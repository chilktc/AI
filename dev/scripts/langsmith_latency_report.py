"""LangSmith에서 에이전트별 LLM 지연 메트릭을 조회하고 리포트를 출력한다.

Usage:
    python3 dev/scripts/langsmith_latency_report.py
    python3 dev/scripts/langsmith_latency_report.py --hours 48
    python3 dev/scripts/langsmith_latency_report.py --agent podcast_reasoning
    python3 dev/scripts/langsmith_latency_report.py --errors-only
    python3 dev/scripts/langsmith_latency_report.py --compare

실행 환경:
    로컬 개발 머신 또는 EC2 호스트에서 실행한다.
    AWS Docker 컨테이너에는 dev/ 폴더가 포함되지 않으므로 컨테이너 내부에서는 실행 불가.
    LangSmith는 클라우드 서비스이므로 LANGCHAIN_API_KEY만 있으면 어디서든 조회 가능.

환경변수:
    LANGCHAIN_API_KEY  — LangSmith API 키 (필수)
    LANGCHAIN_PROJECT  — 프로젝트 이름 (기본값: settings.yaml에서 로드)
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

try:
    from langsmith import Client
except ImportError:
    print("[오류] langsmith 패키지가 설치되지 않았습니다.")
    print("       pip install langsmith")
    sys.exit(1)


# ──────────────────────────────────────────────
# 설정 로드
# ──────────────────────────────────────────────

def _load_project_name() -> str:
    """settings.yaml에서 LangSmith 프로젝트 이름을 읽는다."""
    env_val = os.environ.get("LANGCHAIN_PROJECT", "")
    if env_val:
        return env_val
    try:
        from config.loader import get_settings
        settings = get_settings()
        monitoring = settings._config.get("monitoring", {})
        return monitoring.get("langsmith", {}).get("project", "mind-log")
    except Exception:
        return "mind-log"


# ──────────────────────────────────────────────
# 데이터 조회
# ──────────────────────────────────────────────

def _list_projects(client: Client) -> list[str]:
    """LangSmith에 등록된 프로젝트 이름 목록을 반환한다."""
    return [p.name for p in client.list_projects()]


def _fetch_runs(
    client: Client,
    project_name: str,
    start_time: datetime,
    end_time: datetime,
    agent_filter: str | None,
    limit: int = 500,
) -> list[Any]:
    """LangSmith에서 LLM 스팬을 조회한다.

    LLM 스팬을 사용하는 이유:
    - run.metadata["agent_name"] 으로 에이전트명 식별 가능
    - run.outputs["metadata"] 에 bedrock_call_ms, sem_wait_ms 포함
    - 실제 LLM 호출 지연 시간이 직접 측정됨
    """
    from langsmith.utils import LangSmithNotFoundError

    _PAGE_SIZE = 100  # LangSmith API 최대 허용값

    kwargs: dict[str, Any] = {
        "project_name": project_name,
        "run_type": "llm",
        "start_time": start_time,
        "end_time": end_time,
        "limit": _PAGE_SIZE,
    }
    if agent_filter:
        kwargs["filter"] = f'has(metadata, \'has(metadata, "agent_name:{agent_filter}")\')'

    try:
        runs: list[Any] = []
        seen_ids: set[str] = set()
        while len(runs) < limit:
            page = list(client.list_runs(**kwargs))
            if not page:
                break
            # 중복 제거 후 추가
            new_runs = [r for r in page if str(r.id) not in seen_ids]
            for r in new_runs:
                seen_ids.add(str(r.id))
            runs.extend(new_runs)
            if len(page) < _PAGE_SIZE:
                break  # 마지막 페이지
            # 다음 페이지: cursor 방식 — 마지막 run의 start_time 1ms 앞으로 설정
            from datetime import timedelta as _td
            kwargs["end_time"] = page[-1].start_time - _td(milliseconds=1)
    except LangSmithNotFoundError:
        projects = _list_projects(client)
        print(f"\n[오류] 프로젝트 '{project_name}'를 LangSmith에서 찾을 수 없습니다.")
        print("\n등록된 프로젝트 목록:")
        for name in projects:
            print(f"  - {name}")
        print(f"\n--project 옵션으로 올바른 프로젝트를 지정하거나,")
        print(f"LANGCHAIN_PROJECT 환경변수를 위 이름 중 하나로 설정하세요.")
        sys.exit(1)

    return runs


# ──────────────────────────────────────────────
# 통계 계산
# ──────────────────────────────────────────────

def _calc_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * 0.95) - 1)
    return sorted_vals[idx]


def _run_duration_ms(run: Any) -> float:
    """run의 총 실행 시간(ms)을 반환한다."""
    if run.end_time and run.start_time:
        delta = run.end_time - run.start_time
        return delta.total_seconds() * 1000
    return 0.0


def _build_stats(runs: list[Any]) -> dict[str, dict[str, Any]]:
    """에이전트명 기준으로 통계를 집계한다.

    run.metadata["agent_name"] 으로 에이전트를 식별하고,
    run.outputs["metadata"] 에서 bedrock_call_ms / sem_wait_ms 를 추출한다.
    """
    grouped: dict[str, list[Any]] = defaultdict(list)
    for run in runs:
        # metadata["agent_name"] 우선, 없으면 run.name (모델 ID) 사용
        agent_name = (run.metadata or {}).get("agent_name") or run.name
        grouped[agent_name].append(run)

    stats: dict[str, dict[str, Any]] = {}
    for agent_name, agent_runs in grouped.items():
        total = len(agent_runs)
        errors = [r for r in agent_runs if r.error]
        durations = [_run_duration_ms(r) for r in agent_runs if _run_duration_ms(r) > 0]

        # Bedrock 메타데이터: outputs["metadata"]에 저장됨 (base_agent.py:543-548)
        bedrock_ms_list: list[float] = []
        sem_wait_ms_list: list[float] = []
        retry_counts: list[int] = []

        for run in agent_runs:
            out_meta = (run.outputs or {}).get("metadata") or {}
            bm = out_meta.get("bedrock_call_ms")
            sw = out_meta.get("sem_wait_ms")
            rc = (run.metadata or {}).get("retry_count", 0)

            if bm is not None:
                bedrock_ms_list.append(float(bm))
            if sw is not None:
                sem_wait_ms_list.append(float(sw))
            if rc is not None:
                retry_counts.append(int(rc))

        retried = sum(1 for rc in retry_counts if rc > 0)

        # 에러 메시지 집계
        error_msgs: dict[str, int] = defaultdict(int)
        for r in errors:
            if r.error:
                # 첫 줄만 추출 (긴 traceback 제외)
                first_line = r.error.strip().split("\n")[0][:120]
                error_msgs[first_line] += 1

        stats[agent_name] = {
            "total": total,
            "error_count": len(errors),
            "error_rate": len(errors) / total * 100 if total else 0.0,
            "retry_rate": retried / total * 100 if total else 0.0,
            "avg_ms": statistics.mean(durations) if durations else 0.0,
            "max_ms": max(durations) if durations else 0.0,
            "p95_ms": _calc_p95(durations),
            "avg_bedrock_ms": statistics.mean(bedrock_ms_list) if bedrock_ms_list else None,
            "avg_sem_wait_ms": statistics.mean(sem_wait_ms_list) if sem_wait_ms_list else None,
            "error_msgs": dict(sorted(error_msgs.items(), key=lambda x: -x[1])),
        }

    return stats


# ──────────────────────────────────────────────
# 출력
# ──────────────────────────────────────────────

def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "   N/A"
    if val >= 10_000:
        return f"{val:>7,.0f}"
    return f"{val:>7,.0f}"


def _print_report(
    stats: dict[str, dict[str, Any]],
    prev_stats: dict[str, dict[str, Any]] | None,
    start_time: datetime,
    end_time: datetime,
    project_name: str,
    errors_only: bool,
) -> None:
    print()
    print("=" * 110)
    print(f"  LangSmith 에이전트 지연 리포트")
    print(f"  프로젝트: {project_name}")
    print(f"  기간: {start_time.strftime('%Y-%m-%d %H:%M')} ~ {end_time.strftime('%Y-%m-%d %H:%M')} (UTC)")
    print("=" * 110)

    if not stats:
        print("  [데이터 없음] 해당 기간에 LLM runs가 없습니다.")
        print()
        return

    # 헤더
    if not errors_only:
        print(
            f"{'에이전트명':<28} {'호출':>5} {'평균(ms)':>9} {'P95(ms)':>9} "
            f"{'최대(ms)':>9} {'bedrock(ms)':>12} {'sem_wait(ms)':>13} "
            f"{'재시도율':>8} {'에러율':>7}  {'변화'}"
        )
        print("-" * 110)

    # 평균 기준 내림차순 정렬
    sorted_agents = sorted(stats.items(), key=lambda x: -x[1]["avg_ms"])

    all_errors: dict[str, dict[str, int]] = {}

    for agent_name, s in sorted_agents:
        if errors_only and s["error_count"] == 0:
            continue

        # 이전 기간 대비 변화율 계산
        change_marker = ""
        if prev_stats and agent_name in prev_stats:
            prev_avg = prev_stats[agent_name]["avg_ms"]
            curr_avg = s["avg_ms"]
            if prev_avg > 0:
                ratio = curr_avg / prev_avg
                if ratio >= 2.0:
                    change_marker = f"  ★ {ratio:.1f}x 증가"
                elif ratio >= 1.5:
                    change_marker = f"  ↑ {ratio:.1f}x"
                elif ratio <= 0.7:
                    change_marker = f"  ↓ {ratio:.1f}x"

        if not errors_only:
            print(
                f"{agent_name:<28} {s['total']:>5} "
                f"{_fmt_ms(s['avg_ms'])} "
                f"{_fmt_ms(s['p95_ms'])} "
                f"{_fmt_ms(s['max_ms'])} "
                f"{_fmt_ms(s['avg_bedrock_ms']):>12} "
                f"{_fmt_ms(s['avg_sem_wait_ms']):>13} "
                f"{s['retry_rate']:>7.1f}% "
                f"{s['error_rate']:>6.1f}%"
                f"{change_marker}"
            )

        if s["error_msgs"]:
            all_errors[agent_name] = s["error_msgs"]

    # 에러 섹션
    if all_errors:
        print()
        print("─" * 110)
        print("  에러 상위 목록")
        print("─" * 110)
        # 에러를 횟수 기준 평탄화
        flat: list[tuple[str, str, int]] = []
        for agent_name, msgs in all_errors.items():
            for msg, cnt in msgs.items():
                flat.append((agent_name, msg, cnt))
        flat.sort(key=lambda x: -x[2])
        for i, (agent_name, msg, cnt) in enumerate(flat[:10], 1):
            print(f"  {i:>2}. [{cnt:>3}회] {agent_name} — {msg}")

    # 비교 없는 경우 힌트 출력
    if prev_stats is None and not errors_only:
        print()
        print("  Tip: --compare 옵션을 사용하면 이전 동일 기간과 지연을 비교합니다.")

    print("=" * 110)
    print()


def _print_diagnosis(stats: dict[str, dict[str, Any]], prev_stats: dict[str, dict[str, Any]] | None) -> None:
    """지연 증가 에이전트에 대한 원인 진단 힌트를 출력한다."""
    suspects: list[tuple[str, float, str]] = []

    for agent_name, s in stats.items():
        if prev_stats and agent_name in prev_stats:
            prev_avg = prev_stats[agent_name]["avg_ms"]
            if prev_avg > 0 and s["avg_ms"] / prev_avg >= 2.0:
                # 원인 추정
                bedrock_ms = s["avg_bedrock_ms"] or 0
                sem_ms = s["avg_sem_wait_ms"] or 0
                retry_rate = s["retry_rate"]

                if retry_rate > 10:
                    cause = f"Bedrock ThrottlingException 재시도 ({retry_rate:.1f}%) — max_concurrent 조정 검토"
                elif sem_ms > bedrock_ms and sem_ms > 1000:
                    cause = f"세마포어 대기 병목 (sem_wait 평균 {sem_ms:.0f}ms) — 동시성 설정 확인"
                elif bedrock_ms > 5000:
                    cause = f"Bedrock API 자체 응답 지연 ({bedrock_ms:.0f}ms) — AWS 리전 상태 확인"
                else:
                    cause = "원인 불명 — LangSmith UI에서 개별 트레이스 확인 권장"

                suspects.append((agent_name, s["avg_ms"] / prev_avg, cause))

    if suspects:
        print()
        print("─" * 80)
        print("  [진단] 2배 이상 지연 증가 에이전트")
        print("─" * 80)
        for agent_name, ratio, cause in suspects:
            print(f"  • {agent_name} ({ratio:.1f}x): {cause}")
        print()
        print("  참고: config/settings.yaml → llm.bedrock.max_concurrent")
        print()


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LangSmith 에이전트 지연 분석 리포트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--hours", type=int, default=24, help="조회 기간 (시간, 기본값: 24)")
    parser.add_argument("--project", type=str, default=None, help="LangSmith 프로젝트 이름 (기본값: settings.yaml 또는 LANGCHAIN_PROJECT)")
    parser.add_argument("--agent", type=str, default=None, help="특정 에이전트만 조회 (예: podcast_reasoning)")
    parser.add_argument("--errors-only", action="store_true", help="에러가 있는 에이전트만 출력")
    parser.add_argument("--compare", action="store_true", help="이전 동일 기간과 지연 비교")
    parser.add_argument("--limit", type=int, default=500, help="조회 최대 runs 수 (기본값: 500, 페이지당 100개씩 자동 페이지네이션)")
    parser.add_argument("--list-projects", action="store_true", help="LangSmith에 등록된 프로젝트 목록만 출력")
    args = parser.parse_args()

    api_key = os.environ.get("LANGCHAIN_API_KEY", "")
    if not api_key:
        print("[오류] LANGCHAIN_API_KEY 환경변수가 설정되지 않았습니다.")
        print("       export LANGCHAIN_API_KEY=<your_langsmith_api_key>")
        sys.exit(1)

    client = Client(api_key=api_key)

    if args.list_projects:
        print("\nLangSmith 프로젝트 목록:")
        for name in _list_projects(client):
            print(f"  - {name}")
        print()
        sys.exit(0)

    project_name = args.project or _load_project_name()

    now = datetime.now(tz=timezone.utc)
    end_time = now
    start_time = now - timedelta(hours=args.hours)

    print(f"\n조회 중... (프로젝트: {project_name}, 최근 {args.hours}시간)")

    runs = _fetch_runs(client, project_name, start_time, end_time, args.agent, args.limit)
    print(f"  → {len(runs)}개 LLM runs 수집 완료")

    stats = _build_stats(runs)

    # 비교 모드: 이전 동일 기간 조회
    prev_stats: dict[str, dict[str, Any]] | None = None
    if args.compare:
        prev_end = start_time
        prev_start = start_time - timedelta(hours=args.hours)
        print(f"  → 이전 기간 조회 중 ({prev_start.strftime('%m-%d %H:%M')} ~ {prev_end.strftime('%m-%d %H:%M')})...")
        prev_runs = _fetch_runs(client, project_name, prev_start, prev_end, args.agent, args.limit)
        print(f"  → {len(prev_runs)}개 LLM runs 수집 완료")
        prev_stats = _build_stats(prev_runs)

    _print_report(stats, prev_stats, start_time, end_time, project_name, args.errors_only)

    if args.compare:
        _print_diagnosis(stats, prev_stats)


if __name__ == "__main__":
    main()

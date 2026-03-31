"""Bedrock 모델 최적화 테스트 — 오케스트레이터.

Phase별 테스트를 관리하고, 서브프로세스를 스케줄링한다.
Chrome MCP를 통해 AWS SSM에서 직접 실행한다.

사용법:
    python -m dev.live_tests.run_bedrock_model_test --phase all
    python -m dev.live_tests.run_bedrock_model_test --phase calibration
    python -m dev.live_tests.run_bedrock_model_test --phase 0
    python -m dev.live_tests.run_bedrock_model_test --phase 1
    python -m dev.live_tests.run_bedrock_model_test --phase 1 --agent safety
    python -m dev.live_tests.run_bedrock_model_test --phase 1 --retry-failed
    python -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 1
    python -m dev.live_tests.run_bedrock_model_test --phase 3 --optimal-config path/to/config.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


# --- 상수 ---

RESULTS_DIR = Path(__file__).parent / "results" / "bedrock_model_test"
PROGRESS_FILE = RESULTS_DIR / "progress.json"
CALIBRATION_FILE = RESULTS_DIR / "calibration.json"

RUNS_PER_MODEL = 3
DEFAULT_MAX_CONCURRENT = 2
PROCESS_TIMEOUT = 600  # 10분
INTER_PROCESS_DELAY = 5  # 초


# --- 유틸리티 ---

def _get_memory_mb() -> dict[str, int]:
    """가용 메모리를 /proc/meminfo에서 읽는다."""
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"):
                    info[parts[0].rstrip(":")] = int(parts[1]) // 1024
        return {
            "total_mb": info.get("MemTotal", 0),
            "available_mb": info.get("MemAvailable", 0),
            "swap_used_mb": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
        }
    except FileNotFoundError:
        return {"total_mb": 0, "available_mb": 0, "swap_used_mb": 0}


def _load_progress() -> dict[str, Any]:
    """진행 상황을 로드한다. 없으면 초기값 반환."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"completed": 0, "failed": 0, "failed_tests": []}


def _save_progress(progress: dict[str, Any]) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    progress["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


# --- Phase 0: 연결 확인 ---

async def run_phase0() -> None:
    """모든 Bedrock 모델의 연결을 확인한다."""
    # Bedrock 프로바이더 설정
    os.environ["LLM_PROVIDER"] = "bedrock"
    import config.loader
    config.loader._settings_instance = None  # Reset so bedrock provider is picked up

    from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS

    print("\n" + "=" * 60)
    print("Phase 0: Bedrock 모델 연결 확인")
    print("=" * 60)

    phase0_dir = RESULTS_DIR / "phase0"
    phase0_dir.mkdir(parents=True, exist_ok=True)

    # 텍스트 모델 (Claude)
    for model in BEDROCK_MODELS:
        print(f"\n  [{model['short']}] {model['model_id']}...", end=" ")
        try:
            from src.agents.shared.llm_client import LLMClient
            client = LLMClient(agent_name="connectivity_test", model_override=model["model_id"])

            start = time.perf_counter()
            response = await client.generate(
                system_prompt="연결 테스트입니다.",
                user_message="Hello",
                max_tokens=10,
                temperature=0.0,
            )
            elapsed = time.perf_counter() - start

            result = {"model": model, "status": "ok", "response_time": round(elapsed, 2), "response": response[:100]}
            print(f"OK ({elapsed:.1f}s)")

        except Exception as e:
            result = {"model": model, "status": "error", "error": str(e), "error_type": type(e).__name__}
            print(f"FAIL: {e}")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = phase0_dir / f"connectivity_{model['short']}_{timestamp}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # 이미지 모델 — VisualizationAgent로 실제 생성 1회 시도
    if not IMAGE_MODELS:
        print("\n  이미지 모델 없음, 건너뜀")
    for model in IMAGE_MODELS:
        print(f"\n  [{model['short']}] {model['model_id']}...", end=" ")
        try:
            from src.agents.podcast.visualization import VisualizationAgent
            config.loader._settings_instance = None
            _settings = config.loader.get_settings()
            viz_cfg = _settings._config.setdefault("agents", {}).setdefault("visualization", {})
            viz_cfg["image_model"] = model["model_id"]

            agent = VisualizationAgent()
            start = time.perf_counter()
            test_state = {
                "emotion_vectors": {"joy": 0.5},
                "content_analysis": {},
                "mode": "podcast",
                "user_id": "phase0-test",
            }
            result_data = await agent.process(test_state)
            elapsed = time.perf_counter() - start

            img_status = result_data.get("visual_data", {}).get("status", "unknown")
            result = {
                "model": model,
                "status": "ok" if img_status != "error" else "error",
                "response_time": round(elapsed, 2),
                "image_status": img_status,
            }
            print(f"OK ({elapsed:.1f}s, status={img_status})")
        except Exception as e:
            result = {
                "model": model,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
            print(f"FAIL: {e}")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = phase0_dir / f"connectivity_{model['short']}_{timestamp}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # IMAGE_MODELS 루프 종료 후 — 다음 Phase에 settings 오염 방지
    config.loader._settings_instance = None

    print(f"\n  Phase 0 완료 -> {phase0_dir}")


# --- Phase 0.5: 캘리브레이션 ---

async def run_calibration(max_test: int = 3) -> dict[str, Any]:
    """인스턴스의 동시성/메모리/Rate Limit을 실측한다."""
    print("\n" + "=" * 60)
    print("Phase 0.5: 캘리브레이션")
    print("=" * 60)

    cal: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instance": _get_memory_mb(),
    }

    # C-1: 단일 파이프라인 메모리 + 시간
    print("\n  [C-1] 단일 파이프라인 실행 (메모리/시간 측정)...")
    mem_before = _get_memory_mb()

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "dev.live_tests.run_single_bedrock_test",
        "--agent", "intent_classifier",
        "--model-id", "anthropic.claude-3-haiku-20240307-v1:0",
        "--model-short", "cal-haiku",
        "--run", "0",
        "--output", str(RESULTS_DIR / "calibration_single.json"),
        "--skip-viz", "true",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=PROCESS_TIMEOUT)

    mem_after = _get_memory_mb()
    cal_result_path = RESULTS_DIR / "calibration_single.json"

    if proc.returncode == 0 and cal_result_path.exists():
        single = json.loads(cal_result_path.read_text(encoding="utf-8"))
        cal["single_pipeline"] = {
            "duration_sec": single.get("runtime", {}).get("pipeline_seconds", 0),
            "memory_before": mem_before,
            "memory_after": mem_after,
            "memory_delta_mb": mem_before["available_mb"] - mem_after["available_mb"],
            "status": "ok",
        }
        print(f"    소요: {cal['single_pipeline']['duration_sec']}s, 메모리 변화: -{cal['single_pipeline']['memory_delta_mb']}MB")
    else:
        cal["single_pipeline"] = {"status": "error", "stderr": stderr.decode()[:500]}
        print(f"    실패: {stderr.decode()[:200]}")

    # C-3/C-4: 동시성 테스트
    for n in range(2, max_test + 1):
        print(f"\n  [C-{n+1}] 동시 {n}프로세스 안정성 테스트...")
        mem_before = _get_memory_mb()

        tasks = []
        for i in range(n):
            p = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "dev.live_tests.run_single_bedrock_test",
                "--agent", "intent_classifier",
                "--model-id", "anthropic.claude-3-haiku-20240307-v1:0",
                "--model-short", f"cal-concurrent-{i}",
                "--run", str(i),
                "--output", str(RESULTS_DIR / f"calibration_concurrent_{n}_{i}.json"),
                "--skip-viz", "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            tasks.append(p)

        results = []
        start = time.perf_counter()

        async def _wait_proc(proc: asyncio.subprocess.Process) -> dict[str, Any]:
            try:
                _, err = await asyncio.wait_for(proc.communicate(), timeout=PROCESS_TIMEOUT)
                return {"returncode": proc.returncode, "stderr": err.decode()[:200]}
            except asyncio.TimeoutError:
                proc.kill()
                return {"returncode": -1, "stderr": "timeout"}

        results = await asyncio.gather(*[_wait_proc(p) for p in tasks])

        elapsed = time.perf_counter() - start
        mem_after = _get_memory_mb()

        all_ok = all(r["returncode"] == 0 for r in results)
        status = "ok" if all_ok else "failed"
        cal[f"{n}_processes"] = {
            "status": status,
            "duration_sec": round(elapsed, 1),
            "memory_after": mem_after,
            "results": results,
        }
        print(f"    {status.upper()} ({elapsed:.1f}s), 가용메모리: {mem_after['available_mb']}MB")

        if not all_ok:
            print(f"    동시 {n}프로세스 불안정 -- max_concurrent = {n - 1}로 결정")
            break

    # 추천값 결정
    max_concurrent = 1
    for n in range(2, max_test + 1):
        if cal.get(f"{n}_processes", {}).get("status") == "ok":
            max_concurrent = n
        else:
            break

    cal["recommended"] = {
        "max_concurrent": max_concurrent,
        "execution_mode": "subprocess",
    }

    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(cal, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  캘리브레이션 완료 -> max_concurrent = {max_concurrent}")
    print(f"  저장: {CALIBRATION_FILE}")

    return cal


# --- Phase 1: 벤치마크 ---

async def run_phase1(
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    agent_filter: str | None = None,
    retry_failed: bool = False,
) -> None:
    """에이전트별 모델 벤치마크를 실행한다."""
    from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS, AGENT_OUTPUT_FIELDS

    print("\n" + "=" * 60)
    print(f"Phase 1: 벤치마크 (max_concurrent={max_concurrent})")
    print("=" * 60)

    phase1_dir = RESULTS_DIR / "phase1"
    phase1_dir.mkdir(parents=True, exist_ok=True)

    agents = list(AGENT_OUTPUT_FIELDS.keys())
    if agent_filter:
        agents = [a for a in agents if a == agent_filter]

    progress = _load_progress()
    progress["phase"] = "phase1"
    progress["started_at"] = progress.get("started_at", time.strftime("%Y-%m-%dT%H:%M:%SZ"))

    semaphore = asyncio.Semaphore(max_concurrent)

    for agent_name in agents:
        if agent_name == "visualization":
            skip_viz = "false"
            models = IMAGE_MODELS
        else:
            skip_viz = "true"
            models = BEDROCK_MODELS

        if not models:
            print(f"\n> {agent_name}: 모델 목록 비어 있음, 건너뜀")
            continue

        print(f"\n> {agent_name} ({len(models)} 모델 x {RUNS_PER_MODEL} 회)")

        tasks = []
        for model in models:
            for run in range(1, RUNS_PER_MODEL + 1):
                output_file = phase1_dir / f"{agent_name}_{model['short']}_run{run}.json"

                # 이미 완료된 결과가 있으면 건너뜀 (retry-failed 아닐 때)
                if output_file.exists() and not retry_failed:
                    existing = json.loads(output_file.read_text(encoding="utf-8"))
                    if "error" not in existing:
                        continue

                # retry-failed: 에러가 있는 것만 재실행
                if retry_failed and output_file.exists():
                    existing = json.loads(output_file.read_text(encoding="utf-8"))
                    if "error" not in existing:
                        continue

                tasks.append({
                    "agent": agent_name,
                    "model_id": model["model_id"],
                    "model_short": model["short"],
                    "run": run,
                    "output": str(output_file),
                    "skip_viz": skip_viz,
                })

        if not tasks:
            print("  (모든 테스트 완료됨, 건너뜀)")
            continue

        print(f"  실행할 테스트: {len(tasks)}회")

        async def _run_one(task: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                # 메모리 확인
                mem = _get_memory_mb()
                if mem["available_mb"] < 500 and mem["available_mb"] > 0:
                    print(f"  [!] 메모리 부족 ({mem['available_mb']}MB), 30초 대기...")
                    await asyncio.sleep(30)

                cmd = [
                    sys.executable, "-m", "dev.live_tests.run_single_bedrock_test",
                    "--agent", task["agent"],
                    "--model-id", task["model_id"],
                    "--model-short", task["model_short"],
                    "--run", str(task["run"]),
                    "--output", task["output"],
                    "--skip-viz", task["skip_viz"],
                ]
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=PROCESS_TIMEOUT,
                    )
                    if proc.returncode == 0:
                        progress["completed"] = progress.get("completed", 0) + 1
                    else:
                        progress["failed"] = progress.get("failed", 0) + 1
                        progress.setdefault("failed_tests", []).append({
                            "agent": task["agent"],
                            "model": task["model_short"],
                            "run": task["run"],
                            "error": stderr.decode()[:200],
                        })
                    _save_progress(progress)
                    await asyncio.sleep(INTER_PROCESS_DELAY)
                    return {"task": task, "returncode": proc.returncode, "stdout": stdout.decode()[:200]}

                except asyncio.TimeoutError:
                    progress["failed"] = progress.get("failed", 0) + 1
                    progress.setdefault("failed_tests", []).append({
                        "agent": task["agent"], "model": task["model_short"],
                        "run": task["run"], "error": "timeout",
                    })
                    _save_progress(progress)
                    return {"task": task, "returncode": -1, "error": "timeout"}

        results = await asyncio.gather(*[_run_one(t) for t in tasks])
        successes = sum(1 for r in results if r.get("returncode") == 0)
        failures = len(results) - successes
        print(f"  [v] {agent_name}: {successes}/{len(results)} 성공 (실패: {failures})")

    progress["phase"] = "phase1_complete"
    _save_progress(progress)
    print(f"\n  Phase 1 완료 -> {phase1_dir}")


# --- Phase 3: 최적 조합 검증 ---

async def run_phase3(
    optimal_config_path: str | None = None,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> None:
    """최적 조합 + Baseline을 각 5회씩 실행한다."""
    from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS

    RUNS_PHASE3 = 5

    print("\n" + "=" * 60)
    print(f"Phase 3: 최적 파이프라인 검증 (max_concurrent={max_concurrent})")
    print("=" * 60)

    phase3_dir = RESULTS_DIR / "phase3"
    phase3_dir.mkdir(parents=True, exist_ok=True)

    # 최적 조합은 Phase 2 (로컬) 산출 후 config로 전달
    if optimal_config_path and Path(optimal_config_path).exists():
        optimal = json.loads(Path(optimal_config_path).read_text(encoding="utf-8"))
    else:
        print("  최적 조합 설정 파일이 필요합니다 (--optimal-config)")
        print("  Phase 2를 로컬에서 먼저 실행하세요.")
        return

    # model_short → model_id 매핑
    model_id_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}
    image_model_id_map = {m["short"]: m["model_id"] for m in IMAGE_MODELS}

    best_models: dict[str, dict[str, Any]] = optimal.get("best_models", optimal)
    print(f"  대상 에이전트: {len(best_models)}개, 각 {RUNS_PHASE3}회 실행")

    progress = _load_progress()
    progress["phase"] = "phase3"
    _save_progress(progress)

    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = []
    for agent_name, info in best_models.items():
        model_short = info["model_short"]

        if agent_name == "visualization":
            model_id = image_model_id_map.get(model_short)
            skip_viz = "false"
        else:
            model_id = model_id_map.get(model_short)
            skip_viz = "true"

        if not model_id:
            print(f"  [!] {agent_name}: model_short '{model_short}' 매핑 없음, 건너뜀")
            continue

        for run in range(1, RUNS_PHASE3 + 1):
            output_file = phase3_dir / f"{agent_name}_{model_short}_run{run}.json"
            if output_file.exists():
                existing = json.loads(output_file.read_text(encoding="utf-8"))
                if "error" not in existing:
                    continue

            tasks.append({
                "agent": agent_name,
                "model_id": model_id,
                "model_short": model_short,
                "run": run,
                "output": str(output_file),
                "skip_viz": skip_viz,
            })

    print(f"  실행할 테스트: {len(tasks)}회")

    async def _run_one(task: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            mem = _get_memory_mb()
            if mem["available_mb"] < 500 and mem["available_mb"] > 0:
                print(f"  [!] 메모리 부족 ({mem['available_mb']}MB), 30초 대기...")
                await asyncio.sleep(30)

            cmd = [
                sys.executable, "-m", "dev.live_tests.run_single_bedrock_test",
                "--agent", task["agent"],
                "--model-id", task["model_id"],
                "--model-short", task["model_short"],
                "--run", str(task["run"]),
                "--output", task["output"],
                "--skip-viz", task["skip_viz"],
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=PROCESS_TIMEOUT,
                )
                if proc.returncode == 0:
                    progress["completed"] = progress.get("completed", 0) + 1
                    print(f"  [v] {task['agent']} / {task['model_short']} run{task['run']}")
                else:
                    progress["failed"] = progress.get("failed", 0) + 1
                    progress.setdefault("failed_tests", []).append({
                        "agent": task["agent"],
                        "model": task["model_short"],
                        "run": task["run"],
                        "error": stderr.decode()[:200],
                    })
                    print(f"  [x] {task['agent']} / {task['model_short']} run{task['run']}: {stderr.decode()[:100]}")
                _save_progress(progress)
                await asyncio.sleep(INTER_PROCESS_DELAY)
                return {"task": task, "returncode": proc.returncode}

            except asyncio.TimeoutError:
                progress["failed"] = progress.get("failed", 0) + 1
                progress.setdefault("failed_tests", []).append({
                    "agent": task["agent"],
                    "model": task["model_short"],
                    "run": task["run"],
                    "error": "timeout",
                })
                _save_progress(progress)
                print(f"  [!] {task['agent']} / {task['model_short']} run{task['run']}: timeout")
                return {"task": task, "returncode": -1, "error": "timeout"}

    results = await asyncio.gather(*[_run_one(t) for t in tasks])
    successes = sum(1 for r in results if r.get("returncode") == 0)
    failures = len(results) - successes

    progress["phase"] = "phase3_complete"
    _save_progress(progress)
    print(f"\n  Phase 3 완료 -> {phase3_dir}")
    print(f"  결과: {successes}/{len(results)} 성공 (실패: {failures})")


# --- CLI ---

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bedrock 모델 최적화 테스트 오케스트레이터")
    parser.add_argument("--phase", required=True,
                        choices=["all", "calibration", "0", "1", "3"],
                        help="실행할 Phase")
    parser.add_argument("--max-concurrent", type=int, default=None,
                        help="동시 실행 프로세스 수 (캘리브레이션 결과 오버라이드)")
    parser.add_argument("--agent", default=None,
                        help="특정 에이전트만 실행 (Phase 1)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="실패한 테스트만 재실행 (Phase 1)")
    parser.add_argument("--optimal-config", default=None,
                        help="최적 조합 설정 JSON 경로 (Phase 3)")
    return parser


async def main_async() -> None:
    parser = create_parser()
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # max_concurrent 결정
    max_concurrent = args.max_concurrent
    if max_concurrent is None:
        if CALIBRATION_FILE.exists():
            cal = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
            max_concurrent = cal.get("recommended", {}).get("max_concurrent", DEFAULT_MAX_CONCURRENT)
        else:
            max_concurrent = DEFAULT_MAX_CONCURRENT

    if args.phase in ("all", "calibration"):
        await run_calibration()

    if args.phase in ("all", "0"):
        await run_phase0()

    if args.phase in ("all", "1"):
        await run_phase1(
            max_concurrent=max_concurrent,
            agent_filter=args.agent,
            retry_failed=args.retry_failed,
        )

    if args.phase == "3":
        await run_phase3(optimal_config_path=args.optimal_config, max_concurrent=max_concurrent)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

"""Bedrock 모델 최적화 테스트 — 종합점수 산출.

Phase 1 결과 JSON을 읽어 에이전트별 (모델 x 지표) 매트릭스를 구성하고,
가중 종합점수를 산출한다.

로컬에서 실행 — 표준 라이브러리만 사용 (json, statistics, pathlib).

사용법:
    python -m dev.live_tests.scoring \
        --input dev/live_tests/results/bedrock_model_test/ \
        --output dev/live_tests/results/bedrock_model_test/summary/
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from dev.live_tests.evaluator_criteria import DEFAULT_WEIGHTS


def load_phase1_results(input_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Phase 1 결과를 에이전트-모델 쌍으로 그룹핑한다.

    Returns:
        {"safety__c35-sonnet-v2": [run1, run2, run3], ...}
    """
    phase1_dir = input_dir / "phase1"
    if not phase1_dir.exists():
        print(f"Phase 1 결과 디렉토리 없음: {phase1_dir}")
        return {}

    groups: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(phase1_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if "error" in data and "test_info" not in data:
            continue

        info = data.get("test_info", {})
        agent = info.get("agent", "unknown")
        model_short = info.get("model_short", "unknown")
        key = f"{agent}__{model_short}"
        groups.setdefault(key, []).append(data)

    return groups


def compute_agent_model_stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """동일 에이전트-모델 쌍의 반복 실행 결과에서 통계를 산출한다."""
    scores = []
    times = []
    failures = 0

    for run in runs:
        if "error" in run:
            failures += 1
            continue

        eval_score = run.get("evaluation", {}).get("total_score", 0.0)
        pipeline_time = run.get("runtime", {}).get("pipeline_seconds", 0.0)

        if isinstance(eval_score, (int, float)):
            scores.append(float(eval_score))
        if isinstance(pipeline_time, (int, float)):
            times.append(float(pipeline_time))

    total = len(runs)
    success_count = total - failures

    return {
        "runs": total,
        "successes": success_count,
        "failures": failures,
        "failure_rate": failures / total if total > 0 else 1.0,
        "quality_mean": statistics.mean(scores) if scores else 0.0,
        "quality_std": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "quality_min": min(scores) if scores else 0.0,
        "speed_mean": statistics.mean(times) if times else 0.0,
        "speed_max": max(times) if times else 0.0,
        "individual_scores": scores,
        "individual_times": times,
    }


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """min-max 정규화 (0~1)."""
    if max_val == min_val:
        return 1.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def compute_composite_scores(
    agent_stats: dict[str, dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """에이전트-모델 쌍별 종합점수를 산출한다.

    종합점수 = quality*0.35 + consistency*0.25 + speed*0.15 + cost*0.10 + reliability*0.15
    """
    w = weights or DEFAULT_WEIGHTS

    if not agent_stats:
        return {}

    # 동일 에이전트 내에서 정규화
    agents: dict[str, list[str]] = {}
    for key in agent_stats:
        agent = key.split("__")[0]
        agents.setdefault(agent, []).append(key)

    results: dict[str, dict[str, Any]] = {}

    for agent, keys in agents.items():
        stats_list = [agent_stats[k] for k in keys]

        # 정규화 범위 계산
        all_quality = [s["quality_mean"] for s in stats_list]
        all_std = [s["quality_std"] for s in stats_list]
        all_speed = [s["speed_mean"] for s in stats_list]

        max_std = max(all_std) if all_std else 1.0
        max_speed = max(all_speed) if all_speed else 1.0

        for key, stats in zip(keys, stats_list):
            quality_norm = stats["quality_mean"]  # 이미 0~1 범위
            consistency_norm = 1.0 - (stats["quality_std"] / max_std if max_std > 0 else 0.0)
            speed_norm = 1.0 - (stats["speed_mean"] / max_speed if max_speed > 0 else 0.0)
            cost_norm = speed_norm  # 토큰 사용량 ≈ 속도에 비례 (간이 근사)
            reliability_norm = 1.0 - stats["failure_rate"]

            composite = (
                quality_norm * w["quality"]
                + consistency_norm * w["consistency"]
                + speed_norm * w["speed"]
                + cost_norm * w["cost_efficiency"]
                + reliability_norm * w["reliability"]
            )

            results[key] = {
                **stats,
                "dimensions": {
                    "quality": round(quality_norm, 4),
                    "consistency": round(consistency_norm, 4),
                    "speed": round(speed_norm, 4),
                    "cost_efficiency": round(cost_norm, 4),
                    "reliability": round(reliability_norm, 4),
                },
                "composite_score": round(composite, 4),
            }

    return results


def select_best_models(composite: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """에이전트별 최적 모델을 선정한다.

    1순위: 종합점수 최고
    2순위: 동률 시 일관성(std 낮은) 우선
    3순위: 속도 빠른 모델 우선
    """
    agents: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for key, data in composite.items():
        agent = key.split("__")[0]
        agents.setdefault(agent, []).append((key, data))

    best: dict[str, dict[str, Any]] = {}
    for agent, candidates in agents.items():
        sorted_candidates = sorted(
            candidates,
            key=lambda x: (
                -x[1]["composite_score"],
                x[1]["quality_std"],
                x[1]["speed_mean"],
            ),
        )
        winner_key, winner_data = sorted_candidates[0]
        model_short = winner_key.split("__")[1]
        best[agent] = {
            "model_short": model_short,
            "composite_score": winner_data["composite_score"],
            "quality_mean": winner_data["quality_mean"],
            "quality_std": winner_data["quality_std"],
            "speed_mean": winner_data["speed_mean"],
            "failure_rate": winner_data["failure_rate"],
        }

    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedrock 모델 테스트 종합점수 산출")
    parser.add_argument("--input", required=True, help="결과 디렉토리 (bedrock_model_test/)")
    parser.add_argument("--output", required=True, help="집계 결과 저장 디렉토리")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 결과 로드
    groups = load_phase1_results(input_dir)
    print(f"로드된 에이전트-모델 쌍: {len(groups)}")

    # 2. 통계 산출
    agent_stats = {key: compute_agent_model_stats(runs) for key, runs in groups.items()}

    # 3. 종합점수 산출
    composite = compute_composite_scores(agent_stats)

    # 4. 최적 모델 선정
    best = select_best_models(composite)

    # 5. 결과 저장
    aggregated = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weights": DEFAULT_WEIGHTS,
        "best_models": best,
        "composite_scores": composite,
    }

    out_path = output_dir / "aggregated_results.json"
    out_path.write_text(json.dumps(aggregated, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. 요약 출력
    print(f"\n{'='*60}")
    print("에이전트별 최적 모델")
    print(f"{'='*60}")
    for agent, info in sorted(best.items()):
        print(f"  {agent:25s} → {info['model_short']:15s} (score={info['composite_score']:.3f}, "
              f"quality={info['quality_mean']:.3f}±{info['quality_std']:.3f})")

    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()

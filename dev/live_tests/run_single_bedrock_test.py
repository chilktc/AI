"""Bedrock 모델 최적화 테스트 — 단일 테스트 워커.

subprocess로 호출되며, 독립 프로세스에서 1회의 E2E 파이프라인 + Evaluator 채점을 수행한다.
Settings/환경변수가 다른 워커와 완전히 격리된다.

사용법:
    python -m dev.live_tests.run_single_bedrock_test \\
        --agent safety \\
        --model-id "apac.anthropic.claude-3-5-sonnet-20241022-v2:0" \\
        --model-short c35-sonnet-v2 \\
        --run 1 \\
        --output results/bedrock_model_test/phase1/safety_c35-sonnet-v2_run1.json \\
        --skip-viz true
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


def _get_memory_mb() -> dict[str, int]:
    """가용 메모리를 /proc/meminfo에서 읽는다 (Linux 전용)."""
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


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bedrock 단일 테스트 워커")
    parser.add_argument("--agent", required=True, help="테스트 대상 에이전트 이름")
    parser.add_argument("--model-id", required=True, help="Bedrock 모델 ID")
    parser.add_argument("--model-short", required=True, help="모델 약칭 (결과 파일용)")
    parser.add_argument("--run", type=int, required=True, help="반복 번호 (1, 2, 3)")
    parser.add_argument("--output", required=True, help="결과 JSON 저장 경로")
    parser.add_argument("--skip-viz", default="true", help="Visualization 스킵 여부")
    parser.add_argument("--evaluator-model", default=None, help="Evaluator 모델 ID 오버라이드")
    return parser


async def run_test(args: argparse.Namespace) -> dict[str, Any]:
    """단일 E2E 테스트를 실행하고 결과를 반환한다."""

    # 1. 환경변수 설정
    os.environ["LLM_PROVIDER"] = "bedrock"
    os.environ["SKIP_VISUALIZATION"] = args.skip_viz

    # 2. Settings 리셋 + 대상 에이전트 모델 오버라이드
    import config.loader
    config.loader._settings_instance = None
    settings = config.loader.get_settings()

    agent_cfg = settings._config.setdefault("agents", {}).setdefault(args.agent, {})
    agent_cfg["model_id"] = args.model_id

    # Evaluator 모델 오버라이드 (지정 시)
    if args.evaluator_model:
        os.environ["EVALUATOR_MODEL_OVERRIDE"] = args.evaluator_model

    # 3. 워크플로우 빌드 + 실행
    from src.graph.workflow import build_unified_graph
    from src.api.client import BackendClient
    from unittest.mock import AsyncMock, patch
    from dev.live_tests.conftest_live import Timer
    from dev.live_tests.fixtures import make_e2e_state

    initial_state = make_e2e_state()
    graph = build_unified_graph()
    compiled = graph.compile()

    mock_response = {"success": True, "id": f"bedrock-test-{args.agent}", "message": "saved"}
    memory_before = _get_memory_mb()

    with patch.object(BackendClient, "save", new_callable=AsyncMock, return_value=mock_response):
        with Timer() as t:
            final_state = await compiled.ainvoke(initial_state)

    memory_after = _get_memory_mb()
    pipeline_elapsed = t.elapsed

    # 4. 파이프라인 결과 검증
    from dev.live_tests.evaluator_criteria import AGENT_OUTPUT_FIELDS

    expected_fields = [
        "intent", "safety_flags", "emotion_vectors",
        "content_analysis", "reasoning_result",
        "script_draft", "validation_result", "final_output",
    ]
    fields_present = sum(1 for f in expected_fields if final_state.get(f))

    vr = final_state.get("validation_result", {})
    bv_score = vr.get("overall_score", vr.get("score", 0.0)) if isinstance(vr, dict) else 0.0
    rr = final_state.get("reasoning_result", {})
    confidence = rr.get("confidence", 0.0) if isinstance(rr, dict) else 0.0
    final_output = final_state.get("final_output", "")
    final_output_len = len(final_output) if isinstance(final_output, str) else 0

    # 5. Evaluator Agent 채점
    from dev.live_tests.evaluator_agent import evaluate

    with Timer() as t_eval:
        evaluation = await evaluate(
            agent_name=args.agent,
            pipeline_state=final_state,
            user_input=initial_state["user_input"],
        )

    evaluator_elapsed = t_eval.elapsed

    # 6. 결과 조립
    result: dict[str, Any] = {
        "test_info": {
            "test_type": "bedrock_model_comparison",
            "agent": args.agent,
            "model_id": args.model_id,
            "model_short": args.model_short,
            "run": args.run,
            "skip_visualization": args.skip_viz,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "runtime": {
            "pipeline_seconds": round(pipeline_elapsed, 2),
            "evaluator_seconds": round(evaluator_elapsed, 2),
            "total_seconds": round(pipeline_elapsed + evaluator_elapsed, 2),
        },
        "memory": {
            "before": memory_before,
            "after": memory_after,
        },
        "pipeline_result": {
            "fields_present": fields_present,
            "fields_total": len(expected_fields),
            "bv_score": bv_score,
            "confidence": confidence,
            "final_output_len": final_output_len,
        },
        "evaluation": evaluation,
    }

    # 대상 에이전트 출력 필드 저장
    agent_fields = AGENT_OUTPUT_FIELDS.get(args.agent, [])
    agent_output: dict[str, Any] = {}
    for field in agent_fields:
        value = final_state.get(field)
        if value is not None:
            agent_output[field] = value
    result["agent_output"] = agent_output

    return result


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    # 출력 디렉토리 생성
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[워커] {args.agent} / {args.model_short} / run {args.run}")

    try:
        result = asyncio.run(run_test(args))

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        score = result.get("evaluation", {}).get("total_score", "N/A")
        elapsed = result.get("runtime", {}).get("total_seconds", "N/A")
        print(f"[완료] score={score}, elapsed={elapsed}s → {output_path}")

    except Exception as e:
        error_result = {
            "test_info": {
                "agent": args.agent,
                "model_id": args.model_id,
                "model_short": args.model_short,
                "run": args.run,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "error": str(e),
            "error_type": type(e).__name__,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        print(f"[실패] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

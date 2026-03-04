"""
E2E LangGraph 워크플로우 멀티 프로바이더 테스트.

실제 LangGraph 워크플로우(build_unified_graph → compile → ainvoke)를 통해
intent_classifier부터 END까지 전체 노드가 동작하는 것을 검증한다.

팟캐스트모드 기본 — 모든 에이전트가 실제 구현체(telemetry만 STUB).

실행 흐름:
    TIER 0: IntentClassifier (REAL — LLM 의도 분류)
    TIER 1 (병렬 Fan-out): Safety + Emotion + ContentAnalyzer + PodcastReasoning
    TIER 2: ScriptGenerator (REAL)
    TIER 3: BatchValidator (REAL)
    TIER 4: ScriptPersonalizer (REAL)
    비동기: Visualization + Telemetry(stub) + Learning

사용법:
    # 전체 (Ollama 2모델 + OpenAI)
    python3 -m dev.live_tests.test_e2e_multi_provider

    # Ollama만
    python3 -m dev.live_tests.test_e2e_multi_provider --ollama-only

    # OpenAI만
    python3 -m dev.live_tests.test_e2e_multi_provider --openai-only

    # 커스텀 입력 JSON
    python3 -m dev.live_tests.test_e2e_multi_provider --input test_inputs/my_scenario.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from dev.live_tests.conftest_live import (
    Timer,
    check_provider_health,
    print_banner,
    print_error,
    print_section,
    setup_provider,
)
from dev.live_tests.fixtures import load_state_from_json, make_e2e_state

logger = logging.getLogger(__name__)

# ────────────────────────────────────────
# 기본 설정
# ────────────────────────────────────────

DEFAULT_OLLAMA_MODELS = ["gpt-oss:20b", "qwen2.5:14b"]
DEFAULT_OPENAI_MODEL = "gpt-5-mini"

# ANSI 컬러
_G = "\033[92m"  # green
_R = "\033[91m"  # red
_Y = "\033[93m"  # yellow
_C = "\033[96m"  # cyan
_B = "\033[1m"   # bold
_0 = "\033[0m"   # reset

# 검증할 상태 필드 (에이전트 → 필드명)
EXPECTED_FIELDS = [
    "intent",             # TIER 0: IntentClassifier
    "safety_flags",       # TIER 1: Safety
    "emotion_vectors",    # TIER 1: Emotion
    "content_analysis",   # TIER 1: ContentAnalyzer
    "reasoning_result",   # TIER 1: PodcastReasoning
    "script_draft",       # TIER 2: ScriptGenerator
    "validation_result",  # TIER 3: BatchValidator
    "final_output",       # TIER 4: ScriptPersonalizer
]


# ────────────────────────────────────────
# 싱글톤 리프레시
# ────────────────────────────────────────


def _refresh_all_singletons() -> None:
    """
    프로바이더 전환 후 모든 에이전트 싱글톤을 재생성한다.

    모든 에이전트 모듈은 모듈 레벨에서 싱글톤 인스턴스를 생성한다.
    프로바이더를 전환(환경변수 LLM_PROVIDER 변경 + Settings 리셋)한 뒤
    이 함수를 호출하면 새 프로바이더 설정이 적용된 에이전트가 생성된다.

    대상:
        - workflow.py 내부 3개 (reset_agents)
        - 에이전트 모듈 내부 8개 (직접 교체)
    """
    import importlib

    # 1) Settings 싱글톤 리셋
    from config.loader import get_settings

    settings = get_settings()
    settings._instance = None  # type: ignore[attr-defined]

    # 2) workflow.py 내부 싱글톤 리셋 (reset_agents 함수 사용)
    from src.graph import workflow

    importlib.reload(workflow)

    # 3) 에이전트 모듈 싱글톤 교체
    agent_modules = [
        "src.agents.podcast.safety",
        "src.agents.podcast.emotion",
        "src.agents.podcast.content_analyzer",
        "src.agents.podcast.podcast_reasoning",
        "src.agents.podcast.batch_validator",
        "src.agents.podcast.visualization",
        "src.agents.shared.learning",
        "src.agents.podcast.episode_memory",
    ]

    for module_name in agent_modules:
        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)
        except Exception as e:
            logger.warning("싱글톤 리프레시 실패 — %s: %s", module_name, e)


# ────────────────────────────────────────
# 결과 검증
# ────────────────────────────────────────


def _validate_result(state: dict[str, Any]) -> dict[str, Any]:
    """
    ainvoke() 반환 상태에서 주요 필드를 검증한다.

    Returns:
        검증 결과 dict:
            fields_present: 존재하는 필드 수
            fields_total: 총 검증 필드 수
            main_theme: ContentAnalyzer가 추출한 주제
            confidence: PodcastReasoning confidence
            bv_score: BatchValidator 점수
            strategy: 추론 전략
            final_output_len: 최종 출력 길이
    """
    present = sum(1 for f in EXPECTED_FIELDS if state.get(f))
    total = len(EXPECTED_FIELDS)

    # ContentAnalyzer
    ca = state.get("content_analysis", {})
    main_theme = ca.get("main_theme", "N/A") if isinstance(ca, dict) else "N/A"

    # PodcastReasoning
    rr = state.get("reasoning_result", {})
    confidence = rr.get("confidence", "N/A") if isinstance(rr, dict) else "N/A"
    strategy = rr.get("reasoning_strategy", "N/A") if isinstance(rr, dict) else "N/A"

    # BatchValidator
    vr = state.get("validation_result", {})
    bv_score = "N/A"
    if isinstance(vr, dict):
        bv_score = vr.get("overall_score", vr.get("score", "N/A"))

    # ScriptPersonalizer
    final_output = state.get("final_output", "")
    final_output_len = len(final_output) if isinstance(final_output, str) else 0

    return {
        "fields_present": present,
        "fields_total": total,
        "main_theme": main_theme,
        "confidence": confidence,
        "bv_score": bv_score,
        "strategy": strategy,
        "final_output_len": final_output_len,
    }


# ────────────────────────────────────────
# 단일 프로바이더/모델 워크플로우 실행
# ────────────────────────────────────────


async def run_workflow_for_model(
    provider: str,
    model_name: str,
    initial_state: dict[str, Any],
) -> dict[str, Any] | None:
    """
    지정된 프로바이더/모델로 실제 LangGraph 워크플로우를 실행한다.

    Args:
        provider: LLM 프로바이더 (ollama, openai)
        model_name: 모델명
        initial_state: ainvoke에 전달할 초기 상태

    Returns:
        결과 요약 dict 또는 실패 시 None
    """
    label = f"{provider}/{model_name}"
    print_banner(f"E2E LangGraph 워크플로우: {label}", color="cyan")

    # 1. 프로바이더 셋업
    print_section("프로바이더 셋업")
    setup_provider(provider, model_name)

    # 2. 싱글톤 리프레시 (프로바이더 전환 반영)
    print_section("싱글톤 리프레시")
    _refresh_all_singletons()
    print(f"  {_G}[OK]{_0} 모든 에이전트 싱글톤 재생성 완료")

    # 3. 헬스체크
    print_section("헬스체크")
    healthy = await check_provider_health(provider)
    if not healthy:
        print(f"  {_Y}[SKIP]{_0} {label} — 헬스체크 실패")
        return None

    try:
        # 4. LangGraph 워크플로우 빌드 + 컴파일
        print_section("LangGraph 워크플로우 빌드")
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        node_names = [n for n in compiled.nodes.keys() if not n.startswith("__")]
        print(f"  {_G}[OK]{_0} 빌드 완료 — {len(node_names)}개 노드")

        # 5. BackendClient.save() mock + ainvoke 실행
        print_section("ainvoke 실행 (전체 워크플로우)")
        print(f"  입력: user_input({len(initial_state.get('user_input', ''))}자), mode={initial_state.get('mode')}")

        from src.api.client import BackendClient

        mock_response = {"success": True, "id": "e2e-test-001", "message": "saved"}

        with patch.object(
            BackendClient, "save", new_callable=AsyncMock, return_value=mock_response
        ):
            with Timer() as t_total:
                final_state = await compiled.ainvoke(initial_state)

        elapsed = t_total.elapsed
        print(f"\n  {_G}[OK]{_0} ainvoke 완료 — {elapsed:.1f}초")

        # 6. 결과 검증
        print_section("결과 검증")
        validation = _validate_result(final_state)

        fields_ok = validation["fields_present"]
        fields_total = validation["fields_total"]
        status = _G if fields_ok == fields_total else _Y
        print(f"  필드: {status}{fields_ok}/{fields_total}{_0}")

        for field in EXPECTED_FIELDS:
            val = final_state.get(field)
            if val:
                if isinstance(val, dict):
                    keys = list(val.keys())[:4]
                    print(f"  {_G}✓{_0} {field}: dict({len(val)} keys) — {keys}")
                elif isinstance(val, str):
                    preview = val[:60] + "..." if len(val) > 60 else val
                    print(f"  {_G}✓{_0} {field}: str({len(val)}자) — {preview}")
                else:
                    print(f"  {_G}✓{_0} {field}: {type(val).__name__}")
            else:
                print(f"  {_R}✗{_0} {field}: 없음")

        print(f"\n  main_theme: {validation['main_theme']}")
        print(f"  confidence: {validation['confidence']}")
        print(f"  strategy: {validation['strategy']}")
        print(f"  bv_score: {validation['bv_score']}")
        print(f"  final_output: {validation['final_output_len']}자")

        # 7. 결과 파일 저장 (results 폴더)
        _save_results_to_file(provider, model_name, final_state, elapsed, validation)

        return {
            "provider": provider,
            "model": model_name,
            "success": True,
            "total_time": elapsed,
            "fields_present": fields_ok,
            "fields_total": fields_total,
            "main_theme": validation["main_theme"],
            "confidence": validation["confidence"],
            "strategy": validation["strategy"],
            "bv_score": validation["bv_score"],
            "final_output_len": validation["final_output_len"],
        }

    except Exception as e:
        print_error(f"E2E ({label})", e)
        import traceback

        traceback.print_exc()
        return None


# ────────────────────────────────────────
# 결과 파일 저장
# ────────────────────────────────────────


def _save_results_to_file(
    provider: str,
    model_name: str,
    final_state: dict[str, Any],
    elapsed: float,
    validation: dict[str, Any],
) -> None:
    """
    E2E 테스트 결과를 dev/live_tests/results/ 폴더에 JSON으로 저장한다.

    visualization_result, emotion_vectors 등 주요 에이전트 출력을 모두 포함한다.
    """
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    # 파일명: {provider}_{model}_{timestamp}.json
    safe_model = model_name.replace(":", "_").replace("/", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{provider}_{safe_model}_{timestamp}.json"

    # 저장할 데이터 구성
    result_data: dict[str, Any] = {
        "test_info": {
            "provider": provider,
            "model": model_name,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_time_seconds": round(elapsed, 2),
        },
        "validation_summary": validation,
    }

    # 주요 에이전트 출력 필드 저장
    for field in EXPECTED_FIELDS:
        val = final_state.get(field)
        if val is not None:
            result_data[field] = val

    # visualization_result 저장 (비동기 에이전트 출력)
    vis_result = final_state.get("visualization_result")
    if vis_result:
        result_data["visualization_result"] = vis_result

    # visual_data 저장 (있는 경우)
    visual_data = final_state.get("visual_data")
    if visual_data:
        result_data["visual_data"] = visual_data

    file_path = results_dir / filename
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  {_G}[SAVED]{_0} 결과 저장: {file_path}")
    except Exception as e:
        print(f"\n  {_Y}[WARN]{_0} 결과 저장 실패: {e}")


# ────────────────────────────────────────
# 비교 테이블 출력
# ────────────────────────────────────────


def print_comparison_table(results: list[dict[str, Any]]) -> None:
    """프로바이더/모델별 결과 비교 테이블을 출력한다."""
    print_banner("E2E 멀티 프로바이더 비교 결과", color="green")

    if not results:
        print("  실행된 테스트가 없습니다.")
        return

    # 테이블 헤더
    header = (
        f"{'Provider/Model':<26}{'Status':>8}{'Total':>8}"
        f"{'Fields':>8}  {'Main Theme':<24}{'Confidence':>12}{'BV Score':>10}"
    )
    separator = "─" * len(header)

    print(f"\n{_B}{header}{_0}")
    print(separator)

    for r in results:
        if not r or not r.get("success"):
            provider = r.get("provider", "?") if r else "?"
            model = r.get("model", "?") if r else "?"
            label = f"{provider}/{model}"
            print(f"{_R}{label:<26}{'[FAIL]':>8}{_0}")
            continue

        label = f"{r['provider']}/{r['model']}"
        if len(label) > 25:
            label = label[:23] + ".."

        # main_theme 자르기 (최대 22자)
        theme = r.get("main_theme", "N/A")
        if isinstance(theme, str) and len(theme) > 22:
            theme = theme[:20] + ".."

        # 수치 포맷팅
        confidence = r.get("confidence", "N/A")
        confidence_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence)

        bv_score = r.get("bv_score", "N/A")
        bv_score_str = f"{bv_score:.2f}" if isinstance(bv_score, (int, float)) else str(bv_score)

        fields_str = f"{r['fields_present']}/{r['fields_total']}"

        row = (
            f"{label:<26}{_G}{'[OK]':>8}{_0}"
            f"{r['total_time']:>7.1f}s"
            f"{fields_str:>8}  {theme:<24}{confidence_str:>12}{bv_score_str:>10}"
        )
        print(row)

    print(separator)

    # 성공/실패 요약
    success_count = sum(1 for r in results if r and r.get("success"))
    fail_count = len(results) - success_count
    print(f"\n  결과: {_G}{success_count} 성공{_0} / {_R}{fail_count} 실패{_0} (총 {len(results)}개)")


# ────────────────────────────────────────
# 메인 실행
# ────────────────────────────────────────


async def run_all_providers(
    ollama_models: list[str] | None = None,
    openai_model: str | None = None,
    ollama_only: bool = False,
    openai_only: bool = False,
    input_file: str | None = None,
) -> list[dict[str, Any]]:
    """
    모든 프로바이더/모델 조합으로 E2E LangGraph 워크플로우 테스트를 실행한다.

    Args:
        ollama_models: Ollama 모델 리스트 (기본: gpt-oss:20b, qwen2.5:14b)
        openai_model: OpenAI 모델 (기본: gpt-4o-mini)
        ollama_only: Ollama만 테스트
        openai_only: OpenAI만 테스트
        input_file: 커스텀 입력 JSON 파일 경로 (None이면 기본 입력 사용)

    Returns:
        각 모델별 결과 dict 리스트
    """
    if ollama_models is None:
        ollama_models = DEFAULT_OLLAMA_MODELS
    if openai_model is None:
        openai_model = DEFAULT_OPENAI_MODEL

    # 초기 상태 로드
    if input_file:
        initial_state = load_state_from_json(input_file)
        input_source = f"커스텀 JSON: {input_file}"
    else:
        initial_state = make_e2e_state()
        input_source = "기본 입력 (fixtures.make_e2e_state)"

    print_banner("E2E LangGraph 워크플로우 멀티 프로바이더 테스트", color="bold")
    print(f"  테스트 일시: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  입력 소스: {input_source}")
    print(f"  입력 텍스트 길이: {len(initial_state.get('user_input', ''))}자")
    print(f"  모드: {initial_state.get('mode', 'N/A')}")

    if not openai_only:
        print(f"  Ollama 모델: {', '.join(ollama_models)}")
    if not ollama_only:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            print(f"  OpenAI 모델: {openai_model}")
        else:
            print(f"  OpenAI: {_Y}OPENAI_API_KEY 미설정 — 스킵{_0}")

    print(f"\n  워크플로우: intent_classifier → TIER1(fan-out) → script_generator"
          f" → batch_validator → script_personalizer → async → END")

    results: list[dict[str, Any]] = []
    total_start = time.perf_counter()

    # ── Ollama 모델들 ──
    if not openai_only:
        for model in ollama_models:
            result = await run_workflow_for_model("ollama", model, initial_state)
            results.append(result or {"provider": "ollama", "model": model, "success": False})

    # ── OpenAI ──
    if not ollama_only:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            result = await run_workflow_for_model("openai", openai_model, initial_state)
            results.append(
                result or {"provider": "openai", "model": openai_model, "success": False}
            )
        else:
            print(f"\n  {_Y}[SKIP]{_0} OpenAI — OPENAI_API_KEY 미설정")
            print("  .env 파일에 OPENAI_API_KEY=sk-... 을 추가하세요.")

    total_elapsed = time.perf_counter() - total_start

    # 비교 테이블 출력
    print_comparison_table(results)
    print(f"  전체 소요 시간: {total_elapsed:.2f}초\n")

    return results


def create_parser() -> argparse.ArgumentParser:
    """CLI 인자를 파싱하는 argparse 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="E2E LangGraph 워크플로우 멀티 프로바이더 테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 (Ollama 2모델 + OpenAI)
  python3 -m dev.live_tests.test_e2e_multi_provider

  # Ollama만
  python3 -m dev.live_tests.test_e2e_multi_provider --ollama-only

  # OpenAI만
  python3 -m dev.live_tests.test_e2e_multi_provider --openai-only

  # Ollama 모델 지정
  python3 -m dev.live_tests.test_e2e_multi_provider --ollama-models gpt-oss:20b,mistral-small:24b

  # 커스텀 입력 JSON
  python3 -m dev.live_tests.test_e2e_multi_provider --input dev/live_tests/test_inputs/my_scenario.json
        """,
    )

    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--ollama-only",
        action="store_true",
        help="Ollama 모델만 테스트",
    )
    scope.add_argument(
        "--openai-only",
        action="store_true",
        help="OpenAI만 테스트",
    )

    parser.add_argument(
        "--ollama-models",
        default=None,
        help=f"Ollama 모델 (콤마 구분, 기본: {','.join(DEFAULT_OLLAMA_MODELS)})",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help=f"OpenAI 모델 (기본: {DEFAULT_OPENAI_MODEL})",
    )
    parser.add_argument(
        "--input",
        dest="input_file",
        default=None,
        help="커스텀 테스트 입력 JSON 파일 경로",
    )

    return parser


def main() -> None:
    """CLI 메인 엔트리포인트."""
    parser = create_parser()
    args = parser.parse_args()

    ollama_models = None
    if args.ollama_models:
        ollama_models = [m.strip() for m in args.ollama_models.split(",")]

    asyncio.run(
        run_all_providers(
            ollama_models=ollama_models,
            openai_model=args.openai_model,
            ollama_only=args.ollama_only,
            openai_only=args.openai_only,
            input_file=args.input_file,
        )
    )


if __name__ == "__main__":
    main()

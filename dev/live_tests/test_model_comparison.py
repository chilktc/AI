"""
멀티 모델 비교 라이브 테스트 — 지정된 Ollama 모델로 3개 에이전트를 실행하고 결과를 파일로 저장.

테스트 대상 (비동기 에이전트 제외):
  1. Content Analyzer (TIER 1)
  2. Podcast Reasoning (TIER 1)
  3. Batch Validator (TIER 3)

사용법:
    cd /Users/kttechup/Documents/NewProject/mind-log
    python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b
    python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b --output results/qwen2.5_14b.txt

    # 추론 깊이별 테스트 (complexity_score 조정)
    python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b --complexity 0.9   # full: GoT+ToT+CoT
    python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b --complexity 0.7   # standard: ToT+CoT (기본값)
    python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b --complexity 0.3   # minimal: CoT only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any



# ════════════════════════════════════════
# 사용자 입력 텍스트
# ════════════════════════════════════════
USER_INPUT = (
    "아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어. "
    "내가 과장 진급하고 위에서 하도 성과를 가지고 압박하길래 나도 나름대로 할 수 있을 수준으로 힘들게 네고하고, "
    "후배한테도 최대한 좋게 전달하려고 했던 건데 이렇게 뒷담을 들어야 한다는게 너무 짜증난다. "
    "나도 나름대로 중간에서 조율을 하고 내가 할 일을 하는 건데, "
    "그거가지고 친하게 지내던 후배가 뒷담을 하는게 너무 실망이고 오히려 그러니까 나도 그냥 차갑게 대하고 싶어. "
    "근데 그래봤자 나만 겉돌게 되는건 아닌지 무섭기도 하고… "
    "그렇다고 상사랑 친하게 지내기도 어려운게 진짜 내 상사는 진짜 말이 안 통함. "
    "아직은 그냥 모른척 내가 하던대로 하고 있어. "
    "그런데 후배를 마주치면 나도 모르게 얼굴이 굳고 좀 거리감이 느껴져서 괜히 툭 툭 내뱉듯이 말을 하게 되는 거 같아. "
    "후배는 내가 뒷담화 들은 걸 모르니까 그냥 아직까지는 자연스럽게 대하려고 하는거 같아. "
    "내가 업무 지시를 해도 그냥 웃으면서 잘 받고. 근데 그 뒤에 불만이 가득 쌓인거지. 차라리 말을 하던지."
)


# 전역 complexity 설정 (CLI에서 설정)
_COMPLEXITY_SCORE: float = 0.7


def _depth_label(complexity: float) -> str:
    """complexity_score에 따른 추론 깊이 레이블 반환."""
    if complexity >= 0.8:
        return "full (GoT+ToT+CoT, LLM 3회)"
    elif complexity >= 0.5:
        return "standard (ToT+CoT, LLM 2회)"
    else:
        return "minimal (CoT only, LLM 1회)"


class DualOutput:
    """stdout과 파일에 동시에 출력하는 래퍼."""

    def __init__(self, filepath: str | None):
        self.terminal = sys.stdout
        self.log = None
        if filepath:
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            self.log = open(filepath, "w", encoding="utf-8")

    def write(self, message: str) -> None:
        self.terminal.write(message)
        if self.log:
            # ANSI 코드 제거
            import re
            clean = re.sub(r"\033\[[0-9;]*m", "", message)
            self.log.write(clean)

    def flush(self) -> None:
        self.terminal.flush()
        if self.log:
            self.log.flush()

    def close(self) -> None:
        if self.log:
            self.log.close()


class Timer:
    """소요 시간 측정."""
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self._start: float = 0.0
    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self
    def __exit__(self, *args: Any) -> None:
        self.elapsed = time.perf_counter() - self._start


def make_custom_state() -> dict[str, Any]:
    return {
        "user_input": USER_INPUT,
        "user_id": "user_model_test_001",
        "session_id": "sess_model_test_001",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "interpersonal_conflict",
            "complexity_score": _COMPLEXITY_SCORE,
            "topic_hint": "직장 내 뒷담화와 중간관리자의 갈등",
            "risk_flag": False,
        },
    }


def print_json(data: Any, indent: int = 4) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=indent))


# ════════════════════════════════════════
# 에이전트 테스트
# ════════════════════════════════════════


async def test_content_analyzer() -> dict[str, Any] | None:
    print("\n" + "=" * 70)
    print(" [AGENT 1] Content Analyzer (TIER 1)")
    print("=" * 70)
    try:
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        state = make_custom_state()
        print(f"  complexity_score: {state['intent']['complexity_score']}")

        with Timer() as t:
            result = await agent(state)

        ca = result.get("content_analysis", {})
        print(f"\n  소요 시간: {t.elapsed:.2f}초")
        print(f"  LLM 호출 횟수: 1회")
        print(f"\n  === content_analysis 전체 출력 ===")
        print_json(ca)

        expected = ["main_theme", "sub_themes", "episode_type", "depth_level",
                     "target_duration", "narrative_structure"]
        print(f"\n  === 필드 검증 ===")
        for f in expected:
            status = "OK" if f in ca else "MISSING"
            print(f"  [{status}] {f}")

        return result
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_podcast_reasoning() -> dict[str, Any] | None:
    print("\n" + "=" * 70)
    print(" [AGENT 2] Podcast Reasoning (TIER 1)")
    print("=" * 70)
    try:
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()
        state = make_custom_state()
        complexity = state["intent"]["complexity_score"]
        depth = _depth_label(complexity)

        print(f"  complexity_score: {complexity}")
        print(f"  예상 추론 깊이: {depth}")

        with Timer() as t:
            result = await agent(state)

        rr = result.get("reasoning_result", {})
        print(f"\n  소요 시간: {t.elapsed:.2f}초")

        # LLM 호출 횟수 추정
        has_got = "got_result" in rr
        has_tot = "tot_result" in rr
        llm_calls = (1 if has_got else 0) + (1 if has_tot else 0) + 1  # CoT always
        print(f"  LLM 호출 횟수: {llm_calls}회 (GoT:{has_got}, ToT:{has_tot})")

        print(f"\n  === reasoning_result 전체 출력 ===")
        print_json(rr)

        expected = ["episode_structure", "narrative_flow", "key_points",
                     "emotional_journey", "confidence", "reasoning_strategy"]
        print(f"\n  === 필드 검증 ===")
        for f in expected:
            status = "OK" if f in rr else "MISSING"
            val = rr.get(f, "N/A")
            if isinstance(val, list):
                val = f"[{len(val)}개 항목]"
            elif isinstance(val, dict):
                val = f"{{{len(val)}개 키}}"
            elif isinstance(val, str) and len(val) > 80:
                val = val[:80] + "..."
            print(f"  [{status}] {f}: {val}")

        return result
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_batch_validator(
    content_analysis: dict[str, Any],
    reasoning_result: dict[str, Any],
) -> dict[str, Any] | None:
    print("\n" + "=" * 70)
    print(" [AGENT 3] Batch Validator (TIER 3)")
    print("=" * 70)
    try:
        from src.agents.podcast.batch_validator import BatchValidatorAgent
        from dev.live_tests.fixtures import generate_mock_script

        temp_state = make_custom_state()
        temp_state["content_analysis"] = content_analysis
        temp_state["reasoning_result"] = reasoning_result
        script_draft = generate_mock_script(temp_state)

        state = make_custom_state()
        state["content_analysis"] = content_analysis
        state["reasoning_result"] = reasoning_result
        state["script_draft"] = script_draft
        state["safety_flags"] = {"risk_level": "safe", "crisis_detected": False, "content_warnings": []}
        state["emotion_vectors"] = {"primary_emotion": "anger", "secondary_emotion": "disappointment",
                                     "intensity": 0.7, "valence": -0.5}
        state["iteration_count"] = 0

        print(f"  script_draft.title: {script_draft.get('title', 'N/A')}")
        print(f"  script_draft.segments: {len(script_draft.get('segments', []))}개")
        print(f"  script_draft.total_duration: {script_draft.get('total_duration', 'N/A')}초")

        agent = BatchValidatorAgent()

        with Timer() as t:
            result = await agent(state)

        vr = result.get("validation_result", {})
        print(f"\n  소요 시간: {t.elapsed:.2f}초")
        print(f"  LLM 호출 횟수: 1회")
        print(f"\n  === validation_result 전체 출력 ===")
        print_json(vr)

        passed = vr.get("passed", False)
        score = vr.get("overall_score", "N/A")
        next_step = result.get("next_step", "unknown")
        print(f"\n  === 라우팅 결정 ===")
        print(f"  검증 통과: {passed}")
        print(f"  overall_score: {score}")
        print(f"  next_step: {next_step}")
        print(f"  iteration_count: {result.get('iteration_count', 'N/A')}")

        return result
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ════════════════════════════════════════
# 메인
# ════════════════════════════════════════


async def run_all(model_name: str, output_path: str | None, complexity: float = 0.7) -> None:
    global _COMPLEXITY_SCORE
    _COMPLEXITY_SCORE = complexity

    dual = DualOutput(output_path)
    old_stdout = sys.stdout
    sys.stdout = dual

    try:
        provider = "ollama"

        print("=" * 70)
        print(f" Mind-Log 모델 비교 테스트: {model_name}")
        print("=" * 70)
        print(f"  프로바이더: {provider}")
        print(f"  모델: {model_name}")
        print(f"  complexity_score: {complexity}")
        print(f"  추론 깊이: {_depth_label(complexity)}")
        print(f"  입력 주제: 직장 내 뒷담화 — 중간관리자의 갈등")
        print(f"  입력 텍스트 길이: {len(USER_INPUT)}자")
        print(f"  테스트 일시: {time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 모델 환경변수 설정
        os.environ["LLM_PROVIDER"] = provider
        os.environ["LLM_MODEL_SONNET"] = model_name
        os.environ["LLM_MODEL_HAIKU"] = model_name
        os.environ["LLM_MODEL_OPUS"] = model_name

        # Ollama config의 모델 매핑도 오버라이드
        os.environ["OLLAMA_MODEL_OVERRIDE"] = model_name

        # Settings 싱글톤 리셋
        import config.loader
        config.loader._settings_instance = None

        # Ollama 등록
        from dev.ollama_bootstrap import register_ollama
        register_ollama()

        # Ollama provider의 모델 매핑 패치
        import dev.ollama_provider as op
        original_load = op._load_ollama_config

        def patched_load() -> dict[str, Any]:
            cfg = original_load()
            cfg["models"] = {"haiku": model_name, "sonnet": model_name, "opus": model_name}
            return cfg
        op._load_ollama_config = patched_load

        # 헬스체크
        print(f"\n  === Ollama 헬스체크 ===")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("http://localhost:11434/v1/models")
                models = [m["id"] for m in resp.json().get("data", [])]
                print(f"  서버: OK")
                print(f"  사용 가능 모델: {', '.join(models)}")
                if model_name not in models:
                    # 이름 형식 차이 허용 (예: qwen2.5:14b vs qwen2.5:14b-instruct-...)
                    base = model_name.split(":")[0]
                    found = [m for m in models if base in m]
                    if not found:
                        print(f"  [ERROR] {model_name}이 Ollama에 설치되어 있지 않습니다!")
                        return
        except Exception as e:
            print(f"  [ERROR] Ollama 서버 연결 실패: {e}")
            return

        total_start = time.perf_counter()

        # 1. Content Analyzer
        ca_result = await test_content_analyzer()
        if ca_result is None:
            print("\n  Content Analyzer 실패 — 이후 테스트 중단")
            return

        # 2. Podcast Reasoning
        pr_result = await test_podcast_reasoning()
        if pr_result is None:
            print("\n  Podcast Reasoning 실패 — 이후 테스트 중단")
            return

        # 3. Batch Validator
        content_analysis = ca_result.get("content_analysis", {})
        reasoning_result = pr_result.get("reasoning_result", {})
        bv_result = await test_batch_validator(content_analysis, reasoning_result)

        total_elapsed = time.perf_counter() - total_start

        # 전체 요약
        print("\n" + "=" * 70)
        print(f" 전체 테스트 요약: {model_name}")
        print("=" * 70)
        print(f"  총 소요 시간: {total_elapsed:.2f}초")

        results = {
            "Content Analyzer": ca_result is not None,
            "Podcast Reasoning": pr_result is not None,
            "Batch Validator": bv_result is not None,
        }
        for name, success in results.items():
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} {name}")

        passed = sum(1 for v in results.values() if v)
        print(f"\n  결과: {passed}/{len(results)} 성공")

        # Restore
        op._load_ollama_config = original_load

    finally:
        sys.stdout = old_stdout
        dual.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="모델 비교 테스트")
    parser.add_argument("--model", required=True, help="Ollama 모델명 (예: qwen2.5:14b)")
    parser.add_argument("--output", default=None, help="결과 저장 파일 경로")
    parser.add_argument("--complexity", type=float, default=0.7,
                        help="complexity_score (0.0~1.0). >=0.8: full(GoT+ToT+CoT), >=0.5: standard(ToT+CoT), <0.5: minimal(CoT)")
    args = parser.parse_args()

    asyncio.run(run_all(args.model, args.output, args.complexity))


if __name__ == "__main__":
    main()

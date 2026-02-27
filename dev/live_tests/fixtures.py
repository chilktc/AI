"""
라이브 테스트용 현실적인 한국어 AgentState 데이터.

각 에이전트의 TIER에 맞는 입력 상태를 생성한다.
- TIER 1 에이전트 (Content Analyzer, Podcast Reasoning): user_input + intent만
- TIER 3 에이전트 (Batch Validator): 앞단 결과 전부 포함
- 비동기 에이전트 (Learning): 전체 파이프라인 완료 상태
- E2E 워크플로우: 최소 입력 (user_input + mode만, intent 없음)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def make_content_analyzer_state() -> dict[str, Any]:
    """
    Content Analyzer용 입력 상태 (TIER 1).

    TIER 1은 Intent Classifier 직후 실행되므로
    user_input, intent, user_id, session_id, mode만 채운다.
    """
    return {
        "user_input": (
            "최근에 직장 스트레스가 너무 심해서 잠을 못 자겠어요. "
            "매일 야근을 하다 보니 체력도 떨어지고 우울한 기분이 드는데, "
            "이런 상황에서 마음을 다잡을 수 있는 이야기를 해주세요."
        ),
        "user_id": "user_live_test_001",
        "session_id": "sess_live_test_001",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "stress_management",
            "complexity_score": 0.6,
            "topic_hint": "직장 스트레스와 번아웃",
            "risk_flag": False,
        },
    }


def make_podcast_reasoning_state() -> dict[str, Any]:
    """
    Podcast Reasoning용 입력 상태 (TIER 1).

    TIER 1 병렬 실행이므로 Content Analyzer 결과는 참조 불가.
    user_input과 intent만으로 독립 추론한다.
    complexity_score=0.7 → "standard" 깊이 (ToT → CoT, LLM 2회)
    """
    return {
        "user_input": (
            "불면증이 심해지고 있어요. 밤에 잠자리에 누워도 이런저런 생각이 "
            "떠올라서 쉽게 잠들지 못해요. 수면 위생에 대해 알고 싶고, "
            "잠들기 전에 할 수 있는 명상이나 이완 방법도 궁금합니다."
        ),
        "user_id": "user_live_test_002",
        "session_id": "sess_live_test_002",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "sleep_health",
            "complexity_score": 0.7,
            "topic_hint": "수면 위생과 불면증 대처",
            "risk_flag": False,
        },
    }


def make_batch_validator_state() -> dict[str, Any]:
    """
    Batch Validator용 입력 상태 (TIER 3).

    TIER 1, TIER 2 결과가 모두 포함된 상태.
    script_draft는 개발자1(Script Generator) 출력을 시뮬레이션한다.
    """
    return {
        "user_input": (
            "최근에 인간관계에서 갈등이 생겨서 마음이 힘들어요. "
            "직장 동료와의 관계가 틀어졌는데 어떻게 해결해야 할지 모르겠어요."
        ),
        "user_id": "user_live_test_003",
        "session_id": "sess_live_test_003",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "interpersonal_relations",
            "complexity_score": 0.65,
        },
        # TIER 1 — Content Analyzer 결과
        "content_analysis": {
            "main_theme": "직장 인간관계 갈등과 소통",
            "sub_themes": ["갈등 해결 전략", "감정 조절", "직장 커뮤니케이션"],
            "episode_type": "교육",
            "depth_level": "moderate",
            "target_audience": "직장인",
            "narrative_structure": "problem_solution",
            "target_duration_minutes": 4,
            "keywords": ["인간관계", "갈등", "소통", "직장"],
            "complexity_score": 0.65,
        },
        # TIER 1 — Podcast Reasoning 결과
        "reasoning_result": {
            "episode_structure": [
                {
                    "segment": "intro",
                    "duration_seconds": 30,
                    "description": "직장 내 인간관계의 중요성 소개",
                },
                {
                    "segment": "body_1",
                    "duration_seconds": 90,
                    "description": "갈등의 원인 분석과 감정 인식",
                },
                {
                    "segment": "body_2",
                    "duration_seconds": 90,
                    "description": "건설적 대화법과 해결 전략",
                },
                {
                    "segment": "outro",
                    "duration_seconds": 30,
                    "description": "실천 가능한 행동 제안",
                },
            ],
            "narrative_flow": "공감 → 분석 → 전략 → 실천",
            "key_points": [
                "감정을 먼저 인정하기",
                "I-message로 소통하기",
                "경계 설정의 중요성",
            ],
            "emotional_journey": [
                {"phase": "opening", "emotion": "공감"},
                {"phase": "exploration", "emotion": "이해"},
                {"phase": "resolution", "emotion": "희망"},
            ],
            "confidence": 0.82,
            "reasoning_strategy": "ToT",
        },
        # TIER 1 — Safety Agent 결과 (공용)
        "safety_flags": {
            "risk_level": "safe",
            "crisis_detected": False,
            "content_warnings": [],
        },
        # TIER 1 — Emotion Agent 결과 (공용)
        "emotion_vectors": {
            "primary_emotion": "anxiety",
            "secondary_emotion": "sadness",
            "intensity": 0.6,
            "valence": -0.3,
        },
        # TIER 2 — Script Generator 결과 (개발자1 — 시뮬레이션)
        "script_draft": {
            "title": "직장 내 갈등, 이렇게 풀어보세요",
            "segments": [
                {
                    "type": "intro",
                    "content": (
                        "안녕하세요, Mind-Log 팟캐스트입니다. "
                        "오늘은 많은 분들이 고민하시는 직장 내 인간관계 갈등에 대해 "
                        "이야기해 보겠습니다."
                    ),
                    "duration": 30,
                    "speaker": "host",
                },
                {
                    "type": "body",
                    "content": (
                        "직장에서 동료와의 갈등은 누구나 겪을 수 있는 일입니다. "
                        "중요한 것은 이 갈등을 어떻게 바라보고 대처하느냐입니다. "
                        "먼저, 자신의 감정을 솔직하게 인정하는 것이 첫 번째 단계입니다. "
                        "그 다음으로 상대방의 입장에서 생각해보는 연습을 해볼 수 있습니다. "
                        "대화를 할 때는 '나-전달법(I-message)'을 활용하면 좋습니다."
                    ),
                    "duration": 180,
                    "speaker": "host",
                },
                {
                    "type": "outro",
                    "content": (
                        "오늘 이야기가 도움이 되셨으면 좋겠습니다. "
                        "작은 변화가 큰 차이를 만들 수 있습니다. "
                        "다음 에피소드에서 다시 만나요."
                    ),
                    "duration": 30,
                    "speaker": "host",
                },
            ],
            "total_duration": 240,
            "tone": "warm_supportive",
            "language": "ko",
        },
        # 제어 필드
        "iteration_count": 0,
    }


def make_learning_state() -> dict[str, Any]:
    """
    Learning Agent용 입력 상태 (비동기).

    전체 파이프라인이 완료된 후의 상태.
    모든 주요 필드가 채워져 있어야 패턴 학습이 가능하다.
    """
    # Batch Validator 상태를 기반으로 추가 필드를 채움
    state = make_batch_validator_state()

    # TIER 3 — Batch Validator 결과
    state["validation_result"] = {
        "is_valid": True,
        "overall_score": 0.88,
        "checks": {
            "structure_completeness": {"passed": True, "score": 0.9},
            "safety_compliance": {"passed": True, "score": 1.0},
            "tone_consistency": {"passed": True, "score": 0.85},
            "timing_appropriateness": {"passed": True, "score": 0.9},
            "harmful_content_check": {"passed": True, "score": 1.0},
        },
        "feedback": "스크립트 품질이 양호합니다.",
    }
    state["next_step"] = "script_personalizer"

    # TIER 4 — Script Personalizer 결과 (개발자1 — 시뮬레이션)
    state["final_output"] = (
        "직장 내 갈등, 이렇게 풀어보세요 — "
        "오늘은 많은 분들이 고민하시는 직장 내 인간관계에 대해 이야기합니다..."
    )

    return state


def make_e2e_state() -> dict[str, Any]:
    """
    E2E LangGraph 워크플로우 테스트용 최소 초기 상태.

    직장 내 뒷담화/갈등 시나리오 — 복잡도가 높아
    프로바이더 간 추론 품질 차이를 비교하기에 적합하다.

    **최소 입력**: user_input + user_id + session_id + mode만 전달.
    intent는 pre-fill 하지 않음 — IntentClassifier가 LLM으로 실제 분류한다.
    """
    return {
        "user_input": (
            "- 상황: 아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어. "
            "내가 과장 진급하고 위에서 하도 성과를 가지고 압박하길래 "
            "나도 나름대로 할 수 있을 수준으로 힘들게 네고하고, "
            "후배한테도 최대한 좋게 전달하려고 했던 건데 "
            "이렇게 뒷담을 들어야 한다는게 너무 짜증난다.\n"
            "- 자신의 생각: 나도 나름대로 중간에서 조율을 하고 내가 할 일을 하는 건데, "
            "그거가지고 친하게 지내던 후배가 뒷담을 하는게 너무 실망이고 "
            "오히려 그러니까 나도 그냥 차갑게 대하고 싶어. "
            "근데 그래봤자 나만 겉돌게 되는건 아닌지 무섭기도 하고… "
            "그렇다고 상사랑 친하게 지내기도 어려운게 "
            "진짜 내 상사는 진짜 말이 안 통함.\n"
            "- 자신의 행동 및 반응: 아직은 그냥 모른척 내가 하던대로 하고 있어. "
            "그런데 후배를 마주치면 나도 모르게 얼굴이 굳고 "
            "좀 거리감이 느껴져서 괜히 툭 툭 내뱉듯이 말을 하게 되는 거 같아.\n"
            "- 동료의 반응: 후배는 내가 뒷담화 들은 걸 모르니까 "
            "그냥 아직까지는 자연스럽게 대하려고 하는거 같아. "
            "내가 업무 지시를 해도 그냥 웃으면서 잘 받고. "
            "근데 그 뒤에 불만이 가득 쌓인거지. 차라리 말을 하던지."
        ),
        "user_id": "user_e2e_graph_001",
        "session_id": "sess_e2e_graph_001",
        "mode": "podcast",
    }


def load_state_from_json(file_path: str | Path) -> dict[str, Any]:
    """
    JSON 파일에서 E2E 테스트 초기 상태를 로드한다.

    JSON 파일 형식:
        {
            "user_input": "테스트할 내용...",
            "mode": "podcast",          // 선택, 기본값: "podcast"
            "user_id": "user_xxx",      // 선택, 기본값: "user_e2e_graph_001"
            "session_id": "sess_xxx"    // 선택, 기본값: "sess_e2e_graph_001"
        }

    Args:
        file_path: JSON 파일 경로

    Returns:
        AgentState 초기 dict

    Raises:
        FileNotFoundError: 파일이 존재하지 않을 때
        json.JSONDecodeError: JSON 형식이 올바르지 않을 때
        ValueError: user_input 필드가 없을 때
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"테스트 입력 파일을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "user_input" not in data:
        raise ValueError(f"JSON 파일에 'user_input' 필드가 필수입니다: {path}")

    state: dict[str, Any] = {
        "user_input": data["user_input"],
        "user_id": data.get("user_id", "user_e2e_graph_001"),
        "session_id": data.get("session_id", "sess_e2e_graph_001"),
        "mode": data.get("mode", "podcast"),
    }

    logger.info("커스텀 테스트 입력 로드 완료: %s (mode=%s)", path.name, state["mode"])
    return state


def make_pipeline_initial_state() -> dict[str, Any]:
    """
    파이프라인 시뮬레이션용 초기 상태.

    TIER 0(Intent Classifier) 직후의 최소 상태.
    """
    return {
        "user_input": (
            "요즘 자존감이 많이 떨어졌어요. 자꾸 다른 사람과 비교하게 되고, "
            "내가 잘하고 있는 건지 모르겠어요. 자존감을 높이는 방법에 대해 "
            "이야기해 주세요."
        ),
        "user_id": "user_live_pipeline_001",
        "session_id": "sess_live_pipeline_001",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "self_esteem",
            "complexity_score": 0.6,
            "topic_hint": "자존감 향상",
            "risk_flag": False,
        },
    }


def generate_mock_script(state: dict[str, Any]) -> dict[str, Any]:
    """
    개발자1(Script Generator) 출력을 시뮬레이션한다.

    파이프라인 시뮬레이션에서 TIER 2의 Script Generator 자리를
    대체하는 mock 함수이다.

    개발자1이 Script Generator를 완성하면, 이 함수 호출을
    실제 ScriptGeneratorAgent()(state) 호출로 교체한다.

    왜 mock인가:
    1. Script Generator는 개발자1 담당이며 아직 구현되지 않았다
    2. 이 라이브 테스트의 목적은 개발자3 담당 에이전트의 상태 전파 검증이다
    3. Batch Validator가 script_draft 입력을 필요로 하므로 현실적 데이터를 제공한다

    Args:
        state: TIER 1 완료 후의 AgentState

    Returns:
        script_draft dict
    """
    content_analysis = state.get("content_analysis", {})
    reasoning_result = state.get("reasoning_result", {})

    topic = content_analysis.get("main_theme", "멘탈케어 에피소드")
    key_points = reasoning_result.get("key_points", ["마음 관리의 중요성"])

    # reasoning_result의 episode_structure를 기반으로 세그먼트 생성
    segments = []
    structure = reasoning_result.get("episode_structure", [])

    if structure:
        for seg in structure:
            segments.append(
                {
                    "type": seg.get("segment", "body"),
                    "content": seg.get("description", "내용"),
                    "duration": seg.get("duration_seconds", 60),
                    "speaker": "host",
                }
            )
    else:
        # 기본 구조
        segments = [
            {"type": "intro", "content": f"{topic} 소개", "duration": 30, "speaker": "host"},
            {
                "type": "body",
                "content": f"{', '.join(key_points)}",
                "duration": 180,
                "speaker": "host",
            },
            {"type": "outro", "content": "마무리", "duration": 30, "speaker": "host"},
        ]

    total_duration = sum(s["duration"] for s in segments)

    return {
        "title": topic,
        "segments": segments,
        "total_duration": total_duration,
        "tone": "warm_supportive",
        "language": "ko",
    }

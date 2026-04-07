# Bedrock 모델 최적화 테스트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 팟캐스트 파이프라인 10개 에이전트의 최적 Bedrock 모델을 선정하는 테스트 프레임워크 구현

**Architecture:** 서브프로세스 분리 방식으로 각 테스트를 독립 프로세스에서 실행. 오케스트레이터(`run_bedrock_model_test.py`)가 워커(`run_single_bedrock_test.py`)를 subprocess로 호출하여 Settings/환경변수 충돌을 회피. Evaluator Agent가 Claude 3.5 Sonnet v2로 에이전트 출력을 채점. 결과 JSON은 AWS에서 생성/커밋되고, `scoring.py`는 로컬에서 종합점수를 산출한다.

**Tech Stack:** Python 3.11+ (표준 라이브러리 + 기존 requirements.txt만 사용), LangGraph, boto3, 기존 conftest_live.py/fixtures.py 유틸리티 활용

**Spec:** `docs/superpowers/specs/2026-03-30-bedrock-model-optimization-design.md` (v4)

---

## 파일 구조

```
dev/live_tests/
├── evaluator_criteria.py          # Task 1: 에이전트별 평가 기준 데이터
├── evaluator_agent.py             # Task 2: Evaluator Agent (LLM 채점)
├── run_single_bedrock_test.py     # Task 3: 단일 테스트 워커 (subprocess용)
├── run_bedrock_model_test.py      # Task 4: 오케스트레이터 (Phase 관리)
└── scoring.py                     # Task 5: 종합점수 산출 (로컬용, 표준 라이브러리)
```

---

## 핵심 패턴 참조 (기존 코드에서 발견)

구현 시 반드시 따라야 하는 기존 패턴:

```python
# Settings 리셋 + 모델 오버라이드
import config.loader
config.loader._settings_instance = None
settings = config.loader.get_settings()
agent_cfg = settings._config.setdefault("agents", {}).setdefault(agent_name, {})
agent_cfg["model_id"] = bedrock_model_id  # 직접 패치

# 워크플로우 실행 (BackendClient 모킹 필수)
from src.graph.workflow import build_unified_graph
from src.api.client import BackendClient
from unittest.mock import AsyncMock, patch

graph = build_unified_graph()
compiled = graph.compile()
with patch.object(BackendClient, "save", new_callable=AsyncMock, return_value={"success": True, "id": "test", "message": "saved"}):
    final_state = await compiled.ainvoke(initial_state)

# Timer (conftest_live.py에서 import)
from dev.live_tests.conftest_live import Timer
with Timer() as t:
    result = await compiled.ainvoke(state)
elapsed = t.elapsed

# E2E 초기 상태 (fixtures.py에서 import)
from dev.live_tests.fixtures import make_e2e_state
initial_state = make_e2e_state()

# 에이전트 출력 필드 매핑
AGENT_OUTPUT_FIELDS = {
    "intent_classifier": ["intent", "risk_level", "risk_score", "safety_flags"],
    "safety": ["safety_flags", "risk_level", "risk_score"],
    "emotion": ["emotion_vectors"],
    "content_analyzer": ["content_analysis"],
    "podcast_reasoning": ["reasoning_result", "memory_results", "knowledge_results"],
    "script_generator": ["script_draft"],
    "batch_validator": ["validation_result"],
    "script_personalizer": ["final_output"],
    "visualization": ["visual_data"],
    "learning": [],  # AgentState 변경 없음
}
```

---

## Task 1: evaluator_criteria.py — 에이전트별 평가 기준 정의

**Files:**
- Create: `dev/live_tests/evaluator_criteria.py`

이 파일은 순수 데이터 정의 — 에이전트별 공통/전문 평가 항목을 딕셔너리로 선언한다. LLM 호출 없음.

- [ ] **Step 1: 공통 평가 항목 + 에이전트별 전문 항목 정의**

```python
"""Bedrock 모델 최적화 테스트 — 에이전트별 평가 기준 정의.

Evaluator Agent가 LLM 채점 시 사용하는 평가 항목.
각 항목은 0~1 점수로 채점되며, 한 줄 근거가 함께 반환된다.
"""

from __future__ import annotations

# 모든 에이전트에 공통 적용 (6항목)
COMMON_CRITERIA: list[dict[str, str]] = [
    {"name": "structural_completeness", "description": "필수 필드 존재, 스키마 준수, 타입 정확성"},
    {"name": "output_stability", "description": "JSON 파싱 가능, 예외 없이 정상 종료"},
    {"name": "instruction_compliance", "description": "프롬프트에서 요구한 형식/제약 조건 이행 여부"},
    {"name": "korean_quality", "description": "자연스러운 한국어 표현, 어색한 번역체 여부"},
    {"name": "hallucination", "description": "입력에 없는 정보 생성, 사실 왜곡 여부 (낮을수록 좋음 → 점수 반전)"},
    {"name": "token_efficiency", "description": "불필요한 반복/장황함 없이 핵심을 전달하는가"},
]

# 에이전트별 전문 평가 항목
AGENT_CRITERIA: dict[str, list[dict[str, str]]] = {
    "intent_classifier": [
        {"name": "intent_accuracy", "description": "입력 발화에 대한 intent 분류가 적절한가"},
        {"name": "mode_detection", "description": "conversation/podcast 모드 판별이 맞는가"},
        {"name": "complexity_score_rationality", "description": "입력 복잡도를 적절히 반영하는가"},
        {"name": "risk_flag_sensitivity", "description": "1차 위기 감지가 과민/둔감하지 않은가"},
        {"name": "execution_plan_quality", "description": "후속 TIER에 전달할 실행 계획이 합리적인가"},
    ],
    "safety": [
        {"name": "crisis_detection_accuracy", "description": "위험 수준(safe/warning/crisis) 판정이 입력에 부합하는가"},
        {"name": "risk_level_granularity", "description": "0~4 레벨이 미세한 뉘앙스를 잘 구분하는가"},
        {"name": "risk_score_precision", "description": "0.0~1.0 점수가 위험도를 정량적으로 잘 반영하는가"},
        {"name": "false_positive_control", "description": "안전한 입력을 위험하다고 오판하지 않는가"},
        {"name": "false_negative_control", "description": "위험한 입력을 안전하다고 놓치지 않는가"},
        {"name": "reasoning_provided", "description": "판정 이유를 명확히 설명하는가"},
    ],
    "emotion": [
        {"name": "emotion_identification", "description": "입력에서 드러나는 감정을 정확히 포착하는가"},
        {"name": "vector_diversity", "description": "단일 감정이 아닌 복합 감정을 포착하는가"},
        {"name": "intensity_rationality", "description": "감정 강도(intensity)가 맥락에 비례하는가"},
        {"name": "subtle_emotion_detection", "description": "직접 표현되지 않은 내재된 감정을 읽어내는가"},
        {"name": "emotion_relationships", "description": "복합 감정 간 상호 관계(예: 분노 뒤의 슬픔)를 파악하는가"},
        {"name": "cultural_context", "description": "한국 문화권 감정 표현의 뉘앙스를 이해하는가"},
    ],
    "content_analyzer": [
        {"name": "topic_extraction", "description": "핵심 주제와 부수 주제를 빠짐없이 식별하는가"},
        {"name": "structuring_quality", "description": "추출된 분석이 논리적으로 잘 정리되어 있는가"},
        {"name": "analysis_depth", "description": "표면적 요약이 아닌 심층 분석을 제공하는가"},
        {"name": "podcast_suitability", "description": "분석 결과가 팟캐스트 에피소드 생성에 활용 가능한가"},
        {"name": "key_quote_extraction", "description": "사용자 발화에서 핵심 표현을 정확히 포착하는가"},
        {"name": "emotional_journey", "description": "감정 흐름 구성이 자연스럽고 풍부한가"},
    ],
    "podcast_reasoning": [
        {"name": "reasoning_depth", "description": "단순 요약이 아닌 다단계 추론을 수행하는가"},
        {"name": "logical_consistency", "description": "추론 과정에 모순이나 비약이 없는가"},
        {"name": "strategy_appropriateness", "description": "GoT/ToT/CoT 전략 선택이 입력 복잡도에 맞는가"},
        {"name": "agent_call_judgment", "description": "Memory/Knowledge 호출 필요성 판단이 적절한가"},
        {"name": "multi_perspective", "description": "하나의 해석에 고착되지 않고 복수 관점을 탐색하는가"},
        {"name": "actionable_insight", "description": "추론 결과가 스크립트 생성에 실질적으로 활용 가능한가"},
    ],
    "script_generator": [
        {"name": "script_structure", "description": "인트로/본문/클로징 등 구조가 갖춰져 있는가"},
        {"name": "narrative_flow", "description": "대본이 자연스럽게 읽히고 흐름이 매끄러운가"},
        {"name": "tier1_reflection", "description": "Safety/Emotion/Content/Reasoning 결과가 스크립트에 반영되는가"},
        {"name": "safety_warning_integration", "description": "Safety warning이 스크립트에 적절히 포함되는가"},
        {"name": "listener_engagement", "description": "팟캐스트로서 듣고 싶은 매력이 있는가"},
        {"name": "length_appropriateness", "description": "너무 짧거나 장황하지 않은 적정 분량인가"},
    ],
    "batch_validator": [
        {"name": "bv_score", "description": "산출된 품질 점수 (기존 핵심 지표)"},
        {"name": "validation_precision", "description": "실제 문제를 정확히 짚어내는가"},
        {"name": "feedback_specificity", "description": "부족함 수준이 아닌 구체적 개선점을 제시하는가"},
        {"name": "feedback_actionability", "description": "제시된 피드백으로 실제 개선이 가능한가"},
        {"name": "scoring_consistency", "description": "동일 품질의 입력에 대해 유사한 점수를 부여하는가"},
        {"name": "strictness_balance", "description": "너무 관대하거나 가혹하지 않은 적정 수준인가"},
    ],
    "script_personalizer": [
        {"name": "tone_appropriateness", "description": "사용자 감정 상태에 맞는 톤으로 조정되었는가"},
        {"name": "personalization_level", "description": "일반적 응답이 아닌 사용자 맥락이 반영된 조정인가"},
        {"name": "safety_tone_enforcement", "description": "warning 시 톤이 적절히 강화되었는가"},
        {"name": "original_preservation", "description": "개인화 과정에서 핵심 내용이 손실되지 않았는가"},
        {"name": "empathy_expression", "description": "사용자 상황에 대한 공감이 자연스럽게 드러나는가"},
        {"name": "consistent_persona", "description": "전체 스크립트에서 일관된 화자 톤이 유지되는가"},
    ],
    "visualization": [
        {"name": "visual_metadata_quality", "description": "색상/구도/분위기 등 메타데이터가 풍부한가"},
        {"name": "image_prompt_quality", "description": "생성된 프롬프트가 감정 상태를 잘 표현하는가"},
        {"name": "emotion_visual_mapping", "description": "감정 벡터와 시각적 표현이 일치하는가"},
        {"name": "creativity", "description": "진부하지 않은 독창적 시각 표현을 제안하는가"},
        {"name": "feasibility", "description": "이미지 생성 모델이 실제로 렌더링 가능한 프롬프트인가"},
    ],
    "learning": [
        {"name": "insight_usefulness", "description": "추출된 학습 인사이트가 향후 대화에 활용 가능한가"},
        {"name": "pattern_extraction", "description": "사용자 행동/감정 패턴을 정확히 식별하는가"},
        {"name": "overfitting_prevention", "description": "단일 대화에서 과도한 일반화를 하지 않는가"},
        {"name": "privacy_respect", "description": "민감 정보를 부적절하게 기록하지 않는가"},
        {"name": "data_structuring", "description": "학습 결과가 잘 구조화되어 검색 가능한가"},
    ],
}

# 에이전트 이름 → AgentState 출력 필드 매핑
AGENT_OUTPUT_FIELDS: dict[str, list[str]] = {
    "intent_classifier": ["intent", "risk_level", "risk_score", "safety_flags"],
    "safety": ["safety_flags", "risk_level", "risk_score"],
    "emotion": ["emotion_vectors"],
    "content_analyzer": ["content_analysis"],
    "podcast_reasoning": ["reasoning_result", "memory_results", "knowledge_results"],
    "script_generator": ["script_draft"],
    "batch_validator": ["validation_result"],
    "script_personalizer": ["final_output"],
    "visualization": ["visual_data"],
    "learning": [],
}

# 테스트 대상 Bedrock 모델 목록
BEDROCK_MODELS: list[dict[str, str]] = [
    {"short": "c3-sonnet", "model_id": "apac.anthropic.claude-3-sonnet-20240229-v1:0"},
    {"short": "c3-haiku", "model_id": "anthropic.claude-3-haiku-20240307-v1:0"},
    {"short": "c35-sonnet-v1", "model_id": "apac.anthropic.claude-3-5-sonnet-20240620-v1:0"},
    {"short": "c35-sonnet-v2", "model_id": "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"},
    {"short": "c37-sonnet", "model_id": "apac.anthropic.claude-3-7-sonnet-20250219-v1:0"},
]

# 이미지 생성 모델 (Visualization 전용)
IMAGE_MODELS: list[dict[str, str]] = [
    {"short": "titan-v2", "model_id": "amazon.titan-image-generator-v2:0"},
    {"short": "titan-v1", "model_id": "amazon.titan-image-generator-v1"},
    {"short": "nova-canvas", "model_id": "amazon.nova-canvas-v1:0"},
]

# 에이전트별 기본 모델 키 (settings.yaml 기준)
AGENT_DEFAULT_MODEL: dict[str, str] = {
    "intent_classifier": "haiku",
    "safety": "sonnet",
    "emotion": "sonnet",
    "content_analyzer": "sonnet",
    "podcast_reasoning": "sonnet",
    "script_generator": "sonnet",
    "batch_validator": "sonnet",
    "script_personalizer": "sonnet",
    "visualization": "sonnet",
    "learning": "haiku",
}

# Evaluator Agent 고정 모델
EVALUATOR_MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"

# 종합점수 기본 가중치
DEFAULT_WEIGHTS: dict[str, float] = {
    "quality": 0.35,
    "consistency": 0.25,
    "speed": 0.15,
    "cost_efficiency": 0.10,
    "reliability": 0.15,
}
```

- [ ] **Step 2: 커밋**

```bash
git add dev/live_tests/evaluator_criteria.py
git commit -m "feat: Bedrock 모델 테스트 — 에이전트별 평가 기준 정의 (evaluator_criteria.py)"
```

---

## Task 2: evaluator_agent.py — Evaluator Agent 구현

**Files:**
- Create: `dev/live_tests/evaluator_agent.py`
- Read: `src/agents/shared/llm_client.py` (LLMClient 인터페이스 확인)
- Read: `dev/live_tests/evaluator_criteria.py` (Task 1에서 생성)

Evaluator Agent는 파이프라인 실행 결과에서 교체된 에이전트의 출력을 추출하고, Claude 3.5 Sonnet v2로 채점한다. BaseAgent를 상속하지 않고 독립 모듈로 구현한다 (향후 파이프라인 편입 시 전환).

- [ ] **Step 1: EvaluatorAgent 클래스 구현**

```python
"""Bedrock 모델 최적화 테스트 — Evaluator Agent.

파이프라인 실행 후 교체된 에이전트의 출력을 독립적으로 평가하는 채점 에이전트.
고정 모델(Claude 3.5 Sonnet v2)로 항목별 점수(0~1) + 한 줄 근거를 반환한다.

설계: docs/superpowers/specs/2026-03-30-bedrock-model-optimization-design.md 섹션 4
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.shared.llm_client import LLMClient

from .evaluator_criteria import (
    AGENT_OUTPUT_FIELDS,
    COMMON_CRITERIA,
    AGENT_CRITERIA,
    EVALUATOR_MODEL_ID,
)

logger = logging.getLogger(__name__)


def _build_evaluation_prompt(
    agent_name: str,
    agent_output: dict[str, Any],
    user_input: str,
    criteria: list[dict[str, str]],
) -> str:
    """Evaluator용 시스템 프롬프트를 생성한다."""
    criteria_text = "\n".join(
        f"- {c['name']}: {c['description']}" for c in criteria
    )
    return f"""당신은 AI 에이전트 출력 품질 평가자입니다.

## 평가 대상
- 에이전트: {agent_name}
- 사용자 입력: {user_input}

## 에이전트 출력
```json
{json.dumps(agent_output, ensure_ascii=False, indent=2, default=str)[:8000]}
```

## 평가 기준
{criteria_text}

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요. 각 항목에 대해 0.0~1.0 점수와 한 줄 근거를 제공합니다.

```json
{{
  "scores": {{
    "<항목_name>": {{"score": 0.85, "reason": "한 줄 근거"}}
  }},
  "total_score": 0.85,
  "summary": "전체 평가 요약 (1~2문장)"
}}
```
"""


def _extract_agent_output(
    agent_name: str,
    pipeline_state: dict[str, Any],
) -> dict[str, Any]:
    """파이프라인 최종 상태에서 대상 에이전트의 출력 필드만 추출한다."""
    fields = AGENT_OUTPUT_FIELDS.get(agent_name, [])
    output = {}
    for field in fields:
        value = pipeline_state.get(field)
        if value is not None:
            output[field] = value
    return output


async def evaluate(
    agent_name: str,
    pipeline_state: dict[str, Any],
    user_input: str,
) -> dict[str, Any]:
    """교체된 에이전트의 출력을 채점한다.

    Args:
        agent_name: 평가 대상 에이전트 이름
        pipeline_state: ainvoke() 반환 상태 (전체)
        user_input: 원본 사용자 입력

    Returns:
        {"common": {...}, "specialized": {...}, "total_score": float, "summary": str}
    """
    agent_output = _extract_agent_output(agent_name, pipeline_state)

    if not agent_output and agent_name != "learning":
        return {
            "common": {},
            "specialized": {},
            "total_score": 0.0,
            "summary": f"{agent_name} 출력이 비어있음 — 채점 불가",
            "error": "empty_output",
        }

    # 공통 + 전문 평가 항목
    specialized = AGENT_CRITERIA.get(agent_name, [])
    all_criteria = COMMON_CRITERIA + specialized

    # LLM 채점 (고정 모델)
    client = LLMClient(agent_name="evaluator", model_override=EVALUATOR_MODEL_ID)
    prompt = _build_evaluation_prompt(agent_name, agent_output, user_input, all_criteria)

    try:
        response_text = await client.generate(
            system_prompt=prompt,
            user_message="위 에이전트 출력을 평가 기준에 따라 채점해주세요.",
            max_tokens=2048,
            temperature=0.1,
        )

        # JSON 파싱 (코드 블록 내 JSON 추출)
        json_text = response_text
        if "```json" in response_text:
            json_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_text = response_text.split("```")[1].split("```")[0]

        result = json.loads(json_text.strip())
        scores = result.get("scores", {})

        # 공통/전문 분리
        common_names = {c["name"] for c in COMMON_CRITERIA}
        common_scores = {k: v for k, v in scores.items() if k in common_names}
        specialized_scores = {k: v for k, v in scores.items() if k not in common_names}

        return {
            "common": common_scores,
            "specialized": specialized_scores,
            "total_score": result.get("total_score", 0.0),
            "summary": result.get("summary", ""),
            "token_usage": client.total_usage,
        }

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("Evaluator 응답 파싱 실패: %s", e)
        return {
            "common": {},
            "specialized": {},
            "total_score": 0.0,
            "summary": f"Evaluator 응답 파싱 실패: {e}",
            "error": "parse_error",
            "raw_response": response_text[:2000] if "response_text" in dir() else "",
        }
    except Exception as e:
        logger.error("Evaluator 호출 실패: %s", e)
        return {
            "common": {},
            "specialized": {},
            "total_score": 0.0,
            "summary": f"Evaluator 호출 실패: {e}",
            "error": str(type(e).__name__),
        }
```

- [ ] **Step 2: 커밋**

```bash
git add dev/live_tests/evaluator_agent.py
git commit -m "feat: Bedrock 모델 테스트 — Evaluator Agent 구현 (evaluator_agent.py)"
```

---

## Task 3: run_single_bedrock_test.py — 단일 테스트 워커

**Files:**
- Create: `dev/live_tests/run_single_bedrock_test.py`
- Read: `dev/live_tests/conftest_live.py` (Timer, setup_provider)
- Read: `dev/live_tests/fixtures.py` (make_e2e_state)
- Read: `dev/live_tests/evaluator_agent.py` (Task 2에서 생성)

subprocess로 호출되는 독립 프로세스. 1회의 E2E 파이프라인 + Evaluator 채점을 수행하고 결과 JSON을 저장한다.

- [ ] **Step 1: CLI 파서 + 메인 로직 구현**

```python
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
        from dev.live_tests.evaluator_criteria import EVALUATOR_MODEL_ID
        # evaluator_criteria 모듈의 상수는 변경 불가이므로 환경변수로 전달
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
```

- [ ] **Step 2: 커밋**

```bash
git add dev/live_tests/run_single_bedrock_test.py
git commit -m "feat: Bedrock 모델 테스트 — 단일 테스트 워커 구현 (run_single_bedrock_test.py)"
```

---

## Task 4: run_bedrock_model_test.py — 오케스트레이터

**Files:**
- Create: `dev/live_tests/run_bedrock_model_test.py`
- Read: `dev/live_tests/evaluator_criteria.py` (모델 목록, 에이전트 목록)
- Read: `dev/live_tests/conftest_live.py` (setup_provider, check_provider_health)

Phase 관리, 서브프로세스 스케줄링, 진행 상황 추적, 캘리브레이션을 담당한다.

- [ ] **Step 1: CLI + Phase 라우팅 + 캘리브레이션 구현**

```python
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
    python -m dev.live_tests.run_bedrock_model_test --phase 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
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

    print(f"\n  Phase 0 완료 → {phase0_dir}")


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
        for p in tasks:
            try:
                _, stderr = await asyncio.wait_for(p.communicate(), timeout=PROCESS_TIMEOUT)
                results.append({"returncode": p.returncode, "stderr": stderr.decode()[:200]})
            except asyncio.TimeoutError:
                p.kill()
                results.append({"returncode": -1, "stderr": "timeout"})

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
            print(f"    동시 {n}프로세스 불안정 — max_concurrent = {n - 1}로 결정")
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
    print(f"\n  캘리브레이션 완료 → max_concurrent = {max_concurrent}")
    print(f"  저장: {CALIBRATION_FILE}")

    return cal


# --- Phase 1: 벤치마크 ---

async def run_phase1(
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    agent_filter: str | None = None,
    retry_failed: bool = False,
) -> None:
    """에이전트별 모델 벤치마크를 실행한다."""
    from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, AGENT_OUTPUT_FIELDS

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
        skip_viz = "true" if agent_name != "visualization" else "false"
        models = BEDROCK_MODELS

        print(f"\n▶ {agent_name} ({len(models)} 모델 x {RUNS_PER_MODEL} 회)")

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
            print(f"  (모든 테스트 완료됨, 건너뜀)")
            continue

        print(f"  실행할 테스트: {len(tasks)}회")

        async def _run_one(task: dict[str, str]) -> dict[str, Any]:
            async with semaphore:
                # 메모리 확인
                mem = _get_memory_mb()
                if mem["available_mb"] < 500 and mem["available_mb"] > 0:
                    print(f"  ⚠ 메모리 부족 ({mem['available_mb']}MB), 30초 대기...")
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
        print(f"  ✓ {agent_name}: {successes}/{len(results)} 성공 (실패: {failures})")

    progress["phase"] = "phase1_complete"
    _save_progress(progress)
    print(f"\n  Phase 1 완료 → {phase1_dir}")


# --- Phase 3: 최적 조합 검증 ---

async def run_phase3(optimal_config_path: str | None = None) -> None:
    """최적 조합 + Baseline을 각 5회씩 실행한다."""
    print("\n" + "=" * 60)
    print("Phase 3: 최적 파이프라인 검증")
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

    print(f"  최적 조합: {json.dumps(optimal, indent=2, ensure_ascii=False)[:200]}")
    print("  Phase 3 구현은 Phase 2 결과에 의존합니다.")


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
        await run_phase3(optimal_config_path=args.optimal_config)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 커밋**

```bash
git add dev/live_tests/run_bedrock_model_test.py
git commit -m "feat: Bedrock 모델 테스트 — 오케스트레이터 구현 (run_bedrock_model_test.py)"
```

---

## Task 5: scoring.py — 종합점수 산출 (로컬)

**Files:**
- Create: `dev/live_tests/scoring.py`

표준 라이브러리(json, statistics, pathlib)만 사용. 결과 JSON을 읽어 에이전트별 종합점수를 산출한다.

- [ ] **Step 1: 종합점수 산출 로직 구현**

```python
"""Bedrock 모델 최적화 테스트 — 종합점수 산출.

Phase 1 결과 JSON을 읽어 에이전트별 (모델 x 지표) 매트릭스를 구성하고,
가중 종합점수를 산출한다.

로컬에서 실행 — 표준 라이브러리만 사용 (json, statistics, pathlib).

사용법:
    python -m dev.live_tests.scoring \\
        --input dev/live_tests/results/bedrock_model_test/ \\
        --output dev/live_tests/results/bedrock_model_test/summary/
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


DEFAULT_WEIGHTS = {
    "quality": 0.35,
    "consistency": 0.25,
    "speed": 0.15,
    "cost_efficiency": 0.10,
    "reliability": 0.15,
}


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
```

- [ ] **Step 2: 커밋**

```bash
git add dev/live_tests/scoring.py
git commit -m "feat: Bedrock 모델 테스트 — 종합점수 산출 구현 (scoring.py)"
```

---

## 최종 검증

- [ ] **Step 1: 전체 파일 존재 확인**

```bash
ls -la dev/live_tests/evaluator_criteria.py
ls -la dev/live_tests/evaluator_agent.py
ls -la dev/live_tests/run_single_bedrock_test.py
ls -la dev/live_tests/run_bedrock_model_test.py
ls -la dev/live_tests/scoring.py
```

- [ ] **Step 2: import 검증 (로컬)**

```bash
python -c "from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, AGENT_CRITERIA; print(f'모델: {len(BEDROCK_MODELS)}, 에이전트: {len(AGENT_CRITERIA)}')"
python -c "from dev.live_tests.evaluator_agent import evaluate; print('evaluator_agent OK')"
python -c "from dev.live_tests.run_single_bedrock_test import create_parser; print('single_test OK')"
python -c "from dev.live_tests.run_bedrock_model_test import create_parser; print('orchestrator OK')"
python -c "from dev.live_tests.scoring import load_phase1_results; print('scoring OK')"
```

- [ ] **Step 3: CLI 도움말 확인**

```bash
python -m dev.live_tests.run_single_bedrock_test --help
python -m dev.live_tests.run_bedrock_model_test --help
python -m dev.live_tests.scoring --help
```

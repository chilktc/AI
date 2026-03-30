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

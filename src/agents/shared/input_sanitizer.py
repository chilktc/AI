"""사용자 입력의 프롬프트 인젝션 패턴을 감지한다.

라우트 레벨에서 그래프 실행 전에 호출하여, 감지 시 safety_flags에 표시한다.
입력 자체를 차단하지 않고 Safety Agent가 최종 판단한다.
"""

from __future__ import annotations

import re

# 인젝션 패턴 목록 — 새 패턴 추가 시 이 리스트에 항목 추가
INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?previous",  # "ignore previous instructions"
    r"(?:system|assistant)\s*:",  # 역할 탈출 시도
    r"\[INST\]",  # Llama 형식 인젝션
    r"<\|im_start\|>",  # ChatML 형식 인젝션
    r"(?:you\s+are|act\s+as)\s+(?:now|a)",  # 역할 재정의
    r"(?:print|reveal|show)\s+(?:your|the)\s+(?:system|prompt|instructions)",  # 프롬프트 유출
]

_COMPILED: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> bool:
    """인젝션 패턴 감지 시 True를 반환한다.

    Args:
        text: 사용자 입력 텍스트

    Returns:
        패턴이 하나라도 매칭되면 True
    """
    return any(pat.search(text) for pat in _COMPILED)

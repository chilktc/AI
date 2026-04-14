"""사용자 입력의 프롬프트 인젝션 패턴을 감지한다.

라우트 레벨에서 그래프 실행 전에 호출하여, 감지 시 safety_flags에 표시한다.
입력 자체를 차단하지 않고 Safety Agent가 최종 판단한다.
"""

from __future__ import annotations

import re

# 인젝션 패턴 목록 — 새 패턴 추가 시 이 리스트에 항목 추가
INJECTION_PATTERNS: list[str] = [
    # ── 영어 패턴 ──────────────────────────────────────────────────────────
    r"ignore\s+(all\s+)?previous",  # "ignore previous instructions"
    r"(?:system|assistant)\s*:",  # 역할 탈출 시도
    r"\[INST\]",  # Llama 형식 인젝션
    r"<\|im_start\|>",  # ChatML 형식 인젝션
    r"(?:you\s+are|act\s+as)\s+(?:now|a)",  # 역할 재정의
    r"(?:print|reveal|show)\s+(?:your|the)\s+(?:system|prompt|instructions)",  # 프롬프트 유출
    # ── 한국어 패턴 ────────────────────────────────────────────────────────
    # 주의: 일상 감정 표현("무시해줘", "알려줘")과 구분하기 위해 인젝션 전형 어구와
    # 함께 나타날 때만 감지한다. 단독 동사는 False Positive 위험이 크다.
    r"이전\s*(?:지시|명령|설정|규칙)을?\s*무시",  # "이전 지시를 무시해" 패턴
    r"(?:시스템|어시스턴트)\s*프롬프트를?\s*(?:보여|알려|출력)",  # 프롬프트 유출 요청
    r"지금부터\s*(?:너는|당신은|you\s*are)\s*\S+(?:야|이야|입니다|다)",  # 역할 재정의
    r"(?:프롬프트|지시문|시스템\s*메시지)를?\s*(?:무시|우회|변경|수정)해",  # 프롬프트 조작
    r"(?:역할|persona)을?\s*(?:바꿔|변경해|전환해)",  # 역할 전환 요청
    r"(?:탈옥|jailbreak|감옥\s*탈출)\s*(?:해|시켜|모드)",  # 탈옥 시도 명시
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

"""LLM 출력에서 PII(개인식별정보) 패턴을 감지하고 마스킹한다.

[보안 담당자 참고]
이 모듈은 AI팀이 초기 구현한 최소 PII 정제 레이어입니다.
패턴 추가/수정, 마스킹 정책 변경, 외부 라이브러리(Microsoft Presidio 등) 전환은
보안 담당자가 검토 후 진행해 주세요.

주요 설계 결정:
1. 정규식 기반 — 외부 의존성 없이 배포 가능 (Presidio 전환 시 이 파일만 교체)
2. 감지만 하고 차단하지 않음 — 마스킹 후 정상 처리 (서비스 가용성 우선)
3. 로깅 — 감지된 PII 타입을 로그에 기록 (원본 데이터는 기록하지 않음)
4. 설정 기반 — settings.yaml에서 활성화/비활성화 가능

적용 위치:
- src/api/routes/podcasts.py — DB 저장 전 final_output 정제

한계:
- 이름/주소 등 자연어 PII는 정규식으로 감지 불가 (NER 모델 필요)
- 정규식 오탐(false positive) 가능 — 예: 12자리 일반 숫자가 주민번호로 인식
- 한국어 특화 패턴만 포함 — 다국어 지원 시 패턴 확장 필요
"""

from __future__ import annotations

import re
from typing import Any

from src.utils.logger import get_agent_logger

logger = get_agent_logger("output_sanitizer")

# ============================================================
# PII 패턴 정의
# ============================================================
# [보안 담당자 참고] 패턴 추가/수정 시 이 리스트만 변경하면 됩니다.
# 각 항목: (패턴_이름, 컴파일된_정규식, 마스킹_텍스트, 설명)
#
# 패턴 우선순위: 리스트 순서대로 적용됨.
# 주민번호(13자리)를 먼저 매칭해야 전화번호(11자리)와 겹치지 않습니다.
# ============================================================

_PII_PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
    # --- 한국 주민등록번호 (Resident Registration Number) ---
    # 형식: YYMMDD-GNNNNNN (G=성별: 1~4, 외국인: 5~8)
    # 예시: 900101-1234567, 9001011234567
    # [주의] 13자리 숫자 조합이므로 오탐 가능성 있음
    (
        "rrn_kr",
        re.compile(
            r"\b(\d{2})"  # 출생년도 2자리
            r"(0[1-9]|1[0-2])"  # 월 (01-12)
            r"(0[1-9]|[12]\d|3[01])"  # 일 (01-31)
            r"-?"  # 하이픈 선택
            r"([1-8])"  # 성별/세기 구분 (1-4: 내국인, 5-8: 외국인)
            r"(\d{6})"  # 나머지 6자리
            r"\b"
        ),
        "[주민번호_마스킹]",
        "한국 주민등록번호 (13자리, 하이픈 포함/미포함)",
    ),
    # --- 한국 휴대전화 번호 ---
    # 형식: 01X-XXXX-XXXX 또는 01XXXXXXXXX
    # 유효 접두사: 010, 011, 016, 017, 018, 019
    # \b 대신 (?<!\d)/(?!\d) 사용 — 한국어(유니코드 \w)와 \b 충돌 방지
    (
        "phone_kr_mobile",
        re.compile(
            r"(?<!\d)(01[016789])"  # 통신사 접두사 (앞에 숫자 없음)
            r"-?"  # 하이픈 선택
            r"(\d{3,4})"  # 중간 3-4자리
            r"-?"  # 하이픈 선택
            r"(\d{4})"  # 마지막 4자리
            r"(?!\d)"  # 뒤에 숫자 없음
        ),
        "[휴대전화_마스킹]",
        "한국 휴대전화 번호 (010-1234-5678 등)",
    ),
    # --- 한국 유선전화 번호 ---
    # 형식: 0XX-XXXX-XXXX (지역번호 2-3자리)
    # [주의] 010 등 휴대전화와 겹치지 않도록 위에서 먼저 매칭
    (
        "phone_kr_landline",
        re.compile(
            r"\b(0[2-6]\d?)"  # 지역번호 (02, 031, 051 등)
            r"-"  # 하이픈 필수 (오탐 방지)
            r"(\d{3,4})"  # 중간 3-4자리
            r"-"  # 하이픈 필수
            r"(\d{4})"  # 마지막 4자리
            r"\b"
        ),
        "[유선전화_마스킹]",
        "한국 유선전화 번호 (02-1234-5678, 031-123-4567 등)",
    ),
    # --- 이메일 주소 ---
    # RFC 5322 간소화 버전
    # (?<!\S)/(?!\S) 대신 전체 패턴으로 충분히 구분됨 (@가 핵심 앵커)
    (
        "email",
        re.compile(
            r"[a-zA-Z0-9._%+\-]+"  # 로컬 파트
            r"@"
            r"[a-zA-Z0-9.\-]+"  # 도메인
            r"\.[a-zA-Z]{2,}"  # TLD
        ),
        "[이메일_마스킹]",
        "이메일 주소",
    ),
    # --- 신용카드 번호 ---
    # 형식: 16자리 (4-4-4-4, 하이픈/공백 구분)
    # [주의] 16자리 숫자 조합 오탐 가능
    (
        "card_number",
        re.compile(
            r"\b(\d{4})"  # 첫 4자리
            r"[-\s]"  # 구분자 필수 (오탐 방지)
            r"(\d{4})"  # 둘째 4자리
            r"[-\s]"
            r"(\d{4})"  # 셋째 4자리
            r"[-\s]"
            r"(\d{4})"  # 넷째 4자리
            r"\b"
        ),
        "[카드번호_마스킹]",
        "신용카드/체크카드 번호 (16자리, 구분자 포함)",
    ),
]

# 컴파일 검증 — 모듈 로드 시 패턴 문법 오류를 즉시 발견
assert all(isinstance(p[1], re.Pattern) for p in _PII_PATTERNS), "PII 패턴 컴파일 오류"


def sanitize_output(text: str) -> tuple[str, list[str]]:
    """LLM 출력 텍스트에서 PII를 감지하고 마스킹한다.

    [보안 담당자 참고]
    - 감지된 PII는 한국어 마스킹 텍스트로 대체됩니다 (예: [휴대전화_마스킹])
    - 원본 PII 값은 로그에 기록하지 않습니다 (감지된 타입명만 기록)
    - 마스킹 텍스트 형식을 변경하려면 _PII_PATTERNS의 3번째 요소를 수정하세요

    Args:
        text: LLM 출력 텍스트 (final_output 등)

    Returns:
        tuple: (마스킹된 텍스트, 감지된 PII 타입 이름 리스트)
               PII가 없으면 (원본 텍스트, []) 반환

    Examples:
        >>> sanitize_output("연락처는 010-1234-5678입니다")
        ("연락처는 [휴대전화_마스킹]입니다", ["phone_kr_mobile"])
    """
    if not text:
        return text, []

    detected: list[str] = []
    result = text

    for name, pattern, mask_text, _description in _PII_PATTERNS:
        if pattern.search(result):
            detected.append(name)
            result = pattern.sub(mask_text, result)

    if detected:
        # [보안 로그] 감지된 PII 타입만 기록 — 원본 값은 절대 로그에 남기지 않음
        logger.warning(
            "[PII 정제] 감지된 패턴: %s (총 %d건)",
            detected,
            len(detected),
        )

    return result, detected


def sanitize_dict_values(data: dict, target_keys: list[str] | None = None) -> dict:
    """dict 내의 문자열 값들에서 PII를 정제한다.

    [보안 담당자 참고]
    JSON 파싱된 final_output(dict)의 특정 필드만 선택적으로 정제할 때 사용합니다.
    target_keys가 None이면 모든 문자열 값을 정제합니다.

    Args:
        data: 정제 대상 dict
        target_keys: 정제할 키 목록. None이면 모든 문자열 값 정제.

    Returns:
        정제된 dict (원본을 변경하지 않고 새 dict 반환)
    """
    sanitized: dict = {}

    for key, value in data.items():
        if isinstance(value, str):
            if target_keys is None or key in target_keys:
                clean, _ = sanitize_output(value)
                sanitized[key] = clean
            else:
                sanitized[key] = value
        elif isinstance(value, list):
            sanitized_list: list[Any] = []
            for item in value:
                if isinstance(item, str) and (target_keys is None or key in target_keys):
                    clean, _ = sanitize_output(item)
                    sanitized_list.append(clean)
                elif isinstance(item, dict):
                    sanitized_list.append(sanitize_dict_values(item, target_keys))
                else:
                    sanitized_list.append(item)
            sanitized[key] = sanitized_list
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_values(value, target_keys)
        else:
            sanitized[key] = value

    return sanitized


# ============================================================
# [보안 담당자 참고] 패턴 확장 가이드
# ============================================================
#
# 1. 새 패턴 추가:
#    _PII_PATTERNS 리스트에 튜플 추가:
#    ("패턴_이름", re.compile(r"정규식"), "[마스킹_텍스트]", "설명")
#
# 2. 패턴 우선순위:
#    리스트 순서대로 매칭됨. 긴 패턴(주민번호 13자리)을
#    짧은 패턴(전화번호 11자리)보다 먼저 배치할 것.
#
# 3. 외부 라이브러리 전환:
#    Microsoft Presidio 등 NER 기반 PII 감지로 전환 시
#    sanitize_output() 함수 내부만 교체하면 됨.
#    함수 시그니처(입력: str, 출력: tuple[str, list[str]])는 유지.
#
# 4. 테스트:
#    tests/agents/shared/test_output_sanitizer.py에 테스트 케이스 추가.
# ============================================================

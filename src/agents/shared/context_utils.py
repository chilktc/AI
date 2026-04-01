"""
에이전트 공용 컨텍스트 빌딩 유틸리티.

여러 에이전트에서 반복되는 dict→문자열 변환, 값 클램핑 패턴을 통합한다.
"""

from __future__ import annotations

from typing import Any


def build_section(label: str, data: dict[str, Any], keys: list[str] | None = None) -> str:
    """dict에서 지정된 키를 추출하여 레이블 섹션으로 포맷한다.

    Args:
        label: 섹션 라벨 (예: "감정 분석")
        data: 원본 dict
        keys: 추출할 키 목록. None이면 전체 키 사용.

    Returns:
        "[label]\n- key1: value1\n- key2: value2" 형태의 문자열.
        data가 비어있으면 빈 문자열 반환.
    """
    if not data:
        return ""
    selected_keys = keys if keys is not None else list(data.keys())
    lines = [f"[{label}]"]
    for k in selected_keys:
        v = data.get(k, "N/A")
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def build_context(*sections: str) -> str:
    """비어있지 않은 섹션들을 \\n\\n으로 결합한다."""
    return "\n\n".join(s for s in sections if s)


def format_dict_summary(data: dict[str, Any], max_depth: int = 1, max_str_len: int = 200) -> str:
    """dict를 사람이 읽을 수 있는 요약 문자열로 변환한다."""
    if not data:
        return "(빈 데이터)"
    parts = []
    for k, v in data.items():
        if isinstance(v, dict) and max_depth > 0:
            nested = format_dict_summary(v, max_depth - 1, max_str_len)
            parts.append(f"- {k}: {nested}")
        elif isinstance(v, str) and len(v) > max_str_len:
            parts.append(f"- {k}: {v[:max_str_len]}...")
        elif isinstance(v, list):
            parts.append(f"- {k}: [{len(v)}건]")
        else:
            parts.append(f"- {k}: {v}")
    return "\n".join(parts)


def clamp(value: Any, lo: float, hi: float, default: float = 0.0) -> float:
    """숫자 값을 [lo, hi] 범위 내로 제한한다. 변환 실패 시 default 반환."""
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default

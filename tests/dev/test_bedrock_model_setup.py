"""evaluator_criteria.py 모델 목록 검증 테스트."""
from __future__ import annotations

import pytest

from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS


def _shorts() -> list[str]:
    return [m["short"] for m in BEDROCK_MODELS]


def _model_ids() -> list[str]:
    return [m["model_id"] for m in BEDROCK_MODELS]


# === 제거 확인 ===

def test_c3_sonnet_removed() -> None:
    """Phase 1 전패 모델 c3-sonnet은 목록에 없어야 한다."""
    assert "c3-sonnet" not in _shorts()


def test_c35_sonnet_v1_removed() -> None:
    """v2 구버전 c35-sonnet-v1은 목록에 없어야 한다."""
    assert "c35-sonnet-v1" not in _shorts()


# === 신규 모델 확인 ===

def test_claude_sonnet_4_present() -> None:
    assert "claude-sonnet-4" in _shorts()


def test_nova_pro_present() -> None:
    assert "nova-pro" in _shorts()


def test_nova_lite_present() -> None:
    assert "nova-lite" in _shorts()


# === model_id 형식 확인 ===

def test_claude_sonnet_4_model_id() -> None:
    entry = next(m for m in BEDROCK_MODELS if m["short"] == "claude-sonnet-4")
    assert entry["model_id"] == "apac.anthropic.claude-sonnet-4-20250514-v1:0"


def test_nova_pro_model_id() -> None:
    entry = next(m for m in BEDROCK_MODELS if m["short"] == "nova-pro")
    assert entry["model_id"] == "apac.amazon.nova-pro-v1:0"


def test_nova_lite_model_id() -> None:
    entry = next(m for m in BEDROCK_MODELS if m["short"] == "nova-lite")
    assert entry["model_id"] == "apac.amazon.nova-lite-v1:0"


# === 기존 유지 모델 확인 ===

def test_existing_models_retained() -> None:
    for short in ("c3-haiku", "c35-sonnet-v2", "c37-sonnet"):
        assert short in _shorts(), f"{short} 누락"


# === 총 개수 확인 ===

def test_bedrock_models_count() -> None:
    """6종이어야 한다."""
    assert len(BEDROCK_MODELS) == 6


# === IMAGE_MODELS 변경 없음 확인 ===

def test_image_models_unchanged() -> None:
    shorts = [m["short"] for m in IMAGE_MODELS]
    assert set(shorts) == {"titan-v2", "titan-v1", "nova-canvas"}

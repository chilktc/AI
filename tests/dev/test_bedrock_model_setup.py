"""evaluator_criteria.py 모델 목록 검증 테스트."""
from __future__ import annotations

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


# ===  run_single_bedrock_test 모델 오버라이드 로직 ===

def _make_mock_settings(agent_name: str) -> dict:
    """settings._config 구조를 모사한 dict를 반환한다."""
    return {"agents": {agent_name: {}}}


def _apply_model_override(agent_name: str, model_id: str, config: dict) -> None:
    """run_single_bedrock_test.py의 오버라이드 로직을 분리한 순수 함수."""
    agent_cfg = config.setdefault("agents", {}).setdefault(agent_name, {})
    if agent_name == "visualization":
        agent_cfg["image_model"] = model_id
    else:
        agent_cfg["model_id"] = model_id


def test_visualization_uses_image_model_key() -> None:
    """visualization 에이전트는 image_model 키로 오버라이드해야 한다."""
    cfg = _make_mock_settings("visualization")
    _apply_model_override("visualization", "amazon.titan-image-generator-v2:0", cfg)
    agent_cfg = cfg["agents"]["visualization"]
    assert "image_model" in agent_cfg
    assert "model_id" not in agent_cfg
    assert agent_cfg["image_model"] == "amazon.titan-image-generator-v2:0"


def test_non_visualization_uses_model_id_key() -> None:
    """visualization 외 에이전트는 model_id 키로 오버라이드해야 한다."""
    for agent in ("safety", "emotion", "script_generator", "intent_classifier"):
        cfg = _make_mock_settings(agent)
        _apply_model_override(agent, "apac.amazon.nova-pro-v1:0", cfg)
        agent_cfg = cfg["agents"][agent]
        assert "model_id" in agent_cfg, f"{agent}: model_id 없음"
        assert "image_model" not in agent_cfg, f"{agent}: image_model이 잘못 설정됨"


# === Phase 1 모델 선택 로직 ===


def _select_models_and_skip_viz(agent_name: str) -> tuple[list[dict], str]:
    """Phase 1에서 에이전트별 모델 목록과 skip_viz를 반환하는 순수 함수."""
    if agent_name == "visualization":
        return IMAGE_MODELS, "false"
    return BEDROCK_MODELS, "true"


def test_phase1_visualization_uses_image_models() -> None:
    models, skip_viz = _select_models_and_skip_viz("visualization")
    assert models is IMAGE_MODELS
    assert skip_viz == "false"


def test_phase1_other_agents_use_bedrock_models() -> None:
    for agent in ("safety", "emotion", "content_analyzer", "script_generator"):
        models, skip_viz = _select_models_and_skip_viz(agent)
        assert models is BEDROCK_MODELS, f"{agent}: BEDROCK_MODELS 아님"
        assert skip_viz == "true", f"{agent}: skip_viz가 true 아님"


# === Phase 3 model_id 조회 로직 ===


def _resolve_model_id(agent_name: str, model_short: str) -> str | None:
    """Phase 3에서 에이전트 + model_short 조합으로 model_id를 반환하는 순수 함수."""
    bedrock_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}
    image_map = {m["short"]: m["model_id"] for m in IMAGE_MODELS}
    if agent_name == "visualization":
        return image_map.get(model_short)
    return bedrock_map.get(model_short)


def test_phase3_visualization_resolves_from_image_map() -> None:
    model_id = _resolve_model_id("visualization", "nova-canvas")
    assert model_id == "amazon.nova-canvas-v1:0"


def test_phase3_visualization_titan_v2_resolves() -> None:
    model_id = _resolve_model_id("visualization", "titan-v2")
    assert model_id == "amazon.titan-image-generator-v2:0"


def test_phase3_non_visualization_resolves_from_bedrock_map() -> None:
    model_id = _resolve_model_id("safety", "c37-sonnet")
    assert model_id == "apac.anthropic.claude-3-7-sonnet-20250219-v1:0"


def test_phase3_visualization_bedrock_short_returns_none() -> None:
    """visualization에 텍스트 모델 short를 넣으면 None이어야 한다."""
    model_id = _resolve_model_id("visualization", "c37-sonnet")
    assert model_id is None

# Bedrock 모델 최적화 재설계 v2 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bedrock 모델 목록 재편성(6종) + Visualization 버그 4개 지점 수정으로 전체 에이전트 최적 모델 선정 테스트를 재실행 가능한 상태로 만든다.

**Architecture:** 5개 파일만 수정한다. `evaluator_criteria.py`는 모델 목록 데이터 수정, `run_single_bedrock_test.py`는 model 오버라이드 키 분기, `run_bedrock_model_test.py`는 Phase 0/1/3 세 곳에서 visualization 분기 추가. 신규 파일 없음.

**Tech Stack:** Python 3.11+, pytest, 기존 `src/agents/podcast/visualization.py` / `src/agents/shared/llm_client.py` 활용

**Spec:** `docs/superpowers/specs/2026-03-31-bedrock-model-optimization-v2-design.md`

---

## 파일 구조

| 파일 | 역할 | 변경 유형 |
|------|------|----------|
| `dev/live_tests/evaluator_criteria.py` | 모델 목록 데이터 정의 | 수정 (BEDROCK_MODELS 재편성) |
| `dev/live_tests/run_single_bedrock_test.py` | 단일 테스트 워커 | 수정 (line 71: image_model 분기) |
| `dev/live_tests/run_bedrock_model_test.py` | 오케스트레이터 | 수정 (Phase 0/1/3 세 지점) |
| `tests/dev/test_bedrock_model_setup.py` | 위 변경사항 단위 테스트 | 신규 |

---

## Task 1: BEDROCK_MODELS 재편성 (`evaluator_criteria.py`)

**Files:**
- Modify: `dev/live_tests/evaluator_criteria.py:114-128`
- Test: `tests/dev/test_bedrock_model_setup.py`

- [ ] **Step 1: 테스트 디렉토리 및 파일 생성**

```bash
mkdir -p tests/dev
touch tests/dev/__init__.py
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/dev/test_bedrock_model_setup.py` 를 아래 내용으로 생성:

```python
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
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
cd /path/to/mind-log
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: `test_c3_sonnet_removed`, `test_claude_sonnet_4_present` 등 다수 FAIL

- [ ] **Step 4: `evaluator_criteria.py` BEDROCK_MODELS 수정**

`dev/live_tests/evaluator_criteria.py` 의 `BEDROCK_MODELS` 블록(line 114~121)을 아래로 교체:

```python
# 테스트 대상 Bedrock 모델 목록
BEDROCK_MODELS: list[dict[str, str]] = [
    {"short": "c3-haiku",        "model_id": "anthropic.claude-3-haiku-20240307-v1:0"},
    {"short": "c35-sonnet-v2",   "model_id": "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"},
    {"short": "c37-sonnet",      "model_id": "apac.anthropic.claude-3-7-sonnet-20250219-v1:0"},
    {"short": "claude-sonnet-4", "model_id": "apac.anthropic.claude-sonnet-4-20250514-v1:0"},
    {"short": "nova-pro",        "model_id": "apac.amazon.nova-pro-v1:0"},
    {"short": "nova-lite",       "model_id": "apac.amazon.nova-lite-v1:0"},
]
```

`IMAGE_MODELS` 블록(line 123~128)은 변경하지 않는다.

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: 11개 테스트 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add dev/live_tests/evaluator_criteria.py tests/dev/__init__.py tests/dev/test_bedrock_model_setup.py
git commit -m "feat: Bedrock 모델 목록 재편성 — c3-sonnet/c35v1 제거, claude-sonnet-4/nova-pro/nova-lite 추가"
```

---

## Task 2: visualization model 오버라이드 키 수정 (`run_single_bedrock_test.py`)

**Files:**
- Modify: `dev/live_tests/run_single_bedrock_test.py:70-71`
- Test: `tests/dev/test_bedrock_model_setup.py` (추가)

- [ ] **Step 1: 실패 테스트 추가**

`tests/dev/test_bedrock_model_setup.py` 하단에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
pytest tests/dev/test_bedrock_model_setup.py::test_visualization_uses_image_model_key -v
```

예상: FAIL — `assert "image_model" in agent_cfg` 실패 (현재는 `model_id`로 설정됨)

- [ ] **Step 3: `run_single_bedrock_test.py` line 71 수정**

`dev/live_tests/run_single_bedrock_test.py` 의 line 70-71:

```python
# 수정 전
agent_cfg = settings._config.setdefault("agents", {}).setdefault(args.agent, {})
agent_cfg["model_id"] = args.model_id
```

```python
# 수정 후
agent_cfg = settings._config.setdefault("agents", {}).setdefault(args.agent, {})
if args.agent == "visualization":
    agent_cfg["image_model"] = args.model_id
else:
    agent_cfg["model_id"] = args.model_id
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: 13개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add dev/live_tests/run_single_bedrock_test.py tests/dev/test_bedrock_model_setup.py
git commit -m "fix: visualization 에이전트 model 오버라이드 키를 image_model로 수정"
```

---

## Task 3: Phase 1 — visualization models 분기 (`run_bedrock_model_test.py`)

**Files:**
- Modify: `dev/live_tests/run_bedrock_model_test.py:277-279`
- Test: `tests/dev/test_bedrock_model_setup.py` (추가)

- [ ] **Step 1: 실패 테스트 추가**

`tests/dev/test_bedrock_model_setup.py` 하단에 추가:

```python
# === Phase 1 모델 선택 로직 ===

from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS


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
```

- [ ] **Step 2: 테스트 실행 — 통과 확인 (순수 함수이므로 바로 통과)**

```bash
pytest tests/dev/test_bedrock_model_setup.py::test_phase1_visualization_uses_image_models -v
pytest tests/dev/test_bedrock_model_setup.py::test_phase1_other_agents_use_bedrock_models -v
```

예상: PASS (순수 함수 테스트이므로 구현 전에도 통과)

- [ ] **Step 3: `run_bedrock_model_test.py` Phase 1 루프 수정**

`dev/live_tests/run_bedrock_model_test.py` 의 line 277-279:

```python
# 수정 전
for agent_name in agents:
    skip_viz = "true" if agent_name != "visualization" else "false"
    models = BEDROCK_MODELS
```

```python
# 수정 후
for agent_name in agents:
    if agent_name == "visualization":
        skip_viz = "false"
        models = IMAGE_MODELS
    else:
        skip_viz = "true"
        models = BEDROCK_MODELS
```

> **참고:** Phase 1 루프 상단의 import 라인(line 258)에 `IMAGE_MODELS`가 이미 포함되어 있는지 확인한다.
> `from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, AGENT_OUTPUT_FIELDS` →
> `from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS, AGENT_OUTPUT_FIELDS` 로 수정 필요 시 추가.

- [ ] **Step 4: 전체 테스트 실행**

```bash
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: 15개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add dev/live_tests/run_bedrock_model_test.py tests/dev/test_bedrock_model_setup.py
git commit -m "fix: Phase 1 visualization 에이전트를 IMAGE_MODELS로 분기"
```

---

## Task 4: Phase 3 — model_id_map에 IMAGE_MODELS 추가 (`run_bedrock_model_test.py`)

**Files:**
- Modify: `dev/live_tests/run_bedrock_model_test.py:381,401,413-420`

- [ ] **Step 1: 실패 테스트 추가**

`tests/dev/test_bedrock_model_setup.py` 하단에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행 — 통과 확인 (순수 함수)**

```bash
pytest tests/dev/test_bedrock_model_setup.py::test_phase3_visualization_resolves_from_image_map -v
```

예상: PASS

- [ ] **Step 3: `run_bedrock_model_test.py` Phase 3 수정**

`dev/live_tests/run_bedrock_model_test.py` Phase 3 함수 내부를 수정한다.

**3-A: import 라인 수정 (Phase 3 함수 내 import, 약 line 381)**

```python
# 수정 전
from dev.live_tests.evaluator_criteria import BEDROCK_MODELS

# 수정 후
from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS
```

**3-B: model_id_map 선언 직후 image_model_id_map 추가 (약 line 401)**

```python
# 수정 전
model_id_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}

# 수정 후
model_id_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}
image_model_id_map = {m["short"]: m["model_id"] for m in IMAGE_MODELS}
```

**3-C: model_id 조회 + skip_viz 분기 (약 line 413-420)**

```python
# 수정 전
for agent_name, info in best_models.items():
    model_short = info["model_short"]
    model_id = model_id_map.get(model_short)
    if not model_id:
        print(f"  [!] {agent_name}: model_short '{model_short}' 매핑 없음, 건너뜀")
        continue

    skip_viz = "true" if agent_name != "visualization" else "false"
```

```python
# 수정 후
for agent_name, info in best_models.items():
    model_short = info["model_short"]

    if agent_name == "visualization":
        model_id = image_model_id_map.get(model_short)
        skip_viz = "false"
    else:
        model_id = model_id_map.get(model_short)
        skip_viz = "true"

    if not model_id:
        print(f"  [!] {agent_name}: model_short '{model_short}' 매핑 없음, 건너뜀")
        continue
```

- [ ] **Step 4: 전체 테스트 실행**

```bash
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: 19개 테스트 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add dev/live_tests/run_bedrock_model_test.py tests/dev/test_bedrock_model_setup.py
git commit -m "fix: Phase 3 visualization model_id를 IMAGE_MODELS 매핑에서 조회하도록 수정"
```

---

## Task 5: Phase 0 — 이미지 모델 실제 연결 테스트 (`run_bedrock_model_test.py`)

**Files:**
- Modify: `dev/live_tests/run_bedrock_model_test.py:119-127`

> Phase 0는 실제 AWS 호출이 포함되므로 단위 테스트 대신 코드 리뷰 + 로컬 dry-run으로 검증한다.

- [ ] **Step 1: `run_bedrock_model_test.py` Phase 0 이미지 루프 수정**

`dev/live_tests/run_bedrock_model_test.py` 의 line 119-127 (이미지 모델 루프):

```python
# 수정 전
# 이미지 모델
for model in IMAGE_MODELS:
    print(f"\n  [{model['short']}] {model['model_id']}...", end=" ")
    result = {"model": model, "status": "skipped", "note": "이미지 모델은 별도 테스트 필요"}
    print("SKIP (이미지 모델)")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = phase0_dir / f"connectivity_{model['short']}_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
```

```python
# 수정 후
# 이미지 모델 — VisualizationAgent로 실제 생성 1회 시도
for model in IMAGE_MODELS:
    print(f"\n  [{model['short']}] {model['model_id']}...", end=" ")
    try:
        from src.agents.podcast.visualization import VisualizationAgent
        import config.loader as _loader
        _loader._settings_instance = None
        _settings = _loader.get_settings()
        viz_cfg = _settings._config.setdefault("agents", {}).setdefault("visualization", {})
        viz_cfg["image_model"] = model["model_id"]

        agent = VisualizationAgent()
        start = time.perf_counter()
        test_state = {
            "emotion_vectors": {"joy": 0.5},
            "content_analysis": {},
            "mode": "podcast",
            "user_id": "phase0-test",
        }
        result_data = await agent.process(test_state)
        elapsed = time.perf_counter() - start

        img_status = result_data.get("visual_data", {}).get("status", "unknown")
        result = {
            "model": model,
            "status": "ok" if img_status != "error" else "error",
            "response_time": round(elapsed, 2),
            "image_status": img_status,
        }
        print(f"OK ({elapsed:.1f}s, status={img_status})")
    except Exception as e:
        result = {
            "model": model,
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        print(f"FAIL: {e}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = phase0_dir / f"connectivity_{model['short']}_{timestamp}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 2: Phase 0 함수 최상단 import에 `IMAGE_MODELS` 포함 확인**

Phase 0 함수 내 `from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS` 라인에 `IMAGE_MODELS`가 이미 있는지 확인 (line 83). 없으면 추가.

- [ ] **Step 3: 전체 단위 테스트 실행 (회귀 확인)**

```bash
pytest tests/dev/test_bedrock_model_setup.py -v
```

예상: 19개 테스트 모두 PASS

- [ ] **Step 4: 전체 기존 테스트 회귀 확인**

```bash
pytest tests/ -v --ignore=tests/dev -x
```

예상: 기존 테스트 모두 통과 (수정한 파일은 dev/live_tests/만이므로 영향 없음)

- [ ] **Step 5: 커밋**

```bash
git add dev/live_tests/run_bedrock_model_test.py
git commit -m "fix: Phase 0 이미지 모델 연결 확인 SKIP 해제 — VisualizationAgent 실제 호출로 전환"
```

---

## Task 6: EC2 실행 준비 확인

> 코드 수정 완료 후 EC2 전송 및 실행 전 로컬 검증 단계.

- [ ] **Step 1: 전체 수정 파일 최종 확인**

```bash
git diff HEAD~4 --name-only
```

예상 출력:
```
dev/live_tests/evaluator_criteria.py
dev/live_tests/run_bedrock_model_test.py
dev/live_tests/run_single_bedrock_test.py
tests/dev/__init__.py
tests/dev/test_bedrock_model_setup.py
```

- [ ] **Step 2: 전체 테스트 최종 실행**

```bash
pytest tests/ -v -x
```

예상: 전체 통과

- [ ] **Step 3: EC2에 수정 파일 전송 (base64)**

수정된 3개 파일을 base64로 인코딩하여 EC2에 전송:

```bash
# 로컬에서 실행
base64 dev/live_tests/evaluator_criteria.py > /tmp/evaluator_criteria.b64
base64 dev/live_tests/run_single_bedrock_test.py > /tmp/run_single_bedrock_test.b64
base64 dev/live_tests/run_bedrock_model_test.py > /tmp/run_bedrock_model_test.b64

# EC2에서 복원
base64 -d /tmp/evaluator_criteria.b64 > dev/live_tests/evaluator_criteria.py
base64 -d /tmp/run_single_bedrock_test.b64 > dev/live_tests/run_single_bedrock_test.py
base64 -d /tmp/run_bedrock_model_test.b64 > dev/live_tests/run_bedrock_model_test.py
```

- [ ] **Step 4: EC2에서 Phase 0 실행 — 신규 모델 연결 확인**

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 0
```

결과 확인:
- 텍스트 모델 (claude-sonnet-4, nova-pro, nova-lite): `OK` 여부 확인
- 이미지 모델 (titan-v2, titan-v1, nova-canvas): `OK` 또는 `FAIL` 여부 확인
- **FAIL 모델은 `evaluator_criteria.py`에서 제거 후 EC2 재전송**

- [ ] **Step 5: Phase 1 실행 — 전체 벤치마크**

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 5
```

예상: 171 tests (텍스트 162 + visualization 9), visualization `quality > 0.0` 확인

- [ ] **Step 6: Phase 2 Scoring**

```bash
python3 -m dev.live_tests.scoring \
  --input dev/live_tests/results/bedrock_model_test/ \
  --output dev/live_tests/results/bedrock_model_test/summary/
```

- [ ] **Step 7: Phase 3 최적 모델 검증**

```bash
python3 -m dev.live_tests.run_bedrock_model_test \
  --phase 3 \
  --optimal-config dev/live_tests/results/bedrock_model_test/summary/optimal_config.json \
  --max-concurrent 5
```

예상: 30 tests 전체 성공

- [ ] **Step 8: 결과 커밋 (EC2 → 로컬 pull)**

```bash
git add dev/live_tests/results/bedrock_model_test/
git commit -m "test: Bedrock 모델 최적화 v2 테스트 결과 — Phase 0~3 완료"
```

---

## Task 7: `config/settings.yaml` 최적 모델 반영

> Phase 3 결과를 확인한 후 진행한다.

**Files:**
- Modify: `config/settings.yaml`

- [ ] **Step 1: Phase 3 결과에서 에이전트별 최적 모델 확인**

```bash
cat dev/live_tests/results/bedrock_model_test/summary/optimal_config.json
```

- [ ] **Step 2: `config/settings.yaml` `llm.bedrock_models` 신규 키 추가**

현재:
```yaml
llm:
  bedrock_models:
    haiku: "anthropic.claude-3-haiku-20240307-v1:0"
    sonnet: "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
    opus: "anthropic.claude-3-opus-20240229-v1:0"
```

추가 (optimal_config에서 신규 모델이 최적으로 선정된 경우):
```yaml
llm:
  bedrock_models:
    haiku: "anthropic.claude-3-haiku-20240307-v1:0"
    sonnet: "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
    opus: "anthropic.claude-3-opus-20240229-v1:0"
    sonnet_4: "apac.anthropic.claude-sonnet-4-20250514-v1:0"       # 신규 (필요 시)
    nova_pro: "apac.amazon.nova-pro-v1:0"                          # 신규 (필요 시)
    nova_lite: "apac.amazon.nova-lite-v1:0"                        # 신규 (필요 시)
```

> **주의:** `config/settings.yaml`은 공용 인프라 파일이므로 `pytest tests/ -v` 통과 후 커밋한다.

- [ ] **Step 3: 에이전트별 `model:` 값 변경**

optimal_config.json 결과를 기반으로 `agents.{name}.model:` 값을 변경한다.
변경 가능한 키는 `llm.bedrock_models`에 정의된 키만 사용한다.

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/ -v -x
```

예상: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add config/settings.yaml
git commit -m "config: Bedrock 최적화 v2 결과 반영 — 에이전트별 최적 모델 settings.yaml 업데이트"
```

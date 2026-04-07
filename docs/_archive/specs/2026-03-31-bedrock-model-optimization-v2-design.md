# Bedrock 모델 최적화 재설계 v2 — 전체 모델 범위 확장

**작성일:** 2026-03-31
**상태:** 승인됨
**관련 계획서:** `docs/superpowers/plans/2026-03-31-bedrock-model-optimization-v2.md` (작성 예정)

---

## 배경 및 목적

Phase 1~3 테스트 결과에서 발견된 3가지 문제를 해결하고,
전체 가용 Bedrock 모델에 대한 완전한 최적화를 재실행한다.

| # | 문제 | 원인 | 조치 |
|---|------|------|------|
| 1 | 모델 범위 부족 | Anthropic 5종만 테스트, 구버전/실패 모델 포함 | 모델 목록 재편성 |
| 2 | Visualization quality=0.000 | 텍스트 모델로 이미지 생성 모델 슬롯을 덮어씀 | 4개 지점 버그 수정 |
| 3 | Learning 구조적 저점 | 단일 세션 테스트 한계 | 이번 범위 외, 보류 |

---

## 1. 모델 목록 재편성

### BEDROCK_MODELS (텍스트 에이전트용) — 5종 → 6종

| 처리 | short | model_id | 이유 |
|------|-------|---------|------|
| **제거** | ~~c3-sonnet~~ | `apac.anthropic.claude-3-sonnet-20240229-v1:0` | Phase 1 30/30 전패 |
| **제거** | ~~c35-sonnet-v1~~ | `apac.anthropic.claude-3-5-sonnet-20240620-v1:0` | v2 구버전, 열등 |
| 유지 | c3-haiku | `anthropic.claude-3-haiku-20240307-v1:0` | 경량 최적 모델 |
| 유지 | c35-sonnet-v2 | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | 현 기본 모델 |
| 유지 | c37-sonnet | `apac.anthropic.claude-3-7-sonnet-20250219-v1:0` | 고성능 |
| **신규** | **claude-sonnet-4** | `apac.anthropic.claude-sonnet-4-20250514-v1:0` | 최신 Anthropic |
| **신규** | **nova-pro** | `apac.amazon.nova-pro-v1:0` | Amazon 최고 성능 |
| **신규** | **nova-lite** | `apac.amazon.nova-lite-v1:0` | Amazon 균형형 |

**비-Anthropic 후보 조사 결과 (ap-northeast-2 기준):**
- Meta Llama, Mistral: ap-northeast-2 리전 미지원 → 제외
- Amazon Nova Micro: 초경량 텍스트 전용 모델, 복잡한 한국어 추론 부적합 → 제외
- Amazon Nova Pro/Lite: APAC inference profile 지원 확인 → 포함

### IMAGE_MODELS (visualization 전용) — 기존 3종 유지

| short | model_id |
|-------|---------|
| titan-v2 | `amazon.titan-image-generator-v2:0` |
| titan-v1 | `amazon.titan-image-generator-v1` |
| nova-canvas | `amazon.nova-canvas-v1:0` |

---

## 2. Visualization 버그 수정

### 에이전트 동작 구조

Visualization 에이전트는 두 단계로 동작한다:

```
Step 1: call_llm_json()
        텍스트 LLM → image_prompt 텍스트 생성
        (settings 기본 모델 고정, 테스트 대상 아님)

Step 2: call_image_gen(model=image_model)
        이미지 생성 모델 → 실제 이미지 생성
        (agents.visualization.image_model 키, 이것이 테스트 대상)
```

### SKIP_VISUALIZATION 로직 — 변경 없음

`SKIP_VISUALIZATION` 환경변수는 비용 절감을 위한 의도적 설계이며 정상 동작한다.

| 상황 | skip_viz 값 | 결과 |
|------|------------|------|
| 다른 에이전트 모델 테스트 중 | `"true"` | visualization 스킵 (비용 절감) |
| visualization 에이전트 테스트 중 | `"false"` | visualization 실행 |
| 실제 파이프라인 (비테스트) | 환경변수 없음 | visualization 항상 실행 |

**버그는 skip 판단 이후 단계에서 발생한다.**

### 버그 지점 4곳

#### ① `run_bedrock_model_test.py` — Phase 0 이미지 모델 연결 SKIP

**현재:** `IMAGE_MODELS`를 `status: "skipped"`로 기록만 하고 실제 연결 확인 없음

**수정 후:** `VisualizationAgent`를 직접 생성하여 이미지 생성 1회 시도

```python
for model in IMAGE_MODELS:
    print(f"\n  [{model['short']}] {model['model_id']}...", end=" ")
    try:
        from src.agents.podcast.visualization import VisualizationAgent
        import config.loader
        config.loader._settings_instance = None
        settings = config.loader.get_settings()
        viz_cfg = settings._config.setdefault("agents", {}).setdefault("visualization", {})
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
        result = {"model": model, "status": "error", "error": str(e), "error_type": type(e).__name__}
        print(f"FAIL: {e}")

    out_path = phase0_dir / f"connectivity_{model['short']}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
```

---

#### ② `run_bedrock_model_test.py` — Phase 1 models 분기 없음

**현재:**
```python
skip_viz = "true" if agent_name != "visualization" else "false"
models = BEDROCK_MODELS  # visualization도 텍스트 모델 사용 → 버그
```

**수정 후:**
```python
if agent_name == "visualization":
    skip_viz = "false"
    models = IMAGE_MODELS
else:
    skip_viz = "true"
    models = BEDROCK_MODELS
```

---

#### ③ `run_bedrock_model_test.py` — Phase 3 model_id_map에 IMAGE_MODELS 미포함

**현재:**
```python
model_id_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}
...
model_id = model_id_map.get(model_short)   # visualization → None
if not model_id:
    print(f"  [!] 매핑 없음, 건너뜀")
    continue   # visualization 항상 스킵됨

skip_viz = "true" if agent_name != "visualization" else "false"
```

**수정 후:**
```python
from dev.live_tests.evaluator_criteria import BEDROCK_MODELS, IMAGE_MODELS
model_id_map = {m["short"]: m["model_id"] for m in BEDROCK_MODELS}
image_model_id_map = {m["short"]: m["model_id"] for m in IMAGE_MODELS}
...
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

---

#### ④ `run_single_bedrock_test.py` — model 오버라이드 키 오류

**현재:**
```python
# visualization도 텍스트 model_id 키를 덮어씀
# visualization.py line 74: agent_cfg.get("image_model") 참조 → 반영 안 됨
agent_cfg["model_id"] = args.model_id
```

**수정 후:**
```python
# visualization은 image_model 키로 오버라이드
if args.agent == "visualization":
    agent_cfg["image_model"] = args.model_id
else:
    agent_cfg["model_id"] = args.model_id
```

---

## 3. 수정 파일 요약

| 파일 | 수정 지점 | 내용 |
|------|----------|------|
| `dev/live_tests/evaluator_criteria.py` | `BEDROCK_MODELS` | c3-sonnet/c35-sonnet-v1 제거, claude-sonnet-4/nova-pro/nova-lite 추가 |
| `dev/live_tests/run_bedrock_model_test.py` | Phase 0 이미지 루프 | SKIP → VisualizationAgent 실제 연결 테스트 |
| `dev/live_tests/run_bedrock_model_test.py` | Phase 1 models 분기 | visualization → `IMAGE_MODELS` |
| `dev/live_tests/run_bedrock_model_test.py` | Phase 3 model_id_map | `image_model_id_map` 추가, visualization 분기 |
| `dev/live_tests/run_single_bedrock_test.py` | model 오버라이드 | visualization → `image_model` 키 |

---

## 4. 실행 계획 (EC2, max_concurrent=5)

### Step 1 — 코드 수정 (로컬 → EC2 base64 전송)

5개 파일 수정 후 EC2에 적용한다.

### Step 2 — Phase 0: 신규 모델 연결 확인

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 0
```

- 텍스트 모델 3종 신규 연결 확인: claude-sonnet-4, nova-pro, nova-lite
- 이미지 모델 3종 실제 연결 확인: titan-v2, titan-v1, nova-canvas (SKIP 해제 후 최초 실행)
- **실패 모델은 이후 단계 진행 전 `evaluator_criteria.py`에서 제거**

### Step 3 — Phase 1: 전체 벤치마크

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 5
```

| 대상 | 에이전트 수 | 모델 수 | 반복 | 테스트 수 |
|------|-----------|--------|------|---------|
| 텍스트 에이전트 | 9개 | 6종 | 3회 | 162 |
| visualization | 1개 | 3종 | 3회 | 9 |
| **합계** | **10개** | — | — | **171** |

max_concurrent=5로 동시 5개 subprocess 병렬 처리.

### Step 4 — Phase 2: Scoring

```bash
python3 -m dev.live_tests.scoring \
  --input dev/live_tests/results/bedrock_model_test/ \
  --output dev/live_tests/results/bedrock_model_test/summary/
```

- `aggregated_results.json`, `optimal_config.json` 생성

### Step 5 — Phase 3: 최적 모델 검증

```bash
python3 -m dev.live_tests.run_bedrock_model_test \
  --phase 3 \
  --optimal-config dev/live_tests/results/bedrock_model_test/summary/optimal_config.json \
  --max-concurrent 5
```

- 에이전트별 최적 모델 1종 × 3회 재검증
- 10 에이전트 × 3회 = **30 tests**, max_concurrent=5

### Step 6 — `config/settings.yaml` 업데이트

Phase 3 결과 기반으로:
1. `llm.bedrock_models`에 신규 모델 키 추가 (claude_sonnet_4, nova_pro, nova_lite)
2. 에이전트별 `model:` 값을 최적 모델로 변경

---

## 5. 검증 기준

- Phase 0: 신규 모델 6종 모두 연결 응답 확인
- Phase 1: visualization `quality > 0.0` (기존 0.000 탈출)
- Phase 3: 전체 에이전트 30/30 성공

---

*작성: 2026-03-31*

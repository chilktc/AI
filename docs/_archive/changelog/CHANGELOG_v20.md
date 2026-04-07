# 변경이력 v20

> 날짜: 2026-03-03

---

## v20: 테스트 스위트 구조 개선 — 361→270 테스트 감축 (v3+v4)

### 배경

v19에서 모니터링 인프라(텔레메트리 콜백, 에이전트 I/O 트래커, 스트리밍)를 구축하면서
**25개 테스트 파일, 361개 테스트** 항목이 축적되었다. 중복 검증, 과잉 parametrize,
미사용 fixture, 데드코드 등 테스트 유지보수 부담이 증가하여 **체계적인 감축 작업**을
2단계(v3 + v4)로 수행하였다.

**원칙**: Production 코드 변경 없음. Protected 파일 수정 없음.

### 변경 요약

| 단계 | 설명 | Before | After | 감축 |
|------|------|--------|-------|------|
| v3 | 단위 테스트 중심 구조 개선 | 361 | 285 | -76 |
| v4 | 통합/E2E 중복 병합 + 데드코드 | 285 | 270 | -15 |
| **총합** | | **361** | **270** | **-91 (-25.2%)** |

---

### v3: 단위 테스트 구조 개선 (361→285, -76)

#### 주요 작업

1. **공용 Mock 데이터 통합** — `tests/shared_fixtures/mock_data.py` 신규 생성
   - 흩어진 20+ mock 상수를 TIER 0~4 + 비동기별로 체계화
   - `DEVELOPER_FIELDS_*`, `EXPECTED_*_FIELDS` 검증 매핑 추가

2. **테스트 파일별 감축**

   | 파일 | Before | After | 변화 |
   |------|--------|-------|------|
   | `test_podcast_reasoning.py` | 38 | 14 | -24 |
   | `test_e2e_mock_pipeline.py` | 30 | 12 | -18 |
   | `test_llm_client.py` | 36 | 22 | -14 |
   | `test_content_analyzer.py` | 30 | 24 | -6 |
   | `test_batch_validator.py` | 20 | 10 | -10 |
   | `test_prompt_versioning.py` | 19 | 11 | -8 |
   | `test_prompt_loader.py` | 24 | 16 | -8 |
   | `test_visualization_agent.py` | 14 | 7 | -7 |
   | `test_learning.py` | 19 | 10 | -9 |
   | `test_streaming.py` | 17 | 10 | -7 |
   | `test_callbacks.py` | 17 | 14 | -3 |
   | 기타 소규모 | — | — | +38 (신규 fixture/conftest) |

3. **신규 인프라 파일**
   - `tests/__init__.py` — 테스트 패키지 초기화
   - `tests/agents/podcast/conftest.py` — GoT 기본 threshold autouse fixture
   - `tests/agents/shared/test_base_agent_tracing.py` — 트레이싱 테스트 분리
   - `tests/shared_fixtures/__init__.py` + `mock_data.py` — 공유 상수

4. **테스트 품질 개선**
   - `get_prompt` KeyError 방어: Emotion/Safety Agent fixture에서 `get_prompt` 패치 추가
   - `_mock_settings_factory` model_id 선택적 파라미터화: Bedrock/OpenAI 테스트 수정
   - E501 라인 길이 위반 수정 (ruff)

---

### v4: 통합/E2E 중복 병합 + 데드코드 (285→270, -15)

#### A. 중복 테스트 병합 (-13)

| 파일 | Before | After | 감축 | 방법 |
|------|--------|-------|------|------|
| `test_crisis_preemption.py` | 6 | 3 | -3 | 동일 mock 셋업 3개→1 병합, 팟캐스트 2개→1 병합, 클래스 제거 |
| `test_conversation_pipeline.py` | 5 | 3 | -2 | 동일 fan-out 호출 3개→1 병합, 클래스 제거 |
| `test_podcast_pipeline.py` | 4 | 2 | -2 | 동일 fan-out 호출 3개→1 병합, 클래스 제거 |
| `test_e2e_mock_pipeline.py` | 12→8 | 8 | -4 | 팟캐스트 3개→1, CRISIS 3개→1 병합 |
| `test_retry_loop.py` | 10 | 8 | -2 | 중복 케이스 삭제 + increment 통합 |
| `test_callbacks.py` | — | — | 0 | opus 정확값 검증을 parametrize 내부 통합 (항목 수 불변) |

#### B. 과잉 parametrize 정리 (-2)

| 파일 | 삭제 케이스 | 사유 |
|------|-----------|------|
| `test_streaming.py` | `test_compile_graph["default"]` | `builder=None` ↔ `"unified"` 동일 경로 |
| `test_retry_loop.py` | `test_increment_iteration[(0,1)]` | A에서 통합 |

#### C. 데드코드 삭제

| 대상 | 내용 |
|------|------|
| `tests/shared_fixtures/mock_states.py` | 파일 삭제 — 어떤 테스트에서도 import 안 됨 |
| `tests/shared_fixtures/__init__.py` | `mock_states` import 제거 |
| `tests/integration/conftest.py` | 미사용 fixture 9개 삭제: `mock_intent_result`, `mock_synthesis_result`, `mock_validation_pass_result`, `mock_validation_fail_result`, `mock_personalization_result`, `mock_script_draft_result`, `mock_batch_validation_pass`, `mock_batch_validation_fail`, `mock_all_llm_calls` |

---

### 변경된 파일 목록

#### 테스트 파일 (20개 수정 + 4개 신규 + 1개 삭제)

**수정 (20개):**

| 파일 | 카테고리 |
|------|---------|
| `tests/conftest.py` | 공용 설정 |
| `tests/integration/conftest.py` | 데드코드 삭제 |
| `tests/integration/test_crisis_preemption.py` | 병합 (6→3) |
| `tests/integration/test_conversation_pipeline.py` | 병합 (5→3) |
| `tests/integration/test_podcast_pipeline.py` | 병합 (4→2) |
| `tests/integration/test_retry_loop.py` | 병합 + 정리 |
| `tests/graph/test_e2e_mock_pipeline.py` | 병합 (12→8) |
| `tests/monitoring/test_callbacks.py` | 병합 |
| `tests/monitoring/test_streaming.py` | parametrize 정리 |
| `tests/agents/podcast/test_batch_validator.py` | v3 감축 |
| `tests/agents/podcast/test_content_analyzer.py` | v3 감축 |
| `tests/agents/podcast/test_emotion_agent.py` | v3 감축 + fixture 수정 |
| `tests/agents/podcast/test_episode_memory.py` | v3 감축 |
| `tests/agents/podcast/test_podcast_reasoning.py` | v3 감축 (38→14) |
| `tests/agents/podcast/test_safety_agent.py` | v3 감축 + fixture 수정 |
| `tests/agents/podcast/test_visualization_agent.py` | v3 감축 |
| `tests/agents/shared/test_llm_client.py` | v3 감축 + model_id 수정 |
| `tests/agents/shared/test_prompt_loader.py` | v3 감축 |
| `tests/agents/shared/test_prompt_versioning.py` | v3 감축 |
| `tests/agents/test_learning.py` | v3 감축 |

**신규 (4개):**

| 파일 | 내용 |
|------|------|
| `tests/__init__.py` | 테스트 패키지 초기화 |
| `tests/agents/podcast/conftest.py` | GoT threshold autouse fixture |
| `tests/agents/shared/test_base_agent_tracing.py` | 트레이싱 전용 테스트 분리 |
| `tests/shared_fixtures/` | `__init__.py` + `mock_data.py` (공유 Mock 상수) |

**삭제 (1개):**

| 파일 | 사유 |
|------|------|
| `tests/shared_fixtures/mock_states.py` | 미사용 데드코드 |

---

### 검증 결과

```
$ python3 -m pytest tests/ -v --tb=short
270 passed in 184.51s

$ python3 -m pytest tests/ --collect-only -q
270 tests collected

$ python3 -m ruff check tests/
All checks passed!

$ grep -r "mock_states" tests/
(0 matches)
```

---

### 참고: 간접 커버리지 확인

서브에이전트 전수 대조에서 "미테스트"로 식별된 7개 함수가 **모두 기존 E2E/통합 테스트로 간접 커버**됨을 확인:

| 함수 | 커버하는 테스트 |
|------|---------------|
| `route_after_tier0` | `test_conversation_full_pipeline`, `test_podcast_e2e_full` |
| `crisis_response_node` | `test_crisis_e2e_full` |
| `async_post_processing_node` | `test_conversation_full_pipeline` (END까지 도달) |
| `run_with_cancel` | `test_crisis_cancels_other_tasks` |
| `_safety_deep_crisis` | `test_crisis_conversation_all_assertions` |
| `intent_classifier_node` | 모든 E2E 테스트 (TIER 0 경유) |
| `build_unified_graph` | `test_unified_graph_builds_without_error` + E2E 전체 |

신규 테스트 추가 불필요.

---

*Production 코드 변경: 없음 | Protected 파일 수정: 없음*

# 코드 리뷰 보고서 — 2026-03-06

> 6개 서브에이전트 분석 결과를 종합한 코드 품질 개선 제안서.
> **개발자1·2 영역은 코드 수정 없이 제안 사항만 정리**했으며, 해당 개발자의 판단에 따라 적용 여부를 결정한다.

---

## 개발자1 영역 개선 제안

### `src/agents/conversation/intent_classifier.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 70 | `process()` 반환 타입 `dict` | `dict[str, Any]` 명시 | 코드 가독성 + mypy 정합성 |
| line 188 | `4000` 매직넘버 (입력 길이 제한) | 상수 `MAX_INPUT_LENGTH = 4000` 추출 | 의도 명확화, 설정 가능하게 |
| line 196-283 | `_preliminary_classify()` 88줄 | `_detect_crisis()`, `_detect_podcast()`, `_classify_by_pattern()` 분리 | 단일 책임 원칙, 테스트 용이성 |
| line 430-452 | 감정/주제 키워드 50+ 하드코딩 | `config/app_config.py`로 이동 | 키워드 추가/변경 시 코드 수정 불필요 |
| line 11 | `from typing import Dict, List, Optional` | PEP 585 (`dict`, `list`) 전환 | Python 3.11+ 표준 |

### `src/agents/conversation/knowledge.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 11 | `from typing import Dict, List, Optional` | PEP 585 전환 | Python 3.11+ 표준 |
| line 122, 144, 160 | `List[Dict[str, Any]]` 파라미터 타입 | `list[dict[str, Any]]` 변경 | 통일성 |
| line 88, 114, 140 | 광범위한 `except Exception` (3곳) | 구체적 예외 타입(`json.JSONDecodeError`, `KeyError` 등) | 디버깅 시 원인 파악 용이 |

### `src/agents/podcast/script_generator.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 27 | `process()` 반환 타입 `dict` | `dict[str, Any]` 명시 | mypy 정합성 |
| line 22 | `WORDS_PER_MINUTE = 150` 클래스 변수 | `settings.yaml`로 이동 | 환경별 조정 가능하게 |
| line 165-177 | 영어 프롬프트 하드코딩 (제목 생성) | YAML 프롬프트 파일로 이동 | 프롬프트 관리 정책과 일관성 |
| line 212-228 | 영어 프롬프트 하드코딩 (세그먼트 생성) | YAML 프롬프트 파일로 이동 | 동일 |
| line 11 | `from typing import Dict, List` | PEP 585 전환 | Python 3.11+ 표준 |

### `src/agents/podcast/script_personalizer.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 65 | `process()` 반환 타입 `dict` | `dict[str, Any]` 명시 | mypy 정합성 |
| line 248-315 | `_apply_rule_based_adjustments()` 68줄 | `_adjust_formality()`, `_adjust_age_style()`, `_adjust_attitude()` 분리 | 단일 책임 원칙 |
| line 11 | `from typing import Dict, List, Optional` | PEP 585 전환 | Python 3.11+ 표준 |

---

## 개발자2 영역 개선 제안

### `src/agents/podcast/visualization.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 59-61 | `"dall-e-3"`, `"1024x1024"`, `"standard"` 하드코딩 | `settings.yaml`의 `visualization` 섹션으로 이동 | 모델 변경 시 코드 수정 불필요 |

### `src/agents/conversation/emotion.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 51 | `"불안"`, `"우울"` 한국어 키워드 하드코딩 | `config/app_config.py`로 이동 | 키워드 추가 시 코드 수정 불필요 |
| line 62-66 | `_clamp()` 함수가 `process()` 내부에 정의 | 클래스 메서드 또는 모듈 레벨로 이동 | 재사용성, 테스트 용이성 |

---

## 공용 인프라 개선 제안 (팀 리뷰 대상)

### `src/agents/shared/base_agent.py`

| 위치 | 현재 상태 | 개선 제안 | 이유 |
|------|----------|----------|------|
| line 554-618 | `call_image_gen()`에서 openai 직접 import | LLMClient로 위임 | 멀티 프로바이더 추상화 원칙 일관성 |
| line 601 | 이미지 출력 경로 `"data/outputs/images"` 하드코딩 | `settings.yaml`로 이동 | 환경별 경로 조정 |

---

## 이번 정리에서 실행된 개선 사항

### 공용 인프라 수정 (Phase 2-3에서 완료)

- `config/loader.py` — 미사용 `is_feature_enabled()`, `anthropic_api_key` 제거
- `src/graph/workflow.py` — `_settings._config.get()` private 접근 → public 프로퍼티 사용
- `src/agents/shared/llm_client.py` — `parse_json_response()` / `_parse_json_response()` 중복 통합

### 개발자3 영역 수정 (Phase 3-A에서 완료)

- `src/agents/podcast/batch_validator.py` — `_build_validation_context()` (83줄) → `_build_script_context()` + `_build_analysis_context()` 분리
- 타입 힌트: 이미 PEP 585 준수 확인 (변경 불필요)
- `LearningEvent` 제거 불가: `script_personalizer.py`(개발자1)에서 사용 중

### 검증 불일치 (분석 오류 수정)

| 항목 | 원래 분석 | 실제 확인 | 조치 |
|------|----------|----------|------|
| `REDIS_CONFIG` (app_config.py) | 미사용 → 제거 | `intent_classifier.py`에서 import | 유지 (주석 업데이트) |
| `mock_content_analysis_result` (conftest.py) | 미사용 fixture | `test_podcast_pipeline.py`에서 사용 | 유지 |
| `mock_podcast_reasoning_result` (conftest.py) | 미사용 fixture | `test_podcast_pipeline.py`에서 사용 | 유지 |
| `LearningEvent` (schemas.py) | 미사용 → 제거 | `script_personalizer.py`에서 사용 | 유지 |

---

## 우선순위 요약

### 높음 (코드 안정성에 직접 영향)

1. **PEP 585 타입 힌트 통일** — 개발자1 파일 4개에서 `Dict`, `List`, `Optional` 사용 중
2. **`_preliminary_classify()` 분해** — 88줄 함수, 위기감지·팟캐스트감지·패턴분류 혼합
3. **광범위한 `except Exception`** — knowledge.py에서 3곳

### 중간 (유지보수성 향상)

4. **하드코딩된 프롬프트** — script_generator.py에 영어 프롬프트 2곳
5. **하드코딩된 키워드** — intent_classifier.py, emotion.py
6. **하드코딩된 모델/해상도** — visualization.py의 DALL-E 설정

### 낮음 (코드 정리)

7. **매직넘버 상수화** — intent_classifier.py `4000`, script_generator.py `150`
8. **`_clamp()` 위치 이동** — emotion.py
9. **이미지 출력 경로 설정화** — base_agent.py

---

*작성일: 2026-03-06*

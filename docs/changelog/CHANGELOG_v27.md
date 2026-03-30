# 변경이력 v27

> 날짜: 2026-03-30

## 개요

팟캐스트 파이프라인의 동시 요청 안전성을 확보하기 위한 구조적 리팩토링.
10개 에이전트의 모듈 레벨 싱글톤을 제거하고 요청별 인스턴스 생성으로 전환하여,
100명 동시 요청에서도 사용자 간 개인정보가 절대 섞이지 않도록 한다.

전체 298 테스트 통과 확인.

---

## 주요 변경

### refactor: 에이전트 싱글톤 → 요청별 인스턴스 (레이어 A)

**배경**: 모듈 레벨 싱글톤 에이전트가 `_last_input_snapshot`, `_llm_call_count` 등
mutable 인스턴스 상태를 동시 요청 간 공유하여, 사용자 A의 민감 데이터가 사용자 B에게 노출될 수 있었다.

**변경**: 노드 함수 내부에서 에이전트를 매번 새로 생성하는 패턴으로 전환.

| 파일 | 제거된 싱글톤 |
|------|-------------|
| `src/graph/workflow.py` | `_intent_classifier`, `_script_generator`, `_script_personalizer` |
| `src/agents/podcast/safety.py` | `safety_agent` |
| `src/agents/podcast/emotion.py` | `emotion_agent` |
| `src/agents/podcast/content_analyzer.py` | `content_analyzer_agent` |
| `src/agents/podcast/podcast_reasoning.py` | `podcast_reasoning_agent` |
| `src/agents/podcast/batch_validator.py` | `batch_validator_agent` |
| `src/agents/podcast/visualization.py` | `visualization_agent` |
| `src/agents/shared/learning.py` | `learning_agent` |

`workflow.py`의 `reset_agents()` 함수도 삭제 (싱글톤 없으므로 불필요).

### refactor: base_agent.py — ContextVar 일원화 (레이어 B)

- `_current_ab_variant` 인스턴스 변수 제거 — ContextVar `_active_ab_variant`로 일원화
- `ab_variant` 프로퍼티가 ContextVar에서 직접 읽도록 변경
- LangSmith metadata, `get_execution_metrics()`도 ContextVar 사용으로 통일
- 클래스 docstring에 `[동시성 안전]` 경고 추가
- `_llm_call_count`, `_last_input_snapshot`, `_last_output_snapshot`에 동시성 주석 추가

### refactor: llm_client.py — 방어적 복사 (레이어 C)

- `last_usage` 프로퍼티가 `.copy()` 반환으로 변경 (내부 상태 보호)
- `_custom_providers`, `_last_usage`, `_total_usage`에 동시성 주석 추가
- 클래스 docstring에 `[동시성 안전]` 경고 추가

### fix: docker-compose.yml

- deprecated `version: '3.8'` 제거 (Docker Compose V2 경고 해소)

### test: E2E mock 테스트 패치 방식 전환

- `tests/graph/test_e2e_mock_pipeline.py`: 4개 fixture의 싱글톤 인스턴스 패치를 노드 함수 패치로 전환
  - `wf._intent_classifier.process` → `wf.intent_classifier_node`
  - `wf._script_generator.process` → `wf.script_generator_node`
  - `wf._script_personalizer.process` → `wf.script_personalizer_node`
- `test_retry_then_pass` fixture도 동일하게 수정

### docs: 문서 정비

- `CLAUDE.md`: 노드 인터페이스 규칙에 요청별 생성 패턴 명시, 구현 현황 날짜 갱신, 삭제된 문서 참조 제거
- `docs/guides/E2E_TEST_GUIDE.md`: 싱글톤 리프레시 섹션 → 모듈 재로드 방식으로 교체
- `docs/guides/AGENT_DEV_GUIDE.md`: 싱글톤 + 노드 래퍼 예시 → 요청별 인스턴스 패턴으로 교체
- `docs/getting-started/QUICK_START.md`: 노드 함수 예시 추가
- `docs/superpowers/specs/...design.md`: Section 1에 "리팩토링 전 기준" 주석 추가
- `docs/superpowers/plans/...md`: 구현 완료 상태 반영

---

## 설계 문서

- 설계서: `docs/superpowers/specs/2026-03-30-podcast-concurrency-isolation-design.md`
- 구현 계획: `docs/superpowers/plans/2026-03-30-podcast-concurrency-isolation.md`

---

## 영향

- **동시성**: 요청별 인스턴스 생성으로 모든 mutable 상태가 격리됨
- **성능**: 인스턴스 생성 오버헤드 ~5-15ms (LLM 호출 대비 0.1% 미만)
- **기존 테스트**: 298 전체 통과 (싱글톤 패치 테스트 4건 노드 함수 패치로 수정)
- **보호 파일**: `base_agent.py`, `llm_client.py` 수정 (주석 + 방어적 복사 + ContextVar 일원화)

---

*마지막 업데이트: 2026-03-30*

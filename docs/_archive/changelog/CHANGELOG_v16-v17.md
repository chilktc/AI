# 변경이력 v16~v17

> 날짜: 2026-02-15

---

## v16: 2차 검토 — 문서 동기화 잔존 불일치 수정

### 배경

v14에서 문서 일관성 통합 업데이트를 수행했으나, 2차 검토에서 8건의 잔존 불일치가 발견되었다.

### 변경 내용 (8개 파일)

| 파일 | 변경 내용 |
|------|----------|
| `config/settings.yaml` | 대화모드 에이전트 7개 설정 추가 (intent_classifier, safety, emotion, context, reasoning, synthesis, validator, personalization), 섹션 구분자(공용/대화/팟캐스트/비동기) 정리 |
| `CLAUDE.md` | Reasoning Agent 모델: `Sonnet 4` → `Opus 4.6` (line 44) |
| `README.md` | `Opus 4.5` → `Opus 4.6` (line 37) |
| `docs/PROJECT_SUMMARY.md` | `Opus 4.5` → `Opus 4.6` (2곳: line 65, 95) |
| `ProjectDocs/ARCHITECTURE_v4.0.md` | `class TierOneOrchestrator:` → LangGraph 기반 `tier1_fan_out()` 함수로 교체 (line 237-264) |
| `ProjectDocs/agents/conversation/02_safety.md` | v4.0 주석 추가: "아래 코드는 CRISIS 선점의 개념 설명용입니다" (line 361-375) |
| `ProjectDocs/참고자료/듀얼모드_아키텍처_분석.md` | "v3.0 방식의 단점을 보여주는 예시" 주석 추가 |
| `ProjectDocs/agents/conversation/07_reasoning.md` | 모델 주석: `Sonnet 4` → `Opus 4.6` (line 125, 372) |

### 검증

- `Opus 4.5` grep: 0건 (main 소스 기준)
- `TierOneOrchestrator` grep: 0건 (완전 제거)
- `WorkflowOrchestrator` grep: 1건 (주석 달린 개념 설명용)
- settings.yaml 대화모드 에이전트 7개 확인

---

## v17: 공통 인프라 완성 — workflow.py, 통합 테스트, 개발 가이드

### 배경

설계 문서 20개 에이전트 명세(98%)와 공용 인프라(95%)가 완성된 상태에서, 나머지 개발자들이 에이전트를 구현하기 위한 공통 인프라를 완성한다.

### 신규 파일

| 파일 | 내용 |
|------|------|
| `src/graph/workflow.py` | **[Protected File]** LangGraph 듀얼모드 TIER 파이프라인 스켈레톤. 8개 핵심 함수 (run_with_cancel, tier1_*_fan_out, route_after_*, build_*_graph), 미구현 에이전트 stub 노드, Safety CRISIS 선점(asyncio.Event), 재시도 루프(max 2회), 모드 분기 라우터 |
| `tests/integration/conftest.py` | 통합 테스트 공용 fixture — AgentState, 모의 에이전트 결과, 전역 LLM mock |
| `tests/integration/test_conversation_pipeline.py` | 대화모드 TIER 1 fan-out + 상태 전달 검증 (5 tests) |
| `tests/integration/test_podcast_pipeline.py` | 팟캐스트모드 TIER 1 fan-out + 상태 전달 검증 (4 tests) |
| `tests/integration/test_crisis_preemption.py` | Safety CRISIS 선점 — 취소/즉시응답/TIER건너뜀 검증 (6 tests) |
| `tests/integration/test_retry_loop.py` | TIER 3→2 재시도 루프 — 라우터/카운터/엣지케이스 (17 tests) |
| `docs/AGENT_DEV_GUIDE.md` | 에이전트 개발 가이드 7개 섹션 (체크리스트, 템플릿, YAML 작성법, 테스트 패턴, 공용 에이전트 분기, workflow.py 등록, 참고 예시) |
| `prompts/**/*.yaml` (22개) | 프롬프트 YAML — 로컬 전용, gitignored. 개발자3 직접 작성 7개 + 플레이스홀더 15개 |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/shared/stubs.py` | `MemoryAgentStub` 클래스 추가 (대화모드 Reasoning Agent DI용) |
| `docs/QUICK_START.md` | "3. 첫 에이전트 개발" 섹션에 AGENT_DEV_GUIDE.md 참조 링크 추가 |
| `.gitignore` | `models/` → `/models/` (src/models/ 추적 복구), `.claude/` 제외 추가 |

### .gitignore 버그 수정

`models/` 규칙이 `src/models/`까지 매칭하여 **Protected File 3개가 git에서 누락**되던 문제 수정:
- `models/` → `/models/` (루트 디렉토리만 매칭)
- 복구된 파일: `src/models/__init__.py`, `src/models/agent_state.py`, `src/models/message.py`

### 테스트

- 기존: 210개 → 신규 32개 추가 → 총 **242개 passed**
- `ruff check src/ tests/`: All checks passed
- `mypy src/`: no issues found in 24 source files

---

*마지막 업데이트: 2026-02-15*

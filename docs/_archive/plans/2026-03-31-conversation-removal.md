# 대화모드 잔재 제거 — 팟캐스트 전용 프로젝트 전환

**작성일**: 2026-03-31
**대상 브랜치**: develop
**범위**: 대화모드 전용 코드·설정·프롬프트·테스트·문서 제거, 폴더 구조 단순화

---

## Context

프로젝트가 "대화모드+팟캐스트모드" 듀얼모드에서 **팟캐스트 전용**으로 전환된다.
"대화모드와 팟캐스트모드를 위한 공용"이라는 개념 자체가 사라지며, 모든 에이전트는 팟캐스트를 위해 존재한다.
공용 인프라 코드(BaseAgent, LLMClient, PromptLoader 등)는 유지하되, "모드 공용 에이전트"라는 분류는 제거한다.

**핵심 원칙:**
- `src/agents/shared/` = **인프라 코드만** (base_agent, llm_client, prompt_loader 등)
- `src/agents/podcast/` = **모든 에이전트** (intent_classifier, knowledge, learning 포함)
- `src/agents/conversation/` = **삭제**
- `prompts/conversation/` = **삭제**
- `prompts/shared/` = learning.yaml을 podcast/로 이동 후 **삭제**

---

## 전환 후 에이전트 목록 (11개)

| # | 에이전트 | TIER | 현재 위치 | 전환 후 위치 | 역할 |
|---|---------|------|---------|-----------|------|
| 01 | Intent Classifier | TIER 0 | conversation/ | **podcast/** (이동) | 의도 분류 + 1차 위기 감지 |
| 02 | Safety Agent | TIER 1 (병렬) | podcast/ | podcast/ (유지) | 안전성 검증 + CRISIS 선점 |
| 03 | Emotion Agent | TIER 1 (병렬) | podcast/ | podcast/ (유지) | 감정 벡터 추출 |
| 04 | Content Analyzer | TIER 1 (병렬) | podcast/ | podcast/ (유지) | 주제 분석 |
| 05 | Podcast Reasoning | TIER 1 (병렬) | podcast/ | podcast/ (유지) | GoT/ToT/CoT 추론 |
| 06 | Episode Memory | 독립 (Reasoning 조건부) | podcast/ | podcast/ (유지) | 에피소드 기억 저장/검색 |
| 07 | Knowledge Agent | 독립 (Reasoning 조건부) | conversation/ | **podcast/** (이동) | 전문 지식 RAG 검색 |
| 08 | Script Generator | TIER 2 (병렬) | podcast/ | podcast/ (유지) | 스크립트 생성 |
| 09 | Visualization | TIER 2 (병렬) / 비동기 | podcast/ | podcast/ (유지) | 커버 이미지 생성 |
| 10 | Batch Validator | TIER 3 | podcast/ | podcast/ (유지) | 품질 검증 |
| 11 | Script Personalizer | TIER 4 | podcast/ | podcast/ (유지) | 톤/스타일 조정 |

> Learning Agent는 비동기 후처리(async_post_processing_node)에서 실행.
> shared/ → **podcast/**로 이동 (삭제 아님). 이동 시 학습 컨텍스트 보강도 포함.

| 부가 | Learning Agent | 비동기 후처리 | shared/ | **podcast/** (이동 + 보강) | 사용자 패턴 학습 → 개인화 |

**삭제되는 에이전트 (stub 6개):**
- Context Agent (stub)
- Reasoning Agent — 대화모드 (stub)
- Synthesis Agent (stub)
- Validator Agent — 대화모드 (stub)
- Personalization Agent (stub)
- Telemetry Agent (stub) — 삭제. 모니터링은 기존 인프라(callback + Prometheus + LangSmith)로 충분. `async_post_processing_node`에서 telemetry_node 호출 제거, Learning만 남김.

**shared/ 잔류 (인프라 코드 9개):**
| 파일 | 역할 |
|------|------|
| base_agent.py | 모든 에이전트 부모 클래스 |
| llm_client.py | LLM 멀티 프로바이더 클라이언트 |
| prompt_loader.py | YAML 프롬프트 로더 |
| base_memory.py | 메모리 에이전트 부모 클래스 |
| context_utils.py | 컨텍스트 빌드 유틸리티 |
| safety_constants.py | 안전 상수 (CRISIS_HELPLINES 등) |
| stubs.py | KnowledgeAgentStub, EpisodeMemoryStub |
| input_sanitizer.py | 입력 인젝션 감지 |
| output_sanitizer.py | 출력 PII 정제 |

---

## 폴더 구조 변경

### 변경 전
```
src/agents/
├── conversation/           ← 삭제
│   ├── intent_classifier.py   (→ podcast/로 이동)
│   └── knowledge.py           (→ podcast/로 이동)
├── podcast/
│   ├── batch_validator.py
│   ├── content_analyzer.py
│   ├── emotion.py
│   ├── episode_memory.py
│   ├── podcast_reasoning.py
│   ├── safety.py
│   ├── script_generator.py
│   ├── script_personalizer.py
│   └── visualization.py
└── shared/
    ├── base_agent.py        (인프라, 유지)
    ├── llm_client.py        (인프라, 유지)
    ├── prompt_loader.py     (인프라, 유지)
    ├── base_memory.py       (인프라, 유지)
    ├── context_utils.py     (유틸리티, 유지)
    ├── safety_constants.py  (유틸리티, 유지)
    ├── stubs.py             (유틸리티, 유지)
    ├── input_sanitizer.py   (유틸리티, 유지)
    ├── output_sanitizer.py  (유틸리티, 유지)
    └── learning.py          (→ podcast/로 이동)
```

### 변경 후
```
src/agents/
├── podcast/                ← 모든 에이전트
│   ├── intent_classifier.py   (conversation/에서 이동)
│   ├── knowledge.py           (conversation/에서 이동)
│   ├── learning.py            (shared/에서 이동)
│   ├── batch_validator.py
│   ├── content_analyzer.py
│   ├── emotion.py
│   ├── episode_memory.py
│   ├── podcast_reasoning.py
│   ├── safety.py
│   ├── script_generator.py
│   ├── script_personalizer.py
│   └── visualization.py
└── shared/                 ← 인프라 코드만
    ├── base_agent.py
    ├── llm_client.py
    ├── prompt_loader.py
    ├── base_memory.py
    ├── context_utils.py
    ├── safety_constants.py
    ├── stubs.py
    ├── input_sanitizer.py
    └── output_sanitizer.py

prompts/
├── podcast/                ← 모든 프롬프트
│   ├── intent_classifier.yaml  (이미 존재)
│   ├── knowledge.yaml          (이미 존재)
│   ├── learning.yaml           (shared/에서 이동)
│   ├── batch_validator.yaml
│   ├── content_analyzer.yaml
│   ├── emotion.yaml
│   ├── podcast_reasoning.yaml
│   ├── safety.yaml
│   ├── script_generator.yaml
│   ├── script_personalizer.yaml
│   ├── visualization.yaml
│   └── _archive/
└── _pipeline_context.yaml
```

---

## 프롬프트 로딩 메커니즘 (변경 불필요)

`BaseAgent._resolve_mode()`가 모듈 경로에서 자동 판별:
- `src.agents.podcast.*` → `"podcast"` → `prompts/podcast/{agent_name}.yaml`
- `src.agents.shared.*` → `"shared"` → `prompts/shared/{agent_name}.yaml`

에이전트를 `podcast/`로 이동하면 mode가 자동으로 `"podcast"`가 되어 `prompts/podcast/`에서 프롬프트를 로드한다.
→ PromptLoader 코드 변경 불필요.

**단, knowledge.py에 하드코딩된 `"conversation"` 3곳 수정 필수:**
```python
# 변경 전 (3곳)
self._prompt_loader.load_user_prompt("conversation", "knowledge", "expand_query")
# 변경 후
self._prompt_loader.load_user_prompt(self._prompt_mode, "knowledge", "expand_query")
```

---

## Import 경로 변경 영향 범위

### conversation → podcast 이동 (3곳)
| 파일 | 현재 import | 변경 |
|------|-----------|------|
| `src/graph/workflow.py:99` | `from src.agents.conversation.intent_classifier` | `from src.agents.podcast.intent_classifier` |
| `tests/agents/conversation/test_intent_classifier.py` | `from src.agents.conversation.intent_classifier` | 파일 이동 후 `from src.agents.podcast.intent_classifier` |
| `tests/agents/conversation/test_knowledge.py` | `from src.agents.conversation.knowledge` | 파일 이동 후 `from src.agents.podcast.knowledge` |

### shared → podcast 이동 (learning, ~8곳)
| 파일 | 현재 import | 변경 |
|------|-----------|------|
| `src/graph/workflow.py:108` | `from src.agents.shared.learning` | `from src.agents.podcast.learning` |
| `tests/agents/test_learning.py` | `from src.agents.shared.learning` | `from src.agents.podcast.learning` |
| `dev/live_tests/test_learning_live.py` | `from src.agents.shared.learning` | `from src.agents.podcast.learning` |
| `dev/live_tests/test_custom_input.py` | `from src.agents.shared.learning` | `from src.agents.podcast.learning` |
| `dev/live_tests/test_pipeline_live.py` | `from src.agents.shared.learning` | `from src.agents.podcast.learning` |
| `src/api/routes/sessions.py:21` | `from src.agents.shared.learning` (주석 상태) | 동일 변경 또는 삭제 |

### shared 인프라 import (변경 없음)
`from src.agents.shared.base_agent`, `llm_client`, `prompt_loader` 등 76곳 → **경로 변경 없음**

---

## API 영향

### 변경 필요
| 파일 | 항목 | 변경 |
|------|------|------|
| `external_schemas.py` | `SessionCreateRequest.mode` 기본값 | `"conversation"` → `"podcast"` |
| `external_schemas.py` | `SessionCreateRequest.mode` Literal | `["conversation", "podcast"]` → `["podcast"]` (deprecated 처리 또는 즉시 제거) |
| `external_schemas.py` | 대화 전용 스키마 6개 | `ConversationRequest`, `ConversationResponse`, `ConversationResponseMeta`, `ConversationContextHint`, `ConversationPreferences`, `MySQLConversationTurn` 삭제 |
| `backend_resources.py` | `RESOURCE_CONVERSATION`, `RESOURCE_MEMORY` | 삭제 (TODO 상태, 미사용) |
| `sessions.py:69-72` | Learning Agent 트리거 TODO | 주석 삭제/갱신 |
| `tests/api/test_sessions_endpoint.py` | mode 기본값 테스트 | `"conversation"` → `"podcast"` |

### 변경 없음
- `POST /api/podcasts/episodes` — 영향 없음
- `POST /api/podcasts/episodes/stream` — 영향 없음
- `POST /api/sessions` — mode 기본값만 변경
- `GET /health` — 영향 없음

---

## Phase 1 — 에이전트 파일 이동 + import 수정

### 1-1. 파일 이동 (git mv)
```
src/agents/conversation/intent_classifier.py → src/agents/podcast/intent_classifier.py
src/agents/conversation/knowledge.py → src/agents/podcast/knowledge.py
src/agents/shared/learning.py → src/agents/podcast/learning.py
```

### 1-2. knowledge.py 하드코딩 수정
`"conversation"` → `self._prompt_mode` (3곳: _expand_query, _assess_applicability, _synthesize_knowledge)

### 1-3. learning.py 이동 + 학습 컨텍스트 보강

> Learning Agent는 삭제가 아닌 **이동 + 보강**. 최종 응답 후 개인화 학습 데이터를 관리하는 핵심 에이전트.

**이동**: `src/agents/shared/learning.py` → `src/agents/podcast/learning.py`
**프롬프트**: `prompts/shared/learning.yaml` → `prompts/podcast/learning.yaml`
**주석 갱신**: 파일 내 경로 참조

**학습 컨텍스트 보강** (`_build_learning_context()` 메서드):

현재 포함되는 데이터 (4개):
- `user_input`, `emotion_vectors` (primary_emotion, intensity만), `content_analysis` (topic, episode_type만), `final_output` (500자 절삭)

추가할 데이터 (개인화에 유용한 4개):
- `safety_flags` — 위험 수준/패턴 → 프롬프트의 `risk_patterns` 분석 근거
- `intent` — 의도 분류 결과 (intent_type, complexity_score) → `topic_preferences` 정확도 향상
- `reasoning_result` — 추론 깊이/방법 (depth_level) → `engagement_patterns.avg_session_depth`
- `validation_result` — BV score → 품질 추이 분석

```python
# 추가할 섹션들
safety_sec = build_section(
    "안전성 분석",
    state.get("safety_flags", {}),
    ["status", "risk_score"],
)
intent_sec = build_section(
    "의도 분류",
    state.get("intent", {}),
    ["intent_type", "complexity_score"],
)
reasoning_sec = build_section(
    "추론 결과",
    state.get("reasoning_result", {}),
    ["depth_level", "method"],
)
validation_sec = build_section(
    "검증 결과",
    state.get("validation_result", {}),
    ["overall_score", "safety_compliance"],
)
```

### 1-4. import 경로 수정
- `src/graph/workflow.py` (2곳: intent_classifier, learning)
- 테스트 파일들 (이동과 동시에 수정)

### 1-5. 테스트 파일 이동
```
tests/agents/conversation/test_intent_classifier.py → tests/agents/podcast/test_intent_classifier.py
tests/agents/conversation/test_knowledge.py → tests/agents/podcast/test_knowledge.py
```

### 1-6. 프롬프트 파일 이동
```
prompts/shared/learning.yaml → prompts/podcast/learning.yaml
```

### 1-7. 디렉토리 삭제
- `src/agents/conversation/` (빈 디렉토리 + __init__.py)
- `prompts/shared/` (learning.yaml 이동 후 나머지 7개 미사용 파일 삭제)

**검증**: `pytest tests/agents/podcast/test_intent_classifier.py tests/agents/podcast/test_knowledge.py tests/agents/test_learning.py -v`

---

## Phase 2 — workflow.py 대화모드 코드 제거 + 테스트 정리 (단일 커밋)

### 2-1. workflow.py 삭제 대상

| 대상 | 설명 |
|------|------|
| `_stub_node()` 헬퍼 | 대화 stub에서만 사용 |
| `context_node()` stub | 대화 TIER 1 |
| `reasoning_node()` stub | 대화 TIER 1 |
| `synthesis_node()` stub | 대화 TIER 2 |
| `validator_node()` stub | 대화 TIER 3 |
| `personalization_node()` stub | 대화 TIER 4 |
| `telemetry_node()` stub | 모니터링은 callback+Prometheus+LangSmith로 충분 |
| `tier1_conversation_fan_out()` | 대화 TIER 1 팬아웃 (~86줄) |
| `route_after_tier3_conversation()` | 대화 TIER 3 라우팅 |
| `build_conversation_graph()` | 대화 전용 그래프 빌더 |

**유지**: `telemetry_node` stub — `async_post_processing_node`에서 호출

### 2-2. workflow.py 수정 대상

- `route_after_tier0()`: "conversation" 분기 제거 → `"tier1_podcast"` 고정
- `build_unified_graph()`: 대화 노드 등록/엣지 제거
- `compile_graph()`: builders에서 `"conversation"` 키 제거
- `async_post_processing_node()`: telemetry_node 호출 제거 → Learning만 실행
- `langgraph.json`: "conversation" 빌더 매핑 제거

### 2-3. 테스트 삭제/수정

**삭제:**
- `tests/integration/test_conversation_pipeline.py`
- `tests/agents/conversation/` 디렉토리 (Phase 1 이후 빈 디렉토리)

**수정:**
- `tests/integration/conftest.py`: conversation_state, mock_context_result, mock_reasoning_result fixture 삭제
- `tests/integration/test_crisis_preemption.py`: conversation fan-out 사용 테스트 삭제
- `tests/integration/test_retry_loop.py`: "conversation" 파라미터 제거
- `tests/graph/test_e2e_mock_pipeline.py`: 대화 fixture/테스트/mock 삭제
- `tests/shared_fixtures/mock_data.py`: 대화 전용 mock 상수 삭제

**검증**: `pytest tests/ -v`

---

## Phase 3 — Protected Files + 모델 수정

### 3-1. agent_state.py
- `mode: Literal["conversation", "podcast"]` → `mode: Literal["podcast"]`
- `context: dict` 필드 삭제
- `response_draft: str` 필드 삭제

### 3-2. message.py
- `MessageMetadata.mode` Literal에서 "conversation" 제거

### 3-3. base_agent.py
- `_resolve_mode()`에서 "conversation" 분기 제거
- `create_message()` 내 `"episode" if mode == "podcast" else "turn"` → `"episode"`

### 3-4. stubs.py
- `MemoryAgentStub` 삭제 (대화모드 전용)

**검증**: `pytest tests/ -v`

---

## Phase 4 — 설정 + API 정리

### 4-1. settings.yaml
**삭제**: context, reasoning, memory, synthesis, validator, personalization 에이전트 설정
**유지**: knowledge (팟캐스트 사용), visualization (공용)
**주석 갱신**: "대화모드 TIER X" 라벨 삭제
**삭제**: Pinecone `index_memory_conversation`

### 4-2. external_schemas.py
- SessionCreateRequest.mode 기본값 → `"podcast"`
- 대화 전용 스키마 6개 삭제 (ConversationRequest, ConversationResponse 등)

### 4-3. backend_resources.py
- RESOURCE_CONVERSATION, RESOURCE_MEMORY 삭제

### 4-4. sessions.py
- 대화모드 TODO 주석 삭제/갱신

**검증**: `pytest tests/ -v`

---

## Phase 5 — 프롬프트 디렉토리 정리

- `prompts/conversation/` 전체 삭제 (12개 파일)
- `prompts/shared/` 전체 삭제 (Phase 1에서 learning.yaml 이동 후 미사용 7개)

**검증**: `pytest tests/ -v`, 프롬프트 로딩 테스트

---

## Phase 6 — 문서 갱신

### CLAUDE.md
- "듀얼모드" → 팟캐스트 전용 아키텍처
- 대화모드 에이전트 테이블/실행 흐름 삭제
- Intent Classifier, Knowledge를 podcast/ 위치로 갱신
- 개발자 담당에서 대화모드 열 삭제

### README.md
- 듀얼모드 테이블 삭제, 팟캐스트 전용으로

### docs/architecture/AGENT_ROLES.md
- 대화모드 에이전트 설명 삭제

**검증**: 문서 링크 확인

---

## Phase 7 — 최종 검증

### 7-1. 테스트 스위트

```bash
# 전체 테스트
pytest tests/ -v --tb=short

# 이동된 에이전트 개별 테스트
pytest tests/agents/podcast/test_intent_classifier.py -v
pytest tests/agents/podcast/test_knowledge.py -v
pytest tests/agents/test_learning.py -v

# 그래프 컴파일 + 스트리밍 테스트
pytest tests/monitoring/test_streaming.py -v
pytest tests/graph/ -v

# 프롬프트 로딩 테스트
pytest tests/agents/shared/test_prompt_loader.py -v

# 보안 테스트 (Phase 1-4 이후 유지 확인)
pytest tests/agents/shared/test_input_sanitizer.py tests/agents/shared/test_output_sanitizer.py -v
```

### 7-2. 그래프 컴파일 검증

```bash
# 팟캐스트/통합 그래프 컴파일 성공
python3 -c "
from src.graph.workflow import compile_graph
compile_graph('unified')
compile_graph('podcast')
print('OK: unified + podcast 컴파일 성공')
"

# conversation 그래프 빌더가 제거되었는지 확인
python3 -c "
from src.graph.workflow import compile_graph
try:
    compile_graph('conversation')
    print('FAIL: conversation 빌더가 아직 존재')
except (ValueError, KeyError):
    print('OK: conversation 빌더 제거 확인')
"
```

### 7-3. 잔재 검색

```bash
# src/ config/ tests/ 에서 "conversation" 문자열 잔재
grep -rn "conversation" src/ config/ tests/ \
  --include="*.py" --include="*.yaml" --include="*.yml" \
  | grep -v __pycache__ | grep -v changelog | grep -v ".pyc"

# 허용되는 잔재: external_schemas.py의 deprecated 주석, changelog 문서
# 그 외 0건이어야 함

# workflow.py 전용 검증 (0건 필수)
grep -n "conversation" src/graph/workflow.py

# settings.yaml 전용 검증 (0건 필수)
grep -n "conversation" config/settings.yaml

# _stub_node 함수 잔재 (0건 필수 — telemetry_node 포함 모든 stub 제거)
grep -n "_stub_node\|stub_node" src/graph/workflow.py
```

### 7-4. 디렉토리 구조 검증

```bash
# 삭제된 디렉토리 확인
[ ! -d src/agents/conversation ] && echo "OK: src/agents/conversation/ 삭제됨" || echo "FAIL"
[ ! -d prompts/conversation ]    && echo "OK: prompts/conversation/ 삭제됨"    || echo "FAIL"
[ ! -d prompts/shared ]          && echo "OK: prompts/shared/ 삭제됨"          || echo "FAIL"
[ ! -d tests/agents/conversation ] && echo "OK: tests/agents/conversation/ 삭제됨" || echo "FAIL"

# shared/ 에 에이전트 파일이 없는지 확인 (인프라만 존재)
ls src/agents/shared/*.py | grep -v base_agent | grep -v llm_client | grep -v prompt_loader \
  | grep -v base_memory | grep -v context_utils | grep -v safety_constants \
  | grep -v stubs | grep -v input_sanitizer | grep -v output_sanitizer \
  | grep -v __init__ \
  && echo "FAIL: shared/에 인프라 외 파일 존재" || echo "OK: shared/는 인프라만"

# podcast/ 에 모든 에이전트가 존재하는지 확인
for agent in intent_classifier knowledge learning batch_validator content_analyzer \
  emotion episode_memory podcast_reasoning safety script_generator \
  script_personalizer visualization; do
  [ -f "src/agents/podcast/${agent}.py" ] && echo "OK: ${agent}.py" || echo "FAIL: ${agent}.py 없음"
done
```

### 7-5. import 경로 검증

```bash
# 삭제된 경로 import가 남아있지 않은지 확인 (0건 필수)
grep -rn "from src.agents.conversation" src/ tests/ dev/ --include="*.py"
grep -rn "from src.agents.shared.learning" src/ tests/ dev/ --include="*.py"

# telemetry_node 참조가 workflow.py에서 제거되었는지 확인
grep -n "telemetry_node" src/graph/workflow.py
# 0건이어야 함
```

### 7-6. API 엔드포인트 검증

```bash
# SessionCreateRequest.mode 기본값 확인
grep -n "mode.*conversation" src/api/external_schemas.py
# deprecated 주석 외 0건

# 대화모드 전용 리소스 상수 제거 확인
grep -n "RESOURCE_CONVERSATION\|RESOURCE_MEMORY" src/api/backend_resources.py
# 0건이어야 함
```

### 7-7. 프롬프트 로딩 경로 검증

```bash
# 모든 에이전트의 프롬프트가 prompts/podcast/ 에서 로드되는지 확인
for agent in intent_classifier knowledge learning batch_validator content_analyzer \
  emotion podcast_reasoning safety script_generator script_personalizer visualization; do
  [ -f "prompts/podcast/${agent}.yaml" ] && echo "OK: ${agent}.yaml" || echo "FAIL: ${agent}.yaml 없음"
done

# knowledge.py에 "conversation" 하드코딩이 없는지 확인
grep -n '"conversation"' src/agents/podcast/knowledge.py
# 0건이어야 함
```

---

### 완료 기준 체크리스트

#### 필수 (전부 통과해야 완료)

| # | 기준 | 검증 명령 | 기대 결과 |
|---|------|---------|----------|
| 1 | 전체 테스트 통과 | `pytest tests/ -v` | 0 failed (backend connectivity 제외) |
| 2 | `src/agents/conversation/` 삭제 | `[ ! -d src/agents/conversation ]` | 디렉토리 없음 |
| 3 | `prompts/conversation/` 삭제 | `[ ! -d prompts/conversation ]` | 디렉토리 없음 |
| 4 | `prompts/shared/` 삭제 | `[ ! -d prompts/shared ]` | 디렉토리 없음 |
| 5 | workflow.py "conversation" 0건 | `grep "conversation" src/graph/workflow.py` | 0건 |
| 6 | settings.yaml "conversation" 0건 | `grep "conversation" config/settings.yaml` | 0건 |
| 7 | 에이전트 11개 전부 podcast/에 존재 | 위 for 루프 | 11개 OK |
| 8 | shared/에 인프라 코드만 존재 | 위 ls 검증 | 에이전트 파일 0개 |
| 9 | 그래프 컴파일 성공 | `compile_graph("unified")`, `compile_graph("podcast")` | 예외 없음 |
| 10 | conversation 빌더 제거 | `compile_graph("conversation")` | ValueError 발생 |
| 11 | telemetry_node 참조 제거 | `grep "telemetry_node" src/graph/workflow.py` | 0건 |
| 12 | _stub_node 함수 제거 | `grep "_stub_node" src/graph/workflow.py` | 0건 |
| 13 | conversation import 잔재 제거 | `grep "from src.agents.conversation" src/ tests/` | 0건 |
| 14 | learning import 경로 갱신 | `grep "from src.agents.shared.learning" src/ tests/` | 0건 |
| 15 | knowledge.py "conversation" 제거 | `grep '"conversation"' src/agents/podcast/knowledge.py` | 0건 |
| 16 | 프롬프트 11개 전부 podcast/에 존재 | 위 for 루프 | 11개 OK |
| 17 | API mode 기본값 podcast | `grep 'mode.*conversation' src/api/external_schemas.py` | deprecated 주석 외 0건 |
| 18 | 대화 리소스 상수 제거 | `grep 'RESOURCE_CONVERSATION' src/api/backend_resources.py` | 0건 |

#### 참고 (필수는 아니지만 확인)

| # | 기준 | 비고 |
|---|------|------|
| A | CLAUDE.md에서 "대화모드 에이전트 13개" 문구 없음 | 문서 갱신 확인 |
| B | README.md에서 "듀얼모드" 문구 없음 | 문서 갱신 확인 |
| C | external_schemas.py 대화 전용 스키마 삭제 | ConversationRequest 등 6개 |
| D | docs/architecture/AGENT_ROLES.md 대화 에이전트 설명 삭제 | 문서 정리 |

---

*마지막 업데이트: 2026-03-31*

# CLAUDE.md - Mind-Log AI 프로젝트 가이드

## 프로젝트 개요

**Mind-Log**: 초개인화 AI 멘탈케어 & 시각화 플랫폼

사용자의 감정과 생각을 AI가 분석하여 개인화된 멘탈케어 서비스를 제공하고, 내면 상태를 시각적 이미지로 표현하는 플랫폼.

---

## 아키텍처 요약

### TIER 기반 파이프라인 (v5.0)

**TIER 기반 파이프라인**으로 팟캐스트 에이전트를 오케스트레이션한다. **Orchestrator 없이** 에이전트 간 메시지 프로토콜(v2.0)을 통해 직접 통신하는 구조.

```
TIER 0: Intent Classifier → 의도 분류 + 1차 위기 감지
TIER 1 (병렬 Fan-out): Safety + Emotion + Content Analyzer + Podcast Reasoning
TIER 2 (생성): Script Generator + Visualization (병렬)
TIER 3 (검증): Batch Validator (실패 시 TIER 2 재시도, 최대 2회)
TIER 4 (후처리): Script Personalizer
비동기: Learning Agent
```

### 핵심 설계 원칙

- **Orchestrator 제거**: 에이전트들이 메시지 프로토콜(v2.0)을 통해 직접 통신
- **TIER 기반 파이프라인**: 병렬 처리(Fan-out)와 순차 처리를 효율적으로 조합
- **CRISIS 선점**: Safety Agent의 위기 신호가 TIER 1 병렬 작업 전체를 취소하고 즉시 응답
- **Episode Memory/Knowledge 독립**: Podcast Reasoning Agent가 조건부로 호출하는 독립 에이전트

### 에이전트 구성 (11개 + Learning)

| # | 에이전트 | TIER | 모델 | 담당 개발자 |
|---|---------|------|------|------------|
| 01 | Intent Classifier | TIER 0 | Sonnet 3.7 | 개발자1 |
| 02 | Safety Agent | TIER 1 (병렬) | Sonnet 3.7 | 개발자2 |
| 03 | Emotion Agent | TIER 1 (병렬) | Haiku | 개발자2 |
| 04 | Content Analyzer | TIER 1 (병렬) | Haiku | 개발자3 |
| 05 | Podcast Reasoning | TIER 1 (병렬) | Sonnet 3.7 | 개발자3 |
| 06 | Episode Memory | 독립 (Reasoning 조건부) | Sonnet 3.5 | 개발자2 |
| 07 | Knowledge Agent | 독립 (Reasoning 조건부) | Sonnet 3.5 | 개발자1 |
| 08 | Script Generator | TIER 2 (병렬) | Haiku | 개발자1 |
| 09 | Visualization | TIER 2 (병렬) / 비동기 | Haiku | 개발자2 |
| 10 | Batch Validator | TIER 3 | Haiku | 개발자3 |
| 11 | Script Personalizer | TIER 4 | Sonnet 3.7 | 개발자1 |
| 부가 | Learning Agent | 비동기 후처리 | Sonnet 3.5 | 개발자3 |

### 파일 위치

모든 에이전트는 `src/agents/podcast/`에 위치한다.
공용 인프라(BaseAgent, LLMClient, PromptLoader 등)는 `src/agents/shared/`에 위치한다.

### 실행 흐름

```
사용자 입력
    ↓
TIER 0: Intent Classifier
    │ 모드 감지 + 의도 분류
    ↓
TIER 1 (병렬 Fan-out):
├─ Safety Agent (공용)
├─ Emotion Agent (공용)
├─ Content Analyzer
└─ Podcast Reasoning
      ├─ Episode Memory ← 조건부 호출 (독립 에이전트)
      └─ Knowledge Agent (공용) ← 조건부 호출 (독립 에이전트)
    ↓ (Fan-in)
TIER 2 (병렬): Script Generator + Visualization (커버 이미지)
    ↓
TIER 3: Batch Validator
    │ 품질 검증 (실패 시 TIER 2 재시도)
    ↓
TIER 4: Script Personalizer
    │ 톤/스타일 조정 + Safety 경고 톤
    ↓
팟캐스트 에피소드 출력
    ↓
비동기: Learning
```

### Safety CRISIS 선점 메커니즘

Safety의 CRISIS 판정은 **병렬 실행을 중단시키는 선점(preemption)**이다.

```
1. Intent Classifier → risk_flag = true (1차 감지)
2. TIER 1 병렬 시작: Safety, Emotion, Content Analyzer, Podcast Reasoning 동시 실행

3. Safety Agent 판정:
   ├── safe/warning → 정상 흐름 계속
   └── CRISIS →
       ■ CANCEL SIGNAL 발행
       ■ Emotion, Content Analyzer, Podcast Reasoning 실행 취소
       ■ Safety 심화 모드 진입
       ■ Safety이 직접 위기 응답 생성
       ■ Script Generator/Batch Validator/Script Personalizer 건너뜀
       ■ 위기 응답 즉시 출력

Safety 상태별 흐름:
  safe    → TIER 1~4 정상 완료
  warning → TIER 1~4 정상 완료 → Personalization에서 톤 조정
  crisis  → ■ TIER 1 중단 → Safety 심화 → 즉시 위기 응답
```

---

## 개발자 협업 규칙

### 개발자별 담당 영역

| 개발자 | 브랜치 접두사 | 담당 에이전트 |
|--------|-------------|-------------|
| **개발자1** | `feature/analysis-*` | Intent Classifier, Knowledge, Script Generator, Script Personalizer |
| **개발자2** | `feature/reasoning-*` | Safety, Emotion, Visualization, Episode Memory |
| **개발자3** | `feature/validation-*` | Podcast Reasoning, Content Analyzer, Batch Validator, Learning |

### 브랜치 전략

```
main ← PR 머지 (3명 전원 승인 필수)
 └── develop ← 통합 테스트 브랜치 (최소 1명 리뷰)
      ├── feature/analysis-*     (개발자1)
      ├── feature/reasoning-*    (개발자2)
      └── feature/validation-*   (개발자3)
```

**규칙:**
- 각 개발자는 자기 도메인 브랜치에서만 작업한다
- `develop`에 머지할 때 최소 1명 이상의 다른 개발자 리뷰 필수
- `main`에 머지할 때 3명 전원 승인 필수
- 공용 파일(AgentState, 메시지 프로토콜 등) 수정 시 **반드시 전원 리뷰**

### 수정 불가 영역 (Protected Files)

아래 파일은 단독 수정 금지. 반드시 3인 합의 후 수정:

- `src/models/agent_state.py` — 공유 상태 스키마
- `src/models/message.py` — 에이전트 간 메시지 포맷
- `src/api/contracts.py` — 백엔드 API 요청/응답 스키마
- `src/graph/workflow.py` — LangGraph 워크플로우 정의

### 공용 인프라 (Shared Infrastructure — 인터페이스 변경 금지)

아래 파일은 모든 에이전트가 의존하는 공용 코드이다.
**기존 public 메서드의 시그니처(파라미터, 반환 타입)와 동작을 변경하지 마시오.**
신규 메서드/함수 추가만 허용한다. 수정 후 반드시 전체 테스트(`pytest tests/ -v`) 통과를 확인한다.

- `src/agents/shared/base_agent.py` — 에이전트 공통 부모 클래스 (BaseAgent ABC)
- `src/agents/shared/llm_client.py` — LLM 멀티 프로바이더 클라이언트
- `src/agents/shared/prompt_loader.py` — YAML 프롬프트 로더
- `config/loader.py` — 설정 로더 (Settings 싱글톤)

---

## 에이전트 간 입출력 규약

### AgentState (공유 상태)

모든 에이전트는 하나의 `AgentState`를 읽고 쓴다. 각 에이전트는 **자기 담당 필드만 쓰고**, 다른 에이전트 필드는 읽기만 한다.

```python
class AgentState(TypedDict, total=False):
    # total=False: 모든 필드가 선택적. 에이전트는 변경한 필드만 반환하고,
    # LangGraph가 기존 상태에 병합(merge)한다.

    # === 입력 (Intent Classifier가 설정) ===
    user_input: str
    user_id: str
    session_id: str
    mode: Literal["podcast"]

    # === 분석 필드 ===
    intent: dict              # Intent Classifier → 의도 분류 결과
    emotion_vectors: dict     # Emotion → 감정 벡터
    content_analysis: dict    # Content Analyzer → 팟캐스트 주제 분석

    # === 추론/생성 필드 ===
    memory_results: dict      # Episode Memory → 기억 검색 결과
    knowledge_results: dict   # Knowledge → 전문 지식 검색 결과
    reasoning_result: dict    # Podcast Reasoning → GoT/ToT/CoT 추론 결과
    script_draft: dict        # Script Generator → 팟캐스트 스크립트

    # === 검증/부가 필드 ===
    risk_level: int           # Safety → 위험 레벨 (0-4)
    risk_score: float         # Safety → Risk Score (0.0-1.0)
    safety_flags: dict        # Safety → 안전 플래그
    validation_result: dict   # Batch Validator → 검증 결과
    final_output: str         # Script Personalizer → 최종 응답
    visual_data: dict         # Visualization → 시각화 메타데이터

    # === 제어 ===
    next_step: str            # 워크플로우 라우팅 플래그
    execution_plan: dict      # Intent Classifier가 결정한 실행 계획
    iteration_count: int      # 피드백 루프 카운터 (최대 2회 재시도)
```

### 필드 접근 규칙

| 개발자 | 쓰기 가능 필드 | 읽기 가능 필드 |
|--------|--------------|--------------|
| 개발자1 | intent, knowledge_results, final_output, script_draft | user_input, user_id, session_id, mode |
| 개발자2 | emotion_vectors, risk_level, risk_score, safety_flags, memory_results, visual_data | 개발자1 쓰기 필드 + 개발자1 읽기 필드 |
| 개발자3 | content_analysis, reasoning_result, validation_result | 전체 필드 읽기 가능 |

> **예외**: Intent Classifier(개발자1)는 TIER 0에서 1차 위기 감지를 위해
> risk_level, risk_score, safety_flags를 초기 설정한다.
> Safety Agent(개발자2)가 TIER 1에서 이 값을 최종 덮어쓴다. (이슈 S-1)

> **설정 참조**: 에이전트별 런타임 설정값(임계값, 토큰 예산, 타임아웃 등)은
> `config/settings.yaml`이 단일 진실 소스(SSOT)이다.
> 코드의 기본값은 settings.yaml 미설정 시 폴백용이며, 운영 환경에서는 settings.yaml 값이 우선한다.

### 에이전트 간 메시지 포맷 (v2.0)

에이전트 간 통신은 **통합 메시지 엔벨로프 v2.0**을 사용한다:

```json
{
  "schema_version": "agents.protocol.v2",
  "message_id": "msg_{uuid}",
  "request_id": "req_{uuid}",
  "timestamp": "2026-02-10T14:30:00.123Z",

  "sender": "{agent_name}",
  "receiver": "{agent_name}",
  "message_type": "request | response | event | cancel | error",

  "payload": { },

  "metadata": {
    "session_id": "sess_{uuid}",
    "correlation_id": "corr_{uuid}",
    "trace_id": "trace_{uuid}",
    "mode": "podcast",
    "interaction_unit": "episode",
    "tier": 0,
    "priority": 1,
    "retry_count": 0
  },

  "audit": {
    "agent_version": "1.0.0",
    "processing_time_ms": 120,
    "llm_calls": 1,
    "status": "ok | error | partial"
  },

  "errors": []
}
```

**메시지 타입:** request(작업 요청), response(결과 전달), event(비동기 이벤트), cancel(CRISIS 취소), error(실패 알림)

**priority 레벨:** 0=CRITICAL (Safety CRISIS), 1=HIGH (일반 파이프라인), 2=NORMAL (비동기), 3=LOW (학습/텔레메트리)

---

## 백엔드 API 규약

### 서버 아키텍처

```
Frontend (app-4:3000) → Backend 서버 (app-3:8080) ↔ AI 서버 (app-2:8000)
                                    ↓
                                   DB
```

| 서버 | 역할 | 포트 |
|------|------|------|
| AI 서버 | LLM 파이프라인 실행, Backend 서버 전용 API 제공 | 8000 |
| Backend 서버 | 데이터 영속화 (MySQL), 조회, 프론트엔드 API 제공 | 8080 |

- 프론트엔드는 **Backend 서버에만** 접속한다. AI 서버와 직접 통신하지 않는다.
- AI 서버와 양방향 통신하는 서버는 **오직 Backend 서버** 하나뿐이다.
- Backend 서버가 프론트엔드 요청을 받아 AI 서버에 전달하고, 결과를 프론트엔드에 반환한다.
- Save/Load API는 AI → Backend 내부 통신이다 (`BackendClient` 경유).
- Backend 서버 API 계약서: `docs/architecture/API_SPEC.md` (v2.0, 5개 문서 모음)

백엔드 서버와는 REST API + JSON으로 통신한다. API 스키마는 `src/api/contracts.py`에 정의되어 있으며, 리소스 경로/타입 상수는 `src/api/backend_resources.py`에서 관리한다.

### 저장 API (Save)

```
POST /api/v1/{resource}
Content-Type: application/json

요청 예시:
{
  "user_id": "uuid",
  "session_id": "uuid",
  "type": "podcast_episode | emotion_log | visualization | learning",
  "data": { ... },
  "timestamp": "2026-02-10T12:00:00Z"
}

응답:
{
  "success": true,
  "id": "uuid",
  "message": "saved"
}
```

### 조회 API (Load)

```
GET /api/v1/{resource}?user_id={uuid}&type={type}&limit={n}
Content-Type: application/json

응답:
{
  "success": true,
  "data": [ ... ],
  "total": 10,
  "page": 1
}
```

### 에러 응답 (공통)

```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND | VALIDATION_ERROR | SERVER_ERROR",
    "message": "상세 에러 메시지"
  }
}
```

### API 연동 원칙

- 모든 API 호출은 `src/api/` 모듈을 통해서만 한다 (직접 HTTP 호출 금지)
- API 스키마 변경은 백엔드 팀과 합의 후 `src/api/contracts.py`에 반영
- 리소스 경로 상수: `src/api/backend_resources.py` (RESOURCE_* 상수)
- Save 타입 상수: `src/api/backend_resources.py` (TYPE_* 상수)
- 타임아웃: 기본 5초, LLM 관련 30초 (config `api.timeout`, `api.llm_timeout`)
- Backend URL 기본값: `http://localhost:8080/api/v1` (`BACKEND_API_URL` 환경변수로 오버라이드)
- 실패 시 최대 3회 재시도 (exponential backoff)
- 활성 리소스: learning, podcast_episodes, content_analyses, emotion_logs, visualizations
- 세션 리소스: sessions (`TODO(backend)` — 백엔드 팀 협의 필요)
- 저장 모드(`config/settings.yaml`의 `storage.mode`): `local` | `proxy`(기본) | `hybrid`

---

## LangGraph 워크플로우

### 노드 등록 규칙

각 개발자가 만든 에이전트는 LangGraph의 노드로 등록된다. 노드 등록은 `src/graph/workflow.py`에서 통합한다.

```python
# 각 개발자는 자기 에이전트를 함수로 구현
# src/agents/podcast/intent_classifier.py → intent_classifier_node(state) -> dict[str, Any]
# src/agents/podcast/safety.py → safety_node(state) -> dict[str, Any]

# workflow.py에서 통합 (3인 합의 영역)
# v4.0: TIER 기반 + 모드별 확장 (UnifiedStateGraph)
graph = StateGraph(AgentState)

# TIER 0
graph.add_node("intent_classifier", intent_classifier_node)  # 개발자1

# TIER 1 (병렬 Fan-out)
graph.add_node("safety", safety_node)                        # 개발자2
graph.add_node("emotion", emotion_node)                      # 개발자2
graph.add_node("content_analyzer", content_analyzer_node)    # 개발자3
graph.add_node("podcast_reasoning", podcast_reasoning_node)  # 개발자3
# Episode Memory/Knowledge는 독립 에이전트 — Podcast Reasoning 내부에서 조건부 호출

# TIER 2
graph.add_node("script_generator", script_generator_node)    # 개발자1
graph.add_node("visualization", visualization_node)          # 개발자2

# TIER 3
graph.add_node("batch_validator", batch_validator_node)      # 개발자3

# TIER 4
graph.add_node("script_personalizer", script_personalizer_node)  # 개발자1

# ... 팟캐스트모드 노드, 조건부 엣지, 병렬 그룹 설정
```

### 노드 인터페이스 규칙

모든 에이전트 노드는 동일한 시그니처를 따른다. **노드 함수 내부에서 에이전트를 새로 생성**하여
동시 요청 간 상태를 격리한다. 모듈 레벨 싱글톤으로 에이전트를 생성하지 마시오.

```python
async def agent_node(state: AgentState) -> dict[str, Any]:
    """요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = SomeAgent()          # 요청별 인스턴스 생성
    return await agent(state)    # __call__ 또는 .process() 사용
    # LangGraph가 반환된 dict를 기존 상태에 자동 병합
```

### Memory/Knowledge 독립 에이전트 패턴

Memory와 Knowledge는 StateGraph 노드가 아닌 **독립 에이전트**로, Reasoning Agent가 조건부로 호출한다:

```python
class ReasoningAgent:
    def __init__(self, memory_agent: MemoryAgent, knowledge_agent: KnowledgeAgent):
        self.memory_agent = memory_agent      # 의존성 주입
        self.knowledge_agent = knowledge_agent

    async def run(self, user_input, intent_metadata, complexity_score):
        # 1단계: 추론 그래프 구축 (사용자 발화만으로)
        graph = await self.build_reasoning_graph(user_input, complexity_score)

        # 2단계: 필요 판단 후 독립 에이전트 호출
        memory_result = None
        knowledge_result = None

        if graph.needs_personal_context:
            memory_result = await self.memory_agent.search(query=graph.memory_query)

        if graph.needs_expert_knowledge:
            knowledge_result = await self.knowledge_agent.search(query=graph.knowledge_query)

        # 3단계: 통합 추론
        return await self.synthesize_reasoning(graph, memory_result, knowledge_result)
```

---

## 코딩 컨벤션

- **Python 3.11+**, 타입 힌팅 필수
- **포맷터**: Black + isort
- **린터**: Ruff + mypy
- **테스트**: pytest + pytest-asyncio
- **네이밍**: 에이전트 클래스 `{Name}Agent`, 노드 함수 `{name}_node`, 상태 키 `snake_case`
- **커밋**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:` 접두사 사용

---

## 프롬프트 관리

에이전트 프롬프트는 `prompts/` 디렉토리의 YAML 파일로 관리하며, 멀티버전 형식을 지원한다.
`config/settings.yaml`의 `prompts.versions` 섹션에서 에이전트별 사용 버전을 핀닝한다.

현재 핀닝 (2026-03-13 최종 확정, Round 4):
- Content Analyzer: v2.1.0 / Podcast Reasoning: v3.1.0 / Batch Validator: v2.3.0

상세: `docs/guides/PROMPT_VERSIONING.md`

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| LLM | Anthropic Claude (Opus 4.6, Sonnet 4, Haiku) / AWS Bedrock / OpenAI / Ollama(개발용) |
| 오케스트레이션 | LangGraph StateGraph (TIER 기반 파이프라인) |
| 벡터 DB | Pinecone |
| 관계형 DB | MySQL |
| 그래프 DB | Neo4j |
| 이미지 저장 | S3 / CDN |
| 프레임워크 | FastAPI + Uvicorn |
| CI/CD | GitHub Actions |

---

## 구현 현황 (2026-04-07 기준)

| 구분 | 구현 에이전트 | 진행률 |
|------|------------|--------|
| **TIER 0-4** | Intent Classifier, Safety, Emotion, Content Analyzer, Podcast Reasoning, Script Generator, Visualization, Batch Validator, Script Personalizer | 9/9 |
| **독립** | Episode Memory, Knowledge | 2/2 |
| **비동기** | Learning Agent | 1/1 |

> **메시지 프로토콜 v2.0 현황**: `BaseAgent.create_message()`로 `MessageEnvelope` 생성이 가능하나,
> 현재 독립 에이전트 호출은 DI 패턴(직접 메서드 호출)으로 구현되어 엔벨로프가 미사용 상태이다.
> 백엔드 통신 확장 시 활성화를 검토한다.

### 인프라 강화 (PR #52~#61)

| 구분 | 내용 | PR |
|------|------|-----|
| 타입 힌트 현대화 | Dict→dict, Optional→\|None, mypy 63→0 에러 | #52 |
| 보안 강화 | 프롬프트 인젝션 방어, PII 정제, 민감정보 제거 | #58, #59 |
| 파이프라인 견고성 | 13개 취약점 수정, TIER 0~4 타임아웃, fallback 추가 | #60 |
| 독스트링 품질 | Google-style 통일, docstring 오류 수정 | #61 |
| 테스트 보강 | Circuit Breaker 9개 + SSE 스트리밍 11개 테스트 | #61 |
| Neo4j 통합 | GoT→Neo4j 저장, 그래프 API, 누적 그래프, Mode B 단일화 | #50, #51, #53, #69 |

### 테스트 현황

```
532 passed
```

---

## 참고 문서

### 프로젝트 문서 (저장소 내)

- `docs/getting-started/QUICK_START.md` — 환경 설정 및 빠른 시작
- `docs/architecture/AGENT_ROLES.md` — 에이전트별 역할·입출력·이슈 정의서
- `docs/architecture/NEO4J_INTEGRATION.md` — Neo4j 그래프 DB 통합 명세 (v1.3)
- `docs/guides/PROMPT_VERSIONING.md` — 프롬프트 멀티버전 관리 가이드

### 설계 원본 (저장소 외부 — 임의 수정 금지)

> 아래 문서는 프로젝트 설계 원본으로, 저장소에 포함되지 않는다.

- ProjectDocs/INDEX.md — 마스터 인덱스 (20개 에이전트 전체)
- ProjectDocs/ARCHITECTURE_v4.0.md — v4.0 아키텍처 확정 명세
- ProjectDocs/ARCHITECTURE_REDESIGN_v4.0.md — v4.0 재설계 과정 및 상세
- ProjectDocs/AGENTS_INDEX.md — 에이전트 통합 인덱스 v2.0
- ProjectDocs/AGENT_MESSAGE_PROTOCOL_v2.0.md — 통합 메시지 프로토콜 v2.0

---

*마지막 업데이트: 2026-04-07*

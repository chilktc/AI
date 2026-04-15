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
| 01 | Intent Classifier | TIER 0 | Haiku | 개발자1 |
| 02 | Safety Agent | TIER 1 (병렬) | Sonnet | 개발자2 |
| 03 | Emotion Agent | TIER 1 (병렬) | Haiku | 개발자2 |
| 04 | Content Analyzer | TIER 1 (병렬) | Haiku | 개발자3 |
| 05 | Podcast Reasoning | TIER 1 (병렬) | Sonnet | 개발자3 |
| 06 | Episode Memory | 독립 (Reasoning 조건부) | Sonnet | 개발자2 |
| 07 | Knowledge Agent | 독립 (Reasoning 조건부) | Sonnet | 개발자1 |
| 08 | Script Generator | TIER 2 (병렬) | Haiku | 개발자1 |
| 09 | Visualization | TIER 2 (병렬) / 비동기 | Haiku | 개발자2 |
| 10 | Batch Validator | TIER 3 | Haiku | 개발자3 |
| 11 | Script Personalizer | TIER 4 | Sonnet | 개발자1 |
| 부가 | Learning Agent | 비동기 후처리 | Sonnet | 개발자3 |

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

- **safe** → TIER 1~4 정상 완료
- **warning** → TIER 1~4 정상 완료 → Personalization에서 톤 조정
- **crisis** → TIER 1 중단 → Safety 심화 → 즉시 위기 응답 (CANCEL SIGNAL 발행)

> 상세 흐름: `docs/architecture/AGENT_ROLES.md` Safety Agent 섹션 참조

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

- `src/agents/shared/base_agent.py` — 에이전트 공통 부모 클래스 (BaseAgent ABC, `get_fallback_output()` 선택적 메서드 포함)
- `src/agents/shared/llm_client.py` — LLM 멀티 프로바이더 클라이언트
- `src/agents/shared/prompt_loader.py` — YAML 프롬프트 로더
- `src/agents/shared/input_sanitizer.py` — 프롬프트 인젝션 방어 (입력 정제)
- `src/agents/shared/output_sanitizer.py` — PII 정제 (출력 마스킹)
- `config/loader.py` — 설정 로더 (Settings 싱글톤)

---

## 에이전트 간 입출력 규약

### AgentState (공유 상태)

모든 에이전트는 하나의 `AgentState`를 읽고 쓴다. 각 에이전트는 **자기 담당 필드만 쓰고**, 다른 에이전트 필드는 읽기만 한다.

- 정의: `src/models/agent_state.py` (TypedDict, total=False — 26개 필드)
- 전체 필드 명세: `docs/architecture/AGENT_OUTPUT_CONTRACT.md`
- 입출력 예시: `docs/architecture/AGENT_INPUT_OUTPUT.md`

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

에이전트 간 통신은 **통합 메시지 엔벨로프 v2.0**을 사용한다. 정의: `src/models/message.py`

- **메시지 타입**: request / response / event / cancel / error
- **priority**: 0=CRITICAL (Safety CRISIS), 1=HIGH (일반), 2=NORMAL (비동기), 3=LOW (학습)
- 전체 스키마: 설계 원본 `AGENT_MESSAGE_PROTOCOL_v2.0.md` 참조

> 현재 독립 에이전트 호출은 DI 패턴(직접 메서드 호출)으로 구현되어 엔벨로프 미사용 상태.

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

### API 엔드포인트

- Save: `POST /greenroom/ingest/ai/{resource}` — 상세: `docs/architecture/API_ENDPOINTS_INTERNAL.md`
- Load: `GET /greenroom/ingest/ai/{resource}?user_id={uuid}&type={type}&limit={n}`
- 에러/재시도: `docs/architecture/API_COMMON.md`
- 전체 API 명세: `docs/architecture/API_SPEC.md` (v2.0, 5개 문서 모음)

### API 연동 원칙

- 모든 API 호출은 `src/api/` 모듈을 통해서만 한다 (직접 HTTP 호출 금지)
- API 스키마 변경은 백엔드 팀과 합의 후 `src/api/contracts.py`에 반영
- 리소스 경로 상수: `src/api/backend_resources.py` (RESOURCE_* 상수)
- Save 타입 상수: `src/api/backend_resources.py` (TYPE_* 상수)
- 타임아웃: 기본 10초, LLM 관련 60초 (config `api.timeout`, `api.llm_timeout`)
- Backend URL 기본값: `http://localhost:8080/greenroom/ingest/ai` (`BACKEND_API_URL` 환경변수로 오버라이드)
- 실패 시 최대 3회 재시도 (exponential backoff)
- 활성 리소스 (SaveRequest 경유): podcast_metadata, content_analyses, emotion_logs, visualizations, learning
- 수집 API (직접 전송, SaveRequest 미사용): podcast_episodes, tickets/mind-frequencies
- 세션 리소스: sessions (`TODO(backend)` — 백엔드 팀 협의 필요)
- 저장 모드(`config/settings.yaml`의 `storage.mode`): `local` | `proxy`(기본) | `hybrid`

---

## LangGraph 워크플로우

### 노드 등록 규칙

- 노드 등록: `src/graph/workflow.py`에서 통합 (3인 합의 영역, Protected File)
- 에이전트별 노드 매핑: `docs/architecture/AGENT_ROLES.md` 참조

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

Memory와 Knowledge는 StateGraph 노드가 아닌 **독립 에이전트**로, Reasoning Agent가 조건부로 DI 호출한다.
구현: `src/agents/podcast/podcast_reasoning.py` / 가이드: `docs/guides/AGENT_DEV_GUIDE.md`

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

현재 핀닝 (2026-04-14 settings.yaml 동기화):
- Content Analyzer: v2.2.0 / Podcast Reasoning: v3.2.0 / Batch Validator: v2.3.0 / Visualization: v1.19.0

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

## 구현 현황 (2026-04-15 기준)

| 구분 | 구현 에이전트 | 진행률 |
|------|------------|--------|
| **TIER 0-4** | Intent Classifier, Safety, Emotion, Content Analyzer, Podcast Reasoning, Script Generator, Visualization, Batch Validator, Script Personalizer | 9/9 |
| **독립** | Episode Memory, Knowledge | 2/2 |
| **비동기** | Learning Agent | 1/1 |

> **메시지 프로토콜 v2.0 현황**: `BaseAgent.create_message()`로 `MessageEnvelope` 생성이 가능하나,
> 현재 독립 에이전트 호출은 DI 패턴(직접 메서드 호출)으로 구현되어 엔벨로프가 미사용 상태이다.
> 백엔드 통신 확장 시 활성화를 검토한다.

### 인프라 강화 (PR #52~#143)

| 구분 | 내용 | PR |
|------|------|-----|
| 타입 힌트 현대화 | Dict→dict, Optional→\|None, mypy 63→0 에러 | #52 |
| 보안 강화 | 프롬프트 인젝션 방어, PII 정제, 민감정보 제거 | #58, #59 |
| 파이프라인 견고성 | 13개 취약점 수정, TIER 0~4 타임아웃, fallback 추가 | #60 |
| 독스트링 품질 | Google-style 통일, docstring 오류 수정 | #61 |
| 테스트 보강 | Circuit Breaker 9개 + SSE 스트리밍 11개 테스트 | #61 |
| Neo4j 통합 | GoT→Neo4j 저장, 그래프 API, 누적 그래프, Mode B 단일화 | #50, #51, #53, #69 |
| Pinecone 인프라 | PineconeClient, CLI 스크립트 3종, 테스트 59개 | #64~#68 |
| 에이전트 출력 감사 | 7 Task 전체 완료 (SA/EA/CA/SG/VI/BV/횡단) | develop 직접 |
| Stories 수신 인프라 | asyncio.Event 대기 + TIER 4 wait_for_stories_node | #110 |
| 로그 시스템 통일 | logging.getLogger→get_agent_logger 18개 파일, JSON 포맷 통일 | #112, #113 |
| CRISIS-타임아웃 수정 | 로그 구분, 경합 방지, TIER 1 타임아웃 240s | #114 |
| TIER 타임아웃 확장 | TIER 0/4/비동기 타임아웃 2배 확장, Bedrock throttling 로그 | #116 |
| S3 ACL 추가 | Visualization put_object에 ACL="public-read" 추가 | #117 |
| Bedrock 지연 추적 | LLM 호출 구간별 타이밍 로깅, LangSmith 메타데이터 연동 | #131, #135, #136 |
| BV score 보정 | Batch Validator score/decision LLM hallucination 방지 | #132 |
| Visualization 안정화 | Titan 콘텐츠 차단 방어, JSON 파싱 fallback, ContentBlockedError 전환 | #133, #138, #139 |
| 모델 다운그레이드 | sonnet_37 APAC 지연 급증 대응, Haiku/Sonnet 전환 | #137 |
| Episode Memory 개선 | phase별 컨텍스트 주입 (GoT/ToT/CoT 분리) | #134 |
| CancelledError 수정 | HTTP 연결 종료 시 스택 트레이스 제거 | #140 |
| 구조적 취약점 수정 | CI/CD Job 의존성, lint 순서, SHA 태깅, 롤백 스크립트, 한국어 인젝션 패턴, 취소 태스크 정리 등 16건 | #142 |
| deploy.yml SSM 배포 신뢰성 강화 | SSM 싱글쿼트 파싱 오류 수정, 15초×40회 폴링 교체, unhealthy 즉시 실패 감지 | #143 |
| Knowledge RAG 1차 구현 | KT Cloud RAG Suite 연동 (Parser/Embedding/TextGen), scripts/ingest_knowledge.py | #145 |
| Knowledge Agent 리팩터링 | Pinecone 임계값 외부화(settings.yaml), try/except 세분화, 에러 흐름 로깅 강화 | #146 |
| KnowledgeAgentStub 정식 제거 | podcast_reasoning.py에서 실제 KnowledgeAgent로 fallback 전환, shared/stubs.py에서 Stub 클래스 제거 | #147 |
| Knowledge RAG env 회귀 수정 | PARSER→PARSE 네이밍 정렬, PASSAGE Embedding env 주입 복원, GitHub Secrets 정합 | #148, #149, #150 |
| Knowledge RAG 파이프라인 연결 | Reasoning phase별 주입(ToT/CoT), ScriptGenerator state 키 정합, Pinecone 관측성/top_k 외부화 | #151 |
| 호스트 페르소나 8종 연동 | 8종 호스트 페르소나 script_personalizer 연동 + Python 3.9 하위 호환성 강화 | #152 |
| Pinecone 인덱스명 통일 | rag-suite-knowledge 단일 인덱스명 통일 (코드·config·테스트·문서 전체) | #153 |
| Knowledge Pinecone 임계값 조정 | 임계값 0.7→0.25 (KT Cloud Query↔Passage 실측 score 0.20~0.35 반영) | #155 |
| Knowledge Backend API URL 수정 | BackendClient._knowledge_base_url 도입, /api/internal/knowledge 엔드포인트 분리 | #156, #157 |
| Knowledge search() 정리 | Parser 단계 제거 (텍스트 쿼리에 불필요), F821 lint 수정 | #158 |
| CRISIS 파이프라인 출력 정상화 | TIER 1 cancel_event 제거, TIER 2~4 LLM 폴백 하드코딩, StoriesStore 정리 | #159 |

### 테스트 현황

```
612 passed
```
*594 → 612: CRISIS 폴백 단위 테스트 18건 추가 (#159, 2026-04-15)*

---

## 참고 문서

### 프로젝트 문서 (저장소 내)

- `docs/getting-started/QUICK_START.md` — 환경 설정 및 빠른 시작
- `docs/architecture/AGENT_ROLES.md` — 에이전트별 역할·입출력·이슈 정의서
- `docs/architecture/NEO4J_INTEGRATION.md` — Neo4j 그래프 DB 통합 명세 (v1.3)
- `docs/architecture/VECTOR_DB_RAG_GUIDE.md` — Pinecone 벡터 DB + RAG 가이드
- `docs/guides/PROMPT_VERSIONING.md` — 프롬프트 멀티버전 관리 가이드
- `docs/reports/SECURITY_REMEDIATION_TRACKER.md` — 보안 후속조치 추적 (키 로테이션, Secrets)

### 설계 원본 (저장소 외부 — 임의 수정 금지)

> 아래 문서는 프로젝트 설계 원본으로, 저장소에 포함되지 않는다.

- ProjectDocs/INDEX.md — 마스터 인덱스 (20개 에이전트 전체)
- ProjectDocs/ARCHITECTURE_v4.0.md — v4.0 아키텍처 확정 명세
- ProjectDocs/ARCHITECTURE_REDESIGN_v4.0.md — v4.0 재설계 과정 및 상세
- ProjectDocs/AGENTS_INDEX.md — 에이전트 통합 인덱스 v2.0
- ProjectDocs/AGENT_MESSAGE_PROTOCOL_v2.0.md — 통합 메시지 프로토콜 v2.0

---

*마지막 업데이트: 2026-04-15 17:30*

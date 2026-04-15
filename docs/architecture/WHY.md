# WHY — Mind-Log 설계 결정과 진화 이력

> 새 개발자를 위한 문서. "왜 이렇게 구현했는가"와 "왜 이것은 사라졌는가"를 설명한다.
>
> **읽는 순서**: README → CLAUDE.md → **이 문서** → 담당 에이전트 코드
>
> **업데이트 원칙**: 기능을 삭제하거나 설계를 바꿀 때 반드시 이 문서를 함께 수정한다.
> 단순 버그 수정이나 문서 오탈자는 여기에 기록하지 않는다.
>
> 마지막 업데이트: 2026-04-08

---

## 목차

1. [제거된 기능 (Graveyard)](#1-제거된-기능-graveyard)
2. [현재 유효한 설계 결정](#2-현재-유효한-설계-결정)
3. [보류/미결 결정](#3-보류미결-결정)
4. [채택하지 않은 대안 (Museum)](#4-채택하지-않은-대안-museum)

---

## 1. 제거된 기능 (Graveyard)

> 이 섹션에 있는 기능은 **의도적으로 삭제**되었다.
> 재도입을 검토하려면 "재도입 조건"을 먼저 읽어라.

---

### 1-A. 대화모드 (Conversation Mode)

**상태**: 2026-03-31 완전 삭제 (PR #45, #48, #49, #61)

**삭제 전 상태**:
- `mode: Literal["conversation", "podcast"]` 듀얼 모드
- 대화모드 전용 에이전트 7개 (Context, Reasoning-대화, Synthesis, Validator-대화, Personalization, Telemetry, Memory-대화)
- `src/agents/conversation/` 디렉토리
- `prompts/conversation/` 12개 YAML 파일
- 대화모드 TIER 0~4 별도 파이프라인

**삭제 이유**:
1. 7개 에이전트 전부 stub 상태 — 실제 구현이 전혀 없는 코드였음
2. 팟캐스트 파이프라인 완성이 우선순위에서 앞섰음
3. stub 코드가 테스트와 타입 검사에서 노이즈를 발생시켰음
4. 유지보수 비용 대비 실현 가치 없음

**현재 영향**:
- `AgentState.mode`는 `Literal["podcast"]`만 허용
- `src/api/contracts.py`에서 대화 관련 스키마 삭제됨
- `config/settings.yaml`에서 `features.conversation_mode: false` 항목 삭제됨

**재도입 조건**:
팟캐스트 파이프라인이 프로덕션 안정화된 후, 별도 브랜치에서 `mode: Literal["conversation", "podcast"]`를 복원하는 방식으로 진행. 삭제된 에이전트 7개는 git 이력(`PR #45`)에서 복구 가능.

---

### 1-B. Graph Mode A (AI 서버 EMA 계산)

**상태**: 2026-04-07 삭제 (PR #69)

**삭제 전 상태**:
- AI 서버가 GoT(Graph of Thoughts) 결과 수신 후 EMA(지수이동평균) 직접 계산
- 기존 노드 조회(GET) → EMA 계산 → 갱신 전송(PUT) — 네트워크 2왕복
- 설정: `config/settings.yaml → graph.upsert_mode: "ai_server"`, `graph.ema_alpha: 0.3`
- 관련 함수 7개: `calc_ema()`, `calc_trend()`, `merge_nodes_from_got()`, `merge_edges_from_got()` 등
- 테스트 29개

**삭제 이유**:
1. AI 서버가 도메인 로직(EMA 계산)을 담당하면 Backend와 책임이 분산됨
2. GET → 계산 → PUT 3단계가 불필요한 네트워크 오버헤드 발생
3. Mode B(Backend UPSERT)가 AI 서버 부담 최소화 원칙에 부합
4. 두 모드 병렬 유지는 테스트·코드 복잡도를 2배로 키움

**현재 상태**:
- `src/api/graph_cumulative.py`: 7함수 → `publish_graph_to_rdb()` 단일 함수
- EMA 계산 책임: Backend 서버로 이관
- `config/loader.py`에서 `graph_upsert_mode`, `graph_ema_alpha` 프로퍼티 삭제됨
- `config/settings.yaml`에서 `graph:` 블록 삭제됨
- 테스트 29개 → 6개

**재도입 조건**:
Backend 팀이 EMA 계산을 구현할 수 없거나, AI 서버에서 실시간 가중치 피드백이 필요한 요구사항이 생길 경우. 설계 원본: `docs/_archive/specs/2026-04-06-graph-cumulative-rdb-design.md`

---

### 1-C. 모듈 레벨 싱글톤 에이전트

**상태**: 2026-03-30 제거 (v27, PR #38 기반)

**삭제 전 상태**:
```python
# workflow.py — 모듈 최상위
_intent_classifier = IntentClassifierAgent()
_safety_agent = SafetyAgent()
# ... 10개 에이전트 싱글톤
```
- `_llm_call_count`, `_last_input_snapshot` 등 mutable 상태가 전역 공유

**삭제 이유**:
1. 사용자 A의 요청 처리 중 상태가 사용자 B의 요청에 노출될 위험
2. 테스트 격리 불가 — 한 테스트의 부작용이 다른 테스트에 영향
3. `_current_ab_variant`(A/B 테스트 variant)가 동시 요청 간 섞이는 버그 발생 가능

**현재 상태**:
```python
async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    agent = IntentClassifierAgent()  # 요청마다 새 인스턴스
    return await agent(state)
```
- 인스턴스 생성 오버헤드: ~5-15ms (LLM 호출 수초 대비 무시 가능)
- `_active_ab_variant`: `contextvars.ContextVar`로 비동기 안전 격리

**재도입 금지**: 동시 요청이 1개라고 보장되지 않는 한 절대 싱글톤으로 되돌리면 안 됨.

---

### 1-D. Orchestrator 모듈

**상태**: v4.0 아키텍처 설계 시 미채택 (코드로 구현된 적 없음)

**검토 당시 개념**:
- 에이전트 간 메시지 라우팅을 담당하는 별도 중앙 조정 모듈

**미채택 이유**:
- LangGraph `StateGraph`가 노드 라우팅, 상태 병합, 조건부 엣지를 모두 제공
- 별도 Orchestrator는 StateGraph와 책임이 겹쳐 불필요한 레이어가 됨
- TIER 기반 파이프라인으로 역할 명확히 분리

**현재 구조**: `src/graph/workflow.py`의 `build_unified_graph()`가 오케스트레이션 역할 수행

---

### 1-E. AgentState.response_draft 필드

**상태**: 대화모드 삭제와 함께 영구 미사용 확정

**원래 목적**: Synthesis Agent(대화모드 TIER 2)가 최종 응답 초안을 저장하는 필드

**현재 상태**: `AgentState`에 필드 정의만 남아있으나 어떤 에이전트도 쓰지 않음. 대화모드 재도입 전까지 삭제 예정.

**참고**: `AgentState`는 protected file이므로 삭제 시 3인 합의 필요.

---

## 2. 현재 유효한 설계 결정

> 각 결정의 "재검토 조건"을 확인하고 함부로 변경하지 마라.

---

### 2-A. TIER 기반 파이프라인 (v5.0)

**결정**: TIER 0→1(병렬)→2(병렬)→3→4, 비동기 Learning 구조

**문제 상황**: 에이전트 11개를 어떤 순서와 병렬도로 실행할지 결정 필요. 순차 실행은 너무 느리고, 완전 병렬은 의존성 문제 발생.

**검토한 대안**:
- 완전 순차: 단순하지만 TIER 1 에이전트들(Safety, Emotion, Content Analyzer, Reasoning)을 병렬로 돌릴 기회를 버림
- 완전 병렬: Safety CRISIS 결과가 나오기 전에 다른 에이전트가 이미 LLM을 호출함 — 비용 낭비

**선택 이유**: TIER 1은 입력만 보면 되는 에이전트들이라 병렬 가능. TIER 2는 TIER 1 결과가 필요하므로 순차. Safety CRISIS 시 TIER 1 전체 취소로 비용 제어.

**재검토 조건**: 에이전트 수가 크게 늘거나(20+), TIER 간 의존성이 복잡해지면 재검토.

---

### 2-B. Safety CRISIS 선점(Preemption)

**결정**: Safety가 CRISIS 판정 시 TIER 1 나머지 에이전트를 즉시 취소하고 위기 응답만 전송

**문제 상황**: Safety가 TIER 1에서 병렬 실행되는데, CRISIS 판정 후에도 Emotion/Content Analyzer/Reasoning이 계속 실행되면 LLM 비용 낭비 + 부적절한 콘텐츠 생성 가능성

**선택 이유**: 멘탈케어 서비스 특성상 위기 상황에서 빠른 응답이 최우선. CRISIS 고정 메시지는 LLM 생성 없이 즉시 전송.

**고정 메시지 정책**: CRISIS 응답은 LLM이 생성하지 않음. 하드코딩된 안전 메시지만 사용. (자유 생성 시 예상치 못한 문구 위험)

**재검토 금지**: 위기 응답을 LLM으로 생성하는 방향으로 변경 시 반드시 안전팀 검토 필요.

---

### 2-C. 요청별 에이전트 인스턴스 생성

**결정**: 노드 함수 내부에서 매번 `agent = SomeAgent()` 생성

**선택 이유**: [1-C 참고] 동시 요청 간 상태 격리. 인스턴스 생성 비용(<15ms)은 LLM 호출(1~10초) 대비 무시 가능.

**예외 없음**: 성능 최적화를 이유로 싱글톤으로 되돌리지 말 것.

---

### 2-D. YAML 프롬프트 관리 + 5계층 보안

**결정**: 프롬프트를 코드가 아닌 `prompts/{mode}/{agent}.yaml`로 관리

**문제 상황**: 초기에는 Python 코드 안에 하드코딩 → 재배포 없이 프롬프트 수정 불가, 버전 관리 불가, A/B 테스트 불가

**현재 구조**:
- 멀티버전: `versions.v1.0.0`, `versions.v2.0.0` 공존
- 버전 핀닝: `config/settings.yaml → prompts.versions.{agent}`
- A/B 테스트: `prompts.ab_tests.{agent}` — 세션 기반 결정적 할당
- 5계층 보안: `safe_load` 강제, 경로 검증, 화이트리스트, 크기 제한, 스키마 검증

**`.gitignore` 정책**: `prompts/` 디렉토리는 기본 `.gitignore` 대상. 운영 YAML은 `git add -f`로 명시적 추적. 이유: 프롬프트는 경쟁 민감 정보.

**재검토 조건**: 프롬프트 파일 수가 50개를 넘거나 동적 생성 필요성이 생기면 데이터베이스 저장 방식 검토.

---

### 2-E. DI 패턴 — Memory/Knowledge 독립 에이전트

**결정**: Episode Memory와 Knowledge Agent는 StateGraph 노드가 아닌 DI(의존성 주입)로 Podcast Reasoning 내부에서 조건부 호출

**문제 상황**: 모든 에이전트를 노드로 등록하면 StateGraph가 항상 두 에이전트를 호출함 → 단순 입력에도 Pinecone 쿼리 발생 (비용·지연)

**현재 구조**:
```python
class PodcastReasoningAgent:
    def __init__(self, memory_agent, knowledge_agent):
        self.memory_agent = memory_agent  # DI
        self.knowledge_agent = knowledge_agent  # DI

    async def run(self, ...):
        if complexity_score > threshold:
            memory = await self.memory_agent.search(query)
        if needs_expert_knowledge:
            knowledge = await self.knowledge_agent.search(query)
```

**재검토 조건**: Memory/Knowledge가 다른 에이전트(Emotion 등)에서도 직접 호출되어야 한다면 MessageEnvelope v2.0 기반 이벤트 방식으로 전환 검토.

---

### 2-F. LLM 멀티 프로바이더

**결정**: Anthropic SDK, AWS Bedrock, OpenAI, 커스텀(Ollama) 4개 프로바이더 지원

**구현**: `src/agents/shared/llm_client.py` — `provider` 설정으로 분기, 외부 등록 지원(`register_provider()`)

**프로바이더별 사용처**:
- **Anthropic SDK**: 로컬 개발, API 키 있을 때
- **AWS Bedrock**: 프로덕션 (IAM Role 기반, 키 불필요)
- **OpenAI**: 프롬프트 이터레이션 테스트 (gpt-4o-mini로 빠른 검증)
- **Ollama**: 오프라인 개발, 비용 없이 파이프라인 구조 테스트

**Ollama 프로덕션 사용 금지**: 품질 편차가 크고 SLA 보장 불가. [4-B 참고]

---

### 2-G. json.loads strict=False

**결정**: LLM JSON 응답 파싱 시 `strict=False` 옵션 사용

**이유**: Ollama 등 로컬 모델이 JSON 응답에 제어 문자(`\n`, `\t` 리터럴)를 포함시키는 경우가 있음. `strict=True`이면 파싱 실패 → 폴백 출력 → 파이프라인 품질 저하.

**보안 고려**: `json.loads`는 코드 실행 위험 없음. `eval()`과 혼동하지 말 것.

---

### 2-H. 재시도 최대 2회

**결정**: Batch Validator 피드백 루프 최대 2회 (`iteration_count` ≤ 2)

**변경 이력**: 초기 계획서에는 3회 → v4.0 아키텍처 확정 시 2회로 축소

**이유**: 3회 모두 실패하는 케이스는 프롬프트 구조 문제이지 재시도로 해결될 문제가 아님. 무한 루프 방지 + LLM 비용 제어.

**재검토 조건**: 검증 통과율이 50% 이하로 떨어지면 재시도 횟수보다 Validator 프롬프트 개선을 먼저 검토.

---

### 2-I. MessageEnvelope v2.0 — 현재 부분 사용

**결정**: 에이전트 간 통신 포맷 정의 완료, 실제 사용은 보류

**현재 상태**: `BaseAgent.create_message()`로 `MessageEnvelope` 생성 가능하나, 실제 에이전트 호출은 DI 패턴(직접 메서드 호출)으로 구현 중 → 엔벨로프 미사용

**보류 이유**: DI 패턴이 더 단순하고, Backend와의 통신 확장 전까지 오버엔지니어링

**활성화 조건**: AI 서버 간 분산 처리, 또는 에이전트를 별도 서비스로 분리할 때.

---

## 3. 보류/미결 결정

> 아직 결정되지 않은 설계 질문들. 구현 전에 여기에 먼저 답해야 한다.

---

### 3-A. Telemetry 실시간 모니터링

**질문**: LLM 호출 비용, 파이프라인 지연, 사용자 행동을 어떻게 추적할 것인가?

**현재 상태**: LangSmith + Prometheus + `MindLogTelemetryCallback`으로 부분 충족. Telemetry 전담 에이전트 계획 있었으나 담당자 미정.

**결정 전 확인사항**: 어떤 메트릭을 실시간으로 볼 것인가 + 누가 담당하는가.

---

### 3-B. Frontend WebSocket 연동

**질문**: 팟캐스트 생성 진행률을 실시간 스트리밍으로 보내는 방식?

**현재 상태**: `/episodes/stream` SSE 엔드포인트 코드 구현 완료. Frontend 팀과 연동 미시작.

**결정 전 확인사항**: Frontend가 SSE를 쓸 것인가, WebSocket을 쓸 것인가.

---

### 3-C. 인증/인가 (Auth)

**질문**: AI 서버가 user_id를 신뢰하는 현재 구조가 맞는가?

**현재 상태**: AI 서버는 `user_id`를 검증 없이 신뢰. Backend 서버가 JWT/OAuth 담당.

**결정 전 확인사항**: Backend 팀과 인증 흐름 협의 필요.

---

### 3-D. Emotional Journey 형식 통일

**질문**: Emotion Agent, Script Personalizer, Learning Agent가 각각 다른 형식으로 감정을 표현 중. 통일할 것인가?

**현재 상태**: 3개 에이전트가 독립적으로 감정 표현 형식 사용.

**영향 범위**: 통일 시 3개 에이전트 프롬프트 + 코드 동시 변경 필요 + LLM 재테스트.

---

### 3-E. AgentState.response_draft 필드 삭제

**질문**: 대화모드 삭제로 영구 미사용 확정된 `response_draft` 필드를 `AgentState`에서 삭제할 것인가?

**현재 상태**: 필드 정의만 남아있음, 어떤 에이전트도 쓰지 않음.

**결정 전 확인사항**: `AgentState`는 protected file → 3인 합의 필요.

---

## 4. 채택하지 않은 대안 (Museum)

> 한 번 탈락한 대안이 왜 탈락했는지를 기억해야 같은 논의를 반복하지 않는다.

---

### 4-A. PostgreSQL

**검토**: 초기 계획에서 관계형 DB 후보

**탈락 이유**: MySQL이 팀 운영 환경(KT Cloud, AWS RDS)과 더 잘 맞고, 설정 비용 낮음

**재검토 조건**: PostGIS(지리 정보), JSONB 고급 쿼리가 필요해지면 재검토 가능.

---

### 4-B. Ollama 프로덕션 사용

**검토**: 로컬 LLM을 프로덕션 LLM으로 활용해 API 비용 절감

**탈락 이유**:
- Round 1~3 이터레이션 결과: 같은 프롬프트에서 BV Score 표준편차 0.047 (불안정)
- `depth_level` 같은 enum 필드에서 지시를 무시하고 임의 값 출력
- 예시 값을 그대로 복사하는 경향 (confidence: 0.90 예시 → 항상 0.90 출력)
- 프로덕션 SLA 보장 불가

**현재 사용처**: 오프라인 개발, 파이프라인 구조 검증 (품질 무관한 작업)만 허용.

---

### 4-C. GraphQL

**검토**: Frontend와의 API 레이어로 GraphQL 고려

**탈락 이유**: 팟캐스트 에피소드 생성 API는 단순 Request/Response 구조. GraphQL의 복잡성(스키마 정의, resolver, N+1 문제)이 이 프로젝트에서 오버엔지니어링.

**재검토 조건**: Frontend가 복잡한 쿼리 조합(에피소드+감정+시각화 동시 조회)이 필요해질 때.

---

### 4-D. 3회 재시도

**검토**: Batch Validator 피드백 루프 3회

**탈락 이유**: [2-H 참고] 3회 실패는 재시도 문제가 아니라 프롬프트 구조 문제. 비용 대비 효과 없음.

---

### 4-E. MessageEnvelope 전면 도입 (초기 단계)

**검토**: 모든 에이전트 간 통신을 MessageEnvelope v2.0으로 강제

**보류 이유**: 현재 에이전트는 모두 단일 프로세스 내에서 실행. 직접 메서드 호출이 더 빠르고 단순. 분산 처리가 필요한 시점에 도입.

---

*이 문서는 설계 판단이 바뀔 때마다 갱신한다. "이건 왜 이렇게 됐지?"라는 질문의 첫 번째 답이 여기 있어야 한다.*

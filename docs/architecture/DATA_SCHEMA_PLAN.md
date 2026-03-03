# Mind-Log 데이터 스키마 계획서

> **작성일**: 2026-03-03
> **버전**: v3.0 (영속화 아키텍처 재설계)
> **상태**: 초안 (3인 리뷰 필요)

---

## 목차

1. [v2.0 문제점 분석](#1-v20-문제점-분석)
2. [검토한 접근법 7가지 비교](#2-검토한-접근법-7가지-비교)
3. [안 A — 이벤트 드리븐 영속화](#3-안-a--이벤트-드리븐-영속화)
4. [안 B — 하이브리드 도메인 영속화](#4-안-b--하이브리드-도메인-영속화)
5. [공통 — 외부 입력/출력 스키마](#5-공통--외부-입력출력-스키마)
6. [공통 — MySQL 스키마 (5개 테이블)](#6-공통--mysql-스키마)
7. [공통 — Pinecone / S3 / Neo4j 스키마](#7-공통--pinecone--s3--neo4j-스키마)
8. [안 A vs 안 B 최종 비교](#8-안-a-vs-안-b-최종-비교)
9. [추적 가능성 체계](#9-추적-가능성-체계)
10. [데이터 라이프사이클](#10-데이터-라이프사이클)

---

## 1. v2.0 문제점 분석

### 1.1 현재 상태

v2.0에서 도입한 **단일 Persistence Layer**는 아직 구현되지 않았다(의사코드만 존재).
코드베이스 분석 결과 20개 에이전트 중 DB에 쓰기를 하는 것은 Learning Agent 1개뿐이며,
나머지 19개 에이전트의 데이터는 세션 종료 시 전부 소실된다.

### 1.2 구조적 문제점

#### 문제 1: God Object — 높은 결합도

```
Persistence Layer (단일 함수)
    ├── Emotion Agent 내부 구조 알아야 함 (.primary_emotion, .intensity, .valence, .arousal)
    ├── Intent Classifier 내부 구조 알아야 함 (.complexity_score, .detected_entities.topics)
    ├── Safety Agent 내부 구조 알아야 함 (.status, .reasons)
    ├── Content Analyzer 내부 구조 알아야 함 (.main_theme)
    ├── Script Personalizer 내부 구조 알아야 함 (.episode_title, .segments[].script_text)
    └── Reasoning Agent 내부 구조 알아야 함 (summarize 필요)

→ 6개 에이전트의 내부 dict 구조에 15+ 지점 하드코딩 의존
→ 에이전트 출력 형식 변경 시 Persistence Layer 연쇄 수정
→ CLAUDE.md "필드 소유권" 원칙 위배 (개발자3이 바꾸면 Persistence 담당자도 수정)
```

#### 문제 2: DB 부하 집중

파이프라인 1회 완료 시 발생하는 쓰기 연산:

| 모드 | MySQL | Pinecone | Embedding API | S3 | 총 I/O |
|------|-------|----------|---------------|----|--------|
| 대화 | 3~4건 (순차) | 1건 | 1회 (~100ms) | 0~1건 | **5~7건** |
| 팟캐스트 | 3~4건 (순차) | 4건 (세그먼트별, 순차) | 4회 (~400ms) | 0~1건 | **11~13건** |

모든 쓰기가 **단일 함수에서 순차 실행**:
- 대화모드 Persistence 소요: ~170ms
- 팟캐스트모드 Persistence 소요: **~620ms** (임베딩 루프가 병목)

동시 사용자 1,000명 시 초당 쓰기 추정:

| 지표 | 추정치 |
|------|-------|
| MySQL 초당 쓰기 | 54~68건/sec |
| Pinecone 초당 upsert | 27~44건/sec |
| Embedding API 초당 호출 | 27~44회/sec |
| 동시 Persistence 인스턴스 | 3~10개 (커넥션 풀 경합) |

#### 문제 3: 단일 장애점 (SPOF)

| 장애 시나리오 | 영향 |
|-------------|------|
| MySQL 연결 실패 | 대화 기록, 에피소드, safety 이벤트 **전부 미저장** |
| Pinecone 연결 실패 | 벡터 미저장 + MySQL 역참조 UPDATE 실패 |
| Persistence Layer 함수 예외 | **safety_events 포함 전부 유실** (법적 의무 위반 가능) |

부분 실패 복구 메커니즘 없음. MySQL → Pinecone 사이에서 죽으면 데이터 불일치.

#### 문제 4: 확장성 한계

| 시나리오 | 수정 필요 파일 수 |
|---------|----------------|
| 에이전트 1개 추가 | 5개 (agent_state.py★ + workflow.py★ + Persistence + schema + DDL) |
| 새 DB 추가 (Redis 등) | Persistence Layer 전면 수정 + 부분 실패 조합 2배 증가 |
| 새 모드 추가 (journal 등) | elif 분기 추가 → 코드량 O(N×M) 증가 |

★ = Protected File (3인 합의 필요)

---

## 2. 검토한 접근법 7가지 비교

서브에이전트 4개를 병렬로 실행하여 각각 다른 아키텍처 패턴을 연구·비교했다.

| 접근법 | 핵심 개념 | 에이전트 추가 시 변경 | DB 부하 | 인프라 복잡도 | 3명 팀 적합 |
|--------|---------|-------------------|--------|------------|-----------|
| **A: 이벤트 드리븐** | 에이전트가 이벤트 발행, DB별 컨슈머가 구독 | 이벤트 클래스 1개 + 구독 등록 | 분산 (즉시 비동기) | 낮음 (asyncio.Queue) | **적합** |
| B: CQRS | EventStore + Projector + QueryService | 이벤트 + Projector 핸들러 | 분산 (프로젝션) | **높음** | 과잉 |
| C: Persister 플러그인 | 에이전트별 저장 방법을 코드로 선언 | Persister 파일 1개 (auto-discover) | 병렬화 가능 | 중간 (파일 수 증가) | 적합 |
| D: YAML 선언적 | 설정 파일로 매핑 관리 | YAML 10줄 추가 | 병렬화 가능 | 낮음 | 부적합 (merge conflict) |
| E: 도메인 Persistence 분리 | 도메인별 Persister 노드를 LangGraph에 등록 | 해당 Persister만 수정 | 병렬 Fan-out | 낮음 | 적합 |
| F: 비동기 Write-behind 큐 | 배치 처리로 DB 호출 횟수 최소화 | 이벤트 매핑 추가 | **배치로 획기적 감소** | 중간 (워커 관리) | 약간 과잉 |
| **G: 하이브리드 (E+F)** | 도메인 분리 + 우선순위별 배치 | 해당 Persister만 수정 | 우선순위별 최적화 | 낮음 (asyncio.Queue) | **적합** |

### 최종 선정: 안 A (이벤트 드리븐) + 안 B (하이브리드 도메인)

- **안 A**: "에이전트 독립성"에 초점 — 에이전트가 이벤트를 발행하면 끝. 저장 로직을 모름.
- **안 B**: "DB 부하 최적화"에 초점 — 도메인별로 분리하고, 우선순위별로 즉시/배치/비동기 선택.

두 안 모두:
- **Protected File 수정 불필요** (workflow.py, agent_state.py, base_agent.py)
- **외부 인프라 추가 불필요** (asyncio.Queue만 사용)
- **에이전트 추가 시 중앙 코드 수정 불필요**

---

## 3. 안 A — 이벤트 드리븐 영속화

### 3.1 설계 원칙

```
핵심: 에이전트는 "내 결과를 이벤트로 발행"하면 끝.
      어디에 저장되는지, 어떻게 저장되는지 모른다.
      DB별 컨슈머가 이벤트를 받아서 독립적으로 저장한다.
```

### 3.2 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────┐
│               LangGraph 파이프라인 (AgentState)               │
│                                                              │
│  TIER 0 → TIER 1 (병렬) → TIER 2 → TIER 3 → TIER 4         │
│     │         │              │         │         │           │
│     ▼         ▼              ▼         ▼         ▼           │
│  emit()    emit()          emit()   emit()    emit()         │
│  Intent    Emotion         Synth    Valid.    Person.         │
│  Analyzed  Analyzed        Drafted  Checked   Finalized      │
└──────┬────────┬──────────────┬────────┬─────────┬────────────┘
       │        │              │        │         │
       ▼        ▼              ▼        ▼         ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    EventBus (asyncio.Queue)              │
  │                                                         │
  │  이벤트를 받아 등록된 핸들러(컨슈머)에 병렬 디스패치     │
  │  핸들러 하나가 실패해도 다른 핸들러는 계속 실행          │
  └────────┬──────────────┬──────────────┬──────────────────┘
           │              │              │
           ▼              ▼              ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │ MySQLConsumer│ │PineconeConsum│ │  S3Consumer  │
   │              │ │              │ │              │
   │ conv_history │ │ mem_convers. │ │ vis/ upload  │
   │ podcast_ep   │ │ mem_podcast  │ │              │
   │ safety_events│ │              │ │              │
   │ pipeline_logs│ │              │ │              │
   │ learning_pat │ │              │ │              │
   └──────────────┘ └──────────────┘ └──────────────┘
```

### 3.3 이벤트 정의

```python
# src/persistence/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass(frozen=True)
class DomainEvent:
    """모든 도메인 이벤트의 기본 클래스. 불변(frozen)."""
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    event_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str = ""
    session_id: str = ""
    mode: str = ""           # "conversation" | "podcast"
    trace_id: str = ""


@dataclass(frozen=True)
class EmotionAnalyzed(DomainEvent):
    event_type: str = "emotion.analyzed"
    emotion_vectors: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SafetyEvaluated(DomainEvent):
    event_type: str = "safety.evaluated"
    risk_level: int = 0
    risk_score: float = 0.0
    safety_flags: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class IntentClassified(DomainEvent):
    event_type: str = "intent.classified"
    intent: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ReasoningCompleted(DomainEvent):
    event_type: str = "reasoning.completed"
    reasoning_result: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ContentAnalyzed(DomainEvent):
    event_type: str = "content.analyzed"
    content_analysis: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ResponseFinalized(DomainEvent):
    event_type: str = "response.finalized"
    final_output: str = ""
    turn_sequence: int = 0

@dataclass(frozen=True)
class ScriptFinalized(DomainEvent):
    event_type: str = "script.finalized"
    script_draft: dict[str, Any] = field(default_factory=dict)
    final_output: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class VisualizationCreated(DomainEvent):
    event_type: str = "visualization.created"
    visual_data: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class LearningUpdated(DomainEvent):
    event_type: str = "learning.updated"
    patterns: dict[str, Any] = field(default_factory=dict)
```

### 3.4 이벤트 버스

```python
# src/persistence/event_bus.py
import asyncio
import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger(__name__)


class EventBus:
    """
    In-Process 비동기 이벤트 버스.
    Phase 1: asyncio.Queue (추가 인프라 없음)
    Phase 2: Redis Streams로 교체 가능 (에이전트 코드 변경 없음)
    """

    def __init__(self, max_queue_size: int = 1000) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue[DomainEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._running = False

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """이벤트 타입별 핸들러 등록."""
        self._subscribers[event_type].append(handler)

    async def emit(self, event: DomainEvent) -> None:
        """이벤트를 큐에 넣는다 (fire-and-forget, 에이전트 블로킹 없음)."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("EventBus 큐 포화 — 이벤트 드롭: %s", event.event_id)

    async def start(self) -> None:
        """디스패치 루프 시작 (앱 startup 시 1회 호출)."""
        self._running = True
        asyncio.create_task(self._dispatch_loop())

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                handlers = self._subscribers.get(event.event_type, [])
                # 핸들러들을 병렬 실행 — 하나 실패해도 나머지 계속
                tasks = [asyncio.create_task(self._safe(h, event)) for h in handlers]
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    @staticmethod
    async def _safe(handler: Callable, event: DomainEvent) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception("핸들러 실패: %s ← %s", handler.__name__, event.event_id)
```

### 3.5 DB별 컨슈머

```python
# src/persistence/consumers/mysql_consumer.py
class MySQLConsumer:
    """MySQL 저장 담당. 이벤트 타입별로 적절한 테이블에 INSERT."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def on_response_finalized(self, event: ResponseFinalized) -> None:
        """대화 응답 완료 → conversation_history INSERT."""
        await self._backend.save("conversation_history", SaveRequest(
            user_id=event.user_id,
            session_id=event.session_id,
            type="conversation",
            data={
                "user_input": event.final_output,  # 실제론 별도 필드
                "ai_response": event.final_output,
                "turn_sequence": event.turn_sequence,
                "trace_id": event.trace_id,
            },
            timestamp=event.timestamp,
        ))

    async def on_safety_evaluated(self, event: SafetyEvaluated) -> None:
        """Safety 이벤트 → warning/crisis만 safety_events INSERT."""
        status = event.safety_flags.get("status", "safe")
        if status in ("warning", "crisis"):
            await self._backend.save("safety_events", SaveRequest(
                user_id=event.user_id,
                session_id=event.session_id,
                type="safety_event",
                data={
                    "severity": status,
                    "risk_score": event.risk_score,
                    "risk_level": event.risk_level,
                    "safety_flags": event.safety_flags,
                    "trace_id": event.trace_id,
                },
                timestamp=event.timestamp,
            ))


# src/persistence/consumers/pinecone_consumer.py
class PineconeConsumer:
    """Pinecone 벡터 저장 담당."""

    async def on_response_finalized(self, event: ResponseFinalized) -> None:
        """대화 완료 → mem_conversation에 벡터 upsert."""
        embedding = await self._embed(event.final_output)
        await self._pinecone.upsert("mem_conversation", ...)

    async def on_script_finalized(self, event: ScriptFinalized) -> None:
        """팟캐스트 완료 → 세그먼트별 mem_podcast_episode에 벡터 upsert."""
        for idx, seg in enumerate(event.final_output.get("segments", [])):
            embedding = await self._embed(seg.get("script_text", ""))
            await self._pinecone.upsert("mem_podcast_episode", ...)


# src/persistence/consumers/s3_consumer.py
class S3Consumer:
    """S3 이미지 업로드 담당."""

    async def on_visualization_created(self, event: VisualizationCreated) -> None:
        """시각화 완료 → S3 업로드 + CDN URL 반환."""
        image_data = event.visual_data.get("image_bytes")
        if image_data:
            await self._s3.upload(...)
```

### 3.6 구독 등록 (앱 초기화)

```python
# src/persistence/setup.py
def setup_event_bus() -> EventBus:
    bus = EventBus()
    mysql = MySQLConsumer(backend=BackendClient())
    pinecone = PineconeConsumer(pinecone_client=get_pinecone())
    s3 = S3Consumer(s3_client=get_s3())

    # MySQL 구독
    bus.subscribe("response.finalized",   mysql.on_response_finalized)
    bus.subscribe("script.finalized",     mysql.on_script_finalized)
    bus.subscribe("safety.evaluated",     mysql.on_safety_evaluated)
    bus.subscribe("learning.updated",     mysql.on_learning_updated)

    # Pinecone 구독
    bus.subscribe("response.finalized",   pinecone.on_response_finalized)
    bus.subscribe("script.finalized",     pinecone.on_script_finalized)

    # S3 구독
    bus.subscribe("visualization.created", s3.on_visualization_created)

    return bus
```

### 3.7 에이전트 연동 — BaseAgent에 신규 메서드 추가

```python
# src/agents/shared/base_agent.py (신규 메서드 추가만 — 기존 인터페이스 불변)
class BaseAgent(ABC):
    # ... 기존 코드 그대로 ...

    _event_bus: ClassVar[EventBus | None] = None

    @classmethod
    def set_event_bus(cls, bus: EventBus) -> None:
        """전역 이벤트 버스 설정. 앱 startup 시 1회 호출."""
        cls._event_bus = bus

    async def emit_event(self, event: DomainEvent) -> None:
        """이벤트 발행. 버스 없으면 무시 (opt-in)."""
        if self._event_bus is not None:
            await self._event_bus.emit(event)
```

### 3.8 에이전트 사용 예시

```python
# 각 에이전트의 process() 마지막에 이벤트 발행 (선택적)
class EmotionAgent(BaseAgent):
    async def process(self, state: AgentState) -> dict[str, Any]:
        result = await self._analyze_emotion(state)

        # 이벤트 발행 — 어디에 저장될지는 모름
        await self.emit_event(EmotionAnalyzed(
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
            mode=state.get("mode", "conversation"),
            trace_id=state.get("trace_id", ""),
            emotion_vectors=result["emotion_vectors"],
        ))

        return result  # AgentState 반환 (LangGraph 상태 merge)
```

### 3.9 에이전트 추가 시 변경 범위

```
새 "Feedback Agent" 추가 시:

1. src/agents/conversation/feedback.py     (신규 — 에이전트 구현)
2. src/persistence/events.py               (1줄 — FeedbackReceived 이벤트 클래스 추가)
3. src/persistence/consumers/mysql_consumer.py (1메서드 — on_feedback_received 핸들러)
4. src/persistence/setup.py                (1줄 — bus.subscribe 등록)

변경하지 않는 파일:
  ✓ workflow.py (Protected) — 워크플로우 노드 추가는 별도
  ✓ agent_state.py (Protected) — 필요 시만
  ✓ base_agent.py — 이미 emit_event() 있음
  ✓ 다른 에이전트 코드 — 영향 없음
  ✓ 다른 컨슈머 코드 — 영향 없음
```

### 3.10 시퀀스 다이어그램

```
User     FastAPI   LangGraph    EmotionAgent  SafetyAgent   EventBus   MySQL  Pinecone  S3
 │         │          │              │            │            │         │       │       │
 │─request→│          │              │            │            │         │       │       │
 │         │─ainvoke─→│              │            │            │         │       │       │
 │         │          │─TIER1 병렬──→│            │            │         │       │       │
 │         │          │              │─emit(Emotion)──────────→│         │       │       │
 │         │          │              │            │            │         │       │       │
 │         │          │─TIER1 병렬────────────────→│           │         │       │       │
 │         │          │              │            │─emit(Safety)────────→│       │       │
 │         │          │              │            │            │         │       │       │
 │         │          │─TIER2~4 계속 ...          │            │         │       │       │
 │         │          │              │            │            │         │       │       │
 │         │←─state───│              │            │  비동기     │         │       │       │
 │←─응답───│          │              │            │  디스패치   │         │       │       │
 │ (즉시)  │          │              │            │  ┌─────────┘         │       │       │
 │         │          │              │            │  │                   │       │       │
 │         │          │              │            │  │──emotion.analyzed→│       │       │
 │         │          │              │            │  │──emotion.analyzed→│───────→│      │
 │         │          │              │            │  │──safety.evaluated→│       │       │
 │         │          │              │            │  │                   │       │       │
```

### 3.11 장점/단점 요약

**장점:**
- 에이전트 완전 독립: 이벤트만 발행하면 끝, 저장 로직 일절 모름
- 장애 격리: MySQL 컨슈머 실패해도 Pinecone 컨슈머는 정상 동작
- Open-Closed Principle: 기존 코드 수정 없이 새 컨슈머/이벤트만 추가
- 점진적 진화: asyncio.Queue → Redis Streams → Kafka (에이전트 코드 변경 없음)
- 부하 분산: 이벤트가 파이프라인 실행 중 즉시 발행되므로 DB 쓰기가 시간적으로 분산

**단점:**
- 최종 일관성: 이벤트 처리 지연 시 DB 간 일시적 불일치
- 이벤트 순서: 동일 세션의 이벤트가 처리 순서와 다르게 저장될 수 있음
- 디버깅 복잡도: 이벤트 발행 → 큐 → 컨슈머 경로를 추적해야 함
- conversation_history에 대화의 모든 데이터를 통합하려면 컨슈머 간 조율 필요

---

## 4. 안 B — 하이브리드 도메인 영속화

### 4.1 설계 원칙

```
핵심: 도메인별 Persister로 분리하고,
      데이터 특성에 따라 즉시/배치/비동기를 선택한다.
      workflow.py 외부의 pipeline/runner.py에서 오케스트레이션한다.
```

| 데이터 특성 | 저장 전략 | 이유 |
|------------|----------|------|
| Safety 이벤트 | **즉시 동기** | 위기 데이터 유실 불가, 법적 의무 |
| 대화 기록 / 에피소드 | **동기 배치** | 핵심 비즈니스 데이터, 순서 보장 |
| Pinecone 벡터 | **비동기 큐 + 배치 upsert** | eventual consistency 허용, 배치가 효율적 |
| S3 이미지 | **비동기 큐** | 가장 느린 I/O, 완전 비동기 |
| 파이프라인 로그 | **비동기 큐 + 배치** | 지연 허용, 대량 데이터 |

### 4.2 아키텍처 다이어그램

```
┌──────────────────────────────────────────────────────────────────┐
│               LangGraph 파이프라인 (AgentState)                   │
│  TIER 0 → TIER 1 (병렬) → TIER 2 → TIER 3 → TIER 4             │
└────────────────────────────┬─────────────────────────────────────┘
                             │ final AgentState
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│        pipeline/runner.py — 파이프라인 실행기                     │
│                                                                  │
│  1. response = build_response(final_state)  → 사용자 즉시 반환   │
│  2. asyncio.create_task(orchestrator.persist(final_state))       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ fire-and-forget
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│             PersistenceOrchestrator                               │
│                                                                  │
│  Phase 1 (동기, 블로킹):                                         │
│  └─ SafetyPersister → MySQL safety_events (즉시)                │
│                                                                  │
│  Phase 2 (병렬, 비동기):                                         │
│  ├─ CorePersister → MySQL conv_history / podcast_episodes       │
│  ├─ VectorPersister → asyncio.Queue → Pinecone 배치 upsert     │
│  └─ AssetPersister → asyncio.Queue → S3 비동기 업로드            │
└──────────────────────────────────────────────────────────────────┘
```

### 4.3 BasePersister 인터페이스

```python
# src/persistence/base_persister.py
from abc import ABC, abstractmethod
from typing import Any
from src.models.agent_state import AgentState


class BasePersister(ABC):
    """도메인별 Persister 기본 클래스."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def should_run(self, state: AgentState) -> bool:
        """이 Persister가 실행되어야 하는지 판단."""
        ...

    @abstractmethod
    async def persist(self, state: AgentState) -> dict[str, Any]:
        """도메인 데이터를 저장. 자기 도메인 필드만 읽는다."""
        ...
```

### 4.4 SafetyPersister — 즉시 동기 저장

```python
# src/persistence/safety_persister.py
class SafetyPersister(BasePersister):
    """Safety 이벤트 즉시 저장 — warning/crisis만. 큐 사용 안 함."""

    def __init__(self, backend: BackendClient) -> None:
        super().__init__(name="safety")
        self._backend = backend

    def should_run(self, state: AgentState) -> bool:
        status = state.get("safety_flags", {}).get("status", "safe")
        return status in ("warning", "crisis")

    async def persist(self, state: AgentState) -> dict[str, Any]:
        safety = state["safety_flags"]
        await self._backend.save("safety_events", SaveRequest(
            user_id=state["user_id"],
            session_id=state["session_id"],
            type="safety_event",
            data={
                "severity": safety["status"],
                "risk_score": state.get("risk_score", 0.0),
                "risk_level": state.get("risk_level", 0),
                "risk_category": safety.get("reasons", ["unknown"])[0],
                "safety_flags": safety,
                "action_taken": "crisis_response" if safety["status"] == "crisis" else "flag",
                "trace_id": state.get("trace_id", ""),
            },
            timestamp=datetime.now(timezone.utc),
        ))
        return {"safety_saved": True}
```

### 4.5 CorePersister — 핵심 데이터 (모드별 자동 분기)

```python
# src/persistence/core_persister.py
class CorePersister(BasePersister):
    """MySQL 핵심 데이터 저장 — 대화 기록 / 팟캐스트 에피소드."""

    def __init__(self, backend: BackendClient) -> None:
        super().__init__(name="core")
        self._backend = backend

    def should_run(self, state: AgentState) -> bool:
        return state.get("final_output") is not None

    async def persist(self, state: AgentState) -> dict[str, Any]:
        mode = state.get("mode", "conversation")
        if mode == "conversation":
            return await self._save_conversation(state)
        elif mode == "podcast":
            return await self._save_podcast(state)
        return {}

    async def _save_conversation(self, state: AgentState) -> dict:
        """conversation_history INSERT — 한 턴의 모든 핵심 정보 통합."""
        record_id = str(uuid4())
        emotion = state.get("emotion_vectors", {})
        await self._backend.save("conversation_history", SaveRequest(
            user_id=state["user_id"],
            session_id=state["session_id"],
            type="conversation",
            data={
                "id": record_id,
                "user_input": state["user_input"],
                "ai_response": state["final_output"],
                "intent": state.get("intent"),
                "emotion_vectors": emotion,
                "primary_emotion": emotion.get("primary_emotion", "neutral"),
                "emotion_intensity": emotion.get("intensity", 0.0),
                "valence": emotion.get("valence", 0.0),
                "arousal": emotion.get("arousal", 0.0),
                "risk_level": state.get("risk_level", 0),
                "reasoning_summary": self._summarize(state.get("reasoning_result")),
                "trace_id": state.get("trace_id", ""),
            },
            timestamp=datetime.now(timezone.utc),
        ))
        return {"conversation_id": record_id}

    async def _save_podcast(self, state: AgentState) -> dict:
        """podcast_episodes INSERT — 에피소드 + 세그먼트 통합."""
        record_id = str(uuid4())
        # ... script_draft, content_analysis, emotion_vectors 추출
        return {"episode_id": record_id}

    @staticmethod
    def _summarize(reasoning_result: dict | None) -> str | None:
        if not reasoning_result:
            return None
        return str(reasoning_result)[:500]
```

### 4.6 VectorPersister — Pinecone 배치 upsert

```python
# src/persistence/vector_persister.py
class VectorPersister(BasePersister):
    """Pinecone 벡터 비동기 배치 저장.

    내부 asyncio.Queue로 버퍼링 → 50건 또는 3초마다 bulk upsert.
    Pinecone API 호출 횟수를 50분의 1로 줄인다.
    """

    def __init__(self, pinecone_client, batch_size: int = 50, flush_sec: float = 3.0):
        super().__init__(name="vector")
        self._client = pinecone_client
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._batch_size = batch_size
        self._flush_sec = flush_sec

    async def start_worker(self) -> None:
        """앱 startup 시 호출 — 배치 워커 시작."""
        asyncio.create_task(self._batch_loop())

    def should_run(self, state: AgentState) -> bool:
        return state.get("final_output") is not None

    async def persist(self, state: AgentState) -> dict[str, Any]:
        """큐에 벡터화 대상을 넣는다 (즉시 반환)."""
        mode = state.get("mode", "conversation")
        if mode == "conversation":
            await self._queue.put({
                "text": f"{state.get('user_input','')} {state.get('final_output','')}",
                "namespace": "mem_conversation",
                "metadata": {
                    "user_id": state["user_id"],
                    "session_id": state["session_id"],
                    "primary_emotion": state.get("emotion_vectors",{}).get("primary_emotion",""),
                    "trace_id": state.get("trace_id", ""),
                },
            })
        elif mode == "podcast":
            for idx, seg in enumerate(state.get("script_draft",{}).get("segments",[])):
                await self._queue.put({
                    "text": seg.get("script_text", ""),
                    "namespace": "mem_podcast_episode",
                    "metadata": {
                        "user_id": state["user_id"],
                        "segment_idx": idx,
                        "trace_id": state.get("trace_id", ""),
                    },
                })
        return {"vectors_queued": True, "queue_size": self._queue.qsize()}

    async def _batch_loop(self) -> None:
        batch: list[dict] = []
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self._flush_sec)
                batch.append(item)
                if len(batch) >= self._batch_size:
                    await self._flush(batch)
                    batch = []
            except asyncio.TimeoutError:
                if batch:
                    await self._flush(batch)
                    batch = []

    async def _flush(self, batch: list[dict]) -> None:
        """배치 upsert — 단일 API 호출로 최대 100건."""
        vectors = []
        for item in batch:
            embedding = await self._embed(item["text"])
            vectors.append({
                "id": f"vec_{uuid4().hex[:12]}",
                "values": embedding,
                "metadata": item["metadata"],
            })
        # 네임스페이스별 그룹핑
        by_ns: dict[str, list] = defaultdict(list)
        for v, item in zip(vectors, batch):
            by_ns[item["namespace"]].append(v)
        for ns, vecs in by_ns.items():
            await self._client.upsert(namespace=ns, vectors=vecs)
```

### 4.7 AssetPersister — S3 비동기 업로드

```python
# src/persistence/asset_persister.py
class AssetPersister(BasePersister):
    """S3 이미지 비동기 업로드. 가장 느린 I/O — 완전 비동기."""

    def should_run(self, state: AgentState) -> bool:
        return state.get("visual_data") is not None

    async def persist(self, state: AgentState) -> dict[str, Any]:
        visual = state["visual_data"]
        user_id = state["user_id"]
        session_id = state["session_id"]
        mode = state.get("mode", "conversation")

        key = f"vis/{user_id}/{mode}/{session_id}/{uuid4().hex[:8]}.webp"
        await self._s3.upload(bucket="mindlog-images", key=key, data=visual.get("image_bytes"))

        cdn_url = f"https://cdn.mindlog.app/{key}"
        # MySQL에 URL 업데이트 (비동기)
        await self._backend.save(...)
        return {"image_url": cdn_url}
```

### 4.8 PersistenceOrchestrator — 통합 실행기

```python
# src/persistence/orchestrator.py
class PersistenceOrchestrator:
    """도메인별 Persister를 우선순위에 따라 실행."""

    def __init__(self, safety, core, vector, asset, metrics):
        self._safety = safety
        self._core = core
        self._vector = vector
        self._asset = asset
        self._metrics = metrics

    async def persist(self, state: AgentState) -> dict[str, Any]:
        results = {}

        # Phase 1: Safety 즉시 (블로킹)
        if self._safety.should_run(state):
            results["safety"] = await self._safety.persist(state)

        # Phase 2: 나머지 병렬 (non-blocking)
        tasks = []
        for name, persister in [
            ("core", self._core),
            ("vector", self._vector),
            ("asset", self._asset),
            ("metrics", self._metrics),
        ]:
            if persister.should_run(state):
                tasks.append(self._safe_persist(name, persister, state, results))

        if tasks:
            await asyncio.gather(*tasks)
        return results

    @staticmethod
    async def _safe_persist(name, persister, state, results):
        try:
            results[name] = await persister.persist(state)
        except Exception as e:
            logger.error("Persister 실패: %s — %s", name, e)
            results[name] = {"status": "error", "error": str(e)}
```

### 4.9 pipeline/runner.py — workflow.py 수정 없이 통합

```python
# src/pipeline/runner.py
from src.graph.workflow import compile_graph
from src.persistence.orchestrator import PersistenceOrchestrator

async def run_pipeline(user_input, user_id, session_id, mode="conversation"):
    """LangGraph 파이프라인 실행 + 하이브리드 영속화."""

    compiled = compile_graph("unified")

    # 1. 파이프라인 실행
    final_state = await compiled.ainvoke({
        "user_input": user_input,
        "user_id": user_id,
        "session_id": session_id,
        "mode": mode,
    })

    # 2. 응답 즉시 반환 (사용자 대기 0ms)
    response = build_response(final_state)

    # 3. 영속화 fire-and-forget
    orchestrator = get_orchestrator()
    asyncio.create_task(orchestrator.persist(final_state))

    return response
```

### 4.10 에이전트 추가 시 변경 범위

```
새 "Feedback Agent" 추가 시:

1. src/agents/conversation/feedback.py      (신규 — 에이전트 구현)
2. src/persistence/core_persister.py        (1메서드 — _save_feedback 추가)
   또는 src/persistence/feedback_persister.py (신규 Persister)
3. src/persistence/orchestrator.py          (1줄 — Persister 등록)

변경하지 않는 파일:
  ✓ workflow.py (Protected)
  ✓ agent_state.py (Protected)
  ✓ base_agent.py
  ✓ 다른 Persister 코드
  ✓ VectorPersister, AssetPersister (영향 없음)
```

### 4.11 시퀀스 다이어그램

```
User     FastAPI   LangGraph   PersistOrch  Safety   Core   Vector   Asset   MySQL  Pinecone  S3
 │         │          │            │          │       │       │        │       │       │       │
 │─request→│          │            │          │       │       │        │       │       │       │
 │         │─ainvoke─→│            │          │       │       │        │       │       │       │
 │         │          │═TIER 0~4══│          │       │       │        │       │       │       │
 │         │←─state───│            │          │       │       │        │       │       │       │
 │←─응답───│          │            │          │       │       │        │       │       │       │
 │ (즉시)  │──fire&forget────────→│          │       │       │        │       │       │       │
 │         │          │            │          │       │       │        │       │       │       │
 │         │          │            │─Phase1──→│       │       │        │       │       │       │
 │         │          │            │ (Safety  │─sync──────────────────────────→│       │       │
 │         │          │            │  즉시)   │←ok────────────────────────────│       │       │
 │         │          │            │          │       │       │        │       │       │       │
 │         │          │            │─Phase2 (병렬)───→│       │        │       │       │       │
 │         │          │            │          │       │─batch─────────────────→│       │       │
 │         │          │            │──────────────────────────→│       │       │       │       │
 │         │          │            │          │       │        │─queue─→│      │       │       │
 │         │          │            │          │       │        │ 배치   │      │       │       │
 │         │          │            │─────────────────────────────────→│       │       │       │
 │         │          │            │          │       │        │      │─S3───→│       │       │
 │         │          │            │          │       │        │       │      │       │       │
 │         │          │            │          │       │   [3초후]      │      │       │       │
 │         │          │            │          │       │   │─bulk upsert──────────────→│       │
```

### 4.12 장점/단점 요약

**장점:**
- 우선순위별 저장: Safety 즉시, Core 동기, Vector/Asset 비동기 — 데이터 특성에 맞는 전략
- DB 부하 최적화: Pinecone 배치 upsert로 API 호출 50분의 1 감소
- 응답 지연 0: fire-and-forget으로 사용자 응답 즉시 반환
- Protected File 미수정: workflow.py 밖(pipeline/runner.py)에서 오케스트레이션
- 장애 격리: Persister별 독립 실행, 부분 실패 허용
- Safety 즉시성 보장: 큐를 거치지 않으므로 위기 데이터 유실 불가

**단점:**
- CorePersister가 AgentState 내부 구조를 알아야 함 (안 A보다 결합도 약간 높음)
- Persister 수 증가 시 오케스트레이터 등록 관리 필요
- VectorPersister 내부의 asyncio.Queue가 프로세스 재시작 시 유실 가능

---

## 5. 공통 — 외부 입력/출력 스키마

### 5.1 외부 입력 (우리가 받는 것)

테이블을 정의하지 않는다. 외부 시스템에서 받아서 그대로 사용.

```python
# POST /api/v1/conversations
{
    "user_id": "uuid",           # 외부 시스템의 사용자 ID
    "session_id": "uuid",        # 외부 시스템의 세션 ID
    "mode": "conversation",
    "user_input": "오늘 하루 너무 힘들었어...",
    "trace_id": "trace_xxx",     # (선택) 분산 추적 ID
    "user_profile": {            # (선택) 외부에서 관리하는 사용자 정보
        "nickname": "홍길동",
        "locale": "ko-KR",
        "timezone": "Asia/Seoul"
    }
}

# POST /api/v1/podcasts/episodes
{
    "user_id": "uuid",
    "session_id": "uuid",
    "mode": "podcast",
    "user_input": "직장 스트레스 관리법에 대해 알고 싶어",
    "description": "특히 야근이 많은 상황에서...",
    "preferences": {
        "target_duration_min": 5,
        "tone": "calm",
        "depth": "moderate"
    }
}
```

### 5.2 외부 출력 (우리가 주는 것)

```python
class ConversationResponse:
    response_text: str              # AgentState.final_output
    turn_sequence: int
    emotion: {
        primary_emotion: str
        intensity: float            # 0.0~1.0
        valence: float              # -1.0~1.0
        arousal: float              # 0.0~1.0
    }
    safety_alert: {                 # nullable (warning/crisis만)
        level: str
        message: str
        helpline_info: [...]
    }
    visualization: {                # nullable (비동기 완료 후)
        image_url: str
        interpretation: str
        palette: str
    }
    trace_id: str
    processing_time_ms: int

class PodcastEpisodeResponse:
    episode_id: str
    episode_title: str
    total_duration_min: int
    segments: [{
        segment_id: str
        segment_type: str           # "intro" | "body" | "reflection" | "closing"
        script_text: str
        duration_min: int
        emotional_tone: str
    }]
    key_insights: [str]
    themes: [str]
    emotion: { ... }
    safety_alert: { ... }           # nullable
    cover_image: { ... }            # nullable
    trace_id: str
    processing_time_ms: int
```

---

## 6. 공통 — MySQL 스키마

**5개 테이블.** 두 안 모두 동일한 테이블 구조를 사용한다.

### 6.1 conversation_history

```sql
CREATE TABLE conversation_history (
    id                  CHAR(36)        NOT NULL COMMENT 'UUIDv4',
    user_id             CHAR(36)        NOT NULL,
    session_id          CHAR(36)        NOT NULL,
    turn_sequence       SMALLINT UNSIGNED NOT NULL,

    user_input          TEXT            NOT NULL,
    ai_response         TEXT            NOT NULL,

    intent              JSON            NOT NULL,
    emotion_vectors     JSON            NOT NULL,
    safety_flags        JSON            NULL     COMMENT 'safe이면 NULL',
    reasoning_summary   TEXT            NULL,

    primary_emotion     VARCHAR(30)     NOT NULL,
    emotion_intensity   DECIMAL(3,2)    NOT NULL,
    valence             DECIMAL(4,2)    NOT NULL,
    arousal             DECIMAL(3,2)    NOT NULL,
    risk_level          TINYINT UNSIGNED NOT NULL DEFAULT 0,
    complexity_score    DECIMAL(3,2)    NULL,

    visualization_url   VARCHAR(1024)   NULL,
    visualization_meta  JSON            NULL,
    pinecone_vector_id  VARCHAR(100)    NULL,

    trace_id            CHAR(36)        NOT NULL,
    processing_time_ms  INT UNSIGNED    NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE INDEX uix_session_turn (session_id, turn_sequence),
    INDEX ix_user_time (user_id, created_at DESC),
    INDEX ix_user_emotion (user_id, primary_emotion, created_at DESC),
    INDEX ix_trace (trace_id),
    INDEX ix_risk (risk_level, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  PARTITION BY RANGE (UNIX_TIMESTAMP(created_at)) (
    PARTITION p2026_q1 VALUES LESS THAN (UNIX_TIMESTAMP('2026-04-01')),
    PARTITION p2026_q2 VALUES LESS THAN (UNIX_TIMESTAMP('2026-07-01')),
    PARTITION p2026_q3 VALUES LESS THAN (UNIX_TIMESTAMP('2026-10-01')),
    PARTITION p2026_q4 VALUES LESS THAN (UNIX_TIMESTAMP('2027-01-01')),
    PARTITION p_future  VALUES LESS THAN MAXVALUE
  );
```

### 6.2 podcast_episodes

```sql
CREATE TABLE podcast_episodes (
    id                  CHAR(36)        NOT NULL,
    user_id             CHAR(36)        NOT NULL,
    session_id          CHAR(36)        NOT NULL,

    title               VARCHAR(200)    NOT NULL,
    theme               VARCHAR(100)    NULL,
    episode_number      INT UNSIGNED    NULL,
    status              ENUM('generating','completed','failed') NOT NULL DEFAULT 'generating',
    duration_sec        INT UNSIGNED    NULL,

    script_json         JSON            NOT NULL COMMENT '세그먼트 배열 포함',
    content_analysis    JSON            NULL,
    emotion_summary     JSON            NOT NULL,
    safety_flags        JSON            NULL,
    reasoning_summary   TEXT            NULL,
    validation_result   JSON            NULL,

    primary_emotion     VARCHAR(30)     NOT NULL,
    risk_level          TINYINT UNSIGNED NOT NULL DEFAULT 0,

    cover_image_url     VARCHAR(1024)   NULL,
    cover_image_meta    JSON            NULL,
    pinecone_vector_ids JSON            NULL,

    trace_id            CHAR(36)        NOT NULL,
    processing_time_ms  INT UNSIGNED    NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE INDEX uix_session (session_id),
    INDEX ix_user_created (user_id, created_at DESC),
    INDEX ix_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.3 safety_events

```sql
CREATE TABLE safety_events (
    id                  CHAR(36)        NOT NULL,
    user_id             CHAR(36)        NOT NULL,
    session_id          CHAR(36)        NOT NULL,
    mode                ENUM('conversation','podcast') NOT NULL,

    severity            ENUM('warning','crisis') NOT NULL,
    risk_score          DECIMAL(4,3)    NOT NULL,
    risk_level          TINYINT UNSIGNED NOT NULL,
    risk_category       VARCHAR(50)     NOT NULL,
    risk_indicators     JSON            NOT NULL,
    safety_flags        JSON            NOT NULL,

    action_taken        ENUM('flag','escalate','crisis_response','block') NOT NULL,
    crisis_response     TEXT            NULL,
    pipeline_cancelled  TINYINT(1)      NOT NULL DEFAULT 0,

    trace_id            CHAR(36)        NOT NULL,
    occurred_at         TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    reviewed_at         TIMESTAMP       NULL,
    reviewer_notes      TEXT            NULL,

    PRIMARY KEY (id),
    INDEX ix_user (user_id, occurred_at DESC),
    INDEX ix_severity (severity, occurred_at DESC),
    INDEX ix_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='삭제 금지, 최소 5년 보관';
```

### 6.4 learning_patterns

```sql
CREATE TABLE learning_patterns (
    id                  CHAR(36)        NOT NULL,
    user_id             CHAR(36)        NOT NULL,

    pattern_type        VARCHAR(50)     NOT NULL,
    pattern_key         VARCHAR(100)    NOT NULL,
    pattern_value       JSON            NOT NULL,

    confidence          DECIMAL(3,2)    NOT NULL DEFAULT 0.50,
    sample_count        INT UNSIGNED    NOT NULL DEFAULT 1,

    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE INDEX uix_user_type_key (user_id, pattern_type, pattern_key),
    INDEX ix_confidence (user_id, confidence DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 6.5 pipeline_logs

```sql
CREATE TABLE pipeline_logs (
    id                  CHAR(36)        NOT NULL,
    user_id             CHAR(36)        NOT NULL,
    session_id          CHAR(36)        NOT NULL,
    mode                ENUM('conversation','podcast') NOT NULL,

    trace_id            CHAR(36)        NOT NULL,
    correlation_id      CHAR(36)        NULL,

    status              ENUM('completed','failed','crisis_abort') NOT NULL,
    started_at          TIMESTAMP(3)    NOT NULL,
    completed_at        TIMESTAMP(3)    NULL,
    total_duration_ms   INT UNSIGNED    NULL,

    tier_timings        JSON            NULL,
    iteration_count     TINYINT UNSIGNED NOT NULL DEFAULT 0,

    error_code          VARCHAR(50)     NULL,
    error_message       TEXT            NULL,

    total_input_tokens  INT UNSIGNED    NULL,
    total_output_tokens INT UNSIGNED    NULL,
    llm_calls_count     SMALLINT UNSIGNED NULL,

    PRIMARY KEY (id),
    INDEX ix_trace (trace_id),
    INDEX ix_user (user_id, started_at DESC),
    INDEX ix_status (status, started_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  PARTITION BY RANGE (UNIX_TIMESTAMP(started_at)) (
    PARTITION p2026_q1 VALUES LESS THAN (UNIX_TIMESTAMP('2026-04-01')),
    PARTITION p2026_q2 VALUES LESS THAN (UNIX_TIMESTAMP('2026-07-01')),
    PARTITION p2026_q3 VALUES LESS THAN (UNIX_TIMESTAMP('2026-10-01')),
    PARTITION p2026_q4 VALUES LESS THAN (UNIX_TIMESTAMP('2027-01-01')),
    PARTITION p_future  VALUES LESS THAN MAXVALUE
  );
```

### 6.6 ER 다이어그램

```
(외부: user_id, session_id — FK 없음)
    │
    ├── conversation_history (user_id, session_id, turn_sequence)
    │     ├── pinecone_vector_id → Pinecone (mem_conversation)
    │     └── visualization_url → S3 (이미지)
    │
    ├── podcast_episodes (user_id, session_id)
    │     ├── pinecone_vector_ids → Pinecone (mem_podcast_episode)
    │     └── cover_image_url → S3 (커버 이미지)
    │
    ├── safety_events (user_id, session_id)
    │
    ├── learning_patterns (user_id)
    │
    └── pipeline_logs (user_id, session_id, trace_id)
```

---

## 7. 공통 — Pinecone / S3 / Neo4j 스키마

### 7.1 Pinecone

**인덱스명**: `mind-log-vectors` | **Dimension**: 384 | **Metric**: cosine

| 네임스페이스 | 용도 | 읽는 에이전트 | 쓰는 주체 |
|-------------|------|-------------|----------|
| `mem_conversation` | 과거 대화 검색 | Memory Agent | 안 A: PineconeConsumer / 안 B: VectorPersister |
| `mem_podcast_episode` | 과거 에피소드 검색 | Episode Memory | 동일 |
| `expert_knowledge` | 전문 지식 RAG | Knowledge Agent | 관리자 배치 |

메타데이터 스키마는 v2.0과 동일 (6.2~6.4절).

### 7.2 S3

```
mindlog-images/ (ap-northeast-2)
├── vis/{user_id}/
│   ├── conv/{session_id}/{timestamp}_{emotion}_{id}.webp
│   └── podcast/{episode_id}/cover_{id}.webp
├── shared/templates/
└── temp/ (24시간 자동 삭제)
```

### 7.3 Neo4j (선택 — 추후 도입)

현재 코드에서 Neo4j 사용하는 에이전트 없음. 추후 필요 시 도입.

---

## 8. 안 A vs 안 B 최종 비교

### 8.1 종합 비교표

| 평가 항목 | 안 A (이벤트 드리븐) | 안 B (하이브리드 도메인) |
|----------|--------------------|-----------------------|
| **결합도** | **매우 낮음** — 에이전트는 이벤트만 발행 | 낮음 — CorePersister가 AgentState 구조 일부 알아야 함 |
| **DB 부하 분산** | 파이프라인 실행 중 시간적 분산 | **우선순위별 최적화** (즉시/배치/비동기 3단계) |
| **Pinecone 효율** | 건당 upsert (실시간) | **배치 50건 upsert** (API 호출 50분의 1) |
| **Safety 즉시성** | 이벤트 버스 경유 (약간의 지연 가능) | **직접 동기 호출** (지연 없음) |
| **응답 지연** | **0ms** (이벤트는 fire-and-forget) | **0ms** (fire-and-forget) |
| **에이전트 추가 시** | 이벤트 클래스 + 컨슈머 핸들러 + 구독 등록 | Persister 메서드 또는 파일 추가 |
| **Protected File 수정** | base_agent.py에 1메서드 추가 (1회) | **수정 없음** |
| **데이터 일관성** | 최종 일관성 (이벤트 지연) | 도메인별 선택 (Safety=강한, Vector=최종) |
| **디버깅** | 이벤트 추적 필요 (발행→큐→핸들러) | 직관적 (Persister → DB) |
| **conversation_history 통합** | 여러 이벤트 조합 필요 (조율 복잡) | **CorePersister가 한번에 통합** |
| **확장성 (Phase 2)** | Redis Streams로 교체 (에이전트 무변경) | VectorPersister 배치 크기 조절 |
| **인프라** | asyncio.Queue (외부 없음) | asyncio.Queue (외부 없음) |
| **구현 공수** | ~3일 (이벤트 + 버스 + 컨슈머 3개) | ~3일 (Persister 4개 + 오케스트레이터) |
| **학습 곡선** | 이벤트 드리븐 패턴 이해 필요 | **낮음** (직관적인 함수 호출) |

### 8.2 상황별 권장

| 상황 | 권장 안 | 이유 |
|------|--------|------|
| 에이전트가 빈번하게 추가/변경됨 | **안 A** | 이벤트만 추가하면 되므로 변경 범위 최소 |
| DB 부하 최적화가 최우선 | **안 B** | 배치 + 우선순위로 부하를 세밀하게 제어 |
| Safety 데이터 유실 절대 불가 | **안 B** | Safety 동기 저장이 아키텍처에 내장 |
| 향후 Kafka/Redis 도입 계획 | **안 A** | EventBus 교체만으로 분산 메시징 전환 |
| conversation_history 통합 저장 | **안 B** | CorePersister가 여러 필드를 조합 |
| 3명 팀 빠른 구현 | **안 B** | 직관적, 학습 곡선 낮음 |

### 8.3 두 안의 결합도 가능 여부

두 안은 **상호 배타적이 아니다.** 결합 가능:

```
Phase 1: 안 B (하이브리드 도메인)로 빠르게 구현
Phase 2: 에이전트에 emit_event()를 추가 (안 A의 이벤트 발행)
         → CorePersister를 이벤트 컨슈머로 리팩토링
         → 점진적으로 안 A 구조로 진화
```

---

## 9. 추적 가능성 체계

### 9.1 ID 체계 (두 안 공통)

```
trace_id:    외부에서 받거나 우리가 생성. 파이프라인 1회 실행 식별.
session_id:  외부에서 받음. 세션(여러 턴/에피소드) 묶음.
user_id:     외부에서 받음. 사용자 식별.
event_id:    (안 A만) 이벤트 고유 ID. 이벤트 추적용.
```

### 9.2 추적 흐름

```
외부 요청 (user_id, session_id, trace_id)
    ↓
LangGraph 파이프라인 (동일 trace_id)
    ↓
영속화 (안 A: 이벤트에 trace_id 포함 / 안 B: Persister에 trace_id 전달)
    ├── conversation_history.trace_id
    ├── podcast_episodes.trace_id
    ├── safety_events.trace_id
    └── pipeline_logs.trace_id
```

```sql
-- trace_id 하나로 전체 흐름 조회
SELECT * FROM pipeline_logs WHERE trace_id = ?;
SELECT * FROM conversation_history WHERE trace_id = ?;
SELECT * FROM safety_events WHERE trace_id = ?;
```

---

## 10. 데이터 라이프사이클

| 테이블 | 활성 보관 | 아카이브/삭제 |
|--------|---------|------------|
| conversation_history | 6개월 | 파티션 스왑 → cold storage. 2년 후 삭제 |
| podcast_episodes | 무기한 | 사용자 요청 시만 삭제 |
| safety_events | **5년 (법적 의무)** | 삭제 금지. 탈퇴 시 user_id 익명화 |
| learning_patterns | 무기한 | 탈퇴 시 삭제 |
| pipeline_logs | 1개월 | 3개월 후 삭제 |

**사용자 데이터 삭제 (탈퇴 시)**:
```
1. Pinecone: user_id 필터로 벡터 삭제
2. S3: vis/{user_id}/ prefix 전체 삭제
3. MySQL: conversation_history, podcast_episodes, learning_patterns 삭제
4. MySQL: safety_events는 삭제 안 함 → user_id='ANONYMIZED'로 업데이트
```

---

## 부록: 파일 구조 비교

### 안 A 파일 구조

```
src/persistence/
    __init__.py
    events.py              # DomainEvent 정의 (~10개 이벤트 클래스)
    event_bus.py           # EventBus (asyncio.Queue)
    setup.py               # 구독 등록
    consumers/
        __init__.py
        mysql_consumer.py  # MySQL 저장 핸들러
        pinecone_consumer.py
        s3_consumer.py
```

### 안 B 파일 구조

```
src/persistence/
    __init__.py
    base_persister.py      # BasePersister ABC
    orchestrator.py        # PersistenceOrchestrator
    safety_persister.py    # 즉시 동기
    core_persister.py      # MySQL 핵심 데이터
    vector_persister.py    # Pinecone 배치
    asset_persister.py     # S3 비동기
    dlq.py                 # Dead Letter Queue
src/pipeline/
    runner.py              # 파이프라인 실행 + 영속화 통합
```

---

## 부록: 기존 코드와의 호환

| 기존 파일 | 관계 |
|----------|------|
| `src/models/agent_state.py` | 두 안 모두 읽기만 함 (수정 안 함) |
| `src/models/message.py` | trace_id 전파에 사용 |
| `src/api/contracts.py` | SaveRequest/LoadResponse 그대로 사용 |
| `src/api/client.py` | BackendClient를 컨슈머/Persister가 내부에서 사용 |
| `src/agents/shared/base_agent.py` | 안 A: emit_event() 1메서드 추가 / 안 B: 변경 없음 |
| `src/graph/workflow.py` | **두 안 모두 수정 안 함** |

---

*마지막 업데이트: 2026-03-03 v3.0*

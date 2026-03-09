# Mind-Log 파이프라인 중간 결과 외부 전달 가이드

> **작성일**: 2026-03-09
> **관련 문서**: `docs/guides/INFRA_DEPLOYMENT_GUIDE.md` 섹션 3-3-c (팟캐스트 라우트)
> **대상 모드**: 팟캐스트모드 (대화모드 향후 확장 대비 포함)

팟캐스트 파이프라인 실행 중, 특정 에이전트 결과를 파이프라인 완료 전에 즉시 Backend에 전달하는 구조를 설계한다.

---

## 목차

1. [코드 점검 결과](#1-코드-점검-결과)
2. [중간 전달 대상](#2-중간-전달-대상)
3. [현재 코드 흐름 분석](#3-현재-코드-흐름-분석)
4. [설계: PipelineRunner 패턴](#4-설계-pipelinerunner-패턴)
5. [구현 상세](#5-구현-상세)
6. [실패 처리](#6-실패-처리)
7. [검증 방법](#7-검증-방법)
8. [파일 요약](#8-파일-요약)

---

## 1. 코드 점검 결과

파이프라인 최종 상태(`ainvoke()` 반환값)에 대한 점검 결과:

| 항목 | 결과 | 근거 |
|------|------|------|
| `ainvoke()` 최종 상태에 `final_output` 포함 | ✅ 확인 | `script_personalizer` 노드가 반환 |
| `ainvoke()` 최종 상태에 `visual_data` 포함 | ✅ 확인 | `async_post` 노드가 실제 그래프 노드 — fire-and-forget 아님 |
| TIER 1 fan-in/fan-out 정상 동작 | ✅ 확인 | 모든 TIER 1 에이전트 완료 후에야 TIER 2 시작 |
| `PodcastEpisodeResponse` JSON에 모든 데이터 포함 | ✅ 확인 | episode, emotion, safety_alert, cover_image 모두 매핑됨 |

### async_post 노드 동작 확인

`async_post_processing_node`은 이름과 달리 fire-and-forget이 **아니다**.
LangGraph StateGraph의 실제 노드로 등록되어 있으며(`workflow.py:628`),
`script_personalizer → async_post → END` 엣지로 연결된다(`workflow.py:654-655`).

```python
# workflow.py:407-428
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    tasks = [
        asyncio.create_task(visualization_node(state)),
        asyncio.create_task(telemetry_node(state)),
        asyncio.create_task(learning_node(state)),
    ]
    results: dict[str, Any] = {}
    for task in asyncio.as_completed(tasks):
        try:
            result = await task
            results.update(result)       # ← 모든 결과 수집
        except Exception:
            logger.exception("[ASYNC] 비동기 후처리 태스크 실패 — 무시")
    return results                       # ← 그래프에 반환 → 최종 상태에 병합
```

`ainvoke()`는 `async_post → END` 완료 후에 반환하므로, `visual_data`가 최종 상태에 포함된다.

---

## 2. 중간 전달 대상

최종 응답에 이미 모든 데이터가 포함되므로, **별도 중간 전달이 필요한 데이터는 2개뿐**이다:

| 데이터 | 에이전트 | TIER | 중간 전달 이유 |
|--------|---------|------|---------------|
| `content_analysis` | Content Analyzer | TIER 1 | 파이프라인 완료 전에 Backend에서 먼저 저장/활용 필요 |
| `emotion_vectors` | Emotion Agent | TIER 1 | 파이프라인 완료 전에 Backend에서 먼저 저장/활용 필요 |

**별도 전달 불필요:**
- `final_output` — 최종 `PodcastEpisodeResponse` JSON에 포함
- `visual_data` — 최종 `PodcastEpisodeResponse` JSON에 포함

---

## 3. 현재 코드 흐름 분석

### 팟캐스트 파이프라인 전체 흐름

```
intent_classifier → tier1_podcast(fan-out) → script_generator → batch_validator
→ script_personalizer → async_post(Visualization+Telemetry+Learning) → END
```

### tier1_podcast_fan_out — 중간 전달 포인트

참조: `src/graph/workflow.py:330-401`

```python
async def tier1_podcast_fan_out(state: AgentState) -> dict[str, Any]:
    writer = _get_writer()
    cancel_event = asyncio.Event()
    tier_start = time.monotonic()
    agent_names = ["safety", "emotion", "content_analyzer", "podcast_reasoning"]

    writer({"event": "tier_start", "tier": 1, "mode": "podcast", "agents": agent_names})

    # 4개 에이전트 병렬 실행
    tasks = [
        run_with_cancel(safety_node(state), cancel_event, "safety"),
        run_with_cancel(emotion_node(state), cancel_event, "emotion"),
        run_with_cancel(content_analyzer_node(state), cancel_event, "content_analyzer"),
        run_with_cancel(podcast_reasoning_node(state), cancel_event, "podcast_reasoning"),
    ]

    merged: dict[str, Any] = {}
    completed_count = 0
    for coro in asyncio.as_completed(tasks):
        name, result = await coro
        completed_count += 1
        elapsed_ms = int((time.monotonic() - tier_start) * 1000)

        # CRISIS 체크 (Safety Agent)
        if name == "safety" and result.get("safety_flags", {}).get("status") == "crisis":
            cancel_event.set()
            # ... CRISIS 처리 ...
            return {**deep_result, "next_step": "crisis_response"}

        # ★ 에이전트 완료 이벤트 발행 (현재: 데이터 미포함)
        writer({
            "event": "agent_complete",
            "tier": 1,
            "agent": name,               # ← "content_analyzer" 또는 "emotion"
            "elapsed_ms": elapsed_ms,
            "progress": f"{completed_count}/{len(agent_names)}",
        })
        merged.update(result)

    writer({"event": "tier_end", "tier": 1, "mode": "podcast", "status": "ok", ...})
    return merged                         # ← fan-in: 모든 결과 병합 후 TIER 2로 전달
```

**핵심:**
- 에이전트가 완료되는 시점(line 384-390)에 `name`과 `result`를 이미 알고 있다
- 이 시점에 `agent_complete` 이벤트에 `result`를 포함시키면, 외부에서 중간 결과를 식별 가능
- `asyncio.as_completed()`로 완료 순서대로 처리하므로, 먼저 끝나는 에이전트 결과가 즉시 전달됨

### LangGraph `updates` 스트림의 제약

`tier1_podcast`는 LangGraph에서 **단일 노드**로 등록됨:

```python
# workflow.py:623
graph.add_node("tier1_podcast", tier1_podcast_fan_out)
```

LangGraph의 `stream_mode="updates"`는 노드 단위로 상태 변경을 보고한다.
따라서 TIER 1 내부 4개 에이전트의 개별 결과는 `updates`에서 분리되지 않는다.

→ **`custom` 이벤트(writer())를 통해서만** TIER 1 내부 에이전트별 결과를 식별할 수 있다.

### 기존 인프라 활용 포인트

| 인프라 | 위치 | 역할 |
|--------|------|------|
| `_get_writer()` | workflow.py:49-59 | LangGraph 커스텀 이벤트 발행 (no-op 폴백 포함) |
| `astream(stream_mode=["updates", "custom"])` | workflow.py:796-804 | 스트림 모드 소비 패턴 |
| `agent_complete` 이벤트 | workflow.py:384-390 | 이미 TIER 1 fan-out에서 발행 (현재 데이터 미포함) |
| `BackendClient.save()` | src/api/client.py | `@with_retry(max_retries=3)` 재시도 로직 내장 |
| `SaveRequest` | src/api/contracts.py | Backend 저장 요청 스키마 |

---

## 4. 설계: PipelineRunner 패턴

### 핵심 아이디어

1. `ainvoke()` → `astream()`으로 교체 (PipelineRunner 내부에서만)
2. 스트림을 내부적으로 소비하면서, Content Analyzer/Emotion 완료 시 Backend에 즉시 저장
3. **API 응답은 기존과 동일한 `PodcastEpisodeResponse` JSON 유지**
4. workflow.py의 `agent_complete` 이벤트에 `"data": result` 필드 1줄 추가

### 왜 이 방식인가

| 특성 | 설명 |
|------|------|
| 에이전트 코드 수정 | ❌ 없음 |
| API 응답 형식 변경 | ❌ 없음 (기존 JSON 유지) |
| 프론트엔드 변경 | ❌ 없음 |
| workflow.py 변경 | 1줄 추가 (하위 호환) |
| INFRA_DEPLOYMENT_GUIDE.md 호환 | ✅ 기존 코드 확장 |
| 실패 안전성 | ✅ Backend 저장 실패해도 파이프라인 정상 진행 |
| 향후 SSE 확장 | ✅ PipelineRunner에 yield 모드 추가로 가능 |

### 아키텍처 흐름

```
POST /api/v1/podcasts/episodes (JSON)
         │
         ▼
┌──── podcasts.py ─────────────────────┐
│ 1. PodcastRequest → AgentState       │
│ 2. PipelineRunner.run_podcast()      │
│ 3. result → PodcastEpisodeResponse   │
│ 4. return JSON (기존과 동일)          │
└────────────┬─────────────────────────┘
             │
             ▼
┌──── PipelineRunner ──────────────────┐
│                                       │
│ compiled.astream(stream_mode=         │
│   ["updates", "custom"])              │
│                                       │
│ 스트림 소비 루프:                      │
│  custom 이벤트 수신 시:                │
│   agent="content_analyzer" + data?    │
│     → asyncio.create_task(            │
│         backend.save(                 │
│           "content_analysis"))        ← ① 즉시 전달
│   agent="emotion" + data?             │
│     → asyncio.create_task(            │
│         backend.save(                 │
│           "emotion_log"))             ← ② 즉시 전달
│                                       │
│ return final_state (ainvoke와 동일)   │
└───────────────────────────────────────┘
         │                    │
         ▼                    ▼ (fire-and-forget)
  최종 JSON 응답         Backend (app-3:8080)
  (모든 데이터 포함)      중간 결과 저장
```

### 데이터 흐름 상세

#### ① Content Analyzer 중간 전달

```
TIER 1 fan-out 내부:
  content_analyzer_node(state) 완료
  ↓
  writer({
    "event": "agent_complete",
    "agent": "content_analyzer",
    "data": result                     ← workflow.py 추가분
  })
  ↓
  PipelineRunner._handle_custom_event()
  ↓ agent == "content_analyzer" 매칭
  ↓ data["content_analysis"] 추출
  asyncio.create_task(
    backend.save("content_analysis", SaveRequest(...))
  )
  ↓
  POST http://app-3:8080/api/v1/content_analysis
  {user_id, session_id, type: "content_analysis", data: {...}}
```

#### ② Emotion Agent 중간 전달

```
TIER 1 fan-out 내부:
  emotion_node(state) 완료
  ↓
  writer({
    "event": "agent_complete",
    "agent": "emotion",
    "data": result                     ← workflow.py 추가분
  })
  ↓
  PipelineRunner._handle_custom_event()
  ↓ agent == "emotion" 매칭
  ↓ data["emotion_vectors"] 추출
  asyncio.create_task(
    backend.save("emotion_log", SaveRequest(...))
  )
  ↓
  POST http://app-3:8080/api/v1/emotion_log
  {user_id, session_id, type: "emotion_log", data: {...}}
```

---

## 5. 구현 상세

### 5-1. `src/graph/workflow.py` 수정 (보호 파일 — 3인 승인 필요)

**변경량: 1줄 추가 × 2곳**

#### 위치 1: `tier1_podcast_fan_out()` line 384-390

```python
# 현재 코드:
writer({
    "event": "agent_complete",
    "tier": 1,
    "agent": name,
    "elapsed_ms": elapsed_ms,
    "progress": f"{completed_count}/{len(agent_names)}",
})

# 변경 후:
writer({
    "event": "agent_complete",
    "tier": 1,
    "agent": name,
    "elapsed_ms": elapsed_ms,
    "progress": f"{completed_count}/{len(agent_names)}",
    "data": result,  # ← 1줄 추가
})
```

#### 위치 2: `tier1_conversation_fan_out()` line 309-315

동일한 변경 적용 (대화모드 향후 확장 대비).

#### 하위 호환성 분석

- 기존 스트림 소비자(`tier_start`, `agent_complete`, `tier_end`의 `event`, `tier`, `agent` 필드만 읽는 코드)는 `data` 필드를 무시한다
- Python dict에 새 키를 추가하는 것은 하위 호환
- `tests/monitoring/test_streaming.py`의 `agent_complete` 이벤트 검증에서 `data` 필드가 있어도 통과한다 (dict subset matching)

---

### 5-2. `src/api/pipeline_runner.py` 신규 생성

참조 파일:
- `src/api/client.py` — `BackendClient.save()` 메서드
- `src/api/contracts.py` — `SaveRequest` 스키마
- `src/monitoring/callbacks.py` — `MindLogTelemetryCallback`

```python
"""
파이프라인 실행기 — astream() 소비 + 중간 결과 Backend 저장.

ainvoke() 대신 astream()을 사용하여 스트림을 내부적으로 소비하고,
Content Analyzer / Emotion 완료 시 BackendClient.save()를 즉시 호출한다.
API 응답 형식은 변경되지 않는다 (최종 상태를 ainvoke()와 동일하게 반환).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.api.client import BackendClient
from src.api.contracts import SaveRequest
from src.monitoring.callbacks import MindLogTelemetryCallback

logger = logging.getLogger("mind-log.api.pipeline_runner")

# TIER 1 fan-out 내부에서 중간 전달할 에이전트 목록
# agent_name: (state_field_key, backend_resource_type)
_INTERMEDIATE_TARGETS: dict[str, tuple[str, str]] = {
    "content_analyzer": ("content_analysis", "content_analysis"),
    "emotion": ("emotion_vectors", "emotion_log"),
}


class PipelineRunner:
    """LangGraph 파이프라인을 실행하고 중간 결과를 Backend에 전달한다.

    ainvoke()와 동일한 최종 상태 dict를 반환하지만,
    파이프라인 실행 중 특정 에이전트 완료 시 Backend에 즉시 저장한다.
    """

    def __init__(
        self,
        compiled_graph: Any,
        backend_client: BackendClient,
    ) -> None:
        self._graph = compiled_graph
        self._backend = backend_client

    async def run_podcast(
        self,
        state: dict[str, Any],
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        팟캐스트 파이프라인을 실행한다.

        astream()으로 스트림을 내부 소비하며:
        - content_analyzer / emotion 완료 시 Backend에 즉시 저장
        - 최종 상태를 ainvoke()와 동일한 dict로 반환

        Args:
            state: AgentState 초기 상태
            session_id: 세션 ID
            user_id: 사용자 ID

        Returns:
            최종 AgentState dict (podcasts.py에서 응답 매핑에 사용)
        """
        callback = MindLogTelemetryCallback()
        config = {
            "configurable": {"thread_id": f"session_{session_id}"},
            "callbacks": [callback],
        }

        final_state: dict[str, Any] = {}

        async for mode, chunk in self._graph.astream(
            state,
            config=config,
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom":
                # 커스텀 이벤트: agent_complete에서 중간 결과 처리
                self._handle_custom_event(chunk, session_id, user_id)
            elif mode == "updates":
                # updates: {"node_name": {state_changes}}
                # 각 노드 완료 시 상태 변경을 누적 (ainvoke와 동일한 최종 상태 구성)
                for node_name, node_output in chunk.items():
                    final_state.update(node_output)

        return final_state

    def _handle_custom_event(
        self,
        event: dict[str, Any],
        session_id: str,
        user_id: str,
    ) -> None:
        """agent_complete 이벤트에서 중간 결과를 Backend로 전달한다.

        _INTERMEDIATE_TARGETS에 정의된 에이전트(content_analyzer, emotion)의
        완료 이벤트에 data 필드가 있으면, 해당 데이터를 Backend에 비동기 저장한다.
        """
        if event.get("event") != "agent_complete":
            return

        agent_name = event.get("agent", "")
        data = event.get("data")

        # data 필드가 없거나 대상 에이전트가 아니면 무시
        if not data or agent_name not in _INTERMEDIATE_TARGETS:
            return

        field_key, resource_type = _INTERMEDIATE_TARGETS[agent_name]
        field_data = data.get(field_key)
        if field_data is None:
            return

        logger.info(
            "[중간전달] %s 완료 → Backend 저장 (%s)", agent_name, resource_type
        )
        asyncio.create_task(
            self._save_to_backend(resource_type, field_data, session_id, user_id)
        )

    async def _save_to_backend(
        self,
        resource_type: str,
        data: Any,
        session_id: str,
        user_id: str,
    ) -> None:
        """Backend에 비동기 저장한다. 실패해도 파이프라인에 영향 없음.

        BackendClient.save()는 @with_retry(max_retries=3)가 내장되어 있으므로,
        일시적 네트워크 오류는 자동 재시도된다.
        """
        try:
            request = SaveRequest(
                user_id=user_id,
                session_id=session_id,
                type=resource_type,
                data=data if isinstance(data, dict) else {"value": data},
                timestamp=datetime.now(timezone.utc),
            )
            await self._backend.save(resource_type, request)
            logger.info("[저장완료] %s", resource_type)
        except Exception:
            # 저장 실패는 WARNING — 파이프라인 정상 진행
            # 최종 JSON 응답에 모든 데이터가 포함되므로 데이터 유실 없음
            logger.warning(
                "[저장실패] %s — 파이프라인 정상 진행",
                resource_type,
                exc_info=True,
            )
```

---

### 5-3. `src/api/routes/podcasts.py` 수정

`docs/guides/INFRA_DEPLOYMENT_GUIDE.md` 섹션 3-3-c의 코드를 기반으로, `ainvoke()` 호출 부분만 교체한다.

#### 변경 전 (INFRA_DEPLOYMENT_GUIDE.md 코드)

```python
@router.post("/podcasts/episodes", response_model=PodcastEpisodeResponse)
async def create_episode(req: PodcastRequest, request: Request) -> PodcastEpisodeResponse:
    start_time = time.time()
    compiled_graph = request.app.state.compiled_graph

    # 1. AgentState 구성
    state = _build_agent_state(req)

    # 2. 파이프라인 실행
    callback = MindLogTelemetryCallback()
    config = {
        "configurable": {"thread_id": f"session_{req.session_id}"},
        "callbacks": [callback],
    }
    result = await compiled_graph.ainvoke(state, config=config)  # ← 여기만 변경

    # 3. 결과 매핑
    duration_ms = int((time.time() - start_time) * 1000)
    # ... (응답 매핑 로직은 그대로 유지) ...
```

#### 변경 후

```python
from src.api.pipeline_runner import PipelineRunner

@router.post("/podcasts/episodes", response_model=PodcastEpisodeResponse)
async def create_episode(req: PodcastRequest, request: Request) -> PodcastEpisodeResponse:
    start_time = time.time()

    # 1. AgentState 구성
    state = _build_agent_state(req)

    # 2. 파이프라인 실행 (PipelineRunner: 중간 결과 Backend 전달 + 최종 상태 반환)
    runner = PipelineRunner(
        compiled_graph=request.app.state.compiled_graph,
        backend_client=request.app.state.backend_client,
    )
    result = await runner.run_podcast(
        state=state,
        session_id=req.session_id,
        user_id=req.user_id,
    )

    # 3. 결과 매핑 (기존과 동일)
    duration_ms = int((time.time() - start_time) * 1000)
    # ... (응답 매핑 로직은 그대로 유지) ...
```

**변경 요약:**
- `MindLogTelemetryCallback()` 생성 → PipelineRunner 내부로 이동
- `compiled_graph.ainvoke(state, config)` → `runner.run_podcast(state, session_id, user_id)` 교체
- 나머지 코드(응답 매핑 함수 `_build_episode_data`, `_extract_emotion`, `_extract_safety_alert`, `_extract_cover_image`)는 그대로 유지

---

## 6. 실패 처리

### 중간 저장 실패 시 동작

| 상황 | 동작 | 데이터 복구 |
|------|------|------------|
| `content_analysis` Backend 저장 실패 | WARNING 로그 출력. 파이프라인 정상 진행. | 최종 JSON 응답의 `episode` 필드에 포함됨 |
| `emotion_vectors` Backend 저장 실패 | WARNING 로그 출력. 파이프라인 정상 진행. | 최종 JSON 응답의 `emotion` 필드에 포함됨 |
| Backend 전체 다운 | 2건 모두 WARNING. 파이프라인 정상 진행. | 최종 JSON 응답으로 모든 데이터 복구 가능 |
| 파이프라인 중간 실패 | 이미 저장된 중간 결과는 Backend에 유지. `ErrorResponse` 반환. | Backend에 부분 데이터 존재 (디버깅 활용) |

### 안전 설계 원칙

- `asyncio.create_task()`로 fire-and-forget 실행 → 파이프라인 블로킹 없음
- `BackendClient.save()`의 `@with_retry(max_retries=3)` → 일시적 오류 자동 재시도
- 모든 예외는 `_save_to_backend()` 내부에서 catch → 파이프라인에 전파되지 않음
- 최종 JSON 응답에 모든 데이터가 포함되므로, 중간 저장 실패 시에도 데이터 유실 없음

---

## 7. 검증 방법

### 단위 테스트

Mock compiled_graph + Mock BackendClient로 PipelineRunner를 테스트한다:

```python
@pytest.mark.asyncio
async def test_pipeline_runner_saves_content_analysis():
    """content_analyzer 완료 시 Backend에 저장되는지 확인."""
    mock_backend = AsyncMock(spec=BackendClient)

    # custom 이벤트를 발행하는 mock astream
    async def mock_astream(state, config, stream_mode):
        yield ("custom", {
            "event": "agent_complete",
            "agent": "content_analyzer",
            "data": {"content_analysis": {"topic": "test", "themes": []}},
        })
        yield ("updates", {
            "tier1_podcast": {"content_analysis": {...}, "emotion_vectors": {...}},
        })

    mock_graph = AsyncMock()
    mock_graph.astream = mock_astream

    runner = PipelineRunner(mock_graph, mock_backend)
    result = await runner.run_podcast(state={...}, session_id="s1", user_id="u1")

    # Backend save 호출 확인
    mock_backend.save.assert_any_call("content_analysis", ANY)
```

### 검증 항목

- [ ] `content_analyzer` 완료 시 `save("content_analysis")` 호출됨
- [ ] `emotion` 완료 시 `save("emotion_log")` 호출됨
- [ ] Backend 실패 시에도 `final_state` 정상 반환됨
- [ ] `data` 필드 없는 기존 `agent_complete` 이벤트는 무시됨
- [ ] `safety`, `podcast_reasoning` 등 대상이 아닌 에이전트는 무시됨

### 기존 테스트 회귀

- [ ] `pytest tests/ -v` 전체 통과
- [ ] `tests/monitoring/test_streaming.py` 통과 (workflow.py `"data": result` 추가 하위호환 확인)

### 통합 테스트 (선택)

- [ ] `POST /api/v1/podcasts/episodes` → JSON 응답 정상 (기존과 동일한 스키마)
- [ ] Backend mock 서버에 2건의 중간 저장 요청 도착 확인

---

## 8. 파일 요약

| 파일 | 작업 | 보호 등급 | 변경량 |
|------|------|----------|-------|
| `src/graph/workflow.py` | `"data": result` 추가 (line 384, 309) | 🔒 보호 (3인 승인) | 2줄 |
| `src/api/pipeline_runner.py` | 신규 생성 | 일반 | ~100줄 |
| `src/api/routes/podcasts.py` | `ainvoke()` → `PipelineRunner` 교체 | 일반 | ~10줄 변경 |
| 에이전트 코드 전체 | 변경 없음 | — | — |
| `src/api/client.py` | 변경 없음 (기존 save() 재사용) | — | — |
| `src/api/contracts.py` | 변경 없음 (기존 SaveRequest 재사용) | 🔒 보호 | — |
| `src/models/agent_state.py` | 변경 없음 | 🔒 보호 | — |

---

*마지막 업데이트: 2026-03-09*

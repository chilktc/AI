# Safety CRISIS 표출 및 백엔드 연동 수정 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safety Agent의 CRISIS 판정 시 발생하는 화면 표출 오류·백엔드 빈 에피소드 오저장을 수정하고, LLM이 생성한 CRISIS 메시지를 프론트엔드에 올바르게 전달한다.

**Architecture:**
현재 CRISIS 흐름에서 `final_output`이 평문으로 설정되는데 API 핸들러가 이를 JSON으로 파싱을 시도하여 조용히 실패, 빈 에피소드(`ep_fallback`)를 백엔드에 오저장하는 버그 체인이 존재한다. `src/api/routes/podcasts.py`에 CRISIS 조기 분기를 추가하여 에피소드 저장을 건너뛰고, `SlimPodcastResponse`에 `crisis_message` 필드를 추가하여 LLM reasons를 포함한 메시지를 프론트엔드에 전달한다. 백엔드 safety_alert 저장 API는 현재 미존재하므로 상수/모델만 선언하고 실제 활성화는 백엔드팀 협의 후 별도 처리한다.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest, asyncio, LangGraph

---

## 변경 대상 파일 목록

| 파일 | 변경 유형 | 담당 영역 |
|------|---------|---------|
| `src/api/external_schemas.py` | Modify | 공용 스키마 (전원 리뷰) |
| `src/api/routes/podcasts.py` | Modify | 개발자1 (feature/analysis-*) |
| `src/api/backend_resources.py` | Modify | 공용 인프라 (인터페이스 추가만) |
| `tests/api/conftest.py` | Modify | 개발자1 |
| `tests/api/test_podcasts_endpoint.py` | Modify | 개발자1 |
| `tests/integration/conftest.py` | Modify | 모든 개발자 |
| `tests/integration/test_crisis_preemption.py` | Modify | 개발자3 (검증) |

> **Protected File 제외**: `src/graph/workflow.py`(CRISIS 라우팅 정상), `src/api/contracts.py`(백엔드팀 협의 후 별도 PR)는 이번 계획에서 수정하지 않는다.
> `src/api/external_schemas.py` 수정은 공용 스키마이므로 PR 전 전원 리뷰 필수.

---

## 현재 CRISIS 흐름 워크플로우 (버그 포함)

```
[AI 서버 — 현재 버그 있는 흐름]

[T+0ms]     사용자 입력 수신
              └─ POST /api/podcasts/episodes 또는 /episodes/stream

[T+10ms]    compiled_graph.ainvoke() / astream() 시작

[T+100ms]   TIER 0: intent_classifier (TIER0_TIMEOUT 기본값 내)
              └─ risk_flag 감지 시 safety_flags 1차 초기화

[T+2000ms]  TIER 1 병렬 Fan-out 시작 (TIER1_TIMEOUT=240s)
              ├─ safety_node()          ← LLM 호출 (Sonnet)
              ├─ emotion_node()         ← LLM 호출 + AgentDataPublisher.publish()
              │   └─ [T+2500ms] emotion_logs → POST /greenroom/ingest/ai/emotion_logs
              │       ※ Safety 취소보다 먼저 완료될 수 있음 (타이밍 불확정)
              ├─ content_analyzer_node()
              └─ podcast_reasoning_node()

[T+3500ms]  safety_node() CRISIS 판정 (첫 번째 완료)
              ├─ result = {safety_flags:{status:"crisis", required_in_script:[SAFETY_MSG, ...LLM_reasons]},
              │            risk_level:4, risk_score:0.95, next_step:"crisis_response"}
              ├─ cancel_event.set()  ← 나머지 3개 태스크 취소 신호
              ├─ partial_results에 {safety_flags, risk_level, risk_score, next_step:"crisis_response"} 선저장
              └─ _safety_deep_crisis(result) 호출:
                  crisis_msg = "\n".join(required_in_script)
                  └─ 평문 예시: "본 서비스는 AI 모델에...\n\n[전문 상담 기관 안내]\n- 자살예방..."
                  └─ return {safety_flags, risk_level:4, risk_score:0.95, final_output:crisis_msg}

[T+3500ms~] emotion/content/reasoning 태스크 취소 시도
              └─ run_with_cancel() → task.cancel() → CancelledError 전파
              ※ emotion publish()는 try/except로 예외 흡수 → 부분 저장 or 저장 완료 상태

[T+3600ms]  tier1_podcast_fan_out() 반환:
              {safety_flags, risk_level, risk_score, final_output:"평문크리시스메시지", next_step:"crisis_response"}

[T+3600ms]  route_after_tier1() → "crisis_response"

[T+3600ms]  crisis_response_node():
              └─ if state.get("final_output"): return {next_step:"end"}  ← final_output 이미 있으므로 pass

[T+3600ms]  END (async_post 미실행: Learning/Episode Memory 저장 안 됨)

[T+3600ms]  ainvoke() 완료 → final_state 반환

─────── 여기서부터 버그 발생 ───────

[BUG-1] _build_episode_data(final_state):
          output_str = final_state["final_output"]  → "본 서비스는 AI..." (평문)
          json.loads(output_str)  → JSONDecodeError 발생
          except JSONDecodeError: script_data = {}  ← 조용히 빈 dict
          └─ 반환: PodcastEpisodeData(
               episode_id="ep_fallback",   ← 하드코딩 fallback
               script_text="",             ← 빈 문자열
               episode_title="무제 에피소드",
               total_duration=0, ...
             )

[BUG-2] _save_core_data() 호출 (CRISIS 분기 없음):
          (1) asyncio.gather(
                POST /greenroom/ingest/ai/podcast_metadata
                  payload: {episode_id:"ep_fallback", script_text:"", safety_status:"crisis", ...}
                  → 백엔드 400 or 쓰레기 레코드 저장
                  @with_retry 3회 재시도 (모두 실패 시 logger.warning만)
                POST /greenroom/ingest/ai/podcast_episodes
                  payload: {text:"", title:"무제 에피소드", image_url:""}
                  → 빈 수집 전송
              )
          (2) visual_data_raw is None → visualization 저장 스킵 ← 이건 정상

[BUG-3] SlimPodcastResponse 반환:
          episode_id = "ep_fallback"     ← 의미없는 ID
          safety_alert = SafetyAlertData(
            status="crisis",
            alert_message=SAFETY_MESSAGES["crisis"],  ← 고정 문구 (LLM reasons 소실)
            helpline_info=[...]                         ← alert_message 내용과 중복
          )
          ※ crisis_message 필드 없음 → LLM이 생성한 위기 분석 이유가 프론트엔드에 전달 안 됨

[프론트엔드 증상]
  - safety_alert는 정상 수신 → CRISIS UI 렌더 가능
  - episode_id="ep_fallback"으로 에피소드 조회 시도 → 빈 스크립트 표시 or 404
  - LLM reasons 없는 고정 메시지만 표시
  - 중복 헬프라인 표시 가능성
```

---

## 수정 후 목표 CRISIS 흐름 워크플로우

```
[AI 서버 — 수정 후 흐름]

[T+0ms]     사용자 입력 수신

[T+3600ms]  ainvoke() 완료 → final_state 반환 (워크플로우 내부 동일)

─────── 수정된 API 핸들러 ───────

[FIX-1] CRISIS 조기 감지:
          is_crisis = (final_state.get("safety_flags", {}).get("status") == "crisis")

          if is_crisis:
            ├─ _build_episode_data 스킵
            ├─ _save_core_data 스킵  ← DB 오염 없음
            └─ crisis_message = final_state.get("final_output", "")
               (LLM reasons 포함된 평문 메시지)

[FIX-2] _extract_safety_alert() 호출 → SafetyAlertData 정상 생성

[FIX-3] SlimPodcastResponse 반환:
          episode_id = None               ← CRISIS 시 에피소드 없음
          safety_alert = SafetyAlertData(
            status="crisis",
            alert_message=SAFETY_MESSAGES["crisis"],
            helpline_info=[...]
          )
          crisis_message = "본 서비스는...\n\n[자살예방: 109]\n[이유: 자해 표현 감지...]"
          ← LLM reasons 포함 전달

[프론트엔드 — 수정 후]
  - episode_id == null → 에피소드 플레이어 비활성화 (CRISIS UI로 전환)
  - safety_alert로 CRISIS 배너 렌더링
  - crisis_message로 개인화된 위기 메시지 표시
  - DB: episode 오저장 없음 (clean)

[백엔드 연동 — 현재 미구현, 추후 협의]
  - RESOURCE_SAFETY_EVENT = "safety_events" 상수 선언 (준비만)
  - 백엔드팀과 API 스펙 합의 후 실제 저장 호출 활성화
```

---

## Task 1: 테스트 기반 구축 — fixture 수정 및 누락 케이스 추가

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/api/conftest.py`
- Modify: `tests/api/test_podcasts_endpoint.py`

- [ ] **Step 1-1: `tests/integration/conftest.py` — `mock_safety_crisis_result` fixture를 실제 SafetyAgent 출력 포맷으로 수정**

현재 fixture의 문제:
- `crisis_response` 키 존재 (실제 SafetyAgent 출력에 없음)
- `required_in_script` 누락
- `safety_flags` 내부 구조가 실제 safety.py:101-110과 불일치

`tests/integration/conftest.py`의 `mock_safety_crisis_result` fixture를 찾아 아래와 같이 수정:

```python
@pytest.fixture
def mock_safety_crisis_result() -> dict[str, Any]:
    """Safety Agent 모의 결과 — crisis (safety.py:101-116 실제 출력 포맷)."""
    from src.agents.shared.safety_constants import SAFETY_MESSAGES

    return {
        "safety_flags": {
            "status": "crisis",
            "risk_level": 4,
            "risk_score": 0.95,
            "required_in_script": [
                SAFETY_MESSAGES["crisis"],
                "자해 관련 표현이 감지되었습니다.",
            ],
        },
        "risk_level": 4,
        "risk_score": 0.95,
        "next_step": "crisis_response",  # tier1_fan_out이 설정하는 필드
    }
```

- [ ] **Step 1-2: `tests/api/conftest.py` — CRISIS용 pipeline result 헬퍼 추가**

`tests/api/conftest.py`에서 `make_pipeline_result` 함수 바로 아래에 CRISIS 전용 헬퍼를 추가:

```python
def make_crisis_pipeline_result(**overrides: Any) -> dict[str, Any]:
    """CRISIS 판정 시 실제 파이프라인이 반환하는 state 구조.

    final_output이 JSON이 아닌 평문임을 보장 (버그 재현 가능).
    """
    from src.agents.shared.safety_constants import SAFETY_MESSAGES

    crisis_msg = (
        f"{SAFETY_MESSAGES['crisis']}\n\n자해 관련 표현이 감지되었습니다."
    )
    result = {
        "final_output": crisis_msg,          # 평문 (JSON 아님)
        "safety_flags": {
            "status": "crisis",
            "risk_level": 4,
            "risk_score": 0.95,
            "required_in_script": [
                SAFETY_MESSAGES["crisis"],
                "자해 관련 표현이 감지되었습니다.",
            ],
        },
        "risk_level": 4,
        "risk_score": 0.95,
        "next_step": "end",                  # crisis_response_node 통과 후
        "emotion_vectors": {},
        "visual_data": None,
        "intent": {"intent_type": "unknown", "complexity_score": 0.0},
        "reasoning_result": {},
        "iteration_count": 0,
        "session_id": "sess_test123",
    }
    result.update(overrides)
    return result
```

- [ ] **Step 1-3: `tests/api/test_podcasts_endpoint.py` — CRISIS 평문 final_output 테스트 추가**

`test_podcasts_endpoint.py`의 `TestCreatePodcastEpisode` 클래스 내에 추가:

```python
def test_create_episode_crisis_plain_final_output_no_db_save(
    self,
    test_client,
    mock_compiled_graph,
    mock_backend_client,
) -> None:
    """CRISIS 판정 시:
    1. final_output이 평문이어도 500 에러가 아닌 200 반환
    2. episode_id가 None (에피소드 미생성)
    3. crisis_message가 응답에 포함
    4. backend_client.save 미호출 (DB 오염 없음)
    """
    from tests.api.conftest import make_crisis_pipeline_result

    mock_compiled_graph.ainvoke = AsyncMock(
        return_value=make_crisis_pipeline_result()
    )

    response = test_client.post(
        "/api/podcasts/episodes",
        json=self._valid_request(),
    )

    assert response.status_code == 200
    data = response.json()

    # CRISIS 응답 구조
    assert data["safety_alert"]["status"] == "crisis"
    assert data["safety_alert"]["show_emergency_button"] is True
    assert data["episode_id"] is None          # 에피소드 미생성
    assert data["crisis_message"] is not None  # LLM reasons 포함 메시지
    assert len(data["crisis_message"]) > 0

    # 백엔드 저장 미호출 검증
    mock_backend_client.save.assert_not_called()
    mock_backend_client.ingest_podcast_episodes.assert_not_called()


def test_create_episode_crisis_alert_fields(
    self,
    test_client,
    mock_compiled_graph,
) -> None:
    """CRISIS safety_alert 필드 완전성 검증."""
    from tests.api.conftest import make_crisis_pipeline_result

    mock_compiled_graph.ainvoke = AsyncMock(
        return_value=make_crisis_pipeline_result()
    )

    response = test_client.post(
        "/api/podcasts/episodes",
        json=self._valid_request(),
    )

    data = response.json()
    alert = data["safety_alert"]

    assert alert["status"] == "crisis"
    assert isinstance(alert["alert_message"], str)
    assert len(alert["alert_message"]) > 0
    assert alert["show_emergency_button"] is True
    assert alert["helpline_info"] is not None
    assert len(alert["helpline_info"]) > 0
    # 각 helpline에 name과 phone 필드 존재
    for helpline in alert["helpline_info"]:
        assert "name" in helpline
        assert "phone" in helpline
```

- [ ] **Step 1-4: 테스트 실행 — 현재 FAIL 확인**

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
python -m pytest tests/api/test_podcasts_endpoint.py::TestCreatePodcastEpisode::test_create_episode_crisis_plain_final_output_no_db_save -v
```

예상 출력: FAIL (`episode_id` 필드 없음 또는 `"ep_fallback"` 반환, `crisis_message` 없음)

- [ ] **Step 1-5: 커밋 (테스트만)**

```bash
git add tests/integration/conftest.py tests/api/conftest.py tests/api/test_podcasts_endpoint.py
git commit -m "test: CRISIS 평문 final_output 시나리오 테스트 및 fixture 수정"
```

---

## Task 2: `external_schemas.py` — SlimPodcastResponse 스키마 수정

**Files:**
- Modify: `src/api/external_schemas.py`

> 주의: 공용 스키마 변경. PR 전 전원 리뷰 필수. `episode_id`를 `str | None`으로 변경하면 프론트엔드 계약 변경 — 백엔드팀과 사전 공유 필요.

- [ ] **Step 2-1: `SlimPodcastResponse`에 `crisis_message` 필드 추가, `episode_id` 옵셔널 변경**

`src/api/external_schemas.py`에서 `SlimPodcastResponse` 클래스를 찾아 아래와 같이 수정:

```python
class SlimPodcastResponse(BaseModel):
    """
    팟캐스트 에피소드 생성 완료 응답 (슬림).

    파이프라인 실행 + DB 저장 완료 후 반환하는 최소 응답.
    모든 데이터는 DB에 저장되므로 Backend가 GET API로 조회 가능.
    safety_alert만 직접 포함 (CRISIS 시 에피소드 미생성 → DB 미저장).

    CRISIS 시 응답:
        - episode_id: None (에피소드 미생성)
        - safety_alert: SafetyAlertData(status="crisis", ...)
        - crisis_message: LLM이 생성한 위기 대응 메시지 (required_in_script 전체)

    Endpoint 응답: POST /api/podcasts/episodes
    """

    success: Literal[True] = True
    episode_id: str | None = Field(
        default=None,
        description="생성된 에피소드 고유 ID. CRISIS 시 에피소드 미생성으로 None 반환.",
    )
    session_id: str = Field(description="세션 ID")
    safety_alert: SafetyAlertData | None = Field(
        default=None,
        description="안전 경고 (CRISIS 시 에피소드 미생성, 응답에 직접 포함)",
    )
    crisis_message: str | None = Field(
        default=None,
        description=(
            "CRISIS 판정 시 LLM이 생성한 위기 대응 메시지 (required_in_script 전체 포함). "
            "safety_alert.status == 'crisis'일 때만 설정. "
            "법적 고지 + 헬프라인 + LLM이 감지한 위험 사유를 포함."
        ),
    )
    tracing: RequestTracing = Field(description="추적 컨텍스트")
```

- [ ] **Step 2-2: 스키마 변경 후 기존 테스트 통과 확인**

```bash
python -m pytest tests/api/test_podcasts_endpoint.py -v --tb=short
```

예상: 기존 `test_create_episode_success_and_response_structure`는 `episode_id`가 `str`이 아닌 `str | None`을 기대하지 않을 수 있음 → 필요 시 해당 assert를 `assert isinstance(data["episode_id"], (str, type(None)))` 로 완화.

- [ ] **Step 2-3: 커밋**

```bash
git add src/api/external_schemas.py tests/api/test_podcasts_endpoint.py
git commit -m "feat: SlimPodcastResponse에 crisis_message 필드 추가, episode_id 옵셔널 변경"
```

---

## Task 3: `backend_resources.py` — 미래 safety_event 상수 선언

**Files:**
- Modify: `src/api/backend_resources.py`

> 실제 HTTP 호출은 추가하지 않음. 백엔드팀 협의 후 별도 Task에서 활성화.

- [ ] **Step 3-1: `RESOURCE_SAFETY_EVENT` 상수 추가**

`src/api/backend_resources.py`의 기존 RESOURCE_* 상수 블록 끝에 추가:

```python
# Safety 이벤트 저장 — 백엔드팀과 API 스펙 합의 후 활성화 예정
# TODO(backend-team): POST /greenroom/ingest/ai/safety_events 엔드포인트 생성 필요
# 협의 문서: docs/architecture/API_ENDPOINTS_INTERNAL.md
RESOURCE_SAFETY_EVENT = "safety_events"
TYPE_SAFETY_EVENT = "safety_event"
```

- [ ] **Step 3-2: 커밋**

```bash
git add src/api/backend_resources.py
git commit -m "feat: RESOURCE_SAFETY_EVENT 상수 추가 (백엔드팀 협의 후 활성화 예정)"
```

---

## Task 4: `podcasts.py` — `create_podcast_episode` CRISIS 분기 수정 (핵심)

**Files:**
- Modify: `src/api/routes/podcasts.py`

- [ ] **Step 4-1: CRISIS 감지 헬퍼 함수 추가**

`src/api/routes/podcasts.py`에서 `_extract_safety_alert` 함수 바로 아래에 추가:

```python
def _is_crisis_state(state: dict[str, Any]) -> bool:
    """파이프라인 최종 상태가 CRISIS 판정인지 확인한다.

    Args:
        state: ainvoke/astream 완료 후의 final_state.

    Returns:
        Safety Agent가 CRISIS 판정을 내렸으면 True.
    """
    return state.get("safety_flags", {}).get("status") == "crisis"
```

- [ ] **Step 4-2: `create_podcast_episode`에 CRISIS 조기 반환 분기 추가**

`src/api/routes/podcasts.py`의 `create_podcast_episode` 함수에서 `# 3. 데이터 추출` 주석 블록을 찾아, 아래와 같이 CRISIS 분기를 **파이프라인 실행 직후, 데이터 추출 전**에 삽입:

```python
    # 3. 데이터 추출 — CRISIS 분기 우선
    safety_alert = _extract_safety_alert(final_state)

    if _is_crisis_state(final_state):
        # CRISIS: 에피소드 미생성 → DB 저장 스킵 (설계 원칙 복원)
        # final_output에는 LLM이 생성한 위기 메시지(평문)가 있음
        crisis_message = final_state.get("final_output") or ""
        logger.warning(
            "[Podcast][CRISIS] 위기 판정 — 에피소드 저장 스킵. "
            "session_id=%s, risk_level=%s, risk_score=%s",
            request.session_id,
            final_state.get("risk_level"),
            final_state.get("risk_score"),
        )
        return SlimPodcastResponse(
            episode_id=None,
            session_id=request.session_id,
            safety_alert=safety_alert,
            crisis_message=crisis_message,
            tracing=request.tracing,
        )

    # 정상 흐름: 에피소드 데이터 추출 및 저장
    episode_data = _build_episode_data(final_state)
    # ... (기존 코드 그대로)
```

실제 적용 시 최종 코드 블록:

```python
    # 3. 데이터 추출 — CRISIS 분기 우선
    safety_alert = _extract_safety_alert(final_state)

    if _is_crisis_state(final_state):
        crisis_message = final_state.get("final_output") or ""
        logger.warning(
            "[Podcast][CRISIS] 위기 판정 — 에피소드 저장 스킵. "
            "session_id=%s, risk_level=%s, risk_score=%s",
            request.session_id,
            final_state.get("risk_level"),
            final_state.get("risk_score"),
        )
        return SlimPodcastResponse(
            episode_id=None,
            session_id=request.session_id,
            safety_alert=safety_alert,
            crisis_message=crisis_message,
            tracing=request.tracing,
        )

    episode_data = _build_episode_data(final_state)

    intent_data = final_state.get("intent", {})
    meta = PodcastResponseMeta(
        pipeline_duration_ms=elapsed_ms,
        intent_type=intent_data.get("intent_type", "unknown"),
        complexity_score=intent_data.get("complexity_score", 0.0),
        reasoning_depth=final_state.get("reasoning_result", {}).get("reasoning_depth", "standard"),
        retry_count=final_state.get("iteration_count", 0),
        total_words=len(episode_data.script_text.split()),
    )

    # 4. 핵심 데이터 동기 저장 (응답 반환 전 완료)
    await _save_core_data(
        user_id=request.user_id,
        session_id=request.session_id,
        episode_data=episode_data,
        final_state=final_state,
        meta=meta,
        trace_id=request.tracing.trace_id,
        correlation_id=request.tracing.correlation_id,
        elapsed_ms=elapsed_ms,
    )

    return SlimPodcastResponse(
        episode_id=episode_data.episode_id,
        session_id=request.session_id,
        safety_alert=safety_alert,
        tracing=request.tracing,
    )
```

- [ ] **Step 4-3: 테스트 실행 — Task 1에서 작성한 CRISIS 테스트 PASS 확인**

```bash
python -m pytest tests/api/test_podcasts_endpoint.py::TestCreatePodcastEpisode::test_create_episode_crisis_plain_final_output_no_db_save -v
```

예상 출력: PASS

- [ ] **Step 4-4: 기존 정상 흐름 테스트 PASS 확인**

```bash
python -m pytest tests/api/test_podcasts_endpoint.py -v --tb=short
```

예상 출력: 전체 PASS

---

## Task 5: `podcasts.py` — SSE `stream_podcast_episode` CRISIS 분기 수정

**Files:**
- Modify: `src/api/routes/podcasts.py` (SSE 엔드포인트)

- [ ] **Step 5-1: `event_generator` 내부 CRISIS 분기 추가**

`src/api/routes/podcasts.py`의 `event_generator()` 함수 내부에서 `# 파이프라인 완료 — 결과 구성` 주석 블록을 찾아 수정:

```python
            # 파이프라인 완료 — 결과 구성
            safety_alert = _extract_safety_alert(final_state)

            if _is_crisis_state(final_state):
                # CRISIS: 에피소드 미생성 → DB 저장 스킵
                crisis_message = final_state.get("final_output") or ""
                logger.warning(
                    "[SSE][CRISIS] 위기 판정 — 에피소드 저장 스킵. session_id=%s",
                    request.session_id,
                )
                result_payload = SlimPodcastResponse(
                    episode_id=None,
                    session_id=request.session_id,
                    safety_alert=safety_alert,
                    crisis_message=crisis_message,
                    tracing=request.tracing,
                )
                yield _sse_format(
                    {
                        "event": "result",
                        "data": result_payload.model_dump(mode="json"),
                        "timestamp": _now_iso(),
                    }
                )
            else:
                # 정상 흐름
                episode_data = _build_episode_data(final_state)
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                meta = PodcastResponseMeta(
                    mode="podcast",
                    pipeline_duration_ms=elapsed_ms,
                    intent_type=final_state.get("intent", {}).get("intent_type", "unknown"),
                    complexity_score=float(final_state.get("intent", {}).get("complexity_score", 0.0)),
                    reasoning_depth=str(
                        final_state.get("reasoning_result", {}).get("reasoning_depth", "standard")
                    ),
                    retry_count=int(final_state.get("iteration_count", 0)),
                    total_words=len(episode_data.script_text.split()),
                )

                # DB 저장
                await _save_core_data(
                    user_id=request.user_id,
                    session_id=request.session_id,
                    episode_data=episode_data,
                    final_state=final_state,
                    meta=meta,
                    trace_id=request.tracing.trace_id,
                    correlation_id=request.tracing.correlation_id,
                    elapsed_ms=elapsed_ms,
                )

                result_payload = SlimPodcastResponse(
                    episode_id=episode_data.episode_id,
                    session_id=request.session_id,
                    safety_alert=safety_alert,
                    tracing=request.tracing,
                )
                yield _sse_format(
                    {
                        "event": "result",
                        "data": result_payload.model_dump(mode="json"),
                        "timestamp": _now_iso(),
                    }
                )
```

- [ ] **Step 5-2: SSE CRISIS 테스트 추가**

`tests/api/test_podcasts_endpoint.py`에 SSE 엔드포인트 CRISIS 테스트 추가:

```python
class TestStreamPodcastEpisode:
    """POST /api/podcasts/episodes/stream SSE 엔드포인트 테스트."""

    def _valid_request(self, **overrides: Any) -> dict[str, Any]:
        base = {
            "user_id": "test_user_001",
            "session_id": "sess_test123",
            "situation": "직장에서 스트레스를 많이 받고 있어",
            "thought": "이 상황을 어떻게 해결해야 할지 모르겠어",
            "action": "일단 참고 있는데 점점 힘들어지고 있어",
        }
        base.update(overrides)
        return base

    def test_stream_episode_crisis_no_db_save(
        self,
        test_client,
        mock_compiled_graph,
        mock_backend_client,
    ) -> None:
        """SSE 엔드포인트: CRISIS 시 result 이벤트에 crisis_message 포함, DB 저장 없음."""
        import json as json_lib
        from tests.api.conftest import make_crisis_pipeline_result

        # astream은 (mode, chunk) 쌍을 yield하는 async generator
        async def mock_astream(*args: Any, **kwargs: Any):
            yield ("updates", {"crisis_response": make_crisis_pipeline_result()})

        mock_compiled_graph.astream = mock_astream

        response = test_client.post(
            "/api/podcasts/episodes/stream",
            json=self._valid_request(),
        )

        assert response.status_code == 200
        events = [
            json_lib.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        result_events = [e for e in events if e.get("event") == "result"]
        assert len(result_events) == 1
        result_data = result_events[0]["data"]
        assert result_data["episode_id"] is None
        assert result_data["crisis_message"] is not None
        assert result_data["safety_alert"]["status"] == "crisis"

        mock_backend_client.save.assert_not_called()
        mock_backend_client.ingest_podcast_episodes.assert_not_called()
```

- [ ] **Step 5-3: SSE 테스트 실행**

```bash
python -m pytest tests/api/test_podcasts_endpoint.py::TestStreamPodcastEpisode -v --tb=short
```

예상 출력: PASS

---

## Task 6: 전체 테스트 통과 및 최종 커밋

**Files:**
- 수정 없음 (검증만)

- [ ] **Step 6-1: 전체 테스트 실행**

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```

예상: 594개 기존 통과 + 신규 테스트 통과 (총 599개 이상)

- [ ] **Step 6-2: 타입 검사 (mypy)**

```bash
python -m mypy src/api/routes/podcasts.py src/api/external_schemas.py --ignore-missing-imports
```

예상: 0 errors

- [ ] **Step 6-3: 린트**

```bash
python -m ruff check src/api/routes/podcasts.py src/api/external_schemas.py
```

예상: 0 issues

- [ ] **Step 6-4: 전체 변경사항 최종 커밋**

```bash
git add src/api/routes/podcasts.py src/api/external_schemas.py src/api/backend_resources.py \
        tests/api/conftest.py tests/api/test_podcasts_endpoint.py \
        tests/integration/conftest.py
git commit -m "fix: Safety CRISIS 표출 오류 수정 및 백엔드 빈 에피소드 오저장 방지

- SlimPodcastResponse에 crisis_message 필드 추가 (LLM reasons 전달)
- episode_id를 CRISIS 시 None 반환 (ep_fallback 제거)
- create_podcast_episode / stream_podcast_episode에 CRISIS 조기 분기 추가
- CRISIS 시 _save_core_data 스킵 (DB 오염 방지)
- RESOURCE_SAFETY_EVENT 상수 선언 (백엔드 협의 후 활성화)
- 테스트 fixture를 실제 SafetyAgent 출력 포맷으로 수정"
```

---

## 백엔드팀 협의 필요 항목 (이번 PR 범위 외)

아래 항목은 백엔드팀 합의 후 별도 PR로 진행한다.

| 항목 | 내용 | 협의 대상 |
|------|------|---------|
| **safety_events API 신설** | `POST /greenroom/ingest/ai/safety_events` — CRISIS 발생 로그 영구 저장 | 백엔드팀 + 3인 합의 |
| **contracts.py `SafetyEventRecord`** | CRISIS 이벤트 저장용 Pydantic 모델 추가 | Protected File → 3인 합의 |
| **`episode_id: null` 프론트엔드 처리** | CRISIS 시 episode_id가 null이므로 조회 시도 안 하도록 FE 변경 | 프론트엔드팀 |
| **emotion_logs CRISIS 취소 정책** | Emotion publish 도중 CRISIS 취소 발생 시 partial 저장 정책 | 개발자2 |
| **모니터링 — 에러 레벨 승격** | `_save_core_data` 실패 시 warning→error 레벨 승격 | 개발자1 (별도 PR) |

---

## 검토 체크리스트 (Self-Review)

### Spec 커버리지

| 버그 | Task | 구현 여부 |
|------|------|---------|
| final_output JSON 파싱 실패 | Task 4 (CRISIS 조기 분기) | ✅ |
| ep_fallback 빈 에피소드 DB 저장 | Task 4 (CRISIS → _save_core_data 스킵) | ✅ |
| LLM reasons 소실 | Task 2 + Task 4 (crisis_message 필드) | ✅ |
| SSE 엔드포인트 동일 버그 | Task 5 | ✅ |
| 테스트 fixture 불일치 | Task 1 | ✅ |
| backend_resources 상수 선언 | Task 3 | ✅ |
| BackendClient 400 재시도 낭비 | 범위 외 (별도 이슈) | ➖ |
| Emotion 부분 저장 정책 | 범위 외 (개발자2 협의) | ➖ |
| workflow.py SSE 이벤트 강화 | 범위 외 (Protected File) | ➖ |

### 타입 일관성

- `_is_crisis_state()` → `bool` → Task 4/5에서 `if _is_crisis_state(final_state):` 조건 분기 ✅
- `crisis_message: str | None` → Task 2에서 정의, Task 4/5에서 `str | None` 타입으로 할당 ✅
- `episode_id: str | None` → Task 2에서 정의, Task 4에서 `None` 할당 ✅
- `make_crisis_pipeline_result()` → Task 1에서 정의, Task 4/5 테스트에서 사용 ✅

---

*작성일: 2026-04-15 19:00 | 담당: 개발자1 (feature/analysis-crisis-fix 브랜치 권장) | 리뷰: 전원 (external_schemas.py 수정 포함)*

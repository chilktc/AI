# 변경이력 v19

> 날짜: 2026-02-27

---

## v19: 모니터링 시스템 구축 — 텔레메트리 콜백, 토큰 추적, 에이전트 I/O 트래커, 스트리밍 이벤트, 체크포인팅

### 배경

v18에서 E2E 멀티 프로바이더 테스트와 LangSmith 트레이싱 기초(`_traced_process()`)가 완성된 후, LangGraph 시스템을 최대한 활용하기 위해 다음을 구축한다:

1. **LLMClient 토큰 사용량 추적** — Anthropic/Bedrock/OpenAI 3개 프로바이더 응답에서 토큰 수를 추출하여 에이전트별·TIER별 비용 분석의 기초 데이터 확보
2. **BaseAgent 트레이싱 강화** — LangSmith `@traceable` 메타데이터에 프롬프트 버전, A/B variant, 모델 ID 추가 + I/O 스냅샷 자동 캡처
3. **텔레메트리 콜백 핸들러** — LangGraph `BaseCallbackHandler` 기반 TIER별 성능 메트릭 수집, CRISIS 이벤트 감지, 비용 추정
4. **에이전트 I/O 트래커** — 파이프라인 내 각 에이전트의 입출력을 체계적으로 캡처하여 데이터 흐름 추적
5. **텔레메트리 데이터 모델** — 모니터링과 I/O 추적의 통합 데이터 모델 정의
6. **스트리밍 이벤트** — `get_stream_writer()`로 TIER 시작/완료, 에이전트 완료, CRISIS 이벤트를 실시간 발행
7. **State 체크포인팅** — `compile_graph()` 헬퍼로 `InMemorySaver`(dev)/`PostgresSaver`(prod) 체크포인팅 통합

### 신규 파일 (8개)

| 파일 | 내용 |
|------|------|
| `src/monitoring/__init__.py` | 모니터링 패키지 초기화 — `MindLogTelemetryCallback`, `AgentIOTracker`, `AgentMetric`, `MonitoringEvent`, `PipelineMetrics` export |
| `src/monitoring/models.py` | 텔레메트리 데이터 모델 — `AgentMetric`, `TierSummary`, `PipelineMetrics`(TIER별 요약·최종 집계), `MonitoringEvent`, `PipelineRunSummary` |
| `src/monitoring/callbacks.py` | `MindLogTelemetryCallback(BaseCallbackHandler)` — 노드별 TIER 매핑, 실행 시간 추적, CRISIS 감지(`safety_flags.status == "crisis"`), 재시도 카운터, 모델별 비용 추정(USD), `get_summary()` 요약 dict |
| `src/monitoring/io_tracker.py` | `AgentIOTracker` — `capture_input()`/`capture_output()` 스냅샷 캡처, `PipelineTrace` 데이터 흐름 시각화, 민감정보 보호(user_input SHA-256 해시, 문자열 truncation, dict 요약) |
| `tests/monitoring/__init__.py` | 모니터링 테스트 패키지 초기화 |
| `tests/monitoring/test_models.py` | 데이터 모델 단위 테스트 (11 tests) — `AgentMetric`, `PipelineMetrics`(토큰 합산, TIER 요약, finalize), `MonitoringEvent`, `PipelineRunSummary`, `TierSummary` |
| `tests/monitoring/test_callbacks.py` | 텔레메트리 콜백 단위 테스트 (17 tests) — 비용 추정, TIER 타이밍, CRISIS 감지, 에러 기록, 재시도 카운터, 병렬 TIER max 선택, 요약 dict |
| `tests/monitoring/test_io_tracker.py` | I/O 트래커 단위 테스트 (14 tests) — 스냅샷 캡처, 파이프라인 트레이스, 민감정보 해시/truncation/dict 요약, 토큰 사용량, 프롬프트 버전/A/B variant |
| `tests/monitoring/test_streaming.py` | 스트리밍 + 체크포인팅 테스트 (17 tests) — `_get_writer` 폴백, 대화모드/팟캐스트모드 이벤트 발행(tier_start/agent_complete/tier_end/crisis_detected), `compile_graph()` 헬퍼(unified/conversation/podcast/checkpointer) |

### 수정 파일 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/shared/llm_client.py` | 토큰 사용량 추적 추가 — `_last_usage`/`_total_usage` 속성, `last_usage`/`total_usage` property, `reset_total_usage()`, `_record_usage()` 메서드. `_generate_anthropic()`·`_generate_bedrock()`·`_generate_openai()` 각각에서 응답의 usage 필드 추출 (기존 public 메서드 시그니처 변경 없음) |
| `src/agents/shared/base_agent.py` | 트레이싱 메타데이터 강화 — `@traceable`에 `prompt_version`, `ab_variant`, `model_id`, mode 태그 추가. I/O 스냅샷 자동 캡처 (`_last_input_snapshot`/`_last_output_snapshot`). `get_execution_metrics()` 신규 메서드. `_sanitize_state_snapshot()` 정적 메서드 (민감정보 마스킹). `__call__()`에서 `reset_total_usage()` 호출 (기존 public 메서드 시그니처 변경 없음) |
| `config/settings.yaml` | `monitoring` 섹션 추가 — provider 선택(langsmith/langfuse/both), LangSmith 프로젝트 설정, LangFuse 옵션, 메트릭 수집 옵션(토큰·TIER 타이밍·에이전트 I/O), I/O 스냅샷 최대 문자수(2000), CRISIS 알림 설정, 레이턴시 임계값(10000ms) |
| `src/graph/workflow.py` | **[Protected File]** 스트리밍 이벤트 + 체크포인팅 통합. `_get_writer()` 헬퍼(LangGraph 컨텍스트 외부 안전 폴백), `tier1_conversation_fan_out()`/`tier1_podcast_fan_out()`에 `tier_start`·`agent_complete`·`crisis_detected`·`tier_end` 이벤트 발행 추가, `compile_graph()` 헬퍼(unified/conversation/podcast + 선택적 checkpointer) |

### 주요 아키텍처

#### 토큰 사용량 추적 흐름

```
LLMClient._generate_*()
    ↓ response.usage 추출
LLMClient._record_usage()
    ↓ _last_usage (직전 호출), _total_usage (누적) 저장
BaseAgent.__call__()
    ↓ reset_total_usage() → process() → get_execution_metrics()
MindLogTelemetryCallback.add_agent_metric()
    ↓ _estimate_cost() → PipelineMetrics.total_cost_usd 갱신
```

#### 텔레메트리 콜백 수집 구조

```
LangGraph compiled.ainvoke(state, config={"callbacks": [callback]})
    ↓
on_chain_start()  → 노드 시작 시각 기록
on_chain_end()    → 실행 시간 계산, TIER 타이밍 기록, CRISIS 감지
on_chain_error()  → 에러 이벤트 기록
    ↓
callback.get_metrics()  → PipelineMetrics (TIER별 집계)
callback.get_summary()  → 사람이 읽을 수 있는 요약 dict
```

#### 에이전트 I/O 캡처 흐름

```
AgentIOTracker(session_id="sess_123")
    ↓
capture_input(agent_name, state, run_id)
    ↓ _sanitize() → user_input 해시, 문자열 truncation
    ↓ IOSnapshot 생성 → _pending에 저장
    ↓ snapshot_id 반환
        ↓
    [에이전트 실행]
        ↓
capture_output(agent_name, result, snapshot_id, duration_ms)
    ↓ _pending에서 매칭 → output_fields 기록
    ↓ _snapshots에 추가
        ↓
get_pipeline_trace()
    ↓ PipelineTrace.get_data_flow() → 시각화용 dict 리스트
```

#### 스트리밍 이벤트 흐름

```
tier1_*_fan_out() 내부:
    writer = _get_writer()     ← LangGraph 컨텍스트 외부 시 no-op 폴백
    ↓
    writer({"event": "tier_start", "tier": 1, "mode": "...", "agents": [...]})
    ↓
    for agent in as_completed(tasks):
        ↓ CRISIS 감지 시:
        writer({"event": "crisis_detected", "agent": "safety", "risk_level": 4, ...})
        ↓ 정상 완료 시:
        writer({"event": "agent_complete", "agent": name, "progress": "2/4", ...})
    ↓
    writer({"event": "tier_end", "tier": 1, "status": "ok|crisis", "elapsed_ms": ...})

프론트엔드 소비:
    async for mode, chunk in compiled.astream(
        state, config, stream_mode=["updates", "custom"]
    ):
        if mode == "custom":
            handle_streaming_event(chunk)   # tier_start, agent_complete, tier_end, crisis_detected
        elif mode == "updates":
            handle_state_update(chunk)      # AgentState 필드 변경
```

#### 체크포인팅 통합

```
from langgraph.checkpoint.memory import InMemorySaver

# compile_graph() 헬퍼로 간편 컴파일
compiled = compile_graph("unified", checkpointer=InMemorySaver())

# thread_id로 세션 추적 + 텔레메트리 콜백 동시 사용
config = {
    "configurable": {"thread_id": f"session_{session_id}"},
    "callbacks": [MindLogTelemetryCallback(session_id=session_id)],
}
result = await compiled.ainvoke(state, config)

# Time-travel 디버깅: 상태 이력 조회
for snapshot in compiled.get_state_history(config):
    print(snapshot)
```

#### 민감정보 보호 정책

멘탈케어 데이터 특성상 다음 보호 정책을 적용:

| 데이터 유형 | 보호 방식 |
|------------|----------|
| `user_input` (사용자 원문) | SHA-256 해시 앞 16자 + 길이만 저장 |
| 긴 문자열 (> max_chars) | 앞 2000자 + `...<truncated>` |
| dict 값 | 키 목록 + 크기만 저장 (`_keys`, `_size`) |
| 기타 값 | 원본 저장 |

#### 모델별 비용 추정 (USD per 1M tokens)

| 모델 | Input | Output |
|------|-------|--------|
| claude-opus-4-6 | $15.00 | $75.00 |
| claude-sonnet-4-5 | $3.00 | $15.00 |
| claude-haiku-4-5 | $0.80 | $4.00 |

### 스트리밍 이벤트 타입

| 이벤트 | 발생 시점 | 주요 필드 |
|--------|----------|----------|
| `tier_start` | TIER 1 병렬 실행 시작 | tier, mode, agents(목록) |
| `agent_complete` | 개별 에이전트 완료 | tier, agent, elapsed_ms, progress("2/4") |
| `crisis_detected` | Safety CRISIS 판정 | tier, agent, risk_level, elapsed_ms |
| `tier_end` | TIER 1 실행 완료 | tier, mode, status(ok/crisis), elapsed_ms |

### 데이터 모델 요약

| 클래스 | 용도 | 주요 필드 |
|--------|------|----------|
| `AgentMetric` | 개별 에이전트 실행 메트릭 | agent_name, tier, duration_ms, llm_calls, input/output_tokens, model_id, status |
| `TierSummary` | TIER별 실행 요약 | tier, duration_ms, agent_count, total_llm_calls |
| `PipelineMetrics` | 파이프라인 전체 메트릭 | run_id, tier_durations, agent_metrics, crisis_detected, total_cost_usd |
| `MonitoringEvent` | 통합 모니터링 이벤트 | event_type(pipeline_run/agent_execution/crisis), data |
| `PipelineRunSummary` | 대시보드 렌더링용 요약 | tier_summaries, total_llm_calls, estimated_cost_usd, final_status |
| `IOSnapshot` | 에이전트 입출력 스냅샷 | input_fields, output_fields, duration_ms, token_usage, status |
| `PipelineTrace` | 파이프라인 데이터 흐름 | snapshots, get_data_flow() |

### 사용 예시

```python
# 1. 텔레메트리 콜백 + 체크포인팅 + 스트리밍
from langgraph.checkpoint.memory import InMemorySaver
from src.graph.workflow import compile_graph
from src.monitoring import MindLogTelemetryCallback

callback = MindLogTelemetryCallback(session_id="sess_123", mode="conversation")
compiled = compile_graph("unified", checkpointer=InMemorySaver())

config = {
    "configurable": {"thread_id": "session_sess_123"},
    "callbacks": [callback],
}

# 스트리밍 모드로 실행
async for mode, chunk in compiled.astream(
    state, config, stream_mode=["updates", "custom"]
):
    if mode == "custom":
        # {"event": "agent_complete", "agent": "safety", "progress": "1/4", ...}
        send_to_frontend_websocket(chunk)
    elif mode == "updates":
        log_state_delta(chunk)

# 메트릭 요약
summary = callback.get_summary()
# → {"total_duration_ms": 4200, "estimated_cost_usd": 0.0123, ...}

# 2. 에이전트 I/O 추적
from src.monitoring import AgentIOTracker

tracker = AgentIOTracker(session_id="sess_123")
snap_id = tracker.capture_input("safety", state, run_id="run_456")
# ... agent 실행 ...
tracker.capture_output("safety", result, snap_id, duration_ms=120)
trace = tracker.get_pipeline_trace()
flow = trace.get_data_flow()
# → [{"agent": "safety", "tier": 1, "input_keys": [...], "output_keys": [...]}]

# 3. Time-travel 디버깅
for state_snapshot in compiled.get_state_history(config):
    print(state_snapshot)
```

### 검증

- 기존 테스트: **257개 전체 통과** (v18 기준)
- 신규 테스트: **59개** (모델 11 + 콜백 17 + I/O 트래커 14 + 스트리밍/체크포인팅 17)
- 전체 테스트: **316개 통과** (`pytest tests/ -v`)
- 공용 인프라 시그니처 변경: **없음** (신규 메서드·속성 추가만)

### 기대 효과

| 영역 | Before | After |
|------|--------|-------|
| **비용 추적** | 불가능 | 에이전트별·TIER별·모델별 토큰 사용량 + USD 비용 산출 |
| **성능 분석** | 로그 기반 수동 확인 | LangSmith 대시보드에서 실시간 TIER별 레이턴시 분석 |
| **A/B 테스트** | 인프라만 존재, 결과 분석 없음 | LangSmith 메타데이터로 variant별 성능 비교 가능 |
| **CRISIS 모니터링** | 로그에서만 확인 | 콜백 기반 CRISIS 이벤트 감지 + 스트리밍으로 즉시 알림 |
| **디버깅** | 로그 추적 | LangSmith 시각적 트레이스 + 체크포인트 Time-travel |
| **에이전트 I/O** | 블랙박스 | 각 에이전트 입출력 스냅샷 + 데이터 흐름 시각화 |
| **실시간 모니터링** | 없음 | 스트리밍으로 TIER 진행상황 프론트엔드 표시 |
| **세션 지속성** | 없음 | 체크포인팅으로 세션 상태 복원 + 멀티턴 대화 지원 |

---

*마지막 업데이트: 2026-02-27*

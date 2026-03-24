# API 공통 — 스트리밍 이벤트, 에러 코드, 재시도 정책

> [API_SPEC.md](API_SPEC.md) 문서 모음의 일부 (v2.0)

---

## 스트리밍 이벤트 스키마

> 소스: `StreamEvent` + `StreamEventType` (src/api/external_schemas.py)
> SSE/WS 스트리밍 엔드포인트. LangGraph `get_stream_writer()` 이벤트를 프론트엔드 소비 형태로 정규화.

### StreamEventType (StrEnum)

| 이벤트 값 | 상수명 | 설명 |
|----------|--------|------|
| `tier_start` | TIER_START | TIER 실행 시작 |
| `agent_complete` | AGENT_COMPLETE | 개별 에이전트 완료 |
| `tier_end` | TIER_END | TIER 실행 완료 |
| `crisis_detected` | CRISIS_DETECTED | Safety CRISIS 감지 — TIER 1 병렬 작업 즉시 취소 |
| `partial_response` | PARTIAL_RESPONSE | 부분 응답 (스트리밍) |
| `final_response` | FINAL_RESPONSE | 최종 응답 |
| `error` | ERROR | 에러 발생 |

### StreamEvent 필드

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_type | StreamEventType | true | 이벤트 유형 |
| session_id | String | true | 세션 ID |
| tier | Integer | false | 현재 TIER (0-4). `null` 가능 |
| agent | String | false | 에이전트 이름. `null` 가능 |
| data | Object | true | 이벤트 페이로드 (기본값: 빈 객체) |
| elapsed_ms | Integer | true | TIER 시작 이후 경과 시간 (ms, 기본값: 0) |
| timestamp | String (ISO 8601) | true | 이벤트 발생 시각 (UTC) |
| trace_id | String | true | 추적 ID |

---

## 공통 Error Code 명세

> 소스: `ErrorDetail`, `ErrorResponse` (src/api/external_schemas.py)
> 전역 예외 핸들러: `src/api/main.py` (3개 핸들러)

### 에러 응답 공통 형식

```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "상세 에러 메시지",
        "field": "에러 필드명 (검증 에러 시, nullable)",
        "trace_id": "trace_xxx (디버깅용, nullable)"
    },
    "tracing": {
        "request_id": "req_xxx",
        "trace_id": "trace_xxx",
        "correlation_id": "corr_xxx",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

### 에러 코드 목록

| HTTP Status | Code | Description | 클라이언트 대응 |
|-------------|------|-------------|---------------|
| 400 | `VALIDATION_ERROR` | 필수 필드 누락 또는 형식 오류. `error.field`에 문제 필드명 포함 | 요청 데이터 확인 후 수정 |
| 400 | `INPUT_TOO_LONG` | 입력 텍스트가 최대 길이 초과 (topic 200자) | 입력 텍스트 축소 |
| 401 | `AUTH_ERROR` | 인증 실패 (토큰 만료/무효/미포함) | 토큰 갱신 후 재시도 |
| 403 | `FORBIDDEN` | 접근 권한 없음 | 권한 확인 |
| 404 | `NOT_FOUND` | 요청한 리소스를 찾을 수 없음 | URL/ID 확인 |
| 404 | `SESSION_NOT_FOUND` | session_id에 해당하는 세션 미존재 | 세션 생성 후 재시도 |
| 422 | `VALIDATION_ERROR` | Pydantic 구조 검증 실패. `error.field` 포함 | 요청 본문 구조 수정 |
| 429 | `RATE_LIMITED` | 요청 제한 초과 | `Retry-After` 헤더 값만큼 대기 후 재시도 |
| 500 | `SERVER_ERROR` | 서버 내부 오류 | 최대 3회 재시도 (exponential backoff) |
| 500 | `PIPELINE_TIMEOUT` | AI 파이프라인 실행 타임아웃 (기본 30초) | trace_id와 함께 관리자 문의 |
| 500 | `CRISIS_ESCALATION` | Safety Agent CRISIS 감지 에스컬레이션 | 위기 응답 콘텐츠를 사용자에게 즉시 표시 |
| 503 | `SERVICE_UNAVAILABLE` | 서비스 일시 중단 | 10~30초 후 재시도 |

### 전역 예외 핸들러 매핑

| 핸들러 | HTTP Status | Code 매핑 | 트리거 |
|--------|------------|----------|--------|
| `http_exception_handler` | 원본 유지 | 404→`NOT_FOUND`, 429→`RATE_LIMITED`, 기타→`SERVER_ERROR` | `StarletteHTTPException` |
| `validation_exception_handler` | 422 | `VALIDATION_ERROR` | Pydantic `RequestValidationError` |
| `general_exception_handler` | 500 | `SERVER_ERROR` | 미처리 `Exception` (catch-all) |

### 재시도 정책

- **4xx 에러**: 재시도 불필요 (요청 수정 후 재전송)
- **429 에러**: `Retry-After` 헤더 값만큼 대기 후 재시도 (헤더 미포함 시 10초 권장)
- **5xx 에러**: 최대 3회 재시도 (exponential backoff: 1초, 2초, 4초). `PIPELINE_TIMEOUT`은 재시도 비권장

---

*[← API_SPEC.md (인덱스)](API_SPEC.md) · [발신 API ←](API_ENDPOINTS_INTERNAL.md)*

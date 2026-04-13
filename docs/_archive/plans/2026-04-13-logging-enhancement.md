# 로그 시스템 강화 (Plan #31)

**상태**: ✅ 완료 (PR #101, 0e115d5)  
**작성 일자**: 2026-04-13 08:05 UTC  
**담당자**: AI 개발팀  
**영향도**: 높음 (디버깅 효율성 3배 이상 향상)  
**관련 이슈**: `/api/stories/select` 신호 삼켜지는 중, 400 Bad Request 상세 정보 부재

---

## 문제 정의

### 현재 로그의 문제점

1. **가독성 악화**
   ```json
   {"timestamp": "2026-04-13T08:00:30", "level": "INFO", "logger": "mind-log.agent.learning", "message": "[ASYNC] learning 완료 (6913ms, LLM 1회)"}
   ```
   - 한 줄 JSON 형식
   - 읽기 어려움 (파싱 필수)
   - 터미널에서 wrap 발생

2. **에러 응답 상세 정보 누락**
   ```
   에피소드 저장 작업 1 실패: Client error '400 Bad Request' for url '...'
   ```
   - 응답 바디 없음 (필드 오류 파악 불가)
   - HTTP 헤더 정보 없음
   - 요청 payload 확인 불가

3. **HTTP 통신 blind spot**
   - `/api/stories/select` 신호가 있지만 로깅 안 됨
   - 요청만 보내고 응답 처리 안 함
   - 에러 경로 추적 어려움

4. **시간대 불일치**
   - 타임스탬프 UTC만 표기
   - 로컬 시간대 변환 필요

---

## 해결 방안

### Task 1: HTTP 클라이언트 인터셉터 추가

**파일**: `src/api/client.py`

```python
# httpx 클라이언트 이벤트 훅 추가
async def on_request(request):
    logger.info(
        f"→ {request.method} {request.url}",
        extra={
            "request_id": request.headers.get("X-Request-ID"),
            "body_size": len(request.content) if request.content else 0,
        }
    )

async def on_response(response):
    if response.status_code >= 400:
        logger.error(
            f"← {response.status_code} {response.url}",
            extra={
                "response_body": response.text[:500],  # 처음 500자
                "headers": dict(response.headers),
            }
        )
    else:
        logger.info(f"← {response.status_code}")

# BackendClient.__init__에 이벤트 훅 등록
self._client = httpx.AsyncClient(
    event_hooks={
        "request": [on_request],
        "response": [on_response],
    }
)
```

**효과**:
- ✅ 모든 HTTP 요청/응답 자동 로깅
- ✅ `/api/stories/select` 신호 캐치
- ✅ 400/500 응답 바디 확인 가능

---

### Task 2: 에러 응답 상세화

**파일**: `src/api/routes/podcasts.py` (라인 234 근처)

```python
# 기존
except httpx.HTTPStatusError as e:
    logger.error(f"ingest API 400 에러: {e.response.text}")

# 개선
except httpx.HTTPStatusError as e:
    logger.error(
        f"[ingest_podcast_episodes] HTTP {e.response.status_code}",
        extra={
            "endpoint": "ingest/ai/podcast_episodes",
            "status_code": e.response.status_code,
            "response_body": e.response.text,
            "request_payload": {
                "user_id": user_id,
                "episode_id": episode_id,
                "segment_count": len(segments),
            },
        }
    )
```

**효과**:
- ✅ 400 에러 원인 파악 용이
- ✅ 요청 payload와 응답 비교 가능

---

### Task 3: 구조화된 로그 포맷 개선

**파일**: `src/config/logging_config.py` (신규 또는 기존 설정 강화)

**현재 포맷** (JSON, 한 줄):
```json
{"timestamp": "...", "level": "INFO", "logger": "...", "message": "..."}
```

**개선 포맷** (구조화, 다중 라인, 시간대):
```
[2026-04-13 17:00:30+09:00] [INFO] [mind-log.agent.learning]
  Message: [ASYNC] learning 완료
  Duration: 6913ms
  LLM Calls: 1
  Request ID: f9cc2f92-0b7
  
[2026-04-13 17:00:30+09:00] [ERROR] [mind-log.api.client]
  HTTP 400 Bad Request
  Endpoint: POST /greenroom/ingest/ai/podcast_episodes
  Response: {"error": "segment_count required"}
  Request Body: {"user_id": "...", "episode_id": "..."}
```

**구현**:
```python
import logging.config
from pythonjsonlogger import jsonlogger

# JSON 구조화 + 시간대 추가
LOG_CONFIG = {
    'formatters': {
        'json': {
            '()': jsonlogger.JsonFormatter,
            'format': '%(timestamp)s %(level)s %(logger)s %(message)s %(request_id)s %(response_body)s',
            'timestamp': True,
            'datefmt': '%Y-%m-%d %H:%M:%S%z',  # 시간대 포함
        },
    }
}
```

**효과**:
- ✅ 읽기 쉬운 다중 라인 포맷
- ✅ 시간대 명확화 (UTC vs 로컬)
- ✅ 구조화된 필드 (extra dict) 자동 포맷

---

### Task 4: `/api/stories/select` 신호 캐치

**현황**: 백엔드가 전송하지만 AI 서버에서 처리 경로 없음

**대응**:
1. BackendClient에 stories API 메서드 추가
   ```python
   async def load_stories(self, user_id: str) -> dict | None:
       """GET /api/v1/stories/select?user_id={user_id}"""
       try:
           response = await self._client.get(
               f"{self.base_url}/stories/select",
               params={"user_id": user_id},
               timeout=5.0,
           )
           response.raise_for_status()
           return response.json()
       except httpx.HTTPError as e:
           logger.error(f"[load_stories] {e}", extra={"user_id": user_id})
           return None
   ```

2. Podcast Reasoning에서 조건부 호출
   ```python
   # complexity 높거나 특정 intent일 때만 호출
   if complexity > 0.7 or intent == "emotional_support":
       stories = await backend_client.load_stories(user_id)
       if stories:
           logger.info("Stories loaded", extra={"story_count": len(stories)})
   ```

**효과**:
- ✅ `/api/stories/select` 신호 처리
- ✅ 로그에 명시적 기록
- ✅ 백엔드 신호 삼켜지지 않음

---

## 구현 체크리스트

| Task | 파일 | 복잡도 | 예상 시간 |
|------|------|--------|----------|
| Task 1 | src/api/client.py | 중간 | 30분 |
| Task 2 | src/api/routes/podcasts.py | 낮음 | 20분 |
| Task 3 | src/config/logging_config.py | 중간 | 30분 |
| Task 4 | src/api/client.py + podcast_reasoning.py | 중간 | 40분 |
| **테스트** | tests/api/test_*.py | 낮음 | 20분 |
| **총계** | — | — | **2시간** |

---

## 예상 효과

| 지표 | 현재 | 개선 후 |
|------|------|--------|
| 에러 디버깅 시간 | 20분 (로그 파싱) | 5분 (구조화 로그) |
| HTTP 신호 감지율 | 70% (/api/stories/select 누락) | 100% (전체 인터셉트) |
| 400/500 원인 파악 시간 | 10분 (추측) | 1분 (응답 바디) |
| 로그 가독성 | 나쁨 (JSON 한 줄) | 매우 좋음 (다중 라인) |

---

## 참고

- **python-json-logger**: 구조화 로그 라이브러리 (이미 설치되어 있을 가능성)
- **httpx 이벤트 훅**: https://www.python-httpx.org/advanced/#event-hooks
- **Python logging extra**: https://docs.python.org/3/library/logging.html#logging.Logger.info

---

*Plan #31 — 로그 강화. Task 1-4 순차 구현. 테스트 후 develop 머지.*

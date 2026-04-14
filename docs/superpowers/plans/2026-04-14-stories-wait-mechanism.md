# Plan #35: Stories 수신 인프라 + TIER 4 대기 메커니즘 구현

> **상태**: ✅ 완료 (PR #110, 2026-04-13 MERGED, 581 passed)

**Goal:** 백엔드가 POST /api/stories/select로 전송하는 Stories 데이터를 asyncio.Event 기반으로 수신하고, TIER 4(Script Personalizer) 진입 전 최대 5분 대기하여 파이프라인에 전달한다.

**Architecture:** asyncio.Event per session_id로 Stories 데이터 도착을 신호한다. `wait_for_stories_node`가 TIER 3 완료 후 이벤트를 최대 300초 대기하며, 타임아웃 시 에러 응답을 반환하고 파이프라인을 종료한다. 데이터가 먼저 도착해도 Event가 이미 set 상태이므로 즉시 통과한다(get-or-create 패턴). Plan #34를 완전히 대체한다.

**Tech Stack:** FastAPI, asyncio (asyncio.Event), LangGraph StateGraph, Pydantic v2

## CI 체크리스트 (매 커밋 전 필수)

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
black .
isort .
ruff check .
mypy src/ --ignore-missing-imports
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

CI 기준:
- **Black**: 줄 길이 100, target py311
- **isort**: profile=black, 줄 길이 100
- **ruff**: E/F/W/I 규칙
- **mypy**: `disallow_untyped_defs = true` → 모든 함수 타입 어노테이션 필수
- **pytest**: `asyncio_mode = "auto"` → `@pytest.mark.asyncio` 불필요, `not live` 마커 기준

---

## 파일 맵

| 파일 | 작업 | Protected |
|------|------|-----------|
| `src/api/stories_store.py` | **신규** — asyncio.Event per session StoriesStore | — |
| `src/api/routes/stories.py` | **신규** — POST /api/stories/select 엔드포인트 | — |
| `tests/api/test_stories_store.py` | **신규** — StoriesStore 단위 테스트 7건 | — |
| `tests/api/test_stories_endpoint.py` | **신규** — 엔드포인트 테스트 6건 | — |
| `tests/graph/test_workflow_stories_wait.py` | **신규** — wait 노드 + 라우팅 테스트 5건 | — |
| `config/settings.yaml` | 수정 — `stories.wait_timeout_seconds: 300` 추가 | — |
| `config/loader.py` | 수정 — `stories_wait_timeout` 프로퍼티 추가 | — |
| `src/api/main.py` | 수정 — stories 라우터 등록 | — |
| `src/api/routes/sessions.py` | 수정 — 스텁 코드 3블록 제거 | — |
| `src/api/client.py` | 수정 — `load_stories()` 삭제 | — |
| `src/models/agent_state.py` | **Protected** — `stories_context: dict[str, Any] \| None` 추가 | ✅ |
| `src/graph/workflow.py` | **Protected** — 노드 함수 2개 + 라우팅 함수 1개 + 엣지 수정 | ✅ |

---

### Task 1: settings.yaml + loader.py 설정 추가

**Files:**
- Modify: `config/settings.yaml`
- Modify: `config/loader.py`

- [x] **Step 1: settings.yaml에 stories 섹션 추가**

`config/settings.yaml`의 `# 백엔드 API 설정` 섹션 바로 위에 삽입한다:

```yaml
# Stories 수신 대기 설정
stories:
  wait_timeout_seconds: 300  # 최대 5분 대기
```

- [x] **Step 2: loader.py에 프로퍼티 추가**

`config/loader.py`의 `async_timeout` 프로퍼티(255~257번째 줄) 바로 다음에 추가한다:

```python
@property
def stories_wait_timeout(self) -> int:
    """Stories 데이터 수신 최대 대기 시간 (초). 기본 300초(5분)."""
    return int(self._config.get("stories", {}).get("wait_timeout_seconds", 300))
```

- [x] **Step 3: 설정 동작 확인**

```bash
python3 -c "from config.loader import get_settings; s = get_settings(); print(s.stories_wait_timeout)"
```

Expected output: `300`

- [x] **Step 4: CI 린트 확인**

```bash
black --check config/loader.py config/settings.yaml
isort --check-only config/loader.py
ruff check config/loader.py
mypy config/loader.py --ignore-missing-imports
```

Expected: 에러 없음

- [x] **Step 5: 전체 테스트 통과 확인**

```bash
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

Expected: `563 passed`

- [x] **Step 6: 커밋**

```bash
git add config/settings.yaml config/loader.py
git commit -m "feat: stories wait_timeout_seconds 설정 추가 (기본 300초)"
```

---

### Task 2: StoriesStore 구현 (TDD)

**Files:**
- Create: `src/api/stories_store.py`
- Create: `tests/api/test_stories_store.py`

- [x] **Step 1: 실패하는 테스트 작성**

`tests/api/test_stories_store.py`:

```python
"""StoriesStore asyncio.Event 기반 단위 테스트."""

from __future__ import annotations

import asyncio

import pytest

from src.api.stories_store import StoriesStore


@pytest.fixture
def store() -> StoriesStore:
    return StoriesStore()


class TestSetStories:
    def test_set_stories_stores_data(self, store: StoriesStore) -> None:
        """set_stories 호출 후 데이터가 저장된다."""
        data = {"keywords": ["직장"], "title": "T", "description": "D"}
        store.set_stories("sess_001", data)
        assert store._store["sess_001"]["data"] == data

    def test_set_stories_sets_event(self, store: StoriesStore) -> None:
        """set_stories 호출 후 Event가 set 상태가 된다."""
        store.set_stories("sess_002", {"keywords": [], "title": "", "description": ""})
        assert store._store["sess_002"]["event"].is_set()


class TestWaitForStories:
    async def test_wait_returns_data_when_already_set(self, store: StoriesStore) -> None:
        """데이터가 이미 존재하면 즉시 반환한다."""
        data = {"keywords": ["감정"], "title": "제목", "description": "설명"}
        store.set_stories("sess_003", data)
        result = await store.wait_for_stories("sess_003", timeout=1.0)
        assert result == data

    async def test_wait_returns_data_when_set_concurrently(
        self, store: StoriesStore
    ) -> None:
        """대기 중에 데이터가 도착하면 반환한다."""
        data = {"keywords": ["스트레스"], "title": "제목2", "description": "설명2"}

        async def delayed_set() -> None:
            await asyncio.sleep(0.05)
            store.set_stories("sess_004", data)

        asyncio.create_task(delayed_set())
        result = await store.wait_for_stories("sess_004", timeout=2.0)
        assert result == data

    async def test_wait_returns_none_on_timeout(self, store: StoriesStore) -> None:
        """타임아웃 초과 시 None을 반환한다."""
        result = await store.wait_for_stories("sess_nonexistent", timeout=0.1)
        assert result is None


class TestDeleteSession:
    def test_delete_removes_entry(self, store: StoriesStore) -> None:
        """delete_session 후 해당 세션이 store에서 제거된다."""
        store.set_stories("sess_005", {"keywords": [], "title": "", "description": ""})
        store.delete_session("sess_005")
        assert "sess_005" not in store._store

    def test_delete_nonexistent_session_is_safe(self, store: StoriesStore) -> None:
        """존재하지 않는 세션 삭제는 에러 없이 무시된다."""
        store.delete_session("nonexistent")  # 예외 없이 통과해야 함
```

> `asyncio_mode = "auto"` (pyproject.toml)이므로 `@pytest.mark.asyncio` 불필요.

- [x] **Step 2: 테스트 실패 확인**

```bash
pytest tests/api/test_stories_store.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'StoriesStore'`

- [x] **Step 3: StoriesStore 구현**

`src/api/stories_store.py`:

```python
"""
Stories 수신 인프라 — asyncio.Event 기반 세션별 임시 저장소.

백엔드가 POST /api/stories/select로 stories 데이터를 전송하면
set_stories()가 Event를 set하고, wait_for_stories()가 해제를 기다린다.

get-or-create 패턴으로 set_stories와 wait_for_stories의 호출 순서에 무관하게 동작한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StoriesStore:
    """
    세션별 asyncio.Event를 관리하는 Stories 임시 저장소.

    FastAPI 앱과 생명주기를 공유하는 모듈 레벨 싱글톤(`stories_store`)으로 사용한다.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def _get_or_create(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._store:
            self._store[session_id] = {"event": asyncio.Event(), "data": None}
        return self._store[session_id]

    def set_stories(self, session_id: str, data: dict[str, Any]) -> None:
        """Stories 데이터를 저장하고 대기 중인 wait_for_stories를 깨운다."""
        entry = self._get_or_create(session_id)
        entry["data"] = data
        entry["event"].set()
        logger.info("[StoriesStore] 데이터 수신 완료 — session_id=%s", session_id)

    async def wait_for_stories(
        self, session_id: str, timeout: float
    ) -> dict[str, Any] | None:
        """
        Stories 데이터 도착을 최대 timeout초 대기한다.

        Returns:
            dict: 데이터가 도착한 경우
            None: 타임아웃 초과
        """
        entry = self._get_or_create(session_id)
        try:
            await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
            return entry["data"]  # type: ignore[return-value]
        except asyncio.TimeoutError:
            logger.warning(
                "[StoriesStore] 타임아웃 — session_id=%s, timeout=%.0fs",
                session_id,
                timeout,
            )
            return None

    def delete_session(self, session_id: str) -> None:
        """파이프라인 완료 후 메모리 정리. 존재하지 않는 세션은 무시한다."""
        self._store.pop(session_id, None)


# 모듈 레벨 싱글톤 (FastAPI 앱과 생명주기를 공유)
stories_store = StoriesStore()
```

> `entry["data"]`는 `Any | None` 타입이므로 `# type: ignore[return-value]` 추가.

- [x] **Step 4: CI 린트 확인**

```bash
black --check src/api/stories_store.py
isort --check-only src/api/stories_store.py
ruff check src/api/stories_store.py
mypy src/api/stories_store.py --ignore-missing-imports
```

Expected: 에러 없음. 에러 발생 시 `black src/api/stories_store.py && isort src/api/stories_store.py`로 자동 수정.

- [x] **Step 5: 테스트 통과 확인**

```bash
pytest tests/api/test_stories_store.py -v
```

Expected: `7 passed`

- [x] **Step 6: 커밋**

```bash
git add src/api/stories_store.py tests/api/test_stories_store.py
git commit -m "feat: StoriesStore asyncio.Event 기반 세션별 임시 저장소 구현"
```

---

### Task 3: POST /api/stories/select 엔드포인트 (TDD)

**Files:**
- Create: `src/api/routes/stories.py`
- Create: `tests/api/test_stories_endpoint.py`
- Modify: `src/api/main.py`

- [x] **Step 1: 실패하는 테스트 작성**

`tests/api/test_stories_endpoint.py`:

```python
"""POST /api/stories/select 엔드포인트 테스트."""

from __future__ import annotations


class TestStoriesSelectEndpoint:
    """POST /api/stories/select 엔드포인트 테스트."""

    def test_valid_request_returns_200(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """올바른 페이로드 → 200 + success:true."""
        payload = {
            "session_id": "sess_test_001",
            "keywords": ["직장", "갈등"],
            "title": "나의 이야기",
            "description": "직장 내 갈등 상황",
        }
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 200
        assert response.json() == {"success": True}

    def test_missing_session_id_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """session_id 누락 → 422."""
        payload = {"keywords": ["직장"], "title": "T", "description": "D"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_missing_title_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """title 누락 → 422."""
        payload = {"session_id": "sess_001", "keywords": [], "description": "D"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_missing_description_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """description 누락 → 422."""
        payload = {"session_id": "sess_001", "keywords": [], "title": "T"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_empty_keywords_is_valid(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """keywords가 빈 리스트여도 유효하다."""
        payload = {
            "session_id": "sess_002",
            "keywords": [],
            "title": "T",
            "description": "D",
        }
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 200

    def test_stores_data_in_store(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """수신 데이터가 StoriesStore에 저장되고 Event가 set된다."""
        from src.api.stories_store import stories_store

        session_id = "sess_store_check_001"
        payload = {
            "session_id": session_id,
            "keywords": ["감정"],
            "title": "감정 이야기",
            "description": "나의 감정",
        }
        test_client.post("/api/stories/select", json=payload)

        stored = stories_store._store.get(session_id)
        assert stored is not None
        assert stored["data"]["keywords"] == ["감정"]
        assert stored["event"].is_set()

        # 정리
        stories_store.delete_session(session_id)
```

> `test_client` 픽스처는 `tests/api/conftest.py`에 정의된 FastAPI TestClient. mypy가 픽스처 타입을 추론 못하므로 `# type: ignore[no-untyped-def]` 추가.

- [x] **Step 2: 테스트 실패 확인**

```bash
pytest tests/api/test_stories_endpoint.py -v 2>&1 | head -15
```

Expected: `404 Not Found` (엔드포인트 미등록)

- [x] **Step 3: 엔드포인트 구현**

`src/api/routes/stories.py`:

```python
"""
Stories 수신 라우터.

백엔드가 POST /api/stories/select로 Stories 데이터를 푸시한다.
수신 즉시 StoriesStore에 저장하고 대기 중인 파이프라인 노드를 깨운다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.stories_store import stories_store

router = APIRouter()


class StoriesSelectRequest(BaseModel):
    """POST /api/stories/select 요청 스키마."""

    session_id: str
    keywords: list[str]
    title: str
    description: str


@router.post("/select")
async def receive_stories(request: StoriesSelectRequest) -> dict[str, Any]:
    """
    Stories 데이터 수신.

    백엔드가 사용자의 Stories 선택 완료 후 호출한다.
    수신 즉시 StoriesStore에 저장하여 TIER 4 대기 노드를 깨운다.
    """
    stories_store.set_stories(
        request.session_id,
        {
            "keywords": request.keywords,
            "title": request.title,
            "description": request.description,
        },
    )
    return {"success": True}
```

- [x] **Step 4: main.py에 라우터 등록**

`src/api/main.py` 23번째 줄 import 수정:

```python
# 기존
from src.api.routes import graph, health, podcasts, sessions

# 변경
from src.api.routes import graph, health, podcasts, sessions, stories
```

`app.include_router(sessions.router, ...)` 바로 다음에 추가:

```python
app.include_router(stories.router, prefix="/api/stories", tags=["Stories"])
```

결과 경로: `POST /api/stories/select`

- [x] **Step 5: CI 린트 확인**

```bash
black --check src/api/routes/stories.py src/api/main.py
isort --check-only src/api/routes/stories.py src/api/main.py
ruff check src/api/routes/stories.py src/api/main.py
mypy src/api/routes/stories.py src/api/main.py --ignore-missing-imports
```

Expected: 에러 없음.

- [x] **Step 6: 테스트 통과 확인**

```bash
pytest tests/api/test_stories_endpoint.py -v
```

Expected: `6 passed`

- [x] **Step 7: 전체 테스트 통과 확인**

```bash
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

Expected: `576 passed` (기존 563 + 신규 13)

- [x] **Step 8: 커밋**

```bash
git add src/api/routes/stories.py src/api/main.py tests/api/test_stories_endpoint.py
git commit -m "feat: POST /api/stories/select 수신 엔드포인트 구현 및 등록"
```

---

### Task 4: 스텁 코드 및 죽은 코드 제거

**Files:**
- Modify: `src/api/routes/sessions.py`
- Modify: `src/api/client.py`

- [x] **Step 1: sessions.py — 외부 참조 없음 확인**

```bash
grep -rn "personalization.context\|_personalization_context_store\|PersonalizationContextRequest" \
  src/ tests/
```

Expected: `src/api/routes/sessions.py`에서만 나타남

- [x] **Step 2: sessions.py 스텁 3블록 삭제**

`src/api/routes/sessions.py`에서 다음 3개 블록을 삭제한다.

**블록 1 — 26~30번째 줄 (스토어 변수 + 주석):**

```python
# =========================================================================
# 개인화 맥락 수신 — in-memory 임시 저장소
# =========================================================================
# TODO: 추후 Redis 또는 영속 저장소로 교체
_personalization_context_store: dict[str, dict[str, Any]] = {}
```

**블록 2 — 33~39번째 줄 (요청 스키마 클래스):**

```python
class PersonalizationContextRequest(BaseModel):
    """Personalizer 사전 입력 수신 요청 스키마."""

    session_id: str
    keywords: list[str]
    title: str
    description: str
```

**블록 3 — 91~118번째 줄 (엔드포인트 함수 전체):**

```python
@router.post(
    "/{session_id}/personalization-context",
    ...
)
async def receive_personalization_context(...) -> dict:
    ...
```

삭제 후 `from typing import Any` import가 더 이상 사용되지 않으면 함께 제거한다.

- [x] **Step 3: client.py — load_stories 호출처 없음 확인**

```bash
grep -rn "load_stories" src/
```

Expected: `src/api/client.py` 정의 줄만 나타남

- [x] **Step 4: client.py — load_stories 삭제**

`src/api/client.py` 309~354번째 줄의 `load_stories()` 메서드 전체 삭제.

- [x] **Step 5: CI 린트 확인**

```bash
black --check src/api/routes/sessions.py src/api/client.py
isort --check-only src/api/routes/sessions.py src/api/client.py
ruff check src/api/routes/sessions.py src/api/client.py
mypy src/api/routes/sessions.py src/api/client.py --ignore-missing-imports
```

Expected: 에러 없음.

- [x] **Step 6: 전체 테스트 통과 확인**

```bash
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

Expected: `576 passed`

- [x] **Step 7: 커밋**

```bash
git add src/api/routes/sessions.py src/api/client.py
git commit -m "refactor: personalization-context 스텁 코드 및 load_stories 죽은 코드 제거"
```

---

### Task 5: AgentState에 stories_context 필드 추가 (Protected)

> ⚠️ `src/models/agent_state.py`는 Protected File — 3인 합의 완료 후 수정한다.

**Files:**
- Modify: `src/models/agent_state.py`

- [x] **Step 1: stories_context 필드 추가**

`src/models/agent_state.py` 56번째 줄 `visual_data: dict[str, Any]` 바로 다음에 추가:

```python
stories_context: dict[str, Any] | None  # Stories 선택 데이터 (keywords, title, description)
```

추가 후 해당 섹션:
```python
    # === 검증/부가 필드 ===
    risk_level: int
    risk_score: float
    safety_flags: dict[str, Any]
    validation_result: dict[str, Any]
    final_output: str
    visual_data: dict[str, Any]
    stories_context: dict[str, Any] | None  # ← 추가
```

- [x] **Step 2: CI 린트 확인**

```bash
black --check src/models/agent_state.py
ruff check src/models/agent_state.py
mypy src/models/agent_state.py --ignore-missing-imports
```

Expected: 에러 없음.

- [x] **Step 3: 전체 테스트 통과 확인**

```bash
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

Expected: `576 passed`

- [x] **Step 4: 커밋**

```bash
git add src/models/agent_state.py
git commit -m "feat: AgentState에 stories_context 필드 추가 (Protected — 3인 합의)"
```

---

### Task 6: wait_for_stories_node 구현 + workflow.py 수정 (Protected)

> ⚠️ `src/graph/workflow.py`는 Protected File — 3인 합의 완료 후 수정한다.

**Files:**
- Create: `tests/graph/test_workflow_stories_wait.py`
- Modify: `src/graph/workflow.py`

- [x] **Step 1: 실패하는 테스트 작성**

`tests/graph/test_workflow_stories_wait.py`:

```python
"""wait_for_stories_node 및 route_after_wait_stories 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from src.graph.workflow import route_after_wait_stories


class TestRouteAfterWaitStories:
    def test_stories_timeout_routes_to_error(self) -> None:
        """next_step이 stories_timeout이면 stories_error 반환."""
        state = {"next_step": "stories_timeout", "session_id": "sess_001"}
        assert route_after_wait_stories(state) == "stories_error"

    def test_success_routes_to_script_personalizer(self) -> None:
        """next_step이 빈 문자열이면 script_personalizer 반환."""
        state = {
            "stories_context": {"keywords": [], "title": "T", "description": "D"},
            "next_step": "",
        }
        assert route_after_wait_stories(state) == "script_personalizer"

    def test_no_next_step_routes_to_script_personalizer(self) -> None:
        """next_step 키가 없으면 script_personalizer 반환."""
        state: dict = {"session_id": "sess_002"}
        assert route_after_wait_stories(state) == "script_personalizer"


class TestWaitForStoriesNode:
    async def test_returns_stories_context_on_success(self) -> None:
        """데이터 수신 성공 시 stories_context를 반환한다."""
        from src.graph.workflow import wait_for_stories_node

        mock_data = {"keywords": ["직장"], "title": "T", "description": "D"}
        state: dict = {"session_id": "sess_wait_001"}

        with (
            patch(
                "src.graph.workflow.stories_store.wait_for_stories",
                new=AsyncMock(return_value=mock_data),
            ),
            patch("src.graph.workflow.stories_store.delete_session"),
        ):
            result = await wait_for_stories_node(state)

        assert result["stories_context"] == mock_data
        assert result.get("next_step") != "stories_timeout"

    async def test_returns_stories_timeout_on_timeout(self) -> None:
        """타임아웃 시 next_step: stories_timeout을 반환한다."""
        from src.graph.workflow import wait_for_stories_node

        state: dict = {"session_id": "sess_wait_002"}

        with (
            patch(
                "src.graph.workflow.stories_store.wait_for_stories",
                new=AsyncMock(return_value=None),
            ),
            patch("src.graph.workflow.stories_store.delete_session"),
        ):
            result = await wait_for_stories_node(state)

        assert result["next_step"] == "stories_timeout"
        assert result.get("stories_context") is None
```

> `asyncio_mode = "auto"`이므로 `@pytest.mark.asyncio` 불필요. `with (A, B):` 구문은 Python 3.10+에서 동작하며 CI(3.11/3.12) 기준 정상.

- [x] **Step 2: 테스트 실패 확인**

```bash
pytest tests/graph/test_workflow_stories_wait.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'route_after_wait_stories'`

- [x] **Step 3: workflow.py — import 추가**

`src/graph/workflow.py` 40번째 줄 `from config.loader import get_settings` 바로 다음에 추가:

```python
from src.api.stories_store import stories_store
```

isort 순서: stdlib → third-party(langgraph) → local(config, src). `src.api.stories_store`는 local이므로 `from config.loader` 뒤에 위치한다.

- [x] **Step 4: workflow.py — 모듈 상수 추가**

73번째 줄 `_ASYNC_TIMEOUT: int = _settings.async_timeout` 바로 다음에 추가:

```python
_STORIES_WAIT_TIMEOUT: int = _settings.stories_wait_timeout
```

- [x] **Step 5: workflow.py — 라우팅 함수 추가**

`route_after_tier3_podcast` 함수 바로 다음(500번째 줄 근처)에 추가:

```python
def route_after_wait_stories(state: AgentState) -> str:
    """
    wait_for_stories_node 이후 라우터.

    Returns:
        "script_personalizer" | "stories_error"
    """
    if state.get("next_step") == "stories_timeout":
        return "stories_error"
    return "script_personalizer"
```

- [x] **Step 6: workflow.py — 노드 함수 2개 추가**

`crisis_response_node` 함수 바로 앞(506번째 줄 근처)에 추가:

```python
async def wait_for_stories_node(state: AgentState) -> dict[str, Any]:
    """
    Stories 데이터 대기 노드 (TIER 3 완료 후 TIER 4 진입 전).

    _STORIES_WAIT_TIMEOUT(settings.stories.wait_timeout_seconds, 기본 300초) 동안 대기한다.
    타임아웃 시 next_step: 'stories_timeout'을 반환하여 에러 노드로 라우팅된다.
    """
    session_id = state.get("session_id", "")
    logger.info(
        "[WaitForStories] 대기 시작 — session_id=%s, timeout=%ds",
        session_id,
        _STORIES_WAIT_TIMEOUT,
    )

    data = await stories_store.wait_for_stories(session_id, float(_STORIES_WAIT_TIMEOUT))
    stories_store.delete_session(session_id)

    if data is None:
        logger.warning("[WaitForStories] 타임아웃 — session_id=%s", session_id)
        return {"next_step": "stories_timeout"}

    logger.info("[WaitForStories] 데이터 수신 완료 — session_id=%s", session_id)
    return {"stories_context": data, "next_step": ""}


async def stories_timeout_error_node(state: AgentState) -> dict[str, Any]:
    """
    Stories 타임아웃 에러 응답 노드.

    5분 내 Stories 데이터 미수신 시 에러 응답을 생성하고 파이프라인을 종료한다.
    """
    session_id = state.get("session_id", "")
    logger.error("[StoriesError] Stories 타임아웃 — session_id=%s", session_id)
    return {
        "final_output": (
            "Stories 데이터를 수신하지 못해 처리를 완료할 수 없습니다. 다시 시도해주세요."
        ),
        "next_step": "stories_error",
    }
```

> `final_output` 문자열이 100자 초과이므로 괄호로 묶어 Black 포맷에 맞춘다.

- [x] **Step 7: build_podcast_graph() 수정 (3곳)**

`build_podcast_graph()` 함수(534번째 줄 근처) 내부를 수정한다.

**수정 1 — 노드 추가** (`graph.add_node("script_personalizer", _sp_timeout)` 다음):

```python
graph.add_node("wait_for_stories", wait_for_stories_node)    # type: ignore[arg-type]
graph.add_node("stories_error", stories_timeout_error_node)  # type: ignore[arg-type]
```

**수정 2 — 조건부 엣지 변경** (`"tier4_podcast": "script_personalizer"` → `"wait_for_stories"`):

```python
graph.add_conditional_edges(
    "batch_validator",
    route_after_tier3_podcast,
    {
        "tier4_podcast": "wait_for_stories",
        "tier2_podcast": "increment_iteration",
        "crisis_response": "crisis_response",
    },
)
```

**수정 3 — wait_for_stories 이후 엣지 추가** (`graph.add_edge("script_personalizer", "async_post")` 앞):

```python
graph.add_conditional_edges(
    "wait_for_stories",
    route_after_wait_stories,
    {
        "script_personalizer": "script_personalizer",
        "stories_error": "stories_error",
    },
)
graph.add_edge("stories_error", END)
```

- [x] **Step 8: build_unified_graph() 동일 적용 (3곳)**

`build_unified_graph()` 함수(594번째 줄 근처) 내부에 동일하게 3곳 수정한다.

**수정 1 — 노드 추가** (`graph.add_node("script_personalizer", _script_personalizer_with_timeout)` 다음):

```python
graph.add_node("wait_for_stories", wait_for_stories_node)    # type: ignore[arg-type]
graph.add_node("stories_error", stories_timeout_error_node)  # type: ignore[arg-type]
```

**수정 2 — 조건부 엣지 변경** (`"tier4_podcast": "script_personalizer"` → `"wait_for_stories"`):

```python
graph.add_conditional_edges(
    "batch_validator",
    route_after_tier3_podcast,
    {
        "tier4_podcast": "wait_for_stories",
        "tier2_podcast": "increment_iteration_pod",
        "crisis_response": "crisis_response",
    },
)
```

**수정 3 — wait_for_stories 이후 엣지 추가** (`graph.add_edge("script_personalizer", "async_post")` 앞):

```python
graph.add_conditional_edges(
    "wait_for_stories",
    route_after_wait_stories,
    {
        "script_personalizer": "script_personalizer",
        "stories_error": "stories_error",
    },
)
graph.add_edge("stories_error", END)
```

- [x] **Step 9: CI 린트 확인**

```bash
black --check src/graph/workflow.py
isort --check-only src/graph/workflow.py
ruff check src/graph/workflow.py
mypy src/graph/workflow.py --ignore-missing-imports
```

Expected: 에러 없음. Black이 포맷 오류를 지적하면 `black src/graph/workflow.py`로 자동 수정 후 재확인.

- [x] **Step 10: 테스트 통과 확인**

```bash
pytest tests/graph/test_workflow_stories_wait.py -v
```

Expected: `5 passed`

- [x] **Step 11: 전체 테스트 통과 확인**

```bash
pytest tests/ -x -q -m "not live" 2>&1 | tail -3
```

Expected: `581 passed` (기존 576 + 신규 5)

- [x] **Step 12: 커밋**

```bash
git add src/graph/workflow.py tests/graph/test_workflow_stories_wait.py
git commit -m "feat: wait_for_stories_node 추가 — TIER 3→4 사이 Stories 데이터 대기 (Protected)"
```

---

## 최종 검증

- [ ] **전체 CI 시뮬레이션**

```bash
black --check .
isort --check-only .
ruff check .
mypy src/ --ignore-missing-imports
pytest tests/ -q -m "not live" 2>&1 | tail -5
```

Expected: 모든 체크 통과, `581 passed`

- [ ] **PLAN_INDEX.md 업데이트**

`docs/superpowers/PLAN_INDEX.md` 마지막 항목 다음에 추가:

```markdown
| #35 | feature/validation-stories-wait-0414 | Stories asyncio.Event 수신 인프라 + TIER 4 wait_for_stories_node. Plan #34 대체 |
```

```bash
git add docs/superpowers/PLAN_INDEX.md
git commit -m "docs: Plan #35 PLAN_INDEX 업데이트"
```

---

## 관련 문서

- 설계 스펙: `docs/superpowers/specs/2026-04-14-stories-wait-mechanism-design.md`
- 대체 계획: Plan #34 (`docs/superpowers/plans/2026-04-13-stories-receive-infra.md`) — 이 계획에 흡수됨
- Protected File 정책: `CONTRIBUTING.md` → Protected Files 섹션

---

*Plan #35 — 2026-04-14 — Stories 수신 인프라 + TIER 4 대기 메커니즘 (CI 기준 반영)*

# 에피소드 메모리 저장 트리거 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 팟캐스트 생성 완료 후 AgentState의 `memory_write` 플래그를 통해 에피소드 메모리를 자동 저장하고, deploy.yml에 PR #85가 도입한 신규 KT Cloud/Pinecone 시크릿을 반영한다.

**Architecture:** Script Personalizer(TIER 4)가 최종 스크립트 생성 후 `memory_write=True`, `memory_text=<에피소드 텍스트>`, `memory_metadata={user_id, session_id, episode_id}`를 state에 설정한다. `async_post_processing_node`가 파이프라인 종료 시점에 이 플래그를 확인하고 `EpisodeMemoryAgent._save_to_store()`를 호출하여 Pinecone에 저장한다.

**Tech Stack:** LangGraph AgentState (TypedDict), EpisodeMemoryAgent (Pinecone + KT Cloud embedding), pytest-asyncio, GitHub Actions secrets

---

## 전제조건

> ✅ **PR #85 (feature/agents-gaeun) 머지 완료** (2026-04-08 07:54 KST)
>
> `EpisodeMemoryAgent._save_to_store()`와 `BaseMemoryAgent`의 `memory_write` 트리거 구조가 `develop`에 반영됐다.
> 이 계획은 즉시 구현 가능하다.

---

## 파일 변경 목록

| 파일 | 작업 | 소유 | 비고 |
|------|------|------|------|
| `src/models/agent_state.py` | 수정 | **Protected — 3인 합의 필수** | `memory_write`, `memory_text`, `memory_metadata` 필드 추가 |
| `src/agents/podcast/script_personalizer.py` | 수정 | 개발자1 담당 → 협의 필요 | process() 반환에 memory 플래그 추가 |
| `src/graph/workflow.py` | 수정 | **Protected — 3인 합의 필수** | async_post_processing_node에 메모리 저장 호출 추가 |
| `.github/workflows/deploy.yml` | 수정 | 공동 | 신규 KT Cloud/Pinecone 시크릿 7개 추가 |
| `tests/agents/test_script_personalizer.py` | 수정 | 개발자1 | memory_write 반환 검증 테스트 추가 |
| `tests/graph/test_workflow.py` | 수정 | 개발자2 | async_post memory 저장 트리거 테스트 추가 |

---

## Task 1: AgentState에 메모리 저장 트리거 필드 추가

> ⚠️ **Protected File: 수정 전 3인(개발자1, 2, 3) 합의 필수**
> Slack/PR 코멘트로 합의 후 진행한다.

**Files:**
- Modify: `src/models/agent_state.py:48-59`
- Test: `tests/models/test_agent_state.py` (없으면 신규 생성)

- [ ] **Step 1: 실패 테스트 작성**

`tests/models/test_agent_state.py`에 아래를 추가한다. 파일이 없으면 생성한다.

```python
from src.models.agent_state import AgentState


def test_agent_state_has_memory_write_fields():
    """AgentState에 memory_write 관련 3개 필드가 존재한다."""
    hints = AgentState.__annotations__
    assert "memory_write" in hints, "memory_write 필드 없음"
    assert "memory_text" in hints, "memory_text 필드 없음"
    assert "memory_metadata" in hints, "memory_metadata 필드 없음"


def test_agent_state_memory_write_types():
    """memory_write는 bool, memory_text는 str, memory_metadata는 dict."""
    hints = AgentState.__annotations__
    # total=False TypedDict이므로 Optional로 감싸지 않는다 — 타입 자체만 확인
    assert hints["memory_write"] is bool
    assert hints["memory_text"] is str
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/models/test_agent_state.py -v
```

Expected: FAIL with `AssertionError: memory_write 필드 없음`

- [ ] **Step 3: AgentState에 필드 추가**

`src/models/agent_state.py`의 `# === 검증/부가 필드 ===` 섹션 아래에 새 섹션을 추가한다.

```python
    # === 메모리 저장 트리거 (Script Personalizer → async_post) ===
    memory_write: bool          # True이면 async_post에서 에피소드 메모리 저장 실행
    memory_text: str            # 저장할 에피소드 텍스트 (segments 연결)
    memory_metadata: dict[str, Any]  # 저장 메타데이터 (user_id, session_id, episode_id)
```

최종 `agent_state.py` 검증/부가 + 제어 영역은 다음과 같아야 한다:

```python
    # === 검증/부가 필드 ===
    risk_level: int
    risk_score: float
    safety_flags: dict[str, Any]
    validation_result: dict[str, Any]
    final_output: str
    visual_data: dict[str, Any]

    # === 메모리 저장 트리거 (Script Personalizer → async_post) ===
    memory_write: bool
    memory_text: str
    memory_metadata: dict[str, Any]

    # === 제어 필드 ===
    next_step: str
    execution_plan: dict[str, Any]
    iteration_count: int
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/models/test_agent_state.py -v
```

Expected: PASS

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v -m "not live" --tb=short 2>&1 | tail -20
```

Expected: 기존 통과 수와 동일하게 통과. FAIL 없음.

- [ ] **Step 6: 커밋**

```bash
git add src/models/agent_state.py tests/models/test_agent_state.py
git commit -m "feat: AgentState에 memory_write/memory_text/memory_metadata 필드 추가"
```

---

## Task 2: Script Personalizer — memory_write 플래그 설정

> ⚠️ **개발자1 담당 파일 (script_personalizer.py)**
> 개발자2가 직접 수정하는 경우 PR 리뷰에서 개발자1의 승인을 받는다.

**Files:**
- Modify: `src/agents/podcast/script_personalizer.py` (process 반환 부분, 약 라인 199~215)
- Test: `tests/agents/test_script_personalizer.py`

**배경:** `PersonalizedScript`는 `segments: list[ScriptSegment]`를 가지며, 각 `ScriptSegment.script_text`가 실제 팟캐스트 텍스트다. `memory_text`는 모든 세그먼트 텍스트를 개행으로 이어붙인 값으로 한다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/agents/test_script_personalizer.py`의 기존 테스트 파일에 아래를 추가한다.

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent
from src.models.schemas import PersonalizedScript, ScriptSegment, PersonalizationMeta


def _make_state_with_draft():
    """테스트용 최소 AgentState"""
    seg1 = {
        "segment_id": "s1",
        "segment_type": "opening",
        "duration_minutes": 2,
        "script_text": "안녕하세요, 오늘의 팟캐스트입니다.",
        "word_count": 10,
        "emotional_tone": "warm",
    }
    seg2 = {
        "segment_id": "s2",
        "segment_type": "closing",
        "duration_minutes": 1,
        "script_text": "오늘도 들어주셔서 감사합니다.",
        "word_count": 8,
        "emotional_tone": "calm",
    }
    return {
        "user_id": "user_test_01",
        "session_id": "sess_test_01",
        "script_draft": {
            "episode_id": "ep_test_01",
            "episode_title": "테스트 에피소드",
            "total_duration": 3,
            "segments": [seg1, seg2],
            "key_insights": [],
            "themes": [],
            "is_valid": True,
            "validation_score": 0.9,
            "validation_messages": [],
        },
        "risk_level": 0,
        "safety_flags": {"status": "safe"},
    }


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_write_true():
    """Script Personalizer 완료 후 memory_write=True가 반환에 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()

    result = await agent(state)

    assert result.get("memory_write") is True, "memory_write=True가 반환에 없음"


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_text():
    """memory_text에 에피소드 세그먼트 텍스트가 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()

    result = await agent(state)

    memory_text = result.get("memory_text", "")
    assert "안녕하세요" in memory_text, "첫 번째 세그먼트 텍스트가 memory_text에 없음"
    assert "감사합니다" in memory_text, "두 번째 세그먼트 텍스트가 memory_text에 없음"


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_metadata():
    """memory_metadata에 user_id, session_id, episode_id가 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()

    result = await agent(state)

    meta = result.get("memory_metadata", {})
    assert meta.get("user_id") == "user_test_01"
    assert meta.get("session_id") == "sess_test_01"
    assert "episode_id" in meta
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/agents/test_script_personalizer.py::test_script_personalizer_sets_memory_write_true -v
```

Expected: FAIL with `AssertionError: memory_write=True가 반환에 없음`

- [ ] **Step 3: Script Personalizer process() 반환에 memory 필드 추가**

`src/agents/podcast/script_personalizer.py`에서 `process()` 메서드의 정상 반환 (라인 199~202 부근)을 수정한다.

**수정 전:**
```python
            return {
                # 문자열 형태의 최종 스크립트 반환
                "final_output": personalized_script.model_dump_json()
            }
```

**수정 후:**
```python
            # 메모리 저장용 에피소드 텍스트 추출 (세그먼트 텍스트 연결)
            memory_text = "\n\n".join(
                seg.script_text
                for seg in personalized_script.segments
                if seg.script_text
            )

            return {
                "final_output": personalized_script.model_dump_json(),
                "memory_write": True,
                "memory_text": memory_text,
                "memory_metadata": {
                    "user_id": state.get("user_id", ""),
                    "session_id": state.get("session_id", ""),
                    "episode_id": personalized_script.episode_id,
                    "episode_title": personalized_script.episode_title,
                },
            }
```

fallback 반환 (라인 213~215 부근)도 동일하게 수정한다.

**수정 전:**
```python
            return {"final_output": fallback}
```

**수정 후:**
```python
            # fallback에서도 memory_write 설정 (빈 텍스트면 _save_to_store가 False 반환)
            fallback_script_obj = self._create_fallback_script(
                validated_script, str(state.get("user_id", ""))
            )
            fallback_memory_text = "\n\n".join(
                seg.script_text
                for seg in fallback_script_obj.segments
                if seg.script_text
            )
            return {
                "final_output": fallback,
                "memory_write": True,
                "memory_text": fallback_memory_text,
                "memory_metadata": {
                    "user_id": state.get("user_id", ""),
                    "session_id": state.get("session_id", ""),
                    "episode_id": fallback_script_obj.episode_id,
                    "episode_title": fallback_script_obj.episode_title,
                },
            }
```

> **주의:** fallback 경로에서는 `validated_script` 변수가 try 블록 외부에서도 접근 가능한지 확인한다.
> `validated_script`가 except 블록에서 접근 불가능한 경우, `fallback_memory_text = ""`으로 대체한다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/test_script_personalizer.py::test_script_personalizer_sets_memory_write_true \
       tests/agents/test_script_personalizer.py::test_script_personalizer_sets_memory_text \
       tests/agents/test_script_personalizer.py::test_script_personalizer_sets_memory_metadata -v
```

Expected: 3개 모두 PASS

- [ ] **Step 5: Script Personalizer 기존 테스트 회귀 확인**

```bash
pytest tests/agents/test_script_personalizer.py -v -m "not live"
```

Expected: 기존 PASS + 신규 3개 PASS, FAIL 없음

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/script_personalizer.py tests/agents/test_script_personalizer.py
git commit -m "feat: Script Personalizer — memory_write/text/metadata 반환 추가"
```

---

## Task 3: async_post_processing_node — 에피소드 메모리 저장 호출

> ⚠️ **Protected File (workflow.py): 3인 합의 필수**
> async_post_processing_node 함수 내부만 수정하며, 노드 등록/엣지/라우터 변경 없음.

**Files:**
- Modify: `src/graph/workflow.py` (async_post_processing_node, 라인 377~408)
- Test: `tests/graph/test_workflow.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/graph/test_workflow.py`에 아래를 추가한다.

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.graph.workflow import async_post_processing_node


@pytest.mark.asyncio
async def test_async_post_calls_episode_memory_save_when_flag_set():
    """memory_write=True인 state에서 EpisodeMemoryAgent._save_to_store가 호출된다."""
    state = {
        "memory_write": True,
        "memory_text": "오늘의 팟캐스트 에피소드 텍스트입니다.",
        "memory_metadata": {
            "user_id": "user_01",
            "session_id": "sess_01",
            "episode_id": "ep_01",
            "episode_title": "테스트",
        },
        "final_output": '{"episode_id": "ep_01"}',
    }

    with patch(
        "src.graph.workflow.EpisodeMemoryAgent"
    ) as MockEpisodeMemory:
        mock_instance = MagicMock()
        mock_instance._save_to_store = AsyncMock(return_value=True)
        MockEpisodeMemory.return_value = mock_instance

        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            await async_post_processing_node(state)

        mock_instance._save_to_store.assert_called_once_with(
            "오늘의 팟캐스트 에피소드 텍스트입니다.",
            {
                "user_id": "user_01",
                "session_id": "sess_01",
                "episode_id": "ep_01",
                "episode_title": "테스트",
            },
        )


@pytest.mark.asyncio
async def test_async_post_skips_memory_save_when_flag_not_set():
    """memory_write가 없거나 False이면 EpisodeMemoryAgent가 생성되지 않는다."""
    state = {
        "final_output": '{"episode_id": "ep_01"}',
    }

    with patch(
        "src.graph.workflow.EpisodeMemoryAgent"
    ) as MockEpisodeMemory:
        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            await async_post_processing_node(state)

        MockEpisodeMemory.assert_not_called()


@pytest.mark.asyncio
async def test_async_post_memory_save_failure_does_not_raise():
    """EpisodeMemoryAgent._save_to_store가 예외를 던져도 파이프라인에 영향 없음."""
    state = {
        "memory_write": True,
        "memory_text": "텍스트",
        "memory_metadata": {"user_id": "u1"},
    }

    with patch(
        "src.graph.workflow.EpisodeMemoryAgent"
    ) as MockEpisodeMemory:
        mock_instance = MagicMock()
        mock_instance._save_to_store = AsyncMock(side_effect=RuntimeError("Pinecone 연결 실패"))
        MockEpisodeMemory.return_value = mock_instance

        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            # 예외가 외부로 전파되지 않아야 한다
            result = await async_post_processing_node(state)

        assert isinstance(result, dict)  # 빈 dict라도 반환
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/graph/test_workflow.py::test_async_post_calls_episode_memory_save_when_flag_set -v
```

Expected: FAIL (EpisodeMemoryAgent가 호출되지 않음)

- [ ] **Step 3: async_post_processing_node 수정**

`src/graph/workflow.py` 상단 import에 `EpisodeMemoryAgent`를 추가한다.

기존 import 영역(라인 100~110 부근)에 추가:

```python
from src.agents.podcast.episode_memory import EpisodeMemoryAgent  # noqa: E402
```

그런 다음 `async_post_processing_node` 함수를 수정한다.

**수정 전:**
```python
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    """
    비동기 후처리: Learning Agent.

    최종 응답 출력 후 백그라운드에서 실행.
    실패해도 파이프라인에 영향 없음.
    _ASYNC_TIMEOUT 적용.

    Note: 모니터링은 callback + Prometheus + LangSmith가 담당.
    """
    tasks = [
        asyncio.create_task(learning_node(state)),
    ]
```

**수정 후:**
```python
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    """
    비동기 후처리: Learning Agent + Episode Memory 저장.

    최종 응답 출력 후 백그라운드에서 실행.
    실패해도 파이프라인에 영향 없음.
    _ASYNC_TIMEOUT 적용.

    Note: 모니터링은 callback + Prometheus + LangSmith가 담당.
    """
    tasks = [
        asyncio.create_task(learning_node(state)),
    ]

    # memory_write 플래그가 설정된 경우 에피소드 메모리 저장
    if state.get("memory_write"):
        memory_text = state.get("memory_text", "")
        memory_metadata = state.get("memory_metadata", {})
        if memory_text:
            async def _save_episode_memory() -> dict[str, Any]:
                try:
                    agent = EpisodeMemoryAgent()
                    await agent._save_to_store(memory_text, memory_metadata)
                except Exception:
                    logger.exception("[ASYNC] 에피소드 메모리 저장 실패 — 무시")
                return {}

            tasks.append(asyncio.create_task(_save_episode_memory()))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/graph/test_workflow.py::test_async_post_calls_episode_memory_save_when_flag_set \
       tests/graph/test_workflow.py::test_async_post_skips_memory_save_when_flag_not_set \
       tests/graph/test_workflow.py::test_async_post_memory_save_failure_does_not_raise -v
```

Expected: 3개 모두 PASS

- [ ] **Step 5: workflow 전체 테스트 회귀 확인**

```bash
pytest tests/graph/ -v -m "not live" --tb=short
```

Expected: 기존 PASS + 신규 3개 PASS, FAIL 없음

- [ ] **Step 6: 커밋**

```bash
git add src/graph/workflow.py tests/graph/test_workflow.py
git commit -m "feat: async_post에 에피소드 메모리 저장 트리거 추가"
```

---

## Task 4: deploy.yml — 신규 KT Cloud / Pinecone 시크릿 추가

> PR #85(feature/agents-gaeun)가 도입한 환경변수 7개를 deploy.yml에 반영한다.

**Files:**
- Modify: `.github/workflows/deploy.yml` (deploy job의 `.env` 생성 부분, 라인 89~108)

**신규 시크릿 목록 (GitHub Repository Secrets에도 등록 필요):**

| 시크릿 이름 | 설명 | 기존 여부 |
|------------|------|----------|
| `KT_CLOUD_QUERY_ENDPOINT` | KT Cloud 쿼리 임베딩 엔드포인트 | 신규 |
| `KT_CLOUD_QUERY_TOKEN` | KT Cloud 쿼리 임베딩 API 토큰 | 신규 |
| `KT_CLOUD_PASSAGE_ENDPOINT` | KT Cloud 패시지 임베딩 엔드포인트 | 신규 |
| `KT_CLOUD_PASSAGE_TOKEN` | KT Cloud 패시지 임베딩 API 토큰 | 신규 |
| `KT_CLOUD_TEXTGEN_ENDPOINT` | KT Cloud 텍스트 생성 엔드포인트 | 신규 |
| `KT_CLOUD_TEXTGEN_TOKEN` | KT Cloud 텍스트 생성 API 토큰 | 신규 |
| `PINECONE_INDEX_EPISODE` | Pinecone 에피소드 메모리 인덱스명 | 신규 |
| `PINECONE_API_KEY` | Pinecone API 키 | ✅ 기존 |

- [ ] **Step 1: deploy.yml `.env` 생성 블록에 신규 시크릿 7개 추가**

`NEO4J_URL=bolt://neo4j:7687` 라인 다음, `PINECONE_API_KEY` 라인 앞에 삽입한다.

**수정 전 (라인 105~107 부근):**
```yaml
              "printf '%s\n' 'NEO4J_URL=bolt://neo4j:7687' >> .env",
              "printf '%s\n' 'PINECONE_API_KEY=${{ secrets.PINECONE_API_KEY }}' >> .env",
```

**수정 후:**
```yaml
              "printf '%s\n' 'NEO4J_URL=bolt://neo4j:7687' >> .env",
              "printf '%s\n' 'KT_CLOUD_QUERY_ENDPOINT=${{ secrets.KT_CLOUD_QUERY_ENDPOINT }}' >> .env",
              "printf '%s\n' 'KT_CLOUD_QUERY_TOKEN=${{ secrets.KT_CLOUD_QUERY_TOKEN }}' >> .env",
              "printf '%s\n' 'KT_CLOUD_PASSAGE_ENDPOINT=${{ secrets.KT_CLOUD_PASSAGE_ENDPOINT }}' >> .env",
              "printf '%s\n' 'KT_CLOUD_PASSAGE_TOKEN=${{ secrets.KT_CLOUD_PASSAGE_TOKEN }}' >> .env",
              "printf '%s\n' 'KT_CLOUD_TEXTGEN_ENDPOINT=${{ secrets.KT_CLOUD_TEXTGEN_ENDPOINT }}' >> .env",
              "printf '%s\n' 'KT_CLOUD_TEXTGEN_TOKEN=${{ secrets.KT_CLOUD_TEXTGEN_TOKEN }}' >> .env",
              "printf '%s\n' 'PINECONE_INDEX_EPISODE=${{ secrets.PINECONE_INDEX_EPISODE }}' >> .env",
              "printf '%s\n' 'PINECONE_API_KEY=${{ secrets.PINECONE_API_KEY }}' >> .env",
```

- [ ] **Step 2: deploy.yml YAML 문법 확인**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`

- [ ] **Step 3: GitHub Repository Secrets 등록 (팀원 수동 작업)**

아래 7개 시크릿을 GitHub 저장소 → Settings → Secrets → Actions에 등록한다.
**KT Cloud 값은 개발자2(가은)가 제공한다.**

```
KT_CLOUD_QUERY_ENDPOINT   = <KT Cloud 쿼리 임베딩 URL>
KT_CLOUD_QUERY_TOKEN      = <Bearer 토큰>
KT_CLOUD_PASSAGE_ENDPOINT = <KT Cloud 패시지 임베딩 URL>
KT_CLOUD_PASSAGE_TOKEN    = <Bearer 토큰>
KT_CLOUD_TEXTGEN_ENDPOINT = <KT Cloud Text Generation URL (solar-mini)>
KT_CLOUD_TEXTGEN_TOKEN    = <Bearer 토큰>
PINECONE_INDEX_EPISODE    = <Pinecone 에피소드 인덱스명 (예: mind-log-episode-memory)>
```

> GitHub 시크릿 미등록 시 deploy 후 `.env`에 빈 값으로 기록되어 메모리 저장이 무음 실패한다.
> CI 테스트(mock 사용)는 영향 없음.

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: deploy.yml에 KT Cloud/Pinecone 에피소드 메모리 시크릿 추가"
```

---

## Task 5: 전체 통합 검증 및 PR 준비

- [ ] **Step 1: 전체 테스트 실행**

```bash
pytest tests/ -v -m "not live" --tb=short 2>&1 | tail -30
```

Expected: 기존 532 passed + 신규 테스트(Task 1~3에서 추가된 것) passed. FAIL 없음.

- [ ] **Step 2: mypy 타입 체크**

```bash
mypy src/models/agent_state.py src/agents/podcast/script_personalizer.py src/graph/workflow.py --ignore-missing-imports
```

Expected: `Success: no issues found`

- [ ] **Step 3: lint 확인**

```bash
ruff check src/models/agent_state.py src/agents/podcast/script_personalizer.py src/graph/workflow.py
black --check src/models/agent_state.py src/agents/podcast/script_personalizer.py src/graph/workflow.py
```

Expected: 에러 없음. 포맷 이슈 있으면 `black <파일>` 실행 후 재커밋.

- [ ] **Step 4: 브랜치 최종 확인**

```bash
git log --oneline -10
```

Expected: Task 1~4 커밋 4개가 쌓여 있음.

---

## 참고: 전체 데이터 흐름 (구현 후)

```
TIER 4: Script Personalizer
  └── process() 반환:
      ├── final_output: PersonalizedScript JSON
      ├── memory_write: True            ← 신규
      ├── memory_text: "세그먼트1\n\n세그먼트2..."  ← 신규
      └── memory_metadata: {user_id, session_id, episode_id, episode_title}  ← 신규

비동기: async_post_processing_node
  ├── learning_node(state)             ← 기존
  └── (memory_write=True이면)          ← 신규
      EpisodeMemoryAgent()._save_to_store(memory_text, memory_metadata)
        └── Pinecone namespace: mem_podcast_episode_{user_id}
            └── chunking → KT Cloud embedding-passage → upsert
```

---

*작성일: 2026-04-08 | 브랜치: feature/reasoning-docs-why-and-archive*

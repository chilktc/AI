# Agent Output Audit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에이전트 출력 감사에서 발견된 이슈를 수정한다. 에이전트가 빈 값을 참조하는 상황을 없애고, 프롬프트 출력 스키마와 코드가 일치하도록 맞춘다.

**Architecture:** TIER 0 → 1 → 2 → 3 → 4 순서로 수정한다. 상위 TIER의 출력이 바뀌면 하위 TIER가 받는 값도 바뀌기 때문에, 반드시 파이프라인 순서를 지켜야 한다.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, `unittest.mock.AsyncMock`, `unittest.mock.patch`

---

## v9 현황 요약 (2026-04-13)

### 완료 항목 (구현 불필요)

| 구분 | 내용 | 근거 |
|------|------|------|
| IC-1 | Intent Classifier whitelist 추출 | `_extract_intent_dict()` 이미 구현 (line 596-616) |
| SP-1 | Script Personalizer top-level emotional_journey 참조 제거 | commit `85f71f7` |
| SP-2 | Script Personalizer 레거시 `resolution`/`start_emotion` 제거 | commit `85f71f7` |
| EmotionalJourney 4-키 | `schemas.py` `resolution` → `climax`/`closing` | commit `85f71f7` |
| CA v2.2.0 프롬프트 | 9개 필드 + 4-키 emotional_journey 프롬프트 작성 | commit `85f71f7`, `settings.yaml` 핀닝 완료 |
| SG cascade 1차 수정 | `closing` 1차 키로 변경 (단, `resolution` 폴백 잔존) | commit `85f71f7` |
| content_analyses 협의 | API 테스트 200 OK → 백엔드 테이블 존재 확정 | 2026-04-13 전수 테스트 |
| graph_analyses 삭제 | 코드·상수·테스트 완전 제거. 로컬 스키마 불필요 | commit `884c18c`, RESOURCE 주석처리 |

### 미완료 Task (7건)

| # | 이슈 | TIER | 심각도 | 담당 브랜치 |
|---|------|------|--------|-----------|
| **Task 1** | SA-1+SA-2: Safety 출력 명시화 | TIER 1 | Medium | `feature/reasoning-*` |
| **Task 2** | EA-1: Emotion 폴백 하드코딩 제거 | TIER 1 | Low | `feature/reasoning-*` |
| **Task 3** | CA-1+CA-2+CA-3: `_validate_and_correct()` 화이트리스트 + `_build_db_payload()` | TIER 1 | **Critical** | `feature/validation-*` |
| **Task 4** | SG-1+SG-2: Mental Health 제거 + `resolution` 폴백 잔존 정리 + error 키 | TIER 2 | Medium | `feature/analysis-*` |
| **Task 5** | VI-1+VI-2: Visualization None 통과 + 에러 경로 키 누락 | TIER 2 | Medium | `feature/reasoning-*` |
| **Task 6** | BV-1+BV-2: Batch Validator LLM 통과 저장 + 조기반환 action 키 누락 | TIER 3 | Medium | `feature/validation-*` |
| **Task 7** | 횡단: type 상수 불일치 + PR SSE 키 이름 버그 | 횡단 | Low | 해당 파일 담당자 |

### 실행 순서

```
Task 1·2 (병렬) → Task 3 → Task 4 (Task 3 완료 후) → Task 5·6 (병렬) → Task 7
```

### 백엔드 협의

**모든 협의 완료. 추가 협의 불필요.**
- `content_analyses`: API 테스트 200 OK, 테이블 존재 확정
- `graph_analyses`: 코드 완전 삭제, 로컬 스키마 불필요
- `emotion_logs`: EA-1 수정 대상 `emotional_journey_hint`는 DB 컬럼 아님
- `podcast_episodes`, `visualization_meta`: DEFAULT 있음, 협의 불필요

---

## 참조

### 파이프라인

```
TIER 0: Intent Classifier → TIER 1: Safety/Emotion/CA/PR (병렬) → TIER 2: SG/VI (병렬) → TIER 3: BV → TIER 4: SP
```

### 에이전트별 저장 경로

| 에이전트 | 저장 방식 | resource | 테이블 | 상태 |
|---------|---------|---------|--------|------|
| Content Analyzer | `publisher.publish()` (TIER 1) | `content_analyses` | `content_analyses` | ✅ API 200 OK |
| Emotion Agent | `publisher.publish()` (TIER 1) | `emotion_logs` | `emotion_logs` | ✅ |
| Learning Agent | `client.save()` (비동기) | `learning` | `learning_patterns` | ✅ |
| Visualization | `_save_core_data` (라우트) | `visualizations` | `visualization_meta` | ✅ |
| 에피소드 | `_save_core_data` (라우트) | `podcast_episodes` | `podcast_episodes` | ✅ |

> `graph_analyses`는 2026-04-13에 완전 삭제됨 (commit `884c18c`).

### 제외 항목 (Pinecone 연동 후 처리)

| 이슈 | 에이전트 | 상태 |
|------|---------|------|
| EM-1 | Episode Memory | ✅ PR#86 완료 |
| KA-1 | Knowledge Agent | ⏳ Pinecone 연동 완료 시 |
| PR-1 | Podcast Reasoning | ⏳ KA-1 완료 후 |

### 연쇄 영향 맵 — emotional_journey 키 변경 (resolution → climax + closing)

| 파일 | 현재 | 수정 후 | 처리 |
|-----|------|--------|------|
| `schemas.py` | `resolution` | `climax`/`closing` | ✅ 완료 |
| `content_analyzer.py` 에러 경로 | 3-키 fallback | 4-키 구조 | Task 3 |
| `script_generator.py` `_generate_title` | `.get("resolution")` | `.get("closing")` | Task 4 |
| `script_personalizer.py` | `resolution` 참조 | `closing` 참조 | ✅ 완료 |
| `podcast_reasoning.yaml` CoT | `resolution` 참조 | `climax`/`closing` 참조 | Task 3 완료 후 별도 |

---

## 완료 Task 기록

### IC-1: Intent Classifier — ✅ 수정 불필요

`_extract_intent_dict()` (line 596-616)가 whitelist 기반 명시 추출 수행. `process()`의 모든 반환 경로에서 사용 중.

### SP-1+SP-2: Script Personalizer — ✅ commit `85f71f7`

- SP-1: `content_analysis.get("emotional_journey")` (nested read)로 수정
- SP-2: 레거시 `start_emotion`/`resolution_emotion`/`resolution` 제거, `opening/development/climax/closing` 사용
- TODO 잔존 (line 383-385): personalization-context API → Plan #34 구현 후 정리

### schemas.py EmotionalJourney — ✅ commit `85f71f7`

`resolution` 제거, `climax: str = Field(default="")` + `closing: str = Field(default="")` 추가 완료.

---

## Task 1: SA-1 + SA-2 — Safety Agent 출력 명시화 [TIER 1]

**담당 브랜치:** `feature/reasoning-*`

**문제:**
- SA-1: `"safety_flags": result` — LLM 응답 전체를 그대로 저장. 스펙에 없는 필드 유입 가능.
- SA-2: LLM 실패 시 폴백 dict에 `"flags": {}` 레거시 키 잔존.

**수정 후 safety_flags (4개 키만):** `status`, `risk_level`, `risk_score`, `required_in_script`

**데이터 흐름:**
```
Safety → state["safety_flags"] → podcasts.py(status), Script Generator(required_in_script)
```

**DB 저장 영향:** `podcast_episodes.safety_status` = `safety_flags.get("status", "safe")` — 수정 후에도 `status` 유지 → 협의 불필요 ✅

**Files:**
- Modify: `src/agents/podcast/safety.py:75–82, 97–101`
- Modify: `tests/agents/podcast/test_safety_agent.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/agents/podcast/test_safety_agent.py` 하단에 추가:

```python
@pytest.mark.asyncio
async def test_safety_flags_contains_only_four_expected_keys(agent: SafetyAgent) -> None:
    """safety_flags는 status/risk_level/risk_score/required_in_script 네 키만 가진다 (SA-1)."""
    llm_response = {
        "status": "safe",
        "risk_level": 0,
        "risk_score": 0.05,
        "required_in_script": [],
        "reasons": ["정보성 발화"],         # LLM 응답에 있지만 safety_flags에 넣으면 안 됨
        "extra_llm_field": "유입 금지",    # LLM이 임의로 추가한 필드
    }
    state = AgentState(
        user_input="오늘 기분이 좋아요", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert set(sf.keys()) == {"status", "risk_level", "risk_score", "required_in_script"}
    assert "extra_llm_field" not in sf
    assert "reasons" not in sf


@pytest.mark.asyncio
async def test_fallback_safety_flags_has_no_flags_key(agent: SafetyAgent) -> None:
    """LLM 호출 실패 시 폴백 safety_flags에 레거시 flags 키 없다 (SA-2)."""
    state = AgentState(
        user_input="오늘 날씨 좋아요", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    assert "flags" not in result["safety_flags"], "SA-2: 레거시 flags 키 잔존"
    assert "status" in result["safety_flags"]
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_safety_agent.py::test_safety_flags_contains_only_four_expected_keys -v -m "not live"
```

Expected: **FAIL** — `reasons`, `extra_llm_field` 포함됨

- [ ] **Step 3: safety.py 수정**

폴백 dict (line 75–82) — `"flags": {}` 제거:
```python
            result = {
                "risk_level": 0,
                "risk_score": 0.0,
                "status": "safe",
                "required_in_script": [],
                "error": "llm_call_failed",
            }
```

반환 구성 (line 97–101) — LLM 응답 전체 대신 명시 추출:
```python
        required = result.get("required_in_script", [])
        if not isinstance(required, list):
            required = []

        update_data = {
            "risk_level":   risk_level,
            "risk_score":   float(result.get("risk_score", 0.0)),
            "safety_flags": {
                "status":             status,
                "risk_level":         risk_level,
                "risk_score":         float(result.get("risk_score", 0.0)),
                "required_in_script": required,
            },
        }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_safety_agent.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/safety.py tests/agents/podcast/test_safety_agent.py
git commit -m "fix(safety): SA-1/SA-2 — safety_flags 명시 추출, 레거시 flags 키 제거"
```

---

## Task 2: EA-1 — Emotion Agent 폴백 하드코딩 제거 [TIER 1]

**담당 브랜치:** `feature/reasoning-*`

**문제:** LLM 실패 시 모든 사용자가 동일한 4개 고정 감정 힌트(`["공감", "정리", "실행 가능한 한 가지", "마무리"]`)를 받는다.

**데이터 흐름:**
```
Emotion → state["emotion_vectors"] → publisher → emotion_logs DB / Script Generator(TIER 2) 읽음
```

**DB 저장 영향:** `emotional_journey_hint`는 DB 컬럼 아님 (`init.sql:52-71` 확인). AgentState 내부 필드만 수정 → 협의 불필요 ✅

**Files:**
- Modify: `src/agents/podcast/emotion.py:120`
- Modify: `tests/agents/podcast/test_emotion.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_fallback_emotional_journey_hint_is_empty_not_hardcoded() -> None:
    """LLM 실패 시 emotional_journey_hint는 빈 리스트다 — 하드코딩 금지 (EA-1)."""
    from src.agents.podcast.emotion import EmotionAgent
    from src.models.agent_state import AgentState

    agent = EmotionAgent()
    state = AgentState(user_input="힘든 하루", user_id="u", session_id="s", mode="podcast")

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    hint = result.get("emotion_vectors", {}).get("emotional_journey_hint", "필드없음")
    assert hint == [], f"기대값 [], 실제값: {hint!r}"
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_emotion.py::test_fallback_emotional_journey_hint_is_empty_not_hardcoded -v -m "not live"
```

Expected: **FAIL** — `['공감', '정리', '실행 가능한 한 가지', '마무리']` 반환

- [ ] **Step 3: emotion.py 수정**

```python
# Before (line 120)
"emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],

# After
"emotional_journey_hint": [],
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_emotion.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/emotion.py tests/agents/podcast/test_emotion.py
git commit -m "fix(emotion): EA-1 — 폴백 emotional_journey_hint 빈 리스트로 변경"
```

---

## Task 3: CA-1 + CA-2 + CA-3 — Content Analyzer 코드 검증 적용 [TIER 1]

**담당 브랜치:** `feature/validation-*`

> **2026-04-13 상태:**
> - ✅ CA v2.2.0 프롬프트 작성 완료 (`prompts/podcast/content_analyzer.yaml`, commit `85f71f7`)
> - ✅ `settings.yaml` 핀닝 완료 (`content_analyzer: "2.2.0"`)
> - ❌ `_validate_and_correct()` 화이트리스트 미적용 — `dict(analysis)` 전체 복사 유지
> - ❌ `_build_db_payload()` 미구현
> - ❌ `confidence` 검증/기본값 미구현, `trace_id` publisher 미전달
> - ❌ `emotional_journey` 4-키 코드 강제 미구현 (프롬프트만 4-키 요청, 코드 무검증)
> - **Step 6 (프롬프트 작성) 건너뜀** — 이미 완료됨. Step 1~5, 7~8만 수행.
>
> **sub_themes**: CA v2.1.0/v2.2.0 프롬프트가 "3개 이상 필수"를 요청하지만, `_validate_and_correct()` 코드에 min 보장 없음.
> CA-2에서 min_sub_themes 코드 보장을 추가하면 Script Generator 수정 불필요.

**문제 3건:**

- **CA-1**: `corrected = dict(analysis)` — LLM 응답 전체 복사. 예상 외 필드 유입. `user_summary` 타입 미검증, `key_messages` 타입 미검증.
- **CA-2**: `sub_themes` min 검사 없음 — LLM이 빈 배열 반환해도 `[]` 그대로 통과.
- **CA-3**: 백엔드 API 계약과 코드 불일치 — `emotional_journey` 3키→4키, `confidence` 누락, `trace_id` 미전달.

**CA v2.2.0 필드 목록 (9개):**

| 필드 | 타입 | 비고 |
|-----|------|------|
| `user_summary` | `{keywords: list, summary: str}` | 구조 강제 |
| `main_theme` | `str` | 100자 제한 |
| `emotional_journey` | `{opening, development, climax, closing}` | 4-키 (v2.2.0) |
| `key_messages` | `list[str]` | 최대 5개 |
| `depth_level` | `str` | 코드가 결정 |
| `sub_themes` | `list[str]` | min 3개 보장 |
| `target_duration` | `int` | clamp(3-5) |
| `narrative_structure` | `str` | 유효값 검증 |
| `confidence` | `float` | 0.0-1.0 |

**데이터 흐름:**
```
CA → state["content_analysis"] (9개 필드) → SG, BV, SP가 읽음
CA → publisher.publish(db_payload) → content_analyses DB (9개 필드 + trace_id)
```

**DB 저장 영향:** `content_analyses` API 테스트 200 OK (2026-04-13 확인). 현재 페이로드도 수용됨. 화이트리스트 적용 후에도 호환.

**에러 경로 fallback 수정 필요** (`content_analyzer.py:88`):
```python
# 현재 (3-키)
"emotional_journey": {"opening": "", "development": "", "resolution": ""}
# 수정 후 (4-키)
"emotional_journey": {"opening": "", "development": "", "climax": "", "closing": ""}
```

**Files:**
- Modify: `src/agents/podcast/content_analyzer.py:195–243`
- Modify: `tests/agents/podcast/test_content_analyzer.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/agents/podcast/test_content_analyzer.py` 하단에 추가:

```python
# === CA-1/CA-2/CA-3 출력 필드 화이트리스트 + min_sub_themes 보장 ===


def test_validate_and_correct_excludes_unexpected_fields(
    agent: ContentAnalyzerAgent,
) -> None:
    """_validate_and_correct가 예상 외 LLM 필드를 결과에 포함하지 않는다 (CA-1)."""
    analysis = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "resolution": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": ["스트레스", "감정", "관계"],
        "unknown_new_field": "임의 LLM 추가 필드",  # 허용되지 않는 필드
        "debug_info": {"tokens": 125},               # 허용되지 않는 필드
    }
    result = agent._validate_and_correct(analysis, depth_level="moderate")

    assert "unknown_new_field" not in result, "임의 LLM 필드 유입 금지"
    assert "debug_info" not in result, "디버그 필드 유입 금지"
    assert "sub_themes" in result
    assert len(result["sub_themes"]) >= 3, "min_sub_themes 보장"


def test_validate_and_correct_enforces_min_sub_themes(
    agent: ContentAnalyzerAgent,
) -> None:
    """LLM이 sub_themes를 빈 배열로 반환하면 min_sub_themes 보정 (CA-2)."""
    analysis = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "resolution": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": [],  # LLM이 빈 배열 반환 — min 미달
    }
    result = agent._validate_and_correct(analysis, depth_level="moderate")

    assert len(result["sub_themes"]) >= agent.min_sub_themes, (
        f"sub_themes 최소 {agent.min_sub_themes}개 보장 실패"
    )


def test_build_db_payload_includes_trace_id(
    agent: ContentAnalyzerAgent,
) -> None:
    """_build_db_payload가 trace_id를 포함한다."""
    validated = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "climax": "전환", "closing": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],
        "target_duration": 5,
        "narrative_structure": "reflection",
        "confidence": 0.85,
    }
    db_payload = agent._build_db_payload(validated, trace_id="trace_abc")

    assert db_payload["trace_id"] == "trace_abc"
    assert db_payload["main_theme"] == "스트레스 관리"
    assert db_payload["sub_themes"] == ["직장 스트레스", "감정 조절", "자기돌봄"]


def test_validate_and_correct_validates_user_summary_type(
    agent: ContentAnalyzerAgent,
) -> None:
    """user_summary가 dict 아닐 때 빈 구조로 보정한다 (CA-1)."""
    analysis = {
        "user_summary": "문자열로 잘못 반환",  # LLM 오류
        "main_theme": "주제",
        "emotional_journey": {"opening": "피로", "development": "인식", "resolution": "안도"},
        "key_messages": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="light")

    assert isinstance(result["user_summary"], dict)
    assert "keywords" in result["user_summary"]
    assert isinstance(result["user_summary"]["keywords"], list)


def test_validate_and_correct_validates_emotional_journey_type(
    agent: ContentAnalyzerAgent,
) -> None:
    """emotional_journey가 dict 아닐 때 4-키 빈 구조로 보정한다 (CA-1, CA-3)."""
    analysis = {
        "user_summary": {}, "main_theme": "주제",
        "emotional_journey": "문자열로 잘못 반환",  # LLM 오류
        "key_messages": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="light")

    ej = result["emotional_journey"]
    assert isinstance(ej, dict)
    assert set(ej.keys()) == {"opening", "development", "climax", "closing"}


def test_validate_and_correct_ensures_confidence_is_float(
    agent: ContentAnalyzerAgent,
) -> None:
    """confidence 필드가 항상 0.0~1.0 float으로 보정된다 (CA-3)."""
    analysis_str = {
        "main_theme": "주제", "user_summary": {}, "emotional_journey": {},
        "key_messages": [], "confidence": "0.9",  # 문자열
    }
    result_str = agent._validate_and_correct(analysis_str, depth_level="light")
    assert isinstance(result_str["confidence"], float)
    assert 0.0 <= result_str["confidence"] <= 1.0

    analysis_missing = {
        "main_theme": "주제", "user_summary": {}, "emotional_journey": {},
        "key_messages": [],  # confidence 없음
    }
    result_missing = agent._validate_and_correct(analysis_missing, depth_level="light")
    assert isinstance(result_missing["confidence"], float)


def test_validate_and_correct_limits_key_messages_to_five(
    agent: ContentAnalyzerAgent,
) -> None:
    """key_messages는 최대 5개 제한, dict 타입이면 빈 리스트 반환 (CA-1)."""
    analysis_over = {
        "user_summary": {}, "main_theme": "주제",
        "emotional_journey": {}, "key_messages": ["a", "b", "c", "d", "e", "f"],
    }
    result = agent._validate_and_correct(analysis_over, depth_level="light")
    assert len(result["key_messages"]) <= 5

    analysis_bad = {
        "user_summary": {}, "main_theme": "주제",
        "emotional_journey": {}, "key_messages": {"잘못된": "타입"},
    }
    result_bad = agent._validate_and_correct(analysis_bad, depth_level="light")
    assert result_bad["key_messages"] == []
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_content_analyzer.py::test_validate_and_correct_excludes_unexpected_fields tests/agents/podcast/test_content_analyzer.py::test_validate_and_correct_enforces_min_sub_themes -v -m "not live"
```

Expected: **FAIL**

- [ ] **Step 3: `_validate_and_correct` 재구성 + `_build_db_payload` 추가**

`src/agents/podcast/content_analyzer.py` lines 195–243 교체:

```python
    def _validate_and_correct(self, analysis: dict[str, Any], depth_level: str) -> dict[str, Any]:
        """LLM 분석 결과를 v2.2.0 화이트리스트 기준으로 검증·추출한다.

        반환값은 AgentState용 9개 필드 (v2.2.0 = 백엔드 API 계약 일치).
        DB 저장 시에는 _build_db_payload()로 trace_id를 추가한다.
        """
        # 1. main_theme — 100자 초과 시 잘라냄
        main_theme = str(analysis.get("main_theme", analysis.get("topic", "")))
        if len(main_theme) > self.max_theme_length:
            main_theme = main_theme[: self.max_theme_length] + "..."

        # 2. user_summary — {keywords: list[:5], summary: str} 구조 강제
        raw_summary = analysis.get("user_summary", {})
        if not isinstance(raw_summary, dict):
            raw_summary = {}
        user_summary = {
            "keywords": raw_summary.get("keywords", [])[:5]
            if isinstance(raw_summary.get("keywords"), list)
            else [],
            "summary": str(raw_summary.get("summary", "")),
        }

        # 3. emotional_journey — 4-키 구조 강제 (opening/development/climax/closing)
        raw_journey = analysis.get("emotional_journey", {})
        if not isinstance(raw_journey, dict):
            raw_journey = {}
        emotional_journey = {
            "opening":     str(raw_journey.get("opening", "")),
            "development": str(raw_journey.get("development", "")),
            "climax":      str(raw_journey.get("climax", "")),
            "closing":     str(raw_journey.get("closing", "")),
        }

        # 4. key_messages — list[:5] 제한, 비-list 시 빈 리스트
        raw_messages = analysis.get("key_messages", [])
        key_messages = raw_messages[:5] if isinstance(raw_messages, list) else []

        # 5. sub_themes — list[3-5] 강제. min 미달 시 main_theme 기반 fallback
        raw_themes = analysis.get("sub_themes", analysis.get("themes", []))
        if not isinstance(raw_themes, list):
            raw_themes = []
        raw_themes = raw_themes[: self.max_sub_themes]
        if len(raw_themes) < self.min_sub_themes:
            self.logger.warning(
                "[ContentAnalyzer] sub_themes 개수 미달 (%d < %d) — 기본값으로 보정",
                len(raw_themes), self.min_sub_themes,
            )
            while len(raw_themes) < self.min_sub_themes:
                raw_themes.append(main_theme)

        # 6. target_duration — clamp(3-5). CA v2.2.0부터 LLM이 직접 생성
        target_duration = analysis.get("target_duration")
        if target_duration is not None:
            try:
                target_duration = int(target_duration)
            except (ValueError, TypeError):
                target_duration = 4
            target_duration = clamp(target_duration, self.min_duration, self.max_duration)
        else:
            target_duration = 4

        # 7. narrative_structure — 유효값 검증 + fallback
        narrative = analysis.get("narrative_structure", analysis.get("suggested_structure", ""))
        if narrative not in VALID_NARRATIVE_STRUCTURES:
            narrative = "reflection"

        # 8. confidence — 0.0~1.0 범위 강제
        raw_confidence = analysis.get("confidence")
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else 0.5
        except (ValueError, TypeError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        # 9. depth_level — 코드가 직접 결정
        return {
            "user_summary":       user_summary,
            "main_theme":         main_theme,
            "emotional_journey":  emotional_journey,
            "key_messages":       key_messages,
            "depth_level":        depth_level,
            "sub_themes":         raw_themes,
            "target_duration":    target_duration,
            "narrative_structure": narrative,
            "confidence":         confidence,
        }

    def _build_db_payload(
        self, validated: dict[str, Any], trace_id: str = ""
    ) -> dict[str, Any]:
        """content_analyses DB 저장용 페이로드. 9개 필드 + trace_id."""
        return {
            **validated,
            "trace_id": trace_id,
        }
```

save 호출 부분 (`content_analyzer.py:115–121` 근처) 수정:

```python
        validated_analysis = self._validate_and_correct(llm_analysis, depth_level)

        # DB 저장: 9개 필드 + trace_id
        trace_id = str(state.get("trace_id", ""))
        db_payload = self._build_db_payload(validated_analysis, trace_id=trace_id)
        await publisher.publish(
            resource=RESOURCE_CONTENT_ANALYSIS,
            data=db_payload,
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
        )

        # AgentState: 9개 필드
        return {"content_analysis": validated_analysis}
```

- [ ] **Step 4: 기존 테스트 업데이트**

`test_content_analyzer.py`에서 `emotional_journey` 구조 검증 및 신규 필드 검증 추가:
```python
# emotional_journey — resolution → climax/closing 변경:
# 기존: assert "resolution" in result["content_analysis"]["emotional_journey"]
# 수정: assert "climax" in result["content_analysis"]["emotional_journey"]
#        assert "closing" in result["content_analysis"]["emotional_journey"]
#        assert "resolution" not in result["content_analysis"]["emotional_journey"]

# v2.2.0 신규 필드 검증:
assert "confidence" in result["content_analysis"]
assert isinstance(result["content_analysis"]["confidence"], float)
assert "target_duration" in result["content_analysis"]
assert "narrative_structure" in result["content_analysis"]

# sub_themes min 보장:
assert "sub_themes" in result["content_analysis"]
assert len(result["content_analysis"]["sub_themes"]) >= agent.min_sub_themes
```

`mock_llm_response` fixture를 v2.2.0 형식으로 교체:
```python
@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """LLM v2.2.0이 반환할 모의 분석 결과 (9개 필드)."""
    return {
        "main_theme": "스트레스 해소와 마음 돌봄",
        "user_summary": {
            "keywords": ["스트레스", "피로"],
            "summary": "스트레스와 피로를 호소하는 사용자",
        },
        "emotional_journey": {
            "opening":     "피로와 무기력",
            "development": "원인 인식",
            "climax":      "대처 전략 발견",
            "closing":     "희망과 안도",
        },
        "key_messages": ["나를 돌보는 것은 이기적이지 않다", "작은 변화가 큰 차이를 만든다"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],
        "target_duration": 5,
        "narrative_structure": "reflection",
        "confidence": 0.85,
    }
```

- [ ] **Step 5: 전체 CA 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_content_analyzer.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 6: 건너뜀** — CA v2.2.0 프롬프트 + settings.yaml 핀닝 이미 완료 (commit `85f71f7`).

- [ ] **Step 7: DB 저장 변경 사항 확인**

```bash
grep -n "publisher\|publish\|_build_db_payload" src/agents/podcast/content_analyzer.py
```

- [ ] **Step 8: 커밋**

```bash
git add src/agents/podcast/content_analyzer.py tests/agents/podcast/test_content_analyzer.py
git commit -m "fix(content_analyzer): CA-1/CA-2/CA-3 — v2.2.0 whitelist 9개 필드, 4-키 emotional_journey, confidence 신규"
```

---

## Task 4: SG-1 + SG-2 — Script Generator 수정 [TIER 2]

**담당 브랜치:** `feature/analysis-*`

> **2026-04-13 상태:**
> - `closing` 1차 키로 변경 완료. 그러나 `resolution` 폴백 체인 잔존 (line 227-231).
> - 독스트링 `_generate_title` (line 219)에 `resolution` 참조 남아있음.
> - `state.get("emotional_journey", {})` (line 58) — AgentState 미정의 top-level 키 참조 잔존.

**문제:**
- **SG-1**: `main_theme` 없을 때 `"Mental Health"` 하드코딩 기본값 사용.
- **SG-2**: 실패 시 `{"script_draft": {}, "error": str(e)}` — `"error"` 키는 AgentState에 없음.
- **잔존**: `resolution` 폴백 체인, 독스트링 `resolution` 참조.

**데이터 흐름:**
```
CA → state["content_analysis"]["main_theme", "sub_themes"] → SG
SG → state["script_draft"] → BV → SP
```

**DB 저장 영향:** SG는 publisher 미호출 → 협의 불필요 ✅

**선행 조건:** Task 3 완료 후 실행 (emotional_journey 4-키 보장 필요)

**Files:**
- Modify: `src/agents/podcast/script_generator.py:51–56, 193, 208-212`
- Modify: `tests/agents/podcast/test_script_generator.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_script_generator_source_has_no_mental_health_hardcode() -> None:
    """ScriptGeneratorAgent 소스에 'Mental Health' 하드코딩 없다 (SG-1)."""
    import inspect
    from src.agents.podcast.script_generator import ScriptGeneratorAgent

    source = inspect.getsource(ScriptGeneratorAgent)
    assert "Mental Health" not in source, "SG-1: Mental Health 하드코딩 발견됨"


@pytest.mark.asyncio
async def test_script_generator_returns_error_not_top_level_key_on_failure() -> None:
    """실패 시 top-level 'error' 키 대신 script_draft 내부에 _error 포함 (SG-2)."""
    from src.agents.podcast.script_generator import ScriptGeneratorAgent
    from src.models.agent_state import AgentState

    agent = ScriptGeneratorAgent()
    state = AgentState(
        user_input="오늘 하루", user_id="u", session_id="s", mode="podcast",
        content_analysis={"main_theme": ""},  # 빈 main_theme → 조기 에러 반환
    )

    result = await agent.process(state)

    assert "error" not in result, "top-level 'error' 키는 AgentState 미정의"
    assert "script_draft" in result
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_script_generator.py::test_script_generator_source_has_no_mental_health_hardcode -v -m "not live"
```

Expected: **FAIL** — `"Mental Health"` 소스에 존재

- [ ] **Step 3: script_generator.py 수정**

line 51–56 — `main_theme` 기본값 수정:
```python
        main_theme: str = str(content_analysis.get("main_theme", ""))
        if not main_theme:
            self.logger.error(
                "[ScriptGenerator] main_theme 누락 — content_analysis 유효성: %s",
                bool(content_analysis),
            )
            return {"script_draft": {"_error": "main_theme_missing", "segments": []}}
```

line 208-212 — `_generate_title()` `resolution` → `closing` 수정 (CA-3 연쇄):
```python
# Before
start_emotion = emotional_journey.get(
    "opening", emotional_journey.get("start_emotion", "None")
)
resolution_emotion = emotional_journey.get(
    "resolution", emotional_journey.get("resolution_emotion", "None")
)

# After
start_emotion = emotional_journey.get("opening", "")
resolution_emotion = emotional_journey.get(
    "closing", emotional_journey.get("resolution_emotion", "")
)
```

line 193 — except 블록 반환 수정 (SG-2):
```python
        except Exception as e:
            self.logger.error("[ScriptGenerator] 스크립트 생성 실패: %s", e)
            return {"script_draft": {"_error": str(e), "segments": []}}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_script_generator.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/script_generator.py tests/agents/podcast/test_script_generator.py
git commit -m "fix(script_generator): SG-1/SG-2 — Mental Health 제거, resolution→closing, error 키 정리"
```

---

## Task 5: VI-1 + VI-2 — Visualization Agent 출력 검증 [TIER 2]

**담당 브랜치:** `feature/reasoning-*`

**문제:**
- **VI-1**: `style_type`, `interpretation`을 LLM에서 타입 검증 없이 직접 저장. `None` 통과.
- **VI-2**: 에러 경로에 `image_url`, `style_type`, `interpretation` 키 없음.

**데이터 흐름:**
```
VI → state["visual_data"] → podcasts.py:_save_core_data() → visualization_meta DB
```

**DB 저장 영향:** NOT NULL 제약(`cdn_url`, `interpretation_text`) 위반 위험 줄임 → 협의 불필요 ✅

**Files:**
- Modify: `src/agents/podcast/visualization.py:62, 70–81`
- Modify: `tests/agents/podcast/test_visualization_agent.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_visual_data_style_type_is_str_not_none() -> None:
    """LLM이 style_type=None 반환 시 빈 문자열 기본값 적용 (VI-1)."""
    from src.agents.podcast.visualization import VisualizationAgent
    from src.models.agent_state import AgentState

    agent = VisualizationAgent()
    llm_response = {"style_type": None, "interpretation": None, "color_palette": []}
    state = AgentState(
        user_input="오늘 하루", user_id="u", session_id="s", mode="podcast",
        emotion_vectors={"primary_emotion": "calm"},
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        with patch.object(
            agent, "_generate_image", new_callable=AsyncMock, return_value="http://img.test"
        ):
            result = await agent.process(state)

    vd = result.get("visual_data", {})
    assert isinstance(vd.get("style_type"), str), f"style_type 타입 오류: {vd.get('style_type')!r}"
    assert isinstance(vd.get("interpretation"), str)


@pytest.mark.asyncio
async def test_error_path_visual_data_has_same_keys_as_normal_path() -> None:
    """에러 반환도 정상 반환과 동일한 키 구조를 가진다 (VI-2)."""
    from src.agents.podcast.visualization import VisualizationAgent
    from src.models.agent_state import AgentState

    agent = VisualizationAgent()
    state = AgentState(user_input="오늘 하루", user_id="u", session_id="s", mode="podcast")

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    vd = result.get("visual_data", {})
    for key in ["image_url", "style_type", "interpretation"]:
        assert key in vd, f"에러 경로 visual_data에 '{key}' 키 없음"
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_visualization_agent.py::test_visual_data_style_type_is_str_not_none -v -m "not live"
```

Expected: **FAIL** — `style_type: None` 통과

- [ ] **Step 3: visualization.py 수정**

정상 경로 LLM 필드 추출 (line 70–81):
```python
        "style_type":     str(planning.get("style_type") or "abstract"),
        "interpretation": str(planning.get("interpretation") or ""),
```

에러 경로 반환 (line 62 부근):
```python
        return {
            "visual_data": {
                "style_type":      "abstract",
                "interpretation":  "",
                "image_url":       None,
                "color_palette":   [],
                "error":           str(e),
            }
        }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_visualization_agent.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/visualization.py tests/agents/podcast/test_visualization_agent.py
git commit -m "fix(visualization): VI-1/VI-2 — style_type/interpretation str 보장, 에러 경로 키 구조 일치"
```

---

## Task 6: BV-1 + BV-2 — Batch Validator 명시 필드 추출 [TIER 3]

**담당 브랜치:** `feature/validation-*`

**문제:**
- **BV-1**: `return {"validation_result": validation}` — LLM 응답 전체 저장. `overall_score` 미반환 시 항상 0.0.
- **BV-2**: `script_draft` 비어있을 때 조기 반환에 `action` 필드 없음 → SG 재시도 시 `validation_result["action"]["revision_instructions"]` KeyError.

**수정:** `_build_validation_result()` 헬퍼로 명시 추출. 조기 반환에도 `action` 포함.

**데이터 흐름:**
```
BV → state["validation_result"] → route_after_tier3(verdict), SG 재시도(action), _save_core_data(overall_score)
```

**DB 저장 영향:** `podcast_episodes.validation_score FLOAT` — 명시 float 변환 → 협의 불필요 ✅

**Files:**
- Modify: `src/agents/podcast/batch_validator.py:83–89, 113–130`
- Modify: `tests/agents/podcast/test_batch_validator.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
@pytest.mark.asyncio
async def test_validation_result_excludes_llm_extra_fields() -> None:
    """validation_result에 LLM 임의 필드가 포함되지 않는다 (BV-1)."""
    from src.agents.podcast.batch_validator import BatchValidatorAgent
    from src.models.agent_state import AgentState

    agent = BatchValidatorAgent()
    llm_response = {
        "overall_score": 0.85,
        "action": {"decision": "approve", "revision_instructions": "", "priority_fixes": []},
        "extra_llm_field": "유입 금지",
        "debug_info": "무시 대상",
    }
    state = AgentState(
        user_input="테스트", user_id="u", session_id="s", mode="podcast",
        script_draft={"segments": [{"script_text": "내용"}]},
        iteration_count=0,
    )

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response
    ):
        result = await agent.process(state)

    vr = result["validation_result"]
    assert "extra_llm_field" not in vr
    assert "debug_info" not in vr
    assert "verdict" in vr
    assert "overall_score" in vr
    assert "action" in vr


@pytest.mark.asyncio
async def test_early_return_has_action_field_like_normal_return() -> None:
    """빈 script_draft 조기 반환에도 action 필드 있다 (BV-2)."""
    from src.agents.podcast.batch_validator import BatchValidatorAgent
    from src.models.agent_state import AgentState

    agent = BatchValidatorAgent()
    state = AgentState(
        user_input="테스트", user_id="u", session_id="s", mode="podcast",
        script_draft={},   # 비어있음 → 조기 반환
        iteration_count=0,
    )

    result = await agent.process(state)
    vr = result["validation_result"]

    assert "action" in vr, "BV-2: 조기 반환에 action 없음"
    assert "verdict" in vr
    assert "overall_score" in vr
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_batch_validator.py::test_validation_result_excludes_llm_extra_fields -v -m "not live"
```

Expected: **FAIL** — `extra_llm_field`, `debug_info` 포함됨

- [ ] **Step 3: BatchValidator 수정**

헬퍼 메서드 `_build_validation_result` 추가:
```python
    def _build_validation_result(self, validation: dict[str, Any]) -> dict[str, Any]:
        """LLM 응답에서 명시 필드만 추출하고 verdict를 설정한다."""
        action = validation.get("action", {})
        if not isinstance(action, dict):
            action = {}
        decision = action.get("decision", "revise")
        verdict_map = {"approve": "PASS", "revise": "FAIL", "escalate": "CRITICAL_FAIL"}

        result: dict[str, Any] = {
            "verdict":       verdict_map.get(decision, "FAIL"),
            "overall_score": float(validation.get("overall_score", 0.0)),
            "action": {
                "decision":              decision,
                "revision_instructions": str(action.get("revision_instructions", "")),
                "priority_fixes":        action.get("priority_fixes", [])
                                         if isinstance(action.get("priority_fixes"), list)
                                         else [],
            },
        }
        if isinstance(validation.get("scores"), dict):
            result["scores"] = validation["scores"]
        if isinstance(validation.get("critical_issues"), list):
            result["critical_issues"] = validation["critical_issues"]
        return result
```

조기 반환 (line 83–89) 수정 (BV-2):
```python
            return {
                "validation_result": {
                    "verdict":       "FAIL",
                    "overall_score": 0.0,
                    "action": {
                        "decision":              "revise",
                        "revision_instructions": f"Empty script_draft (iteration={iteration_count})",
                        "priority_fixes":        [],
                    },
                },
            }
```

정상 반환 경로를 모두 `_build_validation_result(validation)` 사용으로 교체.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_batch_validator.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/batch_validator.py tests/agents/podcast/test_batch_validator.py
git commit -m "fix(batch_validator): BV-1/BV-2 — 명시 필드 추출, 조기 반환 action 필드 추가"
```

---

## Task 7: 횡단 이슈 — type 상수 불일치 + SSE 키 버그 [횡단]

**담당 브랜치:** 해당 파일 담당 개발자

> 2026-04-13 병렬 분석에서 신규 발견. Task 1~6과 독립 처리 가능. 심각도 낮음.

### ~~7-A: trace_id 전달 불균형~~ — 수정 불필요

> `publisher.publish()`에 `trace_id` 옵셔널 파라미터가 이미 존재하지만 호출부에서 미전달.
> 백엔드 API 테스트 200 OK — trace_id 없이도 저장 성공. 기능 장애 아닌 추적성 누락.
> `content_analyses`의 trace_id는 Task 3 `_build_db_payload()`에서 처리.
> **나머지(emotion_logs, mind-frequencies, podcast_episodes)는 현상 유지.**

### 7-B: publisher type 필드 상수 불일치

**현황:**

| 에이전트 | publisher 호출 | SaveRequest.type 전송값 | TYPE_* 상수 (미사용) |
|---------|---------------|----------------------|-------------------|
| Content Analyzer | `resource=RESOURCE_CONTENT_ANALYSIS` | `"content_analyses"` (복수) | `TYPE_CONTENT_ANALYSIS` = `"content_analysis"` (단수) |
| Emotion Agent | `resource=RESOURCE_EMOTION_LOG` | `"emotion_logs"` (복수) | `TYPE_EMOTION_LOG` = `"emotion_log"` (단수) |

`publisher.publish()`에서 `data_type` 미전달 시 `resource` 값이 `SaveRequest.type`에 대체 사용됨.
`TYPE_*` 상수가 정의만 되고 어디에서도 사용되지 않는 상태.
백엔드 API 테스트 200 OK이므로 기능 장애는 아니지만, 상수 정의와 실제 전송값 통일 필요.

**수정:**
- Content Analyzer: `publisher.publish()` 호출 시 `data_type=TYPE_CONTENT_ANALYSIS` 명시 전달 (Task 3 Step 3에서 함께 처리)
- Emotion Agent: `publisher.publish()` 호출 시 `data_type=TYPE_EMOTION_LOG` 명시 전달

**Files:**
- `src/agents/podcast/content_analyzer.py` (Task 3 Step 3에서 처리)
- `src/agents/podcast/emotion.py` (line 138)

- [ ] **Step 1: Emotion Agent publish 호출에 data_type 추가**

```python
# emotion.py line 138 부근
# Before
await publisher.publish(
    resource=RESOURCE_EMOTION_LOG,
    data=emotion_data,
    user_id=state.get("user_id", ""),
    session_id=state.get("session_id", ""),
)

# After
from src.api.backend_resources import TYPE_EMOTION_LOG
await publisher.publish(
    resource=RESOURCE_EMOTION_LOG,
    data=emotion_data,
    user_id=state.get("user_id", ""),
    session_id=state.get("session_id", ""),
    data_type=TYPE_EMOTION_LOG,
)
```

- [ ] **Step 2: Content Analyzer는 Task 3 Step 3에서 처리** — `_build_db_payload()` 적용 시 `data_type=TYPE_CONTENT_ANALYSIS` 함께 추가.

- [ ] **Step 3: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_emotion.py tests/agents/podcast/test_content_analyzer.py -v -m "not live"
```

- [ ] **Step 4: 커밋**

```bash
git add src/agents/podcast/emotion.py
git commit -m "fix(emotion): 7-B — publisher data_type=TYPE_EMOTION_LOG 명시 전달"
```

### 7-C: SSE 스트리밍 reasoning_depth 키 불일치

**현황:**

| 경로 | 코드 | 키 | 정상 |
|------|------|---|------|
| 일반 응답 (`podcasts.py:336`) | `reasoning_result.get("reasoning_depth", "standard")` | ✅ 올바름 | — |
| SSE 스트리밍 (`podcasts.py:477`) | `reasoning_result.get("depth_level", "standard")` | ❌ 잘못된 키 | 항상 `"standard"` 반환 |

`podcast_reasoning.py:229`에서 `reasoning["reasoning_depth"] = depth`로 설정.
SSE에서 `"depth_level"` 참조는 Content Analyzer의 출력 필드와 키 혼동.
프론트엔드에 잘못된 추론 깊이가 표시됨.

**수정:** `podcasts.py:477` — `"depth_level"` → `"reasoning_depth"`

**Files:**
- Modify: `src/api/routes/podcasts.py:477`

- [ ] **Step 1: 수정**

```python
# podcasts.py line 477
# Before
depth = reasoning_result.get("depth_level", "standard")

# After
depth = reasoning_result.get("reasoning_depth", "standard")
```

- [ ] **Step 2: SSE 테스트 통과 확인**

```bash
pytest tests/api/test_sse_streaming.py -v -m "not live"
```

- [ ] **Step 3: 커밋**

```bash
git add src/api/routes/podcasts.py
git commit -m "fix(sse): 7-C — reasoning_result 키 depth_level→reasoning_depth 수정"
```

---

## 부록: AWS 배포 환경

> 2026-04-08 점검 결과. 구현 시 이 환경 기준.

| 서비스 | 리전 | 비고 |
|--------|------|------|
| AWS Bedrock (LLM) | `ap-northeast-2` | 동시 호출 상한 10, 재시도 3회 |
| AWS Bedrock (이미지) | `us-east-1` | Titan 이미지 서울 미지원 → 크로스 리전 |
| S3 | `ap-northeast-2` | `mindlog-images` 버킷 |
| Pinecone | SaaS | 인덱스: `expert-knowledge`, `mem-podcast-episode` |
| Neo4j | AI 서버 동일 호스트 | `bolt://localhost:7687` |

**Bedrock 모델 리전:** Haiku In-Region, Sonnet 3.7 APAC CRIS (`apac.anthropic.*`), Opus → Sonnet 4 대체.

**인증:** boto3 기본 체인 (환경변수 → credentials → EC2 IAM Role).

**구현 주의:**
1. LLM용(`ap-northeast-2`)과 이미지용(`us-east-1`) boto3 클라이언트 별도 초기화
2. `settings.yaml`의 `bedrock_models` 섹션 CRIS 모델 ID 임의 변경 금지
3. Visualization Agent만 S3 직접 업로드, 나머지는 백엔드 API 경유

---

*v5 (2026-04-08): 초기 작성*
*v6 (2026-04-08): IC-1 완료 확인, DB 아키텍처 검증, AWS 섹션 추가*
*v7 (2026-04-09): 백엔드 API 계약 확정, CA-3 추가, schemas.py Task 추가, 연쇄 영향 맵*
*v8 (2026-04-13): API 전수 테스트 반영, SP/schemas 완료, graph_analyses 삭제, SG cascade 부분수정, Task 11 추가*
*v9 (2026-04-13): 문서 전면 정리 — 완료/미완료 분리, Task 재넘버링(7건), 중복 제거, sub_themes CA min 보장으로 통합*

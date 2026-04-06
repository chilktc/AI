# Phase 1: 개별 방어 코드 수정 (Changes 1-7)

← [인덱스로 돌아가기](./pipeline-robustness-index.md) | [Phase 2 →](./pipeline-robustness-part2.md)

**PR 브랜치:** `feature/reasoning-pipeline-robustness`
**Base:** `develop` (PR#59 머지 후)
**리뷰:** 3인 전원 (workflow.py Protected File 포함)

---

## Change 1: workflow.py — `__call__()` 우회 수정 (3곳)

**근거:** 3개 노드가 `agent.process(state)` 직접 호출 → LangSmith 트레이싱, A/B 테스트 ContextVar, LLM 카운터 모두 비활성화됨.

```python
# workflow.py:118  intent_classifier_node
# workflow.py:127  script_generator_node
# workflow.py:185  script_personalizer_node

# 변경 전:
    return await agent.process(state)
# 변경 후:
    return await agent(state)
```

**후속 조치:**
- `settings.yaml` `prompts.ab_tests.intent_classifier.enabled: false` 여부 확인
- 변경 후 LangSmith에서 3개 에이전트 트레이스 신규 생성 확인

**테스트:** `test_intent_classifier_node_uses_call_not_process` — `mock_agent.assert_awaited_once_with(state)` + `mock_agent.process.assert_not_called()`

- [ ] Step 1: 3곳 수정
- [ ] Step 2: A/B 테스트 설정 확인
- [ ] Step 3: `pytest tests/graph/ -v`

> **Protected File — 3인 합의 필수**

---

## Change 1-B: workflow.py — TIER 0 타임아웃 래퍼

**근거:** `_TIER0_TIMEOUT`(20초)이 로드되지만 전혀 사용되지 않음. Intent Classifier 무응답 시 파이프라인 무한 대기.

```python
# build_unified_graph() 내:

# 변경 전:
graph.add_node("intent_classifier", intent_classifier_node)

# 변경 후:
async def _intent_classifier_with_timeout(s: AgentState) -> dict[str, Any]:
    return await _with_timeout(intent_classifier_node, s, _TIER0_TIMEOUT, "intent_classifier")
graph.add_node("intent_classifier", _intent_classifier_with_timeout)
```

- [ ] Step 1: `build_unified_graph()` 수정
- [ ] Step 2: 타임아웃 테스트 추가
- [ ] Step 3: `pytest tests/graph/ -v`

> **Protected File — Change 1과 동일 PR**

---

## Change 2: podcast_reasoning.py — user_input 안전 접근

**근거:** `state["user_input"]` — KeyError 위험 (독립 테스트, 미래 워크플로우 변경 시).

```python
# 변경 전 (라인 81):
user_input = state["user_input"]

# 변경 후:
user_input = state.get("user_input", "")
if not user_input:
    self.logger.error("[PodcastReasoning] user_input 없음")
    return {
        "reasoning_result": {
            "episode_structure": [], "key_themes": [], "emotional_arc": {},
            "confidence": 0.0, "reasoning_depth": "minimal",
            "error": "user_input_missing",
        }
    }
```

**테스트:** `test_missing_or_empty_user_input_returns_fallback` — `user_input=""`/키 없음 → `error == "user_input_missing"` + `confidence == 0.0`

- [ ] Step 1: `podcast_reasoning.py:81` 수정
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_podcast_reasoning.py -v`

---

## Change 2-B: content_analyzer.py — user_input 안전 접근

Change 2와 동일 패턴. `content_analyzer.py:81`.

```python
# 변경 후:
user_input = state.get("user_input", "")
if not user_input:
    self.logger.error("[ContentAnalyzer] user_input 없음")
    return {
        "content_analysis": {
            "main_theme": "", "sub_themes": [], "emotional_journey": {},
            "depth_level": "light", "error": "user_input_missing",
        }
    }
```

- [ ] Step 1: `content_analyzer.py:81` 수정
- [ ] Step 2: 빈 user_input 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_content_analyzer.py -v`

---

## Change 3: script_generator.py — content_analysis fallback 수정

**근거:** `state.get("content_analysis", state)` — `state` 전체를 fallback으로 사용. `main_theme`이 항상 `"Mental Health"` 기본값으로 고정됨.

```python
# 변경 전 (라인 48-50):
content_analysis = cast(dict[str, Any], state.get("content_analysis", state))
# state 최상단에 병합됐을 수도 있고 dict 형태일 수도 있음

# 변경 후:
content_analysis = cast(dict[str, Any], state.get("content_analysis", {}))
if not content_analysis:
    self.logger.warning("[ScriptGenerator] content_analysis 없음 — 기본값으로 생성")
```

**테스트:** `test_missing_content_analysis_uses_empty_dict_not_state`

- [ ] Step 1: `script_generator.py:48-50` fallback `state` → `{}` 교체
- [ ] Step 2: `grep -r "state\.get.*state)" src/agents/` — 동일 패턴 검색
- [ ] Step 3: 테스트 추가
- [ ] Step 4: `pytest tests/agents/podcast/test_script_generator.py -v`

---

## Change 4: batch_validator.py — call_llm_json() try/except

**근거:** `call_llm_json()` 실패 시 TIER 3 크래시 → 파이프라인 중단. 다른 에이전트와 달리 유일하게 try/except 없음.

**Fallback 결정:** `FAIL` 반환 (재시도 1회 허용, LLM 일시 오류 대응). 재시도 후에도 실패하면 `forced_pass`.

```python
# 변경 전 (라인 84-87):
validation = await self.call_llm_json(...)

# 변경 후:
try:
    validation = await self.call_llm_json(...)
except Exception as e:
    self.logger.error("[BatchValidator] LLM 호출 실패 — FAIL 처리: %s", e)
    return {
        "validation_result": {
            "verdict": "FAIL", "decision": "revise", "overall_score": 0.0,
            "action": {"decision": "revise"}, "error": "llm_call_failed",
        }
    }
```

**테스트:** `test_llm_call_failure_returns_fail_verdict` — `side_effect=Exception` → `verdict=="FAIL"`, `error=="llm_call_failed"`

- [ ] Step 1: try/except 추가
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_batch_validator.py -v`

---

## Change 4-B: safety.py — call_llm_json() try/except [CRITICAL]

**근거:** Safety Agent는 CRISIS 판정 담당. LLM 실패 시 TIER 1 병렬 4개 작업 전체 크래시.

**Fallback 결정:** `status="safe"` (LLM 실패 시 오탐보다 안정성 우선. Intent Classifier 1차 감지로 부분 보호).

```python
try:
    result = await self.call_llm_json(...)
except Exception as e:
    self.logger.error("[SafetyAgent] LLM 호출 실패 — safe fallback: %s", e)
    result = {
        "risk_level": 0, "risk_score": 0.0, "status": "safe",
        "flags": {}, "required_in_script": [], "error": "llm_call_failed",
    }
```

- [ ] Step 1: `safety.py:45-47` try/except 추가
- [ ] Step 2: LLM 실패 → safe fallback 테스트
- [ ] Step 3: `pytest tests/agents/podcast/test_safety.py -v`

---

## Change 4-C: podcast_reasoning.py — GoT/ToT/CoT try/except

**근거:** 3개 추론 메서드(`_graph_of_thoughts:270`, `_tree_of_thoughts:298`, `_chain_of_thoughts:328`)에 try/except 없음. 이전 HTTP 500 (JSONDecodeError) 사고의 원인.

```python
# 각 메서드 내 call_llm_json() 호출 wrap:
try:
    result = await self.call_llm_json(...)
except Exception as e:
    self.logger.warning("[PodcastReasoning] %s LLM 실패: %s", method_name, e)
    result = {}  # _execute_reasoning_pipeline()에서 .get()으로 안전 접근
```

- [ ] Step 1: 3곳 각각 try/except 추가
- [ ] Step 2: 기존 `test_llm_returns_empty_dict` 커버 확인 + 보완
- [ ] Step 3: `pytest tests/agents/podcast/test_podcast_reasoning.py -v`

---

## Change 5: emotion.py — LLM 실패 fallback 개선

**근거:** fallback이 `user_input` 키워드("불안"/"우울")만 확인. Intent Classifier가 이미 분석한 `detected_entities.emotions`를 무시함. "요즘 힘들다" → `"neutral"` 오판정.

```python
# 변경 전:
primary = "anxiety" if "불안" in text else ("sadness" if "우울" in text else "neutral")

# 변경 후 (1순위: intent 감정, 2순위: 키워드):
detected_emotions = (
    intent.get("detected_entities", {}).get("emotions", [])
    if isinstance(intent.get("detected_entities"), dict) else []
)
primary = detected_emotions[0] if detected_emotions else None
if not primary:
    primary = "anxiety" if "불안" in user_input else ("sadness" if "우울" in user_input else "neutral")
# secondary_emotions도 detected_emotions[1:]로 채움
```

**테스트:** `test_llm_failure_fallback_uses_intent_emotions` — `user_input="요즘 힘들다"` + `intent.detected_entities.emotions=["sadness"]` → `primary_emotion=="sadness"`

- [ ] Step 1: `emotion.py` fallback except 블록 수정
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_emotion_agent.py -v`

---

## Change 6: script_personalizer.py — ValidatedScript 실패 fallback

**근거:** `ValidatedScript(**script_data)` 실패 시 except 블록에서 `validated_script=None` → `_create_fallback_script()` 미호출 → `final_output=""` 반환.

```python
# 변경 전 (라인 88-93):
validated_script = ValidatedScript(**script_data) if script_data else None

# 변경 후:
validated_script: ValidatedScript | None = None
if script_data:
    try:
        validated_script = ValidatedScript(**script_data)
    except Exception as pydantic_err:
        self.logger.warning("[ScriptPersonalizer] Pydantic 실패 — raw fallback: %s", pydantic_err)
        raw_segments = script_data.get("segments", [])
        raw_title = script_data.get("episode_title", "마음 이야기")
        if raw_segments:
            try:
                min_segments = [
                    ScriptSegment(
                        segment_id=seg.get("segment_id", f"seg_{i}"),
                        segment_type=seg.get("segment_type", "body"),
                        duration_minutes=int(seg.get("duration_minutes", 5)),
                        script_text=str(seg.get("script_text", "")),
                        word_count=len(str(seg.get("script_text", "")).split()),
                        emotional_tone=seg.get("emotional_tone", "neutral"),
                        tts_markers=[],
                    )
                    for i, seg in enumerate(raw_segments)
                    if isinstance(seg, dict) and seg.get("script_text")
                ]
                if min_segments:
                    validated_script = ValidatedScript(
                        episode_title=raw_title,
                        total_duration=script_data.get("total_duration", 5),
                        segments=min_segments, key_insights=[], themes=[],
                    )
            except Exception:
                pass
```

**체크리스트:**
- [ ] `script_personalizer.py` 상단 imports에서 `ScriptSegment` import 확인
- [ ] `ValidatedScript` 필수 필드 목록 확인 (`episode_title` 누락 시 ValidationError)

**테스트:**
- `test_empty_script_draft_returns_nonempty_output` — `script_draft={}` → `final_output != ""`
- `test_malformed_script_draft_returns_nonempty_output` — `episode_title` 누락 → `final_output != ""`

- [ ] Step 1: Pydantic try/except 추가
- [ ] Step 2: `ScriptSegment` import 확인
- [ ] Step 3: 테스트 추가
- [ ] Step 4: `pytest tests/agents/podcast/test_script_personalizer.py -v`

---

## Change 7: script_generator.py — FAIL 재시도 시 validation_result 피드백 주입 [신규]

### 근거

**[멀티 서브에이전트 3개 교차 검증 결과 — 2026-04-07]**

Batch Validator는 FAIL 판정 시 `validation_result`에 다음 피드백 필드를 이미 출력한다:

```json
{
  "action": {
    "decision": "revise",
    "revision_instructions": "도입부가 사용자 감정에 공감하는 내용으로 시작해야 합니다",
    "priority_fixes": ["도입부 감정 공감 강화", "세그먼트 3 톤 조정", "결론 구체성 보완"]
  },
  "validation": {
    "issues": [
      {"criterion": "emotional_alignment", "location": "segment 1", "severity": "major",
       "description": "감정 벡터 반영 미흡"}
    ]
  }
}
```

LangGraph state merge로 이 값은 재시도 시 Script Generator의 state에 존재한다.
**그러나 Script Generator의 `process()` 메서드는 `validation_result`를 전혀 읽지 않는다.**

결과: 매 재시도마다 동일 입력으로 동일 품질의 스크립트를 재생성 → FAIL 반복 가능성 높음.

### 수정 대상 (script_generator.py)

`process()` 내 `knowledge_context` 읽기 직후 (라인 111 다음):

```python
# 변경 후: 라인 111 다음에 추가
knowledge_context: dict[str, Any] = cast(dict[str, Any], state.get("knowledge_context", {}))

# [Change 7] FAIL 재시도 시 이전 검증 피드백 주입
iteration_count = state.get("iteration_count", 0)
revision_feedback = ""
if iteration_count > 0:
    prev_action = state.get("validation_result", {}).get("action", {})
    rev_instructions = prev_action.get("revision_instructions") or ""
    priority_fixes = prev_action.get("priority_fixes") or []
    if rev_instructions or priority_fixes:
        fixes_text = "\n".join(f"- {f}" for f in priority_fixes[:3])
        revision_feedback = (
            f"\n[이전 검증 실패 피드백 (재시도 {iteration_count}회차)]\n"
            f"수정 지침: {rev_instructions}\n"
            f"우선 수정 항목:\n{fixes_text}"
        )
        self.logger.info(
            "[ScriptGenerator] 재시도 피드백 주입 (iteration=%d, fixes=%d개)",
            iteration_count, len(priority_fixes),
        )
```

### 피드백 주입 위치

`_generate_segment_script()` 호출 시 `revision_feedback`를 파라미터로 전달하고, 메서드 내 LLM user_message에 append:

```python
# 라인 126-133 수정:
segment_script = await self._generate_segment_script(
    segment=segment,
    episode_title=episode_title,
    main_theme=main_theme,
    emotional_journey=emotional_journey,
    previous_context=prev_context,
    knowledge_context=knowledge_context,
    revision_feedback=revision_feedback,   # [Change 7] 추가
)
```

`_generate_segment_script()` 내 user_message 구성에 `revision_feedback` 추가 (빈 문자열이면 무시):
```python
# user_message 마지막에 조건부 추가:
if revision_feedback:
    user_message += revision_feedback
```

### 후속 조치

- **`prompts/podcast/script_generator.yaml`** 업데이트: system_prompt에 재시도 피드백 처리 지침 추가
  ```
  재시도 회차(iteration_count > 0)에는 [이전 검증 실패 피드백] 섹션이 제공됩니다.
  이 피드백의 수정 지침과 우선 수정 항목을 반드시 반영하여 스크립트를 개선하세요.
  ```
- `_generate_title()` 호출에는 피드백 미적용 (제목 품질에 직접 영향 없음)
- `_extract_insights()` 호출에도 미적용

### 테스트

`tests/agents/podcast/test_script_generator.py` 추가:

```python
@pytest.mark.asyncio
async def test_retry_injects_revision_feedback_into_prompt():
    """iteration_count > 0일 때 validation_result.action.revision_instructions가
    _generate_segment_script에 전달된다."""
    agent = ScriptGeneratorAgent()

    state = AgentState(
        user_input="스트레스 관리",
        user_id="u1", session_id="s1", mode="podcast",
        iteration_count=1,   # 재시도 회차
        validation_result={
            "verdict": "FAIL",
            "action": {
                "decision": "revise",
                "revision_instructions": "도입부 감정 공감 강화 필요",
                "priority_fixes": ["도입부 공감 강화", "톤 조정"],
            }
        },
        reasoning_result={"episode_structure": [{"section": "intro", "duration_ratio": 1.0}]},
        content_analysis={"main_theme": "스트레스", "sub_themes": [], "target_duration": 5},
    )

    with patch.object(agent, "_generate_segment_script", new_callable=AsyncMock) as mock_gen, \
         patch.object(agent, "_generate_title", new_callable=AsyncMock, return_value="테스트 제목"), \
         patch.object(agent, "_extract_insights", new_callable=AsyncMock, return_value=[]):
        mock_gen.return_value = {
            "segment_id": "seg_1", "script_text": "내용", "word_count": 10,
            "duration_minutes": 5, "emotional_tone": "neutral",
        }
        await agent.process(state)

    # revision_feedback이 _generate_segment_script에 전달됐는지 확인
    call_kwargs = mock_gen.call_args.kwargs
    assert "revision_feedback" in call_kwargs
    assert "도입부 감정 공감 강화 필요" in call_kwargs["revision_feedback"]

@pytest.mark.asyncio
async def test_no_revision_feedback_on_first_attempt():
    """iteration_count == 0이면 revision_feedback이 빈 문자열이다."""
    agent = ScriptGeneratorAgent()
    state = AgentState(
        user_input="테스트", user_id="u1", session_id="s1", mode="podcast",
        iteration_count=0,   # 최초 실행
    )

    with patch.object(agent, "_generate_segment_script", new_callable=AsyncMock) as mock_gen, \
         patch.object(agent, "_generate_title", new_callable=AsyncMock, return_value="제목"), \
         patch.object(agent, "_extract_insights", new_callable=AsyncMock, return_value=[]):
        mock_gen.return_value = {"segment_id": "s1", "script_text": "내용", "word_count": 5,
                                 "duration_minutes": 5, "emotional_tone": "neutral"}
        await agent.process(state)

    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("revision_feedback", "") == ""
```

### 구현 절차

- [ ] Step 1: `script_generator.py` `process()` — `iteration_count` + `revision_feedback` 추출 코드 추가 (라인 111 다음)
- [ ] Step 2: `_generate_segment_script()` 시그니처에 `revision_feedback: str = ""` 파라미터 추가
- [ ] Step 3: `_generate_segment_script()` 내 user_message에 revision_feedback 조건부 append
- [ ] Step 4: `prompts/podcast/script_generator.yaml` — system_prompt에 재시도 처리 지침 추가
- [ ] Step 5: 테스트 2개 추가
- [ ] Step 6: `pytest tests/agents/podcast/test_script_generator.py -v`
- [ ] Step 7: `pytest tests/ -v --tb=short` — 전체 회귀 없음

---

## Change 8: visualization.py — call_llm_json() try/except 추가 [신규]

**근거:** `visualization.py:51-54` — `call_llm_json()` 호출에 try/except 없음. LLM 파싱 실패 시 TIER 2 전체 크래시. Change 4 (Batch Validator), Change 4-B (Safety)와 동일 패턴.

**영향:** visualization_node는 script_generator_node와 TIER 2 병렬 실행. 시각화 LLM 실패 시 스크립트도 같이 버려짐.

```python
# 변경 전 (라인 51-54):
planning = await self.call_llm_json(
    system_prompt=self.get_prompt("system_prompt"),
    user_message=context,
)
image_prompt: str = planning.get("image_prompt") or ""

# 변경 후:
try:
    planning = await self.call_llm_json(
        system_prompt=self.get_prompt("system_prompt"),
        user_message=context,
    )
except Exception as e:
    self.logger.error("[Visualization] LLM 호출 실패 — 빈 이미지로 처리: %s", e)
    return {
        "visual_data": {
            "status": "failed",
            "error": "llm_call_failed",
            "image_url": None,
        }
    }
image_prompt: str = planning.get("image_prompt") or ""
```

**테스트:** `test_visualization_llm_failure_returns_failed_status`

- [ ] Step 1: `visualization.py:51-54` try/except 추가
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_visualization.py -v`

---

## Change 9: workflow.py — `_with_timeout()` 타임아웃 마커 + TIER 3 자동 PASS 방지 [신규, CRITICAL]

### 근거

**`_with_timeout()` (라인 87-94) 현재 동작:**
```python
except asyncio.TimeoutError:
    logger.error("[%s] 타임아웃 (%ds)", name, timeout)
    return {}  # ← 빈 dict
```

**빈 dict가 downstream에서 일으키는 숨은 버그:**

TIER 3 (Batch Validator)가 타임아웃 → `_with_timeout()`이 `{}` 반환 → LangGraph가 state에 merge → `validation_result` 필드 없음(이전 값 유지 또는 없음)

`route_after_tier3_podcast()`:
```python
validation = state.get("validation_result", {})
verdict = validation.get("verdict", "PASS")  # ← 기본값 "PASS"
```

→ **Batch Validator가 타임아웃됐는데 자동으로 PASS 처리 → TIER 4 진행 → 검증 없는 스크립트 최종 출력**

### 수정 대상 (workflow.py — 2곳)

**변경 1 — `_with_timeout()` (라인 87-94):**
```python
# 변경 전:
except asyncio.TimeoutError:
    logger.error("[%s] 타임아웃 (%ds)", name, timeout)
    return {}

# 변경 후:
except asyncio.TimeoutError:
    logger.error("[%s] 타임아웃 (%ds) — 타임아웃 마커 반환", name, timeout)
    return {"_timeout": True, "_timeout_node": name}
```

**변경 2 — `route_after_tier3_podcast()` (라인 431 근처, 시작 부분에 추가):**
```python
def route_after_tier3_podcast(state: AgentState) -> str:
    next_step = state.get("next_step", "")
    if next_step == "crisis_response":
        return "crisis_response"

    # [Change 9] 타임아웃 마커 감지 — 재시도 또는 강제 통과
    validation = state.get("validation_result", {})
    if validation.get("_timeout"):
        iteration_count = state.get("iteration_count", 0)
        logger.warning(
            "[BatchValidator] 타임아웃 — FAIL로 처리 (iteration=%d/%d)",
            iteration_count, _MAX_RETRIES,
        )
        if iteration_count < _MAX_RETRIES:
            return "tier2_podcast"
        logger.warning("[BatchValidator] 타임아웃 + 재시도 소진 — 강제 통과")
        return "tier4_podcast"

    # 기존 verdict 처리 로직 이하 동일
    ...
```

**주의:** `_timeout` 마커는 `AgentState`의 `validation_result: dict`에 임시 포함. `AgentState` 스키마 변경 불필요 (dict 내부 키이므로).

### 테스트

```python
@pytest.mark.asyncio
async def test_with_timeout_returns_timeout_marker():
    """_with_timeout 타임아웃 시 {'_timeout': True} 반환."""
    async def slow_node(state):
        await asyncio.sleep(10)
        return {"result": "done"}

    result = await _with_timeout(slow_node, {}, timeout=0.01, name="test")
    assert result.get("_timeout") is True

@pytest.mark.asyncio
async def test_tier3_timeout_triggers_retry_not_pass():
    """Batch Validator 타임아웃 시 자동 PASS가 아닌 재시도."""
    state = {
        "validation_result": {"_timeout": True, "_timeout_node": "batch_validator"},
        "iteration_count": 0,
    }
    route = route_after_tier3_podcast(state)
    assert route == "tier2_podcast"  # PASS가 아닌 재시도
```

### 구현 절차

- [ ] Step 1: `_with_timeout()` 반환값 `{}` → `{"_timeout": True, "_timeout_node": name}` 수정
- [ ] Step 2: `route_after_tier3_podcast()` 시작 부분에 타임아웃 마커 처리 추가
- [ ] Step 3: 테스트 추가
- [ ] Step 4: `pytest tests/graph/ -v`

> **Protected File — Change 1, 1-B와 동일 PR. 3인 합의 필수.**

---

## Settings 조정: max_retries 축소 [신규]

**근거:** 현재 설정에서 최악 파이프라인 누적 시간 계산:

```
max_retries=2 (FAIL):
  TIER 2 (280s) + TIER 3 (100s) + TIER 2 (280s) + TIER 3 (100s) + TIER 2 (280s) + TIER 3 (100s) = 1140s

max_critical_retries=4 (CRITICAL_FAIL):
  최대 5회 TIER 2 실행 = 약 1900s (31분)
```

31분을 기다리는 사용자 경험은 허용 불가.

**`config/settings.yaml` 수정:**

```yaml
# 변경 전:
pipeline:
  max_retries: 2
  max_critical_retries: 4

# 변경 후:
pipeline:
  max_retries: 1        # FAIL 시 1회 재시도 (총 2회 TIER 2 실행)
  max_critical_retries: 2  # CRITICAL_FAIL 시 2회 재시도 (총 3회 TIER 2 실행)
```

**최악 시간 (수정 후):**
- FAIL: 280 + 100 + 280 + 100 = 760s (약 12분)
- CRITICAL_FAIL: 280 + 100 + 280 + 100 + 280 + 100 = 1140s (약 19분)

**참고:** BatchValidatorAgent의 `self.max_retries`도 settings에서 로드되므로 자동 동기화.

- [ ] `config/settings.yaml` `pipeline.max_retries: 1`, `pipeline.max_critical_retries: 2` 수정
- [ ] 변경 후 Batch Validator 재시도 로직 테스트 (`iteration_count` 확인)

---

## v2 부록: max_retries 동기화 확인

- `batch_validator.py`의 `self.max_retries` = `get_agent_config("batch_validator").max_retries` (default 2)
- `workflow.py`의 `_MAX_RETRIES` = `_settings.max_retries`

두 값이 다른 설정 키를 참조하면 BatchValidator가 "강제 통과" 반환했는데 router가 "재시도" 선택하는 모순 발생.

- [ ] `settings.yaml`에서 `pipeline.max_retries`와 `agents.batch_validator.max_retries` 값 비교
- [ ] 불일치 시 `pipeline.max_retries`를 SSOT으로 통일

---

## PR 전략

| 항목 | 내용 |
|------|------|
| 브랜치 | `feature/reasoning-pipeline-robustness` |
| Base | `develop` (PR#59 머지 후) |
| 리뷰어 | 개발자1, 개발자2, 개발자3 (전원 필수) |
| 머지 방식 | Squash 금지 — Change별 커밋 이력 보존 |
| PR 설명 필수 포함 | 각 버그 발생 조건 + fallback 동작 + 모니터링 체크리스트 |

---

*Part 1 — v5 (2026-04-07) | Change 8 (visualization), Change 9 (_with_timeout 타임아웃 마커), Settings 조정 신규 추가. 취약점 재점검 완료.*

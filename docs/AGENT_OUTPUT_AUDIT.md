# 에이전트 출력 감사 보고서 (AGENT_OUTPUT_AUDIT.md)

> **작성일**: 2026-04-08
> **감사 범위**: `src/agents/podcast/` 전체 12개 에이전트
> **감사 목적**: 프롬프트 출력 ↔ 코드 처리 ↔ AgentState 정합성 전수 검토
> **후속 작업**: 이 문서를 기준으로 각 이슈를 우선순위에 따라 수정한다
> **담당**: 개발자별 섹션 5 참고

---

## 목차

1. [발견된 문제 유형](#1-발견된-문제-유형)
2. [이슈 카탈로그 (에이전트별)](#2-이슈-카탈로그-에이전트별)
3. [이슈 전체 요약표](#3-이슈-전체-요약표)
4. [수정 방법 가이드](#4-수정-방법-가이드)
5. [수정 우선순위 및 담당자](#5-수정-우선순위-및-담당자)
6. [검증 체크리스트](#6-검증-체크리스트)

---

## 1. 발견된 문제 유형

### 유형 A — 코드 미검증 통과 필드 (Pass-through)

LLM 응답 dict 전체를 복사(`dict(llm_response)` 또는 직접 반환)한 뒤, 일부 필드만 명시적으로 처리한다. 명시적으로 처리하지 않는 필드는:
- LLM이 출력하면 검증 없이 `content_analysis`/`validation_result` 등에 포함된다 (보안/안정성 리스크)
- LLM이 해당 필드를 출력하지 않으면 조용히 누락된다 (silent data loss)
- 코드만 보면 해당 필드가 존재한다는 것을 알 수 없다 (가독성 문제)

### 유형 B — 레거시 보정 필드 (Stale correction)

프롬프트가 업그레이드되어 LLM이 더 이상 해당 필드를 출력하지 않지만, 코드의 보정 로직이 여전히 기본값으로 채운다. 하위 에이전트는 실제 LLM 분석값이 아닌 하드코딩된 기본값을 받는다.

### 유형 C — AgentState 미정의 반환 키

에이전트가 `src/models/agent_state.py`에 정의되지 않은 키를 반환한다. LangGraph는 이를 무시하지만, 다른 에이전트가 `state.get("해당키")`로 참조하면 항상 `None`을 받는다.

---

## 2. 이슈 카탈로그 (에이전트별)

---

### CA-1 — Content Analyzer: `user_summary` / `key_messages` 미검증 통과 [유형 A]

**심각도**: 🟠 중간
**파일**: `src/agents/podcast/content_analyzer.py`
**프롬프트**: `prompts/podcast/content_analyzer.yaml` (활성 버전: `v2.1.0`)

**문제**:
`_validate_and_correct` 메서드가 `corrected = dict(analysis)` (line 206)로 LLM 응답 전체를 복사한 뒤, `main_theme` · `sub_themes` · `target_duration` · `narrative_structure` · `depth_level` 5개 필드만 명시적으로 처리한다. v2.1.0 프롬프트가 요구하는 `user_summary` · `emotional_journey` · `key_messages`는 처리되지 않고 통과된다.

**현재 코드** (`content_analyzer.py:195–243`):
```python
def _validate_and_correct(self, analysis: dict[str, Any], depth_level: str) -> dict[str, Any]:
    corrected = dict(analysis)          # ← LLM 전체 복사
    # main_theme, sub_themes, target_duration, narrative_structure, depth_level만 처리
    # user_summary, emotional_journey, key_messages는 처리 없이 통과
    return corrected
```

**v2.1.0 프롬프트 요구 필드** (`content_analyzer.yaml:94–111`):
```json
{
  "user_summary":      {"keywords": [...], "summary": "..."},
  "main_theme":        "...",
  "emotional_journey": {"opening": "...", "development": "...", "resolution": "..."},
  "key_messages":      ["...", "...", "..."],
  "depth_level":       "deep"
}
```

**영향**:
- `user_summary`는 프론트엔드에 직접 표시되는 공감 텍스트. 하위 에이전트(Script Generator 등)가 이 값을 참조하지 못하면 사용자 대면 텍스트 개인화 불가
- `key_messages`가 Script Generator에 전달되지 않으면 핵심 메시지 반영 누락 가능

**수정 방법**: 섹션 4-A 참고

---

### CA-2 — Content Analyzer: `sub_themes` / `target_duration` / `narrative_structure` 레거시 보정 [유형 B]

**심각도**: 🔴 높음
**파일**: `src/agents/podcast/content_analyzer.py`

**문제**:
`_validate_and_correct` 내 보정 로직이 `sub_themes`, `target_duration`, `narrative_structure`를 처리한다. 그러나 v2.1.0 프롬프트는 이 3개 필드를 **더 이상 출력하지 않는다** (v1.0.0 → v1.1.0 마이그레이션 시 제거됨). 결과적으로 이 필드들은 항상 기본값으로 채워진다.

**현재 코드** (`content_analyzer.py:214–238`):
```python
# LLM v2.1.0은 sub_themes를 출력하지 않음 → 항상 []
sub_themes = corrected.get("sub_themes", corrected.get("themes", []))
corrected["sub_themes"] = sub_themes  # 항상 []

# LLM v2.1.0은 target_duration을 출력하지 않음 → 항상 4
corrected["target_duration"] = 4     # 기본값 고정

# LLM v2.1.0은 narrative_structure를 출력하지 않음 → 항상 "reflection"
corrected["narrative_structure"] = "reflection"  # 기본값 고정
```

**영향**:
- `Script Generator`가 `content_analysis.get("sub_themes", [])` (script_generator.py:55) 참조 시 항상 `[]` 수신
- Podcast Reasoning이 서사 구조를 담당하는데, Content Analyzer에서 여전히 `narrative_structure`를 내보내어 혼란 유발

**수정 방법**: 섹션 4-B 참고

---

### SG-1 — Script Generator: `"Mental Health"` 하드코딩 폴백 [유형 B]

**심각도**: 🟠 중간
**파일**: `src/agents/podcast/script_generator.py`

**문제**:
`content_analysis`가 없거나 `main_theme`이 누락된 경우 폴백으로 `"Mental Health"` 문자열을 사용한다.

**현재 코드** (`script_generator.py:51–53`):
```python
main_theme: str = str(
    content_analysis.get("main_theme", state.get("main_theme", "Mental Health"))
)
```

**영향**:
- Content Analyzer 실패 또는 TIER 1 오류 시 `"Mental Health"` 주제로 스크립트가 생성됨
- 사용자 입력과 무관한 generic 스크립트가 최종 출력될 수 있음 (silent failure)

**수정 방법**: 섹션 4-C 참고

---

### EM-1 — Episode Memory: `suggested_personalization` stub 하드코딩 [유형 B]

**심각도**: 🔴 높음
**파일**: `src/agents/podcast/episode_memory.py`

**문제**:
`suggested_personalization` 필드가 실제 메모리 검색 결과가 아닌 개발 중 stub 고정값으로 하드코딩되어 있다.

**현재 코드** (`episode_memory.py:55–59`):
```python
payload = {
    "items": items,
    "summary": f"'{query}'와 관련된 과거 기록을 {len(items)}건 찾았습니다.",
    "suggested_personalization": {"topic": "Restoration of Color"},  # ← stub 고정값
    "_meta": {"namespace": "mem_podcast_episode", "engine": "mock_db", "status": "success"},
}
```

**영향**:
- Podcast Reasoning 또는 Script Personalizer가 `memory_results.suggested_personalization`을 참조하면 `{"topic": "Restoration of Color"}`라는 무의미한 값을 받음
- 운영 코드에 개발 stub이 잔존하여 디버깅 혼란 유발

**수정 방법**: 섹션 4-D 참고

---

### KA-1 — Knowledge Agent: `recommended_approaches` AgentState 미정의 [유형 C]

**심각도**: 🟡 낮음
**파일**: `src/agents/podcast/knowledge.py`

**문제**:
`_build_output` 메서드 (knowledge.py:293–299)가 `recommended_approaches` 키를 반환하지만, `AgentState`에 이 필드가 정의되어 있지 않다.

**현재 코드** (`knowledge.py:293–299`):
```python
return {
    "knowledge_results": {
        "documents": enriched_docs,
        "synthesis": synthesis.get("synthesis", ""),
    },
    "recommended_approaches": synthesis.get("recommended_approaches", []),  # ← AgentState 미정의
}
```

**영향**:
- LangGraph는 `AgentState`에 없는 키를 병합 시 무시
- `state.get("recommended_approaches")`로 참조하는 코드는 항상 `None` 반환
- 현재 Script Generator가 이 경로로 참조하는 코드는 없음 (즉각적 영향 없음)

**수정 방법**: 섹션 4-E 참고

---

### BV-1 — Batch Validator: LLM 응답 전체 미검증 반환 [유형 A]

**심각도**: 🟡 낮음
**파일**: `src/agents/podcast/batch_validator.py`

**문제**:
LLM이 반환한 `validation` dict 전체를 `verdict` 필드만 추가한 채 그대로 `validation_result`에 저장한다. LLM이 예상 외 필드를 추가로 반환하거나 필수 필드(`overall_score`, `action`)를 누락해도 탐지되지 않는다.

**현재 코드** (`batch_validator.py:116–130`):
```python
action = validation.get("action", {})
decision = action.get("decision", "revise")
verdict_map = {"approve": "PASS", "revise": "FAIL", "escalate": "CRITICAL_FAIL"}
validation["verdict"] = verdict_map.get(decision, "FAIL")
return {"validation_result": validation}  # ← 전체 미검증 반환
```

**v2.3.0 프롬프트 기대 필드**:
```json
{
  "overall_score": float,
  "action": {"decision": "approve|revise|escalate", "revision_instructions": "...", "priority_fixes": [...]},
  "scores": {...},
  "critical_issues": [...]
}
```

**영향**:
- `overall_score` 누락 시 `validation.get("overall_score", 0)` 폴백이 항상 `0` → 로그상 검증 점수 항상 0으로 표시
- `action.revision_instructions` 누락 시 Script Generator가 재시도 시 개선 방향 없이 재시도

**수정 방법**: 섹션 4-F 참고

---

### EA-1 — Emotion Agent: LLM 실패 시 `emotional_journey_hint` 고정값 [유형 B]

**심각도**: 🟢 낮음 (LLM 실패 시에만 발동)
**파일**: `src/agents/podcast/emotion.py`

**문제**:
LLM 호출 실패 시 폴백 로직에서 `emotional_journey_hint`를 하드코딩된 배열로 설정한다.

**현재 코드** (`emotion.py:120`):
```python
"emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],
```

**영향**:
- LLM 실패 시에만 발동되므로 정상 흐름에서는 영향 없음
- LLM 실패가 반복되는 환경에서는 모든 에피소드가 동일한 감정 여정 힌트를 받음

**수정 방법**: 섹션 4-G 참고

---

### PR-1 — Podcast Reasoning: `recommended_approaches` 조건부 전파 [유형 C]

**심각도**: 🟢 낮음
**파일**: `src/agents/podcast/podcast_reasoning.py`

**문제**:
Knowledge Agent가 반환한 `recommended_approaches`를 Podcast Reasoning이 AgentState에 전파하지 않는다. Knowledge 결과는 `knowledge_results`로만 AgentState에 기록되며, `recommended_approaches`는 로컬 변수로만 사용된다.

**현재 코드** (`podcast_reasoning.py:130–141`):
```python
result: dict[str, Any] = {"reasoning_result": reasoning}
if memory_result:
    result["memory_results"] = memory_result
if knowledge_result:
    result["knowledge_results"] = knowledge_result
# recommended_approaches는 포함되지 않음
return result
```

**영향**: KA-1과 동일 — 현재 하위 에이전트에서 참조하는 코드 없음

---

### SG-2 — Script Generator: 실패 시 `error` 키 AgentState 미정의 [유형 C]

**심각도**: 🟢 무해
**파일**: `src/agents/podcast/script_generator.py`

**문제**:
LLM 실패 시 `{"script_draft": {}, "error": str(e)}`를 반환하지만, `error` 키가 `AgentState`에 없다.

**현재 코드** (`script_generator.py:193`):
```python
return {"script_draft": {}, "error": str(e)}  # "error"는 AgentState 미정의
```

**영향**: LangGraph가 `error` 키를 무시하므로 워크플로우에 영향 없음. 단, 실패 원인을 AgentState에서 추적할 수 없음.

---

### BV-2 — Batch Validator: 조기 반환 시 `reason` 키 AgentState 미정의 [유형 C]

**심각도**: 🟢 무해
**파일**: `src/agents/podcast/batch_validator.py`

**문제**:
`script_draft`가 비어있을 때 조기 반환 dict에 `reason` 키가 포함되지만 AgentState에 없다.

**현재 코드** (`batch_validator.py:83–89`):
```python
return {
    "validation_result": {
        "verdict": "FAIL",
        "reason": "Empty script_draft",  # ← AgentState 미정의, validation_result 내부 키
        "overall_score": 0.0,
    },
}
```

**영향**: `validation_result` 내부 키이므로 LangGraph 레벨에서는 문제없음. 단, Batch Validator의 정상 반환 구조와 다름 (action, decision 필드 누락).

---


## 3. 이슈 전체 요약표

| ID | 에이전트 | 유형 | 심각도 | 핵심 문제 | 담당 |
|----|---------|------|--------|---------|------|
| CA-1 | Content Analyzer | A (pass-through) | 🟠 중간 | `user_summary`, `key_messages` 미검증 통과 | 개발자3 |
| CA-2 | Content Analyzer | B (legacy) | 🔴 높음 | `sub_themes`=`[]`, `target_duration`=`4`, `narrative_structure`=`"reflection"` 고정 | 개발자3 |
| SG-1 | Script Generator | B (legacy) | 🟠 중간 | `"Mental Health"` 하드코딩 폴백 | 개발자1 |
| EM-1 | Episode Memory | B (legacy) | 🔴 높음 | `suggested_personalization`=`{"topic": "Restoration of Color"}` stub | 개발자2 |
| KA-1 | Knowledge Agent | C (undefined key) | 🟡 낮음 | `recommended_approaches` AgentState 미정의 반환 | 개발자1 |
| BV-1 | Batch Validator | A (pass-through) | 🟡 낮음 | LLM 응답 전체 미검증 반환 | 개발자3 |
| EA-1 | Emotion Agent | B (legacy) | 🟢 낮음 | 폴백 시 `emotional_journey_hint` 하드코딩 | 개발자2 |
| PR-1 | Podcast Reasoning | C (undefined key) | 🟢 낮음 | `recommended_approaches` 조건부 미전파 | 개발자3 |
| SG-2 | Script Generator | C (undefined key) | 🟢 무해 | 실패 시 `error` 키 AgentState 미정의 | 개발자1 |
| BV-2 | Batch Validator | C (undefined key) | 🟢 무해 | 조기 반환 시 `reason` 키 AgentState 미정의 | 개발자3 |

---

## 4. 수정 방법 가이드

---

### 4-A: CA-1 수정 — 화이트리스트 재구성

**파일**: `src/agents/podcast/content_analyzer.py`

`_validate_and_correct` 메서드에서 `dict(analysis)` 전체 복사 대신, v2.1.0 프롬프트의 출력 필드를 명시적으로 추출한다.

```python
def _validate_and_correct(self, analysis: dict[str, Any], depth_level: str) -> dict[str, Any]:
    """LLM 분석 결과를 v2.1.0 스펙에 맞게 검증하고 보정한다."""

    # 1. user_summary 검증 — 구조 보장
    raw_summary = analysis.get("user_summary", {})
    if not isinstance(raw_summary, dict):
        raw_summary = {}
    user_summary = {
        "keywords": raw_summary.get("keywords", []) if isinstance(raw_summary.get("keywords"), list) else [],
        "summary": str(raw_summary.get("summary", "")),
    }
    # keywords 개수 제한 (3–5개)
    user_summary["keywords"] = user_summary["keywords"][:5]

    # 2. main_theme 검증 — 길이 제한
    main_theme = str(analysis.get("main_theme", ""))
    if len(main_theme) > self.max_theme_length:
        main_theme = main_theme[:self.max_theme_length] + "..."

    # 3. emotional_journey 검증 — 구조 보장
    raw_journey = analysis.get("emotional_journey", {})
    emotional_journey = {
        "opening":     str(raw_journey.get("opening", "")),
        "development": str(raw_journey.get("development", "")),
        "resolution":  str(raw_journey.get("resolution", "")),
    } if isinstance(raw_journey, dict) else {}

    # 4. key_messages 검증 — 리스트 보장
    key_messages = analysis.get("key_messages", [])
    if not isinstance(key_messages, list):
        key_messages = []
    key_messages = key_messages[:5]  # 최대 5개

    # 5. depth_level — 코드가 complexity_score로 결정 (LLM 값 무시)
    return {
        "user_summary":       user_summary,
        "main_theme":         main_theme,
        "emotional_journey":  emotional_journey,
        "key_messages":       key_messages,
        "depth_level":        depth_level,
    }
```

> **주의**: `sub_themes`, `target_duration`, `narrative_structure` 보정 로직을 함께 제거한다 (CA-2 수정).

---

### 4-B: CA-2 수정 — 레거시 보정 제거

**파일**: `src/agents/podcast/content_analyzer.py`

4-A 수정에서 `_validate_and_correct` 반환 dict에 `sub_themes`, `target_duration`, `narrative_structure`를 제거한다. 아래 코드도 삭제한다:
- `VALID_NARRATIVE_STRUCTURES` 상수 (더 이상 사용 안 함)
- `_DEFAULTS`의 `min_sub_themes`, `max_sub_themes` 항목
- `_load_config`의 `self.min_sub_themes`, `self.max_sub_themes`

**하위 호환 확인**:
```
Script Generator (script_generator.py:55):
    content_analysis.get("sub_themes", state.get("sub_themes", []))
    → [] 반환은 변경 전과 동일하므로 동작 변화 없음 ✅

Script Generator (script_generator.py:56-57):
    content_analysis.get("target_duration", 4)
    → 4 반환은 변경 전과 동일 ✅
```

---

### 4-C: SG-1 수정 — 폴백 로직 개선

**파일**: `src/agents/podcast/script_generator.py`

`"Mental Health"` 하드코딩을 제거하고 `content_analysis` 누락 시 명시적 에러 처리로 전환한다.

```python
# Before
main_theme: str = str(
    content_analysis.get("main_theme", state.get("main_theme", "Mental Health"))
)

# After
main_theme: str = str(content_analysis.get("main_theme", ""))
if not main_theme:
    self.logger.error(
        "[ScriptGenerator] main_theme 누락 — content_analysis=%s",
        bool(content_analysis),
    )
    return {"script_draft": {}, "error": "main_theme_missing"}
```

> `state.get("main_theme", ...)` 참조도 제거. `main_theme`은 AgentState 최상위 필드가 아님.

---

### 4-D: EM-1 수정 — stub 고정값 제거

**파일**: `src/agents/podcast/episode_memory.py`

`suggested_personalization` 하드코딩을 제거한다. Pinecone 연동 전까지는 `None`으로 반환하여 하위 에이전트가 이 값이 없음을 명시적으로 인지하게 한다.

```python
# Before
payload = {
    "items": items,
    "summary": f"'{query}'와 관련된 과거 기록을 {len(items)}건 찾았습니다.",
    "suggested_personalization": {"topic": "Restoration of Color"},  # ← 제거
    "_meta": {"namespace": "mem_podcast_episode", "engine": "mock_db", "status": "success"},
}

# After
payload = {
    "items": items,
    "summary": f"'{query}'와 관련된 과거 기록을 {len(items)}건 찾았습니다.",
    # TODO(개발자2): Pinecone 연동 후 실제 개인화 제안 생성 구현
    # "suggested_personalization": {...},
    "_meta": {"namespace": "mem_podcast_episode", "engine": "mock_db", "status": "success"},
}
```

---

### 4-E: KA-1 수정 — `recommended_approaches` AgentState 등록 또는 반환 제거

두 가지 선택지:

**선택지 1 — AgentState에 필드 추가** (3인 합의 필요)

`src/models/agent_state.py` (Protected File):
```python
# 추론/생성 필드에 추가
recommended_approaches: list[Any]  # Knowledge Agent → 권장 접근법 목록
```

**선택지 2 — 반환 제거** (권장, 현재 사용처 없음)

`knowledge.py:298`:
```python
# Before
return {
    "knowledge_results": {...},
    "recommended_approaches": synthesis.get("recommended_approaches", []),
}

# After — knowledge_results 내부로 이동
return {
    "knowledge_results": {
        "documents": enriched_docs,
        "synthesis": synthesis.get("synthesis", ""),
        "recommended_approaches": synthesis.get("recommended_approaches", []),  # 내부로 이동
    },
}
```

> 선택지 2 채택 시 Podcast Reasoning의 `knowledge_result` 참조 코드도 업데이트 필요:
> `knowledge_result.get("recommended_approaches", [])` → `knowledge_result.get("knowledge_results", {}).get("recommended_approaches", [])`

---

### 4-F: BV-1 수정 — Batch Validator 명시적 필드 추출

**파일**: `src/agents/podcast/batch_validator.py`

LLM 응답에서 기대하는 필드만 명시적으로 추출하여 반환한다.

```python
# LLM 응답 처리 부분 (line 116 이후)
action = validation.get("action", {})
if not isinstance(action, dict):
    action = {}
decision = action.get("decision", "revise")

verdict_map = {"approve": "PASS", "revise": "FAIL", "escalate": "CRITICAL_FAIL"}

# 명시적 필드 재구성
result = {
    "verdict":       verdict_map.get(decision, "FAIL"),
    "overall_score": float(validation.get("overall_score", 0.0)),
    "decision":      decision,
    "action": {
        "decision":               decision,
        "revision_instructions":  str(action.get("revision_instructions", "")),
        "priority_fixes":         action.get("priority_fixes", []) if isinstance(action.get("priority_fixes"), list) else [],
    },
}

# 선택적 필드 — 존재하면 포함
if "scores" in validation:
    result["scores"] = validation["scores"]
if "critical_issues" in validation:
    result["critical_issues"] = validation["critical_issues"]

return {"validation_result": result}
```

---

### 4-G: EA-1 수정 — Emotion Agent 폴백 개선

**파일**: `src/agents/podcast/emotion.py`

LLM 실패 폴백에서 `emotional_journey_hint` 하드코딩을 빈 리스트로 교체한다.

```python
# Before (emotion.py:120)
"emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],

# After
"emotional_journey_hint": [],  # LLM 실패 시 힌트 없음 — Script Generator가 기본 흐름 사용
```

---

## 5. 수정 우선순위 및 담당자

### Phase 1 — 즉시 수정 (데이터 정확성 영향)

| 순서 | 이슈 | 파일 | 담당 | 예상 작업 |
|------|------|------|------|---------|
| 1 | CA-2 | `content_analyzer.py` | 개발자3 | `_validate_and_correct` 레거시 보정 코드 제거 |
| 2 | CA-1 | `content_analyzer.py` | 개발자3 | `_validate_and_correct` 화이트리스트 재구성 (CA-2와 동시 작업) |
| 3 | EM-1 | `episode_memory.py` | 개발자2 | `suggested_personalization` stub 고정값 제거 |
| 4 | SG-1 | `script_generator.py` | 개발자1 | `"Mental Health"` 폴백 제거 및 에러 처리 |

### Phase 2 — 단기 수정 (안정성 개선)

| 순서 | 이슈 | 파일 | 담당 | 예상 작업 |
|------|------|------|------|---------|
| 5 | BV-1 | `batch_validator.py` | 개발자3 | LLM 응답 명시적 필드 추출 |
| 6 | KA-1 | `knowledge.py` | 개발자1 | `recommended_approaches` 위치 정리 (4-E 선택지 2 권장) |
| 7 | EA-1 | `emotion.py` | 개발자2 | 폴백 `emotional_journey_hint` 빈 배열로 교체 |

### Phase 3 — 정리 (낮은 우선순위)

| 순서 | 이슈 | 파일 | 담당 | 예상 작업 |
|------|------|------|------|---------|
| 8 | PR-1 | `podcast_reasoning.py` | 개발자3 | KA-1 수정 후 연동 확인 |
| 9 | SG-2 | `script_generator.py` | 개발자1 | 무해하나 일관성을 위해 `error` 키 제거 검토 |
| 10 | BV-2 | `batch_validator.py` | 개발자3 | 조기 반환 구조를 정상 반환과 일치시킴 |

---

## 6. 검증 체크리스트

각 이슈 수정 완료 후 아래 항목을 확인한다.

### CA-1, CA-2 수정 검증

```bash
# 단위 테스트 실행
pytest tests/agents/test_content_analyzer.py -v

# 확인 항목:
# [ ] content_analysis에 user_summary 키 포함 여부
# [ ] content_analysis에 key_messages 키 포함 여부
# [ ] content_analysis에 sub_themes 키 미포함 여부 (또는 항상 [] 확인)
# [ ] LLM 실패 시 content_analysis.get("user_summary", {}) 방어 처리 동작
```

### SG-1 수정 검증

```bash
pytest tests/agents/test_script_generator.py -v

# 확인 항목:
# [ ] content_analysis 없을 때 script_draft={}, error="main_theme_missing" 반환
# [ ] "Mental Health" 문자열이 스크립트에 나타나지 않음
```

### EM-1 수정 검증

```bash
pytest tests/agents/test_episode_memory.py -v

# 확인 항목:
# [ ] memory_results에 suggested_personalization 키 없음 (또는 None)
# [ ] "Restoration of Color" 문자열이 출력에 나타나지 않음
```

### BV-1 수정 검증

```bash
pytest tests/agents/test_batch_validator.py -v

# 확인 항목:
# [ ] validation_result에 verdict, overall_score, action 키 항상 존재
# [ ] LLM이 overall_score 누락 시 0.0으로 기본값 처리
# [ ] action.revision_instructions 누락 시 "" 처리
```

### 통합 테스트

```bash
# 전체 파이프라인 테스트 (live 제외)
pytest tests/ -v -m "not live"

# 파이프라인 통합 테스트 (있는 경우)
pytest tests/test_pipeline.py -v
```

---

## 관련 문서

- `docs/architecture/AGENT_OUTPUT_CONTRACT.md` — 에이전트별 출력 dict 구조 전체 명세
- `src/models/agent_state.py` — AgentState 스키마 (Protected, 3인 합의 필요)
- `prompts/podcast/content_analyzer.yaml` — Content Analyzer 프롬프트 (활성 버전: v2.1.0)
- `prompts/podcast/batch_validator.yaml` — Batch Validator 프롬프트 (활성 버전: v2.3.0)
- `prompts/podcast/podcast_reasoning.yaml` — Podcast Reasoning 프롬프트 (활성 버전: v3.0.0)

---

*작성: 2026-04-08 | 코드베이스 직접 분석 기반*

# Mind-Log 에이전트 I/O 점검 & 토큰 최적화 보고서

> 작성일: 2026-02-27
> 기준 테스트: `test_e2e_multi_provider.py` (Ollama gpt-oss:20b, qwen2.5:14b, OpenAI gpt-4o-mini)
> 대상: 팟캐스트 파이프라인 전체 에이전트 10개

---

## 개요

LangGraph는 전체 `AgentState` dict를 모든 노드에 전달한다. 각 에이전트의 `process()`에서 필요한 필드만 읽도록 설계되어 있으나, 읽은 필드를 LLM 프롬프트에 넣을 때 **불필요한 데이터까지 직렬화**하는 곳이 존재한다.

---

## 1. 에이전트별 역할 & I/O 매핑

### TIER 0: IntentClassifierAgent

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/conversation/intent_classifier.py` |
| **역할** | 사용자 입력의 의도 분류, 복잡도 산출, 1차 위기 감지 |
| **모델** | Haiku |
| **State 읽기** | `user_input` (L84), `user_id` (L85), `session_id` (L86) |
| **LLM에 전달** | `user_input`만 (L364) |
| **State 쓰기** | `intent`, `risk_level`, `risk_score`, `safety_flags`, `next_step` |
| **토큰 효율** | Clean |

---

### TIER 1: SafetyAgent (병렬) — 개발자2

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/safety.py` |
| **역할** | 사용자 입력의 안전성 판정 (safe/warning/crisis) |
| **모델** | Sonnet 4 |
| **State 읽기** | `user_input` (L40), `intent` (L41) |
| **LLM에 전달** | `user_input` + **`intent` dict 전체** (L54) |
| **State 쓰기** | `safety_flags` |
| **토큰 효율** | **HIGH 낭비** |

**문제**: L54에서 `f"[Intent 참고(TIER0)]\n{intent}\n\n"` — intent dict 전체가 `str()`로 직렬화. Safety가 실제로 필요한 것은 `risk_flag` 1개뿐.

**권장 수정**:
```python
# Before (L54)
f"[Intent 참고(TIER0)]\n{intent}\n\n"

# After
risk_flag = intent.get("risk_flag", False)
intent_ref = f"[Intent 위기감지 참고]\nrisk_flag: {risk_flag}\n\n" if risk_flag else ""
```

---

### TIER 1: EmotionAgent (병렬) — 개발자2

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/emotion.py` |
| **역할** | 감정 벡터 추출 (primary, intensity, valence, arousal) |
| **모델** | Sonnet 4 |
| **State 읽기** | `user_input` (L26), `intent` (L27) |
| **LLM에 전달** | `user_input` + **`intent` dict 전체** (L36) |
| **State 쓰기** | `emotion_vectors` |
| **토큰 효율** | **HIGH 낭비** |

**문제**: L36에서 Safety와 동일 패턴. Emotion은 intent의 **어떤 필드도 제어 흐름에 사용하지 않음** — 순수 토큰 낭비.

**권장 수정**:
```python
# Before (L36)
f"[Intent 참고(TIER0)]\n{intent}\n\n"

# After — Option A: 완전 제거 (Emotion은 user_input만으로 충분)
intent_ref = ""

# After — Option B: 맥락 힌트만 제공
primary = intent.get("primary_intent", "")
intent_ref = f"[의도 참고: {primary}]\n\n" if primary else ""
```

---

### TIER 1: ContentAnalyzerAgent (병렬) — 개발자3

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/content_analyzer.py` |
| **역할** | 팟캐스트 주제 분석, 에피소드 구조 설계, 감정 여정 설정 |
| **모델** | Sonnet 4 |
| **State 읽기** | `user_input` (L84), `intent` (L85) |
| **LLM에 전달** | intent에서 `primary_intent`, `complexity_score`만 선택 추출 (L157-158) |
| **State 쓰기** | `content_analysis` |
| **토큰 효율** | Clean |

---

### TIER 1: PodcastReasoningAgent (병렬) — 개발자3

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/podcast_reasoning.py` |
| **역할** | GoT/ToT/CoT 3단계 추론, Memory/Knowledge 조건부 호출 |
| **모델** | Sonnet 4 |
| **State 읽기** | `user_input` (L80), `user_id` (L81), `intent` (L82), `execution_plan` (L83) |
| **LLM에 전달** | 3회 LLM 호출 모두에 `user_input` 전체 반복 (L329) |
| **State 쓰기** | `reasoning_result`, 조건부 `memory_results`, `knowledge_results` |
| **토큰 효율** | **MEDIUM 낭비** — 수정 완료 |

**문제**: `_build_phase_context()` L329에서 `user_input`이 GoT/ToT/CoT 3회 모두에 전체 전달.

**수정 내용**: ToT/CoT 단계에서 GoT의 `core_pattern` 추출 시 user_input을 요약 참조로 대체.

---

### TIER 2: ScriptGeneratorAgent — 개발자1

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/script_generator.py` |
| **역할** | 팟캐스트 스크립트 생성 (제목, 세그먼트별 본문, 인사이트) |
| **모델** | Sonnet 4 |
| **State 읽기** | `content_analysis` (L42-53), `reasoning_result` (L56), `segment_plan` (L57), `knowledge_context` (L91) |
| **LLM에 전달** | 선택 추출된 필드만 (`main_theme`, `sub_themes`, `emotional_journey` 등) |
| **State 쓰기** | `script_draft` |
| **토큰 효율** | Clean — user_input 직접 읽지 않음 |

---

### TIER 3: BatchValidatorAgent — 개발자3

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/batch_validator.py` |
| **역할** | 스크립트 품질 검증 (5개 기준), 실패 시 TIER 2 재시도 |
| **모델** | Sonnet 4 |
| **State 읽기** | `script_draft` (L54), `content_analysis` (L55), `reasoning_result` (L56), `safety_flags` (L57), `emotion_vectors` (L58), `iteration_count` (L59) |
| **LLM에 전달** | `_dict_to_readable(script_draft)` (L122) + 나머지 4개 부분 추출 |
| **State 쓰기** | `validation_result`, `next_step`, `iteration_count` |
| **토큰 효율** | **MEDIUM-HIGH 낭비** — 수정 완료 |

**문제**: L122에서 `_dict_to_readable(script_draft)` — script_draft의 메타데이터(total_segments, word_counts 등)까지 직렬화.

**수정 내용**: title + full_script + segments 핵심 필드만 추출하여 검증 대상 축소.

---

### TIER 4: ScriptPersonalizerAgent — 개발자1

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/script_personalizer.py` |
| **역할** | 스크립트 톤/스타일 개인화, Safety 경고 톤 강화 |
| **모델** | Sonnet 4 |
| **State 읽기** | `user_id` (L78), `script_draft` (L81) |
| **LLM에 전달** | 세그먼트별 — user_profile + strategy + emotional_journey |
| **State 쓰기** | `final_output` |
| **토큰 효율** | **MEDIUM — 설계 결함** |

**문제**: L83에서 `emotional_journey = None` 하드코딩. `content_analysis.get("emotional_journey")`를 읽어야 하지만 None으로 고정. 또한 `deep_personalization` 관련 코드가 데드 코드 상태 (`enable_deep_personalization=False`, `llm_client=None`).

**권장 수정**:
```python
# Before (L83)
emotional_journey = None

# After
content_analysis = state.get("content_analysis", {})
emotional_journey = content_analysis.get("emotional_journey", {})
```

---

### 비동기: VisualizationAgent — 개발자2

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/visualization.py` |
| **역할** | 감정 기반 시각화 이미지 메타데이터 생성 |
| **모델** | Sonnet 4 |
| **State 읽기** | `mode`, `emotion_vectors`, `safety_flags`, `content_analysis`, `reasoning_result`, `final_output`, `script_draft` |
| **LLM에 전달** | emotion 핵심 필드 + content_summary (fallback 체인) |
| **State 쓰기** | `visualization_result` |
| **토큰 효율** | 양호 — 다수 필드 읽지만 LLM에는 요약만 전달 |

---

### 비동기: LearningAgent — 개발자3

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/shared/learning.py` |
| **역할** | 세션 학습 데이터 추출 및 백엔드 API 저장 |
| **모델** | Haiku |
| **State 읽기** | `user_id`, `session_id`, `mode`, `user_input`, `emotion_vectors`, `content_analysis`, `final_output` |
| **LLM에 전달** | emotion 부분 + content 부분 + final_output (500자 truncate) |
| **State 쓰기** | `{}` (빈 dict — API 저장만) |
| **토큰 효율** | Clean |

---

## 2. 토큰 낭비 요약

### 우선순위별 분류

| 우선순위 | 에이전트 | 문제 | 예상 절감 | 파일:라인 | 담당 |
|---------|---------|------|----------|----------|------|
| **HIGH** | SafetyAgent | intent dict 전체 직렬화 (risk_flag만 필요) | ~200-400 토큰/호출 | `safety.py:54` | 개발자2 |
| **HIGH** | EmotionAgent | intent dict 전체 직렬화 (사용 안 함) | ~200-400 토큰/호출 | `emotion.py:36` | 개발자2 |
| **HIGH** | BatchValidator | script_draft 메타데이터 포함 직렬화 | ~300-500 토큰/호출 | `batch_validator.py:122` | 개발자3 (수정 완료) |
| **MEDIUM** | PodcastReasoning | user_input 3회 반복 전달 | ~300-600 토큰/전체 | `podcast_reasoning.py:329` | 개발자3 (수정 완료) |
| **MEDIUM** | ScriptPersonalizer | emotional_journey 데드 코드 | 기능 결함 | `script_personalizer.py:83` | 개발자1 |

### 정상 구현 (최적화 불필요)

| 에이전트 | 이유 | 담당 |
|---------|------|------|
| IntentClassifier | user_input만 전달 | 개발자1 |
| ContentAnalyzer | `_build_context_info()`로 2개 필드만 선택 추출 | 개발자3 |
| ScriptGenerator | user_input 직접 읽지 않음, 선택적 필드 사용 | 개발자1 |
| LearningAgent | 조건부 포함 + 500자 truncation | 개발자3 |
| VisualizationAgent | LLM에는 요약만 전달, safety_flags 제어 흐름용 | 개발자2 |

---

## 3. 파이프라인 전체 데이터 흐름도

```
[user_input, user_id, session_id]
    │
    ▼
TIER 0: IntentClassifier
    │ ─→ intent, risk_level, risk_score, safety_flags
    │
    ▼ (병렬 Fan-out)
TIER 1: Safety      ← user_input + intent(risk_flag만 필요)
    │ ─→ safety_flags
TIER 1: Emotion     ← user_input + intent(불필요)
    │ ─→ emotion_vectors
TIER 1: ContentAnalyzer ← user_input + intent(primary_intent, complexity만)
    │ ─→ content_analysis
TIER 1: PodcastReasoning ← user_input + intent + execution_plan
    │   ├─ [조건부] EpisodeMemory ← user_input, user_id
    │   └─ [조건부] KnowledgeAgent ← user_input
    │ ─→ reasoning_result (+memory_results, +knowledge_results)
    │
    ▼ (Fan-in)
TIER 2: ScriptGenerator ← content_analysis + reasoning_result + segment_plan + knowledge_context
    │ ─→ script_draft
TIER 2: Visualization(병렬) ← emotion_vectors + content_analysis + ...
    │ ─→ visualization_result
    │
    ▼
TIER 3: BatchValidator ← script_draft + content_analysis + reasoning_result + safety_flags + emotion_vectors
    │ ─→ validation_result, next_step, iteration_count
    │   └─ FAIL → TIER 2 재시도 (최대 2회)
    │
    ▼
TIER 4: ScriptPersonalizer ← user_id + script_draft
    │ ─→ final_output
    │
    ▼ (비동기)
Learning ← user_id + session_id + user_input + emotion_vectors + content_analysis + final_output
    ─→ {} (API 저장만)
```

---

*이 보고서의 개발자3 담당 항목(BatchValidator, PodcastReasoning)은 이미 수정이 반영되었습니다.*
*개발자1, 개발자2 담당 항목은 각자 검토 후 수정 부탁드립니다.*

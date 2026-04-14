# 에이전트 출력 계약서 (AGENT_OUTPUT_CONTRACT.md)

> **버전**: v1.0
> **코드베이스 기준**: 2026-04-08
> **관련 파일**:
> - `src/models/agent_state.py` — AgentState 스키마 (Protected)
> - `src/api/contracts.py` — 범용 Save/Load 스키마 (Protected)
> - `src/api/external_schemas.py` — 외부 입출력 상세 스키마 (SSOT)
> - `src/api/backend_resources.py` — 리소스 경로/타입 상수
> - `src/agents/podcast/` — 에이전트 구현체

---

## 목차

1. [AgentState 스키마 전체 필드](#1-agentstate-스키마-전체-필드)
2. [에이전트별 출력값 목록](#2-에이전트별-출력값-목록)
3. [출력 정합성 요약표](#3-출력-정합성-요약표)
4. [Backend API 저장 스키마](#4-backend-api-저장-스키마)
5. [외부 출력 스키마 (AI → Frontend)](#5-외부-출력-스키마-ai--frontend)
6. [스트리밍 이벤트 스키마](#6-스트리밍-이벤트-스키마)
7. [스키마 파일 관계 및 수정 규칙](#7-스키마-파일-관계-및-수정-규칙)

---

## 1. AgentState 스키마 전체 필드

**파일**: `src/models/agent_state.py` | `total=False` — 모든 필드 선택적

| 필드 | 타입 | 설정 에이전트 | 설명 |
|------|------|-------------|------|
| `user_input` | `str` | Intent Classifier | 사용자 원본 입력 |
| `user_id` | `str` | Intent Classifier | 사용자 고유 ID |
| `session_id` | `str` | Intent Classifier | 세션 고유 ID |
| `mode` | `Literal["podcast"]` | Intent Classifier | 실행 모드 |
| `intent` | `dict[str, Any]` | Intent Classifier | 의도 분류 결과 |
| `execution_plan` | `dict[str, Any]` | Intent Classifier | 파이프라인 실행 계획 |
| `emotion_vectors` | `dict[str, Any]` | Emotion Agent | 감정 벡터 |
| `content_analysis` | `dict[str, Any]` | Content Analyzer | 팟캐스트 주제 분석 |
| `risk_level` | `int` | Safety Agent (TIER 0 초기값) | 위험 레벨 (0–4) |
| `risk_score` | `float` | Safety Agent (TIER 0 초기값) | 위험 점수 (0.0–1.0) |
| `safety_flags` | `dict[str, Any]` | Safety Agent (TIER 0 초기값) | 안전 플래그 및 상태 |
| `memory_results` | `dict[str, Any]` | Podcast Reasoning (조건부) | Episode Memory 검색 결과 |
| `knowledge_results` | `dict[str, Any]` | Podcast Reasoning (조건부) | Knowledge 검색 결과 |
| `reasoning_result` | `dict[str, Any]` | Podcast Reasoning | GoT/ToT/CoT 추론 결과 |
| `script_draft` | `dict[str, Any]` | Script Generator | 팟캐스트 스크립트 초안 |
| `visual_data` | `dict[str, Any]` | Visualization Agent | 시각화 이미지 메타데이터 |
| `validation_result` | `dict[str, Any]` | Batch Validator | 스크립트 검증 결과 |
| `final_output` | `str` | Script Personalizer | 최종 개인화 스크립트 (JSON) |
| `next_step` | `str` | Safety Agent (CRISIS 시) | 워크플로우 라우팅 플래그 |
| `iteration_count` | `int` | workflow.py | TIER 2→3 재시도 카운터 (최대 2) |
| `stories_context` | `dict[str, Any] \| None` | stories_store / workflow.py | Stories 선택 데이터 (keywords, title, description) |
| `memory_write` | `bool` | workflow.py | True이면 async_post에서 에피소드 메모리 저장 실행 |
| `structured_input` | `dict[str, Any]` | Intent Classifier | 정규화된 사용자 입력 구조체 |
| `learning_pattern` | `dict[str, Any] \| None` | Learning Agent | 추출된 학습 패턴 (비동기 후처리) |
| `memory_text` | `str` | Podcast Reasoning | Episode Memory 검색 쿼리 텍스트 |
| `memory_metadata` | `dict[str, Any]` | Podcast Reasoning | Episode Memory 검색 메타데이터 (필터 조건 등) |

**총 26개 필드**

---

## 2. 에이전트별 출력값 목록

### TIER 0 — Intent Classifier

**파일**: `src/agents/podcast/intent_classifier.py`
**클래스**: `IntentClassifierAgent` | **노드**: `intent_classifier_node`

**정상 반환**:
```python
{
    "intent": {
        "intent_type": str,          # podcast_request | emotional_support | information | counseling | casual_chat | crisis
        "complexity_score": float,   # 0.0–1.0
        "detected_entities": {
            "emotions": list[str],
            "topics": list[str],
            "persons": list[str],
        },
        "flags": {
            "requires_memory": bool,
            "requires_knowledge": bool,
            "visualization_hint": bool,
            "urgency_level": int,    # 0–3
            "risk_flag": bool,
        },
        "reasoning": str,
        "trace_id": str,
        "classified_at": datetime,
    },
    "risk_level": int,               # 0 (정상) 또는 4 (위기 감지)
    "risk_score": float,             # 0.0 (정상) 또는 1.0 (위기)
    "safety_flags": {
        "risk_detected": bool,
        "details": str,              # 위기 감지 시에만
    },
}
```

**폴백 반환** (LLM 실패 시): 동일 구조, `risk_level=0`, `risk_score=0.0`, `safety_flags.error` 포함

**AgentState 정합성**: ✅ `intent`, `risk_level`, `risk_score`, `safety_flags` 정의됨

---

### TIER 1 (병렬) — Safety Agent

**파일**: `src/agents/podcast/safety.py`
**클래스**: `SafetyAgent` | **노드**: `safety_node`

**읽는 필드**: `user_input`, `intent.flags.risk_flag`

**반환**:
```python
{
    "safety_flags": {
        "status": str,               # "safe" | "warning" | "crisis"
        "risk_level": int,           # 0–4
        "risk_score": float,         # 0.0–1.0
        "flags": dict,               # 세부 위험 플래그
        "required_in_script": list[str],  # 스크립트에 포함할 안전 문구
                                          # CRISIS: SAFETY_MESSAGES 상수 최우선 배치
        "error": str | None,
    },
    "risk_level": int,
    "risk_score": float,
    # CRISIS 시에만:
    "next_step": "crisis_response",
}
```

**AgentState 정합성**: ✅ `safety_flags`, `risk_level`, `risk_score`, `next_step` 정의됨

---

### TIER 1 (병렬) — Emotion Agent

**파일**: `src/agents/podcast/emotion.py`
**클래스**: `EmotionAgent` | **노드**: `emotion_node`

**읽는 필드**: `user_input`, `intent`

**반환**:
```python
{
    "emotion_vectors": {
        "primary_emotion": str,              # 주요 감정 (영문 키)
        "intensity": float,                  # 0.0–1.0 (clamped)
        "valence": float,                    # -1.0–1.0 (clamped)
        "arousal": float,                    # 0.0–1.0 (clamped)
        "secondary_emotions": list[str],     # 항상 list
        "tone_recommendation": str,          # Personalizer 참고
        "emotional_journey_hint": list[str], # 항상 list, Script Generator 참고
    }
}
```

**Backend 저장**: 에이전트 내부에서 `emotion_logs` 리소스에 즉시 저장

**AgentState 정합성**: ✅ `emotion_vectors` 정의됨

---

### TIER 1 (병렬) — Content Analyzer

**파일**: `src/agents/podcast/content_analyzer.py`
**클래스**: `ContentAnalyzerAgent` | **노드**: `content_analyzer_node`
**활성 프롬프트 버전**: v2.1.0 (`prompts/podcast/content_analyzer.yaml`)

**읽는 필드**: `user_input`, `intent` (선택적)

**반환**:
```python
{
    "content_analysis": {
        # --- LLM 출력 필드 (v2.1.0 프롬프트 기준) ---
        "user_summary": {            # 사용자에게 직접 보여지는 텍스트 (v1.1.0에서 추가)
            "keywords": list[str],   # 핵심 키워드 3–5개 (2–4글자)
            "summary": str,          # 공감 1문장 + 방향 제시 1문장 (따뜻한 톤)
        },
        "main_theme": str,           # 핵심 주제 (≤100자, 코드 보정)
        "emotional_journey": dict,   # {opening, development, resolution}
        "key_messages": list[str],   # 핵심 메시지 3–5개 (v1.1.0에서 추가)
        "depth_level": str,          # "light" | "moderate" | "deep" (코드가 complexity_score로 덮어씀)

        # --- 코드 보정 필드 (레거시, LLM v2.1.0은 미출력) ---
        "sub_themes": list[str],     # 부주제 (v2.1.0 LLM 미출력 → 코드 보정으로 빈 배열 기본값)
        "target_duration": int,      # 목표 길이 (분, 3–5 범위 보정, 기본값 4)
        "narrative_structure": str,  # personal_story | expert_qa | reflection(기본) | comparative

        # --- 오류 시 ---
        "error": str | None,
    }
}
```

> **`user_summary` 처리 주의**: `_validate_and_correct` 메서드는 이 필드를 명시적으로
> 검증하지 않는다. `corrected = dict(analysis)` (line 206)로 LLM 출력 전체를 복사하므로
> LLM이 반환하는 경우에만 포함된다. v2.1.0 프롬프트는 항상 반환을 지시하나,
> LLM 오류 시 누락될 수 있으므로 참조 코드에서 `.get("user_summary", {})` 방어 처리 필요.

> **레거시 보정 필드**: `sub_themes`, `target_duration`, `narrative_structure`는
> v1.0.0 스펙 잔재로 `_validate_and_correct`가 여전히 보정한다.
> v2.1.0 LLM이 이 필드들을 출력하지 않으므로 `sub_themes=[]`, `target_duration=4`,
> `narrative_structure="reflection"` 기본값으로 채워진다.

**Backend 저장**: 에이전트 내부에서 `content_analyses` 리소스에 즉시 저장

**AgentState 정합성**: ✅ `content_analysis` 정의됨

---

### TIER 1 (병렬) — Podcast Reasoning

**파일**: `src/agents/podcast/podcast_reasoning.py`
**클래스**: `PodcastReasoningAgent` | **노드**: `podcast_reasoning_node`

**읽는 필드**: `user_input`, `intent`, `execution_plan` (선택적)

**반환**:
```python
{
    "reasoning_result": {
        "reasoning_depth": str,      # "full" | "standard" | "minimal"
        "reasoning_strategy": str,   # "GoT+ToT+CoT" | "ToT+CoT" | "CoT"
        "got_result": dict | None,   # depth=="full" 시에만
        # {
        #     "nodes": list[dict],   # node_type, label, intensity, group
        #     "edges": list[dict],   # from, to, relationship
        #     "core_pattern": str,
        #     "insights": list[str],
        # }
        "tot_result": dict | None,   # depth ∈ ["full", "standard"] 시에만
        # {
        #     "alternatives": list[dict],
        #     "selected": str,
        #     "selection_rationale": str,
        # }
        "episode_structure": list,
        "narrative_flow": str,
        "key_points": list[str],
        "emotional_journey": list,
        "confidence": float,
    },
    # 조건부 (complexity ≥ 0.6 또는 requires_memory):
    "memory_results": {
        "documents": list[dict],
        "synthesis": str,
    },
    # 조건부 (complexity ≥ 0.5 또는 requires_knowledge):
    "knowledge_results": {
        "documents": list[dict],
        "synthesis": str,
    },
    "recommended_approaches": list,
}
```

**Backend 저장**: GoT 결과 → `graph_analyses` 리소스 및 Neo4j

**AgentState 정합성**: ✅ `reasoning_result`, `memory_results`, `knowledge_results` 정의됨

---

### 독립 에이전트 — Episode Memory

**파일**: `src/agents/podcast/episode_memory.py`
**클래스**: `EpisodeMemoryAgent` | **호출**: Podcast Reasoning 내부 조건부 DI 호출

**반환** (`{"memory_results": payload}`):
```python
{
    "memory_results": {
        "documents": list[dict],   # Pinecone 검색 결과
        "synthesis": str,          # 요약
    }
}
```

**AgentState 정합성**: ✅ `memory_results` 정의됨 (Podcast Reasoning을 통해 병합)

---

### 독립 에이전트 — Knowledge Agent

**파일**: `src/agents/podcast/knowledge.py`
**클래스**: `KnowledgeAgent` | **호출**: Podcast Reasoning 내부 조건부 DI 호출

**반환**:
```python
{
    "knowledge_results": {
        "documents": list[dict],   # Pinecone 검색 결과
        "synthesis": str,          # 전문 지식 요약
    },
    "recommended_approaches": list,
}
```

**AgentState 정합성**: ✅ `knowledge_results` 정의됨 (Podcast Reasoning을 통해 병합)

---

### TIER 2 (병렬) — Script Generator

**파일**: `src/agents/podcast/script_generator.py`
**클래스**: `ScriptGeneratorAgent` | **노드**: `script_generator_node`

**읽는 필드**: `content_analysis`, `emotion_vectors`, `safety_flags`, `reasoning_result`, `iteration_count`, `validation_result`

**반환** (성공):
```python
{
    "script_draft": {
        "episode_title": str,
        "total_duration": int,
        "segments": list[dict],      # 각 segment 구조:
        # {
        #     "segment_id": str,
        #     "segment_type": str,
        #     "duration_minutes": int,
        #     "script_text": str,
        #     "word_count": int,
        #     "emotional_tone": str,
        #     "tts_markers": list,
        # }
        "key_insights": list[str],
        "themes": list[str],
        "metadata": {
            "generated_at": str,
            "main_theme": str,
            "total_words": int,
            "segment_count": int,
            "processing_time": float,
            "safety_context": {
                "status": str,
                "required_in_script": list[str],
            },
        },
    }
}
```

**반환** (실패): `{"script_draft": {}, "error": str}`

> **주의**: `iteration_count > 0`일 때 이전 `validation_result.action.revision_instructions`를 프롬프트에 주입한다.
> `error` 키는 AgentState에 미정의 필드임 — 워크플로우에서 사용되지 않으며 로그 목적으로만 포함됨.

**AgentState 정합성**: ✅ `script_draft` 정의됨

---

### TIER 2 (병렬) — Visualization Agent

**파일**: `src/agents/podcast/visualization.py`
**클래스**: `VisualizationAgent` | **노드**: `visualization_node`

**읽는 필드**: `emotion_vectors`, `content_analysis`, `user_id`, `mode`

**반환** (성공):
```python
{
    "visual_data": {
        "image_url": str | None,     # S3 CDN URL
        "s3_key": str,
        "status": str,               # "completed"
        "retry_count": int,
        "style_type": str,
        "interpretation": str,       # 해설 텍스트 (한국어, 1–2문장)
        "original_prompt": str,      # 이미지 생성 프롬프트 (영문)
    }
}
```

**반환** (실패): `{"visual_data": {"status": "failed", "error": str}}`

**반환** (SKIP_VISUALIZATION=true): `{"visual_data": {"status": "skipped"}}`

> TIER 2 재시도 시 Visualization 실패는 워크플로우를 중단시키지 않는다 (선택적 실행).
> 내부 자동 재시도 최대 횟수: `settings.yaml`의 `max_retries` 값.

**AgentState 정합성**: ✅ `visual_data` 정의됨

---

### TIER 3 — Batch Validator

**파일**: `src/agents/podcast/batch_validator.py`
**클래스**: `BatchValidatorAgent` | **노드**: `batch_validator_node`

**읽는 필드**: `script_draft`, `content_analysis`, `reasoning_result`, `safety_flags`, `emotion_vectors`, `iteration_count`

**반환**:
```python
{
    "validation_result": {
        "verdict": str,              # "PASS" | "FAIL" | "CRITICAL_FAIL"
        "overall_score": float,      # 0.0–1.0
        "decision": str,             # "approve" | "revise" | "escalate"
        "action": {
            "decision": str,
            "revision_instructions": str,
            "priority_fixes": list[str],
        },
        "forced_pass": bool,         # iteration_count 초과 시에만 True
    }
}
```

**라우팅 로직** (`route_after_tier3_podcast`):
- `verdict == "PASS"` 또는 `forced_pass == True` → `script_personalizer`
- `verdict == "FAIL"` + `iteration_count < max_retries` → `tier2_podcast` (재시도)
- `verdict == "CRITICAL_FAIL"` → `crisis_response`

**AgentState 정합성**: ✅ `validation_result` 정의됨

---

### TIER 4 — Script Personalizer

**파일**: `src/agents/podcast/script_personalizer.py`
**클래스**: `ScriptPersonalizerAgent` | **노드**: `script_personalizer_node`

**읽는 필드**: `user_id`, `script_draft`, `content_analysis`, `emotion_vectors`

**반환**:
```python
{
    "final_output": str   # PersonalizedScript.model_dump_json() 직렬화 문자열
}
```

**`final_output` JSON 내부 구조**:
```json
{
    "episode_id": "ep_...",
    "episode_title": "string",
    "total_duration": 5,
    "segments": [
        {
            "segment_id": "string",
            "segment_type": "string",
            "duration_minutes": 1,
            "script_text": "string",
            "word_count": 100,
            "emotional_tone": "string",
            "tts_markers": []
        }
    ],
    "key_insights": ["string"],
    "themes": ["string"],
    "personalization_meta": {
        "applied_style": {},
        "adjusted_segments": ["string"],
        "attitude_applied": "string"
    }
}
```

**AgentState 정합성**: ✅ `final_output` 정의됨

---

### 비동기 후처리 — Learning Agent

**파일**: `src/agents/podcast/learning.py`
**클래스**: `LearningAgent` | **노드**: `learning_node`

**읽는 필드**: 전체 AgentState (분석 전용)

**반환**: `{}` (빈 dict — AgentState 변경 없음)

**Backend 저장**: `learning` 리소스에 패턴 분석 결과 저장

**AgentState 정합성**: N/A (상태 변경 없음)

---

## 3. 출력 정합성 요약표

| 에이전트 | 파일 | 반환 키 | AgentState 필드 | 정합성 |
|---------|------|---------|----------------|--------|
| Intent Classifier | `intent_classifier.py` | `intent`, `risk_level`, `risk_score`, `safety_flags` | ✅ 4개 정의 | ✅ |
| Safety Agent | `safety.py` | `safety_flags`, `risk_level`, `risk_score`, `next_step`(조건부) | ✅ 4개 정의 | ✅ |
| Emotion Agent | `emotion.py` | `emotion_vectors` | ✅ 1개 정의 | ✅ |
| Content Analyzer | `content_analyzer.py` | `content_analysis` (`user_summary`, `key_messages` 포함 — 코드 미검증 통과 필드) | ✅ 1개 정의 | ✅ |
| Podcast Reasoning | `podcast_reasoning.py` | `reasoning_result`, `memory_results`*, `knowledge_results`*, `recommended_approaches`* | ✅ 3개 정의, `recommended_approaches` 미정의 ⚠️ | ⚠️ |
| Episode Memory | `episode_memory.py` | `memory_results` | ✅ 1개 정의 | ✅ |
| Knowledge Agent | `knowledge.py` | `knowledge_results`, `recommended_approaches` | ✅ 1개 정의, `recommended_approaches` 미정의 ⚠️ | ⚠️ |
| Script Generator | `script_generator.py` | `script_draft`, `error`(실패시) | ✅ 1개 정의, `error` 미정의 (무해) | ✅ |
| Visualization Agent | `visualization.py` | `visual_data` | ✅ 1개 정의 | ✅ |
| Batch Validator | `batch_validator.py` | `validation_result` | ✅ 1개 정의 | ✅ |
| Script Personalizer | `script_personalizer.py` | `final_output` | ✅ 1개 정의 | ✅ |
| Learning Agent | `learning.py` | `{}` | N/A | ✅ |

**범례**: `*` = 조건부 반환 | ⚠️ = 주의사항 있음

### 주의사항

1. **`user_summary`, `key_messages`** (Content Analyzer): `_validate_and_correct`에서 명시적 검증 없이 LLM 출력 그대로 통과. v2.1.0 프롬프트는 항상 반환하도록 지시하지만, LLM 오류 시 누락 가능. 참조 시 `.get("user_summary", {})` 방어 처리 필요.

2. **`sub_themes`, `target_duration`, `narrative_structure`** (Content Analyzer): v2.1.0 LLM이 출력하지 않는 레거시 필드. 코드 보정 로직이 잔존하여 기본값으로 채워진다 (`sub_themes=[]`, `target_duration=4`, `narrative_structure="reflection"`). 이 필드에 의존하는 하위 에이전트는 항상 기본값만 받음.

3. **`recommended_approaches`** (Knowledge Agent, Podcast Reasoning): AgentState에 미정의. LangGraph가 병합 시 무시하므로 워크플로우 오작동 없음. 그러나 Script Generator에서 이 값을 참조하는 경우 `state.get("recommended_approaches")`가 항상 `None`을 반환한다.

4. **`error`** (Script Generator 실패 시): AgentState에 미정의. 무시되며 폴백(`script_draft: {}`)으로 처리됨.

---

## 4. Backend API 저장 스키마

### 저장 흐름 개요

```
에이전트 내부 즉시 저장:
  Emotion Agent       → emotion_logs (TYPE_EMOTION_LOG)
  Content Analyzer    → content_analyses (TYPE_CONTENT_ANALYSIS)
  Podcast Reasoning   → graph_analyses (TYPE_GRAPH_ANALYSIS) + Neo4j

파이프라인 완료 후 일괄 저장 (podcasts.py _save_episode_bundle):
  Script Personalizer 결과 → podcast_episodes + podcast_segments (TYPE_PODCAST_EPISODE)
  Visualization Agent 결과 → visualizations (TYPE_VISUALIZATION)

비동기 후처리 저장:
  Learning Agent      → learning (TYPE_LEARNING)
```

### contracts.py — 범용 Save/Load 스키마

```python
# AI → Backend 저장 요청
class SaveRequest(BaseModel):
    user_id: str
    session_id: str
    type: str        # 아래 타입 상수 사용
    data: dict[str, Any]
    timestamp: datetime

# Backend → AI 저장 응답
class SaveResponse(BaseModel):
    success: bool
    id: str | None    # 생성된 리소스 ID
    message: str | None

# Backend → AI 조회 응답
class LoadResponse(BaseModel):
    success: bool
    data: list[dict[str, Any]]
    total: int
    page: int
```

### 리소스 경로 & 타입 상수 (`backend_resources.py`)

| 리소스 상수 | 경로 (`resource=`) | 타입 상수 | 타입 값 (`type=`) | 저장 에이전트 |
|-----------|-------------------|---------|-----------------|-------------|
| `RESOURCE_EMOTION_LOG` | `emotion_logs` | `TYPE_EMOTION_LOG` | `emotion_log` | Emotion Agent |
| `RESOURCE_CONTENT_ANALYSIS` | `content_analyses` | `TYPE_CONTENT_ANALYSIS` | `content_analysis` | Content Analyzer |
| ~~`RESOURCE_GRAPH_ANALYSIS`~~ | ~~`graph_analyses`~~ | ~~`TYPE_GRAPH_ANALYSIS`~~ | ~~`graph_analysis`~~ | ~~Podcast Reasoning~~ — **제거됨 (2026-04-09)** |
| `RESOURCE_PODCAST_EPISODE` | `podcast_episodes` | `TYPE_PODCAST_EPISODE` | `podcast_episode` | 파이프라인 완료 후 |
| `RESOURCE_VISUALIZATION` | `visualizations` | `TYPE_VISUALIZATION` | `visualization` | 파이프라인 완료 후 |
| `RESOURCE_LEARNING` | `learning` | `TYPE_LEARNING` | `learning` | Learning Agent |
| `RESOURCE_GRAPH_NODES` | `graph_nodes` | `TYPE_GRAPH_CUMULATIVE` | `graph_cumulative` | Podcast Reasoning (EMA 누적 그래프, GET/PUT) |
| `RESOURCE_SESSION` | `sessions` | — | — | TODO(backend): 경로명 확정 필요 |

> **주의**: `resource`와 `type`은 별개 파라미터다. `resource`는 API 경로, `type`은 SaveRequest의 `type` 필드.

### SaveRequest.data 구체 스키마 (`external_schemas.py`)

#### `TYPE_EMOTION_LOG` → `MySQLEmotionLog`

```python
{
    "log_id": str,            # PK
    "session_id": str,        # FK → sessions
    "user_id": str,           # FK → users
    "mode": "podcast",
    "episode_id": str | None, # FK → podcast_episodes
    "primary_emotion": str,
    "intensity": float,       # 0.0–1.0
    "valence": float,         # -1.0–1.0
    "arousal": float,         # 0.0–1.0
    "secondary_emotions": list[str],
    "tone_recommendation": str,
    "trace_id": str,
    "created_at": datetime,
}
```

#### `TYPE_PODCAST_EPISODE` → `MySQLPodcastEpisode` + `MySQLPodcastSegment` (복수)

**에피소드 메타** (`podcast_episodes` 테이블):
```python
{
    "episode_id": str,         # PK
    "session_id": str,         # FK
    "user_id": str,            # FK
    "episode_title": str,
    "total_duration": int,     # 분
    "total_words": int,
    "segment_count": int,
    "key_insights": list[str],
    "themes": list[str],
    "reasoning_depth": str,    # full | standard | minimal
    "cover_image_url": str | None,
    "intent_type": str,
    "complexity_score": float,
    "safety_status": str,      # safe | warning | crisis
    "validation_score": float,
    "retry_count": int,
    "pipeline_duration_ms": int,
    "trace_id": str,
    "correlation_id": str,
    "created_at": datetime,
}
```

**세그먼트** (`podcast_segments` 테이블, 에피소드당 복수 행):
```python
{
    "segment_id": str,           # PK
    "episode_id": str,           # FK → podcast_episodes
    "segment_order": int,        # 0부터
    "segment_type": str,
    "duration_minutes": int,
    "script_text": str,
    "word_count": int,
    "emotional_tone": str,
    "tts_markers_json": str,     # JSON 직렬화
}
```

#### `TYPE_GRAPH_CUMULATIVE` → `GraphCumulativeData` (전용 PUT)

> 주의: 범용 `SaveRequest` 대신 전용 형식 사용. `session_id`/`timestamp` 포함 금지.
> `put_graph_cumulative()`가 `{user_id, type, data}` 만 전송한다.

```python
# PUT /api/v1/graph_nodes body
{
    "user_id": str,                # 사용자 UUID
    "type": "graph_cumulative",
    "data": {
        "nodes": [
            {
                "label": str,          # 키워드 텍스트 (예: "업무과부하")
                "grp": str,            # 6개 카테고리 중 하나
                "weight": float,       # EMA 누적 가중치 (0.0~1.0)
                "mention_count": int,  # 등장 횟수
                "trend": str,          # "increasing" | "stable" | "decreasing"
                "first_seen": str,     # ISO 8601 (최초 등장)
                "last_seen": str,      # ISO 8601 (최근 등장)
            }
        ],
        "links": [
            {
                "source_label": str,   # 출발 노드 label
                "source_grp": str,     # 출발 노드 grp
                "target_label": str,   # 도착 노드 label
                "target_grp": str,     # 도착 노드 grp
                "weight": int,         # 연결 강도/빈도
                "relationship": str,   # 관계 유형 (causes 등)
                "first_seen": str,     # ISO 8601
                "last_seen": str,      # ISO 8601
            }
        ],
    }
}
```

**UPSERT 키**: 노드 `user_id + label + grp`, 링크 `user_id + source_label + source_grp + target_label + target_grp`

#### `TYPE_VISUALIZATION` → `MySQLVisualizationMeta`

```python
{
    "visualization_id": str,  # PK
    "session_id": str,        # FK
    "user_id": str,           # FK
    "mode": "podcast",
    "episode_id": str | None,
    "s3_key": str,            # S3 객체 키
    "cdn_url": str,           # CDN URL
    "image_prompt": str,      # 생성 프롬프트 (영문)
    "interpretation_text": str,
    "trace_id": str,
    "created_at": datetime,
}
```

#### `TYPE_LEARNING` → `MySQLLearningPattern`

```python
{
    "pattern_id": str,                # PK
    "session_id": str,                # FK
    "user_id": str,                   # FK
    "mode": "podcast",
    "preferred_topics": list[str],
    "emotional_patterns": list[str],
    "interaction_style": str,
    "personalization_suggestions": list[str],
    "effectiveness_score": float,     # 0.0–1.0
    "raw_learning_data": dict,        # LLM 원본 결과 (디버깅용)
    "trace_id": str,
    "created_at": datetime,
}
```

---

## 5. 외부 출력 스키마 (AI → Frontend)

### 5-1. 팟캐스트 에피소드 생성 응답

**엔드포인트**: `POST /api/v1/podcasts/episodes`
**스키마**: `PodcastEpisodeResponse` (전체) 또는 `SlimPodcastResponse` (슬림)

#### `PodcastEpisodeResponse` (전체 응답)

AgentState 필드 매핑:

| 응답 필드 | AgentState 출처 | 비고 |
|----------|----------------|------|
| `episode` | `script_draft` + `final_output` | Script Personalizer 최종 출력 |
| `emotion` | `emotion_vectors` | 요약 버전 (EmotionSummary) |
| `safety_alert` | `safety_flags` | warning/crisis 시에만 포함 |
| `cover_image` | `visual_data` | 비동기 생성 시 null 가능 |
| `metadata` | 파이프라인 메타 | 처리 시간, 추론 깊이 등 |
| `tracing` | 자동 생성 | request_id, trace_id, correlation_id |

```python
class PodcastEpisodeResponse(BaseModel):
    success: Literal[True]
    episode: PodcastEpisodeData        # 에피소드 전체 데이터
    emotion: EmotionSummary | None
    safety_alert: SafetyAlertData | None
    cover_image: VisualizationData | None
    metadata: PodcastResponseMeta
    tracing: RequestTracing
```

#### `PodcastEpisodeData` (에피소드 본문)

```python
{
    "episode_id": str,
    "session_id": str,
    "episode_title": str,
    "total_duration": int,
    "segments": [
        {
            "segment_id": str,
            "segment_type": str,
            "duration_minutes": int,
            "script_text": str,
            "word_count": int,
            "emotional_tone": str,
            "tts_markers": [
                {"position": int, "instruction": str}
            ]
        }
    ],
    "key_insights": list[str],
    "themes": list[str],
    "created_at": datetime,
}
```

#### `EmotionSummary` (emotion_vectors 요약)

```python
{
    "primary_emotion": str,      # 영문 키
    "primary_emotion_kr": str,   # 한국어 (UI 표시용)
    "intensity": float,          # 0.0–1.0
    "valence": float,            # -1.0–1.0
    "secondary_emotions": list[str],
    "tone_recommendation": str,
}
```

> `arousal`과 `emotional_journey_hint`는 Emotion Agent 내부 전용 — 이 응답에 미포함.

#### `SafetyAlertData` (safety_flags 응답 변환)

```python
{
    "status": "warning" | "crisis",
    "alert_message": str,          # 한국어 안내 메시지
    "helpline_info": [             # crisis 시 필수
        {"name": str, "phone": str, "description": str}
    ] | None,
    "show_emergency_button": bool, # crisis 시 True
}
```

#### `VisualizationData` (visual_data 응답 변환)

```python
{
    "image_url": str | None,     # S3 CDN URL
    "interpretation": str,
    "style_type": str,
    "original_prompt": str,
    "resolution": str,           # 기본 "1024x1024"
    "status": str,               # "completed" | "skipped"
}
```

> `local_path`는 내부 전용 — API 응답에 미포함.

#### `SlimPodcastResponse` (슬림 응답)

```python
{
    "success": True,
    "episode_id": str,
    "session_id": str,
    "safety_alert": SafetyAlertData | None,
    "tracing": RequestTracing,
}
```

> 파이프라인 실행 + DB 저장 완료 후 반환하는 최소 응답.
> CRISIS 시 에피소드가 미생성되어 DB 미저장이므로 `safety_alert`만 직접 포함.

#### `PodcastResponseMeta`

```python
{
    "mode": "podcast",
    "pipeline_duration_ms": int,
    "intent_type": str,
    "complexity_score": float,
    "reasoning_depth": str,      # full | standard | minimal
    "retry_count": int,
    "total_words": int,
}
```

---

### 5-2. 감정 히스토리 조회 응답

**엔드포인트**: `GET /api/v1/users/{user_id}/emotions`
**스키마**: `EmotionHistoryResponse`

```python
{
    "success": True,
    "emotions": [
        {
            "log_id": str,
            "session_id": str,
            "mode": "podcast",
            "primary_emotion": str,
            "intensity": float,
            "valence": float,
            "arousal": float,          # 히스토리 조회에는 포함 (내부 저장값)
            "secondary_emotions": list[str],
            "created_at": datetime,
        }
    ],
    "pagination": {
        "page": int,
        "page_size": int,
        "total_items": int,
        "total_pages": int,
        "has_next": bool,
        "has_prev": bool,
    },
    "tracing": RequestTracing,
}
```

---

### 5-3. 에피소드 목록 조회 응답

**엔드포인트**: `GET /api/v1/users/{user_id}/podcasts/episodes`
**스키마**: `PodcastEpisodeListResponse`

```python
{
    "success": True,
    "episodes": [
        {
            "episode_id": str,
            "episode_title": str,
            "total_duration": int,
            "themes": list[str],
            "primary_emotion": str | None,
            "cover_image_url": str | None,
            "created_at": datetime,
        }
    ],
    "pagination": PaginationMeta,
    "tracing": RequestTracing,
}
```

---

### 5-4. 세션 관리 응답

**세션 생성** (`POST /api/v1/sessions`) → `SessionCreateResponse`:
```python
{
    "success": True,
    "session_id": str,
    "mode": "podcast",
    "created_at": datetime,
    "tracing": RequestTracing,
}
```

**사용자 프로필 조회** (`GET /api/v1/users/{user_id}/profile`) → `UserProfileResponse`:
```python
{
    "success": True,
    "profile": {
        "user_id": str,
        "display_name": str,
        "age_group": str,           # 10s | 20s | 30s | 40s | 50s | 60s_plus
        "preferred_style": str,     # warm | professional | casual | neutral
        "preferred_attitude": str,  # supportive | analytical | balanced | motivational
        "accessibility_needs": list[str],
        "notification_enabled": bool,
        "created_at": datetime,
        "updated_at": datetime,
        "total_sessions": int,
        "total_episodes": int,
    },
    "tracing": RequestTracing,
}
```

---

### 5-5. 에러 응답 (공통)

```python
{
    "success": False,
    "error": {
        "code": str,         # NOT_FOUND | VALIDATION_ERROR | SERVER_ERROR |
                             # RATE_LIMITED | PIPELINE_TIMEOUT | CRISIS_ESCALATION
        "message": str,
        "field": str | None, # 검증 에러 시 해당 필드명
        "trace_id": str | None,
    },
    "tracing": RequestTracing | None,
}
```

---

## 6. 스트리밍 이벤트 스키마

**엔드포인트**: `POST /api/v1/podcasts/episodes/stream`
**프로토콜**: SSE (Server-Sent Events)
**스키마**: `StreamEvent`

```python
{
    "event_type": str,           # 아래 이벤트 타입 참조
    "session_id": str,
    "tier": int | None,          # 현재 TIER (0–4)
    "agent": str | None,         # 에이전트 이름 (해당 시)
    "data": dict,                # 이벤트 페이로드 (타입별 상이)
    "elapsed_ms": int,
    "timestamp": datetime,
    "trace_id": str,
}
```

### 이벤트 타입 (`StreamEventType`)

| 이벤트 | 발생 시점 | `data` 내용 |
|-------|---------|------------|
| `tier_start` | TIER 실행 시작 | `{"tier": int, "agents": list[str]}` |
| `agent_complete` | 개별 에이전트 완료 | `{"agent": str, "duration_ms": int}` |
| `tier_end` | TIER 실행 완료 | `{"tier": int, "duration_ms": int}` |
| `crisis_detected` | Safety CRISIS 감지 | `{"safety_alert": SafetyAlertData}` |
| `partial_response` | 부분 응답 (스트리밍 중) | `{"content": str}` |
| `final_response` | 최종 응답 완료 | `PodcastEpisodeResponse` |
| `error` | 에러 발생 | `{"error": ErrorDetail}` |

---

## 7. 스키마 파일 관계 및 수정 규칙

### 파일 역할 분담

```
contracts.py        — 범용 Save/Load 스키마 (Protected, 3인 합의)
external_schemas.py — 외부 입출력 상세 스키마 SSOT (신규 개발용)
backend_resources.py — 리소스/타입 상수 (모든 에이전트가 import)
agent_state.py      — LangGraph 공유 상태 (Protected, 3인 합의)
```

### 수정 시 체크리스트

| 변경 내용 | 수정할 파일 |
|----------|-----------|
| 에이전트 새 출력 필드 추가 | `agent_state.py` + 해당 에이전트 파일 |
| 새 리소스 경로 추가 | `backend_resources.py` (Backend 팀 합의 후) |
| 새 API 엔드포인트 응답 스키마 | `external_schemas.py` + `docs/architecture/API_SPEC.md` |
| SaveRequest.data 구체 스키마 변경 | `external_schemas.py`의 `MySQL*` 클래스 + Backend 팀 합의 |
| contracts.py의 공통 Save/Load 변경 | `contracts.py` + 3인 합의 |

### `contracts.py` vs `external_schemas.py`

- `contracts.py`의 `ErrorDetail`/`ErrorResponse`는 **DEPRECATED** — 신규 코드는 `external_schemas.py` 버전 사용
- `contracts.py`의 `SaveRequest`/`SaveResponse`/`LoadResponse`는 **유효** — 모든 에이전트가 이 스키마로 Backend 통신
- `external_schemas.py`의 `MySQL*` 클래스는 `SaveRequest.data`의 구체 타입 — 직렬화 후 `data` 필드에 할당

---

*최종 업데이트: 2026-04-08 | 코드베이스 기준으로 작성*

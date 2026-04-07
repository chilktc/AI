# 에이전트 역할 정의서 (AGENT_ROLES.md)

코드 분석 기반으로 작성된 에이전트별 역할·입출력·스키마·소비자·이슈 정의서.

> **참고**: 이 문서는 실제 코드를 기준으로 작성됨. `ProjectDocs/`의 설계 원본과 차이가 있을 수 있음.

---

## 데이터 플로우 개요

### 팟캐스트 모드

```
TIER 0 (Intent)         → 0.3~0.5 KB
TIER 1 (병렬 4개)       → ~8~12 KB (Content 0.25~0.8 + Emotion 0.3 + Reasoning 7~11 + Safety 0.5)
TIER 2 (Script Gen + Visualization 병렬) → 8~21 KB + 1~2 KB
TIER 3 (Batch Val)      → 0.2~0.6 KB
TIER 4 (Personalizer)   → 9~22 KB
Peak State Size: 19~37 KB
```

---

## 구현 현황

| 상태 | 에이전트 |
|------|----------|
| **구현 완료 (11개)** | Intent Classifier, Safety, Emotion, Knowledge, Content Analyzer, Podcast Reasoning, Script Generator, Batch Validator, Script Personalizer, Visualization, Episode Memory |
| **공용 구현 완료 (1개)** | Learning |
| **스텁 (0개)** | — |

---

## 에이전트 상세

### Intent Classifier -- TIER 0 / 공용

- **목적**: 사용자 입력의 의도를 분류하고, 모드를 감지하며, 1차 위기 신호를 판별한다.
- **모델**: Sonnet 3.7 (`sonnet_37`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `user_id` | 세션 | O |
| `session_id` | 세션 | O |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `intent` | dict (IntentClassifierOutput) | 0.3~0.5 KB |
| `risk_level` | int (0-4) | - |
| `risk_score` | float (0.0-1.0) | - |
| `safety_flags` | dict | - |
**출력 스키마 (IntentClassifierOutput)**

```python
{
  "intent_type": str,           # casual_chat|emotional_support|counseling|crisis|information|podcast_request
  "complexity_score": float,    # 0.0-1.0
  "detected_entities": {
    "emotions": list[str],
    "topics": list[str],
    "persons": list[str]
  },
  "flags": {
    "requires_memory": bool,
    "requires_knowledge": bool,
    "visualization_hint": bool,
    "urgency_level": int,       # 0-3
    "risk_flag": bool
  },
  "reasoning": str,
  "trace_id": str,
  "classified_at": datetime
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Safety | `intent` (risk_flag) | reasoning, trace_id |
| Emotion | `intent` (전체) | reasoning, trace_id |
| Content Analyzer | `intent.complexity_score` | reasoning, trace_id, entities |
| Podcast Reasoning | `intent.complexity_score`, `execution_plan` | reasoning, trace_id |

- **데이터 효율**: 30~50% (reasoning, trace_id, classified_at 미사용)
- **알려진 이슈**:
  - [S-1] `risk_level`, `risk_score`, `safety_flags` 쓰기 -- 개발자2 전용 필드 경계 위반
  - [B-3] Safety Agent와 이중 위험평가

---

### Safety Agent -- TIER 1 (병렬) / 공용

- **목적**: 사용자 입력의 위험도를 평가하고, CRISIS 시 파이프라인을 선점 중단한다.
- **모델**: Sonnet 3.7 (`sonnet_37`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `intent` | Intent Classifier | O |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `safety_flags` | dict | ~0.5 KB |

**출력 스키마**

```python
{
  "status": str,                    # safe|warning|crisis
  "reasons": list[str],
  "forbidden_topics": list[str],
  "required_in_script": list[str],
  "tone_guidelines": {
    "avoid_medical_claims": bool,
    "avoid_diagnosis": bool,
    "use_supportive_neutral_tone": bool
  },
  "_debug": {
    "rule_crisis_hit": bool,
    "intent_risk_flag": bool,
    "llm_used": bool
  }
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Batch Validator | status, reasons | _debug |
| Script Personalizer | status, required_in_script | _debug, tone_guidelines |
| Visualization | status, required_in_script | _debug |

- **데이터 효율**: 100%
- **알려진 이슈**:
  - [B-4] 전체 intent dict를 LLM 컨텍스트에 전달 (200~400 토큰 낭비)

---

### Emotion Agent -- TIER 1 (병렬) / 공용

- **목적**: 사용자 입력의 감정을 분석하여 벡터화한다.
- **모델**: Haiku (`haiku`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `intent` | Intent Classifier | X (컨텍스트 참고) |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `emotion_vectors` | dict | ~0.3 KB |

**출력 스키마**

```python
{
  "primary_emotion": str,
  "intensity": float,               # 0.0-1.0
  "valence": float,                 # -1.0 ~ 1.0
  "arousal": float,                 # 0.0-1.0
  "secondary_emotions": list[str],
  "tone_recommendation": str,
  "emotional_journey_hint": list[str]
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Visualization | primary_emotion, intensity, valence, arousal | secondary_emotions |
| Script Personalizer | tone_recommendation | secondary_emotions |
| Batch Validator | (전체) | - |

- **데이터 효율**: 100%
- **알려진 이슈**:
  - [B-4] 전체 intent dict를 LLM 컨텍스트에 전달 (Safety와 동일)

---

### Content Analyzer -- TIER 1 (병렬) / 팟캐스트

- **목적**: 사용자 입력을 분석하여 팟캐스트 에피소드 주제·구조·깊이를 도출한다.
- **모델**: Haiku (`haiku`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `intent` | Intent Classifier | O (complexity_score) |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `content_analysis` | dict | 0.25~0.8 KB |

**출력 스키마**

```python
{
  "main_theme": str,                # max 100자
  "sub_themes": list[str],          # 3-5개
  "target_duration": int,           # 3-5분 고정
  "narrative_structure": str,       # personal_story|expert_qa|reflection|comparative
  "depth_level": str                # light|moderate|deep
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Script Generator | main_theme, sub_themes, target_duration | - |
| Batch Validator | main_theme (비교용) | narrative_structure |

- **데이터 효율**: 75~80%

---

### Podcast Reasoning -- TIER 1 (병렬) / 팟캐스트

- **목적**: GoT+ToT+CoT 3단계 추론으로 에피소드 구조·내러티브·핵심 포인트를 도출한다.
- **모델**: Sonnet 3.7 (`sonnet_37`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `user_id` | 세션 | O |
| `intent` | Intent Classifier | O (complexity_score) |
| `execution_plan` | Intent Classifier | X (조건부 참고) |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `reasoning_result` | dict | 7~11 KB |
| `memory_results` | dict (조건부) | 1.5~3.5 KB |
| `knowledge_results` | dict (조건부) | 2~5 KB |

**추론 깊이 라우팅**

| complexity_score | 깊이 | 전략 | LLM 호출 |
|-----------------|------|------|----------|
| >= full_threshold | full | GoT -> ToT -> CoT | 3회 |
| >= standard_threshold | standard | ToT -> CoT | 2회 |
| < standard_threshold | minimal | CoT only | 1회 |

> **설정값 (settings.yaml SSOT)**: `full_threshold: 0.0`, `standard_threshold: 0.0` → 모든 요청에 full 추론 적용.
> 코드 기본값: 0.8/0.5 (settings.yaml 미설정 시 폴백).

**출력 스키마**

```python
{
  "reasoning_depth": str,           # full|standard|minimal
  "reasoning_strategy": str,        # GoT+ToT+CoT|ToT+CoT|CoT
  "got_result": {                   # full일 때만
    "nodes": list, "edges": list,
    "core_pattern": str, "insights": list
  },
  "tot_result": {                   # full/standard일 때만
    "alternatives": list, "selected": dict,
    "selection_rationale": str
  },
  "episode_structure": list,
  "narrative_flow": str,
  "key_points": list,
  "emotional_journey": list,
  "confidence": float
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Script Generator | episode_structure, narrative_flow, key_points, emotional_journey | **got_result, tot_result** (전체 미사용) |
| Batch Validator | (비교용 참조) | got_result, tot_result |

- **데이터 효율**: **5~7%** (got_result, tot_result가 7~10KB 차지하지만 다운스트림에서 미사용)
- **알려진 이슈**:
  - ~~[C-1]~~ RESOLVED: 임계값 — settings.yaml에서 0.0/0.0으로 설정 (항상 full 추론). 코드 기본값 0.8/0.5는 폴백용.
  - [C-2] 토큰 예산 6000 (`max_tokens: 6000`, 4096에서 상향) -- 출력 7~11KB 잘림 가능성 감소
  - [S-5] memory_results, knowledge_results 조건부 쓰기 미문서화

---

### Episode Memory -- 독립 / 팟캐스트

- **목적**: 과거 팟캐스트 에피소드 기억을 검색하여 일관성과 연속성을 확보한다.
- **모델**: Sonnet 3.5 v2 (`sonnet`, BaseMemoryAgent 상속)
- **구현 상태**: 완료 (KT Cloud RAG Suite 연동)

**입력**: DI 호출 -- `search(query, user_id)`

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `memory_results` | dict | 1.5~3.5 KB |

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Podcast Reasoning | count만 확인 | episodes, segments 상세 |

- **데이터 효율**: 3~7% (count만 사용, 상세 에피소드 데이터 미사용)
- **인덱스명**: `mem-podcast-episode` (하이픈, Pinecone 인덱스 식별자)
- **네임스페이스**: `mem_podcast_episode` (언더스코어, 인덱스 내 데이터 분리)

---

### Knowledge Agent -- 독립 / 공용

- **목적**: 전문 지식 DB를 검색하여 근거 기반 정보를 제공한다.
- **모델**: Sonnet 3.5 v2 (`sonnet`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `user_input` | 사용자 | O |
| `domain_hints` | (미정의) | X |
| `user_context` | (미정의) | X |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `knowledge_results` | dict | 2~5 KB |

**출력 스키마**

```python
{
  "documents": list[{
    "id": str, "title": str, "content": str,
    "relevance_score": float, "applicability_score": float
  }],
  "synthesis": str,
  "recommended_approaches": list[{
    "approach": str, "rationale": str, "contraindications": list[str]
  }]
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Podcast Reasoning | synthesis, recommended_approaches | documents 상세 |

- **데이터 효율**: 20~50% (synthesis만 주로 사용)
- **알려진 이슈**:
  - [S-3] domain_hints, user_context -- AgentState에 미정의 필드 읽기
  - [B-7] domain_hints 미전달

---

### Script Generator -- TIER 2 / 팟캐스트

- **목적**: TIER 1 분석 결과를 종합하여 팟캐스트 스크립트를 생성한다.
- **모델**: Haiku (`haiku`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `content_analysis` | Content Analyzer | O |
| `reasoning_result` | Podcast Reasoning | O (episode_structure) |
| `knowledge_context` | Knowledge Agent | X |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `script_draft` | dict | 8~21 KB |

**출력 스키마**

```python
{
  "episode_title": str,             # 10-30자
  "total_duration": int,
  "segments": list[{
    "segment_id": str, "segment_type": str,
    "duration_minutes": float, "script_text": str,
    "word_count": int, "emotional_tone": str, "tts_markers": dict
  }],
  "key_insights": list[str],       # 3-5개
  "themes": list[str],
  "metadata": dict
}
```

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Batch Validator | 전체 | - |
| Script Personalizer | 전체 | - |

- **데이터 효율**: 100% (출력 전체가 다운스트림에서 사용)
- **알려진 이슈**:
  - [C-2] 토큰 예산 4096 -- 출력 8~21KB 잘림 가능성
  - [S-4] content_analysis 필드 직접 읽기 범위 문서화 필요

---

### Batch Validator -- TIER 3 / 팟캐스트

- **목적**: 스크립트 초안의 품질을 5가지 기준으로 검증하고, 실패 시 재시도를 라우팅한다.
- **모델**: Haiku (`haiku`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `script_draft` | Script Generator | O |
| `content_analysis` | Content Analyzer | O |
| `reasoning_result` | Podcast Reasoning | O |
| `safety_flags` | Safety Agent | O |
| `emotion_vectors` | Emotion Agent | O |
| `iteration_count` | 제어 | O |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `validation_result` | dict | 0.2~0.6 KB |
| `iteration_count` | int (조건부) | - |

**검증 기준**: completeness, quality, safety compliance, emotional tone fit, coherence

**재시도 로직**: `max_retries` = settings.yaml `agents.batch_validator.max_retries` (기본값 2) -- 실패 시 retry_script, 초과 시 forced_pass

**소비자**

| 에이전트 | 사용 필드 | 미사용 필드 |
|----------|-----------|-------------|
| Script Personalizer | passed, forced_pass | 검증 상세 |

- **데이터 효율**: 100%
- **알려진 이슈**:
  - [C-4] MAX_RETRIES 하드코딩 -- settings.yaml 미참조

---

### Script Personalizer -- TIER 4 / 팟캐스트

- **목적**: 사용자 프로필 기반으로 스크립트의 톤·스타일·접근성을 조정한다.
- **모델**: Sonnet 3.7 (`sonnet_37`)
- **구현 상태**: 완료

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `script_draft` | Script Generator | O |
| `user_id` | 세션 | O |
| `emotion_vectors` | Emotion Agent | X |
| `safety_flags` | Safety Agent | X |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `final_output` | str (JSON 직렬화) | 9~22 KB |

**출력 스키마 (PersonalizedScript)**

```python
{
  "episode_id": str,                # ep_{uuid[:12]}
  "episode_title": str,
  "total_duration": int,
  "segments": list[ScriptSegment],
  "key_insights": list[str],
  "themes": list[str],
  "personalization_meta": {
    "applied_style": dict,
    "adjusted_segments": list[str],
    "attitude_applied": str
  }
}
```

**소비자**: 프론트엔드/스토리지 (최종 출력)

- **데이터 효율**: 100%
- **알려진 이슈**:
  - ~~[B-5]~~ RESOLVED: emotional_journey — content_analysis에서 조건부 로드 (None 하드코딩 제거)
  - [S-6] final_output을 model_dump_json() 문자열로 반환 (다른 에이전트는 dict)
  - ~~[C-5]~~ RESOLVED: deep_personalization 플래그 settings.yaml 등록 완료 (`agents.script_personalizer.deep_personalization`)

---

### Visualization Agent -- TIER 2 (병렬) / 공용

- **목적**: 감정 벡터 기반으로 시각화 이미지를 생성하고 S3에 업로드한다.
- **모델**: Haiku (`haiku`, 기획 LLM) + Amazon Titan Image Generator v2 (이미지 생성)
- **구현 상태**: 완료
- **TIER 위치**: TIER 2 — Script Generator와 병렬 실행 (`tier2_podcast_fan_out`)
- **재시도 동작**: `visual_data`가 이미 state에 존재하면 건너뜀 (TIER 3 실패 → TIER 2 재시도 시 중복 방지)
- **실패 허용**: Visualization 실패 시 파이프라인에 영향 없음 (Script Generator 결과만 필수)
- **설정 기반**: 모든 런타임 값(모델/버킷/리전/경로/재시도)은 `config/settings.yaml`에서 관리. 코드 내 하드코딩 없음 (v26)
- **스킵 모드**: `SKIP_VISUALIZATION=true` 환경변수로 이미지 생성 건너뜀 (테스트/배포 시 비용 절감)

**입력 (AgentState 읽기)**

| 필드 | 출처 | 필수 |
|------|------|------|
| `emotion_vectors` | Emotion Agent | O |
| `content_analysis` | Content Analyzer | O |
| `mode` | Intent Classifier | O |
| `user_id` | 세션 | O |

**출력 (AgentState 쓰기)**

| 필드 | 타입 | 크기 |
|------|------|------|
| `visual_data` | dict | 1~2 KB |

**출력 스키마**:
```python
{
    "visual_data": {
        "image_url": str | None,     # S3 URL
        "status": "completed" | "failed" | "skipped",
        "retry_count": int,
        "error": str | None,
        "style_type": str,           # LLM 기획 결과
        "interpretation": str,       # LLM 해석 텍스트
        "original_prompt": str,      # 이미지 생성 프롬프트
    }
}
```

**settings.yaml 설정**:
```yaml
agents:
  visualization:
    model: sonnet                                     # 기획 LLM
    max_tokens: 2048
    image_model: "amazon.titan-image-generator-v2:0"  # 이미지 생성 모델
    image_region: "us-east-1"                         # 이미지 모델 리전 (서울에 없음)
```

- **데이터 효율**: 100%
- **알려진 이슈**:
  - ~~[S-2] `visualization_result` 반환 vs AgentState `visual_data` 정의 -- 키 이름 불일치~~ (RESOLVED: v10에서 수정됨)
  - ~~[S-3] 하드코딩 6건 (모델/버킷/리전/경로/재시도) -- settings.yaml 미사용~~ (RESOLVED: v26에서 전면 제거)
  - ~~[S-4] `call_llm_json(model=...)` TypeError -- LLMClient가 model 파라미터 미지원~~ (RESOLVED: v26에서 model 파라미터 제거)

---

### Learning Agent -- 비동기 / 공용

- **목적**: 사용자 선호·감정 패턴·응답 효과를 분석하여 백엔드에 저장한다.
- **모델**: Sonnet 3.5 v2 (`sonnet`)
- **구현 상태**: 완료

**입력**: AgentState 전체 읽기 (read-only)

**출력**: 빈 dict `{}` (AgentState 변경 없음, 백엔드 API로 직접 저장)

- **데이터 효율**: N/A (출력 없음)

---

## 데이터 효율성 매트릭스

| 에이전트 | 출력(KB) | 실제소비(KB) | 효율(%) | 비고 |
|----------|---------|-------------|---------|------|
| Intent Classifier | 0.3~0.5 | 0.15 | 30~50% | reasoning, trace_id 미사용 |
| Safety | 0.5 | 0.5 | 100% | - |
| Emotion | 0.3 | 0.3 | 100% | - |
| Content Analyzer | 0.25~0.8 | 0.2~0.6 | 75~80% | 구조화 효율적 |
| **Podcast Reasoning** | **7~11** | **0.5** | **5~7%** | **got_result/tot_result 미사용** |
| Episode Memory | 1.5~3.5 | 0.1 | 3~7% | count만 사용 |
| Knowledge | 2~5 | 1.0 | 20~50% | synthesis만 사용 |
| Script Generator | 8~21 | 8~21 | 100% | 출력 전체 사용 |
| Batch Validator | 0.2~0.6 | 0.2~0.6 | 100% | 최적화 완료 |
| Script Personalizer | 9~22 | 9~22 | 100% | - |
| Visualization | 1~2 | 1~2 | 100% | - |

---

## 성능 최적화 대상

| # | 대상 | 현재 | 개선안 | 절감 |
|---|------|------|--------|------|
| O-1 | Podcast Reasoning 출력 | 7~11 KB (GoT+ToT+CoT 전체 포함) | CoT 핵심만 전달, GoT/ToT는 디버그 전용 | 5~8 KB/요청 |
| O-2 | Script Generator 입력 크기 | reasoning_result 전체 수신 (효율 17%) | episode_structure 등 사용 필드만 전달 | LLM 컨텍스트 70% 절감 |
| O-3 | TIER간 상태 누적 | 19~37 KB (TIER 4 도달 시) | 필드 정리 후 축소 | 장기 |

---

## 발견된 이슈 목록

### 기능적 불일치

| # | 심각도 | 이슈 | 파일 | 담당 |
|---|--------|------|------|------|
| B-1 | ~~CRITICAL~~ RESOLVED | Conversation/Podcast 그래프 TIER 0 건너뜀 — 대화모드 제거 완료 (PR #45) | workflow.py | 3인합의 |
| B-2 | ~~CRITICAL~~ RESOLVED | Crisis Deep Response — `required_in_script` 활용으로 법적 고지/상담 번호 전달 (v26) | workflow.py:278~301 | 개발자2 |
| B-3 | HIGH | 이중 위험평가 (Intent + Safety 중복) | intent_classifier.py, safety.py | 개발자1+2 |
| B-4 | HIGH | Safety/Emotion이 전체 intent dict를 LLM에 전달 (200~400토큰 낭비) | safety.py:54, emotion.py:36 | 개발자2 |
| B-5 | ~~MEDIUM~~ RESOLVED | Script Personalizer emotional_journey — content_analysis에서 조건부 로드 | script_personalizer.py | 개발자1 |
| B-7 | MEDIUM | Knowledge Agent domain_hints 미전달 | knowledge.py | 개발자1 |
| B-8 | LOW | CONTRIBUTING.md 노드 시그니처 불일치 | CONTRIBUTING.md:58 | 문서 (수정 완료) |

### AgentState 필드 접근 위반

| # | 심각도 | 이슈 | 에이전트 |
|---|--------|------|----------|
| S-1 | HIGH | 개발자 경계 위반: Intent가 개발자2 필드 쓰기 (risk_level, risk_score, safety_flags) | Intent Classifier |
| S-2 | ~~HIGH~~ RESOLVED | 출력 키 불일치: visual_data로 수정 완료 (visualization.py:64) | Visualization |
| S-3 | MEDIUM | 미정의 필드 읽기: domain_hints, user_context | Knowledge |
| S-4 | MEDIUM | Script Generator 다수 필드 직접 읽기 문서화 필요 | Script Generator |
| S-5 | MEDIUM | 조건부 쓰기 미문서화: memory_results, knowledge_results | Podcast Reasoning |
| S-6 | MEDIUM | 반환 타입 불일치: final_output을 JSON 문자열로 반환 | Script Personalizer |
| S-7 | LOW | 고아 필드: response_draft 정의됨 but 미사용 | AgentState |

### 설정 불일치

| # | 심각도 | 이슈 | 위치 |
|---|--------|------|------|
| C-1 | ~~CRITICAL~~ RESOLVED | Podcast Reasoning 임계값 — settings.yaml 0.0/0.0 (항상 full), 코드 기본값 0.8/0.5 폴백 | settings.yaml |
| C-2 | HIGH → MEDIUM | 토큰 예산: podcast_reasoning 6000으로 상향, script_generator 4096 유지 | settings.yaml |
| C-3 | ~~MEDIUM~~ RESOLVED | TIER 타임아웃 — settings.yaml에서 로드, workflow.py asyncio.wait_for() 적용 완료 (PR #60) | workflow.py |
| C-4 | ~~MEDIUM~~ RESOLVED | batch_validator max_retries — settings.yaml에서 로드 (`cfg.get("max_retries", 2)`) | batch_validator.py |
| C-5 | ~~MEDIUM~~ RESOLVED | deep_personalization 플래그 settings.yaml 등록 완료 | settings.yaml |

### 프롬프트 YAML 상태

| # | 심각도 | 이슈 |
|---|--------|------|
| P-1 | ~~HIGH~~ RESOLVED | shared/ + conversation/ YAML 전체 삭제됨 (PR #45, 대화모드 제거) |
| P-2 | PASS | 팟캐스트 모드 7개 YAML -- 출력스키마, 역할, 변수주입 모두 일치 |

---

*마지막 업데이트: 2026-04-07*

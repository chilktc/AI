# Agent I/O Consolidation & Reprocessing Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에이전트 I/O 전수 문서화, 중간 저장 제거 및 단일 최종 저장 통합, 미사용 필드 정리, 팟캐스트 재가공 에이전트(익명화) 신규 구현.

**Architecture:** 현재 TIER 1 에이전트(Emotion, ContentAnalyzer)가 파이프라인 실행 중 직접 백엔드에 중간 저장을 수행함. 이를 제거하고, TIER 4 이후 단일 `_save_core_data()` 호출에서 필요 데이터를 통합 저장하도록 재구성. 신규 PodcastReprocessingAgent를 TIER 4 이후 비동기로 배치하여 final_output의 개인식별정보를 익명화.

**Tech Stack:** Python 3.11+, LangGraph, FastAPI, MySQL (BackendClient), AgentDataPublisher, output_sanitizer(기존 재사용)

---

## 사전 조사 결과 요약

### 현재 저장 경로 (As-Is)

| 저장 위치 | 리소스 | 시점 | 저장 주체 |
|----------|--------|------|----------|
| EmotionAgent L138 | `emotion_logs` | TIER 1 병렬 실행 중 | publisher.publish() |
| ContentAnalyzerAgent L116 | `content_analyses` | TIER 1 병렬 실행 중 | publisher.publish() |
| PodcastReasoningAgent L505 | `graph_nodes` (PUT) | TIER 1 완료 후 | graph_cumulative.publish_graph_to_rdb() |
| podcasts.py:_save_core_data() L214 | `podcast_episodes` + segments | TIER 4 완료 후 | BackendClient.save() |
| podcasts.py:_save_core_data() L244 | `visualizations` | TIER 4 완료 후 | BackendClient.save() |
| LearningAgent L159 | `learning` | 비동기 후처리 | BackendClient.save() |

### 목표 저장 경로 (To-Be)

| 저장 위치 | 리소스 | 시점 | 저장 주체 |
|----------|--------|------|----------|
| podcasts.py:_save_core_data() | `podcast_episodes` + segments | TIER 4 완료 후 | BackendClient.save() |
| podcasts.py:_save_core_data() | `emotion_logs` | TIER 4 완료 후 (emotion_vectors에서) | BackendClient.save() |
| podcasts.py:_save_core_data() | `content_analyses` | TIER 4 완료 후 (content_analysis에서) | BackendClient.save() |
| podcasts.py:_save_core_data() | `visualizations` | TIER 4 완료 후 | BackendClient.save() |
| podcast_reasoning.py L505 | `graph_nodes` (PUT) | TIER 1 완료 후 | 유지 (누적 그래프, 별도 로직) |
| LearningAgent | `learning` | 비동기 후처리 | 유지 |
| PodcastReprocessingAgent (신규) | `podcast_episodes_anonymized` | 비동기 후처리 | BackendClient.save() |

### 프론트엔드가 사용하는 필드 (저장 필수)

**podcast_episodes / podcast_segments:**
- `episode_id`, `episode_title`, `total_duration`, `total_words`, `segment_count`
- `key_insights[]`, `themes[]`, `cover_image_url`
- `segments[].script_text`, `segments[].emotional_tone`, `segments[].duration_minutes`, `segments[].tts_markers`

**emotion_logs (감정 화면):**
- `primary_emotion`, `intensity`, `valence`, `arousal`, `secondary_emotions[]`

**visualizations (커버 이미지):**
- `cdn_url`, `interpretation_text`

**프론트 미사용 (내부용):**
- `validation_score`, `complexity_score`, `intent_type`, `reasoning_depth`, `retry_count`, `pipeline_duration_ms`, `trace_id`, `correlation_id`
- `tone_recommendation` (emotion_logs)
- `image_prompt` (visualizations)
- `raw_learning_data` (learning_patterns)

### AgentState 미사용 필드

| 필드 | 설정 에이전트 | 문제 |
|------|------------|------|
| `knowledge_results` | PodcastReasoning (조건부) | 하위 에이전트가 읽지 않음 |
| `risk_level`, `risk_score` | Intent Classifier + Safety | 라우팅/검증에 미사용 |
| `execution_plan` | Intent Classifier (불명확) | PodcastReasoning만 읽음 |

### DB 스키마 불일치

| 테이블 | 컬럼 | 문제 |
|--------|------|------|
| `sessions` | `turn_count` | init.sql 정의, 코드 미사용 |
| `emotion_logs` | `turn_id` | init.sql 정의, 코드 미사용 |
| `emotion_logs` | `arousal` | DATA_SCHEMA.md "미포함"이나 실제로 API 응답 포함 |

---

## 파일 구조 (변경/신규 목록)

| 상태 | 파일 | 변경 내용 |
|------|------|---------|
| **수정** | `src/agents/podcast/emotion.py` | publisher.publish() 제거 |
| **수정** | `src/agents/podcast/content_analyzer.py` | publisher.publish() 제거 |
| **수정** | `src/api/routes/podcasts.py` | _save_core_data()에 emotion/content 저장 추가 |
| **수정** | `src/api/contracts.py` | EmotionLogData, ContentAnalysisData 저장 스키마 추가 |
| **수정** | `src/api/backend_resources.py` | TYPE_EMOTION_LOG, TYPE_CONTENT_ANALYSIS 상수 확인/추가 |
| **신규** | `src/agents/podcast/podcast_reprocessing.py` | PodcastReprocessingAgent 구현 |
| **수정** | `src/graph/workflow.py` | reprocessing_node 등록, 비동기 후처리 연결 |
| **신규** | `prompts/podcast/podcast_reprocessing.yaml` | 재가공 에이전트 프롬프트 |
| **수정** | `src/models/agent_state.py` | `reprocessed_output`, `anonymization_report` 필드 추가 |
| **신규** | `dev/local_db/mysql/migrations/001_add_anonymized_table.sql` | `podcast_episodes_anonymized` 테이블 |
| **수정** | `docs/architecture/AGENT_OUTPUT_CONTRACT.md` | 데이터 워크플로우 문서 갱신 |
| **신규** | `docs/architecture/AGENT_IO_DATAFLOW.md` | 에이전트 전체 I/O 및 워크플로우 문서 |
| **수정** | `tests/agents/test_podcast_reprocessing.py` | 신규 에이전트 테스트 |
| **수정** | `tests/api/test_routes_podcasts.py` | _save_core_data 통합 저장 테스트 |

---

## Task 1: 에이전트 I/O 및 데이터 워크플로우 문서 작성

**Files:**
- Create: `docs/architecture/AGENT_IO_DATAFLOW.md`

- [ ] **Step 1: AGENT_IO_DATAFLOW.md 작성**

파일 내용 (전체 작성):

```markdown
# 에이전트 I/O 및 데이터 워크플로우

> 마지막 업데이트: 2026-04-13
> 버전: v1.0

## 1. 파이프라인 전체 데이터 흐름

```
사용자 입력 (PodcastRequest)
  situation, thought, action, colleague_reaction
    ↓ (routes/podcasts.py: user_input 조합)
[AgentState 초기화]
  user_input, user_id, session_id, mode="podcast"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 0: Intent Classifier
  읽기: user_input, user_id, session_id
  쓰기: intent, risk_level, risk_score, safety_flags (1차)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 1 (병렬 Fan-out)
  Safety:   읽기: user_input, intent → 쓰기: safety_flags, risk_level, risk_score, next_step(위기시)
  Emotion:  읽기: user_input, intent → 쓰기: emotion_vectors
  Content:  읽기: user_input, intent → 쓰기: content_analysis
  Reasoning: 읽기: user_input, user_id, intent, execution_plan, session_id
             → 쓰기: reasoning_result, memory_results(조건부), knowledge_results(조건부)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  route_after_tier1:
    next_step == "crisis_response" → crisis_response_node
    else → TIER 2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 2 (병렬)
  ScriptGen:  읽기: safety_flags, content_analysis, reasoning_result, validation_result(재시도시)
              → 쓰기: script_draft
  Visualization: 읽기: emotion_vectors, content_analysis, user_id, mode
                 → 쓰기: visual_data
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 3: Batch Validator
  읽기: script_draft, content_analysis, reasoning_result, safety_flags, emotion_vectors, iteration_count
  쓰기: validation_result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  route_after_tier3:
    verdict == "PASS" → TIER 4
    verdict == "CRITICAL_FAIL" + retries 가능 → TIER 2 재시도
    verdict == "FAIL" + retries 가능 → TIER 2 재시도
    else → TIER 4 강제 통과

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 4: Script Personalizer
  읽기: user_id, script_draft, content_analysis(emotional_journey), session_id
  쓰기: final_output, memory_write, memory_text, memory_metadata
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ↓
_save_core_data() [동기] → podcast_episodes + segments + emotion_logs + content_analyses + visualizations
    ↓
SlimPodcastResponse → 프론트엔드

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
비동기 후처리 (async_post)
  PodcastReprocessingAgent (신규):
    읽기: final_output, user_id, session_id
    쓰기: reprocessed_output, anonymization_report
    저장: podcast_episodes_anonymized
  LearningAgent:
    읽기: emotion_vectors, content_analysis, intent, safety_flags, reasoning_result,
          validation_result, final_output
    저장: learning_patterns
  Memory 저장:
    memory_write, memory_text, memory_metadata → Pinecone (mem-podcast-episode)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 2. 에이전트별 I/O 명세

### Intent Classifier (TIER 0)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_input | str | 사용자 발화 |
| 읽기 | user_id | str | 사용자 UUID |
| 읽기 | session_id | str | 세션 UUID |
| 쓰기 | intent | dict | {intent_type, complexity_score, detected_entities, flags, reasoning} |
| 쓰기 | risk_level | int | 0-4 (1차 판단) |
| 쓰기 | risk_score | float | 0.0-1.0 (1차 판단) |
| 쓰기 | safety_flags | dict | 1차 위기 초기값 (Safety가 최종 덮어씀) |

### Safety Agent (TIER 1)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_input | str | |
| 읽기 | intent | dict | flags.risk_flag 추출 |
| 쓰기 | safety_flags | dict | {status, risk_score, required_in_script, ...} |
| 쓰기 | risk_level | int | 최종 값 (0-4) |
| 쓰기 | risk_score | float | 최종 값 (0.0-1.0) |
| 쓰기(조건부) | next_step | str | "crisis_response" (CRISIS 판정시만) |

### Emotion Agent (TIER 1)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_input | str | |
| 읽기 | intent | dict | intent_type, flags.urgency_level, detected_entities.emotions |
| 쓰기 | emotion_vectors | dict | {primary_emotion, intensity, valence, arousal, secondary_emotions, tone_recommendation, emotional_journey_hint} |

### Content Analyzer (TIER 1)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_input | str | |
| 읽기 | intent | dict | complexity_score |
| 쓰기 | content_analysis | dict | {user_summary, main_theme, emotional_journey(4-key), key_messages, depth_level, sub_themes, target_duration, narrative_structure, confidence} |

### Podcast Reasoning (TIER 1)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_input | str | |
| 읽기 | user_id | str | |
| 읽기 | session_id | str | |
| 읽기 | intent | dict | complexity_score |
| 읽기 | execution_plan | dict | needs_memory, needs_knowledge |
| 쓰기 | reasoning_result | dict | {episode_structure, depth_level, method, ...} |
| 쓰기(조건부) | memory_results | dict | Episode Memory 결과 |
| 쓰기(조건부) | knowledge_results | dict | Knowledge 결과 (하위 에이전트 미사용 ⚠️) |

### Script Generator (TIER 2)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | safety_flags | dict | status, required_in_script |
| 읽기 | content_analysis | dict | main_theme, sub_themes, emotional_journey, target_duration |
| 읽기 | reasoning_result | dict | episode_structure |
| 읽기 | validation_result | dict | action.revision_instructions (재시도시) |
| 읽기 | iteration_count | int | 재시도 횟수 |
| 읽기 | user_id | str | |
| 읽기 | session_id | str | |
| 쓰기 | script_draft | dict | {episode_title, total_duration, segments[], key_insights, themes, metadata} |

### Visualization (TIER 2)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | emotion_vectors | dict | |
| 읽기 | content_analysis | dict | |
| 읽기 | user_id | str | |
| 읽기 | mode | str | |
| 쓰기 | visual_data | dict | {visualization_id, image_url, s3_key, original_prompt, interpretation, style_type} |

### Batch Validator (TIER 3)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | script_draft | dict | |
| 읽기 | content_analysis | dict | |
| 읽기 | reasoning_result | dict | |
| 읽기 | safety_flags | dict | |
| 읽기 | emotion_vectors | dict | |
| 읽기 | iteration_count | int | |
| 쓰기 | validation_result | dict | {verdict, overall_score, action, ...} |

### Script Personalizer (TIER 4)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | user_id | str | |
| 읽기 | session_id | str | |
| 읽기 | script_draft | dict | |
| 읽기 | content_analysis | dict | emotional_journey |
| 쓰기 | final_output | str | PersonalizedScript JSON 문자열 |
| 쓰기 | memory_write | bool | Pinecone 저장 여부 |
| 쓰기 | memory_text | str | Pinecone 저장 텍스트 |
| 쓰기 | memory_metadata | dict | Pinecone 메타데이터 |

### PodcastReprocessingAgent (TIER 4 이후, 비동기 — 신규)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | final_output | str | PersonalizedScript JSON 문자열 |
| 읽기 | user_id | str | |
| 읽기 | session_id | str | |
| 쓰기 | reprocessed_output | str | 익명화된 PersonalizedScript JSON 문자열 |
| 쓰기 | anonymization_report | dict | {original_pii_detected, anonymized_field_count, anonymization_confidence, manual_review_required, flagged_segments, changes_summary} |

### Learning Agent (비동기)
| 방향 | 필드 | 타입 | 설명 |
|------|------|------|------|
| 읽기 | emotion_vectors | dict | primary_emotion, intensity |
| 읽기 | content_analysis | dict | main_theme |
| 읽기 | intent | dict | intent_type, complexity_score |
| 읽기 | safety_flags | dict | status, risk_score |
| 읽기 | reasoning_result | dict | depth_level, method |
| 읽기 | validation_result | dict | overall_score |
| 읽기 | final_output | str | 최대 500자 요약 |

## 3. DB 스키마 불일치 현황

| 테이블 | 컬럼 | 문제 | 권장 조치 |
|--------|------|------|---------|
| sessions | turn_count | 코드 미사용 (대화모드용 예약) | 유지 (대화모드 제외 결정으로 현재 미필요) |
| emotion_logs | turn_id | 코드 미사용 (대화모드용 예약) | 유지 |
| emotion_logs | arousal | DATA_SCHEMA.md "미포함"이나 실제 API 포함 | DATA_SCHEMA.md 문서 수정 |
| podcast_episodes | validation_score, complexity_score, intent_type 등 | DB 저장은 되나 API 응답 미포함 | 유지 (내부 분석용) |

## 4. AgentState 필드 상태

| 필드 | 상태 | 권장 조치 |
|------|------|---------|
| knowledge_results | ⚠️ 미사용 (하위 에이전트 미참조) | 현재는 유지, 향후 ScriptGenerator 활용 검토 |
| risk_level, risk_score | ⚠️ 미사용 (라우팅 미활용) | 현재는 유지, BatchValidator 활용 검토 |
| memory_results | ⚠️ 제한적 사용 | 현재는 유지 |
| execution_plan | ⚠️ 불명확 | 현재는 유지 |
```

- [ ] **Step 2: 커밋**

```bash
git add docs/architecture/AGENT_IO_DATAFLOW.md
git commit -m "docs: 에이전트 I/O 및 데이터 워크플로우 전수 문서화"
```

---

## Task 2: Emotion Agent 중간 저장 제거

**Files:**
- Modify: `src/agents/podcast/emotion.py:138-143`
- Modify: `tests/agents/test_emotion.py`

**배경:** Emotion Agent가 TIER 1 병렬 실행 중 `publisher.publish("emotion_logs", ...)` 를 직접 호출함. 이를 제거하고, emotion_vectors AgentState 필드를 routes/podcasts.py의 `_save_core_data()`에서 최종 저장하도록 이관.

- [ ] **Step 1: emotion.py 중간 저장 코드 확인**

```bash
grep -n "publish" src/agents/podcast/emotion.py
```

예상 출력: `138:        await self.publisher.publish("emotion_logs", emotion_data, ...)`

- [ ] **Step 2: 테스트 확인 (현재 publish 호출 테스트 여부)**

```bash
grep -n "publish" tests/agents/test_emotion.py
```

- [ ] **Step 3: 실패 테스트 작성 (publish 미호출 검증)**

`tests/agents/test_emotion.py`에 추가:

```python
@pytest.mark.asyncio
async def test_emotion_agent_does_not_publish_directly():
    """Emotion Agent는 더 이상 publish()를 직접 호출하지 않는다."""
    agent = EmotionAgent()
    state: AgentState = {
        "user_input": "요즘 너무 지쳐요",
        "user_id": "u_test",
        "session_id": "sess_test",
        "intent": {"intent_type": "stress_relief", "flags": {"urgency_level": "moderate"}},
    }
    with patch.object(agent, "publisher") as mock_pub:
        result = await agent.process(state)
        mock_pub.publish.assert_not_called()
    assert "emotion_vectors" in result
    assert "primary_emotion" in result["emotion_vectors"]
```

- [ ] **Step 4: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/test_emotion.py::test_emotion_agent_does_not_publish_directly -v
```

Expected: FAIL (현재 publish 호출하므로)

- [ ] **Step 5: emotion.py에서 publish 블록 제거**

`src/agents/podcast/emotion.py` L138-143 부근에서:

```python
# 제거 대상 (before)
await self.publisher.publish(
    RESOURCE_EMOTION_LOG,
    emotion_payload,
    user_id=state.get("user_id"),
    session_id=state.get("session_id"),
)
```

위 블록만 제거. `emotion_vectors` 반환은 그대로 유지.

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/agents/test_emotion.py -v
```

Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add src/agents/podcast/emotion.py tests/agents/test_emotion.py
git commit -m "refactor: Emotion Agent 중간 publish() 제거 — 최종 저장으로 이관"
```

---

## Task 3: Content Analyzer 중간 저장 제거

**Files:**
- Modify: `src/agents/podcast/content_analyzer.py:116-121`
- Modify: `tests/agents/test_content_analyzer.py`

**배경:** ContentAnalyzerAgent가 TIER 1 병렬 실행 중 `publisher.publish("content_analyses", ...)` 를 직접 호출함. 이를 제거.

- [ ] **Step 1: content_analyzer.py 중간 저장 코드 확인**

```bash
grep -n "publish" src/agents/podcast/content_analyzer.py
```

예상 출력: `116:        await self.publisher.publish("content_analyses", content_payload, ...)`

- [ ] **Step 2: 실패 테스트 작성**

`tests/agents/test_content_analyzer.py`에 추가:

```python
@pytest.mark.asyncio
async def test_content_analyzer_does_not_publish_directly():
    """Content Analyzer는 더 이상 publish()를 직접 호출하지 않는다."""
    agent = ContentAnalyzerAgent()
    state: AgentState = {
        "user_input": "업무 스트레스가 너무 심해요",
        "user_id": "u_test",
        "session_id": "sess_test",
        "intent": {"complexity_score": 0.6},
    }
    with patch.object(agent, "publisher") as mock_pub:
        result = await agent.process(state)
        mock_pub.publish.assert_not_called()
    assert "content_analysis" in result
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/test_content_analyzer.py::test_content_analyzer_does_not_publish_directly -v
```

Expected: FAIL

- [ ] **Step 4: content_analyzer.py에서 publish 블록 제거**

`src/agents/podcast/content_analyzer.py` L116-121 부근에서 publish 블록만 제거.

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/agents/test_content_analyzer.py -v
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/content_analyzer.py tests/agents/test_content_analyzer.py
git commit -m "refactor: Content Analyzer 중간 publish() 제거 — 최종 저장으로 이관"
```

---

## Task 4: _save_core_data()에 emotion_logs + content_analyses 통합

**Files:**
- Modify: `src/api/routes/podcasts.py` (_save_core_data 함수)
- Modify: `src/api/contracts.py` (저장 스키마 확인/추가)
- Modify: `src/api/backend_resources.py` (상수 확인)
- Modify: `tests/api/test_routes_podcasts.py`

**배경:** EmotionAgent와 ContentAnalyzer가 제거한 publish() 대신, TIER 4 완료 후 `_save_core_data()`에서 `AgentState`의 `emotion_vectors`와 `content_analysis`를 읽어 백엔드에 저장한다.

- [ ] **Step 1: 기존 _save_core_data 확인**

```bash
grep -n "RESOURCE_\|save_requests\|emotion\|content_anal" src/api/routes/podcasts.py | head -60
```

- [ ] **Step 2: contracts.py에서 EmotionLogData 확인**

```bash
grep -n "EmotionLog\|emotion_log\|ContentAnalysis\|content_analysis" src/api/contracts.py | head -30
```

필요시 다음 스키마 추가:

`src/api/contracts.py`에 추가:

```python
class EmotionLogSaveData(BaseModel):
    """emotion_logs 저장 페이로드"""
    episode_id: str
    mode: str = "podcast"
    primary_emotion: str
    intensity: float
    valence: float
    arousal: float
    secondary_emotions: list[str] = []
    tone_recommendation: str | None = None
    trace_id: str | None = None


class ContentAnalysisSaveData(BaseModel):
    """content_analyses 저장 페이로드"""
    episode_id: str
    mode: str = "podcast"
    main_theme: str
    sub_themes: list[str] = []
    emotional_journey: dict  # {opening, development, climax, closing}
    depth_level: str
    narrative_structure: str | None = None
    target_duration: int | None = None
    confidence: float | None = None
    trace_id: str | None = None
```

- [ ] **Step 3: backend_resources.py에서 상수 확인**

```bash
grep -n "RESOURCE_EMOTION\|RESOURCE_CONTENT\|TYPE_EMOTION\|TYPE_CONTENT" src/api/backend_resources.py
```

없는 상수가 있으면 추가:

```python
RESOURCE_EMOTION_LOG = "emotion_logs"
TYPE_EMOTION_LOG = "emotion_log"
RESOURCE_CONTENT_ANALYSIS = "content_analyses"
TYPE_CONTENT_ANALYSIS = "content_analysis"
```

- [ ] **Step 4: 실패 테스트 작성**

`tests/api/test_routes_podcasts.py`에 추가:

```python
@pytest.mark.asyncio
async def test_save_core_data_includes_emotion_and_content(mock_client):
    """_save_core_data가 emotion_logs와 content_analyses를 포함해 저장한다."""
    final_state = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": '{"episode_id": "ep_test", "episode_title": "테스트", "total_duration": 5, "segments": [], "key_insights": [], "themes": []}',
        "emotion_vectors": {
            "primary_emotion": "anxiety",
            "intensity": 0.7,
            "valence": -0.5,
            "arousal": 0.6,
            "secondary_emotions": ["stress"],
            "tone_recommendation": "empathetic",
        },
        "content_analysis": {
            "main_theme": "직장 스트레스",
            "emotional_journey": {"opening": "불안", "development": "심화", "climax": "전환", "closing": "완화"},
            "depth_level": "standard",
            "sub_themes": ["번아웃"],
            "target_duration": 5,
            "narrative_structure": "linear",
            "confidence": 0.85,
        },
        "visual_data": None,
        "intent": {"intent_type": "stress_relief", "complexity_score": 0.6},
        "safety_flags": {"status": "safe"},
        "validation_result": {"overall_score": 0.9},
        "iteration_count": 0,
    }
    saved_resources = []
    mock_client.save = AsyncMock(side_effect=lambda req: saved_resources.append(req.type) or {"success": True, "id": "test_id"})

    await _save_core_data(final_state, "trace_test", "corr_test", mock_client)

    assert TYPE_EMOTION_LOG in saved_resources, "emotion_log 저장 누락"
    assert TYPE_CONTENT_ANALYSIS in saved_resources, "content_analysis 저장 누락"
    assert TYPE_PODCAST_EPISODE in saved_resources, "podcast_episode 저장 누락"
```

- [ ] **Step 5: 테스트 실행 (실패 확인)**

```bash
pytest tests/api/test_routes_podcasts.py::test_save_core_data_includes_emotion_and_content -v
```

Expected: FAIL

- [ ] **Step 6: _save_core_data()에 emotion_logs + content_analyses 저장 추가**

`src/api/routes/podcasts.py`의 `_save_core_data()` 함수에 추가:

```python
# --- emotion_logs 저장 (기존 EmotionAgent publish 대체) ---
emotion_vectors = final_state.get("emotion_vectors", {})
if emotion_vectors and emotion_vectors.get("primary_emotion"):
    emotion_request = SaveRequest(
        user_id=user_id,
        session_id=session_id,
        type=TYPE_EMOTION_LOG,
        data={
            "episode_id": episode_data.episode_id,
            "mode": "podcast",
            "primary_emotion": emotion_vectors.get("primary_emotion", ""),
            "intensity": float(emotion_vectors.get("intensity", 0.5)),
            "valence": float(emotion_vectors.get("valence", 0.0)),
            "arousal": float(emotion_vectors.get("arousal", 0.5)),
            "secondary_emotions": emotion_vectors.get("secondary_emotions", []),
            "tone_recommendation": emotion_vectors.get("tone_recommendation"),
            "trace_id": trace_id,
        },
        timestamp=now,
    )
    save_requests.append(emotion_request)

# --- content_analyses 저장 (기존 ContentAnalyzer publish 대체) ---
content_analysis = final_state.get("content_analysis", {})
if content_analysis and content_analysis.get("main_theme"):
    content_request = SaveRequest(
        user_id=user_id,
        session_id=session_id,
        type=TYPE_CONTENT_ANALYSIS,
        data={
            "episode_id": episode_data.episode_id,
            "mode": "podcast",
            "main_theme": content_analysis.get("main_theme", ""),
            "sub_themes": content_analysis.get("sub_themes", []),
            "emotional_journey": content_analysis.get("emotional_journey", {}),
            "depth_level": content_analysis.get("depth_level", "standard"),
            "narrative_structure": content_analysis.get("narrative_structure"),
            "target_duration": content_analysis.get("target_duration"),
            "confidence": content_analysis.get("confidence"),
            "trace_id": trace_id,
        },
        timestamp=now,
    )
    save_requests.append(content_request)
```

`save_requests` 리스트에 추가 후 기존 `await asyncio.gather(*[client.save(r) for r in save_requests])` 패턴으로 일괄 저장.

- [ ] **Step 7: 테스트 통과 확인**

```bash
pytest tests/api/test_routes_podcasts.py -v
```

Expected: PASS

- [ ] **Step 8: 전체 관련 테스트 확인**

```bash
pytest tests/agents/test_emotion.py tests/agents/test_content_analyzer.py tests/api/test_routes_podcasts.py -v
```

Expected: 모두 PASS

- [ ] **Step 9: 커밋**

```bash
git add src/api/routes/podcasts.py src/api/contracts.py src/api/backend_resources.py tests/api/test_routes_podcasts.py
git commit -m "feat: _save_core_data에 emotion_logs + content_analyses 통합 저장"
```

---

## Task 5: AgentState에 재가공 에이전트 필드 추가

**Files:**
- Modify: `src/models/agent_state.py`

**주의:** `agent_state.py`는 3인 합의 Protected File. 이 Task는 신규 필드 추가만 수행하며 기존 필드 변경 없음.

- [ ] **Step 1: 현재 agent_state.py 확인**

```bash
grep -n "final_output\|memory_write\|reprocess" src/models/agent_state.py
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/models/test_agent_state.py`(또는 기존 state 테스트 파일)에 추가:

```python
def test_agent_state_has_reprocessing_fields():
    """AgentState에 재가공 에이전트 출력 필드가 정의되어야 한다."""
    from src.models.agent_state import AgentState
    state: AgentState = {
        "reprocessed_output": '{"episode_id": "ep_anon_test"}',
        "anonymization_report": {
            "original_pii_detected": ["phone_kr_mobile"],
            "anonymized_field_count": 2,
            "anonymization_confidence": 0.92,
            "manual_review_required": False,
            "flagged_segments": ["seg_001"],
            "changes_summary": {},
        },
    }
    # TypedDict는 런타임 타입 검사를 강제하지 않지만, 키 존재 자체를 확인
    assert "reprocessed_output" in AgentState.__annotations__
    assert "anonymization_report" in AgentState.__annotations__
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/models/test_agent_state.py::test_agent_state_has_reprocessing_fields -v
```

Expected: FAIL (필드 미정의)

- [ ] **Step 4: agent_state.py에 신규 필드 추가**

`src/models/agent_state.py`에서 `final_output` 이후에 추가:

```python
    # === 재가공 에이전트 (TIER 4 이후 비동기) ===
    reprocessed_output: str          # PodcastReprocessingAgent → 익명화된 final_output JSON 문자열
    anonymization_report: dict       # PodcastReprocessingAgent → 익명화 보고서
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/models/ -v
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/models/agent_state.py tests/models/test_agent_state.py
git commit -m "feat: AgentState에 재가공 에이전트 필드 추가 (reprocessed_output, anonymization_report)"
```

---

## Task 6: podcast_episodes_anonymized 테이블 마이그레이션

**Files:**
- Create: `dev/local_db/mysql/migrations/001_add_anonymized_table.sql`

- [ ] **Step 1: 기존 마이그레이션 파일 확인**

```bash
ls dev/local_db/mysql/
```

- [ ] **Step 2: 마이그레이션 파일 작성**

`dev/local_db/mysql/migrations/001_add_anonymized_table.sql`:

```sql
-- Migration 001: 익명화 에피소드 테이블 추가
-- Date: 2026-04-13
-- Purpose: PodcastReprocessingAgent 결과 저장

CREATE TABLE IF NOT EXISTS podcast_episodes_anonymized (
    anon_id          VARCHAR(64)   NOT NULL PRIMARY KEY,
    episode_id       VARCHAR(64)   NOT NULL COMMENT 'FK → podcast_episodes.episode_id',
    user_id          VARCHAR(64)   NOT NULL COMMENT 'FK → users.user_id',
    anonymized_script_json  TEXT   NOT NULL COMMENT '익명화된 PersonalizedScript JSON',
    anonymization_report_json TEXT COMMENT '익명화 보고서 JSON',
    anonymization_level ENUM('minimal', 'standard', 'strict') NOT NULL DEFAULT 'standard',
    anonymization_confidence FLOAT DEFAULT 0.0 COMMENT '0.0-1.0',
    manual_review_required BOOLEAN NOT NULL DEFAULT FALSE,
    review_status    ENUM('pending', 'approved', 'flagged') NOT NULL DEFAULT 'pending',
    trace_id         VARCHAR(64)   NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_episode_id (episode_id),
    INDEX idx_user_id (user_id),
    INDEX idx_review_status (review_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- [ ] **Step 3: 커밋**

```bash
git add dev/local_db/mysql/migrations/001_add_anonymized_table.sql
git commit -m "db: podcast_episodes_anonymized 테이블 마이그레이션 추가"
```

---

## Task 7: PodcastReprocessingAgent 구현

**Files:**
- Create: `src/agents/podcast/podcast_reprocessing.py`
- Create: `prompts/podcast/podcast_reprocessing.yaml`
- Create: `tests/agents/test_podcast_reprocessing.py`

- [ ] **Step 1: 테스트 파일 작성**

`tests/agents/test_podcast_reprocessing.py`:

```python
"""PodcastReprocessingAgent 테스트"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from src.agents.podcast.podcast_reprocessing import PodcastReprocessingAgent
from src.models.agent_state import AgentState


def _make_final_output(script_text: str = "홍길동은 회사에서 번아웃을 경험했습니다.") -> str:
    """테스트용 PersonalizedScript JSON 문자열 생성"""
    return json.dumps({
        "episode_id": "ep_test_001",
        "episode_title": "번아웃 극복하기",
        "total_duration": 5,
        "segments": [
            {
                "segment_id": "seg_001",
                "segment_type": "opening",
                "duration_minutes": 1,
                "script_text": script_text,
                "word_count": 10,
                "emotional_tone": "empathetic",
                "tts_markers": [],
            }
        ],
        "key_insights": ["개인정보 포함 인사이트"],
        "themes": ["번아웃"],
        "personalization_meta": {
            "applied_style": {},
            "adjusted_segments": [],
            "attitude_applied": "empathetic",
        },
    }, ensure_ascii=False)


@pytest.mark.asyncio
async def test_reprocessing_returns_required_fields():
    """PodcastReprocessingAgent는 reprocessed_output과 anonymization_report를 반환한다."""
    agent = PodcastReprocessingAgent()
    state: AgentState = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": _make_final_output(),
    }
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value={
        "reprocessed_script": _make_final_output("누군가는 회사에서 번아웃을 경험했습니다."),
        "changes": [{"segment_id": "seg_001", "type": "name_replacement", "original": "홍길동", "replacement": "누군가"}],
    })):
        result = await agent.process(state)

    assert "reprocessed_output" in result
    assert "anonymization_report" in result
    report = result["anonymization_report"]
    assert "anonymization_confidence" in report
    assert "flagged_segments" in report
    assert "anonymized_field_count" in report


@pytest.mark.asyncio
async def test_reprocessing_fallback_on_empty_final_output():
    """final_output이 없으면 원본 그대로 반환하고 에러 플래그를 포함한다."""
    agent = PodcastReprocessingAgent()
    state: AgentState = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": "",
    }
    result = await agent.process(state)

    assert "reprocessed_output" in result
    report = result["anonymization_report"]
    assert report.get("anonymization_confidence") == 0.0


@pytest.mark.asyncio
async def test_reprocessing_regex_pii_detected():
    """정규식 기반 PII(전화번호)가 감지되면 anonymization_report에 포함된다."""
    agent = PodcastReprocessingAgent()
    script_with_phone = _make_final_output("010-1234-5678로 연락 주세요.")
    state: AgentState = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": script_with_phone,
    }
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value={
        "reprocessed_script": _make_final_output("연락처로 연락 주세요."),
        "changes": [],
    })):
        result = await agent.process(state)

    report = result["anonymization_report"]
    assert "phone_kr_mobile" in report.get("original_pii_detected", [])
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/test_podcast_reprocessing.py -v
```

Expected: FAIL (모듈 미존재)

- [ ] **Step 3: 프롬프트 YAML 작성**

`prompts/podcast/podcast_reprocessing.yaml`:

```yaml
default_version: "1.0.0"

versions:
  "1.0.0":
    system: |
      당신은 멘탈케어 팟캐스트 스크립트 익명화 전문가입니다.
      사용자가 제공한 팟캐스트 스크립트에서 특정 개인을 식별할 수 있는 정보를 찾아
      자연스럽게 대체하는 역할을 합니다.

      익명화 대상:
      - 인물 이름 (한국어 이름, 닉네임): 자연스러운 대명사 또는 일반 호칭으로 대체
        예) "홍길동은" → "한 직장인은", "지현이가" → "동료가"
      - 지명/장소 (구체적 주소, 특정 카페/건물명): 일반화
        예) "강남역 카페 오디너리" → "한 카페"
      - 회사명/직함 (구체적 회사): 일반화
        예) "삼성전자의 김팀장" → "대기업의 팀장"
      - 의료/진단 정보: 완곡하게 표현
        예) "우울증 진단을 받았" → "정신건강 어려움을 경험했"

      반드시 지킬 것:
      1. 스크립트의 감정적 핵심과 교육적 메시지는 그대로 보존
      2. 자연스러운 한국어 문장 유지
      3. 세그먼트 구조(segment_id 등) 변경 금지
      4. 변경한 내용을 changes 배열에 명확히 기록

    user: |
      다음 팟캐스트 스크립트의 segments에서 개인식별정보를 익명화하세요.

      스크립트 JSON:
      {script_json}

      감지된 정규식 PII (이미 감지됨, 참고용):
      {detected_pii_list}

      출력 형식 (JSON):
      {{
        "reprocessed_script": {{
          ...원본과 동일한 구조, segments[].script_text만 수정...
        }},
        "changes": [
          {{
            "segment_id": "seg_xxx",
            "type": "name_replacement|location_replacement|company_replacement|medical_generalization",
            "original": "원본 텍스트 (10자 이내)",
            "replacement": "대체 텍스트"
          }}
        ]
      }}
```

- [ ] **Step 4: PodcastReprocessingAgent 구현**

`src/agents/podcast/podcast_reprocessing.py`:

```python
"""PodcastReprocessingAgent — 팟캐스트 스크립트 익명화 에이전트 (TIER 4 이후, 비동기)"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.output_sanitizer import sanitize_text
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)


class PodcastReprocessingAgent(BaseAgent):
    """최종 팟캐스트 스크립트에서 개인식별정보를 익명화한다."""

    def __init__(self) -> None:
        super().__init__(name="podcast_reprocessing", tier=4)

    async def process(self, state: AgentState) -> dict:
        """AgentState에서 final_output을 읽어 익명화 후 반환."""
        final_output = state.get("final_output", "")
        if not final_output:
            logger.warning("[PodcastReprocessing] final_output 없음, 폴백 반환")
            return self._fallback_result(final_output, reason="empty_final_output")

        try:
            script_data = json.loads(final_output)
        except json.JSONDecodeError as e:
            logger.error("[PodcastReprocessing] final_output JSON 파싱 실패: %s", e)
            return self._fallback_result(final_output, reason="json_parse_error")

        # Step 1: 정규식 기반 PII 감지 (output_sanitizer 재사용)
        detected_pii: list[str] = self._detect_pii_types(script_data)

        # Step 2: LLM 기반 익명화 (이름/지명/회사명 등 맥락 의존적 PII)
        try:
            llm_result = await self.call_llm_json(
                prompt_name="podcast_reprocessing",
                variables={
                    "script_json": json.dumps(script_data, ensure_ascii=False, indent=2),
                    "detected_pii_list": json.dumps(detected_pii, ensure_ascii=False),
                },
                version=self._get_prompt_version("podcast_reprocessing"),
            )
        except Exception as e:
            logger.error("[PodcastReprocessing] LLM 호출 실패: %s", e)
            return self._fallback_result(final_output, reason="llm_call_failed")

        reprocessed_script = llm_result.get("reprocessed_script", script_data)
        changes: list[dict] = llm_result.get("changes", [])

        # Step 3: 익명화 보고서 생성
        flagged_segment_ids = list({c.get("segment_id", "") for c in changes if c.get("segment_id")})
        report = {
            "original_pii_detected": detected_pii,
            "anonymized_field_count": len(changes),
            "anonymization_confidence": self._estimate_confidence(detected_pii, changes),
            "manual_review_required": len(detected_pii) > 5 or any(
                c.get("type") == "medical_generalization" for c in changes
            ),
            "flagged_segments": flagged_segment_ids,
            "changes_summary": {c["type"]: changes.count(c) for c in changes if "type" in c},
        }

        return {
            "reprocessed_output": json.dumps(reprocessed_script, ensure_ascii=False),
            "anonymization_report": report,
        }

    def _detect_pii_types(self, script_data: dict) -> list[str]:
        """정규식 기반 PII 타입 감지. output_sanitizer의 패턴 재사용."""
        all_text = " ".join(
            seg.get("script_text", "")
            for seg in script_data.get("segments", [])
        )
        # output_sanitizer의 공개 함수 활용
        from src.agents.shared.output_sanitizer import detect_pii_types
        return detect_pii_types(all_text)

    def _estimate_confidence(self, detected: list[str], changes: list[dict]) -> float:
        """익명화 신뢰도 추정 (0.0-1.0)."""
        if not detected and not changes:
            return 1.0  # PII 없음 = 완전 익명화
        if not changes:
            return 0.5  # 감지는 됐으나 변경 없음
        # 감지 건수 대비 변경 건수 비율
        return min(1.0, len(changes) / max(len(detected), 1))

    def _fallback_result(self, original: str, reason: str) -> dict:
        return {
            "reprocessed_output": original,
            "anonymization_report": {
                "original_pii_detected": [],
                "anonymized_field_count": 0,
                "anonymization_confidence": 0.0,
                "manual_review_required": True,
                "flagged_segments": [],
                "changes_summary": {"error": reason},
            },
        }
```

- [ ] **Step 5: output_sanitizer에 detect_pii_types 함수 확인/추가**

```bash
grep -n "detect_pii_types\|def detect" src/agents/shared/output_sanitizer.py
```

없으면 추가:

```python
def detect_pii_types(text: str) -> list[str]:
    """텍스트에서 감지된 PII 타입 목록 반환 (마스킹 없이 타입만)."""
    detected = []
    for pattern_name, pattern in _PII_PATTERNS.items():
        if pattern.search(text):
            detected.append(pattern_name)
    return detected
```

(`_PII_PATTERNS`는 기존 sanitize 함수에서 사용하는 패턴 딕셔너리. 기존 코드 구조에 맞게 조정.)

- [ ] **Step 6: 테스트 실행 (통과 확인)**

```bash
pytest tests/agents/test_podcast_reprocessing.py -v
```

Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add src/agents/podcast/podcast_reprocessing.py prompts/podcast/podcast_reprocessing.yaml tests/agents/test_podcast_reprocessing.py
git commit -m "feat: PodcastReprocessingAgent 구현 — 팟캐스트 스크립트 익명화"
```

---

## Task 8: workflow.py에 재가공 에이전트 등록

**Files:**
- Modify: `src/graph/workflow.py`

**주의:** `workflow.py`는 3인 합의 Protected File. 신규 노드 등록만 수행.

- [ ] **Step 1: 현재 비동기 후처리 노드 확인**

```bash
grep -n "async_post\|learning\|memory_write" src/graph/workflow.py | head -30
```

- [ ] **Step 2: 현재 async_post_processing_node 확인**

```bash
grep -n -A 20 "def async_post" src/graph/workflow.py | head -40
```

- [ ] **Step 3: 실패 테스트 작성**

`tests/graph/test_workflow.py`(또는 기존 워크플로우 테스트)에 추가:

```python
def test_workflow_includes_reprocessing_node():
    """워크플로우에 podcast_reprocessing 노드가 등록되어야 한다."""
    from src.graph.workflow import app  # 컴파일된 LangGraph 앱
    # LangGraph Graph 노드 목록 확인
    node_names = list(app.nodes.keys()) if hasattr(app, 'nodes') else []
    assert "podcast_reprocessing" in node_names, f"podcast_reprocessing 노드 미등록. 현재 노드: {node_names}"
```

- [ ] **Step 4: 테스트 실행 (실패 확인)**

```bash
pytest tests/graph/test_workflow.py::test_workflow_includes_reprocessing_node -v
```

Expected: FAIL

- [ ] **Step 5: workflow.py에 재가공 노드 등록**

```python
# 1. import 추가
from src.agents.podcast.podcast_reprocessing import PodcastReprocessingAgent

# 2. 노드 함수 추가 (기존 async_post_processing_node 근처)
async def podcast_reprocessing_node(state: AgentState) -> dict[str, Any]:
    """요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = PodcastReprocessingAgent()
    return await agent.process(state)

# 3. 노드 등록
graph.add_node("podcast_reprocessing", podcast_reprocessing_node)

# 4. async_post_processing_node에서 재가공 에이전트 호출 추가
# 기존 Learning/Memory 작업과 함께 asyncio.gather로 병렬 실행
# (기존 async_post 로직에 reprocessing 호출 통합)
```

비동기 후처리 노드가 Learning과 Memory를 병렬로 실행하는 구조라면:

```python
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    tasks = [
        learning_node_inner(state),
        memory_write_node_inner(state),
        podcast_reprocessing_node(state),  # 신규 추가
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged = {}
    for r in results:
        if isinstance(r, dict):
            merged.update(r)
    return merged
```

(실제 구조에 맞게 조정. 기존 비동기 후처리 패턴을 따름.)

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/graph/test_workflow.py -v
```

Expected: PASS

- [ ] **Step 7: 전체 테스트**

```bash
pytest tests/ -v --ignore=tests/live -x
```

Expected: 모두 PASS

- [ ] **Step 8: 커밋**

```bash
git add src/graph/workflow.py tests/graph/test_workflow.py
git commit -m "feat: workflow.py에 podcast_reprocessing 노드 등록 — 비동기 후처리 통합"
```

---

## Task 9: 재가공 결과 백엔드 저장 연결

**Files:**
- Modify: `src/api/routes/podcasts.py` (async_post 또는 비동기 후처리 경로)
- Modify: `src/api/backend_resources.py`

- [ ] **Step 1: 현재 비동기 저장 경로 확인**

```bash
grep -n "async_post\|reprocess\|anonymize" src/api/routes/podcasts.py | head -20
```

- [ ] **Step 2: backend_resources.py에 익명화 상수 추가**

`src/api/backend_resources.py`:

```python
RESOURCE_PODCAST_EPISODE_ANONYMIZED = "podcast_episodes_anonymized"
TYPE_PODCAST_EPISODE_ANONYMIZED = "podcast_episode_anonymized"
```

- [ ] **Step 3: 실패 테스트 작성**

`tests/api/test_routes_podcasts.py`에 추가:

```python
@pytest.mark.asyncio
async def test_async_post_saves_reprocessed_episode(mock_client):
    """비동기 후처리에서 재가공된 에피소드를 저장한다."""
    final_state = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": '{"episode_id": "ep_test"}',
        "reprocessed_output": '{"episode_id": "ep_test", "segments": []}',
        "anonymization_report": {
            "original_pii_detected": ["phone_kr_mobile"],
            "anonymized_field_count": 1,
            "anonymization_confidence": 0.9,
            "manual_review_required": False,
            "flagged_segments": [],
            "changes_summary": {},
        },
    }
    saved_types = []
    mock_client.save = AsyncMock(
        side_effect=lambda req: saved_types.append(req.type) or {"success": True, "id": "id"}
    )
    await _async_post_save(final_state, mock_client)
    assert TYPE_PODCAST_EPISODE_ANONYMIZED in saved_types
```

- [ ] **Step 4: 비동기 후처리 저장 로직 추가**

`src/api/routes/podcasts.py`의 비동기 후처리 저장 함수에:

```python
# 재가공 결과 저장
reprocessed_output = final_state.get("reprocessed_output")
anon_report = final_state.get("anonymization_report", {})
if reprocessed_output and reprocessed_output != final_state.get("final_output"):
    anon_request = SaveRequest(
        user_id=final_state.get("user_id", ""),
        session_id=final_state.get("session_id", ""),
        type=TYPE_PODCAST_EPISODE_ANONYMIZED,
        data={
            "anon_id": f"anon_{episode_id}",
            "episode_id": episode_id,
            "user_id": final_state.get("user_id", ""),
            "anonymized_script_json": reprocessed_output,
            "anonymization_report_json": json.dumps(anon_report),
            "anonymization_level": "standard",
            "anonymization_confidence": anon_report.get("anonymization_confidence", 0.0),
            "manual_review_required": anon_report.get("manual_review_required", False),
            "review_status": "pending",
        },
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
    await client.save(anon_request)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/api/test_routes_podcasts.py -v
```

Expected: PASS

- [ ] **Step 6: 전체 테스트 실행**

```bash
pytest tests/ -v --ignore=tests/live -x
```

Expected: PASS

- [ ] **Step 7: 커밋**

```bash
git add src/api/routes/podcasts.py src/api/backend_resources.py tests/api/test_routes_podcasts.py
git commit -m "feat: 재가공 에피소드 백엔드 저장 연결 (podcast_episodes_anonymized)"
```

---

## Task 10: 문서 최종 갱신

**Files:**
- Modify: `docs/architecture/AGENT_OUTPUT_CONTRACT.md`
- Modify: `docs/superpowers/PLAN_INDEX.md`

- [ ] **Step 1: AGENT_OUTPUT_CONTRACT.md 갱신**

주요 변경사항 반영:
- 중간 저장 제거 (Emotion, ContentAnalyzer publish 제거)
- 단일 최종 저장 구조 설명
- PodcastReprocessingAgent 추가
- emotional_journey 4-key (climax/closing) 반영

- [ ] **Step 2: PLAN_INDEX.md에 Plan #25 등록**

```markdown
| #25 | [Agent I/O 통합 및 재가공 에이전트](plans/2026-04-13-agent-io-consolidation.md) | 중간 저장 제거, 단일 저장 통합, 익명화 에이전트 | 🔲 구현 대기 |
```

- [ ] **Step 3: 커밋**

```bash
git add docs/architecture/AGENT_OUTPUT_CONTRACT.md docs/superpowers/PLAN_INDEX.md
git commit -m "docs: AGENT_OUTPUT_CONTRACT 갱신 + PLAN_INDEX #25 등록"
```

---

## 연쇄 영향 체크리스트

| 항목 | 영향 | 확인 필요 |
|------|------|---------|
| Emotion Agent publisher 제거 | emotion_logs 저장 경로 변경 | `_save_core_data` 에서 누락 없이 저장되는지 E2E 확인 |
| CA publisher 제거 | content_analyses 저장 경로 변경 | 동일 |
| AgentState 신규 필드 | LangGraph 상태 병합 | total=False이므로 안전 |
| workflow.py 수정 | Protected File | 3인 합의 후 PR |
| agent_state.py 수정 | Protected File | 3인 합의 후 PR |
| output_sanitizer 추가 | detect_pii_types 신규 함수 | 기존 테스트 회귀 확인 |

## 미구현 범위 (이 계획 외)

다음 항목은 이 계획에서 **의도적으로 제외**함:

- `knowledge_results`, `risk_level`, `risk_score` 미사용 필드 정리 — 향후 활용 계획 확정 후 별도 계획서 작성
- DB 불일치 컬럼(`turn_count`, `turn_id`) 제거 — 대화모드 제외 결정과 연계, 현재 유지
- Plan #22 (에이전트 출력 감사 CA-1~CA-3, SP-1~2 등) — 별도 브랜치에서 진행 중
- NER 모델 통합 (Pororo/KoBERT) — Phase 2 (중기), 이 계획에서는 LLM 기반으로 대체

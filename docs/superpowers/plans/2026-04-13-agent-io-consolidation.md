# Agent I/O 문서화 및 재가공 에이전트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에이전트 전체 I/O 및 데이터 워크플로우 문서화 + 팟캐스트 재가공 에이전트(익명화) 신규 구현.

**Architecture:** 기존 저장 API(publisher.publish(), BackendClient.save(), graph_nodes PUT)는 **변경 없이 유지**. 백엔드 프론트엔드용 테이블(`podcasts`, `mind_frequencies`)에 맞춰 ingest API 호출부만 정합. PodcastReprocessingAgent/EpisodeSummaryAgent는 백엔드 테이블 미확보로 **보류**.

**Tech Stack:** Python 3.11+, LangGraph, FastAPI, MySQL (BackendClient), output_sanitizer(기존 재사용)

---

## ✅ 구현 완료 요약 (2026-04-13)

> Task 8 + Task 9(A/B) 구현 완료. Task 7(AGENT_IO_DATAFLOW.md 추출) + Task 1~6, 11(보류) 미완.

### 완료된 커밋

| 커밋 | 내용 |
|------|------|
| `e016e15` | feat: ingest_podcast_episodes() 백엔드 podcasts 테이블 정합 + 감정 컬럼 추가 |
| `0899c22` | feat: init.sql podcast_episodes 신규 컬럼 추가 + podcast_segments 테이블 제거 |
| `34df842` | feat: init.sql content_analyses + user_summaries 테이블 추가 |
| `ebef350` | feat: ContentAnalyzer user_summary 별도 저장 추가 + BackendClient.ingest_user_summary() |
| `831f58f` | fix: ingest_mind_frequencies 로깅 수정 — 성공 INFO + 실패 ERROR + content_analyzer 중복 except 제거 |
| `4ccfc4b` | fix: RESOURCE_MIND_FREQUENCIES 경로 수정 — tickets/mind-frequencies → mind-frequencies |
| `bcf7509` | test: TestWithLLM 클래스에 @pytest.mark.live 마커 추가 |

### 구현 중 발생한 수정사항 (이력)

| 수정 | 원인 | 결과 |
|------|------|------|
| `ingest_podcast_episodes()` 파라미터 `user_id` 추가 → **취소** | 초기 계획에 user_id 포함. 백엔드 확인 결과 `id`, `user_id`, `created_at` 3개는 백엔드 자동 채움 — AI 서버 전송 불필요 | `user_id` 파라미터 제거, 3개 파라미터(`session_id`, `image_url`, `text`)로 확정 |
| `BACKEND_API_URL /api/v1` 이슈 노트 추가 → **취소** | `/greenroom/ingest/ai`와 `/api/v1` 엔드포인트를 혼용 오인. 두 경로는 완전히 독립된 별개 엔드포인트 | 관련 노트 전부 제거 |
| `RESOURCE_MIND_FREQUENCIES = "tickets/mind-frequencies"` → `"mind-frequencies"` | 백엔드 실제 경로 확인 결과 prefix `tickets/` 없음 | `backend_resources.py` + `client.py` docstring 수정 (커밋 `4ccfc4b`) |
| `TestWithLLM` 클래스에 `@pytest.mark.live` 마커 누락 | 마커 없이 회귀 테스트 실행 시 실제 LLM 호출 발생 — Ollama 없는 환경에서 3개 에러 | `test_script_personalizer.py` 클래스에 마커 추가 (커밋 `bcf7509`) |
| 회귀 테스트 명령 `--ignore=tests/live` → `-m "not live"` 로 변경 | `--ignore=tests/live`만으로는 다른 디렉토리의 `@pytest.mark.live` 테스트 필터 불가 | 모든 회귀 확인 명령에 `-m "not live"` 추가 |

### 테스트 결과

```
512 passed, 0 errors  (live 테스트 제외: pytest tests/ -m "not live")
```

---

## ⚠️ 핵심 통신 원칙 (변경 불가)

```
Frontend ─────────────────────── Backend (app-3:8080)
          REST API 요청/응답               ↕  HTTP API
                                  AI 서버 (app-2:8000)
```

- **AI 서버는 Frontend와 절대 직접 통신하지 않는다.**
- AI 서버 → Backend: `BackendClient.save()` (HTTP POST) — **API 통신만** 사용
- Backend → Frontend: REST GET API — 데이터 조회 제공 (Frontend 요청 기반)
- **세션 격리**: 모든 저장/조회는 `user_id` + `session_id` 조합으로 라우팅. 다른 사용자 데이터 섞임 방지.

> ℹ️ ContentAnalyzer 1차 로딩 흐름:
> AI 서버 → `BackendClient.save()` → Backend에 `user_summary` API 저장 → Frontend는 Backend API 폴링 또는 Backend의 별도 알림 방식으로 수신 (Backend 팀 구현 담당)

---

## 중요: 변경하지 않는 범위

| 항목 | 이유 |
|------|------|
| GoT→Neo4j 저장 (`_save_graph_data()`) | PR #50, #51 완료, 테스트 통과 |
| graph_nodes 누적 저장 (`publish_graph_to_rdb()`) | PR #88, Mode A 완료, BE 3차 E2E 검증 완료 (`tests/api/test_graph_cumulative.py` 27개 통과) |

## 이번 계획에서 변경하는 범위

| 항목 | 변경 내용 | Task |
|------|---------|------|
| `ingest_podcast_episodes()` **정합** | 백엔드 `podcasts` 테이블(`session_id, image_url, text`)에 맞춰 시그니처·호출부 전면 수정 | Task 8 |
| `_save_core_data()` 확장 | (1) 감정 컬럼(`primary_emotion`, `secondary_emotions`) 추가, (2) `ingest_podcast_episodes()` 호출 인자 정합 | Task 8 |
| `podcast_episodes` 테이블 | `script_text`, `tts_markers_json`, `primary_emotion`, `secondary_emotions` 컬럼 추가 — **init.sql 직접 수정** | Task 8 |
| `podcast_segments` 테이블 | **init.sql에서 테이블 정의 제거** — v3.0에서 segments 구조 폐기 | Task 8 |
| ContentAnalyzerAgent 신규 저장 추가 | **user_summary (keywords·summary) 별도 전송 추가 — 기존 publisher 유지** | Task 9 |
| `content_analyses` + `user_summaries` 테이블 추가 | init.sql에 두 테이블 정의 추가 (방안 A 확정) | Task 9 |
| `ingest_mind_frequencies()` 로깅 수정 | 성공 로그 추가 + 에러 로그 WARNING→ERROR 격상 + `content_analyzer.py` 중복 try/except 제거 | Task 9 |

> ✅ EmotionAgent `publisher.publish()` — **변경 없음 (유지)**. emotion_logs 상세 감정 기록용 유지.
> ✅ `_save_core_data()` 자동 동기 저장 — **변경 없음** (확장만). 파이프라인 완료 후 자동 저장 유지.
> ⚠️ `ingest_mind_frequencies()` — **로깅 수정 필요**. 시그니처·경로는 호환이나 성공 시 로그 없음 + 실패 시 WARNING(필터 가능) → 데이터 미적재 시 원인 파악 불가.

### ⛔ 보류 항목 (백엔드 테이블 미확보)

| 항목 | 사유 |
|------|------|
| PodcastReprocessingAgent (구 Task 1,2,3,4,6) | `podcast_episodes_anonymized` 테이블 백엔드에 없음 |
| EpisodeSummaryAgent (구 Task 5,11) | `episode_summaries` 테이블 백엔드에 없음 |
| AgentState 재가공/요약 필드 (구 Task 1) | 위 에이전트 보류에 따라 |
| workflow.py `episode_summary_node` (구 Task 5) | 위 에이전트 보류에 따라 |


### UX 로딩 플로우 (2단계 구조)

```
사용자 입력 → Frontend: Backend API 요청
    ↓
[TIER 1 병렬 실행 중...]
    ↓
ContentAnalyzer 완료
    → publisher.publish() → BackendClient.save() → Backend API 저장
    → ✅ 1차 로딩 완료 트리거 (Frontend가 Backend를 폴링하거나 Backend 알림 — Backend 담당)
    → 프론트: 안내화면 표시 (화면 1)
    ↓
[TIER 2~4 계속 실행 중... 사용자는 화면 1을 보고 있음]
    ↓
사용자: "다음" 버튼 클릭 → 2차 로딩 시작
    ↓
TIER 4 완료 → _save_core_data() → BackendClient.save() → Backend API 저장
    → ✅ 2차 로딩 완료 트리거 (Frontend가 Backend GET API 조회 — Backend 담당)
    → 프론트: 에피소드 결과 화면 (화면 2)
```

### 화면별 저장 구조

| 화면 | 필요 데이터 | 저장 위치 (백엔드 테이블) | 타이밍 |
|:----:|-----------|---------|--------|
| **화면 1 (1차 로딩 후)** | keywords, description | `mind_frequencies` (ingest API) | TIER 1 ContentAnalyzer 완료 직후 ⚡ |
| **화면 2 (2차 로딩 후)** | 이미지, 에피소드 본문 | `podcasts` (ingest API) | TIER 4 완료 후 |
| *(내부)* | 상세 메타 (타이틀, 감정, 검증점수 등) | `podcast_metadata` (기존 save API) | TIER 4 완료 후 |

> ℹ️ 백엔드 프론트엔드용 테이블은 `mind_frequencies`와 `podcasts` 두 개. 기존 `podcast_metadata`, `emotion_logs` 등은 내부 분석용으로 기존 save API 유지.

---

## Part 1: 에이전트 I/O 및 데이터 워크플로우 현황

> 이 섹션은 프론트엔드에서 사용하는 데이터 컬럼 정리의 기준 자료입니다.

### 1-1. 파이프라인 전체 데이터 흐름

> **색상 범례:** 🟣 TIER 0 &nbsp;|&nbsp; 🔵 TIER 1 병렬 &nbsp;|&nbsp; 🟢 TIER 2 병렬 &nbsp;|&nbsp; 🟡 TIER 3 &nbsp;|&nbsp; 🟠 TIER 4 &nbsp;|&nbsp; ⬛ 비동기 후처리 &nbsp;|&nbsp; 💾 저장

---

📥 **사용자 입력** (`PodcastRequest`) — `situation` · `thought` · `action` · `colleague_reaction`

⚙️ **AgentState 초기화** — `user_input` · `user_id` · `session_id` · `mode="podcast"`

---

### 🟣 TIER 0 — Intent Classifier

- **읽기:** `user_input` · `user_id` · `session_id`
- **쓰기:** `intent` · `risk_level` · `risk_score` · `safety_flags` (1차 초기값)

---

### 🔵 TIER 1 — 병렬 Fan-out

| 에이전트 | 읽기 | 쓰기 | 저장 |
|:-------:|------|------|:----:|
| **Safety** | `user_input` · `intent.flags.risk_flag` | `safety_flags` · `risk_level` · `risk_score` · `next_step`? | — |
| **Emotion** | `user_input` · `intent` | `emotion_vectors` | 💾 `emotion_logs` *(유지)* |
| **Content Analyzer** | `user_input` · `intent` | `content_analysis` | 💾 `content_analyses` (기존 전체 저장 유지) + 💾 `user_summaries` (user_summary 추가 저장, Task 9) |
| **Podcast Reasoning** | `user_input` · `user_id` · `intent` · `execution_plan` · `session_id` | `reasoning_result` · `memory_results`? · `knowledge_results`? | 💾 Neo4j + `graph_nodes` |

> ⚡ **CRISIS 선점:** Safety가 `next_step="crisis_response"` 설정 → 🚨 Crisis Response 즉시 출력, 이하 TIER 전체 스킵

---

### 🟢 TIER 2 — 병렬

| 에이전트 | 읽기 | 쓰기 |
|:-------:|------|------|
| **Script Generator** | `safety_flags` · `content_analysis` · `reasoning_result` · `validation_result` (재시도 시) | `script_draft` |
| **Visualization** | `emotion_vectors` · `content_analysis` · `user_id` · `mode` | `visual_data` |

---

### 🟡 TIER 3 — Batch Validator

- **읽기:** `script_draft` · `content_analysis` · `reasoning_result` · `safety_flags` · `emotion_vectors` · `iteration_count`
- **쓰기:** `validation_result`

> 🔄 **verdict 판정:** `FAIL` + 재시도 가능 → TIER 2 재시도 (최대 2회) &nbsp;|&nbsp; `PASS` / 강제 통과 → TIER 4 진행

---

### 🟠 TIER 4 — Script Personalizer

- **읽기:** `user_id` · `script_draft` · `content_analysis` (emotional_journey) · `session_id`
- **쓰기:** `final_output` · `memory_write` · `memory_text` · `memory_metadata`

---

💾 **`_save_core_data()`** (동기 — 응답 반환 전) → `podcast_episodes`(+감정컬럼) + `visualizations` *(Task 8 확장)*

📤 **`SlimPodcastResponse`** → `episode_id` · `session_id` · `safety_alert`

---

### 프론트엔드 결과 표시 (파이프라인 완료 후)

> `_save_core_data()` 완료 → Backend에 API 저장 → Frontend는 Backend GET API로 상세 조회 후 렌더링

| 화면 요소 | 조회 방법 | 필드 |
|---------|---------|------|
| **타이틀** | `GET /podcast_episodes/{episode_id}` | `episode_title` |
| **감정 타이틀 2~3개** | `GET /podcast_episodes/{episode_id}` | `primary_emotion` + `secondary_emotions[0:2]` |
| **에피소드 텍스트** | `GET /podcast_episodes/{episode_id}` | `script_text` |
| **이미지** | `GET /podcast_episodes/{episode_id}` | `cover_image_url` |

> ℹ️ **차후 화면 (별도 구현):** 에피소드 목록 — 생성 일자 · 타이틀 · 감정 타이틀 · `episode_summary` (EpisodeSummaryAgent 생성분)

---

### ⬛ 비동기 후처리

| 에이전트 | 읽기 | 쓰기 | 저장 |
|:-------:|------|------|:----:|
| **EpisodeSummaryAgent** ★신규 (보류) | `final_output` · `user_id` · `session_id` | `episode_summary` | 💾 `episode_summaries` |
| **Learning Agent** | 전체 state | — | 💾 `learning_patterns` |
| **Episode Memory** | (`memory_write=True` 시만) | — | 💾 Pinecone `mem-podcast-episode` |

> ℹ️ **PodcastReprocessingAgent** — 메인 파이프라인 비동기 후처리와 **별개**. Backend에서 사용자 공유 동의 데이터를 수신했을 때만 별도로 트리거되는 독립 에이전트. 별도 엔드포인트(`POST /api/episodes/{id}/reprocess`) 또는 Backend 이벤트로 호출됨.

### 1-2. 프론트엔드 로딩 플로우 (참고 — Backend 팀 담당)

> **AI 서버 역할**: `BackendClient.save()` (HTTP POST)로 데이터를 Backend에 저장하는 것이 전부.
> 아래 흐름은 Backend가 Frontend에 제공하는 알림 흐름으로, AI 서버와는 무관하다. Backend 팀 담당.

**1차 로딩 트리거 (AI 서버 → Backend API 저장)**

```
ContentAnalyzerAgent 완료 (TIER 1)
    → publisher.publish(validated_analysis) → BackendClient.save() → POST /api/content_analyses   ← 기존 유지
    → publisher.publish(user_summary)       → BackendClient.save() → POST /api/user_summaries      ← 신규 추가 (Task 9)
    → ✅ Backend가 user_summaries 수신 후 1차 로딩 완료 처리 (Frontend 알림 방식은 Backend 팀 결정)
```

**2차 로딩 트리거 (AI 서버 → Backend API 저장)**

```
파이프라인 TIER 4 완료
    → _save_core_data() → BackendClient.save() → POST /api/podcast_metadata + ingest_podcast_episodes
    → ✅ Backend가 수신 후 2차 로딩 완료 처리 (Frontend 알림 방식은 Backend 팀 결정)
```

> ℹ️ **Frontend 알림 방식** (SSE / WebSocket / 폴링 등)은 Backend 팀이 결정한다.
> AI 서버는 Backend에 HTTP POST로 저장할 뿐이며, Frontend와 직접 통신하지 않는다.

**2차 로딩 완료 후 — Frontend가 Backend GET API 호출**

| 화면 | Backend GET API | 조회 데이터 |
|------|---------------|-----------|
| **화면 2** | `GET /podcast_episodes/{episode_id}?user_id=` | 타이틀 · 감정 키워드 · 텍스트 · 이미지 |
| 그래프 화면 | `GET /graph_nodes?user_id=` | 누적 EMA 그래프 |

### 1-3. 에이전트별 입출력 데이터 상세 명세

---

#### 🟣 Intent Classifier `TIER 0`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| user_input | state.get("user_input", "") | 분류 대상 텍스트 |
| user_id | state.get("user_id", "anonymous") | 사용자 식별 |
| session_id | state.get("session_id", "session_0") | 세션 추적 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| intent | dict | intent_type, complexity_score, detected_entities, flags, reasoning, trace_id, classified_at |
| risk_level | int | 0~4 (0=안전, 4=위기) |
| risk_score | float | 0.0~1.0 |
| safety_flags | dict | risk_detected, details (1차 초기값 — Safety가 최종 덮어씀) |

**intent 상세 구조:**
```python
{
  "intent_type": str,               # "podcast_request" | "emotional_support" | "crisis" | "casual_chat"
  "complexity_score": float,         # 0.0~1.0
  "detected_entities": {
    "emotions": list[str],            # ["불안", "피로"]
    "topics": list[str],              # ["직장", "가족"]
    "persons": list[str]              # []
  },
  "flags": {
    "requires_memory": bool,
    "requires_knowledge": bool,
    "visualization_hint": bool,
    "urgency_level": int,             # 0~3
    "risk_flag": bool                 # 위기 상황 플래그
  },
  "reasoning": str,
  "trace_id": str,
  "classified_at": str               # ISO datetime
}
```

**폴백 반환:**
```python
{
  "intent_type": DEFAULT_INTENT,
  "complexity_score": DEFAULT_COMPLEXITY_SCORE,
  "detected_entities": {"emotions": [], "topics": [], "persons": []},
  "flags": {"requires_memory": False, "requires_knowledge": False,
            "visualization_hint": False, "urgency_level": 0},
  "reasoning": "Fallback to rule-based classification due to LLM error"
}
```

---

#### 🔵 Emotion Agent `TIER 1`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| user_input | state.get("user_input", "") | 감정 분석 대상 |
| intent | state.get("intent", {}) | intent_type, flags.urgency_level, detected_entities.emotions (4개 핵심 필드만 추출) |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| emotion_vectors | dict | 7개 필드 |

**emotion_vectors 상세:**
```python
{
  "primary_emotion": str,              # "anxiety" | "sadness" | "joy" | "neutral" 등
  "intensity": float,                   # clamp(0.0, 1.0), 기본값 0.3
  "valence": float,                     # clamp(-1.0, 1.0), 기본값 0.0
  "arousal": float,                     # clamp(0.0, 1.0), 기본값 0.3
  "secondary_emotions": list[str],      # list 타입 보장
  "tone_recommendation": str,           # "supportive_neutral" | "empathetic" 등
  "emotional_journey_hint": list[str]   # ["공감", "정리", "실행 가능한 한 가지", "마무리"]
}
```

**publisher.publish() 저장 (L138~143) — 변경 없음 (유지)**
```python
publisher.publish(
  resource="emotion_logs",       # RESOURCE_EMOTION_LOG
  data=emotion_vectors,          # 7개 필드 전체 — 상세 감정 기록용
  user_id=user_id,
  session_id=session_id
)
```
> ✅ **유지 이유:** emotion_logs는 상세 감정 로그 보관용. 화면용 감정 키워드(`primary_emotion`, `secondary_emotions[0:2]`)는 Task 8에서 `_save_core_data()`를 통해 `podcast_episodes`에 별도 저장.

**폴백 반환:**
```python
{
  "primary_emotion": str,   # 감지된 감정 또는 "neutral"
  "intensity": float,
  "valence": float,
  "arousal": float,
  "secondary_emotions": [],
  "tone_recommendation": "supportive_neutral",
  "emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"]
}
```

---

#### 🔵 Content Analyzer `TIER 1`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| user_input | state.get("user_input", "") | 콘텐츠 분석 대상 |
| intent | state.get("intent", {}) | complexity_score → depth_level 사전 결정 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| content_analysis | dict | 10개 필드 |

**content_analysis 상세:**
```python
{
  "user_summary": {              # ⚠️ pass-through (코드 검증 없음, Plan #22 CA-1)
    "keywords": list[str],       #   사용자 입력에서 추출한 3~5개 핵심 키워드 (2~4글자)
    "summary": str               #   이 사용자만의 구체적 경험 공감 + 방향 1~2문장
  },
  "key_messages": list[str],     # ⚠️ pass-through (코드 검증 없음, Plan #22 CA-1)
                                 #   이 사용자에게만 해당하는 구체적 행동 제안 3~5개
  "main_theme": str,             # 최대 100자, 한국어 (_validate_and_correct 보정)
  "sub_themes": list[str],       # 3~5개 범위 보정 (_validate_and_correct)
  "target_duration": int,        # 3~5분 범위 고정 (_validate_and_correct)
  "narrative_structure": str,    # "personal_story"|"expert_qa"|"reflection"|"comparative"
  "depth_level": str,            # "light"|"moderate"|"deep" (코드가 complexity_score로 결정)
  "emotional_journey": dict,     # 4-key: opening/development/climax/closing (CA v2.2.0 이후)
  "confidence": float,           # 0.0~1.0 (CA v2.2.0 이후)
  "error": str                   # 에러 시만 포함
}
```

> ⚠️ **CA-1 이슈 (Plan #22 Task 4):** `user_summary`, `key_messages`는 LLM 출력 pass-through. `_validate_and_correct()`에서 타입·구조 검증 미적용 상태.

**publisher.publish() 저장 (L114~121) — 변경 없음 (유지)**

```python
# [현재 코드 — 유지]
await publisher.publish(
    resource=RESOURCE_CONTENT_ANALYSIS,
    data=validated_analysis,          # 전체 분석 결과 — 변경 없음
    user_id=state.get("user_id", ""),
    session_id=session_id,
)
```

**user_summary 별도 저장 추가 (Task 9 신규)**

```python
# [Task 9 추가 — ingest_mind_frequencies 호출 이후에 추가]
user_summary = validated_analysis.get("user_summary", {})
await backend_client.ingest_user_summary(
    session_id=session_id,
    keywords=user_summary.get("keywords", []),    # list[str] → 백엔드 콤마 join
    description=user_summary.get("summary", ""),  # summary → description 매핑
)
```

> ✏️ **추가 이유:** `user_summaries` 테이블은 **화면 1(안내화면) 전용 조기 저장**으로 활용. TIER 1이 완료되는 시점에 `user_summary`를 즉시 저장하여 Backend가 Frontend에 1차 로딩 완료를 알릴 수 있게 함. 기존 `content_analyses` 전체 저장은 내부 분석용으로 유지.

**폴백 반환:**
```python
{
  "main_theme": "",
  "sub_themes": [],
  "emotional_journey": {},
  "depth_level": "light",
  "error": "user_input_missing"
  # user_summary, key_messages: LLM 미호출이므로 폴백에 미포함
}
```

---

#### 🔵 Safety Agent `TIER 1`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| user_input | state.get("user_input", "") | 안전성 평가 대상 |
| intent | state.get("intent", {}).get("flags", {}).get("risk_flag", False) | Intent Classifier 1차 감지 플래그만 추출 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| safety_flags | dict | LLM 전체 결과 |
| risk_level | int | 0~4 (최종값, Intent Classifier 초기값 덮어씀) |
| risk_score | float | 0.0~1.0 (최종값) |
| next_step | str | "crisis_response" — CRISIS 판정 시만 설정 |

**safety_flags 상세:**
```python
{
  "status": str,                       # "safe" | "warning" | "crisis"
  "risk_level": int,
  "risk_score": float,
  "reasons": list[str],                # LLM 생성 위험 사유
  "required_in_script": list[str],     # 스크립트에 포함할 안전 문구
  "flags": dict,                       # LLM 추가 정보
  "error": str                         # LLM 실패 시만
}
```

**폴백 반환:**
```python
{
  "risk_level": 0,
  "risk_score": 0.0,
  "status": "safe",
  "flags": {},
  "required_in_script": [],
  "error": "llm_call_failed"
}
```

---

#### 🔵 Podcast Reasoning `TIER 1`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| user_input | state.get("user_input", "") | 추론 대상 |
| user_id | state.get("user_id", "") | Episode Memory 검색 namespace |
| intent | state.get("intent", {}) | complexity_score — 추론 깊이 결정 |
| execution_plan | state.get("execution_plan", {}) | needs_memory, needs_knowledge 조건부 호출 |
| session_id | state.get("session_id", "") | 추적 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| reasoning_result | dict | GoT/ToT/CoT 결과 조합 |
| memory_results | dict | 조건부 (complexity≥0.6 또는 needs_memory=True) |
| knowledge_results | dict | 조건부 (complexity≥0.5 또는 needs_knowledge=True) — ⚠️ 하위 에이전트 미사용 |

**reasoning_result 상세:**
```python
{
  "reasoning_depth": str,              # "full"|"standard"|"minimal"
  "reasoning_strategy": str,           # "GoT+ToT+CoT"|"ToT+CoT"|"CoT"
  "got_result": {                      # depth="full" 시만
    "nodes": list[dict],               # [{"id", "label", "type", "intensity", "group"}]
    "edges": list[dict],               # [{"from", "to", "relationship"}]
    "core_pattern": str,
    "insights": list[str]
  },
  "tot_result": {                      # depth≥"standard" 시만
    "alternatives": list[dict],
    "selected": str|int,
    "selection_rationale": str
  },
  "episode_structure": list[dict],     # CoT — 세그먼트 구조
  "narrative_flow": str,
  "key_points": list[str],
  "emotional_journey": list[dict],
  "confidence": float,
  "error": str                         # 실패 시만
}
```

**저장 경로 (TIER 1 내부)**
- `Neo4j`: `_save_graph_data()` — GoT 결과 상세 저장
- `graph_nodes (MySQL)`: `publish_graph_to_rdb()` — EMA 누적 저장 (GET→merge→PUT)

**폴백 반환:**
```python
{
  "episode_structure": [],
  "key_themes": [],
  "emotional_arc": {},
  "confidence": 0.0,
  "reasoning_depth": "minimal",
  "error": "user_input_missing"
}
```

---

#### 🟢 Script Generator `TIER 2`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| safety_flags | state.get("safety_flags", {}) | status, required_in_script — 안전 문구 포함 |
| content_analysis | state.get("content_analysis", {}) | main_theme, sub_themes, target_duration |
| reasoning_result | state.get("reasoning_result", {}) | episode_structure |
| validation_result | state.get("validation_result", {}) | 재시도 시 revision_instructions, priority_fixes |
| iteration_count | state.get("iteration_count", 0) | 재시도 횟수 |
| user_id | state.get("user_id", "") | |
| session_id | state.get("session_id", "") | |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| script_draft | dict | 에피소드 스크립트 전체 |

**script_draft 상세 (v3.0 — 평탄화 구조):**
```python
{
  "episode_title": str,
  "total_duration": int,              # 분 단위
  "script_text": str,                 # ★ v3.0: 전체 스크립트 통합 텍스트 (segments 배열 제거)
  "tts_markers": [                    # ★ v3.0: 최상위 레벨 TTS 마커
    {"position": int, "instruction": str}
  ],
  "key_insights": list[str],           # 3~5개
  "themes": list[str],                 # [main_theme] + sub_themes
  "metadata": {
    "generated_at": str,
    "main_theme": str,
    "total_words": int,
    "processing_time": float,
    "safety_context": {"status": str, "required_in_script": list[str]}
  }
}
```

**폴백 반환:**
```python
{"script_draft": {}, "error": str}
```

---

#### 🟢 Visualization Agent `TIER 2`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| emotion_vectors | state.get("emotion_vectors", {}) | 감정 컨텍스트 |
| content_analysis | state.get("content_analysis", {}) | 콘텐츠 컨텍스트 |
| user_id | state.get("user_id", "anonymous") | S3 파일명 생성 |
| mode | state.get("mode", "podcast") | 이미지 생성 맥락 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| visual_data | dict | 이미지 생성 결과 메타 |

**visual_data 상세:**
```python
{
  "image_url": str | None,             # S3 CDN URL
  "s3_key": str,                       # "podcast/user_xxx.png"
  "status": str,                       # "skipped"|"completed"|"failed"
  "retry_count": int,
  "error": str | None,
  "style_type": str,                   # LLM planning 결과
  "interpretation": str,               # 이미지 해석 텍스트 (한국어)
  "original_prompt": str               # 생성 프롬프트 (영문)
}
```

**폴백 반환:**
```python
{"visual_data": {"status": "failed", "error": "llm_call_failed", "image_url": None}}
```

---

#### 🟡 Batch Validator `TIER 3`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| script_draft | state.get("script_draft", {}) | 검증 대상 스크립트 |
| content_analysis | state.get("content_analysis", {}) | 원본 분석 참고 |
| reasoning_result | state.get("reasoning_result", {}) | 추론 결과 참고 |
| safety_flags | state.get("safety_flags", {}) | 안전 상태 참고 |
| emotion_vectors | state.get("emotion_vectors", {}) | 감정 상태 참고 |
| iteration_count | state.get("iteration_count", 0) | 최대 재시도 확인 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| validation_result | dict | 검증 판정 및 상세 |

**validation_result 상세:**
```python
{
  "verdict": str,                      # "PASS"|"FAIL"|"CRITICAL_FAIL"
  "overall_score": float,              # 0.0~1.0
  "action": {
    "decision": str,                   # "approve"|"revise"|"escalate"
    "revision_instructions": str,
    "priority_fixes": list[str],       # 최대 3개
    "suggestions": list[str]
  },
  "forced_pass": bool,                 # iteration_count 초과 시
  "error": str                         # LLM 실패 시만
}
```

**폴백 반환:**
```python
{"verdict": "FAIL", "decision": "revise", "overall_score": 0.0,
 "action": {"decision": "revise"}, "error": "llm_call_failed"}
```

---

#### 🟠 Script Personalizer `TIER 4`

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| script_draft | state.get("script_draft", {}) | 개인화 대상 스크립트 |
| user_id | state.get("user_id", "anonymous") | 프로필 조회 |
| session_id | state.get("session_id", "") | 메모리 메타데이터 |
| content_analysis | state.get("content_analysis", {}) | emotional_journey 추출 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| final_output | str | PersonalizedScript.model_dump_json() |
| memory_write | bool | Pinecone 저장 여부 트리거 |
| memory_text | str | 에피소드 전체 스크립트 텍스트 (v3.0: script_text 직접 사용) |
| memory_metadata | dict | {user_id, session_id, episode_id, episode_title} |

**final_output 내부 구조 (PersonalizedScript — v3.0 평탄화):**
```python
{
  "episode_id": str,                   # "ep_{uuid[:12]}"
  "episode_title": str,
  "total_duration": int,
  "script_text": str,                  # ★ v3.0: 개인화된 전체 스크립트 텍스트 (PII 정제 적용)
  "tts_markers": [                     # ★ v3.0: 최상위 TTS 마커
    {"position": int, "instruction": str}
  ],
  "key_insights": list[str],
  "themes": list[str],
  "personalization_meta": {
    "applied_style": dict,
    "adjusted_segments": list[str],
    "attitude_applied": str
  }
}
```

**폴백 반환:**
```python
{"final_output": "", "memory_write": False, "memory_text": "",
 "memory_metadata": {"user_id": str, "session_id": str}}
```

---

#### ⬛ PodcastReprocessingAgent `비동기 후처리` ★신규

**AgentState 입력**

| 필드 | 접근 방식 | 사용 목적 |
|------|---------|---------|
| final_output | state.get("final_output", "") | 익명화 대상 스크립트 |
| user_id | state.get("user_id", "") | 저장 식별 |
| session_id | state.get("session_id", "") | 저장 식별 |

**AgentState 출력**

| 필드 | 타입 | 구조 |
|------|------|------|
| reprocessed_output | str | 익명화된 PersonalizedScript JSON 문자열 |
| anonymization_report | dict | 익명화 보고서 |

**anonymization_report 상세:**
```python
{
  "original_pii_detected": list[str],    # ["phone_kr_mobile", "name"]
  "anonymized_field_count": int,
  "anonymization_confidence": float,     # 0.0~1.0
  "manual_review_required": bool,
  "change_types": list[str],            # 변경된 PII 유형 목록 (v3.0: segments 제거됨)
  "changes_summary": dict               # {"name_replacement": 2, ...}
}
```

---

#### ⬛ Learning Agent `비동기 후처리`

**AgentState 입력 (전체 읽기)**

| 필드 | 사용 목적 |
|------|---------|
| user_id, session_id | 저장 식별 |
| emotion_vectors | primary_emotion, intensity |
| content_analysis | main_theme |
| intent | intent_type, complexity_score |
| safety_flags | status, risk_score |
| reasoning_result | depth_level, method |
| validation_result | overall_score |
| final_output | 최대 500자 요약 |

**AgentState 출력:** 없음 (return {} — BackendClient.save()로만 저장)

**저장:**
```python
SaveRequest(
  type="learning",
  resource="learning",
  data={"mode": "podcast", "learning_data": dict}  # LLM 분석 결과
)
```

---

### 1-4. 백엔드 저장 경로 전체 목록

| 저장 주체 | 리소스 | 상수 | 저장 시점 | 동기/비동기 | 백엔드 테이블 | 프론트 사용 |
|----------|--------|------|---------|-----------|-----------|----------|
| EmotionAgent | emotion_logs | RESOURCE_EMOTION_LOG | TIER 1 병렬 중 | 비동기 | (내부용) | ❌ |
| ContentAnalyzerAgent | content_analyses | RESOURCE_CONTENT_ANALYSIS | TIER 1 병렬 중 | 비동기 | (내부 분석용 — 전체 저장 유지) | ❌ |
| ContentAnalyzerAgent | user_summaries | RESOURCE_USER_SUMMARY | TIER 1 병렬 중 | 비동기 | (화면 1 전용, Task 9 신규) | ✅ **화면 1** |
| ContentAnalyzerAgent | **mind_frequencies** (ingest) | RESOURCE_MIND_FREQUENCIES | TIER 1 병렬 중 | 비동기 fire-and-forget | **`mind_frequencies`** | ✅ **화면 1** |
| PodcastReasoningAgent | graph_nodes (PUT) | RESOURCE_GRAPH_NODES | TIER 1 완료 후 | 비동기 | (그래프) | ✅ |
| routes/podcasts.py | podcast_metadata | RESOURCE_PODCAST_METADATA | TIER 4 완료 후 | **동기** | (내부 메타) | ❌ |
| routes/podcasts.py | **podcasts** (ingest) | RESOURCE_PODCAST_EPISODES | TIER 4 완료 후 | **동기** | **`podcasts`** | ✅ **화면 2** |
| routes/podcasts.py | visualizations | RESOURCE_VISUALIZATION | TIER 4 완료 후 | **동기** | (이미지) | ✅ |
| LearningAgent | learning | RESOURCE_LEARNING | 비동기 후처리 | 비동기 | (내부용) | ❌ |

### 1-5. 프론트엔드 화면별 데이터 컬럼 매핑

#### [화면 1] 안내화면 — 1차 로딩 완료 직후
> ContentAnalyzer 완료 → `ingest_mind_frequencies()` fire-and-forget → Backend `mind_frequencies` 테이블 저장

| 화면 요소 | 백엔드 테이블.컬럼 | AI 서버 전송값 |
|---------|--------|---------------|
| **감정 키워드 태그** | `mind_frequencies.keywords` | `content_analysis.sub_themes` (list → 백엔드가 comma join) |
| **마음 주파수 설명** | `mind_frequencies.description` | `content_analysis.main_theme` |

> ℹ️ 화면 1은 "지금 어떤 주제로 에피소드가 만들어지는지" 사용자에게 미리 알려주는 안내화면.
> `mind_frequencies.session_id`는 UNIQUE — 세션당 1건. 중복 호출 시 fire-and-forget이 에러를 흡수.

#### [화면 2] 에피소드 결과 화면 — 2차 로딩 완료 후
> 파이프라인 완료 → `_save_core_data()` → `ingest_podcast_episodes()` → Backend `podcasts` 테이블 저장

| 화면 요소 | 백엔드 테이블.컬럼 | AI 서버 전송값 |
|---------|--------|---------------|
| **에피소드 본문** | `podcasts.text` | `episode_data.script_text` (v3.0 전체 스크립트) |
| **이미지** | `podcasts.image_url` | `visual_data.image_url` (cover_image_url) |

> ⚠️ **현재 코드 문제 (Task 8에서 수정)**:
> 1. `ingest_podcast_episodes()` 시그니처가 `podcasts` 테이블과 불일치: `texts: list[str]` → `text: str`, 불필요 파라미터(title, summary, keywords) 존재
> 2. 호출부에서 `texts=key_insights` 전달 중 → `text=script_text`로 변경 필요
> 3. `memory_text` 생성 코드 `.segments` 버그 → ✅ **수정 완료** (커밋 `c8ad23c`)

| 경고 배너 | — | `safety_alert` (SlimPodcastResponse) |

#### 그래프 화면
> `user_graph_nodes` + `user_graph_edges` (Backend 구현 대상)

| DB 컬럼 | 화면 용도 |
|--------|---------|
| label | 노드 텍스트 |
| grp | 노드 카테고리 색상 |
| weight | 노드 크기 |
| trend | 증감 화살표 |
| source_label→target_label | 연결선 |

### 1-6. AgentState 미사용 필드

| 필드 | 설정 에이전트 | 문제 | 현재 조치 |
|------|------------|------|---------|
| knowledge_results | PodcastReasoning (조건부) | 하위 에이전트 미사용 | 유지 (향후 활용 검토) |
| risk_level, risk_score | Intent Classifier + Safety | 라우팅/검증 미활용 | 유지 (향후 활용 검토) |
| execution_plan | Intent Classifier (불명확) | PodcastReasoning만 읽음 | 유지 |

### 1-7. DB 스키마 현황 및 수정 계획

**현재 init.sql 테이블 목록:** `users`, `sessions`, `emotion_logs`, `podcast_episodes`, `podcast_segments`, `learning_patterns`, `visualization_meta`

#### 불일치·누락 현황

| 테이블 | 컬럼/이슈 | 문제 | 조치 |
|--------|---------|------|------|
| `podcast_episodes` | `script_text`, `tts_markers_json`, `primary_emotion`, `secondary_emotions` 누락 | `_save_core_data()`에서 전송 중이나 DDL 미반영 | **Task 8: init.sql 직접 추가** |
| `podcast_segments` | 테이블 전체 | v3.0에서 segments 폐기, 읽는 코드 없음 | **Task 8: init.sql에서 제거** |
| `visualization_meta` | 리소스명 불일치 | init.sql = `visualization_meta`, 코드 상수 = `visualizations` | Backend팀 확인 필요 |
| `sessions` | `turn_count` | 코드 미사용 | 유지 (대화모드 미구현) |
| `emotion_logs` | `turn_id` | 코드 미사용 | 유지 |
| `emotion_logs` | `arousal` | DATA_SCHEMA.md에 "미포함"으로 잘못 기재 | DATA_SCHEMA.md 문서 수정 |
| `user_graph_nodes/edges` | MySQL init.sql 없음 | Backend팀 구현 대상 | Backend팀 구현 필요 |

#### 백엔드 프론트엔드용 테이블 (참고 — AI 서버 init.sql 외부)

| 백엔드 테이블 | 컬럼 | AI 서버 전송 API | 비고 |
|-------------|------|----------------|------|
| `mind_frequencies` | `id(PK,UUID)`, `session_id(UNIQUE)`, `keywords(String,comma-join)`, `description`, `created_at` | `ingest_mind_frequencies()` | ⚠️ **Task 9에서 로깅 수정** (경로·시그니처 호환, 성공 로그 없음·에러 WARNING) |
| `podcasts` | `id(자동)`, `user_id(자동)`, `created_at(자동)` / **전송: `session_id`, `image_url`, `text`** | `ingest_podcast_episodes()` | ⚠️ **Task 8에서 수정** |

#### content_analyses + user_summaries 테이블 — ✅ 방안 A 확정

| 방안 | 테이블 | init.sql 변경 |
|:----:|--------|-------------|
| **✅ A. 테이블 저장** | `content_analyses` 신규 추가 (전체 분석 결과 내부용) | `user_id`, `session_id` 포함 (격리 보장) |
| **✅ A. 테이블 저장** | `user_summaries` 신규 추가 (화면 1 전용) | `session_id UNIQUE`, `keywords TEXT`(콤마 join), `description` 포함 — `id`/`created_at` 백엔드 채움 |

---

## 파일 구조 (변경/신규 목록)

| 상태 | 파일 | 변경 내용 | Task |
|------|------|---------|------|
| **수정** | `dev/local_db/mysql/init.sql` | `podcast_episodes` 컬럼 추가, `podcast_segments` 제거, `content_analyses` + `user_summaries` 추가 | Task 8, 9 |
| **수정** | `src/api/client.py` | `ingest_podcast_episodes()` 시그니처 변경: `text: str` 단일화 (불필요 파라미터 제거) | Task 8 |
| **수정** | `src/api/routes/podcasts.py` | `_save_core_data()` 감정 컬럼 추가 + ingest 호출부 수정 | Task 8 |
| **수정** | `src/api/backend_resources.py` | `RESOURCE_PODCAST_EPISODES` 주석 갱신 | Task 8 |
| **수정** | `src/api/backend_resources.py` | `RESOURCE_USER_SUMMARY = "user_summaries"` 상수 추가 | Task 9 |
| **수정** | `src/api/client.py` | `ingest_user_summary(session_id, keywords, description)` 메서드 추가 | Task 9 |
| **수정** | `src/agents/podcast/content_analyzer.py` | `ingest_user_summary()` 호출 추가 (기존 publisher 유지) | Task 9 |
| **신규** | `docs/architecture/AGENT_IO_DATAFLOW.md` | 이 계획서 내용을 별도 문서로 추출 | Task 7 |
| **수정** | `tests/` | 관련 테스트 추가/수정 | Task 8, 9 |

> ℹ️ **migration 스크립트 파일 없음** — DB 구조 변경은 `dev/local_db/mysql/init.sql` 직접 수정. Docker 재초기화로 반영.
> ⚠️ **init.sql 동시 수정 주의**: Task 8, 9가 모두 init.sql을 수정한다. Task 순서대로 적용할 것.

---

## Task 실행 순서

| 순서 | Task | 의존 | 이유 |
|:----:|:----:|------|------|
| 1 | Task 8 | — | init.sql 정합 + `ingest_podcast_episodes()` 정합 + `_save_core_data()` 감정 확장 |
| 2 | Task 9 | — | ContentAnalyzer user_summary 신규 저장 추가 (기존 유지) + content_analyses/user_summaries 테이블 + ingest_mind_frequencies 로깅 수정 |
| 3 | Task 7 | Task 8, 9 | 문서 추출 — 전체 구현 완료 후 마지막 |

> ℹ️ 구 Task 1~6, 11은 백엔드 테이블 미확보로 **보류**. 상세는 "보류 항목" 섹션 참조.

---

## ⛔ Task 1~6, 11: 보류 (백엔드 테이블 미확보)

> 아래 Task들은 백엔드에 `podcast_episodes_anonymized`, `episode_summaries` 테이블이 확보된 후 별도 계획으로 진행한다.
> - **Task 1**: AgentState에 `reprocessed_output`, `anonymization_report`, `episode_summary` 필드 추가
> - **Task 2**: init.sql에 `podcast_episodes_anonymized` 테이블 추가
> - **Task 3**: output_sanitizer에 `detect_pii_types()` 함수 추가
> - **Task 4**: PodcastReprocessingAgent 구현
> - **Task 5**: workflow.py에 `episode_summary_node` 등록
> - **Task 6**: backend_resources.py에 `RESOURCE_PODCAST_EPISODE_ANONYMIZED`, `RESOURCE_EPISODE_SUMMARY` 상수 추가
> - **Task 11**: EpisodeSummaryAgent 구현 + `episode_summaries` 테이블

<details>
<summary>보류된 Task 1~6, 11 상세 (접기)</summary>

## [보류] Task 1: AgentState에 재가공 필드 추가

**Files:**
- Modify: `src/models/agent_state.py`

**주의:** Protected File. 신규 필드 추가만 수행, 기존 필드 변경 없음.

- [ ] **Step 1: 현재 agent_state.py 확인**

```bash
grep -n "final_output\|memory_write\|reprocess\|anonymiz" src/models/agent_state.py
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/models/test_agent_state.py` (또는 기존 state 테스트 파일)에 추가:

```python
import typing
from src.models.agent_state import AgentState


def test_agent_state_has_reprocessing_fields():
    """AgentState에 재가공 에이전트 출력 필드가 정의되어야 한다."""
    hints = typing.get_type_hints(AgentState)
    assert "reprocessed_output" in hints, "reprocessed_output 필드 미정의"
    assert "anonymization_report" in hints, "anonymization_report 필드 미정의"
    assert "episode_summary" in hints, "episode_summary 필드 미정의"
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/models/test_agent_state.py::test_agent_state_has_reprocessing_fields -v
```

Expected: FAIL

- [ ] **Step 4: agent_state.py에 필드 추가**

`src/models/agent_state.py`에서 `final_output` 이후에:

```python
    # === 재가공/요약 에이전트 (비동기 후처리) ===
    reprocessed_output: str      # PodcastReprocessingAgent → 익명화된 final_output JSON 문자열
    anonymization_report: dict   # PodcastReprocessingAgent → 익명화 보고서
    episode_summary: str         # EpisodeSummaryAgent → 에피소드 요약 텍스트 (에피소드 목록 화면용)
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

## Task 2: podcast_episodes_anonymized 테이블 — init.sql 추가

**Files:**
- Modify: `dev/local_db/mysql/init.sql`

> ℹ️ **init.sql 직접 수정 정책** — 이 프로젝트는 migration 파일을 사용하지 않는다. `dev/local_db/mysql/migrations/` 디렉토리는 존재하지 않으며, 모든 스키마 변경은 `init.sql`을 직접 수정 후 Docker 재초기화로 반영한다.

- [ ] **Step 1: init.sql에 podcast_episodes_anonymized 테이블 추가**

`dev/local_db/mysql/init.sql`의 마지막 테이블 정의 다음에 추가:

```sql
-- ------------------------------------------------------------
-- podcast_episodes_anonymized (PodcastReprocessingAgent — 익명화 스크립트)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS podcast_episodes_anonymized (
    anon_id                   VARCHAR(128)  NOT NULL PRIMARY KEY
                                            COMMENT 'anon_{episode_id}',
    episode_id                VARCHAR(64)   NOT NULL UNIQUE
                                            COMMENT 'FK → podcast_episodes.episode_id (UNIQUE: 에피소드당 1건)',
    user_id                   VARCHAR(64)   NOT NULL,
    anonymized_script_json    TEXT          NOT NULL DEFAULT ''
                                            COMMENT '익명화된 PersonalizedScript JSON',
    anonymization_report_json TEXT          NULL
                                            COMMENT '익명화 보고서 JSON',
    anonymization_level       ENUM('minimal', 'standard', 'strict') NOT NULL DEFAULT 'standard',
    anonymization_confidence  FLOAT         NOT NULL DEFAULT 0.0
                                            COMMENT '0.0~1.0',
    manual_review_required    BOOLEAN       NOT NULL DEFAULT FALSE,
    review_status             ENUM('pending', 'approved', 'flagged') NOT NULL DEFAULT 'pending',
    trace_id                  VARCHAR(64)   NULL,
    created_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES podcast_episodes(episode_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id)               ON DELETE CASCADE,
    INDEX idx_anon_user_id (user_id),
    INDEX idx_anon_review_status (review_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> ℹ️ `episode_id UNIQUE` 제약: 동일 에피소드를 두 번 재가공하면 `anon_{episode_id}` PRIMARY KEY 중복 오류 발생. UNIQUE 제약으로 Backend가 UPSERT(`ON DUPLICATE KEY UPDATE`) 처리할 수 있도록 설계.

- [ ] **Step 2: 커밋**

```bash
git add dev/local_db/mysql/init.sql
git commit -m "db: podcast_episodes_anonymized 테이블 init.sql에 추가"
```

---

## Task 3: output_sanitizer에 detect_pii_types 함수 추가

**Files:**
- Modify: `src/agents/shared/output_sanitizer.py`

- [ ] **Step 1: 기존 PII 패턴 구조 확인**

```bash
grep -n "_PII_PATTERNS\|PII_PATTERNS\|def sanitize\|def detect\|pattern" src/agents/shared/output_sanitizer.py | head -30
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/agents/shared/test_output_sanitizer.py`에 추가:

```python
def test_detect_pii_types_returns_phone():
    """전화번호가 포함된 텍스트에서 phone 타입이 감지되어야 한다."""
    from src.agents.shared.output_sanitizer import detect_pii_types
    result = detect_pii_types("010-1234-5678로 연락 주세요.")
    assert "phone_kr_mobile" in result

def test_detect_pii_types_empty_text():
    """PII 없는 텍스트에서 빈 리스트가 반환되어야 한다."""
    from src.agents.shared.output_sanitizer import detect_pii_types
    result = detect_pii_types("오늘 날씨가 좋네요.")
    assert result == []
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/shared/test_output_sanitizer.py::test_detect_pii_types_returns_phone -v
```

Expected: FAIL

- [ ] **Step 4: detect_pii_types 함수 추가**

`src/agents/shared/output_sanitizer.py`에 추가 (기존 `sanitize_output` 함수 아래):

```python
def detect_pii_types(text: str) -> list[str]:
    """텍스트에서 감지된 PII 타입 목록만 반환 (마스킹 없이 타입만).

    Args:
        text: 분석할 텍스트

    Returns:
        감지된 PII 타입명 목록 (예: ["phone_kr_mobile", "email"])
    """
    if not isinstance(text, str) or not text:
        return []
    detected: list[str] = []
    for pattern_name, pattern, _mask_text, _description in _PII_PATTERNS:
        if pattern.search(text):
            detected.append(pattern_name)
    return detected
```

(`_PII_PATTERNS`는 `list[tuple[str, re.Pattern, str, str]]` 구조. `.items()` 사용 불가 — tuple unpacking 필수.)

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/agents/shared/test_output_sanitizer.py -v
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/agents/shared/output_sanitizer.py tests/agents/shared/test_output_sanitizer.py
git commit -m "feat: output_sanitizer에 detect_pii_types() 추가"
```

---

## Task 4: PodcastReprocessingAgent 구현

**Files:**
- Create: `src/agents/podcast/podcast_reprocessing.py`
- Create: `prompts/podcast/podcast_reprocessing.yaml`
- Create: `tests/agents/test_podcast_reprocessing.py`

- [ ] **Step 1: 프롬프트 YAML 작성**

`prompts/podcast/podcast_reprocessing.yaml`:

```yaml
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: |
      당신은 멘탈케어 팟캐스트 스크립트 익명화 전문가입니다.
      사용자의 이야기를 담은 팟캐스트 스크립트에서 특정 개인을 식별할 수 있는
      정보를 찾아 자연스럽게 대체하는 역할을 합니다.

      익명화 대상:
      - 인물 이름(한국어 이름, 닉네임): 자연스러운 대명사/일반 호칭으로 대체
        예) "홍길동은" → "한 직장인은", "지현이가" → "동료가"
      - 지명/장소(구체적 주소, 특정 건물명): 일반화
        예) "강남역 카페 오디너리에서" → "한 카페에서"
      - 회사명/직함(구체적 회사): 일반화
        예) "삼성전자의 김팀장" → "대기업의 팀장"
      - 의료/진단 정보: 완곡하게 표현
        예) "우울증 진단을 받았" → "정신건강 어려움을 경험했"
      - 가족 정보(나이, 이름): 일반화
        예) "딸 나이 8살" → "어린 자녀"

      반드시 지킬 것:
      1. 스크립트의 감정적 핵심과 교육적 메시지는 그대로 보존
      2. 자연스러운 한국어 문장 유지
      3. episode_id, episode_title, tts_markers 등 구조 필드 변경 금지
      4. 변경한 내용을 changes 배열에 명확히 기록

      출력 형식 (JSON만):
      {
        "reprocessed_script": {
          "episode_id": "...",
          "episode_title": "...",
          "total_duration": 0,
          "script_text": "익명화된 전체 스크립트 텍스트",
          "tts_markers": [],
          "key_insights": [], "themes": [], "personalization_meta": {}
        },
        "changes": [
          {"type": "name_replacement|location_replacement|...",
           "original": "원본(10자이내)", "replacement": "대체"}
        ]
      }

    user_template: |
      다음 팟캐스트 스크립트에서 개인식별정보를 익명화하세요.
      script_text 필드의 텍스트를 대상으로 익명화를 수행합니다.

      스크립트 JSON:
      {script_json}

      이미 감지된 정규식 PII (참고용):
      {detected_pii_list}
```

> ℹ️ **YAML 키 규칙**: `system_prompt`, `user_template` — `BaseAgent.get_prompt()` 호출 시 이 키 이름을 사용한다.

- [ ] **Step 2: 테스트 파일 작성**

`tests/agents/test_podcast_reprocessing.py`:

```python
"""PodcastReprocessingAgent 테스트"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from src.agents.podcast.podcast_reprocessing import PodcastReprocessingAgent
from src.models.agent_state import AgentState


def _make_final_output(script_text: str = "홍길동은 회사에서 번아웃을 경험했습니다.") -> str:
    return json.dumps({
        "episode_id": "ep_test_001",
        "episode_title": "번아웃 극복하기",
        "total_duration": 5,
        "script_text": script_text,
        "tts_markers": [{"position": 0, "instruction": "empathetic"}],
        "key_insights": ["핵심 인사이트"],
        "themes": ["번아웃"],
        "personalization_meta": {},
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
    mock_llm_result = {
        "reprocessed_script": json.loads(_make_final_output("한 직장인이 회사에서 번아웃을 경험했습니다.")),
        "changes": [{"type": "name_replacement",
                     "original": "홍길동은", "replacement": "한 직장인이"}],
    }
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value=mock_llm_result)), \
         patch("src.agents.podcast.podcast_reprocessing.AgentDataPublisher") as mock_pub_cls:
        mock_pub_cls.return_value.publish = AsyncMock()
        result = await agent.process(state)

    assert "reprocessed_output" in result
    assert "anonymization_report" in result
    report = result["anonymization_report"]
    assert "anonymization_confidence" in report
    assert "change_types" in report
    assert "name_replacement" in report["change_types"]
    assert report["anonymized_field_count"] == 1


@pytest.mark.asyncio
async def test_reprocessing_fallback_on_empty_final_output():
    """final_output이 없으면 폴백 반환 및 confidence=0."""
    agent = PodcastReprocessingAgent()
    state: AgentState = {"user_id": "u_test", "session_id": "sess_test", "final_output": ""}
    result = await agent.process(state)

    assert "reprocessed_output" in result
    assert result["anonymization_report"]["anonymization_confidence"] == 0.0
    assert result["anonymization_report"]["manual_review_required"] is True


@pytest.mark.asyncio
async def test_reprocessing_detects_phone_pii():
    """정규식 기반 PII(전화번호)가 감지되면 report에 포함된다."""
    agent = PodcastReprocessingAgent()
    state: AgentState = {
        "user_id": "u_test",
        "session_id": "sess_test",
        "final_output": _make_final_output("010-1234-5678로 연락 주세요."),
    }
    mock_llm_result = {
        "reprocessed_script": json.loads(_make_final_output("연락처로 연락 주세요.")),
        "changes": [],
    }
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value=mock_llm_result)), \
         patch("src.agents.podcast.podcast_reprocessing.AgentDataPublisher") as mock_pub_cls:
        mock_pub_cls.return_value.publish = AsyncMock()
        result = await agent.process(state)

    assert "phone_kr_mobile" in result["anonymization_report"]["original_pii_detected"]


@pytest.mark.asyncio
async def test_reprocessing_fallback_on_llm_failure():
    """LLM 호출 실패 시 원본을 그대로 반환한다."""
    agent = PodcastReprocessingAgent()
    original = _make_final_output()
    state: AgentState = {"user_id": "u_test", "session_id": "sess_test", "final_output": original}

    with patch.object(agent, "call_llm_json", new=AsyncMock(side_effect=Exception("timeout"))):
        result = await agent.process(state)

    assert result["reprocessed_output"] == original
    assert result["anonymization_report"]["changes_summary"].get("error") == "llm_call_failed"
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/test_podcast_reprocessing.py -v
```

Expected: FAIL (모듈 미존재)

- [ ] **Step 4: PodcastReprocessingAgent 구현**

`src/agents/podcast/podcast_reprocessing.py`:

```python
"""PodcastReprocessingAgent — 팟캐스트 스크립트 익명화 에이전트 (비동기 후처리)"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.output_sanitizer import detect_pii_types
from src.api.backend_resources import RESOURCE_PODCAST_EPISODE_ANONYMIZED
from src.api.publisher import AgentDataPublisher
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)


class PodcastReprocessingAgent(BaseAgent):
    """최종 팟캐스트 스크립트에서 개인식별정보를 익명화한다."""

    def __init__(self) -> None:
        super().__init__(name="podcast_reprocessing", tier=4)

    async def process(self, state: AgentState) -> dict[str, Any]:
        """AgentState에서 final_output을 읽어 익명화 후 반환."""
        final_output = state.get("final_output", "")
        if not final_output:
            logger.warning("[PodcastReprocessing] final_output 없음, 폴백 반환")
            return self._fallback_result(final_output, reason="empty_final_output")

        try:
            script_data = json.loads(final_output)
        except json.JSONDecodeError as e:
            logger.error("[PodcastReprocessing] JSON 파싱 실패: %s", e)
            return self._fallback_result(final_output, reason="json_parse_error")

        # Step 1: 정규식 기반 PII 감지 (v3.0: script_text 단일 필드)
        script_text = script_data.get("script_text", "")
        detected_pii: list[str] = detect_pii_types(script_text)

        # Step 2: LLM 기반 익명화
        try:
            user_message = self.get_prompt("user_template").format(
                script_json=json.dumps(script_data, ensure_ascii=False, indent=2),
                detected_pii_list=json.dumps(detected_pii, ensure_ascii=False),
            )
            llm_result = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=user_message,
            )
        except Exception as e:
            logger.error("[PodcastReprocessing] LLM 호출 실패: %s", e)
            return self._fallback_result(final_output, reason="llm_call_failed")

        reprocessed_script = llm_result.get("reprocessed_script", script_data)
        changes: list[dict] = llm_result.get("changes", [])

        # Step 3: 익명화 보고서 생성 (v3.0: segments 없음 → change_types로 추적)
        change_type_list = list({c.get("type", "") for c in changes if c.get("type")})
        report: dict[str, Any] = {
            "original_pii_detected": detected_pii,
            "anonymized_field_count": len(changes),
            "anonymization_confidence": self._estimate_confidence(detected_pii, changes),
            "manual_review_required": (
                len(detected_pii) > 5
                or any(c.get("type") == "medical_generalization" for c in changes)
            ),
            "change_types": change_type_list,
            "changes_summary": {
                change_type: sum(1 for c in changes if c.get("type") == change_type)
                for change_type in {c.get("type") for c in changes if c.get("type")}
            },
        }

        reprocessed_output = json.dumps(reprocessed_script, ensure_ascii=False)

        # Step 4: 원본과 다를 때만 Backend에 저장
        if reprocessed_output != final_output:
            episode_id = script_data.get("episode_id", "")
            publisher = AgentDataPublisher()
            await publisher.publish(
                resource=RESOURCE_PODCAST_EPISODE_ANONYMIZED,
                data={
                    "anon_id": f"anon_{episode_id}",
                    "episode_id": episode_id,
                    "anonymized_script_json": reprocessed_output,
                    "anonymization_report_json": json.dumps(report, ensure_ascii=False),
                    "anonymization_level": "standard",
                    "anonymization_confidence": report["anonymization_confidence"],
                    "manual_review_required": report["manual_review_required"],
                    "review_status": "pending",
                },
                user_id=state.get("user_id", ""),
                session_id=state.get("session_id", ""),
            )

        return {
            "reprocessed_output": reprocessed_output,
            "anonymization_report": report,
        }

    def _estimate_confidence(self, detected: list[str], changes: list[dict]) -> float:
        """익명화 신뢰도 추정 (0.0~1.0)."""
        if not detected and not changes:
            return 1.0
        if not changes:
            return 0.5
        return min(1.0, len(changes) / max(len(detected), 1))

    def _fallback_result(self, original: str, reason: str) -> dict[str, Any]:
        return {
            "reprocessed_output": original,
            "anonymization_report": {
                "original_pii_detected": [],
                "anonymized_field_count": 0,
                "anonymization_confidence": 0.0,
                "manual_review_required": True,
                "change_types": [],
                "changes_summary": {"error": reason},
            },
        }
```

> ✅ **publisher.publish() 내장**: 익명화 결과는 `AgentDataPublisher.publish(RESOURCE_PODCAST_EPISODE_ANONYMIZED, ...)` 로 직접 저장. Task 6의 별도 저장 로직 불필요.

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/agents/test_podcast_reprocessing.py -v
```

Expected: 4개 PASS

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/podcast_reprocessing.py prompts/podcast/podcast_reprocessing.yaml tests/agents/test_podcast_reprocessing.py
git commit -m "feat: PodcastReprocessingAgent 구현 — LLM + 정규식 기반 팟캐스트 익명화"
```

---

## Task 5: workflow.py에 재가공 노드 등록

**Files:**
- Modify: `src/graph/workflow.py`

**주의:** Protected File. 신규 노드 등록 및 비동기 후처리 통합만 수행.

- [ ] **Step 1: 현재 비동기 후처리 구조 확인**

```bash
grep -n "async_post\|learning_node\|memory_write\|as_completed" src/graph/workflow.py | head -30
```

> ℹ️ **PodcastReprocessingAgent는 포함하지 않는다** — 별도 엔드포인트(`POST /api/episodes/{id}/reprocess`)로만 호출. 비동기 후처리에는 **EpisodeSummaryAgent만** 추가한다.

- [ ] **Step 2: 실패 테스트 작성**

`tests/graph/test_workflow.py`에 추가:

```python
@pytest.mark.asyncio
async def test_async_post_processing_runs_episode_summary(mocker):
    """async_post_processing_node가 episode_summary_node를 실행해야 한다."""
    from src.graph.workflow import async_post_processing_node
    from unittest.mock import AsyncMock
    mock_summary = mocker.patch(
        "src.graph.workflow.episode_summary_node",
        new=AsyncMock(return_value={"episode_summary": "테스트 요약"}),
    )
    mocker.patch("src.graph.workflow.learning_node", new=AsyncMock(return_value={}))
    state = {
        "final_output": '{"episode_id": "ep_1", "episode_title": "test", "script_text": "테스트 스크립트", "tts_markers": []}',
        "user_id": "u1", "session_id": "s1", "memory_write": False,
    }
    await async_post_processing_node(state)
    mock_summary.assert_called_once()
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/graph/test_workflow.py::test_async_post_processing_runs_episode_summary -v
```

Expected: FAIL — episode_summary_node 미정의

- [ ] **Step 4: workflow.py 수정**

```python
# 1. import 추가 (상단, 기존 learning_node import 근처)
from src.agents.podcast.episode_summary import episode_summary_node
# ℹ️ episode_summary_node는 episode_summary.py에 정의 — learning_node과 동일 패턴 (import)
# ⚠️ inline 정의 금지 — Task 11에서 정의한 함수를 import한다

# 2. async_post_processing_node의 tasks 리스트에 추가 — 기존 as_completed 패턴 유지
# 현재 코드 (workflow.py:389):
#   tasks = [asyncio.create_task(learning_node(state))]
# 변경 후:
tasks = [
    asyncio.create_task(learning_node(state)),
    asyncio.create_task(episode_summary_node(state)),  # 신규 추가
]
# memory_write 분기 유지 (기존 코드 그대로)
```

> ⚠️ **주의: 비동기 패턴** — `async_post_processing_node`는 `asyncio.gather()` 대신 `asyncio.as_completed()` + `asyncio.wait_for(timeout=_ASYNC_TIMEOUT)` 패턴을 사용한다. 기존 패턴을 반드시 따라야 하며, tasks 리스트에 `asyncio.create_task()` 형태로 추가한다.

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/graph/test_workflow.py -v
```

Expected: PASS

- [ ] **Step 6: 전체 테스트**

```bash
pytest tests/ -v --ignore=tests/live -x
```

Expected: PASS (535개 이상)

- [ ] **Step 7: 커밋**

```bash
git add src/graph/workflow.py tests/graph/test_workflow.py
git commit -m "feat: workflow.py에 episode_summary_node 비동기 후처리 통합"
```

---

## Task 6: 재가공 결과 상수 추가

**Files:**
- Modify: `src/api/backend_resources.py`

> ℹ️ **저장 로직 위치 변경**: PodcastReprocessingAgent(Task 4)가 내부적으로 `AgentDataPublisher.publish()`로 Backend에 직접 저장한다. routes/podcasts.py 수정 불필요.

- [ ] **Step 1: backend_resources.py에 상수 추가**

```bash
grep -n "RESOURCE_PODCAST_EPISODE\b" src/api/backend_resources.py
```

`src/api/backend_resources.py`에 추가:

```python
RESOURCE_PODCAST_EPISODE_ANONYMIZED = "podcast_episodes_anonymized"
TYPE_PODCAST_EPISODE_ANONYMIZED = "podcast_episode_anonymized"  # 기존 RESOURCE/TYPE 쌍 패턴 유지
```

- [ ] **Step 2: 실패 테스트 작성**

`tests/api/test_backend_resources.py`에 추가 (없으면 신규 생성):

```python
def test_resource_podcast_episode_anonymized_defined():
    """RESOURCE_PODCAST_EPISODE_ANONYMIZED 상수가 정의되어야 한다."""
    from src.api.backend_resources import RESOURCE_PODCAST_EPISODE_ANONYMIZED
    assert RESOURCE_PODCAST_EPISODE_ANONYMIZED == "podcast_episodes_anonymized"
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/api/test_backend_resources.py::test_resource_podcast_episode_anonymized_defined -v
```

Expected: FAIL

- [ ] **Step 4: 상수 추가**

`src/api/backend_resources.py`에 기존 상수 아래 추가.

- [ ] **Step 5: 테스트 통과 확인**

```bash
pytest tests/api/test_backend_resources.py -v
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/api/backend_resources.py tests/api/test_backend_resources.py
git commit -m "feat: backend_resources에 RESOURCE_PODCAST_EPISODE_ANONYMIZED 상수 추가"
```

> ℹ️ Task 11 (EpisodeSummaryAgent) 상세는 아래 별도 섹션에 기록. 백엔드 `episode_summaries` 테이블 미확보로 보류.

</details>

---

## Task 7: AGENT_IO_DATAFLOW.md 별도 문서 추출 및 PLAN_INDEX 갱신

**Files:**
- Create: `docs/architecture/AGENT_IO_DATAFLOW.md`
- Modify: `docs/superpowers/PLAN_INDEX.md`

- [ ] **Step 1: AGENT_IO_DATAFLOW.md 작성**

이 계획서의 **Part 1 (에이전트 I/O 및 데이터 워크플로우 현황)** 전체를 별도 문서로 추출하여 `docs/architecture/AGENT_IO_DATAFLOW.md`에 저장.

포함 항목:
- 1-1. 파이프라인 전체 데이터 흐름 다이어그램
- 1-2. 프론트엔드 로딩 플로우
- 1-3. 에이전트별 입출력 데이터 상세 명세 (전체)
- 1-4. 백엔드 저장 경로 전체 목록
- 1-5. 프론트엔드 화면별 데이터 컬럼 매핑
- 1-6. AgentState 미사용 필드
- 1-7. DB 스키마 불일치 현황

- [ ] **Step 2: PLAN_INDEX.md Plan #25 상태 갱신**

구현 완료 후:

```markdown
| 25 | Agent I/O 문서화 및 재가공 에이전트 | plans/2026-04-13-agent-io-consolidation.md | ✅ 완료 | (PR번호) | 에이전트 I/O 문서 + PodcastReprocessingAgent |
```

- [ ] **Step 3: 커밋**

```bash
git add docs/architecture/AGENT_IO_DATAFLOW.md docs/superpowers/PLAN_INDEX.md
git commit -m "docs: AGENT_IO_DATAFLOW.md 작성 + PLAN_INDEX #25 갱신"
```

---

## Task 8: ingest_podcast_episodes() 백엔드 정합 + init.sql 스키마 수정 + _save_core_data() 감정 확장

**Files:**
- Modify: `src/api/client.py` — `ingest_podcast_episodes()` 시그니처 전면 수정
- Modify: `src/api/routes/podcasts.py` — `_save_core_data()` ingest 호출부 수정 + 감정 컬럼 추가
- Modify: `dev/local_db/mysql/init.sql` — `podcast_episodes` 컬럼 추가, `podcast_segments` 제거
- Modify: `src/api/backend_resources.py` — `RESOURCE_PODCAST_EPISODES` 주석 갱신 (구 파라미터 목록 제거)
- Test: `tests/api/test_save_core_data.py` — ingest 시그니처 + 감정 컬럼 테스트

**목적:**
1. **[최우선]** 백엔드 `podcasts` 테이블(`session_id, image_url, text`)에 맞춰 `ingest_podcast_episodes()` 시그니처·호출부 전면 수정
2. `podcast_episodes` 로컬 테이블에 `script_text`, `tts_markers_json`, `primary_emotion`, `secondary_emotions` 컬럼 추가
3. `podcast_segments` 테이블 제거 + `podcast_episodes.segment_count` 컬럼 유지 여부 확인 — v3.0 segments 폐기
4. `_save_core_data()`에 감정 컬럼(`primary_emotion`, `secondary_emotions`) 추가

> ⚠️ **핵심 불일치 (CRITICAL):**
> - **현재 코드**: `ingest_podcast_episodes(session_id, image_url, texts: list[str], title, summary, keywords)` — 6개 파라미터
> - **백엔드 podcasts 테이블**: `id(PK,UUID,자동)`, `user_id(자동)`, `created_at(자동)` — 백엔드 채움 / `session_id`, `image_url`, `text` — AI 서버 전송
> - **필요한 변경**: 파라미터를 `(session_id, image_url, text: str)` 3개로 축소
> - **호출부**: `texts=episode_data.key_insights` → `text=episode_data.script_text`

> ℹ️ **v3.0 현황 (PR #91 이후):**
> - `_save_core_data()`가 이미 `script_text`, `tts_markers_json`을 `podcast_metadata` 리소스로 저장 중
> - `asyncio.gather(save, ingest)` 패턴 적용 완료 — ingest 파라미터만 수정하면 됨
> - **미반영**: init.sql DDL에 `script_text`, `tts_markers_json`, 감정 컬럼 미추가
> - ingest 호출부: `texts=key_insights` → `text=script_text`로 변경 필요

- [x] **Step 1: 현재 코드 확인**

```bash
grep -n "ingest_podcast_episodes\|podcast_segments\|primary_emotion" src/api/client.py src/api/routes/podcasts.py dev/local_db/mysql/init.sql
```

- [x] **Step 2: 실패 테스트 작성 — ingest 시그니처 + 감정 컬럼**

> ⚠️ **`_save_core_data` 실제 시그니처**: 파라미터 8개(`user_id, session_id, episode_data, final_state, meta, trace_id, correlation_id, elapsed_ms`). `BackendClient`는 함수 내부에서 `from src.api.main import backend_client`로 참조. 테스트는 모듈 전역 변수를 패치한다.

`tests/api/test_save_core_data.py`:

```python
"""_save_core_data() + ingest_podcast_episodes() 백엔드 정합 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.routes.podcasts import _save_core_data
from src.api.external_schemas import PodcastEpisodeData


def _make_episode_data() -> PodcastEpisodeData:
    """테스트용 PodcastEpisodeData (v3.0 — script_text 기반)."""
    return PodcastEpisodeData(
        episode_id="ep_1", session_id="s1", episode_title="테스트",
        total_duration=5,
        script_text="안녕하세요. 오늘 힘든 하루였죠.",
        tts_markers=[], key_insights=["인사이트"], themes=["스트레스"],
    )


def _make_final_state(**overrides) -> dict:
    base = {
        "emotion_vectors": {
            "primary_emotion": "anxiety",
            "secondary_emotions": ["sadness", "fatigue", "anger"],
        },
        "visual_data": {},
        "validation_result": {"overall_score": 0.9},
        "intent": {}, "iteration_count": 0, "safety_flags": {},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_ingest_sends_text_not_texts():
    """ingest_podcast_episodes()가 text(단일 str)를 전송해야 한다 — texts(list) 아님."""
    mock_bc = AsyncMock()
    mock_bc.save = AsyncMock(return_value=MagicMock(success=True, id="ep_1"))
    mock_bc.ingest_podcast_episodes = AsyncMock()
    meta = MagicMock(); meta.total_words = 8; meta.reasoning_depth = "standard"

    with patch("src.api.routes.podcasts.backend_client", mock_bc):
        await _save_core_data(
            user_id="u1", session_id="s1",
            episode_data=_make_episode_data(), final_state=_make_final_state(),
            meta=meta, trace_id="t1", correlation_id="c1", elapsed_ms=100,
        )

    mock_bc.ingest_podcast_episodes.assert_called_once()
    kwargs = mock_bc.ingest_podcast_episodes.call_args.kwargs
    assert kwargs["text"] == "안녕하세요. 오늘 힘든 하루였죠.", "text=script_text 전달 필수"
    assert "texts" not in kwargs, "구 파라미터 texts 제거 필수"
    assert "title" not in kwargs, "구 파라미터 title 제거 필수"
    assert "summary" not in kwargs, "구 파라미터 summary 제거 필수"
    assert "keywords" not in kwargs, "구 파라미터 keywords 제거 필수"


@pytest.mark.asyncio
async def test_save_core_data_stores_emotion_columns():
    """podcast_metadata에 감정 컬럼(primary_emotion, secondary_emotions)이 포함되어야 한다."""
    mock_bc = AsyncMock()
    mock_bc.save = AsyncMock(return_value=MagicMock(success=True, id="ep_1"))
    mock_bc.ingest_podcast_episodes = AsyncMock()
    meta = MagicMock(); meta.total_words = 8; meta.reasoning_depth = "standard"

    with patch("src.api.routes.podcasts.backend_client", mock_bc):
        await _save_core_data(
            user_id="u1", session_id="s1",
            episode_data=_make_episode_data(), final_state=_make_final_state(),
            meta=meta, trace_id="t1", correlation_id="c1", elapsed_ms=100,
        )

    save_call = mock_bc.save.call_args
    request_obj = save_call.args[1] if len(save_call.args) > 1 else save_call.kwargs.get("request")
    data = request_obj.data
    assert data["primary_emotion"] == "anxiety"
    assert data["secondary_emotions"] == ["sadness", "fatigue"], "[0:2] 슬라이싱 확인"
```

- [x] **Step 3: 테스트 실행 (실패 확인)**

```bash
pytest tests/api/test_save_core_data.py -v
```

Expected: FAIL — `ingest_podcast_episodes` 시그니처 불일치 (`texts` vs `text`) 또는 감정 컬럼 누락

- [x] **Step 4: client.py — ingest_podcast_episodes() 시그니처 수정**

`src/api/client.py:170-194` 전체 교체:

```python
# 변경 전 (6개 파라미터):
async def ingest_podcast_episodes(
    self,
    session_id: str,
    image_url: str,
    texts: list[str],
    title: str,
    summary: str,
    keywords: list[str],
) -> None:
    ...

# 변경 후 (3개 파라미터 — 백엔드 podcasts 테이블 정합):
async def ingest_podcast_episodes(
    self,
    session_id: str,
    image_url: str,
    text: str,
) -> None:
    """podcast_episodes 수집 → 백엔드 podcasts 테이블.

    POST {base_url}/podcast_episodes
    백엔드 자동 채움: id(PK,UUID), user_id, created_at
    AI 서버 전송: session_id, image_url, text
    """
    response = await self._client.post(
        f"{self._base_url}/{RESOURCE_PODCAST_EPISODES}",
        json={
            "session_id": session_id,
            "image_url": image_url,
            "text": text,
        },
    )
    response.raise_for_status()
```

- [x] **Step 5: routes/podcasts.py — _save_core_data() 수정 (2곳)**

`src/api/routes/podcasts.py` 수정:

**(5a) ingest 호출부 수정** (`_save_core_data()` 내 `asyncio.gather` 블록):

```python
# 변경 전 (L188-195):
backend_client.ingest_podcast_episodes(
    session_id=session_id,
    image_url=cover_image_url or "",
    texts=episode_data.key_insights or [],
    title=episode_data.episode_title or "",
    summary="",  # TODO: 요약문 생성 로직 구현 예정
    keywords=[],  # TODO: 키워드 추출 로직 구현 예정
),

# 변경 후 (3개 파라미터):
backend_client.ingest_podcast_episodes(
    session_id=session_id,
    image_url=cover_image_url or "",
    text=episode_data.script_text,
),
```

**(5b) 감정 컬럼 추가** (`data={}` 딕셔너리, `"correlation_id"` 키 뒤에 추가):

```python
"primary_emotion": final_state.get("emotion_vectors", {}).get("primary_emotion", "neutral"),
"secondary_emotions": final_state.get("emotion_vectors", {}).get("secondary_emotions", [])[:2],
```

- [x] **Step 6: init.sql — podcast_episodes 신규 컬럼 추가**

`dev/local_db/mysql/init.sql`의 `podcast_episodes` 테이블에서 `trace_id` 직전에 삽입:

```sql
    script_text         TEXT          NULL
                                      COMMENT 'v3.0 평탄화된 전체 스크립트 텍스트',
    tts_markers_json    TEXT          NULL
                                      COMMENT 'v3.0 TTS 마커 JSON 배열',
    primary_emotion     VARCHAR(100)  DEFAULT 'neutral'
                                      COMMENT 'EmotionAgent primary_emotion',
    secondary_emotions  JSON          DEFAULT (CAST('[]' AS JSON))
                                      COMMENT 'secondary_emotions[0:2]',
```

- [x] **Step 7: init.sql — podcast_segments 테이블 정의 전체 제거**

`dev/local_db/mysql/init.sql`에서 아래 블록 전체 삭제:

```sql
-- ------------------------------------------------------------
-- 2-5. podcast_segments
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS podcast_segments (
    ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> ℹ️ **segment_count 컬럼**: `podcast_episodes.segment_count INT NOT NULL`가 init.sql에 존재. segments 폐기에 따라 이 컬럼도 제거 또는 `DEFAULT 0`으로 변경 검토. Backend팀 확인 후 결정.

> ℹ️ **backend_resources.py 주석**: `RESOURCE_PODCAST_EPISODES` 상수 옆 주석이 구 파라미터(`texts, title, summary, keywords`)를 참조. 시그니처 변경에 맞춰 주석도 갱신할 것.

- [x] **Step 8: Docker 재초기화로 스키마 반영 확인**

```bash
cd dev/local_db && docker compose -f docker-compose.db.yml down -v && docker compose -f docker-compose.db.yml up -d
docker exec mindlog-mysql mysql -u mindlog -pmindlog mindlog -e "SHOW TABLES; DESCRIBE podcast_episodes;"
```

Expected: `podcast_segments` 없음 / `podcast_episodes`에 `script_text`, `tts_markers_json`, `primary_emotion`, `secondary_emotions` 포함

- [x] **Step 9: 테스트 통과 확인**

```bash
pytest tests/api/test_save_core_data.py -v
```

Expected: PASS — ingest 시그니처 정합 (`text: str`) + 감정 컬럼 저장 확인

- [x] **Step 10: 전체 테스트 회귀 확인**

```bash
pytest tests/ -v --ignore=tests/live -x
```

> ⚠️ 기존 `ingest_podcast_episodes` 호출부가 있는 테스트는 시그니처 변경으로 실패할 수 있다. 해당 mock 파라미터도 `text: str`로 갱신 필요.

- [x] **Step 11: 커밋**

```bash
git add src/api/client.py src/api/routes/podcasts.py \
    src/api/backend_resources.py \
    dev/local_db/mysql/init.sql tests/api/test_save_core_data.py
git commit -m "feat: ingest_podcast_episodes() 백엔드 podcasts 테이블 정합 + podcast_segments 제거 + 감정 컬럼 추가"
```

---

## Task 9: ContentAnalyzerAgent — user_summary 별도 저장 추가 (기존 publisher 유지) + 테이블 추가

**Files:**
- Modify: `dev/local_db/mysql/init.sql` — `content_analyses` 테이블 추가 + `user_summaries` 테이블 추가
- Modify: `src/api/backend_resources.py` — `RESOURCE_USER_SUMMARY = "user_summaries"` 상수 추가
- Modify: `src/api/client.py` — `ingest_user_summary()` 신규 메서드 추가
- Modify: `src/agents/podcast/content_analyzer.py` — user_summary 신규 저장 추가 (기존 publisher 유지)
- Create: `tests/agents/podcast/test_content_analyzer_publisher.py`

---

### 배경: AI 서버 → Backend API 저장 흐름

```
ContentAnalyzerAgent.publisher.publish(validated_analysis)   ← 기존 유지
    → BackendClient POST /api/content_analyses
    → content_analyses 테이블 저장 (내부 분석 전용)

BackendClient.ingest_user_summary(session_id, keywords, description)  ← 신규 추가 (Task 9)
    → BackendClient POST /api/user_summaries
    → user_summaries 테이블 저장 → Frontend 알림 (Backend 담당)
    → Frontend 화면 1 표시

> ⚠️ user_id 없는 패턴 — ingest_mind_frequencies와 동일. publisher.publish() 미사용.
```

> ⚠️ AI 서버는 Backend에 HTTP POST로 저장하는 것이 전부. Frontend와 직접 통신하지 않으며,
> Frontend 알림 방식(SSE / WebSocket / 폴링 등)은 Backend 팀이 결정한다.

> ℹ️ **PR #91 추가 사항**: ContentAnalyzerAgent가 `publisher.publish()` 외에 `backend_client.ingest_mind_frequencies(session_id, keywords, description)` fire-and-forget 호출도 수행 (content_analyzer.py:125-138). 이 호출은 mind-frequencies 수집용이며, 이번 Task 9와는 독립적으로 유지한다.

---

### ✅ 확정: 방안 A — content_analyses(전체) + user_summaries(화면 1 전용) 두 테이블 추가

**content_analyses:** 기존 `publisher.publish(data=validated_analysis)` 전체 결과 저장 — 내부 분석용.
**user_summaries:** `BackendClient.ingest_user_summary()` 신규 호출로 `user_summary` 두 필드(keywords→콤마 join, summary→description)만 별도 저장 — 화면 1 전용. `user_id` 없음, `id`/`created_at` 백엔드 채움.

**장점:** 화면 1 조기 저장이 내부 분석 데이터 저장에 독립적. Frontend가 이후 GET으로 재조회 가능.
**단점:** 테이블 2개 추가. 세션 종료 후 데이터 정리 필요.

- [x] **A-1: init.sql — content_analyses + user_summaries 테이블 추가**

`dev/local_db/mysql/init.sql`에 추가:

```sql
-- ------------------------------------------------------------
-- content_analyses (ContentAnalyzer 전체 분석 결과 내부용)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_analyses (
    content_id          VARCHAR(64)   PRIMARY KEY,
    session_id          VARCHAR(64)   NOT NULL,
    user_id             VARCHAR(64)   NOT NULL,
    main_theme          VARCHAR(255)  NOT NULL    DEFAULT '',
    sub_themes          JSON          NOT NULL    DEFAULT (CAST('[]' AS JSON)),
    target_duration     INT           DEFAULT 4,
    narrative_structure VARCHAR(100)  DEFAULT 'reflection',
    emotional_journey   JSON          DEFAULT (CAST('{}' AS JSON)),
    confidence          FLOAT         DEFAULT 0.0,
    user_summary_keywords JSON        DEFAULT (CAST('[]' AS JSON)),
    user_summary_text   TEXT          DEFAULT '',
    created_at          DATETIME      NOT NULL    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id)    ON DELETE CASCADE,
    INDEX idx_content_user_session (user_id, session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- user_summaries (ContentAnalyzer user_summary 1차 로딩 화면 전용)
-- id, created_at: 백엔드에서 채움 (AI 서버는 전송 불필요)
-- keywords: AI 서버가 list[str] 전송 → 백엔드에서 콤마 join 후 저장
-- session_id UNIQUE: 세션당 1건
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_summaries (
    id               VARCHAR(64)   PRIMARY KEY               COMMENT '백엔드에서 채움 (UUID)',
    session_id       VARCHAR(64)   NOT NULL UNIQUE           COMMENT '세션 식별자',
    keywords         TEXT          NOT NULL DEFAULT ''       COMMENT '키워드 콤마 join 문자열 (백엔드 처리)',
    description      TEXT          NOT NULL DEFAULT ''       COMMENT 'user_summary.summary 텍스트',
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '백엔드에서 채움',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- [x] **A-2: Docker 재초기화**

```bash
cd dev/local_db && docker compose -f docker-compose.db.yml down -v && docker compose -f docker-compose.db.yml up -d
docker exec mindlog-mysql mysql -u mindlog -pmindlog mindlog -e "SHOW TABLES;"
```

Expected: `content_analyses`, `user_summaries` 테이블 포함

- [x] **A-3: 실패 테스트 작성**

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_content_analyzer_keeps_existing_publisher_and_adds_user_summary():
    """기존 publisher.publish(전체 데이터) 유지 + ingest_user_summary 신규 호출 검증."""
    from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

    mock_llm_return = {
        "main_theme": "직장 스트레스",
        "sub_themes": ["번아웃"],
        "user_summary": {"keywords": ["번아웃", "스트레스"], "summary": "많이 힘드셨군요."},
        "target_duration": 4,
        "narrative_structure": "reflection",
    }
    agent = ContentAnalyzerAgent()
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value=mock_llm_return)), \
         patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as mock_pub_cls, \
         patch("src.agents.podcast.content_analyzer.BackendClient") as mock_bc_cls:
        mock_pub_cls.return_value.publish = AsyncMock(return_value=True)
        mock_bc_cls.return_value.ingest_mind_frequencies = AsyncMock()
        mock_bc_cls.return_value.ingest_user_summary = AsyncMock()
        mock_bc_cls.return_value.close = AsyncMock()
        await agent({"user_input": "직장 스트레스", "user_id": "u1", "session_id": "s1"})

    # 기존 publisher: 1회 (전체 validated_analysis)
    mock_pub_cls.return_value.publish.assert_called_once()
    pub_kwargs = mock_pub_cls.return_value.publish.call_args.kwargs
    assert pub_kwargs["resource"] == "content_analyses"
    assert "main_theme" in pub_kwargs["data"]   # 전체 데이터 포함

    # 신규 ingest_user_summary: 1회 (keywords list + description)
    mock_bc_cls.return_value.ingest_user_summary.assert_called_once()
    us_kwargs = mock_bc_cls.return_value.ingest_user_summary.call_args.kwargs
    assert us_kwargs["session_id"] == "s1"
    assert us_kwargs["keywords"] == ["번아웃", "스트레스"]   # list[str] 전송
    assert us_kwargs["description"] == "많이 힘드셨군요."
```

- [x] **A-4: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/podcast/test_content_analyzer_publisher.py -v
```

- [x] **A-5: backend_resources.py + client.py + content_analyzer.py 수정**

`src/api/backend_resources.py`에 상수 추가:
```python
RESOURCE_USER_SUMMARY = "user_summaries"  # POST /greenroom/ingest/ai/user_summaries
```

`src/api/client.py`에 신규 메서드 추가 (`ingest_mind_frequencies` 이후):
```python
async def ingest_user_summary(
    self, session_id: str, keywords: list[str], description: str
) -> None:
    """user_summaries 수집 엔드포인트 호출 (fire-and-forget).

    POST {base_url}/user_summaries
    keywords는 list[str]로 전송 — 백엔드에서 콤마 join 후 저장.
    실패 시 로그만 기록하고 파이프라인에 영향을 주지 않는다.
    """
    try:
        response = await self._client.post(
            f"{self._base_url}/{RESOURCE_USER_SUMMARY}",
            json={
                "session_id": session_id,
                "keywords": keywords,
                "description": description,
            },
        )
        response.raise_for_status()
    except Exception as e:
        _logger.warning("[BackendClient] ingest_user_summary failed (ignored): %s", e)
```

`src/agents/podcast/content_analyzer.py` — 기존 publisher 유지 + 신규 ingest 추가:

```python
# 변경 전 (기존 코드 — 유지)
publisher = AgentDataPublisher()
await publisher.publish(
    resource=RESOURCE_CONTENT_ANALYSIS,
    data=validated_analysis,
    user_id=state.get("user_id", ""),
    session_id=session_id,
)

# 변경 후 (기존 코드 유지 + 신규 추가)
publisher = AgentDataPublisher()

# (기존 유지) 전체 분석 결과 저장
await publisher.publish(
    resource=RESOURCE_CONTENT_ANALYSIS,
    data=validated_analysis,
    user_id=state.get("user_id", ""),
    session_id=session_id,
)

# (신규 추가) user_summary 별도 저장 — 화면 1 전용 (user_id 없음, 백엔드 패턴)
user_summary = validated_analysis.get("user_summary", {})
await backend_client.ingest_user_summary(
    session_id=session_id,
    keywords=user_summary.get("keywords", []),
    description=user_summary.get("summary", ""),
)
```

> ℹ️ `backend_client`는 이미 `ingest_mind_frequencies` 호출 시 생성된 인스턴스 재사용. `ingest_user_summary` 호출을 `ingest_mind_frequencies` 호출 이후에 추가한다.

- [x] **A-6: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/ -v
```

- [x] **A-7: 커밋**

```bash
git add dev/local_db/mysql/init.sql \
    src/api/backend_resources.py \
    src/api/client.py \
    src/agents/podcast/content_analyzer.py \
    tests/agents/podcast/test_content_analyzer_publisher.py
git commit -m "feat: ContentAnalyzer user_summary 별도 저장 추가 + user_summaries 테이블 + BackendClient.ingest_user_summary()"
```

### mind_frequencies 로깅 수정

> ⚠️ **문제 확인**: 경로(`/greenroom/ingest/ai/mind-frequencies`) · 시그니처는 백엔드와 호환이나 **데이터 미적재** 신고 받음.
> - **성공 로그 없음**: 호출 성공 시 아무것도 로그하지 않아 실제 실행 여부 확인 불가
> - **에러 로그 수준 낮음**: 실패 시 `_logger.warning` (WARNING 레벨 — 로그 필터에서 누락될 수 있음)
> - **중복 try/except**: `content_analyzer.py`의 outer try/except는 `ingest_mind_frequencies`가 내부에서 예외를 먹기 때문에 실제로 실행되지 않는 죽은 코드

- [x] **B-1: 실패 테스트 작성 — 로깅 검증**

`tests/api/test_client.py` (기존 파일에 테스트 추가):

```python
@pytest.mark.asyncio
async def test_ingest_mind_frequencies_logs_on_success(caplog):
    """성공 시 INFO 레벨 로그가 남아야 한다."""
    import logging
    client = BackendClient(base_url="http://test")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    with caplog.at_level(logging.INFO, logger="src.api.client"):
        with patch.object(client._client, "post", return_value=mock_resp):
            await client.ingest_mind_frequencies(
                session_id="s1", keywords=["번아웃"], description="힘든 하루"
            )

    assert any("ingest_mind_frequencies" in r.message and "s1" in r.message
                for r in caplog.records), "성공 시 INFO 로그 필수"


@pytest.mark.asyncio
async def test_ingest_mind_frequencies_logs_error_at_error_level(caplog):
    """실패 시 ERROR 레벨 로그가 남아야 한다 (WARNING 아님)."""
    import logging
    client = BackendClient(base_url="http://test")

    with caplog.at_level(logging.ERROR, logger="src.api.client"):
        with patch.object(client._client, "post", side_effect=Exception("connection refused")):
            await client.ingest_mind_frequencies(
                session_id="s1", keywords=["번아웃"], description="힘든 하루"
            )

    assert any(r.levelno == logging.ERROR for r in caplog.records), "실패 시 ERROR 레벨 필수"
```

- [x] **B-2: 테스트 실행 (실패 확인)**

```bash
pytest tests/api/test_client.py -k "mind_frequencies" -v
```

Expected: FAIL — 성공 로그 없음, WARNING 레벨

- [x] **B-3: client.py — ingest_mind_frequencies 로깅 수정**

`src/api/client.py:149-168` 수정:

```python
# 변경 전:
async def ingest_mind_frequencies(
    self, session_id: str, keywords: list[str], description: str
) -> None:
    try:
        response = await self._client.post(
            f"{self._base_url}/{RESOURCE_MIND_FREQUENCIES}",
            json={"session_id": session_id, "keywords": keywords, "description": description},
        )
        response.raise_for_status()
    except Exception as e:
        _logger.warning("[BackendClient] ingest_mind_frequencies failed (ignored): %s", e)

# 변경 후:
async def ingest_mind_frequencies(
    self, session_id: str, keywords: list[str], description: str
) -> None:
    """mind-frequencies 수집 엔드포인트 호출 (fire-and-forget).

    POST {base_url}/mind-frequencies
    실패 시 ERROR 로그만 기록하고 파이프라인에 영향을 주지 않는다.
    """
    try:
        response = await self._client.post(
            f"{self._base_url}/{RESOURCE_MIND_FREQUENCIES}",
            json={"session_id": session_id, "keywords": keywords, "description": description},
        )
        response.raise_for_status()
        _logger.info(
            "[BackendClient] ingest_mind_frequencies OK (session=%s, keywords=%d개)",
            session_id,
            len(keywords),
        )
    except Exception as e:
        _logger.error(
            "[BackendClient] ingest_mind_frequencies FAILED (session=%s): %s",
            session_id,
            e,
        )
```

- [x] **B-4: content_analyzer.py — 중복 try/except 제거**

`src/agents/podcast/content_analyzer.py:125-138` 수정:

```python
# 변경 전 (중복 try/except — outer except는 실제로 실행되지 않음):
backend_client = BackendClient()
try:
    keywords: list[str] = validated_analysis.get("sub_themes", [])
    description: str = validated_analysis.get("main_theme", "")
    await backend_client.ingest_mind_frequencies(
        session_id=session_id,
        keywords=keywords,
        description=description,
    )
except Exception as e:
    self.logger.warning("[ContentAnalyzer] ingest_mind_frequencies failed (ignored): %s", e)
finally:
    await backend_client.close()

# 변경 후 (ingest_mind_frequencies가 자체적으로 예외 처리 + 로깅):
backend_client = BackendClient()
try:
    keywords: list[str] = validated_analysis.get("sub_themes", [])
    description: str = validated_analysis.get("main_theme", "")
    await backend_client.ingest_mind_frequencies(
        session_id=session_id,
        keywords=keywords,
        description=description,
    )
finally:
    await backend_client.close()
```

- [x] **B-5: 테스트 실행 (통과 확인)**

```bash
pytest tests/api/test_client.py -k "mind_frequencies" -v
```

Expected: PASS

- [x] **B-6: 커밋**

```bash
git add src/api/client.py src/agents/podcast/content_analyzer.py \
    tests/api/test_client.py
git commit -m "fix: ingest_mind_frequencies 로깅 수정 — 성공 INFO + 실패 ERROR + content_analyzer 중복 try/except 제거"
```

---

## ⛔ [보류] Task 11: EpisodeSummaryAgent 구현

**Files:**
- Modify: `dev/local_db/mysql/init.sql` — `episode_summaries` 테이블 추가
- Create: `src/agents/podcast/episode_summary.py`
- Create: `prompts/podcast/episode_summary.yaml`
- Create: `tests/agents/test_episode_summary.py`
- Modify: `src/api/backend_resources.py` — `RESOURCE_EPISODE_SUMMARY` 추가

**역할:** TIER 4 완료 후 비동기로 `final_output`을 받아 에피소드 요약 텍스트 생성 → `episode_summaries` 테이블 저장.
저장 시 `user_id` + `session_id` + `episode_id` 포함 — 유저별 조회 및 격리 보장.

- [ ] **Step 1: init.sql — episode_summaries 테이블 추가**

`dev/local_db/mysql/init.sql`에 기존 테이블 아래에 추가:

```sql
-- ------------------------------------------------------------
-- episode_summaries (EpisodeSummaryAgent — 에피소드 목록 화면용)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS episode_summaries (
    summary_id    VARCHAR(128)  NOT NULL  PRIMARY KEY
                                          COMMENT 'summary_{episode_id}',
    episode_id    VARCHAR(64)   NOT NULL  UNIQUE
                                          COMMENT 'FK → podcast_episodes.episode_id (UNIQUE: 에피소드당 1건)',
    session_id    VARCHAR(64)   NOT NULL,
    user_id       VARCHAR(64)   NOT NULL,
    summary_text  TEXT          NOT NULL  DEFAULT ''
                                          COMMENT '2~3문장 에피소드 요약 (화면 3 표시용)',
    created_at    DATETIME      NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES podcast_episodes(episode_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)         ON DELETE CASCADE,
    FOREIGN KEY (user_id)    REFERENCES users(user_id)               ON DELETE CASCADE,
    INDEX idx_summary_user_created (user_id, created_at),
    INDEX idx_summary_episode (episode_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- [ ] **Step 2: Docker 재초기화 확인**

```bash
cd dev/local_db && docker compose -f docker-compose.db.yml down -v && docker compose -f docker-compose.db.yml up -d
docker exec mindlog-mysql mysql -u mindlog -pmindlog mindlog -e "SHOW TABLES;"
```

Expected: `episode_summaries` 포함

- [ ] **Step 3: RESOURCE 상수 추가**

`src/api/backend_resources.py`:

```python
RESOURCE_EPISODE_SUMMARY = "episode_summaries"
TYPE_EPISODE_SUMMARY = "episode_summary"
```

- [ ] **Step 4: 실패 테스트 작성**

`tests/agents/test_episode_summary.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_episode_summary_returns_summary_text():
    """EpisodeSummaryAgent가 episode_summary 필드를 반환해야 한다."""
    from src.agents.podcast.episode_summary import EpisodeSummaryAgent
    agent = EpisodeSummaryAgent()
    state = {
        "final_output": '{"episode_id": "ep_test_001", "episode_title": "직장 스트레스 극복기", "script_text": "오늘 힘든 하루였죠? 함께 이야기해 볼게요.", "tts_markers": []}',
        "user_id": "user_1",
        "session_id": "sess_1",
    }
    with patch.object(agent, "call_llm_json", new=AsyncMock(return_value={"summary_text": "직장 스트레스를 함께 풀어보는 에피소드입니다."})), \
         patch("src.agents.podcast.episode_summary.AgentDataPublisher") as mock_pub_cls:
        mock_pub_cls.return_value.publish = AsyncMock(return_value=True)
        result = await agent.process(state)
    assert "episode_summary" in result
    assert isinstance(result["episode_summary"], str)
    assert len(result["episode_summary"]) > 0
    mock_pub_cls.return_value.publish.assert_called_once()
    pub_kwargs = mock_pub_cls.return_value.publish.call_args.kwargs
    assert pub_kwargs["data"]["episode_id"] == "ep_test_001"
    assert "summary_text" in pub_kwargs["data"]

@pytest.mark.asyncio
async def test_episode_summary_fallback_on_empty_final_output():
    """final_output이 없으면 빈 문자열을 반환해야 한다."""
    from src.agents.podcast.episode_summary import EpisodeSummaryAgent
    agent = EpisodeSummaryAgent()
    result = await agent.process({"final_output": "", "user_id": "u1", "session_id": "s1"})
    assert result["episode_summary"] == ""
```

- [ ] **Step 5: 테스트 실행 (실패 확인)**

```bash
pytest tests/agents/test_episode_summary.py -v
```

Expected: FAIL — EpisodeSummaryAgent 없음

- [ ] **Step 6: EpisodeSummaryAgent 구현**

`src/agents/podcast/episode_summary.py`:

```python
"""EpisodeSummaryAgent — 에피소드 최종 출력 기반 요약 생성 (비동기 후처리)."""
from __future__ import annotations
import json
from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.api.backend_resources import RESOURCE_EPISODE_SUMMARY
from src.api.publisher import AgentDataPublisher
from src.models.agent_state import AgentState


class EpisodeSummaryAgent(BaseAgent):
    """비동기 후처리 — final_output을 2~3문장으로 요약하여 episode_summaries에 저장."""

    def __init__(self) -> None:
        super().__init__(name="episode_summary", tier=4)

    async def process(self, state: AgentState) -> dict[str, Any]:
        final_output = state.get("final_output", "")
        if not final_output:
            return {"episode_summary": ""}

        try:
            script_data = json.loads(final_output)
        except json.JSONDecodeError:
            return {"episode_summary": ""}

        episode_title = script_data.get("episode_title", "")
        # v3.0: script_text 단일 필드에서 미리보기 추출 (최대 600자)
        script_preview = script_data.get("script_text", "")[:600]

        llm_result = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=self.get_prompt("user_template").format(
                episode_title=episode_title,
                script_preview=script_preview,
            ),
        )
        summary_text = llm_result.get("summary_text", "")

        # episode_id는 final_output JSON(PersonalizedScript)에 포함됨
        # script_draft는 AgentState에 없으므로 script_data(이미 파싱)에서 꺼냄
        episode_id = script_data.get("episode_id", "")
        summary_id = f"summary_{episode_id}"  # episode_summaries PK
        publisher = AgentDataPublisher()
        await publisher.publish(
            resource=RESOURCE_EPISODE_SUMMARY,
            data={
                "summary_id": summary_id,   # PK — 테이블 PRIMARY KEY
                "summary_text": summary_text,
                "episode_id": episode_id,
            },
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
        )

        return {"episode_summary": summary_text}


async def episode_summary_node(state: AgentState) -> dict[str, Any]:
    """workflow.py에서 import하여 사용 — learning_node과 동일 패턴."""
    agent = EpisodeSummaryAgent()
    return await agent(state)  # __call__ 사용 (process() 직접 호출 금지)
```

- [ ] **Step 7: 프롬프트 YAML 작성**

`prompts/podcast/episode_summary.yaml`:

```yaml
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: |
      당신은 멘탈케어 팟캐스트 에피소드를 2~3문장으로 요약하는 전문가입니다.
      사용자가 이 에피소드를 보고 재청취 여부를 결정할 수 있도록
      핵심 내용과 감정적 가치를 간결하게 전달하세요.

      반드시 JSON으로만 응답하세요:
      {"summary_text": "2~3문장 요약"}

      조건:
      - 총 100자 이내
      - 에피소드 제목과 핵심 내용 포함
      - 사용자 감정에 공감하는 톤
      - 예시: "직장에서의 배신감을 함께 들여다보는 에피소드입니다. 감정을 정리하고 앞으로 나아갈 방향을 찾아볼게요."

    user_template: |
      에피소드 제목: {episode_title}
      내용 미리보기: {script_preview}
```

- [ ] **Step 8: 테스트 통과 확인**

```bash
pytest tests/agents/test_episode_summary.py -v
```

Expected: PASS

- [ ] **Step 9: 커밋**

```bash
git add src/agents/podcast/episode_summary.py prompts/podcast/episode_summary.yaml \
    tests/agents/test_episode_summary.py \
    dev/local_db/mysql/init.sql \
    src/api/backend_resources.py
git commit -m "feat: EpisodeSummaryAgent 구현 — 비동기 에피소드 요약 생성 + episode_summaries 저장"
```

---

## 연쇄 영향 체크리스트

| 항목 | 영향 | 확인 |
|------|------|------|
| GoT→Neo4j/graph_nodes 유지 | PR #50,#51,#88 결과 유지 | ✅ 변경 없음 |
| `ingest_podcast_episodes()` 시그니처 변경 | `(texts, title, summary, keywords)` 제거 → `text: str` 단일화 (3개 파라미터) | ⚠️ client.py + 호출부 동시 수정 필수 (Task 8) |
| `_save_core_data()` 확장 | 감정 컬럼 추가 + ingest 호출부 수정 | ⚠️ 기존 mock 테스트 파라미터 갱신 필요 (Task 8) |
| `podcast_segments` 테이블 제거 | init.sql에서 삭제 — Docker 재초기화 필요 | ✅ 읽는 코드 없음 (v3.0 폐기) |
| Emotion publisher 유지 | emotion_logs 저장 — **변경 없음** | ✅ 기존 테스트 영향 없음 |
| Content publisher 신규 추가 | user_summaries 신규 저장 추가 (기존 content_analyses 유지) | ⚠️ 신규 테스트 작성 필요 (Task 9) |
| `ingest_mind_frequencies()` 로깅 수정 | 성공 로그 추가 + 에러 WARNING→ERROR 격상 + content_analyzer.py 중복 try/except 제거 | ⚠️ Task 9 포함 |

## 미구현 범위 (이 계획 외)

- **PodcastReprocessingAgent / EpisodeSummaryAgent** — 백엔드 테이블(`podcast_episodes_anonymized`, `episode_summaries`) 미확보로 보류 (구 Task 1~6, 11)
- **AgentState 재가공 필드** (`reprocessed_output`, `anonymization_report`, `episode_summary`) — 위 에이전트 보류에 따라 보류
- **workflow.py `episode_summary_node`** — 위 에이전트 보류에 따라 보류
- **`POST /api/episodes/{id}/reprocess` 엔드포인트** — PodcastReprocessingAgent 트리거용, 백엔드 합의 필요
- GoT/Neo4j/graph_nodes 저장 변경 — 완료된 테스트 보호
- knowledge_results, risk_level, risk_score 미사용 필드 정리 — 향후 별도 검토
- DB 불일치 컬럼(turn_count, turn_id) 제거 — 대화모드 미구현과 연계
- NER 모델 통합 (Pororo/KoBERT) — Phase 2 (중기)
- 에피소드 목록 화면 Backend API — Backend팀 구현 대상

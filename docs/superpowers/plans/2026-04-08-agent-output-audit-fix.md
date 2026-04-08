# Agent Output Audit Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에이전트 출력 감사에서 발견된 이슈를 수정한다. 에이전트가 빈 값을 참조하는 상황을 없애고, 프롬프트 출력 스키마와 코드가 일치하도록 맞춘다.

> **2026-04-08 코드 직접 점검 결과:**
> - **IC-1 수정 완료**: `_extract_intent_dict()` 정적 메서드(line 596–616)가 이미 whitelist 추출을 수행한다. Task 1은 건너뛴다.
> - **총 이슈**: Task 1 포함 원래 14건 → IC-1 완료 제외 **13건 미수정**
> - **DB 아키텍처 검증 완료**: 모든 에이전트가 MySQL에 직접 접근하지 않음. publisher.publish() 또는 BackendClient.save()를 통해서만 저장. Neo4j/Pinecone 직접 접근은 설계 원칙에 부합.
> - **DB 스키마 무변형 확인**: 이 계획의 모든 Task는 에이전트 내부 코드만 수정하며 DB 스키마를 변경하지 않는다. content_analyses 테이블에 `_build_db_payload()`로 기존 컬럼 유지.

**Architecture:** TIER 0 → 1 → 2 → 3 → 4 순서로 수정한다. 상위 TIER의 출력이 바뀌면 하위 TIER가 받는 값도 바뀌기 때문에, 반드시 파이프라인 순서를 지켜야 한다.

**Deployment:** AWS 기준 (`ap-northeast-2` Bedrock, S3 `mindlog-images`, Pinecone). 세부 환경 정보는 계획서 하단 "AWS 배포 환경" 섹션 참고.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, `unittest.mock.AsyncMock`, `unittest.mock.patch`

---

## 이 계획서를 읽기 전에 알아야 할 개념

### 파이프라인이란?
데이터가 에이전트를 순서대로 거치며 처리되는 흐름이다.

```
사용자 입력
  ↓
TIER 0: Intent Classifier  (의도 파악)
  ↓
TIER 1: Safety / Emotion / Content Analyzer / Podcast Reasoning  (분석, 동시 실행)
  ↓
TIER 2: Script Generator / Visualization  (생성, 동시 실행)
  ↓
TIER 3: Batch Validator  (검증)
  ↓
TIER 4: Script Personalizer  (개인화)
  ↓
팟캐스트 에피소드 출력
```

### DB 저장이란?
에이전트가 만든 결과물을 데이터베이스(DB)에 저장한다.
이 프로젝트에서 DB 저장은 두 가지 방식으로 이루어진다:

```
방식 1 — 에이전트가 직접 저장 (TIER 1 실행 중):
  Content Analyzer → publisher.publish() → backend API → DB (content_analyses 테이블)
  Emotion Agent    → publisher.publish() → backend API → DB (emotion_logs 테이블)

방식 2 — 라우트가 통합 저장 (TIER 4 완료 후):
  podcasts.py:_save_core_data() → backend API → DB (podcast_episodes, visualizations 테이블)
```

### 왜 DB 스키마 협의가 필요한가?
DB 테이블은 "어떤 칸(컬럼)에 어떤 데이터를 넣는지" 미리 정해진 구조(스키마)가 있다.

예를 들어 `content_analyses` 테이블에 `sub_themes` 컬럼이 있고 "값이 반드시 있어야 함(NOT NULL)"으로 설정되어 있다면:
→ 우리가 `sub_themes`를 보내지 않으면 → 백엔드에서 INSERT/UPDATE 오류 발생 → 저장 실패

이 DB 테이블 구조는 **백엔드 팀이 관리**한다. 우리(AI 서버)는 직접 수정할 수 없다.
따라서 **에이전트 출력에서 필드를 추가/삭제하기 전에 반드시 백엔드 팀과 협의**해야 한다.

### script_draft는 삭제되었나?
**아니다. script_draft는 현재도 활성 상태다.**
- `src/models/agent_state.py:46` — AgentState에 정의됨
- Script Generator → Batch Validator → Script Personalizer 순서로 전달되는 핵심 필드

### sub_themes는 어디서 오는가?

> **⚠️ 2026-04-08 정정**: 이전 분석에서 CA v2.1.0이 sub_themes를 제거했다고 기록했으나 오류였다.
> CA v2.1.0은 `prompts/podcast/content_analyzer.yaml:313-336`에서 **6개 필드를 필수 출력**하며,
> sub_themes 포함 금지 문구는 v1.1.0 프롬프트(line 48-287)에 있던 것이었다.

**프롬프트 버전별 sub_themes 변화:**
- v1.0.0 (주석 참고용): CA가 sub_themes, target_duration, narrative_structure를 LLM에서 직접 생성
- v1.1.0 (긴 프롬프트): CA에서 sub_themes **제거** → Podcast Reasoning 이관 (5개 필드만)
- v2.0.0 / v2.1.0 (현재 활성): sub_themes **복원** — 6개 필드 필수, "3개 이상 생성, 빈 배열 금지"

**실제 문제 (코드)**: CA v2.1.0 프롬프트는 sub_themes를 요청하지만,
`_validate_and_correct()` 코드에 최소 개수(min_sub_themes=3) 보장 로직이 없다.
LLM이 빈 배열을 반환하거나 필드를 생략해도 코드가 `[]`로 통과시킨다.

→ 결과: **Script Generator가 `content_analysis.sub_themes` = `[]` 을 받는 경우 발생**
→ 이 계획에서 수정한다 (Task 4 CA-2 + Task 5).

---

## 제외 항목 (Pinecone 연동 완료 후 별도 처리)

| 이슈 | 에이전트 | 상태 |
|------|---------|------|
| EM-1 | Episode Memory | ✅ **PR#86에서 완료** — Pinecone REST API 직접 연동, `suggested_personalization` 제거, `AgentState`에 `memory_write`/`memory_text`/`memory_metadata` 3개 필드 추가됨 |
| KA-1 | Knowledge Agent | ⏳ Pinecone 연동 완료 시 함께 처리 |
| PR-1 | Podcast Reasoning | ⏳ KA-1 완료 후 연동 — Pinecone 선행 필요 |

---

## DB 저장 변경 사항 — 백엔드 협의 목록

> **스키마 근거**: `dev/local_db/mysql/init.sql` + `src/api/external_schemas.py` + `docs/architecture/DATA_SCHEMA.md`
>
> **중요**: Content Analyzer는 현재 `validated_analysis` 단일 dict를 AgentState와 DB 저장 양쪽에 그대로 사용한다.
> Task 4에서는 이 두 경로를 분리한다 — AgentState는 6개 필드(sub_themes min 보장), DB 저장은 target_duration/narrative_structure 기본값 추가.

> **2026-04-08 추가 검토 항목 — `podcast_episodes.safety_status` 컬럼**
>
> 현재 `src/api/external_schemas.py:809`에 프론트엔드 응답 필드(`safety_status`)로 정의되어 있어,
> 백엔드가 프론트엔드에 이 값을 전달하고 있다. 단순히 `safety_flags.get("status", "safe")`를 저장하는 컬럼이므로
> "실제로 프론트엔드가 이 값을 사용하는가?" 를 백엔드 팀과 확인 후 삭제 여부를 결정해야 한다.
> 현재 API 테스트가 진행 중이므로 이번 계획에서는 **현상 유지**, 별도 협의 항목으로 기록한다.

---

### 에이전트별 저장 경로 전체 맵

코드베이스 직접 분석 결과 (`src/agents/podcast/`, `src/api/routes/podcasts.py`):

| 에이전트 | 저장 방식 | resource | 대응 테이블 | 테이블 존재 여부 |
|---------|---------|---------|-----------|--------------|
| Content Analyzer | `publisher.publish()` (TIER 1) | `content_analyses` | `content_analyses` | ❓ **로컬 미정의** |
| Emotion Agent | `publisher.publish()` (TIER 1) | `emotion_logs` | `emotion_logs` | ✅ |
| Podcast Reasoning | `publisher.publish()` (TIER 1, GoT만) | `graph_analyses` | `graph_analyses` | ❓ **로컬 미정의** |
| Learning Agent | `client.save()` (비동기) | `learning` | `learning_patterns` | ✅ |
| Visualization | routes가 저장 (`_save_core_data`) | `visualizations` | `visualization_meta` | ✅ |
| 전체 에피소드 | routes가 저장 (`_save_core_data`) | `podcast_episodes` | `podcast_episodes` | ✅ |

> 로컬 스키마에 없는 두 리소스(`content_analyses`, `graph_analyses`)는 백엔드 서버가 실제 테이블을 보유할 가능성이 높다.
> `src/api/backend_resources.py`에 `RESOURCE_CONTENT_ANALYSIS`, `RESOURCE_GRAPH_ANALYSIS`로 명시적으로 등록되어 있고,
> 현재 코드가 실제로 save 호출을 하고 있기 때문이다. 백엔드에서 테이블 존재 여부를 확인해야 한다.

---

### 우선순위 요약

| 리소스 | 협의 필요 여부 | 이유 |
|--------|-------------|------|
| `content_analyses` | ⚠️ **협의 필수** | 로컬 스키마 미정의. 테이블 확인 + sub_themes 컬럼 유지 여부 확인 필요 |
| `graph_analyses` | ℹ️ **확인 권장** | 로컬 스키마 미정의. 이번 계획의 직접 수정 대상은 아님 |
| `podcast_episodes` | ✅ 협의 불필요 | 컬럼 모두 확인 완료, DEFAULT 있음 |
| `emotion_logs` | ✅ 협의 불필요 | EA-1이 수정하는 `emotional_journey_hint`는 DB 컬럼 아님 |
| `visualization_meta` | ✅ 협의 불필요 | Task 7이 NOT NULL 위반 위험 줄임 |

---

### [⚠️ 협의 필수] content_analyses

**영향 Task:** Task 4 (CA-1 + CA-2)

#### 현황

Content Analyzer는 `_validate_and_correct()` 결과를 **AgentState와 DB 양쪽에 동일하게** 사용한다:

```
현재 코드 흐름 (src/agents/podcast/content_analyzer.py:115-121):
    validated_analysis = self._validate_and_correct(llm_analysis, depth_level)
    await publisher.publish(data=validated_analysis)   ← DB에 저장
    return {"content_analysis": validated_analysis}   ← AgentState에 저장
```

현재 `validated_analysis`에 포함되는 필드:
`main_theme`, **`sub_themes`** (=`[]`), `emotional_journey`(`resolution` 3-키), **`target_duration`** (=`4`), **`narrative_structure`** (=`"reflection"`), `key_messages`, `depth_level`

CA v2.1.0 프롬프트는 sub_themes를 6개 필드 중 하나로 포함한다. 그러나 `target_duration`과 `narrative_structure`는 v2.1.0에 없으며, 코드가 기본값으로 채워 DB에 전송한다. sub_themes는 코드 min 보장 로직 부재로 빈 배열이 통과될 수 있다. `emotional_journey`는 3-키(`resolution`) 구조로, 백엔드 API 계약(4-키: `climax/closing`)과 불일치한다.

#### 문제

`content_analyses` 테이블이 로컬 스키마(`init.sql`, `external_schemas.py`, `DATA_SCHEMA.md`)에 **정의되지 않음**.
따라서 현재 백엔드 테이블의 컬럼 구조를 알 수 없다.

#### Task 4에서의 처리 방향

**CA v2.2.0 이후 AgentState와 DB 저장을 9+1 구조로 통일한다:**

| 경로 | 포함 필드 | 이유 |
|-----|---------|-----|
| AgentState (`content_analysis`) | 9개: `user_summary`, `main_theme`, `emotional_journey`(4-키), `key_messages`, `depth_level`, `sub_themes`, `target_duration`, `narrative_structure`, `confidence` | v2.2.0 전체 출력 스펙. 백엔드 API 계약 완전 일치 |
| DB 저장 (`_build_db_payload`) | 9개 필드 + `trace_id` (AgentState에서 추출) | content_analyses 테이블 최종 형태 (백엔드 계약 확정) |

`sub_themes`는 min 보장으로 3개 이상. `emotional_journey`는 4-키(`opening/development/climax/closing`)로 변경. `confidence`는 LLM이 직접 생성하는 신규 필드. `trace_id`는 DB 저장 시 data 내 포함.

#### 백엔드에 요청할 내용

1. `content_analyses` 테이블 존재 여부 확인
2. 테이블이 있다면 아래 컬럼들의 NOT NULL 여부 확인:

| 컬럼명 | Task 4 이후 전송 값 | NOT NULL 위험 |
|-------|-----------------|-------------|
| `user_summary` | `{"keywords": [...], "summary": "..."}` (구조 보장됨) | 없음 |
| `main_theme` | 비어있지 않은 문자열 | 없음 |
| `emotional_journey` | `{"opening": "...", "development": "...", "climax": "...", "closing": "..."}` (4-키, CA-3 확정) | 없음 |
| `key_messages` | 문자열 배열 최대 5개 | 없음 |
| `depth_level` | `"deep"` / `"moderate"` / `"light"` | 없음 |
| `sub_themes` | 실제 값 3개 이상 — CA v2.2.0 min 보장 후 | ✅ 실제 값 전송 (NOT NULL 호환) |
| `target_duration` | LLM 생성 값 + clamp(3-5) — CA v2.2.0에서 복원 | 없음 |
| `narrative_structure` | LLM 생성 유효값 — CA v2.2.0에서 복원 | 없음 |
| `confidence` | LLM 생성 float (0.0-1.0) — CA v2.2.0 신규 | 없음 |
| `trace_id` | AgentState에서 추출, data 내 포함 | 없음 |

3. 테이블이 없다면 위 컬럼 구조로 생성 요청

> **구현 순서**: Task 4 코드 수정은 백엔드 확인과 무관하게 진행 가능하다. DB 저장 페이로드를 그대로 유지하므로 기존 동작과 호환된다.

---

### [ℹ️ 확인 권장] graph_analyses

**영향 Task:** 없음 (이번 계획의 수정 대상 아님)

Podcast Reasoning이 GoT 결과를 `graph_analyses` 리소스에 publish한다 (`podcast_reasoning.py:603-613`):

```python
await publisher.publish(
    resource=RESOURCE_GRAPH_ANALYSIS,  # "graph_analyses"
    data={"got_result": ..., "graph_data": ..., "category_distribution": ...},
    ...
)
```

이 리소스도 로컬 스키마에 정의되지 않았다. 백엔드 서버가 처리하는 구조로, 이번 계획에서 수정하지 않는다.
백엔드 팀에 테이블 존재 여부와 구조를 별도로 확인하는 것을 권장한다.

---

### [✅ 협의 불필요] podcast_episodes

**영향 Task:** Task 1 (IC-1), Task 2 (SA-1+SA-2), Task 8 (BV-1)

실제 스키마 (`init.sql:76–100` 기준):

| 컬럼명 | 타입/제약 | Task 연관 | 판단 |
|-------|---------|---------|------|
| `intent_type` | `VARCHAR(100) DEFAULT 'unknown'` | Task 1 (IC-1) | DEFAULT 있음 → 협의 불필요. IC-1 수정 후 명시적 값 전송됨 |
| `safety_status` | `ENUM('safe','warning','crisis') DEFAULT 'safe'` | Task 2 (SA fix) | SA 출력 `status`는 이 ENUM 3개 중 하나 → 호환 ✅ |
| `validation_score` | `FLOAT DEFAULT 0.0` | Task 8 (BV-1) | BV 출력 `overall_score`는 float → 호환 ✅ |
| `cover_image_url` | `VARCHAR(512) nullable` | Task 7 (VI fix) | nullable이므로 없어도 OK ✅ |

---

### [✅ 협의 불필요] emotion_logs

**영향 Task:** Task 3 (EA-1)

EA-1이 수정하는 `emotional_journey_hint` 필드는 **`emotion_logs` 테이블 컬럼이 아니다.**

실제 `emotion_logs` 컬럼 (`init.sql:52–71`):
`log_id`, `session_id`, `user_id`, `mode`, `turn_id`, `episode_id`,
`primary_emotion` (NOT NULL), `intensity` (FLOAT NOT NULL), `valence` (FLOAT NOT NULL),
`arousal` (FLOAT NOT NULL), `secondary_emotions` (JSON DEFAULT []),
`tone_recommendation` (nullable), `trace_id`, `created_at`

→ `emotional_journey_hint`는 Emotion Agent가 AgentState에 담는 내부 필드.
   DB에는 전송되지 않으므로 Task 3 수정이 DB에 미치는 영향 없음.

---

### [✅ 협의 불필요] visualization_meta

**영향 Task:** Task 7 (VI-1 + VI-2)

실제 테이블명은 `visualizations`가 아니라 **`visualization_meta`**다 (`init.sql:143–158`).

주요 NOT NULL 제약:

| 컬럼명 | 타입/제약 | Task 7 이후 |
|-------|---------|-----------|
| `s3_key` | `VARCHAR(512) NOT NULL` | VI 정상 경로에서 채워짐 |
| `cdn_url` | `VARCHAR(512) NOT NULL` | VI 정상 경로에서 채워짐 |
| `image_prompt` | `TEXT NOT NULL` | VI 정상 경로에서 채워짐 |
| `interpretation_text` | `TEXT NOT NULL` | VI 정상 경로에서 채워짐 |

Task 7(VI-1/VI-2)은 에러 경로에서도 구조를 보장하도록 출력 검증을 강화한다.
이는 NOT NULL 제약 위반 위험을 줄이는 방향이므로 협의 불필요.

---

## 백엔드 API 계약 확정 (2026-04-09) — content_analysis 데이터 구조

> **출처**: 백엔드 팀과 협의 중인 API 페이로드 확정본

```json
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "session_id": "sess_a1b2c3d4e5f6",
  "type": "content_analysis",
  "data": {
    "main_theme": "직장 내 스트레스 관리와 마인드풀니스",
    "sub_themes": ["업무 과부하와 번아웃 예방", "마인드풀니스 기법 소개", "일상에서의 스트레스 해소법"],
    "target_duration": 5,
    "narrative_structure": "reflection",
    "depth_level": "moderate",
    "emotional_journey": {
      "opening": "공감과 인정",
      "development": "원인 탐색",
      "climax": "해결 전략",
      "closing": "희망과 동기부여"
    },
    "confidence": 0.85,
    "trace_id": "trace_abc123def456"
  },
  "timestamp": "2026-03-10T14:25:00.123456+00:00"
}
```

### 현재 코드와의 차이 분석 (5개 서브에이전트 점검 결과)

| 필드 | 현재 코드 상태 | API 계약 | 필요 작업 |
|------|-------------|---------|---------|
| `emotional_journey` 키 | `opening/development/resolution` (3개) | `opening/development/climax/closing` (4개) | **CA 프롬프트 v2.2.0 신규 작성 + 코드 구조 변경** |
| `confidence` | CA에서 생성 안 함 | float (0.85) | **CA 프롬프트에 추가, `_validate_and_correct()` 처리 추가** |
| `trace_id` | `publisher.publish()` 호출에 미전달 | data 내 포함 | **AgentState의 trace_id를 data에 포함** |
| `target_duration` | LLM 출력 + `clamp(3-5)` — ✅ 정상 | int (5) | 프롬프트에서 명시적으로 다시 요청 (v1.1.0 이후 제거됨) |
| `narrative_structure` | 유효값 검증 + fallback — ✅ 정상 | str ("reflection") | 프롬프트에서 명시적으로 다시 요청 |
| `sub_themes` | min 보장 코드 없음 | list 3개 이상 | min_sub_themes 보장 (CA-2) |
| `main_theme` | 100자 제한 — ✅ 정상 | str | 변경 없음 |
| `depth_level` | 코드가 결정 — ✅ 정상 | str | 변경 없음 |

### 중요: target_duration / narrative_structure 아키텍처 결정

**현재 설계**: Podcast Reasoning ToT가 target_duration/narrative_structure를 생성. CA는 코드 기본값(4/"reflection")으로 content_analyses에 전송.

**백엔드 계약 요구**: content_analysis 데이터에 실제 값 포함.

**결정 필요**: 아래 두 가지 중 선택:
- **Option A (권장)**: CA v2.2.0 프롬프트에 target_duration/narrative_structure 복원 → CA가 직접 생성해 content_analyses에 실제 값 전송. PR도 독립적으로 자체 에피소드 구조에 활용.
- **Option B**: 현재 구조 유지 (CA는 기본값, PR이 실제 값 생성). content_analyses에는 기본값이 저장됨 — 백엔드와 협의 필요.

---

## 수정 대상 전체 (TIER 순서)

```
TIER 0: [Task 1] IC-1 ✅ 수정 완료 — _extract_intent_dict() 이미 구현됨, 건너뜀
TIER 1: [Task 2] SA-1+SA-2         — Safety 출력 명시화
        [Task 3] EA-1              — Emotion 폴백 하드코딩 제거
        [Task 4] CA-1+CA-2+CA-3   — CA v2.2.0 프롬프트 신규 작성 + 4-키 emotional_journey + confidence + trace_id
TIER 1→2 연결:
        [Task 5] PR 수정            — sub_themes 상위 노출 + PR 프롬프트 climax/closing 반영
TIER 2: [Task 6] SG-1+SG-2         — Script Generator sub_themes 소스 수정 + resolution→closing 연쇄 수정
        [Task 7] VI-1+VI-2         — Visualization 출력 검증
TIER 3: [Task 8] BV-1+BV-2         — Batch Validator 명시 필드 추출
TIER 4: [Task 9] SP-1+SP-2         — Script Personalizer resolution→closing 참조 정정 (v2.2.0)
공용:  [Task 10] schemas.py EmotionalJourney 4-키 구조 변경 (전담 개발자 협의 필수)
```

> **실행 순서**: Task 1 건너뜀 → Task 2·3 (병렬 가능) → Task 4 → Task 10 → Task 5·6·9 (Task 4 완료 후) → Task 7·8 (병렬 가능)

---

## Task 1: IC-1 — Intent Classifier `intent` 필드 명시 추출 [TIER 0] ✅ 수정 완료

**담당 브랜치:** `feature/analysis-*`

> **2026-04-08 점검 결과: 이미 수정됨 — 이 Task는 건너뛴다.**
> `_extract_intent_dict()` 정적 메서드(line 596–616)가 whitelist 기반 명시 추출을 수행한다.
> `process()`의 모든 반환 경로(line 118, 161, 175)에서 이 메서드를 사용한다.

**무엇이 문제였나?**
~~현재 코드는 `IntentClassifierOutput.model_dump()`를 그대로 `intent` 필드에 저장한다.~~
이 경우 Pydantic 모델에 필드가 추가될 때마다 의도하지 않은 내부 필드가 `intent`에 포함될 수 있다.

**데이터 흐름:**
```
Intent Classifier → state["intent"] → (읽는 곳)
  1. Content Analyzer: state["intent"].get("complexity_score")
  2. Podcast Reasoning: state["intent"].get("complexity_score")
  3. podcasts.py:_save_core_data(): intent_data.get("intent_type"), intent_data.get("complexity_score")
```

**DB 저장 영향:**
`podcast_episodes` 테이블에 `intent_type` 값이 저장된다.
현재 코드: `intent_data.get("intent_type", "unknown")`
문제: `IntentClassifierOutput`에 `intent_type` 필드가 없고 `primary_intent`만 있을 경우, 항상 `"unknown"` 저장 → 기존 버그일 수 있음.
→ Step 1에서 반드시 확인 후 처리.

**Files:**
- Modify: `src/agents/podcast/intent_classifier.py`
- Check & possibly modify: `src/api/routes/podcasts.py:202`
- Modify: `tests/agents/podcast/test_intent_classifier.py`

- [ ] **Step 1: IntentClassifierOutput 필드와 라우트 사용처 확인**

```bash
grep -n "intent_type\|primary_intent\|IntentClassifierOutput\|class.*Output" src/agents/podcast/intent_classifier.py
grep -n "intent_type\|intent_data" src/api/routes/podcasts.py
```

결과를 보고 판단:
- **Case A**: `IntentClassifierOutput`에 `intent_type` 필드 있음 → 명시 추출 화이트리스트에 그대로 포함
- **Case B**: `IntentClassifierOutput`에 `primary_intent`만 있음 → `_save_core_data`에서 `intent_type` 읽는 줄을 `primary_intent`로 수정 (기존 버그 수정)

- [ ] **Step 2: 실패 테스트 작성**

`tests/agents/podcast/test_intent_classifier.py` 에 추가:

```python
@pytest.mark.asyncio
async def test_intent_field_has_no_internal_pydantic_fields() -> None:
    """intent 필드에 Pydantic 내부 필드가 포함되지 않는다 (IC-1)."""
    from src.agents.podcast.intent_classifier import IntentClassifierAgent
    from unittest.mock import AsyncMock, patch
    from src.models.agent_state import AgentState

    agent = IntentClassifierAgent()
    # LLM 응답에 내부 디버그 필드 포함 (실제로 LLM이 보낼 수 있는 임의 필드)
    mock_output = {
        "primary_intent": "stress_relief",
        "complexity_score": 0.7,
        "sub_intents": ["sleep", "anxiety"],
        "confidence": 0.9,
        "_internal_debug": "제거 대상",
        "raw_tokens": 125,
    }
    state = AgentState(
        user_input="스트레스 받아요", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_output):
        result = await agent.process(state)

    intent = result.get("intent", {})
    assert "_internal_debug" not in intent, "내부 디버그 필드 유입됨"
    assert "raw_tokens" not in intent, "내부 토큰 정보 유입됨"
    assert "primary_intent" in intent
    assert "complexity_score" in intent
```

- [ ] **Step 3: 실패 확인**

```bash
pytest tests/agents/podcast/test_intent_classifier.py::test_intent_field_has_no_internal_pydantic_fields -v -m "not live"
```

Expected: **FAIL** (model_dump() 전체가 intent에 들어가면 내부 필드가 포함됨)

- [ ] **Step 4: intent_classifier.py 수정 — 명시 추출**

```python
        # Step 1 결과에 따라 intent_type 포함 여부 결정
        intent_dict: dict[str, Any] = {
            "primary_intent":   str(output.get("primary_intent", "general")),
            "complexity_score": float(output.get("complexity_score", 0.5)),
            "sub_intents":      output.get("sub_intents", [])
                                if isinstance(output.get("sub_intents"), list) else [],
            "confidence":       float(output.get("confidence", 0.5)),
        }
        # Case A일 때만 아래 줄 추가:
        # intent_dict["intent_type"] = str(output.get("intent_type", "general"))
        return {"intent": intent_dict, ...}
```

- [ ] **Step 5: Case B 해당 시 — `_save_core_data` 수정**

`src/api/routes/podcasts.py` line 202:
```python
# Before (Case B일 때 항상 "unknown" 반환하는 기존 버그)
"intent_type": intent_data.get("intent_type", "unknown"),
# After
"intent_type": intent_data.get("intent_type", intent_data.get("primary_intent", "unknown")),
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_intent_classifier.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 7: 커밋**

```bash
git add src/agents/podcast/intent_classifier.py tests/agents/podcast/test_intent_classifier.py
git commit -m "fix(intent_classifier): IC-1 — intent 필드 명시 추출로 schema drift 방지"
```

---

## Task 2: SA-1 + SA-2 — Safety Agent 출력 명시화 [TIER 1]

**담당 브랜치:** `feature/reasoning-*`

**무엇이 문제인가?**
- SA-1: 현재 코드 `"safety_flags": result` — LLM 응답 전체를 그대로 저장. LLM이 스펙에 없는 필드를 추가 반환하면 그것도 포함됨.
- SA-2: LLM 호출 실패 시 반환하는 폴백 dict에 `"flags": {}` 키가 있음 — 이 필드는 현재 코드 어디서도 읽지 않는 레거시.

**Safety Agent v1.2.0 프롬프트 출력 스키마 (허용 필드만):**
```
status:             "safe" | "warning" | "crisis"
risk_level:         0 | 1 | 2 | 3
risk_score:         0.0 ~ 1.0
reasons:            list[str]  (위험 사유)
required_in_script: list[str]  (스크립트 필수 포함 문구)
```

**수정 후 safety_flags 구조 (4개 키만):**
```
status, risk_level, risk_score, required_in_script
```

> `reasons`는 `_extract_safety_alert`에서 사용되지 않으므로 safety_flags에서 제외.
> 단, SAFETY_MESSAGES 상수 주입 로직은 그대로 유지.

**데이터 흐름:**
```
Safety Agent → state["safety_flags"] → (읽는 곳)
  1. podcasts.py:_extract_safety_alert() → safety_flags.get("status")  ✅
  2. podcasts.py:_save_core_data()       → safety_flags.get("status")  ✅
  3. Script Generator (TIER 2)          → safety_flags.get("required_in_script")  ✅
```

**DB 저장 영향:** `podcast_episodes` 테이블의 `safety_status` 컬럼은 `safety_flags.get("status", "safe")`로 채움. 수정 후에도 `status` 필드는 유지 → **백엔드 협의 불필요** ✅

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

## Task 3: EA-1 — Emotion Agent 폴백 하드코딩 제거 [TIER 1]

**담당 브랜치:** `feature/reasoning-*`

**무엇이 문제인가?**
LLM 호출이 연속으로 실패할 경우, 모든 사용자가 동일한 4개 고정 감정 힌트를 받는다:
```python
"emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"]
```
이것은 실제 사용자 감정 분석이 아닌 하드코딩 값이다.

**데이터 흐름:**
```
Emotion Agent → state["emotion_vectors"] → publisher → emotion_logs DB
                                         → Script Generator (TIER 2)가 읽음
```

**DB 저장 영향:**
`emotion_logs` 테이블에 `emotional_journey_hint` 값이 `[]`로 저장됨 (기존: 4개 항목).
필드 자체는 유지, 값만 변경 → 백엔드 컬럼이 배열 타입이면 문제없음.
**백엔드에 형식 변경 고지 필요** (4개 → 0개).

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

## Task 4: CA-1 + CA-2 + CA-3 — Content Analyzer v2.2.0 전환 [TIER 1]

**담당 브랜치:** `feature/validation-*`

---

### 무엇이 문제인가?

Content Analyzer는 LLM에게 분석을 맡기고 그 결과를 `_validate_and_correct()` 메서드로 검증한 뒤 반환한다. 이 메서드에는 두 가지 문제가 있다.

---

**CA-1 문제: LLM 응답을 통째로 복사해서 쓴다**

현재 코드 (`content_analyzer.py:206`):
```python
corrected = dict(analysis)   # LLM이 준 딕셔너리 전체를 그대로 복사
```

이렇게 하면 LLM이 예상 외 필드를 추가로 반환했을 때 그게 그대로 `content_analysis`에 들어간다. 예를 들어 LLM이 `{"main_theme": "...", "user_summary": "문자열로 잘못 반환", "my_extra_field": "테스트"}` 라고 응답하면 코드는 이것을 그대로 통과시킨다.

- `user_summary`는 반드시 `{"keywords": [...], "summary": "..."}` 딕셔너리 형태여야 하는데, LLM이 가끔 문자열로 반환할 때 코드가 이를 잡지 못한다.
- `key_messages`는 반드시 리스트여야 하는데, LLM이 딕셔너리로 반환해도 코드가 모른다.
- 모르고 통과된 잘못된 값이 Script Generator까지 내려가면, 스크립트 생성 도중 예상 외 오류가 발생한다.

**왜 이게 나쁜가?** 코드가 "이 6개 필드만 사용한다"고 보장해주지 않으면, 나중에 누군가 "여기서 무슨 값이 나오는지"를 코드만 보고 알 수가 없다. 필드가 존재한다는 보장이 없는 것이다.

---

**CA-2 문제: `_validate_and_correct()`가 sub_themes 최소 개수를 보장하지 않는다**

> **⚠️ 2026-04-08 정정**: 이전 분석에서 "v2.1.0이 sub_themes를 제거했다"고 기록했으나 오류였다.
> `prompts/podcast/content_analyzer.yaml` v2.1.0 (line 313-336)은 **6개 필드 필수 출력** 지시.
> sub_themes 포함 금지 문구는 v1.1.0 (line 48-287)의 내용이었다.
>
> **실제 v2.1.0 프롬프트**: "sub_themes는 반드시 3개 이상 생성하세요. 빈 배열이면 안 됩니다."
> 따라서 **프롬프트 수정은 불필요하다. 코드만 수정하면 된다.**

현재 코드 (`content_analyzer.py:215-220`):
```python
sub_themes = corrected.get("sub_themes", corrected.get("themes", []))
if not isinstance(sub_themes, list):
    sub_themes = []
if len(sub_themes) > self.max_sub_themes:
    sub_themes = sub_themes[: self.max_sub_themes]
corrected["sub_themes"] = sub_themes   # 최솟값 검사 없음 — [] 그대로 통과
```

v2.1.0 프롬프트는 LLM에게 sub_themes를 3개 이상 생성하라고 요청하지만,
코드에는 최소 개수(min_sub_themes=3) 검사가 없다. LLM이 빈 배열을 반환하거나 필드를 생략해도
코드가 검사 없이 `[]`를 그대로 통과시킨다. 그 결과:
- `content_analysis.sub_themes`가 `[]`(빈 배열)일 수 있다
- Script Generator가 `content_analysis.sub_themes`를 읽으면 빈 배열을 받을 수 있다
- 팟캐스트 에피소드에 세부 주제가 없는 상태로 생성될 수 있다

또한 `target_duration`과 `narrative_structure`는 v2.1.0 프롬프트가 출력하지 않으나,
코드가 기본값(4, "reflection")으로 강제 추가한다. **백엔드 API 계약 확정으로 이 두 필드도 실제 LLM 값이 필요하다 (CA-3에서 처리).**

**CA-3 문제 (신규 — 백엔드 API 계약 확정):**

백엔드가 요구하는 `content_analysis` 데이터 구조와 현재 코드 간에 3가지 불일치가 있다:

1. **emotional_journey 4-키 불일치**: API 계약 → `opening/development/climax/closing`. 현재 코드 및 **모든 프롬프트 버전** → `opening/development/resolution` (3키). `climax`와 `closing`은 어느 버전에도 존재하지 않는다.

2. **confidence 필드 누락**: API 계약 → `float` 필수. 현재 CA 코드 → 생성하지 않음. `publisher.publish()` 호출에서도 미전달.

3. **trace_id 필드 누락**: API 계약 data 내 포함. 현재 CA → `publisher.publish()` 호출에 미전달.

4. **target_duration/narrative_structure**: API 계약 → 실제 값 (5, "reflection"). 현재 → 코드 기본값 하드코딩. **CA v2.2.0 프롬프트에서 다시 LLM이 생성하도록 복원 필요.**

---

### 어떻게 수정하는가?

**세 가지를 처리한다:**

1. **CA-1 수정**: `corrected = dict(analysis)` 전체 복사 방식을 버리고, 허용 필드를 명시적으로 추출한다. 각 필드의 타입도 직접 검증한다.

2. **CA-2 수정**: `_validate_and_correct()`에 sub_themes **최소 개수 보장 로직을 추가**한다.

3. **CA-3 수정 (신규)**: **CA v2.2.0 프롬프트 신규 작성** — 백엔드 API 계약의 4-키 emotional_journey, confidence, target_duration, narrative_structure를 LLM이 생성하도록 지시. `_validate_and_correct()`에 새 필드 검증 로직 추가.

**CA v2.2.0 필드 목록 (9개):**
```
user_summary        → {keywords: list, summary: str}
main_theme          → str
emotional_journey   → {opening, development, climax, closing}  ← 4개 키로 변경
key_messages        → list[str] (3-5개)
depth_level         → "shallow"|"medium"|"deep"  (코드가 결정)
sub_themes          → list[str] (3개 이상 필수, min 보장)
target_duration     → int (3-5분, clamp 유지)                  ← LLM에서 다시 생성
narrative_structure → str (유효값 검증 유지)                    ← LLM에서 다시 생성
confidence          → float (0.0-1.0, LLM이 생성)              ← 신규 추가
```

**trace_id 처리**: LLM이 생성하는 값이 아니다. AgentState에서 가져오거나 `publisher.publish()` 단에서 처리한다 (시스템 생성 트레이스).

**DB 저장 경로**: `_build_db_payload()`를 통해 모든 9개 필드 + trace_id를 전송.
- AgentState (`content_analysis` 키): 9개 필드 (`_validate_and_correct` 반환값)
- DB 페이로드 (`_build_db_payload` 경유): 9개 필드 + `trace_id`

---

### 왜 이렇게 하는가?

**emotional_journey 키 변경의 의미:**
- `resolution` (해소) → `climax` (해결 전략) + `closing` (희망/마무리) 로 분리
- 기존 3단계에서 4단계로 확장: 도입 → 탐색 → 해결(climax) → 희망(closing)
- Podcast Reasoning CoT 프롬프트도 이 4단계 구조를 반영하도록 업데이트 필요

**confidence 추가의 의미:**
- CA LLM이 자신의 분석에 대한 신뢰도를 직접 평가
- Script Generator나 Batch Validator가 낮은 confidence를 보고 처리 방식을 조정할 수 있음

---

### 수정 후 얻는 결과

- `content_analysis`에는 항상 정확한 타입으로 **9개 필드**가 존재한다.
- 백엔드 API 계약의 `content_analysis` 데이터 구조와 완전히 일치한다.
- `emotional_journey`가 4-키 구조(opening/development/climax/closing)로 명확해진다.
- `sub_themes`는 min_sub_themes(=3) 보장으로 **항상 3개 이상의 배열**이 된다.

**Content Analyzer v2.2.0 프롬프트 (목표 출력, 9개 필드):**
```
user_summary        → {keywords: list, summary: str}
main_theme          → str (100자 이내)
emotional_journey   → {opening: str, development: str, climax: str, closing: str}
key_messages        → list[str] (3-5개)
depth_level         → "shallow"|"medium"|"deep"  (코드가 결정)
sub_themes          → list[str] (3-5개, 필수 — 빈 배열 금지)
target_duration     → int (3-5분)
narrative_structure → "personal_story"|"expert_qa"|"reflection"|"comparative"
confidence          → float (0.0-1.0)
```

**DB 저장 영향:** `content_analyses` 테이블

- **AgentState** (`content_analysis` 키): 9개 필드 (`_validate_and_correct` 반환값)
- **DB 페이로드** (`_build_db_payload` 경유): 9개 필드 + `trace_id` (AgentState 또는 시스템 생성)

> ⚠️ **백엔드 협의 필수** (본 계획 상단 "DB 저장 변경 사항" 섹션 참조)
> 구현 전 백엔드 팀에 content_analyses 테이블 컬럼 구조 확인 요청. 코드 수정 자체는 선행 가능.

**Files:**
- Modify: `src/agents/podcast/content_analyzer.py:195–243`
- Modify: `tests/agents/podcast/test_content_analyzer.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/agents/podcast/test_content_analyzer.py` 하단에 추가:

```python
# === 8. v2.1.0 출력 필드 화이트리스트 + min_sub_themes 보장 ===


def test_validate_and_correct_excludes_unexpected_fields(
    agent: ContentAnalyzerAgent,
) -> None:
    """_validate_and_correct가 예상 외 LLM 필드를 결과에 포함하지 않는다 (CA-1).

    v2.1.0은 6개 필드만 출력함. LLM이 추가 필드를 돌려보내도 화이트리스트로 차단.
    """
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
    # sub_themes는 v2.1.0에 포함 — 결과에 있어야 함
    assert "sub_themes" in result
    assert len(result["sub_themes"]) >= 3, "min_sub_themes 보장"


def test_validate_and_correct_enforces_min_sub_themes(
    agent: ContentAnalyzerAgent,
) -> None:
    """LLM이 sub_themes를 빈 배열로 반환하면 min_sub_themes 미달로 처리된다 (CA-2).

    v2.1.0 프롬프트는 sub_themes 3개 이상을 요청하나, LLM이 규칙을 어길 수 있다.
    코드가 이를 보장해야 한다.
    """
    analysis = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "resolution": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": [],  # LLM이 빈 배열 반환 — min 미달
    }
    result = agent._validate_and_correct(analysis, depth_level="moderate")

    # min_sub_themes 보장: 빈 배열이 그대로 통과되면 안 됨
    assert len(result["sub_themes"]) >= agent.min_sub_themes, (
        f"sub_themes 최소 {agent.min_sub_themes}개 보장 실패"
    )


def test_build_db_payload_includes_legacy_fields(
    agent: ContentAnalyzerAgent,
) -> None:
    """_build_db_payload가 content_analyses DB용 레거시 필드를 기본값으로 포함한다.

    content_analyses 테이블은 target_duration, narrative_structure 컬럼을 보유할 수 있다.
    CA v2.1.0에서 이 값들이 LLM 출력에 없으므로 기본값으로 채워 전송한다.
    sub_themes는 AgentState와 동일한 실제 값이 포함된다.
    """
    validated = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "resolution": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],
    }
    db_payload = agent._build_db_payload(validated)

    # 레거시 필드가 기본값으로 포함되어야 함
    assert "target_duration" in db_payload
    assert "narrative_structure" in db_payload

    # 6개 필드도 그대로 포함
    assert db_payload["main_theme"] == "스트레스 관리"
    assert db_payload["depth_level"] == "moderate"
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
    """emotional_journey가 dict 아닐 때 4-키 빈 구조로 보정한다 (CA-1, CA-3).

    CA v2.2.0 기준: opening/development/climax/closing 4-키 구조를 보장한다.
    """
    analysis = {
        "user_summary": {}, "main_theme": "주제",
        "emotional_journey": "문자열로 잘못 반환",  # LLM 오류
        "key_messages": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="light")

    ej = result["emotional_journey"]
    assert isinstance(ej, dict)
    # CA v2.2.0: 4-키 구조 (resolution → climax + closing 분리)
    assert set(ej.keys()) == {"opening", "development", "climax", "closing"}


def test_validate_and_correct_ensures_confidence_is_float(
    agent: ContentAnalyzerAgent,
) -> None:
    """confidence 필드가 항상 0.0~1.0 float으로 보정된다 (CA-3)."""
    # LLM이 confidence를 문자열로 반환하거나 생략할 때
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
- `test_validate_and_correct_excludes_unexpected_fields`: `unknown_new_field`가 결과에 남아있음 (현재 `dict(analysis)` 전체 복사)
- `test_validate_and_correct_enforces_min_sub_themes`: 빈 배열이 min 검사 없이 통과됨

- [ ] **Step 3: `_validate_and_correct` 재구성 + `_build_db_payload` 추가**

`src/agents/podcast/content_analyzer.py` lines 195–243 교체:

```python
    def _validate_and_correct(self, analysis: dict[str, Any], depth_level: str) -> dict[str, Any]:
        """
        LLM 분석 결과를 v2.2.0 화이트리스트 기준으로 검증·추출한다.

        반환값은 AgentState용 9개 필드를 포함한다 (v2.2.0 출력 스펙 = 백엔드 API 계약 일치).
        DB 저장 시에는 _build_db_payload()로 trace_id를 추가한다.

        허용 필드 (9개):
            user_summary, main_theme, emotional_journey (4-키), key_messages,
            depth_level, sub_themes, target_duration, narrative_structure, confidence
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

        # 3. emotional_journey — CA v2.2.0 기준: 4-키 구조 강제
        #    백엔드 API 계약: opening/development/climax/closing
        #    이전 v2.1.0 이하: opening/development/resolution (3-키) — 더 이상 사용 안 함
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
        # min_sub_themes 미달 시: LLM이 규칙을 어긴 것 — main_theme 기반 기본값으로 채움
        if len(raw_themes) < self.min_sub_themes:
            self.logger.warning(
                "[ContentAnalyzer] sub_themes 개수 미달 (%d < %d) — 기본값으로 보정",
                len(raw_themes), self.min_sub_themes,
            )
            while len(raw_themes) < self.min_sub_themes:
                raw_themes.append(main_theme)  # main_theme을 fallback으로 사용

        # 6. target_duration — clamp(3-5). CA v2.2.0부터 LLM이 직접 생성
        target_duration = analysis.get("target_duration")
        if target_duration is not None:
            try:
                target_duration = int(target_duration)
            except (ValueError, TypeError):
                target_duration = 4
            target_duration = clamp(target_duration, self.min_duration, self.max_duration)
        else:
            target_duration = 4  # LLM 미출력 시 기본값

        # 7. narrative_structure — 유효값 검증 + fallback
        narrative = analysis.get("narrative_structure", analysis.get("suggested_structure", ""))
        if narrative not in VALID_NARRATIVE_STRUCTURES:
            narrative = "reflection"

        # 8. confidence — LLM이 직접 평가하는 신뢰도. 0.0~1.0 범위 강제
        raw_confidence = analysis.get("confidence")
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else 0.5
        except (ValueError, TypeError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        # 9. depth_level — LLM 값 무시, complexity_score 기반으로 코드가 직접 결정
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
        """
        content_analyses DB 저장용 페이로드를 구성한다.

        CA v2.2.0부터 validated 딕셔너리에 이미 9개 필드가 모두 포함되어 있다.
        DB 저장 시에만 trace_id를 추가한다 (시스템 생성 트레이스).
        """
        return {
            **validated,
            "trace_id": trace_id,
        }
```

또한 save 호출 부분 (`content_analyzer.py:115–121` 근처)을 아래와 같이 수정한다:

```python
        validated_analysis = self._validate_and_correct(llm_analysis, depth_level)

        # DB 저장: 9개 필드 + trace_id (백엔드 API 계약 확정 구조)
        trace_id = str(state.get("trace_id", ""))  # AgentState에서 추출 (없으면 빈 문자열)
        db_payload = self._build_db_payload(validated_analysis, trace_id=trace_id)
        await publisher.publish(
            resource=RESOURCE_CONTENT_ANALYSIS,
            data=db_payload,
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
        )

        # AgentState: v2.2.0 9개 필드 (백엔드 API 계약 완전 일치)
        return {"content_analysis": validated_analysis}
```

- [ ] **Step 4: 기존 테스트 업데이트**

`test_content_analyzer.py` 에서 `emotional_journey` 구조 검증 및 신규 필드 검증 추가:
```python
# emotional_journey — resolution → climax/closing 변경:
# 기존: assert "resolution" in result["content_analysis"]["emotional_journey"]
# 수정: assert "climax" in result["content_analysis"]["emotional_journey"]
#        assert "closing" in result["content_analysis"]["emotional_journey"]
#        assert "resolution" not in result["content_analysis"]["emotional_journey"]

# v2.2.0 신규 필드 검증 추가:
assert "confidence" in result["content_analysis"]
assert isinstance(result["content_analysis"]["confidence"], float)
assert "target_duration" in result["content_analysis"]
assert "narrative_structure" in result["content_analysis"]

# sub_themes AgentState 포함 확인 (v2.2.0에서도 유지):
assert "sub_themes" in result["content_analysis"]
assert len(result["content_analysis"]["sub_themes"]) >= agent.min_sub_themes
```

`mock_llm_response` fixture를 v2.2.0 형식으로 교체 (9개 필드, 4-키 emotional_journey, confidence 포함):
```python
@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """LLM v2.2.0이 반환할 모의 분석 결과 (9개 필드, 백엔드 API 계약 일치)."""
    return {
        "main_theme": "스트레스 해소와 마음 돌봄",
        "user_summary": {
            "keywords": ["스트레스", "피로"],
            "summary": "스트레스와 피로를 호소하는 사용자",
        },
        "emotional_journey": {
            "opening":     "피로와 무기력",
            "development": "원인 인식",
            "climax":      "대처 전략 발견",   # v2.2.0 신규 키
            "closing":     "희망과 안도",       # v2.2.0 신규 키 (resolution 대체)
        },
        "key_messages": ["나를 돌보는 것은 이기적이지 않다", "작은 변화가 큰 차이를 만든다"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],  # 3개 이상 필수
        "target_duration": 5,            # v2.2.0 복원: LLM이 직접 생성
        "narrative_structure": "reflection",  # v2.2.0 복원: LLM이 직접 생성
        "confidence": 0.85,              # v2.2.0 신규: LLM이 직접 평가
    }
```

- [ ] **Step 5: 전체 CA 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_content_analyzer.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 6: CA v2.2.0 프롬프트 작성**

`prompts/podcast/content_analyzer.yaml`에 v2.2.0 신규 버전 추가:

```yaml
# versions 딕셔너리에 "2.2.0" 키 추가
"2.2.0":
  system_prompt: |
    당신은 팟캐스트 콘텐츠 분석 전문가입니다.
    사용자 입력에서 에피소드 주제와 구조를 분석하여 아래 JSON 형식으로 반환하세요.

    **필수 출력 필드 (9개) — 모두 포함, 누락 금지:**
    {
      "main_theme": "핵심 주제 (100자 이내)",
      "user_summary": {
        "keywords": ["키워드1", "키워드2", ...],
        "summary": "사용자 입력 1-2문장 요약"
      },
      "emotional_journey": {
        "opening":     "에피소드 시작 감정 상태 (공감/인정)",
        "development": "감정 변화 과정 (원인 탐색/이해)",
        "climax":      "핵심 전환점 — 해결 전략 또는 통찰 (1문장)",
        "closing":     "마무리 감정 — 희망/동기부여 (1문장)"
      },
      "key_messages": ["핵심 메시지 1", "핵심 메시지 2", "핵심 메시지 3"],
      "sub_themes": ["세부 주제1", "세부 주제2", "세부 주제3"],
      "target_duration": 5,
      "narrative_structure": "reflection",
      "confidence": 0.85
    }

    **규칙:**
    - sub_themes는 반드시 3개 이상 생성하세요. 빈 배열이면 안 됩니다.
    - target_duration은 3~5 사이 정수 (분 단위).
    - narrative_structure는 personal_story|expert_qa|reflection|comparative 중 하나.
    - confidence는 0.0~1.0 사이 float — 분석 신뢰도를 직접 평가하세요.
    - emotional_journey의 climax와 closing은 각각 1문장으로 구체적으로 작성하세요.
    - depth_level은 포함하지 마세요 (코드가 결정합니다).
```

**왜 v2.2.0 프롬프트를 새로 작성하는가:**
- v2.1.0의 `emotional_journey`는 `opening/development/resolution` 3-키 구조. 백엔드 API 계약은 `climax/closing`을 요구함.
- `confidence` 필드가 v2.1.0에 없음.
- `target_duration`/`narrative_structure`가 v2.1.0에서 제거되었으나 API 계약에는 실제 값 필요.

`config/settings.yaml`의 `prompts.versions.content_analyzer`를 `"2.2.0"`으로 핀닝한다:
```yaml
prompts:
  versions:
    content_analyzer: "2.2.0"    # v2.1.0 → v2.2.0 업그레이드
```

- [ ] **Step 7: DB 저장 변경 사항 확인**

```bash
grep -n "publisher\|publish\|_build_db_payload" src/agents/podcast/content_analyzer.py
```

`_build_db_payload(validated_analysis, trace_id=trace_id)` 가 호출되는지 확인.
이 수정 이후 DB에는 9개 필드 + `trace_id`가 전송된다. **백엔드 팀 협의 완료 후 구현** (계획서 상단 DB 협의 목록 참조).

- [ ] **Step 8: 커밋**

```bash
git add src/agents/podcast/content_analyzer.py prompts/podcast/content_analyzer.yaml \
        config/settings.yaml tests/agents/podcast/test_content_analyzer.py
git commit -m "fix(content_analyzer): CA-1/CA-2/CA-3 — v2.2.0 whitelist 9개 필드, 4-키 emotional_journey, confidence 신규"
```

---

## Task 5: sub_themes 공급 경로 결정 [TIER 1→2 연결]

**담당 브랜치:** `feature/validation-*` (Podcast Reasoning 담당)

---

### 무엇이 문제인가?

Script Generator(스크립트를 생성하는 에이전트)는 팟캐스트에 담을 세부 주제 목록(`sub_themes`)이 필요하다. 예: `["직장 스트레스", "수면 부족", "자기돌봄"]`. 이 목록이 있어야 에피소드 안에서 다양한 측면을 다룰 수 있다.

> **⚠️ 2026-04-08 정정**: 이전 분석에서 "CA v2.1.0이 sub_themes를 제거했다"고 기록했으나 오류였다.
> **CA v2.1.0 프롬프트는 sub_themes를 6개 필드 중 하나로 필수 출력**하도록 지시한다.
> 실제 문제는 `_validate_and_correct()` 코드에 min_sub_themes 보장 로직이 없어서
> LLM이 빈 배열을 반환해도 코드가 그대로 통과시킨다는 것이다.

CA v2.1.0 프롬프트는 "sub_themes 3개 이상 필수, 빈 배열 금지"라고 LLM에 요청하지만,
코드가 이를 보장하지 않으면 LLM이 규칙을 어겨도 탐지되지 않는다. 그 결과 Script Generator가 `content_analysis.sub_themes` = `[]`를 받는 경우가 발생한다.

**현재 Script Generator 코드** (`script_generator.py:54`):
```python
sub_themes = content_analysis.get("sub_themes", state.get("sub_themes", []))
# content_analysis에 sub_themes가 없으면 → state에서 찾음 → 그것도 없으면 → []
# 결과: 항상 [] (빈 배열)
```

세부 주제 없이 만들어진 에피소드는 단조롭고 개인화가 약하다.

---

### 어떻게 해결하는가? — 세 가지 선택지

> **결정 필요**: 아래 세 가지 방법 중 하나를 선택해야 한다.
> Task 4(CA-2)에서 min_sub_themes 코드 보장을 추가하므로, **선택지 B가 가장 단순한 경로**다.

---

**선택지 A: Podcast Reasoning(PR)에서 sub_themes를 생성해서 전달**

PR은 GoT(Graph of Thoughts, 생각 그래프) 분석을 통해 이미 `got_result.sub_themes`를 만들고 있다. 그런데 이것을 `reasoning_result` 최상위로 꺼내놓지 않아서 Script Generator가 접근하지 못한다.

```python
# 현재: got_result 안에 숨어있음
reasoning["got_result"] = {"sub_themes": ["테마1", ...], ...}
# sub_themes가 최상위에 없어서 script_generator.py가 읽을 수 없음

# 수정 후: 최상위로 꺼냄
reasoning["got_result"] = {"sub_themes": ["테마1", ...], ...}
reasoning["sub_themes"] = reasoning["got_result"].get("sub_themes", [])
# 이제 script_generator.py에서 reasoning_result.get("sub_themes")로 읽을 수 있음
```

이 경우 Script Generator도 수정이 필요하다: `content_analysis.sub_themes` 대신 `reasoning_result.sub_themes`를 읽도록 바꿔야 한다 (Task 6에서 처리).

- **장점**: GoT가 사용자 입력을 더 깊이 분석해서 만든 주제라 품질이 높다.
- **단점**: Script Generator 수정 필요. GoT가 실행되지 않는 경우(`depth != "full"`) `sub_themes`가 비어있다.

---

**선택지 B: Content Analyzer(CA)에서 sub_themes를 코드로 보장**

CA v2.1.0 프롬프트는 이미 sub_themes를 요청한다. Task 4(CA-2)에서 `_validate_and_correct()`에 min_sub_themes(=3) 강제 보장 로직을 추가하면, CA가 sub_themes를 항상 3개 이상 출력하게 된다. Script Generator 코드는 변경이 불필요하다.

해야 할 일:
1. Task 4(CA-2)에서 min_sub_themes 보장 로직 추가 (코드 1-2줄)
2. Script Generator는 기존대로 `content_analysis.sub_themes` 읽기
3. PR 코드/프롬프트 변경 불필요

- **장점**: Script Generator 수정이 없다. 프롬프트 버전도 그대로다. 가장 단순한 경로다.
- **단점**: LLM이 반드시 고품질 sub_themes를 생성한다는 보장은 없다 (프롬프트만으로 제어).

---

**선택지 C: CA 또는 PR 프롬프트 롤백**

> **결론 먼저**: CA 프롬프트 롤백은 실질적인 의미가 없다. PR 롤백은 오히려 역효과다.

CA 롤백 분석:
- v2.1.0 → v2.0.0: 두 버전 모두 6개 필드(sub_themes 포함) 구조가 동일하다. 롤백해도 동일한 문제.
- v2.1.0 → v1.1.0: v1.1.0은 5개 필드 전용 프롬프트로 **sub_themes를 제거**한 버전이다. 롤백하면 오히려 sub_themes가 완전히 사라진다.
- v2.1.0 → v1.0.0 (주석상 원본): sub_themes, target_duration, narrative_structure를 LLM이 생성하는 버전. 하지만 versions 딕셔너리에 없으므로 직접 사용 불가. 새로 추가해야 함.

PR 롤백 분석:
- PR은 v1.1.0부터 GoT에서 sub_themes를 생성한다. PR을 어느 버전으로 롤백해도 GoT의 sub_themes 생성은 유지된다.
- PR 롤백은 sub_themes 문제와 무관하다.

| 롤백 대상 | 결과 | 권장 여부 |
|---------|-----|---------|
| CA v2.1.0 → v2.0.0 | 동일 구조, 문제 미해결 | ❌ 불필요 |
| CA v2.1.0 → v1.1.0 | sub_themes 완전 제거, 악화 | ❌ 비권장 |
| CA v2.1.0 → v1.0.0 신규추가 | 가능하지만 프롬프트 신규 작성 필요 | ⚠️ 선택지 B보다 복잡 |
| PR 롤백 (어느 버전이든) | sub_themes 문제와 무관 | ❌ 불필요 |

**결론: 선택지 C는 비권장.** 코드 min 보장 로직 추가(선택지 B)가 훨씬 단순하고 확실하다.

---

### 현재 계획 (선택지 B 권장, A는 선택적 보강)

**선택지 B 선택 시 (권장):** Task 4(CA-2)에서 min_sub_themes 보장 로직 추가. Task 5는 선택적 보강으로, Script Generator는 기존 코드 유지.

**선택지 A 선택 시:** PR GoT가 주 공급원, Script Generator가 reasoning_result를 읽도록 Task 6에서 추가 수정 필요.

아래 구현 단계는 **선택지 A**를 기준으로 작성되어 있다. 선택지 B만 채택한다면 이 Task의 Steps는 생략할 수 있다.

**수정 후 reasoning_result 구조 (선택지 A):**
```python
reasoning = {
    ...,
    "got_result": {"sub_themes": [...], ...},
    "sub_themes": ["테마1", "테마2", ...],  # got_result에서 최상위로 올림 (추가)
}
# depth=full 미만일 때: "sub_themes": []
```

**Files:**
- Modify: `src/agents/podcast/podcast_reasoning.py` (lines 234–248 부근)
- Modify: `tests/agents/podcast/test_podcast_reasoning.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_reasoning_result_has_sub_themes_at_top_level() -> None:
    """reasoning_result 최상위에 sub_themes 필드가 있다 (PR sub_themes 노출)."""
    from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
    from unittest.mock import AsyncMock, patch
    from src.models.agent_state import AgentState

    agent = PodcastReasoningAgent()
    mock_got = {
        "sub_themes": ["직장 스트레스", "관계 갈등", "자기돌봄"],
        "nodes": [], "edges": [], "insights": [],
    }
    mock_cot = {
        "episode_structure": [], "narrative_flow": "", "key_points": [],
        "emotional_journey": [], "confidence": 0.8,
    }
    state = AgentState(
        user_input="요즘 회사가 힘들어요",
        user_id="u", session_id="s", mode="podcast",
        intent={"complexity_score": 0.9},
    )

    with patch.object(
        agent, "_graph_of_thoughts", new_callable=AsyncMock, return_value=mock_got
    ):
        with patch.object(
            agent, "_chain_of_thoughts", new_callable=AsyncMock, return_value=mock_cot
        ):
            result = await agent.process(state)

    rr = result.get("reasoning_result", {})
    assert "sub_themes" in rr, "reasoning_result 최상위에 sub_themes 없음"
    assert isinstance(rr["sub_themes"], list)
    assert "직장 스트레스" in rr["sub_themes"]
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_reasoning_result_has_sub_themes_at_top_level -v -m "not live"
```

Expected: **FAIL** — `sub_themes`가 최상위에 없음

- [ ] **Step 3: podcast_reasoning.py 수정**

`_execute_reasoning_pipeline` 결과 조립 부분 (line 233–248):
```python
        # GoT 결과 포함 (depth=full일 때)
        if got_result is not None:
            reasoning["got_result"] = got_result
            # sub_themes를 최상위로 노출 — Script Generator가 직접 접근 가능하게
            reasoning["sub_themes"] = got_result.get("sub_themes", [])
        else:
            # GoT 미실행 시 빈 리스트 (Script Generator가 빈 값 없이 접근)
            reasoning["sub_themes"] = []
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
git commit -m "fix(podcast_reasoning): sub_themes를 reasoning_result 최상위로 노출"
```

---

## Task 6: SG-1 + SG-2 — Script Generator 수정 [TIER 2]

**담당 브랜치:** `feature/analysis-*`

**무엇이 문제인가?**

**SG-1:** `main_theme` 없을 때 `"Mental Health"` 하드코딩 기본값 사용 → 사용자 입력과 무관한 주제로 스크립트 생성.

**sub_themes 소스 변경 (Task 4/5 연동):**
현재: `content_analysis.get("sub_themes", ...)` → CA min 보장 없으면 빈 배열 가능
수정: Task 5(선택 A 채택 시) `reasoning_result.get("sub_themes", [])` 또는 Task 4(선택 B) CA에서 직접

> **⚠️ CA-3 연쇄 영향 (Task 4 완료 후 필수 확인):**
> `script_generator.py:211` — `emotional_journey` 에서 `resolution` 키를 읽는다.
> CA v2.2.0 이후 `emotional_journey`는 `climax/closing` 4-키 구조. `resolution` 키가 없으면 `None` 반환.
>
> ```python
> # 현재 코드 (script_generator.py:211) — 수정 필요
> resolution = content_analysis.get("emotional_journey", {}).get("resolution", "")
> # ↑ CA v2.2.0 이후 resolution 키 없음 → 항상 "" 반환
>
> # 수정 후
> emotional_journey = content_analysis.get("emotional_journey", {})
> climax = emotional_journey.get("climax", "")    # 핵심 전환점
> closing = emotional_journey.get("closing", "")  # 마무리 감정
> ```
>
> **이 줄을 함께 수정해야 한다** (Task 6 Step 3에서 처리).

**SG-2:** 실패 시 반환 `{"script_draft": {}, "error": str(e)}` — `"error"` 키는 AgentState에 없음. LangGraph가 무시하고 실패 원인 추적 불가.

**데이터 흐름:**
```
Podcast Reasoning → state["reasoning_result"]["sub_themes"] → Script Generator ← Task 5 완료 필요
Content Analyzer  → state["content_analysis"]["main_theme"] → Script Generator
Script Generator  → state["script_draft"] → Batch Validator → Script Personalizer
```

**DB 저장 영향:** Script Generator는 publisher 미호출. DB에 직접 저장 안 함 → 백엔드 협의 불필요.

**Files:**
- Modify: `src/agents/podcast/script_generator.py:51–56, 193`
- Modify: `tests/agents/podcast/test_script_generator.py`

**선행 조건:** Task 5 완료 후 실행 (reasoning_result.sub_themes 보장 필요)

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_script_generator_source_has_no_mental_health_hardcode() -> None:
    """ScriptGeneratorAgent 소스에 'Mental Health' 하드코딩 없다 (SG-1)."""
    import inspect
    from src.agents.podcast.script_generator import ScriptGeneratorAgent

    source = inspect.getsource(ScriptGeneratorAgent)
    assert "Mental Health" not in source, "SG-1: Mental Health 하드코딩 발견됨"


@pytest.mark.asyncio
async def test_script_generator_reads_sub_themes_from_reasoning_result() -> None:
    """sub_themes를 content_analysis가 아닌 reasoning_result에서 읽는다."""
    import inspect
    from src.agents.podcast.script_generator import ScriptGeneratorAgent

    source = inspect.getsource(ScriptGeneratorAgent)
    # content_analysis에서 sub_themes 읽는 코드 없어야 함
    assert 'content_analysis.get("sub_themes"' not in source, \
        "content_analysis.sub_themes 읽기 잔존 — reasoning_result로 변경 필요"


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

line 51–56 — `main_theme` + `sub_themes` 소스 수정:
```python
        main_theme: str = str(content_analysis.get("main_theme", ""))
        if not main_theme:
            self.logger.error(
                "[ScriptGenerator] main_theme 누락 — content_analysis 유효성: %s",
                bool(content_analysis),
            )
            return {"script_draft": {"_error": "main_theme_missing", "segments": []}}

        # sub_themes: CA v2.1.0 이후 Podcast Reasoning에서 제공 (Task 5 연동)
        sub_themes: list[str] = cast(
            list[str], reasoning_result.get("sub_themes", [])
        )
```

line 62–64 — `target_duration` 소스 수정 (CA에서 제거된 후 reasoning_result 확인):
```python
        target_duration: float = float(
            cast(Any,
                 reasoning_result.get("target_duration",
                 state.get("target_duration", 5)))
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
git commit -m "fix(script_generator): SG-1/SG-2 — Mental Health 제거, sub_themes PR로부터 읽기, error 키 정리"
```

---

## Task 7: VI-1 + VI-2 — Visualization Agent 출력 검증 [TIER 2]

**담당 브랜치:** `feature/reasoning-*`

**무엇이 문제인가?**
- VI-1: `visual_data.style_type`, `interpretation`을 LLM 응답에서 타입 검증 없이 직접 저장. LLM이 `None` 반환 시 하위 처리에서 오류 발생.
- VI-2: 에러 경로 반환 dict에 `image_url`, `style_type`, `interpretation` 키가 없음. 라우트 코드가 이 키들을 읽을 때 KeyError 발생 가능.

**`podcasts.py:_save_core_data()`가 visual_data에서 읽는 키:**
```python
visual_data_raw.get("image_url")           # 에러 경로: None → 안전
visual_data_raw.get("interpretation", "")  # 에러 경로: KeyError 없이 ""
visual_data_raw.get("s3_key", "")
visual_data_raw.get("original_prompt", "")
```
→ 에러 경로에 이 키들이 없으면 `.get(key, default)` 덕분에 즉각 오류는 없으나, 구조 불일치는 유지 보수 혼란을 야기.

**DB 저장 영향:**
`visualizations` 테이블에 저장되는 `cdn_url`(=image_url), `interpretation_text`가 에러 경로에서 빈값으로 저장됨 → 정상 동작.
**백엔드 협의 불필요** ✅

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

## Task 8: BV-1 + BV-2 — Batch Validator 명시 필드 추출 [TIER 3]

**담당 브랜치:** `feature/validation-*`

---

### 무엇이 문제인가?

Batch Validator는 Script Generator가 만든 스크립트를 LLM에게 평가시킨다. LLM은 "이 스크립트가 합격인가, 수정이 필요한가, 아니면 심각한 문제가 있는가"를 판단하고 점수와 이유를 반환한다. 이 결과가 `validation_result`에 저장된다.

---

**BV-1 문제: LLM 응답 전체를 그대로 저장한다**

현재 코드 (`batch_validator.py:122`):
```python
validation["verdict"] = verdict_map.get(decision, "FAIL")  # verdict 추가
return {"validation_result": validation}  # LLM 전체 응답을 그대로 반환
```

LLM이 `{"overall_score": 0.85, "action": {...}, "extra_debug": "..."}` 라고 답하면, `extra_debug`까지 그대로 `validation_result`에 들어간다.

더 심각한 것은 **LLM이 필수 필드를 안 줄 때**다:
- `overall_score`가 없으면 → `validation_result.get("overall_score", 0.0)` → **항상 0.0** 반환 → DB에 `validation_score = 0.0` 저장 → 로그를 봐도 검증 점수가 항상 0이라 디버깅 불가
- `action.revision_instructions`가 없으면 → 스크립트가 FAIL 판정 받아서 재시도할 때 Script Generator가 "뭘 고쳐야 하는지" 모른다 → 똑같은 스크립트를 또 만들어서 또 FAIL → 무의미한 재시도 반복

**왜 `overall_score`가 항상 float으로 보장되어야 하는가?**
DB의 `podcast_episodes` 테이블에 `validation_score FLOAT` 컬럼이 있다. Python에서 `None`이나 문자열을 float 컬럼에 넣으려 하면 DB INSERT 오류가 난다. 지금은 `validation_result.get("overall_score", 0.0)`으로 꺼내는데, LLM이 `overall_score`를 안 줬다면 항상 0.0이 DB에 저장되는 것이다. 수정 후에는 코드가 LLM 응답에서 `overall_score`를 꺼내서 명시적으로 `float()`으로 변환해 저장한다. 이렇게 하면 LLM이 실수로 `"0.85"` 같은 문자열로 줘도 코드가 `0.85`로 바꿔준다.

---

**BV-2 문제: 조기 반환의 구조가 정상 반환과 다르다**

`script_draft`(Script Generator가 만든 스크립트)가 아예 비어있으면, Batch Validator는 LLM을 호출하지 않고 즉시 FAIL을 반환한다. 이것이 "조기 반환"이다.

현재 조기 반환 코드 (`batch_validator.py:83-89`):
```python
return {
    "validation_result": {
        "verdict": "FAIL",
        "reason": "Empty script_draft",
        "overall_score": 0.0,
        # ↑ action 필드가 없다!
    },
}
```

정상 반환에는 `action.revision_instructions`가 있다. Script Generator는 재시도 시 `validation_result["action"]["revision_instructions"]`를 읽어서 "이번엔 이 부분을 고쳐서 써봐"라는 지시를 받는다.

조기 반환을 받으면 `action` 키가 없다 → `validation_result["action"]` → `KeyError` 발생 → 파이프라인 오류.

**어떤 상황에서 script_draft가 비어있을 수 있는가?** Script Generator가 LLM 오류로 실패해서 `{"script_draft": {}, "_error": "..."}` 를 반환한 경우다. 이건 드문 상황이지만 발생 시 파이프라인이 KeyError로 터진다.

---

### 어떻게 수정하는가?

`_build_validation_result(validation)` 헬퍼 메서드를 만든다. 이 메서드는:
1. LLM 응답에서 허용 필드(`overall_score`, `action`, 선택적으로 `scores`, `critical_issues`)만 꺼낸다.
2. `overall_score`를 명시적으로 `float()`으로 변환한다.
3. `action` 내부 필드도 명시적으로 꺼내서 구조를 보장한다.

그리고 조기 반환에도 `action` 필드를 추가한다:
```python
return {
    "validation_result": {
        "verdict": "FAIL",
        "overall_score": 0.0,
        "action": {
            "decision": "revise",
            "revision_instructions": "Empty script_draft — Script Generator failed",
            "priority_fixes": [],
        },
    },
}
```

---

### 왜 이렇게 하는가?

모든 반환 경로(정상 반환 / 조기 반환)에서 `validation_result`의 구조를 동일하게 만드는 것이 목표다. 구조가 항상 같으면:
- Script Generator는 항상 `validation_result["action"]["revision_instructions"]`를 안전하게 읽을 수 있다.
- 라우팅 코드(`route_after_tier3_podcast`)는 항상 `validation_result["verdict"]`를 안전하게 읽을 수 있다.
- DB 저장 코드는 항상 `float(validation_result["overall_score"])`를 안전하게 할 수 있다.

"구조를 보장한다"는 것은 곧 "KeyError, TypeError 없이 코드가 동작한다"는 의미다.

---

### 수정 후 얻는 결과

- `validation_result`에는 항상 `verdict`, `overall_score`, `action` 세 개의 키가 존재한다.
- LLM이 임의 필드를 추가해도 `validation_result`에 들어오지 않는다.
- 스크립트 재시도 시 Script Generator가 `revision_instructions`를 받아 실제로 개선된 스크립트를 만든다.
- `validation_score`가 DB에 항상 올바른 float 값으로 저장된다.

**Batch Validator v2.3.0 프롬프트 출력 스키마:**
```
overall_score: 0.0 ~ 1.0
action: {
  decision:              "approve" | "revise" | "escalate"
  revision_instructions: str  (재시도 개선 방향)
  priority_fixes:        list[str]
}
```

**데이터 흐름:**
```
Batch Validator → state["validation_result"] → (읽는 곳)
  1. route_after_tier3_podcast() → validation_result["verdict"] (라우팅 결정)
  2. Script Generator (재시도 시) → validation_result["action"]["revision_instructions"]
  3. podcasts.py:_save_core_data() → validation_result.get("overall_score", 0.0)
```

**DB 저장 영향:**
`podcast_episodes` 테이블 `validation_score FLOAT` 컬럼에 저장된다.
수정 전: LLM이 `overall_score`를 안 줄 경우 항상 `0.0` 저장 (검증 점수 손실).
수정 후: `float(validation["overall_score"])` 명시 변환 → 항상 올바른 float 저장 → **백엔드 협의 불필요** ✅

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
    assert "verdict" in vr        # 코드가 추가하는 필드
    assert "overall_score" in vr
    assert "action" in vr


@pytest.mark.asyncio
async def test_early_return_has_action_field_like_normal_return() -> None:
    """빈 script_draft 조기 반환에도 action 필드 있다 (BV-2)."""
    from src.agents.podcast.batch_validator import BatchValidatorAgent
    from src.models.agent_state import AgentState
    import asyncio

    agent = BatchValidatorAgent()
    state = AgentState(
        user_input="테스트", user_id="u", session_id="s", mode="podcast",
        script_draft={},   # 비어있음 → 조기 반환
        iteration_count=0,
    )

    result = asyncio.get_event_loop().run_until_complete(agent.process(state))
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
        # 선택 필드 (있을 때만 추가)
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

정상 반환 경로(approve/escalate/revise)를 모두 `_build_validation_result(validation)` 사용으로 교체.
기존 `validation["verdict"] = ...` 줄 삭제.

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

## Task 9: SP-1 + SP-2 — Script Personalizer 감정 필드 참조 정정 [TIER 4]

**담당 브랜치:** `feature/analysis-*`

**무엇이 문제인가?**
- SP-1: `state.get("emotional_journey")` — AgentState에 없는 최상위 키를 읽는다. 항상 `None` 반환 → 폴백 로직 강제 실행.
- SP-2: `emotional_journey_data.get("start_emotion")`, `emotional_journey_data.get("resolution_emotion")` — CA v1.x 시절 필드명. v2.1.0은 `opening`, `resolution`을 사용한다.

**Task 4 완료 후 content_analysis.emotional_journey 구조 (v2.2.0 기준):**
```python
{
  "opening":     "시작 감정 상태 (공감/인정)",
  "development": "감정 변화 과정 (원인 탐색)",
  "climax":      "핵심 전환점 — 해결 전략",      # v2.2.0 신규 (resolution 대체)
  "closing":     "마무리 감정 — 희망/동기부여",    # v2.2.0 신규 (resolution 분리)
}
```
→ `start_emotion`, `resolution_emotion`, `resolution` 폴백은 영구적으로 `None`/`""` 반환 (데드 코드)

> **⚠️ CA-3 연쇄 영향**: `resolution` 키가 v2.2.0 이후 존재하지 않는다.
> SP가 `resolution`을 읽으면 항상 `""` 반환 → 폴백 `"따뜻함"` 강제 실행 → 실제 마무리 감정 무시.
> `closing` 키로 변경해야 한다.

**선행 조건:** Task 4(CA-1/CA-2/CA-3) 완료 후 실행.
`content_analysis.emotional_journey`가 `{opening, development, climax, closing}` 4-키 구조를 보장한 뒤 SP 수정.

**DB 저장 영향:** Script Personalizer는 publisher 미호출. 영향 없음 ✅

**Files:**
- Modify: `src/agents/podcast/script_personalizer.py:130–147`
- Modify: `tests/agents/podcast/test_script_personalizer.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_personalizer_no_state_top_level_emotional_journey() -> None:
    """state 최상위 emotional_journey 참조 없다 — AgentState 미정의 키 (SP-1)."""
    import inspect
    from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent

    source = inspect.getsource(ScriptPersonalizerAgent)
    assert 'state.get("emotional_journey")' not in source, \
        "SP-1: state 최상위 emotional_journey 참조 존재"


def test_personalizer_no_v1x_emotion_field_names() -> None:
    """start_emotion/resolution_emotion/resolution v1.x 및 v2.1.x 레거시 필드명 없다 (SP-2).

    CA v2.2.0 이후 emotional_journey는 climax/closing 4-키 구조.
    resolution 키가 더 이상 존재하지 않으므로 SP가 이를 참조하면 항상 "" 반환.
    """
    import inspect
    from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent

    source = inspect.getsource(ScriptPersonalizerAgent)
    assert '"start_emotion"' not in source, "SP-2: start_emotion 레거시 참조 존재"
    assert '"resolution_emotion"' not in source, "SP-2: resolution_emotion 레거시 참조 존재"
    # CA v2.2.0: resolution → closing으로 변경됨
    assert '.get("resolution"' not in source, "SP-2: resolution v2.1.x 참조 잔존 — closing으로 변경 필요"
    # 신규 키 참조 확인
    assert '"closing"' in source, "SP-2: closing 키 참조 없음 — v2.2.0 반영 필요"
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/agents/podcast/test_script_personalizer.py::test_personalizer_no_state_top_level_emotional_journey -v -m "not live"
```

Expected: **FAIL** — `state.get("emotional_journey")` 패턴 존재

- [ ] **Step 3: script_personalizer.py 수정**

lines 130–147 수정:
```python
            # content_analysis에서 감정 여정 추출 — v2.1.0 필드 (opening/development/resolution)
            content_analysis = state.get("content_analysis", {})
            emotional_journey_data = content_analysis.get("emotional_journey")
            # ↑ state.get("emotional_journey") 폴백 제거 (AgentState 미정의 키)

            emotional_journey = None
            if emotional_journey_data and isinstance(emotional_journey_data, dict):
                try:
                    emotional_journey = EmotionalJourney(
                        opening=emotional_journey_data.get("opening", "차분함"),
                        development=emotional_journey_data.get("development", "공감"),
                        climax=emotional_journey_data.get("climax", ""),        # v2.2.0: 핵심 전환점
                        closing=emotional_journey_data.get("closing", "따뜻함"), # v2.2.0: resolution 대체
                        # ↑ start_emotion/resolution_emotion/resolution 레거시 폴백 전부 제거
                        # Task 10: schemas.py EmotionalJourney 모델도 4-키로 업데이트 필요
                        journey_type=emotional_journey_data.get("journey_type", "healing"),
                    )
                except Exception as e:
                    self.logger.warning(
                        "[ScriptPersonalizer] EmotionalJourney 생성 실패: %s", e
                    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_script_personalizer.py -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 전체 회귀 테스트**

```bash
pytest tests/ -v -m "not live" -q
```

Expected: **0 failed** (기준선 유지)

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/script_personalizer.py tests/agents/podcast/test_script_personalizer.py
git commit -m "fix(script_personalizer): SP-1/SP-2 — v1.x 레거시 필드 제거, v2.2.0 opening/climax/closing 사용"
```

---

## Task 10: schemas.py EmotionalJourney 모델 4-키 구조 변경 [공통 모델]

**담당 브랜치:** `feature/reasoning-*` (또는 전담 개발자 협의)

> **⚠️ Protected File 인접 영역**: `src/models/schemas.py`는 공용 모델 파일. 변경 전 전원 리뷰 필수.
> 단, 이 변경은 기존 필드를 제거하고 새 필드를 추가하는 것으로, AgentState 스키마(`agent_state.py`)와는 별도 파일이다.

---

### 무엇이 문제인가?

`src/models/schemas.py:53-68`에 정의된 `EmotionalJourney` Pydantic 모델은 현재 `resolution` 필드를 가지고 있다:

```python
# 현재 구조 (v2.1.x 기준)
class EmotionalJourney(BaseModel):
    """감정 여정 구조 — TIER 1 CA 출력 기반."""
    opening: str
    development: str
    resolution: str       # ← v2.2.0 이후 존재하지 않는 키
    journey_type: str = "healing"
```

CA v2.2.0 이후 `emotional_journey`에 `resolution` 키가 없다. `climax`와 `closing`으로 분리되었다.

**왜 `EmotionalJourney` 모델이 존재하는가?**
Script Personalizer가 `emotional_journey` dict를 `EmotionalJourney(**emotional_journey_data)` 형식으로 파싱하여 타입 검증을 수행한다. 모델에 정의되지 않은 필드를 넘기거나(`climax`, `closing`), 정의된 필드를 빠뜨리면(`resolution`) Pydantic이 ValidationError를 발생시킨다.

**schemas.py 파일 노트:**
```
# 현재 docstring: "Podcast Reasoning은 emotional_journey를 list[str]로 출력"
# → 이 노트가 오해를 낳는다. CA가 dict로 출력하고 SP가 이 모델로 파싱한다.
# Task 10에서 docstring도 수정한다.
```

---

### 어떻게 수정하는가?

`EmotionalJourney` 모델의 `resolution` 필드를 제거하고 `climax` + `closing` 필드를 추가한다:

```python
# 수정 후 구조 (v2.2.0 기준)
class EmotionalJourney(BaseModel):
    """감정 여정 구조 — CA v2.2.0 출력 기반.

    백엔드 API 계약 확정 구조 (2026-04-09):
    opening(공감/인정) → development(원인 탐색) → climax(해결 전략) → closing(희망/동기부여)
    """
    opening: str
    development: str
    climax: str           # 핵심 전환점 — 해결 전략 또는 통찰 (v2.2.0 신규, resolution 대체 1)
    closing: str          # 마무리 감정 — 희망/동기부여 (v2.2.0 신규, resolution 대체 2)
    journey_type: str = "healing"
```

---

### 왜 이렇게 하는가?

`resolution` 하나의 필드가 "해결 전략"과 "마무리 감정"이라는 두 가지 의미를 담고 있었다. 백엔드 팀과의 API 계약에서 이 두 개념을 분리해야 한다고 합의되어:
- `climax` = 에피소드의 핵심 전환점 (구체적인 해결 방법 제시)
- `closing` = 에피소드가 끝날 때의 감정 상태 (청취자가 느끼는 마무리 감정)

이 분리로 Script Personalizer가 더 정밀하게 에피소드 마무리 톤을 조정할 수 있다.

---

### 수정 후 얻는 결과

- `EmotionalJourney` 모델이 CA v2.2.0 출력 구조와 일치한다.
- SP에서 `EmotionalJourney(**emotional_journey_data)` 파싱 시 ValidationError 없이 성공한다.
- Pydantic 타입 검증이 4-키 구조를 강제한다.

**Files:**
- Modify: `src/models/schemas.py:53-68`

**선행 조건:** Task 4(CA-3) 완료 후 실행.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_emotional_journey_model_has_climax_and_closing() -> None:
    """EmotionalJourney 모델이 v2.2.0 4-키 구조를 가진다 (Task 10)."""
    from src.models.schemas import EmotionalJourney

    # 정상: 4-키 구조
    ej = EmotionalJourney(
        opening="피로와 무기력",
        development="원인 인식",
        climax="대처 전략 발견",
        closing="희망과 안도",
    )
    assert ej.climax == "대처 전략 발견"
    assert ej.closing == "희망과 안도"
    assert not hasattr(ej, "resolution"), "resolution 필드 잔존 — 제거 필요"


def test_emotional_journey_model_rejects_resolution_key() -> None:
    """EmotionalJourney 모델이 resolution 키를 거부한다 (Task 10).

    CA v2.2.0 이후 resolution 키가 존재하지 않는다. 이 키로 파싱을 시도하면
    Pydantic이 에러를 발생시켜야 한다 (extra='forbid' 설정 시).
    """
    from src.models.schemas import EmotionalJourney
    import pytest

    # 구버전 v2.1.x 형식 — 이제 거부되어야 함
    with pytest.raises(Exception):
        EmotionalJourney(
            opening="피로",
            development="인식",
            resolution="안도",  # v2.1.x 레거시 키
        )
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/ -k "test_emotional_journey_model" -v -m "not live"
```

Expected: **FAIL** — `resolution` 필드 존재, `climax`/`closing` 없음

- [ ] **Step 3: schemas.py 수정**

`src/models/schemas.py:53-68`:
```python
class EmotionalJourney(BaseModel):
    """감정 여정 구조 — CA v2.2.0 출력 기반.

    백엔드 API 계약 확정 구조 (2026-04-09):
    opening → development → climax → closing 4단계 흐름.
    Script Personalizer가 content_analysis.emotional_journey를 이 모델로 파싱한다.
    """
    opening: str
    development: str
    climax: str = ""      # 핵심 전환점 (v2.2.0 신규)
    closing: str = ""     # 마무리 감정 (v2.2.0 신규, resolution 대체)
    journey_type: str = "healing"
```

> **왜 `climax`와 `closing`에 기본값(`= ""`)을 주는가?**
> 롤아웃 기간 중 일부 CA가 v2.1.x 프롬프트를 사용 중일 수 있다. 기본값이 없으면
> 구버전 출력을 파싱할 때 ValidationError가 발생한다. Task 4 완료 후 기본값 제거를 검토한다.

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/ -k "emotional_journey" -v -m "not live"
```

Expected: **All PASS**

- [ ] **Step 5: 회귀 테스트**

```bash
pytest tests/ -v -m "not live" -q
```

Expected: **0 failed**

- [ ] **Step 6: 커밋**

```bash
git add src/models/schemas.py tests/
git commit -m "fix(schemas): EmotionalJourney 모델 v2.2.0 4-키 구조 — resolution 제거, climax/closing 추가"
```

---

## 연쇄 영향 맵 — CA v2.2.0 emotional_journey 키 변경 (resolution → climax + closing)

> **배경**: CA v2.2.0에서 `emotional_journey`의 `resolution` 키가 제거되고 `climax` + `closing`으로 분리된다.
> 이 변경이 코드베이스 전체에 영향을 미치는 모든 파일을 정리한다.

### 영향 파일 목록

| 파일 | 위치 | 현재 코드 | 수정 후 | 처리 Task |
|-----|------|---------|--------|---------|
| `src/models/schemas.py` | line 53-68 | `resolution: str` 필드 | `climax: str`, `closing: str` 추가, `resolution` 제거 | **Task 10** |
| `src/agents/podcast/script_generator.py` | line 211 | `.get("resolution", "")` | `.get("climax", "")` + `.get("closing", "")` | **Task 6** |
| `src/agents/podcast/script_personalizer.py` | lines 141-143, 573 | `resolution` 참조 | `closing` 참조 | **Task 9** |
| `prompts/podcast/podcast_reasoning.yaml` | v2.1.0 CoT, line ~1198 | `ca_emotional_alignment`에서 "마무리" → CA `resolution` | "마무리" → CA `closing` | **Task 5 선행 후 PR 프롬프트 수정** |
| `prompts/podcast/content_analyzer.yaml` | 신규 v2.2.0 | 없음 | 4-키 `emotional_journey` 지시 추가 | **Task 4 Step 6** |

### 수정 순서

```
Task 4 (CA-3) → Task 10 (schemas.py) → Task 6 (SG) + Task 9 (SP) → PR 프롬프트 업데이트
```

> Task 4가 선행되어야 schemas.py, SG, SP에서 어떤 키를 받는지 확정된다.

### PR 프롬프트 수정 상세

`prompts/podcast/podcast_reasoning.yaml` v2.1.0 CoT 섹션 (line ~1198):

현재:
```yaml
ca_emotional_alignment:
  - 마무리: "{{ ca_analysis.emotional_journey.resolution }}"
```

수정 후:
```yaml
ca_emotional_alignment:
  - 핵심전환: "{{ ca_analysis.emotional_journey.climax }}"
  - 마무리: "{{ ca_analysis.emotional_journey.closing }}"
```

**왜 이 수정이 필요한가?** Podcast Reasoning이 CoT(Chain of Thoughts) 분석 시 CA의 감정 여정을 참고한다. `resolution` 키 없이 렌더링하면 템플릿 오류 또는 빈 값이 된다. `climax`(해결 전략)과 `closing`(마무리)을 구분하면 Reasoning 품질도 향상된다.

---

## Self-Review

### 1. 이슈 커버리지 (14건)

| 이슈 | TIER | 유형 | Task | 커버 |
|------|------|------|------|------|
| IC-1 | 0 | A | 1 | ✅ |
| SA-1 | 1 | A | 2 | ✅ |
| SA-2 | 1 | B | 2 | ✅ |
| EA-1 | 1 | B | 3 | ✅ |
| CA-1 | 1 | A | 4 | ✅ |
| CA-2 | 1 | B | 4 | ✅ |
| CA-3 (emotional_journey 4-키, confidence, trace_id) | 1 | 신규 | 4 | ✅ |
| PR sub_themes 노출 | 1→2 | 신규 | 5 | ✅ |
| SG-1 | 2 | B | 6 | ✅ |
| SG sub_themes 소스 | 2 | 연동 | 6 | ✅ |
| SG-2 | 2 | C | 6 | ✅ |
| VI-1 | 2 | A | 7 | ✅ |
| VI-2 | 2 | B | 7 | ✅ |
| BV-1 | 3 | A | 8 | ✅ |
| BV-2 | 3 | C | 8 | ✅ |
| SP-1 | 4 | C | 9 | ✅ |
| SP-2 | 4 | B | 9 | ✅ |
| schemas.py EmotionalJourney 4-키 | 공통 | 신규 | 10 | ✅ |
| EM-1 | — | B | 제외 | ✅ PR#86 완료 |
| KA-1 | — | C | 제외 | ⏳ Pinecone 선행 |
| PR-1 | — | C | 제외 | ⏳ KA-1 선행 |

### 2. 빈 값 참조 해소 확인

| 에이전트 | 빈 값 참조 문제 | 해소 방법 |
|---------|-------------|---------|
| SG: `sub_themes` | CA min 보장 없어 빈 배열 가능 | Task 4(CA-2): min_sub_themes 보장. Task 5(선택A): PR GoT도 fallback으로 노출 가능 |
| SP: `state.emotional_journey` | AgentState 미정의, 항상 None | Task 9: state 참조 제거 |
| SP: `start_emotion`/`resolution_emotion` | CA v2.1.0 미출력, 항상 None | Task 9: opening/resolution으로 교체 |

### 3. DB 협의 사항 재확인 (실제 스키마 기반)

> 근거: `dev/local_db/mysql/init.sql`, `src/api/external_schemas.py`, `docs/architecture/DATA_SCHEMA.md`
> 에이전트 저장 코드 직접 분석 (`src/agents/podcast/`, `src/api/routes/podcasts.py`)

| 리소스 | 협의 여부 | 근거 |
|--------|---------|------|
| `content_analyses` | **⚠️ 협의 필수** | 로컬 스키마 미정의. 백엔드 API 계약 확정(2026-04-09): 9개 필드 + trace_id. emotional_journey 4-키(climax/closing), confidence 신규. 백엔드 컬럼 구조 확인 필요 |
| `graph_analyses` | ℹ️ 확인 권장 | 로컬 스키마 미정의. PR GoT 결과 저장. 이번 계획 수정 대상 아님 |
| `emotion_logs` | ✅ 불필요 | `emotional_journey_hint`는 DB 컬럼 아님 (`init.sql:52-71` 확인). AgentState 내부 필드만 수정 |
| `podcast_episodes` | ✅ 불필요 | `intent_type VARCHAR(100) DEFAULT 'unknown'`, `safety_status ENUM`, `validation_score FLOAT` 모두 확인 완료 |
| `visualization_meta` | ✅ 불필요 | Task 7이 NOT NULL 제약(`cdn_url`, `image_prompt`, `interpretation_text`) 위반 위험 줄임 |

### 4. 선행 조건 준수

- Task 6(SG sub_themes) → Task 5(PR) 완료 후 실행 명시 ✅
- Task 9(SP) → Task 4(CA) 완료 후 실행 명시 ✅

---

---

## AWS 배포 환경

> **2026-04-08 점검 결과** — 코드베이스 직접 분석 기반. 구현 시 이 환경을 기준으로 코드를 작성한다.

### 인프라 맵

| 서비스 | 리전 | 설정 위치 | 비고 |
|--------|------|---------|------|
| **AWS Bedrock (LLM)** | `ap-northeast-2` (서울) | `config/settings.yaml` → `llm.bedrock` | 동시 호출 상한 10, 재시도 3회 |
| **AWS Bedrock (이미지)** | `us-east-1` (버지니아) | `settings.yaml` → `agents.visualization.image_region` | Titan 이미지 생성 모델이 서울 미지원 → 크로스 리전 |
| **S3** | `ap-northeast-2` 기본 | `settings.yaml` → `storage.s3.bucket: mindlog-images` | `AWS_REGION` 환경변수 재사용 |
| **Pinecone** | SaaS (AWS 외부) | `settings.yaml` → `storage.pinecone` | 인덱스: `expert-knowledge`, `mem-podcast-episode` |
| **Neo4j** | AI 서버 동일 호스트 | `docker-compose.yml` | `bolt://localhost:7687` |

### Bedrock 모델별 리전 제약

| 모델 계열 | 호출 방식 | 이유 |
|----------|----------|------|
| Claude Haiku | In-Region (`anthropic.claude-3-haiku-20240307-v1:0`) | 서울 In-Region 지원 |
| Claude Sonnet 3.7 / Sonnet v2 | APAC CRIS (`apac.anthropic.*`) | 서울 In-Region 직접 호출 불가 → Cross-Region Inference Profile |
| Claude Opus (대체) | APAC CRIS (`apac.anthropic.claude-sonnet-4-20250514-v1:0`) | Opus 4.6 서울 미지원 → Sonnet 4로 대체 |

### AWS 인증 방식

boto3 기본 자격증명 체인에 의존한다: 환경변수 → `~/.aws/credentials` → EC2 인스턴스 프로파일(IAM Role).
- **로컬 개발**: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` 환경변수 사용 (`.env.example` 참고)
- **EC2 배포**: IAM 인스턴스 프로파일(Role) 사용 — 액세스 키 불필요

### 필수 환경변수 (AWS 관련)

| 환경변수 | 기본값 | 필수 여부 |
|---------|--------|---------|
| `AWS_REGION` | `ap-northeast-2` | 선택 (기본값 있음) |
| `AWS_ACCESS_KEY_ID` | 없음 | IAM Role 미사용 시 필수 |
| `AWS_SECRET_ACCESS_KEY` | 없음 | IAM Role 미사용 시 필수 |
| `AWS_S3_BUCKET` | `mindlog-images` | 선택 (기본값 있음) |
| `PINECONE_API_KEY` | 없음 | **필수** |
| `LLM_PROVIDER` | `bedrock` | 선택 |

### 구현 시 주의사항

1. **boto3 클라이언트 리전**: LLM용(`ap-northeast-2`)과 이미지 생성용(`us-east-1`) 클라이언트가 별도 초기화됨. `base_agent.py:call_image_gen()`이 `image_region` 설정으로 분리.
2. **CRIS 모델 ID**: `settings.yaml`의 `bedrock_models` 섹션에 `apac.anthropic.*` 접두사 붙은 ID를 그대로 사용. 임의로 변경 금지.
3. **S3 직접 접근**: Visualization Agent만 `boto3`로 S3에 직접 업로드. 나머지 스토리지는 백엔드 API 경유.
4. **`SKIP_VISUALIZATION` 환경변수**: Visualization 이미지 생성을 긴급 비활성화할 때 사용. `.env.example`에 추가 필요.

---

*작성일: 2026-04-08 (v5) | DB 섹션: 에이전트 저장 경로 전수 조사 반영. content_analyses sub_themes DB 유지 전략. graph_analyses 신규 발견. Task 4 AgentState/DB 경로 분리*
*2026-04-08 v6 업데이트: IC-1 수정 완료 확인. DB 아키텍처 검증. AWS 배포 환경 섹션 추가.*
*2026-04-09 v7 업데이트: 백엔드 API 계약 확정 반영. CA-3 추가 (4-키 emotional_journey, confidence, trace_id). CA v2.2.0 프롬프트 작성 지시. schemas.py Task 10 추가. 연쇄 영향 맵 신규 섹션. SG/SP/PR 프롬프트 resolution→closing 수정 지시. 5개 서브에이전트 점검 결과 통합.*

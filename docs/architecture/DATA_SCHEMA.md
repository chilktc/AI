# 데이터 스키마 명세 (DATA_SCHEMA.md)

> **버전**: v1.1
> **SSOT**: Notion "작업중인 db 스키마" (N10) + `src/api/external_schemas.py`
> **최종 업데이트**: 2026-04-13

---

## 목차

1. [DB별 책임 분담](#1-db별-책임-분담)
2. [MySQL 테이블 (8개)](#2-mysql-테이블-8개)
3. [Pinecone 인덱스 (2개)](#3-pinecone-인덱스-2개)
4. [Neo4j 노드 (5개)](#4-neo4j-노드-5개)
5. [S3 오브젝트 스토리지](#5-s3-오브젝트-스토리지)
6. [추적 체계 (Tracing)](#6-추적-체계-tracing)

---

## 1. DB별 책임 분담

| DB | SSOT 역할 | 저장 데이터 |
|----|----------|-----------|
| **MySQL** | 구조화된 트랜잭션 데이터 (관계형 정규화) | 사용자, 세션, 감정 로그, 에피소드 메타, 학습 패턴, 시각화 메타 |
| **Pinecone** | 시맨틱 검색 벡터 (원본은 MySQL) | 에피소드 임베딩, 지식 문서 임베딩. `vec_{mysql_pk}` 형식으로 MySQL 참조 |
| **Neo4j** | 관계/그래프 분석 (관계만 저장, 원본은 MySQL) | 감정 패턴 관계, 토픽 연결, 사용자-에피소드 관계, GoT 추론 그래프 |
| **S3/CDN** | 바이너리 에셋 (메타데이터는 MySQL) | 시각화 이미지, 팟캐스트 커버, TTS 오디오 |

**원칙**: Pinecone/Neo4j는 MySQL PK를 참조하는 보조 DB이다. 원본 데이터는 항상 MySQL에 존재한다.

---

## 2. MySQL 테이블 (8개)

모든 테이블은 `SaveRequest(type, data)`를 통해 BackendClient로 저장된다.

> **변경 이력 (2026-04-13):** `podcast_segments` 테이블 제거 (v3.0 flat script_text 전환으로 폐기). `podcast_episodes`에 `script_text`, `tts_markers_json`, `primary_emotion`, `secondary_emotions` 컬럼 추가. `content_analyses`, `user_summaries` 신규 추가. 총 7→8개.

### 2-1. users

사용자 프로필 정보. `PATCH /api/users/{user_id}/profile`로 수정.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `user_id` | VARCHAR | **PK** | UUID v4 |
| `display_name` | VARCHAR(50) | nullable | 표시 이름 |
| `age_group` | ENUM | default `30s` | `10s\|20s\|30s\|40s\|50s\|60s_plus` |
| `preferred_style` | ENUM | default `neutral` | `warm\|professional\|casual\|neutral` |
| `preferred_attitude` | ENUM | default `balanced` | `supportive\|analytical\|balanced\|motivational` |
| `accessibility_needs` | JSON | default `[]` | 접근성 요구사항 배열 |
| `notification_enabled` | BOOLEAN | default `true` | 알림 활성화 여부 |
| `total_sessions` | INT | default `0` | 누적 세션 수 |
| `total_episodes` | INT | default `0` | 누적 에피소드 수 |
| `created_at` | DATETIME | not null | 생성 시각 (UTC) |
| `updated_at` | DATETIME | not null | 수정 시각 (UTC) |

### 2-2. sessions

세션 관리. SaveRequest type: `session`.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `session_id` | VARCHAR | **PK** | `sess_{uuid_hex[:12]}` 형식 |
| `user_id` | VARCHAR | **FK** → users | |
| `mode` | ENUM | not null | `podcast` |
| `status` | ENUM | default `active` | `active\|closed\|expired` |
| `episode_count` | INT | default `0` | 세션 내 에피소드 수 |
| `feedback_rating` | INT | nullable | 1-5 |
| `feedback_helpful` | BOOLEAN | nullable | |
| `feedback_comment` | VARCHAR(500) | nullable | |
| `created_at` | DATETIME | not null | |
| `closed_at` | DATETIME | nullable | |

**인덱스**: `(user_id, created_at)`, `(status)`

### 2-3. emotion_logs

감정 분석 로그. SaveRequest type: `emotion_log`.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `log_id` | VARCHAR | **PK** | UUID v4 |
| `session_id` | VARCHAR | **FK** → sessions | |
| `user_id` | VARCHAR | **FK** → users | |
| `mode` | ENUM | not null | |
| `episode_id` | VARCHAR | nullable | 팟캐스트 에피소드 ID |
| `primary_emotion` | VARCHAR | not null | 주요 감정 (영문) |
| `intensity` | FLOAT | not null | 0.0 ~ 1.0 |
| `valence` | FLOAT | not null | -1.0 ~ 1.0 |
| `arousal` | FLOAT | not null | 0.0 ~ 1.0 (DB 저장 전용, API 응답 미포함) |
| `secondary_emotions` | JSON | default `[]` | 부가 감정 배열 |
| `tone_recommendation` | VARCHAR | nullable | 톤 추천 |
| `trace_id` | VARCHAR | nullable | 분산 추적 ID |
| `created_at` | DATETIME | not null | |

**인덱스**: `(user_id, created_at)`, `(primary_emotion)`

### 2-4. podcast_episodes

팟캐스트 에피소드 메타데이터. SaveRequest type: `podcast_episode`.
`ingest_podcast_episodes(session_id, image_url, text)` — Backend `podcasts` 테이블 ingest (별도 fire-and-forget).

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `episode_id` | VARCHAR | **PK** | UUID v4 |
| `session_id` | VARCHAR | **FK** → sessions | |
| `user_id` | VARCHAR | **FK** → users | |
| `episode_title` | VARCHAR | not null | 한국어 제목 |
| `total_duration` | FLOAT | not null | 분 단위 |
| `total_words` | INT | default `0` | 총 단어 수 |
| `segment_count` | INT | not null | 세그먼트 수 (v3.0 이후 미사용, 0 고정) |
| `key_insights` | JSON | not null | 핵심 인사이트 배열 (3-5개, 한국어) |
| `themes` | JSON | not null | 테마 태그 배열 (한국어) |
| `reasoning_depth` | ENUM | default `standard` | `full\|standard\|minimal` |
| `cover_image_url` | VARCHAR | nullable | S3 CDN URL |
| `intent_type` | VARCHAR | default `unknown` | 의도 분류 타입 |
| `complexity_score` | FLOAT | default `0.0` | 입력 복잡도 (0.0~1.0) |
| `safety_status` | ENUM | default `safe` | `safe\|warning\|crisis` |
| `validation_score` | FLOAT | default `0.0` | 검증 점수 |
| `retry_count` | INT | default `0` | TIER 2→3 재시도 횟수 |
| `pipeline_duration_ms` | INT | default `0` | 파이프라인 소요 시간 (ms) |
| `script_text` | TEXT | nullable | **v3.0 신규** — 평탄화된 전체 스크립트 텍스트 |
| `tts_markers_json` | TEXT | nullable | **v3.0 신규** — TTS 마커 JSON 배열 |
| `primary_emotion` | VARCHAR(100) | default `neutral` | **v3.0 신규** — EmotionAgent primary_emotion |
| `secondary_emotions` | JSON | default `[]` | **v3.0 신규** — secondary_emotions[0:2] |
| `trace_id` | VARCHAR | nullable | |
| `correlation_id` | VARCHAR | nullable | |
| `created_at` | DATETIME | not null | |

**인덱스**: `(user_id, created_at)`

> **Backend `podcasts` 테이블 (ingest 전용):** `id(PK,UUID)`, `user_id`, `created_at` 는 백엔드 자동 채움. AI 서버는 `session_id`, `image_url`, `text` 3개만 전송.

### 2-5. ~~podcast_segments~~ [제거됨 2026-04-13]

> v3.0에서 세그먼트 구조 폐기 — `podcast_episodes.script_text`(TEXT) 단일 필드로 통합.
> `dev/local_db/mysql/init.sql`에서 테이블 정의 완전 제거. 이전 이력은 git log 참조.

### 2-6 (구 2-5). learning_patterns

학습 패턴 데이터. SaveRequest type: `learning`.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `pattern_id` | VARCHAR | **PK** | UUID v4 |
| `session_id` | VARCHAR | **FK** → sessions | |
| `user_id` | VARCHAR | **FK** → users | |
| `mode` | ENUM | not null | |
| `preferred_topics` | JSON | default `[]` | 선호 주제 배열 |
| `emotional_patterns` | JSON | default `[]` | 감정 패턴 배열 |
| `interaction_style` | VARCHAR | default `standard` | |
| `personalization_suggestions` | JSON | default `[]` | 개인화 제안 배열 |
| `effectiveness_score` | FLOAT | default `0.0` | 0.0 ~ 1.0 |
| `raw_learning_data` | JSON | default `{}` | 디버깅용 원시 데이터 |
| `trace_id` | VARCHAR | nullable | |
| `created_at` | DATETIME | not null | |

**인덱스**: `(user_id, created_at)`

### 2-7 (구 2-6). visualization_meta

시각화 메타데이터. SaveRequest type: `visualization`.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `visualization_id` | VARCHAR | **PK** | UUID v4 |
| `session_id` | VARCHAR | **FK** → sessions | |
| `user_id` | VARCHAR | **FK** → users | |
| `mode` | ENUM | not null | |
| `episode_id` | VARCHAR | nullable | |
| `s3_key` | VARCHAR | not null | S3 경로 (예: `vis/podcast/sess_xxx/ep_xxx.png`) |
| `cdn_url` | VARCHAR | not null | CDN URL |
| `image_prompt` | TEXT | not null | 이미지 생성 프롬프트 (영문) |
| `interpretation_text` | TEXT | not null | 해석 텍스트 (한국어) |
| `trace_id` | VARCHAR | nullable | |
| `created_at` | DATETIME | not null | |

### 2-8. content_analyses [신규 2026-04-13]

ContentAnalyzer 전체 분석 결과 저장 (내부 분석용). `publisher.publish()` → `BackendClient.save(resource="content_analyses")` 경유.

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `content_id` | VARCHAR(64) | **PK** | |
| `session_id` | VARCHAR(64) | **FK** → sessions, not null | |
| `user_id` | VARCHAR(64) | **FK** → users, not null | |
| `main_theme` | VARCHAR(255) | not null, default `''` | 주요 주제 |
| `sub_themes` | JSON | not null, default `[]` | 하위 주제 배열 |
| `target_duration` | INT | default `4` | 목표 에피소드 길이(분) |
| `narrative_structure` | VARCHAR(100) | default `reflection` | 서사 구조 |
| `emotional_journey` | JSON | default `{}` | 감정 여정 4-키 구조 (opening/development/climax/closing) |
| `confidence` | FLOAT | default `0.0` | 분석 신뢰도 |
| `user_summary_keywords` | JSON | default `[]` | 사용자 요약 키워드 배열 |
| `user_summary_text` | TEXT | default `''` | 사용자 요약 텍스트 |
| `created_at` | DATETIME | not null | |

**인덱스**: `(user_id, session_id)`

### 2-9. user_summaries [신규 2026-04-13]

ContentAnalyzer user_summary 화면 1 전용 저장 (Frontend 1차 로딩 트리거).
`BackendClient.ingest_user_summary(session_id, keywords, description)` — fire-and-forget (user_id 없음, 백엔드 패턴).

| 컬럼 | 타입 | 제약조건 | 설명 |
|------|------|---------|------|
| `id` | VARCHAR(64) | **PK** | 백엔드에서 자동 채움 (UUID) |
| `session_id` | VARCHAR(64) | **FK** → sessions, UNIQUE | 세션당 1건 |
| `keywords` | TEXT | not null, default `''` | AI 서버가 `list[str]` 전송 → 백엔드에서 콤마 join 저장 |
| `description` | TEXT | not null, default `''` | user_summary.summary 텍스트 |
| `created_at` | DATETIME | not null | 백엔드에서 자동 채움 |

---

## 3. Pinecone 인덱스 (2개)

Pinecone은 원본 텍스트를 저장하지 않는다. MySQL PK를 참조하며 벡터 ID 규칙은 `vec_{entity_type}_{mysql_pk}`.

### 공통 메타데이터 (PineconeVectorMetadata)

모든 벡터에 포함:

| 필드 | 타입 | 설명 |
|------|------|------|
| `mysql_id` | String | MySQL PK 참조 |
| `entity_type` | String | `podcast_episode \| knowledge_document` |
| `user_id` | String | |
| `session_id` | String | |
| `mode` | String | |
| `created_at` | String | ISO 8601 (Pinecone은 datetime 미지원) |

### 3-1. mem-podcast-episode

에피소드 시맨틱 검색용. Episode Memory Agent가 유사 에피소드 탐색에 사용.

| 항목 | 값 |
|------|---|
| **네임스페이스** | `user_id` |
| **임베딩 소스** | `title + key_insights + themes` |
| **용도** | Episode Memory — 유사 에피소드 검색 |

| 추가 메타데이터 | 타입 | 설명 |
|--------------|------|------|
| `episode_id` | String | 에피소드 ID |
| `title` | String | 에피소드 제목 |
| `themes` | Array | 테마 태그 (필터링용) |
| `primary_emotion` | String (nullable) | 주요 감정 |

### 3-2. expert-knowledge

전문 지식 검색용. Knowledge Agent가 관련 지식 탐색에 사용.

| 항목 | 값 |
|------|---|
| **네임스페이스** | `domain` |
| **임베딩 소스** | 문서 청크 텍스트 |
| **용도** | Knowledge Agent — 전문 지식 검색 |

| 추가 메타데이터 | 타입 | 설명 |
|--------------|------|------|
| `document_id` | String | 문서 ID |
| `chunk_index` | Int | 청크 인덱스 |
| `domain` | String | `mental_health`, `psychology` 등 |
| `source` | String | papers, guidelines 등 |
| `text_preview` | String | 최대 500자 미리보기 |

---

## 4. Neo4j 노드 (5개)

Neo4j는 관계/패턴 분석 전용이다. 원본 데이터는 MySQL에 존재하며, Neo4j 노드는 `mysql_id`로 MySQL PK를 참조한다.

**공통 속성** (모든 노드): `mysql_id`, `created_at` (ISO 8601)

### 노드 타입

| 레이블 | 고유 속성 | 설명 |
|-------|---------|------|
| `:User` | `user_id` (unique), `display_name` | 사용자 |
| `:Session` | `session_id` (unique), `mode` | 세션 |
| `:Emotion` | `emotion_key` (unique), `emotion_kr`, `category` | 감정 (positive/negative/neutral) |
| `:Topic` | `topic_name` (unique), `domain` | 토픽 (work/family/health 등) |
| `:GoTNode` | `got_node_id` (unique), `episode_id`, `node_type`, `label`, `weight` | GoT 추론 그래프 노드 |

### 관계 타입

| 관계 | 방향 | 속성 | 설명 |
|------|-----|------|------|
| `HAS_SESSION` | User → Session | — | 사용자의 세션 |
| `SHOWS_PATTERN` | User → EmotionPattern | — | 감정 패턴 보유 |
| `PRODUCED_EPISODE` | Session → PodcastEpisode | — | 세션에서 생성된 에피소드 |
| `COVERS` | Episode → Topic | — | 에피소드가 다루는 토픽 |
| `ADDRESSED` | Episode → Emotion | — | 에피소드가 다룬 감정 |
| `OFTEN_COOCCURS` | Emotion → Emotion | `count` | 자주 동시 발생하는 감정 |
| `RELATED_TO` | Topic → Topic | `weight` | 관련 토픽 |
| `LEADS_TO` | GoTNode → GoTNode | `weight`, `relation_type` | GoT 추론 흐름 |
| `REASONED_BY` | Episode → GoTNode | — | 에피소드의 추론 그래프 |

---

## 5. S3 오브젝트 스토리지

S3는 바이너리 에셋만 저장한다. 메타데이터는 MySQL `visualization_meta` 테이블에서 관리.

### 버킷 구조

```
mind-log-bucket/
├── vis/
│   └── podcast/{session_id}/{episode_id}.png       # 팟캐스트 커버 이미지
├── audio/
│   └── podcast/{session_id}/{episode_id}/
│       ├── full.mp3                                # 전체 오디오
│       └── seg_{n}.mp3                             # 세그먼트별 오디오
└── exports/
    └── {user_id}/                                  # 사용자 데이터 내보내기
```

### S3AssetReference 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `bucket` | String | 기본값: `mind-log-bucket` |
| `key` | String | 전체 S3 경로 |
| `content_type` | String | MIME 타입 (`image/png`, `audio/mpeg` 등) |
| `mysql_meta_id` | String | `visualization_meta.visualization_id` 참조 |
| `cdn_url` | String | CDN URL |
| `size_bytes` | Int (optional) | 파일 크기 |

---

## 6. 추적 체계 (Tracing)

요청부터 DB 저장까지 전체 흐름을 추적하는 3단계 ID 체계.

| ID | 생성 규칙 | 범위 | 용도 |
|----|---------|------|------|
| `request_id` | `req_{hex[:12]}` | 개별 API 호출 1:1 | API 요청 식별 |
| `trace_id` | `trace_{hex[:12]}` | 요청 → TIER 0-4 파이프라인 → DB 저장 | 분산 추적 |
| `correlation_id` | `corr_{hex[:12]}` | 하나의 사용자 행동에서 파생된 모든 처리 | 상관관계 그룹핑 |

### 추적 조회 API

```
GET /api/admin/traces/{trace_id}
```

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `include_agent_logs` | false | 에이전트 로그 포함 여부 |
| `include_db_records` | true | DB 저장 기록 포함 여부 |

**TraceResult 응답**:
- `trace_id`, `request_id`, `correlation_id`, `request_summary`
- `pipeline_stages[]`: tier(0-4), agents, duration_ms, status(`ok|crisis|retry|error`)
- `total_pipeline_duration_ms`
- `stored_records[]`: database(`mysql|pinecone|neo4j|s3`), entity_type, record_id, stored_at

---

*출처: Notion "작업중인 db 스키마" + `src/api/external_schemas.py` (56 Pydantic 모델)*
*마지막 업데이트: 2026-03-13*

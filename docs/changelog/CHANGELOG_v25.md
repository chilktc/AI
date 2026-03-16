# Changelog v25

> **날짜**: 2026-03-16
> **요약**: API 응답 슬림화 + Visualization TIER 2 이동 + 재시도 중복 방지

---

## 변경 유형: API 리팩토링 + 파이프라인 최적화

### 배경

- 팟캐스트 에피소드 생성 API 응답이 과도하게 큼 (episode, emotion, cover_image, metadata 전체 포함)
- Backend가 GET API로 조회 가능한 데이터를 중복 반환할 필요 없음
- Visualization이 TIER 4 이후 비동기 실행되어 사용자 대기 시간 증가 (~20초 추가)
- TIER 3 재시도 시 Visualization이 불필요하게 중복 실행

### 변경 내용

#### 코드 수정 (5개 파일)

| 파일 | 변경 |
|------|------|
| `src/api/external_schemas.py` | `SlimPodcastResponse` 추가, `MySQLPodcastEpisode` 메타 필드 6개 추가, `MySQLVisualizationMeta` dead field 3개 제거 |
| `src/api/routes/podcasts.py` | 응답 `PodcastEpisodeResponse` → `SlimPodcastResponse`, `BackgroundTasks` → 동기 저장(`_save_core_data`), 감정 로그 저장 제거 (Emotion Agent가 TIER 1에서 `AgentDataPublisher`로 이미 저장) |
| `src/graph/workflow.py` | `tier2_podcast_fan_out()` 추가 (Script Generator + Visualization 병렬), `async_post`에서 Visualization 제거, 재시도 시 `visual_data` 가드 |
| `src/agents/podcast/script_generator.py` | `episode_structure` str 타입 방어 처리 (프롬프트가 문자열 배열 반환 시 dict 변환) |
| `tests/api/test_podcasts_endpoint.py` | `SlimPodcastResponse` 스키마 맞춤 수정, 불필요 테스트 3개 삭제 (8/8 통과) |

#### 문서 갱신 (4개 파일)

| 파일 | 변경 |
|------|------|
| `docs/architecture/API_ENDPOINTS_RECEIVING.md` | 응답 스키마 `PodcastEpisodeResponse` → `SlimPodcastResponse`로 전면 교체 |
| `docs/architecture/API_ARCHITECTURE.md` | 저장 방식 `BackgroundTasks` → 동기 저장(`_save_core_data`), 타임라인 갱신 |
| `docs/architecture/DATA_SCHEMA.md` | `podcast_episodes` 6컬럼 추가, `visualization_meta` 3컬럼 제거 |
| `docs/architecture/AGENT_ROLES.md` | Visualization Agent TIER 위치 "비동기" → "TIER 2 (병렬)" 갱신 |

### 영향 범위

- **Breaking Change**: 팟캐스트 에피소드 생성 API 응답 스키마 변경 (`PodcastEpisodeResponse` → `SlimPodcastResponse`)
- **Protected File**: `workflow.py` 수정 — 3인 합의 리뷰 필요
- **DB 마이그레이션**: `podcast_episodes` 테이블에 6개 컬럼 추가, `visualization_meta` 테이블에서 3개 컬럼 제거

### 검증 결과

- 유닛 테스트: 8/8 통과 (`tests/api/test_podcasts_endpoint.py`)
- E2E 테스트: 통과 (8/8 필드, BV score 0.87)
- 재시도 발생 시 Visualization 1회만 실행 확인

---

*마지막 업데이트: 2026-03-16*

# Mind-Log API 기능 명세서

> **작성일**: 2026-03-03
> **버전**: v2.0
> **갱신일**: 2026-03-13
> **상태**: 팟캐스트모드 구현 완료 (대화모드 API는 향후 구현 시 추가 예정)

---

## 문서 구성 (v2.0)

v2.0에서 단일 문서(1,865행)를 5개 문서로 분할했습니다. 내용 변경 없이 구조만 재배치했습니다.

| 문서 | 설명 |
|------|------|
| **API_SPEC.md** (본 문서) | 인덱스, API 목록, 협의 사항, 변경이력 |
| [API_ARCHITECTURE.md](API_ARCHITECTURE.md) | 서버 구조, 미들웨어, 파이프라인 실행 흐름 (Phase 0~3) |
| [API_ENDPOINTS_RECEIVING.md](API_ENDPOINTS_RECEIVING.md) | 수신 API (Backend→AI) 9개 엔드포인트 상세 |
| [API_ENDPOINTS_INTERNAL.md](API_ENDPOINTS_INTERNAL.md) | 발신 API (AI→Backend) 5개 + Load API |
| [API_COMMON.md](API_COMMON.md) | 스트리밍 이벤트, 에러 코드, 재시도 정책 |

---

## 서버 구분

> 서버 아키텍처 및 통신 흐름은 [CLAUDE.md](../../CLAUDE.md#백엔드-api-규약), 상세는 [API_ARCHITECTURE.md](API_ARCHITECTURE.md)를 참조하세요.

---

## 카테고리

| 카테고리 | 설명 | 방향 |
|---------|------|------|
| **Podcast** | 팟캐스트 모드 관련 API | 수신 (Backend → AI) |
| **Session** | 세션 생성/종료 API | 수신 (Backend → AI) |
| **History** | 히스토리 조회 API | Backend → Frontend (AI 미관여) |
| **User** | 사용자 프로필 API | 수신 (Backend → AI) |
| **Operational** | 헬스체크, 메트릭 | 수신 (Backend/AWS → AI) |
| **Internal** | AI → Backend 내부 저장 API | 발신 (AI → Backend) |
| **Streaming** | 실시간 이벤트 스트리밍 | AI → Frontend (SSE/WS) |
| **Common** | 공통 에러 코드 등 | — |

---

## API 목록

### ▼ 수신 API (Backend Server → AI Server)

> 상세: [API_ENDPOINTS_RECEIVING.md](API_ENDPOINTS_RECEIVING.md)

#### Podcast

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 1 | [팟캐스트 에피소드 생성](API_ENDPOINTS_RECEIVING.md#1-팟캐스트-에피소드-생성) | `POST` | /api/v1/podcasts/episodes | 구현 완료 | v1.1: 스키마 갱신 |

#### History

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 2 | [감정 추이 조회](API_ENDPOINTS_RECEIVING.md#2-감정-추이-조회) | `GET` | /api/v1/users/{user_id}/emotions | 명세 완료 | v1.2: 엔드포인트 변경, user_id→PathVar |
| 3 | [에피소드 목록 조회](API_ENDPOINTS_RECEIVING.md#3-에피소드-목록-조회) | `GET` | /api/v1/users/{user_id}/podcasts/episodes | 명세 완료 | v1.2: 엔드포인트 변경, themes→Array |
| 4 | [에피소드 단건 조회](API_ENDPOINTS_RECEIVING.md#4-에피소드-단건-조회) | `GET` | /api/v1/users/{user_id}/podcasts/episodes/{episode_id} | 명세 완료 | v1.2: 엔드포인트 변경, 응답 구조 변경 |

#### Session

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 5 | [세션 생성](API_ENDPOINTS_RECEIVING.md#5-세션-생성) | `POST` | /api/v1/sessions | 구현 완료 | v1.1 추가 |
| 6 | [세션 종료](API_ENDPOINTS_RECEIVING.md#6-세션-종료) | `POST` | /api/v1/sessions/{session_id}/close | 구현 완료 | v1.1 추가 |

#### User

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 14 | [사용자 프로필 수정](API_ENDPOINTS_RECEIVING.md#14-사용자-프로필-수정) | `PATCH` | /api/v1/users/{user_id}/profile | 명세 완료 | v1.2 추가 |

#### Operational

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 7 | [헬스체크](API_ENDPOINTS_RECEIVING.md#7-헬스체크) | `GET` | /health, /health/ready | 구현 완료 | v1.1 추가 |
| 8 | [Prometheus 메트릭](API_ENDPOINTS_RECEIVING.md#8-prometheus-메트릭) | `GET` | /metrics | 구현 완료 | v1.1 추가 |

### ▼ 발신 API (AI Server → Backend Server)

> 상세: [API_ENDPOINTS_INTERNAL.md](API_ENDPOINTS_INTERNAL.md)

#### Internal

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 9 | [에피소드 저장](API_ENDPOINTS_INTERNAL.md#9-에피소드-저장) | `POST` | /api/v1/podcast_episodes | 명세 완료 | v1.1 추가 |
| 10 | [감정 로그 저장](API_ENDPOINTS_INTERNAL.md#10-감정-로그-저장) | `POST` | /api/v1/emotion_logs | 명세 완료 | v1.1 추가 |
| 11 | [시각화 메타 저장](API_ENDPOINTS_INTERNAL.md#11-시각화-메타-저장) | `POST` | /api/v1/visualizations | 명세 완료 | v1.1 추가 |
| 12 | [학습 데이터 저장](API_ENDPOINTS_INTERNAL.md#12-학습-데이터-저장) | `POST` | /api/v1/learning | 명세 완료 | v1.1 추가 |
| 13 | [콘텐츠 분석 저장](API_ENDPOINTS_INTERNAL.md#13-콘텐츠-분석-저장) | `POST` | /api/v1/content_analyses | 명세 완료 | v1.1 추가 |

### ▼ Common

> 상세: [API_COMMON.md](API_COMMON.md)

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [공통 Error Code 명세](API_COMMON.md#공통-error-code-명세) | | | 명세 완료 | v1.2: 에러 코드 추가/변경 |
| [스트리밍 이벤트 스키마](API_COMMON.md#스트리밍-이벤트-스키마) | | | 명세 완료 | v1.2 추가 |

---

## Backend 협의 사항

> 출처: BACKEND_API_CONTRACT.md에서 통합 (v1.2)

### 즉시 협의 (1차)

- [ ] Backend 헬스체크 경로 확인 (`/health` 또는 `/actuator/health`)
- [ ] AI → Backend 네트워크 연결 확인 (app-2:8000 → app-3:8080)
- [ ] 인증/인가 방식 결정 (Service-to-service 토큰 / API Key / 내부 네트워크 신뢰)

### API 명세 확정 (2차)

- [ ] Save API 5개 리소스의 data 스키마 검토 및 확정
- [ ] Load API 쿼리 파라미터 및 응답 구조 확정
- [ ] 에러 코드 체계 확정
- [ ] 페이지네이션 방식 (offset vs cursor) 확정

### 향후 협의 (3차)

- [ ] 벡터 검색 엔드포인트 존재 여부 (`vector/search`)
- [ ] 그래프 쿼리 엔드포인트 존재 여부 (`graph/query`)
- [ ] 이미지 업로드 엔드포인트 (`storage/upload`)
- [ ] S3 객체 조회 엔드포인트 (`storage/object`)
- [x] ~~대화모드 전용 리소스 경로~~ — 대화모드 제거 (PR #45), 해당 리소스 불필요

---

## 리소스 경로 정리

| 리소스 경로 | 상태 | Save type | 용도 |
|------------|------|-----------|------|
| `podcast_episodes` | **활성** | `podcast_episode` | 에피소드 메타 + 세그먼트 |
| `emotion_logs` | **활성** | `emotion_log` | 감정 벡터 데이터 |
| `visualizations` | **활성** | `visualization` | 커버 이미지 메타 |
| `learning` | **활성** | `learning` | 학습 패턴 데이터 |
| `content_analyses` | **활성** | `content_analysis` | 콘텐츠 분석 결과 |
| ~~`conversations`~~ | 제거됨 | — | ~~대화 기록~~ (대화모드 제거, PR #45) |
| ~~`memories`~~ | 제거됨 | — | ~~개인 기억 데이터~~ (대화모드 제거) |
| `sessions` | TODO(backend) | — | 세션 메타데이터 (백엔드 팀 협의 필요) |

**상수 정의**: `src/api/backend_resources.py`

---

## 참조 파일 인덱스

| 파일 | 역할 |
|------|------|
| `src/api/main.py` | 서버 시작, 라우터 등록, 예외 핸들러 |
| `src/api/routes/podcasts.py` | 에피소드 생성, 응답 구성, 백그라운드 저장 |
| `src/api/routes/sessions.py` | 세션 생성/종료 |
| `src/api/routes/health.py` | 헬스체크 |
| `src/api/client.py` | BackendClient (save/load) |
| `src/api/publisher.py` | AgentDataPublisher (중간 데이터 전달) |
| `src/api/contracts.py` | SaveRequest, SaveResponse, LoadResponse |
| `src/api/backend_resources.py` | 리소스 경로/타입 상수 |
| `src/api/external_schemas.py` | 외부 API 스키마 (요청/응답) |
| `src/api/middleware.py` | HTTP 요청 로깅 미들웨어 |
| `src/monitoring/prometheus.py` | Prometheus 메트릭 수집/노출 |
| `src/monitoring/callbacks.py` | LangGraph 텔레메트리 콜백 |
| `src/graph/workflow.py` | LangGraph 워크플로우 정의 |

---

## 변경이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-03-03 | 최초 작성 (팟캐스트 에피소드 생성 API) |
| v1.1 | 2026-03-11 | History API 3건 + Session 2건 + Operational 2건 + Internal 5건 + Error Code 추가 |
| v1.2 | 2026-03-13 | History API 엔드포인트 변경 (Notion SSOT 동기화), API_FLOW.md/BACKEND_API_CONTRACT.md 통합, 사용자 프로필 API 추가, 스트리밍 이벤트 스키마 추가, segment_type 영문 통일, Error Code 갱신 |
| v2.0 | 2026-03-13 | 구조 분할 리팩토링: 단일 문서(1,865행)를 5개 문서로 분할. 내용 변경 없이 구조만 재배치. API_ARCHITECTURE, API_ENDPOINTS_RECEIVING, API_ENDPOINTS_INTERNAL, API_COMMON 신규 생성 |

---

*마지막 업데이트: 2026-03-13 v2.0*

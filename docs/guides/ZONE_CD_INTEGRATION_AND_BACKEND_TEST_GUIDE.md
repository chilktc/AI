# Zone C/D ↔ Zone A 통합 및 백엔드 연동 테스트 가이드

> **작성일**: 2026-03-11
> **담당**: 개발자3 (Zone C: 관측성, Zone D: Backend 저장소 추상화)
> **브랜치**: `feature/validation-zone-cd-integration`

Zone C(관측성)와 Zone D(Backend 저장소 추상화) 인프라를 Zone A(API 서버 코어)에 통합한 작업 내역과, 백엔드 서버(app-3) 연동 테스트 방법을 문서화한다.

---

## 목차

1. [통합 작업 요약](#1-통합-작업-요약)
2. [변경 내역](#2-변경-내역)
3. [단위 테스트 (mock 기반)](#3-단위-테스트-mock-기반)
4. [백엔드 통신 아키텍처](#4-백엔드-통신-아키텍처)
5. [백엔드 연동 테스트](#5-백엔드-연동-테스트)
6. [Docker 환경 참조](#6-docker-환경-참조)
7. [백엔드팀 협의 사항](#7-백엔드팀-협의-사항)
8. [검증 체크리스트](#8-검증-체크리스트)

---

## 1. 통합 작업 요약

### 배경

`AI_Team_Work_Zone_Assignment.md`의 의존 관계에 따라 Zone A(API 서버) 기본 골격 완성 후 Zone C/D 통합을 진행:

```
Zone C (관측성) ← A + B 기본 완성 후 착수
```

Zone A가 PR #18, #19로 develop에 머지되어 FastAPI 앱과 라우터가 구축되었으므로, Zone C의 남은 통합 작업과 API 엔드포인트/BackendClient 테스트 작성을 진행하였다.

### 작업 범위

| 영역 | 내용 |
|------|------|
| C-1 구조화 로깅 | HTTP 요청/응답 미들웨어 (`RequestLoggingMiddleware`) |
| C-2 Prometheus | `/metrics` 라우터 등록 + `MindLogTelemetryCallback` 연동 |
| Health Check | Docker/ALB 용어 수정 + `storage_mode` 필드 추가 |
| Docker | healthcheck `curl` → `python urllib` 버그 수정 |
| API 테스트 | 엔드포인트 38개 단위 테스트 + 백엔드 연동 E2E 테스트 코드 |

---

## 2. 변경 내역

### 수정 파일 (4개)

| 파일 | 변경 내용 | 근거 |
|------|----------|------|
| `src/api/main.py` | Prometheus 라우터 등록 + 미들웨어 등록 + lifespan 로깅 | C-2 항목: "main.py에 라우터 등록 필요" |
| `src/api/routes/podcasts.py` | `MindLogTelemetryCallback` + `MetricsCollector.record_pipeline()` | C-2: Prometheus 메트릭 수집원 연결 |
| `src/api/routes/health.py` | 쿠버네티스→Docker/ALB 용어 수정 + `storage_mode` 추가 | 실제 배포: Docker + AWS ALB (EC2) |
| `docker-compose.yml` | healthcheck `curl` → `python urllib` | python:3.11-slim에 curl 미설치 |

### 신규 파일 (12개)

| 파일 | 내용 |
|------|------|
| `src/api/middleware.py` | HTTP 요청/응답 구조화 로깅 (X-Request-ID, 제외 경로, 소요 시간) |
| `tests/api/__init__.py` | 테스트 패키지 |
| `tests/api/conftest.py` | API 테스트 공용 Fixture (mock compiled_graph, mock backend_client) |
| `tests/api/test_health_endpoint.py` | Health/Ready 엔드포인트 테스트 (6건) |
| `tests/api/test_sessions_endpoint.py` | Session 생성/종료 테스트 (8건) |
| `tests/api/test_podcasts_endpoint.py` | Podcast 에피소드 생성 테스트 (11건) |
| `tests/api/test_backend_client.py` | BackendClient save/load 단위 테스트 (8건) |
| `tests/api/test_middleware.py` | 미들웨어 단위 테스트 (5건) |
| `tests/api/e2e/__init__.py` | E2E 테스트 패키지 |
| `tests/api/e2e/conftest.py` | E2E Fixture (실제 BackendClient, CLI 옵션, 연결 확인) |
| `tests/api/e2e/test_backend_health.py` | 백엔드 헬스체크 연결 테스트 (7건) |
| `tests/api/e2e/test_backend_integration.py` | 백엔드 API 통합 테스트 스켈레톤 (8건, 현재 skip) |

---

## 3. 단위 테스트 (mock 기반)

### 실행 방법

```bash
# 전체 API 단위 테스트 (38건, 외부 의존성 없음)
pytest tests/api/ -v --ignore=tests/api/e2e

# 개별 파일 실행
pytest tests/api/test_health_endpoint.py -v
pytest tests/api/test_sessions_endpoint.py -v
pytest tests/api/test_podcasts_endpoint.py -v
pytest tests/api/test_backend_client.py -v
pytest tests/api/test_middleware.py -v
```

### 테스트 구조

```
tests/api/
├── conftest.py                    ← mock Fixture (compiled_graph, backend_client)
├── test_health_endpoint.py        ← GET /health, GET /health/ready
├── test_sessions_endpoint.py      ← POST /api/v1/sessions, POST /close
├── test_podcasts_endpoint.py      ← POST /api/v1/podcasts/episodes
├── test_backend_client.py         ← BackendClient save/load (httpx mock)
├── test_middleware.py             ← X-Request-ID, 로깅 제외 경로
└── e2e/                           ← 실제 백엔드 연동 (아래 섹션 5 참조)
    ├── conftest.py
    ├── test_backend_health.py
    └── test_backend_integration.py
```

### 핵심 설계: Mock 주입

`conftest.py`에서 `compiled_graph`와 `backend_client`를 mock으로 주입하여, LangGraph 파이프라인이나 실제 백엔드 서버 없이 엔드포인트 로직만 격리 테스트:

```python
@pytest.fixture
def test_client(mock_compiled_graph, mock_backend_client):
    with (
        patch("src.api.main.compiled_graph", mock_compiled_graph),
        patch("src.api.main.backend_client", mock_backend_client),
    ):
        from fastapi.testclient import TestClient
        from src.api.main import app
        yield TestClient(app, raise_server_exceptions=False)
```

### 테스트 검증 항목

| 파일 | 테스트 수 | 주요 검증 내용 |
|------|--------:|-------------|
| `test_health_endpoint.py` | 6 | 200 OK, not_ready 상태, storage_mode 포함 |
| `test_sessions_endpoint.py` | 8 | 세션 생성, tracing ID 자동생성, 422 검증 |
| `test_podcasts_endpoint.py` | 11 | 에피소드 생성, 감정 추출, 위기 경고, 파이프라인 에러 |
| `test_backend_client.py` | 8 | save/load 직렬화, HTTP 에러, 리소스 정리 |
| `test_middleware.py` | 5 | X-Request-ID 생성/재사용, 제외 경로 |

---

## 4. 백엔드 통신 아키텍처

### 통신 흐름

```
프론트엔드(app-4:3000)
        │
        ▼ HTTP
Backend 서버(app-3:8080)     ← Spring Boot + MySQL
        │
        ▼ HTTP
AI 서버(app-2:8000)          ← FastAPI + LangGraph 파이프라인
        │
        │ BackendClient (src/api/client.py)
        │  - POST /api/v1/{resource}  → save()
        │  - GET  /api/v1/{resource}  → load()
        │  - 재시도: exponential backoff, 최대 3회
        │  - 타임아웃: 기본 5초
        ▼
Backend 서버(app-3:8080)     ← 데이터 영속화
```

### 설정

| 환경변수 | 설명 | 기본값 |
|---------|------|--------|
| `BACKEND_API_URL` | Backend API 기본 URL | `http://localhost:8080/api/v1` |
| `api.timeout` (config) | 기본 타임아웃 (초) | `5` |
| `STORAGE_MODE` | 저장소 모드 | `local` |

설정 참조: `config/loader.py` (`api_base_url`, `api_timeout` 프로퍼티)

### API 스키마 (contracts.py)

**저장 요청 (SaveRequest)**:
```json
{
    "user_id": "uuid",
    "session_id": "uuid",
    "type": "learning | conversation | emotion_log | ...",
    "data": { "..." },
    "timestamp": "2026-03-11T12:00:00Z"
}
```

**저장 응답 (SaveResponse)**:
```json
{
    "success": true,
    "id": "uuid",
    "message": "saved"
}
```

**조회 응답 (LoadResponse)**:
```json
{
    "success": true,
    "data": [ { "..." } ],
    "total": 10,
    "page": 1
}
```

---

## 5. 백엔드 연동 테스트

### 테스트 단계

| 단계 | 목적 | 테스트 파일 | 시점 |
|------|------|-----------|------|
| **1차** | 네트워크 연결 + 헬스체크 | `test_backend_health.py` | **지금** |
| **2차** | Save/Load API 통합 | `test_backend_integration.py` | API 명세 확정 후 |

### 1차: 백엔드 헬스체크 테스트

백엔드 서버가 실행 중이고 네트워크 연결이 가능한지 확인한다.

```bash
# Backend URL 지정하여 실행 (app-3 IP)
pytest tests/api/e2e/test_backend_health.py -v -m live \
    --backend-url=http://10.7.10.20:8080

# 또는 환경변수로 실행
BACKEND_API_URL=http://10.7.10.20:8080/api/v1 \
    pytest tests/api/e2e/test_backend_health.py -v -m live

# 로컬 개발 시 (localhost)
pytest tests/api/e2e/test_backend_health.py -v -m live \
    --backend-url=http://localhost:8080
```

**검증 항목**:

| 테스트 | 검증 내용 |
|--------|----------|
| `test_backend_server_reachable` | TCP 연결 가능 (포트 열림 확인) |
| `test_backend_responds_to_http` | HTTP 요청 응답 (서버 동작 확인) |
| `test_health_returns_200` | 헬스체크 엔드포인트 200 OK |
| `test_health_response_is_json` | 헬스체크 JSON 응답 |
| `test_api_v1_path_exists` | `/api/v1/` 경로 인식 |
| `test_client_initialization` | BackendClient 생성/종료 |
| `test_client_timeout_setting` | 타임아웃 설정 검증 |

> **참고**: 백엔드가 Spring Boot인 경우 `/actuator/health` 경로도 자동으로 시도한다.

### 2차: 백엔드 API 통합 테스트 (API 명세 확정 후)

```bash
pytest tests/api/e2e/test_backend_integration.py -v -m live \
    --backend-url=http://10.7.10.20:8080
```

현재 모든 테스트에 `pytest.skip("API 명세 미확정")` 적용됨. 활성화 절차:

1. 백엔드팀과 API 명세서 교환
2. `src/api/backend_resources.py`의 `TODO(backend)` 마커 해결
3. 해당 테스트의 `pytest.skip()` 제거
4. 테스트 실행 및 검증

### conftest.py 옵션

| Fixture | 설명 |
|---------|------|
| `backend_url` | `--backend-url` CLI 옵션 또는 `BACKEND_API_URL` 환경변수 |
| `backend_api_url` | `{backend_url}/api/v1` 전체 경로 |
| `skip_if_no_backend` | 백엔드 미연결 시 자동 skip (테스트 실패 방지) |
| `real_backend_client` | 실제 BackendClient 인스턴스 (mock 아님) |
| `http_client` | 동기 httpx.Client (헬스체크용) |

---

## 6. Docker 환경 참조

### 이미지 빌드 및 실행

```bash
# 이미지 빌드
docker compose build

# 컨테이너 실행
docker compose up -d

# 상태 확인
docker ps
docker inspect --format='{{.State.Health.Status}}' mindlog-ai-service
```

### 헬스체크 확인

```bash
# 기본 헬스체크 (ALB용)
curl http://localhost:8000/health
# → {"status": "ok"}

# 심층 상태 확인 (Readiness)
curl http://localhost:8000/health/ready
# → {"status": "ready", "components": {"graph": "ok", "backend_client": "ok"}, "storage_mode": "local"}

# Prometheus 메트릭
curl http://localhost:8000/metrics
# → Prometheus 포맷 출력
```

### 백엔드 연결 설정 (Docker)

`docker-compose.yml`의 `env_file`로 `.env` 파일을 로드하며, 백엔드 URL을 설정:

```bash
# .env 파일
BACKEND_API_URL=http://10.7.10.20:8080/api/v1
STORAGE_MODE=proxy
```

컨테이너 내부에서 BackendClient가 이 URL로 자동 연결된다.

---

## 7. 백엔드팀 협의 사항

### 미확정 항목 (TODO(backend) 마커)

`grep -rn "TODO(backend)" src/` 실행 결과 14개 항목 미확정:

| 파일 | 항목 수 | 내용 |
|------|------:|------|
| `src/api/backend_resources.py` | 8 | 리소스 경로명 (conversations, emotion_logs, memories 등) |
| `src/db/api_proxy.py` | 11 | 프록시 엔드포인트 (vector/search, graph/query, storage 등) |
| `src/db/s3_client.py` | 1 | 업로드 prefix 구조 확정 |

### 1차 협의 (헬스체크)

- [ ] Backend 헬스체크 경로 확인 (`/health` 또는 `/actuator/health`)
- [ ] AI → Backend 네트워크 연결 확인 (app-2 → app-3:8080)
- [ ] `test_backend_health.py` 전체 통과 확인

### 2차 협의 (API 명세)

- [ ] SaveRequest/SaveResponse 스키마 호환 확인
- [ ] 리소스 경로명 확정 (`backend_resources.py` TODO 해결)
- [ ] `test_backend_integration.py` skip 해제 및 실행
- [ ] 에러 응답 형식 (ErrorResponse) 일치 확인

---

## 8. 검증 체크리스트

### 로컬 개발 환경

- [ ] `pytest tests/api/ -v --ignore=tests/api/e2e` → 38건 전체 통과
- [ ] `python3 -c "import tests.api.e2e.test_backend_health"` → import 성공

### 백엔드 연결 테스트

- [ ] `pytest tests/api/e2e/test_backend_health.py -v -m live --backend-url=http://...:8080`
- [ ] TCP 연결 테스트 통과
- [ ] 헬스체크 엔드포인트 200 OK
- [ ] API v1 경로 인식

### API 통합 테스트 (명세 확정 후)

- [ ] `backend_resources.py` TODO 마커 해결
- [ ] `test_backend_integration.py` skip 해제
- [ ] Save → SaveResponse 정상 반환
- [ ] Load → LoadResponse 정상 반환
- [ ] Save → Load 왕복 데이터 일치

### Docker 환경

- [ ] `docker compose build` 성공
- [ ] `docker compose up -d` 후 healthcheck healthy
- [ ] `curl localhost:8000/health` → 200 OK
- [ ] `curl localhost:8000/health/ready` → storage_mode 포함
- [ ] `curl localhost:8000/metrics` → Prometheus 포맷 출력

> **아카이브** — Zone A/B/C/D 체계 기준으로 작성됨. 현재 개발자1/2/3 구조와 다를 수 있으므로 참고용으로만 사용.

# MindLog AI Team — Work Zone Assignment

> **Date**: 2026-03-09
> **Target**: app-2 (EC2 t3.medium, FastAPI:8000)
> **Base Document**: [INFRA_DEPLOYMENT_GUIDE.md](INFRA_DEPLOYMENT_GUIDE.md)
>
> 본 문서는 [INFRA_DEPLOYMENT_GUIDE.md](INFRA_DEPLOYMENT_GUIDE.md)의 작업을 Zone별로 분할한 배정표입니다.

---

## 1. Overview

INFRA_DEPLOYMENT_GUIDE.md의 전체 구현 작업을 **4개 구역**으로 분할합니다. 각 구역은 구현 영역(도메인) 기준이며, 담당자는 추후 배정합니다.

| Zone | Domain | Tasks | Complexity | Key Focus |
|------|--------|-------|------------|-----------|
| **A** | API 서버 코어 | 3개 | M + L | FastAPI + 라우트 + 매핑 |
| **B** | 배포 / DevOps | 6개 | All S | Docker + 환경 분리 + CI |
| **C** | 관측성 / 운영 | 3개 | S + M | 로깅 + 메트릭 + S3 |
| **D** | 타팀 협의 / 이관 | 8개 | - | 블로커 해소 + 스키마 협의 |

---

## Zone A — API 서버 코어

서비스의 핵심 뼈대. 나머지 모든 구역이 이 위에 올라가므로 **최우선 착수** 대상입니다.

### A-1. FastAPI 앱 엔트리포인트 (3-1)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `src/api/main.py` |
| 복잡도 | M (중간) |
| 중요도 | 치명 — Dockerfile CMD가 참조하는 모듈이 부재 |

**핵심 구현 내용:**

- **Lifespan:** `compile_graph()` + `BackendClient` 초기화 (앱 전역 공유)
- **CORS:** 환경변수 `ALLOWED_ORIGINS`로 제어 (로컬: `*`, 프로덕션: app-3 origin)
- **예외처리:** `ErrorResponse`(`external_schemas.py`) 활용 통합 예외 핸들러
- **라우터:** `include_router`로 health, sessions, podcasts 등록

**참조 파일:**

- `src/graph/workflow.py:762-824` — `compile_graph()`
- `src/api/client.py` — `BackendClient`
- `src/api/external_schemas.py:101-122` — `ErrorResponse`, `ErrorDetail`

---

### A-2. Health Check 엔드포인트 (3-2)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `src/api/routes/health.py` |
| 복잡도 | S (소) |
| 중요도 | 치명 — ALB 헬스체크 실패 시 트래픽 차단 |

**핵심 구현 내용:**

- **GET /health:** ALB 헬스체크용 (200 OK 반환)
- **GET /health/ready:** LangGraph 컴파일 + BackendClient + Settings 로드 상태 확인

---

### A-3. FastAPI 라우트 핸들러 (3-3)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `src/api/routes/__init__.py`, `sessions.py`, `podcasts.py` |
| 복잡도 | L (대) — 가장 복잡한 작업 |
| 중요도 | 치명 — HTTP 엔드포인트 부재 |

**세션 라우트 (sessions.py):**

- `POST /api/sessions` — 세션 생성 (session_id 서버 생성)
- `POST /api/sessions/{id}/close` — 세션 종료 + Learning Agent 트리거

**팟캐스트 라우트 (podcasts.py) — AgentState 매핑:**

| PodcastRequest 필드 | AgentState 필드 | 변환 |
|---------------------|----------------|------|
| `topic` + `description` | `user_input` | 문자열 결합 |
| `user_id` | `user_id` | 직접 매핑 |
| `session_id` | `session_id` | 직접 매핑 |
| — | `mode` | `"podcast"` 고정 |

**결과 매핑:**

| AgentState 결과 | Response 필드 | 변환 함수 |
|----------------|--------------|-----------|
| `script_draft` + `final_output` | `episode` | `_build_episode_data()` |
| `emotion_vectors` | `emotion` | `_extract_emotion()` |
| `safety_flags` | `safety_alert` | `_extract_safety_alert()` |
| `visual_data` | `cover_image` | `_extract_cover_image()` |

**참조:** `src/api/external_schemas.py`, `src/graph/workflow.py`, `src/models/agent_state.py`

---

## Zone B — 배포 / DevOps

코드를 AWS 환경에 올리기 위한 컨테이너화와 환경 설정. **Zone A와 병행 진행** 가능합니다.

### B-1. 프롬프트 독립 배포 전략 (3-4)

| 항목 | 내용 |
|------|------|
| 복잡도 | S |
| 중요도 | 치명 — `prompts/`가 `.gitignore`에 포함, Docker 이미지에 누락 |

- **방법:** Docker 볼륨 마운트 (`./prompts:/app/prompts`)
- **업데이트:** SSM 접속 → YAML 수정 → `docker compose restart`
- **기존 인프라:** `prompt_loader.py`의 `PROMPT_DIR` 환경변수 지원 활용

---

### B-2. docker-compose.yml (3-5)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `docker-compose.yml` |
| 복잡도 | S |

- 포트: `8000:8000`, `env_file: .env`, volumes: `logs` + `prompts`
- healthcheck: `curl -f http://localhost:8000/health` (30s interval)
- `restart: unless-stopped`

---

### B-3. .dockerignore (3-6)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `.dockerignore` |
| 복잡도 | S |

- 제외 대상: `.git`, `__pycache__`, `.env`, `tests/`, `docs/`, `prompts/`, `*.md` 등
- `prompts/` 제외 이유: 볼륨 마운트로 관리하므로 이미지 내 포함 불필요

---

### B-4. .env.example 프로덕션 섹션 (3-7)

| 항목 | 내용 |
|------|------|
| 수정 파일 | `.env.example` |
| 복잡도 | S |

- 추가: `APP_ENV`, `LLM_PROVIDER`, `AWS_REGION`, `BACKEND_API_URL`, `ALLOWED_ORIGINS`, `LOG_FORMAT`, `LOG_LEVEL`, `PROMPT_DIR`

---

### B-5. 환경 분리 전략 (3-11)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `config/settings.production.yaml` |
| 수정 파일 | `config/loader.py` (`_deep_merge` 추가) |
| 복잡도 | S |

- `APP_ENV`에 따라 `settings.{env}.yaml` 오버레이 자동 로드
- `get_settings()` 시그니처 불변 유지

---

### B-6. CI Docker 빌드 검증 (3-12)

| 항목 | 내용 |
|------|------|
| 수정 파일 | `.github/workflows/ci.yml` |
| 복잡도 | S |

- `docker-build` job 추가: `docker build -t mindlog-ai:test .`

---

## Zone C — 관측성 / 운영 (Observability)

프로덕션 운영을 위한 모니터링, 로깅, S3 연동. **Zone A 기본 골격 완성 후** 진행합니다.

### C-1. 구조화 JSON 로깅 (3-8)

| 항목 | 내용 |
|------|------|
| 수정 파일 | `src/utils/logger.py` |
| 추가 의존성 | `python-json-logger>=2.0.0` |
| 복잡도 | S |

- `APP_ENV=production` 시 JSON, 개발 시 평문 텍스트
- `get_agent_logger()` 시그니처 불변 유지
- OpenSearch 수집용 포맷

---

### C-2. Prometheus 메트릭 엔드포인트 (3-9)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `src/monitoring/prometheus.py` |
| 추가 의존성 | `prometheus-client>=0.20.0` |
| 복잡도 | M |

- `GET /metrics` 엔드포인트 → Prometheus → Grafana
- 메트릭: 요청 수, 파이프라인 실행 시간, 에이전트별 실행 시간, LLM 토큰, 위기 이벤트
- `main.py`에 라우터 등록 필요

---

### C-3. S3 Read 클라이언트 (3-10)

| 항목 | 내용 |
|------|------|
| 생성 파일 | `src/db/__init__.py`, `src/db/s3_client.py` |
| 복잡도 | S |

- boto3 기반 읽기 전용 (`s3:Get*`, `s3:List*`)
- `get_object`, `list_objects`, `generate_presigned_url`
- S3 쓰기는 `BackendClient` 경유 (AI팀 쓰기 권한 없음)

---

## Zone D — 타팀 협의 / 이관

코드 작업은 아니지만, **블로커가 될 수 있어 가장 먼저 시작**해야 합니다.

> ⚠️ **Bedrock IAM 권한(4-1)** 과 **Backend API 연동(4-2)** 은 블로커 위험이 높습니다.

### 인프라팀 협의 사항

| # | 항목 | 블로커 위험 | 담당자 |
|---|------|------------|--------|
| 4-1 | Bedrock `InvokeModel` IAM 권한 추가 | **높음** — LLM 호출 불가 | |
| 4-5 | ALB 헬스체크 경로 `/health` 설정 | 중간 | |
| 4-6 | Prometheus 스크래핑 대상 추가 | 낮음 | |
| 4-7 | 로그 수집 에이전트 설치 (Filebeat/FluentBit) | 낮음 | |

### Backend팀 협의 사항

| # | 항목 | 블로커 위험 | 담당자 |
|---|------|------------|--------|
| 4-2 | API 연동 스키마 확인 + 통신 테스트 | **높음** — 데이터 저장 불가 | |
| 4-3 | DB 접근 방식 결정 (Backend 경유 vs 직접) | 중간 | |
| 4-4 | S3 이미지 업로드 경로 결정 | 중간 | |
| 4-8 | CI/CD 자동 배포 (향후 로드맵) | 낮음 | |

---

## 2. Dependency & Timeline

### 의존 관계

```
Zone D (타팀 협의)  ← 즉시 시작 (블로커 선제 해소)
    ↓
Zone A (API 코어)  ←→  Zone B (배포/DevOps)   ← 병행 가능
    ↓                      ↓
Zone C (관측성)    ←  A + B 기본 완성 후 착수
    ↓
통합 검증 (app-2 배포 + ALB 연결)
```

### 타임라인

| 순서 | Zone | 시점 | 선행 조건 | 병행 가능 |
|------|------|------|-----------|-----------|
| 0 | D (타팀 협의) | Week 1 즉시 | 없음 | A, B |
| 1 | A (API 코어) | Week 1 | 없음 | B |
| 1 | B (배포/DevOps) | Week 1 | 없음 | A |
| 2 | C (관측성) | Week 1 후반~Week 2 | A 기본 완성 | - |
| 3 | 통합 검증 | Week 2 후반 | A + B + C 완성 | - |

- **Week 1:** Zone D(협의) 즉시 시작 + Zone A(코어)와 Zone B(배포) 병행 진행
- **Week 2:** Zone C(관측성) 진행 + 통합 검증 (app-2 배포 + ALB 연결)

---

## 3. Verification Checklist

### 로컬 검증

1. Docker 빌드: `docker compose up -d` → `curl localhost:8000/health` → 200 OK
2. 팟캐스트: `POST /api/podcasts/episodes` → 에피소드 응답 수신
3. 메트릭: `curl localhost:8000/metrics` → Prometheus 포맷 출력
4. JSON 로그: `APP_ENV=production` 실행 → JSON 로그 확인
5. 테스트: `pytest` + `ruff check` + `mypy` 통과

### 프로덕션 검증 (app-2)

1. SSM 접속 → `/home/ubuntu/app/`에서 `docker compose up -d`
2. ALB 헬스체크 통과 확인 (EC2 > Target Groups > Healthy)
3. Backend(app-3)에서 AI 서버 호출 성공 확인
4. Grafana(app-1:3001)에서 메트릭 수집 확인
5. OpenSearch(app-1:5601)에서 JSON 로그 수집 확인

---

## 4. References

### 노션 문서

- [260308 IAM 계정](https://www.notion.so/260308-IAM-31d9e3e335cc809c9539f209d5d30e78)
- [260308 서버 접속 방법](https://www.notion.so/260308-SSH-31d9e3e335cc801f8e5dc6698119cd84)
- [260308 인프라 인수인계 보고서](https://www.notion.so/260308-31d9e3e335cc8020b07cdfcdb09cfc7e)

### GitHub 인프라 레포

- [chilktc/infra](https://github.com/chilktc/infra)
  - `aws/` — 클라우드 인프라 (VPC, Subnet, ALB, IAM)
  - `platform/` — K8s 플랫폼 (Istio, ArgoCD, Prometheus)
  - `apps/` — 애플리케이션 매니페스트
  - `gitops/` — ArgoCD GitOps 루트
  - `docs/` — 아키텍처, PRD, 스펙 문서

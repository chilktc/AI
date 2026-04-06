> **아카이브** — Zone A/B/C/D 체계 기준으로 작성됨. 현재 개발자1/2/3 구조와 다를 수 있으므로 참고용으로만 사용.

# Mind-Log 외부 인프라 전환 — 단계별 구현 가이드

> **작성일**: 2026-03-09
> **기준 문서**: AI_Team_Infrastructure_Guide.docx
> **배포 타겟**: app-2 (EC2 t3.medium, <APP2_IP>), Docker, FastAPI:8000

내부 파이프라인(LangGraph TIER 기반)을 완성 단계까지 구축한 상태에서,
AWS EC2 배포, 백엔드 API 연동, 모니터링 연결 등 외부 인프라 작업을 진행한다.

**핵심 원칙**: 개발은 로컬에서, 배포는 AWS에서. 모든 환경 차이는 환경변수와 설정 오버레이로 제어하며 코드 자체는 동일하다.

---

## 목차

1. [인프라팀 구축 완료 현황](#1-인프라팀이-이미-구축-완료-ai팀-작업-불필요)
2. [AI팀 접근 확인 체크리스트](#2-ai팀-접근-확인-전달받은-정보로-즉시-가능)
3. [AI팀 구현 작업 (코드 포함)](#3-ai팀-구현-작업-우선순위-순)
4. [타팀 협의 필수 사항](#4-타팀-협의-필수-사항)
5. [타팀 이관 체크리스트](#5-타팀-이관-체크리스트)
6. [로컬 환경 vs 프로덕션 환경](#6-로컬-환경-vs-프로덕션-환경)
7. [개발자별 작업 배분](#7-개발자별-작업-배분)
8. [검증 방법](#8-검증-방법)

---

## 1. 인프라팀이 이미 구축 완료 (AI팀 작업 불필요)

### 네트워크/컴퓨팅

- VPC 10.7.0.0/16, AZ 2개 (ap-northeast-2a, 2c)
- EC2 t3.medium x4 (Ubuntu 22.04, Docker/Docker Compose 사전 설치)
- ALB: `<ALB_DOMAIN>`

### 서버 할당

| 서버 | IP | 역할 | 포트 |
|------|-----|------|------|
| app-1 | <APP1_IP> | 모니터링 | Grafana:3001, OpenSearch:5601, Prometheus:9090 |
| app-2 | <APP2_IP> | **AI 서비스** | FastAPI:8000 |
| app-3 | <APP3_IP> | Backend | Spring Boot:8080 |
| app-4 | <APP4_IP> | Frontend | Next.js:3000 |

### 접근/보안

- IAM 사용자: `<IAM_USER_AI>` / 그룹: `7team_AI_Group`
- SSM 접근 구성 완료 (SSH 차단, SSM 전용)
- S3 읽기 전용 (s3:Get*, s3:List*)
- 배포 경로: `/home/ubuntu/app/`, Docker 유저: ubuntu (sudo 불필요)
- S3 백업 버킷: `<S3_LOGS_BUCKET>`

---

## 2. AI팀 접근 확인 (전달받은 정보로 즉시 가능)

전달받은 AWS 크레덴셜(콘솔 URL, 사용자명, 비밀번호, 액세스 키)로 바로 수행 가능한 항목.

### 콘솔 접속

- [ ] AWS 콘솔 로그인: `https://<AWS_ACCOUNT_ID>.signin.aws.amazon.com/console` (사용자명: `<IAM_USER_AI>`)
- [ ] EC2 > Instances에서 `app-2` 선택 > Connect > Session Manager 탭 > Connect
- [ ] app-2 터미널에서 확인:
  ```bash
  docker --version
  docker compose version
  ls -la /home/ubuntu/app/
  ```

### AWS CLI (액세스 키 사용)

- [ ] AWS CLI 설정:
  ```bash
  aws configure
  # 전달받은 액세스 키 / 시크릿 키 입력
  # Default region: ap-northeast-2
  # Default output: json
  ```
- [ ] S3 읽기 테스트:
  ```bash
  aws s3 ls s3://<S3_LOGS_BUCKET>/
  ```
- [ ] IAM 권한 확인 (Bedrock 권한 포함 여부):
  ```bash
  aws iam list-attached-group-policies --group-name 7team_AI_Group
  ```

### 모니터링 대시보드

- [ ] Grafana: `http://ALB_DOMAIN:3001` 접속 (admin / <팀장에게 별도 확인>)
- [ ] OpenSearch: `http://ALB_DOMAIN:5601` 접속 (admin / <팀장에게 별도 확인>)

### 네트워크 확인 (app-2 SSM 접속 후)

- [ ] Backend 통신 테스트:
  ```bash
  curl http://<APP3_IP>:8080
  ```
- [ ] Bedrock 권한 테스트:
  ```bash
  aws bedrock-runtime invoke-model \
    --model-id anthropic.claude-haiku-4-5-20251001-v1:0 \
    --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}' \
    --region ap-northeast-2 \
    output.json
  ```

---

## 3. AI팀 구현 작업 (우선순위 순)

### 3-1. FastAPI 앱 엔트리포인트 [치명]

**문제**: Dockerfile CMD가 `python -m src.api.main`을 참조하지만 이 모듈이 존재하지 않는다. 앱 시작 불가.

**생성 파일**: `src/api/main.py`

**핵심 설계**:
- Lifespan에서 `compile_graph()` + `BackendClient` 초기화 (앱 전역 공유)
- 환경변수 `ALLOWED_ORIGINS`로 CORS 제어 (로컬: `*`, 프로덕션: app-3 origin)
- `ErrorResponse`(`external_schemas.py`)를 활용한 통합 예외 처리
- 라우트 라우터를 `include_router`로 등록

**참조 파일**:
- `src/graph/workflow.py:762-824` — `compile_graph()` 함수
- `src/api/client.py` — `BackendClient` (비동기 HTTP 클라이언트)
- `src/api/external_schemas.py:101-122` — `ErrorResponse`, `ErrorDetail`

```python
"""
FastAPI 앱 엔트리포인트.

Dockerfile CMD: python -m src.api.main
로컬 개발: uvicorn src.api.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from config.loader import get_settings
from src.api.client import BackendClient
from src.api.external_schemas import ErrorDetail, ErrorResponse
from src.api.routes import health, podcasts, sessions
from src.graph.workflow import compile_graph

logger = logging.getLogger("mind-log.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 리소스를 관리한다."""
    # --- 시작 ---
    settings = get_settings()
    logger.info("Mind-Log AI 서버 시작 (v%s)", settings.app_version)

    # LangGraph 컴파일 (앱 전역 공유)
    app.state.compiled_graph = compile_graph("unified")
    logger.info("LangGraph 컴파일 완료")

    # BackendClient 초기화
    app.state.backend_client = BackendClient()
    logger.info("BackendClient 초기화 완료 (base_url=%s)", settings.api_base_url)

    yield

    # --- 종료 ---
    await app.state.backend_client.close()
    logger.info("Mind-Log AI 서버 종료")


def create_app() -> FastAPI:
    """FastAPI 앱을 생성한다."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # --- CORS ---
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- 예외 핸들러 ---
    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(code="VALIDATION_ERROR", message=str(exc))
            ).model_dump(mode="json"),
        )

    @app.exception_handler(httpx.HTTPStatusError)
    async def http_status_error_handler(
        request: Request, exc: httpx.HTTPStatusError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="BACKEND_ERROR",
                    message=f"Backend API 오류: {exc.response.status_code}",
                )
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def general_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("처리되지 않은 예외: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(code="SERVER_ERROR", message="내부 서버 오류")
            ).model_dump(mode="json"),
        )

    # --- 라우터 등록 ---
    app.include_router(health.router)
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(podcasts.router, prefix="/api/v1")

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("APP_ENV", "development") == "development",
    )
```

**환경 분리 포인트**:
- `ALLOWED_ORIGINS`: 로컬 `*` / 프로덕션 `http://<APP3_IP>:8080`
- `APP_ENV`: 로컬 `development`(reload=True) / 프로덕션 `production`(reload=False)
- `PORT`: 기본 8000, 환경변수로 오버라이드 가능

**담당**: 개발자1 / **복잡도**: M

---

### 3-2. Health Check 엔드포인트 [치명]

**문제**: ALB가 헬스체크 실패 시 app-2로 트래픽을 보내지 않는다.

**생성 파일**: `src/api/routes/health.py`

```python
"""Health check 엔드포인트 — ALB 헬스체크 + 서비스 준비 상태 확인."""

from __future__ import annotations

from fastapi import APIRouter, Request

from config.loader import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """ALB 헬스체크용. 앱이 살아있으면 200 OK."""
    settings = get_settings()
    return {"status": "healthy", "version": settings.app_version}


@router.get("/health/ready")
async def readiness_check(request: Request) -> dict:
    """서비스 준비 상태 확인. LangGraph 컴파일 + Settings 로드 확인."""
    checks = {
        "graph_compiled": hasattr(request.app.state, "compiled_graph")
        and request.app.state.compiled_graph is not None,
        "backend_client": hasattr(request.app.state, "backend_client")
        and request.app.state.backend_client is not None,
        "settings_loaded": True,
    }
    try:
        get_settings()
    except Exception:
        checks["settings_loaded"] = False

    all_ready = all(checks.values())
    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
    }
```

**담당**: 아무 개발자 / **복잡도**: S

---

### 3-3. FastAPI 라우트 핸들러 [치명]

**문제**: `external_schemas.py`에 Pydantic 스키마가 정의되어 있으나 HTTP 엔드포인트가 없다.

#### 3-3-a. 라우트 패키지 초기화

**생성 파일**: `src/api/routes/__init__.py`

```python
"""API 라우트 패키지."""
```

#### 3-3-b. 세션 라우트

**생성 파일**: `src/api/routes/sessions.py`

**참조**: `src/api/external_schemas.py:135-199` — `SessionCreateRequest`/`Response`, `SessionCloseRequest`

```python
"""세션 관리 라우트."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter

from src.api.external_schemas import (
    RequestTracing,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionCreateResponse,
)

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(req: SessionCreateRequest) -> SessionCreateResponse:
    """
    세션을 생성한다.

    POST /api/v1/sessions
    세션 ID는 서버에서 생성하여 반환한다.
    """
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    return SessionCreateResponse(
        session_id=session_id,
        mode=req.mode,
        created_at=datetime.now(timezone.utc),
        tracing=req.tracing,
    )


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, req: SessionCloseRequest) -> dict:
    """
    세션을 종료한다.

    POST /api/v1/sessions/{session_id}/close
    Learning Agent를 비동기로 트리거한다 (향후 구현).
    """
    # TODO: Learning Agent 비동기 트리거
    # TODO: BackendClient를 통해 세션 종료 기록 저장
    return {
        "success": True,
        "session_id": session_id,
        "message": "세션이 종료되었습니다",
    }
```

#### 3-3-c. 팟캐스트 라우트

**생성 파일**: `src/api/routes/podcasts.py`

**참조**:
- `src/api/external_schemas.py:293-329` — `PodcastRequest` (AgentState 매핑 주석 포함)
- `src/api/external_schemas.py:596-694` — `PodcastEpisodeResponse`, `PodcastEpisodeData`
- `src/graph/workflow.py:762-824` — `compile_graph()`, `ainvoke()` 사용법
- `src/models/agent_state.py` — `AgentState` 필드 정의

**AgentState 매핑** (`external_schemas.py` 주석 기반):

| PodcastRequest 필드 | AgentState 필드 | 변환 |
|---------------------|----------------|------|
| `topic` + `description` | `user_input` | 문자열 결합 |
| `user_id` | `user_id` | 직접 매핑 |
| `session_id` | `session_id` | 직접 매핑 |
| — | `mode` | `"podcast"` 고정 |

**결과 매핑**:

| AgentState 필드 | PodcastEpisodeResponse 필드 |
|----------------|---------------------------|
| `script_draft` + `final_output` | `episode` |
| `emotion_vectors` | `emotion` |
| `safety_flags` | `safety_alert` |
| `visual_data` | `cover_image` |

```python
"""팟캐스트 에피소드 생성 라우트."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

from src.api.external_schemas import (
    EmotionSummary,
    ErrorDetail,
    ErrorResponse,
    PodcastEpisodeData,
    PodcastEpisodeResponse,
    PodcastRequest,
    PodcastResponseMeta,
    PodcastSegment,
    SafetyAlertData,
    VisualizationData,
)
from src.monitoring.callbacks import MindLogTelemetryCallback

logger = logging.getLogger("mind-log.api.podcasts")

router = APIRouter(tags=["podcasts"])


def _build_agent_state(req: PodcastRequest) -> dict[str, Any]:
    """PodcastRequest → AgentState 초기 상태를 구성한다."""
    # external_schemas.py 매핑 주석 기반:
    # user_input ← topic + (description or "")
    user_input = req.topic
    if req.description:
        user_input = f"{req.topic}\n{req.description}"

    return {
        "user_input": user_input,
        "user_id": req.user_id,
        "session_id": req.session_id,
        "mode": "podcast",
    }


def _build_episode_data(
    result: dict[str, Any], session_id: str
) -> PodcastEpisodeData:
    """AgentState 결과 → PodcastEpisodeData로 변환한다."""
    script_draft = result.get("script_draft", {})
    episode_id = f"ep_{uuid.uuid4().hex[:12]}"

    # script_draft에서 세그먼트 추출
    raw_segments = script_draft.get("segments", [])
    segments = []
    for seg in raw_segments:
        segments.append(
            PodcastSegment(
                segment_id=seg.get("segment_id", f"seg_{uuid.uuid4().hex[:8]}"),
                segment_type=seg.get("segment_type", "unknown"),
                duration_minutes=seg.get("duration_minutes", 1),
                script_text=seg.get("script_text", ""),
                word_count=seg.get("word_count", 0),
                emotional_tone=seg.get("emotional_tone", "neutral"),
                tts_markers=seg.get("tts_markers", []),
            )
        )

    return PodcastEpisodeData(
        episode_id=episode_id,
        session_id=session_id,
        title=script_draft.get("title", ""),
        total_duration_minutes=script_draft.get("total_duration_minutes", 5),
        segments=segments,
        key_insights=script_draft.get("key_insights", []),
        themes=script_draft.get("themes", []),
        created_at=datetime.now(timezone.utc),
    )


def _extract_emotion(result: dict[str, Any]) -> EmotionSummary | None:
    """AgentState.emotion_vectors → EmotionSummary 요약."""
    ev = result.get("emotion_vectors")
    if not ev:
        return None
    return EmotionSummary(
        primary_emotion=ev.get("primary_emotion", "neutral"),
        primary_emotion_kr=ev.get("primary_emotion_kr", "중립"),
        intensity=ev.get("intensity", 0.5),
        valence=ev.get("valence", 0.0),
        secondary_emotions=ev.get("secondary_emotions", []),
        tone_recommendation=ev.get("tone_recommendation", "supportive_neutral"),
    )


def _extract_safety_alert(result: dict[str, Any]) -> SafetyAlertData | None:
    """AgentState.safety_flags → SafetyAlertData (safe가 아닌 경우만)."""
    sf = result.get("safety_flags")
    if not sf or sf.get("status") == "safe":
        return None
    return SafetyAlertData(
        status=sf.get("status", "warning"),
        alert_message=sf.get("alert_message", ""),
        helpline_info=sf.get("helpline_info"),
        show_emergency_button=sf.get("show_emergency_button", False),
    )


def _extract_cover_image(result: dict[str, Any]) -> VisualizationData | None:
    """AgentState.visual_data → VisualizationData."""
    vd = result.get("visual_data")
    if not vd:
        return None
    from src.api.external_schemas import VisualizationStyleInfo

    style_raw = vd.get("style_info", {})
    return VisualizationData(
        image_url=vd.get("image_url"),
        interpretation_text=vd.get("interpretation_text", ""),
        style_info=VisualizationStyleInfo(
            type=style_raw.get("type", "Conceptual"),
            palette=style_raw.get("palette", "blue"),
            gradient=style_raw.get("gradient", ["#4A90D9", "#357ABD"]),
            pattern=style_raw.get("pattern", "shimmer_noise"),
            primary_emotion=style_raw.get("primary_emotion", "neutral"),
            intensity_label=style_raw.get("intensity_label", "Balanced"),
        ),
    )


@router.post("/podcasts/episodes", response_model=PodcastEpisodeResponse)
async def create_episode(
    req: PodcastRequest, request: Request
) -> PodcastEpisodeResponse:
    """
    팟캐스트 에피소드를 생성한다.

    POST /api/v1/podcasts/episodes

    1. PodcastRequest → AgentState 초기 상태 구성
    2. compiled_graph.ainvoke() 호출
    3. AgentState 결과 → PodcastEpisodeResponse 매핑
    """
    start_time = time.time()
    compiled_graph = request.app.state.compiled_graph

    # 1. AgentState 구성
    state = _build_agent_state(req)

    # 2. 파이프라인 실행
    callback = MindLogTelemetryCallback()
    config = {
        "configurable": {"thread_id": f"session_{req.session_id}"},
        "callbacks": [callback],
    }
    result = await compiled_graph.ainvoke(state, config=config)

    # 3. 결과 매핑
    duration_ms = int((time.time() - start_time) * 1000)
    intent = result.get("intent", {})
    episode_data = _build_episode_data(result, req.session_id)

    return PodcastEpisodeResponse(
        episode=episode_data,
        emotion=_extract_emotion(result),
        safety_alert=_extract_safety_alert(result),
        cover_image=_extract_cover_image(result),
        metadata=PodcastResponseMeta(
            pipeline_duration_ms=duration_ms,
            intent_type=intent.get("intent_type", "podcast_creation"),
            complexity_score=intent.get("complexity_score", 0.5),
            reasoning_depth=intent.get("reasoning_depth", "standard"),
            retry_count=result.get("iteration_count", 0),
            total_words=sum(s.word_count for s in episode_data.segments),
        ),
        tracing=req.tracing,
    )
```

**담당**: 개발자1 / **복잡도**: L

---

### 3-4. 프롬프트 독립 배포 전략 [치명]

**문제**: `prompts/`가 `.gitignore:66`에 포함되어 git에 추적되지 않는다. Docker 이미지에도 누락된다.
프롬프트는 코드 배포와 독립적으로 업데이트할 수 있어야 한다.

**기존 인프라 활용** (코드 수정 없이 동작):
- `src/agents/shared/prompt_loader.py:424` — `PROMPT_DIR` 환경변수 지원이 이미 구현됨
- `src/agents/shared/prompt_loader.py:51` — 허용 디렉토리: `prompts`, `prompts_dev`, `prompts_staging`, `prompts_prod`
- `src/agents/shared/prompt_loader.py:412` — `clear_cache()` 핫리로드 메서드 존재

**권장 방법**: Docker 볼륨 마운트

`docker-compose.yml`에서:
```yaml
volumes:
  - ./prompts:/app/prompts
```

app-2의 `/home/ubuntu/app/prompts/`에 YAML 파일을 별도 관리한다.

**업데이트 절차**:
1. SSM으로 app-2 접속
2. `/home/ubuntu/app/prompts/` 하위 YAML 파일 수정
3. `docker compose restart` (컨테이너 재시작, 이미지 재빌드 불필요)

**장점**:
- Docker 이미지 재빌드 없이 프롬프트 업데이트 가능
- 코드와 프롬프트의 배포 주기를 완전히 분리
- 기존 `PromptLoader` 코드 수정 없이 동작
- `prompts_prod` 디렉토리를 사용하면 환경별 프롬프트 분리도 가능

**초기 배포**:
- 로컬 `prompts/` 디렉토리를 app-2로 전송 (scp 또는 tar + S3 경유)
- SSM 터미널에서 직접 업로드하거나, 인프라팀에 S3 임시 쓰기 권한 요청

**버전 관리 (선택)**:
- `prompts/`를 별도 Git 레포로 관리하면 변경 이력 추적 + 코드 리뷰 가능
- app-2에서 `git clone`/`git pull`로 업데이트

**담당**: 팀 합의 / **복잡도**: S

---

### 3-5. docker-compose.yml 생성

**문제**: 인프라 가이드가 `/home/ubuntu/app/`에서 `docker compose up -d` 실행을 요구한다.

**생성 파일**: `docker-compose.yml`

```yaml
services:
  ai-server:
    build: .
    container_name: mindlog-ai
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./prompts:/app/prompts
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

**환경 분리**:
- 로컬: `.env`에 `LLM_PROVIDER=ollama` 또는 `openai`
- 프로덕션: `.env`에 `LLM_PROVIDER=bedrock`, `BACKEND_API_URL=http://<APP3_IP>:8080/api/v1`
- `prompts/` 볼륨 마운트로 프롬프트 독립 배포

**담당**: 아무 개발자 / **복잡도**: S

---

### 3-6. .dockerignore 생성

**문제**: 현재 없어서 `COPY . .` 실행 시 `.git`, `__pycache__`, `.env`, 테스트 등이 이미지에 포함된다.

**생성 파일**: `.dockerignore`

```
.git/
.github/
.claude/
.langgraph_api/
__pycache__/
*.pyc
.env
.env.*
!.env.example
tests/
dev/
docs/
ProjectDocs/
data/outputs/images/
prompts/
*.md
.ruff_cache/
.mypy_cache/
.pytest_cache/
```

> `prompts/`를 제외하는 이유: 볼륨 마운트로 관리하므로 이미지에 포함시키지 않는다.

**담당**: 아무 개발자 / **복잡도**: S

---

### 3-7. 프로덕션 .env 템플릿 업데이트

**문제**: 현재 `.env.example`은 로컬 개발용만 정의되어 있다.

**수정 파일**: `.env.example`

기존 내용 유지 + 아래 프로덕션 섹션 추가:

```bash
# === Production (app-2 배포 시) ===
# APP_ENV=production
# LLM_PROVIDER=bedrock
# AWS_REGION=ap-northeast-2
# BACKEND_API_URL=http://<APP3_IP>:8080/api/v1
# ALLOWED_ORIGINS=http://<APP3_IP>:8080,http://<APP4_IP>:3000
# LOG_FORMAT=json
# LOG_LEVEL=INFO
# PROMPT_DIR=prompts
```

**복잡도**: S

---

### 3-8. 구조화 JSON 로깅

**문제**: 현재 `src/utils/logger.py`가 평문 텍스트만 출력. OpenSearch는 JSON 포맷을 기대한다.

**수정 파일**: `src/utils/logger.py`

**제약**: 기존 `get_agent_logger()` 시그니처 변경 불가 (공용 인프라).

**방법**: `_create_formatter()` 내부에서 `APP_ENV`를 확인하여 `JsonFormatter` 또는 기존 `Formatter`를 반환.

**추가 의존성**: `python-json-logger` (requirements.txt에 추가)

```python
"""
구조화 로거 — 에이전트 실행 추적을 위한 로깅 유틸리티.

모든 에이전트는 이 로거를 사용하여 일관된 형식으로 로그를 남긴다.
에이전트명, TIER, session_id 등의 컨텍스트 정보를 자동으로 포함한다.

APP_ENV=production 시 JSON 포맷 출력 (OpenSearch 수집용).
"""

from __future__ import annotations

import logging
import os
import sys


def _is_production() -> bool:
    """프로덕션 환경 여부를 반환한다."""
    return os.getenv("APP_ENV", "development") == "production"


def _create_formatter() -> logging.Formatter:
    """로그 포맷터를 생성한다. 프로덕션에서는 JSON, 개발에서는 읽기 쉬운 형식."""
    if _is_production():
        try:
            from pythonjsonlogger import jsonlogger

            return jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        except ImportError:
            pass  # python-json-logger 미설치 시 기본 포맷 사용

    fmt = "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    return logging.Formatter(fmt, datefmt=datefmt)


def _get_log_level() -> int:
    """환경변수에서 로그 레벨을 결정한다."""
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    에이전트 전용 로거를 생성한다.

    각 에이전트는 고유한 이름의 로거를 사용하여 로그를 구분할 수 있다.

    Args:
        agent_name: 에이전트 이름 (예: content_analyzer, podcast_reasoning)

    Returns:
        설정된 Logger 인스턴스

    사용 예시:
        logger = get_agent_logger("content_analyzer")
        logger.info("콘텐츠 분석 시작", extra={"session_id": "sess_abc123"})
    """
    logger_name = f"mind-log.agent.{agent_name}"
    logger = logging.getLogger(logger_name)

    # 이미 핸들러가 설정된 경우 중복 방지
    if not logger.handlers:
        logger.setLevel(_get_log_level())
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_create_formatter())
        logger.addHandler(handler)
        logger.propagate = False  # 루트 로거로 전파 방지

    return logger
```

**환경 분리**: `APP_ENV=production`이면 JSON, 아니면 기존 평문. `get_agent_logger()` 시그니처 불변.

**requirements.txt에 추가**:
```
python-json-logger>=2.0.0
```

**담당**: 개발자2 / **복잡도**: S

---

### 3-9. Prometheus 메트릭 엔드포인트

**문제**: Grafana(app-1:3001)가 Prometheus 메트릭을 스크래핑하여 대시보드를 구성한다.

**생성 파일**: `src/monitoring/prometheus.py`

**추가 의존성**: `prometheus-client` (requirements.txt에 추가)

**참조**: `src/monitoring/callbacks.py` — `MindLogTelemetryCallback`, `_NODE_TIER_MAP`

```python
"""Prometheus 메트릭 수집 및 /metrics 엔드포인트."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest
from fastapi import APIRouter, Response

router = APIRouter(tags=["monitoring"])

# --- 메트릭 정의 ---
REQUEST_COUNT = Counter(
    "mindlog_requests_total",
    "총 API 요청 수",
    ["method", "endpoint", "status"],
)
PIPELINE_DURATION = Histogram(
    "mindlog_pipeline_duration_seconds",
    "파이프라인 전체 실행 시간",
    ["mode"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)
AGENT_DURATION = Histogram(
    "mindlog_agent_duration_seconds",
    "에이전트별 실행 시간",
    ["agent_name", "tier"],
    buckets=[0.1, 0.5, 1, 2, 5, 10],
)
LLM_TOKENS = Counter(
    "mindlog_llm_tokens_total",
    "LLM 토큰 사용량",
    ["agent_name", "direction"],  # direction: input / output
)
CRISIS_EVENTS = Counter(
    "mindlog_crisis_events_total",
    "위기 감지 이벤트 수",
)


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus 메트릭을 반환한다."""
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
```

**main.py에 라우터 등록 추가**:
```python
from src.monitoring.prometheus import router as metrics_router
app.include_router(metrics_router)
```

**requirements.txt에 추가**:
```
prometheus-client>=0.20.0
```

**복잡도**: M

---

### 3-10. S3 Read 클라이언트

**문제**: boto3 의존성은 있으나(Bedrock용으로만 사용 중) S3 읽기 코드가 없다.

**생성 파일**: `src/db/__init__.py`, `src/db/s3_client.py`

```python
# src/db/__init__.py
"""데이터베이스 및 스토리지 클라이언트 패키지."""
```

```python
# src/db/s3_client.py
"""S3 읽기 전용 클라이언트 — 로그/미디어 백업 조회."""

from __future__ import annotations

import logging
from typing import Any

import boto3

from config.loader import get_settings

logger = logging.getLogger("mind-log.db.s3")


class S3ReadClient:
    """S3 읽기 전용 클라이언트. AI팀은 s3:Get*, s3:List* 권한만 보유."""

    def __init__(self, bucket: str | None = None) -> None:
        settings = get_settings()
        self._bucket = bucket or "<S3_LOGS_BUCKET>"
        self._client = boto3.client("s3", region_name=settings.bedrock_region)

    def get_object(self, key: str) -> bytes:
        """S3 오브젝트를 읽는다."""
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def list_objects(
        self, prefix: str = "", max_keys: int = 100
    ) -> list[dict[str, Any]]:
        """S3 오브젝트 목록을 조회한다."""
        response = self._client.list_objects_v2(
            Bucket=self._bucket, Prefix=prefix, MaxKeys=max_keys
        )
        return response.get("Contents", [])

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """미리 서명된 URL을 생성한다 (읽기 전용)."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
```

**S3 쓰기(이미지 업로드)**:
- AI팀은 S3 쓰기 권한 없음
- Visualization Agent가 생성한 이미지는 `BackendClient`를 통해 Backend(app-3)에 전달
- Backend가 S3에 업로드하는 구조 (Backend 팀의 S3 쓰기 권한 확인 필요)

**담당**: 개발자2 / **복잡도**: S

---

### 3-11. 환경 분리 전략

**문제**: 현재 `config/settings.yaml` 단일 설정. dev/prod 분리가 없다.

**참조**: `config/loader.py` — `Settings` 클래스, `get_settings()` 싱글톤

**제약**: `get_settings()` 시그니처 불변

#### 생성 파일: `config/settings.production.yaml`

```yaml
# 프로덕션 오버레이 — settings.yaml의 값을 덮어쓴다.
# APP_ENV=production일 때 자동 로드.

llm:
  provider: bedrock

api:
  timeout: 30
  max_retries: 3

pipeline:
  max_retries: 2
  tier1_timeout_seconds: 30
```

#### 수정 파일: `config/loader.py`

`Settings.__init__` 내부에 오버레이 로딩 추가 (기존 시그니처 불변):

```python
def __init__(self, config_path: Path | None = None) -> None:
    """설정 파일을 로드한다."""
    path = config_path or _SETTINGS_PATH
    with open(path, encoding="utf-8") as f:
        self._config: dict[str, Any] = yaml.safe_load(f)

    # 프로덕션 오버레이 로드 (APP_ENV=production일 때)
    app_env = os.getenv("APP_ENV", "development")
    overlay_path = _CONFIG_DIR / f"settings.{app_env}.yaml"
    if overlay_path.exists() and overlay_path != path:
        with open(overlay_path, encoding="utf-8") as f:
            overlay = yaml.safe_load(f) or {}
        self._deep_merge(self._config, overlay)
```

신규 private 메서드 추가:

```python
@staticmethod
def _deep_merge(base: dict, overlay: dict) -> None:
    """overlay의 값을 base에 재귀적으로 병합한다."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            Settings._deep_merge(base[key], value)
        else:
            base[key] = value
```

**복잡도**: S

---

### 3-12. CI에 Docker 빌드 검증 추가

**문제**: 현재 CI는 테스트+린트만 실행. Docker 이미지가 정상 빌드되는지 검증이 없다.

**수정 파일**: `.github/workflows/ci.yml`

추가할 스텝:

```yaml
  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Docker 빌드 검증
        run: docker build -t mindlog-ai:test .
```

**복잡도**: S

---

## 4. 타팀 협의 필수 사항

### 4-1. Bedrock IAM 권한 [차단 위험]

인프라 가이드의 IAM 권한에 Bedrock이 명시되어 있지 않다 (SSM + EC2 Read + S3 Read만 기재).
`settings.yaml`에 `bedrock_region: ap-northeast-2`가 설정되어 있고 `llm_client.py`에 Bedrock 통합이 완료되어 있으나, IAM에 `bedrock:InvokeModel` 권한이 없으면 LLM 호출이 불가하다.

**대응**: 2번 체크리스트에서 Bedrock 권한을 확인한다. 권한이 없으면 인프라팀에 app-2 IAM 역할에 Bedrock 권한 추가를 요청한다.

### 4-2. Backend API 연동

`BackendClient`(`src/api/client.py`)가 app-3의 REST API를 호출한다.

Backend 팀에 확인:
- app-3에 `/api/v1/{resource}` 엔드포인트가 배포되어 있는지
- `contracts.py`의 `SaveRequest`/`SaveResponse` 스키마와 호환되는지
- app-2 → app-3:8080 내부 네트워크 통신 가능 여부

### 4-3. DB 접근 방식

`BackendClient`는 Backend 서버 경유 저장을 전제로 설계됨.
`external_schemas.py`에 직접 DB 접근 스키마도 정의되어 있다.

**결정 필요**: AI 서버의 DB 접근 범위. 이 결정에 따라 MySQL/Pinecone/Neo4j 클라이언트 구현 범위가 결정됨.

### 4-4. S3 이미지 업로드

AI팀은 S3 읽기 전용. Visualization Agent가 생성한 이미지 저장 경로:
- Backend 팀에 S3 쓰기 권한이 있는지 확인
- 있으면: AI → `BackendClient`로 이미지 바이트 전송 → Backend가 S3 업로드
- 없으면: 인프라팀에 별도 경로 요청

### 4-5. ALB 헬스체크 경로

AI팀이 `/health` 엔드포인트를 구현하면, 인프라팀이 ALB 타겟 그룹의 헬스체크 경로를 `/health`로 설정해야 한다.

### 4-6. Prometheus 스크래핑

AI팀이 `/metrics` 엔드포인트를 구현하면, 인프라팀이 app-1의 `prometheus.yml`에 `app-2:8000/metrics`를 추가해야 한다.

### 4-7. 로그 수집 파이프라인

AI팀이 JSON 로그를 출력해도, app-2에서 app-1의 OpenSearch로 전송할 에이전트(Filebeat/FluentBit)가 필요하다.
인프라 가이드에 로그 전송 방법이 명시되어 있지 않다.

### 4-8. CI/CD 자동 배포 (향후)

인프라 가이드에 CI/CD는 향후 로드맵으로 명시. 현재는 수동 배포.
자동 배포 구축 시: ECR 레포지토리 생성, SSM 배포 명령 권한 부여 필요.

---

## 5. 타팀 이관 체크리스트

배포 준비 완료 후 타팀에 요청할 항목.

### 인프라팀

- [ ] app-2 IAM에 Bedrock `InvokeModel` 권한 추가 (4-1)
- [ ] ALB 타겟 그룹 헬스체크 경로 `/health` 설정 (4-5)
- [ ] Prometheus에 `app-2:8000/metrics` 스크래핑 대상 추가 (4-6)
- [ ] app-2에 로그 수집 에이전트 설치 (4-7)
- [ ] S3 `vis/` 프리픽스 쓰기 권한 (4-4 결과에 따라)

### Backend팀

- [ ] `src/api/external_schemas.py` 기반 요청/응답 스키마 공유
- [ ] `contracts.py`의 `SaveRequest`/`SaveResponse` 준수하는 저장 엔드포인트 구현
- [ ] `BackendClient` 연동 테스트 (AI → app-3:8080/api/v1)
- [ ] MySQL 테이블 생성 (`external_schemas.py` 기반)
- [ ] S3 이미지 업로드 API (4-4에서 Backend 경유 시)

---

## 6. 로컬 환경 vs 프로덕션 환경

| 항목 | 로컬 (현재) | 프로덕션 (app-2) |
|------|-----------|-----------------|
| LLM | Ollama 또는 OpenAI gpt-4o-mini | AWS Bedrock (IAM 역할 인증) |
| DB | localhost 또는 mock | Backend API 경유 |
| 실행 | `python -m src.api.main` | `docker compose up -d` |
| 로그 | 평문 텍스트 | JSON (OpenSearch 수집) |
| 프롬프트 | 로컬 `prompts/` 디렉토리 | Docker 볼륨 마운트 |
| 모니터링 | 없음 | `/metrics` → Prometheus → Grafana |
| 접근 | 직접 | SSM 전용 |
| `.env` | `LLM_PROVIDER=ollama` | `LLM_PROVIDER=bedrock` |

### 코드 분리 원칙

모든 환경 차이는 환경변수(`.env`)와 설정 오버레이(`settings.{env}.yaml`)로 제어한다. 코드 자체는 동일하다.

**환경변수 기반 분기**:

| 환경변수 | 역할 | 참조 코드 |
|---------|------|----------|
| `APP_ENV` | 로그 포맷, uvicorn reload, 설정 오버레이 | `src/utils/logger.py`, `src/api/main.py`, `config/loader.py` |
| `LLM_PROVIDER` | LLM 프로바이더 선택 | `config/loader.py:61` |
| `BACKEND_API_URL` | Backend API 주소 | `config/loader.py:199` |
| `ALLOWED_ORIGINS` | CORS 허용 origin | `src/api/main.py` |
| `PROMPT_DIR` | 프롬프트 디렉토리 | `src/agents/shared/prompt_loader.py:424` |

---

## 7. 개발자별 작업 배분

### 개발자1 (feature/analysis 브랜치)

**Week 1**:
- 3-1 `main.py` 엔트리포인트
- 3-2 health check
- 3-3 라우트 핸들러 (sessions, podcasts)
- 3-5 `docker-compose.yml` + 3-6 `.dockerignore`

**Week 2**:
- 3-7 `.env.example` 프로덕션 변수
- 로컬 Docker 빌드/실행 검증

### 개발자2 (feature/reasoning 브랜치)

**Week 1**:
- 3-8 JSON 로깅
- 3-10 S3 Read 클라이언트
- 3-11 환경 분리

**Week 2**:
- 3-9 Prometheus 메트릭
- 타팀 이관 사항 정리 및 전달

### 개발자3 (feature/validation 브랜치)

**Week 1**:
- 3-4 프롬프트 배포 전략 적용
- 기존 테스트 Docker 환경 호환성 점검

**Week 2**:
- 3-12 CI Docker 빌드 스텝
- 통합 테스트 Docker 환경 실행

### 공동

- 2번 접근 확인 체크리스트 (Week 1 초반, 전원)
- 4번 타팀 협의 (Week 1, 필요한 항목부터)
- app-2 초기 배포 및 ALB 연결 검증 (Week 2 후반)

---

## 8. 검증 방법

### 로컬 검증

1. **Docker 빌드**: `docker compose up -d` → `curl localhost:8000/health` → 200 OK
2. **팟캐스트**: `POST /api/v1/podcasts/episodes` 테스트 요청 → 에피소드 응답 수신
3. **메트릭**: `curl localhost:8000/metrics` → Prometheus 포맷 출력
4. **JSON 로그**: `APP_ENV=production python -m src.api.main` → JSON 로그 출력 확인
5. **테스트**: `pytest tests/ -v` + `ruff check` + `mypy` 통과

### 프로덕션 검증 (app-2)

1. SSM 접속 → `/home/ubuntu/app/`에서 `docker compose up -d`
2. ALB 헬스체크 통과 확인 (EC2 > Target Groups > Healthy)
3. Backend(app-3)에서 AI 서버 호출 성공 확인
4. Grafana(app-1:3001)에서 메트릭 수집 확인
5. OpenSearch(app-1:5601)에서 JSON 로그 수집 확인

---

*작성일: 2026-03-09*

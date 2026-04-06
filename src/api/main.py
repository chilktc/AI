"""
FastAPI 앱 엔트리포인트.

API 서버의 뼈대로서 CORS, 예외 핸들링, 라우터 등록 및 Lifespan(앱 수명주기)
관리를 담당한다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from config.loader import get_settings
from src.api.client import BackendClient
from src.api.external_schemas import ErrorDetail, ErrorResponse, RequestTracing
from src.api.middleware import RequestLoggingMiddleware
from src.api.routes import graph, health, podcasts, sessions
from src.graph.workflow import compile_graph
from src.monitoring.prometheus import get_metrics_router
from src.utils.logger import get_agent_logger

logger = get_agent_logger("api_server")


# 전역 클라이언트 인스턴스 (필요 시 의존성 주입 등에 활용)
backend_client: BackendClient | None = None
compiled_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    애플리케이션 수명주기 이벤트.
    앱 시작 시 초기화하고 종료 시 리소스를 반환한다.
    """
    global backend_client, compiled_graph

    settings = get_settings()
    storage_mode = getattr(settings, "storage_mode", "local")

    logger.info(
        "앱 시작: STORAGE_MODE=%s",
        storage_mode,
        extra={"storage_mode": storage_mode},
    )

    # 1. LangGraph 컴파일 (최초 1회 컴파일 캐싱 효과)
    # MemorySaver 등 체포인터 설정은 환경에 맞게 추가할 수 있음
    compiled_graph = compile_graph("unified")
    logger.info("LangGraph 컴파일 완료 (unified)")

    # 2. Backend API 클라이언트 초기화
    backend_client = BackendClient()
    logger.info(
        "BackendClient 초기화 완료 (base_url=%s)",
        backend_client._base_url,
    )

    # 프로덕션 환경 안전 검증
    import os as _os

    app_env = _os.getenv("APP_ENV", "development")

    # 3a. CORS 와일드카드 경고
    if "*" in settings.allowed_origins and app_env == "production":
        logger.warning(
            "프로덕션에서 CORS 와일드카드('*') 감지. ALLOWED_ORIGINS 환경변수를 설정하세요."
        )

    # 3b. 필수 자격증명 검증
    llm_provider = _os.getenv("LLM_PROVIDER", "anthropic")
    required_vars: dict[str, list[str]] = {
        "anthropic": ["ANTHROPIC_API_KEY"],
        "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
        "openai": ["OPENAI_API_KEY"],
    }
    missing = [v for v in required_vars.get(llm_provider, []) if not _os.getenv(v)]
    if missing and app_env == "production":
        raise RuntimeError(f"프로덕션 필수 환경변수 누락: {missing}")
    elif missing:
        logger.warning("환경변수 미설정 (비프로덕션): %s", missing)

    # 3c. prompts 디렉토리 존재 확인
    from pathlib import Path as _Path

    prompts_dir = _Path(_os.getenv("PROMPT_DIR", "prompts"))
    if not prompts_dir.exists() or not any(prompts_dir.iterdir()):
        logger.warning(
            "prompts 디렉토리가 비어있거나 존재하지 않음: %s. "
            "docker-compose로 볼륨 마운트가 필요합니다.",
            prompts_dir,
        )

    yield

    # 앱 종료 시 리소스 정리
    logger.info("앱 종료 시작: 리소스 정리")
    if backend_client:
        await backend_client.close()
    logger.info("앱 종료 완료")


# FastAPI 앱 생성
app = FastAPI(
    title="Mind-Log AI Server",
    description="Mind-Log 멘탈케어 플랫폼 AI 파이프라인 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 설정
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP 요청/응답 구조화 로깅 미들웨어 (C-1)
app.add_middleware(RequestLoggingMiddleware)

# ---------------------------------------------------------------------------
# 전역 예외 처리기
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """표준 HTTP 에러를 ErrorResponse 스키마에 맞게 래핑"""
    tracing = RequestTracing()  # 가상의 기본값. 실제로는 dependency로 주입받을 수 있음.

    error_code = "NOT_FOUND" if exc.status_code == 404 else "SERVER_ERROR"
    if exc.status_code == 429:
        error_code = "RATE_LIMITED"

    error_detail = ErrorDetail(
        code=error_code,
        message=str(exc.detail),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=error_detail, tracing=tracing).model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """요청 검증 실패 에러를 ErrorResponse 스키마에 맞게 래핑"""
    tracing = RequestTracing()

    # 첫 번째 에러의 필드명 추출
    first_error = exc.errors()[0]
    loc = first_error.get("loc", [])
    field_name = str(loc[-1]) if loc else "unknown"

    error_detail = ErrorDetail(
        code="VALIDATION_ERROR",
        message="요청 데이터 검증에 실패했습니다.",
        field=field_name,
    )

    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error=error_detail, tracing=tracing).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 모든 서버 에러 핸들러"""
    tracing = RequestTracing()

    error_detail = ErrorDetail(
        code="SERVER_ERROR",
        message="서버 내부 오류가 발생했습니다.",
    )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error=error_detail, tracing=tracing).model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# 라우터 등록
# ---------------------------------------------------------------------------
app.include_router(health.router, tags=["Health Check"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["Sessions"])
app.include_router(podcasts.router, prefix="/api/v1/podcasts", tags=["Podcasts"])
# [이관 주석] Neo4j 이관 시 아래 graph 라우터 등록을 삭제.
app.include_router(graph.router)

# Prometheus 메트릭 엔드포인트 (C-2: prometheus.py 인수 사항)
app.include_router(get_metrics_router())

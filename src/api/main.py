"""
FastAPI 앱 엔트리포인트.

API 서버의 뼈대로서 CORS, 예외 핸들링, 라우터 등록 및 Lifespan(앱 수명주기)
관리를 담당한다. 
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config.loader import get_settings
from src.api.client import BackendClient
from src.api.external_schemas import ErrorDetail, ErrorResponse, RequestTracing
from src.api.routes import health, sessions, podcasts
from src.graph.workflow import compile_graph


# 전역 클라이언트 인스턴스 (필요 시 의존성 주입 등에 활용)
backend_client: BackendClient | None = None
compiled_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    애플리케이션 수명주기 이벤트.
    앱 시작 시 초기화하고 종료 시 리소스를 반환한다.
    """
    global backend_client, compiled_graph
    
    settings = get_settings()

    # 1. LangGraph 컴파일 (최초 1회 컴파일 캐싱 효과)
    # MemorySaver 등 체포인터 설정은 환경에 맞게 추가할 수 있음
    compiled_graph = compile_graph("unified")

    # 2. Backend API 클라이언트 초기화
    backend_client = BackendClient()

    yield

    # 앱 종료 시 리소스 정리
    if backend_client:
        await backend_client.close()

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

# ---------------------------------------------------------------------------
# 전역 예외 처리기
# ---------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """표준 HTTP 에러를 ErrorResponse 스키마에 맞게 래핑"""
    tracing = RequestTracing() # 가상의 기본값. 실제로는 dependency로 주입받을 수 있음.
    
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
async def validation_exception_handler(request: Request, exc: RequestValidationError):
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
async def general_exception_handler(request: Request, exc: Exception):
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

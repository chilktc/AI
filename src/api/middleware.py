"""
HTTP 요청/응답 구조화 로깅 미들웨어.

Zone C-1 JSON 구조화 로깅을 활용하여 모든 HTTP 요청의
시작/완료를 기록한다.

- X-Request-ID 헤더 자동 생성 또는 클라이언트 전달 값 재사용
- ALB/Prometheus 빈번 호출 경로 제외: /health, /health/ready, /metrics
- APP_ENV=production 시 src/utils/logger.py의 JSON 포맷터 자동 적용
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.utils.logger import get_agent_logger

logger = get_agent_logger("http")

# ALB/Prometheus가 빈번하게 호출하는 경로 — 로깅 제외
_EXCLUDED_PATHS: frozenset[str] = frozenset({"/health", "/health/ready", "/metrics"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """HTTP 요청/응답 로깅 미들웨어.

    모든 요청에 대해:
    1. X-Request-ID 헤더가 없으면 UUID를 생성하여 부여
    2. 요청 시작/완료를 구조화 로그로 기록
    3. 응답 헤더에 X-Request-ID를 포함하여 추적 가능하게 함
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청을 가로채어 로깅 후 다음 핸들러로 전달한다."""
        # 1. Request ID 결정 (클라이언트 제공 or 서버 생성)
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:12]

        # 2. 제외 경로 확인
        path = request.url.path
        if path in _EXCLUDED_PATHS:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # 3. 요청 시작 로깅
        method = request.method
        logger.info(
            "요청 시작: %s %s",
            method,
            path,
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        # 4. 다음 핸들러 호출 + 소요 시간 측정
        start_time = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "요청 실패: %s %s (%dms)",
                method,
                path,
                elapsed_ms,
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "elapsed_ms": elapsed_ms,
                    "status_code": 500,
                },
            )
            raise

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # 5. 요청 완료 로깅
        log_level = "warning" if response.status_code >= 400 else "info"
        getattr(logger, log_level)(
            "요청 완료: %s %s → %d (%dms)",
            method,
            path,
            response.status_code,
            elapsed_ms,
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )

        # 6. 응답에 Request ID 헤더 추가
        response.headers["X-Request-ID"] = request_id
        return response

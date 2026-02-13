"""
재시도 유틸리티 — Exponential backoff 데코레이터.

API 호출이나 LLM 호출 실패 시 자동 재시도를 제공한다.
기본 5초, LLM 관련 30초 타임아웃을 지원한다.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger("mind-log.utils.retry")

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Exponential backoff 재시도 데코레이터.

    지정된 예외 발생 시 자동으로 재시도한다.
    대기 시간은 base_delay * (2 ** attempt)로 증가하며 max_delay를 넘지 않는다.

    Args:
        max_retries: 최대 재시도 횟수
        base_delay: 첫 번째 재시도까지 대기 시간 (초)
        max_delay: 최대 대기 시간 (초)
        exceptions: 재시도할 예외 타입 튜플

    사용 예시:
        @with_retry(max_retries=3, base_delay=1.0)
        async def call_api():
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # 마지막 시도였으면 예외를 그대로 발생
                    if attempt >= max_retries:
                        break

                    # 대기 시간 계산 (exponential backoff)
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.warning(
                        "%s 재시도 %d/%d (%.1f초 후) — %s: %s",
                        func.__name__,
                        attempt + 1,
                        max_retries,
                        delay,
                        type(e).__name__,
                        str(e),
                    )
                    await asyncio.sleep(delay)

            # 모든 재시도 실패
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator

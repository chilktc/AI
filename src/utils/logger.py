"""
구조화 로거 — 에이전트 실행 추적을 위한 로깅 유틸리티.

모든 에이전트는 이 로거를 사용하여 일관된 형식으로 로그를 남긴다.
에이전트명, TIER, session_id 등의 컨텍스트 정보를 자동으로 포함한다.
"""

from __future__ import annotations

import logging
import os
import sys


def _get_log_level() -> int:
    """환경변수에서 로그 레벨을 결정한다."""
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


def _create_formatter() -> logging.Formatter:
    """로그 포맷터를 생성한다. 개발 환경에서는 읽기 쉬운 형식을 사용."""
    fmt = "[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    return logging.Formatter(fmt, datefmt=datefmt)


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

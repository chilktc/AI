"""
구조화 로거 — 에이전트 실행 추적을 위한 로깅 유틸리티.

[Shared Infrastructure — 인터페이스 변경 금지]
get_agent_logger()의 시그니처와 동작을 변경하지 마시오.
신규 함수 추가만 허용. 수정 시 전체 테스트(pytest tests/ -v) 통과 필수.

모든 에이전트는 이 로거를 사용하여 일관된 형식으로 로그를 남긴다.
에이전트명, TIER, session_id 등의 컨텍스트 정보를 자동으로 포함한다.

APP_ENV에 따른 로그 포맷:
  - production: JSON 구조화 로그 (OpenSearch 수집용)
  - 그 외: 사람이 읽기 쉬운 평문 텍스트
"""

from __future__ import annotations

import logging
import os
import sys


def _get_log_level() -> int:
    """환경변수에서 로그 레벨을 결정한다."""
    level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_str, logging.INFO)


def _is_production() -> bool:
    """프로덕션 환경 여부를 판별한다."""
    return os.getenv("APP_ENV", "").lower() == "production"


def _create_json_formatter() -> logging.Formatter:
    """프로덕션용 JSON 포맷터를 생성한다.

    OpenSearch 수집에 적합한 구조화 JSON 포맷.
    extra 필드(session_id, tier 등)가 자동으로 JSON에 포함된다.
    """
    from pythonjsonlogger.json import JsonFormatter

    return JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _create_formatter() -> logging.Formatter:
    """로그 포맷터를 생성한다. APP_ENV에 따라 JSON/평문을 선택."""
    if _is_production():
        return _create_json_formatter()
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

"""
API 라우터 초기화 스크립트.

하위 모듈(health, sessions, podcasts)을 로드하여 APIRouter 조립 시 사용한다.
"""

from src.api.routes import health as health
from src.api.routes import podcasts as podcasts
from src.api.routes import sessions as sessions

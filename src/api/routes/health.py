"""
Health Check API 라우터.

AWS ALB 및 쿠버네티스 Liveness/Readiness Probe용 엔드포인트.
"""

from fastapi import APIRouter
from pydantic import BaseModel

# backend_client 및 compiled_graph는 main.py 초기화 전에는 가져오면 순환참조가 생길 수 있습니다.
# 라우터 함수 내에서 runtime 시에 가져오도록 수정하겠습니다.

router = APIRouter()


class HealthResponse(BaseModel):
    """기본 Health 응답"""
    status: str = "ok"

class ReadyResponse(BaseModel):
    """Ready(준비됨) 응답"""
    status: str = "ready"
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    ALB 헬스체크용 엔드포인트.
    애플리케이션이 실행 중인지(200 OK)만 확인한다.
    """
    return HealthResponse()


@router.get("/health/ready", response_model=ReadyResponse)
async def ready_check():
    """
    심층 상태 점검 (Readiness Probe).
    
    LangGraph가 컴파일되었고, 백엔드 클라이언트가 초기화되었는지 검사한다.
    트래픽을 받을 준비가 되었는지 여부를 반환.
    """
    from src.api.main import backend_client, compiled_graph
    
    components_status = {
        "graph": "ok" if compiled_graph is not None else "not_ready",
        "backend_client": "ok" if backend_client is not None else "not_ready",
    }
    
    # 하나라도 not_ready면 전체 상태가 "not_ready"일 수 있지만 
    # 현재 정책상 컴포넌트들 상태를 포함하여 200 반환 후 상태 라벨만 표시
    status = "ready" if all(v == "ok" for v in components_status.values()) else "not_ready"
    
    # 만약 완전히 트래픽 처리가 불가능한 상태라면 503 에러를 반환하게 구현할 수도 있음.
    # 여기서는 상태값 반환으로 처리.
    
    return ReadyResponse(status=status, components=components_status)

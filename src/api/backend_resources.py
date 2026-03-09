"""
Backend API 리소스 매핑.

BackendClient.save/load의 resource 파라미터로 사용할 경로 상수.
Backend팀과의 협의 사항을 한 곳에 집중하여 관리한다.

TODO(backend): 4-2 각 리소스 경로와 스키마를 Backend팀과 최종 확정 필요.
검색: grep -rn "TODO(backend)" src/
"""

# --- 확정된 리소스 (이미 사용 중) ---
RESOURCE_LEARNING = "learning"  # LearningAgent에서 사용 중

# --- 협의 필요 리소스 ---
RESOURCE_CONVERSATION = "conversations"  # TODO(backend): 4-2 경로명 확정
RESOURCE_EMOTION_LOG = "emotion_logs"  # TODO(backend): 4-2 경로명 확정
RESOURCE_MEMORY = "memories"  # TODO(backend): 4-2 경로명 확정
RESOURCE_VISUALIZATION = "visualizations"  # TODO(backend): 4-2 이미지 바이트 전송 방식 확정
RESOURCE_SESSION = "sessions"  # TODO(backend): 4-2 경로명 확정

# --- 프록시 전용 (STORAGE_MODE=proxy/hybrid 시) ---
RESOURCE_VECTOR_SEARCH = "vector/search"  # TODO(backend): 4-3 엔드포인트 존재 여부 확인
RESOURCE_GRAPH_QUERY = "graph/query"  # TODO(backend): 4-3 그래프 쿼리 엔드포인트 확인
RESOURCE_STORAGE_UPLOAD = "storage/upload"  # TODO(backend): 4-4 이미지 업로드 엔드포인트 확인
RESOURCE_STORAGE_OBJECT = "storage/object"  # TODO(backend): 4-4 S3 객체 조회 엔드포인트 확인

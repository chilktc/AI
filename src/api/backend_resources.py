"""
Backend API 리소스 매핑.

BackendClient.save/load의 resource 파라미터로 사용할 경로 상수.
Backend팀과의 협의 사항을 한 곳에 집중하여 관리한다.

경로 상수는 BackendClient.save(resource=...) / load(resource=...) 에서 사용.
타입 상수는 SaveRequest(type=...) 에서 사용.

Backend API 계약서: docs/architecture/API_SPEC.md (v2.0)
"""

# ===================================================================
# 리소스 경로 상수 — BackendClient.save/load(resource=...) 에서 사용
# ===================================================================

# --- 활성 리소스 (팟캐스트 파이프라인에서 사용 중) ---
RESOURCE_LEARNING = "learning"  # LearningAgent 학습 결과 저장
RESOURCE_PODCAST_EPISODE = "podcast_episodes"  # 에피소드 메타 + 세그먼트
RESOURCE_CONTENT_ANALYSIS = "content_analyses"  # ContentAnalyzer 분석 결과
RESOURCE_EMOTION_LOG = "emotion_logs"  # 감정 벡터 데이터 저장
RESOURCE_VISUALIZATION = "visualizations"  # 시각화(커버 이미지) 메타 저장
# [이관 주석] 아래 리소스는 Neo4j 위치와 무관하게 항상 필요.
# Backend가 프론트엔드에 그래프 데이터를 서빙하기 위해 사용.
RESOURCE_GRAPH_ANALYSIS = "graph_analyses"  # GoT 그래프 분석 결과 저장

# --- 협의 필요 리소스 ---
RESOURCE_SESSION = "sessions"  # TODO(backend): 경로명 확정

# --- 프록시 전용 (STORAGE_MODE=proxy/hybrid 시) ---
RESOURCE_VECTOR_SEARCH = "vector/search"  # TODO(backend): 엔드포인트 존재 여부 확인
RESOURCE_GRAPH_QUERY = "graph/query"  # TODO(backend): 그래프 쿼리 엔드포인트 확인
RESOURCE_STORAGE_UPLOAD = "storage/upload"  # TODO(backend): 이미지 업로드 엔드포인트 확인
RESOURCE_STORAGE_OBJECT = "storage/object"  # TODO(backend): S3 객체 조회 엔드포인트 확인

# ===================================================================
# Save 타입 상수 — SaveRequest(type=...) 에서 사용
# 리소스 경로(resource)와 타입(type)은 별개임에 주의.
# ===================================================================
TYPE_PODCAST_EPISODE = "podcast_episode"
TYPE_EMOTION_LOG = "emotion_log"
TYPE_VISUALIZATION = "visualization"
TYPE_LEARNING = "learning"
TYPE_CONTENT_ANALYSIS = "content_analysis"
TYPE_GRAPH_ANALYSIS = "graph_analysis"  # GoT 그래프 분석 결과

# --- 누적 그래프 리소스 ---
RESOURCE_GRAPH_EPISODES = "graph_nodes/episodes"
TYPE_GRAPH_EPISODE = "graph_episode"

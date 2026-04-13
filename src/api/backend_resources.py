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
RESOURCE_PODCAST_METADATA = "podcast_metadata"  # 에피소드 메타 + 스크립트 전체 저장
RESOURCE_PODCAST_EPISODES = "podcast_episodes"  # podcast_episodes 수집 API (session_id, image_url, text)
RESOURCE_CONTENT_ANALYSIS = "content_analyses"  # ContentAnalyzer 분석 결과
RESOURCE_EMOTION_LOG = "emotion_logs"  # 감정 벡터 데이터 저장
RESOURCE_VISUALIZATION = "visualizations"  # 시각화(커버 이미지) 메타 저장
# [제거됨 2026-04-09] _publish_graph_to_backend() 제거로 미사용.
# 프론트엔드는 /graph_nodes (누적 그래프)를 직접 읽으므로 graph_analyses 불필요.
# RESOURCE_GRAPH_ANALYSIS = "graph_analyses"

# --- 협의 필요 리소스 ---
RESOURCE_SESSION = "sessions"  # TODO(backend): 경로명 확정

# --- mind-frequencies 수집 ---
RESOURCE_MIND_FREQUENCIES = "mind-frequencies"  # POST /greenroom/ingest/ai/mind-frequencies
# [제거됨 2026-04-13] user_summaries → mind-frequencies로 통합
# RESOURCE_USER_SUMMARY = "user_summaries"

# --- 프록시 전용 (STORAGE_MODE=proxy/hybrid 시) ---
RESOURCE_VECTOR_SEARCH = "vector/search"  # TODO(backend): 엔드포인트 존재 여부 확인
RESOURCE_GRAPH_QUERY = "graph/query"  # TODO(backend): 그래프 쿼리 엔드포인트 확인
RESOURCE_STORAGE_UPLOAD = "storage/upload"  # TODO(backend): 이미지 업로드 엔드포인트 확인
RESOURCE_STORAGE_OBJECT = "storage/object"  # TODO(backend): S3 객체 조회 엔드포인트 확인

# ===================================================================
# Save 타입 상수 — SaveRequest(type=...) 에서 사용
# 리소스 경로(resource)와 타입(type)은 별개임에 주의.
# ===================================================================
TYPE_PODCAST_METADATA = "podcast_metadata"
TYPE_EMOTION_LOG = "emotion_log"
TYPE_VISUALIZATION = "visualization"
TYPE_LEARNING = "learning"
TYPE_CONTENT_ANALYSIS = "content_analysis"
# TYPE_GRAPH_ANALYSIS = "graph_analysis"  # [제거됨 2026-04-09]

# --- 누적 그래프 리소스 (Mode A) ---
RESOURCE_GRAPH_NODES = "graph_nodes"  # GET(조회)/PUT(갱신) 공통 엔드포인트
TYPE_GRAPH_CUMULATIVE = "graph_cumulative"  # PUT 전송 시 SaveRequest.type 필드

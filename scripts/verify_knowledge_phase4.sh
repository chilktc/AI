#!/usr/bin/env bash
# Plan #47 Phase 4 — Knowledge Agent 운영 검증 통합 스크립트
#
# 사용처: AWS SSM Session Manager 또는 EC2 SSH 접속 후 실행
# 실행 방법:
#   chmod +x scripts/verify_knowledge_phase4.sh
#   ./scripts/verify_knowledge_phase4.sh [실사용자_UUID]
#
# 필요 권한: sudo (docker exec / docker logs), docker 컨테이너 mindlog-ai-service 기동 중
#
# 결과 해석:
#   - Task 4-1 ~ 4-2: 배포 상태 / 설정 반영 확인 (Pinecone 데이터 무관)
#   - Task 4-3: Knowledge 실호출 — articles_count 값이 핵심 지표
#       · articles_count == 0 → 도메인 불일치(mental_health 미적재) 또는 임계값 과도 가능성
#       · articles_count >= 1 → 파이프라인 동작 확정
#   - Task 4-4: 운영 로그 이상 없는지 확인
#
# 주의: 본 스크립트는 호스트 상태를 변경하지 않음(읽기 전용).

set -u  # undefined var 경고만, 에러는 계속 진행

USER_UUID="${1:-00000000-0000-0000-0000-000000000000}"
CONTAINER="mindlog-ai-service"
SEP="================================================================"

echo
echo "${SEP}"
echo "Plan #47 Phase 4 — Knowledge Agent 운영 검증"
echo "시작 시각: $(date -Iseconds)"
echo "컨테이너: ${CONTAINER}"
echo "검증용 user_id: ${USER_UUID}"
echo "${SEP}"

# ============================================================
# Task 4-1: 컨테이너 상태
# ============================================================
echo
echo "### Task 4-1: 컨테이너 상태 ###"
sudo docker ps --filter "name=${CONTAINER}" --format "{{.Names}}	{{.Status}}	{{.Image}}"
echo
echo "--- 재시작 이력 ---"
sudo docker inspect "${CONTAINER}" --format '{{.RestartCount}} restarts, started_at={{.State.StartedAt}}' 2>/dev/null \
    || echo "ERROR: 컨테이너 inspect 실패"

# ============================================================
# Task 4-2: 설정 반영 + Stub 제거 + 실인스턴스 확인
# ============================================================
echo
echo "### Task 4-2: 설정 / Stub 제거 / 실인스턴스 확인 ###"
sudo docker exec "${CONTAINER}" python3 -c "
from config.loader import get_settings
s = get_settings()
cfg = s.get_agent_config('knowledge')
print(f'[CFG] pinecone_score_threshold = {cfg.get(\"pinecone_score_threshold\")}')
print(f'[CFG] pinecone_top_k = {cfg.get(\"pinecone_top_k\")}')
print(f'[CFG] full knowledge config keys = {list(cfg.keys())}')

# KnowledgeAgentStub 제거 검증
try:
    from src.agents.shared.stubs import KnowledgeAgentStub  # noqa: F401
    print('[STUB] FAIL — KnowledgeAgentStub import 성공 (제거 미반영)')
except ImportError:
    print('[STUB] OK — KnowledgeAgentStub import 실패 (정식 제거 반영)')

# 실인스턴스 확인
from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
from src.agents.podcast.knowledge import KnowledgeAgent
a = PodcastReasoningAgent()
print(f'[KA] knowledge_agent type = {type(a.knowledge_agent).__name__}')
print(f'[KA] is_real = {isinstance(a.knowledge_agent, KnowledgeAgent)}')
"

# ============================================================
# Task 4-3 Step 1: 환경변수 로딩
# ============================================================
echo
echo "### Task 4-3 Step 1: 환경변수 로딩 확인 ###"
sudo docker exec "${CONTAINER}" python3 -c "
import os
keys = [
    'KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT',
    'KT_CLOUD_KNOWLEDGE_PARSE_TOKEN',
    'KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_ENDPOINT',
    'KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_TOKEN',
    'KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT',
    'KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT',
    'KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN',
    'PINECONE_API_KEY',
    'PINECONE_INDEX_KNOWLEDGE',
]
for k in keys:
    v = os.environ.get(k, '')
    status = 'SET' if v else 'EMPTY'
    print(f'  {k}={status}')
"

# ============================================================
# Task 4-3 Step 2: Knowledge search() 실호출
# ============================================================
echo
echo "### Task 4-3 Step 2: KnowledgeAgent.search() 실호출 ###"
echo "  (articles_count 가 핵심 지표)"
sudo docker exec "${CONTAINER}" python3 -c "
import asyncio
from src.agents.podcast.knowledge import KnowledgeAgent

async def run():
    ka = KnowledgeAgent()
    r = await ka.search(query='스트레스 관리 방법', domain='mental_health')
    articles = r.get('articles', [])
    guidelines = r.get('guidelines', [])
    print(f'[SEARCH] articles_count = {len(articles)}')
    print(f'[SEARCH] guidelines_count = {len(guidelines)}')
    if articles:
        first = articles[0]
        print(f'[SEARCH] first_article_keys = {list(first.keys())[:8]}')
        print(f'[SEARCH] first_article_id = {first.get(\"id\")!r}')
        print(f'[SEARCH] first_article_title = {first.get(\"title\", \"\")[:60]!r}')
        print(f'[SEARCH] first_article_score = {first.get(\"score\")}')

asyncio.run(run())
"

# ============================================================
# Task 4-3 Step 3: Episode Memory 실호출
# ============================================================
echo
echo "### Task 4-3 Step 3: EpisodeMemoryAgent 실호출 ###"
echo "  user_id = ${USER_UUID}"
sudo docker exec "${CONTAINER}" python3 -c "
import asyncio
from src.agents.podcast.episode_memory import EpisodeMemoryAgent

async def run():
    em = EpisodeMemoryAgent()
    state = {'user_id': '${USER_UUID}', 'user_input': '요즘 자꾸 불안해'}
    r = await em.process(state)
    mr = r.get('memory_results', {})
    items = mr.get('items', [])
    summary = mr.get('summary', '')
    print(f'[MEM] items_count = {len(items)}')
    print(f'[MEM] summary_len = {len(summary)}')

asyncio.run(run())
" 2>&1 || echo "[MEM] 실행 실패 — 에러 상세 위 로그 확인"

# ============================================================
# Task 4-4 Step 1: Knowledge 관련 최근 로그
# ============================================================
echo
echo "### Task 4-4 Step 1: Knowledge/KT Cloud 로그 (tail 500, 상위 30행) ###"
sudo docker logs --tail 500 "${CONTAINER}" 2>&1 \
    | grep -E '"agent":\s*"knowledge"|KnowledgeAgent|kt.?cloud|pinecone' -i \
    | head -30 \
    || echo "(관련 로그 없음)"

# ============================================================
# Task 4-4 Step 2: 최근 10분 ERROR 로그
# ============================================================
echo
echo "### Task 4-4 Step 2: 최근 10분 ERROR/CRITICAL/Timeout ###"
sudo docker logs --since 10m "${CONTAINER}" 2>&1 \
    | grep -iE 'ERROR|CRITICAL|timeout|CancelledError' \
    | head -20 \
    || echo "(에러 없음 — 양호)"

# ============================================================
# Task 4-4 Step 3: Bedrock/KT Cloud 지연 로그
# ============================================================
echo
echo "### Task 4-4 Step 3: LLM 지연 로그 (duration_ms / latency) ###"
sudo docker logs --tail 300 "${CONTAINER}" 2>&1 \
    | grep -E 'duration_ms|latency' \
    | head -10 \
    || echo "(지연 로그 없음)"

echo
echo "${SEP}"
echo "완료 시각: $(date -Iseconds)"
echo "${SEP}"
echo
echo "※ 결과 해석 요약:"
echo "  1. [STUB] OK + [KA] is_real=True → PR #147 반영 확정"
echo "  2. [SEARCH] articles_count == 0 이면:"
echo "     (a) Pinecone 적재 실패 또는 도메인 불일치(personal_counsel 만 적재됨)"
echo "     (b) scripts/ingest_config.yaml에 domain=mental_health 추가 + 재적재 필요"
echo "     (c) 또는 pinecone_score_threshold 0.7 과도 가능성 — 0.5로 낮춰 재시도"
echo "  3. [SEARCH] articles_count >= 1 이면 → Plan #47 Phase 4 전체 완료"

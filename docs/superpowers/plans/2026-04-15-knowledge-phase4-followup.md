# Plan #47 Phase 4 후속 — articles_count=0 차단 원인 및 처리 계획

> 작성: 2026-04-15 18:30 / 작성자: 개발자1 / 브랜치: `feature/analysis-knowledge-threshold-tune`

## 1. 배경

- PR #147(KnowledgeAgentStub 제거) → PR #154(deploy.yml `KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_*` 누락 보완) 머지 후 운영 환경에서 Plan #47 Phase 4 검증 스크립트(`scripts/verify_knowledge_phase4.sh`)를 재실행했다.
- `[STUB] OK`, `[KA] is_real=True`, 환경변수 8종 SET, Pinecone vector_count=65 까지는 모두 정상이나 `[SEARCH] articles_count = 0` 으로 종결되었다.

## 2. 검증 결과 요약 (2026-04-15 18:06 UTC)

| 항목 | 결과 | 비고 |
|------|------|------|
| 컨테이너 환경변수 | ✅ PARSE/EMBEDDING_QUERY/EMBEDDING_PASSAGE/TEXTGEN/PINECONE_* 전부 SET | PR #154 반영 확정 |
| KnowledgeAgent 인스턴스 | ✅ `is_real=True` | Stub 제거 반영 |
| Pinecone 인덱스 | ✅ dim=4096, vector_count=65, namespace="" | 65/65 적재 성공 |
| 메타데이터 | ⚠️ `{"domain": "mental_health"}` 만 보관 (text/title 없음) | 설계대로(원문은 RDB에서 조회) |
| Embedding Query API | ✅ 4096-dim 벡터 정상 반환 | KT Cloud Query 모델 |
| 도메인 필터 (`$eq=mental_health`) | ✅ 10건 매치 | filter 동작 정상 |
| 실측 cosine score 분포 | ❌ 최댓값 0.3186, 상위5: 0.319/0.309/0.253/0.251/0.247 | threshold 0.7 미달 |
| Backend RDB ingest | ❌ 65/65 모두 `500 Internal Server Error` | 엔드포인트 미구현/장애 |

## 3. 차단 원인 (2개 동시 발생)

### 블로커 1 — Pinecone 임계값 과도 (즉시 조치 가능)

- 위치: [config/settings.yaml:89](../../../config/settings.yaml#L89)
- 현황: `pinecone_score_threshold: 0.7`
- 실측: KT Cloud `embedding-query` ↔ `embedding-passage` 페어의 정상 매치 점수가 0.20 ~ 0.35 대역에 형성됨. 0.7은 사실상 모든 결과를 컷하는 값.
- 처리: **0.7 → 0.25** 로 하향 (본 PR).

### 블로커 2 — Backend RDB `internal/knowledge` 미구현 (백엔드 협의 필요)

- 위치(클라이언트):
  - 호출: `KnowledgeAgent._fetch_documents_from_backend()` ([src/agents/podcast/knowledge.py:680](../../../src/agents/podcast/knowledge.py#L680))
  - 적재: `scripts/ingest_knowledge.py:save_to_backend()` ([scripts/ingest_knowledge.py:196](../../../scripts/ingest_knowledge.py#L196))
- 설계 의도:
  - Pinecone 메타데이터에는 `domain` 만 보관(검색용).
  - 원문 text/title/page/source는 Backend MySQL에서 chunk_id 로 조회.
- 운영 결과:
  - 적재 시점에 `POST http://10.7.10.20:8080/greenroom/ingest/ai/internal/knowledge` 가 65/65 전부 `500 Internal Server Error` 를 반환.
  - 결과적으로 Pinecone에 vector는 있어도 RDB에 원문이 없으므로 런타임 `articles` 배열은 항상 빈 채로 매핑된다.
- 백엔드 팀 요청 사항:
  - `POST /greenroom/ingest/ai/internal/knowledge` (적재) — body: `{id, title, content, page, source, domain}`
  - `GET /greenroom/ingest/ai/internal/knowledge?ids=id1,id2,...` (런타임 조회) — 응답: `[{id, title, content, page, source, domain}, ...]`

## 4. 단계별 후속 처리

### Step A — 본 PR (블로커 1)

- [x] `config/settings.yaml` `pinecone_score_threshold` 0.7 → 0.25
- [x] `tests/agents/podcast/test_knowledge.py` 회귀 테스트 통과 확인
- [ ] PR을 `develop` 으로 올린다 (base: develop, reviewers: 개발자2/개발자3)

### Step B — 백엔드 합의 후 별도 PR (블로커 2)

- [ ] Backend 팀에 `internal/knowledge` POST/GET 엔드포인트 사양 공유 + 구현 일정 협의
- [ ] 구현 완료 후 운영 환경에서 `scripts/ingest_knowledge.py` 재실행 (Pinecone 멱등 upsert 이므로 중복 적재 무해)
- [ ] `scripts/verify_knowledge_phase4.sh` 재실행 → `articles_count >= 1` 확인 시 Plan #47 Phase 4 종료

## 5. 검증 산출물 (참고)

```
# Pinecone STATS (컨테이너 내부에서 실행)
STATS: {'dimension': 4096, 'index_fullness': 0.0,
        'namespaces': {'': {'vector_count': 65}},
        'total_vector_count': 65}

# 실 쿼리 ("스트레스 관리 방법") with $eq=mental_health filter
REAL_MATCHES: 10
  score= 0.3186  id= kb_9422e332_p1_5c18ba3c11
  score= 0.3087  id= kb_9422e332_p1_76220512a8
  score= 0.2525  id= kb_9422e332_p1_d213a71979
  score= 0.2508  id= kb_9422e332_p1_6f2b9305ae
  score= 0.2474  id= kb_9422e332_p1_05632342bc
```

## 6. 참고 PR/Plan

- PR #145, #146, #147 (Knowledge RAG 1차/리팩터링/Stub 제거)
- PR #148, #149, #150 (Knowledge env 변수 PARSE_* 정렬)
- PR #154 (deploy.yml `EMBEDDING_PASSAGE` 누락 보완 — 본 차단 직전 머지)
- Plan: `2026-04-15-knowledge-rag-wiring-fix.md` (search 결과 → Reasoning/Generator 연결)
- Plan: `2026-04-15-knowledge-rag-pr148-regression-fix.md` (env 회귀)

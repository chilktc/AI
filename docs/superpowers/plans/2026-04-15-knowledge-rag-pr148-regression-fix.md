# Knowledge RAG PR #148 회귀 수정 + Pinecone 정합성 복구 계획서

**작성일**: 2026-04-15 15:22
**개정**: 2026-04-15 15:35 — 사용자 지침 반영
  - Pinecone 인덱스 미생성 시 **개발자3가 직접 생성** (이전에 수행 경험 있음, Episode Memory 인덱스와 동일 스펙)
  - D2 (MEMORY.md 업데이트) 제외
  - 모든 단계 **리뷰 진행 필수** (코드 수정 / PR / 시크릿 / 인덱스 생성 / 재검증 각 단계별)
**개정**: 2026-04-15 16:10 — SSM 재검증 후 방향 전환
  - PR #149 `PARSER_*`로 revert 적용 → 배포 후 컨테이너 env 확인 결과 **값이 빈 문자열**(0 chars)
  - GitHub Secrets 실제 등록 네이밍은 `KT_CLOUD_KNOWLEDGE_PARSE_*` (E 하나)로 확인됨
  - 사용자 결정: **시크릿 네이밍(PARSE_*)에 맞춰 코드/배포 정렬** (PR #148 방향이 운영과 정합)
  - 후속 PR(feature/validation-knowledge-parse-secret-align)에서 `knowledge.py`/`deploy.yml`/`.env.example` 모두 `PARSE_*`로 통일
**작성자**: 개발자3 (feature/validation-*)
**기반 근거**:
- `docs/superpowers/plans/2026-04-15-pr145-knowledge-rag-followup.md` (원저자 지침)
- `docs/superpowers/plans/2026-04-15-knowledge-agent-activation-and-verification.md` Task 4
- SSM 크롬 MCP 재검증 결과 (2026-04-15 15:16)

**작업 유형**: 계획 전용. 이 문서 작성까지. 실제 코드/시크릿/Pinecone 변경은 사용자 지시 후.

---

## 0. Executive Summary

### 0.1 결론 요약

| 항목 | 상태 | 조치 |
|------|------|------|
| 컨테이너 배포·환경변수 주입 | ✅ 정상 (PR #148 SHA `0d6ea04` 반영) | — |
| `KnowledgeAgent.search()` 코드 경로 | ✅ 정상 (Fallback 전부 동작) | — |
| Parser API 호출 | ❌ HTTP 400 | **본 계획 A**: env var 분리 원복 |
| Pinecone host 조회 | ❌ HTTP 404 | **본 계획 B**: 인덱스 정합성 확인 + 필요 시 재적재 |
| `articles_count >= 1` (Plan Task 4-3 성공 기준) | ❌ 0건 반환 | A + B 완료 후 재검증 |

### 0.2 근본 원인 (최단 설명)

**원인 1 — Parser env var 설계 파기**
PR #145 원저자(개발자1)는 **의도적으로** 런타임용 `PARSER`와 적재용 `PARSE`를 분리했다. `.env.example` 주석이 이를 명시하고, `2026-04-15-pr145-knowledge-rag-followup.md` §0.3에도 "PARSER vs PARSE는 한 글자 차이지만 용도가 다른 별개 API"라고 기록되어 있다. PR #148(본인 작성)에서 "정합성 맞춤"이라는 명목으로 `knowledge.py`의 `PARSER_ENDPOINT/_TOKEN`을 `PARSE_ENDPOINT/_TOKEN`으로 변경해, 런타임과 적재 스크립트가 **동일 env var로 서로 다른 API를 호출**하게 되었다. GitHub Secrets는 적재용 값(`/v1/document-parse` + docparse 토큰)을 담고 있어 런타임이 이 엔드포인트를 호출하면 400을 받는다.

**원인 2 — Pinecone 인덱스 정합성**
SSM 런타임 호출 시 `GET https://api.pinecone.io/indexes/rag-suite-knowledge`가 404를 반환한다. 가능성 세 가지:
- (2a) 해당 이름의 인덱스가 Pinecone에 아직 생성되지 않았다.
- (2b) GitHub Secret `PINECONE_INDEX_KNOWLEDGE`가 실제 생성된 인덱스명과 불일치한다 (코드 기본값은 `expert-knowledge`).
- (2c) Pinecone API Key가 해당 인덱스를 소유한 프로젝트 키가 아니다.

보조 증거: `scripts/ingest_config.yaml`의 유일한 적재 항목은 `domain=personal_counsel` 단 1건이므로, 설령 인덱스가 존재해도 `domain=mental_health` 필터로는 결과가 0이 되는 구조.

### 0.3 책임 영역

| 항목 | 수정 주체 | 영역 |
|------|----------|------|
| A1. `knowledge.py` env var 복구 | 개발자3 (본인) | 코드 (PR #148 회귀 수정) |
| A2. `deploy.yml` Secrets 주입 라인 복구 | 개발자3 | CI/CD |
| A3. GitHub Secrets 재등록 (`KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT/_TOKEN`) | **사용자/운영 담당** | GitHub Settings |
| B1. Pinecone 인덱스 존재·이름 확인 (SSM env 실값 + Pinecone API 조회) | 개발자3 | SSM |
| B1'. 인덱스 미생성 시 **직접 생성** (시크릿 값과 동일 이름, Episode Memory와 동일 스펙) | 개발자3 | SSM (Pinecone API) |
| B2. `scripts/ingest_knowledge.py` 적재 실행 (`mental_health` 도메인 추가 포함) | 개발자1 (원저자) 또는 운영 | 로컬/오프라인 |
| B3. 재검증 (Task 4-3 재실행) | 개발자3 | SSM |

---

## 1. Phase A — 코드 회귀 수정 (PR #148 원복)

### A1. `src/agents/podcast/knowledge.py` 수정

**현재 (PR #148 머지본, 2026-04-15 0d6ea04)**
```python
self.parser_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT", "")
self.parser_token = os.getenv("KT_CLOUD_KNOWLEDGE_PARSE_TOKEN", "")
```

**원복 (PR #145 원저자 설계 복원)**
```python
self.parser_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT", "")
self.parser_token = os.getenv("KT_CLOUD_KNOWLEDGE_PARSER_TOKEN", "")
```

- 파이썬 속성명(`parser_endpoint`, `parser_token`)은 그대로 유지 (이전 PR도 그대로였음).
- 영향 범위: `_parse_query()` 만 사용. 다른 호출 경로 없음.

### A2. `.env.example` 주석 정합성 복구

**현재** (L48-49, PR #148에서 수정됨)
```
# KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT=https://your-endpoint.proxy.aifoundry.ktcloud.com/v1/parser
# KT_CLOUD_KNOWLEDGE_PARSE_TOKEN=your_parse_token
```

**원복**
```
# KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT=https://your-endpoint.proxy.aifoundry.ktcloud.com/v1/parser
# KT_CLOUD_KNOWLEDGE_PARSER_TOKEN=your_parser_token
```

적재 스크립트용 L56-57은 `PARSE`(R 없음)로 이미 정확. 그대로 유지.

L45의 경고 주석(“PARSER vs PARSE”)이 이미 원저자 버전에 있었으므로 원복 후 자연스럽게 정합 상태로 돌아온다.

### A3. `.github/workflows/deploy.yml` 수정

**현재** (PR #148 추가분)
```
"printf '%s\\n' 'KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT=${{ secrets.KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT }}' >> .env",
"printf '%s\\n' 'KT_CLOUD_KNOWLEDGE_PARSE_TOKEN=${{ secrets.KT_CLOUD_KNOWLEDGE_PARSE_TOKEN }}' >> .env",
```

**원복안**
```
"printf '%s\\n' 'KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT=${{ secrets.KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT }}' >> .env",
"printf '%s\\n' 'KT_CLOUD_KNOWLEDGE_PARSER_TOKEN=${{ secrets.KT_CLOUD_KNOWLEDGE_PARSER_TOKEN }}' >> .env",
```

- `PARSE`(적재용) secret은 **deploy.yml에서 주입하지 않는다.** 적재는 오프라인에서 실행되므로 EC2 `.env`에 담길 이유가 없다.
- EMBEDDING_QUERY / TEXTGEN / PINECONE_INDEX_KNOWLEDGE 주입 라인은 그대로 유지 (PR #148에서 추가된 부분 중 이들은 정상).

### A4. 테스트 영향

- `tests/test_rag_synthesis.py`: 환경변수 이름 자체를 검증하지 않는다. `KnowledgeAgent.search()` 동작만 검증하므로 **변경 불필요**.
- 단, mock/patch에서 env var 이름을 하드코딩한 곳이 있는지 점검 필요:
  - `Grep pattern="KT_CLOUD_KNOWLEDGE_PARSE" path=tests/` — 결과 있으면 함께 복구.
- 신규 테스트 추가: 없음 (회귀 수정이므로).

---

## 2. Phase B — Pinecone 정합성 복구 (운영·원저자 영역)

### B1. 현재 상태 점검 (개발자3 — SSM)

**B1-1. 시크릿 실값 확인 (SSM 컨테이너 env)**
```bash
sudo docker exec mindlog-ai-service printenv PINECONE_INDEX_KNOWLEDGE
```
- AWS 환경에 주입된 실제 인덱스명 확인. 이 값이 **프로젝트 표준**. 시크릿을 바꾸지 않는다.

**B1-2. Pinecone 인덱스 존재 여부 조회**
```bash
sudo docker exec mindlog-ai-service python3 -c "
import os, httpx
api_key = os.environ['PINECONE_API_KEY']
idx = os.environ['PINECONE_INDEX_KNOWLEDGE']
r = httpx.get(f'https://api.pinecone.io/indexes/{idx}',
              headers={'Api-Key': api_key}, timeout=10.0)
print('status:', r.status_code)
print('body:', r.text[:400])
"
```
- 200 → 존재. `dimension` 필드 확인 (4096이어야 함).
- 404 → B1'로 진행.
- 401/403 → API Key 권한 문제. 사용자 에스컬레이션.

### B1'. 인덱스 직접 생성 (404일 때만, 개발자3)

**스펙 결정 기준**: `PINECONE_INDEX_EPISODE`(기존 가동 중인 인덱스)의 스펙을 참조하여 동일 구성. `embedding-query`/`embedding-passage`가 모두 4096차원이므로 `dimension=4096`, 메트릭은 cosine(임베딩 표준).

**사전 조회 — Episode 인덱스 스펙 확인**
```bash
sudo docker exec mindlog-ai-service python3 -c "
import os, httpx
api_key = os.environ['PINECONE_API_KEY']
ep = os.environ.get('PINECONE_INDEX_EPISODE', '')
if ep:
    r = httpx.get(f'https://api.pinecone.io/indexes/{ep}',
                  headers={'Api-Key': api_key}, timeout=10.0)
    print(r.status_code, r.text)
else:
    print('PINECONE_INDEX_EPISODE 미설정')
"
```
- 반환된 JSON에서 `dimension`, `metric`, `spec` 확인 → 동일 스펙 사용.

**생성 명령 (확인 후 실행)**
```bash
sudo docker exec mindlog-ai-service python3 -c "
import os, json, httpx
api_key = os.environ['PINECONE_API_KEY']
idx = os.environ['PINECONE_INDEX_KNOWLEDGE']
body = {
    'name': idx,
    'dimension': 4096,
    'metric': 'cosine',
    'spec': {'serverless': {'cloud': 'aws', 'region': 'us-east-1'}},
}
r = httpx.post('https://api.pinecone.io/indexes',
               headers={'Api-Key': api_key, 'Content-Type': 'application/json'},
               json=body, timeout=30.0)
print('status:', r.status_code)
print('body:', r.text[:800])
"
```
- `spec` 값은 B1'-pre 단계에서 조회한 Episode 인덱스 `spec`을 그대로 복사(리전/클라우드 혼선 방지).
- 생성 직후 status가 Ready가 될 때까지 10초 정도 대기 후 B1-2 재조회하여 `status=Ready` 확인.
- **리뷰 게이트**: 생성 명령 실행 **전** 최종 body(특히 `spec`)를 사용자에게 보여주고 승인 대기.

### B1''. API Key 권한 확인

- 인덱스 조회가 401/403이거나 생성이 권한 에러로 실패 시, 현재 `PINECONE_API_KEY`가 해당 Pinecone 프로젝트의 권한을 가진 키인지 재확인 후 사용자에게 보고.

### B2. 적재 데이터 확장 (원저자 영역)

현재 `scripts/ingest_config.yaml`은 PDF 1건, `personal_counsel` 도메인만 등록되어 있다.

**권장안 (원저자 개발자1 협의)**:
- `mental_health` 도메인 PDF 최소 1건 추가 (예: 스트레스 관리 매뉴얼 — 기 주석 처리된 예시 참고).
- `personal_counsel` 외 도메인이 RAG에서 실제로 조회될 수 있도록 최소 1건씩이라도 시드 데이터 확보.
- 적재 명령 예시:
  ```bash
  python scripts/ingest_knowledge.py --config scripts/ingest_config.yaml
  ```
- **본 계획 범위 밖**: 적재 실행 자체는 본 PR이 아니라 별도 운영 작업으로 분리 (담당: 개발자1 또는 운영).

### B3. 임계값/도메인 매칭 정책 점검 (범위 외, 관찰 항목)

- 현재 `pinecone_score_threshold=0.7` (settings.yaml), 도메인 필터 `{"domain": {"$eq": domain}}`. 런타임 호출자가 `domain="mental_health"`으로 고정할 경우, 적재에 없는 도메인은 항상 빈 응답이 된다.
- 호출부(`podcast_reasoning.py`)가 어떤 domain 값을 넘기는지 재확인 필요하지만, 이는 본 계획 **범위 외**로 둔다.

---

## 3. Phase C — 재검증 (개발자3)

### C1. 사전 조건 체크리스트

- [ ] Phase A PR 머지 완료 + develop 빌드 성공
- [ ] GitHub Secret `KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT` 등록 완료 (값: `/v1/parser`로 끝나는 URL)
- [ ] GitHub Secret `KT_CLOUD_KNOWLEDGE_PARSER_TOKEN` 등록 완료
- [ ] Phase B1 완료 (Pinecone 인덱스 존재·이름·dimension·API Key 정합)
- [ ] Phase B2 완료 (도메인 `mental_health` 포함 최소 1건 이상 적재)
- [ ] deploy.yml 최신화 반영된 SHA가 EC2에 배포 완료

### C2. SSM 재검증 명령

```bash
# 1. env 주입 확인 (PARSER로 변경됐는지)
sudo docker exec mindlog-ai-service env | grep -E "KT_CLOUD_KNOWLEDGE_PARSER|KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY|KT_CLOUD_KNOWLEDGE_TEXTGEN|PINECONE_INDEX_KNOWLEDGE" | sed 's/=.*/=<SET>/'

# 2. search() 재호출
sudo docker exec mindlog-ai-service python3 -c "
import asyncio
from src.agents.podcast.knowledge import KnowledgeAgent
async def run():
    kn = KnowledgeAgent()
    r = await kn.search(query='불안 대처', domain='mental_health')
    print('articles_count:', len(r.get('articles', [])))
    for a in r.get('articles', [])[:2]:
        print('-', a.get('title'), '| score:', a.get('score'))
asyncio.run(run())
"
```

### C3. 성공 기준 (Task 4-3와 동일)

- Parser 호출 시 HTTP 200 (`[KnowledgeAgent] Parser 완료: ...` 로그)
- Pinecone host 조회 200 (`[KnowledgeAgent] Pinecone 검색 결과 없음` 또는 결과 로그)
- `articles_count >= 1`

### C4. 실패 시 롤백 기준

- Phase A 회귀 수정만 원복 가능 (env var 네이밍 복구는 코드·deploy.yml 동시 revert).
- Pinecone 관련 문제는 롤백이 아니라 Phase B를 마저 해결.

---

## 4. Phase D — 문서 반영

### D1. 갱신 대상

| 문서 | 섹션 | 갱신 내용 |
|------|------|---------|
| `docs/superpowers/plans/2026-04-15-knowledge-agent-activation-and-verification.md` | Task 4-3 체크박스 | Phase C 검증 완료 후 체크 |
| `CLAUDE.md` | "구현 현황" PR 목록 | PR #148 회귀 수정 PR 번호 + 날짜 추기 |
| `docs/superpowers/plans/INDEX.md` | Knowledge RAG 섹션 | 본 계획서 링크 추가 |

### D2. 메모리 업데이트 — **제외** (사용자 지침 2026-04-15 15:35)

---

## 5. 리스크 및 오픈 이슈

### 5.1 즉시 리스크

- **R1** — Phase A PR 머지 시 `KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT` 시크릿이 등록 안 되어 있으면 런타임에서 Parser가 계속 비활성(미설정) 상태. 다만 `_parse_query`는 미설정 시 원본 쿼리로 fallback 하므로 서비스 중단은 없음.
- **R2** — Phase B 완료 전에는 `articles_count == 0`이 지속된다. 이는 Safety/Personalizer 등 상위 흐름에는 영향 없음 (KnowledgeAgent는 `{"articles": [], "guidelines": []}`를 정상 반환).
- **R3** — Pinecone 인덱스 직접 생성 시 `spec` 오류(리전·cloud 불일치)로 적재 단계에서 네트워크 비용/지연 발생 가능. Episode Memory 인덱스 스펙을 **그대로 복사**하여 리스크 최소화. 생성 전 리뷰 게이트 필수.

### 5.2 오픈 이슈 (범위 외, 추후 트랙)

- **O1** — `_parse_query()`가 `/v1/parser` 미설정 시 원본 쿼리를 쓰는데, 이게 "Parser는 선택적"이라는 설계라면 env var 분리 유지가 맞고, "필수"라면 Parser 비활성 시 경보 로직 필요. 본 계획에서는 결정하지 않음.
- **O2** — `ingest_config.yaml` 확장 범위·도메인 체계(감성 분류 vs 심리 도메인)는 별도 기획 필요. 본 계획은 "최소 1건 `mental_health`" 선으로 한정.
- **O3** — `PINECONE_INDEX_KNOWLEDGE` 기본값(`expert-knowledge`)과 실제 운영값(`rag-suite-knowledge`) 괴리. 코드 기본값을 운영값에 맞추든, 운영값을 코드 기본값에 맞추든 일관화 필요.

---

## 6. 진행 순서 — 단계별 리뷰 게이트 필수

> **원칙**: 각 체크박스는 **사용자 리뷰·승인 후** 다음 단계로 진행. 체크 없이 다음 단계 착수 금지.

### 게이트 1: 계획 승인
1. [ ] **본 계획서 사용자 리뷰·승인** ← **현재 단계**

### 게이트 2: Phase A 코드 수정
2. [ ] feature/validation-knowledge-parser-revert 브랜치 생성
3. [ ] `knowledge.py` / `.env.example` / `deploy.yml` 수정 (diff 공유)
4. [ ] **사용자 리뷰 — diff 확인**
5. [ ] 로컬 pytest + lint 통과 확인
6. [ ] **사용자 리뷰 — 테스트 결과 확인**
7. [ ] 커밋
8. [ ] **사용자 지시 후** 푸시 + PR 생성 (base: develop)
9. [ ] CI 통과 확인 → 사용자 공유

### 게이트 3: 시크릿 등록
10. [ ] **사용자**: `KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT/_TOKEN` 시크릿 등록 후 확인 회신

### 게이트 4: PR 머지 + 배포
11. [ ] **사용자 지시 후** PR 머지 → deploy 자동 실행
12. [ ] 배포 성공 확인 (SHA 매칭)

### 게이트 5: Phase B — Pinecone 정합성 (개발자3 SSM)
13. [ ] B1-1: SSM `printenv PINECONE_INDEX_KNOWLEDGE` 실값 확인 → 사용자 공유
14. [ ] B1-2: Pinecone 인덱스 조회 → 결과 사용자 공유
15. [ ] **분기**:
    - **존재(200)**: → 게이트 6
    - **없음(404)**: → 게이트 5a
16. [ ] (게이트 5a) B1'-pre: Episode 인덱스 스펙 조회 → 사용자 공유
17. [ ] (게이트 5a) 생성 body 초안 제시 → **사용자 리뷰·승인**
18. [ ] (게이트 5a) 인덱스 생성 실행 → 결과·status=Ready 확인 → 사용자 공유

### 게이트 6: Phase C — 1차 재검증 (Parser 동작 확인)
19. [ ] SSM env 주입 확인 (PARSER 이름으로 `<SET>`)
20. [ ] `KnowledgeAgent.search()` 호출 → Parser 200 로그 확인
    - `articles_count`는 Phase B2 전까지 0 허용 (인덱스 비어있음 or 도메인 미적재)
21. [ ] 결과 사용자 공유

### 게이트 7: Phase B2 — 적재 (범위 외, 원저자/운영 영역)
22. [ ] **사용자/개발자1**: `scripts/ingest_knowledge.py` 실행 여부 결정
23. [ ] 실행 완료 회신

### 게이트 8: Phase C — 최종 재검증
24. [ ] SSM `KnowledgeAgent.search()` 재호출 → `articles_count >= 1` 확인
25. [ ] 결과 사용자 공유

### 게이트 9: Phase D 문서 반영
26. [ ] 영향 계획서 체크박스 반영 (D1) → **사용자 리뷰**
27. [ ] (D2 제외)

---

## 7. 리뷰 체크리스트 (각 게이트별)

**공통**: 모든 게이트는 결과를 사용자에게 **명시적으로 보여주고 승인 받은 후** 다음 단계 진행.

- 코드 diff: 전체 변경사항 인용 후 승인 대기
- 테스트 결과: pass/fail 카운트 + 실패 항목 상세
- SSM 실행: 명령 + 출력 스크린샷
- Pinecone 생성 body: JSON 전문 + spec 근거(Episode 스펙 참조)
- PR 생성 직전: 브랜치명·커밋 메시지·PR 제목·본문 모두 제시

---

**마지막 업데이트**: 2026-04-15 15:35

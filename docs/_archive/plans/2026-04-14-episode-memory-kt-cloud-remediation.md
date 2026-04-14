# Plan #40: Episode Memory + KT Cloud 연동 정합성 수정

> **상태**: ✅ 완료
> **마지막 업데이트**: 2026-04-14 19:00
> **선행 PR**: #119 (가은 — KT Cloud embedding API), #122 (충돌 해소), #124 (로직 복원), #125 (user_id metadata)
> **완료 PR**: #127 (EpisodeMemory DI 전환 + 어댑터 패턴), .env.example 변수명 수정, settings.yaml 미사용 index_memory_podcast 제거

---

## Context

가은(imnotgaeun)의 PR #119에서 Episode Memory Agent에 KT Cloud embedding API `/v1/embeddings` 경로 + `{"model": mode, "input": text}` payload 구조가 적용되었다. 충돌 해소 및 로직 복원 완료 후 종합 점검한 결과, 아래 이슈가 확인되었다.

---

## 현황 요약

### GitHub Secrets 상태 (2026-04-14 확인)

| Secret | 등록일 | 상태 |
|--------|--------|------|
| `KT_CLOUD_QUERY_ENDPOINT` | 2026-04-08 | ✅ |
| `KT_CLOUD_QUERY_TOKEN` | 2026-04-08 | ✅ |
| `KT_CLOUD_PASSAGE_ENDPOINT` | 2026-04-08 | ✅ |
| `KT_CLOUD_PASSAGE_TOKEN` | 2026-04-08 | ✅ |
| `KT_CLOUD_TEXTGEN_ENDPOINT` | 2026-04-08 | ✅ |
| `KT_CLOUD_TEXTGEN_TOKEN` | 2026-04-08 | ✅ |
| `PINECONE_API_KEY` | 2026-04-07 | ✅ |
| `PINECONE_INDEX_EPISODE` | 2026-04-08 | ✅ |

### deploy.yml 환경변수 전달 (라인 108-115)

```
KT_CLOUD_QUERY_ENDPOINT → .env → docker-compose → 컨테이너 ✅
KT_CLOUD_QUERY_TOKEN → .env → docker-compose → 컨테이너 ✅
KT_CLOUD_PASSAGE_ENDPOINT → .env → docker-compose → 컨테이너 ✅
KT_CLOUD_PASSAGE_TOKEN → .env → docker-compose → 컨테이너 ✅
KT_CLOUD_TEXTGEN_ENDPOINT → .env → docker-compose → 컨테이너 ✅
KT_CLOUD_TEXTGEN_TOKEN → .env → docker-compose → 컨테이너 ✅
PINECONE_INDEX_EPISODE → .env → docker-compose → 컨테이너 ✅
```

**결론**: 배포 파이프라인에서 환경변수 전달은 정상.

---

## 이슈 목록

### Issue 1: `search()` 메서드 부재 (Critical)

**상태**: ❌ 미구현
**파일**: `src/agents/podcast/episode_memory.py`

**문제**:
- `podcast_reasoning.py:456`에서 `self.episode_memory.search(query, user_id)` 호출
- `stubs.py:31`의 `EpisodeMemoryStub.search()` 인터페이스 정의:
  ```python
  async def search(self, query: str, user_id: str) -> dict:
      return {"episodes": [], "relevance_scores": []}
  ```
- `EpisodeMemoryAgent`에는 `search()` 메서드가 없음 → Stub→실제 전환 시 **AttributeError**

**호출 조건** (`podcast_reasoning.py:437-460`):
- `execution_plan.needs_memory == True` 또는 `complexity >= 0.6`

**영향**: 현재는 Stub으로 동작하므로 증상 없음. DI 전환 시 런타임 에러 발생.

**수정 방안**:
```python
async def search(self, query: str, user_id: str) -> dict:
    """PodcastReasoningAgent 호환 검색 인터페이스."""
    namespace = self._build_namespace(user_id)
    items = await self._retrieve_from_store(query, namespace)
    return {
        "episodes": items,
        "relevance_scores": [item.get("score", 0.0) for item in items],
    }
```

---

### Issue 2: .env.example 변수명 불일치 (Warning)

**상태**: ⚠️ 문서 오류
**파일**: `.env.example`

**현재 `.env.example` (라인 33-35)**:
```bash
# KT Cloud RAG Suite - Episode Memory
KT_CLOUD_ENDPOINT=          # ← 코드에서 미사용
KT_CLOUD_API_TOKEN=         # ← 코드에서 미사용
```

**실제 코드가 참조하는 변수** (`episode_memory.py:26-31`):
```
KT_CLOUD_QUERY_ENDPOINT
KT_CLOUD_QUERY_TOKEN
KT_CLOUD_PASSAGE_ENDPOINT
KT_CLOUD_PASSAGE_TOKEN
KT_CLOUD_TEXTGEN_ENDPOINT
KT_CLOUD_TEXTGEN_TOKEN
```

**영향**: `.env.example` 보고 설정하면 변수명이 달라서 빈 문자열로 로드됨. GitHub Secrets와 deploy.yml에는 올바른 변수명이 등록되어 있어 **프로덕션에는 영향 없음**. 로컬 개발 환경 설정 시 혼동 가능.

**수정 방안**: `.env.example`의 Episode Memory 섹션을 실제 변수명으로 교체.

---

### Issue 3: Pinecone 인덱스 설정 이중 경로 (Warning)

**상태**: ⚠️ 설정 불일치

| 위치 | 설정 방식 | 값 |
|------|----------|---|
| `config/settings.yaml:166` | `pinecone.index_memory_podcast` | `"mem-podcast-episode"` |
| `episode_memory.py:33` | `os.getenv("PINECONE_INDEX_EPISODE", "")` | GitHub Secret에서 주입 |

**문제**: settings.yaml에 정의된 `index_memory_podcast`를 episode_memory.py가 참조하지 않음. 대신 환경변수 `PINECONE_INDEX_EPISODE`를 직접 사용.

**영향**: 실질적 문제 없음 (프로덕션에서 GitHub Secret으로 주입). 하지만 설정 소스가 이중으로 존재하여 혼동 가능.

**수정 방안**: 두 가지 옵션
- **A**: episode_memory.py가 Settings를 참조하도록 변경 (Knowledge Agent 패턴과 통일)
- **B**: settings.yaml에서 `index_memory_podcast` 제거하고 환경변수 전용으로 유지 (현상 유지)

→ 가은 담당 에이전트이므로 가은과 협의 필요.

---

### Issue 4: Knowledge Agent 임베딩 호출 비일관성 (Warning)

**상태**: ⚠️ 비일관

| 항목 | Episode Memory | Knowledge Agent |
|------|---------------|-----------------|
| 경로 | `{endpoint}/v1/embeddings` ✅ | `{endpoint}` (경로 미명시) |
| payload | `{"model": mode, "input": text}` ✅ | `{"input": text}` (`model` 없음) |
| 환경변수 | `KT_CLOUD_QUERY_ENDPOINT` | `KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT` |

**파일**: `src/agents/podcast/knowledge.py:409-432`

**가능성**:
- Knowledge Agent의 `KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT` 값 자체에 `/v1/embeddings` 경로가 포함되어 있을 수 있음
- KT Cloud API가 `model` 필드 없이도 동작할 수 있음 (기본 모델 사용)

**영향**: Knowledge Agent가 현재 프로덕션에서 정상 동작 중이라면 문제 없음. 추후 KT Cloud API 변경 시 영향 가능.

**수정 방안**: Knowledge Agent의 `_embed_query()`를 Episode Memory 패턴으로 통일하거나, 두 에이전트의 KT Cloud 연동 방식 차이를 문서화.

→ Knowledge Agent는 개발자1 담당이므로 협의 필요.

---

### Issue 5: SCORE_THRESHOLD 이슈 (Info)

**상태**: 📋 참고

PR #119 설명에서 가은이 언급:
> `_SCORE_THRESHOLD = 0.7`로 설정되어 있으나 테스트 당시 score가 0.378이 버려져 0건으로 나옴. 차후 관련 문제가 있을 시 해당 값 수치 조정 필요.

**파일**: `episode_memory.py:14`
```python
_SCORE_THRESHOLD = 0.7
```

**영향**: 실제 서비스에서 유사도 점수가 낮으면 모든 결과가 필터링되어 빈 결과 반환. `super().process(state)` fallback으로 LLM 기반 응답 생성.

**수정 방안**: 프로덕션 데이터 축적 후 threshold 조정. 즉시 조치 불필요.

---

## Task 목록

### Task 1: EpisodeMemoryAgent.search() 메서드 추가

**Priority**: 🔴 Critical
**Files**:
- Modify: `src/agents/podcast/episode_memory.py`
- Add test: `tests/agents/podcast/test_episode_memory.py`

**구현**:
1. `search(query: str, user_id: str) -> dict` 메서드 추가
2. 반환 구조: `{"episodes": list[dict], "relevance_scores": list[float]}` (Stub과 동일)
3. 내부적으로 `_build_namespace()` + `_retrieve_from_store()` 호출
4. 테스트: mock 기반 search() 호출 검증

**검증 기준**:
- `EpisodeMemoryStub.search()` 시그니처와 동일
- `podcast_reasoning.py`에서 DI로 실제 에이전트 주입 시 정상 동작
- 기존 테스트 전체 통과

---

### Task 2: .env.example Episode Memory 변수명 수정

**Priority**: ⚠️ Warning
**Files**:
- Modify: `.env.example`

**구현**:
```bash
# KT Cloud RAG Suite - Episode Memory
# KT_CLOUD_QUERY_ENDPOINT=https://...proxy.aifoundry.ktcloud.com
# KT_CLOUD_QUERY_TOKEN=
# KT_CLOUD_PASSAGE_ENDPOINT=https://...proxy.aifoundry.ktcloud.com
# KT_CLOUD_PASSAGE_TOKEN=
# KT_CLOUD_TEXTGEN_ENDPOINT=https://...proxy.aifoundry.ktcloud.com
# KT_CLOUD_TEXTGEN_TOKEN=
# PINECONE_INDEX_EPISODE=mem-podcast-episode
```

---

### Task 3: Knowledge Agent 임베딩 호출 표준화 검토

**Priority**: 📋 협의 필요
**Files**:
- Review: `src/agents/podcast/knowledge.py:409-432`

**내용**:
- Knowledge Agent의 `_embed_query()`가 `/v1/embeddings` 경로와 `model` 필드를 사용하는지 확인
- 환경변수 `KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT` 값에 경로가 포함되어 있는지 확인
- Episode Memory 패턴과 통일 여부 결정

→ **개발자1 + 가은 협의 후 진행**

---

### Task 4: Pinecone 인덱스 설정 통일 검토

**Priority**: 📋 협의 필요
**Files**:
- Review: `config/settings.yaml:163-166`
- Review: `src/agents/podcast/episode_memory.py:33`

**내용**:
- settings.yaml의 `index_memory_podcast` vs 환경변수 `PINECONE_INDEX_EPISODE` 이중 존재
- 어느 쪽을 정규 소스로 할지 결정

→ **가은 협의 후 진행**

---

## 파일 맵

| 파일 | Task | 변경 유형 |
|------|------|----------|
| `src/agents/podcast/episode_memory.py` | Task 1 | `search()` 메서드 추가 |
| `tests/agents/podcast/test_episode_memory.py` | Task 1 | `search()` 테스트 추가 |
| `.env.example` | Task 2 | 변수명 수정 |
| `src/agents/podcast/knowledge.py` | Task 3 | 검토 (수정 여부 협의) |
| `config/settings.yaml` | Task 4 | 검토 (수정 여부 협의) |

---

## 참고: 환경변수 전체 흐름

```
GitHub Secrets
    ↓ (deploy.yml 라인 91-116)
.env 파일 동적 생성 (EC2)
    ↓ (docker-compose.yml env_file)
컨테이너 환경변수
    ↓ (os.getenv)
EpisodeMemoryAgent.__init__()
    ├── KT_CLOUD_QUERY_ENDPOINT → _embed("embedding-query")
    ├── KT_CLOUD_PASSAGE_ENDPOINT → _embed("embedding-passage")
    ├── KT_CLOUD_TEXTGEN_ENDPOINT → _generate_summary()
    ├── PINECONE_API_KEY → _get_host(), _upsert(), _query()
    └── PINECONE_INDEX_EPISODE → _get_host()
```

---

## 참고: Stub vs 실제 에이전트 전환 경로

```
현재:
  podcast_reasoning.py → EpisodeMemoryStub.search() → 빈 결과

전환 후 (Task 1 완료 시):
  podcast_reasoning.py → EpisodeMemoryAgent.search()
                            ├── _build_namespace(user_id)
                            ├── _retrieve_from_store(query, namespace)
                            │      ├── _embed(query, "embedding-query") → KT Cloud
                            │      └── _query(vec, namespace) → Pinecone
                            └── return {"episodes": items, "relevance_scores": [...]}

DI 전환 위치:
  podcast_reasoning.py:58
  현재: self.episode_memory = episode_memory or EpisodeMemoryStub()
  변경: self.episode_memory = episode_memory or EpisodeMemoryAgent()
  ※ DI 전환은 Task 1 완료 + 프로덕션 검증 후 별도 작업
```

---

*작성일: 2026-04-14 15:30*

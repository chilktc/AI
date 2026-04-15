# Episode Memory & Knowledge Agent — 벡터 DB(Pinecone) RAG 설명서

> 작성일: 2026-04-06
> 대상 에이전트: Episode Memory Agent, Knowledge Agent
> 핵심 기술: Pinecone Vector DB, Embedding, RAG (Retrieval-Augmented Generation)

---

## 1. 에이전트 개요

### 1.1 Episode Memory Agent

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/episode_memory.py` |
| **부모 클래스** | `BaseMemoryAgent` → `BaseAgent` |
| **역할** | 사용자의 과거 팟캐스트 에피소드 기억을 검색하여 개인화된 연속성 제공 |
| **호출 조건** | Podcast Reasoning Agent가 `complexity_score ≥ 0.6` 또는 `execution_plan.needs_memory = True`일 때 조건부 호출 |
| **Pinecone 인덱스** | `mem-podcast-episode` |
| **출력 필드** | `AgentState.memory_results` |

**핵심 기능:**
- **인출(Retrieve)**: 사용자 발화를 임베딩하여 과거 에피소드 중 유사한 기억을 벡터 검색
- **저장(Save)**: 새로운 에피소드 완료 후 해당 내용을 임베딩하여 벡터 DB에 저장
- **개인화 연속성**: "지난번에 불안에 대해 이야기했죠" 같은 맥락 유지

**현재 구현 상태:**
- KT Cloud RAG Suite 임베딩 API 연결 코드 존재 (환경변수: `KT_CLOUD_ENDPOINT`, `KT_CLOUD_API_TOKEN`)
- 실제 벡터 검색은 `data/cache/mock_db.json` 로컬 파일에서 수행 (목업 상태)
- Pinecone 직접 연동은 **미구현** — `PineconeClient` 인프라는 준비됨

### 1.2 Knowledge Agent

| 항목 | 내용 |
|------|------|
| **파일** | `src/agents/podcast/knowledge.py` |
| **부모 클래스** | `BaseAgent` |
| **역할** | CBT, DBT 등 전문 심리상담 지식을 벡터 검색하여 근거 기반(Evidence-Based) 응답 제공 |
| **호출 조건** | Podcast Reasoning Agent가 `complexity_score ≥ 0.5` 또는 `execution_plan.needs_knowledge = True`일 때 조건부 호출 |
| **Pinecone 인덱스** | `rag-suite-knowledge` |
| **출력 필드** | `AgentState.knowledge_results` |

**핵심 기능 (5단계 RAG 파이프라인):**

```
사용자 발화 → ① 쿼리 확장(LLM) → ② 벡터 검색(Pinecone) → ③ 원문 조회(RDB)
                                                                    ↓
                      ⑤ 최종 출력 구조화 ← ④ 적합성 평가(LLM) + 지식 종합(LLM)
```

| 단계 | 메서드 | 설명 |
|------|--------|------|
| ① 쿼리 확장 | `_expand_query()` | LLM이 사용자 일상어를 전문 심리학 용어로 변환 + 도메인 분류 |
| ② 벡터 검색 | `_search_knowledge_base()` | Pinecone에서 임베딩 유사도 기반 top-k 검색 |
| ③ 원문 조회 | `_get_documents()` | 벡터 검색 결과의 doc_id로 RDB에서 전체 문서 조회 |
| ④ 적합성 평가 | `_assess_applicability()` | LLM이 사용자 맥락(나이, 문화, 이전 치료)에 맞는지 평가 |
| ⑤ 지식 종합 | `_synthesize_knowledge()` | LLM이 모든 문서를 통합하여 권장 치료 접근법 생성 |

**현재 구현 상태:**
- Pinecone 클라이언트를 DI(의존성 주입)로 받는 구조 완성
- Podcast Reasoning에서는 `KnowledgeAgentStub`(빈 결과 반환)으로 대체 중
- 실제 Pinecone/RDB 클라이언트 연결 시 즉시 동작 가능

---

## 2. 데이터 흐름 상세

### 2.1 Episode Memory — 벡터 검색 흐름

```
[Podcast Reasoning Agent]
    │
    │ episode_memory.search(query, user_id)
    ↓
[EpisodeMemoryAgent.process()]
    │
    ├─ 1. state에서 query 추출 (memory_query > user_input 우선순위)
    │
    ├─ 2. _retrieve_from_store(query)
    │     ├─ Embedding API로 query → 벡터 변환
    │     ├─ Pinecone query: index="mem-podcast-episode"
    │     │   filter={"user_id": user_id}
    │     │   top_k=5
    │     └─ 유사 에피소드 목록 반환
    │
    └─ 3. 결과 구조화 → memory_results
          {
            "items": [...],           // 과거 에피소드 목록
            "summary": "...",         // 검색 결과 요약
            "suggested_personalization": {...},
            "_meta": {"namespace": "mem-podcast-episode", ...}
          }
```

### 2.2 Knowledge Agent — 5단계 RAG 파이프라인 흐름

```
[Podcast Reasoning Agent]
    │
    │ knowledge_agent.search(query, domain)
    ↓
[KnowledgeAgent.process()]
    │
    ├─ ① _expand_query(query, domain_hints)
    │     └─ LLM: "불안해요" → {
    │          professional_query: "generalized anxiety disorder coping strategies",
    │          selected_domains: ["CBT", "DBT"],
    │          search_keywords: ["anxiety", "cognitive restructuring"]
    │        }
    │
    ├─ ② _search_knowledge_base(professional_query, domains)
    │     ├─ embedding_client.get_embedding(query) → [0.12, -0.34, ...]
    │     └─ pinecone_client.query(
    │          index="rag-suite-knowledge",
    │          vector=embedding,
    │          filter={"domain": {"$in": ["CBT", "DBT"]}},
    │          top_k=5
    │        ) → [{id: "doc_001", score: 0.92, metadata: {...}}, ...]
    │
    ├─ ③ _get_documents(doc_ids=["doc_001", ...])
    │     └─ RDB: SELECT id, title, content, domain, source,
    │             evidence_level, contraindications
    │             FROM knowledge_base WHERE id = ANY($1)
    │
    ├─ ④ _assess_applicability(documents, user_context)
    │     └─ LLM: 사용자 나이/문화/이전 치료 기반 적합성 점수 (0~1)
    │
    ├─ ⑤ _synthesize_knowledge(query, documents, applicability)
    │     └─ LLM: 종합 분석 + 권장 접근법 + 근거 수준
    │
    └─ _build_output() → {
          "knowledge_results": {
            "documents": [{id, title, content, source, relevance_score, applicability_score, ...}],
            "synthesis": "근거 기반 분석 텍스트"
          },
          "recommended_approaches": [{approach, rationale, contraindications}]
        }
```

---

## 3. Pinecone 인덱스 설계

### 3.1 인덱스 구성

프로젝트에서 사용하는 Pinecone 인덱스는 2개이다.

| 인덱스 이름 | 용도 | 사용 에이전트 | 데이터 특성 |
|------------|------|-------------|------------|
| `rag-suite-knowledge` | 전문 심리상담 지식 | Knowledge Agent | 정적 데이터 (사전 적재) |
| `mem-podcast-episode` | 사용자별 에피소드 기억 | Episode Memory Agent | 동적 데이터 (실시간 누적) |

### 3.2 `rag-suite-knowledge` 인덱스 (Knowledge Agent)

**목적:** CBT, DBT, 정신역동, 위기개입 등 전문 심리치료 지식 문서의 임베딩 저장

**벡터 스키마:**

```json
{
  "id": "doc_001",
  "values": [0.12, -0.34, 0.56, ...],   // 임베딩 벡터 (차원: 모델에 따라 결정)
  "metadata": {
    "domain": "CBT",                     // 도메인: CBT | DBT | psychodynamic | crisis_intervention | general_psychology
    "title": "인지 재구조화 기법",
    "source": "journal_article",          // 출처 유형: journal_article | textbook | clinical_guideline
    "evidence_level": "high",             // 근거 수준: high | moderate | low
    "doc_id": "doc_001",                  // RDB 원문 조회용 ID
    "language": "ko",
    "last_updated": "2026-01-15"
  }
}
```

**필터 사용 패턴:**

```python
# Knowledge Agent의 _search_knowledge_base()에서 사용
results = await pinecone_client.query(
    index="rag-suite-knowledge",
    vector=embedding,                          # 쿼리 임베딩
    filter={"domain": {"$in": ["CBT", "DBT"]}},  # 도메인 필터
    top_k=5,
    include_metadata=True,
)
```

**데이터 적재 전략:**
- 사전 배치 적재 (Batch Ingestion): 논문, 교과서, 임상 가이드라인을 청킹하여 임베딩 후 upsert
- 업데이트 주기: 새로운 연구/가이드라인 발표 시 수동 배치
- 청킹 권장: 500~1000 토큰 단위, 문단/섹션 경계 기준

### 3.3 `mem-podcast-episode` 인덱스 (Episode Memory Agent)

**목적:** 사용자별 팟캐스트 에피소드 기억의 임베딩 저장

**벡터 스키마:**

```json
{
  "id": "mem_user123_ep_20260405",
  "values": [0.08, -0.21, 0.43, ...],   // 임베딩 벡터
  "metadata": {
    "user_id": "user_123",               // 사용자 격리 (필수 필터)
    "session_id": "sess_abc",
    "episode_date": "2026-04-05",
    "topic": "불안 관리",
    "emotion_primary": "anxiety",
    "type": "user_log",                   // user_log | system_summary
    "text_preview": "오늘 직장에서 발표할 때..."  // 원문 미리보기 (200자)
  }
}
```

**네임스페이스 사용:**

```python
# 네임스페이스로 사용자 데이터 격리 (선택적)
results = await pinecone_client.query(
    index="mem-podcast-episode",
    vector=embedding,
    filter={"user_id": {"$eq": user_id}},   # 사용자 필터 (필수)
    top_k=5,
    namespace="",                            # 또는 user_id를 네임스페이스로 사용
)
```

**데이터 적재 전략:**
- 실시간 적재: 에피소드 완료 시 `_save_to_store()` 호출
- 저장 내용: 에피소드 요약 텍스트 + 감정 벡터 + 주제 메타데이터
- 사용자당 데이터 증가: 매 세션마다 1~3건 누적

### 3.4 임베딩 모델 선택

| 옵션 | 모델 | 차원 | 비용 | 비고 |
|------|------|------|------|------|
| **권장** | Amazon Titan Embeddings v2 | 1024 | AWS 네이티브, Bedrock 통합 | AWS 환경 최적 |
| 대안 1 | Upstage Embedding | 4096 | KT Cloud 연동 (현재 코드 참조) | 기존 코드와 호환 |
| 대안 2 | OpenAI text-embedding-3-small | 1536 | 저렴, 고성능 | 외부 의존 |
| 대안 3 | Cohere embed-multilingual-v3 | 1024 | 다국어 강점 | 한국어 성능 우수 |

> **주의:** 인덱스 생성 시 임베딩 차원을 모델에 맞춰야 합니다. 인덱스 생성 후에는 차원 변경이 불가능합니다.

---

## 4. AWS 기반 Pinecone 운용 방안

### 4.1 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────┐
│                     AWS Cloud (VPC)                       │
│                                                           │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │  ECS/EKS    │    │  Amazon      │    │  Amazon     │  │
│  │  AI Server  │───▶│  Bedrock     │    │  RDS/Aurora │  │
│  │  (app-2)    │    │  (Embedding) │    │  (MySQL)    │  │
│  │  :8000      │    └──────────────┘    └─────────────┘  │
│  │             │                              ▲           │
│  │  ┌────────┐ │                              │           │
│  │  │Pinecone│ │    ┌──────────────┐          │           │
│  │  │Client  │─┼───▶│  Pinecone    │          │           │
│  │  └────────┘ │    │  (Serverless)│          │           │
│  │             │    │  AWS us-east-1│          │           │
│  └──────┬──────┘    └──────────────┘          │           │
│         │                                      │           │
│  ┌──────▼──────┐                               │           │
│  │  Backend    │───────────────────────────────┘           │
│  │  Server     │                                           │
│  │  (app-3)    │    ┌──────────────┐                      │
│  │  :8080      │───▶│  Amazon S3   │                      │
│  └─────────────┘    │  (Images)    │                      │
│                     └──────────────┘                      │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Pinecone 배포 옵션 (AWS)

Pinecone은 AWS 위에서 호스팅되는 관리형 서비스이다. AWS 리전 선택이 레이턴시에 직접 영향을 준다.

| 옵션 | 설명 | 비용 | 권장 상황 |
|------|------|------|----------|
| **Pinecone Serverless** | 종량제, 자동 스케일링 | $2/M 읽기 유닛 | 트래픽 변동 큼, 초기 단계 ★권장 |
| Pinecone Standard (Pod) | 전용 Pod 할당 | $0.096/hr (s1.x1) | 일정한 고트래픽 |

**Pinecone Serverless on AWS 설정:**

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="YOUR_API_KEY")

# 1. rag-suite-knowledge 인덱스 생성
pc.create_index(
    name="rag-suite-knowledge",
    dimension=1024,                    # Amazon Titan v2 기준
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"            # AI 서버 리전과 일치시킬 것
    )
)

# 2. mem-podcast-episode 인덱스 생성
pc.create_index(
    name="mem-podcast-episode",
    dimension=1024,
    metric="cosine",
    spec=ServerlessSpec(
        cloud="aws",
        region="us-east-1"
    )
)
```

### 4.3 임베딩 생성 — Amazon Bedrock 연동

AWS 환경에서는 Amazon Bedrock의 임베딩 모델을 사용하는 것이 네트워크 레이턴시와 비용 측면에서 최적이다.

**임베딩 클라이언트 구현 예시:**

```python
import boto3
import json
from typing import Any

class BedrockEmbeddingClient:
    """Amazon Bedrock 기반 임베딩 클라이언트.

    Knowledge Agent와 Episode Memory Agent의 embedding_client로 주입.
    """

    def __init__(
        self,
        model_id: str = "amazon.titan-embed-text-v2:0",
        region: str = "us-east-1",
    ) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region,
        )
        self._model_id = model_id

    async def get_embedding(self, text: str) -> list[float]:
        """텍스트를 임베딩 벡터로 변환한다."""
        import asyncio

        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,        # Titan v2는 256/512/1024 지원
            "normalize": True,
        })

        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["embedding"]
```

### 4.4 Storage Mode별 동작

`config/settings.yaml`의 `storage.mode` 설정에 따라 Pinecone 접근 방식이 달라진다.

```
storage.mode 값에 따른 벡터 DB 접근 경로:

local   → PineconeClient (직접 접속)
           AI 서버가 Pinecone API를 직접 호출
           개발/테스트 환경에 적합

proxy   → VectorProxyClient → BackendClient → Backend 서버 → Pinecone
           AI 서버는 Backend API만 호출, Backend가 Pinecone 중계
           프로덕션 기본값 (현재 설정)

hybrid  → PineconeClient (직접 접속)
           Pinecone/Neo4j는 직접, MySQL만 Backend 경유
           프로덕션 대안
```

**팩토리 코드 (`src/db/factory.py`):**

```python
def create_vector_client() -> BaseVectorClient:
    mode = get_settings().storage_mode
    if mode == "proxy":
        return VectorProxyClient(BackendClient())   # Backend API 경유
    return PineconeClient()                          # 직접 접속 (local/hybrid)
```

### 4.5 AWS 보안 설정

**환경변수 관리 (AWS Secrets Manager 권장):**

```bash
# Pinecone 관련
PINECONE_API_KEY=pcsk_xxxxx           # Pinecone API 키
PINECONE_ENVIRONMENT=us-east-1        # Pinecone 환경 (Serverless는 생략 가능)

# Bedrock 임베딩 (IAM Role 사용 시 불필요)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=xxxxx               # 또는 IAM Role 사용 (권장)
AWS_SECRET_ACCESS_KEY=xxxxx
```

**IAM 정책 (최소 권한):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockEmbedding",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
      ]
    }
  ]
}
```

**네트워크 보안:**
- AI 서버 → Pinecone: HTTPS (443) 아웃바운드 허용
- AI 서버 → Bedrock: AWS PrivateLink (VPC 엔드포인트) 사용 권장
- AI 서버 → RDS: VPC 내부 통신 (Security Group으로 제한)

---

## 5. Pinecone 통합 구현 가이드

### 5.1 Episode Memory Agent — Pinecone 전환

현재 `mock_db.json` 기반인 Episode Memory를 Pinecone으로 전환하는 방법이다.

**변경 대상:** `_retrieve_from_store()`, `_save_to_store()`

```python
class EpisodeMemoryAgent(BaseMemoryAgent):

    def __init__(
        self,
        pinecone_client: BaseVectorClient | None = None,
        embedding_client: Any | None = None,
    ) -> None:
        super().__init__(
            name="episode_memory",
            output_key="memory_results",
            namespace="mem-podcast-episode",
            tier=None,
        )
        self.pinecone_client = pinecone_client
        self.embedding_client = embedding_client

    async def _retrieve_from_store(self, query: str) -> list[dict]:
        """Pinecone에서 유사 에피소드를 검색한다."""
        if not self.embedding_client or not self.pinecone_client:
            return []  # 클라이언트 미설정 시 빈 결과

        # 1. 쿼리 임베딩
        embedding = await self.embedding_client.get_embedding(query)

        # 2. Pinecone 검색
        results = await self.pinecone_client.query(
            index="mem-podcast-episode",
            vector=embedding,
            filter={"user_id": {"$eq": self._current_user_id}},
            top_k=5,
            include_metadata=True,
        )

        # 3. 결과 변환
        items = []
        for match in results.get("matches", []):
            items.append({
                "text": match["metadata"].get("text_preview", ""),
                "score": match["score"],
                "metadata": match["metadata"],
            })
        return items

    async def _save_to_store(self, text: str, metadata: dict | None = None) -> bool:
        """새 에피소드를 Pinecone에 저장한다."""
        if not self.embedding_client or not self.pinecone_client:
            return False

        # 1. 임베딩 생성
        embedding = await self.embedding_client.get_embedding(text)

        # 2. Pinecone upsert
        vector_id = f"mem_{metadata.get('user_id', 'unknown')}_{metadata.get('date', '')}"
        await self.pinecone_client.upsert(
            index="mem-podcast-episode",
            vectors=[{
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "user_id": metadata.get("user_id", ""),
                    "text_preview": text[:200],
                    "type": metadata.get("type", "user_log"),
                    **metadata,
                },
            }],
        )
        return True
```

### 5.2 Knowledge Agent — 이미 Pinecone 준비 완료

Knowledge Agent는 이미 DI 기반으로 Pinecone 클라이언트를 받는 구조이다.
실제 연동은 클라이언트만 주입하면 된다.

**워크플로우 등록 시 클라이언트 주입:**

```python
# src/graph/workflow.py 에서

from src.db.factory import create_vector_client, create_rdb_client

# 클라이언트 생성
vector_client = create_vector_client()         # Pinecone 또는 프록시
rdb_client = create_rdb_client()               # MySQL 또는 프록시
embedding_client = BedrockEmbeddingClient()    # Bedrock 임베딩

# Knowledge Agent 노드 생성
knowledge_node = await create_knowledge_node(
    db_client=rdb_client,
    pinecone_client=vector_client,
    embedding_client=embedding_client,
)

# Podcast Reasoning에 실제 에이전트 주입 (stub 대체)
podcast_reasoning = PodcastReasoningAgent(
    episode_memory=EpisodeMemoryAgent(
        pinecone_client=vector_client,
        embedding_client=embedding_client,
    ),
    knowledge_agent=KnowledgeAgent(
        db_client=rdb_client,
        pinecone_client=vector_client,
        embedding_client=embedding_client,
    ),
)
```

---

## 6. 데이터 적재 (Knowledge Base 초기 구축)

### 6.1 전문 지식 데이터 적재 스크립트 예시

```python
"""rag-suite-knowledge 인덱스에 심리상담 지식을 배치 적재하는 스크립트."""

import json
from pathlib import Path

async def ingest_knowledge_base(
    pinecone_client,
    embedding_client,
    data_dir: str = "data/knowledge_base/",
):
    """JSON 형식의 지식 문서를 Pinecone에 적재한다."""

    data_path = Path(data_dir)
    batch_size = 100
    batch = []

    for json_file in data_path.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            documents = json.load(f)

        for doc in documents:
            # 임베딩 생성
            text_to_embed = f"{doc['title']}\n{doc['content']}"
            embedding = await embedding_client.get_embedding(text_to_embed)

            batch.append({
                "id": doc["id"],
                "values": embedding,
                "metadata": {
                    "domain": doc["domain"],           # CBT, DBT, ...
                    "title": doc["title"],
                    "source": doc["source"],
                    "evidence_level": doc["evidence_level"],
                    "doc_id": doc["id"],
                    "language": doc.get("language", "ko"),
                    "last_updated": doc.get("last_updated", ""),
                },
            })

            if len(batch) >= batch_size:
                await pinecone_client.upsert(
                    index="rag-suite-knowledge",
                    vectors=batch,
                )
                batch = []

    # 잔여 배치 처리
    if batch:
        await pinecone_client.upsert(
            index="rag-suite-knowledge",
            vectors=batch,
        )
```

### 6.2 지식 문서 JSON 포맷

```json
[
  {
    "id": "cbt_001",
    "title": "인지 재구조화 기법",
    "content": "인지 재구조화(Cognitive Restructuring)는 CBT의 핵심 기법으로...",
    "domain": "CBT",
    "source": "clinical_guideline",
    "evidence_level": "high",
    "contraindications": "급성 정신병적 상태에서는 부적합",
    "language": "ko",
    "last_updated": "2026-01-15"
  },
  {
    "id": "dbt_001",
    "title": "감정 조절 기술 (Emotion Regulation)",
    "content": "DBT의 감정 조절 모듈은 4가지 핵심 기술을 포함하며...",
    "domain": "DBT",
    "source": "textbook",
    "evidence_level": "high",
    "contraindications": null,
    "language": "ko",
    "last_updated": "2026-02-01"
  }
]
```

---

## 7. 비용 및 성능 예측

### 7.1 Pinecone Serverless 비용 (AWS us-east-1)

| 항목 | 단가 | 예상 사용량 (월) | 예상 비용 |
|------|------|----------------|----------|
| 저장 | $0.33/GB | rag-suite-knowledge: ~0.5GB, memory: ~2GB | ~$0.8 |
| 읽기 유닛 | $8.25/1M RU | 10만 쿼리 × 5 top_k | ~$4.1 |
| 쓰기 유닛 | $2/1M WU | 1만 upsert (에피소드 저장) | ~$0.02 |
| **소계** | | | **~$5/월** |

> 초기 단계 기준 추정. 사용자 수 증가 시 선형 증가.

### 7.2 Amazon Bedrock 임베딩 비용

| 모델 | 단가 | 예상 사용량 (월) | 예상 비용 |
|------|------|----------------|----------|
| Titan Embeddings v2 | $0.02/1K 입력 토큰 | 50만 토큰 (검색+저장) | ~$10 |

### 7.3 레이턴시 예측

| 단계 | 예상 레이턴시 |
|------|------------|
| Bedrock 임베딩 | 50~150ms |
| Pinecone 검색 (Serverless) | 50~200ms |
| RDB 원문 조회 | 10~50ms |
| LLM 쿼리 확장/평가/종합 (3회) | 1~5s (모델에 따라) |
| **Episode Memory 총합** | 100~350ms |
| **Knowledge Agent 총합** | 1.5~6s |

---

## 8. 현재 코드의 알려진 이슈

| 이슈 | 설명 | 영향 |
|------|------|------|
| **Episode Memory: mock_db 의존** | `_retrieve_from_store()`가 `mock_db.json`에서만 읽음 | Pinecone 전환 필요 |
| **Knowledge Agent: stub DI** | Podcast Reasoning이 `KnowledgeAgentStub` 사용 중 | 실제 클라이언트 주입 필요 |
| **[S-3] domain_hints 미정의** | `AgentState`에 `domain_hints` 필드 없음 | Intent Classifier에서 전달 불가 |
| **[B-7] domain_hints 미전달** | Intent Classifier가 `domain_hints` 생성 안 함 | Knowledge Agent가 전체 도메인 검색 |
| **[S-5] 메모리 데이터 비효율** | 에피소드 상세 조회하지만 count만 사용 | 불필요한 데이터 전송 |
| **임베딩 클라이언트 미통합** | Episode Memory는 KT Cloud, Knowledge는 DI — 통합 필요 | 이중 임베딩 파이프라인 |

---

## 9. 요약 — 현재 상태 vs 목표 상태

```
현재 (as-is):
  Episode Memory  → KT Cloud 임베딩 확인 + mock_db.json 로컬 파일
  Knowledge Agent → Stub (빈 결과 반환)
  Pinecone Client → 코드 존재하나 연결 안 됨
  임베딩           → KT Cloud (Episode Memory만), 미통합

목표 (to-be):
  Episode Memory  → Bedrock 임베딩 + Pinecone (mem-podcast-episode)
  Knowledge Agent → Bedrock 임베딩 + Pinecone (rag-suite-knowledge) + RDS 원문
  Pinecone Client → factory.py로 환경별 자동 생성
  임베딩           → BedrockEmbeddingClient 통합 (DI)
```

**전환 작업 우선순위:**
1. `BedrockEmbeddingClient` 구현 (공통 임베딩 클라이언트)
2. Pinecone Serverless 인덱스 2개 생성 (AWS us-east-1)
3. `rag-suite-knowledge` 지식 데이터 초기 적재
4. Episode Memory의 `_retrieve_from_store()` / `_save_to_store()` Pinecone 전환
5. Knowledge Agent에 실제 클라이언트 DI 주입 (stub 교체)
6. `domain_hints` 필드 추가 및 Intent Classifier 연동 ([S-3], [B-7] 해결)

# Pinecone 벡터 DB 공통 인프라 구축 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 다른 개발자들이 Pinecone을 올바르게 사용할 수 있는 공통 기반을 먼저 구축한다. 에이전트별 구현은 이 계획의 범위 밖이다.

**Architecture:** 환경 검증 → 공통 클라이언트(Bedrock 임베딩) → 팩토리 함수 → 인덱스 생성 → 개발자 CLI 스크립트 → 가이드 문서 순으로 진행한다.

**Tech Stack:** Pinecone Serverless (AWS `us-east-1`), Amazon Bedrock Titan Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024차원, 리전 `ap-northeast-2`), boto3>=1.34.0, pinecone>=3.0.0

---

## 현재 완료 현황 (2026-04-15 16:50 재정합)

> **⚠️ 방향 전환 공지 (2026-04-15)**: 본 계획서는 초기(2026-04-07) **Amazon Bedrock Titan Embeddings v2** 기준으로 설계되었으나,
> 2026-04-15 기준 실제 구현은 **KT Cloud Embedding Passage/Query API + Qwen3-32B TextGen** 으로 확정되었다(PR #145/#146/#150).
> 따라서 Task 2(BedrockEmbeddingClient)는 **폐기**, Task 5/6/7/9는 KT Cloud 기반으로 **재설계 필요**.

| Task | 상태 | PR | 비고 |
|------|------|-----|------|
| Task 1: 환경변수 검증 스크립트 | ✅ 완료 | #64 | `validate_pinecone_env.py` 작성, 테스트 5개 통과 |
| Task 2: BedrockEmbeddingClient | ⛔ **폐기** | — | KT Cloud Embedding으로 선회(PR #145). 별도 클라이언트 클래스 불필요 — `src/agents/podcast/knowledge.py`가 직접 KT Cloud API 호출 |
| Task 3: Pinecone 인덱스 생성 스크립트 | ✅ 완료 | #64, #67 | `create_pinecone_indexes.py`, EC2 인덱스 생성 확인. **차원 4096 확정** |
| Task 4: Pinecone 연결 상태 테스트 스크립트 | ✅ 완료 | #64, #67 | `test_pinecone_connection.py`, EC2 헬스체크 통과 |
| Task 5: 임베딩 생성 테스트 스크립트 | 🔶 **재설계 필요** | — | 기존 Bedrock 전제 → **KT Cloud Embedding Query API** 호출 스크립트로 재작성 필요 |
| Task 6: 벡터 저장 → 검색 E2E 테스트 | 🔶 **재설계 필요** | — | KT Cloud 임베딩 → Pinecone upsert → query E2E 로직으로 재작성 필요 |
| Task 7: 지식 데이터 초기 적재 스크립트 | ✅ **대체 구현 완료** | #145 | `scripts/ingest_knowledge.py` + `scripts/ingest_config.yaml` (KT Cloud Parser + Embedding Passage + Pinecone upsert). ⚠️ 현재 `domain=personal_counsel` 1건만 적재 설정 — 운영 쿼리(`domain=mental_health`)와 불일치 |
| Task 8: 전체 회귀 테스트 | 🔶 일부 완료 | #67 | tests/db/ 59개 통과, 전체 594 passed 유지(2026-04-15) |
| Task 9: 개발자 가이드 | ❌ 미완료 | — | `PINECONE_DEVELOPER_GUIDE.md` 미작성 — **KT Cloud + Pinecone 기준으로 신규 작성 필요** (임베딩 차원 2560 등 실값 반영) |

**추가 완료 (2026-04-15 기준):**
- EC2 Docker 환경 Pinecone 연결 검증 완료 (PR #65, #66 선행 필요 수정 포함)
- 인덱스명 하이픈 규칙 적용: `expert-knowledge`, `mem-podcast-episode`
- `knowledge.py` 인덱스명: 기본값 `expert-knowledge` (`PINECONE_INDEX_KNOWLEDGE` 환경변수로 오버라이드)
- **인덱스 차원 1024 → 4096 변경**: `create_pinecone_indexes.py`, `test_pinecone_connection.py`, `tests/db/test_pinecone_*.py` 일괄 수정 완료
  - ⚠️ 실제 KT Cloud Embedding은 2560차원 반환 가능 — 인덱스 차원 정합성 운영 검증 필요(Plan #47 Phase 4)
- **Pinecone DB 연결 완료**: EC2 환경에서 실제 인덱스 생성 및 연결 확인
- **PR #85(feature/agents-gaeun) 머지 완료** (2026-04-08 07:54): EpisodeMemoryAgent._save_to_store() 실제 구현 반영. EpisodeMemory 저장 트리거 구현은 Plan #23 완료
- **KT Cloud RAG Suite 통합 완료** (PR #145, 2026-04-15): Document Parse API, Embedding Passage/Query API, Qwen3-32B TextGen 연동. `scripts/ingest_knowledge.py` + `scripts/ingest_config.yaml` 적재 파이프라인 완성
- **KnowledgeAgent 임계값 외부화** (PR #146): `pinecone_score_threshold`, `pinecone_top_k` settings.yaml 외부화
- **KnowledgeAgentStub 정식 제거** (PR #147): 실제 KnowledgeAgent로 fallback 전환
- **환경변수 네이밍 정합** (PR #148~#150): `KT_CLOUD_KNOWLEDGE_PARSE_*`로 통일 (GitHub Secrets 정합)
- **RAG 결과 파이프라인 연결** (PR #151): Reasoning phase별 주입, ScriptGenerator state 키 정합, 관측성 경고 추가

### 잔여 과제 — 운영 필수/선택 구분

| 구분 | 항목 | 블로커 여부 |
|------|------|-----------|
| **운영 필수(데이터)** | `ingest_config.yaml`에 `domain=mental_health` 문서 추가 및 `scripts/ingest_knowledge.py` 실행 | ★ 필수 — Plan #47 Phase 4 `articles_count ≥ 1` 검증의 선행 조건 |
| **운영 선택(CLI)** | Task 5 `test_embedding.py` (KT Cloud 기반) | 선택 — 개발자 CLI |
| **운영 선택(CLI)** | Task 6 `test_vector_roundtrip.py` (KT Cloud 기반) | 선택 — 개발자 CLI |
| **운영 선택(문서)** | Task 9 `PINECONE_DEVELOPER_GUIDE.md` (KT Cloud 기준) | 선택 — 개발자 온보딩용 |

---

## 담당자 및 브랜치

| 역할 | 담당 | 브랜치 |
|------|------|--------|
| **이 계획 실행** | 개발자3 (공통 인프라) | `feature/validation-pinecone-infra` |
| 이후 EpisodeMemory 전환 | 개발자2 | `feature/reasoning-*` |
| 이후 KnowledgeAgent 전환 | 개발자1 | `feature/analysis-*` |
| 이후 Reasoning DI 주입 | 개발자3 | `feature/validation-*` |

> **Protected Files — 이 계획에서 수정 없음:**
> `src/models/agent_state.py`, `src/graph/workflow.py`, `src/api/contracts.py`, `src/models/message.py`
>
> **에이전트 코드 — 이 계획에서 수정 없음:**
> `src/agents/podcast/episode_memory.py`, `src/agents/podcast/knowledge.py`, `src/agents/podcast/podcast_reasoning.py`

---

## 배포 환경 구조

```
EC2 t3.medium (2 vCPU, 4GB RAM)
├── Docker: mindlog-ai-service (1500m)   → src/, config/ 포함
│   └── Bedrock Client ─────────────────→ AWS Bedrock (ap-northeast-2)
│   └── Pinecone Client ────────────────→ Pinecone Serverless (us-east-1)
└── Docker: mindlog-neo4j (1g)

dev/scripts/ → Docker 이미지에 미포함
             → 호스트(로컬 또는 EC2 SSH)에서 직접 실행
             → 또는 docker compose run으로 실행 (volume 필요)
```

### AWS 인증 방식 (Docker 컨테이너)

EC2에서 IAM 인스턴스 프로파일을 사용하면 Docker 컨테이너도 자동으로 인증된다.
`169.254.169.254` 메타데이터 엔드포인트는 EC2 위의 컨테이너에서 접근 가능하다.

```
EC2 배포 환경 (권장):
  → IAM 인스턴스 프로파일에 Bedrock 권한 부여
  → .env에 AWS 키 불필요 (자동 인증)

로컬 개발 환경:
  → .env에 AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY 직접 설정
```

### 스크립트 실행 위치 규칙

| 실행 방식 | 명령어 형태 | 사용 시점 |
|---------|-----------|---------|
| **호스트 직접** | `python dev/scripts/xxx.py` | 로컬 개발, EC2 SSH 접속 후 |
| **Docker 컨테이너** | `docker compose run --rm ai-server python dev/scripts/xxx.py` | EC2에서 컨테이너 환경 그대로 테스트 |

> Docker 컨테이너에서 실행 시 `dev/` 폴더가 이미지에 없으므로 볼륨 마운트 필요:
> `docker compose run --rm -v $(pwd)/dev:/app/dev ai-server python dev/scripts/xxx.py`

---

## 파일 구조 (이 계획에서 생성/수정하는 파일)

| 상태 | 파일 경로 | 역할 |
|------|----------|------|
| **신규** | `src/db/embedding_client.py` | `BaseEmbeddingClient` 추상 + `BedrockEmbeddingClient` |
| **수정** | `src/db/factory.py` | `create_embedding_client()` 함수 추가 |
| **신규** | `tests/db/__init__.py` | 테스트 패키지 |
| **신규** | `tests/db/test_embedding_client.py` | 단위 테스트 |
| **신규** | `dev/scripts/validate_pinecone_env.py` | 필수 환경변수 사전 검증 |
| **신규** | `dev/scripts/create_pinecone_indexes.py` | 인덱스 2개 생성 (1회성) |
| **신규** | `dev/scripts/test_pinecone_connection.py` | 연결 + 인덱스 상태 확인 |
| **신규** | `dev/scripts/test_embedding.py` | 임베딩 생성 확인 (개발자 CLI) |
| **신규** | `dev/scripts/test_vector_roundtrip.py` | 저장→검색 E2E 확인 (개발자 CLI) |
| **신규** | `dev/scripts/ingest_knowledge_base.py` | 지식 데이터 초기 적재 |
| **신규** | `dev/data/knowledge_sample.json` | 샘플 지식 데이터 |
| **신규** | `docs/guides/PINECONE_DEVELOPER_GUIDE.md` | 개발자 사용 가이드 |

---

## Task 1: 환경변수 검증 스크립트

배포 또는 개발 시작 전 필수 환경변수 누락을 조기에 감지한다.

**Files:**
- Create: `dev/scripts/validate_pinecone_env.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""
Pinecone + AWS Bedrock 연동에 필요한 환경변수를 검증한다.

실행 (호스트):
    python dev/scripts/validate_pinecone_env.py

실행 (Docker):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/validate_pinecone_env.py
"""
from __future__ import annotations

import os
import sys

REQUIRED: list[tuple[str, str]] = [
    ("PINECONE_API_KEY", "Pinecone API 키 (pinecone.io 콘솔에서 발급)"),
    ("AWS_REGION", "AWS 리전 (예: ap-northeast-2)"),
]

OPTIONAL: list[tuple[str, str, str]] = [
    ("STORAGE_MODE", "저장소 모드 — Pinecone 직접 접속 시 반드시 local 또는 hybrid", "proxy"),
    ("APP_ENV", "애플리케이션 환경", "development"),
]


def check_aws_credentials() -> bool:
    """환경변수 또는 IAM 인스턴스 프로파일로 AWS 자격증명 확인."""
    # 방법 1: 환경변수
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        print("[OK] AWS 자격증명 (환경변수)")
        return True

    # 방법 2: IAM 인스턴스 프로파일 (EC2 전용)
    try:
        import urllib.request
        url = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
        with urllib.request.urlopen(url, timeout=1) as resp:
            role = resp.read().decode().strip()
            if role:
                print(f"[OK] AWS 자격증명 (IAM 인스턴스 프로파일: {role})")
                return True
    except Exception:
        pass

    print("[ERROR] AWS 자격증명 없음")
    print("  → 로컬: .env에 AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY 추가")
    print("  → EC2:  인스턴스에 IAM 역할 부여 (bedrock:InvokeModel 권한 필요)")
    return False


def main() -> None:
    errors: list[str] = []

    print("=== 필수 환경변수 ===")
    for var, desc in REQUIRED:
        val = os.getenv(var)
        if not val:
            print(f"[ERROR] {var} 미설정 — {desc}")
            errors.append(var)
        else:
            masked = val[:6] + "****" if len(val) > 6 else "****"
            print(f"[OK]    {var} = {masked}")

    print("\n=== AWS 자격증명 ===")
    if not check_aws_credentials():
        errors.append("AWS_CREDENTIALS")

    print("\n=== 선택 환경변수 ===")
    for var, desc, default in OPTIONAL:
        val = os.getenv(var, default)
        print(f"[INFO]  {var} = {val} — {desc}")

    mode = os.getenv("STORAGE_MODE", "proxy")
    if mode not in ("local", "proxy", "hybrid"):
        print(f"[ERROR] STORAGE_MODE='{mode}' 잘못된 값 — local|proxy|hybrid 중 하나")
        errors.append("STORAGE_MODE")
    elif mode == "proxy":
        print("\n[WARN] STORAGE_MODE=proxy")
        print("  Pinecone 직접 연결 테스트 시 STORAGE_MODE=local 로 변경하세요.")
        print("  .env: STORAGE_MODE=local")

    print()
    if errors:
        print(f"검증 실패: {len(errors)}건 — {errors}")
        sys.exit(1)
    print("검증 통과")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 확인**

```bash
python -m py_compile dev/scripts/validate_pinecone_env.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 실패 케이스 확인**

```bash
PINECONE_API_KEY="" python dev/scripts/validate_pinecone_env.py
echo "exit code: $?"
```

Expected: `[ERROR] PINECONE_API_KEY 미설정` + `exit code: 1`

- [ ] **Step 4: 커밋**

```bash
git add dev/scripts/validate_pinecone_env.py
git commit -m "feat: Pinecone + AWS 환경변수 검증 스크립트"
```

---

## Task 2: BedrockEmbeddingClient 구현 (공통 라이브러리)

**Files:**
- Create: `src/db/embedding_client.py`
- Create: `tests/db/__init__.py`
- Create: `tests/db/test_embedding_client.py`

- [ ] **Step 1: 실패 테스트 먼저 작성**

```python
# tests/db/__init__.py
```
(빈 파일)

```python
# tests/db/test_embedding_client.py
"""
BedrockEmbeddingClient 단위 테스트.

boto3를 모킹하여 AWS 자격증명 없이 실행 가능하다.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.db.embedding_client import BedrockEmbeddingClient


class TestBedrockEmbeddingClient:

    def test_default_region_is_ap_northeast_2(self) -> None:
        """기본 리전이 ap-northeast-2(서울)로 설정된다."""
        with patch("boto3.client"):
            client = BedrockEmbeddingClient()
        assert client._region == "ap-northeast-2"

    def test_default_model_is_titan_v2(self) -> None:
        """기본 모델이 Titan Embeddings v2다."""
        with patch("boto3.client"):
            client = BedrockEmbeddingClient()
        assert client._model_id == "amazon.titan-embed-text-v2:0"

    def test_custom_params(self) -> None:
        """커스텀 파라미터로 인스턴스 생성."""
        with patch("boto3.client"):
            client = BedrockEmbeddingClient(model_id="custom", region="us-east-1")
        assert client._model_id == "custom"
        assert client._region == "us-east-1"

    @pytest.mark.asyncio
    async def test_get_embedding_returns_1024_dim_list(self) -> None:
        """1024차원 float 리스트를 반환한다."""
        fake_vector = [0.1] * 1024
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({"embedding": fake_vector}).encode()

        with patch("boto3.client") as mock_boto:
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_model.return_value = {"body": mock_body}
            mock_boto.return_value = mock_bedrock

            client = BedrockEmbeddingClient()
            result = await client.get_embedding("테스트")

        assert isinstance(result, list)
        assert len(result) == 1024
        assert all(isinstance(v, float) for v in result)

    @pytest.mark.asyncio
    async def test_request_body_has_correct_format(self) -> None:
        """Bedrock 요청 본문이 dimensions=1024, normalize=True를 포함한다."""
        fake_vector = [0.0] * 1024
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({"embedding": fake_vector}).encode()

        captured: list[str] = []

        with patch("boto3.client") as mock_boto:
            mock_bedrock = MagicMock()

            def capture(**kwargs: object) -> dict:
                captured.append(str(kwargs["body"]))
                return {"body": mock_body}

            mock_bedrock.invoke_model.side_effect = capture
            mock_boto.return_value = mock_bedrock

            client = BedrockEmbeddingClient()
            await client.get_embedding("hello")

        body = json.loads(captured[0])
        assert body["dimensions"] == 1024
        assert body["normalize"] is True
        assert "inputText" in body

    @pytest.mark.asyncio
    async def test_calls_correct_model_id(self) -> None:
        """invoke_model이 올바른 modelId로 호출된다."""
        fake_vector = [0.0] * 1024
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps({"embedding": fake_vector}).encode()

        with patch("boto3.client") as mock_boto:
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_model.return_value = {"body": mock_body}
            mock_boto.return_value = mock_bedrock

            client = BedrockEmbeddingClient()
            await client.get_embedding("hello")

            kwargs = mock_bedrock.invoke_model.call_args[1]
            assert kwargs["modelId"] == "amazon.titan-embed-text-v2:0"


class TestCreateEmbeddingClient:

    def test_returns_bedrock_client(self) -> None:
        """create_embedding_client()가 BedrockEmbeddingClient를 반환한다."""
        from src.db.factory import create_embedding_client

        with patch("boto3.client"):
            client = create_embedding_client()

        assert isinstance(client, BedrockEmbeddingClient)
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/db/test_embedding_client.py -v 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'src.db.embedding_client'`

- [ ] **Step 3: BedrockEmbeddingClient 구현**

```python
# src/db/embedding_client.py
"""
임베딩 클라이언트 — 텍스트를 벡터로 변환.

모든 에이전트(EpisodeMemory, Knowledge)의 embedding_client DI에 주입한다.

사용법:
    from src.db.factory import create_embedding_client
    client = create_embedding_client()
    vector = await client.get_embedding("텍스트")  # list[float], 1024차원

인터페이스:
    class BaseEmbeddingClient(ABC):
        async def get_embedding(self, text: str) -> list[float]: ...

구현체:
    BedrockEmbeddingClient — Amazon Bedrock Titan v2 (ap-northeast-2)
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod

import boto3

logger = logging.getLogger(__name__)


class BaseEmbeddingClient(ABC):
    """임베딩 클라이언트 추상 인터페이스.

    에이전트 생성자 타입 힌팅용:
        def __init__(self, embedding_client: BaseEmbeddingClient | None = None)
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """텍스트를 임베딩 벡터로 변환한다.

        Args:
            text: 임베딩할 텍스트

        Returns:
            1024차원 float 리스트
        """
        ...


class BedrockEmbeddingClient(BaseEmbeddingClient):
    """Amazon Bedrock Titan Embeddings v2 임베딩 클라이언트.

    임베딩 차원: 1024 (Pinecone 인덱스 차원과 일치)
    리전: ap-northeast-2 (서울) — AI 서버와 동일 리전, 네트워크 비용 최소화

    AWS 인증 (우선순위):
        1. EC2 IAM 인스턴스 프로파일 (프로덕션 권장, 키 불필요)
        2. 환경변수 AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (로컬 개발)

    IAM 최소 권한:
        bedrock:InvokeModel
        Resource: arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.titan-embed-text-v2:0
    """

    def __init__(
        self,
        model_id: str = "amazon.titan-embed-text-v2:0",
        region: str = "ap-northeast-2",
    ) -> None:
        self._model_id = model_id
        self._region = region
        # boto3는 자동으로 환경변수 → IAM 프로파일 순서로 인증을 시도한다
        self._client = boto3.client("bedrock-runtime", region_name=region)

    async def get_embedding(self, text: str) -> list[float]:
        """텍스트를 1024차원 임베딩 벡터로 변환한다.

        Args:
            text: 임베딩할 텍스트 (최대 8192 토큰)

        Returns:
            1024차원 float 리스트 (정규화됨)
        """
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True,
        })

        # boto3는 동기 라이브러리 → asyncio.to_thread로 블로킹 방지
        response = await asyncio.to_thread(
            self._client.invoke_model,
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        vector: list[float] = result["embedding"]
        logger.debug("임베딩 생성 완료 (차원: %d)", len(vector))
        return vector
```

- [ ] **Step 4: factory.py 업데이트**

`src/db/factory.py` 파일을 읽어 다음 내용을 반영한다:

파일 상단 (`from __future__ import annotations` 바로 아래) 에 추가:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.embedding_client import BaseEmbeddingClient
```

파일 맨 끝에 함수 추가:

```python
def create_embedding_client() -> "BaseEmbeddingClient":
    """임베딩 클라이언트를 생성한다.

    항상 BedrockEmbeddingClient (ap-northeast-2, Titan v2)를 반환한다.

    AWS 인증:
        EC2 환경: IAM 인스턴스 프로파일 자동 사용
        로컬 환경: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY 환경변수 필요

    사용법:
        from src.db.factory import create_embedding_client
        client = create_embedding_client()
        vector = await client.get_embedding("텍스트")
    """
    from src.db.embedding_client import BedrockEmbeddingClient

    return BedrockEmbeddingClient()
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
python -m pytest tests/db/test_embedding_client.py -v
```

Expected: `6 passed`

- [ ] **Step 6: 커밋**

```bash
git add src/db/embedding_client.py src/db/factory.py \
        tests/db/__init__.py tests/db/test_embedding_client.py
git commit -m "feat: BedrockEmbeddingClient 공통 임베딩 클라이언트 + factory 함수 추가"
```

---

## Task 3: Pinecone 인덱스 생성 스크립트 (1회성)

**Files:**
- Create: `dev/scripts/create_pinecone_indexes.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""
Pinecone 인덱스 생성 스크립트 (1회성 실행).

인덱스:
  expert_knowledge    : Knowledge Agent — 심리상담 전문 지식 (1024차원)
  mem_podcast_episode : Episode Memory  — 사용자 에피소드 기억 (1024차원)

실행 (호스트):
    PINECONE_API_KEY=<key> python dev/scripts/create_pinecone_indexes.py

실행 (Docker):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/create_pinecone_indexes.py

옵션:
    --force   기존 인덱스 삭제 후 재생성
"""
from __future__ import annotations

import argparse
import os
import sys

from pinecone import Pinecone, ServerlessSpec

# Pinecone Serverless: AWS us-east-1만 지원
CLOUD = "aws"
REGION = "us-east-1"

INDEXES = [
    {
        "name": "expert_knowledge",
        "dimension": 1024,
        "metric": "cosine",
        "description": "Knowledge Agent — 심리상담 전문 지식 벡터",
    },
    {
        "name": "mem_podcast_episode",
        "dimension": 1024,
        "metric": "cosine",
        "description": "Episode Memory — 팟캐스트 에피소드 기억 벡터",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="기존 인덱스 삭제 후 재생성")
    args = parser.parse_args()

    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        print("[ERROR] PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    pc = Pinecone(api_key=api_key)
    existing = {idx["name"] for idx in pc.list_indexes()}
    print(f"현재 인덱스: {existing or '없음'}\n")

    for cfg in INDEXES:
        name: str = cfg["name"]

        if name in existing:
            if args.force:
                print(f"[DELETE] '{name}' 삭제 중...")
                pc.delete_index(name)
                print(f"[OK]    '{name}' 삭제 완료")
            else:
                print(f"[SKIP]  '{name}' 이미 존재 ({cfg['description']})")
                continue

        print(f"[CREATE] '{name}' 생성 중 ({cfg['dimension']}차원, {cfg['metric']}, {CLOUD}/{REGION})...")
        pc.create_index(
            name=name,
            dimension=cfg["dimension"],
            metric=cfg["metric"],
            spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        )
        print(f"[OK]     '{name}' 생성 완료 — {cfg['description']}")

    print("\n완료")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 확인**

```bash
python -m py_compile dev/scripts/create_pinecone_indexes.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add dev/scripts/create_pinecone_indexes.py
git commit -m "feat: Pinecone 인덱스 생성 스크립트 (expert_knowledge, mem_podcast_episode)"
```

---

## Task 4: Pinecone 연결 상태 테스트 스크립트

**Files:**
- Create: `dev/scripts/test_pinecone_connection.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""
Pinecone 연결 상태 + 인덱스 접근성 확인 스크립트.

실행 (호스트):
    PINECONE_API_KEY=<key> python dev/scripts/test_pinecone_connection.py

실행 (Docker):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/test_pinecone_connection.py

테스트:
  1. Pinecone API 연결
  2. 필수 인덱스 존재 여부 확인
  3. 인덱스 stats (벡터 수, 차원)
  4. 더미 쿼리 — 인덱스 정상 응답 확인
"""
from __future__ import annotations

import os
import sys


def test_api_connection(pc: object) -> bool:
    try:
        indexes = pc.list_indexes()  # type: ignore[attr-defined]
        names = [idx["name"] for idx in indexes]
        print(f"[OK] Pinecone API 연결 성공 — 인덱스: {names}")
        return True
    except Exception as e:
        print(f"[ERROR] Pinecone API 연결 실패: {e}")
        return False


def test_index_exists(pc: object, required: list[str]) -> bool:
    all_ok = True
    existing = {idx["name"] for idx in pc.list_indexes()}  # type: ignore[attr-defined]
    for name in required:
        if name in existing:
            idx = pc.Index(name)  # type: ignore[attr-defined]
            stats = idx.describe_index_stats()
            count = stats.get("total_vector_count", 0)
            dim = stats.get("dimension", "?")
            print(f"[OK] '{name}' — 벡터 수: {count}, 차원: {dim}")
        else:
            print(f"[ERROR] '{name}' 인덱스 없음 → create_pinecone_indexes.py 실행 필요")
            all_ok = False
    return all_ok


def test_dummy_query(pc: object, index_name: str, dimension: int = 1024) -> bool:
    """더미 벡터로 쿼리하여 인덱스 응답을 확인한다."""
    existing = {idx["name"] for idx in pc.list_indexes()}  # type: ignore[attr-defined]
    if index_name not in existing:
        print(f"[SKIP] '{index_name}' 인덱스 없음 — 쿼리 생략")
        return True
    try:
        idx = pc.Index(index_name)  # type: ignore[attr-defined]
        result = idx.query(vector=[0.0] * dimension, top_k=1, include_metadata=False)
        count = len(result.get("matches", []))
        print(f"[OK] '{index_name}' 더미 쿼리 성공 (결과 {count}건)")
        return True
    except Exception as e:
        print(f"[ERROR] '{index_name}' 쿼리 실패: {e}")
        return False


def main() -> None:
    from pinecone import Pinecone

    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        print("[ERROR] PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    pc = Pinecone(api_key=api_key)
    required = ["expert_knowledge", "mem_podcast_episode"]
    results: list[bool] = []

    print("=== 1. API 연결 ===")
    results.append(test_api_connection(pc))

    print("\n=== 2. 인덱스 상태 ===")
    results.append(test_index_exists(pc, required))

    print("\n=== 3. 더미 쿼리 ===")
    for name in required:
        results.append(test_dummy_query(pc, name))

    print()
    if all(results):
        print("모든 테스트 통과 — Pinecone 정상")
    else:
        print(f"실패: {results.count(False)}건")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 확인**

```bash
python -m py_compile dev/scripts/test_pinecone_connection.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add dev/scripts/test_pinecone_connection.py
git commit -m "feat: Pinecone 연결 상태 테스트 스크립트"
```

---

## Task 5: 임베딩 생성 테스트 스크립트 (개발자 CLI)

각 에이전트 개발자가 "임베딩이 실제로 잘 생성되는가"를 직접 확인하는 도구.

**Files:**
- Create: `dev/scripts/test_embedding.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""
Bedrock 임베딩 생성 확인 스크립트 (개발자 CLI).

실행 (호스트):
    AWS_REGION=ap-northeast-2 \\
    AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> \\
    python dev/scripts/test_embedding.py --text "심리상담 관련 텍스트"

실행 (Docker):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/test_embedding.py --text "심리상담 관련 텍스트"

출력:
    - 벡터 차원 수
    - 처음 5개 값 (정상 여부 확인용)
    - 처리 시간
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time


async def run(text: str) -> None:
    # PYTHONPATH=/app 환경에서 실행
    sys.path.insert(0, ".")

    from src.db.embedding_client import BedrockEmbeddingClient

    print(f"입력 텍스트: {text[:80]}{'...' if len(text) > 80 else ''}")
    print("임베딩 생성 중...\n")

    client = BedrockEmbeddingClient()
    start = time.perf_counter()

    try:
        vector = await client.get_embedding(text)
    except Exception as e:
        print(f"[ERROR] 임베딩 생성 실패: {e}")
        print("\n확인 사항:")
        print("  1. AWS_REGION=ap-northeast-2 설정 여부")
        print("  2. AWS 자격증명 (환경변수 or IAM 인스턴스 프로파일)")
        print("  3. Bedrock 모델 접근 권한 (ap-northeast-2 리전)")
        sys.exit(1)

    elapsed = time.perf_counter() - start

    print(f"[OK] 임베딩 생성 성공")
    print(f"  차원: {len(vector)}")
    print(f"  첫 5개 값: {[round(v, 4) for v in vector[:5]]}")
    print(f"  처리 시간: {elapsed:.2f}초")

    if len(vector) != 1024:
        print(f"[WARN] 차원이 1024가 아님! Pinecone 인덱스와 불일치 가능")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bedrock 임베딩 생성 테스트")
    parser.add_argument("--text", default="오늘 기분이 좋았어요. 산책도 하고 친구도 만났습니다.", help="임베딩할 텍스트")
    args = parser.parse_args()
    asyncio.run(run(args.text))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 확인**

```bash
python -m py_compile dev/scripts/test_embedding.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add dev/scripts/test_embedding.py
git commit -m "feat: Bedrock 임베딩 생성 확인 CLI 스크립트"
```

---

## Task 6: 벡터 저장 → 검색 E2E 테스트 스크립트 (개발자 CLI)

임베딩 생성부터 Pinecone 저장, 검색까지 전체 흐름을 확인하는 도구. 에이전트 개발자가 실제 연동 전 동작을 검증할 때 사용한다.

**Files:**
- Create: `dev/scripts/test_vector_roundtrip.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
"""
Pinecone 저장 → 검색 E2E 테스트 스크립트 (개발자 CLI).

흐름:
  1. 텍스트를 Bedrock으로 임베딩
  2. Pinecone 인덱스에 upsert
  3. 동일 텍스트로 쿼리 → 방금 저장한 벡터가 1위로 검색되는지 확인
  4. 테스트 벡터 삭제 (cleanup)

실행 (호스트):
    PINECONE_API_KEY=<key> AWS_REGION=ap-northeast-2 \\
    AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> \\
    STORAGE_MODE=local \\
    python dev/scripts/test_vector_roundtrip.py \\
        --index expert_knowledge \\
        --text "인지행동치료는 부정적 사고 패턴을 교정하는 치료법이다"

실행 (Docker):
    docker compose run --rm \\
        -v $(pwd)/dev:/app/dev \\
        -e STORAGE_MODE=local \\
        ai-server \\
        python dev/scripts/test_vector_roundtrip.py --index expert_knowledge

옵션:
    --index   대상 인덱스 (기본: expert_knowledge)
    --text    테스트 텍스트
    --no-cleanup  저장된 테스트 벡터를 삭제하지 않음 (디버깅용)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid


async def run(index_name: str, text: str, cleanup: bool) -> None:
    sys.path.insert(0, ".")

    from src.db.embedding_client import BedrockEmbeddingClient
    from src.db.pinecone_client import PineconeClient

    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        print("[ERROR] PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    embedding_client = BedrockEmbeddingClient()
    pinecone_client = PineconeClient(api_key=api_key)
    test_id = f"test_{uuid.uuid4().hex[:8]}"

    print(f"인덱스: {index_name}")
    print(f"텍스트: {text[:80]}{'...' if len(text) > 80 else ''}")
    print(f"테스트 ID: {test_id}\n")

    # 1. 임베딩 생성
    print("1. 임베딩 생성...")
    t = time.perf_counter()
    try:
        embedding = await embedding_client.get_embedding(text)
    except Exception as e:
        print(f"[ERROR] 임베딩 실패: {e}")
        sys.exit(1)
    print(f"   완료 ({time.perf_counter() - t:.2f}초, {len(embedding)}차원)")

    # 2. Pinecone upsert
    print("2. Pinecone 저장...")
    t = time.perf_counter()
    try:
        await pinecone_client.upsert(
            index=index_name,
            vectors=[{
                "id": test_id,
                "values": embedding,
                "metadata": {"source": "roundtrip_test", "text_preview": text[:100]},
            }],
        )
    except Exception as e:
        print(f"[ERROR] upsert 실패: {e}")
        sys.exit(1)
    print(f"   완료 ({time.perf_counter() - t:.2f}초)")

    # 3. 쿼리 (동일 텍스트)
    print("3. 벡터 검색...")
    t = time.perf_counter()
    try:
        results = await pinecone_client.query(
            index=index_name,
            vector=embedding,
            filter={},
            top_k=3,
            include_metadata=True,
        )
    except Exception as e:
        print(f"[ERROR] 쿼리 실패: {e}")
        sys.exit(1)
    elapsed = time.perf_counter() - t

    matches = results.get("matches", [])
    print(f"   완료 ({elapsed:.2f}초, {len(matches)}건)")

    # 4. 결과 검증
    print()
    if matches:
        top = matches[0]
        print(f"[결과] 1위: id={top['id']}, score={top.get('score', '?'):.4f}")
        if top["id"] == test_id:
            print("[OK] 방금 저장한 벡터가 1위로 검색됨 — E2E 정상")
        else:
            print(f"[WARN] 1위가 테스트 벡터가 아님 (id={top['id']}) — 인덱스에 다른 데이터가 있을 수 있음")
    else:
        print("[WARN] 검색 결과 없음 — 인덱스가 비어있거나 벡터 반영에 시간이 필요할 수 있음")

    # 5. cleanup
    if cleanup:
        print(f"\n4. 테스트 벡터 삭제 ({test_id})...")
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=api_key)
            idx = pc.Index(index_name)
            idx.delete(ids=[test_id])
            print(f"   삭제 완료")
        except Exception as e:
            print(f"   [WARN] 삭제 실패: {e} — 수동 삭제 필요")

    await pinecone_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinecone E2E 라운드트립 테스트")
    parser.add_argument("--index", default="expert_knowledge",
                        choices=["expert_knowledge", "mem_podcast_episode"],
                        help="대상 인덱스")
    parser.add_argument("--text", default="인지행동치료는 부정적 사고 패턴을 교정하는 심리치료 기법입니다.",
                        help="테스트 텍스트")
    parser.add_argument("--no-cleanup", action="store_true", help="테스트 벡터 삭제 안 함")
    args = parser.parse_args()
    asyncio.run(run(args.index, args.text, cleanup=not args.no_cleanup))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 문법 확인**

```bash
python -m py_compile dev/scripts/test_vector_roundtrip.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add dev/scripts/test_vector_roundtrip.py
git commit -m "feat: Pinecone 저장→검색 E2E 테스트 CLI 스크립트"
```

---

## Task 7: 지식 데이터 초기 적재 스크립트

**Files:**
- Create: `dev/scripts/ingest_knowledge_base.py`
- Create: `dev/data/knowledge_sample.json`

- [ ] **Step 1: 샘플 데이터 작성**

```bash
mkdir -p dev/data
```

```json
[
  {
    "id": "doc_cbt_001",
    "domain": "CBT",
    "title": "인지행동치료 기본 원리",
    "content": "인지행동치료(CBT)는 부정적인 사고 패턴과 행동을 인식하고 수정하는 심리치료 접근법입니다. 사고-감정-행동의 연관성을 이해하고, 자동적 사고를 인식하여 인지를 재구성합니다.",
    "source": "clinical_guideline",
    "evidence_level": "high"
  },
  {
    "id": "doc_dbt_001",
    "domain": "DBT",
    "title": "변증법적 행동치료 마음챙김 기술",
    "content": "DBT의 마음챙김 기술은 현재 순간을 판단 없이 관찰하는 능력을 개발합니다. WHAT 기술(관찰, 기술, 참여)과 HOW 기술(비판단적, 집중, 효과적으로)이 핵심입니다.",
    "source": "textbook",
    "evidence_level": "high"
  },
  {
    "id": "doc_crisis_001",
    "domain": "crisis_intervention",
    "title": "위기 개입 안전 계획",
    "content": "위기 상황에서 안전 계획은 자해 충동에 대응하는 개인화된 전략입니다. 경고 신호 인식, 내부 대처 전략, 사회적 지지, 전문 자원 연락처로 구성됩니다.",
    "source": "clinical_guideline",
    "evidence_level": "high"
  },
  {
    "id": "doc_general_001",
    "domain": "general_psychology",
    "title": "감정 조절 전략",
    "content": "감정 조절은 감정의 강도와 지속 시간을 조절하는 능력입니다. 호흡 조절, 점진적 근육 이완, 인지적 재평가 등의 전략이 효과적으로 알려져 있습니다.",
    "source": "journal_article",
    "evidence_level": "moderate"
  }
]
```

- [ ] **Step 2: 적재 스크립트 작성**

```python
#!/usr/bin/env python3
"""
expert_knowledge 인덱스에 지식 데이터를 적재하는 스크립트.

실행 (호스트):
    PINECONE_API_KEY=<key> AWS_REGION=ap-northeast-2 \\
    AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> \\
    STORAGE_MODE=local \\
    python dev/scripts/ingest_knowledge_base.py \\
        --data dev/data/knowledge_sample.json

실행 (Docker):
    docker compose run --rm \\
        -v $(pwd)/dev:/app/dev \\
        -e STORAGE_MODE=local \\
        ai-server \\
        python dev/scripts/ingest_knowledge_base.py --data dev/data/knowledge_sample.json

옵션:
    --data      JSON 데이터 파일 경로 (기본: dev/data/knowledge_sample.json)
    --dry-run   임베딩/upsert 없이 데이터만 출력 (실행 전 검증용)
    --batch-size  한 번에 upsert할 벡터 수 (기본: 10, t3.medium 메모리 고려)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INDEX_NAME = "expert_knowledge"


async def ingest(data_path: Path, dry_run: bool, batch_size: int) -> None:
    sys.path.insert(0, ".")

    with open(data_path, encoding="utf-8") as f:
        documents: list[dict] = json.load(f)

    logger.info("총 %d개 문서 처리 예정 (인덱스: %s)", len(documents), INDEX_NAME)

    if dry_run:
        for doc in documents:
            logger.info("[DRY-RUN] id=%-20s domain=%-25s title=%s",
                        doc["id"], doc["domain"], doc["title"])
        logger.info("dry-run 완료 — 실제 저장 없음")
        return

    import os
    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        logger.error("PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    from src.db.embedding_client import BedrockEmbeddingClient
    from src.db.pinecone_client import PineconeClient

    embedding_client = BedrockEmbeddingClient()
    pinecone_client = PineconeClient(api_key=api_key)

    batch: list[dict] = []
    for i, doc in enumerate(documents, 1):
        text = f"{doc['title']}\n{doc['content']}"
        logger.info("[%d/%d] 임베딩 중: %s", i, len(documents), doc["id"])

        try:
            embedding = await embedding_client.get_embedding(text)
        except Exception as e:
            logger.error("임베딩 실패 (%s): %s — 건너뜀", doc["id"], e)
            continue

        batch.append({
            "id": f"vec_{doc['id']}",
            "values": embedding,
            "metadata": {
                "mysql_id": doc["id"],
                "entity_type": "knowledge",
                "domain": doc["domain"],
                "title": doc["title"],
                "source": doc.get("source", ""),
                "evidence_level": doc.get("evidence_level", ""),
                "language": "ko",
                "text_preview": doc["content"][:200],
            },
        })

        # 배치 단위로 upsert (t3.medium 메모리 절약)
        if len(batch) >= batch_size:
            logger.info("upsert 중 (%d개)...", len(batch))
            await pinecone_client.upsert(index=INDEX_NAME, vectors=batch)
            batch.clear()

    # 남은 배치 처리
    if batch:
        logger.info("upsert 중 (%d개)...", len(batch))
        await pinecone_client.upsert(index=INDEX_NAME, vectors=batch)

    logger.info("적재 완료")
    await pinecone_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinecone 지식 데이터 적재")
    parser.add_argument("--data", default="dev/data/knowledge_sample.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("데이터 파일 없음: %s", data_path)
        sys.exit(1)

    asyncio.run(ingest(data_path, args.dry_run, args.batch_size))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: dry-run 동작 확인**

```bash
python dev/scripts/ingest_knowledge_base.py --dry-run
```

Expected: 4개 문서 정보 출력 + `dry-run 완료 — 실제 저장 없음`

- [ ] **Step 4: 커밋**

```bash
git add dev/scripts/ingest_knowledge_base.py dev/data/knowledge_sample.json
git commit -m "feat: 지식 베이스 초기 적재 스크립트 + 샘플 데이터"
```

---

## Task 8: 전체 회귀 테스트

공통 코드가 기존 에이전트 테스트를 깨트리지 않는지 확인한다.

- [ ] **Step 1: DB 테스트 실행**

```bash
python -m pytest tests/db/ -v
```

Expected: `6 passed`

- [ ] **Step 2: 전체 단위 테스트 실행**

```bash
python -m pytest tests/ --ignore=tests/integration -x -q
```

Expected: 기존 테스트 전체 통과

- [ ] **Step 3: 실패 시 원인 파악**

```bash
python -m pytest tests/ --ignore=tests/integration -x -v 2>&1 | grep -E "FAILED|ERROR"
```

공통 파일(`src/db/embedding_client.py`, `src/db/factory.py`)의 import 오류가 원인일 가능성이 높다. 해당 파일 수정 후 재실행.

- [ ] **Step 4: 커밋 (수정이 있을 경우)**

```bash
git add -A
git commit -m "fix: 공통 임베딩 클라이언트 추가 후 회귀 테스트 수정"
```

---

## Task 9: 개발자 가이드 작성

**Files:**
- Create: `docs/guides/PINECONE_DEVELOPER_GUIDE.md`

- [ ] **Step 1: 가이드 파일 작성**

내용:

```markdown
# Pinecone 벡터 DB 개발자 가이드

각 에이전트 개발자가 Pinecone 클라이언트를 사용하기 위한 가이드.

---

## 1. 사전 준비

### 환경변수 (.env 파일)

```
# Pinecone (필수)
PINECONE_API_KEY=<pinecone.io에서 발급>

# AWS (필수 — Bedrock 임베딩용)
AWS_REGION=ap-northeast-2

# AWS 자격증명 (로컬 개발용 — EC2에서는 IAM 프로파일로 자동 인증)
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>

# 중요: Pinecone 직접 연결 시 반드시 local 또는 hybrid
STORAGE_MODE=local
```

> `STORAGE_MODE=proxy`(프로덕션 기본값)로 두면 Pinecone에 직접 연결하지 않고
> Backend API를 경유합니다. 개발/테스트 시 `STORAGE_MODE=local`로 설정하세요.

### 환경 검증

```bash
python dev/scripts/validate_pinecone_env.py
```

### 인덱스 생성 (최초 1회)

```bash
PINECONE_API_KEY=<key> python dev/scripts/create_pinecone_indexes.py
```

---

## 2. 개발자 CLI 명령어 모음

### 환경 확인

```bash
# 필수 환경변수 검증
python dev/scripts/validate_pinecone_env.py

# Pinecone 연결 + 인덱스 상태 확인
PINECONE_API_KEY=<key> python dev/scripts/test_pinecone_connection.py
```

### 임베딩 테스트

```bash
# Bedrock 임베딩 생성 확인 (AWS 자격증명 필요)
python dev/scripts/test_embedding.py --text "내 에이전트가 처리할 텍스트"
```

### 저장 → 검색 E2E 테스트

```bash
# expert_knowledge 인덱스에 저장하고 검색 (Knowledge Agent 개발자용)
PINECONE_API_KEY=<key> STORAGE_MODE=local \
python dev/scripts/test_vector_roundtrip.py \
    --index expert_knowledge \
    --text "인지행동치료 관련 텍스트"

# mem_podcast_episode 인덱스 (Episode Memory 개발자용)
PINECONE_API_KEY=<key> STORAGE_MODE=local \
python dev/scripts/test_vector_roundtrip.py \
    --index mem_podcast_episode \
    --text "사용자의 오늘 대화 내용"
```

### 지식 데이터 적재

```bash
# dry-run (실제 저장 없이 데이터 확인)
python dev/scripts/ingest_knowledge_base.py --dry-run

# 실제 적재
PINECONE_API_KEY=<key> STORAGE_MODE=local \
python dev/scripts/ingest_knowledge_base.py \
    --data dev/data/knowledge_sample.json
```

### Docker 컨테이너에서 실행

```bash
# 기본 형태 (dev/ 폴더 볼륨 마운트 필요)
docker compose run --rm \
    -v $(pwd)/dev:/app/dev \
    -e STORAGE_MODE=local \
    ai-server \
    python dev/scripts/<스크립트명>.py [옵션]

# 예시: 임베딩 테스트
docker compose run --rm \
    -v $(pwd)/dev:/app/dev \
    ai-server \
    python dev/scripts/test_embedding.py --text "테스트"

# 예시: E2E 테스트
docker compose run --rm \
    -v $(pwd)/dev:/app/dev \
    -e STORAGE_MODE=local \
    ai-server \
    python dev/scripts/test_vector_roundtrip.py --index expert_knowledge
```

---

## 3. 에이전트 코드에서 사용하는 방법

### 팩토리로 클라이언트 생성

```python
from src.db.factory import create_vector_client, create_embedding_client

vector_client = create_vector_client()      # STORAGE_MODE에 따라 자동 선택
embedding_client = create_embedding_client() # BedrockEmbeddingClient
```

### 에이전트 DI 패턴

```python
from src.db.base import BaseVectorClient
from src.db.embedding_client import BaseEmbeddingClient

class MyAgent(BaseAgent):
    def __init__(
        self,
        pinecone_client: BaseVectorClient | None = None,
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> None:
        super().__init__(name="my_agent")
        self.pinecone_client = pinecone_client
        self.embedding_client = embedding_client

    async def _search(self, query: str, filter_dict: dict) -> list[dict]:
        if not self.embedding_client or not self.pinecone_client:
            return []  # 클라이언트 없으면 빈 결과 (graceful)

        embedding = await self.embedding_client.get_embedding(query)
        results = await self.pinecone_client.query(
            index="<인덱스명>",
            vector=embedding,
            filter=filter_dict,
            top_k=5,
            include_metadata=True,
        )
        return results.get("matches", [])
```

### 노드 함수에서 클라이언트 주입

```python
async def my_agent_node(state: AgentState) -> dict[str, Any]:
    from config.loader import get_settings
    from src.db.factory import create_vector_client, create_embedding_client

    settings = get_settings()
    if settings.storage_mode in ("local", "hybrid"):
        vector_client = create_vector_client()
        embedding_client = create_embedding_client()
    else:
        vector_client = None
        embedding_client = None

    agent = MyAgent(
        pinecone_client=vector_client,
        embedding_client=embedding_client,
    )
    return await agent(state)
```

### 테스트에서 Mock 사용

```python
from unittest.mock import AsyncMock
import pytest

@pytest.fixture
def mock_vector_client() -> AsyncMock:
    mock = AsyncMock()
    mock.query.return_value = {
        "matches": [
            {
                "id": "vec_001",
                "score": 0.92,
                "metadata": {"domain": "CBT", "text_preview": "인지행동치료..."},
            }
        ]
    }
    return mock

@pytest.fixture
def mock_embedding_client() -> AsyncMock:
    mock = AsyncMock()
    mock.get_embedding.return_value = [0.1] * 1024
    return mock
```

---

## 4. 인덱스 정보

| 인덱스 | 담당 에이전트 | 차원 | 필터 예시 |
|--------|------------|------|---------|
| `expert_knowledge` | Knowledge Agent | 1024 | `{"domain": {"$in": ["CBT", "DBT"]}}` |
| `mem_podcast_episode` | Episode Memory | 1024 | `{"user_id": {"$eq": "user_123"}}` |

---

## 5. AWS IAM 최소 권한

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.titan-embed-text-v2:0"
    }
  ]
}
```
```

- [ ] **Step 2: 커밋**

```bash
git add docs/guides/PINECONE_DEVELOPER_GUIDE.md
git commit -m "docs: Pinecone 개발자 가이드 (CLI 명령어, Docker, DI 패턴, Mock)"
```

---

## 완료 기준 — 다른 개발자에게 전달 전 체크리스트

- [x] `python dev/scripts/validate_pinecone_env.py` 통과 (PR #64)
- [x] `PINECONE_API_KEY=<key> python dev/scripts/create_pinecone_indexes.py` — 인덱스 2개 생성 (PR #64, #67 — EC2 확인 완료)
- [x] `PINECONE_API_KEY=<key> python dev/scripts/test_pinecone_connection.py` — 전체 통과 (PR #64, #67 — EC2 확인 완료)
- [ ] `python dev/scripts/test_embedding.py` — 1024차원 벡터 반환 확인
- [ ] `python dev/scripts/test_vector_roundtrip.py --index expert-knowledge` — E2E 통과
- [ ] `python dev/scripts/ingest_knowledge_base.py --dry-run` — 4개 문서 출력
- [x] `python -m pytest tests/db/ -v` — 59개 통과 (PR #67)
- [x] `python -m pytest tests/ --ignore=tests/integration -x -q` — 기존 테스트 전체 통과 (479 passed 유지)
- [ ] `docs/guides/PINECONE_DEVELOPER_GUIDE.md` 작성 완료

---

## 이후 각 개발자 담당 작업 (이 계획 범위 밖)

| 개발자 | 파일 | 내용 | 참고 |
|--------|------|------|------|
| 개발자2 | `episode_memory.py` | DI + Pinecone `_retrieve_from_store()` 전환 | 가이드 §3 "DI 패턴" |
| 개발자1 | `knowledge.py` | `search()` 어댑터 + DI 주입 | 가이드 §3 "DI 패턴" |
| 개발자3 | `podcast_reasoning.py` | `podcast_reasoning_node` DI 주입 | 가이드 §3 "노드 함수" |
| 공동 | `ingest_knowledge_base.py` | 실제 지식 문서 적재 | 가이드 §2 "데이터 적재" |

---

*작성일: 2026-04-07 | 담당: 개발자3 (공통 인프라)*

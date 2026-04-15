"""
Knowledge Base PDF 적재 스크립트.

PDF 문서를 읽어 청킹 → Embedding → Pinecone + Backend RDB에 적재한다.
EpisodeMemoryAgent의 적재 패턴(Embedding → Pinecone upsert)을 재사용한다.

실행 환경:
    수동 실행용 스크립트. .env 또는 로컬 export로 환경변수를 주입한다.
    컨테이너(mindlog-ai-service) 런타임에서는 사용하지 않지만, deploy.yml도
    동일한 KT_CLOUD_KNOWLEDGE_PARSE_* 시크릿을 주입한다(Runtime·Ingest 공용 네이밍).

사용법:
    # YAML 설정 파일 기반 (기본)
    python scripts/ingest_knowledge.py

    # 설정 파일 경로 지정
    python scripts/ingest_knowledge.py --config scripts/ingest_config.yaml

    # 특정 파일만 적재
    python scripts/ingest_knowledge.py --pdf scripts/pdfs/cbt_guide.pdf \
        --domain mental_health --title "CBT 기법 가이드"

    # 미리보기(DB/Pinecone 저장 없이 청크만 출력)
    python scripts/ingest_knowledge.py --dry-run

필요 환경변수 (.env):
    KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT             — Upstage Document Parse API (PDF→MD)
    KT_CLOUD_KNOWLEDGE_PARSE_TOKEN                — Document Parse 인증 토큰
    KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT — KT Cloud Embedding(Passage) API
    KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_TOKEN    — Embedding(Passage) 인증 토큰
    PINECONE_API_KEY                              — Pinecone API 키
    PINECONE_INDEX_KNOWLEDGE                      — Pinecone 인덱스명 (기본: rag-suite-knowledge)
    BACKEND_API_URL                               — Backend API URL (기본: http://localhost:8080/api)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

import httpx
import yaml

# .env 로드 시도 (dotenv가 없어도 동작)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ============================================================
# 설정
# ============================================================

DEFAULT_CONFIG = "scripts/ingest_config.yaml"
DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 50


# ============================================================
# PDF 텍스트 추출
# ============================================================


async def extract_text_from_pdf(pdf_path: str, endpoint: str, token: str) -> list[dict]:
    """Upstage Document Parse API를 사용하여 PDF 텍스트를 마크다운 형태 등 구조화하여 추출한다.

    Returns:
        [{"page": 1, "text": "마크다운 전체 텍스트..."}]
    """
    if not endpoint or not token:
        print("❌ KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT 설정이 비어있습니다.")
        return []

    try:
        with open(pdf_path, "rb") as f:
            # Document Parse 가이드라인에 따른 Request Body
            files = {"document": (Path(pdf_path).name, f, "application/pdf")}
            data = {"model": "document-parse", "output_formats": '["markdown"]'}

            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"},
                    data=data,
                    files=files,
                )
                r.raise_for_status()

                result = r.json()
                md_text = result.get("content", {}).get("markdown", "")

                if md_text:
                    return [{"page": 1, "text": md_text}]
                return []
    except Exception as e:
        print(f"❌ Document Parse API 실패: {e}")
        return []


# ============================================================
# 청킹
# ============================================================


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """텍스트를 고정 크기 청크로 분할한다. EpisodeMemoryAgent._split()과 동일한 로직."""
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size - overlap
    return chunks


def make_chunk_id(source: str, page: int, idx: int) -> str:
    """Pinecone/RDB에서 사용할 chunk_id를 생성한다 (ASCII 전용)."""
    # 파일명에 한글이 있을 수 있으므로 파일명을 해싱하여 접두어로 사용
    source_hash = hashlib.md5(source.encode()).hexdigest()[:8]
    chunk_hash = hashlib.md5(f"{source}_{page}_{idx}".encode()).hexdigest()[:10]
    return f"kb_{source_hash}_p{page}_{chunk_hash}"


# ============================================================
# KT Cloud Embedding API
# ============================================================


async def embed_text(text: str, endpoint: str, token: str) -> list[float]:
    """KT Cloud Embedding API(Passage)로 텍스트를 벡터로 변환한다."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "embedding-passage", "input": text},
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return []
        return data[0].get("embedding", [])


# ============================================================
# Pinecone
# ============================================================


async def get_pinecone_host(index_name: str, api_key: str) -> str:
    """Pinecone 인덱스 호스트를 조회한다."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.pinecone.io/indexes/{index_name}",
            headers={"Api-Key": api_key},
            timeout=10.0,
        )
        r.raise_for_status()
        return r.json()["host"]


async def upsert_pinecone(
    host: str,
    api_key: str,
    chunk_id: str,
    vector: list[float],
    metadata: dict,
) -> None:
    """Pinecone에 벡터를 upsert한다."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://{host}/vectors/upsert",
            headers={"Api-Key": api_key},
            json={
                "vectors": [{"id": chunk_id, "values": vector, "metadata": metadata}],
            },
            timeout=15.0,
        )
        r.raise_for_status()


# ============================================================
# Backend RDB 저장
# ============================================================


async def save_to_backend(
    chunk_id: str,
    text: str,
    page: int,
    source: str,
    domain: str,
    title: str,
) -> None:
    """Backend RDB에 청크 데이터를 저장한다.

    BackendClient._knowledge_base_url을 사용하여 URL을 호스트 기준으로 고정한다.
    ({host}/api/internal/knowledge)
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.api.client import BackendClient

    client = BackendClient()
    try:
        await client.ingest_knowledge_chunk(
            chunk_id=chunk_id,
            title=title,
            content=text,
            page=page,
            source=source,
            domain=domain,
        )
    finally:
        await client.close()



# ============================================================
# 문서 1개 적재
# ============================================================


async def ingest_document(
    pdf_path: str,
    domain: str,
    title: str,
    chunk_size: int,
    chunk_overlap: int,
    embedding_endpoint: str,
    embedding_token: str,
    parse_endpoint: str,
    parse_token: str,
    pinecone_host: str,
    pinecone_api_key: str,
    backend_url: str,
    dry_run: bool = False,
) -> dict:
    """PDF 1개를 적재한다.

    Returns:
        {"total_chunks": int, "success": int, "failed": int}
    """
    source = Path(pdf_path).name
    print(f"\n📄 {source} ({title}) — domain: {domain}")

    # 1. Document Parse API 텍스트 추출 (Markdown)
    pages = await extract_text_from_pdf(pdf_path, parse_endpoint, parse_token)
    if not pages:
        print("  ⚠️  텍스트 추출 실패 또는 빈 PDF")
        return {"total_chunks": 0, "success": 0, "failed": 0}
    print(f"  📖 {len(pages)}개 페이지에서 텍스트 추출 완료")

    # 2. 청킹
    all_chunks: list[dict] = []
    for page_data in pages:
        chunks = chunk_text(page_data["text"], chunk_size, chunk_overlap)
        for idx, chunk_text_str in enumerate(chunks):
            chunk_id = make_chunk_id(source, page_data["page"], idx)
            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text_str,
                    "page": page_data["page"],
                }
            )
    print(f"  ✂️  {len(all_chunks)}개 청크 생성")

    if dry_run:
        print(f"\n{'='*50}\n🔍 [미리보기 모드] 생성된 청크 확인\n{'='*50}")
        for chunk in all_chunks:
            print(f"\n[Page {chunk['page']} | ID: {chunk['chunk_id'][:15]}...]")
            print(f"내용:\n{chunk['text']}")
            print("-" * 50)
        return {"total_chunks": len(all_chunks), "success": 0, "failed": 0}

    # 3. 각 청크 처리
    success = 0
    failed = 0
    for i, chunk in enumerate(all_chunks):
        try:
            # Embedding
            vector = await embed_text(chunk["text"], embedding_endpoint, embedding_token)
            if not vector:
                print(f"  ⚠️  [{i+1}/{len(all_chunks)}] 임베딩 실패 — skip")
                failed += 1
                continue

            # Pinecone upsert
            await upsert_pinecone(
                host=pinecone_host,
                api_key=pinecone_api_key,
                chunk_id=chunk["chunk_id"],
                vector=vector,
                metadata={"domain": domain},
            )

            # Backend RDB 저장
            try:
                await save_to_backend(
                    chunk_id=chunk["chunk_id"],
                    text=chunk["text"],
                    page=chunk["page"],
                    source=source,
                    domain=domain,
                    title=title,
                )
            except Exception as e:
                # Backend 미구현 시에도 Pinecone 적재는 성공으로 간주
                print(f"  ⚠️  [{i+1}] Backend 저장 실패 (Pinecone는 성공): {e}")

            success += 1

            if (i + 1) % 10 == 0 or (i + 1) == len(all_chunks):
                print(f"  ✅ [{i+1}/{len(all_chunks)}] 적재 완료")

        except Exception as e:
            print(f"  ❌ [{i+1}/{len(all_chunks)}] 실패: {e}")
            failed += 1

    return {"total_chunks": len(all_chunks), "success": success, "failed": failed}


# ============================================================
# 메인
# ============================================================


async def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge Base PDF 적재 스크립트")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="YAML 설정 파일 경로")
    parser.add_argument("--pdf", help="단일 PDF 파일 경로 (설정 파일 대신 사용)")
    parser.add_argument("--domain", help="단일 PDF의 domain")
    parser.add_argument("--title", help="단일 PDF의 title")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="미리보기 모드 (DB에 저장하지 않고 생성된 청크만 터미널에 출력)",
    )
    args = parser.parse_args()

    # 환경변수 로드
    parse_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT", "")
    parse_token = os.getenv("KT_CLOUD_KNOWLEDGE_PARSE_TOKEN", "")
    embedding_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT", "")
    embedding_token = os.getenv("KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_TOKEN", "")
    pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
    pinecone_index = os.getenv("PINECONE_INDEX_KNOWLEDGE", "rag-suite-knowledge")
    backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8080/api")

    if not parse_endpoint or not parse_token:
        print("❌ KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT / TOKEN 환경변수가 필요합니다.")
        sys.exit(1)
    if not embedding_endpoint or not embedding_token:
        print("❌ KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT / TOKEN 환경변수가 필요합니다.")
        sys.exit(1)
    if not pinecone_api_key:
        print("❌ PINECONE_API_KEY 환경변수가 필요합니다.")
        sys.exit(1)

    # Pinecone 호스트 조회
    print(f"🔍 Pinecone 인덱스 '{pinecone_index}' 호스트 조회 중...")
    try:
        pinecone_host = await get_pinecone_host(pinecone_index, pinecone_api_key)
        print(f"  ✅ 호스트: {pinecone_host}")
    except Exception as e:
        print(f"❌ Pinecone 호스트 조회 실패: {e}")
        sys.exit(1)

    # 문서 목록 결정
    if args.pdf:
        # 단일 파일 모드
        if not args.domain:
            print("❌ --pdf 사용 시 --domain이 필수입니다.")
            sys.exit(1)
        documents = [
            {
                "path": args.pdf,
                "domain": args.domain,
                "title": args.title or Path(args.pdf).stem,
            }
        ]
        chunk_size = DEFAULT_CHUNK_SIZE
        chunk_overlap = DEFAULT_CHUNK_OVERLAP
    else:
        # YAML 설정 파일 모드
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ 설정 파일이 없습니다: {config_path}")
            sys.exit(1)

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        documents = config.get("documents", [])
        chunk_size = config.get("chunk_size", DEFAULT_CHUNK_SIZE)
        chunk_overlap = config.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)

        if not documents:
            print("❌ 설정 파일에 문서가 없습니다.")
            sys.exit(1)

    # 적재 실행
    print(f"\n{'='*50}")
    print("📚 Knowledge Base 적재 시작")
    print(f"  문서 수: {len(documents)}")
    print(f"  청크 크기: {chunk_size}자, 오버랩: {chunk_overlap}자")
    print(f"  Pinecone 인덱스: {pinecone_index}")
    print(f"  Backend URL: {backend_url}")
    print(f"{'='*50}")

    total_stats = {"total_chunks": 0, "success": 0, "failed": 0}

    for doc in documents:
        path = doc.get("path", "")
        domain = doc.get("domain", "")
        title = doc.get("title", "")

        if not domain:
            print(f"\n⚠️  {path} — domain이 지정되지 않아 건너뜁니다.")
            continue

        if not Path(path).exists():
            print(f"\n❌ {path} — 파일이 존재하지 않습니다. 건너뜁니다.")
            continue

        stats = await ingest_document(
            pdf_path=path,
            domain=domain,
            title=title or Path(path).stem,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding_endpoint=embedding_endpoint,
            embedding_token=embedding_token,
            parse_endpoint=parse_endpoint,
            parse_token=parse_token,
            pinecone_host=pinecone_host,
            pinecone_api_key=pinecone_api_key,
            backend_url=backend_url,
            dry_run=args.dry_run,
        )

        total_stats["total_chunks"] += stats["total_chunks"]
        total_stats["success"] += stats["success"]
        total_stats["failed"] += stats["failed"]

    # 결과 출력
    print(f"\n{'='*50}")
    print("📊 적재 완료 요약")
    print(f"  전체 청크: {total_stats['total_chunks']}")
    print(f"  성공: {total_stats['success']}")
    print(f"  실패: {total_stats['failed']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())

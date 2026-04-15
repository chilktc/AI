#!/usr/bin/env python3
"""
Pinecone 연결 상태 + 인덱스 접근성 확인 스크립트.

API 연결 → 인덱스 존재 여부 → 더미 쿼리 순으로 헬스체크를 수행한다.

실행 (호스트):
    PINECONE_API_KEY=<key> python dev/scripts/test_pinecone_connection.py

실행 (Docker):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/test_pinecone_connection.py

옵션:
    --skip-query   더미 쿼리 생략 (인덱스 존재 여부만 확인)
"""
from __future__ import annotations

import argparse
import os
import sys


def test_api_connection(pc: object) -> bool:
    try:
        indexes = pc.list_indexes()  # type: ignore[attr-defined]
        names = [idx["name"] for idx in indexes]
        print(f"[OK] API 연결 성공 — 현재 인덱스: {names or '없음'}")
        return True
    except Exception as e:
        print(f"[ERROR] API 연결 실패: {e}")
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
            print(f"[ERROR] '{name}' 인덱스 없음")
            print(f"        → python dev/scripts/create_pinecone_indexes.py 실행 필요")
            all_ok = False
    return all_ok


def test_dummy_query(pc: object, index_name: str, dimension: int = 4096) -> bool:
    """더미 영벡터로 쿼리하여 인덱스가 정상 응답하는지 확인한다."""
    existing = {idx["name"] for idx in pc.list_indexes()}  # type: ignore[attr-defined]
    if index_name not in existing:
        print(f"[SKIP] '{index_name}' 없음 — 쿼리 생략")
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
    parser = argparse.ArgumentParser(description="Pinecone 연결 헬스체크")
    parser.add_argument("--skip-query", action="store_true", help="더미 쿼리 생략")
    args = parser.parse_args()

    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        print("[ERROR] PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    from pinecone import Pinecone

    pc = Pinecone(api_key=api_key)
    required = ["rag-suite-knowledge", "mem-podcast-episode"]
    results: list[bool] = []

    print("=== 1. API 연결 ===")
    results.append(test_api_connection(pc))

    print("\n=== 2. 인덱스 상태 ===")
    results.append(test_index_exists(pc, required))

    if not args.skip_query:
        print("\n=== 3. 더미 쿼리 ===")
        for name in required:
            results.append(test_dummy_query(pc, name))

    print()
    if all(results):
        print("헬스체크 통과 — Pinecone 정상")
    else:
        print(f"헬스체크 실패: {results.count(False)}건")
        sys.exit(1)


if __name__ == "__main__":
    main()

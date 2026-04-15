#!/usr/bin/env python3
"""
Pinecone 인덱스 생성 스크립트 (1회성 실행).

인덱스:
  rag-suite-knowledge    : Knowledge Agent — 심리상담 전문 지식 (4096차원)
  mem-podcast-episode : Episode Memory  — 사용자 에피소드 기억 (4096차원)

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

# Pinecone Serverless 지원 리전 (AWS)
CLOUD = "aws"
REGION = "us-east-1"

INDEXES = [
    {
        "name": "rag-suite-knowledge",
        "dimension": 4096,
        "metric": "cosine",
        "description": "Knowledge Agent — 심리상담 전문 지식 벡터",
    },
    {
        "name": "mem-podcast-episode",
        "dimension": 4096,
        "metric": "cosine",
        "description": "Episode Memory — 팟캐스트 에피소드 기억 벡터",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinecone 인덱스 생성")
    parser.add_argument("--force", action="store_true", help="기존 인덱스 삭제 후 재생성")
    args = parser.parse_args()

    api_key = os.environ.get("PINECONE_API_KEY", "")
    if not api_key:
        print("[ERROR] PINECONE_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=api_key)
    existing = {idx["name"] for idx in pc.list_indexes()}
    print(f"현재 인덱스: {existing or '없음'}\n")

    for cfg in INDEXES:
        name: str = cfg["name"]

        if name in existing:
            if args.force:
                print(f"[DELETE] '{name}' 삭제 중...")
                pc.delete_index(name)
                print(f"[OK]     '{name}' 삭제 완료")
            else:
                print(f"[SKIP]   '{name}' 이미 존재 — {cfg['description']}")
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

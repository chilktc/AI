#!/usr/bin/env python3
"""
Pinecone 연결에 필요한 환경변수를 검증한다.

실행 (호스트):
    python dev/scripts/validate_pinecone_env.py

실행 (Docker — dev/ 볼륨 마운트 필요):
    docker compose run --rm -v $(pwd)/dev:/app/dev ai-server \\
        python dev/scripts/validate_pinecone_env.py

STORAGE_MODE 오버라이드:
    STORAGE_MODE=local python dev/scripts/validate_pinecone_env.py
"""
from __future__ import annotations

import os
import sys

REQUIRED: list[tuple[str, str]] = [
    ("PINECONE_API_KEY", "Pinecone API 키 (pinecone.io 콘솔에서 발급)"),
]

OPTIONAL: list[tuple[str, str, str]] = [
    ("STORAGE_MODE", "저장소 모드 (Pinecone 직접 접속 시 local 또는 hybrid 필요)", "proxy"),
    ("APP_ENV", "애플리케이션 환경", "development"),
]


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

    print("\n=== 선택 환경변수 ===")
    for var, desc, default in OPTIONAL:
        val = os.getenv(var, default)
        print(f"[INFO]  {var} = {val} — {desc}")

    mode = os.getenv("STORAGE_MODE", "proxy")
    if mode not in ("local", "proxy", "hybrid"):
        print(f"\n[ERROR] STORAGE_MODE='{mode}' 잘못된 값 — local|proxy|hybrid 중 하나")
        errors.append("STORAGE_MODE")
    elif mode == "proxy":
        print("\n[WARN] STORAGE_MODE=proxy (기본값)")
        print("  Pinecone 직접 연결 테스트 시 오버라이드 필요:")
        print("  STORAGE_MODE=local python dev/scripts/validate_pinecone_env.py")

    print()
    if errors:
        print(f"검증 실패: {errors}")
        sys.exit(1)
    print("검증 통과")


if __name__ == "__main__":
    main()

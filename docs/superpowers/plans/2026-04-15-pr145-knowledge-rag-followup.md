# PR #145 (knowledge 수정) 머지 후 Follow-up 수정 계획서

**작성일**: 2026-04-15 21:30
**개정**: 2026-04-15 22:10 — 사용자 지침 반영
  - 네이밍 현상 유지 (코드가 쓰는 변수명 그대로, 이미 GitHub Secrets 등록됨)
  - 로직 수정 없음
  - 모든 수정은 **PR #145 머지 이후** follow-up PR로 진행

**대상 PR**: chilktc/AI#145 — `knowledge 수정` (base: `develop`, head: `jun-RAG`, 작성자: Ljun47/개발자1)
**PR 상태 스냅샷**: `mergeStateStatus=UNSTABLE`, `mergeable=MERGEABLE`, `reviews=[]`
  - CI: test(3.11) ✅ / test(3.12) ✅ / lint ❌ (isort) / docker-build ⏭️ SKIPPED

**작업 유형**: 계획 전용. 본 문서 작성까지. 실제 머지·코드 수정·푸시는 사용자 지시 후.

---

## 0. Executive Summary

### 0.1 사용자 지침 기반 스코프 재조정

| 이전 초안 | 개정 후 |
|----------|--------|
| 블로커 B2 "환경변수 이름 3중 불일치" → 네이밍 재설계 | ❌ 철회. **현상 유지**. Secrets 기등록. |
| "머지 전 블로커 해소 Phase 1" | ❌ 철회. **PR #145 먼저 머지** 후 단일 follow-up 트랙. |
| 로직성 개선(에러 핸들링, 임계값 외부화 등) | ❌ 본 계획 범위 외. |
| I1 테스트 파일 이동 / I2 f-string / I3 docstring / B1 isort / B3 .env.example 보강 | ✅ follow-up 대상 (로직 아님, 파일 이동/텍스트 수정만). |

### 0.2 머지 경로

```
[현재]  PR #145 (UNSTABLE: lint 실패)
          │
          ├─ (사용자 승인 시) ───────────▶  머지
          │                                  │
          │                            develop lint 빨간불 (일시)
          │                                  │
          ▼                                  ▼
  feature/analysis-rag-pr145-fix  ──PR──▶ develop 복구 (green)
   (본 계획서가 기술하는 단일 follow-up PR)
```

- **develop lint가 일시적으로 실패 상태가 되는 구간**이 존재한다는 점을 사용자·팀이 인지한 상태로 머지하는 것이 전제. follow-up PR을 즉시 뒤따라 올려 복구 시간을 최소화.
- Follow-up PR 작성 주체: 원칙적으로 개발자1(원저자). 사용자 지시 시 대리 수정 가능.

### 0.3 현재 코드 기준 **확정된** 환경변수 (현상 유지)

GitHub Secrets에 등록되어 있는 이름 그대로. `.env.example`는 이 이름들을 반영만 한다. **코드 수정 없음.**

| 사용처 | 변수명 | 용도 |
|-------|--------|------|
| `src/agents/podcast/knowledge.py` | `KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT` / `_TOKEN` | 쿼리 전처리 (KT RAG Parser) |
| `src/agents/podcast/knowledge.py` | `KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_ENDPOINT` / `_TOKEN` | 쿼리 임베딩 (embedding-query) |
| `src/agents/podcast/knowledge.py` | `KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT` / `_TOKEN` | Qwen3 TextGen |
| `scripts/ingest_knowledge.py` | `KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT` / `_TOKEN` | Upstage Document Parse (PDF→MD) |
| `scripts/ingest_knowledge.py` | `KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT` / `_TOKEN` | 문서 임베딩 (embedding-passage) |
| 공용 | `PINECONE_API_KEY`, `PINECONE_INDEX_KNOWLEDGE` | Pinecone 접속 |
| 공용 | `BACKEND_API_URL` | Backend RDB API |

> `PARSER`(쿼리 전처리) vs `PARSE`(PDF→MD)는 한 글자 차이지만 **용도가 다른 별개 API**. `.env.example` 주석에서 이를 명시만 하고 이름은 건드리지 않는다.

---

## 1. Follow-up 대상 항목 (머지 후 단일 PR로 처리)

### 1.1 🔴 필수 (develop lint 복구)

#### F1. CI lint 실패 — isort 정렬
- 파일: `tests/test_rag_synthesis.py`
- 에러: `Imports are incorrectly sorted and/or formatted.`
- 수정: isort 표준 정렬 적용. 예상 결과
  ```python
  import asyncio
  import json
  import os

  from dotenv import load_dotenv

  from src.agents.podcast.knowledge import KnowledgeAgent
  ```
- 검증: `isort --check-only tests/test_rag_synthesis.py`
- **로직 변경 없음** — import 순서만.

### 1.2 🟡 문서/파일 정리 (로직 무관)

#### F2. `.env.example` 중복 블록 제거 + 실제 사용 변수 전부 반영
- 현재 상태: PR #145 diff에서 L43-L51 블록(기존)과 신규로 추가된 L50-L60 블록이 **동일 내용 거의 복제**. 신규 블록은 코드가 실제로 읽는 `EMBEDDING_QUERY_*` / `EMBEDDING_PASSAGE_*` / `PARSE_*` 변수를 담고 있지 않음.
- 수정안 (네이밍 현상 유지, 주석만 보강):
  ```bash
  # === Knowledge Agent — KT Cloud RAG Suite ===
  # 용도별 엔드포인트/토큰이 별개. PARSER(쿼리 전처리)와 PARSE(PDF→MD)는 서로 다른 API이므로 주의.

  # Runtime 검색 경로 (src/agents/podcast/knowledge.py)
  # KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT=https://.../v1/parser          # 쿼리 전처리 (KT RAG Parser)
  # KT_CLOUD_KNOWLEDGE_PARSER_TOKEN=your_parser_token
  # KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_ENDPOINT=https://.../v1/embeddings  # embedding-query
  # KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_TOKEN=your_embedding_query_token
  # KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT=https://.../v1/chat/completions   # Qwen3-32B
  # KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN=your_textgen_token

  # 적재 스크립트 경로 (scripts/ingest_knowledge.py)
  # KT_CLOUD_KNOWLEDGE_PARSE_ENDPOINT=https://.../v1/document-parse       # Upstage Document Parse (PDF→MD)
  # KT_CLOUD_KNOWLEDGE_PARSE_TOKEN=your_docparse_token
  # KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_ENDPOINT=https://.../v1/embeddings  # embedding-passage
  # KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_TOKEN=your_embedding_passage_token

  # Pinecone 인덱스명
  # PINECONE_INDEX_KNOWLEDGE=expert-knowledge
  ```
- 완료 기준:
  - `grep -c "KT_CLOUD_KNOWLEDGE" .env.example` 결과가 중복 없이 10개(엔드포인트 5 + 토큰 5)
  - 기존 구 `KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT/TOKEN` 라인 제거
  - `PINECONE_INDEX_KNOWLEDGE` 주석은 1회만
- **로직 변경 없음** — 주석 전용 파일.

#### F3. `scripts/ingest_knowledge.py` 모듈 docstring 갱신
- 현재 L18-23이 구 변수명(`KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT`)을 안내.
- 수정: 실제 사용 변수(`KT_CLOUD_KNOWLEDGE_PARSE_*`, `KT_CLOUD_KNOWLEDGE_EMBEDDING_PASSAGE_*`)로 교체. `--dry-run` 옵션 사용법 1줄 추가.
- **로직 변경 없음** — docstring 전용.

#### F4. placeholder 없는 f-string 정리 (ruff F541)
- 파일: `scripts/ingest_knowledge.py`
- 3곳의 무의미한 f-string을 일반 문자열로 복원
  ```python
  print(f"  ⚠️  텍스트 추출 실패 또는 빈 PDF")  →  print("  ⚠️  텍스트 추출 실패 또는 빈 PDF")
  print(f"📚 Knowledge Base 적재 시작")      →  print("📚 Knowledge Base 적재 시작")
  print(f"📊 적재 완료 요약")                →  print("📊 적재 완료 요약")
  ```
- **로직 변경 없음** — 리터럴 형태만.

#### F5. `tests/test_rag_synthesis.py` 재배치 (pytest 수집 제외)
- 현재 파일은
  - `async def test_rag_flow()` 이지만 `@pytest.mark.asyncio` 없음
  - `assert` 없음 → pytest 의미 있는 검증 불가
  - 실 KT Cloud / Pinecone 네트워크 호출 시도
- **파일 이동만** 수행 (내용은 그대로):
  - `tests/test_rag_synthesis.py` → `dev/live_tests/manual_rag_check.py`
  - 상단 docstring 1줄 추가: *"수동 실행용 RAG 스모크 스크립트. pytest 비대상. 실 KT Cloud/Pinecone 호출 발생."*
- 검증: `pytest tests/ -v`가 596 passed 그대로 유지 (새 파일 수집 안 됨 확인).
- **로직 변경 없음** — 파일 경로와 docstring만.

### 1.3 🟢 메타 / 기록 (코드 손대지 않음)

| # | 항목 | 조치 |
|---|------|------|
| M1 | 리뷰 승인 0건 | 머지 전 개발자2 또는 3 리뷰 1건 획득 (CLAUDE.md 규약). 본 PR에서 확보되지 않으면 사용자 결정. |
| M2 | 브랜치명 `jun-RAG`가 `feature/analysis-*` 규약과 어긋남 | 소급 불가. 차기 PR부터 규약 준수 유도. |
| M3 | PR body 체크리스트 미체크 | 원저자가 머지 전 업데이트. |
| M4 | Backend `POST /api/internal/knowledge` 미구현 상태 | follow-up PR 본문에 "현재 Backend 저장은 404, Pinecone만 동작" 사실 명시만. |
| M5 | `scripts/pdfs/상담성과_지속성_분석.pdf` 바이너리 커밋 | 정책 재확인만. 원저자 의도 존중, 건드리지 않음. |
| M6 | `scripts/ingest_config.yaml` 기본 문서 교체 | 원저자 의도 존중, 건드리지 않음 (설정 변경은 로직 변경에 준한다고 보고 제외). |
| M7 | TextGen `Qwen/Qwen3-32B` 모델 ID | 실호출 시점에서 검증 (본 계획 범위 외). |
| M8 | `insert(0, {...})` 등 Black 스타일 회귀 | 본 follow-up에서는 `black .`을 **건드린 파일에만** 선택적 적용. 전역 재포맷은 스코프 외. |

---

## 2. 브랜치 / PR 전략

### 2.1 브랜치

| 브랜치명 | 작성자 | PR base | 리뷰 요건 |
|---------|--------|---------|----------|
| `feature/analysis-rag-pr145-fix` | 개발자1 (원저자) 권장 | `develop` | 1인 이상 |

- 대리 수정 시 브랜치명 동일, 사용자 지시 후 착수. PR 설명에 "PR #145 merge follow-up" 명시.
- CLAUDE.md 브랜치 규약(`feature/analysis-*`) 준수.

### 2.2 PR 범위 (단일 PR 유지)

| 포함 | 불포함 |
|-----|-------|
| F1 isort 정렬 | 환경변수 이름 변경 |
| F2 `.env.example` 정비 | 코드 로직 수정 (함수/에러 핸들링/임계값 등) |
| F3 docstring 갱신 | `ingest_config.yaml` 기본 문서 변경 |
| F4 f-string 정리 | Pinecone 임계값 외부화 |
| F5 테스트 파일 `dev/live_tests/`로 이동 | Backend API 구현 |
| 건드린 파일에 한정한 `black` 적용(선택) | 전역 re-format |

### 2.3 타임라인 가이드

```
T0        PR #145 머지 승인 → 머지  (develop lint 빨간불 진입)
T0 + ε    feature/analysis-rag-pr145-fix 생성, 본 계획 §1.1 ~ §1.2 커밋
T0 + α    follow-up PR open → CI green 확인 → 리뷰 요청
T0 + β    1인 리뷰 승인 → develop 머지 → lint 복구
```

- α/β는 시간 명시하지 않음(사용자 피드백: 시간 추정 지양). develop lint 빨간불 구간은 짧을수록 좋음.

---

## 3. 체크리스트 (follow-up PR 단위)

### 3.1 구현

- [ ] `feature/analysis-rag-pr145-fix` 브랜치 생성 (`develop` 기준)
- [ ] **F1** `isort tests/test_rag_synthesis.py` — *단, F5에서 이동하면 이 단계 생략 가능. 이동 후 이동된 파일에 대해 isort 실행.*
- [ ] **F5** `git mv tests/test_rag_synthesis.py dev/live_tests/manual_rag_check.py` + 상단 docstring 1줄 추가
- [ ] **F2** `.env.example` 중복 블록 제거 + §0.3의 10개 변수(주석 포함) 반영
- [ ] **F3** `scripts/ingest_knowledge.py` docstring L18-23 갱신 + `--dry-run` 사용법 1줄
- [ ] **F4** `scripts/ingest_knowledge.py` 3곳 f-string → 일반 문자열
- [ ] (선택) `black scripts/ingest_knowledge.py dev/live_tests/manual_rag_check.py .env.example` — 건드린 파일에만

### 3.2 검증

- [ ] `pytest tests/ -v` → **596 passed** 유지 (F5 이동 후 수집 수 감소 없음 확인 — 원래 해당 파일은 유효한 테스트가 아니었으므로 숫자 변동 없어야 정상)
- [ ] `isort --check-only .` → 통과
- [ ] `ruff check .` → F541 0건
- [ ] `black --check` (건드린 파일만) → 통과
- [ ] `grep -c "KT_CLOUD_KNOWLEDGE" .env.example` → 10
- [ ] `grep "KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT" .env.example` → **0건** (구 이름 제거 확인)
- [ ] follow-up PR CI 4개 잡 전부 green

### 3.3 리뷰 & 머지

- [ ] 개발자2 또는 3 리뷰 1건 이상
- [ ] 사용자 최종 "머지" 지시 후 develop 머지

---

## 4. 리스크 & 롤백

### 4.1 리스크

| 리스크 | 완화책 |
|--------|--------|
| PR #145 머지 직후 develop lint 빨간불 구간 | follow-up PR을 사전에 로컬에서 준비해두었다가 머지 직후 즉시 push/open |
| F5 파일 이동 시 pytest 수집 수가 줄어들지 않음(다른 이유로 수집 중이었다면) | `pytest --collect-only tests/ | grep rag_synthesis` 사전 확인. 원래도 유효 테스트가 아니었음(assert 0건) |
| `.env.example` 주석만 바뀌어도 GitHub Actions/EC2 배포 영향? | 주석 라인뿐이라 런타임 무영향. 배포 파이프라인이 `.env.example`를 소스로 쓰지 않음 확인 |
| 누군가가 follow-up 전에 develop에서 다른 PR을 올림 | develop lint 실패 상태라서 머지 차단될 수 있음 → 팀 공지 권장 |

### 4.2 롤백

- Follow-up PR 머지 후 이상 발생 시: 해당 merge commit만 revert(소규모 변경이라 충돌 없음 예상).
- PR #145 자체 롤백이 필요한 사태는 본 follow-up 스코프 외 — 별도 판단.

---

## 5. 본 계획서가 **명시적으로 제외**하는 항목

- 환경변수 이름 변경 (사용자 지침: 현상 유지, Secrets 기등록)
- `src/agents/podcast/knowledge.py` 로직 수정 (에러 메시지 줄바꿈 등 포함)
- `scripts/ingest_knowledge.py` 로직 수정 (Upstage API 호출 구조, chunk_id 생성 규칙, `--dry-run` 동작 등)
- `scripts/ingest_config.yaml` 기본 문서 복원 (원저자 의도 존중)
- `scripts/pdfs/상담성과_지속성_분석.pdf` 제거
- Pinecone 0.7 임계값 외부화
- Backend `POST /api/internal/knowledge` 구현
- Process 경로(`knowledge.py process()`)와 Search 경로(`search()`) 통합
- 전역 `black .` 재포맷
- TextGen 모델 ID 검증 (실호출 없이는 불가 — 백엔드 연동 테스트 재개 시점으로 연기)

---

## 6. 승인 게이트

- [ ] **게이트 1** — 사용자 승인: 본 계획서 범위(§1.1 ~ §1.3) 수락
- [ ] **게이트 2** — 사용자 지시: PR #145 머지 시점 결정 (리뷰 1건 확보 전제)
- [ ] **게이트 3** — 사용자 지시: follow-up PR 원저자 수행 vs 대리 수정
- [ ] **게이트 4** — follow-up PR CI green + 리뷰 1건 + 사용자 "머지" 지시

**게이트 1 승인 전까지 코드/문서 수정 없음. 게이트 2 지시 전까지 머지 없음. 게이트 3 지시 전까지 follow-up PR 브랜치 생성 없음. 게이트 4 지시 전까지 follow-up 머지 없음.**

---

*마지막 업데이트: 2026-04-15 22:10 (개정 1회)*

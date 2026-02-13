# 변경이력 v10~v13

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-13 ~ 2026-02-14

---

## v10 — pgvector 제거 + 플랜 파일 MySQL 통일 + CLAUDE.md 개발자 명칭 통일

> 날짜: 2026-02-13

### 배경

v9에서 PostgreSQL → MySQL 통일 작업을 수행했으나, 3가지 누락 사항이 발견되었다:

1. **pgvector 잔류**: `README.md`, `CLAUDE.md`, `docs/PROJECT_SUMMARY.md`에 "Pinecone / pgvector" 표기가 남아있었다. pgvector는 PostgreSQL 전용 벡터 확장이므로 MySQL 환경에서 사용 불가. Pinecone 단독으로 통일.
2. **플랜 파일 DB 스키마**: 플랜 파일의 "DB 스키마 참고 자료" 섹션에 PostgreSQL 문법(`JSONB`, `SERIAL`, `TIMESTAMP WITH TIME ZONE`)이 잔류. MySQL 문법(`JSON`, `INT AUTO_INCREMENT`, `DATETIME`)으로 수정.
3. **루트 CLAUDE.md Dev-A/B/C 잔류**: 루트 CLAUDE.md가 여전히 Dev-A/B/C 체계를 사용. worktree CLAUDE.md(개발자1/2/3)를 기준으로 통일.

### 변경 내용

#### 1. pgvector 제거 (3개 파일)

| 파일 | 변경 |
|------|------|
| `README.md` | `Pinecone / pgvector` → `Pinecone` |
| `CLAUDE.md` | `Pinecone / pgvector` → `Pinecone` |
| `docs/PROJECT_SUMMARY.md` | `Pinecone / pgvector` → `Pinecone` |

#### 2. 플랜 파일 DB 스키마 MySQL 변환

| PostgreSQL 문법 | MySQL 문법 |
|----------------|-----------|
| `JSONB` | `JSON` |
| `SERIAL PRIMARY KEY` | `INT AUTO_INCREMENT PRIMARY KEY` |
| `TIMESTAMP WITH TIME ZONE` | `DATETIME` |
| `DEFAULT '{}'` | `DEFAULT (JSON_OBJECT())` |
| `DEFAULT '[]'` | `DEFAULT (JSON_ARRAY())` |

#### 3. 루트 CLAUDE.md 개발자 명칭 통일 (7곳)

에이전트 테이블, 담당 영역, 브랜치 전략, AgentState 주석, 필드 접근 규칙, 워크플로우 주석에서 Dev-A/B/C → 개발자1/2/3으로 변경. 에이전트 역할 재배분도 worktree CLAUDE.md 기준으로 반영.

---

## v11 — Ollama 로컬 LLM 프로바이더 추가

> 날짜: 2026-02-13

### 배경

로컬 개발/테스트 시 API 키 없이 에이전트의 LLM 호출 및 결과 파싱을 검증할 수 있도록, Ollama를 로컬 개발 전용 프로바이더로 추가했다.

**핵심 설계**: 운영 코드와 완전 분리. Ollama 관련 코드/설정/테스트는 `dev/` 폴더에 격리, `.gitignore`로 git push에서 자동 제외, `dev/` 폴더 삭제만으로 완전 제거 가능.

### 변경 내용

#### 1. 운영 코드 변경 (최소 — 1개 파일)

| 파일 | 변경 |
|------|------|
| `src/agents/shared/llm_client.py` | `register_provider()`, `unregister_provider()` 메서드 추가 + 커스텀 프로바이더 디스패치 로직 |

커스텀 프로바이더 미등록 시 기존 Anthropic/Bedrock 코드 경로 변경 0.

#### 2. dev/ 디렉토리 (git 제외 — 로컬 전용)

| 파일 | 설명 |
|------|------|
| `dev/ollama_provider.py` | Ollama OpenAI 호환 API 프로바이더 클래스 |
| `dev/ollama_config.yaml` | 모델 매핑 (haiku/sonnet/opus → qwen2.5:7b), 서버 URL, 타임아웃 |
| `dev/ollama_bootstrap.py` | LLMClient에 Ollama 프로바이더 등록/해제 |
| `dev/test_ollama.py` | Ollama 프로바이더 단위 테스트 |
| `dev/README.md` | dev/ 폴더 빠른 시작 가이드 |

#### 3. 문서 + 설정

| 파일 | 변경 |
|------|------|
| `docs/OLLAMA_SETUP.md` | 종합 설정 가이드 (신규 생성) |
| `.gitignore` | `dev/` 추가 |
| `.env.example` | Ollama 환경변수 템플릿 추가 |

#### 4. 테스트

| 파일 | 변경 |
|------|------|
| `tests/agents/shared/test_llm_client.py` | register_provider/unregister_provider 테스트 10개 추가 (총 37개) |

### 테스트 결과

```
기존 139개 + 신규 10개(register_provider) = 149개 전체 통과
```

---

## v12 — 공용 인프라 보호 마킹 (AI 코딩 도구 수정 방지)

> 날짜: 2026-02-13

### 배경

AI 바이브코딩 도구(Claude Code, Cursor, Copilot 등)가 공용 인프라 파일을 의도치 않게 수정하는 것을 방지하기 위해, 보호 헤더 주석을 추가했다.

### 보호 레벨

| 레벨 | 표시 | 대상 | 규칙 |
|------|------|------|------|
| Level 1: 완전 보호 | `[Protected File]` | agent_state.py, message.py, contracts.py, workflow.py | 수정 금지. 3인 합의 필수 |
| Level 2: 인터페이스 보호 | `[Shared Infrastructure]` | base_agent.py, llm_client.py, prompt_loader.py, config/loader.py | 기존 public 메서드 시그니처/동작 변경 금지. 신규 추가만 허용 |

### 변경 내용

#### 1. CLAUDE.md (워크트리)

"수정 불가 영역" 섹션 바로 아래에 "공용 인프라 (Shared Infrastructure)" 섹션 추가.

#### 2. 공용 인프라 파일 헤더 주석 추가 (4개)

| 파일 | 추가된 헤더 |
|------|-----------|
| `src/agents/shared/base_agent.py` | `[Shared Infrastructure — 인터페이스 변경 금지]` + public 메서드 목록 |
| `src/agents/shared/llm_client.py` | `[Shared Infrastructure — 인터페이스 변경 금지]` + public 메서드 목록 |
| `src/agents/shared/prompt_loader.py` | `[Shared Infrastructure — 인터페이스 변경 금지]` + public 메서드 목록 |
| `config/loader.py` | `[Shared Infrastructure — 인터페이스 변경 금지]` + public 메서드 목록 |

코드 로직 변경 0 (docstring만 수정).

---

## v13 — 개별 에이전트 라이브 LLM 테스트 (멀티 프로바이더) + json.loads strict=False

> 날짜: 2026-02-13

### 배경

기존 210개 테스트는 전부 LLM 호출을 mock하여 파싱/로직/상태 전파만 검증한다. 실제 LLM을 호출했을 때 프롬프트가 의도한 JSON 구조를 반환하는지, 한국어 응답이 올바른지 확인하려면 라이브 스모크 테스트가 필요했다.

### 변경 내용

#### 1. 라이브 LLM 테스트 스위트 (`dev/live_tests/`)

운영 코드 변경 0. 전부 `dev/` 내에 생성 (`.gitignore` 적용).

| 파일 | 설명 |
|------|------|
| `dev/live_tests/__init__.py` | 패키지 초기화 |
| `dev/live_tests/conftest_live.py` | 공통 인프라 (프로바이더 셋업, 헬스체크, 출력 포맷팅) |
| `dev/live_tests/fixtures.py` | 현실적 한국어 AgentState 데이터 |
| `dev/live_tests/run_live.py` | CLI 러너 (--agent, --all, --pipeline, --provider) |
| `dev/live_tests/test_content_analyzer_live.py` | Content Analyzer 라이브 테스트 |
| `dev/live_tests/test_podcast_reasoning_live.py` | Podcast Reasoning 라이브 테스트 |
| `dev/live_tests/test_batch_validator_live.py` | Batch Validator 라이브 테스트 |
| `dev/live_tests/test_learning_live.py` | Learning Agent 라이브 테스트 |
| `dev/live_tests/test_pipeline_live.py` | 파이프라인 시뮬레이션 (TIER 1→3→비동기) |

**지원 프로바이더:** Ollama (기본), Anthropic API, AWS Bedrock

```bash
# 사용법
python3 -m dev.live_tests.run_live --agent content_analyzer
python3 -m dev.live_tests.run_live --all --provider anthropic
python3 -m dev.live_tests.run_live --pipeline
```

#### 2. json.loads strict=False (운영 코드 수정 — 1곳)

| 파일 | 변경 |
|------|------|
| `src/agents/shared/llm_client.py` | `json.loads(raw)` → `json.loads(raw, strict=False)` (2곳) |

**배경:** Ollama 로컬 모델(qwen2.5:7b 등)이 JSON 응답에 제어 문자(`\n`, `\t` 등)를 포함하여 `json.loads()`가 `JSONDecodeError`를 발생시키는 문제. `strict=False`로 제어 문자를 허용하면 파싱 성공. Anthropic API 응답에는 제어 문자가 없으므로 기존 동작에 영향 없음.

### 테스트 결과

```
운영 테스트: 210개 전체 통과 (기존과 동일)
라이브 테스트: Ollama qwen2.5:7b로 4개 에이전트 + 파이프라인 시뮬레이션 성공
```

---

## 검증 (v10~v13 전체)

```bash
python3 -m black . --check       # 통과
python3 -m ruff check .          # 통과
python3 -m isort . --check       # 통과
python3 -m mypy src/ config/     # 통과
python3 -m pytest tests/ -v      # 210개 통과
```

---

*마지막 업데이트: 2026-02-14*

# 변경이력 v14~v15

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-14

---

## v14: 문서 일관성 통합 업데이트 (v9-v13 반영)

### 커밋

`b8a1236` — feat: v10-v14 Ollama 프로바이더 + 인프라 보호 + 라이브 테스트 + 문서 통합

> v10~v13과 동일 커밋에 v14 문서 통합이 포함됨.

### 배경

v9~v13에서 LLM 듀얼 프로바이더, Ollama, 인프라 보호 마킹, 라이브 테스트 등 대규모 변경이 이뤄졌으나, 프로젝트 문서(CLAUDE.md, PROJECT_STRUCTURE.md, QUICK_START.md 등)가 아직 이전 상태를 반영하고 있었다.

### 변경 내용

| 문서 | 변경 내용 |
|------|----------|
| `CLAUDE.md` | 공용 인프라 보호 규칙 추가, 개발자 명칭 통일, 기술 스택 Pinecone 단독 반영 (+302줄) |
| `docs/PROJECT_STRUCTURE.md` | dev/ 폴더 구조, config/ 구조, 멀티 프로바이더 설명 추가 (+112줄) |
| `docs/PROJECT_SUMMARY.md` | v10~v13 변경이력 섹션 추가, 테스트 수 업데이트 (+89줄) |
| `docs/QUICK_START.md` | Ollama 빠른 시작, 멀티 프로바이더 설정 추가 (+89줄) |
| `.env.example` | Ollama/Bedrock 환경변수 예시 추가 |
| `docs/OLLAMA_SETUP.md` | Ollama 종합 설정 가이드 신규 작성 (393줄) |
| `docs/CHANGELOG_v10-v13.md` | v10~v13 변경이력 신규 작성 (196줄) |

### 코드 변경 (v14 커밋에 함께 포함)

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/podcast/content_analyzer.py` | 멀티턴 대화, complexity 기반 깊이 조절 고도화 (+169줄) |
| `src/agents/shared/base_agent.py` | `[Shared Infrastructure]` 보호 마킹 추가 (+5줄) |
| `src/agents/shared/llm_client.py` | register_provider 플러그인 시스템 + Bedrock 프로바이더 (+90줄) |
| `src/agents/shared/prompt_loader.py` | `[Shared Infrastructure]` 보호 마킹 추가 (+5줄) |
| `config/loader.py` | `get_prompt_version()`, `get_ab_test_config()` 추가 (+6줄) |

### 테스트 추가

| 파일 | 신규 테스트 수 | 내용 |
|------|-------------|------|
| `tests/agents/podcast/test_content_analyzer.py` | +39개 | 멀티턴/복잡도/엣지케이스 |
| `tests/agents/podcast/test_batch_validator.py` | +16개 | 추가 엣지케이스 |
| `tests/agents/podcast/test_podcast_reasoning.py` | +5개 | 추론 파이프라인 엣지케이스 |
| `tests/agents/shared/test_llm_client.py` | +25개 | 멀티 프로바이더, register_provider |
| `tests/agents/test_learning.py` | +3개 | 추가 엣지케이스 |

- 합계: 210개 passed (기존 122 + 신규 88)

---

## v15: dev/ 폴더 git 추적 추가 및 push

### 커밋

| 해시 | 메시지 |
|------|--------|
| `f00dd20` | feat: dev/ 폴더 git 추적 추가 (Ollama 프로바이더 + 라이브 테스트) |
| `282a5ad` | fix: dev/ 라이브 테스트 lint 에러 수정 |

### 배경

`dev/` 폴더가 `.gitignore`에 의해 전체 제외되어 있어 다른 개발자와 공유가 불가능했다. Ollama 프로바이더(4개 파일)와 라이브 LLM 테스트(9개 파일)를 git 추적에 포함시켜 팀 전체가 활용할 수 있게 한다.

### 변경 내용

#### 1. `.gitignore` 수정

```diff
-# 로컬 개발 전용 (Ollama 등 — 운영 배포 시 제외)
-dev/
+# 로컬 개발 전용 — __pycache__만 제외 (소스는 git 추적)
+dev/__pycache__/
+dev/**/__pycache__/
```

#### 2. dev/ 내부 gitignore 문구 업데이트 (6개 파일)

| 파일 | 변경 |
|------|------|
| `dev/README.md` | `.gitignore에 의해 git push에서 자동 제외` → `로컬 개발 전용` |
| `dev/live_tests/README.md` | `.gitignore에 의해 git push에서 자동 제외` → `로컬 개발 전용 테스트` |
| `dev/ollama_provider.py` | `.gitignore에 의해 git push에서 제외` → `운영 배포 시 제거 가능` |
| `dev/ollama_bootstrap.py` | `.gitignore에 의해 git push에서 제외` → `운영 배포 시 제거 가능` |
| `dev/ollama_config.yaml` | `.gitignore에 의해 git 추적에서 제외` → `운영 배포 시 제거 가능` |
| `dev/test_ollama.py` | `.gitignore에 의해 git push에서 제외` → `운영 배포 시 제거 가능` |

#### 3. docs/OLLAMA_SETUP.md gitignore 문구 업데이트 (5곳)

- `.gitignore로 git push에서 자동 제외` → `운영 배포 시 삭제로 완전 제거`
- `dev/ ← .gitignore (git push 제외)` → `dev/ ← 로컬 개발 전용 (운영 배포 시 삭제)`
- `dev/ 폴더는 .gitignore에 의해 git에서 추적되지 않는다` → `dev/ 폴더는 로컬 개발 전용이다. 프로젝트 클론 시 자동으로 포함된다`
- `.env 파일에 추가 (이미 .gitignore에 포함)` → `.env 파일에 추가 (.env는 .gitignore에 포함)`
- `dev/ 폴더는 .gitignore에 의해 git push에서 자동 제외된다` → `dev/ 폴더는 운영 배포 시 삭제로 완전히 제거할 수 있다`

#### 4. lint 에러 수정 (커밋 `282a5ad`)

| 파일 | 수정 내용 |
|------|----------|
| `dev/live_tests/run_live.py` | 미사용 `sys` import 제거 + E501 줄 길이 수정 |
| `dev/live_tests/test_batch_validator_live.py` | E501 줄 길이 수정 (변수 추출) |
| `dev/live_tests/test_pipeline_live.py` | 미사용 `json` import 제거 + F541 f-string 수정 |

### git 추적 추가된 파일 (15개)

**Ollama 프로바이더 (5개)**
- `dev/README.md` (71줄)
- `dev/ollama_provider.py` (134줄)
- `dev/ollama_config.yaml` (25줄)
- `dev/ollama_bootstrap.py` (42줄)
- `dev/test_ollama.py` (362줄)

**라이브 LLM 테스트 (10개)**
- `dev/live_tests/__init__.py` (11줄)
- `dev/live_tests/README.md` (318줄)
- `dev/live_tests/conftest_live.py` (288줄)
- `dev/live_tests/fixtures.py` (318줄)
- `dev/live_tests/run_live.py` (219줄)
- `dev/live_tests/test_content_analyzer_live.py` (130줄)
- `dev/live_tests/test_podcast_reasoning_live.py` (176줄)
- `dev/live_tests/test_batch_validator_live.py` (157줄)
- `dev/live_tests/test_learning_live.py` (132줄)
- `dev/live_tests/test_pipeline_live.py` (259줄)

### 검증

- `__pycache__` git 미포함 확인 ✅
- 운영 테스트 210개 passed ✅
- `black --check` ✅ `ruff check` ✅ `isort --check` ✅ `mypy` ✅

---

*마지막 업데이트: 2026-02-14*

# 동시성 격리 리팩토링 커밋 + 로컬/원격 정리 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미커밋된 v27 동시성 격리 리팩토링을 새 브랜치에 커밋·푸시하고, 로컬/원격을 develop 기준으로 동기화한 뒤 불필요한 브랜치·워크트리를 정리한다.

**Architecture:** 현재 `feature/deploy-fix-v26` 위의 미커밋 변경사항을 stash → develop 최신으로 이동 → 새 브랜치 생성 → stash pop → 커밋·푸시 → 정리.

**Tech Stack:** git, gh CLI

---

## 현재 상태 요약

### 워크트리

| 경로 | 브랜치 | 미커밋 변경 | 원격 |
|------|--------|-----------|------|
| `.` (메인) | `feature/deploy-fix-v26` | 21개 수정 + 8개 untracked | **gone** (PR#36으로 develop 머지 완료) |
| `.claude/worktrees/code-audit` | `feature/code-audit` | 없음 | **gone** (PR#31로 머지 완료) |

### 로컬 브랜치

| 브랜치 | 원격 추적 | 상태 | 처리 |
|--------|----------|------|------|
| `main` | `origin/main` | 동기화됨 | **유지** |
| `develop` | `origin/develop` | 4커밋 뒤처짐 | **pull 후 유지** |
| `feature/deploy-fix-v26` ★현재 | gone | 미커밋 변경 있음 | stash 후 **삭제** |
| `feature/code-audit` | gone | 워크트리 연결됨 | 워크트리 제거 후 **삭제** |
| `operation` | `origin/operation` | 동기화됨 | **삭제** |

### stash

| 항목 | 내용 | 처리 |
|------|------|------|
| `stash@{0}` | `test_e2e_bedrock.py local fix` | **드롭** (PR#34에서 삭제된 파일 관련) |

### 커밋 제외 대상 (untracked)

| 파일/디렉토리 | 이유 | 처리 |
|-------------|------|------|
| `.mcp.json` | 로컬 MCP 설정 | `.gitignore`에 추가, 커밋하지 않음 |
| `docs/*/CLAUDE.md` (4개) | Claude Code 로컬 설정 | `.gitignore`에 추가, 커밋하지 않음 |
| `발표_자료/` | 이미 저장소 외부 자료 | 커밋하지 않음 |
| `docs/superpowers/` | 계획/설계 문서 | 커밋에 **포함** |

---

## 실행 계획

### Task 1: 미커밋 변경사항 보존 (stash)

**Files:**
- 없음 (git 조작만)

- [ ] **Step 1: 현재 변경사항을 stash에 저장**

```bash
git stash push -u -m "v27-concurrency-isolation-refactor"
```

> `-u`: untracked 파일도 포함. `.mcp.json`, `docs/superpowers/`, `CLAUDE.md` 서브디렉토리, `발표_자료/`, `CHANGELOG_v27.md` 모두 stash에 보존.

- [ ] **Step 2: working tree가 깨끗한지 확인**

Run: `git status`
Expected: `nothing to commit, working tree clean`

---

### Task 2: code-audit 워크트리 제거

**Files:**
- 없음 (git 조작만)

- [ ] **Step 1: 워크트리 제거**

```bash
git worktree remove .claude/worktrees/code-audit
```

- [ ] **Step 2: feature/code-audit 브랜치 삭제**

```bash
git branch -D feature/code-audit
```

- [ ] **Step 3: 워크트리 목록 확인**

Run: `git worktree list`
Expected: 메인 워크트리 1개만 표시

---

### Task 3: develop 브랜치로 이동 + 최신화

**Files:**
- 없음 (git 조작만)

- [ ] **Step 1: develop으로 checkout**

```bash
git checkout develop
```

- [ ] **Step 2: develop 최신화**

```bash
git pull origin develop
```

Expected: `3f4ac8e`까지 fast-forward

- [ ] **Step 3: feature/deploy-fix-v26 브랜치 삭제**

```bash
git branch -D feature/deploy-fix-v26
```

- [ ] **Step 4: operation 브랜치 삭제**

```bash
git branch -D operation
```

---

### Task 4: 리팩토링 브랜치 생성 + 변경사항 복원

**Files:**
- 없음 (git 조작만)

- [ ] **Step 1: 새 브랜치 생성 (develop 기반)**

```bash
git checkout -b refactor/concurrency-isolation
```

> 브랜치명: `refactor/concurrency-isolation` — 동시성 격리 리팩토링 내용을 반영.

- [ ] **Step 2: stash에서 v27 변경사항 복원**

```bash
git stash pop "stash@{0}"
```

> stash@{0}은 Task 1에서 넣은 `v27-concurrency-isolation-refactor`. 기존 stash@{0}이었던 `test_e2e_bedrock.py local fix`는 stash@{1}로 밀려남.

- [ ] **Step 3: 복원 확인**

Run: `git status --short`
Expected: 21개 수정 파일 + 8개 untracked 파일 복원

---

### Task 5: 커밋 대상 분류 + .gitignore 업데이트

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore에 로컬 전용 파일 추가**

`.gitignore`에 아래 항목 추가:

```
# Claude Code 로컬 설정
.mcp.json
docs/**/CLAUDE.md
!docs/architecture/CLAUDE.md  # 필요시 제외 가능

# 발표 자료 (저장소 외부)
발표_자료/
```

> `docs/**/CLAUDE.md` 4개 파일과 `.mcp.json`, `발표_자료/`를 추적 제외.
> 루트 `CLAUDE.md`는 이미 추적 중이므로 영향 없음.

- [ ] **Step 2: .gitignore 확인**

Run: `git status --short`
Expected: `.mcp.json`, `docs/*/CLAUDE.md`, `발표_자료/`가 untracked 목록에서 사라짐. `docs/superpowers/`, `docs/changelog/CHANGELOG_v27.md`는 유지.

---

### Task 6: 커밋 (Co-Authored-By 제외)

**Files:**
- 커밋 대상: 수정 21개 + 신규 (`docs/superpowers/`, `docs/changelog/CHANGELOG_v27.md`, `.gitignore`)

- [ ] **Step 1: 소스 코드 + 테스트 커밋**

```bash
git add \
  src/agents/podcast/batch_validator.py \
  src/agents/podcast/content_analyzer.py \
  src/agents/podcast/emotion.py \
  src/agents/podcast/podcast_reasoning.py \
  src/agents/podcast/safety.py \
  src/agents/podcast/visualization.py \
  src/agents/shared/base_agent.py \
  src/agents/shared/learning.py \
  src/agents/shared/llm_client.py \
  src/graph/workflow.py \
  tests/graph/test_e2e_mock_pipeline.py

git commit -m "$(cat <<'EOF'
refactor: 에이전트 싱글톤 제거 → 요청별 인스턴스 생성 패턴 (동시성 격리)

- 10개 에이전트 노드 함수에서 모듈 레벨 싱글톤 제거, 요청마다 새 인스턴스 생성
- BaseAgent: _current_ab_variant 인스턴스 변수 제거 → ContextVar 전용
- LLMClient: last_usage 복사본 반환으로 내부 상태 보호
- workflow.py: reset_agents() 함수 제거 (불필요)
- 테스트: mock 대상을 싱글톤 메서드 → 노드 함수로 변경
EOF
)"
```

- [ ] **Step 2: 문서 + 인프라 커밋**

```bash
git add \
  .gitignore \
  CLAUDE.md \
  docker-compose.yml \
  docs/INDEX.md \
  docs/changelog/INDEX.md \
  docs/changelog/CHANGELOG_v27.md \
  docs/getting-started/QUICK_START.md \
  docs/guides/AGENT_DEV_GUIDE.md \
  docs/guides/E2E_TEST_GUIDE.md \
  docs/guides/INFRA_DEPLOYMENT_GUIDE.md \
  docs/guides/INFRA_ONBOARDING_GUIDE.md \
  docs/guides/INFRA_ZONE_ASSIGNMENT.md \
  docs/superpowers/

git commit -m "$(cat <<'EOF'
docs: v27 동시성 격리 리팩토링 문서 업데이트 + 아카이브 정리

- AGENT_DEV_GUIDE: 싱글톤 → 요청별 인스턴스 패턴으로 가이드 전환
- E2E_TEST_GUIDE: reset_agents() 제거 반영, 프로바이더 전환 방법 업데이트
- QUICK_START: 노드 함수 예시 + 환경변수 설명 보강
- INFRA 가이드 3개: 아카이브 경고 배너 추가
- CHANGELOG_v27, INDEX 업데이트
- docker-compose.yml: deprecated version 키 제거
- .gitignore: 로컬 전용 파일 제외 추가
EOF
)"
```

- [ ] **Step 3: 커밋 이력 확인**

Run: `git log --oneline -3`
Expected: 2개 커밋 (refactor + docs), Co-Authored-By 없음

---

### Task 7: 푸시 + develop PR 생성

**Files:**
- 없음 (git/gh 조작만)

- [ ] **Step 1: 원격에 브랜치 푸시**

```bash
git push -u origin refactor/concurrency-isolation
```

- [ ] **Step 2: develop 대상 PR 생성**

```bash
gh pr create \
  --base develop \
  --title "refactor: 에이전트 동시성 격리 리팩토링 (v27)" \
  --body "$(cat <<'EOF'
## Summary
- 10개 에이전트의 모듈 레벨 싱글톤을 제거하고 노드 함수 내 요청별 인스턴스 생성 패턴으로 전환
- BaseAgent/LLMClient 동시성 안전성 강화
- 관련 문서 및 테스트 업데이트

## Test plan
- [ ] `pytest tests/graph/test_e2e_mock_pipeline.py -v` 통과 확인
- [ ] 팟캐스트 파이프라인 E2E 실행 확인
EOF
)"
```

---

### Task 8: 로컬 최종 정리

**Files:**
- 없음 (git 조작만)

- [ ] **Step 1: stash 정리 (오래된 stash 드롭)**

```bash
git stash drop "stash@{0}"
```

> Task 1의 v27 stash는 pop으로 이미 제거됨. 남은 것은 기존 `test_e2e_bedrock.py local fix` (PR#34에서 삭제된 파일 관련, 더 이상 필요 없음).

- [ ] **Step 2: main 브랜치 최신화**

```bash
git checkout main && git pull origin main
```

- [ ] **Step 3: develop으로 복귀**

```bash
git checkout develop
```

- [ ] **Step 4: 최종 상태 확인**

```bash
git branch -a -vv
git worktree list
git stash list
```

Expected:
- 로컬 브랜치: `main`, `develop`, `refactor/concurrency-isolation` (PR 머지 후 삭제 가능)
- 워크트리: 메인 1개만
- stash: 비어 있음
- 원격: `origin/main`, `origin/develop`, `origin/refactor/concurrency-isolation`

---

## 최종 결과 목표

```
로컬 브랜치:
  main                          ← origin/main (동기화)
  develop                       ← origin/develop (동기화, 현재 브랜치)
  refactor/concurrency-isolation ← origin/refactor/concurrency-isolation (PR 대기)

워크트리: 메인 1개만
stash: 비어 있음
삭제된 브랜치: feature/deploy-fix-v26, feature/code-audit, operation
```

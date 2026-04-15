# Git 히스토리 정리 계획 v2 — 브랜치 정리 + main 동기화

> **작성일**: 2026-04-15 17:30  
> **관련 Plan**: Plan #28 (민감정보 제거, 3인 합의 대기 중) / 신규 Plan #52  
> **전제**: Plan #28(git-filter-repo 민감정보 제거)은 별도로 진행. 본 계획은 브랜치 정리 + main 동기화에 집중.

---

## 현황 진단 (2026-04-15 17:30 기준)

### 원격 브랜치 (5개)

| 브랜치 | 상태 | 마지막 PR | 삭제 가능 |
|--------|------|----------|----------|
| `origin/develop` | ✅ 운영 중 | — | ❌ |
| `origin/main` | ✅ 운영 중 | — | ❌ |
| `origin/feature/analysis-crisis-output-fix` | 스쿼시 머지 완료 (#159) | #159 | ✅ |
| `origin/feature/analysis-knowledge-threshold-tune` | 스쿼시 머지 완료 (#155) | #155 | ✅ |
| `origin/jun-RAG` | 스쿼시 머지 완료 (#145~#158) | #158 | ✅ |

### 로컬 브랜치 (3개)

| 브랜치 | 상태 | 비고 | 삭제 가능 |
|--------|------|------|----------|
| `develop` | ✅ 운영 중 | — | ❌ |
| `main` | ✅ 운영 중 | — | ❌ |
| `feature/validation-knowledge-reasoning-injection` | PR 없음, 원격 미존재 | 작업 중단 가능성 | 확인 후 삭제 |

### main ↔ develop 간격

```
develop이 main보다 앞선 커밋: 453개
main이 develop보다 앞선 커밋: 0개
```

develop이 main보다 완전히 앞선 상태 (main은 develop의 조상). 즉 develop → main 방향 fast-forward merge가 가능하다.

---

## 정리 항목

### Phase A — 원격 stale 브랜치 삭제 (즉시 실행 가능, 합의 불필요)

머지 완료된 3개 원격 브랜치를 삭제한다. 스쿼시 머지로 develop에 이미 반영됨.

```bash
git push origin --delete feature/analysis-crisis-output-fix
git push origin --delete feature/analysis-knowledge-threshold-tune
git push origin --delete jun-RAG
```

**영향 없음**: develop에 스쿼시 커밋으로 반영 완료. 브랜치 삭제 시 커밋 이력 유실 없음.

### Phase B — 로컬 브랜치 정리 (개발자 확인 후)

`feature/validation-knowledge-reasoning-injection` 로컬 브랜치:
- 원격(origin)에 해당 브랜치 없음
- 연결된 PR 없음 (gh pr list 조회 결과 없음)
- 작업 내용 확인 필요

```bash
# 1. 내용 확인
git log --oneline develop..feature/validation-knowledge-reasoning-injection

# 2. 보존 불필요 확인 시 삭제
git branch -D feature/validation-knowledge-reasoning-injection
```

### Phase C — main ← develop 동기화 (3인 합의 필요)

develop이 main보다 453 커밋 앞선 상태. fast-forward merge가 가능하므로 충돌 없음.

**방법 A: Fast-forward merge (권장)**

```bash
git checkout main
git merge --ff-only origin/develop
git push origin main
```

**방법 B: PR을 통한 머지 (심리적 안전장치)**

```bash
gh pr create --base main --head develop \
  --title "chore: develop → main 동기화 (PR #145~#159 반영)" \
  --body "develop에 머지된 PR #145~#159 내용을 main에 반영한다. fast-forward merge."
```

**주의사항**:
- CLAUDE.md 규칙: "main에 머지할 때 3명 전원 승인 필수"
- AWS CD 파이프라인이 main push에 반응할 경우 자동 배포 발생 가능 → AWS가 열려야 정상 배포 가능 (현재 닫힌 상태)
- 배포 전 `config/settings.yaml` 환경변수 최신화 확인 필요

### Phase D — jun-RAG 브랜치 전략 개선 (문서화)

**현황 문제**: `jun-RAG` 브랜치가 #145~#158에 걸쳐 장기 재사용됨. 개발 과정에서 develop의 변경사항이 jun-RAG에 쌓이면서:
- 스쿼시 머지 후 develop↔jun-RAG 히스토리 분기 발생
- 충돌 해결 시 어떤 커밋이 고유한지 파악이 어려움

**권장 개선**: 각 PR마다 별도 feature 브랜치 사용. `feature/analysis-*` 네이밍 규칙 준수.

---

## 실행 우선순위

| 우선순위 | Phase | 합의 | 즉시 실행 | 비고 |
|---------|-------|------|---------|------|
| 1 | A — 원격 stale 브랜치 삭제 | 불필요 | ✅ | 즉시 가능 |
| 2 | B — 로컬 브랜치 정리 | 작업 담당자 확인 | ✅ | 내용 확인 후 |
| 3 | C — main ← develop 동기화 | 3인 합의 필수 | ❌ | AWS 오픈 후 |
| 4 | Plan #28 — 민감정보 git-filter-repo | 3인 합의 + 전원 re-clone | ❌ | 별도 계획 유지 |

---

## Phase A 실행 명령 (즉시)

```bash
# 원격 stale 브랜치 삭제 (1회 실행)
git push origin --delete feature/analysis-crisis-output-fix
git push origin --delete feature/analysis-knowledge-threshold-tune
git push origin --delete jun-RAG

# 로컬 캐시 정리
git remote prune origin
git fetch --prune
```

---

*작성: 2026-04-15 17:30*

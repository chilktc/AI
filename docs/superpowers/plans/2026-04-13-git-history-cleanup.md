# Git History 민감정보 제거 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** git history에 잔존하는 KT Cloud API 토큰 및 기타 민감정보를 `git-filter-repo`로 완전 제거한다.

**Architecture:** `git filter-repo --replace-text` 를 클린 미러 클론에서 실행 → force-push → 전원 re-clone

**Tech Stack:** git-filter-repo (pip 설치), GitHub (force-push, 브랜치 보호 일시 해제)

> ⚠️ **3인 합의 필요**: 이 작업은 **force-push로 전체 히스토리가 재작성**된다.
> 실행 전 팀원 전원이 작업 중인 브랜치를 push하고 동의해야 한다.
> 합의 없이 단독 실행 금지.

---

## 제거 대상 민감정보

| # | 유형 | 값 | 최초 노출 커밋 | 현재 코드 상태 |
|---|------|-----|--------------|--------------|
| 1 | KT Cloud API 토큰 | `kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e` | `1d099b6` | 제거됨 (환경변수로 교체) |
| 2 | KT Cloud 엔드포인트 | `https://no753ozr79oq.proxy.aifoundry.ktcloud.com/v1/embeddings` | `1d099b6` | 제거됨 (환경변수로 교체) |
| 3 | ALB 도메인 | `t7-mindlog-prod-alb-1834710625.ap-northeast-2.elb.amazonaws.com` | 과거 커밋 | 제거됨 |
| 4 | 내부 IP | `10.7.10.20` | 과거 커밋 | 제거됨 |
| 5 | DB 비밀번호 | `mindlog_pass` | 과거 커밋 | 제거됨 |
| 6 | DB 루트 비밀번호 | `mindlog_root` | 과거 커밋 | 제거됨 |
| 7 | Neo4j DB 비밀번호 | `mindlog_neo4j` | 과거 커밋 | 제거됨 |

> **중요**: 코드에서 제거했어도 git history에는 영구적으로 남아있다.
> `git show 1d099b6` 으로 현재도 토큰이 조회됨을 확인 완료.

---

## 사전 조건 체크리스트

실행 전 **3인 모두** 완료 확인:

- [ ] 팀원 전원 현재 작업 브랜치 push 완료
- [ ] 팀원 전원 동의 서명 (Slack 또는 PR 코멘트)
- [ ] GitHub main 브랜치 보호 규칙 일시 해제 확인 (현재 규칙 없음 — 2026-04-13 확인)
- [ ] KT Cloud 토큰 로테이션 완료 (기존 토큰 폐기 — 이미 노출된 것으로 간주)
- [ ] 작업 담당자 로컬에 `git-filter-repo` 설치 확인

---

## Task 1: 사전 준비

**Files:**
- Read: `docs/SECURITY_REMEDIATION_TRACKER.md`
- Create: `expressions.txt` (임시, 실행 후 삭제)

- [ ] **Step 1: git-filter-repo 설치 확인 및 설치**

  ```bash
  pip install git-filter-repo
  git filter-repo --version
  # Expected: git-filter-repo 2.x.x
  ```

- [ ] **Step 2: 전체 커밋 수 및 히스토리 확인**

  ```bash
  git log --all --oneline | wc -l
  # 현재: 405 커밋 (2026-04-13 기준)
  ```

- [ ] **Step 3: 로컬 백업 번들 생성**

  ```bash
  cd <레포 상위 디렉토리>
  git bundle create mind-log-backup-$(date +%Y%m%d).bundle --all
  ls -lh mind-log-backup-*.bundle
  # Expected: 파일 크기 > 0
  ```

- [ ] **Step 4: 제거 패턴 파일 생성 (expressions.txt)**

  작업 디렉토리(레포 외부)에 생성:
  ```bash
  cat > /tmp/expressions.txt << 'EOF'
  kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e==>***KT_TOKEN_REMOVED***
  no753ozr79oq.proxy.aifoundry.ktcloud.com==>KT_ENDPOINT_REMOVED
  t7-mindlog-prod-alb-1834710625.ap-northeast-2.elb.amazonaws.com==>ALB_DOMAIN_REMOVED
  10.7.10.20==>INTERNAL_IP_REMOVED
  mindlog_pass==>DB_PASS_REMOVED
  mindlog_root==>DB_ROOT_REMOVED
  mindlog_neo4j==>DB_NEO4J_REMOVED
  EOF
  cat /tmp/expressions.txt
  ```

  > ⚠️ `expressions.txt`를 레포 내부에 저장하지 말 것 — git history에 기록됨

- [ ] **Step 5: 드라이런으로 영향 범위 확인**

  ```bash
  # 현재 레포에서 각 패턴이 몇 개의 커밋에 있는지 확인
  git log --all -S "kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e" --oneline
  git log --all -S "mindlog_pass" --oneline
  git log --all -S "10.7.10.20" --oneline
  ```

  각 패턴에 해당하는 커밋 수 기록. 예상: 각 1~5개.

---

## Task 2: 미러 클론에서 filter-repo 실행

> **별도 클린 클론에서 실행** — 기존 작업 디렉토리 오염 방지

- [ ] **Step 1: 미러 클론 생성**

  ```bash
  cd /tmp
  git clone --mirror https://github.com/chilktc/AI mind-log-mirror
  cd mind-log-mirror
  ls
  # Expected: HEAD, config, objects/, refs/ 등 bare repo 구조
  ```

- [ ] **Step 2: filter-repo 실행**

  ```bash
  cd /tmp/mind-log-mirror
  git filter-repo --replace-text /tmp/expressions.txt
  ```

  Expected: 진행 상황 출력, 완료 메시지.
  > 실행 시간: 405커밋 기준 수 분 소요 예상

- [ ] **Step 3: 결과 검증 — 패턴 잔존 여부 확인**

  ```bash
  cd /tmp/mind-log-mirror
  # 각 패턴이 완전히 제거되었는지 확인
  git log --all -S "kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e" --oneline
  # Expected: 출력 없음 (0 커밋)

  git log --all -S "mindlog_pass" --oneline
  # Expected: 출력 없음

  git log --all -S "10.7.10.20" --oneline
  # Expected: 출력 없음
  ```

  패턴이 남아있으면 **Step 2로 돌아가서 재실행**.

- [ ] **Step 4: 최신 커밋 내용 무결성 확인**

  ```bash
  cd /tmp/mind-log-mirror
  # main, develop 최신 커밋의 핵심 파일이 올바른지 확인
  git show HEAD:src/api/client.py | grep -c "session_id"
  # Expected: > 0 (파일 내용 정상)

  git log --oneline -5
  # Expected: 커밋 메시지가 정상 (영향받은 커밋의 해시는 변경됨)
  ```

---

## Task 3: GitHub force-push

> ⚠️ **이 단계는 되돌릴 수 없다.** Task 2 검증 완료 후에만 실행.

- [ ] **Step 1: 모든 브랜치 및 태그 force-push**

  ```bash
  cd /tmp/mind-log-mirror
  git remote set-url origin https://github.com/chilktc/AI
  git push --force --all
  git push --force --tags
  ```

  Expected:
  ```
  + <old_hash>...<new_hash> main -> main (forced update)
  + <old_hash>...<new_hash> develop -> develop (forced update)
  ...
  ```

- [ ] **Step 2: GitHub에서 히스토리 정리 요청 (캐시 제거)**

  GitHub은 force-push 후에도 일부 데이터를 캐싱할 수 있다.
  GitHub Support에 "secret scanning / git history purge" 요청 또는
  GitHub Settings → Code security → Secret scanning 활성화로 자동 감지 확인.

  ```
  GitHub → chilktc/AI → Settings → Security & analysis
  → Secret scanning: Enable
  ```

---

## Task 4: 전원 re-clone 및 재동기화

> force-push 후 기존 로컬 클론은 모두 **오염된 상태**이다.
> 기존 디렉토리를 사용하지 말고 반드시 re-clone.

- [ ] **Step 1: 기존 로컬 클론 백업 후 삭제**

  각 팀원 실행:
  ```bash
  # 기존 작업 디렉토리 백업
  cp -r /path/to/mind-log /path/to/mind-log-old-backup

  # 기존 디렉토리 삭제 (re-clone 전)
  rm -rf /path/to/mind-log
  ```

- [ ] **Step 2: 신규 클론**

  ```bash
  git clone https://github.com/chilktc/AI mind-log
  cd mind-log
  git checkout develop
  ```

- [ ] **Step 3: 기존 작업 브랜치 복원 (필요 시)**

  force-push로 원격 브랜치도 재작성되었으므로, 로컬에서 사용 중이던 브랜치도 원격에서 새로 체크아웃:
  ```bash
  git fetch --all
  git checkout -b feature/my-branch origin/feature/my-branch
  ```

  > ⚠️ 기존 로컬 브랜치에서 cherry-pick하지 말 것 — 오염된 커밋이 다시 들어올 수 있음

- [ ] **Step 4: 검증 — 신규 클론에서 패턴 잔존 없음 확인**

  ```bash
  cd mind-log
  git log --all -S "kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e" --oneline
  # Expected: 출력 없음
  ```

- [ ] **Step 5: .git/objects 정리 (선택, 완전 제거용)**

  filter-repo는 자동으로 reflog 정리를 수행하지만, 명시적 정리:
  ```bash
  cd mind-log
  git reflog expire --expire=now --all
  git gc --prune=now --aggressive
  ```

---

## Task 5: 후속 조치 및 문서 업데이트

- [ ] **Step 1: SECURITY_REMEDIATION_TRACKER.md Section 5 완료 처리**

  파일: `docs/SECURITY_REMEDIATION_TRACKER.md`
  Section 5의 체크박스 완료 처리 및 완료 날짜 기재.

- [ ] **Step 2: PLAN_INDEX.md 업데이트**

  파일: `docs/superpowers/PLAN_INDEX.md`
  #16 항목 상태를 `❌ 미완료` → `✅ 완료` 로 변경.

- [ ] **Step 3: pre-commit hook 도입 (선택)**

  향후 재발 방지:
  ```bash
  pip install detect-secrets
  detect-secrets scan > .secrets.baseline
  ```

  `.pre-commit-config.yaml` 추가:
  ```yaml
  repos:
    - repo: https://github.com/Yelp/detect-secrets
      rev: v1.4.0
      hooks:
        - id: detect-secrets
          args: ['--baseline', '.secrets.baseline']
  ```

  ```bash
  pre-commit install
  git add .secrets.baseline .pre-commit-config.yaml
  git commit -m "security: detect-secrets pre-commit hook 도입"
  ```

- [ ] **Step 4: 커밋 (문서 업데이트)**

  ```bash
  git add docs/SECURITY_REMEDIATION_TRACKER.md docs/superpowers/PLAN_INDEX.md
  git commit -m "docs: git history 정리 완료 — SECURITY_REMEDIATION_TRACKER 업데이트"
  ```

---

## 롤백 플랜

filter-repo 실행 후 문제 발생 시:

```bash
# 백업 번들에서 복원
cd /tmp
git clone mind-log-backup-YYYYMMDD.bundle mind-log-restored
cd mind-log-restored
git remote add origin https://github.com/chilktc/AI
git push --force --all  # 원복
git push --force --tags
```

---

## 실행 후 확인 체크리스트

```
[ ] git log --all -S "kt_cctc..." 결과 없음
[ ] git log --all -S "mindlog_pass" 결과 없음
[ ] git log --all -S "10.7.10.20" 결과 없음
[ ] 전원 re-clone 완료
[ ] develop/main 브랜치 최신 커밋 내용 정상 동작 확인
[ ] CI/CD 파이프라인 정상 실행 확인
[ ] SECURITY_REMEDIATION_TRACKER.md #16 완료 처리
```

---

*작성: 2026-04-13*
*기반 문서: `docs/SECURITY_REMEDIATION_TRACKER.md`, `docs/_archive/plans/2026-04-06-aws-env-remediation.md` Phase 5*

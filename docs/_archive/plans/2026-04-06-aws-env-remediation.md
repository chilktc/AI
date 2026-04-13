# AWS 환경변수 & 보안 후속조치 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR#58 배포 후 발견된 환경변수 누락·하드코딩·git 추적 문제를 해결하여 AWS 배포가 올바르게 동작하도록 한다.

**Architecture:** GitHub Secrets → deploy.yml → EC2 `.env` 주입 흐름에서 누락된 항목을 추가하고, deploy.yml 하드코딩을 Secrets 참조 방식으로 전환한다. git 추적 문제는 `git rm --cached`로 처리한다.

**Tech Stack:** GitHub Actions, AWS EC2 (SSM), Docker Compose, Python FastAPI

**브랜치:** `feature/reasoning-aws-env-remediation`

---

## 현황 분석 — GitHub Secrets vs deploy.yml 교차 검증

### GitHub Secrets 등록 현황 (2026-04-06 기준, 16개)

| Secret 이름 | 등록일 | deploy.yml 주입 | 상태 |
|------------|--------|----------------|------|
| `ALLOWED_ORIGINS` | Mar 17 | ✅ 98번 줄 | 정상 |
| `APP_ENV` | Mar 17 | ✅ 95번 줄 | 정상 |
| `AWS_ACCESS_KEY_ID` | Mar 17 | ✅ 68·93번 줄 | 정상 |
| `AWS_INSTANCE_ID` | Mar 17 | ✅ 77번 줄 | 정상 |
| `AWS_REGION` | Mar 17 | ✅ 97·111번 줄 | 정상 |
| `AWS_S3_BUCKET` | Mar 25 | ✅ 92번 줄 | 정상 |
| `AWS_SECRET_ACCESS_KEY` | Mar 17 | ✅ 69·94번 줄 | 정상 |
| `GHCR_TOKEN` | Mar 31 | ✅ 33·106번 줄 | 정상 |
| `LANGCHAIN_API_KEY` | Mar 30 | ✅ 90번 줄 | 정상 |
| `LANGCHAIN_PROJECT` | Mar 17 | ✅ 91번 줄 | 정상 |
| `LANGCHAIN_TRACING_V2` | Mar 17 | ✅ 89번 줄 | 정상 |
| `LLM_PROVIDER` | Mar 17 | ✅ 96번 줄 | 정상 |
| `LOG_FORMAT` | Mar 17 | ❌ deploy.yml 미주입 | 누락 |
| `LOG_LEVEL` | Mar 17 | ✅ 99번 줄 | 정상 |
| `NEO4J_PASSWORD` | Apr 6 | ✅ 102번 줄 | 정상 |
| `PROMPT_DIR` | Mar 25 | ✅ 104번 줄 | 정상 |

### deploy.yml 참조 항목 중 GitHub Secrets 미등록

| deploy.yml 참조 | 줄 번호 | GitHub Secrets | 결과 |
|----------------|--------|---------------|------|
| `secrets.BACKEND_API_URL` | 100 | ❌ **미등록** | 빈 문자열로 .env 주입 → API 연결 실패 |

### deploy.yml 하드코딩 (Secrets 미사용)

| 항목 | 줄 번호 | 현재 값 | 문제 |
|------|--------|--------|------|
| `STORAGE_MODE` | 101 | `local` | settings.yaml 기본값 `proxy`와 불일치. MySQL 직접접속 강제 |
| `NEO4J_URL` | 103 | `bolt://neo4j:7687` | Docker Compose 서비스명 고정. 환경별 유연성 없음 |

---

## 발견된 이슈 — 원인 및 수정 방향

### 🔴 ISSUE-1: `BACKEND_API_URL` GitHub Secrets 미등록

**발생 경위:**
1. deploy.yml 100번 줄: `BACKEND_API_URL=${{ secrets.BACKEND_API_URL }}`
2. GitHub Actions는 미등록 Secret을 **빈 문자열 `""`** 로 치환
3. EC2 `.env`에 `BACKEND_API_URL=` (빈값) 주입
4. `config/loader.py:264` — `os.getenv("BACKEND_API_URL", "http://localhost:8080/api")`
5. Python `os.getenv`는 빈 문자열도 유효한 값으로 인식 → 기본값 미사용
6. `api_base_url`이 `""` (빈 문자열) → httpx URL 파싱 오류 발생
7. **모든 Save/Load API 호출 실패** (podcast_episodes, emotion_logs, visualizations, learning 전체)

**수정 방향:**
- GitHub Settings → Secrets → `BACKEND_API_URL` 신규 등록
- 값: app-3 Backend 서버의 실제 Private IP 또는 도메인
  - 형식: `http://<app-3-private-ip>:8080/api`

---

### 🔴 ISSUE-2: `STORAGE_MODE=local` 하드코딩 + `MYSQL_URL` 미주입

**발생 경위:**
1. deploy.yml 101번 줄: `STORAGE_MODE=local` 직접 기재 (Secret 미사용)
2. `MYSQL_URL`은 GitHub Secrets에도 없고 deploy.yml에도 없음
3. PR#58(`src/db/mysql_client.py`) — `MYSQL_URL` 기본값을 실제 URL에서 `""` 로 변경
4. `STORAGE_MODE=local` + `MYSQL_URL=미설정` 조합 → 첫 DB 쿼리 시점에 `pymysql.err.OperationalError`
5. **사전 감지 없음**: `main.py` lifespan에서 MYSQL_URL 검증 로직 없어 앱은 정상 기동

**수정 방향 (두 가지 옵션, 3인 합의 필요):**

- **옵션 A (권장)**: `STORAGE_MODE=proxy`로 변경
  - deploy.yml 101번 줄: `STORAGE_MODE=local` → `STORAGE_MODE=${{ secrets.STORAGE_MODE }}`
  - GitHub Secrets에 `STORAGE_MODE=proxy` 등록
  - 근거: CLAUDE.md "settings.yaml 기본값은 `proxy`", BackendClient 경유가 설계 의도

- **옵션 B**: `MYSQL_URL` Secrets 등록 + deploy.yml 주입
  - GitHub Secrets에 `MYSQL_URL=mysql+pymysql://user:pass@<db-host>:3306/mindlog` 등록
  - deploy.yml에 `"printf '%s\n' 'MYSQL_URL=${{ secrets.MYSQL_URL }}' >> .env"` 추가
  - `STORAGE_MODE=local` 유지

---

### 🔴 ISSUE-3: `dev/local_db/.env.db` git 추적 중

**발생 경위:**
1. `dev/local_db/.env.db`는 커밋 `d403e61` (2026-03-17)에서 최초 추가됨
2. PR#58에서 `.gitignore`에 `*.db` 패턴 추가
3. **이미 추적 중인 파일에는 `.gitignore` 효력 없음** — git은 tracked file을 무시하지 않음
4. 현재도 `git ls-files`에 `dev/local_db/.env.db` 포함
5. 파일 내용: `MYSQL_URL=mysql+pymysql://mindlog_user:mindlog_pass@...`, `NEO4J_PASSWORD=mindlog_neo4j`
6. Docker 이미지 빌드 시 COPY 명령에 포함될 가능성 → 컨테이너 내부 자격증명 존재

**수정 방향:**
```bash
git rm --cached dev/local_db/.env.db
# commit: "fix: .env.db git 추적 해제"
```
- `.dockerignore`에도 `dev/local_db/.env.db` 추가 확인

---

### 🟠 ISSUE-4: `LOG_FORMAT` Secret 주입 누락

**발생 경위:**
1. GitHub Secrets에 `LOG_FORMAT` 등록되어 있음 (Mar 17)
2. deploy.yml에서 `.env`에 주입하는 라인 없음
3. 현재 앱은 `LOG_FORMAT` 환경변수를 `config/loader.py`에서 직접 참조하지 않음
4. 주입하려는 의도가 있었으나 deploy.yml 작성 시 누락된 것으로 판단

**수정 방향:**
- deploy.yml에 `LOG_FORMAT` 주입 라인 추가
- 또는 Secret 자체를 삭제 (코드에서 미사용 확인 후)

---

### 🟠 ISSUE-5: `APP_ENV` 값 미확인

**발생 경위:**
1. `APP_ENV` Secret은 Mar 17 등록, Mar 17 마지막 업데이트
2. PR#58 이후 변경 없음 — 현재 값이 `production`인지 불명확
3. `main.py` lifespan: `APP_ENV=production`일 때만 필수 자격증명 누락 시 RuntimeError 발생
4. `APP_ENV`가 `production`이 아닌 경우 → 자격증명 누락해도 서버 기동 → silent failure

**수정 방향:**
- GitHub Secrets에서 `APP_ENV` 현재 값 확인 (값은 `production`이어야 함)
- `development` 또는 다른 값이면 `production`으로 변경

---

### 🟡 ISSUE-6: git history 내 민감정보 잔존

**발생 경위:**
1. `SECURITY_REMEDIATION_TRACKER.md`에 명시된 커밋 `1d099b6`에 KT Cloud API 토큰 잔존
2. ALB 도메인 (`t7-mindlog-prod-alb-*.ap-northeast-2.elb.amazonaws.com`) 과거 커밋에 존재
3. 내부 IP (`${BACKEND_HOST}`) 과거 커밋에 존재
4. PR#58에서 코드 제거는 완료했으나 `git filter-repo` 미실행

**수정 방향:**
- 3인 합의 후 `git filter-repo` 실행 (force-push 수반, main 보호 브랜치 일시 해제 필요)
- 실행 전 모든 팀원 로컬 브랜치 백업 필수
- KT Cloud API 토큰 즉시 로테이션 (이미 노출된 것으로 간주)

---

### 🟡 ISSUE-7: `build_podcast_graph()`에 TIER 0 (Intent Classifier) 누락

**발생 경위:**
1. `src/graph/workflow.py`에 두 가지 그래프 빌더 존재
   - `build_unified_graph()`: TIER 0 포함 (Intent Classifier → TIER 1 → ...)
   - `build_podcast_graph()`: TIER 1부터 시작 (TIER 0 없음)
2. `compile_graph("podcast")` 호출 시 Intent Classifier 없이 실행
3. 설계 의도인지 버그인지 불명확 — CLAUDE.md는 모든 파이프라인에 TIER 0 포함으로 명세

**수정 방향:**
- 개발자3(workflow.py 관리)에게 설계 의도 확인 필요
- 의도적 설계라면 CLAUDE.md에 예외 케이스 명시
- 버그라면 `build_podcast_graph()`에 `intent_classifier` 노드 추가 (3인 합의)

---

### 🟡 ISSUE-8: Podcast Reasoning 설정 CLAUDE.md 미갱신

**발생 경위:**
1. `settings.yaml` 주석: `# haiku → sonnet_37: GoT group 6개 카테고리 분류 정확도 향상`
2. 프롬프트 버전도 `3.1.0`으로 패치됨 (주석: `# v3.0.0 + GoT group 필드`)
3. CLAUDE.md는 여전히 모델 `Haiku`, 프롬프트 `v3.0.0`으로 기재
4. Memory 기록도 Round 4 확정이 `PR v3.0.0`으로 기록됨

**수정 방향:**
- CLAUDE.md 에이전트 구성 표에서 Podcast Reasoning 모델 `Haiku` → `Sonnet 3.7` 수정
- CLAUDE.md 프롬프트 핀닝 섹션에서 `v3.0.0` → `v3.1.0` 수정
- Memory 기록 갱신 (`feedback_plan_decisions` 또는 project 메모리)

---

## 구현 계획

### Phase 1: git 추적 문제 해결 (코드 변경 없음, 즉시 실행 가능)

#### Task 1-1: `dev/local_db/.env.db` git 추적 해제

**파일:**
- Modify: `.gitignore` (확인용)
- Execute: `git rm --cached dev/local_db/.env.db`

- [ ] **Step 1: 현재 추적 상태 확인**
  ```bash
  git ls-files dev/local_db/.env.db
  # 출력: dev/local_db/.env.db (추적 중 확인)
  ```

- [ ] **Step 2: git 추적 해제 (파일 삭제 없이)**
  ```bash
  git rm --cached dev/local_db/.env.db
  ```
  Expected: `rm 'dev/local_db/.env.db'`

- [ ] **Step 3: .gitignore 적용 확인**
  ```bash
  git status dev/local_db/.env.db
  # Expected: 아무 출력 없음 (untracked + ignored)
  git check-ignore -v dev/local_db/.env.db
  # Expected: .gitignore:N:*.db  dev/local_db/.env.db
  ```

- [ ] **Step 4: .dockerignore 확인 및 추가**
  ```bash
  cat .dockerignore 2>/dev/null || echo "파일 없음"
  # dev/local_db/.env.db 항목 없으면 추가
  ```
  `.dockerignore`에 없으면 추가:
  ```
  dev/local_db/.env.db
  dev/local_db/.env.db.*
  ```

- [ ] **Step 5: 커밋**
  ```bash
  git add .gitignore .dockerignore
  git commit -m "fix: .env.db git 추적 해제 및 dockerignore 추가"
  ```

---

### Phase 2: deploy.yml 수정

#### Task 2-1: `BACKEND_API_URL` Secrets 주입 정상화

**파일:**
- Modify: `.github/workflows/deploy.yml` (100번 줄 — 변경 없음, Secret 등록으로 해결)
- GitHub Settings: Secrets → `BACKEND_API_URL` 등록 (수동)

**사전 조건:** app-3 Backend 서버의 Private IP 또는 도메인 확인 필요

- [ ] **Step 1: 현재 deploy.yml 100번 줄 확인**
  ```bash
  sed -n '98,105p' .github/workflows/deploy.yml
  ```
  Expected: `BACKEND_API_URL=${{ secrets.BACKEND_API_URL }}`

- [ ] **Step 2: loader.py의 BACKEND_API_URL 처리 로직 확인**
  ```bash
  grep -n "BACKEND_API_URL" config/loader.py
  ```
  확인 포인트: `os.getenv("BACKEND_API_URL", "http://localhost:8080/api")`
  → 빈 문자열 시 기본값 미사용 버그 확인

- [ ] **Step 3: loader.py 빈 문자열 방어 로직 추가 (코드 수정)**
  파일: `config/loader.py:264`

  현재:
  ```python
  return os.getenv("BACKEND_API_URL", "http://localhost:8080/api")
  ```
  수정 후:
  ```python
  val = os.getenv("BACKEND_API_URL", "").strip()
  return val if val else "http://localhost:8080/api"
  ```

- [ ] **Step 4: GitHub Secrets에 `BACKEND_API_URL` 등록 (수동 작업)**
  ```
  GitHub → chilktc/AI → Settings → Secrets and variables → Actions
  → New repository secret
  Name: BACKEND_API_URL
  Value: http://<app-3-private-ip>:8080/api
  ```

- [ ] **Step 5: 커밋**
  ```bash
  git add config/loader.py
  git commit -m "fix: BACKEND_API_URL 빈 문자열 폴백 방어 로직 추가"
  ```

---

#### Task 2-2: `STORAGE_MODE` Secrets 전환 (옵션 A — proxy 전환)

**파일:**
- Modify: `.github/workflows/deploy.yml` (101번 줄)

- [ ] **Step 1: 3인 합의 확인 — STORAGE_MODE 방향 결정**
  - 옵션 A: `proxy` 전환 (BackendClient 경유, MySQL 직접 미사용)
  - 옵션 B: `local` 유지 + `MYSQL_URL` Secrets 추가
  - **합의 후 진행**

- [ ] **Step 2 (옵션 A 선택 시): deploy.yml 101번 줄 수정**
  파일: `.github/workflows/deploy.yml:101`

  현재:
  ```yaml
  "printf '%s\n' 'STORAGE_MODE=local' >> .env",
  ```
  수정 후:
  ```yaml
  "printf '%s\n' 'STORAGE_MODE=${{ secrets.STORAGE_MODE }}' >> .env",
  ```

- [ ] **Step 3 (옵션 A 선택 시): GitHub Secrets에 `STORAGE_MODE` 등록 (수동)**
  ```
  Name: STORAGE_MODE
  Value: proxy
  ```

- [ ] **Step 4 (옵션 B 선택 시): MYSQL_URL 주입 라인 추가**
  파일: `.github/workflows/deploy.yml` — 101번 줄 뒤에 추가:
  ```yaml
  "printf '%s\n' 'MYSQL_URL=${{ secrets.MYSQL_URL }}' >> .env",
  ```
  GitHub Secrets에 `MYSQL_URL` 등록 필요.

- [ ] **Step 5: 커밋**
  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "fix: STORAGE_MODE deploy.yml Secrets 전환"
  ```

---

#### Task 2-3: `LOG_FORMAT` 주입 추가

**파일:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: 코드에서 LOG_FORMAT 실제 사용 여부 확인**
  ```bash
  grep -rn "LOG_FORMAT" src/ config/ --include="*.py" --include="*.yaml"
  ```
  Expected: 사용처가 있으면 주입 추가, 없으면 Secret 삭제 검토

- [ ] **Step 2: 사용처 있을 경우 deploy.yml에 주입 라인 추가**
  파일: `.github/workflows/deploy.yml` — `LOG_LEVEL` 줄 뒤에 추가:
  ```yaml
  "printf '%s\n' 'LOG_FORMAT=${{ secrets.LOG_FORMAT }}' >> .env",
  ```

- [ ] **Step 3: 커밋**
  ```bash
  git add .github/workflows/deploy.yml
  git commit -m "fix: LOG_FORMAT 환경변수 .env 주입 추가"
  ```

---

### Phase 3: CLAUDE.md 문서 갱신

#### Task 3-1: Podcast Reasoning 설정 반영

**파일:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: settings.yaml 실제 설정 확인**
  ```bash
  grep -A5 "podcast_reasoning" config/settings.yaml
  ```
  확인 포인트: `model: sonnet_37`, 프롬프트 버전 `3.1.0`

- [ ] **Step 2: CLAUDE.md 에이전트 구성 표 수정**
  파일: `CLAUDE.md` — 에이전트 구성 표에서:
  ```
  | 05 | Podcast Reasoning | TIER 1 (병렬) | Haiku | 개발자3 |
  ```
  수정 후:
  ```
  | 05 | Podcast Reasoning | TIER 1 (병렬) | Sonnet 3.7 | 개발자3 |
  ```

- [ ] **Step 3: CLAUDE.md 프롬프트 핀닝 섹션 수정**
  ```
  현재: Podcast Reasoning: v3.0.0
  수정: Podcast Reasoning: v3.1.0
  ```

- [ ] **Step 4: 커밋**
  ```bash
  git add CLAUDE.md
  git commit -m "docs: Podcast Reasoning 모델/프롬프트 버전 실제 설정 반영"
  ```

---

### Phase 4: AWS 실제 환경 테스트

#### Task 4-1: Phase 1~3 변경사항 develop 반영 후 재배포

- [ ] **Step 1: PR 생성 → 팀 리뷰 → develop 머지**
  ```bash
  git push origin feature/reasoning-aws-env-remediation
  # GitHub에서 PR 생성: feature/reasoning-aws-env-remediation → develop
  ```

- [ ] **Step 2: GitHub Actions 배포 완료 대기**
  ```
  GitHub → chilktc/AI → Actions → 최신 워크플로우 실행 확인
  ```

- [ ] **Step 3: EC2 `.env` 파일 내용 확인 (SSM 경유)**
  AWS Systems Manager → Session Manager → app-2 접속:
  ```bash
  cat /home/ubuntu/app/.env | grep -E "BACKEND_API_URL|STORAGE_MODE|MYSQL_URL|APP_ENV"
  ```
  Expected:
  ```
  BACKEND_API_URL=http://<app-3-ip>:8080/api  ← 실제 값 존재
  STORAGE_MODE=proxy  (또는 local + MYSQL_URL 존재)
  APP_ENV=production
  ```

#### Task 4-2: Backend Health E2E 테스트

- [ ] **Step 1: app-2에서 Backend Health 테스트 실행**
  ```bash
  cd /home/ubuntu/app
  source .env
  pytest tests/api/e2e/test_backend_health.py -v -m live \
      --backend-url=$BACKEND_API_URL
  ```
  Expected: 모든 테스트 PASS (또는 SKIP — backend 미기동 시)

- [ ] **Step 2: API 직접 호출 테스트 (curl)**
  ```bash
  # Health check
  curl -s $BACKEND_API_URL/../health | python3 -m json.tool

  # Save API 테스트 (STORAGE_MODE에 따라 동작 여부 결정)
  curl -X POST $BACKEND_API_URL/emotion_logs \
    -H "Content-Type: application/json" \
    -d '{"user_id":"test","session_id":"test","type":"emotion_log","data":{},"timestamp":"2026-04-06T00:00:00Z"}'
  ```

#### Task 4-3: 팟캐스트 파이프라인 스모크 테스트

- [ ] **Step 1: LLM 연결 확인 (Bedrock)**
  ```bash
  cd /home/ubuntu/app
  source .env
  python3 -c "
  from src.agents.shared.llm_client import LLMClient
  from config.loader import get_settings
  s = get_settings()
  print('Provider:', s.llm_provider)
  print('Region:', s.bedrock_region)
  print('API URL:', s.api_base_url)
  print('Storage mode:', s.storage_mode)
  "
  ```
  Expected:
  ```
  Provider: bedrock
  Region: ap-northeast-2
  API URL: http://<app-3-ip>:8080/api   ← localhost가 아닌 실제 IP
  Storage mode: proxy  (또는 local)
  ```

- [ ] **Step 2: 파이프라인 E2E 실행**
  ```bash
  cd /home/ubuntu/app
  source .env
  python3 tests/api/e2e/test_e2e_podcast.py 2>&1 | tee /tmp/e2e_result.log
  ```

- [ ] **Step 3: 결과 확인**
  ```bash
  tail -50 /tmp/e2e_result.log
  # PASS 확인 또는 오류 원인 분석
  ```

---

### Phase 5: 후속 보안 조치 (3인 합의 필요, 별도 진행)

#### Task 5-1: git filter-repo 실행

**사전 조건:** 3명 전원 합의, main 브랜치 보호 규칙 일시 해제

- [ ] **Step 1: 제거할 패턴 목록 확인** (`docs/SECURITY_REMEDIATION_TRACKER.md` 참조)
  - KT Cloud API 토큰 (커밋 `1d099b6` 이전)
  - ALB 도메인 `t7-mindlog-prod-alb-1834710625.ap-northeast-2.elb.amazonaws.com`
  - 내부 IP `${BACKEND_HOST}`
  - DB 비밀번호 `mindlog_pass`, `mindlog_root`, `mindlog_neo4j`

- [ ] **Step 2: 모든 팀원 로컬 브랜치 백업**
  ```bash
  git bundle create mind-log-backup-$(date +%Y%m%d).bundle --all
  ```

- [ ] **Step 3: git filter-repo 실행 (별도 클린 클론에서)**
  ```bash
  git clone --mirror https://github.com/chilktc/AI mind-log-mirror
  cd mind-log-mirror
  git filter-repo --replace-text <(cat << 'EOF'
  t7-mindlog-prod-alb-1834710625.ap-northeast-2.elb.amazonaws.com==>ALB_DOMAIN_REMOVED
  ${BACKEND_HOST}==>INTERNAL_IP_REMOVED
  mindlog_pass==>DB_PASS_REMOVED
  mindlog_root==>DB_ROOT_REMOVED
  mindlog_neo4j==>DB_NEO4J_REMOVED
  EOF
  )
  git push --force --all
  git push --force --tags
  ```

- [ ] **Step 4: 모든 팀원 re-clone 후 작업 재개**

#### Task 5-2: KT Cloud API 토큰 로테이션

- [ ] KT Cloud 콘솔에서 기존 토큰 즉시 폐기
- [ ] 신규 토큰 발급
- [ ] GitHub Secrets에 `KT_CLOUD_API_TOKEN` 등록 + deploy.yml 주입 추가

---

## 우선순위 실행 순서

```
즉시 (오늘):
  Phase 1 (Task 1-1) — .env.db git 추적 해제
  Task 4-1 Step 3    — EC2 현재 .env 내용 확인 (현황 파악)

배포 전 (오늘~내일):
  Task 2-1           — BACKEND_API_URL Secrets 등록 + loader.py 방어 로직
  Task 2-2           — STORAGE_MODE 방향 결정 (3인 합의) 후 deploy.yml 수정
  Task 2-3           — LOG_FORMAT 주입 추가

배포 후:
  Phase 4            — AWS 실제 환경 테스트

이번 주:
  Phase 3            — CLAUDE.md 문서 갱신
  Phase 5            — git filter-repo (3인 합의 후)
```

---

## 테스트 체크리스트 (배포 후 최종 확인)

```
[ ] EC2 .env에 BACKEND_API_URL 실제 값 존재
[ ] EC2 .env에 STORAGE_MODE 값 존재 (proxy 또는 local)
[ ] STORAGE_MODE=local이면 MYSQL_URL도 존재
[ ] APP_ENV=production 확인
[ ] settings.api_base_url이 localhost가 아닌 실제 URL 반환
[ ] test_backend_health.py -m live PASS
[ ] 팟캐스트 파이프라인 E2E 오류 없음
[ ] dev/local_db/.env.db가 git status에서 untracked+ignored 상태
[ ] Docker 이미지에 .env.db 미포함 확인
```

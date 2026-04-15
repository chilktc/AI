# 보안 감사 후속 조치 추적

> **감사일**: 2026-04-06
> **수정 브랜치**: `feature/reasoning-security-remediation`
> **상태**: 코드 수정 완료, 수동 조치 미완료

---

## 1. 키 로테이션 필요 목록

코드 수정으로 해결할 수 없는 항목이다. 반드시 수동으로 로테이션해야 한다.

| # | 시크릿 | 노출 경로 | 담당 | 조치 | 완료 여부 |
|---|--------|----------|------|------|----------|
| 1 | **KT Cloud API 토큰** | git history (커밋 `1d099b6` 이전) | 개발자2 | KT Cloud 콘솔에서 즉시 새 토큰 발급 → `.env`의 `KT_CLOUD_API_TOKEN` 업데이트 | [ ] |
| 2 | **OpenAI API 키** (`sk-proj-...`) | 로컬 `.env` (비추적) | AI팀 | ⚠️ **배포 환경(Bedrock)에서는 불필요**. 로컬 개발에서만 사용 시 로테이션 불필요. OpenAI 프로바이더 전환 시에만 조치 필요. | [N/A] |
| 3 | **LangSmith API 키** (`lsv2_pt_...`) | ~~git history 노출~~ → **2026-04-15 재확인: 실제 값 미노출** (커밋 `ffa54f8` 검사 결과, 마스킹 예시 텍스트만 기재됨. filter-repo 불필요) + 로컬 `.env` (비추적) | AI팀 | git history 조치 불필요. 필요 시 `.env`의 `LANGCHAIN_API_KEY` 로테이션. | [확인완료] |
| 4 | **Grafana/OpenSearch 비밀번호** | 문서에서 제거됨, 실서버 변경 필요 | 인프라팀 | app-1 SSM 접속 → Grafana/OpenSearch admin 비밀번호 변경 | [ ] |
| 5 | **로컬 DB 비밀번호** | `docker-compose.db.yml`에서 제거됨 | 각 개발자 | 로컬 `.env.db` 재설정 (`dev/local_db/.env.db.example` 참조) | [ ] |

---

## 2. GitHub Secrets 업데이트

`deploy.yml`이 참조하는 GitHub Secrets 중 이번 감사로 변경이 필요한 항목:

| # | Secret 이름 | 변경 필요? | 사유 |
|---|------------|-----------|------|
| 1 | `GHCR_TOKEN` | ❌ 불필요 | 미노출 |
| 2 | `AWS_ACCESS_KEY_ID` | ⚠️ 확인 필요 | IAM 사용자명 문서 노출. 키 자체는 미노출이나 점검 권장 |
| 3 | `AWS_SECRET_ACCESS_KEY` | ⚠️ 확인 필요 | 위와 동일 |
| 4 | `AWS_REGION` | ❌ 불필요 | 비밀정보 아님 |
| 5 | `AWS_INSTANCE_ID` | ❌ 불필요 | 미노출 |
| 6 | `LANGCHAIN_TRACING_V2` | ❌ 불필요 | 비밀정보 아님 |
| 7 | **`LANGCHAIN_API_KEY`** | ⚠️ 확인 완료 (변경 선택) | 2026-04-15 재확인: git history에 실제 값 미노출 (예시 텍스트만). 현재 Secret은 정상 동작 중. 로테이션은 선택사항. |
| 8 | `LANGCHAIN_PROJECT` | ❌ 불필요 | 비밀정보 아님 |
| 9 | `AWS_S3_BUCKET` | ⚠️ 확인 필요 | 버킷명 설정파일 노출. 버킷명 변경 시 업데이트 |
| 10 | `APP_ENV` | ❌ 불필요 | 비밀정보 아님 |
| 11 | `LLM_PROVIDER` | ❌ 불필요 | 비밀정보 아님 |
| 12 | `ALLOWED_ORIGINS` | ⚠️ 확인 필요 | ALB 엔드포인트 문서 노출. ALB 변경 시 업데이트 |
| 13 | `LOG_LEVEL` | ❌ 불필요 | 비밀정보 아님 |
| 14 | `BACKEND_API_URL` | ❌ 불필요 | 이미 설정됨 |
| 15 | **`NEO4J_PASSWORD`** | **⚠️ 권장** | 로컬 dev 비밀번호가 docker-compose에 노출. 운영 비밀번호 동일 시 변경 필수 |

### deploy.yml 미포함 — 추가 검토 필요

| # | 환경변수 | 권장 조치 |
|---|---------|----------|
| 1 | `MYSQL_URL` | 운영 DB 접속 필요 시 Secrets 추가 + deploy.yml 라인 추가 |
| 2 | `KT_CLOUD_ENDPOINT` | Episode Memory 운영 시 Secrets 추가 + deploy.yml 라인 추가 |
| 3 | `KT_CLOUD_API_TOKEN` | 토큰 로테이션 후 새 토큰으로 Secrets 추가 |
| 4 | `OPENAI_API_KEY` | ❌ **배포 환경 불필요** — 운영은 Bedrock 사용. 로컬 개발 전용. |
| 5 | `ANTHROPIC_API_KEY` | 운영에서 직접 API 사용 시 추가 (bedrock 사용 시 불필요) |
| 6 | `PINECONE_API_KEY` | Pinecone 연동 시 추가 필요 |

---

## 3. 접속 정보 보안 저장소 이관

문서에서 제거된 접속 정보를 Notion 비공개 페이지, 1Password, 또는 AWS Secrets Manager에 보관해야 한다.

### 이관할 정보 목록

**[AWS 콘솔 접속]**
- 로그인 URL (AWS Account ID 포함)
- IAM 사용자명 3개 (AI, Backend, Frontend)
- 비밀번호: 팀장 보유

**[모니터링 대시보드]**
- Grafana: ALB:3001 — admin 계정 비밀번호
- OpenSearch: ALB:5601 — admin 계정 비밀번호

**[서버 Private IP]**
- app-1 ~ app-4 Private IP 4개
- 각 서버의 역할 및 포트 정보

**[AWS 리소스]**
- ALB 도메인
- S3 버킷명 3개 (로그, AI 에셋, 이미지)

---

## 4. 개발 환경 재설정 가이드

이번 수정으로 각 개발자가 수행해야 할 작업:

### 4-1. 로컬 DB 환경 재설정

```bash
# 1. .env.db 재생성 (기존 파일이 로컬에 남아있으므로 확인)
cd dev/local_db
cp .env.db.example .env.db
# .env.db를 열어 실제 비밀번호 입력

# 2. Docker 컨테이너 재생성 (비밀번호 변경 시)
docker compose -f docker-compose.db.yml down -v
docker compose -f docker-compose.db.yml --env-file .env.db up -d
# ⚠️ -v 옵션으로 기존 볼륨 삭제됨 (로컬 테스트 데이터 초기화)
```

### 4-2. MYSQL_URL 환경변수 설정

`mysql_client.py`의 기본 fallback이 제거되었으므로, `.env` 또는 `.env.db`에 `MYSQL_URL` 필수 설정:

```bash
MYSQL_URL=mysql+pymysql://mindlog_user:<비밀번호>@localhost:3306/mindlog
```

### 4-3. 로컬 DB 테스트 실행

```bash
source dev/local_db/.env.db && pytest dev/local_db/ -v
```

---

## 5. Git History 정리 (3인 합의 필요)

KT Cloud 토큰이 git history에 잔존한다. 완전 제거 절차:

1. 3명 전원이 작업 중인 브랜치를 push
2. `git filter-repo --replace-text expressions.txt` 실행
3. `expressions.txt` 내용: `kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e==>***REDACTED***`
4. force-push 후 전원 re-clone

> **이 작업은 별도 합의 후 진행한다.**

---

## 6. 향후 방지 대책

| 대책 | 담당 | 우선순위 |
|------|------|---------|
| `detect-secrets` pre-commit hook 도입 | 인프라 담당 | MEDIUM |
| GitHub Secret Scanning 활성화 | 인프라 담당 | HIGH |
| `.env.example` 정기 점검 (실제 값 혼입 방지) | 전원 | LOW |

---

*마지막 업데이트: 2026-04-15 17:30*

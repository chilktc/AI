> **아카이브** — Zone A/B/C/D 체계 기준으로 작성됨. 현재 개발자1/2/3 구조와 다를 수 있으므로 참고용으로만 사용.

# 프로젝트 인프라 적용 가이드

> 작성일: 2026-03-09
> 기반 문서: 인프라팀 인수인계 보고서 (260308)
> 인프라 레포: [chilktc/infra](https://github.com/chilktc/infra)
>
> 인프라 구현 상세는 [INFRA_DEPLOYMENT_GUIDE.md](INFRA_DEPLOYMENT_GUIDE.md)를 참조하세요.

---

## 1. 인프라 현황 요약

| 항목 | 상세 |
|------|------|
| VPC 대역 | `10.7.0.0/16` (Team 7 할당) |
| 가용 영역 | ap-northeast-2a, ap-northeast-2c (2AZ 고가용성) |
| 서버 스펙 | EC2 `t3.medium` (2vCPU, 4GB RAM) × 4대 |
| 로드밸런서 | AWS ALB (Application Load Balancer) |
| 접속 방식 | AWS Session Manager (SSM) — SSH 완전 차단 |
| OS | Ubuntu 22.04 LTS |
| 컨테이너 | Docker & Docker Compose 사전 설치 |

---

## 2. 서버 접속 가이드 (SSM 방식)

### 2-1. AWS 콘솔 로그인

- 로그인 URL: `https://<AWS_ACCOUNT_ID>.signin.aws.amazon.com/console`
- 계정 정보:

| 팀 | 사용자 ID | IAM 그룹 |
|----|-----------|----------|
| AI | `<IAM_USER_AI>` | 7team_AI_Group |
| Backend | `<IAM_USER_BACKEND>` | 7team_Backend_Group |
| Frontend | `<IAM_USER_FRONTEND>` | 7team_Frontend_Group |

- 비밀번호: 팀장에게 별도 확인

### 2-2. SSM 접속 순서

1. AWS 콘솔 상단 검색창에 `EC2` 입력 후 이동
2. 왼쪽 메뉴에서 `인스턴스` 클릭
3. 본인 담당 서버 선택 → 우측 상단 `연결 (Connect)` 클릭
4. `세션 매니저` 탭 선택 → `연결` 클릭
5. 브라우저에서 바로 터미널이 열림 (`.pem` 키파일 불필요)

> ⚠️ SSH(22번 포트)는 보안상 완전히 차단되어 있습니다. 반드시 SSM을 통해서만 접속하세요.

---

## 3. 서버 배치 및 포트 매핑

### 3-1. 서버 리스트

| 서버 | AZ | Private IP | 역할 | ALB 포함 |
|------|----|------------|------|----------|
| app-1 | 2a | `<APP1_IP>` | 관리/모니터링 (Bastion) | ❌ |
| app-2 | 2c | `<APP2_IP>` | AI 서비스 (FastAPI) | ✅ |
| app-3 | 2a | `<APP3_IP>` | Backend/Core (Spring Boot) | ✅ |
| app-4 | 2c | `<APP4_IP>` | Frontend (Next.js) | ✅ |

### 3-2. ALB 포트 매핑 (외부 접근)

ALB 도메인: `http://<ALB_DOMAIN>`

| 서비스 | 서버 | 포트 | 접속 URL |
|--------|------|------|----------|
| Frontend (Next.js) | app-4 | 3000 | `ALB주소:3000` |
| Backend (Spring Boot) | app-3 | 8080 (또는 80) | `ALB주소:8080` 또는 `ALB주소` |
| AI Server (FastAPI) | app-2 | 8000 | 백엔드 내부 통신용 |
| Grafana | app-1 | 3001 | `ALB주소:3001` |
| OpenSearch Dashboard | app-1 | 5601 | `ALB주소:5601` |

---

## 4. 팀별 적용 사항

### 4-1. Backend 팀

**담당 서버:** app-3 (`<APP3_IP>`) — 메인, app-4 (`<APP4_IP>`) — HA 이중화

**적용 항목:**

- **배포 경로:** `/home/ubuntu/app/`에 `docker-compose.yml` 배치 후 실행
- **포트 바인딩:** `8080` 포트로 바인딩하면 ALB와 자동 연동
- **IAM 권한 범위:**
  - SES 이메일 발송 (`SendEmail`, `SendRawEmail`, `SendTemplatedEmail` 등)
  - SSM 서버 접속 (`StartSession`, `ResumeSession`, `TerminateSession`)
  - EC2/SSM 조회 (`DescribeInstances`, `DescribeSessions` 등)
- **환경변수:** `.env` 파일 사용 필수, docker-compose 내 비밀번호 하드코딩 금지
- **S3 활용:** 로그/미디어 백업에 `<S3_LOGS_BUCKET>` 버킷 사용
- **Docker 권한:** `ubuntu` 사용자가 docker 그룹에 포함되어 `sudo` 불필요

**참조:** [infra/apps](https://github.com/chilktc/infra/tree/main/apps) — 앱 매니페스트 (향후 K8s 전환 시 참고)

### 4-2. AI 팀

**담당 서버:** app-2 (`<APP2_IP>`)

**적용 항목:**

- **배포 경로:** `/home/ubuntu/app/`에 `docker-compose.yml` 배치 후 실행
- **포트 바인딩:** `8000` 포트 (백엔드 내부 통신용)
- **IAM 권한 범위:**
  - SSM 서버 접속 (`StartSession`, `ResumeSession`, `TerminateSession`)
  - EC2/SSM 조회 (`DescribeInstances`, `DescribeSessions` 등)
  - S3 읽기 전용 (`s3:Get*`, `s3:List*`)
- **환경변수:** `.env` 파일 사용 필수
- **S3 데이터 접근:** S3 버킷에서 데이터를 읽을 수 있으나, 쓰기 권한은 없음

**참조:** [infra/aws](https://github.com/chilktc/infra/tree/main/aws) — AWS 인프라 리소스 구성

### 4-3. Frontend 팀

**담당 서버:** app-4 (`<APP4_IP>`)

**적용 항목:**

- **배포 경로:** `/home/ubuntu/app/`에 `docker-compose.yml` 배치 후 실행
- **포트 바인딩:** `3000` 포트 (Next.js)
- **ALB 접속점:** `http://<ALB_DOMAIN>`
- **IAM 권한 범위:**
  - S3 정적 배포 (`PutObject`, `GetObject`, `ListBucket`, `DeleteObject` 등)
  - CloudFront 캐시 무효화 (`CreateInvalidation`, `GetInvalidation`, `ListDistributions`)
  - EC2/ELB 조회 (`DescribeInstances`, `DescribeLoadBalancers`)
- **라우팅:** 현재 대상 그룹은 app-2, 3, 4로 구성. 경로별 라우팅 분기(`api/*`, `admin/*` 등)가 필요하면 인프라팀에 요청

**참조:** [infra/docs](https://github.com/chilktc/infra/tree/main/docs) — 아키텍처/PRD/스펙 문서

---

## 5. 배포 가이드 (공통)

### 5-1. Docker Compose 배포 방식

```bash
# SSM으로 서버 접속 후
cd /home/ubuntu/app/

# docker-compose.yml과 .env 파일 배치
# (docker-compose.yml 내에서 env_file로 .env 참조)

# 실행
docker compose up -d

# 로그 확인
docker compose logs -f

# 재배포
docker compose down && docker compose up -d
```

### 5-2. .env 환경변수 관리

- 서버 내 `/home/ubuntu/app/.env` 파일을 통해 환경변수를 로드하도록 구성되어 있음
- Docker Compose 내 비밀번호/키 하드코딩은 **금지**
- `.env` 파일은 Git에 커밋하지 않도록 `.gitignore`에 반드시 포함

---

## 6. 모니터링 환경

모든 서버에 아래 모니터링 도구가 자동 설치되어 작동 중:

| 도구 | 포트 | 용도 | 기본 계정 |
|------|------|------|-----------|
| Prometheus | 9090 | 메트릭 수집 | - |
| Grafana | 3000 (내부) / 3001 (ALB) | 데이터 시각화 | `admin` / `<팀장에게 별도 확인>` |
| OpenSearch | 9200 (API) / 5601 (Dashboard) | 로그 수집/시각화 | `admin` / `<팀장에게 별도 확인>` |

> ⚠️ OpenSearch 구동을 위해 `vm.max_map_count` 커널 파라미터가 이미 최적화되어 있습니다. 변경하지 마세요.

**참조:** [infra/platform](https://github.com/chilktc/infra/tree/main/platform) — Prometheus, Grafana 등 플랫폼 구성 요소

---

## 7. 보안 준수 사항

1. **SSH 접근 금지:** 22번 포트 완전 차단. 반드시 SSM으로만 접속
2. **최소 권한 원칙:** 각 팀은 본인 그룹에 할당된 리소스 외에는 수정 권한 없음
3. **.env 환경변수 사용:** 비밀번호/API키 등 민감 정보는 `.env` 파일로 관리
4. **S3 백업 활용:** 로그/미디어 파일은 `<S3_LOGS_BUCKET>` 버킷 사용 (디스크 풀 방지)
5. **보안 그룹 구성:**
   - ALB SG: 외부 80, 443 포트만 오픈 (app-1 트래픽 차단)
   - App SG: ALB로부터의 트래픽 및 내부 관리용 8080, 3000, 9090, 5601 포트 허용

---

## 8. 향후 계획 (인프라팀 로드맵)

| 항목 | 내용 |
|------|------|
| FinOps | t3.medium 기준 시작, 리소스 모니터링 결과에 따라 사양 조정 |
| SSL/HTTPS | ACM(AWS Certificate Manager) 통한 HTTPS 보안 처리 예정 |
| CI/CD | GitHub Actions 또는 Jenkins 기반 자동 배포 파이프라인 구축 중 |
| K8s 전환 | 현재 EC2 기반 → 향후 EKS 기반 Kubernetes 플랫폼으로 전환 계획 |

**참조:** [infra/gitops](https://github.com/chilktc/infra/tree/main/gitops) — ArgoCD GitOps 루트 (K8s 전환 시 활용)

---

## 9. 참조 링크

### 노션 문서

- [260308 IAM 계정](https://www.notion.so/260308-IAM-31d9e3e335cc809c9539f209d5d30e78) — IAM 그룹/정책 상세
- [260308 서버 접속 방법 (SSH 키파일 불필요)](https://www.notion.so/260308-SSH-31d9e3e335cc801f8e5dc6698119cd84) — 접속 가이드
- [260308 인프라 구축 완료 및 인수인계 보고서](https://www.notion.so/260308-31d9e3e335cc8020b07cdfcdb09cfc7e) — 전체 인수인계

### GitHub 인프라 레포

- [chilktc/infra](https://github.com/chilktc/infra) — 인프라 레포 전체
  - [aws/](https://github.com/chilktc/infra/tree/main/aws) — 클라우드 인프라 리소스 (VPC, Subnet, ALB, EKS, IAM 등)
  - [platform/](https://github.com/chilktc/infra/tree/main/platform) — K8s 플랫폼 구성 (Istio, ArgoCD, Prometheus 등)
  - [apps/](https://github.com/chilktc/infra/tree/main/apps) — 애플리케이션 매니페스트
  - [gitops/](https://github.com/chilktc/infra/tree/main/gitops) — ArgoCD GitOps 루트
  - [docs/](https://github.com/chilktc/infra/tree/main/docs) — 아키텍처, PRD, 스펙 문서

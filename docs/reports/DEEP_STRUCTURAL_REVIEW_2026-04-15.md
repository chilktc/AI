# 심층 구조적 점검 보고서 (Deep Structural Review)

**작성일**: 2026-04-15  
**조사 범위**: CI/CD, 시크릿/보안, 동시성, 인스턴스 생명주기, 캐시/메모리 누수, 문서 불일치  
**전제**: 코드 수정 없음 — 분석 및 목록화 전용

---

## 목차

1. [CI/CD 파이프라인 심층 분석](#1-cicd-파이프라인-심층-분석)
2. [시크릿/환경변수 보안 심층 분석](#2-시크릿환경변수-보안-심층-분석)
3. [동시성 및 경합 조건 심층 분석](#3-동시성-및-경합-조건-심층-분석)
4. [인스턴스 생명주기 및 리소스 관리](#4-인스턴스-생명주기-및-리소스-관리)
5. [캐시 및 메모리 누수](#5-캐시-및-메모리-누수)
6. [문서-코드 불일치 전수 조사](#6-문서-코드-불일치-전수-조사)
7. [전체 우선순위 종합표](#7-전체-우선순위-종합표)

---

## 1. CI/CD 파이프라인 심층 분석

### CI-1. Job 간 의존성 부재 — 검증 순서 미보장 (위험도: 🔴 높음)

**파일**: `.github/workflows/ci.yml:13-87`

```yaml
jobs:
  test:         # 독립 실행
  lint:         # 독립 실행
  docker-build: # 독립 실행 — lint/test 실패해도 빌드 진행
```

세 job이 완전 병렬 실행됨. lint 체크가 실패해도 test와 docker-build는 계속 실행된다. 검증되지 않은 코드가 이미지화될 수 있다.

**권장**: `needs: [lint, test]` 추가로 `lint → test → docker-build` 순차 보장.

---

### CI-2. mypy 설정 — CI 실행 명령이 pyproject.toml 엄격함 우회 (위험도: 🟠 중간)

**파일**: `.github/workflows/ci.yml:71` vs `pyproject.toml:34-43`

```yaml
# ci.yml — 플래그 직접 지정
run: mypy src/ --ignore-missing-imports

# pyproject.toml — 엄격하게 설정
[tool.mypy]
disallow_untyped_defs = true
warn_return_any = true
ignore_missing_imports = true
```

CI 명령에서 `--ignore-missing-imports` 플래그를 명시하면 `pyproject.toml`의 나머지 엄격 설정이 **부분적으로 우회**될 수 있다. 서드파티 라이브러리 타입 오류 사각지대 존재.

**권장**: `mypy src/` — 설정 파일만 사용 (플래그 제거).

---

### CI-3. ruff/black/isort 실행 순서 역방향 (위험도: 🟠 중간)

**파일**: `.github/workflows/ci.yml:65-69`

```yaml
- name: Black    # 포맷 체크
- name: Ruff     # 린트
- name: isort    # import 순서
```

**올바른 순서**: `isort → black → ruff`. 현재 isort가 마지막에 실행되어 import 순서를 재정렬한 후 Black이 다시 포맷을 바꾸는 순환 충돌이 발생할 수 있다. 간헐적 CI 실패 원인.

---

### CI-4. 배포 이미지 태깅 — `latest`만 사용, 버전 추적 불가 (위험도: 🔴 높음)

**파일**: `deploy.yml:44-47, 117`

```yaml
# 빌드 시 태그 3개 생성
tags: |
  type=sha,format=long      # sha 태그 생성하지만...
  type=ref,event=branch
  latest

# 배포 시 — latest만 사용
"AI_SERVER_IMAGE=...ai-server:latest"
```

commit SHA 태그가 생성되지만 배포에서 무시된다. 다음 커밋이 `latest`를 덮어쓰면 이전 버전 복구 불가. 롤백 시 수동으로 이미지 태그를 찾아야 한다.

**권장**: `type=sha,format=short` 태그로 배포, `latest` 태그는 참조용으로만 유지.

---

### CI-5. 헬스체크 없는 배포 — 즉시 장애 미감지 (위험도: 🔴 높음)

**파일**: `deploy.yml:119-120`

```bash
sudo docker compose pull ai-server
sudo docker compose up -d --no-deps ai-server
# ← 헬스체크 대기 없음. 컨테이너 시작=배포 완료로 처리
```

`docker-compose.yml`에 `healthcheck`가 정의되어 있지만, 배포 스크립트에서 대기하지 않는다. 컨테이너가 시작됐지만 내부 초기화(DB 연결, 캐시 로드) 실패 상태에서 "배포 완료"가 반환될 수 있다.

**권장**:
```bash
sudo docker compose up -d --no-deps ai-server
sudo docker compose exec ai-server python -c "import uvicorn" && \
  curl -sf http://localhost:8000/health || exit 1
```

---

### CI-6. 롤백 전략 전무 (위험도: 🔴 높음)

**파일**: `deploy.yml` 전체

- 이전 이미지 보존 없음 (`docker image prune -f --filter "until=24h"` — 24시간 이내도 삭제)
- 배포 실패 자동 감지 없음
- 수동 롤백 스크립트 없음

배포 후 24시간 이내 장애를 발견해도 이미 이전 이미지가 삭제될 수 있다.

---

### CI-7. graceful shutdown 추적 누락 (위험도: 🟠 중간)

**파일**: `deploy.yml:119-120`, `docker-compose.yml:30-31`

```yaml
# docker-compose.yml
stop_grace_period: 310s    # 기존 컨테이너 종료에 최대 310초 허용

# deploy.yml — 즉시 진행
docker compose up -d --no-deps ai-server
```

`docker compose up -d`는 새 컨테이너를 시작하면서 기존 컨테이너 종료를 기다리지 않는다. 최대 310초간 두 컨테이너가 동시에 실행될 수 있다.

---

### CI-8. develop 브랜치 직접 프로덕션 배포 (위험도: 🟠 중간)

**파일**: `deploy.yml:3-5`

```yaml
on:
  push:
    branches:
      - develop   # ← main이 아닌 develop에서 직접 배포
```

CLAUDE.md의 브랜치 전략(`main ← 3명 전원 승인`)과 불일치. develop push만으로 EC2 자동 배포 트리거.

---

### CI-9. pip 캐시 분리로 인한 비효율 (위험도: 🟡 낮음)

**파일**: `ci.yml:25-31, 53-59`

- test job: `pip-3.11-hash` / `pip-3.12-hash` (Python 버전별 별도 캐시)
- lint job: `pip-lint-hash` (별도 캐시)

같은 패키지를 중복 설치한다. 매트릭스 Python 버전을 캐시 키에서 제거하면 공유 가능.

---

## 2. 시크릿/환경변수 보안 심층 분석

### SEC-1. deploy.yml — 평문 시크릿이 SSM 커맨드에 포함 (위험도: 🔴 극도로 높음)

**파일**: `deploy.yml:78-116`

```bash
aws ssm send-command \
  --parameters 'commands=[
    "printf '"'"'%s\n'"'"' '"'"'AWS_SECRET_ACCESS_KEY=${{ secrets.AWS_SECRET_ACCESS_KEY }}'"'"' >> .env",
    "printf '"'"'%s\n'"'"' '"'"'LANGCHAIN_API_KEY=${{ secrets.LANGCHAIN_API_KEY }}'"'"' >> .env",
    ...
  ]'
```

**3중 노출 경로**:
1. **AWS CloudTrail**: `ssm:SendCommand` 이벤트에 명령 파라미터(평문 시크릿 포함) 기록
2. **EC2 Shell History**: `~/.bash_history`에 평문 기록 가능
3. **SSM Command History**: AWS 콘솔 → Systems Manager → Run Command → History에서 조회 가능

전체 16개 이상 시크릿이 이 방식으로 주입됨.

**권장 대안**: AWS Secrets Manager / SSM Parameter Store에서 EC2에서 직접 읽기.
```bash
# EC2 내부에서 안전하게 로드
aws secretsmanager get-secret-value --secret-id mind-log/prod \
  --query SecretString --output text > .env
chmod 600 .env
```

---

### SEC-2. .env 파일 권한 미설정 (위험도: 🔴 높음)

**파일**: `deploy.yml:91-116`

`.env` 파일 생성 후 권한 설정이 없다. 기본 생성 권한(644)이면 동일 서버의 다른 프로세스(nginx, monitoring agent 등)가 읽을 수 있다.

**권장**: 마지막 줄에 `chmod 600 .env && chown ubuntu:ubuntu .env` 추가.

---

### SEC-3. ALLOWED_ORIGINS 와일드카드 기본값 (위험도: 🔴 높음)

**파일**: `config/loader.py:292-293`

```python
origins_str = os.getenv("ALLOWED_ORIGINS", "*")   # ← 와일드카드 기본값
```

`ALLOWED_ORIGINS` 환경변수 미설정 시 CORS가 모든 도메인에서 허용된다. GitHub Actions 시크릿에 미등록 시 자동으로 `*`가 적용됨.

`BACKEND_API_URL`의 경우 빈 문자열 체크 패턴이 있지만, `ALLOWED_ORIGINS`는 없다:
```python
# 불일치: BACKEND_API_URL은 빈 문자열 체크, ALLOWED_ORIGINS는 미체크
val = os.getenv("BACKEND_API_URL", "").strip()
return val if val else "http://localhost:8080/..."   # ← 빈 문자열 방어 있음

origins_str = os.getenv("ALLOWED_ORIGINS", "*")    # ← 방어 없음
```

---

### SEC-4. git history에 시크릿 잔존 (위험도: 🔴 높음)

**파일**: `docs/SECURITY_REMEDIATION_TRACKER.md:15-17`

| 항목 | 상태 | 커밋 |
|------|------|------|
| KT Cloud API 토큰 3개 | ❌ git history 잔존 | 현재 커밋 이전 |
| LangSmith API 키 | ❌ git history 잔존 | `ffa54f8` |

`git log -p | grep "lsv2_pt_"` 또는 `KT_CLOUD` 검색으로 누구나 추출 가능.

**즉시 조치 필요**: 토큰 로테이션 + `git filter-repo` 실행 (Plan #28, 3인 합의 필요).

---

### SEC-5. AWS 크레덴셜 — 장기 Access Key 사용 (위험도: 🔴 높음)

**파일**: `deploy.yml:70-72`

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

장기 크레덴셜(Access Key)을 GitHub Secret에 저장. GitHub 계정 침해 시 AWS 계정 전체 노출.

**권장**: GitHub OIDC + IAM Role로 전환 (임시 크레덴셜, 로테이션 불필요).
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::ACCOUNT:role/GitHubActionsRole
    aws-region: ap-northeast-2
```

---

### SEC-6. deploy.yml 누락 시크릿 — 서비스 미동작 (위험도: 🟠 중간)

**파일**: `deploy.yml:91-116`, 실제 코드 참조

| 환경변수 | 코드 참조 | deploy.yml 포함 | 영향 |
|---------|----------|:---:|------|
| `MYSQL_URL` | `loader.py:340` | ❌ | Backend DB 연결 불가 |
| `PINECONE_API_KEY` | `episode_memory.py:60` | ❌ | Episode Memory 오류 |
| `KT_CLOUD_KNOWLEDGE_PARSER_TOKEN` | `knowledge.py:44` | ❌ | Knowledge Agent 오류 |
| `KT_CLOUD_KNOWLEDGE_EMBEDDING_TOKEN` | `knowledge.py:47` | ❌ | Knowledge Agent 오류 |
| `KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN` | `knowledge.py:50` | ❌ | Knowledge Agent 오류 |
| `PINECONE_INDEX_KNOWLEDGE` | `knowledge.py:53` | ❌ | Knowledge Agent 오류 |

Knowledge Agent가 프로덕션에서 동작하지 않는 근본 원인 중 하나일 수 있다.

---

### SEC-7. KT Cloud 토큰 — deploy.yml 포함분과 미포함분 혼재 (위험도: 🟠 중간)

**파일**: `deploy.yml:108-113`, `.env.example:32-51`

| 토큰 | deploy.yml | git history 노출 | 비고 |
|------|:---:|:---:|------|
| KT_CLOUD_QUERY_TOKEN | ✅ 포함 | ⚠️ 노출 | 로테이션 필요 |
| KT_CLOUD_PASSAGE_TOKEN | ✅ 포함 | ⚠️ 노출 | 로테이션 필요 |
| KT_CLOUD_TEXTGEN_TOKEN | ✅ 포함 | ⚠️ 노출 | 로테이션 필요 |
| KT_CLOUD_KNOWLEDGE_PARSER_TOKEN | ❌ 미포함 | ⚠️ 노출 | 로테이션 + 배포 추가 필요 |
| KT_CLOUD_KNOWLEDGE_EMBEDDING_TOKEN | ❌ 미포함 | ⚠️ 노출 | 로테이션 + 배포 추가 필요 |
| KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN | ❌ 미포함 | ⚠️ 노출 | 로테이션 + 배포 추가 필요 |

---

### SEC-8. Neo4j 포트 외부 노출 (위험도: 🟠 중간)

**파일**: `docker-compose.yml:47-48`

```yaml
ports:
  - "7474:7474"   # Browser UI — 외부 노출
  - "7687:7687"   # Bolt — 외부 노출
```

EC2 보안 그룹에서 제한하지 않으면 외부에서 Neo4j 직접 접근 가능.

**권장**: `127.0.0.1:7474:7474` 또는 포트 바인딩 제거.

---

### SEC-9. S3 키 path traversal 방어 부재 (위험도: 🟠 중간)

**파일**: `src/agents/podcast/visualization.py:193-195`

```python
file_name = f"{user_id}_{uuid.uuid4().hex[:8]}.png"
s3_key = f"{upload_prefix}/{file_name}"
```

`user_id`에 `../` 포함 시 의도치 않은 S3 경로에 파일 저장 가능. AI 서버 측 경로 정제 없음.

---

### SEC-10. 한국어 프롬프트 인젝션 패턴 미감지 (위험도: 🟠 중간)

**파일**: `src/agents/shared/input_sanitizer.py`

감지 패턴 6개가 모두 영어 기반. `이전 지시를 무시해`, `시스템 프롬프트를 보여줘` 같은 한국어 인젝션 패턴 무방비.

또한 감지 후 입력 자체를 정제하지 않고 `safety_flags`에 표시만 한다. 원본 `user_input`이 그대로 Safety/Emotion/Reasoning 에이전트 프롬프트에 삽입된다.

---

## 3. 동시성 및 경합 조건 심층 분석

### CON-1. Circuit Breaker — check-then-act 경합 (위험도: 🔴 높음)

**파일**: `src/agents/shared/llm_client.py:140-156`

```python
_breakers: dict[str, _CircuitBreaker] = {}  # 클래스 변수 — 모든 인스턴스 공유

@classmethod
def _get_breaker(cls, provider: str) -> _CircuitBreaker:
    if provider not in cls._breakers:         # CHECK — 비원자적
        cls._breakers[provider] = _CircuitBreaker(...)   # ACT
    return cls._breakers[provider]
```

두 코루틴이 동시에 `if` 체크를 통과하면 같은 `provider`에 Circuit Breaker 2개가 생성된다. 하나가 덮어써지면 실패 카운터가 리셋되어 Circuit Breaker가 제때 열리지 않는다.

**재현 조건**: 앱 시작 직후 동시 LLM 요청 + 동일 provider 첫 사용

**권장 수정**:
```python
_breaker_lock: asyncio.Lock = asyncio.Lock()

@classmethod
async def _get_breaker(cls, provider: str) -> _CircuitBreaker:
    if provider not in cls._breakers:
        async with cls._breaker_lock:
            if provider not in cls._breakers:   # Double-checked locking
                cls._breakers[provider] = _CircuitBreaker(...)
    return cls._breakers[provider]
```

---

### CON-2. Bedrock Semaphore 초기화 경합 (위험도: 🔴 높음)

**파일**: `src/agents/shared/llm_client.py:294-298`

```python
_bedrock_semaphore: asyncio.Semaphore | None = None

if LLMClient._bedrock_semaphore is None:      # CHECK
    limit = bedrock_config.get("concurrency_limit", 10)
    LLMClient._bedrock_semaphore = asyncio.Semaphore(int(limit))  # ACT
```

CON-1과 동일한 패턴. 초기화 순간에 두 코루틴이 동시 진입하면 Semaphore 2개 생성 → concurrency_limit 우회.

**재현 조건**: FastAPI 시작 직후 동시 Bedrock 요청 + provider 첫 사용

---

### CON-3. StoriesStore — 세션 생성/삭제 경합 (위험도: 🟠 중간)

**파일**: `src/api/stories_store.py:30-33, 70-72`

```python
def _get_or_create(self, session_id: str) -> dict[str, Any]:
    if session_id not in self._store:         # CHECK
        self._store[session_id] = {           # ACT — asyncio.Event() 생성 경합 가능
            "event": asyncio.Event(),
            "data": None,
        }
    return self._store[session_id]

def delete_session(self, session_id: str) -> None:
    self._store.pop(session_id, None)         # 동시 write 중 삭제 가능
```

`wait_for_stories()` 타임아웃 직후 `delete_session()` 실행 중에 새 요청이 동일 `session_id`로 `set_stories()`를 호출하면 경합 발생.

---

### CON-4. TIER 1 취소 후 태스크 완전 정리 미보장 (위험도: 🟠 중간)

**파일**: `src/graph/workflow.py:216-241`

```python
# run_with_cancel 내부
cancel_waiter = asyncio.create_task(cancel_event.wait())
task = asyncio.create_task(coro)

done, _ = await asyncio.wait(
    [task, cancel_waiter],
    return_when=asyncio.FIRST_COMPLETED,
)

if cancel_waiter in done:
    task.cancel()
    # ← task의 CancelledError 처리 대기 없음
    # 진행 중인 LLM API 호출은 계속 실행됨
```

CRISIS 발생 시 `task.cancel()` 호출 후 즉시 반환. 이미 진행 중인 Emotion/Content/Reasoning의 Bedrock API 호출이 완료될 때까지 불필요한 토큰이 소비된다.

---

### CON-5. asyncio.wait_for 중첩 타임아웃 — 상태 소실 (위험도: 🟠 중간)

**파일**: `src/graph/workflow.py:78-96, 370-390`

```python
# _with_timeout() — 개별 에이전트 타임아웃
except asyncio.TimeoutError:
    return {}   # 빈 dict 반환 → partial_results에 미반영

# tier1_podcast_fan_out — 전체 TIER 타임아웃
except asyncio.TimeoutError:
    merged = partial_results  # 이미 {} 반환한 에이전트 결과는 없음
```

내부 타임아웃으로 `{}`가 반환되면 해당 에이전트 결과가 `partial_results`에 포함되지 않는다. 이후 전체 TIER 타임아웃이 발생해도 소실된 데이터는 복구 불가. `batch_validator` 타임아웃 시 검증 없이 강제 통과.

---

### CON-6. asyncio.as_completed 중 예외 발생 시 미완료 태스크 누수 (위험도: 🟡 낮음)

**파일**: `src/graph/workflow.py:305-330`

`asyncio.as_completed(tasks)`에서 예외 발생 후 `break` 시 나머지 미완료 태스크가 orphaned 상태로 남을 수 있다. 현재 코드에서 `finally` 정리 블록이 있어 실질적 위험은 낮지만, 복잡한 예외 경로에서 누수 가능성 존재.

---

## 4. 인스턴스 생명주기 및 리소스 관리

### INS-1. boto3 클라이언트 — 요청마다 신규 생성 (위험도: 🔴 높음)

**파일**: `src/agents/shared/llm_client.py:264-298`, `src/agents/podcast/visualization.py:118-121`

```python
# llm_client.py — 매 LLMClient 인스턴스마다 boto3 클라이언트 생성
def _init_bedrock_client(self, settings: Any) -> None:
    self._bedrock_client = boto3.client(**kwargs)

# visualization.py — 매 VisualizationAgent 인스턴스마다 S3 클라이언트 생성
self.s3_client = boto3.client("s3", region_name=...)
```

에이전트는 요청마다 새 인스턴스가 생성된다(`workflow.py` 노드 함수). 동시 요청 100개 = boto3 클라이언트 100개 생성. 각 클라이언트가 내부 HTTP 연결 풀(기본 10 connections)을 보유하므로 최악의 경우 1,000개 연결.

**잠재 영향**: 메모리 선형 증가 → OOM, AWS STS 토큰 캐시 미활용, 불필요한 TLS 핸드셰이크

**권장**: boto3 Session을 FastAPI lifespan에서 초기화하고 공유.
```python
# main.py lifespan
session = boto3.Session(region_name="ap-northeast-2")
bedrock_client = session.client("bedrock-runtime")
app.state.bedrock_client = bedrock_client
```

---

### INS-2. httpx.AsyncClient — 11곳에서 요청마다 생성 (위험도: 🔴 높음)

**파일**: `episode_memory.py` (5곳), `knowledge.py` (6곳)

```python
# 매 API 호출마다 새 클라이언트 생성
async with httpx.AsyncClient() as client:
    r = await client.post(...)
```

하나의 에피소드 메모리 저장 요청 중 최대 5개, 지식 검색 중 최대 6개 AsyncClient 생성. 동시 요청 시:

```
동시 요청 50개 × 에이전트당 5개 AsyncClient
= 250개 httpx.AsyncClient × 내부 100-connection 풀
→ 시스템 파일 디스크립터 한계 도달 가능 (ulimit -n: 1024~4096)
```

**잠재 영향**: `"Too many open files"` → 새 요청 실패, TCP TIME_WAIT 소켓 누적

**권장**:
```python
# 클래스 레벨 싱글톤
class EpisodeMemoryAgent(BaseMemoryAgent):
    _http_client: httpx.AsyncClient | None = None
    
    @classmethod
    async def _get_client(cls) -> httpx.AsyncClient:
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_connections=20)
            )
        return cls._http_client
```

---

### INS-3. LangGraph StateGraph — 체크포인터 미설정 (위험도: 🟠 중간)

**파일**: `src/api/main.py:67-70`, `src/graph/workflow.py:781-839`

```python
compiled_graph = compile_graph("unified")   # checkpointer=None (기본값)
```

체크포인터 없이 실행 시, 각 노드의 중간 상태 복사본이 가비지 컬렉션 전까지 메모리에 유지된다. TIER 1 병렬 4개 노드 × state 복사(~50 KB) × 동시 요청 수 = 메모리 누적.

```
TIER 1: 4개 노드 × 50 KB × 100 동시 요청 = 20 MB (순간)
TIER 전체: 9개 노드 × 50 KB × 100 = 45 MB (순간)
가비지 컬렉션 지연 시 실제 100-200 MB 사용 가능
```

---

## 5. 캐시 및 메모리 누수

### MEM-1. StoriesStore — 모든 종료 경로에서 세션 미정리 (위험도: 🔴 높음)

**파일**: `src/api/stories_store.py:42-68`, `src/graph/workflow.py:555-562`

```python
# stories_store.py — TimeoutError/CancelledError 시 delete 없음
async def wait_for_stories(self, session_id, timeout):
    entry = self._get_or_create(session_id)
    try:
        await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
        return entry["data"]
    except asyncio.TimeoutError:
        return None     # ← delete_session() 미호출
    except asyncio.CancelledError:
        return None     # ← delete_session() 미호출

# workflow.py:560 — 정상 경로에서만 정리
data = await stories_store.wait_for_stories(session_id, ...)
stories_store.delete_session(session_id)  # ← 위 예외 발생 시 이 줄 미실행
```

TIER 1~3에서 예외 발생 → `wait_for_stories()` 자체가 호출되지 않음 → `_get_or_create()`로 생성된 엔트리 영구 잔류.

HTTP 클라이언트 연결 끊김 → anyio CancelledError 전파 → `delete_session()` 미실행.

**메모리 누적 계산**:
```
세션당 Entry 크기: asyncio.Event + dict ≈ 500 bytes ~ 100 KB (stories 데이터 포함 시)
24시간 운영 중 미정리 세션 1,000개 × 100 KB = 100 MB 누적
```

**권장**:
```python
async def wait_for_stories(self, session_id: str, timeout: float):
    entry = self._get_or_create(session_id)
    try:
        await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
        return entry["data"]
    except (asyncio.TimeoutError, asyncio.CancelledError) as e:
        logger.warning("[StoriesStore] 비정상 종료 — session=%s", session_id)
        return None
    finally:
        self.delete_session(session_id)   # ← 모든 경로에서 정리
```

---

### MEM-2. requirements.txt 버전 비고정 — 재현 불가 버그 원천 (위험도: 🔴 높음)

**파일**: `requirements.txt` 전체

```
langgraph>=0.2.0          # 0.3.x breaking change 가능
langchain-core>=0.3.0     # 0.4.x 내부 API 변경
anthropic>=0.40.0         # SDK major 변경
pydantic>=2.0.0           # model_validate 동작 변경
fastapi>=0.110.0          # 1.0 전환 시 breaking change
boto3>=1.26.0             # Bedrock API 변경 가능
```

lock 파일 없음. CI 통과 후 다른 버전이 프로덕션에 설치될 수 있다. 재현 불가능한 버그의 구조적 원인.

---

### MEM-3. LangSmith 콜백 — 요청별 생성 (위험도: 🟡 낮음)

**파일**: `src/monitoring/callbacks.py:70-96`

```python
class MindLogTelemetryCallback(BaseCallbackHandler):
    def __init__(self, ...):
        self._events: list[MonitoringEvent] = []   # 이벤트 누적
        self.metrics = PipelineMetrics(...)         # 메트릭 누적
```

파이프라인 실행마다 콜백 인스턴스가 생성되고 `_events`, `metrics` 리스트가 누적된다. 실행 완료 후 즉시 GC 대상이 되므로 현재는 안전하나, LangSmith 활성화 시 내부 run_id 캐시가 추가로 메모리를 사용할 수 있다.

---

### MEM-4. asyncio.iscoroutinefunction — Python 3.16 제거 예정 (위험도: 🟡 낮음)

**발생 위치**: `tests/graph/test_e2e_mock_pipeline.py` (LangChain Core 내부에서 68회 경고)

```
DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated — Python 3.16에서 제거
```

현재는 LangChain Core 내부에서 발생하므로 직접 수정 불가. 의존성 업그레이드 또는 Python 3.16 이전에 대응 필요.

---

## 6. 문서-코드 불일치 전수 조사

### DOC-1. 에이전트 모델 — 4개 에이전트 다운그레이드 미반영 (위험도: 🔴 높음)

**파일**: `CLAUDE.md:36-47` vs `config/settings.yaml:66-148`

| 에이전트 | CLAUDE.md 기술 | settings.yaml 실제값 | 변경일 |
|---------|:---:|:---:|:---:|
| Intent Classifier | Sonnet 3.7 | **haiku** | 2026-04-14 |
| Safety Agent | Sonnet 3.7 | **sonnet** | 2026-04-14 |
| Podcast Reasoning | Sonnet 3.7 | **sonnet** | 2026-04-14 |
| Script Personalizer | Sonnet 3.7 | **sonnet** | 2026-04-14 |

4개 에이전트가 APAC 지연 급증으로 다운그레이드됐으나 CLAUDE.md가 미갱신.

---

### DOC-2. AgentState 신규 필드 4개 — CLAUDE.md 미반영 (위험도: 🔴 높음)

**파일**: `CLAUDE.md:172-175` vs `src/models/agent_state.py:31-62`

| 신규 필드 | 타입 | 추가 시점 | CLAUDE.md |
|----------|------|----------|:---:|
| `structured_input` | `dict[str, Any]` | 최근 추가 | ❌ 누락 |
| `learning_pattern` | `dict[str, Any] \| None` | 최근 추가 | ❌ 누락 |
| `memory_text` | `str` | PR #86 | ❌ 누락 |
| `memory_metadata` | `dict[str, Any]` | PR #86 | ❌ 누락 |

AgentState는 Protected File(3인 합의 필요)이므로 변경 시 문서 동시 업데이트가 필수. 누락됨.

---

### DOC-3. CLAUDE.md 개발자별 쓰기 가능 필드 — 신규 필드 미반영 (위험도: 🟠 중간)

**파일**: `CLAUDE.md:필드 접근 규칙 테이블`

| 미반영 항목 | 실제 코드 |
|-----------|---------|
| Script Personalizer가 `memory_write`, `memory_text`, `memory_metadata` 쓰기 | `script_personalizer.py:184-193` |
| Podcast Reasoning이 `memory_results`, `knowledge_results` 쓰기 | `podcast_reasoning.py:86-88` |
| `wait_for_stories` 노드 — TIER 3→4 사이 삽입 | `workflow.py:641` |

---

### DOC-4. CLAUDE.md 구현 현황 테스트 수 불일치 (위험도: 🟠 중간)

**파일**: `CLAUDE.md:505-509`

```
### 테스트 현황
```
583 passed
```
```

실제 현황:
- `pytest --collect-only` 결과: **596 collected, 39 deselected** (live 제외)
- 총 정의된 테스트: 635개 (`@pytest.mark.live` 39개 포함)

문서의 "583"은 이전 시점의 수치.

---

### DOC-5. CLAUDE.md API 타임아웃 기술 불일치 (위험도: 🟠 중간)

**파일**: `CLAUDE.md:백엔드 API 규약 섹션` vs `config/settings.yaml:188-190`

| 항목 | CLAUDE.md | settings.yaml |
|------|:---:|:---:|
| 기본 타임아웃 | "5초" | `timeout: 10` |
| LLM 타임아웃 | "30초" | `llm_timeout: 60` |

PR #116에서 2배 확장됐으나 CLAUDE.md 미갱신.

---

### DOC-6. AGENT_OUTPUT_CONTRACT.md — 신규 필드 4개 누락 (위험도: 🟠 중간)

**파일**: `docs/architecture/AGENT_OUTPUT_CONTRACT.md`

계약 문서에서 `structured_input`, `learning_pattern`, `memory_text`, `memory_metadata` 4개 필드 누락. Protected File 변경 시 계약 문서 동시 갱신 필수.

---

### DOC-7. 프롬프트 버전 핀닝 — Visualization 누락 (위험도: 🟡 낮음)

**파일**: `CLAUDE.md:448-456` vs `config/settings.yaml:194-204`

```
# CLAUDE.md — 3개만 명시
Content Analyzer: v2.2.0 / Podcast Reasoning: v3.2.0 / Batch Validator: v2.3.0

# settings.yaml — Visualization도 핀닝됨
visualization: "1.19.0"   # ← CLAUDE.md에서 누락
```

---

### DOC-8. CLAUDE.md CRISIS 심화 응답 생성 주체 불일치 (위험도: 🟡 낮음)

**파일**: `CLAUDE.md:76-90` vs `src/graph/workflow.py:247-275`

```
# CLAUDE.md — Safety Agent가 직접 심화 응답 생성
"Safety 심화 모드 진입 → Safety가 직접 위기 응답 생성"

# 실제 코드 — workflow.py의 _safety_deep_crisis() 함수가 응답 조립
async def _safety_deep_crisis(state: AgentState) -> dict[str, Any]:
    safety_result = state.get("safety_result", {})
    # Safety 결과에서 required_in_script를 추출하여 조립
```

---

### DOC-9. API_SPEC.md 갱신일 오래됨 (위험도: 🟡 낮음)

**파일**: `docs/architecture/API_SPEC.md:3-6`

갱신일이 `2026-04-08`로 최근 6일간 변경 미반영.

---

## 7. 전체 우선순위 종합표

### 🔴 P0 — 즉시 (안전/보안/서비스 가용성 직접 영향)

| # | 이슈 | 카테고리 | 파일 |
|---|------|---------|------|
| 1 | deploy.yml 시크릿 평문 SSM 노출 | 보안 | deploy.yml:78-116 |
| 2 | git history KT Cloud 토큰/LangSmith 키 잔존 | 보안 | SECURITY_TRACKER |
| 3 | ALLOWED_ORIGINS 와일드카드 기본값 | 보안 | loader.py:292 |
| 4 | AWS Access Key 장기 크레덴셜 사용 | 보안 | deploy.yml:70-72 |
| 5 | deploy.yml 롤백 전략 전무 | CI/CD | deploy.yml |
| 6 | 배포 헬스체크 부재 | CI/CD | deploy.yml:119-120 |
| 7 | StoriesStore 세션 미정리 메모리 누수 | 메모리 | stories_store.py:42-68 |
| 8 | CI Job 의존성 부재 | CI/CD | ci.yml:13-87 |

### 🟠 P1 — 단기 (1~2주, 품질/안정성 개선)

| # | 이슈 | 카테고리 | 파일 |
|---|------|---------|------|
| 9 | Circuit Breaker 초기화 경합 | 동시성 | llm_client.py:140-156 |
| 10 | Bedrock Semaphore 초기화 경합 | 동시성 | llm_client.py:294-298 |
| 11 | httpx.AsyncClient 11곳 요청마다 생성 | 리소스 | episode_memory.py, knowledge.py |
| 12 | boto3 클라이언트 요청마다 생성 | 리소스 | llm_client.py, visualization.py |
| 13 | requirements.txt 버전 비고정 | 의존성 | requirements.txt |
| 14 | .env 파일 권한 미설정 | 보안 | deploy.yml |
| 15 | deploy.yml KnowledgeAgent 시크릿 6개 누락 | 보안/기능 | deploy.yml |
| 16 | CLAUDE.md 에이전트 모델 4개 미갱신 | 문서 | CLAUDE.md |
| 17 | AgentState 신규 필드 4개 문서 미반영 | 문서 | CLAUDE.md |
| 18 | TIER 타임아웃 중첩 상태 소실 | 동시성 | workflow.py:78-96 |
| 19 | Neo4j 포트 외부 노출 | 보안 | docker-compose.yml:47-48 |
| 20 | ruff/black/isort 실행 순서 역방향 | CI/CD | ci.yml:65-69 |

### 🟡 P2 — 중기 (프로젝트 완성도)

| # | 이슈 | 카테고리 | 파일 |
|---|------|---------|------|
| 21 | 배포 이미지 태깅 — SHA 기반 전환 | CI/CD | deploy.yml:44-47 |
| 22 | develop → main 기반 배포 전환 | CI/CD | deploy.yml:3-5 |
| 23 | S3 path traversal 방어 추가 | 보안 | visualization.py:193-195 |
| 24 | 한국어 인젝션 패턴 추가 | 보안 | input_sanitizer.py |
| 25 | graceful shutdown 배포 추적 | CI/CD | deploy.yml:119-120 |
| 26 | StoriesStore 경합 조건 | 동시성 | stories_store.py:30-33 |
| 27 | TIER 1 취소 태스크 정리 완전성 | 동시성 | workflow.py:216-241 |
| 28 | AGENT_OUTPUT_CONTRACT.md 신규 필드 동기화 | 문서 | |
| 29 | CLAUDE.md 테스트 수/타임아웃 갱신 | 문서 | CLAUDE.md |
| 30 | mypy CI 설정 정합성 | CI/CD | ci.yml:71 |
| 31 | pip 캐시 통합 | CI/CD | ci.yml:25-59 |

### 📋 P3 — 장기/합의 필요

| # | 이슈 | 조건 |
|---|------|------|
| 32 | git history 민감정보 제거 (Plan #28) | 3인 합의 후 실행 |
| 33 | AWS OIDC + IAM Role 전환 | 인프라팀 협력 |
| 34 | AWS Secrets Manager 이관 | 인프라팀 협력 |
| 35 | LangGraph PostgresSaver 체크포인터 | DB 인프라 필요 |
| 36 | requirements.txt lock 파일 도입 | pip-tools/poetry 결정 필요 |

---

## 총평

**즉시 위험 (P0)**: 보안 관련 8건이 긴급. 특히 SSM 커맨드에 평문 시크릿 노출과 git history 잔존 토큰은 외부 서비스 침해 위험이 있으며, 서비스가 운영 중인 상태에서 실시간 위협.

**구조적 취약점**: httpx/boto3 클라이언트 반복 생성(11+개소)과 StoriesStore 메모리 누수는 트래픽 증가 시 시스템 안정성에 직접 영향. 현재 트래픽 수준에서는 잠재되어 있으나 임계점 도달 시 급격한 성능 저하.

**문서 신뢰성**: AgentState Protected File 변경 시 문서 동시 갱신 프로세스가 누락되어 문서-코드 불일치 4건이 발생. 향후 Protected File 변경 프로세스에 문서 갱신 체크리스트 추가 필요.

---

*이 보고서는 코드 수정 없이 조사/분석만 수행한 결과물입니다.*  
*분석 기준일: 2026-04-15 | Deep Structural Review v1*

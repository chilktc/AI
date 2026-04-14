# 구조적 수정 구현 계획서 (v2)

**작성일**: 2026-04-15 17:00  
**기준 보고서**: `docs/reports/DEEP_STRUCTURAL_REVIEW_2026-04-15.md`  
**최종 태스크**: 18개 (서브에이전트 교차 검증 후 과잉구현 9개 제거)  
**작업 유형**: 구현 계획 전용 — 실제 코드 수정/커밋/푸시 없음

---

## 제거된 태스크 (과잉구현 판정)

서브에이전트 3개가 독립 교차 검증한 결과 이하 태스크 제거:

| 제거 태스크 | 제거 이유 |
|-----------|---------|
| TASK-B1 | AWS IAM 접근 불가 (사용자 결정) |
| TASK-B3 | AWS IAM 접근 불가 (사용자 결정) |
| TASK-A3 | `pyproject.toml`에 동일 설정 이미 존재 — CI 플래그 제거는 cosmetic only, 기능 변화 없음 |
| TASK-B5 | user_id는 UUID 포맷으로 Backend 검증 통과, S3 path traversal 위협 현실성 없음 |
| TASK-C1 | asyncio 단일 이벤트 루프에서 `_get_breaker()` 경합 불가능, `setdefault` 전환 이득 0 |
| TASK-C2 | `reset_class_state()` 는 테스트 편의 전용, 프로덕션 코드 오염 대비 이득 미미 |
| TASK-C3 | `_with_timeout()` 타임아웃 시 `{}` 반환은 이미 올바른 처리 (라우터가 verdict 없음 → FAIL 처리), sentinel 이득 없음 |
| TASK-D1 | 각 메서드가 다른 호스트로 요청 (KT Cloud, Pinecone, TextGen) → TCP 연결 재사용 불가, httpx 풀링 이득 없음 |
| TASK-D2 | boto3 클라이언트 생성 비용 ~2ms (전체 요청 1-5초 대비 0.5%), 싱글톤화 시 요청 격리 설계 원칙과 모순 |

> **유지 결정**: TASK-E3는 서브에이전트가 "코드 변경 없으면 제거" 라고 판단했으나,
> `src/models/agent_state.py` 실제 코드에 4개 필드(`structured_input`, `learning_pattern`,
> `memory_text`, `memory_metadata`)가 존재함을 직접 확인 → 문서 동기화 필요, **유지**.

---

## 목차

1. [브랜치 전략](#1-브랜치-전략)
2. [그룹 A — CI/CD 파이프라인](#2-그룹-a--cicd-파이프라인) (8개)
3. [그룹 B — 보안 및 설정](#3-그룹-b--보안-및-설정) (3개)
4. [그룹 C — 동시성 및 안전성](#4-그룹-c--동시성-및-안전성) (2개)
5. [그룹 D — 의존성 관리](#5-그룹-d--의존성-관리) (1개)
6. [그룹 E — 문서 동기화](#6-그룹-e--문서-동기화) (4개)
7. [전체 실행 순서](#7-전체-실행-순서)
8. [리뷰 포인트 최종 정리](#8-리뷰-포인트-최종-정리)

---

## 1. 브랜치 전략

| 브랜치명 | 그룹 | PR 조건 |
|---------|------|---------|
| `feature/infra-cicd-fix` | 그룹 A (CI/CD) | 3인 합의 |
| `feature/infra-security-fix` | 그룹 B (보안) | 3인 합의 |
| `feature/validation-concurrency-fix` | 그룹 C (동시성) | 3인 합의 (workflow.py 인접) |
| `feature/infra-deps-fix` | 그룹 D (의존성) | 리뷰 1인 이상 |
| `feature/infra-docs-sync` | 그룹 E (문서) | 3인 합의 (CLAUDE.md) |

**규칙**: 모든 브랜치는 `develop` 기준 생성, PR target은 `develop`.

---

## 2. 그룹 A — CI/CD 파이프라인

**수정 파일**: `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `scripts/rollback.sh`(신규)

---

### TASK-A1: CI Job 의존성 추가 🔴 P0

**이슈**: #8 (CI-1)  
**파일**: `.github/workflows/ci.yml:73`

**현재**:
```yaml
docker-build:
  runs-on: ubuntu-latest
  # needs 없음 — lint/test 실패해도 docker 빌드 진행
```

**변경**:
```yaml
docker-build:
  needs: [lint, test]   # 이 한 줄 추가
  runs-on: ubuntu-latest
```

**효과**: lint 또는 test 실패 시 docker-build 차단. matrix(3.11/3.12) 중 하나라도 실패 시 전체 실패.

---

### TASK-A2: Lint 실행 순서 정상화 🟠 P1

**이슈**: #20 (CI-3)  
**파일**: `.github/workflows/ci.yml:64-71`

**현재 순서**: Black → Ruff → isort  
**올바른 순서**: isort → Black → Ruff

**변경**:
```yaml
- name: isort
  run: isort --check-only .
- name: Black
  run: black --check .
- name: Ruff
  run: ruff check .
- name: mypy
  run: mypy src/ --ignore-missing-imports
```

**이유**: isort가 import 순서를 바꾼 후 Black이 재포맷하는 순환 충돌 방지. 간헐적 CI 실패 원인.

---

### TASK-A4: 배포 헬스체크 대기 추가 🔴 P0

**이슈**: #6 (CI-5)  
**파일**: `.github/workflows/deploy.yml:119-121`

**현재**:
```bash
"sudo docker compose pull ai-server",
"sudo docker compose up -d --no-deps ai-server",
"sudo docker image prune -f --filter \"until=24h\""
```

**변경** (헬스체크 루프 삽입, image prune 주기 72h로 연장):
```bash
"sudo docker compose pull ai-server",
"sudo docker compose up -d --no-deps ai-server",
"for i in $(seq 1 12); do if sudo docker compose exec -T ai-server python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" 2>/dev/null; then echo 'Health check passed'; break; fi; if [ $i -eq 12 ]; then echo 'Health check failed' && exit 1; fi; echo \"Attempt $i/12, retrying in 10s...\"; sleep 10; done",
"sudo docker image prune -f --filter \"until=72h\""
```

**포인트**:
- `docker-compose.yml:26`의 python urllib healthcheck와 동일 방식 (curl 미설치 우회)
- `-T` 플래그: SSM 비대화형 환경에서 TTY 비활성화
- prune 주기 24h → 72h: TASK-A5 롤백 이미지 보존과 연계

---

### TASK-A5: 롤백 전략 구축 🔴 P0

**이슈**: #5 (CI-6)  
**파일**: `.github/workflows/deploy.yml`, 신규 `scripts/rollback.sh`

**deploy.yml 변경** (docker up 직전에 현재 이미지 기록):
```bash
"PREV_IMAGE=$(sudo docker inspect mindlog-ai-service --format='{{.Config.Image}}' 2>/dev/null || echo 'none') && echo \"$PREV_IMAGE\" > /home/ubuntu/app/.prev_image",
"sudo docker compose up -d --no-deps ai-server",
```

**신규 파일** `scripts/rollback.sh`:
```bash
#!/bin/bash
# Mind-Log AI 서버 롤백 스크립트
# 사용법: ssh ubuntu@EC2_IP 'bash /home/ubuntu/app/scripts/rollback.sh'
PREV=$(cat /home/ubuntu/app/.prev_image 2>/dev/null)
if [ -z "$PREV" ] || [ "$PREV" = "none" ]; then
  echo "이전 이미지 정보 없음 — 롤백 불가"
  exit 1
fi
echo "롤백 대상: $PREV"
AI_SERVER_IMAGE=$PREV sudo docker compose up -d --no-deps ai-server
echo "롤백 완료: $PREV"
```

**포인트**: TASK-A6(SHA 태깅) 완료 후 `.prev_image`에 SHA 태그가 저장되어 더 정밀한 롤백 가능.

---

### TASK-A6: SHA 기반 이미지 태깅 🟡 P2

**이슈**: #21 (CI-4)  
**파일**: `.github/workflows/deploy.yml`

**문제**: 빌드 시 SHA 태그 생성하지만 배포는 `latest`만 사용 → 롤백 추적 불가.

**변경 1** (build-and-push job에 output 추가):
```yaml
jobs:
  build-and-push:
    outputs:
      sha-tag: ${{ steps.get-sha.outputs.sha_tag }}
    steps:
      # ... 기존 스텝 ...
      - name: Get short SHA
        id: get-sha
        run: echo "sha_tag=sha-$(echo ${{ github.sha }} | cut -c1-7)" >> $GITHUB_OUTPUT
```

**변경 2** (deploy job에서 SHA 태그 사용):
```bash
"printf '%s\n' 'AI_SERVER_IMAGE=${{ env.REGISTRY }}/${{ env.IMAGE_NAME_LOWER }}-ai-server:${{ needs.build-and-push.outputs.sha-tag }}' >> .env",
```

**포인트**: `latest` 태그는 캐시/참조용으로 계속 생성, 실제 배포는 SHA 태그 사용.

---

### TASK-A7: .env 파일 권한 설정 🟠 P1

**이슈**: #14 (SEC-2)  
**파일**: `.github/workflows/deploy.yml`

**현재**: `.env` 생성 후 chmod 미설정 (기본 644, 타 프로세스 읽기 가능).

**변경** (마지막 env 주입 라인 바로 뒤에 추가):
```bash
"chmod 600 /home/ubuntu/app/.env && chown ubuntu:ubuntu /home/ubuntu/app/.env",
```

**포인트**: SSM Run Command는 root로 실행 → `chown ubuntu:ubuntu` 필수. Docker Compose는 root로 실행하므로 읽기 가능.

---

### TASK-A8: Graceful Shutdown 명시적 추적 🟡 P2

**이슈**: #25 (CI-7)  
**파일**: `.github/workflows/deploy.yml:119`

**현재**: `docker compose up -d`가 기존 컨테이너 종료(310초 grace)를 기다리지 않음.

**변경** (up 직전에 기존 컨테이너 명시적 종료):
```bash
"sudo docker stop --time=30 mindlog-ai-service 2>/dev/null || true",
"sudo docker compose up -d --no-deps ai-server",
```

**포인트**:
- `--time=30`: 30초 내 종료 (310초 전체 대기 불필요, 대부분 LLM 요청 30초 내 완료)
- `|| true`: 초기 배포 시 컨테이너 없어도 오류 무시 (idempotent)

---

### TASK-A9: pip 캐시 키 통합 🟡 P2

**이슈**: #31 (CI-9)  
**파일**: `.github/workflows/ci.yml:53-59`

**현재**: lint job이 `pip-lint-{hash}` 별도 캐시 사용 → test job 설치 내용 재다운로드.

**변경** (lint job 캐시 키를 test job과 통일):
```yaml
# lint job
- name: Cache pip
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-3.11-${{ hashFiles('requirements-dev.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-3.11-
```

**검증됨**: pip는 ABI 태그(`cp311-cp311-linux_x86_64`)로 wheel을 구분 저장 → Python 버전 간 캐시 공유 충돌 없음. `pydantic-core`(Rust), `Pillow`(C) 등 C 확장도 버전별 별도 파일로 공존.

---

## 3. 그룹 B — 보안 및 설정

**수정 파일**: `config/loader.py`, `docker-compose.yml`, `src/agents/shared/input_sanitizer.py`

---

### TASK-B2: ALLOWED_ORIGINS 와일드카드 기본값 제거 🔴 P0

**이슈**: #3 (SEC-3)  
**파일**: `config/loader.py:291-293`

**현재**:
```python
origins_str = os.getenv("ALLOWED_ORIGINS", "*")
return [o.strip() for o in origins_str.split(",")]
```

**변경**:
```python
@property
def allowed_origins(self) -> list[str]:
    """CORS 허용 오리진 목록. 환경변수 미설정 시 localhost로 제한."""
    origins_str = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not origins_str:
        import logging
        logging.getLogger(__name__).warning(
            "ALLOWED_ORIGINS 미설정 — localhost:3000으로 제한. "
            "프로덕션 배포 전 반드시 설정하세요."
        )
        return ["http://localhost:3000", "http://localhost:8080"]
    return [o.strip() for o in origins_str.split(",") if o.strip()]
```

**포인트**:
- `BACKEND_API_URL` 빈 문자열 방어 패턴(loader.py 내 기존 코드)과 동일하게 구현
- 반환 타입 `list[str]` 유지 (공용 인프라 — 시그니처 변경 금지)
- 프로덕션에서 `ALLOWED_ORIGINS` 미설정 시 CORS 전면 개방 차단

---

### TASK-B4: Neo4j 포트 localhost 바인딩 🟠 P1

**이슈**: #19 (SEC-8)  
**파일**: `docker-compose.yml:47-48`

**현재**:
```yaml
ports:
  - "7474:7474"
  - "7687:7687"
```

**변경**:
```yaml
ports:
  - "127.0.0.1:7474:7474"
  - "127.0.0.1:7687:7687"
```

**포인트**:
- `ai-server`는 Docker 내부 네트워크(`neo4j:7687`)로 접속 — 이 변경과 무관하게 정상 동작
- EC2 보안그룹이 이미 차단 중이더라도 Defense in Depth 원칙상 2줄 수정으로 추가 방어
- 개발 환경에서 Browser UI 접근 필요 시: `ssh -L 7474:localhost:7474 ubuntu@EC2_IP`

---

### TASK-B6: 한국어 인젝션 패턴 추가 🟡 P2

**이슈**: #24 (SEC-10)  
**파일**: `src/agents/shared/input_sanitizer.py`

**현재**: 영문 6개 패턴만 존재.

**추가 패턴**:
```python
INJECTION_PATTERNS: list[str] = [
    # 기존 영문 패턴 유지
    r"ignore\s+(all\s+)?previous",
    r"(?:system|assistant)\s*:",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"(?:you\s+are|act\s+as)\s+(?:now|a)",
    r"(?:print|reveal|show)\s+(?:your|the)\s+(?:system|prompt|instructions)",
    # 한국어 인젝션 패턴 추가
    r"이전\s*(?:지시|명령|프롬프트)를?\s*(?:무시|삭제|잊어)",
    r"(?:시스템|system)\s*(?:프롬프트|지시|명령)를?\s*(?:보여|출력|알려)",
    r"지금부터\s*(?:너는|당신은|당신의\s*역할은)",
    r"(?:역할|페르소나)을?\s*바꿔",
    r"(?:개발자|관리자|admin)\s*모드",
    r"(?:DAN|단)\s*모드\s*(?:활성화|켜)",
]
```

**포인트**:
- input_sanitizer (패턴 감지) ≠ Safety Agent (LLM 위험도 평가) — 중복 아님, 다른 레이어
- 패턴에 동작 동사(`무시|삭제|잊어`) 명시 → `"이전 지시를 받았다"` 오탐 방지 처리됨
- `detect_injection()` 함수 시그니처 변경 없음 (공용 인프라)

---

## 4. 그룹 C — 동시성 및 안전성

**수정 파일**: `src/api/stories_store.py`, `src/graph/workflow.py`

---

### TASK-C4: StoriesStore CancelledError 누수 수정 🔴 P0

**이슈**: #7 (MEM-1)  
**파일**: `src/api/stories_store.py:42-68`

**정밀 분석**:

`workflow.py:559-560`에서 호출자가 이미 명시적 `delete_session()`을 호출:
```python
data = await stories_store.wait_for_stories(session_id, ...)
stories_store.delete_session(session_id)   # 정상/타임아웃은 여기서 처리됨
```

실제 누수 경로는 **CancelledError 단 하나** — HTTP 연결 종료로 `wait_for_stories_node` 자체가 취소되면 line 560에 도달 불가.

| 경로 | 현재 | 수정 후 |
|------|------|--------|
| 성공 | line 560 처리 ✓ | finally + line 560 (이중 pop, 무해) |
| TimeoutError | line 560 처리 ✓ | finally + line 560 (이중 pop, 무해) |
| **CancelledError** | **line 560 미도달 → 누수** ❌ | **finally 실행 → 정리** ✓ |

**변경**:
```python
async def wait_for_stories(self, session_id: str, timeout: float) -> dict[str, Any] | None:
    entry = self._get_or_create(session_id)
    try:
        await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
        return entry["data"]
    except asyncio.TimeoutError:
        logger.warning(
            "[StoriesStore] 타임아웃 — session_id=%s, timeout=%.0fs",
            session_id,
            timeout,
        )
        return None
    except asyncio.CancelledError:
        logger.info(
            "[StoriesStore] 취소 — session_id=%s (HTTP 연결 종료)",
            session_id,
        )
        return None
    finally:
        # CancelledError 경로: workflow.py:560 미도달 → 여기서 정리
        # 정상/Timeout: workflow.py:560과 이중 호출 → pop(None) 패턴으로 무해
        self.delete_session(session_id)
```

**포인트**: `delete_session()` 내부는 `self._store.pop(session_id, None)` — 이중 호출 안전.

---

### TASK-C5: TIER 1 취소 태스크 정리 완전성 🟡 P2

**이슈**: #27 (CON-4)  
**파일**: `src/graph/workflow.py:225-230`

**현재**:
```python
if cancel_waiter in done and task not in done:
    task.cancel()
    ...
    return (name, {})
```

**문제**: `task.cancel()` 후 `await task` 없음 → 취소된 코루틴(LLM 호출)의 정리 코드가 미실행될 수 있음.

**변경**:
```python
if cancel_waiter in done and task not in done:
    task.cancel()
    reason = (cancel_reason or {}).get("reason", "알 수 없음")
    logger.info("[CANCEL] %s 취소됨 (사유: %s)", name, reason)
    try:
        await task   # 취소 완료까지 대기
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("[CANCEL] %s 취소 중 예외: %s", name, e)
    return (name, {})
```

**포인트**:
- `workflow.py`는 Protected File 인접 — 3인 합의 필요
- `await task` 추가로 취소 완료까지 대기 → CRISIS 응답 시간 약간 증가 가능 (수십ms 수준)
- asyncio best practice: `cancel()` 후 반드시 `await` 권장

---

## 5. 그룹 D — 의존성 관리

**수정 파일**: `requirements.txt`

---

### TASK-D3: requirements.txt 상한 버전 핀닝 🟠 P1

**이슈**: #13 (MEM-2)  
**파일**: `requirements.txt` 전체

**현재**: 모든 의존성이 `>=` 하한만 존재 → major 버전 breaking change 시 재현 불가 버그 발생.

**변경** (현재 검증된 버전 기준 상한 추가):
```
# === Core ===
anthropic>=0.40.0,<1.0.0
boto3>=1.34.0,<2.0.0
langgraph>=0.2.0,<0.4.0           # 0.3.x까지 검증됨
langchain-core>=0.3.0,<0.4.0
langsmith>=0.2.0,<1.0.0
openai>=1.0.0,<2.0.0
python-dotenv>=1.0.0,<2.0.0
pydantic>=2.0.0,<3.0.0

# === Database ===
PyMySQL>=1.1.0,<2.0.0
pinecone>=3.0.0,<4.0.0
neo4j>=5.0.0,<6.0.0

# === API ===
fastapi>=0.110.0,<1.0.0
uvicorn>=0.30.0,<1.0.0
httpx>=0.27.0,<1.0.0

# === Image ===
Pillow>=10.0.0,<11.0.0

# === Monitoring ===
python-json-logger>=2.0.0,<3.0.0
prometheus-client>=0.20.0,<1.0.0

# === Utils ===
pyyaml>=6.0.0,<7.0.0
pdfplumber>=0.11.0,<1.0.0
```

**포인트**:
- 상한은 major 버전 경계에만 적용 → 유지보수 부담 최소화
- `langgraph<0.4.0`: 0.3.x에서 StateGraph API 변경 이력 있음 → 보수적 적용
- 완전한 재현성은 lock 파일로만 가능 (이 작업은 중간 단계)
- 적용 전 `pip install -r requirements.txt` 로컬 실행으로 현재 버전 확인 권장

---

## 6. 그룹 E — 문서 동기화

**수정 파일**: `CLAUDE.md`, `docs/architecture/AGENT_OUTPUT_CONTRACT.md`

---

### TASK-E1: CLAUDE.md 에이전트 모델 갱신 🟠 P1

**이슈**: #16 (DOC-1)  
**파일**: `CLAUDE.md` 에이전트 구성 테이블

**변경**: APAC 지연 급증(2026-04-14)으로 다운그레이드된 4개 에이전트 반영:

| 에이전트 | 현재 문서 | 실제(settings.yaml) |
|---------|:---:|:---:|
| Intent Classifier | Sonnet 3.7 | **Haiku** |
| Safety Agent | Sonnet 3.7 | Sonnet (다운그레이드) |
| Podcast Reasoning | Sonnet 3.7 | Sonnet (다운그레이드) |
| Script Personalizer | Sonnet 3.7 | Sonnet (다운그레이드) |

테이블 하단에 주석 추가:
```
> **모델 설정**: 실제 사용 모델은 `config/settings.yaml`이 SSOT.
> APAC 지연 급증(2026-04-14) 이후 일부 에이전트 다운그레이드 — settings.yaml 참조.
```

---

### TASK-E2: CLAUDE.md AgentState 신규 필드 4개 추가 🟠 P1

**이슈**: #17 (DOC-2)  
**파일**: `CLAUDE.md` AgentState 스키마 섹션

**현재 `src/models/agent_state.py`에 존재하지만 CLAUDE.md 미반영**:
- `structured_input: dict[str, Any]` — 프론트엔드 4가지 입력 구조체
- `learning_pattern: dict[str, Any] | None` — 백엔드 Push 학습 패턴 (nullable)
- `memory_text: str` — 저장할 에피소드 텍스트
- `memory_metadata: dict[str, Any]` — 저장 메타데이터

개발자별 쓰기 가능 필드 테이블도 함께 갱신:
```
개발자1 | 기존 + memory_write, memory_text, memory_metadata (Script Personalizer 담당)
```

---

### TASK-E3: AGENT_OUTPUT_CONTRACT.md 신규 필드 동기화 🟡 P2

**이슈**: #28 (DOC-6)  
**파일**: `docs/architecture/AGENT_OUTPUT_CONTRACT.md`

**근거**: `src/models/agent_state.py` 실제 코드에 4개 필드 존재 확인 (Protected File 변경 시 계약서 동시 갱신 의무).

AgentState 전체 필드 테이블에 추가:

| 필드 | 타입 | 설정 에이전트 | 설명 |
|------|------|-------------|------|
| `structured_input` | `dict[str, Any]` | Intent Classifier | 프론트엔드 4가지 입력 구조체 |
| `learning_pattern` | `dict[str, Any] \| None` | Intent Classifier | 백엔드 Push 학습 패턴 |
| `memory_text` | `str` | Script Personalizer | 저장할 에피소드 텍스트 |
| `memory_metadata` | `dict[str, Any]` | Script Personalizer | 저장 메타데이터 |

문서 헤더 갱신: `버전: v1.1 / 코드베이스 기준: 2026-04-15`

---

### TASK-E4: CLAUDE.md 테스트 수 / 타임아웃 / 프롬프트 버전 갱신 🟡 P2

**이슈**: #29 (DOC-4/5), DOC-7 포함  
**파일**: `CLAUDE.md`

**변경 1 — 테스트 수**:
```
583 passed
→
596 passed (39개 @pytest.mark.live 제외, 총 정의 635개)
```

**변경 2 — API 타임아웃** (PR #116 반영):
```
기본 5초, LLM 관련 30초
→
기본 10초, LLM 관련 60초 (PR #116 2배 확장, 2026-04-14)
```

**변경 3 — Visualization 프롬프트 버전 추가** (DOC-7):
```
현재 핀닝: CA v2.2.0 / PR v3.2.0 / BV v2.3.0
→
현재 핀닝: CA v2.2.0 / PR v3.2.0 / BV v2.3.0 / Visualization v1.19.0
```

---

## 7. 전체 실행 순서

### Phase 1 — 즉시 (P0) | 1~2일 | 병렬 작업 가능

```
독립 병렬 실행:
├── TASK-A1: ci.yml Job 의존성 (1줄)
├── TASK-B2: loader.py ALLOWED_ORIGINS (8줄)
└── TASK-C4: stories_store.py finally (3줄)

순차 실행 (TASK-A4 → A5 순서):
├── TASK-A7: .env 권한 (1줄, A4와 동일 PR)
├── TASK-A4: 헬스체크 대기 (~10줄)
└── TASK-A5: 롤백 전략 (~20줄 + rollback.sh)

문서 병렬:
└── TASK-E1 + E2: CLAUDE.md 갱신
```

### Phase 2 — 단기 (P1) | 1주

```
보안:
├── TASK-B4: Neo4j 포트 (2줄)
└── TASK-A2: lint 순서 정상화 (4줄 순서 변경)

의존성:
└── TASK-D3: requirements.txt 상한 핀닝

문서:
└── TASK-E3: AGENT_OUTPUT_CONTRACT.md 동기화
```

### Phase 3 — 중기 (P2) | 2~4주

```
CI/CD:
├── TASK-A6: SHA 기반 이미지 태깅
├── TASK-A8: graceful shutdown 명시
└── TASK-A9: pip 캐시 키 통합

보안:
└── TASK-B6: 한국어 인젝션 패턴 (+ 테스트 추가)

동시성:
└── TASK-C5: TIER 1 취소 await (3인 합의 후)

문서:
└── TASK-E4: 테스트 수 / 타임아웃 갱신
```

---

## 8. 리뷰 포인트 최종 정리

| 태스크 | 포인트 | 상태 |
|--------|-------|------|
| **TASK-A4** | SSM 비대화형 환경에서 bash 따옴표 이스케이프 복잡 → 별도 스크립트 파일로 분리 권장 | 확인 필요 |
| **TASK-A5** | TASK-A6(SHA 태깅) 완료 전에는 `.prev_image`에 `latest` 저장 → 롤백 시 동일 이미지로 롤백 가능성 | 수용 가능 |
| **TASK-B2** | `allowed_origins` property는 매 요청마다 호출됨 → 경고 로그 중복 방지를 위해 Settings `__init__`에서 1회 검증 고려 | 선택적 개선 |
| **TASK-B4** | EC2 보안그룹에서 이미 차단 중인지 확인 권장 (이 변경은 Docker 레이어 추가 방어) | 낮음 |
| **TASK-C4** | 성공 경로에서 `finally: delete_session()` 후 `workflow.py:560`에서 이중 호출 → `pop(None)` 패턴으로 무해 확인됨 | ✅ 안전 |
| **TASK-C5** | `await task` 추가로 CRISIS 취소 완료 대기 시간 증가 → 수십ms 수준, 허용 범위 | ✅ 수용 |
| **TASK-D3** | `langgraph<0.4.0` 상한 적용 전 현재 실제 설치 버전 `pip freeze`로 확인 필수 | 확인 필요 |

---

## 최종 태스크 일람표 (18개)

| 태스크 | 이슈# | 우선순위 | 파일 | 규모 |
|--------|------|---------|------|------|
| TASK-A1 | #8 (CI-1) | 🔴 P0 | ci.yml | 1줄 |
| TASK-A2 | #20 (CI-3) | 🟠 P1 | ci.yml | 4줄 순서 변경 |
| TASK-A4 | #6 (CI-5) | 🔴 P0 | deploy.yml | ~10줄 |
| TASK-A5 | #5 (CI-6) | 🔴 P0 | deploy.yml + scripts/ | ~20줄 |
| TASK-A6 | #21 (CI-4) | 🟡 P2 | deploy.yml | ~10줄 |
| TASK-A7 | #14 (SEC-2) | 🔴 P0 | deploy.yml | 1줄 |
| TASK-A8 | #25 (CI-7) | 🟡 P2 | deploy.yml | 2줄 |
| TASK-A9 | #31 (CI-9) | 🟡 P2 | ci.yml | 1줄 |
| TASK-B2 | #3 (SEC-3) | 🔴 P0 | loader.py | 8줄 |
| TASK-B4 | #19 (SEC-8) | 🟠 P1 | docker-compose.yml | 2줄 |
| TASK-B6 | #24 (SEC-10) | 🟡 P2 | input_sanitizer.py | 7줄 |
| TASK-C4 | #7 (MEM-1) | 🔴 P0 | stories_store.py | 3줄 |
| TASK-C5 | #27 (CON-4) | 🟡 P2 | workflow.py | 8줄 |
| TASK-D3 | #13 (MEM-2) | 🟠 P1 | requirements.txt | 18줄 수정 |
| TASK-E1 | #16 (DOC-1) | 🟠 P1 | CLAUDE.md | 4줄 + 주석 |
| TASK-E2 | #17 (DOC-2) | 🟠 P1 | CLAUDE.md | 8줄 추가 |
| TASK-E3 | #28 (DOC-6) | 🟡 P2 | AGENT_OUTPUT_CONTRACT.md | 4줄 추가 |
| TASK-E4 | #29 (DOC-4/5) | 🟡 P2 | CLAUDE.md | 3줄 수정 |

---

*구현 계획 전용 — 코드 수정/커밋/푸시 없음*  
*작성: 2026-04-15 17:00 | Structural Fix Plan v2 (서브에이전트 교차 검증 완료)*

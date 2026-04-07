# AWS 인스턴스 잔여 테스트 현황 확인 결과

## Context

Bedrock 모델 최적화 v2 계획서(`docs/superpowers/plans/2026-03-31-bedrock-model-optimization-v2.md`)의 **코드 수정(Task 1~5)은 모두 완료**되어 `develop`에 머지되어 있다. 그러나 **EC2 인스턴스에서 실제 테스트를 실행하는 Task 6~7은 미완료** 상태이다.

---

## 이미 해결된 이슈

| # | 이슈 | 해결 방법 |
|---|------|----------|
| **D-1** | EC2 OOM (Docker 빌드 시 메모리 부족) | GHCR 전환 — EC2에서 빌드하지 않고 `docker-compose pull`로 변경 (PR #40) |
| **D-4** | Docker 이미지 크기 최적화 | GHCR 전환으로 EC2 로컬 빌드 불필요 |
| **C-1** | settings.yaml bedrock_models APAC ID | `sonnet: apac.anthropic.claude-3-5-sonnet-...`, `opus: apac.anthropic.claude-sonnet-4-...`로 수정 완료 |
| **SSM** | git config `--global` → `--system` | PR #44 (commit fd44510) |
| **SSM** | git safe.directory 미설정 | PR #43 (commit 663941c) |
| **GHCR** | Container registry 인증 | PR #42 (commit 098f6e4) |

---

## 1. Bedrock 모델 최적화 v2 — EC2 테스트 (Task 6, 미실행)

`dev/live_tests/results/bedrock_model_test/` 디렉토리가 비어있음 — Phase 0~3 한 번도 실행되지 않음.

| 단계 | 명령어 | 목적 |
|------|--------|------|
| **Phase 0** | `python3 -m dev.live_tests.run_bedrock_model_test --phase 0` | 신규 모델 6종 연결 확인 (claude-sonnet-4, nova-pro, nova-lite + 이미지 3종) |
| **Phase 1** | `python3 -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 5` | 전체 벤치마크 (171 테스트) |
| **Phase 2** | scoring 스크립트 | 점수 산출 |
| **Phase 3** | `--phase 3 --optimal-config .../optimal_config.json` | 최적 모델 검증 (30 테스트) |

Phase 0 실패 모델은 목록에서 제거 후 Phase 1 진행.

---

## 2. settings.yaml 최적 모델 반영 (Task 7, Phase 3 완료 후)

Phase 3 결과(`optimal_config.json`) 기반으로 `config/settings.yaml` 에이전트별 모델 업데이트.

---

## 3. 미해결 이슈 — 심층 조사 결과 (2026-04-01)

### 실제 수정 필요: 3건

---

### D-2: deploy.yml fire-and-forget (HIGH — 확인됨)

- **파일**: `.github/workflows/deploy.yml:75-107`
- **현상**: `aws ssm send-command` 실행 후 결과 확인 없이 워크플로우 종료

**근본 원인 분석:**

`ssm send-command`는 명령을 EC2에 **전송만** 하고 즉시 반환한다. GitHub Actions는 전송 성공(`$? == 0`)만 확인하고 워크플로우를 종료한다. EC2에서 실제로 일어나는 작업(git fetch, docker pull, compose up 등)의 성공/실패는 **전혀 모니터링하지 않는다.**

```
GitHub Actions 관점:
  ssm send-command 호출 → API 응답 200 → "성공" ✓ (여기서 끝)

EC2 관점 (비동기):
  git fetch → docker login → docker pull → compose up → prune
  ↑ 이 중 어디서 실패해도 GitHub Actions는 이미 녹색 ✓ 표시
```

추가 발견:
- `--timeout-seconds` 미설정 → EC2에서 `docker pull`이 네트워크 이슈로 행(hang) 걸리면 무기한 대기
- 명령 출력 로그 수집 경로 없음 → 실패 시 EC2에 SSH 접속해서 수동 확인 필요
- 현재 워크플로우에 deploy 이후 헬스체크 단계도 없음

**수정 방향:**

`ssm send-command` 실행 후 `CommandId`를 캡처하고, `aws ssm wait command-executed`로 원격 명령 완료를 대기한다.

```yaml
- name: Deploy via AWS SSM
  run: |
    CMD_ID=$(aws ssm send-command \
      --instance-ids "${{ secrets.AWS_INSTANCE_ID }}" \
      --document-name "AWS-RunShellScript" \
      --timeout-seconds 600 \
      --parameters '...' \
      --region ${{ secrets.AWS_REGION }} \
      --query "Command.CommandId" \
      --output text)

    aws ssm wait command-executed \
      --command-id "$CMD_ID" \
      --instance-id "${{ secrets.AWS_INSTANCE_ID }}"
```

**이유:**
- AWS 기반 배포에서 SSM은 EC2 원격 실행의 표준 방식이며, `wait command-executed`는 AWS가 제공하는 공식 완료 대기 메커니즘
- `--timeout-seconds 600` (10분)은 docker pull + compose up에 충분하면서 무기한 행을 방지
- `wait`가 실패 시 GitHub Actions가 비정상 종료 코드를 받아 워크플로우도 실패 표시

---

### C-2: conftest_live.py 환경변수명 불일치 (HIGH — 확인됨)

- **파일**: `dev/live_tests/conftest_live.py:40-43`
- **현상**: Bedrock 프로바이더 사용 시 모델 오버라이드가 조용히 무시됨

**근본 원인 분석:**

`conftest_live.py`는 **단일 프로바이더(Anthropic 직접 API) 가정**으로 작성되었다. 모든 프로바이더에 대해 `LLM_MODEL_*` 환경변수만 설정한다.

그러나 `config/loader.py`의 모델 ID 조회 체인은 프로바이더별로 분리되어 있다:

| 프로바이더 | 환경변수 | 조회 함수 |
|-----------|---------|----------|
| Anthropic | `LLM_MODEL_{KEY}` | `get_model_id()` (loader.py:114-133) |
| Bedrock | `LLM_BEDROCK_MODEL_{KEY}` | `get_bedrock_model_id()` (loader.py:135-159) |
| OpenAI | `LLM_OPENAI_MODEL_{KEY}` | `get_openai_model_id()` |

conftest_live.py가 `LLM_MODEL_SONNET`을 설정해도, Bedrock 경로에서는 `LLM_BEDROCK_MODEL_SONNET`을 확인하므로 오버라이드가 적용되지 않는다. 결과적으로 `settings.yaml`의 기본값(`apac.anthropic.claude-3-5-sonnet-20241022-v2:0`)으로 폴백하여 **테스트는 성공하지만 의도한 모델이 아닌 다른 모델로 실행된다.**

**수정 방향:**

프로바이더별로 올바른 환경변수를 설정하도록 분기한다:

```python
if model_override:
    if provider == "bedrock":
        os.environ["LLM_BEDROCK_MODEL_SONNET"] = model_override
        os.environ["LLM_BEDROCK_MODEL_HAIKU"] = model_override
    elif provider == "openai":
        os.environ["LLM_OPENAI_MODEL_SONNET"] = model_override
        os.environ["LLM_OPENAI_MODEL_HAIKU"] = model_override
    else:
        os.environ["LLM_MODEL_SONNET"] = model_override
        os.environ["LLM_MODEL_HAIKU"] = model_override
```

**이유:**
- `config/loader.py`의 프로바이더별 조회 체인과 정확히 일치시켜야 오버라이드가 실제로 적용됨
- 현재 프로젝트는 AWS Bedrock 기반 운영이므로, Bedrock 경로가 올바르게 동작해야 Phase 0~3 벤치마크 결과를 신뢰할 수 있음

---

### D-3: deploy.yml .env 값 미인용 (MEDIUM — 실제 위험도 낮음)

- **파일**: `.github/workflows/deploy.yml:88-101`
- **현상**: 모든 `.env` 값이 따옴표 없이 기록됨

**근본 원인 분석:**

심층 조사 결과 실제 위험도는 이전 판정보다 **낮다:**

1. **python-dotenv 동작**: 프로젝트는 `python-dotenv>=1.0.0`을 사용하며(`requirements.txt`), python-dotenv는 미인용 값을 정상 처리한다
2. **docker-compose 동작**: `docker-compose.yml`이 `env_file: [.env]`로 로드하며, docker-compose도 미인용 값을 정상 파싱한다
3. **ALLOWED_ORIGINS 처리**: `config/loader.py:274-277`에서 `split(",")` + `strip()` 처리 → 쉼표 구분 URL도 정상 동작

```python
@property
def allowed_origins(self) -> list[str]:
    origins_str = os.getenv("ALLOWED_ORIGINS", "*")
    return [o.strip() for o in origins_str.split(",")]
```

**실제 위험 시나리오 (edge case):**
- GitHub Secrets 값에 셸 특수문자(`$`, `` ` ``, `"`, `\`)가 포함된 경우 → `echo` 명령에서 셸이 해석
- 예: `AWS_SECRET_ACCESS_KEY`에 `$` 포함 시 → 변수 확장으로 값 손상 가능

**수정 방향:**

GitHub Secrets 값이 셸 해석 없이 그대로 .env에 기록되도록 `echo` 대신 `cat << 'EOF'` heredoc 또는 `printf '%s\n'`을 사용한다.

```bash
# 현재 (셸 해석 가능):
echo "AWS_SECRET_ACCESS_KEY=${{ secrets.AWS_SECRET_ACCESS_KEY }}" >> .env

# 수정 (셸 해석 방지 — 단일 따옴표로 감싸기):
printf '%s\n' 'AWS_SECRET_ACCESS_KEY=${{ secrets.AWS_SECRET_ACCESS_KEY }}' >> .env
```

**이유:**
- AWS 크레덴셜은 base64 인코딩이라 현재도 문제없지만, `AWS_SECRET_ACCESS_KEY`에 `$`가 포함될 확률은 약 2% (base64 charset에 포함)
- 방어적 코딩으로 향후 Secrets 값 변경 시에도 안전하게 동작
- 현재 운영 환경에서 즉시 장애를 유발하지는 않으므로 MEDIUM 유지

---

### 이슈 아님으로 제거: 3건

---

### ~~M-1: Learning Agent 프롬프트 로드 실패~~ → 이슈 아님

**심층 조사 결과:**

1. 프롬프트 파일 `prompts/podcast/learning.yaml` 존재하며 형식 정상 (version 1.0.0, system_prompt 키 포함)
2. `settings.yaml`의 `prompts.versions`에 learning 미등록 → YAML 파일의 기본 버전(1.0.0) 사용 → 정상 동작
3. `BaseAgent._load_prompts()`의 `except PromptLoadError` 블록(base_agent.py:239-246)은 **설계 의도대로** 방어적 처리. 모든 에이전트가 프롬프트 YAML을 필요로 하지 않기 때문에 파일 미존재 시 빈 dict 반환은 정상
4. Learning Agent는 프롬프트 파일이 존재하므로 `PromptLoadError`가 발생하지 않음 → KeyError 시나리오 도달 불가

**결론:** 이론적 코드 경로일 뿐 실제 런타임에서 발생하지 않는다.

---

### ~~M-2: BackendClient 모킹 범위 부족~~ → 이슈 아님

**심층 조사 결과:**

`async_post_processing_node` (workflow.py:360-390) 코드를 정밀 분석한 결과, **fire-and-forget 패턴이 아니다:**

```python
tasks = [asyncio.create_task(learning_node(state))]  # 태스크 생성

async def _run_async_tasks():
    for task in asyncio.as_completed(tasks):
        result = await task      # ← 태스크를 await함
        results.update(result)
    return results

return await asyncio.wait_for(_run_async_tasks(), timeout=_ASYNC_TIMEOUT)
# ↑ 노드 함수가 태스크 완료를 대기한 후에야 반환
```

`asyncio.create_task()` 후 즉시 `await`로 완료를 대기한다. 노드 함수가 반환되는 시점에 태스크는 이미 완료되어 있다. 따라서:
- 테스트의 mock 스코프 내에서 모든 실행이 완료됨
- BackendClient가 mock 스코프 밖에서 호출되는 시나리오 불가
- E2E 테스트에서 `learning_node`를 `AsyncMock`으로 대체하는 것은 불필요한 안전 장치가 아닌 테스트 격리 목적

**결론:** mock 스코프 문제는 존재하지 않는다.

---

### ~~L-1: LANGCHAIN_API_KEY~~ → 이슈 아님

사용자 확인: 키 존재함. `base_agent.py:261-277`에서 graceful degradation 구현 완료. 코드 수정 불필요.

---

## 작업 순서

이슈 수정을 먼저 완료한 후, Bedrock 테스트를 진행한다.

### Step 1: 이슈 수정 (코드)

| 순서 | 이슈 | 우선순위 | 수정 파일 | 난이도 |
|------|------|---------|----------|--------|
| 1-1 | **D-2** SSM 배포 완료 대기 + 타임아웃(600s) 추가 | HIGH | `.github/workflows/deploy.yml` | 낮음 |
| 1-2 | **C-2** 프로바이더별 환경변수명 분기 | HIGH | `dev/live_tests/conftest_live.py` | 낮음 |
| 1-3 | **D-3** .env 값 셸 해석 방지 | MEDIUM | `.github/workflows/deploy.yml` | 낮음 |

### Step 2: Bedrock 모델 최적화 — EC2 테스트 (Task 6)

| 순서 | 단계 | 목적 |
|------|------|------|
| 2-1 | Phase 0 | 신규 모델 6종 연결 확인 |
| 2-2 | Phase 1 | 전체 벤치마크 (171 테스트) |
| 2-3 | Phase 2 | 점수 산출 |
| 2-4 | Phase 3 | 최적 모델 검증 (30 테스트) |

### Step 3: settings.yaml 최적 모델 반영 (Task 7)

Phase 3 결과(`optimal_config.json`) 기반으로 `config/settings.yaml` 에이전트별 모델 업데이트.

# Bedrock E2E 테스트 결과 및 개선 계획

> **테스트 일시**: 2026-03-26 14:38~14:39 KST
> **인스턴스**: i-02631e0888c49b0b7 (EC2, ap-northeast-2)
> **환경**: `.venv` (Python 3.13) + `LLM_PROVIDER=bedrock`
> **모델**: anthropic.claude-3-haiku-20240307-v1:0 (Haiku), apac.anthropic.claude-3-5-sonnet-20241022-v2:0 (Sonnet, env override)
> **PR**: #35 (`fix: Docker 배포 차단 해제 + Visualization settings 전환 + Bedrock Converse API + CRISIS 버그 수정`)

---

## 1. 테스트 결과 요약

| 항목 | 결과 |
|------|------|
| 파이프라인 완료 | **8/8 필드 (100%)** |
| 총 소요 시간 | **76.81초** |
| BV Score | **0.86** |
| Confidence | **0.85** |
| 추론 전략 | GoT+ToT+CoT (full) |
| 최종 출력 길이 | 3,222자 |
| Visualization | S3 업로드 성공 (completed) |
| Verdict | **PASS** |

### TIER별 실행 결과

| TIER | 에이전트 | 필드 | 상태 |
|------|---------|------|------|
| TIER 0 | IntentClassifier | `intent` | OK (3.3s) |
| TIER 1 | Safety | `safety_flags` | OK (warning, risk=1) |
| TIER 1 | Emotion | `emotion_vectors` | OK |
| TIER 1 | ContentAnalyzer | `content_analysis` | OK (depth=deep) |
| TIER 1 | PodcastReasoning | `reasoning_result` | OK (GoT+ToT+CoT) |
| TIER 2 | ScriptGenerator | `script_draft` | OK (5 segments, 463 words, 42.9s) |
| TIER 3 | BatchValidator | `validation_result` | OK (score=0.86, PASS) |
| TIER 4 | ScriptPersonalizer | `final_output` | OK (3,222 chars) |

### 비동기 에이전트

| 에이전트 | 상태 | 비고 |
|---------|------|------|
| Visualization | OK | S3 업로드 완료, image_url 생성 |
| Learning | ERROR | KeyError: 'system_prompt' (비차단) |
| Telemetry | N/A | 미구현 (스텁) |

---

## 2. AWS 자동 배포 실패 원인 최종 보고

### 근본 원인: 메모리 부족(OOM) + Swap 미설정

| 리소스 | 수치 | 상태 |
|--------|------|------|
| **RAM** | 3,836MB (3.8GB) | 빌드 시 부족 |
| **Swap** | **0MB (없음)** | **치명적** |
| **디스크** | 29GB 중 19GB 사용 (11GB 여유) | 경계 수준 |
| **Docker 이미지** | 9.1GB (`app-ai-server:latest`) | 매우 큼 |
| **실행 컨테이너** | 0개 | 서비스 중단 상태 |

### 실패 메커니즘

```
1. GitHub Actions deploy.yml → develop push 시 SSM send-command 발송
   → GitHub 측 정상 동작 (✅ 성공, 2초 소요)
2. EC2에서 SSM Agent가 배포 스크립트 실행:
   - git fetch + git reset --hard        → 성공
   - docker-compose down                  → 성공
   - docker-compose up -d --build         → ❌ FAIL
     └─ pip install에서 sentence-transformers(+PyTorch ~2GB) 설치 시
        RAM 3.8GB 초과 → OOM
3. OOM으로 SSM Agent crash → ipc messaging received timeout signal 에러
4. Docker 빌드 미완료 → 컨테이너 미시작 → 서비스 중단
```

### deploy.yml 구조적 문제: Fire-and-Forget 패턴

```yaml
# .github/workflows/deploy.yml (현재)
- name: Deploy via AWS SSM
  run: |
    aws ssm send-command \
      --instance-ids "${{ secrets.AWS_INSTANCE_ID }}" \
      --document-name "AWS-RunShellScript" \
      --parameters 'commands=[...]' \
      --region ${{ secrets.AWS_REGION }}
```

`send-command`는 명령을 EC2에 **전달만** 하고 결과를 기다리지 않음. 따라서:
- EC2에서 Docker 빌드가 OOM으로 실패해도 GitHub Actions는 **성공(✅)** 으로 표시
- 배포 실패를 감지할 수 없어 **5회 연속 실패**가 발생할 때까지 인지 불가

### 타임라인

| 날짜 | 이벤트 |
|------|--------|
| Mar 24 07:26 | 마지막 성공 배포 (PR #33) |
| Mar 24 09:46 | **첫 실패** — 이후 모든 배포 연속 실패 (5회) |
| Mar 26 13:04 | PR #35 배포 실패 (가장 최근, GitHub Actions Run #16) |
| Mar 26 13:30 | 수동 배포로 해결 (sentence-transformers 제거 후 빌드 성공, 48초) |

### 치킨-앤-에그(Chicken-and-Egg) 문제

PR #35의 핵심 수정사항 중 하나가 `sentence-transformers 제거`. 이 수정이 적용되면 Docker 빌드 OOM이 해결되지만, **자동 배포 자체가 OOM으로 실패**하기 때문에 수정사항이 적용될 수 없는 순환 문제.

→ 수동 배포(`git reset --hard origin/develop` + `docker-compose up -d --build`)로 해결 완료.

### 재발 방지 대책

| # | 대책 | 우선순위 | 설명 |
|---|------|---------|------|
| D-1 | **Swap 파일 설정** | CRITICAL | `fallocate -l 2G /swapfile && mkswap && swapon` — OOM 근본 방지 |
| D-2 | **deploy.yml에 배포 확인 로직 추가** | HIGH | `ssm send-command` → `ssm wait command-executed` 또는 health check curl |
| D-3 | **deploy.yml .env 값 인용 처리** | MEDIUM | `ALLOWED_ORIGINS` URL 값에 따옴표 추가 (M-3과 동일) |
| D-4 | **Docker 이미지 크기 최적화** | LOW | multi-stage build 최적화, 불필요 의존성 정리 |

### deploy.yml 수정안

```yaml
# 개선안: send-command 후 결과 확인
- name: Deploy via AWS SSM
  run: |
    COMMAND_ID=$(aws ssm send-command \
      --instance-ids "${{ secrets.AWS_INSTANCE_ID }}" \
      --document-name "AWS-RunShellScript" \
      --parameters 'commands=[...]' \
      --region ${{ secrets.AWS_REGION }} \
      --query "Command.CommandId" \
      --output text)

    echo "SSM Command ID: $COMMAND_ID"

    # 결과 대기 (최대 5분)
    aws ssm wait command-executed \
      --command-id "$COMMAND_ID" \
      --instance-id "${{ secrets.AWS_INSTANCE_ID }}" \
      --region ${{ secrets.AWS_REGION }}

    # 결과 확인
    aws ssm get-command-invocation \
      --command-id "$COMMAND_ID" \
      --instance-id "${{ secrets.AWS_INSTANCE_ID }}" \
      --region ${{ secrets.AWS_REGION }}
```

---

## 3. 발견된 이슈 (7건)

### CRITICAL (2건)

#### C-1. Bedrock 모델 ID가 ap-northeast-2에서 작동 불가

**증상**: `ValidationException: Invocation of model ID anthropic.claude-3-5-sonnet-20241022-v2:0 with on-demand throughput isn't supported`

**근본 원인**: `config/settings.yaml`의 `bedrock_models`가 on-demand 형식으로 설정되어 있으나, `ap-northeast-2`(서울)에서는 Sonnet/Opus의 on-demand throughput이 지원되지 않음. APAC 리전에서는 cross-region inference profile ID(`apac.` 접두사)가 필요.

**현재 설정** (`config/settings.yaml:21-24`):
```yaml
bedrock_models:
  haiku: "anthropic.claude-3-haiku-20240307-v1:0"      # OK (on-demand 지원)
  sonnet: "anthropic.claude-3-5-sonnet-20241022-v2:0"   # FAIL
  opus:   "anthropic.claude-3-opus-20240229-v1:0"       # FAIL
```

**수정안**:
```yaml
bedrock_models:
  haiku: "anthropic.claude-3-haiku-20240307-v1:0"
  sonnet: "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"
  opus:   "apac.anthropic.claude-3-opus-20240229-v1:0"
```

**영향 범위**: Sonnet을 사용하는 모든 에이전트 (Safety, Emotion, ContentAnalyzer, PodcastReasoning, ScriptGenerator, BatchValidator, ScriptPersonalizer, Visualization) - 총 8개

**임시 워크어라운드**: `export LLM_BEDROCK_MODEL_SONNET=apac.anthropic.claude-3-5-sonnet-20241022-v2:0`

---

#### C-2. conftest_live.py의 환경변수명 불일치

**증상**: `setup_provider("bedrock", model_override)`에서 `model_override`가 Bedrock 경로에 적용되지 않음

**근본 원인**: `conftest_live.py:40-43`에서 `LLM_MODEL_SONNET`을 설정하지만, Bedrock 프로바이더는 `LLM_BEDROCK_MODEL_SONNET`을 확인함.

**현재 코드** (`dev/live_tests/conftest_live.py:40-43`):
```python
if model_override:
    os.environ["LLM_MODEL_SONNET"] = model_override    # Anthropic용 (Bedrock 무시)
    os.environ["LLM_MODEL_HAIKU"] = model_override      # Anthropic용 (Bedrock 무시)
```

**모델 ID 해석 경로**:
```
LLMClient.__init__() → settings.get_bedrock_model_id(model_key)
  → os.getenv("LLM_BEDROCK_MODEL_{KEY}")         ← 여기를 확인
  → settings.yaml bedrock_models[key]              ← 폴백
  → settings.get_model_id(key)                     ← 최종 폴백
```

**수정안** (`dev/live_tests/conftest_live.py`):
```python
if model_override:
    if provider == "bedrock":
        os.environ["LLM_BEDROCK_MODEL_SONNET"] = model_override
        os.environ["LLM_BEDROCK_MODEL_HAIKU"] = model_override
    else:
        os.environ["LLM_MODEL_SONNET"] = model_override
        os.environ["LLM_MODEL_HAIKU"] = model_override
```

---

### MEDIUM (3건)

#### M-1. Learning Agent 프롬프트 로드 실패

**증상**: `KeyError: 'system_prompt'` (비동기 에이전트, 파이프라인 결과에 영향 없음)

**근본 원인 분석**:
- 프롬프트 파일 존재: `prompts/shared/learning.yaml` (version: "1.0.0", system_prompt 키 포함)
- `BaseAgent._load_prompts()` (`base_agent.py:221-239`)에서 `PromptLoadError` 발생 시 **빈 dict `{}`를 반환**하고 DEBUG 레벨로만 로그
- 이후 `get_prompt("system_prompt")` 호출 시 빈 dict에서 키 접근 → `KeyError`
- **설계 결함**: 프롬프트 로드 실패가 조용히 무시되어 런타임에 KeyError로 노출

**심층 분석 결과**: 프롬프트 파일은 존재하며 구조도 정상 (`prompts/shared/learning.yaml`, version: "1.0.0", system_prompt 키 포함). 모드 해석도 정확 (`"shared"`). 문제는 테스트 환경에서 PromptLoader의 base_dir 경로 해석 시 `PromptLoadError`가 발생하고, 이것이 무음 처리되는 것.

**수정안**:
1. `BaseAgent._load_prompts()` 예외 핸들러에서 실제 에러 내용을 WARNING으로 로깅:
   ```python
   except PromptLoadError as e:
       self.logger.warning("프롬프트 로드 실패: %s — %s", self._prompt_mode, str(e))
       return {}
   ```
2. 에이전트 초기화 시 필수 프롬프트 키 검증 (fail-fast):
   ```python
   def __init__(self, ...):
       super().__init__(...)
       if "system_prompt" not in self._prompts:
           raise RuntimeError(f"{self.__class__.__name__}: system_prompt 로드 실패")
   ```
3. AWS 테스트 환경에서 PromptLoader의 base_dir 경로가 올바른지 확인 (`PROMPT_DIR` 환경변수 또는 작업 디렉토리)

---

#### M-2. BackendClient 모킹 범위 부족

**증상**: `RuntimeError: BackendClient가 초기화되지 않았습니다` (emotion_logs, content_analyses 저장 시)

**근본 원인**: `test_e2e_multi_provider.py:243-247`의 `patch.object(BackendClient, "save", ...)` 범위가 `ainvoke()` 호출만 커버. 비동기 에이전트와 `AgentDataPublisher`를 통한 저장 호출이 모킹 범위 밖에서 실행됨.

**심층 분석 결과**: Learning Agent는 `learning.py:41`에서 `self._api_client = BackendClient()`로 **자체 인스턴스**를 생성. `patch.object(BackendClient, "save")`는 클래스 메서드를 패치하지만, 이미 생성된 인스턴스에는 적용 안 됨. 또한 테스트는 FastAPI lifespan을 거치지 않아 `src.api.main.backend_client` 싱글톤이 `None`으로 남음.

**영향받는 에이전트**:

| 에이전트 | 파일 | 저장 메커니즘 | 타이밍 |
|---------|------|------------|--------|
| Learning Agent | `src/agents/shared/learning.py:41,122` | 자체 `BackendClient()` 인스턴스 | 비동기 (post-ainvoke) |
| Emotion Agent | `src/agents/podcast/emotion.py:80` | `AgentDataPublisher.publish()` → `src.api.main.backend_client` | TIER 1 (병렬) |
| Content Analyzer | `src/agents/podcast/content_analyzer.py:105` | `AgentDataPublisher.publish()` → `src.api.main.backend_client` | TIER 1 (병렬) |

**수정안** (3가지 옵션):

**Option A (권장)**: 모킹 범위 확장 + 비동기 대기
```python
with patch.object(BackendClient, "save", ...) as mock_save:
    final_state = await compiled.ainvoke(initial_state)
    await asyncio.sleep(0.5)  # 비동기 태스크 완료 대기
```

**Option B**: BackendClient 싱글톤 모킹
```python
with patch("src.api.main.backend_client") as mock_client:
    mock_client.save = AsyncMock(return_value=mock_response)
    final_state = await compiled.ainvoke(initial_state)
```

**Option C**: AgentDataPublisher + BackendClient 동시 모킹
```python
with patch("src.api.publisher.AgentDataPublisher.publish", new_callable=AsyncMock):
    with patch.object(BackendClient, "save", ...):
        final_state = await compiled.ainvoke(initial_state)
```

---

#### M-3. .env 파일 URL 값 미인용

**증상**: `source .env` → `-bash: https://bloom-chii.com/: No such file or directory`

**근본 원인**: `.env` 파일의 URL 값에 따옴표 없음. `source`로 로드 시 셸이 `://`, `?`, `&` 등을 특수 문자로 해석.

**추가 분석**: 에러의 원인 URL은 `ALLOWED_ORIGINS=https://bloom-chii.com/`으로 추정 (`deploy.yml:46`). Docker Compose의 `.env` 파싱은 정상 동작하지만, bash `source .env`는 URL의 `://`, `?`, `&`를 특수 문자로 해석.

**수정안**:
1. `.env`의 모든 URL/복합 문자열 값을 따옴표로 감싸기:
```bash
# Before (BROKEN)
ALLOWED_ORIGINS=https://bloom-chii.com/

# After (FIXED)
ALLOWED_ORIGINS="https://bloom-chii.com/"
```
2. `.github/workflows/deploy.yml`의 echo 명령에서 값 인용 처리:
```yaml
# Before
echo \"ALLOWED_ORIGINS=${{ secrets.ALLOWED_ORIGINS }}\" >> .env
# After
echo 'ALLOWED_ORIGINS=\"${{ secrets.ALLOWED_ORIGINS }}\"' >> .env
```
3. **권장**: EC2에서 `source .env` 대신 `dotenv` 라이브러리 사용 (Python `load_dotenv()`는 URL을 정상 처리)

---

### LOW (1건)

#### L-1. LANGCHAIN_API_KEY 미설정

**증상**: `LANGCHAIN_API_KEY: (len=0)` — LangSmith 트레이싱 비활성화

**근본 원인**: `.env`에 `LANGCHAIN_API_KEY` 값 없음. `settings.yaml`에서 `monitoring.langsmith.tracing_enabled: true`이지만, API 키 없이는 트레이스 전송 불가.

**수정안**:
1. LangSmith 프로젝트에서 API 키 발급
2. `.env`에 추가: `LANGCHAIN_API_KEY="lsv2_pt_..."`
3. GitHub Secrets에도 추가 (CI/CD 배포 시 필요)
4. `LANGCHAIN_TRACING_V2="true"` 확인

---

### INFO (2건)

#### I-1. Visualization Agent 이미지 리전 설정

**현황**: `config/settings.yaml:111`에서 `image_region: "us-east-1"` 고정. Titan Image Generator가 서울에 없어서 us-east-1 사용.

**참고**: 현재 정상 동작 중 (S3 업로드 완료). 향후 ap-northeast-2에서 이미지 모델 사용 가능 시 리전 변경 검토.

---

#### I-2. Docker 컨테이너 config/ 볼륨 미마운트

**현황**: `docker-compose.yml`에서 `config/` 디렉토리가 볼륨으로 마운트되지 않음:
```yaml
volumes:
  - ./prompts:/app/prompts   # 마운트됨
  - ./logs:/app/logs          # 마운트됨
  # config/ 미마운트 → settings.yaml 변경 시 이미지 리빌드 필요
```

**영향**: C-1(settings.yaml bedrock_models 수정) 적용 시 Docker 이미지 리빌드 필요. 환경변수(`.env`의 `LLM_BEDROCK_MODEL_*`)로 오버라이드하면 리빌드 없이 적용 가능.

**권장 대응**:
- **즉시**: `.env`에 `LLM_BEDROCK_MODEL_SONNET`, `LLM_BEDROCK_MODEL_HAIKU` 추가 (리빌드 불필요)
- **향후**: `docker-compose.yml`에 `- ./config:/app/config` 볼륨 마운트 추가 검토

---

## 4. 수정 우선순위 및 일정

| 순위 | 이슈 | 담당 | 난이도 | 예상 작업 |
|------|------|------|--------|----------|
| 1 | **D-1. Swap 파일 설정** | 인프라 | 낮음 | EC2에서 2GB swap 생성 |
| 2 | **D-2. deploy.yml 배포 확인 로직** | 인프라 | 중간 | ssm wait + health check 추가 |
| 3 | C-1. settings.yaml bedrock_models | 전원 합의 | 낮음 | YAML 3줄 수정 |
| 4 | C-2. conftest_live.py env var | 개발자3 | 낮음 | 조건문 추가 |
| 5 | D-3/M-3. .env URL 인용 + deploy.yml | 인프라 | 낮음 | 따옴표 추가 |
| 6 | M-2. BackendClient 모킹 | 개발자3 | 중간 | 테스트 코드 수정 |
| 7 | M-1. Learning Agent 프롬프트 | 개발자3 | 중간 | 로깅 강화 + 원인 파악 |
| 8 | L-1. LANGCHAIN_API_KEY | 인프라 | 낮음 | .env + Secrets 추가 |

---

## 5. 검증 계획

### 즉시 검증 (C-1, C-2 수정 후)

```bash
# settings.yaml 수정 후 E2E 재실행 (env override 없이)
cd ~/app && source .venv/bin/activate
PYTHONPATH=. python3 /tmp/bedrock_e2e.py
# 기대: 8/8 필드, env override 없이 정상 동작
```

### LangSmith 검증 (L-1 수정 후)

```bash
# .env에 LANGCHAIN_API_KEY 추가 후
PYTHONPATH=. python3 /tmp/bedrock_e2e.py
# LangSmith 대시보드에서 트레이스 확인
```

---

## 6. 테스트 결과 파일 위치

| 위치 | 경로 |
|------|------|
| AWS 인스턴스 원본 | `~/app/dev/live_tests/results/bedrock_anthropic.claude-3-haiku-20240307-v1_0_20260326_143922.json` |
| S3 백업 | `s3://t7-mindlog-ai-assets/tmp/bedrock_e2e_result.json` |
| 로컬 복사본 | `dev/live_tests/results/bedrock_anthropic.claude-3-haiku-20240307-v1_0_20260326_143922.json` |

---

## 7. 결론

PR #35 배포 후 Bedrock E2E 테스트는 **파이프라인 8/8 필드 완료, BV Score 0.86으로 성공**했다. 단, 이는 `LLM_BEDROCK_MODEL_SONNET` 환경변수 워크어라운드를 적용한 결과이며, `config/settings.yaml`의 bedrock_models에 APAC inference profile ID를 반영하는 것이 **즉시 필요**하다.

AWS 자동 배포는 **EC2 메모리 부족(OOM) + Swap 미설정**으로 5회 연속 실패했으며, `deploy.yml`의 fire-and-forget 패턴으로 인해 실패가 감지되지 않았다. 수동 배포로 해결 완료되었으나, Swap 설정과 deploy.yml 개선이 재발 방지를 위해 필수적이다.

비차단 이슈(Learning Agent 프롬프트, BackendClient 모킹, .env 파싱, LangSmith 키)는 운영 안정성을 위해 순차적으로 수정한다.

---

*작성일: 2026-03-26 | 최종 수정: 2026-03-27*

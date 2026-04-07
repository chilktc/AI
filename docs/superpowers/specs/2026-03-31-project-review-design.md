# Mind-Log 프로젝트 점검 및 AWS 안정화 설계 문서

**작성일**: 2026-03-31
**대상 브랜치**: develop
**작성 기반**: 코드베이스 전수 탐색 + AWS Bedrock 공식 문서 검증

---

## Context (배경 및 목적)

Mind-Log AI 서버는 실제 서비스 런칭을 앞두고 있으며 AWS EC2 + Docker 환경에서 운영 예정이다.
최근 AWS 인스턴스에서 다음 문제들이 발생했다:

1. **Bedrock 모델 연결 실패** — `ValidationException: on-demand throughput isn't supported` (원인 확인)
2. **Docker 빌드 이슈** — 이전 수정 후 재검증 필요
3. **GitHub Actions 미작동** — 배포 파이프라인 이슈 목록화 필요
4. **Bedrock rate limit 대응 미비** — ThrottlingException 처리 코드 없음
5. **동시 요청 처리** — 5개 프로세스 동시 작동 확인, Semaphore 미적용
6. **EC2↔로컬↔원격 Git 동기화 불가** — EC2 push 불가로 변경사항 유실 위험

추가: 코드 품질(데드코드·설정 불일치·주석·토큰 낭비), Neo4j/Pinecone AWS 운영 방안, Bedrock 프롬프트 캐싱 도입.

### 전체 진행 흐름

```
[긴급 선행] Git 동기화 체계 수립
    ↓ (내일 GitHub 권한자 처리 후)

Track 1 (코드 품질)     Track 2 (AWS 안정화)      Track 3 (DB 인프라)
로컬 작업               코드 수정 포함              계획 수립
    ↓                      ↓                          ↓
     [EC2 커밋/푸시 → 로컬 검토 → 머지 → 설계문서 비교 → 계획 수정]
```

---

## 섹션 1: Git 동기화 체계 수립

### 현재 문제

`deploy.yml` 34~36번 줄이 EC2 로컬 변경을 매 배포 시 강제 삭제:
```bash
git clone -b develop https://github.com/[레포].git .
git fetch origin develop
git reset --hard origin/develop   # EC2 로컬 변경 전체 삭제
```
- EC2에 GitHub 인증 없음 → push 불가
- 현재 미커밋 파일: `dev/live_tests/run_bedrock_model_test.py`

### 단기 해결 (즉시)
```bash
git add dev/live_tests/run_bedrock_model_test.py
git commit -m "fix: Bedrock 모델 테스트 오케스트레이터 업데이트"
git push origin develop
```

### 중기 해결 (내일 GitHub 권한자 요청)

EC2에 SSH Deploy Key 등록:
1. EC2에서 `ssh-keygen -t ed25519 -C "mindlog-ec2"` 실행
2. GitHub 레포 Settings → Deploy Keys → 공개키 등록 (write 권한)
3. `deploy.yml` clone URL을 `git@github.com:[org]/mind-log.git`으로 변경

**원칙**: "EC2는 배포 수신 전용, 개발·수정은 반드시 로컬에서만"

---

## 섹션 2: 작업 후 검토 및 계획 수정 워크플로우

모든 작업 완료 후 아래 게이트를 통과해야 한다.

```
Step 1. EC2 또는 로컬에서 작업 완료
    ↓
Step 2. 커밋 및 GitHub push (develop 브랜치)
    ↓
Step 3. 로컬에서 git pull → 변경 내용 코드 리뷰
         - 의도한 수정 반영 확인
         - 예상치 못한 변경사항 없는지 확인
    ↓
Step 4. 테스트 실행
         pytest tests/ -v -x
         (관련 에이전트만: pytest tests/agents/ -v -k "emotion or safety or llm_client")
    ↓
Step 5. 본 설계 문서와 비교 분석
         - 설계 의도와 구현 일치 여부
         - 새 발견 이슈 → 섹션 9(추가 발견 이슈)에 기록
    ↓
Step 6. 구현 계획서(writing-plans 결과물) 업데이트
    ↓
Step 7. develop → main PR 생성 (3인 전원 승인)
```

### 비교 분석 체크리스트 (Step 5용)

**Track 2 (AWS 안정화)**
- [ ] `settings.yaml` bedrock_models APAC CRIS ID 적용 확인
- [ ] `llm_client.py` ThrottlingException try/except 코드 존재
- [ ] `llm_client.py` asyncio.Semaphore 클래스 변수 존재
- [ ] `llm_client.py` `cachePoint` 또는 `cache_control` 추가 확인
- [ ] `settings.yaml` `prompt_caching` 섹션 추가 확인
- [ ] `docker-compose.yml` mem_limit 설정 확인
- [ ] `storage.mode` 운영 설정 확인

**Track 1 (코드 품질)**
- [ ] `podcast_reasoning.max_tokens: 8192` 확인
- [ ] `script_generator.max_tokens: 8192` 확인
- [ ] `emotion.py` `_build_intent_context()` 메서드 존재
- [ ] `prompts/podcast/emotion.yaml` Intent 활용 가이드 섹션
- [ ] `agent_state.py` `response_draft` TODO 주석

**Track 3 (DB 인프라)**
- [ ] `docker-compose.yml` neo4j 서비스 추가
- [ ] `settings.yaml` databases 섹션 추가
- [ ] EC2 Swap 2GB 설정 (인프라팀)

---

## 섹션 3: Track 2 — AWS/Bedrock 안정화

### 3-1. Bedrock 모델 ID 교체 — P1 (연결 실패 핵심 원인)

**파일**: `config/settings.yaml`

**확인된 에러** (`docs/reports/BEDROCK_E2E_IMPROVEMENT_PLAN_20260326.md`):
```
ValidationException: Invocation of model ID
anthropic.claude-3-5-sonnet-20241022-v2:0
with on-demand throughput isn't supported
```

서울 리전(`ap-northeast-2`)에서 Claude 3.5 Sonnet v2 이상은 직접(In-Region) 호출 불가.
APAC Cross-Region Inference Profile(CRIS) ID 필수.

| 키 | 현재 (잘못됨) | 수정 후 | 근거 |
|----|--------------|--------|------|
| `haiku` | `anthropic.claude-3-haiku-20240307-v1:0` | 동일 (유지) | In-Region 지원됨 |
| `sonnet` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | APAC CRIS 필수 |
| `opus` | `anthropic.claude-3-opus-20240229-v1:0` | `apac.anthropic.claude-sonnet-4-20250514-v1:0` | Opus 서울 미지원, Sonnet 4 대체 |

> `run_bedrock_model_test.py`의 최적 모델 확정 시 해당 ID로 재교체.

테스트 후 추가 가능 모델:
```yaml
# nova_pro: "apac.amazon.nova-pro-v1:0"
# nova_lite: "apac.amazon.nova-lite-v1:0"
```

---

### 3-2. ThrottlingException Retry 추가 — P1

**파일**: `src/agents/shared/llm_client.py` (`_generate_bedrock()` 341~381번 줄)

현재 try/except 전혀 없음 → rate limit 초과 시 파이프라인 전체 실패.

수정 방향:
- `botocore.exceptions.ClientError`로 Bedrock 전체 에러 포착
- 에러 코드별 처리:
  - `ThrottlingException`, `ServiceUnavailableException` → exponential backoff (1s→2s→4s, 최대 3회)
  - `ModelNotReadyException` → 고정 5초 대기 후 1회 재시도
  - `AccessDeniedException` → 즉시 실패 + 명확한 메시지
- `settings.yaml` 추가:
  ```yaml
  bedrock:
    region: "ap-northeast-2"
    retry:
      max_attempts: 3
      initial_backoff_seconds: 1
      max_backoff_seconds: 8
  ```

> **주의**: `llm_client.py`는 공용 인프라 — public 메서드 시그니처 변경 금지, 내부만 수정.

---

### 3-3. asyncio.Semaphore 동시 요청 제한 — P2

**파일**: `src/agents/shared/llm_client.py`

현황: 5개 프로세스 × TIER 1 4개 에이전트 = 최대 20개 Bedrock 동시 호출.

검증 사항:
- Bedrock은 concurrent connections 별도 제한 없음 (TPM/RPM 기준 throttle)
- On-Demand rate limit 증가 요청 가능 — **비용 변화 없음** (실사용 토큰만 과금)
- APAC CRIS 사용 시 APAC 여러 리전으로 자동 분산 → 실효 처리량 증가

수정 방향:
- `LLMClient` 클래스 변수에 `asyncio.Semaphore` 추가 (인스턴스 간 공유)
- `settings.yaml` 추가:
  ```yaml
  bedrock:
    concurrency_limit: 10
  ```
- `generate()` 앞뒤로 semaphore 획득/반납

인프라팀 이슈 (Service Quotas 증가 신청):
```
AWS Console → Service Quotas → Amazon Bedrock → ap-northeast-2
→ "Cross-Region InvokeModel tokens per minute for claude-3-5-sonnet-v2"
→ 요청 증가 (CRIS quota 승인율이 On-Demand보다 높음)
```

---

### 3-4. Bedrock/Anthropic 프롬프트 캐싱 전략 — P2

**파일**: `src/agents/shared/llm_client.py`, `config/settings.yaml`

#### 효과

현재 모든 에이전트가 매 요청마다 동일한 시스템 프롬프트를 전송.
AWS Bedrock은 2025년 4월 `cachePoint` GA — 캐시 히트 시 **입력 토큰 90% 절감**.

| 구분 | 비용 |
|------|------|
| 캐시 쓰기 (첫 요청) | 표준 입력 토큰 × 1.25 |
| 캐시 읽기 (이후 요청) | 표준 입력 토큰 × 0.10 |
| **순 절감 효과** | **반복 요청 시 최대 ~88% 절감** |

#### 지원 모델

| 모델 | 캐싱 지원 | TTL |
|------|---------|-----|
| `claude-3-5-sonnet-20241022-v2` (현재 sonnet) | ✅ | 5분 |
| `claude-3-haiku-20240307` (현재 haiku) | ❌ | - |
| `claude-sonnet-4` (opus 대체 예정) | ✅ | 5분 / 1시간 |

#### 에이전트별 캐싱 우선순위

| 에이전트 | 프롬프트 크기 | 효과 |
|---------|------------|------|
| Batch Validator | 28KB | ★★★★★ |
| Script Generator | ~2KB | ★★★★ |
| Podcast Reasoning | ~2.3KB | ★★★★ |
| Safety, Emotion, Content Analyzer | 0.8~1.6KB | ★★★ (1,024 토큰 경계 확인 필요) |
| Intent Classifier, Visualization | 1.6~1.9KB | ★★★ |

#### 구현 방법

**Bedrock** (`_generate_bedrock()` 수정):
```python
system=[
    {"text": system_prompt},
    {"cachePoint": {"type": "default"}}   # 시스템 프롬프트 전체 캐시
]
```

**Anthropic 직접 API** (`_generate_anthropic()` 수정):
```python
system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
```

**`settings.yaml` 추가**:
```yaml
llm:
  prompt_caching:
    enabled: true      # on/off 제어
    ttl: "5m"          # "5m" | "1h" (Claude 4.5+ 모델만)
    min_tokens: 1024   # 미만 프롬프트는 스킵 (오류 없음)
```

**토큰 추적 확장** (`_record_usage()`):
```python
cache_read_tokens=usage.get("cacheReadInputTokens", 0),
cache_write_tokens=usage.get("cacheWriteInputTokens", 0),
```

#### 서울 리전 지원 검증

공식 AWS 문서에 `ap-northeast-2` 직접 캐싱 지원 미명시. APAC CRIS 경유 시 가능하나 캐시 히트율 저하 가능성 있음.

**Phase 0 검증 추가** (`run_bedrock_model_test.py`):
```python
response = client.converse(
    modelId="apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
    system=[{"text": test_prompt_1024_tokens}, {"cachePoint": {"type": "default"}}],
    messages=[{"role": "user", "content": [{"text": "test"}]}],
    inferenceConfig={"maxTokens": 10}
)
# cacheWriteInputTokens > 0 → 캐싱 활성화 확인
```

미지원 확인 시 폴백: Anthropic 직접 API(`provider: anthropic`) 사용 — `cache_control` 지원됨.

---

### 3-5. storage.mode 운영 설정 — P2

**파일**: `config/settings.yaml` 177번 줄

현재 `storage.mode: "local"` → 백엔드 API 저장 안 됨.
`deploy.yml`의 `.env` 생성 부분에 추가:
```bash
echo "STORAGE_MODE=proxy" >> .env
```

→ GitHub Actions 이슈 G-6으로도 등록.

---

### 3-6. Docker 리소스 제한 — P3

**파일**: `docker-compose.yml`

현재 메모리/CPU 제한 없음 → EC2 t3.medium(4GB)에서 OOM 위험.

```yaml
services:
  ai-server:
    mem_limit: 2g
    memswap_limit: 2g
    cpus: '1.5'
```

Neo4j 추가 시 `1500m`으로 조정 (섹션 5 참조).

---

### 3-7. Learning Agent KeyError 수정 — P3

**파일**: `src/agents/shared/learning.py`

확인된 에러 (E2E 테스트 결과 JSON):
```
Learning: ERROR (KeyError: 'system_prompt' — 비차단)
```
비동기라 파이프라인은 안 막히나 학습 데이터 누적 안 됨.

수정 방향:
- `BaseAgent._load_prompts()` 예외 처리에 에러 로깅 추가
- `prompts/shared/learning.yaml`의 `system_prompt` 키 존재 여부 확인

---

## 섹션 4: Track 1 — 코드 품질

### 4-1. 토큰 예산 증가 — P1

**파일**: `config/settings.yaml`

출력 잘림 → JSON 파싱 실패 → TIER 3 검증 실패 → 재시도 2회 → 파이프라인 오류.

| 에이전트 | 현재 | 수정 후 | 근거 |
|---------|------|--------|------|
| `podcast_reasoning` | 4096 | 8192 | 실제 출력 7~11KB |
| `script_generator` | 4096 | 8192 | 실제 출력 8~21KB |

---

### 4-2. Emotion Agent Intent 최적화 — P2

**파일**: `src/agents/podcast/emotion.py`, `prompts/podcast/emotion.yaml`

현재 Emotion Agent가 Intent dict 전체(17개 필드, ~500~800 토큰)를 LLM에 전달.
Safety/Content Analyzer는 이미 필요한 필드만 추출 (최적화 완료).

| 에이전트 | Intent 사용 | 토큰 소모 |
|---------|-----------|---------|
| Safety | `risk_flag` 1개 (조건부) | 0~30 |
| Content Analyzer | `complexity_score` 1개 | 50~80 |
| **Emotion (현재)** | **전체 dict 17개 필드** | **500~800** |

Emotion에 실제 필요한 필드: `detected_entities.emotions`, `intent_type`, `flags.urgency_level`, `flags.risk_flag` (4개)

수정 방향:
- `emotion.py`: `_build_intent_context(intent)` 메서드 추가 (Safety 패턴 참고)
- `prompts/podcast/emotion.yaml`: "Intent 참고 정보" 활용 가이드 추가

예상 절감: **요청당 400~700 토큰**.

---

### 4-3. 설정 불일치 및 누락 항목 — P3

**파일**: `config/settings.yaml`

`script_personalizer.py` 83번 줄에 `deep_personalization` 하드코딩 → settings에 추가:
```yaml
agents:
  script_personalizer:
    deep_personalization: false  # 코드 하드코딩에서 설정화
```

> `podcast_reasoning.full_threshold: 0.0` (항상 full 추론)은 **의도된 설정** — 변경 불필요.

---

### 4-4. 고아 필드 및 미사용 코드 명시 — P3

**파일**: `src/models/agent_state.py`

`response_draft` 필드: 대화모드 제거로 영구 미사용. AgentState에서 삭제 예정.

`script_personalizer.py` 83번 줄 `emotional_journey = None` 하드코딩 → 설정화 또는 명시적 TODO 추가.

---

### 4-5. 주석/docstring 통일 — P3

현황: `base_agent.py`, `llm_client.py`는 상세 (기준점). `safety.py`, `emotion.py`, `workflow.py` 노드 함수에 주석 없음.

각 에이전트 `process()` 메서드에 최소 docstring 추가:
```python
async def process(self, state: AgentState) -> dict[str, Any]:
    """
    감정 벡터를 추출한다.

    Args:
        state: user_input, intent 필드 읽음
    Returns:
        {"emotion_vectors": {...}}  — AgentState에 병합됨
    """
```

---

## 섹션 5: Track 3 — Neo4j/Pinecone AWS 운영 방안

### 5-1. t3.medium 메모리 분석

| 구성 요소 | 메모리 |
|---------|--------|
| OS + Docker 데몬 | ~500MB |
| ai-server (FastAPI + LangGraph) | ~500MB~1GB |
| Neo4j (최소 설정) | ~750MB~1GB |
| **합계** | **~1.75~2.5GB / 4GB** |

**EC2 Swap 2GB 설정 필수** (이미 `BEDROCK_E2E_IMPROVEMENT_PLAN_20260326.md` D-1 CRITICAL):
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 5-2. Neo4j 운영 방안 결정

**추천: Docker Compose 통합 (A안)**

| 항목 | A. Docker Compose | B. 별도 EC2 | C. Neo4j Aura |
|------|-----------------|-----------|--------------|
| 비용 | 추가 없음 | ~$30/월 추가 | $65~/월 |
| 설정 복잡도 | 낮음 | 중간 | 매우 낮음 |
| AI팀 제어권 | 완전 | 완전 | 제한적 |
| 네트워크 지연 | 없음 | ~1ms | ~20~50ms |
| 적용 속도 | 가장 빠름 | 느림 | 빠름 |

`docker-compose.yml` 추가:
```yaml
neo4j:
  image: neo4j:5-community
  container_name: mindlog-neo4j
  ports:
    - "7474:7474"
    - "7687:7687"
  environment:
    NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
    NEO4J_server_memory_heap_initial__size: "256m"
    NEO4J_server_memory_heap_max__size: "512m"
    NEO4J_server_memory_pagecache_size: "256m"
  volumes:
    - ./data/neo4j:/data
    - ./logs/neo4j:/logs
  mem_limit: 1g
  restart: unless-stopped
```

ai-server mem_limit: `2g` → `1500m` 조정 (Neo4j 추가분 확보).

### 5-3. Pinecone 연동

`requirements.txt`에 이미 `pinecone-client>=3.0.0` 포함, `settings.yaml`에 인덱스명 정의됨.
`.env`에 `PINECONE_API_KEY` 추가만 하면 즉시 사용 가능.

### 5-4. settings.yaml databases 섹션 추가

```yaml
databases:
  neo4j:
    uri: "bolt://localhost:7687"   # 환경변수 NEO4J_URI로 오버라이드
  pinecone:
    index_knowledge: "expert_knowledge"
    index_memory_conversation: "mem_conversation"
    index_memory_podcast: "mem_podcast_episode"
    # 환경변수 PINECONE_API_KEY 필수
```

---

## 섹션 6: GitHub Actions 이슈 목록 (인프라팀 전달)

수정 없이 발견된 이슈만 기록. 인프라팀이 처리.

| ID | 이슈 | 위치 (deploy.yml) | 영향 | 권장 조치 |
|----|------|-----------------|------|---------|
| G-1 | git clone HTTPS 인증 미설정 | 34번 줄 | 프라이빗 레포 clone 실패 | Deploy Key 또는 GITHUB_TOKEN 추가 |
| G-2 | AWS 자격증명 EC2 평문 저장 | 41~42번 줄 | 보안 위험 | EC2 IAM Role 전환 후 해당 줄 제거 |
| G-3 | SSM 명령 성공 여부 미확인 | 전체 | 배포 실패해도 Actions 성공 표시 | wait 커맨드 또는 `--output-s3` 추가 |
| G-4 | `docker-compose down` 다운타임 | 51번 줄 | 매 배포마다 수 초 서비스 중단 | `--no-recreate` 또는 Blue-Green 전환 |
| G-5 | DB 환경변수 미포함 | 37~49번 줄 | Neo4j/Pinecone 연동 불가 | `PINECONE_API_KEY`, `NEO4J_URI` 등 추가 |
| G-6 | `STORAGE_MODE` 미포함 | 37~49번 줄 | 프로덕션에서도 local 모드 동작 | `STORAGE_MODE=proxy` 추가 |

---

## 섹션 7: 작업 우선순위 요약

### 즉시 (오늘)
1. `dev/live_tests/run_bedrock_model_test.py` 로컬 커밋 및 push
2. `settings.yaml` bedrock_models APAC CRIS ID 교체 **(연결 실패 해결)**
3. `settings.yaml` podcast_reasoning / script_generator `max_tokens: 8192`

### 단기 (내일~이번 주)
4. `llm_client.py` ThrottlingException exponential backoff retry 추가
5. `llm_client.py` asyncio.Semaphore 동시 요청 제한
6. **`llm_client.py` + `settings.yaml` 프롬프트 캐싱 적용 (Bedrock `cachePoint`)**
7. `run_bedrock_model_test.py` Phase 0에 캐싱 지원 여부 검증 추가
8. `emotion.py` + `prompts/podcast/emotion.yaml` Intent 최적화
9. `docker-compose.yml` 리소스 제한 + Neo4j 서비스 추가
10. GitHub 권한자에게 Deploy Key 요청 (Git 동기화)

### 중기 (이번 주~다음 주)
11. Learning Agent KeyError 수정
12. 주석/docstring 통일
13. 고아 필드 정리
14. GitHub Actions 이슈 목록 인프라팀 전달
15. Service Quotas 증가 신청 (인프라팀)

---

## 섹션 8: 검증 방법

### 로컬 검증
```bash
pytest tests/ -v                                          # 전체
pytest tests/agents/shared/test_llm_client.py -v        # Bedrock 설정
pytest tests/agents/podcast/test_emotion.py -v          # Emotion 최적화
```

### AWS 검증 (Chrome MCP / puppeteer 사용)
```bash
docker-compose ps && docker stats --no-stream            # 컨테이너 상태
curl http://localhost:8000/health/ready                   # 준비 상태
python3 -m dev.live_tests.run_bedrock_model_test --phase 0  # Bedrock 연결
```

### 완료 기준
1. `pytest tests/ -v` 전체 통과
2. `docker-compose up --build` 에러 없이 빌드 및 기동
3. `/health/ready` → `"status": "ready"`
4. Bedrock Phase 0 — 텍스트 + 이미지 모델 연결 통과
5. Bedrock Phase 0 캐싱 검증 — `cacheWriteInputTokens > 0`
6. 팟캐스트 E2E — BV Score ≥ 0.80

---

## 섹션 9: 추가 발견 이슈 (작업 중 기록용)

| 발견일 | 이슈 | 파일 | 심각도 | 처리 방향 |
|--------|------|------|--------|---------|
| (작업 진행 중 기록) | | | | |

---

*마지막 업데이트: 2026-03-31*
*다음 갱신: EC2 커밋/푸시 후 비교 분석 완료 시*

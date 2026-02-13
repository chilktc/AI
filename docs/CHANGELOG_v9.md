# 변경이력 v9 — 문서 일관성 통합 + LLM 듀얼 프로바이더 아키텍처

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-13

---

## 배경

### 문제

v8까지 코드와 인프라는 완성되었으나, 프로젝트 문서 전반에 4가지 불일치가 존재했다:

1. **DB 표기 불일치** — 일부 문서가 PostgreSQL로 표기되어 있으나 실제 기술 스택은 MySQL
2. **개발자 명칭 불일치** — 초기 설계 문서의 Dev-A/B/C와 실제 역할 배분(개발자1/2/3)이 혼재
3. **LLM 프로바이더 단일 구조** — Anthropic 직접 API만 지원, AWS Bedrock 미지원
4. **Telemetry Agent 담당자 표기 불일치** — 일부 문서에서 Dev-C(개발자3) 소속으로 표기되어 있으나 실제로는 미정

### 목표

1. 모든 문서에서 PostgreSQL → MySQL 통일
2. Dev-A/B/C → 개발자1/2/3으로 전체 문서 통일 (81+ 위치)
3. LLMClient를 듀얼 프로바이더(Anthropic + AWS Bedrock) 아키텍처로 확장
4. Telemetry Agent를 "미정"으로 전체 문서 통일
5. 듀얼 프로바이더 테스트 코드 작성 (27개 테스트)

---

## 변경 내용

### 1. PostgreSQL → MySQL 통일

실제 기술 스택(MySQL)에 맞춰 모든 문서의 DB 표기를 수정했다.

| 파일 | 변경 내용 |
|------|----------|
| `docs/QUICK_START.md` | PostgreSQL 요구사항 → MySQL, Docker Compose 주석 |
| `src/agents/shared/stubs.py` | 주석의 "PostgreSQL 메타데이터" → "MySQL 메타데이터" |
| `CLAUDE.md` | 기술 스택 표 PostgreSQL → MySQL |
| `README.md` | 기술 스택 표 PostgreSQL → MySQL |

### 2. Dev-A/B/C → 개발자1/2/3 통일

9개 파일, 81개 이상의 위치에서 개발자 명칭을 통일했다.

**매핑 규칙:**

| 이전 | 이후 | 도메인 |
|------|------|--------|
| Dev-A | 개발자1 | 분석 (Analysis) |
| Dev-B | 개발자2 | 추론/생성 (Reasoning) |
| Dev-C | 개발자3 | 검증/부가 (Validation) |

**수정 파일:**

| 파일 | 주요 변경 |
|------|----------|
| `CLAUDE.md` | 에이전트 표, AgentState 주석, 필드 접근 규칙, 브랜치 전략, 워크플로우 코드 |
| `README.md` | 팀 구성 표, 에이전트-개발자 배치 |
| `CONTRIBUTING.md` | 개발자 도메인 표, 파일 경로 |
| `docs/GIT_WORKFLOW.md` | 브랜치 트리, 규칙, 네이밍 예시 |
| `docs/PROJECT_STRUCTURE.md` | 파일별 `[Dev-X]` 태그 → `[개발자N]`, 소유권 표 |
| `docs/QUICK_START.md` | 개발자별 시작 지점 |
| `.github/pull_request_template.md` | 도메인 체크박스 |
| `docs/CHANGELOG_v1-v5.md` | 역할 배분 표 |
| `docs/PROJECT_SUMMARY.md` | 경고 노트 → 완료 상태로 업데이트 |

### 3. LLM 듀얼 프로바이더 아키텍처 (Anthropic + AWS Bedrock)

#### 3-1. LLMClient 듀얼 프로바이더 (`src/agents/shared/llm_client.py`)

기존 Anthropic 전용 클라이언트를 듀얼 프로바이더로 확장했다.

**프로바이더 선택 우선순위:**

```
1. LLMClient 생성자의 provider_override 파라미터
2. 환경변수 LLM_PROVIDER
3. config/settings.yaml의 llm.provider 값
```

**신규 메서드/속성:**

| 메서드/속성 | 설명 |
|-----------|------|
| `provider` 프로퍼티 | 현재 프로바이더 ("anthropic" \| "bedrock") |
| `_init_bedrock_client()` | boto3 Bedrock 클라이언트 초기화 |
| `_generate_bedrock()` | Bedrock invoke_model 호출 (asyncio.to_thread 래핑) |

**Bedrock 호출 흐름:**

```python
# boto3는 동기 SDK — asyncio.to_thread로 비동기 래핑
response = await asyncio.to_thread(
    self._bedrock_client.invoke_model,
    modelId=self._model_id,
    body=request_body,
    contentType="application/json",
    accept="application/json",
)
```

#### 3-2. Settings Bedrock 지원 (`config/loader.py`)

| 메서드/속성 | 설명 |
|-----------|------|
| `llm_provider` | LLM 프로바이더 (환경변수 `LLM_PROVIDER`로 오버라이드) |
| `bedrock_region` | AWS 리전 (환경변수 `AWS_REGION`으로 오버라이드) |
| `bedrock_config` | Bedrock 설정 전체 dict |
| `get_bedrock_model_id()` | Bedrock 모델 ID 조회 (환경변수 + fallback) |

#### 3-3. 설정 파일 (`config/settings.yaml`)

```yaml
llm:
  provider: anthropic  # anthropic | bedrock
  models:
    haiku: "claude-haiku-4-5-20251001"
    sonnet: "claude-sonnet-4-5-20250929"
    opus: "claude-opus-4-6"
  bedrock_models:
    haiku: "anthropic.claude-haiku-4-5-20251001-v1:0"
    sonnet: "anthropic.claude-sonnet-4-5-20250929-v2:0"
    opus: "anthropic.claude-opus-4-6-v1:0"
  bedrock:
    region: "ap-northeast-2"
```

#### 3-4. 의존성 (`requirements.txt`)

```
boto3>=1.34.0  # AWS Bedrock 듀얼 프로바이더 (선택적)
```

boto3는 Bedrock 사용 시에만 필요. 미설치 시 Anthropic 모드는 정상 동작하고, Bedrock 모드 초기화 시 `ImportError` 발생.

### 4. Telemetry Agent 담당자 통일

모든 문서에서 Telemetry Agent를 "미정 (전체 에이전트 완료 후 예정)"으로 통일했다.

**영향 파일:** `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `docs/PROJECT_STRUCTURE.md`, `docs/CHANGELOG_v1-v5.md`

### 5. LLM 듀얼 프로바이더 테스트 (`tests/agents/shared/test_llm_client.py`)

27개 테스트를 7개 클래스로 구성:

| 테스트 클래스 | 테스트 수 | 범위 |
|-------------|----------|------|
| `TestSettingsLLMProvider` | 6 | provider 기본값, 환경변수 오버라이드, region, config |
| `TestSettingsBedrockModelId` | 5 | Bedrock 모델 ID 조회, 환경변수 오버라이드, fallback |
| `TestLLMClientAnthropicMode` | 4 | Anthropic 기본 동작, model_override, generate, generate_json |
| `TestLLMClientBedrockMode` | 3 | Bedrock provider_override, model_override, invoke_model 호출 |
| `TestLLMClientProviderPriority` | 3 | settings → 환경변수 → override 우선순위 |
| `TestLLMClientJsonParsing` | 5 | 순수 JSON, 마크다운 블록, 공백, 무효 JSON, 중첩 |
| `TestLLMClientBoto3Missing` | 1 | boto3 미설치 시 ImportError |

---

## 영향 범위

### 수정 파일 (16개)

| 카테고리 | 파일 | 변경 유형 |
|---------|------|----------|
| 코드 | `src/agents/shared/llm_client.py` | 듀얼 프로바이더 전체 재작성 |
| 코드 | `config/loader.py` | Bedrock 속성 4개 추가 |
| 코드 | `src/agents/shared/stubs.py` | 주석 MySQL 통일 |
| 설정 | `config/settings.yaml` | bedrock_models, bedrock 섹션 추가 |
| 설정 | `requirements.txt` | boto3 추가 |
| 설정 | `.env.example` | LLM_PROVIDER 주석 추가 |
| 문서 | `CLAUDE.md` | 개발자 명칭, 에이전트 표, 기술 스택 |
| 문서 | `README.md` | 팀 구성, 기술 스택 |
| 문서 | `CONTRIBUTING.md` | 개발자 도메인 표 |
| 문서 | `docs/GIT_WORKFLOW.md` | 브랜치 전략 |
| 문서 | `docs/PROJECT_STRUCTURE.md` | 파일 소유권 |
| 문서 | `docs/QUICK_START.md` | DB + 개발자 시작 지점 |
| 문서 | `docs/CHANGELOG_v1-v5.md` | 역할 배분 표 |
| 문서 | `docs/PROJECT_SUMMARY.md` | 상태 업데이트 |
| 문서 | `.github/pull_request_template.md` | 도메인 체크박스 |

### 신규 파일 (2개)

| 파일 | 설명 |
|------|------|
| `tests/agents/shared/test_llm_client.py` | LLM 듀얼 프로바이더 테스트 (27개) |
| `docs/CHANGELOG_v9.md` | 이 변경이력 |

### 미수정 (Protected Files)

- `src/models/agent_state.py` — 변경 없음
- `src/models/message.py` — 변경 없음
- `src/api/contracts.py` — 변경 없음
- `src/graph/workflow.py` — 변경 없음

---

## 테스트

```
총 테스트: 139개 전체 통과
- 기존: 112개 (v6~v8)
- 신규: 27개 (LLM 듀얼 프로바이더)
```

---

## 검증

```bash
python3 -m black . --check       # 통과
python3 -m ruff check .          # 통과
python3 -m isort . --check       # 통과
python3 -m mypy src/ config/     # 통과
python3 -m pytest tests/ -v      # 139개 통과
```

---

*마지막 업데이트: 2026-02-13*

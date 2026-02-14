# Mind-Log 프로젝트 종합 현황 보고서

> 최종 업데이트: 2026-02-14 (v3 — v9~v13 반영: 멀티 프로바이더, pgvector 제거, Ollama, 인프라 보호, 라이브 테스트)

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **프로젝트명** | Mind-Log |
| **목적** | 초개인화 AI 멘탈케어 & 시각화 플랫폼 |
| **핵심 기능** | 사용자의 감정·생각을 AI가 분석 → 개인화된 멘탈케어 제공 + 내면 상태 시각화 |
| **듀얼모드** | 대화모드(실시간 상담) + 팟캐스트모드(에피소드 생성) |
| **현재 버전** | v0.1.0 |
| **개발 전략** | 팟캐스트모드 우선 구현 → 대화모드 후속 |

---

## 2. 아키텍처

### 2.1 TIER 기반 파이프라인 (v4.0)

Orchestrator 없이 에이전트 간 **메시지 프로토콜 v2.0** + **LangGraph StateGraph**로 직접 통신하는 구조.

```
TIER 0: Intent Classifier → 의도 분류 + 모드 감지 + complexity_score
    ↓
TIER 1 (병렬 Fan-out):
├─ Safety Agent ─── CRISIS 시 → 모든 병렬 취소 → 즉시 위기 응답
├─ Emotion Agent
├─ Context Agent / Content Analyzer (모드별)
└─ Reasoning Agent / Podcast Reasoning (모드별)
      ├─ Memory Agent ← 조건부 호출 (독립)
      └─ Knowledge Agent ← 조건부 호출 (독립)
    ↓ (Fan-in)
TIER 2: Synthesis / Script Generator (+Visualization 병렬)
    ↓
TIER 3: Validator / Batch Validator (실패 시 TIER 2 재시도, 최대 2회)
    ↓
TIER 4: Personalization / Script Personalizer
    ↓
비동기: Visualization + Telemetry + Learning
```

### 2.2 Safety CRISIS 선점 메커니즘

Safety Agent가 `risk_level ≥ 3` 판정 시:
1. **CANCEL SIGNAL** 발행 → TIER 1 병렬 작업 전체 취소
2. Safety 심화 모드 진입 → 위기 응답 직접 생성
3. TIER 2~4 건너뜀 → 즉시 출력

### 2.3 에이전트 전체 목록 (20개)

#### 대화모드 (13개)

| # | 에이전트 | TIER | 모델 | 담당 |
|---|---------|------|------|------|
| 01 | Intent Classifier | 0 | Haiku | 개발자1 |
| 02 | Safety Agent | 1 (병렬) | Sonnet 4 | 개발자2 |
| 03 | Emotion Agent | 1 (병렬) | Sonnet 4 | 개발자2 |
| 04 | Context Agent | 1 (병렬) | Haiku | 개발자3 |
| 05 | Memory Agent | 독립 | Sonnet 4 | 개발자2 |
| 06 | Knowledge Agent | 독립 | Sonnet 4 | 개발자1 |
| 07 | Reasoning Agent | 1 (병렬) | Opus 4.6 | 개발자3 |
| 08 | Synthesis Agent | 2 | Sonnet 4 | 개발자1 |
| 09 | Validator Agent | 3 | Sonnet 4 | 개발자3 |
| 10 | Personalization Agent | 4 | Sonnet 4 | 개발자1 |
| 11 | Visualization Agent | 비동기 | Sonnet 4 | 개발자2 |
| 12 | Telemetry Agent | 비동기 | Haiku | **미정** |
| 13 | Learning Agent | 비동기 | Haiku | 개발자3 |

#### 팟캐스트모드 (7개)

| # | 에이전트 | TIER | 모델 | 담당 |
|---|---------|------|------|------|
| 01 | Content Analyzer | 1 (병렬) | Sonnet 4 | 개발자3 |
| 02 | Episode Memory | 독립 | Sonnet 4 | 개발자2 |
| 03 | Podcast Reasoning | 1 (병렬) | Sonnet 4 | 개발자3 |
| 04 | Script Generator | 2 | Sonnet 4 | 개발자1 |
| 05 | Batch Validator | 3 | Sonnet 4 | 개발자3 |
| 06 | Script Personalizer | 4 | Sonnet 4 | 개발자1 |
| 07 | Visualization (Podcast) | 2 (병렬)/비동기 | Sonnet 4 | 개발자2 |

#### 양쪽 모드 공용

Intent Classifier, Safety Agent, Emotion Agent, Knowledge Agent, Visualization Agent, Telemetry Agent, Learning Agent

---

## 3. 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| LLM | Anthropic Claude (Opus 4.6, Sonnet 4, Haiku) | 외부 API 직접 호출 + AWS Bedrock 듀얼 지원 + Ollama 로컬 개발 |
| LLM 호출 방식 | **듀얼**: 외부 API (Anthropic SDK) + AWS Bedrock | 섹션 3.1 참조 |
| 오케스트레이션 | LangGraph StateGraph | |
| 벡터 DB | Pinecone | |
| 관계형 DB | **MySQL** | ~~PostgreSQL~~ → MySQL 변경 |
| 그래프 DB | Neo4j | |
| 캐시 | Redis | |
| 이미지 저장 | S3 / CDN | |
| 프레임워크 | FastAPI + Uvicorn | |
| HTTP 클라이언트 | httpx (비동기) | |
| 데이터 검증 | Pydantic v2 | |
| 설정 관리 | PyYAML | |
| CI/CD | GitHub Actions | |
| Python | 3.12 | |
| 린팅 | Black + isort + Ruff + mypy | |
| 테스트 | pytest + pytest-asyncio | |

### 3.1 LLM 호출 방식 — 듀얼 아키텍처

두 가지 방식으로 LLM을 호출할 수 있으며, 설정으로 전환 가능하도록 설계한다.

#### 방식 A: 외부 API 직접 호출 (Anthropic SDK)

```
에이전트 → LLMClient → Anthropic SDK → Claude API (api.anthropic.com)
```

- 현재 구현된 방식 (`src/agents/shared/llm_client.py`)
- `ANTHROPIC_API_KEY` 환경변수 필요
- 장점: 간단한 설정, 빠른 개발
- 단점: API 키 관리, 요금 직접 처리

#### 방식 B: AWS Bedrock 경유

```
에이전트 → LLMClient → boto3 Bedrock Runtime → Claude on Bedrock (AWS)
```

- AWS 인프라 내에서 Claude 모델 호출
- IAM Role 기반 인증 (API 키 불필요)
- 장점: AWS 생태계 통합, VPC 내부 호출, IAM 권한 관리, 비용 통합
- 단점: AWS 의존성, 초기 설정 복잡

#### 전환 설계 (구현 완료)

```yaml
# config/settings.yaml
llm:
  provider: "anthropic"        # "anthropic" | "bedrock" | "custom"
  anthropic:
    api_key_env: "ANTHROPIC_API_KEY"
  bedrock:
    region: "us-east-1"
    # IAM Role 기반 인증 (별도 키 불필요)
  models:
    haiku: "claude-haiku-4-5-20251001"
    sonnet: "claude-sonnet-4-5-20250929"
    opus: "claude-opus-4-6"
```

```python
# LLMClient에서 provider에 따라 분기 (커스텀 프로바이더 플러그인 지원)
class LLMClient:
    _custom_providers: dict[str, type] = {}  # 외부 프로바이더 레지스트리

    def __init__(self, provider: str, ...):
        if provider in self._custom_providers:
            # 커스텀 프로바이더 (Ollama 등)
            ...
        elif provider == "bedrock":
            self._client = boto3.client("bedrock-runtime", ...)
        else:
            self._client = anthropic.AsyncAnthropic(...)
```

---

## 4. 팀 구성 및 역할

> ✅ 모든 문서가 실제 역할 배분 기준으로 업데이트 완료되었다.
> 초반 계획(Dev-A/B/C 도메인 기반)과의 차이는 [섹션 14](#14-초반-계획서-대비-변경-사항) 참조.

| 개발자 | 대화모드 에이전트 | 팟캐스트모드 에이전트 |
|--------|-----------------|-------------------|
| **개발자1** | Intent Classifier, Knowledge, Synthesis, Personalization | Script Generator, Script Personalizer |
| **개발자2** | Safety, Memory, Visualization, Emotion | Episode Memory, Visualization(Podcast) |
| **개발자3(나)** | Reasoning, Context, Validator, Learning | Podcast Reasoning, Content Analyzer, Batch Validator |
| **미정** | Telemetry Agent | — |

- **Telemetry Agent**: 전체 에이전트 개발 완료 후 담당자 결정 예정
- **Content Analyzer**: Context Agent의 팟캐스트 모드 대응이므로 개발자3 담당

### 브랜치 접두사 (현행 유지)

| 개발자 | 브랜치 접두사 |
|--------|-------------|
| 개발자1 | `feature/analysis-*` |
| 개발자2 | `feature/reasoning-*` |
| 개발자3 | `feature/validation-*` |

### 수정 불가 영역 (3인 합의 필수)

- `src/models/agent_state.py` — 공유 상태 스키마
- `src/models/message.py` — 에이전트 간 메시지 포맷
- `src/api/contracts.py` — 백엔드 API 스키마
- `src/graph/workflow.py` — LangGraph 워크플로우 정의

---

## 5. 개발 현황

### 5.1 구현 완료 (✅)

#### 핵심 인프라
| 구성 요소 | 파일 | 설명 |
|-----------|------|------|
| BaseAgent | `src/agents/shared/base_agent.py` | ABC 패턴, LLM 자동 설정, 프롬프트 자동 로드, A/B 테스트 |
| LLM 클라이언트 | `src/agents/shared/llm_client.py` | 멀티 프로바이더 LLM 클라이언트 (Anthropic + Bedrock + 커스텀) |
| PromptLoader | `src/agents/shared/prompt_loader.py` | 5계층 보안 YAML 로더, 멀티버전 지원 |
| Settings | `config/loader.py` | YAML 설정 + 환경변수, 버전/A/B 테스트 통제 |
| AgentState | `src/models/agent_state.py` | TypedDict 공유 상태 (Protected) |
| MessageProtocol | `src/models/message.py` | v2.0 통합 메시지 엔벨로프 (Protected) |
| API 클라이언트 | `src/api/client.py` | httpx 비동기 백엔드 통신 |
| API 스키마 | `src/api/contracts.py` | SaveRequest/LoadResponse (Protected) |
| 유틸리티 | `src/utils/logger.py`, `retry.py` | 로깅, 재시도 데코레이터 |

#### 팟캐스트 에이전트 (개발자3 스코프)
| 에이전트 | 파일 | TIER | 상태 |
|---------|------|------|------|
| Content Analyzer | `src/agents/podcast/content_analyzer.py` | 1 | ✅ 구현 완료 |
| Podcast Reasoning | `src/agents/podcast/podcast_reasoning.py` | 1 | ✅ 구현 완료 (GoT/ToT/CoT) |
| Batch Validator | `src/agents/podcast/batch_validator.py` | 3 | ✅ 구현 완료 (5개 기준 검증) |
| Learning Agent | `src/agents/shared/learning.py` | 비동기 | ✅ 구현 완료 |

#### 프롬프트 시스템
| 프롬프트 | 파일 | 형식 |
|---------|------|------|
| Content Analyzer | `prompts/podcast/content_analyzer.yaml` | 멀티버전 v1.0.0 |
| Podcast Reasoning | `prompts/podcast/podcast_reasoning.yaml` | 멀티버전 v1.0.0 (GoT/ToT/CoT) |
| Batch Validator | `prompts/podcast/batch_validator.yaml` | 멀티버전 v1.0.0 |
| Learning | `prompts/shared/learning.yaml` | 멀티버전 v1.0.0 |

### 5.2 미구현 / 스텁 상태 (⏳)

| 항목 | 상태 | 담당 | 비고 |
|------|------|------|------|
| Script Generator | ⏳ 스텁 | 개발자1 | TIER 2 생성 에이전트 |
| Script Personalizer | ⏳ 스텁 | 개발자1 | TIER 4 톤/스타일 조정 |
| Episode Memory | ⏳ 스텁 | 개발자2 | DI 패턴으로 Reasoning이 조건부 호출 |
| Safety Agent (전체) | ⏳ 스텁 | 개발자2 | 현재 risk_level 반환만 |
| Emotion Agent | ⏳ 스텁 | 개발자2 | |
| Intent Classifier | ⏳ 스텁 | 개발자1 | |
| Knowledge Agent (실제) | ⏳ 스텁 | 개발자1 | 현재 스텁으로 빈 결과 반환 |
| LangGraph Workflow | ⏳ 미구현 | 3인 합의 | `src/graph/workflow.py` |
| 대화모드 에이전트 13개 | ⏳ 보류 | 전원 | 팟캐스트 완료 후 착수 |

---

## 6. 버전 이력 요약

### v1 — 개발자 역할 배분
- 3인 개발자 에이전트별 담당 확정

### v2 — 팟캐스트 우선 결정
- 대화모드 보류, 팟캐스트모드부터 구현하기로 결정

### v3 — 코딩 원칙 수립
- 한국어 주석 필수, API 모델 유연성 (config 기반), 프로토콜 준수, 가독성 우선

### v4 — TIER 1 병렬 참조 버그 수정
- Podcast Reasoning의 입력에서 `content_analysis`, `emotion_vectors` 제거 (병렬 실행이므로 상호 참조 불가)

### v5 — Batch Validator 입력 추가
- `emotion_vectors`를 Batch Validator 입력에 추가 (TIER 3이므로 TIER 1 결과 참조 가능)

### v6 — 에피소드 시간 조정 + 추론 파이프라인
- 에피소드 길이: 10-20분 → **3-5분**
- complexity_score 기반 3단계 추론 깊이:
  - `full` (≥ 0.8): GoT → ToT → CoT (LLM 3회)
  - `standard` (0.5~0.8): ToT → CoT (LLM 2회)
  - `minimal` (< 0.5): CoT만 (LLM 1회)
- GoT: 개념/감정/경험 그래프 추출 (노드 4-8, 엣지 3-10)
- ToT: 에피소드 구조 대안 3-5개 생성 + 4개 기준 평가
- CoT: 상세 에피소드 설계 + 감정 여정 5단계 매핑

### v7 — 프롬프트 외부화
- Python 하드코딩 → YAML 외부 파일로 분리
- PromptLoader: 5계층 보안 (safe_load, 경로 검증, 화이트리스트, 크기 제한, 스키마 검증)
- BaseAgent 자동 연동: 에이전트 초기화 시 YAML 자동 로드
- 환경변수 `PROMPT_DIR` 지원 (dev/staging/prod)
- 테스트 85개 전체 통과

### v8 — 멀티버전 프롬프트 + A/B 테스트
- YAML 멀티버전 형식: `versions` 키 아래 SemVer별 프롬프트 공존
- settings.yaml 버전 통제:
  - `prompts.versions.default` — 글로벌 기본 버전
  - `prompts.versions.{에이전트명}` — 에이전트별 고정
- A/B 테스트:
  - `prompts.ab_tests.{에이전트명}` — variant_a/b, traffic_split, assignment
  - 세션 기반 결정적 variant 선택 (MD5 해시)
  - `contextvars.ContextVar`로 비동기 안전 격리
- YAML 4개 전부 멀티버전 형식으로 마이그레이션
- 테스트 112개 전체 통과 (기존 85 + 신규 27)

### v9 — 문서 일관성 통합 + LLM 듀얼 프로바이더 아키텍처
- LLMClient를 멀티 프로바이더 구조로 확장 (Anthropic SDK + AWS Bedrock)
- `config/settings.yaml`에 프로바이더 전환 설정 추가
- 프로젝트 문서 전체 일관성 검토 + 통합 업데이트
- 테스트 149개 전체 통과

### v10 — pgvector 제거 + MySQL 통일
- pgvector (PostgreSQL 전용) 제거 → **Pinecone 단독** 벡터 DB
- 프로젝트 문서에서 pgvector 참조 전부 삭제
- 플랜 파일 DB 스키마 PostgreSQL → MySQL 문법 전환

### v11 — Ollama 로컬 LLM 프로바이더 추가
- `dev/` 폴더에 Ollama 프로바이더 격리 (`.gitignore` 자동 제외)
- LLMClient에 `register_provider()` 플러그인 메서드 추가 (운영 코드 변경 최소)
- `docs/OLLAMA_SETUP.md` 종합 설정 가이드 작성
- 테스트 210개 전체 통과

### v12 — 공용 인프라 보호 마킹
- `[Shared Infrastructure]` 헤더를 공용 인프라 파일 4개에 추가
- CLAUDE.md에 공용 인프라 보호 섹션 강화
- 기존 public 메서드 시그니처/동작 변경 금지 규칙 명시

### v13 — 개별 에이전트 라이브 LLM 테스트
- `dev/live_tests/` 디렉토리에 멀티 프로바이더 라이브 테스트 추가
- Ollama, Anthropic API, AWS Bedrock 3종 프로바이더 지원
- CLI 러너: `--agent`, `--all`, `--pipeline`, `--provider` 옵션
- `json.loads(strict=False)` 적용 — 로컬 LLM 제어 문자 허용

---

## 7. 테스트 현황

### 전체 결과: 210 passed ✅

| 테스트 파일 | 테스트 수 | 검증 대상 |
|------------|----------|----------|
| `test_content_analyzer.py` | 6 | 콘텐츠 분석 출력, 의도 컨텍스트, 에이전트 속성 |
| `test_podcast_reasoning.py` | 28 | GoT/ToT/CoT 파이프라인, 깊이 라우팅, DI, 스텁, 하위호환 |
| `test_batch_validator.py` | 11 | 5개 기준 검증, 통과/실패/강제통과, 재시도 |
| `test_learning.py` | 8 | 학습 패턴 추출, API 저장, 에러 핸들링 |
| `test_prompt_loader.py` | 30 | YAML 로딩, 보안 (경로 순회, 크기 제한, 스키마), 캐시, BaseAgent 연동 |
| `test_prompt_versioning.py` | 27 | 멀티버전 로드, 기본/폴백 버전, A/B 테스트, Settings 연동 |
| `test_llm_client.py` | 37 | LLM 멀티 프로바이더, JSON 파싱, register_provider, Bedrock |
| **합계** | **210** | |

### 린트/타입 검사

```
✅ black --check          (코드 포매팅)
✅ ruff check .           (린팅)
✅ isort . --check        (임포트 정렬)
✅ mypy src/ config/      (타입 체크)
✅ pytest tests/ -v       (210 passed)
```

---

## 8. 프로젝트 구조

```
mind-log/
├── CLAUDE.md                          # 프로젝트 가이드 + 아키텍처 명세
├── README.md                          # 프로젝트 소개
├── CONTRIBUTING.md                    # 기여 가이드라인
├── pyproject.toml                     # pytest, black, ruff, isort, mypy 설정
├── conftest.py                        # pytest 전역 설정
├── requirements.txt                   # 의존성 목록
├── .env.example                       # 환경변수 템플릿
│
├── config/
│   ├── __init__.py
│   ├── loader.py                      # Settings 클래스 + get_settings()
│   └── settings.yaml                  # 앱/LLM/에이전트/파이프라인/API/프롬프트/기능 설정
│
├── src/
│   ├── models/
│   │   ├── agent_state.py             # [Protected] AgentState TypedDict
│   │   └── message.py                 # [Protected] MessageEnvelope v2.0
│   ├── agents/
│   │   ├── shared/
│   │   │   ├── base_agent.py          # BaseAgent ABC (v8 멀티버전 + A/B)
│   │   │   ├── llm_client.py          # 멀티 프로바이더 LLM 클라이언트 (Anthropic + Bedrock + 커스텀)
│   │   │   ├── prompt_loader.py       # YAML 프롬프트 로더 (v7+v8)
│   │   │   ├── learning.py            # Learning Agent
│   │   │   └── stubs.py               # Episode Memory & Knowledge 스텁
│   │   ├── podcast/
│   │   │   ├── content_analyzer.py    # Content Analyzer (TIER 1)
│   │   │   ├── podcast_reasoning.py   # Podcast Reasoning (GoT/ToT/CoT)
│   │   │   └── batch_validator.py     # Batch Validator (TIER 3)
│   │   └── conversation/              # [보류] 대화모드 에이전트
│   ├── api/
│   │   ├── client.py                  # BackendClient (httpx 비동기)
│   │   └── contracts.py               # [Protected] SaveRequest/LoadResponse
│   ├── graph/
│   │   └── __init__.py                # [Protected] LangGraph 워크플로우 (미구현 — 3인 합의 후 작성)
│   └── utils/
│       ├── logger.py                  # 구조화 로깅
│       └── retry.py                   # 재시도 데코레이터
│
├── prompts/                           # [.gitignore] YAML 프롬프트 (보안상 리포 미포함)
│   ├── podcast/
│   │   ├── content_analyzer.yaml      # 멀티버전 v1.0.0
│   │   ├── podcast_reasoning.yaml     # 멀티버전 v1.0.0 (GoT/ToT/CoT)
│   │   └── batch_validator.yaml       # 멀티버전 v1.0.0
│   └── shared/
│       └── learning.yaml              # 멀티버전 v1.0.0
│
├── tests/
│   ├── agents/
│   │   ├── podcast/
│   │   │   ├── test_content_analyzer.py    # 6 tests
│   │   │   ├── test_podcast_reasoning.py   # 28 tests
│   │   │   └── test_batch_validator.py     # 11 tests
│   │   ├── shared/
│   │   │   ├── test_llm_client.py          # 37 tests
│   │   │   ├── test_prompt_loader.py       # 30 tests
│   │   │   └── test_prompt_versioning.py   # 27 tests
│   │   └── conversation/                   # [보류]
│   ├── test_learning.py                    # 8 tests (기존 위치)
│   └── integration/                        # [보류]
│
├── docs/
│   ├── PROJECT_STRUCTURE.md           # 디렉토리 구조 상세
│   ├── PROJECT_SUMMARY.md            # ← 본 문서
│   ├── GIT_WORKFLOW.md                # 브랜치/커밋/PR 가이드
│   ├── QUICK_START.md                 # 환경 설정 및 빠른 시작
│   ├── OLLAMA_SETUP.md               # Ollama 로컬 LLM 설정 가이드
│   ├── PROMPT_SECURITY.md             # 프롬프트 보안 문서 [.gitignore]
│   ├── CHANGELOG_v1-v5.md            # v1~v5 변경이력
│   ├── CHANGELOG_v6.md               # v6 변경이력
│   ├── CHANGELOG_v7.md               # v7 변경이력
│   └── CHANGELOG_v9.md               # v9 변경이력
│
├── dev/                               # 로컬 개발 전용 (.gitignore — git push 제외)
│   ├── ollama_provider.py             # Ollama OpenAI 호환 API 프로바이더
│   ├── ollama_config.yaml             # Ollama 전용 설정
│   ├── ollama_bootstrap.py            # LLMClient에 Ollama 프로바이더 등록
│   ├── test_ollama.py                 # Ollama 프로바이더 단위 테스트
│   ├── README.md                      # dev/ 빠른 시작 가이드
│   └── live_tests/                    # 라이브 LLM 테스트 (멀티 프로바이더)
│       ├── run_live.py                # CLI 러너 (--agent, --all, --pipeline, --provider)
│       └── ...                        # 에이전트별 라이브 테스트 파일
│
└── .github/
    ├── workflows/ci.yml               # CI/CD 파이프라인
    └── pull_request_template.md       # PR 템플릿
```

---

## 9. 핵심 설계 패턴

### 9.1 BaseAgent ABC 패턴

모든 에이전트는 `BaseAgent`를 상속하고 `process()` 메서드만 구현한다.

```python
class ContentAnalyzerAgent(BaseAgent):
    agent_name = "content_analyzer"
    mode = "podcast"
    tier = 1
    model_key = "sonnet"

    async def process(self, state: AgentState) -> dict:
        # 1. 입력 읽기
        # 2. LLM 호출
        # 3. 결과 반환 (자기 담당 필드만)
        return {"content_analysis": result}
```

### 9.2 LangGraph 노드 반환 규칙

노드 함수는 `dict`(부분 상태)를 반환한다. 전체 `AgentState`가 아님.

```python
async def content_analyzer_node(state: AgentState) -> dict:
    agent = ContentAnalyzerAgent()
    return await agent(state)
```

### 9.3 DI 패턴 (스텁 교체)

Memory/Knowledge는 스텁으로 시작, 실제 에이전트 구현 시 교체.

```python
agent = PodcastReasoningAgent(
    episode_memory=EpisodeMemoryStub(),    # → 실제 에이전트로 교체 가능
    knowledge_agent=KnowledgeAgentStub(),
)
```

### 9.4 complexity 기반 추론 깊이 라우팅 (v6)

```
complexity >= 0.8 → full   (GoT + ToT + CoT, LLM 3회)
0.5 ≤ complexity  → standard (ToT + CoT, LLM 2회)
complexity < 0.5  → minimal  (CoT만, LLM 1회)
```

### 9.5 멀티버전 프롬프트 + A/B 테스트 (v8)

```
버전 해석 우선순위:
  A/B 테스트 variant → 에이전트별 고정 버전 → 글로벌 기본 → YAML default_version → 첫 번째 버전

A/B 테스트:
  session_id + agent_name → MD5 해시 → ratio → variant_a or variant_b
  contextvars.ContextVar로 비동기 격리
```

---

## 10. Git 브랜치 전략

```
main ← PR 머지 (3명 전원 승인 필수)
 └── develop ← 통합 테스트 브랜치 (최소 1명 리뷰)
      ├── feature/analysis-*     (개발자1)
      ├── feature/reasoning-*    (개발자2)
      └── feature/validation-*   (개발자3)  ← 현재 활성: feature/validation-podcast-agents
```

### 커밋 컨벤션

```
<type>(<scope>): <설명>

type: feat, fix, refactor, test, docs, chore
scope: intent, safety, emotion, context, memory, knowledge, reasoning,
       synthesis, validator, personal, visual, telemetry, learning,
       podcast, content, episode, script, batch, graph, api, models
```

### 현재 브랜치 상태

| 브랜치 | 기반 | 커밋 수 | 상태 |
|--------|------|---------|------|
| `feature/validation-podcast-agents` | develop | 4 | ✅ 활성 (원격 푸시 완료) |
| `develop` | main | 0 (동기화) | 기본 통합 브랜치 |
| `main` | — | 2 | 프로덕션 |

### 커밋 이력 (feature/validation-podcast-agents)

```
d345d71 docs: pgvector 제거 — Pinecone 단독 벡터 DB로 통일
146fd28 feat: 문서 일관성 통합 + LLM 듀얼 프로바이더 아키텍처 (v9)
6da2cdb feat: 프롬프트 외부화(v7) + 멀티버전/A/B 테스트(v8) 구현
e0b9619 feat(podcast): 팟캐스트 모드 에이전트 구현 (Phase 0-4 + v6 CoT/ToT/GoT)
e4267ee 커밋                          ← develop 분기점
3a3812d Initial commit: Setup mind-log project structure
```

---

## 11. API 규약

### 저장 (Save)

```
POST /api/v1/{resource}
{
  "user_id": "uuid",
  "session_id": "uuid",
  "type": "conversation | emotion_log | learning | visualization",
  "data": { ... },
  "timestamp": "2026-02-12T12:00:00Z"
}
```

### 조회 (Load)

```
GET /api/v1/{resource}?user_id={uuid}&type={type}&limit={n}
```

### 연동 원칙

- 모든 API 호출은 `src/api/` 모듈 경유 (직접 HTTP 금지)
- 타임아웃: 기본 5초, LLM 관련 30초
- 실패 시 최대 3회 재시도 (exponential backoff)

---

## 12. 주요 설계 결정 기록

| # | 결정 | 근거 |
|---|------|------|
| 1 | 팟캐스트모드 우선 구현 | 배치 처리로 파이프라인 검증이 용이 |
| 2 | Orchestrator 제거 | StateGraph + 메시지 프로토콜로 충분, 단순화 |
| 3 | 에피소드 3-5분 | 멘탈케어 마이크로 콘텐츠 최적 소비 시간 |
| 4 | 재시도 최대 2회 | 무한 루프 방지 (CLAUDE.md v4.0) |
| 5 | YAML safe_load 강제 | 임의 코드 실행 방어 |
| 6 | prompts/ 디렉토리 .gitignore | 프롬프트 보안 (리포지토리 미포함) |
| 7 | complexity 기반 추론 라우팅 | 단순 쿼리의 LLM 비용 절감 |
| 8 | 세션 기반 A/B variant | 동일 세션 내 일관된 경험 보장 |
| 9 | contextvars 사용 | LangGraph 병렬 실행에서 비동기 안전 격리 |
| 10 | DI 패턴 (스텁) | Memory/Knowledge 미구현 상태에서도 파이프라인 테스트 가능 |
| 11 | 관계형 DB → MySQL | PostgreSQL에서 MySQL로 변경 |
| 12 | LLM 트리플 프로바이더 | Anthropic SDK + AWS Bedrock + 커스텀(Ollama) 플러그인으로 유연성 확보 |
| 13 | json.loads strict=False | 로컬 LLM(Ollama 등)의 제어 문자 포함 JSON 응답 허용 |
| 14 | dev/ 폴더 격리 | 개발 전용 코드를 .gitignore로 분리, 운영 영향 0 |

---

## 13. 다음 단계 (향후 로드맵)

### 단기 (팟캐스트 파이프라인 완성)

1. **Script Generator** 구현 (개발자1) — TIER 2 스크립트 생성
2. **Script Personalizer** 구현 (개발자1) — TIER 4 톤/스타일 조정
3. **Episode Memory** 실제 구현 (개발자2) — 스텁 교체
4. **Knowledge Agent** 실제 구현 (개발자1) — 스텁 교체
5. **LangGraph Workflow** 통합 (3인 합의) — 전체 파이프라인 연결

### 중기 (대화모드 착수)

7. Intent Classifier, Safety, Emotion, Context 에이전트 구현
8. Reasoning, Memory, Knowledge, Synthesis 에이전트 구현
9. Validator, Personalization 에이전트 구현
10. 대화모드 LangGraph 워크플로우 통합

### 장기 (플랫폼 완성)

11. Visualization Agent 구현 (이미지 생성)
12. Telemetry 실시간 모니터링 (담당자 결정 후)
13. 프론트엔드 연동 (FastAPI + WebSocket)
14. 프로덕션 배포 + A/B 테스트 실전 운영

---

## 14. 초반 계획서 대비 변경 사항

프로젝트 초반 계획(CLAUDE.md, v1~v5 문서)과 현재 실제 구현 사이에 발생한 차이점을 정리한다.

### 14.1 팀 역할 배분 변경

초반 CLAUDE.md에는 **도메인 기반(Dev-A/B/C)**으로 기록되어 있으나, 실제로는 **에이전트 기반**으로 배분이 이루어졌다.

| 구분 | 초반 계획 (CLAUDE.md) | 실제 확정 |
|------|---------------------|----------|
| **명칭** | Dev-A / Dev-B / Dev-C | 개발자1 / 개발자2 / 개발자3 |
| **분류 기준** | 도메인 (분석/추론/검증) | 에이전트 단위 (도메인 혼합) |
| Intent Classifier | Dev-A (분석) | 개발자1 |
| Emotion | Dev-A (분석) | **개발자2** |
| Context | Dev-A (분석) | **개발자3** |
| Content Analyzer | Dev-A (분석) | **개발자3** (Context의 팟캐스트 대응) |
| Reasoning | Dev-B (추론) | **개발자3** |
| Memory | Dev-B (추론) | **개발자2** |
| Knowledge | Dev-B (추론) | **개발자1** |
| Synthesis | Dev-B (추론) | **개발자1** |
| Safety | Dev-C (검증) | **개발자2** |
| Validator | Dev-C (검증) | **개발자3** |
| Personalization | Dev-C (검증) | **개발자1** |
| Visualization | Dev-C (검증) | **개발자2** |
| Learning | Dev-C (검증) | **개발자3** |
| Telemetry | Dev-C (검증) | **미정** (전체 완료 후 결정) |

> 볼드체는 초반 계획과 다르게 배정된 항목

### 14.2 기술 스택 변경

| 항목 | 초반 계획 | 현재 |
|------|----------|------|
| 관계형 DB | PostgreSQL | **MySQL** |
| LLM 호출 | Anthropic SDK 직접 호출만 | **트리플: Anthropic SDK + AWS Bedrock + 커스텀(Ollama)** (구현 완료) |

### 14.3 v7/v8 — 초반 계획에 없던 신규 시스템

v7과 v8에서 도입된 기능은 **초반 CLAUDE.md에 전혀 언급되지 않았던** 완전히 새로운 인프라 계층이다.

#### 초반 계획의 가정

- 프롬프트는 Python 코드 내에 하드코딩
- 버전 관리 없음 (단일 프롬프트)
- A/B 테스트 미고려
- 환경별(dev/staging/prod) 프롬프트 분리 미고려
- 프롬프트 보안 미고려

#### v7에서 추가된 것 (초반 계획에 없음)

| 항목 | 설명 |
|------|------|
| **PromptLoader 클래스** | 전체 신규 모듈 (`src/agents/shared/prompt_loader.py`, 250+ LOC) |
| **YAML 프롬프트 파일** | `prompts/` 디렉토리 + 4개 YAML 파일 |
| **5계층 보안** | safe_load, 경로 검증, 화이트리스트, 크기 제한, 스키마 검증 |
| **BaseAgent 프롬프트 연동** | `_load_prompts()`, `get_prompt()`, `prompt_version` |
| **환경변수 분리** | `PROMPT_DIR` → dev/staging/prod 프롬프트 전환 |
| **prompts/ .gitignore** | 프롬프트 보안을 위해 리포지토리에서 제외 |
| **PROMPT_SECURITY.md** | 8개 위협 영역 보안 문서 (465줄) |
| **테스트 85개** | 프롬프트 로딩, 보안, 캐시, BaseAgent 연동 검증 |

#### v8에서 추가된 것 (초반 계획에 없음)

| 항목 | 설명 |
|------|------|
| **멀티버전 YAML 형식** | `versions` 키 아래 SemVer별 프롬프트 공존 |
| **settings.yaml 버전 통제** | `prompts.versions.default`, 에이전트별 고정 |
| **A/B 테스트 프레임워크** | variant_a/b, traffic_split, session 기반 결정적 할당 |
| **contextvars 격리** | `_active_ab_variant` ContextVar로 비동기 안전 |
| **BaseAgent A/B 메서드** | `_resolve_ab_variant()`, `_preload_ab_variants()`, `ab_variant` |
| **Settings 확장** | `get_prompt_version()`, `get_ab_test_config()` |
| **테스트 27개 추가** | 멀티버전, A/B, Settings 연동 검증 |

#### 영향받은 파일

| 파일 | 초반 계획 상태 | v7/v8 이후 상태 |
|------|--------------|----------------|
| `src/agents/shared/prompt_loader.py` | **존재하지 않음** | 신규 생성 (250+ LOC) |
| `src/agents/shared/base_agent.py` | 기본 ABC 패턴만 | +200 LOC (프롬프트 로드 + A/B 테스트) |
| `config/loader.py` | 기본 Settings만 | +70 LOC (버전 해석 + A/B 설정) |
| `config/settings.yaml` | LLM/agent 설정만 | +25줄 (prompts.versions, ab_tests) |
| `prompts/*.yaml` | **존재하지 않음** | 4개 파일 신규 생성 |
| `docs/PROMPT_SECURITY.md` | **존재하지 않음** | 465줄 보안 문서 |
| `tests/agents/shared/` | **존재하지 않음** | 57개 테스트 (prompt_loader + versioning) |

### 14.4 AgentState 필드 접근 규칙 차이

초반 계획의 필드 접근 규칙은 도메인 기반(Dev-A/B/C)이었으나, 실제 에이전트 배분이 도메인을 넘나들기 때문에 조정이 필요하다.

| 초반 계획 | 실제 상태 |
|----------|----------|
| Dev-A만 `intent`, `emotion_vectors`, `context` 쓰기 | 개발자1(Intent), 개발자2(Emotion), 개발자3(Context)이 각각 담당 |
| Dev-B만 `memory_results`, `reasoning_result` 쓰기 | 개발자2(Memory), 개발자3(Reasoning)이 각각 담당 |
| Dev-C만 `risk_level`, `validation_result` 쓰기 | 개발자2(Safety), 개발자3(Validator)이 각각 담당 |

> **결론**: 필드 접근 규칙은 "개발자별"이 아닌 "에이전트별"로 관리해야 한다.
> 각 에이전트는 자기 담당 출력 필드만 쓰고, 나머지는 읽기만 하는 원칙은 동일하게 유지.

### 14.5 재시도 횟수 차이

| 항목 | 초반 CLAUDE.md | 실제 구현 |
|------|--------------|----------|
| Validator 피드백 루프 | 최대 **3회** (Phase 4 기술) | 최대 **2회** (v4.0 TIER 아키텍처 명세 + 코드) |

> v4.0 아키텍처 재설계 시 3회 → 2회로 변경됨. 코드(`batch_validator.py`)에서도 2회로 구현되어 있음.

---

*본 문서는 프로젝트의 전체 현황을 종합한 것으로, 코드·문서·대화 이력을 기반으로 작성되었습니다.*

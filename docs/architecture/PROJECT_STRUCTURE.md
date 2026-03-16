# 프로젝트 구조

Mind-Log 멀티에이전트 AI 시스템의 디렉토리 구조 및 각 파일의 역할을 설명합니다.

---

## 전체 구조

```
mind-log/
│
├── CLAUDE.md                    # AI 개발 통합 가이드 (아키텍처 + 협업 규칙)
├── README.md                    # 프로젝트 소개
├── CONTRIBUTING.md              # 기여 가이드
├── requirements.txt             # Python 의존성
├── Dockerfile                   # Docker 빌드 설정
├── pyproject.toml               # 프로젝트 메타데이터 + 도구 설정 (black, ruff, mypy, pytest)
├── conftest.py                  # pytest 공용 fixture
├── .env.example                 # 환경변수 템플릿
├── .gitignore                   # Git 무시 파일
│
├── src/                         # 소스 코드
│   ├── __init__.py
│   │
│   ├── models/                  # 공유 데이터 모델 (Protected - 3인 합의 필수)
│   │   ├── __init__.py
│   │   ├── agent_state.py       # AgentState TypedDict 정의
│   │   └── message.py           # MessageEnvelope v2.0 통합 메시지 프로토콜
│   │
│   ├── agents/                  # 에이전트 구현
│   │   ├── __init__.py
│   │   │
│   │   ├── conversation/        # 대화모드 에이전트 (현재 2/13 구현)
│   │   │   ├── __init__.py
│   │   │   ├── intent_classifier.py   # [개발자1] TIER 0: 의도 분류 ✓
│   │   │   ├── knowledge.py           # [개발자1] 독립: 전문 지식 검색 ✓
│   │   │   # --- 미구현 (향후 추가 예정) ---
│   │   │   # safety.py              # [개발자2] TIER 1 — 현재 podcast/safety.py에서 공용
│   │   │   # emotion.py             # [개발자2] TIER 1 — 현재 podcast/emotion.py에서 공용
│   │   │   # context.py             # [개발자3] TIER 1: 맥락 관리
│   │   │   # memory.py              # [개발자2] 독립: 개인 기억 검색
│   │   │   # reasoning.py           # [개발자3] TIER 1: 심층 추론
│   │   │   # synthesis.py           # [개발자1] TIER 2: 응답 생성
│   │   │   # validator.py           # [개발자3] TIER 3: 품질 검증
│   │   │   # personalization.py     # [개발자1] TIER 4: 개인화
│   │   │   # visualization.py       # [개발자2] 비동기: 시각화
│   │   │   # telemetry.py           # [미정] 비동기: 텔레메트리
│   │   │   # learning.py            # [개발자3] 비동기 — 현재 shared/learning.py에서 공용
│   │   │
│   │   ├── podcast/             # 팟캐스트모드 에이전트 (7개)
│   │   │   ├── __init__.py
│   │   │   ├── content_analyzer.py    # [개발자3] TIER 1: 콘텐츠 분석
│   │   │   ├── episode_memory.py      # [개발자2] 독립: 에피소드 기억
│   │   │   ├── podcast_reasoning.py   # [개발자3] TIER 1: 팟캐스트 추론
│   │   │   ├── script_generator.py    # [개발자1] TIER 2: 스크립트 생성
│   │   │   ├── batch_validator.py     # [개발자3] TIER 3: 배치 검증
│   │   │   ├── script_personalizer.py # [개발자1] TIER 4: 스크립트 개인화
│   │   │   └── visualization.py       # [개발자2] TIER 2/비동기: 커버 이미지
│   │   │
│   │   └── shared/              # 공용 에이전트 유틸리티
│   │       ├── __init__.py
│   │       ├── base_agent.py    # 에이전트 공통 부모 클래스 (BaseAgent ABC)
│   │       ├── llm_client.py    # 멀티 프로바이더 LLM 클라이언트 (Anthropic + Bedrock + OpenAI + Ollama + 커스텀)
│   │       ├── prompt_loader.py # YAML 프롬프트 로더 (멀티버전 + A/B 테스트)
│   │       ├── learning.py      # Learning Agent 구현 (양쪽 모드 공용)
│   │       ├── base_memory.py   # 기억 에이전트 공통 베이스 클래스
│   │       ├── safety_constants.py # Safety Agent 공용 상수 (위기 키워드, 도움 정보 등)
│   │       └── stubs.py         # Episode Memory / Knowledge 스텁 (통합 전 임시)
│   │
│   ├── api/                     # API 계층 (엔드포인트 + 백엔드 통신)
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 앱 진입점 (lifespan, 라우터 등록)
│   │   ├── middleware.py        # 요청 추적 미들웨어, CORS 설정
│   │   ├── external_schemas.py  # 외부 API 요청/응답 + DB 저장 스키마 (SSOT)
│   │   ├── client.py            # BackendClient — 재시도, 타임아웃 포함 비동기 HTTP
│   │   ├── contracts.py         # 범용 Save/Load 요청/응답 스키마 (Protected)
│   │   ├── backend_resources.py # Backend API 리소스 경로 상수 + TODO(backend)
│   │   ├── publisher.py         # AgentDataPublisher — 에이전트 데이터 전달 유틸리티
│   │   └── routes/              # FastAPI 엔드포인트 라우터
│   │       ├── __init__.py
│   │       ├── podcasts.py      # 에피소드 생성 + BackgroundTasks 비동기 저장
│   │       ├── sessions.py      # 세션 생성/종료
│   │       └── health.py        # 헬스체크 (readiness/liveness)
│   │
│   ├── db/                      # 저장소 추상화 (현재 미사용 — 모든 영속화는 BackendClient REST API 경유)
│   │   ├── __init__.py          # 4개 ABC + 4개 팩토리 함수 export
│   │   ├── base.py              # 추상 인터페이스 (BaseVector/Graph/RDB/StorageClient)
│   │   ├── pinecone_client.py   # Pinecone 직접 클라이언트
│   │   ├── neo4j_client.py      # Neo4j 직접 클라이언트
│   │   ├── mysql_client.py      # MySQL 직접 클라이언트
│   │   ├── s3_client.py         # S3 직접 클라이언트 (읽기+쓰기)
│   │   ├── api_proxy.py         # Backend API 프록시 4종
│   │   └── factory.py           # 환경별 팩토리 (STORAGE_MODE=local|proxy|hybrid)
│   │   # NOTE: 현재 어디서도 import되지 않음. STORAGE_MODE 설정은 존재하나
│   │   # 실제 에이전트/API는 모두 BackendClient(src/api/client.py) 경유로 저장.
│   │   # 향후 직접 DB 접속이 필요할 때 활성화 예정.
│   │
│   ├── graph/                   # LangGraph 워크플로우 (Protected - 3인 합의 필수)
│   │   ├── __init__.py
│   │   └── workflow.py          # TIER 기반 듀얼모드 워크플로우 (구현 완료)
│   │
│   ├── monitoring/              # 모니터링 인프라
│   │   ├── __init__.py          # 텔레메트리 콜백, I/O 트래커, 데이터 모델 export
│   │   ├── models.py            # AgentMetric, PipelineMetrics, MonitoringEvent 등
│   │   ├── callbacks.py         # MindLogTelemetryCallback (LangGraph 콜백)
│   │   ├── io_tracker.py        # AgentIOTracker (에이전트 입출력 스냅샷)
│   │   └── prometheus.py        # Prometheus 메트릭 + GET /metrics 라우터
│   │
│   └── utils/                   # 공통 유틸리티
│       ├── __init__.py
│       ├── logger.py            # 구조화 로깅 (APP_ENV=production → JSON 포맷)
│       └── retry.py             # Exponential backoff 재시도 데코레이터
│
├── config/                      # 환경 설정
│   ├── __init__.py
│   ├── loader.py                # 설정 로더 (Settings 싱글톤 — YAML + .env 통합)
│   └── settings.yaml            # 모델, 타임아웃, 기능 플래그, 프롬프트 버전 설정
│
├── prompts/                     # 에이전트 프롬프트 YAML (.gitignore — git push 제외)
│   ├── podcast/                 # 팟캐스트모드 에이전트 프롬프트
│   │   ├── content_analyzer.yaml
│   │   ├── podcast_reasoning.yaml
│   │   └── batch_validator.yaml
│   └── shared/                  # 공용 에이전트 프롬프트
│       └── learning.yaml
│
├── tests/                       # 테스트 코드
│   ├── __init__.py
│   ├── agents/
│   │   ├── conversation/        # 대화모드 에이전트 단위 테스트
│   │   ├── podcast/             # 팟캐스트모드 에이전트 단위 테스트
│   │   │   ├── test_content_analyzer.py
│   │   │   ├── test_podcast_reasoning.py
│   │   │   └── test_batch_validator.py
│   │   ├── shared/              # 공용 인프라 테스트
│   │   │   ├── test_llm_client.py
│   │   │   ├── test_prompt_loader.py
│   │   │   └── test_prompt_versioning.py
│   │   └── test_learning.py     # Learning Agent 테스트
│   ├── api/                     # API 계층 테스트
│   │   ├── conftest.py          # compiled_graph/backend_client mock fixture
│   │   ├── test_backend_client.py   # BackendClient save/load 테스트
│   │   ├── test_publisher.py        # AgentDataPublisher 단위 테스트
│   │   ├── test_podcasts_endpoint.py # 에피소드 생성 엔드포인트 테스트
│   │   ├── test_sessions_endpoint.py # 세션 엔드포인트 테스트
│   │   ├── test_health_endpoint.py   # 헬스체크 테스트
│   │   ├── test_middleware.py        # 미들웨어 테스트
│   │   └── e2e/                      # API E2E 테스트
│   └── integration/             # 통합 테스트 (에이전트 간 연동)
│
├── docs/                        # 프로젝트 문서
│   ├── INDEX.md                 # 마스터 네비게이션
│   ├── getting-started/         # 시작 가이드
│   │   ├── QUICK_START.md       # 환경 설정 및 빠른 시작
│   │   └── OLLAMA_SETUP.md      # Ollama 로컬 LLM 설정 가이드
│   ├── architecture/            # 아키텍처 문서
│   │   ├── PROJECT_STRUCTURE.md # 이 파일
│   │   ├── AGENT_ROLES.md       # 에이전트별 역할·입출력·이슈 정의서
│   │   ├── API_SPEC.md          # REST API 명세 인덱스 (v2.0)
│   │   ├── API_ARCHITECTURE.md  # API 아키텍처 (서버 구조, 파이프라인 흐름)
│   │   ├── API_ENDPOINTS_RECEIVING.md # 수신 API (Backend→AI) 상세
│   │   ├── API_ENDPOINTS_INTERNAL.md  # 발신 API (AI→Backend) 상세
│   │   ├── API_COMMON.md        # 공통 에러 코드, 스트리밍, 재시도
│   │   └── DATA_SCHEMA_PLAN.md  # 데이터 스키마 설계 계획
│   ├── guides/                  # 개발 가이드
│   │   ├── AGENT_DEV_GUIDE.md   # 에이전트 개발 상세 가이드
│   │   ├── GIT_WORKFLOW.md      # 브랜치/커밋/PR 가이드
│   │   └── E2E_TEST_GUIDE.md    # E2E 테스트 가이드
│   ├── reports/                 # 보고서
│   │   ├── PROJECT_SUMMARY.md   # 프로젝트 현황 종합 보고서
│   │   ├── AGENT_IO_ANALYSIS.md # 에이전트 I/O 분석 보고서
│   │   ├── OLLAMA_MODEL_TEST_REPORT.md # Ollama 모델 테스트 결과
│   │   └── REFACTORING_LOG.md   # 리팩토링 이력
│   └── changelog/               # 변경이력
│       └── CHANGELOG_v*.md      # v1~v21 변경이력
│
├── dev/                         # 로컬 개발 전용 (.gitignore — git push 제외)
│   ├── ollama_provider.py       # Ollama OpenAI 호환 API 프로바이더
│   ├── ollama_config.yaml       # Ollama 전용 설정 (모델 매핑, URL, 타임아웃)
│   ├── ollama_bootstrap.py      # LLMClient에 Ollama 프로바이더 등록/해제
│   ├── test_ollama.py           # Ollama 프로바이더 단위 테스트
│   ├── README.md                # dev/ 폴더 빠른 시작 가이드
│   └── live_tests/              # 라이브 LLM 테스트 (멀티 프로바이더)
│       ├── conftest_live.py     # 공통 인프라 (프로바이더 셋업, 헬스체크)
│       ├── fixtures.py          # 현실적 한국어 AgentState 데이터
│       ├── run_live.py          # CLI 러너 (--agent, --all, --pipeline, --provider)
│       ├── test_content_analyzer_live.py
│       ├── test_podcast_reasoning_live.py
│       ├── test_batch_validator_live.py
│       ├── test_learning_live.py
│       └── test_pipeline_live.py
│
├── .github/
│   ├── workflows/ci.yml         # CI/CD 파이프라인
│   ├── pull_request_template.md # PR 템플릿
│   └── ISSUE_TEMPLATE/          # 이슈 템플릿
│
└── ProjectDocs/                 # 설계 원본 문서 (71개 — 수정 대상 아님)
    ├── INDEX.md                 # 마스터 인덱스
    ├── ARCHITECTURE_v4.0.md     # v4.0 아키텍처 확정 명세
    └── ...                      # 에이전트별 상세 설계 문서
```

---

## 핵심 디렉토리 설명

### src/models/ — 공유 데이터 모델

모든 에이전트가 사용하는 공통 스키마를 정의합니다. 3명의 개발자 모두에게 영향을 미치므로 **수정 시 전원 리뷰가 필수**입니다.

- `agent_state.py`: LangGraph에서 사용하는 AgentState TypedDict. 각 에이전트의 입출력 필드를 정의.
- `message.py`: MessageEnvelope v2.0 통합 메시지 프로토콜. 에이전트 간 직접 통신에 사용하는 메시지 포맷.

### src/agents/ — 에이전트 구현

에이전트는 모드별로 분리되어 있으며, 각 파일은 하나의 에이전트 노드를 구현합니다. 모든 에이전트는 `BaseAgent` ABC를 상속받아 `process()` 메서드를 구현하며, 변경된 필드만 `dict`로 반환합니다 (LangGraph 자동 병합).

```python
class MyAgent(BaseAgent):
    async def process(self, state: AgentState) -> dict[str, Any]:
        # 자기 담당 필드만 반환 (부분 상태)
        return {"my_field": result}
```

> **공용 에이전트 참고**: Safety Agent와 Emotion Agent는 현재 `podcast/` 디렉토리에 구현되어 있으나, 양쪽 모드(대화/팟캐스트)에서 공용으로 사용됩니다. `workflow.py`에서 두 에이전트를 모드 분기 전 공통 TIER 1에 배치하여 호출합니다. Learning Agent는 `shared/learning.py`에 구현되어 양쪽 모드에서 비동기로 호출됩니다.

### src/agents/shared/ — 공용 인프라

모든 에이전트가 의존하는 공용 코드입니다. 기존 public 메서드의 시그니처/동작 변경은 금지되며, 신규 추가만 허용됩니다.

- `base_agent.py`: BaseAgent ABC — LLM 호출, 로깅, 시간 측정, 프롬프트 로딩 공통 처리
- `llm_client.py`: 멀티 프로바이더 LLM 클라이언트 (Anthropic SDK + AWS Bedrock + OpenAI + Ollama + 커스텀 플러그인)
- `prompt_loader.py`: YAML 기반 프롬프트 로더 (멀티버전 지원 + A/B 테스트)
- `learning.py`: Learning Agent 구현 (대화/팟캐스트 양쪽 모드 공용)
- `base_memory.py`: 기억 에이전트(Memory, Episode Memory) 공통 베이스 클래스
- `safety_constants.py`: Safety Agent 공용 상수 — 위기 감지 키워드, 도움 정보, 위험 레벨 정의
- `stubs.py`: Episode Memory / Knowledge Agent 스텁 (통합 전 임시 인터페이스)

### src/api/ — API 계층

FastAPI 엔드포인트와 백엔드 서버 통신을 모두 담당합니다. 모든 HTTP 호출은 이 모듈을 통해서만 수행합니다.

- `main.py`: FastAPI 앱 진입점. lifespan으로 LangGraph/BackendClient 초기화, 라우터 등록
- `middleware.py`: 요청 추적 미들웨어(trace_id 주입), CORS 설정
- `external_schemas.py`: Backend 서버 ↔ AI ↔ 백엔드 DB 전체 데이터 스키마 (SSOT). Pydantic v2 기반
- `client.py`: `BackendClient` — `@with_retry(3)` + 타임아웃 포함 비동기 HTTP 클라이언트
- `contracts.py`: 범용 `SaveRequest`/`SaveResponse` 스키마 (Protected — 3인 합의 필수)
- `backend_resources.py`: Backend API 리소스 경로 상수. `TODO(backend):` 주석으로 협의 포인트 표시
- `publisher.py`: `AgentDataPublisher` — 에이전트가 파이프라인 실행 중 백엔드에 데이터를 전달하는 공통 유틸리티. SaveRequest 생성/에러 처리/로깅을 캡슐화
- `routes/podcasts.py`: 에피소드 생성 엔드포인트 + `_save_episode_bundle()`로 BackgroundTasks 비동기 3단계 저장
- `routes/sessions.py`: 세션 생성/종료 엔드포인트
- `routes/health.py`: readiness/liveness 헬스체크 엔드포인트

### src/db/ — 저장소 추상화 (현재 미사용)

> **NOTE**: 현재 전체 코드베이스에서 이 모듈을 import하는 곳이 없습니다. 모든 데이터 영속화는 `BackendClient` (src/api/client.py) REST API를 경유합니다. `STORAGE_MODE` 환경변수 설정은 존재하나 실제로 이 팩토리를 호출하는 코드가 없는 상태입니다.

Strategy + Factory 패턴으로 환경별(개발/배포/하이브리드) DB 접근 방식을 전환하는 설계입니다.

- `base.py`: 추상 인터페이스 4종 (`BaseVectorClient`, `BaseGraphClient`, `BaseRDBClient`, `BaseStorageClient`)
- `pinecone_client.py`, `neo4j_client.py`, `mysql_client.py`, `s3_client.py`: 직접 접속 구현체
- `api_proxy.py`: Backend API 경유 프록시 구현체 4종
- `factory.py`: `STORAGE_MODE=local|proxy|hybrid`에 따라 적절한 구현체를 반환하는 팩토리

### src/monitoring/ — 모니터링 인프라

텔레메트리 콜백, 에이전트 I/O 추적, Prometheus 메트릭을 제공합니다.

- `callbacks.py`: LangGraph 콜백 기반 TIER별 성능 메트릭, CRISIS 감지, 비용 추정
- `io_tracker.py`: 에이전트 입출력 스냅샷 캡처 + 민감정보 보호
- `prometheus.py`: `GET /metrics` 엔드포인트 + 5개 메트릭 (요청 수, CRISIS, 파이프라인/에이전트 실행 시간, LLM 토큰)

### src/graph/ — LangGraph 워크플로우

에이전트 노드들을 연결하는 StateGraph를 정의합니다. `workflow.py`에 TIER 기반 듀얼모드 파이프라인이 구현되어 있으며, `build_unified_graph()` 함수로 대화모드/팟캐스트모드 워크플로우를 통합 구성합니다.

### config/ — 설정 관리

- `loader.py`: YAML + .env 환경변수를 통합 관리하는 Settings 싱글톤
- `settings.yaml`: 에이전트별 모델/temperature, 프롬프트 버전 핀닝, A/B 테스트 설정

### dev/ — 로컬 개발 전용 (.gitignore)

`.gitignore`에 의해 git push에서 제외됩니다. Ollama 로컬 LLM 프로바이더와 라이브 LLM 테스트를 포함합니다.

### prompts/ — 에이전트 프롬프트 (.gitignore)

에이전트별 시스템 프롬프트를 YAML 파일로 관리합니다. 멀티버전 형식을 지원하며, `config/settings.yaml`에서 버전을 중앙 통제합니다.

**프롬프트 버전 선택 우선순위** (`prompt_loader.py` + `loader.py`):

1. `config/settings.yaml` → `prompts.versions.{agent_name}` (에이전트별 핀닝)
2. `config/settings.yaml` → `prompts.versions.default` (글로벌 기본값)
3. YAML 파일 내부 `default_version` 필드
4. 첫 번째 버전 (fallback)

A/B 테스트가 활성화된 경우(`prompts.ab_tests.{agent_name}.enabled: true`), 위 우선순위 대신 `variant_a`/`variant_b` 중 하나가 `traffic_split` 비율에 따라 선택됩니다.

> **NOTE**: `prompts/conversation/` 디렉토리에 12개 YAML 파일이 있으나, 그 중 7개(emotion, memory, safety, synthesis, personalization, telemetry, visualization)는 `[TODO]` 스텁입니다. 대화모드 에이전트 구현 시 실제 프롬프트로 교체 필요.

---

## 파일 소유권 규칙

| 표시 | 의미 |
|------|------|
| [개발자1] | 개발자1 소유 (브랜치: feature/analysis-*) |
| [개발자2] | 개발자2 소유 (브랜치: feature/reasoning-*) |
| [개발자3] | 개발자3 소유 (브랜치: feature/validation-*) |
| [미정] | 담당자 미정 (전체 에이전트 완료 후 배정) |
| Protected | 3인 합의 후에만 수정 가능 |

---

*참고: 에이전트 상세 설계는 ProjectDocs/ 폴더의 개별 에이전트 문서를 참조하세요.*

*마지막 업데이트: 2026-03-13*

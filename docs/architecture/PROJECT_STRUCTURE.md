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
│   │   ├── conversation/        # 대화모드 에이전트 (13개)
│   │   │   ├── __init__.py
│   │   │   ├── intent_classifier.py   # [개발자1] TIER 0: 의도 분류
│   │   │   ├── safety.py              # [개발자2] TIER 1: 안전성 검사
│   │   │   ├── emotion.py             # [개발자2] TIER 1: 감정 분석
│   │   │   ├── context.py             # [개발자3] TIER 1: 맥락 관리
│   │   │   ├── memory.py              # [개발자2] 독립: 개인 기억 검색
│   │   │   ├── knowledge.py           # [개발자1] 독립: 전문 지식 검색
│   │   │   ├── reasoning.py           # [개발자3] TIER 1: 심층 추론
│   │   │   ├── synthesis.py           # [개발자1] TIER 2: 응답 생성
│   │   │   ├── validator.py           # [개발자3] TIER 3: 품질 검증
│   │   │   ├── personalization.py     # [개발자1] TIER 4: 개인화
│   │   │   ├── visualization.py       # [개발자2] 비동기: 시각화
│   │   │   ├── telemetry.py           # [미정] 비동기: 텔레메트리
│   │   │   └── learning.py            # [개발자3] 비동기: 학습
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
│   │       ├── llm_client.py    # 멀티 프로바이더 LLM 클라이언트 (Anthropic + Bedrock + 커스텀)
│   │       ├── prompt_loader.py # YAML 프롬프트 로더 (멀티버전 + A/B 테스트)
│   │       ├── learning.py      # Learning Agent 구현 (양쪽 모드 공용)
│   │       └── stubs.py         # Episode Memory / Knowledge 스텁 (통합 전 임시)
│   │
│   ├── api/                     # 백엔드 API 통신 (Protected - 3인 합의 필수)
│   │   ├── __init__.py
│   │   ├── client.py            # HTTP 클라이언트 (재시도, 타임아웃)
│   │   └── contracts.py         # 요청/응답 스키마 정의
│   │
│   ├── graph/                   # LangGraph 워크플로우 (Protected - 3인 합의 필수)
│   │   ├── __init__.py
│   │   └── workflow.py          # TIER 기반 듀얼모드 워크플로우 (구현 완료)
│   │
│   └── utils/                   # 공통 유틸리티
│       ├── __init__.py
│       ├── logger.py            # 구조화 로깅 설정
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
│   │   ├── API_SPEC.md          # REST API 명세
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
│       └── CHANGELOG_v*.md      # v1~v19 변경이력 (10개)
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

### src/agents/shared/ — 공용 인프라

모든 에이전트가 의존하는 공용 코드입니다. 기존 public 메서드의 시그니처/동작 변경은 금지되며, 신규 추가만 허용됩니다.

- `base_agent.py`: BaseAgent ABC — LLM 호출, 로깅, 시간 측정, 프롬프트 로딩 공통 처리
- `llm_client.py`: 멀티 프로바이더 LLM 클라이언트 (Anthropic SDK + AWS Bedrock + 커스텀 플러그인)
- `prompt_loader.py`: YAML 기반 프롬프트 로더 (멀티버전 지원 + A/B 테스트)
- `learning.py`: Learning Agent 구현 (대화/팟캐스트 양쪽 모드 공용)
- `stubs.py`: Episode Memory / Knowledge Agent 스텁 (통합 전 임시 인터페이스)

### src/api/ — 백엔드 API 통신

백엔드 서버와의 통신을 담당합니다. 모든 HTTP 호출은 이 모듈을 통해서만 수행합니다.

### src/graph/ — LangGraph 워크플로우

에이전트 노드들을 연결하는 StateGraph를 정의합니다. `workflow.py`에 TIER 기반 듀얼모드 파이프라인이 구현되어 있으며, `build_unified_graph()` 함수로 대화모드/팟캐스트모드 워크플로우를 통합 구성합니다.

### config/ — 설정 관리

- `loader.py`: YAML + .env 환경변수를 통합 관리하는 Settings 싱글톤
- `settings.yaml`: 에이전트별 모델/temperature, 프롬프트 버전 핀닝, A/B 테스트 설정

### dev/ — 로컬 개발 전용 (.gitignore)

`.gitignore`에 의해 git push에서 제외됩니다. Ollama 로컬 LLM 프로바이더와 라이브 LLM 테스트를 포함합니다.

### prompts/ — 에이전트 프롬프트 (.gitignore)

에이전트별 시스템 프롬프트를 YAML 파일로 관리합니다. 멀티버전 형식을 지원하며, `config/settings.yaml`에서 버전을 중앙 통제합니다.

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

*마지막 업데이트: 2026-02-14*

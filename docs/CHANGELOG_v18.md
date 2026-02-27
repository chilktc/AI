# 변경이력 v18

> 날짜: 2026-02-27

---

## v18: E2E 멀티 프로바이더 테스트 + OpenAI 프로바이더 정식 통합 + LangSmith 트레이싱

### 배경

v17에서 공통 인프라(workflow.py, 통합 테스트, 개발 가이드)가 완성된 후, 다음 단계로:

1. **OpenAI를 프로덕션 프로바이더로 정식 통합** — Anthropic, Bedrock과 동일한 레벨에 배치
2. **E2E 멀티 프로바이더 테스트** — Ollama(로컬)와 OpenAI(API)로 동일 파이프라인을 실행하고 결과를 비교하는 테스트 프레임워크 구축
3. **LangSmith 트레이싱** — `@traceable` 기반 에이전트 트레이싱으로 fan-out 노드에서도 개별 에이전트 실행을 추적할 수 있도록 개선
4. **코드 품질 개선** — workflow.py 노드명 정규화, 테스트 환경변수 격리, 모델 매핑 버그 수정

### 신규 파일 (3개)

| 파일 | 내용 |
|------|------|
| `dev/live_tests/test_e2e_multi_provider.py` | E2E 멀티 프로바이더 파이프라인 테스트. Ollama(gpt-oss:20b, qwen2.5:14b) + OpenAI(gpt-4o-mini) 비교 실행, 결과 테이블 출력, LangGraph compile-only 검증 포함 |
| `docs/E2E_TEST_GUIDE.md` | E2E 테스트 실행 가이드 — 전제조건, CLI 옵션, 결과 해석, 트러블슈팅, 비용 참고 |
| `docs/REFACTORING_LOG.md` | 리팩토링 이력 — 이번 세션 4건 기록 |

### 수정 파일 (11개)

| 파일 | 변경 내용 |
|------|----------|
| `config/settings.yaml` | `openai_models` 섹션 추가 (haiku→gpt-4o-mini, sonnet→gpt-4o-mini, opus→gpt-4o), provider 주석에 `openai` 추가 |
| `config/loader.py` | `get_openai_model_id()` 신규 메서드 추가 — 환경변수 `LLM_OPENAI_MODEL_{KEY}` 오버라이드 지원, fallback gpt-4o-mini |
| `src/agents/shared/llm_client.py` | OpenAI 모델 매핑 버그 수정 — `agent_config.get("model", "gpt-4")` → `settings.get_openai_model_id(model_key)` 사용으로 변경 (Bedrock 패턴 통일) |
| `src/agents/shared/base_agent.py` | `_traced_process()` 메서드 추가 — `@traceable` 래핑으로 LangSmith child span 생성, `__call__`에서 호출 |
| `src/graph/workflow.py` | 3개 그래프 빌더 노드명 변경 — tier 기반(`tier0`, `tier1_safety`) → 에이전트명(`intent_classifier`, `safety`) |
| `tests/agents/shared/test_llm_client.py` | `autouse` fixture 추가 — 테스트 간 `LLM_PROVIDER` 환경변수 격리, Settings 싱글톤 리셋 |
| `requirements.txt` | `openai>=1.0.0` 추가 (Core 섹션), `langsmith>=0.2.0` 추가 |
| `dev/live_tests/conftest_live.py` | `_setup_openai()` + `_check_openai_health()` 함수 추가, `setup_provider()`/`check_provider_health()` 라우팅에 OpenAI 분기 추가 |
| `dev/live_tests/run_live.py` | `SUPPORTED_PROVIDERS`에 `"openai"` 추가, `--e2e` 옵션 추가, `run_e2e()` 핸들러 추가 |
| `dev/live_tests/fixtures.py` | `make_e2e_state()` 함수 추가 — 직장 내 뒷담화 시나리오 (complexity_score=0.75) |
| `.env.example` | OpenAI 섹션 추가 (`OPENAI_API_KEY` 플레이스홀더) |

### 문서 업데이트 (1개)

| 파일 | 변경 내용 |
|------|----------|
| `dev/live_tests/README.md` | OpenAI 프로바이더 + E2E 테스트 섹션 추가, CLI 옵션 업데이트, 파일 구조 업데이트 |

### OpenAI 프로바이더 아키텍처

OpenAI는 **프로덕션 프로바이더**로서 Anthropic, Bedrock과 동일한 레벨에 배치:

```
config/settings.yaml          ← openai_models 매핑 정의
config/loader.py              ← get_openai_model_id() 조회
src/agents/shared/llm_client.py ← OpenAI 분기에서 settings 매핑 사용
```

모델 매핑:

| 에이전트 모델 키 | OpenAI 모델 | 용도 |
|-----------------|------------|------|
| haiku | gpt-4o-mini | 경량 작업 |
| sonnet | gpt-4o-mini | 표준 작업 (비용 효율적) |
| opus | gpt-4o | 복잡한 추론 |

환경변수 오버라이드: `LLM_OPENAI_MODEL_SONNET=gpt-4o`

### 리팩토링 요약

| # | 대상 | 변경 내용 | 근거 |
|---|------|----------|------|
| 1 | `base_agent.py` | `_traced_process()` 추가 | LangSmith에서 fan-out 노드 내부 에이전트 실행을 child span으로 추적 |
| 2 | `workflow.py` | 노드명 tier→에이전트명 | LangSmith/LangGraph Studio에서 노드를 직관적으로 식별 |
| 3 | `test_llm_client.py` | autouse fixture | 테스트 간 환경변수 격리로 순서 의존성 제거 |
| 4 | `llm_client.py` | OpenAI 모델 매핑 수정 | "sonnet"을 OpenAI에 직접 전송하던 버그 수정 → settings 매핑 사용 |

### 검증

- 기존 테스트: **257개 전체 통과** (`pytest tests/ -v`)
- `ruff check src/ tests/`: All checks passed
- LangGraph 3개 그래프 빌더 노드명 확인 (에이전트명 기반)
- `test_llm_client.py`: 37/37 passed (autouse fixture 포함)

---

*마지막 업데이트: 2026-02-27*

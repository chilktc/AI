# Refactoring Log — develop → main 병합 전 정리

> **⚠️ 아카이브**: 이 문서는 v18(2026-02-26)까지의 리팩토링 이력만 포함합니다.
> v19~v27 이후 변경사항은 `docs/changelog/` 개별 파일을 참조하세요.

**날짜**: 2026-02-26
**기준 커밋**: c5039db (공용코드 기준)
**대상 브랜치**: develop (7f4121f)

---

## 1. 개발자3 삭제 파일 복원

개발자1의 PR(feature/analysis-integration) 머지 과정에서 개발자3의 에이전트 3개 + 테스트 3개가 삭제됨.
c5039db에서 복원:

| 파일 | 유형 |
|------|------|
| `src/agents/podcast/batch_validator.py` | 에이전트 (TIER 3) |
| `src/agents/podcast/content_analyzer.py` | 에이전트 (TIER 1) |
| `src/agents/podcast/podcast_reasoning.py` | 에이전트 (TIER 1) |
| `tests/agents/podcast/test_batch_validator.py` | 테스트 |
| `tests/agents/podcast/test_content_analyzer.py` | 테스트 |
| `tests/agents/podcast/test_podcast_reasoning.py` | 테스트 |

---

## 2. src/agents/common/ 이동 및 삭제

개발자1이 별도로 생성한 `src/agents/common/` (5파일) 처리. 병합은 없음.

### 처리 상세

| 원본 (common/) | 처리 방식 | 대상 위치 | 사유 |
|---------------|----------|----------|------|
| `common/schemas.py` | **이동** (복사 후 원본 삭제, 주석만 보강) | `src/models/schemas.py` | 에이전트 전용 Pydantic 모델 → models 디렉토리 |
| `common/config.py` | **삭제** (중복 제거) | — (`config/app_config.py`와 100% 동일) | 기존 파일이 이미 존재하여 단순 삭제 |
| `common/llm_client.py` | **삭제** (중복 제거) | — | 프로덕션 Ollama 지원이 이미 존재 (LLMClient + OllamaProvider + ollama_bootstrap) — 중복 파일 삭제 |
| `common/protocols.py` | **삭제** | — | `src/models/message.py` (Protected)가 정식 프로토콜 — 간략 버전 삭제 |
| `common/__init__.py` | **삭제** | — | 디렉토리 제거 |

### common/ vs 공용코드 차이

| common/ 파일 | 공용코드 대응 | 차이점 |
|-------------|-------------|--------|
| `protocols.py` (AgentMessage) | `src/models/message.py` (MessageEnvelope) | message.py가 더 엄격한 타입 (Literal, IntEnum, Priority Enum) 사용 |
| `llm_client.py` (OllamaClient) | `shared/llm_client.py` (LLMClient) | 역할 다름: Ollama=로컬테스트, LLMClient=프로덕션(Anthropic/Bedrock/OpenAI) |
| `config.py` | `config/app_config.py` | 100% 동일 내용 |

---

## 3. BaseAgent 상속 리팩토링

개발자1의 에이전트 4개가 독자 클래스로 구현 → BaseAgent 상속으로 전환.

### 변경 대상

| 에이전트 | 파일 | TIER | 변경 사항 |
|---------|------|------|----------|
| IntentClassifierAgent | `src/agents/conversation/intent_classifier.py` | 0 | BaseAgent(name="intent_classifier", tier=0) 상속 |
| KnowledgeAgent | `src/agents/conversation/knowledge.py` | None | BaseAgent(name="knowledge") 상속 |
| ScriptGeneratorAgent | `src/agents/podcast/script_generator.py` | 2 | BaseAgent(name="script_generator", tier=2) 상속 |
| ScriptPersonalizerAgent | `src/agents/podcast/script_personalizer.py` | 4 | BaseAgent(name="script_personalizer", tier=4) 상속 |

### 변경 패턴

```python
# Before (독자 클래스)
class IntentClassifierAgent:
    def __init__(self):
        self.llm_client = LLMClient(agent_name="intent_classifier")
    async def process(self, state: AgentState) -> dict: ...

# After (BaseAgent 상속)
class IntentClassifierAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="intent_classifier", tier=0)
    async def process(self, state: AgentState) -> dict: ...
```

### 상세 변경 내역

**공통:**
- `import logging` + `logger = logging.getLogger(__name__)` 제거 → `self.logger` (BaseAgent 제공) 사용
- `from src.agents.shared.llm_client import LLMClient` 제거 (BaseAgent가 자동 초기화)
- `self.llm_client.generate()` → `self.call_llm()` (LLM 호출 횟수 자동 추적)
- `self.llm_client.generate_json()` → `self.call_llm_json()` (LLM 호출 횟수 자동 추적)

**IntentClassifierAgent 특이사항:**
- 조건부 LLM: `use_llm=False` 시 `self.llm_client = None` 유지
- Redis 캐싱 로직 변경 없음

**ScriptGeneratorAgent 특이사항:**
- `provider_override="openai"` 유지 — `super().__init__()` 후 `self.llm_client` 재설정

**ScriptPersonalizerAgent 특이사항:**
- 조건부 LLM: `enable_deep_personalization=False` 시 `self.llm_client = None`

### Import 경로 변경

| 에이전트 | 변경 전 | 변경 후 |
|---------|---------|---------|
| intent_classifier | `from src.agents.common.config import ...` | `from config.app_config import ...` |
| intent_classifier | `from src.agents.common.schemas import ...` | `from src.models.schemas import ...` |
| script_personalizer | `from src.agents.common.config import ...` | `from config.app_config import ...` |
| script_personalizer | `from src.agents.common.schemas import ...` | `from src.models.schemas import ...` |

---

## 4. workflow.py 스텁 교체

구현 파일이 존재하는 6개 에이전트의 스텁을 실제 import로 교체.

### 교체된 스텁 → 실제 import

| 노드 | import 경로 | 개발자 |
|------|-----------|--------|
| `safety_node` | `src.agents.podcast.safety` | 개발자2 |
| `emotion_node` | `src.agents.podcast.emotion` | 개발자2 |
| `visualization_node` | `src.agents.podcast.visualization` | 개발자2 |
| `content_analyzer_node` | `src.agents.podcast.content_analyzer` | 개발자3 |
| `podcast_reasoning_node` | `src.agents.podcast.podcast_reasoning` | 개발자3 |
| `batch_validator_node` | `src.agents.podcast.batch_validator` | 개발자3 |

### 유지된 스텁 (구현 파일 없음)

| 노드 | 사유 |
|------|------|
| `context_node` | 개발자3 대화모드 — 미구현 |
| `reasoning_node` | 개발자3 대화모드 — 미구현 |
| `synthesis_node` | 개발자1 대화모드 — 미구현 |
| `validator_node` | 개발자3 대화모드 — 미구현 |
| `personalization_node` | 개발자1 대화모드 — 미구현 |
| `telemetry_node` | 담당 미정 |

---

## 5. 테스트 파일 수정

| 파일 | 변경 |
|------|------|
| `tests/agents/conversation/test_intent_classifier.py` | `src.agents.common.llm_client` → `dev.utils.ollama_client` |
| `tests/agents/podcast/test_script_personalizer.py` | `src.agents.common.schemas` → `src.models.schemas` |
| `tests/agents/podcast/test_script_personalizer.py` | `src.agents.common.llm_client` → `dev.utils.ollama_client` |

---

## 6. 삭제된 파일 목록

| 파일 | 사유 |
|------|------|
| `src/agents/common/__init__.py` | 디렉토리 제거 |
| `src/agents/common/config.py` | config/app_config.py로 통합 |
| `src/agents/common/schemas.py` | src/models/schemas.py로 이동 |
| `src/agents/common/protocols.py` | src/models/message.py 사용 |
| `src/agents/common/llm_client.py` | 프로덕션 Ollama 인프라와 중복 — 삭제 |
| `dev/utils/ollama_client.py` | 프로덕션 Ollama 인프라와 중복 — 삭제 (섹션 8 참조) |
| `test_ollama.py` | 루트 레벨 스크래치 |
| `test_req.py` | 루트 레벨 스크래치 |
| `req_out.txt` | 생성 파일 |

---

## 7. 변경하지 않은 파일

### Protected Files (인터페이스 변경 없음)
- `src/models/agent_state.py`
- `src/models/message.py`
- `src/api/contracts.py`

### Shared Infrastructure (인터페이스 변경 없음)
- `src/agents/shared/base_agent.py`
- `src/agents/shared/llm_client.py`
- `src/agents/shared/prompt_loader.py`
- `src/agents/shared/base_memory.py`
- `config/loader.py`

---

## 8. dev/utils/ollama_client.py 삭제

이전 리팩토링(섹션 2)에서 `common/llm_client.py` → `dev/utils/ollama_client.py`로 이동했으나,
재검토 결과 프로덕션 인프라와 **완전 중복**임이 확인되어 삭제.

### 중복 근거

| 기능 | ollama_client.py (삭제) | 프로덕션 인프라 (유지) |
|------|------------------------|---------------------|
| Ollama 연결 | OllamaClient 클래스 — OpenAI SDK 직접 사용 | `dev/ollama_provider.py` — OllamaProvider 클래스 |
| 부트스트랩 | create_ollama_client() 팩토리 | `dev/ollama_bootstrap.py` — register_ollama() |
| LLMClient 통합 | 독립 클래스 (통합 안 됨) | LLMClient.register_provider() 플러그인 |
| 테스트 픽스처 | 없음 (`__main__` 블록에서 직접 사용) | `tests/conftest.py` — llm_client 세션 픽스처 |
| 설정 관리 | 하드코딩 base_url | config/settings.yaml + 환경변수 |

### 영향 범위

ollama_client.py를 참조하던 테스트 파일 2곳의 `if __name__ == "__main__"` 블록 정리:
- `tests/agents/conversation/test_intent_classifier.py` — ollama 직접 실행 블록 제거
- `tests/agents/podcast/test_script_personalizer.py` — ollama 직접 실행 블록 제거

이 블록들은 CI 테스트 스위트에 포함되지 않으며, 정식 테스트는 conftest.py의 llm_client 픽스처 사용.

### Ollama 관련 정식 인프라 (유지)

| 파일 | 역할 |
|------|------|
| `dev/ollama_provider.py` | OllamaProvider — LLMClient 플러그인 |
| `dev/ollama_bootstrap.py` | register_ollama() — 프로바이더 등록 |
| `tests/conftest.py` | llm_client 픽스처 — Ollama 포인팅 |
| `src/agents/shared/llm_client.py` | register_provider() 메서드 — 커스텀 프로바이더 지원 |

---

## 9. src/models/schemas.py 데드코드 제거

schemas.py의 21개 클래스 중 10개가 미사용 데드코드로 확인되어 제거.
파일 자체는 유지 (11개 클래스가 활발히 사용 중).

### 제거된 클래스 (10개)

| 클래스 | 유형 | 제거 사유 |
|--------|------|----------|
| `IntentType` | Enum | 코드에서 문자열 리터럴로 직접 사용, enum 미참조 |
| `FormailtyLevel` | Enum | 오타 포함 (Formailty), 어디서도 미사용 |
| `AttitudeType` | Enum | config/app_config.py에서 문자열 직접 사용 |
| `JourneyType` | Enum | 어디서도 import/참조 없음 |
| `IntentClassifierInput` | Pydantic 모델 | 미사용 — 에이전트가 AgentState dict 직접 접근 |
| `ScriptPersonalizerInput` | Pydantic 모델 | 미사용 — 에이전트가 AgentState dict 직접 접근 |
| `ConversationState` | Pydantic 모델 | AgentState(TypedDict, agent_state.py)가 정식 스키마 |
| `PodcastState` | Pydantic 모델 | AgentState(TypedDict, agent_state.py)가 정식 스키마 |

### 유지된 클래스 (11개)

| 클래스 | 사용 파일 |
|--------|----------|
| `DetectedEntities` | intent_classifier.py |
| `IntentFlags` | intent_classifier.py |
| `IntentClassifierOutput` | intent_classifier.py |
| `EmotionalJourney` | script_personalizer.py |
| `UserProfile` | script_personalizer.py |
| `TTSMarker` | script_personalizer.py |
| `ScriptSegment` | script_personalizer.py |
| `ValidatedScript` | script_personalizer.py |
| `PersonalizationMeta` | script_personalizer.py |
| `PersonalizedScript` | script_personalizer.py |
| `LearningEvent` | script_personalizer.py |

---

## 2026-02-27 (v18) — LangSmith 트레이싱 + 코드 품질 개선

### 10. `base_agent.py` — LangSmith 트레이싱 래퍼

**변경 파일:** `src/agents/shared/base_agent.py`

**변경 전:**
- `__call__` → `self.process()` 직접 호출
- LangSmith에서 fan-out 노드 실행 시 개별 에이전트가 하나의 span으로 합쳐져 디버깅 어려움

**변경 후:**
- `_traced_process()` 메서드 추가 — `@traceable` 데코레이터로 child span 생성
- `__call__` → `self._traced_process()` → `self.process()` 체이닝
- `run_name`에 에이전트 클래스명 포함 (`ContentAnalyzerAgent.process`)
- `langsmith` 미설치 시 graceful fallback (`self.process()` 직접 호출)

**근거:** LangSmith Studio에서 `tier1_fan_out` 같은 병렬 노드를 전개하면 Safety, Emotion, Content Analyzer 등 각 에이전트가 별도 child span으로 표시되어 디버깅이 직관적

**인터페이스 영향:** 없음 (기존 `process()` 시그니처 유지)

---

### 11. `workflow.py` — 노드명 정규화

**변경 파일:** `src/graph/workflow.py`

**변경 전:**
```python
graph.add_node("tier0", intent_classifier_node)
graph.add_node("tier1_safety", safety_node)
graph.add_node("tier1_emotion", emotion_node)
```

**변경 후:**
```python
graph.add_node("intent_classifier", intent_classifier_node)
graph.add_node("safety", safety_node)
graph.add_node("emotion", emotion_node)
```

**적용 범위:** `build_conversation_graph()`, `build_podcast_graph()`, `build_unified_graph()` 3개 함수

**근거:**
- LangSmith/LangGraph Studio에서 노드를 에이전트명으로 직관적 식별
- CLAUDE.md 아키텍처 문서의 노드 등록 규칙과 일치
- 엣지/라우팅 코드도 함께 업데이트

---

### 12. `test_llm_client.py` — 환경변수 격리 fixture

**변경 파일:** `tests/agents/shared/test_llm_client.py`

**변경 전:**
- 일부 테스트에서 `LLM_PROVIDER` 환경변수를 설정 후 정리하지 않음
- 테스트 실행 순서에 따라 다른 테스트에 영향 가능

**변경 후:**
```python
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """테스트 간 LLM 환경변수 격리."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL_SONNET", raising=False)
    monkeypatch.delenv("LLM_MODEL_HAIKU", raising=False)
    import config.loader
    config.loader._settings_instance = None
```

**근거:** 테스트 순서 독립성 보장, CI에서 간헐적 실패 방지

---

### 13. `llm_client.py` — OpenAI 모델 매핑 수정

**변경 파일:** `src/agents/shared/llm_client.py`

**변경 전:**
```python
model_key = agent_config.get("model", "gpt-4")
self._model_id = model_override or agent_config.get("model_id", model_key)
```

**변경 후:**
```python
model_key = agent_config.get("model", "sonnet")
self._model_id = model_override or agent_config.get(
    "model_id", settings.get_openai_model_id(model_key)
)
```

**근거:** Bedrock 분기(`settings.get_bedrock_model_id()`)와 동일한 패턴으로 통일. "sonnet"을 OpenAI API에 직접 전송하던 버그 수정

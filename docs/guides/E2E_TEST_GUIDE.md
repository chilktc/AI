# E2E LangGraph 워크플로우 멀티 프로바이더 테스트 가이드

> 실제 LangGraph 워크플로우(`build_unified_graph() → compile() → ainvoke()`)를 통해
> intent_classifier부터 END까지 전체 노드가 동작하는 것을 검증한다. 팟캐스트모드 기본.

---

## 목적

- **전체 워크플로우 검증** — LangGraph `ainvoke()`로 TIER 0 → TIER 1(병렬) → TIER 2 → TIER 3 → TIER 4 → 비동기 → END 전체 흐름 동작 확인
- 프로바이더/모델 간 **응답 품질 비교** (주제 분석, 추론 전략, 검증 점수)
- **상태 전파 검증** — 8개 주요 필드가 모든 프로바이더에서 올바르게 생성되는지 확인

## 전제조건

### 공통

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
pip install -r requirements.txt
```

### Ollama (로컬 모델)

```bash
# Ollama 설치 (https://ollama.com)
brew install ollama          # macOS

# 테스트 모델 다운로드
ollama pull gpt-oss:20b
ollama pull qwen2.5:14b

# 서버 시작
ollama serve

# 연결 확인
curl http://localhost:11434/v1/models
```

### OpenAI API

```bash
# .env 파일에 API 키 추가 (절대 코드에 직접 저장하지 마세요)
echo "OPENAI_API_KEY=sk-..." >> .env
```

> **보안 주의:** API 키는 반드시 `.env` 파일에만 저장한다. 코드나 커밋에 포함하지 마시오.

> **기본 프로바이더:** `config/settings.yaml`의 `provider: bedrock` (AWS Bedrock)가 운영 기본이다.
> 프롬프트 최적화 테스트(Round 4)에서는 OpenAI `gpt-4o-mini`를 사용했으며, Ollama는 로컬 개발용으로 유지.
> 프로바이더 전환: `.env`에 `LLM_PROVIDER=openai` 또는 `LLM_PROVIDER=anthropic` 설정.

---

## 빠른 시작

### 전체 테스트 (Ollama 2모델 + OpenAI)

```bash
python3 -m dev.live_tests.test_e2e_multi_provider
```

### Ollama만 테스트

```bash
python3 -m dev.live_tests.test_e2e_multi_provider --ollama-only
```

### OpenAI만 테스트

```bash
python3 -m dev.live_tests.test_e2e_multi_provider --openai-only
```

### 커스텀 입력으로 테스트

```bash
python3 -m dev.live_tests.test_e2e_multi_provider --input dev/live_tests/test_inputs/my_scenario.json
```

### run_live CLI에서 실행

```bash
python3 -m dev.live_tests.run_live --e2e
python3 -m dev.live_tests.run_live --e2e --input test_inputs/my_scenario.json
```

---

## CLI 옵션

```
python3 -m dev.live_tests.test_e2e_multi_provider [-h]
    [--ollama-only | --openai-only]
    [--ollama-models MODELS]
    [--openai-model MODEL]
    [--input FILE]

선택:
  --ollama-only           Ollama 모델만 테스트
  --openai-only           OpenAI만 테스트
  --ollama-models MODELS  Ollama 모델 (콤마 구분, 기본: gpt-oss:20b,qwen2.5:14b)
  --openai-model MODEL    OpenAI 모델 (기본: gpt-4o-mini)
  --input FILE            커스텀 테스트 입력 JSON 파일 경로
  -h, --help              도움말 출력
```

### 사용 예시

```bash
# Ollama 모델 변경
python3 -m dev.live_tests.test_e2e_multi_provider --ollama-models mistral-small:24b,phi4:14b

# OpenAI 고성능 모델 테스트
python3 -m dev.live_tests.test_e2e_multi_provider --openai-only --openai-model gpt-4o

# 커스텀 입력으로 Ollama만 테스트
python3 -m dev.live_tests.test_e2e_multi_provider --ollama-only --input test_inputs/my_case.json
```

---

## LangGraph 워크플로우 실행 흐름

> TIER 기반 파이프라인 전체 구조는 [CLAUDE.md](../CLAUDE.md#팟캐스트모드-실행-흐름)를 참조하세요.

`test_e2e_multi_provider.py`는 실제 LangGraph `ainvoke()`를 호출하여 `build_unified_graph() → compile() → ainvoke(state)` 전체 파이프라인을 실행한다.

### Mock 최소화

| 대상 | Mock 여부 | 사유 |
|------|----------|------|
| 모든 에이전트 | **REAL** | 팟캐스트 경로 전부 구현 완료 |
| `BackendClient.save()` | **Mock** | 백엔드 서버 미실행 (Learning Agent + AgentDataPublisher 경유: Emotion·Content Analyzer) |
| LLM 호출 | **REAL** | Ollama/OpenAI 실제 API 사용 |
| Telemetry | **콜백** | LangGraph 콜백으로 동작 (`MindLogTelemetryCallback`), 독립 노드 아님 |

### 초기 상태 (최소 입력)

IntentClassifier에 전달하는 초기 상태는 **최소한의 필드만** 포함한다:

```python
{
    "user_input": "- 상황: ... - 자신의 생각: ... - 자신의 행동 및 반응: ... - 동료의 반응: ...",
    "user_id": "user_e2e_graph_001",
    "session_id": "sess_e2e_graph_001",
    "mode": "podcast",
}
```

`intent`는 pre-fill 하지 않는다 — IntentClassifier가 LLM으로 실제 분류한다.

---

## 커스텀 테스트 데이터

### JSON 입력 파일 형식

`dev/live_tests/test_inputs/` 디렉토리에 JSON 파일을 생성한다:

```json
{
    "user_input": "- 상황: 테스트할 내용...\n- 자신의 생각: ...\n- 자신의 행동 및 반응: ...\n- 동료의 반응: ...",
    "mode": "podcast",
    "user_id": "user_custom_001",
    "session_id": "sess_custom_001"
}
```

| 필드 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `user_input` | ✅ | — | IntentClassifier에 전달할 사용자 입력 텍스트 |
| `mode` | ❌ | `"podcast"` | 실행 모드 (`"podcast"`) |
| `user_id` | ❌ | `"user_e2e_graph_001"` | 사용자 ID |
| `session_id` | ❌ | `"sess_e2e_graph_001"` | 세션 ID |

### 기본 제공 파일

`dev/live_tests/test_inputs/default_podcast.json` — 직장 내 뒷담화 시나리오

### 입력 로딩 우선순위

1. `--input <파일경로>` CLI 옵션 → JSON 파일에서 로드
2. 지정하지 않으면 → `fixtures.make_e2e_state()` 기본값 사용

---

## 프로바이더 전환 시 모듈 재로드

### 아키텍처 (v27~)

에이전트는 모듈 레벨 싱글톤이 아니라 **노드 함수 내부에서 요청마다 새로 생성**된다.
따라서 프로바이더 전환 시 싱글톤 리프레시가 불필요하며, Settings 리셋 + 모듈 재로드만 하면 된다.

### 프로바이더 전환 방법

```python
import importlib
from config import loader as settings_mod
from src.graph import workflow

# 1. Settings 싱글톤 리셋 (환경변수 재로드)
settings_mod._settings_instance = None

# 2. workflow 모듈 재로드 (노드 함수가 새 Settings로 에이전트 생성)
importlib.reload(workflow)
```

> **참고**: `reset_agents()` 함수는 v27에서 제거되었다. 에이전트가 요청별로 생성되므로
> 모듈 재로드만 하면 새 프로바이더 설정이 자동 적용된다.

---

## 결과 검증

### 검증 필드 (8개)

| 필드 | 출처 | 검증 조건 |
|------|------|----------|
| `intent` | IntentClassifier (TIER 0) | dict, `mode` 키 존재 |
| `safety_flags` | Safety (TIER 1) | dict |
| `emotion_vectors` | Emotion (TIER 1) | dict |
| `content_analysis` | ContentAnalyzer (TIER 1) | dict, `main_theme` 존재 |
| `reasoning_result` | PodcastReasoning (TIER 1) | dict, `episode_structure` 존재 |
| `script_draft` | ScriptGenerator (TIER 2) | dict, `segments` 존재 |
| `validation_result` | BatchValidator (TIER 3) | dict |
| `final_output` | ScriptPersonalizer (TIER 4) | str, 비어있지 않음 |

### 비교 테이블 예시

```
Provider/Model          Status  Total   Fields  Main Theme              Confidence    BV Score
─────────────────────────────────────────────────────────────────────────────────────────────────
ollama/gpt-oss:20b        [OK]  182.3s     8/8  직장 내 뒷담화와 갈등         0.78        0.85
ollama/qwen2.5:14b        [OK]   95.1s     8/8  직장 인간관계 갈등            0.85        0.88
openai/gpt-4o-mini        [OK]   28.3s     8/8  직장 갈등과 소통              0.92        0.91
```

### 비교 관점

1. **속도**: OpenAI API > Ollama (네트워크 지연 vs 로컬 추론 시간)
2. **필드 완성도**: 8/8이면 모든 에이전트가 정상 동작
3. **주제 분석 정확도**: Main Theme이 입력 시나리오를 얼마나 정확히 반영하는지
4. **검증 점수**: 높을수록 생성된 스크립트 품질이 좋음

---

## 트러블슈팅

### OpenAI API 키 미설정

```
[SKIP] OpenAI — OPENAI_API_KEY 미설정
  .env 파일에 OPENAI_API_KEY=sk-... 을 추가하세요.
```

OpenAI 키가 없으면 해당 테스트만 건너뛴다 (에러가 아님).

### Ollama 모델 미설치

```
[SKIP] ollama/gpt-oss:20b — 헬스체크 실패
```

`ollama pull gpt-oss:20b`로 모델을 먼저 다운로드한다.

### JSON 파싱 실패 (Ollama)

작은 로컬 모델은 JSON 형식을 정확히 반환하지 못할 수 있다. JSON 안정성이 높은 모델(`qwen2.5:14b`, `mistral-small:24b`)을 사용한다.

### 타임아웃 (Ollama)

대형 모델(20b+)은 GPU 없이 실행 시 2분 이상 소요될 수 있다.
전체 워크플로우(10개 에이전트)는 총 5~10분 이상 걸릴 수 있다.

### 모듈 재로드 실패

```
WARNING: 모듈 재로드 실패 — src.graph.workflow: ...
```

workflow 모듈 reload 실패 시 이전 프로바이더의 설정으로 실행될 수 있다.
한 번에 하나의 프로바이더만 테스트하려면 `--ollama-only` 또는 `--openai-only` 옵션을 사용한다.

---

## 비용 참고

### OpenAI API

| 모델 | 테스트 1회 예상 비용 |
|------|---------------------|
| gpt-4o-mini | $0.05~0.20 (전체 워크플로우) |
| gpt-4o | $0.30~1.00 (전체 워크플로우) |

> 전체 워크플로우는 10개 에이전트가 각각 LLM을 호출하므로, 단일 에이전트 테스트보다 비용이 높다.

### Ollama

로컬 실행이므로 API 비용 없음. GPU/CPU 자원만 소비.

---

## pytest 마커별 실행

`pyproject.toml`에 정의된 마커를 사용하여 테스트를 선택적으로 실행할 수 있다.

```bash
# 단위 테스트만
pytest -m unit

# 통합 테스트만
pytest -m integration

# 실제 LLM 호출 테스트 제외
pytest -m "not live"

# 느린 테스트 제외
pytest -m "not slow"

# 단위 + 통합만 (live 제외)
pytest -m "unit or integration"
```

### 마커 정의

| 마커 | 설명 |
|------|------|
| `unit` | 외부 의존성 없는 단위 테스트 |
| `integration` | 에이전트 간 연동 통합 테스트 |
| `live` | 실제 LLM API 호출 (느림, 비용 발생) |
| `slow` | 5초 이상 소요되는 테스트 |

---

## 누락 테스트 목록

아래 핵심 파일들은 아직 테스트가 작성되지 않았다. 우선순위별로 정리:

### 높음 — 데이터 모델/계약

| 파일 | 역할 | 필요 테스트 |
|------|------|------------|
| `src/models/agent_state.py` | 공유 상태 스키마 | 필드 타입 검증, 필드 병합 로직 |
| `src/models/message.py` | 에이전트 간 메시지 포맷 | 메시지 생성·직렬화 |
| `src/api/contracts.py` | 백엔드 API 요청/응답 스키마 | 스키마 검증, 직렬화/역직렬화 |

### 중간 — 유틸리티/인프라

| 파일 | 역할 | 필요 테스트 |
|------|------|------------|
| `src/utils/retry.py` | 재시도 로직 | 재시도 횟수, backoff, 예외 전파 |
| `src/api/client.py` | 백엔드 API 클라이언트 | 성공/실패 응답 처리, 타임아웃 |
| `src/models/schemas.py` | 데이터 모델 | Pydantic 검증, 기본값 |

---

*마지막 업데이트: 2026-03-13*

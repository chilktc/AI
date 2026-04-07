# Mind-Log 프로젝트 종합 점검 — 미완료·미구현·미해결 항목 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트 전체 계획서(7개)와 코드베이스를 전수 점검하여 발견된 미완료·미구현·미해결 항목을 우선순위별로 해결한다.

**Architecture:** 기존 7개 계획서의 코드 검증 + 전체 테스트 실행 + import 에러·설정 불일치·TODO 전수 조사 결과를 기반으로, 실제 문제가 되는 항목만 추출하여 Task로 구성. 총 5차 조사(초기 + 심층 + 3회 추가 라운드) 결과 반영.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, pytest, GitHub Actions, AWS Bedrock/SSM

---

## 점검 방법론

1. **기존 계획서 7개의 Phase별 코드 검증** — 실제 파일/함수 존재 여부 확인
2. **전체 테스트 스위트 실행** — `pytest tests/ -v` (350건 수집, 1 collection error, 1 fail, 336 pass, 13 skip)
3. **깨진 import / 삭제된 모듈 참조 전수 검색** — conversation/, shared/learning, 싱글톤 잔재
4. **TODO/FIXME/stub 전수 조사** — 27건 발견, 미구현 기능 분류
5. **설정 불일치** — settings.yaml vs 실제 코드 동작 교차 검증
6. **프롬프트 버전 핀닝 동작 검증** — PromptLoader 실제 호출 테스트
7. **워크플로우 그래프 교차 검증** — build_podcast_graph() vs build_unified_graph() 노드 등록 비교
8. **린팅 전수 점검** — black, ruff, isort, mypy 실행 및 위반 집계
9. **Dead code 추적** — AgentState 필드/next_step 라우팅 실제 소비 여부 검증
10. **문서 정합성** — CONTRIBUTING.md, CLAUDE.md vs 실제 코드 구조 비교

---

## 전체 계획서 진행 현황 요약

| # | 계획서 | 전체 상태 | 잔여 |
|---|--------|---------|------|
| 1 | 동시 요청 격리 (03-30) | ✅ 완료 | — |
| 2 | Bedrock 최적화 v1 (03-30) | ⚠️ 코드 완료, EC2 미실행 | Task 15 |
| 3 | Bedrock 최적화 v2 (03-31) | ⚠️ 코드 완료, EC2 미실행 | Task 15 |
| 4 | 잔여 이슈 조사 (03-31) | ⚠️ D-2,C-2 완료 / D-3 미완료 | .env printf 전환 |
| 5 | 코드 품질 점검 (03-31) | ✅ Phase 1-9 완료 | — |
| 6 | 대화모드 잔재 제거 (03-31) | ⚠️ Phase 4 부분 완료 | 스키마 7개 미삭제, CONTRIBUTING.md |
| 7 | DB 통합 테스트 (03-16) | ✅ 완료 | — |

---

## 발견된 미완료·미구현·미해결 항목 전체 목록

### A. 테스트 실패 / 수집 에러 (즉시 수정 필요)

| # | 파일 | 문제 | 심각도 |
|---|------|------|--------|
| **A-1** | `tests/api/e2e/test_e2e_podcast.py:61-64` | **ImportError — 싱글톤 참조 4건**. `safety_agent`, `emotion_agent`, `content_analyzer_agent`, `podcast_reasoning_agent` import 시도하지만 v27에서 싱글톤 제거됨. **pytest 수집 단계에서 전체 파일 에러** → 350건 중 1 collection error | CRITICAL |
| **A-2** | `dev/manual_tests/run_vis_test.py:2` | `from src.agents.podcast.visualization import visualization_agent` — 싱글톤 참조. 또한 `mode="conversation"` 사용 (삭제된 모드) | HIGH |
| **A-3** | `dev/local_db/test_e2e_podcast.py:103` | `"src.agents.shared.learning"` — 삭제된 모듈 경로. learning은 `src.agents.podcast.learning`으로 이동됨 | HIGH |
| **A-4** | `src/agents/podcast/episode_memory.py:138-141` | **모듈 레벨 싱글톤 잔재**. `episode_memory_agent = EpisodeMemoryAgent()` — v27 동시 요청 격리에서 누락. 현재 workflow 노드로 등록되어 있지 않아 직접적 영향은 없지만, 독립 에이전트 통합 시 문제될 수 있음 | MEDIUM |
| **A-5** | `tests/agents/podcast/test_episode_memory.py` | **소스 파일 누락** — `.pyc` 캐시만 존재(`__pycache__/test_episode_memory.cpython-312-pytest-9.0.2.pyc`). `.py` 원본 삭제됨. 에피소드 메모리 에이전트 테스트 커버리지 부재 | MEDIUM |

### B. 프롬프트 버전 불일치 (운영 품질 영향)

| # | 에이전트 | settings.yaml 핀닝 | 실제 프롬프트 파일 | 문제 |
|---|---------|-------------------|-----------------|------|
| **B-1** | content_analyzer | v2.1.0 | 레거시 형식, v1.0.1만 존재 | **최적화된 v2.1.0이 `_archive/`에 멀티버전 형식으로 있으나 active 파일은 레거시**. PromptLoader가 레거시 형식에서 version 파라미터를 무시하므로 v1.0.1 사용 중 |
| **B-2** | podcast_reasoning | v3.0.0 | 레거시 형식, v1.0.2만 존재 | **최적화된 v3.0.0이 `_archive/`에 멀티버전 형식으로 있으나 active 파일은 레거시**. v1.0.2 사용 중 |

> batch_validator는 정상 — 멀티버전 형식, default_version="2.3.0", 실제 2.3.0 버전 존재

### C. 대화모드 잔재 (conversation-removal Phase 4 미완료)

| # | 파일 | 잔재 | 비고 |
|---|------|------|------|
| **C-1** | `src/api/external_schemas.py` | 대화 전용 Pydantic 스키마 **7개** 미삭제 | `ConversationRequest`, `ConversationContextHint`, `ConversationPreferences`, `ConversationResponse`, `ConversationResponseMeta`, `MySQLConversationTurn`, `PineconeConversationVector` — 코드베이스 어디에서도 import/사용되지 않음 확인 |
| **C-2** | `src/api/contracts.py:23` | 주석에 `"conversation"` 타입 언급 | Protected File — 주석만 수정 |
| **C-3** | `src/agents/podcast/intent_classifier.py:1` | 헤더 주석 `# agents/conversation/intent_classifier.py` — 이전 경로 참조 | 코스메틱 |
| **C-4** | `CONTRIBUTING.md:15-18,93` | **삭제된 `src/agents/conversation/` 디렉토리 참조**. 개발자별 담당 영역 표에 conversation 에이전트 6개 나열 (synthesis, memory, reasoning, context, validator, telemetry). 테스트 경로에도 `tests/agents/{conversation,podcast}/` 형식 | HIGH |

### D. 설정 불일치 / 미사용 설정

| # | 파일:라인 | 문제 | 심각도 |
|---|----------|------|--------|
| **D-1** | `config/settings.yaml:133-135` | `visualization_podcast` 에이전트 설정 — 대응 파일/클래스 없음. `visualization`과 중복 | MEDIUM |
| **D-2** | `config/settings.yaml:155-157` | `telemetry` 에이전트 설정 — telemetry_node는 workflow에서 삭제됨 (대화모드 잔재). 모니터링은 callback+Prometheus+LangSmith로 처리 | MEDIUM |
| **D-3** | `config/settings.yaml:211-217` | `features` 섹션 — 코드에서 전혀 읽지 않음. `get_feature_flag()` 메서드 미구현 | LOW |
| **D-4** | `.env.example:57-61` | `ENABLE_PODCAST_MODE` 등 4개 환경변수 — 코드에서 미참조 | LOW |

### E. 미구현 기능 (TODO)

| # | 파일:라인 | 내용 | 심각도 |
|---|----------|------|--------|
| **E-1** | `script_personalizer.py:642-652` | `enable_deep_personalization` 파라미터가 `create_script_personalizer_node()`에서 하드코딩 `False`. settings.yaml에 `deep_personalization: false` 값이 있지만 읽지 않음 | MEDIUM |
| **E-2** | `src/api/external_schemas.py:226,317` | 텍스트 필드 `max_length` 확정 필요 (`TODO(입력 제한)`) | LOW |

### F. 배포 워크플로우 미수정

| # | 파일:라인 | 문제 | 심각도 |
|---|----------|------|--------|
| **F-1** | `.github/workflows/deploy.yml:89-102` | `.env` 값 기록 시 `echo` 사용 — 셸 특수문자(`$`, `` ` ``) 해석 위험. `printf '%s\n'`으로 전환 필요 (remaining-issues D-3) | MEDIUM |

### G. Bedrock EC2 테스트 미실행 (인프라 작업)

| # | 항목 | 상태 |
|---|------|------|
| **G-1** | Bedrock 모델 벤치마크 Phase 0-3 | `dev/live_tests/results/bedrock_model_test/` 비어있음 — EC2에서 한 번도 실행되지 않음 |
| **G-2** | settings.yaml 최적 모델 반영 | G-1 완료 후 진행 |

### H. 백엔드 팀 협의 대기 (이번 계획 범위 밖)

| # | 항목 | 건수 |
|---|------|------|
| H-1 | `TODO(backend)` — API 엔드포인트 확정 | 14건 (api_proxy.py 10, backend_resources.py 4) |
| H-2 | API Key 인증 | 백엔드 합의 전 미구현 |
| H-3 | 체크포인트 영속화 | 백엔드 DB 지원 협의 필요 |
| H-4 | 토큰 예산 관리 | 추후 |
| H-5 | Rate Limiting | API Gateway 레벨 (인프라팀) |

### I. 워크플로우 / 라우팅 결함 (3차 조사 발견)

| # | 파일:라인 | 문제 | 심각도 |
|---|----------|------|--------|
| **I-1** | `src/graph/workflow.py:558-559` | **build_unified_graph()에서 batch_validator, script_personalizer에 timeout 래퍼 미적용**. `build_podcast_graph()`(lines 498-504)은 `_with_timeout()` 래퍼를 올바르게 적용하지만, 실제 운영 진입점인 `build_unified_graph()`는 plain 노드 함수를 직접 등록. **운영 환경에서 TIER 3-4 무한 대기 가능** | **CRITICAL** |
| **I-2** | `src/agents/podcast/intent_classifier.py:118,154,176` | **next_step dead code** — IntentClassifier가 `"safety_intervention"`, `"process_normal"` 값을 설정하지만, `route_after_tier0()`(line 396)은 이 값을 읽지 않고 항상 `"tier1_podcast"` 반환. next_step 값이 라우팅에 전혀 영향을 주지 않음 | MEDIUM |
| **I-3** | `src/agents/podcast/batch_validator.py:74,104,128,139` + `workflow.py:413-451` | **Batch Validator next_step dead code** — batch_validator가 `"retry_script"`, `"script_personalizer"` 등 next_step을 설정하지만, `route_after_tier3_podcast()` 라우터가 `validation_result.verdict` 필드로 직접 판단하여 next_step 무시 | LOW |

### J. 린팅 컴플라이언스 (3차 조사 발견)

| # | 도구 | 위반 건수 | 비고 |
|---|------|----------|------|
| **J-1** | Black (포맷팅) | 68파일 리포맷 필요 | 114 파일 중 68 파일 |
| **J-2** | Ruff (린팅) | 168 에러 (90 자동수정 가능) | 78건 수동 수정 필요 |
| **J-3** | isort (import 정렬) | 0 파일 (현재 시점, Task 수정 후 재확인 필요) | — |
| **J-4** | mypy (타입 검사) | 61 에러 / 17 파일 | 주요: knowledge(7), intent_classifier(6), episode_memory(5), routes(8) |

> CI 린트 잡(`ci.yml`)이 black/ruff/isort/mypy 4개 전부를 실행하므로, 현재 **CI가 모든 PR에서 lint 실패** 상태.

---

## 우선순위별 실행 순서

| 순서 | Task | 항목 | 난이도 | EC2 | 비고 |
|------|------|------|--------|-----|------|
| 1 | Task 1 | A-1: test_e2e_podcast.py 싱글톤 import 수정 | 낮음 | ❌ | CI 테스트 차단 해제 |
| 2 | Task 2 | A-2,A-3: dev/ 하위 파일 싱글톤/경로 수정 | 낮음 | ❌ | |
| 3 | Task 3 | A-4: episode_memory.py 싱글톤 잔재 제거 | 낮음 | ❌ | |
| 4 | **Task 4** | **I-1: build_unified_graph() timeout 래퍼 추가** | **중간** | ❌ | **운영 진입점 — CRITICAL** |
| 5 | Task 5 | B-1,B-2: 프롬프트 파일 멀티버전 복원 | 중간 | ❌ | 운영 품질 직접 영향 |
| 6 | Task 6 | C-1~C-4: 대화모드 스키마/주석/문서 잔재 삭제 | 낮음 | ❌ | CONTRIBUTING.md 포함 |
| 7 | Task 7 | D-1,D-2: settings.yaml 미사용 에이전트 설정 제거 | 낮음 | ❌ | |
| 8 | Task 8 | E-1: deep_personalization settings 연동 | 낮음 | ❌ | |
| 9 | Task 9 | F-1: deploy.yml printf 전환 | 낮음 | ❌ | |
| 10 | Task 10 | D-3,D-4: 미사용 features/환경변수 정리 | 낮음 | ❌ | |
| 11 | Task 11 | I-2,I-3: Dead code 정리 (next_step) | 낮음 | ❌ | |
| 12 | Task 12 | A-5: test_episode_memory.py 테스트 복원 | 중간 | ❌ | |
| 13 | Task 13 | J-1~J-4: 린팅 컴플라이언스 수정 | 높음 | ❌ | 68+168+0+61건 (isort 재확인) |
| 14 | Task 14 | CI 파이프라인 검증 | 낮음 | ❌ | Task 1~13 완료 후 |
| 15 | Task 15 | G-1,G-2: Bedrock EC2 테스트 + settings 반영 | 중간 | ✅ | EC2 접근 필요 |

---

## 파일 구조

| 파일 | 역할 | 변경 유형 | Task |
|------|------|----------|------|
| `tests/api/e2e/test_e2e_podcast.py` | E2E 팟캐스트 테스트 | 수정 (싱글톤→노드 함수/클래스) | T1 |
| `dev/manual_tests/run_vis_test.py` | 수동 시각화 테스트 | 수정 (싱글톤→인스턴스 생성, mode 수정) | T2 |
| `dev/local_db/test_e2e_podcast.py` | 로컬 DB E2E 테스트 | 수정 (learning 경로) | T2 |
| `src/agents/podcast/episode_memory.py` | 에피소드 메모리 에이전트 | 수정 (싱글톤 제거) | T3 |
| `src/graph/workflow.py` | LangGraph 워크플로우 | 수정 (timeout 래퍼 추가) | T4 |
| `prompts/podcast/content_analyzer.yaml` | CA 프롬프트 | 교체 (_archive/에서 멀티버전 복원) | T5 |
| `prompts/podcast/podcast_reasoning.yaml` | PR 프롬프트 | 교체 (_archive/에서 멀티버전 복원) | T5 |
| `src/api/external_schemas.py` | API 스키마 | 수정 (대화 스키마 7개 삭제) | T6 |
| `src/api/contracts.py` | API 계약 | 수정 (주석만 — Protected File) | T6 |
| `src/agents/podcast/intent_classifier.py` | 의도 분류기 | 수정 (헤더 주석 + dead code) | T6, T11 |
| `CONTRIBUTING.md` | 기여 가이드 | 수정 (conversation/ 참조 제거) | T6 |
| `docs/getting-started/QUICK_START.md` | 빠른 시작 가이드 | 수정 (conversation/ 참조 20건+) | T6 |
| `docs/guides/AGENT_DEV_GUIDE.md` | 에이전트 개발 가이드 | 수정 (conversation/ 참조 1건) | T6 |
| `config/settings.yaml` | 설정 | 수정 (미사용 에이전트 제거) | T7, T10 |
| `src/agents/podcast/script_personalizer.py` | 스크립트 개인화 | 수정 (settings 연동) | T8 |
| `.github/workflows/deploy.yml` | CI/CD 배포 | 수정 (printf 전환) | T9 |
| `.env.example` | 환경변수 문서 | 수정 (미사용 변수 제거) | T10 |
| `src/agents/podcast/batch_validator.py` | 배치 검증기 | 수정 (dead code 주석) | T11 |
| `tests/agents/podcast/test_episode_memory.py` | 에피소드 메모리 테스트 | 생성 (소스 복원) | T12 |
| `src/**/*.py`, `tests/**/*.py` | 전체 소스 | 수정 (black, ruff, isort, mypy) | T13 |

---

## Task 1: test_e2e_podcast.py 싱글톤 import 에러 수정

**항목:** A-1 | **심각도:** CRITICAL | **난이도:** 낮음

**Files:**
- Modify: `tests/api/e2e/test_e2e_podcast.py:61-77`

> 이 파일은 v27 싱글톤 제거 후 업데이트되지 않아 `pytest` 수집 단계에서 **전체 파일 ImportError** 발생.
> 싱글톤 변수(`safety_agent` 등)를 에이전트 클래스 직접 인스턴스 생성으로 교체한다.
> `_force_cheap_model()`도 싱글톤 참조이므로 요청별 인스턴스 패턴에 맞게 수정한다.

- [ ] **Step 1: 현재 파일의 import와 _force_cheap_model 확인**

`tests/api/e2e/test_e2e_podcast.py:58-78` 읽기.

깨진 import (lines 61-64):
```python
from src.agents.podcast.safety import safety_agent          # ← 존재하지 않음
from src.agents.podcast.emotion import emotion_agent        # ← 존재하지 않음
from src.agents.podcast.content_analyzer import content_analyzer_agent  # ← 존재하지 않음
from src.agents.podcast.podcast_reasoning import podcast_reasoning_agent  # ← 존재하지 않음
```

- [ ] **Step 2: import를 클래스 import로 교체**

Lines 61-64를 다음으로 교체:
```python
from src.agents.podcast.safety import SafetyAgent
from src.agents.podcast.emotion import EmotionAgent
from src.agents.podcast.content_analyzer import ContentAnalyzerAgent
from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
```

- [ ] **Step 3: _force_cheap_model() 함수를 요청별 인스턴스 패턴으로 수정**

Lines 66-78의 `_force_cheap_model()` 함수 전체를 수정.
싱글톤 참조 대신 에이전트를 요청별로 생성하여 모델을 주입하는 패턴으로 변경:

```python
def _force_cheap_model():
    """요청별 에이전트 인스턴스의 llm_client에 하이쿠 주입"""
    agents = {
        "safety": SafetyAgent(),
        "emotion": EmotionAgent(),
        "content_analyzer": ContentAnalyzerAgent(),
        "podcast_reasoning": PodcastReasoningAgent(),
    }
    for name, agent in agents.items():
        if hasattr(agent, "llm_client"):
            agent.llm_client._model_id = CHEAP_MODEL
            print(f"  ✅ {name} 연결 완료")
```

> ⚠️ **검증 결과**: `_force_cheap_model()`는 **사실상 dead code**이다.
> - 워크플로우가 노드 함수 내부에서 요청마다 **새 에이전트 인스턴스를 생성**하므로,
>   이 함수에서 인스턴스를 mutate해도 실제 실행되는 인스턴스에 영향이 없다.
> - 실제 모델 강제는 `patched_generate` 몽키패치(line 26)가 담당한다.
> - lines 71-73의 `getattr(wf, ...)` 호출도 모두 `None`을 반환한다 (workflow.py에 모듈 레벨 싱글톤 없음).
>
> **결론**: import 에러 해결을 위해 클래스 import로 교체하되, `_force_cheap_model()` 함수 전체를
> dead code 주석과 함께 간소화하거나 삭제를 검토한다. 최소한 import 에러는 반드시 해결한다.

- [ ] **Step 4: import 검증**
```bash
python3 -c "import tests.api.e2e.test_e2e_podcast" 2>&1
```
Expected: ImportError 없음

- [ ] **Step 5: 커밋**

```bash
git add tests/api/e2e/test_e2e_podcast.py
git commit -m "fix: test_e2e_podcast.py 싱글톤 import 제거 — v27 동시요청 격리 반영

safety_agent, emotion_agent 등 모듈 레벨 싱글톤이 v27에서 제거되었으나
이 테스트 파일이 업데이트되지 않아 pytest 수집 에러 발생.
클래스 직접 import로 교체."
```

---

## Task 2: dev/ 하위 파일 싱글톤/경로 수정

**항목:** A-2, A-3 | **심각도:** HIGH | **난이도:** 낮음

**Files:**
- Modify: `dev/manual_tests/run_vis_test.py:2,11,18`
- Modify: `dev/local_db/test_e2e_podcast.py:103`

- [ ] **Step 1: run_vis_test.py 수정**

Line 2 — 싱글톤 import 교체:
```python
# 변경 전
from src.agents.podcast.visualization import visualization_agent
# 변경 후
from src.agents.podcast.visualization import VisualizationAgent
```

Line 11 — `mode="conversation"` → `mode="podcast"`:
```python
# 변경 전
mode="conversation",
# 변경 후
mode="podcast",
```

Line 18 — 싱글톤 사용 교체:
```python
# 변경 전
result = await visualization_agent.process(state)
# 변경 후
agent = VisualizationAgent()
result = await agent.process(state)
```

- [ ] **Step 2: test_e2e_podcast.py (dev/local_db/) 수정**

Line 103 — 삭제된 모듈 경로 교체:
```python
# 변경 전
"src.agents.shared.learning",
# 변경 후
"src.agents.podcast.learning",
```

- [ ] **Step 3: 커밋**

```bash
git add dev/manual_tests/run_vis_test.py dev/local_db/test_e2e_podcast.py
git commit -m "fix: dev/ 하위 파일 싱글톤 참조 및 삭제 모듈 경로 수정

- run_vis_test.py: visualization_agent 싱글톤 → VisualizationAgent 인스턴스
- run_vis_test.py: mode='conversation' → 'podcast'
- test_e2e_podcast.py: src.agents.shared.learning → src.agents.podcast.learning"
```

---

## Task 3: episode_memory.py 싱글톤 잔재 제거

**항목:** A-4 | **심각도:** MEDIUM | **난이도:** 낮음

**Files:**
- Modify: `src/agents/podcast/episode_memory.py:138-141`

> v27 동시 요청 격리에서 모든 에이전트의 모듈 레벨 싱글톤을 제거했으나,
> episode_memory.py의 싱글톤이 누락됨. 현재 workflow 노드로 등록되어 있지 않아
> 직접 호출되지는 않지만, 독립 에이전트 통합 시 동시 요청 격리 위반이 발생할 수 있음.

- [ ] **Step 1: 싱글톤 + 노드 래퍼를 요청별 인스턴스 패턴으로 수정**

`src/agents/podcast/episode_memory.py` 하단(lines 138-141)을 교체:

```python
# 변경 전
episode_memory_agent = EpisodeMemoryAgent()

async def episode_memory_node(state: AgentState):
    return await episode_memory_agent(state)

# 변경 후
async def episode_memory_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Episode Memory.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = EpisodeMemoryAgent()
    return await agent(state)
```

필요한 import 추가 (파일 상단에 없다면):
```python
from typing import Any
```

- [ ] **Step 2: 테스트 실행**

```bash
pytest tests/ -v --tb=short --ignore=tests/api/e2e/test_e2e_podcast.py -x -q 2>&1 | tail -5
```
Expected: 기존 테스트 전체 통과 (episode_memory는 workflow 미등록이므로 영향 없음)

- [ ] **Step 3: 커밋**

```bash
git add src/agents/podcast/episode_memory.py
git commit -m "fix: episode_memory.py 모듈 레벨 싱글톤 제거 — v27 동시요청 격리 누락분

다른 에이전트는 v27에서 요청별 인스턴스로 전환 완료했으나
episode_memory.py가 누락됨. 노드 함수 내부에서 인스턴스 생성하도록 수정."
```

---

## Task 4: build_unified_graph() timeout 래퍼 추가 ★ CRITICAL

**항목:** I-1 | **심각도:** CRITICAL | **난이도:** 중간

**Files:**
- Modify: `src/graph/workflow.py:558-559`

> **핵심 문제**: 실제 운영 진입점인 `build_unified_graph()`에서 batch_validator와
> script_personalizer 노드가 timeout 래퍼 없이 등록되어 있다.
> `build_podcast_graph()`(lines 498-504)은 올바르게 `_with_timeout()` 래퍼를 적용하지만,
> `build_unified_graph()`(lines 558-559)는 plain 노드 함수를 직접 등록한다.
>
> **위험**: LLM 호출이 응답하지 않을 경우 TIER 3-4에서 무한 대기 발생.
> `_TIER3_TIMEOUT`, `_TIER4_TIMEOUT` 상수는 이미 정의되어 있으므로 래핑만 추가하면 됨.
>
> ⚠️ `src/graph/workflow.py`는 **Protected File** (3인 합의 필요). 주석으로 변경 사유를 명시한다.

- [ ] **Step 1: 현재 build_unified_graph() 노드 등록 확인**

`src/graph/workflow.py` lines 550-565 읽기. 다음과 같은 패턴 확인:
```python
# line 558
graph.add_node("batch_validator", batch_validator_node)        # NO TIMEOUT
# line 559
graph.add_node("script_personalizer", script_personalizer_node)  # NO TIMEOUT
```

build_podcast_graph() 패턴 확인 (lines 498-504):
```python
graph.add_node("batch_validator", lambda s: _with_timeout(batch_validator_node, s, _TIER3_TIMEOUT, "batch_validator"))
graph.add_node("script_personalizer", lambda s: _with_timeout(script_personalizer_node, s, _TIER4_TIMEOUT, "script_personalizer"))
```

- [ ] **Step 2: build_unified_graph()에 timeout 래퍼 적용**

Lines 558-559를 다음으로 교체:
```python
# TIER 3 — Batch Validator (timeout 적용, build_podcast_graph와 동일)
graph.add_node(
    "batch_validator",
    lambda s: _with_timeout(batch_validator_node, s, _TIER3_TIMEOUT, "batch_validator"),
)
# TIER 4 — Script Personalizer (timeout 적용, build_podcast_graph와 동일)
graph.add_node(
    "script_personalizer",
    lambda s: _with_timeout(script_personalizer_node, s, _TIER4_TIMEOUT, "script_personalizer"),
)
```

- [ ] **Step 3: 다른 노드에도 timeout 누락이 없는지 교차 검증**

build_unified_graph()의 모든 `graph.add_node()` 호출을 build_podcast_graph()와 비교하여
timeout 래핑 일관성 확인.

```bash
grep -n "add_node" src/graph/workflow.py
```

> **검증 결과**: batch_validator와 script_personalizer만 누락 확인.
> tier1_podcast_fan_out, tier2_podcast_fan_out은 내부에서 자체 `asyncio.wait_for` timeout 처리.
> crisis_response, async_post는 간단한 동기 작업이거나 자체 timeout 보유.
> intent_classifier_node(line 553)도 timeout 미적용이지만, Haiku 경량 호출이라 위험도 낮음.
> `_TIER0_TIMEOUT`(10s)이 정의되어 있으나 현재 미사용 — 필요시 별도 적용 가능.

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/graph/ -v --tb=short -q 2>&1 | tail -10
pytest tests/ -v --tb=short --ignore=tests/api/e2e/test_e2e_podcast.py -q 2>&1 | tail -5
```
Expected: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/graph/workflow.py
git commit -m "fix: build_unified_graph()에 batch_validator, script_personalizer timeout 래퍼 추가

운영 진입점인 build_unified_graph()에서 TIER 3-4 노드가
timeout 래퍼 없이 등록되어 LLM 무한 대기 가능성 있었음.
build_podcast_graph()와 동일하게 _with_timeout() 적용.

⚠️ Protected File — workflow.py 변경, 3인 합의 리뷰 필요."
```

---

## Task 5: 프롬프트 파일 멀티버전 복원 (content_analyzer, podcast_reasoning)

**항목:** B-1, B-2 | **심각도:** HIGH | **난이도:** 중간

**Files:**
- Replace: `prompts/podcast/content_analyzer.yaml` ← `prompts/podcast/_archive/content_analyzer.yaml`
- Replace: `prompts/podcast/podcast_reasoning.yaml` ← `prompts/podcast/_archive/podcast_reasoning.yaml`

> **핵심 문제**: settings.yaml이 content_analyzer v2.1.0, podcast_reasoning v3.0.0을 핀닝하지만,
> active 프롬프트 파일은 레거시 단일 버전 형식(v1.0.1, v1.0.2)이다.
> PromptLoader는 레거시 형식에서 version 파라미터를 **무시**하므로,
> 최적화된 프롬프트가 아닌 구버전이 사용되고 있다.
>
> `_archive/`에 Round 4 최적화 결과가 포함된 멀티버전 형식 파일이 존재한다.
> archive 파일을 active 파일로 복원하면 settings.yaml 핀닝이 정상 동작한다.

- [ ] **Step 1: archive 파일의 버전 구조 확인**

```bash
# content_analyzer archive — v2.1.0 존재 확인
grep "default_version\|\"2.1.0\"" prompts/podcast/_archive/content_analyzer.yaml | head -5

# podcast_reasoning archive — v3.0.0 존재 확인
grep "default_version\|\"3.0.0\"" prompts/podcast/_archive/podcast_reasoning.yaml | head -5
```
Expected: default_version이 핀닝 버전과 일치

- [ ] **Step 2: archive → active 복원**

```bash
cp prompts/podcast/_archive/content_analyzer.yaml prompts/podcast/content_analyzer.yaml
cp prompts/podcast/_archive/podcast_reasoning.yaml prompts/podcast/podcast_reasoning.yaml
```

- [ ] **Step 3: 복원 후 PromptLoader 동작 검증**

```bash
python3 -c "
from src.agents.shared.prompt_loader import PromptLoader
pl = PromptLoader()

# content_analyzer v2.1.0 로드
result = pl.load('podcast', 'content_analyzer', 'system_prompt', version='2.1.0')
ver = pl.get_version('podcast', 'content_analyzer', version='2.1.0')
print(f'CA version: {ver}, prompt length: {len(result)}')

# podcast_reasoning v3.0.0 로드
result = pl.load_all('podcast', 'podcast_reasoning', version='3.0.0')
ver = pl.get_version('podcast', 'podcast_reasoning', version='3.0.0')
print(f'PR version: {ver}, prompt keys: {list(result.keys())}')

# batch_validator v2.3.0 확인 (기존 정상)
ver = pl.get_version('podcast', 'batch_validator', version='2.3.0')
print(f'BV version: {ver}')
"
```
Expected:
```
CA version: 2.1.0, prompt length: (양수)
PR version: 3.0.0, prompt keys: ['got', 'tot', 'cot']
BV version: 2.3.0
```

- [ ] **Step 4: 전체 테스트**

```bash
pytest tests/ -v --tb=short --ignore=tests/api/e2e/test_e2e_podcast.py -q 2>&1 | tail -5
```
Expected: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add prompts/podcast/content_analyzer.yaml prompts/podcast/podcast_reasoning.yaml
git commit -m "fix: 프롬프트 파일 멀티버전 형식 복원 — Round 4 최적화 결과 적용

content_analyzer.yaml: 레거시 v1.0.1 → 멀티버전 (default v2.1.0)
podcast_reasoning.yaml: 레거시 v1.0.2 → 멀티버전 (default v3.0.0)
settings.yaml 핀닝(CA 2.1.0, PR 3.0.0)이 무시되던 문제 해결.
_archive/에서 Round 4 최적화 결과 포함 파일 복원."
```

---

## Task 6: 대화모드 스키마/주석/문서 잔재 삭제

**항목:** C-1, C-2, C-3, C-4 | **심각도:** HIGH | **난이도:** 낮음

**Files:**
- Modify: `src/api/external_schemas.py`
- Modify: `src/api/contracts.py:23` (주석만 — Protected File)
- Modify: `src/agents/podcast/intent_classifier.py:1` (헤더 주석)
- Modify: `CONTRIBUTING.md:15-18,93`
- Modify: `docs/getting-started/QUICK_START.md` (conversation/ 참조 20건+)
- Modify: `docs/guides/AGENT_DEV_GUIDE.md:195` (conversation/ 참조 1건)

> conversation-removal Phase 4 잔여 작업. 7개 대화 전용 스키마가 external_schemas.py에 남아있고,
> CONTRIBUTING.md, QUICK_START.md, AGENT_DEV_GUIDE.md가 삭제된 src/agents/conversation/ 디렉토리를 참조한다.
>
> ⚠️ `docs/changelog/`, `docs/reports/REFACTORING_LOG.md` 등 **과거 기록 문서**에도 conversation/ 참조가
> 남아있으나, 이들은 히스토리 보존을 위해 **수정하지 않는다**.

- [ ] **Step 1: 참조 없음 최종 확인**

```bash
grep -rn "ConversationRequest\|ConversationResponse\|ConversationContextHint\|ConversationPreferences\|ConversationResponseMeta\|MySQLConversationTurn\|PineconeConversationVector" src/ tests/ --include="*.py" | grep -v "external_schemas.py" | grep -v __pycache__
```
Expected: 0건

- [ ] **Step 2: external_schemas.py에서 대화 전용 스키마 7개 삭제**

삭제 대상 클래스:
1. `ConversationRequest`
2. `ConversationContextHint`
3. `ConversationPreferences`
4. `ConversationResponse`
5. `ConversationResponseMeta`
6. `MySQLConversationTurn`
7. `PineconeConversationVector`

각 클래스의 시작~끝(다음 클래스 정의 전까지) 및 관련 섹션 주석도 함께 삭제.

- [ ] **Step 3: contracts.py 주석 수정**

`src/api/contracts.py:23` — 주석에서 `conversation` 제거:
```python
# 변경 전
type: str  # 데이터 유형 (conversation, emotion_log, memory, visualization, learning 등)
# 변경 후
type: str  # 데이터 유형 (podcast_episode, emotion_log, visualization, learning, content_analysis 등)
```

- [ ] **Step 4: intent_classifier.py 헤더 주석 수정**

`src/agents/podcast/intent_classifier.py:1`:
```python
# 변경 전
# agents/conversation/intent_classifier.py
# 변경 후
# agents/podcast/intent_classifier.py
```

- [ ] **Step 5: CONTRIBUTING.md 대화모드 참조 제거**

`CONTRIBUTING.md` lines 15-18 — 개발자별 담당 영역 표에서 `src/agents/conversation/` 경로를 모두 `src/agents/podcast/` 경로로 수정. 존재하지 않는 에이전트(synthesis, context, validator, telemetry) 제거:

```markdown
# 변경 전 (lines 15-18)
| 개발자1 | `src/agents/conversation/{intent_classifier,knowledge,synthesis,personalization}.py`, `src/agents/podcast/{script_generator,script_personalizer}.py` |
| 개발자2 | `src/agents/conversation/{safety,memory,visualization,emotion}.py`, `src/agents/podcast/{episode_memory,visualization}.py` |
| 개발자3 | `src/agents/conversation/{reasoning,context,validator,learning}.py`, `src/agents/podcast/{podcast_reasoning,content_analyzer,batch_validator}.py` |
| 미정 | `src/agents/conversation/telemetry.py` (전체 에이전트 완료 후 예정) |

# 변경 후 — CLAUDE.md 에이전트 배정표와 일치하도록 수정
| 개발자1 | `src/agents/podcast/{intent_classifier,knowledge,script_generator,script_personalizer}.py` |
| 개발자2 | `src/agents/podcast/{safety,emotion,visualization,episode_memory}.py` |
| 개발자3 | `src/agents/podcast/{podcast_reasoning,content_analyzer,batch_validator,learning}.py` |
```

Line 93 — 테스트 경로에서 conversation 제거:
```markdown
# 변경 전
- 테스트 파일 위치: `tests/agents/{conversation,podcast}/test_{agent_name}.py`
# 변경 후
- 테스트 파일 위치: `tests/agents/podcast/test_{agent_name}.py`
```

- [ ] **Step 6: QUICK_START.md 대화모드 참조 갱신**

`docs/getting-started/QUICK_START.md`에서 `src/agents/conversation/` 경로를 `src/agents/podcast/`로 교체.
존재하지 않는 에이전트 이름(synthesis, context, validator 등)은 현재 에이전트 목록에 맞게 수정.
약 20건 이상의 참조가 있으므로 파일 전체를 확인하며 수정한다.

- [ ] **Step 7: AGENT_DEV_GUIDE.md 대화모드 참조 갱신**

`docs/guides/AGENT_DEV_GUIDE.md:195` 부근의 conversation/ 참조를 podcast/로 수정.

> ⚠️ changelog, REFACTORING_LOG.md 등 과거 기록 문서는 히스토리 보존을 위해 수정하지 않는다.

- [ ] **Step 8: 테스트 실행**

```bash
pytest tests/api/ -v --tb=short -q 2>&1 | tail -5
```
Expected: 전체 통과

- [ ] **Step 9: 잔재 검색**

```bash
grep -rn "Conversation" src/api/external_schemas.py
grep -rn "agents/conversation" CONTRIBUTING.md docs/getting-started/QUICK_START.md docs/guides/AGENT_DEV_GUIDE.md
```
Expected: 0건

- [ ] **Step 10: 커밋**

```bash
git add src/api/external_schemas.py src/api/contracts.py src/agents/podcast/intent_classifier.py CONTRIBUTING.md docs/getting-started/QUICK_START.md docs/guides/AGENT_DEV_GUIDE.md
git commit -m "refactor: 대화모드 잔재 전면 삭제 — Phase 4 완료

- external_schemas.py: Conversation* 스키마 7개 삭제 (미참조 확인)
- contracts.py: 주석에서 conversation 타입 제거
- intent_classifier.py: 헤더 경로 agents/conversation → agents/podcast
- CONTRIBUTING.md: 삭제된 src/agents/conversation/ 참조 제거, 에이전트 배정 갱신
- QUICK_START.md: conversation/ 경로 20건+ 갱신
- AGENT_DEV_GUIDE.md: conversation/ 경로 수정"
```

---

## Task 7: settings.yaml 미사용 에이전트 설정 제거

**항목:** D-1, D-2 | **심각도:** MEDIUM | **난이도:** 낮음

**Files:**
- Modify: `config/settings.yaml:133-135,155-157`

> `visualization_podcast`와 `telemetry` 에이전트 설정이 settings.yaml에 존재하지만
> 대응 파일/클래스/워크플로우 노드가 없다.

- [ ] **Step 1: visualization_podcast 설정 삭제**

`config/settings.yaml`에서 `visualization_podcast` 블록(lines 133-135) 삭제:
```yaml
# 삭제
  visualization_podcast:
    model: sonnet
    max_tokens: 2048
```

- [ ] **Step 2: telemetry 에이전트 설정 삭제**

`config/settings.yaml`에서 `telemetry` 블록(lines 155-157) 삭제:
```yaml
# 삭제
  telemetry:
    model: haiku
    max_tokens: 1024
```

- [ ] **Step 3: features 섹션의 telemetry 제거**

`config/settings.yaml` features 섹션에서 `telemetry: true` 라인 삭제.

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/ -v --tb=short --ignore=tests/api/e2e/test_e2e_podcast.py -q 2>&1 | tail -5
```
Expected: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add config/settings.yaml
git commit -m "refactor: settings.yaml 미사용 에이전트 설정 제거

visualization_podcast (visualization과 중복), telemetry (대화모드 잔재) 설정 삭제.
features.telemetry도 제거. 대응 파일/클래스/노드가 존재하지 않음 확인."
```

---

## Task 8: deep_personalization settings 연동

**항목:** E-1 | **심각도:** MEDIUM | **난이도:** 낮음

**Files:**
- Modify: `src/agents/podcast/script_personalizer.py` (ScriptPersonalizerAgent.__init__ 또는 workflow.py 노드 함수)

> ⚠️ **검증 결과**: 계획 초안에서는 `create_script_personalizer_node()` (lines 641-658)을 수정 대상으로
> 지정했으나, 이 팩토리 함수는 **운영에서 사용되지 않는다**.
>
> 실제 운영 경로: `workflow.py` line 179-182의 `script_personalizer_node()` → `ScriptPersonalizerAgent()` 직접 생성.
> `create_script_personalizer_node()`는 워크플로우에서 호출하지 않는 dead code이다.
>
> **올바른 수정 경로 2가지** (택 1):
> - **방법 A**: `ScriptPersonalizerAgent.__init__()`에서 settings.yaml 읽기 (에이전트 자체가 설정 인지)
> - **방법 B**: `workflow.py`의 `script_personalizer_node()` 내부에서 설정을 읽어 인스턴스 생성 시 전달
>   (Protected File이므로 3인 합의 필요)
>
> **권장: 방법 A** — Protected File 수정 불필요.

- [ ] **Step 1: 실제 운영 경로 확인**

```bash
# workflow.py에서 script_personalizer가 어떻게 생성되는지 확인
grep -n "script_personalizer" src/graph/workflow.py | head -10

# create_script_personalizer_node가 어디서 호출되는지 확인
grep -rn "create_script_personalizer_node" src/ tests/ --include="*.py"
```
Expected: `create_script_personalizer_node()` 호출처 0건 (dead code 확인)

- [ ] **Step 2: ScriptPersonalizerAgent.__init__()에서 settings 연동 (방법 A)**

`src/agents/podcast/script_personalizer.py`의 `__init__()`:

```python
# 변경 전 (line ~50)
def __init__(self, ..., enable_deep_personalization: bool = False):
    ...
    self.enable_deep_personalization = enable_deep_personalization

# 변경 후
def __init__(self, ..., enable_deep_personalization: bool | None = None):
    ...
    if enable_deep_personalization is None:
        from config.loader import get_settings
        agent_cfg = get_settings().get_agent_config("script_personalizer")
        enable_deep_personalization = agent_cfg.get("deep_personalization", False)
    self.enable_deep_personalization = enable_deep_personalization
```

- [ ] **Step 3: create_script_personalizer_node()의 TODO 주석 갱신**

`create_script_personalizer_node()` (lines 641-658)의 TODO를 완료 주석으로 변경:
```python
# NOTE: 이 팩토리 함수는 현재 운영에서 미사용.
# deep_personalization 설정은 ScriptPersonalizerAgent.__init__()에서 직접 읽음.
```

- [ ] **Step 4: 테스트 실행**

```bash
pytest tests/agents/podcast/test_script_personalizer.py -v --tb=short
```
Expected: 전체 통과

- [ ] **Step 5: 커밋**

```bash
git add src/agents/podcast/script_personalizer.py
git commit -m "feat: deep_personalization 설정을 settings.yaml에서 읽도록 연동

ScriptPersonalizerAgent.__init__()에서 settings.yaml의
agents.script_personalizer.deep_personalization 값을 읽도록 수정.
(create_script_personalizer_node()는 운영 미사용 — TODO를 갱신)"
```

---

## Task 9: deploy.yml printf 전환

**항목:** F-1 | **심각도:** MEDIUM | **난이도:** 낮음

**Files:**
- Modify: `.github/workflows/deploy.yml:89-102`

> GitHub Secrets 값에 셸 특수문자가 포함될 경우 `echo`가 해석할 수 있다.
> `printf '%s\n'`으로 전환한다. (remaining-issues D-3)

- [ ] **Step 1: 현재 echo 라인 확인**

`.github/workflows/deploy.yml`의 SSM parameters 내 `.env` 기록 부분 확인.

- [ ] **Step 2: echo → printf 전환**

각 `.env` 기록 라인을 전환:

```bash
# 변경 전 (예시)
"echo '"'"'LANGCHAIN_TRACING_V2=${{ secrets.LANGCHAIN_TRACING_V2 }}'"'"' > .env",

# 변경 후
"printf '%s\\n' 'LANGCHAIN_TRACING_V2=${{ secrets.LANGCHAIN_TRACING_V2 }}' > .env",
```

> 주의: SSM command JSON 내부이므로 이스케이프 형식(`\\n`)에 주의.
> 첫 번째 라인만 `>` (덮어쓰기), 나머지는 `>>` (추가).
> `PROMPT_DIR=/app/prompts`처럼 시크릿이 아닌 고정값은 echo 유지 가능.

- [ ] **Step 3: YAML 문법 검증**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"
```
Expected: 에러 없음

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/deploy.yml
git commit -m "fix: deploy.yml .env 기록 시 셸 해석 방지

echo → printf '%s\n' 전환으로 GitHub Secrets 값에
셸 특수문자가 포함되어도 원본 그대로 .env에 기록.
remaining-issues D-3 해결."
```

---

## Task 10: 미사용 features/환경변수 정리

**항목:** D-3, D-4 | **심각도:** LOW | **난이도:** 낮음

**Files:**
- Modify: `config/settings.yaml:211-217`
- Modify: `.env.example:57-61`

- [ ] **Step 1: features 섹션에 미사용 주석 추가**

`config/settings.yaml` features 섹션:
```yaml
# 변경 전
features:
  podcast_mode: true
  visualization: true
  telemetry: true     # Task 7에서 이미 제거
  learning: true

# 변경 후
# [미사용] Feature flags — 코드에서 읽지 않음.
# 향후 에이전트별 활성화/비활성화 제어 시 config/loader.py에 property 추가 필요.
# features:
#   podcast_mode: true
#   visualization: true
#   learning: true
```

- [ ] **Step 2: .env.example 미사용 변수 제거 또는 주석 처리**

`.env.example`에서 `ENABLE_*` 변수 4개를 주석 처리:
```bash
# [미사용] Feature flags — 코드에서 참조하지 않음. 향후 구현 시 활성화.
# ENABLE_PODCAST_MODE=true
# ENABLE_VISUALIZATION=true
# ENABLE_TELEMETRY=true
# ENABLE_LEARNING=true
```

- [ ] **Step 3: 커밋**

```bash
git add config/settings.yaml .env.example
git commit -m "refactor: 미사용 feature flags 주석 처리

settings.yaml features 섹션과 .env.example의 ENABLE_* 변수는
코드에서 읽지 않으므로 주석 처리. 향후 구현 시 활성화."
```

---

## Task 11: Dead code 정리 (Intent Classifier / Batch Validator next_step)

**항목:** I-2, I-3 | **심각도:** MEDIUM/LOW | **난이도:** 낮음

**Files:**
- Modify: `src/agents/podcast/intent_classifier.py:118,154,176`
- Modify: `src/agents/podcast/batch_validator.py:74,104,128,139`

> **Intent Classifier**: `next_step`에 `"safety_intervention"`, `"process_normal"` 값을 설정하지만,
> `route_after_tier0()`는 이 값을 읽지 않고 항상 `"tier1_podcast"`를 반환한다.
> next_step 값이 라우팅에 전혀 영향을 주지 않는 dead code.
>
> **Batch Validator**: `next_step`에 `"retry_script"`, `"script_personalizer"` 등을 설정하지만,
> `route_after_tier3_podcast()` 라우터가 `validation_result.verdict` 필드로 직접 판단하여 next_step 무시.
> (단, `crisis_response` 값은 라우터가 먼저 확인 — 이것은 tier1_podcast_fan_out이 설정하는 값)
>
> ⚠️ **사이드이펙트 주의**: `test_batch_validator.py`에 next_step 값을 assert하는 테스트가 **6건** 있음
> (lines 96, 137, 166, 199, 259, 293). **주석만 추가**하고 값 자체는 절대 제거하지 않는다.
>
> **방침**: 삭제보다는 주석으로 dead code 상태를 명시한다. 향후 라우팅 고도화 시 재활용 가능.

- [ ] **Step 1: Intent Classifier — next_step 할당에 주석 추가**

`src/agents/podcast/intent_classifier.py`에서 next_step 관련 코드에 주석 추가:

Line 118 부근:
```python
# NOTE(dead-code): next_step은 현재 route_after_tier0()에서 참조하지 않음.
# 라우터가 항상 "tier1_podcast"를 반환. 향후 라우팅 분기 확장 시 활용 가능.
"next_step": "safety_intervention",
```

Line 154 부근:
```python
# NOTE(dead-code): route_after_tier0()가 next_step을 읽지 않음 — 항상 tier1_podcast.
next_step = "safety_intervention" if risk_level > 0 else "process_normal"
```

- [ ] **Step 2: Batch Validator — next_step 할당에 주석 추가**

`src/agents/podcast/batch_validator.py`에서 next_step 관련 코드에 주석 추가:

Lines 74, 104, 128, 139 부근:
```python
# NOTE(dead-code): next_step은 현재 route_after_tier3_podcast()에서 참조하지 않음.
# 라우터가 validation_result.verdict 필드를 직접 읽어 판단.
"next_step": "retry_script",
```

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/agents/podcast/test_intent_classifier.py tests/agents/podcast/test_batch_validator.py -v --tb=short
```
Expected: 전체 통과

- [ ] **Step 4: 커밋**

```bash
git add src/agents/podcast/intent_classifier.py src/agents/podcast/batch_validator.py
git commit -m "docs: intent_classifier, batch_validator의 dead code next_step에 주석 추가

- intent_classifier: next_step ('safety_intervention'/'process_normal')이
  route_after_tier0()에서 참조되지 않음을 명시
- batch_validator: next_step ('retry_script'/'script_personalizer')이
  route_after_tier3_podcast()에서 참조되지 않음을 명시
향후 라우팅 고도화 시 재활용 가능하므로 삭제하지 않고 주석 처리."
```

---

## Task 12: test_episode_memory.py 테스트 복원

**항목:** A-5 | **심각도:** MEDIUM | **난이도:** 중간

**Files:**
- Create: `tests/agents/podcast/test_episode_memory.py`

> episode_memory.py의 `.py` 테스트 소스가 누락되어 `.pyc` 캐시만 존재.
> 다른 에이전트 테스트(`test_safety.py`, `test_emotion.py` 등)의 패턴을 참조하여 기본 테스트 복원.

- [ ] **Step 1: 기존 에이전트 테스트 패턴 확인**

```bash
head -50 tests/agents/podcast/test_safety.py
```
다른 에이전트 테스트의 기본 구조(import, fixture, 기본 테스트 케이스) 확인.

- [ ] **Step 2: test_episode_memory.py 작성**

`tests/agents/podcast/test_episode_memory.py` 생성:

기본 테스트 항목:
1. `EpisodeMemoryAgent` 인스턴스 생성 가능 여부
2. `episode_memory_node()` 함수 호출 가능 여부 (요청별 인스턴스 생성 확인)
3. 빈/최소 AgentState로 호출 시 에러 없이 결과 반환
4. 반환 결과에 `memory_results` 키 포함 여부

> **Mock 대상** (검증 결과 확인):
> - `httpx.AsyncClient.post` — KT Cloud 임베딩 API 호출 (Pinecone/Neo4j 아님)
> - 로컬 파일 I/O — `data/cache/mock_db.json` 읽기/쓰기 (tmp_path 활용 권장)
> - `call_llm_json` — BaseMemoryAgent 폴백 LLM 호출
> - `get_prompt` — 프롬프트 로딩 (다른 테스트와 동일 패턴)

- [ ] **Step 3: 테스트 실행**

```bash
pytest tests/agents/podcast/test_episode_memory.py -v --tb=short
```
Expected: 전체 통과

- [ ] **Step 4: 커밋**

```bash
git add tests/agents/podcast/test_episode_memory.py
git commit -m "test: episode_memory 에이전트 기본 테스트 복원

.py 소스 파일이 누락되어 .pyc 캐시만 존재하던 상태.
기본 인스턴스 생성, 노드 함수 호출, 반환값 검증 테스트 추가."
```

---

## Task 13: 린팅 컴플라이언스 수정

**항목:** J-1~J-4 | **심각도:** HIGH (CI 차단) | **난이도:** 높음

**Files:**
- Modify: `src/**/*.py`, `tests/**/*.py` (다수)

> CI(`ci.yml`)의 lint 잡이 black/ruff/isort/mypy 4개를 모두 검사한다.
> 현재 68파일 black, 168건 ruff, 61건 mypy 위반으로 **CI가 lint 실패 상태**.
> (isort는 현재 시점에서 0건 — 이전 측정과 다름. 다른 Task 수정 후 재확인 필요.)
>
> **전략**: 자동 수정 도구를 최대한 활용한 후 수동 수정 진행.
> 1단계: isort (현재 0건이지만 다른 Task 후 발생 가능) → 2단계: black → 3단계: ruff --fix → 4단계: ruff 수동 → 5단계: mypy

- [ ] **Step 1: isort 확인 및 자동 수정 (현재 0건이지만 다른 Task 후 변경될 수 있음)**

```bash
python3 -m isort --check-only src/ tests/ --profile black
# 위반 있으면:
python3 -m isort src/ tests/ --profile black
```
Expected: 현재 0건, Task 1~12 수정 후 재확인

- [ ] **Step 2: black 자동 포맷팅**

```bash
python3 -m black src/ tests/
```
Expected: 68파일 리포맷

- [ ] **Step 3: ruff 자동 수정**

```bash
python3 -m ruff check --fix src/ tests/
```
Expected: 90건 자동 수정

- [ ] **Step 4: ruff 잔여 에러 수동 수정**

```bash
python3 -m ruff check src/ tests/ 2>&1 | head -80
```
남은 ~78건 수동 확인·수정. 주요 카테고리별 처리:
- 미사용 import (`F401`) → 삭제
- 미사용 변수 (`F841`) → 삭제 또는 `_` 접두사
- 타입 에러 → 수정

- [ ] **Step 5: mypy 에러 수정**

```bash
python3 -m mypy src/ --ignore-missing-imports 2>&1 | head -80
```
61건 / 17파일 수정. 주요 hotspot:
- `knowledge.py` (7건): 타입 불일치, 반환 타입 누락
- `intent_classifier.py` (6건): None 할당, 누락 어노테이션
- `episode_memory.py` (5건): implicit Optional, 누락 어노테이션
- `routes/*.py` (8건): 반환 타입 누락

- [ ] **Step 6: 전체 린트 검증**

```bash
python3 -m black --check src/ tests/
python3 -m ruff check src/ tests/
python3 -m isort --check-only src/ tests/
python3 -m mypy src/ --ignore-missing-imports
```
Expected: 4개 전부 에러 0건

- [ ] **Step 7: 전체 테스트 확인**

```bash
pytest tests/ -v --tb=short -q 2>&1 | tail -10
```
Expected: 린트 수정이 동작을 변경하지 않았는지 확인

- [ ] **Step 8: 커밋**

```bash
git add -u src/ tests/
git commit -m "style: 린팅 컴플라이언스 전면 수정

- isort: import 정렬 (22파일)
- black: 코드 포맷팅 (68파일)
- ruff: 린트 에러 수정 (168건)
- mypy: 타입 에러 수정 (61건/17파일)
CI lint 잡 통과를 위한 전면 정리."
```

---

## Task 14: CI 파이프라인 검증

**항목:** 전체 | **심각도:** HIGH | **난이도:** 낮음

> Task 1~13 완료 후 CI 파이프라인이 정상 작동하는지 종합 검증.

- [ ] **Step 1: 로컬 CI 시뮬레이션**

```bash
# 테스트 (ci.yml test job과 동일)
pytest tests/ -v --cov=src --cov-report=xml 2>&1 | tail -20

# 린트 (ci.yml lint job과 동일)
python3 -m black --check .
python3 -m ruff check .
python3 -m isort --check-only .
python3 -m mypy src/ --ignore-missing-imports
```
Expected: 전부 통과

- [ ] **Step 2: Docker 빌드 테스트**

```bash
docker build -t mindlog-ai:test . 2>&1 | tail -10
```
Expected: 빌드 성공

- [ ] **Step 3: 결과 정리**

| 검증 항목 | 결과 |
|----------|------|
| pytest 수집 에러 | 0건 |
| pytest 실패 | 0건 (backend connectivity 제외) |
| black | 통과 |
| ruff | 통과 |
| isort | 통과 |
| mypy | 통과 |
| Docker build | 성공 |

---

## Task 15: Bedrock EC2 테스트 + settings 반영 (인프라 작업)

**항목:** G-1, G-2 | **심각도:** MEDIUM | **난이도:** 중간

> ⚠️ EC2 인스턴스 접근 필요. 이 Task는 로컬에서 실행 불가.

**Files:**
- 실행: `dev/live_tests/run_bedrock_model_test.py`
- 결과: `dev/live_tests/results/bedrock_model_test/`
- Modify (Phase 3 후): `config/settings.yaml`

- [ ] **Step 1: EC2 접속 및 코드 동기화**

```bash
cd /home/ubuntu/mind-log && git pull origin develop
```

- [ ] **Step 2: Phase 0 — 모델 연결 확인**

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 0
```

- [ ] **Step 3: Phase 1 — 전체 벤치마크 (171 테스트)**

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 5
```

- [ ] **Step 4: Phase 2 — 점수 산출**

```bash
python3 -m dev.live_tests.scoring --input-dir dev/live_tests/results/bedrock_model_test/
```

- [ ] **Step 5: Phase 3 — 최적 모델 검증 (30 테스트)**

```bash
python3 -m dev.live_tests.run_bedrock_model_test --phase 3 \
  --optimal-config dev/live_tests/results/bedrock_model_test/optimal_config.json
```

- [ ] **Step 6: 결과 커밋 + settings.yaml 반영**

Phase 3 결과(`optimal_config.json`)의 에이전트별 최적 모델 ID를
`config/settings.yaml`의 에이전트별 `model_id`에 반영.

```bash
git add dev/live_tests/results/bedrock_model_test/ config/settings.yaml
git commit -m "feat: Bedrock 모델 벤치마크 Phase 0-3 결과 + 최적 모델 적용

EC2에서 실행한 모델 최적화 벤치마크 결과 반영.
에이전트별 최적 Bedrock 모델 ID를 settings.yaml에 적용."
```

---

## 완료 기준 체크리스트

### 필수 (전부 통과해야 완료)

| # | 기준 | 검증 | Task |
|---|------|------|------|
| 1 | pytest 수집 에러 0건 | `pytest tests/ --co -q` → 에러 없음 | T1 |
| 2 | 전체 테스트 통과 | `pytest tests/ -v` → 0 failed (backend connectivity 제외) | T1-T8, T12 |
| 3 | 싱글톤 참조 잔재 0건 | `grep -rn "safety_agent\|emotion_agent\|content_analyzer_agent\|podcast_reasoning_agent\|visualization_agent\|episode_memory_agent" src/ tests/ dev/ --include="*.py"` → 0건 | T1-T3 |
| 4 | CA v2.1.0 로드 성공 | PromptLoader 검증 스크립트 | T5 |
| 5 | PR v3.0.0 로드 성공 | PromptLoader 검증 스크립트 | T5 |
| 6 | Conversation 스키마 0건 | `grep "class.*Conversation" src/api/external_schemas.py` → 0건 | T6 |
| 7 | CONTRIBUTING.md conversation/ 참조 0건 | `grep "agents/conversation" CONTRIBUTING.md` → 0건 | T6 |
| 8 | 미사용 에이전트 설정 제거 | `grep "visualization_podcast\|telemetry:" config/settings.yaml` → 0건 | T7 |
| 9 | deep_personalization settings 연동 | `grep "TODO.*deep_personal" src/agents/podcast/script_personalizer.py` → 0건 | T8 |
| 10 | deploy.yml printf 사용 | `grep "printf.*\.env" .github/workflows/deploy.yml` → 해당 라인 존재 | T9 |
| 11 | build_unified_graph timeout 적용 | `grep "_with_timeout.*batch_validator\|_with_timeout.*script_personalizer" src/graph/workflow.py` → build_unified_graph 내 2건 | T4 |
| 12 | CI lint 4종 통과 | `black --check . && ruff check . && isort --check-only . && mypy src/` → 전부 0 에러 | T13 |
| 13 | episode_memory 테스트 존재 | `test -f tests/agents/podcast/test_episode_memory.py` → 존재 | T12 |

---

## 의존 관계 그래프

```
T1 (e2e import) ──┐
T2 (dev/ 파일)  ──┤
T3 (singleton)  ──┼─→ T14 (CI 검증)
T4 (timeout) ★  ──┤
T5 (prompts)   ──┤
T6 (conversation)─┤
T7 (settings)  ──┤
T8 (deep_psnl) ──┤
T9 (deploy.yml)──┤
T10 (features) ──┤
T11 (dead code)──┤
T12 (test_em)  ──┤
T13 (linting)  ──┘
                   ↓
              T14 (CI 전체 검증)
                   ↓
              T15 (Bedrock EC2) ← 별도 인프라 작업
```

- **T1~T13**: 상호 독립. 병렬 실행 가능 (단, T13은 T1~T12 이후 실행 권장 — 린트 자동수정이 다른 Task의 변경과 충돌할 수 있음)
- **T14**: T1~T13 전부 완료 후 실행
- **T15**: EC2 접근 필요, 다른 Task와 독립

---

*작성일: 2026-04-01*
*최종 갱신: 2026-04-02 (6차 정밀 검증 — 6건 오류 수정)*
*점검 범위: 기존 계획서 7개 + 코드 전수 조사 (테스트 실행, import 검증, 설정 교차 검증, TODO 전수 조사, 워크플로우 교차 검증, 린팅 전수 점검, dead code 추적, 문서 정합성)*

### 검증 이력

| 일자 | 라운드 | 내용 |
|------|--------|------|
| 04-01 | 초기 점검 | 기존 7개 계획서 진행 상황 확인, 코드 전수 검색 |
| 04-01 | 심층 조사 | 프롬프트 버전 실행 검증, import 에러 확인, TODO 전수 |
| 04-01 | 추가 1차 | 워크플로우 교차 검증, CONTRIBUTING.md 정합성 |
| 04-01 | 추가 2차 | 린팅 전수 점검, CI 파이프라인 상태 확인 |
| 04-01 | 추가 3차 | Dead code 추적, SSE 에러 경로 확인 |
| 04-02 | **정밀 검증** | **전 Task 코드 대조 재검증 — 6건 오류 발견·수정** |

### 정밀 검증에서 수정된 6건

| # | Task | 수정 내용 |
|---|------|----------|
| 1 | T1 | `_force_cheap_model()`이 dead code임을 명시. 워크플로우가 요청별 새 인스턴스를 생성하므로 이 함수의 인스턴스 mutate가 무의미 |
| 2 | T2 | `mode="conversation"` 라인 번호 13→11 수정 |
| 3 | T6 | `QUICK_START.md`(20건+), `AGENT_DEV_GUIDE.md`(1건) conversation/ 참조 추가. 과거 기록 문서(changelog 등) 수정 제외 명시 |
| 4 | T8 | **수정 대상 오류**: `create_script_personalizer_node()`가 운영 미사용 → 실제 경로인 `ScriptPersonalizerAgent.__init__()` 수정으로 변경 |
| 5 | T12 | mock 대상을 Pinecone/Neo4j → httpx + 로컬 JSON(data/cache/mock_db.json)으로 수정 |
| 6 | T13 | isort 위반 건수 22→0으로 수정 (현재 시점 재측정 결과) |

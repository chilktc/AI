# Mind-Log 프로젝트 종합 점검 및 코드 품질 개선 계획

**작성일**: 2026-03-31
**대상 브랜치**: develop
**범위**: 코드 품질, 코딩 컨벤션, 주석/독스트링, 문서 통일성, 폴더 구조, 인젝션 방어, Circuit Breaker, 팟캐스트 SSE, PII 정제

---

## Context

Mind-Log AI 서버의 런칭 전 종합 코드 품질 점검이다. 3개 탐색 에이전트가 코드 품질, 프로젝트 구조/문서, 업계 모범 사례를 기준으로 전수 분석한 결과를 바탕으로 한다.

**사용자 요청 7가지 항목:**
1. 불필요한 코드 제거
2. 누락된 기능 보완 (기존 범위 내)
3. 통일되지 않은 코딩 컨벤션 정리
4. 기능 설명 주석 누락 보완
5. 로직 설명 주석 누락 보완
6. 프로젝트 문서 통일성 + 불필요한 내용 정리
7. 폴더 구조 및 파일 위치 정리

**제약 조건:**
- Protected Files (`agent_state.py`, `message.py`, `contracts.py`, `workflow.py`): 3인 합의 필요
- Shared Infrastructure (`base_agent.py`, `llm_client.py`, `prompt_loader.py`, `loader.py`): public 메서드 시그니처 변경 금지
- 각 Phase는 독립적으로 커밋/테스트 가능해야 함

---

## 발견 사항 종합

### A. 코딩 컨벤션 불일치

| 항목 | 현상 | 위치 | 건수 |
|------|------|------|------|
| 타입 힌트 | 구식 `Dict, List, Optional` vs 현대식 `dict, list` 혼용 | script_generator, knowledge, intent_classifier, script_personalizer, schemas.py | 5개 파일 |
| 로깅 포맷 | f-string(`self.logger.info(f"...")`) vs %-포맷(`logger.info("[%s]", ...)`) | 4개 파일에 f-string 22곳, %-포맷 24곳 + module logger 53곳 | 75+곳 |
| print 문 | `traceback.print_exc()` / `print()` 사용 | podcasts.py:300, callbacks.py:13-14 (docstring 예시) | 1곳 실코드 |
| 독스트링 | Google-style 준수(base_agent) vs 자유형(script_generator 등) 혼재 | 전체 에이전트 파일 | 다수 |

### B. 불필요한 코드 / 미사용 항목

| 항목 | 위치 | 설명 |
|------|------|------|
| 미사용 설정 `features` 섹션 | `settings.yaml:237-241` | 코드에서 한 번도 읽지 않음 |
| 미사용 설정 `databases` 섹션 | `settings.yaml:264-272` | 최근 추가했으나 읽는 코드 없음 |
| 미사용 변수 `start_time` | `script_personalizer.py:75` | 할당 후 미사용 |
| 중복 할당 `visual_data_raw` | `podcasts.py:162, 212` | 동일 변수를 두 번 할당 |
| 프롬프트 아카이브 | `prompts/podcast/_archive/` | 3개 구버전 YAML — 의도 미문서화 |

### C. 주석/독스트링 누락

| 위치 | 복잡도 | 누락 내용 |
|------|--------|---------|
| `base_agent.py:192-223` | 높음 | `_resolve_ab_variant()` — MD5 해시 기반 A/B 세션 배정 알고리즘 |
| `llm_client.py:389-481` | 높음 | `_generate_bedrock()` — Retry + Semaphore + 캐싱 복합 로직 |
| `workflow.py:211-255` | 높음 | `run_with_cancel()` — asyncio.Event 기반 취소 메커니즘 (CRISIS 선점) |
| `callbacks.py:52-56` | 중간 | `_MODEL_COSTS` — 가격 기준일(2026-02) 및 갱신 주기 미기재 |
| `script_generator.py:22` | 낮음 | `WORDS_PER_MINUTE = 150` — 한국어 기준 근거 미설명 |

### D. 에러 처리 / 방어 코드

| 위치 | 문제 | 심각도 |
|------|------|--------|
| `emotion.py:93` | `except KeyError` — 실제로는 JSON 파싱 실패 대응이므로 Exception이 적절 | 중간 |
| `llm_client.py:387` | `response.content[0].text` — content 빈 리스트 시 IndexError | 높음 |
| `podcasts.py:300` | `traceback.print_exc()` — logger로 대체 필요 | 중간 |
| bare except 9곳 | base_agent 4곳, podcasts 3곳, batch_validator 1곳, workflow 1곳 | 중간 |

### E. 폴더 구조 / 파일 위치

| 문제 | 현재 위치 | 올바른 위치 |
|------|---------|-----------|
| 루트 테스트 파일 | `/test_e2e_podcast.py` | `/tests/api/e2e/test_e2e_podcast.py` |
| 루트 테스트 파일 | `/test_safety.py` | `/tests/agents/podcast/test_safety.py` |
| 발표 자료 | `/발표_자료/` (5개) | `.gitignore` 추가 또는 `docs/reports/presentations/`로 이동 |

### F. 문서 불일치

| 문제 | 위치 |
|------|------|
| 깨진 링크: `docs/architecture/PROJECT_STRUCTURE.md` | `README.md:99` |
| 깨진 링크: `docs/guides/GIT_WORKFLOW.md` | `README.md:100`, `CONTRIBUTING.md:86,120` |
| `features` 설정 문서화 없음 | `settings.yaml:237-241` |
| TODO(backend) 14건 — 확인/갱신 필요 | `src/api/backend_resources.py` |

### G. 누락된 기능 (기존 범위 내)

| 항목 | 위치 | 설명 |
|------|------|------|
| TIER 2-4 타임아웃 래퍼 미적용 | `workflow.py:100-104, 647-710` | 타임아웃 상수는 정의됨, 래퍼만 미적용 |
| `databases` 설정 읽기 코드 없음 | `config/loader.py` | 설정만 있고 property 없음 |

### G-2. 멀티에이전트 시스템 갭 분석 (웹서치 기반)

| 항목 | 현상 | 심각도 | 이번 계획 |
|------|------|--------|---------|
| 출력 PII 정제 | LLM 출력의 PII(전화/이메일/주민번호) 미마스킹 — 멘탈케어 데이터 민감 | CRITICAL | **Phase 9** |
| 체크포인트 영속화 | `compile_graph(checkpointer=...)` 파라미터 존재하나 미전달 | HIGH | **추후** (별도 DB 추가 불가) |
| 토큰 예산 관리 | 요청당 비용 제한 없음, 입력 토큰 추정 없음 | MEDIUM | **추후** |
| CRISIS Human-in-the-Loop | CRISIS 응답이 AI → 사용자 직접 전송 | — | **불필요** (고정 메시지 유지) |
| 대화모드 Validator | `validator_node`가 STUB | MEDIUM | 개발자3 영역 (범위 밖) |

### H. 업계 모범 사례 대비 — 보안/안정성/기능 갭

| 항목 | 현상 | 심각도 | 구현 결정 |
|------|------|--------|---------|
| 프롬프트 인젝션 방어 | 사용자 입력이 LLM에 직접 전달 | HIGH | **Phase 6: 입력 전처리 필터** |
| Circuit Breaker | LLM 장애 시 cascading failure | MEDIUM | **Phase 7: 수동 구현** (의존성 최소화) |
| HTTP 스트리밍 (SSE) | astream 인프라 존재하나 미노출 | MEDIUM | **Phase 8: 팟캐스트 SSE** |
| 출력 PII 정제 | LLM 출력에 PII(이름/번호/주소) 미정제 — 멘탈케어 데이터 민감 | CRITICAL | **Phase 9: 출력 정제 레이어** |
| API 인증/인가 | 인증 없이 모든 엔드포인트 접근 가능 | CRITICAL | **추후**: 백엔드 합의 후 진행 |
| Secrets Manager | .env 파일로만 시크릿 관리 | — | **불필요**: CD 파이프라인(GitHub Secrets→SSM)으로 충분 |
| 체크포인트 영속화 | compile_graph에 checkpointer 파라미터 존재하나 미전달 | HIGH | **추후**: 별도 DB 추가 불가, 백엔드 협의 필요 |
| 토큰 예산 관리 | 요청당 비용 제한 없음, 입력 토큰 사전 추정 없음 | MEDIUM | **추후**: 요청별 예산 가드레일 |
| CRISIS Human-in-the-Loop | CRISIS 응답이 사람 검토 없이 즉시 전송 | — | **불필요**: 현재 고정 메시지 출력 유지 |
| Rate Limiting | 요청 수 제한 없음 | MEDIUM | **추후**: API Gateway 레벨 (인프라팀) |
| DB 마이그레이션 | 마이그레이션 전략 없음 | LOW | **보류**: AI 서버는 DB 직접 미사용 |

---

## Phase 1 — 코딩 컨벤션 통일 + 폴더 정리 (무위험)

> 로직 변경 없이 포맷·위치만 수정. 테스트 결과에 영향 없음.

### 1-1. 타입 힌트 현대화 (5개 파일)

`from typing import Dict, List, Optional` → `dict, list, | None` (Python 3.10+)

| 파일 | 현재 | 수정 |
|------|------|------|
| `src/agents/podcast/script_generator.py:10` | `from typing import Any, Dict, List` | `from typing import Any` |
| `src/agents/conversation/knowledge.py:11` | `from typing import Any, Dict, List, Optional` | `from typing import Any` |
| `src/agents/conversation/intent_classifier.py:15` | `from typing import Any, Dict, List, Optional` | `from typing import Any` |
| `src/agents/podcast/script_personalizer.py:14` | `from typing import Any, Dict, List, Optional` | `from typing import Any` |
| `src/models/schemas.py:9` | `from typing import Any, Dict, List, Optional` | `from typing import Any` |

각 파일 본문의 `Dict[str, Any]` → `dict[str, Any]`, `List[str]` → `list[str]`, `Optional[X]` → `X | None` 치환.

### 1-2. 로깅 포맷 통일 (f-string → %-포맷)

`self.logger.info(f"[Foo] {bar}")` → `self.logger.info("[Foo] %s", bar)` (lazy evaluation 권장)

대상 4개 파일, 22곳:
- `src/agents/conversation/knowledge.py` (7곳)
- `src/agents/conversation/intent_classifier.py` (4곳)
- `src/agents/podcast/script_generator.py` (3곳)
- `src/agents/podcast/script_personalizer.py` (8곳)

### 1-3. `traceback.print_exc()` → logger 전환

- `src/api/routes/podcasts.py:300`: `traceback.print_exc()` → `logger.error("...", exc_info=True)`

### 1-4. 루트 테스트 파일 이동

```
/test_e2e_podcast.py → /tests/api/e2e/test_e2e_podcast.py
/test_safety.py      → /tests/agents/podcast/test_safety.py
```

`conftest.py` import 경로 및 pytest 수집에 영향 없는지 확인.

### 1-5. 프롬프트 아카이브 정리

`prompts/podcast/_archive/` — README 1줄 추가 또는 디렉토리 통째 삭제 (아카이브 목적 확인 후).

### 1-6. 발표 자료 정리

`발표_자료/` — 확인 결과 이미 `.gitignore`에 포함됨. **추가 작업 불필요.**

**검증**: `pytest tests/ -v` — 전체 통과 확인

---

## Phase 2 — 주석 및 독스트링 보강 (무위험)

> 주석·독스트링만 추가. 실행 로직 변경 없음.

### 2-1. 복잡 로직 인라인 주석 추가

| 파일:라인 | 추가 내용 |
|----------|---------|
| `base_agent.py:192-223` | `_resolve_ab_variant()` — MD5 해시로 session_id를 0-9999 범위 정수로 매핑하여 A/B 그룹 결정. 동일 세션은 항상 동일 그룹에 배정됨. |
| `llm_client.py:389-481` | `_generate_bedrock()` — (1) Semaphore 획득, (2) system 배열에 cachePoint 조건부 삽입, (3) converse() 호출, (4) ThrottlingException → exponential backoff (1s→2s→4s), (5) usage 기록 |
| `workflow.py:211-255` | `run_with_cancel()` — Safety CRISIS 시 cancel_event.set()으로 나머지 TIER 1 태스크를 asyncio.Task.cancel() 경유 취소 |
| `callbacks.py:52-56` | `_MODEL_COSTS` — "2026-02 기준 Anthropic 공식 가격. 가격 변경 시 이 dict 갱신 필요" |
| `script_generator.py:22` | `WORDS_PER_MINUTE` — "한국어 기준 평균 발화 속도 (KBS 아나운서 기준 ~150 WPM). 팟캐스트 시간 추정에 사용" |

### 2-2. 독스트링 통일 (Google-style)

기준: `base_agent.py`의 Google-style (`Args:`, `Returns:`, `Raises:`)

보강 대상:
- `script_generator.py:24` — `__init__` 독스트링 추가
- `script_generator.py:155-189` — `_generate_title()` 반환 타입 문서화
- `script_generator.py:191-242` — `_generate_segment_script()` 파라미터 `knowledge_context` 문서화
- `script_personalizer.py:195-200` — `_query_user_profile()` 독스트링 완성

### 2-3. 모듈 헤더 독스트링 점검

기준: 파일 최상단에 모듈 설명 + TIER/모델/담당 정보.

이미 대부분 준수. 누락된 파일 확인 후 보완:
- `src/models/schemas.py` — 모듈 독스트링 확인
- `src/api/routes/` 하위 파일들 — TIER 없지만 역할 설명 확인

**검증**: `pytest tests/ -v` — 전체 통과 확인 (로직 변경 없음)

---

## Phase 3 — 불필요한 코드 제거 + 에러 처리 개선 (저위험)

> 동작에 영향을 주는 변경. 각 항목별로 관련 테스트 확인.

### 3-1. 미사용 변수 제거

| 파일 | 라인 | 변수 | 조치 |
|------|------|------|------|
| `script_personalizer.py` | 75 | `start_time = datetime.now()` | 제거 (실제 시간 계산은 다른 위치) |
| `podcasts.py` | 162 | `visual_data_raw` 첫 번째 할당 | 중복 할당 제거 (212번 줄의 할당만 유지) |

### 3-2. `emotion.py` 예외 타입 수정

```python
# 현재 (line 93)
except KeyError:
# 수정: LLM JSON 파싱 실패 전체를 커버
except Exception:
    self.logger.warning("[EmotionAgent] LLM 응답 파싱 실패 — 폴백 적용", exc_info=True)
```

### 3-3. `llm_client.py` 방어 코드 추가

```python
# 현재 (line 387 부근)
return response.content[0].text

# 수정
if not response.content:
    raise ValueError("Anthropic API returned empty content")
return response.content[0].text
```

> Shared Infrastructure — public 시그니처 변경 없음, 내부 방어 로직만 추가.

### 3-4. `podcasts.py:300` print → logger

```python
# 현재
traceback.print_exc()
# 수정
logger.error("[Podcast] 파이프라인 오류", exc_info=True)
```

(`import traceback` 제거 가능 여부 확인)

### 3-5. bare except 로깅 보강 (9곳)

bare `except Exception: pass` 또는 `except Exception:` 후 무시하는 패턴을 `logger.warning(..., exc_info=True)`으로 보강.

대상:
- `base_agent.py` (4곳: lines 138, 151, 277, 488) — 내부 방어 로직이므로 warning 로그 추가
- `podcasts.py` (3곳: lines 206, 235, 309) — 이미 `exc_info=True` 있는지 확인, 없으면 추가
- `batch_validator.py` (1곳: line 39) — 설정 로드 실패 시 warning 로그
- `workflow.py` (1곳: 확인 후 보강) — Protected File이므로 최소 변경

> `workflow.py`는 Protected File. 주석/로깅 추가만 하고 로직은 변경하지 않는다. 팀 리뷰 시 명시할 것.

### 3-6. 미사용 `features` 설정 섹션 처리

`settings.yaml:237-241` — 코드에서 전혀 읽지 않으므로:
- 주석으로 "미사용 — 향후 feature flag 도입 시 활성화" 명시
- 또는 삭제 (팀 확인 후)

### 3-7. `databases` 설정 읽기 코드 추가

`config/loader.py`에 `databases_config` property 추가 (Phase 4에서 추가한 설정이 읽히도록):

```python
@property
def databases_config(self) -> dict[str, Any]:
    """데이터베이스 설정을 반환한다."""
    return cast(dict[str, Any], self._config.get("databases", {}))
```

> Shared Infrastructure — 신규 property 추가만 (기존 메서드 변경 없음).

**검증**: `pytest tests/ -v`, 특히 `test_llm_client.py`, `test_emotion.py`

---

## Phase 4 — 문서 정비 (무위험)

> 코드 변경 없음. 문서 파일만 수정/생성.

### 4-1. 깨진 링크 수정

**`README.md:99-100`** — 두 가지 선택지:

**선택 A** (권장): 링크를 기존 문서로 리다이렉트
```markdown
| [CLAUDE.md](CLAUDE.md) | 프로젝트 구조, 아키텍처, 협업 규칙 상세 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 브랜치 전략, 커밋 컨벤션, PR 가이드 |
```

**선택 B**: `PROJECT_STRUCTURE.md`, `GIT_WORKFLOW.md` 신규 생성
- `PROJECT_STRUCTURE.md`: 현재 디렉토리 트리 + 파일별 역할 설명
- `GIT_WORKFLOW.md`: CONTRIBUTING.md에서 Git 관련 내용 추출·확장

→ **선택 A 권장** (중복 문서 방지, CLAUDE.md와 CONTRIBUTING.md가 이미 해당 내용 포함)

**`CONTRIBUTING.md:86,120`** — GIT_WORKFLOW.md 참조를 CONTRIBUTING.md 내부 섹션 앵커로 변경

### 4-2. `docs/INDEX.md` 갱신

현재 문서 목록이 실제 파일과 일치하는지 확인하고 갱신:
- `PROJECT_STRUCTURE.md` 제거 (또는 리다이렉트 명시)
- `GIT_WORKFLOW.md` 제거 (또는 리다이렉트 명시)

### 4-3. TODO(backend) 마커 갱신

전체 25개 `TODO(backend)` 마커 점검 (backend_resources.py 7건, api_proxy.py 15건, s3_client.py 1건, 기타 2건):
- 여전히 백엔드 팀 미확정인 항목은 유지
- 이미 확정된 항목이 있으면 TODO 제거
- 각 파일의 TODO 상태를 확인하고 현재 상태를 주석에 반영

### 4-4. 프롬프트 아카이브 README 추가

`prompts/podcast/_archive/README.md` 생성:
```markdown
# Prompt Archive
프롬프트 최적화 라운드에서 교체된 구버전. 참고용으로 보관.
삭제 시 프롬프트 히스토리 비교에 영향 없음.
```

### 4-5. `settings.yaml` 미사용 섹션 주석 보강

`features` 섹션에 설명 주석 추가:
```yaml
# [미사용] Feature flags — 향후 에이전트별 활성화/비활성화 제어 시 사용 예정
# 현재 코드에서 읽지 않음. 활성화 시 config/loader.py에 property 추가 필요.
features:
  podcast_mode: true
  ...
```

**검증**: 문서 링크 검증 (수동), `pytest` 불필요

---

## Phase 5 — Protected File 최소 변경 (팀 협의 필요)

> `workflow.py`는 Protected File. 3인 합의 필수. Phase 1-4 완료 후 별도 PR.

### 5-1. TIER 2-4 타임아웃 래퍼 적용

`workflow.py`의 TODO 5곳에 `asyncio.wait_for()` 래퍼 적용:

```python
# 현재
graph.add_node("synthesis", synthesis_node)  # TODO: _TIER2_TIMEOUT 적용

# 수정: 래퍼 함수로 감싸기
async def _with_timeout(coro_func, state, timeout, name):
    try:
        return await asyncio.wait_for(coro_func(state), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("[%s] 타임아웃 (%ds)", name, timeout)
        raise
```

대상 노드:
- `synthesis_node` → `_TIER2_TIMEOUT`
- `validator_node` → `_TIER3_TIMEOUT`
- `personalization_node` → `_TIER4_TIMEOUT`
- `batch_validator_node` → `_TIER3_TIMEOUT`
- `script_personalizer_node` → `_TIER4_TIMEOUT`

### 5-2. `podcasts.py` 순환 import 정리

`src/api/routes/podcasts.py:139, 278` — 함수 내부 import 패턴:
```python
def some_route():
    from src.api.main import get_compiled_graph  # 순환 import 회피
```

→ 의존성 주입 패턴 또는 별도 registry 모듈로 분리 검토.
(구조적 변경이므로 팀 설계 논의 후 진행)

---

## Phase 6 — 보안: 프롬프트 인젝션 방어

> 6-1 API Key 인증은 백엔드 팀 합의 후 진행 — 이번 계획에서 제외.

### 6-1. 프롬프트 인젝션 입력 전처리 필터

**신규 파일**: `src/agents/shared/input_sanitizer.py`
```python
"""사용자 입력의 프롬프트 인젝션 패턴을 감지한다."""
import re
from __future__ import annotations

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",       # "ignore previous instructions"
    r"(?:system|assistant)\s*:",          # 역할 탈출 시도
    r"\[INST\]",                          # Llama 형식 인젝션
    r"<\|im_start\|>",                   # ChatML 형식 인젝션
    r"(?:you\s+are|act\s+as)\s+(?:now|a)", # 역할 재정의
    r"(?:print|reveal|show)\s+(?:your|the)\s+(?:system|prompt|instructions)",  # 프롬프트 유출
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

def detect_injection(text: str) -> bool:
    """인젝션 패턴 감지 시 True 반환."""
    return any(pat.search(text) for pat in _COMPILED)
```

**수정 파일**: `src/api/routes/podcasts.py`, `src/api/routes/sessions.py`
- **라우트 레벨**에서 그래프 실행 전 인젝션 감지 (Shared Infrastructure 수정 회피)
- 감지 시 `state["safety_flags"]["injection_detected"] = True` 설정 후 정상 실행
- Safety Agent가 해당 플래그를 참조하여 최종 판단 (입력 자체는 차단하지 않음)

```python
# src/api/routes/podcasts.py (그래프 실행 직전)
from src.agents.shared.input_sanitizer import detect_injection

state = _build_initial_state(request)
if detect_injection(request.user_input):
    logger.warning("[Injection] 패턴 감지: %s", request.user_input[:50])
    state["safety_flags"] = {"injection_detected": True}
result = await graph.ainvoke(state)
```

> BaseAgent.__call__은 Shared Infrastructure이므로 수정하지 않는다. 라우트 레벨 전처리가 더 안전.

**검증**: `pytest tests/agents/shared/` + 신규 `tests/agents/shared/test_input_sanitizer.py`

### 6-2. 테스트 인프라 (Phase 6-10 공통)

**수정 파일**: `pyproject.toml` — 테스트 마커 추가
```toml
markers = [
    # ... 기존 마커 유지 ...
    "security: 보안 관련 테스트 (인젝션, 인증)",
    "resilience: 회복력 테스트 (Circuit Breaker, 타임아웃)",
    "streaming: SSE 스트리밍 테스트",
]
```

### 6-3. 인젝션 감지 테스트

**신규 파일**: `tests/agents/shared/test_input_sanitizer.py`
- 정상 입력 → False
- 각 인젝션 패턴 → True
- 한국어 일반 문장 → False (오탐 방지)
- `@pytest.mark.security` 마커 적용

---

## Phase 7 — 안정성: Circuit Breaker (수동 구현)

### 7-1. LLMClient 내부 Circuit Breaker

외부 라이브러리 없이 `llm_client.py` 내부에 상태 머신 구현.

**수정 파일**: `src/agents/shared/llm_client.py`

```python
class _CircuitBreaker:
    """LLM 프로바이더별 Circuit Breaker 상태 머신.

    상태 전이:
        CLOSED → (fail_max 연속 실패) → OPEN
        OPEN → (reset_timeout 경과) → HALF_OPEN
        HALF_OPEN → (1회 성공) → CLOSED
        HALF_OPEN → (1회 실패) → OPEN

    동시성 안전: asyncio.Lock으로 상태 전이를 보호한다.
    실패 카운팅: retry 전체 실패 = 1회 카운트 (retry 개별 실패가 아님).
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, fail_max: int = 5, reset_timeout: float = 30.0):
        self._state = self.CLOSED
        self._failure_count = 0
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def check(self) -> None:
        """OPEN 상태면 CircuitOpenError를 발생시킨다."""
        async with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self._reset_timeout:
                    self._state = self.HALF_OPEN
                else:
                    raise CircuitOpenError(f"Circuit OPEN — {self._reset_timeout}s 대기 중")

    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._fail_max:
                self._state = self.OPEN

class CircuitOpenError(Exception):
    """Circuit Breaker가 OPEN 상태일 때 발생."""
```

**프로바이더별 breaker 관리** (클래스 변수):
```python
class LLMClient:
    # 프로바이더별 Circuit Breaker — 인스턴스 간 공유
    _breakers: dict[str, _CircuitBreaker] = {}

    @classmethod
    def _get_breaker(cls, provider: str) -> _CircuitBreaker:
        if provider not in cls._breakers:
            cfg = get_settings().circuit_breaker_config
            cls._breakers[provider] = _CircuitBreaker(
                fail_max=cfg.get("fail_max", 5),
                reset_timeout=cfg.get("reset_timeout", 30),
            )
        return cls._breakers[provider]
```

**실패 카운팅 전략**:
- `_generate_bedrock()`: retry 3회 전부 소진 후 최종 실패 시 `record_failure()` 1회
- `_generate_anthropic()`: 동일 패턴
- 즉, retry 내부 개별 실패는 카운트하지 않음 (cascading failure 방지 목적에 부합)

**설정 추가**: `config/settings.yaml`
```yaml
llm:
  circuit_breaker:
    fail_max: 5          # 연속 실패 횟수 → OPEN
    reset_timeout: 30    # OPEN → HALF_OPEN 전환 대기(초)
```

**설정 property 추가**: `config/loader.py`
```python
@property
def circuit_breaker_config(self) -> dict[str, Any]:
    """Circuit Breaker 설정을 반환한다."""
    return cast(dict[str, Any], self._config.get("llm", {}).get("circuit_breaker", {}))
```

**검증**: `pytest tests/agents/shared/test_llm_client.py` — Circuit Breaker 상태 전이 테스트 추가
- CLOSED → OPEN 전이 (fail_max 초과)
- OPEN → HALF_OPEN 전이 (reset_timeout 경과)
- HALF_OPEN → CLOSED 전이 (성공)
- 동시 요청 시 Lock 동작 확인

---

## Phase 8 — 팟캐스트 SSE 스트리밍 엔드포인트

> 기존 `POST /episodes`(ainvoke, 동기 대기)를 유지하면서,
> 신규 `POST /episodes/stream` SSE 엔드포인트를 추가한다.
> workflow.py의 `_get_writer()` + `stream_mode="custom"` 인프라를 HTTP로 노출하는 것이 핵심.

### 8-1. 기존 인프라 현황

**이미 구현된 스트리밍 인프라:**

1. `workflow.py:49-59` — `_get_writer()` 헬퍼:
   ```python
   def _get_writer():
       """LangGraph 스트림 라이터를 안전하게 가져온다."""
       try:
           from langgraph.config import get_stream_writer
           return get_stream_writer()
       except Exception:
           return lambda x: None
   ```

2. writer 호출이 이미 삽입된 위치 (10곳+):
   - `tier1_podcast_fan_out()`: TIER 1 시작/종료, 에이전트별 완료, CRISIS 감지
   - `tier2_podcast_fan_out()`: TIER 2 시작/종료
   - `tier1_conversation_fan_out()`: 대화모드 TIER 1 (향후 활용)

3. 기존 이벤트 포맷:
   ```python
   writer({
       "event": "tier_start" | "tier_end" | "agent_complete" | "crisis_detected",
       "tier": 0-4,
       "mode": "podcast",
       "agents": ["safety", "emotion", ...],  # tier_start에서만
       "agent": "script_generator",            # agent_complete에서만
       "elapsed_ms": 1234,
       "progress": "2/4",                      # agent_complete에서만
       "status": "ok" | "crisis",
   })
   ```

4. `compile_graph()` docstring(라인 880-886)에 `astream()` 사용 예제 존재하나 실제 호출 없음.

**현재 엔드포인트** (`podcasts.py:239-344`):
- `POST /api/v1/podcasts/episodes` → `ainvoke()` → 전체 완료 후 `SlimPodcastResponse` 반환
- 스트리밍 없음

### 8-2. SSE 엔드포인트 추가

**수정 파일**: `src/api/routes/podcasts.py`

기존 `create_podcast_episode()` 엔드포인트는 그대로 유지 (하위 호환).
새로운 스트리밍 엔드포인트를 추가한다.

```python
from fastapi.responses import StreamingResponse

@router.post("/episodes/stream")
async def stream_podcast_episode(request: PodcastRequest) -> StreamingResponse:
    """팟캐스트 에피소드 생성 — SSE 스트리밍.

    TIER별 진행 상황을 실시간으로 전송한다.
    기존 POST /episodes와 동일한 파이프라인을 실행하되,
    ainvoke() 대신 astream()을 사용하여 중간 이벤트를 SSE로 전달한다.

    SSE 이벤트 흐름:
        1. connected          — 연결 성공, 파이프라인 시작
        2. tier_start          — TIER N 시작 (포함 에이전트 목록)
        3. agent_complete      — 개별 에이전트 완료 (진행률)
        4. crisis_detected     — Safety CRISIS 감지 (TIER 1 취소)
        5. tier_end            — TIER N 종료 (소요 시간)
        6. result              — 최종 결과 (SlimPodcastResponse JSON)
        7. done                — 스트림 종료
        8. error               — 오류 발생 시

    클라이언트 사용 예시:
        const evtSource = new EventSource('/api/v1/podcasts/episodes/stream');
        evtSource.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.event === 'tier_start') updateProgress(data);
            if (data.event === 'result') showResult(data);
            if (data.event === 'done') evtSource.close();
        };
    """
    # 1. 입력 검증 및 초기 상태 구성 (기존 create_podcast_episode와 동일)
    compiled_graph = _get_compiled_graph()
    initial_state = _build_initial_state(request)
    telemetry_cb = MindLogTelemetryCallback(...)

    config = {
        "configurable": {"thread_id": request.session_id},
        "callbacks": [telemetry_cb],
    }

    async def event_generator():
        """SSE 이벤트 생성기.

        astream(stream_mode=["updates", "custom"])으로 그래프를 실행한다.
        - "custom" 모드: workflow.py의 writer() 호출이 이벤트로 전달됨
        - "updates" 모드: 노드별 상태 업데이트 (최종 결과 추출용)
        """
        import json
        from datetime import datetime, timezone

        # 연결 성공 이벤트
        yield _sse_format({
            "event": "connected",
            "timestamp": _now_iso(),
            "session_id": request.session_id,
        })

        final_state = {}

        try:
            async for mode, chunk in compiled_graph.astream(
                initial_state,
                config=config,
                stream_mode=["updates", "custom"],
            ):
                if mode == "custom":
                    # writer()가 발행한 커스텀 이벤트를 SSE로 전달
                    chunk["timestamp"] = _now_iso()
                    yield _sse_format(chunk)

                elif mode == "updates":
                    # 노드별 상태 업데이트 — final_state 누적
                    # (클라이언트에는 전송하지 않음, 최종 결과 구성용)
                    if isinstance(chunk, dict):
                        for node_output in chunk.values():
                            if isinstance(node_output, dict):
                                final_state.update(node_output)

            # 파이프라인 완료 — 최종 결과 구성
            episode_data = _build_episode_data(final_state)
            safety_alert = _extract_safety_alert(final_state)

            # DB 저장 (기존 로직 재사용)
            await _save_core_data(
                final_state, episode_data, request, compiled_graph
            )

            # 최종 결과 이벤트
            result_payload = SlimPodcastResponse(
                episode_id=episode_data.episode_id,
                session_id=request.session_id,
                safety_alert=safety_alert,
                tracing=request.tracing,
            )
            yield _sse_format({
                "event": "result",
                "data": result_payload.model_dump(),
                "timestamp": _now_iso(),
            })

        except Exception as e:
            logger.error("[SSE] 파이프라인 오류: %s", e, exc_info=True)
            yield _sse_format({
                "event": "error",
                "message": "파이프라인 실행 중 오류가 발생했습니다.",
                "timestamp": _now_iso(),
            })

        # 스트림 종료 이벤트
        yield _sse_format({"event": "done", "timestamp": _now_iso()})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",        # 프록시 캐싱 방지
            "Connection": "keep-alive",          # 연결 유지
            "X-Accel-Buffering": "no",           # Nginx 버퍼링 비활성화
        },
    )


def _sse_format(data: dict) -> str:
    """SSE 프로토콜 형식으로 변환한다.

    SSE 표준: 각 이벤트는 'data: {JSON}\n\n' 형식.
    브라우저 EventSource API가 이 형식을 자동 파싱한다.
    """
    import json
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _now_iso() -> str:
    """현재 시각을 ISO 8601 형식으로 반환한다."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

### 8-3. SSE 이벤트 스키마

**수정 파일**: `src/api/external_schemas.py`

```python
class SSEEventData(BaseModel):
    """SSE 스트리밍 이벤트 데이터 스키마.

    팟캐스트 에피소드 생성 과정에서 클라이언트에 실시간 전달되는 이벤트.
    각 이벤트는 'data: {JSON}\n\n' 형식의 SSE 프로토콜로 전송된다.

    이벤트 타입별 필드:
        connected:        session_id
        tier_start:       tier, mode, agents[]
        agent_complete:   tier, agent, elapsed_ms, progress
        crisis_detected:  tier, status
        tier_end:         tier, mode, elapsed_ms, status
        result:           data (SlimPodcastResponse)
        error:            message
        done:             (없음)
    """
    event: str
    tier: int | None = None
    mode: str | None = None
    agent: str | None = None
    agents: list[str] | None = None
    elapsed_ms: int | None = None
    progress: str | None = None
    status: str | None = None
    session_id: str | None = None
    message: str | None = None
    data: dict[str, Any] | None = None
    timestamp: str
```

### 8-4. 기존 헬퍼 함수 재사용

기존 `podcasts.py`의 다음 함수들을 SSE 엔드포인트에서 재사용:
- `_build_initial_state(request)` — 초기 AgentState 구성
- `_build_episode_data(state)` — final_output → PodcastEpisodeData
- `_extract_safety_alert(state)` — safety_flags → SafetyAlertData
- `_save_core_data(state, episode_data, request, graph)` — DB 저장
- `_get_compiled_graph()` — 컴파일된 그래프 참조

> 이 함수들이 현재 엔드포인트 함수 내부에 정의되어 있다면, 모듈 레벨로 추출하여 양쪽에서 재사용한다.

### 8-5. docker-compose.yml / Nginx 고려사항

```yaml
# docker-compose.yml — 기존 healthcheck는 HTTP GET이므로 SSE와 무관
# Nginx 리버스 프록시 사용 시 아래 설정 필요:
#   proxy_buffering off;
#   proxy_cache off;
#   proxy_set_header Connection '';
#   chunked_transfer_encoding off;
```

> ALB 사용 시: Target Group의 idle timeout을 SSE 최대 예상 시간(~120s)보다 길게 설정.

### 8-6. 에러 처리 및 타임아웃

- `astream()` 내부 에이전트 오류 → `error` 이벤트 전송 후 `done`으로 종료
- 클라이언트 연결 끊김 → `event_generator()` 내부 GeneratorExit 발생, 자원 정리
- 서버 측 전체 타임아웃: FastAPI의 기본 keep-alive + ALB idle timeout으로 관리

### 8-7. 검증

```bash
# 1. 수동 테스트 — curl로 SSE 스트림 확인
curl -N -X POST http://localhost:8000/api/v1/podcasts/episodes/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","session_id":"sess_001","situation":"테스트",...}'

# 기대 출력:
# data: {"event":"connected","timestamp":"...","session_id":"sess_001"}
# data: {"event":"tier_start","tier":0,"mode":"podcast",...}
# data: {"event":"tier_end","tier":0,...}
# data: {"event":"tier_start","tier":1,"mode":"podcast","agents":["safety","emotion",...],...}
# data: {"event":"agent_complete","tier":1,"agent":"safety","progress":"1/4",...}
# ...
# data: {"event":"result","data":{...},"timestamp":"..."}
# data: {"event":"done","timestamp":"..."}

# 2. 기존 엔드포인트 하위 호환 확인
pytest tests/api/ -v -k "podcast"

# 3. SSE 이벤트 포맷 검증 테스트
pytest tests/api/test_sse_streaming.py -v
```

---

## Phase 9 — 출력 PII 정제 (CRITICAL)

> 멘탈케어 서비스 특성상 LLM이 사용자의 이름, 전화번호, 주소 등을 응답에 포함할 수 있다.
> 최종 응답이 DB에 저장되기 전에 PII를 감지·마스킹하는 레이어를 추가한다.
>
> **보안 담당자 검토 예정**: 이 모듈은 AI팀이 초기 구현하며, 추후 사이버 보안 담당자가
> 패턴 정확성, 커버리지, 규정 준수 여부를 검토하고 수정할 수 있다.
> 코드에 자세한 주석을 달아 보안 담당자가 이해하고 수정할 수 있도록 한다.

### 9-0. 현재 데이터 흐름 분석

PII 노출 지점을 정확히 파악한 결과:

```
final_output (PersonalizedScript JSON)
    ├─→ [API 응답] SlimPodcastResponse — episode_id + safety_alert만 포함 (✅ 안전)
    └─→ [DB 저장] _save_core_data() → script_text, key_insights 등 포함 (⚠️ PII 가능)
```

- **API 응답 (SlimPodcastResponse)**: episode_id와 safety_alert(고정 템플릿)만 포함 → 이미 안전
- **DB 저장 (podcasts.py:145-200)**: script_text, episode_title, key_insights가 MySQL에 저장 → PII 포함 가능
- **SSE 스트리밍 (Phase 8)**: result 이벤트에 SlimPodcastResponse만 전달 → 안전
- **기존 입력 정제**: `io_tracker.py:192-212`의 `_sanitize()`, `base_agent.py:791-822`의 `_sanitize_state_snapshot()` — 모니터링 스냅샷만 정제, 출력 정제 없음

**정제 적용 지점**: `final_output`이 파싱된 직후, DB 저장 전 (`_build_episode_data()` 호출 직전)

### 9-1. PII 감지 모듈

**신규 파일**: `src/agents/shared/output_sanitizer.py`

정규식 기반 PII 패턴 감지 (한국어 + 영어). 외부 라이브러리(Presidio 등) 의존 없이 최소 구현.
보안 담당자가 패턴을 추가/수정할 수 있도록 각 패턴에 상세 주석을 작성한다.

```python
"""LLM 출력에서 PII(개인식별정보) 패턴을 감지하고 마스킹한다.

[보안 담당자 참고]
이 모듈은 AI팀이 초기 구현한 최소 PII 정제 레이어입니다.
패턴 추가/수정, 마스킹 정책 변경, 외부 라이브러리(Microsoft Presidio 등) 전환은
보안 담당자가 검토 후 진행해 주세요.

주요 설계 결정:
1. 정규식 기반 — 외부 의존성 없이 배포 가능 (Presidio 전환 시 이 파일만 교체)
2. 감지만 하고 차단하지 않음 — 마스킹 후 정상 처리 (서비스 가용성 우선)
3. 로깅 — 감지된 PII 타입을 로그에 기록 (원본 데이터는 기록하지 않음)
4. 설정 기반 — settings.yaml에서 활성화/비활성화 가능

적용 위치:
- src/api/routes/podcasts.py — DB 저장 전 final_output 정제
- src/api/routes/sessions.py — (향후 대화모드 구현 시)

한계:
- 이름/주소 등 자연어 PII는 정규식으로 감지 불가 (NER 모델 필요)
- 정규식 오탐(false positive) 가능 — 예: 12자리 일반 숫자가 주민번호로 인식
- 한국어 특화 패턴만 포함 — 다국어 지원 시 패턴 확장 필요
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ============================================================
# PII 패턴 정의
# ============================================================
# [보안 담당자 참고] 패턴 추가/수정 시 이 리스트만 변경하면 됩니다.
# 각 항목: (패턴_이름, 컴파일된_정규식, 마스킹_텍스트, 설명)
#
# 패턴 우선순위: 리스트 순서대로 적용됨.
# 주민번호(13자리)를 먼저 매칭해야 전화번호(11자리)와 겹치지 않습니다.
# ============================================================

_PII_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    # --- 한국 주민등록번호 (Resident Registration Number) ---
    # 형식: YYMMDD-GNNNNNN (G=성별: 1~4, 외국인: 5~8)
    # 예시: 900101-1234567, 9001011234567
    # [주의] 13자리 숫자 조합이므로 오탐 가능성 있음
    (
        "rrn_kr",
        re.compile(
            r"\b(\d{2})"                   # 출생년도 2자리
            r"(0[1-9]|1[0-2])"             # 월 (01-12)
            r"(0[1-9]|[12]\d|3[01])"       # 일 (01-31)
            r"-?"                           # 하이픈 선택
            r"([1-8])"                      # 성별/세기 구분 (1-4: 내국인, 5-8: 외국인)
            r"(\d{6})"                      # 나머지 6자리
            r"\b"
        ),
        "[주민번호_마스킹]",
        "한국 주민등록번호 (13자리, 하이픈 포함/미포함)",
    ),

    # --- 한국 휴대전화 번호 ---
    # 형식: 01X-XXXX-XXXX 또는 01XXXXXXXXX
    # 유효 접두사: 010, 011, 016, 017, 018, 019
    (
        "phone_kr_mobile",
        re.compile(
            r"\b(01[016789])"              # 통신사 접두사
            r"-?"                           # 하이픈 선택
            r"(\d{3,4})"                    # 중간 3-4자리
            r"-?"                           # 하이픈 선택
            r"(\d{4})"                      # 마지막 4자리
            r"\b"
        ),
        "[휴대전화_마스킹]",
        "한국 휴대전화 번호 (010-1234-5678 등)",
    ),

    # --- 한국 유선전화 번호 ---
    # 형식: 0XX-XXXX-XXXX (지역번호 2-3자리)
    # 서울(02), 경기(031), 부산(051) 등
    # [주의] 010 등 휴대전화와 겹치지 않도록 위에서 먼저 매칭
    (
        "phone_kr_landline",
        re.compile(
            r"\b(0[2-6]\d?)"               # 지역번호 (02, 031, 051 등)
            r"-?"                           # 하이픈 선택
            r"(\d{3,4})"                    # 중간 3-4자리
            r"-?"                           # 하이픈 선택
            r"(\d{4})"                      # 마지막 4자리
            r"\b"
        ),
        "[유선전화_마스킹]",
        "한국 유선전화 번호 (02-1234-5678, 031-123-4567 등)",
    ),

    # --- 이메일 주소 ---
    # RFC 5322 간소화 버전
    (
        "email",
        re.compile(
            r"\b[a-zA-Z0-9._%+\-]+"        # 로컬 파트
            r"@"
            r"[a-zA-Z0-9.\-]+"             # 도메인
            r"\.[a-zA-Z]{2,}"              # TLD
            r"\b"
        ),
        "[이메일_마스킹]",
        "이메일 주소",
    ),

    # --- 신용카드 번호 ---
    # 형식: 16자리 (4-4-4-4, 하이픈/공백 구분)
    # Visa, Mastercard, 국내 카드 등
    # [주의] 16자리 숫자 조합 오탐 가능 — 신용카드가 LLM 출력에 나올 확률은 낮음
    (
        "card_number",
        re.compile(
            r"\b(\d{4})"                   # 첫 4자리
            r"[-\s]?"                       # 구분자 선택
            r"(\d{4})"                      # 둘째 4자리
            r"[-\s]?"
            r"(\d{4})"                      # 셋째 4자리
            r"[-\s]?"
            r"(\d{4})"                      # 넷째 4자리
            r"\b"
        ),
        "[카드번호_마스킹]",
        "신용카드/체크카드 번호 (16자리)",
    ),

    # --- 계좌번호 ---
    # 한국 은행 계좌: 10-14자리, 하이픈 구분
    # [주의] 오탐률이 높은 패턴 — 필요 시 비활성화 고려
    (
        "bank_account_kr",
        re.compile(
            r"\b(\d{3,4})"                 # 은행/지점 코드
            r"-"                            # 하이픈 필수 (오탐 방지)
            r"(\d{2,6})"                    # 중간
            r"-"
            r"(\d{1,4})"                    # 끝
            r"\b"
        ),
        "[계좌번호_마스킹]",
        "한국 은행 계좌번호 (하이픈 포함 형식만 감지)",
    ),
]

# 컴파일 검증 — 모듈 로드 시 패턴 문법 오류를 즉시 발견
assert all(isinstance(p[1], re.Pattern) for p in _PII_PATTERNS), "PII 패턴 컴파일 오류"


def sanitize_output(text: str) -> tuple[str, list[str]]:
    """LLM 출력 텍스트에서 PII를 감지하고 마스킹한다.

    [보안 담당자 참고]
    - 감지된 PII는 한국어 마스킹 텍스트로 대체됩니다 (예: [휴대전화_마스킹])
    - 원본 PII 값은 로그에 기록하지 않습니다 (감지된 타입명만 기록)
    - 마스킹 텍스트 형식을 변경하려면 _PII_PATTERNS의 3번째 요소를 수정하세요

    Args:
        text: LLM 출력 텍스트 (final_output 등)

    Returns:
        tuple: (마스킹된 텍스트, 감지된 PII 타입 이름 리스트)
               PII가 없으면 (원본 텍스트, []) 반환

    Examples:
        >>> sanitize_output("연락처는 010-1234-5678입니다")
        ("연락처는 [휴대전화_마스킹]입니다", ["phone_kr_mobile"])

        >>> sanitize_output("오늘 날씨가 좋습니다")
        ("오늘 날씨가 좋습니다", [])
    """
    if not text:
        return text, []

    detected: list[str] = []
    result = text

    for name, pattern, mask_text, _description in _PII_PATTERNS:
        if pattern.search(result):
            detected.append(name)
            result = pattern.sub(mask_text, result)

    if detected:
        # [보안 로그] 감지된 PII 타입만 기록 — 원본 값은 절대 로그에 남기지 않음
        logger.warning(
            "[PII 정제] 감지된 패턴: %s (총 %d건)",
            detected, len(detected),
        )

    return result, detected


def sanitize_dict_values(data: dict, target_keys: list[str] | None = None) -> dict:
    """dict 내의 문자열 값들에서 PII를 정제한다.

    [보안 담당자 참고]
    JSON 파싱된 final_output(dict)의 특정 필드만 선택적으로 정제할 때 사용합니다.
    target_keys가 None이면 모든 문자열 값을 정제합니다.

    Args:
        data: 정제 대상 dict
        target_keys: 정제할 키 목록. None이면 모든 문자열 값 정제.
                     예: ["script_text", "episode_title", "key_insights"]

    Returns:
        정제된 dict (원본을 변경하지 않고 새 dict 반환)
    """
    sanitized = {}
    all_detected: list[str] = []

    for key, value in data.items():
        if isinstance(value, str):
            if target_keys is None or key in target_keys:
                clean, detected = sanitize_output(value)
                sanitized[key] = clean
                all_detected.extend(detected)
            else:
                sanitized[key] = value
        elif isinstance(value, list):
            # 리스트 내 문자열도 정제 (예: key_insights, themes)
            sanitized_list = []
            for item in value:
                if isinstance(item, str) and (target_keys is None or key in target_keys):
                    clean, detected = sanitize_output(item)
                    sanitized_list.append(clean)
                    all_detected.extend(detected)
                else:
                    sanitized_list.append(item)
            sanitized[key] = sanitized_list
        elif isinstance(value, dict):
            # 중첩 dict 재귀 정제 (예: segments 내부)
            sanitized[key] = sanitize_dict_values(value, target_keys)
        else:
            sanitized[key] = value

    return sanitized


# ============================================================
# [보안 담당자 참고] 패턴 확장 가이드
# ============================================================
#
# 1. 새 패턴 추가:
#    _PII_PATTERNS 리스트에 튜플 추가:
#    ("패턴_이름", re.compile(r"정규식"), "[마스킹_텍스트]", "설명")
#
# 2. 패턴 우선순위:
#    리스트 순서대로 매칭됨. 긴 패턴(주민번호 13자리)을
#    짧은 패턴(전화번호 11자리)보다 먼저 배치할 것.
#
# 3. 오탐 방지:
#    \b (단어 경계)를 적극 사용하여 부분 매칭 방지.
#    하이픈 필수 패턴(계좌번호)은 오탐률을 낮추는 데 효과적.
#
# 4. 외부 라이브러리 전환:
#    Microsoft Presidio 등 NER 기반 PII 감지로 전환 시
#    sanitize_output() 함수 내부만 교체하면 됨.
#    함수 시그니처(입력: str, 출력: tuple[str, list[str]])는 유지.
#
# 5. 테스트:
#    tests/agents/shared/test_output_sanitizer.py에 테스트 케이스 추가.
#    오탐/미탐 케이스도 반드시 포함.
# ============================================================
```

### 9-2. 라우트 레벨 적용

**수정 파일**: `src/api/routes/podcasts.py`

`final_output` JSON을 파싱한 직후, `_build_episode_data()` 호출 전에 정제한다.
이 위치에서 정제하면 API 응답과 DB 저장 모두에 정제된 데이터가 사용된다.

```python
from src.agents.shared.output_sanitizer import sanitize_dict_values

# --- 기존 코드 (podcasts.py:44-49) ---
output_str = state.get("final_output", "{}")
script_data = json.loads(output_str) if output_str else {}

# --- 추가: PII 정제 (DB 저장 전) ---
# [보안 담당자 참고]
# script_text에 사용자 이름, 전화번호 등이 LLM에 의해 생성될 수 있다.
# 정제 대상 필드: script_text(대본), episode_title(제목), key_insights(통찰)
# segments 내부의 script_text도 재귀적으로 정제된다.
if get_settings().pii_sanitization_enabled:
    script_data = sanitize_dict_values(
        script_data,
        target_keys=["script_text", "episode_title", "key_insights"],
    )

episode_data = _build_episode_data(script_data)
```

**수정 파일**: `src/api/routes/sessions.py` (향후 대화모드 구현 시 동일 패턴 적용)

> SSE 스트리밍 엔드포인트(Phase 8)에도 동일한 정제 로직을 적용한다.
> `event_generator()` 내부에서 final_state 누적 후, result 이벤트 전송 전에 정제.

### 9-3. 설정

**수정 파일**: `config/settings.yaml`
```yaml
# ============================================================
# [보안] PII(개인식별정보) 정제 설정
# ============================================================
# [보안 담당자 참고]
# - enabled: false로 설정 시 PII 정제를 비활성화합니다 (개발 환경용)
# - 프로덕션에서는 반드시 true로 유지하세요
# - 정제 패턴은 src/agents/shared/output_sanitizer.py에서 관리합니다
security:
  pii_sanitization:
    enabled: true
```

**수정 파일**: `config/loader.py`
```python
@property
def pii_sanitization_enabled(self) -> bool:
    """PII 정제 활성화 여부를 반환한다."""
    return bool(
        self._config.get("security", {})
        .get("pii_sanitization", {})
        .get("enabled", True)  # 기본값: 활성화
    )
```

> Shared Infrastructure — 신규 property 추가만 (기존 메서드 변경 없음).

### 9-4. 테스트

**신규 파일**: `tests/agents/shared/test_output_sanitizer.py`

```python
"""output_sanitizer 모듈 테스트.

[보안 담당자 참고]
새 PII 패턴 추가 시 이 파일에도 테스트 케이스를 추가해 주세요.
오탐(false positive) 케이스도 반드시 포함하여 일반 텍스트가
잘못 마스킹되지 않는지 확인합니다.
"""
import pytest
from src.agents.shared.output_sanitizer import sanitize_output, sanitize_dict_values

# === 정탐(True Positive) 테스트 ===

class TestPhoneKrMobile:
    """한국 휴대전화 번호 감지."""

    def test_with_hyphens(self):
        text = "연락처는 010-1234-5678입니다"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected
        assert "010-1234-5678" not in result
        assert "[휴대전화_마스킹]" in result

    def test_without_hyphens(self):
        text = "전화번호 01012345678로 연락주세요"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected

    def test_old_prefix(self):
        """011, 016 등 구형 번호."""
        text = "011-234-5678"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected

class TestRrnKr:
    """한국 주민등록번호 감지."""

    def test_with_hyphen(self):
        text = "주민번호 900101-1234567"
        result, detected = sanitize_output(text)
        assert "rrn_kr" in detected
        assert "[주민번호_마스킹]" in result

    def test_without_hyphen(self):
        text = "9001011234567"
        result, detected = sanitize_output(text)
        assert "rrn_kr" in detected

class TestEmail:
    """이메일 주소 감지."""

    def test_standard(self):
        text = "이메일: user@example.com"
        result, detected = sanitize_output(text)
        assert "email" in detected
        assert "[이메일_마스킹]" in result

# === 오탐(False Positive) 방지 테스트 ===

class TestFalsePositives:
    """일반 텍스트가 잘못 마스킹되지 않는지 확인."""

    def test_normal_korean_text(self):
        text = "오늘 하루도 수고했어요. 내일은 더 좋은 날이 될 거예요."
        result, detected = sanitize_output(text)
        assert detected == []
        assert result == text

    def test_short_numbers(self):
        """짧은 숫자는 전화번호로 인식하지 않아야 함."""
        text = "3시에 만나요. 5개 사세요."
        result, detected = sanitize_output(text)
        assert detected == []

    def test_date_format(self):
        """날짜 형식이 주민번호로 인식되지 않아야 함."""
        text = "2026-03-31에 만나요"
        result, detected = sanitize_output(text)
        assert "rrn_kr" not in detected

# === 복합 테스트 ===

class TestMultiplePII:
    """여러 PII가 동시에 포함된 경우."""

    def test_multiple_types(self):
        text = "이름: 홍길동, 전화: 010-1234-5678, 이메일: hong@test.com"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected
        assert "email" in detected
        assert "010-1234-5678" not in result
        assert "hong@test.com" not in result

# === dict 정제 테스트 ===

class TestSanitizeDict:
    """dict 내 문자열 값 정제."""

    def test_target_keys(self):
        data = {
            "script_text": "전화 010-1234-5678로 상담하세요",
            "episode_title": "멘탈케어 에피소드",
            "duration": 300,
        }
        result = sanitize_dict_values(data, target_keys=["script_text"])
        assert "[휴대전화_마스킹]" in result["script_text"]
        assert result["episode_title"] == "멘탈케어 에피소드"  # 미정제
        assert result["duration"] == 300  # 숫자는 무변경
```

### 9-5. 검증

```bash
# 1. PII 정제 단위 테스트
pytest tests/agents/shared/test_output_sanitizer.py -v

# 2. 기존 팟캐스트 테스트 영향 없음 확인
pytest tests/api/ -v -k "podcast"

# 3. 수동 검증 — LLM에 전화번호 포함 입력 → DB 저장 데이터 확인
# (개발 환경에서 pii_sanitization.enabled: true 상태로 테스트)
```


---

## 추후 고려 사항

| 항목 | 결정 | 비고 |
|------|------|------|
| **서비스 간 API Key 인증** | 백엔드 합의 후 진행 | `X-API-Key` 헤더 검증 — 라우터별 Depends 적용, health/metrics 면제 |
| **AWS Secrets Manager** | 불필요 | 현재 CD 파이프라인(GitHub Actions Secrets → SSM → .env)으로 충분 |
| **체크포인트 영속화** | 백엔드 협의 필요 | 별도 DB 추가 불가. 백엔드 MySQL 활용 또는 MemorySaver 유지 검토 |
| **토큰 예산 관리** | 추후 필요 | 요청당 비용 상한, 입력 토큰 추정, 일일 예산 가드레일 |
| **CRISIS Human-in-the-Loop** | 불필요 | 현재 고정 메시지 출력 방식 유지 |
| Rate Limiting | API Gateway 레벨 | 인프라팀에 요구사항 전달 |
| DB 마이그레이션 | 보류 | AI 서버는 DB 직접 미사용 (BackendClient 경유) |
| 대화모드 Validator | 개발자3 구현 영역 | 현재 STUB — 이 계획 범위 밖 |
| 대화모드 SSE 스트리밍 | 대화모드 구현 후 진행 | conversations.py 신규 라우터 |
| OpenTelemetry 표준화 | 추후 검토 | 현재 커스텀 IOTracker+callbacks — OTEL 전환 시 대규모 리팩토링 |
| Config Hot-Reload | 추후 검토 | settings.yaml 변경 시 서버 재시작 필요 — watchdog 기반 reload 가능 |
| 컨텍스트 압축 | 추후 검토 | 긴 대화 시 토큰 절약 — staged compaction 패턴 |

---

## 수정 파일 목록

### Phase 1 (10개 파일)
- `src/agents/podcast/script_generator.py` — 타입 힌트
- `src/agents/conversation/knowledge.py` — 타입 힌트 + 로깅
- `src/agents/conversation/intent_classifier.py` — 타입 힌트 + 로깅
- `src/agents/podcast/script_personalizer.py` — 타입 힌트 + 로깅
- `src/models/schemas.py` — 타입 힌트
- `src/api/routes/podcasts.py` — traceback.print_exc 제거
- `test_e2e_podcast.py` → `tests/api/e2e/test_e2e_podcast.py` (이동)
- `test_safety.py` → `tests/agents/podcast/test_safety.py` (이동)
- `.gitignore` — 발표_자료/ 추가
- `prompts/podcast/_archive/` — 정리

### Phase 2 (6개 파일, 주석만)
- `src/agents/shared/base_agent.py` — 인라인 주석
- `src/agents/shared/llm_client.py` — 인라인 주석
- `src/graph/workflow.py` — 인라인 주석 (주석만이므로 Protected File 예외 가능)
- `src/monitoring/callbacks.py` — 가격 기준 주석
- `src/agents/podcast/script_generator.py` — WPM 근거 + 독스트링
- `src/agents/podcast/script_personalizer.py` — 독스트링 보강

### Phase 3 (7개 파일)
- `src/agents/podcast/script_personalizer.py` — 미사용 변수 제거
- `src/api/routes/podcasts.py` — 중복 변수 + print 제거 + bare except 보강
- `src/agents/podcast/emotion.py` — 예외 타입 수정
- `src/agents/shared/llm_client.py` — content 빈 리스트 방어
- `src/agents/shared/base_agent.py` — bare except 4곳 로깅 추가
- `src/agents/podcast/batch_validator.py` — bare except 로깅
- `config/loader.py` — `databases_config` property 추가

### Phase 4 (5개 파일, 문서)
- `README.md` — 깨진 링크 수정
- `CONTRIBUTING.md` — GIT_WORKFLOW 참조 수정
- `docs/INDEX.md` — 목록 갱신
- `config/settings.yaml` — features 섹션 주석
- `prompts/podcast/_archive/README.md` — 신규

### Phase 5 (2개 파일, 팀 협의)
- `src/graph/workflow.py` — TIER 타임아웃 래퍼
- `src/api/routes/podcasts.py` — 순환 import 정리 (검토)

### Phase 6 (5개 파일, 보안)
- `src/agents/shared/input_sanitizer.py` — 신규: 프롬프트 인젝션 패턴 감지
- `src/api/routes/podcasts.py` — 그래프 실행 전 인젝션 감지 호출
- `src/api/routes/sessions.py` — 동일
- `tests/agents/shared/test_input_sanitizer.py` — 신규: 인젝션 감지 테스트
- `pyproject.toml` — security/resilience/streaming 마커 추가

### Phase 7 (4개 파일, 안정성)
- `src/agents/shared/llm_client.py` — _CircuitBreaker 클래스 + 상태 머신
- `config/settings.yaml` — llm.circuit_breaker 설정 추가
- `config/loader.py` — circuit_breaker_config property 추가
- `tests/agents/shared/test_llm_client.py` — Circuit Breaker 테스트 추가

### Phase 8 (4개 파일, 팟캐스트 SSE 스트리밍)
- `src/api/routes/podcasts.py` — `/episodes/stream` SSE 엔드포인트 추가 + 헬퍼 함수 모듈 레벨 추출
- `src/api/external_schemas.py` — SSEEventData 스키마 추가
- `tests/api/test_sse_streaming.py` — 신규: SSE 이벤트 포맷 검증 테스트
- (기존 `_build_episode_data`, `_save_core_data` 등 재사용)

### Phase 9 (6개 파일, PII 정제 — 보안 담당자 검토 예정)
- `src/agents/shared/output_sanitizer.py` — 신규: PII 감지/마스킹 모듈 (자세한 주석 포함)
- `src/api/routes/podcasts.py` — DB 저장 전 final_output 정제
- `config/settings.yaml` — security.pii_sanitization 설정
- `config/loader.py` — pii_sanitization_enabled property
- `tests/agents/shared/test_output_sanitizer.py` — 신규: 정탐/오탐 테스트
- (향후 sessions.py에도 동일 패턴 적용)

---

## 검증

```bash
# Phase 1-3 공통
pytest tests/ -v

# Phase 1: 이동한 테스트 파일 실행 확인
pytest tests/api/e2e/test_e2e_podcast.py -v
pytest tests/agents/podcast/test_safety.py -v

# Phase 3: 변경된 에이전트 개별 테스트
pytest tests/agents/podcast/test_emotion.py -v
pytest tests/agents/shared/test_llm_client.py -v

# Phase 6: 보안 테스트
pytest tests/agents/shared/test_input_sanitizer.py -v

# Phase 7: Circuit Breaker 테스트
pytest tests/agents/shared/test_llm_client.py -v -k "circuit"

# Phase 8: SSE 스트리밍 테스트
pytest tests/api/test_sse_streaming.py -v
# 수동: curl -N -X POST http://localhost:8000/api/v1/podcasts/episodes/stream -H "Content-Type: application/json" -d '...'

# Phase 9: PII 정제 테스트 (보안 담당자 검토 전 기본 검증)
pytest tests/agents/shared/test_output_sanitizer.py -v

# 전체 완료 후
pytest tests/ -v --tb=short
```

### 완료 기준
1. `pytest tests/ -v` — 전체 통과 (기존 1 fail은 backend connectivity, 허용)
2. `git grep "from typing import.*Dict"` — 0건 (타입 힌트 통일)
3. `git grep "traceback.print_exc"` — 0건
4. 루트 디렉토리에 `test_*.py` 파일 없음
5. README/CONTRIBUTING 내 모든 문서 링크가 유효
6. 인젝션 패턴 입력 시 `safety_flags.injection_detected = True` 설정
7. LLM 5회 연속 실패 시 Circuit Breaker OPEN 전환 확인
8. 팟캐스트 SSE 스트리밍 엔드포인트 정상 응답
9. 전화번호/이메일/주민번호 포함 LLM 출력 → 마스킹 확인 (Phase 9)

---

---

## 실행 전 준비

1. 이 계획서를 `docs/superpowers/plans/`에 정식 저장 (실행 시 첫 번째 작업)
2. 각 Phase 완료 시 개별 커밋 + push
3. Phase 5는 별도 PR (Protected File 3인 합의)
4. Phase 6-9는 보안/안정성 관련이므로 충분한 테스트 후 커밋

## Phase 실행 순서 및 의존성

```
Phase 1-4: 독립 (순서대로, 각각 무위험~저위험)
Phase 5: Protected File — 별도 PR
Phase 6-9: 독립 (순서대로)
```

---

*마지막 업데이트: 2026-03-31 (v4 — 사용자 피드백 반영: API Key/대화모드/Secrets/체크포인트/토큰예산/CRISIS 제외)*

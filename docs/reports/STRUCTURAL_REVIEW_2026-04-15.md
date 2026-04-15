# 프로젝트 구조적 점검 보고서

**작성일**: 2026-04-15  
**대상 기간**: 2026-04-08 ~ 2026-04-14 (최근 일주일)  
**분석 범위**: PR #100 ~ #140, 커밋 170+건, 소스 코드 전체  
**목적**: 프로젝트 마무리를 위한 구조적 점검 — 반복 패턴, 잠재 이슈, 개선 방향

---

## 목차

1. [최근 일주일 통계 요약](#1-최근-일주일-통계-요약)
2. [반복 수정 패턴 분석](#2-반복-수정-패턴-분석)
3. [구조적 이슈 — 상세](#3-구조적-이슈--상세)
4. [잠재 이슈 — 에러 핸들링](#4-잠재-이슈--에러-핸들링)
5. [잠재 이슈 — 동시성/경합 조건](#5-잠재-이슈--동시성경합-조건)
6. [잠재 이슈 — 보안](#6-잠재-이슈--보안)
7. [잠재 이슈 — 리소스 관리](#7-잠재-이슈--리소스-관리)
8. [잠재 이슈 — 의존성/배포/CI](#8-잠재-이슈--의존성배포ci)
9. [잠재 이슈 — 워크플로우/설정 정합성](#9-잠재-이슈--워크플로우설정-정합성)
10. [긍정적 신호](#10-긍정적-신호)
11. [우선순위별 종합 액션 목록](#11-우선순위별-종합-액션-목록)

---

## 1. 최근 일주일 통계 요약

### 커밋 타입별 분포

| 타입 | 건수 | 비율 |
|------|------|------|
| docs: | 66 | 38.8% |
| fix: | 56 | 32.9% |
| feat: | 26 | 15.3% |
| test: | 10 | 5.9% |
| style: | 5 | 2.9% |
| refactor: | 4 | 2.4% |
| chore: | 3 | 1.8% |
| **합계** | **170** | **100%** |

### 수정 빈도 상위 파일 (src/ 내)

| 수정 횟수 | 파일 | 의미 |
|-----------|------|------|
| 18 | `src/api/client.py` | BackendClient 반복 수정 |
| 10 | `src/graph/workflow.py` | 파이프라인 엣지/타임아웃 조정 |
| 10 | `src/api/backend_resources.py` | 리소스 경로 변경 |
| 9 | `src/api/routes/podcasts.py` | SSE/라우트 수정 |
| 8 | `src/agents/shared/llm_client.py` | LLM 클라이언트 지연 추적 |
| 8 | `src/agents/podcast/content_analyzer.py` | 출력 스키마 감사 수정 |
| 7 | `src/agents/podcast/script_personalizer.py` | DI/메모리 필드 |
| 7 | `src/agents/podcast/podcast_reasoning.py` | DI/컨텍스트 주입 |
| 6 | `src/agents/podcast/visualization.py` | Titan 차단/JSON 파싱 |
| 6 | `src/agents/podcast/episode_memory.py` | KT Cloud 연동 |

> **해석**: fix 비율(32.9%)이 feat(15.3%)의 2배 이상. 기능 추가보다 버그 수정에 시간이 집중됨.
> client.py(18회)와 workflow.py(10회)가 핫스팟으로, 백엔드 연동과 파이프라인 조정이 반복됨.

### 머지된 PR 목록 (최근 일주일)

| PR | 날짜 | 제목 | 분류 |
|----|------|------|------|
| #140 | 04-14 | CancelledError 스택 트레이스 제거 | 안정성 |
| #139 | 04-14 | Titan ValidationException → ContentBlockedError 전환 누락 | Visualization 버그 |
| #138 | 04-14 | Visualization JSON 파싱 실패 대응 | Visualization 버그 |
| #137 | 04-14 | sonnet_37 APAC 지연 급증 모델 다운그레이드 | Bedrock 긴급 대응 |
| #136 | 04-14 | Bedrock 지연 추적 + docs 정리 | 관측성 |
| #135 | 04-14 | Bedrock LLM 지연 구간 추적 로깅 | 관측성 |
| #134 | 04-14 | Episode Memory phase별 컨텍스트 주입 개선 | 기능 |
| #133 | 04-14 | Visualization Titan 콘텐츠 정책 차단 방어 | Visualization 버그 |
| #132 | 04-14 | Batch Validator score/decision 불일치 보정 | LLM hallucination |
| #131 | 04-14 | LLM 레이턴시 추적 로깅 강화 | 관측성 |
| #130 | 04-14 | Docker graceful shutdown | 배포 안정성 |
| #129 | 04-14 | Ruff F401 수정 | CI lint |
| #128 | 04-14 | Black 포맷팅 수정 | CI lint |
| #127 | 04-14 | Episode Memory DI 전환 + KT Cloud 정합성 | 기능 |
| #126 | 04-14 | Episode Memory 계획서 | 문서 |
| #125 | 04-14 | Episode Memory user_id 복원 | Episode Memory 버그 |
| #124 | 04-14 | Episode Memory 원본 로직 복원 | Episode Memory 버그 |
| #123 | 04-14 | S3 ACL 롤백 | 롤백 |
| #122 | 04-14 | Episode Memory KT Cloud API 충돌 해소 | Episode Memory 버그 |
| #121 | 04-14 | 계획 문서 전체 점검 (v37) | 문서 |
| #120 | 04-14 | Ruff F401/E501 해결 | CI lint |
| #119 | 04-14 | 에피소드 메모리 에이전트 수정 (개발자2) | 기능 |
| #118 | 04-14 | Black 포매팅 적용 | CI lint |
| #117 | 04-14 | S3 ACL=public-read 추가 | 기능 (실패) |
| #116 | 04-14 | TIER 타임아웃 2배 확장 | 안정성 |
| #115 | 04-14 | 계획 문서 점검 (v35) | 문서 |
| #114 | 04-14 | CRISIS-타임아웃 로그 구분 및 경합 수정 | 안정성 |
| #113 | 04-14 | 로그 시스템 전체 통일 | 인프라 |
| #112 | 04-14 | 로그 시스템 정리 + 동시성 안전성 강화 | 인프라 |
| #111 | 04-14 | mind-frequencies 데이터 매핑 수정 | 백엔드 연동 |

---

## 2. 반복 수정 패턴 분석

### 2-1. Visualization — 3회 연속 수정 (#133 → #138 → #139)

| PR | 증상 | 수정 내용 |
|----|------|----------|
| #133 | AWS Titan이 콘텐츠 정책 위반으로 이미지 생성 거부 | 키워드 필터링 + SAFE_FALLBACK_PROMPT + 재시도 |
| #138 | LLM이 비정형 JSON 반환하여 `json.loads()` 실패 | 프롬프트 v1.19.0 강화 + regex fallback 추가 |
| #139 | Titan `ValidationException`이 `ContentBlockedError`로 변환되지 않음 | 예외 전환 로직 누락 수정 |

**근본 원인**: LLM JSON 출력 비보장 + Titan 에러 타입 다양성 미대응. regex fallback은 임시방편이며 재발 가능.  
**권장 해결**: Bedrock Structured Outputs (2026-02 GA) 또는 Tool Use 방식으로 JSON Schema 강제. Titan 에러 계층 구조를 전수 조사하여 포괄적 예외 처리.

### 2-2. Episode Memory — 5회 연속 수정 (#119 → #122 → #124 → #125 → #127)

| PR | 증상 | 수정 내용 |
|----|------|----------|
| #119 | 개발자2가 KT Cloud + Pinecone 통합 구현 | 신규 구현 |
| #122 | PR #119와 develop 간 충돌 | API 경로 수정 + 충돌 해소 |
| #124 | #119 머지 후 원본 로직이 깨짐 | 가은 원본 로직 복원 |
| #125 | upsert metadata에서 user_id가 누락됨 | user_id 복원 |
| #127 | Stub → 실제 에이전트 DI 전환 필요 | 어댑터 패턴 적용 |

**근본 원인**: 개발자 간 독립 브랜치에서 동일 파일 수정 → 통합 검증 없이 순차 머지. `user_id` 같은 기본 필드가 누락될 정도로 머지 후 E2E 검증 부재.  
**권장 해결**: Episode Memory 변경 시 통합 테스트 체크리스트 (upsert, search, metadata 포함) 필수화.

### 2-3. CI Lint — 4회 반복 (#118 → #120 → #128 → #129)

| PR | 도구 | 원인 |
|----|------|------|
| #118 | Black | 5개 파일 포맷 미적용 |
| #120 | Ruff | 17개 파일 미사용 import + 줄 길이 초과 |
| #128 | Black | 추가 파일 포맷 미적용 |
| #129 | Ruff | EpisodeMemoryStub import 미제거 |

**근본 원인**: `.pre-commit-config.yaml` 미존재. 로컬에서 lint 실행 없이 push → CI 실패 → 수정 커밋 반복.  
**권장 해결**: pre-commit hook 설치 (ruff + ruff-format 또는 black). 팀 전원 `pre-commit install` 실행.

### 2-4. S3 ACL 추가 → 즉시 롤백 (#117 → #123)

**경위**: `put_object(ACL="public-read")` 추가(#117) → 프로덕션에서 `AccessControlListNotSupported` 에러 → 즉시 롤백(#123).  
**근본 원인**: 2023년 4월 이후 신규 S3 버킷은 ACL 기본 비활성화. 사전 검증 없이 적용.  
**현재 상태**: S3 직접 URL 방식 유지 중이나 브라우저 접근 문제 미해결.  
**권장 해결**: CloudFront + OAC(Origin Access Control) 또는 Presigned URL 방식 전환.

### 2-5. Bedrock APAC 지연 → 긴급 다운그레이드 (#137)

**경위**: sonnet_37 APAC CRIS에서 지연 3.2x~16.3x 급증 → Intent Classifier(haiku), Safety/Personalizer(sonnet)로 다운그레이드.  
**현재 상태**: 다운그레이드 설정이 settings.yaml에 영구 반영됨. 복구 기준/시점 미정의. 다운그레이드 전후 품질 비교 미수행.  
**권장 해결**: (1) Global CRIS 전환 검토 (US/EU/APAC 전체 풀 라우팅), (2) 모델 계층 예산 정책 문서화, (3) CloudWatch P95 지연 알림 + 자동 fallback 로직.

---

## 3. 구조적 이슈 — 상세

### S-1. KnowledgeAgent Stub 영구 미연결 (위험도: 🔴 높음)

**파일**: `src/agents/podcast/podcast_reasoning.py:73`

```python
self.knowledge_agent = knowledge_agent or KnowledgeAgentStub()
```

- `KnowledgeAgent._embed_query()` 구현 존재 (knowledge.py:409)
- `KnowledgeAgent._search_knowledge_base()` 내부에서 `embedding_client`가 None이면 빈 결과 반환 (knowledge.py:144)
- 노드 함수(`podcast_reasoning_node`, line 663-665)에서는 `KnowledgeAgent()`를 주입하지만, embedding_client DI가 없어 실질적으로 빈 결과
- **결과**: 프로덕션에서 전문 지식 검색이 완전히 비활성 상태. RAG 파이프라인의 핵심 기능 미동작

**영향 범위**: 모든 팟캐스트 에피소드에서 전문 지식 참조 불가 → 스크립트 품질 저하

### S-2. Safety Agent LLM 실패 시 무조건 safe 판정 (위험도: 🔴 높음)

**파일**: `src/agents/podcast/safety.py:73-81`

```python
except Exception as e:
    self.logger.error("[SafetyAgent] LLM 호출 실패 — safe fallback: %s", e)
    result = {
        "risk_level": 0,
        "risk_score": 0.0,
        "status": "safe",
        ...
    }
```

- 멘탈케어 서비스에서 Safety Agent의 역할은 **위기 사용자 감지**
- LLM 호출 실패(네트워크, 타임아웃, Bedrock throttling 등) 시 무조건 `safe`로 판정
- 실제 위기 상황의 사용자가 `safe`로 오판되면 CRISIS 개입 없이 일반 파이프라인 진행
- **fail-safe 원칙 위반**: 안전 시스템은 실패 시 "더 안전한 쪽"(= CRISIS 또는 최소한 warning)으로 판정해야 함

**권장 조치**: LLM 실패 시 `risk_level: 2` (warning) 이상으로 설정하여 Personalizer에서 톤 조정 최소 보장. 또는 Intent Classifier의 1차 risk_flag를 유지하여 LLM 실패 시 1차 판정 그대로 사용.

### S-3. Batch Validator — LLM이 decision을 직접 출력 (위험도: 🟠 중간)

**파일**: `src/agents/podcast/batch_validator.py`

- PR #132에서 score/decision 불일치 보정 로직 추가됨
- 그러나 여전히 LLM이 `score`와 `decision`을 **독립적으로** 출력하는 구조
- LLM hallucination으로 score=0.85(통과)와 decision="REJECT"를 동시에 출력 가능
- 보정 로직은 후처리이며, 근본 해결이 아님

**권장 조치**: `decision` 필드를 LLM 출력에서 제거하고, 코드에서 `decision = "PASS" if score >= threshold else "REJECT"`로 결정하는 hybrid 방식 적용. temperature=0.0~0.1 고정.

### S-4. episode_memory.py — print() 사용 + 미정의 변수 참조 (위험도: 🟠 중간)

**파일**: `src/agents/podcast/episode_memory.py:128-132`

```python
except Exception as e:
    print(f"[Embedding error] {e}")       # ← get_agent_logger() 미사용
    try:
        print(f"[Embedding response body] {r.text}")  # noqa: F821 — r 미정의 가능
    except Exception:
        pass                               # ← 에러 완전 삼킴
    return []
```

**문제 3가지**:
1. `print()` 사용 → JSON 구조화 로그 미적용, CloudWatch/ELK 수집 누락 (PR #112/#113에서 나머지 18개 파일은 통일 완료)
2. `r` 변수가 정의되지 않은 채 `r.text` 접근 가능 → `NameError` 발생 → 내부 `except: pass`로 삼켜짐
3. 에러 후 빈 리스트 `[]` 반환 → 임베딩 실패가 상위 호출자에게 전파되지 않음

이 패턴이 `episode_memory.py` 내 **6곳** (line 128, 130, 150, 171, 217, 241)에서 반복됨.

### S-5. Script Personalizer 미구현 분기 (위험도: 🟡 낮음)

**파일**: `src/agents/podcast/script_personalizer.py:347-355, 450`

```python
if attitude == "empathetic":
    pass
elif attitude == "rational":
    pass
# ...
if "hearing_impairment" in ...:
    pass
```

- 태도별 텍스트 조정, 청각 장애 접근성 — 개인화 에이전트의 핵심 기능이 `pass` 처리
- 비즈니스 규칙 정의가 선행되어야 하며, 현재는 LLM 프롬프트에 의존

### S-6. test_knowledge.py RuntimeWarning — coroutine never awaited (위험도: 🟡 낮음)

**파일**: `tests/agents/podcast/test_knowledge.py:63`

```
RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
```

- AsyncMock의 반환값이 올바르게 await되지 않아 비동기 동작을 실제로 검증하지 못하는 테스트
- 596 passed이므로 기능 테스트에는 영향 없으나, 비동기 mock 패턴 오류

### S-7. data/cache/ 디렉토리 미생성 (위험도: 🟡 낮음)

- Episode Memory가 런타임에 `data/cache/` 경로에 의존
- 프로젝트 루트에 해당 디렉토리 미존재 → 프로덕션에서 `FileNotFoundError` 잠재
- `.gitkeep` 파일로 디렉토리 유지 필요

### S-8. CLAUDE.md 문서-코드 불일치 4건 (위험도: 🟡 낮음)

| 항목 | CLAUDE.md 기술 | 실제 코드 |
|------|---------------|----------|
| API 타임아웃 | "기본 5초, LLM 30초" | settings.yaml: `timeout: 10`, `llm_timeout: 60` |
| wait_for_stories 노드 | 미기술 | workflow.py:641에 TIER 3→4 사이 삽입 |
| Script Personalizer 쓰기 필드 | `final_output` 만 명시 | `memory_write`, `memory_text`, `memory_metadata` 추가 반환 |
| Podcast Reasoning 쓰기 필드 | `reasoning_result` 만 명시 | `memory_results`, `knowledge_results`도 기록 |

---

## 4. 잠재 이슈 — 에러 핸들링

### E-1. workflow.py _with_timeout 빈 dict 반환으로 검증 우회 (위험도: 🟠 중간)

**파일**: `src/graph/workflow.py:92-96`

```python
except asyncio.TimeoutError:
    logger.error("[%s] 타임아웃 (%ds)", name, timeout)
    return {}
```

- 타임아웃 시 빈 dict를 반환하면 LangGraph가 정상 결과로 merge
- `batch_validator_node` 타임아웃 시 `validation_result` 미설정 → `verdict is None` → 재시도 소진 후 **강제 통과**
- 검증 없이 TIER 4로 진행되어 품질 미달 스크립트가 사용자에게 전달 가능

### E-2. knowledge.py — 13개 except Exception 블록에서 빈 결과 반환 (위험도: 🟡 낮음)

**파일**: `src/agents/podcast/knowledge.py` (13곳)

- 각 하위 호출이 독립적으로 실패해도 빈 리스트/dict 반환으로 graceful degradation
- 단일 실패는 문제없으나, 여러 하위 호출 연쇄 실패 시 빈 `knowledge_results` 전달
- **연쇄 실패 임계값 검사 부재** — 전부 실패해도 경고 없이 진행

### E-3. ScriptPersonalizer Pydantic 실패 후 None 진행 (위험도: 🟡 낮음)

**파일**: `src/agents/podcast/script_personalizer.py:93, 111-113`

```python
validated_script: ValidatedScript | None = None
# ...
except Exception as pydantic_err:
    self.logger.warning("[ScriptPersonalizer] Pydantic 실패: %s", pydantic_err)
```

- Pydantic 파싱 실패 시 `validated_script`가 `None`으로 유지
- 후속 코드에서 `None` 체크 없이 속성 접근 시 `AttributeError` 가능
- 현재 fallback 경로에서 `"validated_script" in locals()` 체크가 부분적으로 존재

---

## 5. 잠재 이슈 — 동시성/경합 조건

### C-1. Circuit Breaker _breakers 클래스 변수 — check-then-act 경합 (위험도: 🟡 낮음)

**파일**: `src/agents/shared/llm_client.py:141, 148-156`

```python
_breakers: dict[str, _CircuitBreaker] = {}

@classmethod
def _get_breaker(cls, provider: str) -> _CircuitBreaker:
    if provider not in cls._breakers:          # check
        cls._breakers[provider] = _CircuitBreaker(...)  # act
    return cls._breakers[provider]
```

- 두 코루틴이 동시에 동일 provider로 진입하면 Circuit Breaker가 2개 생성, 하나 덮어쓰기
- asyncio는 싱글 스레드이므로 일반적으로 안전하지만, `await` 포인트가 check와 act 사이에 있으면 발생 가능
- 실제 확률은 극히 낮음 (앱 초기화 시점에 집중)

### C-2. StoriesStore 고아 세션 메모리 누수 (위험도: 🟠 중간)

**파일**: `src/api/stories_store.py:51-60`

- `wait_for_stories()` 타임아웃 → `None` 반환이지만 `_store`에서 엔트리 미삭제
- 정상 경로에서는 `delete_session()` 호출로 정리되지만, TIER 1~3에서 예외 발생 시 `wait_for_stories()`가 아예 실행되지 못함
- `_get_or_create()`로 생성된 엔트리가 영구 잔류 → 장기 운영 시 `_store` dict 증가

**권장 조치**: TTL 기반 자동 정리 또는 주기적 cleanup 로직 추가.

### C-3. TIER 1 cancel 후 LLM 호출 비용 누수 (위험도: 🟡 낮음)

**파일**: `src/graph/workflow.py:216-241`

- `cancel_event.set()` 후 `task.cancel()` 호출하지만, 취소된 태스크의 LLM API 호출이 완료될 때까지 대기하지 않음
- CRISIS 발생 시 이미 진행 중인 Emotion/Content/Reasoning의 LLM 호출이 응답까지 진행 → 불필요한 토큰 비용

### C-4. _bedrock_semaphore 초기화 경합 (위험도: 🟡 낮음)

**파일**: `src/agents/shared/llm_client.py:295-297`

- C-1과 동일한 check-then-act 패턴. Semaphore가 2개 생성되어 concurrency_limit 우회 가능
- asyncio 싱글 스레드 특성으로 실제 확률은 극히 낮음

---

## 6. 잠재 이슈 — 보안

### SEC-1. 프롬프트 인젝션 방어 사각지대 (위험도: 🟠 중간)

**파일**: `src/agents/shared/input_sanitizer.py`, 각 에이전트 프롬프트 삽입 부분

**현황**:
- `detect_injection()`은 라우트 레벨(`src/api/routes/podcasts.py:282-284`)에서만 호출
- 감지 시 `safety_flags`에 표시만 할 뿐 **입력 자체를 정제하지 않음**
- 실제 에이전트에서는 원본 `user_input`이 그대로 프롬프트에 삽입:
  - `safety.py:63` — `f"사용자 입력 분석 요청:\n{user_input}"`
  - `emotion.py:83` — `f"[사용자 입력]\n{user_input}"`
  - `podcast_reasoning.py:400, 410` — `f"[사용자 입력]\n{user_input}"`
  - `learning.py:78` — `f"[사용자 입력]\n{user_input}"`
- 감지 패턴(6개)은 **영어만** 포함. 한국어 인젝션 패턴 미감지:
  - `이전 지시를 무시해`, `시스템 프롬프트를 보여줘` 등

**잠재 영향**: 프롬프트 인젝션으로 에이전트 행동 조작 또는 시스템 프롬프트 유출 가능. Safety Agent 자체의 프롬프트도 인젝션 대상.

### SEC-2. S3 키 path traversal 방어 부재 (위험도: 🟠 중간)

**파일**: `src/agents/podcast/visualization.py:193-195`

```python
file_name = f"{user_id}_{uuid.uuid4().hex[:8]}.png"
s3_key = f"{upload_prefix}/{file_name}"
```

- `user_id`가 `state.get("user_id", "anonymous")`로 가져오며, 경로 정제 없이 S3 키에 삽입
- `user_id`에 `../` 포함 시 의도치 않은 S3 경로에 파일 저장 가능
- 실제 위험은 user_id 생성 로직(Backend 서버)에 따라 다르나, AI 서버 측 방어 코드 없음

### SEC-3. PII 정제 커버리지 한계 (위험도: 🟡 낮음)

**파일**: `src/agents/shared/output_sanitizer.py`

- 자연어 PII(이름, 주소) 감지 불가 (NER 필요)
- 연속 16자리 카드번호 미감지 (구분자 있는 경우만)
- 한국어 특화 패턴만 포함

---

## 7. 잠재 이슈 — 리소스 관리

### R-1. httpx.AsyncClient 매 호출마다 생성/소멸 (위험도: 🟠 중간)

**파일**: `episode_memory.py` (5곳), `knowledge.py` (6곳) — 총 11곳

```python
async with httpx.AsyncClient() as client:
    r = await client.post(...)
```

- 하나의 요청 처리 중 최대 11개의 HTTP 클라이언트 생성/소멸
- TCP 커넥션 재사용 불가, TLS 핸드셰이크 반복, TIME_WAIT 누적
- **권장**: 모듈/클래스 레벨 공유 httpx.AsyncClient 사용 (connection pooling)

### R-2. boto3 S3/Bedrock 클라이언트 요청마다 생성 (위험도: 🟠 중간)

**파일**: `visualization.py:118-121`, `llm_client.py:292`

- `VisualizationAgent.__init__`에서 `boto3.client("s3")` 생성 → 요청마다 새 인스턴스
- `LLMClient._get_bedrock_client()`에서도 요청마다 생성
- boto3 세션 생성 오버헤드, AWS STS 토큰 캐시 미활용
- **권장**: boto3 Session을 모듈 레벨 또는 FastAPI lifespan에서 초기화하고 공유

### R-3. asyncio.TimeoutError 후 내부 태스크 미취소 (위험도: 🟡 낮음)

**파일**: `src/graph/workflow.py:168-174`

- `tier2_podcast_fan_out`에서 `asyncio.wait_for()` 타임아웃 시 내부 `script_task`/`vis_task`의 명시적 취소 없음
- `wait_for()`가 래핑된 코루틴은 취소하지만, 내부 `create_task()`로 생성된 태스크는 자동 취소 보장 안 됨
- LLM 호출이 백그라운드에서 계속 진행 → 불필요한 토큰 비용 + 메모리 누수

### R-4. Neo4j 드라이버 세션 누수 가능성 (위험도: 🟡 낮음)

**파일**: `src/db/neo4j_client.py:48-51`

- context manager로 `close()` 호출이 보장되지만, `execute_query()` 내부 세션이 별도 관리됨
- 예외 발생 시 세션 정리 순서에 따라 누수 가능 (장기 운영 시 풀 고갈)

---

## 8. 잠재 이슈 — 의존성/배포/CI

### D-1. requirements.txt 버전 핀닝 미비 (위험도: 🔴 높음)

**파일**: `requirements.txt` 전체

모든 의존성이 `>=` (하한만 지정) 형태. lock 파일 없음.

| 패키지 | 현재 선언 | 위험 |
|--------|-----------|------|
| `langgraph>=0.2.0` | 0.3.x breaking change 가능 |
| `langchain-core>=0.3.0` | 0.4.x 내부 API 변경 가능 |
| `anthropic>=0.40.0` | SDK major 변경 가능 |
| `pydantic>=2.0.0` | model_validate 동작 변경 가능 |
| `fastapi>=0.110.0` | 1.0 전환 시 breaking change 가능 |

**권장 조치**: `pip freeze > requirements.lock` 또는 `pip-tools` compile, poetry/pdm 도입 검토.

### D-2. deploy.yml 롤백 전략 부재 (위험도: 🔴 높음)

**파일**: `.github/workflows/deploy.yml`

- `git reset --hard origin/develop` → 항상 최신 develop 덮어쓰기
- Docker 이미지 태그링 없이 latest 사용
- 헬스체크 실패 시 자동 롤백 로직 없음
- `docker image prune -f --filter "until=24h"` → 이전 이미지도 삭제

**권장 조치**: 이미지 태그에 커밋 SHA 사용, 헬스체크 + 자동 롤백, 이전 이미지 2개 보존.

### D-3. deploy.yml Knowledge Agent 시크릿 7개 누락 (위험도: 🟠 중간)

**파일**: `deploy.yml:91-117`

`.env` 생성 시 아래 환경변수가 deploy.yml에 없음:
- `KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT` / `KT_CLOUD_KNOWLEDGE_PARSER_TOKEN`
- `KT_CLOUD_KNOWLEDGE_EMBEDDING_ENDPOINT` / `KT_CLOUD_KNOWLEDGE_EMBEDDING_TOKEN`
- `KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT` / `KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN`
- `PINECONE_INDEX_KNOWLEDGE`

Knowledge Agent 코드(`knowledge.py:42-52`)에서 참조하지만 프로덕션에서 빈 문자열로 폴백.

### D-4. develop 직접 프로덕션 배포 (위험도: 🟠 중간)

**파일**: `deploy.yml:3-5`

```yaml
on:
  push:
    branches:
      - develop
```

develop push만으로 EC2 자동 배포. CLAUDE.md의 브랜치 전략(`main ← PR 머지 (3명 전원 승인 필수)`)과 불일치. main 기반 배포가 아님.

### D-5. Neo4j 포트 외부 노출 (위험도: 🟠 중간)

**파일**: `docker-compose.yml:47-48`

```yaml
ports:
  - "7474:7474"   # HTTP Browser UI
  - "7687:7687"   # Bolt
```

EC2 보안 그룹에서 제한하지 않으면 외부 직접 접근 가능. `127.0.0.1:7474:7474` 또는 포트 제거 권장.

### D-6. CI lint job에서 서드파티 스텁 미설치 (위험도: 🟡 낮음)

**파일**: `ci.yml:62-63`

lint job에서 `requirements-dev.txt`가 아닌 lint 도구만 개별 설치. `ignore_missing_imports = true`로 서드파티 타입 오류 사각지대 존재.

### D-7. CORS 와일드카드 기본값 (위험도: 🟡 낮음)

**파일**: `config/loader.py:292`

```python
origins_str = os.getenv("ALLOWED_ORIGINS", "*")
```

`ALLOWED_ORIGINS` 미설정 시 `*` 허용. deploy.yml에서 시크릿 주입하므로 실제 위험은 미등록 시에만 발생.

### D-8. live 테스트 22개 CI 미실행 (위험도: 🟡 낮음)

`@pytest.mark.live` 마커가 붙은 22개 테스트가 CI에서 제외(`-m 'not live'`). 실제 LLM/외부 서비스 회귀를 CI가 감지 불가. 별도 스케줄 또는 수동 실행 환경 필요.

---

## 9. 잠재 이슈 — 워크플로우/설정 정합성

### W-1. EpisodeMemoryAgent private 메서드 직접 호출 (위험도: 🟠 중간)

**파일**: `src/graph/workflow.py:430`

```python
await agent._save_to_store(memory_text, memory_metadata)
```

`_save_to_store`는 `_` 접두사 private 메서드. 공개 인터페이스를 통하지 않아 EpisodeMemoryAgent 내부 변경 시 워크플로우가 깨질 수 있음.

### W-2. loader.py 폴백 타임아웃과 settings.yaml 실제값 4~8배 괴리 (위험도: 🟠 중간)

| TIER | settings.yaml | loader.py 폴백 | 배율 |
|------|:---:|:---:|:---:|
| TIER 0 | 40초 | 10초 | 4x |
| TIER 1 | 240초 | 30초 | **8x** |
| TIER 2 | 280초 | 140초 | 2x |
| TIER 4 | 40초 | 10초 | 4x |
| 비동기 | 120초 | 30초 | 4x |

settings.yaml 로드 실패 시 폴백값으로 동작하면 대부분의 LLM 호출이 타임아웃됨. 특히 TIER 1 폴백 30초는 Bedrock APAC CRIS 환경에서 단일 호출도 완료 불가.

### W-3. Episode Memory와 Knowledge Agent DI 패턴 비대칭 (위험도: 🟡 낮음)

**파일**: `src/agents/podcast/podcast_reasoning.py:65-73`

```python
self.episode_memory = episode_memory or _get_episode_memory_agent_class()()  # 실제 에이전트
self.knowledge_agent = knowledge_agent or KnowledgeAgentStub()               # Stub
```

- DI 미전달 시: Episode Memory는 실제 구현체(인프라 연결 시도), Knowledge는 Stub(빈 결과)
- 호출 인터페이스도 불일치: Episode Memory `.process(state)` vs Knowledge `.search(query, domain)`

### W-4. 모듈 레벨 설정 캐싱 — 핫 리로드 불가 (위험도: 🟡 낮음)

**파일**: `src/graph/workflow.py:66-76`

```python
_settings = get_settings()
_TIER1_TIMEOUT = _settings.tier1_timeout
```

모듈 import 시점에 설정을 한 번 읽어 캐싱. 런타임 중 settings.yaml 변경 미반영. 테스트 시 `_settings_instance = None` 패치해도 workflow.py 모듈 변수는 업데이트되지 않는 주의점.

### W-5. monitoring 설정 대부분 loader.py에서 미접근 (위험도: 🟡 낮음)

settings.yaml의 `monitoring.langfuse`, `monitoring.metrics`, `monitoring.alerting` 설정이 정의되어 있으나 loader.py에는 `langsmith_tracing_enabled`만 getter 존재. 나머지는 미래 확장용으로 보이나 dead 설정 잠재.

---

## 10. 긍정적 신호

| 항목 | 내용 |
|------|------|
| **테스트 596 passed** | 전체 테스트 안정적, 10초 이내 실행. mypy CI 포함 |
| **AgentState 접근 안전** | 전 에이전트(12개, 64건)가 `state.get()` 패턴 사용. `state["key"]` 직접 접근 0건 |
| **노드 인터페이스 규약 준수** | 전 에이전트가 요청마다 새 인스턴스 생성. 싱글톤 사용 0건 |
| **CRISIS 선점 메커니즘** | asyncio.Event 기반 CRISIS-타임아웃 경합 방지까지 정교하게 구현 |
| **로그 시스템 통일** | PR #112/#113에서 18개 파일 `get_agent_logger()` 통일 (episode_memory.py 제외) |
| **Docker 보안** | 멀티스테이지 빌드, 비root 사용자, .dockerignore 적절 |
| **Bedrock 지연 추적** | LangSmith 메타데이터 + 구간별 로깅으로 가시성 확보 |
| **Graceful shutdown** | 재배포 시 300초 요청 보호 |
| **개발자별 필드 쓰기 권한** | 의도된 예외(Intent Classifier 1차 risk 설정) 외 위반 없음 |

---

## 11. 우선순위별 종합 액션 목록

### 🔴 즉시 (프로덕션 안전/품질 직접 영향)

| # | 항목 | 근거 | 관련 이슈 |
|---|------|------|----------|
| 1 | Safety Agent LLM 실패 시 `warning` 이상으로 변경 | 멘탈케어 서비스에서 fail-safe 원칙 위반 | S-2 |
| 2 | requirements.txt lock 파일 생성 | 재현 불가능 버그 원인 차단 | D-1 |
| 3 | deploy.yml 롤백 메커니즘 추가 | 배포 실패 시 복구 불가 | D-2 |
| 4 | pre-commit hook 설치 | CI lint 반복 커밋 즉시 차단 | 패턴 2-3 |

### 🟠 단기 (1~2주 내 개선)

| # | 항목 | 근거 | 관련 이슈 |
|---|------|------|----------|
| 5 | episode_memory.py `print()` → `get_agent_logger()` 전환 | 로그 통일성 유일 예외 | S-4 |
| 6 | Batch Validator `decision` 코드 결정 hybrid 방식 | LLM hallucination 원천 차단 | S-3 |
| 7 | Visualization — Bedrock Structured Outputs 전환 | JSON 파싱 실패 근본 해결 | 패턴 2-1 |
| 8 | S3 Presigned URL 또는 CloudFront OAC 전환 | ACL 의존 제거 | 패턴 2-4 |
| 9 | deploy.yml Knowledge Agent 시크릿 7개 추가 | 프로덕션 KnowledgeAgent 미동작 | D-3 |
| 10 | 프롬프트 인젝션 한국어 패턴 추가 + 입력 정제 적용 | 보안 사각지대 해소 | SEC-1 |
| 11 | S3 키 user_id 경로 정제 | path traversal 방어 | SEC-2 |
| 12 | httpx.AsyncClient 공유 인스턴스 전환 | 커넥션 풀링 성능 개선 | R-1 |
| 13 | StoriesStore TTL 기반 자동 정리 | 장기 운영 메모리 누수 방지 | C-2 |
| 14 | data/cache/ 디렉토리 생성 (.gitkeep) | 런타임 에러 방지 | S-7 |
| 15 | loader.py 폴백 타임아웃 현실화 | settings.yaml 미로드 시 전체 장애 방지 | W-2 |

### 🟡 중기 (프로젝트 완성도)

| # | 항목 | 근거 | 관련 이슈 |
|---|------|------|----------|
| 16 | KnowledgeAgent embedding DI 연결 | RAG 핵심 기능 활성화 | S-1 |
| 17 | Bedrock sonnet_37 복구 기준 + Global CRIS 전환 | APAC 지연 재발 대응 | 패턴 2-5 |
| 18 | develop → main 기반 배포 전환 | 브랜치 전략과 배포 일치 | D-4 |
| 19 | Neo4j 포트 바인딩 제한 | 외부 노출 차단 | D-5 |
| 20 | CLAUDE.md 문서-코드 불일치 해소 | 설계 문서 신뢰성 | S-8 |
| 21 | test_knowledge.py coroutine 경고 수정 | 비동기 테스트 신뢰성 | S-6 |
| 22 | boto3 클라이언트 공유 인스턴스 전환 | AWS 세션 오버헤드 제거 | R-2 |
| 23 | workflow.py _save_to_store 공개 인터페이스 전환 | 캡슐화 복원 | W-1 |

### 📋 장기/합의 필요

| # | 항목 | 근거 |
|---|------|------|
| 24 | TODO(backend) 22건 해소 | 백엔드 팀 일정 협의 |
| 25 | Git history 민감정보 제거 (Plan #28) | 3인 합의 후 실행 |
| 26 | Script Personalizer empathetic/rational 비즈니스 규칙 | 기획 정의 선행 필요 |
| 27 | 보안 키 로테이션 5건 | 인프라팀 협력 |

---

*이 보고서는 코드 수정 없이 조사/분석만 수행한 결과물입니다.*  
*마지막 업데이트: 2026-04-15 — 구조적 점검 보고서 v1*

# 독스트링 품질 개선 구현 계획서

**버전**: v2  
**작성일**: 2026-04-07 11:10  
**최종수정**: 2026-04-07 11:35 (4-에이전트 3차 코드 점검 반영)  
**브랜치**: `feature/reasoning-docs-quality`  
**담당**: 개발자2 (feature/reasoning-* 도메인)  
**근거 문서**: `IMPLEMENTATION_ROADMAP.md` v3, `PLAN_INDEX.md` v3

---

## v1 → v2 변경 사유 (4-에이전트 3차 코드 점검)

| 발견 에이전트 | 문제 | 심각도 | 수정 내용 |
|-------------|------|--------|----------|
| C | Phase 1 경로 오류: `/api/episodes/stream` → 실제 절대경로 `/api/podcasts/episodes/stream` | 🔴 HIGH | Phase 1 변경 후 문구 수정 |
| B | Phase 3 Args에 `iteration_count` 누락 (state.get() 호출 코드 확인됨) | 🟡 MEDIUM | Phase 3 Args 보강 |
| A | Phase 2 Returns에 `safety_flags` 내부 필드 설명 부족 | 🟡 MEDIUM | Phase 2 Returns 보강 |
| D | Phase 4 검증에 `test_compile_conversation_raises_error()` 보존 확인 누락 | 🟡 MEDIUM | Phase 4 검증 보강 |
| C | `StreamEvent` 클래스가 실제 SSE 구현에서 미사용 (podcasts.py는 raw dict 사용) | 🟡 MEDIUM | Phase 1 배경 보강 |
| B | 기존 docstring의 `next_step` 출력 기술이 틀렸음 — 테스트(line 321)로 증명 | ✅ 계획서 v1 정확, 추가 근거 반영 |

---

## 개요

4-에이전트 2차 교차 검증으로 확인된 실제 미완료 항목 4개를 구현한다.  
**모든 변경은 docstring/주석/디렉토리에 한정하며, 실행 로직을 변경하지 않는다.**

---

## 구현 대상 요약

| Phase | 파일 | 변경 유형 | 범위 |
|-------|------|----------|------|
| 1 | `src/api/external_schemas.py` | docstring 텍스트 수정 | 3줄 → 1줄 |
| 2 | `src/agents/podcast/safety.py` | docstring Google-style 확장 | 1개 메서드 |
| 3 | `src/agents/podcast/batch_validator.py` | docstring 형식 변환 | 1개 메서드 |
| 4 | `src/agents/conversation/` | 빈 디렉토리 삭제 | 디렉토리 1개 |

**의존관계**: Phase 1~3은 상호 독립. Phase 4는 마지막에 실행.  
**테스트 목표**: 각 Phase 후 `pytest tests/ -v` 통과 (444 passed, 14 skipped)

---

## Phase 1: external_schemas.py 경로 오류 수정

### 배경

`StreamEvent` 클래스 docstring이 대화모드 제거(PR #45) 이전 경로를 그대로 가리키고 있다.

**실제 엔드포인트 확인** (3차 점검):
- `src/api/routes/podcasts.py:381`: `@router.post("/episodes/stream")`
- `main.py:202`: `app.include_router(podcasts.router, prefix="/api/podcasts", ...)`
- 절대경로: `POST /api/podcasts/episodes/stream`
- HTTP 메서드: POST (GET이 아님)

**추가 발견**: `StreamEvent`는 정의만 있고 실제 SSE 구현(`podcasts.py`)은 raw dict를 사용한다.  
WebSocket 엔드포인트는 코드에 존재하지 않는다.

### 대상 파일

`src/api/external_schemas.py`

### 변경 전 (line 683-685)

```python
    사용법:
        SSE: GET /api/conversations/stream?session_id=...
        WS:  ws://api/ws/conversations?session_id=...
```

### 변경 후

```python
    사용법:
        SSE: POST /api/podcasts/episodes/stream (Content-Type: application/json)
```

> WS 줄 제거 이유: WebSocket 엔드포인트 미구현.  
> GET → POST 수정 이유: 실제 엔드포인트가 `@router.post()` 데코레이터 사용.  
> 경로 수정: conversations → podcasts/episodes (라우터 마운트 경로 반영).

### 검증

```bash
pytest tests/ -v
# 기대: 444 passed, 14 skipped (docstring만 수정이므로 테스트 수 불변)
```

### 커밋

```
docs: StreamEvent 사용법 경로 수정 (GET conversations→POST podcasts/episodes)
```

---

## Phase 2: safety.py process() Google-style 독스트링

### 배경

`SafetyAgent.process()`가 한 줄 요약만 있고 Args/Returns/Raises가 없다.  
프로젝트 내 모든 에이전트(`EmotionAgent`, `ContentAnalyzerAgent`, `IntentClassifierAgent` 등)가  
Google-style을 준수하는데 `SafetyAgent`만 미준수 상태다.

### 대상 파일

`src/agents/podcast/safety.py`

### 참조: BaseAgent.process() 스타일 (base_agent.py:351-363)

```python
@abstractmethod
async def process(self, state: AgentState) -> dict[str, Any]:
    """
    에이전트 핵심 로직.

    자기 담당 필드만 포함한 dict를 반환한다.

    Args:
        state: 현재 AgentState (전체 상태 읽기 가능)

    Returns:
        업데이트할 필드만 포함한 dict
    """
```

### 변경 전 (line 24-25)

```python
    async def process(self, state: AgentState) -> dict[str, Any]:
        """안전성 판정 및 시스템 상수 결합 로직을 수행한다."""
```

### 변경 후

```python
    async def process(self, state: AgentState) -> dict[str, Any]:
        """안전성 판정 및 시스템 상수 결합 로직을 수행한다.

        user_input과 intent의 risk_flag를 기반으로 LLM에 위험도 평가를 요청한다.
        CRISIS/warning 판정 시 SAFETY_MESSAGES 상수를 required_in_script 최상단에 결합한다
        (법적/임상 안내 문구 우선 배치).

        Args:
            state: 현재 AgentState. 참조 필드:
                - user_input (str): 사용자 입력 텍스트.
                - intent (dict): Intent Classifier 결과.
                  flags.risk_flag만 추출 (1차 위기 감지 여부).

        Returns:
            변경된 필드만 포함한 dict:
                - safety_flags (dict): LLM 평가 전체 결과
                  (status, risk_level, risk_score, reasons, required_in_script 포함).
                  CRISIS/warning 시 required_in_script[0]은 SAFETY_MESSAGES 고정 문구.
                - risk_level (int): 위험 레벨 (0–4).
                - risk_score (float): 위험 점수 (0.0–1.0).
                - next_step (str): crisis 판정 시에만 포함. 값: "crisis_response".

        Raises:
            없음. LLM 호출 실패 시 status="safe" fallback 결과를 반환한다
            (safety_flags.error="llm_call_failed" 포함, required_in_script 미설정).
        """
```

### 주의사항

- `line 26` 이하 기존 코드는 **일절 변경하지 않는다**.
- 기존 한 줄 docstring을 멀티라인으로 **교체**하는 것이 전부다.

### 검증

```bash
pytest tests/agents/podcast/test_safety.py -v
pytest tests/ -v
# 기대: 444 passed, 14 skipped
```

### 커밋

```
docs: SafetyAgent.process() Google-style 독스트링 보강
```

---

## Phase 3: batch_validator.py process() Google-style 독스트링

### 배경

`BatchValidatorAgent.process()`가 커스텀 `입력:/출력:` 형식을 사용하고 있다.  
프로젝트 표준인 Google-style(base_agent.py 기준)로 통일한다.

**3차 점검에서 발견된 기존 docstring 오류**:
- `출력: next_step: 다음 단계 라우팅 ("script_personalizer" 또는 "retry_script")` — **사실과 다름**
- `process()`의 모든 return 문에서 `next_step`을 반환하지 않음 (코드 전수 확인)
- 테스트 `test_batch_validator.py:321`: `assert "next_step" not in result` — 명시적 계약
- 라우팅은 `workflow.py`의 `route_after_tier3_podcast()`가 `validation_result.verdict`를 읽어 처리

**3차 점검에서 발견된 누락 입력 필드**:
- `iteration_count`: `state.get("iteration_count", 0)` 사용하지만 기존 docstring에 없음
- 재시도 가능 여부 판단에 사용 (`iteration_count < self.max_retries`)

### 대상 파일

`src/agents/podcast/batch_validator.py`

### 변경 전 (line 43-57)

```python
    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        스크립트 품질을 검증하고 통과 여부를 결정한다.

        입력 (모두 TIER 1/2 결과 — TIER 3이므로 참조 정당):
            - script_draft: Script Generator(TIER 2)가 생성한 스크립트
            - content_analysis: Content Analyzer(TIER 1) 분석 결과
            - reasoning_result: Podcast Reasoning(TIER 1) 추론 결과
            - safety_flags: Safety Agent(TIER 1) 안전 플래그
            - emotion_vectors: Emotion Agent(TIER 1) 감정 벡터 — 톤 적합성 판단용

        출력:
            - validation_result: 검증 결과 상세
            - next_step: 다음 단계 라우팅 ("script_personalizer" 또는 "retry_script")
        """
```

### 변경 후

```python
    async def process(self, state: AgentState) -> dict[str, Any]:
        """스크립트 품질을 검증하고 통과 여부를 결정한다.

        TIER 1/2 결과를 조합해 LLM에 스크립트 품질 검증을 요청하고,
        approve/revise/escalate 판정에 따라 verdict를 설정한다.
        라우팅 결정은 workflow.py의 route_after_tier3_podcast()가 verdict를 읽어 처리한다.

        Args:
            state: 현재 AgentState. 참조 필드 (모두 TIER 1/2 결과):
                - script_draft (dict): Script Generator(TIER 2)가 생성한 스크립트.
                - content_analysis (dict): Content Analyzer(TIER 1) 분석 결과.
                - reasoning_result (dict): Podcast Reasoning(TIER 1) 추론 결과.
                - safety_flags (dict): Safety Agent(TIER 1) 안전 플래그.
                - emotion_vectors (dict): Emotion Agent(TIER 1) 감정 벡터.
                - iteration_count (int): 현재 재시도 횟수 (기본값 0).
                  max_retries 초과 시 강제 통과(forced_pass) 처리에 사용.

        Returns:
            변경된 필드만 포함한 dict:
                - validation_result (dict): 검증 결과 상세.
                  - verdict (str): "PASS" | "FAIL" | "CRITICAL_FAIL".
                  - overall_score (float): 종합 품질 점수.
                  - action (dict): LLM 판정 결과 (decision: approve|revise|escalate).
                  - forced_pass (bool): iteration_count 초과 시만 포함.

        Raises:
            없음. LLM 호출 실패 시 verdict="FAIL" 결과를 반환한다.
        """
```

> **변경 범위**: 기존 docstring 블록(line 44-57)을 위 내용으로 **전체 교체**한다.  
> `line 58` 이하 코드는 **일절 변경하지 않는다**.

### 검증

```bash
pytest tests/agents/podcast/test_batch_validator.py -v
# test_batch_validator.py:321의 `assert "next_step" not in result` 통과 확인
pytest tests/ -v
# 기대: 444 passed, 14 skipped
```

### 커밋

```
docs: BatchValidatorAgent.process() Google-style 독스트링 통일
```

---

## Phase 4: src/agents/conversation/ 빈 디렉토리 제거

### 배경

대화모드 제거(PR #45) 후 소스 파일은 삭제됐으나 `__pycache__`가 남아 디렉토리가 잔존한다.

**3차 점검 확인 사항**:
- 디렉토리 내용: `__pycache__/` 만 존재 (Python 소스 파일 없음)
- 코드베이스 전체에서 `from src.agents.conversation` import 없음
- `workflow.py`에 conversation 노드 미등록
- `compile_graph("conversation")` 호출 시 ValueError 발생 — 의도된 설계

**보존 필수 테스트** (삭제해서는 안 됨):  
`tests/monitoring/test_streaming.py:test_compile_conversation_raises_error()`  
→ conversation 제거가 올바르게 유지되는지 지속 검증하는 테스트

### 실행 명령

```bash
rm -rf src/agents/conversation/
```

### 검증

```bash
# 1. 디렉토리 삭제 확인
ls src/agents/conversation/ 2>/dev/null || echo "삭제 완료"

# 2. import 잔재 없음 확인
grep -r "from src.agents.conversation" src/ tests/ || echo "import 없음"
grep -r "agents\.conversation" src/ tests/ || echo "참조 없음"

# 3. conversation 제거 테스트 통과 확인 (이 테스트는 반드시 PASS여야 함)
pytest tests/monitoring/test_streaming.py::test_compile_conversation_raises_error -v

# 4. 전체 테스트
pytest tests/ -v
# 기대: 444 passed, 14 skipped
```

### 커밋

```
chore: src/agents/conversation/ 빈 디렉토리 제거 (대화모드 제거 잔재)
```

---

## 전체 실행 순서

```
Phase 1 → 검증 → 커밋
Phase 2 → 검증 → 커밋
Phase 3 → 검증 → 커밋
Phase 4 → 검증 → 커밋
→ 최종 전체 테스트 → push
```

각 Phase는 **상호 독립**이므로 실패해도 다른 Phase에 영향 없음.  
각 Phase 후 반드시 `pytest tests/ -v` 통과를 확인한 뒤 커밋한다.  
모든 커밋에 Co-Authored-By **미포함**.

### 최종 푸시

```bash
git push origin feature/reasoning-docs-quality
```

---

## 최종 테스트 기준

```bash
pytest tests/ -v
```

| 항목 | 기대값 |
|------|--------|
| passed | 444 |
| skipped | 14 |
| failed | 0 |
| error | 0 |

---

## PR 양식

**제목**: `docs: 독스트링 품질 개선 + 빈 디렉토리 제거`  
**Base**: `develop` | **Compare**: `feature/reasoning-docs-quality`

```markdown
## 개요

4-에이전트 3차 코드 점검 후 최종 확정된 미완료 항목 4개 처리.
로직 변경 없음 — docstring/주석/디렉토리만 변경.

## 변경 내역

| Phase | 파일 | 내용 |
|-------|------|------|
| 1 | `src/api/external_schemas.py` | StreamEvent docstring 경로 수정 (GET conversations→POST podcasts/episodes) |
| 2 | `src/agents/podcast/safety.py` | process() Google-style 독스트링 보강 (Args/Returns/Raises) |
| 3 | `src/agents/podcast/batch_validator.py` | process() Google-style 독스트링 통일 (iteration_count 추가, next_step 오류 수정) |
| 4 | `src/agents/conversation/` | 빈 디렉토리 제거 (__pycache__만 존재) |

## 테스트 결과

```
444 passed, 14 skipped
```

## 로직 변경 없음 확인

- external_schemas.py: docstring 텍스트만 수정 (기능 없음)
- safety.py: 한 줄 docstring → 멀티라인 확장, 코드 불변
- batch_validator.py: 커스텀 형식 → Google-style 변환 + 잘못된 next_step 기술 수정, 코드 불변
- conversation/: __pycache__만 있던 빈 디렉토리 삭제

## 참고 문서

- `docs/superpowers/PLAN_INDEX.md` v3
- `docs/superpowers/IMPLEMENTATION_ROADMAP.md` v3
- `docs/superpowers/plans/2026-04-07-docs-quality-implementation.md` v2
```

---

## 범위 외 항목 (이 PR에서 처리하지 않음)

| 항목 | 이유 |
|------|------|
| Circuit Breaker 상태 전환 테스트 | 선택적 작업, 별도 PR |
| SSE /episodes/stream 테스트 | 선택적 작업, 별도 PR |
| StreamEvent → podcasts.py 실제 통합 | 기능 변경, 이 PR 범위 초과 |
| Stub 에이전트 실제 DI 연결 | Pinecone 연동 선행 필요 |
| 보안 키 로테이션 6건 | 수동 조치, 코드 PR 없음 |
| Bedrock EC2 벤치마크 | 인프라 협력 필요 |

---

*계획서 v2 — 2026-04-07 11:35*  
*v1 → v2: 4-에이전트 3차 코드 점검 반영 (경로 오류, iteration_count 누락, safety_flags 내부 구조, Phase 4 검증 보강)*

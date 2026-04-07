# 독스트링 품질 개선 구현 계획서

**버전**: v1  
**작성일**: 2026-04-07 11:10  
**브랜치**: `feature/reasoning-docs-quality`  
**담당**: 개발자2 (feature/reasoning-* 도메인)  
**근거 문서**: `IMPLEMENTATION_ROADMAP.md` v3, `PLAN_INDEX.md` v3

---

## 개요

4-에이전트 2차 교차 검증으로 확인된 실제 미완료 항목 4개를 구현한다.  
**모든 변경은 docstring/주석/디렉토리에 한정하며, 실행 로직을 변경하지 않는다.**

---

## 구현 대상 요약

| Phase | 파일 | 변경 유형 | 범위 |
|-------|------|----------|------|
| 1 | `src/api/external_schemas.py` | docstring 텍스트 수정 | 2줄 |
| 2 | `src/agents/podcast/safety.py` | docstring Google-style 확장 | 1개 메서드 |
| 3 | `src/agents/podcast/batch_validator.py` | docstring 형식 변환 | 1개 메서드 |
| 4 | `src/agents/conversation/` | 빈 디렉토리 삭제 | 디렉토리 1개 |

**의존관계**: Phase 1~3은 상호 독립. Phase 4는 마지막에 실행.  
**테스트 목표**: 각 Phase 후 `pytest tests/ -v` 통과 (444 passed, 14 skipped)

---

## Phase 1: external_schemas.py 경로 오류 수정

### 배경

`StreamEvent` 클래스 docstring이 대화모드 제거(PR #45) 이전 경로를 그대로 가리키고 있다.  
실제 엔드포인트는 `POST /api/v1/episodes/stream` (PR #48, `podcasts.py:381`)이다.

### 대상 파일

`src/api/external_schemas.py`

### 변경 전/후

**변경 전 (line 683-685):**
```python
    사용법:
        SSE: GET /api/v1/conversations/stream?session_id=...
        WS:  ws://api/v1/ws/conversations?session_id=...
```

**변경 후:**
```python
    사용법:
        SSE: POST /api/v1/episodes/stream (Content-Type: application/json)
```

> WebSocket 줄 제거 이유: WS 엔드포인트는 미구현 상태. 없는 엔드포인트를 docstring에 명시하면 혼란을 초래함.

### 검증

```bash
pytest tests/ -v
# 기대: 444 passed, 14 skipped (변경 없어야 함 — docstring만 수정)
```

### 커밋

```
docs: StreamEvent 사용법 경로 수정 (conversations→episodes)
```

---

## Phase 2: safety.py process() Google-style 독스트링

### 배경

`SafetyAgent.process()`가 한 줄 요약만 있고 Args/Returns/Raises가 없다.  
`BaseAgent.process()` (추상 메서드, `base_agent.py:351-363`)의 Google-style을 상속 구현체도 동일하게 따라야 한다.

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

        user_input과 intent의 risk_flag를 기반으로 LLM에 위험도 평가를 요청하고,
        CRISIS/warning 판정 시 SAFETY_MESSAGES 상수를 required_in_script에 결합한다.

        Args:
            state: 현재 AgentState. 참조 필드:
                - user_input (str): 사용자 입력 텍스트.
                - intent (dict): Intent Classifier 결과
                  (flags.risk_flag — 1차 위기 감지 여부).

        Returns:
            변경된 필드만 포함한 dict:
                - safety_flags (dict): LLM 평가 전체 결과.
                - risk_level (int): 위험 레벨 (0–4).
                - risk_score (float): 위험 점수 (0.0–1.0).
                - next_step (str): crisis 판정 시에만 포함 ("crisis_response").

        Raises:
            없음. LLM 호출 실패 시 safe fallback 결과를 반환한다.
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
        approve/revise/escalate 판정에 따라 라우팅 값을 결정한다.

        Args:
            state: 현재 AgentState. 참조 필드 (모두 TIER 1/2 결과):
                - script_draft (dict): Script Generator(TIER 2)가 생성한 스크립트.
                - content_analysis (dict): Content Analyzer(TIER 1) 분석 결과.
                - reasoning_result (dict): Podcast Reasoning(TIER 1) 추론 결과.
                - safety_flags (dict): Safety Agent(TIER 1) 안전 플래그.
                - emotion_vectors (dict): Emotion Agent(TIER 1) 감정 벡터.

        Returns:
            변경된 필드만 포함한 dict:
                - validation_result (dict): 검증 결과 상세
                  (verdict: "PASS"|"FAIL"|"CRITICAL_FAIL", overall_score, action 등).

        Raises:
            없음. LLM 호출 실패 시 FAIL verdict 결과를 반환한다.
        """
```

> **변경 범위**: 기존 docstring 블록(line 44-57)을 위 내용으로 **전체 교체**한다.  
> `line 58` 이하 코드는 **일절 변경하지 않는다**.

> **next_step 필드 제거 이유**: 실제 `process()`의 반환 dict에 `next_step`이 포함되지 않는다  
> (코드 확인: line 115-116, 125-128 반환값 모두 `validation_result`만 반환).  
> 라우팅은 `workflow.py`의 `route_after_tier3_podcast()`가 `validation_result.verdict`를 읽어 결정한다.

### 검증

```bash
pytest tests/agents/podcast/test_batch_validator.py -v
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
디렉토리 내 파일:
- `__pycache__/intent_classifier.cpython-312.pyc`
- `__pycache__/__init__.cpython-312.pyc`

소스 파일이 없으므로 `__pycache__`도 유효하지 않다.

### 실행 명령

```bash
rm -rf src/agents/conversation/
```

### 검증

```bash
# 디렉토리 삭제 확인
ls src/agents/conversation/ 2>/dev/null || echo "삭제 완료"

# import 잔재 여부 확인 (0건이어야 함)
grep -r "from src.agents.conversation" src/ tests/ || echo "import 없음"
grep -r "agents.conversation" src/ tests/ || echo "참조 없음"

# 전체 테스트
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
Phase 1 → 커밋 → Phase 2 → 커밋 → Phase 3 → 커밋 → Phase 4 → 커밋 → 푸시
```

각 Phase는 **독립적**이므로 실패해도 다른 Phase에 영향 없음.  
각 Phase 후 반드시 `pytest tests/ -v` 통과를 확인한 뒤 커밋한다.

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

4-에이전트 2차 교차 검증으로 확인된 실제 미완료 항목 4개 처리.
로직 변경 없음 — docstring/주석/디렉토리만 변경.

## 변경 내역

| Phase | 파일 | 내용 |
|-------|------|------|
| 1 | `src/api/external_schemas.py` | StreamEvent docstring 경로 수정 (conversations→episodes) |
| 2 | `src/agents/podcast/safety.py` | process() Google-style 독스트링 보강 |
| 3 | `src/agents/podcast/batch_validator.py` | process() Google-style 독스트링 통일 |
| 4 | `src/agents/conversation/` | 빈 디렉토리 제거 |

## 테스트 결과

```
444 passed, 14 skipped
```

## 로직 변경 없음 확인

- external_schemas.py: docstring 텍스트만 수정
- safety.py: 한 줄 docstring → 멀티라인 확장, 코드 불변
- batch_validator.py: 커스텀 형식 → Google-style 변환, 코드 불변
- conversation/: __pycache__만 있던 빈 디렉토리 삭제

## 참고 문서

- `docs/superpowers/PLAN_INDEX.md` v3
- `docs/superpowers/IMPLEMENTATION_ROADMAP.md` v3
```

---

## 범위 외 항목 (이 PR에서 처리하지 않음)

| 항목 | 이유 |
|------|------|
| Circuit Breaker 상태 전환 테스트 | 선택적 작업, 별도 PR |
| SSE /episodes/stream 테스트 | 선택적 작업, 별도 PR |
| Stub 에이전트 실제 DI 연결 | Pinecone 연동 선행 필요 |
| 보안 키 로테이션 6건 | 수동 조치, 코드 PR 없음 |
| Bedrock EC2 벤치마크 | 인프라 협력 필요 |

---

*계획서 v1 — 2026-04-07 11:10*  
*이 문서가 구현 명령 전 최종 계획서.*

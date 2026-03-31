# 기여 가이드

Mind-Log 프로젝트에 기여하기 위한 가이드입니다.

---

## 팀 내부 개발자

### 도메인 규칙

각 개발자는 자기 도메인의 에이전트만 구현하며, 다른 도메인 코드를 직접 수정하지 않습니다.

| 개발자 | 담당 파일 경로 |
|--------|---------------|
| 개발자1 | `src/agents/conversation/{intent_classifier,knowledge,synthesis,personalization}.py`, `src/agents/podcast/{script_generator,script_personalizer}.py` |
| 개발자2 | `src/agents/conversation/{safety,memory,visualization,emotion}.py`, `src/agents/podcast/{episode_memory,visualization}.py` |
| 개발자3 | `src/agents/conversation/{reasoning,context,validator,learning}.py`, `src/agents/podcast/{podcast_reasoning,content_analyzer,batch_validator}.py` |
| 미정 | `src/agents/conversation/telemetry.py` (전체 에이전트 완료 후 예정) |

### Protected Files

아래 파일은 3명 전원 합의 후에만 수정할 수 있습니다:

- `src/models/agent_state.py`
- `src/models/message.py`
- `src/api/contracts.py`
- `src/graph/workflow.py`

### Shared Infrastructure — 인터페이스 안정성

아래 파일은 모든 에이전트가 의존하는 공용 코드입니다.
기존 public 메서드의 시그니처(파라미터, 반환 타입)와 동작을 변경하지 마세요.
신규 메서드/함수 추가만 허용됩니다. 수정 후 반드시 `pytest tests/ -v` 통과를 확인하세요.

- `src/agents/shared/base_agent.py` — BaseAgent ABC
- `src/agents/shared/llm_client.py` — LLM 멀티 프로바이더 클라이언트
- `src/agents/shared/prompt_loader.py` — YAML 프롬프트 로더
- `config/loader.py` — Settings 싱글톤

> 상세 규칙: CLAUDE.md "공용 인프라" 참조

### PR 리뷰 규칙

- `feature/* → develop`: 다른 도메인 개발자 최소 1명 리뷰
- `develop → main`: 3명 전원 승인
- Protected Files 포함 PR: 3명 전원 승인

---

## 코드 스타일

- **Python 3.11+**, 타입 힌팅 필수
- **포맷터**: `black .` (자동 포매팅)
- **린터**: `ruff check .` + `mypy src/`
- **정렬**: `isort .` (import 정렬)

### 네이밍 규칙

| 대상 | 규칙 | 예시 |
|------|------|------|
| 에이전트 클래스 | PascalCase | `EmotionAgent` |
| 노드 함수 | snake_case + `_node` | `emotion_node` |
| AgentState 필드 | snake_case | `emotion_vectors` |
| 테스트 파일 | `test_` + 에이전트명 | `test_emotion.py` |

### 에이전트 노드 시그니처

모든 에이전트는 이 시그니처를 따릅니다:

```python
async def {name}_node(state: AgentState) -> dict[str, Any]:
    # 자기 담당 필드만 읽고 쓰기 — 변경된 필드만 dict로 반환
    return {"필드명": 값}
```

---

## 커밋 컨벤션

```
<type>(<scope>): <description>
```

타입: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

상세 스코프 목록은 이 문서의 하단 및 `CLAUDE.md`를 참조하세요.

---

## 테스트 요구사항

- 모든 에이전트는 단위 테스트 필수
- 테스트 파일 위치: `tests/agents/{conversation,podcast}/test_{agent_name}.py`
- PR 제출 전 `pytest tests/ -v` 통과 확인

---

## 외부 기여자

외부 기여는 Fork & PR 방식으로 진행합니다.

```bash
# 1. Fork 후 클론
git clone https://github.com/your-username/mind-log.git
cd mind-log

# 2. upstream 등록
git remote add upstream https://github.com/your-org/mind-log.git

# 3. 기능 브랜치 생성
git checkout -b feature/your-feature

# 4. 작업 후 PR 제출
git push origin feature/your-feature
# GitHub에서 upstream의 develop 브랜치로 PR 생성
```

---

*상세 브랜치 전략은 이 문서, 아키텍처 규칙은 CLAUDE.md를 참조하세요.*

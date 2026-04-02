# 빠른 시작 가이드

Mind-Log 프로젝트 환경 설정부터 첫 에이전트 개발까지의 가이드입니다.

---

## 1. 환경 설정

### 필수 요구사항

- Python 3.11+
- Git
- MySQL (로컬 또는 Docker)

### 저장소 클론 및 초기 설정

```bash
# 저장소 클론
git clone https://github.com/your-org/mind-log.git
cd mind-log

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 아래 정보를 입력:
#   - 기본 프로바이더(Bedrock): AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
#   - 대안 프로바이더: LLM_PROVIDER=anthropic (ANTHROPIC_API_KEY) 또는 LLM_PROVIDER=openai (OPENAI_API_KEY)
#   - DB 접속 정보 (필요 시)
```

### Docker로 서비스 실행 (선택)

```bash
# MySQL + Neo4j 한번에 실행 (docker-compose.yml 필요)
docker compose up -d
```

---

## 2. 프로젝트 이해

### 필수 읽기 문서

| 순서 | 문서 | 내용 |
|------|------|------|
| 1 | CLAUDE.md | 아키텍처 요약, 협업 규칙, 브랜치 전략, API 규약 |
| 2 | docs/guides/AGENT_DEV_GUIDE.md | 에이전트 개발 템플릿, 테스트 패턴 |
| 3 | docs/guides/INFRA_ZONE_ASSIGNMENT.md | Zone A/B/C/D 작업 영역 분할 |

### 에이전트 설계 문서

에이전트 상세 설계는 `ProjectDocs/` 폴더에 있습니다:

- `ProjectDocs/INDEX.md` — 마스터 인덱스
- `ProjectDocs/ARCHITECTURE_v4.0.md` — v4.0 아키텍처 명세
- `ProjectDocs/agents/podcast/` — 팟캐스트모드 에이전트 상세 문서

---

## 3. 첫 에이전트 개발

> 상세 구현 가이드, 템플릿, 테스트 패턴은 **[에이전트 개발 가이드](AGENT_DEV_GUIDE.md)**를 참조하세요.

### 에이전트 노드 기본 구조

모든 에이전트는 `BaseAgent` ABC를 상속받아 `process()` 메서드를 구현합니다.
변경된 필드만 `dict`로 반환하면 LangGraph가 자동 병합합니다:

```python
# src/agents/podcast/emotion.py 예시

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class EmotionAgent(BaseAgent):
    """Emotion Agent: 사용자 입력의 감정을 분석한다."""

    @property
    def agent_name(self) -> str:
        return "emotion"

    async def process(self, state: AgentState) -> dict[str, Any]:
        # 1. 입력 읽기 (자기 담당 읽기 필드만)
        user_input = state["user_input"]

        # 2. LLM 호출 (BaseAgent가 제공하는 call_llm_json 사용)
        result = await self.call_llm_json(user_input)

        # 3. 변경된 필드만 dict로 반환 (LangGraph 자동 병합)
        return {"emotion_vectors": result}


# 노드 함수 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
# 모듈 레벨 싱글톤으로 에이전트를 생성하지 마시오.
async def emotion_node(state: AgentState) -> dict[str, Any]:
    agent = EmotionAgent()
    return await agent(state)
```

### 개발 절차

```bash
# 1. develop에서 기능 브랜치 생성
git checkout develop
git pull origin develop
git checkout -b feature/analysis-emotion-agent

# 2. 에이전트 구현
# src/agents/podcast/emotion.py 작성

# 3. 테스트 작성
# tests/agents/podcast/test_emotion.py 작성

# 4. 테스트 실행
pytest tests/agents/podcast/test_emotion.py -v

# 5. 린트 확인
black src/agents/podcast/emotion.py
ruff check src/agents/podcast/emotion.py

# 6. 커밋 및 PR
git add src/agents/podcast/emotion.py tests/agents/podcast/test_emotion.py
git commit -m "feat(emotion): Emotion Agent 감정 벡터 분석 구현"
git push origin feature/analysis-emotion-agent
# GitHub에서 PR 생성
```

---

## 4. 개발자별 시작점

### 개발자1 (브랜치: feature/analysis-*)

담당 에이전트: `Intent Classifier`, `Knowledge`, `Synthesis`, `Personalization` / `Script Generator`, `Script Personalizer`

참고 문서:
- `ProjectDocs/agents/podcast/01_intent_classifier.md`
- `ProjectDocs/agents/podcast/06_knowledge.md`
- `ProjectDocs/agents/podcast/08_synthesis.md`
- `ProjectDocs/agents/podcast/10_personalization.md`
- `ProjectDocs/agents/podcast/04_script_generator.md`

### 개발자2 (브랜치: feature/reasoning-*)

담당 에이전트: `Safety`, `Memory`, `Visualization`, `Emotion` / `Episode Memory`, `Visualization(Podcast)`

참고 문서:
- `ProjectDocs/agents/podcast/02_safety.md`
- `ProjectDocs/agents/podcast/05_memory.md`
- `ProjectDocs/agents/podcast/11_visualization.md`
- `ProjectDocs/agents/podcast/03_emotion.md`
- `ProjectDocs/agents/podcast/02_episode_memory.md`

### 개발자3 (브랜치: feature/validation-*)

담당 에이전트: `Reasoning`, `Context`, `Validator`, `Learning` / `Podcast Reasoning`, `Content Analyzer`, `Batch Validator`

참고 문서:
- `ProjectDocs/agents/podcast/07_reasoning.md`
- `ProjectDocs/agents/podcast/04_context.md`
- `ProjectDocs/agents/podcast/09_validator.md`
- `ProjectDocs/agents/podcast/13_learning.md`
- `ProjectDocs/agents/podcast/03_podcast_reasoning.md`
- `ProjectDocs/agents/podcast/01_content_analyzer.md`
- `ProjectDocs/agents/podcast/05_batch_validator.md`

---

## 5. 프롬프트 시스템

에이전트의 시스템 프롬프트는 코드 안에 하드코딩하지 않고 **YAML 파일로 외부 관리**합니다.
`PromptLoader`가 YAML 로드, 멀티버전 지원, A/B 테스트를 처리합니다.

```
prompts/
├── podcast/                 # 팟캐스트모드 에이전트 프롬프트
│   ├── content_analyzer.yaml
│   ├── podcast_reasoning.yaml
│   └── batch_validator.yaml
└── shared/                  # 공용 에이전트 프롬프트
    └── learning.yaml
```

- 프롬프트 버전은 `config/settings.yaml`에서 중앙 통제합니다
- BaseAgent가 자동으로 프롬프트를 로드하므로 에이전트 코드에서 직접 로드할 필요 없습니다
- 상세 내용은 `src/agents/shared/prompt_loader.py`를 참조하세요

---

## 6. 로컬 LLM 개발 (Ollama)

API 키 없이 로컬에서 에이전트를 테스트하려면 **Ollama**를 사용할 수 있습니다.
Ollama 관련 코드는 `dev/` 폴더에 격리되어 있으며 `.gitignore`로 git push에서 제외됩니다.

```bash
# 빠른 시작
ollama pull qwen2.5:7b       # 한국어 성능 우수
ollama serve
echo "LLM_PROVIDER=ollama" >> .env
```

종합 설정 가이드: `docs/getting-started/OLLAMA_SETUP.md`

---

## 7. 라이브 LLM 테스트

`dev/live_tests/`에서 실제 LLM을 호출하여 에이전트 동작을 검증할 수 있습니다.
Ollama(기본), Anthropic API, AWS Bedrock 모든 프로바이더를 지원합니다.

```bash
# 단일 에이전트 테스트
python3 -m dev.live_tests.run_live --agent content_analyzer

# 전체 에이전트 순차 실행
python3 -m dev.live_tests.run_live --all

# Anthropic API 사용
python3 -m dev.live_tests.run_live --all --provider anthropic
```

상세 사용법: `dev/live_tests/README.md`

---

## 8. 테스트 실행

```bash
# 전체 테스트
pytest tests/ -v

# 특정 에이전트 테스트
pytest tests/agents/podcast/test_emotion.py -v

# 통합 테스트
pytest tests/integration/ -v

# 커버리지 포함
pytest tests/ --cov=src --cov-report=html
```

---

*자세한 협업 규칙과 API 규약은 CLAUDE.md를 참조하세요.*

*마지막 업데이트: 2026-03-13*

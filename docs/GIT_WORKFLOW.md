# Git 워크플로우 가이드

Mind-Log 프로젝트의 3인 개발자 협업을 위한 Git 브랜치 전략, 커밋 컨벤션, PR 프로세스를 정의합니다.

---

## 브랜치 전략

```
main ← PR 머지 (3명 전원 승인 필수)
 └── develop ← 통합 테스트 브랜치 (최소 1명 리뷰)
      ├── feature/analysis-*      (개발자1)
      ├── feature/reasoning-*     (개발자2)
      └── feature/validation-*    (개발자3)
```

### 브랜치 규칙

- `main`: 프로덕션 배포 브랜치. PR 머지 시 3명 전원 승인 필수.
- `develop`: 통합 테스트 브랜치. 각 도메인 브랜치에서 머지. 최소 1명 리뷰 필수.
- `feature/analysis-*`: 개발자1 전용. Intent Classifier, Knowledge, Synthesis, Personalization, Script Generator, Script Personalizer.
- `feature/reasoning-*`: 개발자2 전용. Safety, Memory, Visualization, Emotion, Episode Memory, Visualization(Podcast).
- `feature/validation-*`: 개발자3 전용. Reasoning, Context, Validator, Learning, Podcast Reasoning, Content Analyzer, Batch Validator.
- `fix/*`: 버그 수정. 도메인 접두사 포함 권장 (예: `fix/analysis-intent-null-check`)
- `hotfix/*`: 긴급 수정. main에서 분기 후 직접 main에 머지.

### 브랜치 네이밍 예시

```
feature/analysis-intent-classifier    # 개발자1: Intent Classifier 구현
feature/analysis-knowledge-rag        # 개발자1: Knowledge Agent RAG 구현
feature/reasoning-safety-crisis       # 개발자2: Safety Agent 위기 대응
feature/reasoning-memory-agent        # 개발자2: Memory Agent 구현
feature/validation-reasoning          # 개발자3: Reasoning Agent 구현
feature/validation-batch-validator    # 개발자3: Batch Validator 구현
```

---

## 커밋 컨벤션

### 커밋 메시지 형식

```
<type>(<scope>): <description>

[optional body]
```

### 타입

| 타입 | 설명 |
|------|------|
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `test` | 테스트 추가/수정 |
| `docs` | 문서 수정 |
| `chore` | 빌드, 설정 등 기타 변경 |

### 스코프

| 스코프 | 대상 |
|--------|------|
| `intent` | Intent Classifier |
| `safety` | Safety Agent |
| `emotion` | Emotion Agent |
| `context` | Context Agent |
| `memory` | Memory Agent |
| `knowledge` | Knowledge Agent |
| `reasoning` | Reasoning Agent |
| `synthesis` | Synthesis Agent |
| `validator` | Validator Agent |
| `personal` | Personalization Agent |
| `visual` | Visualization Agent |
| `telemetry` | Telemetry Agent |
| `learning` | Learning Agent |
| `podcast` | 팟캐스트모드 전체 |
| `content` | Content Analyzer |
| `episode` | Episode Memory |
| `script` | Script Generator |
| `batch` | Batch Validator |
| `graph` | LangGraph 워크플로우 |
| `api` | 백엔드 API |
| `models` | 공유 모델 |

### 커밋 예시

```
feat(intent): Intent Classifier TIER 0 구현
feat(safety): CRISIS 메시지 선점 처리 로직 추가
fix(emotion): 감정 벡터 정규화 오류 수정
refactor(synthesis): LLM 프롬프트 템플릿 분리
test(validator): 품질 점수 검증 단위 테스트 추가
docs(models): AgentState 필드 설명 업데이트
```

---

## PR (Pull Request) 프로세스

### 1단계: feature → develop

```bash
# 작업 완료 후
git push origin feature/analysis-intent-classifier

# GitHub에서 PR 생성
# Base: develop ← Compare: feature/analysis-intent-classifier
```

**리뷰 규칙:**
- 최소 1명의 다른 도메인 개발자 리뷰 필수
- CI 테스트 통과 필수
- 린트 (Black, Ruff) 통과 필수

### 2단계: develop → main

```bash
# develop에서 통합 테스트 완료 후
# GitHub에서 PR 생성
# Base: main ← Compare: develop
```

**리뷰 규칙:**
- 3명 전원 승인 필수
- 통합 테스트 전체 통과 필수
- Protected Files 변경 시 특별 검토

### Protected Files 수정 시

아래 파일 수정이 포함된 PR은 **반드시 3명 전원 리뷰 및 승인**이 필요합니다:

- `src/models/agent_state.py`
- `src/models/message.py`
- `src/api/contracts.py`
- `src/graph/workflow.py`

---

## 충돌 해결

### 자기 도메인 파일

각 개발자가 자기 도메인 파일만 수정하므로 일반적으로 충돌이 발생하지 않습니다.

### 공유 파일 충돌

Protected Files에서 충돌이 발생한 경우:
1. 팀 슬랙/디스코드에서 충돌 내용 공유
2. 3명이 함께 충돌 해결 방안 합의
3. 한 명이 대표로 충돌 해결 후 커밋
4. 나머지 2명이 결과 확인 후 승인

---

## 일반 작업 흐름

```bash
# 1. develop 최신화
git checkout develop
git pull origin develop

# 2. 기능 브랜치 생성
git checkout -b feature/analysis-emotion-agent

# 3. 작업 및 커밋
git add src/agents/conversation/emotion.py
git commit -m "feat(emotion): Emotion Agent 감정 벡터 분석 구현"

# 4. 푸시
git push origin feature/analysis-emotion-agent

# 5. GitHub에서 PR 생성 (develop ← feature/analysis-emotion-agent)
```

---

*상세 협업 규칙은 CLAUDE.md를 참조하세요.*

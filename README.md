# Mind-Log

초개인화 AI 멘탈케어 & 시각화 플랫폼

사용자의 감정과 생각을 AI가 분석하여 개인화된 멘탈케어 서비스를 제공하고, 내면 상태를 시각적 이미지로 표현합니다.

---

## 듀얼모드 아키텍처

Mind-Log는 두 가지 모드를 지원하는 멀티에이전트 시스템입니다.

| 항목 | 대화모드 | 팟캐스트모드 |
|-----|---------|------------|
| 에이전트 | 13개 전용 | 7개 전용 |
| 처리 방식 | 실시간 스트리밍 | 배치 처리 |
| 출력 형식 | 자유로운 텍스트 | 구조화된 스크립트 |
| 응답 시간 | ~5-10초 | ~18-20초 |

### TIER 기반 파이프라인

```
TIER 0: Intent Classifier → 의도 분류 + 모드 감지
TIER 1 (병렬 Fan-out): Safety + Emotion + Context/ContentAnalyzer + Reasoning/PodcastReasoning
TIER 2 (생성): Synthesis / Script Generator (+Visualization 병렬)
TIER 3 (검증): Validator / Batch Validator (실패 시 TIER 2 재시도, 최대 2회)
TIER 4 (후처리): Personalization / Script Personalizer
비동기: Visualization + Telemetry + Learning
```

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| LLM | Anthropic Claude (Opus 4.6, Sonnet 4, Haiku) / AWS Bedrock |
| 오케스트레이션 | LangGraph StateGraph |
| 벡터 DB | Pinecone |
| 관계형 DB | MySQL |
| 그래프 DB | Neo4j |
| 캐시 | Redis |
| 이미지 저장 | S3 / CDN |
| 프레임워크 | FastAPI + Uvicorn |
| CI/CD | GitHub Actions |

---

## 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/your-org/mind-log.git
cd mind-log

# 2. 가상환경 생성
python -m venv .venv
source .venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 5. 테스트 실행
pytest tests/
```

---

## 프로젝트 구조

```
mind-log/
├── src/
│   ├── agents/           # 에이전트 구현
│   │   ├── conversation/ # 대화모드 에이전트 (13개)
│   │   ├── podcast/      # 팟캐스트모드 에이전트 (7개)
│   │   └── shared/       # 공용 에이전트 유틸리티
│   ├── models/           # AgentState, AgentMessage 스키마
│   ├── api/              # 백엔드 API 클라이언트
│   ├── graph/            # LangGraph 워크플로우 정의
│   └── utils/            # 공통 유틸리티
├── config/               # 환경 설정 파일
├── tests/                # 테스트 코드
├── docs/                 # 프로젝트 문서
└── CLAUDE.md             # AI 개발 가이드 (아키텍처 + 협업 규칙)
```

---

## 문서 안내

| 문서 | 설명 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 아키텍처 + 협업 규칙 + API 규약 통합 가이드 |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | 폴더 구조 및 파일 역할 상세 |
| [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) | 브랜치 전략, 커밋 컨벤션, PR 가이드 |
| [docs/QUICK_START.md](docs/QUICK_START.md) | 환경 설정 및 첫 에이전트 개발 가이드 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 기여 가이드 및 코드 리뷰 규칙 |

---

## 팀 구성

| 개발자 | 대화모드 에이전트 | 팟캐스트모드 에이전트 |
|--------|-----------------|---------------------|
| 개발자1 | Intent Classifier, Knowledge, Synthesis, Personalization | Script Generator, Script Personalizer |
| 개발자2 | Safety, Memory, Visualization, Emotion | Episode Memory, Visualization(Podcast) |
| 개발자3 | Reasoning, Context, Validator, Learning | Podcast Reasoning, Content Analyzer, Batch Validator |
| 미정 | Telemetry Agent | — (전체 에이전트 완료 후 예정) |

---

## 라이선스

MIT License

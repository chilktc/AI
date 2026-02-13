# 라이브 LLM 테스트 — 개별 에이전트 실제 LLM 호출 스모크 테스트

> **이 폴더는 `dev/` 하위에 위치한 로컬 개발 전용 테스트입니다.**

## 개요

기존 210개 운영 테스트는 LLM 호출을 mock하여 파싱/로직/상태 전파만 검증한다.
이 라이브 테스트는 **실제 LLM을 호출**하여 다음을 확인한다:

- 프롬프트가 의도한 JSON 구조를 반환하는지
- 한국어 응답이 올바르게 생성되는지
- 에이전트의 후처리(검증, 보정, 클램핑)가 실제 LLM 응답에서도 작동하는지
- TIER 1 → TIER 3 → 비동기 상태 전파가 올바른지

**자동 pass/fail이 아닌 사람이 결과를 눈으로 확인하는 스모크 테스트**이다.

## 지원 프로바이더

| 프로바이더 | 설정 방법 | 사전 조건 | 기본값 |
|-----------|---------|----------|--------|
| **Ollama** | `--provider ollama` 또는 미지정 | `ollama serve` 실행 + 모델 다운로드 | **기본값** |
| **Anthropic** | `--provider anthropic` | `ANTHROPIC_API_KEY` 환경변수 | |
| **Bedrock** | `--provider bedrock` | AWS IAM 인증 (환경변수 또는 IAM Role) | |

**프로바이더 선택 우선순위:**
1. CLI `--provider` 옵션
2. 환경변수 `LLM_PROVIDER`
3. 기본값 `ollama`

## 빠른 시작

### 1. Ollama 사전 준비 (기본 프로바이더)

```bash
# Ollama 설치 (https://ollama.com)
brew install ollama          # macOS
# 또는 https://ollama.com    # Windows/Linux

# 모델 다운로드
ollama pull llama3.2         # sonnet 대체 (범용)
ollama pull gemma2:2b        # haiku 대체 (경량)

# 서버 시작
ollama serve

# 연결 확인
curl http://localhost:11434/v1/models
```

### 2. 단일 에이전트 테스트

```bash
# Content Analyzer (TIER 1)
python3 -m dev.live_tests.run_live --agent content_analyzer

# Podcast Reasoning (TIER 1 — GoT/ToT/CoT 추론 파이프라인)
python3 -m dev.live_tests.run_live --agent podcast_reasoning

# Batch Validator (TIER 3 — 스크립트 품질 검증)
python3 -m dev.live_tests.run_live --agent batch_validator

# Learning Agent (비동기 — 패턴 학습)
python3 -m dev.live_tests.run_live --agent learning
```

### 3. 전체 에이전트 순차 실행

```bash
python3 -m dev.live_tests.run_live --all
```

4개 에이전트를 순차적으로 실행하고 전체 요약(성공/실패 수, 소요 시간)을 출력한다.

### 4. 파이프라인 시뮬레이션

```bash
python3 -m dev.live_tests.run_live --pipeline
```

LangGraph 없이 수동으로 에이전트를 체이닝하여 전체 흐름을 검증한다:

```
TIER 1: Content Analyzer → Podcast Reasoning (실제 LLM)
    ↓
TIER 2: Mock Script Generator (개발자1 미구현 — 고정 데이터)
    ↓
TIER 3: Batch Validator (실제 LLM)
    ↓
비동기: Learning Agent (실제 LLM + BackendClient mock)
```

## 다른 프로바이더로 실행

### Anthropic API 직접 호출

```bash
# 사전 조건: API 키 설정
export ANTHROPIC_API_KEY=sk-ant-api03-...

# 단일 에이전트
python3 -m dev.live_tests.run_live --agent content_analyzer --provider anthropic

# 전체 에이전트
python3 -m dev.live_tests.run_live --all --provider anthropic

# 파이프라인 시뮬레이션
python3 -m dev.live_tests.run_live --pipeline --provider anthropic
```

### AWS Bedrock

```bash
# 사전 조건: AWS 인증 설정
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=ap-northeast-2

# 또는 IAM Role 사용 (EC2/ECS 환경)

# 인증 확인
aws sts get-caller-identity

# 실행
python3 -m dev.live_tests.run_live --agent content_analyzer --provider bedrock
python3 -m dev.live_tests.run_live --pipeline --provider bedrock
```

### 모델 오버라이드

특정 모델을 지정하여 테스트할 수 있다.

```bash
# Ollama — 다른 로컬 모델 사용
python3 -m dev.live_tests.run_live --agent content_analyzer --model mistral:7b
python3 -m dev.live_tests.run_live --agent content_analyzer --model qwen2.5:7b

# Anthropic — 특정 모델 버전 지정
python3 -m dev.live_tests.run_live --agent content_analyzer --provider anthropic --model claude-sonnet-4-20250514

# Bedrock — Bedrock 모델 ID 지정
python3 -m dev.live_tests.run_live --agent content_analyzer --provider bedrock --model anthropic.claude-sonnet-4-5-20250929-v2:0
```

## CLI 옵션 전체 목록

```
python3 -m dev.live_tests.run_live [-h] (--agent {name} | --all | --pipeline)
                                    [--provider {ollama,anthropic,bedrock}]
                                    [--model MODEL]

필수 (하나만 선택):
  --agent {name}    단일 에이전트 테스트 실행
                    name: content_analyzer, podcast_reasoning,
                          batch_validator, learning
  --all             4개 에이전트 전부 순차 실행
  --pipeline        파이프라인 시뮬레이션 (TIER 1→2→3→비동기)

선택:
  --provider {p}    LLM 프로바이더 (기본값: ollama)
                    p: ollama, anthropic, bedrock
  --model MODEL     모델 오버라이드
                    Ollama: mistral:7b, qwen2.5:7b 등
                    Anthropic: claude-sonnet-4-20250514 등
                    Bedrock: anthropic.claude-sonnet-4-5-20250929-v2:0 등
  -h, --help        도움말 출력
```

## 파일 구조

```
dev/live_tests/
├── __init__.py                        # 패키지 초기화
├── README.md                          # 이 파일
├── conftest_live.py                   # 공통 인프라: 프로바이더 셋업, 헬스체크, 출력 포맷팅
├── fixtures.py                        # 현실적인 한국어 AgentState 테스트 데이터
├── run_live.py                        # CLI 러너 (argparse — 멀티 프로바이더 지원)
├── test_content_analyzer_live.py      # Content Analyzer 라이브 테스트
├── test_podcast_reasoning_live.py     # Podcast Reasoning 라이브 테스트
├── test_batch_validator_live.py       # Batch Validator 라이브 테스트
├── test_learning_live.py              # Learning Agent 라이브 테스트
└── test_pipeline_live.py              # 파이프라인 시뮬레이션 (TIER 1→3→비동기)
```

### 각 파일의 역할

| 파일 | 역할 |
|------|------|
| `conftest_live.py` | `setup_provider()` — 프로바이더별 환경 설정 (Settings 싱글톤 리셋, Ollama 등록, API 키 확인, AWS 인증) |
| | `check_provider_health()` — 프로바이더별 연결 상태 확인 |
| | `print_result()` / `print_error()` — 컬러 포맷팅 결과 출력 |
| | `Timer` — 소요 시간 측정 컨텍스트 매니저 |
| `fixtures.py` | `make_content_analyzer_state()` — TIER 1 입력 (직장 스트레스 주제) |
| | `make_podcast_reasoning_state()` — TIER 1 입력 (불면증/수면 위생 주제) |
| | `make_batch_validator_state()` — TIER 3 입력 (전체 앞단 결과 포함) |
| | `make_learning_state()` — 전체 파이프라인 완료 상태 |
| | `make_pipeline_initial_state()` — 파이프라인 시뮬레이션 초기 입력 (자존감 주제) |
| | `generate_mock_script()` — 개발자1 Script Generator 출력 시뮬레이션 |

## 에이전트별 확인 항목

### Content Analyzer (TIER 1)

- LLM 1회 호출 (`call_llm_json`)
- 반환 필드: `content_analysis`
- 확인: `main_theme`, `sub_themes`, `episode_type`, `depth_level`, `target_duration`, `narrative_structure` 존재 여부
- 후처리: `target_duration` 3~5분 범위 클램핑, `sub_themes` 3~5개 제한

### Podcast Reasoning (TIER 1)

- LLM 1~3회 (complexity에 따라 GoT/ToT/CoT 조합)
- 입력 complexity=0.7 → "standard" 깊이 → ToT + CoT (LLM 2회)
- 반환 필드: `reasoning_result`
- 확인: `episode_structure`, `narrative_flow`, `key_points`, `emotional_journey`, `confidence`, `reasoning_strategy`, `reasoning_depth`
- 추론 깊이: GoT 결과 미포함, ToT 결과 포함 확인

### Batch Validator (TIER 3)

- LLM 1회 호출 (`call_llm_json`)
- 반환 필드: `validation_result`, `next_step`, (실패 시 `iteration_count`)
- 확인: `passed`, `overall_score` 존재 여부
- 라우팅: 통과 시 `next_step="script_personalizer"`, 실패 시 `next_step="retry_script"`

### Learning Agent (비동기)

- LLM 1회 호출 (`call_llm_json`)
- `BackendClient.save()`는 mock 처리
- 반환: 빈 dict (AgentState 변경 없음)
- 확인: `BackendClient.save()` 호출 여부, 저장 데이터 구조

### 파이프라인 시뮬레이션

- 전체 흐름: Content Analyzer → Podcast Reasoning → Mock Script → Batch Validator → Learning
- 각 단계별 소요 시간 출력
- 상태 필드 전파 확인 (7개 필드)

## Mock Script Generator에 대해

파이프라인 시뮬레이션에서 TIER 2 Script Generator는 **mock으로 처리**한다.

- **이유**: Script Generator는 **개발자1 담당**이며 아직 코드(`src/agents/podcast/script_generator.py`)와 프롬프트(`prompts/podcast/script_generator.yaml`)가 구현되지 않았다.
- **동작**: `fixtures.py`의 `generate_mock_script(state)` 함수가 Content Analyzer와 Podcast Reasoning의 출력을 참조하여 현실적인 `script_draft` 구조를 반환한다.
- **교체 시점**: 개발자1이 Script Generator를 완성하면, `generate_mock_script()` 호출을 실제 `ScriptGeneratorAgent()(state)` 호출로 교체한다.

## 트러블슈팅

### Ollama 서버 연결 실패

```
[ERROR] Ollama 서버 연결 실패.
  `ollama serve`를 실행하세요.
```

**해결:**
```bash
ollama serve                             # 서버 시작
curl http://localhost:11434/v1/models    # 연결 확인
ollama list                              # 다운로드된 모델 확인
```

### Ollama JSON 파싱 실패

로컬 모델이 JSON 형식을 올바르게 반환하지 못하는 경우:

**해결:**
- `temperature`를 낮춘다 (0.1~0.3 권장)
- JSON 안정성이 높은 모델 사용: `mistral:7b`, `qwen2.5:7b`
- `--model` 옵션으로 다른 모델 시도

### Anthropic API 키 오류

```
[ERROR] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.
```

**해결:**
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

### AWS Bedrock 인증 실패

```
[ERROR] AWS 인증 실패.
```

**해결:**
```bash
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=ap-northeast-2
aws sts get-caller-identity    # 인증 확인
```

### 테스트가 너무 느림 (Ollama)

로컬 모델 추론은 GPU/CPU 성능에 따라 10~120초 소요될 수 있다.

**해결:**
- 경량 모델 사용: `gemma2:2b` (1.6GB)
- `ollama_config.yaml`의 `timeout` 값 확인 (기본 120초)
- GPU 가속 확인: `ollama ps` 명령어로 GPU 사용 여부 확인

### Anthropic API 비용

테스트 1회당 Sonnet 4 모델 기준:
- 단일 에이전트: 약 $0.01~0.05
- `--all` (4개 에이전트): 약 $0.05~0.25
- `--pipeline`: 약 $0.10~0.30

## 추천 모델

| 용도 | Ollama 모델 | 크기 | 비고 |
|------|------------|------|------|
| 빠른 테스트 | `gemma2:2b` | 1.6GB | haiku 대체, 빠르지만 JSON 불안정 가능 |
| 범용 개발 | `llama3.2` | 2.0GB | sonnet 대체, 기본 권장 |
| JSON 안정 | `mistral:7b` | 4.1GB | JSON 형식 출력이 안정적 |
| 한국어 | `qwen2.5:7b` | 4.7GB | 한국어 응답 품질 우수 |
| 고품질 추론 | `llama3.1:8b` | 4.7GB | 복잡한 추론 작업에 적합 |

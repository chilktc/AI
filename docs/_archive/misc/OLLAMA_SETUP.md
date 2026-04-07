# Ollama 로컬 LLM 설정 가이드

> **⚠️ DEPRECATED**: Round 4(2026-03-06) 이후 프로덕션 LLM은 Bedrock/OpenAI로 전환되었습니다.
> 이 가이드는 초기 로컬 개발용 참고 자료로만 보존됩니다.
> 최신 테스트 결과는 `docs/reports/OLLAMA_MODEL_TEST_REPORT.md`를 참조하세요.

## 1. 개요

### Ollama란?

[Ollama](https://ollama.com)는 로컬 환경에서 대형 언어 모델(LLM)을 실행할 수 있는 오픈소스 도구이다. HuggingFace의 오픈소스 모델이나 Ollama 라이브러리의 모델을 다운로드하여 API 키 없이 LLM을 호출할 수 있다.

### Mind-Log에서의 역할

- **용도**: 로컬 개발/테스트 전용
- **목적**: API 키 없이 에이전트의 LLM 호출 흐름과 결과 파싱을 검증
- **위치**: `dev/` 폴더에 격리 (운영 배포 시 삭제로 완전 제거)
- **운영 영향**: 없음 — `dev/` 폴더 삭제로 완전 제거 가능

### 분리 구조

```
프로젝트 루트/
├── src/agents/shared/llm_client.py   # 운영 코드 — register_provider() 플러그인만 추가
├── config/settings.yaml              # 운영 설정 — 변경 없음
│
├── dev/                              # ← 로컬 개발 전용 (운영 배포 시 삭제)
│   ├── ollama_provider.py            # Ollama 프로바이더 구현
│   ├── ollama_config.yaml            # Ollama 전용 설정 (모델 매핑, URL, 타임아웃)
│   ├── ollama_bootstrap.py           # LLMClient에 Ollama 프로바이더 등록
│   ├── test_ollama.py                # Ollama 전용 테스트
│   └── README.md                     # 빠른 시작 가이드
│
└── .env                              # LLM_PROVIDER=ollama (git 제외)
```

---

## 2. Ollama 설치

### macOS

```bash
# Homebrew
brew install ollama

# 또는 공식 설치 파일
# https://ollama.com/download/mac
```

### Windows

1. [https://ollama.com/download/windows](https://ollama.com/download/windows)에서 설치 파일 다운로드
2. 설치 후 시스템 트레이에서 Ollama 아이콘 확인
3. PowerShell에서 `ollama --version`으로 설치 확인

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 설치 확인

```bash
ollama --version
# ollama version 0.x.x
```

---

## 3. 모델 다운로드

```bash
# 범용 개발 (sonnet 대체)
ollama pull llama3.2

# 경량 빠른 테스트 (haiku 대체)
ollama pull gemma2:2b

# 선택적 — JSON 안정성이 필요한 경우
ollama pull mistral:7b

# 선택적 — 한국어 성능이 필요한 경우
ollama pull qwen2.5:7b
```

### 다운로드 확인

```bash
ollama list
# NAME              ID          SIZE    MODIFIED
# llama3.2:latest   ...         2.0 GB  ...
# gemma2:2b         ...         1.6 GB  ...
```

---

## 4. dev/ 폴더 설정

`dev/` 폴더는 로컬 개발 전용이다. 프로젝트 클론 시 자동으로 포함된다.

### 4.1. 이미 dev/ 폴더가 있는 경우

설정 파일만 커스터마이즈:

```bash
# dev/ollama_config.yaml 수정
vi dev/ollama_config.yaml
```

### 4.2. dev/ 폴더가 없는 경우

다른 개발자의 로컬 환경에서 `dev/` 폴더를 복사하거나, 이 저장소의 초기 셋업 시 자동 생성되는 파일을 사용한다.

### 4.3. ollama_config.yaml 설정

```yaml
ollama:
  base_url: "http://localhost:11434"  # Ollama 서버 URL
  timeout: 120                         # 타임아웃 (초)

  models:
    haiku: "gpt-oss:20b"      # Learning Agent, Intent Classifier 등
    sonnet: "gpt-oss:20b"     # Content Analyzer, Batch Validator 등
    opus: "gpt-oss:20b"       # Reasoning Agent 등 고급 모델
```

> **참고**: Mind-Log는 한국어 기반 프로젝트이므로 `qwen2.5` 계열 모델을 권장합니다.
> 현재 `dev/ollama_config.yaml`의 기본 매핑은 `gpt-oss:20b`이며, 한국어 성능 우선 시 `qwen2.5:14b`(sonnet/opus) + `qwen2.5:7b`(haiku)로 변경을 권장합니다 (상세: `docs/reports/OLLAMA_MODEL_TEST_REPORT.md` 섹션 7.2).
>
> **운영 기본 프로바이더 (Round 4 이후)**: OpenAI `gpt-4o-mini`가 기본입니다. Ollama는 로컬 개발/오프라인 테스트용으로 유지됩니다.

### 4.4. .env 설정

```bash
# .env 파일에 추가 (.env는 .gitignore에 포함)
LLM_PROVIDER=ollama
```

환경변수로 개별 설정을 오버라이드할 수도 있다:

```bash
OLLAMA_BASE_URL=http://localhost:11434   # 서버 URL
OLLAMA_TIMEOUT=120                        # 타임아웃 (초)
```

---

## 5. 사용법

### 5.1. Ollama 서버 시작

```bash
ollama serve
# Listening on 127.0.0.1:11434
```

### 5.2. 프로바이더 등록 (앱 시작 시)

```python
# main.py 또는 앱 시작 스크립트에서
import os
if os.getenv("LLM_PROVIDER") == "ollama":
    from dev.ollama_bootstrap import register_ollama
    register_ollama()
```

### 5.3. 테스트 실행

```bash
# Ollama 프로바이더 단위 테스트 (서버 불필요 — mock 사용)
python3 -m pytest dev/test_ollama.py -v

# 기존 운영 테스트 전체 실행 (Ollama 무관)
python3 -m pytest tests/ -v

# Ollama로 전체 에이전트 테스트 (서버 필요)
LLM_PROVIDER=ollama python3 -m pytest tests/ -v
```

### 5.4. CLI에서 직접 테스트

```python
import asyncio
from dev.ollama_bootstrap import register_ollama
from src.agents.shared.llm_client import LLMClient

register_ollama()

async def test():
    client = LLMClient(agent_name="content_analyzer", provider_override="ollama")
    result = await client.generate(
        system_prompt="한국어로 응답하라.",
        user_message="안녕하세요"
    )
    print(f"Result: {result}")

asyncio.run(test())
```

---

## 6. 추천 모델

| 용도 | 모델 | 크기 | VRAM | 비고 |
|------|------|------|------|------|
| 빠른 테스트 | `gemma2:2b` | 1.6GB | 3GB+ | haiku 대체, 속도 우선 |
| 범용 개발 | `llama3.2` | 2.0GB | 4GB+ | sonnet 대체, 균형 |
| JSON 안정 | `mistral:7b` | 4.1GB | 6GB+ | JSON 모드 안정적 |
| 한국어 | `qwen2.5:7b` | 4.7GB | 8GB+ | 한국어 성능 우수 |
| 한국어 경량 | `qwen2.5:3b` | 2.0GB | 4GB+ | 한국어 + 경량 |
| 추론 품질 | `llama3.2:latest` | 2.0GB | 4GB+ | opus 대체 |

### 모델 선택 기준

- **속도 우선**: `gemma2:2b` — 응답 속도가 빠르지만 품질은 낮음
- **JSON 파싱**: `mistral:7b` — JSON 형식 응답이 안정적
- **한국어**: `qwen2.5:7b` — Mind-Log는 한국어 기반이므로 한국어 성능 중요
- **메모리 제한**: `gemma2:2b` 또는 `qwen2.5:3b` — 8GB RAM 미만 환경

---

## 7. IDE 연동

### VS Code

`.env` 파일 설정만으로 자동 적용:

```env
LLM_PROVIDER=ollama
```

`launch.json`에서 환경변수 설정:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Mind-Log (Ollama)",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": ["src.main:app", "--reload"],
            "env": {
                "LLM_PROVIDER": "ollama"
            }
        }
    ]
}
```

### Cursor

Cursor 터미널에서 환경변수 설정:

```bash
# 터미널에서 직접
export LLM_PROVIDER=ollama

# 또는 .env 파일 사용 (Cursor가 자동으로 로드)
echo "LLM_PROVIDER=ollama" >> .env
```

---

## 8. 트러블슈팅

### Ollama 서버 연결 확인

```bash
# 서버 상태 확인
curl http://localhost:11434/v1/models

# 정상 응답 예시:
# {"object":"list","data":[{"id":"llama3.2:latest",...}]}
```

### 포트 충돌

기본 포트(11434)가 이미 사용 중인 경우:

```bash
# 다른 포트로 Ollama 실행
OLLAMA_HOST=0.0.0.0:8080 ollama serve

# 설정에서 URL 변경
# dev/ollama_config.yaml
ollama:
  base_url: "http://localhost:8080"

# 또는 환경변수
OLLAMA_BASE_URL=http://localhost:8080
```

### 메모리 부족

```bash
# 더 작은 모델 사용
ollama pull gemma2:2b    # 1.6GB
ollama pull qwen2.5:3b   # 2.0GB

# dev/ollama_config.yaml에서 모델 변경
ollama:
  models:
    sonnet: "gemma2:2b"   # 경량 모델로 대체
```

### JSON 파싱 실패

로컬 모델은 JSON 형식을 정확히 따르지 못할 수 있다.

**자동 대응 (코드 레벨):** `LLMClient.generate_json()`은 `json.loads(raw, strict=False)`를 사용하여 로컬 모델이 생성하는 제어 문자(`\n`, `\t` 등)를 자동 허용한다. 대부분의 경우 추가 설정 없이 파싱이 성공한다.

**추가 대응 (설정 레벨):**

```yaml
# temperature를 낮추면 JSON 안정성 향상
# config/settings.yaml (에이전트별 temperature 조절)
agents:
  content_analyzer:
    temperature: 0.1   # 기본 0.7 → 0.1로 낮춤

# 또는 JSON에 강한 모델 사용
ollama:
  models:
    sonnet: "mistral:7b"  # JSON 모드가 안정적
```

### 모델 다운로드 느림

```bash
# 백그라운드에서 다운로드
nohup ollama pull llama3.2 &

# 다운로드 진행률 확인
ollama list
```

---

## 9. 제한사항 및 주의

### 프로덕션 사용 금지

- Ollama는 **로컬 개발/테스트 전용**이다
- 운영 서버에서는 반드시 Anthropic API 또는 AWS Bedrock을 사용한다
- `dev/` 폴더를 운영 서버에 배포하지 않는다

### git 분리

- `dev/` 폴더는 운영 배포 시 삭제로 완전히 제거할 수 있다
- `dev/` 설정은 git으로 공유되므로 프로젝트 클론 시 자동으로 포함된다
- `docs/getting-started/OLLAMA_SETUP.md`(이 문서)는 git에 포함되므로 모든 개발자가 참고 가능

### 모델별 차이

- 로컬 모델은 Anthropic Claude 대비 품질이 낮다
- JSON 형식 응답이 불안정할 수 있다 (temperature 조절 권장)
- 한국어 지원은 모델에 따라 크게 다르다 (`qwen2.5` 계열 권장)
- 토큰 제한이 다를 수 있다 (컨텍스트 윈도우 확인 필요)

### 완전 제거 방법

```bash
# 1. dev/ 폴더 삭제
rm -rf dev/

# 2. .env에서 LLM_PROVIDER=ollama 제거
# 3. 운영 테스트 통과 확인
python3 -m pytest tests/ -v
```

---

---

## 10. 라이브 LLM 테스트

`dev/live_tests/`에서 개별 에이전트를 실제 LLM으로 호출하여 동작을 검증할 수 있다.
Ollama, Anthropic API, AWS Bedrock 모든 프로바이더를 지원한다.

```bash
# Ollama 기본 — 단일 에이전트
python3 -m dev.live_tests.run_live --agent content_analyzer

# 전체 에이전트 순차 실행
python3 -m dev.live_tests.run_live --all

# 파이프라인 시뮬레이션 (TIER 1→2→3→비동기)
python3 -m dev.live_tests.run_live --pipeline
```

상세 사용법은 `dev/live_tests/README.md`를 참조하세요.

---

*마지막 업데이트: 2026-04-07*

# dev/ — 로컬 개발 전용 디렉토리

> **이 폴더는 로컬 개발 전용입니다.**
> 운영 배포 시 이 폴더를 삭제하면 완전히 제거됩니다.

## Ollama 로컬 LLM 프로바이더

### 빠른 시작

```bash
# 1. Ollama 설치 (https://ollama.com)
brew install ollama          # macOS
# 또는 https://ollama.com    # Windows/Linux

# 2. 모델 다운로드
ollama pull llama3.2         # 범용 (sonnet 대체)
ollama pull gemma2:2b        # 경량 (haiku 대체)

# 3. Ollama 서버 시작
ollama serve

# 4. .env 파일에 추가
echo "LLM_PROVIDER=ollama" >> .env

# 5. 테스트 실행
python3 -m pytest dev/test_ollama.py -v
```

### 파일 구조

| 파일 | 설명 |
|------|------|
| `ollama_provider.py` | Ollama OpenAI 호환 API 프로바이더 클래스 |
| `ollama_config.yaml` | 모델 매핑, 서버 URL, 타임아웃 설정 |
| `ollama_bootstrap.py` | LLMClient에 Ollama 프로바이더 등록/해제 |
| `test_ollama.py` | Ollama 프로바이더 단위 테스트 |
| `README.md` | 이 파일 |

### 상세 가이드

종합 설정 가이드는 `docs/OLLAMA_SETUP.md`를 참고하세요.

---

## 라이브 LLM 테스트 (`live_tests/`)

개별 에이전트를 **실제 LLM으로 호출**하여 동작을 검증하는 스모크 테스트 스위트.
Ollama(기본), Anthropic API, AWS Bedrock 모든 프로바이더를 지원한다.

### 빠른 시작

```bash
# Ollama 기본 — 단일 에이전트
python3 -m dev.live_tests.run_live --agent content_analyzer

# 전체 에이전트 순차 실행
python3 -m dev.live_tests.run_live --all

# 파이프라인 시뮬레이션 (TIER 1→2→3→비동기)
python3 -m dev.live_tests.run_live --pipeline

# Anthropic API 사용
python3 -m dev.live_tests.run_live --all --provider anthropic

# AWS Bedrock 사용
python3 -m dev.live_tests.run_live --pipeline --provider bedrock
```

### 상세 문서

전체 사용법, CLI 옵션, 프로바이더별 설정, 트러블슈팅은 `live_tests/README.md`를 참고하세요.

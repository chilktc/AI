# 프로젝트 설계 결정 및 변경 이력

> PROJECT_SUMMARY.md에서 추출한 고유 콘텐츠. 프로젝트 설계 결정과 초반 계획 대비 변경 사항을 기록한다.
> 최종 업데이트: 2026-04-14 11:00

---

## 1. LLM 호출 방식 — 듀얼 아키텍처

두 가지 방식으로 LLM을 호출할 수 있으며, 설정으로 전환 가능하도록 설계한다.

### 방식 A: 외부 API 직접 호출 (Anthropic SDK)

```
에이전트 → LLMClient → Anthropic SDK → Claude API (api.anthropic.com)
```

- 현재 구현된 방식 (`src/agents/shared/llm_client.py`)
- `ANTHROPIC_API_KEY` 환경변수 필요
- 장점: 간단한 설정, 빠른 개발
- 단점: API 키 관리, 요금 직접 처리

### 방식 B: AWS Bedrock 경유

```
에이전트 → LLMClient → boto3 Bedrock Runtime → Claude on Bedrock (AWS)
```

- AWS 인프라 내에서 Claude 모델 호출
- IAM Role 기반 인증 (API 키 불필요)
- 장점: AWS 생태계 통합, VPC 내부 호출, IAM 권한 관리, 비용 통합
- 단점: AWS 의존성, 초기 설정 복잡

### 전환 설계 (구현 완료)

```yaml
# config/settings.yaml
llm:
  provider: "anthropic"        # "anthropic" | "bedrock" | "custom"
  anthropic:
    api_key_env: "ANTHROPIC_API_KEY"
  bedrock:
    region: "us-east-1"
    # IAM Role 기반 인증 (별도 키 불필요)
  models:
    haiku: "claude-haiku-4-5-20251001"
    sonnet: "claude-sonnet-4-5-20250929"
    opus: "claude-opus-4-6"
```

```python
# LLMClient에서 provider에 따라 분기 (커스텀 프로바이더 플러그인 지원)
class LLMClient:
    _custom_providers: dict[str, type] = {}  # 외부 프로바이더 레지스트리

    def __init__(self, provider: str, ...):
        if provider in self._custom_providers:
            # 커스텀 프로바이더 (Ollama 등)
            ...
        elif provider == "bedrock":
            self._client = boto3.client("bedrock-runtime", ...)
        else:
            self._client = anthropic.AsyncAnthropic(...)
```

---

## 2. 주요 설계 결정 기록

| # | 결정 | 근거 |
|---|------|------|
| 1 | 팟캐스트모드 우선 구현 | 배치 처리로 파이프라인 검증이 용이 |
| 2 | Orchestrator 제거 | StateGraph + 메시지 프로토콜로 충분, 단순화 |
| 3 | 에피소드 3-5분 | 멘탈케어 마이크로 콘텐츠 최적 소비 시간 |
| 4 | 재시도 최대 2회 | 무한 루프 방지 (CLAUDE.md v4.0) |
| 5 | YAML safe_load 강제 | 임의 코드 실행 방어 |
| 6 | prompts/ 보안 정책 | .gitignore 규칙 유지 + 운영 YAML은 `git add -f`로 추적 (PROMPT_SECURITY.md만 미포함) |
| 7 | complexity 기반 추론 라우팅 | 단순 쿼리의 LLM 비용 절감 |
| 8 | 세션 기반 A/B variant | 동일 세션 내 일관된 경험 보장 |
| 9 | contextvars 사용 | LangGraph 병렬 실행에서 비동기 안전 격리 |
| 10 | DI 패턴 (스텁) | Memory/Knowledge 구현 완료. 스텁은 Pinecone 연결 전까지 폴백으로 유지 |
| 11 | 관계형 DB → MySQL | PostgreSQL에서 MySQL로 변경 |
| 12 | LLM 멀티 프로바이더 | Anthropic SDK + AWS Bedrock + OpenAI + 커스텀(Ollama) 플러그인으로 유연성 확보 |
| 13 | json.loads strict=False | 로컬 LLM(Ollama 등)의 제어 문자 포함 JSON 응답 허용 |
| 14 | dev/ 폴더 격리 | 개발 전용 코드를 .gitignore로 분리, 운영 영향 0 |
| 15 | Neo4j GoT 저장 | 추론 이력 원본을 Neo4j에 저장, RDB는 누적 요약만 담당 (PR #50, #51, #53, #69) |
| 16 | Pinecone RAG 파이프라인 | 벡터 DB 공통 인프라 구축, 인덱스명 하이픈 통일 (PR #64~#68) |
| 17 | 입력/출력 정제 (PII) | 프롬프트 인젝션 방어(InputSanitizer) + PII 마스킹(OutputSanitizer) 이중 방어 (PR #58, #59) |
| 18 | Graph Mode B 단일화 | AI 서버 EMA 계산 제거, Backend UPSERT 단일 흐름으로 확정 (PR #69) |

---

## 3. 향후 로드맵

### 단기 — 팟캐스트 파이프라인 ✅ 완료 (v14~v23)

1. ~~Script Generator 구현 (개발자1)~~ ✅
2. ~~Script Personalizer 구현 (개발자1)~~ ✅
3. ~~Episode Memory 실제 구현 (개발자2)~~ ✅
4. ~~Knowledge Agent 실제 구현 (개발자1)~~ ✅
5. ~~LangGraph Workflow 통합 (3인 합의)~~ ✅

### 중기 (팟캐스트모드 완성 + 대화모드 삭제) — 완료

6. ~~Intent Classifier~~ ✅, ~~Safety~~ ✅, ~~Emotion~~ ✅ — 구현 완료 (팟캐스트 공용)
7. ~~Content Analyzer~~ ✅, ~~Podcast Reasoning~~ ✅, ~~Episode Memory~~ ✅, ~~Knowledge~~ ✅ — 팟캐스트 모드 구현 완료
8. ~~Batch Validator~~ ✅, ~~Script Personalizer~~ ✅ — 팟캐스트 모드 구현 완료
9. ~~대화모드 에이전트 (Context, Synthesis 등)~~ ✅ 삭제 완료 (PR #45, #48, #49, #61) — 팟캐스트모드 단일 집중으로 결정

### 장기 (플랫폼 완성)

10. ~~Visualization Agent~~ ✅ — 구현 완료
11. Telemetry 실시간 모니터링 (담당자 결정 후) — ⏳
12. 프론트엔드 연동 (FastAPI + WebSocket) — ⏳
14. 프로덕션 배포 + A/B 테스트 실전 운영

---

## 4. 초반 계획서 대비 변경 사항

프로젝트 초반 계획(CLAUDE.md, v1~v5 문서)과 현재 실제 구현 사이에 발생한 차이점을 정리한다.

### 4.1 팀 역할 배분 변경

초반 CLAUDE.md에는 **도메인 기반(Dev-A/B/C)**으로 기록되어 있으나, 실제로는 **에이전트 기반**으로 배분이 이루어졌다.

| 구분 | 초반 계획 (CLAUDE.md) | 실제 확정 |
|------|---------------------|----------|
| **명칭** | Dev-A / Dev-B / Dev-C | 개발자1 / 개발자2 / 개발자3 |
| **분류 기준** | 도메인 (분석/추론/검증) | 에이전트 단위 (도메인 혼합) |
| Intent Classifier | Dev-A (분석) | 개발자1 |
| Emotion | Dev-A (분석) | **개발자2** |
| Context | Dev-A (분석) | **개발자3** |
| Content Analyzer | Dev-A (분석) | **개발자3** (Context의 팟캐스트 대응) |
| Reasoning | Dev-B (추론) | **개발자3** |
| Memory | Dev-B (추론) | **개발자2** |
| Knowledge | Dev-B (추론) | **개발자1** |
| Synthesis | Dev-B (추론) | **개발자1** |
| Safety | Dev-C (검증) | **개발자2** |
| Validator | Dev-C (검증) | **개발자3** |
| Personalization | Dev-C (검증) | **개발자1** |
| Visualization | Dev-C (검증) | **개발자2** |
| Learning | Dev-C (검증) | **개발자3** |
| Telemetry | Dev-C (검증) | **미정** (전체 완료 후 결정) |

> 볼드체는 초반 계획과 다르게 배정된 항목

### 4.2 기술 스택 변경

| 항목 | 초반 계획 | 현재 |
|------|----------|------|
| 관계형 DB | PostgreSQL | **MySQL** |
| LLM 호출 | Anthropic SDK 직접 호출만 | **멀티: Anthropic SDK + AWS Bedrock + OpenAI + 커스텀(Ollama)** (구현 완료) |

### 4.3 v7/v8 — 초반 계획에 없던 신규 시스템

v7과 v8에서 도입된 기능은 **초반 CLAUDE.md에 전혀 언급되지 않았던** 완전히 새로운 인프라 계층이다.

#### 초반 계획의 가정

- 프롬프트는 Python 코드 내에 하드코딩
- 버전 관리 없음 (단일 프롬프트)
- A/B 테스트 미고려
- 환경별(dev/staging/prod) 프롬프트 분리 미고려
- 프롬프트 보안 미고려

#### v7에서 추가된 것 (초반 계획에 없음)

| 항목 | 설명 |
|------|------|
| **PromptLoader 클래스** | 전체 신규 모듈 (`src/agents/shared/prompt_loader.py`, 250+ LOC) |
| **YAML 프롬프트 파일** | `prompts/` 디렉토리 + 4개 YAML 파일 |
| **5계층 보안** | safe_load, 경로 검증, 화이트리스트, 크기 제한, 스키마 검증 |
| **BaseAgent 프롬프트 연동** | `_load_prompts()`, `get_prompt()`, `prompt_version` |
| **환경변수 분리** | `PROMPT_DIR` → dev/staging/prod 프롬프트 전환 |
| **prompts/ .gitignore** | 프롬프트 보안을 위해 리포지토리에서 제외 |
| **PROMPT_SECURITY.md** | 8개 위협 영역 보안 문서 (465줄) |
| **테스트 85개** | 프롬프트 로딩, 보안, 캐시, BaseAgent 연동 검증 |

#### v8에서 추가된 것 (초반 계획에 없음)

| 항목 | 설명 |
|------|------|
| **멀티버전 YAML 형식** | `versions` 키 아래 SemVer별 프롬프트 공존 |
| **settings.yaml 버전 통제** | `prompts.versions.default`, 에이전트별 고정 |
| **A/B 테스트 프레임워크** | variant_a/b, traffic_split, session 기반 결정적 할당 |
| **contextvars 격리** | `_active_ab_variant` ContextVar로 비동기 안전 |
| **BaseAgent A/B 메서드** | `_resolve_ab_variant()`, `_preload_ab_variants()`, `ab_variant` |
| **Settings 확장** | `get_prompt_version()`, `get_ab_test_config()` |
| **테스트 27개 추가** | 멀티버전, A/B, Settings 연동 검증 |

#### 영향받은 파일

| 파일 | 초반 계획 상태 | v7/v8 이후 상태 |
|------|--------------|----------------|
| `src/agents/shared/prompt_loader.py` | **존재하지 않음** | 신규 생성 (250+ LOC) |
| `src/agents/shared/base_agent.py` | 기본 ABC 패턴만 | +200 LOC (프롬프트 로드 + A/B 테스트) |
| `config/loader.py` | 기본 Settings만 | +70 LOC (버전 해석 + A/B 설정) |
| `config/settings.yaml` | LLM/agent 설정만 | +25줄 (prompts.versions, ab_tests) |
| `prompts/*.yaml` | **존재하지 않음** | 4개 파일 신규 생성 |
| `docs/PROMPT_SECURITY.md` | **존재하지 않음** | 465줄 보안 문서 |
| `tests/agents/shared/` | **존재하지 않음** | 57개 테스트 (prompt_loader + versioning) |

### 4.4 AgentState 필드 접근 규칙 차이

초반 계획의 필드 접근 규칙은 도메인 기반(Dev-A/B/C)이었으나, 실제 에이전트 배분이 도메인을 넘나들기 때문에 조정이 필요하다.

| 초반 계획 | 실제 상태 |
|----------|----------|
| Dev-A만 `intent`, `emotion_vectors`, `context` 쓰기 | 개발자1(Intent), 개발자2(Emotion), 개발자3(Context)이 각각 담당 |
| Dev-B만 `memory_results`, `reasoning_result` 쓰기 | 개발자2(Memory), 개발자3(Reasoning)이 각각 담당 |
| Dev-C만 `risk_level`, `validation_result` 쓰기 | 개발자2(Safety), 개발자3(Validator)이 각각 담당 |

> **결론**: 필드 접근 규칙은 "개발자별"이 아닌 "에이전트별"로 관리해야 한다.
> 각 에이전트는 자기 담당 출력 필드만 쓰고, 나머지는 읽기만 하는 원칙은 동일하게 유지.

### 4.5 재시도 횟수 차이

| 항목 | 초반 CLAUDE.md | 실제 구현 |
|------|--------------|----------|
| Validator 피드백 루프 | 최대 **3회** (Phase 4 기술) | 최대 **2회** (v4.0 TIER 아키텍처 명세 + 코드) |

> v4.0 아키텍처 재설계 시 3회 → 2회로 변경됨. 코드(`batch_validator.py`)에서도 2회로 구현되어 있음.

---

*본 문서는 PROJECT_SUMMARY.md에서 고유 콘텐츠만 추출하여 생성되었습니다. (2026-03-17)*

# 변경이력 v7 — 프롬프트 외부 관리 체계 (YAML 외부화 + PromptLoader)

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-12

---

## 배경

### 문제

v6까지 프롬프트가 에이전트 Python 파일 내부에 하드코딩되어 있었다:

- 프롬프트 변경 시 코드 수정 + 재배포 필요
- 프롬프트 버전 추적 불가
- 환경(dev/staging/prod)별 프롬프트 분리 불가
- 민감한 시스템 프롬프트가 소스 코드에 노출
- 프롬프트 이터레이션이 코드 변경과 결합

### 목표

1. 프롬프트를 YAML 파일로 외부화 — 코드 변경 없이 프롬프트 수정 가능
2. `PromptLoader` 도입 — 보안 검증 + 캐싱 + 자동 로딩
3. `BaseAgent` 통합 — 에이전트 생성 시 YAML 프롬프트 자동 로드
4. 환경변수(`PROMPT_DIR`)로 환경별 프롬프트 전환

---

## 변경 내용

### 1. PromptLoader 클래스 (`src/agents/shared/prompt_loader.py`)

YAML 기반 프롬프트 로더로, 5계층 보안 방어를 적용한다:

| 보안 계층 | 방어 내용 |
|----------|----------|
| YAML 파싱 | `yaml.safe_load()` 전용 사용 (코드 실행 방지) |
| 경로 검증 | `Path.resolve()` + `relative_to()` (경로 조작 방지) |
| 디렉토리 화이트리스트 | `prompts`, `prompts_dev`, `prompts_staging`, `prompts_prod`만 허용 |
| 파일 크기 제한 | 100KB 초과 파일 거부 (YAML Bomb 방어) |
| 스키마 검증 | `version` 필수, `system_prompt` 또는 `prompts` 필수 (fail-fast) |

**핵심 메서드:**

| 메서드 | 기능 |
|--------|------|
| `load(mode, agent_name, prompt_key)` | 단일 프롬프트 로드 |
| `load_all(mode, agent_name)` | 에이전트의 모든 프롬프트 로드 |
| `get_version(mode, agent_name)` | SemVer 버전 반환 |
| `clear_cache()` | 캐시 초기화 (핫리로드/테스트) |

**캐싱:** `{mode}/{agent_name}` 키로 파싱된 YAML dict를 인메모리 캐싱. 동일 파일의 반복 로드를 방지한다.

### 2. BaseAgent 통합 (`src/agents/shared/base_agent.py`)

`BaseAgent.__init__()`에서 PromptLoader를 자동 초기화하고 YAML 프롬프트를 로드한다:

```python
# BaseAgent.__init__()에 추가된 필드
self._prompt_loader = PromptLoader(base_dir=get_prompt_base_dir())
self._prompt_mode = self._resolve_mode()       # "podcast" | "conversation" | "shared"
self._prompts = self._load_prompts()           # YAML에서 로드된 프롬프트 dict
self._prompt_version = self._load_prompt_version()  # SemVer 또는 None
```

**주요 메서드:**

- `_resolve_mode()` — 모듈 경로에서 모드 자동 추론 (`src.agents.podcast.X` → `"podcast"`)
- `_load_prompts()` — YAML 로드, 실패 시 빈 dict 반환 (하위 호환)
- `get_prompt(key)` — 로드된 프롬프트 접근 (KeyError if 없음)
- `prompt_version` 프로퍼티 — 현재 프롬프트 SemVer 반환

**에이전트 코드 변경 최소화:**

```python
# 에이전트에서 프롬프트 사용
prompt = self.get_prompt("system_prompt")       # 단일 프롬프트
got_prompt = self.get_prompt("got")             # 다중 프롬프트
```

**로그 출력:**

```
[TIER 1] content_analyzer 시작 (prompt v1.0.0)
[TIER 1] content_analyzer 완료 (250ms, LLM 1회)
```

### 3. YAML 프롬프트 파일 구조

**디렉토리 구조:**

```
prompts/
├── podcast/
│   ├── content_analyzer.yaml      (단일 프롬프트)
│   ├── podcast_reasoning.yaml     (다중: got/tot/cot)
│   └── batch_validator.yaml       (단일 프롬프트)
└── shared/
    └── learning.yaml              (단일 프롬프트)
```

**단일 프롬프트 형식:**

```yaml
version: "1.0.0"
agent: content_analyzer
tier: 1
model: sonnet
description: "팟캐스트 에피소드 주제/테마/구조 분석"

system_prompt: |
  당신은 Mind-Log 팟캐스트 플랫폼의 콘텐츠 분석 전문가입니다.
  ...
```

**다중 프롬프트 형식 (GoT/ToT/CoT):**

```yaml
version: "1.0.0"
agent: podcast_reasoning
tier: 1
model: sonnet
description: "복잡도 기반 3단계 추론 파이프라인"

prompts:
  got:
    description: "Graph of Thoughts"
    system_prompt: |
      ...
  tot:
    description: "Tree of Thoughts"
    system_prompt: |
      ...
  cot:
    description: "Chain of Thoughts"
    system_prompt: |
      ...
```

### 4. 환경변수 지원

```python
def get_prompt_base_dir() -> str:
    return os.getenv("PROMPT_DIR", "prompts")
```

| 환경 | 설정 |
|------|------|
| 개발 | `PROMPT_DIR=prompts` (기본값) |
| 스테이징 | `PROMPT_DIR=prompts_staging` |
| 프로덕션 | `PROMPT_DIR=prompts_prod` |

### 5. 보안 문서 (`docs/PROMPT_SECURITY.md`)

8개 보안 위협 영역에 대한 방어 전략을 문서화:

1. YAML 파싱 취약점
2. 프롬프트 인젝션/변조
3. 경로 조작 (Path Traversal)
4. 환경변수 주입
5. 민감정보 유출
6. 프롬프트 유출 방지
7. 버전 관리 (SemVer + 승격 워크플로우)
8. CI/CD 검증 파이프라인

---

## 영향 범위

### 신규 파일

| 파일 | 설명 |
|------|------|
| `src/agents/shared/prompt_loader.py` | PromptLoader 클래스 + `get_prompt_base_dir()` |
| `prompts/podcast/content_analyzer.yaml` | Content Analyzer 프롬프트 |
| `prompts/podcast/podcast_reasoning.yaml` | Podcast Reasoning GoT/ToT/CoT 프롬프트 |
| `prompts/podcast/batch_validator.yaml` | Batch Validator 검증 프롬프트 |
| `prompts/shared/learning.yaml` | Learning Agent 프롬프트 |
| `docs/PROMPT_SECURITY.md` | 보안 문서 |
| `tests/agents/shared/test_prompt_loader.py` | PromptLoader 테스트 |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/shared/base_agent.py` | PromptLoader 통합 (`_prompt_loader`, `_prompts`, `get_prompt()`, `prompt_version`) |
| `src/agents/podcast/content_analyzer.py` | 하드코딩 프롬프트 → `self.get_prompt()` |
| `src/agents/podcast/podcast_reasoning.py` | 하드코딩 프롬프트 → `self.get_prompt("got"/"tot"/"cot")` |
| `src/agents/podcast/batch_validator.py` | 하드코딩 프롬프트 → `self.get_prompt()` |
| `src/agents/shared/learning.py` | 하드코딩 프롬프트 → `self.get_prompt()` |

---

## 테스트

### 테스트 구조 (`tests/agents/shared/test_prompt_loader.py`)

| 카테고리 | 테스트 수 | 범위 |
|---------|----------|------|
| 프롬프트 로딩 | 5개 | 단일/다중/shared 에이전트 로드 |
| 전체 로딩 | 2개 | `load_all()` 단일/다중 프롬프트 |
| 버전 조회 | 3개 | 단일/다중/shared 에이전트 버전 |
| 캐싱 | 2개 | 캐시 동작 + `clear_cache()` |
| 보안 검증 | 9개 | 경로조작, 파일크기, YAML파싱, 스키마검증, 화이트리스트 |
| 환경변수 | 2개 | 기본값 + `PROMPT_DIR` 오버라이드 |
| BaseAgent 통합 | 7개 | 4개 에이전트 로드, `get_prompt()`, `prompt_version` |

**총 테스트: 85개 전체 통과**

---

## 검증

```bash
python3 -m black . --check       # 통과
python3 -m ruff check .          # 통과
python3 -m isort . --check       # 통과
python3 -m mypy src/ config/     # 통과
python3 -m pytest tests/ -v      # 85개 통과
```

---

*마지막 업데이트: 2026-02-12*

# 변경이력 v8 — 멀티버전 프롬프트 + A/B 테스트 + 롤백

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-12
> 커밋: `6da2cdb` (v7과 동일 커밋에 포함)

---

## 배경

### 문제

v7에서 프롬프트를 YAML 외부화했으나, 단일 버전만 지원했다:

- 프롬프트 A/B 테스트가 불가능 — 효과 비교를 위한 프레임워크 없음
- 프롬프트 버전 롤백 불가 — 새 버전 배포 후 문제 발생 시 대응 어려움
- 에이전트별 프롬프트 버전 고정 불가 — 특정 에이전트만 다른 버전 사용 불가
- 버전 해석 우선순위 규칙 없음

### 목표

1. YAML 멀티버전 형식 도입 — `versions` 키 아래 SemVer별 프롬프트 공존
2. `settings.yaml` 중앙 통제 — 글로벌 기본 + 에이전트별 고정 버전
3. A/B 테스트 프레임워크 — session 기반 결정적 variant 할당
4. 기존 v7 하위 호환 유지 — 단일 버전 YAML도 그대로 동작

---

## 변경 내용

### 1. YAML 멀티버전 형식

기존 단일 버전 형식에서 `versions` 키를 추가하여 SemVer별 프롬프트를 공존시킨다:

```yaml
# 멀티버전 형식 (v8)
default_version: "1.0.0"
versions:
  "1.0.0":
    system_prompt: "v1 프롬프트..."
  "1.1.0":
    system_prompt: "v1.1 프롬프트 (개선)..."
```

YAML 4개 파일 전부 멀티버전 형식으로 마이그레이션:
- `prompts/podcast/content_analyzer.yaml`
- `prompts/podcast/podcast_reasoning.yaml`
- `prompts/podcast/batch_validator.yaml`
- `prompts/shared/learning.yaml`

### 2. settings.yaml 버전 통제

```yaml
prompts:
  versions:
    default: "1.0.0"                    # 글로벌 기본 버전
    content_analyzer: "1.0.0"           # 에이전트별 고정 (선택)
    podcast_reasoning: "1.0.0"
```

### 3. A/B 테스트 프레임워크

```yaml
prompts:
  ab_tests:
    content_analyzer:
      variant_a: "1.0.0"
      variant_b: "1.1.0"
      traffic_split: 0.5               # 50:50 분배
      assignment: "session"             # 세션 기반 결정적 할당
```

- `session_id + agent_name → MD5 해시 → ratio → variant_a or variant_b`
- `contextvars.ContextVar`(`_active_ab_variant`)로 비동기 안전 격리

### 4. 버전 해석 우선순위

```
A/B 테스트 variant → 에이전트별 고정 버전 → 글로벌 기본 → YAML default_version → 첫 번째 버전
```

### 5. PromptLoader 확장 (`src/agents/shared/prompt_loader.py`)

- `load_version(agent_name, version)` — 특정 버전 로드
- `list_versions(agent_name)` — 사용 가능한 버전 목록
- 단일 버전 YAML 하위 호환 유지

### 6. BaseAgent A/B 메서드 (`src/agents/shared/base_agent.py`)

| 메서드 | 역할 |
|--------|------|
| `_resolve_ab_variant()` | Settings에서 A/B 테스트 설정 조회 + variant 결정 |
| `_preload_ab_variants()` | A/B 설정이 있으면 양쪽 variant 프롬프트를 미리 로드 |
| `ab_variant` 프로퍼티 | 현재 활성화된 variant 반환 |

### 7. Settings 확장 (`config/loader.py`)

| 메서드 | 역할 |
|--------|------|
| `get_prompt_version(agent_name)` | 에이전트별 고정 버전 또는 글로벌 기본 반환 |
| `get_ab_test_config(agent_name)` | A/B 테스트 설정 반환 (없으면 None) |

---

## 영향받은 파일

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/agents/shared/prompt_loader.py` | 수정 | 멀티버전 로드 + 버전 목록 기능 추가 |
| `src/agents/shared/base_agent.py` | 수정 | A/B 테스트 메서드 3개 추가 (+200 LOC) |
| `config/loader.py` | 수정 | `get_prompt_version()`, `get_ab_test_config()` 추가 (+70 LOC) |
| `config/settings.yaml` | 수정 | `prompts.versions`, `prompts.ab_tests` 섹션 추가 (+25줄) |
| `prompts/podcast/content_analyzer.yaml` | 수정 | 멀티버전 형식으로 마이그레이션 |
| `prompts/podcast/podcast_reasoning.yaml` | 수정 | 멀티버전 형식으로 마이그레이션 |
| `prompts/podcast/batch_validator.yaml` | 수정 | 멀티버전 형식으로 마이그레이션 |
| `prompts/shared/learning.yaml` | 수정 | 멀티버전 형식으로 마이그레이션 |
| `tests/agents/shared/test_prompt_versioning.py` | 신규 | 멀티버전 + A/B 테스트 27개 |

---

## 테스트

- 기존 85개 테스트 전체 통과 (하위 호환 확인)
- 신규 27개 테스트 추가 (`test_prompt_versioning.py`)
- 합계: 112개 passed

---

## 비고

- v7과 v8은 동일 커밋(`6da2cdb feat: 프롬프트 외부화(v7) + 멀티버전/A/B 테스트(v8) 구현`)에 포함
- v7의 CHANGELOG는 `docs/CHANGELOG_v7.md`에 별도 존재
- v8의 상세 내용은 `docs/PROJECT_SUMMARY.md` §v8, §9.5, §14.3에도 기록되어 있음

---

*마지막 업데이트: 2026-02-14*

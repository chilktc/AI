# 프로덕션 버그 3종 수정 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 프로덕션 로그에서 발견된 3가지 버그(IntentClassifier 프롬프트 로드 실패, ScriptPersonalizer `.segments` 속성 오류, 누적 그래프 PUT 타임스탬프 거부)를 수정한다.

**Architecture:** 각 버그는 독립적이며 순서 상관없이 수정 가능하다. Task 1(ScriptPersonalizer)과 Task 2(Timestamp)는 소스 코드 수정 + 테스트 갱신이고, Task 3(YAML)은 gitignore 우회 커밋이다.

**Tech Stack:** Python 3.11, Pydantic v2, pytest, FastAPI, datetime (stdlib)

---

## ✅ 구현 완료 (2026-04-13)

| Task | 커밋 | PR |
|------|------|-----|
| Task 1: ScriptPersonalizer `.segments` → `.script_text` | `c8ad23c` | #93→develop |
| Task 2: graph_cumulative 타임스탬프 `+00:00` 제거 | `29f66bf` | #94→develop |
| Task 3: 미커밋 프롬프트 YAML 5개 force-add | `acb8903` | #95→develop |

---

## 배경: 버그 원인 요약

| # | 에러 | 원인 | 영향 파일 |
|---|------|------|----------|
| 1 | `[ScriptPersonalizer] Error: 'PersonalizedScript' object has no attribute 'segments'` | PR #91에서 `segments: list[ScriptSegment]` → `script_text: str`로 평탄화됐는데, personalizer 내부 2곳이 미갱신 | `src/agents/podcast/script_personalizer.py:188,220` |
| 2 | `누적 그래프 PUT 실패` (백엔드가 `+00:00` 거부) | `datetime.now(timezone.utc).isoformat()` → `"2026-04-09T00:00:00+00:00"` 생성. 백엔드가 timezone suffix 거부 | `src/api/graph_cumulative.py:66,122` |
| 3 | `프롬프트 키 'system_prompt'를 찾을 수 없음 (에이전트: intent_classifier). 사용 가능한 키: []` | `prompts/` 디렉토리가 `.gitignore`에 등록되어 있고, `intent_classifier.yaml` 등 5개 파일이 force-add 없이 미커밋 상태 | `prompts/podcast/intent_classifier.yaml` 등 5개 |

---

## 수정 대상 파일

| 파일 | 변경 유형 |
|------|----------|
| `src/agents/podcast/script_personalizer.py` | 수정: line 187-189, 219-221 |
| `src/api/graph_cumulative.py` | 수정: line 66, 122 |
| `tests/agents/podcast/test_script_personalizer.py` | 수정: fixture + helper |
| `tests/api/test_graph_cumulative.py` | 수정: `_NOW_ISO` 정의 |
| `prompts/podcast/intent_classifier.yaml` (+ 4개) | git force-add |

---

## Task 1: ScriptPersonalizer — `.segments` → `.script_text` 수정

**Files:**
- Modify: `src/agents/podcast/script_personalizer.py:187-189, 219-221`
- Modify: `tests/agents/podcast/test_script_personalizer.py:26-68, 144`

### 원인 상세

`PersonalizedScript`와 `ValidatedScript` 스키마(PR #91에서 변경):
```python
# src/models/schemas.py
class ValidatedScript(BaseModel):
    episode_title: str
    total_duration: int
    script_text: str  # ← 전체 스크립트 (segments 제거됨)
    tts_markers: list[TTSMarker]
    key_insights: list[str]
    themes: list[str]
    # segments 필드 없음!

class PersonalizedScript(BaseModel):
    episode_id: str
    episode_title: str
    total_duration: int
    script_text: str  # ← 전체 스크립트 (segments 제거됨)
    # segments 필드 없음!
```

`script_personalizer.py` 두 곳이 여전히 `.segments`를 순회하려 함:
- **line 187-189**: 성공 경로에서 `memory_text` 추출 시
- **line 219-221**: 예외 처리(fallback) 경로에서 `fallback_memory_text` 추출 시

---

- [x] **Step 1: 현재 실패 확인**

```bash
pytest tests/agents/podcast/test_script_personalizer.py -v -x 2>&1 | head -40
```

Expected: 일부 테스트에서 `AttributeError: 'PersonalizedScript' object has no attribute 'segments'` 또는 `ValidationError` 발생

---

- [x] **Step 2: `script_personalizer.py` line 187-189 수정**

현재 코드(`src/agents/podcast/script_personalizer.py:186-189`):
```python
            # 메모리 저장용 에피소드 텍스트 추출 (세그먼트 텍스트 연결)
            memory_text = "\n\n".join(
                seg.script_text for seg in personalized_script.segments if seg.script_text
            )
```

수정 후:
```python
            # 메모리 저장용 에피소드 텍스트 추출
            memory_text = personalized_script.script_text or ""
```

---

- [x] **Step 3: `script_personalizer.py` line 219-221 수정**

현재 코드(`src/agents/podcast/script_personalizer.py:218-221`):
```python
                try:
                    fallback_memory_text = "\n\n".join(
                        seg.script_text for seg in validated_script.segments if seg.script_text
                    )
```

수정 후:
```python
                try:
                    fallback_memory_text = validated_script.script_text or ""
```

---

- [x] **Step 4: 테스트 fixture `create_sample_script()` 수정**

`tests/agents/podcast/test_script_personalizer.py:26-68`의 `create_sample_script()` 함수 전체를 교체한다.

현재: `ValidatedScript(segments=[ScriptSegment(...)], total_duration=15, ...)` — `script_text` 미포함으로 Pydantic `ValidationError` 발생

수정 후:
```python
def create_sample_script() -> ValidatedScript:
    """샘플 스크립트"""
    return ValidatedScript(
        episode_title="번아웃, 그것은 나약함이 아닙니다",
        total_duration=15,
        script_text=(
            "여러분, 안녕하세요. 오늘은 번아웃에 대해 이야기해볼게요. "
            "요즘 많이 지치셨나요?\n\n"
            "번아웃은 단순한 피로가 아닙니다. "
            "세계보건기구에서도 공식적으로 인정한 직업 현상이에요.\n\n"
            "오늘 이야기가 도움이 되셨길 바랍니다. 여러분을 응원합니다."
        ),
        key_insights=["번아웃은 신호다"],
        themes=["번아웃", "스트레스"],
    )
```

---

- [x] **Step 5: 테스트 helper `_print_personalization_result` line 144 수정**

`tests/agents/podcast/test_script_personalizer.py:144`:

현재:
```python
        orig_texts_joined = " ".join([s.script_text for s in original.segments])
```

수정 후:
```python
        orig_texts_joined = original.script_text
```

---

- [x] **Step 6: 테스트 실행 확인**

```bash
pytest tests/agents/podcast/test_script_personalizer.py -v 2>&1 | tail -20
```

Expected: `PASSED` (이전 실패 테스트 포함)

---

- [x] **Step 7: 전체 테스트 통과 확인**

```bash
pytest tests/ -v --timeout=30 -q 2>&1 | tail -10
```

Expected: 실패 없음 (기존 532개 이상 PASSED)

---

- [x] **Step 8: 커밋**

```bash
git add src/agents/podcast/script_personalizer.py tests/agents/podcast/test_script_personalizer.py
git commit -m "fix: ScriptPersonalizer .segments → .script_text 수정 (PR #91 평탄화 미반영 수정)"
```

---

## Task 2: 누적 그래프 PUT — Timestamp `+00:00` 제거

**Files:**
- Modify: `src/api/graph_cumulative.py:66,122`
- Modify: `tests/api/test_graph_cumulative.py:22`

### 원인 상세

`src/api/graph_cumulative.py` 두 함수(`_merge_nodes`, `_merge_links`)에서:
```python
now = datetime.now(timezone.utc)   # line 217
now_iso = now.isoformat()           # line 66, 122 — "2026-04-09T00:00:00+00:00" 생성
```

백엔드가 `+00:00` timezone suffix를 거부 → PUT 실패.

수정: `strftime('%Y-%m-%dT%H:%M:%S')` 사용 → `"2026-04-09T00:00:00"` (마이크로초 및 timezone 없음)

> **참고**: 기존 백엔드에서 받아오는 `first_seen`/`last_seen` 데이터(`"2026-04-01T00:00:00+00:00"` 형태)는 AI 서버가 수정하지 않고 그대로 보존한다. 오직 새로 생성하는 타임스탬프만 수정한다.

---

- [x] **Step 1: 현재 실패 재현 (선택)**

`test_graph_cumulative.py`가 `_NOW_ISO`를 기준으로 assertion하므로, 수정 전 현황 확인:

```bash
pytest tests/api/test_graph_cumulative.py -v -q 2>&1 | tail -10
```

Expected: PASSED (현재 코드와 테스트가 둘 다 `+00:00` 사용하므로 통과)

---

- [x] **Step 2: `graph_cumulative.py` line 66 수정**

`src/api/graph_cumulative.py`의 `_merge_nodes()` 함수 내부:

현재:
```python
    now_iso = now.isoformat()
```

수정 후:
```python
    now_iso = now.strftime('%Y-%m-%dT%H:%M:%S')
```

> `line 66`은 `_merge_nodes(existing, got_nodes, now, alpha)` 함수 내부의 첫 번째 `now_iso` 할당이다. grep으로 위치 확인: `grep -n "now_iso = now" src/api/graph_cumulative.py`

---

- [x] **Step 3: `graph_cumulative.py` line 122 수정**

`src/api/graph_cumulative.py`의 `_merge_links()` 함수 내부:

현재:
```python
    now_iso = now.isoformat()
```

수정 후:
```python
    now_iso = now.strftime('%Y-%m-%dT%H:%M:%S')
```

---

- [x] **Step 4: 테스트 `_NOW_ISO` 수정**

`tests/api/test_graph_cumulative.py:22`:

현재:
```python
_NOW = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()  # "2026-04-09T00:00:00+00:00"
```

수정 후:
```python
_NOW = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.strftime('%Y-%m-%dT%H:%M:%S')  # "2026-04-09T00:00:00"
```

> `_NOW_ISO`를 사용하는 assertion(line 115, 116, 137 등)은 자동으로 새 형식을 검증한다.
> 기존 fixture 데이터(`"2026-04-01T00:00:00+00:00"` 형태)는 백엔드 입력값이므로 변경하지 않는다.

---

- [x] **Step 5: 테스트 실행 확인**

```bash
pytest tests/api/test_graph_cumulative.py -v 2>&1 | tail -20
```

Expected: 전체 PASSED

---

- [x] **Step 6: 전체 테스트 통과 확인**

```bash
pytest tests/ -v --timeout=30 -q 2>&1 | tail -10
```

Expected: 실패 없음

---

- [x] **Step 7: 커밋**

```bash
git add src/api/graph_cumulative.py tests/api/test_graph_cumulative.py
git commit -m "fix: graph_cumulative 타임스탬프 +00:00 제거 — 백엔드 PUT 거부 해결"
```

---

## Task 3: 미커밋 프롬프트 YAML 파일 — git force-add

**Files:**
- Force-add: `prompts/podcast/intent_classifier.yaml`
- Force-add: `prompts/podcast/emotion.yaml`
- Force-add: `prompts/podcast/knowledge.yaml`
- Force-add: `prompts/podcast/script_generator.yaml`
- Force-add: `prompts/podcast/script_personalizer.yaml`

### 원인 상세

`prompts/` 디렉토리가 `.gitignore`에 등록되어 있다:
```
# .gitignore
prompts/
```

`git ls-files prompts/`로 확인하면 현재 6개 파일만 tracked (이전에 force-add됨):
- `batch_validator.yaml`, `content_analyzer.yaml`, `learning.yaml`, `podcast_reasoning.yaml`, `safety.yaml`, `visualization.yaml`

나머지 5개(`intent_classifier`, `emotion`, `knowledge`, `script_generator`, `script_personalizer`)는 로컬에만 존재 → 서버 배포 시 파일 없음 → `PromptLoadError` → `self._prompts = {}` → `get_prompt("system_prompt")` 실패

---

- [x] **Step 1: 현재 tracked 파일 확인**

```bash
git ls-files prompts/
```

Expected 출력:
```
prompts/podcast/batch_validator.yaml
prompts/podcast/content_analyzer.yaml
prompts/podcast/learning.yaml
prompts/podcast/podcast_reasoning.yaml
prompts/podcast/safety.yaml
prompts/podcast/visualization.yaml
```

미포함 5개(`intent_classifier`, `emotion`, `knowledge`, `script_generator`, `script_personalizer`)가 목록에 없음을 확인

---

- [x] **Step 2: 각 파일 내용 검증**

5개 파일이 올바른 YAML 구조를 가지고 있는지 확인:

```bash
python3 -c "
import yaml
files = [
    'prompts/podcast/intent_classifier.yaml',
    'prompts/podcast/emotion.yaml',
    'prompts/podcast/knowledge.yaml',
    'prompts/podcast/script_generator.yaml',
    'prompts/podcast/script_personalizer.yaml',
]
for f in files:
    with open(f) as fp:
        data = yaml.safe_load(fp)
    has_version = 'version' in data or 'default_version' in data or 'versions' in data
    has_prompt = 'system_prompt' in data or 'prompts' in data or 'versions' in data
    print(f'{f}: version={has_version}, prompt={has_prompt}')
"
```

Expected: 각 파일마다 `version=True, prompt=True` 출력

---

- [x] **Step 3: 5개 파일 force-add**

```bash
git add -f prompts/podcast/intent_classifier.yaml \
          prompts/podcast/emotion.yaml \
          prompts/podcast/knowledge.yaml \
          prompts/podcast/script_generator.yaml \
          prompts/podcast/script_personalizer.yaml
```

---

- [x] **Step 4: tracked 파일 재확인**

```bash
git ls-files prompts/
```

Expected: 11개 파일 모두 출력 (기존 6개 + 신규 5개)

---

- [x] **Step 5: PromptLoader로 로드 검증**

```bash
python3 -c "
from src.agents.shared.prompt_loader import PromptLoader, get_prompt_base_dir
loader = PromptLoader(base_dir=get_prompt_base_dir())
for agent in ['intent_classifier', 'emotion', 'knowledge', 'script_generator', 'script_personalizer']:
    try:
        prompts = loader.load_all('podcast', agent)
        print(f'{agent}: keys={list(prompts.keys())}')
    except Exception as e:
        print(f'{agent}: ERROR — {e}')
"
```

Expected: 각 에이전트마다 `keys=['system_prompt']` (또는 다중 키) 출력, ERROR 없음

---

- [x] **Step 6: 커밋**

```bash
git commit -m "fix: 미커밋 프롬프트 YAML 5개 force-add (intent_classifier 등) — PromptLoadError 수정"
```

---

## Task 4: PR 생성 및 merge

- [x] **Step 1: 브랜치 생성 (작업 시작 전)**

위 Task 1~3은 `develop`에서 새 브랜치를 만들어서 작업한다:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/reasoning-production-bugfix
```

---

- [x] **Step 2: 전체 테스트 최종 확인**

```bash
pytest tests/ -q --timeout=30 2>&1 | tail -5
```

Expected: `N passed` (기존 532개 이상, 실패 0)

---

- [x] **Step 3: PR 생성**

```bash
/opt/homebrew/bin/gh pr create \
  --base develop \
  --title "fix: 프로덕션 버그 3종 수정 (segments, timestamp, 프롬프트 YAML)" \
  --body "$(cat <<'EOF'
## 개요

프로덕션 로그에서 발견된 버그 3종 수정.

## 변경 내역

| 버그 | 원인 | 수정 |
|------|------|------|
| ScriptPersonalizer `.segments` AttributeError | PR #91 평탄화 후 2곳 미갱신 | `personalized_script.script_text` 직접 사용 |
| 누적 그래프 PUT 실패 (`+00:00` 거부) | `isoformat()` timezone suffix | `strftime('%Y-%m-%dT%H:%M:%S')` 로 변경 |
| IntentClassifier 프롬프트 로드 실패 | 5개 YAML 미커밋 (gitignore) | `git add -f` force-add |

## 테스트

- `pytest tests/agents/podcast/test_script_personalizer.py -v` PASS
- `pytest tests/api/test_graph_cumulative.py -v` PASS
- `pytest tests/ -q` 전체 PASS
EOF
)"
```

---

## 검증 기준

| 항목 | 기준 |
|------|------|
| ScriptPersonalizer | `process()` 성공 시 `memory_text == personalized_script.script_text` |
| Timestamp | `now_iso`가 `+` 문자 미포함 (`"2026-04-09T00:00:00"` 형태) |
| PromptLoader | `load_all("podcast", "intent_classifier")["system_prompt"]` 존재 확인 |
| 전체 테스트 | 기존 테스트 깨지지 않음 (532개 이상 PASSED) |

---

*2026-04-13 작성 — feature/reasoning-production-bugfix 브랜치 대상*

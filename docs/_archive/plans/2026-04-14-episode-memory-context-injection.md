# Episode Memory 컨텍스트 주입 개선 Implementation Plan

> **상태**: ✅ 완료
> **완료 PR**: #134 (feat: Episode Memory phase별 컨텍스트 주입 개선 GoT/ToT/CoT 분리)
> **마지막 업데이트**: 2026-04-14 19:00

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_build_phase_context()`를 phase별로 분기하여 GoT는 오염 방지, ToT는 구조 다양성, CoT는 스타일 개인화를 각각 달성한다.

**Architecture:** `podcast_reasoning.py`의 `_build_phase_context()` 내 메모리 블록(3줄)을 phase 분기 로직으로 교체하고, `_load_config()`에 `memory_style_score_threshold` 설정을 추가한다. YAML 프롬프트는 v3.2.0을 신규 추가하고 settings.yaml에서 핀닝을 변경한다.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, PyYAML

---

## 파일 변경 목록

| 파일 | 작업 | 변경 내용 |
|------|------|---------|
| `src/agents/podcast/podcast_reasoning.py` | Modify | `_load_config()` + `_build_phase_context()` |
| `config/settings.yaml` | Modify | `podcast_reasoning.memory_style_score_threshold` 추가 + 프롬프트 버전 핀닝 변경 |
| `prompts/podcast/podcast_reasoning.yaml` | Modify | v3.2.0 신규 버전 추가 (gitignore 대상 — 로컬만 반영) |
| `tests/agents/podcast/test_podcast_reasoning.py` | Modify | phase별 메모리 컨텍스트 테스트 6개 추가 |

---

## Task 1: `memory_style_score_threshold` 설정 로드

**Files:**
- Modify: `src/agents/podcast/podcast_reasoning.py:161-170`
- Modify: `config/settings.yaml:118`
- Test: `tests/agents/podcast/test_podcast_reasoning.py` (파일 끝에 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/agents/podcast/test_podcast_reasoning.py` 파일 끝(881번 라인 이후)에 추가:

```python
# === 15. memory_style_score_threshold 설정 로드 ===


def test_memory_style_score_threshold_default() -> None:
    """memory_style_score_threshold 기본값이 0.9로 로드된다."""
    agent = PodcastReasoningAgent()
    assert hasattr(agent, "memory_style_score_threshold")
    assert agent.memory_style_score_threshold == 0.9
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
pytest tests/agents/podcast/test_podcast_reasoning.py::test_memory_style_score_threshold_default -v
```

Expected: `FAILED` — `AttributeError: 'PodcastReasoningAgent' object has no attribute 'memory_style_score_threshold'`

- [ ] **Step 3: `_load_config()` 구현**

`src/agents/podcast/podcast_reasoning.py:161-170` 교체:

```python
def _load_config(self) -> None:
    """settings.yaml에서 추론 깊이 임계값을 로드한다. 실패 시 기본값 사용."""
    cfg = self._load_agent_config(
        {
            "full_threshold": 0.8,
            "standard_threshold": 0.5,
            "memory_style_score_threshold": 0.9,
        }
    )
    self.full_threshold: float = cfg["full_threshold"]
    self.standard_threshold: float = cfg["standard_threshold"]
    self.memory_style_score_threshold: float = cfg["memory_style_score_threshold"]
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_memory_style_score_threshold_default -v
```

Expected: `PASSED`

- [ ] **Step 5: `config/settings.yaml` 118번 라인 이후에 설정 추가**

`standard_threshold: 0.0` 라인 바로 다음에 추가:

```yaml
    memory_style_score_threshold: 0.9  # CoT 스타일 참고용 에피소드 최소 유사도 (0.0~1.0)
```

변경 후 `podcast_reasoning` 섹션:
```yaml
  podcast_reasoning:
    model: sonnet_37
    max_tokens: 6000
    temperature: 0.3
    full_threshold: 0.0
    standard_threshold: 0.0
    memory_style_score_threshold: 0.9  # CoT 스타일 참고용 에피소드 최소 유사도 (0.0~1.0)
```

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -m "not live"
```

Expected: 기존 테스트 전부 `PASSED`, 신규 1개 `PASSED`

- [ ] **Step 7: 커밋**

```bash
git add src/agents/podcast/podcast_reasoning.py config/settings.yaml tests/agents/podcast/test_podcast_reasoning.py
git commit -m "feat: memory_style_score_threshold 설정 로드 추가"
```

---

## Task 2: GoT phase — 기존 동작 회귀 테스트

**Files:**
- Test: `tests/agents/podcast/test_podcast_reasoning.py` (Task 1 테스트 바로 아래에 추가)

> GoT phase는 코드 변경 없음. 회귀 테스트만 추가하여 "이후 변경에서도 GoT에 원문이 들어가지 않음"을 보장한다.

- [ ] **Step 1: 실패 없는 회귀 테스트 작성 (이미 통과해야 정상)**

```python
# === 16. _build_phase_context — phase별 메모리 분기 ===


def test_build_phase_context_got_memory_count_only(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """GoT phase: memory_result가 있어도 건수 요약만 포함되고 원문은 포함되지 않는다."""
    memory_result = {
        "episodes": [
            {
                "text": "안녕하세요. 번아웃 에피소드 원문입니다.",
                "score": 0.94,
                "metadata": {
                    "date": "2026-04-10T14:32:15",
                    "episode_title": "번아웃과 리더십",
                },
            }
        ],
        "summary": "번아웃 관련 1개 에피소드",
    }
    context = agent_with_stubs._build_phase_context(
        phase="GoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        memory_result=memory_result,
    )
    assert "[과거 에피소드 기억]" in context
    assert "1건 발견" in context
    assert "번아웃 에피소드 원문" not in context
    assert "번아웃과 리더십" not in context
```

- [ ] **Step 2: 테스트 실행 → 통과 확인 (기존 동작 검증)**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_got_memory_count_only -v
```

Expected: `PASSED` (코드 변경 없이 통과해야 함)

- [ ] **Step 3: 커밋**

```bash
git add tests/agents/podcast/test_podcast_reasoning.py
git commit -m "test: GoT phase 메모리 건수 회귀 테스트 추가"
```

---

## Task 3: ToT phase — 메타데이터 분기 구현

**Files:**
- Modify: `src/agents/podcast/podcast_reasoning.py:417-419`
- Test: `tests/agents/podcast/test_podcast_reasoning.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Task 2 테스트 바로 아래에 추가:

```python
def test_build_phase_context_tot_metadata_only(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """ToT phase: 에피소드 제목·날짜가 포함되고 원문 텍스트는 포함되지 않는다."""
    memory_result = {
        "episodes": [
            {
                "text": "안녕하세요. 번아웃 에피소드 원문입니다.",
                "score": 0.94,
                "metadata": {
                    "date": "2026-04-10T14:32:15",
                    "episode_title": "번아웃과 리더십",
                },
            },
            {
                "text": "수면 문제 에피소드 원문입니다.",
                "score": 0.81,
                "metadata": {
                    "date": "2026-03-28T09:15:44",
                    "episode_title": "잠 못 드는 밤",
                },
            },
        ],
        "summary": "번아웃, 수면 관련 2개 에피소드",
    }
    context = agent_with_stubs._build_phase_context(
        phase="ToT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        memory_result=memory_result,
    )
    assert "[과거 에피소드 기억 — 구조 참고]" in context
    assert "2026-04-10" in context
    assert "번아웃과 리더십" in context
    assert "2026-03-28" in context
    assert "잠 못 드는 밤" in context
    # 원문 텍스트 미포함
    assert "번아웃 에피소드 원문" not in context
    assert "수면 문제 에피소드 원문" not in context
    # 다양성 가이드 문구 포함
    assert "다양성" in context
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_tot_metadata_only -v
```

Expected: `FAILED` — `AssertionError: assert '[과거 에피소드 기억 — 구조 참고]' in ...`

- [ ] **Step 3: `_build_phase_context()` ToT 분기 구현**

`src/agents/podcast/podcast_reasoning.py:417-419`의 3줄을 다음으로 교체:

```python
        # 독립 에이전트 결과 — phase별 역할 분리 (GoT: 오염방지 / ToT: 구조다양성 / CoT: 스타일개인화)
        if memory_result and memory_result.get("episodes"):
            episodes = memory_result["episodes"]
            episode_count = len(episodes)

            if phase == "GoT":
                # GoT: 건수만 — 노드 오염 방지
                parts.append(f"[과거 에피소드 기억]\n- {episode_count}건 발견")

            elif phase == "ToT":
                # ToT: 메타데이터만 — 구조 다양성 가이드
                lines = ["[과거 에피소드 기억 — 구조 참고]"]
                for ep in episodes:
                    date = ep.get("metadata", {}).get("date", "")[:10]
                    title = ep.get("metadata", {}).get("episode_title", "제목 없음")
                    lines.append(f"- {date} '{title}'")
                lines.append("→ 위 에피소드에서 사용된 구조를 파악하여 대안 생성 시 다양성을 확보하세요.")
                parts.append("\n".join(lines))

            elif phase == "CoT":
                # CoT: summary + score 필터 원문 — 스타일 개인화 (Task 4에서 구현)
                parts.append(f"[과거 에피소드 기억]\n- {episode_count}건 발견")
```

> 주의: CoT 분기는 Task 4에서 완성한다. 지금은 임시로 GoT와 동일하게 건수만 표시.

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_tot_metadata_only -v
```

Expected: `PASSED`

- [ ] **Step 5: 기존 테스트 회귀 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -m "not live"
```

Expected: 전체 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
git commit -m "feat: ToT phase 메모리 메타데이터 분기 구현"
```

---

## Task 4: CoT phase — 스타일 개인화 구현

**Files:**
- Modify: `src/agents/podcast/podcast_reasoning.py` (Task 3에서 작성한 CoT 임시 분기 교체)
- Test: `tests/agents/podcast/test_podcast_reasoning.py`

- [ ] **Step 1: 실패하는 테스트 3개 작성**

Task 3 테스트 바로 아래에 추가:

```python
def test_build_phase_context_cot_includes_high_score_text(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """CoT phase: score >= threshold 에피소드의 원문 발췌가 포함된다."""
    agent_with_stubs.memory_style_score_threshold = 0.9
    memory_result = {
        "episodes": [
            {
                "text": "안녕하세요. 번아웃 에피소드 원문입니다. 긴 텍스트가 여기 있습니다.",
                "score": 0.94,
                "metadata": {
                    "date": "2026-04-10T14:32:15",
                    "episode_title": "번아웃과 리더십",
                },
            }
        ],
        "summary": "번아웃 관련 1개 에피소드",
    }
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        memory_result=memory_result,
    )
    assert "[과거 에피소드 스타일 참고]" in context
    assert "요약: 번아웃 관련 1개 에피소드" in context
    assert "번아웃과 리더십" in context
    assert "0.94" in context
    assert "번아웃 에피소드 원문" in context
    assert "스타일" in context


def test_build_phase_context_cot_excludes_low_score_text(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """CoT phase: score < threshold 에피소드의 원문 발췌는 포함되지 않는다."""
    agent_with_stubs.memory_style_score_threshold = 0.9
    memory_result = {
        "episodes": [
            {
                "text": "낮은 유사도 에피소드 원문입니다.",
                "score": 0.75,
                "metadata": {
                    "date": "2026-03-01T10:00:00",
                    "episode_title": "낮은 유사도 에피소드",
                },
            }
        ],
        "summary": "",
    }
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        memory_result=memory_result,
    )
    assert "[과거 에피소드 스타일 참고]" in context
    assert "낮은 유사도 에피소드 원문" not in context


def test_build_phase_context_cot_no_memory(
    agent_with_stubs: PodcastReasoningAgent,
) -> None:
    """CoT phase: memory_result=None이면 메모리 섹션이 없다."""
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="요즘 너무 힘들어요.",
        intent={},
        memory_result=None,
    )
    assert "[과거 에피소드 스타일 참고]" not in context
    assert "[과거 에피소드 기억]" not in context
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_includes_high_score_text tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_excludes_low_score_text tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_no_memory -v
```

Expected: 3개 모두 `FAILED`

- [ ] **Step 3: CoT 임시 분기를 최종 구현으로 교체**

Task 3에서 작성한 `elif phase == "CoT":` 블록을 다음으로 교체:

```python
            elif phase == "CoT":
                # CoT: summary + score 필터 원문 — 스타일 개인화
                lines = ["[과거 에피소드 스타일 참고]"]
                summary = memory_result.get("summary", "")
                if summary:
                    lines.append(f"요약: {summary}")
                for ep in episodes:
                    score = ep.get("score", 0.0)
                    if score < self.memory_style_score_threshold:
                        continue
                    date = ep.get("metadata", {}).get("date", "")[:10]
                    title = ep.get("metadata", {}).get("episode_title", "제목 없음")
                    text_preview = ep.get("text", "")[:200]
                    lines.append(
                        f"\n[{date}] '{title}' (유사도 {score:.2f})\n{text_preview}..."
                    )
                lines.append("→ 내용(주제·구조)이 아닌 스타일(말투·톤)만 참고하세요.")
                parts.append("\n".join(lines))
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_includes_high_score_text tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_excludes_low_score_text tests/agents/podcast/test_podcast_reasoning.py::test_build_phase_context_cot_no_memory -v
```

Expected: 3개 모두 `PASSED`

- [ ] **Step 5: 전체 테스트 회귀 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -m "not live"
```

Expected: 전체 `PASSED`

- [ ] **Step 6: 커밋**

```bash
git add src/agents/podcast/podcast_reasoning.py tests/agents/podcast/test_podcast_reasoning.py
git commit -m "feat: CoT phase 에피소드 스타일 개인화 분기 구현"
```

---

## Task 5: YAML 프롬프트 v3.2.0 추가 + 버전 핀닝 변경

**Files:**
- Modify: `prompts/podcast/podcast_reasoning.yaml` (gitignore 대상 — 로컬만)
- Modify: `config/settings.yaml:201`

> `prompts/` 디렉토리는 `.gitignore` 대상이므로 YAML 변경은 커밋되지 않는다.
> `settings.yaml`의 버전 핀닝 변경만 커밋한다.

- [ ] **Step 1: `prompts/podcast/podcast_reasoning.yaml`에 v3.2.0 추가**

파일에서 `"3.1.0":` 버전 블록 전체를 복사한 뒤, 그 아래에 `"3.2.0":` 블록을 추가한다.
`tot` 시스템 프롬프트 끝(기존 내용 뒤)에 아래를 추가:

```yaml
          ## 과거 에피소드 구조 참고 (제공된 경우)
          [과거 에피소드 기억 — 구조 참고] 섹션이 있으면,
          이미 사용된 구조를 파악하여 대안 생성 시 다양성을 확보하세요.
          단, 과거 구조 회피가 현재 사용자 상태에 맞지 않는다면 무시해도 됩니다.
```

`cot` 시스템 프롬프트 끝(기존 내용 뒤)에 아래를 추가:

```yaml
          ## 과거 에피소드 스타일 참고 (제공된 경우)
          [과거 에피소드 스타일 참고] 섹션이 있으면,
          호칭 방식, 도입/마무리 톤, 문장 길이를 참고하여 일관된 경험을 제공하세요.
          내용(주제·구조)이 아닌 스타일(말투·톤)만 참고합니다.
```

- [ ] **Step 2: `config/settings.yaml:201` 핀닝 변경**

```yaml
# 변경 전
    podcast_reasoning: "3.1.0"

# 변경 후
    podcast_reasoning: "3.2.0"
```

- [ ] **Step 3: 서버 재기동 없이 설정 반영 확인**

```bash
cd /Users/kttechup/Documents/NewProject/mind-log
python3 -c "
from config.loader import get_settings
s = get_settings()
ver = s.prompts.versions.get('podcast_reasoning')
print('podcast_reasoning version:', ver)
assert ver == '3.2.0', f'Expected 3.2.0, got {ver}'
print('OK')
"
```

Expected:
```
podcast_reasoning version: 3.2.0
OK
```

- [ ] **Step 4: 전체 테스트 최종 확인**

```bash
pytest tests/agents/podcast/test_podcast_reasoning.py -v -m "not live"
```

Expected: 전체 `PASSED`

- [ ] **Step 5: 커밋**

```bash
git add config/settings.yaml
git commit -m "feat: podcast_reasoning 프롬프트 버전 3.1.0 → 3.2.0 핀닝"
```

---

## 셀프 리뷰 체크리스트

- [x] **스펙 커버리지**: GoT(건수유지) / ToT(메타데이터) / CoT(score필터 원문) / threshold설정 / YAML핀닝 모두 Task로 구현됨
- [x] **플레이스홀더 없음**: 모든 Step에 실제 코드 포함
- [x] **타입 일관성**: `memory_style_score_threshold: float` Task 1에서 정의, Task 4에서 `self.memory_style_score_threshold` 참조
- [x] **메서드명 일관성**: `_build_phase_context`, `_load_config` 모두 기존 파일 명칭과 동일
- [x] **conftest autouse 영향**: `got_default_thresholds` fixture는 `full_threshold`, `standard_threshold`만 덮어쓰므로 `memory_style_score_threshold`에 영향 없음 — Task 1 테스트 정상 동작

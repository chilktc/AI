# Episode Memory 컨텍스트 주입 개선 설계

**작성일**: 2026-04-14  
**브랜치**: `feature/validation-episode-memory-context`  
**담당**: 개발자3  
**관련 파일**: `src/agents/podcast/podcast_reasoning.py`, `prompts/podcast/podcast_reasoning.yaml`, `config/settings.yaml`

---

## 배경 및 문제

현재 `_build_phase_context()`는 GoT·ToT·CoT 세 단계 모두에서 Episode Memory 결과를
건수 요약(`"- N건 발견"`)만 LLM에 전달한다. Pinecone에서 검색한 실제 에피소드 텍스트,
제목, 날짜, 유사도 점수는 전혀 활용되지 않는다.

```python
# 현재 코드 (podcast_reasoning.py:417-419)
if memory_result and memory_result.get("episodes"):
    episode_count = len(memory_result["episodes"])
    parts.append(f"[과거 에피소드 기억]\n- {episode_count}건 발견")
```

---

## 목표

- GoT 단계의 노드 오염(Node Contamination) 없이
- ToT 단계에서 구조 다양성(Structure Diversity)을 높이고
- CoT 단계에서 사용자 말투·톤 개인화(Style Personalization)를 실현한다

---

## 설계 결정: GoT 오염 방지 근거

GoT에 에피소드 원문을 주입하면 세 가지 오염 경로가 발생한다.

| 오염 경로 | 현상 |
|-----------|------|
| Label Bleed | 사용자가 언급하지 않은 과거 에피소드 어휘가 GoT 노드로 생성됨 |
| Edge Distortion | 과거 에피소드의 인과관계가 현재 입력에 투영되어 Neo4j에 잘못된 패턴 저장 |
| Anchoring Effect | `core_pattern`이 과거 에피소드 주제로 고착 → ToT·CoT 전체가 재탕 방향으로 수렴 |

**레퍼런스**: RAT (arxiv 2403.05313), CoT-RAG (arxiv 2504.13534), Context Engineering (Phil Schmid, 2025)  
→ 모두 "구조 추출 단계 완료 후 외부 컨텍스트 주입"을 권고한다.

---

## 아키텍처

### phase별 메모리 삽입 전략

| Phase | 메모리 사용 | 삽입 형태 | 목적 |
|-------|------------|-----------|------|
| **GoT** | 건수만 (기존 유지) | `"- N건 발견"` | 오염 방지. 존재 여부만 전달 |
| **ToT** | 메타데이터 | `date` + `title` 목록 + 가이드 문구 | 이미 사용된 구조 파악 → 구조 다양성 확보 |
| **CoT** | 원문 발췌 (score 필터) | `summary` + score ≥ threshold 에피소드의 `text[:200]` | 말투·톤 개인화 |

### 설정값

`config/settings.yaml`의 `podcast_reasoning` 섹션에 신규 키 추가:

```yaml
podcast_reasoning:
  memory_style_score_threshold: 0.9  # CoT 스타일 참고용 에피소드 최소 유사도 (0.0~1.0)
```

기본값 0.9 — 유사도가 낮은 에피소드 원문은 스타일 노이즈가 될 수 있어 높게 설정.
운영 중 조정이 필요하면 settings.yaml만 수정하면 된다.

---

## 변경 상세

### 1. `src/agents/podcast/podcast_reasoning.py`

#### 1-1. `_load_config()` — 신규 설정값 로드

```python
def _load_config(self) -> None:
    cfg = self._load_agent_config({
        "full_threshold": 0.8,
        "standard_threshold": 0.5,
        "memory_style_score_threshold": 0.9,  # 추가
    })
    self.full_threshold: float = cfg["full_threshold"]
    self.standard_threshold: float = cfg["standard_threshold"]
    self.memory_style_score_threshold: float = cfg["memory_style_score_threshold"]  # 추가
```

#### 1-2. `_build_phase_context()` — phase별 분기 (417~419라인 교체)

**현재:**
```python
if memory_result and memory_result.get("episodes"):
    episode_count = len(memory_result["episodes"])
    parts.append(f"[과거 에피소드 기억]\n- {episode_count}건 발견")
```

**변경 후:**
```python
if memory_result and memory_result.get("episodes"):
    episodes = memory_result["episodes"]
    episode_count = len(episodes)

    if phase == "GoT":
        # GoT: 건수만 — 오염 방지
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
            lines.append(f"\n[{date}] '{title}' (유사도 {score:.2f})\n{text_preview}...")
        lines.append("→ 내용(주제·구조)이 아닌 스타일(말투·톤)만 참고하세요.")
        parts.append("\n".join(lines))
```

### 2. `config/settings.yaml`

`podcast_reasoning` 섹션에 1줄 추가:

```yaml
podcast_reasoning:
  model: sonnet_37
  max_tokens: 6000
  temperature: 0.3
  full_threshold: 0.0
  standard_threshold: 0.0
  memory_style_score_threshold: 0.9   # 추가: CoT 스타일 참고 최소 유사도
```

### 3. `prompts/podcast/podcast_reasoning.yaml` — v3.2.0 신규 버전

v3.1.0을 기반으로 ToT·CoT 시스템 프롬프트에 메모리 활용 지시 추가.

**ToT 시스템 프롬프트 추가:**
```
## 과거 에피소드 구조 참고 (제공된 경우)
[과거 에피소드 기억 — 구조 참고] 섹션이 있으면,
이미 사용된 구조를 파악하여 대안 생성 시 다양성을 확보하세요.
단, 과거 구조 회피가 현재 사용자 상태에 맞지 않는다면 무시해도 됩니다.
```

**CoT 시스템 프롬프트 추가:**
```
## 과거 에피소드 스타일 참고 (제공된 경우)
[과거 에피소드 스타일 참고] 섹션이 있으면,
호칭 방식, 도입/마무리 톤, 문장 길이를 참고하여 일관된 경험을 제공하세요.
내용(주제·구조)이 아닌 스타일(말투·톤)만 참고합니다.
```

**settings.yaml 핀닝 변경:**
```yaml
prompts:
  versions:
    podcast_reasoning: "3.2.0"   # 3.1.0 → 3.2.0
```

---

## 테스트 계획

**파일**: `tests/agents/podcast/test_podcast_reasoning.py`

| # | 케이스 | 검증 내용 |
|---|--------|---------|
| 1 | GoT + memory_result 있음 | `"N건 발견"` 포함, 원문 텍스트 미포함 |
| 2 | ToT + memory_result 있음 | 에피소드 제목·날짜 포함, 원문 텍스트 미포함 |
| 3 | CoT + score ≥ threshold | 원문 발췌 200자 포함 |
| 4 | CoT + score < threshold | 해당 에피소드 원문 미포함 |
| 5 | CoT + memory_result=None | 기존 동작과 동일 (메모리 섹션 없음) |
| 6 | threshold 설정값 반영 | settings 값이 인스턴스에 로드되는지 확인 |

---

## 변경하지 않는 것

- `episode_memory.py` — 저장·검색 로직 그대로
- `_fetch_memory_if_needed()` — 호출 조건(complexity ≥ 0.6) 그대로
- GoT 관련 코드 — 기존 유지
- Knowledge Agent 관련 코드 — 이번 작업 범위 외

---

## 예상 효과

- **ToT**: 과거와 다른 에피소드 구조 선택 → 반복 에피소드 감소
- **CoT**: 사용자가 선호하는 말투·톤이 새 에피소드에 반영 → 개인화 품질 향상
- **GoT**: 오염 없이 현재 발화 기반의 순수한 그래프 유지 → Neo4j 데이터 정확도 유지

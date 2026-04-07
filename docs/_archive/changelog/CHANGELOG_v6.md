# 변경이력 v6 — 에피소드 3-5분 전파 + CoT/ToT/GoT 추론 파이프라인

> 계획서: `.claude/plans/expressive-churning-goblet.md`
> 날짜: 2026-02-11

---

## 배경

### Q1: 에피소드 길이 조정

초기 설계에서 에피소드 기본 길이가 10-20분으로 설정되어 있었다. 멘탈케어 콘텐츠 특성상 짧고 집중도 높은 에피소드가 효과적이므로, **3-5분 에피소드**로 전환했다.

### Q2+Q3: 추론 파이프라인

Podcast Reasoning이 단일 LLM 호출로 에피소드 구조를 설계하는 것은 복잡한 주제에 대해 깊이가 부족하다. 사용자 입력의 **복잡도(complexity_score)**에 따라 추론 깊이를 동적으로 조절하는 3단계 파이프라인을 도입했다.

---

## 변경 내용

### 1. 복잡도 기반 추론 깊이 결정

Intent Classifier가 반환하는 `complexity_score` (0.0~1.0)에 따라 추론 깊이를 3단계로 분류한다:

| 복잡도 범위 | 추론 깊이 | 전략 | LLM 호출 수 |
|------------|----------|------|------------|
| `>= 0.8` | `full` | GoT + ToT + CoT | 3회 |
| `>= 0.5` | `standard` | ToT + CoT | 2회 |
| `< 0.5` | `minimal` | CoT only | 1회 |

```python
def _determine_reasoning_depth(self, complexity: float) -> ReasoningDepth:
    if complexity >= 0.8:
        return "full"      # GoT + ToT + CoT
    elif complexity >= 0.5:
        return "standard"  # ToT + CoT
    else:
        return "minimal"   # CoT only
```

### 2. GoT (Graph of Thoughts) — 개념 관계 그래프

**실행 조건**: `complexity >= 0.8` (high complexity)

사용자 발화에서 개념, 감정, 경험을 노드(node)로, 관계를 엣지(edge)로 추출하여 그래프를 구성한다.

- **노드 수 제약**: 4~8개 (3-5분 에피소드 스케일에 맞춤)
- **엣지 수 제약**: 3~10개
- **출력**: `nodes`, `edges`, `core_pattern`, `insights`
- Neo4j 호환 JSON 구조

### 3. ToT (Tree of Thoughts) — 구조 대안 탐색

**실행 조건**: `complexity >= 0.5` (medium+ complexity)

3~5개의 에피소드 구조 대안을 생성하고, 4가지 기준으로 평가하여 최적안을 선택한다:

- 청취자 몰입도
- 멘탈케어 적합성
- **시간 효율성: 핵심 메시지를 3-5분 내에 전달 가능한가?**
- 구조 완전성

각 대안에는 세그먼트별 `duration_seconds`와 `focus`가 포함된다.

### 4. CoT (Chain of Thoughts) — 단계적 상세화

**실행 조건**: 항상 실행 (모든 복잡도)

선택된 구조를 단계별로 상세화하여 최종 에피소드 설계를 완성한다:

- 각 세그먼트: `duration_seconds`, `content_summary`, `tone`
- 감정 여정 5단계: opening → exploration → deepening → resolution → closing
- **설계 원칙: "에피소드 총 길이는 3-5분 내외로 설계"**

### 5. 3-5분 전파 (에피소드 길이 제약)

3-5분 에피소드 제약이 파이프라인 전체에 걸쳐 적용된다:

| 적용 위치 | 제약 내용 |
|----------|----------|
| GoT 프롬프트 | 노드 4-8개로 제한 (3-5분 스케일) |
| ToT 프롬프트 | 평가 기준에 "시간 효율성" 포함 |
| CoT 프롬프트 | "에피소드 총 길이는 3-5분 내외로 설계" 명시 |
| Batch Validator | 검증 기준 4번 "타이밍 적절성: 3-5분" |

### 6. 조건부 의존성 호출 강화

Episode Memory와 Knowledge Agent의 호출 조건을 복잡도 기반으로 보강:

- **Episode Memory**: `needs_memory=True` 또는 `complexity >= 0.6`
- **Knowledge Agent**: `needs_knowledge=True` 또는 `complexity >= 0.5`

---

## 영향 범위

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/podcast/podcast_reasoning.py` | 3단계 추론 파이프라인 (GoT/ToT/CoT), 복잡도 라우팅, 조건부 호출 강화 |
| `src/agents/podcast/content_analyzer.py` | 에피소드 분석 구조 유지 (프롬프트에서 길이 제약 반영) |
| `src/agents/podcast/batch_validator.py` | 검증 기준 4번 타이밍 적절성 (3-5분) |

### 출력 구조 변경

```python
reasoning_result = {
    "reasoning_depth": "full" | "standard" | "minimal",
    "reasoning_strategy": "GoT+ToT+CoT" | "ToT+CoT" | "CoT",
    "got_result": {...},          # depth == "full"일 때만
    "tot_result": {...},          # depth >= "standard"일 때만
    # CoT 결과는 최상위에 배치 (하위 호환)
    "episode_structure": [...],
    "narrative_flow": "...",
    "key_points": [...],
    "emotional_journey": [...],
    "confidence": 0.85,
}
```

---

## 검증

- 테스트 54개 전체 통과
- `black`, `ruff`, `isort`, `mypy` 통과

---

*마지막 업데이트: 2026-02-11*

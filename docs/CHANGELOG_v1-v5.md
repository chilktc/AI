# 변경이력 v1 ~ v5

> 계획서: `.claude/plans/expressive-churning-goblet.md`

---

## v1 — 개발자 역할 재배분 (2026-02-11)

### 배경

초기 설계에서 에이전트 담당을 재조정할 필요가 있었다. 팟캐스트모드와 대화모드 에이전트를 3명의 개발자에게 효율적으로 분배하기 위해 역할을 재배분했다.

### 변경 내용

| 개발자 | 대화모드 | 팟캐스트모드 |
|--------|---------|------------|
| 개발자1 | Intent Classifier, Knowledge, Synthesis, Personalization | Script Generator, Script Personalizer |
| 개발자2 | Safety, Memory, Visualization, Emotion | Episode Memory, Visualization(Podcast) |
| 개발자3 | Reasoning, Context, Validator, Learning | Podcast Reasoning, Content Analyzer, Batch Validator |
| 미정 | Telemetry Agent | — (전체 에이전트 완료 후 예정) |

### 영향

- 브랜치 접두사 규칙 확정: `feature/analysis-*`, `feature/reasoning-*`, `feature/validation-*`
- Protected Files 규칙 적용: `agent_state.py`, `message.py`, `contracts.py`, `workflow.py`

---

## v2 — 팟캐스트 모드 우선 개발 결정 (2026-02-11)

### 배경

대화모드(13개 에이전트)와 팟캐스트모드(7개 에이전트)를 동시에 개발하면 범위가 넓어진다. 팟캐스트 모드를 먼저 완성한 후 대화모드를 추가하는 전략을 채택했다.

### 변경 내용

- 팟캐스트 모드 에이전트를 먼저 구현 (Phase 0~4)
- 대화모드는 팟캐스트 안정화 후 순차 추가
- 공유 에이전트(Safety, Emotion, Intent Classifier 등)는 팟캐스트 구현 시 함께 설계

### 영향

- 개발자3 초기 구현 범위: Content Analyzer, Podcast Reasoning, Batch Validator, Learning Agent (4개)
- 대화모드 전용 에이전트(Validator, Personalization 등)는 이후 Phase에서 구현

---

## v3 — 코드 작성 원칙 (2026-02-11)

### 배경

3명의 개발자가 동시에 작업하므로 일관된 코드 스타일과 규칙이 필요했다.

### 변경 내용

5가지 코드 작성 원칙을 확정:

1. **한글 주석 필수** — 모든 클래스, 메서드, 복잡한 로직에 한글 주석
2. **미사용 코드 금지** — 현재 팟캐스트 모드에서 쓰지 않는 코드는 구현하지 않음
3. **API 모델 변경 유연** — `LLMClient`에서 모델명을 config로 관리, 하드코딩 금지
4. **메시지 프로토콜 준수** — v2.0 엔벨로프 형식 무조건 따름
5. **가독성 우선** — 다른 개발자가 봐도 바로 이해할 수 있는 명확한 코드

### 영향

- `config/settings.yaml`에서 모델명 관리 (`haiku`, `sonnet`, `opus`)
- `LLMClient`가 config에서 모델 ID를 자동 해석
- 모든 소스 파일에 한글 docstring 적용

---

## v4 — TIER 1 병렬 참조 결함 수정 (2026-02-11)

### 배경

초기 설계에서 Podcast Reasoning이 Content Analyzer의 `content_analysis`와 Emotion Agent의 `emotion_vectors`를 입력으로 사용하도록 되어 있었다. 그러나 이 4개 에이전트는 **TIER 1에서 병렬(Fan-out)** 실행되므로 서로의 결과를 참조할 수 없다.

### 문제

```
TIER 1 (병렬 Fan-out):
├─ Safety Agent       ─┐
├─ Emotion Agent      ─┤ 동시 실행 → 서로 참조 불가
├─ Content Analyzer   ─┤
└─ Podcast Reasoning  ─┘
```

Podcast Reasoning이 `content_analysis`(Content Analyzer)와 `emotion_vectors`(Emotion Agent)를 입력에서 참조하면, 아직 실행되지 않은 에이전트의 결과를 읽게 되어 빈 데이터가 들어온다.

### 변경 내용

- Podcast Reasoning의 입력에서 `content_analysis`와 `emotion_vectors` 제거
- Podcast Reasoning은 `user_input`과 `intent`(TIER 0 결과)만으로 독립 추론
- 같은 TIER 에이전트 간 참조 금지 원칙 명시

### 영향

- `src/agents/podcast/podcast_reasoning.py` — 입력 필드 변경
- 계획서의 에이전트 입출력 규약 업데이트
- TIER 간 데이터 흐름 재정립

---

## v5 — Batch Validator emotion_vectors 추가 (2026-02-11)

### 배경

Batch Validator(TIER 3)의 검증 기준 중 "톤 일관성"은 스크립트의 톤이 사용자 감정 상태에 적합한지 판단해야 한다. 이를 위해 Emotion Agent의 `emotion_vectors`가 필요하다.

### 문제

v4에서 같은 TIER 간 참조를 금지했지만, Batch Validator는 **TIER 3**이고 Emotion Agent는 **TIER 1**이므로 참조가 정당하다. 그러나 초기 설계에서 Batch Validator의 입력에 `emotion_vectors`가 누락되어 있었다.

### 변경 내용

- Batch Validator 입력에 `emotion_vectors` 추가
- 검증 기준 "톤 일관성"에서 감정 벡터 정보를 활용하도록 설계 보강

### 영향

- `src/agents/podcast/batch_validator.py` — `emotion_vectors` 입력 필드 추가
- 검증 로직에서 감정 상태 기반 톤 적절성 판단 강화

---

*마지막 업데이트: 2026-02-11*

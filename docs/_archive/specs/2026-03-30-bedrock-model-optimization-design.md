# Bedrock 모델 최적화 테스트 설계서

> 작성일: 2026-03-30
> 목적: 팟캐스트 파이프라인 에이전트별 최적 Bedrock 모델 선정

---

## 1. 테스트 목적

팟캐스트 파이프라인의 10개 에이전트 각각에 대해 AWS Bedrock 모델을 교체하며 **전체 파이프라인을 E2E 실행**하고, 종합지표(품질/일관성/속도/비용효율/신뢰성)를 통해 에이전트별 최적 모델을 선정한다. 최종적으로 최적 모델 조합의 파이프라인을 검증하여 현재 설정(baseline) 대비 개선율을 확인한다.

---

## 2. 테스트 대상

### 2.1 Claude 모델 (5개)

| 약칭 | 모델명 | Bedrock Model ID |
|------|--------|-----------------|
| c3-sonnet | Claude 3 Sonnet | `anthropic.claude-3-sonnet-20240229-v1:0` |
| c3-haiku | Claude 3 Haiku | `anthropic.claude-3-haiku-20240307-v1:0` |
| c35-sonnet-v1 | Claude 3.5 Sonnet v1 | `anthropic.claude-3-5-sonnet-20240620-v1:0` |
| c35-sonnet-v2 | Claude 3.5 Sonnet v2 | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| c37-sonnet | Claude 3.7 Sonnet | `anthropic.claude-3-7-sonnet-20250219-v1:0` |

### 2.2 에이전트 (10개 -- 팟캐스트 파이프라인 전체)

| # | 에이전트 | TIER | 기본 모델 | 테스트 모델 |
|---|---------|------|----------|-----------|
| 1 | Intent Classifier | TIER 0 | haiku | 2.1의 Claude 5개 |
| 2 | Safety Agent | TIER 1 (병렬) | sonnet | 2.1의 Claude 5개 |
| 3 | Emotion Agent | TIER 1 (병렬) | sonnet | 2.1의 Claude 5개 |
| 4 | Content Analyzer | TIER 1 (병렬) | sonnet | 2.1의 Claude 5개 |
| 5 | Podcast Reasoning | TIER 1 (병렬) | sonnet | 2.1의 Claude 5개 |
| 6 | Script Generator | TIER 2 | sonnet | 2.1의 Claude 5개 |
| 7 | Batch Validator | TIER 3 | sonnet | 2.1의 Claude 5개 |
| 8 | Script Personalizer | TIER 4 | sonnet | 2.1의 Claude 5개 |
| 9 | Visualization | 비동기 | sonnet + Titan v2 | Claude 5개 + 이미지 모델 3개 |
| 10 | Learning Agent | 비동기 | haiku | 2.1의 Claude 5개 |

> **모든 테스트는 전체 파이프라인 E2E 실행**이다. 대상 에이전트 1개의 모델만 교체하고, 나머지 에이전트는 기본값을 유지한 채 파이프라인을 실행한다.

> Episode Memory / Knowledge Agent는 Podcast Reasoning 내부에서 조건부 호출되므로, Podcast Reasoning 테스트 시 함께 영향을 받는다.

#### Visualization 스킵 정책

Visualization Agent는 이미지 생성 비용이 크므로, **Visualization 자체를 테스트할 때만 동작**한다. 다른 에이전트(1~8, 10번) 테스트 시에는 기존 `SKIP_VISUALIZATION=true` 환경변수로 스킵한다.

```
에이전트 1~8, 10 테스트 시: SKIP_VISUALIZATION=true  (Visualization 스킵)
에이전트 9 (Visualization) 테스트 시: SKIP_VISUALIZATION=false (정상 동작)
```

#### 2.2.1 이미지 생성 모델 (us-east-1 리전)

Visualization 테스트 시 교체 대상인 이미지 생성 모델 목록:

| 약칭 | 모델명 | Bedrock Model ID | 상태 | 비고 |
|------|--------|-----------------|------|------|
| titan-v2 | Amazon Titan Image Gen v2 | `amazon.titan-image-generator-v2:0` | Legacy (EOL 2026-06-30) | 현재 사용 중 |
| titan-v1 | Amazon Titan Image Gen v1 | `amazon.titan-image-generator-v1` | Legacy | 기능 제한 |
| nova-canvas | Amazon Nova Canvas | `amazon.nova-canvas-v1:0` | **Active** | 권장 대체 모델 |

> Stability AI text-to-image는 us-west-2 전용이므로 제외. Titan v2는 2026-06-30 EOL 예정.

### 2.3 테스트 입력 (고정)

기존 테스트 픽스처에서 E2E 테스트용 입력을 사용한다.

**소스**: `dev/live_tests/test_inputs/default_podcast.json` + `dev/live_tests/fixtures.py`의 `create_e2e_state()`

```python
# E2E 최소 입력 (IntentClassifier가 LLM으로 직접 분류)
{
    "user_input": "- 상황: 아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어...",
    "user_id": "user_e2e_graph_001",
    "session_id": "sess_e2e_graph_001",
    "mode": "podcast"
}
```

> intent가 사전 설정되지 않은 최소 입력으로, TIER 0 Intent Classifier부터 전체 파이프라인을 순차 실행한다.
> 변수 통제를 위해 모든 실행에서 동일 입력을 사용한다.

---

## 3. 테스트 구조 (5단계)

```
Phase 0: 연결 확인 --- Claude 5개 + 이미지 3개 = 8회 [AWS]
    |
Phase 0.5: 캘리브레이션 --- 동시성/메모리/Rate Limit 실측 ~10회 [AWS]
    |
Phase 1: 전체 파이프라인 벤치마크 --- 순차 또는 병렬 [AWS]
    |
    |  에이전트 1~8, 10 (Visualization 외):
    |    9에이전트 x 5모델 x 3회 = 135회 (SKIP_VISUALIZATION=true)
    |
    |  에이전트 9 (Visualization):
    |    Claude 5모델 x 3회 = 15회 + 이미지 3모델 x 3회 = 9회 = 24회
    |
    |  매 실행마다:
    |  1. 대상 에이전트의 모델 설정 변경
    |  2. Visualization 스킵 여부 설정
    |  3. 전체 파이프라인 E2E 실행
    |  4. 런타임 지표 자동 수집
    |  5. Evaluator Agent가 교체된 에이전트의 출력 품질 평가
    |  6. 결과 JSON 저장
    |
    +-- 결과 커밋 + 푸시 → 로컬 git pull
    |
Phase 2: 종합점수 산출 + 최적 모델 선정 [로컬]
    |  에이전트별 (모델 x 지표) 매트릭스 -> 가중 종합점수 -> 최적 모델 결정
    |
Phase 3: 최적 파이프라인 검증 [AWS]
    |  Phase 2 선정 조합으로 전체 파이프라인 5회 실행
    |  + Baseline(현재 설정) 5회 실행
    |  -> 성능 비교 및 개선율 산출
    |
    +-- 결과 커밋 + 푸시 → 로컬 git pull
    |
Phase 4: 보고서 생성 [로컬]
    |  Markdown (.md) 생성 — Claude Code가 결과 JSON을 분석하여 작성
```

> **실행 환경 분리**: Phase 0/0.5/1/3은 AWS EC2(Bedrock 접근 필요, Chrome MCP로 제어),
> Phase 2/4는 로컬(결과 JSON 읽기 + 계산/포맷팅만, Claude Code 활용). 상세: 섹션 11.

### 3.1 총 실행 횟수

| Phase | 내용 | Vis 스킵 | 실행 횟수 | 환경 |
|-------|------|---------|----------|------|
| Phase 0 | 연결 확인 (Claude 5 + 이미지 3) | - | 8회 | AWS |
| Phase 0.5 | 캘리브레이션 (동시성/메모리/Rate Limit) | 스킵 | ~10회 | AWS |
| Phase 1 | 에이전트 1~8, 10 벤치마크 (9 x 5모델 x 3회) | 스킵 | 135회 | AWS |
| Phase 1 | Visualization 벤치마크 (Claude 5 x 3 + 이미지 3 x 3) | 동작 | 24회 | AWS |
| Phase 2 | 종합점수 산출 + 최적 모델 선정 | - | - | 로컬 |
| Phase 3 | 최적 조합 (5회) + Baseline (5회) | 동작 | 10회 | AWS |
| Phase 4 | Markdown 보고서 생성 (Claude Code) | - | - | 로컬 |
| **합계 (LLM 호출)** | | | **~187회** | |

### 3.2 테스트 방식

**전체 파이프라인 E2E 실행**: 매 테스트마다 대상 에이전트 1개의 모델만 교체하고, 전체 파이프라인(TIER 0 ~ TIER 4 + 비동기)을 처음부터 끝까지 실행한다. 나머지 에이전트는 `settings.yaml` 기본값을 유지한다.

**TIER별 타임아웃 (현재 설정 기준)**:

| TIER | 타임아웃 | 비고 |
|------|---------|------|
| TIER 0 | 10초 | Intent Classifier |
| TIER 1 | 30초 | 병렬 4개 에이전트 |
| TIER 2 | 140초 | Script Generator + Visualization (Vis 스킵 시 단축) |
| TIER 3 | 50초 | Batch Validator + 재시도 |
| TIER 4 | 10초 | Script Personalizer |
| 비동기 | 30초 | Visualization + Learning |

> Visualization 스킵 시 TIER 2 소요 시간이 대폭 단축된다.
> 1회 파이프라인 예상 소요: Vis 스킵 시 ~2분, Vis 포함 시 ~4분.
> **전체 ~187회 예상 총 소요: 약 6~8시간** (캘리브레이션 + Evaluator 호출 포함).

### 3.3 실행 순서

매 실행마다 모델 설정이 변경되므로 기본적으로 **순차 실행**한다. 병렬 실행 방안은 섹션 11을 참조한다.

```
실행 루프 (순차 모드):
  for agent in 10개_에이전트:
      for model in 테스트_모델_목록:
          for run in [1, 2, 3]:
              1. Settings 싱글톤 리셋
              2. 대상 에이전트 모델 오버라이드
              3. Visualization 스킵 설정
                 - agent != "visualization" -> SKIP_VISUALIZATION=true
                 - agent == "visualization" -> SKIP_VISUALIZATION=false
              4. 전체 파이프라인 E2E 실행 (workflow.ainvoke)
              5. 런타임 지표 수집
              6. Evaluator Agent 평가
              7. 결과 JSON 저장
              8. 다음 실행을 위해 설정 초기화
```

> **동시성 격리 리팩토링 반영 (v27, 커밋 ffe5290)**:
> 에이전트 싱글톤이 제거되어 모든 노드 함수가 요청마다 새 인스턴스를 생성한다.
> 따라서 기존의 "에이전트 싱글톤 리프레시" 단계는 불필요하다.
> 워크플로우 수준(`ainvoke()`)에서는 동시 실행이 안전하나,
> Settings 싱글톤 패치 + 환경변수(`SKIP_VISUALIZATION` 등)가 프로세스 전역이므로
> **동일 프로세스 내 병렬 실행 시 설정 충돌이 발생**한다.
> 병렬 실행을 위한 구체적 방안은 섹션 11에서 다룬다.

---

## 4. Evaluator Agent (자체 평가 에이전트)

### 4.1 개요

Evaluator Agent는 전체 파이프라인 실행 후, 교체된 에이전트의 출력을 독립적으로 평가하는 **채점 에이전트**이다. 향후 프로젝트 파이프라인의 비동기 에이전트로 편입 가능하도록 **별도 모듈**로 설계한다.

- **위치**: `dev/live_tests/evaluator_agent.py` (테스트 코드)
- **평가 기준 정의**: `dev/live_tests/evaluator_criteria.py` (에이전트별 평가 항목)
- **향후 확장**: 비동기 에이전트로 파이프라인에 추가 시 `src/agents/shared/`로 이동하고 `BaseAgent` 상속으로 전환 가능
- **평가 모델**: Claude 3.5 Sonnet v2 (고정) -- 평가 기준 일관성을 위해 평가자 모델은 변경하지 않음
- **평가 방식**: 에이전트 출력 + 원본 입력 + 파이프라인 컨텍스트를 Evaluator에게 전달 -> 항목별 점수(0~1) + 한 줄 근거 반환

### 4.1.1 모듈 설계 원칙

```
현재 (테스트 용도):
  dev/live_tests/run_bedrock_model_test.py
      -> from dev.live_tests.evaluator_agent import EvaluatorAgent
      -> evaluator.evaluate(agent_name, output, input, context)

향후 (파이프라인 비동기 에이전트):
  src/agents/shared/evaluator.py 로 이동
      -> class EvaluatorAgent(BaseAgent) 로 전환
      -> workflow.py에 비동기 노드로 등록
      -> 매 파이프라인 실행 후 자동 품질 모니터링
```

- 평가 기준을 `evaluator_criteria.py`에 분리하여 에이전트 추가/변경 시 기준만 수정
- LLM 호출은 `llm_client.py`를 사용하여 프로바이더 독립적으로 동작
- 평가 결과 스키마는 `AgentState`에 추가 가능한 형태로 설계

### 4.2 공통 평가 항목 (모든 에이전트, 6항목)

| 항목 | 설명 |
|------|------|
| 구조적 완성도 | 필수 필드 존재, 스키마 준수, 타입 정확성 |
| 출력 안정성 | JSON 파싱 가능, 예외 없이 정상 종료 |
| 지시 준수도 | 프롬프트에서 요구한 형식/제약 조건 이행 여부 |
| 한국어 품질 | 자연스러운 한국어 표현, 어색한 번역체 여부 |
| 환각(Hallucination) | 입력에 없는 정보 생성, 사실 왜곡 여부 |
| 토큰 효율성 | 불필요한 반복/장황함 없이 핵심을 전달하는가 |

### 4.3 에이전트별 전문 평가 항목

#### Intent Classifier (TIER 0) -- 5항목

| 항목 | 설명 |
|------|------|
| 의도 분류 정확성 | 입력 발화에 대한 intent 분류가 적절한가 |
| 모드 감지 정확성 | conversation/podcast 모드 판별이 맞는가 |
| complexity_score 합리성 | 입력 복잡도를 적절히 반영하는가 |
| risk_flag 민감도 | 1차 위기 감지가 과민/둔감하지 않은가 |
| execution_plan 적절성 | 후속 TIER에 전달할 실행 계획이 합리적인가 |

#### Safety Agent (TIER 1) -- 6항목

| 항목 | 설명 |
|------|------|
| 위기 감지 정확성 | 위험 수준(safe/warning/crisis) 판정이 입력에 부합하는가 |
| risk_level 세분화 | 0~4 레벨이 미세한 뉘앙스를 잘 구분하는가 |
| risk_score 정밀도 | 0.0~1.0 점수가 위험도를 정량적으로 잘 반영하는가 |
| False Positive 통제 | 안전한 입력을 위험하다고 오판하지 않는가 |
| False Negative 통제 | 위험한 입력을 안전하다고 놓치지 않는가 |
| 근거 제시 | 판정 이유를 명확히 설명하는가 |

#### Emotion Agent (TIER 1) -- 6항목

| 항목 | 설명 |
|------|------|
| 감정 식별 정확성 | 입력에서 드러나는 감정을 정확히 포착하는가 |
| 벡터 다양성 | 단일 감정이 아닌 복합 감정을 포착하는가 |
| 강도 합리성 | 감정 강도(intensity)가 맥락에 비례하는가 |
| 미묘한 감정 탐지 | 직접 표현되지 않은 내재된 감정을 읽어내는가 |
| 감정 간 관계성 | 복합 감정 간 상호 관계(예: 분노 뒤의 슬픔)를 파악하는가 |
| 문화적 맥락 반영 | 한국 문화권 감정 표현의 뉘앙스를 이해하는가 |

#### Content Analyzer (TIER 1) -- 6항목

| 항목 | 설명 |
|------|------|
| 주제 추출 완성도 | 핵심 주제와 부수 주제를 빠짐없이 식별하는가 |
| 구조화 품질 | 추출된 분석이 논리적으로 잘 정리되어 있는가 |
| 분석 깊이 | 표면적 요약이 아닌 심층 분석을 제공하는가 |
| 팟캐스트 적합성 | 분석 결과가 팟캐스트 에피소드 생성에 활용 가능한가 |
| 핵심 인용 추출 | 사용자 발화에서 핵심 표현을 정확히 포착하는가 |
| emotional_journey 구성 | 감정 흐름 구성이 자연스럽고 풍부한가 |

#### Podcast Reasoning (TIER 1) -- 6항목

| 항목 | 설명 |
|------|------|
| 추론 깊이 | 단순 요약이 아닌 다단계 추론을 수행하는가 |
| 논리적 일관성 | 추론 과정에 모순이나 비약이 없는가 |
| 추론 전략 적절성 | GoT/ToT/CoT 전략 선택이 입력 복잡도에 맞는가 |
| Memory/Knowledge 호출 판단 | 독립 에이전트 호출 필요성 판단이 적절한가 |
| 다각적 관점 제시 | 하나의 해석에 고착되지 않고 복수 관점을 탐색하는가 |
| 실행 가능한 인사이트 | 추론 결과가 스크립트 생성에 실질적으로 활용 가능한가 |

#### Script Generator (TIER 2) -- 6항목

| 항목 | 설명 |
|------|------|
| 스크립트 구조 완성도 | 인트로/본문/클로징 등 구조가 갖춰져 있는가 |
| 내러티브 자연스러움 | 대본이 자연스럽게 읽히고 흐름이 매끄러운가 |
| TIER 1 결과 반영도 | Safety/Emotion/Content/Reasoning 결과가 스크립트에 반영되는가 |
| Safety 경고 통합 | Safety warning이 스크립트에 적절히 포함되는가 |
| 청취자 몰입도 | 팟캐스트로서 듣고 싶은 매력이 있는가 |
| 분량 적절성 | 너무 짧거나 장황하지 않은 적정 분량인가 |

#### Batch Validator (TIER 3) -- 6항목

| 항목 | 설명 |
|------|------|
| BV Score 자체 | 산출된 품질 점수 (기존 핵심 지표) |
| 검증 정밀도 | 실제 문제를 정확히 짚어내는가 |
| 피드백 구체성 | "부족함" 수준이 아닌 구체적 개선점을 제시하는가 |
| 피드백 실행 가능성 | 제시된 피드백으로 실제 개선이 가능한가 |
| 채점 일관성 | 동일 품질의 입력에 대해 유사한 점수를 부여하는가 |
| 기준 엄격도 균형 | 너무 관대하거나 가혹하지 않은 적정 수준인가 |

#### Script Personalizer (TIER 4) -- 6항목

| 항목 | 설명 |
|------|------|
| 톤 적절성 | 사용자 감정 상태에 맞는 톤으로 조정되었는가 |
| 개인화 수준 | 일반적 응답이 아닌 사용자 맥락이 반영된 조정인가 |
| Safety 경고 톤 강화 | warning 시 톤이 적절히 강화되었는가 |
| 원본 보존도 | 개인화 과정에서 핵심 내용이 손실되지 않았는가 |
| 공감 표현 | 사용자 상황에 대한 공감이 자연스럽게 드러나는가 |
| 일관된 페르소나 | 전체 스크립트에서 일관된 화자 톤이 유지되는가 |

#### Visualization (비동기) -- 5항목

| 항목 | 설명 |
|------|------|
| 시각 메타데이터 품질 | 색상/구도/분위기 등 메타데이터가 풍부한가 |
| 이미지 프롬프트 적절성 | 생성된 프롬프트가 감정 상태를 잘 표현하는가 |
| 감정-시각 매핑 정확성 | 감정 벡터와 시각적 표현이 일치하는가 |
| 창의성 | 진부하지 않은 독창적 시각 표현을 제안하는가 |
| 실현 가능성 | 이미지 생성 모델이 실제로 렌더링 가능한 프롬프트인가 |

#### Learning Agent (비동기) -- 5항목

| 항목 | 설명 |
|------|------|
| 인사이트 유용성 | 추출된 학습 인사이트가 향후 대화에 활용 가능한가 |
| 패턴 추출 정확성 | 사용자 행동/감정 패턴을 정확히 식별하는가 |
| 과적합 방지 | 단일 대화에서 과도한 일반화를 하지 않는가 |
| 프라이버시 존중 | 민감 정보를 부적절하게 기록하지 않는가 |
| 저장 데이터 구조화 | 학습 결과가 잘 구조화되어 검색 가능한가 |

> 에이전트당 총 평가 항목: 공통 6 + 전문 5~6 = **11~12항목**

---

## 5. 수집 지표

### 5.1 매 실행마다 수집

```
전체 파이프라인 E2E 실행 1회당 수집 데이터:
|
+-- 런타임 지표 (자동 수집)
|   +-- 교체 에이전트 추론 시간 (초)
|   +-- 전체 파이프라인 시간 (초)
|   +-- 토큰 사용량 -- input / output / total
|   +-- 에러 발생 여부 -- 타임아웃, 파싱 실패, API 에러
|   +-- 필드 완성도 -- 8개 필수 필드 존재 여부
|
+-- Evaluator 평가 지표 (LLM 채점)
|   +-- 공통 6항목 점수 (각 0~1)
|   +-- 에이전트별 전문 5~6항목 점수 (각 0~1)
|   +-- 항목별 한 줄 근거
|
+-- 파이프라인 영향 지표
    +-- BV Score -- 전체 파이프라인 품질
    +-- final_output 길이
    +-- Confidence
```

### 5.2 3회 반복 후 통계 (에이전트-모델 쌍마다)

| 통계 | 용도 |
|------|------|
| 평균 (mean) | 해당 모델의 일반적 성능 수준 |
| 표준편차 (std) | 일관성 -- 낮을수록 안정적 |
| 최솟값 (min) | 최악의 경우 품질 하한선 |
| 실패율 | 3회 중 에러 발생 비율 |

---

## 6. 종합점수 산출

### 6.1 공식

```
종합점수 = (품질 x 0.35) + (일관성 x 0.25) + (속도 x 0.15) + (비용효율 x 0.10) + (신뢰성 x 0.15)
```

### 6.2 차원별 산출 방식

| 차원 | 산출 방식 | 가중치 |
|------|----------|--------|
| 품질 | Evaluator 전체 항목 평균점수의 3회 평균 | 35% |
| 일관성 | Evaluator 점수의 표준편차 역수 정규화 (`1 - std/max_std`) | 25% |
| 속도 | 에이전트 추론시간 역수 정규화 (`1 - time/max_time`) | 15% |
| 비용효율 | 총 토큰 사용량 역수 정규화 (`1 - tokens/max_tokens`) | 10% |
| 신뢰성 | `1 - 실패율` (에러/타임아웃 없이 완료한 비율) | 15% |

> 정규화: 동일 에이전트의 모델 결과 내에서 min-max 정규화 (0~1 범위)

### 6.3 가중치 설정 (외부 조정 가능)

```python
DEFAULT_WEIGHTS = {
    "quality": 0.35,
    "consistency": 0.25,
    "speed": 0.15,
    "cost_efficiency": 0.10,
    "reliability": 0.15,
}
```

가중치는 테스트 스크립트의 설정 파라미터로 외부에서 변경 가능하게 구현한다.

### 6.4 최적 모델 선정 기준

```
에이전트별:
  1순위: 종합점수 최고 모델
  2순위: 종합점수 동률 시 -> 일관성(std) 낮은 모델 우선
  3순위: 일관성도 동률 시 -> 속도 빠른 모델 우선
```

---

## 7. Phase 3: 최적 파이프라인 검증

```
Phase 2 결과: 에이전트별 최적 모델 선정
    |
Step 1: 최적 조합 파이프라인 구성
    예시: Intent(c3-haiku) + Safety(c35-sonnet-v2) + Emotion(c37-sonnet) + ...
    |
Step 2: 최적 조합 5회 실행 (Evaluator 전체 평가 포함)
    |
Step 3: Baseline(현재 settings.yaml 설정) 5회 실행
    |
Step 4: 비교 분석
    +-- 에이전트별 품질 비교 (최적 vs baseline)
    +-- 파이프라인 전체 BV Score 비교
    +-- 총 추론 시간 비교
    +-- 총 토큰 비용 비교
    +-- 개선율(%) 산출
```

---

## 8. 결과 문서 구조

### 8.1 JSON 개별 결과 (자동 생성)

```
dev/live_tests/results/bedrock_model_test/
+-- calibration.json                                         # 캘리브레이션 결과
+-- progress.json                                            # 진행 상황 추적 (재개용)
+-- phase0/
|   +-- connectivity_{model_short}_{timestamp}.json          # 8개
+-- phase1/
|   +-- {agent}_{model_short}_run{n}_{timestamp}.json        # 159개
+-- phase3/
|   +-- optimal_{run_n}_{timestamp}.json                     # 5개
|   +-- baseline_{run_n}_{timestamp}.json                    # 5개
+-- summary/
    +-- aggregated_results.json                              # 전체 통계 집계
```

### 8.2 Markdown 보고서 (로컬에서 생성)

**경로**: `dev/live_tests/results/bedrock_model_test/bedrock_model_comparison_report.md`

AWS에서 커밋된 결과 JSON을 git pull한 뒤, **Claude Code가 결과 JSON을 분석**하여 Markdown 보고서를 생성한다. 외부 패키지(openpyxl 등) 없이, `scoring.py`의 집계 결과 + Claude Code의 분석 능력으로 보고서를 작성한다.

**보고서 구성**:

```markdown
# Bedrock 모델 비교 테스트 보고서

## 1. 테스트 개요 (환경, 총 실행 횟수, 캘리브레이션 요약)
## 2. 에이전트별 최적 모델 결과 (10개 에이전트 x 5모델 종합점수 매트릭스)
## 3. 에이전트별 상세 (런타임, Evaluator 항목별 점수, 통계)
##    3.1 Intent Classifier
##    3.2 Safety Agent
##    ...
##    3.10 Learning Agent
## 4. Phase 3 최적 파이프라인 검증 (최적 조합 vs Baseline 비교)
## 5. 종합점수 산출 상세 (가중치, 정규화 과정)
## 6. 권장 사항
```

> **패키지 추가 없이 보고서 생성**: 외부 패키지를 설치하지 않는다.
> `scoring.py`가 JSON 집계를 수행하고, Claude Code가 집계 결과를 읽어 Markdown으로 정리한다.
> 상세: 섹션 11.6.

### 8.3 Markdown 요약 보고서

**경로**: `docs/reports/bedrock_model_comparison.md`

```
# Bedrock 모델 비교 테스트 보고서

## 1. 테스트 개요
## 2. 에이전트별 최적 모델 결과
## 3. 종합점수 분석
## 4. 최적 파이프라인 검증 결과
## 5. 권장 사항
## 6. 상세 데이터 참조
```

---

## 9. 기술 구현 개요

### 9.1 신규 파일 구조

```
dev/live_tests/
+-- run_bedrock_model_test.py          # 오케스트레이터 (Phase 관리 + 병렬 제어) [AWS]
+-- run_single_bedrock_test.py         # 단일 테스트 워커 (subprocess로 호출) [AWS]
+-- evaluator_agent.py                 # Evaluator Agent 구현 [AWS]
+-- evaluator_criteria.py              # 에이전트별 평가 기준 정의 [AWS]
+-- scoring.py                         # 종합점수 산출 로직 [로컬]
+-- results/bedrock_model_test/        # 결과 디렉토리 (AWS에서 생성, git으로 로컬 전달)
```

> **실행 환경 구분**: [AWS] 표시 파일은 EC2에서 실행 (LLM 호출 필요),
> [로컬] 표시 파일은 로컬에서 실행 (결과 JSON 읽기 + 계산만). 상세: 섹션 11.
>
> Evaluator Agent는 향후 파이프라인 편입 시 `src/agents/shared/`로 이동하고 `BaseAgent` 상속으로 전환한다. 현재는 `dev/live_tests/` 내에서 독립적으로 동작한다.

### 9.2 Bedrock API 현황

현재 코드는 두 가지 Bedrock API를 사용한다:

- **텍스트 생성 (Claude)**: `Converse API` (`bedrock_client.converse()`) -- invoke_model에서 마이그레이션 완료
- **이미지 생성 (Titan/Nova)**: `invoke_model` API -- Converse API 미지원

> Nova Canvas 테스트 시 `invoke_model` API의 요청 포맷이 Titan과 다를 수 있으므로, `base_agent.py`의 `_generate_image_bedrock()` 메서드 호환성을 Phase 0에서 확인한다.

### 9.3 모델 교체 메커니즘

에이전트별 모델 교체는 `settings.yaml`의 에이전트 설정(`agents.{agent_name}.model`)을 런타임에 패치하는 방식으로 구현한다. 기존 `run_prompt_iteration.py`에서 사용한 Settings 싱글톤 리셋 패턴(에이전트 싱글톤과 무관 — Settings 설정 객체의 리셋)을 활용한다.

> **동시성 격리 반영**: v27 리팩토링으로 에이전트 싱글톤이 제거되었다.
> 모든 에이전트 노드 함수는 호출 시마다 새 인스턴스를 생성하므로,
> Settings 패치 후 별도의 에이전트 리프레시가 불필요하다.
> 새 인스턴스가 생성될 때 변경된 Settings 값을 자동으로 읽는다.

```python
# 대상 에이전트만 모델 교체, 나머지는 기본값 유지
def override_agent_model(agent_name: str, bedrock_model_id: str):
    settings = get_settings()
    agent_cfg = settings._config.setdefault("agents", {}).setdefault(agent_name, {})
    agent_cfg["model_id"] = bedrock_model_id
    # 에이전트 싱글톤 리프레시 불필요 — 노드 함수가 매번 새 인스턴스를 생성하므로
    # 다음 ainvoke() 시 변경된 model_id가 자동 반영된다.
```

### 9.4 Evaluator Agent 호출 방식

```python
# 전체 파이프라인 E2E 실행
pipeline_result = await workflow.ainvoke(initial_state)

# 교체된 에이전트의 출력만 추출
agent_output = extract_agent_output(pipeline_result, target_agent)

# Evaluator Agent 채점 (고정 모델: Claude 3.5 Sonnet v2)
evaluation = await evaluator.evaluate(
    agent_name=target_agent,
    agent_output=agent_output,
    user_input=test_input,
    pipeline_context=pipeline_result,
)
# evaluation = { "common": {...}, "specialized": {...}, "total_score": 0.85 }
```

### 9.5 환경 요구사항

- AWS EC2 인스턴스 (Bedrock 접근 권한 설정 완료)
- Claude 5개 + 이미지 3개 모델 전체 Model Access 승인 필요
- Python 3.11+, boto3 (기존 requirements.txt 패키지만 사용, 추가 설치 없음)
- 환경변수: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (또는 IAM Role)

### 9.6 참고 파일

| 파일 | 용도 |
|------|------|
| `dev/live_tests/test_e2e_podcast.py` | 기존 팟캐스트 E2E 테스트 (참고용) |
| `dev/live_tests/run_prompt_iteration.py` | 프롬프트 이터레이션 러너 (Settings 리셋 패턴, `--skip-viz` 플래그 참고) |
| `dev/live_tests/conftest_live.py` | 테스트 인프라 유틸리티 (`setup_provider`, `Timer` 등) |
| `dev/live_tests/fixtures.py` | 테스트 픽스처 (`create_e2e_state()`) |

---

## 10. 제약 사항 및 주의점

1. **Evaluator 모델 고정**: 평가 일관성을 위해 Evaluator는 항상 Claude 3.5 Sonnet v2를 사용한다. Evaluator 자체의 편향이 존재할 수 있으므로, 절대적 점수보다 모델 간 상대 비교에 초점을 둔다.
2. **단일 입력 한계**: 1개 입력으로 테스트하므로 특정 유형의 입력에 대한 성능만 반영된다. 향후 다양한 입력으로 확장 테스트를 고려할 수 있다.
3. **비용**: ~187회 파이프라인 실행 + Evaluator 호출로 Bedrock API 비용이 발생한다. 135회는 Visualization 스킵으로 이미지 생성 비용을 절감한다.
4. **모델 가용성**: AWS 리전 및 계정에 따라 일부 모델이 사용 불가할 수 있다. Phase 0에서 사전 확인한다.
5. **Episode Memory/Knowledge**: Podcast Reasoning 내부에서 조건부 호출되므로, 해당 독립 에이전트의 모델은 직접 교체하지 않는다. Podcast Reasoning 모델 교체 시 간접적으로 영향을 받는다.
6. **Visualization 리전 분리**: 텍스트 기획(Claude)은 `ap-northeast-2`, 이미지 생성(Titan/Nova)은 `us-east-1`에서 실행된다. 리전 간 지연시간이 추론 시간에 포함된다.
7. **Titan v2 EOL**: 현재 사용 중인 `amazon.titan-image-generator-v2:0`는 2026-06-30 지원 종료 예정이다. 테스트 결과에 따라 Nova Canvas 마이그레이션을 권장할 수 있다.
8. **순차 실행 (기본)**: v27 동시성 격리로 에이전트 인스턴스는 요청별 격리되었으나, Settings 싱글톤 패치와 환경변수(`SKIP_VISUALIZATION`, `LLM_BEDROCK_MODEL_*`)가 프로세스 전역이므로 **동일 프로세스 내 병렬 실행 시 설정 충돌**이 발생한다. 기본적으로 순차 실행하되, 섹션 11의 병렬 실행 방안을 선택적으로 적용할 수 있다.
9. **Nova Canvas API 호환성**: 현재 `base_agent.py`의 `_generate_image_bedrock()`는 Titan 요청 포맷으로 구현되어 있다. Nova Canvas는 요청 포맷이 다를 수 있으므로 Phase 0에서 호환성을 확인하고, 필요 시 분기 로직을 추가한다.
10. **Converse API**: 텍스트 생성은 Converse API로 마이그레이션 완료 상태이다. 토큰 사용량 필드가 `inputTokens`/`outputTokens` (camelCase)이므로 수집 코드에서 이를 반영한다.

---

## 11. 테스트 실행 전략

### 11.1 실행 환경

#### AWS EC2 인스턴스 (테스트 실행)

| 항목 | 값 | 비고 |
|------|---|------|
| 인스턴스 | app-2 (t3.medium) | Private IP: <APP2_IP> |
| vCPU | 2 | 버스팅 가능 (T3 크레딧) |
| RAM | 3.8GB | Swap 미설정 (설정 필요) |
| 디스크 | 29GB (여유 ~11GB) | Docker 이미지 9.1GB 차지 |
| OS | Ubuntu 22.04 LTS | Python 3.13 (.venv) |
| 접속 | AWS SSM (SSH 차단) | Session Manager 또는 send-command |
| Bedrock 리전 | ap-northeast-2 (텍스트), us-east-1 (이미지) | APAC inference profile 필수 |

> **메모리 제약**: t3.medium 3.8GB에서 Docker 컨테이너가 상주하면 가용 메모리가 ~1.5~2GB로 줄어든다.
> 테스트 실행 시 **Docker 컨테이너를 중지**하고 네이티브 Python으로 실행하거나,
> 컨테이너 내부에서 실행하되 메모리 모니터링을 필수로 한다.

> **Swap 설정 필수**: 테스트 전에 2GB Swap을 설정하여 OOM 방지:
> ```bash
> sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
> sudo mkswap /swapfile && sudo swapon /swapfile
> echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
> ```

#### Bedrock 모델 ID (APAC Inference Profile)

ap-northeast-2에서 Sonnet/Opus는 on-demand가 지원되지 않으므로 **APAC cross-region inference profile** ID를 사용한다:

| 약칭 | 테스트용 Bedrock Model ID | 비고 |
|------|--------------------------|------|
| c3-sonnet | `apac.anthropic.claude-3-sonnet-20240229-v1:0` | APAC 필요 여부 Phase 0에서 확인 |
| c3-haiku | `anthropic.claude-3-haiku-20240307-v1:0` | on-demand 지원 |
| c35-sonnet-v1 | `apac.anthropic.claude-3-5-sonnet-20240620-v1:0` | APAC 필요 |
| c35-sonnet-v2 | `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | 현재 기본값 |
| c37-sonnet | `apac.anthropic.claude-3-7-sonnet-20250219-v1:0` | APAC 필요 |

> Phase 0 연결 확인 시 각 모델의 `apac.` 접두사 필요 여부를 실측한다.
> on-demand로 직접 호출이 가능한 모델은 접두사 없이 사용한다.

#### 로컬 환경 (보고서 생성)

| 항목 | 값 |
|------|---|
| 역할 | 결과 JSON → Markdown 보고서 생성 |
| 추가 패키지 | 없음 (기존 패키지만 사용) |
| Claude Code | 로컬에서 scoring.py 실행 + 결과 분석 + Markdown 보고서 작성 |

#### AWS 인스턴스 제어: Chrome MCP

Claude Code 데스크톱 앱에서 **Chrome MCP**를 통해 AWS EC2 인스턴스를 직접 제어한다.
SSM Session Manager 웹 콘솔을 Chrome MCP로 조작하여 명령어 입력, 로그 조회, 모니터링이 가능하다.

| 기능 | Chrome MCP 활용 |
|------|----------------|
| 명령어 실행 | SSM 세션에 직접 입력 (테스트 러너 실행, git 명령 등) |
| 로그 조회 | stdout/stderr 실시간 확인, progress.json 확인 |
| 메모리 모니터링 | `free -m`, `cat /proc/meminfo` 직접 실행 |
| 장애 대응 | 오류 발생 시 즉시 파라미터 조정 + 재실행 |
| 파일 확인 | 결과 JSON 내용 확인, 디스크 사용량 확인 |

> **반자동 워크플로우**: Chrome MCP로 AWS 인스턴스를 조작하므로,
> 완전 자동화가 아닌 **사람이 모니터링하며 필요 시 개입**하는 방식이다.
> 캘리브레이션 결과를 보고 동시성 파라미터를 직접 조정할 수 있다.

### 11.2 전체 워크플로우: AWS 실행 → 로컬 분석

```
[Claude Code 데스크톱 앱]
    │
    ├── Chrome MCP ──→ [AWS EC2 SSM 세션]
    │                       │
    │               Phase 0: 연결 확인 (8회)
    │                       ↓
    │               Phase 0.5: 캘리브레이션
    │                  │  동시 프로세스 수 실측
    │                  │  Bedrock Rate Limit 실측
    │                  │  메모리 사용량 실측 (free -m)
    │                  │  → calibration.json 저장
    │                  │  → 결과 확인 후 파라미터 조정
    │                       ↓
    │               Phase 1: 벤치마크 (159회)
    │                  │  결과 JSON 저장
    │                  │  progress.json으로 진행 확인
    │                       ↓
    │               Phase 3: 최적 조합 검증 (10회)
    │                       ↓
    │               git add + commit + push
    │                       │
    └── 로컬 터미널 ──→ git pull
                            ↓
                     Phase 2: 종합점수 산출 (scoring.py)
                            ↓
                     Phase 4: Markdown 보고서 생성
                        │  Claude Code가 JSON 분석 → .md 작성
                            ↓
                     보고서 커밋 + 푸시
```

**역할 분리 원칙**:
- **AWS (Chrome MCP 제어)**: 파이프라인 실행 + Evaluator 채점 + 결과 JSON 저장
- **로컬 (Claude Code CLI)**: 결과 집계 + 통계 산출 + Markdown 보고서 생성
- **패키지 제약**: 기존 requirements.txt/requirements-dev.txt의 패키지만 사용. 추가 설치 없음.

### 11.3 Phase 0.5: 캘리브레이션 (사전 실측)

테스트 본실행 전에 EC2 인스턴스의 **실제 한계를 측정**하여 최적 실행 파라미터를 결정한다.
설계서의 이론값이 아닌, 실측값 기반으로 동적 튜닝한다.

#### 캘리브레이션 항목

| # | 항목 | 측정 방법 | 결정하는 파라미터 |
|---|------|----------|-----------------|
| C-1 | 단일 파이프라인 메모리 | 1회 E2E 실행 중 RSS 피크 측정 | 동시 프로세스 상한 |
| C-2 | 단일 파이프라인 소요시간 | Vis 스킵/포함 각 1회 실행 | 전체 소요시간 예측 |
| C-3 | 동시 2프로세스 안정성 | 2개 서브프로세스 동시 실행 | 병렬 실행 가능 여부 |
| C-4 | 동시 3프로세스 안정성 | 3개 서브프로세스 동시 실행 | 최대 동시성 |
| C-5 | Bedrock Rate Limit | 빠르게 5회 연속 호출 후 ThrottlingException 확인 | API 호출 간격 |
| C-6 | 가용 메모리 확인 | `free -m` + Docker 상태 확인 | Docker 중지 여부 결정 |

#### 캘리브레이션 실행 절차

```bash
# EC2 SSM 접속 후 실행
cd /home/ubuntu/app

# 0. 사전 준비: Swap 설정 + Docker 상태 확인
free -m                           # 가용 메모리 확인
docker stats --no-stream          # Docker 메모리 사용 확인
sudo swapon --show                # Swap 확인 (없으면 위 11.1의 명령으로 생성)

# 1. Docker 중지 (메모리 확보)
docker compose down               # 가용 메모리를 최대화
free -m                           # 중지 후 가용 메모리 재확인

# 2. 캘리브레이션 실행
python -m dev.live_tests.run_bedrock_model_test --phase calibration

# 또는 수동 단계별 실행:
# C-1: 단일 파이프라인 메모리 측정
python -m dev.live_tests.run_bedrock_model_test --phase calibration --step memory

# C-3~C-4: 동시성 테스트 (2개 → 3개 순차적으로)
python -m dev.live_tests.run_bedrock_model_test --phase calibration --step concurrency

# C-5: Bedrock Rate Limit 측정
python -m dev.live_tests.run_bedrock_model_test --phase calibration --step ratelimit
```

#### 캘리브레이션 결과 저장

```json
// dev/live_tests/results/bedrock_model_test/calibration.json
{
  "timestamp": "2026-03-31T10:00:00Z",
  "instance": {
    "type": "t3.medium",
    "vcpu": 2,
    "total_ram_mb": 3836,
    "swap_mb": 2048,
    "available_ram_mb": 2100,
    "docker_stopped": true
  },
  "single_pipeline": {
    "memory_peak_mb": 850,
    "duration_sec_skip_viz": 77,
    "duration_sec_with_viz": 130
  },
  "concurrency": {
    "max_safe_processes": 2,
    "2_processes": {"status": "ok", "peak_memory_mb": 1600, "duration_sec": 85},
    "3_processes": {"status": "oom_risk", "peak_memory_mb": 2400, "notes": "swap 사용 시작"}
  },
  "bedrock_ratelimit": {
    "model": "apac.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "burst_5_result": "ok",
    "throttle_detected": false,
    "estimated_rpm": 60
  },
  "recommended": {
    "max_concurrent": 2,
    "execution_mode": "subprocess",
    "estimated_total_hours": 4.5,
    "notes": "t3.medium에서 2병렬이 안전 상한. 3병렬은 swap 의존으로 비권장."
  }
}
```

> **캘리브레이션 결과에 따른 분기**:
> - `max_safe_processes >= 2` → 서브프로세스 병렬 실행 (11.4)
> - `max_safe_processes == 1` → 순차 실행으로 폴백 (섹션 3.3)
> - OOM 발생 → Docker 중지 확인, Swap 설정 확인 후 재시도

#### 메모리 모니터링 방법

Chrome MCP를 통해 `free -m` 등의 명령어를 직접 실행하거나,
테스트 스크립트 내부에서 `/proc/meminfo`를 파싱하여 수집한다 (외부 패키지 불필요).

```bash
# Chrome MCP에서 직접 실행:
free -m && echo "---" && ps aux --sort=-%mem | head -5
```

```python
# 테스트 스크립트 내부에서 자동 수집 (/proc/meminfo 파싱, 패키지 불필요):
def get_memory_usage() -> dict[str, int]:
    """가용 메모리를 /proc/meminfo에서 읽는다 (psutil 대체)."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if parts[0] in ("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"):
                info[parts[0].rstrip(":")] = int(parts[1]) // 1024  # kB → MB
    return {
        "total_mb": info.get("MemTotal", 0),
        "available_mb": info.get("MemAvailable", 0),
        "swap_total_mb": info.get("SwapTotal", 0),
        "swap_used_mb": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
    }
```

### 11.4 실행 방안: 서브프로세스 분리

t3.medium의 자원 제약을 고려하여 **서브프로세스(subprocess) 방식**을 채택한다.
각 테스트를 독립 Python 프로세스로 실행하여 메모리 격리 + 장애 격리를 확보하고,
프로세스 종료 시 메모리가 즉시 회수되어 장시간 테스트에 유리하다.

#### 구조: 2개 스크립트

```
dev/live_tests/
├── run_bedrock_model_test.py       # 오케스트레이터 (Phase 관리 + 병렬 제어)
└── run_single_bedrock_test.py      # 단일 테스트 워커 (subprocess로 호출)
```

#### 단일 테스트 워커 (run_single_bedrock_test.py)

독립 프로세스에서 실행되며, 1회의 파이프라인 E2E + Evaluator 채점을 수행한다.

```bash
# CLI 사용법:
python -m dev.live_tests.run_single_bedrock_test \
  --agent safety \
  --model-id "apac.anthropic.claude-3-5-sonnet-20241022-v2:0" \
  --model-short c35-sonnet-v2 \
  --run 1 \
  --output results/bedrock_model_test/phase1/safety_c35-sonnet-v2_run1.json \
  --skip-viz true
```

**워커 프로세스 내부 동작**:
1. CLI 인자 파싱
2. 환경변수 설정 (`SKIP_VISUALIZATION`, `LLM_PROVIDER=bedrock`)
3. Settings 싱글톤 리셋 + 모델 오버라이드
4. 워크플로우 컴파일 + `ainvoke()` 실행
5. 런타임 지표 수집 (소요시간, 토큰, /proc/meminfo 기반 메모리)
6. Evaluator Agent 채점
7. 결과 JSON 저장 → stdout에 경로 출력
8. 프로세스 종료 (메모리 즉시 회수)

#### 오케스트레이터 (run_bedrock_model_test.py)

전체 Phase를 관리하고, 서브프로세스를 스케줄링한다.

```bash
# 전체 실행 (캘리브레이션 → Phase 0 → Phase 1 → Phase 3)
python -m dev.live_tests.run_bedrock_model_test --phase all

# 개별 Phase 실행
python -m dev.live_tests.run_bedrock_model_test --phase calibration
python -m dev.live_tests.run_bedrock_model_test --phase 0
python -m dev.live_tests.run_bedrock_model_test --phase 1
python -m dev.live_tests.run_bedrock_model_test --phase 3

# 실패한 테스트만 재실행
python -m dev.live_tests.run_bedrock_model_test --phase 1 --retry-failed

# 특정 에이전트만 실행
python -m dev.live_tests.run_bedrock_model_test --phase 1 --agent safety

# 동시성 오버라이드 (캘리브레이션 결과 무시)
python -m dev.live_tests.run_bedrock_model_test --phase 1 --max-concurrent 1
```

#### 실행 전략: 에이전트별 순차 + 모델별 병렬

```
t3.medium (2vCPU, 3.8GB RAM) 기준:
  max_concurrent = 2 (캘리브레이션에서 조정)

에이전트 1 (Intent Classifier):
  ├─ [프로세스 1] c3-sonnet run1  ──┐
  ├─ [프로세스 2] c3-sonnet run2  ──┤ 동시 2개
  │  (프로세스 1 완료)              │
  ├─ [프로세스 1] c3-sonnet run3  ──┘
  ├─ [프로세스 2] c3-haiku run1   ──┐
  │  ...                            │
  └─ 15회 완료 → 중간 결과 로그 출력

에이전트 2 (Safety Agent):
  ├─ ... (동일 패턴)
  ...

에이전트 10 (Learning Agent):
  └─ 15회 완료

Visualization (별도):
  └─ Claude 5모델 x 3회 + 이미지 3모델 x 3회 = 24회

총: 159회 + Phase 0(8회) + Phase 0.5(~10회) + Phase 3(10회) = ~187회
```

#### 메모리 안전장치

오케스트레이터가 각 서브프로세스 실행 전/후에 `/proc/meminfo`를 읽어 메모리를 확인한다:

```python
import asyncio

MEMORY_THRESHOLD_MB = 500  # 가용 메모리가 이 이하면 대기

def _get_available_memory_mb() -> int:
    """/proc/meminfo에서 가용 메모리(MB)를 읽는다."""
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024  # kB → MB
    return 0

async def wait_for_memory(threshold_mb: int = MEMORY_THRESHOLD_MB):
    """가용 메모리가 임계값 이상이 될 때까지 대기한다."""
    while True:
        available = _get_available_memory_mb()
        if available >= threshold_mb:
            return available
        print(f"  ⚠ 메모리 부족: {available}MB < {threshold_mb}MB, 30초 대기...")
        await asyncio.sleep(30)
```

#### Bedrock Rate Limit 대응

```python
# 서브프로세스 간 최소 간격 (ThrottlingException 방지)
INTER_PROCESS_DELAY_SEC = 5  # 캘리브레이션에서 조정

async def run_with_delay(job, semaphore, delay):
    """서브프로세스 실행 후 다음 실행까지 최소 간격을 둔다."""
    result = await run_subprocess_test(job, semaphore)
    await asyncio.sleep(delay)
    return result
```

#### 장애 대응 매트릭스

| 장애 유형 | 감지 방법 | 자동 대응 | 수동 대응 |
|----------|----------|----------|----------|
| OOM Kill | returncode -9 | max_concurrent -= 1, 재시도 | Swap 확인, Docker 중지 |
| ThrottlingException | stderr에 `ThrottlingException` | 대기 시간 2배 증가, 재시도 | Bedrock 콘솔에서 할당량 확인 |
| 타임아웃 (10분) | asyncio.TimeoutError | 1회 재시도 | 네트워크/Bedrock 상태 확인 |
| JSON 파싱 실패 | 결과 파일 읽기 오류 | 해당 run만 재시도 | 에이전트 출력 로그 확인 |
| 디스크 부족 | OSError | 테스트 중단 + 경고 | 불필요 파일 정리 |

### 11.5 결과 수집 및 커밋 (AWS)

#### 결과 디렉토리 구조

```
dev/live_tests/results/bedrock_model_test/
├── calibration.json                                # 캘리브레이션 결과
├── phase0/
│   └── connectivity_{model_short}_{timestamp}.json  # 8개
├── phase1/
│   └── {agent}_{model_short}_run{n}_{timestamp}.json  # 159개
├── phase3/
│   ├── optimal_{run_n}_{timestamp}.json             # 5개
│   └── baseline_{run_n}_{timestamp}.json            # 5개
├── progress.json                                    # 진행 상황 추적
└── summary/
    └── aggregated_results.json                      # 에이전트별 집계 (AWS에서 생성)
```

#### 진행 상황 추적 (progress.json)

오케스트레이터가 매 테스트 완료 시 업데이트한다. 중단 후 재개 시 이 파일을 읽어 이어서 실행한다.

```json
{
  "started_at": "2026-03-31T10:00:00Z",
  "last_updated": "2026-03-31T12:30:00Z",
  "phase": "phase1",
  "total_tests": 159,
  "completed": 45,
  "failed": 2,
  "remaining": 112,
  "current_agent": "emotion",
  "failed_tests": [
    {"agent": "safety", "model": "c3-sonnet", "run": 2, "error": "timeout"},
    {"agent": "safety", "model": "c37-sonnet", "run": 1, "error": "throttling"}
  ]
}
```

#### AWS에서 결과 커밋

모든 Phase 완료 후 (또는 Phase 1 완료 후 중간 커밋):

```bash
cd /home/ubuntu/app
git add dev/live_tests/results/bedrock_model_test/
git commit -m "test: Bedrock 모델 비교 테스트 Phase 1 결과 (N/159 완료)"
git push origin develop
```

> **중간 커밋 전략**: Phase 1이 장시간(~4~6시간) 소요되므로,
> 에이전트 5개 완료 시점에 중간 커밋하여 결과 유실을 방지한다.
> `--retry-failed`로 실패 건을 재실행한 후 최종 커밋한다.

### 11.6 보고서 생성 (로컬, Claude Code)

#### 로컬에서 결과 수신

```bash
# 로컬 환경
git pull origin develop

# 결과 파일 확인
ls dev/live_tests/results/bedrock_model_test/phase1/ | wc -l  # 159개 확인
cat dev/live_tests/results/bedrock_model_test/progress.json    # 완료 상태 확인
```

#### Phase 2: 종합점수 산출

```bash
# 종합점수 산출 (외부 패키지 불필요 — 표준 라이브러리의 json, statistics만 사용)
python -m dev.live_tests.scoring \
  --input dev/live_tests/results/bedrock_model_test/ \
  --output dev/live_tests/results/bedrock_model_test/summary/
```

#### Phase 4: Markdown 보고서 생성

외부 패키지 없이, **Claude Code가 집계 결과 JSON을 읽어 Markdown 보고서를 작성**한다.

```bash
# Claude Code CLI에서:
# 1. scoring.py의 집계 결과를 읽음
# 2. 에이전트별 최적 모델, 종합점수 매트릭스, Phase 3 비교 등을 정리
# 3. docs/reports/bedrock_model_comparison.md로 저장
```

> **패키지 추가 없이 보고서 생성하는 방식**:
> - `scoring.py`: Python 표준 라이브러리(json, statistics, pathlib)만 사용
> - Markdown 보고서: Claude Code가 집계 JSON을 분석하여 직접 작성
> - Excel이 필요한 경우: 집계 JSON을 CSV로 변환(`csv` 표준 라이브러리) 후 스프레드시트에서 열기

#### 로컬 전용 스크립트

```
dev/live_tests/
└── scoring.py              # Phase 2: 종합점수 산출 (표준 라이브러리만 사용)
```

Markdown 보고서는 별도 스크립트 대신 **Claude Code가 직접 작성**한다.
결과 JSON을 읽어 분석하며 보고서를 작성할 수 있고, 필요 시 보완/수정도 대화형으로 가능하다.

### 11.7 실행 환경별 직접 조정 가이드

설계서의 값은 **예측치**이다. 실제 실행 시 아래 항목을 직접 확인하고 조정한다.

#### 조정이 필요한 파라미터

| 파라미터 | 설계 예측 | 실측 방법 | 조정 기준 |
|---------|----------|----------|----------|
| `max_concurrent` | 2 | 캘리브레이션 C-3, C-4 | OOM 없이 완료되는 최대 프로세스 수 |
| `inter_process_delay` | 5초 | 캘리브레이션 C-5 | ThrottlingException 발생 시 2배 증가 |
| `process_timeout` | 600초 | 캘리브레이션 C-2 | 단일 파이프라인 소요시간 x 3 |
| `memory_threshold_mb` | 500MB | `free -m`으로 실측 | Swap 진입 직전 가용 메모리 |
| Bedrock 모델 ID | `apac.` 접두사 | Phase 0에서 모델별 확인 | on-demand 가능하면 접두사 제거 |
| `skip_visualization` 동작 | 환경변수 | 실측: Vis 스킵/포함 소요시간 차이 | 차이가 없으면 항상 포함 |

#### 실행 중 모니터링 (Chrome MCP)

Claude Code 데스크톱 앱의 Chrome MCP로 AWS SSM 세션에 직접 명령어를 입력하여 모니터링한다.

```bash
# 메모리 + CPU 확인
free -m && ps aux --sort=-%mem | head -5

# 디스크 사용량 (결과 JSON 누적)
du -sh /home/ubuntu/app/dev/live_tests/results/bedrock_model_test/

# 테스트 진행 상황
cat /home/ubuntu/app/dev/live_tests/results/bedrock_model_test/progress.json | python3 -m json.tool

# 최근 결과 파일 확인
ls -lt /home/ubuntu/app/dev/live_tests/results/bedrock_model_test/phase1/ | head -5
```

> Chrome MCP를 통해 위 명령어를 필요할 때마다 직접 입력한다.
> 장시간 실행 시 중간중간 progress.json과 메모리 상태를 확인하며,
> 문제 발생 시 즉시 파라미터를 조정하고 재실행할 수 있다.

#### 문제 발생 시 대응 순서

```
1. OOM Kill 발생:
   → max_concurrent를 1로 낮추고 순차 실행
   → Docker가 실행 중이면 docker compose down
   → Swap이 없으면 설정
   → 그래도 OOM이면 단일 파이프라인도 메모리 부족 → 인스턴스 업그레이드 검토

2. ThrottlingException 반복:
   → inter_process_delay를 10초 → 20초 → 30초로 증가
   → max_concurrent를 1로 낮춤
   → Bedrock 콘솔 > Service Quotas에서 할당량 확인/증가 요청
   → 대안: 시간대를 바꿔 실행 (사용량이 적은 시간)

3. 테스트 중단 후 재개:
   → progress.json을 확인하여 남은 테스트 파악
   → python -m dev.live_tests.run_bedrock_model_test --phase 1 --retry-failed
   → 또는 특정 에이전트만: --agent safety

4. 디스크 부족:
   → 완료된 Phase 결과를 git commit + push 후 확인
   → Docker 이미지 정리: docker system prune -a
   → 로그 정리: truncate -s 0 /home/ubuntu/app/logs/*.log
```

### 11.8 전체 예상 일정

| 단계 | 환경 | 예상 소요 | 비고 |
|------|------|----------|------|
| Swap 설정 + Docker 중지 | AWS | 5분 | 1회성 |
| Phase 0: 연결 확인 | AWS | 10분 | 8회 |
| Phase 0.5: 캘리브레이션 | AWS | 30분 | ~10회 + 분석 |
| Phase 1: 벤치마크 | AWS | **4~6시간** | 159회 (2병렬 기준) |
| 중간 커밋 + 푸시 | AWS | 5분 | Phase 1 중간/완료 시 |
| Phase 3: 최적 검증 | AWS | 1시간 | 10회 |
| 최종 커밋 + 푸시 | AWS | 5분 | - |
| git pull | 로컬 | 1분 | - |
| Phase 2: 종합점수 산출 | 로컬 | 5분 | scoring.py (표준 라이브러리) |
| Phase 4: 보고서 생성 | 로컬 | 10분 | Claude Code가 MD 작성 |
| **합계** | | **~6~8시간** | Phase 1이 병목 |

> 캘리브레이션 결과에 따라 `max_concurrent`가 1이면 ~8시간, 2이면 ~5시간, 3이면 ~4시간.
> 실제 시간은 Bedrock 응답 속도와 인스턴스 부하에 따라 변동한다.

---

*설계 완료: 2026-03-30 (v4: 패키지 추가 금지 반영 + Chrome MCP 워크플로우 + psutil/openpyxl 제거)*

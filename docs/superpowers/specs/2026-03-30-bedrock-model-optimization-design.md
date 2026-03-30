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

## 3. 테스트 구조 (4단계)

```
Phase 0: 연결 확인 --- Claude 5개 + 이미지 3개 = 8회
    |
Phase 1: 전체 파이프라인 벤치마크 --- 순차 실행
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
Phase 2: 종합점수 산출 + 최적 모델 선정
    |  에이전트별 (모델 x 지표) 매트릭스 -> 가중 종합점수 -> 최적 모델 결정
    |
Phase 3: 최적 파이프라인 검증
    |  Phase 2 선정 조합으로 전체 파이프라인 5회 실행
    |  + Baseline(현재 설정) 5회 실행
    |  -> 성능 비교 및 개선율 산출
```

### 3.1 총 실행 횟수

| Phase | 내용 | Vis 스킵 | 실행 횟수 |
|-------|------|---------|----------|
| Phase 0 | 연결 확인 (Claude 5 + 이미지 3) | - | 8회 |
| Phase 1 | 에이전트 1~8, 10 벤치마크 (9 x 5모델 x 3회) | 스킵 | 135회 |
| Phase 1 | Visualization 벤치마크 (Claude 5 x 3 + 이미지 3 x 3) | 동작 | 24회 |
| Phase 3 | 최적 조합 (5회) + Baseline (5회) | 동작 | 10회 |
| **합계** | | | **177회** |

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
> **전체 177회 예상 총 소요: 약 6~8시간** (Evaluator 호출 포함).

### 3.3 실행 순서

매 실행마다 모델 설정이 변경되므로 **순차 실행**한다.

```
실행 루프:
  for agent in 10개_에이전트:
      for model in 테스트_모델_목록:
          for run in [1, 2, 3]:
              1. Settings 싱글톤 리셋
              2. 대상 에이전트 모델 오버라이드
              3. Visualization 스킵 설정
                 - agent != "visualization" -> SKIP_VISUALIZATION=true
                 - agent == "visualization" -> SKIP_VISUALIZATION=false
              4. 에이전트 싱글톤 리프레시
              5. 전체 파이프라인 E2E 실행 (workflow.ainvoke)
              6. 런타임 지표 수집
              7. Evaluator Agent 평가
              8. 결과 JSON 저장
              9. 다음 실행을 위해 설정 초기화
```

> 파이프라인을 동시에 여러 개 실행(병렬)하려면 독립된 설정 인스턴스가 필요하다.
> 현재 Settings가 싱글톤 패턴이므로 동일 프로세스 내 병렬 실행은 설정 충돌이 발생한다.
> 따라서 모든 테스트는 순차 실행하며, 설정 변경 -> 실행 -> 수집 -> 초기화 사이클을 반복한다.

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
+-- phase0/
|   +-- connectivity_{model_short}_{timestamp}.json
+-- phase1/
|   +-- {agent}_{model_short}_run{n}_{timestamp}.json       # 159개
+-- phase3/
|   +-- optimal_{run_n}_{timestamp}.json                     # 5개
|   +-- baseline_{run_n}_{timestamp}.json                    # 5개
+-- summary/
    +-- aggregated_results.json                              # 전체 통계 집계
```

### 8.2 Excel 보고서

**경로**: `dev/live_tests/results/bedrock_model_test/bedrock_model_comparison_report.xlsx`

| 시트 | 내용 |
|------|------|
| Overview | 테스트 개요, 환경 정보, 총 실행 횟수 |
| Phase 0 - Connectivity | 8개 모델 연결 결과, 응답 시간 |
| Agent Summary | 에이전트별 최적 모델 + 종합점수 매트릭스 (10행 x 5열) |
| Intent Classifier | 해당 에이전트 5모델 x 3회 상세 (런타임, Evaluator 항목별 점수, 통계) |
| Safety Agent | 위와 동일 형식 |
| Emotion Agent | 위와 동일 형식 |
| Content Analyzer | 위와 동일 형식 |
| Podcast Reasoning | 위와 동일 형식 |
| Script Generator | 위와 동일 형식 |
| Batch Validator | 위와 동일 형식 |
| Script Personalizer | 위와 동일 형식 |
| Visualization | Claude 5모델 + 이미지 3모델 상세 |
| Learning Agent | 위와 동일 형식 |
| Phase 3 - Validation | 최적 조합 vs Baseline 비교 (5회씩) |
| Composite Scores | 전체 종합점수 산출 상세 (가중치, 정규화 과정) |
| Raw Data | 177회 전체 원시 데이터 |

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
+-- run_bedrock_model_test.py          # 메인 테스트 러너 (Phase 0/1/3 실행)
+-- evaluator_agent.py                 # Evaluator Agent 구현
+-- evaluator_criteria.py              # 에이전트별 평가 기준 정의
+-- scoring.py                         # 종합점수 산출 로직
+-- report_generator.py                # Excel + Markdown 보고서 생성
+-- results/bedrock_model_test/        # 결과 디렉토리
```

> Evaluator Agent는 향후 파이프라인 편입 시 `src/agents/shared/`로 이동하고 `BaseAgent` 상속으로 전환한다. 현재는 `dev/live_tests/` 내에서 독립적으로 동작한다.

### 9.2 Bedrock API 현황

현재 코드는 두 가지 Bedrock API를 사용한다:

- **텍스트 생성 (Claude)**: `Converse API` (`bedrock_client.converse()`) -- invoke_model에서 마이그레이션 완료
- **이미지 생성 (Titan/Nova)**: `invoke_model` API -- Converse API 미지원

> Nova Canvas 테스트 시 `invoke_model` API의 요청 포맷이 Titan과 다를 수 있으므로, `base_agent.py`의 `_generate_image_bedrock()` 메서드 호환성을 Phase 0에서 확인한다.

### 9.3 모델 교체 메커니즘

에이전트별 모델 교체는 `settings.yaml`의 에이전트 설정(`agents.{agent_name}.model`)을 런타임에 패치하는 방식으로 구현한다. 기존 `run_prompt_iteration.py`에서 사용한 Settings 싱글톤 리셋 패턴을 활용한다.

```python
# 대상 에이전트만 모델 교체, 나머지는 기본값 유지
def override_agent_model(agent_name: str, bedrock_model_id: str):
    settings = get_settings()
    settings.agents[agent_name].model_id = bedrock_model_id
    # 해당 에이전트 싱글톤 리프레시
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
- Python 3.11+, boto3, openpyxl (Excel 생성용)
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
3. **비용**: 177회 파이프라인 실행 + Evaluator 호출로 Bedrock API 비용이 발생한다. 135회는 Visualization 스킵으로 이미지 생성 비용을 절감한다.
4. **모델 가용성**: AWS 리전 및 계정에 따라 일부 모델이 사용 불가할 수 있다. Phase 0에서 사전 확인한다.
5. **Episode Memory/Knowledge**: Podcast Reasoning 내부에서 조건부 호출되므로, 해당 독립 에이전트의 모델은 직접 교체하지 않는다. Podcast Reasoning 모델 교체 시 간접적으로 영향을 받는다.
6. **Visualization 리전 분리**: 텍스트 기획(Claude)은 `ap-northeast-2`, 이미지 생성(Titan/Nova)은 `us-east-1`에서 실행된다. 리전 간 지연시간이 추론 시간에 포함된다.
7. **Titan v2 EOL**: 현재 사용 중인 `amazon.titan-image-generator-v2:0`는 2026-06-30 지원 종료 예정이다. 테스트 결과에 따라 Nova Canvas 마이그레이션을 권장할 수 있다.
8. **순차 실행**: Settings 싱글톤 패턴으로 인해 동일 프로세스 내 병렬 파이프라인 실행이 불가하다. 모든 177회 테스트는 순차 실행한다.
9. **Nova Canvas API 호환성**: 현재 `base_agent.py`의 `_generate_image_bedrock()`는 Titan 요청 포맷으로 구현되어 있다. Nova Canvas는 요청 포맷이 다를 수 있으므로 Phase 0에서 호환성을 확인하고, 필요 시 분기 로직을 추가한다.
10. **Converse API**: 텍스트 생성은 Converse API로 마이그레이션 완료 상태이다. 토큰 사용량 필드가 `inputTokens`/`outputTokens` (camelCase)이므로 수집 코드에서 이를 반영한다.

---

*설계 완료: 2026-03-30 (최종 수정: 코드 변경사항 반영)*

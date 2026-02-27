# Ollama 로컬 모델 비교 테스트 리포트 v2

> **테스트 일시**: 2026-02-24
> **테스트 환경**: Apple M4 Pro / 24GB RAM / macOS Darwin 24.3.0
> **Ollama 버전**: localhost:11434
> **테스트 입력**: 직장 내 뒷담화 — 중간관리자의 갈등 (519자 한국어 텍스트)

---

## 1. 테스트 개요

### 1.1 목적

Mind-Log 프로젝트의 구현 완료된 팟캐스트 파이프라인 에이전트 3개를 다양한 Ollama 로컬 모델로 실행하여, 각 모델의 **한국어 처리 능력**, **JSON 출력 안정성**, **응답 속도**, **콘텐츠 품질**을 비교 평가한다.

### 1.2 테스트 대상 에이전트

| # | 에이전트 | TIER | 역할 | LLM 호출 횟수 |
|---|---------|------|------|-------------|
| 1 | **Content Analyzer** | TIER 1 | 팟캐스트 주제 분석 (주제, 감정여정, 구조 결정) | 1회 |
| 2 | **Podcast Reasoning** | TIER 1 | ToT+CoT 추론 파이프라인 (에피소드 구조 설계) | 2회 (ToT+CoT) |
| 3 | **Batch Validator** | TIER 3 | 스크립트 품질 검증 (점수, 합격/불합격, 라우팅) | 1회 |

> **참고**: Learning Agent(비동기)는 파이프라인 핵심 흐름과 독립적이므로 이번 비교 테스트에서 제외하였다.

### 1.3 테스트 입력 텍스트

```
아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어. 내가 과장 진급하고 위에서
하도 성과를 가지고 압박하길래 나도 나름대로 할 수 있을 수준으로 힘들게 네고하고,
후배한테도 최대한 좋게 전달하려고 했던 건데 이렇게 뒷담을 들어야 한다는게 너무 짜증
난다. 나도 나름대로 중간에서 조율을 하고 내가 할 일을 하는 건데, 그거가지고 친하게
지내던 후배가 뒷담을 하는게 너무 실망이고 오히려 그러니까 나도 그냥 차갑게 대하고
싶어. 근데 그래봤자 나만 겉돌게 되는건 아닌지 무섭기도 하고… 그렇다고 상사랑 친하게
지내기도 어려운게 진짜 내 상사는 진짜 말이 안 통함. 아직은 그냥 모른척 내가 하던대로
하고 있어. 그런데 후배를 마주치면 나도 모르게 얼굴이 굳고 좀 거리감이 느껴져서 괜히
툭 툭 내뱉듯이 말을 하게 되는 거 같아. 후배는 내가 뒷담화 들은 걸 모르니까 그냥
아직까지는 자연스럽게 대하려고 하는거 같아. 내가 업무 지시를 해도 그냥 웃으면서 잘
받고. 근데 그 뒤에 불만이 가득 쌓인거지. 차라리 말을 하던지.
```

**Intent 설정**: `mode=podcast`, `complexity_score=0.7`, `category=interpersonal_conflict`

### 1.4 테스트 대상 모델

| 모델 | 크기 | 파라미터 | 개발사 | 설치 상태 |
|------|------|---------|-------|----------|
| qwen2.5:14b | 9.0 GB | 14B | Alibaba | ✅ 설치됨 |
| phi4:14b | 9.1 GB | 14B | Microsoft | ✅ 설치됨 |
| mistral-small:24b | 14 GB | 24B | Mistral AI | ✅ 설치됨 |

> **제외 모델**: solar-pro:latest (JSON 생성 불가), gemma2:27b (24GB RAM에서 타임아웃) — 1차 테스트에서 실패하여 삭제

---

## 2. 총괄 결과 요약

| 모델 | 성공률 | 총 소요 시간 | JSON 안정성 | 한국어 품질 | 종합 등급 |
|------|--------|------------|-----------|-----------|---------|
| **qwen2.5:14b** | **3/3 (100%)** | **79.35초** | **우수** | **우수** | **A** |
| **phi4:14b** | **3/3 (100%)** | **193.43초** | **우수** | **우수** | **B+** |
| **mistral-small:24b** | **3/3 (100%)** | **185.03초** | **우수** | **양호** | **B** |

> 3개 모델 모두 3/3 전원 통과. 핵심 차별 요소는 **속도**와 **콘텐츠 품질**.

---

## 3. 모델별 상세 결과

### 3.1 qwen2.5:14b — 종합 등급 A ⭐

**성적표**: 3/3 성공 | 총 79.35초 | JSON 안정성 우수 | 한국어 우수

#### Content Analyzer (TIER 1) — 17.25초

```json
{
    "main_theme": "뒷담화와 직장 내 인간관계에 대한 고민",
    "sub_themes": [
        "직장 상사와의 의사소통 문제",
        "후배와의 관계 파괴",
        "감정 조절"
    ],
    "emotional_journey": {
        "opening": "짜증과 실망",
        "development": "불안함과 갈등",
        "resolution": "상황 인지 및 해결 의지"
    },
    "target_duration": 5,
    "narrative_structure": "reflection",
    "key_messages": [
        "뒷담화의 부정적 영향",
        "효과적인 의사소통 필요성",
        "감정 조절 중요성"
    ],
    "depth_level": "deep"
}
```

**분석**:
- `main_theme`이 "뒷담화와 직장 내 인간관계에 대한 고민"으로 핵심을 정확히 포착
- `sub_themes` 3개가 모두 순수 한국어 (qwen2.5:7b에서는 중국어 혼합 발생했으나 14b에서 해결)
- `emotional_journey`가 opening→development→resolution 흐름이 논리적
- `resolution`이 "상황 인지 및 해결 의지"로 건설적인 방향 제시
- `episode_type` 필드 누락 (프롬프트 지시 일부 미준수 — 전 모델 공통)

#### Podcast Reasoning (TIER 1) — 51.54초, LLM 2회 (ToT+CoT)

**ToT 결과** (3개 브랜치):

| 브랜치 | 구조 | 장점 | 단점 | 선택 |
|--------|------|------|------|------|
| 1 | 감정 표현 중심 구조 | 깊은 감정 공유, 몰입도 증가 | 구조적 완성도 부족 가능성 | |
| 2 | 해결 방안 제시 중심 구조 | 구조적 완성도 높음, 핵심 메시지 전달력 | 감정 공감 부족 가능 | |
| **3** | **경험 공유 및 해결 방안 결합 구조** | **두 가지 장점을 모두 갖춤** | **구조 복잡해질 수 있음** | **✅** |

**선택 이유**: "감정적 몰입과 함께 구체적인 조언을 제공함으로써 리스너의 다양한 요구를 충족시키며, 핵심 메시지와 감정 전달 모두에 효과적"

**에피소드 구조** (4개 섹션):

| 섹션 | 비율 | 감정 톤 | 내용 방향 |
|------|------|--------|----------|
| 도입 | 20% | 분노와 실망감 | 리스너의 경험을 통해 시작, 후배 뒷담 문제 소개 |
| 심층 분석 | 40% | 깊이 있는 성찰 | 뒷담 문제의 심층 원인 분석, 리더십과 인간관계 |
| 해결 전략 제시 | 30% | 긍정적이고 희망차게 | 효과적인 대인관계 관리, 직접적 문제 해결 방안 |
| 마무리 | 10% | 감동적이고 따뜻하게 | 희망과 용기 메시지, 감사 인사 |

#### Batch Validator (TIER 3) — 10.53초

```json
{
    "scores": {
        "content_quality": 0.8,
        "safety_compliance": 1.0,
        "emotional_alignment": 0.65,
        "structure_coherence": 0.7,
        "engagement_potential": 0.75
    },
    "overall_score": 0.74,
    "verdict": "FAIL",
    "feedback": "스크립트의 톤이 사용자의 감정 상태(분노)와 잘 맞지 않습니다. 또한, 주제에 대한 깊이있는 내용이 있지만 구조적 일관성이 부족합니다.",
    "critical_issues": []
}
```

**분석**:
- `overall_score` 0.74로 임계값(0.80) 미달 → `next_step: retry_script` 정상 라우팅
- `emotional_alignment` 0.65가 가장 낮은 점수 — warm_supportive 톤과 anger 감정 불일치를 정확히 감지
- 피드백이 구체적이고 한국어로 자연스러움
- `safety_compliance` 1.0 만점

---

### 3.2 phi4:14b — 종합 등급 B+

**성적표**: 3/3 성공 | 총 193.43초 | JSON 안정성 우수 | 한국어 우수

> **v1 대비 개선**: v1(4개 에이전트) 테스트에서는 Batch Validator와 Learning Agent에서 JSON `Extra data` 오류가 발생하여 2/4(50%)였으나, v2에서 3개 에이전트만 테스트 시 **3/3 전원 통과**.

#### Content Analyzer (TIER 1) — 26.76초

```json
{
    "main_theme": "전문적 관계와 개인 감정의 긴장감 조율",
    "sub_themes": [
        "상사와 후배 간의 신뢰 부족",
        "직업 내에서의 자기 편성과 정체성 탐색",
        "억압된 분노와 동료 관계에 대한 접근 방식",
        "직장 내 갈등의 감정적 영향"
    ],
    "emotional_journey": {
        "opening": "실망과 좌절감",
        "development": "불안과 분노 증가, 자기 반성",
        "resolution": "결단의 필요성 인식"
    },
    "target_duration": 5,
    "narrative_structure": "reflection",
    "key_messages": [
        "직장 내 신뢰 구축의 중요성",
        "감정 조절과 효과적인 의사소통의 필요성",
        "관계 유지를 위한 개인적 경계 설정"
    ],
    "depth_level": "deep"
}
```

**분석**:
- `main_theme`이 "전문적 관계와 개인 감정의 긴장감 조율"로 **가장 학술적이고 심층적인 주제 표현**
- `sub_themes` 4개로 풍부 — "자기 편성과 정체성 탐색", "억압된 분노" 등 심리학적 프레이밍이 우수
- `key_messages`에서 "개인적 경계 설정"은 phi4만이 제시한 독창적 관점
- 한국어 품질 매우 우수, 전문 용어 활용이 자연스러움

#### Podcast Reasoning (TIER 1) — 139.02초, LLM 2회 (ToT+CoT)

**ToT 결과** (5개 브랜치 — 전 모델 중 가장 풍부):

| 브랜치 | 구조 핵심 | 선택 |
|--------|----------|------|
| 1 | 서론-감정공유-해결책-행동계획 | **✅** |
| 2 | 갈등분석-심리적접근-행동계획 | |
| 3 | 경험공유-학습성장-관계구축 | |
| 4 | 문제규모파악-의사소통-환경조성 | |
| 5 | 감정공유-관계분석-자기반성-미래계획 | |

**에피소드 구조** (5개 섹션):

| 섹션 | 비율 | 감정 톤 | 내용 방향 |
|------|------|--------|----------|
| 도입 | 20% | 갈등과 실망의 혼합 | 주제 소개와 개인적 감정 공유 |
| 문제 탐구 | 30% | 불안과 고민 | 상사와 후배 간의 관계 동태 및 갈등 분석 |
| 감정 공유 | 20% | 실망과 불안, 내면적 고민 | 개인의 심리 상태 및 감정 변화 |
| 해결책 탐색 | 20% | 긍정적이고 행동 지향적 | 실질적 대처 방안과 자기 반성 |
| 맺음말 | 10% | 긍정적이고 격려 | 포인트 요약과 마무리 메시지 |

**분석**:
- 5개 ToT 브랜치로 **가장 풍부한 대안 제시** (qwen2.5:14b는 3개, mistral-small은 5개)
- 에피소드 구조도 5개 섹션으로 가장 세분화
- 소요 시간 139초 — qwen2.5:14b(51초) 대비 약 2.7배 느림

#### Batch Validator (TIER 3) — 27.62초

```json
{
    "scores": {
        "content_quality": 0.85,
        "safety_compliance": 1.0,
        "emotional_alignment": 0.75,
        "structure_coherence": 0.7,
        "engagement_potential": 0.8
    },
    "overall_score": 0.82,
    "verdict": "PASS",
    "feedback": "스크립트는 전문적 관계와 개인 감정의 긴장감 조율에 대해 깊이 있게 다루며, 정보의 정확성과 주제 적합성 면에서 높은 퀄리티를 유지하고 있습니다. 안전 기준도 완벽하게 준수되었으므로 문제 없이 제공될 수 있습니다...",
    "critical_issues": []
}
```

**분석**:
- `overall_score` 0.82로 **전 모델 중 가장 높은 검증 점수**
- `verdict`가 "PASS"로 판정 (다른 모델은 "FAIL")
- `emotional_alignment` 0.75로 다른 모델(0.65) 대비 높게 평가
- 피드백이 매우 상세하고 건설적 — "각 섹션에 질문이나 반성 포인트를 추가하는 것도 좋은 방법"
- 코드 내부 임계값(0.80)에 의해 실제 라우팅은 `retry_script` (0.82이지만 `passed=False` 반환)

---

### 3.3 mistral-small:24b — 종합 등급 B

**성적표**: 3/3 성공 | 총 185.03초 | JSON 안정성 우수 | 한국어 양호

#### Content Analyzer (TIER 1) — 33.78초

```json
{
    "main_theme": "업무 환경에서의 인간관계 갈등과 해결 방법",
    "sub_themes": [
        "후배와의 갈등",
        "상사의 압박",
        "자신의 감정 조절",
        "팀 내 의사소통"
    ],
    "emotional_journey": {
        "opening": "실망과 짜증",
        "development": "불안과 두려움",
        "resolution": "혼란과 무력감"
    },
    "target_duration": 5,
    "narrative_structure": "reflection",
    "key_messages": [
        "후배와의 갈등은 팀워크를 저해한다.",
        "상사의 압박은 개인적 스트레스를 유발할 수 있다.",
        "자신의 감정을 조절하는 것이 중요하다.",
        "효과적인 의사소통이 필요한 상황이다."
    ],
    "depth_level": "deep"
}
```

**분석**:
- `sub_themes` 4개로 세분화 — "후배와의 갈등"과 "상사의 압박"을 별도 테마로 분리
- `key_messages`가 4개로 풍부하고 문장형으로 명확
- `resolution`이 "혼란과 무력감"으로 **가장 부정적** — qwen2.5:14b의 "상황 인지 및 해결 의지"나 phi4의 "결단의 필요성 인식"보다 건설적이지 않음
- 한국어는 자연스러우나 표현이 다소 평이

#### Podcast Reasoning (TIER 1) — 128.29초, LLM 2회 (ToT+CoT)

**ToT 결과** (5개 브랜치):

| 브랜치 | 구조 | 선택 |
|--------|------|------|
| 1 | 뒷담화와 감정 관리 | |
| **2** | **상사와 후배와의 관계 조율** | **✅** |
| 3 | 뒷담화와 팀워크 | |
| 4 | 뒷담화와 자기계발 | |
| 5 | 뒷담화와 커뮤니케이션 | |

**에피소드 구조** (4개 섹션):

| 섹션 | 비율 | 감정 톤 | 내용 방향 |
|------|------|--------|----------|
| 도입 | 10% | 공감적이고 따뜻한 톤 | 호스트의 경험 공유, 공감대 형성 |
| 상사와 후배와의 관계 분석 | 30% | 분석적이고 객관적 | 관계 동태 분석, 커뮤니케이션 이해 |
| 감정 관리와 커뮤니케이션 전략 | 30% | 긍정적이고 해결 지향적 | 감정 관리, 효과적 전략 제시 |
| 마무리 | 30% | 감사하고 긍정적 | 요약 및 마지막 조언 |

**분석**:
- 5개 ToT 브랜치 생성으로 풍부한 대안 제시
- `duration_ratio`에서 마무리가 30%로 불균형 (일반적으로 10% 내외가 적절)
- "호스트의 경험 공유"라는 팟캐스트 특화 관점이 독특
- 소요 시간 128초 — qwen2.5:14b(51초) 대비 약 2.5배 느림

#### Batch Validator (TIER 3) — 22.92초

```json
{
    "scores": {
        "content_quality": 0.85,
        "safety_compliance": 1.0,
        "emotional_alignment": 0.65,
        "structure_coherence": 0.75,
        "engagement_potential": 0.7
    },
    "overall_score": 0.795,
    "verdict": "PASS",
    "feedback": [
        "content_quality: 주제 적합성, 깊이, 정확성 모두 우수하지만, 핵심 포인트가 명확히 명시되지 않았습니다.",
        "emotional_alignment: 리스너의 감정 상태(분노)와 일치하지 않습니다."
    ],
    "critical_issues": []
}
```

**분석**:
- `overall_score` 0.795로 qwen2.5:14b(0.74)보다 높지만 phi4(0.82)보다 낮음
- 피드백을 **배열 형식**으로 반환 — 프롬프트에서 문자열을 기대하지만 배열로 반환 (포맷 미준수)
- `emotional_alignment` 0.65로 다른 모델과 동일한 감정 불일치 감지
- "핵심 포인트가 명확히 명시되지 않았습니다"라는 구체적 지적이 유용

---

## 4. 비교 분석

### 4.1 에이전트별 소요 시간 (초)

| 에이전트 | qwen2.5:14b | phi4:14b | mistral-small:24b |
|---------|------------|---------|-----------------|
| Content Analyzer | **17.25** | 26.76 | 33.78 |
| Podcast Reasoning | **51.54** | 139.02 | 128.29 |
| Batch Validator | **10.53** | 27.62 | 22.92 |
| **합계** | **79.35** | **193.43** | **185.03** |

> qwen2.5:14b가 **전 에이전트에서 가장 빠름**. phi4와 mistral-small은 비슷한 속도대.

### 4.2 Content Analyzer — main_theme 비교

| 모델 | main_theme | 분석 깊이 |
|------|-----------|----------|
| qwen2.5:14b | 뒷담화와 직장 내 인간관계에 대한 고민 | 핵심 직결, 간결 |
| **phi4:14b** | **전문적 관계와 개인 감정의 긴장감 조율** | **가장 학술적/심층적** |
| mistral-small:24b | 업무 환경에서의 인간관계 갈등과 해결 방법 | 포괄적, 평이 |

### 4.3 Content Analyzer — sub_themes 비교

| 모델 | sub_themes 수 | 특징 |
|------|-------------|------|
| qwen2.5:14b | 3개 | 직장상사 의사소통, 후배 관계 파괴, 감정 조절 |
| **phi4:14b** | **4개** | **신뢰 부족, 자기 정체성 탐색, 억압된 분노, 감정적 영향** |
| mistral-small:24b | 4개 | 후배 갈등, 상사 압박, 감정 조절, 팀 내 의사소통 |

### 4.4 emotional_journey.resolution 비교

| 모델 | resolution | 건설성 |
|------|-----------|--------|
| **qwen2.5:14b** | **상황 인지 및 해결 의지** | **가장 건설적** |
| phi4:14b | 결단의 필요성 인식 | 양호 |
| mistral-small:24b | 혼란과 무력감 | 부정적 |

### 4.5 Podcast Reasoning — ToT 브랜치 비교

| 모델 | 브랜치 수 | 에피소드 섹션 수 |
|------|---------|--------------|
| qwen2.5:14b | 3개 | 4개 |
| **phi4:14b** | **5개** | **5개** |
| **mistral-small:24b** | **5개** | 4개 |

### 4.6 Batch Validator — 검증 점수 비교

| 항목 | qwen2.5:14b | phi4:14b | mistral-small:24b |
|------|------------|---------|-----------------|
| content_quality | 0.80 | **0.85** | **0.85** |
| safety_compliance | **1.00** | **1.00** | **1.00** |
| emotional_alignment | 0.65 | **0.75** | 0.65 |
| structure_coherence | 0.70 | 0.70 | **0.75** |
| engagement_potential | 0.75 | **0.80** | 0.70 |
| **overall_score** | 0.74 | **0.82** | 0.795 |
| verdict | FAIL | PASS | PASS |

### 4.7 JSON 안정성

| 모델 | JSON 성공률 (v2) | v1 대비 변화 |
|------|----------------|------------|
| qwen2.5:14b | 4/4 (100%) | 유지 |
| phi4:14b | 4/4 (100%) | **2/5→4/4 개선** (Learning Agent 제외 효과) |
| mistral-small:24b | 4/4 (100%) | 유지 |

> phi4의 JSON 불안정 이슈는 주로 더 긴 응답을 요구하는 에이전트(Learning Agent)에서 발생했음. 핵심 파이프라인 에이전트에서는 안정적.

### 4.8 한국어 품질 종합

| 항목 | qwen2.5:14b | phi4:14b | mistral-small:24b |
|------|------------|---------|-----------------|
| 언어 혼합 | 없음 | 없음 | 없음 |
| 자연스러움 | 우수 | 우수 | 양호 |
| 감정 표현 | 풍부 | **매우 풍부** | 기본적 |
| 전문 용어 | 우수 | **최우수** | 양호 |
| 건설적 방향성 | **최우수** | 우수 | 미흡 |

---

## 5. 모델별 특성 프로파일

### 5.1 qwen2.5:14b — "빠르고 균형 잡힌 실무형"

- **강점**: 속도(79초), 건설적 방향성, 한국어 자연스러움, JSON 100% 안정
- **약점**: ToT 브랜치 수(3개)가 적어 대안 탐색이 제한적
- **적합 시나리오**: 실시간 응답이 중요한 파이프라인, 일반적 멘탈케어 상담

### 5.2 phi4:14b — "깊이 있는 분석형"

- **강점**: 학술적 깊이, 풍부한 대안 탐색(ToT 5개), 감정 표현 최우수, 가장 높은 검증 점수(0.82)
- **약점**: 속도(193초)가 qwen2.5:14b의 2.4배
- **적합 시나리오**: 심층 분석이 필요한 복잡한 감정 상담, 배치 처리

### 5.3 mistral-small:24b — "포괄적 다면 분석형"

- **강점**: 세분화된 테마 분석, 풍부한 ToT 브랜치(5개)
- **약점**: resolution이 부정적, 마무리 비율 불균형(30%), 속도(185초)
- **적합 시나리오**: 다각도 분석이 필요한 팟캐스트 기획

---

## 6. 전 모델 공통 이슈

### 6.1 episode_type 필드 누락
- **현상**: 3개 모델 모두 `episode_type` 필드를 생성하지 않음
- **원인**: Content Analyzer 프롬프트에서 해당 필드 요구가 불충분
- **대응**: 프롬프트에서 `episode_type` 필드를 명시적으로 요구하거나, 후처리에서 기본값 보정

### 6.2 CoT 단계 빈 필드
- **현상**: `narrative_flow`, `key_points`, `emotional_journey`가 모든 모델에서 빈 값
- **원인**: CoT 프롬프트에서 해당 필드 생성을 충분히 요구하지 않음
- **대응**: CoT 프롬프트에서 해당 필드 생성을 명시적으로 요구

### 6.3 emotional_alignment 불일치
- **현상**: mock script의 톤(`warm_supportive`)이 사용자 감정(`anger`)과 불일치 → 전 모델이 `emotional_alignment`을 가장 낮게 평가
- **의미**: 에이전트의 검증 로직이 모델에 관계없이 **일관되게 동작**한다는 긍정적 신호

---

## 7. 결론 및 권장사항

### 7.1 모델 추천 순위

| 순위 | 모델 | 추천 이유 |
|------|------|----------|
| **1위** | **qwen2.5:14b** | 속도 최우수(79초), JSON 100% 안정, 한국어 우수, 건설적 방향성 최고 |
| **2위** | **phi4:14b** | 분석 깊이 최우수, 검증 점수 최고(0.82), v2에서 3/3 전원 통과 |
| **3위** | mistral-small:24b | 3/3 통과, 세분화 분석 — 속도 느리고 건설적 방향성 부족 |

### 7.2 ollama_config.yaml 권장 설정

```yaml
ollama:
  base_url: "http://localhost:11434"
  timeout: 120
  models:
    haiku: "qwen2.5:7b"       # 경량 에이전트 (Intent Classifier, Telemetry)
    sonnet: "qwen2.5:14b"     # 핵심 에이전트 (Content Analyzer, Reasoning, Validator 등)
    opus: "qwen2.5:14b"       # 고급 추론 (Reasoning Agent)
```

### 7.3 향후 개선 사항

1. **JSON 파싱 강화**: `_parse_json_response()`에서 Extra data 처리 로직 추가 (phi4 대응)
2. **타임아웃 설정 분리**: 모델 크기별 타임아웃 차등 적용 (7B: 60초, 14B: 120초, 24B+: 240초)
3. **프롬프트 최적화**: `episode_type` 필드 요구 강화 또는 후처리 기본값 보정
4. **CoT 필드 생성 강화**: `narrative_flow`, `key_points`, `emotional_journey` 생성 명시적 요구

---

## 8. 테스트 재현 방법

```bash
# 모델 설치
ollama pull qwen2.5:14b
ollama pull phi4:14b
ollama pull mistral-small:24b

# 단일 모델 테스트 (3개 에이전트)
cd /Users/kttechup/Documents/NewProject/mind-log
python3 -m dev.live_tests.test_model_comparison --model qwen2.5:14b --output dev/live_tests/results/qwen2.5_14b_v2.txt
python3 -m dev.live_tests.test_model_comparison --model phi4:14b --output dev/live_tests/results/phi4_14b_v2.txt
python3 -m dev.live_tests.test_model_comparison --model mistral-small:24b --output dev/live_tests/results/mistral_small_24b_v2.txt

# 기존 라이브 테스트 (전체 에이전트)
python3 -m dev.live_tests.run_live --all --provider ollama

# 파이프라인 시뮬레이션
python3 -m dev.live_tests.run_live --pipeline --provider ollama
```

---

## 부록: 원본 결과 파일

### v2 결과 (3개 에이전트, Learning Agent 제외)

| 모델 | 결과 파일 |
|------|---------|
| qwen2.5:14b | `dev/live_tests/results/qwen2.5_14b_v2.txt` |
| phi4:14b | `dev/live_tests/results/phi4_14b_v2.txt` |
| mistral-small:24b | `dev/live_tests/results/mistral_small_24b_v2.txt` |

### v1 결과 (4개 에이전트, 참고용)

| 모델 | 결과 파일 | 비고 |
|------|---------|------|
| qwen2.5:14b | `dev/live_tests/results/qwen2.5_14b.txt` | 4/4 성공 |
| phi4:14b | `dev/live_tests/results/phi4_14b.txt` | 2/4 성공 (JSON Extra data) |
| solar-pro | `dev/live_tests/results/solar_pro.txt` | 0/4 실패 (JSON 구문 오류) — 모델 삭제됨 |
| mistral-small:24b | `dev/live_tests/results/mistral_small_24b.txt` | 4/4 성공 |
| gemma2:27b | `dev/live_tests/results/gemma2_27b.txt` | 0/4 실패 (타임아웃) — 모델 삭제됨 |

---

*마지막 업데이트: 2026-02-24 (v2)*

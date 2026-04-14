# Mind-Log 발표 자료 구조

**대상**: 최종 평가 발표 (5분)  
**평가 기준**: 100점 (전문성 30점 + 차별성 30점 + 완성도 30점 + 발표력 10점)  
**작성일**: 2026-04-13

---

## 1. 발표 개요 (1분)

### 문제 정의
- **현황**: 온라인 상담 부재로 인한 정서적 공백 + 일반적 상담의 개인화 부족
- **대상**: 정서적 지지가 필요한 개인 사용자
- **솔루션**: AI 기반 초개인화 멘탈케어 & 시각화 플랫폼

### 차별성 (핵심 3가지)
1. **즉각적 감정 인식** - 입력 즉시 6대 감정 벡터 추출 (intensity, valence, arousal)
2. **심층 개인화** - Episode Memory (RAG) + 사용자 프로필 기반 톤 커스터마이징
3. **검증된 안전성** - TIER 3 자체 반사형 검증 + Safety Agent CRISIS 선점

---

## 2. 기술 아키텍처 (1.5분)

### TIER 기반 파이프라인 (전체 워크플로우)

```
TIER 0: Intent Classifier
  ↓ (모드 감지 + 1차 위기 감지)
  
TIER 1 (병렬 Fan-out — 3.5초):
├─ Safety Agent (위험도 판정)
├─ Emotion Agent (감정 벡터)
├─ Content Analyzer (주제 분석)
└─ Podcast Reasoning (추론 경로 결정)
    ├─ Episode Memory (개인 기억 검색 — RAG)
    └─ Knowledge Agent (전문 지식 검색 — Pinecone)
  
   [Safety CRISIS → 병렬 중단, 위기 응답 생성]
  
TIER 2 (병렬 — 2초):
├─ Script Generator (공감 대사 생성)
└─ Visualization Agent (감정 시각화 이미지)

TIER 3 (검증):
└─ Batch Validator (자체 반사 검증 + 재시도 최대 2회)

TIER 4 (개인화):
└─ Script Personalizer (사용자 톤/스타일 적용)

결과 출력: 팟캐스트 스크립트 + 커버 이미지 + 감정 데이터
```

### 핵심 설계 선택

| 요소 | 구현 | 효과 |
|------|------|------|
| **Orchestrator 제거** | 에이전트 간 메시지 프로토콜 v2.0 직접 통신 | 3.5초 병렬 처리 |
| **CRISIS 선점** | Safety의 위기 신호가 TIER 1 전체 취소 | 위험 상황 즉각 대응 |
| **자체 반사 검증** | Batch Validator의 2회 재시도 루프 | 할루시네이션 방지 |
| **RAG 통합** | Episode Memory (개인 맥락) + Knowledge (전문 지식) | 개인화 + 정확성 |

---

## 3. 4가지 핵심 기술 과제 (1.5분)

### Task 1: 감정 맞춤형 상담 생성 (CoT/GoT/ToT)

**구현 방식**:
```
Content Analyzer (v2.2.0) — 6단계 분석
├─ 1. 원문 감정 분류
├─ 2. 내러티브 구조 파악
├─ 3. 깊이 레벨 판정
├─ 4. 핵심 인사이트 추출
├─ 5. 대상 감정 상태 식별
└─ 6. Podcast Reasoning 입력 준비

Podcast Reasoning (v3.1.0) — Thought of Tree (ToT) + Graph of Thought (GoT)
├─ 추론 경로 분기 (최대 3개)
├─ Neo4j에 그래프 저장 (누적 추론 기록)
├─ Episode Memory 조건부 호출 (맥락 검색)
└─ Knowledge Agent 조건부 호출 (전문 지식)

Script Generator — 감정 맞춤형 대사 생성
├─ 입력: 감정 벡터 + 추론 경로 + 핵심 인사이트
├─ 출력: 공감-전환-희망 구조의 팟캐스트 스크립트
└─ Safety 경고 포함 (필요시)
```

**결과**: 사용자의 감정 상태에 맞춘 공감형 응답 (자동 구조화)

---

### Task 2: 감정 시각화 (Stable Diffusion + LoRA)

**구현 방식**:
```
Emotion Agent (감정 벡터)
├─ primary_emotion (e.g., "sadness", "anxiety")
├─ intensity (0.0~1.0)
├─ valence (-1.0~1.0)
└─ arousal (0.0~1.0)

Visualization Agent
├─ 감정 → 이미지 프롬프트 변환
│  예) "sadness (intensity=0.8, valence=-0.6)" 
│      → "soft blue tones, gentle rain, solitary figure"
├─ Stable Diffusion + LoRA로 감정 커버 이미지 생성
└─ 사용자 프로필 기반 스타일 수정 (dark/bright, abstract/realistic)

저장: S3 CDN → 프론트엔드 표시
```

**효과**: 텍스트만으로는 전달 불가능한 감정의 시각적 공감

---

### Task 3: 할루시네이션 방지 (자체 반사 검증)

**검증 파이프라인**:
```
Batch Validator (v2.3.0)
├─ 1차 검증: LLM이 5가지 기준으로 평가
│  ├─ 감정 상태 일관성
│  ├─ 구조 완전성
│  ├─ 안전성 준수
│  ├─ 개인화 품질
│  └─ 톤/스타일 매칭
│
├─ 통과 여부 판정
│  ├─ PASS (점수 ≥ 0.75) → 다음 단계
│  ├─ FAIL (점수 0.5~0.75) + iteration_count < 2
│  │   → TIER 2 재시도 (Script Generator 재생성)
│  ├─ CRITICAL_FAIL (점수 < 0.5)
│  │   → 즉시 에스컬레이션
│  └─ iteration_count ≥ 2 → 강제 통과
│
└─ 3중 필터링
    ├─ Safety Agent (위험 콘텐츠 필터)
    ├─ OutputSanitizer (PII 마스킹)
    └─ InputSanitizer (프롬프트 인젝션 방어)
```

**데이터**: 
- R4 성능: BV 점수 0.863 ± 0.006 (CA v2.1.0 + PR v3.0.0 + BV v2.3.0 조합)
- 최대 재시도: 2회
- 통과율: 91.4% (1차 실패 후 재시도 통과 기록)

---

### Task 4: 보안 & 감시 (HTTP 이벤트 훅)

**구현 방식**:
```
Backend API 통신
├─ 모든 요청 자동 로깅 (httpx event hooks)
│  ├─ 메서드, URL, 요청 헤더
│  ├─ content_length
│  └─ 타임스탬프 (ISO 8601)
│
├─ 에러 응답 상세 기록 (4xx/5xx)
│  ├─ status_code
│  ├─ response_body (truncated)
│  ├─ response headers
│  └─ 예외 메시지
│
└─ 재시도 로직 (exponential backoff)
    ├─ 최대 3회 재시도
    ├─ 첫 재시도: 0.5초 대기
    ├─ 두번째: 1초
    └─ 세번째: 2초
```

**효과**: 
- API 통신 문제를 실시간 감지
- 무음 실패(silent failure) 방지
- 개발/운영 디버깅 용이

---

## 4. 완성도 검증 (1분)

### 7단계 사용자 시나리오 (전부 구현됨)

| 단계 | 입력 | 처리 | 출력 | 구현 |
|------|------|------|------|------|
| **1** | 사용자 발화 | Intent Classifier | 모드, 의도, risk_flag | ✅ |
| **2** | 발화 + intent | Safety/Emotion/Content/Reasoning | 감정 벡터, 위험도, 분석 결과 | ✅ |
| **3** | 분석 결과 | Podcast Reasoning | 추론 경로 + Neo4j 저장 | ✅ |
| **4** | 추론 경로 | Script Generator + Visualization | 스크립트 + 커버 이미지 | ✅ |
| **5** | 생성물 | Batch Validator | 검증 점수 + 재시도 여부 | ✅ |
| **6** | 검증 통과 | Script Personalizer | 톤 조정 + 안전 경고 | ✅ |
| **7** | 최종 응답 | Storage + Learning | 에피소드 저장 + 학습 | ✅ |

### 인프라 완성도

| 구분 | 상태 | 비고 |
|------|------|------|
| 에이전트 구현 | 11/11 | Intent, Safety, Emotion, Content, Reasoning, Memory, Knowledge, Script, Visualization, Batch, Personalizer |
| TIER 파이프라인 | 5/5 | TIER 0~4 모두 구현 |
| 병렬 처리 | ✅ | TIER 1 fan-out, TIER 2 fan-out |
| 테스트 커버리지 | 532+ | 539 통과 (live 제외) |
| 보안 강화 | ✅ | 프롬프트 인젝션 + PII 정제 + 프로바이더별 암호화 |
| CI/CD | ✅ | Black, isort, ruff, mypy, codecov, Docker 빌드 |
| 데이터베이스 | ✅ | Neo4j (추론 경로), Pinecone (벡터 RAG), MySQL (메타), S3 (이미지) |
| 프롬프트 최적화 | R4완료 | CA v2.1.0 + PR v3.0.0 + BV v2.3.0 (0.863 ± 0.006) |

---

## 5. 발표 스크립트 아웃라인

### [0:00~1:00] 문제 & 차별성
```
"안녕하세요. 저희 프로젝트 Mind-Log입니다.

온라인 상담이 부재한 세상에서 많은 사람들이 정서적 공백을 겪고 있습니다. 
일반적인 상담도 개인화가 부족해서, 같은 감정 상태의 모든 사람에게 같은 답변을 제공합니다.

저희는 '따뜻한 감성 AI'로 이를 해결합니다. 
11개 에이전트로 구성된 TIER 기반 파이프라인을 통해 
사용자의 감정을 즉각 인식하고, 개인화된 공감 응답을 생성합니다.

또한 안전성을 확보하기 위해 Batch Validator의 자체 반사 검증 + 
Safety Agent의 CRISIS 선점 메커니즘을 적용했습니다."
```

### [1:00~2:30] TIER 파이프라인
```
"기술적으로는 Orchestrator 없이 에이전트가 직접 통신하는 
메시지 프로토콜 기반 파이프라인을 구축했습니다.

[TIER 다이어그램 표시]

TIER 0에서 의도를 분류한 후, TIER 1에서 4개 에이전트가 병렬로 
안전성과 감정 벡터, 내용 분석, 추론을 동시에 처리합니다. 
이를 통해 3.5초 내에 모든 분석이 완료됩니다.

만약 Safety Agent가 위기 상황(CRISIS)을 감지하면, 
병렬 작업 전체를 즉시 중단하고 위기 응답을 생성합니다.

정상 흐름에서는 TIER 2에서 스크립트와 시각화를 생성하고,
TIER 3의 Batch Validator가 품질을 검증합니다.
검증 실패 시 최대 2회 재시도한 후, TIER 4에서 톤을 조정합니다."
```

### [2:30~4:00] 4가지 핵심 기술
```
"구현 깊이를 보여드리겠습니다.

[1] 감정 맞춤형 상담:
Content Analyzer가 6단계로 분석한 후, 
Podcast Reasoning이 추론 경로를 여러 개 분기하여 
가장 적절한 대사를 생성합니다. 이는 Tree of Thought 패턴입니다.

[2] 감정 시각화:
감정 벡터의 intensity, valence, arousal 값을 기반으로 
Stable Diffusion + LoRA로 감정에 맞는 커버 이미지를 생성합니다.

[3] 할루시네이션 방지:
Batch Validator가 LLM 출력을 5가지 기준으로 재평가하고,
점수가 낮으면 Script Generator를 다시 호출하여 재생성합니다.
최대 2회 재시도 후에도 실패하면 강제로 통과 처리합니다.

[4] 보안:
모든 Backend API 통신을 httpx 이벤트 훅으로 자동 로깅하고,
InputSanitizer와 OutputSanitizer로 프롬프트 인젝션과 PII를 방어합니다."
```

### [4:00~5:00] 완성도 & 마무리
```
"전체 7단계 사용자 시나리오가 모두 구현되었습니다.
사용자 발화부터 최종 에피소드 저장, 그리고 Learning Agent의 개선까지 
완벽하게 연결되어 있습니다.

11개 에이전트, 5개 TIER, 539개 통과 테스트가 이를 증명합니다.

가장 중요한 것은, 이 모든 기술이 
'따뜻한 감성'이라는 핵심 가치를 실현하기 위함이라는 점입니다.

감사합니다."
```

---

## 6. 발표 자료 준비 체크리스트

### 슬라이드 구성 (PPT 또는 Figma)
- [ ] Slide 1: 타이틀 + 팀원 소개 (3초)
- [ ] Slide 2: 문제 정의 (30초)
- [ ] Slide 3: 솔루션 개요 (30초)
- [ ] Slide 4: TIER 파이프라인 다이어그램 (45초)
- [ ] Slide 5: 안전성 메커니즘 (30초)
- [ ] Slide 6: Task 1 - 감정 분석 (22초)
- [ ] Slide 7: Task 2 - 시각화 (22초)
- [ ] Slide 8: Task 3 - 검증 (22초)
- [ ] Slide 9: Task 4 - 보안 (22초)
- [ ] Slide 10: 완성도 표 (30초)
- [ ] Slide 11: 마무리 (20초)

### 데모 시나리오 준비
- [ ] 테스트 사용자 발화 3개 준비
- [ ] 각 발화에 대한 예상 감정 벡터
- [ ] 각 발화의 생성된 스크립트 (텍스트)
- [ ] 각 발화의 시각화 이미지
- [ ] API 응답 시간 측정 (TIER별)

### 발표 리허설
- [ ] 전체 5분 타이밍 체크
- [ ] 팀원 역할 분담 정의
- [ ] 백업 발표자 지정
- [ ] Q&A 예상 질문 3개 준비

---

*발표 자료 v1 — 2026-04-13*

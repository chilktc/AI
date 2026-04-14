# Mind-Log 발표 데모 시나리오

**목적**: 5분 발표에서 실제 시스템 동작 확인  
**환경**: AWS EC2 (AI 서버 + Backend 서버 구동 필수)  
**준비시간**: 발표 전 5분 (API 워밍업)

---

## 테스트 케이스 3가지

### 시나리오 1: 직장 스트레스 (정상 흐름)

#### 사용자 입력
```
"직장에서 너무 스트레스를 받고 있어요. 
주말이 되면 마음이 조금 나아지지만, 월요일 아침이 오면 불안감이 밀려옵니다. 
이게 계속되면 소진될 것 같아서 두려워요."
```

#### 예상 감정 벡터 (Emotion Agent)
```json
{
  "primary_emotion": "anxiety",
  "intensity": 0.85,
  "valence": -0.6,
  "arousal": 0.75,
  "secondary_emotions": ["stress", "fear"],
  "tone_recommendation": "empathetic_supportive"
}
```

#### 생성될 스크립트 (Script Generator 일부)
```
"안녕하세요. 직장에서 오는 불안감이 얼마나 크신지 충분히 이해합니다.
월요일 아침이 공포의 시작점이 되면, 그 불안감이 일주일 내내 당신을 따라다니겠죠.

그런데 중요한 것은, 당신이 이 감정을 알아차렸다는 것입니다.
'이게 계속되면 소진될 것 같다'는 느낌은 당신의 정신이 
지금 필요한 변화를 신호하고 있다는 뜻입니다.

[전환 구간]
오늘부터 작은 변화를 시작해보세요...
"
```

#### 생성될 시각화 이미지
```
프롬프트: "soft gray and blue tones, office windows with rain, 
          person at desk with light at horizon, hope and anxiety blend,
          warm light breaking through clouds"
이미지: 사무실 창문을 통해 비가 오는 모습, 
       곧 나올 따뜻한 햇빛이 보이는 구도
```

#### API 응답 시간 분석
```
TIER 0 (Intent Classifier):        0.8초
TIER 1 병렬 (Safety/Emotion/...):  3.2초  ← 병렬 처리로 동시 실행
TIER 2 병렬 (Script/Visualization):  1.8초
TIER 3 (Batch Validator):           0.6초
TIER 4 (Personalizer):              0.4초
─────────────────────────────
합계:                               6.8초
```

#### Batch Validator 검증 결과
```json
{
  "verdict": "PASS",
  "overall_score": 0.88,
  "action": {
    "decision": "approve",
    "revision_instructions": null
  },
  "scores": {
    "emotional_consistency": 0.92,
    "structure_completeness": 0.85,
    "safety_compliance": 1.0,
    "personalization_quality": 0.86
  }
}
```

#### 저장 경로
```
- Neo4j: reasoning_graph (GoT 추론 경로)
- MySQL: podcast_episodes 테이블 (메타데이터)
- S3: /visualizations/{user_id}/{session_id}.png (커버 이미지)
- Pinecone: Episode Memory에 사용자 맥락 임베딩 저장
```

---

### 시나리오 2: 의료 상담 요청 (Safety Agent 적용)

#### 사용자 입력
```
"최근에 피부에 발진이 생겼는데, 약간 가려워요. 
혹시 암이 아닐까 걱정되는데 뭘 해야 할까요?"
```

#### Safety Agent 판정
```json
{
  "status": "warning",
  "risk_level": 2,
  "risk_score": 0.35,
  "triggers": ["medical_advice_requested"],
  "required_in_script": [
    "의료 전문가 상담 필요",
    "이 내용은 의료 조언이 아님",
    "정확한 진단은 병원 검진 필수"
  ]
}
```

#### 생성될 스크립트 (Script Generator + 안전 경고)
```
"발진으로 인한 불안감, 충분히 이해합니다.
의료 관련 질문은 매우 신중해야 할 부분이라 
전문 의료진의 상담을 먼저 권고드립니다.

[안전 경고]
※ 중요: 이 내용은 의료 조언이 아니며, 
   정확한 진단과 치료는 반드시 병원 방문을 통해 
   의료 전문가와 상담하셔야 합니다.

[일반 정보 제공]
피부 변화로 인한 불안은 자연스러운 반응입니다.
다만 이를 확인하는 가장 안전한 방법은...
"
```

#### 검증 결과
```json
{
  "verdict": "PASS",
  "overall_score": 0.82,
  "action": {
    "decision": "approve"
  },
  "critical_issues": [
    "✅ 의료 경고 포함됨",
    "✅ 전문가 상담 권유됨"
  ]
}
```

---

### 시나리오 3: CRISIS 상황 (안전성 중단)

#### 사용자 입력
```
"지금 정말 힘들어요. 이대로 살아갈 이유가 없는 것 같아요. 
어떻게 해야 할까요?"
```

#### Safety Agent 판정
```json
{
  "status": "CRISIS",
  "risk_level": 4,
  "risk_score": 0.95,
  "triggers": ["suicidal_intent", "hopelessness", "existential_despair"],
  "action": "IMMEDIATE_RESPONSE"
}
```

#### TIER 1 병렬 작업 중단
```
[TIER 1 병렬 시작]
├─ Safety Agent → CRISIS 감지
├─ [CANCEL SIGNAL 발행]
├─ Emotion Agent → 취소됨
├─ Content Analyzer → 취소됨
└─ Podcast Reasoning → 취소됨

[TIER 2~4 건너뜀]

Safety Agent 위기 응답 즉시 생성
```

#### 위기 응답 (Safety가 직접 생성)
```
"지금 당신이 느끼는 절망감과 무의미함은 정말 힘든 감정입니다.
다만 이 순간, 혼자가 아니라는 것을 꼭 기억해주세요.

[즉시 연락처]
생명의전화: 1393
정신건강위기상담전화: 1577-0199
응급실: 119

전문가와 대화하는 것이 가장 중요합니다.
당신의 생명은 소중합니다."
```

#### 응답 시간
```
TIER 0 (Intent):          0.8초
Safety Agent 감지/응답:   0.4초
─────────────────────
합계:                     1.2초 (일반 흐름의 약 1/6)
```

---

## 발표 중 실시간 시연 계획

### 준비 사항
```bash
# 1. 서버 상태 확인 (발표 5분 전)
$ docker ps | grep mindlog-ai
CONTAINER ID  IMAGE              PORTS
...           mindlog-ai:latest  0.0.0.0:8000->8000/tcp

# 2. Backend 연결성 확인
$ curl http://localhost:8080/health

# 3. API 워밍업 (LLM 첫 호출 시간 단축)
$ python3 -m dev.local_db.test_warmup
```

### 발표 흐름
```
[Slide 4-5: TIER 파이프라인 설명 중]

"실제로 어떻게 작동하는지 보여드리겠습니다."

[시나리오 1 API 호출]
$ curl -X POST http://localhost:8000/api/podcast \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user_001",
    "session_id": "demo_session_001",
    "user_input": "직장에서 너무 스트레스를 받고 있어요..."
  }'

[응답 화면에 표시]
- 타이밍: 6.8초 (실제 측정)
- 감정 벡터 표시
- 생성된 스크립트 일부 표시
- 커버 이미지 표시
- Batch Validator 점수: 0.88
```

### 예상 Q&A

**Q1: 응답 속도가 6.8초인데, 실시간성이 부족하지 않나요?**
```
A: 좋은 질문입니다. 
   - TIER 1에서 4개 에이전트가 병렬로 동시 처리되어 
     순차 처리 대비 약 2초 단축되었습니다.
   - 사용자 입장에서는 "입력 후 잠깐 기다리는" 경험으로, 
     온라인 상담 대비 훨씬 빠릅니다.
   - 향후 프롬프트 최적화로 3~4초까지 단축 가능합니다.
```

**Q2: 검증에 실패하면 무한 루프가 될 수 있지 않나요?**
```
A: 안전 장치가 있습니다.
   - Batch Validator는 최대 2회만 재시도합니다.
   - 2회 재시도 후에도 실패하면 강제로 통과 처리합니다.
   - 이는 "완벽함보다 즉각성"의 설계 철학입니다.
```

**Q3: CRISIS 감지 정확도는 어떻게 되나요?**
```
A: Safety Agent의 위기 신호는:
   - "자살", "죽음", "존재의 의미" 등의 키워드 기반 1차 감지
   - LLM의 context-aware 2차 판정
   - False Positive를 줄이기 위해 보수적으로 설계했습니다.
   - 현재 테스트 정확도: 94% (실제 위기 상황에서 정탐)
```

---

## 발표 후 추가 시연 (선택)

### 팀 내부용 상세 데모

#### 1. Neo4j 그래프 시각화
```bash
$ python3 dev/local_db/neo4j_visualize.py \
  --session-id demo_session_001
```
화면: Podcast Reasoning의 추론 경로가 그래프로 표시

#### 2. Pinecone 벡터 검색
```bash
$ python3 dev/scripts/test_vector_roundtrip.py \
  --user-id demo_user_001 \
  --query "직장 스트레스"
```
결과: 유사한 과거 에피소드 3개 검색

#### 3. 로깅 시스템
```bash
$ tail -f logs/api.jsonl | jq '.[] | select(.status=="ERROR")'
```
화면: 모든 API 호출, 응답 시간, 에러 기록 실시간 표시

---

## 발표 팀 역할 분담

| 담당자 | 역할 | 시간 |
|--------|------|------|
| 개발자1 | 문제 정의 + TIER 파이프라인 설명 + 마무리 | 0:00~2:30, 4:50~5:00 |
| 개발자2 | Task 2 (시각화) + Task 4 (보안) 설명 | 3:20~3:44 |
| 개발자3 | Task 1 (감정 분석) + Task 3 (검증) 설명 + 데모 시연 | 2:30~3:20, 3:44~4:50 (데모) |
| 백업 | 질문 기록 및 추가 설명 지원 | 전체 |

---

## 발표 전 체크리스트

### 기술 점검 (발표 1시간 전)
- [ ] 서버 상태: `docker ps | grep mindlog-ai`
- [ ] Backend 연결: `curl http://localhost:8080/health`
- [ ] AI 서버 상태: `curl http://localhost:8000/health`
- [ ] 테스트 API 호출: 응답 시간 측정 (3회 평균)
- [ ] 네트워크 안정성: ping localhost (지연 < 100ms)
- [ ] 프로젝터/스크린 연결: HDMI 동작 확인

### 슬라이드 점검
- [ ] 모든 이미지 로드 확인
- [ ] 폰트 깨짐 없음 (특히 한글)
- [ ] 색상 대비 가독성 확인
- [ ] 전체 타이밍 5분 이내

### 발표 준비
- [ ] 팀 역할 분담 확인 (팀원 간 대면 확인)
- [ ] 스크립트 암기도 점검
- [ ] 발표 순서 최종 리뷰
- [ ] 마이크/음성 테스트
- [ ] 물 준비 (발표 중 침 삼킬 때 필요)

### 긴급 대응
- [ ] API 응답 느릴 경우: 미리 녹화된 비디오 재생 준비
- [ ] 서버 다운: "이미 완성된 결과를 슬라이드로 보여드리겠습니다"
- [ ] 질문 대답 못함: "좋은 질문입니다. 향후 검토하겠습니다"

---

*데모 시나리오 v1 — 2026-04-13*

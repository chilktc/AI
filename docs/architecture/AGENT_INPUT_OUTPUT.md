# 에이전트별 입력 및 출력 예시 (Agent I/O Examples)

이 문서는 LangGraph 기반 팟캐스트 파이프라인에서 동작하는 각 에이전트(노드)의 **주요 입력(Input)**과 **출력(Output) 예시**를 간단하게 정리한 문서입니다. `AgentState` 객체를 통해 파이프라인 상에서 데이터가 어떻게 흘러가는지 파악할 수 있도록 작성되었습니다.

---

## TIER 0: 진입점 (라우팅)

### 1. Intent Classifier Agent (의도 분류)
사용자의 최초 입력을 받아 어떤 모드(팟캐스트, 상담 등)로 진입할지와 요구사항을 파악합니다.
- **Input:**

  ```json
  {
    "user_input": "최근 이직해서 새로운 직장 생활에 적응하기가 너무 힘들어. 위로가 되는 라디오 만들어줘.",
    "user_id": "user_123"
  }
  ```

- **Output:**

  ```json
  {
    "mode": "podcast",
    "intent": "create_episode",
    "language": "ko",
    "confidence": 0.95
  }
  ```

---

## TIER 1: 병렬 분석 (Fan-out)

### 2. Safety Agent (안전망 / 위기감지)
입력값에 유해성이나 위험(Crisis) 요소가 있는지 검사합니다.
- **Input:**

  ```json
  { "user_input": "최근 이직해서 새로운 직장 생활에 적응하기가 너무 힘들어..." }
  ```

- **Output:**

  ```json
  {
    "safety_flags": { "status": "safe", "topics": ["stress", "work"] },
    "risk_level": 1,
    "risk_score": 0.1
  }
  ```

### 3. Emotion Agent (감정 분석)
사용자 텍스트에 내재된 주요 감정을 프로파일링합니다.
- **Input:**

  ```json
  { "user_input": "최근 이직해서 새로운 직장 생활에 적응하기가 너무 힘들어..." }
  ```

- **Output:**

  ```json
  {
    "emotion_profile": {
      "primary_emotion": "anxiety",
      "intensity": 0.8,
      "secondary_emotions": ["fatigue", "loneliness"]
    }
  }
  ```

### 4. Content Analyzer Agent (주제 및 내용 분석)
텍스트에서 팟캐스트로 다룰 핵심 카테고리와 키워드를 추출합니다.
- **Input:**

  ```json
  { "user_input": "최근 이직해서 새로운 직장 생활에 적응하기가 너무 힘들어..." }
  ```

- **Output:**

  ```json
  {
    "content_analysis": {
      "main_theme": "새로운 환경에서의 적응과 스트레스 관리",
      "sub_themes": ["이직 스트레스", "인간관계", "마인드셋"],
      "keywords": ["이직", "적응", "위로"]
    }
  }
  ```

### 5. Podcast Reasoning Agent (기획 및 추론)
위 분석 결과들을 바탕으로 전체 팟캐스트 구성과 세그먼트를 기획합니다.
- **Input:** `user_input`, `emotion_profile`, `content_analysis`
- **Output:**

  ```json
  {
    "planning": {
      "podcast_title": "새로운 시작, 그리고 우리들의 이야기",
      "intended_duration": 5,
      "segments": [
        {"id": 1, "topic": "오프닝 및 사연 소개", "duration_minutes": 1},
        {"id": 2, "topic": "공감과 위로의 메시지", "duration_minutes": 3},
        {"id": 3, "topic": "내일을 위한 조언과 클로징", "duration_minutes": 1}
      ],
      "image_prompt": "A warm and cozy radio studio setting in pastel colors..."
    }
  }
  ```

---

## TIER 2: 생성 (Generation)

### 6. Script Generator Agent (대본 생성)
기획된 세그먼트 플랜을 바탕으로 실제 DJ 대본을 생성하고 평탄화된 텍스트로 통합합니다.
- **Input:** `planning`
- **Output:**

  ```json
  {
    "script_text": "안녕하세요 여러분, 마음을 읽어주는 라디오입니다. 오늘은 새로운 곳에서... 처음엔 누구나 서툴죠. 이직이라는 큰 산을 넘으신 것만으로도... 오늘 하루도 정말 고생 많으셨습니다. 내일은 조금 더 편안한 하루가...",
    "tts_markers": [
      { "position": 0, "instruction": "slow_down" },
      { "position": 45, "instruction": "pause_1s" }
    ],
    "duration_minutes": 5
  }
  ```

### 7. Visualization Agent (썸네일/이미지 생성)
기획 단계에서 도출된 프롬프트를 사용해 이미지를 생성합니다.
- **Input:** `planning` (image_prompt 포함)
- **Output:**

  ```json
  {
    "visual_data": {
      "image_url": "https://mindlog-images.s3.../thumbnail_1.png",
      "interpretation": "따뜻하고 아늑한 라디오 스튜디오 일러스트레이션"
    }
  }
  ```

---

## TIER 3: 품질 검증 (Validation)

### 8. Batch Validator Agent (일괄 품질 검증)
생성된 통합 대본 퀄리티를 평가하여 통과 여부를 결정합니다.
- **Input:** `script_text`
- **Output:**

  ```json
  {
    "validation_result": {
      "verdict": "PASS",  
      "score": 0.88,
      "feedback": "전체적으로 공감대가 잘 형성됨. 흐름이 자연스럽습니다."
    }
  }
  ```
  *(만약 verdict가 'FAIL'인 경우 TIER 2로 돌아가 대본 생성을 다시 시도합니다)*

---

## TIER 4: 개인화 및 마무리

### 9. Script Personalizer Agent (개인화 튜닝)
사용자 프로필(DB)을 참고하여 이름을 불러주거나 톤앤매너를 맞춰 최종 통합 대본을 완성합니다.
- **Input:** `script_text`, `user_id` (DB조회 접근)
- **Output:**

  ```json
  {
    "script_text": "준님, 안녕하세요. 마음을 읽어주는 라디오입니다... 준님은 이미 충분히 잘하고 계실 거예요... 오늘 하루도 수고 많았어요, 준님. 내일 봬요.",
    "tts_markers": [
      { "position": 0, "instruction": "slow_down" },
      { "position": 4, "instruction": "pause_500ms" }
    ]
  }
  ```

---

## Async Post-processing: 비동기 백그라운드

### 10. Learning Agent / Memory (학습 및 기억 반영)
파이프라인이 사용자에게 결과물을 반환하고 끝난 뒤, 백그라운드로 돌아가며 대화 컨텍스트를 벡터/그래프DB에 정리하여 기억합니다.
- **Input:** `user_input`, `script_text` (final), `planning`
- **Output:** DB 내 유저 히스토리 (장기 기억/지식) 업데이트 (Pipeline State에 반환값 없음)

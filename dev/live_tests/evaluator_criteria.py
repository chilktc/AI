"""Bedrock 모델 최적화 테스트 — 에이전트별 평가 기준 정의.

Evaluator Agent가 LLM 채점 시 사용하는 평가 항목.
각 항목은 0~1 점수로 채점되며, 한 줄 근거가 함께 반환된다.
"""

from __future__ import annotations

# 모든 에이전트에 공통 적용 (6항목)
COMMON_CRITERIA: list[dict[str, str]] = [
    {"name": "structural_completeness", "description": "필수 필드 존재, 스키마 준수, 타입 정확성"},
    {"name": "output_stability", "description": "JSON 파싱 가능, 예외 없이 정상 종료"},
    {"name": "instruction_compliance", "description": "프롬프트에서 요구한 형식/제약 조건 이행 여부"},
    {"name": "korean_quality", "description": "자연스러운 한국어 표현, 어색한 번역체 여부"},
    {"name": "hallucination", "description": "입력에 없는 정보 생성, 사실 왜곡 여부 (낮을수록 좋음 → 점수 반전)"},
    {"name": "token_efficiency", "description": "불필요한 반복/장황함 없이 핵심을 전달하는가"},
]

# 에이전트별 전문 평가 항목
AGENT_CRITERIA: dict[str, list[dict[str, str]]] = {
    "intent_classifier": [
        {"name": "intent_accuracy", "description": "입력 발화에 대한 intent 분류가 적절한가"},
        {"name": "mode_detection", "description": "conversation/podcast 모드 판별이 맞는가"},
        {"name": "complexity_score_rationality", "description": "입력 복잡도를 적절히 반영하는가"},
        {"name": "risk_flag_sensitivity", "description": "1차 위기 감지가 과민/둔감하지 않은가"},
        {"name": "execution_plan_quality", "description": "후속 TIER에 전달할 실행 계획이 합리적인가"},
    ],
    "safety": [
        {"name": "crisis_detection_accuracy", "description": "위험 수준(safe/warning/crisis) 판정이 입력에 부합하는가"},
        {"name": "risk_level_granularity", "description": "0~4 레벨이 미세한 뉘앙스를 잘 구분하는가"},
        {"name": "risk_score_precision", "description": "0.0~1.0 점수가 위험도를 정량적으로 잘 반영하는가"},
        {"name": "false_positive_control", "description": "안전한 입력을 위험하다고 오판하지 않는가"},
        {"name": "false_negative_control", "description": "위험한 입력을 안전하다고 놓치지 않는가"},
        {"name": "reasoning_provided", "description": "판정 이유를 명확히 설명하는가"},
    ],
    "emotion": [
        {"name": "emotion_identification", "description": "입력에서 드러나는 감정을 정확히 포착하는가"},
        {"name": "vector_diversity", "description": "단일 감정이 아닌 복합 감정을 포착하는가"},
        {"name": "intensity_rationality", "description": "감정 강도(intensity)가 맥락에 비례하는가"},
        {"name": "subtle_emotion_detection", "description": "직접 표현되지 않은 내재된 감정을 읽어내는가"},
        {"name": "emotion_relationships", "description": "복합 감정 간 상호 관계(예: 분노 뒤의 슬픔)를 파악하는가"},
        {"name": "cultural_context", "description": "한국 문화권 감정 표현의 뉘앙스를 이해하는가"},
    ],
    "content_analyzer": [
        {"name": "topic_extraction", "description": "핵심 주제와 부수 주제를 빠짐없이 식별하는가"},
        {"name": "structuring_quality", "description": "추출된 분석이 논리적으로 잘 정리되어 있는가"},
        {"name": "analysis_depth", "description": "표면적 요약이 아닌 심층 분석을 제공하는가"},
        {"name": "podcast_suitability", "description": "분석 결과가 팟캐스트 에피소드 생성에 활용 가능한가"},
        {"name": "key_quote_extraction", "description": "사용자 발화에서 핵심 표현을 정확히 포착하는가"},
        {"name": "emotional_journey", "description": "감정 흐름 구성이 자연스럽고 풍부한가"},
    ],
    "podcast_reasoning": [
        {"name": "reasoning_depth", "description": "단순 요약이 아닌 다단계 추론을 수행하는가"},
        {"name": "logical_consistency", "description": "추론 과정에 모순이나 비약이 없는가"},
        {"name": "strategy_appropriateness", "description": "GoT/ToT/CoT 전략 선택이 입력 복잡도에 맞는가"},
        {"name": "agent_call_judgment", "description": "Memory/Knowledge 호출 필요성 판단이 적절한가"},
        {"name": "multi_perspective", "description": "하나의 해석에 고착되지 않고 복수 관점을 탐색하는가"},
        {"name": "actionable_insight", "description": "추론 결과가 스크립트 생성에 실질적으로 활용 가능한가"},
    ],
    "script_generator": [
        {"name": "script_structure", "description": "인트로/본문/클로징 등 구조가 갖춰져 있는가"},
        {"name": "narrative_flow", "description": "대본이 자연스럽게 읽히고 흐름이 매끄러운가"},
        {"name": "tier1_reflection", "description": "Safety/Emotion/Content/Reasoning 결과가 스크립트에 반영되는가"},
        {"name": "safety_warning_integration", "description": "Safety warning이 스크립트에 적절히 포함되는가"},
        {"name": "listener_engagement", "description": "팟캐스트로서 듣고 싶은 매력이 있는가"},
        {"name": "length_appropriateness", "description": "너무 짧거나 장황하지 않은 적정 분량인가"},
    ],
    "batch_validator": [
        {"name": "bv_score", "description": "산출된 품질 점수 (기존 핵심 지표)"},
        {"name": "validation_precision", "description": "실제 문제를 정확히 짚어내는가"},
        {"name": "feedback_specificity", "description": "부족함 수준이 아닌 구체적 개선점을 제시하는가"},
        {"name": "feedback_actionability", "description": "제시된 피드백으로 실제 개선이 가능한가"},
        {"name": "scoring_consistency", "description": "동일 품질의 입력에 대해 유사한 점수를 부여하는가"},
        {"name": "strictness_balance", "description": "너무 관대하거나 가혹하지 않은 적정 수준인가"},
    ],
    "script_personalizer": [
        {"name": "tone_appropriateness", "description": "사용자 감정 상태에 맞는 톤으로 조정되었는가"},
        {"name": "personalization_level", "description": "일반적 응답이 아닌 사용자 맥락이 반영된 조정인가"},
        {"name": "safety_tone_enforcement", "description": "warning 시 톤이 적절히 강화되었는가"},
        {"name": "original_preservation", "description": "개인화 과정에서 핵심 내용이 손실되지 않았는가"},
        {"name": "empathy_expression", "description": "사용자 상황에 대한 공감이 자연스럽게 드러나는가"},
        {"name": "consistent_persona", "description": "전체 스크립트에서 일관된 화자 톤이 유지되는가"},
    ],
    "visualization": [
        {"name": "visual_metadata_quality", "description": "색상/구도/분위기 등 메타데이터가 풍부한가"},
        {"name": "image_prompt_quality", "description": "생성된 프롬프트가 감정 상태를 잘 표현하는가"},
        {"name": "emotion_visual_mapping", "description": "감정 벡터와 시각적 표현이 일치하는가"},
        {"name": "creativity", "description": "진부하지 않은 독창적 시각 표현을 제안하는가"},
        {"name": "feasibility", "description": "이미지 생성 모델이 실제로 렌더링 가능한 프롬프트인가"},
    ],
    "learning": [
        {"name": "insight_usefulness", "description": "추출된 학습 인사이트가 향후 대화에 활용 가능한가"},
        {"name": "pattern_extraction", "description": "사용자 행동/감정 패턴을 정확히 식별하는가"},
        {"name": "overfitting_prevention", "description": "단일 대화에서 과도한 일반화를 하지 않는가"},
        {"name": "privacy_respect", "description": "민감 정보를 부적절하게 기록하지 않는가"},
        {"name": "data_structuring", "description": "학습 결과가 잘 구조화되어 검색 가능한가"},
    ],
}

# 에이전트 이름 → AgentState 출력 필드 매핑
AGENT_OUTPUT_FIELDS: dict[str, list[str]] = {
    "intent_classifier": ["intent", "risk_level", "risk_score", "safety_flags"],
    "safety": ["safety_flags", "risk_level", "risk_score"],
    "emotion": ["emotion_vectors"],
    "content_analyzer": ["content_analysis"],
    "podcast_reasoning": ["reasoning_result", "memory_results", "knowledge_results"],
    "script_generator": ["script_draft"],
    "batch_validator": ["validation_result"],
    "script_personalizer": ["final_output"],
    "visualization": ["visual_data"],
    "learning": [],
}

# 테스트 대상 Bedrock 모델 목록
BEDROCK_MODELS: list[dict[str, str]] = [
    {"short": "c3-sonnet", "model_id": "apac.anthropic.claude-3-sonnet-20240229-v1:0"},
    {"short": "c3-haiku", "model_id": "anthropic.claude-3-haiku-20240307-v1:0"},
    {"short": "c35-sonnet-v1", "model_id": "apac.anthropic.claude-3-5-sonnet-20240620-v1:0"},
    {"short": "c35-sonnet-v2", "model_id": "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"},
    {"short": "c37-sonnet", "model_id": "apac.anthropic.claude-3-7-sonnet-20250219-v1:0"},
]

# 이미지 생성 모델 (Visualization 전용)
IMAGE_MODELS: list[dict[str, str]] = [
    {"short": "titan-v2", "model_id": "amazon.titan-image-generator-v2:0"},
    {"short": "titan-v1", "model_id": "amazon.titan-image-generator-v1"},
    {"short": "nova-canvas", "model_id": "amazon.nova-canvas-v1:0"},
]

# 에이전트별 기본 모델 키 (settings.yaml 기준)
AGENT_DEFAULT_MODEL: dict[str, str] = {
    "intent_classifier": "haiku",
    "safety": "sonnet",
    "emotion": "sonnet",
    "content_analyzer": "sonnet",
    "podcast_reasoning": "sonnet",
    "script_generator": "sonnet",
    "batch_validator": "sonnet",
    "script_personalizer": "sonnet",
    "visualization": "sonnet",
    "learning": "haiku",
}

# Evaluator Agent 고정 모델
EVALUATOR_MODEL_ID = "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"

# 종합점수 기본 가중치
DEFAULT_WEIGHTS: dict[str, float] = {
    "quality": 0.35,
    "consistency": 0.25,
    "speed": 0.15,
    "cost_efficiency": 0.10,
    "reliability": 0.15,
}

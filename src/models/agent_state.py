"""
AgentState — LangGraph StateGraph 공유 상태 스키마.

[Protected File] 수정 시 3인 합의 필수.

모든 에이전트는 이 상태를 읽고 쓴다.
각 에이전트는 자기 담당 필드만 쓰고, 다른 에이전트 필드는 읽기만 한다.
total=False 설정으로 모든 필드는 선택적이며, 에이전트 노드는
업데이트할 필드만 포함한 dict를 반환한다 (LangGraph가 자동 merge).
"""

from __future__ import annotations

from typing import Any, Literal

from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    LangGraph StateGraph에서 모든 에이전트가 공유하는 상태.

    필드 소유권:
        - 입력 필드: Intent Classifier가 설정
        - 분석 필드: Intent Classifier, Emotion Agent, Context/Content Analyzer
        - 추론/생성 필드: Reasoning, Memory, Knowledge, Synthesis/Script Generator
        - 검증/부가 필드: Safety, Validator, Personalization, Visualization
        - 제어 필드: 워크플로우 라우팅용
    """

    # === 입력 (Intent Classifier가 설정) ===
    user_input: str  # 사용자 원본 입력
    structured_input: dict[str, Any]  # 프론트엔드로부터 전달받는 4가지 입력 필드
    user_id: str  # 사용자 고유 ID
    session_id: str  # 세션 고유 ID
    mode: Literal["podcast"]  # 실행 모드
    learning_pattern: dict[str, Any] | None  # 백엔드 Push 사용자 학습 패턴 (nullable)

    # === 분석 필드 ===
    intent: dict[str, Any]  # Intent Classifier → 의도 분류 결과
    emotion_vectors: dict[str, Any]  # Emotion Agent → 감정 벡터
    content_analysis: dict[str, Any]  # Content Analyzer → 주제 분석

    # === 추론/생성 필드 ===
    memory_results: dict[str, Any]  # Episode Memory → 기억 검색 결과
    knowledge_results: dict[str, Any]  # Knowledge Agent → 전문 지식 검색 결과
    reasoning_result: dict[str, Any]  # Podcast Reasoning → 추론 결과
    script_draft: dict[str, Any]  # Script Generator → 스크립트

    # === 검증/부가 필드 ===
    risk_level: int  # Safety Agent → 위험 레벨 (0-4)
    risk_score: float  # Safety Agent → 위험 점수 (0.0-1.0)
    safety_flags: dict[str, Any]  # Safety Agent → 안전 플래그 및 상태
    validation_result: dict[str, Any]  # Batch Validator → 검증 결과
    final_output: str  # Script Personalizer → 최종 응답
    visual_data: dict[str, Any]  # Visualization Agent → 시각화 메타데이터
    stories_context: dict[str, Any] | None  # Stories 선택 데이터 (keywords, title, description)

    # === 메모리 저장 트리거 (Script Personalizer → async_post) ===
    memory_write: bool  # True이면 async_post에서 에피소드 메모리 저장 실행
    memory_text: str  # 저장할 에피소드 텍스트 (segments 연결)
    memory_metadata: dict[str, Any]  # 저장 메타데이터 (user_id, session_id, episode_id)

    # === 제어 필드 ===
    next_step: str  # 워크플로우 라우팅 플래그
    execution_plan: dict[str, Any]  # Intent Classifier가 결정한 실행 계획
    iteration_count: int  # 피드백 루프 카운터 (최대 2회 재시도)

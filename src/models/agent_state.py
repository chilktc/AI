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
    user_id: str  # 사용자 고유 ID
    session_id: str  # 세션 고유 ID
    mode: Literal["conversation", "podcast"]  # 실행 모드

    # === 분석 필드 ===
    intent: dict[str, Any]  # Intent Classifier → 의도 분류 결과
    emotion_vectors: dict[str, Any]  # Emotion Agent → 감정 벡터
    context: dict[str, Any]  # Context Agent → 대화 맥락 (대화모드)
    content_analysis: dict[str, Any]  # Content Analyzer → 팟캐스트 주제 분석

    # === 추론/생성 필드 ===
    memory_results: dict[str, Any]  # Memory/Episode Memory → 기억 검색 결과
    knowledge_results: dict[str, Any]  # Knowledge Agent → 전문 지식 검색 결과
    reasoning_result: dict[str, Any]  # Reasoning/Podcast Reasoning → 추론 결과
    # TODO: Synthesis Agent 구현 후 활성화 (대화모드 TIER 2 — 현재 미사용)
    response_draft: str  # Synthesis Agent → 응답 초안 (대화모드)
    script_draft: dict[str, Any]  # Script Generator → 팟캐스트 스크립트

    # === 검증/부가 필드 ===
    risk_level: int  # Safety Agent → 위험 레벨 (0-4)
    risk_score: float  # Safety Agent → 위험 점수 (0.0-1.0)
    safety_flags: dict[str, Any]  # Safety Agent → 안전 플래그 및 상태
    validation_result: dict[str, Any]  # Validator/Batch Validator → 검증 결과
    final_output: str  # Personalization/Script Personalizer → 최종 응답
    visual_data: dict[str, Any]  # Visualization Agent → 시각화 메타데이터

    # === 제어 필드 ===
    next_step: str  # 워크플로우 라우팅 플래그
    execution_plan: dict[str, Any]  # Intent Classifier가 결정한 실행 계획
    iteration_count: int  # 피드백 루프 카운터 (최대 2회 재시도)

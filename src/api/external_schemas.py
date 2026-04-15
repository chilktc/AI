"""
외부 입출력 데이터 스키마 정의.

Mind-Log AI 멘탈케어 플랫폼의 모든 외부 인터페이스 스키마를 정의한다.
Backend 서버 ↔ AI 파이프라인 ↔ 백엔드 DB 간 데이터 흐름의 단일 진실 원천(SSOT).

구조:
    1. 공용 기반 스키마 (추적, 페이징, 에러)
    2. 외부 입력 스키마 (Backend 서버 → AI 파이프라인)
    3. 외부 출력 스키마 (AI 파이프라인 → Backend 서버)
    4. 내부 저장 스키마 (DB별 저장 데이터)
    5. 중복 방지 전략 및 DB별 책임 분담

참조:
    - src/api/contracts.py — 기존 API 요청/응답 (범용 Save/Load)
    - src/models/agent_state.py — LangGraph 공유 상태
    - src/models/message.py — 에이전트 간 메시지 프로토콜 v2.0
    - src/models/schemas.py — 에이전트 전용 데이터 구조
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════
# 1. 공용 기반 스키마 — 추적, 페이징, 에러
# ═══════════════════════════════════════════════════════════════════════════


def _generate_request_id() -> str:
    """API 요청 고유 ID 생성. 클라이언트(Backend 서버)에서 전달하지 않으면 서버가 자동 생성."""
    return f"req_{uuid.uuid4().hex[:12]}"


def _generate_trace_id() -> str:
    """분산 추적 ID 생성. 요청 → 파이프라인 → DB 저장까지 전체 흐름을 연결한다."""
    return f"trace_{uuid.uuid4().hex[:12]}"


def _generate_correlation_id() -> str:
    """상관관계 ID 생성. 하나의 사용자 행동에서 파생된 모든 처리를 묶는다."""
    return f"corr_{uuid.uuid4().hex[:12]}"


def _now_utc() -> datetime:
    """현재 UTC 시각 반환."""
    return datetime.now(timezone.utc)


class RequestTracing(BaseModel):
    """
    요청 추적 컨텍스트 — 모든 API 요청에 포함.

    추적 체계:
        request_id:     개별 API 요청 식별 (1:1 매핑)
        trace_id:       분산 추적 — 요청 → TIER 0~4 → DB 저장 전체 연결
        correlation_id: 사용자 행동 단위 — 대화 턴 또는 에피소드 생성 전체를 묶음
    """

    request_id: str = Field(
        default_factory=_generate_request_id,
        description="API 요청 고유 ID. 클라이언트(Backend 서버)에서 전달하거나 서버가 자동 생성",
    )
    trace_id: str = Field(
        default_factory=_generate_trace_id,
        description="분산 추적 ID. 파이프라인 전체 흐름을 연결",
    )
    correlation_id: str = Field(
        default_factory=_generate_correlation_id,
        description="상관관계 ID. 하나의 사용자 행동에서 파생된 처리를 묶음",
    )
    timestamp: datetime = Field(
        default_factory=_now_utc,
        description="요청 생성 시각 (UTC)",
    )


class PaginationParams(BaseModel):
    """페이지네이션 요청 파라미터."""

    page: int = Field(default=1, ge=1, description="요청 페이지 번호 (1부터 시작)")
    page_size: int = Field(default=20, ge=1, le=100, description="페이지당 항목 수")


class PaginationMeta(BaseModel):
    """페이지네이션 응답 메타데이터."""

    page: int = Field(description="현재 페이지 번호")
    page_size: int = Field(description="페이지당 항목 수")
    total_items: int = Field(description="전체 항목 수")
    total_pages: int = Field(description="전체 페이지 수")
    has_next: bool = Field(description="다음 페이지 존재 여부")
    has_prev: bool = Field(description="이전 페이지 존재 여부")


class ErrorDetail(BaseModel):
    """에러 상세 정보."""

    code: str = Field(
        description=(
            "에러 코드. "
            "NOT_FOUND | VALIDATION_ERROR | SERVER_ERROR | "
            "RATE_LIMITED | PIPELINE_TIMEOUT | CRISIS_ESCALATION"
        ),
    )
    message: str = Field(description="사람이 읽을 수 있는 에러 메시지")
    field: str | None = Field(default=None, description="에러가 발생한 필드명 (검증 에러 시)")
    trace_id: str | None = Field(default=None, description="추적 ID (디버깅용)")


class ErrorResponse(BaseModel):
    """에러 응답 — 모든 실패 응답의 공통 래퍼."""

    success: Literal[False] = False
    error: ErrorDetail
    tracing: RequestTracing | None = Field(default=None, description="추적 컨텍스트 (디버깅용)")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 외부 입력 스키마 — Backend 서버 → AI 파이프라인
# ═══════════════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────
# 2-1. 세션 관리
# ───────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    """
    세션 생성 요청.

    Backend 서버가 대화 시작 시 호출한다.
    세션 ID는 서버에서 생성하여 반환한다.

    Endpoint: POST /api/sessions
    """

    user_id: str = Field(description="사용자 고유 ID")
    mode: Literal["podcast"] = Field(
        default="podcast",
        description="실행 모드 (팟캐스트 에피소드 생성)",
    )
    device_info: dict[str, str] | None = Field(
        default=None,
        description="클라이언트 디바이스 정보 (OS, 앱 버전 등). 분석용",
    )
    tracing: RequestTracing = Field(
        default_factory=RequestTracing,
        description="추적 컨텍스트",
    )


class SessionCreateResponse(BaseModel):
    """세션 생성 응답."""

    success: Literal[True] = True
    session_id: str = Field(description="생성된 세션 고유 ID")
    mode: Literal["podcast"] = Field(description="세션 모드")
    created_at: datetime = Field(description="세션 생성 시각")
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class SessionCloseRequest(BaseModel):
    """
    세션 종료 요청.

    Backend 서버가 대화 종료 시 호출한다.
    서버는 Learning Agent를 비동기로 트리거한다.

    Endpoint: POST /api/sessions/{session_id}/close
    """

    user_id: str = Field(description="사용자 고유 ID")
    session_id: str = Field(description="종료할 세션 ID")
    feedback: SessionFeedback | None = Field(
        default=None,
        description="사용자 피드백 (선택)",
    )
    tracing: RequestTracing = Field(
        default_factory=RequestTracing,
        description="추적 컨텍스트",
    )


class SessionFeedback(BaseModel):
    """세션 종료 시 사용자 피드백."""

    rating: int | None = Field(default=None, ge=1, le=5, description="만족도 (1-5)")
    helpful: bool | None = Field(default=None, description="도움이 되었는지 여부")
    comment: str | None = Field(
        default=None, max_length=500, description="자유 피드백 (최대 500자)"
    )


# ───────────────────────────────────────────────
# 2-2. 팟캐스트 생성 요청 (PodcastRequest)
# ───────────────────────────────────────────────


class PodcastRequest(BaseModel):
    """
    팟캐스트 에피소드 생성 요청.

    프론트엔드가 사용자의 상황·생각·행동·동료반응을 구조화하여 전달한다.
    서버는 이 요청을 팟캐스트 모드 LangGraph 파이프라인에 전달한다.

    Endpoint: POST /api/podcasts/episodes
    파이프라인: TIER 0 → TIER 1(병렬) → TIER 2(병렬) → TIER 3 → TIER 4

    AgentState 매핑:
        user_input       ← situation + thought + action + (colleagueReaction or "")
                           (줄바꿈 구분 문자열로 조합)
        user_id          ← user_id
        session_id       ← session_id
        mode             ← "podcast" (고정)
        learning_pattern ← learning_pattern (nullable, Intent Classifier 활용)
    """

    model_config = {"populate_by_name": True}

    user_id: str = Field(description="사용자 고유 ID")
    session_id: str = Field(description="세션 고유 ID")
    situation: str = Field(
        min_length=2,
        max_length=500,
        description="사용자가 처한 상황 (2~500자)",
    )
    thought: str = Field(
        min_length=2,
        max_length=500,
        description="상황에 대한 자신의 생각 (2~500자)",
    )
    action: str = Field(
        min_length=2,
        max_length=500,
        description="자신의 행동 및 반응 (2~500자)",
    )
    colleague_reaction: str | None = Field(
        default=None,
        max_length=500,
        alias="colleagueReaction",
        description="동료의 반응 (선택, 최대 500자)",
    )
    learning_pattern: dict[str, Any] | None = Field(
        default=None,
        description="백엔드가 Push하는 사용자 학습 패턴 (nullable, 신규 사용자는 null)",
    )
    tracing: RequestTracing = Field(
        default_factory=RequestTracing,
        description="추적 컨텍스트",
    )


class PodcastPreferences(BaseModel):
    """팟캐스트 에피소드 생성 선호 설정."""

    target_duration_minutes: int = Field(
        default=5,
        ge=3,
        le=5,
        description="목표 에피소드 길이 (분). 시스템 제한: 3~5분",
    )
    tone: Literal["warm", "professional", "casual", "motivational"] | None = Field(
        default=None,
        description="에피소드 톤 선호",
    )
    include_visualization: bool = Field(
        default=True,
        description="에피소드 커버 이미지 생성 여부",
    )


# ───────────────────────────────────────────────
# 2-4. 사용자 프로필 (UserProfile)
# ───────────────────────────────────────────────


class UserProfileUpdateRequest(BaseModel):
    """
    사용자 프로필 업데이트 요청.

    프론트엔드 설정 화면에서 사용자가 프로필을 수정할 때 사용한다.
    Personalization Agent와 Script Personalizer가 참조한다.

    Endpoint: PATCH /api/users/{user_id}/profile
    저장 위치: MySQL users 테이블
    """

    user_id: str = Field(description="사용자 고유 ID")
    display_name: str | None = Field(default=None, max_length=50, description="표시 이름")
    age_group: Literal["10s", "20s", "30s", "40s", "50s", "60s_plus"] | None = Field(
        default=None,
        description="연령대",
    )
    preferred_style: Literal["warm", "professional", "casual", "neutral"] | None = Field(
        default=None,
        description="선호 대화 스타일",
    )
    preferred_attitude: Literal["supportive", "analytical", "balanced", "motivational"] | None = (
        Field(
            default=None,
            description="선호 상담 태도",
        )
    )
    notification_enabled: bool | None = Field(
        default=None,
        description="알림 수신 동의 여부",
    )
    tracing: RequestTracing = Field(
        default_factory=RequestTracing,
        description="추적 컨텍스트",
    )


class UserProfileResponse(BaseModel):
    """사용자 프로필 조회 응답."""

    success: Literal[True] = True
    profile: UserProfileData = Field(description="사용자 프로필 데이터")
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class UserProfileData(BaseModel):
    """
    사용자 프로필 데이터 (MySQL SSOT).

    Personalization Agent와 Script Personalizer가 참조하는
    사용자 개인화 설정의 단일 진실 원천.
    """

    user_id: str = Field(description="사용자 고유 ID")
    display_name: str = Field(default="", description="표시 이름")
    age_group: str = Field(default="30s", description="연령대")
    preferred_style: str = Field(default="neutral", description="선호 대화 스타일")
    preferred_attitude: str = Field(default="balanced", description="선호 상담 태도")
    notification_enabled: bool = Field(default=True, description="알림 수신 동의")
    created_at: datetime = Field(description="계정 생성 시각")
    updated_at: datetime = Field(description="마지막 수정 시각")
    total_sessions: int = Field(default=0, description="총 세션 수")
    total_episodes: int = Field(default=0, description="총 팟캐스트 에피소드 수")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 외부 출력 스키마 — AI 파이프라인 → Backend 서버
# ═══════════════════════════════════════════════════════════════════════════


class EmotionSummary(BaseModel):
    """
    감정 분석 요약 — 프론트엔드 UI 렌더링용.

    Emotion Agent(emotion_vectors)의 전체 결과가 아닌,
    프론트엔드가 필요로 하는 필드만 추출한 요약 버전.

    원본 출처: AgentState.emotion_vectors (Emotion Agent)

    Note:
        - arousal(각성도)는 Emotion Agent가 출력하지만 프론트엔드에서 미사용이므로
          이 요약 스키마에 포함하지 않는다. DB 저장 시에는 emotion_vectors 원본에서
          직접 추출하여 저장한다 (podcasts.py _save_episode_bundle 참조).
        - emotional_journey_hint도 Emotion Agent 전용 필드로 API에 미노출.
    """

    primary_emotion: str = Field(
        description="주요 감정 (영문 키: sadness, anxiety, joy 등)",
    )
    primary_emotion_kr: str = Field(
        description="주요 감정 한국어 (UI 표시용: 슬픔, 불안, 기쁨 등)",
    )
    intensity: float = Field(ge=0.0, le=1.0, description="감정 강도 (0.0=매우 약함, 1.0=매우 강함)")
    valence: float = Field(ge=-1.0, le=1.0, description="감정 가치 (-1.0=부정, 0=중립, 1.0=긍정)")
    secondary_emotions: list[str] = Field(
        default_factory=list, description="부수 감정 목록 (영문 키)"
    )
    tone_recommendation: str = Field(
        default="supportive_neutral",
        description="추천 톤 (Personalization Agent가 참고한 톤)",
    )


class SafetyAlertData(BaseModel):
    """
    안전 경고 데이터 — 프론트엔드 안전 UI 렌더링용.

    Safety Agent가 "warning" 또는 "crisis" 판정 시에만 생성.
    프론트엔드는 status에 따라 다른 UI를 렌더링한다.

    원본 출처: AgentState.safety_flags (Safety Agent)
    """

    status: Literal["warning", "crisis"] = Field(
        description="안전 상태. warning=경고 배너, crisis=즉시 도움 연결",
    )
    alert_message: str = Field(
        description="프론트엔드에 표시할 안전 안내 메시지 (한국어)",
    )
    helpline_info: list[HelplineInfo] | None = Field(
        default=None,
        description="도움 연결 정보 (crisis 시 필수 포함)",
    )
    show_emergency_button: bool = Field(
        default=False,
        description="긴급 도움 버튼 표시 여부 (crisis 시 True)",
    )


class HelplineInfo(BaseModel):
    """도움 연결 정보 (위기 상황 시)."""

    name: str = Field(description="기관명 (예: '자살예방상담전화')")
    phone: str = Field(description="전화번호 (예: '1393')")
    description: str = Field(description="설명 (예: '24시간 운영')")


class VisualizationData(BaseModel):
    """
    시각화 데이터 — Visualization Agent 출력과 1:1 매핑.

    Visualization Agent가 생성한 추상화 이미지의 메타데이터.
    이미지 URL은 S3 CDN 경로이며, 비동기 생성이므로 초기 응답에는 null일 수 있다.

    원본 출처: AgentState.visual_data (Visualization Agent)

    Note:
        - Agent 출력의 `local_path`는 내부 전용이므로 API에 미노출.
        - `style_info` nested 구조 대신 Agent 출력 그대로 flat 구조를 사용한다.
    """

    image_url: str | None = Field(
        default=None,
        description="이미지 URL (S3 CDN). 비동기 생성 중이면 null",
    )
    interpretation: str = Field(
        default="",
        description="카드 터치 시 표시할 해설 텍스트 (한국어, 1-2문장)",
    )
    style_type: str = Field(
        default="",
        description="시각화 스타일 유형 (예: 'soft_blurred', 'hard_sharp')",
    )
    original_prompt: str = Field(
        default="",
        description="이미지 생성에 사용된 프롬프트 (영문)",
    )
    resolution: str = Field(
        default="1024x1024",
        description="이미지 해상도",
    )
    status: str = Field(
        default="completed",
        description="생성 상태 ('completed', 'skipped')",
    )


# ───────────────────────────────────────────────
# 3-2. 팟캐스트 에피소드 응답 (PodcastEpisodeResponse)
# ───────────────────────────────────────────────


class PodcastEpisodeResponse(BaseModel):
    """
    팟캐스트 에피소드 응답 — 생성된 에피소드 전체 데이터.

    LangGraph 팟캐스트 파이프라인 완료 후 프론트엔드에 반환.
    Script Personalizer(TIER 4)의 최종 스크립트를 핵심으로,
    에피소드 메타데이터와 시각화(커버 이미지)를 포함한다.

    Endpoint 응답: POST /api/podcasts/episodes

    AgentState 매핑:
        episode          ← script_draft + final_output (Script Personalizer)
        emotion          ← emotion_vectors (요약)
        safety_alert     ← safety_flags
        cover_image      ← visual_data
    """

    success: Literal[True] = True
    episode: PodcastEpisodeData = Field(description="에피소드 데이터")
    emotion: EmotionSummary | None = Field(
        default=None,
        description="감정 분석 요약",
    )
    safety_alert: SafetyAlertData | None = Field(
        default=None,
        description="안전 경고 (필요 시에만)",
    )
    cover_image: VisualizationData | None = Field(
        default=None,
        description="에피소드 커버 이미지 (비동기 생성이므로 null 가능)",
    )
    metadata: PodcastResponseMeta = Field(description="응답 메타데이터")
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class SlimPodcastResponse(BaseModel):
    """
    팟캐스트 에피소드 생성 완료 응답 (슬림).

    파이프라인 실행 + DB 저장 완료 후 반환하는 최소 응답.
    모든 데이터는 DB에 저장되므로 Backend가 GET API로 조회 가능.
    safety_alert만 직접 포함 (CRISIS 시 에피소드 미생성 → DB 미저장).

    Endpoint 응답: POST /api/podcasts/episodes
    """

    success: Literal[True] = True
    episode_id: str = Field(description="생성된 에피소드 고유 ID")
    session_id: str = Field(description="세션 ID")
    safety_alert: SafetyAlertData | None = Field(
        default=None,
        description="안전 경고 (CRISIS 시 에피소드 미생성, 응답에 직접 포함)",
    )
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class PodcastEpisodeData(BaseModel):
    """
    팟캐스트 에피소드 데이터.

    프론트엔드는 이 데이터로 에피소드 플레이어를 렌더링한다.
    """

    episode_id: str = Field(description="에피소드 고유 ID")
    session_id: str = Field(description="생성 세션 ID")
    episode_title: str = Field(description="에피소드 제목 (한국어)")
    total_duration: int = Field(description="총 에피소드 길이 (분)")
    script_text: str = Field(description="전체 스크립트 텍스트 (TTS 입력)")
    tts_markers: list[TTSMarkerData] = Field(default_factory=list, description="전체 TTS 제어 마커")
    key_insights: list[str] = Field(default_factory=list, description="핵심 인사이트 (3-5개)")
    themes: list[str] = Field(default_factory=list, description="에피소드 주제 태그")
    created_at: datetime = Field(default_factory=_now_utc, description="에피소드 생성 시각")


class TTSMarkerData(BaseModel):
    """TTS 마커 — 스크립트 특정 위치의 음성 제어 지시."""

    position: int = Field(description="스크립트 텍스트 내 위치 (문자 인덱스)")
    instruction: str = Field(description="TTS 지시사항 (예: 'slow_down', 'pause_1s')")


class PodcastResponseMeta(BaseModel):
    """팟캐스트 응답 메타데이터."""

    mode: Literal["podcast"] = "podcast"
    pipeline_duration_ms: int = Field(description="파이프라인 전체 소요 시간 (밀리초)")
    intent_type: str = Field(description="분류된 의도 타입")
    complexity_score: float = Field(description="입력 복잡도 점수")
    reasoning_depth: str = Field(description="추론 깊이 (full / standard / minimal)")
    retry_count: int = Field(default=0, description="TIER 2→3 재시도 횟수")
    total_words: int = Field(default=0, description="전체 스크립트 단어 수")


# ───────────────────────────────────────────────
# 3-3. 감정 분석 히스토리 응답 (EmotionHistoryResponse)
# ───────────────────────────────────────────────


class EmotionHistoryResponse(BaseModel):
    """
    감정 분석 히스토리 조회 응답.

    사용자의 과거 감정 로그를 시간순으로 반환한다.
    프론트엔드의 감정 추이 그래프, 감정 달력 등에 사용.

    Endpoint 응답: GET /api/users/{user_id}/emotions
    """

    success: Literal[True] = True
    emotions: list[EmotionLogEntry] = Field(description="감정 로그 목록")
    pagination: PaginationMeta = Field(description="페이지네이션 정보")
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class EmotionLogEntry(BaseModel):
    """
    감정 로그 항목 — 개별 대화 턴/에피소드의 감정 기록.

    원본 출처: MySQL emotion_logs 테이블
    """

    log_id: str = Field(description="감정 로그 고유 ID")
    session_id: str = Field(description="소속 세션 ID")
    mode: Literal["podcast"] = Field(description="모드")
    primary_emotion: str = Field(description="주요 감정 (영문 키)")
    intensity: float = Field(description="감정 강도 (0.0-1.0)")
    valence: float = Field(description="감정 가치 (-1.0~1.0)")
    arousal: float = Field(description="각성도 (0.0-1.0)")
    secondary_emotions: list[str] = Field(default_factory=list, description="부수 감정")
    created_at: datetime = Field(description="기록 시각")


# ───────────────────────────────────────────────
# 3-4. 에피소드 목록 조회 응답
# ───────────────────────────────────────────────


class PodcastEpisodeListResponse(BaseModel):
    """
    팟캐스트 에피소드 목록 조회 응답.

    Endpoint 응답: GET /api/users/{user_id}/podcasts/episodes
    """

    success: Literal[True] = True
    episodes: list[PodcastEpisodeSummary] = Field(description="에피소드 요약 목록")
    pagination: PaginationMeta = Field(description="페이지네이션 정보")
    tracing: RequestTracing = Field(description="추적 컨텍스트")


class PodcastEpisodeSummary(BaseModel):
    """에피소드 요약 — 목록 표시용 경량 데이터."""

    episode_id: str = Field(description="에피소드 ID")
    episode_title: str = Field(description="에피소드 제목")
    total_duration: int = Field(description="길이 (분)")
    themes: list[str] = Field(default_factory=list, description="주제 태그")
    primary_emotion: str | None = Field(default=None, description="주요 감정")
    cover_image_url: str | None = Field(default=None, description="커버 이미지 URL")
    created_at: datetime = Field(description="생성 시각")


# ───────────────────────────────────────────────
# 3-5. 스트리밍 이벤트 스키마 (SSE/WebSocket)
# ───────────────────────────────────────────────


class StreamEventType(str, Enum):
    """스트리밍 이벤트 유형."""

    TIER_START = "tier_start"  # TIER 실행 시작
    AGENT_COMPLETE = "agent_complete"  # 개별 에이전트 완료
    TIER_END = "tier_end"  # TIER 실행 완료
    CRISIS_DETECTED = "crisis_detected"  # CRISIS 감지
    PARTIAL_RESPONSE = "partial_response"  # 부분 응답 (스트리밍)
    FINAL_RESPONSE = "final_response"  # 최종 응답
    ERROR = "error"  # 에러 발생


class StreamEvent(BaseModel):
    """
    스트리밍 이벤트 — SSE 또는 WebSocket으로 프론트엔드에 실시간 전달.

    LangGraph의 get_stream_writer()가 발행하는 이벤트를
    프론트엔드 소비 가능한 형태로 정규화한 것.

    사용법:
        SSE: POST /api/podcasts/episodes/stream (Content-Type: application/json)
    """

    event_type: StreamEventType = Field(description="이벤트 유형")
    session_id: str = Field(description="세션 ID")
    tier: int | None = Field(default=None, description="현재 TIER (0-4)")
    agent: str | None = Field(default=None, description="에이전트 이름 (해당 시)")
    data: dict[str, Any] = Field(default_factory=dict, description="이벤트 페이로드")
    elapsed_ms: int = Field(default=0, description="TIER 시작 이후 경과 시간")
    timestamp: datetime = Field(default_factory=_now_utc, description="이벤트 발생 시각")
    trace_id: str = Field(description="추적 ID")


# ═══════════════════════════════════════════════════════════════════════════
# 4. 내부 저장 스키마 — DB별 저장 데이터
# ═══════════════════════════════════════════════════════════════════════════
#
# 중복 방지 전략 (Single Source of Truth):
#
# ┌────────────────────────────────────────────────────────────────────────┐
# │ DB           │ SSOT 역할                  │ 저장 데이터               │
# ├──────────────┼────────────────────────────┼───────────────────────────┤
# │ MySQL        │ 구조화된 트랜잭션 데이터   │ 사용자, 세션, 대화 이력,  │
# │              │ (관계형 정규화)             │ 감정 로그, 에피소드 메타, │
# │              │                            │ 학습 패턴                 │
# ├──────────────┼────────────────────────────┼───────────────────────────┤
# │ Pinecone     │ 의미론적 검색용 벡터       │ 대화 임베딩, 에피소드 임베│
# │              │ (원본은 MySQL에 보관)       │ 딩, 지식 문서 임베딩      │
# │              │                            │ ※ 원본 ID로 MySQL 참조   │
# ├──────────────┼────────────────────────────┼───────────────────────────┤
# │ Neo4j        │ 관계/그래프 분석           │ 감정 패턴 관계, 주제 연결,│
# │              │ (관계만 저장, 원본은 MySQL) │ 사용자-에피소드 관계,     │
# │              │                            │ GoT 추론 그래프           │
# ├──────────────┼────────────────────────────┼───────────────────────────┤
# │ S3 / CDN     │ 바이너리 에셋              │ 시각화 이미지, 커버 이미지│
# │              │ (메타데이터는 MySQL)        │ TTS 오디오 파일           │
# └──────────────┴────────────────────────────┴───────────────────────────┘
#
# 참조 ID 규칙:
#   - MySQL이 모든 엔티티의 원본 ID(PK)를 소유한다.
#   - Pinecone은 벡터 ID로 "vec_{mysql_pk}" 형식을 사용한다.
#   - Neo4j 노드는 mysql_id 속성으로 MySQL PK를 참조한다.
#   - S3 객체 키는 "vis/{mode}/{session_id}/{entity_id}.png" 형식이다.
#
# ═══════════════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────
# 4-1. MySQL 저장 스키마 (SaveRequest.data 구조)
# ───────────────────────────────────────────────
# 기존 contracts.py의 SaveRequest는 type + data(dict) 구조.
# 아래는 type별 data 필드의 구체적 스키마를 정의한다.
# ───────────────────────────────────────────────


class MySQLEmotionLog(BaseModel):
    """
    MySQL 저장 — 감정 로그 데이터.

    SaveRequest(type="emotion_log")의 data 필드 구조.
    테이블: emotion_logs

    Emotion Agent의 분석 결과를 정규화하여 저장.
    프론트엔드 감정 추이 그래프의 데이터 소스.

    인덱스:
        - PK: log_id
        - FK: session_id → sessions.session_id
        - FK: user_id → users.user_id
        - FK: episode_id → podcast_episodes.episode_id (팟캐스트모드)
        - INDEX: (user_id, created_at) — 감정 추이 조회
        - INDEX: (primary_emotion) — 감정별 필터링
    """

    log_id: str = Field(description="감정 로그 고유 ID (PK)")
    session_id: str = Field(description="세션 ID (FK)")
    user_id: str = Field(description="사용자 ID (FK)")
    mode: Literal["podcast"] = Field(description="모드")
    # 원본 컨텍스트 참조
    episode_id: str | None = Field(default=None, description="에피소드 ID (팟캐스트)")
    # Emotion Agent 분석 결과 (정규화)
    primary_emotion: str = Field(description="주요 감정 (영문 키)")
    intensity: float = Field(description="감정 강도 (0.0-1.0)")
    valence: float = Field(description="감정 가치 (-1.0~1.0)")
    arousal: float = Field(description="각성도 (0.0-1.0)")
    secondary_emotions: list[str] = Field(default_factory=list, description="부수 감정 목록")
    tone_recommendation: str = Field(description="추천 톤")
    # 추적
    trace_id: str = Field(description="분산 추적 ID")
    created_at: datetime = Field(default_factory=_now_utc, description="생성 시각")


class MySQLPodcastEpisode(BaseModel):
    """
    MySQL 저장 — 팟캐스트 에피소드 메타데이터.

    SaveRequest(type="podcast_episode")의 data 필드 구조.
    테이블: podcast_episodes

    스크립트 본문(script_text)은 별도 테이블에 세그먼트 단위로 저장.
    이 테이블에는 메타데이터만 보관한다.

    인덱스:
        - PK: episode_id
        - FK: session_id → sessions.session_id
        - FK: user_id → users.user_id
        - INDEX: (user_id, created_at) — 사용자별 에피소드 목록
    """

    episode_id: str = Field(description="에피소드 고유 ID (PK)")
    session_id: str = Field(description="세션 ID (FK)")
    user_id: str = Field(description="사용자 ID (FK)")
    episode_title: str = Field(description="에피소드 제목")
    total_duration: int = Field(description="총 길이 (분)")
    total_words: int = Field(default=0, description="전체 단어 수")
    script_text: str = Field(description="전체 스크립트 텍스트")
    tts_markers_json: str = Field(default="[]", description="TTS 마커 JSON 문자열")
    key_insights: list[str] = Field(default_factory=list, description="핵심 인사이트")
    themes: list[str] = Field(default_factory=list, description="주제 태그")
    reasoning_depth: str = Field(
        default="standard", description="추론 깊이 (full/standard/minimal)"
    )
    cover_image_url: str | None = Field(default=None, description="커버 이미지 S3 URL")
    # 파이프라인 메타
    intent_type: str = Field(default="unknown", description="의도 분류 타입")
    complexity_score: float = Field(default=0.0, description="입력 복잡도 (0.0-1.0)")
    safety_status: str = Field(default="safe", description="안전 상태 (safe/warning/crisis)")
    validation_score: float = Field(default=0.0, description="검증 점수")
    retry_count: int = Field(default=0, description="TIER 2→3 재시도 횟수")
    pipeline_duration_ms: int = Field(default=0, description="파이프라인 소요 시간 (ms)")
    # 추적
    trace_id: str = Field(description="분산 추적 ID")
    correlation_id: str = Field(description="상관관계 ID")
    created_at: datetime = Field(default_factory=_now_utc, description="생성 시각")


class MySQLLearningPattern(BaseModel):
    """
    MySQL 저장 — 학습 패턴 데이터.

    SaveRequest(type="learning")의 data 필드 구조.
    테이블: learning_patterns

    Learning Agent가 세션 종료 후 비동기로 생성하는 사용자 패턴 분석 결과.

    인덱스:
        - PK: pattern_id
        - FK: session_id → sessions.session_id
        - FK: user_id → users.user_id
        - INDEX: (user_id, created_at) — 패턴 추이 조회
    """

    pattern_id: str = Field(description="패턴 고유 ID (PK)")
    session_id: str = Field(description="세션 ID (FK)")
    user_id: str = Field(description="사용자 ID (FK)")
    mode: Literal["podcast"] = Field(description="모드")
    # Learning Agent LLM 분석 결과
    preferred_topics: list[str] = Field(default_factory=list, description="선호 주제 패턴")
    emotional_patterns: list[str] = Field(
        default_factory=list, description="감정 패턴 (예: '주로 저녁에 불안 호소')"
    )
    interaction_style: str = Field(
        default="standard", description="상호작용 스타일 (짧은 대화 선호 등)"
    )
    personalization_suggestions: list[str] = Field(
        default_factory=list, description="개인화 제안 (다음 세션 참고용)"
    )
    effectiveness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="세션 효과성 점수 (0.0-1.0)",
    )
    raw_learning_data: dict[str, Any] = Field(
        default_factory=dict, description="LLM 원본 분석 결과 (디버깅용)"
    )
    # 추적
    trace_id: str = Field(description="분산 추적 ID")
    created_at: datetime = Field(default_factory=_now_utc, description="생성 시각")


class MySQLVisualizationMeta(BaseModel):
    """
    MySQL 저장 — 시각화 메타데이터.

    SaveRequest(type="visualization")의 data 필드 구조.
    테이블: visualization_meta

    이미지 바이너리는 S3에 저장하고, MySQL에는 메타데이터만 보관.

    인덱스:
        - PK: visualization_id
        - FK: session_id → sessions.session_id
        - FK: user_id → users.user_id
        - FK: episode_id — 원본 컨텍스트 참조
    """

    visualization_id: str = Field(description="시각화 고유 ID (PK)")
    session_id: str = Field(description="세션 ID (FK)")
    user_id: str = Field(description="사용자 ID (FK)")
    mode: Literal["podcast"] = Field(description="모드")
    episode_id: str | None = Field(default=None, description="에피소드 ID (팟캐스트)")
    # S3 참조
    s3_key: str = Field(description="S3 객체 키 (예: vis/podcast/sess_xxx/ep_xxx.png)")
    cdn_url: str = Field(description="CDN URL (프론트엔드 접근용)")
    # 시각화 메타
    image_prompt: str = Field(description="이미지 생성 프롬프트 (영문)")
    interpretation_text: str = Field(description="해설 텍스트 (한국어)")
    # 추적
    trace_id: str = Field(description="분산 추적 ID")
    created_at: datetime = Field(default_factory=_now_utc, description="생성 시각")


class MySQLSession(BaseModel):
    """
    MySQL 저장 — 세션 메타데이터.

    테이블: sessions

    인덱스:
        - PK: session_id
        - FK: user_id → users.user_id
        - INDEX: (user_id, created_at) — 사용자별 세션 목록
        - INDEX: (status) — 활성 세션 필터
    """

    session_id: str = Field(description="세션 고유 ID (PK)")
    user_id: str = Field(description="사용자 ID (FK)")
    mode: Literal["podcast"] = Field(description="세션 모드")
    status: Literal["active", "closed", "expired"] = Field(
        default="active", description="세션 상태"
    )
    episode_count: int = Field(default=0, description="에피소드 수 (팟캐스트모드)")
    # 피드백
    feedback_rating: int | None = Field(default=None, description="만족도 (1-5)")
    feedback_helpful: bool | None = Field(default=None, description="도움 여부")
    feedback_comment: str | None = Field(default=None, description="피드백 코멘트")
    # 타임스탬프
    created_at: datetime = Field(default_factory=_now_utc, description="생성 시각")
    closed_at: datetime | None = Field(default=None, description="종료 시각")


# ───────────────────────────────────────────────
# 4-2. Pinecone 저장 스키마 (벡터 DB)
# ───────────────────────────────────────────────


class PineconeVectorMetadata(BaseModel):
    """
    Pinecone 벡터 공통 메타데이터.

    모든 Pinecone 벡터에 첨부되는 메타데이터 필드.
    Pinecone은 원본 텍스트를 저장하지 않고, MySQL PK로 참조한다.

    벡터 ID 규칙: "vec_{entity_type}_{mysql_pk}"
        예: "vec_turn_turn_abc123", "vec_episode_ep_xyz456"
    """

    mysql_id: str = Field(
        description="MySQL 원본 레코드 PK. 전체 데이터 조회 시 MySQL을 참조",
    )
    entity_type: Literal[
        "podcast_episode",
        "knowledge_document",
    ] = Field(
        description="벡터가 나타내는 엔티티 유형",
    )
    user_id: str = Field(description="사용자 ID (네임스페이스 또는 필터용)")
    session_id: str = Field(description="세션 ID")
    mode: Literal["podcast"] = Field(description="모드")
    created_at: str = Field(description="생성 시각 (ISO 8601 문자열 — Pinecone은 datetime 미지원)")


class PineconePodcastVector(PineconeVectorMetadata):
    """
    Pinecone — 팟캐스트 에피소드 벡터 메타데이터.

    인덱스: mind-log-podcasts
    네임스페이스: user_id

    Episode Memory가 유사 에피소드를 검색할 때 사용.
    임베딩 대상: title + key_insights + themes 결합 텍스트.
    """

    entity_type: Literal["podcast_episode"] = "podcast_episode"
    episode_id: str = Field(description="에피소드 ID (MySQL FK)")
    title: str = Field(description="에피소드 제목 (필터용)")
    themes: list[str] = Field(default_factory=list, description="주제 태그 (필터용)")
    primary_emotion: str | None = Field(default=None, description="주요 감정 (필터용)")


class PineconeKnowledgeVector(PineconeVectorMetadata):
    """
    Pinecone — 지식 문서 벡터 메타데이터.

    인덱스: mind-log-knowledge
    네임스페이스: domain (예: "mental_health")

    Knowledge Agent가 전문 지식을 검색할 때 사용.
    임베딩 대상: 문서 청크 텍스트.
    """

    entity_type: Literal["knowledge_document"] = "knowledge_document"
    document_id: str = Field(description="문서 ID (MySQL FK)")
    chunk_index: int = Field(description="문서 내 청크 인덱스")
    domain: str = Field(description="지식 도메인 (mental_health, psychology 등)")
    source: str = Field(description="출처 (논문, 가이드라인 등)")
    text_preview: str = Field(max_length=500, description="청크 미리보기 (500자 이내)")


# ───────────────────────────────────────────────
# 4-3. Neo4j 저장 스키마 (그래프 DB)
# ───────────────────────────────────────────────
# Neo4j는 관계(패턴) 분석 전용. 원본 데이터는 MySQL에 보관하고,
# Neo4j 노드는 mysql_id로 MySQL을 참조한다.
# ───────────────────────────────────────────────


class Neo4jNodeBase(BaseModel):
    """Neo4j 노드 공통 속성."""

    mysql_id: str = Field(description="MySQL 원본 PK 참조")
    created_at: str = Field(description="생성 시각 (ISO 8601)")


class Neo4jUserNode(Neo4jNodeBase):
    """
    Neo4j 노드 — 사용자 (:User).

    라벨: :User
    관계:
        - (:User)-[:HAS_SESSION]->(:Session)
        - (:User)-[:SHOWS_PATTERN]->(:EmotionPattern)
    """

    user_id: str = Field(description="사용자 ID (유니크 제약)")
    display_name: str = Field(default="", description="표시 이름")


class Neo4jSessionNode(Neo4jNodeBase):
    """
    Neo4j 노드 — 세션 (:Session).

    라벨: :Session
    관계:
        - (:Session)-[:CONTAINS_TURN]->(:ConversationTurn)
        - (:Session)-[:PRODUCED_EPISODE]->(:PodcastEpisode)
    """

    session_id: str = Field(description="세션 ID (유니크 제약)")
    mode: str = Field(description="세션 모드")


class Neo4jEmotionNode(Neo4jNodeBase):
    """
    Neo4j 노드 — 감정 (:Emotion).

    라벨: :Emotion
    개별 감정 유형당 하나의 노드 (재사용).

    관계:
        - (:ConversationTurn)-[:FELT {intensity, valence}]->(:Emotion)
        - (:PodcastEpisode)-[:ADDRESSED]->(:Emotion)
        - (:Emotion)-[:OFTEN_COOCCURS {count}]->(:Emotion) — 감정 동시 출현 패턴
    """

    emotion_key: str = Field(description="감정 영문 키 (유니크 제약)")
    emotion_kr: str = Field(description="감정 한국어 이름")
    category: str = Field(
        default="neutral",
        description="감정 카테고리 (positive, negative, neutral)",
    )


class Neo4jTopicNode(Neo4jNodeBase):
    """
    Neo4j 노드 — 주제 (:Topic).

    라벨: :Topic
    주제 키워드당 하나의 노드 (재사용).

    관계:
        - (:ConversationTurn)-[:DISCUSSED]->(:Topic)
        - (:PodcastEpisode)-[:COVERS]->(:Topic)
        - (:Topic)-[:RELATED_TO {weight}]->(:Topic) — 주제 간 연관성
    """

    topic_name: str = Field(description="주제 이름 (유니크 제약)")
    domain: str = Field(default="general", description="주제 도메인 (직장, 가족, 건강 등)")


class Neo4jGoTNode(Neo4jNodeBase):
    """
    Neo4j 노드 — GoT 추론 노드 (:GoTNode).

    라벨: :GoTNode
    Podcast Reasoning Agent의 Graph of Thoughts 결과를 저장.

    관계:
        - (:GoTNode)-[:LEADS_TO {weight, relation_type}]->(:GoTNode) — 추론 연결
        - (:PodcastEpisode)-[:REASONED_BY]->(:GoTNode) — 에피소드-추론 연결
    """

    got_node_id: str = Field(description="GoT 노드 ID (유니크 제약)")
    episode_id: str = Field(description="소속 에피소드 ID")
    node_type: str = Field(description="노드 유형 (concept, emotion, experience 등)")
    label: str = Field(description="노드 라벨 (표시 텍스트)")
    weight: float = Field(default=1.0, description="노드 중요도 가중치")


class Neo4jRelationship(BaseModel):
    """
    Neo4j 엣지(관계) 스키마 — 그래프 분석용 관계.

    모든 관계에는 생성 시각과 출처(trace_id)를 기록하여
    시간 기반 관계 분석을 지원한다.
    """

    relationship_type: str = Field(
        description=(
            "관계 타입. "
            "FELT | DISCUSSED | COVERS | ADDRESSED | "
            "OFTEN_COOCCURS | RELATED_TO | LEADS_TO | "
            "HAS_SESSION | CONTAINS_TURN | PRODUCED_EPISODE | "
            "REASONED_BY | SHOWS_PATTERN"
        )
    )
    from_node_id: str = Field(description="시작 노드 ID")
    to_node_id: str = Field(description="끝 노드 ID")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "관계 속성. " "예: {intensity: 0.8, weight: 1.0, count: 5, relation_type: 'causal'}"
        ),
    )
    trace_id: str = Field(description="추적 ID (관계 생성 출처)")
    created_at: str = Field(description="관계 생성 시각 (ISO 8601)")


# ───────────────────────────────────────────────
# 4-4. S3 저장 스키마 (이미지/오디오)
# ───────────────────────────────────────────────


class S3AssetReference(BaseModel):
    """
    S3 에셋 참조 — MySQL 메타데이터와 S3 바이너리를 연결.

    S3에는 바이너리만 저장하고, MySQL visualization_meta 테이블이
    메타데이터(프롬프트, 해설, 스타일)를 관리한다.

    버킷 구조:
        mind-log-bucket/
        ├── vis/
        │   └── podcast/{session_id}/{episode_id}.png       — 팟캐스트 커버
        ├── audio/
        │   └── podcast/{session_id}/{episode_id}/
        │       ├── full.mp3                                — 전체 오디오
        │       └── seg_{n}.mp3                             — 세그먼트별 오디오
        └── exports/
            └── {user_id}/                                  — 사용자 데이터 내보내기
    """

    bucket: str = Field(default="mind-log-bucket", description="S3 버킷 이름")
    key: str = Field(description="S3 객체 키 (전체 경로)")
    content_type: str = Field(description="MIME 타입 (image/png, audio/mpeg 등)")
    mysql_meta_id: str = Field(
        description="MySQL 메타데이터 레코드 ID (visualization_meta.visualization_id)"
    )
    cdn_url: str = Field(description="CDN 배포 URL (프론트엔드 접근용)")
    size_bytes: int | None = Field(default=None, description="파일 크기 (바이트)")


# ═══════════════════════════════════════════════════════════════════════════
# 5. 추적 가능성 (Traceability) 체계
# ═══════════════════════════════════════════════════════════════════════════
#
# 요청부터 DB 저장까지의 전체 추적 흐름:
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │ 1. 프론트엔드 요청                                                     │
# │    PodcastRequest                                                      │
# │    └── tracing: { request_id, trace_id, correlation_id }              │
# │                                                                        │
# │ 2. LangGraph 파이프라인                                                │
# │    AgentState에 trace_id 주입                                          │
# │    ├── TIER 0: Intent Classifier → trace_id 생성 (또는 요청에서 전달)  │
# │    ├── TIER 1: 각 에이전트 → MessageEnvelope.metadata.trace_id 사용    │
# │    ├── TIER 2: 생성 에이전트 → 동일 trace_id                          │
# │    ├── TIER 3: 검증 에이전트 → 동일 trace_id                          │
# │    └── TIER 4: 후처리 에이전트 → 동일 trace_id                        │
# │                                                                        │
# │ 3. DB 저장                                                             │
# │    SaveRequest 또는 직접 DB 저장 시 trace_id 필수 포함                  │
# │    ├── MySQL: trace_id 컬럼 (모든 테이블)                              │
# │    ├── Pinecone: 메타데이터에 trace_id 미포함 (크기 절약)              │
# │    │   └── mysql_id로 MySQL 조회 → trace_id 확인 가능                  │
# │    └── Neo4j: 관계 속성에 trace_id 포함                                │
# │                                                                        │
# │ 4. 응답                                                                │
# │    PodcastEpisodeResponse                                              │
# │    └── tracing: { request_id, trace_id, correlation_id }              │
# │                                                                        │
# │ ★ 추적 쿼리 예시:                                                     │
# │    - "이 응답이 어떻게 만들어졌나?"                                    │
# │      → trace_id로 파이프라인 전체 로그 + DB 레코드 조회                │
# │    - "이 사용자의 3번째 대화부터 5번째 대화까지 감정 변화"             │
# │      → correlation_id 또는 (user_id + session_id + created_at) 조회    │
# │    - "CRISIS 발생 건의 전체 컨텍스트"                                  │
# │      → trace_id + LangSmith trace 연동                                 │
# └─────────────────────────────────────────────────────────────────────────┘
#
# ═══════════════════════════════════════════════════════════════════════════


class TraceQuery(BaseModel):
    """
    추적 조회 요청 — 관리자/디버깅 도구에서 사용.

    특정 요청의 전체 흐름(파이프라인 실행 + DB 저장)을 조회한다.

    Endpoint: GET /api/admin/traces/{trace_id}
    """

    trace_id: str = Field(description="조회할 추적 ID")
    include_agent_logs: bool = Field(default=False, description="에이전트별 I/O 스냅샷 포함 여부")
    include_db_records: bool = Field(default=True, description="DB 저장 레코드 포함 여부")


class TraceResult(BaseModel):
    """
    추적 조회 결과 — 요청의 전체 흐름을 구조화.

    request → pipeline → storage 3단계로 정보를 구성한다.
    """

    trace_id: str = Field(description="추적 ID")
    request_id: str = Field(description="원본 API 요청 ID")
    correlation_id: str = Field(description="상관관계 ID")
    # 요청 단계
    request_summary: dict[str, Any] = Field(description="원본 요청 요약")
    # 파이프라인 단계
    pipeline_stages: list[PipelineStageTrace] = Field(description="TIER별 파이프라인 실행 추적")
    total_pipeline_duration_ms: int = Field(description="파이프라인 전체 소요 시간")
    # 저장 단계
    stored_records: list[StoredRecordTrace] = Field(description="DB 저장 레코드 목록")


class PipelineStageTrace(BaseModel):
    """파이프라인 TIER별 실행 추적."""

    tier: int = Field(description="TIER 번호 (0-4)")
    agents: list[str] = Field(description="실행된 에이전트 목록")
    duration_ms: int = Field(description="TIER 소요 시간")
    status: Literal["ok", "crisis", "retry", "error"] = Field(description="TIER 실행 결과")
    agent_metrics: list[dict[str, Any]] | None = Field(
        default=None,
        description="에이전트별 메트릭 (include_agent_logs=True 시)",
    )


class StoredRecordTrace(BaseModel):
    """DB 저장 레코드 추적."""

    database: Literal["mysql", "pinecone", "neo4j", "s3"] = Field(description="저장된 DB")
    entity_type: str = Field(description="엔티티 유형 (podcast_episode 등)")
    record_id: str = Field(description="레코드 ID")
    stored_at: datetime = Field(description="저장 시각")


# ---------------------------------------------------------------------------
# SSE 스트리밍 이벤트 스키마
# ---------------------------------------------------------------------------


class SSEEventData(BaseModel):
    """SSE 스트리밍 이벤트 데이터 스키마.

    팟캐스트 에피소드 생성 과정에서 클라이언트에 실시간 전달되는 이벤트.

    이벤트 타입별 필드:
        connected:        session_id
        tier_start:       tier, mode, agents[]
        agent_complete:   tier, agent, elapsed_ms, progress
        crisis_detected:  tier, status
        tier_end:         tier, mode, elapsed_ms, status
        result:           data (SlimPodcastResponse)
        error:            message
        done:             (없음)
    """

    event: str = Field(description="이벤트 타입")
    tier: int | None = Field(default=None, description="TIER 번호 (0-4)")
    mode: str | None = Field(default=None, description="파이프라인 모드")
    agent: str | None = Field(default=None, description="에이전트 이름")
    agents: list[str] | None = Field(default=None, description="TIER 내 에이전트 목록")
    elapsed_ms: int | None = Field(default=None, description="소요 시간 (ms)")
    progress: str | None = Field(default=None, description="진행률 (예: 2/4)")
    status: str | None = Field(default=None, description="상태 (ok, crisis)")
    session_id: str | None = Field(default=None, description="세션 ID")
    message: str | None = Field(default=None, description="오류 메시지")
    data: dict[str, Any] | None = Field(default=None, description="결과 데이터")
    timestamp: str = Field(description="ISO 8601 타임스탬프")

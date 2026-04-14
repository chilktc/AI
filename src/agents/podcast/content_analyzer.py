"""
Content Analyzer — 팟캐스트 에피소드 콘텐츠 분석 에이전트.

TIER 1에서 Safety, Emotion, Podcast Reasoning과 병렬 실행된다.
팟캐스트 에피소드의 주제·테마·감정 흐름을 분석한다.

담당: 개발자3
출력 필드: content_analysis
모델: Sonnet 4

v11 고도화:
    - complexity_score 기반 분석 깊이 조절 (light/moderate/deep)
    - 입력 전처리 (최소 길이 검증, 특수문자 정규화)
    - LLM 결과 검증 및 보정 (target_duration 3-5분 범위 고정 등)
"""

from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.context_utils import clamp
from src.api.backend_resources import RESOURCE_CONTENT_ANALYSIS, TYPE_CONTENT_ANALYSIS
from src.api.client import BackendClient
from src.api.publisher import AgentDataPublisher
from src.models.agent_state import AgentState

# 시스템 프롬프트는 prompts/podcast/content_analyzer.yaml에서 로드한다.
# BaseAgent의 get_prompt()로 접근.

# 유효한 서사 구조 목록 (ProjectDocs 스펙 기준)
VALID_NARRATIVE_STRUCTURES = frozenset(
    {
        "personal_story",
        "expert_qa",
        "reflection",
        "comparative",
    }
)

# 기본값 (settings.yaml 미로드 시 fallback)
_DEFAULTS = {
    "min_duration": 3,
    "max_duration": 5,
    "min_sub_themes": 3,
    "max_sub_themes": 5,
    "min_input_length": 10,
    "max_theme_length": 100,
    "deep_threshold": 0.7,
    "moderate_threshold": 0.4,
}


class ContentAnalyzerAgent(BaseAgent):
    """
    팟캐스트 에피소드 콘텐츠 분석 에이전트.

    사용자 입력에서 에피소드 주제, 테마, 콘텐츠 요구사항을 추출한다.
    Intent Classifier의 의도 분류 결과를 참고하여 분석 정확도를 높인다.

    v11 고도화:
        - complexity_score 기반 depth_level 사전 결정 (light/moderate/deep)
        - 입력 전처리: 특수문자 정규화, 최소 길이 검증
        - LLM 결과 후처리: target_duration, sub_themes 개수, 주제 길이 보정
    """

    def __init__(self) -> None:
        super().__init__(name="content_analyzer", tier=1)
        self._load_config()

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        사용자 입력을 분석하여 팟캐스트 에피소드 콘텐츠 구조를 추출한다.

        입력:
            - user_input: 사용자 원본 입력
            - intent: Intent Classifier의 의도 분류 결과 (선택적)

        출력:
            - content_analysis: 에피소드 주제, 테마, 구조 분석 결과
        """
        user_input = state.get("user_input", "")
        if not user_input:
            self.logger.error("[ContentAnalyzer] user_input 없음")
            return {
                "content_analysis": {
                    "main_theme": "",
                    "sub_themes": [],
                    "emotional_journey": {
                        "opening": "",
                        "development": "",
                        "climax": "",
                        "closing": "",
                    },
                    "depth_level": "light",
                    "error": "user_input_missing",
                }
            }
        intent = state.get("intent", {})

        # STEP 1: 입력 전처리 — 특수문자 정규화 + 길이 검증
        normalized_input = self._normalize_input(user_input)
        complexity_score = self._extract_complexity(intent)
        depth_level = self._determine_depth(complexity_score)

        # Intent Classifier 결과를 참고 정보로 포함
        context_info = self._build_context_info(intent, complexity_score, depth_level)

        # STEP 2: LLM 호출로 콘텐츠 분석 수행
        analysis = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=(
                f"사용자 입력: {normalized_input}{context_info}\n\n" f"[분석 깊이: {depth_level}]"
            ),
        )

        # STEP 3: 결과 검증 및 보정 — 스펙 기준에 맞게 후처리
        validated_analysis = self._validate_and_correct(analysis, depth_level)

        # 백엔드에 분석 결과 직접 전달 (실패 시 예외 미전파)
        session_id = state.get("session_id") or ""
        trace_id = str(state.get("trace_id", ""))
        db_payload = self._build_db_payload(validated_analysis, trace_id=trace_id)
        publisher = AgentDataPublisher()
        await publisher.publish(
            resource=RESOURCE_CONTENT_ANALYSIS,
            data=db_payload,
            user_id=state.get("user_id", ""),
            session_id=session_id,
            data_type=TYPE_CONTENT_ANALYSIS,
        )

        # mind-frequencies 수집 호출 (fire-and-forget, 콘텐츠 분석 직후)
        backend_client = BackendClient()
        try:
            user_summary: dict = validated_analysis.get("user_summary", {})
            keywords: list[str] = user_summary.get("keywords", [])
            description: str = user_summary.get("summary", "")
            await backend_client.ingest_mind_frequencies(
                session_id=session_id,
                keywords=keywords,
                description=description,
            )
        finally:
            await backend_client.close()

        return {
            "content_analysis": validated_analysis,
        }

    # === 설정 로드 ===

    def _load_config(self) -> None:
        """settings.yaml에서 에이전트 설정을 로드한다. 실패 시 기본값 사용."""
        cfg = self._load_agent_config(_DEFAULTS)
        self.min_duration: int = cfg["min_duration"]
        self.max_duration: int = cfg["max_duration"]
        self.min_sub_themes: int = cfg["min_sub_themes"]
        self.max_sub_themes: int = cfg["max_sub_themes"]
        self.min_input_length: int = cfg["min_input_length"]
        self.max_theme_length: int = cfg["max_theme_length"]
        self.deep_threshold: float = cfg["deep_threshold"]
        self.moderate_threshold: float = cfg["moderate_threshold"]

    # === 전처리 메서드 ===

    def _normalize_input(self, raw_input: str) -> str:
        """
        입력 전처리 — 특수문자 정규화 및 공백 정리.

        연속 공백을 단일 공백으로 축소하고 앞뒤 공백을 제거한다.
        입력이 최소 길이 미만이면 그대로 반환한다 (LLM이 처리).
        """
        # 연속 공백 → 단일 공백
        normalized = " ".join(raw_input.split())
        return normalized

    def _extract_complexity(self, intent: dict[str, Any]) -> float:
        """Intent Classifier 결과에서 complexity_score를 추출한다."""
        score = intent.get("complexity_score")
        if score is None:
            # Intent Classifier 미실행 시 기본값 (보통 복잡도)
            return 0.5
        # 0.0~1.0 범위 보정
        return max(0.0, min(1.0, float(score)))

    def _determine_depth(self, complexity_score: float) -> str:
        """
        complexity_score 기반 분석 깊이 결정.

        ≥ 0.7 → deep: 세부 테마, 감정 여정, 서사 구조까지 깊이 분석
        0.4 ~ 0.7 → moderate: 표준 분석
        < 0.4 → light: 기본 주제/테마만 추출
        """
        if complexity_score >= self.deep_threshold:
            return "deep"
        if complexity_score >= self.moderate_threshold:
            return "moderate"
        return "light"

    def _build_context_info(
        self,
        intent: dict[str, Any],
        complexity_score: float,
        depth_level: str,
    ) -> str:
        """Intent Classifier 분석 결과를 LLM 프롬프트에 포함할 참고 정보로 구성."""
        if not intent:
            return ""
        return (
            f"\n\n[참고 — Intent Classifier 분석 결과]\n"
            f"- 주요 의도: {intent.get('primary_intent', '미확인')}\n"
            f"- 복잡도: {complexity_score}\n"
            f"- 분석 깊이: {depth_level}\n"
        )

    # === 후처리 메서드 ===

    def _validate_and_correct(self, analysis: dict[str, Any], depth_level: str) -> dict[str, Any]:
        """LLM 분석 결과를 v2.2.0 화이트리스트 기준으로 검증·추출한다.

        반환값은 AgentState용 9개 필드 (v2.2.0 = 백엔드 API 계약 일치).
        DB 저장 시에는 _build_db_payload()로 trace_id를 추가한다.
        """
        # 1. main_theme — 100자 초과 시 잘라냄
        main_theme = str(analysis.get("main_theme", analysis.get("topic", "")))
        if len(main_theme) > self.max_theme_length:
            main_theme = main_theme[: self.max_theme_length] + "..."

        # 2. user_summary — {keywords: list[:5], summary: str} 구조 강제
        raw_summary = analysis.get("user_summary", {})
        if not isinstance(raw_summary, dict):
            raw_summary = {}
        user_summary = {
            "keywords": (
                raw_summary.get("keywords", [])[:5]
                if isinstance(raw_summary.get("keywords"), list)
                else []
            ),
            "summary": str(raw_summary.get("summary", "")),
        }

        # 3. emotional_journey — 4-키 구조 강제 (opening/development/climax/closing)
        raw_journey = analysis.get("emotional_journey", {})
        if not isinstance(raw_journey, dict):
            raw_journey = {}
        emotional_journey = {
            "opening": str(raw_journey.get("opening", "")),
            "development": str(raw_journey.get("development", "")),
            "climax": str(raw_journey.get("climax", "")),
            "closing": str(raw_journey.get("closing", "")),
        }

        # 4. key_messages — list[:5] 제한, 비-list 시 빈 리스트
        raw_messages = analysis.get("key_messages", [])
        key_messages = raw_messages[:5] if isinstance(raw_messages, list) else []

        # 5. sub_themes — list[3-5] 강제. min 미달 시 main_theme 기반 fallback
        raw_themes = analysis.get("sub_themes", analysis.get("themes", []))
        if not isinstance(raw_themes, list):
            raw_themes = []
        raw_themes = raw_themes[: self.max_sub_themes]
        if len(raw_themes) < self.min_sub_themes:
            self.logger.warning(
                "[ContentAnalyzer] sub_themes 개수 미달 (%d < %d) — 기본값으로 보정",
                len(raw_themes),
                self.min_sub_themes,
            )
            while len(raw_themes) < self.min_sub_themes:
                raw_themes.append(main_theme)

        # 6. target_duration — clamp(3-5)
        target_duration = analysis.get("target_duration")
        if target_duration is not None:
            try:
                target_duration = int(target_duration)
            except (ValueError, TypeError):
                target_duration = 4
            target_duration = clamp(target_duration, self.min_duration, self.max_duration)
        else:
            target_duration = 4

        # 7. narrative_structure — 유효값 검증 + fallback
        narrative = analysis.get("narrative_structure", analysis.get("suggested_structure", ""))
        if narrative not in VALID_NARRATIVE_STRUCTURES:
            narrative = "reflection"

        # 8. confidence — 0.0~1.0 범위 강제
        raw_confidence = analysis.get("confidence")
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else 0.5
        except (ValueError, TypeError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        # 9. depth_level — 코드가 직접 결정
        return {
            "user_summary": user_summary,
            "main_theme": main_theme,
            "emotional_journey": emotional_journey,
            "key_messages": key_messages,
            "depth_level": depth_level,
            "sub_themes": raw_themes,
            "target_duration": target_duration,
            "narrative_structure": narrative,
            "confidence": confidence,
        }

    def _build_db_payload(self, validated: dict[str, Any], trace_id: str = "") -> dict[str, Any]:
        """content_analyses DB 저장용 페이로드. 9개 필드 + trace_id."""
        return {
            **validated,
            "trace_id": trace_id,
        }


async def content_analyzer_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Content Analyzer.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = ContentAnalyzerAgent()
    return await agent(state)

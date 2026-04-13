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
from src.api.backend_resources import RESOURCE_CONTENT_ANALYSIS
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
                    "emotional_journey": {},
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
        session_id = state.get("session_id", "")
        publisher = AgentDataPublisher()
        await publisher.publish(
            resource=RESOURCE_CONTENT_ANALYSIS,
            data=validated_analysis,
            user_id=state.get("user_id", ""),
            session_id=session_id,
        )

        # mind-frequencies 수집 호출 (fire-and-forget, 콘텐츠 분석 직후)
        backend_client = BackendClient()
        try:
            keywords: list[str] = validated_analysis.get("sub_themes", [])
            description: str = validated_analysis.get("main_theme", "")
            await backend_client.ingest_mind_frequencies(
                session_id=session_id,
                keywords=keywords,
                description=description,
            )
        except Exception as e:
            self.logger.warning("[ContentAnalyzer] ingest_mind_frequencies failed (ignored): %s", e)
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
        """
        LLM 분석 결과를 검증하고 스펙 기준에 맞게 보정한다.

        보정 항목:
            1. main_theme 길이 제한 (100자)
            2. sub_themes 개수 제한 (3~5개)
            3. target_duration 범위 제한 (3~5분)
            4. narrative_structure 유효값 검증
            5. depth_level 필드 보장
        """
        corrected = dict(analysis)

        # 1. 주제 길이 검증 — 100자 초과 시 잘라냄
        main_theme = corrected.get("main_theme", corrected.get("topic", ""))
        if len(main_theme) > self.max_theme_length:
            main_theme = main_theme[: self.max_theme_length] + "..."
        corrected["main_theme"] = main_theme

        # 2. 하위 주제 개수 보정 — 3~5개 범위
        sub_themes = corrected.get("sub_themes", corrected.get("themes", []))
        if not isinstance(sub_themes, list):
            sub_themes = []
        if len(sub_themes) > self.max_sub_themes:
            sub_themes = sub_themes[: self.max_sub_themes]
        corrected["sub_themes"] = sub_themes

        # 3. 에피소드 길이 보정 — 3~5분 범위 고정
        target_duration = corrected.get("target_duration")
        if target_duration is not None:
            try:
                target_duration = int(target_duration)
            except (ValueError, TypeError):
                target_duration = 4  # 기본값
            target_duration = clamp(target_duration, self.min_duration, self.max_duration)
        else:
            target_duration = 4  # 기본값
        corrected["target_duration"] = target_duration

        # 4. 서사 구조 유효성 검증 — 유효하지 않으면 reflection 기본값
        narrative = corrected.get("narrative_structure", corrected.get("suggested_structure", ""))
        if narrative not in VALID_NARRATIVE_STRUCTURES:
            narrative = "reflection"
        corrected["narrative_structure"] = narrative

        # 5. depth_level 필드 보장
        corrected["depth_level"] = depth_level

        return corrected


async def content_analyzer_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Content Analyzer.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = ContentAnalyzerAgent()
    return await agent(state)

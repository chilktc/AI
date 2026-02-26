from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


# ============================================================
# Emotion → Color / Style Rule Table (상수)
# ============================================================
# 목적:
# - “감정 카드” 시각 스타일을 LLM에 전부 맡기지 않고,
#   서비스 레벨에서 일관된 규칙(우울=파랑, 기쁨=노랑/분홍 등)을 고정합니다.
#
# 주의:
# - 이 매핑은 UX 일관성을 위한 “디자인 규칙”입니다(정답 아님).
EMOTION_COLOR_MAP: dict[str, dict[str, Any]] = {
    "sadness": {
        "palette": "blue",
        "gradient": ["#1E3A8A", "#60A5FA"],
        "pattern": "soft_rain",
        "keywords": ["calm", "cool", "gentle", "blue haze"],
    },
    "depression": {
        "palette": "blue",
        "gradient": ["#0F172A", "#3B82F6"],
        "pattern": "heavy_fog",
        "keywords": ["low energy", "muted", "blue fog", "quiet"],
    },
    "anxiety": {
        "palette": "purple",
        "gradient": ["#4C1D95", "#A78BFA"],
        "pattern": "shimmer_noise",
        "keywords": ["restless", "tension", "soft pulse"],
    },
    "fear": {
        "palette": "violet",
        "gradient": ["#2E1065", "#C4B5FD"],
        "pattern": "edge_glow",
        "keywords": ["alert", "uncertain", "mist"],
    },
    "anger": {
        "palette": "red",
        "gradient": ["#7F1D1D", "#F87171"],
        "pattern": "sharp_flare",
        "keywords": ["hot", "sharp", "dynamic"],
    },
    "disgust": {
        "palette": "olive",
        "gradient": ["#365314", "#A3E635"],
        "pattern": "grain",
        "keywords": ["aversion", "grainy", "muted green"],
    },
    "stress": {
        "palette": "teal",
        "gradient": ["#134E4A", "#5EEAD4"],
        "pattern": "tight_waves",
        "keywords": ["pressure", "compressed", "teal waves"],
    },
    "neutral": {
        "palette": "gray",
        "gradient": ["#111827", "#9CA3AF"],
        "pattern": "smooth",
        "keywords": ["balanced", "neutral", "soft gray"],
    },
    "joy": {
        "palette": "yellow_pink",
        "gradient": ["#FDE047", "#FB7185"],
        "pattern": "sunburst",
        "keywords": ["bright", "warm", "uplifting", "glow"],
    },
    "happiness": {
        "palette": "yellow_pink",
        "gradient": ["#FACC15", "#FDA4AF"],
        "pattern": "soft_sparkle",
        "keywords": ["warm", "soft sparkle", "light"],
    },
    "gratitude": {
        "palette": "gold",
        "gradient": ["#F59E0B", "#FDE68A"],
        "pattern": "gentle_rays",
        "keywords": ["thankful", "golden", "tender"],
    },
    "hope": {
        "palette": "sky",
        "gradient": ["#38BDF8", "#FBCFE8"],
        "pattern": "rising_mist",
        "keywords": ["forward", "airy", "soft lift"],
    },
}

EMOTION_ALIASES: dict[str, str] = {
    "우울": "sadness",
    "불안": "anxiety",
    "분노": "anger",
    "기쁨": "joy",
    "행복": "happiness",
    "중립": "neutral",
    "스트레스": "stress",
    "두려움": "fear",
    "혐오": "disgust",
}

INTENSITY_LABELS = [
    (0.0, 0.35, "Soft Pastel"),
    (0.35, 0.65, "Balanced"),
    (0.65, 1.01, "Vibrant"),
]

AROUSAL_LABELS = [
    (0.0, 0.35, "Calm"),
    (0.35, 0.65, "Steady"),
    (0.65, 1.01, "Dynamic"),
]


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pick_label(x: float, ranges: list[tuple[float, float, str]]) -> str:
    for lo, hi, label in ranges:
        if lo <= x < hi:
            return label
    return ranges[-1][2]


def _normalize_emotion_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "neutral"
    if raw in EMOTION_ALIASES:
        return EMOTION_ALIASES[raw]
    norm = raw.lower()
    if norm in EMOTION_COLOR_MAP:
        return norm
    if "sad" in norm:
        return "sadness"
    if "anx" in norm:
        return "anxiety"
    if "ang" in norm:
        return "anger"
    if "joy" in norm or "happy" in norm:
        return "joy"
    return "neutral"


def _choose_palette(primary_emotion: str) -> dict[str, Any]:
    key = _normalize_emotion_name(primary_emotion)
    return EMOTION_COLOR_MAP.get(key, EMOTION_COLOR_MAP["neutral"])


class VisualizationAgent(BaseAgent):
    """
    Visualization Agent (tier=None)
    ✅ 출력 키: visualization_result

    기능:
    - 이미지 생성용 프롬프트(image_prompt) 생성
    - 감정 카드 터치 시 노출될 해설(interpretation_text) 생성

    안전:
    - interpretation_text는 진단/단정 금지
    - safety_flags가 warning/crisis이면 완곡한 안전 고지 1문장 추가
    """

    def __init__(self) -> None:
        super().__init__(name="visualization", tier=None)

    async def process(self, state: AgentState) -> dict[str, Any]:
        mode = str(state.get("mode", "podcast"))

        emotion = state.get("emotion_vectors") or {}
        if not isinstance(emotion, dict):
            emotion = {}

        safety_flags = state.get("safety_flags") or {}
        if not isinstance(safety_flags, dict):
            safety_flags = {}

        content_analysis = state.get("content_analysis") or {}
        if not isinstance(content_analysis, dict):
            content_analysis = {}

        reasoning_result = state.get("reasoning_result") or {}
        if not isinstance(reasoning_result, dict):
            reasoning_result = {}

        final_output = state.get("final_output", "")
        script_draft = state.get("script_draft", {})

        primary_emotion = str(emotion.get("primary_emotion", "neutral"))
        intensity = _clamp(_to_float(emotion.get("intensity"), 0.5), 0.0, 1.0)
        valence = _clamp(_to_float(emotion.get("valence"), 0.0), -1.0, 1.0)
        arousal = _clamp(_to_float(emotion.get("arousal"), 0.5), 0.0, 1.0)

        palette_info = _choose_palette(primary_emotion)
        intensity_label = _pick_label(intensity, INTENSITY_LABELS)
        arousal_label = _pick_label(arousal, AROUSAL_LABELS)

        # 품질 핵심: 최종 스크립트/최종 출력이 있으면 그것을 우선 사용
        has_final = isinstance(final_output, str) and len(final_output.strip()) > 0
        has_script = isinstance(script_draft, dict) and len(script_draft) > 0

        if has_final:
            summary_source_label = "final_output"
            content_summary_text = final_output
        elif has_script:
            summary_source_label = "script_draft"
            content_summary_text = str(script_draft)
        else:
            summary_source_label = "fallback_context"
            content_summary_text = (
                f"user_input={state.get('user_input','')}\n"
                f"content_analysis={content_analysis}\n"
                f"reasoning_result={reasoning_result}\n"
                f"emotion_vectors={emotion}\n"
            )

        if mode == "conversation":
            style_guide = (
                "Abstract emotional gradient card style. "
                "Aurora-like soft gradients, no text, no letters, no watermarks. "
                "Focus on color, texture, and gentle shapes."
            )
        else:
            style_guide = (
                "Conceptual illustration for a podcast episode cover. "
                "Warm and friendly, symbolic shapes, minimal clutter. "
                "No text, no letters, no logos, no watermarks."
            )

        safety_status = str(safety_flags.get("status", "safe"))
        required_in_script = safety_flags.get("required_in_script", [])
        if not isinstance(required_in_script, list):
            required_in_script = []

        interpretation_rules = (
            "해설(interpretation)은 1~2문장 한국어로 작성합니다.\n"
            "- 감정 '나열'만 하지 말고, 지금의 맥락을 공감적으로 요약하고 가볍게 통찰을 제공합니다.\n"
            "- 절대 진단/처방/단정 표현 금지. (예: '우울증입니다' 금지)\n"
            "- 사용자가 스스로 선택할 수 있는 부드러운 제안 1개를 포함할 수 있습니다.\n"
            "- 색/패턴이 의미하는 바를 '가능성'으로 표현하세요. (예: '~일지도 몰라요')\n"
        )

        safety_addendum = ""
        if safety_status in ("warning", "crisis"):
            safety_addendum = str(required_in_script[0]) if required_in_script else (
                "필요하시다면 전문가의 도움을 받는 것도 하나의 방법이 될 수 있어요."
            )

        try:
            vis_data = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=(
                    f"[Mode]\n{mode}\n\n"
                    f"[Style Guide]\n{style_guide}\n\n"
                    f"[Emotion Vectors]\n{emotion}\n\n"
                    f"[Fixed Color Rule]\n"
                    f"- primary_emotion={primary_emotion}\n"
                    f"- palette={palette_info.get('palette')}\n"
                    f"- gradient={palette_info.get('gradient')}\n"
                    f"- pattern={palette_info.get('pattern')}\n"
                    f"- intensity={intensity} ({intensity_label})\n"
                    f"- arousal={arousal} ({arousal_label})\n"
                    f"- valence={valence}\n\n"
                    f"[Content Summary Source]\n{summary_source_label}\n\n"
                    f"[Content Summary]\n{content_summary_text}\n\n"
                    f"[Interpretation Rules]\n{interpretation_rules}\n\n"
                    "반드시 JSON으로 반환:\n"
                    "{\n"
                    '  "image_prompt": "이미지 모델용 상세 영어 프롬프트(텍스트/로고/워터마크 금지 포함)",\n'
                    '  "interpretation": "카드 터치 시 보여줄 1~2문장 한국어",\n'
                    '  "style_tags": ["tag1", "tag2", "..."]\n'
                    "}\n"
                ),
            )
        except KeyError:
            vis_data = {
                "image_prompt": "Soft abstract gradient background, aurora-like, no text, no watermark",
                "interpretation": "오늘 마음을 부드러운 빛의 흐름으로 그려보았어요.",
                "style_tags": ["minimal"],
            }

        interpretation = str(vis_data.get("interpretation", "")).strip() or (
            "오늘 마음을 부드러운 빛의 흐름으로 그려보았어요."
        )
        if safety_addendum and (safety_addendum not in interpretation):
            if not interpretation.endswith(("요.", "다.", ".", "!", "?")):
                interpretation += "요."
            interpretation = f"{interpretation} {safety_addendum}"

        style_tags = vis_data.get("style_tags", [])
        if not isinstance(style_tags, list):
            style_tags = []

        s3_path = f"s3://mind-log-bucket/vis/{mode}/{state.get('session_id', 'temp')}.png"

        return {
            "visualization_result": {
                "mode": mode,
                "image_url": s3_path,
                "interpretation_text": interpretation,
                "style_info": {
                    "type": "Aurora" if mode == "conversation" else "Conceptual",
                    "palette": palette_info.get("palette", "gray"),
                    "gradient": palette_info.get("gradient", EMOTION_COLOR_MAP["neutral"]["gradient"]),
                    "pattern": palette_info.get("pattern", "smooth"),
                    "intensity": intensity,
                    "intensity_label": intensity_label,
                    "arousal": arousal,
                    "arousal_label": arousal_label,
                    "valence": valence,
                    "primary_emotion": _normalize_emotion_name(primary_emotion),
                },
                "input_source": summary_source_label,
                "raw_metadata": {
                    "image_prompt": str(vis_data.get("image_prompt", "")).strip(),
                    "style_tags": style_tags,
                    "llm_interpretation": str(vis_data.get("interpretation", "")).strip(),
                    "safety_status": safety_status,
                },
            }
        }


visualization_agent = VisualizationAgent()


async def visualization_node(state: AgentState):
    return await visualization_agent(state)
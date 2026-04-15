# src/agents/shared/safety_constants.py

# 법적 고지 및 임상 안내 문구 (고정 상수)
LEGAL_DISCLAIMER = (
    "본 서비스는 AI 모델에 기반한 보조 도구이며, 전문적인 의료 진단이나 치료를 대체할 수 없습니다. "
    "긴박한 위험이 느껴진다면 반드시 아래의 전문 기관에 도움을 요청하십시오."
)

# 위기 대응 헬프라인 정보
CRISIS_HELPLINES = [
    {"name": "자살예방 상담전화", "number": "109"},
    {"name": "정신건강 상담전화", "number": "1577-0199"},
    {"name": "청소년 상담전화", "number": "1388"},
    {"name": "희망의 전화", "number": "129"},
]

# 위험 상태별 메시지 템플릿 결합
SAFETY_MESSAGES = {
    "warning": (
        "현재 정서적으로 매우 힘든 상태이신 것 같습니다. "
        "잠시 숨을 고르고 주변의 믿을만한 사람에게 "
        "이야기를 나눠보시는 건 어떨까요?"
    ),
    "crisis": f"{LEGAL_DISCLAIMER}\n\n[전문 상담 기관 안내]\n"
    + "\n".join([f"- {h['name']}: {h['number']}" for h in CRISIS_HELPLINES]),
}

# ─────────────────────────────────────────────────────────────
# CRISIS 폴백 상수 — TIER 2~4 에이전트가 LLM 미호출 시 반환할 하드코딩 값
# ─────────────────────────────────────────────────────────────

# Visualization CRISIS 폴백 이미지 URL (실제 이미지 미생성 시 placeholder)
# settings.yaml crisis.fallback_image_url에서도 동일 URL 관리
CRISIS_FALLBACK_IMAGE_URL = "https://mindlog-images.s3.amazonaws.com/vis/crisis_placeholder.png"

CRISIS_FALLBACK_VALUES: dict = {
    # Script Generator CRISIS 폴백 (TIER 2)
    "script_draft": {
        "episode_title": "마음 돌봄 안내",
        "total_duration": 0,
        "script_text": SAFETY_MESSAGES["crisis"],
        "tts_markers": [],
        "key_insights": [],
        "themes": [],
        "metadata": {"safety_status": "crisis"},
    },
    # Visualization CRISIS 폴백 (TIER 2) — image_url 필수 (미제공 시 백엔드 오류)
    "visual_data": {
        "image_url": CRISIS_FALLBACK_IMAGE_URL,
        "s3_key": "",
        "status": "crisis_fallback",
        "style_type": "abstract",
        "interpretation": "위기 안내 화면",
        "original_prompt": "",
        "retry_count": 0,
        "error": None,
    },
    # Batch Validator CRISIS 자동 통과 (TIER 3)
    "validation_result": {
        "verdict": "PASS",
        "overall_score": 0.7,
        "action": {
            "decision": "approve",
            "revision_instructions": "CRISIS 자동 승인",
            "priority_fixes": [],
        },
        "forced_pass": True,
    },
}

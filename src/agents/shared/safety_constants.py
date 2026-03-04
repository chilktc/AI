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
    {"name": "희망의 전화", "number": "129"}
]

# 위험 상태별 메시지 템플릿 결합
SAFETY_MESSAGES = {
    "warning": "현재 정서적으로 매우 힘든 상태이신 것 같습니다. 잠시 숨을 고르고 주변의 믿을만한 사람에게 이야기를 나눠보시는 건 어떨까요?",
    "crisis": f"{LEGAL_DISCLAIMER}\n\n[전문 상담 기관 안내]\n" + "\n".join([f"- {h['name']}: {h['number']}" for h in CRISIS_HELPLINES])
}
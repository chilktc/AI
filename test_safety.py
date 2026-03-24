import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

# [경로 설정] 현재 실행 경로를 파이썬 경로에 추가 (Import 에러 방지)
sys.path.append(os.getcwd())

from src.agents.podcast.safety import SafetyAgent

async def run_safety_test():
    print("🚀 Safety Agent 루트 경로 직접 테스트 시작")
    print("-" * 50)

    # 테스트 케이스 (SAFE / WARNING / CRISIS)
    test_cases = [
        {
            "name": "CASE 1: 일상 (SAFE)",
            "input": "오늘 업무가 좀 많아서 피곤하네.",
            "mock_res": {"status": "safe", "risk_level": 0, "risk_score": 0.1, "reasons": ["단순 피로"]}
        },
        {
            "name": "CASE 2: 번아웃 (WARNING)",
            "input": "진짜 다 그만두고 싶어. 무기력해서 아무것도 못 하겠어.",
            "mock_res": {"status": "warning", "risk_level": 2, "risk_score": 0.6, "reasons": ["탈진 상태"]}
        },
        {
            "name": "CASE 3: 위기 (CRISIS)",
            "input": "더 이상 버틸 수가 없어. 끝내고 싶어.",
            "mock_res": {"status": "crisis", "risk_level": 3, "risk_score": 0.9, "reasons": ["자해 위험"]}
        }
    ]

    agent = SafetyAgent()

    for case in test_cases:
        print(f"\n🔍 [테스트] {case['name']}")
        state = {"user_input": case["input"], "intent": {"flags": {"risk_flag": False}}}

        # LLM 호출 부분만 가짜로 대체
        with patch.object(agent, 'call_llm_json', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = case["mock_res"]

            result = await agent.process(state)

            # 결과 확인
            status = case["mock_res"]["status"]
            print(f"  - 판정: {status.upper()}")
            
            # 헬프라인 문구 결합 확인
            if "safety_flags" in result and "required_in_script" in result["safety_flags"]:
                print(f"  - 안내 문구 삽입: ✅ OK")
            
            # CRISIS 시 워크플로우 중단 플래그 확인
            if status == "crisis":
                print(f"  - 차단 플래그: {'next_step: crisis_response 확인' if result.get('next_step') == 'crisis_response' else '❌ 실패'}")

    print("\n" + "-" * 50 + "\n✅ 테스트 완료")

if __name__ == "__main__":
    asyncio.run(run_safety_test())
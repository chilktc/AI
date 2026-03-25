"""
E2E LangGraph 워크플로우 - AWS Bedrock 실전 검증 테스트.

작업 목표:
1. Bedrock 환경에서 TIER 0부터 TIER 4까지 전체 노드가 무사히 돌아가는지 확인.
2. 각 에이전트가 생성한 결과물(intent, safety_flags 등)이 빠짐없이 생성되는지 검증.
3. 실행 시간(Latency)을 측정하여 가성비 모델 선정의 기초 데이터 확보.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# [경로 설정] 현재 실행 위치를 파이썬 경로에 등록
sys.path.append(os.getcwd())

# 기존 유틸리티 및 픽스처 임포트 (프로젝트 구조에 따라 경로 조정 필요)
try:
    from dev.live_tests.conftest_live import Timer, check_provider_health, print_banner, print_section, setup_provider, print_error
except ImportError:
    # 유틸리티가 없을 경우를 대비한 최소한의 가짜 타이머 클래스
    class Timer:
        def __enter__(self): self.start = time.perf_counter(); return self
        def __exit__(self, *args): self.elapsed = time.perf_counter() - self.start

# ────────────────────────────────────────
# Bedrock 테스트 모델 설정
# ────────────────────────────────────────
DEFAULT_BEDROCK_MODELS = [
    "anthropic.claude-3-haiku-20240307-v1:0",  # 가성비 모델 (테스트 1순위)
    "anthropic.claude-3-5-sonnet-20240620-v1:0" # 고성능 모델 (비교용)
]

# 검증할 에이전트 결과 필드들
EXPECTED_FIELDS = [
    "intent", "safety_flags", "emotion_vectors", "content_analysis", 
    "reasoning_result", "script_draft", "validation_result", "final_output"
]

def _refresh_all_singletons():
    """프로바이더 전환 시 에이전트들을 새 모델로 갈아끼움"""
    import importlib
    from config.loader import get_settings
    settings = get_settings()
    settings._instance = None 
    from src.graph import workflow
    importlib.reload(workflow)

async def run_workflow_for_bedrock(model_name: str, initial_state: dict[str, Any]):
    label = f"Bedrock/{model_name}"
    print_banner(f"🚀 실전 테스트 가동: {label}", color="cyan")

    setup_provider("bedrock", model_name)
    _refresh_all_singletons()

    # 헬스체크 (인프라 팀 권한 확인용)
    if not await check_provider_health("bedrock"):
        print(f" ⚠️ [권한 없음] {label} 모델을 사용할 수 없습니다.")
        return None

    try:
        from src.graph.workflow import build_unified_graph
        app = build_unified_graph().compile()

        from src.api.client import BackendClient
        with patch.object(BackendClient, "save", new_callable=AsyncMock):
            with Timer() as t:
                final_state = await app.ainvoke(initial_state)
        
        elapsed = t.elapsed
        print(f" ✅ [완료] 소요 시간: {elapsed:.1f}초")

        # 결과 검증 (에이전트들이 도장을 다 찍었나?)
        present_count = 0
        for field in EXPECTED_FIELDS:
            if final_state.get(field):
                present_count += 1
        
        _save_results(model_name, final_state, elapsed)
        return {"model": model_name, "success": True, "time": elapsed, "score": f"{present_count}/{len(EXPECTED_FIELDS)}"}

    except Exception as e:
        print(f" ❌ 에러 발생: {e}")
        return {"model": model_name, "success": False}

def _save_results(model, state, elapsed):
    results_dir = Path("./dev/live_tests/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = f"bedrock_{model.replace('.', '_')}_{int(time.time())}.json"
    with open(results_dir / filename, "w", encoding="utf-8") as f:
        json.dump({"model": model, "elapsed": elapsed, "state": state}, f, ensure_ascii=False, indent=2, default=str)

# ────────────────────────────────────────
# 메인 실행부 
# ────────────────────────────────────────
async def main():
    # 1. 초기 상태 설정 (실제 사용 시나리오에 맞게 조정)
    initial_state = {
        "user_input": "팀장님이 배포 빨리 하라고 쪼아대서 너무 스트레스 받아.. 도와줘!", 
        "user_id": "matcha_real",
        "mode": "podcast" # 팟캐스트 모드로 테스트
    }
    
    print_banner("E2E Bedrock 통합 테스트 (실전 모드)", color="bold")
    print(f" 📝 입력 메시지: {initial_state['user_input']}")
    
    results = []
    for model in DEFAULT_BEDROCK_MODELS:
        res = await run_workflow_for_bedrock(model, initial_state)
        if res: results.append(res)
    
    # 최종 결과 요약 표
    print("\n" + "="*60)
    print(f"{'MODEL':<45} | {'TIME':<7} | {'FIELDS'}")
    print("-" * 60)
    for r in results:
        print(f"{r['model']:<45} | {r['time']:>5.1f}s | {r['score']}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
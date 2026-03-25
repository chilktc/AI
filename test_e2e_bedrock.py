from __future__ import annotations
import asyncio, json, os, sys, time, traceback
from pathlib import Path

# 현재 경로를 sys.path에 추가하여 모듈 참조 가능케 함
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv()

# ── workflow 최상단 import (싱글톤 타이밍 및 순환 참조 방지) ──
import src.graph.workflow as wf
from src.graph.workflow import compile_graph

# 2026년형 Bedrock 모델 ID (us. 접두사는 교차 리전 추론을 위해 권장됨)
MODELS = {
    "haiku":  "us.anthropic.claude-3-haiku-20240307-v1:0",
    "sonnet": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "opus":   "us.anthropic.claude-3-opus-20240229-v1:0",
}

# 에이전트별 타겟 모델 매핑
AGENT_MODEL_MAP = {
    "_intent_classifier":   "haiku",
    "_script_generator":    "sonnet",
    "_script_personalizer": "haiku",
}

EXPECTED_FIELDS = ["intent", "safety_flags", "emotion_vectors", "final_output"]

INITIAL_STATE = {
    "user_input": "팀장님이 배포 빨리 하라고 쪼아대서 너무 스트레스 받아.. 도와줘!",
    "user_id":    "matcha_real",
    "session_id": "test_001",
    "mode":        "conversation",
}

def _inject_model(attr: str, model_key: str) -> None:
    """에이전트의 LLMClient 내부 변수(_model_id)를 직접 수정하여 모델을 강제 주입함"""
    agent = getattr(wf, attr, None)
    if agent is None:
        print(f"  ⚠️  {attr} 없음 — 건너뜀")
        return
    lc = getattr(agent, "llm_client", None)
    if lc is None:
        print(f"  ⚠️  {attr}.llm_client 없음 — 건너뜀")
        return
    
    # [치트키] 읽기 전용 속성을 우회하여 내부 변수 직접 수정
    lc._model_id = MODELS[model_key]
    print(f"  ✅ {attr} → {model_key} ({MODELS[model_key]})")

def _set_all_agents(model_key: str) -> None:
    """모든 매핑된 에이전트에 동일한 모델을 일괄 주입"""
    for attr in AGENT_MODEL_MAP:
        _inject_model(attr, model_key)

def _apply_map() -> None:
    """AGENT_MODEL_MAP에 정의된 대로 에이전트별 모델 배정"""
    for attr, model_key in AGENT_MODEL_MAP.items():
        _inject_model(attr, model_key)

def _check_fields(state: dict) -> int:
    """결과 상태값의 필드 유효성 검증"""
    present = 0
    for field in EXPECTED_FIELDS:
        val = state.get(field)
        icon = "✅" if val else "⬜"
        preview = str(val)[:70] if val else "없음"
        print(f"    {icon} {field}: {preview}")
        if val: present += 1
    return present

def _save(label: str, elapsed: float, state: dict) -> Path:
    """테스트 결과를 JSON 파일로 저장"""
    d = Path("./test_results"); d.mkdir(exist_ok=True)
    p = d / f"{label}_{int(time.time())}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"label": label, "elapsed": elapsed, "state": state},
                  f, ensure_ascii=False, indent=2, default=str)
    return p

async def run_scenario(label: str) -> dict:
    """테스트 시나리오 실행 루프"""
    print(f"\n{'='*58}\n  시나리오: {label}\n{'='*58}")
    try:
        app = compile_graph("unified")
        start = time.perf_counter()
        final_state = await app.ainvoke(INITIAL_STATE)
        elapsed = time.perf_counter() - start
        
        print(f"\n  ⏱  완료: {elapsed:.2f}s\n\n  [에이전트 결과 체크]")
        present = _check_fields(final_state)
        path = _save(label, elapsed, final_state)
        print(f"  💾 저장: {path}")
        
        return {"label": label, "success": True, "elapsed": elapsed,
                "score": f"{present}/{len(EXPECTED_FIELDS)}"}
    except Exception as e:
        print(f"\n  ❌ 실패: {e}\n{traceback.format_exc()}")
        return {"label": label, "success": False, "elapsed": 0.0, "error": str(e)}

async def main() -> None:
    """메인 테스트 시퀀스"""
    print("\n" + "="*58 + "\n  E2E Bedrock 통합 테스트\n" + "="*58)
    print(f"  리전     : {os.getenv('AWS_REGION', 'ap-northeast-2')}")
    print(f"  프로바이더: {os.getenv('LLM_PROVIDER', 'bedrock')}")

    print("\n  [현재 에이전트 모델 ID]")
    for attr in AGENT_MODEL_MAP:
        agent = getattr(wf, attr, None)
        lc = getattr(agent, "llm_client", None) if agent else None
        # property getter를 통해 현재 배정된 모델 ID 확인
        mid = getattr(lc, "model_id", "없음") if lc else "llm_client 없음"
        print(f"    {attr}: {mid}")

    results = []
    
    print("\n\n▶ 1단계: 전체 Haiku — 워크플로우 흐름 확인")
    _set_all_agents("haiku")
    res1 = await run_scenario("1단계_전체Haiku")
    results.append(res1)

    if res1["success"]:
        print("\n\n▶ 2단계: 에이전트별 모델 배정 (Haiku & Sonnet)")
        _apply_map()
        res2 = await run_scenario("2단계_모델배정")
        results.append(res2)

    # 최종 결과 요약 테이블 출력
    print("\n\n" + "="*58 + f"\n  {'시나리오':<22} | {'시간':>6} | {'필드':<6} | 상태\n" + "-"*58)
    for r in results:
        st = "✅ 성공" if r["success"] else "❌ 실패"
        print(f"  {r['label']:<22} | {f'{r.get('elapsed',0):.1f}s':>6} | {r.get('score','-'):<6} | {st}")
    print("="*58)

if __name__ == "__main__":
    asyncio.run(main())
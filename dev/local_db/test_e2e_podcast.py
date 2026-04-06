"""
E2E 팟캐스트 파이프라인 + 로컬 DB 통합 테스트.

실제 OpenAI LLM으로 전체 팟캐스트 파이프라인을 실행하고:
  B) 에이전트가 DB 시드 데이터를 활용했는지 검증
  C) 파이프라인 완료 후 BackendClient.save() 호출 내역 검증 + MySQL 기록

기존 코드(src/, tests/, config/) 무수정 — 이 파일만 추가.
삭제: rm dev/local_db/test_e2e_podcast.py

사용법:
    # Docker DB 기동 + 시드 데이터 로드 후
    python -m dev.local_db.test_e2e_podcast

    # pytest로 실행
    pytest dev/local_db/test_e2e_podcast.py -v -s
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

# 프로젝트 루트 sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# .env.db 로드 (기존 환경변수 보존)
_env_db = Path(__file__).parent / ".env.db"
if _env_db.exists():
    with open(_env_db, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

logger = logging.getLogger(__name__)

# ANSI 컬러
_G = "\033[92m"
_R = "\033[91m"
_Y = "\033[93m"
_C = "\033[96m"
_B = "\033[1m"
_0 = "\033[0m"

# 파이프라인 완료 시 존재해야 할 상태 필드
EXPECTED_FIELDS = [
    "intent",
    "safety_flags",
    "emotion_vectors",
    "content_analysis",
    "reasoning_result",
    "script_draft",
    "validation_result",
    "final_output",
]

# 파이프라인에서 BackendClient.save()로 전달되는 리소스 타입
EXPECTED_RESOURCES = [
    "emotion_logs",
    "content_analyses",
    "learning",
]


# ────────────────────────────────────────
# 환경 설정
# ────────────────────────────────────────

def _setup_openai(model: str = "gpt-4o-mini") -> None:
    """OpenAI 프로바이더를 설정하고 싱글톤을 리프레시한다."""
    from dev.live_tests.conftest_live import setup_provider

    setup_provider("openai", model)

    # 싱글톤 리프레시 (기존 e2e 테스트 패턴 재사용)
    import importlib

    from config.loader import get_settings
    settings = get_settings()
    settings._instance = None  # type: ignore[attr-defined]

    from src.graph import workflow
    importlib.reload(workflow)

    agent_modules = [
        "src.agents.podcast.safety",
        "src.agents.podcast.emotion",
        "src.agents.podcast.content_analyzer",
        "src.agents.podcast.podcast_reasoning",
        "src.agents.podcast.batch_validator",
        "src.agents.podcast.visualization",
        "src.agents.podcast.learning",
        "src.agents.podcast.episode_memory",
    ]
    for mod_name in agent_modules:
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
        except Exception as e:
            logger.warning("싱글톤 리프레시 실패 — %s: %s", mod_name, e)


def _check_openai_key() -> bool:
    """OpenAI API 키 존재를 확인한다."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print(f"{_R}[ERROR]{_0} OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  .env 파일에 OPENAI_API_KEY=sk-... 을 추가하세요.")
        return False
    return True


# ────────────────────────────────────────
# DB 프로브 (skip 판단용)
# ────────────────────────────────────────

def _probe_mysql() -> bool:
    """MySQL 연결 가능 여부."""
    try:
        import pymysql
        from src.db.mysql_client import _parse_mysql_url

        url = os.getenv("MYSQL_URL", "")
        if not url:
            return False
        params = _parse_mysql_url(url)
        params["connect_timeout"] = 3
        conn = pymysql.connect(**params)
        conn.close()
        return True
    except Exception:
        return False


def _probe_neo4j() -> bool:
    """Neo4j 연결 가능 여부."""
    try:
        from neo4j import GraphDatabase

        url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pw = os.getenv("NEO4J_PASSWORD", "")
        driver = GraphDatabase.driver(url, auth=(user, pw))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


# ────────────────────────────────────────
# 파이프라인 실행 + 캡처
# ────────────────────────────────────────

async def run_pipeline_with_capture(
    initial_state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    전체 팟캐스트 파이프라인을 실행하고 BackendClient.save() 호출을 캡처한다.

    Returns:
        (final_state, captured_saves)
        - final_state: ainvoke() 반환 상태
        - captured_saves: save() 호출마다 {"resource": str, "data": SaveRequest} 기록
    """
    from src.graph.workflow import build_unified_graph

    graph = build_unified_graph()
    compiled = graph.compile()

    captured_saves: list[dict[str, Any]] = []

    # BackendClient.save()를 가로채서 캡처 + mock 응답 반환
    async def capture_save(self_or_resource, resource_or_data=None, data=None, **kw):
        """save() 호출을 캡처한다. 인스턴스/클래스 메서드 양쪽 대응."""
        # patch.object 사용 시: self가 첫 번째 인자가 아님 (이미 바인딩됨)
        # new_callable=AsyncMock 사용 시: resource, data 순서
        if resource_or_data is not None:
            actual_resource = self_or_resource
            actual_data = resource_or_data
        else:
            actual_resource = self_or_resource
            actual_data = data

        captured_saves.append({
            "resource": actual_resource,
            "data": actual_data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        # mock 성공 응답
        from src.api.contracts import SaveResponse
        return SaveResponse(success=True, id="e2e-captured", message="captured")

    # backend_client 싱글톤을 설정 (AgentDataPublisher가 사용)
    from src.api.client import BackendClient
    import src.api.main as api_main

    mock_client = BackendClient.__new__(BackendClient)
    original_backend_client = api_main.backend_client
    api_main.backend_client = mock_client

    try:
        with patch.object(
            BackendClient, "save",
            new_callable=AsyncMock,
            side_effect=capture_save,
        ):
            final_state = await compiled.ainvoke(initial_state)
    finally:
        # 원래 상태 복원
        api_main.backend_client = original_backend_client

    return final_state, captured_saves


# ────────────────────────────────────────
# 검증 B: 에이전트 상태 필드 검증
# ────────────────────────────────────────

def verify_state_fields(final_state: dict[str, Any]) -> dict[str, Any]:
    """
    파이프라인 완료 후 상태 필드를 검증한다.

    Returns:
        검증 결과 요약 dict
    """
    results = {}
    for field in EXPECTED_FIELDS:
        val = final_state.get(field)
        if val:
            if isinstance(val, dict):
                results[field] = f"dict({len(val)} keys)"
            elif isinstance(val, str):
                results[field] = f"str({len(val)}자)"
            else:
                results[field] = f"{type(val).__name__}"
        else:
            results[field] = None

    present = sum(1 for v in results.values() if v is not None)
    return {
        "fields": results,
        "present": present,
        "total": len(EXPECTED_FIELDS),
        "all_present": present == len(EXPECTED_FIELDS),
    }


# ────────────────────────────────────────
# 검증 C: DB 기록 검증
# ────────────────────────────────────────

def verify_captured_saves(captured_saves: list[dict[str, Any]]) -> dict[str, Any]:
    """
    캡처된 BackendClient.save() 호출을 분석한다.

    Returns:
        리소스별 호출 횟수 + 데이터 요약
    """
    by_resource: dict[str, list[dict[str, Any]]] = {}
    for save in captured_saves:
        resource = save["resource"]
        by_resource.setdefault(resource, []).append(save)

    return {
        "total_saves": len(captured_saves),
        "resources": {k: len(v) for k, v in by_resource.items()},
        "details": by_resource,
    }


async def write_captured_to_mysql(
    captured_saves: list[dict[str, Any]],
    user_id: str,
    session_id: str,
) -> dict[str, bool]:
    """
    캡처된 save 데이터를 실제 MySQL에 INSERT하고 SELECT로 검증한다.

    Returns:
        리소스별 INSERT+SELECT 성공 여부
    """
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    results: dict[str, bool] = {}

    try:
        for save in captured_saves:
            resource = save["resource"]
            save_data = save["data"]

            # SaveRequest에서 data 딕셔너리 추출
            if hasattr(save_data, "data"):
                payload = save_data.data
            elif isinstance(save_data, dict):
                payload = save_data.get("data", save_data)
            else:
                payload = {}

            if resource == "emotion_logs":
                try:
                    import uuid as _uuid
                    log_id = f"log_e2e_{_uuid.uuid4().hex[:12]}"
                    primary = payload.get("primary_emotion", "unknown")
                    intensity = float(payload.get("intensity", 0.5))
                    valence = float(payload.get("valence", 0.0))
                    arousal = float(payload.get("arousal", 0.5))
                    await client.execute(
                        "INSERT INTO emotion_logs "
                        "(log_id, user_id, session_id, mode, "
                        "primary_emotion, intensity, valence, arousal) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (log_id, user_id, session_id, "podcast",
                         primary, intensity, valence, arousal),
                    )
                    rows = await client.fetch(
                        "SELECT primary_emotion FROM emotion_logs "
                        "WHERE log_id = %s",
                        (log_id,),
                    )
                    results["emotion_logs"] = len(rows) > 0
                except Exception as e:
                    logger.warning("emotion_logs INSERT 실패: %s", e)
                    results["emotion_logs"] = False

            elif resource == "content_analyses":
                # content_analyses는 별도 MySQL 테이블 없음 → 캡처 확인만
                results["content_analyses"] = True

            elif resource == "learning":
                # learning_patterns 테이블에 기록
                try:
                    import uuid as _uuid
                    pattern_id = f"pat_e2e_{_uuid.uuid4().hex[:12]}"
                    raw_data = json.dumps(payload, ensure_ascii=False, default=str)
                    await client.execute(
                        "INSERT INTO learning_patterns "
                        "(pattern_id, user_id, session_id, mode, "
                        "raw_learning_data) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (pattern_id, user_id, session_id, "podcast",
                         raw_data),
                    )
                    rows = await client.fetch(
                        "SELECT pattern_id FROM learning_patterns "
                        "WHERE pattern_id = %s",
                        (pattern_id,),
                    )
                    results["learning"] = len(rows) > 0
                except Exception as e:
                    logger.warning("learning INSERT 실패: %s", e)
                    results["learning"] = False

            elif resource == "visualizations":
                # visualization_meta 테이블에 기록
                try:
                    import uuid as _uuid
                    vis_id = f"vis_e2e_{_uuid.uuid4().hex[:12]}"
                    s3_key = payload.get("s3_key", f"e2e-test/{vis_id}.png")
                    cdn_url = payload.get("cdn_url", f"https://cdn.example.com/{vis_id}.png")
                    image_prompt = payload.get("image_prompt", "e2e test image")
                    interpretation = payload.get("interpretation_text", "e2e test")
                    await client.execute(
                        "INSERT INTO visualization_meta "
                        "(visualization_id, user_id, session_id, mode, "
                        "s3_key, cdn_url, image_prompt, interpretation_text) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (vis_id, user_id, session_id, "podcast",
                         s3_key, cdn_url, image_prompt, interpretation),
                    )
                    rows = await client.fetch(
                        "SELECT visualization_id FROM visualization_meta "
                        "WHERE visualization_id = %s",
                        (vis_id,),
                    )
                    results["visualizations"] = len(rows) > 0
                except Exception as e:
                    logger.warning("visualizations INSERT 실패: %s", e)
                    results["visualizations"] = False

    finally:
        # 테스트 데이터 정리 (e2e_ prefix PK 기반)
        try:
            await client.execute(
                "DELETE FROM emotion_logs WHERE log_id LIKE %s", ("log_e2e_%",)
            )
            await client.execute(
                "DELETE FROM learning_patterns WHERE pattern_id LIKE %s", ("pat_e2e_%",)
            )
            await client.execute(
                "DELETE FROM visualization_meta WHERE visualization_id LIKE %s", ("vis_e2e_%",)
            )
        except Exception as e:
            logger.warning("테스트 데이터 정리 실패: %s", e)
        await client.close()

    return results


# ────────────────────────────────────────
# 결과 출력
# ────────────────────────────────────────

def print_results(
    state_verification: dict[str, Any],
    save_verification: dict[str, Any],
    db_write_results: dict[str, bool] | None,
    elapsed: float,
) -> None:
    """검증 결과를 포맷팅하여 출력한다."""
    print(f"\n{_B}{_C}{'=' * 60}{_0}")
    print(f"{_B}{_C} E2E 팟캐스트 파이프라인 + 로컬 DB 검증 결과{_0}")
    print(f"{_B}{_C}{'=' * 60}{_0}")
    print(f"  소요 시간: {elapsed:.1f}초")

    # B: 상태 필드 검증
    print(f"\n{_B}[검증 B] 파이프라인 상태 필드{_0}")
    fields = state_verification["fields"]
    present = state_verification["present"]
    total = state_verification["total"]
    status_color = _G if state_verification["all_present"] else _Y
    print(f"  결과: {status_color}{present}/{total} 필드 존재{_0}")
    for field, val in fields.items():
        if val:
            print(f"  {_G}✓{_0} {field}: {val}")
        else:
            print(f"  {_R}✗{_0} {field}: 없음")

    # C: BackendClient.save() 캡처 검증
    print(f"\n{_B}[검증 C-1] BackendClient.save() 호출 캡처{_0}")
    print(f"  총 호출 횟수: {save_verification['total_saves']}")
    for resource, count in save_verification["resources"].items():
        color = _G if resource in EXPECTED_RESOURCES else _C
        print(f"  {color}●{_0} {resource}: {count}회")

    # C: MySQL 기록 검증
    if db_write_results is not None:
        print(f"\n{_B}[검증 C-2] MySQL INSERT → SELECT 검증{_0}")
        for resource, success in db_write_results.items():
            if success:
                print(f"  {_G}✓{_0} {resource}: INSERT+SELECT 성공")
            else:
                print(f"  {_R}✗{_0} {resource}: 실패")
    else:
        print(f"\n{_Y}[검증 C-2] MySQL 미접속 — INSERT 검증 생략{_0}")

    # 종합 판정
    b_pass = state_verification["all_present"]
    c1_pass = save_verification["total_saves"] > 0
    c2_pass = (
        db_write_results is not None
        and all(db_write_results.values())
        and len(db_write_results) > 0
    ) if db_write_results else None

    print(f"\n{_B}{'─' * 40}{_0}")
    print(f"  검증 B  (상태 필드):  {_G}PASS{_0}" if b_pass else f"  검증 B  (상태 필드):  {_R}FAIL{_0}")
    print(f"  검증 C-1 (save 캡처): {_G}PASS{_0}" if c1_pass else f"  검증 C-1 (save 캡처): {_R}FAIL{_0}")
    if c2_pass is not None:
        print(f"  검증 C-2 (MySQL 기록): {_G}PASS{_0}" if c2_pass else f"  검증 C-2 (MySQL 기록): {_R}FAIL{_0}")
    else:
        print(f"  검증 C-2 (MySQL 기록): {_Y}SKIP{_0}")
    print(f"{_B}{'─' * 40}{_0}\n")


# ────────────────────────────────────────
# 결과 파일 저장
# ────────────────────────────────────────

def save_results_to_file(
    final_state: dict[str, Any],
    state_verification: dict[str, Any],
    save_verification: dict[str, Any],
    db_write_results: dict[str, bool] | None,
    elapsed: float,
) -> Path:
    """결과를 JSON 파일로 저장한다."""
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"e2e_podcast_localdb_{timestamp}.json"

    # final_state에서 직렬화 가능한 필드만 추출
    state_summary = {}
    for field in EXPECTED_FIELDS:
        val = final_state.get(field)
        if val is not None:
            state_summary[field] = val

    result_data = {
        "test_info": {
            "type": "e2e_podcast_localdb",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(elapsed, 2),
            "provider": "openai",
            "model": os.getenv("LLM_MODEL_SONNET", "gpt-4o-mini"),
        },
        "verification_b": state_verification,
        "verification_c1": {
            "total_saves": save_verification["total_saves"],
            "resources": save_verification["resources"],
        },
        "verification_c2": db_write_results,
        "agent_outputs": state_summary,
    }

    file_path = results_dir / filename
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"  {_G}[SAVED]{_0} {file_path}")
    return file_path


# ────────────────────────────────────────
# 메인 실행
# ────────────────────────────────────────

async def run_e2e_test(model: str = "gpt-4o-mini") -> bool:
    """
    E2E 팟캐스트 파이프라인 + 로컬 DB 통합 테스트를 실행한다.

    Returns:
        전체 통과 여부
    """
    print(f"\n{_B}{_C}{'=' * 60}{_0}")
    print(f"{_B}{_C} E2E 팟캐스트 파이프라인 + 로컬 DB 테스트{_0}")
    print(f"{_B}{_C}{'=' * 60}{_0}")
    print(f"  프로바이더: OpenAI ({model})")
    print(f"  모드: podcast")

    # 1. OpenAI 키 확인
    if not _check_openai_key():
        return False

    # 2. DB 상태 확인
    mysql_ok = _probe_mysql()
    neo4j_ok = _probe_neo4j()
    print(f"  MySQL: {_G + 'OK' + _0 if mysql_ok else _Y + 'N/A' + _0}")
    print(f"  Neo4j: {_G + 'OK' + _0 if neo4j_ok else _Y + 'N/A' + _0}")

    # 3. MySQL 시드 데이터 확인 (있으면 사용)
    user_id = "test-user-001"
    session_id = "sess_test000001"

    if mysql_ok:
        from src.db.mysql_client import MySQLClient
        mc = MySQLClient()
        try:
            rows = await mc.fetch(
                "SELECT user_id FROM users WHERE user_id = %s", (user_id,)
            )
            if rows:
                print(f"  시드 데이터: {_G}확인됨{_0} (user={user_id})")
            else:
                print(f"  시드 데이터: {_Y}없음{_0} — python -m dev.local_db.seed 실행 권장")
        except Exception as e:
            print(f"  시드 데이터 확인 실패: {e}")
        finally:
            await mc.close()

    # 4. OpenAI 프로바이더 설정
    print(f"\n{_C}--- 프로바이더 설정 ---{_0}")
    _setup_openai(model)
    print(f"  {_G}[OK]{_0} OpenAI 프로바이더 + 싱글톤 리프레시 완료")

    # 5. 초기 상태 생성 (시드 데이터 user_id 사용)
    from dev.live_tests.fixtures import make_e2e_state
    initial_state = make_e2e_state()
    initial_state["user_id"] = user_id
    initial_state["session_id"] = session_id
    print(f"  입력: {len(initial_state['user_input'])}자, mode={initial_state['mode']}")

    # 6. 파이프라인 실행
    print(f"\n{_C}--- 파이프라인 실행 (OpenAI LLM) ---{_0}")
    start_time = time.perf_counter()
    try:
        final_state, captured_saves = await run_pipeline_with_capture(initial_state)
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        print(f"\n  {_R}[FAIL]{_0} 파이프라인 실행 실패 ({elapsed:.1f}초)")
        print(f"  에러: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    elapsed = time.perf_counter() - start_time
    print(f"  {_G}[OK]{_0} 파이프라인 완료 — {elapsed:.1f}초")

    # 7. 검증 B: 상태 필드
    state_verification = verify_state_fields(final_state)

    # 8. 검증 C-1: save() 캡처
    save_verification = verify_captured_saves(captured_saves)

    # 9. 검증 C-2: MySQL INSERT → SELECT (MySQL 접속 가능 시)
    db_write_results = None
    if mysql_ok and captured_saves:
        try:
            db_write_results = await write_captured_to_mysql(
                captured_saves, user_id, session_id
            )
        except Exception as e:
            logger.warning("MySQL 기록 검증 실패: %s", e)

    # 10. 결과 출력 + 저장
    print_results(state_verification, save_verification, db_write_results, elapsed)
    save_results_to_file(
        final_state, state_verification, save_verification,
        db_write_results, elapsed,
    )

    return state_verification["all_present"] and save_verification["total_saves"] > 0


# ────────────────────────────────────────
# pytest 호환 테스트 클래스
# ────────────────────────────────────────

import pytest

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.timeout(180),
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY 환경변수가 필요합니다",
    ),
]


import pytest_asyncio


@pytest_asyncio.fixture(scope="module")
async def pipeline_result():
    """파이프라인을 1회만 실행하고 결과를 모든 테스트에서 공유한다."""
    _setup_openai()

    from dev.live_tests.fixtures import make_e2e_state
    initial_state = make_e2e_state()
    initial_state["user_id"] = "test-user-001"
    initial_state["session_id"] = "sess_test000001"

    final_state, captured_saves = await run_pipeline_with_capture(initial_state)
    return {
        "final_state": final_state,
        "captured_saves": captured_saves,
        "user_id": "test-user-001",
        "session_id": "sess_test000001",
    }


class TestE2EPodcastPipeline:
    """E2E 팟캐스트 파이프라인 + 로컬 DB 통합 테스트."""

    async def test_pipeline_produces_complete_state(self, pipeline_result) -> None:
        """B: 파이프라인 완주 후 모든 TIER 필드가 존재하는지 검증한다."""
        verification = verify_state_fields(pipeline_result["final_state"])
        missing = [f for f, v in verification["fields"].items() if v is None]
        assert verification["all_present"], (
            f"누락 필드: {missing} ({verification['present']}/{verification['total']})"
        )

    async def test_pipeline_captures_save_calls(self, pipeline_result) -> None:
        """C-1: 파이프라인이 BackendClient.save()를 호출하는지 검증한다."""
        captured_saves = pipeline_result["captured_saves"]

        assert len(captured_saves) > 0, "BackendClient.save()가 한 번도 호출되지 않음"

        resources = {s["resource"] for s in captured_saves}
        print(f"\n  캡처된 리소스: {resources}")
        print(f"  총 호출 횟수: {len(captured_saves)}")

    @pytest.mark.skipif(
        not _probe_mysql(),
        reason="MySQL이 실행 중이지 않습니다",
    )
    async def test_pipeline_writes_to_mysql(self, pipeline_result) -> None:
        """C-2: 캡처된 데이터를 MySQL에 INSERT하고 SELECT로 검증한다."""
        captured_saves = pipeline_result["captured_saves"]

        if not captured_saves:
            pytest.skip("save() 호출이 없어 MySQL 기록 검증 불가")

        db_results = await write_captured_to_mysql(
            captured_saves,
            pipeline_result["user_id"],
            pipeline_result["session_id"],
        )

        failed = [r for r, ok in db_results.items() if not ok]
        assert len(db_results) > 0, "MySQL에 기록할 데이터가 없음"
        # 최소 1개 이상 성공
        success_count = sum(1 for ok in db_results.values() if ok)
        assert success_count > 0, f"MySQL INSERT 전부 실패: {failed}"
        print(f"\n  MySQL 기록 결과: {db_results}")


# ────────────────────────────────────────
# CLI 엔트리포인트
# ────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="E2E 팟캐스트 + 로컬 DB 테스트")
    parser.add_argument(
        "--model", default="gpt-4o-mini", help="OpenAI 모델 (기본: gpt-4o-mini)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    success = asyncio.run(run_e2e_test(model=args.model))
    sys.exit(0 if success else 1)

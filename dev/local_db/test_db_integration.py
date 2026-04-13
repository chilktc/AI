"""
로컬 DB 통합 테스트.

Docker DB + 시드 데이터가 필요하며, 미실행 시 자동 skip된다.
기존 src/ 코드를 수정하지 않고, 에이전트가 사용하는 쿼리 패턴을 실제 DB에서 검증한다.

실행:
    pytest dev/local_db/test_db_integration.py -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from dev.local_db.conftest import requires_all_db, requires_mysql, requires_neo4j

pytestmark = pytest.mark.asyncio


@requires_mysql
class TestMySQLAgentQueries:
    """에이전트가 사용하는 MySQL 쿼리 패턴을 실제 DB에서 검증한다."""

    async def test_user_profile_lookup(self, mysql_client) -> None:
        """ScriptPersonalizer 패턴: 사용자 프로필 조회."""
        rows = await mysql_client.fetch(
            "SELECT user_id, age_group, preferred_style, preferred_attitude "
            "FROM users WHERE user_id = %s",
            ("test-user-001",),
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["age_group"] == "30s"
        assert row["preferred_style"] == "warm"
        assert row["preferred_attitude"] == "supportive"

    async def test_learning_pattern_insert_and_query(self, mysql_client) -> None:
        """LearningAgent 패턴: learning_patterns INSERT 후 SELECT 검증."""
        pattern_id = "lp-inttest-001"
        try:
            await mysql_client.execute(
                "INSERT INTO learning_patterns "
                "(pattern_id, session_id, user_id, mode, "
                "preferred_topics, emotional_patterns, interaction_style, "
                "personalization_suggestions, effectiveness_score, "
                "raw_learning_data, trace_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    pattern_id,
                    "sess_test000001",
                    "test-user-001",
                    "podcast",
                    json.dumps(["테스트토픽"]),
                    json.dumps(["패턴1"]),
                    "detailed",
                    json.dumps(["제안1"]),
                    0.80,
                    json.dumps({"test": True}),
                    "trace_inttest_001",
                ),
            )

            rows = await mysql_client.fetch(
                "SELECT pattern_id, session_id, user_id, effectiveness_score "
                "FROM learning_patterns "
                "WHERE user_id = %s ORDER BY created_at DESC",
                ("test-user-001",),
            )
            assert len(rows) >= 1
            # 방금 삽입한 레코드가 존재하는지 확인
            inserted = [r for r in rows if r["pattern_id"] == pattern_id]
            assert len(inserted) == 1
            assert inserted[0]["session_id"] == "sess_test000001"
            assert float(inserted[0]["effectiveness_score"]) == pytest.approx(0.80)
        finally:
            await mysql_client.execute(
                "DELETE FROM learning_patterns WHERE pattern_id = %s",
                (pattern_id,),
            )

    async def test_flattened_episode_query(self, mysql_client) -> None:
        """v3.1 Flattening: 에피소드 단건 조회 (본문 포함)."""
        rows = await mysql_client.fetch(
            "SELECT episode_id, episode_title, script_text, tts_markers_json "
            "FROM podcast_episodes "
            "WHERE episode_id = %s",
            ("ep-test-001",),
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["episode_title"]
        assert row["script_text"]
        assert isinstance(json.loads(row["tts_markers_json"]), list)

    async def test_emotion_log_query(self, mysql_client) -> None:
        """EmotionAgent 패턴: 감정 로그 조회."""
        rows = await mysql_client.fetch(
            "SELECT log_id, primary_emotion, intensity, valence, arousal, "
            "secondary_emotions "
            "FROM emotion_logs "
            "WHERE user_id = %s AND session_id = %s",
            ("test-user-001", "sess_test000001"),
        )
        assert len(rows) >= 1
        row = rows[0]
        assert row["primary_emotion"] == "anxiety"
        assert 0 <= float(row["intensity"]) <= 1
        assert -1 <= float(row["valence"]) <= 1

    async def test_visualization_meta_query(self, mysql_client) -> None:
        """VisualizationAgent 패턴: 시각화 메타데이터 조회."""
        rows = await mysql_client.fetch(
            "SELECT visualization_id, s3_key, cdn_url, image_prompt "
            "FROM visualization_meta "
            "WHERE user_id = %s AND episode_id = %s",
            ("test-user-001", "ep-test-001"),
        )
        assert len(rows) >= 1
        row = rows[0]
        assert row["s3_key"].startswith("vis/")
        assert row["image_prompt"]  # 비어있지 않음

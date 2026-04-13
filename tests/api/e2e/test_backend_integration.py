"""
백엔드 API 연동 E2E 테스트.

BackendClient의 save/load 메서드를 실제 Backend 서버(app-3)에
대해 실행하여 데이터 저장/조회가 정상 동작하는지 검증한다.

현재 상태: 스켈레톤 (API 명세 미확정)
    - 백엔드팀과 API 명세서 교환 후 각 테스트의 pytest.skip 해제
    - TODO(backend) 마커가 해결된 리소스 경로부터 순차 활성화

실행 방법:
    pytest tests/api/e2e/test_backend_integration.py -v -m live \\
        --backend-url=http://<BACKEND_IP>:8080
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.api.contracts import LoadResponse, SaveRequest, SaveResponse

# ---------------------------------------------------------------------------
# 확정된 리소스: Learning
# (src/api/backend_resources.py에서 유일하게 TODO 마커 없음)
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestBackendLearningApi:
    """Learning 리소스 save/load 통합 테스트.

    리소스 경로: POST/GET /api/learning
    참조: src/api/backend_resources.py → RESOURCE_LEARNING = "learning"
    """

    @pytest.mark.asyncio
    async def test_save_learning_data(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """POST /api/learning → SaveResponse 반환."""
        # TODO(backend): API 명세 확정 후 skip 해제 및 구현
        pytest.skip(
            "백엔드 API 명세 미확정 — " "백엔드팀과 /api/learning 엔드포인트 스키마 확정 후 활성화"
        )

        request = SaveRequest(
            user_id="test_user_e2e",
            session_id="sess_e2e_001",
            type="learning",
            data={
                "topic": "스트레스 관리",
                "insights": ["인사이트1"],
                "source_agent": "learning_agent",
            },
            timestamp=datetime.now(timezone.utc),
        )

        result = await real_backend_client.save("learning", request)

        assert isinstance(result, SaveResponse)
        assert result.success is True
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_load_learning_data(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """GET /api/learning?user_id=... → LoadResponse 반환."""
        # TODO(backend): API 명세 확정 후 skip 해제 및 구현
        pytest.skip(
            "백엔드 API 명세 미확정 — " "백엔드팀과 /api/learning 엔드포인트 스키마 확정 후 활성화"
        )

        result = await real_backend_client.load(
            "learning",
            user_id="test_user_e2e",
        )

        assert isinstance(result, LoadResponse)
        assert result.success is True
        assert isinstance(result.data, list)


# ---------------------------------------------------------------------------
# 미확정 리소스: Conversations, Emotion Logs 등
# (src/api/backend_resources.py에 TODO(backend) 마커 존재)
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestBackendConversationApi:
    """Conversation 리소스 save/load 통합 테스트.

    리소스 경로: TODO(backend) 4-2 경로명 확정 필요
    현재 예상: POST/GET /api/conversations
    """

    @pytest.mark.asyncio
    async def test_save_conversation_data(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """POST /api/conversations → SaveResponse."""
        # TODO(backend): 4-2 리소스 경로명 확정 후 skip 해제
        pytest.skip(
            "리소스 경로 미확정 — " "src/api/backend_resources.py RESOURCE_CONVERSATION 확정 필요"
        )

        request = SaveRequest(
            user_id="test_user_e2e",
            session_id="sess_e2e_002",
            type="conversation",
            data={
                "turn": 1,
                "user_message": "안녕하세요",
                "ai_response": "반갑습니다!",
            },
            timestamp=datetime.now(timezone.utc),
        )

        result = await real_backend_client.save("conversations", request)

        assert isinstance(result, SaveResponse)
        assert result.success is True


@pytest.mark.live
class TestBackendEmotionLogApi:
    """Emotion Log 리소스 save 통합 테스트.

    리소스 경로: TODO(backend) 4-2 경로명 확정 필요
    현재 예상: POST /api/emotion_logs
    """

    @pytest.mark.asyncio
    async def test_save_emotion_log(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """POST /api/emotion_logs → SaveResponse."""
        # TODO(backend): 4-2 리소스 경로명 확정 후 skip 해제
        pytest.skip(
            "리소스 경로 미확정 — " "src/api/backend_resources.py RESOURCE_EMOTION_LOG 확정 필요"
        )

        request = SaveRequest(
            user_id="test_user_e2e",
            session_id="sess_e2e_003",
            type="emotion_log",
            data={
                "primary_emotion": "calm",
                "intensity": 0.6,
                "valence": 0.3,
            },
            timestamp=datetime.now(timezone.utc),
        )

        result = await real_backend_client.save("emotion_logs", request)

        assert isinstance(result, SaveResponse)
        assert result.success is True


# ---------------------------------------------------------------------------
# 왕복 테스트: Save → Load → 데이터 일치 확인
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestBackendRoundTrip:
    """데이터 저장 후 조회하여 일치 여부를 확인하는 왕복 테스트."""

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """Save → Load → 저장한 데이터와 조회한 데이터가 일치."""
        # TODO(backend): API 명세 확정 후 skip 해제
        pytest.skip("API 명세 미확정 — " "Save/Load 왕복 테스트는 엔드포인트 스키마 확정 후 활성화")

        # 1. 저장
        test_data = {
            "topic": "E2E 왕복 테스트",
            "test_marker": "roundtrip_test_001",
        }
        save_request = SaveRequest(
            user_id="test_user_roundtrip",
            session_id="sess_roundtrip_001",
            type="learning",
            data=test_data,
            timestamp=datetime.now(timezone.utc),
        )
        save_result = await real_backend_client.save("learning", save_request)
        assert save_result.success is True

        # 2. 조회
        load_result = await real_backend_client.load(
            "learning",
            user_id="test_user_roundtrip",
            type="learning",
        )
        assert load_result.success is True
        assert load_result.total >= 1

        # 3. 일치 확인
        found = any(item.get("test_marker") == "roundtrip_test_001" for item in load_result.data)
        assert found, "저장한 데이터를 조회 결과에서 찾을 수 없습니다."


# ---------------------------------------------------------------------------
# 에러 핸들링 테스트
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestBackendErrorHandling:
    """Backend 서버 에러 응답 처리 검증."""

    @pytest.mark.asyncio
    async def test_save_invalid_data_returns_error(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """잘못된 데이터 전송 시 적절한 에러 응답."""
        # TODO(backend): API 명세 확정 후 skip 해제
        pytest.skip("API 명세 미확정 — " "에러 응답 형식(ErrorResponse) 확정 후 활성화")

        # 의도적으로 필수 필드를 비정상값으로 설정
        request = SaveRequest(
            user_id="",  # 빈 user_id
            session_id="",
            type="",
            data={},
            timestamp=datetime.now(timezone.utc),
        )

        import httpx

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await real_backend_client.save("learning", request)

        # 4xx 에러 (클라이언트 오류)
        assert 400 <= exc_info.value.response.status_code < 500

    @pytest.mark.asyncio
    async def test_load_nonexistent_user(
        self,
        skip_if_no_backend: None,
        real_backend_client,
    ) -> None:
        """존재하지 않는 user_id 조회 시 빈 결과 반환."""
        # TODO(backend): API 명세 확정 후 skip 해제
        pytest.skip("API 명세 미확정 — " "존재하지 않는 사용자 조회 응답 형식 확정 후 활성화")

        result = await real_backend_client.load(
            "learning",
            user_id="nonexistent_user_99999",
        )

        assert isinstance(result, LoadResponse)
        assert result.data == []
        assert result.total == 0

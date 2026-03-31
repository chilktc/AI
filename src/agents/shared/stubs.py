"""
독립 에이전트 Stub — 통합 전 임시 인터페이스.

Reasoning 계열 에이전트가 조건부로 호출하는 독립 에이전트의 stub 구현.
- Episode Memory (개발자2) — 팟캐스트모드
- Knowledge Agent (개발자1) — 대화모드 + 팟캐스트모드
- Memory Agent (개발자2) — 대화모드

git main 통합 시 실제 에이전트로 교체한다.

인터페이스 계약:
    - search(query, ...) -> dict
    - 반환 형식은 실제 에이전트와 동일
"""

from __future__ import annotations


class EpisodeMemoryStub:
    """
    Episode Memory Agent의 stub 구현.

    실제 에이전트는 Pinecone 벡터 검색 + MySQL 메타데이터를 사용하지만,
    stub은 빈 결과를 반환한다.

    인터페이스 계약:
        async def search(query: str, user_id: str) -> dict
    """

    async def search(self, query: str, user_id: str) -> dict:
        """
        에피소드 기억 검색 (stub — 빈 결과 반환).

        Args:
            query: 검색 쿼리
            user_id: 사용자 ID

        Returns:
            빈 검색 결과 dict
        """
        return {
            "episodes": [],
            "relevance_scores": [],
        }


class KnowledgeAgentStub:
    """
    Knowledge Agent의 stub 구현.

    실제 에이전트는 전문 지식 벡터 DB를 검색하지만,
    stub은 빈 결과를 반환한다.

    인터페이스 계약:
        async def search(query: str, domain: str) -> dict
    """

    async def search(
        self,
        query: str,
        domain: str = "mental_health",
    ) -> dict:
        """
        전문 지식 검색 (stub — 빈 결과 반환).

        Args:
            query: 검색 쿼리
            domain: 지식 도메인 (기본: mental_health)

        Returns:
            빈 검색 결과 dict
        """
        return {
            "articles": [],
            "guidelines": [],
        }



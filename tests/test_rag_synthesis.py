import asyncio
import os
import json
from dotenv import load_dotenv
from src.agents.podcast.knowledge import KnowledgeAgent

async def test_rag_flow():
    load_dotenv()
    
    # 1. 에이전트 생성
    agent = KnowledgeAgent()
    
    # 2. 백엔드 API가 없는 상황을 대비해 원문 조회 로직을 살짝 가로챕니다 (테스트용)
    # 실제 RDB에 데이터가 없더라도 Pinecone에서 찾은 ID를 바탕으로 가짜 텍스트를 넣어 생성이 되는지 확인합니다.
    async def mock_fetch(chunk_ids):
        print(f"🔗 [DEBUG] Pinecone에서 찾은 ID들: {chunk_ids}")
        return [
            {
                "id": cid,
                "title": "테스트 문서",
                "content": "이 내용은 백엔드 RDB 대신 테스트용으로 주입된 텍스트입니다. CBT(인지행동치료)는 사고의 변화를 통해 감정과 행동을 교정하는 치료법입니다.",
                "domain": "mental_health",
                "source": "test_pdf"
            } for cid in chunk_ids
        ]

    # 테스트를 위해 임시로 교체
    agent._fetch_documents_from_backend = mock_fetch

    # 3. 질문 던지기
    user_query = "개인 상담의 효과에 대해서 설명해줄래?"
    print(f"\n🙋 질문: {user_query}")
    print("-" * 50)

    # 4. RAG 실행
    # (Parser -> Embedding -> Pinecone -> TextGen)
    result = await agent.search(query=user_query, domain="personal_counsel")

    # 5. 결과 확인
    articles = result.get("articles", [])
    for article in articles:
        if article.get("id") == "_synthesis":
            print(f"🤖 [Qwen3의 전문 지식 요약 결과]")
            print(article.get("content"))
            print("-" * 50)
        else:
            print(f"🔍 [검색된 근거 ID]: {article.get('id')} (Score: {article.get('score'):.4f})")

if __name__ == "__main__":
    asyncio.run(test_rag_flow())

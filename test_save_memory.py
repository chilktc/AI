import asyncio
from src.agents.podcast.episode_memory import episode_memory_agent

async def test_save_and_verify():
    print("🚀 [Memory Upsert] 저장 기능 테스트 시작...")
    
    # 1. 저장할 새로운 데이터
    new_text = "오늘 KT Cloud RAG Suite 연동에 드디어 성공했다! 팀원들과 맛있는 걸 먹으러 가야지."
    new_meta = {"category": "achievement", "feeling": "happy"}

    # 2. 저장 실행
    success = await episode_memory_agent._save_to_store(new_text, new_meta)

    if success:
        print("\n" + "="*50)
        print("🎉 축하합니다! 새로운 기억이 저장되었습니다.")
        print("이제 mock_db.json 파일을 열어서 마지막 줄을 확인해 보세요.")
        print("="*50)
    else:
        print("❌ 저장에 실패했습니다.")

if __name__ == "__main__":
    asyncio.run(test_save_and_verify())
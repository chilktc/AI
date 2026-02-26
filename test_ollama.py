import asyncio
import os

from openai import AsyncOpenAI


async def main():
    os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
    os.environ["OPENAI_API_KEY"] = "ollama"

    client = AsyncOpenAI()
    try:
        response = await client.chat.completions.create(
            model="gpt-oss:20b", messages=[{"role": "user", "content": "Hello"}]
        )
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"Error: {e}")


asyncio.run(main())

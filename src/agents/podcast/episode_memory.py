import os
import httpx
import hashlib
import datetime
from typing import Any

from src.agents.shared.base_memory import BaseMemoryAgent
from src.models.agent_state import AgentState

_CHUNK_SIZE = 400
_CHUNK_OVERLAP = 50
_TOP_K = 5
_SCORE_THRESHOLD = 0.7


class EpisodeMemoryAgent(BaseMemoryAgent):

    def __init__(self) -> None:
        super().__init__(
            name="episode_memory",
            output_key="memory_results",
            namespace="mem_podcast_episode",  # base namespace (prefix 개념)
        )

        self.query_endpoint = os.getenv("KT_CLOUD_QUERY_ENDPOINT", "")
        self.query_token = os.getenv("KT_CLOUD_QUERY_TOKEN", "")

        self.passage_endpoint = os.getenv("KT_CLOUD_PASSAGE_ENDPOINT", "")
        self.passage_token = os.getenv("KT_CLOUD_PASSAGE_TOKEN", "")

        self.textgen_endpoint = os.getenv("KT_CLOUD_TEXTGEN_ENDPOINT", "")
        self.textgen_token = os.getenv("KT_CLOUD_TEXTGEN_TOKEN", "")

        self.pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
        self.pinecone_index_name = os.getenv("PINECONE_INDEX_EPISODE", "")

        self.pinecone_host = ""

    # ============================================================
    # namespace 생성 (핵심 추가)
    # ============================================================
    def _build_namespace(self, user_id: str) -> str:
        return f"{self._namespace}_{user_id}"

    # ============================================================
    # MAIN PROCESS
    # ============================================================
    async def process(self, state: AgentState) -> dict[str, Any]:
        user_id = str(state.get("user_id", "anonymous"))
        query = state.get("memory_query") or str(state.get("user_input", ""))

        namespace = self._build_namespace(user_id)

        items = await self._retrieve_from_store(query, namespace)

        if not items:
            return await super().process(state)

        summary = await self._generate_summary(query, items)

        return {
            "memory_results": {
                "items": items,
                "summary": summary,
            }
        }

    # ============================================================
    # SAVE
    # ============================================================
    async def _save_to_store(self, text: str, metadata: dict | None = None) -> bool:
        if not text.strip():
            return False

        user_id = str((metadata or {}).get("user_id", "anonymous"))
        namespace = self._build_namespace(user_id)

        chunks = self._split(text)

        for i, chunk in enumerate(chunks):
            vec = await self._embed(chunk, "embedding-passage")
            if not vec:
                continue

            await self._upsert(
                id=self._make_id(text, i),
                vector=vec,
                metadata={
                    "text": chunk,
                    "date": datetime.datetime.now().isoformat(),
                    "user_id": user_id,  # 핵심 추가
                    **(metadata or {})
                },
                namespace=namespace
            )
        return True

    # ============================================================
    # RETRIEVE
    # ============================================================
    async def _retrieve_from_store(self, query: str, namespace: str) -> list[dict]:
        if not query.strip():
            return []

        vec = await self._embed(query, "embedding-query")
        if not vec:
            return []

        return await self._query(vec, namespace)

    # ============================================================
    # EMBEDDING
    # ============================================================
    async def _embed(self, text: str, mode: str) -> list[float]:
        if mode == "embedding-query":
            endpoint = self.query_endpoint
            token = self.query_token
        else:
            endpoint = self.passage_endpoint
            token = self.passage_token

        if not endpoint or not token:
            return []

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {token}"},
                    json={"input": text},
                    timeout=10.0,
                )
                r.raise_for_status()

                data = r.json().get("data", [])
                if not data:
                    return []

                return data[0].get("embedding", [])

            except Exception as e:
                print(f"[Embedding error] {e}")
                return []

    # ============================================================
    # PINECONE HOST
    # ============================================================
    async def _get_host(self):
        if self.pinecone_host:
            return self.pinecone_host

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.pinecone.io/indexes/{self.pinecone_index_name}",
                    headers={"Api-Key": self.pinecone_api_key},
                    timeout=10.0,
                )
                r.raise_for_status()
                self.pinecone_host = r.json()["host"]
                return self.pinecone_host
        except Exception as e:
            print(f"[Pinecone host error] {e}")
            return ""

    # ============================================================
    # UPSERT (namespace 추가)
    # ============================================================
    async def _upsert(self, id: str, vector: list[float], metadata: dict, namespace: str):
        host = await self._get_host()
        if not host:
            return

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://{host}/vectors/upsert",
                    headers={"Api-Key": self.pinecone_api_key},
                    json={
                        "vectors": [{
                            "id": id,
                            "values": vector,
                            "metadata": metadata
                        }],
                        "namespace": namespace  # 핵심 추가
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
        except Exception as e:
            print(f"[Upsert error] {e}")

    # ============================================================
    # QUERY (namespace + 가공)
    # ============================================================
    async def _query(self, vector: list[float], namespace: str) -> list[dict]:
        host = await self._get_host()
        if not host:
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://{host}/query",
                    headers={"Api-Key": self.pinecone_api_key},
                    json={
                        "vector": vector,
                        "topK": _TOP_K,
                        "includeMetadata": True,
                        "namespace": namespace  # 핵심 추가
                    },
                    timeout=10.0,
                )
                r.raise_for_status()

                matches = r.json().get("matches", [])

                results = []
                for m in matches:
                    score = m.get("score", 0.0)
                    metadata = m.get("metadata", {})
                    text = metadata.get("text", "")

                    if score < _SCORE_THRESHOLD:
                        continue
                    if not text.strip():
                        continue

                    results.append({
                        "text": text,
                        "score": score,
                        "metadata": metadata,
                    })

                return results

        except Exception as e:
            print(f"[Pinecone query error] {e}")
            return []

    # ============================================================
    # TEXT GENERATION
    # ============================================================
    async def _generate_summary(self, query: str, items: list[dict]) -> str:
        if not self.textgen_endpoint:
            return f"{len(items)}개의 기억 발견"

        context = "\n".join(f"- {i['text'][:150]}" for i in items)

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    self.textgen_endpoint,
                    headers={"Authorization": f"Bearer {self.textgen_token}"},
                    json={
                        "model": "solar-mini",
                        "messages": [{"role": "user", "content": context}],
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

        except Exception as e:
            print(f"[TextGen error] {e}")
            return f"{len(items)}개의 기억 발견"

    # ============================================================
    # UTILS
    # ============================================================
    def _split(self, text: str):
        chunks = []
        i = 0
        while i < len(text):
            chunks.append(text[i:i + _CHUNK_SIZE])
            i += _CHUNK_SIZE - _CHUNK_OVERLAP
        return chunks

    def _make_id(self, text: str, idx: int):
        base = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"{base}_{idx}"
"""Pipeline RAG complet : retrieve -> build context -> generate (Gemma3:1b)."""

from typing import AsyncGenerator, Optional
from src.embeddings.embedder import Embedder
from src.vector_store.qdrant_client import QdrantVectorStore
from src.retrieval.retrieval_service import RetrievalService
from src.llm.llm_service import LLMService
from src.rag.context_builder import build_context


class RAGPipeline:
    def __init__(self, settings):
        self.settings = settings
        self.embedder = Embedder(
            model_name=settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        )
        self.vector_store = QdrantVectorStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection=settings.qdrant_collection,
        )
        self.retriever = RetrievalService(self.embedder, self.vector_store)
        self.llm = LLMService(
            host=settings.ollama_host,
            port=settings.ollama_port,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout,
        )

    async def query(
        self, question: str, top_k: int = 8, filters: Optional[dict] = None
    ) -> dict:
        chunks = self.retriever.retrieve(question, top_k=top_k, filters=filters)
        context = build_context(chunks)
        answer = await self.llm.generate(context=context, question=question)
        return {"answer": answer, "contexts": chunks}

    async def stream(
        self, question: str, top_k: int = 8, filters: Optional[dict] = None
    ) -> AsyncGenerator[str, None]:
        chunks = self.retriever.retrieve(question, top_k=top_k, filters=filters)
        context = build_context(chunks)
        async for token in self.llm.stream(context=context, question=question):
            yield token

    @staticmethod
    def _build_embedding_query(messages: list[dict], history_window: int = 3) -> str:
        """Construit la requête d'embedding à partir des derniers messages user.

        Permet de résoudre les références implicites comme « ces retards » :
        on concatène les N derniers messages user pour que la recherche
        vectorielle voie le contexte conversationnel.
        """
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        recent = user_msgs[-history_window:]
        return "\n".join(recent) if recent else ""

    async def chat(
        self, messages: list[dict], top_k: int = 8, filters: Optional[dict] = None
    ) -> dict:
        embedding_query = self._build_embedding_query(messages)
        chunks = self.retriever.retrieve(embedding_query, top_k=top_k, filters=filters)
        context = build_context(chunks)
        answer = await self.llm.chat(messages=messages, context=context)
        return {"answer": answer, "contexts": chunks}

    async def chat_stream(
        self, messages: list[dict], top_k: int = 8, filters: Optional[dict] = None
    ) -> AsyncGenerator[str, None]:
        embedding_query = self._build_embedding_query(messages)
        chunks = self.retriever.retrieve(embedding_query, top_k=top_k, filters=filters)
        context = build_context(chunks)
        async for token in self.llm.chat_stream(messages=messages, context=context):
            yield token

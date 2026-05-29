"""Pipeline RAG complet : query_rewrite -> retrieve -> build context -> generate."""

from typing import AsyncGenerator, Optional

import structlog

from src.embeddings.embedder import Embedder
from src.llm.llm_service import LLMService
from src.rag.context_builder import build_context
from src.rag.guardrails import check_context
from src.rag.query_rewriter import filter_by_date_range, rewrite_query
from src.retrieval.retrieval_service import RetrievalService
from src.vector_store.qdrant_client import QdrantVectorStore

log = structlog.get_logger()


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

    def _rewrite_and_merge_filters(
        self, question: str, user_filters: Optional[dict]
    ) -> tuple[Optional[dict], Optional[tuple]]:
        """Extrait les filtres d'intent et les fusionne avec ceux passés par l'API.

        Les filtres explicites (`user_filters`) ont priorité sur ceux dérivés
        de la question — on ne réécrase pas un choix conscient de l'appelant.
        """
        rewritten = rewrite_query(question)
        derived = rewritten.get("qdrant_filters") or {}
        merged = (
            {**derived, **(user_filters or {})} if (derived or user_filters) else None
        )
        if rewritten.get("matched"):
            log.info("query_rewriter", **rewritten["matched"])
        return merged, rewritten.get("date_range")

    # Sources temps réel : peu de docs, embedding faiblement aligné → le filtre
    # de source garantit déjà la pertinence, on relâche le seuil de score.
    _REALTIME_SOURCES = {"prometheus", "elasticsearch"}

    def _threshold_for(self, filters: Optional[dict]) -> Optional[float]:
        # Source temps réel filtrée : le filtre garantit la pertinence, le seuil
        # de score pénaliserait à tort (ex: snapshot santé score ~0.02).
        if filters and filters.get("source") in self._REALTIME_SOURCES:
            return 0.0
        return None

    async def query(
        self, question: str, top_k: int = 8, filters: Optional[dict] = None
    ) -> dict:
        merged_filters, date_range = self._rewrite_and_merge_filters(question, filters)
        # Si on filtre par date post-retrieval, on récupère plus large pour
        # garder du contexte après l'élagage.
        retrieve_k = top_k * 3 if date_range else top_k
        chunks = self.retriever.retrieve(
            question,
            top_k=retrieve_k,
            filters=merged_filters,
            score_threshold=self._threshold_for(merged_filters),
        )
        chunks = filter_by_date_range(chunks, date_range)[:top_k]
        context = build_context(chunks)
        ok, refus = check_context(context)
        if not ok:
            return {"answer": refus, "contexts": chunks}
        answer = await self.llm.generate(context=context, question=question)
        return {"answer": answer, "contexts": chunks}

    async def stream(
        self, question: str, top_k: int = 8, filters: Optional[dict] = None
    ) -> AsyncGenerator[str, None]:
        merged_filters, date_range = self._rewrite_and_merge_filters(question, filters)
        retrieve_k = top_k * 3 if date_range else top_k
        chunks = self.retriever.retrieve(
            question,
            top_k=retrieve_k,
            filters=merged_filters,
            score_threshold=self._threshold_for(merged_filters),
        )
        chunks = filter_by_date_range(chunks, date_range)[:top_k]
        context = build_context(chunks)
        ok, refus = check_context(context)
        if not ok:
            yield refus
            return
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
        merged_filters, date_range = self._rewrite_and_merge_filters(
            embedding_query, filters
        )
        retrieve_k = top_k * 3 if date_range else top_k
        chunks = self.retriever.retrieve(
            embedding_query,
            top_k=retrieve_k,
            filters=merged_filters,
            score_threshold=self._threshold_for(merged_filters),
        )
        chunks = filter_by_date_range(chunks, date_range)[:top_k]
        context = build_context(chunks)
        ok, refus = check_context(context)
        if not ok:
            return {"answer": refus, "contexts": chunks}
        answer = await self.llm.chat(messages=messages, context=context)
        return {"answer": answer, "contexts": chunks}

    async def chat_stream(
        self, messages: list[dict], top_k: int = 8, filters: Optional[dict] = None
    ) -> AsyncGenerator[str, None]:
        embedding_query = self._build_embedding_query(messages)
        merged_filters, date_range = self._rewrite_and_merge_filters(
            embedding_query, filters
        )
        retrieve_k = top_k * 3 if date_range else top_k
        chunks = self.retriever.retrieve(
            embedding_query,
            top_k=retrieve_k,
            filters=merged_filters,
            score_threshold=self._threshold_for(merged_filters),
        )
        chunks = filter_by_date_range(chunks, date_range)[:top_k]
        context = build_context(chunks)
        ok, refus = check_context(context)
        if not ok:
            yield refus
            return
        async for token in self.llm.chat_stream(messages=messages, context=context):
            yield token

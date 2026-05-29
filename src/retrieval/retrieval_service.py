"""Retrieval — embed la question + recherche Qdrant, avec re-ranking optionnel."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from src.embeddings.embedder import Embedder
from src.monitoring.prometheus_metrics import (
    RAG_CONTEXT_SCORE_AVG,
    RAG_EMBEDDING_DURATION,
    RAG_RETRIEVED_DOCS,
    RAG_TOP1_SCORE,
)
from src.vector_store.qdrant_client import QdrantVectorStore

SCORE_THRESHOLD = 0.20
MAX_CONTEXT_CHARS = 2000 * 4  # ≈ 2000 tokens (1 token ≈ 4 chars en moyenne)


class RetrievalService:
    def __init__(
        self, embedder: Embedder, vector_store: QdrantVectorStore, top_k: int = 5
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.default_top_k = top_k

    def retrieve(
        self,
        question: str,
        top_k: int | None = None,
        filters: Optional[dict] = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        """Recherche Qdrant avec seuil de score (défaut ``SCORE_THRESHOLD`` 0.20).

        ``score_threshold`` peut être abaissé par l'appelant quand un filtre de
        source restrictif (ex: source=prometheus, 1 seul doc) garantit déjà la
        pertinence topique — le seuil global pénaliserait alors à tort ces docs.
        """
        k = top_k or self.default_top_k
        threshold = SCORE_THRESHOLD if score_threshold is None else score_threshold

        start_embedding = time.time()
        query_vector = self.embedder.embed_query(question)
        RAG_EMBEDDING_DURATION.observe(time.time() - start_embedding)

        results = self.vector_store.search(
            query_vector, top_k=k, filters=filters, score_threshold=threshold
        )
        filtered = [r for r in results if r.get("score", 0.0) >= threshold]

        RAG_RETRIEVED_DOCS.observe(len(filtered))
        # On ne met à jour le gauge du score de contexte QUE si la requête a
        # ramené des documents. Sinon (requête sans résultat / guardrail), on
        # garde la dernière valeur significative au lieu de la réécraser à 0.0
        # — sans quoi le snapshot Prometheus lisait souvent rag_context_score=0.
        if filtered:
            average_score = sum(r.get("score", 0.0) for r in filtered) / len(filtered)
            RAG_CONTEXT_SCORE_AVG.set(average_score)
            RAG_TOP1_SCORE.observe(float(filtered[0].get("score", 0.0)))

        return filtered

    def retrieve_with_reranking(
        self,
        question: str,
        top_k_initial: int = 10,
        top_k_final: int = 5,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Re-ranking simple : score vectoriel + bonus de récence (max +5%).

        Documents avec timestamp < 24h reçoivent +5%, < 7j +2%, sinon 0.
        """
        candidates = self.retrieve(question, top_k=top_k_initial, filters=filters)
        now = datetime.now(timezone.utc)
        for c in candidates:
            ts = c.get("metadata", {}).get("timestamp")
            bonus = 0.0
            if isinstance(ts, str):
                try:
                    age = now - datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if age.total_seconds() < 86_400:
                        bonus = 0.05
                    elif age.total_seconds() < 7 * 86_400:
                        bonus = 0.02
                except ValueError:
                    pass
            c["rerank_score"] = c.get("score", 0.0) * (1.0 + bonus)
        candidates.sort(
            key=lambda c: c.get("rerank_score", c.get("score", 0.0)), reverse=True
        )
        return candidates[:top_k_final]

    @staticmethod
    def build_context_string(
        retrieved: list[dict], max_chars: int = MAX_CONTEXT_CHARS
    ) -> str:
        """Assemble les passages en un bloc contextuel pour le prompt LLM.

        Format par passage : ``[Passage N | source=… | zone=… | score=…]\\n<texte>``.
        Tronque à ~2000 tokens (8000 caractères) pour rester sous la fenêtre Gemma3.
        """
        parts: list[str] = []
        total = 0
        for i, chunk in enumerate(retrieved, 1):
            meta = chunk.get("metadata", {})
            header = (
                f"[Passage {i} | source={meta.get('source', '?')} "
                f"| zone={meta.get('zone', '?')} "
                f"| score={chunk.get('score', 0.0):.2f}]"
            )
            block = f"{header}\n{chunk.get('text', '')}"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block) + 2
        return "\n\n".join(parts)

"""Retrieval — embed la question + recherche Qdrant, avec re-ranking optionnel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.embeddings.embedder import Embedder
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
        self, question: str, top_k: int | None = None, filters: Optional[dict] = None
    ) -> list[dict]:
        """Recherche Qdrant avec seuil de score 0.30 (déjà appliqué côté store)."""
        k = top_k or self.default_top_k
        query_vector = self.embedder.embed_query(question)
        results = self.vector_store.search(query_vector, top_k=k, filters=filters)
        return [r for r in results if r.get("score", 0.0) >= SCORE_THRESHOLD]

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

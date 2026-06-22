"""Retrieval — embed la question + recherche Qdrant, avec re-ranking optionnel."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.embeddings.embedder import Embedder
from src.monitoring.prometheus_metrics import (
    RAG_CONTEXT_SCORE_AVG,
    RAG_EMBEDDING_CACHE_HITS,
    RAG_EMBEDDING_CACHE_MISSES,
    RAG_EMBEDDING_DURATION,
    RAG_RETRIEVED_DOCS,
    RAG_TOP1_SCORE,
)
from src.retrieval.bm25 import BM25Okapi, reciprocal_rank_fusion, tokenize
from src.vector_store.qdrant_client import QdrantVectorStore

log = structlog.get_logger()

SCORE_THRESHOLD = 0.20
MAX_CONTEXT_CHARS = 2000 * 4  # ≈ 2000 tokens (1 token ≈ 4 chars en moyenne)

# Retrieval hybride : taille du pool dense sur-récupéré avant fusion lexicale.
# On ratisse large (≥ HYBRID_POOL_MIN) pour donner à BM25 de quoi re-classer ;
# RRF ramène ensuite le top_k final.
HYBRID_POOL_MIN = 30
HYBRID_POOL_FACTOR = 4
RRF_K = 60


class RetrievalService:
    def __init__(
        self,
        embedder: Embedder,
        vector_store: QdrantVectorStore,
        top_k: int = 5,
        settings=None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.default_top_k = top_k
        # Cache Redis optionnel : activé uniquement si ``settings`` est fourni,
        # le flag est ON, et Redis répond. Sinon fonctionnement sans cache
        # (rétro-compatible avec les appelants qui ne passent pas settings).
        self.cache = None
        self.cache_enabled = False
        if settings is not None and getattr(settings, "embedding_cache_enabled", False):
            self.cache = self._build_cache(settings)
            self.cache_enabled = self.cache is not None

    @staticmethod
    def _build_cache(settings):
        """Construit le cache Redis avec fallback silencieux si indisponible."""
        try:
            import redis  # import paresseux : la lib peut être absente

            from src.embeddings.embedding_cache import EmbeddingCache

            client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=False,
            )
            client.ping()
            log.info(
                "Cache Redis activé",
                host=settings.redis_host,
                ttl=settings.redis_ttl_embedding_sec,
            )
            return EmbeddingCache(client, ttl_sec=settings.redis_ttl_embedding_sec)
        except Exception as e:
            log.warning("Redis indisponible — cache désactivé", error=str(e))
            return None

    def _embed_query_cached(self, question: str) -> list[float]:
        """Encode la question avec cache-aside : Redis hit (~1ms) sinon compute.

        Sur hit : retour immédiat du vecteur Redis. Sur miss (ou cache off) :
        encode sentence-transformer (~66ms), observe la latence, puis stocke.
        Fallback transparent : Redis indisponible → encode direct sans cache.
        """
        if self.cache is not None:
            cached = self.cache.get(question)
            if cached is not None:
                RAG_EMBEDDING_CACHE_HITS.inc()
                return cached

        start = time.time()
        vector = self.embedder.embed_query(question)
        RAG_EMBEDDING_DURATION.observe(time.time() - start)

        if self.cache is not None:
            RAG_EMBEDDING_CACHE_MISSES.inc()
            self.cache.set(question, vector)
        return vector

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

        query_vector = self._embed_query_cached(question)

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
            RAG_TOP1_SCORE.set(float(filtered[0].get("score", 0.0)))

        return filtered

    def retrieve_hybrid(
        self,
        question: str,
        top_k: int | None = None,
        filters: Optional[dict] = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        """Recherche hybride : dense (Qdrant cosine) + sparse BM25, fusion RRF.

        Étapes :
          1. Sur-récupère un pool dense large (``HYBRID_POOL_MIN`` au moins).
          2. Calcule un score BM25 lexical sur les textes de ce pool.
          3. Fusionne les deux classements par Reciprocal Rank Fusion (RRF).
          4. Renvoie le top_k fusionné.

        Dégradation gracieuse : si le pool dense compte ≤ 1 document, la fusion
        n'apporte rien et on renvoie directement le résultat dense.
        Le champ ``score`` conservé reste le score dense d'origine (comparable
        d'une requête à l'autre) ; le score RRF est exposé via ``rrf_score``.
        """
        k = top_k or self.default_top_k
        threshold = SCORE_THRESHOLD if score_threshold is None else score_threshold
        pool_size = max(HYBRID_POOL_MIN, k * HYBRID_POOL_FACTOR)

        query_vector = self._embed_query_cached(question)

        pool = self.vector_store.search(
            query_vector, top_k=pool_size, filters=filters, score_threshold=threshold
        )
        pool = [r for r in pool if r.get("score", 0.0) >= threshold]

        if len(pool) <= 1:
            self._record_retrieval_metrics(pool)
            return pool[:k]

        # Classement dense : déjà trié par score décroissant par Qdrant.
        dense_ranking = list(range(len(pool)))

        # Classement sparse : BM25 sur les textes du pool.
        corpus = [tokenize(doc.get("text", "")) for doc in pool]
        bm25 = BM25Okapi(corpus)
        bm25_scores = bm25.get_scores(tokenize(question))
        sparse_ranking = sorted(
            range(len(pool)), key=lambda i: bm25_scores[i], reverse=True
        )

        fused = reciprocal_rank_fusion([dense_ranking, sparse_ranking], rrf_k=RRF_K)
        order = sorted(fused, key=lambda i: fused[i], reverse=True)

        result: list[dict] = []
        for idx in order[:k]:
            doc = dict(pool[idx])
            doc["rrf_score"] = fused[idx]
            doc["bm25_score"] = bm25_scores[idx]
            result.append(doc)

        self._record_retrieval_metrics(result)
        return result

    def _record_retrieval_metrics(self, docs: list[dict]) -> None:
        """Met à jour les gauges Prometheus à partir des documents retenus.

        Mêmes garde-fous que ``retrieve`` : on ne réécrase pas le score de
        contexte à 0 quand la requête ne ramène rien (on garde la dernière
        valeur significative).
        """
        RAG_RETRIEVED_DOCS.observe(len(docs))
        if docs:
            average_score = sum(d.get("score", 0.0) for d in docs) / len(docs)
            RAG_CONTEXT_SCORE_AVG.set(average_score)
            RAG_TOP1_SCORE.set(float(docs[0].get("score", 0.0)))

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

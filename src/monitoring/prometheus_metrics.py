"""prometheus_metrics.py — MLOPS-108: Métriques Prometheus partagées
==============================================================
Ce module expose les métriques Prometheus utilisées par l'API RAG.
Les métriques sont déclarées ici pour être enregistrées dans le même registry
et réutilisables depuis l'API, le pipeline RAG et le service de retrieval.
"""

from prometheus_client import Counter, Gauge, Histogram

# Counters
RAG_QUERY_TOTAL = Counter(
    "rag_query_total",
    "Nombre total de requêtes RAG",
    ["status", "zone_filter"],
)

# Histograms
RAG_QUERY_DURATION = Histogram(
    "rag_query_duration_seconds", "Durée totale d'une requête RAG"
)

RAG_LLM_LATENCY = Histogram(
    "rag_llm_latency_seconds",
    "Latence Gemma3 pour la génération de réponse",
    buckets=[0.5, 1, 2, 5, 10, 30],
)

RAG_EMBEDDING_DURATION = Histogram(
    "rag_embedding_duration_seconds",
    "Durée de l'embedding de la question",
    buckets=[0.05, 0.1, 0.2, 0.5, 1],
)

RAG_RETRIEVED_DOCS = Histogram(
    "rag_retrieved_docs_count",
    "Nombre de documents récupérés par requête RAG",
    buckets=[1, 3, 5, 8, 10, 20],
)

# Gauges
RAG_CONTEXT_SCORE_AVG = Gauge(
    "rag_context_score_avg",
    "Score moyen des documents récupérés par Qdrant",
)

RAG_ACTIVE_REQUESTS = Gauge(
    "rag_active_requests",
    "Nombre de requêtes RAG actives en cours",
)


def extract_zone_filter(filters: dict | None) -> str:
    """Extraire une étiquette zone_filter simple depuis les filtres Qdrant."""
    if not filters:
        return "none"

    # Cas simple: lookup direct
    if isinstance(filters, dict):
        if "zone" in filters:
            return str(filters["zone"])

        for key in ("must", "should", "must_not", "filter"):
            value = filters.get(key)
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    match = item.get("match") or item.get("term") or item.get("equals")
                    if isinstance(match, dict) and "zone" in match:
                        return str(match["zone"])

    return "other"

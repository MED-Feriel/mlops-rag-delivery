"""
Évaluation déterministe du retrieval — alternative à RAGAS (LLM-judge) qui
nécessite OPENAI_API_KEY indisponible ici.

4 métriques calculées sur les 10 questions de référence :
  1. top-1 accuracy   : le doc en position 1 satisfait le prédicat attendu ?
  2. MRR              : mean reciprocal rank du 1er doc satisfaisant le prédicat
  3. presence@5       : au moins un doc dans le top-5 satisfait le prédicat
  4. mean_top1_score  : moyenne du score de similarité du top-1

L'évaluation est faite DEUX FOIS :
  - "before" : retrieval brut sans query rewriter (filters=None, top_k=5)
  - "after"  : pipeline complet avec rewriter (RAGPipeline.query)

Chaque condition est logguée comme métriques séparées dans MLflow.

Usage :
    docker compose exec -T api python3 scripts/run_custom_eval.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Callable

sys.path.insert(0, "/app")


# ────────────────────────────────────────────────────────────────
# PRÉDICATS PAR QUESTION
# Chaque prédicat reçoit un dict chunk = {text, score, metadata} et
# retourne True si le doc est "pertinent" pour la question.
# ────────────────────────────────────────────────────────────────


def _has(meta: dict, key: str, val) -> bool:
    return meta.get(key) == val


def _meta_in(meta: dict, key: str, vals: set) -> bool:
    return meta.get(key) in vals


EVAL_EXPECTATIONS: list[tuple[str, str, Callable[[dict], bool]]] = [
    # (question, description du prédicat, fn(chunk) -> bool)
    (
        "Quelles commandes sont actuellement en retard de plus de 30 minutes ?",
        "doc d'incident type=retard OU synthèse incidents",
        lambda c: (
            (
                c["metadata"].get("source") == "incidents"
                and c["metadata"].get("type_event") == "retard"
            )
            or c["metadata"].get("topic") == "synthese_incidents"
        ),
    ),
    (
        "Y a-t-il des incidents critiques actifs en ce moment ?",
        "doc d'incident criticite in {critique, haute}",
        lambda c: (
            c["metadata"].get("source") == "incidents"
            and c["metadata"].get("criticite") in {"critique", "haute"}
        ),
    ),
    (
        "Quel livreur est actuellement bloqué ?",
        "doc d'incident type_event=livreur_bloque",
        lambda c: c["metadata"].get("type_event") == "livreur_bloque",
    ),
    (
        "Quel restaurant a le plus fort taux d'annulation ce mois-ci ?",
        "synthèse top_restaurants OU doc restaurant",
        lambda c: (
            c["metadata"].get("topic") == "top_restaurants"
            or c["metadata"].get("source") == "restaurants"
        ),
    ),
    (
        "Quelle zone géographique a les délais de livraison les plus longs ?",
        "doc zone snapshot OU synthèse incidents par zone",
        lambda c: (
            c["metadata"].get("source") == "zones"
            or c["metadata"].get("topic") == "incidents_par_zone"
        ),
    ),
    (
        "Quelles sont les causes les plus fréquentes de retard ?",
        "synthèse incidents (agrégation causes)",
        lambda c: c["metadata"].get("topic") == "synthese_incidents",
    ),
    (
        "Comment s'est comporté le service de paiement ces dernières heures ?",
        "synthèse paiements OU incident paiement_echoue",
        lambda c: (
            c["metadata"].get("topic") == "synthese_paiements"
            or c["metadata"].get("type_event") == "paiement_echoue"
        ),
    ),
    (
        "Le volume de commandes est-il en hausse ou en baisse aujourd'hui ?",
        "synthèse tendance_volume",
        lambda c: c["metadata"].get("topic") == "tendance_volume",
    ),
    (
        "Les notes clients se sont-elles améliorées récemment ?",
        "doc avis_clients OU synthèse tendance_volume",
        lambda c: (
            c["metadata"].get("source") == "avis_clients"
            or c["metadata"].get("topic") == "tendance_volume"
        ),
    ),
    (
        "Décris les 3 incidents les plus critiques survenus aujourd'hui.",
        "doc d'incident criticite=critique",
        lambda c: (
            c["metadata"].get("source") == "incidents"
            and c["metadata"].get("criticite") == "critique"
        ),
    ),
]


# ────────────────────────────────────────────────────────────────
# CALCUL DES MÉTRIQUES
# ────────────────────────────────────────────────────────────────


def evaluate_query(chunks: list[dict], predicate: Callable[[dict], bool]) -> dict:
    """Retourne les métriques pour une question donnée."""
    if not chunks:
        return {"top1_hit": 0, "rr": 0.0, "presence5": 0, "top1_score": 0.0}
    top1_hit = 1 if predicate(chunks[0]) else 0
    # First matching rank
    rr = 0.0
    for i, c in enumerate(chunks[:10], 1):
        if predicate(c):
            rr = 1.0 / i
            break
    presence5 = 1 if any(predicate(c) for c in chunks[:5]) else 0
    top1_score = float(chunks[0].get("score", 0.0))
    return {
        "top1_hit": top1_hit,
        "rr": rr,
        "presence5": presence5,
        "top1_score": top1_score,
    }


def aggregate(per_q: list[dict]) -> dict:
    n = len(per_q)
    if n == 0:
        return {
            "top1_accuracy": 0.0,
            "mrr": 0.0,
            "presence_at_5": 0.0,
            "mean_top1_score": 0.0,
        }
    return {
        "top1_accuracy": sum(q["top1_hit"] for q in per_q) / n,
        "mrr": sum(q["rr"] for q in per_q) / n,
        "presence_at_5": sum(q["presence5"] for q in per_q) / n,
        "mean_top1_score": sum(q["top1_score"] for q in per_q) / n,
    }


# ────────────────────────────────────────────────────────────────
# CHAINS DE RETRIEVAL
# ────────────────────────────────────────────────────────────────


def retrieve_without_rewriter(retriever, question: str, top_k: int = 5) -> list[dict]:
    """Retrieval brut — embedding + Qdrant top_k, AUCUN filtre."""
    return retriever.retrieve(question, top_k=top_k, filters=None)


def retrieve_with_rewriter(pipeline, question: str, top_k: int = 5) -> list[dict]:
    """Retrieval via le pipeline complet (rewriter activé)."""
    # On utilise la même logique que RAGPipeline.query mais sans LLM gen
    merged_filters, date_range = pipeline._rewrite_and_merge_filters(question, None)
    retrieve_k = top_k * 3 if date_range else top_k
    from src.rag.query_rewriter import filter_by_date_range

    chunks = pipeline.retriever.retrieve(
        question, top_k=retrieve_k, filters=merged_filters
    )
    chunks = filter_by_date_range(chunks, date_range)[:top_k]
    return chunks


# ────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────


async def main() -> None:
    from config.settings import get_settings
    from src.rag.rag_pipeline import RAGPipeline
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment("rag-evaluation")

    pipeline = RAGPipeline(settings)
    retriever = pipeline.retriever

    print("═" * 78)
    print(f"{'Question':<50} | {'predicate':35}")
    print("═" * 78)

    before_per_q = []
    after_per_q = []
    detail_lines = []

    for q, predicate_desc, predicate in EVAL_EXPECTATIONS:
        chunks_before = retrieve_without_rewriter(retriever, q, top_k=5)
        chunks_after = retrieve_with_rewriter(pipeline, q, top_k=5)
        m_before = evaluate_query(chunks_before, predicate)
        m_after = evaluate_query(chunks_after, predicate)
        before_per_q.append(m_before)
        after_per_q.append(m_after)

        # Détail pour audit
        top1_before = chunks_before[0]["metadata"] if chunks_before else {}
        top1_after = chunks_after[0]["metadata"] if chunks_after else {}
        line = (
            f"  Q: {q[:60]}\n"
            f"    predicate: {predicate_desc}\n"
            f"    BEFORE top1: src={top1_before.get('source','-')}/{top1_before.get('topic','-')} "
            f"type={top1_before.get('type_event','-')} crit={top1_before.get('criticite','-')} "
            f"hit={m_before['top1_hit']} rr={m_before['rr']:.2f}\n"
            f"    AFTER  top1: src={top1_after.get('source','-')}/{top1_after.get('topic','-')} "
            f"type={top1_after.get('type_event','-')} crit={top1_after.get('criticite','-')} "
            f"hit={m_after['top1_hit']} rr={m_after['rr']:.2f}"
        )
        print(line)
        print()
        detail_lines.append(line)

    agg_before = aggregate(before_per_q)
    agg_after = aggregate(after_per_q)

    print("═" * 78)
    print(f"{'Metric':<22} | {'BEFORE':>10} | {'AFTER':>10} | {'Δ':>10}")
    print("─" * 78)
    for k in ("top1_accuracy", "mrr", "presence_at_5", "mean_top1_score"):
        b, a = agg_before[k], agg_after[k]
        d = a - b
        sign = "+" if d >= 0 else ""
        print(f"{k:<22} | {b:>10.3f} | {a:>10.3f} | {sign}{d:>9.3f}")
    print("═" * 78)

    # MLflow logging
    with mlflow.start_run(run_name="custom-eval-post-rewriter-167k"):
        mlflow.log_params(
            {
                "n_questions": len(EVAL_EXPECTATIONS),
                "top_k": 5,
                "qdrant_collection": settings.qdrant_collection,
                "vectors_indexed": 167659,
                "method": "custom_deterministic_retrieval_eval",
            }
        )
        # Before metrics
        mlflow.log_metrics({f"before_{k}": v for k, v in agg_before.items()})
        # After metrics
        mlflow.log_metrics({f"after_{k}": v for k, v in agg_after.items()})
        # Deltas
        mlflow.log_metrics(
            {f"delta_{k}": agg_after[k] - agg_before[k] for k in agg_before}
        )
        # Détail comme artifact
        detail_path = "/tmp/custom_eval_detail.txt"
        with open(detail_path, "w") as f:
            f.write("\n".join(detail_lines))
            f.write("\n\nAggregates:\n")
            f.write(f"BEFORE: {agg_before}\nAFTER:  {agg_after}\n")
        mlflow.log_artifact(detail_path, artifact_path="evaluation")
        print("\n✅ MLflow run logguée : custom-eval-post-rewriter-167k")


if __name__ == "__main__":
    asyncio.run(main())

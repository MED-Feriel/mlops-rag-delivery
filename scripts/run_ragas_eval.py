"""Script d'évaluation RAGAS — exécution manuelle hors DAG Airflow.

Usage:
    docker compose exec -T api python3 scripts/run_ragas_eval.py [--limit N]

Lance l'évaluation sur ``EVAL_QUESTIONS`` (ou les ``--limit`` premières) et
logue les scores dans MLflow (expérience ``rag-evaluation``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

# Le container monte /app/src + /app/config — pas besoin de path hack.
sys.path.insert(0, "/app")


async def main(limit: int | None) -> dict:
    from config.settings import get_settings
    from src.evaluation.ragas_evaluator import RAGASEvaluator
    from src.evaluation.test_questions import EVAL_QUESTIONS
    from src.rag.rag_pipeline import RAGPipeline
    import mlflow

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

    questions = EVAL_QUESTIONS[:limit] if limit else EVAL_QUESTIONS
    print("🚀 Démarrage évaluation RAGAS")
    print(f"   Questions : {len(questions)} / {len(EVAL_QUESTIONS)}")
    print(f"   LLM       : {settings.ollama_model}")
    print(f"   Qdrant    : {settings.qdrant_collection}")
    print(f"   MLflow    : {settings.mlflow_tracking_uri}")
    print()

    pipeline = RAGPipeline(settings)
    evaluator = RAGASEvaluator(pipeline, mlflow_experiment="rag-evaluation")

    run_name = f"ragas_eval_{datetime.now().strftime('%Y%m%d_%H%M')}_n{len(questions)}"
    scores = await evaluator.evaluate_and_log(
        questions=questions,
        run_name=run_name,
    )

    print("═" * 60)
    print("📊 SCORES RAGAS")
    print("═" * 60)
    for metric, score in scores.items():
        try:
            bar = "█" * max(0, int(score * 20))
            print(f"  {metric:<22} {score:.3f}  {bar}")
        except Exception:
            print(f"  {metric:<22} {score}")
    print("═" * 60)
    print(f"✅ Résultats dans MLflow : {settings.mlflow_tracking_uri}")
    print("   Expérience : rag-evaluation")
    print(f"   Run name   : {run_name}")
    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nombre de questions à évaluer (défaut: toutes)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.limit))

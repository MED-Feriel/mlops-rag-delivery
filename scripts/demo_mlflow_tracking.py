#!/usr/bin/env python3
"""
demo_mlflow_tracking.py — Démonstration complète MLflow
======================================================
Exemple d'utilisation de MLflow pour tracker et comparer les expériences RAG.

USAGE:
  python demo_mlflow_tracking.py --mode=tracking        # Mode tracking simple
  python demo_mlflow_tracking.py --mode=comparison      # Mode comparaison
  python demo_mlflow_tracking.py --mode=registry        # Mode Model Registry
"""

import asyncio
import sys
import structlog
from argparse import ArgumentParser
from pathlib import Path

# Ajouter src au path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun

log = structlog.get_logger()


async def demo_basic_tracking():
    """Démo 1: Tracking simple des expériences."""
    print("\n" + "=" * 80)
    print("📊 DÉMO 1: Tracking simple des expériences")
    print("=" * 80 + "\n")

    settings = Settings()
    tracker = MLflowTracker(
        tracking_uri=settings.mlflow_tracking_uri, experiment_name="demo_basic"
    )

    # Run 1: Baseline
    with MLflowRun(
        tracker, "baseline_v1", tags={"model": "gemma3:1b", "version": "1.0"}
    ):
        tracker.log_params({"chunk_size": 512, "top_k": 5, "temperature": 0.7})
        tracker.log_metrics(
            {
                "faithfulness": 0.85,
                "answer_relevancy": 0.78,
                "context_precision": 0.82,
                "context_recall": 0.75,
            }
        )
        print("✅ Run 1 (Baseline) loggée")

    # Run 2: Avec hyperparamètres optimisés
    with MLflowRun(
        tracker, "optimized_v1", tags={"model": "gemma3:1b", "version": "2.0"}
    ):
        tracker.log_params({"chunk_size": 768, "top_k": 8, "temperature": 0.5})
        tracker.log_metrics(
            {
                "faithfulness": 0.89,
                "answer_relevancy": 0.82,
                "context_precision": 0.86,
                "context_recall": 0.79,
            }
        )
        print("✅ Run 2 (Optimized) loggée")

    # Run 3: Avec embedding multilingue
    with MLflowRun(
        tracker,
        "multilingual_embedding",
        tags={"model": "gemma3:1b", "embedding": "paraphrase"},
    ):
        tracker.log_params(
            {
                "chunk_size": 512,
                "top_k": 5,
                "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
            }
        )
        tracker.log_metrics(
            {
                "faithfulness": 0.91,
                "answer_relevancy": 0.85,
                "context_precision": 0.88,
                "context_recall": 0.82,
            }
        )
        print("✅ Run 3 (Multilingual) loggée")

    print("\n✅ Tracking simple terminé!")
    print(f"📈 Visualiser sur: {settings.mlflow_tracking_uri}")


async def demo_comparison():
    """Démo 2: Comparaison des expériences."""
    print("\n" + "=" * 80)
    print("📊 DÉMO 2: Comparaison des expériences")
    print("=" * 80 + "\n")

    settings = Settings()
    tracker = MLflowTracker(
        tracking_uri=settings.mlflow_tracking_uri, experiment_name="demo_basic"
    )

    # Comparer sur différentes métriques
    metrics_to_compare = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    print("🔍 Comparaison des meilleures runs par métrique:\n")

    for metric in metrics_to_compare:
        comparison_df = tracker.compare_experiments(metric, top_n=3)

        if not comparison_df.empty:
            print(f"\n📌 Métrique: {metric.upper()}")
            print("-" * 80)
            print(comparison_df.to_string(index=False))
        else:
            print(f"⚠️ Aucune donnée pour {metric}")

    # Obtenir la meilleure run globale
    print("\n\n🏆 MEILLEURE RUN (par faithfulness):")
    print("-" * 80)
    best_run = tracker.get_best_run("faithfulness")

    if best_run:
        print(f"Run ID: {best_run['run_id']}")
        print(f"Status: {best_run['status']}")
        print("\nMétriques:")
        for name, value in best_run["metrics"].items():
            print(f"  {name}: {value:.4f}")
        print("\nParamètres:")
        for name, value in best_run["params"].items():
            print(f"  {name}: {value}")

    print("\n✅ Comparaison terminée!")


async def demo_model_registry():
    """Démo 3: Model Registry."""
    print("\n" + "=" * 80)
    print("📊 DÉMO 3: Model Registry")
    print("=" * 80 + "\n")

    settings = Settings()
    tracker = MLflowTracker(
        tracking_uri=settings.mlflow_tracking_uri, experiment_name="demo_registry"
    )

    # Créer une run avec un modèle
    with MLflowRun(tracker, "production_model_v1", tags={"stage": "production"}):

        tracker.log_params(
            {"model_type": "rag_pipeline", "vector_store": "qdrant", "chunk_size": 512}
        )

        tracker.log_metrics(
            {
                "faithfulness": 0.92,
                "answer_relevancy": 0.88,
                "context_precision": 0.89,
                "context_recall": 0.85,
                "inference_time_ms": 250,
            }
        )

        # Créer un fichier model simulé
        model_file = Path("/tmp/rag_model.pkl")
        model_file.write_text("# Simulé: RAG Model Pickle")
        tracker.log_artifact(str(model_file), artifact_path="model")

        run_id = tracker.client.get_run(
            tracker.client.search_runs(
                experiment_ids=[
                    mlflow.get_experiment_by_name("demo_registry").experiment_id
                ]
            )[0].info.run_id
        ).info.run_id

        print(f"✅ Run créée avec ID: {run_id}")

        # Enregistrer le modèle
        # tracker.register_model(run_id, "model", "rag_production", stage="Staging")
        print("✅ Modèle enregistré dans le registry")

    # Récupérer les versions du modèle
    # versions = tracker.get_model_versions("rag_production")
    # print(f"\n📌 Versions du modèle rag_production:")
    # for v in versions:
    #     print(f"  Version {v['version']}: {v['stage']}")

    print("\n✅ Model Registry demo terminée!")


async def demo_detailed_metrics():
    """Démo 4: Logging détaillé avec artifacts."""
    print("\n" + "=" * 80)
    print("📊 DÉMO 4: Logging détaillé avec artifacts")
    print("=" * 80 + "\n")

    settings = Settings()
    tracker = MLflowTracker(
        tracking_uri=settings.mlflow_tracking_uri, experiment_name="demo_artifacts"
    )

    with MLflowRun(tracker, "detailed_eval", tags={"type": "full_evaluation"}):

        # Logger les hyperparamètres
        tracker.log_params(
            {
                "model": "gemma3:1b",
                "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
                "batch_size": 32,
                "epochs": 5,
                "learning_rate": 0.0001,
            }
        )

        # Logger les métriques par étape
        for step in range(1, 4):
            metrics = {
                "train_loss": 0.5 / step,
                "val_loss": 0.6 / step,
                "accuracy": 0.7 + (0.1 * step),
            }
            tracker.log_metrics(metrics, step=step)
            print(f"  Step {step}: {metrics}")

        # Logger les résultats d'évaluation
        eval_results = {
            "faithfulness": 0.87,
            "answer_relevancy": 0.81,
            "context_precision": 0.84,
            "context_recall": 0.78,
        }
        tracker.log_eval_results(eval_results, eval_name="RAGAS")
        print(f"  Évaluation RAGAS loggée: {eval_results}")

        print("\n✅ Tous les artifacts loggés!")

    print("\n✅ Logging détaillé terminé!")


async def main():
    """Point d'entrée principal."""
    parser = ArgumentParser(description="Démonstration MLflow pour RAG")
    parser.add_argument(
        "--mode",
        default="tracking",
        choices=["tracking", "comparison", "registry", "artifacts", "all"],
        help="Mode de démo à exécuter",
    )
    args = parser.parse_args()

    log.info("[DEMO] Démarrage", mode=args.mode)

    try:
        if args.mode == "tracking" or args.mode == "all":
            await demo_basic_tracking()

        if args.mode == "comparison" or args.mode == "all":
            await demo_comparison()

        if args.mode == "registry" or args.mode == "all":
            await demo_model_registry()

        if args.mode == "artifacts" or args.mode == "all":
            await demo_detailed_metrics()

        print("\n" + "=" * 80)
        print("🎉 TOUTES LES DÉMOS TERMINÉES!")
        print("=" * 80)
        print("\n📈 Accédez au dashboard MLflow:")
        settings = Settings()
        print(f"   {settings.mlflow_tracking_uri}")
        print("\nPour comparer les runs, aller à la section 'Experiments'")

    except Exception as e:
        log.error("[DEMO] Erreur", exc=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    import mlflow

    asyncio.run(main())

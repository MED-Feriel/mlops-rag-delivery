"""
rag_with_mlflow.py — Integration de MLflow avec la pipeline RAG
==============================================================
Wrapper pour tracker automatiquement les runs RAG dans MLflow.
"""

import structlog
from typing import Dict, Any, Optional
from src.monitoring.mlflow_tracker import MLflowTracker, MLflowRun
from src.rag.rag_pipeline import RAGPipeline

log = structlog.get_logger()


class RAGWithMLflow:
    """Pipeline RAG avec tracking MLflow automatique."""

    def __init__(self, rag_pipeline: RAGPipeline, mlflow_tracker: MLflowTracker):
        """
        Initialiser le pipeline RAG avec tracking MLflow.

        Args:
            rag_pipeline: Instance RAGPipeline
            mlflow_tracker: Instance MLflowTracker
        """
        self.rag = rag_pipeline
        self.mlflow = mlflow_tracker
        log.info("[RAG_MLFLOW] Pipeline initialisée")

    async def query_and_log(
        self,
        query: str,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Exécuter une requête RAG et logger dans MLflow.

        Args:
            query: Question utilisateur
            run_name: Nom de la run MLflow
            tags: Tags pour la run

        Returns:
            Résultat RAG complet
        """
        run_name = run_name or f"query_{hash(query)}"
        tags = tags or {"source": "api_query"}

        try:
            with MLflowRun(self.mlflow, run_name, tags):
                # Logger les paramètres de requête
                self.mlflow.log_params(
                    {
                        "query_length": len(query),
                        "top_k": (
                            self.rag.retrieval_service.top_k
                            if hasattr(self.rag, "retrieval_service")
                            else 8
                        ),
                    }
                )

                # Exécuter la requête
                result = await self.rag.query(query)

                # Logger les résultats
                result_metrics = {
                    "nb_documents_retrieved": len(result.get("contexts", [])),
                    "first_doc_score": (
                        float(result.get("contexts", [{}])[0].get("score", 0))
                        if result.get("contexts")
                        else 0
                    ),
                }
                self.mlflow.log_metrics(result_metrics)

                log.info("[RAG_MLFLOW] Requête loggée", result_metrics=result_metrics)
                return result

        except Exception as e:
            log.error("[RAG_MLFLOW] Erreur query_and_log", exc=str(e), exc_info=True)
            raise

    async def evaluate_and_log_batch(
        self,
        questions: list[Dict[str, str]],
        evaluator,
        experiment_name: str = "batch_eval",
    ) -> Dict[str, float]:
        """
        Évaluer un batch de questions et logger dans MLflow.

        Args:
            questions: Liste de {"question": str, "ground_truth": str}
            evaluator: Instance RAGASEvaluator
            experiment_name: Nom de l'expérience

        Returns:
            Scores d'évaluation
        """
        try:
            with MLflowRun(self.mlflow, experiment_name, {"type": "batch_evaluation"}):

                # Logger les paramètres du batch
                self.mlflow.log_params(
                    {"batch_size": len(questions), "evaluator": "RAGAS"}
                )

                # Évaluer
                scores = await evaluator.evaluate_and_log(
                    questions, run_name=experiment_name
                )

                # Logger les scores
                self.mlflow.log_metrics(scores)

                log.info("[RAG_MLFLOW] Batch évalué", scores=scores)
                return scores

        except Exception as e:
            log.error(
                "[RAG_MLFLOW] Erreur evaluate_and_log_batch", exc=str(e), exc_info=True
            )
            raise

    def compare_experiments_summary(self, metric: str = "faithfulness") -> str:
        """
        Retourner un résumé des expériences comparées.

        Args:
            metric: Métrique pour la comparaison

        Returns:
            String formatée avec les résultats
        """
        comparison = self.mlflow.compare_experiments(metric, top_n=10)

        if comparison.empty:
            return "Aucune expérience à comparer"

        summary = f"\n📊 COMPARAISON EXPÉRIENCES — Métrique: {metric}\n"
        summary += "=" * 80 + "\n"

        for idx, row in comparison.iterrows():
            summary += f"#{idx+1} | Run: {row['run_id'][:8]}... | "
            summary += f"Score: {row[metric]:.4f} | "
            summary += f"LLM: {row['llm_model']} | "
            summary += f"Embedding: {row['embedding_model']}\n"

        return summary

    def get_best_model_summary(self, metric: str = "faithfulness") -> str:
        """
        Retourner un résumé du meilleur modèle.

        Args:
            metric: Métrique pour évaluer

        Returns:
            String formatée avec les infos
        """
        best = self.mlflow.get_best_run(metric)

        if not best:
            return "Aucun modèle trouvé"

        summary = f"\n🏆 MEILLEUR MODÈLE — Métrique: {metric}\n"
        summary += "=" * 80 + "\n"
        summary += f"Run ID: {best['run_id']}\n"
        summary += f"Status: {best['status']}\n"
        summary += "\nMétriques:\n"
        for name, value in best["metrics"].items():
            summary += f"  - {name}: {value:.4f}\n"
        summary += "\nParamètres:\n"
        for name, value in best["params"].items():
            summary += f"  - {name}: {value}\n"

        return summary


# Exemple d'utilisation
async def example_usage():
    """Exemple d'utilisation du RAG avec MLflow."""
    from config.settings import Settings
    from src.rag.rag_pipeline import RAGPipeline
    from src.evaluation.ragas_evaluator import RAGASEvaluator

    settings = Settings()

    # Initialiser les services
    rag_pipeline = RAGPipeline(
        llm_service=...,  # Initialiser depuis config
        retrieval_service=...,
    )

    evaluator = RAGASEvaluator(rag_pipeline)
    mlflow_tracker = MLflowTracker(
        tracking_uri=settings.mlflow_tracking_uri,
        experiment_name=settings.mlflow_experiment,
    )

    # Créer le RAG avec MLflow
    rag_mlflow = RAGWithMLflow(rag_pipeline, mlflow_tracker)

    # Exemple 1: Requête simple avec logging
    await rag_mlflow.query_and_log(
        "Combien de commandes retardées en Algérie ?",
        tags={"user": "test", "source": "demo"},
    )

    # Exemple 2: Évaluation batch
    questions = [
        {"question": "Quelle est la livraison la plus rapide ?", "ground_truth": "..."},
        {"question": "Combien d'incidents aujourd'hui ?", "ground_truth": "..."},
    ]
    await rag_mlflow.evaluate_and_log_batch(questions, evaluator)

    # Exemple 3: Comparaison d'expériences
    print(rag_mlflow.compare_experiments_summary("faithfulness"))

    # Exemple 4: Meilleur modèle
    print(rag_mlflow.get_best_model_summary("answer_relevancy"))

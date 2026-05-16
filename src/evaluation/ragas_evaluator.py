"""
ragas_evaluator.py — MLOPS-107: Évaluation RAGAS avec MLflow
============================================================
Évaluation des pipelines RAG sur: faithfulness, answer_relevancy,
context_precision, context_recall. Logs complèts dans MLflow.

FLUX:
  questions → build_dataset → RAGAS evaluate → scores → MLflow
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import mlflow
import pandas as pd
import structlog
from datasets import Dataset
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import HuggingFaceEmbeddings
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

log = structlog.get_logger()


class RAGASEvaluator:
    """Évaluation RAGAS complète avec MLflow tracking."""

    METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]
    METRIC_NAMES = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    def __init__(self, rag_pipeline, mlflow_experiment: str = "rag-evaluation"):
        """
        Initialiser l'évaluateur RAGAS.

        Args:
            rag_pipeline: Instance RAGPipeline
            mlflow_experiment: Nom de l'expérience MLflow
        """
        self.rag = rag_pipeline
        self.experiment = mlflow_experiment
        mlflow.set_experiment(mlflow_experiment)
        log.info("[RAGAS] Évaluateur initialisé", experiment=mlflow_experiment)

    async def build_eval_dataset(self, questions: list[dict]) -> Dataset:
        """
        Construire un dataset d'évaluation à partir des questions.

        Args:
            questions: Liste de {"question": str, "ground_truth": str}

        Returns:
            Dataset RAGAS (question, answer, contexts, ground_truth)
        """
        log.info("[RAGAS] Construction du dataset", nb_questions=len(questions))
        data = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

        for i, q in enumerate(questions):
            try:
                result = await self.rag.query(q["question"])
                data["question"].append(q["question"])
                data["answer"].append(result.get("answer", ""))
                data["contexts"].append(
                    [c.get("text", "") for c in result.get("contexts", [])]
                )
                data["ground_truth"].append(q.get("ground_truth", ""))

                if (i + 1) % 5 == 0:
                    log.info(f"[RAGAS] Progression: {i+1}/{len(questions)}")
            except Exception as e:
                log.error(f"[RAGAS] Erreur pour question {i}: {e}")
                continue

        log.info("[RAGAS] Dataset construit", nb_samples=len(data["question"]))
        return Dataset.from_dict(data)

    async def evaluate_and_log(
        self,
        questions: list[dict],
        run_name: Optional[str] = None,
        save_artifacts: bool = True,
    ) -> Dict[str, float]:
        """
        Évaluer et logger dans MLflow.

        Args:
            questions: Liste de questions d'évaluation
            run_name: Nom de la run MLflow
            save_artifacts: Sauvegarder les résultats détaillés

        Returns:
            Dict des scores {métrique: float}
        """
        log.info("[RAGAS] Évaluation démarrée", nb_questions=len(questions))

        try:
            # Construire le dataset
            dataset = await self.build_eval_dataset(questions)

            # Évaluer avec juge local (Gemma3 via Ollama) + embeddings local
            # Sans cela RAGAS tape sur OpenAI par défaut → AuthenticationError.
            ollama_base = os.getenv(
                "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
            )
            judge_llm = ChatOllama(
                model=os.getenv("RAGAS_JUDGE_MODEL", "gemma3:1b"),
                base_url=ollama_base,
                temperature=0.0,
            )
            local_embeddings = HuggingFaceEmbeddings(
                model_name=os.getenv(
                    "RAGAS_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
                ),
            )
            log.info("[RAGAS] Évaluation en cours (juge=gemma3:1b local)...")
            results = evaluate(
                dataset,
                metrics=self.METRICS,
                llm=judge_llm,
                embeddings=local_embeddings,
            )

            # Extraire les scores
            scores = {
                "faithfulness": float(results["faithfulness"]),
                "answer_relevancy": float(results["answer_relevancy"]),
                "context_precision": float(results["context_precision"]),
                "context_recall": float(results["context_recall"]),
            }

            # Démarrer une run MLflow
            with mlflow.start_run(run_name=run_name or "ragas_eval"):
                # Logger les métriques
                mlflow.log_metrics(scores)

                # Logger les paramètres
                mlflow.log_params(
                    {
                        "nb_questions": len(questions),
                        "llm_model": "gemma3:1b",
                        "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
                        "vector_store": "qdrant",
                    }
                )

                # Logger les artifacts si demandé
                if save_artifacts:
                    self._save_eval_artifacts(results, dataset, scores)

                log.info("[RAGAS] Évaluation terminée", scores=scores)

            return scores

        except Exception as e:
            log.error(f"[RAGAS] Erreur evaluate_and_log: {e}", exc_info=True)
            raise

    def _save_eval_artifacts(self, results, dataset, scores: Dict[str, float]) -> None:
        """
        Sauvegarder les résultats détaillés comme artifacts MLflow.

        Args:
            results: Résultats RAGAS bruts
            dataset: Dataset d'évaluation
            scores: Scores agrégés
        """
        try:
            # Créer un dossier temporaire
            artifact_dir = Path(
                f"/tmp/ragas_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            artifact_dir.mkdir(exist_ok=True)

            # 1. Sauvegarder les scores JSON
            scores_file = artifact_dir / "scores.json"
            with open(scores_file, "w") as f:
                json.dump(
                    {"timestamp": datetime.now().isoformat(), "scores": scores},
                    f,
                    indent=2,
                )
            mlflow.log_artifact(str(scores_file), artifact_path="evaluation")

            # 2. Sauvegarder un résumé CSV
            summary_file = artifact_dir / "summary.csv"
            summary_df = pd.DataFrame(
                {"metric": list(scores.keys()), "score": list(scores.values())}
            )
            summary_df.to_csv(summary_file, index=False)
            mlflow.log_artifact(str(summary_file), artifact_path="evaluation")

            # 3. Sauvegarder le dataset
            dataset_file = artifact_dir / "eval_dataset.json"
            dataset.to_json(dataset_file)
            mlflow.log_artifact(str(dataset_file), artifact_path="evaluation")

            log.info("[RAGAS] Artifacts sauvegardés", artifact_dir=str(artifact_dir))

        except Exception as e:
            log.warning(f"[RAGAS] Erreur save_artifacts (non-bloquant): {e}")

    def compare_runs(
        self, metric: str = "faithfulness", top_n: int = 10
    ) -> pd.DataFrame:
        """
        Comparer les meilleures runs de cette expérience.

        Args:
            metric: Métrique pour la comparaison
            top_n: Nombre de top runs

        Returns:
            DataFrame avec les runs comparées
        """
        try:
            exp = mlflow.get_experiment_by_name(self.experiment)
            if not exp:
                log.warning(f"[RAGAS] Expérience non trouvée: {self.experiment}")
                return pd.DataFrame()

            runs = mlflow.search_runs(
                experiment_ids=[exp.experiment_id], order_by=[f"metrics.{metric} DESC"]
            )

            if runs.empty:
                return pd.DataFrame()

            # Formater pour affichage
            comparison = runs.head(top_n)[
                ["run_id", "start_time", "status", f"metrics.{metric}"]
            ].copy()
            comparison.columns = ["run_id", "timestamp", "status", metric]

            log.info(
                "[RAGAS] Comparaison des runs", metric=metric, count=len(comparison)
            )

            return comparison

        except Exception as e:
            log.error(f"[RAGAS] Erreur compare_runs: {e}")
            return pd.DataFrame()

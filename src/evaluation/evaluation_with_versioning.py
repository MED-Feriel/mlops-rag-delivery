"""
evaluation_with_versioning.py — MLOPS-112: RAGAS Evaluation + Model Versioning
================================================================================
Intégration complète de l'évaluation RAGAS avec le Model Registry MLflow:
- Évaluation automatique des versions
- Comparaison des scores entre versions
- Recommandations de promotion
- Historique d'évaluation
"""

import structlog
import mlflow
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.evaluation.ragas_evaluator import RAGASEvaluator
from src.rag.rag_with_versioning import RAGPipelineWithVersioning
from config.settings import get_settings

log = structlog.get_logger()


class EvaluationWithVersioning:
    """Service d'évaluation RAGAS intégré avec le versioning des modèles."""

    def __init__(self, settings=None):
        """
        Initialiser le service d'évaluation.

        Args:
            settings: Configuration ou get_settings()
        """
        self.settings = settings or get_settings()

        # Pipeline RAG avec versioning
        self.rag_pipeline = RAGPipelineWithVersioning(self.settings)

        # Service de versioning
        self.versioning_service = self.rag_pipeline.versioning_service

        # Évaluateur RAGAS
        self.ragas_evaluator = RAGASEvaluator(
            rag_pipeline=self.rag_pipeline.rag_pipeline,  # Pipeline RAG sous-jacent
            mlflow_experiment="model_evaluation",
        )

        log.info("[Evaluation-Versioning] Service initialisé")

    async def evaluate_version(
        self,
        version: int,
        eval_questions: List[Dict[str, str]],
        eval_dataset_name: str = "test",
        batch_size: int = 5,
    ) -> Dict[str, Any]:
        """
        Évaluer une version spécifique du modèle avec RAGAS.

        Args:
            version: Numéro de version à évaluer
            eval_questions: Questions d'évaluation [{question, ground_truth}, ...]
            eval_dataset_name: Nom du dataset (test, validation, etc)
            batch_size: Nombre de questions par batch

        Returns:
            {
                "version": int,
                "eval_dataset": str,
                "scores": {faithfulness, answer_relevancy, ...},
                "timestamp": str,
                "status": "PASSED" | "FAILED"
            }
        """
        try:
            log.info(
                "[Eval-Versioning] Évaluation démarrée",
                version=version,
                questions=len(eval_questions),
            )

            # Récupérer les infos de la version
            version_info = self.versioning_service.get_model_version_info(version)
            if not version_info:
                raise ValueError(f"Version {version} non trouvée")

            # Créer une run d'évaluation
            run_name = f"eval_v{version}_{eval_dataset_name}_{datetime.now().strftime('%H%M%S')}"

            with mlflow.start_run(run_name=run_name) as run:
                # Logger les paramètres de la version
                mlflow.log_params(
                    {
                        "model_version": version,
                        "eval_dataset": eval_dataset_name,
                        "llm_model": version_info.get("tags", {}).get(
                            "llm_model", "unknown"
                        ),
                        "embedding_model": version_info.get("tags", {}).get(
                            "embedding_model", "unknown"
                        ),
                        "stage": version_info.get("stage", "unknown"),
                    }
                )

                # Évaluer par batch
                all_scores = {}
                for i in range(0, len(eval_questions), batch_size):
                    batch = eval_questions[i : i + batch_size]
                    log.info(
                        f"[Eval-Versioning] Batch {i//batch_size + 1}/{(len(eval_questions)-1)//batch_size + 1}"
                    )

                    # Évaluation RAGAS du batch
                    scores = await self.ragas_evaluator.evaluate_and_log(
                        questions=batch,
                        run_name=f"{run_name}_batch_{i//batch_size}",
                        save_artifacts=False,  # Les artefacts seront sauvegardés à la fin
                    )

                    # Accumuler les scores
                    for metric, value in scores.items():
                        if metric not in all_scores:
                            all_scores[metric] = []
                        all_scores[metric].append(value)

                # Calculer les moyennes
                avg_scores = {
                    metric: sum(values) / len(values)
                    for metric, values in all_scores.items()
                }

                # Logger les scores moyens
                mlflow.log_metrics(avg_scores)

                # Logger les tags
                mlflow.set_tags(
                    {
                        "component": "model_evaluation",
                        "model_version": version,
                        "eval_framework": "RAGAS",
                        "eval_dataset": eval_dataset_name,
                        "status": "COMPLETED",
                    }
                )

                result = {
                    "version": version,
                    "eval_dataset": eval_dataset_name,
                    "scores": avg_scores,
                    "timestamp": datetime.now().isoformat(),
                    "status": "PASSED",
                    "run_id": run.info.run_id,
                }

                log.info(
                    "[Eval-Versioning] Évaluation complétée",
                    version=version,
                    scores=avg_scores,
                )

                return result

        except Exception as e:
            log.error(f"[Eval-Versioning] Erreur évaluation: {e}", exc_info=True)
            return {
                "version": version,
                "eval_dataset": eval_dataset_name,
                "scores": {},
                "timestamp": datetime.now().isoformat(),
                "status": "FAILED",
                "error": str(e),
            }

    async def evaluate_and_promote(
        self,
        version: int,
        eval_questions: List[Dict[str, str]],
        threshold_scores: Optional[Dict[str, float]] = None,
        auto_promote: bool = False,
    ) -> Dict[str, Any]:
        """
        Évaluer une version et potentiellement la promouvoir en Production.

        Args:
            version: Version à évaluer
            eval_questions: Questions d'évaluation
            threshold_scores: Scores minimum requis {faithfulness: 0.80, ...}
            auto_promote: Promouvoir automatiquement si seuils atteints

        Returns:
            {
                "version": int,
                "eval_result": {...},
                "passes_thresholds": bool,
                "promoted": bool,
                "recommendations": [...]
            }
        """
        try:
            # Définir les seuils par défaut
            if threshold_scores is None:
                threshold_scores = {
                    "faithfulness": 0.80,
                    "answer_relevancy": 0.75,
                    "context_precision": 0.85,
                    "context_recall": 0.80,
                }

            log.info(
                "[Eval-Versioning] Évaluation + décision",
                version=version,
                thresholds=threshold_scores,
            )

            # 1. Évaluer la version
            eval_result = await self.evaluate_version(
                version=version, eval_questions=eval_questions
            )

            if eval_result["status"] == "FAILED":
                return {
                    "version": version,
                    "eval_result": eval_result,
                    "passes_thresholds": False,
                    "promoted": False,
                    "recommendations": ["Évaluation échouée. Vérifier les logs."],
                }

            # 2. Vérifier les seuils
            scores = eval_result["scores"]
            passes_thresholds = True
            failed_metrics = []

            for metric, threshold in threshold_scores.items():
                score = scores.get(metric, 0)
                if score < threshold:
                    passes_thresholds = False
                    failed_metrics.append(f"{metric}: {score:.4f} < {threshold:.4f}")

            # 3. Déterminer les recommandations
            recommendations = []
            if passes_thresholds:
                recommendations.append("✅ Tous les seuils atteints!")
                recommendations.append(f"Version {version} prête pour Production")

                if auto_promote:
                    try:
                        self.rag_pipeline.promote_to_production(version=version)
                        recommendations.append(
                            f"✅ Version {version} promue en Production"
                        )
                        promoted = True
                    except Exception as e:
                        recommendations.append(f"⚠️  Erreur promotion: {e}")
                        promoted = False
                else:
                    recommendations.append("Promotion manuelle requise")
                    promoted = False
            else:
                recommendations.append("❌ Seuils non atteints:")
                for metric_fail in failed_metrics:
                    recommendations.append(f"  • {metric_fail}")
                recommendations.append("Améliorer le modèle avant promotion")
                promoted = False

            result = {
                "version": version,
                "eval_result": eval_result,
                "passes_thresholds": passes_thresholds,
                "promoted": promoted,
                "recommendations": recommendations,
            }

            log.info(
                "[Eval-Versioning] Décision",
                version=version,
                passes=passes_thresholds,
                promoted=promoted,
            )

            return result

        except Exception as e:
            log.error(
                f"[Eval-Versioning] Erreur evaluate_and_promote: {e}", exc_info=True
            )
            return {
                "version": version,
                "eval_result": {},
                "passes_thresholds": False,
                "promoted": False,
                "recommendations": [f"Erreur: {str(e)}"],
                "error": str(e),
            }

    def compare_evaluations(
        self, version1: int, version2: int, metric: str = "faithfulness"
    ) -> Dict[str, Any]:
        """
        Comparer les évaluations de deux versions.

        Args:
            version1: Première version
            version2: Deuxième version
            metric: Métrique pour la comparaison

        Returns:
            {
                "version1": {...},
                "version2": {...},
                "winner": "v1" | "v2" | "tie",
                "improvement_percent": float
            }
        """
        try:
            # Récupérer les infos des versions
            info1 = self.versioning_service.get_model_version_info(version1)
            info2 = self.versioning_service.get_model_version_info(version2)

            if not info1 or not info2:
                log.warning("[Eval-Versioning] Versions manquantes")
                return {}

            score1 = info1.get("metrics", {}).get(metric, None)
            score2 = info2.get("metrics", {}).get(metric, None)

            result = {
                "version1": {
                    "version": version1,
                    "stage": info1.get("stage"),
                    "score": score1,
                },
                "version2": {
                    "version": version2,
                    "stage": info2.get("stage"),
                    "score": score2,
                },
                "metric": metric,
            }

            if score1 is not None and score2 is not None:
                improvement = ((score2 - score1) / score1 * 100) if score1 != 0 else 0
                result["improvement_percent"] = improvement
                result["winner"] = (
                    "v2"
                    if improvement > 0.5
                    else ("v1" if improvement < -0.5 else "tie")
                )

            log.info(
                "[Eval-Versioning] Comparaison",
                v1=version1,
                v2=version2,
                winner=result.get("winner"),
            )

            return result

        except Exception as e:
            log.error(f"[Eval-Versioning] Erreur compare: {e}", exc_info=True)
            return {}

    def get_evaluation_history(
        self, version: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Récupérer l'historique des évaluations.

        Args:
            version: Filtrer par version (None = toutes)

        Returns:
            Liste des évaluations avec dates et scores
        """
        try:
            # Récupérer toutes les runs de model_evaluation
            exp = mlflow.get_experiment_by_name("model_evaluation")
            if not exp:
                return []

            runs = mlflow.search_runs(
                experiment_ids=[exp.experiment_id], max_results=1000
            )

            history = []
            for run in runs[:50]:  # Limiter à 50 dernières
                # Extraire les infos pertinentes
                params = run.get("params", {}) if isinstance(run, dict) else {}
                metrics = run.get("metrics", {}) if isinstance(run, dict) else {}

                eval_version = params.get("model_version")

                # Filtrer par version si demandé
                if version is not None and eval_version != str(version):
                    continue

                history.append(
                    {
                        "timestamp": run.get("start_time"),
                        "version": eval_version,
                        "dataset": params.get("eval_dataset"),
                        "stage": params.get("stage"),
                        "scores": {
                            k.replace("metrics.", ""): v
                            for k, v in metrics.items()
                            if k.startswith("metrics.")
                        },
                    }
                )

            log.info(
                "[Eval-Versioning] Historique récupéré",
                total_evals=len(history),
                version=version,
            )

            return history

        except Exception as e:
            log.error(f"[Eval-Versioning] Erreur historique: {e}", exc_info=True)
            return []

    def get_evaluation_report(self) -> Dict[str, Any]:
        """
        Créer un rapport complet des évaluations.

        Returns:
            {
                "production_version": int,
                "production_scores": {...},
                "staging_evaluations": [...],
                "recent_improvements": [...],
                "recommendations": [...]
            }
        """
        try:
            # Récupérer le modèle en Production
            prod_model = self.versioning_service.get_production_model()

            result = {
                "timestamp": datetime.now().isoformat(),
                "production_version": None,
                "production_scores": {},
                "staging_evaluations": [],
                "recent_improvements": [],
                "recommendations": [],
            }

            if prod_model:
                result["production_version"] = prod_model.get("version")
                result["production_scores"] = prod_model.get("metrics", {})

            # Récupérer les versions en Staging
            staging = self.versioning_service.get_all_versions(stage="Staging")
            for v in staging:
                version_info = self.versioning_service.get_model_version_info(
                    int(v["version"])
                )
                if version_info:
                    result["staging_evaluations"].append(
                        {
                            "version": v["version"],
                            "scores": version_info.get("metrics", {}),
                            "created_at": v["created_at"],
                        }
                    )

            # Générer les recommandations
            if result["staging_evaluations"]:
                best_staging = max(
                    result["staging_evaluations"],
                    key=lambda x: x.get("scores", {}).get("faithfulness", 0),
                )
                result["recommendations"].append(
                    f"Considérer promotion v{best_staging['version']} en Production"
                )

            result["recommendations"].append(
                "Voir dashboard MLflow pour l'historique complet"
            )

            log.info(
                "[Eval-Versioning] Rapport créé",
                prod_version=result["production_version"],
                staging_count=len(result["staging_evaluations"]),
            )

            return result

        except Exception as e:
            log.error(f"[Eval-Versioning] Erreur rapport: {e}", exc_info=True)
            return {}

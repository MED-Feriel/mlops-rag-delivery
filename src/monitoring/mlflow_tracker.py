"""
mlflow_tracker.py — MLOPS-110: MLflow Model Registry & Experiment Tracking
===========================================================================
Service complet MLflow pour tracker les expériences, comparer les modèles,
et gérer le modèle registry.

FEATURES:
  - Auto-tracking des paramètres, métriques, artefacts
  - Logging des modèles (MLflow Model Format)
  - Comparaison des expériences
  - Tags pour filtrage rapide
"""

import mlflow
from mlflow.tracking import MlflowClient
import structlog
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

log = structlog.get_logger()


class MLflowTracker:
    """Gestionnaire d'expériences et de modèles avec MLflow."""

    def __init__(self, tracking_uri: str, experiment_name: str = "rag-livraison"):
        """
        Initialiser le tracker MLflow.

        Args:
            tracking_uri: URL du serveur MLflow (ex: http://localhost:5000)
            experiment_name: Nom de l'expérience par défaut
        """
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        mlflow.set_tracking_uri(tracking_uri)

        # Créer l'expérience si elle n'existe pas
        try:
            exp = mlflow.get_experiment_by_name(experiment_name)
            if exp is None:
                mlflow.create_experiment(experiment_name)
                log.info(f"[MLFLOW] Expérience créée: {experiment_name}")
            else:
                log.info(f"[MLFLOW] Expérience chargée: {experiment_name}")
            mlflow.set_experiment(experiment_name)
        except Exception as e:
            log.error(f"[MLFLOW] Erreur init expérience: {e}", exc_info=True)
            raise

        self.client = MlflowClient(tracking_uri)

    def start_run(self, run_name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """
        Démarrer une nouvelle run MLflow.

        Args:
            run_name: Nom de la run (ex: "eval_baseline_v1")
            tags: Tags pour la run (ex: {"model": "gemma3", "stage": "eval"})

        Returns:
            ID de la run
        """
        try:
            run = mlflow.start_run(run_name=run_name)
            run_id = run.info.run_id

            if tags:
                mlflow.set_tags(tags)

            log.info(f"[MLFLOW] Run démarrée", run_id=run_id, run_name=run_name)
            return run_id
        except Exception as e:
            log.error(f"[MLFLOW] Erreur start_run: {e}", exc_info=True)
            raise

    def log_params(self, params: Dict[str, Any]) -> None:
        """
        Logger les paramètres de la run.

        Args:
            params: Dict de paramètres (keys max 500 chars, values max 500 chars)
        """
        try:
            # Limiter la longueur des valeurs (MLflow limite à 500 chars)
            clean_params = {str(k): str(v)[:500] for k, v in params.items()}
            mlflow.log_params(clean_params)
            log.info(f"[MLFLOW] Params loggés", count=len(clean_params))
        except Exception as e:
            log.error(f"[MLFLOW] Erreur log_params: {e}", exc_info=True)

    def log_metrics(self, metrics: Dict[str, float], step: int = 0) -> None:
        """
        Logger les métriques de la run.

        Args:
            metrics: Dict de métriques {nom: valeur_float}
            step: Étape d'entraînement (pour les courbes d'apprentissage)
        """
        try:
            mlflow.log_metrics(metrics, step=step)
            log.info(f"[MLFLOW] Métriques loggées", count=len(metrics), step=step)
        except Exception as e:
            log.error(f"[MLFLOW] Erreur log_metrics: {e}", exc_info=True)

    def log_artifact(
        self, local_path: str, artifact_path: Optional[str] = None
    ) -> None:
        """
        Logger un fichier ou dossier comme artefact.

        Args:
            local_path: Chemin local du fichier/dossier
            artifact_path: Sous-dossier MLflow (ex: "evaluation")
        """
        try:
            mlflow.log_artifact(local_path, artifact_path=artifact_path)
            log.info(
                f"[MLFLOW] Artefact loggé", path=local_path, artifact_path=artifact_path
            )
        except Exception as e:
            log.error(f"[MLFLOW] Erreur log_artifact: {e}", exc_info=True)

    def log_model(
        self,
        model_obj: Any,
        artifact_path: str,
        signature: Optional[Any] = None,
        input_example: Optional[Any] = None,
        model_flavor: str = "python_function",
    ) -> None:
        """
        Logger un modèle MLflow Model Format.

        Args:
            model_obj: Objet modèle (ex: sklearn model, custom pipeline)
            artifact_path: Chemin de stockage (ex: "rag_model")
            signature: Signature d'entrée/sortie du modèle
            input_example: Exemple d'entrée pour inférence
            model_flavor: Flavor du modèle (sklearn, custom, etc)
        """
        try:
            if model_flavor == "sklearn":
                mlflow.sklearn.log_model(model_obj, artifact_path=artifact_path)
            else:
                # Pour les modèles custom
                mlflow.pyfunc.log_model(
                    artifact_path=artifact_path,
                    python_model=model_obj,
                    signature=signature,
                    input_example=input_example,
                )
            log.info(f"[MLFLOW] Modèle loggé", artifact_path=artifact_path)
        except Exception as e:
            log.error(f"[MLFLOW] Erreur log_model: {e}", exc_info=True)

    def log_eval_results(
        self, eval_scores: Dict[str, float], eval_name: str = "RAGAS"
    ) -> None:
        """
        Logger les résultats d'évaluation RAG.

        Args:
            eval_scores: Dict {métrique: score}
            eval_name: Nom de l'éval (RAGAS, BLEU, etc)
        """
        try:
            # Logger les métriques
            self.log_metrics(eval_scores)

            # Logger un artefact JSON
            eval_data = {
                "eval_name": eval_name,
                "timestamp": datetime.now().isoformat(),
                "scores": eval_scores,
            }
            artifact_file = f"/tmp/{eval_name.lower()}_results.json"
            with open(artifact_file, "w") as f:
                json.dump(eval_data, f, indent=2)
            self.log_artifact(artifact_file, artifact_path="evaluation")

            log.info(f"[MLFLOW] Résultats {eval_name} loggés", scores=eval_scores)
        except Exception as e:
            log.error(f"[MLFLOW] Erreur log_eval_results: {e}", exc_info=True)

    def end_run(self, status: str = "FINISHED") -> None:
        """Terminer la run courante."""
        try:
            mlflow.end_run(status=status)
            log.info(f"[MLFLOW] Run terminée", status=status)
        except Exception as e:
            log.error(f"[MLFLOW] Erreur end_run: {e}", exc_info=True)

    def compare_experiments(
        self, metric_name: str = "faithfulness", top_n: int = 10
    ) -> pd.DataFrame:
        """
        Comparer les meilleures runs d'une expérience sur une métrique.

        Args:
            metric_name: Nom de la métrique (ex: "faithfulness")
            top_n: Nombre de top runs à retourner

        Returns:
            DataFrame avec les runs comparées
        """
        try:
            exp = mlflow.get_experiment_by_name(self.experiment_name)
            if not exp:
                log.warning(f"[MLFLOW] Expérience non trouvée: {self.experiment_name}")
                return pd.DataFrame()

            # Récupérer toutes les runs
            runs = mlflow.search_runs(
                experiment_ids=[exp.experiment_id],
                order_by=[f"metrics.{metric_name} DESC"],
            )

            if runs.empty:
                log.warning(f"[MLFLOW] Aucune run trouvée")
                return pd.DataFrame()

            # Garder les top N
            comparison_df = runs.head(top_n)[
                [
                    "run_id",
                    "start_time",
                    "status",
                    f"params.llm_model",
                    f"params.embedding_model",
                    f"metrics.{metric_name}",
                ]
            ].copy()

            comparison_df.columns = [
                "run_id",
                "timestamp",
                "status",
                "llm_model",
                "embedding_model",
                metric_name,
            ]

            log.info(
                f"[MLFLOW] Comparaison réalisée",
                metric=metric_name,
                count=len(comparison_df),
            )

            return comparison_df
        except Exception as e:
            log.error(f"[MLFLOW] Erreur compare_experiments: {e}", exc_info=True)
            return pd.DataFrame()

    def get_best_run(self, metric_name: str = "faithfulness") -> Optional[Dict]:
        """
        Récupérer la meilleure run d'une expérience.

        Args:
            metric_name: Métrique pour évaluer la meilleure run

        Returns:
            Dict avec infos de la run ou None
        """
        try:
            exp = mlflow.get_experiment_by_name(self.experiment_name)
            if not exp:
                return None

            runs = mlflow.search_runs(
                experiment_ids=[exp.experiment_id],
                order_by=[f"metrics.{metric_name} DESC"],
            )

            if runs.empty:
                return None

            best_run = runs.iloc[0]
            result = {
                "run_id": best_run["run_id"],
                "status": best_run["status"],
                "metrics": {
                    col.replace("metrics.", ""): best_run[col]
                    for col in best_run.index
                    if col.startswith("metrics.")
                },
                "params": {
                    col.replace("params.", ""): best_run[col]
                    for col in best_run.index
                    if col.startswith("params.")
                },
            }

            log.info(
                f"[MLFLOW] Meilleure run trouvée",
                run_id=best_run["run_id"],
                metric=metric_name,
            )

            return result
        except Exception as e:
            log.error(f"[MLFLOW] Erreur get_best_run: {e}", exc_info=True)
            return None

    def register_model(
        self, run_id: str, artifact_path: str, model_name: str, stage: str = "Staging"
    ) -> None:
        """
        Enregistrer un modèle dans le Model Registry.

        Args:
            run_id: ID de la run
            artifact_path: Chemin de l'artefact (ex: "rag_model")
            model_name: Nom du modèle dans le registry
            stage: Stage du modèle (Staging, Production, Archived)
        """
        try:
            model_uri = f"runs:/{run_id}/{artifact_path}"
            mv = mlflow.register_model(model_uri, model_name)

            # Optionnel: passer à Production
            if stage == "Production":
                mlflow.tracking.MlflowClient().transition_model_version_stage(
                    name=model_name, version=mv.version, stage="Production"
                )

            log.info(
                f"[MLFLOW] Modèle enregistré",
                model_name=model_name,
                version=mv.version,
                stage=stage,
            )
        except Exception as e:
            log.error(f"[MLFLOW] Erreur register_model: {e}", exc_info=True)

    def get_model_versions(self, model_name: str) -> List[Dict]:
        """
        Récupérer toutes les versions d'un modèle.

        Args:
            model_name: Nom du modèle

        Returns:
            Liste des versions
        """
        try:
            versions = self.client.get_latest_versions(model_name)
            result = []
            for v in versions:
                result.append(
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "status": v.status,
                        "creation_time": v.creation_timestamp,
                    }
                )
            log.info(
                f"[MLFLOW] Versions récupérées",
                model_name=model_name,
                count=len(result),
            )
            return result
        except Exception as e:
            log.error(f"[MLFLOW] Erreur get_model_versions: {e}", exc_info=True)
            return []

    @staticmethod
    def get_tracking_uri_dashboard() -> str:
        """Retourner l'URL du dashboard MLflow."""
        return mlflow.get_tracking_uri()


# Context manager pour simplifier les runs
class MLflowRun:
    """Context manager pour gérer les runs MLflow."""

    def __init__(
        self,
        tracker: MLflowTracker,
        run_name: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        self.tracker = tracker
        self.run_name = run_name
        self.tags = tags or {}
        self.run_id = None

    def __enter__(self):
        self.run_id = self.tracker.start_run(self.run_name, self.tags)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "FAILED" if exc_type else "FINISHED"
        self.tracker.end_run(status=status)
        if exc_type:
            log.error(f"[MLFLOW] Run échouée", exc_type=exc_type, exc_val=exc_val)

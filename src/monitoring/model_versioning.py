"""
model_versioning.py — MLOPS-111: MLflow Model Registry & Versioning
====================================================================
Gestion complète du versioning des modèles RAG:
- Enregistrement automatique des modèles RAG (LLM + embedder)
- Gestion des versions et stages (Staging, Production, Archived)
- Tracking des performances entre versions
- Sélection de modèle par version/stage
"""

import mlflow
from mlflow.tracking import MlflowClient
import structlog
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import hashlib

log = structlog.get_logger()


class RAGModelVersion:
    """Représente une version du modèle RAG complet."""

    def __init__(
        self,
        run_id: str,
        llm_model: str,
        embedding_model: str,
        version: int,
        metrics: Dict[str, float],
        config: Dict[str, Any],
    ):
        """
        Créer une version de modèle RAG.

        Args:
            run_id: ID de la run MLflow
            llm_model: Modèle LLM (ex: gemma3:1b)
            embedding_model: Modèle d'embedding (ex: all-MiniLM-L6-v2)
            version: Numéro de version
            metrics: Métriques d'évaluation
            config: Configuration du modèle
        """
        self.run_id = run_id
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.version = version
        self.metrics = metrics
        self.config = config
        self.created_at = datetime.now().isoformat()

        # Générer un hash pour vérifier l'intégrité
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Générer un hash de la configuration du modèle."""
        config_str = f"{self.llm_model}:{self.embedding_model}:{json.dumps(self.config, sort_keys=True)}"
        return hashlib.md5(config_str.encode()).hexdigest()[:8]

    def to_dict(self) -> Dict[str, Any]:
        """Convertir la version en dictionnaire."""
        return {
            "run_id": self.run_id,
            "llm_model": self.llm_model,
            "embedding_model": self.embedding_model,
            "version": self.version,
            "metrics": self.metrics,
            "config": self.config,
            "created_at": self.created_at,
            "hash": self.hash,
        }


class ModelVersioningService:
    """Service de gestion des versions de modèles RAG dans MLflow."""

    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        model_registry_name: str = "rag-livraison-model",
    ):
        """
        Initialiser le service de versioning.

        Args:
            tracking_uri: URI du serveur MLflow
            model_registry_name: Nom du modèle dans le registry
        """
        self.tracking_uri = tracking_uri
        self.model_registry_name = model_registry_name
        mlflow.set_tracking_uri(tracking_uri)
        self.client = MlflowClient(tracking_uri)

        # Expérience pour le versioning
        self.experiment_name = "model_registry"
        try:
            exp = mlflow.get_experiment_by_name(self.experiment_name)
            if exp is None:
                mlflow.create_experiment(self.experiment_name)
            mlflow.set_experiment(self.experiment_name)
            log.info(
                "[ModelVersioning] Service initialisé", model_name=model_registry_name
            )
        except Exception as e:
            log.error(f"[ModelVersioning] Erreur init: {e}", exc_info=True)
            raise

    def register_rag_model(
        self,
        run_id: str,
        llm_model: str,
        embedding_model: str,
        metrics: Dict[str, float],
        config: Dict[str, Any],
        description: str = "",
    ) -> str:
        """
        Enregistrer une version du modèle RAG dans le Model Registry.

        Args:
            run_id: ID de la run MLflow contenant le modèle
            llm_model: Modèle LLM (ex: gemma3:1b)
            embedding_model: Modèle d'embedding
            metrics: Métriques d'évaluation (faithfulness, latency_ms, etc)
            config: Configuration du modèle
            description: Description de la version

        Returns:
            Version du modèle enregistré
        """
        try:
            # Créer un artefact avec les métadonnées du modèle
            model_metadata = {
                "llm_model": llm_model,
                "embedding_model": embedding_model,
                "metrics": metrics,
                "config": config,
                "registered_at": datetime.now().isoformat(),
                "description": description,
            }

            # Sauvegarder les métadonnées
            metadata_path = Path("/tmp") / f"rag_model_{run_id}.json"
            with open(metadata_path, "w") as f:
                json.dump(model_metadata, f, indent=2)

            # Enregistrer le modèle
            model_uri = f"runs:/{run_id}/rag_model"

            try:
                mv = mlflow.register_model(model_uri, self.model_registry_name)
                version = mv.version
            except Exception as e:
                # Si le modèle existe déjà, créer une nouvelle version
                if "already exists" in str(e):
                    log.info(
                        "[ModelVersioning] Modèle existe déjà, création nouvelle version"
                    )
                    mv = mlflow.register_model(model_uri, self.model_registry_name)
                    version = mv.version
                else:
                    raise

            # Ajouter les métadonnées dans la run
            with mlflow.start_run(run_id=run_id):
                mlflow.log_dict(model_metadata, "model_metadata.json")
                mlflow.log_param("model_registry_version", version)
                mlflow.set_tag("registered_in_model_registry", "true")
                mlflow.set_tag("llm_model", llm_model)
                mlflow.set_tag("embedding_model", embedding_model)

            log.info(
                "[ModelVersioning] Modèle enregistré",
                model_name=self.model_registry_name,
                version=version,
                llm_model=llm_model,
            )

            return version

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur registration: {e}", exc_info=True)
            raise

    def transition_model_stage(
        self, version: int, stage: str, archive_existing: bool = True
    ) -> None:
        """
        Transitionner un modèle vers un nouveau stage.

        Args:
            version: Numéro de version
            stage: Nouveau stage (Staging, Production, Archived)
            archive_existing: Archiver les versions précédentes du même stage
        """
        try:
            if stage not in ["Staging", "Production", "Archived"]:
                raise ValueError(f"Stage invalide: {stage}")

            # Si on envoie en Production, archiver les précédentes versions Production
            if archive_existing and stage == "Production":
                try:
                    versions = self.client.get_latest_versions(self.model_registry_name)
                    for v in versions:
                        if v.current_stage == "Production":
                            self.client.transition_model_version_stage(
                                name=self.model_registry_name,
                                version=v.version,
                                stage="Archived",
                            )
                            log.info(
                                "[ModelVersioning] Version archivée",
                                model_name=self.model_registry_name,
                                version=v.version,
                            )
                except Exception as e:
                    log.warning(f"[ModelVersioning] Erreur archive: {e}")

            # Transitionner la nouvelle version
            self.client.transition_model_version_stage(
                name=self.model_registry_name, version=version, stage=stage
            )

            log.info(
                "[ModelVersioning] Version transitionée",
                model_name=self.model_registry_name,
                version=version,
                stage=stage,
            )

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur transition: {e}", exc_info=True)
            raise

    def get_model_version_info(self, version: Optional[int] = None) -> Dict[str, Any]:
        """
        Récupérer les informations d'une version du modèle.

        Args:
            version: Numéro de version (None = dernière)

        Returns:
            Dictionnaire avec les infos de version
        """
        try:
            versions = self.client.get_latest_versions(self.model_registry_name)

            if version:
                # Version spécifique
                target_version = next(
                    (v for v in versions if int(v.version) == version), None
                )
                if not target_version:
                    log.warning(f"[ModelVersioning] Version non trouvée: {version}")
                    return {}
            else:
                # Dernière version
                target_version = (
                    max(versions, key=lambda v: int(v.version)) if versions else None
                )

            if not target_version:
                return {}

            # Récupérer les métadonnées depuis la run
            run_id = target_version.source.split("/")[-2]
            run = mlflow.get_run(run_id)

            result = {
                "version": target_version.version,
                "stage": target_version.current_stage,
                "status": target_version.status,
                "created_at": datetime.fromtimestamp(
                    target_version.creation_timestamp / 1000
                ).isoformat(),
                "run_id": run_id,
                "metrics": dict(run.data.metrics) if run.data.metrics else {},
                "params": dict(run.data.params) if run.data.params else {},
                "tags": dict(run.data.tags) if run.data.tags else {},
            }

            log.info(
                "[ModelVersioning] Infos version récupérées",
                model_name=self.model_registry_name,
                version=target_version.version,
            )

            return result

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur get_info: {e}", exc_info=True)
            return {}

    def get_all_versions(self, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Récupérer toutes les versions du modèle.

        Args:
            stage: Filtrer par stage (Production, Staging, Archived)

        Returns:
            Liste des versions
        """
        try:
            versions = self.client.get_latest_versions(self.model_registry_name)

            result = []
            for v in versions:
                if stage and v.current_stage != stage:
                    continue

                result.append(
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "status": v.status,
                        "created_at": datetime.fromtimestamp(
                            v.creation_timestamp / 1000
                        ).isoformat(),
                    }
                )

            log.info(
                "[ModelVersioning] Versions lisées",
                model_name=self.model_registry_name,
                count=len(result),
                stage=stage,
            )

            return sorted(result, key=lambda x: int(x["version"]), reverse=True)

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur get_all: {e}", exc_info=True)
            return []

    def compare_versions(
        self, version1: int, version2: int, metric: str = "faithfulness"
    ) -> Dict[str, Any]:
        """
        Comparer deux versions du modèle.

        Args:
            version1: Première version
            version2: Deuxième version
            metric: Métrique à comparer

        Returns:
            Dictionnaire avec la comparaison
        """
        try:
            info1 = self.get_model_version_info(version1)
            info2 = self.get_model_version_info(version2)

            if not info1 or not info2:
                log.warning("[ModelVersioning] Une ou deux versions manquent")
                return {}

            metric1 = info1.get("metrics", {}).get(metric, None)
            metric2 = info2.get("metrics", {}).get(metric, None)

            result = {
                "metric": metric,
                "version1": {
                    "version": version1,
                    "value": metric1,
                    "stage": info1.get("stage"),
                },
                "version2": {
                    "version": version2,
                    "value": metric2,
                    "stage": info2.get("stage"),
                },
            }

            # Calcul de l'amélioration
            if metric1 is not None and metric2 is not None:
                improvement = (
                    ((metric2 - metric1) / metric1 * 100) if metric1 != 0 else 0
                )
                result["improvement_percent"] = improvement
                result["winner"] = (
                    "v2" if improvement > 0 else ("v1" if improvement < 0 else "tie")
                )

            log.info(
                "[ModelVersioning] Versions comparées",
                version1=version1,
                version2=version2,
                metric=metric,
            )

            return result

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur compare: {e}", exc_info=True)
            return {}

    def log_evaluation_results(
        self,
        version: int,
        eval_metrics: Dict[str, float],
        eval_dataset: str = "test",
        eval_framework: str = "RAGAS",
    ) -> None:
        """
        Logger les résultats d'évaluation pour une version.

        Args:
            version: Numéro de version
            eval_metrics: Métriques d'évaluation {faithfulness, answer_relevancy, etc}
            eval_dataset: Nom du dataset (test, validation, etc)
            eval_framework: Framework d'évaluation (RAGAS, BLEU, etc)
        """
        try:
            info = self.get_model_version_info(version)
            if not info:
                log.warning(f"[ModelVersioning] Version non trouvée: {version}")
                return

            run_id = info["run_id"]

            # Créer une nouvelle run pour les résultats d'éval
            with mlflow.start_run():
                mlflow.set_experiment("model_evaluation")

                # Logger les métriques d'éval
                mlflow.log_metrics(eval_metrics)

                # Logger les paramètres
                mlflow.log_params(
                    {
                        "model_version": version,
                        "parent_run_id": run_id,
                        "eval_dataset": eval_dataset,
                        "eval_framework": eval_framework,
                    }
                )

                # Logger les tags
                mlflow.set_tags(
                    {
                        "component": "model_evaluation",
                        "model_registry_version": version,
                        "eval_framework": eval_framework,
                        "stage": info.get("stage", "unknown"),
                    }
                )

                # Sauvegarder les résultats en artefact
                eval_result = {
                    "version": version,
                    "eval_dataset": eval_dataset,
                    "eval_framework": eval_framework,
                    "timestamp": datetime.now().isoformat(),
                    "metrics": eval_metrics,
                }

                artifact_path = Path("/tmp") / f"eval_v{version}_{eval_dataset}.json"
                with open(artifact_path, "w") as f:
                    json.dump(eval_result, f, indent=2)

                mlflow.log_artifact(str(artifact_path), artifact_path="evaluation")

                log.info(
                    "[ModelVersioning] Résultats d'éval loggés",
                    version=version,
                    eval_framework=eval_framework,
                    metrics_count=len(eval_metrics),
                )

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur log_evaluation: {e}", exc_info=True)

    def get_production_model(self) -> Optional[Dict[str, Any]]:
        """
        Récupérer la version du modèle en Production.

        Returns:
            Info de la version en Production ou None
        """
        try:
            prod_versions = self.get_all_versions(stage="Production")
            if prod_versions:
                return self.get_model_version_info(int(prod_versions[0]["version"]))
            return None
        except Exception as e:
            log.error(f"[ModelVersioning] Erreur get_production: {e}", exc_info=True)
            return None

    def create_model_report(self) -> Dict[str, Any]:
        """
        Créer un rapport complet du modèle et de ses versions.

        Returns:
            Rapport avec toutes les informations
        """
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "model_name": self.model_registry_name,
                "versions": self.get_all_versions(),
                "production_model": self.get_production_model(),
                "staging_models": self.get_all_versions(stage="Staging"),
                "archived_models": self.get_all_versions(stage="Archived"),
            }

            log.info(
                "[ModelVersioning] Rapport créé",
                model_name=self.model_registry_name,
                total_versions=len(report["versions"]),
            )

            return report

        except Exception as e:
            log.error(f"[ModelVersioning] Erreur create_report: {e}", exc_info=True)
            return {}


class ModelVersionManager:
    """
    Façade simple sur le Model Registry pour le modèle Gemma3-RAG.

    Utilisée par l'API FastAPI pour:
      - récupérer la version du modèle en Production au démarrage,
      - logger cette version dans chaque run d'inférence,
      - lister les versions disponibles.

    Délègue à ModelVersioningService pour la logique MLflow.
    """

    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        model_name: str = "gemma3-rag-livraison",
    ):
        self.model_name = model_name
        self.tracking_uri = tracking_uri
        self._service = ModelVersioningService(
            tracking_uri=tracking_uri, model_registry_name=model_name
        )
        self.client = self._service.client

    def get_production_version(self) -> Optional[Dict[str, Any]]:
        """Retourner {version, stage, run_id, semver, ...} de la Production, ou None."""
        try:
            versions = self.client.search_model_versions(f"name='{self.model_name}'")
            prod = [v for v in versions if v.current_stage == "Production"]
            if not prod:
                log.warning(
                    "[ModelVersionManager] Aucune version Production",
                    model=self.model_name,
                )
                return None
            latest = max(prod, key=lambda v: int(v.version))
            return {
                "version": latest.version,
                "stage": latest.current_stage,
                "run_id": latest.run_id,
                "source": latest.source,
                "tags": dict(latest.tags) if latest.tags else {},
                "semver": (latest.tags or {}).get("semver"),
                "model_name": self.model_name,
            }
        except Exception as e:
            log.error(
                f"[ModelVersionManager] Erreur get_production_version: {e}",
                exc_info=True,
            )
            return None

    def promote_to_production(
        self, version: int, archive_existing: bool = True
    ) -> bool:
        """Promouvoir une version vers Production (archive l'ancienne par défaut)."""
        try:
            self._service.transition_model_stage(
                version=version, stage="Production", archive_existing=archive_existing
            )
            return True
        except Exception as e:
            log.error(
                f"[ModelVersionManager] Erreur promote_to_production: {e}",
                exc_info=True,
            )
            return False

    def list_versions(self, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lister toutes les versions (optionnellement filtrées par stage)."""
        try:
            versions = self.client.search_model_versions(f"name='{self.model_name}'")
            result = []
            for v in versions:
                if stage and v.current_stage != stage:
                    continue
                result.append(
                    {
                        "version": v.version,
                        "stage": v.current_stage,
                        "status": v.status,
                        "run_id": v.run_id,
                        "semver": (v.tags or {}).get("semver"),
                        "created_at": datetime.fromtimestamp(
                            v.creation_timestamp / 1000
                        ).isoformat(),
                    }
                )
            return sorted(result, key=lambda x: int(x["version"]), reverse=True)
        except Exception as e:
            log.error(f"[ModelVersionManager] Erreur list_versions: {e}", exc_info=True)
            return []

"""
rag_with_versioning.py — MLOPS-111: RAG Pipeline avec Model Versioning
========================================================================
Pipeline RAG qui enregistre automatiquement les versions des modèles
dans MLflow Model Registry et gère les transitions de stages.
"""

import structlog
from typing import Dict, Any, Optional

from src.rag.rag_pipeline_with_mlflow import RAGPipelineWithMLflow
from src.monitoring.model_versioning import ModelVersioningService
from config.settings import get_settings

log = structlog.get_logger()


class RAGPipelineWithVersioning:
    """Pipeline RAG avec gestion automatique du versioning des modèles."""

    def __init__(self, settings=None):
        """
        Initialiser le pipeline avec versioning.

        Args:
            settings: Configuration (ou utilise get_settings())
        """
        self.settings = settings or get_settings()

        # Pipeline RAG existant
        self.rag_pipeline = RAGPipelineWithMLflow(self.settings)

        # Service de versioning
        self.versioning_service = ModelVersioningService(
            tracking_uri=self.settings.mlflow_tracking_uri,
            model_registry_name="rag-livraison-model",
        )

        log.info("[RAG-Versioning] Pipeline initialisé avec versioning")

    async def query_with_version(
        self,
        question: str,
        top_k: int = 8,
        filters: Optional[dict] = None,
        version: Optional[int] = None,
        run_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Requête RAG avec suivi du versioning du modèle utilisé.

        Args:
            question: Question de l'utilisateur
            top_k: Nombre de chunks
            filters: Filtres Qdrant
            version: Version spécifique du modèle (None = production)
            run_name: Nom de la run MLflow

        Returns:
            {"answer": str, "contexts": list, "metrics": dict, "model_version": int}
        """
        try:
            # Récupérer la version du modèle
            if version is None:
                prod_model = self.versioning_service.get_production_model()
                if prod_model:
                    version = int(prod_model["version"])
                    log.info(
                        f"[RAG-Versioning] Utilisant version production: {version}"
                    )

            # Exécuter la requête RAG standard
            result = await self.rag_pipeline.query(
                question=question, top_k=top_k, filters=filters, run_name=run_name
            )

            # Ajouter les infos de versioning
            result["model_version"] = version
            result["model_name"] = "rag-livraison-model"

            log.info(
                "[RAG-Versioning] Query complétée",
                version=version,
                total_time_ms=result["metrics"]["total_time_ms"],
            )

            return result

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur query: {e}", exc_info=True)
            raise

    def register_model_version(
        self, run_id: str, metrics: Dict[str, float], description: str = ""
    ) -> str:
        """
        Enregistrer une nouvelle version du modèle RAG.

        Args:
            run_id: ID de la run RAG à enregistrer
            metrics: Métriques d'évaluation
            description: Description de la version

        Returns:
            Numéro de version enregistré
        """
        try:
            version = self.versioning_service.register_rag_model(
                run_id=run_id,
                llm_model=self.settings.ollama_model,
                embedding_model=self.settings.embedding_model,
                metrics=metrics,
                config={
                    "top_k": 8,
                    "embedding_batch_size": self.settings.embedding_batch_size,
                    "qdrant_collection": self.settings.qdrant_collection,
                    "ollama_temperature": 0.7,
                },
                description=description,
            )

            log.info(
                "[RAG-Versioning] Modèle enregistré",
                version=version,
                llm_model=self.settings.ollama_model,
            )

            return version

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur registration: {e}", exc_info=True)
            raise

    def promote_to_production(self, version: int) -> None:
        """
        Promouvoir une version en Production.

        Args:
            version: Numéro de version à promouvoir
        """
        try:
            # Récupérer les infos de la version
            version_info = self.versioning_service.get_model_version_info(version)

            if not version_info:
                raise ValueError(f"Version non trouvée: {version}")

            # Transitionner vers Production (archive les précédentes)
            self.versioning_service.transition_model_stage(
                version=version, stage="Production", archive_existing=True
            )

            log.info(
                "[RAG-Versioning] Version promue en Production",
                version=version,
                previous_stage=version_info.get("stage"),
            )

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur promotion: {e}", exc_info=True)
            raise

    def get_model_comparison(self, v1: int, v2: int) -> Dict[str, Any]:
        """
        Comparer deux versions du modèle.

        Args:
            v1: Première version
            v2: Deuxième version

        Returns:
            Résultats de la comparaison
        """
        try:
            comparison = self.versioning_service.compare_versions(
                version1=v1,
                version2=v2,
                metric="latency_ms",  # Utiliser latency comme métrique de base
            )

            log.info(
                "[RAG-Versioning] Versions comparées",
                v1=v1,
                v2=v2,
                winner=comparison.get("winner"),
            )

            return comparison

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur comparison: {e}", exc_info=True)
            return {}

    def get_model_report(self) -> Dict[str, Any]:
        """
        Récupérer un rapport complet du modèle et de ses versions.

        Returns:
            Rapport avec toutes les versions et états
        """
        try:
            report = self.versioning_service.create_model_report()

            log.info(
                "[RAG-Versioning] Rapport créé",
                total_versions=len(report.get("versions", [])),
            )

            return report

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur report: {e}", exc_info=True)
            return {}

    def log_evaluation(
        self, version: int, eval_metrics: Dict[str, float], eval_dataset: str = "test"
    ) -> None:
        """
        Logger les résultats d'évaluation pour une version.

        Args:
            version: Numéro de version
            eval_metrics: Métriques d'évaluation RAGAS
            eval_dataset: Nom du dataset
        """
        try:
            self.versioning_service.log_evaluation_results(
                version=version,
                eval_metrics=eval_metrics,
                eval_dataset=eval_dataset,
                eval_framework="RAGAS",
            )

            log.info(
                "[RAG-Versioning] Évaluation loggée",
                version=version,
                dataset=eval_dataset,
            )

        except Exception as e:
            log.error(f"[RAG-Versioning] Erreur eval: {e}", exc_info=True)

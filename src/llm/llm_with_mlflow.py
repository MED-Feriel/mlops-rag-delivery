"""
llm_with_mlflow.py — MLOPS-Gemma: MLflow Tracking pour LLM Gemma3
==================================================================
Wrapper du LLMService avec tracking MLflow complet:
- Paramètres du modèle
- Latencies et performances
- Requêtes et réponses
- Token counts
- Métriques d'évaluation
"""

import mlflow
import structlog
import time
from typing import Optional, Dict, Any
from datetime import datetime

from src.llm.llm_service import LLMService

log = structlog.get_logger()


class LLMWithMLflow:
    """Wrapper LLMService avec MLflow tracking automatique."""

    def __init__(
        self,
        host: str,
        port: int,
        model: str = "gemma3:1b",
        timeout: int = 120,
        mlflow_tracking_uri: str = "http://localhost:5000",
        experiment_name: str = "llm_gemma_inference",
    ):
        """
        Initialiser le service LLM avec MLflow tracking.

        Args:
            host: Host Ollama (ex: localhost)
            port: Port Ollama (ex: 11434)
            model: Modèle à utiliser (ex: gemma3:1b)
            timeout: Timeout des requêtes (secondes)
            mlflow_tracking_uri: URL du serveur MLflow
            experiment_name: Nom de l'expérience MLflow
        """
        self.llm = LLMService(host=host, port=port, model=model, timeout=timeout)
        self.model = model
        self.host = host
        self.port = port
        self.timeout = timeout

        # Configuration MLflow
        mlflow.set_tracking_uri(mlflow_tracking_uri)

        try:
            exp = mlflow.get_experiment_by_name(experiment_name)
            if exp is None:
                mlflow.create_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)
            log.info(f"[MLflow] Expérience {experiment_name} initialisée")
        except Exception as e:
            log.error(f"[MLflow] Erreur init expérience: {e}")
            raise

    def _log_model_params(self):
        """Logger les paramètres du modèle."""
        mlflow.log_params(
            {
                "model": self.model,
                "host": self.host,
                "port": self.port,
                "timeout": self.timeout,
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 512,
            }
        )
        log.info("[MLflow] Paramètres du modèle loggés")

    async def generate(
        self,
        context: str,
        question: str,
        run_name: Optional[str] = None,
        create_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Générer une réponse avec MLflow tracking.

        Args:
            context: Contexte (documents retrievés)
            question: Question de l'utilisateur
            run_name: Nom de la run MLflow
            create_run: Si False, utilise la run courante (pour runs imbriquées)

        Returns:
            {
                "response": str,
                "latency_ms": float,
                "context_length": int,
                "question_length": int,
                "response_length": int
            }
        """
        # Générer un nom de run si nécessaire
        if not run_name:
            run_name = f"generate_{datetime.now().isoformat()}"

        # Wrapper pour gérer les runs imbriquées
        if create_run:
            ctx = mlflow.start_run(run_name=run_name)
        else:
            # Utiliser un context manager no-op pour la cohérence
            from contextlib import nullcontext

            ctx = nullcontext(mlflow.active_run())

        with ctx as run:
            try:
                # Logger les paramètres
                self._log_model_params()

                # Logger les entrées
                mlflow.log_params(
                    {
                        "context_length": len(context),
                        "question_length": len(question),
                    }
                )

                # Exécuter la génération avec chrono
                start = time.time()
                response = await self.llm.generate(context, question)
                latency_ms = (time.time() - start) * 1000

                # Logger les métriques
                mlflow.log_metrics(
                    {
                        "latency_ms": latency_ms,
                        "response_length": len(response),
                        "context_chars": len(context),
                        "question_chars": len(question),
                    }
                )

                # Logger les tags
                mlflow.set_tags(
                    {
                        "component": "llm_inference",
                        "model_type": "gemma3",
                        "method": "generate",
                        "sprint": "sprint6",
                    }
                )

                log.info(
                    "[MLflow] Generate loggée",
                    run_id=run.info.run_id,
                    latency_ms=latency_ms,
                    response_len=len(response),
                )

                return {
                    "response": response,
                    "latency_ms": latency_ms,
                    "context_length": len(context),
                    "question_length": len(question),
                    "response_length": len(response),
                    "run_id": run.info.run_id,
                }

            except Exception as e:
                mlflow.log_param("error", str(e))
                log.error(f"[MLflow] Erreur generate: {e}", exc_info=True)
                raise

    async def chat(
        self,
        messages: list[dict],
        context: str,
        run_name: Optional[str] = None,
        create_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Chat avec historique et MLflow tracking.

        Args:
            messages: Liste des messages [{role, content}, ...]
            context: Contexte pour la réponse
            run_name: Nom de la run MLflow
            create_run: Si False, utilise la run courante (pour runs imbriquées)

        Returns:
            {
                "response": str,
                "latency_ms": float,
                "messages_count": int,
                "run_id": str
            }
        """
        if not run_name:
            run_name = f"chat_{datetime.now().isoformat()}"

        # Wrapper pour gérer les runs imbriquées
        if create_run:
            ctx = mlflow.start_run(run_name=run_name)
        else:
            from contextlib import nullcontext

            ctx = nullcontext(mlflow.active_run())

        with ctx as run:
            try:
                # Logger les paramètres
                self._log_model_params()

                # Logger les entrées
                mlflow.log_params(
                    {
                        "messages_count": len(messages),
                        "context_length": len(context),
                        "last_message_length": (
                            len(messages[-1]["content"]) if messages else 0
                        ),
                    }
                )

                # Exécuter le chat
                start = time.time()
                response = await self.llm.chat(messages, context)
                latency_ms = (time.time() - start) * 1000

                # Logger les métriques
                mlflow.log_metrics(
                    {
                        "latency_ms": latency_ms,
                        "response_length": len(response),
                        "context_chars": len(context),
                        "messages_count": len(messages),
                    }
                )

                # Logger les tags
                mlflow.set_tags(
                    {
                        "component": "llm_inference",
                        "model_type": "gemma3",
                        "method": "chat",
                        "sprint": "sprint6",
                    }
                )

                log.info(
                    "[MLflow] Chat loggée",
                    run_id=run.info.run_id if run else "no-run",
                    latency_ms=latency_ms,
                    messages=len(messages),
                )

                return {
                    "response": response,
                    "latency_ms": latency_ms,
                    "messages_count": len(messages),
                    "response_length": len(response),
                    "run_id": run.info.run_id if run else "no-run",
                }

            except Exception as e:
                mlflow.log_param("error", str(e))
                log.error(f"[MLflow] Erreur chat: {e}", exc_info=True)
                raise

    async def compare_models(
        self,
        test_cases: list[Dict[str, str]],
        experiment_name: str = "model_comparison",
    ) -> Dict[str, Any]:
        """
        Comparer les performances de génération sur plusieurs test cases.

        Args:
            test_cases: Liste de {"context": str, "question": str}
            experiment_name: Nom de l'expérience pour les comparaisons

        Returns:
            {
                "avg_latency_ms": float,
                "total_runs": int,
                "test_cases_passed": int,
                "experiment_name": str
            }
        """
        # Créer/utiliser l'expérience
        try:
            exp = mlflow.get_experiment_by_name(experiment_name)
            if exp is None:
                mlflow.create_experiment(experiment_name)
            mlflow.set_experiment(experiment_name)
        except Exception as e:
            log.error(f"[MLflow] Erreur création expérience: {e}")
            raise

        results = {
            "test_results": [],
            "avg_latency_ms": 0,
            "total_runs": len(test_cases),
            "test_cases_passed": 0,
        }

        total_latency = 0

        for idx, test_case in enumerate(test_cases):
            try:
                result = await self.generate(
                    context=test_case["context"],
                    question=test_case["question"],
                    run_name=f"comparison_test_{idx+1}",
                )

                results["test_results"].append(
                    {
                        "test_id": idx + 1,
                        "question": test_case["question"],
                        "latency_ms": result["latency_ms"],
                        "response_preview": result["response"][:100],
                    }
                )

                total_latency += result["latency_ms"]
                results["test_cases_passed"] += 1

                log.info(f"[MLflow] Test case {idx+1}/{len(test_cases)} OK")

            except Exception as e:
                log.error(f"[MLflow] Erreur test case {idx+1}: {e}")
                results["test_results"].append({"test_id": idx + 1, "error": str(e)})

        # Calculer la moyenne
        if results["test_cases_passed"] > 0:
            results["avg_latency_ms"] = total_latency / results["test_cases_passed"]

        results["experiment_name"] = experiment_name

        log.info(
            "[MLflow] Comparaison terminée",
            avg_latency=results["avg_latency_ms"],
            passed=results["test_cases_passed"],
            total=results["total_runs"],
        )

        return results

    def log_evaluation_metrics(
        self,
        run_id: Optional[str] = None,
        faithfulness: Optional[float] = None,
        answer_relevancy: Optional[float] = None,
        context_precision: Optional[float] = None,
        additional_metrics: Optional[Dict[str, float]] = None,
    ):
        """
        Logger les métriques d'évaluation (RAGAS, etc).

        Args:
            run_id: ID de la run (par défaut: run active)
            faithfulness: Métrique RAGAS (0-1)
            answer_relevancy: Métrique RAGAS (0-1)
            context_precision: Métrique RAGAS (0-1)
            additional_metrics: Autres métriques {name: value}
        """
        metrics = {}

        if faithfulness is not None:
            metrics["ragas_faithfulness"] = faithfulness
        if answer_relevancy is not None:
            metrics["ragas_answer_relevancy"] = answer_relevancy
        if context_precision is not None:
            metrics["ragas_context_precision"] = context_precision

        if additional_metrics:
            metrics.update(additional_metrics)

        if metrics:
            mlflow.log_metrics(metrics)
            log.info("[MLflow] Métriques d'évaluation loggées", metrics=metrics)

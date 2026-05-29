"""
rag_pipeline_with_mlflow.py — MLOPS-RAG: Pipeline RAG avec MLflow Tracking Complet
====================================================================================
Pipeline RAG avec tracking MLflow intégré:
- Étape 1: Retrieve (latency, chunk count)
- Étape 2: Build context
- Étape 3: Generate (LLM latency, token count)
- Étape 4: Logging RAGAS metrics (optionnel)
"""

import mlflow
import structlog
import time
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime

from src.embeddings.embedder import Embedder
from src.monitoring.prometheus_metrics import RAG_LLM_LATENCY
from src.vector_store.qdrant_client import QdrantVectorStore
from src.retrieval.retrieval_service import RetrievalService
from src.llm.llm_with_mlflow import LLMWithMLflow
from src.rag.context_builder import build_context
from src.rag.guardrails import check_context
from src.rag.query_rewriter import filter_by_date_range, rewrite_query
from src.monitoring.model_versioning import ModelVersionManager

log = structlog.get_logger()


class RAGPipelineWithMLflow:
    """Pipeline RAG avec tracking MLflow complet."""

    def __init__(self, settings):
        """
        Initialiser le pipeline RAG avec MLflow tracking.

        Args:
            settings: Configuration (postgres, qdrant, ollama, mlflow)
        """
        self.settings = settings

        # Services RAG
        self.embedder = Embedder(
            model_name=settings.embedding_model,
            batch_size=settings.embedding_batch_size,
        )
        self.vector_store = QdrantVectorStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection=settings.qdrant_collection,
        )
        self.retriever = RetrievalService(self.embedder, self.vector_store)

        # LLM avec MLflow
        self.llm = LLMWithMLflow(
            host=settings.ollama_host,
            port=settings.ollama_port,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout,
            mlflow_tracking_uri=settings.mlflow_tracking_uri,
            experiment_name="rag_inference",
        )

        # Model Registry — version courante du modèle servi
        try:
            self.version_manager = ModelVersionManager(
                tracking_uri=settings.mlflow_tracking_uri,
                model_name="gemma3-rag-livraison",
            )
            self._model_version_info = self.version_manager.get_production_version()
            if self._model_version_info:
                log.info(
                    "[RAG-MLflow] Modèle Production chargé",
                    version=self._model_version_info.get("version"),
                    semver=self._model_version_info.get("semver"),
                )
            else:
                log.warning(
                    "[RAG-MLflow] Aucun modèle en Production — fallback sur la dernière Staging"
                )
                staging = self.version_manager.list_versions(stage="Staging")
                self._model_version_info = staging[0] if staging else None
        except Exception as e:
            log.error(f"[RAG-MLflow] Init ModelVersionManager échoué: {e}")
            self.version_manager = None
            self._model_version_info = None

        log.info("[RAG-MLflow] Pipeline initialisé")

    def reload_model_version(self) -> Optional[Dict[str, Any]]:
        """Recharger la version Production depuis le Registry (post-promotion)."""
        if not self.version_manager:
            return None
        info = self.version_manager.get_production_version()
        if not info:
            staging = self.version_manager.list_versions(stage="Staging")
            info = staging[0] if staging else None
        self._model_version_info = info
        log.info("[RAG-MLflow] Version modèle rechargée", info=info)
        return info

    def _log_model_version_tags(self) -> None:
        """Logger les tags/params identifiant la version du modèle servie."""
        info = self._model_version_info
        if not info:
            mlflow.set_tag("model_registry_status", "unregistered")
            return
        mlflow.set_tags(
            {
                "model_registry_name": "gemma3-rag-livraison",
                "model_registry_version": str(info.get("version")),
                "model_registry_stage": str(info.get("stage")),
                "model_semver": str(info.get("semver") or "n/a"),
            }
        )
        mlflow.log_params(
            {
                "model_version": info.get("version"),
                "model_semver": info.get("semver") or "n/a",
                "model_stage": info.get("stage"),
            }
        )

    def _rewrite_and_merge_filters(
        self, question: str, user_filters: Optional[dict]
    ) -> tuple[Optional[dict], Optional[tuple]]:
        """Extrait les filtres d'intent (criticite/zone/type_event/source/date)
        depuis la question. Les filtres utilisateur explicites sont prioritaires
        sur ceux dérivés (ne pas écraser un choix conscient de l'appelant).
        """
        rewritten = rewrite_query(question)
        derived = rewritten.get("qdrant_filters") or {}
        merged = (
            {**derived, **(user_filters or {})} if (derived or user_filters) else None
        )
        if rewritten.get("matched"):
            log.info("[RAG-MLflow] query_rewriter", **rewritten["matched"])
        return merged, rewritten.get("date_range")

    # Sources temps réel (Familles 2/3) : peu de docs, embedding faiblement
    # aligné → le filtre de source garantit la pertinence, on relâche le seuil.
    _REALTIME_SOURCES = {"prometheus", "elasticsearch"}

    def _threshold_for(self, filters: Optional[dict]) -> Optional[float]:
        # Source temps réel filtrée (1 doc prometheus / ~quelques centaines de
        # logs) : le filtre garantit la pertinence, le seuil de score
        # pénaliserait à tort (ex: snapshot santé score ~0.02). On le neutralise.
        if filters and filters.get("source") in self._REALTIME_SOURCES:
            return 0.0
        return None

    async def query(
        self,
        question: str,
        top_k: int = 8,
        filters: Optional[dict] = None,
        run_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Requête RAG simple avec MLflow tracking complet.

        Args:
            question: Question de l'utilisateur
            top_k: Nombre de chunks à récupérer
            filters: Filtres Qdrant (optionnel)
            run_name: Nom de la run MLflow

        Returns:
            {"answer": str, "contexts": list, "metrics": dict}
        """
        if not run_name:
            run_name = f"rag_query_{datetime.now().isoformat()}"

        with mlflow.start_run(run_name=run_name) as run:
            try:
                self._log_model_version_tags()
                # Logger les paramètres d'entrée
                mlflow.log_params(
                    {"question": question[:100], "top_k": top_k, "method": "query"}
                )

                # ÉTAPE 1: RETRIEVE (query rewriter → filtres dérivés + date)
                merged_filters, date_range = self._rewrite_and_merge_filters(
                    question, filters
                )
                start_retrieve = time.time()
                retrieve_k = top_k * 3 if date_range else top_k
                chunks = self.retriever.retrieve(
                    question,
                    top_k=retrieve_k,
                    filters=merged_filters,
                    score_threshold=self._threshold_for(merged_filters),
                )
                chunks = filter_by_date_range(chunks, date_range)[:top_k]
                retrieve_time = (time.time() - start_retrieve) * 1000  # ms

                mlflow.log_metrics(
                    {
                        "retrieve_time_ms": retrieve_time,
                        "chunks_retrieved": len(chunks),
                        "question_length": len(question),
                    }
                )

                log.info(
                    "[RAG-MLflow] Retrieve OK",
                    time_ms=retrieve_time,
                    chunks=len(chunks),
                )

                # ÉTAPE 2: BUILD CONTEXT
                start_context = time.time()
                context = build_context(chunks)
                context_time = (time.time() - start_context) * 1000

                mlflow.log_metrics(
                    {
                        "context_build_time_ms": context_time,
                        "context_length": len(context),
                        "context_chunks": len(chunks),
                    }
                )

                # GUARDRAIL : contexte vide → réponse de secours sans appel LLM
                # (évite l'hallucination d'un petit modèle face à un contexte vide).
                ok, refus = check_context(context)
                if not ok:
                    mlflow.set_tag("guardrail", "contexte_vide")
                    log.info(
                        "[RAG-MLflow] guardrail contexte_vide — réponse de secours"
                    )
                    return {
                        "answer": refus,
                        "contexts": chunks,
                        "metrics": {
                            "retrieve_time_ms": retrieve_time,
                            "chunks_retrieved": len(chunks),
                            "guardrail": "contexte_vide",
                        },
                    }

                log.info(
                    "[RAG-MLflow] Context build OK",
                    time_ms=context_time,
                    length=len(context),
                )

                # ÉTAPE 3: GENERATE avec LLMWithMLflow
                # Note: On passe create_run=False pour utiliser la run courante
                # et éviter les runs imbriquées
                start_generate = time.time()
                result = await self.llm.generate(context, question, create_run=False)
                generate_time = (time.time() - start_generate) * 1000

                answer = result["response"]
                llm_latency = result["latency_ms"]
                RAG_LLM_LATENCY.observe(llm_latency / 1000.0)

                mlflow.log_metrics(
                    {
                        "generate_time_ms": generate_time,
                        "llm_latency_ms": llm_latency,
                        "answer_length": len(answer),
                        "total_pipeline_time_ms": retrieve_time
                        + context_time
                        + generate_time,
                    }
                )

                # Logger les tags
                mlflow.set_tags(
                    {
                        "component": "rag_pipeline",
                        "method": "query",
                        "status": "success",
                        "sprint": "sprint6",
                    }
                )

                log.info(
                    "[RAG-MLflow] Query terminée",
                    run_id=run.info.run_id[:8],
                    total_time_ms=retrieve_time + context_time + generate_time,
                )

                return {
                    "answer": answer,
                    "contexts": chunks,
                    "metrics": {
                        "retrieve_time_ms": retrieve_time,
                        "context_build_time_ms": context_time,
                        "llm_latency_ms": llm_latency,
                        "total_time_ms": retrieve_time + context_time + generate_time,
                        "chunks_retrieved": len(chunks),
                    },
                }

            except Exception as e:
                log.error(f"[RAG-MLflow] Erreur query: {e}", exc_info=True)
                mlflow.log_param("error", str(e))
                mlflow.set_tag("status", "error")
                raise

    async def stream(
        self,
        question: str,
        top_k: int = 8,
        filters: Optional[dict] = None,
        run_name: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Requête RAG avec streaming.

        Args:
            question: Question de l'utilisateur
            top_k: Nombre de chunks à récupérer
            filters: Filtres Qdrant
            run_name: Nom de la run MLflow

        Yields:
            Tokens de réponse en streaming
        """
        if not run_name:
            run_name = f"rag_stream_{datetime.now().isoformat()}"

        with mlflow.start_run(run_name=run_name):
            try:
                self._log_model_version_tags()
                # Logger les paramètres
                mlflow.log_params(
                    {"question": question[:100], "top_k": top_k, "method": "stream"}
                )

                # RETRIEVE (query rewriter)
                merged_filters, date_range = self._rewrite_and_merge_filters(
                    question, filters
                )
                start = time.time()
                retrieve_k = top_k * 3 if date_range else top_k
                chunks = self.retriever.retrieve(
                    question,
                    top_k=retrieve_k,
                    filters=merged_filters,
                    score_threshold=self._threshold_for(merged_filters),
                )
                chunks = filter_by_date_range(chunks, date_range)[:top_k]
                retrieve_time = (time.time() - start) * 1000

                # BUILD CONTEXT
                context = build_context(chunks)

                mlflow.log_metrics(
                    {
                        "retrieve_time_ms": retrieve_time,
                        "chunks_retrieved": len(chunks),
                        "context_length": len(context),
                    }
                )

                # GUARDRAIL : contexte vide → secours sans appel LLM
                ok, refus = check_context(context)
                if not ok:
                    mlflow.set_tag("guardrail", "contexte_vide")
                    yield refus
                    return

                # STREAM GENERATE
                token_count = 0
                start_generate = time.time()

                async for token in self.llm.llm.stream(context, question):
                    token_count += len(token)
                    yield token

                generate_time = (time.time() - start_generate) * 1000

                mlflow.log_metrics(
                    {"generate_time_ms": generate_time, "tokens_streamed": token_count}
                )

                mlflow.set_tags(
                    {
                        "component": "rag_pipeline",
                        "method": "stream",
                        "status": "success",
                    }
                )

                log.info(
                    "[RAG-MLflow] Stream OK", tokens=token_count, time_ms=generate_time
                )

            except Exception as e:
                log.error(f"[RAG-MLflow] Erreur stream: {e}", exc_info=True)
                mlflow.log_param("error", str(e))
                raise

    async def chat(
        self,
        messages: list[dict],
        top_k: int = 8,
        filters: Optional[dict] = None,
        run_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Chat RAG avec MLflow tracking.

        Args:
            messages: Historique des messages [{role, content}, ...]
            top_k: Nombre de chunks
            filters: Filtres Qdrant
            run_name: Nom de la run MLflow

        Returns:
            {"answer": str, "contexts": list, "metrics": dict}
        """
        if not run_name:
            run_name = f"rag_chat_{datetime.now().isoformat()}"

        with mlflow.start_run(run_name=run_name):
            try:
                self._log_model_version_tags()
                # Logger les paramètres
                mlflow.log_params(
                    {"messages_count": len(messages), "top_k": top_k, "method": "chat"}
                )

                # BUILD EMBEDDING QUERY (pour retrieve avec contexte)
                embedding_query = self._build_embedding_query(messages)

                # RETRIEVE (query rewriter sur l'embedding_query)
                merged_filters, date_range = self._rewrite_and_merge_filters(
                    embedding_query, filters
                )
                start_retrieve = time.time()
                retrieve_k = top_k * 3 if date_range else top_k
                chunks = self.retriever.retrieve(
                    embedding_query,
                    top_k=retrieve_k,
                    filters=merged_filters,
                    score_threshold=self._threshold_for(merged_filters),
                )
                chunks = filter_by_date_range(chunks, date_range)[:top_k]
                retrieve_time = (time.time() - start_retrieve) * 1000

                # BUILD CONTEXT
                context = build_context(chunks)

                mlflow.log_metrics(
                    {
                        "retrieve_time_ms": retrieve_time,
                        "chunks_retrieved": len(chunks),
                        "context_length": len(context),
                        "messages_in_history": len(messages),
                    }
                )

                # GUARDRAIL : contexte vide → réponse de secours sans appel LLM
                ok, refus = check_context(context)
                if not ok:
                    mlflow.set_tag("guardrail", "contexte_vide")
                    return {
                        "answer": refus,
                        "contexts": chunks,
                        "metrics": {
                            "retrieve_time_ms": retrieve_time,
                            "chunks_retrieved": len(chunks),
                            "guardrail": "contexte_vide",
                        },
                    }

                # GENERATE CHAT (passer create_run=False)
                start_generate = time.time()
                result = await self.llm.chat(messages, context, create_run=False)
                generate_time = (time.time() - start_generate) * 1000

                answer = result["response"]
                llm_latency = result["latency_ms"]

                mlflow.log_metrics(
                    {
                        "generate_time_ms": generate_time,
                        "llm_latency_ms": llm_latency,
                        "answer_length": len(answer),
                        "total_time_ms": retrieve_time + generate_time,
                    }
                )

                mlflow.set_tags(
                    {"component": "rag_pipeline", "method": "chat", "status": "success"}
                )

                log.info(
                    "[RAG-MLflow] Chat OK", total_time_ms=retrieve_time + generate_time
                )

                return {
                    "answer": answer,
                    "contexts": chunks,
                    "metrics": {
                        "retrieve_time_ms": retrieve_time,
                        "llm_latency_ms": llm_latency,
                        "total_time_ms": retrieve_time + generate_time,
                        "chunks_retrieved": len(chunks),
                    },
                }

            except Exception as e:
                log.error(f"[RAG-MLflow] Erreur chat: {e}", exc_info=True)
                mlflow.log_param("error", str(e))
                raise

    async def chat_stream(
        self,
        messages: list[dict],
        top_k: int = 8,
        filters: Optional[dict] = None,
        run_name: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Chat avec streaming et MLflow tracking."""
        if not run_name:
            run_name = f"rag_chat_stream_{datetime.now().isoformat()}"

        with mlflow.start_run(run_name=run_name):
            try:
                self._log_model_version_tags()
                mlflow.log_params(
                    {
                        "messages_count": len(messages),
                        "top_k": top_k,
                        "method": "chat_stream",
                    }
                )

                # RETRIEVE (query rewriter)
                embedding_query = self._build_embedding_query(messages)
                merged_filters, date_range = self._rewrite_and_merge_filters(
                    embedding_query, filters
                )
                retrieve_k = top_k * 3 if date_range else top_k
                chunks = self.retriever.retrieve(
                    embedding_query,
                    top_k=retrieve_k,
                    filters=merged_filters,
                    score_threshold=self._threshold_for(merged_filters),
                )
                chunks = filter_by_date_range(chunks, date_range)[:top_k]
                context = build_context(chunks)

                mlflow.log_metrics(
                    {
                        "chunks_retrieved": len(chunks),
                        "context_length": len(context),
                        "messages_count": len(messages),
                    }
                )

                # GUARDRAIL : contexte vide → secours sans appel LLM
                ok, refus = check_context(context)
                if not ok:
                    mlflow.set_tag("guardrail", "contexte_vide")
                    yield refus
                    return

                # STREAM CHAT
                token_count = 0
                start_generate = time.time()

                async for token in self.llm.llm.chat_stream(messages, context):
                    token_count += len(token)
                    yield token

                generate_time = (time.time() - start_generate) * 1000

                mlflow.log_metrics(
                    {"generate_time_ms": generate_time, "tokens_streamed": token_count}
                )

                mlflow.set_tags({"component": "rag_pipeline", "method": "chat_stream"})

            except Exception as e:
                log.error(f"[RAG-MLflow] Erreur chat_stream: {e}")
                raise

    @staticmethod
    def _build_embedding_query(messages: list[dict], history_window: int = 3) -> str:
        """Construire la requête d'embedding avec contexte conversationnel."""
        user_msgs = [m["content"] for m in messages if m.get("role") == "user"]
        recent = user_msgs[-history_window:]
        return "\n".join(recent) if recent else ""

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
from src.vector_store.qdrant_client import QdrantVectorStore
from src.retrieval.retrieval_service import RetrievalService
from src.llm.llm_with_mlflow import LLMWithMLflow
from src.rag.context_builder import build_context

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

        log.info("[RAG-MLflow] Pipeline initialisé")

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
                # Logger les paramètres d'entrée
                mlflow.log_params(
                    {"question": question[:100], "top_k": top_k, "method": "query"}
                )

                # ÉTAPE 1: RETRIEVE
                start_retrieve = time.time()
                chunks = self.retriever.retrieve(question, top_k=top_k, filters=filters)
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
                # Logger les paramètres
                mlflow.log_params(
                    {"question": question[:100], "top_k": top_k, "method": "stream"}
                )

                # RETRIEVE
                start = time.time()
                chunks = self.retriever.retrieve(question, top_k=top_k, filters=filters)
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
                # Logger les paramètres
                mlflow.log_params(
                    {"messages_count": len(messages), "top_k": top_k, "method": "chat"}
                )

                # BUILD EMBEDDING QUERY (pour retrieve avec contexte)
                embedding_query = self._build_embedding_query(messages)

                # RETRIEVE
                start_retrieve = time.time()
                chunks = self.retriever.retrieve(
                    embedding_query, top_k=top_k, filters=filters
                )
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
                mlflow.log_params(
                    {
                        "messages_count": len(messages),
                        "top_k": top_k,
                        "method": "chat_stream",
                    }
                )

                # RETRIEVE
                embedding_query = self._build_embedding_query(messages)
                chunks = self.retriever.retrieve(
                    embedding_query, top_k=top_k, filters=filters
                )
                context = build_context(chunks)

                mlflow.log_metrics(
                    {
                        "chunks_retrieved": len(chunks),
                        "context_length": len(context),
                        "messages_count": len(messages),
                    }
                )

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

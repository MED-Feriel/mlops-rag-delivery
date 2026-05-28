"""
routes_with_mlflow.py — Routes RAG avec MLflow Tracking Complet
===============================================================
Routes FastAPI avec tracking MLflow intégré:
- POST /query → RAG simple avec logging
- POST /query/stream → RAG streaming
- POST /chat → Chat RAG
- POST /chat/stream → Chat streaming
"""

import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.api.models import QueryRequest, QueryResponse
from src.monitoring.prometheus_metrics import (
    RAG_ACTIVE_REQUESTS,
    RAG_QUERY_DURATION,
    RAG_QUERY_TOTAL,
    extract_zone_filter,
)
from src.rag.rag_pipeline_with_mlflow import RAGPipelineWithMLflow
from config.settings import get_settings
import structlog

log = structlog.get_logger()

router = APIRouter()
_pipeline: RAGPipelineWithMLflow | None = None


def _get_pipeline() -> RAGPipelineWithMLflow:
    """Obtenir ou créer le pipeline RAG avec MLflow."""
    global _pipeline
    if _pipeline is None:
        settings = get_settings()
        _pipeline = RAGPipelineWithMLflow(settings)
        log.info("[API] Pipeline RAG avec MLflow initialisé")
    return _pipeline


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Requête RAG simple.

    Logging MLflow:
    - Paramètres: question, top_k, method
    - Étapes: retrieve, context_build, generate
    - Métriques: latencies, chunk count, token count
    """
    start_request = time.time()
    RAG_ACTIVE_REQUESTS.inc()
    zone = extract_zone_filter(req.filters)
    status = "success"

    try:
        if not req.question:
            raise HTTPException(
                status_code=400, detail="question est requis pour /query"
            )

        log.info(f"[API] Query reçue: {req.question[:50]}...")

        result = await _get_pipeline().query(
            req.question,
            top_k=req.top_k or 5,
            filters=req.filters,
            run_name=f"api_query_{req.question[:20].replace(' ', '_')}",
        )

        request_duration = time.time() - start_request
        RAG_QUERY_DURATION.observe(request_duration)
        RAG_QUERY_TOTAL.labels(status=status, zone_filter=zone).inc()

        response = QueryResponse(**result, question=req.question)

        log.info(
            "[API] Query OK",
            chunks=result["metrics"]["chunks_retrieved"],
            total_time_ms=result["metrics"]["total_time_ms"],
        )

        return response

    except HTTPException:
        status = "error"
        RAG_QUERY_TOTAL.labels(status=status, zone_filter=zone).inc()
        raise
    except Exception as e:
        status = "error"
        RAG_QUERY_TOTAL.labels(status=status, zone_filter=zone).inc()
        log.error(f"[API] Erreur query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        RAG_ACTIVE_REQUESTS.dec()


@router.post("/query/stream")
async def query_stream(req: QueryRequest) -> StreamingResponse:
    """
    Requête RAG avec streaming.

    Logging MLflow:
    - Tokens streamés
    - Latencies retrieve/generate
    """
    try:
        log.info(f"[API] Query stream reçue: {req.question[:50]}...")

        pipeline = _get_pipeline()

        async def event_gen():
            async for chunk in pipeline.stream(
                req.question,
                top_k=req.top_k or 5,
                filters=req.filters,
                run_name=f"api_stream_{req.question[:20].replace(' ', '_')}",
            ):
                yield f"data: {chunk}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    except Exception as e:
        log.error(f"[API] Erreur query_stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=QueryResponse)
async def chat(req: QueryRequest) -> QueryResponse:
    """
    Chat RAG avec historique.

    Attendu dans req.messages: [{"role": "user"/"assistant", "content": "..."}, ...]

    Logging MLflow:
    - Nombre de messages historique
    - Contexte conversationnel
    - Performances multi-tour
    """
    start_request = time.time()
    RAG_ACTIVE_REQUESTS.inc()
    zone = extract_zone_filter(req.filters)
    status = "success"

    try:
        # Convertir les ChatMessage Pydantic en dict
        messages = [
            {"role": m.role, "content": m.content} for m in (req.messages or [])
        ]

        log.info(
            "[API] Chat reçu",
            messages=len(messages),
            last_question=messages[-1]["content"][:50] if messages else "",
        )

        result = await _get_pipeline().chat(
            messages,
            top_k=req.top_k or 5,
            filters=req.filters,
            run_name=f"api_chat_{len(messages)}_turns",
        )

        response = QueryResponse(
            **result, question=messages[-1]["content"] if messages else ""
        )

        request_duration = time.time() - start_request
        RAG_QUERY_DURATION.observe(request_duration)
        RAG_QUERY_TOTAL.labels(status=status, zone_filter=zone).inc()

        log.info(
            "[API] Chat OK",
            chunks=result["metrics"]["chunks_retrieved"],
            total_time_ms=result["metrics"]["total_time_ms"],
        )

        return response

    except Exception as e:
        status = "error"
        RAG_QUERY_TOTAL.labels(status=status, zone_filter=zone).inc()
        log.error(f"[API] Erreur chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        RAG_ACTIVE_REQUESTS.dec()


@router.post("/chat/stream")
async def chat_stream(req: QueryRequest) -> StreamingResponse:
    """Chat RAG avec streaming."""
    try:
        messages = req.messages or []

        log.info(f"[API] Chat stream reçu: {len(messages)} messages")

        pipeline = _get_pipeline()

        async def event_gen():
            async for chunk in pipeline.chat_stream(
                messages,
                top_k=req.top_k or 5,
                filters=req.filters,
                run_name=f"api_chat_stream_{len(messages)}_turns",
            ):
                yield f"data: {chunk}\n\n"

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    except Exception as e:
        log.error(f"[API] Erreur chat_stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))

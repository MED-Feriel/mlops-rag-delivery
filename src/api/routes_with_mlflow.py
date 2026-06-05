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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from src.api.auth import get_current_principal
from src.api.feedback_store import FeedbackStore
from src.api.models import FeedbackRequest, QueryRequest, QueryResponse
from src.monitoring.prometheus_metrics import (
    RAG_ACTIVE_REQUESTS,
    RAG_FEEDBACK_TOTAL,
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


_feedback_store: FeedbackStore | None = None
_feedback_store_ready = False


def _get_feedback_store() -> FeedbackStore | None:
    """Store de feedback (singleton, lazy). None si Redis indisponible."""
    global _feedback_store, _feedback_store_ready
    if not _feedback_store_ready:
        _feedback_store = FeedbackStore.from_settings(get_settings())
        _feedback_store_ready = True
    return _feedback_store


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest, principal: str = Depends(get_current_principal)
) -> QueryResponse:
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
        detail = str(e) or f"{type(e).__name__} (aucun détail — voir les logs API)"
        raise HTTPException(status_code=500, detail=detail)
    finally:
        RAG_ACTIVE_REQUESTS.dec()


@router.post("/query/stream")
async def query_stream(
    req: QueryRequest, principal: str = Depends(get_current_principal)
) -> StreamingResponse:
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
async def chat(
    req: QueryRequest, principal: str = Depends(get_current_principal)
) -> QueryResponse:
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


@router.get("/cache/stats")
async def cache_stats() -> dict:
    """Statistiques des caches Redis : embeddings (B.1) et réponses (B.2)."""
    pipeline = _get_pipeline()
    retriever = pipeline.retriever
    if getattr(retriever, "cache_enabled", False):
        stats = retriever.cache.get_stats()
        out = {
            "enabled": True,
            "hit_rate_pct": stats["hit_rate"],
            "hits": stats["hit"],
            "misses": stats["miss"],
            "errors": stats["error"],
            "total_requests": stats["total"],
            "ttl_sec": get_settings().redis_ttl_embedding_sec,
        }
    else:
        out = {"enabled": False, "message": "Cache Redis non disponible"}

    answer_cache = getattr(pipeline, "answer_cache", None)
    if answer_cache is not None:
        a = answer_cache.get_stats()
        out["answer_cache"] = {
            "enabled": True,
            "hit_rate_pct": a["hit_rate"],
            "hits": a["hit"],
            "misses": a["miss"],
            "ttl_sec": get_settings().redis_ttl_answer_sec,
        }
    else:
        out["answer_cache"] = {"enabled": False}
    return out


@router.delete("/cache/flush")
async def cache_flush() -> dict:
    """Vide le cache Redis (utile après mise à jour du modèle d'embedding)."""
    retriever = _get_pipeline().retriever
    if not getattr(retriever, "cache_enabled", False):
        return {"flushed": 0, "message": "Cache non disponible"}
    deleted = retriever.cache.flush()
    return {"flushed": deleted, "message": f"{deleted} entrées supprimées"}


@router.delete("/cache/invalidate")
async def cache_invalidate(query: str) -> dict:
    """Invalide l'entrée de cache d'une seule question (invalidation ciblée).

    Contrairement à ``/cache/flush`` (purge totale), n'enlève que le vecteur
    associé à ``query`` — utile après ré-indexation/correction d'un document
    précis sans jeter tout le cache. La normalisation (casse + espaces) est
    identique à celle utilisée à l'écriture, donc « Quels retards ? » invalide
    bien « quels retards ? ».
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="paramètre 'query' requis")
    retriever = _get_pipeline().retriever
    if not getattr(retriever, "cache_enabled", False):
        return {"invalidated": False, "message": "Cache non disponible"}
    removed = retriever.cache.invalidate(query)
    return {"invalidated": removed, "query": query}


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest, principal: str = Depends(get_current_principal)
) -> dict:
    """Enregistre un feedback 👍/👎 sur une réponse RAG.

    Triple destination : compteur Prometheus (``rag_feedback_total`` → Grafana),
    log structuré (→ Elasticsearch/Kibana) et historique Redis (best-effort, via
    le feedback store). Le rating doit valoir ``up`` ou ``down``.
    """
    rating = (req.rating or "").strip().lower()
    if rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating doit être 'up' ou 'down'")

    RAG_FEEDBACK_TOTAL.labels(rating=rating).inc()
    log.info(
        "rag_feedback",
        rating=rating,
        question=(req.question or "")[:120],
        has_comment=bool(req.comment),
    )

    store = _get_feedback_store()
    persisted = (
        store.record(rating, req.question, req.answer or "", req.comment or "")
        if store is not None
        else False
    )
    return {"recorded": True, "rating": rating, "persisted": persisted}


@router.get("/feedback/stats")
async def feedback_stats() -> dict:
    """Compteurs 👍/👎, taux de satisfaction et derniers feedbacks reçus."""
    store = _get_feedback_store()
    if store is None:
        return {"enabled": False, "message": "Feedback store (Redis) non disponible"}
    return store.get_stats()


@router.post("/chat/stream")
async def chat_stream(
    req: QueryRequest, principal: str = Depends(get_current_principal)
) -> StreamingResponse:
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

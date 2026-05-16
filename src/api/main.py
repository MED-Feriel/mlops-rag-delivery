"""API RAG FastAPI — point d'entrée principal (port 8080) avec MLflow Tracking."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from src.api.models import CollectionStats, HealthResponse
from src.api.openai_compat import router as openai_router
from src.api.routes_with_mlflow import router

log = structlog.get_logger()

app = FastAPI(
    title="RAG Livraison API",
    description="API REST pour le système RAG de supervision plateforme de livraison",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(openai_router)

log.info("[API] Routes avec MLflow tracking intégrées")


# ─── Métriques Prometheus (best-effort) ────────────────────────────────────
try:
    from prometheus_client import (
        Counter,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    RAG_QUERY_TOTAL = Counter("rag_query_total", "Nombre total de requêtes /query")
    RAG_QUERY_DURATION = Histogram("rag_query_duration_seconds", "Durée /query")
    RAG_RETRIEVED_DOCS = Histogram(
        "rag_retrieved_docs_count", "Nb docs récupérés par /query"
    )
    RAG_LLM_LATENCY = Histogram("rag_llm_latency_seconds", "Latence Gemma3")
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False


@app.get("/metrics")
async def metrics() -> Response:
    if not _PROM_AVAILABLE:
        return Response("# prometheus_client not installed\n", media_type="text/plain")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ─── Health & stats ────────────────────────────────────────────────────────
async def _check_qdrant(s) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"http://{s.qdrant_host}:6333/collections")
            return r.status_code == 200
    except Exception:
        return False


async def _check_ollama(s) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"http://{s.ollama_host}:{s.ollama_port}/api/tags")
            return r.status_code == 200 and s.ollama_model in {
                m["name"] for m in r.json().get("models", [])
            }
    except Exception:
        return False


def _check_postgres(s) -> bool:
    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(
            host=s.postgres_host,
            port=s.postgres_port,
            dbname=s.postgres_db,
            user=s.postgres_user,
            password=s.postgres_password,
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    s = get_settings()
    qdrant_ok = await _check_qdrant(s)
    ollama_ok = await _check_ollama(s)
    postgres_ok = _check_postgres(s)
    all_ok = qdrant_ok and ollama_ok and postgres_ok
    status = (
        "healthy"
        if all_ok
        else ("degraded" if (qdrant_ok or ollama_ok) else "unhealthy")
    )
    return HealthResponse(
        status=status,
        qdrant=qdrant_ok,
        ollama=ollama_ok,
        postgres=postgres_ok,
        version=app.version,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/collections/stats", response_model=CollectionStats)
async def collection_stats() -> CollectionStats:
    s = get_settings()
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(
            f"http://{s.qdrant_host}:6333/collections/{s.qdrant_collection}"
        )
        r.raise_for_status()
        data = r.json().get("result", {})
    return CollectionStats(
        collection_name=s.qdrant_collection,
        nb_vectors=data.get("points_count", 0),
        vector_size=s.qdrant_vector_size,
        status=data.get("status", "unknown"),
    )

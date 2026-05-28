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

# Importer les métriques RAG partagées pour les enregistrer dans le registry global.
# Sans cet import, /metrics peut ne pas exposer certains histogrammes/gauges
# si le pipeline n'a pas encore été invoqué.
import src.monitoring.prometheus_metrics  # noqa: F401

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
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

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


@app.post("/admin/reload-model-version")
async def reload_model_version() -> dict:
    """Recharger la version du modèle depuis le Registry sans redémarrer l'API.

    À appeler après une promotion (ex: à la fin du DAG `rag_evaluation_daily`).
    """
    from src.api.routes_with_mlflow import _get_pipeline

    info = _get_pipeline().reload_model_version()
    return {"reloaded": True, "current": info}


@app.get("/model/version")
async def model_version() -> dict:
    """Retourner la version courante du modèle servi (depuis le Model Registry)."""
    from src.monitoring.model_versioning import ModelVersionManager

    s = get_settings()
    mgr = ModelVersionManager(
        tracking_uri=s.mlflow_tracking_uri, model_name="gemma3-rag-livraison"
    )
    prod = mgr.get_production_version()
    if prod:
        return {**prod, "serving_status": "production"}
    staging = mgr.list_versions(stage="Staging")
    if staging:
        return {**staging[0], "serving_status": "staging_fallback"}
    return {"serving_status": "unregistered", "model_name": "gemma3-rag-livraison"}


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

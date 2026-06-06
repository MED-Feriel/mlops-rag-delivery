"""API RAG FastAPI — point d'entrée principal (port 8080) avec MLflow Tracking."""

from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime, timezone

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import get_settings
from src.api.audit import log_api_access
from src.api.auth import (
    create_api_key,
    list_api_keys,
    require_roles,
    revoke_api_key,
    router as auth_router,
)
from src.api.models import CollectionStats, HealthResponse
from src.api.openai_compat import router as openai_router
from src.api.routes_with_mlflow import router

# Importer les métriques RAG partagées pour les enregistrer dans le registry global.
# Sans cet import, /metrics peut ne pas exposer certains histogrammes/gauges
# si le pipeline n'a pas encore été invoqué.
import src.monitoring.prometheus_metrics  # noqa: F401
from src.monitoring.prometheus_metrics import RAG_DATA_DRIFT_PSI, RAG_DEPENDENCY_UP

log = structlog.get_logger()

app = FastAPI(
    title="RAG Livraison API",
    description="API REST pour le système RAG de supervision plateforme de livraison",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    # Origines depuis settings (CORS_ORIGINS) — éviter "*" en production.
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(router)
app.include_router(openai_router)

log.info(
    "[API] Routes intégrées (MLflow + auth)",
    auth_enabled=get_settings().auth_enabled,
)


# ─── Audit logging (MLOPS-117) ──────────────────────────────────────────────
@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Journalise chaque accès API (sauf /health* et /metrics, trop bruyants)."""
    response = await call_next(request)
    path = request.url.path
    if path != "/metrics" and not path.startswith("/health"):
        principal = getattr(request.state, "principal", None)
        log_api_access(
            request=request,
            user_id=getattr(principal, "id", "anonymous"),
            action=request.method,
            resource=path,
            status_code=response.status_code,
        )
    return response


# ─── Gestion des clés API (admin) — MLOPS-117 ───────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str
    roles: list[str] = ["service"]


@app.post("/auth/api-key")
async def create_api_key_endpoint(
    body: ApiKeyCreate, principal=Depends(require_roles("admin"))
) -> dict:
    """Génère une nouvelle clé API (admin uniquement)."""
    key, rec = create_api_key(body.name, body.roles)
    return {
        "api_key": key,
        "id": rec["id"],
        "name": rec["name"],
        "roles": rec["roles"],
        "note": "Conservez cette clé : elle n'est affichée qu'une seule fois.",
    }


@app.get("/auth/api-keys")
async def list_api_keys_endpoint(principal=Depends(require_roles("admin"))) -> dict:
    """Liste les clés API (sans exposer le secret), admin uniquement."""
    return {"api_keys": list_api_keys(get_settings())}


@app.delete("/auth/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    key_id: str, principal=Depends(require_roles("admin"))
) -> dict:
    """Révoque une clé API par son id (admin uniquement)."""
    if not revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail="Clé introuvable ou déjà révoquée")
    return {"revoked": True, "id": key_id}


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


def _check_elasticsearch() -> bool:
    try:
        r = httpx.get("http://elasticsearch:9200", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def _check_kafka() -> bool:
    try:
        host, _, port = get_settings().kafka_bootstrap_servers.partition(":")
        with socket.create_connection((host, int(port or 9092)), timeout=3):
            return True
    except Exception:
        return False


@app.on_event("startup")
async def _dependency_health_loop() -> None:
    """Met à jour rag_dependency_up{dependency} toutes les 20s (boucle de fond).

    Lu par Prometheus via /metrics → dashboard 'Santé backend'. Les checks
    synchrones tournent dans un thread (asyncio.to_thread) pour ne pas bloquer
    la boucle d'événements.
    """

    async def loop() -> None:
        while True:
            s = get_settings()
            try:
                checks = {
                    "qdrant": await _check_qdrant(s),
                    "ollama": await _check_ollama(s),
                    "postgres": await asyncio.to_thread(_check_postgres, s),
                    "elasticsearch": await asyncio.to_thread(_check_elasticsearch),
                    "kafka": await asyncio.to_thread(_check_kafka),
                }
                for dep, ok in checks.items():
                    RAG_DEPENDENCY_UP.labels(dependency=dep).set(1.0 if ok else 0.0)
            except Exception:  # la boucle ne doit jamais mourir
                pass
            await asyncio.sleep(20)

    asyncio.create_task(loop())


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


@app.get("/health/embedding")
async def health_embedding() -> dict:
    """Santé du modèle d'embedding : chargé ? bonne dimension ? latence ?

    Indispensable en prod : si le volume ``./models`` est absent ou HuggingFace
    injoignable, le modèle peut ne pas se charger. Cet endpoint le signale
    explicitement (``status=unhealthy`` + message) au lieu de laisser la
    première requête RAG échouer plus tard avec une 500 opaque. Réutilise
    l'embedder du pipeline singleton (pas de second chargement en mémoire).
    """
    from src.api.routes_with_mlflow import _get_pipeline

    s = get_settings()
    info: dict = {"model": s.embedding_model, "expected_dim": s.qdrant_vector_size}
    try:
        embedder = _get_pipeline().retriever.embedder
        start = time.perf_counter()
        vector = embedder.embed_query("test de santé embedding")
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        dim = len(vector)
        dim_ok = dim == s.qdrant_vector_size
        info.update(
            loaded=True,
            status="healthy" if dim_ok else "degraded",
            dim=dim,
            dim_match=dim_ok,
            embed_latency_ms=latency_ms,
        )
    except Exception as e:
        info.update(
            loaded=False,
            status="unhealthy",
            error=str(e) or type(e).__name__,
        )
    return info


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


@app.get("/prompt/version")
async def prompt_version() -> dict:
    """Version et empreinte SHA du prompt système servi (versioning C.5)."""
    from src.llm.llm_service import PROMPT_SHA, PROMPT_VERSION, SYSTEM_PROMPT

    return {
        "prompt_version": PROMPT_VERSION,
        "prompt_sha": PROMPT_SHA,
        "length_chars": len(SYSTEM_PROMPT),
    }


@app.get("/monitoring/drift")
async def data_drift(
    field: str = "source", sample: int = 500, set_baseline: bool = False
) -> dict:
    """Drift de distribution (PSI) d'un champ payload Qdrant vs baseline (C.4).

    Échantillonne ``sample`` points, calcule la distribution de ``field``, la
    compare à une baseline stockée en Redis (PSI : <0.1 stable, 0.1–0.2 modéré,
    >0.2 significatif). ``?set_baseline=true`` (re)fixe la référence. Met à jour
    la gauge Prometheus ``rag_data_drift_psi{field}`` (scrape Grafana / alerte).
    Pensé pour être appelé périodiquement (DAG Airflow ou cron).
    """
    from src.monitoring.drift import (
        build_redis,
        distribution_from_points,
        drift_level,
        get_baseline,
        population_stability_index,
        set_baseline as save_baseline,
    )

    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"http://{s.qdrant_host}:6333/collections/"
                f"{s.qdrant_collection}/points/scroll",
                json={"limit": sample, "with_payload": True, "with_vector": False},
            )
            r.raise_for_status()
            points = r.json().get("result", {}).get("points", [])
    except Exception as e:
        return {"error": str(e) or type(e).__name__, "field": field}

    current = distribution_from_points(points, field)
    redis_client = build_redis(s)
    baseline = get_baseline(redis_client, field)
    if set_baseline or baseline is None:
        saved = save_baseline(redis_client, field, current)
        return {
            "field": field,
            "n_sampled": len(points),
            "baseline_set": saved,
            "distribution": current,
            "note": "baseline (re)fixée"
            if saved
            else "Redis indisponible — baseline non persistée",
        }

    psi = population_stability_index(baseline, current)
    level = drift_level(psi)
    RAG_DATA_DRIFT_PSI.labels(field=field).set(psi)
    return {
        "field": field,
        "n_sampled": len(points),
        "psi": psi,
        "drift": level,
        "baseline": baseline,
        "current": current,
    }


@app.get("/collections/stats", response_model=CollectionStats)
async def collection_stats(
    principal=Depends(require_roles("admin", "service")),
) -> CollectionStats:
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

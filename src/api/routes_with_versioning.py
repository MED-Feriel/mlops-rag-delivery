"""
routes_with_versioning.py — Routes RAG avec Model Versioning MLflow
====================================================================
Routes FastAPI avec:
- MLflow Tracking complet
- Model Versioning automatique
- Logging des versions utilisées
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.api.models import QueryRequest, QueryResponse
from src.rag.rag_with_versioning import RAGPipelineWithVersioning
from config.settings import get_settings
import structlog
from typing import Optional

log = structlog.get_logger()

router = APIRouter()
_pipeline: Optional[RAGPipelineWithVersioning] = None


def _get_pipeline() -> RAGPipelineWithVersioning:
    """Obtenir ou créer le pipeline RAG avec versioning."""
    global _pipeline
    if _pipeline is None:
        settings = get_settings()
        _pipeline = RAGPipelineWithVersioning(settings)
        log.info("[API-Versioning] Pipeline RAG avec versioning initialisé")
    return _pipeline


@router.post("/query", response_model=QueryResponse)
async def query_with_versioning(req: QueryRequest) -> QueryResponse:
    """
    Requête RAG simple avec versioning automatique.

    Réponse inclut:
    - answer: Réponse du modèle
    - contexts: Documents retrieés
    - metrics: Métriques de performance
    - model_version: Version du modèle utilisé
    - model_name: Nom du modèle dans le registry

    Logging MLflow:
    - Expérience: rag_inference
    - Tags: component, method, status, model_version
    - Métriques: retrieve_time_ms, llm_latency_ms, total_pipeline_time_ms
    """
    try:
        if not req.question:
            raise HTTPException(
                status_code=400, detail="question est requis pour /query"
            )

        log.info(f"[API-Versioning] Query reçue: {req.question[:50]}...")

        # Exécuter la requête avec versioning
        result = await _get_pipeline().query_with_version(
            question=req.question,
            top_k=req.top_k or 5,
            filters=req.filters,
            version=None,  # None = utilise Production
            run_name=f"api_query_{req.question[:20].replace(' ', '_')}",
        )

        # Construire la réponse
        response = QueryResponse(
            answer=result["answer"], contexts=result["contexts"], question=req.question
        )

        log.info(
            "[API-Versioning] Query OK",
            version=result.get("model_version"),
            total_time_ms=result["metrics"]["total_time_ms"],
        )

        return response

    except Exception as e:
        log.error(f"[API-Versioning] Erreur query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream", response_class=StreamingResponse)
async def query_stream_with_versioning(req: QueryRequest) -> StreamingResponse:
    """
    Requête RAG avec streaming et versioning.

    Retourne: Stream de tokens (Server-Sent Events)
    """
    try:
        if not req.question:
            raise HTTPException(status_code=400, detail="question est requis")

        log.info(f"[API-Versioning] Query stream reçue: {req.question[:50]}...")

        async def stream_generator():
            try:
                # Récupérer les chunks retrieés et info version
                pipeline = _get_pipeline()
                result = await pipeline.query_with_version(
                    question=req.question,
                    top_k=req.top_k or 5,
                    filters=req.filters,
                    run_name=f"api_query_stream_{req.question[:20].replace(' ', '_')}",
                )

                # Logger la version utilisée
                log.info(
                    "[API-Versioning] Stream session",
                    version=result.get("model_version"),
                    chunks=result["metrics"]["chunks_retrieved"],
                )

                # Envoyer les tokens streamés
                for char in result["answer"]:
                    yield f"data: {char}\n\n"

            except Exception as e:
                log.error(f"[API-Versioning] Erreur stream: {e}")
                yield f"data: [ERROR] {str(e)}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as e:
        log.error(f"[API-Versioning] Erreur query/stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=QueryResponse)
async def chat_with_versioning(req: QueryRequest) -> QueryResponse:
    """
    Chat RAG multi-tour avec versioning.

    Corps de la requête:
    {
        "messages": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }

    Réponse inclut model_version utilisée.
    """
    try:
        messages = [
            {"role": m.role, "content": m.content} for m in (req.messages or [])
        ]

        if not messages:
            raise HTTPException(
                status_code=400, detail="messages est requis pour /chat"
            )

        log.info(
            "[API-Versioning] Chat reçu",
            messages=len(messages),
            last_question=messages[-1]["content"][:50] if messages else "",
        )

        # Exécuter le chat avec versioning
        result = await _get_pipeline().query_with_version(
            question=messages[-1]["content"],
            top_k=req.top_k or 5,
            filters=req.filters,
            run_name=f"api_chat_{len(messages)}_turns",
        )

        response = QueryResponse(
            answer=result["answer"],
            contexts=result["contexts"],
            question=messages[-1]["content"],
        )

        log.info(
            "[API-Versioning] Chat OK",
            version=result.get("model_version"),
            total_time_ms=result["metrics"]["total_time_ms"],
        )

        return response

    except Exception as e:
        log.error(f"[API-Versioning] Erreur chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream_with_versioning(req: QueryRequest) -> StreamingResponse:
    """Chat RAG streaming avec versioning."""
    try:
        messages = [
            {"role": m.role, "content": m.content} for m in (req.messages or [])
        ]

        if not messages:
            raise HTTPException(status_code=400, detail="messages requis")

        log.info("[API-Versioning] Chat stream reçu", turns=len(messages))

        async def stream_generator():
            try:
                pipeline = _get_pipeline()
                result = await pipeline.query_with_version(
                    question=messages[-1]["content"],
                    top_k=req.top_k or 5,
                    run_name=f"api_chat_stream_{len(messages)}_turns",
                )

                log.info(
                    "[API-Versioning] Chat stream session",
                    version=result.get("model_version"),
                )

                for char in result["answer"]:
                    yield f"data: {char}\n\n"

            except Exception as e:
                log.error(f"[API-Versioning] Erreur chat/stream: {e}")
                yield f"data: [ERROR] {str(e)}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except Exception as e:
        log.error(f"[API-Versioning] Erreur chat/stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/versions")
async def get_model_versions():
    """
    Récupérer les versions du modèle RAG.

    Réponse:
    {
        "model_name": "rag-livraison-model",
        "versions": [
            {
                "version": 3,
                "stage": "Production",
                "status": "READY",
                "created_at": "2026-05-10T09:30:00"
            },
            ...
        ],
        "production_version": 3
    }
    """
    try:
        pipeline = _get_pipeline()
        report = pipeline.get_model_report()

        prod_version = None
        if report.get("production_model"):
            prod_version = report["production_model"].get("version")

        return {
            "model_name": report.get("model_name"),
            "versions": report.get("versions", []),
            "production_version": prod_version,
            "staging_versions": [
                v["version"] for v in report.get("staging_models", [])
            ],
            "archived_versions": [
                v["version"] for v in report.get("archived_models", [])
            ],
        }

    except Exception as e:
        log.error(f"[API-Versioning] Erreur get_versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/compare")
async def compare_model_versions(v1: int, v2: int):
    """
    Comparer deux versions du modèle.

    Query params: v1=1&v2=2

    Réponse:
    {
        "comparison": {
            "metric": "faithfulness",
            "version1": {"value": 0.82, "stage": "Archived"},
            "version2": {"value": 0.85, "stage": "Production"},
            "improvement_percent": 3.66,
            "winner": "v2"
        }
    }
    """
    try:
        pipeline = _get_pipeline()
        comparison = pipeline.get_model_comparison(v1=v1, v2=v2)

        return {"comparison": comparison}

    except Exception as e:
        log.error(f"[API-Versioning] Erreur compare: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/promote")
async def promote_model_version(version: int):
    """
    Promouvoir une version en Production.

    Query params: version=2
    """
    try:
        pipeline = _get_pipeline()
        pipeline.promote_to_production(version=version)

        log.info(f"[API-Versioning] Version {version} promue en Production")

        return {
            "status": "success",
            "message": f"Version {version} est maintenant en Production",
            "version": version,
            "stage": "Production",
        }

    except Exception as e:
        log.error(f"[API-Versioning] Erreur promote: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/info")
async def get_model_info(version: Optional[int] = None):
    """
    Récupérer les infos d'une version (ou Production par défaut).

    Query params: version=2 (optionnel)
    """
    try:
        pipeline = _get_pipeline()

        if version:
            info = pipeline.versioning_service.get_model_version_info(version)
        else:
            info = pipeline.versioning_service.get_production_model()

        if not info:
            raise HTTPException(status_code=404, detail="Version non trouvée")

        return {"model_info": info}

    except Exception as e:
        log.error(f"[API-Versioning] Erreur get_info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

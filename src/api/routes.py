"""Routes RAG — /query (POST) et /query/stream (POST SSE)."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.api.models import QueryRequest, QueryResponse
from src.rag.rag_pipeline import RAGPipeline
from config.settings import get_settings

router = APIRouter()
_pipeline: RAGPipeline | None = None


def _get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline(get_settings())
    return _pipeline


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    try:
        result = await _get_pipeline().query(
            req.question, top_k=req.top_k or 5, filters=req.filters
        )
        return QueryResponse(**result, question=req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def query_stream(req: QueryRequest) -> StreamingResponse:
    pipeline = _get_pipeline()

    async def event_gen():
        async for chunk in pipeline.stream(req.question, top_k=req.top_k or 5):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

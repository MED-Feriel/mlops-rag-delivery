"""Couche de compatibilité OpenAI Chat Completions — pour Open WebUI et autres clients."""

from __future__ import annotations

import json
import time
import uuid
from typing import Literal, Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.rag.rag_pipeline import RAGPipeline
from config.settings import get_settings

router = APIRouter()
_pipeline: RAGPipeline | None = None


def _get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline(get_settings())
    return _pipeline


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None


@router.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": "rag-livraison",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "mlops-rag-delivery",
            }
        ],
    }


def _completion_payload(model: str, content: str, chat_id: str, created: int) -> dict:
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk_payload(
    model: str,
    delta: dict,
    chat_id: str,
    created: int,
    finish_reason: Optional[str] = None,
) -> dict:
    return {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


async def _stream(
    req: ChatCompletionRequest, msgs: list[dict]
) -> AsyncGenerator[str, None]:
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    pipeline = _get_pipeline()

    yield "data: " + json.dumps(
        _chunk_payload(req.model, {"role": "assistant"}, chat_id, created)
    ) + "\n\n"

    try:
        async for token in pipeline.chat_stream(msgs):
            payload = _chunk_payload(req.model, {"content": token}, chat_id, created)
            yield "data: " + json.dumps(payload) + "\n\n"
    except Exception as e:
        err = _chunk_payload(
            req.model, {"content": f"\n[Erreur: {e}]"}, chat_id, created
        )
        yield "data: " + json.dumps(err) + "\n\n"

    yield "data: " + json.dumps(
        _chunk_payload(req.model, {}, chat_id, created, finish_reason="stop")
    ) + "\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if not any(m.role == "user" for m in req.messages):
        raise HTTPException(status_code=400, detail="aucun message utilisateur")

    msgs = [m.model_dump() for m in req.messages]

    if req.stream:
        return StreamingResponse(_stream(req, msgs), media_type="text/event-stream")

    result = await _get_pipeline().chat(msgs)
    return _completion_payload(
        req.model,
        result["answer"],
        chat_id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
    )

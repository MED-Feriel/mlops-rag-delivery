"""Modèles Pydantic pour l'API RAG."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "user" ou "assistant"
    content: str


class QueryRequest(BaseModel):
    question: Optional[str] = Field(default=None, max_length=500)
    messages: Optional[list[ChatMessage]] = None
    top_k: Optional[int] = Field(default=5, ge=1, le=20)
    filters: Optional[dict] = None
    stream: bool = True


class ContextChunk(BaseModel):
    text: str
    score: float
    metadata: dict


class QueryResponse(BaseModel):
    answer: str
    contexts: list[ContextChunk]
    question: str
    latency_ms: Optional[float] = None
    nb_docs_retrieved: Optional[int] = None


class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    qdrant: bool
    ollama: bool
    postgres: bool
    version: str
    timestamp: str


class CollectionStats(BaseModel):
    collection_name: str
    nb_vectors: int
    vector_size: int
    status: str

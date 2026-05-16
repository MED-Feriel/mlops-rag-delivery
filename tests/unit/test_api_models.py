"""Tests unitaires pour les modèles Pydantic de l'API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from pydantic import ValidationError

from src.api.models import (
    ChatMessage,
    CollectionStats,
    ContextChunk,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)


def test_query_request_defaults():
    q = QueryRequest(question="test")
    assert q.top_k == 5
    assert q.stream is True
    assert q.filters is None
    assert q.messages is None


def test_query_request_top_k_lower_bound():
    with pytest.raises(ValidationError):
        QueryRequest(question="x", top_k=0)


def test_query_request_top_k_upper_bound():
    with pytest.raises(ValidationError):
        QueryRequest(question="x", top_k=21)


def test_query_request_question_max_length():
    with pytest.raises(ValidationError):
        QueryRequest(question="a" * 501)


def test_query_request_optional_question():
    q = QueryRequest(messages=[ChatMessage(role="user", content="Hi")])
    assert q.question is None


def test_chat_message_roundtrip():
    msg = ChatMessage(role="user", content="Hello")
    assert msg.model_dump() == {"role": "user", "content": "Hello"}


def test_context_chunk_required_fields():
    c = ContextChunk(text="t", score=0.5, metadata={"src": "kafka"})
    assert c.score == 0.5
    assert c.metadata == {"src": "kafka"}


def test_query_response_defaults():
    r = QueryResponse(answer="ok", contexts=[], question="q")
    assert r.latency_ms is None
    assert r.nb_docs_retrieved is None


def test_health_response_serialization():
    h = HealthResponse(
        status="healthy",
        qdrant=True,
        ollama=True,
        postgres=True,
        version="2.0.0",
        timestamp="2026-05-16T00:00:00Z",
    )
    d = h.model_dump()
    assert d["status"] == "healthy"
    assert d["qdrant"] is True


def test_collection_stats_required_fields():
    s = CollectionStats(
        collection_name="rag", nb_vectors=100, vector_size=384, status="green"
    )
    assert s.nb_vectors == 100
    assert s.vector_size == 384

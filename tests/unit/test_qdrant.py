"""Tests unitaires Retrieval + QdrantVectorStore (mockés)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.retrieval.retrieval_service import (
    SCORE_THRESHOLD,
    RetrievalService,
)


def _retrieval_with_mock(search_results: list[dict]) -> RetrievalService:
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1] * 384
    store = MagicMock()
    store.search.return_value = search_results
    return RetrievalService(embedder, store)


def test_retrieve_returns_list_of_dicts(mock_qdrant):
    results = mock_qdrant.search([0.1] * 384, top_k=5)
    assert isinstance(results, list)
    assert {"text", "score", "metadata"}.issubset(results[0].keys())


def test_retrieve_applies_score_threshold():
    svc = _retrieval_with_mock(
        [
            {"text": "ok", "score": 0.92, "metadata": {}},
            {"text": "trop bas", "score": 0.10, "metadata": {}},
        ]
    )
    out = svc.retrieve("question")
    assert len(out) == 1
    assert out[0]["score"] >= SCORE_THRESHOLD


def test_retrieve_with_reranking_returns_top_k_final():
    svc = _retrieval_with_mock(
        [{"text": f"doc{i}", "score": 0.5 + i * 0.05, "metadata": {}} for i in range(8)]
    )
    out = svc.retrieve_with_reranking("q", top_k_initial=8, top_k_final=3)
    assert len(out) == 3


def test_build_context_string_under_max_chars():
    chunks = [
        {
            "text": "passage " * 100,
            "score": 0.9,
            "metadata": {"source": "commandes", "zone": "Z"},
        }
        for _ in range(20)
    ]
    ctx = RetrievalService.build_context_string(chunks, max_chars=2000)
    assert len(ctx) <= 2200  # marge pour le dernier passage avec son header


def test_build_context_string_includes_headers():
    chunks = [
        {
            "text": "X",
            "score": 0.9,
            "metadata": {"source": "commandes", "zone": "Bab Ezzouar"},
        }
    ]
    ctx = RetrievalService.build_context_string(chunks)
    assert "Passage 1" in ctx
    assert "commandes" in ctx
    assert "Bab Ezzouar" in ctx


def test_qdrant_upsert_returns_count(mock_qdrant):
    n = mock_qdrant.upsert(["a"], [[0.1] * 384], ["t"], [{}])
    assert n == 10

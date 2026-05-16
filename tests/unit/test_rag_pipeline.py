"""Tests unitaires RAG pipeline (avec mocks Qdrant + LLM)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_query_returns_answer_and_contexts(settings, mock_qdrant, mock_llm):
    with patch(
        "src.rag.rag_pipeline.QdrantVectorStore", return_value=mock_qdrant
    ), patch("src.rag.rag_pipeline.LLMService", return_value=mock_llm), patch(
        "src.rag.rag_pipeline.Embedder"
    ) as MockEmbedder:
        MockEmbedder.return_value.embed_query.return_value = [0.1] * 384
        from src.rag.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline(settings)
        result = await pipeline.query("Quels retards en zone Bab Ezzouar ?")
        assert "answer" in result
        assert "contexts" in result
        assert isinstance(result["contexts"], list)


@pytest.mark.asyncio
async def test_chat_uses_history_in_embedding_query(settings, mock_qdrant, mock_llm):
    with patch(
        "src.rag.rag_pipeline.QdrantVectorStore", return_value=mock_qdrant
    ), patch("src.rag.rag_pipeline.LLMService", return_value=mock_llm), patch(
        "src.rag.rag_pipeline.Embedder"
    ) as MockEmbedder:
        MockEmbedder.return_value.embed_query.return_value = [0.1] * 384
        from src.rag.rag_pipeline import RAGPipeline

        pipeline = RAGPipeline(settings)
        messages = [
            {"role": "user", "content": "Quels retards à Alger ?"},
            {"role": "assistant", "content": "..."},
            {"role": "user", "content": "Et les causes ?"},
        ]
        result = await pipeline.chat(messages)
        assert "answer" in result
        # L'embedder doit avoir reçu une concaténation des messages user récents
        called_query = MockEmbedder.return_value.embed_query.call_args[0][0]
        assert "Et les causes" in called_query


def test_build_rag_prompt_contains_system_and_context():
    from src.rag.prompt_builder import build_rag_prompt

    out = build_rag_prompt("Q ?", "CTX")
    assert "Q ?" in out["prompt"]
    assert "CTX" in out["prompt"]
    assert "français" in out["system"].lower() or "francais" in out["system"].lower()


def test_llm_prompt_contains_system_and_context():
    from src.llm.llm_service import LLMService, SYSTEM_PROMPT

    svc = LLMService(host="x", port=1)
    p = svc._build_prompt(context="CTX", question="Q ?")
    assert "CTX" in p and "Q ?" in p
    assert SYSTEM_PROMPT[:20] in p


@pytest.mark.asyncio
async def test_llm_health_check_detects_correct_model():
    """health_check() doit vérifier que gemma3:1b est disponible."""
    from src.llm.llm_service import LLMService

    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [{"name": "gemma3:1b"}]}
    fake_response.status_code = 200

    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=fake_client):
        svc = LLMService(host="x", port=1)
        assert await svc.health_check() is True


@pytest.mark.asyncio
async def test_llm_health_check_false_when_model_missing():
    from src.llm.llm_service import LLMService

    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [{"name": "llama3"}]}
    fake_response.status_code = 200
    fake_client = AsyncMock()
    fake_client.__aenter__.return_value = fake_client
    fake_client.get = AsyncMock(return_value=fake_response)

    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=fake_client):
        svc = LLMService(host="x", port=1)
        assert await svc.health_check() is False

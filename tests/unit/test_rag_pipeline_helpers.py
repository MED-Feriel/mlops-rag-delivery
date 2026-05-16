"""Tests des helpers statiques et asynchrones de RAGPipeline (mocks complets)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.rag_pipeline import RAGPipeline


def _make_pipeline_with_mocks():
    """Construit un RAGPipeline avec tous les composants externes mockés."""
    fake_settings = MagicMock(
        embedding_model="dummy",
        embedding_batch_size=8,
        qdrant_host="x",
        qdrant_port=6333,
        qdrant_collection="c",
        ollama_host="x",
        ollama_port=11434,
        ollama_model="gemma3:1b",
        ollama_timeout=120,
    )
    with patch("src.rag.rag_pipeline.Embedder"), patch(
        "src.rag.rag_pipeline.QdrantVectorStore"
    ), patch("src.rag.rag_pipeline.RetrievalService") as mock_ret, patch(
        "src.rag.rag_pipeline.LLMService"
    ) as mock_llm:
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            {"text": "doc1", "score": 0.9, "metadata": {"source": "k"}}
        ]
        mock_ret.return_value = mock_retriever

        mock_llm_inst = MagicMock()
        mock_llm_inst.generate = AsyncMock(return_value="Réponse mockée")
        mock_llm_inst.chat = AsyncMock(return_value="Chat mockée")
        mock_llm.return_value = mock_llm_inst

        return RAGPipeline(fake_settings), mock_retriever, mock_llm_inst


def test_build_embedding_query_uses_last_n_user_messages():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "R2"},
        {"role": "user", "content": "Q3"},
    ]
    out = RAGPipeline._build_embedding_query(msgs, history_window=3)
    assert "Q1" in out
    assert "Q2" in out
    assert "Q3" in out
    assert "R1" not in out
    assert "R2" not in out


def test_build_embedding_query_limits_to_window():
    msgs = [{"role": "user", "content": f"Q{i}"} for i in range(5)]
    out = RAGPipeline._build_embedding_query(msgs, history_window=2)
    # Doit garder les 2 derniers seulement
    assert "Q3" in out and "Q4" in out
    assert "Q0" not in out and "Q1" not in out


def test_build_embedding_query_no_user_messages_returns_empty():
    msgs = [{"role": "assistant", "content": "hello"}]
    assert RAGPipeline._build_embedding_query(msgs) == ""


def test_build_embedding_query_empty_messages():
    assert RAGPipeline._build_embedding_query([]) == ""


@pytest.mark.asyncio
async def test_query_returns_answer_and_contexts():
    pipeline, mock_ret, mock_llm = _make_pipeline_with_mocks()
    out = await pipeline.query("Quels livreurs en retard ?", top_k=5)
    assert out["answer"] == "Réponse mockée"
    assert len(out["contexts"]) == 1
    mock_ret.retrieve.assert_called_once()
    mock_llm.generate.assert_awaited_once()


async def _async_iter(items):
    for x in items:
        yield x


@pytest.mark.asyncio
async def test_stream_yields_tokens_from_llm():
    pipeline, mock_ret, mock_llm = _make_pipeline_with_mocks()
    mock_llm.stream = MagicMock(return_value=_async_iter(["Hello", " world"]))

    tokens = []
    async for tok in pipeline.stream("q", top_k=3):
        tokens.append(tok)
    assert tokens == ["Hello", " world"]
    mock_ret.retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream_yields_tokens():
    pipeline, mock_ret, mock_llm = _make_pipeline_with_mocks()
    mock_llm.chat_stream = MagicMock(return_value=_async_iter(["tok1", "tok2"]))

    msgs = [{"role": "user", "content": "q"}]
    tokens = []
    async for tok in pipeline.chat_stream(msgs, top_k=2):
        tokens.append(tok)
    assert tokens == ["tok1", "tok2"]


@pytest.mark.asyncio
async def test_chat_uses_embedding_query_built_from_messages():
    pipeline, mock_ret, mock_llm = _make_pipeline_with_mocks()
    msgs = [
        {"role": "user", "content": "Première question"},
        {"role": "assistant", "content": "réponse"},
        {"role": "user", "content": "Suite ?"},
    ]
    out = await pipeline.chat(msgs, top_k=3)
    assert out["answer"] == "Chat mockée"
    # La requête d'embedding doit contenir les messages user
    embedding_query = mock_ret.retrieve.call_args.args[0]
    assert "Première question" in embedding_query
    assert "Suite ?" in embedding_query
    assert "réponse" not in embedding_query

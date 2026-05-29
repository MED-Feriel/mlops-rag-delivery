"""Tests unitaires pour QdrantVectorStore (qdrant_client mocké)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from unittest.mock import MagicMock, patch

from qdrant_client.models import UpdateStatus


def _make_store(existing_collections=("livraison_rag",)):
    """Construit un QdrantVectorStore avec QdrantClient mocké."""
    from src.vector_store.qdrant_client import QdrantVectorStore

    with patch("src.vector_store.qdrant_client.QdrantClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = [MagicMock(name=c) for c in existing_collections]
        # Hack: MagicMock(name=...) ne fixe pas l'attribut .name, on le force
        for col_mock, col_name in zip(
            mock_collections.collections, existing_collections
        ):
            col_mock.name = col_name
        mock_client.get_collections.return_value = mock_collections
        mock_client_cls.return_value = mock_client

        store = QdrantVectorStore("localhost", 6333, "livraison_rag")
        return store, mock_client


def test_init_skips_creation_when_collection_exists():
    store, mock_client = _make_store(existing_collections=("livraison_rag",))
    mock_client.create_collection.assert_not_called()


def test_init_creates_collection_when_missing():
    store, mock_client = _make_store(existing_collections=("autre",))
    mock_client.create_collection.assert_called_once()
    # 6 index payload attendus : source, source_service, topic, zone, criticite, type_event
    assert mock_client.create_payload_index.call_count == 6


def test_upsert_returns_count_on_success():
    store, mock_client = _make_store()
    mock_client.upsert.return_value = MagicMock(status=UpdateStatus.COMPLETED)

    n = store.upsert(
        ids=["doc1", "doc2"],
        vectors=[[0.1] * 384, [0.2] * 384],
        documents=["text 1", "text 2"],
        metadatas=[{"source": "kafka"}, {"source": "postgres"}],
    )
    assert n == 2
    mock_client.upsert.assert_called_once()


def test_upsert_returns_zero_on_failure():
    store, mock_client = _make_store()
    mock_client.upsert.return_value = MagicMock(status="failed")

    n = store.upsert(["d"], [[0.1] * 384], ["t"], [{}])
    assert n == 0


def test_search_without_filters():
    store, mock_client = _make_store()
    mock_result = MagicMock()
    mock_result.payload = {"text": "Commande 4521", "source": "kafka", "zone": "Centre"}
    mock_result.score = 0.92
    mock_client.search.return_value = [mock_result]

    out = store.search([0.1] * 384, top_k=5)
    assert len(out) == 1
    assert out[0]["text"] == "Commande 4521"
    assert out[0]["score"] == 0.92
    assert out[0]["metadata"] == {"source": "kafka", "zone": "Centre"}
    # Vérifie que aucun filtre n'a été passé
    call_kwargs = mock_client.search.call_args.kwargs
    assert call_kwargs["query_filter"] is None
    assert call_kwargs["limit"] == 5


def test_search_with_filters_builds_qdrant_filter():
    store, mock_client = _make_store()
    mock_client.search.return_value = []

    store.search([0.1] * 384, top_k=3, filters={"source": "kafka", "zone": "Centre"})
    call_kwargs = mock_client.search.call_args.kwargs
    qf = call_kwargs["query_filter"]
    assert qf is not None
    # Le Filter doit contenir 2 conditions must
    assert len(qf.must) == 2


def test_search_respects_score_threshold():
    store, mock_client = _make_store()
    mock_client.search.return_value = []

    store.search([0.1] * 384, score_threshold=0.5)
    assert mock_client.search.call_args.kwargs["score_threshold"] == 0.5


def test_reset_deletes_and_recreates():
    store, mock_client = _make_store(existing_collections=("livraison_rag",))
    # Reset: après delete, la collection n'existe plus → _ensure_collection la recrée
    mock_collections_empty = MagicMock()
    mock_collections_empty.collections = []
    mock_client.get_collections.return_value = mock_collections_empty

    store.reset()
    mock_client.delete_collection.assert_called_once_with("livraison_rag")
    mock_client.create_collection.assert_called()


def test_count_returns_points_count():
    store, mock_client = _make_store()
    mock_info = MagicMock()
    mock_info.points_count = 1234
    mock_client.get_collection.return_value = mock_info

    assert store.count() == 1234

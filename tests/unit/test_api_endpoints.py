"""Tests unitaires des endpoints FastAPI (TestClient + mocks)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_metrics_endpoint_returns_200(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")


def test_metrics_endpoint_returns_prometheus_format(client):
    r = client.get("/metrics")
    body = r.text
    assert (
        "rag_query_total" in body
        or "# HELP" in body
        or "prometheus_client not installed" in body
    )


@patch("src.api.main._check_postgres")
@patch("src.api.main._check_ollama", new_callable=AsyncMock)
@patch("src.api.main._check_qdrant", new_callable=AsyncMock)
def test_health_all_up_returns_healthy(mock_qdrant, mock_ollama, mock_pg, client):
    mock_qdrant.return_value = True
    mock_ollama.return_value = True
    mock_pg.return_value = True
    r = client.get("/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "healthy"
    assert payload["qdrant"] is True
    assert payload["ollama"] is True
    assert payload["postgres"] is True
    assert "timestamp" in payload
    assert payload["version"] == "2.0.0"


@patch("src.api.main._check_postgres")
@patch("src.api.main._check_ollama", new_callable=AsyncMock)
@patch("src.api.main._check_qdrant", new_callable=AsyncMock)
def test_health_partial_returns_degraded(mock_qdrant, mock_ollama, mock_pg, client):
    mock_qdrant.return_value = True
    mock_ollama.return_value = False
    mock_pg.return_value = False
    r = client.get("/health")
    assert r.json()["status"] == "degraded"


@patch("src.api.main._check_postgres")
@patch("src.api.main._check_ollama", new_callable=AsyncMock)
@patch("src.api.main._check_qdrant", new_callable=AsyncMock)
def test_health_all_down_returns_unhealthy(mock_qdrant, mock_ollama, mock_pg, client):
    mock_qdrant.return_value = False
    mock_ollama.return_value = False
    mock_pg.return_value = False
    r = client.get("/health")
    assert r.json()["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_check_qdrant_returns_false_on_connection_error():
    from src.api.main import _check_qdrant

    fake_settings = MagicMock(qdrant_host="invalid-host-doesnotexist")
    assert await _check_qdrant(fake_settings) is False


@pytest.mark.asyncio
async def test_check_ollama_returns_false_on_connection_error():
    from src.api.main import _check_ollama

    fake_settings = MagicMock(
        ollama_host="invalid-host-doesnotexist",
        ollama_port=65000,
        ollama_model="gemma3:1b",
    )
    assert await _check_ollama(fake_settings) is False


def test_check_postgres_returns_false_on_connection_error():
    from src.api.main import _check_postgres

    fake_settings = MagicMock(
        postgres_host="invalid-host-doesnotexist",
        postgres_port=65000,
        postgres_db="x",
        postgres_user="x",
        postgres_password="x",
    )
    assert _check_postgres(fake_settings) is False


def test_collection_stats_success(client):
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"result": {"points_count": 1234, "status": "green"}}
    fake_resp.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.get = AsyncMock(return_value=fake_resp)

    with patch("src.api.main.httpx.AsyncClient", return_value=fake_client):
        r = client.get("/collections/stats")
    assert r.status_code == 200
    payload = r.json()
    assert payload["nb_vectors"] == 1234
    assert payload["status"] == "green"
    assert payload["vector_size"] == 384


# ─── OpenAI-compatible endpoints (openai_compat.py) ──────────────────────────


def test_list_models_returns_rag_livraison(client):
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    assert len(data["data"]) >= 1
    assert data["data"][0]["id"] == "rag-livraison"
    assert data["data"][0]["object"] == "model"


def test_chat_completions_rejects_payload_without_user_message(client):
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-livraison",
            "messages": [{"role": "system", "content": "soit utile"}],
            "stream": False,
        },
    )
    assert r.status_code == 400
    assert "utilisateur" in r.json()["detail"].lower()


def test_chat_completions_rejects_invalid_role(client):
    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "rag-livraison",
            "messages": [{"role": "invalid_role", "content": "hi"}],
        },
    )
    # Pydantic Literal validation should kick in
    assert r.status_code == 422


def test_chat_completions_non_stream_returns_completion(client):
    with patch("src.api.openai_compat._get_pipeline") as mock_pipe:
        mock_pipeline = MagicMock()
        mock_pipeline.chat = AsyncMock(return_value={"answer": "Réponse RAG mockée"})
        mock_pipe.return_value = mock_pipeline

        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "rag-livraison",
                "messages": [{"role": "user", "content": "Quels livreurs en retard ?"}],
                "stream": False,
            },
        )
    assert r.status_code == 200
    payload = r.json()
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "rag-livraison"
    assert payload["choices"][0]["message"]["content"] == "Réponse RAG mockée"
    assert payload["choices"][0]["finish_reason"] == "stop"
    assert payload["id"].startswith("chatcmpl-")


def test_completion_payload_structure():
    from src.api.openai_compat import _completion_payload

    out = _completion_payload("m", "hello", "chatcmpl-abc", 1700000000)
    assert out["id"] == "chatcmpl-abc"
    assert out["model"] == "m"
    assert out["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert out["choices"][0]["finish_reason"] == "stop"


def test_chunk_payload_structure():
    from src.api.openai_compat import _chunk_payload

    out = _chunk_payload("m", {"content": "tok"}, "id1", 1700000000)
    assert out["object"] == "chat.completion.chunk"
    assert out["choices"][0]["delta"] == {"content": "tok"}
    assert out["choices"][0]["finish_reason"] is None


def test_chunk_payload_with_finish_reason():
    from src.api.openai_compat import _chunk_payload

    out = _chunk_payload("m", {}, "id1", 1700000000, finish_reason="stop")
    assert out["choices"][0]["finish_reason"] == "stop"

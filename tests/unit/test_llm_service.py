"""Tests unitaires pour LLMService (httpx mocké, aucune connexion réelle à Ollama)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.llm_service import LLMService, _format_history


def test_format_history_excludes_last_message():
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q2_LAST"},
    ]
    h = _format_history(msgs)
    assert "Q1" in h
    assert "R1" in h
    assert "Q2_LAST" not in h
    assert "UTILISATEUR" in h
    assert "ASSISTANT" in h


def test_format_history_single_message_returns_empty():
    assert _format_history([{"role": "user", "content": "only"}]) == ""


def test_format_history_unknown_role_uppercased():
    h = _format_history(
        [
            {"role": "tool", "content": "data"},
            {"role": "user", "content": "last"},
        ]
    )
    assert "TOOL" in h


def test_llmservice_base_url_built_from_host_port():
    svc = LLMService("ollama", 11434, model="gemma3:1b")
    assert svc.base_url == "http://ollama:11434"
    assert svc.model == "gemma3:1b"
    assert svc.timeout == 120


def test_build_prompt_includes_context_and_question():
    svc = LLMService("h", 11434)
    p = svc._build_prompt("CTX_DATA", "MY_QUESTION")
    assert "CTX_DATA" in p
    assert "MY_QUESTION" in p
    assert "CONTEXTE" in p


def test_build_chat_prompt_includes_history_and_last_question():
    svc = LLMService("h", 11434)
    msgs = [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "R1"},
        {"role": "user", "content": "Q_LAST"},
    ]
    p = svc._build_chat_prompt(msgs, "CTX")
    assert "Q_LAST" in p
    assert "HISTORIQUE" in p
    assert "Q1" in p
    assert "R1" in p
    assert "CTX" in p


def test_build_chat_prompt_without_history():
    svc = LLMService("h", 11434)
    p = svc._build_chat_prompt([{"role": "user", "content": "only"}], "CTX")
    assert "only" in p
    assert "HISTORIQUE" not in p


def test_build_chat_prompt_empty_messages_does_not_crash():
    svc = LLMService("h", 11434)
    p = svc._build_chat_prompt([], "CTX")
    assert "CTX" in p


def _make_async_client_mock(json_payload):
    """Helper pour mocker httpx.AsyncClient avec un POST réussi."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_payload
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client, mock_response


@pytest.mark.asyncio
async def test_generate_calls_ollama_and_returns_response():
    mock_client, _ = _make_async_client_mock({"response": "Réponse mockée"})
    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=mock_client):
        svc = LLMService("h", 11434)
        out = await svc.generate("ctx", "q")
    assert out == "Réponse mockée"
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["json"]["model"] == "gemma3:1b"
    assert call_kwargs["json"]["stream"] is False


@pytest.mark.asyncio
async def test_chat_uses_chat_prompt():
    mock_client, _ = _make_async_client_mock({"response": "chat ok"})
    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=mock_client):
        svc = LLMService("h", 11434)
        out = await svc.chat([{"role": "user", "content": "hi"}], "CTX")
    assert out == "chat ok"
    prompt_sent = mock_client.post.await_args.kwargs["json"]["prompt"]
    assert "CTX" in prompt_sent


@pytest.mark.asyncio
async def test_health_check_returns_false_on_connection_error():
    svc = LLMService("invalid-host-doesnotexist", 65000, timeout=1)
    assert await svc.health_check() is False


@pytest.mark.asyncio
async def test_health_check_true_when_model_present():
    mock_response = MagicMock()
    mock_response.json.return_value = {"models": [{"name": "gemma3:1b"}]}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=mock_client):
        svc = LLMService("h", 11434, model="gemma3:1b")
        assert await svc.health_check() is True


@pytest.mark.asyncio
async def test_health_check_false_when_model_absent():
    mock_response = MagicMock()
    mock_response.json.return_value = {"models": [{"name": "llama3:8b"}]}
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("src.llm.llm_service.httpx.AsyncClient", return_value=mock_client):
        svc = LLMService("h", 11434, model="gemma3:1b")
        assert await svc.health_check() is False

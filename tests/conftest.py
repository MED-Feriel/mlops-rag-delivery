import pytest
from unittest.mock import AsyncMock, MagicMock
from config.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        qdrant_host="localhost",
        qdrant_collection="test_collection",
        ollama_model="gemma3:1b",
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
    )


@pytest.fixture
def mock_qdrant():
    mock = MagicMock()
    mock.upsert.return_value = 10
    mock.search.return_value = [
        {
            "text": "Commande 4521 retard 27 min Bab Ezzouar",
            "score": 0.92,
            "metadata": {"criticite": "haute"},
        }
    ]
    return mock


@pytest.fixture
def mock_llm():
    mock = AsyncMock()
    mock.generate.return_value = "Réponse Gemma3 de test."
    mock.health_check.return_value = True
    return mock

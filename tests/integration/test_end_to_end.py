"""Tests d'intégration end-to-end — nécessitent la stack docker compose up.

Ces tests sont marqués ``integration`` et sont skippés si les services ne
sont pas joignables localement (CI sans stack).
"""

from __future__ import annotations

import os

import httpx
import pytest

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
API_URL = os.getenv("API_URL", "http://localhost:8080")


def _alive(url: str, path: str = "/", timeout: float = 1.5) -> bool:
    try:
        r = httpx.get(f"{url}{path}", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def require_qdrant():
    if not _alive(QDRANT_URL, "/collections"):
        pytest.skip("Qdrant indisponible")


@pytest.fixture(scope="module")
def require_ollama():
    if not _alive(OLLAMA_URL, "/api/tags"):
        pytest.skip("Ollama indisponible")


@pytest.fixture(scope="module")
def require_api():
    if not _alive(API_URL, "/health"):
        pytest.skip("API indisponible")


def test_qdrant_collections_endpoint(require_qdrant):
    r = httpx.get(f"{QDRANT_URL}/collections", timeout=3)
    assert r.status_code == 200
    assert "result" in r.json()


def test_ollama_has_gemma3_1b(require_ollama):
    r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
    assert r.status_code == 200
    names = {m["name"] for m in r.json().get("models", [])}
    assert "gemma3:1b" in names


def test_api_health_returns_expected_schema(require_api):
    r = httpx.get(f"{API_URL}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    for key in ("status", "qdrant", "ollama", "postgres", "version", "timestamp"):
        assert key in body


def test_api_metrics_endpoint(require_api):
    r = httpx.get(f"{API_URL}/metrics", timeout=5)
    assert r.status_code == 200

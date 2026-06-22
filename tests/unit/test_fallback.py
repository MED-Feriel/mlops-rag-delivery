"""Tests unitaires du fallback extractif (réponse sans LLM)."""

from src.rag.fallback import build_extractive_answer


def test_empty_chunks_returns_unavailable_message():
    out = build_extractive_answer("question", [])
    assert "indisponible" in out.lower()


def test_lists_sources_and_truncates_long_snippets():
    chunks = [
        {
            "text": "Commande 4521 en retard de 27 min à Bab Ezzouar.",
            "metadata": {"source": "incidents", "zone": "Bab Ezzouar"},
        },
        {"text": "x" * 500, "metadata": {"source": "commandes"}},
    ]
    out = build_extractive_answer("retards", chunks)
    assert "incidents" in out
    assert "Bab Ezzouar" in out
    assert "…" in out  # snippet long tronqué
    assert out.count("\n- ") == 2  # deux puces


def test_ignores_blank_chunks():
    chunks = [
        {"text": "   ", "metadata": {}},
        {"text": "vrai contenu", "metadata": {"source": "logs"}},
    ]
    out = build_extractive_answer("q", chunks)
    assert "vrai contenu" in out
    assert out.count("\n- ") == 1


def test_caps_number_of_chunks():
    chunks = [{"text": f"doc {i}", "metadata": {"source": "x"}} for i in range(20)]
    out = build_extractive_answer("q", chunks)
    assert out.count("\n- ") == 5  # MAX_CHUNKS

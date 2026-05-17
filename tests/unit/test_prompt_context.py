"""Tests unitaires pour prompt_builder et context_builder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from src.rag.context_builder import build_context
from src.rag.prompt_builder import SYSTEM_PROMPT, build_rag_prompt


def test_build_rag_prompt_structure():
    out = build_rag_prompt("Qui est en retard ?", "doc A\ndoc B")
    assert out["question"] == "Qui est en retard ?"
    assert "doc A" in out["context"]
    assert SYSTEM_PROMPT in out["prompt"]
    assert "=== CONTEXTE RÉEL ===" in out["prompt"]
    assert "=== FIN CONTEXTE ===" in out["prompt"]


def test_build_rag_prompt_includes_few_shot_example():
    out = build_rag_prompt("q", "ctx")
    assert "=== EXEMPLE ===" in out["prompt"]
    assert "=== FIN EXEMPLE ===" in out["prompt"]


def test_build_rag_prompt_custom_system():
    out = build_rag_prompt("q", "ctx", system_prompt="Custom system")
    assert out["system"] == "Custom system"
    assert "Custom system" in out["prompt"]


def test_build_context_includes_metadata_and_score():
    chunks = [
        {
            "text": "Commande 4521 en retard",
            "score": 0.92,
            "metadata": {"source": "kafka"},
        },
        {
            "text": "Commande 4522 livrée",
            "score": 0.81,
            "metadata": {"source": "postgres"},
        },
    ]
    ctx = build_context(chunks)
    assert "Doc 1" in ctx and "Doc 2" in ctx
    assert "source=kafka" in ctx
    assert "source=postgres" in ctx
    assert "0.92" in ctx


def test_build_context_respects_max_chars():
    chunks = [
        {"text": "x" * 1000, "score": 1.0, "metadata": {"source": "s"}}
        for _ in range(10)
    ]
    ctx = build_context(chunks, max_chars=2500)
    assert len(ctx) <= 2500 + 200  # tolère le header


def test_build_context_empty_chunks():
    assert build_context([]) == ""


def test_build_context_missing_metadata_key():
    """Un chunk sans 'metadata' doit retourner source='?'."""
    ctx = build_context([{"text": "x", "score": 0.5}])
    assert "source=?" in ctx


def test_build_context_missing_score():
    """Un chunk sans 'score' doit afficher 0.00 sans crasher."""
    ctx = build_context([{"text": "y", "metadata": {"source": "k"}}])
    assert "0.00" in ctx


def test_build_context_stops_at_limit():
    chunks = [
        {"text": "small", "score": 0.5, "metadata": {"source": "a"}},
        {"text": "z" * 10000, "score": 0.4, "metadata": {"source": "b"}},
    ]
    ctx = build_context(chunks, max_chars=200)
    # Le second chunk dépasse → doit être tronqué
    assert "small" in ctx
    assert "z" * 100 not in ctx

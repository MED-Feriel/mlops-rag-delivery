"""Tests du guardrail anti-hallucination (contexte vide → réponse de secours)."""

from src.rag.guardrails import REFUS_CONTEXTE_VIDE, check_context


def test_context_vide_renvoie_refus():
    ok, msg = check_context("")
    assert ok is False
    assert msg == REFUS_CONTEXTE_VIDE


def test_context_none_renvoie_refus():
    ok, msg = check_context(None)  # type: ignore[arg-type]
    assert ok is False
    assert msg == REFUS_CONTEXTE_VIDE


def test_context_espaces_seuls_renvoie_refus():
    # Contexte uniquement blanc (aucun doc récupéré) → refus.
    ok, msg = check_context("   \n  \t ")
    assert ok is False
    assert "Information non disponible" in msg


def test_context_doc_minimal_passe():
    # Un document récupéré, même court, ne doit PAS déclencher le refus
    # (le retrieval a ramené quelque chose → on laisse le LLM répondre).
    ok, msg = check_context("[Doc 1 | source=k | score=0.90]\ndoc1")
    assert ok is True
    assert msg == ""


def test_context_suffisant_passe():
    contexte = (
        "[Doc 1 | source=prometheus | score=0.04]\n"
        "État de santé de la plateforme au 2026-05-29 09:40 UTC. "
        "Taux de succès du RAG : 100.0%. 5 services actifs."
    )
    ok, msg = check_context(contexte)
    assert ok is True
    assert msg == ""

"""Tests unitaires des métriques d'évaluation déterministe (sans réseau)."""

from tests.evaluation.evaluate import (
    aggregate,
    evaluate_retrieval,
    is_relevant,
    mrr,
    precision_at_k,
    recall_at_k,
    relevance_flags,
    top1_accuracy,
)


def test_is_relevant_par_source():
    q = {"source_attendue": "prometheus", "entites_attendues": []}
    assert is_relevant({"metadata": {"source": "prometheus"}}, q) is True
    assert is_relevant({"metadata": {"source": "commandes"}}, q) is False


def test_is_relevant_par_entite_si_pas_de_source():
    q = {"source_attendue": "", "entites_attendues": ["Hydra"]}
    assert is_relevant({"text": "Synthèse zone Hydra", "metadata": {}}, q) is True
    assert is_relevant({"text": "zone Kouba", "metadata": {}}, q) is False


def test_top1_accuracy():
    assert top1_accuracy([True, False]) == 1.0
    assert top1_accuracy([False, True]) == 0.0
    assert top1_accuracy([]) == 0.0


def test_mrr_rang_du_premier_pertinent():
    assert mrr([False, False, True]) == 1.0 / 3
    assert mrr([True]) == 1.0
    assert mrr([False, False]) == 0.0


def test_precision_at_k():
    assert precision_at_k([True, False, True, False], 4) == 0.5
    assert precision_at_k([True, True], 0) == 0.0


def test_recall_at_k_hit():
    assert recall_at_k([False, False, True], 3) == 1.0
    assert recall_at_k([False, False, True], 2) == 0.0


def test_evaluate_retrieval_et_aggregate():
    questions = [
        {
            "id": "F1_Q1",
            "famille": "F1",
            "question": "retards restaurants",
            "source_attendue": "synthese",
            "entites_attendues": [],
        },
        {
            "id": "F3_Q1",
            "famille": "F3",
            "question": "santé plateforme",
            "source_attendue": "prometheus",
            "entites_attendues": [],
        },
    ]

    def fake(question, top_k):
        return [
            {"text": question, "score": 0.9, "metadata": {"source": "synthese"}},
            {"text": question, "score": 0.5, "metadata": {"source": "prometheus"}},
        ]

    res = evaluate_retrieval(questions, fake, top_k=2)
    summary = aggregate(res)
    # F1 : doc1 pertinent (synthese) → top1=1 ; F3 : doc2 pertinent → top1=0, mrr=0.5
    assert summary["by_family"]["F1"]["top1_accuracy"] == 1.0
    assert summary["by_family"]["F3"]["top1_accuracy"] == 0.0
    assert summary["by_family"]["F3"]["mrr"] == 0.5
    assert summary["global"]["n"] == 2


def test_relevance_flags_ordonnes():
    q = {"source_attendue": "synthese", "entites_attendues": []}
    docs = [
        {"metadata": {"source": "commandes"}},
        {"metadata": {"source": "synthese"}},
    ]
    assert relevance_flags(docs, q) == [False, True]

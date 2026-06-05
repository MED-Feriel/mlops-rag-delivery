"""Tests unitaires BM25 Okapi + Reciprocal Rank Fusion."""

from src.retrieval.bm25 import BM25Okapi, reciprocal_rank_fusion, tokenize


def test_tokenize_minuscule_et_mots_courts_ecartes():
    assert tokenize("Pizza à Hydra !") == ["pizza", "hydra"]  # "à" (1 char) écarté


def test_tokenize_garde_accents():
    assert "échouée" in tokenize("Livraison échouée")


def test_bm25_terme_rare_score_plus_eleve():
    corpus = [
        tokenize("retard livraison pizza hydra"),
        tokenize("commande livree a temps dely ibrahim"),
        tokenize("incident pizza hydra paiement"),
    ]
    bm = BM25Okapi(corpus)
    scores = bm.get_scores(tokenize("pizza hydra"))
    # Les docs 0 et 2 contiennent les deux termes → score > 0 ; doc 1 → 0.
    assert scores[0] > 0 and scores[2] > 0
    assert scores[1] == 0.0


def test_bm25_corpus_vide():
    bm = BM25Okapi([])
    assert bm.get_scores(tokenize("rien")) == []


def test_bm25_idf_strictement_positif():
    corpus = [tokenize("a b c"), tokenize("a b"), tokenize("a")]
    bm = BM25Okapi(corpus)
    # Même le terme présent partout ("a") garde un idf positif (forme +1).
    assert all(v > 0 for v in bm.idf.values())


def test_rrf_document_bien_classe_dans_les_deux_gagne():
    # doc 0 : rang 1 dans les deux classements → score le plus élevé.
    fused = reciprocal_rank_fusion([[0, 1, 2], [0, 2, 1]], rrf_k=60)
    order = sorted(fused, key=lambda i: fused[i], reverse=True)
    assert order[0] == 0
    assert fused[0] == 2.0 / 61  # rang 1 dans les deux


def test_rrf_document_unique_par_classement():
    fused = reciprocal_rank_fusion([[5], [5]], rrf_k=60)
    assert fused[5] == 2.0 / 61

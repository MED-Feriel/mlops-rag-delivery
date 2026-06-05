"""BM25 Okapi — scoring lexical sparse en pur Python (aucune dépendance lourde).

Utilisé par le retrieval hybride : le score dense (Qdrant cosine) capture la
proximité sémantique, BM25 capture la correspondance lexicale exacte (noms de
restaurants, de zones, identifiants) que l'embedding multilingue dilue souvent.

Choix d'implémentation : BM25 est calculé *côté client* sur le pool de candidats
ramenés par la recherche dense, et non via des vecteurs sparse natifs Qdrant.
Raison : la collection ``livraison_rag`` (~167k points) est indexée avec un seul
vecteur dense 384-dim ; ajouter des vecteurs sparse natifs imposerait de recréer
la collection et de relancer tout l'ETL. Le pattern « sur-récupération dense puis
re-classement lexical » fournit un vrai signal BM25 sans ré-indexation.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Tokenizer simple, compatible français (garde les accents via \w + UNICODE).
# Tokens d'au moins 2 caractères pour écarter le bruit ponctuel.
_TOKEN_RE = re.compile(r"\w{2,}", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Découpe un texte en tokens minuscules (mots de 2+ caractères)."""
    return _TOKEN_RE.findall(text.lower())


class BM25Okapi:
    """BM25 Okapi sur un petit corpus en mémoire.

    Paramètres standard ``k1=1.5`` (saturation de fréquence) et ``b=0.75``
    (normalisation par longueur). Le corpus est typiquement le pool de candidats
    d'une seule requête (quelques dizaines de documents), donc le coût est
    négligeable.
    """

    def __init__(
        self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.doc_len = [len(doc) for doc in corpus]
        self.n_docs = len(corpus)
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        self.doc_freqs: list[Counter] = [Counter(doc) for doc in corpus]
        self.idf = self._compute_idf()

    def _compute_idf(self) -> dict[str, float]:
        """IDF BM25 (forme probabiliste, plancher à 0 pour rester positif)."""
        df: Counter = Counter()
        for doc in self.corpus:
            for term in set(doc):
                df[term] += 1
        idf: dict[str, float] = {}
        for term, freq in df.items():
            # +1 au numérateur garantit un idf strictement positif (évite les
            # poids négatifs des termes très fréquents du BM25 Okapi brut).
            idf[term] = math.log(1 + (self.n_docs - freq + 0.5) / (freq + 0.5))
        return idf

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        """Score BM25 de chaque document du corpus pour la requête donnée."""
        scores = [0.0] * self.n_docs
        if self.avgdl == 0:
            return scores
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                tf = freqs.get(term, 0)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (
                    1 - self.b + self.b * self.doc_len[i] / self.avgdl
                )
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        return scores


def reciprocal_rank_fusion(
    rankings: list[list[int]], rrf_k: int = 60
) -> dict[int, float]:
    """Fusionne plusieurs classements (listes d'indices ordonnés) par RRF.

    Reciprocal Rank Fusion : ``score(d) = Σ_r 1 / (rrf_k + rang_r(d))`` où
    ``rang`` démarre à 1. ``rrf_k=60`` est la valeur de référence (Cormack 2009).
    Robuste aux échelles de scores hétérogènes (cosine ~[0,1] vs BM25 non borné).

    Retourne un dict ``{indice_document: score_rrf}``.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_idx in enumerate(ranking, start=1):
            fused[doc_idx] = fused.get(doc_idx, 0.0) + 1.0 / (rrf_k + rank)
    return fused

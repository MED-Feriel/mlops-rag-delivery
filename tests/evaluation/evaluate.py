"""Évaluation déterministe du pipeline RAG — retrieval uniquement.

Métriques : top-1 accuracy, MRR, precision@k, recall@k (proxy « hit@k »).
Aucun juge LLM (pas de RAGAS) : l'évaluation circulaire d'un petit modèle comme
Gemma3:1b notant ses propres réponses est peu fiable. On juge ici la pertinence
d'un document récupéré de façon déterministe, à partir de la source attendue
et/ou des entités attendues définies dans ``questions_reference.json``.

Définition de la pertinence (par question) :
  - si ``source_attendue`` est renseignée → un document est pertinent ssi sa
    métadonnée ``source`` est égale à cette source ;
  - sinon → pertinent ssi au moins une ``entites_attendues`` (insensible à la
    casse) apparaît dans le texte du document.

Usage (services Docker actifs) :
    python -m tests.evaluation.evaluate
    python -m tests.evaluation.evaluate --top-k 5 --dense   # comparer dense pur

Les fonctions de métriques sont pures (testables sans réseau) ; ``main()``
branche le vrai retriever construit depuis la config.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

QUESTIONS_FILE = Path(__file__).parent / "questions_reference.json"

# Type de la fonction de retrieval injectée : (question, top_k) -> liste de docs
# au format {"text": str, "score": float, "metadata": {"source": str, ...}}.
RetrieveFn = Callable[[str, int], list[dict]]


# ────────────────────────────────────────────────────────────────────
# Jugement de pertinence
# ────────────────────────────────────────────────────────────────────
def is_relevant(doc: dict, question: dict) -> bool:
    """Détermine de façon déterministe si ``doc`` est pertinent pour la question."""
    source_attendue = question.get("source_attendue") or ""
    if source_attendue:
        return doc.get("metadata", {}).get("source") == source_attendue
    text = doc.get("text", "").lower()
    return any(
        ent.lower() in text for ent in question.get("entites_attendues", [])
    )


# ────────────────────────────────────────────────────────────────────
# Métriques (pures)
# ────────────────────────────────────────────────────────────────────
def relevance_flags(docs: list[dict], question: dict) -> list[bool]:
    """Liste de booléens de pertinence, dans l'ordre du classement."""
    return [is_relevant(d, question) for d in docs]


def top1_accuracy(flags: list[bool]) -> float:
    """1.0 si le document de rang 1 est pertinent, sinon 0.0."""
    return 1.0 if flags and flags[0] else 0.0


def mrr(flags: list[bool]) -> float:
    """Reciprocal rank du premier document pertinent (0.0 si aucun)."""
    for rank, ok in enumerate(flags, start=1):
        if ok:
            return 1.0 / rank
    return 0.0


def precision_at_k(flags: list[bool], k: int) -> float:
    """Proportion de documents pertinents dans le top-k."""
    if k <= 0:
        return 0.0
    topk = flags[:k]
    return sum(topk) / k


def recall_at_k(flags: list[bool], k: int) -> float:
    """Proxy hit@k : 1.0 si au moins un document pertinent dans le top-k.

    Le rappel classique exige le nombre total de documents pertinents du corpus,
    inconnu ici (pas de labels exhaustifs). On retient donc le « hit@k », mesure
    standard quand seule la pertinence binaire est disponible.
    """
    return 1.0 if any(flags[:k]) else 0.0


# ────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────
def load_questions(path: Path = QUESTIONS_FILE) -> list[dict]:
    """Charge les questions de référence depuis le JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["questions"]


def evaluate_retrieval(
    questions: list[dict], retrieve_fn: RetrieveFn, top_k: int = 5
) -> dict:
    """Évalue le retrieval sur les questions ; renvoie le détail par question."""
    per_question = []
    for q in questions:
        docs = retrieve_fn(q["question"], top_k)
        flags = relevance_flags(docs, q)
        per_question.append(
            {
                "id": q["id"],
                "famille": q["famille"],
                "n_docs": len(docs),
                "top1_accuracy": top1_accuracy(flags),
                "mrr": mrr(flags),
                "precision@k": precision_at_k(flags, top_k),
                "recall@k": recall_at_k(flags, top_k),
            }
        )
    return {"top_k": top_k, "per_question": per_question}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(results: dict) -> dict:
    """Agrège les métriques globalement et par famille (F1/F2/F3/F4)."""
    rows = results["per_question"]
    metrics = ("top1_accuracy", "mrr", "precision@k", "recall@k")

    def agg(subset: list[dict]) -> dict:
        return {m: _mean([r[m] for r in subset]) for m in metrics} | {
            "n": len(subset)
        }

    by_family: dict[str, dict] = {}
    for fam in sorted({r["famille"] for r in rows}):
        by_family[fam] = agg([r for r in rows if r["famille"] == fam])
    return {"global": agg(rows), "by_family": by_family}


def generate_report(results: dict, summary: dict) -> str:
    """Produit un rapport markdown des résultats."""
    k = results["top_k"]
    lines = [
        f"# Rapport d'évaluation retrieval (top_k={k})",
        "",
        "## Global",
        "| Métrique | Valeur |",
        "|----------|--------|",
        f"| top-1 accuracy | {summary['global']['top1_accuracy']:.3f} |",
        f"| MRR | {summary['global']['mrr']:.3f} |",
        f"| precision@{k} | {summary['global']['precision@k']:.3f} |",
        f"| recall@{k} (hit) | {summary['global']['recall@k']:.3f} |",
        "",
        "## Par famille",
        "| Famille | n | top-1 | MRR | P@k | R@k |",
        "|---------|---|-------|-----|-----|-----|",
    ]
    for fam, m in summary["by_family"].items():
        lines.append(
            f"| {fam} | {m['n']} | {m['top1_accuracy']:.3f} | {m['mrr']:.3f} "
            f"| {m['precision@k']:.3f} | {m['recall@k']:.3f} |"
        )
    return "\n".join(lines)


def _build_retrieve_fn(use_hybrid: bool) -> RetrieveFn:
    """Construit la fonction de retrieval réelle depuis la config du projet."""
    from config.settings import get_settings
    from src.embeddings.embedder import Embedder
    from src.retrieval.retrieval_service import RetrievalService
    from src.vector_store.qdrant_client import QdrantVectorStore

    s = get_settings()
    embedder = Embedder(model_name=s.embedding_model, batch_size=s.embedding_batch_size)
    store = QdrantVectorStore(
        host=s.qdrant_host, port=s.qdrant_port, collection=s.qdrant_collection
    )
    service = RetrievalService(embedder, store)
    method = service.retrieve_hybrid if use_hybrid else service.retrieve
    return lambda question, top_k: method(question, top_k=top_k)


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation déterministe du RAG")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--dense",
        action="store_true",
        help="Utiliser le dense pur au lieu du hybride (BM25+RRF)",
    )
    args = parser.parse_args()

    questions = load_questions()
    retrieve_fn = _build_retrieve_fn(use_hybrid=not args.dense)
    results = evaluate_retrieval(questions, retrieve_fn, top_k=args.top_k)
    summary = aggregate(results)
    print(generate_report(results, summary))


if __name__ == "__main__":
    main()

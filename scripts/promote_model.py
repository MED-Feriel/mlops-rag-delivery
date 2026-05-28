"""
promote_model.py — Promotion conditionnelle Gemma3 Staging → Production
========================================================================
Règle de gating:
    faithfulness     >= 0.70
    answer_relevancy >= 0.60

Lit le dernier run de l'expérience "rag-evaluation", évalue les scores
RAGAS, et:
  - Si les seuils sont passés → archive l'ancienne Production puis promeut
    la dernière version Staging du modèle "gemma3-rag-livraison" en Production.
  - Sinon → log "Promotion bloquée" + raison + scores actuels et exit 0.

Usage:
    python scripts/promote_model.py
    python scripts/promote_model.py --tracking-uri http://localhost:5000
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional, Tuple

import mlflow
from mlflow.tracking import MlflowClient

MODEL_NAME = "gemma3-rag-livraison"
EVAL_EXPERIMENT = "rag-evaluation"
THRESHOLD_FAITHFULNESS = 0.70
THRESHOLD_ANSWER_RELEVANCY = 0.60


def _read_metric(run, names) -> Optional[float]:
    """Tente plusieurs noms de métrique et renvoie la première trouvée."""
    metrics = run.data.metrics or {}
    for n in names:
        if n in metrics:
            return float(metrics[n])
    return None


def get_latest_ragas_run(client: MlflowClient) -> Optional[object]:
    exp = client.get_experiment_by_name(EVAL_EXPERIMENT)
    if exp is None:
        print(f"[promote] Expérience introuvable: {EVAL_EXPERIMENT}", file=sys.stderr)
        return None
    runs = client.search_runs(
        experiment_ids=[exp.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    return runs[0] if runs else None


def evaluate_gate(run) -> Tuple[bool, dict, Optional[str]]:
    faith = _read_metric(run, ["faithfulness", "ragas_faithfulness"])
    rel = _read_metric(run, ["answer_relevancy", "ragas_answer_relevancy"])

    scores = {"faithfulness": faith, "answer_relevancy": rel}

    if faith is None or rel is None:
        return (
            False,
            scores,
            f"Métriques RAGAS absentes (faithfulness={faith}, answer_relevancy={rel})",
        )

    reasons = []
    if faith < THRESHOLD_FAITHFULNESS:
        reasons.append(f"faithfulness {faith:.3f} < {THRESHOLD_FAITHFULNESS}")
    if rel < THRESHOLD_ANSWER_RELEVANCY:
        reasons.append(f"answer_relevancy {rel:.3f} < {THRESHOLD_ANSWER_RELEVANCY}")

    return (not reasons), scores, ("; ".join(reasons) if reasons else None)


def _latest_staging_version(client: MlflowClient) -> Optional[str]:
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    staging = [v for v in versions if v.current_stage == "Staging"]
    if not staging:
        return None
    return max(staging, key=lambda v: int(v.version)).version


def _current_production_version(client: MlflowClient) -> Optional[str]:
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    prod = [v for v in versions if v.current_stage == "Production"]
    if not prod:
        return None
    return max(prod, key=lambda v: int(v.version)).version


def log_promotion_result(
    tracking_uri: str,
    promoted: bool,
    scores: dict,
    reason: Optional[str],
    promoted_version: Optional[str],
    archived_version: Optional[str],
) -> None:
    mlflow.set_tracking_uri(tracking_uri)
    exp_name = "model_promotion"
    if mlflow.get_experiment_by_name(exp_name) is None:
        mlflow.create_experiment(exp_name)
    mlflow.set_experiment(exp_name)

    with mlflow.start_run(
        run_name=f"promote_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ):
        mlflow.log_metrics({k: v for k, v in scores.items() if v is not None})
        mlflow.log_params(
            {
                "promoted": promoted,
                "promoted_version": promoted_version or "n/a",
                "archived_version": archived_version or "n/a",
                "threshold_faithfulness": THRESHOLD_FAITHFULNESS,
                "threshold_answer_relevancy": THRESHOLD_ANSWER_RELEVANCY,
            }
        )
        mlflow.set_tags(
            {
                "model_name": MODEL_NAME,
                "promotion_status": "success" if promoted else "blocked",
                "reason": (reason or "thresholds_met")[:500],
            }
        )


def main(tracking_uri: str) -> int:
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri)

    run = get_latest_ragas_run(client)
    if run is None:
        print(
            "[promote] Aucun run RAGAS trouvé — promotion impossible", file=sys.stderr
        )
        return 1

    print(f"[promote] Run RAGAS: {run.info.run_id}")
    passed, scores, reason = evaluate_gate(run)
    print(f"[promote] Scores: {json.dumps(scores)}")

    if not passed:
        msg = f"Promotion bloquée: {reason}"
        print(f"[promote] {msg}")
        log_promotion_result(tracking_uri, False, scores, reason, None, None)
        return 0

    staging_version = _latest_staging_version(client)
    if staging_version is None:
        msg = "Promotion bloquée: aucune version Staging à promouvoir"
        print(f"[promote] {msg}")
        log_promotion_result(tracking_uri, False, scores, msg, None, None)
        return 0

    archived_version = _current_production_version(client)
    if archived_version:
        client.transition_model_version_stage(
            name=MODEL_NAME, version=archived_version, stage="Archived"
        )
        print(f"[promote] Archivé v{archived_version} (ancienne Production)")

    client.transition_model_version_stage(
        name=MODEL_NAME, version=staging_version, stage="Production"
    )
    print(f"[promote] Promu v{staging_version} → Production")

    log_promotion_result(
        tracking_uri, True, scores, None, staging_version, archived_version
    )
    return 0


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    args = parser.parse_args()
    sys.exit(main(args.tracking_uri))


if __name__ == "__main__":
    cli()

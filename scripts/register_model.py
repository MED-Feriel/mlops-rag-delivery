"""
register_model.py — Enregistrement de Gemma3:1b dans le MLflow Model Registry
=============================================================================
Gemma3:1b est servi par Ollama (port 11434), pas par MLflow. Ce script
enregistre dans le Model Registry une *référence logique* vers le modèle
Ollama (nom + tags + description + paramètres), sans logger un artefact
pyfunc (l'inférence reste déléguée à Ollama).

Nom registry  : gemma3-rag-livraison
Version initiale : 1.0.0 → stage Staging
Tags : model_type=llm, framework=ollama, quantization=Q4_K_M

Usage:
    python scripts/register_model.py
    python scripts/register_model.py --tracking-uri http://localhost:5000
"""

import argparse
import json
import sys
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient

MODEL_NAME = "gemma3-rag-livraison"
MODEL_DESCRIPTION = "Gemma3 1B pour RAG supervision livraison — ENSTICP PFE 2025"
MODEL_TAGS = {
    "model_type": "llm",
    "framework": "ollama",
    "quantization": "Q4_K_M",
}
SEMVER = "1.0.0"
OLLAMA_MODEL = "gemma3:1b"


def register(tracking_uri: str) -> str:
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri)

    exp_name = "model_registry"
    if mlflow.get_experiment_by_name(exp_name) is None:
        mlflow.create_experiment(exp_name)
    mlflow.set_experiment(exp_name)

    run_name = f"register_gemma3_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.log_params(
            {
                "llm_model": OLLAMA_MODEL,
                "framework": "ollama",
                "quantization": "Q4_K_M",
                "parameter_size": "1B",
                "ollama_host": "http://localhost:11434",
                "semver": SEMVER,
            }
        )
        mlflow.set_tags(
            {
                **MODEL_TAGS,
                "semver": SEMVER,
                "registry_name": MODEL_NAME,
                "ollama_model": OLLAMA_MODEL,
            }
        )
        mlflow.log_param(
            "metadata_json",
            json.dumps(
                {
                    "ollama_model": OLLAMA_MODEL,
                    "description": MODEL_DESCRIPTION,
                    "semver": SEMVER,
                    "registered_at": datetime.now().isoformat(),
                }
            )[:500],
        )
        print(f"[register] Run créée: {run_id}")

    try:
        client.create_registered_model(
            name=MODEL_NAME,
            tags=MODEL_TAGS,
            description=MODEL_DESCRIPTION,
        )
        print(f"[register] Registered model créé: {MODEL_NAME}")
    except Exception as e:
        if "already exists" in str(e) or "RESOURCE_ALREADY_EXISTS" in str(e):
            print(f"[register] Registered model existe déjà: {MODEL_NAME}")
        else:
            raise

    source = f"runs:/{run_id}/ollama_reference"
    mv = client.create_model_version(
        name=MODEL_NAME,
        source=source,
        run_id=run_id,
        description=f"{MODEL_DESCRIPTION} (v{SEMVER})",
        tags={**MODEL_TAGS, "semver": SEMVER, "ollama_model": OLLAMA_MODEL},
    )
    version = mv.version
    print(f"[register] Version créée: {version} (semver={SEMVER})")

    client.transition_model_version_stage(
        name=MODEL_NAME, version=version, stage="Staging"
    )
    print(f"[register] OK — {MODEL_NAME} v{version} → Staging")

    summary = {
        "model_name": MODEL_NAME,
        "version": version,
        "semver": SEMVER,
        "stage": "Staging",
        "run_id": run_id,
        "ollama_model": OLLAMA_MODEL,
    }
    print(json.dumps(summary, indent=2))
    return version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    args = parser.parse_args()
    try:
        register(args.tracking_uri)
    except Exception as e:
        print(f"[register] ÉCHEC: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Capteur C5.2 — Vérification de l'état du modèle MLflow en production.

Exécution : Toutes les heures (DAG Airflow).
Métrique exposée : mlflow_production_model_healthy (1=OK, 0=KO).
Destination : Pushgateway Prometheus (port 9091).
Alerte : P0 si modèle injoignable pendant 5 min.
"""

import os
import logging
from datetime import datetime

import requests
from prometheus_client import Gauge, CollectorRegistry, push_to_gateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
API_URL = os.getenv("API_URL", "http://api:8080")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://pushgateway:9091")
MODEL_NAME = "rag-llm-model"


def get_production_version():
    """
    Récupère la version marquée 'Production' dans MLflow Registry.

    Retourne : tuple (version_name, stage) ou (None, None) en cas d'erreur.
    """
    try:
        url = f"{MLFLOW_TRACKING_URI}/api/2.0/mlflow/registered-models/get"
        params = {"name": MODEL_NAME}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()

        data = response.json()
        model_details = data.get("registered_model", {})
        latest_versions = model_details.get("latest_versions", [])

        production_version = None
        for v in latest_versions:
            if v.get("current_stage") == "Production":
                production_version = v.get("version")
                logger.info(
                    f"✓ MLflow: Version Production trouvée: {production_version}"
                )
                return production_version, "Production"

        logger.warning("⚠ MLflow: Aucune version en stage 'Production'")
        return None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"✗ MLflow API error: {e}")
        return None, None
    except Exception as e:
        logger.error(f"✗ Unexpected error fetching MLflow version: {e}")
        return None, None


def test_model_api(version=None):
    """
    Vérifie que l'API répond correctement.

    Appelle POST /v1/chat/completions avec une question test simple.
    Retourne True si réponse non vide, False sinon.
    """
    try:
        url = f"{API_URL}/v1/chat/completions"
        payload = {
            "messages": [{"role": "user", "content": "Dis OK"}],
            "model": "Assistant Intelligent",
            "temperature": 0.1,
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get("choices") and len(data["choices"]) > 0:
            content = data["choices"][0].get("message", {}).get("content", "").strip()
            if content:
                logger.info(f"✓ API: Réponse reçue ({len(content)} chars)")
                return True

        logger.warning("⚠ API: Réponse vide ou structure inattendue")
        return False

    except requests.exceptions.RequestException as e:
        logger.error(f"✗ API error: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error testing API: {e}")
        return False


def push_metric(healthy, version=None):
    """
    Pousse la métrique mlflow_production_model_healthy vers Pushgateway.

    healthy (bool) : True → métrique = 1, False → métrique = 0.
    """
    try:
        registry = CollectorRegistry()

        gauge = Gauge(
            "mlflow_production_model_healthy",
            "MLflow Production model health (1=OK, 0=KO)",
            registry=registry,
        )

        gauge.set(1 if healthy else 0)

        push_to_gateway(
            PUSHGATEWAY_URL,
            job="mlflow-healthcheck",
            registry=registry,
        )

        status = "✓ HEALTHY" if healthy else "✗ UNHEALTHY"
        logger.info(f"✓ Prometheus: Métrique pushée — {status}")

    except Exception as e:
        logger.error(f"✗ Error pushing metric to Pushgateway: {e}")


def main():
    """
    Flux principal :
    1. Récupérer version Production depuis MLflow Registry
    2. Tester l'API avec cette version
    3. Calculer état de santé (OK si MLflow OK et API répond)
    4. Pousser métrique vers Pushgateway
    """
    logger.info("─" * 60)
    logger.info(f"Capteur C5.2 — Démarrage ({datetime.now().isoformat()})")
    logger.info(f"MLflow: {MLFLOW_TRACKING_URI}")
    logger.info(f"API: {API_URL}")
    logger.info(f"Pushgateway: {PUSHGATEWAY_URL}")
    logger.info("─" * 60)

    # Step 1: Récupérer version Production
    version, stage = get_production_version()

    if version is None:
        logger.error("✗ Impossible de récupérer la version Production")
        push_metric(False)
        return False

    # Step 2: Tester l'API
    api_ok = test_model_api(version)

    # Step 3: État global
    healthy = api_ok

    # Step 4: Pousser métrique
    push_metric(healthy, version)

    result = "✓ OK" if healthy else "✗ FAILED"
    logger.info(f"Résultat: {result}")
    logger.info("─" * 60)

    return healthy


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

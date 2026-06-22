"""
DAG Airflow — Capteur C5.2 — Vérification de l'état du modèle MLflow en production.

Fréquence : Toutes les heures (0 * * * *).
Tâche : Appelle src/monitoring/mlflow_healthcheck.py.
Métrique : mlflow_production_model_healthy exposée vers Pushgateway.
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys

sys.path.insert(0, "/opt/airflow/src")

default_args = {
    "owner": "mlops-rag",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def mlflow_healthcheck_task():
    """Exécute le capteur C5.2."""
    from monitoring.mlflow_healthcheck import main

    return main()


with DAG(
    dag_id="mlflow_healthcheck",
    default_args=default_args,
    schedule_interval="0 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["monitoring", "mlflow"],
) as dag:

    check_task = PythonOperator(
        task_id="check_production_model",
        python_callable=mlflow_healthcheck_task,
    )

    check_task

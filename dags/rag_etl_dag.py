"""DAG Airflow — ETL RAG toutes les 15 minutes (placeholder)"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys

sys.path.insert(0, "/opt/airflow/src")

default_args = {
    "owner": "rag-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def etl_task():
    """Pipeline ETL : extract -> clean -> normalize -> chunk -> embed -> qdrant upsert."""
    # BLOQUANT: implémentation complète des modules ETL à finaliser
    print("ETL RAG run — placeholder")


with DAG(
    "rag_etl",
    default_args=default_args,
    schedule_interval="*/15 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["rag", "etl"],
) as dag:
    PythonOperator(task_id="run_etl", python_callable=etl_task)

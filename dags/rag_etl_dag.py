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


# ──────────────────────────────────────────────────────────────────────────
# DAGs temps quasi-réel : logs ES (Famille 2) + santé Prometheus (Famille 3)
# Indépendants du DAG rag_etl ci-dessus (qui tourne toutes les 15 min).
# ──────────────────────────────────────────────────────────────────────────


def _build_store_and_embedder():
    """Instancie QdrantVectorStore + Embedder depuis la config (env Airflow)."""
    from config.settings import get_settings
    from src.embeddings.embedder import Embedder
    from src.vector_store.qdrant_client import QdrantVectorStore

    s = get_settings()
    embedder = Embedder(model_name=s.embedding_model, batch_size=s.embedding_batch_size)
    store = QdrantVectorStore(
        host=s.qdrant_host, port=s.qdrant_port, collection=s.qdrant_collection
    )
    return store, embedder


def _log_mlflow(run_name: str, metric: str, value: int) -> None:
    """Logue une métrique dans MLflow — non bloquant si MLflow indisponible."""
    try:
        import mlflow
        from config.settings import get_settings

        mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
        with mlflow.start_run(run_name=run_name):
            mlflow.log_metric(metric, value)
    except Exception as e:  # pragma: no cover - MLflow optionnel
        print(f"mlflow skip ({run_name}): {e}")


def index_es_logs_task():
    """Extrait les events problématiques ES (ERROR/WARN) → Qdrant."""
    import asyncio

    from src.ingestion.extract_elasticsearch import index_logs_to_qdrant

    store, embedder = _build_store_and_embedder()
    n = asyncio.run(index_logs_to_qdrant(store, embedder))
    _log_mlflow("rag_logs_indexer", "logs_indexed", n)
    print(f"rag_logs_indexer — {n} logs indexés dans Qdrant")


def snapshot_prometheus_task():
    """Génère le snapshot santé système Prometheus → Qdrant (ID fixe)."""
    import asyncio

    from src.ingestion.extract_prometheus import index_health_to_qdrant

    store, embedder = _build_store_and_embedder()
    n = asyncio.run(index_health_to_qdrant(store, embedder))
    _log_mlflow("rag_prometheus_snapshot", "snapshot_indexed", n)
    print(f"rag_prometheus_snapshot — {n} snapshot santé indexé dans Qdrant")


with DAG(
    "rag_logs_indexer",
    default_args=default_args,
    schedule_interval="*/2 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["rag", "logs", "famille2"],
) as dag_logs:
    PythonOperator(task_id="index_es_logs", python_callable=index_es_logs_task)


with DAG(
    "rag_prometheus_snapshot",
    default_args=default_args,
    schedule_interval="* * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["rag", "metriques", "famille3"],
) as dag_prom:
    PythonOperator(
        task_id="snapshot_prometheus", python_callable=snapshot_prometheus_task
    )

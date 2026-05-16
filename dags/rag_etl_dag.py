"""DAG Airflow — pipeline RAG ETL toutes les 15 minutes.

Étapes : extract_pg >> extract_kafka >> merge >> clean >> build_docs >>
chunk >> embed >> upsert_qdrant >> log_mlflow.

Les tâches communiquent via XCom. La tâche finale logue un résumé dans MLflow.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

sys.path.insert(0, "/opt/airflow/src")
sys.path.insert(0, "/opt/airflow")

default_args = {
    "owner": "rag-team",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
}


def _settings():
    from config.settings import get_settings

    return get_settings()


def task_extract_pg(**ctx) -> dict:
    from src.ingestion.extract import extract_all

    result = asyncio.run(extract_all())
    counts = {k: len(v) for k, v in result.items()}
    ctx["ti"].xcom_push(key="pg_counts", value=counts)
    return result


def task_extract_kafka(**ctx) -> list[dict]:
    from src.ingestion.extract import extract_kafka

    s = _settings()
    msgs = extract_kafka(
        bootstrap_servers=s.kafka_bootstrap_servers,
        group_id=s.kafka_group_id,
        topics=os.getenv("KAFKA_TOPICS", "commandes,incidents,livraisons").split(","),
        max_messages=300,
        poll_timeout=1.0,
    )
    ctx["ti"].xcom_push(key="kafka_count", value=len(msgs))
    return msgs


def task_merge_and_clean(**ctx) -> dict:
    from src.ingestion.clean import clean

    pg = ctx["ti"].xcom_pull(task_ids="extract_pg")
    kafka = ctx["ti"].xcom_pull(task_ids="extract_kafka") or []
    merged = dict(pg or {})
    if kafka:
        merged["kafka_events"] = kafka
    return clean(merged)


def task_build_and_chunk(**ctx) -> tuple[list[str], list[str], list[dict]]:
    from src.ingestion.document_builder import build_documents
    from src.ingestion.chunk import chunk_documents

    s = _settings()
    cleaned = ctx["ti"].xcom_pull(task_ids="merge_and_clean")
    ids, texts, metas = build_documents(cleaned)
    return chunk_documents(
        ids, texts, metas, chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap
    )


def task_embed_and_upsert(**ctx) -> dict:
    from src.embeddings.embedder import Embedder
    from src.vector_store.qdrant_client import QdrantVectorStore

    s = _settings()
    ids, texts, metas = ctx["ti"].xcom_pull(task_ids="build_and_chunk")
    if not ids:
        return {"upserted": 0, "duration_s": 0.0}
    t0 = time.time()
    embedder = Embedder(model_name=s.embedding_model, batch_size=s.embedding_batch_size)
    store = QdrantVectorStore(
        host=s.qdrant_host, port=s.qdrant_port, collection=s.qdrant_collection
    )
    vectors = embedder.embed(texts)
    n = store.upsert(ids, vectors, texts, metas)
    return {"upserted": n, "duration_s": time.time() - t0, "docs": len(ids)}


def task_log_mlflow(**ctx) -> None:
    try:
        import mlflow
    except ImportError:
        return
    s = _settings()
    mlflow.set_tracking_uri(s.mlflow_tracking_uri)
    mlflow.set_experiment(s.mlflow_experiment)
    pg_counts = ctx["ti"].xcom_pull(task_ids="extract_pg", key="pg_counts") or {}
    kafka_count = ctx["ti"].xcom_pull(task_ids="extract_kafka", key="kafka_count") or 0
    upsert = ctx["ti"].xcom_pull(task_ids="embed_and_upsert") or {}
    with mlflow.start_run(run_name=f"rag_etl_{datetime.utcnow().isoformat()}"):
        mlflow.set_tags({"component": "rag_etl_dag", "sprint": "sprint6"})
        for k, v in pg_counts.items():
            mlflow.log_metric(f"pg_{k}", v)
        mlflow.log_metric("kafka_events", kafka_count)
        mlflow.log_metric("upserted", upsert.get("upserted", 0))
        mlflow.log_metric("docs", upsert.get("docs", 0))
        mlflow.log_metric("upsert_duration_s", upsert.get("duration_s", 0.0))


with DAG(
    dag_id="rag_etl",
    default_args=default_args,
    description="ETL RAG : Postgres + Kafka → clean → build → chunk → embed → Qdrant",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["rag", "etl", "sprint6"],
) as dag:
    extract_pg = PythonOperator(task_id="extract_pg", python_callable=task_extract_pg)
    extract_kafka = PythonOperator(
        task_id="extract_kafka", python_callable=task_extract_kafka
    )
    merge_and_clean = PythonOperator(
        task_id="merge_and_clean", python_callable=task_merge_and_clean
    )
    build_and_chunk = PythonOperator(
        task_id="build_and_chunk", python_callable=task_build_and_chunk
    )
    embed_and_upsert = PythonOperator(
        task_id="embed_and_upsert", python_callable=task_embed_and_upsert
    )
    log_mlflow = PythonOperator(
        task_id="log_mlflow", python_callable=task_log_mlflow, trigger_rule="all_done"
    )

    (
        [extract_pg, extract_kafka]
        >> merge_and_clean
        >> build_and_chunk
        >> embed_and_upsert
        >> log_mlflow
    )

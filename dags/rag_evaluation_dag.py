"""DAG Airflow — Évaluation RAGAS quotidienne + promotion auto du modèle."""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import asyncio
import sys

sys.path.insert(0, "/opt/airflow/src")
sys.path.insert(0, "/opt/airflow")

default_args = {
    "owner": "rag-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def evaluate_task():
    async def run():
        from config.settings import get_settings
        from rag.rag_pipeline import RAGPipeline
        from evaluation.ragas_evaluator import RAGASEvaluator
        from evaluation.test_questions import EVAL_QUESTIONS
        import mlflow

        s = get_settings()
        mlflow.set_tracking_uri(s.mlflow_tracking_uri)
        mlflow.set_experiment("rag-evaluation-daily")
        pipeline = RAGPipeline(s)
        evaluator = RAGASEvaluator(pipeline, s.mlflow_experiment)
        scores = await evaluator.evaluate_and_log(
            EVAL_QUESTIONS, run_name=f"daily_{datetime.now().strftime('%Y%m%d')}"
        )
        if scores["faithfulness"] < 0.7:
            raise ValueError(f"Faithfulness trop basse: {scores['faithfulness']:.2f}")

    asyncio.run(run())


def promote_task():
    """Promotion conditionnelle Staging → Production basée sur le dernier run RAGAS."""
    from scripts.promote_model import main as promote_main

    tracking_uri = "http://localhost:5000"
    try:
        from config.settings import get_settings

        tracking_uri = get_settings().mlflow_tracking_uri
    except Exception:
        pass

    rc = promote_main(tracking_uri)
    if rc != 0:
        raise RuntimeError(f"promote_model.py a échoué (rc={rc})")

    import os
    import httpx

    api_url = os.getenv("RAG_API_URL", "http://api:8080")
    try:
        r = httpx.post(f"{api_url}/admin/reload-model-version", timeout=10)
        r.raise_for_status()
        print(f"[promote] API rechargée: {r.json()}")
    except Exception as e:
        print(f"[promote] WARN: reload API échoué ({e}) — redémarrage manuel requis")


with DAG(
    "rag_evaluation_daily",
    default_args=default_args,
    schedule_interval="0 2 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["rag", "ragas", "evaluation"],
) as dag:
    eval_op = PythonOperator(
        task_id="run_ragas_evaluation", python_callable=evaluate_task
    )
    promote_op = PythonOperator(
        task_id="promote_model_if_passed", python_callable=promote_task
    )
    eval_op >> promote_op

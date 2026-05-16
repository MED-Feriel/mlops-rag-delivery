"""DAG Airflow — Évaluation RAGAS quotidienne à 2h du matin"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import asyncio
import sys

sys.path.insert(0, "/opt/airflow/src")

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


with DAG(
    "rag_evaluation_daily",
    default_args=default_args,
    schedule_interval="0 2 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["rag", "ragas", "evaluation"],
) as dag:
    PythonOperator(task_id="run_ragas_evaluation", python_callable=evaluate_task)

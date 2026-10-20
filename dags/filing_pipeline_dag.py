"""
Airflow DAG: daily SEC EDGAR restatement pipeline.

    ingest_edgar -> check_contracts -> run_expectations -> dbt_build -> score_alerts

The DAG only orchestrates. Every task runs the same command you can run by
hand (`python -m ...`, `dbt build`), so a failed task is debugged by running
its command locally, not by reading Airflow internals.

Order matters: quality gates run on bronze BEFORE dbt, so bad raw data
stops the run before it reaches the gold tables people read.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = PROJECT_ROOT / "dbt_project"
PY = "python"  # the Airflow image's interpreter, with requirements.txt installed

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=1),
}

with DAG(
    dag_id="sec_restatement_pipeline",
    description="EDGAR -> bronze -> quality gates -> dbt (silver/gold) -> scored alerts",
    default_args=DEFAULT_ARGS,
    schedule="0 6 * * 1-5",  # 06:00 on weekdays (EDGAR publishes overnight)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,  # two runs writing one DuckDB file would collide
    tags=["sec", "restatements", "dbt"],
) as dag:
    ingest = BashOperator(
        task_id="ingest_edgar",
        bash_command=f"cd {PROJECT_ROOT} && {PY} -m ingestion.pipeline",
        retries=3,  # network calls: retry more than the rest
        retry_delay=timedelta(minutes=5),
    )

    contracts = BashOperator(
        task_id="check_contracts",
        bash_command=f"cd {PROJECT_ROOT} && {PY} -m quality.check_contracts",
        retries=0,  # a failed quality gate won't fix itself on retry
    )

    expectations = BashOperator(
        task_id="run_expectations",
        bash_command=f"cd {PROJECT_ROOT} && {PY} -m quality.run_expectations",
        retries=0,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {DBT_DIR} && dbt deps --profiles-dir . && dbt build --profiles-dir .",
    )

    score = BashOperator(
        task_id="score_alerts",
        bash_command=f"cd {PROJECT_ROOT} && {PY} -m detection.run",
    )

    ingest >> contracts >> expectations >> dbt_build >> score

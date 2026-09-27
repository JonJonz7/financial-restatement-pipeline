"""
Financial Restatement & Anomaly Detection Pipeline — Airflow DAG
================================================================
Orchestrates the full pipeline: EDGAR ingestion -> dbt medallion transforms
-> data quality gates -> restatement detection -> anomaly scoring -> alerts.

Schedule: Daily at 06:00 ET
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt_project"
GE_DIR = PROJECT_ROOT / "quality" / "great_expectations"

# ---------------------------------------------------------------------------
# Default args
# ---------------------------------------------------------------------------
DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": ["data-alerts@company.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}

# ---------------------------------------------------------------------------
# Python callables
# ---------------------------------------------------------------------------


def _ingest_edgar_filings(**context) -> dict:
    """Pull latest EDGAR filings and load into bronze layer."""
    from ingestion.pipeline import run_ingestion

    execution_date = context["ds"]
    logger.info("Starting EDGAR ingestion for %s", execution_date)

    result = run_ingestion(
        execution_date=execution_date,
        mode="incremental",
    )

    logger.info(
        "Ingestion complete — %d filings processed, %d new facts loaded",
        result.get("filings_processed", 0),
        result.get("facts_loaded", 0),
    )
    return result


def _run_great_expectations(**context) -> dict:
    """Execute Great Expectations checkpoint against the warehouse."""
    import great_expectations as gx

    ge_context = gx.get_context(context_root_dir=str(GE_DIR))
    checkpoint_result = ge_context.run_checkpoint(
        checkpoint_name="filing_checkpoint"
    )

    if not checkpoint_result["success"]:
        failing_validations = [
            v
            for v in checkpoint_result.get("run_results", {}).values()
            if not v.get("validation_result", {}).get("success", True)
        ]
        logger.error(
            "Great Expectations checkpoint FAILED — %d validation(s) unsuccessful",
            len(failing_validations),
        )
        raise ValueError(
            f"Data quality gate failed: {len(failing_validations)} "
            "validation(s) did not pass."
        )

    logger.info("Great Expectations checkpoint PASSED")
    return {"ge_success": True}


def _detect_restatements(**context) -> dict:
    """Identify potential restatements via period-over-period comparison."""
    from detection.restatement_detector import detect_restatements

    execution_date = context["ds"]
    logger.info("Running restatement detection for %s", execution_date)

    result = detect_restatements(execution_date=execution_date)

    logger.info(
        "Detection complete — %d potential restatements flagged",
        result.get("restatements_found", 0),
    )

    # Push to XCom for downstream consumption
    context["ti"].xcom_push(key="restatement_count", value=result.get("restatements_found", 0))
    return result


def _score_anomalies(**context) -> dict:
    """Score financial metrics for statistical anomalies."""
    from detection.anomaly_scorer import score_anomalies

    execution_date = context["ds"]
    restatement_count = context["ti"].xcom_pull(
        task_ids="detection.detect_restatements", key="restatement_count"
    )

    logger.info(
        "Scoring anomalies for %s (restatements upstream: %s)",
        execution_date,
        restatement_count,
    )

    result = score_anomalies(execution_date=execution_date)

    logger.info(
        "Scoring complete — %d anomalies above threshold",
        result.get("anomalies_scored", 0),
    )

    context["ti"].xcom_push(key="anomaly_count", value=result.get("anomalies_scored", 0))
    return result


def _generate_alerts(**context) -> dict:
    """Generate and dispatch alerts for high-severity anomalies."""
    from detection.anomaly_scorer import generate_alerts

    execution_date = context["ds"]
    anomaly_count = context["ti"].xcom_pull(
        task_ids="detection.score_anomalies", key="anomaly_count"
    )

    if anomaly_count == 0:
        logger.info("No anomalies to alert on — skipping.")
        return {"alerts_sent": 0}

    logger.info(
        "Generating alerts for %s (%s anomalies)", execution_date, anomaly_count
    )

    result = generate_alerts(execution_date=execution_date)

    logger.info("Alerts dispatched — %d sent", result.get("alerts_sent", 0))
    return result


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="financial_restatement_pipeline",
    description=(
        "End-to-end financial restatement detection: EDGAR ingestion, "
        "dbt medallion transforms, data quality validation, anomaly scoring."
    ),
    default_args=DEFAULT_ARGS,
    schedule_interval="0 6 * * *",  # 06:00 ET (Airflow TZ set to America/New_York)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["financial", "restatement", "data-quality"],
    doc_md=__doc__,
) as dag:

    # -------------------------------------------------------------------
    # Task Group: Ingestion
    # -------------------------------------------------------------------
    with TaskGroup(group_id="ingestion") as ingestion_group:
        ingest_edgar = PythonOperator(
            task_id="ingest_edgar_filings",
            python_callable=_ingest_edgar_filings,
            provide_context=True,
        )

    # -------------------------------------------------------------------
    # Task Group: Transformation (dbt medallion layers)
    # -------------------------------------------------------------------
    with TaskGroup(group_id="transformation") as transformation_group:
        dbt_common = {
            "env": {
                "DBT_PROJECT_DIR": str(DBT_PROJECT_DIR),
                "DBT_PROFILES_DIR": str(DBT_PROJECT_DIR),
            },
        }

        run_dbt_staging = BashOperator(
            task_id="run_dbt_staging",
            bash_command=(
                f"cd {DBT_PROJECT_DIR} && dbt run --select staging "
                "--profiles-dir . --project-dir ."
            ),
            **dbt_common,
        )

        run_dbt_intermediate = BashOperator(
            task_id="run_dbt_intermediate",
            bash_command=(
                f"cd {DBT_PROJECT_DIR} && dbt run --select intermediate "
                "--profiles-dir . --project-dir ."
            ),
            **dbt_common,
        )

        run_dbt_marts = BashOperator(
            task_id="run_dbt_marts",
            bash_command=(
                f"cd {DBT_PROJECT_DIR} && dbt run --select marts "
                "--profiles-dir . --project-dir ."
            ),
            **dbt_common,
        )

        run_dbt_tests = BashOperator(
            task_id="run_dbt_tests",
            bash_command=(
                f"cd {DBT_PROJECT_DIR} && dbt test "
                "--profiles-dir . --project-dir ."
            ),
            **dbt_common,
        )

        # Linear chain within transformation
        run_dbt_staging >> run_dbt_intermediate >> run_dbt_marts >> run_dbt_tests

    # -------------------------------------------------------------------
    # Task Group: Quality Gate
    # -------------------------------------------------------------------
    with TaskGroup(group_id="quality") as quality_group:
        run_ge = PythonOperator(
            task_id="run_great_expectations",
            python_callable=_run_great_expectations,
            provide_context=True,
        )

    # -------------------------------------------------------------------
    # Task Group: Detection & Alerting
    # -------------------------------------------------------------------
    with TaskGroup(group_id="detection") as detection_group:
        detect = PythonOperator(
            task_id="detect_restatements",
            python_callable=_detect_restatements,
            provide_context=True,
        )

        score = PythonOperator(
            task_id="score_anomalies",
            python_callable=_score_anomalies,
            provide_context=True,
        )

        alerts = PythonOperator(
            task_id="generate_alerts",
            python_callable=_generate_alerts,
            provide_context=True,
            trigger_rule=TriggerRule.ALL_SUCCESS,
        )

        detect >> score >> alerts

    # -------------------------------------------------------------------
    # DAG-level dependencies (linear chain with quality gate)
    # -------------------------------------------------------------------
    ingestion_group >> transformation_group >> quality_group >> detection_group

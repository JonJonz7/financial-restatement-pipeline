"""
Integration test: sample data -> bronze -> dbt build -> gold -> alerts.

Runs the real dbt project against a temporary DuckDB file and checks that
every planted case in data/sample/ is detected and nothing else is.
"""

import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

from detection.anomaly_scorer import write_alerts
from ingestion.demo import load_sample

ROOT = Path(__file__).resolve().parent.parent
DBT = shutil.which("dbt") or str(Path(os.sys.executable).parent / "dbt")


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory) -> str:
    db = str(tmp_path_factory.mktemp("e2e") / "e2e.duckdb")
    load_sample(db)
    env = {**os.environ, "WAREHOUSE_DB_PATH": db}
    subprocess.run(
        [DBT, "deps", "--profiles-dir", ".", "--project-dir", "."],
        cwd=ROOT / "dbt_project",
        env=env,
        check=True,
        capture_output=True,
    )
    run = subprocess.run(
        [DBT, "build", "--profiles-dir", ".", "--project-dir", "."],
        cwd=ROOT / "dbt_project",
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout[-3000:]
    return db


def rows(db, sql):
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_amendment_detected_as_material(warehouse):
    got = rows(
        warehouse,
        """
        select metric, restatement_type, severity, round(pct_change, 1)
        from gold.fct_restatements where cik = '0000900001' order by metric""",
    )
    assert got == [
        ("NetIncomeLoss", "AMENDMENT", "MATERIAL", -6.0),
        ("Revenues", "AMENDMENT", "MATERIAL", -6.0),
    ]


def test_recast_detected(warehouse):
    got = rows(
        warehouse,
        """
        select metric, restatement_type, severity from gold.fct_restatements
        where cik = '0000900002' order by metric""",
    )
    assert got == [
        ("NetIncomeLoss", "RECAST", "NOTABLE"),
        ("OperatingIncomeLoss", "RECAST", "NOTABLE"),
        ("Revenues", "RECAST", "MATERIAL"),
    ]


def test_no_false_restatements(warehouse):
    """Comparatives repeated with the same value, and Q4 vs FY sharing an end date,
    must not be flagged: 5 planted restatements, exactly 5 found."""
    assert rows(warehouse, "select count(*) from gold.fct_restatements") == [(5,)]


def test_other_anomaly_types(warehouse):
    got = rows(
        warehouse,
        """
        select anomaly_type, cik, cast(period_end as varchar) from gold.fct_anomalies
        where anomaly_type <> 'RESTATEMENT' order by anomaly_type""",
    )
    assert got == [
        ("BALANCE_SHEET_BREAK", "0000900002", "2023-12-31"),
        ("SCALE_ERROR", "0000900003", "2022-09-30"),
        ("VALUATION_OUTLIER", "0000900003", "2022-09-30"),
    ]


def test_q4_is_derived_when_untagged(warehouse):
    got = rows(
        warehouse,
        """
        select count(*) filter (where is_derived), count(*) from silver.int_quarterly_revenue
        where cik = '0000900002'""",
    )
    assert got == [(3, 12)]


def test_alerts_written_and_ranked(warehouse, tmp_path):
    alerts = write_alerts(warehouse, tmp_path / "alerts.md")
    assert len(alerts) == 8
    assert alerts.iloc[0]["anomaly_type"] == "SCALE_ERROR"
    assert "| Priority |" in (tmp_path / "alerts.md").read_text()


def test_lineage_recorded(warehouse):
    assert rows(
        warehouse,
        """
        select count(*), count(distinct sha256) from bronze.ingestion_runs
        where status = 'ok'""",
    ) == [(6, 6)]

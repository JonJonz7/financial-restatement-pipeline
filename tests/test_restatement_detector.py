"""
Tests for detection/restatement_detector.py.

Uses real DuckDB in-memory databases with synthetic test data.
"""

import duckdb
import pandas as pd
import pytest

from detection.restatement_detector import detect_restatements


def _create_populated_db(tmp_path, rows: list[tuple]) -> str:
    """Helper: create a DuckDB file with bronze schema and insert rows.

    Each row tuple: (cik, metric, period_start, period_end, value, unit,
                     form, filed_date, accession_number, fiscal_year,
                     fiscal_period)
    """
    db_path = str(tmp_path / "test_detect.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    con.execute("""
        CREATE TABLE IF NOT EXISTS bronze.raw_financial_facts (
            cik              VARCHAR NOT NULL,
            metric           VARCHAR NOT NULL,
            period_start     DATE,
            period_end       DATE,
            value            DOUBLE,
            unit             VARCHAR,
            form             VARCHAR,
            filed_date       DATE,
            accession_number VARCHAR,
            fiscal_year      INTEGER,
            fiscal_period    VARCHAR,
            ingested_at      TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (cik, metric, period_end, filed_date, accession_number)
        )
    """)
    for row in rows:
        con.execute(
            """
            INSERT INTO bronze.raw_financial_facts
                (cik, metric, period_start, period_end, value, unit,
                 form, filed_date, accession_number, fiscal_year, fiscal_period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            list(row),
        )
    con.close()
    return db_path


# ---------------------------------------------------------------------------
# Core detection tests
# ---------------------------------------------------------------------------


def test_detect_restatements_finds_value_changes(tmp_path):
    """Two filings for the same (cik, metric, period_end) with different
    values should be detected as a restatement."""
    rows = [
        # Original filing
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         383285000000, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        # Restated filing (different value, later filed_date)
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         390000000000, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 1
    assert df.iloc[0]["cik"] == "0000320193"
    assert df.iloc[0]["metric"] == "Revenues"
    assert df.iloc[0]["original_value"] == 383285000000
    assert df.iloc[0]["restated_value"] == 390000000000


def test_detect_restatements_ignores_identical_values(tmp_path):
    """Same metric/period filed multiple times with the same value
    should NOT be flagged as a restatement."""
    rows = [
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         383285000000, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         383285000000, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 0


# ---------------------------------------------------------------------------
# Severity classification tests
# ---------------------------------------------------------------------------


def test_severity_classification_material(tmp_path):
    """pct_change > 5% should be classified as MATERIAL."""
    original = 100_000_000
    restated = 110_000_000  # 10% change
    rows = [
        ("0000320193", "Assets", None, "2023-09-30",
         original, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        ("0000320193", "Assets", None, "2023-09-30",
         restated, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 1
    assert df.iloc[0]["severity"] == "MATERIAL"
    assert df.iloc[0]["pct_change"] == pytest.approx(10.0)


def test_severity_classification_notable(tmp_path):
    """pct_change between 1% and 5% should be classified as NOTABLE.
    Absolute change must stay under 1M to avoid triggering MATERIAL."""
    original = 10_000
    restated = 10_300  # 3% change, absolute_change = 300
    rows = [
        ("0000320193", "Assets", None, "2023-09-30",
         original, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        ("0000320193", "Assets", None, "2023-09-30",
         restated, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 1
    assert df.iloc[0]["severity"] == "NOTABLE"
    assert 1 < df.iloc[0]["pct_change"] <= 5


def test_severity_classification_minor(tmp_path):
    """pct_change < 1% should be classified as MINOR.
    Absolute change must stay under 1M to avoid triggering MATERIAL."""
    original = 100_000
    restated = 100_500  # 0.5% change, absolute_change = 500
    rows = [
        ("0000320193", "Assets", None, "2023-09-30",
         original, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        ("0000320193", "Assets", None, "2023-09-30",
         restated, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 1
    assert df.iloc[0]["severity"] == "MINOR"
    assert df.iloc[0]["pct_change"] < 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_database_returns_empty_dataframe(tmp_path):
    """An empty warehouse should return an empty DataFrame, not error."""
    db_path = _create_populated_db(tmp_path, [])
    df = detect_restatements(db_path)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_multiple_restatements_detected(tmp_path):
    """Detector should find restatements across multiple companies/metrics."""
    rows = [
        # Company A, Revenues — restated
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         383285000000, "USD", "10-K", "2023-11-03", "acc-001", 2023, "FY"),
        ("0000320193", "Revenues", "2022-10-01", "2023-09-30",
         390000000000, "USD", "10-K/A", "2024-02-15", "acc-002", 2023, "FY"),
        # Company B, Assets — restated
        ("0000789019", "Assets", None, "2023-06-30",
         411976000000, "USD", "10-K", "2023-07-25", "acc-003", 2023, "FY"),
        ("0000789019", "Assets", None, "2023-06-30",
         415000000000, "USD", "10-K/A", "2023-12-01", "acc-004", 2023, "FY"),
        # Company A, Assets — NOT restated (same value)
        ("0000320193", "Assets", None, "2023-09-30",
         352583000000, "USD", "10-K", "2023-11-03", "acc-005", 2023, "FY"),
        ("0000320193", "Assets", None, "2023-09-30",
         352583000000, "USD", "10-K/A", "2024-02-15", "acc-006", 2023, "FY"),
    ]
    db_path = _create_populated_db(tmp_path, rows)
    df = detect_restatements(db_path)

    assert len(df) == 2
    ciks = set(df["cik"].tolist())
    assert "0000320193" in ciks
    assert "0000789019" in ciks

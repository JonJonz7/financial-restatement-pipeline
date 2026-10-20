"""
Read detection results from the gold layer.

Detection itself is SQL in dbt (models/intermediate + models/marts), where it
is versioned, tested and documented with the rest of the warehouse. This
module is the Python access point used by the scorer, the Airflow DAG and
the dashboard, so nothing else needs to know table names.
"""

import logging

import duckdb
import pandas as pd

from detection.thresholds import classify_severity  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


def _read(db_path: str, sql: str) -> pd.DataFrame:
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(sql).fetchdf()
    except duckdb.CatalogException:
        logger.warning("Gold tables missing: run `make transform` (dbt) first")
        return pd.DataFrame()
    finally:
        con.close()


def detect_restatements(db_path: str = "warehouse.duckdb") -> pd.DataFrame:
    """All restatements found by dbt, newest first."""
    df = _read(
        db_path,
        """
        select r.*, c.ticker, c.company_name
        from gold.fct_restatements r
        left join gold.dim_companies c using (cik)
        order by restatement_filed_date desc, abs(absolute_change) desc
    """,
    )
    logger.info("%d restatements in gold.fct_restatements", len(df))
    return df


def detect_cross_source_anomalies(db_path: str = "warehouse.duckdb") -> pd.DataFrame:
    """Non-restatement anomalies: balance-sheet breaks, scale errors, valuation outliers."""
    return _read(
        db_path,
        """
        select a.*, c.ticker, c.company_name
        from gold.fct_anomalies a
        left join gold.dim_companies c using (cik)
        where anomaly_type <> 'RESTATEMENT'
        order by detected_date desc
    """,
    )


def all_anomalies(db_path: str = "warehouse.duckdb") -> pd.DataFrame:
    return _read(
        db_path,
        """
        select a.*, c.ticker, c.company_name
        from gold.fct_anomalies a
        left join gold.dim_companies c using (cik)
    """,
    )

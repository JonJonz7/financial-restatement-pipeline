"""
DuckDB warehouse loader.

Creates the bronze/silver/gold schema layout and provides upsert
functions for raw filings, financial facts, and market data.
"""

import logging
from datetime import datetime, timezone

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema / table DDL
# ---------------------------------------------------------------------------

_INIT_SQL = """
-- Medallion schemas
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Raw SEC filings metadata
CREATE TABLE IF NOT EXISTS bronze.raw_filings (
    cik              VARCHAR NOT NULL,
    accession_number VARCHAR NOT NULL,
    form_type        VARCHAR,
    filing_date      DATE,
    period_of_report DATE,
    primary_document VARCHAR,
    ingested_at      TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (cik, accession_number)
);

-- Raw XBRL financial facts
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
);

-- Raw market data (OHLCV + market cap)
CREATE TABLE IF NOT EXISTS bronze.raw_market_data (
    ticker     VARCHAR NOT NULL,
    date       DATE    NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    volume     BIGINT,
    market_cap DOUBLE,
    ingested_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (ticker, date)
);
"""


def init_warehouse(db_path: str = "warehouse.duckdb") -> None:
    """Create bronze/silver/gold schemas and base tables if they don't exist.

    Args:
        db_path: Path to the DuckDB database file.
    """
    logger.info("Initialising warehouse at %s", db_path)
    con = duckdb.connect(db_path)
    try:
        con.execute(_INIT_SQL)
        logger.info("Warehouse schemas and tables ready")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Loaders (upsert semantics via INSERT OR REPLACE)
# ---------------------------------------------------------------------------


def load_raw_filings(records: list[dict], db_path: str = "warehouse.duckdb") -> None:
    """Upsert filing metadata into ``bronze.raw_filings``.

    Args:
        records: List of dicts with keys matching the table columns.
        db_path: Path to the DuckDB database file.
    """
    if not records:
        logger.warning("No filing records to load")
        return

    logger.info("Loading %d filing records into bronze.raw_filings", len(records))
    now = datetime.now(timezone.utc).isoformat()
    con = duckdb.connect(db_path)
    try:
        for rec in records:
            con.execute(
                """
                INSERT OR REPLACE INTO bronze.raw_filings
                    (cik, accession_number, form_type, filing_date,
                     period_of_report, primary_document, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    rec.get("cik"),
                    rec.get("accession_number"),
                    rec.get("form_type"),
                    rec.get("filing_date"),
                    rec.get("period_of_report"),
                    rec.get("primary_document"),
                    now,
                ],
            )
        logger.info("Loaded %d filing records", len(records))
    finally:
        con.close()


def load_raw_financial_facts(
    records: list[dict], db_path: str = "warehouse.duckdb"
) -> None:
    """Upsert XBRL financial facts into ``bronze.raw_financial_facts``.

    Args:
        records: List of dicts as produced by
                 :func:`edgar_client.extract_financial_metrics`.
        db_path: Path to the DuckDB database file.
    """
    if not records:
        logger.warning("No financial-fact records to load")
        return

    logger.info(
        "Loading %d financial-fact records into bronze.raw_financial_facts",
        len(records),
    )
    now = datetime.now(timezone.utc).isoformat()

    # Batch via DataFrame for performance on large fact sets.
    df = pd.DataFrame(records)
    df["ingested_at"] = now

    # Ensure correct column order and fill missing columns with None.
    columns = [
        "cik", "metric", "period_start", "period_end", "value", "unit",
        "form", "filed_date", "accession_number", "fiscal_year",
        "fiscal_period", "ingested_at",
    ]
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[columns]

    con = duckdb.connect(db_path)
    try:
        # Drop rows where composite key fields are null (can't upsert).
        df = df.dropna(subset=["cik", "metric", "period_end", "filed_date", "accession_number"])

        if df.empty:
            logger.warning("All records dropped due to null key fields")
            return

        # Use INSERT OR REPLACE via a temp table for batch upsert.
        con.execute("CREATE OR REPLACE TEMP TABLE _staging_facts AS SELECT * FROM df")
        con.execute(
            """
            INSERT OR REPLACE INTO bronze.raw_financial_facts
            SELECT * FROM _staging_facts
            """
        )
        con.execute("DROP TABLE IF EXISTS _staging_facts")
        logger.info("Loaded %d financial-fact records", len(df))
    finally:
        con.close()


def load_market_data(
    df: pd.DataFrame, db_path: str = "warehouse.duckdb"
) -> None:
    """Upsert market data into ``bronze.raw_market_data``.

    Args:
        df: DataFrame with columns matching the table schema.
        db_path: Path to the DuckDB database file.
    """
    if df is None or df.empty:
        logger.warning("No market data to load")
        return

    logger.info("Loading %d market-data rows into bronze.raw_market_data", len(df))
    now = datetime.now(timezone.utc).isoformat()

    df = df.copy()
    df["ingested_at"] = now

    # Normalise column names.
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Ensure date column is date-only (strip timezone if present).
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date

    columns = [
        "ticker", "date", "open", "high", "low", "close",
        "volume", "market_cap", "ingested_at",
    ]
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[columns]

    df = df.dropna(subset=["ticker", "date"])

    if df.empty:
        logger.warning("All market-data rows dropped due to null keys")
        return

    con = duckdb.connect(db_path)
    try:
        con.execute("CREATE OR REPLACE TEMP TABLE _staging_market AS SELECT * FROM df")
        con.execute(
            """
            INSERT OR REPLACE INTO bronze.raw_market_data
            SELECT * FROM _staging_market
            """
        )
        con.execute("DROP TABLE IF EXISTS _staging_market")
        logger.info("Loaded %d market-data rows", len(df))
    finally:
        con.close()

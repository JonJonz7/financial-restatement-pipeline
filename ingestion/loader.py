"""
DuckDB warehouse loader.

Creates the bronze/silver/gold schema layout and upserts raw rows into bronze.
Every loader is idempotent: loading the same rows twice leaves one copy,
because each table has a primary key built from the row's real identity.
"""

import hashlib
import logging
from datetime import datetime, timezone

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

_INIT_SQL = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS bronze.raw_companies (
    cik              VARCHAR PRIMARY KEY,
    company_name     VARCHAR,
    ticker           VARCHAR,
    sic              VARCHAR,
    sic_description  VARCHAR,
    fiscal_year_end  VARCHAR,
    ingested_at      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bronze.raw_filings (
    cik              VARCHAR NOT NULL,
    accession_number VARCHAR NOT NULL,
    form_type        VARCHAR,
    filing_date      DATE,
    period_of_report DATE,
    primary_document VARCHAR,
    ingested_at      TIMESTAMP,
    PRIMARY KEY (cik, accession_number)
);

-- One row per XBRL fact as reported in one filing. fact_key hashes the
-- full identity: cik, taxonomy, metric, unit, period_start, period_end and
-- accession number. period_start is NULL for instant facts (balance sheet).
CREATE TABLE IF NOT EXISTS bronze.raw_financial_facts (
    fact_key         VARCHAR PRIMARY KEY,
    cik              VARCHAR NOT NULL,
    taxonomy         VARCHAR NOT NULL,
    metric           VARCHAR NOT NULL,
    unit             VARCHAR NOT NULL,
    period_start     DATE,
    period_end       DATE NOT NULL,
    value            DOUBLE,
    form             VARCHAR,
    filed_date       DATE NOT NULL,
    accession_number VARCHAR NOT NULL,
    fiscal_year      INTEGER,
    fiscal_period    VARCHAR,
    frame            VARCHAR,
    ingested_at      TIMESTAMP
);

-- Daily prices only. Historical market cap is NOT stored here: it is derived
-- in dbt as close price x shares outstanding reported to the SEC.
CREATE TABLE IF NOT EXISTS bronze.raw_market_data (
    ticker      VARCHAR NOT NULL,
    date        DATE    NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    ingested_at TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

-- Lineage: one row per source document loaded.
CREATE TABLE IF NOT EXISTS bronze.ingestion_runs (
    run_id       VARCHAR NOT NULL,
    source       VARCHAR NOT NULL,
    cik          VARCHAR,
    landed_path  VARCHAR,
    sha256       VARCHAR,
    rows_loaded  INTEGER,
    status       VARCHAR NOT NULL,
    error        VARCHAR,
    started_at   TIMESTAMP,
    finished_at  TIMESTAMP
);
"""

FACT_COLUMNS = [
    "fact_key",
    "cik",
    "taxonomy",
    "metric",
    "unit",
    "period_start",
    "period_end",
    "value",
    "form",
    "filed_date",
    "accession_number",
    "fiscal_year",
    "fiscal_period",
    "frame",
    "ingested_at",
]
_FACT_IDENTITY = [
    "cik",
    "taxonomy",
    "metric",
    "unit",
    "period_start",
    "period_end",
    "accession_number",
]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fact_key(row: dict) -> str:
    """Deterministic key for one fact-in-one-filing (same inputs, same key)."""
    parts = ["" if row.get(c) is None else str(row.get(c)) for c in _FACT_IDENTITY]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def connect(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path)


def init_warehouse(db_path: str = "warehouse.duckdb") -> None:
    """Create bronze/silver/gold schemas and bronze tables if they don't exist."""
    logger.info("Initialising warehouse at %s", db_path)
    con = connect(db_path)
    try:
        con.execute(_INIT_SQL)
    finally:
        con.close()


def _upsert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    con.register("_incoming", df)
    try:
        cols = ", ".join(df.columns)
        con.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) SELECT {cols} FROM _incoming"
        )
    finally:
        con.unregister("_incoming")
    return len(df)


def load_companies(records: list[dict], db_path: str = "warehouse.duckdb") -> int:
    """Upsert company profiles into bronze.raw_companies."""
    if not records:
        return 0
    df = pd.DataFrame(records)[
        ["cik", "company_name", "ticker", "sic", "sic_description", "fiscal_year_end"]
    ]
    df["ingested_at"] = _now()
    con = connect(db_path)
    try:
        return _upsert(con, "bronze.raw_companies", df)
    finally:
        con.close()


def load_raw_filings(records: list[dict], db_path: str = "warehouse.duckdb") -> int:
    """Upsert filing metadata into bronze.raw_filings."""
    if not records:
        logger.warning("No filing records to load")
        return 0
    df = pd.DataFrame(records)
    for col in [
        "cik",
        "accession_number",
        "form_type",
        "filing_date",
        "period_of_report",
        "primary_document",
    ]:
        if col not in df.columns:
            df[col] = None
    df = df.dropna(subset=["cik", "accession_number"]).drop_duplicates(
        subset=["cik", "accession_number"]
    )
    for col in ("filing_date", "period_of_report"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    df = df[
        [
            "cik",
            "accession_number",
            "form_type",
            "filing_date",
            "period_of_report",
            "primary_document",
        ]
    ].copy()
    df["ingested_at"] = _now()
    con = connect(db_path)
    try:
        n = _upsert(con, "bronze.raw_filings", df)
        logger.info("Loaded %d filing records", n)
        return n
    finally:
        con.close()


def load_raw_financial_facts(
    records: list[dict], db_path: str = "warehouse.duckdb"
) -> int:
    """Upsert XBRL facts into bronze.raw_financial_facts (batch, idempotent)."""
    if not records:
        logger.warning("No financial-fact records to load")
        return 0
    df = pd.DataFrame(records)
    for col in FACT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["taxonomy"] = df["taxonomy"].fillna("us-gaap")
    df = df.dropna(
        subset=["cik", "metric", "unit", "period_end", "filed_date", "accession_number"]
    )
    if df.empty:
        logger.warning("All fact records dropped: missing key fields")
        return 0
    df["fact_key"] = [fact_key(r) for r in df.to_dict("records")]
    # The same fact can appear twice inside one filing (e.g. dimensional
    # duplicates); keep the first so the primary key holds.
    df = df.drop_duplicates(subset=["fact_key"], keep="first")
    for col in ("period_start", "period_end", "filed_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    df["fiscal_year"] = pd.to_numeric(df["fiscal_year"], errors="coerce").astype(
        "Int64"
    )
    df["ingested_at"] = _now()
    con = connect(db_path)
    try:
        n = _upsert(con, "bronze.raw_financial_facts", df[FACT_COLUMNS])
        logger.info("Loaded %d financial-fact records", n)
        return n
    finally:
        con.close()


def load_market_data(df: pd.DataFrame, db_path: str = "warehouse.duckdb") -> int:
    """Upsert daily prices into bronze.raw_market_data."""
    if df is None or df.empty:
        logger.warning("No market data to load")
        return 0
    df = df.copy()
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.date
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = None
    df = df[
        ["ticker", "date", "open", "high", "low", "close", "volume"]
    ].drop_duplicates(subset=["ticker", "date"], keep="last")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    df["ingested_at"] = _now()
    con = connect(db_path)
    try:
        n = _upsert(con, "bronze.raw_market_data", df)
        logger.info("Loaded %d market-data rows", n)
        return n
    finally:
        con.close()


def record_run(db_path: str, **fields) -> None:
    """Append one lineage row to bronze.ingestion_runs."""
    cols = [
        "run_id",
        "source",
        "cik",
        "landed_path",
        "sha256",
        "rows_loaded",
        "status",
        "error",
        "started_at",
        "finished_at",
    ]
    con = connect(db_path)
    try:
        con.execute(
            f"INSERT INTO bronze.ingestion_runs ({', '.join(cols)}) VALUES "
            f"({', '.join('?' for _ in cols)})",
            [fields.get(c) for c in cols],
        )
    finally:
        con.close()

"""
Tests for ingestion/loader.py.

Uses real DuckDB in-memory databases to verify schema creation and
upsert behaviour.
"""

import duckdb
import pytest

from ingestion.loader import (
    init_warehouse,
    load_raw_filings,
    load_raw_financial_facts,
)


# ---------------------------------------------------------------------------
# init_warehouse
# ---------------------------------------------------------------------------


def test_init_warehouse_creates_schemas(test_db):
    """init_warehouse should create bronze, silver, and gold schemas."""
    con = duckdb.connect(test_db, read_only=True)
    try:
        schemas = con.execute(
            "SELECT schema_name FROM information_schema.schemata"
        ).fetchall()
        schema_names = {row[0] for row in schemas}

        assert "bronze" in schema_names
        assert "silver" in schema_names
        assert "gold" in schema_names
    finally:
        con.close()


def test_init_warehouse_creates_tables(test_db):
    """init_warehouse should create the expected bronze tables."""
    con = duckdb.connect(test_db, read_only=True)
    try:
        tables = con.execute(
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = 'bronze'"
        ).fetchall()
        table_names = {row[1] for row in tables}

        assert "raw_filings" in table_names
        assert "raw_financial_facts" in table_names
        assert "raw_market_data" in table_names
    finally:
        con.close()


# ---------------------------------------------------------------------------
# load_raw_financial_facts
# ---------------------------------------------------------------------------


def test_load_raw_financial_facts_inserts(test_db, sample_financial_records):
    """Loading records should insert them into bronze.raw_financial_facts."""
    load_raw_financial_facts(sample_financial_records, db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM bronze.raw_financial_facts"
        ).fetchone()[0]
        assert count == 3
    finally:
        con.close()


def test_load_raw_financial_facts_upserts(test_db, sample_financial_records):
    """Loading the same records twice should not create duplicates."""
    load_raw_financial_facts(sample_financial_records, db_path=test_db)
    load_raw_financial_facts(sample_financial_records, db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM bronze.raw_financial_facts"
        ).fetchone()[0]
        # Should still be 3, not 6
        assert count == 3
    finally:
        con.close()


def test_load_raw_financial_facts_values_correct(test_db, sample_financial_records):
    """Verify that loaded values can be queried back correctly."""
    load_raw_financial_facts(sample_financial_records, db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        rows = con.execute(
            "SELECT cik, metric, value FROM bronze.raw_financial_facts "
            "WHERE metric = 'Revenues' ORDER BY value"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][2] == 383285000000
        assert rows[1][2] == 394328000000
    finally:
        con.close()


# ---------------------------------------------------------------------------
# load_raw_filings
# ---------------------------------------------------------------------------


def test_load_raw_filings_inserts(test_db):
    """Loading filing records should insert them into bronze.raw_filings."""
    filings = [
        {
            "cik": "0000320193",
            "accession_number": "0000320193-23-000106",
            "form_type": "10-K",
            "filing_date": "2023-11-03",
            "period_of_report": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
        },
        {
            "cik": "0000320193",
            "accession_number": "0000320193-22-000108",
            "form_type": "10-K",
            "filing_date": "2022-10-28",
            "period_of_report": "2022-09-30",
            "primary_document": "aapl-20220930.htm",
        },
    ]
    load_raw_filings(filings, db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM bronze.raw_filings"
        ).fetchone()[0]
        assert count == 2
    finally:
        con.close()


def test_load_raw_filings_upserts(test_db):
    """Loading the same filing records twice should not create duplicates."""
    filings = [
        {
            "cik": "0000320193",
            "accession_number": "0000320193-23-000106",
            "form_type": "10-K",
            "filing_date": "2023-11-03",
            "period_of_report": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
        },
    ]
    load_raw_filings(filings, db_path=test_db)
    load_raw_filings(filings, db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM bronze.raw_filings"
        ).fetchone()[0]
        assert count == 1
    finally:
        con.close()


def test_load_raw_filings_empty_list(test_db):
    """Loading an empty list should be a no-op, not an error."""
    load_raw_filings([], db_path=test_db)

    con = duckdb.connect(test_db, read_only=True)
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM bronze.raw_filings"
        ).fetchone()[0]
        assert count == 0
    finally:
        con.close()

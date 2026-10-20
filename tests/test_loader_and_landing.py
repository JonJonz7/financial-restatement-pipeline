import duckdb
import pandas as pd

from ingestion import landing
from ingestion.edgar_client import extract_financial_metrics
from ingestion.loader import fact_key, load_market_data, load_raw_financial_facts


def _count(db, sql):
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def test_init_creates_layers_and_tables(db):
    tables = _count(
        db, "select count(*) from information_schema.tables where table_schema='bronze'"
    )
    assert tables == 5


def test_quarter_and_year_with_same_end_are_both_kept(db, companyfacts):
    """Regression: v1's key ignored period_start, so the 12-month value overwrote the 3-month one."""
    load_raw_financial_facts(extract_financial_metrics(companyfacts), db)
    n = _count(
        db, "select count(*) from bronze.raw_financial_facts where metric='Revenues'"
    )
    assert n == 2


def test_fact_load_is_idempotent(db, companyfacts):
    rows = extract_financial_metrics(companyfacts)
    load_raw_financial_facts(rows, db)
    load_raw_financial_facts(rows, db)
    assert _count(db, "select count(*) from bronze.raw_financial_facts") == len(rows)


def test_fact_key_is_deterministic_and_sensitive():
    base = {
        "cik": "1",
        "taxonomy": "us-gaap",
        "metric": "Revenues",
        "unit": "USD",
        "period_start": "2023-01-01",
        "period_end": "2023-12-31",
        "accession_number": "a",
    }
    assert fact_key(base) == fact_key(dict(base))
    assert fact_key(base) != fact_key({**base, "period_start": "2023-10-01"})


def test_market_data_dedupes_by_ticker_and_date(db):
    df = pd.DataFrame(
        {
            "ticker": ["X", "X"],
            "date": ["2024-01-02", "2024-01-02"],
            "open": [1, 1],
            "high": [1, 1],
            "low": [1, 1],
            "close": [1.0, 2.0],
            "volume": [10, 20],
        }
    )
    load_market_data(df, db)
    assert _count(db, "select count(*) from bronze.raw_market_data") == 1
    assert _count(db, "select close from bronze.raw_market_data") == 2.0


def test_landing_roundtrip_and_latest(tmp_path):
    path, sha = landing.land("companyfacts", "0000000001", {"b": 2, "a": 1}, tmp_path)
    payload, sha2 = landing.read(path)
    assert payload == {"a": 1, "b": 2} and sha == sha2
    assert landing.latest("companyfacts", tmp_path) == {"0000000001": path}
    # same day, same content -> same file, same hash (idempotent)
    assert landing.land("companyfacts", "0000000001", {"a": 1, "b": 2}, tmp_path) == (
        path,
        sha,
    )

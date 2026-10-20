"""Shared fixtures."""

import pytest


@pytest.fixture
def companyfacts() -> dict:
    """Minimal companyfacts JSON with the case that broke v1: a quarter and a
    full year ending the same day, reported in the same filing."""
    filing = {
        "accn": "0000900001-24-000004",
        "fy": 2023,
        "fp": "FY",
        "form": "10-K",
        "filed": "2024-02-20",
    }
    return {
        "cik": 900001,
        "entityName": "Test Co",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                **filing,
                                "start": "2023-10-01",
                                "end": "2023-12-31",
                                "val": 250,
                            },
                            {
                                **filing,
                                "start": "2023-01-01",
                                "end": "2023-12-31",
                                "val": 1000,
                            },
                        ]
                    }
                },
                "Assets": {
                    "units": {"USD": [{**filing, "end": "2023-12-31", "val": 5000}]}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [{**filing, "end": "2024-02-01", "val": 1_000_000}]
                    }
                },
            },
        },
    }


@pytest.fixture
def submissions() -> dict:
    return {
        "cik": "900001",
        "name": "Test Co",
        "tickers": ["TST"],
        "sic": "1234",
        "sicDescription": "Testing",
        "fiscalYearEnd": "1231",
        "filings": {
            "recent": {
                "accessionNumber": ["a-1", "a-2", "a-3", "a-4"],
                "form": ["10-K/A", "8-K", "10-K", "10-Q"],
                "filingDate": ["2024-05-10", "2024-03-01", "2024-02-20", "2023-11-03"],
                "reportDate": ["2023-12-31", "", "2023-12-31", "2023-09-30"],
                "primaryDocument": ["x.htm", "y.htm", "z.htm", "w.htm"],
            }
        },
    }


@pytest.fixture
def db(tmp_path) -> str:
    from ingestion.loader import init_warehouse

    path = str(tmp_path / "test.duckdb")
    init_warehouse(path)
    return path

"""
Shared fixtures for the Financial Restatement Pipeline test suite.
"""

import os
import tempfile

import duckdb
import pytest

from ingestion.loader import init_warehouse


@pytest.fixture
def sample_xbrl_facts() -> dict:
    """Small dict mimicking the SEC EDGAR companyfacts JSON response."""
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "description": "Total revenues.",
                    "units": {
                        "USD": [
                            {
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 383285000000,
                                "accn": "0000320193-23-000106",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2023-11-03",
                            },
                            {
                                "start": "2021-10-01",
                                "end": "2022-09-30",
                                "val": 394328000000,
                                "accn": "0000320193-22-000108",
                                "fy": 2022,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2022-10-28",
                            },
                        ]
                    },
                },
                "Assets": {
                    "label": "Assets",
                    "description": "Total assets.",
                    "units": {
                        "USD": [
                            {
                                "end": "2023-09-30",
                                "val": 352583000000,
                                "accn": "0000320193-23-000106",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2023-11-03",
                            },
                        ]
                    },
                },
                "EarningsPerShareBasic": {
                    "label": "Earnings Per Share, Basic",
                    "description": "Basic EPS.",
                    "units": {
                        "USD/shares": [
                            {
                                "start": "2022-10-01",
                                "end": "2023-09-30",
                                "val": 6.16,
                                "accn": "0000320193-23-000106",
                                "fy": 2023,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2023-11-03",
                            },
                        ]
                    },
                },
            },
        },
    }


@pytest.fixture
def sample_financial_records() -> list[dict]:
    """List of dicts ready for loading into DuckDB bronze.raw_financial_facts."""
    return [
        {
            "cik": "0000320193",
            "metric": "Revenues",
            "period_start": "2022-10-01",
            "period_end": "2023-09-30",
            "value": 383285000000,
            "unit": "USD",
            "form": "10-K",
            "filed_date": "2023-11-03",
            "accession_number": "0000320193-23-000106",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
        },
        {
            "cik": "0000320193",
            "metric": "Revenues",
            "period_start": "2021-10-01",
            "period_end": "2022-09-30",
            "value": 394328000000,
            "unit": "USD",
            "form": "10-K",
            "filed_date": "2022-10-28",
            "accession_number": "0000320193-22-000108",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
        },
        {
            "cik": "0000320193",
            "metric": "Assets",
            "period_start": None,
            "period_end": "2023-09-30",
            "value": 352583000000,
            "unit": "USD",
            "form": "10-K",
            "filed_date": "2023-11-03",
            "accession_number": "0000320193-23-000106",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
        },
    ]


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary DuckDB database with schemas initialised.

    Yields the path to the database file.  Cleans up after the test.
    """
    db_path = str(tmp_path / "test_warehouse.duckdb")
    init_warehouse(db_path)
    yield db_path
    # Cleanup happens automatically via tmp_path

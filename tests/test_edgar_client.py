"""
Tests for ingestion/edgar_client.py.

All SEC EDGAR API calls are mocked — no real network requests.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ingestion.edgar_client import (
    _headers,
    _normalize_cik,
    extract_financial_metrics,
    get_company_facts,
    get_recent_filings,
)


# ---------------------------------------------------------------------------
# get_company_facts
# ---------------------------------------------------------------------------


@patch("ingestion.edgar_client.requests.get")
@patch("ingestion.edgar_client.time.sleep")
def test_get_company_facts_returns_dict(mock_sleep, mock_get):
    """get_company_facts should return the parsed JSON dict from EDGAR."""
    expected = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": {}},
    }
    mock_response = MagicMock()
    mock_response.json.return_value = expected
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = get_company_facts("320193")

    assert isinstance(result, dict)
    assert result["entityName"] == "Apple Inc."
    assert "facts" in result
    mock_get.assert_called_once()
    # Verify the URL contains the zero-padded CIK
    call_url = mock_get.call_args[0][0]
    assert "CIK0000320193" in call_url


# ---------------------------------------------------------------------------
# extract_financial_metrics
# ---------------------------------------------------------------------------


def test_extract_financial_metrics_flattens_correctly(sample_xbrl_facts):
    """Flattened rows should contain the correct fields from nested XBRL."""
    rows = extract_financial_metrics(sample_xbrl_facts)

    assert len(rows) == 4  # 2 Revenue + 1 Assets + 1 EPS

    revenue_rows = [r for r in rows if r["metric"] == "Revenues"]
    assert len(revenue_rows) == 2

    # Check a specific row
    fy2023_rev = [r for r in revenue_rows if r["fiscal_year"] == 2023][0]
    assert fy2023_rev["value"] == 383285000000
    assert fy2023_rev["unit"] == "USD"
    assert fy2023_rev["form"] == "10-K"
    assert fy2023_rev["filed_date"] == "2023-11-03"
    assert fy2023_rev["period_end"] == "2023-09-30"
    assert fy2023_rev["accession_number"] == "0000320193-23-000106"
    assert fy2023_rev["cik"] == "0000320193"


def test_extract_financial_metrics_handles_empty_facts():
    """An empty facts dict should return an empty list without errors."""
    empty_facts = {"cik": 12345, "entityName": "Empty Corp", "facts": {}}
    rows = extract_financial_metrics(empty_facts)
    assert rows == []


def test_extract_financial_metrics_handles_missing_taxonomy():
    """A facts dict with no us-gaap taxonomy should return empty list."""
    facts = {
        "cik": 12345,
        "entityName": "Foreign Corp",
        "facts": {"ifrs-full": {"Revenue": {"units": {"EUR": []}}}},
    }
    rows = extract_financial_metrics(facts, taxonomy="us-gaap")
    assert rows == []


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@patch("ingestion.edgar_client.requests.get")
@patch("ingestion.edgar_client.time.sleep")
@patch("ingestion.edgar_client.time.monotonic")
def test_rate_limiting(mock_monotonic, mock_sleep, mock_get):
    """_rate_limit should call time.sleep when requests happen too fast."""
    # Simulate two requests very close together (elapsed = 0.01s < 0.1s delay)
    mock_monotonic.side_effect = [0.0, 0.01, 0.11, 0.11]

    mock_response = MagicMock()
    mock_response.json.return_value = {"cik": 1, "entityName": "X", "facts": {}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    # Reset the module-level _last_request_time
    import ingestion.edgar_client as ec
    ec._last_request_time = 0.0

    get_company_facts("1")

    # sleep should have been called because elapsed < RATE_LIMIT_DELAY
    assert mock_sleep.called


# ---------------------------------------------------------------------------
# User-Agent header
# ---------------------------------------------------------------------------


def test_user_agent_header_set():
    """Requests must include the required User-Agent header."""
    headers = _headers()
    assert "User-Agent" in headers
    assert len(headers["User-Agent"]) > 0
    assert "Accept" in headers
    assert headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# get_recent_filings
# ---------------------------------------------------------------------------


@patch("ingestion.edgar_client._get_json")
def test_get_recent_filings_filters_form_type(mock_get_json):
    """get_recent_filings should only return filings matching the form_type."""
    mock_get_json.return_value = {
        "cik": "0000320193",
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "10-K", "8-K", "10-Q"],
                "accessionNumber": ["acc-1", "acc-2", "acc-3", "acc-4", "acc-5"],
                "filingDate": [
                    "2023-11-03",
                    "2023-08-04",
                    "2022-10-28",
                    "2023-07-01",
                    "2023-05-05",
                ],
                "reportDate": [
                    "2023-09-30",
                    "2023-07-01",
                    "2022-09-30",
                    "2023-06-30",
                    "2023-04-01",
                ],
                "primaryDocument": [
                    "aapl-20230930.htm",
                    "aapl-20230701.htm",
                    "aapl-20220930.htm",
                    "aapl-8k.htm",
                    "aapl-20230401.htm",
                ],
            }
        },
    }

    # Filter for 10-K only
    filings = get_recent_filings("320193", form_type="10-K")
    assert len(filings) == 2
    assert all(f["form_type"] == "10-K" for f in filings)

    # Filter for 10-Q only
    mock_get_json.reset_mock()
    mock_get_json.return_value = {
        "cik": "0000320193",
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "10-K", "8-K", "10-Q"],
                "accessionNumber": ["acc-1", "acc-2", "acc-3", "acc-4", "acc-5"],
                "filingDate": [
                    "2023-11-03",
                    "2023-08-04",
                    "2022-10-28",
                    "2023-07-01",
                    "2023-05-05",
                ],
                "reportDate": [
                    "2023-09-30",
                    "2023-07-01",
                    "2022-09-30",
                    "2023-06-30",
                    "2023-04-01",
                ],
                "primaryDocument": [
                    "aapl-20230930.htm",
                    "aapl-20230701.htm",
                    "aapl-20220930.htm",
                    "aapl-8k.htm",
                    "aapl-20230401.htm",
                ],
            }
        },
    }
    filings_q = get_recent_filings("320193", form_type="10-Q")
    assert len(filings_q) == 2
    assert all(f["form_type"] == "10-Q" for f in filings_q)


# ---------------------------------------------------------------------------
# CIK normalisation
# ---------------------------------------------------------------------------


def test_normalize_cik():
    """CIK strings should be zero-padded to 10 digits."""
    assert _normalize_cik("320193") == "0000320193"
    assert _normalize_cik("0000320193") == "0000320193"
    assert _normalize_cik("1") == "0000000001"

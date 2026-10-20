from unittest.mock import MagicMock, patch

import pytest

from ingestion import edgar_client as ec


def test_normalize_cik():
    assert ec._normalize_cik("320193") == "0000320193"
    assert ec._normalize_cik("0000320193") == "0000320193"


def test_extract_keeps_period_start_taxonomy_and_unit(companyfacts):
    rows = ec.extract_financial_metrics(companyfacts)
    revenue = [r for r in rows if r["metric"] == "Revenues"]
    assert {r["period_start"] for r in revenue} == {"2023-10-01", "2023-01-01"}
    assert {r["taxonomy"] for r in rows} == {"us-gaap", "dei"}
    assets = next(r for r in rows if r["metric"] == "Assets")
    assert assets["period_start"] is None  # instant fact
    shares = next(r for r in rows if r["taxonomy"] == "dei")
    assert shares["unit"] == "shares"


def test_extract_single_taxonomy_and_empty():
    assert ec.extract_financial_metrics({"cik": 1, "facts": {}}) == []
    assert ec.extract_financial_metrics({"cik": 1}, "us-gaap") == []


def test_parse_filings_keeps_amendments_and_drops_8k(submissions):
    filings = ec.parse_filings(submissions)
    assert [f["form_type"] for f in filings] == ["10-K/A", "10-K", "10-Q"]
    assert filings[0]["cik"] == "0000900001"


def test_parse_company_profile(submissions):
    p = ec.parse_company_profile(submissions)
    assert p == {
        "cik": "0000900001",
        "company_name": "Test Co",
        "ticker": "TST",
        "sic": "1234",
        "sic_description": "Testing",
        "fiscal_year_end": "1231",
    }


def test_user_agent_is_required(monkeypatch):
    monkeypatch.setenv("EDGAR_USER_AGENT", "")
    with pytest.raises(RuntimeError, match="EDGAR_USER_AGENT"):
        ec._headers()
    monkeypatch.setenv("EDGAR_USER_AGENT", "Jane Doe jane@example.com")
    with pytest.raises(RuntimeError):
        ec._headers()  # placeholder domains are rejected too
    monkeypatch.setenv("EDGAR_USER_AGENT", "Jane Doe jane.doe@university.edu")
    assert ec._headers()["User-Agent"] == "Jane Doe jane.doe@university.edu"


@patch("ingestion.edgar_client.time.sleep")
@patch("ingestion.edgar_client.requests.get")
def test_get_json_retries_transient_errors(mock_get, _sleep, monkeypatch):
    monkeypatch.setenv("EDGAR_USER_AGENT", "Jane Doe jane.doe@university.edu")
    busy = MagicMock(status_code=503)
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"cik": 1}
    mock_get.side_effect = [busy, ok]
    assert ec._get_json("https://data.sec.gov/x") == {"cik": 1}
    assert mock_get.call_count == 2


@patch("ingestion.edgar_client.time.sleep")
@patch("ingestion.edgar_client.time.monotonic")
def test_rate_limit_sleeps_when_too_fast(mock_mono, mock_sleep):
    ec._last_request_time = 100.0
    mock_mono.return_value = 100.05
    ec._rate_limit()
    mock_sleep.assert_called_once()
    assert mock_sleep.call_args[0][0] == pytest.approx(ec.RATE_LIMIT_DELAY - 0.05)

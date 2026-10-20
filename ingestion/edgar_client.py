"""
SEC EDGAR API client.

Fetches XBRL company facts and filing submissions from the SEC EDGAR
public API (data.sec.gov) and flattens them into rows for the warehouse.
Respects SEC fair-access rules: a declared User-Agent and < 10 requests/sec.

Pure parsing functions (``parse_company_profile``, ``parse_filings``,
``extract_financial_metrics``) take the raw JSON and never touch the network,
so the same code path runs on live responses, the landing zone and fixtures.
"""

import logging
import time
from typing import Any, Iterable

import requests

from ingestion.config import (
    RATE_LIMIT_DELAY,
    TAXONOMIES,
    TRACKED_FORMS,
    require_user_agent,
)

logger = logging.getLogger(__name__)

_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Sleep just long enough to stay under the SEC request-rate limit."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _headers() -> dict[str, str]:
    return {
        "User-Agent": require_user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _normalize_cik(cik: str) -> str:
    """'320193' or '0000320193' -> '0000320193'."""
    return str(cik).lstrip("0").zfill(10)


def _get_json(url: str, retries: int = 3) -> dict:
    """GET a JSON document, retrying transient failures with backoff."""
    for attempt in range(1, retries + 1):
        _rate_limit()
        logger.debug("GET %s (attempt %d)", url, attempt)
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            wait = 2**attempt
            logger.warning("HTTP %s from SEC, retrying in %ss", resp.status_code, wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Unreachable: retries exhausted for {url}")


# ---------------------------------------------------------------------------
# Network calls
# ---------------------------------------------------------------------------


def get_company_facts(cik: str) -> dict:
    """Fetch every XBRL fact a company has ever filed (companyfacts endpoint)."""
    cik = _normalize_cik(cik)
    logger.info("Fetching company facts for CIK %s", cik)
    data = _get_json(_COMPANY_FACTS_URL.format(cik=cik))
    logger.info("Retrieved facts for %s (%s)", cik, data.get("entityName", "unknown"))
    return data


def get_submissions(cik: str) -> dict:
    """Fetch company profile + recent filing index (submissions endpoint)."""
    cik = _normalize_cik(cik)
    logger.info("Fetching submissions for CIK %s", cik)
    return _get_json(_SUBMISSIONS_URL.format(cik=cik))


def get_recent_filings(cik: str, form_type: str = "10-K") -> list[dict]:
    """Fetch submissions and return the filings of one form type."""
    return parse_filings(get_submissions(cik), forms=(form_type,))


# ---------------------------------------------------------------------------
# Pure parsers (no network)
# ---------------------------------------------------------------------------


def parse_company_profile(submissions: dict) -> dict:
    """Company name, ticker, industry code and fiscal year end from submissions JSON."""
    tickers = submissions.get("tickers") or []
    return {
        "cik": _normalize_cik(submissions.get("cik", "0")),
        "company_name": submissions.get("name"),
        "ticker": tickers[0] if tickers else None,
        "sic": submissions.get("sic"),
        "sic_description": submissions.get("sicDescription"),
        "fiscal_year_end": submissions.get("fiscalYearEnd"),
    }


def parse_filings(
    submissions: dict, forms: Iterable[str] = TRACKED_FORMS
) -> list[dict]:
    """Flatten the column-oriented 'recent filings' arrays into one dict per filing."""
    cik = _normalize_cik(submissions.get("cik", "0"))
    recent = submissions.get("filings", {}).get("recent", {})
    wanted = set(forms)

    def col(name: str, i: int) -> Any:
        values = recent.get(name, [])
        return values[i] if i < len(values) else None

    filings = [
        {
            "cik": cik,
            "accession_number": col("accessionNumber", i),
            "form_type": form,
            "filing_date": col("filingDate", i),
            "period_of_report": col("reportDate", i) or None,
            "primary_document": col("primaryDocument", i),
        }
        for i, form in enumerate(recent.get("form", []))
        if form in wanted
    ]
    logger.info("Found %d tracked filings for CIK %s", len(filings), cik)
    return filings


def extract_financial_metrics(
    facts: dict,
    taxonomies: str | Iterable[str] = TAXONOMIES,
) -> list[dict]:
    """Flatten companyfacts JSON into one row per (metric, unit, period, filing).

    Each XBRL fact is identified by its metric AND unit AND period_start AND
    period_end. Duration facts (revenue) have a start date; instant facts
    (assets) don't. A 3-month quarter and a 12-month year can share the same
    period_end, so period_start is part of the identity, never optional.
    """
    if isinstance(taxonomies, str):
        taxonomies = (taxonomies,)
    cik = _normalize_cik(str(facts.get("cik", "0")))
    rows: list[dict] = []
    for taxonomy in taxonomies:
        taxonomy_data: dict[str, Any] = facts.get("facts", {}).get(taxonomy, {})
        for metric_name, metric_obj in taxonomy_data.items():
            for unit_label, entries in metric_obj.get("units", {}).items():
                for entry in entries:
                    rows.append(
                        {
                            "cik": cik,
                            "taxonomy": taxonomy,
                            "metric": metric_name,
                            "unit": unit_label,
                            "period_start": entry.get("start"),
                            "period_end": entry.get("end"),
                            "value": entry.get("val"),
                            "form": entry.get("form"),
                            "filed_date": entry.get("filed"),
                            "accession_number": entry.get("accn"),
                            "fiscal_year": entry.get("fy"),
                            "fiscal_period": entry.get("fp"),
                            "frame": entry.get("frame"),
                        }
                    )
    logger.info("Extracted %d fact rows for CIK %s", len(rows), cik)
    return rows

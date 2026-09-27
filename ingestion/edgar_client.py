"""
SEC EDGAR API client.

Fetches XBRL company facts and filing submissions from the SEC EDGAR
public API endpoints. Respects SEC rate-limit guidelines (10 req/sec).
"""

import logging
import os
import time
from typing import Any

import requests

from ingestion.config import EDGAR_USER_AGENT, RATE_LIMIT_DELAY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

_last_request_time: float = 0.0


def _rate_limit() -> None:
    """Sleep if necessary so we never exceed 10 requests / second."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)
    _last_request_time = time.monotonic()


def _headers() -> dict[str, str]:
    """Return request headers with the required User-Agent."""
    user_agent = os.getenv("EDGAR_USER_AGENT", EDGAR_USER_AGENT)
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _normalize_cik(cik: str) -> str:
    """Zero-pad a CIK to 10 digits (SEC convention)."""
    return cik.lstrip("0").zfill(10)


def _get_json(url: str) -> dict:
    """GET *url*, enforce rate limit, return parsed JSON."""
    _rate_limit()
    logger.debug("GET %s", url)
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_company_facts(cik: str) -> dict:
    """Fetch all XBRL financial facts for a company.

    Args:
        cik: Central Index Key (with or without leading zeros).

    Returns:
        Raw JSON dict from the EDGAR companyfacts endpoint.
    """
    cik = _normalize_cik(cik)
    url = _COMPANY_FACTS_URL.format(cik=cik)
    logger.info("Fetching company facts for CIK %s", cik)
    try:
        data = _get_json(url)
        logger.info(
            "Retrieved facts for %s (entity: %s)",
            cik,
            data.get("entityName", "unknown"),
        )
        return data
    except requests.HTTPError as exc:
        logger.error("Failed to fetch company facts for CIK %s: %s", cik, exc)
        raise
    except requests.ConnectionError as exc:
        logger.error("Connection error fetching CIK %s: %s", cik, exc)
        raise


def get_submissions(cik: str) -> dict:
    """Fetch the full filing submission history for a company.

    Args:
        cik: Central Index Key.

    Returns:
        Raw JSON dict from the EDGAR submissions endpoint.
    """
    cik = _normalize_cik(cik)
    url = _SUBMISSIONS_URL.format(cik=cik)
    logger.info("Fetching submissions for CIK %s", cik)
    try:
        data = _get_json(url)
        logger.info(
            "Retrieved submissions for %s (filings: %d recent)",
            cik,
            len(data.get("filings", {}).get("recent", {}).get("accessionNumber", [])),
        )
        return data
    except requests.HTTPError as exc:
        logger.error("Failed to fetch submissions for CIK %s: %s", cik, exc)
        raise
    except requests.ConnectionError as exc:
        logger.error("Connection error fetching submissions for CIK %s: %s", cik, exc)
        raise


def get_recent_filings(cik: str, form_type: str = "10-K") -> list[dict]:
    """Extract recent filings of a given form type from submission history.

    Args:
        cik: Central Index Key.
        form_type: SEC form type filter (default ``"10-K"``).

    Returns:
        List of dicts with keys: accession_number, filing_date,
        period_of_report, primary_document, form_type.
    """
    cik = _normalize_cik(cik)
    submissions = get_submissions(cik)
    recent = submissions.get("filings", {}).get("recent", {})

    forms: list[str] = recent.get("form", [])
    accession_numbers: list[str] = recent.get("accessionNumber", [])
    filing_dates: list[str] = recent.get("filingDate", [])
    report_dates: list[str] = recent.get("reportDate", [])
    primary_docs: list[str] = recent.get("primaryDocument", [])

    filings: list[dict] = []
    for i, form in enumerate(forms):
        if form == form_type:
            filings.append(
                {
                    "cik": cik,
                    "accession_number": accession_numbers[i] if i < len(accession_numbers) else None,
                    "form_type": form,
                    "filing_date": filing_dates[i] if i < len(filing_dates) else None,
                    "period_of_report": report_dates[i] if i < len(report_dates) else None,
                    "primary_document": primary_docs[i] if i < len(primary_docs) else None,
                }
            )

    logger.info(
        "Found %d %s filings for CIK %s", len(filings), form_type, cik
    )
    return filings


def extract_financial_metrics(
    facts: dict,
    taxonomy: str = "us-gaap",
) -> list[dict]:
    """Flatten nested XBRL facts into tabular rows.

    Each row contains:
        cik, metric, period_start, period_end, value, unit, form,
        filed_date, accession_number, fiscal_year, fiscal_period.

    Args:
        facts: Raw company-facts JSON (from :func:`get_company_facts`).
        taxonomy: XBRL taxonomy to extract (default ``"us-gaap"``).

    Returns:
        List of flat dicts suitable for warehouse loading.
    """
    cik = _normalize_cik(str(facts.get("cik", "0")))
    taxonomy_data: dict[str, Any] = facts.get("facts", {}).get(taxonomy, {})

    rows: list[dict] = []
    for metric_name, metric_obj in taxonomy_data.items():
        units: dict[str, list[dict]] = metric_obj.get("units", {})
        for unit_label, entries in units.items():
            for entry in entries:
                rows.append(
                    {
                        "cik": cik,
                        "metric": metric_name,
                        "period_start": entry.get("start"),
                        "period_end": entry.get("end"),
                        "value": entry.get("val"),
                        "unit": unit_label,
                        "form": entry.get("form"),
                        "filed_date": entry.get("filed"),
                        "accession_number": entry.get("accn"),
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),
                    }
                )

    logger.info(
        "Extracted %d metric rows for CIK %s (taxonomy=%s)",
        len(rows),
        cik,
        taxonomy,
    )
    return rows

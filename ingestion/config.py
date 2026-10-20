"""
Configuration for the Financial Restatement & Anomaly Detection Pipeline.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")  # optional; real environment variables win

# SEC EDGAR requires a User-Agent that names you and gives a real contact
# email ("Sample Company Name AdminContact@sample.com"). Requests without one
# are refused with 403. There is deliberately no working default: set it in
# .env or your shell before running live ingestion.
EDGAR_USER_AGENT: str = os.getenv("EDGAR_USER_AGENT", "")

# SEC fair-access limit is 10 requests/second; stay comfortably below it.
RATE_LIMIT_DELAY: float = 0.15

# Default DuckDB warehouse path.
DB_PATH: str = os.getenv("WAREHOUSE_DB_PATH", str(PROJECT_ROOT / "warehouse.duckdb"))

# Landing zone: every raw API response is saved here (gzipped, immutable)
# before it is parsed, so bronze can be rebuilt without calling the API again.
LANDING_DIR: Path = Path(
    os.getenv("LANDING_DIR", str(PROJECT_ROOT / "data" / "landing"))
)

# XBRL taxonomies to extract. us-gaap holds the financial statements; dei
# holds cover-page facts such as shares outstanding (used for market cap).
TAXONOMIES: tuple[str, ...] = ("us-gaap", "dei")

# Filing forms tracked in bronze.raw_filings. Amendments (/A) matter most:
# a 10-K/A is how many restatements are filed.
TRACKED_FORMS: tuple[str, ...] = ("10-K", "10-K/A", "10-Q", "10-Q/A")

# Watched companies: CIK -> ticker.
# CIKs are stored as zero-padded 10-digit strings (SEC convention).
WATCHED_COMPANIES: dict[str, str] = {
    "0000320193": "AAPL",
    "0000789019": "MSFT",
    "0001652044": "GOOGL",
    "0001018724": "AMZN",
    "0001326801": "META",
    "0001318605": "TSLA",
    "0000019617": "JPM",
    "0000886982": "GS",
    "0000070858": "BAC",
    "0000072971": "WFC",
    "0000200406": "JNJ",
    "0000078003": "PFE",
    "0000731766": "UNH",
    "0000034088": "XOM",
    "0000093410": "CVX",
    "0000104169": "WMT",
    "0000354950": "HD",
    "0001403161": "V",
    "0001141391": "MA",
    "0001045810": "NVDA",
}


def require_user_agent() -> str:
    """Return the configured EDGAR User-Agent, or raise a clear error."""
    ua = os.getenv("EDGAR_USER_AGENT", EDGAR_USER_AGENT).strip()
    if not ua or "@" not in ua or "@example." in ua:
        raise RuntimeError(
            "Set EDGAR_USER_AGENT to your name and a real contact email, e.g.\n"
            '  export EDGAR_USER_AGENT="Jane Doe jane.doe@gmail.com"\n'
            "SEC refuses requests without one (HTTP 403). To run without the "
            "network, use `make demo` instead."
        )
    return ua

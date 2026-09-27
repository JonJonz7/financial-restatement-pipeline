"""
Configuration for the Financial Restatement & Anomaly Detection Pipeline.
"""

import os

# SEC EDGAR requires a User-Agent header with contact information.
EDGAR_USER_AGENT: str = os.getenv(
    "EDGAR_USER_AGENT",
    "FinancialRestatementPipeline/1.0 (contact@example.com)",
)

# SEC rate-limit: 10 requests per second max.
RATE_LIMIT_DELAY: float = 0.1

# Default DuckDB warehouse path.
DB_PATH: str = os.getenv(
    "WAREHOUSE_DB_PATH",
    "warehouse.duckdb",
)

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
    "0000015511": "V",   # Visa — CIK used post-IPO filing history
    "0001141391": "MA",
    "0001045810": "NVDA",
}

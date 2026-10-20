"""
Market data client using yfinance (Yahoo Finance).

Provides OHLCV price history, company metadata, and batch snapshots
for cross-validation against SEC-reported financials.
"""

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def get_market_data(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Fetch daily OHLCV history for a single ticker.

    Market cap is deliberately not taken from yfinance: its ``marketCap`` is
    today's value only, and copying it onto past dates would be wrong. The
    warehouse derives historical market cap from close x SEC-reported shares.

    Args:
        ticker: Stock ticker symbol (e.g. ``"AAPL"``).
        period: yfinance period string (default ``"5y"``).

    Returns:
        DataFrame with columns: ticker, date, open, high, low, close,
        volume.
    """
    logger.info("Fetching market data for %s (period=%s)", ticker, period)
    stock = yf.Ticker(ticker)

    try:
        hist: pd.DataFrame = stock.history(period=period)
    except Exception as exc:
        logger.error("Failed to fetch history for %s: %s", ticker, exc)
        return pd.DataFrame()

    if hist.empty:
        logger.warning("No market data returned for %s", ticker)
        return pd.DataFrame()

    hist = hist.reset_index()
    hist.columns = [c.lower().replace(" ", "_") for c in hist.columns]

    # Rename 'date' column if it came through as 'Date'
    if "date" not in hist.columns and "Date" in hist.columns:
        hist = hist.rename(columns={"Date": "date"})

    # Attempt to get current market cap from info; yfinance history
    # does not provide per-day market cap, so we fill the column with
    # the latest snapshot value (or NaN).
    hist["ticker"] = ticker
    desired = ["ticker", "date", "open", "high", "low", "close", "volume"]
    available = [c for c in desired if c in hist.columns]
    hist = hist[available]

    logger.info("Retrieved %d rows of market data for %s", len(hist), ticker)
    return hist


def get_company_info(ticker: str) -> dict:
    """Fetch company metadata: sector, industry, market cap, revenue.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dict with keys: ticker, sector, industry, market_cap,
        total_revenue, currency.
    """
    logger.info("Fetching company info for %s", ticker)
    stock = yf.Ticker(ticker)

    try:
        info = stock.info
    except Exception as exc:
        logger.error("Failed to fetch info for %s: %s", ticker, exc)
        return {"ticker": ticker}

    return {
        "ticker": ticker,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "total_revenue": info.get("totalRevenue"),
        "currency": info.get("currency"),
        "name": info.get("longName") or info.get("shortName"),
    }


def build_market_snapshot(tickers: list[str]) -> pd.DataFrame:
    """Build a combined market-data DataFrame for multiple tickers.

    Useful for batch ingestion and cross-validation against SEC data.

    Args:
        tickers: List of ticker symbols.

    Returns:
        Concatenated DataFrame of OHLCV + market cap for all tickers.
    """
    logger.info("Building market snapshot for %d tickers", len(tickers))
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            df = get_market_data(ticker)
            if not df.empty:
                frames.append(df)
        except Exception as exc:
            logger.error("Skipping %s due to error: %s", ticker, exc)

    if not frames:
        logger.warning("No market data retrieved for any ticker")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "Market snapshot: %d total rows across %d tickers",
        len(combined),
        combined["ticker"].nunique(),
    )
    return combined

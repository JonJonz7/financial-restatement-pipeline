"""
Core restatement detection logic.

Queries the DuckDB warehouse to find cases where a company reported
different values for the same metric and period across different filing
dates — the hallmark of a financial restatement. Also performs
cross-source anomaly detection between SEC filings and market data.
"""

import logging

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Restatement detection
# ---------------------------------------------------------------------------

_RESTATEMENT_SQL = """
WITH ranked AS (
    SELECT
        cik,
        metric,
        period_end,
        value,
        filed_date,
        accession_number,
        form,
        ROW_NUMBER() OVER (
            PARTITION BY cik, metric, period_end
            ORDER BY filed_date ASC
        ) AS filing_seq,
        COUNT(*) OVER (
            PARTITION BY cik, metric, period_end
        ) AS filing_count
    FROM bronze.raw_financial_facts
    WHERE value IS NOT NULL
      AND period_end IS NOT NULL
      AND filed_date IS NOT NULL
),
-- Keep only metric/period combos that were filed more than once
-- with different values (i.e. a restatement occurred).
first_and_last AS (
    SELECT
        r1.cik,
        r1.metric,
        r1.period_end,
        r1.value            AS original_value,
        r1.filed_date       AS original_filing_date,
        r2.value            AS restated_value,
        r2.filed_date       AS restatement_filing_date,
        r2.accession_number AS restatement_accession
    FROM ranked r1
    JOIN ranked r2
      ON  r1.cik        = r2.cik
      AND r1.metric     = r2.metric
      AND r1.period_end = r2.period_end
      AND r1.filing_seq = 1
      AND r2.filing_seq = r2.filing_count   -- latest filing
      AND r2.filing_count > 1
    WHERE r1.value <> r2.value
)
SELECT
    cik,
    metric,
    period_end,
    original_value,
    restated_value,
    original_filing_date,
    restatement_filing_date,
    ABS(restated_value - original_value) AS absolute_change,
    CASE
        WHEN original_value = 0 THEN NULL
        ELSE ABS((restated_value - original_value) / original_value) * 100
    END AS pct_change
FROM first_and_last
ORDER BY restatement_filing_date DESC, ABS(restated_value - original_value) DESC
"""


def detect_restatements(db_path: str = "warehouse.duckdb") -> pd.DataFrame:
    """Detect financial restatements from the warehouse.

    A restatement is defined as the same (cik, metric, period_end) being
    reported with a different ``value`` across two or more filing dates.

    Returns a DataFrame with severity classification:
        - MATERIAL: pct_change > 5% **or** absolute_change > 1 000 000
        - NOTABLE:  pct_change > 1%
        - MINOR:    everything else

    Args:
        db_path: Path to the DuckDB database file.

    Returns:
        DataFrame of detected restatements.
    """
    logger.info("Running restatement detection on %s", db_path)
    con = duckdb.connect(db_path, read_only=True)
    try:
        df = con.execute(_RESTATEMENT_SQL).fetchdf()
    finally:
        con.close()

    if df.empty:
        logger.info("No restatements detected")
        return df

    # Classify severity.
    def _severity(row: pd.Series) -> str:
        pct = row.get("pct_change")
        abs_chg = row.get("absolute_change", 0)
        if (pct is not None and pct > 5) or abs_chg > 1_000_000:
            return "MATERIAL"
        if pct is not None and pct > 1:
            return "NOTABLE"
        return "MINOR"

    df["severity"] = df.apply(_severity, axis=1)

    logger.info(
        "Detected %d restatements (MATERIAL=%d, NOTABLE=%d, MINOR=%d)",
        len(df),
        (df["severity"] == "MATERIAL").sum(),
        (df["severity"] == "NOTABLE").sum(),
        (df["severity"] == "MINOR").sum(),
    )
    return df


# ---------------------------------------------------------------------------
# Cross-source anomaly detection
# ---------------------------------------------------------------------------

_CROSS_SOURCE_SQL = """
WITH sec_revenue AS (
    SELECT
        cik,
        period_end,
        value AS sec_revenue,
        filed_date
    FROM bronze.raw_financial_facts
    WHERE metric IN ('Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
                     'SalesRevenueNet', 'RevenueFromContractWithCustomerIncludingAssessedTax')
      AND value IS NOT NULL
      AND period_end IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY cik, period_end ORDER BY filed_date DESC
    ) = 1
),
sec_assets AS (
    SELECT
        cik,
        period_end,
        value AS sec_total_assets,
        filed_date
    FROM bronze.raw_financial_facts
    WHERE metric = 'Assets'
      AND value IS NOT NULL
      AND period_end IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY cik, period_end ORDER BY filed_date DESC
    ) = 1
),
market AS (
    SELECT
        ticker,
        date AS market_date,
        close,
        market_cap
    FROM bronze.raw_market_data
    WHERE close IS NOT NULL
)
SELECT
    sr.cik,
    sr.period_end,
    sr.sec_revenue,
    sa.sec_total_assets,
    m.market_cap,
    m.close AS stock_close,
    m.market_date,
    CASE
        WHEN sr.sec_revenue > 0 AND m.market_cap > 0
        THEN m.market_cap / sr.sec_revenue
        ELSE NULL
    END AS price_to_revenue,
    CASE
        WHEN sa.sec_total_assets > 0 AND m.market_cap > 0
        THEN m.market_cap / sa.sec_total_assets
        ELSE NULL
    END AS price_to_assets
FROM sec_revenue sr
LEFT JOIN sec_assets sa
    ON sr.cik = sa.cik AND sr.period_end = sa.period_end
LEFT JOIN market m
    ON m.market_date = sr.period_end
WHERE m.market_cap IS NOT NULL
ORDER BY sr.period_end DESC
"""


def detect_cross_source_anomalies(
    db_path: str = "warehouse.duckdb",
) -> pd.DataFrame:
    """Compare SEC-reported financials against market data for anomalies.

    Flags cases where the price-to-revenue or price-to-assets ratio
    is an extreme outlier (beyond 3 standard deviations from the mean
    for that company), which may indicate data-quality issues or
    material misstatements.

    Args:
        db_path: Path to the DuckDB database file.

    Returns:
        DataFrame of flagged anomalies.
    """
    logger.info("Running cross-source anomaly detection on %s", db_path)
    con = duckdb.connect(db_path, read_only=True)
    try:
        df = con.execute(_CROSS_SOURCE_SQL).fetchdf()
    finally:
        con.close()

    if df.empty:
        logger.info("No cross-source data available for anomaly detection")
        return df

    # Flag outliers per CIK based on price-to-revenue.
    anomalies: list[pd.DataFrame] = []
    for cik, grp in df.groupby("cik"):
        for ratio_col in ("price_to_revenue", "price_to_assets"):
            series = grp[ratio_col].dropna()
            if len(series) < 3:
                continue
            mean = series.mean()
            std = series.std()
            if std == 0:
                continue
            z = ((grp[ratio_col] - mean) / std).abs()
            outlier_mask = z > 3
            if outlier_mask.any():
                flagged = grp[outlier_mask].copy()
                flagged["anomaly_type"] = f"{ratio_col}_outlier"
                flagged["z_score"] = z[outlier_mask]
                anomalies.append(flagged)

    if not anomalies:
        logger.info("No cross-source anomalies detected")
        return pd.DataFrame()

    result = pd.concat(anomalies, ignore_index=True)
    logger.info("Detected %d cross-source anomalies", len(result))
    return result

"""
End-to-end pipeline orchestrator.

Coordinates ingestion (SEC EDGAR + market data) and detection
(restatements + cross-source anomalies) into a single runnable flow.
"""

import logging
from typing import Any

import pandas as pd

from ingestion.config import DB_PATH
from ingestion.edgar_client import (
    extract_financial_metrics,
    get_company_facts,
    get_recent_filings,
)
from ingestion.loader import (
    init_warehouse,
    load_market_data,
    load_raw_filings,
    load_raw_financial_facts,
)
from ingestion.market_data import build_market_snapshot

from detection.anomaly_scorer import generate_alerts
from detection.restatement_detector import (
    detect_cross_source_anomalies,
    detect_restatements,
)

logger = logging.getLogger(__name__)


def run_ingestion(
    ciks: list[str],
    tickers: list[str],
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Run the ingestion step: pull SEC EDGAR data and market data, load to warehouse.

    Args:
        ciks: List of CIK strings to ingest.
        tickers: List of ticker symbols for market data.
        db_path: Path to the DuckDB warehouse.

    Returns:
        Summary dict with counts of records ingested.
    """
    logger.info("=== Starting ingestion for %d CIKs, %d tickers ===", len(ciks), len(tickers))
    init_warehouse(db_path)

    total_filings = 0
    total_facts = 0
    errors: list[str] = []

    # ------------------------------------------------------------------
    # SEC EDGAR ingestion
    # ------------------------------------------------------------------
    for cik in ciks:
        try:
            # Filing metadata (10-K + 10-Q).
            for form_type in ("10-K", "10-Q"):
                filings = get_recent_filings(cik, form_type=form_type)
                if filings:
                    load_raw_filings(filings, db_path)
                    total_filings += len(filings)

            # XBRL financial facts.
            facts = get_company_facts(cik)
            rows = extract_financial_metrics(facts)
            if rows:
                load_raw_financial_facts(rows, db_path)
                total_facts += len(rows)

        except Exception as exc:
            msg = f"CIK {cik}: {exc}"
            logger.error("Ingestion error — %s", msg)
            errors.append(msg)

    # ------------------------------------------------------------------
    # Market data ingestion
    # ------------------------------------------------------------------
    total_market_rows = 0
    if tickers:
        try:
            market_df = build_market_snapshot(tickers)
            if not market_df.empty:
                load_market_data(market_df, db_path)
                total_market_rows = len(market_df)
        except Exception as exc:
            msg = f"Market data: {exc}"
            logger.error("Ingestion error — %s", msg)
            errors.append(msg)

    summary = {
        "filings_loaded": total_filings,
        "facts_loaded": total_facts,
        "market_rows_loaded": total_market_rows,
        "errors": errors,
    }
    logger.info("=== Ingestion complete: %s ===", summary)
    return summary


def run_detection(
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Run the detection step: find restatements and anomalies.

    Args:
        db_path: Path to the DuckDB warehouse.

    Returns:
        Summary dict with detection results.
    """
    logger.info("=== Starting detection on %s ===", db_path)

    restatements: pd.DataFrame = detect_restatements(db_path)
    anomalies: pd.DataFrame = detect_cross_source_anomalies(db_path)
    alerts: list[dict] = generate_alerts(restatements, anomalies)

    summary = {
        "restatements_found": len(restatements),
        "cross_source_anomalies": len(anomalies),
        "total_alerts": len(alerts),
        "critical_alerts": sum(
            1 for a in alerts if a.get("severity_score", 0) >= 70
        ),
        "alerts": alerts,
        "restatements_df": restatements,
        "anomalies_df": anomalies,
    }

    logger.info(
        "=== Detection complete: %d restatements, %d anomalies, %d alerts (%d critical) ===",
        summary["restatements_found"],
        summary["cross_source_anomalies"],
        summary["total_alerts"],
        summary["critical_alerts"],
    )
    return summary


def run_full_pipeline(
    ciks: list[str],
    tickers: list[str],
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    """Run the complete pipeline: ingestion then detection.

    Args:
        ciks: List of CIK strings to ingest.
        tickers: List of ticker symbols for market data.
        db_path: Path to the DuckDB warehouse.

    Returns:
        Combined summary dict.
    """
    logger.info("========== FULL PIPELINE START ==========")

    ingestion_summary = run_ingestion(ciks, tickers, db_path)
    detection_summary = run_detection(db_path)

    combined = {
        "ingestion": ingestion_summary,
        "detection": {
            k: v
            for k, v in detection_summary.items()
            if k not in ("restatements_df", "anomalies_df")
        },
    }

    logger.info("========== FULL PIPELINE COMPLETE ==========")
    logger.info("Summary: %s", {
        k: v for k, v in combined.items() if k != "detection" or not isinstance(v, dict) or "alerts" not in v
    })
    return combined

"""
Anomaly scoring and alert generation.

Takes restatement and cross-source anomaly DataFrames and produces a
prioritised alert feed with severity scores and recommended actions.
"""

import logging
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger(__name__)

# Metrics that receive higher severity weight because they directly
# affect investor decisions.
_HIGH_WEIGHT_METRICS: set[str] = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "NetIncomeLoss",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
    "OperatingIncomeLoss",
    "GrossProfit",
}


def score_anomaly(row: dict) -> dict:
    """Score a single restatement or anomaly row.

    Produces:
        - severity_score (0-100)
        - risk_factors: list of human-readable reasons
        - recommended_action: string

    Args:
        row: Dict representing one restatement or anomaly record.

    Returns:
        Enriched dict with scoring fields added.
    """
    score: float = 0.0
    risk_factors: list[str] = []

    # --- Factor 1: Magnitude of percentage change ---
    pct_change = row.get("pct_change")
    if pct_change is not None:
        if pct_change > 20:
            score += 35
            risk_factors.append(f"Very large percentage change ({pct_change:.1f}%)")
        elif pct_change > 10:
            score += 25
            risk_factors.append(f"Large percentage change ({pct_change:.1f}%)")
        elif pct_change > 5:
            score += 18
            risk_factors.append(f"Material percentage change ({pct_change:.1f}%)")
        elif pct_change > 1:
            score += 10
            risk_factors.append(f"Notable percentage change ({pct_change:.1f}%)")
        else:
            score += 3

    # --- Factor 2: Absolute dollar magnitude ---
    absolute_change = row.get("absolute_change", 0)
    if absolute_change > 1_000_000_000:
        score += 25
        risk_factors.append(f"Billion-dollar absolute change (${absolute_change:,.0f})")
    elif absolute_change > 100_000_000:
        score += 18
        risk_factors.append(f"Hundred-million absolute change (${absolute_change:,.0f})")
    elif absolute_change > 1_000_000:
        score += 12
        risk_factors.append(f"Million-dollar absolute change (${absolute_change:,.0f})")
    elif absolute_change > 100_000:
        score += 5

    # --- Factor 3: Metric importance ---
    metric = row.get("metric", "")
    if metric in _HIGH_WEIGHT_METRICS:
        score += 15
        risk_factors.append(f"High-importance metric ({metric})")

    # --- Factor 4: Recency ---
    restatement_date = row.get("restatement_filing_date") or row.get("filed_date")
    if restatement_date is not None:
        try:
            if isinstance(restatement_date, str):
                rd = datetime.strptime(restatement_date, "%Y-%m-%d").date()
            elif isinstance(restatement_date, datetime):
                rd = restatement_date.date()
            elif isinstance(restatement_date, date):
                rd = restatement_date
            else:
                rd = None

            if rd is not None:
                days_ago = (date.today() - rd).days
                if days_ago < 90:
                    score += 10
                    risk_factors.append("Restated within the last 90 days")
                elif days_ago < 365:
                    score += 5
                    risk_factors.append("Restated within the last year")
        except (ValueError, TypeError):
            pass

    # --- Factor 5: Severity classification (if already present) ---
    severity = row.get("severity", "")
    if severity == "MATERIAL":
        score += 10
        risk_factors.append("Classified as MATERIAL")

    # --- Factor 6: Cross-source anomaly z-score ---
    z_score = row.get("z_score")
    if z_score is not None:
        if z_score > 5:
            score += 20
            risk_factors.append(f"Extreme cross-source outlier (z={z_score:.1f})")
        elif z_score > 3:
            score += 12
            risk_factors.append(f"Cross-source outlier (z={z_score:.1f})")

    # Clamp to [0, 100].
    severity_score = int(min(max(score, 0), 100))

    # Determine recommended action.
    if severity_score >= 70:
        recommended_action = "IMMEDIATE REVIEW: Escalate to compliance. Possible material misstatement."
    elif severity_score >= 50:
        recommended_action = "HIGH PRIORITY: Investigate filing differences and compare to peer group."
    elif severity_score >= 30:
        recommended_action = "MONITOR: Flag for next review cycle. Track for repeat occurrences."
    else:
        recommended_action = "LOW PRIORITY: Log and archive. No immediate action required."

    return {
        **row,
        "severity_score": severity_score,
        "risk_factors": risk_factors,
        "recommended_action": recommended_action,
    }


def generate_alerts(
    restatements: pd.DataFrame,
    anomalies: pd.DataFrame,
) -> list[dict]:
    """Produce a prioritised alert feed from restatements and anomalies.

    Args:
        restatements: DataFrame from
            :func:`restatement_detector.detect_restatements`.
        anomalies: DataFrame from
            :func:`restatement_detector.detect_cross_source_anomalies`.

    Returns:
        List of alert dicts sorted by severity_score descending.
    """
    alerts: list[dict] = []

    # Score restatements.
    if restatements is not None and not restatements.empty:
        for _, row in restatements.iterrows():
            alert = score_anomaly(row.to_dict())
            alert["alert_type"] = "RESTATEMENT"
            alerts.append(alert)

    # Score cross-source anomalies.
    if anomalies is not None and not anomalies.empty:
        for _, row in anomalies.iterrows():
            alert = score_anomaly(row.to_dict())
            alert["alert_type"] = "CROSS_SOURCE_ANOMALY"
            alerts.append(alert)

    # Sort by severity (highest first).
    alerts.sort(key=lambda a: a.get("severity_score", 0), reverse=True)

    logger.info(
        "Generated %d alerts (%d restatement, %d cross-source)",
        len(alerts),
        sum(1 for a in alerts if a["alert_type"] == "RESTATEMENT"),
        sum(1 for a in alerts if a["alert_type"] == "CROSS_SOURCE_ANOMALY"),
    )
    return alerts

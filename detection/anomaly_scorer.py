"""
Anomaly prioritisation: turn gold.fct_anomalies into a ranked alert queue.

dbt decides WHAT is an anomaly and how material it is. This module decides
what a reviewer should look at FIRST, with a transparent points system
(every point comes with a human-readable reason) and writes gold.alerts plus
a markdown report.
"""

import logging
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# Metrics investors act on directly get extra weight.
HIGH_WEIGHT_METRICS: set[str] = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "NetIncomeLoss",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
    "OperatingIncomeLoss",
    "GrossProfit",
    "Revenue (quarter)",
}

# Base points by anomaly type: an internally inconsistent filing is worse
# than a valuation that merely looks unusual.
TYPE_POINTS: dict[str, int] = {
    "RESTATEMENT": 0,
    "BALANCE_SHEET_BREAK": 25,
    "SCALE_ERROR": 30,
    "VALUATION_OUTLIER": 10,
}

ACTIONS = [
    (70, "IMMEDIATE REVIEW: escalate to compliance; possible material misstatement."),
    (
        50,
        "HIGH PRIORITY: compare the filings side by side and check the company's disclosures.",
    ),
    (30, "MONITOR: review in the next cycle; watch for repeats."),
    (0, "LOW PRIORITY: log and archive."),
]


def _as_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def score_anomaly(row: dict, as_of: date | None = None) -> dict:
    """Score one anomaly 0-100 and explain every point."""
    as_of = as_of or date.today()
    score = 0.0
    reasons: list[str] = []

    kind = row.get("anomaly_type") or "RESTATEMENT"
    if TYPE_POINTS.get(kind):
        score += TYPE_POINTS[kind]
        reasons.append(f"{kind.replace('_', ' ').title()} (+{TYPE_POINTS[kind]})")

    pct = row.get("pct_change")
    if pct is not None and not pd.isna(pct):
        pct = abs(float(pct))
        for limit, pts, label in (
            (20, 35, "Very large"),
            (10, 25, "Large"),
            (5, 18, "Material"),
            (1, 10, "Notable"),
        ):
            if pct > limit:
                score += pts
                reasons.append(f"{label} change: {pct:.1f}% (+{pts})")
                break
        else:
            score += 3

    if (row.get("unit") or "USD") == "USD":
        amount = abs(float(row.get("absolute_change") or 0) or 0)
        for limit, pts, label in (
            (1e9, 25, "Billion-dollar"),
            (1e8, 18, "Hundred-million"),
            (1e6, 12, "Million-dollar"),
            (1e5, 5, "Six-figure"),
        ):
            if amount > limit:
                score += pts
                reasons.append(f"{label} change: ${amount:,.0f} (+{pts})")
                break

    if row.get("metric") in HIGH_WEIGHT_METRICS:
        score += 15
        reasons.append(f"Key metric: {row.get('metric')} (+15)")

    detected = _as_date(row.get("detected_date") or row.get("restatement_filed_date"))
    if detected is not None:
        age = (as_of - detected).days
        if 0 <= age < 90:
            score += 10
            reasons.append("Detected in the last 90 days (+10)")
        elif 0 <= age < 365:
            score += 5
            reasons.append("Detected in the last year (+5)")

    if row.get("severity") == "MATERIAL":
        score += 10
        reasons.append("Classified MATERIAL (+10)")

    priority = int(min(max(round(score), 0), 100))
    action = next(text for threshold, text in ACTIONS if priority >= threshold)
    return {
        **row,
        "priority_score": priority,
        "risk_factors": reasons,
        "recommended_action": action,
    }


def score_anomalies(anomalies: pd.DataFrame, as_of: date | None = None) -> pd.DataFrame:
    """Score every row; highest priority first."""
    if anomalies is None or anomalies.empty:
        return pd.DataFrame(
            columns=["priority_score", "risk_factors", "recommended_action"]
        )
    scored = [score_anomaly(r, as_of) for r in anomalies.to_dict("records")]
    return pd.DataFrame(scored).sort_values(
        "priority_score", ascending=False, ignore_index=True
    )


def generate_alerts(
    restatements: pd.DataFrame, anomalies: pd.DataFrame, as_of: date | None = None
) -> list[dict]:
    """Backwards-compatible: score two frames together, return a list of dicts."""
    frames = [f for f in (restatements, anomalies) if f is not None and not f.empty]
    if not frames:
        return []
    return score_anomalies(pd.concat(frames, ignore_index=True), as_of).to_dict(
        "records"
    )


def write_alerts(
    db_path: str, report_path: Path | None = None, as_of: date | None = None
) -> pd.DataFrame:
    """Score gold.fct_anomalies into gold.alerts and an optional markdown report."""
    from detection.restatement_detector import all_anomalies

    alerts = score_anomalies(all_anomalies(db_path), as_of)
    if not alerts.empty:
        alerts["risk_factors"] = alerts["risk_factors"].map(" | ".join)
    con = duckdb.connect(db_path)
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold")
        con.register("_alerts", alerts)
        con.execute("CREATE OR REPLACE TABLE gold.alerts AS SELECT * FROM _alerts")
        con.unregister("_alerts")
    finally:
        con.close()
    if report_path is not None:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(render_report(alerts, as_of or date.today()))
    logger.info("Wrote %d alerts to gold.alerts", len(alerts))
    return alerts


def render_report(alerts: pd.DataFrame, as_of: date) -> str:
    lines = [f"# Alert report ({as_of.isoformat()})", ""]
    if alerts.empty:
        return "\n".join(lines + ["No anomalies detected."]) + "\n"
    counts = alerts["anomaly_type"].value_counts().to_dict()
    lines += [
        f"{len(alerts)} alerts: " + ", ".join(f"{v} {k}" for k, v in counts.items()),
        "",
        "| Priority | Company | Type | Metric | Period end | Reported | Expected / prior | Change | Action |",
        "|---:|---|---|---|---|---:|---:|---:|---|",
    ]
    for r in alerts.to_dict("records"):

        def money(v):
            return "" if v is None or pd.isna(v) else f"{v:,.0f}"

        pct = r.get("pct_change")
        lines.append(
            f"| {r['priority_score']} | {r.get('ticker') or r['cik']} | {r['anomaly_type']} | "
            f"{r['metric']} | {str(r['period_end'])[:10]} | {money(r.get('actual_value'))} | "
            f"{money(r.get('expected_value'))} | "
            f"{'' if pct is None or pd.isna(pct) else f'{pct:+.2f}%'} | "
            f"{r['recommended_action'].split(':')[0]} |"
        )
    lines += ["", "Why each alert scored what it did:", ""]
    for r in alerts.to_dict("records"):
        lines.append(
            f"- **{r.get('ticker') or r['cik']} {r['metric']} {str(r['period_end'])[:10]}** "
            f"({r['priority_score']}): {r['risk_factors']}"
        )
    return "\n".join(lines) + "\n"

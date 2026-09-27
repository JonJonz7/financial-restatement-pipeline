"""
Tests for detection/anomaly_scorer.py.
"""

import pandas as pd
import pytest

from detection.anomaly_scorer import generate_alerts, score_anomaly


# ---------------------------------------------------------------------------
# score_anomaly
# ---------------------------------------------------------------------------


def test_score_anomaly_returns_valid_score():
    """Severity score must be an integer between 0 and 100."""
    row = {
        "metric": "Assets",
        "pct_change": 2.5,
        "absolute_change": 500_000,
        "severity": "NOTABLE",
    }
    result = score_anomaly(row)

    assert "severity_score" in result
    assert isinstance(result["severity_score"], int)
    assert 0 <= result["severity_score"] <= 100


def test_high_severity_restatement_scores_high():
    """Revenue restatement with >10% change should score above 70."""
    row = {
        "metric": "Revenues",
        "pct_change": 15.0,
        "absolute_change": 5_000_000_000,
        "severity": "MATERIAL",
        "restatement_filing_date": "2026-08-01",
    }
    result = score_anomaly(row)

    assert result["severity_score"] > 70
    assert "IMMEDIATE REVIEW" in result["recommended_action"]


def test_minor_restatement_scores_low():
    """Non-revenue metric with <1% change should score below 30."""
    row = {
        "metric": "AccountsPayable",
        "pct_change": 0.3,
        "absolute_change": 50_000,
        "severity": "MINOR",
    }
    result = score_anomaly(row)

    assert result["severity_score"] < 30
    assert "LOW PRIORITY" in result["recommended_action"]


def test_generate_alerts_sorted_by_severity():
    """Alerts must be sorted highest severity_score first."""
    restatements = pd.DataFrame([
        {
            "cik": "0000320193",
            "metric": "AccountsPayable",
            "pct_change": 0.5,
            "absolute_change": 10_000,
            "severity": "MINOR",
            "period_end": "2023-09-30",
            "original_value": 100_000,
            "restated_value": 100_500,
            "original_filing_date": "2023-11-03",
            "restatement_filing_date": "2024-02-15",
        },
        {
            "cik": "0000320193",
            "metric": "Revenues",
            "pct_change": 25.0,
            "absolute_change": 50_000_000_000,
            "severity": "MATERIAL",
            "period_end": "2023-09-30",
            "original_value": 200_000_000_000,
            "restated_value": 250_000_000_000,
            "original_filing_date": "2023-11-03",
            "restatement_filing_date": "2024-02-15",
        },
        {
            "cik": "0000789019",
            "metric": "NetIncomeLoss",
            "pct_change": 3.0,
            "absolute_change": 2_000_000_000,
            "severity": "NOTABLE",
            "period_end": "2023-06-30",
            "original_value": 66_000_000_000,
            "restated_value": 68_000_000_000,
            "original_filing_date": "2023-07-25",
            "restatement_filing_date": "2023-12-01",
        },
    ])
    anomalies = pd.DataFrame()

    alerts = generate_alerts(restatements, anomalies)

    assert len(alerts) == 3
    scores = [a["severity_score"] for a in alerts]
    assert scores == sorted(scores, reverse=True), "Alerts not sorted by severity_score descending"


def test_generate_alerts_includes_risk_factors():
    """Each alert should contain a non-empty risk_factors list."""
    restatements = pd.DataFrame([
        {
            "cik": "0000320193",
            "metric": "Revenues",
            "pct_change": 12.0,
            "absolute_change": 40_000_000_000,
            "severity": "MATERIAL",
            "period_end": "2023-09-30",
            "original_value": 350_000_000_000,
            "restated_value": 392_000_000_000,
            "original_filing_date": "2023-11-03",
            "restatement_filing_date": "2024-02-15",
        },
    ])
    anomalies = pd.DataFrame()

    alerts = generate_alerts(restatements, anomalies)

    assert len(alerts) == 1
    assert "risk_factors" in alerts[0]
    assert isinstance(alerts[0]["risk_factors"], list)
    assert len(alerts[0]["risk_factors"]) > 0


def test_recommended_action_for_material():
    """MATERIAL-severity restatements should recommend immediate review."""
    row = {
        "metric": "Revenues",
        "pct_change": 25.0,
        "absolute_change": 10_000_000_000,
        "severity": "MATERIAL",
        "restatement_filing_date": "2026-08-01",
    }
    result = score_anomaly(row)

    assert "IMMEDIATE REVIEW" in result["recommended_action"]
    assert "compliance" in result["recommended_action"].lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_score_anomaly_with_zero_pct_change():
    """A row with pct_change of 0 should not crash and should score low."""
    row = {
        "metric": "CashAndCashEquivalents",
        "pct_change": 0.0,
        "absolute_change": 0,
        "severity": "MINOR",
    }
    result = score_anomaly(row)
    assert result["severity_score"] >= 0


def test_score_anomaly_with_none_pct_change():
    """A row with pct_change=None (division by zero case) should handle gracefully."""
    row = {
        "metric": "SomeMetric",
        "pct_change": None,
        "absolute_change": 1_000,
    }
    result = score_anomaly(row)
    assert isinstance(result["severity_score"], int)
    assert 0 <= result["severity_score"] <= 100


def test_generate_alerts_with_both_sources():
    """Alerts should combine restatements and cross-source anomalies."""
    restatements = pd.DataFrame([
        {
            "cik": "0000320193",
            "metric": "Revenues",
            "pct_change": 8.0,
            "absolute_change": 30_000_000_000,
            "severity": "MATERIAL",
            "period_end": "2023-09-30",
            "original_value": 383285000000,
            "restated_value": 413285000000,
            "original_filing_date": "2023-11-03",
            "restatement_filing_date": "2024-02-15",
        },
    ])
    anomalies = pd.DataFrame([
        {
            "cik": "0000789019",
            "metric": "price_to_revenue",
            "z_score": 4.5,
            "period_end": "2023-06-30",
            "market_date": "2023-06-30",
        },
    ])

    alerts = generate_alerts(restatements, anomalies)

    assert len(alerts) == 2
    alert_types = {a["alert_type"] for a in alerts}
    assert "RESTATEMENT" in alert_types
    assert "CROSS_SOURCE_ANOMALY" in alert_types


def test_generate_alerts_empty_inputs():
    """Empty DataFrames should produce an empty alert list."""
    alerts = generate_alerts(pd.DataFrame(), pd.DataFrame())
    assert alerts == []

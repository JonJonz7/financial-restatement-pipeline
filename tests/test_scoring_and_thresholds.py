from datetime import date

import pandas as pd

from detection.anomaly_scorer import generate_alerts, score_anomaly, score_anomalies
from detection.thresholds import classify_severity, load_thresholds

AS_OF = date(2024, 6, 1)


def test_thresholds_come_from_the_dbt_seed():
    assert [t["severity"] for t in load_thresholds()] == [
        "MATERIAL",
        "NOTABLE",
        "MINOR",
    ]


def test_classify_severity_matches_policy():
    assert classify_severity(6.0, 10, "USD") == "MATERIAL"
    assert classify_severity(0.5, 2_500_000, "USD") == "MATERIAL"  # dollars alone
    assert classify_severity(2.0, 50, "USD") == "NOTABLE"
    assert classify_severity(0.2, 150_000, "USD") == "NOTABLE"
    assert classify_severity(0.2, 50, "USD") == "MINOR"
    assert (
        classify_severity(0.5, 2_500_000, "shares") == "MINOR"
    )  # shares aren't dollars
    assert classify_severity(None, None) == "MINOR"


def test_material_recent_revenue_restatement_scores_high():
    r = score_anomaly(
        {
            "anomaly_type": "RESTATEMENT",
            "metric": "Revenues",
            "pct_change": -25,
            "absolute_change": -2e9,
            "unit": "USD",
            "severity": "MATERIAL",
            "detected_date": "2024-05-10",
        },
        AS_OF,
    )
    assert r["priority_score"] == 95
    assert r["recommended_action"].startswith("IMMEDIATE")
    assert any("Revenues" in x for x in r["risk_factors"])


def test_tiny_old_change_scores_low():
    r = score_anomaly(
        {
            "anomaly_type": "RESTATEMENT",
            "metric": "OtherAssets",
            "pct_change": 0.1,
            "absolute_change": 500,
            "unit": "USD",
            "severity": "MINOR",
            "detected_date": "2019-01-01",
        },
        AS_OF,
    )
    assert r["priority_score"] == 3
    assert r["recommended_action"].startswith("LOW")


def test_share_counts_get_no_dollar_points():
    r = score_anomaly(
        {"metric": "X", "pct_change": 0.5, "absolute_change": 5e9, "unit": "shares"},
        AS_OF,
    )
    assert not any("$" in x for x in r["risk_factors"])


def test_score_anomalies_sorted_and_empty_safe():
    df = pd.DataFrame(
        [
            {"metric": "A", "pct_change": 0.1, "absolute_change": 1},
            {"metric": "Revenues", "pct_change": 30, "absolute_change": 1e9},
        ]
    )
    out = score_anomalies(df, AS_OF)
    assert list(out["priority_score"]) == sorted(out["priority_score"], reverse=True)
    assert score_anomalies(pd.DataFrame(), AS_OF).empty
    assert generate_alerts(pd.DataFrame(), None) == []

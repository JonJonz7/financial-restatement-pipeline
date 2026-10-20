"""
Materiality thresholds: the single source of truth for severity.

Both dbt (macros/severity.sql via the materiality_thresholds seed) and
Python read dbt_project/seeds/materiality_thresholds.csv, so a change to
the policy is one edit in one file, and SQL and Python can't disagree.
"""

import csv
from functools import lru_cache
from pathlib import Path

SEED = (
    Path(__file__).resolve().parent.parent
    / "dbt_project"
    / "seeds"
    / "materiality_thresholds.csv"
)


@lru_cache(maxsize=1)
def load_thresholds(path: Path = SEED) -> tuple[dict, ...]:
    """Thresholds ordered from most to least severe."""
    with open(path, newline="") as fh:
        rows = [
            {
                "severity": r["severity"],
                "rank": int(r["severity_rank"]),
                "min_pct": float(r["min_pct_change"]),
                "min_usd": float(r["min_absolute_usd"]),
            }
            for r in csv.DictReader(fh)
        ]
    return tuple(sorted(rows, key=lambda r: r["rank"], reverse=True))


def classify_severity(
    pct_change: float | None, absolute_change: float | None, unit: str = "USD"
) -> str:
    """MATERIAL / NOTABLE / MINOR for one change (same rule as macros/severity.sql)."""
    pct = abs(pct_change or 0.0)
    amount = abs(absolute_change or 0.0)
    for t in load_thresholds():
        if pct >= t["min_pct"]:
            return t["severity"]
        if unit == "USD" and t["min_usd"] > 0 and amount >= t["min_usd"]:
            return t["severity"]
    return "MINOR"

"""
Score everything dbt detected and write the alert queue.

    python -m detection.run [--db warehouse.duckdb] [--report reports/alerts.md]

Run after `dbt build`. Writes gold.alerts and a markdown report, and prints
a one-line summary. Exit code 0 unless the gold layer is missing.
"""

import argparse
import logging
import sys
from pathlib import Path

from detection.anomaly_scorer import write_alerts
from ingestion.config import DB_PATH, PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score anomalies into gold.alerts")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--report", default=str(PROJECT_ROOT / "reports" / "alerts.md"))
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    alerts = write_alerts(args.db, Path(args.report))
    if alerts.empty:
        print("No anomalies found (did dbt run?).")
        return 0
    critical = int((alerts["priority_score"] >= 70).sum())
    print(
        f"{len(alerts)} alerts, {critical} for immediate review. Report: {args.report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

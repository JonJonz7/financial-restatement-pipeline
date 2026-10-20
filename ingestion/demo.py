"""
Load the offline sample dataset (data/sample/) into bronze. No network.

    python -m ingestion.demo [--db warehouse.duckdb]

The sample JSON goes through exactly the same code as live data: it is
landed (gzipped + fingerprinted), parsed and loaded, with lineage rows in
bronze.ingestion_runs. Only the fetch step is skipped.
"""

import argparse
import json
import logging
import tempfile
import uuid
from pathlib import Path

import pandas as pd

from ingestion.config import DB_PATH, PROJECT_ROOT
from ingestion.loader import init_warehouse, load_market_data
from ingestion.pipeline import _process

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
logger = logging.getLogger(__name__)


def load_sample(
    db_path: str = DB_PATH,
    sample_dir: Path = SAMPLE_DIR,
    landing_dir: Path | None = None,
) -> dict:
    init_warehouse(db_path)
    landing_dir = Path(landing_dir or tempfile.mkdtemp(prefix="frp-landing-"))
    run_id = "demo-" + uuid.uuid4().hex[:8]
    totals = {"filings_loaded": 0, "facts_loaded": 0, "market_rows_loaded": 0}
    for source, key in (
        ("submissions", "filings_loaded"),
        ("companyfacts", "facts_loaded"),
    ):
        for path in sorted((sample_dir / source).glob("CIK*.json")):
            cik = path.stem.replace("CIK", "")
            payload = json.loads(path.read_text())
            totals[key] += _process(
                run_id, source, cik, db_path, landing_dir, payload=payload
            )
    prices = pd.read_csv(sample_dir / "market_prices.csv")
    totals["market_rows_loaded"] = load_market_data(prices, db_path)
    logger.info("Sample data loaded: %s", totals)
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(load_sample(args.db))


if __name__ == "__main__":
    main()

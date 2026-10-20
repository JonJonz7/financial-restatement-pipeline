"""
Ingestion orchestrator: SEC EDGAR + market prices -> landing zone -> bronze.

    python -m ingestion.pipeline                    # all watched companies (needs EDGAR_USER_AGENT)
    python -m ingestion.pipeline --tickers AAPL MSFT
    python -m ingestion.pipeline --no-market        # skip Yahoo Finance prices
    python -m ingestion.pipeline --replay           # rebuild bronze from the landing zone, no network

Each company is processed independently: one company failing (bad CIK,
network blip) is logged in bronze.ingestion_runs and the rest still load.
"""

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingestion import landing
from ingestion.config import DB_PATH, LANDING_DIR, WATCHED_COMPANIES
from ingestion.edgar_client import (
    _normalize_cik,
    extract_financial_metrics,
    get_company_facts,
    get_submissions,
    parse_company_profile,
    parse_filings,
)
from ingestion.loader import (
    init_warehouse,
    load_companies,
    load_market_data,
    load_raw_filings,
    load_raw_financial_facts,
    record_run,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load_submissions(payload: dict, db_path: str) -> int:
    """Parse one submissions document into raw_companies + raw_filings."""
    load_companies([parse_company_profile(payload)], db_path)
    return load_raw_filings(parse_filings(payload), db_path)


def load_companyfacts(payload: dict, db_path: str) -> int:
    """Parse one companyfacts document into raw_financial_facts."""
    return load_raw_financial_facts(extract_financial_metrics(payload), db_path)


_PARSERS = {"submissions": load_submissions, "companyfacts": load_companyfacts}
_FETCHERS = {"submissions": get_submissions, "companyfacts": get_company_facts}


def _process(
    run_id: str,
    source: str,
    cik: str,
    db_path: str,
    landing_dir: Path,
    payload: dict | None = None,
    path: Path | None = None,
) -> int:
    """Fetch (or read) one document, land it, load it, and record lineage."""
    started = _now()
    sha = None
    try:
        if path is not None:  # replay from the landing zone
            payload, sha = landing.read(path)
        else:
            payload = payload if payload is not None else _FETCHERS[source](cik)
            path, sha = landing.land(source, cik, payload, landing_dir)
        rows = _PARSERS[source](payload, db_path)
        record_run(
            db_path,
            run_id=run_id,
            source=source,
            cik=cik,
            landed_path=str(path),
            sha256=sha,
            rows_loaded=rows,
            status="ok",
            started_at=started,
            finished_at=_now(),
        )
        return rows
    except Exception as exc:  # noqa: BLE001 - one bad company must not stop the run
        logger.error("%s for CIK %s failed: %s", source, cik, exc)
        record_run(
            db_path,
            run_id=run_id,
            source=source,
            cik=cik,
            landed_path=str(path) if path else None,
            sha256=sha,
            rows_loaded=0,
            status="error",
            error=str(exc)[:500],
            started_at=started,
            finished_at=_now(),
        )
        raise


def run_ingestion(
    ciks: list[str],
    tickers: list[str],
    db_path: str = DB_PATH,
    landing_dir: Path = LANDING_DIR,
) -> dict[str, Any]:
    """Pull EDGAR filings + facts for each CIK and prices for each ticker into bronze."""
    run_id = uuid.uuid4().hex[:12]
    logger.info(
        "=== Ingestion %s: %d CIKs, %d tickers ===", run_id, len(ciks), len(tickers)
    )
    init_warehouse(db_path)
    totals = {"filings_loaded": 0, "facts_loaded": 0, "market_rows_loaded": 0}
    errors: list[str] = []

    for cik in (_normalize_cik(c) for c in ciks):
        try:
            totals["filings_loaded"] += _process(
                run_id, "submissions", cik, db_path, landing_dir
            )
            totals["facts_loaded"] += _process(
                run_id, "companyfacts", cik, db_path, landing_dir
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"CIK {cik}: {exc}")

    if tickers:
        try:
            from ingestion.market_data import build_market_snapshot

            totals["market_rows_loaded"] = load_market_data(
                build_market_snapshot(tickers), db_path
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Market data failed: %s", exc)
            errors.append(f"Market data: {exc}")

    summary = {"run_id": run_id, **totals, "errors": errors}
    logger.info("=== Ingestion complete: %s ===", summary)
    return summary


def replay(db_path: str = DB_PATH, landing_dir: Path = LANDING_DIR) -> dict[str, Any]:
    """Rebuild bronze from the newest landed file per company. No network calls."""
    run_id = "replay-" + uuid.uuid4().hex[:8]
    init_warehouse(db_path)
    totals = {"filings_loaded": 0, "facts_loaded": 0}
    for source, key in (
        ("submissions", "filings_loaded"),
        ("companyfacts", "facts_loaded"),
    ):
        for cik, path in landing.latest(source, landing_dir).items():
            totals[key] += _process(
                run_id, source, cik, db_path, landing_dir, path=path
            )
    logger.info("=== Replay complete: %s ===", totals)
    return {"run_id": run_id, **totals}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest SEC EDGAR + market data into bronze"
    )
    parser.add_argument(
        "--tickers", nargs="*", help="Subset of watched tickers (default: all)"
    )
    parser.add_argument(
        "--no-market", action="store_true", help="Skip Yahoo Finance prices"
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Rebuild bronze from the landing zone instead of calling the API",
    )
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if args.replay:
        replay(args.db)
        return 0

    by_ticker = {t: c for c, t in WATCHED_COMPANIES.items()}
    tickers = args.tickers or list(by_ticker)
    unknown = [t for t in tickers if t not in by_ticker]
    if unknown:
        parser.error(f"Not in WATCHED_COMPANIES: {', '.join(unknown)}")
    summary = run_ingestion(
        [by_ticker[t] for t in tickers], [] if args.no_market else tickers, args.db
    )
    print({k: v for k, v in summary.items() if k != "errors"})
    for err in summary["errors"]:
        print("ERROR", err, file=sys.stderr)
    # Partial failure is still failure: the scheduler must see it.
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())

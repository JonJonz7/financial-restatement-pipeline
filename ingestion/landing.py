"""
Landing zone: immutable copies of every raw API response.

Raw JSON is written gzipped to ``<LANDING_DIR>/<source>/<cik>/<YYYY-MM-DD>.json.gz``
before any parsing happens. Two reasons:

1. Replay: if a parser bug is found, bronze is rebuilt from these files
   instead of re-downloading (and without hitting the SEC rate limit).
2. Evidence: the SHA-256 of each file is recorded in bronze.ingestion_runs,
   so any number in the warehouse traces back to the exact bytes received.
"""

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

from ingestion.config import LANDING_DIR


def land(
    source: str,
    cik: str,
    payload: dict,
    landing_dir: Path = LANDING_DIR,
    as_of: date | None = None,
) -> tuple[Path, str]:
    """Write one raw payload; return (path, sha256 of the uncompressed bytes).

    Writing the same day twice overwrites that day's file, so a re-run is idempotent.
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    day = (as_of or date.today()).isoformat()
    path = Path(landing_dir) / source / cik / f"{day}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wb") as fh:
        fh.write(raw)
    tmp.replace(path)  # atomic: readers never see a half-written file
    return path, digest


def read(path: Path) -> tuple[dict, str]:
    """Read one landed file; return (payload, sha256)."""
    with gzip.open(path, "rb") as fh:
        raw = fh.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def latest(source: str, landing_dir: Path = LANDING_DIR) -> dict[str, Path]:
    """Newest landed file per CIK for one source: {cik: path}."""
    base = Path(landing_dir) / source
    if not base.exists():
        return {}
    out: dict[str, Path] = {}
    for cik_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        files = sorted(cik_dir.glob("*.json.gz"))
        if files:
            out[cik_dir.name] = files[-1]
    return out

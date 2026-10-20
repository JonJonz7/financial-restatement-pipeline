"""
Execute data contracts against the warehouse.

    python -m quality.check_contracts [--db warehouse.duckdb] [--no-freshness]

For every YAML file in quality/data_contracts/: checks columns exist with the
promised type and nullability, uniqueness, patterns, allowed values, row-level
rules, volume and freshness. Prints one line per check. Exit code 1 if any
"error"-level check fails, so a scheduler or CI stops the pipeline.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import yaml

from ingestion.config import DB_PATH

CONTRACT_DIR = Path(__file__).resolve().parent / "data_contracts"


@dataclass
class Result:
    check: str
    passed: bool
    level: str
    detail: str


def _q(con, sql: str):
    return con.execute(sql).fetchone()[0]


def check_contract(
    con: duckdb.DuckDBPyConnection, contract: dict, freshness: bool = True
) -> list[Result]:
    table = contract["table"]
    schema, name = table.split(".")
    out: list[Result] = []
    actual = {
        r[0]: r[1].upper()
        for r in con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = ? and table_name = ?",
            [schema, name],
        ).fetchall()
    }
    if not actual:
        return [Result(f"{table} exists", False, "error", "table not found")]
    total = _q(con, f"select count(*) from {table}")

    for col in contract.get("columns", []):
        c = col["name"]
        if c not in actual:
            out.append(Result(f"{c}: exists", False, "error", "column missing"))
            continue
        if not actual[c].startswith(col["type"].upper()):
            out.append(
                Result(f"{c}: type", False, "error", f"{actual[c]} != {col['type']}")
            )
        if not col.get("nullable", True):
            n = _q(con, f"select count(*) from {table} where {c} is null")
            out.append(Result(f"{c}: not null", n == 0, "error", f"{n} nulls"))
        if col.get("unique"):
            d = _q(con, f"select count(*) - count(distinct {c}) from {table}")
            out.append(Result(f"{c}: unique", d == 0, "error", f"{d} duplicates"))
        if col.get("pattern"):
            n = _q(
                con,
                f"select count(*) from {table} where {c} is not null "
                f"and not regexp_full_match({c}, '{col['pattern']}')",
            )
            out.append(
                Result(f"{c}: pattern", n == 0, "error", f"{n} rows don't match")
            )
        if col.get("allowed_values"):
            vals = ", ".join(f"'{v}'" for v in col["allowed_values"])
            n = _q(con, f"select count(*) from {table} where {c} not in ({vals})")
            out.append(
                Result(f"{c}: allowed values", n == 0, "error", f"{n} rows outside set")
            )

    for rule in contract.get("rules", []):
        bad = _q(con, f"select count(*) from {table} where not ({rule['condition']})")
        rate = bad / total if total else 0.0
        limit = rule.get("max_failure_rate", 0.0)
        out.append(
            Result(
                f"rule {rule['name']}",
                rate <= limit,
                rule.get("level", "error"),
                f"{bad} failing rows ({rate:.2%}, allowed {limit:.2%})",
            )
        )

    vol = contract.get("volume", {})
    if "min_rows" in vol:
        out.append(
            Result(
                "volume",
                total >= vol["min_rows"],
                "error",
                f"{total} rows (min {vol['min_rows']})",
            )
        )

    fr = contract.get("freshness")
    if fr and freshness:
        age = _q(
            con,
            f"select date_diff('hour', max({fr['column']}), "
            f"timezone('UTC', current_timestamp)) from {table}",
        )
        out.append(
            Result(
                "freshness",
                age is not None and age <= fr["max_age_hours"],
                "error",
                f"newest row is {age}h old (max {fr['max_age_hours']}h)",
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run data contracts")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument(
        "--no-freshness",
        action="store_true",
        help="Skip freshness (for replaying old data)",
    )
    args = parser.parse_args(argv)
    con = duckdb.connect(args.db, read_only=True)
    failed_errors = 0
    try:
        for path in sorted(CONTRACT_DIR.glob("*.yml")):
            contract = yaml.safe_load(path.read_text())
            print(f"== {path.name} -> {contract['table']}")
            for r in check_contract(con, contract, freshness=not args.no_freshness):
                mark = (
                    "PASS" if r.passed else ("FAIL" if r.level == "error" else "WARN")
                )
                print(f"  {mark:4}  {r.check:28} {r.detail}")
                failed_errors += (not r.passed) and r.level == "error"
    finally:
        con.close()
    print("Contracts:", "FAILED" if failed_errors else "passed")
    return 1 if failed_errors else 0


if __name__ == "__main__":
    sys.exit(main())

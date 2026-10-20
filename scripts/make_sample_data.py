"""
Generate the offline sample dataset in data/sample/ (committed to the repo).

Three FICTIONAL companies, written in the exact JSON shape of the SEC EDGAR
`submissions` and `companyfacts` endpoints, plus synthetic daily prices.
They exist so the whole pipeline runs without network access (CI, demos,
`make demo`) and so every detection rule has a known, planted case:

  Northwind Devices (NWDV)   10-K/A restates FY2023 revenue and net income down 6%  -> MATERIAL
                             Q4 (3-month) and FY (12-month) revenue share period_end 2023-12-31
                             -> must NOT be flagged (different period_start = different fact)
  Harbor Logistics (HRBL)    FY2022 revenue recast -0.5% and operating income -2% in the
                             FY2023 10-K (no amendment) -> MINOR / NOTABLE, type RECAST
                             Balance sheet 2023-12-31: Assets != Liabilities + Equity
  Cedar Ridge Health (CDRH)  One quarter's revenue tagged in thousands instead of dollars
                             -> price-to-sales outlier

Run:  python scripts/make_sample_data.py
"""

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"

COMPANIES = [
    {
        "cik": "0000900001",
        "name": "Northwind Devices Inc (FICTIONAL)",
        "ticker": "NWDV",
        "sic": "3571",
        "sic_description": "Electronic Computers",
        "q_rev": 230e6,
        "growth": 0.02,
        "margin": 0.18,
        "shares": 400e6,
        "price": 42.0,
    },
    {
        "cik": "0000900002",
        "name": "Harbor Logistics Corp (FICTIONAL)",
        "ticker": "HRBL",
        "sic": "4213",
        "sic_description": "Trucking (No Local)",
        "q_rev": 120e6,
        "growth": 0.01,
        "margin": 0.07,
        "shares": 150e6,
        "price": 18.0,
    },
    {
        "cik": "0000900003",
        "name": "Cedar Ridge Health Systems (FICTIONAL)",
        "ticker": "CDRH",
        "sic": "8062",
        "sic_description": "Hospitals",
        "q_rev": 310e6,
        "growth": 0.015,
        "margin": 0.05,
        "shares": 220e6,
        "price": 27.0,
    },
]
YEARS = (2021, 2022, 2023)
QUARTERS = {
    1: ("01-01", "03-31"),
    2: ("04-01", "06-30"),
    3: ("07-01", "09-30"),
    4: ("10-01", "12-31"),
}
# filing date of the report covering (year, quarter); Q4 is the 10-K
FILED = {1: "05-05", 2: "08-04", 3: "11-03", 4: "02-20"}


def quarter_revenue(c: dict, year: int, q: int) -> float:
    n = (year - YEARS[0]) * 4 + (q - 1)
    return round(c["q_rev"] * (1 + c["growth"]) ** n, -3)


def accn(cik: str, year: int, seq: int) -> str:
    return f"{cik}-{str(year)[2:]}-{seq:06d}"


def build(c: dict) -> tuple[dict, dict]:
    cik = c["cik"]
    facts: dict[str, dict] = {}
    filings: list[dict] = []

    def add(taxonomy: str, metric: str, unit: str, entry: dict) -> None:
        bucket = facts.setdefault(taxonomy, {}).setdefault(
            metric, {"label": metric, "description": "", "units": {}}
        )
        bucket["units"].setdefault(unit, []).append(entry)

    seq = 0
    for year in YEARS:
        for q in (1, 2, 3, 4):
            seq += 1
            form = "10-K" if q == 4 else "10-Q"
            filed_year = year + 1 if q == 4 else year
            filed = f"{filed_year}-{FILED[q]}"
            a = accn(cik, filed_year, seq)
            period_end = f"{year}-{QUARTERS[q][1]}"
            filings.append(
                {
                    "accessionNumber": a,
                    "form": form,
                    "filingDate": filed,
                    "reportDate": period_end,
                    "primaryDocument": f"{c['ticker'].lower()}-{period_end}.htm",
                }
            )
            fp = "FY" if q == 4 else f"Q{q}"
            base = {"accn": a, "fy": year, "fp": fp, "form": form, "filed": filed}

            # 3-month revenue for this quarter, and the same quarter last year as a comparative
            for y in (year, year - 1):
                if y < YEARS[0]:
                    continue
                if q == 4 and c["ticker"] != "NWDV":
                    continue  # most filers don't tag Q4 separately; Northwind does
                val = quarter_revenue(c, y, q)
                if c["ticker"] == "CDRH" and (y, q) == (2022, 3):
                    val = round(val / 1000, 0)  # planted: tagged in thousands
                add(
                    "us-gaap",
                    "Revenues",
                    "USD",
                    {
                        **base,
                        "start": f"{y}-{QUARTERS[q][0]}",
                        "end": f"{y}-{QUARTERS[q][1]}",
                        "val": val,
                    },
                )

            if q == 4:
                # 10-K: full-year revenue + net income for this year and two prior years
                for y in (year, year - 1, year - 2):
                    if y < YEARS[0]:
                        continue
                    rev = sum(quarter_revenue(c, y, k) for k in (1, 2, 3, 4))
                    op_inc = round(rev * c["margin"], -3)
                    if c["ticker"] == "HRBL" and y == 2022 and year == 2023:
                        rev = round(rev * 0.995, -3)  # planted recast, -0.5%
                        op_inc = round(op_inc * 0.98, -3)  # planted recast, -2%
                    span = {"start": f"{y}-01-01", "end": f"{y}-12-31"}
                    add("us-gaap", "Revenues", "USD", {**base, **span, "val": rev})
                    add(
                        "us-gaap",
                        "OperatingIncomeLoss",
                        "USD",
                        {**base, **span, "val": op_inc},
                    )
                    add(
                        "us-gaap",
                        "NetIncomeLoss",
                        "USD",
                        {**base, **span, "val": round(op_inc * 0.79, -3)},
                    )

            # Balance sheet (instant facts: no start date)
            assets = round(quarter_revenue(c, year, q) * 3.2, -3)
            liab_eq = assets
            if c["ticker"] == "HRBL" and (year, q) == (2023, 4):
                liab_eq = assets - 10_000_000  # planted: does not balance
            add("us-gaap", "Assets", "USD", {**base, "end": period_end, "val": assets})
            add(
                "us-gaap",
                "LiabilitiesAndStockholdersEquity",
                "USD",
                {**base, "end": period_end, "val": liab_eq},
            )
            # Cover page: shares outstanding, as of shortly before filing
            add(
                "dei",
                "EntityCommonStockSharesOutstanding",
                "shares",
                {**base, "end": filed, "val": round(c["shares"] * (1 - 0.002 * seq))},
            )

    if c["ticker"] == "NWDV":
        # planted: 10-K/A amends FY2023 revenue and net income down 6%
        seq += 1
        a = accn(cik, 2024, seq)
        filed = "2024-05-10"
        filings.append(
            {
                "accessionNumber": a,
                "form": "10-K/A",
                "filingDate": filed,
                "reportDate": "2023-12-31",
                "primaryDocument": "nwdv-10ka-2023.htm",
            }
        )
        base = {"accn": a, "fy": 2023, "fp": "FY", "form": "10-K/A", "filed": filed}
        rev = sum(quarter_revenue(c, 2023, k) for k in (1, 2, 3, 4))
        op_inc = round(rev * c["margin"], -3)
        span = {"start": "2023-01-01", "end": "2023-12-31"}
        add(
            "us-gaap", "Revenues", "USD", {**base, **span, "val": round(rev * 0.94, -3)}
        )
        add(
            "us-gaap",
            "NetIncomeLoss",
            "USD",
            {**base, **span, "val": round(op_inc * 0.79 * 0.94, -3)},
        )

    recent = {
        k: [f[k] for f in reversed(filings)]
        for k in (
            "accessionNumber",
            "form",
            "filingDate",
            "reportDate",
            "primaryDocument",
        )
    }
    submissions = {
        "cik": cik.lstrip("0"),
        "name": c["name"],
        "tickers": [c["ticker"]],
        "sic": c["sic"],
        "sicDescription": c["sic_description"],
        "fiscalYearEnd": "1231",
        "filings": {"recent": recent},
    }
    companyfacts = {"cik": int(cik), "entityName": c["name"], "facts": facts}
    return submissions, companyfacts


def prices(c: dict, rng: random.Random) -> list[dict]:
    rows, price, d = [], c["price"], date(2021, 1, 4)
    while d <= date(2024, 6, 28):
        if d.weekday() < 5:
            price *= 1 + rng.gauss(0.0004, 0.015)
            o = price * (1 + rng.gauss(0, 0.004))
            rows.append(
                {
                    "ticker": c["ticker"],
                    "date": d.isoformat(),
                    "open": round(o, 2),
                    "high": round(max(o, price) * 1.006, 2),
                    "low": round(min(o, price) * 0.994, 2),
                    "close": round(price, 2),
                    "volume": int(rng.uniform(0.5, 1.5) * 2_000_000),
                }
            )
        d += timedelta(days=1)
    return rows


def main() -> None:
    rng = random.Random(42)
    for sub in ("submissions", "companyfacts"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    all_prices: list[dict] = []
    for c in COMPANIES:
        submissions, companyfacts = build(c)
        (OUT / "submissions" / f"CIK{c['cik']}.json").write_text(
            json.dumps(submissions, indent=1)
        )
        (OUT / "companyfacts" / f"CIK{c['cik']}.json").write_text(
            json.dumps(companyfacts, indent=1)
        )
        all_prices += prices(c, rng)
    with open(OUT / "market_prices.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_prices[0]))
        w.writeheader()
        w.writerows(all_prices)
    print(f"Wrote {len(COMPANIES)} companies and {len(all_prices)} price rows to {OUT}")


if __name__ == "__main__":
    main()

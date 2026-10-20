# Build guide: from an empty folder to this pipeline

This is the order the project is built in, what is done at each step, why, and how you know the step is finished. Every phase ends in something that runs. Follow it to rebuild the project yourself; the code in this repo is the reference answer.

**Time:** about 6 weeks at 1–2 hours a day. **You need:** Python 3.11, git, a terminal. Docker and Terraform are optional (phase 12).

| Phase | You build | Done when |
|---|---|---|
| 0 | The problem statement and the grain | You can say in one sentence what one row of the core table is |
| 1 | Repo skeleton, tooling | `make lint test` runs (on nothing) |
| 2 | Hands-on look at the source | You've read one real companyfacts JSON and found a restatement by hand |
| 3 | EDGAR client | Parsers are tested on fixtures; the client refuses to run without a User-Agent |
| 4 | Landing zone + lineage | Every raw file is saved with its SHA-256 and can be replayed |
| 5 | Bronze tables + idempotent loads | Loading twice gives the same row count |
| 6 | Sample data with planted cases | `python -m ingestion.demo` fills bronze offline |
| 7 | Quality gates | Contracts + GE fail loudly on bad data |
| 8 | dbt models + tests | `dbt build` passes and finds exactly the planted cases |
| 9 | Scoring + report | `reports/demo_alerts.md` ranks alerts with reasons |
| 10 | Dashboard | Streamlit shows the queue; AppTest renders without errors |
| 11 | Orchestration | Airflow DAG runs the same commands in order |
| 12 | CI/CD, Docker, Terraform | Every push runs lint, tests and the demo pipeline |
| 13 | Live run and triage | Real EDGAR data loads; you can explain the top 5 alerts |
| 14 | Documentation | A stranger can run it from the README |

---

## Phase 0: Frame the problem and pin down the grain

**Goal:** know exactly what you are detecting before writing code.

1. Write down the definition: *a restatement is when a company reports a different value for the same fact (same metric, unit and period) in a later filing.*
2. Learn the vocabulary: **10-K** (annual report), **10-Q** (quarterly), **10-K/A** (amended annual), **XBRL** (machine-readable tags in filings, e.g. `us-gaap:Revenues`), **CIK** (company ID), **accession number** (filing ID).
3. Write the **grain** of the core table: *one row per XBRL fact as reported in one filing, identified by (cik, taxonomy, metric, unit, period_start, period_end, accession_number).*

**Why the grain comes first:** v1 of this project skipped this step and keyed facts without `period_start`. A 3-month quarter and a 12-month year ending the same day collided, and one silently overwrote the other ([LESSONS_FROM_V1.md](LESSONS_FROM_V1.md)).

**Done when:** you can say the grain sentence without looking.

## Phase 1: Repo skeleton and tooling

```bash
mkdir financial-restatement-pipeline && cd $_ && git init
python3.11 -m venv .venv && source .venv/bin/activate
mkdir ingestion detection quality dbt_project dashboard dags tests scripts docs
touch ingestion/__init__.py detection/__init__.py quality/__init__.py tests/__init__.py
```

- `requirements.txt` with **pinned** versions (`duckdb==0.10.1`, not `duckdb`): the same install every time, on every machine.
- `Makefile` with `setup`, `test`, `lint`, `format`. Use absolute paths (`$(CURDIR)/.venv`) because some targets `cd` into subfolders. (v1's relative `.venv/bin/dbt` broke after `cd dbt_project`.)
- `.gitignore`: `.venv/`, `*.duckdb`, `.env`, `data/landing/`.
- `.env.example` listing every setting; real `.env` is never committed.

**Done when:** `make lint test` runs cleanly.

## Phase 2: Explore the source by hand

Before writing a client, look at the data yourself.

```bash
UA="Your Name you@yourdomain.com"
curl -s -H "User-Agent: $UA" https://data.sec.gov/submissions/CIK0000320193.json | python -m json.tool | head -40
curl -s -H "User-Agent: $UA" https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json -o aapl.json
python - <<'PY'
import json
f = json.load(open("aapl.json"))["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
for e in f[-8:]:
    print(e.get("start"), e["end"], e["val"], e["form"], e["filed"], e["accn"])
PY
```

What you should notice:

- Each fact has `start` (missing for balance-sheet facts), `end`, `val`, `accn`, `form`, `filed`, `fy`, `fp`, sometimes `frame`.
- The **same period appears in several filings** (last year's numbers are repeated as comparatives). Usually the value is identical; when it isn't, that's what we detect.
- A quarter and a full year can share an `end` date. Only `start` tells them apart.
- Without a `User-Agent` that names you and gives a contact email, SEC answers **403**.

**Done when:** you've found one fact whose value differs between two filings, by hand.

## Phase 3: The EDGAR client

File: `ingestion/edgar_client.py`. Split it in two:

- **Network functions** (`get_company_facts`, `get_submissions`): rate-limited (< 10 requests/second), retrying 429/5xx with backoff, and refusing to run without a real User-Agent (`config.require_user_agent()`).
- **Pure parsers** (`parse_company_profile`, `parse_filings`, `extract_financial_metrics`): JSON in, rows out, no network. They are what you test.

Keep amendments (`10-K/A`, `10-Q/A`) in the tracked forms, because they're how most restatements are filed. Extract both `us-gaap` (financials) and `dei` (cover page: shares outstanding).

```bash
pytest tests/test_edgar_client.py -v
```

**Done when:** parser tests pass on a fixture that contains a quarter and a year with the same end date, and the User-Agent test passes.

## Phase 4: Landing zone and lineage

File: `ingestion/landing.py`. Every response is written gzipped to `data/landing/<source>/<cik>/<date>.json.gz` **before** parsing, and its SHA-256 is returned.

- **Replay:** if you find a parser bug next month, rebuild bronze from these files (`make replay`) instead of re-downloading.
- **Evidence:** `bronze.ingestion_runs` stores source, CIK, file path, SHA-256, rows loaded and status for each document. Any number in gold traces back to exact bytes.
- Write to a temp file, then rename: readers never see half a file.

**Done when:** `test_landing_roundtrip_and_latest` passes.

## Phase 5: Bronze tables and idempotent loads

File: `ingestion/loader.py`.

- Bronze keeps raw values with light typing. No business logic.
- Each table has a primary key matching its grain. For facts it's `fact_key = md5(cik|taxonomy|metric|unit|period_start|period_end|accession_number)`.
- Loads use `INSERT OR REPLACE` from a DataFrame: **loading the same data twice leaves one copy** (idempotent), so a retried job can't double-count.
- Don't store yfinance's `marketCap`: it is today's value only. v1 copied it onto five years of history. Market cap is derived later from price × shares.

```bash
pytest tests/test_loader_and_landing.py -v
```

**Done when:** idempotency and quarter-vs-year tests pass.

## Phase 6: Sample data with planted cases

File: `scripts/make_sample_data.py` → `data/sample/`.

Write **fictional** companies in EDGAR's exact JSON shape, with one planted case per rule and one trap:

| Company | Planted |
|---|---|
| Northwind (NWDV) | 10-K/A restates FY2023 revenue −6% → MATERIAL AMENDMENT. **Trap:** Q4 and FY revenue share 2023-12-31. |
| Harbor (HRBL) | FY2022 revenue recast −0.5% in the next 10-K (MATERIAL by dollars) + op. income −2%. Balance sheet off by $10M. |
| Cedar Ridge (CDRH) | One quarter tagged in thousands → scale error and valuation outlier |

This is your **test oracle**: you know exactly what the pipeline must find, so you can test it end to end without the internet. `ingestion/demo.py` sends this data through the same land → load path as live data.

**Done when:** `python -m ingestion.demo` loads 214 facts and 6 lineage rows.

## Phase 7: Quality gates

- **Data contract** (`quality/data_contracts/filing_contract.yml`): the producer's promise: columns, types, not-null, unique, patterns, row rules (`period_end >= period_start`), volume and freshness. `quality/check_contracts.py` executes it and exits 1 on any error-level failure.
- **Great Expectations** (`quality/run_expectations.py`): statistical checks with `mostly` (e.g. 98% of forms are in the expected set; real data has rare forms).
- **Placement:** gates run on bronze **before** dbt, so bad raw data stops the run before it reaches tables people read.
- A gate that can't fail is decoration. v1's CI ran GE with `|| echo warning`, so it always passed.

**Done when:** `test_contract_catches_violations` passes, and corrupting a row makes `make quality` exit 1.

## Phase 8: dbt (where the detection logic lives)

```
dbt_project/models/
  staging/       stg_companies, stg_filings, stg_financial_facts, stg_market_data   (views: rename, type, label)
  intermediate/  int_filing_comparisons     LAG() per fact identity → value changes
                 int_balance_sheet_checks   Assets vs Liabilities+Equity per filing
                 int_quarterly_revenue      latest version per quarter; Q4 = FY − Q1..Q3 when untagged
                 int_scale_checks           quarter vs company median
                 int_market_valuation       ASOF join prices, nearest shares, robust z-score
  marts/         dim_companies, dim_filing_periods, fct_restatements, fct_anomalies
seeds/materiality_thresholds.csv            the severity policy (also read by Python)
macros/severity.sql, generate_schema_name.sql, surrogate_key.sql
tests/                                      singular tests (reconciliation, grain regression, orphans)
```

Key ideas to be able to explain:

- **Window functions** find changes: `lag(value) over (partition by <full fact identity> order by filed_date)`.
- **AMENDMENT vs RECAST:** new value from a `/A` form vs from a later regular report.
- **ASOF join:** "price on the last trading day on or before the quarter end".
- **Robust z-score** (median and MAD): one bad value can't hide itself by inflating the spread.
- **One source of truth for policy:** the seed CSV drives both `macros/severity.sql` and `detection/thresholds.py`.
- `generate_schema_name` override so tables land in `silver`/`gold`, not `main_gold`.

```bash
cd dbt_project && dbt deps --profiles-dir . && dbt build --profiles-dir .
```

**Done when:** `PASS=59 ERROR=0`, and `tests/test_end_to_end.py` confirms exactly 5 restatements plus 3 other anomalies.

## Phase 9: Scoring and the report

`detection/anomaly_scorer.py` turns `gold.fct_anomalies` into `gold.alerts` with a 0–100 priority and the reason for every point (type, size in % and in dollars, key metric, recency, severity). Dollar points count only when the unit is USD. `as_of` is a parameter so tests are deterministic. `python -m detection.run` writes the table and `reports/alerts.md`.

**Done when:** the scale error ranks first in the demo report and every alert lists its reasons.

## Phase 10: Dashboard

`dashboard/app.py` (Streamlit, read-only connection): KPI tiles, alert queue, restatement charts, a per-company page (quarterly revenue, price-to-sales), and pipeline health (lineage table, row counts). Test it headless:

```python
from streamlit.testing.v1 import AppTest
AppTest.from_file("dashboard/app.py").run()   # no exceptions = renders
```

## Phase 11: Orchestration

`dags/filing_pipeline_dag.py`: `ingest_edgar → check_contracts → run_expectations → dbt_build → score_alerts`, weekdays 06:00, `catchup=False`, `max_active_runs=1` (one DuckDB writer). Each task runs the same command as the Makefile, so failures are debugged by running the command by hand. Network tasks get more retries; quality gates get none (bad data won't fix itself).

## Phase 12: CI/CD, Docker, Terraform

`.github/workflows/ci.yml` runs on every push:

- `test`: ruff + pytest (including the dbt end-to-end test)
- `demo`: the full pipeline on sample data; the alert report goes to the job summary
- `terraform`: `fmt -check`, `init -backend=false`, `validate` (no cloud account needed)
- `docker`: builds the image and runs the demo inside it
- `audit`: dependency vulnerabilities (report only)

`deploy.yml` is manual, refuses to run without GCP secrets and needs approval to apply.

## Phase 13: Live run and triage

```bash
cp .env.example .env    # your name + real email
make pipeline
```

Then read `reports/alerts.md` like an analyst: for the top alerts, open the two filings on EDGAR (`https://www.sec.gov/Archives/edgar/data/<cik>/<accession without dashes>/`) and decide whether each is a correction, a reclassification or a pipeline bug. Pipeline bugs become tests and fixes; that loop is how v1's bugs were found.

## Phase 14: Documentation

README (what, results, how to run, limitations), this guide, `ARCHITECTURE.md` (decisions and trade-offs), `DATA_DICTIONARY.md`, `RUNBOOK.md`, `LESSONS_FROM_V1.md`, `ROADMAP.md`.

---

## Interview angles by phase

- **Grain (0, 5):** "The first thing I define is what one row means. Getting it wrong here caused silent overwrites in my first version."
- **Idempotency (5):** "Loads are upserts on a natural key, so retries never double-count."
- **Lineage (4):** "Every raw file is stored with its hash, so any number traces back to the exact bytes we received, and bronze can be replayed."
- **Quality placement (7):** "Gates run before transformation and fail the run; a check that can't fail is decoration."
- **Testing with an oracle (6, 8):** "I generate fictional data with known planted cases and assert the pipeline finds exactly those, no more and no less."
- **Honest scope:** "The cloud deployment is designed and validated but not applied; here's what's missing."

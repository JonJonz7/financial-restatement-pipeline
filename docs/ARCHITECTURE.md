# Architecture and decisions

## Flow

```
SEC EDGAR ──► ingestion (rate-limited, retries) ──► landing zone (raw JSON.gz + SHA-256)
                                                        │
Yahoo Finance prices ─────────────────────────────────► bronze (DuckDB) + ingestion_runs (lineage)
                                                        │
                                   quality gates: data contracts + Great Expectations  (fail = stop)
                                                        │
                                   dbt build: staging (views) → intermediate → marts + 45 tests
                                                        │
                                   detection: priority scoring → gold.alerts + reports/alerts.md
                                                        │
                                   Streamlit dashboard (read-only)
```

Orchestrated by Airflow in Docker (`dags/`), or by `make pipeline` locally. Both run the same commands.

## Decisions

Each records the choice, the alternatives and the trade-off.

**D1. DuckDB as the local warehouse.** Columnar and in-process, with zero setup, and it runs in CI. *Alternatives:* Postgres (needs a server), BigQuery (needs an account and costs money). *Trade-off:* one writer at a time, hence `max_active_runs=1`. The SQL is portable enough that the dbt project can target BigQuery later (ROADMAP).

**D2. Land raw files before parsing.** *Why:* replay after parser fixes without re-downloading, plus evidence (SHA-256) for every load. *Cost:* disk space (~1–5 MB per company per day, gzipped).

**D3. Bronze keyed on the full fact identity.** See LESSONS_FROM_V1 #1. Natural-key upserts make every load idempotent.

**D4. Detection in dbt, prioritisation in Python.** What counts as an anomaly is set-based SQL: versioned, tested and documented with the warehouse. What to look at first is row-by-row scoring with human-readable reasons, which is easier to express and unit-test in Python.

**D5. Severity policy in a seed.** `materiality_thresholds.csv` is read by `macros/severity.sql` and `detection/thresholds.py`. Changing the policy is one edit, reviewed in git.

**D6. Quality gates before dbt.** Bad raw data stops the run before it reaches gold. Contracts check schema, SLA and rules; GE checks statistical shape; dbt tests check model logic.

**D7. Historical market cap = close × SEC shares outstanding.** Provider "market cap" fields are point-in-time values. Deriving it keeps history correct and makes the method explicit.

**D8. Robust z-score for valuation outliers.** Median and MAD instead of mean and SD: with mean/SD, a single extreme value inflates the SD and hides itself.

**D9. Q4 derived when untagged.** Most filers report Q4 only inside the annual figure. Q4 = FY − (Q1+Q2+Q3), computed only when all three quarters exist, and marked `is_derived`.

**D10. Cloud: GCP design, not deployed.** Terraform describes GCS (landing), BigQuery (bronze/silver/gold), a Cloud Function (ingestion), Cloud Scheduler and least-privilege IAM, using OIDC (no long-lived keys). CI validates it; the deploy workflow is manual and guarded. Deploying costs money and isn't needed to demonstrate the engineering.

## Scaling notes

- 20 companies: about 1M fact rows in bronze, a full dbt build in seconds on a laptop.
- Thousands of companies: switch ingestion to SEC's nightly bulk `companyfacts.zip` (one download instead of N calls), partition landing by date, make `int_filing_comparisons` incremental (only facts touched by new accessions), and move to BigQuery or another multi-writer warehouse.

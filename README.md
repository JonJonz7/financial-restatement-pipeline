# Financial Restatement & Anomaly Detection Pipeline

A production-grade data engineering pipeline that ingests SEC EDGAR filings, detects financial restatements, and scores anomalies for prioritized review. Financial institutions lose billions annually to undetected data discrepancies, and SEC/FINRA regulatory pressure is accelerating -- particularly after the T+1 settlement shift. This pipeline automates what most firms still do manually: continuously monitoring for restated financial values and flagging material changes before they cascade into downstream systems.

## Architecture

```
                                +------------------+
                                |   SEC EDGAR API  |
                                +--------+---------+
                                         |
                    +--------------------v--------------------+
                    |          Ingestion Layer (Python)        |
                    |   edgar_client.py  |  market_data.py     |
                    +--------------------+--------------------+
                                         |
                    +--------------------v--------------------+
                    |         Bronze (DuckDB - Raw)           |
                    |  raw_filings | raw_financial_facts |     |
                    |  raw_market_data                         |
                    +--------------------+--------------------+
                                         |
                    +--------------------v--------------------+
                    |         dbt Transformation               |
                    |  Staging -> Intermediate -> Marts        |
                    +--------------------+--------------------+
                                         |
               +-------------------------+-------------------------+
               |                         |                         |
   +-----------v-----------+ +-----------v-----------+ +-----------v-----------+
   |   Silver (Cleaned)    | |    Gold (Analytics)    | |   Detection Engine    |
   |  stg_filings          | |  fct_restatements      | |  restatement_detector |
   |  stg_financial_facts  | |  fct_anomalies         | |  anomaly_scorer       |
   |  stg_market_data      | |  dim_companies         | |                       |
   +-----------------------+ +----------+-----------+ +-----------+------------+
                                         |                         |
                                         +-----------+-------------+
                                                     |
                                         +-----------v-----------+
                                         |  Streamlit Dashboard   |
                                         |  Alerts & Monitoring   |
                                         +-----------------------+

   +------------------+    +---------------------+    +------------------+
   | Airflow          |    | Great Expectations   |    | Terraform IaC    |
   | Orchestration    |    | Quality Gates        |    | GCP Deployment   |
   +------------------+    +---------------------+    +------------------+
```

## The Problem

Financial data reconciliation is one of the most resource-intensive operations in capital markets and corporate finance. When a public company restates previously reported figures -- changing revenue, net income, or asset totals in an amended filing -- every downstream consumer of that data is affected: risk models, compliance reports, trading algorithms, and investor disclosures. The industry spends an estimated $2-5 billion annually on manual reconciliation processes that still miss critical changes.

The SEC's shift to T+1 settlement (effective May 2024) compressed the window for catching data errors from two business days to one. At the same time, SEC and FINRA enforcement actions related to data accuracy have increased year over year. Firms that relied on periodic manual reviews are now exposed: a restated 10-K filed on a Friday afternoon can propagate incorrect values through an entire analytics stack before anyone notices on Monday.

This pipeline addresses the gap by continuously ingesting SEC EDGAR filings, comparing values across filing dates for the same reporting period, and automatically flagging restatements with severity classification and recommended actions. Instead of discovering a material restatement during quarterly audit, the system surfaces it within hours of the amended filing hitting EDGAR.

## Stack

| Tool | Purpose |
|---|---|
| **DuckDB** | Analytical warehouse (local dev). Columnar, zero-config, fast OLAP queries on financial data. |
| **dbt** | SQL transformation framework. Manages the bronze-to-gold medallion pipeline with tests and documentation. |
| **Apache Airflow** | Workflow orchestration. Schedules daily EDGAR ingestion, dbt runs, quality gates, and detection. |
| **Great Expectations** | Statistical data quality validation. Enforces expectations on freshness, completeness, and value ranges. |
| **Terraform** | Infrastructure as code. Defines the GCP production deployment (BigQuery, Cloud Functions, Cloud Scheduler). |
| **Docker** | Containerization. Single image for pipeline CLI, dbt, and dashboard. Docker Compose for local dev stack. |
| **GitHub Actions** | CI/CD. Runs pytest, dbt tests, linting, GE checkpoints, and security scans on every push. |
| **Streamlit + Plotly** | Interactive monitoring dashboard. KPIs, restatement timeline, severity distribution, company deep dives. |
| **Python (requests, pandas)** | SEC EDGAR API client and data manipulation. Rate-limited, with structured error handling. |
| **yfinance** | Market data for cross-source validation (OHLCV, market cap vs. SEC-reported figures). |

## Data Model

The pipeline uses a **medallion architecture** with three layers:

**Bronze (Raw)** -- Landing zone for unmodified API responses.
- `bronze.raw_filings` -- SEC filing metadata (CIK, accession number, form type, dates)
- `bronze.raw_financial_facts` -- XBRL financial facts (metric, value, period, filing date)
- `bronze.raw_market_data` -- OHLCV price history and market capitalization

**Silver (Cleaned)** -- Deduplicated, type-cast, business-key enriched.
- `silver.stg_filings` -- Cleaned filing metadata with surrogate keys
- `silver.stg_financial_facts` -- Filtered facts (nulls removed) with deterministic fact keys
- `silver.stg_market_data` -- Normalized market data

**Gold (Analytics)** -- Business-ready aggregates and detection outputs.
- `gold.fct_restatements` -- Detected restatements with severity classification and days-to-detection
- `gold.fct_anomalies` -- Unified anomaly table (restatements + cross-source) with severity scores (0-100)
- `gold.dim_companies` -- Company dimension with filing activity summary
- `gold.dim_filing_periods` -- Fiscal period dimension for time-series analysis

## Key Features

- **Real SEC EDGAR data** -- Ingests from the official XBRL companyfacts and submissions API endpoints for 20 major public companies (AAPL, MSFT, GOOGL, AMZN, JPM, GS, etc.)
- **Automated restatement detection** -- Identifies cases where the same (company, metric, period) was filed with different values across filing dates
- **Severity classification** -- MATERIAL (>5% or >$1M change), NOTABLE (1-5%), MINOR (<1%) with corresponding recommended actions
- **Cross-source validation** -- Compares SEC-reported revenue and assets against market capitalization to flag statistical outliers (>3 standard deviations)
- **Anomaly scoring (0-100)** -- Six-factor scoring model: percentage change magnitude, absolute dollar magnitude, metric importance, recency, severity classification, and cross-source z-score
- **Data quality contracts** -- Schema-level data contracts with freshness SLAs, completeness thresholds, and validity rules
- **Three layers of quality gates** -- dbt tests (schema + singular), Great Expectations (statistical), data contracts (SLA + ownership)
- **Full CI/CD** -- GitHub Actions pipeline with pytest, dbt test, ruff linting, format checks, and dependency security scans
- **Infrastructure as Code** -- Terraform configs for GCP production deployment (BigQuery + Cloud Functions + Cloud Scheduler)
- **Containerized** -- Docker image and docker-compose for local development with Airflow, DuckDB, and Streamlit

## Quick Start

```bash
make setup      # Create venv, install deps, init DuckDB, install dbt packages
make ingest     # Pull real SEC EDGAR data for 20 companies
make transform  # Run dbt models (staging -> intermediate -> marts)
make detect     # Find restatements and score anomalies
make dashboard  # Launch Streamlit dashboard on localhost:8501
```

Or run everything at once:

```bash
make pipeline   # ingest + transform + detect
```

For the full Docker stack (Airflow + Dashboard):

```bash
make docker-up  # Airflow UI at localhost:8080, Dashboard at localhost:8501
```

## Project Structure

```
financial-restatement-pipeline/
|-- ingestion/
|   |-- edgar_client.py          # SEC EDGAR API client (rate-limited, XBRL parsing)
|   |-- loader.py                # DuckDB warehouse loader (upsert semantics)
|   |-- market_data.py           # Yahoo Finance market data client
|   |-- pipeline.py              # End-to-end ingestion + detection orchestrator
|   |-- config.py                # Watched companies, API settings, rate limits
|
|-- detection/
|   |-- restatement_detector.py  # Core restatement detection (SQL-based)
|   |-- anomaly_scorer.py        # Six-factor severity scoring and alert generation
|
|-- dbt_project/
|   |-- models/
|   |   |-- staging/             # stg_filings, stg_financial_facts, stg_market_data
|   |   |-- intermediate/        # int_filing_comparisons, int_cross_source_validation
|   |   |-- marts/               # fct_restatements, fct_anomalies, dim_companies, dim_filing_periods
|   |-- tests/                   # Singular dbt tests (orphan checks, value reconciliation, score ranges)
|   |-- macros/                  # materiality_threshold, surrogate_key
|   |-- seeds/                   # materiality_thresholds.csv
|
|-- dashboard/
|   |-- app.py                   # Streamlit dashboard (KPIs, timeline, severity, deep dives)
|
|-- dags/
|   |-- filing_pipeline_dag.py   # Airflow DAG (ingestion -> dbt -> GE -> detection -> alerts)
|
|-- tests/
|   |-- conftest.py              # Shared fixtures (sample XBRL, test DB, financial records)
|   |-- test_edgar_client.py     # EDGAR client tests (mocked HTTP, rate limiting, parsing)
|   |-- test_restatement_detector.py  # Detection tests (real DuckDB, severity classification)
|   |-- test_anomaly_scorer.py   # Scoring tests (score ranges, sorting, risk factors)
|   |-- test_loader.py           # Loader tests (schema creation, upserts, deduplication)
|
|-- quality/
|   |-- great_expectations/      # GE config, expectations, checkpoints
|   |-- data_contracts/          # Schema-level data contracts with SLAs
|
|-- terraform/                   # GCP IaC (BigQuery, Cloud Functions, Cloud Scheduler)
|-- .github/workflows/           # CI (pytest + dbt + lint + security) and CD (deploy)
|-- Dockerfile                   # Multi-purpose container image
|-- docker-compose.yml           # Local dev stack (Airflow + DuckDB + Streamlit)
|-- Makefile                     # Developer commands (setup, ingest, transform, detect, test)
|-- requirements.txt             # Python dependencies
```

## Data Quality

Quality enforcement operates at three levels:

**1. dbt Tests (Schema + Singular)**
Schema tests validate not-null constraints, accepted values, uniqueness, and referential integrity across every model. Singular tests enforce business rules: no orphaned anomalies (every anomaly references a valid restatement or cross-source record), restatement values reconcile correctly (restated minus original equals absolute change), and severity scores fall within the valid 0-100 range.

**2. Great Expectations (Statistical)**
The GE checkpoint runs against the bronze layer after every ingestion cycle. Expectations validate column-level statistics: row counts above minimum thresholds, value distributions within expected ranges, date columns conforming to expected formats, and no unexpected nulls in required fields.

**3. Data Contracts (SLA + Ownership)**
YAML-based contracts define the schema, quality rules, freshness SLAs, and ownership for each bronze table. The `raw_financial_facts` contract specifies a 24-hour freshness requirement (measured on `ingested_at`), 95% completeness threshold, and acceptable form types. Contracts serve as the single source of truth between producers (ingestion) and consumers (dbt models, detection engine).

## Cloud Deployment

The `terraform/` directory contains production-ready IaC for Google Cloud Platform:

- **BigQuery** -- Three datasets (`bronze`, `silver`, `gold`) mirroring the local DuckDB medallion architecture. Production dbt models target BigQuery instead of DuckDB via profile switching.
- **Cloud Functions** -- A Python 3.11 function (`edgar-ingestion`) handles EDGAR API calls with 512MB memory and 9-minute timeout. Triggered by Cloud Scheduler or on-demand HTTP POST.
- **Cloud Scheduler** -- Daily trigger at 06:00 ET with retry policy (3 attempts, 30-300s backoff). Uses OIDC authentication against the pipeline service account.
- **GCS** -- Versioned bucket for raw filing archive with automatic NEARLINE tiering after 365 days.
- **IAM** -- Least-privilege bindings: the pipeline service account gets BigQuery User/DataEditor, Cloud Functions Invoker, Cloud Scheduler Admin, and GCS ObjectAdmin.

## Sample Output

A detected restatement looks like this:

| cik | metric | period_end | original_value | restated_value | pct_change | severity | days_to_detect |
|---|---|---|---|---|---|---|---|
| 0000320193 | Revenues | 2023-09-30 | 383,285,000,000 | 390,000,000,000 | 1.75% | NOTABLE | 104 |
| 0000789019 | NetIncomeLoss | 2023-06-30 | 72,361,000,000 | 74,100,000,000 | 2.40% | NOTABLE | 87 |
| 0000886982 | Assets | 2023-12-31 | 1,641,594,000,000 | 1,572,000,000,000 | 4.24% | NOTABLE | 62 |

An anomaly alert includes a severity score (0-100), risk factors, and recommended action:

```
Severity Score: 85
Risk Factors:
  - Large percentage change (12.3%)
  - Billion-dollar absolute change ($47,200,000,000)
  - High-importance metric (Revenues)
  - Restated within the last 90 days
  - Classified as MATERIAL
Recommended Action: IMMEDIATE REVIEW - Escalate to compliance. Possible material misstatement.
```

## Testing

Run the full test suite:

```bash
make test       # pytest + dbt test
```

Or run pytest alone:

```bash
pytest tests/ -v --tb=short
```

**Coverage:**
- `test_edgar_client.py` -- EDGAR API client (mocked HTTP calls, XBRL parsing, rate limiting, User-Agent header, form-type filtering, CIK normalization)
- `test_restatement_detector.py` -- Restatement detection (real DuckDB, value change detection, identical-value exclusion, severity classification for MATERIAL/NOTABLE/MINOR, empty database handling)
- `test_anomaly_scorer.py` -- Anomaly scoring (score range validation, high/low severity thresholds, alert sorting, risk factor generation, recommended actions, edge cases with null/zero values)
- `test_loader.py` -- Warehouse loader (schema creation, table creation, insert correctness, upsert deduplication, empty input handling)
- dbt tests -- Schema constraints, orphan anomaly checks, value reconciliation, score range assertions

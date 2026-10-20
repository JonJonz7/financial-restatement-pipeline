# Data dictionary

## bronze (raw, loaded by `ingestion/loader.py`)

| Table | Grain | Key columns |
|---|---|---|
| `raw_companies` | one company | `cik` (10-digit), `company_name`, `ticker`, `sic`, `sic_description`, `fiscal_year_end` (MMDD) |
| `raw_filings` | one filing | `accession_number`, `cik`, `form_type` (10-K, 10-K/A, 10-Q, 10-Q/A), `filing_date`, `period_of_report` |
| `raw_financial_facts` | one fact as reported in one filing | `fact_key` (md5 of the identity), `cik`, `taxonomy` (us-gaap/dei), `metric`, `unit`, `period_start` (NULL = instant), `period_end`, `value`, `form`, `filed_date`, `accession_number`, `fiscal_year`, `fiscal_period`, `frame` |
| `raw_market_data` | one ticker-day | `ticker`, `date`, `open`, `high`, `low`, `close`, `volume` |
| `ingestion_runs` | one source document loaded | `run_id`, `source`, `cik`, `landed_path`, `sha256`, `rows_loaded`, `status`, `error`, `started_at`, `finished_at` |

## silver (dbt)

| Model | Grain | Notes |
|---|---|---|
| `stg_financial_facts` | as bronze | adds `duration_days`, `period_type` (instant / quarter / year / other) |
| `stg_filings` | filing | adds `is_amendment` |
| `stg_companies`, `stg_market_data` | as bronze | renamed and typed |
| `int_filing_comparisons` | one value change | `original_value`, `restated_value`, both accession numbers, `pct_change`, `absolute_change` |
| `int_balance_sheet_checks` | filing with a break | `assets`, `liabilities_and_equity`, `difference` |
| `int_quarterly_revenue` | company-quarter | latest filed version; `is_derived` = Q4 computed from FY |
| `int_scale_checks` | flagged company-quarter | `ratio_to_median` |
| `int_market_valuation` | company-quarter | `market_cap`, `price_to_sales`, `robust_z`, `is_outlier` |

## gold

| Table | Grain | Notes |
|---|---|---|
| `dim_companies` | company | filing counts incl. `amendment_filings` |
| `dim_filing_periods` | fiscal year + period | facts and companies reporting |
| `fct_restatements` | value change | `restatement_type` (AMENDMENT / RECAST), `severity`, `days_to_restatement` |
| `fct_anomalies` | anomaly | `anomaly_type` (RESTATEMENT / BALANCE_SHEET_BREAK / SCALE_ERROR / VALUATION_OUTLIER), `expected_value`, `actual_value`, `severity`, `detail` |
| `alerts` | anomaly | `fct_anomalies` + `priority_score` (0–100), `risk_factors`, `recommended_action` (written by `detection/run.py`) |

## Severity policy (`seeds/materiality_thresholds.csv`)

| Severity | Rule |
|---|---|
| MATERIAL | change ≥ 5%, or ≥ $1M when the unit is USD |
| NOTABLE | change ≥ 1%, or ≥ $100K when the unit is USD |
| MINOR | anything else |

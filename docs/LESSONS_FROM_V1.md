# Lessons from v1

The first version of this repo (commit `6a6e8e4`) had 33 passing unit tests and a professional README, but it had never run end to end. Running it surfaced the bugs below. Each is fixed and now has a test.

| # | Bug | Effect | Fix | Test |
|---|---|---|---|---|
| 1 | Fact primary key ignored `period_start` and `unit` | A 3-month quarter and a 12-month year ending the same day collided; `INSERT OR REPLACE` kept one and silently dropped the other | `fact_key` over the full identity (cik, taxonomy, metric, unit, period_start, period_end, accession) | `test_quarter_and_year_with_same_end_are_both_kept` |
| 2 | Restatement detection partitioned by (cik, metric, period_end) | Quarter vs year compared → huge fake "restatements" | Partition by the full fact identity | dbt `assert_no_quarter_vs_year_comparisons`, `test_no_false_restatements` |
| 3 | dbt staging selected columns bronze never had (`form_type`, `company_name`, `ticker`, `sic_code`, `filed_date`) | `dbt run` could not succeed | New `raw_companies` table from the submissions endpoint; staging rewritten on real columns | CI `dbt build` |
| 4 | Cross-source join matched market data on date only | Every company's revenue joined to every ticker's price | Join by ticker; ASOF join for the last trading day | `int_market_valuation` uniqueness test |
| 5 | yfinance `marketCap` (today's value) copied onto 5 years of history | All historical valuations were wrong | Market cap = close × SEC-reported shares outstanding | `int_market_valuation` |
| 6 | `make ingest` / `make detect` ran modules with no `__main__` | Commands did nothing and exited 0 | Real CLIs (`ingestion.pipeline`, `detection.run`) with exit codes | CI demo job |
| 7 | Makefile `cd dbt_project && .venv/bin/dbt` | `make setup` always failed | Absolute paths via `$(CURDIR)` | `make demo` |
| 8 | CI quality job: `great_expectations ... \|\| echo warning` | The gate could never fail | Executable contracts + GE runner, both exit 1 on failure | `test_contract_catches_violations` |
| 9 | Python and dbt had different materiality rules | Same change could be MATERIAL in one, NOTABLE in the other | One seed CSV read by both | `test_thresholds_come_from_the_dbt_seed` |
| 10 | Default User-Agent `contact@example.com` | SEC returns 403 for every request | No default; clear error with instructions | `test_user_agent_is_required` |
| 11 | Visa listed with the wrong CIK | Would have loaded another company's filings | Corrected to 0001403161 | — |
| 12 | Airflow DAG imported `score_anomalies`, which didn't exist | DAG import error | DAG runs the CLI commands | — |
| 13 | Deploy workflow ran on every push without credentials, and deployed a Cloud Function entry point that didn't exist | Red builds; a deploy that couldn't work | Manual-only deploy with a preflight check; gap listed in ROADMAP | — |

## What to take from it

- **Passing unit tests ≠ a working pipeline.** Each unit worked alone; the seams between them (column names, keys, joins) were wrong. An end-to-end test on realistic data catches seam bugs; unit tests don't.
- **Define the grain before the schema.** Bugs 1 and 2 are the same mistake: not writing down what one row means.
- **A check that can't fail is decoration** (bug 8).
- **One source of truth for business rules** (bug 9).

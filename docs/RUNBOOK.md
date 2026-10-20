# Runbook

## Daily operation

`make pipeline` (or the Airflow DAG at 06:00 on weekdays): ingest → quality → dbt build → alerts. Output: `reports/alerts.md`, `gold.alerts`, and the dashboard.

## When something fails

| Symptom | Likely cause | What to do |
|---|---|---|
| `RuntimeError: Set EDGAR_USER_AGENT` | No contact configured | Put `EDGAR_USER_AGENT="Name email"` in `.env` |
| HTTP 403 from data.sec.gov | User-Agent missing or looks fake | Use a real name and email; don't use example.com |
| HTTP 429 / 503 | SEC rate limit or outage | The client retries 3× with backoff; if it persists, rerun later. Already-landed companies don't need re-fetching: `make replay` |
| `ingest` exits 1, some companies loaded | One company failed (bad CIK, network) | `select * from bronze.ingestion_runs where status='error' order by finished_at desc` |
| Contract FAIL `freshness` | Ingestion didn't run or failed | Check the ingest step; for old data use `python -m quality.check_contracts --no-freshness` |
| Contract FAIL on a rule | Upstream data changed shape | Look at failing rows with the rule's condition negated; fix the parser, then `make replay` |
| `dbt build` test fails | A model's assumptions broke | `cd dbt_project && dbt test --select <test> --store-failures`, then query the failures table |
| DuckDB "could not set lock" | Two writers (dashboard open in write mode, or two runs) | Close other connections; the dashboard opens read-only |
| Dashboard says no gold data | dbt hasn't run on that warehouse | `make demo` or `make pipeline`; check `WAREHOUSE_DB_PATH` |

## Rebuild from scratch without the network

```bash
make clean            # removes warehouses, keeps data/landing
make replay           # bronze from landed files
make transform detect
```

## Change the severity policy

Edit `dbt_project/seeds/materiality_thresholds.csv`, run `make test transform`. dbt and Python both pick it up.

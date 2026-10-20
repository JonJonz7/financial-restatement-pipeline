# Roadmap

Honest list of what isn't built yet, in priority order.

1. **Live-data baseline.** Run against all 20 watched companies, triage the top alerts against the actual filings, and add any newly found parser edge cases as tests.
2. **Bulk ingestion.** Use SEC's nightly `companyfacts.zip` for full-market coverage instead of one call per company.
3. **Incremental dbt.** Make `int_filing_comparisons` incremental on new accession numbers.
4. **BigQuery target.** Add a `prod` profile and fix any DuckDB-only SQL (`ASOF JOIN`, `QUALIFY`) with dbt cross-database macros.
5. **Cloud Function entry point.** `ingest_handler(request)` that lands to GCS, so the Terraform design can actually be applied.
6. **Alert delivery.** Send immediate-review alerts to email or Slack, with de-duplication so the same alert isn't sent twice.
7. **Disclosure text.** Link each amendment to its explanatory note (the "Explanatory Note" section of the 10-K/A).

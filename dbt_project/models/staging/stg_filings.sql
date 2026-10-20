/*
    stg_filings
    SEC filing index (10-K, 10-Q and their /A amendments).
    Grain: accession_number (one filing). Duplicates from repeated
    ingestion are removed by keeping the most recent load.
*/
with source as (
    select * from {{ source('bronze', 'raw_filings') }}
),

deduplicated as (
    select
        cast(cik as varchar)              as cik,
        cast(accession_number as varchar) as accession_number,
        cast(form_type as varchar)        as form_type,
        form_type like '%/A'              as is_amendment,
        cast(filing_date as date)         as filed_date,
        cast(period_of_report as date)    as period_of_report,
        cast(primary_document as varchar) as primary_document,
        cast(ingested_at as timestamp)    as ingested_at,
        row_number() over (partition by accession_number order by ingested_at desc) as _rn
    from source
)

select * exclude (_rn)
from deduplicated
where _rn = 1

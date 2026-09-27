/*
    stg_filings
    ---------------------------------------------------------------
    Staging model for SEC EDGAR filing metadata.

    Business logic:
      - Cleans and standardises column names from the bronze layer.
      - Casts raw strings to proper types (dates, integers).
      - Deduplicates on accession_number, keeping the most recently
        ingested record when duplicates exist.
*/

with source as (

    select * from {{ source('bronze', 'raw_filings') }}

),

cleaned as (

    select
        cast(cik                as integer)     as cik,
        cast(accession_number   as varchar)     as accession_number,
        cast(company_name       as varchar)     as company_name,
        cast(form_type          as varchar)     as form_type,
        cast(filed_date         as date)        as filed_date,
        cast(period_of_report   as date)        as period_of_report,
        cast(fiscal_year        as integer)     as fiscal_year,
        cast(fiscal_period      as varchar)     as fiscal_period,
        cast(ticker             as varchar)     as ticker,
        cast(sic_code           as varchar)     as sic_code,
        cast(ingested_at        as timestamp)   as ingested_at
    from source

),

-- Keep only the latest ingested record per accession_number
deduplicated as (

    select
        *,
        row_number() over (
            partition by accession_number
            order by ingested_at desc
        ) as _row_num
    from cleaned

)

select
    cik,
    accession_number,
    company_name,
    form_type,
    filed_date,
    period_of_report,
    fiscal_year,
    fiscal_period,
    ticker,
    sic_code,
    ingested_at
from deduplicated
where _row_num = 1

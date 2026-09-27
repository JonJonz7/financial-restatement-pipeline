/*
    stg_financial_facts
    ---------------------------------------------------------------
    Staging model for SEC XBRL financial facts (revenue, assets,
    net income, etc.).

    Business logic:
      - Casts raw values to proper types.
      - Filters out records with null metric values (unusable for
        comparison or anomaly detection).
      - Adds a deterministic surrogate key from (cik, metric,
        period_end, filed_date) so downstream models can identify
        each unique fact observation.
*/

with source as (

    select * from {{ source('bronze', 'raw_financial_facts') }}

),

cleaned as (

    select
        cast(cik            as integer)     as cik,
        cast(metric         as varchar)     as metric,
        cast(value          as double)      as value,
        cast(unit           as varchar)     as unit,
        cast(period_start   as date)        as period_start,
        cast(period_end     as date)        as period_end,
        cast(filed_date     as date)        as filed_date,
        cast(form_type      as varchar)     as form_type,
        cast(accession_number as varchar)   as accession_number,
        cast(fiscal_year    as integer)     as fiscal_year,
        cast(fiscal_period  as varchar)     as fiscal_period,
        cast(ingested_at    as timestamp)   as ingested_at
    from source
    -- Exclude rows where the reported value is null — they cannot
    -- contribute to restatement detection or anomaly scoring.
    where value is not null

),

with_surrogate_key as (

    select
        *,
        {{ generate_surrogate_key(['cik', 'metric', 'period_end', 'filed_date']) }}
            as fact_key
    from cleaned

)

select
    fact_key,
    cik,
    metric,
    value,
    unit,
    period_start,
    period_end,
    filed_date,
    form_type,
    accession_number,
    fiscal_year,
    fiscal_period,
    ingested_at
from with_surrogate_key

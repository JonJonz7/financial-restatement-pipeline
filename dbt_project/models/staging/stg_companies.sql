/*
    stg_companies
    One row per company (CIK) from the SEC submissions profile.
    Grain: cik.
*/
select
    cast(cik as varchar)             as cik,
    cast(company_name as varchar)    as company_name,
    upper(cast(ticker as varchar))   as ticker,
    cast(sic as varchar)             as sic_code,
    cast(sic_description as varchar) as sic_description,
    cast(fiscal_year_end as varchar) as fiscal_year_end,
    cast(ingested_at as timestamp)   as ingested_at
from {{ source('bronze', 'raw_companies') }}

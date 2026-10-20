/*
    dim_companies
    One row per company with its filing activity.
    Grain: cik.
*/
with filing_stats as (
    select
        cik,
        min(filed_date)                                         as first_filing_date,
        max(filed_date)                                         as latest_filing_date,
        count(*)                                                as total_filings,
        count(*) filter (where form_type in ('10-K', '10-K/A')) as annual_filings,
        count(*) filter (where form_type in ('10-Q', '10-Q/A')) as quarterly_filings,
        count(*) filter (where is_amendment)                    as amendment_filings
    from {{ ref('stg_filings') }}
    group by cik
)

select
    c.cik,
    c.company_name,
    c.ticker,
    c.sic_code,
    c.sic_description,
    c.fiscal_year_end,
    f.first_filing_date,
    f.latest_filing_date,
    coalesce(f.total_filings, 0)     as total_filings,
    coalesce(f.annual_filings, 0)    as annual_filings,
    coalesce(f.quarterly_filings, 0) as quarterly_filings,
    coalesce(f.amendment_filings, 0) as amendment_filings
from {{ ref('stg_companies') }} c
left join filing_stats f using (cik)

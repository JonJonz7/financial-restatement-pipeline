/*
    dim_filing_periods
    Fiscal periods (e.g. 2023 Q2) with how many facts and companies report them.
    Grain: (fiscal_year, fiscal_period).
*/
select
    {{ generate_surrogate_key(['fiscal_year', 'fiscal_period']) }} as period_key,
    fiscal_year,
    fiscal_period,
    min(period_start)   as period_start_date,
    max(period_end)     as period_end_date,
    min(filed_date)     as earliest_filing_date,
    max(filed_date)     as latest_filing_date,
    count(*)            as total_facts_reported,
    count(distinct cik) as companies_reporting
from {{ ref('stg_financial_facts') }}
where fiscal_year is not null
  and fiscal_period is not null
group by fiscal_year, fiscal_period

/*
    dim_filing_periods
    ---------------------------------------------------------------
    Filing period dimension table.

    Grain: one row per unique (fiscal_year, fiscal_period).

    Provides date-range context for each reporting period observed
    in the data, enabling time-series analysis and period-over-
    period comparisons in downstream dashboards.
*/

with period_facts as (

    select
        fiscal_year,
        fiscal_period,

        -- Earliest and latest period_end dates observed for this
        -- (fiscal_year, fiscal_period) combination
        min(period_start)   as period_start_date,
        max(period_end)     as period_end_date,

        -- Filing activity within this period
        min(filed_date)     as earliest_filing_date,
        max(filed_date)     as latest_filing_date,

        -- How many distinct facts were reported for this period
        count(*)            as total_facts_reported,

        -- How many distinct companies filed for this period
        count(distinct cik) as companies_reporting

    from {{ ref('stg_financial_facts') }}
    where
        fiscal_year is not null
        and fiscal_period is not null
    group by fiscal_year, fiscal_period

),

with_key as (

    select
        {{ generate_surrogate_key(['fiscal_year', 'fiscal_period']) }}
            as period_key,
        *
    from period_facts

)

select
    period_key,
    fiscal_year,
    fiscal_period,
    period_start_date,
    period_end_date,
    earliest_filing_date,
    latest_filing_date,
    total_facts_reported,
    companies_reporting
from with_key

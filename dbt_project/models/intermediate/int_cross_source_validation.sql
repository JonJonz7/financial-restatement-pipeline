/*
    int_cross_source_validation
    ---------------------------------------------------------------
    Cross-source anomaly detection: compares SEC-reported financial
    figures against market data to flag large discrepancies.

    Logic:
      1. Take Revenue and Assets facts from stg_financial_facts.
      2. Join to stg_filings to get the ticker for each CIK.
      3. For each fact, find the closest market-data date to the
         filing's period_end (within a 7-day window).
      4. Compare the SEC-reported value against market_cap to
         compute a ratio and flag outliers.

    A large discrepancy between reported revenue/assets and market
    cap can indicate data-entry errors, misclassified units, or
    genuinely anomalous financial situations worth investigating.
*/

with sec_facts as (

    -- Filter to metrics that are meaningful to compare against
    -- market capitalisation
    select
        ff.cik,
        ff.metric,
        ff.value        as reported_value,
        ff.period_end,
        ff.filed_date,
        ff.unit,
        f.ticker,
        f.company_name
    from {{ ref('stg_financial_facts') }} ff
    inner join {{ ref('stg_filings') }} f
        on ff.cik = f.cik
    where
        ff.metric in ('Revenue', 'Assets', 'Revenues', 'AssetsCurrent', 'RevenueFromContractWithCustomerExcludingAssessedTax')
        and f.ticker is not null

),

-- For each SEC fact, find the closest market data date
-- (within 7 calendar days of period_end)
market_match as (

    select
        sf.*,
        md.date         as market_date,
        md.close_price,
        md.market_cap,
        md.volume,

        -- Days between period_end and market data date
        abs(sf.period_end - md.date) as days_offset,

        -- Rank by proximity; closest date wins
        row_number() over (
            partition by sf.cik, sf.metric, sf.period_end
            order by abs(sf.period_end - md.date)
        ) as proximity_rank

    from sec_facts sf
    inner join {{ ref('stg_market_data') }} md
        on sf.ticker = md.ticker
        and abs(sf.period_end - md.date) <= 7

),

closest_match as (

    select * from market_match
    where proximity_rank = 1

),

discrepancies as (

    select
        cik,
        company_name,
        ticker,
        metric,
        period_end,
        filed_date,
        reported_value,
        market_cap,
        market_date,
        close_price,
        days_offset,

        -- Ratio of reported value to market cap
        -- Values far from typical ranges indicate anomalies
        case
            when market_cap is null or market_cap = 0 then null
            else round(reported_value / market_cap, 4)
        end as value_to_market_cap_ratio,

        -- Flag: is the ratio outside a reasonable range?
        -- Revenue typically 0.1x - 2x market cap; assets 0.5x - 5x
        case
            when market_cap is null or market_cap = 0
                then 'UNKNOWN'
            when metric in ('Revenue', 'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax')
                and (reported_value / market_cap > 3.0
                  or reported_value / market_cap < 0.01)
                then 'FLAGGED'
            when metric in ('Assets', 'AssetsCurrent')
                and (reported_value / market_cap > 10.0
                  or reported_value / market_cap < 0.01)
                then 'FLAGGED'
            else 'NORMAL'
        end as discrepancy_flag,

        -- Absolute difference between reported value and market cap
        abs(reported_value - market_cap) as absolute_discrepancy,

        -- Percentage difference relative to market cap
        case
            when market_cap is null or market_cap = 0 then null
            else round(
                abs(reported_value - market_cap) / market_cap * 100,
                2
            )
        end as pct_discrepancy

    from closest_match

)

select * from discrepancies
where discrepancy_flag != 'NORMAL'

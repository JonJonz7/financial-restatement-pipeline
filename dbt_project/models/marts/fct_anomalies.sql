/*
    fct_anomalies
    ---------------------------------------------------------------
    Every detected issue in one table, one shape:

      RESTATEMENT          a reported number changed in a later filing
      BALANCE_SHEET_BREAK  Assets != Liabilities + Equity in one filing
      SCALE_ERROR          a quarter's revenue is <5% or >20x the usual (units)
      VALUATION_OUTLIER    price-to-sales far outside the company's own history

    expected_value = what the number should be (or was), actual_value = what
    was reported. Prioritisation (0-100) happens downstream in
    detection/anomaly_scorer.py, which writes gold.alerts.

    Grain: anomaly_id.
*/
with restatements as (
    select
        restatement_id           as anomaly_id,
        'RESTATEMENT'            as anomaly_type,
        cik, metric, period_end,
        original_value           as expected_value,
        restated_value           as actual_value,
        absolute_change,
        pct_change,
        unit,
        severity,
        restatement_filed_date   as detected_date,
        restatement_type || ' in ' || restatement_form_type || ' ' || restatement_accession_number as detail
    from {{ ref('fct_restatements') }}
),

balance_breaks as (
    select
        {{ generate_surrogate_key(['cik', 'period_end', 'accession_number', "'BS'"]) }},
        'BALANCE_SHEET_BREAK',
        cik, 'Assets', period_end,
        liabilities_and_equity, assets,
        difference, pct_difference, 'USD',
        {{ severity('pct_difference', 'difference', "'USD'") }},
        filed_date,
        'Assets vs LiabilitiesAndStockholdersEquity in ' || accession_number
    from {{ ref('int_balance_sheet_checks') }}
),

scale_errors as (
    select
        {{ generate_surrogate_key(['cik', 'period_end', "'SCALE'"]) }},
        'SCALE_ERROR',
        cik, 'Revenue (quarter)', period_end,
        median_revenue, revenue,
        revenue - median_revenue,
        round((revenue - median_revenue) / median_revenue * 100, 4),
        'USD',
        'MATERIAL',
        period_end,
        'Quarter revenue is ' || cast(ratio_to_median as varchar) || 'x the company median'
    from {{ ref('int_scale_checks') }}
),

valuation as (
    select
        {{ generate_surrogate_key(['cik', 'period_end', "'VAL'"]) }},
        'VALUATION_OUTLIER',
        cik, 'PriceToSales', period_end,
        null, price_to_sales,
        null, null,
        'ratio',
        'NOTABLE',
        period_end,
        'Robust z-score ' || cast(robust_z as varchar) || ' vs company history'
    from {{ ref('int_market_valuation') }}
    where is_outlier
)

select * from restatements
union all select * from balance_breaks
union all select * from scale_errors
union all select * from valuation

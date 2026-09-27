/*
    fct_anomalies
    ---------------------------------------------------------------
    Unified anomaly fact table combining two detection sources:
      1. RESTATEMENT  — from fct_restatements (value changed across
         filings for the same metric/period)
      2. CROSS_SOURCE — from int_cross_source_validation (SEC-
         reported figures diverge significantly from market data)

    Each anomaly receives a severity_score (0-100) to enable
    prioritised review. The score considers both the magnitude
    of the discrepancy and the type of anomaly.

    Grain: one row per anomaly event.
*/

with restatement_anomalies as (

    select
        restatement_id                  as anomaly_id,
        'RESTATEMENT'                   as anomaly_type,
        cik,
        metric,
        period_end,
        original_value                  as expected_value,
        restated_value                  as actual_value,
        absolute_change,
        pct_change,
        severity,
        restatement_filed_date          as detected_date,

        -- Severity score 0-100 based on materiality
        -- MATERIAL -> 70-100, NOTABLE -> 40-69, MINOR -> 1-39
        case severity
            when 'MATERIAL' then
                least(100, 70 + round(abs(pct_change) * 2, 0)::integer)
            when 'NOTABLE' then
                least(69,  40 + round(abs(pct_change) * 5, 0)::integer)
            else
                least(39,  1  + round(abs(pct_change) * 10, 0)::integer)
        end as severity_score

    from {{ ref('fct_restatements') }}

),

cross_source_anomalies as (

    select
        {{ generate_surrogate_key([
            'cik',
            'metric',
            'period_end',
            'market_date'
        ]) }}                           as anomaly_id,
        'CROSS_SOURCE'                  as anomaly_type,
        cik,
        metric,
        period_end,
        market_cap                      as expected_value,
        reported_value                  as actual_value,
        absolute_discrepancy            as absolute_change,
        pct_discrepancy                 as pct_change,

        -- Classify cross-source anomalies using the same macro
        {{ materiality_threshold('pct_discrepancy', 'absolute_discrepancy') }}
                                        as severity,

        filed_date                      as detected_date,

        -- Severity score for cross-source anomalies
        -- Scaled similarly but capped
        case
            {{ materiality_threshold('pct_discrepancy', 'absolute_discrepancy') }}
            when 'MATERIAL' then
                least(100, 70 + least(30, round(pct_discrepancy / 10, 0)::integer))
            when 'NOTABLE' then
                least(69,  40 + least(29, round(pct_discrepancy / 5, 0)::integer))
            else
                least(39,  1  + least(38, round(pct_discrepancy, 0)::integer))
        end as severity_score

    from {{ ref('int_cross_source_validation') }}
    where discrepancy_flag = 'FLAGGED'

),

unioned as (

    select * from restatement_anomalies
    union all
    select * from cross_source_anomalies

)

select
    anomaly_id,
    anomaly_type,
    cik,
    metric,
    period_end,
    expected_value,
    actual_value,
    absolute_change,
    pct_change,
    severity,
    severity_score,
    detected_date
from unioned

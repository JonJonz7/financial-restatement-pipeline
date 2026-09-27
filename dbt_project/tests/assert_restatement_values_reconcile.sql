/*
    Singular test: assert_restatement_values_reconcile
    ---------------------------------------------------------------
    Verifies that every restatement in fct_restatements traces back
    to actual different values in the staging layer.

    This test catches cases where:
      - A restatement was fabricated by a transformation bug
      - The original_value or restated_value don't match what's
        in stg_financial_facts
      - A join error created phantom restatements

    The query returns rows that FAIL reconciliation.
    A passing test returns 0 rows.
*/

with restatements as (

    select
        cik,
        metric,
        period_end,
        original_value,
        restated_value,
        original_filed_date,
        restatement_filed_date
    from {{ ref('fct_restatements') }}

),

-- Look up the original value in staging
original_facts as (

    select
        cik,
        metric,
        period_end,
        filed_date,
        value
    from {{ ref('stg_financial_facts') }}

),

reconciled as (

    select
        r.cik,
        r.metric,
        r.period_end,
        r.original_value,
        r.restated_value,
        r.original_filed_date,
        r.restatement_filed_date,

        orig.value  as staging_original_value,
        rest.value  as staging_restated_value

    from restatements r

    -- Join to find the original value in staging
    left join original_facts orig
        on  r.cik               = orig.cik
        and r.metric            = orig.metric
        and r.period_end        = orig.period_end
        and r.original_filed_date = orig.filed_date

    -- Join to find the restated value in staging
    left join original_facts rest
        on  r.cik               = rest.cik
        and r.metric            = rest.metric
        and r.period_end        = rest.period_end
        and r.restatement_filed_date = rest.filed_date

)

-- Return rows where the restatement does NOT reconcile with staging
select *
from reconciled
where
    -- Original value doesn't match staging
    staging_original_value is null
    or staging_restated_value is null
    or abs(original_value - staging_original_value) > 0.01
    or abs(restated_value - staging_restated_value) > 0.01
    -- Values should actually differ
    or abs(original_value - restated_value) < 0.01

/*
    int_filing_comparisons
    ---------------------------------------------------------------
    Core restatement-detection model.

    For every (cik, metric, period_end) combination, this model
    self-joins stg_financial_facts to find cases where the SAME
    metric for the SAME reporting period was filed with DIFFERENT
    values on DIFFERENT filing dates.

    This is the hallmark of a financial restatement: a company
    files a 10-K reporting Revenue of $X for FY2023, then later
    files a 10-K/A (amended) reporting Revenue of $Y for the same
    FY2023 period.

    Window functions (LAG / LEAD) ordered by filed_date identify:
      - prior_value:  what was reported in the previous filing
      - next_value:   what was reported in the next filing
      - Whether a change actually occurred

    Output columns:
      cik, metric, period_end,
      original_value, restated_value,
      original_filed_date, restatement_filed_date,
      absolute_change, pct_change
*/

with fact_timeline as (

    -- Order each (cik, metric, period_end) group by filing date
    -- so we can detect value changes across filings
    select
        cik,
        metric,
        period_end,
        value,
        filed_date,
        form_type,
        accession_number,

        -- Previous reported value for the same metric/period
        lag(value)       over (
            partition by cik, metric, period_end
            order by filed_date
        ) as prior_value,

        -- Previous filing date
        lag(filed_date)  over (
            partition by cik, metric, period_end
            order by filed_date
        ) as prior_filed_date,

        -- Next reported value (to confirm this row was later restated)
        lead(value)      over (
            partition by cik, metric, period_end
            order by filed_date
        ) as next_value,

        -- Filing sequence number within the group
        row_number()     over (
            partition by cik, metric, period_end
            order by filed_date
        ) as filing_seq

    from {{ ref('stg_financial_facts') }}

),

restatements as (

    -- A restatement exists when:
    --   1. There is a prior filing for the same (cik, metric, period_end)
    --   2. The value changed between the two filings
    select
        cik,
        metric,
        period_end,
        prior_value         as original_value,
        value               as restated_value,
        prior_filed_date    as original_filed_date,
        filed_date          as restatement_filed_date,
        form_type           as restatement_form_type,
        accession_number    as restatement_accession_number,

        -- Absolute dollar change
        value - prior_value as absolute_change,

        -- Percentage change (guard against division by zero)
        case
            when prior_value = 0 then null
            else round(
                ((value - prior_value) / abs(prior_value)) * 100,
                4
            )
        end as pct_change

    from fact_timeline
    where
        -- Must have a prior filing to compare against
        prior_value is not null
        -- The value must actually differ
        and value != prior_value

)

select * from restatements

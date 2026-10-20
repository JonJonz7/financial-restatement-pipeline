/*
    int_filing_comparisons
    ---------------------------------------------------------------
    Every time a fact's value CHANGES from one filing to the next.

    A fact is identified by (cik, taxonomy, metric, unit, period_start,
    period_end). Companies repeat last year's numbers in this year's report
    as comparatives; usually the value is identical. When it is not, the
    company has restated or recast that number.

    Comparing at a coarser grain (e.g. without period_start) would compare a
    3-month quarter to a 12-month year ending the same day and report huge
    fake "restatements". That bug existed in v1 of this project.

    Grain: one row per value change (restating filing).
*/
with versions as (
    select
        cik, taxonomy, metric, unit, period_start, period_end, period_type,
        value, filed_date, form_type, accession_number,
        lag(value)            over w as prior_value,
        lag(filed_date)       over w as prior_filed_date,
        lag(accession_number) over w as prior_accession_number,
        row_number()          over w as version_number
    from {{ ref('stg_financial_facts') }}
    window w as (
        partition by cik, taxonomy, metric, unit, period_start, period_end
        order by filed_date, accession_number
    )
)

select
    cik,
    taxonomy,
    metric,
    unit,
    period_start,
    period_end,
    period_type,
    prior_value                    as original_value,
    value                          as restated_value,
    prior_filed_date               as original_filed_date,
    filed_date                     as restatement_filed_date,
    prior_accession_number         as original_accession_number,
    accession_number               as restatement_accession_number,
    form_type                      as restatement_form_type,
    version_number,
    value - prior_value            as absolute_change,
    case
        when prior_value = 0 then null
        else round((value - prior_value) / abs(prior_value) * 100, 4)
    end                            as pct_change
from versions
where prior_value is not null
  and value <> prior_value

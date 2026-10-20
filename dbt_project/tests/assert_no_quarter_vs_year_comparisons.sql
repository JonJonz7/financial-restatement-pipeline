/*
    Regression test for the v1 grain bug: a 3-month quarter must never be
    compared with a 12-month year that ends on the same day. Every
    restatement compares two facts with the same period_start.
*/
select r.restatement_id
from {{ ref('fct_restatements') }} r
join {{ ref('stg_financial_facts') }} f
  on f.accession_number = r.original_accession_number
 and f.cik = r.cik and f.metric = r.metric and f.unit = r.unit
 and f.period_end = r.period_end
 and f.value = r.original_value
where f.period_start is distinct from r.period_start
  and not exists (
      select 1 from {{ ref('stg_financial_facts') }} g
      where g.accession_number = r.original_accession_number
        and g.cik = r.cik and g.metric = r.metric and g.unit = r.unit
        and g.period_end = r.period_end and g.value = r.original_value
        and g.period_start is not distinct from r.period_start
  )

/*
    Every restatement must tie back to two real facts in staging: the
    original and the restated value, at the same full grain, and the two
    must differ. Returns offending rows (a passing test returns none).
*/
with r as (select * from {{ ref('fct_restatements') }}),
f as (select * from {{ ref('stg_financial_facts') }})

select r.restatement_id
from r
left join f orig
  on orig.cik = r.cik and orig.taxonomy = r.taxonomy and orig.metric = r.metric
 and orig.unit = r.unit and orig.period_end = r.period_end
 and orig.period_start is not distinct from r.period_start
 and orig.accession_number = r.original_accession_number
left join f rest
  on rest.cik = r.cik and rest.taxonomy = r.taxonomy and rest.metric = r.metric
 and rest.unit = r.unit and rest.period_end = r.period_end
 and rest.period_start is not distinct from r.period_start
 and rest.accession_number = r.restatement_accession_number
where orig.value is null
   or rest.value is null
   or abs(orig.value - r.original_value) > 0.01
   or abs(rest.value - r.restated_value) > 0.01
   or abs(r.original_value - r.restated_value) < 0.01

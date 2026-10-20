/*
    fct_restatements
    ---------------------------------------------------------------
    Detected restatements with severity and type.

    restatement_type:
      AMENDMENT  the new value came in an amended filing (10-K/A, 10-Q/A):
                 the company formally corrected a report.
      RECAST     the new value appeared as a comparative in a later regular
                 report. Often a reclassification (e.g. discontinued
                 operations), sometimes a quiet correction. Worth a look.

    severity comes from the materiality_thresholds seed (see macros/severity.sql).
    Grain: one row per value change (cik, taxonomy, metric, unit,
    period_start, period_end, restatement_accession_number).
*/
select
    {{ generate_surrogate_key([
        'cik', 'taxonomy', 'metric', 'unit', 'period_start', 'period_end',
        'restatement_accession_number'
    ]) }}                                                            as restatement_id,
    cik,
    taxonomy,
    metric,
    unit,
    period_start,
    period_end,
    period_type,
    original_value,
    restated_value,
    absolute_change,
    pct_change,
    original_filed_date,
    restatement_filed_date,
    original_accession_number,
    restatement_accession_number,
    restatement_form_type,
    case when restatement_form_type like '%/A' then 'AMENDMENT' else 'RECAST' end as restatement_type,
    date_diff('day', original_filed_date, restatement_filed_date)     as days_to_restatement,
    {{ severity('pct_change', 'absolute_change', 'unit') }}          as severity
from {{ ref('int_filing_comparisons') }}

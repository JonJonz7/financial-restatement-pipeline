/*
    fct_restatements
    ---------------------------------------------------------------
    Final restatement fact table.

    Business logic:
      - Sources from int_filing_comparisons (which already filters
        to rows where values differ between filings).
      - Adds severity classification via the materiality_threshold
        macro (MATERIAL / NOTABLE / MINOR).
      - Computes days_to_restatement: the number of calendar days
        between the original filing and the restatement filing.
        Longer gaps may indicate the restatement was discovered
        during a subsequent audit cycle.
      - Generates a unique restatement_id for downstream joins.

    Grain: one row per (cik, metric, period_end, restatement_filed_date).
*/

with restatements as (

    select
        -- Surrogate key for this restatement event
        {{ generate_surrogate_key([
            'cik',
            'metric',
            'period_end',
            'restatement_filed_date'
        ]) }} as restatement_id,

        cik,
        metric,
        period_end,
        original_value,
        restated_value,
        original_filed_date,
        restatement_filed_date,
        restatement_form_type,
        restatement_accession_number,
        absolute_change,
        pct_change,

        -- Calendar days between original filing and restatement
        restatement_filed_date - original_filed_date
            as days_to_restatement,

        -- Severity classification using the reusable macro
        {{ materiality_threshold('pct_change', 'absolute_change') }}
            as severity

    from {{ ref('int_filing_comparisons') }}

)

select * from restatements

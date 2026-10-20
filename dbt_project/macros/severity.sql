{#
    severity(pct_col, abs_col, unit_col)
    ------------------------------------------------------------------
    Classifies a change as MATERIAL / NOTABLE / MINOR using the
    materiality_thresholds seed: the single source of truth, also read by
    detection/thresholds.py, so SQL and Python can never disagree.
    The dollar threshold applies only when the unit is USD (a change of
    2,000,000 shares is not "$2M").
#}
{% macro severity(pct_col, abs_col, unit_col) %}
    (
        select t.severity
        from {{ ref('materiality_thresholds') }} t
        where abs(coalesce({{ pct_col }}, 0)) >= t.min_pct_change
           or ({{ unit_col }} = 'USD' and abs(coalesce({{ abs_col }}, 0)) >= t.min_absolute_usd
               and t.min_absolute_usd > 0)
        order by t.severity_rank desc
        limit 1
    )
{% endmacro %}

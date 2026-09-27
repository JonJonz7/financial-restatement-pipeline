/*
    Macro: materiality_threshold
    ---------------------------------------------------------------
    Returns a severity classification (MATERIAL / NOTABLE / MINOR)
    based on the percentage change and absolute dollar change of a
    restatement or anomaly.

    Thresholds (aligned with seeds/materiality_thresholds.csv):
      MATERIAL  ->  pct_change >= 5%   OR  absolute_change >= $1,000,000
      NOTABLE   ->  pct_change >= 1%   OR  absolute_change >= $100,000
      MINOR     ->  anything else that is a detectable change

    Usage:
        {{ materiality_threshold('pct_change', 'absolute_change') }}
*/

{% macro materiality_threshold(pct_change, absolute_change) %}

    case
        when abs({{ pct_change }}) >= 5.0
          or abs({{ absolute_change }}) >= 1000000
            then 'MATERIAL'

        when abs({{ pct_change }}) >= 1.0
          or abs({{ absolute_change }}) >= 100000
            then 'NOTABLE'

        else 'MINOR'
    end

{% endmacro %}

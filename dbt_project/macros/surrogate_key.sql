/*
    Macro: generate_surrogate_key
    ---------------------------------------------------------------
    Creates a deterministic hash-based surrogate key from a list of
    column names. Null-safe: coalesces nulls to the literal string
    '___NULL___' before hashing so that nulls produce a consistent
    key rather than propagating null through the hash.

    Usage:
        {{ generate_surrogate_key(['cik', 'metric', 'period_end']) }}
*/

{% macro generate_surrogate_key(fields) %}

    md5(
        {%- for field in fields %}
            coalesce(cast({{ field }} as varchar), '___NULL___')
            {%- if not loop.last %} || '|' || {% endif -%}
        {%- endfor %}
    )

{% endmacro %}

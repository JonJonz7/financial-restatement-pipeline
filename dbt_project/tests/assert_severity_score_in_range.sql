/*
    Singular test: assert_severity_score_in_range
    ---------------------------------------------------------------
    Standalone fallback for the dbt_utils.accepted_range test on
    fct_anomalies.severity_score.

    Every anomaly's severity_score must be between 0 and 100
    inclusive. Returns rows that violate this constraint.
    A passing test returns 0 rows.
*/

select
    anomaly_id,
    anomaly_type,
    cik,
    severity_score
from {{ ref('fct_anomalies') }}
where
    severity_score is null
    or severity_score < 0
    or severity_score > 100

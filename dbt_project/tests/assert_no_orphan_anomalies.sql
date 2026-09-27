/*
    Singular test: assert_no_orphan_anomalies
    ---------------------------------------------------------------
    Every anomaly in fct_anomalies must have a corresponding company
    in dim_companies. An orphan anomaly means:
      - The CIK in the anomaly table doesn't exist in dim_companies
      - This could indicate a join issue, a missing filing, or a
        data quality problem upstream

    The query returns orphaned rows (anomalies without a matching
    company). A passing test returns 0 rows.
*/

select
    a.anomaly_id,
    a.anomaly_type,
    a.cik,
    a.metric,
    a.period_end,
    a.severity,
    a.severity_score
from {{ ref('fct_anomalies') }} a
left join {{ ref('dim_companies') }} c
    on a.cik = c.cik
where c.cik is null

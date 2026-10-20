/*
    Every anomaly must belong to a known company in dim_companies.
    An orphan means a fact was loaded for a CIK whose profile is missing.
*/
select a.anomaly_id, a.anomaly_type, a.cik
from {{ ref('fct_anomalies') }} a
left join {{ ref('dim_companies') }} c on a.cik = c.cik
where c.cik is null

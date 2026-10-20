/*
    stg_financial_facts
    One XBRL fact as reported in one filing.

    Grain: (cik, taxonomy, metric, unit, period_start, period_end, accession_number)
    -- the same key bronze uses (fact_key). period_start is NULL for instant
    facts (balance sheet). duration_days separates a 3-month quarter from a
    12-month year that end on the same day: they are DIFFERENT facts.
*/
select
    cast(fact_key as varchar)          as fact_key,
    cast(cik as varchar)               as cik,
    cast(taxonomy as varchar)          as taxonomy,
    cast(metric as varchar)            as metric,
    cast(unit as varchar)              as unit,
    cast(period_start as date)         as period_start,
    cast(period_end as date)           as period_end,
    case
        when period_start is null then 0
        else date_diff('day', cast(period_start as date), cast(period_end as date)) + 1
    end                                as duration_days,
    case
        when period_start is null then 'instant'
        when date_diff('day', cast(period_start as date), cast(period_end as date)) between 80 and 100 then 'quarter'
        when date_diff('day', cast(period_start as date), cast(period_end as date)) between 350 and 380 then 'year'
        else 'other'
    end                                as period_type,
    cast(value as double)              as value,
    cast(form as varchar)              as form_type,
    cast(filed_date as date)           as filed_date,
    cast(accession_number as varchar)  as accession_number,
    cast(fiscal_year as integer)       as fiscal_year,
    cast(fiscal_period as varchar)     as fiscal_period,
    cast(frame as varchar)             as frame,
    cast(ingested_at as timestamp)     as ingested_at
from {{ source('bronze', 'raw_financial_facts') }}
where value is not null

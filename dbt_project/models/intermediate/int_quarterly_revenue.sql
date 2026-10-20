/*
    int_quarterly_revenue
    ---------------------------------------------------------------
    One revenue number per company per fiscal quarter, using the LATEST
    filed version of each fact (restatements included).

    Companies use different revenue tags; the first available in priority
    order is used. Most companies never tag Q4 separately: it is derived
    as full year minus Q1-Q3 when all four are available.

    Grain: (cik, period_end) for quarters.
*/
with tags as (
    select * from (values
        ('Revenues', 1),
        ('RevenueFromContractWithCustomerExcludingAssessedTax', 2),
        ('RevenueFromContractWithCustomerIncludingAssessedTax', 3),
        ('SalesRevenueNet', 4)
    ) as t(metric, priority)
),

latest as (
    select f.cik, f.period_start, f.period_end, f.period_type, f.value, f.filed_date, t.priority
    from {{ ref('stg_financial_facts') }} f
    join tags t on t.metric = f.metric
    where f.taxonomy = 'us-gaap' and f.unit = 'USD' and f.period_type in ('quarter', 'year')
    qualify row_number() over (
        partition by f.cik, f.period_start, f.period_end
        order by t.priority, f.filed_date desc
    ) = 1
),

quarters as (
    select cik, period_start, period_end, value as revenue, false as is_derived
    from latest where period_type = 'quarter'
),

years as (
    select cik, period_start, period_end, value as revenue
    from latest where period_type = 'year'
),

derived_q4 as (
    -- Q4 = full year - the three earlier quarters inside the same year
    select
        y.cik,
        y.period_end - interval 91 day as period_start,
        y.period_end,
        y.revenue - sum(q.revenue)     as revenue,
        true                           as is_derived
    from years y
    join quarters q
      on q.cik = y.cik
     and q.period_start >= y.period_start
     and q.period_end < y.period_end
    where not exists (
        select 1 from quarters q4 where q4.cik = y.cik and q4.period_end = y.period_end
    )
    group by y.cik, y.period_end, y.revenue
    having count(*) = 3
)

select cik, cast(period_start as date) as period_start, period_end, revenue, is_derived
from quarters
union all
select cik, cast(period_start as date), period_end, revenue, is_derived
from derived_q4

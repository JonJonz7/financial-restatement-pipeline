/*
    int_scale_checks
    ---------------------------------------------------------------
    Unit-scale errors: a quarter tagged in thousands instead of dollars
    looks 1,000x too small. Each quarter is compared with the company's
    median quarter; anything below 5% or above 20x of it is flagged.

    Grain: (cik, period_end). Only flagged quarters are returned.
*/
with medians as (
    select cik, median(revenue) as median_revenue
    from {{ ref('int_quarterly_revenue') }}
    where revenue > 0
    group by cik
)

select
    q.cik,
    q.period_end,
    q.revenue,
    m.median_revenue,
    round(q.revenue / m.median_revenue, 6) as ratio_to_median
from {{ ref('int_quarterly_revenue') }} q
join medians m using (cik)
where q.revenue / m.median_revenue < 0.05
   or q.revenue / m.median_revenue > 20

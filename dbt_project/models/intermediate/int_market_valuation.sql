/*
    int_market_valuation
    ---------------------------------------------------------------
    Cross-source check: SEC numbers vs the stock market.

    market cap at quarter end = closing price on the last trading day on or
    before period_end (ASOF join) x shares outstanding reported to the SEC
    closest to that date. Price-to-sales uses annualised quarterly revenue.

    Each company is compared with ITSELF over time using a robust z-score
    (median and MAD instead of mean and standard deviation, so one bad value
    can't hide itself by inflating the spread). |robust_z| > 3.5 is flagged.

    Grain: (cik, period_end).
*/
with revenue as (
    select q.*, c.ticker
    from {{ ref('int_quarterly_revenue') }} q
    join {{ ref('stg_companies') }} c using (cik)
    where q.revenue > 0
),

priced as (
    select r.*, p.trade_date as price_date, p.close_price
    from revenue r
    asof join {{ ref('stg_market_data') }} p
      on p.ticker = r.ticker
     and p.trade_date <= r.period_end
),

shares as (
    select cik, period_end as shares_date, value as shares_outstanding
    from {{ ref('stg_financial_facts') }}
    where taxonomy = 'dei' and metric = 'EntityCommonStockSharesOutstanding'
    qualify row_number() over (partition by cik, period_end order by filed_date desc) = 1
),

valued as (
    select
        p.*,
        s.shares_outstanding,
        s.shares_date,
        p.close_price * s.shares_outstanding                       as market_cap,
        p.close_price * s.shares_outstanding / (p.revenue * 4)     as price_to_sales
    from priced p
    join shares s
      on s.cik = p.cik
     and s.shares_date between p.period_end - interval 30 day and p.period_end + interval 120 day
    qualify row_number() over (
        partition by p.cik, p.period_end
        order by abs(date_diff('day', p.period_end, s.shares_date))
    ) = 1
),

logged as (
    select *, ln(price_to_sales) as log_ps from valued where price_to_sales > 0
),

stats as (
    select cik, median(log_ps) as med, median(abs(log_ps - med_all)) as mad
    from (select cik, log_ps, median(log_ps) over (partition by cik) as med_all from logged)
    group by cik
)

select
    l.cik, l.ticker, l.period_end, l.revenue, l.is_derived, l.price_date, l.close_price,
    l.shares_outstanding, l.market_cap, l.price_to_sales,
    case when s.mad > 0 then round(0.6745 * (l.log_ps - s.med) / s.mad, 3) end as robust_z,
    coalesce(abs(0.6745 * (l.log_ps - s.med) / nullif(s.mad, 0)) > 3.5, false)  as is_outlier
from logged l
join stats s using (cik)

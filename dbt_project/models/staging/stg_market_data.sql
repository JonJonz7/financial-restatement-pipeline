/*
    stg_market_data
    ---------------------------------------------------------------
    Staging model for market / pricing data pulled from external
    sources (e.g. Yahoo Finance, Alpha Vantage).

    Business logic:
      - Casts raw columns to proper types.
      - Deduplicates by (ticker, date), keeping the most recently
        ingested row when duplicates exist (e.g. from overlapping
        API pulls).
*/

with source as (

    select * from {{ source('bronze', 'raw_market_data') }}

),

cleaned as (

    select
        cast(ticker         as varchar)     as ticker,
        cast(date           as date)        as date,
        cast(open           as double)      as open_price,
        cast(high           as double)      as high_price,
        cast(low            as double)      as low_price,
        cast(close          as double)      as close_price,
        cast(volume         as bigint)      as volume,
        cast(market_cap     as double)      as market_cap,
        cast(ingested_at    as timestamp)   as ingested_at
    from source

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by ticker, date
            order by ingested_at desc
        ) as _row_num
    from cleaned

)

select
    ticker,
    date,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    market_cap,
    ingested_at
from deduplicated
where _row_num = 1

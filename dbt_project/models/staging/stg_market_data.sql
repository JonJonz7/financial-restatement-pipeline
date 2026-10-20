/*
    stg_market_data
    Daily prices. Grain: (ticker, date).
*/
select
    upper(cast(ticker as varchar)) as ticker,
    cast(date as date)             as trade_date,
    cast(open as double)           as open_price,
    cast(high as double)           as high_price,
    cast(low as double)            as low_price,
    cast(close as double)          as close_price,
    cast(volume as bigint)         as volume
from {{ source('bronze', 'raw_market_data') }}
where close is not null

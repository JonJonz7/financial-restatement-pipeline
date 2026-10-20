/*
    int_balance_sheet_checks
    ---------------------------------------------------------------
    The accounting equation: Assets = Liabilities + Stockholders' Equity.
    In XBRL, Assets must equal LiabilitiesAndStockholdersEquity in every
    filing. A difference means a tagging error or a data problem upstream.

    Grain: (cik, period_end, accession_number). Only breaks are returned.
*/
with bs as (
    select
        cik,
        period_end,
        accession_number,
        filed_date,
        max(case when metric = 'Assets' then value end)                           as assets,
        max(case when metric = 'LiabilitiesAndStockholdersEquity' then value end) as liabilities_and_equity
    from {{ ref('stg_financial_facts') }}
    where taxonomy = 'us-gaap'
      and unit = 'USD'
      and metric in ('Assets', 'LiabilitiesAndStockholdersEquity')
    group by cik, period_end, accession_number, filed_date
)

select
    *,
    assets - liabilities_and_equity as difference,
    round((assets - liabilities_and_equity) / nullif(abs(assets), 0) * 100, 4) as pct_difference
from bs
where assets is not null
  and liabilities_and_equity is not null
  and abs(assets - liabilities_and_equity) >= 1   -- tolerate rounding to the dollar

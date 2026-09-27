/*
    dim_companies
    ---------------------------------------------------------------
    Company dimension table built from staging filing metadata.

    Grain: one row per CIK (unique company).

    Provides a look-up for company attributes and filing activity
    summary that mart fact tables can join to.
*/

with filing_stats as (

    select
        cik,

        -- Company name: take the most recent filing's company name
        -- (companies sometimes change their legal name)
        max_by(company_name, filed_date)    as company_name,

        -- Ticker: take the most recent non-null ticker
        max_by(ticker, filed_date)          as ticker,

        -- SIC industry code
        max_by(sic_code, filed_date)        as sic_code,

        -- Filing activity summary
        min(filed_date)                     as first_filing_date,
        max(filed_date)                     as latest_filing_date,
        count(distinct accession_number)    as total_filings,

        -- Form type breakdown
        count(distinct case when form_type in ('10-K', '10-K/A')
            then accession_number end)      as annual_filings,
        count(distinct case when form_type in ('10-Q', '10-Q/A')
            then accession_number end)      as quarterly_filings

    from {{ ref('stg_filings') }}
    group by cik

)

select
    cik,
    company_name,
    ticker,
    sic_code,
    first_filing_date,
    latest_filing_date,
    total_filings,
    annual_filings,
    quarterly_filings
from filing_stats

# Alert report (2026-10-20)

8 alerts: 5 RESTATEMENT, 1 SCALE_ERROR, 1 BALANCE_SHEET_BREAK, 1 VALUATION_OUTLIER

| Priority | Company | Type | Metric | Period end | Reported | Expected / prior | Change | Action |
|---:|---|---|---|---|---:|---:|---:|---|
| 100 | CDRH | SCALE_ERROR | Revenue (quarter) | 2022-09-30 | 338,967 | 331,490,500 | -99.90% | IMMEDIATE REVIEW |
| 57 | HRBL | BALANCE_SHEET_BREAK | Assets | 2023-12-31 | 428,416,000 | 418,416,000 | +2.33% | HIGH PRIORITY |
| 55 | NWDV | RESTATEMENT | NetIncomeLoss | 2023-12-31 | 148,465,000 | 157,942,000 | -6.00% | HIGH PRIORITY |
| 55 | NWDV | RESTATEMENT | Revenues | 2023-12-31 | 1,044,056,000 | 1,110,698,000 | -6.00% | HIGH PRIORITY |
| 40 | HRBL | RESTATEMENT | Revenues | 2022-12-31 | 504,496,000 | 507,031,000 | -0.50% | MONITOR |
| 30 | HRBL | RESTATEMENT | NetIncomeLoss | 2022-12-31 | 27,478,000 | 28,039,000 | -2.00% | MONITOR |
| 30 | HRBL | RESTATEMENT | OperatingIncomeLoss | 2022-12-31 | 34,782,000 | 35,492,000 | -2.00% | MONITOR |
| 10 | CDRH | VALUATION_OUTLIER | PriceToSales | 2022-09-30 | 5,222 |  |  | LOW PRIORITY |

Why each alert scored what it did:

- **CDRH Revenue (quarter) 2022-09-30** (100): Scale Error (+30) | Very large change: 99.9% (+35) | Hundred-million change: $331,151,533 (+18) | Key metric: Revenue (quarter) (+15) | Classified MATERIAL (+10)
- **HRBL Assets 2023-12-31** (57): Balance Sheet Break (+25) | Notable change: 2.3% (+10) | Million-dollar change: $10,000,000 (+12) | Classified MATERIAL (+10)
- **NWDV NetIncomeLoss 2023-12-31** (55): Material change: 6.0% (+18) | Million-dollar change: $9,477,000 (+12) | Key metric: NetIncomeLoss (+15) | Classified MATERIAL (+10)
- **NWDV Revenues 2023-12-31** (55): Material change: 6.0% (+18) | Million-dollar change: $66,642,000 (+12) | Key metric: Revenues (+15) | Classified MATERIAL (+10)
- **HRBL Revenues 2022-12-31** (40): Million-dollar change: $2,535,000 (+12) | Key metric: Revenues (+15) | Classified MATERIAL (+10)
- **HRBL NetIncomeLoss 2022-12-31** (30): Notable change: 2.0% (+10) | Six-figure change: $561,000 (+5) | Key metric: NetIncomeLoss (+15)
- **HRBL OperatingIncomeLoss 2022-12-31** (30): Notable change: 2.0% (+10) | Six-figure change: $710,000 (+5) | Key metric: OperatingIncomeLoss (+15)
- **CDRH PriceToSales 2022-09-30** (10): Valuation Outlier (+10)

# What real recessions look like, against the model's stress control

12 November 2026. "Seen" means the number was in a summary of the cited page's text; the raw page was not
read line by line.
Nothing in the model was changed because of this file.

## 1. The model's stress control in the same units

The control adds 0 to 2 points to the monthly chance that a job loses its wage, for 12 months (months 25 to 36),
on top of the normal 0.55% a month. Spell lengths keep their normal law (median 11.5 weeks, mean 24.8 weeks).
Measured share of jobs without a wage (S0, r_out 4.4%, a0 0.2, three development seeds, 11 Nov map; the job-loss
path is the same in every arm):

| Stress level, points a month | 0 | 0.5 | 1 | 1.5 | 2 |
|---|---|---|---|---|---|
| Peak share of jobs without a wage, % | 2.4 | 3.4 | 5.0 | 6.8 | 8.2 |
| Mean over the stress year, % | 2.0 | 3.1 | 4.3 | 5.7 | 6.7 |
| Mean over the following year, % | 2.1 | 2.4 | 2.8 | 3.4 | 3.9 |

## 2. Labour market, sourced

| Measure | Normal years | 2007-09 recession | 2020 | Source |
|---|---|---|---|---|
| Unemployment rate, % | 3.5 (Feb 2020), 5.0 (Dec 2007) | 10.0 (Oct 2009); 10.8 (Nov-Dec 1982) | 14.8 (Apr 2020) | FRED UNRATE, seen |
| Job losers, % of labour force (U-2) | 1.6 to 2.1 (2018-19, 2024-25) | 6.5 (Sep-Oct 2009) | 13.2 (Apr 2020), 4.5 by Dec | FRED U2RATE, seen |
| Layoffs and discharges, % of jobs a month | 1.0 to 1.3 | 2.0 (Apr 2009) | 8.6 (Mar), 7.0 (Apr), 1.6 (May) | FRED JTSLDR, seen |
| Weeks unemployed, mean / median | 20.5 / 9.5 (Jan 2019); 21 to 25 / 9.5 to 11.4 (2025) | 40.7 (Jul 2011) / 25.2 (Jun 2010) | | FRED UEMPMEAN, UEMPMED, seen |

URLs: https://fred.stlouisfed.org/series/UNRATE, /U2RATE, /JTSLDR, /UEMPMEAN, /UEMPMED.

The series that matches the model's measure is U-2, job losers: the model's normal stock of 2.0% of jobs sits
on its normal level (1.6 to 2.1%). The 2007-09 peak of 6.5% lies between the model's levels of 1 point (5.0%)
and 1.5 points (6.8%); the top level, 2 points (8.2%), is beyond it (the 1981-82 value of U-2 was not
checked). April 2020 was a one-month shock of about 11 points that mostly reversed within months, a different
shape from a year of raised job loss. So the range of job loss is wide enough for a recession of the 2007-09
kind.

Two things a real recession has that the control does not: spells get longer (mean 40 weeks at the 2011 peak,
against the model's 24.8 at every level), and loans stop being repaid for good (section 3).

## 3. Credit losses, sourced (all commercial banks, % of balances a year, charge-offs net of recoveries)

| Loans | Normal years (2015-19) | Peak | Source |
|---|---|---|---|
| Credit cards | 2.9 to 3.8 | 10.54 (2009 Q4) | FRED CORCCACBS, seen |
| All consumer loans | 1.74 to 2.36 | 6.60 (2010 Q1) | FRED CORCACBS, seen |
| Other consumer loans (column read by inference) | 0.7 to 0.9 | 3.36 (2009 Q2) | Federal Reserve charge-off release |
| Business loans | 0.17 to 0.45 | 2.57 (2009 Q3) | FRED CORBLACBS, seen |

Federal Reserve release: https://www.federalreserve.gov/releases/chargeoff/chgallsa.htm

Not found: a small-business loss rate for 2008-10, the share of the unemployed who miss debt payments, and a
monthly employment-to-unemployment probability for 2008-09 (the 2% in circulation has no source found).

## 4. What the model's pool loses (final rules, commit 5fec7c0, M1, r_out 4.4%, no stress)

| | a0 0.2 | a0 0.6 |
|---|---|---|
| Instalment loans written off, five years, $ a person | 32 | 31 |
| Recovered later | 9 | 13 |
| Net, as % of the instalment book a year | 0.9 | 0.3 |
| Bridges written off / recovered, five years | 3 / 3 | 2 / 2 |
| Learned loss in the instalment coupon, points, by year | 0, 0, 0.2, 0, 0.9 | 0, 0, 0.05, 0.03, 0.3 |

The model has no permanent default: a debt written off stays owed and is collected when the borrower has money
again. No forced test run leaves a pool loan unpaid for 90 days at up to 50 points of stress. So the stress
control interrupts incomes; it cannot make a loan uncollectable. Banks' prices in the model (cards at about 22%,
personal loans by score) are taken from data and include the losses banks really bear; the pool's price holds
almost none.

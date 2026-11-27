"""The calendar and every sourced or declared number the engine reads.

Each constant keeps its source in the comment beside it. A few small functions sit here because constants
below them are computed with them when the module loads.
"""
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm


# --------------------------------------------------------------------------------------------------------------------
# Calendar and sourced parameters. Every number below is sourced or declared; the comment names its source.
# --------------------------------------------------------------------------------------------------------------------
DAYS = 30                                      # days per model month
CYCLE_DAYS = np.array([1, 7, 15, 30, 60])      # billing cycles in days: daily, weekly, fortnightly, monthly, 60-day
# Pay periods of jobs: BLS pay frequencies, shares of establishments (weekly 27.0%, every two weeks 43.0%, twice a
# month 19.8%, monthly 10.3%; they sum to 100.1 and are normalised). Twice a month is every 15 days of the 30-day
# month and every two weeks every 14 days.
PAY_DAYS = np.array([7, 14, 15, 30])
PAY_SHARES = np.array([27.0, 43.0, 19.8, 10.3])
# Outside safe return: Fed Distributional Financial Accounts, 2026 Q2, $ millions, by wealth percentile group: total
# deposits (FRED WFRBLDEB50, WFRBLDEN40, WFRBLDEN09, WFRBLTOP1DE) and money market fund shares (FRED WFRBLB50088,
# WFRBLN40061, WFRBLN09034, WFRBLT01007). Deposits earn the FDIC national savings rate (FRED SNDR, October 2026:
# 0.38%/yr); money market fund shares earn the T-bill control rho_H.
DFA_GROUP_UPPER = np.array([0.50, 0.90, 0.99, 1.00])
DFA_DEPOSITS = np.array([777430.0, 5090389.0, 5014713.0, 3323113.0])
DFA_MONEY_MARKET = np.array([55950.0, 1021646.0, 2075552.0, 1957779.0])
# Who owns the firms beyond the household economy (``Economy.edge`` "conserved"): Fed Distributional Financial
# Accounts, 2026 Q2, $ millions, by wealth percentile group, corporate equities and mutual fund shares (FRED
# WFRBLB50095, WFRBLN40068, WFRBLN09041, WFRBLT01014): shares 0.58%, 11.39%, 37.15% and 50.88%.
DFA_EQUITIES = np.array([374196.0, 7362060.0, 24014368.0, 32889546.0])
FDIC_SAVINGS_RATE = 0.0038 / 12
# Outside prices follow r_out, the same in every arm, from their October 2026 levels, when three-month bills paid
# 4.05% a year (BILL_ANCHOR): the savings deposit rate moves by 0.08 of a change in r_out (FRED, January 2022 to
# January 2024; 0.46 a sensitivity), floored at 0.06% a year (DEPOSIT_FLOOR, a month); card and business rates follow
# prime one for one at today's margins; new vehicle and personal loans follow their own pass-throughs, while existing
# loans keep their sealed rates (``Economy.linked_rates`` and the pass-throughs beside it). r_out runs on the model's
# basis, a nominal rate a year credited monthly, so every anchor is the bill on that basis: 4.05% on a discount basis
# is 4.135% (``BILL_MONTHLY``, below), the anchor ``outside_prices`` reads.
BILL_ANCHOR = 0.0405
DEPOSIT_FLOOR = 0.0006 / 12
# Buffer replay: the buffer sizes a person compares, in months of its own spending (declared grid).
BUFFER_MULTIPLES = np.array([0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0])
# Payment routes recorded in the payment log (network figure): plain E transfer, card, or P/USDC between participants.
ROUTE_E, ROUTE_CARD, ROUTE_P = 0, 1, 2
# Wage contracts: labour income is 58.3% of receipts (the labour share behind the billing-cycle mix).
LABOUR_SHARE = 0.583
# Obligation kinds. A LATE_WAGE is an unpaid wage re-queued to its job's next pay date (to the recipient's next billing
# date with ``Economy.pay_dates`` off). An OUTSIDE_WAGE is the wage of a job's spell day after a distress year's extra
# layoff (the harsh stress): its payer still owes it on the job's pay dates and pays it out of the household economy,
# and its worker receives nothing; a LATE_OUTSIDE_WAGE is one left unpaid and re-queued, as a LATE_WAGE is.
SERVICE, WAGE, SHOCK, LATE_WAGE, OUTSIDE_WAGE, LATE_OUTSIDE_WAGE = 0, 1, 2, 3, 4, 5
# Conversion fee (Fed Regulation II debit cap): 21 cents plus 0.05% of value (12 CFR 235.3(b)) plus the 1 cent
# fraud-prevention adjustment (12 CFR 235.4), per conversion, the cents scaled to the $142 average payment: 0.2049%.
CONVERSION_FEE = 0.0005 + 0.22 / 142
# SHED 2025 (Economic Well-Being of U.S. Households in 2025, May 2026): share with a major unexpected
# expense in the prior 12 months (vehicle 30%, house or appliance 22%, medical 21%); median cost $1,000-1,999,
# taken at its geometric midpoint over BLS CEX 2023 mean monthly spending ($6,440).
SHOCK_ANNUAL = np.array([0.30, 0.22, 0.21])
SHOCK_SIZE = (1000.0 * 1999.0) ** 0.5 / 6440.0
# Cards and credit scores: income brackets, card ownership, FICO bands and card APRs (sources in docs/PARAMETERS.csv).
INCOME_BRACKETS = np.array([17687, 21446, 36584, 61383]) / 137100
# Has a credit card, by family income under $25,000, $25,000 to $49,999, $50,000 to $99,999 and $100,000 or more:
# 46, 71, 88 and 97% (Fed, Economic Well-Being of U.S. Households in 2025, May 2026, Table 40), the same survey year as
# the engine's other inputs from that survey.
CARD_OWNERSHIP = np.array([0.46, 0.71, 0.88, 0.97])
FICO_EDGES = np.array([300, 580, 670, 740, 800, 851])
FICO_CUMULATIVE = np.cumsum([0.0, 0.147, 0.149, 0.201, 0.275, 0.228])
CARD_TIER_SCORES = np.array([620, 720])
# Card APRs by score tier (620 and below, 620 to 719, 720 and above): median purchase APRs of large issuers' cards,
# 28.49, 28.20 and 22.99% (CFPB, Terms of Credit Card Plans data report, February 2024, on first-half 2023 data).
CARD_APR = np.array([0.2849, 0.2820, 0.2299])
# Credit score and income: a Spearman rank correlation of 0.291 between VantageScore 2.0 and income (FEDS Notes, "Are
# Income and Credit Scores Highly Correlated?", 13 Aug 2018, Table 1). The score is drawn by a Gaussian link on income
# rank (``cards_and_scores``), whose correlation rho gives a rank correlation (6 / pi) asin(rho / 2); rho = 2 sin(pi x
# 0.291 / 6) = 0.3036 gives 0.291.
SCORE_INCOME_CORRELATION = 2 * np.sin(np.pi * 0.291 / 6)
# Distress. Layoffs fall more often on lower incomes: relative risk is BLS unemployment by
# education (August 2026, ages 25+: no diploma 4.7%, high school 4.4%, some college or associate 3.7%, bachelor's or
# more 2.7%) mixed through each income bracket's householder education (Census HINC-01, CPS ASEC 2026, incomes in
# 2025, thousands of householders 25+; rows those four groups, columns the four income brackets above).
UNEMPLOYMENT_BY_EDUCATION = np.array([0.047, 0.044, 0.037, 0.027])
HOUSEHOLDS_BY_EDUCATION = np.array([[3251, 2375, 2244, 1419], [6192, 7360, 9977, 9305], [4265, 6098, 10560, 13742],
                                    [3000, 4473, 11799, 35491]], float)
# BLS unemployment duration in September 2026 (FRED UEMPMED, median 11.5 weeks; UEMPMEAN, mean 24.8 weeks), which
# describes spells still in progress. With ``Economy.completed_spells`` off, spell lengths read it as completed lengths:
# log-normal with median 80.5 days and sigma = sqrt(2 ln(mean / median)), a completed mean of 174 days.
SPELL_MEDIAN_DAYS = 11.5 * 7
SPELL_SIGMA = (2 * np.log(24.8 / 11.5)) ** 0.5
SPELL_MEAN_DAYS = 24.8 * 7


def completed_spell_law(median_age, mean_age):
    """The log-normal law of completed spell lengths whose spells in progress have the given median and mean age, in
    days: (the completed median exp(mu), sigma).

    In a steady state a spell's elapsed length a has density S(a) / E[L], S the survival of the completed length L. Its
    mean is E[L^2] / (2 E[L]) = exp(mu + 1.5 sigma^2) / 2, which sets mu for each sigma; its median m solves
    E[min(L, m)] / E[L] = 1/2, with E[min(L, m)] = m (1 - Phi(z)) + E[L] Phi(z - sigma) and z = (ln m - mu) / sigma,
    and the share is rising in sigma, so one root.
    """
    mu = lambda sigma: np.log(2 * mean_age) - 1.5 * sigma ** 2
    z = lambda sigma: (np.log(median_age) - mu(sigma)) / sigma
    half = lambda sigma: (median_age * norm.sf(z(sigma)) / np.exp(mu(sigma) + sigma ** 2 / 2)
                          + norm.cdf(z(sigma) - sigma) - 0.5)
    sigma = brentq(half, 0.1, 2.0)
    return float(np.exp(mu(sigma))), float(sigma)


# Spell lengths are completed lengths, log-normal and consistent with the BLS figures for spells in progress: a
# completed median of 61.4 days, sigma 1.074 and a mean of 109.4 days; 50.9% of spells outlast 60 days (59.4% when the
# figures are read as completed lengths). Solved once, here.
COMPLETED_SPELL_MEDIAN_DAYS, COMPLETED_SPELL_SIGMA = completed_spell_law(SPELL_MEDIAN_DAYS, SPELL_MEAN_DAYS)
# Normal job loss: every month in every arm, burn-in included, each job loses its wage with this monthly probability
# (times its earner's bracket weight), from its steady stock at month 0. With completed spells the stock is about 1.9%
# of jobs, by hand, close to today's job-loser stock of about 2.0% of payroll jobs.
JOB_LOSS = 0.0055
# Instalment credit: vehicle, personal and business loans (request rates, terms, sizes and rates).
REQUEST_RATE = np.array([0.347 / 60, 0.185 / 24, 0.37 / 12])
TERM_MONTHS = np.array([60, 24, 11])
# Household loan sizes scale with the person's spending: a request is the size times 12 times its monthly spending,
# so each dollar amount is over a year of mean spending, 12 x $6,440 (``MONTH_USD``, BLS CEX 2023), and a mean spender
# asks for exactly the source's dollars: a new vehicle $43,582 and a used one $27,528 (Experian, Q4 2025), a personal
# loan $7,000.
TERM_SIZE = np.array([(0.433 * 43582 + 0.567 * 27528) / (12 * 6440.0), 7000 / (12 * 6440.0),
                      (25e3 * 100e3) ** 0.5 / (100e3 * 1e6) ** 0.5])
BUSINESS_PRODUCT = np.array([False, False, True])
VEHICLE_NEW_SHARE = 0.433
VEHICLE_SIZE = np.array([43582 / (12 * 6440.0), 27528 / (12 * 6440.0)])
VEHICLE_TIER_SCORES = np.array([501, 601, 661, 781])
VEHICLE_APR = np.array([[0.1611, 0.1352, 0.0971, 0.0615, 0.0441], [0.2162, 0.1910, 0.1393, 0.0881, 0.0629]])
PERSONAL_SCORES = np.array([620, 640, 660, 680, 700, 720, 740])
PERSONAL_APR = np.array([0.1797, 0.1721, 0.1612, 0.1476, 0.1319, 0.1197, 0.1082])
BUSINESS_APR = 0.074
DTI_CAP = 0.43
# Loan book kinds: BRIDGE (pool or Comet bridging due on its covering date; card bridging too where no card limits
# apply), TERM (instalment loan), REVOLVE (unpaid card statement, and the card's fees, no due date), OVERDRAFT (rounding
# overdrafts at r_ext, no due date; failure fees too under the legacy rules), FEE_DEBT (an unpaid failure fee,
# interest-free and repaid first, no due date), CASH_ADVANCE (a card's cash advance for a non-card bill, at the cash
# APR, no due date, kept apart from REVOLVE so the monthly merge never reprices it) and CHARGED_OFF (a card balance
# charged off at 180 days past due: still owed, at no further interest, no due date).
BRIDGE, TERM, REVOLVE, OVERDRAFT, FEE_DEBT, CASH_ADVANCE, CHARGED_OFF = 0, 1, 2, 3, 4, 5, 6
WRITE_OFF_DAYS = 90      # a pool loan 90 days past due is written down to zero (legal debt remains)
LOSS_LAG_MONTHS = WRITE_OFF_DAYS // DAYS   # loss learning counts exposure once its losses could have been booked
LOAN_YEARS = 5           # term-loan age bands reported for write-offs and exposure: years 1 to 5 of a loan's life;
                         # and loan years, the year after launch a pool loan was made, the last taking any later year
                         # (at least this many: a run longer than 60 months has one a year)
C1_HORIZON_DAYS = 60     # a covering date must lie within two months (the longest billing cycle)
# Every billing cycle and pay period divides this many days (420), so each person's expected receipts repeat with it:
# the covering date of an outside loan beyond the horizon extends the schedule by whole repeats.
C1_PERIOD_DAYS = int(np.lcm.reduce(np.concatenate([CYCLE_DAYS, PAY_DAYS])))
# Scale of the economy for the real Comet market: one model unit is one month of mean
# spending, $6,440 (BLS CEX 2023: $77,280 a year), and the N people stand for the 134.6 million US consumer units
# (BLS CEX 2023), the population the calibration describes.
MONTH_USD = 6440.0
CENT = 0.01 / MONTH_USD   # one cent in the model's money; a record of payments counts nothing smaller
# Starting cushions: the Fed survey's liquid savings at a rank of the population, in dollars
# (Economic Well-Being of U.S. Households in 2025: 18% could not cover $100 from savings, 30% not $500, about half not
# a $2,000 emergency, 38% could cover $5,000 or more), interpolated from $0; above the last point it sets no level.
SURVEY_RANKS = np.array([0.0, 0.18, 0.30, 0.50, 0.62])
SURVEY_SAVINGS = np.array([0.0, 100.0, 500.0, 2000.0, 5000.0])
# A failed payment: a flat fee per failed payment, in real dollars, in place of the declared 5%. The average overdraft
# fee is about $27 (Bankrate via Checkbook); the CFPB found a median $34 on a median $24 debit purchase (2014) and card
# late fees averaged $32 (2022). Buffer choices price it at the person's average payment. Its scope: bills and wages
# only, at most one fee a payer a day. A failed card-eligible purchase is declined without one, as a debit card purchase
# is without opt-in (Regulation E); the largest overdraft banks cap fees at one to five a day, most at three (CFPB,
# April 2024). At most two fees a payer a model month (``Economy.fees_a_month``), declared a stand-in for coverage
# limits, returned items and account closure, not a bank term (the three published monthly caps are 5, 10 and 20, CFPB,
# April 2024); failures past it carry no fee.
FAIL_FEE = 27.0 / MONTH_USD
# Card rewards: card issuers pay a cardholder 0.75% of what it pays by card, at the month's close.
# Consumers earned $47.5 billion of rewards on $3.6 trillion of credit card purchases in 2024 (1.32%; CFPB, card market
# report, Dec 2025), and credit cards were 57% of card value (Fed Payments Study, 2024): 0.75% of the all-card 1.7% fee.
CARD_REWARDS = 0.0075
# Real costs of intermediation, used only for the headline's real part; the same rate for the same
# service whoever provides it (sources in docs/PARAMETERS.csv). Lending, per unit of principal-time: card credit
# 3.4% a year (servicing, marketing and collection; Agarwal, Chomsisengphet, Mahoney and Stroebel, QJE 2015) and term
# credit 2.5% (FDIC banking profile, Q4 2025). A failed payment, or a pool bridge to a payer without a card in its
# place: $2 an item (CFPB overdraft rule, Dec 2024). Card rails: issuer processing and fraud prevention $0.069 a payment
# (Fed Regulation II data, 2023), fraud 0.11% of value (Nilson Report, US 2023) and the network 0.09% (Visa, fiscal
# 2025). The P rail (P payments run on stablecoin rails): one transfer's gas a payment
# (``GAS_PER_P_PAYMENT``), no card-style processing, fraud or network charge. Holding money or savings (E, P, USDC,
# deposits, money market funds, pool shares): 0.24% a year (ICI, money market funds, 2025).
CARD_LENDING_COST = 0.034 / 12
TERM_LENDING_COST = 0.025 / 12
FAIL_COST = 2.0 / MONTH_USD
CARD_PROCESSING = 0.069 / MONTH_USD
CARD_FRAUD, CARD_NETWORK = 0.0011, 0.0009
HOLDING_COST = 0.0024 / 12
# M0, the strongest real DeFi, each number sourced or derived:
# * USDC converts to and from dollars at no fee (Coinbase Exchange fee table effective 1 June 2026, read Nov 2026: no
#   fee on net USD to USDC conversions up to $2 million a rolling 30 days, 0.03% to $30 million, 0.05% above), far
#   above any household's conversions, so zero for every household.
USDC_CONVERSION = 0.0
# * USDC earns the bill less the Sky Savings Rate's spread under it at the October 2026 anchor. The sUSDS contract's
#   ssr() on Ethereum (0xa3931d71877C0E7a3148CB7Eb4463524FEc27fbD), read on 5 November 2026 through public archive
#   nodes (drpc and Blast, which agree), was 3.60% a year from 1 Oct to block 26,141,856 (7 Oct 2026, 16:58:47 UTC) and
#   3.80% from then to the end of October (and on 5 November), each an APY: the ray rate a second compounded over a
#   year. The anchor is October's mean bill (FRED TB3MS, October 2026: 4.05%, ``BILL_ANCHOR``), quoted on a discount
#   basis. The model reads every rate as a nominal annual rate credited monthly, so both go to that basis first: the
#   bill's 91-day discount yield becomes its effective annual yield, 365 days over 91 a period, credited monthly,
#   4.135% (``BILL_MONTHLY``); each SSR APY becomes the nominal rate credited monthly that compounds to it, 3.542% and
#   3.735%, time-weighted over October, 3.694%; so the spread is 0.441 point (0.293 point if the APYs were read against
#   the discount-basis bill; converting the SSR alone gives 0.357, the lower bound).
def monthly_credited(apy):
    """The nominal annual rate, credited monthly, that compounds to the annual yield ``apy``."""
    return 12 * ((1 + apy) ** (1 / 12) - 1)


BILL_MONTHLY = 12 * ((1 - BILL_ANCHOR * 91 / 360) ** (-365 / 91 / 12) - 1)
SSR_LOW, SSR_HIGH = 0.036, 0.038
SSR_CHANGE_DAYS = 6 + (16 + 58 / 60 + 47 / 3600) / 24       # days of October 2026 at 3.60%, from 1 Oct 00:00 UTC
SSR_OCTOBER = (monthly_credited(SSR_LOW) * SSR_CHANGE_DAYS + monthly_credited(SSR_HIGH) * (31 - SSR_CHANGE_DAYS)) / 31
RESERVE_SPREAD = (BILL_MONTHLY - SSR_OCTOBER) / 12           # a month, 0.441 point a year
# * Gas on Base, where Comet USDC runs: $0.00169 a transaction (growthepie, Base transaction costs, October 2026
#   mean), two legs a USDC payment (the payer redeems from the savings vault and the payee deposits), in place of gas
#   in proportion to value at the mainnet pin's base fee.
GAS_PER_TRANSFER = 0.00169 / MONTH_USD
GAS_PER_PAYMENT = 2 * GAS_PER_TRANSFER
# P payments run on the same rails: a P payment costs its payer what a USDC transfer costs, one transfer, since P pays
# its yield in the wallet and needs no savings vault's legs; paid to validators outside the economy. There is no
# provider fee on P.
GAS_PER_P_PAYMENT = GAS_PER_TRANSFER
# * M0's rates move with the outside rate as observed, not flat in r_out. Pass-through is one for one: each cell holds
#   r_out for five years, so the medium run applies. On-chain getters (Blast and Nodies archive nodes) against FRED
#   TB3MS, monthly, with Newey-West errors: the DAI and Sky savings slope, 2019 to 2026, is 1.02 [0.64, 1.39]; Comet
#   v3's lag-0 slopes are 1.30 [-0.03, 2.63] for supply and 1.58 [-0.11, 3.27] for borrow, neither different from 1;
#   Barbon, Barthelemy and Nguyen (2026, ECB WP 3280) find convergence over the medium run. Levels are the observed
#   October 2026 rates on the common basis, a nominal rate a year credited monthly: USDC's savings rate stays the bill
#   less the Sky spread, max(r_out - 0.441 point, 0) (``RESERVE_SPREAD``); Comet USDC on Ethereum,
#   0xc3d688B66703497DAA19211EEdff47f25384cdc3, borrows at the October 2026 median of its on-chain getBorrowRate reads,
#   5.31% (the median, not the mean of 5.81%: the lower rate is the reading against CPM), and supplies at the median of
#   its getSupplyRate reads, 4.40% (the Aavescan 30-day mean of 3.52% is unmatched by the Ethereum market's own reads,
#   4.67% on average hourly from 6 Oct to 5 Nov). Each is a per-second rate times Comet's 365-day year, so it is first
#   credited monthly (``per_second_monthly``), then set against the October bill on the same basis (``BILL_MONTHLY``):
#   Comet's rates are r_out plus those spreads, every rate floored at zero (``m0_rates``).
COMET_SECONDS_PER_YEAR = 365 * 24 * 3600


def per_second_monthly(apr):
    """The nominal rate a year, credited monthly, of a Comet rate quoted as its per-second rate times Comet's 365-day
    year (``apr``), compounded each second over a twelfth of that year (the common basis), written with log1p and
    expm1, since 1 plus a per-second rate loses digits."""
    return 12 * np.expm1(COMET_SECONDS_PER_YEAR / 12 * np.log1p(apr / COMET_SECONDS_PER_YEAR))


COMET_BORROW_OCTOBER, COMET_SUPPLY_OCTOBER = per_second_monthly(0.0531), per_second_monthly(0.0440)
COMET_BORROW_SPREAD = (COMET_BORROW_OCTOBER - BILL_MONTHLY) / 12    # a month, over r_out
COMET_SUPPLY_SPREAD = (COMET_SUPPLY_OCTOBER - BILL_MONTHLY) / 12
# * The sensitivity ``Economy.m0_rates`` "fitted": the lag-3 OLS lines of the same estimate, each
#   (intercept, slope) a year in r_out, floored at zero: savings -2.79% + 1.76 r_out, capped at r_out since a
#   reserve-funded rate has no payer above the bill; Comet borrow -1.32% + 1.60 r_out; Comet supply -2.12% + 1.50 r_out.
M0_FITTED = dict(savings=(-0.0279, 1.76), borrow=(-0.0132, 1.60), supply=(-0.0212, 1.50))


# * Crypto collateral (``Economy.crypto_share``): a share of people, drawn once on a stream of its own, hold collateral
#   and can borrow from Comet against full cover; nobody else can. The runners' default is nobody: collateral lending by
#   Compound III is not run or reported, since real DeFi lends only against collateral worth more than the loan, which
#   is not everyday credit; the option remains only so the existing unit tests of that code path can run (they pass a
#   share, such as 10%, explicitly).
CRYPTO_SHARE = 0.0
# Failure counts kept by person and month, reported only: no rule reads them. fail_units, each day's unpaid shares of
# failed bills and wages capped at one a payer (the fee's count before the monthly cap, and the real part's under the
# legacy rules; the fee charged under the monthly cap is the run's ``fees``); fail_shares, the same without a cap, each
# bill or wage once (the real failure line's unit); fail_items, whole bills and wages returned (``in_order``);
# fail_days, days with a failed bill or wage; declined_shares and declined_items, card-eligible purchases of payers
# without a card, or past a holder's room on its line, declined without a fee (the purchase is lost; not a failed
# bill); bridged_shares and bridged_items, bills and wages that the pool's draw paid in place of failing, for a payer
# without a card and, for a holder, the part of the draw its cash line could not have taken, the least of the draw and
# the shortfall beyond the cash line's room; bridged_card, the share of the card-eligible purchases of payers without a
# card, or past a holder's room, that it paid (new lending, not a replaced failure). No cap applies in counting
# fail_shares or fail_items, but the path they are counted on still depends on the one-fee-a-day cap, through the fee
# debt ranked ahead of the pool, the pool's same-day limit and the buffer replays.
FAILURE_COUNTS = ("fail_units", "fail_shares", "fail_items", "fail_days", "declined_shares", "declined_items",
                  "bridged_shares", "bridged_items", "bridged_card")
# Credit by person and month: business credit is read inside the one population; records only, no rule reads them
# (``credit_path``, returned as ``credit``; ``simulate`` says what each counts). The last two split the card's interest
# and fees: interest on cash advances alone and cash-advance fees alone, each also inside interest_card and fees_card.
CREDIT_RECORDS = ("bridge_pool", "bridge_card", "bridge_comet", "bridge_refused", "term_pool", "term_outside",
                  "term_cancelled", "interest_pool", "interest_outside", "interest_card", "wages_late", "advance_card",
                  "fees_card", "charged_off_card", "interest_advance", "fees_advance")
# Exit notice: an exit request executes this many months after it starts, at that month's NAV, and lapses if withdrawn
# first. The issuer is a pure custodian: it holds no pool shares, so no stake.
EXIT_NOTICE_MONTHS = 2
# The owner exit rule: an owner reads its own realised return since buying over at most this many months; owners leave
# by the users' rule, the gap spread over the same 12 months.
OWN_RETURN_MONTHS = 12
# The issuer's stay test: its complete wallet averaged over this many months, read every month from
# the 12th after launch. A negative average records "issuer would leave"; the issuer keeps operating.
STAY_MONTHS = 12
# Two rates a month closer than this are equal (numerical zero): at N* the quote equals owners' alternative exactly in
# exact arithmetic, and rounding must not read that tie as a quote below it.
RATE_TIE = 1e-15
# Backing: reserves below P owed by more than this share fail the unsafe falsifier (numerical zero).
BACKING_TOLERANCE = 1e-9
# The issuer's books, each a monthly series "issuer_<name>". The issuer is a pure custodian: it holds P's reserves and
# keeps c_I at zero profit, with no pool shares and no support fund, so its profit and loss is one line per job of a
# custodian, adding up to the complete wallet; then its cash, what its owners put in when the month's cash is negative
# and what they take out; then its expenses' one part, its 0.24% of P. The float line is minus what the issuer pays out
# of the reserve return, to wallet holders (less demurrage) and to the pool (demurrage and its own cash's return). The
# issuer is not a payment operator (P payments run on stablecoin rails), so it has no fee line and bears no rail.
ISSUER_BOOKS = ("custodian", "indexer", "float", "expenses", "wallet", "owners_in", "payout", "expense_holding")
# The pool's own margin, part by part, each a monthly series "margin_<name>" beside "own_margin": coupons accrued (the
# fixed cost's part among them), recoveries, less the operating cost, the fixed cost, gross write-offs and owners'
# alternative on lent principal-time (``_World._own_margin``). There is no provider fee, so neither fees nor owners' own
# fees are parts.
MARGIN_PARTS = ("coupons", "recovered", "operating", "fixed", "written_off", "alternative")
# The issuer pays households nothing of its own: M2's indexation is the holder's own yield, paid out of the reserve
# return on its own P while the issuer keeps only c_I, so M2's gains are read in full, with no issuer transfer line for
# indexation; P's yield is likewise the reserve return on the holder's own P less custody and demurrage.
CONSUMER_UNITS = 134.556e6
# Earned-wage access, in every arm: held by at most about 7.4% of consumer units (about 10 million
# users in 2022 over the consumer units, an upper bound; CFPB, July 2024), usable on up to half of the wages earned and
# still unpaid on a job not in a spell (NCLC, March 2020: many providers limit access to half), at 2.45% of the amount
# ($2.60 on a $106 advance; CFPB, July 2024, eight employer-partnered providers). Its real cost is $2 a use, declared:
# no source splits earned-wage cost from margin.
EWA_SHARE = 10e6 / CONSUMER_UNITS
EWA_FEE = 0.0245
EWA_LIMIT = 0.5
EWA_COST = 2.0 / MONTH_USD
# Card limits, the outside-card contract, the same in every arm. Each holder's line is the
# average credit line per cardholder, all cards, of its CFPB score tier in 2023 (CFPB, The Consumer Credit Card Market,
# December 2025, Fig 89; overall $26,218), read from the score the engine draws: deep subprime (579 or below), subprime
# (580 to 619), near-prime (620 to 659), prime (660 to 719), prime plus (720 to 799) and superprime (800 and above).
# Lines are held fixed in real terms.
CARD_LINE_SCORES = np.array([580, 620, 660, 720, 800])
CARD_LINE = np.array([5696.0, 8121.0, 12524.0, 22068.0, 29335.0, 41654.0]) / MONTH_USD
# The starting balance: an outside balance each holder brings into the run, which uses up part of its line and stays
# fixed; the model neither charges interest on it nor collects it, so it is no part of net wealth (the model carries no
# legacy debt). A holder starts at 90 to 100% of its line, uniform, with its tier's chance: the share of cardholders at
# 90% or more across their general purpose cards on 31 Jul 2024, deep subprime 68.41%, subprime 46.88%, near-prime
# 32.32% (CFPB 2025, Fig 92), and prime and above 5.2%, set so that 18% of the model's holders start there, the share
# of card borrowers at 90% or more of their limits in Q1 2024 (NY Fed, Liberty Street Economics, 14 May 2024).
CARD_MAXED = np.array([0.6841, 0.4688, 0.3232, 0.052, 0.052, 0.052])
# Every other holder uses a share of its line drawn in the same post's bands below 90%: under 20%, 20 to 60% and 60 to
# 90% of the limit, held by 52, 19 and 11% of borrowers (so 63, 23 and 13% of those below 90%), uniform within a band,
# times its tier's share of active accounts revolving in 2024, general purpose (CFPB 2025, Fig 50: 88.06, 83.39,
# 81.68, 72.17, 41.86 and 19.64%), since the model makes its own purchase float, which must not be counted twice.
CARD_BANDS = np.array([0.0, 0.2, 0.6, 0.9])
CARD_BAND_SHARES = np.array([52.0, 19.0, 11.0]) / 82.0
CARD_REVOLVING = np.array([0.8806, 0.8339, 0.8168, 0.7217, 0.4186, 0.1964])
# A cash advance for a non-card bill: the most common cash-advance APR in the agreements the CFPB reviewed, 30%, and
# its fee, the greater of $10 or 5% of the advance (CFPB, Data Spotlight on cash advance fees, 16 Dec 2024), interest
# running from the day it is taken (CFPB, card market report, Oct 2023, Sec 6.4.2). The APR moves with r_out as the
# purchase APRs do. The cash line is 20% of the line (CFPB 2023, Sec 6.4: "20 percent of the line is common"), within
# the room the line has left.
CASH_ADVANCE_APR = 0.30
CASH_ADVANCE_FEE_FLOOR = 10.0 / MONTH_USD
CASH_ADVANCE_FEE_RATE = 0.05
CASH_LINE_SHARE = 0.2
# The minimum payment, due with the statement on day 20: the greater of $40, or the whole balance if smaller, and 1% of
# the balance plus the cycle's interest and fees and any amount past due (CFPB 2025, Sec 4.1.1), never above the
# balance. Missing it costs a late fee of $30, or $41 for a repeat within the next six billing cycles, never above the
# minimum due (12 CFR 1026.52(b); 86 FR 60357). That these amounts apply since the 2024 rule was vacated (15 Apr 2025)
# is a reading of the rule. No penalty APR, no re-aging.
CARD_MINIMUM_FLOOR = 40.0 / MONTH_USD
CARD_MINIMUM_SHARE = 0.01
LATE_FEE, LATE_FEE_REPEAT, LATE_FEE_CYCLES = 30.0 / MONTH_USD, 41.0 / MONTH_USD, 6
# Charge-off: a card 180 days past due is charged off and its line closed for the rest of the run (FFIEC Uniform Retail
# Credit Classification policy, 65 FR 36903, 12 Jun 2000); the debt stays owed, at no further interest, as the pool's
# own written-off loans do.
CHARGE_OFF_DAYS = 180
# The distress line cut (``Economy.card_line_cut``, off by default, when lines are held through the distress year, and
# on in the second run): at the start of the distress year each open line is cut by 60% of its tier's fall from 2008 to
# 2012, the part that came before the CARD Act passed, times the distress level over 2%. Total lines fell 32.4%, deep
# subprime lines 54.3% and superprime 26.7% (CFPB, CARD Act Report, Oct 2013, Sec 3.3.1), so at 2% deep subprime lines
# fall 32.6%, superprime 16.0% and the four tiers between 19.4%. The lines came back (``Economy.card_cut_months``, 0
# never, the default): total card credit lines fell from $3.6 trillion in Q2 2008 to $2.4 trillion in Q4 2012, 32.4%
# (CFPB, CARD Act Report, Oct 2013, p. 52), were "nearly equal to" their pre-recession high at $4.3 trillion in 2018
# (CFPB, The Consumer Credit Card Market, Aug 2019, p. 10) and reached a post-recession high of over $4.5 trillion in
# 2019 (CFPB, The Consumer Credit Card Market, Sep 2021, p. 9): about ten years, so the run restores the cut lines 120
# months after the cut.
CARD_CUT = 0.6 * np.array([0.543, 0.324, 0.324, 0.324, 0.324, 0.267])
CARD_CUT_LEVEL = 0.02
SECONDS_PER_MONTH = DAYS * 24 * 3600
BIG = 10 ** 9            # "no date" sentinel for due dates and arrears start
EPS = 1e-12              # numerical zero for money amounts
# One row per loan. ``pool`` marks the CPM pool as lender (else an outside lender); ``rate`` is the sealed coupon per
# month; ``alt`` is the borrower's outside rate for the same credit (used to measure the saving); ``due`` is the
# due day of a bridge; term loans repay ``instal`` principal per instalment over ``months`` from origin month ``m0``,
# ``ndue`` instalments have fallen due, ``interest_due`` is the interest already due, ``since`` the day the oldest
# unpaid instalment fell due; ``carried`` is False once a pool loan is written off. A pool bridge's ``m0`` is the
# month it was made, read only by the record by loan year; a cash advance's is the month it was taken, read only by the
# replays' card room (the month's advances still owed); outside bridges, revolving balances and overdrafts keep 0, and
# every other rule that reads ``m0`` reads term loans only. ``card_part`` is the share of a pool bridge the real part
# counts as card credit, read only by the real part's records: for a payer without a card the part that paid
# card-eligible purchases (new lending); for a card holder the part its cash line would otherwise have taken, with any
# purchases past its room, and a statement's whole draw, the rest having paid in place of failing; 0 on every other
# loan. ``cover`` is the cut in a pool bridge's coupon a month that demurrage pays (coverage times the coupon's capital
# part, sealed with the bridge), read only by theta's record; 0 on every other loan. ``business`` marks a term loan for
# a business product (``BUSINESS_PRODUCT``), set where term loans are made, a record read only by the loan-loss bound's
# class; False on every other loan.
BOOK_FIELDS = ("borrower", "pool", "kind", "principal", "interest", "interest_due", "rate", "alt", "due", "original",
               "instal", "ndue", "months", "m0", "since", "carried", "card_part", "cover", "business")
# Loan losses at sourced rates, the bound reading (``Economy.loan_losses`` "sourced"): every lender,
# the pool included, loses each month the charge-off rate of the bank loans its loans replace. Federal Reserve,
# charge-off rates on loans at all commercial banks, % of balances a year, via FRED; "normal" is the mean of the 20
# quarters 2015Q1 to 2019Q4, "peak" the highest quarter of 2008 to 2011. Classes, in this order: card (pool bridges,
# card bridges, revolving card debt and overdrafts, not Comet's loans, which are secured by collateral; CORCCACBS,
# normal 3.402, peak 10.54 in 2009 Q4), consumer (instalment loans for vehicles and personal needs, pool or outside;
# COROCLACBS, normal 0.829, peak 3.36 in 2009 Q2) and business (instalment loans for business products, pool or
# outside; CORBLACBS, normal 0.3315, peak 2.57 in 2009 Q3). Fee debt, overdue wages and earned-wage advances are not
# loans here and lose nothing. The published rate is net charge-offs over the average balance of the period, so each
# month a lender group loses the month's rate over 12 times the class's average principal over the month's days
# (``_World._loss_base``), not its month-end book. The pool prices what it loses: each coupon
# carries its class's rate of the month (``_World._priced_loss``), so owners bear no loss the published rate gives.
LOSS_CLASSES = ("card", "consumer", "business")
CHARGE_OFF_NORMAL = np.array([3.402, 0.829, 0.3315]) / 100
CHARGE_OFF_PEAK = np.array([10.54, 3.36, 2.57]) / 100
# The month's rate moves from normal to peak with the share of jobs without a wage three months earlier (the engine
# writes a pool loan off 90 days after a missed payment): x = max((J - normal) / (peak - normal), 0), with the job-loser
# rate U-2 (FRED U2RATE) in payroll-job units, the units of the model's own share of jobs: U-2 times the labor force
# over payroll jobs (FRED CLF16OV / PAYEMS). Normal 2.32%, from U-2's mean of 2.12% over 2015 to 2019; peak 7.68%, from
# 6.5% in September 2009 (6.5 x 153,827 / 130,246 thousand).
JOB_LOSER_NORMAL, JOB_LOSER_PEAK = 0.0232, 0.0768
LOSS_LAG = 3
# The loan-loss bound's monthly records, per person, reported and read by no rule: the pool's
# bridging and term principal discharged, and outside lenders' by class. Kept only under "sourced".
# Records only, stored in every arm and read by no rule (``_close``): completed service and shock
# purchases (at the share completed) and durables settled, a count a person a month; the largest single pool loan
# outstanding and the largest pool debt of one borrower, principal carried, as shares of pool capital at the close
# (NaN with no pool capital). US law caps one national bank's lending to one borrower at 15% of capital (12 U.S.C. 84).
MEASURE_SERIES = ("purchases_n", "durables_n", "largest_loan_share", "largest_borrower_share")
# MicroVelocity's records (Campajola, D'Errico and Tessone), each person's sums by year after launch
# (``velocity_path``): payments to others out of its E and P, and balance-time of E and P, of outside savings and of
# pool shares at their value, in unit-months (a balance held all month adds the balance once).
VELOCITY_RECORDS = ("outflow", "money_bt", "savings_bt", "shares_bt")
LOAN_LOSS_SERIES = ("discharged_pool_bridge", "discharged_pool_term", "discharged_outside_card",
                    "discharged_outside_consumer", "discharged_outside_business")
# The bound's amount carried forward undischarged at each close, every class and lender group together, per person.
# Kept only under "sourced", as the discharge records are.
LOSS_CARRIED = "loss_carried"


# Settlement days needing more sweeps than this are counted (``slow_days``).
SLOW_SWEEPS = 500


# The robustness switches (docs/ROBUSTNESS_PLAN.md, section 5), each off by default (``Economy``). Their random streams
# are keyed apart from every stream of the base, so no base draw moves: the buffer review (43, by month), the joining
# thresholds (3107), the ring's positions (3108) and the sellers each world draws for services, shocks and instalment
# purchases (47, 53 and 59, by month).
BUFFER_REVIEW_STREAM, THRESHOLD_STREAM, RING_STREAM = 43, 3107, 3108
SELLER_STREAMS = dict(service=47, shock=53, term=59)
# Purchases at random and card statements on each holder's own date, each off by default
# (``Economy.purchases``, ``Economy.statement_dates``), on streams keyed apart from every other: each person's number of
# purchases in a month (61, by month), the day, seller and card flag of each of them (67, by month), and each person's
# closing day, drawn once (3112).
PURCHASE_COUNT_STREAM, PURCHASE_STREAM, STATEMENT_DATE_STREAM = 61, 67, 3112
# By default a statement closes on day 29 and is due on day 20 of the next month, 21 days later, the least the CARD Act
# allows between a statement's delivery and its due date (Regulation Z, 12 CFR 1026.5(b)(2)(ii)); under each holder's
# own date it is due the same 21 days after its own closing day.
STATEMENT_CLOSE_DAY, STATEMENT_DUE_LAG = 29, 21
# The side studies of the second run, each off by default (``Economy``), on streams
# keyed apart from every other: who reads the pool's record at entry (3109, one draw a person for the run), and the
# random distress years (3110, one draw a month after launch at a dial of 4; 3111, one draw a year drawn there, which
# thins it to the run's dial).
SCEPTIC_STREAM, DISTRESS_START_STREAM, DISTRESS_KEEP_STREAM = 3109, 3110, 3111
# The stress year as a slowdown (``Economy.distress_purchases``), off by default, on a stream
# keyed apart from every other: one uniform for each purchase of a distress month (3113, by month).
DROP_STREAM = 3113
# The wage links of ``Economy.wage_links`` "one_each", off by default, on a stream
# keyed apart from every other: the permutations drawn once at the opening until one has no fixed point (3114).
WAGE_LINK_STREAM = 3114
# The highest dial of the random distress years, the expected number of years in a run, at which they are drawn.
DISTRESS_DIAL_MAX = 4.0
# Measured joining thresholds: log-normal with log-mean -2 and log-spread 1 (mean 0.19), fitted to the adoption of a
# paid Skype service (Karsai, Iniguez, Kikas, Kaski and Kertesz 2016). Their share of people who never adopt belongs to
# that product and is not used.
THRESHOLD_LOG_MEAN, THRESHOLD_LOG_SPREAD = -2.0, 1.0
# Sellers on a ring: a local purchase goes to one of the buyer's 32 nearest positions, 16 each side (the ring of
# Watts and Strogatz 1998).
RING_SIDE = 16
# Sellers with hubs: a seller is drawn with chance proportional to k^(-HUB_WEIGHT_EXPONENT), k its rank by initial
# spending (the largest spender 1). The weight exponent 1 / (gamma - 1) gives a number of partners with tail exponent
# gamma (Goh, Kahng and Kim 2001); gamma 2.9 is the degree exponent measured on the Sarafu payment network (Mattsson,
# Criscione and Takes 2023), so the weight exponent is 0.526.
SARAFU_DEGREE_EXPONENT = 2.9
HUB_WEIGHT_EXPONENT = 1 / (SARAFU_DEGREE_EXPONENT - 1)

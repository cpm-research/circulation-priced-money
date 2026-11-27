"""Registered-economy agent-based model of Circulation-Priced Money (CPM) and its comparators.

This module is the population ABM of the CPM research programme. It puts the
mechanism of the paper (``paper/cpm.tex``) and the conventions of the core
model (``src/cpm_abm/core_model.py``) into one
economy of heterogeneous households with daily, dated cash flows.
The rules in force are listed in ``docs/DECISIONS.md`` and described in full in
the paper's model section (``paper/sections/model.tex``), with the map from that
description to the code in ``docs/MODEL.md``; comments name each rule by what it
does and cite the paper's equations by what they compute.

Units and time
--------------
* Money is measured in months of mean household spending (1.0 = $6,440, BLS
  CEX 2023). Rates are per month unless a name says otherwise.
* A month has 30 days. A run is ``burn_in`` months of S0 (no CPM) followed by
  ``months`` months after launch; all arms share the burn-in exactly.
* The economy runs in real units: with 2% CPI inflation every nominal
  stock loses dJ/J of its real value each month, while M2's indexed P does not.

Arms (the same economy and behaviour rules, compared person by person)
----------------------------------------------------------------------
* ``S0``  status quo: E (bank money), cards, outside savings and lenders.
* ``M1``  CPM: nominal P, a funded lending pool, competitive P (wallet P pays its holders the reserve return less the
          issuer's custody cost less demurrage c, and c, the capital cost of the liquidity the pool kept available last
          cycle over last cycle's wallet P, goes to the pool) and an issuer that is a pure custodian.
* ``M2``  M1 with P indexed to the CPI: the contract runs in P terms.
* ``U``   M1 with no demurrage: the same P with c = 0, so wallet P pays the reserve return less custody and a bridge
          pays the full coupon; everything else as M1, so U against M1 on the same draws is what demurrage adds.
* ``M0``  the strongest real DeFi: USDC earns a reserve-funded savings rate, the bill less the Sky Savings Rate's spread
          under it, paid from T-bill income; it and Comet's rates move with r_out one for one from their observed
          October 2026 levels (``m0_rates``); payments pay the gas of two legs on Base; USDC converts at no fee; Comet
          is the only credit, against crypto collateral only: a share of people drawn on a stream of its own hold it,
          with full cover (``Economy.crypto_share``; 0, nobody, is the engine's and the runners' default: collateral
          lending by Compound III is not run or reported, since real DeFi lends only against collateral worth more than
          the loan, which is not everyday credit; the option remains only for the unit tests of that code path).

The economy (identical in every arm)
------------------------------------
* Population: Pareto liquid wealth, spending rising with wealth^0.5.
* Settlement: every bill settles on the payee's billing date (daily, weekly, fortnightly, monthly or 60-day) and every
  wage on its job's pay date, at BLS pay frequencies (weekly, every two weeks, twice a month or monthly), so receipts
  arrive in lumps.
* Income: each person pays 58.3% of spending as one persistent wage contract to a uniformly drawn recipient and 41.7% as
  32 service bundles to uniform sellers; every non-housing bundle is card-eligible, 28% of spending.
* Failure cost: a failed bill or wage costs a flat $27, at most one fee a payer a day and two a model month
  (``Economy.fees_a_month``); the fee debt bears no interest and is repaid first; a re-queued wage carries no second
  fee, and the buffer choice counts it once.
* Alternatives to failing: a short payer uses its own money, today's receipts, same-day savings, the card for a holder's
  card-eligible purchases, the pool (where no dearer than the line it holds), Comet (M0), the card for a holder's other
  payments, then earned-wage access, and only then fails. Access is held by a drawn share of wage earners: up to half of
  the wages earned and still unpaid on a job not in a spell, at 2.45%, repaid first from that wage.
* Card limits, the outside-card contract, the same in every arm: each holder has a line by its CFPB score tier and a
  fixed starting balance using part of it. Card purchases go on the card up to the room left, smallest first, the rest
  the cash route; a holder's other payments the card covers only as a cash advance, up to 20% of the line within the
  room, at 30% a year (moving with r_out) and the greater of $10 or 5%; holders reach earned-wage access too. The
  statement carries a minimum payment ($40 or 1% plus interest, fees and past due) and a late fee ($30, $41 for a
  repeat); a card 180 days past due is charged off, its line closed and its debt still owed. The pool's tests for
  holders are partial (``limit_with_card``, ``limit_with_revolve``). Each person's class stays the population's card
  holding.
* Payers in chronic deficit (spending above income received over the
  burn-in, with a liquid cushion below a month of their own spending) are
  flagged at launch, the same in every arm, and reported apart only.
* P payments run on stablecoin rails: P is a token on the same public chain as USDC, so a P payment costs its payer one
  transfer's gas on Base, paid to validators outside the economy, where a USDC payment takes two; there is no provider
  fee and no card-style processing, fraud or network charge on P, and the issuer is not a payment operator (it bears
  0.24% a year of P outstanding). P payments settle whenever P is issued, with or without a pool. The pool's fixed cost
  is priced into the loan coupon at break-even (``_cycle_terms``).
* The yardsticks, records only, no rule reads them: the pool's own margin and its parts, the joint issuer-and-pool test
  and households' capital in exit requests still unpaid (the base of the 90% household test). M2's indexation is the
  holder's own yield so no line records it as paid by the issuer. Owners' compensation K in the self-financing ratio is
  their alternative, and the ratio credits recovered principal.
* The issuer is a pure custodian: it holds P's reserves and keeps c_I at zero profit; it holds no pool shares and no
  support fund and buys no exits. Households alone own the pool, by free entry at the published quote, from the first
  dealing with a lending need; owners' exits are paid after the two-month notice from pool cash and, for the rest, by
  the same dealing's new subscriptions. New subscriptions pay leaving owners first: during the month pool cash is set
  aside only for the part of the exits falling due at the next dealing that the last dealing's unused offers would not
  have covered (``_cash_for_loans``). Whether the issuer would leave is still read every month (``_stay_test``), a
  record.
* Competitive P, in M1, M2 and U, nothing set by hand: the issuer keeps its zero-profit custody, c_I = 0.24% a year of
  all P (``issuer_share``); wallet P pays its holders y_P = rho_p - c_I - c on their balance-time each month, credited
  as P. Demurrage pays for liquidity kept available: c (``_cycle_terms``) is the capital cost of all the liquidity the
  pool kept available last cycle, its bridging principal-time at owners' alternative plus its standby cash-time (pool
  cash held ready up to the cycle's peak bridging need beyond what was lent) at the alternative less what idle cash
  earns, over last cycle's wallet P balance-time, at most rho_p - c_I, published at the start of the month; its proceeds
  go to the pool (``_reserve_return``), so a bridge drawn this month is sealed at the coupon less the capital part they
  cover; the pool's own P cash earns rho_p - c_I. U has c = 0. Pool entry is the free-entry equilibrium (derived): the
  quote is ``paper_return``, capital up to the capital target earning owners' alternative and the pool's own cash beyond
  it rho_p - c_I, and entry stops at N* = ``paper_capital``; F, the fee margin, is 0 with no fees, so N* is the capital
  target (``_limit``): the lending need with its bridging part at the cycle's peak in M1 and M2, so owners earn their
  alternative on every unit kept ready, and the lending need P* in U, where nothing pays for standby. The term part
  funds next month's lending: carried term principal plus the term lending refused plus the month's growth in the pool's
  term book, floored at zero, and U's lending need takes the same growth; capital already above N* stays. Free entry
  applies in every month: a pool whose last share has been paid out is open again, and households enter at the published
  quote in any later dealing with a lending need, as at launch.
* Most rules have their switch in ``Economy``; ``LEGACY`` (``legacy``) turns every one off and ``LEGACY_STEP45`` those
  of the yardsticks, for sensitivities and worked examples. Demurrage and competitive P have no switch.
* Outside finance: cards by income bracket and a credit score; instalment credit for vehicles, personal needs and firms;
  savings at each household's own deposit/money-market mix. Outside deposit and credit rates follow r_out from their
  October 2026 levels, the same in every arm, anchored at the bill on r_out's monthly-credited basis: deposits by
  0.08 of a change, floored at 0.06%, card and business rates one for one; a loan keeps the rate it was made at.
* Optional SHED unexpected-expense shocks (off under normal conditions).
* Job loss: every month, in every arm and the burn-in, jobs lose their wage at the normal rate of 0.55% a month, more
  often for lower incomes, from its steady stock at month 0, for completed spells consistent with BLS unemployment
  spells in progress; after normal job loss the payer keeps the unpaid wage. Distress, the third control (level 0 in
  normal times), adds an extra monthly rate in a distress year. The harsh stress, the only behaviour: an extra layoff's
  wage leaves the household economy for its whole spell. Its payer still owes it on the job's pay dates, to the outside,
  and its worker receives nothing, so level 0 is unchanged. No unemployment insurance is modelled (declared).

What happens each month (``_World.month``)
------------------------------------------
1. Jobs are laid off, at the normal rate and in the distress year at the
   distress control's extra rate too (``_layoffs``). Obligations are
   created: service bundles, daily wage accruals (none for a laid-off job,
   but the wage an extra layoff's payer owes to the outside), shocks and
   term-credit requests (``_obligations``).
2. The pool's terms are set from completed observations: the bridging and
   term coupons with loss learning by product and the fixed cost's part, the
   capital limit N* and the
   quote at it, demurrage c on wallet P, its coverage of the capital cost of
   the liquidity kept available and the yield P pays (``_cycle_terms``).
3. Dealing: owners' exit requests by the users' leaving rule (capital above
   N* stays), overdue wages and debts first, the cash
   buffer, then spare money into pool shares up to N* or into outside
   savings (``_dealing``).
4. Thirty days of settlement (``day``): instalments, term purchases, routed
   payments with pool, card or Comet bridging and failures, the card
   statement, repayment, accrual and write-offs.
5. Close (``_close``): under the loan-loss bound
   (``Economy.loan_losses`` "sourced") loans discharged at sourced charge-off
   rates first; savings income, the reserve return on P (the yield to
   wallet holders, demurrage and the pool's own cash's return to the pool),
   NAV, the experience of using P and adoption (joining, leaving), card
   rewards, CPI, next month's spending and all records.

The boundary
------------
Every intermediary sits outside the household economy in every arm: outside
lenders, the banks that charge failure fees, card networks and issuers, the
conversion provider, the pool's operating provider, the issuer, and M0's
validators and stablecoin issuer. What households pay any of them leaves; what
any of them pays households (card rewards, M2's indexation, P's yield and the
pool's part of the reserve return, M0's savings rate) comes in. Nothing is
handed back, except outside lenders' interest under the recirculation stress.
The wage of a distress year's extra layoff leaves too: its
payer owes it to the outside, and nobody in the economy receives it.

Accounting guarantee
--------------------
Money only moves between named accounts. Each person's net financial wealth
is cash (E and P) + outside savings + pool shares at NAV + receivables -
payables - card balances - every loan. Summed over people, its monthly change
equals exactly the flows with the outside (savings income, outside interest,
penalties, card, conversion and pool costs, the card's cash-advance and late
fees, card rewards, gas on P and USDC payments, USDC's savings rate, the
reserve return paid on P, the wages of the distress year's extra layoffs,
booked when each of their wage rows is made, as the payer's payable with no
receivable, and under the loan-loss bound outside lenders' discharged
principal) plus the write-off valuation of pool loans plus the CPI term. A
card's starting balance is no part of net wealth.
``tests/test_economy_abm.py`` checks this identity to 1e-12 in every arm;
reported residuals are about 1e-16.

Behaviour (no forecasting, no optimisation over the world)
----------------------------------------------------------
* Buffer: the cheapest of a few buffer sizes, replaying the
  person's own last month of cash flows.
* Joining: Bass rate p + q x (share of own counterparties using P).
* Leaving: each month a share upsilon (0.153, the monthly chance at review rate 0.166) of participants reviews, and a
  reviewer leaves with the core model's logistic probability of its 12-month average experience falling short of one
  conversion of its 12-month average P balance, spread over the 12 months, at a noise scale of 1e-4 of its own monthly
  spending (``_leaving``).
* Investing (one savings rule): spare money splits by the person's own deposit and money-market mix; only the
  money-market part goes to the pool, while the pool's quote is at least rho_H plus the owners' spread. Owners leave by
  the users' rule: each month 16.6% of owners review, on a stream of their own, and a reviewer files to exit with the
  logistic probability of its 12-month realised return gap in dollars falling short of its leaving cost spread over 12
  months, at the same noise scale (``_exits``).
"""
from dataclasses import dataclass, replace
from functools import reduce

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from cpm_abm.comet import load_pin, rate as comet_curve

# The engine lives in the package cpm_abm.engine, one idea per module (its docstring is the code map). This module
# re-exports its names, so imports from here keep working.
from cpm_abm.engine.constants import (BACKING_TOLERANCE, BIG, BILL_ANCHOR, BILL_MONTHLY, BOOK_FIELDS, BRIDGE,
                                      BUFFER_MULTIPLES, BUSINESS_APR, BUSINESS_PRODUCT, C1_HORIZON_DAYS, C1_PERIOD_DAYS,
                                      CARD_APR, CARD_BAND_SHARES, CARD_BANDS, CARD_CUT, CARD_CUT_LEVEL, CARD_FRAUD,
                                      CARD_LENDING_COST, CARD_LINE, CARD_LINE_SCORES, CARD_MAXED, CARD_MINIMUM_FLOOR,
                                      CARD_MINIMUM_SHARE, CARD_NETWORK, CARD_OWNERSHIP, CARD_PROCESSING, CARD_REVOLVING,
                                      CARD_REWARDS, CARD_TIER_SCORES, CASH_ADVANCE, CASH_ADVANCE_APR,
                                      CASH_ADVANCE_FEE_FLOOR, CASH_ADVANCE_FEE_RATE, CASH_LINE_SHARE, CHARGE_OFF_DAYS,
                                      CHARGE_OFF_NORMAL, CHARGE_OFF_PEAK, CHARGED_OFF, COMET_BORROW_OCTOBER,
                                      COMET_BORROW_SPREAD, COMET_SECONDS_PER_YEAR, COMET_SUPPLY_OCTOBER,
                                      COMET_SUPPLY_SPREAD, completed_spell_law, COMPLETED_SPELL_MEDIAN_DAYS,
                                      COMPLETED_SPELL_SIGMA, CONSUMER_UNITS, CONVERSION_FEE, CREDIT_RECORDS,
                                      CRYPTO_SHARE, CYCLE_DAYS, DAYS, DEPOSIT_FLOOR, DFA_DEPOSITS, DFA_GROUP_UPPER,
                                      DFA_MONEY_MARKET, DTI_CAP, EPS, EWA_COST, EWA_FEE, EWA_LIMIT, EWA_SHARE,
                                      EXIT_NOTICE_MONTHS, FAIL_COST, FAIL_FEE, FAILURE_COUNTS, FDIC_SAVINGS_RATE,
                                      FEE_DEBT, FICO_CUMULATIVE, FICO_EDGES, GAS_PER_P_PAYMENT, GAS_PER_PAYMENT,
                                      GAS_PER_TRANSFER, HOLDING_COST, HOUSEHOLDS_BY_EDUCATION, INCOME_BRACKETS,
                                      ISSUER_BOOKS, JOB_LOSER_NORMAL, JOB_LOSER_PEAK, JOB_LOSS, LABOUR_SHARE, LATE_FEE,
                                      LATE_FEE_CYCLES, LATE_FEE_REPEAT, LATE_OUTSIDE_WAGE, LATE_WAGE, LOAN_LOSS_SERIES,
                                      LOAN_YEARS, LOSS_CARRIED, LOSS_CLASSES, LOSS_LAG, LOSS_LAG_MONTHS, M0_FITTED,
                                      MARGIN_PARTS, MEASURE_SERIES, MONTH_USD, monthly_credited, OUTSIDE_WAGE,
                                      OVERDRAFT, OWN_RETURN_MONTHS, PAY_DAYS, PAY_SHARES, per_second_monthly,
                                      PERSONAL_APR, PERSONAL_SCORES, RATE_TIE, REQUEST_RATE, RESERVE_SPREAD, REVOLVE,
                                      ROUTE_CARD, ROUTE_E, ROUTE_P, SCORE_INCOME_CORRELATION, SECONDS_PER_MONTH,
                                      SERVICE, SHOCK, SHOCK_ANNUAL, SHOCK_SIZE, SLOW_SWEEPS, SPELL_MEAN_DAYS,
                                      SPELL_MEDIAN_DAYS, SPELL_SIGMA, SSR_CHANGE_DAYS, SSR_HIGH, SSR_LOW, SSR_OCTOBER,
                                      STAY_MONTHS, SURVEY_RANKS, SURVEY_SAVINGS, TERM, TERM_LENDING_COST, TERM_MONTHS,
                                      TERM_SIZE, UNEMPLOYMENT_BY_EDUCATION, USDC_CONVERSION, VEHICLE_APR,
                                      VEHICLE_NEW_SHARE, VEHICLE_SIZE, VEHICLE_TIER_SCORES, VELOCITY_RECORDS, WAGE,
                                      WRITE_OFF_DAYS)
from cpm_abm.engine.settings import Economy, LEGACY, legacy, LEGACY_RULES, LEGACY_STEP45
from cpm_abm.engine.population import (billing_cycle_shares, build_population, card_lines, card_tier, cards_and_scores,
                                       draw_spells, income_bracket, income_source, last_billing, layoff_weight,
                                       next_billing, pareto_stratum_means, rank_share, spell_law, spell_stock,
                                       term_outside_apr)
from cpm_abm.engine.rates import (charge_off_rates, issuer_share, logistic, m0_rates, money_market_share,
                                  outside_prices, outside_return, own_returns, own_window, paper_capital, paper_return)
from cpm_abm.engine.lending_rules import (_rises, choose_buffer, limit_with_advance, limit_with_card, limit_with_fee,
                                          limit_with_revolve, replay_cost)
from cpm_abm.engine.ledger import (_concat, _DUE_SOON_FIELDS, _empty, _merge_sorted, _overdue_of, _take, allocate,
                                   COIN_CONVENTIONS, COIN_EDGES, COIN_RECENT, COIN_WINDOW, Coinage, COINAGE_RECORDS,
                                   in_order)
from cpm_abm.engine.measures import _velocity_groups, gini, holding_velocity, microvelocity, turnover
from cpm_abm.engine.world import _World, launch_state, resume, simulate
# The robustness switches (docs/ROBUSTNESS_PLAN.md, section 5): their constants and the fixed network they read.
from cpm_abm.engine.constants import (BUFFER_REVIEW_STREAM, HUB_WEIGHT_EXPONENT, RING_SIDE, RING_STREAM,
                                      SARAFU_DEGREE_EXPONENT, SELLER_STREAMS, THRESHOLD_LOG_MEAN, THRESHOLD_LOG_SPREAD,
                                      THRESHOLD_STREAM)
from cpm_abm.engine.network import (build_network, hub_sellers, hub_weights, Network, rank_of, ring_sellers,
                                    threshold_chance, thresholds)
from cpm_abm.engine.lending_rules import review, reviewed_buffer
# The side studies of the second registered run: their streams and the random distress years.
from cpm_abm.engine.constants import (DISTRESS_DIAL_MAX, DISTRESS_KEEP_STREAM, DISTRESS_START_STREAM,
                                      SCEPTIC_STREAM)
from cpm_abm.engine.population import distress_calendar, distress_years

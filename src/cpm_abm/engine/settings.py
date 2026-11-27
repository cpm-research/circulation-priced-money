"""The Economy settings: population size, calendar, behavioural switches and stress options.

Also the legacy rules, the switches that give the earlier engines' behaviour for regression checks.
"""
from dataclasses import dataclass, replace

import numpy as np

from cpm_abm.engine.constants import CARD_CUT_LEVEL, DISTRESS_DIAL_MAX, EWA_SHARE, HOLDING_COST, JOB_LOSS, RING_SIDE
from cpm_abm.engine.rates import m0_rates


@dataclass(frozen=True)
class Economy:
    """The economy: population size, calendar, behavioural switches and stress options.

    Defaults are the first run's settings (``docs/DECISIONS.md``): the household economy and failure cost (the card
    base, outside prices following r_out, normal job loss and completed spells among them) and the yardsticks and
    CPM's own rules (the issuer's costs and the owners' spread among them). Each of those rules has its switch below;
    ``LEGACY_STEP45`` turns the yardstick and pool rules off, and ``LEGACY`` (``legacy``) turns all of them off.
    Demurrage has none. Contract and price inputs (rho_H, o, C_fix, card APR ...) live in ``core_model.Inputs`` so
    the ABM and the core model read the same numbers. Every runner sets C_fix to its sourced level
    (``run_economy_figures.engine_inputs``, $0.18 a consumer unit a year); the core's 5e-5 is only the default of
    ``Inputs()``. The engine does not read the core's provider fee alpha, as P payments run on stablecoin rails. The
    failed-payment fee is the ABM's own (``FAIL_FEE``); the core model keeps its declared 5%.
    """

    n: int = 1000                 # people (each runner sets the size it runs; 100 for development)
    alpha: float = 1.5            # Pareto shape of initial wealth (liquid and illiquid)
    buffer_months: float = 0.6    # median initial wealth in months of own spending, before the survey's cushions
    beta: float = 0.5             # spending elasticity to relative wealth
    bundles: int = 32             # service bundles per person per month
    burn_in: int = 6              # months of S0 before launch, in every arm (declared)
    months: int = 60              # months after launch
    # Cap on settlement sweeps within a day; the iteration stops earlier at its fixed point. Under the harsh stress a
    # ring of late wages among payers with no money and no card can need thousands of sweeps. Days above SLOW_SWEEPS
    # are counted in slow_days.
    sweeps: int = 20_000
    wealth_floor: float = 0.02    # relative-wealth floor for spending (declared)
    seed: int = 20261021
    n12: bool = True              # outside safe return rises with wealth (False: rho_H for everyone)
    shocks: bool = False          # unexpected expenses from the Fed's SHED survey; off under normal conditions
    routing: str = "fee"          # "fee": P only where it saves the card fee; "all": every payment in P
    h4_months: int = 12           # leaving-rule experience window in months; 0 = one cycle
    # The leaving rule's logistic noise as a multiple of its scale, the core model's 1e-4 of each person's own monthly
    # spending; every result reports 0.5 and 2 beside it.
    leave_noise: float = 1.0
    # Core-model conventions (``core_model.py``): a participant's working cash is P and conversion costs
    # only the switching cost chi at joining and leaving; merchant-fee savings are a transfer kept out of experience
    # (f_ext = 0). The alternatives are sensitivities: routine conversion at every E-P crossing and
    # merchant savings counted in experience.
    routine_conversion: bool = False
    merchant_in_experience: bool = False
    # Stress: outside lenders' interest, and the card's fees, return to households by spending.
    lender_income_recirculated: bool = False
    inflation: float = 0.02 / 12  # CPI in every arm (the 2% target)
    # M0 rates. "reserve" (the default; M0 is the strongest real DeFi): USDC earns the bill less the Sky Savings Rate's
    # spread under it (``RESERVE_SPREAD``), floored at zero, paid from T-bill income as an outside flow, and Comet lends
    # against collateral at its borrow rate, both moving with r_out as observed (``m0_rates``). "pinned" reads the
    # supply and borrow rates off the pinned Comet curves at the utilisation this economy's own supply produces;
    # "fixed" is the earlier M0 convention (supply rho_H + premium whatever the volume), kept as the upper-bound
    # sensitivity.
    comet: str = "reserve"
    # How M0's rates follow r_out in the "reserve" mode: "observed" (default), one for one from the observed October
    # 2026 levels; "fitted", the lag-3 OLS lines of the same estimate, a sensitivity (``M0_FITTED``).
    m0_rates: str = "observed"
    # What the stablecoin pays its holder in M0, read only in the "reserve" mode: "reserve" (default), the bill less the
    # Sky spread (``m0_rates``); "none", nothing, and its issuer keeps the whole reserve return, as the large dollar
    # stablecoins do (their holders earn a yield only by lending them on). Comet's collateral lending and every other
    # M0 rule are unchanged. Example: at an outside rate of 4.4% a year a holder of $1,000 of USDC earns $39.59 a year
    # under "reserve" (4.4% less 0.441 point) and nothing under "none", and the issuer keeps $4.41 and $44 of the
    # reserve return on it.
    usdc_yield: str = "reserve"
    # M0's crypto collateral holders: this share of people, drawn once on a stream of their own (``build_population``),
    # can borrow from Comet against full cover, and nobody else. 0 (the default here and in the runners, CRYPTO_SHARE)
    # means no crypto collateral: collateral lending by Compound III is not run or reported, and the option remains
    # only for the unit tests of that code path. It replaces the core model's uniform ``collateral_cover``, which the
    # engine no longer reads.
    crypto_share: float = 0.0
    # Distress control: the extra monthly rate per job at which jobs lose their wage in a distress year, above normal
    # job loss (``job_loss``), in the year that starts distress_start months after launch and lasts distress_length
    # months (months 25-36); 0 is the level without distress. An extra layoff's wage leaves the household economy for
    # its whole spell, owed by its payer to the outside on the job's pay dates, its worker receiving nothing; after
    # normal job loss the payer keeps the wage, so level 0 is unchanged. No unemployment insurance is modelled; 2
    # points, the stress clause's headline, is 2009's wage loss before unemployment insurance.
    distress: float = 0.0
    distress_start: int = 24
    distress_length: int = 12
    # The household economy and failure cost, each rule with its switch; the legacy value of each is in
    # ``LEGACY_RULES``.
    # A re-queued wage counts once in the buffer replay's flows, on the day it first fell due.
    requeued_once: bool = True
    # Wages settle on their job's pay dates at BLS pay frequencies (``PAY_DAYS``), not on the recipient's billing dates.
    pay_dates: bool = True
    # At most this many failure fees a payer a model month, counted in fee units (a partly unpaid payment counts as its
    # share), reset on day 1; past it a failure carries no fee. np.inf is no monthly cap. Two: the S0 check gave $37.35
    # a consumer unit a year at two and $53.35 at three, both in the $28 to $62 band, and two leans against CPM.
    fees_a_month: float = 2.0
    # The buffer choice of payers without pool access prices failures past the monthly cap at $27 (a declared device
    # standing in for the closure and lost service the model omits); False prices them at $0, as the experience
    # replays do (the S0 check's second reading).
    buffer_prices_past_cap: bool = True
    # The failure fee is booked as fee debt: no interest, repaid first (False: outside debt at r_ext).
    fee_debt_free: bool = True
    # The real part's failure line counts unpaid shares of failed bills and wages and, for payers without a card,
    # bridged shares, each obligation once (False: fee units and pool payer-days). Read by the runner.
    failure_shares: bool = True
    # Earned-wage access in every arm: the share of people who hold it, drawn among wage earners on a stream of its
    # own (``EWA_SHARE``, an upper bound); a short payer without a card uses it after the pool and before failing. 0 is
    # no access.
    earned_wage_share: float = EWA_SHARE
    # Every non-housing bundle is card-eligible, 28% of spending (False: the core's card share of them, 18.2%).
    card_base_all: bool = True
    # Outside deposit and credit rates follow r_out from their October 2026 levels (``BILL_ANCHOR``; False: fixed): the
    # savings deposit rate by deposit_pass_through of a change, card and business rates one for one, and new vehicle and
    # personal loans by their own pass-throughs. The loan pass-throughs are sourced: the change in the Fed G.19
    # commercial-bank finance rate over the change in the three-month bill (FRED TB3MS, the same month), February 2022
    # to February 2024, the 2022 to 2023 tightening: new-car loans, 60 months (FRED RIFLPBCIANM60NM), 4.52% to 8.22%
    # against 0.33% to 5.24%, 0.75; 24-month personal loans (FRED TERMCBPER24NS), 9.39% to 12.49%, 0.63.
    # Least-squares slopes over the window's nine quarterly observations agree: 0.74 (standard error 0.06) and 0.66
    # (0.08). Series in data/raw/fred_g19_pass_through_20261113.
    # The shift is r_out less the October 2026 bill on r_out's basis (``outside_prices``), so at that rate nothing
    # moves.
    linked_rates: bool = True
    deposit_pass_through: float = 0.08
    vehicle_pass_through: float = 0.75
    personal_pass_through: float = 0.63
    # Normal job loss, the monthly rate per job in every month and every arm (``JOB_LOSS``; 0 is none).
    job_loss: float = JOB_LOSS
    # Spell lengths are completed lengths consistent with the BLS figures for spells in progress (False: those figures
    # read as completed lengths).
    completed_spells: bool = True
    # The yardsticks and CPM's own rules, each rule with its switch; the legacy value of each is in
    # ``LEGACY_STEP45``.
    # The issuer's own cost of P outstanding, a month, its expenses line (0.24% a year, ``HOLDING_COST``, the money
    # funds' cost of holding money; 0 is none). There is no provider fee or rail cost, as P payments run on stablecoin
    # rails.
    issuer_cost: float = HOLDING_COST
    # Owners' spread over the safe alternative, a month (0.25 point a year, declared, unsourced; 0 and 1 point are
    # sensitivities): applied alike to owners' alternative, every share's, and the coupon's capital part. The
    # yardsticks read it through ``_World._owners_alternative`` and ``_owners_alternative_nominal`` (0 is none).
    owner_spread: float = 0.0025 / 12
    # How the pool's paying its own way is read ("The pool pays its own way" in ``docs/DECISIONS.md``): "margin"
    # (default) reads the pool's own margin (``_World._own_margin``), with owners' compensation K at their alternative,
    # without the 0.9, and recovered principal credited in the old ratio's numerator; "coverage" is the earlier
    # self-financing test, collected income over 0.95 of K at 0.9 of r_out and the pool's costs. Read by the engine's K
    # and interest_collected records and by the runner's persistence test 4 and falsifier 3.
    self_financing: str = "margin"
    # What entrants compare with their alternative at dealing: "quote" (default), the pool's published quote at N*;
    # "realised", the pool's trailing realised return (``_World._track_record``), a sensitivity, which reads the quote
    # while the pool has no track record; "leaving_rule", a third reading between the two: the same track record, read
    # by each saver with the leaving rule's own dispersion (``_World._enters``), so "realised" is its limit with no
    # noise (``leave_noise`` 0).
    entry_reads: str = "quote"
    # Loan losses: "none" (default; a loan written off stays owed and is collected later, so lenders lose almost
    # nothing); "sourced", the bound: every lender, the pool included, discharges each month the sourced charge-off rate
    # of the bank loans its loans replace (``charge_off_rates``, ``_World._loan_losses``), and the pool's coupons carry
    # that rate (``_World._priced_loss``).
    loan_losses: str = "none"
    # The distress line cut: False (default), lines are held through the distress year, as in the first run; True cuts
    # each open line at the start of the distress year by its tier's sourced share times the distress level over 2%
    # (``CARD_CUT``, ``_World._cut_lines``), as the second run sets.
    card_line_cut: bool = False
    # How long the distress line cut lasts, in months from the cut, read only with the cut on: 0 (default), the cut
    # lines are never restored; m above 0, m months after the cut each line still open returns to what it would have
    # been without the cut, and a line charged off in the meantime stays closed. Total card lines were back near their
    # pre-recession high about ten years after 2008 (``CARD_CUT``), so the second run reads 120.
    card_cut_months: int = 0
    # The robustness switches (docs/ROBUSTNESS_PLAN.md, section 5), each off by default; every one draws on streams of
    # its own (``constants``), and the network, thresholds and launch set are the same in every arm
    # (``network.build_network``).
    # Buffer review share alpha: each month a person re-chooses its cash buffer only when its review draw is below
    # alpha, and otherwise keeps last month's. 1 is the base, everyone every month.
    buffer_review: float = 1.0
    # Joining rule: "linear", the base, chance xi0 + xi1 x contact share; "threshold", xi0 + xi1 where the contact share
    # is at least the person's own threshold and xi0 otherwise. Thresholds, read only under "threshold": "uniform" on 0
    # to 1, "measured" log-normal (``THRESHOLD_LOG_MEAN``), or one common number for everyone.
    joining: str = "linear"
    thresholds: object = "uniform"
    # Sellers of services, shocks and instalment purchases: "uniform" over the others, the base; "ring", one of the
    # buyer's 32 nearest positions on a ring with chance local_share and anyone else otherwise; "hubs", with chance
    # proportional to a weight falling with the rank of initial spending (``HUB_WEIGHT_EXPONENT``). Wage links are not
    # changed by these switches (``wage_links``).
    sellers: str = "uniform"
    local_share: float = 1.0
    # Launch placement: "scattered", the base, each person with chance a0; "neighbourhood" (ring only), the round(a0 n)
    # people on the first ring positions; "largest" (hubs only), the round(a0 n) people with the largest weights.
    launch: str = "scattered"
    # The pool's cash and its order of collection, each off by default (the first run's rule).
    # Standby: "measured" (default), one cash for loans for term loans, bridges and card-statement draws alike;
    # "reserved", in the arrangements with demurrage only (M1, M2), term loans take only the cash above the standby
    # the charge pays for, max(cash for loans - max(peak - pool bridging carried, 0), 0), with the peak bridging need
    # the month's terms read (``_World._cash_for_term``). Bridges and statement draws keep all the cash for loans, and
    # the pool without demurrage holds none back (but under ``uncharged_standby`` "reserved", below).
    standby: str = "measured"
    # Months of completed receipts other than wages the bridging budget reads (``_World._receipt_streams``): 1
    # (default), last month's; 2, the mean of the last two completed months (the one month while only one exists).
    # Wages are read from last month in both.
    receipts_window: int = 1
    # What the day's end collects first from all the borrower's money: "bridge" (default), what is due (missed
    # instalments and due bridges) and then overdue wages from money above the buffer; "wages", overdue wages from all
    # the borrower's money first and what is due after; "wages_same_budget", overdue wages first but from the money
    # above the buffer only, so that only the order changes. The monthly dealing keeps its order in all three.
    # Example ($400 of money, a $300 buffer, a $250 due bridge, a $200 overdue wage): the wage gets $0 under "bridge",
    # $200 under "wages" and $100 under "wages_same_budget", the bridge then $250 of what is left.
    collect_first: str = "bridge"
    # The capital target of the pool without demurrage (U): "mean" (default), the mean lending need; "peak", the
    # target of the pool with demurrage, the term lending need plus the peak bridging need, with no charge and no
    # other change (``_World._limit``).
    uncharged_target: str = "mean"
    # Purchases a month: "fixed" (default), ``bundles`` purchases a person, each 41.7% of its spending over
    # ``bundles``; "poisson_size", a Poisson number with mean ``bundles``, each of the same size, so the month's total
    # varies; "poisson_month", the same Poisson number (a count of zero taken as one), each 41.7% of spending over that
    # count, so the month's total is the same as under "fixed". The counts and each purchase's day, seller and card
    # flag are drawn on streams of their own (``PURCHASE_COUNT_STREAM``, ``PURCHASE_STREAM``), the same in every arm.
    purchases: str = "fixed"
    # Card statement dates: "common" (default), every statement closes on day 29 and is due on day 20 of the next
    # month; "own", each person's closing day drawn once, uniformly over the 30 days, on a stream of its own
    # (``STATEMENT_DATE_STREAM``), its statement covering the 30 days up to and including that day and due 21 days
    # after it, with the minimum payment, the late fee and the pool's payment of the statement on that day.
    statement_dates: str = "common"
    # The side studies of the second run, each off by default, so a run with every one at its default is the first
    # run bit for bit; each draws on streams of its own (``constants``).
    # The share of savers who read the pool's record at entry: None (default), every saver reads as ``entry_reads``
    # says; a share phi from 0 to 1 fixes each person for the run as a record-reader, when its draw on a stream of its
    # own (SCEPTIC_STREAM) is below phi, or a quote-reader otherwise, so a higher share's readers contain a lower
    # one's. Record-readers enter as everyone does under ``entry_reads`` "realised" and quote-readers as everyone does
    # under "quote" (``_World._entry_nominal``); it needs ``entry_reads`` "quote". Example: draws of 0.2 and 0.7 at phi
    # 0.5: the first reads the record, the second the quote; at phi 0.8 both read the record.
    sceptical_share: object = None
    # Owners who react to unpaid exits: "none" (default); "reviewers", at the dealing after one that left any executed
    # exit unpaid every owner whose review comes up files; "all", at that dealing every owner files, whether or not its
    # review came up (``_World._exits``). The trigger is read again at each dealing.
    owners_follow: str = "none"
    # When the distress years fall: "dated" (default), one year from distress_start months after launch for
    # distress_length months; "random", years of distress_length months that start at random months after launch and
    # never overlap, distress_expected of them expected in a run before overlaps are refused (the dial, at most
    # DISTRESS_DIAL_MAX), drawn on streams of their own from the seed and the run length only (``distress_years``),
    # so every arm and every distress level of a seed meets the same dates and a lower dial's years are among a
    # higher one's. distress_expected is read only under "random".
    distress_dates: str = "dated"
    distress_expected: float = 1.0
    # The household economy's edge and the stress year as a slowdown, each off by default, so a run with every one at
    # its default is the first run bit for bit.
    # The edge: "open" (default), money households pay across the edge (interest, fees, gas, wages owed outside) and
    # lose to inflation is gone for good, and money from outside (rewards, yields) comes in for good; "conserved", at
    # each close the month's net loss across the edge and to inflation, A = -(external + inflation), is paid back to
    # households' cash (``_World._return_edge``), so their total real wealth changes only by revaluation. The money
    # that leaves is the income of firms that households own, and comes back to them as owners and as workers and
    # sellers: person i receives A w_i, w_i = owners_share omega_i + (1 - owners_share) v_i, omega_i its fixed share of
    # equities (``DFA_EQUITIES``, by its wealth group at the opening) and v_i its share of the month's receipts from
    # other households. A negative A is collected with the same weights. Example: households lose 10 across the
    # edge and 2 to inflation and the outside pays them 4 in rewards: external is -6, A is 8, and with owners_share
    # 0.1 a person of the top 1% at 1,000 people (omega 0.0509) holding 0.2% of the receipts gets
    # 8 x (0.1 x 0.0509 + 0.9 x 0.002) = 0.055.
    edge: str = "open"
    # The sourced share of what households pay the financial side that is its owners' income (the same figure as
    # LENDER_SHARE in scripts/paper_numbers.py); the rest returns as wages and sales. Read only under edge "conserved".
    owners_share: float = 0.10
    # The distress year's extra layoffs: "outside" (default), the wage is still owed by its payer to the outside
    # (``OUTSIDE_WAGE``); "kept", a slowdown, the payer simply does not owe it and keeps the money, its worker receiving
    # nothing as before (recorded as wages_kept).
    distress_wages: str = "outside"
    # The share of purchases dropped in the distress year at the 2-point level (``CARD_CUT_LEVEL``), 0 by default: in a
    # distress month each purchase is dropped with chance x = distress_purchases x distress / 0.02, on one uniform a
    # purchase on a stream of its own (``DROP_STREAM``), the same in every arm, so a higher level's drops contain a
    # lower one's. A dropped purchase is not made, not retried and is no failure: the buyer keeps the money and the
    # seller receives nothing. It needs purchases "poisson_size". Example: 0.25 at a distress level of 0.01 drops
    # each purchase with chance 0.125, about 4 of a person's 32 a month.
    distress_purchases: float = 0.0
    # Who each wage goes to: "random" (default), each person pays one wage to one other person drawn uniformly, so the
    # wages a person receives are close to Poisson with mean 1 and about 37% receive none; "one_each", the links are a
    # random permutation with no fixed point (``wage_links_one_each``), drawn on a stream of its own (WAGE_LINK_STREAM),
    # so everybody pays one wage and receives exactly one and no other draw of the population moves. Example, 3
    # people: under "random" 0 may pay 1, 1 pay 0 and 2 pay 0, so 2 receives none; under "one_each" 0 pays 1, 1 pays 2
    # and 2 pays 0, or the reverse.
    wage_links: str = "random"
    # Whether the savings a person keeps in its own cash are spent on a durable before it borrows. At each dealing the
    # deposit part of spare money stays as the person's own cash when that cash pays at least the deposit rate, as a
    # participant's wallet does and bank money does not, and otherwise goes to outside savings. "used" (default): a
    # durable is paid from all own money above the buffer, then credit, so savings kept in the wallet are spent on it
    # while savings in a deposit are not, and the same person borrows less and keeps no cushion once its savings sit in
    # a wallet. "kept": the deposit part kept at the last dealing is left alone, as outside savings are, so the same
    # person borrows the same amount whichever vehicle holds its savings; under either a shortfall can draw on them the
    # same day. Under "kept" they then run down as outside savings do and are refilled only at the next dealing
    # (``_World._run_down_kept``). Example: $70,000 of own money, a buffer of $9,000 and $50,000 of savings kept at the
    # last dealing: a $48,000 durable takes $48,000 of own money and no loan under "used"; under "kept" it takes $11,000
    # and a loan of $37,000.
    durable_savings: str = "used"
    # The settings below each change one rule and are off by default, so a run with every one at its default is the
    # first run bit for bit.
    # Whether the leaving rule counts the card rewards a participant gives up: False (default), experience holds no such
    # term; True, each participant's monthly experience is charged the reward rate (``CARD_REWARDS``) on the
    # card-eligible purchases it paid from its wallet that its card would have taken (the month's ``card_internal``),
    # which in the bank arrangement would have earned rewards (``_World._forgone_rewards``). Example: a $1,000 card
    # purchase paid from the wallet costs $7.50.
    experience_rewards: bool = False
    # What the distress line cut cuts, read only with the cut on (with it off any value runs the lines held): "line"
    # (default), the whole line falls by the tier's share, while the starting balance, which the model never lets its
    # holder repay, stays, so a line cut below it leaves no room; "room", the room above the starting balance falls by
    # that share, the new line being the starting balance plus (1 - share) times the line above it
    # (``_World._cut_lines``). Restoration after card_cut_months returns the line as before under both. Example: a
    # line of $1,000 with a starting balance of $950 and a cut of 32.58%: under "line" it becomes $674.20 and the room
    # nothing; under "room" it becomes $983.71 and the room $33.71.
    card_cut_on: str = "line"
    # Whether the pool's covering budget counts what the card is already owed: False (default), only the loan book and
    # earned-wage advances; True, each holder's closed statement not yet due and its card purchases not yet billed
    # count among what its receipts must repay first, and where the statement itself is being refinanced, only the
    # unbilled purchases, so nothing is counted twice (``_World._c1_budget``). Example: $100 of expected receipts, an
    # empty loan book and a $100 statement owed: $100 spare under False, $0 under True.
    screen_card_owed: bool = False
    # The savings the buffer replay lets a saver offering money to the pool draw on the same day: "share_of_liquid"
    # (default), the deposit share of all its money less each candidate, max((1 - mm_share) x liquid - candidate, 0);
    # "share_of_spare", the deposit share of what is above each candidate, (1 - mm_share) x max(liquid - candidate,
    # 0), as the dealing leaves it under a full subscription (``_World._dealing``, ``choose_buffer``). Savers who offer
    # nothing draw all their money above the candidate under both. Example: $100 liquid, a candidate of $40 and a
    # money-market share of 50%: $10 under "share_of_liquid", $30 under "share_of_spare".
    buffer_reserve: str = "share_of_liquid"
    # How the stress year's split paydays count: "split" (default), the worker's wage for the days worked and the wage
    # owed outside for the days of an extra layoff are two obligations, each with its failed share and fee units;
    # "merged", every first-time wage row of one job and one pay date, worker's and outside's together (a pay period
    # across a month's end leaves two worker rows on one date too), counts as one row of their total for failed
    # shares, fee units, the failure fee and whole items returned, while the money still goes where it goes under
    # "split" (``_World._one_payday``). Example: a $100 payday split $60 and $40, half of each paid: failed shares 1.0
    # and a $27 fee under "split"; 0.5 and $13.50 under "merged", as for one $100 row half paid.
    stress_paydays: str = "split"
    # Whether the pool without demurrage (U) holds back cash from term loans: "none" (default), it holds none;
    # "reserved", by the same rule as the pool with demurrage under ``standby`` "reserved" (``_World._standby_held``),
    # which it needs, so that with ``uncharged_target`` "peak" the two pools differ only by the charge. Example, dollars
    # a person: a peak bridging need of 240, 80 carried and 300 of cash leave 140 open to term loans in M1 and, under
    # "reserved", in U, against 300 in U under "none".
    uncharged_standby: str = "none"
    # What the conserved edge's monthly payout returns, read only with ``edge`` "conserved": "accrued" (default),
    # A = -(external + inflation), which counts amounts booked when a debt to the outside is created (outside interest
    # as it accrues, the card's fees, the failure fee, the earned-wage fee, the stress year's wages owed outside and
    # the pool's unpaid operating cost), so households receive as cash what nobody has paid yet; "paid", each person's
    # stock of such amounts accrued and not yet paid is read liability by liability (``_World._edge_owed``: each
    # outside loan's accrued interest, its fee debt, the card's fees and interest, the earned-wage fees, the wages owed
    # outside, and the pool's payable), and the payout is A less the month's change in that stock, so an amount is
    # returned in the month a payment on the same liability clears it (``_return_edge``). It needs fee_debt_free, under
    # which the failure fee is a debt of its own. Example: $10 of card interest accrued in month 1 and paid with the
    # statement in month 2 is handed back in month 1 under "accrued" and in month 2 under "paid".
    payout: str = "accrued"
    # The share of the month's payout that is in fact returned to households, read only with ``edge`` "conserved": the
    # amount the payout rule gives (accrued or paid) times this share is paid by the same split as the whole, and the
    # rest leaves the household economy for good (recorded as ``edge_kept``). 1.0 (default) returns all of it; 0.0
    # returns nothing, the household numbers of the open edge. Example: $100 to return in a month gives $100, $10 and
    # $0 at 1, 0.10 and 0, with $0, $90 and $100 kept.
    edge_returned: float = 1.0
    # A day whose settlement does not reach a fixed point: "raise" (default), the run stops with an error at the sweep
    # cap; "hold", where the sweeps repeat two states with money still moving and nothing to defer, or reach the cap,
    # every request for same-day credit (the pool's bridge, Comet's, the card's cash advance, earned-wage access) stands
    # for the rest of the day at the most asked, and the sweeps go on with the requests only rising, so they end; a
    # payer short when it must pay keeps the credit it took, repaid by the day's collection. A day that reaches the cap
    # with no payer's completion moving by a cent of money (a cycle of rounding, nobody lending) is settled where it
    # stands. Every day that settles under "raise" is unchanged, and each use is counted (``settle_held``). Example: a
    # payer short $100 asks a $100 bridge in one sweep and nothing in the next, for ever, under "raise"; under "hold" it
    # draws $100 and the day settles with every payment made.
    settle_cycle: str = "raise"

    def __post_init__(self):
        """Refuse an unknown reading of self-financing or of M0's rates: a misspelt one would silently read as the
        coverage test or as the fixed rates."""
        if self.self_financing not in ("margin", "coverage"):
            raise ValueError(f"self_financing is 'margin' or 'coverage', not {self.self_financing!r}")
        if self.comet not in ("reserve", "pinned", "fixed"):
            raise ValueError(f"comet is 'reserve', 'pinned' or 'fixed', not {self.comet!r}")
        if self.m0_rates not in ("observed", "fitted"):
            raise ValueError(f"m0_rates is 'observed' or 'fitted', not {self.m0_rates!r}")
        if self.usdc_yield not in ("reserve", "none"):
            raise ValueError(f"usdc_yield is 'reserve' or 'none', not {self.usdc_yield!r}")
        if self.usdc_yield == "none" and self.comet != "reserve":
            raise ValueError("usdc_yield is read only in M0's 'reserve' mode (comet='reserve')")
        if self.entry_reads not in ("quote", "realised", "leaving_rule"):
            raise ValueError(f"entry_reads is 'quote', 'realised' or 'leaving_rule', not {self.entry_reads!r}")
        if self.loan_losses not in ("none", "sourced"):
            raise ValueError(f"loan_losses is 'none' or 'sourced', not {self.loan_losses!r}")
        if self.purchases not in ("fixed", "poisson_size", "poisson_month"):
            raise ValueError(f"purchases is 'fixed', 'poisson_size' or 'poisson_month', not {self.purchases!r}")
        if self.statement_dates not in ("common", "own"):
            raise ValueError(f"statement_dates is 'common' or 'own', not {self.statement_dates!r}")
        self._check_switches()
        self._check_side_studies()

    def _check_side_studies(self):
        """Refuse a side-study setting that is misspelt, out of range or in a combination it does not define: a share of
        record-readers is a number from 0 to 1 beside the quote reading; the dial of random distress years runs from 0
        to DISTRESS_DIAL_MAX and is read only under random dates; and the distress line cut, defined at the one dated
        distress year, is not combined with random ones."""
        share = self.sceptical_share
        if share is not None and (isinstance(share, bool) or not isinstance(share, (int, float))
                                  or not 0 <= share <= 1):
            raise ValueError(f"sceptical_share is None or one number from 0 to 1, not {share!r}")
        if share is not None and self.entry_reads != "quote":
            raise ValueError("sceptical_share mixes the quote and realised readings and needs entry_reads='quote'")
        if self.owners_follow not in ("none", "reviewers", "all"):
            raise ValueError(f"owners_follow is 'none', 'reviewers' or 'all', not {self.owners_follow!r}")
        if self.distress_dates not in ("dated", "random"):
            raise ValueError(f"distress_dates is 'dated' or 'random', not {self.distress_dates!r}")
        if not 0 <= self.distress_expected <= DISTRESS_DIAL_MAX:
            raise ValueError(f"distress_expected is from 0 to {DISTRESS_DIAL_MAX:g}, not {self.distress_expected!r}")
        if self.distress_dates == "dated" and self.distress_expected != 1.0:
            raise ValueError("distress_expected is read only under random distress years (distress_dates='random')")
        if self.distress_dates == "random" and self.card_line_cut:
            raise ValueError("the distress line cut is defined at the dated distress year, not with random ones")
        months = self.card_cut_months
        if isinstance(months, bool) or not isinstance(months, (int, np.integer)) or months < 0:
            raise ValueError(f"card_cut_months is a whole number of months from 0, not {months!r}")
        if months > 0 and not self.card_line_cut:
            raise ValueError("card_cut_months is read only with the distress line cut on (card_line_cut=True)")
        if self.wage_links not in ("random", "one_each"):
            raise ValueError(f"wage_links is 'random' or 'one_each', not {self.wage_links!r}")
        if self.durable_savings not in ("used", "kept"):
            raise ValueError(f"durable_savings is 'used' or 'kept', not {self.durable_savings!r}")
        self._check_edge()
        self._check_matched_rules()

    def _check_matched_rules(self):
        """Refuse a setting that is misspelt or in a combination it does not define."""
        if not isinstance(self.experience_rewards, bool):
            raise ValueError(f"experience_rewards is True or False, not {self.experience_rewards!r}")
        if self.card_cut_on not in ("line", "room"):
            raise ValueError(f"card_cut_on is 'line' or 'room', not {self.card_cut_on!r}")
        if not isinstance(self.screen_card_owed, bool):
            raise ValueError(f"screen_card_owed is True or False, not {self.screen_card_owed!r}")
        if self.buffer_reserve not in ("share_of_liquid", "share_of_spare"):
            raise ValueError(f"buffer_reserve is 'share_of_liquid' or 'share_of_spare', not {self.buffer_reserve!r}")
        if self.stress_paydays not in ("split", "merged"):
            raise ValueError(f"stress_paydays is 'split' or 'merged', not {self.stress_paydays!r}")
        if self.uncharged_standby not in ("none", "reserved"):
            raise ValueError(f"uncharged_standby is 'none' or 'reserved', not {self.uncharged_standby!r}")
        if self.uncharged_standby == "reserved" and self.standby != "reserved":
            raise ValueError("uncharged_standby 'reserved' holds back cash by the rule of standby 'reserved', which it "
                             "needs")
        if self.payout not in ("accrued", "paid"):
            raise ValueError(f"payout is 'accrued' or 'paid', not {self.payout!r}")
        if self.payout == "paid" and self.edge != "conserved":
            raise ValueError("payout 'paid' is read only with the conserved edge (edge='conserved')")
        if self.payout == "paid" and not self.fee_debt_free:
            raise ValueError("payout 'paid' reads the failure fee as a debt of its own, which needs fee_debt_free")
        share = self.edge_returned
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not 0 <= share <= 1:
            raise ValueError(f"edge_returned is a share from 0 to 1, not {share!r}")
        if share != 1 and self.edge != "conserved":
            raise ValueError("edge_returned is read only with the conserved edge (edge='conserved')")
        if self.settle_cycle not in ("raise", "hold"):
            raise ValueError(f"settle_cycle is 'raise' or 'hold', not {self.settle_cycle!r}")

    def _check_edge(self):
        """Refuse an edge or slowdown setting that is misspelt, out of range or in a combination it does not define: the
        conserved edge and the recirculation stress would both return the same money; the owners' share is a share;
        drops need purchases of fixed size at random, and their chance at the level run is a probability."""
        if self.edge not in ("open", "conserved"):
            raise ValueError(f"edge is 'open' or 'conserved', not {self.edge!r}")
        if self.edge == "conserved" and self.lender_income_recirculated:
            raise ValueError("the conserved edge already returns outside lenders' income; it is not combined with "
                             "lender_income_recirculated")
        if not 0 <= self.owners_share <= 1:
            raise ValueError(f"owners_share is a share from 0 to 1, not {self.owners_share!r}")
        if self.distress_wages not in ("outside", "kept"):
            raise ValueError(f"distress_wages is 'outside' or 'kept', not {self.distress_wages!r}")
        if not 0 <= self.distress_purchases <= 1:
            raise ValueError(f"distress_purchases is a share from 0 to 1, not {self.distress_purchases!r}")
        if self.distress_purchases > 0 and self.purchases != "poisson_size":
            raise ValueError("distress_purchases needs purchases='poisson_size'")
        if self.distress_purchases > 0 and self.distress_purchases * self.distress / CARD_CUT_LEVEL > 1:
            raise ValueError("distress_purchases x distress / 0.02, the chance a purchase is dropped, is at most 1")

    def _check_switches(self):
        """Refuse a robustness switch that is misspelt, out of range or in a combination the plan does not define: a
        neighbourhood launch needs the ring, a largest-first launch needs hubs, thresholds are read only under the
        threshold rule and a local share only on the ring, which needs more people than one neighbourhood."""
        if not 0 < self.buffer_review <= 1:
            raise ValueError(f"buffer_review is a share above 0 and at most 1, not {self.buffer_review!r}")
        if self.joining not in ("linear", "threshold"):
            raise ValueError(f"joining is 'linear' or 'threshold', not {self.joining!r}")
        named = isinstance(self.thresholds, str)
        if (named and self.thresholds not in ("uniform", "measured")) or (not named and (
                isinstance(self.thresholds, bool) or not isinstance(self.thresholds, (int, float))
                or not 0 <= self.thresholds <= 1)):
            raise ValueError(f"thresholds is 'uniform', 'measured' or one number from 0 to 1, not {self.thresholds!r}")
        if self.joining == "linear" and self.thresholds != "uniform":
            raise ValueError("thresholds are read only under the threshold joining rule (joining='threshold')")
        if self.sellers not in ("uniform", "ring", "hubs"):
            raise ValueError(f"sellers is 'uniform', 'ring' or 'hubs', not {self.sellers!r}")
        if not 0 <= self.local_share <= 1:
            raise ValueError(f"local_share is a share from 0 to 1, not {self.local_share!r}")
        if self.sellers != "ring" and self.local_share != 1.0:
            raise ValueError("local_share is read only on the ring (sellers='ring')")
        if self.sellers == "ring" and self.n <= 2 * RING_SIDE:
            raise ValueError(f"the ring needs more than {2 * RING_SIDE} people, one neighbourhood; got {self.n}")
        if self.launch not in ("scattered", "neighbourhood", "largest"):
            raise ValueError(f"launch is 'scattered', 'neighbourhood' or 'largest', not {self.launch!r}")
        needs = dict(neighbourhood="ring", largest="hubs").get(self.launch)
        if needs is not None and self.sellers != needs:
            raise ValueError(f"a {self.launch} launch needs sellers={needs!r}, not {self.sellers!r}")
        if self.standby not in ("measured", "reserved"):
            raise ValueError(f"standby is 'measured' or 'reserved', not {self.standby!r}")
        if isinstance(self.receipts_window, bool) or self.receipts_window not in (1, 2):
            raise ValueError(f"receipts_window is 1 or 2 months, not {self.receipts_window!r}")
        if self.collect_first not in ("bridge", "wages", "wages_same_budget"):
            raise ValueError(f"collect_first is 'bridge', 'wages' or 'wages_same_budget', not {self.collect_first!r}")
        if self.uncharged_target not in ("mean", "peak"):
            raise ValueError(f"uncharged_target is 'mean' or 'peak', not {self.uncharged_target!r}")


# The yardstick and pool rules switched off, as ``replace(economy, **LEGACY_STEP45)``. With no issuer cost the issuer's
# derived share of the reserve return is zero.
LEGACY_STEP45 = dict(issuer_cost=0.0, owner_spread=0.0, self_financing="coverage")
# Every household-economy, yardstick and pool rule off and no monthly cap of fees; ``legacy`` gives any economy these
# rules.
LEGACY_RULES = dict(requeued_once=False, pay_dates=False, fees_a_month=np.inf, fee_debt_free=False,
                    failure_shares=False, earned_wage_share=0.0, card_base_all=False, linked_rates=False, job_loss=0.0,
                    completed_spells=False, **LEGACY_STEP45)


def legacy(economy=None):
    """``economy`` (default ``Economy()``) with every household-economy, yardstick and pool rule off, no fee cap."""
    return replace(economy or Economy(), **LEGACY_RULES)


LEGACY = legacy()

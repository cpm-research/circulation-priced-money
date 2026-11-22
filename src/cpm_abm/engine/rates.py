"""Rates and the contract's arithmetic.

The outside world's rates and prices (savings returns by wealth rank, M0's rates, the outside prices a world runs
at, the month's charge-off rates of the loans the pool's loans replace), and the contract's derived quantities
(owners' realised returns, the logistic weight, the capital limit at free entry, the issuer's share of the reserve
return and what a unit of pool capital earns).
"""
import numpy as np

from cpm_abm.engine.constants import (BILL_MONTHLY, CHARGE_OFF_NORMAL, CHARGE_OFF_PEAK, COMET_BORROW_SPREAD,
                                      COMET_SUPPLY_SPREAD, DEPOSIT_FLOOR, DFA_DEPOSITS, DFA_GROUP_UPPER,
                                      DFA_MONEY_MARKET, EPS, FDIC_SAVINGS_RATE, JOB_LOSER_NORMAL, JOB_LOSER_PEAK,
                                      M0_FITTED, RESERVE_SPREAD)
from cpm_abm.engine.population import rank_share


def m0_rates(rho_H, mode="observed"):
    """M0's rates a month at the safe rate ``rho_H`` a month (decided 5 Nov: they move with the outside rate as
    observed): USDC's savings rate, Comet's borrow rate and Comet's supply rate. "observed", one for one from the
    October 2026 levels (``RESERVE_SPREAD``, ``COMET_BORROW_SPREAD``, ``COMET_SUPPLY_SPREAD``); "fitted", the lag-3 OLS
    lines (``M0_FITTED``), the savings rate capped at rho_H. Every rate is floored at zero."""
    if mode == "observed":
        return (max(rho_H - RESERVE_SPREAD, 0.0), max(rho_H + COMET_BORROW_SPREAD, 0.0),
                max(rho_H + COMET_SUPPLY_SPREAD, 0.0))
    line = lambda key: (M0_FITTED[key][0] + M0_FITTED[key][1] * 12 * rho_H) / 12
    return max(0.0, min(rho_H, line("savings"))), max(0.0, line("borrow")), max(0.0, line("supply"))


def charge_off_rates(jobs_without_wage):
    """The month's charge-off rate a year of each loss class (``LOSS_CLASSES``) at a share ``jobs_without_wage`` of
    jobs without a wage three months earlier (decided 12 Nov): normal + (peak - normal) x, x = max((J - 0.0232) /
    (0.0768 - 0.0232), 0), not capped above the peak (the anchors in payroll-job units, 14 Nov 2026). J of 0.0232 or
    less gives the normal rates, 0.0768 the peaks."""
    x = max((jobs_without_wage - JOB_LOSER_NORMAL) / (JOB_LOSER_PEAK - JOB_LOSER_NORMAL), 0.0)
    return CHARGE_OFF_NORMAL + (CHARGE_OFF_PEAK - CHARGE_OFF_NORMAL) * x


def money_market_share(wealth, n12=True):
    """Each person's money market share of outside savings, by current wealth-rank group (DFA); 1 with n12 off."""
    if not n12:
        return np.ones(wealth.size)
    group = np.searchsorted(DFA_GROUP_UPPER, rank_share(wealth), side="left")
    return (DFA_MONEY_MARKET / (DFA_DEPOSITS + DFA_MONEY_MARKET))[group]


def outside_return(wealth, rho, n12=True, deposit=FDIC_SAVINGS_RATE):
    """Each person's safe outside return per month, by current wealth-rank group (DFA, FDIC).

    Deposits earn ``deposit``, the savings deposit rate a month (by default
    the FDIC national savings rate of October 2026; a world passes its rate
    following r_out, 3 Nov), and money market fund shares earn rho_H, in each
    DFA group's proportions; with n12 off, everyone earns rho_H.
    """
    money_market = money_market_share(wealth, n12)
    return (1 - money_market) * deposit + money_market * rho


def outside_prices(rho_H, economy):
    """The outside prices a world runs at, from the safe rate ``rho_H`` a month (decided 3 Nov): the savings deposit
    rate a month, the shift a year of every card APR tier, and the shifts a year of new vehicle, personal and business
    loans, by product; with ``linked_rates`` off, the FDIC rate and no shift (None), as built.

    Every product is anchored at the October 2026 bills rate, the card tiers too, which carry no date of their own: a
    reading of the rule (4 Nov). The anchor is on r_out's basis, a nominal rate a year credited
    monthly (decided 5 Nov: every anchor on the monthly-credited basis), 4.135% (``BILL_MONTHLY``), where the 3 Nov
    build read the discount-basis 4.05% (``BILL_ANCHOR``). The deposit rate is floored at 0.06% a year.
    """
    if not economy.linked_rates:
        return FDIC_SAVINGS_RATE, None, None
    shift = 12 * rho_H - BILL_MONTHLY
    deposit = max(FDIC_SAVINGS_RATE + economy.deposit_pass_through * shift / 12, DEPOSIT_FLOOR)
    return deposit, shift, np.array([economy.vehicle_pass_through, economy.personal_pass_through, 1.0]) * shift


def own_returns(owned, rate, months=12):
    """Each household owner's realised return since buying, over at most ``months`` months, in every month (reported,
    decided 3 Nov; owners' exits read it at each dealing, ``_World._own_return``).

    owned: person-by-month pool capital after dealing (a run's ``owned``); rate: each month's return on a unit of
    capital, the same for every share (R, or R net of issuer money), NaN where there was no pool. A holding begins in
    the first month with capital after a month without; the return is the income credited from then, or from
    ``months`` months back if later, over the capital-time of those months. NaN where the person holds nothing.
    Owner level, value-weighted, on the NAV basis and before CPI (decided 4 Nov).
    """
    held, income, capital, _ = own_window(owned, rate, months)
    return np.where(held, income / np.where(held, capital, 1.0), np.nan)


def own_window(owned, rate, months=12):
    """The window each holding's realised return is read over (``own_returns``), in every month: whether the person
    holds capital, the income credited and the capital-time over the window, and the months it spans. A holding begins
    in the first month with capital after a month without, and the window runs from then, or from ``months`` months
    back if later. The owner exit rule (decided 5 Nov) reads the gap in dollars a month from it: the income less
    the alternative on the capital-time, over the months spanned."""
    held = owned > EPS
    month = np.arange(owned.shape[0])[:, None]
    began = held & ~np.vstack([np.zeros((1, owned.shape[1]), bool), held[:-1]])
    first = np.maximum(np.maximum.accumulate(np.where(began, month, 0), axis=0), month - months + 1)
    running = lambda values: np.vstack([np.zeros((1, owned.shape[1])), np.cumsum(values, axis=0)])
    window = lambda total: total[1:] - np.take_along_axis(total, first, axis=0)
    capital, income = window(running(owned)), window(running(owned * np.nan_to_num(rate)[:, None]))
    return held, income, capital, month - first + 1


def logistic(x):
    """The core model's overflow-safe logistic weight (``core_model.adopt``), 1 / (1 + exp(-x)) written as
    0.5 (1 + tanh(x / 2)), which the leaving rule reads (decided 4 Nov: the core model's logistic noise)."""
    return 0.5 * (1.0 + np.tanh(x / 2.0))


def paper_capital(lent, margin, alternative, real_rate, pool_rate=0.0):
    """The capital limit N*, the free-entry equilibrium of pool capital (derived 5 Nov from the zero-profit
    principle, as for the issuer and competitive P): owners enter until the quote (``paper_return``) equals their
    alternative. Lent capital earns the alternative through the coupon's capital part, the margin F is shared
    over all capital, and capital beyond the lending need P* sits as the pool's own cash at ``pool_rate`` (the reserve
    return less custody, p_net), so the quote at N >= P* is (alternative P* + F + pool_rate (N - P*)) / N, and it
    equals the alternative at N* = P* + F / (alternative - pool_rate), in closed form, never a monthly ratchet (the
    5 Nov review). F is the margin without the pool cash's own return. The October 2026 draft's proposition on a
    restoring capital incentive, N* = P* + m / rho, was the special case with no return on idle cash (``pool_rate``
    0); that contract, with a fee margin, was replaced. Under
    demurrage that pays for liquidity kept available (decided 5 Nov) ``lent`` is the capital target, the lending
    need with its bridging part at the cycle's peak, since demurrage pays the standby up to it the alternative less
    ``pool_rate``. F is the fee margin, 0 with no fees (decided 5 Nov), so the engine's N* is the capital target
    (``_World._limit``), equation (target) of paper/cpm.tex.

    N* is floored at P*, and is P* alone where F is at or below zero (the quote is then below the alternative at any
    capital above P*, so nobody enters beyond it) and where the real reserve rate is at or below zero (decided
    3 Nov: "the lending need alone when the real reserve rate is at or below zero"). The switch reads the real reserve
    rate, not the owners' alternative: the owners' spread keeps the alternative above zero where the real rate is zero
    (M2 at r_out 2%), and F over the spread alone would set a standby many times the lending need. ``real_rate`` is
    the reserve rate net of the arm's index, the contract's rho_p: in P terms in M2 (rho_H less dJ/J) and nominal in
    M1 (rho_H), so M1 at r_out 2% keeps a standby and M2 there has P* alone. Where idle cash earns the alternative
    itself (no owners' spread and no custody cost, the yardsticks off) the quote never falls to it and N* is
    unbounded: capital is then limited by households' supply alone. Every argument in one unit and period: money, and
    rates a month.
    """
    if real_rate <= 0 or margin <= 0:
        return lent
    gap = alternative - pool_rate
    return lent + margin / gap if gap > 0 else np.inf


def issuer_share(rate, cost):
    """The issuer's share of the reserve return on P (decided 4 Nov), derived, never set by hand: its break-even
    under contestable issuance. Free entry drives an issuer's profit to zero, so its custody share of the reserve
    return just covers its cost of holding a money balance, s_I rate = c_I, that is s_I = c_I / rate, at most 1:
    5.5% at a reserve rate of 4.4% a year and c_I 0.24% (ICI money funds 2025), 12% at 2%. At a rate at or below c_I
    no share covers the cost and the issuer takes all of it (1), the declared limit its stay test records (M2 at a zero
    real rate). ``rate`` is the reserve rate the contract runs at (real in M2), ``cost`` the issuer's cost of P
    outstanding, both a month; with no cost the share is zero. Under competitive P (decided 5 Nov) it is a record
    and the one place the issuer's take is derived: the issuer keeps s_I rate = c_I of the reserve return on all P, and
    wallet P pays its holders the rest, (1 - s_I) rate = rho_p - c_I, less demurrage."""
    return min(1.0, cost / rate) if rate > 0 else 1.0


def paper_return(lent, margin, capital, rate, pool_rate=0.0):
    """What a unit of pool capital earns, the free-entry quote (derived 5 Nov): loan income at ``rate`` on lent
    capital, the smaller of capital and the lending need ``lent``, plus the margin F, plus ``pool_rate`` on the
    capital beyond the lending need, the pool's own cash (the reserve return less custody, p_net), over capital; NaN
    with no capital. With ``pool_rate`` 0 it is the October 2026 draft's owner return A(N) / N, a contract since
    replaced. With ``rate`` the alternative, it equals the alternative at N* (``paper_capital``) and falls strictly
    above P* while F is positive and ``pool_rate`` is below the alternative; with F 0, as the engine runs it, it is
    the quote, equation (quote) of paper/cpm.tex. At unbounded capital it is ``pool_rate``, its limit."""
    if not capital > 0:
        return np.nan
    if np.isinf(capital):
        return pool_rate
    return (rate * min(capital, lent) + margin + pool_rate * max(capital - lent, 0.0)) / capital

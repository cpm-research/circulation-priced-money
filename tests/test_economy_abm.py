"""Tests for the economy ABM (src/cpm_abm/economy_abm.py), all at tiny scale (N <= 120, a few months).

What is covered
---------------
* Calibration: the population (wealth, spending, billing, cards), starting cushions from the Fed survey with the
  rest illiquid, outside returns by wealth group, the monthly obligations (wages, services) and card ownership by
  bracket.
* Accounting: the conservation identity in every arm (S0, M0, M1, M2, U), receivables equal open obligations,
  overdrafts are booked as debt, write-offs keep the legal debt while the loss is valuation, and the reserve account
  matches P owed (backing).
* Mechanics: priority payment, dual-balance conversion, instalments, fee routing (a card holder short of money puts
  card purchases on the card), the 12-month window of the leaving rule, CPI with indexed P (M2), Comet in M0, loss
  learning by product, the issuer as a pure custodian with no shares and no fund, its 12-month stay test, owners
  leaving by the users' rule on a stream of their own and paid from pool cash after the notice, the wind-down,
  same-day savings (in settlement, the statement, instalments and the buffer replay), the flat failure fee on bills
  and wages (at most one a day, in settlement, the pool's limit and the replay), common random numbers across arms,
  and pool coverage lowering failures.
* One savings rule: only the money-market part of spare money goes to the pool, while its quote reaches the saver's
  own outside rate (r_out plus the owners' spread). Owners file to exit by the logistic leaving rule on each owner's
  own realised return. Runs that check the pool's own mechanics use a test device whose savers compare the pool with
  their mixed return, so a pool forms.
* Competitive P and pool entry (section (Entry and exit) of paper/cpm.tex): the issuer keeps its derived break-even
  custody, c_I of every unit of P; the holding charge (demurrage) c is the last cycle's capital cost of bridging over
  its wallet P balance-time, at most rho_p - c_I, so coverage is 1 unless c is bounded; wallet P is paid
  y_P = rho_p - c_I - c on its balance-time, demurrage goes to the pool and the pool's own cash earns rho_p - c_I;
  P's published yield is what the deposit rule and the replay read; coverage seals a bridge at the coupon less the
  capital part demurrage pays; demurrage pays for the liquidity kept available, the standby at the alternative less
  what idle cash earns, so owners earn their alternative on a steady cycle and N* starts from the peak bridging
  need; demurrage that just pays the cut leaves the margin at zero and the pool cash's return is pool income;
  capital settles at N*, the capital target, since F = 0 with no fees, where the quote is owners' alternative, and a
  pool whose last share is paid out reopens by free entry in a later dealing, with the launch plan pricing the fixed
  cost on its lending need and no demurrage; U is the same P with c = 0 on the same draws; and a small run with no
  provider fee forms a pool at its limit with every record kept and wealth exact in every arm.
* P payments on stablecoin rails: a P payment costs its payer one transfer's gas, with or without a pool, half a
  USDC payment's two legs; no provider fee exists anywhere and the engine reads none; the issuer has no fee or rail
  line; the coupon carries the pool's fixed cost at break-even, and the pool's own margin is zero at break-even in a
  steady cycle.
* M0 as the strongest real DeFi: USDC earns the bill less the Sky Savings Rate's spread under it, read on chain, and
  Comet's rates move with r_out one for one from their observed October medians (the fitted lines a sensitivity); a
  USDC payment pays two legs of Base gas whatever its value; USDC converts at no fee. The pool's fixed cost is
  sourced and the runners read its level.
* The boundary rule: card, conversion and pool costs leave the economy, card rewards come back, outside lenders'
  interest returns only under the stress, and the real part, transfers and cash check match their worked examples.
* The population map: the distress reading (a quarter of the dip, three months running, looked for after the dip),
  the reward-for-failure share, the share of seeds Persistent (a seed where a falsifier fires is not, nor one worse
  than M0 where the cell is systematically worse) and its Wilson interval, the full cross on fresh seeds, and one
  short distress job read end to end, every job running S0, M0, U, M1 and M2.
* The region reading and its figures: a pool arm's cell is stable when its pool forms and persists by the Wilson
  rule, the issuer stays and every group's mean gain against S0 and M0, read in full, is at least -$2 a person a
  year, each part on its worked example, with the bare-majority reading beside; liquidity and demurrage by window
  match their worked examples; and the region figures draw from a tiny synthetic store as PNG and PDF, skip what a
  store cannot support and never overwrite.
* The records: a run stores the Inputs fields and constants the engine reads, the Economy without the fields each
  job sets, the share of bridges wanted the pool drew under its own name, and cash to lend, which credit death
  reads; provenance hashes each source as committed and names the Comet pin; the map defaults to 12 workers on one
  BLAS thread each, can select cells of the grid (Step 2 is 6 jobs and 30 runs) and writes its four stores, read
  back with their labels, notes and selection; and the records change no outcome.
* The failure counts: failed bills and wages in fee units, unpaid shares and whole items (the fewest a bank paying
  smallest first returns), declined card-eligible purchases apart, the pool's bridges in their place, the fee
  reproduced from the counts, the monthly cap read from their spread, and the counting changes no outcome.
* The wage-loss path and paired differences: jobs without a wage as the month's average and on its last day, stored
  for every arm with the wages their payers kept, and each seed's paired differences against S0 and M0 a year after
  launch, by harm group, quintile, billing cycle and class (card holding x income source), with the gain by the
  arm's own W2 role beside; neither changes an outcome.
* Reports: owners' realised return from the pool's books (each owner's own since buying, over at most 12 months),
  the issuer's share of pool capital and crossings between E and P (at most one a person a step in each kind, net),
  with the runner's reads and stored monthly series; net of issuer money, owners lose at most their whole holding;
  none of them changes an outcome. Owners' return by loan year: the pool's loans by product and the year after
  launch they were made, their income to owners (coupons less the operating cost, write-offs, recoveries) and
  principal-time, adding up to the books R reads; it changes no outcome.
* The buffers people choose: each person's buffer as the dealing chose it, by month, and its means by card holding,
  stored for every arm and by person for S0 on the development seeds; it changes no outcome.
* Each record that changes no outcome is checked against a run with it silenced on every other record of the run,
  including in a forced run with distress whose owners ask to exit and whose pool takes demurrage.
* The household economy and failure cost: the replay counts a re-queued wage once; wages settle on their jobs' BLS
  pay dates; at most two fees a payer a model month, the cap binding at whatever it is set to, the buffer replay
  pricing failures past them at $27 and the experience replays at $0, the pool's limit counting the capped fee; fee
  debt is interest-free and repaid first; and the real failure line counts unpaid and bridged shares. Earned-wage
  access applies only to wages earned and still unpaid, on a job not in a spell, up to half of them, and is repaid
  first from that wage, on time or late; the three places that compare the pool with the advance (the loan-cost
  comparison, the pool's same-day limit and the replays) match their worked examples; holders are drawn among
  earners on their own stream; and wealth accounting stays exact with access in every arm. Payers in chronic deficit
  are flagged at launch, the same in every arm, and the flag changes no outcome. Every non-housing bundle is
  card-eligible (28% of spending); outside prices follow r_out from their October 2026 levels (each product's value
  at r_out 2, 4.4 and 6%, existing loans keeping their sealed rates, the 0.06% deposit floor); normal job loss at
  0.55% a month gives a 1.9% stock, spells are identical before the distress year across arms and levels, and
  completed spells match the BLS statistics of spells in progress. Holders' card bridging is recorded, the S0 check
  runs S0 alone, and the run record stores the outside prices and the distress labels.
* The yardsticks' shared helpers: the capital limit N* switches on the real reserve rate and the return on capital
  matches its worked examples; a late wage paid in P pays gas on the share it completes; the issuer's books carry
  its 0.24% of P in its wallet, fund refill and stay test, per $1 of P as the worked example gives; and the report
  adds those costs to the most it could bear.
* The yardsticks' records and readings: the pool's own margin and its parts match their worked examples (zero at
  break-even), a written-off bridge repaid in full nets to its interest and its principal is credited in the old
  ratio, which is 1.000 at the capital limit without the 0.9; the joint issuer-and-pool test matches its worked
  example and equals its bottom-up form every month of forced runs; queued exits and the 90% household reading on
  both bases, persistence test 4 and falsifier 3 on household-held months match their worked examples; M2's gains
  are read in full, with no issuer transfer line; and the transfers report and gain split carry the gas paid to
  validators.
* Credit by person and month, records only: non-negative, summing to the loan book's new instalment principal by
  lender and to the bridging and outside-interest series, no pool credit in S0, and the runner's report by class.

Run with ``python -X utf8 -m unittest tests.test_economy_abm`` with ``src`` on the path (see the README).
"""
import contextlib
from dataclasses import replace
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import warnings

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import (BIG, BILL_ANCHOR, BRIDGE, BUSINESS_APR, CARD_APR, CARD_CUT, CARD_FRAUD, CARD_LINE,
                                 CARD_MAXED, CARD_OWNERSHIP, CARD_REVOLVING, CASH_ADVANCE, CASH_ADVANCE_APR,
                                 CASH_ADVANCE_FEE_FLOOR, CASH_ADVANCE_FEE_RATE, CASH_LINE_SHARE, CHARGE_OFF_DAYS,
                                 CHARGED_OFF, LATE_FEE, LATE_FEE_REPEAT, card_lines, card_tier,
                                 limit_with_card, limit_with_revolve,
                                 CARD_PROCESSING, CARD_REWARDS, COMPLETED_SPELL_MEDIAN_DAYS,
                                 COMPLETED_SPELL_SIGMA, CONSUMER_UNITS, CONVERSION_FEE, CREDIT_RECORDS,
                                 BILL_MONTHLY, COMET_BORROW_OCTOBER, COMET_BORROW_SPREAD, COMET_SECONDS_PER_YEAR,
                                 COMET_SUPPLY_OCTOBER, COMET_SUPPLY_SPREAD, CRYPTO_SHARE, CYCLE_DAYS, DAYS,
                                 DEPOSIT_FLOOR, DFA_DEPOSITS, DFA_MONEY_MARKET, SSR_HIGH, SSR_LOW, SSR_CHANGE_DAYS,
                                 EPS, EWA_COST, GAS_PER_PAYMENT, GAS_PER_P_PAYMENT, GAS_PER_TRANSFER, RESERVE_SPREAD,
                                 SSR_OCTOBER, USDC_CONVERSION,
                                 EWA_FEE, EWA_LIMIT, EWA_SHARE, FAIL_COST, FAIL_FEE, FAILURE_COUNTS, FEE_DEBT,
                                 FDIC_SAVINGS_RATE, HOLDING_COST, HOUSEHOLDS_BY_EDUCATION, INCOME_BRACKETS,
                                 ISSUER_BOOKS, JOB_LOSS, LABOUR_SHARE, LATE_OUTSIDE_WAGE, LATE_WAGE, OUTSIDE_WAGE,
                                 LEGACY_STEP45, LOAN_YEARS, M0_FITTED, MARGIN_PARTS, MONTH_USD, OVERDRAFT, PAY_DAYS,
                                 PAY_SHARES, PERSONAL_APR, REVOLVE, SERVICE, SHOCK,
                                 SPELL_MEDIAN_DAYS, SPELL_SIGMA, STAY_MONTHS,
                                 TERM, VEHICLE_APR, WAGE, Economy, _World, allocate, billing_cycle_shares,
                                 build_population, choose_buffer, draw_spells, in_order, issuer_share, layoff_weight,
                                 legacy,
                                 limit_with_advance, limit_with_fee, logistic, m0_rates, monthly_credited,
                                 outside_prices, outside_return, own_returns, own_window, per_second_monthly,
                                 paper_capital, paper_return, pareto_stratum_means, rank_share, replay_cost, simulate,
                                 spell_law, spell_stock, term_outside_apr)


TINY = Economy(n=80, months=6, burn_in=3)


class SweepCapTests(unittest.TestCase):
    """The settlement sweep cap is 20,000 a day, and days needing more than 500 sweeps are counted."""

    def test_the_cap_is_twenty_thousand_and_slow_days_are_recorded(self):
        from cpm_abm.economy_abm import SLOW_SWEEPS
        self.assertEqual((Economy().sweeps, SLOW_SWEEPS), (20_000, 500))
        series = simulate(Inputs(), 0.6, TINY, "M1")["series"]
        after = slice(TINY.burn_in, None)
        self.assertTrue((series["most_sweeps"][after] >= 2).all())
        self.assertTrue((series["slow_days"][after] >= 0).all())
        self.assertTrue(((series["slow_days"][after] > 0) <= (series["most_sweeps"][after] > SLOW_SWEEPS)).all())


def tiny_world(arm="S0", economy=TINY):
    """A fresh world with an open month of accumulators, ready for direct method checks."""
    world = _World(Inputs(), 0.6, economy, arm)
    world.acc = {key: np.zeros(economy.n) for key in ("conversion", "receipts", "v", "gas")}
    world.acc.update(gas_paid=0.0, recovered=0.0, recovered_principal=0.0, interest_collected=0.0, written_off=0.0,
                     written_off_bridge=0.0, written_off_term=0.0, lost=np.zeros(2),
                     age_loss=np.zeros(LOAN_YEARS), vintage_income=np.zeros((2, LOAN_YEARS)),
                     vintage_exposure=np.zeros((2, LOAN_YEARS)))
    return world


def controlled_world(arm="M1", cost=None):
    """A ten-person world after one quiet month, emptied to a controlled state."""
    inputs = Inputs() if cost is None else replace(Inputs(), C_fix=cost)
    w = _World(inputs, 0.6, Economy(n=10, burn_in=10, months=1, inflation=0.0), arm)
    w.month(0)
    zero = lambda name: getattr(w, name).__setitem__(slice(None), 0.0)
    # Earned-wage accruals and advances owed are emptied with the other accounts.
    list(map(zero, ("cash", "pcash", "savings", "shares", "card_statement", "card_unbilled", "od_pending",
                    "receivable", "payable", "buffer", "accrued", "ewa_owed")))
    w.book = {key: value[:0] for key, value in w.book.items()}
    w.ob = {key: value[:0] for key, value in w.ob.items()}
    w.req = {key: value[:0] for key, value in w.req.items()}
    w.holder[:], w.part[:] = False, False
    w.sector = dict.fromkeys(w.sector, 0.0)
    w.acc["rewards"][:] = 0.0   # the quiet month's rewards were paid at its close
    w.acc["fee_units"][:] = 0.0   # a count left from the quiet month would cap the fees
    # Normal job loss may leave a job in a spell after the quiet month (its month-0 stock or a layoff in it); a
    # controlled state has none, so every job pays unless a test lays it off.
    w.spell_start[:], w.spell_end[:] = 0, 0
    # The card accounts are emptied too: every line is open-ended, with no starting balance and nothing owed on the
    # card, so a test that makes someone a holder meets a limit only where it sets one.
    w.card_line[:], w.card_start = 1e6, np.zeros(10)
    w.card_interest[:], w.card_fees[:], w.card_past_due[:], w.card_paid[:] = 0.0, 0.0, 0.0, 0.0
    w.card_late_since[:], w.card_late_month[:] = BIG, -BIG
    w.external = w.valuation = 0.0
    entering(w)
    w.today = {key: np.zeros(10) for key in ("financing", "fees", "saved", "card_internal", "discretionary", "unpaid",
                                             "savings")}
    return w


def entering(w):
    """Make every saver review entry at every dealing: entry-review draws of zero, so a dealing test called directly
    reads the entry rule itself, with every saver offering. In a run savers review entry at the users' rate, 0.166 a
    month, and the run's monthly draws replace these."""
    w.entry_draw = np.zeros(w.n)


def one_invoice(w, face=1.0, at=30, card=True):
    """One service invoice from person 0 to person 1, settling on day `at`, card-eligible unless `card` is False."""
    w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([float(face)]), settle=np.array([at]),
                card=np.array([card]), kind=np.array([SERVICE]))
    w.receivable[1] = w.payable[0] = face


def funded_pool(w, capital=10.0):
    """Everyone participates and the pool holds `capital` of cash owned by person 2."""
    w.part[:] = True
    w.pool_cash, w.nav_ps = capital, 1.0
    w.shares[2] = capital
    w.service = w.asking = w.launched = True


def entry(**fields):
    """One closed month's ``window`` entry for the pool's terms, every field zero but those given: the lending need and
    its term part, the margin, the fixed cost and the lent principal-time, demurrage's parts and, by day (demurrage
    pays for liquidity kept available), the carried bridging principal, the bridging refused and the pool cash held
    ready."""
    base = dict(need=0.0, margin=0.0, fixed=0.0, lent=0.0, revenue=0.0, covered=0.0, capital_cost=0.0, wallet=0.0,
                float_pool=0.0, charges=0.0, need_term=0.0, bridging=np.zeros(DAYS), refused_bridging=0.0,
                ready=np.zeros(DAYS))
    return dict(base, **fields)


def closed(w, month, rate):
    """Stand in for month ``month``'s close in a dealing test: the two records the owner exit rule reads, each
    household's capital after dealing and the month's R net of issuer money."""
    w.held_path[month], w.r_owners[month] = w.shares * w.nav_ps, rate


def earning(w, rate):
    """Every month's records as the owner exit rule reads them: each household's holding now and R ``rate``, so every
    owner's own realised return is ``rate`` whenever it bought."""
    w.held_path[:], w.r_owners[:] = w.shares * w.nav_ps, rate


def reviewing(w, noise=0.0):
    """Make every owner review at every dealing and leave on its draw (owners leave by the users' rule): review and
    leaving draws of zero, and the rule's noise at ``noise`` times its scale. With none (the default) an owner files
    exactly when its realised gap in dollars falls short of minus its leaving cost, the rule's limit without noise."""
    w.owner_draws = np.zeros(w.n), np.zeros(w.n)
    w.economy = replace(w.economy, leave_noise=noise)


class PooledWorld(_World):
    """Test device for the pool's mechanics: savers compare the pool with their own mixed return, not with their own
    outside rate as the savings rule has it, so a pool forms in a small run; the money-market split still applies."""

    def _cycle_terms(self, month):
        super()._cycle_terms(month)
        self.pool_alternative = self.r_out.copy()


def pooled(inputs, a0, economy, arm):
    """``simulate`` for the test device: a run whose pool forms."""
    return PooledWorld(inputs, a0, economy, arm).run()


class EnteringWorld(PooledWorld):
    """The test device with every saver reviewing entry every month, for runs whose inputs set upsilon, the review rate
    entry shares with participation, to zero: a draw of zero is not below zero, so the review itself is forced."""

    def _reviews_entry(self):
        return np.ones(self.n, bool)


class ForcedRun(PooledWorld):
    """A partial run in the test device: for three months the pool's quote and every owner's own realised return are
    held below most owners' own rate, and every owner reviews and leaves where the users' rule gives it better than
    even odds, so owners ask to exit and the pool pays them from its cash after the notice, the rest waiting for cash
    (the issuer is a pure custodian and buys no shares). Small runs never see such exits on their own, so the run is
    forced. Own rates include the owners' spread, so both are set at their 30th percentile, which keeps the lowest
    group of owners in."""

    def _forced(self, month):
        owned = self.shares > EPS
        if month in (8, 9, 10) and owned.any():
            return float(np.quantile(self._owners_alternative_nominal()[owned], 0.3)) - self.index
        return None

    def _cycle_terms(self, month):
        super()._cycle_terms(month)
        forced = self._forced(month)
        self.R_hat = self.R_hat if forced is None else forced
        if forced is not None:
            self.owner_draws = np.zeros(self.n), np.full(self.n, 0.5)

    def _own_return(self, month):
        own, forced = super()._own_return(month), self._forced(month)
        return own if forced is None else np.where(np.isfinite(own), forced, own)


# The forced run's economy, with distress at the map's highest level over six months from the second after launch,
# and 24 months after launch beside it.
FORCED = Economy(n=100, burn_in=3, months=16)
FORCED_DISTRESS = replace(FORCED, distress=0.02, distress_start=2, distress_length=6)
FORCED_LONG, FORCED_DISTRESS_LONG = replace(FORCED, months=24), replace(FORCED_DISTRESS, months=24)
# Every series the real part reads (``real_part``), for its worked examples.
REAL_SERIES = ("pt_card", "pt_pool_card", "pt_pool_nocard_card", "pt_pool_card_credit", "pt_term", "pt_pool_term",
               "penalties", "nocard_bridges", "fail_shares", "fail_items", "bridged_shares", "bridged_items",
               "bridged_card", "card_payments", "card_value", "p_payments", "p_value", "gas", "money_bt", "savings_bt",
               "shares_bt", "pool_operating", "ewa_uses")


@lru_cache(maxsize=None)
def kept_run(world, arm, economy):
    """One run of ``world`` (a class) at a0 0.6, kept for every test that compares a run against it; no test changes
    a run it reads."""
    return world(Inputs(), 0.6, economy, arm).run()


# The map's short economy: 40 people over 12 months after launch, with a three-month distress year.
MAP_ECONOMY = Economy(n=40, burn_in=2, months=12, distress_start=3, distress_length=3)


@lru_cache(maxsize=None)
def map_jobs():
    """Two short map jobs at r_out 4.4% and a0 0.6 on a development seed, without distress and at 2%, kept for every
    test that reads a job; no test changes a job it reads."""
    from scripts.run_economy_population import job
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return tuple(job((0.044, 0.6, level, 20261021, 40, False), MAP_ECONOMY) for level in (0.0, 0.02))


def map_seed(seed, letter="P", worse_trade=False, harmed=(), formed=True, gains=None, m0=None):
    """One seed of a map cell for the reading's worked examples: every report zero, the pool arms reading A (Against:
    the issuer would leave), P (Persistent) or I (Inconclusive: P4 fails), worse than M0 on trade and harmed in the
    given groups when asked. For the region reading: whether the pool formed and the gains against S0 by class,
    quintile and cycle, read in full, each a dict of lists, zero where not given; against M0 the same, unless ``m0``
    gives the gains against M0."""
    from scripts.run_economy_population import REAL_LINES
    zero = lambda *keys: dict.fromkeys(keys, 0.0)
    money = lambda: zero("launch_usd", "end_usd", "lowest_usd")
    windows = lambda *keys: {key: [0.0, 0.0] for key in keys}
    wealth = lambda given: dict({f"gain_usd_a_year_by_{name}": (given or {}).get(name, [0.0] * size)
                                 for name, size in (("class", 4), ("quintile", 5), ("cycle", 2))}, gain_usd_a_year=0.0)
    # The complete gain equals the wealth gain at both ends here: no seller's sales differ. The gain under the
    # cash-advance bound is the same too: no arm differs in cash advances.
    end = lambda given: dict(wealth(given), bound=wealth(given))
    by = lambda given: dict(wealth(given), bound=wealth(given), complete_gain=dict(face=end(given), zero=end(given)))
    against = dict(S0=by(gains), M0=by(m0) if m0 is not None else by(gains))
    common = dict(zero("mean_gain_usd", "median_gain_usd", "issuer_usd", "p_yield_pct",
                       "better_off", "A_launch", "A_W1", "A_W2", "failures_pct", "merchant_fees_pct"),
                  split=dict(other=0.0), fees_usd_a_year=[0.0] * 5, failed_usd_a_year=[0.0] * 5,
                  transfers_usd_a_year=[0.0] * 5, real_part=zero(*REAL_LINES),
                  transfers=dict(total=zero("paid_usd")), cash=dict(everyone=money(), poorer_half=money()),
                  crossings=dict(routine=zero("a_year", "a_participant_year", "usd_a_year"),
                                 conversions=zero("a_year", "usd_a_year")),
                  liquidity=windows("precautionary_usd", "shortfall_covered_usd_a_year", "failed_usd_a_year"),
                  # Credit and purchases by class, zero in every class.
                  by_class={key: [0.0] * 4 for key in ("class_sizes", *CREDIT_RECORDS, "completed", "lost", "durables",
                                                       "sales")},
                  against=against)
    rate = lambda: dict(W1=None, W2=None, by_year=[None] * 5)
    reported = dict(owners=dict(gross_pct=rate(), net_pct=rate(), capital_W2_usd=0.0, own_net_W2_lowest_pct=None,
                                own_net_W2_mean_pct=None,
                                by_loan_year=dict.fromkeys(("all", "bridge", "term"), [None] * LOAN_YEARS),
                                by_loan_year_own=dict.fromkeys(("all", "bridge", "term"), [None] * LOAN_YEARS),
                                shared_unallocated_usd=0.0),
                    owners_excess=dict(alternative_pct=0.0, W1=None, W2=None),
                    # The yardsticks: the own margin and joint test by window, and the 90% reading.
                    own_margin_usd_a_year=[0.0, 0.0], own_margin_held_months=[12, 12], joint_usd_a_year=[0.0, 0.0],
                    pays_its_way_W2=letter != "I",
                    issuer_never_leaves=letter != "A",
                    households=dict(households_hold_90_W2=True, households_hold_90_W2_all_capital=True,
                                    p_routes_W2=True, counts=True),
                    # The contract and demurrage.
                    pool_formed=formed, demurrage=dict(windows("float_pool_usd_a_year", "charges_usd_a_year"),
                                                       s_issuer=0.0545))
    tests = dict(P=dict(P1=True, P2=True, P3=True, P4=letter != "I", P5=True),
                 X=dict(X1=False, X2=False, X3=False, X4=None, X5=False, X6=letter == "A"), verdict=letter)
    pool = dict(common, **zero("c_pct", "r_g_pct", "theta", "N", "N_star", "coverage", "r_b_pct", "quote_pct",
                               "bridges_drawn_over_wanted",
                               "backing_lowest", "backing_topup_usd", "fee_refused_usd", "fee_refused_n",
                               *(f"issuer_{key}_{unit}" for key in ("headroom", "costs", "most_cost")
                                 for unit in ("usd_a_year", "share_of_P"))),
                V1_worse=worse_trade, V3_harmed=np.isin(np.arange(10), harmed).tolist(), issuer_limit=False, **tests,
                **reported)
    return dict(r_out=0.044, a0=0.6, distress=0.0, recirculated=False, seed=seed, S0=common,
                arms=dict(M0=common, M1=pool, M2=pool))


def synthetic_store(folder, arms=("U", "M1", "M2"), levels=(0.0, 0.02), months=24):
    """A tiny map store written by hand as the population runner writes one: two r_out, two a0 and the given distress
    levels, S0, M0 and the given pool arms, each pool arm's region reading cycling through the readings (M2's at r_out
    2% its declared limit), and two seeds' monthly paths at the baseline r_out and a0."""
    from scripts.run_economy_population import VERDICTS
    rates, a0s = (0.02, 0.044), (0.3, 0.6)
    readings = [name for name in VERDICTS if name != "declared limit"]
    by_window = lambda value: [value, value]
    liquidity = lambda money, ratio, failed: dict(precautionary_usd=by_window(money),
                                                  precautionary_per_dollar_covered=by_window(ratio),
                                                  failed_usd_a_year=by_window(failed))
    cells, turn = [], 0
    for rate, a0, level in ((rate, a0, level) for rate in rates for a0 in a0s for level in levels):
        cell = dict(r_out=rate, a0=a0, distress=level, seeds=2, S0_liquidity=liquidity(1000.0, 0.6, 40.0),
                    M0=dict(A_W2=a0, liquidity=liquidity(990.0, 0.6, 38.0)))
        for k, arm in enumerate(arms):
            name = "declared limit" if arm == "M2" and rate == 0.02 else readings[(turn + k) % len(readings)]
            cell[arm] = dict(A_W2=a0 + 0.01 * k, N=0.1 * k, r_b_pct=6.0 - k, r_g_pct=7.0 - k,
                             liquidity=liquidity(900.0 + 10 * k, 0.4, 30.0 - k),
                             against=dict(S0=dict(gain_usd_a_year=5.0 * k - 3)),
                             region=dict(verdict=name, verdict_majority=name))
        cells.append(cell)
        turn += 1
    path = lambda scale: [scale * (1 + month / months) for month in range(months)]
    contract = lambda k: dict(A=path(0.5), N=path(0.05 * k), Q=path(0.06 * k), c=path(1e-5), coverage=path(0.5),
                              theta=path(0.3), r_b=path(0.004), r_g=path(0.005), quote=path(0.004))
    jobs = [dict(r_out=0.044, a0=0.6, distress=level, seed=seed, recirculated=False,
                 monthly={arm: contract(k) for k, arm in enumerate(arms)}) for level in levels for seed in (1, 2)]
    economy = dict(inflation=0.02 / 12, distress_start=3, distress_length=3)
    outside = [dict(r_out=rate, card=[0.25 + rate, 0.24 + rate, 0.19 + rate]) for rate in rates]
    (folder / "summary.json").write_text(json.dumps(dict(economy=economy, outside_rates=outside, cells=cells)),
                                         encoding="utf-8")
    (folder / "measures.json").write_text(json.dumps(dict(economy=economy, jobs=jobs)), encoding="utf-8")


class EconomyAbmTests(unittest.TestCase):
    """The population, dated settlement, credit and conservation of wealth."""

    def test_population_follows_its_calibration(self):
        """Pareto tail, median wealth 0.6, spending exponent 0.5, exact cycle mix and card ownership by bracket."""
        pop = build_population(Economy(n=1000))
        wealth = pop["wealth"] + pop["illiquid"]
        means = pareto_stratum_means(1000, 1.5)
        self.assertAlmostEqual(float(np.sort(means)[-100:].sum() / means.sum()), 0.1 ** (1 - 1 / 1.5), places=12)
        self.assertAlmostEqual(float(pop["spending"].mean()), 1.0, places=12)
        self.assertAlmostEqual(float(np.median(wealth) / np.median(pop["spending"])), 0.6, places=12)
        self.assertLess(float(np.ptp(np.log(pop["spending"]) - 0.5 * np.log(wealth))), 1e-12)
        counts = np.array([np.sum(pop["cycles"] == T) for T in CYCLE_DAYS])
        np.testing.assert_array_less(np.abs(counts - billing_cycle_shares() * 1000), 1.0)
        bracket = np.searchsorted(np.cumsum(INCOME_BRACKETS)[:-1], rank_share(pop["spending"]), side="right")
        size = np.bincount(bracket, minlength=4)
        np.testing.assert_array_equal(np.bincount(bracket, weights=pop["holder"], minlength=4),
                                      np.round(CARD_OWNERSHIP * size))
        self.assertTrue(np.all((pop["score"] >= 300) & (pop["score"] <= 851)))
        self.assertFalse(np.any(pop["wage_to"] == np.arange(1000)))

    def test_starting_cushions_follow_the_fed_survey_where_it_is_lower(self):
        """Starting liquid cushions follow the Fed survey (2025) where it is below the wealth calibration: 18% start
        under $100, 30% under $500 and half under $2,000, while nobody's total wealth is under $2,042; above the 62nd
        percentile all wealth is liquid. The rest is illiquid wealth, so total wealth, spending and the DFA ranks do
        not depend on the cushions."""
        pop = build_population(Economy(n=1000))
        dollars = pop["wealth"] * MONTH_USD
        total = (pop["wealth"] + pop["illiquid"]) * MONTH_USD
        self.assertGreater(float(total.min()), 2042.0)
        for line, share in ((100.0, 0.18), (500.0, 0.30), (2000.0, 0.50)):
            self.assertEqual(float(np.mean(dollars < line)), share)
        rank = rank_share(total)
        survey = np.interp(rank, [0.0, 0.18, 0.30, 0.50, 0.62], [0.0, 100.0, 500.0, 2000.0, 5000.0])
        np.testing.assert_allclose(dollars, np.where(rank <= 0.62, np.minimum(total, survey), total), rtol=1e-12)
        self.assertTrue(np.all(pop["illiquid"] >= 0.0))
        self.assertEqual(float(pop["illiquid"][rank > 0.62].max()), 0.0)

    def test_outside_return_rises_with_wealth_from_the_deposit_rate(self):
        """Each DFA group earns its deposit/money-market mix; the return rises with rank and never exceeds rho_H."""
        rho = Inputs().rho_H
        rate = outside_return(np.linspace(0.1, 10.0, 1000), rho)
        self.assertTrue(np.all(np.diff(rate) >= 0))
        share = DFA_MONEY_MARKET / (DFA_DEPOSITS + DFA_MONEY_MARKET)
        self.assertAlmostEqual(float(rate[0]), float((1 - share[0]) * FDIC_SAVINGS_RATE + share[0] * rho), places=15)
        self.assertTrue(np.all(rate < rho) and np.all(rate > FDIC_SAVINGS_RATE))
        np.testing.assert_allclose(outside_return(np.ones(5), rho, n12=False), rho)

    def test_obligations_follow_wages_services_and_billing(self):
        """32 service bundles of 41.7% of spending and one wage contract of 58.3%; each bill settles on the payee's
        billing date and each wage on its job's pay date (under the legacy rules, wages too on the payee's billing
        date)."""
        world = tiny_world()
        world.acc = dict(shocks=0.0, volume=0.0)
        world._obligations(0)
        ob, cycles, phases = world.ob, world.pop["cycles"], world.pop["phases"]
        service, wage = ob["kind"] == SERVICE, ob["kind"] == WAGE
        self.assertTrue(np.all(np.bincount(ob["buyer"][service], minlength=TINY.n) == TINY.bundles))
        np.testing.assert_allclose(np.bincount(ob["buyer"][service], weights=ob["amount"][service], minlength=TINY.n),
                                   (1 - LABOUR_SHARE) * world.spending)
        np.testing.assert_allclose(np.bincount(ob["buyer"][wage], weights=ob["amount"][wage], minlength=TINY.n),
                                   LABOUR_SHARE * world.spending)
        np.testing.assert_array_equal(ob["seller"][wage], world.pop["wage_to"][ob["buyer"][wage]])
        self.assertFalse(np.any(ob["buyer"] == ob["seller"]))
        seller, buyer = ob["seller"][~wage], ob["buyer"][wage]
        self.assertTrue(np.all((ob["settle"][~wage] - phases[seller]) % cycles[seller] == 0))
        pay_days, pay_phase = world.pop["pay_days"], world.pop["pay_phase"]
        self.assertTrue(np.all((ob["settle"][wage] - pay_phase[buyer]) % pay_days[buyer] == 0))
        self.assertEqual(int((ob["kind"] == 2).sum()), 0)  # shocks are off under normal conditions

    def test_wealth_changes_only_through_outside_flows_and_valuation(self):
        """Every month, the change in total net wealth equals outside flows plus write-off valuation, in every arm, with
        and without outside lenders' interest returned to households."""
        for economy in (TINY, replace(TINY, lender_income_recirculated=True)):
            for arm in ("S0", "M0", "U", "M1", "M2"):
                series = simulate(Inputs(), 0.6, economy, arm)["series"]
                np.testing.assert_allclose(series["wealth_change"],
                                           series["external"] + series["valuation"] + series["inflation"], atol=1e-12)

    def test_receivables_match_open_obligations(self):
        """Every receivable is an open obligation: settled, lost and re-queued entries are never paid twice."""
        world = _World(Inputs(), 0.6, replace(TINY, months=4), "M1")
        world.run()
        open_amount = np.bincount(world.ob["seller"], weights=world.ob["amount"], minlength=TINY.n)
        np.testing.assert_allclose(world.receivable, open_amount, atol=1e-12)
        np.testing.assert_allclose(world.payable, np.bincount(world.ob["buyer"], weights=world.ob["amount"],
                                                              minlength=TINY.n), atol=1e-12)

    def test_fee_routing_settles_only_card_eligible_purchases_in_p(self):
        """Fee routing: wages and free transfers between participants stay on E and card purchases use P; routing "all"
        settles more payments in P. P payments need a pool with owners, so the run is the test device whose pool
        forms."""
        run = pooled(Inputs(), 1.0, replace(TINY, n=60), "M1")
        log = run["payments"][TINY.burn_in]
        world = _World(Inputs(), 1.0, replace(TINY, n=60), "M1")
        self.assertGreater(int((log[3] == 2).sum()), 0)
        self.assertTrue(np.all(world.holder[log[0][log[3] == 2].astype(int)]))
        settled_h3 = pooled(Inputs(), 1.0, replace(TINY, n=60, routing="all"), "M1")["payments"][TINY.burn_in]
        self.assertGreater(int((settled_h3[3] == 2).sum()), int((log[3] == 2).sum()))

    def test_leaving_experience_averages_the_last_twelve_months_in_p(self):
        """Exit reads the mean monthly experience over the last 12 months in P."""
        economy = replace(TINY, months=16, h4_months=12)
        world = _World(Inputs(), 0.6, economy, "M1")
        world.run()
        self.assertEqual(world.exp_hist.shape[0], 12)
        stayed = world.status[-1] & world.part
        np.testing.assert_array_equal(np.isfinite(world.exp_hist[-1]), stayed)
        # The threshold's balance is kept over the same months in P: each month's wallet P balance-time.
        self.assertEqual(world.p_hist.shape, world.exp_hist.shape)
        np.testing.assert_array_equal(np.isfinite(world.p_hist), np.isfinite(world.exp_hist))

    def test_the_leaving_rule_reads_its_hand_cases(self):
        """The leaving rule: a reviewer with a 12-month average experience e leaves with probability
        logistic((-e - threshold) / noise scale), the threshold one conversion of its 12-month average P balance spread
        over the 12 months and the noise scale 1e-4 of its own monthly spending.

        Example, at the mean spending of $6,440 a month and an average P balance of $3,220: the conversion fee is
        0.05% + $0.22 / $142 = 0.2049% (the 1 cent fraud adjustment included), so the threshold is 0.0020493 x $3,220 =
        $6.599, $0.5499 a month, and the noise scale is $0.644. At zero gain: 0.5499 / 0.644 = 0.8539, exp(0.8539) =
        2.3487, 1 / 3.3487 = 0.299; the review share upsilon is 1 - exp(-0.166) = 0.15295, so a participant leaves at
        0.15295 x 0.2986 = 4.6% a month. At a gain of $0.5: 1.0499 / 0.644 = 1.6303, 1 / (1 + 5.1052) = 0.164; $1:
        1.5499 / 0.644 = 2.4067, 1 / (1 + 11.097) = 0.083; $2: 2.5499 / 0.644 = 3.9595, 1 / (1 + 52.43) = 0.019. At an
        experience exactly minus the threshold half the reviewers leave. Half the noise: 0.5499 / 0.322 = 1.7077,
        1 / (1 + 5.5164) = 0.153 at zero gain; twice: 0.5499 / 1.288 = 0.4269, 1 / (1 + 1.5325) = 0.395. Without noise
        (``leave_noise`` 0) a reviewer leaves exactly when its experience is below minus the threshold. A participant
        not reviewing, and a non-participant, never leaves. In M0 USDC converts at no fee, so the threshold is zero
        and a reviewer at zero gain leaves with one half."""
        def leaves(experience, draw, arm="M1", noise=1.0, reviewing=True, joined=True, balance=3220.0):
            w = controlled_world(arm)
            w.economy = replace(w.economy, leave_noise=noise)
            w.spending[:] = 1.0
            w.part[:] = joined
            got = w._leaving(np.full(10, experience / MONTH_USD), np.full(10, balance / MONTH_USD), np.zeros(10),
                             np.full(10, 0.1 if reviewing else 0.2), np.full(10, draw))
            return bool(got[0])
        threshold = CONVERSION_FEE * 3220.0 / 12
        self.assertAlmostEqual(threshold, 0.5499, places=4)
        self.assertAlmostEqual(Inputs().noise * MONTH_USD, 0.644, places=12)
        chance = lambda gain, scale=0.644: float(logistic((-gain - threshold) / scale))
        self.assertAlmostEqual(chance(0.0), 0.299, places=3)
        self.assertAlmostEqual(Inputs().upsilon, 0.15295, places=5)
        self.assertAlmostEqual(Inputs().upsilon * chance(0.0), 0.046, places=3)
        np.testing.assert_allclose([chance(gain) for gain in (0.5, 1.0, 2.0)], [0.164, 0.083, 0.019], atol=5e-4)
        self.assertAlmostEqual(chance(0.0, 0.322), 0.153, places=3)
        self.assertAlmostEqual(chance(0.0, 1.288), 0.395, places=3)
        for gain in (0.0, 1.0):
            self.assertTrue(leaves(gain, chance(gain) - 1e-9))
            self.assertFalse(leaves(gain, chance(gain) + 1e-9))
        self.assertTrue(leaves(-threshold, 0.5 - 1e-9))
        self.assertFalse(leaves(-threshold, 0.5 + 1e-9))
        for noise, scale in ((0.5, 0.322), (2.0, 1.288)):
            self.assertTrue(leaves(0.0, chance(0.0, scale) - 1e-9, noise=noise))
            self.assertFalse(leaves(0.0, chance(0.0, scale) + 1e-9, noise=noise))
        self.assertTrue(leaves(-threshold - 0.01, 0.999999, noise=0.0))
        self.assertFalse(leaves(-threshold + 0.01, 0.0, noise=0.0))
        self.assertFalse(leaves(-100.0, 0.0, reviewing=False))
        self.assertFalse(leaves(-100.0, 0.0, joined=False))
        self.assertTrue(leaves(0.0, 0.5 - 1e-9, arm="M0"))
        self.assertFalse(leaves(0.0, 0.5 + 1e-9, arm="M0"))

    def test_the_leaving_draws_have_a_stream_of_their_own(self):
        """The leaving rule's draws come one a person a month from a stream of their own, the same in every arm, so
        taking them moves no other draw: the joining and review draws still come from the adoption stream in its own
        order."""
        economy = replace(TINY, months=3)
        draws = {arm: _World(Inputs(), 0.6, economy, arm).leave_rng.random(economy.n)
                 for arm in ("M0", "U", "M1", "M2")}
        for arm in ("U", "M1", "M2"):
            np.testing.assert_array_equal(draws[arm], draws["M0"])
        own = np.random.default_rng(np.random.SeedSequence([economy.seed, 29])).random(economy.n)
        np.testing.assert_array_equal(draws["M1"], own)
        adopt = np.random.default_rng(np.random.SeedSequence([economy.seed, 7]))
        w = _World(Inputs(), 0.6, economy, "M1")
        w.leave_rng.random(economy.n)
        adopt.random(economy.n)                                    # the launch draw
        np.testing.assert_array_equal(w.adopt_rng.random(economy.n), adopt.random(economy.n))

    def test_holding_a_buffer_in_p_costs_the_money_market_part_alone(self):
        """The buffer replay's holding cost: the deposit part of spare money stays in P (or USDC) while it pays at least
        the deposit rate, so the deposit part of a buffer held in P forgoes P's own yield, not the deposit rate, and a
        participant's cost of holding a buffer all in P is mm_share x (rho_H - y_P), never negative. The person's mixed
        return less y_P would be below zero for most people (a mixed return of about 0.9% against y_P of about 4.1%)
        and would keep nearly all liquid money as buffer. A non-participant's checking pays below deposits, so its
        cost is its mixed return less checking. In M1, U and M0 alike."""
        from unittest import mock
        from cpm_abm import economy_abm
        from cpm_abm.engine import world_dealing   # where _dealing looks choose_buffer up
        for arm in ("M1", "U", "M0"):
            w = controlled_world(arm)
            w.part[:5] = True
            w.last["p_share"][:] = 1.0
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            with mock.patch.object(world_dealing, "choose_buffer", wraps=economy_abm.choose_buffer) as replay:
                w._dealing(1)
            hold = replay.call_args_list[0].args[4]
            self.assertGreater(w.p_yield, w.deposit_rate, arm)
            expected = np.where(w.part, w.mm_share * (w.inputs.rho_H - w.p_yield), w.r_out - w.inputs.buffer_yield)
            np.testing.assert_allclose(hold, expected, rtol=1e-12, atol=1e-18, err_msg=arm)
            self.assertTrue(np.all(hold >= 0.0), arm)
            self.assertTrue(np.any((w.r_out - w.p_yield)[w.part] < 0.0), arm)      # the mixed return less y_P

    def test_experience_credits_p_yield_on_the_deposit_part_above_the_deposit_rate(self):
        """Experience's yield: the deposit part of spare money kept in P would earn the deposit rate were the person to
        leave, so experience credits P's yield on it less the deposit rate, on at most the month's P balance-time; the
        rest of the balance earns its full yield.

        Example (monthly units): a participant with 1 of wallet P balance-time and 0.004 of yield, of which 0.4 is the
        deposit part kept, is credited 0.004 - 0.4 x the deposit rate; with 2 of deposit part kept (more than its
        balance), 0.004 - 1 x it."""
        def credited(kept):
            w = controlled_world("M1")
            w.part[0] = True
            w.acc["p_bt"][:], w.acc["p_yield"][:], w.acc["deposit_kept"] = 0.0, 0.0, np.zeros(10)
            w.acc["p_bt"][0], w.acc["p_yield"][0], w.acc["deposit_kept"][0] = 1.0, 0.004, kept
            w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
            return float(w.series["exp_yield"][-1]), w.deposit_rate
        got, rate = credited(0.4)
        self.assertAlmostEqual(got, 0.004 - 0.4 * rate, places=15)
        got, rate = credited(2.0)
        self.assertAlmostEqual(got, 0.004 - 1.0 * rate, places=15)

    def test_joining_and_leaving_m0_are_conversions_whatever_the_fee(self):
        """Crossings (reported only): joining, leaving and P redeemed for a non-participant convert whatever the fee, so
        USDC's free conversion in M0 is counted as conversions, not routine crossings, as in M1."""
        for arm in ("M0", "M1"):
            w = controlled_world(arm)
            w.cash[:2] = 1.0
            w.crossed = np.zeros((2, 10))
            joined = np.zeros(10, bool)
            joined[:2] = True
            w._join(joined, np.ones(10))
            self.assertFalse(w.crossed[0].any(), arm)
            np.testing.assert_allclose(w.crossed[1][:2], 1.0 / (1 + w.conversion), rtol=1e-12)
            w.crossed = np.zeros((2, 10))
            w._leave(joined)
            self.assertFalse(w.crossed[0].any(), arm)
            np.testing.assert_allclose(w.crossed[1][:2], -1.0 / (1 + w.conversion), rtol=1e-12)
            w.crossed = np.zeros((2, 10))
            w._credit_p(np.array([5]), np.array([0.5]))
            self.assertFalse(w.crossed[0].any(), arm)
            self.assertAlmostEqual(float(w.crossed[1][5]), -0.5, places=15)

    def test_the_monopoly_bound_is_the_largest_issuer_share_the_quote_still_reaches(self):
        """What a monopoly issuer could take, a bound that is recorded only: the largest share s of the reserve return
        it could keep with the quote still reaching owners' alternative.

        Example (one model month standing for the year, the reserve rate 4.4%): over the last cycle wallet P held
        $1,000 of balance-time, bridging cost $30 of capital, which demurrage took in full, and the fee margin F
        without that demurrage was A = -$10. An issuer keeping a share s of the reserve return leaves wallet P
        (1 - s) 44, so demurrage takes min(30, (1 - s) 44) and F(s) = -10 + min(30, (1 - s) 44) reaches zero, where the
        quote reaches owners' alternative, up to s = 1 - 10 / 44 = 77.3%. With A at zero any share up to 1 leaves it
        there; where even all of the bridging cost cannot (A = -$40) the bound is undefined; in U, with no demurrage, A
        below zero is undefined too. A small run whose pool forms (100 people, no provider fee) records it, wherever
        it is defined, between 0 and 1, and M0, with no pool, never."""
        def bound(rest, arm="M1"):
            w = controlled_world(arm)
            w.rho_p = 0.044
            charges = 0.0 if arm == "U" else 30.0
            entry = dict(margin=(rest + charges) / 2, charges=charges / 2, wallet=500.0, capital_cost=15.0)
            return w._monopoly_share([entry, dict(entry)])
        self.assertAlmostEqual(bound(-10.0), 1 - 10.0 / 44.0, places=12)
        share = bound(-10.0)
        self.assertAlmostEqual(-10.0 + min(30.0, (1 - share) * 44.0), 0.0, places=10)
        self.assertEqual(bound(0.0), 1.0)
        self.assertTrue(np.isnan(bound(-40.0)))
        self.assertTrue(np.isnan(bound(-10.0, "U")))
        self.assertEqual(bound(5.0, "U"), 1.0)
        from scripts.run_economy_figures import engine_inputs
        economy, inputs = Economy(n=100, months=4), engine_inputs()
        recorded = simulate(inputs, 0.6, economy, "M1")["series"]["s_monopoly"][economy.burn_in:]
        defined = recorded[np.isfinite(recorded)]
        self.assertTrue(defined.size > 0 and np.all((defined >= 0.0) & (defined <= 1.0)))
        self.assertTrue(np.isnan(simulate(inputs, 0.6, economy, "M0")["series"]["s_monopoly"]).all())

    def test_cpi_deflates_nominal_stocks_but_not_indexed_p(self):
        """CPI erodes E and nominal P (M1) in real terms; M2's indexed P keeps its real value."""
        economy = replace(TINY, inflation=0.02 / 12)
        factor = 1 / (1 + economy.inflation)
        m1, m2 = tiny_world("M1", economy), tiny_world("M2", economy)
        list(map(lambda w: (w.pcash.__setitem__(slice(None), 1.0), w.cash.__setitem__(slice(None), 2.0)), (m1, m2)))
        change_m1, change_m2 = m1._deflate(), m2._deflate()
        np.testing.assert_allclose(m1.pcash, factor)
        np.testing.assert_allclose(m2.pcash, 1.0)
        np.testing.assert_allclose(m2.cash, 2.0 * factor)
        self.assertLess(change_m1, change_m2)

    def test_m0_has_no_pool_charge_or_issuer_and_pays_comet_yield(self):
        """M0: participants earn the Comet supply rate on USDC; no pool, holding charge or issuer income."""
        series = simulate(Inputs(), 0.6, TINY, "M0")["series"]
        after = slice(TINY.burn_in, None)
        self.assertEqual(float(np.nanmax(series["c"][after])), 0.0)
        self.assertEqual(float(np.nanmax(series["N"][after])), 0.0)
        self.assertEqual(float(np.nanmax(series["issuer"][after])), 0.0)
        self.assertGreater(float(np.nanmean(series["exp_yield"][after])), 0.0)

    # ---- Closure, funding and lending limits ----------------------------------------------------------------------
    def test_insolvent_closure_creates_no_money(self):
        """Pool costs are paid only from pool cash; an unpaid payable at closure is the creditor's loss, not new money.
        The emptied pool is open again, since free entry applies in every month."""
        w = controlled_world(cost=0.2)
        w.pool_cash, w.shares[1], w.nav_ps, w.capital = 1.0, 1.0, 1.0, 1.0
        w.had_owners = w.service = w.launched = True
        start = w.net_wealth().sum()
        w._close(0, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertEqual((float(w.shares.sum()), w.pool_cash, w.pool_payable, w.winding), (0.0, 0.0, 0.0, False))
        self.assertLessEqual(w.net_wealth().sum(), start + 1e-12)
        self.assertAlmostEqual(w.net_wealth().sum() - start, w.external + w.valuation, places=12)

    def test_unfunded_payment_chain_fails_without_overdraft(self):
        """Settlement reaches its fixed point: nobody with no money or card pays, and no overdraft funds anyone."""
        w = controlled_world("S0")
        w.ob = dict(buyer=np.arange(4), seller=np.arange(1, 5), amount=np.ones(4), settle=np.full(4, 30),
                    card=np.zeros(4, bool), kind=np.full(4, SERVICE))
        np.add.at(w.receivable, w.ob["seller"], 1.0)
        np.add.at(w.payable, w.ob["buyer"], 1.0)
        w._settle(1, 30)
        self.assertEqual(float(w.cash.sum()), 0.0)
        self.assertEqual(float(w.od_pending.sum()), 0.0)

    def test_share_subscription_never_borrows_its_fee(self):
        """A non-participant buys at most spare / (1 + conversion fee) of shares and takes on no debt (all of its
        spare money in money-market funds, so all of it is offered)."""
        w = controlled_world()
        w.cash[:], w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 1.0, 0.0, 1.0, 100.0, 0.02, True   # Q does not bind
        w.mm_share[:] = 1.0
        w.last["flows"][:] = 0.0
        w.last["flows_s0"][:] = 0.0
        w._dealing(1)
        self.assertAlmostEqual(float(w.shares.sum()), 10 / (1 + CONVERSION_FEE), places=10)
        self.assertEqual(float(w.book["principal"].sum()), 0.0)

    def test_gas_comes_from_owned_funds(self):
        """A payer that cannot fund a P payment's gas from its own money does not get a pool loan for it; it pays by
        card."""
        w = controlled_world()
        funded_pool(w)
        w.holder[0], w.card_apr[0], w.r_g = True, 0.01, 0.005
        w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
        one_invoice(w)
        w._settle(1, 30)
        self.assertEqual(int(w.book["pool"].sum()), 0)
        self.assertAlmostEqual(float(w.card_unbilled[0]), 1.0)

    def test_pool_lends_only_what_observed_receipts_repay_in_two_months(self):
        """No pool loan beyond what two months of receipts repay; the card is due on its own covering date."""
        w = controlled_world()
        funded_pool(w, 200.0)
        w.holder[0], w.cash[0] = True, 0.2
        w.last["receipts"][:] = 0.1
        one_invoice(w, 100.0, card=False)
        w._settle(1, 30)
        pool = w.book["pool"]
        self.assertEqual(float(w.book["principal"][pool].sum()), 0.0)
        self.assertTrue(np.all(w.book["due"][pool] <= 30 + 60))
        self.assertTrue(np.all(w.book["due"][~pool] > 30 + 60))   # outside maturity is not cut to the pool horizon

    def test_covering_budget_reserves_term_interest(self):
        """The covering budget puts term principal and interest due in the next two months ahead of a new bridge.

        Example ($, monthly rates): a $20,000 term loan at 6% a year paying $400 of principal a month puts $800 of
        principal and $200 of interest ahead; interest already accrued counts too, and a loan with one instalment left
        carries one month of interest."""
        w = controlled_world()
        w._add_loans(np.array([0]), False, TERM, np.array([20000.0]), 0.06 / 12, 0.06 / 12, BIG, np.array([50]), 0)
        owed = lambda: float(w._c1_budget(60)[2][0])
        self.assertAlmostEqual(owed(), 800.0 + 200.0, places=9)
        w._accrue()                                                # a day of interest, accrued and not yet due
        self.assertAlmostEqual(owed(), 1000.0 + 20000.0 * 0.005 / DAYS, places=9)
        w.book["principal"][0], w.book["interest"][0] = 400.0, 0.0
        self.assertAlmostEqual(owed(), 400.0 + 400.0 * 0.005, places=9)

    @staticmethod
    def wage_only_world(cycle, phase, pay_days, pay_phase, wage=3755.0):
        """Person 0's only receipt last month is one wage of `wage` dollars from job 3, on that job's pay dates; person
        0 bills on its own `cycle` and `phase`. Nothing is owed (the controlled world)."""
        w = controlled_world()
        w.pop["cycles"][0], w.pop["phases"][0] = cycle, phase
        w.pop["wage_to"][3], w.pop["pay_days"][3], w.pop["pay_phase"][3] = 0, pay_days, pay_phase
        w.last["wages_paid"][:], w.last["receipts"][:] = 0.0, 0.0
        w.last["wages_paid"][3] = w.last["receipts"][0] = wage / MONTH_USD
        return w

    def test_a_bridge_falls_due_on_the_wage_pay_date(self):
        """The covering budget expects a wage on its job's pay dates, so a bridge falls due when the wage arrives.

        Example ($): a person on the daily billing cycle whose only receipt is a monthly wage of $3,755 on day 25. A
        $300 bridge drawn on day 10 falls due on day 25; spreading the wage over the billing dates, $125.17 a day,
        would put it on day 13, before the wage arrives. The receipts expected in the two-month horizon are two
        monthly wages, the same as sixty days of $125.17."""
        w = self.wage_only_world(cycle=1, phase=0, pay_days=30, pay_phase=25)
        draw = np.array([300.0 / MONTH_USD])
        self.assertEqual(w._due_c1(np.array([0]), draw, 10).tolist(), [25])
        self.assertEqual(w._due_c1(np.array([0]), draw, 10, rate=np.array([0.02])).tolist(), [25])  # outside lender too
        expected, spare, owed, last = w._c1_budget(10)
        self.assertAlmostEqual(float(expected[0]) * MONTH_USD, 2 * 3755.0, places=6)
        self.assertEqual((float(owed[0]), int(last[0])), (0.0, 70))    # the last own billing date in the horizon

    def test_a_bridge_falls_due_on_the_first_weekly_pay_date_that_covers_it(self):
        """A bridge falls due on the first pay date whose cumulative wage covers it, not on the next billing date.

        Example ($): a person on the monthly billing cycle (next billing date day 39) paid $3,755 a month weekly,
        $876.17 a week on days 16, 23 and 30. A $2,000 bridge drawn on day 10 falls due on day 30, the first pay date
        whose cumulative wage, $2,628.50, covers it ($1,752.33 on day 23 does not), and a $500 bridge on day 16."""
        w = self.wage_only_world(cycle=30, phase=9, pay_days=7, pay_phase=2)
        due = lambda dollars, rate=None: w._due_c1(np.array([0]), np.array([dollars / MONTH_USD]), 10, rate).tolist()
        self.assertEqual((due(2000.0), due(500.0)), ([30], [16]))
        # Weekly pay dates do not divide the horizon: days 16 to 65 hold eight of them, $7,009.33, against two months.
        self.assertAlmostEqual(float(w._c1_budget(10)[0][0]) * MONTH_USD, 8 * 3755.0 * 7 / 30, places=6)

    def test_an_outside_loan_beyond_the_horizon_falls_due_on_the_schedule_repeated(self):
        """An outside loan larger than two months of receipts is due on its own covering date however late, on the same
        schedule repeated: the date matches a day-by-day count of weekly wages and monthly other receipts against the
        loan with its simple interest."""
        w = self.wage_only_world(cycle=30, phase=9, pay_days=7, pay_phase=2)
        w.last["receipts"][0] += 1000.0 / MONTH_USD   # $1,000 a month of other receipts on own billing dates
        amount, rate, t = 30000.0 / MONTH_USD, 0.02, 10
        days = np.arange(t + 1, t + 5000)
        weekly, monthly = (days - 2) % 7 == 0, (days - 9) % 30 == 0
        cum = np.cumsum(weekly * 3755.0 * 7 / 30 + monthly * 1000.0) / MONTH_USD
        covered = (weekly | monthly) & (cum >= amount * (1 + rate * (days - t) / DAYS) - 1e-9)
        self.assertEqual(w._due_c1(np.array([0]), np.array([amount]), t, np.array([rate])).tolist(),
                         [int(days[covered.argmax()])])
        self.assertGreater(int(days[covered.argmax()]), t + 60)

    def test_wage_dated_budget_keeps_the_accounting_identity_in_every_arm(self):
        """With bridges dated by the wage-dated budget and shocks on, the conservation identity holds every month in
        every arm, and each job's recorded wages are part of its recipient's receipts."""
        economy = replace(TINY, n=60, burn_in=2, months=4, shocks=True)
        for arm in ("S0", "M0", "M1", "M2", "U"):
            w = _World(Inputs(), 0.6, economy, arm)
            series = w.run()["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            incoming = np.bincount(w.pop["wage_to"], weights=w.last["wages_paid"], minlength=w.n)
            self.assertGreater(float(incoming.sum()), 0.0)
            self.assertTrue(np.all(incoming <= w.last["receipts"] + 1e-12))

    def test_same_day_requests_share_the_debt_limit(self):
        """Term requests on the same day share the debt-service limit, in arrival order.

        Example (spending $6,440 a month, debt service $1,800): a vehicle loan adding $450 and a personal loan adding
        $700 a month pass the 43% limit alone but reach 46% together; the vehicle loan goes ahead and the personal
        purchase is cancelled."""
        def bought(products):
            w = controlled_world()
            w.spending[0] = 1.0
            w._add_loans(np.array([0]), False, TERM, np.array([1800.0 / 6440.0 * 12]), 0.0, 0.0, BIG, np.array([12]), 0)
            add = np.array([450.0, 700.0])[products] / 6440.0
            months = np.full(add.size, 12)
            w.req = dict(buyer=np.zeros(add.size, int), seller=np.ones(add.size, int), price=add * months,
                         settle=np.full(add.size, 30), product=np.array(products), rate=np.zeros(add.size),
                         months=months)
            w._term_purchases(30)
            return w.durable["value"][w.durable["owner"] == 0] / 12 * 6440.0
        np.testing.assert_allclose(bought([0, 1]), [450.0])
        np.testing.assert_allclose(bought([1]), [700.0])           # the personal loan alone passes

    # ---- The minimum S0 counterfactual ----------------------------------------------------------------------------
    def test_illiquid_wealth_sets_spending_but_never_pays_a_bill(self):
        """Illiquid wealth sets a person's spending but never pays a bill.

        Example: a person with $64,400 of illiquid wealth and no money cannot pay a $100 bill, which fails with the
        flat $27 fee as fee debt, yet at the close it spends the most in the economy."""
        w = controlled_world("S0")
        w.pop["illiquid"][:] = 0.0
        w.pop["illiquid"][0] = 10.0
        one_invoice(w, 100 / MONTH_USD, card=False)
        w._settle(1, 30)
        self.assertEqual(float(w.cash[1]), 0.0)
        np.testing.assert_allclose(w.book["principal"][w.book["kind"] == FEE_DEBT], [FAIL_FEE], rtol=1e-12)
        w._close(0, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertEqual(float(w.pop["illiquid"][0]), 10.0)
        self.assertEqual(int(np.argmax(w.spending)), 0)
        self.assertGreater(float(w.spending[0]), 7.0)              # 10 units against a floor of 0.02 for the rest

    def test_savings_pay_a_bill_the_same_day(self):
        """Savings pay a bill on the day it falls due.

        Example: $3,000 saved and no spare cash meet a $500 bill on day 10. The seller is paid, nothing is borrowed or
        fails, and the day's cash flow shows the $500 payment, not the transfer. The draw gives up the month's
        interest on $500, as savings earn on the month-end balance."""
        w = controlled_world("S0")
        w.savings[0] = 3000 / MONTH_USD
        one_invoice(w, 500 / MONTH_USD, at=DAYS + 10, card=False)
        w.day(1, 10)
        self.assertAlmostEqual(float(w.savings[0]), 2500 / MONTH_USD, places=15)
        self.assertAlmostEqual(float(w.cash[1]), 500 / MONTH_USD * (1 + w.inputs.buffer_yield / DAYS), places=15)
        self.assertEqual(float(w.cash[0]), 0.0)
        self.assertEqual(int(w.book["borrower"].size), 0)
        self.assertAlmostEqual(float(w.acc["flows"][0, 10]), -500 / MONTH_USD, places=15)
        w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertAlmostEqual(float(w.savings[0]), 2500 / MONTH_USD * (1 + w.saving_rate[0]), places=15)

    def test_savings_pay_the_statement_and_an_instalment_before_revolving_or_arrears(self):
        """Same-day savings pay what cash cannot: a $1,000 statement with $300 of cash is paid in full and nothing
        revolves; an instalment falling due with no cash is paid and nothing is overdue."""
        w = controlled_world("S0")
        w.holder[0], w.cash[0], w.savings[0] = True, 300 / MONTH_USD, 2000 / MONTH_USD
        w.card_statement[0] = 1000 / MONTH_USD
        w._statement(20, DAYS + 20)
        self.assertEqual(int(w.book["borrower"].size), 0)
        self.assertAlmostEqual(float(w.savings[0]), 1300 / MONTH_USD, places=15)
        self.assertAlmostEqual(float(w.cash[0]), 0.0, places=15)
        w.savings[1] = 1.0
        w.pop["cycles"][1], w.pop["phases"][1] = 30, 0
        w._add_loans(np.array([1]), False, TERM, np.array([1.2]), 0.01, 0.01, BIG, np.array([12]), 0)
        w._instalments(DAYS)
        self.assertAlmostEqual(float(w.book["principal"][0]), 1.1, places=12)
        self.assertAlmostEqual(float(w.savings[1]), 0.9, places=12)
        self.assertLess(float(w._overdue(np.array([0]))[0]), EPS)

    def test_buffer_replay_draws_savings_before_credit_or_failure(self):
        """The buffer replay draws savings before credit or failure.

        Example: half a unit spent on day 10 and received back on day 20, from no buffer. Savings above the buffer
        pay it for the month's interest on what was drawn; a shortfall beyond them needs credit or fails. A second dip
        after the receipts is paid from them, since the first draw stays out of savings until dealing."""
        flows = np.zeros((1, DAYS))
        flows[0, 10], flows[0, 20] = -0.5, 0.5
        one = lambda x: np.full(1, x)
        cost = lambda reserve: float(replay_cost(flows, np.zeros((1, 1)), one(0.02), one(0.0), one(0.3),
                                                 reserve=np.full((1, 1), reserve), draw_rate=one(0.003))[0, 0])
        self.assertAlmostEqual(cost(1.0), 0.003 * 0.5, places=15)
        self.assertAlmostEqual(cost(0.2), 0.003 * 0.2 + 0.02 * 0.3 * 10 / DAYS + 0.3 * 0.3, places=15)
        flows[0, 22], flows[0, 25] = -0.3, 0.3
        self.assertAlmostEqual(cost(1.0), 0.003 * 0.5, places=15)

    def test_same_day_savings_let_a_buffer_stop_short_of_the_dip(self):
        """Same-day savings let a buffer stop short of the dip.

        Example: a dip of 0.3 months from day 10 to day 20 without a card. Without same-day savings the person
        keeps half a month (a quarter would leave 0.05 to fail); with them a quarter month, drawing the rest. Money it
        will offer to the pool cannot be drawn, so a person investing in the pool keeps half a month."""
        flows = np.zeros((1, DAYS))
        flows[0, 10], flows[0, 20] = -0.3, 0.3
        one = lambda x: np.full(1, x)
        pick = lambda **saving: float(choose_buffer(flows, one(1.0), one(3.0), one(0.0), one(0.0029), one(0.3),
                                                    **saving)[0][0])
        self.assertEqual(pick(), 0.5)
        self.assertEqual(pick(draw_rate=one(0.003)), 0.25)
        self.assertEqual(pick(draw_rate=one(0.003), drawable=one(0.0)), 0.5)

    def test_the_failure_fee_falls_on_bills_and_wages_at_most_once_a_day(self):
        """The failure fee falls on bills and wages at most once a day.

        Example: without a card or savings, $60 against one $100 bill pays 60% of it, so 0.4 of a payment fails and
        the fee is $10.80, booked as fee debt. Against bills of $50 and $100 it pays 40% of each: 1.2 payments fail,
        capped at one fee, $27. A failed card-eligible purchase is declined without a fee and its unpaid part is
        lost. The month's average payment, $75, prices the fee at 36% a unit in next month's buffer choice, and the
        month's record holds the $27 fee and the $90 that failed."""
        def settle(amounts, card=False):
            w = controlled_world("S0")
            w.cash[0] = 60 / MONTH_USD
            for key in ("due_n", "due_amt", "fee", "failed_new"):
                w.acc[key][:] = 0.0
            k = len(amounts)
            w.ob = dict(buyer=np.zeros(k, int), seller=np.arange(1, k + 1), amount=np.array(amounts) / MONTH_USD,
                        settle=np.full(k, 30), card=np.full(k, card), kind=np.full(k, SERVICE))
            w.receivable[1:k + 1] = w.ob["amount"]
            w.payable[0] = w.ob["amount"].sum()
            w._settle(1, 30)
            return w, float(w.book["principal"][w.book["kind"] == FEE_DEBT].sum()) * MONTH_USD
        _, fee = settle([100.0])
        self.assertAlmostEqual(fee, 0.4 * 27.0, places=10)
        w, fee = settle([50.0, 100.0])
        np.testing.assert_allclose(w.cash[1:3], np.array([20.0, 40.0]) / MONTH_USD, rtol=1e-12)
        self.assertAlmostEqual(fee, 27.0, places=10)
        self.assertAlmostEqual(-w.external * MONTH_USD, 27.0, places=10)
        w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertAlmostEqual(float(w._fail_rate()[0]), 27.0 / 75.0, places=12)
        self.assertAlmostEqual(float(w.fee_path[1][0]) * MONTH_USD, 27.0, places=10)
        self.assertAlmostEqual(float(w.failed_path[1][0]) * MONTH_USD, 90.0, places=10)
        w, fee = settle([100.0], card=True)
        self.assertEqual(fee, 0.0)
        self.assertAlmostEqual(float(w.cash[1]), 60 / MONTH_USD, places=15)

    def test_pool_limit_counts_a_fee_capped_at_one_a_day(self):
        """The pool's lending limit counts a fee capped at one a day.

        Example ($): a payer without a card owes three $100 bills with nothing to pay them. Whatever the pool does
        not lend fails, and its fee is capped at one. With $250 of receipts in two months the pool lends until those
        receipts exactly repay the loan and a fee below the cap; with $200, until they repay the loan and one full fee.
        The limit function: the cap lets the pool lend more than an uncapped fee would; a fee debt the receipts
        cannot cover stops all lending; a $20 bill, whose fee costs more than the loan, is lent in full or not at
        all. Under the monthly cap of two fees the limit counts the capped fee exactly: with 1.5 fees already
        charged this month, the day's cap is half a fee, so with $200 of receipts the pool lends until they repay
        the loan and $13.50."""
        def lend(receipts, units=0.0):
            w = controlled_world()
            funded_pool(w)
            w.acc["fee_units"][0] = units
            w.r_g = w.r_b = 0.005
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:] = receipts / MONTH_USD
            # The budget expects wages on their jobs' pay dates; the quiet month's wages would add receipts to the
            # example, whose receipts are none of them wages.
            w.last["wages_paid"][:] = 0.0
            w.ob = dict(buyer=np.zeros(3, int), seller=np.arange(1, 4), amount=np.full(3, 100.0 / MONTH_USD),
                        settle=np.full(3, 30), card=np.zeros(3, bool), kind=np.full(3, SERVICE))
            w.receivable[1:4] = w.ob["amount"]
            w.payable[0] = w.ob["amount"].sum()
            _, spare, _, last = w._c1_budget(30)
            factor, grow = w._pool_factor(30, last[0]), 1.0   # fee debt bears no interest
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS))
            w._settle(1, 30)
            draw = float(w.book["principal"][w.book["pool"]].sum())
            fee = float(w.book["principal"][w.book["kind"] == FEE_DEBT].sum())
            self.assertAlmostEqual(draw * factor + fee * grow, float(spare[0]), places=14)
            # Failure counts: each bill is failed or bridged in shares, and in whole bills the draw pays the ones it
            # covers in full, smallest first.
            counts = {key: float(w.acc[key][0]) for key in FAILURE_COUNTS}
            self.assertAlmostEqual(counts["fail_shares"] + counts["bridged_shares"], 3.0, places=12)
            self.assertEqual(counts["fail_items"] + counts["bridged_items"], 3.0)
            self.assertEqual(counts["bridged_items"], np.floor(draw * MONTH_USD / 100))
            return draw, fee
        draw, fee = lend(125.0)
        self.assertTrue(0.0 < fee < FAIL_FEE and draw > 0.0)
        draw, fee = lend(100.0)
        self.assertAlmostEqual(fee, FAIL_FEE, places=15)
        capped, fee = lend(100.0, units=1.5)
        self.assertAlmostEqual(fee * MONTH_USD, 13.5, places=10)
        self.assertGreater(capped, draw)
        one = lambda x: np.full(1, x)
        limit = lambda spare, unit, cap, short=300.0: float(limit_with_fee(one(short), one(spare), one(1.01),
                                                                           one(unit), one(cap))[0])
        self.assertAlmostEqual(limit(250.0, 0.28, 28.0), (250.0 - 84.0) / 0.73, places=10)
        self.assertAlmostEqual(limit(200.0, 0.28, 28.0), (200.0 - 28.0) / 1.01, places=10)
        self.assertAlmostEqual(limit(200.0, 0.28, np.inf), (200.0 - 84.0) / 0.73, places=10)
        self.assertEqual(limit(20.0, 0.28, 28.0), 0.0)
        self.assertEqual(limit(40.0, 1.4, 28.0, short=20.0), 20.0)
        self.assertEqual(limit(24.0, 1.4, 28.0, short=20.0), 0.0)

    def test_buffer_replay_caps_the_failure_cost_at_one_fee_a_day(self):
        """In the replay a day's failures cost at most the cap: half a unit failing on day 10 costs 0.15 at 0.3 a unit,
        or the cap of 0.05; a tenth failing on day 20 adds 0.03, below that day's cap."""
        flows = np.zeros((1, DAYS))
        flows[0, 10] = -0.5
        one = lambda x: np.full(1, x)
        cost = lambda cap: float(replay_cost(flows, np.zeros((1, 1)), one(0.0), one(0.0), one(0.3),
                                             fail_cap=cap)[0, 0])
        self.assertAlmostEqual(cost(None), 0.15, places=15)
        self.assertAlmostEqual(cost(0.05), 0.05, places=15)
        flows[0, 20] = -0.1
        self.assertAlmostEqual(cost(0.05), 0.05 + 0.03, places=15)

    def test_a_failed_wage_pays_the_fee_once(self):
        """A wage its payer cannot pay carries the $27 fee; re-queued to its job's next pay date, it fails again
        without a second fee, and the record of new failed payments counts it once."""
        w = controlled_world("S0")
        w.acc["failed_new"][:] = 0.0
        w.ob = dict(buyer=np.array([3]), seller=np.array([4]), amount=np.array([0.5]), settle=np.array([30]),
                    card=np.array([False]), kind=np.array([WAGE]))
        w.receivable[4] = w.payable[3] = 0.5
        w._settle(1, 30)
        later = int(w.ob["settle"][w.ob["kind"] == LATE_WAGE][0])
        w._settle(later // DAYS, later)
        np.testing.assert_allclose(w.book["principal"][w.book["kind"] == FEE_DEBT], [FAIL_FEE], rtol=1e-12)
        self.assertAlmostEqual(float(w.payable[3]), 0.5, places=15)   # still owed
        self.assertAlmostEqual(float(w.acc["failed_new"][3]), 0.5, places=15)

    def test_pool_lends_a_small_bill_whose_fee_would_cost_more(self):
        """The pool lends a small bill whose failure fee would cost more than the loan.

        Example: failing a $20 bill costs $27, more than the pool's coupon on it. Without a card the pool lends the
        $20 when two months of receipts ($40) repay the fee on all of it, and otherwise ($24) nothing, however capacity
        might ration it, as for a card holder; the bill then fails with its fee. The $24 case is recorded as a
        refusal: the loan alone, $20.20 with its coupon, would have been repaid."""
        for receipts, pool_lends in ((20.0, True), (12.0, False)):
            w = controlled_world()
            funded_pool(w)
            w.r_g = w.r_b = 0.005
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:] = receipts / MONTH_USD
            # The budget expects wages on their jobs' pay dates; the quiet month's wages would add receipts to the
            # example, whose receipts are none of them wages.
            w.last["wages_paid"][:] = 0.0
            w.acc["fee_refused"] = w.acc["fee_refused_n"] = 0.0
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS))
            one_invoice(w, 20 / MONTH_USD, card=False)
            w._settle(1, 30)
            loans, fees = w.book["principal"][w.book["pool"]], w.book["principal"][w.book["kind"] == FEE_DEBT]
            np.testing.assert_allclose(loans, [20 / MONTH_USD] if pool_lends else [], rtol=1e-12)
            np.testing.assert_allclose(fees, [] if pool_lends else [FAIL_FEE], rtol=1e-12)
            self.assertAlmostEqual(w.acc["fee_refused"], 0.0 if pool_lends else 20 / MONTH_USD, places=15)
            self.assertEqual(w.acc["fee_refused_n"], 0.0 if pool_lends else 1.0)
            # Failure counts: the bill lent is one bridged in place of failing; refused, one failed.
            self.assertAlmostEqual(float(w.acc["bridged_shares"][0]), float(pool_lends), places=12)
            items = tuple(float(w.acc[key][0]) for key in ("bridged_items", "fail_items"))
            self.assertEqual(items, (1.0, 0.0) if pool_lends else (0.0, 1.0))

    # ---- The boundary rule and its real cost shares -------------------------------------------------------------
    def test_card_conversion_and_pool_costs_leave_and_card_rewards_come_back(self):
        """Card fees, conversion fees and pool costs leave the economy; card rewards come back.

        Example: on a $1 card purchase the seller keeps 98.3 cents, the 1.7-cent fee leaves, and the buyer's 0.75
        cents of rewards come in at the close. A leaver's conversion fee leaves. A pool cost of 0.1 with 0.04 of cash
        leaves in full when incurred, 0.06 owed to the provider, and paying that later moves no wealth. Outside
        lenders' interest comes back by spending only under the recirculation stress."""
        inputs = Inputs()
        w = controlled_world("S0")
        w.holder[0] = True
        one_invoice(w)
        w._settle(1, 30)
        self.assertAlmostEqual(float(w.cash[1]), 1 - inputs.f_card, places=15)
        self.assertAlmostEqual(w.external, -inputs.f_card, places=15)
        self.assertAlmostEqual(float(w._pay_rewards()[0]), CARD_REWARDS, places=15)
        self.assertAlmostEqual(float(w.cash[0]), CARD_REWARDS, places=15)
        self.assertAlmostEqual(w.external, CARD_REWARDS - inputs.f_card, places=15)
        m1 = controlled_world()
        m1.part[0], m1.pcash[0], m1.reserves = True, 100.0, 100.0
        m1._leave(np.arange(10) == 0)
        self.assertAlmostEqual(float(m1.cash[0]), 100 * (1 - CONVERSION_FEE), places=12)
        self.assertAlmostEqual(m1.external, -100 * CONVERSION_FEE, places=12)
        m1.external, m1.pool_cash = 0.0, 0.04
        m1._pool_cost(0.1)
        self.assertAlmostEqual(m1.external, -0.1, places=15)
        self.assertAlmostEqual(m1.pool_payable, 0.06, places=15)
        m1.pool_cash = 0.1
        m1._pool_cost(0.0)
        self.assertAlmostEqual(m1.external, -0.1, places=15)
        self.assertAlmostEqual(m1.pool_cash, 0.04, places=15)
        self.assertAlmostEqual(m1.pool_payable, 0.0, places=15)
        self.assertEqual(float(m1._recirculate().sum()), 0.0)
        m1.sector["lenders"], m1.spending = 0.3, np.ones(10)
        np.testing.assert_allclose(m1._recirculate(), 0.03, rtol=1e-12)
        self.assertEqual(m1.sector["lenders"], 0.0)

    def test_rewards_are_a_fixed_share_of_card_spending_in_a_run(self):
        """In a short S0 run, card fees are 1.7% of card value and rewards 0.75% every month, and each person's
        payments to outside intermediaries are recorded month by month."""
        run = simulate(Inputs(), 0.6, TINY, "S0")
        s, f_card = run["series"], Inputs().f_card
        self.assertGreater(float(s["card_value"].sum()), 0.0)
        np.testing.assert_allclose(s["merchant_fees"], s["card_value"] * f_card, rtol=1e-12)
        np.testing.assert_allclose(s["rewards"], s["card_value"] * CARD_REWARDS, rtol=1e-12)
        self.assertEqual(run["transfers"].shape, (TINY.burn_in + TINY.months, TINY.n))

    @staticmethod
    def year_of(arm, volumes, keys):
        """One person's year in an arm: each volume in the first month after launch (burn-in 1, 12 months)."""
        series = {key: np.zeros(13) for key in keys}
        for key, value in volumes.items():
            series[key][1] = value
        return dict(arm=arm, series=series)

    def test_real_part_prices_the_hand_cases_at_the_same_rates(self):
        """The real part prices the same events at the same rates in every arm.

        Example, one person over a year: a $10,000 loan uses $250 of real resources from the outside lender or the
        pool; one failed bill $2, as does the pool bridge in its place; $10,000 of card purchases in 70 payments of
        $142 cost $24.86 on the card rails (processing $4.86, fraud $11, network $9) and $0.12 in P, one transfer's
        gas on Base a payment, $0.00169 (P payments run on stablecoin rails, with no card-style processing, fraud or
        network charge), so CPM saves $24.74; $1,000 held a year costs $2.40 as E or as P. The pool's priced 2%
        ($200) is set against its sourced $252. The failed bill is one unpaid share and the bridge one bridged share,
        the unit of the real failure line."""
        from scripts.run_economy_population import real_part
        w = Economy(n=1, burn_in=1, months=12)
        keys = REAL_SERIES
        loan, payments, spend, held = 10000 / MONTH_USD * 12, 10000 / 142, 10000 / MONTH_USD, 1000 / MONTH_USD * 12
        s0 = real_part(self.year_of("S0", dict(pt_term=loan, penalties=FAIL_FEE, fail_shares=1.0,
                                               card_payments=payments, card_value=spend, money_bt=held), keys), w)
        m1 = real_part(self.year_of("M1", dict(pt_pool_term=loan, nocard_bridges=1.0, bridged_shares=1.0,
                                               p_payments=payments, p_value=spend, money_bt=held,
                                               gas=payments * GAS_PER_P_PAYMENT, pool_operating=200 / MONTH_USD),
                                    keys), w)
        self.assertEqual((s0["term_credit"], s0["failed_payments"], s0["card_rails"], s0["holding"]),
                         (250.0, 2.0, 24.86, 2.4))
        self.assertEqual((m1["term_credit"], m1["failed_payments"], m1["p_rail"], m1["holding"]),
                         (250.0, 2.0, 0.12, 2.4))
        self.assertEqual((s0["total"], m1["total"]), (279.26, 254.52))
        self.assertEqual((m1["pool_priced_usd"], m1["pool_sourced_usd"]), (200.0, 252.0))
        # Earned-wage access: the CFPB's 27 advances a user a year cost the declared $54, in the total; with no access
        # the line is zero.
        ewa = real_part(self.year_of("S0", dict(ewa_uses=27.0), keys), w)
        self.assertEqual((ewa["earned_wage"], ewa["total"]), (54.0, 54.0))
        self.assertEqual(real_part(self.year_of("S0", dict(ewa_uses=27.0), keys), legacy(w))["earned_wage"], 0.0)

    def test_transfers_split_what_households_pay_into_real_cost_and_margin(self):
        """What households pay splits into real cost and margin.

        Example, one person over a year: $900 of interest on a $10,000 outside loan is $250 of real cost and a $650
        margin; a $27 failure fee is $2 and $25; $170 of card fees less $75 of rewards on $10,000 of card purchases
        is $24.86 and $70.14; the issuer's $33 on $1,000 of P is $2.40 and $30.60. A conversion fee has no sourced
        real cost, so no margin is claimed for it. Earned-wage access: the CFPB's 27 advances and $68.88 of fees a
        user a year are $54 of real cost at the declared $2 a use and a $14.88 margin; with no access there is no
        such row. With card limits, $10 of cash-advance fees and $30 of late fees go to the outside lenders too, $940
        paid against the same $250."""
        from scripts.run_economy_population import transfers
        w = Economy(n=1, burn_in=1, months=12)
        keys = ("out_interest", "pt_card", "pt_term", "penalties", "merchant_fees", "rewards", "card_payments",
                "card_value", "conversion_fees", "pool_operating", "deposit_spread", "e_bt", "savings_bt", "issuer",
                "P_out", "issuer_spread", "p_bt", "gas", "ewa_fees", "ewa_uses", "advance_fees", "late_fees")
        usd = lambda dollars: dollars / MONTH_USD
        s0 = transfers(self.year_of("S0", dict(out_interest=usd(900), pt_term=usd(10000) * 12, penalties=FAIL_FEE,
                                               merchant_fees=usd(170), rewards=usd(75), card_payments=10000 / 142,
                                               card_value=usd(10000), conversion_fees=usd(1)), keys), w)
        self.assertEqual(s0["outside_lenders"], dict(paid_usd=900.0, real_usd=250.0, margin_usd=650.0))
        fees = transfers(self.year_of("S0", dict(out_interest=usd(900), pt_term=usd(10000) * 12,
                                                 advance_fees=usd(10), late_fees=usd(30)), keys), w)
        self.assertEqual(fees["outside_lenders"], dict(paid_usd=940.0, real_usd=250.0, margin_usd=690.0))
        self.assertEqual(s0["failure_fees"], dict(paid_usd=27.0, real_usd=2.0, margin_usd=25.0))
        self.assertEqual(s0["card_rails"], dict(paid_usd=95.0, real_usd=24.86, margin_usd=70.14))
        self.assertEqual(s0["conversion"], dict(paid_usd=1.0, real_usd=None, margin_usd=None))
        self.assertEqual(s0["total"], dict(paid_usd=1023.0, real_usd=276.86, margin_usd=745.14))
        self.assertNotIn("issuer", s0)
        m1 = transfers(self.year_of("M1", dict(issuer=usd(33), P_out=usd(1000) * 12), keys), w)
        self.assertEqual(m1["issuer"], dict(paid_usd=33.0, real_usd=2.4, margin_usd=30.6))
        self.assertEqual(s0["earned_wage"], dict(paid_usd=0.0, real_usd=0.0, margin_usd=0.0))
        ewa = transfers(self.year_of("S0", dict(ewa_fees=usd(68.88), ewa_uses=27.0), keys), w)
        self.assertEqual(ewa["earned_wage"], dict(paid_usd=68.88, real_usd=54.0, margin_usd=14.88))
        self.assertEqual(ewa["total"], dict(paid_usd=68.88, real_usd=54.0, margin_usd=14.88))
        self.assertNotIn("earned_wage", transfers(self.year_of("S0", dict(ewa_fees=usd(68.88)), keys), legacy(w)))

    def test_cash_check_reads_money_at_launch_at_the_end_and_at_its_lowest(self):
        """Households' money is read at the close before launch, at the end and at its lowest after launch, for
        everyone and for the half holding least."""
        from scripts.run_economy_population import cash_check
        liquid = np.array([1.0, 0.9, 0.8, 0.5, 0.7, 0.6]) * 1000 / MONTH_USD
        cash = cash_check(dict(series=dict(liquid=liquid, liquid_low=liquid / 2)), Economy(n=1, burn_in=2, months=4))
        self.assertEqual(cash["everyone"], dict(launch_usd=900.0, end_usd=600.0, lowest_usd=500.0))
        self.assertEqual(cash["poorer_half"], dict(launch_usd=450.0, end_usd=300.0, lowest_usd=250.0))

    def test_each_job_keeps_its_paired_differences_a_year(self):
        """Each job keeps its paired differences a year.

        Example: ten people over two years after launch. S0 has two failed payments ($4 of real
        resources), M0 one ($2) and M1 none, so M1 saves $2 a year against S0 and $1 against M0. M1 ends $200 above S0
        for each person on a short billing cycle and $100 below for each on a long one, and M0 ends $40 above S0 for
        everyone: against S0, M1 gains $100 and -$50 a year by cycle and $25 in every quintile and on average, with
        half worse off; against M0, $80 and -$70, and $5 on average. Nobody holds a card or business income, so the
        first class holds everyone; two years hold no W2, so every role but never participant is empty. People 0 and 2,
        on short cycles, are flagged as payers in chronic deficit: against S0 they gain $100 a year and the
        others $6.25."""
        from scripts.run_economy_population import REAL_LINES, differences
        w = Economy(n=10, burn_in=1, months=24)
        launch, cycles = np.arange(10) / MONTH_USD, np.tile([7, 30], 5)
        wealth = lambda end_gain: np.vstack([np.tile(launch, (w.burn_in + w.months, 1)), launch + end_gain / MONTH_USD])
        run = lambda arm, failed, end_gain: dict(self.paired_run(arm, w, cycles, np.zeros(10, bool), np.zeros(10, bool),
                                                                 dict(penalties=failed * FAIL_FEE, fail_shares=failed),
                                                                 chronic=np.isin(np.arange(10), (0, 2))),
                                                 wealth=wealth(end_gain))
        s0, m0, m1 = run("S0", 2, 0.0), run("M0", 1, 40.0), run("M1", 0, np.where(cycles > 15, -100.0, 200.0))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)                    # a W2 role read on no months
            to_s0, to_m0 = differences(m1, s0, w), differences(m1, m0, w)
        self.assertEqual(to_s0["real_saving_usd_a_year"],
                         dict(dict.fromkeys(REAL_LINES, 0.0), failed_payments=2.0, total=2.0))
        self.assertEqual(to_m0["real_saving_usd_a_year"]["total"], 1.0)
        self.assertEqual((to_s0["gain_usd_a_year"], to_s0["worse_off"]), (25.0, 0.5))
        self.assertEqual(to_s0["gain_usd_a_year_by_group"], [100.0, -50.0] * 5)
        self.assertEqual(to_s0["gain_usd_a_year_by_quintile"], [25.0] * 5)
        self.assertEqual(to_s0["gain_usd_a_year_by_cycle"], [100.0, -50.0])
        self.assertEqual((to_m0["gain_usd_a_year"], to_m0["gain_usd_a_year_by_cycle"]), (5.0, [80.0, -70.0]))
        np.testing.assert_array_equal(to_s0["gain_usd_a_year_by_class"], [25.0, np.nan, np.nan, np.nan])
        np.testing.assert_array_equal(list(to_s0["gain_usd_a_year_by_role"].values()), [np.nan, np.nan, np.nan, 25.0])
        self.assertEqual(to_s0["gain_usd_a_year_by_chronic"], [6.25, 100.0])
        # The gains are read in full (M2's indexation is the holder's own yield), with no line netting issuer
        # transfers out. Beside the wealth measure sit the complete gain, its parts and the difference in sales by
        # group.
        self.assertEqual(set(to_s0), {"real_saving_usd_a_year", "gain_usd_a_year", "worse_off",
                                      "gain_usd_a_year_by_group", "gain_usd_a_year_by_quintile",
                                      "gain_usd_a_year_by_cycle", "gain_usd_a_year_by_class",
                                      "gain_usd_a_year_by_role", "gain_usd_a_year_by_chronic", "complete_gain",
                                      "complete_gain_parts_usd_a_year", "sales_usd_a_year",
                                      *(f"sales_usd_a_year_by_{name}"
                                        for name in ("group", "quintile", "cycle", "class", "chronic")),
                                      # The cash-advance bound and the stored read-outs.
                                      "bound", "advance_saving_usd_a_year", "advance_saving_usd_a_year_by_quintile",
                                      "advance_saving_usd_a_year_by_class", "dispersion", "gain_usd_a_year_at_month"})

    @classmethod
    def paired_run(cls, arm, w, cycles, holder, business, volumes=None, roles=None, chronic=None, purchases=None,
                   credit=None):
        """One arm's run for the paired differences' examples: the real part's volumes in the first month after
        launch, the population's billing cycles, card holding and income source, person-by-month participation,
        ownership and borrowing (``roles``, nobody by default), the chronic-deficit flags (nobody by default), the
        person-by-month purchase records (none by default) and credit records (none by default)."""
        keys = REAL_SERIES
        none = np.zeros((w.burn_in + w.months, cycles.size), bool)
        flags = dict(dict.fromkeys(("participant", "owner", "borrower"), none), **(roles or {}))
        bought = {key: np.zeros((w.burn_in + w.months, cycles.size)) for key in ("completed", "durables", "lost",
                                                                                  "sales")}
        owed = {key: np.zeros((w.burn_in + w.months, cycles.size)) for key in CREDIT_RECORDS}
        return dict(cls.year_of(arm, volumes or {}, keys), population=dict(cycles=cycles, holder=holder,
                                                                           business=business),
                    economy=w, chronic=np.zeros(cycles.size, bool) if chronic is None else chronic,
                    purchases=dict(bought, **(purchases or {})), credit=dict(owed, **(credit or {})), **flags)

    def test_paired_gains_are_split_by_class_and_reported_by_role(self):
        """Paired gains are split by class and reported by role.

        Example: eight people over five years after launch, gaining -$10, $20, $30, $40, -$30,
        $0, $10 and $60 a year against S0. The class is card holding x income source, fixed at the population draw and
        labelled 2 * card holder + business income: people 0 and 4 hold no card and earn wages (-$20 a class mean), 1
        and 5 no card and business income ($10), 2 and 6 a card and wages ($20), 3 and 7 a card and business income
        ($50). By the arm's own role in W2, reported beside and overlapping: 2 and 3 own pool shares ($35), 4 is in P
        for six months of W2 and borrows in one of them (-$30), 2, 3 and 6 are in P all W2 (daily users, $26.67) and
        0, 1 and 5 never participate ($3.33); 7 took part in one month before W2 only, in no role. Arms whose card
        holding or income source differ are refused, and two arms' runs hold the same of both."""
        from scripts.run_economy_population import AGAINST_NOTE, CLASSES, differences
        w = Economy(n=8, burn_in=1, months=60)
        total, people = w.burn_in + w.months, np.arange(8)
        holder, business = np.tile([False, False, True, True], 2), np.tile([False, True], 4)
        months = lambda first, last: (np.arange(total) >= first) & (np.arange(total) <= last)
        flags = lambda who, first, last: months(first, last)[:, None] & np.isin(people, who)[None, :]
        roles = dict(participant=flags([2, 3, 6], 1, 60) | flags([4], 37, 42) | flags([7], 10, 10),
                     owner=flags([2, 3], 1, 60), borrower=flags([4], 40, 40))
        gain = np.array([-10.0, 20.0, 30.0, 40.0, -30.0, 0.0, 10.0, 60.0])
        end = lambda yearly: np.vstack([np.zeros((total, 8)), yearly * w.months / 12 / MONTH_USD])
        s0 = dict(self.paired_run("S0", w, np.full(8, 30), holder, business), wealth=end(np.zeros(8)))
        m1 = dict(self.paired_run("M1", w, np.full(8, 30), holder, business, roles=roles), wealth=end(gain))
        to_s0 = differences(m1, s0, w)
        self.assertEqual(to_s0["gain_usd_a_year_by_class"], [-20.0, 10.0, 20.0, 50.0])
        self.assertEqual(to_s0["gain_usd_a_year_by_role"],
                         dict(investor=35.0, borrower=-30.0, daily_user=26.67, never_participant=3.33))
        self.assertEqual(CLASSES[2 * 1 + 0], "card and wage income")
        self.assertIn(", ".join(CLASSES), AGAINST_NOTE)
        for key in ("holder", "business"):
            other = dict(m1, population=dict(m1["population"], **{key: ~m1["population"][key]}))
            with self.assertRaises(ValueError):
                differences(other, s0, w)
        # In a run both are drawn with the population, so every arm holds the same.
        economy = replace(TINY, n=100, months=12)
        runs = kept_run(_World, "S0", economy), kept_run(PooledWorld, "M1", economy)
        for key in ("holder", "business"):
            np.testing.assert_array_equal(runs[0]["population"][key], runs[1]["population"][key])
            self.assertEqual(runs[0]["population"][key].dtype, bool)

    # ---- The distress reading and the population map -------------------------------------------------------------
    def test_recovery_reads_a_quarter_of_the_dip_for_three_months(self):
        """Recovery is the first month the gap stays within a quarter of its peak for three months.

        Example: gaps against the same seed's run without distress over 60 months. Failures peak at 1
        point in month 36 and halve every two months: recovered in month 40, four months after the distress year.
        Participation peaks at 5 points and settles at a lasting 1-point loss: recovered in month 40, with a lasting gap
        of about 1 point. A wallet that wobbles by 0.3 after a -2 peak is within a quarter at once. A gap that stays
        never recovers, and no gap needs no recovery."""
        from scripts.run_economy_population import recovery
        w = Economy()
        months = np.arange(1, 61)
        ramp, after = np.clip((months - 24) / 12, 0.0, 1.0), months > 36   # the distress year is months 25 to 36
        r = recovery(np.where(after, 0.5 ** ((months - 36) / 2), ramp), w)
        self.assertEqual((r["gap"], r["month"], r["months_to_recover"]), (1.0, 36, 4))
        r = recovery(np.where(after, -0.01 - 0.03 * 0.5 ** (months - 36), -0.05 * ramp), w)
        self.assertEqual((r["gap"], r["month"], r["months_to_recover"]), (-0.05, 36, 4))
        self.assertAlmostEqual(r["lasting"], -0.01, places=5)
        wallet = np.where(after, 0.3 * (-1.0) ** months, np.where(months == 30, -2.0, 0.0))
        self.assertEqual(recovery(wallet, w)["months_to_recover"], 1)
        self.assertIsNone(recovery(np.where(months >= 30, -1.0, 0.0), w)["months_to_recover"])
        self.assertEqual(recovery(np.zeros(60), w)["months_to_recover"], 0)

    def test_recovery_is_looked_for_only_after_the_largest_gap(self):
        """Recovery is looked for only after the largest gap.

        Example, a wave after the distress year: the gap is 0.1 in the distress year and 0.02 for three months after
        it, then 0.5 from month 45 with its largest, 1.0, in month 50. Staying at 0.5 it has not recovered; falling
        to 0.1 from month 51 it recovers 15 months after the distress year. A gap still growing in month 60 has not
        recovered."""
        from scripts.run_economy_population import recovery
        w = Economy()
        months = np.arange(1, 61)
        year = (months >= 25) & (months <= 36)
        quiet = np.where(year, 0.1, np.where((months >= 37) & (months <= 39), 0.02, 0.0))
        wave = np.where(months == 50, 1.0, np.where(months >= 45, 0.5, quiet))
        r = recovery(wave, w)
        self.assertEqual((r["gap"], r["month"], r["months_to_recover"]), (1.0, 50, None))
        self.assertAlmostEqual(r["lasting"], 6.5 / 12, places=12)
        self.assertEqual(recovery(np.where(months > 50, 0.1, wave), w)["months_to_recover"], 15)
        r = recovery(np.where(months > 50, (months - 50) / 10, np.where(year, 0.1, 0.0)), w)
        self.assertEqual((r["month"], r["months_to_recover"]), (60, None))

    def test_wilson_interval_for_the_share_of_seeds_persistent(self):
        """14 Persistent seeds of 20 give an interval of about 48% to 86%; all or none of three seeds reach the ends."""
        from scripts.run_economy_population import wilson
        self.assertEqual(wilson(14, 20), [0.481, 0.855])
        self.assertEqual(wilson(3, 3)[1], 1.0)
        self.assertEqual(wilson(0, 3)[0], 0.0)
        self.assertIsNone(wilson(0, 0))

    def test_share_persistent_counts_only_seeds_whose_own_verdict_is_persistent(self):
        """The share persistent counts only seeds whose own verdict is persistent.

        Example: three seeds in which every persistence test holds unless noted. Seeds read A (Against: the issuer
        would leave), P (Persistent) or I (Inconclusive: P4 fails). PPP is Persistent with no falsifier, 3 of 3. APP
        is Persistent by majority and says a falsifier fired in 1 of 3 seeds: 2 of 3 Persistent. AAP is Against, 1
        of 3. API has no majority: Inconclusive, 1 of 3."""
        from scripts.run_economy_population import decide
        cases = (("PPP", "Persistent, no falsifier (", 1.0, [0.438, 1.0]),
                 ("APP", "Persistent, a falsifier in 1 of 3 seeds (", 0.667, [0.208, 0.939]),
                 ("AAP", "Against CPM (the issuer would leave)", 0.333, [0.061, 0.792]),
                 ("API", "Inconclusive", 0.333, [0.061, 0.792]))
        for letters, label, share, interval in cases:
            seeds = [map_seed(seed, letter) for seed, letter in enumerate(letters)]
            cell = decide(seeds, 0.044, 0.6, 0.0, False, Economy())["M1"]
            self.assertTrue(cell["verdict"].startswith(label), (letters, cell["verdict"]))
            self.assertEqual((cell["persistent_share"], cell["persistent_share_interval"]), (share, interval))
            self.assertEqual(cell["worse_than_M0_seeds"], 0)

    def test_share_persistent_counts_a_seed_worse_than_m0_where_the_cell_is(self):
        """The share persistent counts a seed worse than M0 where the cell is.

        Example: five seeds in which every persistence test holds. Trade worse than M0 in 4 of 5 seeds is systematic
        (80%): Against, with 1 of 5 seeds Persistent. In 3 of 5 it is not, and all 5 stay Persistent. One group
        harmed in 4 seeds and another in the fifth only: Against, and the fifth seed, harmed only in a group the cell
        does not find harmed, stays Persistent."""
        from scripts.run_economy_population import decide
        cell = lambda seeds: decide(seeds, 0.044, 0.6, 0.0, False, Economy())["M1"]
        trade = cell([map_seed(seed, worse_trade=seed < 4) for seed in range(5)])
        self.assertEqual(trade["verdict"], "Against CPM")
        self.assertEqual((trade["persistent_share"], trade["persistent_share_interval"]), (0.2, [0.036, 0.624]))
        self.assertEqual(trade["seed_verdicts"], ["Against CPM"] * 4 + ["P"])
        self.assertEqual(trade["worse_than_M0_seeds"], 4)
        below = cell([map_seed(seed, worse_trade=seed < 3) for seed in range(5)])
        self.assertTrue(below["verdict"].startswith("Persistent, no falsifier"), below["verdict"])
        self.assertEqual((below["persistent_share"], below["worse_than_M0_seeds"]), (1.0, 0))
        self.assertEqual(below["seed_verdicts"], ["P"] * 5)
        group = cell([map_seed(seed, harmed=(3,) if seed < 4 else (7,)) for seed in range(5)])
        self.assertEqual((group["verdict"], group["V3_groups_harmed"], group["persistent_share"]),
                         ("Against CPM", 1, 0.2))
        self.assertEqual(group["seed_verdicts"], ["Against CPM"] * 4 + ["P"])

    def test_paired_reading_names_a_reward_for_failure_at_80_percent_of_seeds(self):
        """Five paired seeds. The issuer's distress-year wallet is higher in four, so it is rewarded for failure (80%),
        and in three it is not. Failures rise half a point in the CPM arms and a point in S0, so every seed's dip is
        smaller than S0's."""
        from scripts.run_economy_population import paired
        w = Economy()
        year = slice(w.distress_start, w.distress_start + w.distress_length)

        def seed_job(seed, distressed, higher):
            s0, cpm, wallet = np.full(60, 0.01), np.full(60, 0.01), np.full(60, 0.01)
            if distressed:
                s0[year], cpm[year], wallet[year] = 0.02, 0.015, (0.011 if seed < higher else 0.009)
            pool = dict(failures=cpm.tolist(), participation=[0.5] * 60, pool_capital=[0.1] * 60, exits=[0.0] * 60,
                        issuer_wallet=wallet.tolist())
            return dict(seed=seed, measures=dict(S0=dict(failures=s0.tolist()),
                                                 M0=dict(failures=cpm.tolist(), participation=[0.5] * 60), M1=pool,
                                                 M2=pool))
        base = [seed_job(seed, False, 0) for seed in range(5)]
        for higher, rewarded in ((4, True), (3, False)):
            reading = paired([seed_job(seed, True, higher) for seed in range(5)], base, w)
            self.assertEqual(reading["seeds_paired"], 5)
            self.assertEqual(reading["M1"]["issuer_rewarded_for_failure"], rewarded)
            self.assertAlmostEqual(reading["S0"]["failures"]["gap"], 1.0, places=10)
            self.assertAlmostEqual(reading["M2"]["failures_against_S0"]["gap_difference"], -0.5, places=10)
            self.assertEqual(reading["M2"]["failures_against_S0"]["share_smaller"], 1.0)

    def test_population_map_covers_the_full_cross_on_fresh_seeds(self):
        """The confirmation map: 105 cells, each on the frozen n fresh seeds none of which is a development seed, plus
        the baseline with lenders' interest recirculated; with n = 14, 1,484 jobs of five runs each (S0, M0, U, M1 and
        M2), 7,420 runs, and with n = 37, 3,922 jobs, 19,610 runs (no seed simulated). The seeds are the first n of a
        block never run, from 20261401 (at most 100); the blocks 20261101 to 20261120, 20261201 to 20261220 and 20261301
        to 20261308 are retired. The count is 30, so SEEDS["confirmation"] is 20261401 to 20261430."""
        from scripts.run_economy_population import CONFIRMATION_RESERVED, SEEDS, runs_in, seeds_for, tasks_for
        self.assertEqual(SEEDS["confirmation"], tuple(range(20261401, 20261431)))
        block = set(CONFIRMATION_RESERVED)
        self.assertEqual(CONFIRMATION_RESERVED, tuple(range(20261401, 20261501)))
        self.assertFalse(block & set(range(20261101, 20261121)))
        self.assertFalse(block & set(range(20261201, 20261221)))
        self.assertEqual(SEEDS["development"], (20261021, 20261022, 20261023))
        self.assertFalse(block & set(SEEDS["development"]))
        # The sweep set shares no seed with either, so exploring sizes reads no confirmation seed.
        self.assertEqual(SEEDS["sweep"], tuple(range(20261301, 20261309)))
        self.assertFalse(set(SEEDS["sweep"]) & (block | set(SEEDS["development"])))
        for n in (14, 37):
            seeds = seeds_for("confirmation", n)
            self.assertEqual(seeds, tuple(range(20261401, 20261401 + n)))
            tasks = tasks_for(seeds, 1000)
            self.assertEqual(len({task[:4] for task in tasks if not task[5]}), 105 * n)
            self.assertEqual(sum(map(runs_in, tasks)), 5 * (105 + 1) * n)

    def test_a_run_can_select_cells_of_the_grid(self):
        """A run can select cells of the grid.

        Example: r_out 4.4% and a0 0.6 at distress 0 and 2% on the development seeds is 6 jobs and 30 runs (S0, M0,
        U, M1 and M2 in each), the recirculation set left out. By default a run selects the full grid, 1,590 runs on
        the development seeds, and a value outside the grid is refused."""
        from scripts.run_economy_population import GRID, SEEDS, options, runs_in, selected, tasks_for
        step2 = options().parse_args(["--seeds", "development", "--r_out", "0.044", "--a0", "0.6",
                                      "--distress", "0.02", "0"])
        selection = selected(step2.r_out, step2.a0, step2.distress)
        self.assertEqual(selection, dict(r_out=(0.044,), a0=(0.6,), distress=(0.0, 0.02)))
        tasks = tasks_for(SEEDS["development"], 1000, selection)
        self.assertEqual(len(tasks), 6)
        self.assertEqual(sum(map(runs_in, tasks)), 30)
        self.assertEqual({task[3] for task in tasks}, set(SEEDS["development"]))
        self.assertFalse(any(task[5] for task in tasks))
        everything = options().parse_args(["--seeds", "development"])
        self.assertEqual(selected(everything.r_out, everything.a0, everything.distress), GRID)
        full = tasks_for(SEEDS["development"], 1000, selected())
        self.assertEqual(full, tasks_for(SEEDS["development"], 1000))
        self.assertEqual(sum(map(runs_in, full)), 1590)
        with self.assertRaises(ValueError):
            selected(a0=(0.5,))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            options().parse_args(["--seeds", "development", "--a0", "0.5"])

    def test_population_map_runs_and_reads_a_distress_job(self):
        """A short economy (40 people, a three-month distress year): jobs without distress and at 2% run all five arms,
        and the cell reads each arm against its own run without distress, with the share persistent and its interval,
        fees, failures and payments to outside intermediaries by quintile. The boundary rule's reports are there (the
        real part line by line against S0, the transfers with the issuer in M2 and the stablecoin issuer in M0, the cash
        check), the failure counts, and no system gain."""
        from scripts.run_economy_population import MEASURES, REAL_LINES, WAGE_LOSS, decide
        template, jobs = MAP_ECONOMY, map_jobs()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            cell = decide(jobs, 0.044, 0.6, 0.02, False, template)
        self.assertEqual(len(jobs[1]["measures"]["M2"]["failures"]), 12)
        reading = cell["distress_reading"]
        self.assertEqual(reading["seeds_paired"], 1)
        self.assertTrue(set(MEASURES) <= set(reading["M2"]) and set(reading["S0"]) == {"failures"})
        self.assertEqual(len(cell["S0_fees_usd_a_year_by_quintile"]), 5)
        self.assertEqual(len(cell["M2"]["persistent_share_interval"]), 2)
        self.assertNotIn("system_gain_usd", cell["M2"])
        self.assertEqual(set(cell["M2"]["real_saving_against_S0_usd"]), set(REAL_LINES))
        self.assertIn("issuer", cell["M2"]["transfers"])
        self.assertIn("stablecoin_issuer", cell["M0"]["transfers"])
        self.assertEqual(set(cell["S0_cash"]), {"everyone", "poorer_half"})
        self.assertEqual(len(cell["M1"]["transfers_usd_a_year_by_quintile"]), 5)
        self.assertIn("bridges_drawn_over_wanted", cell["M2"])   # named for what it holds
        # "coverage" is demurrage's coverage of the bridging capital cost, the engine's record; the share of bridges
        # wanted that the pool drew has its own name.
        self.assertIn("coverage", cell["M2"])
        # Records: participation in years 2 and 3, the contract's limit and rates, demurrage by window,
        # liquidity in every arm and S0, the paired differences' seed means, and each pool arm's region reading.
        from scripts.run_economy_population import VERDICTS
        for arm in ("U", "M1", "M2"):
            self.assertTrue({"A_W1", "N_star", "coverage", "r_b_pct", "quote_pct", "pool_formed", "demurrage",
                             "liquidity"} <= set(jobs[0]["arms"][arm]), arm)
            self.assertIn(cell[arm]["region"]["verdict"], VERDICTS)
            self.assertEqual(set(cell[arm]["against"]), set(jobs[1]["arms"][arm]["against"]))
        self.assertIn("liquidity", cell["M0"])
        self.assertEqual(set(cell["S0_liquidity"]), set(jobs[0]["S0"]["liquidity"]))
        self.assertIsInstance(cell["M2"]["worse_than_M0_seeds"], int)
        # The issuer's room: its headroom beyond its own costs, those costs and the most cost it could bear in all,
        # in each pool arm's row and the cell, under names that say so; and the household-held months each window's
        # margin averages over, beside it.
        room = lambda unit: {f"issuer_{key}_{unit}" for key in ("headroom", "costs", "most_cost")}
        for arm in ("U", "M1", "M2"):
            row = jobs[1]["arms"][arm]
            self.assertTrue(room("usd_a_year") | room("share_of_P") <= set(row), arm)
            self.assertTrue(room("usd_a_year") | room("pct_of_P") <= set(cell[arm]), arm)
            self.assertFalse(any("most_expense" in key for key in set(row) | set(cell[arm])), arm)
            if row["issuer_headroom_usd_a_year"] is not None:
                self.assertAlmostEqual(row["issuer_most_cost_usd_a_year"],
                                       row["issuer_headroom_usd_a_year"] + row["issuer_costs_usd_a_year"], places=9)
            self.assertEqual(len(row["own_margin_held_months"]), 2)
            self.assertEqual(cell[arm]["own_margin_held_months_W2_by_seed"], [row["own_margin_held_months"][1]])
        # The failure counts: every arm's monthly series, and on a development seed by person and month.
        failures = jobs[1]["failure_counts"]
        self.assertEqual(set(failures), {"S0", "M0", "U", "M1", "M2"})
        self.assertEqual(len(failures["M2"]["monthly"]["fail_items"]), 12)
        self.assertTrue(all("payer_months" in failures[arm] for arm in failures))
        # The wage-loss path, every arm's, on the same spells.
        stored = jobs[1]["measures"]
        for arm in ("S0", "M0", "U", "M1", "M2"):
            self.assertTrue(set(WAGE_LOSS) <= set(stored[arm]))
            self.assertEqual(len(stored[arm]["wages_withheld"]), 12)
        for name in ("jobs_without_wage", "jobs_without_wage_last_day"):
            self.assertEqual(stored["S0"][name], stored["M1"][name])
        # Each seed's paired differences a year after launch: the template runs 12 months, so they match the row's
        # 60-month fields read over its 12.
        rows, s0 = jobs[0]["arms"], jobs[0]["S0"]
        people = build_population(replace(template, seed=20261021))
        size = np.bincount(2 * people["holder"] + people["business"], minlength=4)
        self.assertEqual(set(rows["M0"]["against"]), {"S0"})
        # M1 is read against U too, which shows what demurrage adds.
        self.assertEqual({arm: set(rows[arm]["against"]) for arm in ("U", "M1", "M2")},
                         dict(U={"S0", "M0"}, M1={"S0", "M0", "U"}, M2={"S0", "M0"}))
        for arm in ("U", "M1", "M2"):
            to = rows[arm]["against"]
            self.assertAlmostEqual(to["S0"]["gain_usd_a_year"], rows[arm]["mean_gain_usd"], delta=0.0051)
            self.assertAlmostEqual(to["M0"]["gain_usd_a_year"],
                                   rows[arm]["mean_gain_usd"] - rows["M0"]["mean_gain_usd"], delta=0.0051)
            self.assertAlmostEqual(to["S0"]["real_saving_usd_a_year"]["total"],
                                   s0["real_part"]["total"] - rows[arm]["real_part"]["total"], places=6)
            self.assertAlmostEqual(to["M0"]["real_saving_usd_a_year"]["total"],
                                   rows["M0"]["real_part"]["total"] - rows[arm]["real_part"]["total"], places=6)
            self.assertAlmostEqual(to["S0"]["worse_off"], 1 - rows[arm]["better_off"], delta=0.0006)
            self.assertEqual(len(to["M0"]["gain_usd_a_year_by_group"]), 10)
            # The four classes weighted by their size give the mean gain; the W2 roles beside them.
            means = np.array(to["S0"]["gain_usd_a_year_by_class"], float)
            self.assertAlmostEqual(float(np.nansum(means * size)) / 40, to["S0"]["gain_usd_a_year"], delta=0.01)
            self.assertEqual(list(to["M0"]["gain_usd_a_year_by_role"]),
                             ["investor", "borrower", "daily_user", "never_participant"])
            self.assertEqual({key: len(value) for key, value in rows[arm]["owners"]["by_loan_year"].items()},
                             dict.fromkeys(("all", "bridge", "term"), LOAN_YEARS))
        # The pool series: each arm's monthly series, owners in the pool arms, crossings in every CPM arm and the mean
        # buffers by card holding in every arm; 12 months hold no W2, so its reads are undefined. The harsh stress's
        # read-outs are stored in every arm, with mean wealth, and the pool run's read-outs in the pool arms; the
        # settlement's records in every arm.
        from scripts.run_economy_population import (BUFFERS, CONTRACT, CROSSINGS, MONTHLY, OWNERS, POOL_RUN, STRESS,
                                                    WEALTH)
        self.assertEqual(len(jobs[0]["monthly"]["M2"]["owners_capital"]), 12)
        from cpm_abm.experiment.notes import CHAINS
        self.assertEqual(set(jobs[0]["monthly"]["M0"]), set(CROSSINGS) | set(BUFFERS) | set(STRESS) | set(WEALTH)
                         | set(CHAINS))
        self.assertEqual(set(jobs[0]["monthly"]["S0"]), set(BUFFERS) | set(STRESS) | {"mean_wealth"} | set(CHAINS))
        for arm in ("U", "M1", "M2"):
            self.assertEqual(set(jobs[0]["monthly"][arm]), set(CONTRACT) | set(OWNERS) | set(CROSSINGS) | set(BUFFERS)
                             | set(STRESS) | set(POOL_RUN) | set(WEALTH) | set(CHAINS))
            self.assertEqual(len(jobs[0]["monthly"][arm]["offers_unused"]), 12)
        self.assertEqual(set(POOL_RUN), {"pool_cash", "cash_to_lend", "exit_set_aside", "offers", "offers_unused",
                                         "exit_paid", "exits_filed", "term_pool", "bridges_drawn_over_wanted",
                                         "written_off_bridge", "written_off_term"})
        self.assertFalse(set(POOL_RUN) & set(STRESS))   # stored once: written_off and P_bar are with the stress
        self.assertEqual(len(jobs[0]["monthly"]["S0"]["buffer_nocard"]), 12)
        # S0's buffers by person and month after launch on a development seed, and no other arm's.
        stored = np.array(failures["S0"]["buffers"])
        self.assertEqual(stored.shape, (12, 40))
        holder = build_population(replace(template, seed=20261021, distress=0.02))["holder"]
        for group, key in ((holder, "buffer_card"), (~holder, "buffer_nocard")):
            np.testing.assert_allclose(stored[:, group].mean(axis=1), jobs[1]["monthly"]["S0"][key], atol=1e-6)
        self.assertFalse(any("buffers" in failures[arm] for arm in ("M0", "U", "M1", "M2")))
        self.assertEqual({arm: set(series) for arm, series in jobs[0]["monthly"].items()},
                         {arm: set(keys) for arm, keys in MONTHLY.items()})
        self.assertEqual(set(cell["M1"]["crossings"]), {"routine", "conversions"})
        self.assertIn("crossings", cell["M0"])
        self.assertIn("W2", cell["M2"]["owners"]["net_pct"])
        self.assertIsNone(cell["M2"]["owners"]["net_pct"]["W2"])
        self.assertEqual(set(cell["M2"]["owners"]["by_loan_year"]), {"all", "bridge", "term"})
        # The issuer is a pure custodian: no support fund or issuer-held share is reported.
        self.assertFalse({"support_months", "support_usd", "issuer_held_share_W2"} & set(cell["M2"]))
        json.dumps(dict(jobs=jobs, cell=cell))                     # the map's files can be written

    def test_a_selection_of_cells_writes_the_four_stores(self):
        """A selection of cells writes the four stores as a run writes them, on the two short jobs (one seed).

        The four stores read back with the record of the selection and the Economy without the fields each job sets,
        the wage-loss and monthly keys, the failure counts' labels for every stored part and key, its note and fee,
        cells.json's note on the paired differences and none of the per-job series or counts, and summary.json's notes
        on the region reading and liquidity with the readings in order."""
        from scripts.run_economy_population import (AGAINST_NOTE, FAILURE_LABELS, FAILURE_NOTE, LIQUIDITY_NOTE,
                                                    MONTHLY, MONTHLY_NOTE, REGION_NOTE, REPORT_NOTES, VERDICTS,
                                                    WAGE_LOSS, decide_cells, run_record, runs_in, selected,
                                                    write_stores)
        selection, jobs = selected((0.044,), (0.6,), (0.0, 0.02)), map_jobs()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            cells, recirculated = decide_cells(jobs, selection, MAP_ECONOMY, 40)
        self.assertEqual([(c["r_out"], c["a0"], c["distress"], c["n"]) for c in cells],
                         [(0.044, 0.6, 0.0, 40), (0.044, 0.6, 0.02, 40)])
        self.assertEqual(cells[1]["distress_reading"]["seeds_paired"], 1)
        self.assertIsNone(recirculated)                            # the recirculation set runs with the full grid only
        total = sum(runs_in((0.044, 0.6, level, 20261021, 40, False)) for level in (0.0, 0.02))
        meta = run_record(MAP_ECONOMY, "development", total, selection)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            write_stores(output, meta, jobs, cells, recirculated)
            self.assertEqual(sorted(path.name for path in output.iterdir()),
                             ["cells.json", "failure_counts.json", "measures.json", "summary.json"])
            read = lambda name: json.loads((output / name).read_text(encoding="utf-8"))
            measures, failures, kept, summary = map(read, ("measures.json", "failure_counts.json", "cells.json",
                                                           "summary.json"))
        for store in (measures, failures, kept, summary):
            self.assertEqual(store["selected"], dict(r_out=[0.044], a0=[0.6], distress=[0.0, 0.02], full_grid=False))
            self.assertEqual((store["population_runs"], store["economy"]["n"]), (10, 40))
            self.assertEqual([store["economy"][key] for key in ("seed", "distress", "lender_income_recirculated")],
                             [None] * 3)
        self.assertEqual(measures["wage_loss"], WAGE_LOSS)
        self.assertEqual(measures["monthly"], {arm: list(keys) for arm, keys in MONTHLY.items()})
        self.assertEqual(measures["monthly_note"], MONTHLY_NOTE)
        self.assertEqual((summary["region_note"], summary["verdicts"], summary["liquidity_note"]),
                         (REGION_NOTE, list(VERDICTS), LIQUIDITY_NOTE))
        self.assertEqual([(job["distress"], job["seed"]) for job in measures["jobs"]],
                         [(0.0, 20261021), (0.02, 20261021)])
        from cpm_abm.economy_abm import MEASURE_SERIES   # the recording-only measures (tests/test_measures.py)
        self.assertEqual(set(measures["jobs"][1]["series"]["S0"]),
                         {"failures", *WAGE_LOSS, *MEASURE_SERIES, "turnover", "microvelocity", "holding_velocity"})
        self.assertEqual(set(measures["jobs"][0]["monthly"]), {"S0", "M0", "U", "M1", "M2"})
        self.assertEqual((failures["labels"], failures["note"]), (FAILURE_LABELS, FAILURE_NOTE))
        self.assertEqual((failures["fail_fee_usd"], failures["monthly_caps"]), (27.0, [2, 3, 5]))
        stored = failures["jobs"][1]["failure_counts"]
        self.assertIn("buffers", stored["S0"])
        for arm, parts in stored.items():
            self.assertTrue(set(parts) <= set(FAILURE_LABELS), arm)
            for part, values in parts.items():
                if isinstance(values, dict):
                    self.assertEqual({re.sub(r"_\d+$", "_k", key) for key in values}, set(FAILURE_LABELS[part]),
                                     (arm, part))
        self.assertEqual(kept["against_note"], AGAINST_NOTE)
        # The arm rows' earned-wage and chronic-deficit reports are stored with their notes.
        self.assertEqual(kept["report_notes"], REPORT_NOTES)
        self.assertTrue(all(set(REPORT_NOTES) <= set(row) for row in kept["jobs"][0]["arms"].values()))
        self.assertTrue(set(REPORT_NOTES) <= set(kept["jobs"][0]["S0"]))
        self.assertFalse({"measures", "monthly", "failure_counts"} & set().union(*kept["jobs"]))
        self.assertEqual(set(kept["jobs"][0]["arms"]["M1"]["against"]), {"S0", "M0", "U"})
        self.assertEqual(len(summary["cells"]), 2)
        self.assertIsNone(summary["baseline_lender_interest_recirculated"])

    # ---- The region reading and its figures -----------------------------------------------------------------------
    def test_the_region_reading_reads_its_hand_cases(self):
        """The region reading classifies a cell as stable, not persistent, a group loses, issuer leaves and so on.

        Examples, on seeds whose reports are zero unless noted. Twenty Persistent seeds whose pool formed read stable
        (Wilson lower bound 0.839); three read not persistent on the persistence rule (0.438), stable on a bare
        majority. A class at -$2.00 a person a year in every seed is at the margin and stable, at -$2.01 a group
        loses; the gains are read in full (M2's indexation is the holder's own yield), so there is one basis and no
        reading "passes on issuer transfers". Claim (d) reads each group's 95% t lower bound against S0 and against
        M0: a quintile at -$3 against M0 alone loses; a class at
        $0 and -$3.5 in alternate seeds has a mean of -$1.75 but a bound of -$2.59 and loses; a group defined in one
        seed only has no bound and loses. One seed of twenty whose issuer would leave keeps the cell persistent (19 of
        20, 0.764) and reads issuer leaves. No pool formed reads no pool. M2 at r_out 2% is its declared limit. A
        group's t lower bound reads its worked value, and a group empty in every seed is no group."""
        from scipy.stats import t as student
        from scripts.run_economy_population import VERDICTS, decide
        self.assertNotIn("passes on issuer transfers", VERDICTS)
        region = lambda seeds, rate=0.044, arm="M1": decide(seeds, rate, 0.6, 0.0, False, Economy())[arm]["region"]
        many = lambda count=20, **kw: [map_seed(seed, **kw) for seed in range(count)]
        got = region(many())
        self.assertEqual((got["verdict"], got["verdict_majority"], got["in_region"]), ("stable", "stable", True))
        self.assertEqual((got["persistent_seeds"], got["persistent_interval"], got["pool_forms_share"]),
                         (20, [0.839, 1.0], 1.0))
        self.assertEqual(got["groups"]["lowest"],
                         dict(lower_95=0.0, mean=0.0, group="no card and wage income", against="S0"))
        self.assertFalse({"groups_net", "groups_gross", "held_by_issuer_money_seeds"} & set(got))
        got = region(many(3))
        self.assertEqual((got["verdict"], got["verdict_majority"], got["persistent"]),
                         ("not persistent", "stable", False))
        at = lambda value: dict(gains=dict(**{"class": [0.0, value, 0.0, 0.0]}))
        self.assertEqual(region(many(**at(-2.0)))["verdict"], "stable")
        got = region(many(**at(-2.01)))
        self.assertEqual((got["verdict"], got["groups"]["lowest"]),
                         ("a group loses", dict(lower_95=-2.01, mean=-2.01, group="no card and business income",
                                                against="S0")))
        quintile = lambda value: dict(quintile=[0.0, value, 0.0, 0.0, 0.0])
        got = region(many(m0=quintile(-3.0)))
        self.assertEqual((got["verdict"], got["groups"]["lowest"]["against"], got["groups"]["S0"]["quintile"]),
                         ("a group loses", "M0", dict(mean=[0.0] * 5, lower_95=[0.0] * 5)))
        alternate = [map_seed(seed, gains=dict(**{"class": [0.0, -3.5 * (seed % 2), 0.0, 0.0]})) for seed in range(20)]
        got = region(alternate)
        spread = student.ppf(0.975, 19) * np.std([0.0, -3.5] * 10, ddof=1) / np.sqrt(20)
        self.assertEqual(got["groups"]["S0"]["class"]["mean"][1], -1.75)
        self.assertEqual(got["groups"]["lowest"]["lower_95"], round(-1.75 - spread, 2))
        self.assertAlmostEqual(-1.75 - spread, -2.59, places=2)
        self.assertEqual(got["verdict"], "a group loses")
        single = [map_seed(seed, gains=dict(**{"class": [0.0, 0.0 if seed == 0 else float("nan"), 0.0, 0.0]}))
                  for seed in range(20)]
        got = region(single)
        self.assertEqual((got["verdict"], got["groups"]["lowest"]["lower_95"]), ("a group loses", None))
        got = region([map_seed(seed, "A" if seed == 0 else "P") for seed in range(20)])
        self.assertEqual((got["verdict"], got["persistent"], got["issuer_leaves_seeds"]), ("issuer leaves", True, 1))
        self.assertEqual(region(many(formed=False))["verdict"], "no pool")
        limit = [dict(seed, r_out=0.02) for seed in many()]
        self.assertEqual((region(limit, 0.02, "M2")["verdict"], region(limit, 0.02, "M1")["verdict"]),
                         ("declared limit", "stable"))
        # A cycle group at 0 in ten seeds and 2 in ten: mean 1, lower bound 1 - t(0.975, 19) sd / sqrt(20).
        got = region([map_seed(seed, gains=dict(cycle=[0.0, 2.0 * (seed % 2)])) for seed in range(20)])
        lower = 1 - student.ppf(0.975, 19) * np.std([0.0, 2.0] * 10, ddof=1) / np.sqrt(20)
        self.assertEqual(got["groups"]["S0"]["cycle"], dict(mean=[0.0, 1.0], lower_95=[0.0, round(lower, 2)]))
        self.assertEqual(got["verdict"], "stable")
        got = region(many(gains=dict(**{"class": [0.0, float("nan"), 0.0, 0.0]})))
        self.assertEqual((got["groups"]["S0"]["class"]["mean"][1], got["verdict"]), (None, "stable"))

    def test_the_complete_gain_reads_its_hand_cases(self):
        """The complete gain of arm A against arm B.

        Examples: (i) A $100 purchase by a person without a card
        fails in B and completes in A, nothing else differs: on wealth the buyer is -100 and the seller +100; at face
        the buyer is 0 and the seller +100; at zero both are 0. (ii) A $500 durable is bought on term credit in A and
        cancelled in B, $20 of interest paid by the end: on wealth the buyer is -520 and the seller +500; at face the
        buyer is -20 and the seller +500; at zero the buyer is -20 and the seller 0. People are buyer, then seller.
        Case (i) read through the paired differences gives the same by person, and means of 0 on wealth, +50 in
        purchases completed and in sales, and -50 in purchases lost."""
        from scripts.run_economy_population import complete_gain
        cases = (dict(wealth=[-100.0, 100.0], completed=[100.0, 0.0], durables=[0.0, 0.0], sales=[0.0, 100.0],
                      face=[0.0, 100.0], zero=[0.0, 0.0]),
                 dict(wealth=[-520.0, 500.0], completed=[0.0, 0.0], durables=[500.0, 0.0], sales=[0.0, 500.0],
                      face=[-20.0, 500.0], zero=[-20.0, 0.0]))
        for case in cases:
            face, zero = complete_gain(*(np.array(case[key]) for key in ("wealth", "completed", "durables", "sales")))
            self.assertEqual((face.tolist(), zero.tolist()), (case["face"], case["zero"]))
        # Case (i) through the paired differences over one year after launch, the buyer on a short cycle and the
        # seller on a long one: each end's gain by cycle, the parts' means and the difference in sales by cycle.
        from scripts.run_economy_population import differences
        w = Economy(n=2, burn_in=1, months=12)
        cycles, no, month = np.array([7, 30]), np.zeros(2, bool), np.zeros((13, 2))
        record = lambda person, value: np.where((np.arange(13) == 1)[:, None] & (np.arange(2) == person)[None, :],
                                                value / MONTH_USD, 0.0)
        end = lambda gain: np.vstack([month, np.array(gain) / MONTH_USD])
        b = dict(self.paired_run("S0", w, cycles, no, no, purchases=dict(lost=record(0, 100.0))), wealth=end([0, 0]))
        a = dict(self.paired_run("M1", w, cycles, no, no,
                                 purchases=dict(completed=record(0, 100.0), sales=record(1, 100.0))),
                 wealth=end([-100.0, 100.0]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)                    # a W2 role read on no months
            got = differences(a, b, w)
        self.assertEqual((got["gain_usd_a_year_by_cycle"], got["complete_gain"]["face"]["gain_usd_a_year_by_cycle"],
                          got["complete_gain"]["zero"]["gain_usd_a_year_by_cycle"], got["sales_usd_a_year_by_cycle"]),
                         ([-100.0, 100.0], [0.0, 100.0], [0.0, 0.0], [0.0, 100.0]))
        self.assertEqual(got["complete_gain_parts_usd_a_year"],
                         dict(wealth=0.0, purchases_completed=50.0, durables=0.0, sales=50.0, purchases_lost=-50.0))

    def test_purchase_records_balance_on_a_tiny_world(self):
        """The purchase records on a tiny world with shocks, in S0, M0 and M1: every month the sum over people
        of purchases completed and durables bought equals the sum of sales, since each completed purchase is one
        buyer's and one seller's; and each person's service and shock purchases completed and lost add up to those due
        to it as buyer that month."""

        class Due(_World):
            """Records each buyer's service and shock purchases falling due, as ``_settle`` reads them."""

            def __init__(self, *args):
                super().__init__(*args)
                self.due = np.zeros((self.total, self.n))

            def _settle(self, month, t):
                lo, hi = np.searchsorted(self.ob["settle"], [t, t + 1])
                kind = self.ob["kind"][lo:hi]
                purchase = (kind == SERVICE) | (kind == SHOCK)
                self.due[month] += np.bincount(self.ob["buyer"][lo:hi], weights=self.ob["amount"][lo:hi] * purchase,
                                               minlength=self.n)
                super()._settle(month, t)

        economy = replace(TINY, shocks=True)
        for arm in ("S0", "M0", "M1"):
            world = Due(Inputs(), 0.6, economy, arm)
            run = world.run()
            bought = run["purchases"]
            self.assertTrue((bought["sales"].sum(axis=1) > 0).all() and bought["durables"].sum() > 0)
            np.testing.assert_allclose((bought["completed"] + bought["durables"]).sum(axis=1),
                                       bought["sales"].sum(axis=1), rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(bought["completed"] + bought["lost"], world.due, rtol=1e-12, atol=1e-12)

    def test_credit_records_match_the_book_on_a_tiny_world(self):
        """The credit records on a tiny world in M1, a pool formed: every record is non-negative; each month the
        instalment principal lent by each lender, summed over people, equals what the loan book was given that month;
        the pool's bridges equal the bridges series and the card's bridging the card_bridging and revolved series;
        interest on card and other outside loans equals the out_interest series; and a payer with no new failed payment
        in a month has no late wage. In S0 the pool lends nothing and earns no interest."""

        class Booked(PooledWorld):
            """Records the instalment principal booked each month, by lender (pool, outside)."""

            def __init__(self, *args):
                super().__init__(*args)
                self.booked = np.zeros((self.total, 2))

            def _add_loans(self, borrower, pool, kind, principal, *args, **kwargs):
                if kind == TERM:
                    self.booked[self.this_month, 0 if pool else 1] += float(np.sum(principal))
                super()._add_loans(borrower, pool, kind, principal, *args, **kwargs)

        economy = replace(TINY, n=100, months=12, shocks=True)
        world = Booked(Inputs(), 0.6, economy, "M1")
        run = world.run()
        credit, series, n = run["credit"], run["series"], economy.n
        self.assertEqual(set(credit), set(CREDIT_RECORDS))
        for key, path in credit.items():
            self.assertEqual(path.shape, (world.total, n), key)
            self.assertTrue(np.all(path >= 0.0), key)
        after = slice(economy.burn_in, None)
        self.assertTrue(credit["bridge_pool"][after].sum() > 0 and credit["term_pool"][after].sum() > 0)
        np.testing.assert_allclose(credit["term_pool"].sum(axis=1), world.booked[:, 0], rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(credit["term_outside"].sum(axis=1), world.booked[:, 1], rtol=1e-12, atol=1e-9)
        np.testing.assert_allclose(credit["bridge_pool"].sum(axis=1), series["bridges"] * n, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(credit["bridge_card"].sum(axis=1), (series["card_bridging"] + series["revolved"]) * n,
                                   rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose((credit["interest_card"] + credit["interest_outside"]).sum(axis=1),
                                   series["out_interest"] * n, rtol=1e-12, atol=1e-12)
        np.testing.assert_array_equal(credit["wages_late"][run["failed"] == 0.0], 0.0)
        self.assertTrue(np.all(credit["wages_late"] <= run["failed"] + 1e-12))
        s0 = simulate(Inputs(), 0.6, economy, "S0")["credit"]
        for key in ("bridge_pool", "term_pool", "interest_pool"):
            self.assertEqual(float(np.abs(s0[key]).sum()), 0.0, key)

    def test_the_runner_reports_credit_by_class(self):
        """The runner's credit and purchases by class, in S0 and a pool arm: four entries for every record, in
        the order of the classes, and class sizes that add up to the population."""
        from scripts.run_economy_population import CLASSES, by_class
        for arm in ("S0", "M1"):
            report = by_class(simulate(Inputs(), 0.6, TINY, arm), TINY)
            self.assertEqual(sum(report["class_sizes"]), TINY.n)
            for key in CREDIT_RECORDS + ("completed", "lost", "durables", "sales"):
                self.assertEqual(len(report[key]), len(CLASSES), key)

    def test_the_region_reads_claim_d_on_the_complete_gain(self):
        """The region reads claim (d) on the complete gain.

        Example, on twenty seeds alike, so each bound is its mean. A class at $0 on wealth, +$1 at face and -$3 at
        zero fails at zero: a group loses, the face end alone passes, and the gain at share s, -3 + 4 s, reaches -$2
        at s = 0.25, the break-even share on bounds and on means against both; the wealth measure passes. A class at
        -$3 on wealth and $0 at both ends is stable at break-even 0, the wealth measure failing beside it. A class at
        -$3 at face and $0 at zero loses with no break-even share, the zero end alone passing.

        The clause asks S0 at both ends and M0 at face. The same class at $0 at both ends against S0 and at +$1 at
        face and -$3 at zero against M0 is stable, M0's break-even share 0.25 and S0's 0. At $0
        against M0 and the S0 reading above, it loses on S0's zero end. At -$3 at face and $0 at zero against M0
        alone, it loses with M0's break-even share None. With M0's class alternating seed by seed between 0 and +2 at
        face, its bound is below the mean, so the break-even share on bounds exceeds the one on means."""
        import copy
        from scripts.run_economy_population import decide

        def seeds(wealth, face, zero, m0=None):
            """Twenty seeds; ``m0`` is (face, zero) against M0, each a number or a function of the seed, the S0 ends
            against M0 too when not given."""
            value = lambda given, seed: given(seed) if callable(given) else given
            rows = []
            for seed in range(20):
                row = copy.deepcopy(map_seed(seed, gains=dict(**{"class": [0.0, wealth, 0.0, 0.0]})))
                for arm in ("M1", "M2"):
                    for other, (at_face, at_zero) in (("S0", (face, zero)), ("M0", m0 or (face, zero))):
                        ends = row["arms"][arm]["against"][other]["complete_gain"]
                        ends["face"]["gain_usd_a_year_by_class"] = [0.0, value(at_face, seed), 0.0, 0.0]
                        ends["zero"]["gain_usd_a_year_by_class"] = [0.0, value(at_zero, seed), 0.0, 0.0]
                rows.append(row)
            return decide(rows, 0.044, 0.6, 0.0, False, Economy())["M1"]["region"]

        yard = lambda got, other: tuple(got["complete_gain"]["by_yardstick"][other][key] for key in (
            "face_passes", "zero_passes", "break_even_share", "break_even_share_on_means"))
        read = lambda got: (got["verdict"], got["complete_gain"]["clause_holds"], yard(got, "S0"), yard(got, "M0"),
                            got["groups"]["at_or_above_margin"], got["groups_measure"])
        got = seeds(0.0, 1.0, -3.0)
        self.assertEqual(read(got), ("a group loses", False, (True, False, 0.25, 0.25), (True, False, 0.25, 0.25),
                                     True, "wealth"))
        self.assertEqual(got["complete_gain"]["zero"]["lowest"],
                         dict(lower_95=-3.0, mean=-3.0, group="no card and business income", against="S0"))
        self.assertFalse({"ends_passing", "break_even_share", "at_or_above_margin"} & set(got["complete_gain"]))
        self.assertEqual(read(seeds(-3.0, 0.0, 0.0)), ("stable", True, (True, True, 0.0, 0.0), (True, True, 0.0, 0.0),
                                                       False, "wealth"))
        self.assertEqual(read(seeds(0.0, -3.0, 0.0)), ("a group loses", False, (False, True, None, None),
                                                       (False, True, None, None), True, "wealth"))
        # In the region against S0 at both ends and M0 at face, not at zero.
        got = seeds(0.0, 0.0, 0.0, m0=(1.0, -3.0))
        self.assertEqual(read(got), ("stable", True, (True, True, 0.0, 0.0), (True, False, 0.25, 0.25), True,
                                     "wealth"))
        self.assertTrue(0 < got["complete_gain"]["by_yardstick"]["M0"]["break_even_share"] < 1)
        self.assertEqual((got["in_region"], got["complete_gain"]["zero"]["at_or_above_margin"]), (True, False))
        # Failing against S0 at the zero end loses, whatever M0 reads.
        self.assertEqual(read(seeds(0.0, 1.0, -3.0, m0=(0.0, 0.0))),
                         ("a group loses", False, (True, False, 0.25, 0.25), (True, True, 0.0, 0.0), True, "wealth"))
        # Failing against M0 at face loses, with no break-even share against M0.
        got = seeds(0.0, 0.0, 0.0, m0=(-3.0, 0.0))
        self.assertEqual(read(got), ("a group loses", False, (True, True, 0.0, 0.0), (False, True, None, None), True,
                                     "wealth"))
        # Bounds against means: M0 at face 0 or +2 in alternate seeds (mean 1, bound 1 - t sd / sqrt 20 = 0.520) and
        # -3 at zero. On means -3 + 4 s reaches -2 at s = 0.25; on bounds -3 + 3.520 s does at s = 0.284, 0.29 on the
        # grid.
        got = seeds(0.0, 0.0, 0.0, m0=(lambda seed: 2.0 * (seed % 2), -3.0))
        self.assertEqual((got["verdict"], yard(got, "M0")), ("stable", (True, False, 0.29, 0.25)))

    def test_owners_excess_reads_its_hand_case(self):
        """Owners' net return less their alternative, reported only: capital 1 and net income 0.004 every
        month is 4.8% a year; at a reserve rate of 0.3% a month and the owners' spread of 0.25 point the alternative is
        3.85%, so the excess is 0.95 in both windows, None where no capital is held. Across seeds 1, 2 and 3 the mean
        is 2 with a 95% t interval of 2 -/+ t(0.975, 2) / sqrt(3); one seed has no interval."""
        from scipy.stats import t as student
        from scripts.run_economy_population import owners_excess, t_interval
        w = Economy(n=1, burn_in=1, months=60)
        series = dict(owners_capital=np.ones(61), owners_income_net=np.full(61, 0.004))
        got = owners_excess(dict(series=series, rho_p=0.003, economy=w), w)
        self.assertEqual(got, dict(alternative_pct=3.85, W1=0.95, W2=0.95))
        series["owners_capital"][37:] = 0.0
        self.assertIsNone(owners_excess(dict(series=series, rho_p=0.003, economy=w), w)["W2"])
        half = student.ppf(0.975, 2) / np.sqrt(3)
        self.assertEqual(t_interval([1.0, None, 2.0, 3.0]),
                         dict(mean=2.0, lower_95=round(2 - half, 3), upper_95=round(2 + half, 3), seeds=3))
        self.assertEqual(t_interval([1.5, None]), dict(mean=1.5, lower_95=None, upper_95=None, seeds=1))

    def test_liquidity_and_demurrage_read_their_hand_cases(self):
        """Liquidity and demurrage by window on constant series, in months of mean spending a person: money
        held 0.1 ($644, buffers 0.06, idle P 0.03, the pool's idle cash 0.01); a month's pool bridges 0.01, card
        bridging 0.005, revolved statements 0.002 and earned-wage advances 0.001, $1,391.04 of shortfall covered a
        year, so 0.463 of money held per dollar of it; failures 0.003 a month, $231.84 a year, and half an unpaid
        share a month, 6 a year. The issuer's derived share is its first defined value, the monopoly bound (a
        record) its W2 mean, and the yield on wallet P, the pool cash's return, the issuer's custody and demurrage
        are flows a year. A run that ends before a window has none there."""
        from scripts.run_economy_population import demurrage, liquidity
        months = 60
        economy = Economy(n=1, burn_in=0, months=months)
        flat = lambda value: np.full(months, value)
        series = dict(precautionary=flat(0.1), buffers=flat(0.06), idle=flat(0.03), pool_idle=flat(0.01),
                      bridges=flat(0.01), card_bridging=flat(0.005), revolved=flat(0.002), comet_bridging=flat(0.0),
                      ewa_value=flat(0.001), failures=flat(0.003), fail_shares=flat(0.5),
                      s_issuer=np.r_[np.nan, flat(0.0545)[1:]], s_monopoly=np.r_[flat(np.nan)[:30], flat(0.8)[30:]],
                      **{key: flat(0.001) for key in ("wallet_yield", "float_pool", "float_issuer", "charges",
                                                      "covered", "bridge_capital_cost", "issuer_wallet")})
        got = liquidity(dict(series=series, economy=economy), economy)
        self.assertEqual(got["precautionary_usd"], [644.0, 644.0])
        self.assertEqual((got["buffers_usd"], got["idle_p_usd"], got["pool_idle_usd"]),
                         ([386.4, 386.4], [193.2, 193.2], [64.4, 64.4]))
        self.assertEqual(got["shortfall_covered_usd_a_year"], [1391.04, 1391.04])
        self.assertEqual((got["pool_bridges_usd_a_year"], got["revolved_usd_a_year"]),
                         ([772.8, 772.8], [154.56, 154.56]))
        self.assertAlmostEqual(got["precautionary_per_dollar_covered"][1], round(644 / 1391.04, 4), places=12)
        self.assertEqual((got["failed_usd_a_year"], got["failed_shares_a_year"]), ([231.84, 231.84], [6.0, 6.0]))
        got = demurrage(dict(series=series, economy=economy), economy)
        self.assertEqual((got["s_issuer"], got["charges_usd_a_year"], got["wallet_yield_usd_a_year"]),
                         (0.0545, [77.28, 77.28], [77.28, 77.28]))
        self.assertEqual(got["s_monopoly_W2"], 0.8)                  # the monopoly bound, a record
        short = replace(economy, months=12)
        cut = {key: value[:12] for key, value in series.items()}
        self.assertEqual(liquidity(dict(series=cut, economy=short), short)["precautionary_usd"], [None, None])

    def test_the_region_figures_draw_from_a_tiny_store(self):
        """The region figures from a tiny synthetic store: every figure as PNG and PDF, the bare-majority
        region figures under their own names beside, a figure already there never overwritten, and a store without
        U, without monthly paths or without distress skipping what it cannot support with a printed note."""
        from scripts.run_region_figures import draw
        names = ["region_3d", "region_slice_distress_0", "region_slice_distress_2", "paths_baseline",
                 "paths_distress", "demurrage_effect", "bridging_vs_card", "liquidity_vs_s0"]
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder)
            synthetic_store(store)
            self.assertEqual(draw(store), names)
            self.assertEqual(draw(store, majority=True),
                             ["region_3d_majority", "region_slice_distress_0_majority",
                              "region_slice_distress_2_majority"])
            for name in names:
                for suffix in (".png", ".pdf"):
                    self.assertGreater((store / f"{name}{suffix}").stat().st_size, 1000, name + suffix)
            with self.assertRaises(FileExistsError):
                draw(store)
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder)
            synthetic_store(store, arms=("M1", "M2"), levels=(0.0,))
            (store / "measures.json").unlink()
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                drawn = draw(store)
            self.assertEqual(drawn, ["region_3d", "region_slice_distress_0", "bridging_vs_card", "liquidity_vs_s0"])
            for skipped in ("paths_baseline skipped", "paths_distress skipped", "demurrage_effect skipped"):
                self.assertIn(skipped, printed.getvalue())

    def test_receipts_repay_the_coupon_and_debts_ranked_ahead(self):
        """A loan the receipts cannot repay with its coupon goes to the card; one they can is repaid by its date.

        With card limits a holder's bill goes to the card as a cash advance, priced here at the card's 1% a month
        with no fee; at the cash APR and its fee the card's cost would decide the case instead of the coupon."""
        for receipts, pool_lends in ((1.0, False), (1.05, True)):
            w = controlled_world("M2")
            w.economy = replace(w.economy, inflation=0.02 / 12)
            w.index = w.economy.inflation
            funded_pool(w)
            w.holder[:2], w.card_apr[:2], w.r_g = True, 0.01, 0.005
            w.cash_apr[:2], w.advance_floor, w.advance_rate = 0.01, 0.0, 0.0
            w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
            w.pcash[0] = w.pcash[1] = 0.004
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:] = receipts
            one_invoice(w, 2.0, card=False)
            w._settle(1, 30)
            self.assertEqual(bool(w.book["pool"].any()), pool_lends)
            due = int(w.book["due"][w.book["pool"]].max()) if pool_lends else 0
            list(map(lambda day: self._receive_and_repay(w, day, receipts), (60, 90)))
            if pool_lends:
                self.assertLessEqual(float((w.book["principal"] + w.book["interest"])[w.book["pool"]].sum()), 1e-12)
                self.assertLessEqual(due, 90)
            w._arrears(91)
            self.assertFalse(bool(w.arrears[0]))

    def _receive_and_repay(self, w, day, amount):
        """Thirty days of accrual, a CPI mark, then one P receipt to person 0 settled and used to repay."""
        list(map(lambda _: w._accrue(), range(30)))
        w._deflate()
        w.ob = dict(buyer=np.array([1]), seller=np.array([0]), amount=np.array([amount]), settle=np.array([day]),
                    card=np.array([True]), kind=np.array([SERVICE]))
        w.payable[1] += amount
        w.receivable[0] += amount
        w.pcash[1] += amount
        w._settle(day // DAYS, day)
        w._repay(np.maximum(w.cash + w.pcash, 0.0))

    def test_revolving_debt_ranks_ahead_of_the_pool(self):
        """Revolving card debt is repaid first, so it uses up the receipts the pool would otherwise lend against."""
        w = controlled_world()
        funded_pool(w)
        w.holder[0], w.card_apr[0], w.r_g = True, 0.02, 0.005
        w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
        w.last["receipts"][:] = 1.0
        w._add_loans(np.array([0]), False, REVOLVE, np.array([5.0]), 0.02, 0.02, 10 ** 9)
        one_invoice(w, 0.5, card=False)
        w._settle(1, 30)
        self.assertFalse(bool(w.book["pool"].any()))

    def _due_bridge_day(self, arm, money, due_in=0, late_wage=0.0):
        """One quiet day (month 1, day 5) for person 0 with a buffer of 500, ``money`` of its own and a 300 bridge
        due ``due_in`` days from today: a card bridge in S0 (outside, at the card rate), a pool bridge in M1. Returns
        the world after the day and the bridge's balance left."""
        w = controlled_world(arm)
        pool = arm != "S0"
        if pool:
            funded_pool(w, 1000.0)
            w.pcash[0] = money
        else:
            w.holder[0], w.card_apr[0] = True, 0.0
            w.cash[0] = money
        w.buffer[0] = 500.0
        t = DAYS + 5
        w._add_loans(np.array([0]), pool, BRIDGE, np.array([300.0]), 0.0, 0.0, t + due_in)
        if late_wage:
            # An overdue wage of person 0's to person 1, re-queued to a later pay date so today's settlement leaves it.
            w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([late_wage]),
                        settle=np.array([t + 30]), card=np.array([False]), kind=np.array([LATE_WAGE]))
            w.payable[0] = w.receivable[1] = late_wage
        w.day(1, 5)
        w._arrears(t + 1)
        bridge = w.book["kind"] == BRIDGE
        return w, float((w.book["principal"] + w.book["interest"])[bridge].sum())

    def test_a_due_bridge_is_collected_from_all_money(self):
        """A bridge that is due is collected from all of the borrower's money, not only the part above the buffer.

        Example: buffer 500, a 300 bridge due today, 400 of money after the day's payments, all below the buffer.
        300 is collected, 100 is left and the borrower is not in arrears tomorrow. With only 200, all 200 is
        collected, 100 stays past due and the borrower is in arrears tomorrow. The same holds for a card bridge (S0)
        and a pool bridge (M1)."""
        for arm in ("S0", "M1"):
            w, left = self._due_bridge_day(arm, 400.0)
            self.assertAlmostEqual(left, 0.0, places=9, msg=arm)
            self.assertAlmostEqual(float(w.cash[0] + w.pcash[0]), 100.0, places=2, msg=arm)  # S0 cash earns its yield
            self.assertFalse(bool(w.arrears[0]), arm)
            w, left = self._due_bridge_day(arm, 200.0)
            self.assertAlmostEqual(left, 100.0, places=9, msg=arm)
            self.assertAlmostEqual(float(w.cash[0] + w.pcash[0]), 0.0, places=9, msg=arm)
            self.assertTrue(bool(w.arrears[0]), arm)
            self.assertEqual(float(w.od_pending.sum()), 0.0, arm)
            self.assertFalse(bool((w.book["kind"] == OVERDRAFT).any()), arm)

    def test_a_bridge_not_yet_due_is_repaid_only_above_the_buffer(self):
        """A bridge due tomorrow keeps the existing rule: with 400 of money below a buffer of 500 nothing is repaid,
        and it is not in arrears."""
        for arm in ("S0", "M1"):
            w, left = self._due_bridge_day(arm, 400.0, due_in=1)
            self.assertAlmostEqual(left, 300.0, places=9, msg=arm)
            self.assertFalse(bool(w.arrears[0]), arm)

    def test_a_due_bridge_ranks_ahead_of_overdue_wages(self):
        """A bridge that has reached its due date is collected before overdue wages, as an instalment falling due is.

        Example: buffer 500, money 700, an overdue wage of 250 and a 300 bridge due today: the bridge
        takes 300, which leaves 400, nothing above the buffer, so the wage stays overdue in full."""
        for arm in ("S0", "M1"):
            w, left = self._due_bridge_day(arm, 700.0, late_wage=250.0)
            self.assertAlmostEqual(left, 0.0, places=9, msg=arm)
            self.assertAlmostEqual(float(w.cash[0] + w.pcash[0]), 400.0, places=2, msg=arm)
            self.assertAlmostEqual(float(w.ob["amount"][w.ob["kind"] == LATE_WAGE].sum()), 250.0, places=9, msg=arm)

    def test_a_due_bridge_draws_same_day_savings(self):
        """As instalments falling due are, a due bridge is collected from cash, then same-day savings: 100 of money
        and 250 of outside savings repay a 300 bridge due today, leaving 50 in savings."""
        w = controlled_world("S0")
        w.buffer[0], w.cash[0], w.savings[0] = 500.0, 100.0, 250.0
        w._add_loans(np.array([0]), False, BRIDGE, np.array([300.0]), 0.0, 0.0, DAYS + 5)
        w._collect_due(DAYS + 5)
        self.assertAlmostEqual(float((w.book["principal"] + w.book["interest"]).sum()), 0.0, places=12)
        self.assertAlmostEqual(float(w.cash[0]), 0.0, places=12)
        self.assertAlmostEqual(float(w.savings[0]), 50.0, places=12)

    def _missed_instalment_day(self, arm, money, bridge=0.0):
        """One quiet day (month 2, day 5) for person 0 with a buffer of 500 and ``money`` of its own: a term loan of
        1,200 over 12 months whose first instalment of 100 fell due a month ago and was missed, and, if ``bridge``, a
        bridge of that size due today. Outside loans in S0, pool loans in M1; no interest. Returns the world after the
        day, the instalment amount still overdue and the bridge's balance left."""
        w = controlled_world(arm)
        pool = arm != "S0"
        if pool:
            funded_pool(w, 2000.0)
            w.pcash[0] = money
        else:
            w.holder[0], w.card_apr[0] = True, 0.0
            w.cash[0] = money
        w.buffer[0] = 500.0
        t = 2 * DAYS + 5
        w._add_loans(np.array([0]), pool, TERM, np.array([1200.0]), 0.0, 0.0, BIG, np.array([12]), 0)
        term = w.book["kind"] == TERM
        w.book["ndue"][term], w.book["since"][term] = 1, t - DAYS     # one instalment due, unpaid for a month
        if bridge:
            w._add_loans(np.array([0]), pool, BRIDGE, np.array([bridge]), 0.0, 0.0, t)
        w._collect_due(t)
        w._arrears(t + 1)
        every = np.arange(w.book["borrower"].size)
        left = w.book["kind"] == BRIDGE
        return w, float(w._overdue(every).sum()), float((w.book["principal"] + w.book["interest"])[left].sum())

    def test_a_missed_instalment_is_collected_from_all_money(self):
        """A missed instalment is collected from all of the borrower's money, not only the part above the buffer.

        Example: buffer 500, 400 of money, all below the buffer, and an instalment of 100 missed a month ago. The 100
        is collected, 300 is left, the loan is current again and the borrower is not in arrears. The same holds for
        an outside loan (S0) and a pool loan (M1)."""
        for arm in ("S0", "M1"):
            w, overdue, _ = self._missed_instalment_day(arm, 400.0)
            self.assertAlmostEqual(overdue, 0.0, places=9, msg=arm)
            self.assertAlmostEqual(float(w.cash[0] + w.pcash[0]), 300.0, places=9, msg=arm)
            self.assertFalse(bool(w.arrears[0]), arm)
            term = w.book["kind"] == TERM
            self.assertAlmostEqual(float(w.book["principal"][term].sum()), 1100.0, places=9, msg=arm)
            self.assertTrue(bool((w.book["since"][term] == BIG).all()), arm)   # no longer counted towards a write-off

    def test_a_missed_instalment_ranks_ahead_of_a_due_bridge(self):
        """A missed instalment ranks ahead of a due bridge.

        Example: buffer 500, 250 of money, a missed instalment of 100 and a 200
        bridge due today. The instalment is paid in full first, the bridge gets the 150 left and 50 of it stays past
        due, so the shortfall sits on the bridge, not on the instalment loan."""
        for arm in ("S0", "M1"):
            w, overdue, bridge = self._missed_instalment_day(arm, 250.0, bridge=200.0)
            self.assertAlmostEqual(overdue, 0.0, places=9, msg=arm)
            self.assertAlmostEqual(bridge, 50.0, places=9, msg=arm)
            self.assertAlmostEqual(float(w.cash[0] + w.pcash[0]), 0.0, places=9, msg=arm)
            self.assertTrue(bool(w.arrears[0]), arm)

    def test_the_dealing_collects_a_bridge_already_due_before_a_dearer_current_one(self):
        """The dealing collects a bridge already due before a dearer current one.

        Example: at the dealing of month 1 (day 30) a borrower with savings of 1 owes a bridge of 1 due on day 29 at
        1% and a dearer bridge of 1 due on day 45 at 2%. What was due before today is collected first, so the due
        bridge is paid and the current one is not: principal [0, 1]."""
        w = controlled_world("S0")
        w.savings[0] = 1.0
        for due, rate in [(29, 0.01), (45, 0.02)]:
            w._add_loans(np.array([0]), False, BRIDGE, np.ones(1), rate, rate, due)
        w._dealing(1)
        self.assertEqual(w.book["due"].tolist(), [29, 45])
        self.assertAlmostEqual(float(w.book["principal"][0]), 0.0, places=12)
        self.assertAlmostEqual(float(w.book["principal"][1]), 1.0, places=12)

    def test_the_dealing_collects_a_due_bridge_before_overdue_wages(self):
        """The dealing collects a due bridge before overdue wages.

        Example: at the dealing of month 1 a payer holds savings of 300, owes an overdue wage of 250 and a bridge
        of 300 due on day 29, no interest: money for one. What is due ranks first, so the bridge is paid in full and
        the wage stays overdue at 250. A bridge falling due on the dealing day itself (day 30) is left for that day's
        end: nothing is collected for it at the dealing."""
        for due, paid in ((DAYS - 1, True), (DAYS, False)):
            w = controlled_world("S0")
            w.savings[0] = 300.0
            w._add_loans(np.array([0]), False, BRIDGE, np.array([300.0]), 0.0, 0.0, due)
            w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([250.0]),
                        settle=np.array([DAYS + 30]), card=np.array([False]), kind=np.array([LATE_WAGE]))
            w.payable[0] = w.receivable[1] = 250.0
            w._dealing(1)
            bridge = float(w.book["principal"][w.book["kind"] == BRIDGE].sum())
            wage = float(w.ob["amount"][w.ob["kind"] == LATE_WAGE].sum())
            if paid:
                self.assertAlmostEqual(bridge, 0.0, places=9)
                self.assertAlmostEqual(wage, 250.0, places=9)
            else:   # current debts: the wage first, then the bridge from what is left
                self.assertAlmostEqual(wage, 0.0, places=9)
                self.assertAlmostEqual(bridge, 250.0, places=9)

    def test_a_one_sweep_cap_cannot_skip_the_fixed_point(self):
        """Every settlement is verified by one more sweep; a cap that stops short is an error, not overdraft."""
        w = controlled_world("S0")
        w.economy = replace(w.economy, sweeps=1)
        w.ob = dict(buyer=np.arange(4), seller=np.arange(1, 5), amount=np.ones(4), settle=np.full(4, 30),
                    card=np.zeros(4, bool), kind=np.full(4, SERVICE))
        np.add.at(w.receivable, w.ob["seller"], 1.0)
        np.add.at(w.payable, w.ob["buyer"], 1.0)
        with self.assertRaises(RuntimeError):
            w._settle(1, 30)

    def test_a_cycling_bridge_request_is_deferred_for_the_day(self):
        """Reserve 30 for an exit, leaving 100 to lend. Alice needs 100 and owes Ben 10. Ben needs 70 if she pays in
        full. He qualifies at his limit of 72, but his entry cuts Alice's draw and makes his shortfall exceed 72.
        Defer Ben's bridge, clear Alice's payments, and fund Ben's remaining 70 by card: with card limits it is a cash
        advance, here at the card's rate of zero and no fee."""
        w = controlled_world("U")
        funded_pool(w, 130.0)
        w.reserves = 130.0
        w.this_month = 2
        w.exit_start[2], w.exit_left[2] = 1, 30.0
        w.holder[1], w.cash[1], w.card_apr[1] = True, 20.0, 0.0
        w.cash_apr[1], w.advance_floor, w.advance_rate = 0.0, 0.0, 0.0
        w.r_b = 0.0
        w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
        w.last["receipts"][:] = 0.0
        w.last["receipts"][:2] = [100.0, 36.0]
        w.ob = dict(buyer=np.array([0, 0, 1]), seller=np.array([1, 4, 3]), amount=np.array([10.0, 90.0, 100.0]),
                    settle=np.full(3, 60), card=np.zeros(3, bool), kind=np.full(3, SERVICE))
        np.add.at(w.receivable, w.ob["seller"], w.ob["amount"])
        np.add.at(w.payable, w.ob["buyer"], w.ob["amount"])
        before = w.net_wealth().sum()
        failed_before = w.acc["failed"]

        w._settle(2, 60)

        pool = w.book["pool"]
        np.testing.assert_array_equal(w.book["borrower"][pool], [0])
        np.testing.assert_array_equal(w.book["principal"][pool], [100.0])
        np.testing.assert_array_equal(w.book["borrower"][~pool], [1])
        np.testing.assert_array_equal(w.book["principal"][~pool], [70.0])
        self.assertEqual(w.pool_cash, 30.0)
        self.assertEqual(w.acc["failed"], failed_before)
        self.assertEqual(float(w.od_pending.sum()), 0.0)
        self.assertEqual(w.net_wealth().sum() - before, w.external + w.valuation)

    def test_native_p_subscribes_without_a_conversion_reserve(self):
        """Under routine conversion, P already held buys shares one for one; nothing is left idle (all of it
        money-market money)."""
        w = controlled_world()
        w.economy = replace(w.economy, routine_conversion=True)
        w.part[:], w.pcash[:], w.mm_share[:] = True, 1.0, 1.0
        w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 0.0, 1.0, 100.0, 0.02, True   # capacity does not bind
        w.last["flows"][:] = 0.0
        w.last["flows_s0"][:] = 0.0
        before = float(w.acc["conversion"].sum())   # the quiet month's own rounding, not dealing's
        w._dealing(1)
        self.assertAlmostEqual(float(w.shares.sum()), 10.0, places=12)
        self.assertEqual(float(w.acc["conversion"].sum()), before)

    def test_p_funded_saving_pays_its_conversion_from_the_same_money(self):
        """Under routine conversion, P converted into E savings buys spare / (1 + fee) and borrows nothing (all of it
        money-market money with no pool to take it: P's deposit part would stay in P, which pays more than deposits
        under competitive P)."""
        w = controlled_world()
        w.economy = replace(w.economy, routine_conversion=True)
        w.part[:], w.pcash[:], w.R_hat, w.Q, w.mm_share[:] = True, 1.0, 0.0, 0.0, 1.0
        w.last["flows"][:] = 0.0
        w.last["flows_s0"][:] = 0.0
        w._dealing(1)
        self.assertAlmostEqual(float(w.savings.sum()), 10 / (1 + CONVERSION_FEE), places=12)
        self.assertEqual(float(w.book["principal"].sum()), 0.0)

    def test_gas_leaves_the_economy_and_funds_no_same_day_delivery(self):
        """A P payment's gas goes to validators outside the economy and funds no same-day delivery.

        P payments run on stablecoin rails, so none of the gas reaches pool cash to be lent the same day. The payment
        is in P because every payment between participants is (routing "all") and it is not card-eligible, so it
        cannot go on the card. Its payer holds 0.002 of P, which pays the gas, and owes the unit: a pool holding
        0.998 lends 0.998 and the card bridges the gas, and a pool holding the gas more lends it all. With card
        limits the card bridges it as a cash advance, here at the card's rate and no fee."""
        def lent(capital):
            w = controlled_world()
            w.economy = replace(w.economy, routing="all")
            funded_pool(w, capital)
            w.pcash[0] = 0.002
            w.holder[0], w.card_apr[0], w.r_g = True, 0.01, 0.005
            w.cash_apr[0], w.advance_floor, w.advance_rate = 0.01, 0.0, 0.0
            w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
            w.last["receipts"][:] = 1.0
            one_invoice(w, card=False)
            w._settle(1, 30)
            np.testing.assert_allclose(w.acc["gas"][0], GAS_PER_P_PAYMENT, rtol=1e-12)
            return w.book["principal"][w.book["pool"]], w.book["principal"][~w.book["pool"]]
        pool, outside = lent(0.998)
        np.testing.assert_allclose(pool, [0.998], rtol=0, atol=1e-15)
        np.testing.assert_allclose(outside, [GAS_PER_P_PAYMENT], rtol=0, atol=1e-15)
        pool, outside = lent(0.998 + GAS_PER_P_PAYMENT)
        np.testing.assert_allclose(pool, [0.998 + GAS_PER_P_PAYMENT], rtol=0, atol=1e-15)
        self.assertEqual(outside.size, 0)

    def owned_pool(self, cash, loan=True):
        """One household owning the pool (1 share at NAV 1), optionally beside one outstanding pool bridge; every owner
        reviews every month and leaves by the users' rule without noise (``reviewing``), the rule's limit."""
        w = controlled_world()
        w.shares[0], w.nav_ps, w.pool_cash, w.Q, w.had_owners, w.launched = 1.0, 1.0, cash, 10.0, True, True
        w.pool_alternative[:] = 0.001
        reviewing(w)
        if loan:
            w._add_loans(np.array([1]), True, BRIDGE, np.array([1.0]), 0.005, 0.02, 90)
        return w

    def test_exit_request_lapses_when_the_owners_own_return_recovers(self):
        """A request waits two months; if the owner no longer wants out by then, nothing is paid or wound down. The
        owner reads its own realised return: nothing in its first month, below its 0.1% a month plus the owners'
        spread, then 1.5% a month over its two months once the second earns 3%, and at that review its draw no
        longer says leave."""
        w = self.owned_pool(0.0)
        w.R_hat = 0.0
        closed(w, 0, 0.0)
        w._dealing(1)                       # request filed
        self.assertEqual(int(w.exit_start[0]), 1)
        closed(w, 1, 0.03)
        self.assertAlmostEqual(float(w._own_return(2)[0]), 0.015, places=15)
        w._dealing(2)                       # recovered within the notice: the request lapses
        self.assertFalse(w.winding)
        self.assertEqual(int(w.exit_start[0]), -1)
        self.assertAlmostEqual(float(w.shares[0]), 1.0)

    def test_executed_full_exit_winds_down_until_paid(self):
        """Wind-down applies once every owner's exit is executed (the issuer holds no shares); a later
        better quote does not stop it while shares remain to be paid."""
        w = self.owned_pool(0.0)
        w.R_hat = 0.0
        earning(w, 0.0)                      # the owner's own return, below its own rate
        list(map(w._dealing, (1, 2)))
        self.assertFalse(w.winding)          # requested, not yet executed
        w._dealing(3)                        # two months on, still worse: executed
        self.assertTrue(w.winding)
        w.R_hat = 0.01
        w._dealing(4)
        self.assertTrue(w.winding)

    def test_exit_pays_the_execution_date_nav(self):
        """The exiter bears the losses of the notice period: payment uses the NAV of the execution month."""
        w = self.owned_pool(2.0, loan=False)
        w.nav_ps = w._assets() / w._all_shares()
        w.R_hat = 0.0
        earning(w, 0.0)
        w._dealing(1)
        w.pool_cash -= 0.5                   # a loss during the notice period
        w.nav_ps = w._assets() / w._all_shares()
        nav_at_execution = w.nav_ps
        shares = float(w.shares[0])
        w._dealing(3)
        self.assertAlmostEqual(float(w.acc["exit_paid"]), shares * nav_at_execution, places=12)
        self.assertLess(nav_at_execution, 2.0)   # it is the post-loss NAV, not the NAV when the request was filed

    def test_exits_are_paid_from_pool_cash_after_the_notice_and_the_rest_waits(self):
        """Exits are paid from pool cash after the notice and the rest waits.

        The issuer is a pure custodian, so owners' exits are paid from pool cash after the two-month notice and no
        fund buys them. Example ($): an owner asks to take out $1,000 of a $2,900 pool holding $550 of cash. Two
        months on the pool pays $550 and $450 waits; $200 of later cash pays $200, and $300 more pays
        the last $250, so the pool ends at $1,900 with $50 of cash, and it never winds down, since the other owner
        stays."""
        w = self.owned_pool(550.0, loan=False)
        w.shares[0], w.shares[3], w.pool_alternative[3] = 1000.0, 1900.0, -1.0   # one owner leaving, one staying
        w.Q, w.R_hat = 1e9, 0.0
        earning(w, 0.0)                            # every owner's own return 0, below the leaver's own rate
        w._dealing(1)                              # the request is filed
        self.assertEqual(float(w.acc["exit_paid"]), 0.0)
        w._dealing(3)                              # executed: the pool's cash pays $550
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 550.0, places=9)
        self.assertAlmostEqual(float(w.shares[0]), 450.0, places=9)
        self.assertAlmostEqual(w.pool_cash, 0.0, places=9)
        self.assertFalse(w.winding)
        w.pool_cash = 200.0                        # loan repayments, less than the $450 still owed
        w._dealing(4)
        self.assertAlmostEqual(float(w.shares[0]), 250.0, places=9)
        w.pool_cash += 300.0
        w._dealing(5)
        self.assertEqual(float(w.shares[0]), 0.0)
        self.assertAlmostEqual(w.pool_cash, 50.0, places=9)
        self.assertAlmostEqual(float(w.shares.sum()), 1900.0, places=9)
        self.assertFalse(w.winding)
        self.assertFalse(any(hasattr(w, name) for name in ("fund", "fund_shares", "issuer_shares", "issuer_support")))

    def test_due_exits_rank_ahead_of_new_loans_and_offers_buy_them_first(self):
        """Due exits rank ahead of new loans, and offers buy them first.

        Exits are paid from pool cash after the two-month notice, and due exits rank ahead of new bridges and term
        loans. Example ($): during an owner's notice the pool sets aside cash for it: with $500 of
        pool cash and a $300 request filed in month 1, due at the dealing of month 3, new loans in month 2 may take
        only $200; a request filed in month 2, due in month 4, is not yet set aside. At the dealing, money offered to
        the pool first buys the due exits pool cash left unpaid, at NAV, as subscriptions meet redemptions in an
        open-ended fund: an owner takes out $1,000 of a $2,900 pool, N* $2,900, holding $550 of cash; the cash pays
        $550, a saver's offer buys the other $450, and only the rest, $550, takes room up to N*, so the owner is paid
        in full within its notice, capital is $2,900 again and the pool holds $550 of cash. No backstop is used.

        The set-aside is only the due exits beyond the last dealing's unused offers; this world has had no dealing,
        so its unused offers are zero and the whole $300 is set aside. The rule with offers is pinned in the test
        below."""
        w = self.owned_pool(500.0, loan=False)
        self.assertEqual(w.unused_offers, 0.0)
        w.shares[0], w.shares[3] = 300.0, 1000.0
        w.this_month = 2
        w.exit_start[0], w.exit_left[0] = 1, 300.0
        self.assertAlmostEqual(w._cash_for_loans(), 200.0, places=12)
        self.assertAlmostEqual(w._lendable(), 500.0, places=12)             # exits themselves are paid from it all
        w.exit_start[0] = 2
        self.assertAlmostEqual(w._cash_for_loans(), 500.0, places=12)
        w = self.owned_pool(550.0, loan=False)
        w.shares[0], w.shares[3], w.pool_alternative[3] = 1000.0, 1900.0, -1.0   # one owner leaving, one staying
        w.part[4], w.pcash[4], w.mm_share[:] = True, 50000.0, 1.0                   # a saver
        w.mm_share[0] = 0.0                              # the leaver does not offer its payout back
        w.Q, w.R_hat = 2900.0, 0.0
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        earning(w, 0.0)                                  # the owner's own return 0, below its own rate
        list(map(w._dealing, (1, 2)))                    # filed; no saver enters at a quote below its rate
        self.assertEqual(float(w.shares[4]), 0.0)
        w.R_hat = 0.01
        w._dealing(3)                                    # executed: cash pays $550, the saver's money the rest
        self.assertEqual(float(w.shares[0]), 0.0)
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 1000.0, places=9)
        self.assertAlmostEqual(float(w.shares[4]) * w.nav_ps, 1000.0, places=9)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 2900.0, places=9)
        self.assertAlmostEqual(w.pool_cash, 550.0, places=9)
        self.assertAlmostEqual(float(w.exit_in_time[1]), float(w.exit_started[1]), places=9)
        self.assertAlmostEqual(float(w.exit_started[1]), 1000.0, places=9)
        self.assertFalse(w.winding)

    def test_cash_for_loans_sets_aside_only_the_due_exits_unused_offers_would_not_cover(self):
        """Cash for loans sets aside only the due exits that the last dealing's unused offers would not cover.

        New subscriptions pay leaving owners first. Example ($): pool cash $100 with nothing payable and $60 of exits
        falling due at the next dealing. With $500 of the last dealing's offers unused, they cover the exits and
        nothing is set aside: cash for loans is $100. With $20 unused, $40 is set aside and cash for loans is $60.
        With none unused, all $60 is set aside and cash for loans is $40. Exits themselves are paid from all $100."""
        w = self.owned_pool(100.0, loan=False)
        w.shares[0], w.shares[3] = 60.0, 1000.0
        w.this_month = 2
        w.exit_start[0], w.exit_left[0] = 1, 60.0
        self.assertEqual(w.pool_payable, 0.0)
        for unused, cash in ((500.0, 100.0), (20.0, 60.0), (0.0, 40.0)):
            w.unused_offers = unused
            self.assertAlmostEqual(w._cash_for_loans(), cash, places=12)
            self.assertAlmostEqual(w._lendable(), 100.0, places=12)

    def test_an_exit_falling_due_is_paid_by_offers_when_pool_cash_is_zero(self):
        """An exit falling due is paid by offers when pool cash is zero: new subscriptions pay leaving owners first.

        Example: an owner files to take out $1,000 of a $2,900 pool at N* $2,900, and a saver with $50,000 of P
        offers at every dealing at a quote above its own rate. The pool is full, so the offer finds no room and is
        recorded unused; with it, the $1,000 falling due is not set aside: $1,000 of repayments in the month before
        the exit is all cash for loans, and lent. At the
        dealing pool cash is zero, so the exit is paid by the saver's accepted offer, in full and within its notice;
        capital is $2,900 again and the pool holds no cash."""
        w = self.owned_pool(0.0, loan=False)
        w.shares[0], w.shares[3], w.pool_alternative[3] = 1000.0, 1900.0, -1.0   # one owner leaving, one staying
        w.part[4], w.pcash[4], w.mm_share[:] = True, 50000.0, 1.0                   # a saver
        w.mm_share[0] = 0.0                              # the leaver does not offer its payout back
        w.Q, w.R_hat = 2900.0, 0.01
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        earning(w, 0.0)                                  # the owner's own return 0, below its own rate
        list(map(w._dealing, (1, 2)))                    # filed; the saver's offer finds no room
        self.assertEqual(int(w.exit_start[0]), 1)
        self.assertEqual(float(w.shares[4]), 0.0)
        self.assertAlmostEqual(w.unused_offers, 50000.0 - float(w.buffer[4]), places=6)
        w.this_month = 2
        w.pool_cash = 1000.0                             # repayments in month 2
        self.assertAlmostEqual(w._cash_for_loans(), 1000.0, places=9)
        w.pool_cash = 0.0                                # all lent
        w._dealing(3)                                    # executed: no pool cash, the saver's money pays it all
        self.assertEqual(float(w.shares[0]), 0.0)
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 1000.0, places=9)
        self.assertAlmostEqual(float(w.cash[0]), 1000.0 * (1 - w.conversion), places=9)   # redeemed to E: not in P
        self.assertAlmostEqual(float(w.shares[4]) * w.nav_ps, 1000.0, places=9)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 2900.0, places=9)
        self.assertAlmostEqual(w.pool_cash, 0.0, places=9)
        self.assertAlmostEqual(float(w.exit_in_time[1]), float(w.exit_started[1]), places=9)
        self.assertAlmostEqual(float(w.exit_started[1]), 1000.0, places=9)
        self.assertEqual(int(w.exit_start[0]), -1)
        self.assertFalse(w.winding)

    def test_only_a_saver_reviewing_entry_offers_to_the_pool(self):
        """Only a saver reviewing entry offers to the pool.

        Savers review entry at the users' rate, upsilon 0.153 a month. Example: two savers with $100 of P each, all of
        it money-market money, at a quote above their own rate and room to spare. The one whose entry-review draw is
        0.1 reviews and buys shares with its spare money; the one whose draw is 0.5 does not review, so
        its spare money goes to outside savings and the 10 shares it already holds stay."""
        w = self.owned_pool(0.0, loan=False)
        w.part[[4, 5]], w.pcash[[4, 5]], w.mm_share[[4, 5]] = True, 100.0, 1.0
        w.shares[5] = 10.0
        w.Q, w.R_hat = 1e9, 0.01
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        w.entry_draw = np.ones(w.n)
        w.entry_draw[[4, 5]] = 0.1, 0.5
        np.testing.assert_array_equal(np.flatnonzero(w._reviews_entry()), [4])
        w._dealing(1)
        self.assertAlmostEqual(float(w.shares[4]) * w.nav_ps, 100.0 - float(w.buffer[4]), places=9)
        self.assertGreater(float(w.shares[4]), 0.0)
        self.assertEqual(float(w.savings[4]), 0.0)
        self.assertEqual(float(w.shares[5]), 10.0)
        self.assertAlmostEqual(float(w.savings[5]), 100.0 - float(w.buffer[5]), places=9)
        self.assertGreater(float(w.savings[5]), 0.0)

    def test_entry_review_draws_are_one_a_person_a_month_on_their_own_stream(self):
        """The entry-review draws are one a person a month, burn-in included, on their own stream.

        The stream is seeded [seed, 41] and is the same in every arm, so arms stay paired. Over 5,040 draws the share
        reviewing is upsilon, 1 - exp(-0.166) = 0.15295, within sampling error (four standard errors,
        4 x sqrt(0.15295 x 0.84705 / 5040) = 4 x 0.005070 = 0.0203)."""
        economy = Economy(n=10, burn_in=10, months=1, inflation=0.0)
        expected = np.random.default_rng(np.random.SeedSequence([economy.seed, 41])).random(10)
        for arm in ("S0", "M1"):
            w = _World(Inputs(), 0.6, economy, arm)
            np.testing.assert_array_equal(w.entry_draw, np.ones(10))   # before any month, nobody reviews
            w.month(0)                                                   # a burn-in month
            np.testing.assert_array_equal(w.entry_draw, expected)
        w = tiny_world("M1")
        draws = np.concatenate([w.entry_rng.random(w.n) for _ in range(63)])
        self.assertEqual(draws.size, 5040)
        w.n, w.entry_draw = draws.size, draws
        share = float(w._reviews_entry().mean())
        self.assertLess(abs(share - w.inputs.upsilon), 4 * np.sqrt(0.15295 * 0.84705 / 5040))

    def test_an_owner_with_a_standing_exit_request_buys_no_shares(self):
        """An owner with a standing exit request buys no shares.

        An owner files to exit for its whole holding, at a review from one month after buying. Example: an owner
        files to take out its 10 shares at NAV 1. At the next dealing the quote is above its own
        rate and it has $5 of P to spare, but its request stands, so it buys none and the $5 goes to outside savings.
        At execution it is paid 10, its whole holding at filing, from pool cash, and holds nothing."""
        w = self.owned_pool(1000.0, loan=False)
        w.shares[0], w.part[0], w.mm_share[0] = 10.0, True, 1.0
        w.shares[2], w.pool_alternative[2] = 100.0, -1.0                    # an owner who stays
        w.Q, w.R_hat = 1e9, 0.0
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        earning(w, 0.0)                                                     # its own return 0, below its own rate
        w._dealing(1)                                                       # the request is filed
        np.testing.assert_array_equal(w.exit_start[[0, 2]], [1, -1])
        self.assertAlmostEqual(float(w.exit_left[0]), 10.0, places=12)
        w.pcash[0], w.R_hat = 5.0, 0.01
        self.assertTrue(bool(w._no_offer()[0]))
        w._dealing(2)                                                       # standing request: no offer
        self.assertEqual(float(w.shares[0]), 10.0)
        self.assertAlmostEqual(float(w.savings[0]), 5.0 - float(w.buffer[0]), places=9)
        w.cash[0] = w.pcash[0] = w.savings[0] = 0.0
        w._dealing(3)                                                       # executed: paid its 10
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 10.0, places=9)
        self.assertEqual(float(w.shares[0]), 0.0)
        self.assertEqual(int(w.exit_start[0]), -1)

    def test_no_exit_request_is_opened_without_a_filing(self):
        """No exit request is opened without a filing.

        The dealing's offers pay the executed exits that pool cash left unpaid, and the bookkeeping of those payments
        must not open a request for an owner who wanted out, had just been paid its request in full and still held
        shares, though it had filed none. Example ($, NAV 1): owner 0 holds 15 shares with a standing request for 5,
        owner 1 a request for its 10, owner 2 stays with 100, and the pool holds $15 of cash. At execution the cash
        pays 60% of the $25 due: owner 0 is paid 9 (its request for 5 done), owner 1 is paid
        6. A saver's $2 buys the unpaid exits pro rata. Owner 0 has no request open after the dealing and bought
        nothing back; owner 1's request stands."""
        w = self.owned_pool(15.0, loan=False)
        w.shares[:3] = 15.0, 10.0, 100.0
        w.pool_alternative[2] = -1.0
        w.part[[0, 1, 4]], w.mm_share[:] = True, 0.0
        w.pcash[0], w.pcash[4], w.mm_share[[0, 4]] = 50.0, 2.0, 1.0       # owner 0 has money to buy back
        w.exit_start[:2], w.exit_nav[:2], w.exit_left[:2] = 1, 1.0, (5.0, 10.0)
        w.exit_started[1] = 15.0
        w.Q, w.R_hat = 1.0, 0.01                                             # room only for the unpaid exits
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        earning(w, 0.0)
        w._dealing(3)
        self.assertAlmostEqual(float(w.shares[4]), 2.0, places=9)
        self.assertEqual(int(w.exit_start[0]), -1)
        self.assertEqual(float(w.exit_started[3]), 0.0)
        self.assertEqual(int(w.exit_start[1]), 1)
        self.assertAlmostEqual(float(w.shares[0]), 15.0 - 9.0 - 1.2, places=9)
        self.assertAlmostEqual(float(w.shares[1]), 10.0 - 6.0 - 0.8, places=9)

    def test_wind_down_pays_every_owner_pro_rata_from_cash(self):
        """Once every owner's exit is executing the pool winds down and pays them all pro rata from its cash: two
        owners of 1 each ask out and the pool holds 0.5 of cash, so each is paid 0.25 (no stake or fund is paid
        beside them)."""
        w = self.owned_pool(0.5, loan=False)
        w.shares[2] = 1.0
        w.R_hat = 0.0
        earning(w, 0.0)
        list(map(w._dealing, (1, 2)))
        self.assertFalse(w.winding)
        w._dealing(3)
        self.assertTrue(w.winding)
        np.testing.assert_allclose(w.shares[[0, 2]], [0.75, 0.75], rtol=1e-12)
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 0.5, places=12)

    def test_owners_read_their_own_return_since_buying_in_a_partial_run(self):
        """Owners read their own return since buying in a partial run.

        Owners leave by the users' rule without noise. Example ($): two participants hold $1,000 each from the first
        month and the pool holds $550 of cash. Every month earns owners' own rate a, except that the third writes off
        $17 on its $2,000 of capital. A third participant buys $755 after it. At the next dealing the first two read
        a - 17 / 6,000 over their three months and file; the third has no month behind it, so no reading, and a month
        later reads a and stays. Two months on the first two still read below a (the write-off is inside their 12
        months): the pool pays $550 from cash and $1,450 waits, so the pool runs on at $2,205; once the $1,450 is
        paid it runs on at $755. Under one comparator for every owner all three would have filed and the pool would
        have wound down."""
        w = self.owned_pool(550.0, loan=False)
        w.part[[0, 1, 3]] = True
        w.shares[:2] = 1000.0
        w.Q, w.R_hat = 1e9, 0.0
        a = float(w._owners_alternative_nominal()[0])
        rates = {1: a, 2: a, 3: a - 17.0 / 2000.0}
        for month in (1, 2, 3):
            w._dealing(month)
            closed(w, month, rates[month])
        self.assertTrue(np.all(w.exit_start < 0))             # every month so far at a: nobody files
        w.shares[3] = 755.0                                   # bought after the write-off
        np.testing.assert_allclose(w._own_return(4)[:2], a - 17.0 / 6000.0, rtol=0, atol=1e-18)
        self.assertTrue(np.isnan(w._own_return(4)[3]))
        w._dealing(4)
        np.testing.assert_array_equal(w.exit_start[[0, 1, 3]], [4, 4, -1])
        closed(w, 4, a)
        self.assertAlmostEqual(float(w._own_return(5)[3]), a, places=15)
        w._dealing(5)
        np.testing.assert_array_equal(w.exit_start[[0, 1, 3]], [4, 4, -1])
        closed(w, 5, a)
        w._dealing(6)                                         # executed: cash pays $550, $1,450 waits
        np.testing.assert_allclose(w.shares[[0, 1, 3]], [725.0, 725.0, 755.0], rtol=1e-12)
        self.assertFalse(w.winding)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 2205.0, places=9)
        closed(w, 6, a)
        w.pool_cash += 1450.0                                 # loan repayments
        w._dealing(7)
        np.testing.assert_allclose(w.shares[[0, 1, 3]], [0.0, 0.0, 755.0], rtol=0, atol=1e-9)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 755.0, places=9)
        self.assertEqual(int(w.exit_start[3]), -1)
        self.assertFalse(w.winding)

    def test_owners_leave_by_the_users_rule(self):
        """Owners leave the pool by the users' leaving rule: a reviewing owner files to exit with the logistic
        probability of its own return's shortfall less its leaving cost.

        Example ($ a month): two owners of $1,000 whose own realised return is 0.01 point a month below their own
        rate, a gap of -$0.10 a month, each spending the mean $6,440 a month, so the noise scale is 1e-4 of $6,440,
        $0.644. The participant's payout is credited in P and costs nothing to take, so it leaves with probability
        logistic(0.10 / 0.644) = 0.5387 when it reviews. The owner paid in E bears one conversion of its $1,000 at
        0.05% + $0.22 / $142 = 0.20493%, $2.0493, spread over 12 months, $0.17077, so its probability is
        logistic((0.10 - 0.17077) / 0.644) = 1 / (1 + exp(0.10989)) = 1 / (1 + 1.11616) = 0.4726. A share
        1 - exp(-0.166) = 15.295% of owners review a month: a review draw of 0.152 reviews and 0.154 does not, and a
        reviewer files when its leaving draw is below its probability. In M2 the return is in P terms and CPI is
        added, so the same gap gives the same probabilities. Without noise the rule is a step at the threshold: 0.01
        point below files the participant alone and 0.02 point below files both."""
        def world(shortfall, arm="M1", index=0.0, noise=1.0):
            w = controlled_world(arm)
            w.economy = replace(w.economy, leave_noise=noise)
            w.shares[:2], w.part[0], w.nav_ps, w.pool_cash, w.Q = 1000.0 / MONTH_USD, True, 1.0, 0.0, 1e9
            w.spending[:] = 1.0
            w.launched, w.had_owners, w.R_hat, w.index = True, True, 0.0, index
            earning(w, float(w._owners_alternative_nominal()[0]) - index - shortfall)
            return w

        def filed(w, review, leave):
            w.owner_draws = np.full(10, review), np.r_[np.asarray(leave, float), np.ones(8)]
            w._dealing(1)
            return (w.exit_start[:2] >= 0).tolist()
        cost = CONVERSION_FEE * 1000.0 / 12
        self.assertAlmostEqual(cost, 0.17077, places=5)
        want = [logistic(0.10 / 0.644), logistic((0.10 - cost) / 0.644)]
        self.assertAlmostEqual(want[0], 0.5387, places=4)
        self.assertAlmostEqual(want[1], 0.4726, places=4)
        for arm, index in (("M1", 0.0), ("M2", 0.002)):
            w = world(0.0001, arm, index)
            gap = w._own_gap(1)[:2] * MONTH_USD
            np.testing.assert_allclose(gap, -0.10, rtol=1e-9)
            threshold = np.array([0.0, CONVERSION_FEE]) * 1000.0 / MONTH_USD / 12
            np.testing.assert_allclose(w._leave_chance(w._own_gap(1), np.r_[threshold, np.zeros(8)])[:2], want,
                                       rtol=1e-9)
            self.assertEqual(filed(w, 0.152, [want[0] - 1e-6, want[1] + 1e-6]), [True, False])
            self.assertEqual(filed(world(0.0001, arm, index), 0.152, [want[0] + 1e-6, want[1] - 1e-6]),
                             [False, True])
            self.assertEqual(filed(world(0.0001, arm, index), 0.154, [0.0, 0.0]), [False, False])
        self.assertEqual(filed(world(0.0001, noise=0.0), 0.0, [0.0, 0.0]), [True, False])
        self.assertEqual(filed(world(0.0002, noise=0.0), 0.0, [0.0, 0.0]), [True, True])
        self.assertTrue(np.isnan(controlled_world()._own_gap(1)).all())     # no holding, no reading

    def test_the_owners_draws_have_a_stream_of_their_own(self):
        """The owners' leaving rule draws from a random stream of its own: each month every arm draws a review number
        and a leaving number for each person from it, the same in every arm, and no other stream moves. S0's records
        are the same whatever the owners' stream holds, and a pool arm's draws are the stream's own."""
        economy = replace(TINY, n=40, months=4)
        draws = {}
        for arm in ("S0", "M0", "M1"):
            w = _World(Inputs(), 0.6, economy, arm)
            seen = []
            month = w.month
            w.month = lambda m, w=w, seen=seen, month=month: (month(m), seen.append(w.owner_draws))[0]
            w.run()
            draws[arm] = seen
        stream = np.random.default_rng(np.random.SeedSequence([economy.seed, 31]))
        expected = [(stream.random(40), stream.random(40)) for _ in range(economy.burn_in + economy.months)]
        for arm in draws:
            for got, want in zip(draws[arm], expected):
                np.testing.assert_array_equal(got[0], want[0])
                np.testing.assert_array_equal(got[1], want[1])

        class Other(_World):
            def __init__(self, *args):
                super().__init__(*args)
                self.owner_rng = np.random.default_rng(1)
        self.assert_same_outcome(simulate(Inputs(), 0.6, economy, "S0"), Other(Inputs(), 0.6, economy, "S0").run(), ())

    def test_room_is_the_limit_less_every_share(self):
        """The room for new capital is capacity less every share held: the issuer holds no stake and no fund, so
        nothing else counts against capacity.

        Example ($, capacity $2,900, a household offering more than the room): an empty pool takes $2,900 and nothing
        comes back next month; with $855 already held it takes $2,045."""
        def dealt(households=0.0, months=(1,)):
            w = controlled_world()
            w.part[0], w.pcash[0], w.mm_share[:] = True, 5000.0, 1.0      # all of it money-market money
            w.pool_alternative[:], w.pool_alternative[1] = 0.001, -1.0     # 1 holds and stays
            w.shares[1] = households
            w.nav_ps, w.pool_cash, w.Q, w.R_hat, w.launched = 1.0, 0.0, 2900.0, 0.01, True
            w.last["flows"][:] = 0.0
            w.last["flows_s0"][:] = 0.0
            list(map(w._dealing, months))
            return w
        capital = lambda w: w._all_shares() * w.nav_ps
        w = dealt()
        self.assertAlmostEqual(float(w.shares.sum()), 2900.0, places=9)
        self.assertAlmostEqual(capital(w), 2900.0, places=9)
        w = dealt(months=(1, 2))
        self.assertAlmostEqual(capital(w), 2900.0, places=9)
        self.assertEqual(float(w.acc["exit_paid"]), 0.0)
        w = dealt(households=855.0)
        self.assertAlmostEqual(float(w.shares[0]), 2045.0, places=9)
        self.assertAlmostEqual(capital(w), 2900.0, places=9)

    def test_capital_above_the_limit_stays(self):
        """Capital already above a fallen capacity N* stays: nobody is returned capital pro rata and no saver enters.

        Example ($): N* falls to $2,500 while capital is $2,900 and no owner files. The household keeps its $2,900
        and the pool keeps its $400 of cash."""
        w = controlled_world()
        w.pool_alternative[:] = -1.0                                     # every owner stays and every saver offers
        w.shares[1] = 2900.0
        w.nav_ps, w.pool_cash, w.Q, w.R_hat, w.launched = 1.0, 400.0, 2500.0, 0.01, True
        w.last["flows"][:] = 0.0
        w.last["flows_s0"][:] = 0.0
        w._dealing(1)
        self.assertEqual(float(w.shares.sum()), 2900.0)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 2900.0, places=9)
        self.assertEqual(float(w.acc["exit_requested"]), 0.0)
        self.assertEqual(w.pool_cash, 400.0)

    def test_capital_after_dealing_never_exceeds_capacity(self):
        """Entry never takes capital after dealing (every share at NAV) above capacity N*. Capital already above a
        fallen N* stays, so a dealing ends at most at the larger of N* and the capital it began with."""
        class Dealt(_World):
            def _dealing(self, month):
                before = self._all_shares() * self.nav_ps
                capital = super()._dealing(month)
                self.seen.append((capital, max(self.Q, before)))
                return capital
        for arm in ("M1", "M2"):
            w = Dealt(Inputs(), 0.6, replace(TINY, n=100, months=14), arm)
            w.seen = []
            w.run()
            capital, bound = np.array(w.seen).T
            self.assertTrue(np.any(capital > 0))
            self.assertTrue(np.all(capital <= bound * (1 + 1e-12)))

    def test_the_issuer_holds_no_pool_shares_and_households_own_all_capital(self):
        """The issuer is a pure custodian: it holds no pool shares and no support fund. In every pool arm of a run
        whose pool forms (the test device), households' capital is all pool capital every month, no stake or fund
        line or series is kept, wealth accounting stays exact, and the issuer's wallet, its custody less its cost, is
        never negative beyond rounding, so the stay test never reads "would leave"."""
        for arm in ("U", "M1", "M2"):
            world = PooledWorld(Inputs(), 0.6, replace(TINY, n=100, months=12), arm)
            series = world.run()["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            self.assertGreater(float(series["N"].max()), 0.0, arm)
            np.testing.assert_allclose(series["owners_capital"], series["N"], rtol=1e-12, atol=0)
            self.assertFalse(any(hasattr(world, name) for name in ("issuer_shares", "fund", "fund_shares")), arm)
            self.assertFalse({"issuer_stake", "issuer_held_share", "issuer_owner", "issuer_support_fund",
                              "issuer_fund_balance", "issuer_support"} & set(series), arm)
            self.assertTrue(np.all(series["issuer_wallet"][TINY.burn_in:] >= -1e-15), arm)
            self.assertFalse(np.nan_to_num(series["issuer_would_leave"]).any(), arm)
        self.assertEqual(ISSUER_BOOKS, ("custodian", "indexer", "float", "expenses", "wallet", "owners_in", "payout",
                                        "expense_holding"))

    def test_issuer_books_reproduce_the_hand_case(self):
        """The books of the issuer, a pure custodian that keeps its cost c_I and pays out the rest of the reserve yield.

        Example ($ a person a year, one model month standing for the year): on $1,350 of P at r_out 4.4% with a cost
        of 0.24% of P, the custodian line is $59.40, it pays out rho_p - c_I, 4.16%, $56.16, and its expenses are
        $3.24, so its wallet is zero and nothing is paid out. In M2 at 4.4% indexation is $27.00 and it pays out
        2.16%, $29.16: zero again. In a wind-down month the $200 of the pool's own cash earns it its 4.16%, $8.32,
        the payout. In M2 at r_out 2%, a zero real rate, it pays nothing out and its wallet is minus its cost,
        -$3.24, which its owners add (a declared limit of M2)."""
        def books(index=0.0, rate=0.044, paid=None):
            w = controlled_world("M2" if index else "M1")
            w.economy = replace(w.economy, issuer_cost=0.0024)
            w.inputs, w.index, w.rho_p = replace(w.inputs, rho_H=rate), index, rate - index
            net = max(rate - index - 0.0024, 0.0)
            w.acc.update(p_all=1350.0, wallet_yield=net * 1350.0 if paid is None else paid, float_pool=0.0)
            return w._issuer_books()
        check = lambda got, **want: [self.assertAlmostEqual(got[key], value, places=10) for key, value in want.items()]
        check(books(), custodian=59.40, indexer=0.0, float=-56.16, expenses=-3.24, wallet=0.0, payout=0.0,
              owners_in=0.0, expense_holding=-3.24)
        check(books(0.02), custodian=59.40, indexer=-27.00, float=-29.16, wallet=0.0)
        check(books(paid=0.0416 * 1150.0), float=-47.84, wallet=8.32, payout=8.32, owners_in=0.0)
        check(books(0.02, rate=0.02), custodian=27.00, indexer=-27.00, float=0.0, wallet=-3.24, owners_in=3.24,
              payout=0.0)
        self.assertEqual(set(books()), set(ISSUER_BOOKS))

    def test_issuer_books_reconcile_every_month(self):
        """The issuer's lines add up to its wallet, which its owners take out or put in, and its net reserve income is
        its custodian, indexer and float lines (the test device, whose pool forms)."""
        for arm in ("M1", "M2"):
            series = pooled(Inputs(), 0.6, replace(TINY, n=100, months=12), arm)["series"]
            get = lambda key: series["issuer_" + key]
            lines = sum(map(get, ("custodian", "indexer", "float", "expenses")))
            np.testing.assert_allclose(get("wallet"), lines, atol=1e-15)
            np.testing.assert_allclose(series["issuer"], get("custodian") + get("indexer") + get("float"),
                                       atol=1e-15)
            np.testing.assert_allclose(get("payout") - get("owners_in"), get("wallet"), atol=1e-15)

    def test_a_forced_run_pays_exits_from_pool_cash_with_the_books_closed(self):
        """A partial run on the pool is paid from the pool's cash alone: the issuer, a pure custodian, buys no exits.
        The owners' own return is held below most owners' own rate for three months with every owner reviewing (the
        test device, whose owners compare the pool with their mixed returns), so owners ask to exit. What the pool
        pays never exceeds what was requested, the households hold all pool capital, and wealth accounting, backing
        and the issuer's books close every month."""
        for arm in ("M1", "M2"):
            series = ForcedRun(Inputs(), 0.6, FORCED_LONG, arm).run()["series"]
            self.assertGreater(float(series["exit_requested"].sum()), 0.0, arm)
            self.assertGreater(float(series["exit_paid"].sum()), 0.0, arm)
            self.assertTrue(np.all(series["exit_paid"] <= series["exit_requested"] + 1e-15), arm)
            np.testing.assert_allclose(series["backing"][3:], 1.0, atol=1e-9)
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            np.testing.assert_allclose(series["owners_capital"], series["N"], rtol=1e-12, atol=0)
            get = lambda key: series["issuer_" + key]
            np.testing.assert_allclose(get("wallet"), sum(map(get, ("custodian", "indexer", "float", "expenses"))),
                                       atol=1e-15)

    def test_reserves_follow_every_issue_and_redemption(self):
        """Reserves equal P owed after every issue and redemption.

        Example: a joiner's conversion issues P against reserves (the fee leaves to the conversion provider), P paid
        to a non-participant is redeemed, a leaver redeems the rest, an exit paid in P from pool cash moves no
        reserves (the issuer, a pure custodian, buys no shares), and CPI deflates M1's reserves with its P."""
        w = controlled_world()
        owed = lambda: float(w.pcash.sum() + w.pool_cash)
        w.cash[0] = 100.0 * (1 + CONVERSION_FEE)
        w._join(np.arange(10) == 0, np.ones(10))
        w.part[0] = True
        self.assertAlmostEqual(w.reserves, 100.0, places=10)
        w._debit(np.where(np.arange(10) == 0, 50.0, 0.0), np.zeros(10))   # a P payment to person 1, not in P
        w._receive(np.array([1]), np.array([50.0]), np.array([True]))
        self.assertAlmostEqual(w.reserves, 50.0, places=10)
        self.assertAlmostEqual(w.reserves, owed(), places=10)
        w._leave(np.arange(10) == 0)
        self.assertAlmostEqual(w.reserves, owed(), places=10)
        w.pool_cash, w.reserves = 1.0, w.reserves + 1.0                    # P the pool holds
        w._credit_p(np.array([3]), np.array([0.4]))                         # an exit paid in P from pool cash
        w.pool_cash -= 0.4
        self.assertAlmostEqual(w.reserves, owed(), places=10)
        w.economy = replace(w.economy, inflation=0.02 / 12)
        w._deflate()
        self.assertAlmostEqual(w.reserves, owed(), places=12)

    def test_backing_holds_in_every_setup_and_is_untracked_without_an_issuer(self):
        """Reserves equal P owed every month after launch, through routine conversion fees, payments routed in P,
        distress and low adoption; S0 and M0 have no reserve account to check."""
        tiny = Economy(n=100, burn_in=3, months=14)
        setups = (("M1", replace(tiny, routine_conversion=True), 0.6), ("M2", replace(tiny, routing="all", distress=0.02,
                                                                                      distress_start=4), 0.6),
                  ("M1", tiny, 0.05))
        for arm, economy, a0 in setups:
            backing = simulate(Inputs(), a0, economy, arm)["series"]["backing"][economy.burn_in:]
            np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9)
            self.assertTrue(np.isfinite(backing).any())
        for arm in ("S0", "M0"):
            self.assertTrue(np.isnan(simulate(Inputs(), 0.6, tiny, arm)["series"]["backing"]).all())

    def test_owners_keep_backing_at_one_below_zero_real_rates(self):
        """Below a zero real rate the issuer's owners keep backing at 1.

        Example: in M2 at r_out 1%, reserves earn -1% real, so the owners put in the shortfall each month (the
        backing top-up) and backing stays at 1; at r_out 4.4% there is nothing to put in."""
        tiny = Economy(n=100, burn_in=3, months=14)
        for rate, short in ((0.01, True), (0.044, False)):
            series = simulate(replace(Inputs(), rho_H=rate / 12), 0.6, tiny, "M2")["series"]
            income = series["issuer_custodian"] + series["issuer_indexer"] + series["issuer_float"]
            np.testing.assert_allclose(series["backing_topup"], np.maximum(-income, 0.0), atol=1e-15)
            self.assertEqual(bool(series["backing_topup"].max() > 0), short)
            backing = series["backing"][tiny.burn_in:]
            np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9)

    def test_backing_below_one_makes_the_run_unsafe(self):
        """X5: reserves below P owed in any month since launch make the run Against. With full backing the write-off
        clause decides, and without a reserve account the backing clause stays untested. The report gives the lowest
        backing and the owners' backing top-ups."""
        from scripts.run_economy_figures import DOLLARS, persistence
        months = 60
        series = {key: np.ones(months) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                  "cash_to_lend", "interest_collected", "own_margin",
                                                  "owners_capital")}
        series.update(K=np.full(months, 0.1), pool_costs=np.zeros(months), write_off_rate=np.zeros(months),
                      arrears_share=np.zeros(months), backing=np.ones(months), backing_topup=np.full(months, 0.001))
        run = dict(series=series, economy=Economy(n=2, burn_in=0, months=months), arm="M2", rho_p=0.0)
        full = persistence(run, 0.6)
        self.assertIs(full["X"]["X5"], False)
        self.assertEqual(full["detail"]["backing_lowest"], 1.0)
        self.assertAlmostEqual(full["detail"]["backing_topup_usd"], 0.06 * DOLLARS, places=9)
        series["backing"] = np.where(np.arange(months) == 40, 0.99, 1.0)
        short = persistence(run, 0.6)
        self.assertIs(short["X"]["X5"], True)
        self.assertTrue(short["verdict"].startswith("Against CPM"))
        self.assertEqual(short["detail"]["backing_lowest"], 0.99)
        del series["backing"], series["backing_topup"]
        self.assertIs(persistence(run, 0.6)["X"]["X5"], False)
        self.assertIsNone(persistence(run, 0.6)["detail"]["backing_short"])

    def test_stay_test_averages_the_last_twelve_months(self):
        """The stay test reads the issuer's average wallet over the last 12 months.

        Example ($ a person a month, a wallet of $49.12 a year): a one-month loss of $14.50, 10% of $145, leaves the
        12-month average at about $2.88 (a two-month average would read -$3.16). Only a one-month loss above a year's
        wallet records 'issuer would leave', zero counts as staying, there is no reading before the 12th month, and
        the record stays once made."""
        normal = 49.12 / 12

        def run(wallets):
            w = controlled_world()
            return list(map(w._stay_test, wallets)), w.issuer_leaves
        readings, leaves = run([normal] * 11 + [normal - 14.50])
        self.assertTrue(np.isnan(readings[:11]).all())
        self.assertAlmostEqual(readings[11], (49.12 - 14.50) / 12, places=12)
        self.assertFalse(leaves)
        self.assertFalse(run([normal] * 11 + [normal - 49.11])[1])
        self.assertTrue(run([normal] * 11 + [normal - 49.13])[1])
        self.assertFalse(run([0.0] * 12)[1])
        readings, leaves = run([normal] * 11 + [normal - 60.0] + [normal] * 12)
        self.assertAlmostEqual(readings[-1], normal, places=12)
        self.assertTrue(leaves)

    def test_at_zero_real_rates_the_custodian_cannot_cover_its_cost(self):
        """At a zero real rate M2's custodian cannot cover its cost: the issuer is a pure custodian with no stake to
        earn, a declared limit of M2.

        Example ($ a person a year, one model month standing for the year): in M2 at r_out = inflation, reserve
        income and indexation cancel and the custodian pays nothing out. With no cost its wallet is zero and it
        stays; with its cost of 0.24% of the $1,350 of P its wallet is -$3.24 and it records "issuer would leave"."""
        def leaves(cost=0.0):
            w = controlled_world("M2")
            w.economy = replace(w.economy, issuer_cost=cost)
            w.inputs, w.index, w.rho_p = replace(w.inputs, rho_H=0.02), 0.02, 0.0
            w.acc.update(p_all=1350.0, wallet_yield=0.0, float_pool=0.0)
            wallet = w._issuer_books()["wallet"]
            self.assertAlmostEqual(wallet, -cost * 1350.0, places=12)
            list(map(w._stay_test, [wallet] * STAY_MONTHS))
            return w.issuer_leaves
        self.assertFalse(leaves())
        self.assertTrue(leaves(cost=0.0024))

    def test_stay_test_reads_every_month_since_launch(self):
        """From the 12th month after launch the reading is the average complete wallet of the last 12 months, every
        month counted, with or without a pool; before then, and in S0, it is undefined. The issuer is a pure
        custodian whose wallet is never negative beyond rounding, so the record never reads "would leave" at r_out
        4.4%."""
        economy = replace(TINY, n=100, months=14)
        launch = economy.burn_in
        for arm in ("M1", "M2"):
            series = simulate(Inputs(), 0.6, economy, arm)["series"]
            stay, wallet = series["issuer_stay"], series["issuer_wallet"]
            self.assertTrue(np.isnan(stay[:launch + 11]).all())
            self.assertTrue(np.isnan(series["issuer_would_leave"][:launch + 11]).all())
            self.assertTrue(np.all(wallet[launch:] >= -1e-15))
            self.assertFalse(np.nan_to_num(series["issuer_would_leave"]).any())
            for month in range(launch + 11, launch + 14):
                self.assertAlmostEqual(float(stay[month]), float(wallet[month - 11:month + 1].mean()), places=14)
            self.assertTrue(np.isin(series["issuer_would_leave"][launch + 11:], (0.0, 1.0)).all())
        self.assertTrue(np.isnan(simulate(Inputs(), 0.0, economy, "S0")["series"]["issuer_stay"]).all())

    def test_issuer_who_would_leave_makes_the_run_against(self):
        """X6: a negative 12-month reading makes the run Against and names the issuer, with M2's declared limit at
        zero real rates. The report gives the record's first month and the most annual expense the issuer could bear
        (12 times its lowest reading, per person and over the P outstanding)."""
        from scripts.run_economy_figures import DOLLARS, persistence
        months = 60
        series = {key: np.ones(months) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                  "cash_to_lend", "interest_collected", "own_margin",
                                                  "owners_capital")}
        series.update(K=np.full(months, 0.1), pool_costs=np.zeros(months), write_off_rate=np.zeros(months),
                      arrears_share=np.zeros(months), P_out=np.full(months, 0.2))
        read = np.arange(months) >= STAY_MONTHS - 1               # readings from the 12th month after launch
        stay = np.where(read, 0.001, np.nan)
        stay[30] = -0.0005                                        # one negative reading, in month 31 after launch
        series.update(issuer_stay=stay, issuer_would_leave=np.where(read, (np.arange(months) >= 30) * 1.0, np.nan))
        run = lambda arm, rho_p: dict(series=series, economy=Economy(n=2, burn_in=0, months=months), arm=arm,
                                      rho_p=rho_p)
        m2 = persistence(run("M2", 0.0), 0.6)
        self.assertIs(m2["X"]["X6"], True)
        self.assertEqual(m2["verdict"], "Against CPM (the issuer would leave; zero real rates, a declared limit of M2)")
        self.assertEqual(m2["detail"]["issuer_would_leave_from_month"], 31)
        self.assertAlmostEqual(m2["detail"]["issuer_most_expense_usd_a_year"], -0.006 * DOLLARS, places=9)
        self.assertAlmostEqual(m2["detail"]["issuer_most_expense_share_of_P"], -0.03, places=12)
        self.assertEqual(persistence(run("M1", 0.044 / 12), 0.6)["verdict"], "Against CPM (the issuer would leave)")
        series.update(issuer_stay=np.where(read, 0.001, np.nan), issuer_would_leave=np.where(read, 0.0, np.nan))
        self.assertIs(persistence(run("M1", 0.044 / 12), 0.6)["X"]["X6"], False)

    def test_pool_credit_only_when_no_dearer_than_the_card(self):
        """Loan-cost comparison: with a pool coupon above the card APR, the shortfall goes to the card."""
        w = controlled_world()
        funded_pool(w)
        w.holder[0], w.card_apr[0], w.r_g, w.cash[0] = True, 0.01, 0.10, 0.002
        w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
        w.last["receipts"][:] = 1.0
        one_invoice(w, card=False)
        w._settle(1, 30)
        self.assertEqual(int(w.book["pool"].sum()), 0)

    def test_m2_compares_dated_repayments_with_indexation(self):
        """Over a month that crosses a CPI mark, an M2 draw costs (1 + r_g)(1 + index); a near tie goes to the card.
        A card holder's bill is compared with a cash advance, priced here at the example's APR with no fee (at the
        cash APR and its fee the pool would win both cases)."""
        for apr, pool_lends in ((0.00667, False), (0.0068, True)):
            w = controlled_world("M2")
            w.economy = replace(w.economy, inflation=0.02 / 12)
            w.index = w.economy.inflation
            funded_pool(w)
            w.pcash[0] = 0.002
            w.holder[0], w.card_apr[0], w.r_g = True, apr, 0.005
            w.cash_apr[0], w.advance_floor, w.advance_rate = apr, 0.0, 0.0
            w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:] = 1.0
            # The budget expects wages on their jobs' pay dates, so wages in the quiet month would date the draw
            # before the CPI mark. None of the receipts here are wages, so they are due on day 60.
            w.last["wages_paid"][:] = 0.0
            one_invoice(w, card=False)
            w._settle(1, 30)
            self.assertEqual(bool(w.book["pool"].any()), pool_lends)

    def test_late_cancellation_keeps_a_missed_deadline(self):
        """A request withdrawn after its two months stays a failure; one withdrawn in time leaves the base."""
        for later, kept in ((39, 1.0), (37, 0.0)):
            w = _World(Inputs(), 0.6, Economy(n=10, burn_in=0, months=60), "M1")
            w.shares[:] = 0.0
            w.shares[0], w.nav_ps = 1.0, 1.0
            w._track_exits(36, np.arange(10) == 0, np.zeros(10))
            w._track_exits(later, np.zeros(10, bool), np.zeros(10))
            self.assertEqual(float(w.exit_started[36]), kept)

    def test_unfollowed_requests_are_not_certified(self):
        """A W2 request due after the run is not judged: timeliness reads exits whose deadline falls inside the run.
        A request that fails inside the run still fails the clause."""
        from scripts.run_economy_figures import persistence
        series = {key: np.ones(60) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                              "cash_to_lend", "interest_collected", "own_margin",
                                              "owners_capital")}
        series.update(K=np.full(60, 0.1), pool_costs=np.zeros(60), exit_requested=np.zeros(60),
                      exit_paid=np.zeros(60), write_off_rate=np.zeros(60), arrears_share=np.zeros(60))
        exits = dict(started=np.zeros(60), in_time=np.zeros(60))
        exits["started"][58] = 1.0
        report = dict(series=series, economy=Economy(n=2, burn_in=0, months=60), exits=exits)
        self.assertIs(persistence(report, 0.6)["P"]["P3"], True)
        exits["started"][40] = 99.0                      # a failure inside the run outweighs any censored outcome
        self.assertFalse(persistence(report, 0.6)["P"]["P3"])
        exits["in_time"][40] = 99.0                      # paid in time: 99% passes whatever the censored request does
        self.assertTrue(persistence(report, 0.6)["P"]["P3"])

    def test_m0_savings_earn_the_own_rate_plus_the_premium(self):
        """M0's savings part is (supply - control rate) x savings: with a premium of 0, M0 savings earn exactly S0's
        rate."""
        worlds = list(map(controlled_world, ("S0", "M0")))
        worlds[1].part[:] = True
        list(map(lambda w: w.savings.__setitem__(slice(None), 1.0), worlds))
        list(map(lambda w: w._close(0, w.net_wealth(), np.ones(10), np.ones(10)), worlds))
        np.testing.assert_allclose(worlds[0].savings, 1.0 + worlds[0].r_out)
        np.testing.assert_allclose(worlds[1].savings, worlds[0].savings)

    def test_real_defi_supply_rate_follows_the_pinned_curve(self):
        """M0: with no supply from this economy Comet pays its pinned rate; economy-scale supply drives it towards 0."""
        w = controlled_world("M0")
        w.part[:] = True
        w._comet_rates()
        self.assertAlmostEqual(w.p_yield * 365 / DAYS, 0.0727, places=4)   # pinned: 7.27%/yr (365 days) at 91.3% use
        w.pcash[:] = 1.0                                               # one month of spending each, at US scale
        w._comet_rates()
        self.assertLess(w.p_yield * 12, 0.0001)
        self.assertGreater(w.comet_borrow * 365 / DAYS, 0.0149)        # borrow base rate 1.5%/yr (365 days)

    def test_m0_rates_move_with_r_out_from_their_observed_october_levels(self):
        """M0 is the strongest real DeFi, and its rates move with the outside rate one for one from their observed
        October 2026 levels, on the model's common basis, a nominal annual rate credited monthly.

        The 4.05% bill (TB3MS) is a 91-day discount yield: as an effective annual yield credited monthly it is
        4.135%. On chain the SSR was a 3.60% APY to 7 October 2026 16:58:47 UTC and 3.80% after, credited monthly
        3.542% and 3.735%, a time-weighted October mean of 3.694%, so the spread is 0.441 point: USDC earns 3.999% at
        r_out 4.44%, 1.559% at 2% and nothing at 0.2%. Comet USDC on Ethereum borrowed at an October median of 5.31%
        and supplied at 4.40%, each a per-second rate times Comet's 365-day year: credited monthly, 5.3218% and
        4.4081%, so 1.1872 and 0.2736 points over the bill on the same basis, and Comet borrows at 5.6272% at r_out
        4.44%, 3.1872% at 2% and 7.1872% at 6% (supplying at 4.7136%, 2.2736% and 6.2736%), every rate floored at
        zero. The fitted sensitivity reads the lag-3 OLS lines, savings capped at r_out: at 2%, 4.4% and 6%, savings
        0.73%, 4.4% and 6%, borrow 1.88%, 5.72% and 8.28%, supply 0.88%, 4.48% and 6.88%. The pinned and fixed modes
        keep their rates, and an unknown mode is refused."""
        self.assertEqual(Economy().comet, "reserve")
        self.assertAlmostEqual(BILL_MONTHLY, 12 * ((1 - BILL_ANCHOR * 91 / 360) ** (-365 / 91 / 12) - 1), places=15)
        self.assertAlmostEqual(BILL_MONTHLY, 0.041345, places=6)
        self.assertAlmostEqual((1 + monthly_credited(SSR_LOW) / 12) ** 12 - 1, SSR_LOW, places=14)   # compounds back
        self.assertAlmostEqual(monthly_credited(SSR_HIGH), 0.037354, places=6)
        self.assertAlmostEqual(SSR_OCTOBER, (monthly_credited(SSR_LOW) * SSR_CHANGE_DAYS
                                             + monthly_credited(SSR_HIGH) * (31 - SSR_CHANGE_DAYS)) / 31, places=15)
        self.assertAlmostEqual(SSR_CHANGE_DAYS, 6 + (16 + 58 / 60 + 47 / 3600) / 24, places=15)
        self.assertAlmostEqual(SSR_OCTOBER, 0.036935, places=6)
        self.assertAlmostEqual(RESERVE_SPREAD * 12, BILL_MONTHLY - SSR_OCTOBER, places=15)
        self.assertAlmostEqual(RESERVE_SPREAD * 12, 0.00441, places=5)
        self.assertEqual(COMET_SECONDS_PER_YEAR, 31536000)
        self.assertAlmostEqual(per_second_monthly(0.0531), 12 * np.expm1(0.0531 / 12), places=10)   # near continuous
        self.assertAlmostEqual(COMET_BORROW_OCTOBER, per_second_monthly(0.0531), places=15)
        self.assertAlmostEqual(COMET_SUPPLY_OCTOBER, per_second_monthly(0.0440), places=15)
        self.assertAlmostEqual(COMET_BORROW_OCTOBER, 0.053218, places=6)
        self.assertAlmostEqual(COMET_SUPPLY_OCTOBER, 0.044081, places=6)
        self.assertAlmostEqual(COMET_BORROW_SPREAD * 12, COMET_BORROW_OCTOBER - BILL_MONTHLY, places=15)
        self.assertAlmostEqual(COMET_SUPPLY_SPREAD * 12, COMET_SUPPLY_OCTOBER - BILL_MONTHLY, places=15)
        world = lambda r_out, comet="reserve", mode="observed": _World(
            replace(Inputs(), rho_H=r_out / 12), 0.6, Economy(n=10, comet=comet, m0_rates=mode), "M0")
        for r_out, rate, borrow, supply in ((0.0444, 0.03999, 0.056272, 0.047136), (0.02, 0.01559, 0.031872, 0.022736),
                                            (0.06, 0.05559, 0.071872, 0.062736), (0.002, 0.0, 0.013872, 0.004736)):
            w = world(r_out)
            self.assertAlmostEqual(w.p_yield * 12, rate, places=5)
            self.assertAlmostEqual(w.comet_borrow * 12, borrow, places=6)
            self.assertAlmostEqual(w.comet_supply * 12, supply, places=6)
            self.assertEqual((w.p_yield, w.comet_borrow, w.comet_supply), m0_rates(r_out / 12))
        self.assertEqual(m0_rates(-0.02 / 12), (0.0, 0.0, 0.0))                 # every rate floored at zero
        self.assertAlmostEqual(world(0.0444).issuer_keeps * 12, 0.0444 - 0.03999, places=5)   # the Sky spread kept
        self.assertEqual(M0_FITTED, dict(savings=(-0.0279, 1.76), borrow=(-0.0132, 1.60), supply=(-0.0212, 1.50)))
        for r_out, rates in ((0.02, (0.0073, 0.0188, 0.0088)), (0.044, (0.044, 0.0572, 0.0448)),
                             (0.06, (0.06, 0.0828, 0.0688))):
            np.testing.assert_allclose(np.array(m0_rates(r_out / 12, "fitted")) * 12, rates, rtol=0, atol=1e-12)
            w = world(r_out, mode="fitted")
            np.testing.assert_allclose(np.array([w.p_yield, w.comet_borrow, w.comet_supply]) * 12, rates, atol=1e-12)
        self.assertEqual(m0_rates(0.0, "fitted"), (0.0, 0.0, 0.0))
        self.assertEqual(Economy().m0_rates, "observed")
        fixed = world(0.0444, "fixed")
        self.assertEqual(fixed.p_yield, Inputs().rho_H + Inputs().supply_premium)
        self.assertEqual(fixed.comet_borrow, fixed.p_yield + Inputs().borrow_margin)
        with self.assertRaises(ValueError):
            Economy(comet="pinnd")
        with self.assertRaises(ValueError):
            Economy(m0_rates="fited")

    def test_m0_crypto_collateral_is_a_draw_of_holders_at_full_cover(self):
        """M0's crypto collateral: a share of people drawn once on a stream of its own hold it and borrow from Comet
        at full cover, nobody else does, and no other arm reads it. At 10% (SHED 2025, passed explicitly) 100 of
        1,000 people hold it. The default is nobody: collateral lending by Compound III is not run or reported, and
        the option remains for these tests. Every other population draw is the same whatever the share, and a 5%
        share's holders are among the 10% share's."""
        self.assertEqual((CRYPTO_SHARE, Economy().crypto_share), (0.0, 0.0))
        draw = lambda share: build_population(Economy(n=1000, crypto_share=share))
        none, tenth, twentieth = draw(0.0), draw(0.1), draw(0.05)
        self.assertEqual((int(none["crypto"].sum()), int(tenth["crypto"].sum()), int(twentieth["crypto"].sum())),
                         (0, 100, 50))
        self.assertTrue(np.all(tenth["crypto"][twentieth["crypto"]]))
        for key, value in none.items():
            if key != "crypto":
                np.testing.assert_array_equal(value, tenth[key], err_msg=key)
        economy = Economy(n=1000, crypto_share=0.1)
        m0 = _World(Inputs(), 0.6, economy, "M0")
        np.testing.assert_array_equal(m0.cover, tenth["crypto"].astype(float))
        for arm in ("S0", "U", "M1", "M2"):
            self.assertFalse(_World(Inputs(), 0.6, economy, arm).cover.any(), arm)

    def test_the_dealing_replay_prices_m0_comet_credit_for_collateral_holders(self):
        """With M0's crypto collateral holders (set here; none by default), the dealing's buffer replay prices their
        shortfalls as the settlement and the experience replay meet them. A collateral holder using USDC borrows from
        Comet at full cover, at Comet's rate, r_out plus 1.1872 points, and neither fails nor draws an advance, where
        a participant without collateral or card fails; a collateral holder that does not use USDC cannot reach
        Comet. The rule leans against CPM. No other arm has collateral, so no other arm's replay changes."""
        from unittest import mock
        w = controlled_world("M0")
        w.part[:2] = True
        w.cover[[0, 2]] = 1.0
        seen = {}

        def capture(flows, spending, liquid, credit, hold, fail_cost, **options):
            seen.update(credit=credit.copy(), fail=fail_cost.copy(), advance=options.get("advance_rate"))
            return np.zeros(w.n), None
        with mock.patch("cpm_abm.engine.world_dealing.choose_buffer", side_effect=capture):
            w._dealing(1)
        self.assertAlmostEqual(w.comet_borrow, Inputs().rho_H + COMET_BORROW_SPREAD, places=15)
        self.assertEqual(seen["credit"][0], w.comet_borrow)
        self.assertEqual(seen["fail"][0], 0.0)
        self.assertEqual((seen["credit"][1], seen["credit"][2]), (0.0, 0.0))
        self.assertTrue(seen["fail"][1] > 0.0 and seen["fail"][2] > 0.0)
        if seen["advance"] is not None:
            self.assertEqual(seen["advance"][0], 0.0)

    def test_m0_pays_two_legs_of_base_gas_a_payment_whatever_its_value(self):
        """A USDC payment between two M0 participants pays the gas of its two legs on Base, $0.00169 each (growthepie,
        October 2026 mean), $0.00338 a payment whatever its value.

        Example: a $64.40 and a $6,440 card-eligible purchase each cost their payer exactly that, which leaves for
        the validators, outside the economy, and the payees receive the full amounts."""
        w = controlled_world("M0")
        w.part[:], w.holder[:2] = True, True
        w.pcash[0], w.pcash[2] = 2.0, 2.0
        w.ob = dict(buyer=np.array([0, 2]), seller=np.array([1, 3]), amount=np.array([0.01, 1.0]),
                    settle=np.array([30, 30]), card=np.array([True, True]), kind=np.full(2, SERVICE))
        w.holder[2] = True
        w.receivable[[1, 3]], w.payable[[0, 2]] = (0.01, 1.0), (0.01, 1.0)
        w._settle(1, 30)
        self.assertAlmostEqual(GAS_PER_PAYMENT * MONTH_USD, 0.00338, places=15)
        self.assertEqual(GAS_PER_PAYMENT, 2 * GAS_PER_TRANSFER)
        np.testing.assert_allclose(w.acc["gas"][[0, 2]], GAS_PER_PAYMENT, rtol=1e-12)
        np.testing.assert_allclose(w.pcash[[0, 2]], [2.0 - 0.01 - GAS_PER_PAYMENT, 1.0 - GAS_PER_PAYMENT], rtol=1e-12)
        np.testing.assert_allclose(w.pcash[[1, 3]], [0.01, 1.0], rtol=1e-12)
        self.assertAlmostEqual(w.external, -2 * GAS_PER_PAYMENT, places=15)

    def test_usdc_converts_at_no_fee_while_p_pays_the_debit_cap(self):
        """USDC converts to and from dollars at no fee (Coinbase, since 13 Aug 2025), so an M0 joiner's whole working
        balance becomes USDC, a leaver's whole USDC comes back, and the leaving rule's one conversion costs nothing.
        P keeps the debit-cap conversion fee."""
        self.assertEqual(USDC_CONVERSION, 0.0)
        for arm, fee in (("M0", 0.0), ("M1", CONVERSION_FEE)):
            w = controlled_world(arm)
            self.assertEqual(w.conversion, fee)
            w.cash[:2], w.acc["conversion"][:] = 1.0, 0.0
            joined = np.zeros(10, bool)
            joined[:2] = True
            w._join(joined, np.ones(10))
            self.assertAlmostEqual(float(w.pcash[0]), 1.0 / (1 + fee), places=15)
            w._leave(joined)
            self.assertAlmostEqual(float(w.cash[0]), (1 - fee) / (1 + fee), places=15)
            self.assertAlmostEqual(float(w.acc["conversion"][0]), 2 * fee / (1 + fee), places=15)

    def test_theta_counts_only_bridging_coupons(self):
        """Financing share: theta's base is bridging interest, not term-loan interest."""
        w = controlled_world("M1")
        w._add_loans(np.array([0]), True, BRIDGE, np.array([1.0]), 0.01, 0.02, 90)
        w._add_loans(np.array([1]), True, TERM, np.array([5.0]), 0.01, 0.02, 10 ** 9, np.array([12]), 0)
        w.acc.update(bridge_coupons=0.0, coupons=0.0, p_all=0.0, op_cost=0.0)
        w._accrue()
        self.assertAlmostEqual(w.acc["bridge_coupons"], 0.01 / DAYS, places=15)
        self.assertAlmostEqual(w.acc["coupons"], 6 * 0.01 / DAYS, places=15)


    def test_demurrage_is_the_bridging_capital_cost_over_wallet_p_and_p_pays_the_rest(self):
        """The holding charge (demurrage) is the bridging capital cost over wallet P, and P pays the rest of its yield.

        Example (the last cycle's two months stand for the example's year; the reserve rate is 4.4%, c_I 0.24% and
        there is no owners' spread, so owners' alternative is 4.4%): the cycle carried $1,500 of bridging
        principal-time, a capital cost of $66, on $10,000 of wallet P balance-time. Demurrage is c = 66 / 10,000 =
        0.66%, published at the start of the month; P pays y_P = 4.4 - 0.24 - 0.66 = 3.50%; coverage is 1, so a bridge
        drawn this month is sealed at the coupon less its whole capital part, while term loans keep the coupon. A $600
        capital cost would need 6%, held at rho_p - c_I = 4.16%, so P pays 0 and coverage is 416 / 600. With no
        bridging, or no wallet P, c and coverage are zero and P pays 4.16%; U is the same P with c = 0; a pool winding
        down and one without shares charge nothing, so no month publishes a c the pool will not take. In M2 at 2%
        inflation the real rate is 2.4%, c_I a tenth of it, so y_P = 2.4 - 0.24 - 0.66 = 1.50% real and 3.50% with
        indexation, as in M1; at a zero real rate (the declared limit) P pays its indexation alone and demurrage
        covers nothing.

        Demurrage also pays for liquidity kept available. With the cycle's bridging carried at $1,500 for the first
        half of each month and none for the second (so its $1,500 of principal-time) and $2,000 of pool cash held
        ready, the peak bridging need is $1,500 and the standby is $1,500 held for half of each month, $1,500 of
        cash-time over the cycle, whose capital cost is the alternative less what idle cash earns, 4.4 - 4.16 = 0.24
        point, $3.60: c rises by exactly that over the wallet, 3.60 / 10,000, to 0.696%, and coverage stays 1. With
        $500 held ready the standby is $500 for half of each month, $500 of cash-time, and c rises by $1.20 over the
        wallet. U, with no demurrage, takes none of it."""
        def terms(cost=66.0, wallet=10000.0, arm="M1", inflation=0.0, winding=False, shares=True,
                  ready=0.0):
            economy = Economy(n=10, burn_in=10, months=1, inflation=inflation, issuer_cost=0.0024, owner_spread=0.0)
            w = _World(replace(Inputs(), rho_H=0.044), 0.6, economy, arm)
            if shares:
                funded_pool(w, 1.0)
            w.launched, w.winding = True, winding
            carried = np.where(np.arange(DAYS) < DAYS // 2, 1500.0, 0.0) if cost == 66.0 else np.zeros(DAYS)
            month = entry(capital_cost=cost / 2, wallet=wallet / 2, bridging=carried, ready=np.full(DAYS, ready))
            w.window = [dict(month), dict(month)]                     # the last cycle, two months
            w._cycle_terms(11)
            return w
        w = terms()
        self.assertAlmostEqual(w.p_net, 0.0416, places=15)
        self.assertAlmostEqual(w.c, 0.0066, places=15)
        self.assertAlmostEqual(w.p_yield, 0.035, places=15)
        self.assertAlmostEqual(w.c * 10000.0, 66.0, places=10)        # demurrage pays the whole capital cost
        self.assertEqual(w.coverage, 1.0)
        self.assertAlmostEqual(w.r_g, 0.044 + w.inputs.o, places=15)
        self.assertAlmostEqual(w.r_b, w.r_g - 0.044, places=15)
        self.assertEqual(w.r_term, w.r_g)                              # term loans keep the full coupon
        w = terms(cost=600.0)
        self.assertAlmostEqual(w.c, 0.0416, places=15)                 # held at rho_p - c_I
        self.assertAlmostEqual(w.p_yield, 0.0, places=15)
        self.assertAlmostEqual(w.coverage, 416.0 / 600.0, places=15)
        self.assertAlmostEqual(w.r_b, w.r_g - 416.0 / 600.0 * 0.044, places=15)
        for w in (terms(cost=0.0), terms(wallet=0.0), terms(arm="U"), terms(winding=True),
                  terms(shares=False)):
            self.assertEqual((w.c, w.coverage, w.r_b), (0.0, 0.0, w.r_g))
            self.assertAlmostEqual(w.p_yield, 0.0416, places=15)
        w = terms(arm="M2", inflation=0.02)
        self.assertAlmostEqual(w.s_issuer, 0.1, places=15)
        self.assertAlmostEqual(w.p_net, 0.0216, places=15)
        self.assertAlmostEqual(w.c, 0.0066, places=15)
        self.assertAlmostEqual(w.p_yield - w.index, 0.015, places=15)
        self.assertAlmostEqual(w.p_yield, 0.035, places=15)
        w = terms(arm="M2", inflation=0.044)
        self.assertEqual((w.s_issuer, w.p_net, w.c, w.coverage), (1.0, 0.0, 0.0, 0.0))
        self.assertAlmostEqual(w.p_yield, 0.044, places=15)            # its indexation alone
        alternative = 0.044
        w = terms(ready=2000.0)
        self.assertEqual((w.peak, w.standby), (1500.0, 750.0))         # the standby a month over the cycle
        self.assertAlmostEqual((alternative - w.p_net) * 1500.0, 3.60, places=12)
        self.assertAlmostEqual(w.c - terms().c, (alternative - w.p_net) * 1500.0 / 10000.0, places=15)
        self.assertAlmostEqual(w.c, 0.00696, places=15)
        self.assertEqual(w.coverage, 1.0)
        w = terms(ready=500.0)
        self.assertEqual(w.standby, 250.0)
        self.assertAlmostEqual(w.c - terms().c, (alternative - w.p_net) * 500.0 / 10000.0, places=15)
        self.assertEqual(terms(arm="U", ready=2000.0).c, 0.0)


    def test_deposit_part_of_spare_money_stays_in_cash_only_when_it_pays_more(self):
        """Where idle money sits: the money market part is saved at rho_H; the deposit part stays as cash only if the
        cash pays at least what deposits pay (ties stay), else it is saved at the deposit rate, so the savings earn
        their own mix's rate. For P the rule reads its published yield, y_P net of demurrage (plus M2's indexation):
        the world's own at r_out 4.44% is 4.20% before demurrage, and 4.10% after a 0.1-point demurrage still beats
        the 0.41% deposit rate, so the deposit part stays in P; P paying nothing (the declared limit's real yield) or
        bank money does not."""
        def place(arm, p_yield=None):
            w = controlled_world(arm)
            w.part[0] = arm != "S0"
            w.pcash[0], w.cash[0] = (0.0, 10.0) if arm == "S0" else (10.0, 0.0)   # each arm's own cash
            w.mm_share[:] = 0.2
            if p_yield is not None:
                w.p_yield = p_yield
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            w._dealing(1)                                   # no pool yet, no flows: no buffer, the whole 10 is spare
            return w.pcash[0] + w.cash[0], w.savings[0], w.saving_rate[0]
        # The deposit rate follows r_out: 0.41% a year at r_out 4.44%.
        deposit = controlled_world().deposit_rate
        self.assertAlmostEqual(controlled_world("M1").p_yield * 12, 0.0444 - 0.0024, places=15)
        for arm, p_yield in (("M1", None), ("M1", (0.0444 - 0.0024 - 0.001) / 12), ("M1", deposit),
                             ("M2", 0.02 / 12), ("U", None)):
            held, saved, rate = place(arm, p_yield)         # a tie stays in P too
            self.assertAlmostEqual(held, 8.0, places=12)    # the deposit part stays in P
            self.assertAlmostEqual(saved, 2.0, places=12)   # the money market part is saved at rho_H
            self.assertEqual(rate, Inputs().rho_H)
        for arm, p_yield in (("M1", 0.0), ("M2", deposit - 1e-6), ("S0", None)):
            held, saved, rate = place(arm, p_yield)
            self.assertAlmostEqual(held, 0.0, places=12)
            self.assertAlmostEqual(saved, 10.0, places=12)
            self.assertAlmostEqual(rate, 0.2 * Inputs().rho_H + 0.8 * deposit, places=15)

    def test_only_the_money_market_part_goes_to_the_pool_when_it_beats_r_out(self):
        """Only the money-market part of spare money buys pool shares, and only when the pool's quote beats the
        household's own outside rate (paper/cpm.tex, section "Entry and exit").

        Example: a household outside P with $1,000 spare, 16.72% of its savings in money-market funds (the 50th to
        90th percentiles). Its own outside rate is r_out 4.44% plus the owners' 0.25 point, 4.69%. With the pool
        quoting 4.8%, its $167 money-market part buys shares (less the conversion fee) and its $833 deposit part is
        saved at the deposit rate; holding a buffer forgoes the mix with that part at 4.8%. At 4.6%, below its own
        rate, nothing goes to the pool, and all $1,000 is saved at the mix's rate."""
        rho, share, spare = Inputs().rho_H, 0.1672, 1000 / MONTH_USD
        for quote, bought in ((0.048 / 12, True), (0.046 / 12, False)):
            w = controlled_world()
            w.cash[0], w.mm_share[:] = spare, share
            w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 0.0, 1.0, 100.0, quote, True   # N* does not bind
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            w._dealing(1)
            mobile = share * spare
            self.assertAlmostEqual(float(w.shares[0]), mobile / (1 + CONVERSION_FEE) if bought else 0.0, places=15)
            self.assertAlmostEqual(float(w.savings[0]), spare - mobile if bought else spare, places=15)
            # The deposit rate follows r_out: 0.41% a year at r_out 4.44%.
            self.assertAlmostEqual(float(w.saving_rate[0]),
                                   w.deposit_rate if bought else share * rho + (1 - share) * w.deposit_rate, places=15)
            self.assertAlmostEqual(float(w.acc["alternative"][0]),
                                   float(w.r_out[0]) + (share * (quote - rho) if bought else 0.0), places=15)

    def test_the_pool_track_record_is_its_capital_weighted_realised_return(self):
        """The pool's track record, which entry reads under ``entry_reads`` "realised", is its capital-weighted
        realised return.

        Example: monthly returns of 0.004 and 0.002 on pool capital of 100 and 300 after their dealings give
        (0.4 + 0.6) / 400 = 0.0025. A month without capital or without a finite return does not count, so a pool with
        no such month has no track record (NaN)."""
        w = controlled_world()
        self.assertTrue(np.isnan(w._track_record(3)))                        # no month with capital
        w.held_path[0, :2] = 50.0                                            # 100 across two owners
        w.held_path[1, 0] = 300.0
        w.r_owners[0], w.r_owners[1] = 0.004, 0.002
        w.r_owners[2] = 0.05                                                 # a month without capital: not counted
        self.assertAlmostEqual(w._track_record(3), 0.0025, places=15)
        self.assertAlmostEqual(w._track_record(1), 0.004, places=15)         # only closed months before the dealing
        w.r_owners[:2] = np.nan                                              # capital without a finite return
        self.assertTrue(np.isnan(w._track_record(3)))
        self.assertTrue(np.isnan(w._track_record(0)))                        # the first dealing reads nothing

    def test_entry_reading_the_track_record_reads_the_quote_at_launch(self):
        """Under ``entry_reads`` "realised" the launch dealing has no track record, so entry reads the quote, as the
        default rule does: in the test device whose pool forms, capital forms at launch and every record through the
        launch dealing is the default rule's bit for bit."""
        economy = replace(TINY, n=60, months=1)
        runs = {reads: PooledWorld(Inputs(), 1.0, replace(economy, entry_reads=reads), "M1")
                for reads in ("quote", "realised")}
        for world in runs.values():
            world.run()
        launch = economy.burn_in
        self.assertGreater(float(runs["quote"].held_path[launch].sum()), 0.0)
        np.testing.assert_array_equal(runs["realised"].held_path[:launch + 1], runs["quote"].held_path[:launch + 1])
        with self.assertRaises(ValueError):
            replace(economy, entry_reads="track")

    def test_entry_reading_a_poor_track_record_accepts_no_offer(self):
        """Under ``entry_reads`` "realised" a saver offers nothing to a pool whose track record is below its own rate.

        Example: the pool quotes 4.8% a year, above the household's own 4.69%, so under the default rule its
        money-market part buys shares. Under "realised" the same state with a track record of 3% a year (last month's
        return on $100 of other owners' capital) buys none, and a track record of 4.8% buys as the quote does."""
        share, spare = 0.1672, 1000 / MONTH_USD
        for reads, record, bought in (("quote", 0.03 / 12, True), ("realised", 0.03 / 12, False),
                                      ("realised", 0.048 / 12, True)):
            w = controlled_world()
            w.economy = replace(w.economy, entry_reads=reads)
            w.cash[0], w.mm_share[:] = spare, share
            w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 0.0, 1.0, 100.0, 0.048 / 12, True   # N* does not bind
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            w.held_path[0, 1], w.r_owners[0] = 100.0 / MONTH_USD, record          # the pool's last closed month
            w._dealing(1)
            mobile = share * spare
            self.assertAlmostEqual(float(w.shares[0]), mobile / (1 + CONVERSION_FEE) if bought else 0.0, places=15)
            self.assertAlmostEqual(float(w.savings[0]), spare - mobile if bought else spare, places=15)

    def test_entry_by_the_leaving_rule_disperses_the_track_record_reading(self):
        """Under ``entry_reads`` "leaving_rule" each saver reads the track record with the leaving rule's own
        dispersion.

        Example: $167.20 of money-market money at hand and a track record of 3% a year against the household's own
        4.69% give a gap of -$0.2355 a month. With the rule's scale (1e-4 of its monthly spending) the saver offers
        with probability logistic(gap / scale), and it buys exactly when the month's draw on the reading's own stream
        is at least the leaving rule's probability at that gap. With no noise it never buys at 3% and always at 4.8%,
        the "realised" reading, and a run with no noise is that reading's bit for bit."""
        from cpm_abm.economy_abm import logistic
        share, spare = 0.1672, 1000 / MONTH_USD

        def dealt(record, noise):
            w = controlled_world()
            w.economy = replace(w.economy, entry_reads="leaving_rule", leave_noise=noise)
            w.cash[0], w.mm_share[:] = spare, share
            w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 0.0, 1.0, 100.0, 0.048 / 12, True
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            w.held_path[0, 1], w.r_owners[0] = 100.0 / MONTH_USD, record
            own = float(w._owners_alternative_nominal()[0])
            w._dealing(1)
            return w, own

        for record, bought in ((0.03 / 12, False), (0.048 / 12, True)):
            w, _ = dealt(record, 0.0)
            self.assertEqual(bool(w.shares[0] > 0), bought)
        w, own = dealt(0.03 / 12, 1.0)
        gap = (0.03 / 12 - own) * share * spare
        self.assertAlmostEqual(gap * MONTH_USD, (0.03 / 12 - own) * 167.2, places=12)
        scale = w.inputs.noise * float(w.spending[0])
        chance = float(logistic(gap / scale))
        self.assertTrue(0.0 < chance < 0.5)
        draw = np.random.default_rng(np.random.SeedSequence([w.economy.seed, 37, 1])).random(w.n)[0]
        self.assertAlmostEqual(1.0 - float(w._leave_chance(np.full(w.n, gap), 0.0)[0]), chance, places=12)
        self.assertEqual(bool(w.shares[0] > 0), bool(draw >= 1.0 - chance))
        np.testing.assert_array_equal(w._enters(1, np.zeros(w.n)),
                                      np.random.default_rng(np.random.SeedSequence([w.economy.seed, 37, 1])).random(w.n)
                                      >= 0.5)
        economy = replace(TINY, n=60, months=4, leave_noise=0.0)
        runs = [PooledWorld(Inputs(), 1.0, replace(economy, entry_reads=reads), "M1") for reads in
                ("realised", "leaving_rule")]
        for world in runs:
            world.run()
        self.assertGreater(float(runs[0].held_path.sum()), 0.0)
        np.testing.assert_array_equal(runs[1].held_path, runs[0].held_path)
        np.testing.assert_array_equal(runs[1].wealth_path, runs[0].wealth_path)

    def test_with_no_noise_the_leaving_rule_reading_equals_realised_entry_at_the_tie(self):
        """With no noise the leaving-rule reading uses the realised comparison itself, so the two agree at a tie.

        Example: an own alternative of 0.004 a month and a track record of 0.004 - RATE_TIE. Realised entry compares
        record >= alternative - RATE_TIE, which holds. The dollar gap (record - alternative + RATE_TIE) x money at
        hand is negative by rounding, so reading its sign would refuse the offer; both readings buy."""
        from cpm_abm.economy_abm import RATE_TIE
        alternative = 0.004
        record = alternative - RATE_TIE
        self.assertTrue(record >= alternative - RATE_TIE)
        self.assertFalse(record - alternative + RATE_TIE >= 0)     # the rounding a sign test would read
        share, spare = 0.1672, 1000 / MONTH_USD
        bought = {}
        for reads in ("realised", "leaving_rule"):
            w = controlled_world()
            w.economy = replace(w.economy, entry_reads=reads, leave_noise=0.0)
            w._owners_alternative_nominal = lambda w=w: np.full(w.n, alternative)
            w.cash[0], w.mm_share[:] = spare, share
            w.pool_cash, w.nav_ps, w.Q, w.R_hat, w.launched = 0.0, 1.0, 100.0, 0.048 / 12, True
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            w.held_path[0, 1], w.r_owners[0] = 100.0 / MONTH_USD, record
            self.assertEqual(w.index, 0.0)
            w._dealing(1)
            bought[reads] = float(w.shares[0])
        self.assertGreater(bought["realised"], 0.0)
        self.assertEqual(bought["leaving_rule"], bought["realised"])

    def test_owners_exit_when_their_own_return_falls_below_rho_h_and_the_spread(self):
        """Each owner reads its own realised return against its own outside rate, rho_H plus the owners' spread.

        Example: an owner whose own mix earns about 1% files to exit when its own realised return is 3.9% a year
        against rho_H 4.44% plus the owners' 0.25 point. A month at 5.7% brings its return since buying to 4.8%, so
        it no longer wants out and its request lapses. The quote does not move an exit: it is 6% throughout."""
        w = controlled_world()
        reviewing(w)                                                 # it reviews each month, without noise
        w.shares[0], w.nav_ps, w.pool_cash, w.Q, w.had_owners, w.launched = 1.0, 1.0, 0.0, 10.0, True, True
        w.r_out[:] = 0.0105 / 12                                     # the 50th to 90th mix, which is not the comparison
        w.R_hat = 0.06 / 12
        closed(w, 0, 0.039 / 12)
        w._dealing(1)
        self.assertEqual(int(w.exit_start[0]), 1)
        closed(w, 1, 0.057 / 12)
        w._dealing(2)
        self.assertEqual(int(w.exit_start[0]), -1)
        self.assertAlmostEqual(float(w.shares[0]), 1.0, places=15)


    def test_demurrage_coverage_and_p_yield_follow_the_last_cycle_every_month(self):
        """Every month's demurrage, coverage, bridging rate and P's yield follow their formulas on the records of the
        last two months, the cycle the terms read (the launch plan observes no bridging or wallet P). c is the cycle's
        capital cost of the liquidity kept available, bridging and the standby, over its wallet P balance-time, at
        most rho_p - c_I; coverage is c times that wallet over the cost; r_b is the coupon less coverage times owners'
        alternative; P's yield is rho_p - c_I - c plus M2's indexation; and the demurrage taken is c on the month's
        wallet P while the pool has shares. At the default rates c is far below its bound, so coverage is 1 whenever
        the cycle bridged. Where the issuer's cost of P is within half a percent of the reserve rate the bound binds:
        P pays nothing and covers only part of the cost. Wealth accounting and backing stay exact (the test device,
        whose pool forms)."""
        economy = replace(TINY, n=100, months=12)
        rho = {"M1": Inputs().rho_H, "M2": Inputs().rho_H - economy.inflation}
        for arm, bound in (("M1", False), ("M2", False), ("M1", True), ("M2", True)):
            w = replace(economy, issuer_cost=0.995 * rho[arm]) if bound else economy
            world = PooledWorld(Inputs(), 0.6, w, arm)
            series = world.run()["series"]
            launch = w.burn_in
            month = lambda key: np.r_[0.0, series[key][launch:-1]]      # each month's entry, the plan's first
            cycle = lambda key: (month(key) + np.r_[0.0, month(key)[:-1]])[1:]   # the last two, from launch + 1
            cost, wallet = map(cycle, ("bridge_capital_cost", "p_bt"))
            cost = cost + 2 * series["standby_cost"][launch + 1:]          # the standby's, a month over two months
            c = np.minimum(np.divide(cost, wallet, out=np.zeros(cost.size), where=wallet > 0), world.p_net)
            # c is published only while the pool takes demurrage. Where the bound binds, the pool's first months earn
            # less than owners' own rates, every owner files (each reads its own realised return) and the pool winds
            # down. Coverage is published with the terms, from the c published then, so the month whose dealing
            # begins the wind-down keeps it on record although its c is not taken.
            published = np.where(series["service"][launch:-1] > 0, c, 0.0)
            c = np.where(series["service"][launch + 1:] > 0, c, 0.0)
            np.testing.assert_allclose(series["c"][launch + 1:], c, rtol=1e-9, atol=1e-18)
            coverage = np.where(cost > 0, np.minimum(1.0, published * wallet / np.where(cost > 0, cost, 1.0)), 0.0)
            np.testing.assert_allclose(series["coverage"][launch + 1:], coverage, rtol=1e-9, atol=1e-15)
            alternative = max(world.rho_p, 0.0) + w.owner_spread
            np.testing.assert_allclose(series["r_b"], series["r_g"] - series["coverage"] * alternative, rtol=0,
                                       atol=1e-18)
            np.testing.assert_allclose(series["p_yield"][launch:], world.index + world.p_net - series["c"][launch:],
                                       rtol=0, atol=1e-18)
            held = series["N"] > 0
            np.testing.assert_allclose(series["charges"][held], (series["c"] * series["p_bt"])[held], rtol=1e-12,
                                       atol=1e-18)
            np.testing.assert_allclose(series["wallet_yield"][launch:], world.p_net * series["p_bt"][launch:],
                                       rtol=1e-12, atol=1e-18)
            self.assertTrue(np.all(series["c"] <= world.p_net))
            self.assertEqual(float(np.nanmax(series["s_issuer"])), world.s_issuer)
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            backing = series["backing"][launch:]
            np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9)
            bridged = cost > 0
            self.assertTrue(bridged.any(), arm)
            if bound:
                self.assertTrue(np.any(series["c"][launch + 1:][bridged] == world.p_net), arm)
                self.assertTrue(np.any(series["coverage"][launch + 1:][bridged] < 1.0), arm)
            else:
                self.assertTrue(np.all(series["c"][launch + 1:][bridged] < world.p_net), arm)
                np.testing.assert_allclose(series["coverage"][launch + 1:][bridged], 1.0, rtol=0, atol=1e-15)

    def test_loss_is_learned_by_product_over_lagged_exposure(self):
        """Each product's coupon carries its own losses over the principal-time carried at least three months ago.

        Exposure from the last three months has not had time to show its losses, so it cannot dilute them; once a
        month is old enough it counts.
        """
        w = controlled_world()
        w.launched = True
        w.loss_net = np.array([0.01, 0.10])
        w.exposure = np.array([[1.0, 2.0], [9.0, 9.0], [9.0, 9.0], [9.0, 9.0]])
        w._cycle_terms(4)
        base = w.rho_p + w.economy.owner_spread + w.inputs.o   # owners' alternative and o
        self.assertAlmostEqual(w.r_g, base + 0.01, places=15)
        self.assertAlmostEqual(w.r_term, base + 0.05, places=15)
        w.exposure = np.vstack([w.exposure, [0.0, 0.0]])
        w._cycle_terms(5)
        self.assertAlmostEqual(w.r_g, base + 0.01 / 10.0, places=15)
        self.assertAlmostEqual(w.r_term, base + 0.10 / 11.0, places=15)

    def test_term_losses_and_exposure_are_reported_by_year_of_life(self):
        """A term loan's exposure counts in its year of life, and a write-off in the year it first missed a payment."""
        w = controlled_world()
        w.this_month = 14
        w._add_loans(np.array([0]), True, TERM, np.array([2.0]), 0.005, 0.02, 10 ** 9, np.array([24]), 0)
        w._accrue()
        np.testing.assert_allclose(w.acc["exposure"], [0.0, 2.0 / DAYS])
        np.testing.assert_allclose(w.acc["age_exposure"], [0.0, 2.0 / DAYS, 0.0, 0.0, 0.0])
        owed = float(w.book["principal"][0] + w.book["interest"][0])
        w.book["since"][0] = 13 * DAYS                       # first missed payment in month 13, its second year
        w._write_off(13 * DAYS + 90)
        np.testing.assert_allclose(w.acc["age_loss"], [0.0, owed, 0.0, 0.0, 0.0])

    def test_write_offs_and_recoveries_are_learned_by_product(self):
        """A written-off bridge adds to the bridging loss only; a later payment on it is that product's recovery."""
        w = controlled_world()
        w._add_loans(np.array([0, 1]), True, np.array([BRIDGE, TERM]), np.array([0.5, 2.0]), 0.005, 0.02,
                     np.array([10, 10 ** 9]), np.array([0, 24]), 0)
        w._write_off(100)
        np.testing.assert_allclose(w.acc["lost"], [0.5, 0.0])
        w.part[0], w.pcash[0] = True, 1.0
        w._pay(np.array([0]), np.array([0.2]), np.full(10, 1.0))
        np.testing.assert_allclose(w.acc["lost"], [0.3, 0.0])
        self.assertAlmostEqual(w.acc["recovered"], 0.2)

    def test_pool_loans_are_recorded_by_product_and_loan_year(self):
        """Pool loans are recorded by product and by the loan year in which they were made.

        Example, in a world launched at month 10: a pool bridge of 0.5 made in month 12 (loan year 1) at 1% a month,
        a term loan of 2.0 made in month 23 (loan year 2) at 0.5% and one of 1.0 made in month 80, counted in the
        last band. A day's accrual credits each its coupon less the operating cost o it carries, with its
        principal-time; written off, the bridge takes its principal and interest from its band and accrues nothing
        more, and a payment of 0.2 on it comes back as recovery. The record adds up to the books R reads."""
        w = controlled_world()
        o, size = w.inputs.o, (2, LOAN_YEARS)
        w.acc.update(vintage_income=np.zeros(size), vintage_exposure=np.zeros(size))
        w.this_month = 85                                    # every loan made by now
        w._add_loans(np.array([0]), True, BRIDGE, np.array([0.5]), 0.01, 0.02, 20 * DAYS, None, 12)
        w._add_loans(np.array([1, 2]), True, TERM, np.array([2.0, 1.0]), 0.005, 0.02, BIG, np.array([24, 24]),
                     np.array([23, 80]))
        books = lambda: w.acc["coupons"] - w.acc["op_cost"] - w.acc["written_off"] + w.acc["recovered"]
        before = books()
        w._accrue()
        day = np.zeros(size)
        day[0, 0], day[1, 1], day[1, 4] = 0.5 * (0.01 - o) / DAYS, 2.0 * (0.005 - o) / DAYS, 1.0 * (0.005 - o) / DAYS
        np.testing.assert_allclose(w.acc["vintage_income"], day, rtol=1e-12, atol=1e-15)
        carried = np.zeros(size)
        carried[0, 0], carried[1, 1], carried[1, 4] = 0.5 / DAYS, 2.0 / DAYS, 1.0 / DAYS
        np.testing.assert_allclose(w.acc["vintage_exposure"], carried, rtol=1e-12)
        owed = float(w.book["principal"][0] + w.book["interest"][0])
        w._write_off(20 * DAYS + 90)
        np.testing.assert_array_equal(w.book["carried"], [False, True, True])   # the bridge only
        w._accrue()                                                               # the bridge accrues nothing more
        w.part[0], w.pcash[0] = True, 1.0
        w._pay(np.array([0]), np.array([0.2]), np.full(10, 1.0))
        self.assertAlmostEqual(w.acc["recovered"], 0.2)
        expected = 2 * day
        expected[0, 0] = day[0, 0] - owed + 0.2                                   # -0.3 less a day's o on 0.5
        np.testing.assert_allclose(w.acc["vintage_income"], expected, rtol=1e-12, atol=1e-15)
        carried[1] *= 2
        np.testing.assert_allclose(w.acc["vintage_exposure"], carried, rtol=1e-12)
        self.assertAlmostEqual(float(w.acc["vintage_income"].sum()), books() - before, places=14)

    def test_short_card_holder_puts_the_purchase_on_the_card(self):
        """A card holder whose own money cannot pay a card purchase from a participant uses the card, free until the
        statement, and borrows nothing. One whose P can pay it pays in P with one transfer's gas, which goes to
        validators outside the economy: a P payment carries no provider fee and no rail charge."""
        inputs = Inputs()
        for owned, on_card in ((0.5, True), (1.002, False)):
            w = controlled_world()
            funded_pool(w)
            w.holder[0], w.card_apr[0], w.r_g, w.pcash[0] = True, 0.01, 0.005, owned
            w.r_b = w.r_g   # no demurrage coverage here: a bridge is sealed at the coupon
            w.last["receipts"][:] = 1.0
            w.acc["gas_paid"] = 0.0
            one_invoice(w)
            w._settle(1, 30)
            self.assertFalse(bool(w.book["pool"].any()))
            self.assertAlmostEqual(float(w.card_unbilled[0]), 1.0 if on_card else 0.0)
            # The card fee leaves, or the P payment's gas.
            self.assertAlmostEqual(w.external, -inputs.f_card if on_card else -GAS_PER_P_PAYMENT, places=15)
            self.assertAlmostEqual(float(w.acc["rewards"][0]), CARD_REWARDS if on_card else 0.0, places=15)
            self.assertAlmostEqual(w.acc["gas_paid"], 0.0 if on_card else GAS_PER_P_PAYMENT, places=15)

    def test_written_off_loan_keeps_accruing_legal_interest(self):
        """Impairment changes carrying value, not legal principal or rate; the extra liability is valuation."""
        w = controlled_world()
        w._add_loans(np.array([0]), True, BRIDGE, np.array([1.0]), 0.01, 0.02, 0)
        w._write_off(90)
        w.valuation = 0.0
        w._accrue()
        self.assertAlmostEqual(float(w.book["interest"][0]), 0.01 / DAYS)
        self.assertAlmostEqual(w.valuation, -0.01 / DAYS)

    def test_report_does_not_certify_without_evidence(self):
        """Without exit cohorts or credit quality, those tests are undefined and the verdict is not Persistent."""
        from scripts.run_economy_figures import persistence
        series = {key: np.ones(60) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                              "cash_to_lend", "interest_collected", "own_margin",
                                              "owners_capital")}
        series.update(K=np.full(60, 0.1), pool_costs=np.zeros(60), exit_requested=np.zeros(60),
                      exit_paid=np.zeros(60), write_off_rate=np.full(60, np.nan), arrears_share=np.full(60, np.nan))
        verdict = persistence(dict(series=series, economy=Economy(n=2, burn_in=0, months=60)), 0.6)
        self.assertIsNone(verdict["P"]["P3"])
        self.assertIsNone(verdict["P"]["P5"])
        self.assertNotIn("Persistent", verdict["verdict"])

    def test_use_and_collapse_follow_the_decided_tolerances(self):
        """The use and collapse tests and their tolerances, with the registered tests reported beside them.

        Example: windows are months 13-36 and 37-60, and participation is given as launch, first window, second
        window. 0.80, 0.79, 0.77: use holds (0.77 is within 0.05 of both) and nothing collapses, where the registered
        tests read no use and a collapse (0.77 is below 0.80). 0.60, 0.47, 0.45: use fails (below 0.55), no collapse
        (not below 0.30). 0.60, 0.30, 0.20: use fails and collapse fires (below half the launch share). Pool capital
        at 0.4 of the first window's: collapse. A second-window month with capital and no service, a wind-down:
        collapse."""
        from scripts.run_economy_figures import persistence

        def read(launch, first, second, capital=1.0, serving=True):
            series = {key: np.ones(60) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                  "cash_to_lend", "interest_collected", "own_margin",
                                                  "owners_capital")}
            series.update(K=np.full(60, 0.1), pool_costs=np.zeros(60), exit_requested=np.zeros(60),
                          exit_paid=np.zeros(60), write_off_rate=np.full(60, np.nan), arrears_share=np.full(60, np.nan))
            series["A"] = np.r_[np.full(12, launch), np.full(24, first), np.full(24, second)]
            series["N"] = np.r_[np.ones(36), np.full(24, capital)]
            if not serving:
                series["service"][40] = 0.0
            return persistence(dict(series=series, economy=Economy(n=2, burn_in=0, months=60)), launch)

        high = read(0.80, 0.79, 0.77)
        self.assertIs(high["P"]["P1"], True)
        self.assertIs(high["X"]["X1"], False)
        self.assertEqual(high["detail"]["registered_tests"], dict(P1=False, X1=True))
        drift = read(0.60, 0.47, 0.45)
        self.assertIs(drift["P"]["P1"], False)
        self.assertIs(drift["X"]["X1"], False)
        fall = read(0.60, 0.30, 0.20)
        self.assertIs(fall["P"]["P1"], False)
        self.assertIs(fall["X"]["X1"], True)
        self.assertIs(read(0.60, 0.60, 0.60)["X"]["X1"], False)
        self.assertIs(read(0.60, 0.60, 0.60, capital=0.4)["X"]["X1"], True)
        self.assertIs(read(0.60, 0.60, 0.60, capital=0.4)["detail"]["capital_halved"], True)
        self.assertIs(read(0.60, 0.60, 0.60, serving=False)["X"]["X1"], True)
        self.assertIs(read(0.60, 0.60, 0.60, serving=False)["detail"]["wound_down"], True)

    def test_arms_share_random_numbers_until_launch(self):
        """S0 and M1 are identical through the burn-in; S0 never opens a pool."""
        s0 = simulate(Inputs(), 0.6, TINY, "S0")
        m1 = simulate(Inputs(), 0.6, TINY, "M1")
        np.testing.assert_array_equal(s0["wealth"][:TINY.burn_in + 1], m1["wealth"][:TINY.burn_in + 1])
        self.assertEqual(float(s0["series"]["service"].max()), 0.0)
        self.assertEqual(float(s0["series"]["N"].max()), 0.0)

    def test_allocation_pays_each_owner_in_priority_order(self):
        """allocate pays the first-priority claim first and never exceeds the owner's budget."""
        owner = np.array([0, 0, 1, 0])
        cost = np.array([2.0, 1.0, 5.0, 4.0])
        priority = np.array([2, 0, 0, 1])
        paid = allocate(owner, cost, (priority,), np.array([4.0, 3.0]))
        np.testing.assert_allclose(paid, [0.0, 1.0, 3.0, 3.0])

    def test_dual_balances_convert_only_the_shortfall(self):
        """A P payment uses P first and converts only the missing part of E, paying the conversion fee on it."""
        world = tiny_world()
        world.cash[:], world.pcash[:] = 1.0, 0.0
        world.pcash[0] = 0.3
        world._debit(np.where(np.arange(TINY.n) == 0, 0.5, 0.0), np.zeros(TINY.n))
        self.assertAlmostEqual(float(world.pcash[0]), 0.0)
        self.assertAlmostEqual(float(world.cash[0]), 1.0 - 0.2 * (1 + CONVERSION_FEE))
        self.assertAlmostEqual(float(world.acc["conversion"][0]), 0.2 * CONVERSION_FEE)

    def test_term_loans_repay_equal_instalments_on_billing_dates(self):
        """One instalment of principal falls due on the first billing date on or after each month."""
        world = tiny_world()
        who = np.array([5])
        world.cash[5] = 10.0
        world._add_loans(who, False, TERM, np.array([1.2]), 0.01, 0.01, 10 ** 9, np.array([12]), 0)
        cycle, phase = world.pop["cycles"][5], world.pop["phases"][5]
        first = DAYS + (phase - DAYS) % cycle
        list(map(world._instalments, range(first)))
        self.assertAlmostEqual(float(world.book["principal"][0]), 1.2)
        world._instalments(first)
        self.assertAlmostEqual(float(world.book["principal"][0]), 1.1)
        self.assertEqual(int(world.book["ndue"][0]), 1)

    def test_interest_on_a_late_final_instalment_falls_due(self):
        """Once a loan's last instalment has fallen due, all its accrued interest is due, so a loan repaid late
        leaves the book.

        Example: a one-month loan of 1 at 1% a month, billed on days 0, 30, 60. Its only, and so final, instalment
        falls due on day 30 with 0.01 of interest, and the borrower has nothing. The next month accrues 0.01 more,
        due as well, so on day 60, with money, the borrower pays 1.02 and the book is clean: no principal, no
        interest, nothing overdue."""
        w = controlled_world("S0")
        w.pop["cycles"][1], w.pop["phases"][1] = 30, 0
        w._add_loans(np.array([1]), False, TERM, np.array([1.0]), 0.01, 0.01, BIG, np.array([1]), 0)
        for t in range(60):
            w._instalments(t)
            w._collect_due(t)
            w._accrue()
        self.assertEqual(int(w.book["ndue"][0]), 1)
        self.assertAlmostEqual(float(w.book["interest"][0]), 0.02, places=12)
        self.assertAlmostEqual(float(w._overdue(np.array([0]))[0]), 1.02, places=12)
        w.cash[1] = 2.0
        w._instalments(60)
        w._collect_due(60)
        self.assertLess(float(w.book["principal"][0] + w.book["interest"][0]), EPS)
        self.assertLess(float(w._overdue(np.array([0]))[0]), EPS)
        self.assertAlmostEqual(float(w.cash[1]), 0.98, places=12)

    def test_real_cost_principal_time_counts_written_off_pool_loans_still_owed(self):
        """The real part's principal-time counts written-off pool loans while they are still owed (records only).

        Example: a written-off pool bridge of 3 to a card holder and a written-off pool term loan of 2 are still
        owed, so a day adds 3 / DAYS to ``pt_pool_card`` and 2 / DAYS to ``pt_pool_term``, as outside loans are
        counted while owed. The loss-learning exposure, coupons and the operating cost, which rules read, count only
        carried loans and stay zero."""
        w = controlled_world("M1")
        w.holder[1] = True
        w._add_loans(np.array([1]), True, BRIDGE, np.array([3.0]), 0.005, 0.02, 90)
        w._add_loans(np.array([2]), True, TERM, np.array([2.0]), 0.005, 0.02, BIG, np.array([12]), 0)
        w.book["carried"][:] = False
        for key in ("pt_pool_card", "pt_pool_term", "pt_pool_nocard_card", "coupons", "op_cost", "pool_pt"):
            w.acc[key] = 0.0
        w.acc["exposure"] = np.zeros(2)
        w._accrue()
        self.assertAlmostEqual(w.acc["pt_pool_card"], 3.0 / DAYS, places=15)
        self.assertAlmostEqual(w.acc["pt_pool_term"], 2.0 / DAYS, places=15)
        np.testing.assert_array_equal(w.acc["exposure"], [0.0, 0.0])
        self.assertEqual((w.acc["coupons"], w.acc["op_cost"], w.acc["pool_pt"]), (0.0, 0.0, 0.0))

    def test_write_off_keeps_legal_debt_and_books_valuation(self):
        """Write-off: 90 days past due, the pool loan carries zero, its legal debt stays, and the loss is valuation."""
        world = tiny_world()
        world._add_loans(np.array([3]), True, BRIDGE, np.array([0.5]), 0.005, 0.02, 10)
        before = world.net_wealth()[3]
        world.valuation = 0.0
        world._write_off(99)
        self.assertTrue(bool(world.book["carried"][0]))
        world._write_off(100)
        self.assertFalse(bool(world.book["carried"][0]))
        self.assertAlmostEqual(world.valuation, -0.5)
        self.assertAlmostEqual(float(world.net_wealth()[3]), float(before))
        self.assertAlmostEqual(world._assets(), 0.0)

    def test_overdraft_is_booked_as_outside_debt(self):
        """A negative balance left after converting the other unit becomes overdraft debt at r_ext."""
        world = tiny_world()
        world.cash[:], world.pcash[:] = 0.0, 0.0
        world.cash[2] = -0.4
        world._cover()
        world._book_overdrafts()
        self.assertAlmostEqual(float(world.cash[2]), 0.0)
        self.assertEqual(int(world.book["kind"][0]), OVERDRAFT)
        self.assertAlmostEqual(float(world.book["principal"][0]), 0.4)

    def test_layoff_weights_and_spells_follow_their_sources(self):
        """Stock statistics match: layoff risk falls with income (BLS by education through Census brackets), and the
        completed spell law's spells in progress, whose elapsed length has density S(a) / E[L], have the BLS median
        of 11.5 weeks (80.5 days) and mean of 24.8 weeks (173.6 days), integrated here apart from the closed forms
        the law is solved with. Its completed median is about 61 days and its mean about 109, and 50.9% of spells
        outlast 60 days (59.4% if the BLS figures were read as completed lengths)."""
        from scipy.integrate import quad
        from scipy.stats import norm
        weight = layoff_weight()
        np.testing.assert_allclose(weight, [1.126, 1.091, 1.027, 0.918], atol=5e-4)
        households = HOUSEHOLDS_BY_EDUCATION.sum(axis=0)
        self.assertAlmostEqual(float(weight @ households / households.sum()), 1.0, places=12)
        mu, sigma = np.log(COMPLETED_SPELL_MEDIAN_DAYS), COMPLETED_SPELL_SIGMA
        mean = np.exp(mu + sigma ** 2 / 2)
        survival = lambda a: norm.sf((np.log(a) - mu) / sigma)
        self.assertAlmostEqual(quad(survival, 0.0, 80.5)[0] / mean, 0.5, places=9)                   # age median
        self.assertAlmostEqual(quad(lambda a: a * survival(a), 0.0, np.inf, limit=200)[0] / mean, 173.6, places=6)
        self.assertAlmostEqual(COMPLETED_SPELL_MEDIAN_DAYS, 61.4476, places=3)
        self.assertAlmostEqual(COMPLETED_SPELL_SIGMA, 1.074466, places=5)
        self.assertAlmostEqual(float(mean), 109.4451, places=3)
        self.assertAlmostEqual(float(survival(60.0)), 0.50885, places=5)
        as_built = norm.sf((np.log(60.0) - np.log(SPELL_MEDIAN_DAYS)) / SPELL_SIGMA)
        self.assertAlmostEqual(float(as_built), 0.594, places=3)
        self.assertAlmostEqual(float(SPELL_MEDIAN_DAYS * np.exp(SPELL_SIGMA ** 2 / 2) / 7), 24.8, places=10)

    def test_a_laid_off_job_pays_nothing_and_owes_nothing(self):
        """A job laid off for the whole month creates no wage obligation; its payer keeps that month's wage."""
        world = tiny_world()
        world.acc = dict(shocks=0.0, volume=0.0)
        world.spell_start[0], world.spell_end[0] = 0, DAYS
        world._obligations(0)
        wage = world.ob["kind"] == WAGE
        self.assertFalse(bool((world.ob["buyer"][wage] == 0).any()))
        self.assertAlmostEqual(world.acc["withheld"], LABOUR_SHARE * float(world.spending[0]), places=12)
        self.assertAlmostEqual(world.acc["laid_off"], 1 / TINY.n, places=12)
        self.assertAlmostEqual(float(world.payable[0]), float(world.ob["amount"][world.ob["buyer"] == 0].sum()),
                               places=12)

    def test_jobs_without_wage_are_read_on_average_and_on_the_last_day(self):
        """Jobs without a wage are read as a monthly average and on the month's last day.

        Example: 80 jobs in a 30-day month: one in a spell all month, one whose spell ends on day 20 and
        one whose spell starts on day 25 and runs on. The month's average share of job-days in a spell is 55 of 2,400;
        on the month's last day 2 jobs of 80 pay no wage, the one whose spell ended not among them."""
        world = tiny_world()
        world.acc = dict(shocks=0.0, volume=0.0)
        world.spell_start[:3], world.spell_end[:3] = (0, 0, 25), (DAYS, 20, 4 * DAYS)
        world._obligations(0)
        self.assertAlmostEqual(world.acc["laid_off"], (DAYS + 20 + DAYS - 25) / (TINY.n * DAYS), places=12)
        self.assertAlmostEqual(world.acc["laid_off_last_day"], 2 / TINY.n, places=12)

    def test_spells_are_identical_before_the_distress_year_across_arms_and_levels(self):
        """Spells are identical before month 25 across arms and distress levels: with normal job loss (5% a month
        here so a small run shows spells), S0
        and M1 without distress and at 0.5 have the same jobs without a wage, on average and on the last day, in every
        month before the distress year, and runs that end before it end with the same spells. Spells start before the
        distress year and can run past it; within a level both arms see the very same spells; and the distress months
        lay off more at 0.5."""
        economy = replace(TINY, n=100, burn_in=2, months=6, distress_start=2, distress_length=2, job_loss=0.05)
        first = economy.burn_in + economy.distress_start
        cases = [(arm, level) for arm in ("S0", "M1") for level in (0.0, 0.5)]
        worlds = {case: _World(Inputs(), 0.6, replace(economy, distress=case[1]), case[0]) for case in cases}
        series = {case: world.run()["series"] for case, world in worlds.items()}
        for case in cases[1:]:
            for key in ("laid_off", "laid_off_last_day"):
                np.testing.assert_array_equal(series[case][key][:first], series[cases[0]][key][:first], err_msg=key)
        short = {case: _World(Inputs(), 0.6, replace(economy, distress=case[1], months=economy.distress_start), case[0])
                 for case in cases}
        list(map(lambda world: world.run(), short.values()))
        for case in cases[1:]:
            np.testing.assert_array_equal(short[case].spell_start, short[cases[0]].spell_start)
            np.testing.assert_array_equal(short[case].spell_end, short[cases[0]].spell_end)
        s0 = short[cases[0]]
        self.assertTrue(np.any((s0.spell_end > 0) & (s0.spell_start < first * DAYS)))   # spells before the year
        self.assertTrue(np.all(series[cases[0]]["laid_off"][:first] > 0))
        for level in (0.0, 0.5):
            np.testing.assert_array_equal(worlds["S0", level].spell_start, worlds["M1", level].spell_start)
            np.testing.assert_array_equal(worlds["S0", level].spell_end, worlds["M1", level].spell_end)
        distressed = worlds["S0", 0.5]
        self.assertTrue(np.any(distressed.spell_end > (first + economy.distress_length) * DAYS))   # past the year
        year = slice(first, first + economy.distress_length)
        self.assertTrue(np.all(series["S0", 0.5]["laid_off"][year] > series["S0", 0.0]["laid_off"][year]))

    def test_the_map_stores_the_wage_loss_path_for_every_arm(self):
        """Every arm's stored series carry the share of job-days on a job in a spell, the share of jobs in a spell on
        the month's last day, the wages their payers kept and (under the harsh stress) the wages of extra layoffs
        sent outside, month by month after launch, exactly as the run records them; the spells are the same in every
        arm.

        Example: the window starts at launch and a missing value reads as zero."""
        from scripts.run_economy_population import APPLIES, MEASURES, WAGE_LOSS, measures
        series = dict(failure_share=np.array([0.0, 0.1, np.nan]), laid_off=np.array([0.0, 0.02, 0.05]),
                      laid_off_last_day=np.array([0.0, 0.03, 0.04]), wages_withheld=np.array([0.0, 0.01, 0.02]),
                      wages_out=np.array([0.0, 0.005, 0.0]))
        self.assertEqual(measures(dict(arm="S0", series=series), Economy(n=1, burn_in=1, months=2)),
                         dict(failures=[0.1, 0.0], jobs_without_wage=[0.02, 0.05],
                              jobs_without_wage_last_day=[0.03, 0.04], wages_withheld=[0.01, 0.02],
                              wages_out=[0.005, 0.0]))
        economy = replace(TINY, n=100, burn_in=2, months=6, distress=0.5, distress_start=1, distress_length=2)
        runs = {arm: simulate(Inputs(), 0.6, economy, arm) for arm in ("S0", "M2")}
        stored = {arm: measures(run, economy) for arm, run in runs.items()}
        after = slice(economy.burn_in, economy.burn_in + economy.months)
        for arm, run in runs.items():
            # The recording-only measures (tests/test_measures.py) are stored beside them.
            from cpm_abm.economy_abm import MEASURE_SERIES
            self.assertEqual(set(stored[arm]),
                             set(APPLIES[arm]) | set(WAGE_LOSS) | set(MEASURE_SERIES)
                             | {"turnover", "microvelocity", "holding_velocity"})
            for name, key in WAGE_LOSS.items():
                np.testing.assert_allclose(stored[arm][name], run["series"][key][after], atol=1e-12)
            for name in APPLIES[arm]:
                self.assertEqual(stored[arm][name],
                                 np.nan_to_num(run["series"][MEASURES[name]][after]).round(12).tolist())
        for name in ("jobs_without_wage", "jobs_without_wage_last_day"):
            self.assertEqual(stored["S0"][name], stored["M2"][name])
            self.assertTrue(all(share > 0 for share in stored["S0"][name][1:3]))   # the distress year
        self.assertGreater(sum(stored["M2"]["wages_withheld"]), 0.0)
        self.assertGreater(sum(stored["M2"]["wages_out"]), 0.0)   # the distress year's extra layoffs

    def test_distress_keeps_wealth_accounting_exact(self):
        """With layoffs on, the conservation identity holds every month in every arm; payers keep the wages of normal
        job loss and, under the harsh stress, send the extra layoffs' wages outside."""
        economy = replace(TINY, n=100, burn_in=2, months=6, distress=0.2, distress_start=1, distress_length=3)
        for arm in ("S0", "M0", "M1", "M2"):
            series = simulate(Inputs(), 0.6, economy, arm)["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            self.assertGreater(float(series["wages_withheld"].sum()), 0.0)
            self.assertGreater(float(series["wages_out"].sum()), 0.0)

    def test_pool_coverage_lowers_failures(self):
        """With everyone participating, no exits and the pool funded (the test device, whose pool forms), failed
        payment value falls below S0's."""
        frozen = replace(Inputs(), xi0=0.0, xi1=0.0, upsilon=0.0)
        economy = replace(TINY, n=120)
        s0 = simulate(frozen, 1.0, economy, "S0")["series"]["failure_share"][economy.burn_in + 1:]
        m1 = pooled(frozen, 1.0, economy, "M1")["series"]["failure_share"][economy.burn_in + 1:]
        self.assertLess(float(m1.mean()), float(s0.mean()))

    # ---- Records and runner settings that change no outcome ----------------------------------------------------------
    def test_run_record_stores_what_the_engine_reads(self):
        """The stored inputs are the Inputs fields the engine reads and no other: the core model's 3.7% inflation, 5%
        penalty, no rewards and shocks are not among them. The constants are the engine's own ($27 a failed payment,
        0.75% card rewards), without codes, and rho_H is stored once per r_out."""
        from scripts.run_economy_figures import ENGINE_INPUTS, engine_record
        from scripts.run_economy_population import A0S, DISTRESS, RATES, cell_inputs, run_record
        engine = Path(__file__).resolve().parents[1] / "src" / "cpm_abm" / "economy_abm.py"
        # The engine's source is the facade and the package it re-exports (cpm_abm.engine).
        source = "".join(path.read_text(encoding="utf-8")
                         for path in [engine, *sorted((engine.parent / "engine").rglob("*.py"))])
        self.assertEqual(set(re.findall(r"\binputs\.(\w+)", source)), set(ENGINE_INPUTS))
        record = engine_record(cell_inputs(0.044))
        self.assertEqual(record["inputs"]["rho_H"], 0.044 / 12)
        self.assertEqual(set(record["inputs"]), set(ENGINE_INPUTS))
        self.assertFalse({"inflation", "penalty", "rewards", "shock_prob", "shock_size"} & set(record["inputs"]))
        self.assertAlmostEqual(record["constants"]["FAIL_FEE"] * MONTH_USD, 27.0, places=9)
        self.assertEqual(record["constants"]["CARD_REWARDS"], CARD_REWARDS)
        self.assertEqual(record["constants"]["CONVERSION_FEE"], CONVERSION_FEE)
        self.assertEqual(record["constants"]["HOUSEHOLDS_BY_EDUCATION"], HOUSEHOLDS_BY_EDUCATION.tolist())
        self.assertFalse({"EPS", "BIG", "ROUTE_P", "TERM", "BOOK_FIELDS", "ISSUER_BOOKS"} & set(record["constants"]))
        self.assertIn("in the units its source comment gives", record["constants_units"])
        meta = run_record(Economy(n=40), "development", 0)
        self.assertEqual(meta["inputs"]["rho_H"], [rate / 12 for rate in RATES])
        self.assertEqual(meta["constants"], record["constants"])
        self.assertEqual(meta["constants_units"], record["constants_units"])
        self.assertNotIn("penalty", meta["inputs"])
        # Each job sets its seed, distress level and convention, so the stored Economy leaves them unset, and by
        # default the run selects the full grid.
        self.assertEqual([meta["economy"][key] for key in ("seed", "distress", "lender_income_recirculated")],
                         [None] * 3)
        self.assertEqual(meta["economy"]["n"], 40)
        # The record shows what entry reads.
        self.assertEqual(meta["economy"]["entry_reads"], "quote")
        self.assertEqual(run_record(Economy(n=40, entry_reads="realised"), "development", 0)["economy"]["entry_reads"],
                         "realised")
        self.assertIn("each job stores its own", meta["economy_note"])
        self.assertEqual(meta["selected"], dict(r_out=RATES, a0=A0S, distress=DISTRESS, full_grid=True))
        json.dumps(meta)

    def test_provenance_hashes_each_source_as_committed_and_names_the_comet_pin(self):
        """Each source is hashed with CRLF read as LF, as git stores it, so a source unchanged since the commit hashes
        as the committed file whatever the working copy's line endings; comet.py is among the sources and the record
        names the block of the Comet snapshot M0 reads and the raw-byte hash of the manifest its files are checked
        against."""
        from scripts.run_economy_figures import COMET_DATA, provenance
        root = Path(__file__).resolve().parents[1]
        record = provenance("scripts/run_economy_population.py")
        # The engine is a package: every module of it is among the sources.
        engine = {path.relative_to(root).as_posix() for path in (root / "src" / "cpm_abm" / "engine").glob("*.py")}
        self.assertGreaterEqual(len(engine), 10)
        # So is the population runner: every module of the experiment package is among the sources.
        experiment = {path.relative_to(root).as_posix()
                      for path in (root / "src" / "cpm_abm" / "experiment").glob("*.py")}
        self.assertGreaterEqual(len(experiment), 8)
        self.assertEqual(set(record["sources"]), {"src/cpm_abm/economy_abm.py", "src/cpm_abm/core_model.py",
                                                  "src/cpm_abm/comet.py", "scripts/run_economy_figures.py",
                                                  "scripts/run_economy_population.py"} | engine | experiment)
        self.assertEqual(record["comet_pin_block"], 26_214_368)
        manifest = (root / COMET_DATA / "sha256_manifest.json").read_bytes()
        self.assertEqual(record["comet_pin_manifest"], hashlib.sha256(manifest).hexdigest())
        git = lambda *command: subprocess.run(["git", "-c", "safe.directory=*", *command], cwd=root,
                                              capture_output=True, timeout=10)
        for path, digest in record["sources"].items():
            lf = (root / path).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(digest, hashlib.sha256(lf).hexdigest(), path)
            # Against the committed file where git is there and the source is unchanged since the commit.
            try:
                unchanged, committed = git("diff", "--quiet", "HEAD", "--", path), git("show", f"HEAD:{path}")
            except (OSError, subprocess.SubprocessError):
                continue
            if unchanged.returncode == 0 and committed.returncode == 0:
                self.assertEqual(digest, hashlib.sha256(committed.stdout).hexdigest(), path)

    def test_population_map_defaults_to_twelve_workers_on_one_blas_thread(self):
        """A population run uses 12 workers by default, and refuses more (``main``) unless --most-workers raises the
        limit: 12 is what a 31 GB laptop holds (more run out of memory), and a machine with about 1.5 GB for every
        worker may set a higher one. Checked in a --dry-run, which simulates and writes nothing: 16 workers are
        refused at the default limit and accepted with --most-workers 16. The runner sets one BLAS and OpenMP thread
        per process before numpy loads, which cuts each worker's committed memory from about 1.7 GB to 0.25 GB."""
        import os
        import sys
        from unittest import mock
        from scripts.run_economy_population import WORKERS_MOST, main, options
        self.assertEqual(options().parse_args(["--seeds", "development", "--timing"]).workers, 12)
        self.assertEqual(options().parse_args(["--seeds", "development"]).most_workers, 12)
        self.assertEqual(WORKERS_MOST, 12)
        launch = ["run_economy_population.py", "--seeds", "development", "--workers", "16", "--dry-run"]
        err = io.StringIO()
        with mock.patch.object(sys, "argv", launch), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            main()
        self.assertIn("--workers must be from 1 to 12", err.getvalue())
        out = io.StringIO()
        with mock.patch.object(sys, "argv", [*launch, "--most-workers", "16"]), contextlib.redirect_stdout(out):
            main()
        self.assertEqual(json.loads(out.getvalue().split("cells (r_out")[0])["workers"], 16)
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            self.assertEqual(os.environ.get(name), "1", name)
        source = (Path(__file__).resolve().parents[1] / "scripts" / "run_economy_population.py").read_text(
            encoding="utf-8")
        self.assertLess(source.index('os.environ[_threads] = "1"'), source.index("import numpy"))

    def test_runners_default_to_no_collateral_lending_the_decided_noise_and_no_provider_fee(self):
        """The runners' defaults: M0 runs with no crypto collateral holders (collateral lending by Compound III is
        not run or reported; the option remains for the unit tests); the leaving rule's noise is its default scale,
        with half and twice as options and nothing else; and every runner that builds cell inputs (population,
        figures, stress) runs with no provider fee (P payments run on stablecoin rails), the core model's alpha set
        to zero in one place, while the core model keeps its own 0.2%, which the engine no longer reads (nor stores
        among its inputs)."""
        import scripts.run_economy_figures as figures
        import scripts.run_economy_population as population
        import scripts.run_economy_stress as stress
        args = population.options().parse_args(["--seeds", "development"])
        self.assertEqual((args.crypto_share, args.leave_noise), (CRYPTO_SHARE, 1.0))
        self.assertEqual(CRYPTO_SHARE, 0.0)
        self.assertEqual(population.options().parse_args(["--seeds", "development", "--leave-noise", "2"]).leave_noise,
                         2.0)
        # What entry reads: the quote by default, the track record as the sensitivity.
        self.assertEqual(args.entry_reads, "quote")
        self.assertEqual(population.options().parse_args(["--seeds", "development", "--entry-reads", "realised"])
                         .entry_reads, "realised")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            population.options().parse_args(["--seeds", "development", "--leave-noise", "3"])
        # Card lines in the distress year: held by default, the cut on its own switch.
        self.assertEqual(args.card_lines, "held")
        self.assertEqual(population.options().parse_args(["--seeds", "development", "--card-lines", "cut"]).card_lines,
                         "cut")
        root = Path(__file__).resolve().parents[1]
        for name in ("run_economy_population.py", "run_economy_stress.py", "run_economy_figures.py"):
            self.assertNotIn("PROVIDER_FEE", (root / "scripts" / name).read_text(encoding="utf-8"), name)
        self.assertNotIn("inputs.alpha", (root / "src" / "cpm_abm" / "economy_abm.py").read_text(encoding="utf-8"))
        self.assertNotIn("alpha", figures.ENGINE_INPUTS)
        self.assertEqual((figures.engine_inputs().alpha, Inputs().alpha), (0.0, 0.002))
        self.assertEqual((population.cell_inputs(0.044).alpha, population.cell_inputs(0.044).rho_H), (0.0, 0.044 / 12))
        from unittest import mock
        with mock.patch("cpm_abm.experiment.jobs.simulate", side_effect=RuntimeError) as run:
            with self.assertRaises(RuntimeError):
                population.job((0.044, 0.6, 0.0, 20261021, 10, False))
        self.assertEqual(run.call_args.args[2].crypto_share, CRYPTO_SHARE)
        with mock.patch.object(stress, "simulate", side_effect=RuntimeError) as run:
            with self.assertRaises(RuntimeError):
                stress.run(("baseline", "M1", 20261021, 10))
        self.assertEqual(run.call_args.args[0].alpha, 0.0)

    def test_bridges_drawn_over_wanted_is_the_share_the_pool_funds(self):
        """The record "bridges_drawn_over_wanted" is the share of the bridging wanted that the pool funds.

        Example: a bill of 0.04 (months of spending) wanted in full from a pool holding 0.01 of cash: a quarter is
        drawn. "coverage" is the holding charge's (demurrage) share of the bridging capital cost, zero here with no
        cycle observed, and "bridges" is the value drawn."""
        w = controlled_world()
        funded_pool(w, 0.01)
        w.r_g = w.r_b = 0.005
        w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
        w.last["receipts"][:] = 1.0
        w.acc["want"][:] = w.acc["drawn"][:] = 0.0
        one_invoice(w, 0.04, card=False)
        w._settle(1, 30)
        self.assertAlmostEqual(float(w.acc["want"].sum()), 0.04, places=15)
        w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertAlmostEqual(w.series["bridges_drawn_over_wanted"][-1], 0.25, places=12)
        self.assertEqual(w.series["coverage"][-1], 0.0)
        self.assertAlmostEqual(w.series["bridges"][-1] * 10, 0.01, places=12)

    def test_credit_death_reads_cash_to_lend(self):
        """Six second-window months with no new pool loans are credit death only while the pool has cash to lend:
        the same months read as nothing when the pool holds cash it may not lend. At the close a pool serving lends its cash net of what it owes its creditors, and one not serving lends nothing."""
        from scripts.run_economy_figures import persistence
        months = 60
        series = {key: np.ones(months) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                  "cash_to_lend", "interest_collected", "own_margin",
                                                  "owners_capital")}
        series.update(K=np.full(months, 0.1), pool_costs=np.zeros(months), write_off_rate=np.zeros(months),
                      arrears_share=np.zeros(months))
        series["new_pool_loans"][40:46] = 0.0                   # six W2 months without a new pool loan
        run = dict(series=series, economy=Economy(n=2, burn_in=0, months=months))
        self.assertIs(persistence(run, 0.6)["X"]["X2"], True)
        series["cash_to_lend"][40:46] = 0.0                     # gross pool cash stays 1
        self.assertIs(persistence(run, 0.6)["X"]["X2"], False)  # True before the fix
        for serving, payable in ((True, 0.0), (True, 0.3), (False, 0.0)):
            w = controlled_world()
            w.pool_cash, w.shares[1], w.nav_ps, w.capital = 1.0, 1.0, 1.0, 1.0
            w.had_owners = w.launched = True
            w.service, w.pool_payable = serving, payable
            w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
            self.assertGreater(w.series["pool_cash"][-1], 0.0)
            self.assertEqual(w.series["service"][-1], float(serving))
            self.assertAlmostEqual(w.series["cash_to_lend"][-1], w.series["pool_cash"][-1] if serving else 0.0,
                                   places=15)
            self.assertAlmostEqual(w.series["cash_to_lend"][-1], w._cash_to_lend() / 10, places=15)

    def test_new_records_change_no_outcome(self):
        """The cash-to-lend record changes no outcome: the same small economy with cash to lend silenced gives every
        other record exactly (the test device, whose pool forms, in M1 and M2)."""
        class Silenced(PooledWorld):
            def _cash_to_lend(self):
                return 0.0
        economy = replace(TINY, n=100, months=12)
        for arm in ("M1", "M2"):
            run, silenced = kept_run(PooledWorld, arm, economy), Silenced(Inputs(), 0.6, economy, arm).run()
            self.assertGreater(float(np.max(run["series"]["cash_to_lend"])), 0.0)   # the record is live
            self.assertEqual(float(np.max(silenced["series"]["cash_to_lend"])), 0.0)
            self.assert_same_outcome(run, silenced, ("cash_to_lend",))

    # ---- Failure counts ---------------------------------------------------------------------------------------
    def test_whole_items_are_the_fewest_a_bank_paying_in_order_returns(self):
        """Example ($): each payment's running total within its payer's day, smallest first, whatever order the day
        lists them in (equal payments in either order). Two $40 bills against $30 return both; three $14 against $41
        one; $100 and $5 against $100 one; $10, $30 and $50 against $45 one, the $50."""
        payer = np.array([0, 0, 1, 1, 1, 2, 2, 3, 3, 3])
        cost = np.array([40.0, 40.0, 14.0, 14.0, 14.0, 100.0, 5.0, 50.0, 10.0, 30.0])
        within = np.array([40.0, 80.0, 14.0, 28.0, 42.0, 105.0, 5.0, 90.0, 10.0, 40.0])
        np.testing.assert_array_equal(in_order(payer, cost), within)
        funds = np.array([30.0, 41.0, 100.0, 45.0])
        returned = lambda who, totals: np.bincount(who, weights=totals > funds[who], minlength=4)
        np.testing.assert_array_equal(returned(payer, within), [2.0, 1.0, 1.0, 1.0])
        shuffle = np.random.default_rng(7).permutation(payer.size)
        shuffled = in_order(payer[shuffle], cost[shuffle])
        np.testing.assert_array_equal(np.sort(shuffled + 1000 * payer[shuffle]), np.sort(within + 1000 * payer))
        np.testing.assert_array_equal(returned(payer[shuffle], shuffled), [2.0, 1.0, 1.0, 1.0])

    def test_failures_count_in_fee_units_unpaid_shares_and_whole_items(self):
        """Failures count in fee units, unpaid shares and whole items.

        Examples ($), a payer without a card or savings. $40 + $40 against $30: 1.25 payments fail in shares, one
        fee unit ($27) and both bills in whole items. Three $14 against $41: 3/42 in shares and fee units, one whole
        bill. $5 + $100 against $100: 10/105, one. $10 + $30 + $50 against $45: 1.5 shares, one fee unit, one whole
        bill. A $14 card-eligible purchase and a $40 bill against $30: each loses 24/54, the bill alone carries the fee
        and is returned whole, and the purchase, paid first, is declined in share only. A $100 card-eligible purchase
        against $60: 0.4 declined, one whole purchase, no failed bill. S0 bridges nothing."""
        def settle(cash, amounts, card=()):
            w = controlled_world("S0")
            w.cash[0] = cash / MONTH_USD
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS))
            k = len(amounts)
            w.ob = dict(buyer=np.zeros(k, int), seller=np.arange(1, k + 1), amount=np.array(amounts) / MONTH_USD,
                        settle=np.full(k, 30), card=np.isin(np.arange(k), card), kind=np.full(k, SERVICE))
            w.receivable[1:k + 1] = w.ob["amount"]
            w.payable[0] = w.ob["amount"].sum()
            w._settle(1, 30)
            fee = float(w.book["principal"][w.book["kind"] == FEE_DEBT].sum()) * MONTH_USD
            self.assertEqual(float(sum(w.acc[key].sum() for key in ("bridged_shares", "bridged_items",
                                                                     "bridged_card"))), 0.0)
            self.assertEqual(float(np.delete(np.stack([w.acc[key] for key in FAILURE_COUNTS]), 0, axis=1).sum()), 0.0)
            return {key: float(w.acc[key][0]) for key in FAILURE_COUNTS}, fee
        cases = (((30, [40, 40]), dict(fail_shares=1.25, fail_units=1.0, fail_items=2.0, fail_days=1.0), 27.0),
                 ((41, [14, 14, 14]), dict(fail_shares=3 / 42, fail_units=3 / 42, fail_items=1.0), 27 * 3 / 42),
                 ((100, [5, 100]), dict(fail_shares=10 / 105, fail_units=10 / 105, fail_items=1.0), 27 * 10 / 105),
                 ((45, [10, 30, 50]), dict(fail_shares=1.5, fail_units=1.0, fail_items=1.0), 27.0),
                 ((30, [14, 40], (0,)), dict(fail_shares=24 / 54, declined_shares=24 / 54, fail_items=1.0,
                                             declined_items=0.0), 27 * 24 / 54),
                 ((60, [100], (0,)), dict(fail_shares=0.0, fail_units=0.0, fail_items=0.0, fail_days=0.0,
                                          declined_shares=0.4, declined_items=1.0), 0.0))
        for args, expected, fee in cases:
            counts, charged = settle(*args)
            for key, value in expected.items():
                self.assertAlmostEqual(counts[key], value, places=12, msg=(args, key))
            self.assertAlmostEqual(charged, fee, places=10)
            self.assertAlmostEqual(counts["fail_units"] * 27.0, charged, places=10)

    def test_failure_counts_are_kept_by_person_and_month_and_reproduce_the_fee(self):
        """In short runs of S0 and M1 (everyone participating, the test device, whose pool forms) the counts are kept by
        person and month and as series a person a month; the fee is $27 a fee unit up to the monthly cap a person a
        month (``fees_a_month``, two), the count starting again each month, so no person-month pays more than $54 and
        the cap binds on some; fee units never exceed unpaid shares or days with a failure; whole items are whole; the
        real part's failed payments are read from the unpaid and bridged shares; and only the pool bridges."""
        from scripts.run_economy_population import real_part
        frozen = replace(Inputs(), xi0=0.0, xi1=0.0, upsilon=0.0)
        economy = replace(TINY, n=120)
        cap = economy.fees_a_month
        self.assertEqual(cap, 2.0)
        after = slice(economy.burn_in, economy.burn_in + economy.months)
        # upsilon 0 freezes participation and also the savers' entry decision, so every saver is made to consider
        # entry each month (``EnteringWorld``) for the pool to form.
        runs = dict(S0=simulate(frozen, 1.0, economy, "S0"), M1=EnteringWorld(frozen, 1.0, economy, "M1").run())
        for arm, run in runs.items():
            counts, series = run["failure_counts"], run["series"]
            self.assertEqual(set(counts), set(FAILURE_COUNTS))
            for key in FAILURE_COUNTS:
                self.assertEqual(counts[key].shape, (economy.burn_in + economy.months, economy.n))
                np.testing.assert_allclose(series[key], counts[key].mean(axis=1), rtol=1e-12, atol=1e-15, err_msg=key)
            np.testing.assert_allclose(np.minimum(counts["fail_units"], cap) * FAIL_FEE, run["fees"], rtol=1e-12,
                                       atol=1e-15)
            self.assertTrue(np.all(run["fees"] <= cap * FAIL_FEE * (1 + 1e-12)), arm)
            self.assertTrue(np.any(counts["fail_units"] > cap + 1e-9), arm)                 # the cap binds
            self.assertTrue(np.all(run["fees"] <= counts["fail_units"] * FAIL_FEE * (1 + 1e-12)), arm)
            self.assertTrue(np.all(counts["fail_units"]
                                   <= np.minimum(counts["fail_shares"], counts["fail_days"]) + 1e-9))
            self.assertGreater(float(counts["fail_shares"].sum()), 0.0, arm)
            np.testing.assert_array_equal(counts["fail_items"], np.round(counts["fail_items"]))
            line = FAIL_COST * (series["fail_shares"][after].sum() + series["bridged_shares"][after].sum()) * MONTH_USD
            self.assertAlmostEqual(real_part(run, economy)["failed_payments"], line, delta=0.01)
        self.assertEqual(float(runs["S0"]["failure_counts"]["bridged_shares"].sum()), 0.0)
        self.assertGreater(float(runs["M1"]["failure_counts"]["bridged_shares"].sum()), 0.0)

    def test_failure_report_reads_the_monthly_cap_from_the_spread_of_fee_units(self):
        """The failure report reads the monthly cap from the spread of fee units.

        Example ($): two people over one month after launch with 4 and 1 fee units: $810 of fees a person a year;
        under a monthly cap of 2, 3 and 5, $486, $648 and $810; at 3 a month 2 units a person are left, the cap binds
        half the people and everyone paid; the heaviest payer's 4 units are 48 a year. With the development seeds each
        person-month is stored, named apart from the monthly payers; the map's seed sets store the monthly series and
        spread only. Every stored key has a label: the monthly series, the yearly figures and the table's columns. The
        run's own monthly cap binds nobody where every fee unit was charged, and half the people where the
        fees stop at three a month ($648 a person a year)."""
        from scripts.run_economy_population import FAILURE_LABELS, failure_report
        w = Economy(n=2, burn_in=1, months=1)
        units = np.array([[0.0, 0.0], [4.0, 1.0]])
        counts = dict({key: np.zeros((2, 2)) for key in FAILURE_COUNTS}, fail_units=units, fail_shares=units,
                      fail_days=units)
        series = dict({key: value.mean(axis=1) for key, value in counts.items()}, nocard_bridges=np.zeros(2))
        run = dict(series=series, failure_counts=counts, fees=units * FAIL_FEE)
        report = failure_report(run, w, by_payer=True)
        year, month = report["a_year"], report["monthly"]
        self.assertEqual(year["fees_usd"], 810.0)
        self.assertEqual([year[f"fees_usd_cap_{cap}"] for cap in (2, 3, 5)], [486.0, 648.0, 810.0])
        self.assertEqual((month["capped_3"], month["binds_3"], month["payers"]), ([2.0], [0.5], [1.0]))
        # The run's own monthly cap: these fees were charged on every fee unit, so it binds nobody; charged
        # under a cap of 3 a month, it binds the person with 4 fee units, half the people.
        self.assertEqual(month["binds"], [0.0])
        capped = failure_report(dict(run, fees=np.minimum(units, 3.0) * FAIL_FEE), w)
        self.assertEqual((capped["monthly"]["binds"], capped["a_year"]["fees_usd"]), ([0.5], 648.0))
        self.assertEqual(year["heaviest_fee_units"], 48.0)
        payers = report["payer_months"]
        self.assertEqual((payers["month"], payers["person"], payers["fees_usd"]), ([1, 1], [0, 1], [108.0, 27.0]))
        self.assertEqual(payers["fail_units"], [4.0, 1.0])
        self.assertEqual(set(failure_report(run, w)), {"monthly", "a_year"})
        self.assertEqual(set(report), {"monthly", "a_year", "payer_months"})
        self.assertEqual({part: {re.sub(r"_\d+$", "_k", key) for key in values} for part, values in report.items()},
                         {part: set(FAILURE_LABELS[part]) for part in report})
        self.assertEqual(set(FAILURE_LABELS), {"monthly", "a_year", "payer_months", "buffers"})
        json.dumps(report)

    def assert_same_outcome(self, run, other, new):
        """Two runs agree exactly on every record but the ``new`` ones, each a series or a key of the run: every other
        series and every other key of the run, the person-level paths and reports, channels, exits, loan ages, the
        population, the economy, the payments log and the reserve rate."""
        self.assertEqual(set(run), set(other))
        self.assertEqual(set(run["series"]), set(other["series"]))
        self.assertTrue(set(new) <= set(run) | set(run["series"]), new)   # each record left out exists

        def same(mine, theirs, name):
            """One record, compared exactly; a dict key by key."""
            if isinstance(mine, dict):
                self.assertEqual(set(mine), set(theirs), name)
                list(map(lambda key: same(mine[key], theirs[key], f"{name} {key}"), mine))
            elif isinstance(mine, (str, Economy)):
                self.assertEqual(mine, theirs, name)
            else:
                np.testing.assert_array_equal(mine, theirs, err_msg=name)
        kept = lambda records: {key: value for key, value in records.items() if key not in new}
        same(kept(dict(run, series=kept(run["series"]))), kept(dict(other, series=kept(other["series"]))), "run")

    def assert_exits_reached(self, run, arm):
        """The forced run reaches the exit path (owners leave by the users' rule and are paid from pool cash):
        owners request exits and some are paid."""
        self.assertGreater(float(np.max(run["series"]["exit_requested"])), 0.0, arm)
        self.assertGreater(float(np.max(run["series"]["exit_paid"])), 0.0, arm)

    def test_failure_counts_change_no_outcome(self):
        """The failure counts change no outcome: the same small economy with the counting silenced gives every
        other record exactly, in S0, M0, M1 and M2 (the test device, whose pool forms), and in M1 and M2 in a forced
        run with distress, whose owners ask to exit."""
        silence = lambda base: type("Silenced", (base,), dict(_count_failures=lambda self, *args: None))
        economy = replace(TINY, n=100, months=12)
        for arm, base, w in (("S0", _World, economy), ("M0", _World, economy), ("M1", PooledWorld, economy),
                             ("M2", PooledWorld, economy), ("M1", ForcedRun, FORCED_DISTRESS),
                             ("M2", ForcedRun, FORCED_DISTRESS)):
            run, silenced = kept_run(base, arm, w), silence(base)(Inputs(), 0.6, w, arm).run()
            self.assertGreater(float(run["failure_counts"]["fail_shares"].sum()), 0.0, arm)   # the counts are live
            self.assertFalse(any(silenced["failure_counts"][key].any() for key in FAILURE_COUNTS))
            if base is ForcedRun:
                self.assert_exits_reached(run, arm)
                self.assertGreater(float(run["series"]["laid_off"].max()), 0.0, arm)
            # Hit workers' failed shares (the harsh stress's read-out) are part of the failure counts.
            self.assert_same_outcome(run, silenced, FAILURE_COUNTS + ("failure_counts", "fail_shares_hit"))

    # ---- The wage-loss path and paired differences ----------------------------------------------------------------
    def test_wage_loss_and_paired_differences_change_no_outcome(self):
        """The count of jobs without a wage on the month's last day and each seed's paired differences change
        no outcome: the same small distressed economy with the count silenced gives every other record exactly, in S0,
        M0, M1 and M2 (the test device, whose pool forms); from the distress year's last month on, the count reads the
        spells the run ends with; and each arm's row with its paired differences silenced keeps every other field."""
        from unittest import mock
        from scripts import run_economy_population as population
        silence = lambda base: type("Silenced", (base,), dict(_laid_off_last_day=lambda self, spell: 0.0))
        # Without normal job loss, so that no spell starts after the distress year and the spells a run ends
        # with are those the last months read: the record is what this checks, not the job-loss rule.
        economy = replace(TINY, n=100, months=8, distress=0.5, distress_start=1, distress_length=2, job_loss=0.0)
        runs = {}
        for arm, base in (("S0", _World), ("M0", _World), ("M1", PooledWorld), ("M2", PooledWorld)):
            world = base(Inputs(), 0.6, economy, arm)
            runs[arm], silenced = world.run(), silence(base)(Inputs(), 0.6, economy, arm).run()
            last = runs[arm]["series"]["laid_off_last_day"]
            self.assertGreater(float(last.max()), 0.0, arm)                     # the count is live
            self.assertEqual(float(silenced["series"]["laid_off_last_day"].max()), 0.0)
            self.assert_same_outcome(runs[arm], silenced, ("laid_off_last_day",))
            # No spell starts after the distress year, so from its last month on the spells read are those at the end.
            first = economy.burn_in + economy.distress_start + economy.distress_length - 1
            ends = (np.arange(first, economy.burn_in + economy.months) + 1) * DAYS - 1
            expected = ((world.spell_start <= ends[:, None]) & (ends[:, None] < world.spell_end)).mean(axis=1)
            np.testing.assert_array_equal(last[first:], expected)
        rows = lambda: {arm: population.arm_row(runs[arm], runs["S0"], runs["M0"], 0.6, economy)
                        for arm in ("M0", "M1", "M2")}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            live = rows()
            with mock.patch("cpm_abm.experiment.gains.differences", lambda arm, other, w: None):
                quiet = rows()
        drop = lambda row: json.dumps({key: value for key, value in row.items() if key != "against"})
        for arm in ("M0", "M1", "M2"):
            self.assertIsNotNone(live[arm]["against"]["S0"])
            self.assertEqual(drop(live[arm]), drop(quiet[arm]), arm)

    # ---- Owners' return, the issuer-held share and crossings between E and P -------------------------------------
    def test_owners_income_is_their_capital_times_the_nav_change(self):
        """Dealing is at NAV, so households' income each month is their capital after dealing times the NAV's change
        from dealing to the close before CPI, read here from the pool's own books. With the holding charge
        (demurrage) no issuer money reaches the pool's income, so net of issuer money it is the same, read in months
        where the pool's float is paid. Households hold all pool capital (the issuer is a pure custodian). Checked
        in the forced run of the test device, whose pool forms, in M1 and M2, over 24 months after launch
        (``FORCED_LONG``)."""
        class Watched(ForcedRun):
            def _close(self, *args):
                self.navs.append([self.nav_ps, np.nan])              # the dealing NAV, unchanged through the days
                super()._close(*args)

            def _deflate(self):
                self.navs[-1][1] = self.nav_ps                       # the close's NAV, before CPI
                return super()._deflate()
        for arm in ("M1", "M2"):
            w = Watched(Inputs(), 0.6, FORCED_LONG, arm)
            w.navs = []
            run = w.run()
            s = run["series"]
            opened, closed = np.array(w.navs).T
            pool = s["owners_capital"] > 0
            self.assertTrue(pool.any(), arm)                          # the pool formed
            self.assert_exits_reached(run, arm)
            at = lambda key: s[key][pool]
            book = (run["owned"].sum(axis=1) * (closed / opened - 1))[pool]
            np.testing.assert_allclose(at("owners_income") * 100, book, rtol=1e-9, atol=1e-14)
            self.assertTrue(np.any(at("float_pool") > 0), arm)          # the pool's float reached it
            np.testing.assert_array_equal(at("owners_income_net"), at("owners_income"))
            np.testing.assert_array_equal(s["R_net"], s["R"])
            np.testing.assert_allclose(at("owners_capital"), at("N"), rtol=1e-12)
            np.testing.assert_allclose(at("owners_income"), at("owners_capital") * at("R"), rtol=1e-12)
            np.testing.assert_allclose(run["owned"].sum(axis=1) / 100, s["owners_capital"], rtol=1e-12, atol=1e-15)
            self.assertTrue(np.all(s["owners_income"][~pool] == 0.0))

    def test_owners_lose_at_most_their_whole_holding_net_as_in_all(self):
        """Owners lose at most their whole holding, net as in all.

        Example: households hold 1.9 of 2.0 of pool capital. At R = 3% they earn 0.057;
        where the NAV falls by 99.5% they lose 1.8905, and where it closes below zero (R = -120%) their whole holding,
        1.9, and no more; R itself is not capped. With the holding charge (demurrage) the pool's float and the charge
        are the contract's, not issuer money, so net of issuer money is the same as in all, even with a float of 0.02
        in the month's books."""
        w = controlled_world()
        w.acc.update(float_pool=0.02)
        w.capital, w.owners_held = 2.0, np.r_[1.0, 0.9, np.zeros(8)]
        for R, gross in ((0.03, 0.057), (-0.995, -1.8905), (-1.2, -1.9)):
            R_net, capital, income, income_net = w._owners_income(R)
            self.assertEqual(R_net, R)
            self.assertAlmostEqual(capital, 1.9, places=12)
            self.assertAlmostEqual(income, gross, places=12)
            self.assertEqual(income_net, income, msg=R)

    def test_own_return_runs_from_buying_over_at_most_twelve_months(self):
        """An owner's own return runs from buying, over at most twelve months.

        Example: two owners over five months. The first holds $1,000 for three months, sells, and buys $500 again:
        its return restarts. The second buys $2,000 in the second month. Over at most two months the window drops the
        oldest month."""
        owned = np.array([[1000.0, 0.0], [1000.0, 2000.0], [1000.0, 2000.0], [0.0, 2000.0], [500.0, 2000.0]])
        rate = np.array([0.01, 0.02, -0.01, 0.03, 0.005])
        np.testing.assert_allclose(own_returns(owned, rate),
                                   [[0.01, np.nan], [0.015, 0.02], [0.02 / 3, 0.005], [np.nan, 0.04 / 3],
                                    [0.005, 0.01125]], rtol=1e-12)
        short = own_returns(owned, rate, months=2)
        np.testing.assert_allclose(short[2:, 0], [0.005, np.nan, 0.005], rtol=1e-12)
        np.testing.assert_allclose(short[3:, 1], [0.01, 0.0175], rtol=1e-12)
        # A month without a pool (R undefined) credits nothing.
        np.testing.assert_allclose(own_returns(owned[:2], np.array([np.nan, 0.02]))[1], [0.01, 0.02], rtol=1e-12)

    def test_owners_return_reads_the_hand_case(self):
        """The owners' return report reads a worked case.

        Example: one household holding $10,000 of shares for five years after launch, earning 0.1% a month in the
        first year, 0.2% in the second and so on, 0.05% a month of it issuer money: 1.2% to 6.0% a year by year, 5.4% in
        W2 and 4.8% net. Its own net return over the last 12 months is lowest, 3.1%, in W2's first month, where 11
        months of the third year (2.5% a month net, x 12) meet one of the fourth (3.5%); over W2 it averages 4.25%."""
        from scripts.run_economy_population import owners_return
        w = Economy(n=1, burn_in=1, months=60)
        held = np.r_[0.0, np.full(60, 10000 / MONTH_USD)]
        R = np.r_[np.nan, 0.001 * np.repeat(np.arange(1, 6), 12)]
        series = dict(owners_capital=held, owners_income=np.nan_to_num(held * R), R=R, R_net=R - 0.0005,
                      owners_income_net=np.nan_to_num(held * (R - 0.0005)))
        report = owners_return(dict(series=series, owned=held[:, None], economy=w, vintage=self.no_loans(61)), w)
        self.assertEqual(report["gross_pct"], dict(W1=3.0, W2=5.4, by_year=[1.2, 2.4, 3.6, 4.8, 6.0]))
        self.assertEqual(report["net_pct"]["W2"], 4.8)
        self.assertEqual(report["capital_W2_usd"], 10000.0)
        self.assertEqual((report["own_net_W2_lowest_pct"], report["own_net_W2_mean_pct"]), (3.1, 4.25))
        nothing = owners_return(dict(series=dict(series, owners_capital=0 * held, owners_income=0 * held,
                                                 owners_income_net=0 * held), owned=0 * held[:, None], economy=w,
                                    vintage=self.no_loans(61)), w)
        self.assertEqual((nothing["gross_pct"]["W2"], nothing["own_net_W2_lowest_pct"]), (None, None))
        self.assertEqual(report["by_loan_year"], dict.fromkeys(("all", "bridge", "term"), [None] * LOAN_YEARS))
        json.dumps(report)
        # A holding bought in W2's first month whose NAV closes below zero (R -120%, -121% net) loses all of itself:
        # -1,200% a year net, not -1,212%.
        first = np.arange(61) == w.burn_in + 36
        lost, R = np.where(first, 10000 / MONTH_USD, 0.0), np.where(first, -1.2, np.nan)
        series = dict(owners_capital=lost, owners_income=-lost, R=R, R_net=R - 0.01, owners_income_net=-lost)
        wiped = owners_return(dict(series=series, owned=lost[:, None], economy=w, vintage=self.no_loans(61)), w)
        self.assertEqual((wiped["own_net_W2_lowest_pct"], wiped["own_net_W2_mean_pct"]), (-1200.0, -1200.0))

    @staticmethod
    def no_loans(months):
        """A run's loan-year record with no pool loan: income and principal-time zero in every band, and no pool-wide
        income."""
        return dict(income=np.zeros((months, 2, LOAN_YEARS)), exposure=np.zeros((months, 2, LOAN_YEARS)),
                    shared=np.zeros(months))

    def test_owners_return_reads_each_loan_year(self):
        """The owners' return is read for each loan year.

        Example: five years after launch. Bridges made in the first year carry 0.5 for 12
        months and earn 0.005 a month, 12% a year; term loans of that year carry 2.0 for 24 months and earn 0.01 a
        month, 6%: together 6.667%. Term loans made in the second year carry 1.0 for 12 months and earn 0.004 a month,
        but 0.3 of them is written off and 0.1 later recovered: -15.2% a year. No loan was made later, nor a bridge in
        the second year (None). A burn-in month is not read, nor a payment of 0.5 after the pool wound down for good
        in month 50 (R undefined from then). Those are the loans' own incomes. Spread by principal-time,
        0.0025 a month of provider fees less the fixed cost in the first year goes 0.0005 to the bridges and
        0.002 to the term loans carried then, which earn 13.2% and 6.6%, 7.333% together; the -0.002 of month 30,
        with no loan carried, is no loan year's (-$12.88 a person), and the 1.0 after the wind-down is not read."""
        from scripts.run_economy_population import owners_return
        w = Economy(n=1, burn_in=1, months=60)
        record = self.no_loans(61)
        income, exposure, shared = record["income"], record["exposure"], record["shared"]
        shared[1:13], shared[30], shared[55] = 0.0025, -0.002, 1.0
        income[0, 0, 0] = exposure[0, 0, 0] = 1.0                       # a burn-in month
        income[1:13, 0, 0], exposure[1:13, 0, 0] = 0.005, 0.5
        income[1:25, 1, 0], exposure[1:25, 1, 0] = 0.01, 2.0
        income[13:25, 1, 1], exposure[13:25, 1, 1] = 0.004, 1.0
        income[20, 1, 1] -= 0.3                                          # a write-off
        income[30, 1, 1] += 0.1                                          # a recovery, with nothing carried
        income[55, 1, 1] += 0.5                                          # paid to a pool with no owner
        nothing = np.zeros(61)
        R = np.where((np.arange(61) >= w.burn_in) & (np.arange(61) < 50), 0.001, np.nan)
        series = dict(owners_capital=nothing, owners_income=nothing, owners_income_net=nothing, R=R,
                      R_net=np.full(61, np.nan))
        report = owners_return(dict(series=series, owned=nothing[:, None], economy=w, vintage=record), w)
        self.assertEqual(report["by_loan_year_own"], dict(all=[6.667, -15.2, None, None, None],
                                                          bridge=[12.0, None, None, None, None],
                                                          term=[6.0, -15.2, None, None, None]))
        self.assertEqual(report["by_loan_year"], dict(all=[7.333, -15.2, None, None, None],
                                                      bridge=[13.2, None, None, None, None],
                                                      term=[6.6, -15.2, None, None, None]))
        self.assertEqual(report["shared_unallocated_usd"], -12.88)
        json.dumps(report)

    def test_crossings_count_each_persons_net_move_in_a_step(self):
        """Crossings count each person's net move between E and P in a step.

        Example ($): a participant paying a $40 bill in E from its P crosses once for $40, and its payee, outside
        P and paid in E, does not. $50 swept into P and paid out in E within one step does not cross; split over two
        steps it crosses twice. Joining, leaving and P redeemed by a non-participant are conversions, valued before
        the fee."""
        w = controlled_world()
        w.part[[0, 2, 5]] = True
        w.pcash[0] = 100 / MONTH_USD
        w.acc["crossings"][:] = w.acc["crossed"][:] = 0.0
        one_invoice(w, 40 / MONTH_USD, card=False)
        w._settle(1, 30)
        w._count_crossings()
        np.testing.assert_array_equal(w.acc["crossings"][0], np.arange(10) == 0)
        self.assertAlmostEqual(float(w.acc["crossed"][0, 0]), 40 / MONTH_USD, places=15)
        self.assertEqual(float(w.acc["crossings"][1].sum()), 0.0)
        pay = (np.arange(10) == 2) * 50 / MONTH_USD
        w.cash[2] = 50 / MONTH_USD
        w._cover()                                                   # swept into P
        w._debit(np.zeros(10), pay)                                  # and paid out in E the same step
        w._count_crossings()
        self.assertEqual(float(w.acc["crossings"][0, 2]), 0.0)
        w.cash[2] = 50 / MONTH_USD
        w._cover()
        w._count_crossings()
        w._debit(np.zeros(10), pay)
        w._count_crossings()
        self.assertEqual(float(w.acc["crossings"][0, 2]), 2.0)
        self.assertAlmostEqual(float(w.acc["crossed"][0, 2]), 100 / MONTH_USD, places=15)
        w.cash[3] = 1.0
        w._join(np.arange(10) == 3, np.ones(10))
        w.pcash[5] = 1.0
        w._leave(np.arange(10) == 5)
        w._credit_p(np.array([4]), np.array([0.2]))
        w._count_crossings()
        np.testing.assert_array_equal(w.acc["crossings"][1], np.isin(np.arange(10), (3, 4, 5)))
        np.testing.assert_allclose(w.acc["crossed"][1, [3, 4, 5]], [1 / (1 + CONVERSION_FEE), 0.2, 1.0], rtol=1e-12)
        # The conversions add no routine crossing, and each fold closes its step.
        np.testing.assert_array_equal(w.acc["crossings"][0], (np.arange(10) == 0) + 2 * (np.arange(10) == 2))
        self.assertEqual(float(np.abs(w.crossed).sum()), 0.0)

    def test_crossings_are_zero_without_p(self):
        """Without P there is nothing to cross: S0 never crosses, and M1 does not before launch."""
        s0, m1 = (simulate(Inputs(), 0.6, TINY, arm)["series"] for arm in ("S0", "M1"))
        for key in ("crossings", "crossed", "conversions", "converted"):
            self.assertEqual(float(np.abs(s0[key]).sum()), 0.0, key)
            self.assertEqual(float(np.abs(m1[key][:TINY.burn_in]).sum()), 0.0, key)
        self.assertGreater(float(m1["conversions"][TINY.burn_in]), 0.0)   # the launch conversions

    def test_crossings_report_reads_the_hand_case(self):
        """The crossings report counts routine crossings and conversions.

        Example ($): one person over a year after launch: 20 routine crossings of $50 every month and one $3,220
        conversion at launch are 240 crossings and $12,000 a year and one conversion of $3,220; a participant half the
        time crosses 480 times a participant-year."""
        from scripts.run_economy_population import crossings
        w = Economy(n=1, burn_in=1, months=12)
        after = np.r_[0.0, np.ones(12)]
        series = dict(crossings=20 * after, crossed=20 * 50 / MONTH_USD * after, A=after,
                      conversions=np.r_[0.0, 1.0, np.zeros(11)], converted=np.r_[0.0, 3220 / MONTH_USD, np.zeros(11)])
        report = crossings(dict(series=series), w)
        self.assertEqual(report["routine"], dict(a_year=240.0, a_participant_year=240.0, usd_a_year=12000.0))
        self.assertEqual(report["conversions"], dict(a_year=1.0, usd_a_year=3220.0))
        half = crossings(dict(series=dict(series, A=after / 2)), w)
        self.assertEqual(half["routine"]["a_participant_year"], 480.0)
        self.assertIsNone(crossings(dict(series=dict(series, A=0 * after)), w)["routine"]["a_participant_year"])

    def test_seed_means_skip_undefined_seeds(self):
        """A value undefined in a seed (None) is left out of the cell's mean; undefined in every seed it stays None."""
        from scripts.run_economy_population import seed_nanmeans
        self.assertEqual(seed_nanmeans([dict(a=None), dict(a=2.0), dict(a=4.0)]), dict(a=3.0))
        self.assertEqual(seed_nanmeans([dict(a=[None, 1.0]), dict(a=[None, 2.0])]), dict(a=[None, 1.5]))
        self.assertIsNone(seed_nanmeans([None, None]))

    def test_pool_series_change_no_outcome(self):
        """Owners' income, their holdings and crossings change no outcome: the same small economy with all
        three silenced gives every other record exactly, in M0, M1 and M2 (the test device, whose pool forms), and in
        forced runs whose owners ask to exit: M1 and M2 with distress, and over 24 months M2 without and M1 with
        distress, in each of which the pool's float reaches the silenced owners' income."""
        def silence(base):
            quiet = dict(_crossed=lambda self, *args, **kwargs: None, _count_crossings=lambda self: None,
                         _holdings=lambda self: None,
                         _owners_income=lambda self, R: (np.nan, 0.0, 0.0, 0.0))
            return type("Silent", (base,), quiet)
        # The yardsticks' records read owners' holdings and income too: the income in the joint test.
        new = ("owners_capital", "owners_income", "owners_income_net", "R_net", "crossings", "crossed", "conversions",
               "converted", "owned", "own_margin", "joint")
        economy = replace(TINY, n=100, months=12)
        for arm, base, w in (("M0", _World, economy), ("M1", PooledWorld, economy), ("M2", PooledWorld, economy),
                             ("M1", ForcedRun, FORCED_DISTRESS), ("M2", ForcedRun, FORCED_DISTRESS),
                             ("M2", ForcedRun, FORCED_LONG), ("M1", ForcedRun, FORCED_DISTRESS_LONG)):
            run, silent = kept_run(base, arm, w), silence(base)(Inputs(), 0.6, w, arm).run()
            after = slice(w.burn_in, None)
            self.assertGreater(float(run["series"]["crossings"][after].sum()), 0.0, arm)     # the records are live
            self.assertGreater(float(run["crossings"].sum()), 0.0, arm)
            self.assertEqual(float(silent["crossings"].sum() + silent["owned"].sum()), 0.0)
            if arm != "M0":
                self.assertGreater(float(run["owned"].sum()), 0.0, arm)
            if base is ForcedRun:
                self.assert_exits_reached(run, arm)
                if w.distress > 0:
                    self.assertGreater(float(run["series"]["laid_off"].max()), 0.0, arm)
                self.assertGreater(float(run["series"]["float_pool"].sum()), 0.0, arm)   # the float reached the pool
            self.assert_same_outcome(run, silent, new)

    def test_loan_year_record_changes_no_outcome(self):
        """Owners' return by loan year changes no outcome: forced runs with distress in M1 and M2 (the test
        device, whose pool lends, writes loans off and recovers on them) with the record silenced and bridges undated
        give every other record exactly. The silenced run reads the books R reads, where R reads them; as every other
        record is the same, they are the live run's, and the live record adds up to them each month: its income to
        the coupons less the operating cost, write-offs and recoveries, in all and by product, and its
        principal-time to the pool's, and with the pool-wide income to the owners' income less the holding charge's
        (demurrage) revenue (the pool's float and the charge) in every month the pool has capital. No band holds a
        loan before its year, and bridges of the second year are dated.

        A due bridge is collected before overdue wages, so the runs are 36 months long with 10 points of distress
        for a year. A missed instalment is collected from all money too, so no forced run leaves a pool loan unpaid
        for 90 days; the test device therefore writes a loan off 10 days past due, which exercises the same
        write-off and recovery paths sooner. Under the harsh stress a year at 10 points sends so many wages outside
        that by month 34 four payers with no money owe each other a ring of late wages (one owes 123 months of its
        spending), whose settlement reaches its fixed point only slowly, so the run allows 20,000 sweeps a day; a
        day that converges within the engine's 500 is unchanged by the cap."""
        from unittest import mock
        from cpm_abm import economy_abm
        from cpm_abm.engine import world_credit   # where _write_off looks WRITE_OFF_DAYS up
        class Silent(ForcedRun):
            def _by_loan_year(self, rows, income, exposure=0.0):
                pass

            def _add_loans(self, borrower, pool, kind, principal, rate, alt, due, months=None, m0=0, card_part=0.0,
                           cover=0.0, business=False):
                # A cash advance keeps its month, which the replays' card room reads.
                super()._add_loans(borrower, pool, kind, principal, rate, alt, due, months,
                                   m0 if kind in (TERM, CASH_ADVANCE) else 0, card_part, cover, business)

            def _owners_income(self, R):
                acc = self.acc
                revenue = acc["float_pool"] + float(acc["charges"].sum())   # demurrage's, which the record leaves out
                self.books.append([acc["coupons"] - acc["op_cost"] - acc["written_off"] + acc["recovered"],
                                   acc["written_off"], acc["recovered"], acc["bridge_coupons"], *acc["lost"],
                                   *acc["exposure"], R * self.capital - revenue if self.capital > 0 else np.nan])
                return super()._owners_income(R)

        w, o = replace(FORCED_DISTRESS_LONG, distress=0.1, distress_length=12, months=36, sweeps=20000), Inputs().o
        total = w.burn_in + w.months
        early = np.arange(total)[:, None, None] < w.burn_in + 12 * np.arange(LOAN_YEARS)[None, None, :]
        for arm in ("M1", "M2"):
            # Both runs are made here, under the short write-off period, and neither is kept for another test.
            with mock.patch.object(world_credit, "WRITE_OFF_DAYS", 10):
                run, world = ForcedRun(Inputs(), 0.6, w, arm).run(), Silent(Inputs(), 0.6, w, arm)
                world.books = []
                silent = world.run()
            books = np.array(world.books)                                    # one row a month
            self.assertEqual(books.shape, (total, 9))
            loans, written, recovered, bridge_coupons, lost_bridge, _, carried_bridge, carried_term, net = books.T
            income, exposure = (run["vintage"][key] * w.n for key in ("income", "exposure"))
            self.assertEqual(income.shape, (total, 2, LOAN_YEARS))
            self.assertGreater(float(run["series"]["new_pool_loans"].sum()), 0.0, arm)   # loans, write-offs and
            self.assertGreater(float(written.max()), 0.0, arm)                             # recoveries occur
            self.assertGreater(float(recovered.max()), 0.0, arm)
            np.testing.assert_allclose(income.sum(axis=(1, 2)), loans, rtol=1e-9, atol=1e-14)
            np.testing.assert_allclose(income[:, 0].sum(axis=1),
                                       bridge_coupons - o * carried_bridge - lost_bridge, rtol=1e-9, atol=1e-14)
            np.testing.assert_allclose(exposure.sum(axis=2), np.c_[carried_bridge, carried_term], rtol=1e-9,
                                       atol=1e-14)
            np.testing.assert_allclose(exposure.sum(axis=(1, 2)) / w.n, run["series"]["pool_pt"], rtol=1e-9,
                                       atol=1e-15)
            pooled = np.isfinite(net)
            self.assertTrue(pooled.any(), arm)
            np.testing.assert_allclose((income.sum(axis=(1, 2)) + run["vintage"]["shared"] * w.n)[pooled], net[pooled],
                                       rtol=1e-9, atol=1e-14)
            self.assertFalse(np.any(np.where(early, exposure, 0.0)), arm)
            self.assertGreater(float(exposure[:, 0, 1].sum()), 0.0, arm)
            self.assertFalse(any(silent["vintage"][key].any() for key in ("income", "exposure")))
            self.assert_same_outcome(run, silent, ("vintage",))

    # ---- The buffers people choose ---------------------------------------------------------------------------------
    def test_buffers_are_kept_by_person_and_month_and_by_card_holding(self):
        """Buffers are recorded by person and month and averaged by card holding.

        Example ($): at a month's dealing four card holders chose buffers of $0, $644, $1,288 and $3,220 and six
        people without a card $322 each, so the means are $1,288 and $322; with nobody without a card that mean is
        undefined. In short runs of S0 and M1 (the test device, whose pool forms) each person's record is the buffer
        the dealing chose, in months of mean spending, and the series are its means by card holding. The means read each
        person's class, the population's card holding, which a closed line does not change, so the example sets the
        population's holding."""
        w = controlled_world()
        w.holder[:4] = w.pop["holder"][:4] = True
        w.pop["holder"][4:] = False
        w.buffer[:] = np.r_[0.0, 644.0, 1288.0, 3220.0, np.full(6, 322.0)] / MONTH_USD
        w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
        self.assertAlmostEqual(w.series["buffer_card"][-1] * MONTH_USD, 1288.0, places=9)
        self.assertAlmostEqual(w.series["buffer_nocard"][-1] * MONTH_USD, 322.0, places=9)
        np.testing.assert_array_equal(w.buffer_path[1], w.buffer)
        w.pop["holder"][:] = True
        self.assertTrue(np.isnan(w._buffers()[1]))

        def watched(base):
            """The world with a copy of each month's buffer taken right after the dealing chose it."""
            def dealing(self, month):
                capital = base._dealing(self, month)
                self.chosen.append(self.buffer.copy())
                return capital
            return type("Watched", (base,), dict(_dealing=dealing))
        for arm, base in (("S0", _World), ("M1", PooledWorld)):
            world = watched(base)(Inputs(), 0.6, TINY, arm)
            world.chosen = []
            run = world.run()
            buffers, holder = run["buffers"], run["population"]["holder"]
            np.testing.assert_array_equal(buffers, np.array(world.chosen))
            self.assertGreater(float(buffers[1:].sum()), 0.0, arm)
            np.testing.assert_allclose(run["series"]["buffer_card"], buffers[:, holder].mean(axis=1), rtol=1e-12)
            np.testing.assert_allclose(run["series"]["buffer_nocard"], buffers[:, ~holder].mean(axis=1), rtol=1e-12)

    def test_buffer_record_changes_no_outcome(self):
        """The buffers kept by person and month and their means by card holding change no outcome:
        the same small economy with the record silenced gives every other record exactly, in S0 and M1 (the test
        device, whose pool forms)."""
        silence = lambda base: type("Silenced", (base,), dict(_buffers=lambda self: (np.zeros(self.n), np.nan, np.nan)))
        economy = replace(TINY, n=100, months=12)
        for arm, base in (("S0", _World), ("M1", PooledWorld)):
            run, silenced = kept_run(base, arm, economy), silence(base)(Inputs(), 0.6, economy, arm).run()
            self.assertGreater(float(run["buffers"].sum()), 0.0, arm)          # the record is live
            self.assertTrue(np.all(np.isfinite(run["series"]["buffer_card"])), arm)
            self.assertEqual(float(silenced["buffers"].sum()), 0.0)
            self.assert_same_outcome(run, silenced, ("buffers", "buffer_nocard", "buffer_card"))

    # ---- The household economy and failure cost -------------------------------------------------------------------
    def test_the_replay_counts_a_requeued_wage_once(self):
        """The replay counts a re-queued wage once.

        Example ($): a $100 wage from person 3 to person 4, whose cycle is one day (wages on billing dates, so the
        wage is re-queued daily), with no money for five settlement days and $100 on the sixth. The six days of
        payer 3's own cash flow add up to -$100: the wage once, on the day it first fell due, its later failures
        adding nothing and its payment taken back out of the day it is paid. With ``requeued_once`` off, each failed
        retry counts again and the payment once more: -$600."""
        def flows(requeued_once):
            w = controlled_world("S0")
            w.economy = replace(w.economy, pay_dates=False, requeued_once=requeued_once)
            w.pop["cycles"][4], w.pop["phases"][4] = 1, 0
            w.ob = dict(buyer=np.array([3]), seller=np.array([4]), amount=np.array([100 / MONTH_USD]),
                        settle=np.array([DAYS]), card=np.array([False]), kind=np.array([WAGE]))
            w.receivable[4] = w.payable[3] = 100 / MONTH_USD
            for d in range(6):
                w.cash[3] = 100 / MONTH_USD if d == 5 else 0.0
                w.day(1, d)
            self.assertAlmostEqual(float(w.payable[3]), 0.0, places=15)                # paid on the sixth day
            return float(w.acc["flows"][3, :6].sum()) * MONTH_USD
        self.assertAlmostEqual(flows(True), -100.0, places=9)
        self.assertAlmostEqual(flows(False), -600.0, places=9)

    def test_wages_settle_on_their_jobs_pay_dates_at_bls_frequencies(self):
        """Wages settle on their job's pay dates at BLS frequencies.

        Example: a weekly job with phase 3 and a $10 daily wage settles month 0's wages on days 3, 10, 17,
        24 and 31 with $40, $70, $70, $70 and $50, whatever its recipient's billing cycle (daily or 60-day); a job paid
        twice a month, phase 4, pays exactly twice in month 1, on days 34 and 49, 15 days' wages each time. At 1,000
        people the pay periods follow the BLS shares in exact proportion, each phase within its period."""
        def wages(days, phase, cycle, months=(0,)):
            world = tiny_world()
            world.acc = dict(shocks=0.0, volume=0.0)
            world.pop["pay_days"][0], world.pop["pay_phase"][0] = days, phase
            recipient = world.pop["wage_to"][0]
            world.pop["cycles"][recipient], world.pop["phases"][recipient] = cycle, 0
            world.spending[0] = 10 / MONTH_USD * DAYS / LABOUR_SHARE
            list(map(world._obligations, months))
            mine = (world.ob["kind"] == WAGE) & (world.ob["buyer"] == 0)
            return world.ob["settle"][mine], world.ob["amount"][mine] * MONTH_USD
        for cycle in (1, 60):
            settle, amount = wages(7, 3, cycle)
            np.testing.assert_array_equal(settle, [3, 10, 17, 24, 31])
            np.testing.assert_allclose(amount, [40.0, 70.0, 70.0, 70.0, 50.0], rtol=1e-12)
        settle, amount = wages(15, 4, 1, months=(0, 1))
        month_1 = (settle >= DAYS) & (settle < 2 * DAYS)
        dates, where = np.unique(settle[month_1], return_inverse=True)
        np.testing.assert_array_equal(dates, [34, 49])
        np.testing.assert_allclose(np.bincount(where, weights=amount[month_1]), [150.0, 150.0], rtol=1e-12)
        pop = build_population(Economy(n=1000))
        counts = np.array([np.sum(pop["pay_days"] == days) for days in PAY_DAYS])
        np.testing.assert_array_less(np.abs(counts - PAY_SHARES / PAY_SHARES.sum() * 1000), 1.0)
        self.assertEqual(int(counts.sum()), 1000)
        self.assertTrue(np.all((pop["pay_phase"] >= 0) & (pop["pay_phase"] < pop["pay_days"])))

    def test_a_failed_wage_is_requeued_to_its_jobs_next_pay_date(self):
        """A weekly job (phase 2) whose $100 wage fails on its pay date, day 30, is re-queued to the job's next pay
        date, day 37; with ``pay_dates`` off, to its recipient's next billing date, day 31 on a daily cycle."""
        def later(pay_dates):
            w = controlled_world("S0")
            w.economy = replace(w.economy, pay_dates=pay_dates)
            w.pop["pay_days"][3], w.pop["pay_phase"][3] = 7, 2
            w.pop["cycles"][4], w.pop["phases"][4] = 1, 0
            w.ob = dict(buyer=np.array([3]), seller=np.array([4]), amount=np.array([100 / MONTH_USD]),
                        settle=np.array([DAYS]), card=np.array([False]), kind=np.array([WAGE]))
            w.receivable[4] = w.payable[3] = 100 / MONTH_USD
            w._settle(1, DAYS)
            return int(w.ob["settle"][w.ob["kind"] == LATE_WAGE][0])
        self.assertEqual((later(True), later(False)), (37, 31))

    def test_a_lean_month_costs_54_dollars_at_two_fees_and_81_at_three(self):
        """A lean month costs $54 at a cap of two fees and $81 at three.

        Example ($): a payer without a card or money owes a $100 bill on each of days 30, 35, 40 and 45. All four
        fail in full (4 unpaid shares and fee units), but at most two fees a model month are charged: $27, $27 and
        nothing twice, $54, booked as fee debt. With $50 of cash before each bill, half of each fails, half a fee a
        day: fees on four days make $54 and the other three carry none. A bill on day 60, after the count resets on
        day 1, carries $27 again. At a cap of three fees a month: $27 three times, $81, fees on six days and $27
        again after the reset."""
        def bills(days, cash=0.0, cap=None):
            w = controlled_world("S0")
            if cap is not None:
                w.economy = replace(w.economy, fees_a_month=cap)
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS + ("fee",)))
            charged = []
            for day in days:
                w.cash[0] = cash / MONTH_USD
                one_invoice(w, 100 / MONTH_USD, at=day, card=False)
                before = float(w.acc["fee"][0])
                w._settle(day // DAYS, day)
                charged.append(round((float(w.acc["fee"][0]) - before) * MONTH_USD, 9))
            return w, charged
        for cap, fees in ((None, 2), (3.0, 3)):
            w, charged = bills((30, 35, 40, 45), cap=cap)
            self.assertEqual(w.economy.fees_a_month, float(fees))
            self.assertEqual(charged, [27.0] * fees + [0.0] * (4 - fees))
            debt = float(w.book["principal"][w.book["kind"] == FEE_DEBT].sum()) * MONTH_USD
            self.assertAlmostEqual(debt, 27.0 * fees, places=9)
            self.assertEqual(tuple(float(w.acc[key][0]) for key in ("fail_shares", "fail_units", "fee_units")),
                             (4.0, 4.0, float(fees)))
            w.acc["fee_units"] = np.zeros(w.n)   # day 1 of the next month: ``month`` rebuilds every accumulator
            one_invoice(w, 100 / MONTH_USD, at=2 * DAYS, card=False)
            w._settle(2, 2 * DAYS)
            self.assertAlmostEqual(float(w.acc["fee"][0]) * MONTH_USD, 27.0 * (fees + 1), places=9)
            _, charged = bills(range(DAYS, DAYS + 7), cash=50.0, cap=cap)
            self.assertEqual(charged, [13.5] * (2 * fees) + [0.0] * (7 - 2 * fees))

    def test_the_buffer_replay_prices_failures_past_the_cap_at_27_and_the_experience_replays_at_0(self):
        """The buffer replay prices failures past the cap at $27 and the experience replays at $0.

        Example: failures of 0.1 on days 5, 10, 15 and 20 from no buffer, at 1.0 a unit and at most
        0.05 a day. The buffer replay prices all four, 0.20 ($27 past the cap); the experience replays three, 0.15 ($0
        past it, what the wallet pays). In a run the dealing's replay is given no monthly limit and both experience
        replays the month's cap of fees (``fees_a_month``, two); with the device off
        (``buffer_prices_past_cap``) the dealing's replay the cap too, and with no monthly cap no replay has a
        limit."""
        from unittest import mock
        from cpm_abm import economy_abm
        from cpm_abm.engine import world_close, world_dealing   # where _dealing and _close look choose_buffer up
        flows = np.zeros((1, DAYS))
        flows[0, [5, 10, 15, 20]] = -0.1
        one = lambda x: np.full(1, x)
        cost = lambda **month: float(replay_cost(flows, np.zeros((1, 1)), one(0.0), one(0.0), one(1.0), fail_cap=0.05,
                                                 **month)[0, 0])
        self.assertAlmostEqual(cost(), 0.20, places=15)
        self.assertAlmostEqual(cost(fail_month=0.15), 0.15, places=15)

        def limits(economy):
            """The monthly limit each replay of a two-month S0 run was given, in the order they ran (the experience
            replays forced: an S0 run reads none of them and skips them, ``_World._experience_unread``)."""
            with mock.patch.object(world_dealing, "choose_buffer", wraps=economy_abm.choose_buffer) as replay,                     mock.patch.object(world_close, "choose_buffer", replay),                     mock.patch.object(_World, "_experience_unread", lambda self: False):
                simulate(Inputs(), 0.6, economy, "S0")
            return [call.kwargs.get("fail_month") for call in replay.call_args_list]
        w = Economy(n=20, burn_in=1, months=1)
        cap = w.fees_a_month * FAIL_FEE
        self.assertEqual(w.fees_a_month, 2.0)
        self.assertEqual(limits(w), [cap, cap, None, cap, cap])                 # close; dealing, close
        self.assertEqual(limits(replace(w, buffer_prices_past_cap=False)), [cap] * 5)
        self.assertEqual(limits(replace(w, fees_a_month=3.0)), [3 * FAIL_FEE, 3 * FAIL_FEE, None, 3 * FAIL_FEE,
                                                                 3 * FAIL_FEE])
        self.assertEqual(limits(replace(w, fees_a_month=np.inf)), [None] * 5)

    def test_fee_debt_is_repaid_before_card_debt(self):
        """Fee debt is repaid before card debt.

        Example ($): a card holder owes $27 of fee debt and $100 revolving on the card at 28.49% a year, and repays
        from $50: the fee first ($27), then $23 to the card. Were the fee outside debt at 22% a year, repaid dearest
        first, the card would take all $50. Fee debt accrues nothing: still $27 after 30 days."""
        def repay(kind, rate):
            w = controlled_world("S0")
            w.holder[0], w.cash[0] = True, 50 / MONTH_USD
            w._add_loans(np.array([0]), False, kind, np.array([27 / MONTH_USD]), rate, rate, BIG)
            w._add_loans(np.array([0]), False, REVOLVE, np.array([100 / MONTH_USD]), 0.2849 / 12, 0.2849 / 12, BIG)
            w._repay(np.maximum(w.cash + w.pcash, 0.0))
            self.assertAlmostEqual(float(w.cash[0]), 0.0, places=15)
            return (w.book["principal"] + w.book["interest"]) * MONTH_USD
        np.testing.assert_allclose(repay(FEE_DEBT, 0.0), [0.0, 77.0], atol=1e-9)
        np.testing.assert_allclose(repay(OVERDRAFT, Inputs().r_ext), [27.0, 50.0], atol=1e-9)
        w = controlled_world("S0")
        w._add_loans(np.array([0]), False, FEE_DEBT, np.array([27 / MONTH_USD]), 0.0, 0.0, BIG)
        list(map(lambda day: w._accrue(), range(DAYS)))
        np.testing.assert_allclose((w.book["principal"] + w.book["interest"]) * MONTH_USD, [27.0], rtol=1e-12)

    def test_the_real_failure_line_counts_unpaid_and_bridged_shares(self):
        """The real failure line counts unpaid and bridged shares.

        Examples ($): one person over one month after launch, at $2 a unit whatever the fee and the cap. Two
        $40 bills against $30 of cash: 1.25 unpaid shares (as the settlement counts them), $2.50 (against $2.00 for
        one fee unit), with the two whole bills returned, $4.00, beside it. With half a bill bridged by the pool for
        a payer without a card, $3.50 (against $4.00 with the bridged payer-day added). Three $14 bills against $41:
        3/42 shares, $0.14. A bridged card-eligible purchase is card credit by its principal-time, with its $2 reading
        beside: a $1,000 bridge held a month costs $2.83, and the pool's sourced cost adds the bridged share's $1."""
        from scripts.run_economy_population import real_part
        w = Economy(n=1, burn_in=1, months=1)

        def read(rule=True, **volumes):
            """The real part of one month's volumes, with the real failure line (``rule``) or the fee-unit line."""
            series = {key: np.zeros(2) for key in REAL_SERIES}
            list(map(lambda item: series[item[0]].__setitem__(1, item[1]), volumes.items()))
            return real_part(dict(arm="S0", series=series), replace(w, failure_shares=rule))
        two = dict(fail_shares=1.25, fail_items=2.0, penalties=FAIL_FEE)
        line = read(**two)
        self.assertEqual((line["failed_payments"], line["failed_payments_items"], line["failed_payments_as_built"]),
                         (2.5, 4.0, 2.0))
        self.assertEqual(read(rule=False, **two)["failed_payments"], 2.0)
        self.assertNotIn("failed_payments_as_built", read(rule=False, **two))
        bridged = dict(two, bridged_shares=0.5, nocard_bridges=1.0)
        self.assertEqual((read(**bridged)["failed_payments"], read(rule=False, **bridged)["failed_payments"]),
                         (3.5, 4.0))
        self.assertEqual(read(fail_shares=3 / 42, penalties=FAIL_FEE * 3 / 42)["failed_payments"], 0.14)
        card = read(pt_pool_nocard_card=1000 / MONTH_USD, bridged_card=0.5, bridged_shares=0.5)
        self.assertEqual((card["card_credit"], card["bridged_card_at_2"], card["pool_sourced_usd"]), (2.83, 1.0, 3.83))
        self.assertEqual(read(rule=False, pt_pool_nocard_card=1000 / MONTH_USD)["card_credit"], 0.0)

    def test_a_pool_bridge_records_the_card_eligible_part_for_a_payer_without_a_card(self):
        """A pool bridge records the card-eligible part for a payer without a card.

        Example ($): the pool bridges a $14 card-eligible purchase and a $40 bill of a payer without a card
        or money. The bill is one bridged share, a replaced failure, and the purchase new lending: 14/54 of the bridge,
        its principal-time counted apart ($14 for a day)."""
        w = controlled_world()
        funded_pool(w)
        w.r_g = w.r_b = 0.005
        w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
        w.last["receipts"][:] = 1.0
        list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS))
        w.acc["pt_pool_nocard_card"] = 0.0
        w.ob = dict(buyer=np.zeros(2, int), seller=np.array([1, 2]), amount=np.array([14.0, 40.0]) / MONTH_USD,
                    settle=np.full(2, DAYS), card=np.array([True, False]), kind=np.full(2, SERVICE))
        w.receivable[1:3] = w.ob["amount"]
        w.payable[0] = w.ob["amount"].sum()
        w._settle(1, DAYS)
        bridge = w.book["pool"]
        np.testing.assert_allclose(w.book["principal"][bridge] * MONTH_USD, [54.0], rtol=1e-12)
        np.testing.assert_allclose(w.book["card_part"][bridge], [14 / 54], rtol=1e-12)
        self.assertEqual(float(w.book["card_part"][~bridge].sum()), 0.0)
        self.assertEqual(tuple(round(float(w.acc[key][0]), 12) for key in ("bridged_shares", "bridged_card",
                                                                           "fail_shares")), (1.0, 1.0, 0.0))
        w._accrue()
        self.assertAlmostEqual(w.acc["pt_pool_nocard_card"] * MONTH_USD, 14.0 / DAYS, places=12)

    # ---- Earned-wage access and payers in chronic deficit ---------------------------------------------------------
    @staticmethod
    def wage_case(arm="S0", bill=100.0, on=40, spell=(0, 0)):
        """The world of the earned-wage examples ($): job 2 pays person 1 monthly, on day 59, and is in a spell on
        the days ``spell`` gives; person 1 holds earned-wage access, has no card and no money, and owes a bill of
        ``bill`` to person 5 on day ``on``, when $330 is earned and still unpaid (11 days at $30). The month's $900 wage
        row settles on day 59; payer 2 has no money. The month's accumulators are emptied."""
        w = controlled_world(arm)
        w.pop["wage_to"][2], w.pop["pay_days"][2], w.pop["pay_phase"][2] = 1, 30, 29
        w.pop["ewa"][:] = np.arange(10) == 1
        w.spell_start[:], w.spell_end[:] = 0, 0
        w.spell_start[2], w.spell_end[2] = spell
        w.accrued[2] = 330 / MONTH_USD
        w.ob = dict(buyer=np.array([1, 2]), seller=np.array([5, 1]), amount=np.array([bill, 900.0]) / MONTH_USD,
                    settle=np.array([on, 59]), card=np.zeros(2, bool), kind=np.array([SERVICE, WAGE]))
        w.receivable[[5, 1]] = w.payable[[1, 2]] = w.ob["amount"]
        list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0),
                 ("ewa_uses", "ewa_value", "ewa_fees", "fee") + FAILURE_COUNTS))
        return w

    def test_earned_wage_access_applies_only_to_earned_unpaid_wages_and_is_repaid_first_from_them(self):
        """Earned-wage access applies only to earned, unpaid wages and is repaid first from them.

        Examples ($): person 1, with no card or money, owes a $100 bill on day 40, when
        $330 of job 2's wage is earned and unpaid: it advances $100, owes $102.45 against job 2, the $2.45 fee leaves
        the economy, no failure fee is charged and nothing fails. On day 59 payer 2 pays the $900 wage: the advance is
        taken from it first, so person 1 keeps $797.55 and owes nothing. A $200 bill instead: half of the $330, $165,
        is advanced and $35 fails, 0.175 of a fee ($4.725). With job 2 in a spell on day 40 nothing is advanced and the
        bill fails with its $27. If payer 2 cannot pay on day 59 the wage is re-queued and $102.45 is still owed; the
        re-queued $900 is still earned and unpaid, so a $400 bill on day 60 is advanced $350 (half of it less the $100
        advanced) and $50 fails; and when payer 2 later pays $400 of the overdue wage, person 1 receives $297.55. In a
        run, a job's accruals are all due on its pay dates: none is left the day the job pays."""
        usd = lambda value: round(float(value) * MONTH_USD, 9)
        w = self.wage_case()
        w._settle(1, 40)
        self.assertEqual((usd(w.acc["ewa_value"][1]), usd(w.ewa_owed[2]), usd(w.external)), (100.0, 102.45, -2.45))
        self.assertEqual((usd(w.acc["fee"][1]), float(w.acc["fail_shares"][1]), usd(w.payable[1])), (0.0, 0.0, 0.0))
        self.assertEqual((float(w.acc["ewa_uses"][1]), usd(w.acc["ewa_fees"][1]), usd(w.cash[1])), (1.0, 2.45, 0.0))
        self.assertAlmostEqual(usd(w.net_wealth()[1]), 797.55, places=9)     # the wage is receivable, the advance owed
        w.cash[2] = 900 / MONTH_USD
        w._settle(1, 59)
        self.assertEqual((usd(w.cash[1]), usd(w.ewa_owed.sum()), usd(w.accrued[2])), (797.55, 0.0, 0.0))
        w = self.wage_case(bill=200.0)
        w._settle(1, 40)
        self.assertEqual((usd(w.acc["ewa_value"][1]), usd(w.acc["fee"][1]), round(float(w.acc["fail_shares"][1]), 12)),
                         (165.0, 4.725, 0.175))
        self.assertAlmostEqual(usd(w.ewa_owed[2]), 165 * (1 + EWA_FEE), places=9)
        w = self.wage_case(spell=(35, 50))
        w._settle(1, 40)
        self.assertEqual((usd(w.acc["ewa_value"][1]), usd(w.acc["fee"][1]), usd(w.ewa_owed.sum())), (0.0, 27.0, 0.0))
        w = self.wage_case()
        w._settle(1, 40)
        w._settle(1, 59)
        late = w.ob["kind"] == LATE_WAGE
        self.assertEqual((w.ob["settle"][late].tolist(), usd(w.ob["amount"][late].sum())), ([89], 900.0))
        self.assertEqual((usd(w.ewa_owed[2]), usd(w.cash[1])), (102.45, 0.0))
        requeued = {key: value[late] for key, value in w.ob.items()}
        bill = dict(buyer=[1], seller=[5], amount=[400 / MONTH_USD], settle=[60], card=[False], kind=[SERVICE])
        w.ob = {key: np.concatenate([value, requeued[key]]) for key, value in bill.items()}
        w.acc["ewa_value"][:] = 0.0
        w._settle(2, 60)
        self.assertEqual((usd(w.acc["ewa_value"][1]), round(float(w.acc["fail_shares"][1]), 12)), (350.0, 0.125))
        w = self.wage_case()
        w._settle(1, 40)
        w._settle(1, 59)
        w.cash[2] = 400 / MONTH_USD
        w._wage_arrears(np.maximum(w.cash + w.pcash, 0.0))
        self.assertEqual((usd(w.cash[1]), usd(w.ewa_owed.sum())), (297.55, 0.0))

        class Watched(_World):
            """A run that reads, after each settlement, what is still accrued on the jobs paying that day."""
            def _settle(self, month, t):
                super()._settle(month, t)
                paying = (t - self.pop["pay_phase"]) % self.pop["pay_days"] == 0
                self.left.append(float(np.abs(self.accrued[paying]).max()) if paying.any() else 0.0)
        world = Watched(Inputs(), 0.6, replace(TINY, n=40, burn_in=1, months=2), "S0")
        world.left = []
        world.run()
        self.assertLess(max(world.left), 1e-12)
        self.assertGreater(float(world.accrued.sum()), 0.0)                   # wages earned and not yet due remain

    def test_the_pool_is_kept_where_no_dearer_than_the_advance_held(self):
        """The pool is kept where it is no dearer than the advance held.

        Example ($): a wage earner without a card, short $84 five days before its covering date,
        can advance it for $2.06 (2.45%); the pool bridge costs about $0.08 (5 days at 4.44%, the owners' 0.25 point and
        2% a year, its full coupon), so the payer stays in the pool's queue and the pool lends the $84. With a coupon of
        2% a month over 60 days (a factor of 1.04, above 1.0245) the pool is dearer: the payer leaves the queue and
        advances the $84, owing $86.06. Without access a payer without a card is never dearer, its alternative being
        failure."""
        draw, room, ahead = (np.zeros(10) for _ in range(3))
        draw[0], room[0] = 84 / MONTH_USD, 165 / MONTH_USD

        def world(coupon=None, cycle=30):
            """The M1 world: everyone participates and the pool is funded; person 0's covering date is its next own
            billing date, 5 days after day 40 on a 30-day cycle and 60 days after on a 60-day one."""
            w = controlled_world()
            funded_pool(w)
            w.r_g = w.r_b = w.r_g if coupon is None else coupon
            w.pop["cycles"][0], w.pop["phases"][0] = cycle, (40 + (5 if cycle == 30 else 0)) % cycle
            w.last["receipts"][:] = 1.0
            # The budget expects wages on their jobs' pay dates, and the quiet month's wage to person 0 would date
            # the draw on day 42, an incoming job's pay date. The example's receipts are none of them wages, so the
            # covering date stays person 0's own billing date.
            w.last["wages_paid"][:] = 0.0
            w.pop["wage_to"][3], w.pop["ewa"][:] = 0, np.arange(10) == 0
            w.spell_start[:], w.spell_end[:] = 0, 0
            w.accrued[3] = 330 / MONTH_USD
            w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([84 / MONTH_USD]),
                        settle=np.array([40]), card=np.array([False]), kind=np.array([SERVICE]))
            w.receivable[1] = w.payable[0] = 84 / MONTH_USD
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), ("ewa_value", "ewa_fees", "fee")))
            return w
        w = world()
        due = w._due_c1(np.array([0]), draw[:1], 40, ahead=ahead[:1])
        self.assertEqual(due.tolist(), [45])
        self.assertAlmostEqual(float(w._pool_factor(40, due)[0] - 1) * 84,
                               (0.0037 + 0.0025 / 12 + 0.02 / 12) * 5 / 30 * 84, places=12)
        self.assertAlmostEqual(EWA_FEE * 84, 2.058, places=12)
        self.assertEqual((bool(w._dearer(draw, 40, ahead)[0]), bool(w._dearer(draw, 40, ahead, room)[0])),
                         (False, False))
        w._settle(1, 40)
        self.assertEqual((round(float(w.book["principal"][w.book["pool"]].sum()) * MONTH_USD, 9),
                          float(w.acc["ewa_value"][0])), (84.0, 0.0))
        w = world(coupon=0.02, cycle=60)
        self.assertEqual(w._due_c1(np.array([0]), draw[:1], 40, ahead=ahead[:1]).tolist(), [100])
        self.assertEqual((bool(w._dearer(draw, 40, ahead)[0]), bool(w._dearer(draw, 40, ahead, room)[0])),
                         (False, True))
        w._settle(1, 40)
        self.assertEqual(float(w.book["principal"][w.book["pool"]].sum()), 0.0)
        usd = lambda value: round(float(value) * MONTH_USD, 9)
        self.assertEqual((usd(w.acc["ewa_value"][0]), usd(w.ewa_owed[3]), usd(w.acc["fee"][0])), (84.0, 86.058, 0.0))

    def test_pool_limit_counts_the_advance_and_its_fee_ahead_of_the_draw(self):
        """The same-day limit with earned-wage access, in the units of the other limit cases: short 300, room
        100, receipts 250, the pool at 1.01, the fee 0.28 a failed unit and at most 28, the advance at 1.0245. The debt
        is 130.45 with no draw and 231.45 at a draw of 100, where the fee stops binding at its cap; it then rises 0.73
        a unit, so the pool lends 100 + 18.55 / 0.73 = 125.41: with the advance of 100 and a fee of 20.885 on the 74.59
        that fails, the receipts repay exactly 250. With no room it is the limit without access, (250 - 84) / 0.73;
        with 400 of receipts the pool lends all 300, the last piece falling (the advance dearer than the pool); with
        receipts below 130.45 it lends nothing."""
        case = lambda spare, room: map(np.atleast_1d, (300.0, spare, 1.01, 0.28, 28.0, room))
        limit = lambda spare, room: float(limit_with_advance(*case(spare, room), 1.0245)[0])
        x = limit(250.0, 100.0)
        self.assertAlmostEqual(x, 100 + 18.55 / 0.73, places=9)
        self.assertAlmostEqual(0.28 * (200 - x), 20.885, places=3)
        self.assertAlmostEqual(1.01 * x + 1.0245 * 100 + 0.28 * (200 - x), 250.0, places=9)
        self.assertAlmostEqual(limit(250.0, 0.0), (250 - 84) / 0.73, places=9)
        self.assertEqual((limit(400.0, 100.0), limit(130.0, 100.0)), (300.0, 0.0))
        # With no room it agrees with the limit without access, whatever the case.
        rng = np.random.default_rng(3)
        short, spare, unit, cap = (rng.random(200) * scale for scale in (3.0, 3.0, 0.5, 0.05))
        f_pool = 1 + rng.random(200) * 0.02
        np.testing.assert_allclose(limit_with_advance(short, spare, f_pool, unit, cap, np.zeros(200), 1 + EWA_FEE),
                                   limit_with_fee(short, spare, f_pool, unit, cap), rtol=1e-12, atol=1e-15)

    def test_replays_price_the_advance_per_unit_drawn_before_failure(self):
        """The replays price the advance per unit drawn before failure.

        Example: a dip of 0.3 from day 10 to day 20 from no buffer, a failure costing 0.3 a unit and room
        of 0.2 every day at 2.45% a unit drawn: 0.2 is advanced once (0.0049) and 0.1 fails (0.03), 0.0349 against 0.09
        without access. In a run the dealing's replay and both experience replays read the room at the advance's fee
        for holders of access (S0: nobody admitted by a pool), card holders among them, as holders reach access after
        their cash line, and with no access none does."""
        from unittest import mock
        from cpm_abm import economy_abm
        from cpm_abm.engine import world_close, world_dealing   # where _dealing and _close look choose_buffer up
        flows = np.zeros((1, DAYS))
        flows[0, 10], flows[0, 20] = -0.3, 0.3
        one = lambda x: np.full(1, x)
        cost = lambda **access: float(replay_cost(flows, np.zeros((1, 1)), one(0.0), one(0.0), one(0.3),
                                                  **access)[0, 0])
        self.assertAlmostEqual(cost(advance=np.full((1, DAYS), 0.2), advance_rate=one(EWA_FEE)), 0.0349, places=15)
        self.assertAlmostEqual(cost(), 0.09, places=15)

        def calls(economy):
            """Each replay's room and advance rate in a two-month S0 run, in the order they ran, with the population."""
            world = _World(Inputs(), 0.6, economy, "S0")
            world._experience_unread = lambda: False   # an S0 run reads no experience replay and skips them; forced
            with mock.patch.object(world_dealing, "choose_buffer", wraps=economy_abm.choose_buffer) as replay, \
                    mock.patch.object(world_close, "choose_buffer", replay):
                world.run()
            pairs = [(call.kwargs.get("advance"), call.kwargs.get("advance_rate")) for call in replay.call_args_list]
            return pairs, world
        w = Economy(n=20, burn_in=1, months=1, earned_wage_share=1.0)   # every earner, so some hold no card
        seen, world = calls(w)
        rate = world.pop["ewa"] * EWA_FEE
        self.assertEqual(len(seen), 5)                              # two at each close, one at the second dealing
        for room, advance_rate in seen:
            self.assertEqual(room.shape, (20, DAYS))
            np.testing.assert_array_equal(advance_rate, rate)
        self.assertTrue(rate.any())
        self.assertEqual([pair for pair in calls(legacy(w))[0] if pair != (None, None)], [])

    def test_earned_wage_holders_are_drawn_among_earners_on_their_own_stream(self):
        """Holders are exactly round(share x n) people, 74 of 1,000 at the declared 10 million users over the
        consumer units, all wage earners, the same whatever the arm; a larger share's holders include a smaller one's,
        and the draw moves no other part of the population. In a run, holders of access use it (card holders too,
        after their cash line), wealth accounting stays exact in every arm, and with no access nothing is
        advanced."""
        self.assertAlmostEqual(EWA_SHARE, 10e6 / CONSUMER_UNITS, places=15)
        self.assertEqual((EWA_FEE, EWA_LIMIT, round(EWA_COST * MONTH_USD, 12)), (0.0245, 0.5, 2.0))
        pop = build_population(Economy(n=1000))
        self.assertEqual(int(pop["ewa"].sum()), 74)
        self.assertTrue(np.all(np.isin(np.flatnonzero(pop["ewa"]), pop["wage_to"])))
        wider = build_population(Economy(n=1000, earned_wage_share=0.2))
        self.assertEqual(int(wider["ewa"].sum()), 200)
        self.assertTrue(np.all(wider["ewa"][pop["ewa"]]))
        none = build_population(Economy(n=1000, earned_wage_share=0.0))
        self.assertFalse(none["ewa"].any())
        for key in set(pop) - {"ewa"}:
            np.testing.assert_array_equal(pop[key], none[key], err_msg=key)
        economy = replace(TINY, earned_wage_share=1.0)
        for arm, base in (("S0", _World), ("M0", _World), ("M1", PooledWorld), ("M2", PooledWorld)):
            run = base(Inputs(), 0.6, economy, arm).run()
            series = run["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            self.assertGreater(float(run["ewa"]["uses"].sum()), 0.0, arm)
            np.testing.assert_allclose(run["ewa"]["fees"], EWA_FEE * run["ewa"]["value"], rtol=1e-12, atol=1e-18)
        run = simulate(Inputs(), 0.6, replace(TINY, earned_wage_share=0.0), "S0")
        self.assertEqual(float(run["series"]["ewa_value"].sum() + run["series"]["ewa_owed"].sum()), 0.0)

    def test_payers_in_chronic_deficit_are_flagged_at_launch(self):
        """Payers in chronic deficit are flagged at launch.

        Examples: three people at launch, each with a month's spending of 1.0: one spent 6.0 over the
        burn-in against 5.0 received, with a cushion of 0.5 (0.3 in E and 0.2 in savings), and is flagged; with a
        cushion of 1.2 it is not; one that spent 5.0 against 6.0 received, with a cushion of 0.1, is not. In a run the
        flags are set from the burn-in, the same in S0 and M1 (the test device, whose pool forms)."""
        w = controlled_world()
        w.spending[:3] = 1.0
        w.burn_spent[:3] = (6.0, 6.0, 5.0)
        w.receipts_path[:] = 0.0
        w.receipts_path[0, :3], w.receipts_path[9, :3] = (2.0, 2.0, 3.0), (3.0, 3.0, 3.0)
        w.cash[:3], w.savings[:3] = (0.3, 0.7, 0.1), (0.2, 0.5, 0.0)
        w._chronic()
        self.assertEqual(w.chronic[:3].tolist(), [True, False, False])
        economy = replace(TINY, n=100, months=12)
        runs = kept_run(_World, "S0", economy), kept_run(PooledWorld, "M1", economy)
        np.testing.assert_array_equal(runs[0]["chronic"], runs[1]["chronic"])
        self.assertTrue(runs[0]["chronic"].any() and not runs[0]["chronic"].all())

    def test_the_chronic_deficit_flag_changes_no_outcome(self):
        """The flag is a record only: a run with it silenced gives every other record exactly, in S0 and M1
        (the test device, whose pool forms)."""
        silence = lambda base: type("Silenced", (base,), dict(_chronic=lambda self: None))
        economy = replace(TINY, n=100, months=12)
        for arm, base in (("S0", _World), ("M1", PooledWorld)):
            run, silenced = kept_run(base, arm, economy), silence(base)(Inputs(), 0.6, economy, arm).run()
            self.assertTrue(run["chronic"].any(), arm)                         # the record is live
            self.assertFalse(silenced["chronic"].any(), arm)
            self.assert_same_outcome(run, silenced, ("chronic",))

    def test_the_runner_reports_earned_wage_access_and_chronic_payers_apart(self):
        """The runner reports earned-wage access and chronic payers apart.

        Example ($): four people over a year after launch: two hold access, one used it on 30 days with
        $1,200 advanced and $29.40 of fees, so per user a year 30 advances, $29.40 and $1,200. People 0 and 1 are
        flagged as in chronic deficit: they paid $54 and $0 of failure fees, 2 and 0 unpaid shares and $60 and $20 to
        intermediaries, and the others nothing."""
        from scripts.run_economy_population import by_chronic, ewa_report
        w = Economy(n=4, burn_in=1, months=12)
        path = lambda values: np.vstack([np.zeros(4), np.tile(np.asarray(values, float) / 12, (12, 1))])
        usd = lambda dollars: np.asarray(dollars, float) / MONTH_USD
        two = np.array([True, True, False, False])
        run = dict(population=dict(ewa=two), chronic=two,
                   ewa=dict(uses=path([30, 0, 0, 0]), fees=path(usd([29.4, 0, 0, 0])),
                            value=path(usd([1200, 0, 0, 0]))),
                   fees=path(usd([54, 0, 0, 0])), failure_counts=dict(fail_shares=path([2, 0, 0, 0])),
                   transfers=path(usd([60, 20, 0, 0])))
        self.assertEqual(ewa_report(run, w), dict(holders=0.5, users=0.25, advances_a_user_year=30.0,
                                                   fees_usd_a_user_year=29.4, value_usd_a_user_year=1200.0))
        self.assertEqual(by_chronic(run, w), dict(
            share=0.5, not_flagged=dict(fees_usd_a_year=0.0, failed_shares_a_year=0.0, transfers_usd_a_year=0.0),
            flagged=dict(fees_usd_a_year=27.0, failed_shares_a_year=1.0, transfers_usd_a_year=40.0)))
        nobody = dict(run, ewa=dict(uses=path([0] * 4), fees=path([0] * 4), value=path([0] * 4)),
                      chronic=np.zeros(4, bool))
        self.assertIsNone(ewa_report(nobody, w)["advances_a_user_year"])
        self.assertIsNone(by_chronic(nobody, w)["flagged"]["fees_usd_a_year"])

    # ---- The card base, outside prices and normal job loss --------------------------------------------------------
    def test_every_non_housing_bundle_is_card_eligible(self):
        """Every non-housing bundle is card-eligible.

        At 1,000 people over one month, card-eligible bundles are 28% of spending (0.417 x 0.671), against 18.2%
        in the first run (0.417 x 0.436). The same uniform draw decides, so every bundle eligible in the first run
        stays eligible, and the bundles are otherwise the same."""
        def services(card_base_all):
            world = _World(Inputs(), 0.6, Economy(n=1000, card_base_all=card_base_all), "S0")
            world.acc = dict(shocks=0.0, volume=0.0)
            world._obligations(0)
            service = world.ob["kind"] == SERVICE
            share = float(world.ob["amount"][service & world.ob["card"]].sum() / world.spending.sum())
            return world.card_share, {key: value[service] for key, value in world.ob.items()}, share
        card_share, decided, share = services(True)
        card_share_built, built, share_built = services(False)
        self.assertAlmostEqual(card_share, 1 - Inputs().housing, places=15)
        self.assertAlmostEqual(card_share_built, (1 - Inputs().housing) * Inputs().card_share, places=15)
        self.assertAlmostEqual(share, 0.28, delta=0.01)
        self.assertAlmostEqual(share_built, 0.182, delta=0.01)
        self.assertTrue(np.all(decided["card"][built["card"]]))                 # eligible as built stays eligible
        self.assertGreater(int(decided["card"].sum()), int(built["card"].sum()))
        for key in ("buyer", "seller", "amount", "settle"):
            np.testing.assert_array_equal(decided[key], built[key])

    def test_each_outside_price_matches_its_hand_value_at_each_r_out(self):
        """Each outside price matches its hand value at each r_out.

        Examples, a year, from three-month bills at 4.05% in October 2026, on r_out's basis, credited monthly,
        4.13452% (every anchor is on the monthly-credited basis): at r_out 2, 4.4 and 6%
        deposits pay 0.209238, 0.401238 and 0.529238%, the lowest card tier 26.355, 28.755 and 30.355% (the other tiers
        26.065 and 20.855, 28.465 and 23.255, 30.065 and 24.855%) and business loans 5.265, 7.665 and 9.265%. Vehicle
        and personal loans move by their pass-throughs, 0.75 and 0.63 (Fed G.19 on the bill, February 2022 to February
        2024): the shifts are -2.13452, +0.26548 and +1.86548 points (-4.13452 at 0%), so a new vehicle at
        score 700 (6.15%) is 6.15 - 0.75 x 2.13452 = 4.54911%, 6.15 + 0.75 x 0.26548 = 6.34911% and 6.15 + 0.75 x
        1.86548 = 7.54911% (3.04911% at 0%), and a personal loan at score 700 (13.19%) is 13.19 - 0.63 x 2.13452 =
        11.84525%, 13.19 + 0.63 x 0.26548 = 13.35725% and 13.19 + 0.63 x 1.86548 = 14.36525% (10.58525% at 0%). M2's
        deposit-part edge (2% less the deposit rate) is $17.908, $15.988 and $14.708 per $1,000, and the pool's
        business-loan edge at no learned loss (the outside rate less rho_H, the owners' 0.25 point and o) is +1.015
        points at every r_out. In the first run prices are fixed: 0.38%, 28.49, 28.20 and 22.99%, 7.4%, $16.20 and
        edges of +3.15, +0.75 and -0.85 points. At a synthetic r_out of 0% deposits sit on the 0.06% floor, the lowest card tier at 24.355% and business
        loans at 3.265%."""
        from scripts.run_economy_population import cell_inputs
        self.assertAlmostEqual(BILL_MONTHLY, 0.0413452, places=7)
        shift = lambda r_out: r_out - BILL_MONTHLY
        hand = lambda r_out, deposit, edge, built, loans: (deposit, tuple(np.array(CARD_APR) + shift(r_out)),
                                                           0.074 + shift(r_out), edge, built, loans)
        hands = {0.02: hand(0.02, 0.0038 + 0.08 * shift(0.02), 17.90762, 3.15, (0.0454911, 0.1184525)),
                 0.044: hand(0.044, 0.0038 + 0.08 * shift(0.044), 15.98762, 0.75, (0.0634911, 0.1335725)),
                 0.06: hand(0.06, 0.0038 + 0.08 * shift(0.06), 14.70762, -0.85, (0.0754911, 0.1436525)),
                 0.0: hand(0.0, 0.0006, None, None, (0.0304911, 0.1058525))}
        self.assertAlmostEqual(hands[0.044][0], 0.00401238, places=8)
        self.assertAlmostEqual(hands[0.044][2], 0.0766548, places=7)
        self.assertAlmostEqual(hands[0.0][1][0], 0.2435548, places=7)
        product, score, used = np.array([0, 1, 2]), np.full(3, 700.0), np.array([False, True, False])
        fixed = term_outside_apr(product, score, used)
        self.assertEqual((fixed[0], fixed[1]), (0.0615, 0.1319))
        for r_out, (deposit, card, business, edge, edge_built, loans) in hands.items():
            world = _World(cell_inputs(r_out), 0.6, Economy(n=40), "S0")
            tier = dict(zip(CARD_APR, card))
            self.assertAlmostEqual(12 * world.deposit_rate, deposit, places=15)
            np.testing.assert_allclose(12 * world.card_apr, [tier[apr] for apr in world.pop["card_apr"]], rtol=0,
                                       atol=1e-15)
            np.testing.assert_allclose(term_outside_apr(product, score, used, world.term_shift),
                                       [fixed[0] + 0.75 * shift(r_out), fixed[1] + 0.63 * shift(r_out), business],
                                       rtol=0, atol=1e-15)
            np.testing.assert_allclose(term_outside_apr(product, score, used, world.term_shift)[:2], loans, rtol=0,
                                       atol=1e-7)
            built = _World(cell_inputs(r_out), 0.6, legacy(Economy(n=40)), "S0")
            self.assertEqual((built.deposit_rate, built.term_shift), (FDIC_SAVINGS_RATE, None))
            np.testing.assert_array_equal(built.card_apr, built.pop["card_apr"] / 12)
            if edge is None:
                continue
            coupon = 12 * world.r_term                           # rho_H, the owners' spread and o, no learned loss
            self.assertAlmostEqual((0.02 - 12 * world.deposit_rate) * 1000, edge, places=5)
            self.assertAlmostEqual(100 * (business - coupon), 1.01548, places=5)
            self.assertAlmostEqual((0.02 - 12 * built.deposit_rate) * 1000, 16.20, places=9)
            self.assertAlmostEqual(100 * (BUSINESS_APR - coupon), edge_built, places=9)
        self.assertEqual(tuple(CARD_APR), (0.2849, 0.2820, 0.2299))
        self.assertEqual(BUSINESS_APR, 0.074)

    def test_existing_loans_keep_their_sealed_rates(self):
        """Existing loans keep their sealed rates.

        Example (the anchor on the monthly-credited basis): business requests made at r_out 2% carry
        5.265%; when outside prices move to r_out 6%'s, the month's new business requests carry 9.265% and the earlier
        requests keep 5.265%, and an outside business loan booked at 5.35% keeps that rate and accrues at it, a month's
        interest 5.35% / 12 of its principal: a rate is read when a request is made and sealed with it."""
        low, high = 0.074 + 0.02 - BILL_MONTHLY, 0.074 + 0.06 - BILL_MONTHLY
        from scripts.run_economy_population import cell_inputs
        moved = outside_prices(cell_inputs(0.06).rho_H, Economy())[2]
        world = _World(cell_inputs(0.02), 0.6, Economy(n=1000), "S0")
        world.acc = dict(shocks=0.0, volume=0.0)
        world._obligations(0)
        rates = lambda: world.req["rate"][world.req["product"] == 2] * 12
        before = rates()
        self.assertTrue(before.size > 0)
        np.testing.assert_allclose(before, low, rtol=0, atol=1e-15)
        world.term_shift = moved
        world._obligations(1)
        after = rates()
        self.assertEqual(int(np.isclose(after, low, rtol=0, atol=1e-15).sum()), before.size)
        self.assertGreater(int(np.isclose(after, high, rtol=0, atol=1e-15).sum()), 0)
        self.assertEqual(int(np.isclose(after, low, rtol=0, atol=1e-15).sum()
                             + np.isclose(after, high, rtol=0, atol=1e-15).sum()), after.size)
        w = controlled_world("S0")
        w._add_loans(np.array([0]), False, TERM, np.array([1.0]), np.array([0.0535 / 12]), np.array([0.0535 / 12]),
                     BIG, np.array([11]), 1)
        w.term_shift = moved
        w._obligations(1)
        list(map(lambda day: w._accrue(), range(DAYS)))
        self.assertEqual(float(w.book["rate"][0]), 0.0535 / 12)
        self.assertAlmostEqual(float(w.book["interest"][0]), 0.0535 / 12, places=15)

    def test_the_deposit_floor_binds_on_a_synthetic_rate_below_it(self):
        """The deposit floor binds on a synthetic rate below it.

        Example (the anchor on the monthly-credited basis, 4.13452%): at a synthetic r_out of 0% the
        deposit rate would be 0.38% - 0.08 x 4.13452% = 0.0492% a year, below the 0.06% floor, so it is 0.06%; with the
        0.46 pass-through (a sensitivity) at r_out 2% it would be negative, and is 0.06% too; at r_out 6% that
        pass-through gives 0.38% + 0.46 x 1.86548% = 1.2381%, above it."""
        decided, sensitivity = Economy(), replace(Economy(), deposit_pass_through=0.46)
        self.assertAlmostEqual(0.0038 + 0.08 * (0.0 - BILL_MONTHLY), 0.000492, places=6)
        self.assertEqual(outside_prices(0.0, decided)[0], DEPOSIT_FLOOR)
        self.assertAlmostEqual(12 * DEPOSIT_FLOOR, 0.0006, places=15)
        self.assertEqual(outside_prices(0.02 / 12, sensitivity)[0], DEPOSIT_FLOOR)
        self.assertAlmostEqual(12 * outside_prices(0.06 / 12, sensitivity)[0], 0.0038 + 0.46 * (0.06 - BILL_MONTHLY),
                               places=15)
        self.assertAlmostEqual(12 * outside_prices(0.06 / 12, sensitivity)[0], 0.012381, places=6)
        self.assertEqual(_World(replace(Inputs(), rho_H=0.0), 0.6, Economy(n=40), "S0").deposit_rate, DEPOSIT_FLOOR)

    def test_normal_job_loss_at_055_percent_a_month_gives_a_19_percent_stock(self):
        """Normal job loss holds a steady stock of jobs without a wage, h D / (1 + h D).

        Example: at 0.55% a month with completed spells (a mean of 109.4 days, 3.65 months) the stock is 1.967% of
        jobs. 20,000 synthetic jobs of weight one, started at that stock (``spell_stock``) and laid off month by month
        as the engine lays them off (``draw_spells``: a job in a spell is not laid off again), hold a mean month-end
        stock over 48 months within 1.85% to 2.10%. A world draws its month-0 stock the same way, on a stream of its
        own, from each job's own hazard, with every spell in it under way on day 0; without normal job loss no job
        starts in a spell."""
        median, sigma = spell_law(Economy())
        self.assertEqual((median, sigma), (COMPLETED_SPELL_MEDIAN_DAYS, COMPLETED_SPELL_SIGMA))
        self.assertEqual(spell_law(legacy()), (SPELL_MEDIAN_DAYS, SPELL_SIGMA))
        months = median * np.exp(sigma ** 2 / 2) / DAYS
        self.assertAlmostEqual(JOB_LOSS * months / (1 + JOB_LOSS * months), 0.01967, places=4)
        hazard = np.full(20000, JOB_LOSS)
        start, end = spell_stock(np.random.default_rng(np.random.SeedSequence([20261021, 23])), hazard, median, sigma)
        stocks = []
        for month in range(48):
            rng = np.random.default_rng(np.random.SeedSequence([20261021, 19, month]))
            laid_off, begins, ends = draw_spells(rng, hazard, end <= month * DAYS, month * DAYS, median, sigma)
            start, end = np.where(laid_off, begins, start), np.where(laid_off, ends, end)
            last = (month + 1) * DAYS - 1
            stocks.append(float(((start <= last) & (last < end)).mean()))
        self.assertTrue(0.0185 <= np.mean(stocks) <= 0.0210, np.mean(stocks))
        world = _World(Inputs(), 0.6, Economy(n=1000), "S0")
        drawn = spell_stock(np.random.default_rng(np.random.SeedSequence([world.economy.seed, 23])),
                            JOB_LOSS * world.layoff_rate, median, sigma)
        np.testing.assert_array_equal(world.spell_start, drawn[0])
        np.testing.assert_array_equal(world.spell_end, drawn[1])
        under_way = (world.spell_start <= 0) & (0 < world.spell_end)
        np.testing.assert_array_equal(under_way, world.spell_end > 0)
        self.assertTrue(0.01 < float(under_way.mean()) < 0.03)
        self.assertFalse(_World(Inputs(), 0.6, Economy(n=1000, job_loss=0.0), "S0").spell_end.any())

    def test_holders_card_bridging_is_recorded_for_the_s0_check(self):
        """Holders' bridging on the card is recorded, and the runner reports it a person and a holder a year.

        Examples ($): a card holder with no money bridges a $100 bill on the card as a cash advance, and the record
        holds the $100; a payer without a card bridges nothing on a card. In a run the record is live. The runner reads
        $12 a month per capita over a year, ten people of whom two hold a card, as $144 a person and $720 a holder a
        year, and None with no holder. The report carries the card's fees and charge-offs beside it: $1 a month per
        capita of cash-advance fees, $0.50 of late fees and $2 charged off are $60, $30 and $120 a holder a year, and
        one line closed is half the two holders."""
        from scripts.run_economy_population import card_bridging
        for holder, bridged in ((True, 100.0), (False, 0.0)):
            w = controlled_world("S0")
            w.holder[0], w.acc["card_bridging"] = holder, 0.0     # the quiet month's holders bridged in it
            one_invoice(w, 100 / MONTH_USD, at=30, card=False)
            w._settle(1, 30)
            self.assertAlmostEqual(w.acc["card_bridging"] * MONTH_USD, bridged, places=9)
        run = kept_run(_World, "S0", replace(TINY, n=100, months=12))
        self.assertGreater(float(run["series"]["card_bridging"].sum()), 0.0)
        economy = Economy(n=10, burn_in=1, months=12)
        two = np.isin(np.arange(10), (3, 7))
        monthly = lambda dollars: np.r_[0.0, np.full(12, dollars / MONTH_USD)]
        synthetic = dict(series=dict(card_bridging=monthly(12.0), advance_fees=monthly(1.0), late_fees=monthly(0.5),
                                     charged_off=monthly(2.0), lines_closed=np.r_[0.0, 1.0, np.zeros(11)]),
                         population=dict(holder=two))
        self.assertEqual(card_bridging(synthetic, economy),
                         dict(usd_a_year=144.0, usd_a_holder_year=720.0, advance_fees_usd_a_holder_year=60.0,
                              late_fees_usd_a_holder_year=30.0, charged_off_usd_a_holder_year=120.0,
                              lines_closed_share=0.5))
        nobody = dict(synthetic, population=dict(holder=np.zeros(10, bool)))
        self.assertIsNone(card_bridging(nobody, economy)["usd_a_holder_year"])

    def test_the_s0_check_runs_s0_alone(self):
        """The S0 check (``--arms S0``) runs S0 alone; by default every arm runs.

        Example: r_out 2, 4.4 and 6% and distress 0, 1 and 2% on the development seeds are 27 jobs of one run each. A
        job with S0 alone runs no other arm, and its S0 reports are exactly the full job's (common random numbers). Its
        cell reads S0 alone, with no highest mean gain and S0's own paired distress reading. The four stores are
        written, opening with the arms run, and the region figures are skipped with printed notes."""
        from scripts.run_economy_population import (SEEDS, decide_cells, job, options, run_record, runs_in, selected,
                                                    tasks_for, write_stores)
        from scripts.run_region_figures import draw
        check = options().parse_args(["--seeds", "development", "--arms", "S0", "--a0", "0.6", "--distress", "0",
                                      "0.01", "0.02"])
        self.assertEqual((check.arms, options().parse_args(["--seeds", "development"]).arms), ("S0", "all"))
        tasks = tasks_for(SEEDS["development"], 1000, selected(check.r_out, check.a0, check.distress))
        self.assertEqual((len(tasks), sum(runs_in(task, s0_only=True) for task in tasks)), (27, 27))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            jobs = [job((0.044, 0.6, level, 20261021, 40, False), MAP_ECONOMY, s0_only=True) for level in (0.0, 0.02)]
            selection = selected((0.044,), (0.6,), (0.0, 0.02))
            cells, recirculated = decide_cells(jobs, selection, MAP_ECONOMY, 40)
        for alone, full in zip(jobs, map_jobs()):
            self.assertEqual(alone["arms"], {})
            for part in ("measures", "monthly", "failure_counts"):
                self.assertEqual(set(alone[part]), {"S0"}, part)
                self.assertEqual(json.dumps(alone[part]["S0"]), json.dumps(full[part]["S0"]), part)
            self.assertEqual(json.dumps(alone["S0"]), json.dumps(full["S0"]))
        self.assertIsNone(cells[0]["highest_mean_gain"])
        self.assertFalse({"M0", "U", "M1", "M2"} & set(cells[0]))
        self.assertEqual(set(cells[1]["distress_reading"]), {"seeds_paired", "S0"})
        self.assertIn("usd_a_holder_year", jobs[0]["S0"]["card_bridging"])
        meta =run_record(MAP_ECONOMY, "development", 2, selection, s0_only=True)
        self.assertEqual(meta["arms"], ["S0"])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            write_stores(output, meta, jobs, cells, recirculated)
            self.assertEqual(len(list(output.iterdir())), 4)
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(draw(output), [])
            self.assertIn("region_3d skipped", printed.getvalue())
            self.assertEqual(len(list(output.iterdir())), 4)

    def test_run_record_stores_the_outside_prices_and_the_distress_labels(self):
        """The run record stores the outside prices each r_out runs at, a year: deposits, card tiers, business loans
        and the vehicle and personal grids, which move by 0.75 and 0.63 of the shift (at r_out 6% by 0.75 x 1.86548 =
        1.39911 and 0.63 x 1.86548 = 1.17525 points). It also stores the products kept fixed (none, every pass-through
        being sourced) and each distress level's labels: its extra and total monthly rates with normal job loss (0.55%
        to 2.55%) and its label of jobs without a wage at month 36 (``STOCK_LABELS``). Under ``legacy`` no price
        follows r_out: every product is fixed, deposits at 0.38% and cards at ``CARD_APR``."""
        from scripts.run_economy_population import RATES, STOCK_LABELS, run_record
        meta = run_record(Economy(n=40), "development", 0)
        rates = meta["outside_rates"]
        self.assertEqual([row["r_out"] for row in rates], list(RATES))
        self.assertAlmostEqual(rates[0]["deposit"], 0.0038 + 0.08 * (0.02 - BILL_MONTHLY), places=12)
        np.testing.assert_allclose(rates[2]["card"], np.array(CARD_APR) + 0.06 - BILL_MONTHLY, rtol=0, atol=1e-12)
        self.assertAlmostEqual(rates[1]["business"], 0.074 + 0.044 - BILL_MONTHLY, places=12)
        self.assertEqual(meta["fixed_cost"], "central")
        np.testing.assert_allclose(rates[2]["vehicle"], VEHICLE_APR + 0.0139911, rtol=0, atol=1e-7)
        np.testing.assert_allclose(rates[2]["personal"], PERSONAL_APR + 0.0117525, rtol=0, atol=1e-7)
        self.assertEqual(meta["fixed_products"], [])
        labels = meta["distress_labels"]
        self.assertEqual(labels["extra_pct_a_month"], [0.0, 0.5, 1.0, 1.5, 2.0])
        self.assertEqual(labels["total_pct_a_month"], [0.55, 1.05, 1.55, 2.05, 2.55])
        self.assertEqual(labels["jobs_without_wage_month_36_pct"], list(STOCK_LABELS))
        fixed = run_record(legacy(Economy(n=40)), "development", 0)
        self.assertEqual(fixed["fixed_products"], ["deposit", "card", "business", "vehicle", "personal"])
        self.assertEqual([row["deposit"] for row in fixed["outside_rates"]], [0.0038] * 3)
        self.assertEqual(fixed["outside_rates"][2]["card"], CARD_APR.tolist())
        self.assertEqual(fixed["distress_labels"]["total_pct_a_month"], [0.0, 0.5, 1.0, 1.5, 2.0])
        json.dumps(meta)

    # ---- The yardsticks' shared helpers and the fee plumbing ----------------------------------------------------
    def test_the_capital_limit_switches_on_the_real_rate_and_the_return_reads_the_hand_cases(self):
        """The capital limit N* (``paper_capital``) is the lending need P* plus the margin over the alternative,
        switched on the real reserve rate, and the return on capital (``paper_return``) falls to the alternative at N*.

        Examples (monthly units except the first two): lending of $1,000, a margin of $5 and rho 5% give N* $1,100 and
        R(N*) 5%; a margin of $2 (10 - 3 - 5) gives N* $1,040 and R(N*) 5%. P* 0.6 and m 0.001 at r_out 4.4%: N*
        0.872727 without the spread and 0.858065 with its 0.25 point, where R is 6.65% a year at P*, 4.65% at N* and
        4.2273% at 1.1 N*, falling strictly above P*. Where the real reserve rate is zero (M2 at r_out 2%), N* is P*,
        0.6, although the spread keeps the alternative above zero: switched on the alternative it would be 5.40, nine
        times P*. The real rate is the reserve rate net of the arm's index, nominal in M1, so M1 at r_out 2% keeps its
        standby: N* 1.133333 at m 0.001. A margin at or below zero leaves N* at P* (the free-entry limit: the quote is
        then below the alternative at any capital above P*), where the formula alone would give 0.548387 at m -0.0002
        and -0.174194 at m -0.003. With the pool's own cash earning p_net = rho - c_I (0.24%), N* = P* + F /
        (alternative - p_net) = 0.6 + 0.001 / ((0.25 + 0.24) / 1200) = 3.048980, where the quote is the alternative and
        above which it falls towards p_net, its limit at unbounded capital; with no return on idle cash it is the N*
        above. Where idle cash earns the alternative itself (no spread and no custody) N* is unbounded and the quote
        never falls below the alternative. No capital has no return."""
        self.assertAlmostEqual(paper_capital(1000.0, 5.0, 0.05, 0.05), 1100.0, places=9)
        self.assertAlmostEqual(paper_return(1000.0, 5.0, 1100.0, 0.05), 0.05, places=15)
        self.assertAlmostEqual(paper_capital(1000.0, 10.0 - 3.0 - 5.0, 0.05, 0.05), 1040.0, places=9)
        self.assertAlmostEqual(paper_return(1000.0, 2.0, 1040.0, 0.05), 0.05, places=15)
        rate, spread = 0.044 / 12, 0.0025 / 12
        self.assertAlmostEqual(paper_capital(0.6, 0.001, rate, rate), 0.872727, places=6)
        alt = rate + spread
        star = paper_capital(0.6, 0.001, alt, rate)
        self.assertAlmostEqual(star, 0.858065, places=6)
        yearly = [12 * paper_return(0.6, 0.001, capital, alt) for capital in (0.6, star, 1.1 * star)]
        np.testing.assert_allclose(yearly, [0.0665, 0.0465, 0.042273], rtol=0, atol=5e-7)
        falling = np.diff([paper_return(0.6, 0.001, capital, alt) for capital in np.linspace(0.6, 3.0, 25)])
        self.assertTrue(np.all(falling < 0))
        self.assertEqual(paper_capital(0.6, -0.0002, alt, rate), 0.6)
        self.assertAlmostEqual(0.6 - 0.0002 / alt, 0.548387, places=6)
        self.assertEqual(paper_capital(0.6, 0.001, spread, 0.0), 0.6)
        self.assertEqual(paper_capital(0.6, 0.001, spread, -0.01 / 12), 0.6)
        self.assertAlmostEqual(0.6 + 0.001 / spread, 5.40, places=9)
        self.assertAlmostEqual(paper_capital(0.6, 0.001, 0.02 / 12 + spread, 0.02 / 12), 1.133333, places=6)
        self.assertAlmostEqual(0.6 - 0.003 / alt, -0.174194, places=6)
        self.assertEqual(paper_capital(0.6, -0.003, alt, rate), 0.6)
        p_net = rate - 0.0024 / 12
        free = paper_capital(0.6, 0.001, alt, rate, p_net)
        self.assertAlmostEqual(free, 0.6 + 0.001 / (0.0049 / 12), places=12)
        self.assertAlmostEqual(free, 3.048980, places=6)
        self.assertAlmostEqual(paper_return(0.6, 0.001, free, alt, p_net), alt, places=15)
        above = [paper_return(0.6, 0.001, capital, alt, p_net) for capital in np.linspace(0.6, 10 * free, 50)]
        self.assertTrue(np.all(np.diff(above) < 0) and above[-1] > p_net)
        self.assertEqual(paper_return(0.6, 0.001, np.inf, alt, p_net), p_net)
        self.assertEqual(paper_capital(0.6, 0.001, rate, rate, rate), np.inf)
        self.assertEqual(paper_capital(0.6, -0.001, rate, rate, rate), 0.6)
        self.assertTrue(np.isnan(paper_return(0.6, 0.001, 0.0, alt)))

    def test_a_late_wage_paid_in_p_pays_gas_on_the_share_it_completes(self):
        """A late wage paid in P pays one transfer's gas on the share of what is owed that the payment completes.

        Example ($, routing "all"): payer 2 owes person 1 a $100 late wage in P and pays it from $50.000845 of P, $50
        and half a transfer's gas, half of what it owed: that payment counts half a payment among P payments, as
        ``_settle`` counts a payment, and pays half the gas, $0.000845. Paid off later from $50.00169 more, the rest
        counts one payment, the whole of what it still owed, and pays a whole transfer's gas. The pool's cash is
        untouched: no fee exists."""
        w = controlled_world()
        w.economy = replace(w.economy, routing="all")
        funded_pool(w)                                                        # everyone participates; the pool serves
        w.ob = dict(buyer=np.array([2]), seller=np.array([1]), amount=np.array([100.0 / MONTH_USD]),
                    settle=np.array([20]), card=np.zeros(1, bool), kind=np.array([LATE_WAGE]))
        w.receivable[1] = w.payable[2] = 100.0 / MONTH_USD
        counted, cash = [], w.pool_cash
        for held in (50.000845, 50.00169):
            w.pcash[2] = held / MONTH_USD
            count, gas = w.acc["p_n"], w.acc["gas_paid"]
            w._wage_arrears(np.maximum(w.cash + w.pcash, 0.0))
            counted.append((w.acc["p_n"] - count, (w.acc["gas_paid"] - gas) * MONTH_USD))
        self.assertEqual(w.ob["amount"].size, 0)                              # paid off
        np.testing.assert_allclose(counted, [(0.5, 0.000845), (1.0, 0.00169)], rtol=1e-9, atol=1e-15)
        self.assertEqual(w.pool_cash, cash)

    def test_owners_alternative_is_the_reserve_rate_floored_at_zero_and_the_spread(self):
        """The owners' alternative a month in P terms is the reserve rate floored at zero plus the 0.25 point spread:
        4.65% a year in M1 at r_out 4.4%, the spread alone in M2 at r_out 2% and at 1%; nominal, each saver's rho_H
        plus the spread. Under ``LEGACY_STEP45`` there is no spread."""
        spread = 0.0025 / 12
        for arm, rate, index, want in (("M1", 0.044, 0.0, 0.0465 / 12), ("M2", 0.02, 0.02, spread),
                                       ("M2", 0.01, 0.02, spread)):
            w = controlled_world(arm)
            w.rho_p = (rate - index) / 12
            self.assertAlmostEqual(w._owners_alternative(), want, places=15)
            np.testing.assert_allclose(w._owners_alternative_nominal(), w.pool_alternative + spread, rtol=0, atol=0)
        w.economy = replace(w.economy, **LEGACY_STEP45)
        self.assertEqual(w._owners_alternative(), 0.0)
        np.testing.assert_array_equal(w._owners_alternative_nominal(), w.pool_alternative)

    def test_the_issuer_books_carry_no_fee_or_rail_and_its_cost_of_p_every_month(self):
        """The issuer is a pure custodian and not a payment operator, since P payments run on stablecoin rails: its
        books have no fee line and no rail, and its expenses line is its 0.24% a year of the P outstanding alone.

        Checked in the test device's pooled runs of M1, M2 and M1 under routing "all" (where wages paid late and term
        purchases in P pay gas too): the four lines add up to the wallet; the stay test reads that wallet; wealth
        accounting, backing and the issuer's cash close every month. Payers' gas is one transfer a completed P payment,
        counted as the share completed, and no fee record exists. Under ``LEGACY_STEP45`` the expenses line is zero."""
        economy = replace(TINY, n=100, months=12)
        self.assertFalse({"fees", "expense_rail"} & set(ISSUER_BOOKS))
        for arm, w in (("M1", economy), ("M2", economy), ("M1", replace(economy, routing="all"))):
            series = kept_run(PooledWorld, arm, w)["series"]
            get = lambda key: series["issuer_" + key]
            for key in ("fees_to_pool", "fees_to_operator", "rail", "alpha_fees", "issuer_fees", "issuer_expense_rail",
                        "margin_fees", "margin_own_fees"):
                self.assertNotIn(key, series)
            self.assertGreater(float(series["p_payments"].sum()), 0.0, arm)
            np.testing.assert_allclose(series["gas"], GAS_PER_P_PAYMENT * series["p_payments"], rtol=1e-12, atol=1e-21)
            np.testing.assert_allclose(get("expense_holding"), -HOLDING_COST * series["P_out"], rtol=1e-12, atol=1e-18)
            np.testing.assert_array_equal(get("expense_holding"), get("expenses"))
            self.assertTrue(np.all(get("expenses")[series["P_out"] > 0] < 0), arm)
            lines = sum(map(get, ("custodian", "indexer", "float", "expenses")))
            np.testing.assert_allclose(get("wallet"), lines, atol=1e-15)
            launch = economy.burn_in
            stay = series["issuer_stay"]
            np.testing.assert_allclose(stay[launch + 11:], [get("wallet")[month - 11:month + 1].mean()
                                                            for month in range(launch + 11, launch + economy.months)],
                                       rtol=0, atol=1e-15)
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            backing = series["backing"][launch:]
            np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9)
            np.testing.assert_allclose(get("payout") - get("owners_in"), get("wallet"), atol=1e-15)
        series = pooled(Inputs(), 0.6, replace(economy, **LEGACY_STEP45), "M1")["series"]
        for key in ("issuer_expenses", "issuer_expense_holding"):
            self.assertFalse(series[key].any(), key)

    def test_the_issuers_wallet_per_dollar_of_p_reads_the_hand_case(self):
        """The issuer's wallet per $1 of P is the reserve return less indexation and its 0.24% cost of holding P.

        Example ($1 of P for a year, one model month standing for the year, no pool flows): the wallet is r_out less
        0.24% in M1, +1.76%, +4.16% and +5.76% at r_out 2, 4.4 and 6%, and r_out less 2% inflation and 0.24% in M2,
        -0.24%, +2.16% and +3.76%. So M2 at r_out 2%, where reserve income and indexation cancel, records 'issuer would
        leave' (its declared limit) wherever the wallet carries no pool flows; with a pool what it pays out of the
        reserve return enters. With no issuer cost the wallet there reads zero, which counts as staying."""
        def wallet(arm, rate, cost=0.0024):
            w = controlled_world(arm)
            index = 0.02 if arm == "M2" else 0.0
            w.economy = replace(w.economy, issuer_cost=cost)
            w.inputs, w.index, w.rho_p = replace(w.inputs, rho_H=rate), index, rate - index
            w.acc.update(p_all=1.0, float_pool=0.0, wallet_yield=0.0)
            got = w._issuer_books()["wallet"]
            list(map(w._stay_test, [got] * STAY_MONTHS))
            return got, w.issuer_leaves
        rates = (0.02, 0.044, 0.06)
        np.testing.assert_allclose([wallet("M1", rate)[0] for rate in rates], [0.0176, 0.0416, 0.0576], rtol=0,
                                   atol=1e-15)
        np.testing.assert_allclose([wallet("M2", rate)[0] for rate in rates], [-0.0024, 0.0216, 0.0376], rtol=0,
                                   atol=1e-15)
        self.assertTrue(wallet("M2", 0.02)[1])
        self.assertFalse(wallet("M2", 0.044)[1])
        self.assertFalse(wallet("M1", 0.02)[1])
        self.assertEqual(wallet("M2", 0.02, cost=0.0), (0.0, False))

    def test_the_most_cost_the_issuer_could_bear_adds_its_costs(self):
        """The stay reading's most annual expense is read on a wallet that already carries the issuer's own costs, so
        it is what the issuer could bear beyond them; the report adds those costs over the same 12 months and their
        sum, per person and over P.

        Example ($ a person): the lowest 12-month reading, -$0.0005 a month of model money, is -$38.64 a year; expenses
        of $0.30 a month are $3.60 a year over the same months; the most it could bear in all is -$35.04 a year, over
        the $1,288 of P. With no costs the two readings agree, and a run that does not store the expenses line has
        neither."""
        from scripts.run_economy_figures import DOLLARS, issuer_stay, persistence
        months = 60
        read = np.arange(months) >= STAY_MONTHS - 1
        stay = np.where(read, 0.001, np.nan)
        stay[30] = -0.0005
        series = dict(issuer_stay=stay, issuer_would_leave=np.where(read, (np.arange(months) >= 30) * 1.0, np.nan),
                      P_out=np.full(months, 0.2), issuer_expenses=np.full(months, -0.30 / DOLLARS))
        run = dict(series=series, economy=Economy(n=2, burn_in=0, months=months), arm="M1", rho_p=0.044 / 12)
        got = issuer_stay(run)
        self.assertAlmostEqual(got["expense"], -38.64, places=9)
        self.assertAlmostEqual(got["costs"], 3.60, places=9)
        self.assertAlmostEqual(got["most_cost"], -35.04, places=9)
        self.assertAlmostEqual(got["cost_share"], 3.60 / (0.2 * DOLLARS), places=12)
        self.assertAlmostEqual(got["most_cost_share"], -35.04 / (0.2 * DOLLARS), places=12)
        series.update({key: np.ones(months) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                        "cash_to_lend", "interest_collected", "own_margin",
                                                        "owners_capital")})
        series.update(K=np.full(months, 0.1), pool_costs=np.zeros(months), write_off_rate=np.zeros(months),
                      arrears_share=np.zeros(months))
        detail = persistence(run, 0.6)["detail"]
        self.assertAlmostEqual(detail["issuer_most_cost_usd_a_year"], -35.04, places=9)
        self.assertAlmostEqual(detail["issuer_costs_usd_a_year"], 3.60, places=9)
        series["issuer_expenses"] = np.zeros(months)
        got = issuer_stay(run)
        self.assertEqual((got["costs"], got["most_cost"]), (0.0, got["expense"]))
        del series["issuer_expenses"]
        self.assertEqual((issuer_stay(run)["costs"], issuer_stay(run)["most_cost"]), (None, None))

    # ---- The yardsticks' records and readings ------------------------------------------------------------------
    def test_the_pools_own_margin_reads_the_hand_cases(self):
        """The pool's own margin is coupons and recoveries less operating and fixed costs, write-offs and owners'
        alternative on what is lent (docs/DECISIONS.md, "The pool pays its own way"); it is zero at break-even.

        Example (one model month standing for the year, the alternative 5% and no spread): lending of $1,000 at the 5%
        alternative plus o 2% plus the fixed cost's part (the coupon carries the fixed cost at break-even, $5 over
        $1,000 of principal-time, 0.5%) accrues $75 of coupons and costs $20 to operate and $5 fixed, so the margin is
        zero, 75 - 20 - 5 - 50, realised losses being the learned loss (none here), and N* is the lending need.
        Coupons without the fixed part, $70, leave the fixed cost unpaid, a margin of -$5. No provider fee exists, so
        fees are not a part. The owners' spread (0.25 point a year) raises the alternative on the $1,000 lent. Outside
        the pool arms there is no margin, and S0 and M0 record none."""
        def world(spread=0.0, arm="M1", coupons=75.0):
            w = controlled_world(arm)
            w.economy = replace(w.economy, owner_spread=spread)
            w.rho_p = 0.05
            w.shares[2], w.nav_ps = 1000.0, 1.0
            w.owners_held, w.capital = w.shares * w.nav_ps, 1000.0
            w.acc.update(coupons=coupons, op_cost=20.0, pool_pt=1000.0, written_off=0.0, recovered=0.0)
            return w
        parts, margin = world()._own_margin(5.0)
        self.assertEqual(list(parts), list(MARGIN_PARTS))
        self.assertEqual(list(MARGIN_PARTS), ["coupons", "recovered", "operating", "fixed", "written_off",
                                              "alternative"])
        np.testing.assert_allclose(list(parts.values()), [75.0, 0.0, -20.0, -5.0, 0.0, -50.0], rtol=0, atol=1e-12)
        self.assertAlmostEqual(margin, 0.0, places=12)
        self.assertAlmostEqual(paper_capital(1000.0, margin, 0.05, 0.05), 1000.0, places=9)
        self.assertAlmostEqual(world(coupons=70.0)._own_margin(5.0)[1], -5.0, places=12)
        # The owners' spread on lent principal-time.
        spread = 0.0025 / 12
        w = world(spread)
        self.assertAlmostEqual(w._own_margin(5.0)[0]["alternative"], -(0.05 + spread) * 1000.0, places=12)
        # No margin outside the pool arms.
        parts, margin = world(arm="M0")._own_margin(5.0)
        self.assertTrue(np.isnan(margin) and all(np.isnan(value) for value in parts.values()))
        economy = replace(TINY, n=100, months=12)
        for arm in ("S0", "M0"):
            series = kept_run(_World, arm, economy)["series"]
            for key in ("own_margin", "joint", *("margin_" + part for part in MARGIN_PARTS)):
                self.assertTrue(np.isnan(series[key]).all(), (arm, key))

    def test_recoveries_are_credited_in_the_margin_and_the_old_ratio(self):
        """A written-off pool loan that is repaid later is credited: in the pool's own margin it nets to its interest,
        and its principal is credited in the numerator of the old ratio (collected income over owners' compensation K
        and the pool's costs).

        Example: a $100 pool bridge accrues $1 of coupons, is written off at $101, and is then repaid in full with
        $0.50 more of legal interest, $101.50. In the margin the write-off is -$101 and the recovery +$101.50, so with
        the $1 accrued the loan nets to its whole interest, $1.50. Under ``self_financing`` "margin" the $100 of
        principal recovered is credited in the ratio's numerator; under "coverage" it is not, and the repaid bridge
        still costs the ratio its $100."""
        def repaid(rules=None):
            w = controlled_world()
            w.economy = replace(w.economy, **(rules or {}))
            w.acc.update(coupons=0.0, op_cost=0.0, pool_pt=0.0, written_off=0.0, recovered=0.0, interest_collected=0.0,
                         recovered_principal=0.0, reserve_to_pool=0.0)
            w._add_loans(np.array([0]), True, BRIDGE, np.array([100.0]), DAYS / 100.0, 0.02, 10, None, 0)
            w._accrue()                                                # $1 of coupons in a day
            w._write_off(100)
            w.book["interest"][0] = 1.5                                # $0.50 more of legal interest
            w.part[0], w.pcash[0] = True, 101.5
            w._pay(np.array([0]), np.array([101.5]), np.full(10, 101.5))
            return w
        w = repaid()
        self.assertAlmostEqual(w.acc["written_off"], 101.0, places=12)
        self.assertAlmostEqual(w.acc["recovered"], 101.5, places=12)
        self.assertAlmostEqual(w.acc["recovered_principal"], 100.0, places=12)
        self.assertAlmostEqual(w.acc["interest_collected"], 1.5, places=12)
        parts, _ = w._own_margin(0.0)
        self.assertAlmostEqual(parts["coupons"] + parts["recovered"] + parts["written_off"], 1.5, places=12)
        records = {}
        for name, rules in (("margin", None), ("coverage", dict(self_financing="coverage"))):
            w = repaid(rules)
            w._close(0, w.net_wealth(), np.ones(10), np.ones(10))
            records[name] = {key: w.series[key][-1] * 10 for key in ("interest_collected", "recovered_principal",
                                                                      "margin_recovered", "margin_written_off")}
        self.assertAlmostEqual(records["margin"]["interest_collected"], 101.5, places=10)
        self.assertAlmostEqual(records["coverage"]["interest_collected"], 1.5, places=10)
        self.assertAlmostEqual(records["margin"]["recovered_principal"], 100.0, places=10)
        self.assertAlmostEqual(records["margin"]["margin_recovered"], 101.5, places=10)
        self.assertAlmostEqual(records["margin"]["margin_written_off"], -101.0, places=10)

    def test_the_held_capital_ratio_is_one_at_the_capital_limit(self):
        """The old ratio, collected income over owners' compensation K and the pool's costs, is about 1 at the capital
        limit by construction once K is at owners' alternative.

        Example: at the capital limit of $1,000, the lending need, collected income of $75 of coupons (the coupon
        carries the fixed cost at break-even and no fee exists) against K at the 5% alternative on $1,000 ($50) and the
        pool's $25 of costs (operating $20 and fixed $5) is a ratio of 1.000. Under ``self_financing`` "coverage", with
        K at 0.9 of r_out ($45), it is 75 / 70, 1.071."""
        def ratio(coupons, capital, rules=None):
            w = controlled_world(cost=0.5)                                  # a fixed cost of $5 over ten people
            w.economy = replace(w.economy, owner_spread=0.0, **(rules or {}))
            w.inputs, w.rho_p = replace(w.inputs, rho_H=0.05), 0.05
            w.capital, w.Q, w.service = capital, 1200.0, True
            w.acc.update(coupons=coupons, interest_collected=coupons, op_cost=20.0, written_off=0.0, recovered=0.0,
                         recovered_principal=0.0, reserve_to_pool=0.0, pool_pt=1000.0)
            w._close(0, w.net_wealth(), np.ones(10), np.ones(10))
            get = lambda key: w.series[key][-1] * 10
            self.assertAlmostEqual(get("pool_costs"), 25.0, places=12)
            return get("interest_collected") / (get("K") + get("pool_costs")), get("K")
        got, K = ratio(75.0, 1000.0)
        self.assertAlmostEqual(K, 50.0, places=10)
        self.assertAlmostEqual(got, 1.0, places=12)
        got, K = ratio(75.0, 1000.0, dict(self_financing="coverage"))
        self.assertAlmostEqual(K, 45.0, places=10)
        self.assertAlmostEqual(got, 75.0 / 70.0, places=12)
        self.assertAlmostEqual(got, 1.071, places=3)

    def test_the_joint_test_reads_the_hand_case_and_consolidates_the_books(self):
        """The joint issuer-and-pool test reads the two as one firm: the issuer's wallet plus the income credited to
        households' shares less their alternative on their capital. It equals its bottom-up form every month.

        Example (one model month standing for the year, the alternative 5%, no fee and no rail, the issuer a pure
        custodian): at the capital limit of $1,000, the lending need, households hold all of it, and P outstanding is
        $10,000 with no yield paid out. The issuer's wallet is 500 - 24 = $476, households earn their alternative, so
        the joint test is $476; bottom up, the margin of zero at break-even less the alternative on nothing not lent
        plus the custodian and expenses lines is $476 too. The owners' spread is charged on every share.

        In forced runs, M1 with CPI and M2, whose owners ask to exit, the joint test equals the bottom-up form every
        month, with demurrage's charge added and the coupon cut the margin counts taken off: the firm's float pays the
        cut, so it is income once, and households pay the charge to the firm. The firm also pays the yield on wallet P
        before demurrage (the books' float line), which the bottom-up form takes off. The cut the margin counts is at
        most the demurrage taken, not demurrage plus the pool cash's own return."""
        def books(spread=0.0):
            w = controlled_world()
            w.economy = replace(w.economy, owner_spread=spread, issuer_cost=0.0024)
            w.inputs, w.rho_p = replace(w.inputs, rho_H=0.05), 0.05
            w.acc.update(p_all=10000.0, float_pool=0.0, wallet_yield=0.0)
            w.shares[0], w.nav_ps = 1000.0, 1.0
            return w, w._issuer_books()
        w, got = books()
        self.assertAlmostEqual(got["wallet"], 476.0, places=10)
        joint = w._joint(got, 1000.0 * 0.05, 1000.0)
        self.assertAlmostEqual(joint, 476.0, places=10)
        bottom = 0.0 - 0.05 * (1000.0 - 1000.0) + sum(got[key] for key in ("custodian", "indexer", "expenses"))
        self.assertAlmostEqual(bottom, 476.0, places=10)
        spread = 0.0025 / 12
        w, got = books(spread)
        self.assertAlmostEqual(w._joint(got, 1000.0 * 0.05, 1000.0), 476.0 - spread * 1000.0, places=10)
        for arm in ("M1", "M2"):
            run = kept_run(ForcedRun, arm, FORCED_DISTRESS)
            series = run["series"]
            self.assert_exits_reached(run, arm)
            get = lambda key: series["issuer_" + key]
            alternative = max(run["rho_p"], 0.0) + FORCED_DISTRESS.owner_spread
            self.assertGreater(run["rho_p"], 0.0)
            cut = np.minimum(series["covered"], series["charges"])
            bottom = (series["own_margin"] - alternative * (series["N"] - series["pool_pt"]) + get("custodian")
                      + get("indexer") + get("expenses") + series["charges"] - cut
                      - series["wallet_yield"])
            np.testing.assert_allclose(series["joint"], bottom, rtol=0, atol=1e-12)
            self.assertTrue(np.any(series["joint"] != series["issuer_wallet"]), arm)

    def test_queued_exits_and_the_90_percent_reading_on_both_bases(self):
        """Queued exits and the 90% reading of household-held capital, on two bases.

        Example, with the issuer a pure custodian: two owners' executed exits of $1,000 each, of which pool cash paid
        $550, leave $1,305 queued beside an owner's $755, and households hold all of the $2,060 of pool capital. A
        request is queued from its filing, within its notice too, on the shares it still has to pay; one that has
        lapsed is not. The 90% reading is taken on capital net of queued exits and, beside it, on all pool capital:
        a pool where households hold $2,060 of $2,350, $1,305 of it queued, holds 72.25% net of the queue and 87.66%
        of all capital and fails both; households holding 95%, or exactly 90%, in every W2 month pass; one W2 month
        without pool capital fails, and a run ending before W2 holds in none."""
        from scripts.run_economy_population import households_pool
        w = controlled_world()
        w.shares[:3], w.nav_ps = (652.5, 652.5, 755.0), 1.0
        w.exit_start[:2], w.exit_left[:2] = 3, 652.5
        w._holdings()
        self.assertAlmostEqual(float(w.owners_held.sum()), 2060.0, places=12)
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 2060.0, places=12)
        self.assertAlmostEqual(w._queued(), 1305.0, places=12)
        # The third owner files for $100 of its $755 this month: within its notice, it is queued too.
        w.exit_start[2], w.exit_left[2] = 5, 100.0
        self.assertAlmostEqual(w._queued(), 1405.0, places=12)
        w.exit_left[2] = 1000.0                                              # never more than the shares it holds
        self.assertAlmostEqual(w._queued(), 2060.0, places=12)
        w.exit_start[:], w.exit_left[:] = -1, 0.0                           # every request lapsed or paid
        self.assertEqual(w._queued(), 0.0)
        months = 60
        economy = Economy(n=2, burn_in=0, months=months)

        def reading(owned, capital, queued=0.0, change=None, length=months):
            series = dict(N=np.full(length, capital), owners_capital=np.full(length, owned),
                          owners_queued=np.full(length, queued), p_value=np.ones(length))
            if change:
                change(series)
            span = replace(economy, months=length)
            return households_pool(dict(series=series, economy=span), span)
        both = lambda got: (got["households_hold_90_W2"], got["households_hold_90_W2_all_capital"])
        got = reading(2060.0, 2350.0, 1305.0)
        self.assertEqual(both(got), (False, False))
        self.assertAlmostEqual(got["household_share_W2_lowest"], 755.0 / 1045.0, places=4)
        self.assertAlmostEqual(got["household_share_W2_lowest_all_capital"], 2060.0 / 2350.0, places=4)
        self.assertEqual(reading(2060.0, 2060.0)["household_share_W2_lowest_all_capital"], 1.0)
        for owned in (95.0, 90.0):
            self.assertEqual(both(reading(owned, 100.0)), (True, True), owned)
        self.assertEqual(both(reading(89.0, 100.0)), (False, False))
        # Queued exits count against households on the strict base only.
        self.assertEqual(both(reading(95.0, 100.0, queued=60.0)), (False, True))
        self.assertFalse({"held_by_issuer_money", "issuer_money_usd_a_year", "fund_months",
                          "issuer_held_share"} & set(reading(95.0, 100.0)))

        def empty(series):
            series["N"][40] = series["owners_capital"][40] = 0.0
        self.assertEqual(both(reading(95.0, 100.0, change=empty)), (False, False))
        got = reading(95.0, 100.0, length=12)
        self.assertEqual((*both(got), got["p_routes_W2"], got["counts"]), (False, False, False, False))

    def test_p4_and_x3_read_the_own_margin_on_household_held_months(self):
        """Persistence test 4 and falsifier 3 read the pool's own margin on the months households hold pool capital.

        A second window whose margin sums to zero passes; -$0.01 a consumer unit a year fails; a second window held
        only by the issuer's shares gives no reading (None), however high its margin, because the opening owns the
        whole fee margin there. The joint test, read on the same months, gives none either. X3 fires only when both
        windows are below zero. The detail gives, by window, the margin, the number of household-held months it
        averages over (24 and 24, then 24 and none, then 24 and one), its parts, the joint test and the old ratio
        with its label. With the Step 4 and 5 rules off (``LEGACY_STEP45``) both read the coverage as in the first
        run, and any other reading is refused."""
        from scripts.run_economy_figures import DOLLARS, HELD_CAPITAL_LABEL, persistence
        months = 60
        series = {key: np.ones(months) for key in ("A", "N", "service", "pool_pt", "new_pool_loans", "pool_cash",
                                                  "cash_to_lend", "interest_collected", "owners_capital", "joint")}
        series.update(K=np.full(months, 0.1), pool_costs=np.zeros(months), write_off_rate=np.zeros(months),
                      arrears_share=np.zeros(months), own_margin=np.zeros(months),
                      **{"margin_" + key: np.zeros(months) for key in MARGIN_PARTS})
        run = dict(series=series, economy=Economy(n=2, burn_in=0, months=months))
        read = lambda: persistence(run, 0.6)
        series["own_margin"][36:48], series["own_margin"][48:60] = 0.5, -0.5          # W2 sums to zero
        got = read()
        self.assertIs(got["P"]["P4"], True)
        self.assertIs(got["X"]["X3"], False)
        self.assertEqual(got["detail"]["own_margin_usd_a_year"], (0.0, 0.0))
        self.assertEqual(got["detail"]["own_margin_held_months"], (24, 24))
        np.testing.assert_allclose(got["detail"]["held_capital_ratio"], (10.0, 10.0), rtol=1e-15)
        self.assertEqual(got["detail"]["held_capital_ratio_label"], HELD_CAPITAL_LABEL)
        self.assertAlmostEqual(got["detail"]["joint_usd_a_year"][1], 12 * DOLLARS, places=9)
        self.assertEqual(set(got["detail"]["own_margin_parts_usd_a_year"]), set(MARGIN_PARTS))
        self.assertNotIn("self_financing_coverage", got["detail"])
        series["own_margin"][36:60] = -0.01 / 12 / DOLLARS                              # -$0.01 a CU a year
        got = read()
        self.assertIs(got["P"]["P4"], True)        # no outside money: owners absorb the margin
        self.assertAlmostEqual(got["detail"]["own_margin_usd_a_year"][1], -0.01, places=12)
        self.assertIs(got["X"]["X3"], False)                                           # W1 is still zero
        series["own_margin"][12:36] = -0.01 / 12 / DOLLARS
        self.assertIs(read()["X"]["X3"], False)    # no outside money can enter
        # A second window held only by the issuer's shares: no reading, whatever its margin.
        series["owners_capital"][36:60], series["own_margin"][36:60] = 0.0, 1.0
        got = read()
        self.assertIsNone(got["P"]["P4"])
        self.assertIsNone(got["X"]["X3"])
        self.assertIsNone(got["detail"]["own_margin_usd_a_year"][1])
        self.assertIsNone(got["detail"]["joint_usd_a_year"][1])           # nor the joint test there
        self.assertEqual(got["detail"]["own_margin_held_months"], (24, 0))
        self.assertNotIn("Persistent", got["verdict"])
        # One household month in W2 is read alone, annualised from that month, and the count says so.
        series["owners_capital"][50], series["own_margin"][50] = 1.0, -1.0
        got = read()
        self.assertIs(got["P"]["P4"], True)        # no outside money; the margin is reported
        self.assertAlmostEqual(got["detail"]["own_margin_usd_a_year"][1], -12 * DOLLARS, places=9)
        self.assertEqual(got["detail"]["own_margin_held_months"], (24, 1))
        # The first run's reading: the coverage, collected income over K and the costs, 10 against 0.95.
        run["economy"] = replace(run["economy"], **LEGACY_STEP45)
        got = read()
        self.assertIs(got["P"]["P4"], True)
        np.testing.assert_allclose(got["detail"]["self_financing_coverage"], (10.0, 10.0), rtol=1e-15)
        self.assertNotIn("own_margin_usd_a_year", got["detail"])
        # A misspelt reading is refused rather than read as the coverage.
        with self.assertRaises(ValueError):
            replace(run["economy"], self_financing="margins")

    def test_m2_gains_are_read_in_full_with_no_issuer_transfer_line(self):
        """M2's indexation is the holder's own yield, so paired gains are read in full.

        Under competitive P the CPI indexation on P is paid out of the holder's own reserve return while the issuer
        keeps only c_I, so no run records it as an issuer transfer and the transfers report sets nothing beside the
        issuer's row. Example: a person gaining $100 against S0 over two years gains $50 a year, with no gain net of
        transfers beside it. In a pooled M2 run the issuer's books still carry the indexation, dJ/J on all P, in its
        indexer line, and its custodian, indexer and float lines net to its custody c_I every month the pool takes
        demurrage, so the indexation comes out of the holders' reserve return, not the issuer's."""
        from scripts.run_economy_population import differences, transfers
        run = kept_run(PooledWorld, "M2", replace(TINY, n=100, months=12))
        self.assertFalse({"issuer_transfers", "index_books"} & set(run))
        series = run["series"]
        np.testing.assert_allclose(-series["issuer_indexer"], replace(TINY).inflation * series["P_out"], rtol=1e-12,
                                   atol=1e-18)
        takes = (series["N"] > 0) & (series["service"] > 0)
        self.assertTrue(takes.any())
        custody = series["issuer_custodian"] + series["issuer_indexer"] + series["issuer_float"]
        np.testing.assert_allclose(custody[takes], -series["issuer_expenses"][takes], rtol=1e-9, atol=1e-18)
        self.assertNotIn("issuer_to_households_usd", transfers(run, replace(TINY, n=100, months=12)))
        economy = Economy(n=2, burn_in=1, months=24)
        cycles, no = np.array([7, 30]), np.zeros(2, bool)
        end = lambda gain: np.vstack([np.zeros((25, 2)), gain / MONTH_USD])
        s0 = dict(self.paired_run("S0", economy, cycles, no, no), wealth=end(np.zeros(2)))
        m2 = dict(self.paired_run("M2", economy, cycles, no, no), wealth=end(np.array([100.0, 0.0])))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)                    # a W2 role read on no months
            got = differences(m2, s0, economy)
        self.assertEqual((got["gain_usd_a_year"], got["gain_usd_a_year_by_cycle"]), (25.0, [50.0, 0.0]))
        self.assertFalse({"issuer_transfers_usd_a_year", "net_of_issuer_transfers"} & set(got))

    def test_transfers_and_the_gain_split_carry_the_gas_paid_to_validators(self):
        """The issuer is not a payment operator, because P payments run on stablecoin rails.

        Its row in the transfers report is its net reserve income against holding P, $33 and $2.40 on $1,000 of P, a
        $30.60 margin, with no fee and no rail. P payments' gas goes to validators: 1,000 P payments in a year pay
        $1.69, all of it real, as M0's USDC payments pay theirs. In the gain split the gas leaves the household
        economy on a line of its own, as do the card's cash-advance and late fees and the wages sent outside under
        the harsh stress."""
        from scripts.run_economy_population import split, transfers
        w = Economy(n=1, burn_in=1, months=12)
        usd = lambda dollars: dollars / MONTH_USD
        keys = ("out_interest", "pt_card", "pt_term", "penalties", "merchant_fees", "rewards", "card_payments",
                "card_value", "conversion_fees", "pool_operating", "deposit_spread", "e_bt", "savings_bt", "issuer",
                "P_out", "issuer_spread", "p_bt", "gas", "ewa_fees", "ewa_uses", "advance_fees", "late_fees")
        gas = 1000 * GAS_PER_P_PAYMENT
        m1 = transfers(self.year_of("M1", dict(issuer=usd(33), P_out=usd(1000) * 12, gas=gas), keys), w)
        self.assertEqual(m1["issuer"], dict(paid_usd=33.0, real_usd=2.4, margin_usd=30.6))
        self.assertEqual(m1["validators"], dict(paid_usd=1.69, real_usd=1.69, margin_usd=0.0))
        m0 = transfers(self.year_of("M0", dict(gas=2 * gas), keys), w)
        self.assertEqual(m0["validators"], dict(paid_usd=3.38, real_usd=3.38, margin_usd=0.0))
        self.assertNotIn("validators", transfers(self.year_of("S0", {}, keys), w))
        keys = ("out_interest", "penalties", "merchant_fees", "rewards", "conversion_fees", "pool_operating",
                "savings_income", "valuation", "inflation", "external", "gas", "advance_fees", "late_fees", "wages_out")
        arm = self.year_of("M1", dict(gas=gas, external=-gas), keys)
        parts = split(arm, self.year_of("S0", {}, keys), w)
        self.assertAlmostEqual(parts["gas_to_validators"], -1.69, places=9)
        self.assertAlmostEqual(parts["other_outside_flows"], 0.0, places=9)
        arm = self.year_of("M1", dict(advance_fees=usd(10), late_fees=usd(30), external=-usd(40)), keys)
        parts = split(arm, self.year_of("S0", {}, keys), w)
        self.assertEqual((round(parts["advance_fees_saved"], 9), round(parts["late_fees_saved"], 9)), (-10.0, -30.0))
        self.assertAlmostEqual(parts["other_outside_flows"], 0.0, places=9)


    # ---- Demurrage and pool entry -----------------------------------------------------------------------------

    def test_wallet_p_earns_its_yield_less_demurrage_and_the_issuer_keeps_its_custody(self):
        """Wallet P earns its yield less demurrage, and the issuer keeps its custody cost.

        The issuer's share of the reserve return is derived, never set: its break-even under contestable issuance,
        s_I = c_I / rho with c_I 0.24%: 5.45% at 4.4%, 12% at 2%, 10% in M2 at 4.4% (2.4% real), and all of it where
        rho is at or below c_I (r_out 0.2%) or zero (M2 at r_out 2%); outside the pool arms there is none.

        Example, one model month standing for the year: in a month whose two wallets held
        $1,000 and $500 of P and the pool's own cash $200, the reserve return at 4.4% is $74.80. With demurrage at
        0.66%, the holders are paid 4.16% less 0.66%, $35.00 and $17.50, as P, the pool takes the $9.90 of demurrage
        and $8.32 on its own cash, $70.72 in all from outside the household economy, and the issuer keeps $4.08,
        exactly its 0.24% cost of the $1,700, so its custodian, float and expense lines net to zero. In M2 the real
        return of $40.80 pays the holders 2.16% less 0.66%, $15.00 and $7.50, and the pool $9.90 and $4.32, leaving the
        issuer the same $4.08. In U, with no demurrage, the holders get $41.60 and $20.80. With no pool shares, or a
        pool winding down, no demurrage is withheld and the issuer keeps the pool cash's $8.32 too."""
        share = lambda arm, r_out: _World(replace(Inputs(), rho_H=r_out / 12), 0.6, Economy(n=10), arm).s_issuer
        self.assertAlmostEqual(share("M1", 0.044), 0.0024 / 0.044, places=15)
        self.assertAlmostEqual(share("M1", 0.044), 0.0545, places=4)
        self.assertAlmostEqual(share("M1", 0.02), 0.12, places=15)
        self.assertAlmostEqual(share("M2", 0.044), 0.10, places=12)
        self.assertEqual((share("M1", 0.002), share("M2", 0.02)), (1.0, 1.0))
        self.assertEqual(share("U", 0.044), share("M1", 0.044))
        self.assertTrue(np.isnan(share("S0", 0.044)) and np.isnan(share("M0", 0.044)))
        self.assertEqual(issuer_share(0.044, 0.0), 0.0)

        def month(arm="M1", inflation=0.0, shares=True, winding=False):
            economy = Economy(n=10, burn_in=10, months=1, inflation=inflation, issuer_cost=0.0024)
            w = _World(replace(Inputs(), rho_H=0.044), 0.6, economy, arm)
            w.month(0)                                                  # a quiet month opens every account
            w.pcash[:], w.pool_cash, w.external = 0.0, 0.0, 0.0
            if shares:
                funded_pool(w, 200.0)
            w.winding, w.c = winding, (0.0066 if w.demurrage else 0.0)
            w.acc["p_bt"][:] = 0.0
            w.acc["p_bt"][:2] = 1000.0, 500.0
            w.acc["p_yield"][:], w.acc["charges"][:] = 0.0, 0.0
            w.acc.update(p_all=1700.0, pool_cash_bt=200.0)
            cash = w.pool_cash
            taken = w._reserve_return()
            return w, w.pool_cash - cash, taken
        w, into, taken = month()
        np.testing.assert_allclose(w.pcash[:2], [35.0, 17.5], rtol=1e-12)
        np.testing.assert_allclose(w.acc["p_yield"][:2], [41.6, 20.8], rtol=1e-12)      # before demurrage
        np.testing.assert_allclose(w.acc["charges"][:2], [6.6, 3.3], rtol=1e-12)         # withheld
        self.assertAlmostEqual(taken, 9.9, places=10)
        self.assertAlmostEqual(w.acc["wallet_yield"], 62.4, places=10)
        self.assertAlmostEqual(w.acc["float_pool"], 8.32, places=10)
        self.assertAlmostEqual(into, 18.22, places=10)
        self.assertAlmostEqual(w.external, 70.72, places=10)
        self.assertAlmostEqual(w.acc["float_issuer"], 4.08, places=10)
        books = w._issuer_books()
        self.assertAlmostEqual(books["custodian"] + books["indexer"] + books["float"] + books["expenses"], 0.0,
                               places=10)
        self.assertAlmostEqual(books["expense_holding"], -4.08, places=10)
        w, into, taken = month("M2", inflation=0.02)
        np.testing.assert_allclose(w.pcash[:2], [15.0, 7.5], rtol=1e-12)
        self.assertAlmostEqual(into, 14.22, places=10)
        self.assertAlmostEqual(taken, 9.9, places=10)
        self.assertAlmostEqual(w.acc["float_issuer"], 4.08, places=10)
        books = w._issuer_books()
        self.assertAlmostEqual(books["custodian"] + books["indexer"] + books["float"] + books["expenses"], 0.0,
                               places=10)
        w, into, taken = month("U")
        np.testing.assert_allclose(w.pcash[:2], [41.6, 20.8], rtol=1e-12)
        self.assertAlmostEqual(into, 8.32, places=10)
        self.assertAlmostEqual(w.acc["float_issuer"], 4.08, places=10)
        self.assertEqual(taken, 0.0)
        for w, into, taken in (month(shares=False), month(winding=True)):
            np.testing.assert_allclose(w.pcash[:2], [41.6, 20.8], rtol=1e-12)
            self.assertEqual((into, taken, w.acc["float_pool"]), (0.0, 0.0, 0.0))
            self.assertAlmostEqual(w.acc["float_issuer"], 12.40, places=10)

    def test_capital_settles_at_the_free_entry_limit_where_the_quote_is_the_alternative(self):
        """Capital settles at the free-entry limit N*, where the quote is the owners' alternative.

        Example, one model month standing for the year, owners' alternative 5% and no spread, the pool's own cash
        earning p_net 4%: F, the fee margin, is 0 with no fees, so N* is the capital target: the last cycle lent
        $1,000 and N* is $1,000 whether its realised margin was +$10 or -$10, which stay in owners' NAV, not in N*.
        The quote at capital N is (alt min(N, P*) + p_net max(N - P*, 0)) / N: the alternative at N* and below it,
        54 / 1,100 at $1,100 and 130 / 3,000 at $3,000, falling towards p_net above N*. With no return on idle cash
        (p_net 0) it is N* = P* + m / rho at m = 0, $1,000 again, and at a real reserve rate of zero N* is the
        lending need alone. N* never reads the pool's own capital, so it cannot ratchet. In a dealing, a saver whose
        own rate is rho_H plus the owners' spread invests at N* (a tie) up to N* whatever the realised margin; an
        owner whose own realised return is its alternative stays, since exits read each owner's own return, not the
        quote."""
        def limit(margin, rho=0.05, pool=0.04):
            w = controlled_world()
            w.economy, w.rho_p, w.p_net = replace(w.economy, owner_spread=0.0), rho, pool
            return w, w._limit([entry(need=1000.0, need_term=1000.0, margin=margin)] * 2)
        for margin in (10.0, -10.0):
            w, (N, quote) = limit(margin)
            self.assertEqual((N, w.margin), (1000.0, 0.0))
            self.assertAlmostEqual(quote, 0.05, places=15)
            self.assertAlmostEqual(w._quote(800.0), 0.05, places=15)
            self.assertAlmostEqual(w._quote(1100.0), 54.0 / 1100.0, places=15)
            self.assertAlmostEqual(w._quote(3000.0), 130.0 / 3000.0, places=15)
        self.assertEqual(limit(10.0, pool=0.0)[1][0], 1000.0)
        self.assertEqual(limit(10.0, rho=0.0)[1][0], 1000.0)

        def dealt(margin):
            w = controlled_world()
            w.launched = True
            w.window = [entry(need=1.0, need_term=1.0, margin=margin, lent=1.0)] * 2
            w._cycle_terms(1)
            w.cash[0], w.mm_share[:] = 5.0, 1.0
            w.shares[1], w.nav_ps, w.pool_cash = 0.5, 1.0, 0.5             # an owner already holding 0.5
            closed(w, 0, float(w._owners_alternative_nominal()[1]) - w.index)   # which earned its alternative
            w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
            return w, w._dealing(1)
        for margin in (0.001, -0.001):
            w, capital = dealt(margin)
            alternative = w._owners_alternative()
            self.assertEqual(w.Q, 1.0)                                         # the capital target
            self.assertAlmostEqual(w.R_hat, alternative, places=15)        # at N*, the alternative: a tie, invests
            self.assertGreater(float(w.shares[0]), 0.0)
            self.assertAlmostEqual(capital, w.Q, places=12)                    # entry stops at N*
            self.assertEqual(int(w.exit_start[1]), -1)

    def test_a_pool_whose_last_share_is_paid_out_reopens_by_free_entry(self):
        """Free entry applies in every month: the single owner's exit winds the pool down and its
        last share is paid out at the dealing two months on, which takes no entry although a saver offers. The pool is
        then not closed for good: at the next dealing with a lending need (an N* of 5 months of spending here, the quote
        above the saver's own rate) the saver enters at the published quote up to N*, as at launch, and the pool takes
        demurrage again once it has shares."""
        w = self.owned_pool(1.0, loan=False)
        w.part[4], w.pcash[4], w.mm_share[:] = True, 500.0, 1.0          # a saver with money-market money
        w.pool_alternative[4] = 0.001
        w.R_hat, w.Q = 0.01, 10.0
        w.last["flows"][:], w.last["flows_s0"][:] = 0.0, 0.0
        earning(w, 0.0)                                                    # the owner earns below its own rate
        w.owner_draws = np.where(np.arange(10) == 0, 0.0, 1.0), np.zeros(10)   # the owner alone reviews and leaves
        w.R_hat = 0.0                                                      # no saver enters while the owner is in
        list(map(w._dealing, (1, 2)))
        self.assertFalse(w.winding)
        w.R_hat = 0.01
        w._dealing(3)                                                      # executed and paid in full
        self.assertEqual((float(w.shares[0]), float(w.shares[4]), w.winding), (0.0, 0.0, False))
        self.assertAlmostEqual(float(w.acc["exit_paid"]), 1.0, places=12)
        w.Q = 5.0
        w._dealing(4)                                                      # a later dealing: entry by free entry
        self.assertGreater(float(w.shares[4]), 4.9)                         # it takes almost all the room
        self.assertAlmostEqual(w._all_shares() * w.nav_ps, 5.0, places=12)   # the old owner's payout re-enters too
        self.assertAlmostEqual(w.pool_cash, 5.0, places=12)
        self.assertTrue(not w.winding and w._takes_demurrage())

    def test_the_launch_plan_prices_the_fixed_cost_on_its_lending_need_with_no_fee_and_no_demurrage(self):
        """The launch plan prices the fixed cost on its lending need, with no fee and no demurrage.

        Example: half the people participate at launch, and the lending need P* is the
        mean of the participants' bridging need path, 3. No fee exists (P payments run on stablecoin rails), so the
        plan's only cost beyond its loans is the fixed cost, ten people's $0.322 a month, which the coupon prices on
        that lending need at break-even: its part is the fixed cost over 3 a month, and the plan's margin F is zero.
        The launch month's limit is the free-entry N* at F zero: in U the lending need P* itself, and in M1 the peak
        bridging need, the path's largest day, 4 (demurrage pays for liquidity kept available), where
        the quote is owners' alternative.
        Under competitive P the wallets' reserve return goes to their holders, no bridging is observed yet and the pool
        holds no cash, so the plan counts no demurrage and is the same in U and M1. With no bridging need there is no
        lending to price the fixed cost on: the coupon has no fixed part, the margin is minus the fixed cost and the
        limit is zero."""
        def plan(arm, need=True):
            w = controlled_world(arm)
            w.part[:5] = True
            w.last["bridge_path"] = np.zeros((10, DAYS))
            if need:
                w.last["bridge_path"][0], w.last["bridge_path"][1, :15], w.last["bridge_path"][6] = 2.0, 2.0, 9.0
            w.launched = True
            w._cycle_terms(w.economy.burn_in)
            return w, w.window[0]
        fixed = Inputs().C_fix * 10
        w, got = plan("M1")
        self.assertAlmostEqual(got["need"], 3.0, places=15)
        self.assertEqual((got["margin"], got["fixed"], got["lent"]), (0.0, fixed, got["need"]))
        self.assertEqual((got["revenue"], got["capital_cost"], got["wallet"], got["charges"]), (0.0, 0.0, 0.0, 0.0))
        self.assertAlmostEqual(w.r_fix, fixed / 3.0, places=15)
        alternative = w._owners_alternative()
        self.assertAlmostEqual(w.r_g, alternative + w.inputs.o + fixed / 3.0, places=15)
        self.assertEqual(w.r_term, w.r_g)                                   # no loss learned yet
        self.assertEqual((w.Q, w.peak, w.standby), (4.0, 4.0, 0.0))
        self.assertAlmostEqual(w.R_hat, alternative, places=15)
        self.assertEqual((w.c, w.coverage), (0.0, 0.0))
        u, plain = plan("U")
        np.testing.assert_equal(plain, got)
        self.assertEqual(u.Q, got["need"])
        w, got = plan("M1", need=False)
        self.assertEqual((got["need"], got["margin"], w.r_fix, w.Q), (0.0, -fixed, 0.0, 0.0))
        self.assertTrue(np.isnan(w.R_hat))

    def test_the_coupon_carries_the_fixed_cost_at_break_even(self):
        """The coupon carries the pool's fixed cost at break-even, the zero-profit principle.

        P payments run on stablecoin rails, so no fee carries the fixed cost.

        Example ($): ten people at the core's fixed cost of
        $0.322 a person a month bear $3.22 a month; over the last cycle, two months whose loans carried $3,220 of
        principal-time each, bridging and term, that is $6.44 over $6,440 of principal-months, 0.1% a month (1.2% a
        year), added to the coupon's operating part o, 2% a year, beside the capital part, owners' alternative. A
        bridge drawn this month, its whole capital part covered by demurrage, is sealed at o and the fixed part alone,
        3.2% a year: the bridger pays the fixed cost after demurrage covers the capital part. Accrued on the same
        lending the fixed part pays the $6.44 exactly. A cycle that lent nothing prices the fixed cost a month on its
        lending need P*: $3.22 a month over a need of $3,220 is 0.1% again; with no lending need, or
        no cycle, there is no fixed part."""
        w = controlled_world()
        funded_pool(w, 1.0)
        fixed = Inputs().C_fix * 10
        self.assertAlmostEqual(fixed * MONTH_USD, 3.22, places=12)
        month = entry(need=0.5, need_term=0.5, fixed=fixed, lent=0.5, capital_cost=0.001, wallet=1.0)
        w.window = [dict(month), dict(month)]
        self.assertAlmostEqual(0.5 * MONTH_USD, 3220.0, places=9)
        w._cycle_terms(11)
        self.assertAlmostEqual(w.r_fix, 0.001, places=15)
        self.assertAlmostEqual(w.r_fix * 12, 0.012, places=15)
        self.assertAlmostEqual(w.r_fix * (0.5 + 0.5), 2 * fixed, places=15)   # the fixed part pays the cycle's cost
        alternative = w._owners_alternative()
        self.assertAlmostEqual(w.r_g, alternative + w.inputs.o + 0.001, places=15)
        self.assertEqual(w.coverage, 1.0)
        self.assertAlmostEqual(w.r_b, w.inputs.o + 0.001, places=15)
        self.assertAlmostEqual(w.r_b * 12, 0.032, places=15)
        self.assertAlmostEqual(w._fixed_rate([dict(month, lent=0.0)] * 2), 0.001, places=15)
        self.assertEqual(w._fixed_rate([dict(month, lent=0.0, need=0.0)] * 2), 0.0)
        self.assertEqual(w._fixed_rate([]), 0.0)

    def test_the_pools_own_margin_is_zero_at_break_even_in_a_steady_cycle(self):
        """Over a steady cycle the coupon's fixed part pays the fixed cost exactly: the pool's loans
        carried 0.5 of principal-time in each of the last two months, a term loan of 0.5 is sealed at this month's
        coupon and carried the whole month, and it accrues the capital part on its principal-time, the operating cost
        and the fixed cost, so the pool's own margin, coupons less the operating cost, the fixed cost and owners'
        alternative on the principal-time lent, is zero, with no loss learned."""
        w = controlled_world()
        funded_pool(w, 1.0)
        fixed = Inputs().C_fix * 10
        w.window = [entry(need=0.5, need_term=0.5, fixed=fixed, lent=0.5)] * 2
        w._cycle_terms(11)
        w._add_loans(np.array([0]), True, TERM, np.array([0.5]), w.r_term, 0.1, BIG, np.array([60]), 0)
        w.acc.update(coupons=0.0, op_cost=0.0, pool_pt=0.0, written_off=0.0, recovered=0.0)
        list(map(lambda _: w._accrue(), range(DAYS)))
        self.assertAlmostEqual(w.acc["pool_pt"], 0.5, places=15)
        parts, margin = w._own_margin(fixed)
        self.assertAlmostEqual(parts["coupons"], (w._owners_alternative() + w.inputs.o + fixed / 0.5) * 0.5,
                               places=15)
        self.assertAlmostEqual(margin, 0.0, places=15)

    def test_the_engine_reads_no_provider_fee_and_gas_is_the_only_payment_cost(self):
        """No provider fee exists, since P payments run on stablecoin rails: the same small pooled run at
        the core model's 0.2% fee and at 5% gives every record exactly, in M1 and in M0, so the engine reads none; the
        P payments' only cost is gas, one transfer a completed P payment in M1 (the share completed) and two a USDC
        payment in M0, and the records hold no fee, rail or owners' own fees anywhere."""
        economy = replace(TINY, n=100, months=8)
        for arm, gas in (("M1", GAS_PER_P_PAYMENT), ("M0", GAS_PER_PAYMENT)):
            low = PooledWorld(Inputs(), 0.6, economy, arm).run()
            high = PooledWorld(replace(Inputs(), alpha=0.05), 0.6, economy, arm).run()
            self.assert_same_outcome(low, high, ())
            series = low["series"]
            self.assertGreater(float(series["p_payments"].sum()), 0.0, arm)
            np.testing.assert_allclose(series["gas"], gas * series["p_payments"], rtol=1e-12, atol=1e-21)
            self.assertFalse(any("fee" in key and key.startswith(("margin", "issuer")) for key in series), arm)
            self.assertNotIn("alpha_paid", low["channels"])
            np.testing.assert_allclose(low["channels"]["gas_paid"].sum(), series["gas"].sum() * economy.n, rtol=1e-12)

    def test_p_payments_cost_one_transfers_gas_with_or_without_a_pool(self):
        """P payments run on stablecoin rails and cost one transfer's gas, with or without a pool.

        P is a token on the same chain as USDC, so a P payment costs its payer one transfer's gas on Base, $0.00169
        (growthepie, October 2026 mean), half a USDC payment's two legs, whatever its value: a $64.40 and a $6,440
        card-eligible purchase between participants each cost their payer exactly that. It leaves for the
        validators, outside the economy, as P redeemed, so the reserves fall with it; the payees receive the full
        amounts, the pool's cash is untouched and nobody inside receives a fee. P payments do not depend on the
        pool: the same holds with a pool that serves and after launch with none."""
        self.assertAlmostEqual(GAS_PER_P_PAYMENT * MONTH_USD, 0.00169, places=15)
        self.assertEqual(GAS_PER_PAYMENT, 2 * GAS_PER_P_PAYMENT)
        for serves in (True, False):
            w = controlled_world()
            if serves:
                funded_pool(w, 5.0)
            w.part[:], w.holder[[0, 2]], w.launched = True, True, True
            w.pcash[0], w.pcash[2], w.reserves = 2.0, 2.0, 4.0
            cash, merchant = w.pool_cash, w.acc["merchant"].copy()
            w.ob = dict(buyer=np.array([0, 2]), seller=np.array([1, 3]), amount=np.array([0.01, 1.0]),
                        settle=np.array([30, 30]), card=np.array([True, True]), kind=np.full(2, SERVICE))
            w.receivable[[1, 3]], w.payable[[0, 2]] = (0.01, 1.0), (0.01, 1.0)
            w._settle(1, 30)
            self.assertEqual(w.service, serves)
            np.testing.assert_allclose(w.acc["gas"][[0, 2]], GAS_PER_P_PAYMENT, rtol=1e-12)
            np.testing.assert_allclose(w.pcash[[0, 2]], [2.0 - 0.01 - GAS_PER_P_PAYMENT, 1.0 - GAS_PER_P_PAYMENT],
                                       rtol=1e-12)
            np.testing.assert_allclose(w.pcash[[1, 3]], [0.01, 1.0], rtol=1e-12)
            self.assertAlmostEqual(w.external, -2 * GAS_PER_P_PAYMENT, places=15)
            self.assertAlmostEqual(w.reserves, 4.0 - 2 * GAS_PER_P_PAYMENT, places=15)
            self.assertEqual(w.pool_cash, cash)
            self.assertEqual(w.acc["p_n"], 2.0)
            np.testing.assert_array_equal(w.acc["merchant"], merchant)          # no card fee: both went in P

    def test_a_bridge_is_sealed_at_the_coupon_less_the_capital_part_demurrage_pays(self):
        """A bridge is sealed at the coupon less the capital part that demurrage pays.

        Example: with coverage of a half (demurrage held at rho_p - c_I on a cycle's wallet P that pays half its $1
        capital cost), a bill the pool bridges this month is sealed at r_b, the coupon less half its capital part
        (owners' alternative, the owners' spread included), and carries that cut. A day's accrual books the borrower's
        coupon at r_b and the cut demurrage pays beside it, so theta, demurrage's share of bridging finance, is the cut
        over the full coupon. Next month's terms do not reprice the sealed bridge."""
        w = controlled_world()
        funded_pool(w, 10.0)
        w.window = [entry(revenue=0.25, capital_cost=0.5, wallet=0.25 / w.p_net, charges=0.25)] * 2
        w._cycle_terms(11)
        alternative = w._owners_alternative()
        self.assertAlmostEqual(w.coverage, 0.5, places=15)
        self.assertAlmostEqual(w.r_b, w.r_g - 0.5 * alternative, places=15)
        w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
        w.last["receipts"][:] = 1.0
        one_invoice(w, 0.04, card=False)
        w._settle(1, 30)
        bridge = w.book["pool"] & (w.book["kind"] == BRIDGE)
        self.assertEqual(int(bridge.sum()), 1)
        self.assertAlmostEqual(float(w.book["principal"][bridge][0]), 0.04, places=15)
        self.assertEqual(float(w.book["rate"][bridge][0]), w.r_b)
        self.assertAlmostEqual(float(w.book["cover"][bridge][0]), 0.5 * alternative, places=15)
        w.acc.update(covered=0.0, bridge_coupons=0.0, coupons=0.0)
        w.r_b = w.r_g                                                      # next month's terms, say
        w._accrue()
        self.assertAlmostEqual(w.acc["bridge_coupons"], 0.04 * (w.r_g - 0.5 * alternative) / DAYS, places=15)
        self.assertAlmostEqual(w.acc["covered"], 0.04 * 0.5 * alternative / DAYS, places=15)
        theta = w.acc["covered"] / (w.acc["covered"] + w.acc["bridge_coupons"])
        self.assertAlmostEqual(theta, 0.5 * alternative / w.r_g, places=12)


    def test_demurrage_pays_the_coupon_cut_and_the_pool_cash_return_is_pool_income(self):
        """Demurrage pays the coupon cut, and the return on the pool's cash is pool income.

        Example, one model month standing for the year, the reserve rate 4.4%, c_I 0.24%, no owners' spread and no
        fixed cost: a pool of $1,000, all lent, earns $30 of coupons from its borrowers,
        sealed at r_b, while demurrage at 1.4% on $1,000 of wallet P takes the $14 the cut costs. Its realised return
        is R = (30 + 14) / 1,000, owners' alternative; the margin F next month's quote reads is zero, demurrage
        just paying the cut, so N* is the lending need; and the pool's own margin counts the full coupon, $44, and is
        zero too. The holders are paid 4.16% less 1.4% on their $600 and $400. With $200 of the pool's own cash beside
        it, that cash's $8.32 is pool income in R, (30 + 14 + 8.32) / 1,000, but not in the margin F, which stays zero:
        the free-entry quote counts that return on capital beyond P* instead, so N* cannot ratchet on it, and the own
        margin's coupons still add at most the demurrage taken, $14: with a $20 cut (c was published from the cycle
        before) they are $44, not $50, as the pool cash's return is no coupon income."""
        def close(pool_cash_bt, covered=14.0):
            w = controlled_world(cost=0.0)
            w.economy = replace(w.economy, owner_spread=0.0, issuer_cost=0.0024)
            w.inputs, w.rho_p = replace(w.inputs, rho_H=0.044), 0.044
            w.s_issuer = issuer_share(0.044, 0.0024)
            w.p_net, w.c = (1 - w.s_issuer) * 0.044, 0.014
            funded_pool(w, 1000.0)
            w.capital, w.owners_held = 1000.0, w.shares * w.nav_ps
            w.pcash[:] = 0.0
            w.acc["p_bt"][:] = 0.0
            w.acc["p_bt"][:2] = 600.0, 400.0
            w.acc["p_yield"][:], w.acc["charges"][:] = 0.0, 0.0
            w.acc.update(p_all=1000.0 + pool_cash_bt, pool_cash_bt=pool_cash_bt, coupons=30.0, covered=covered,
                         op_cost=0.0, written_off=0.0, recovered=0.0, pool_pt=1000.0, refused=0.0,
                         bridge_pt=np.zeros(10))
            w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
            return w
        w = close(0.0)
        self.assertAlmostEqual(w.series["charges"][-1] * 10, 14.0, places=10)
        self.assertAlmostEqual(w.series["R"][-1], (30.0 + 14.0) / 1000.0, places=12)
        self.assertAlmostEqual(w.window[-1]["margin"], 0.0, places=10)
        self.assertAlmostEqual(w.window[-1]["revenue"] - w.window[-1]["covered"], 0.0, places=10)
        self.assertAlmostEqual(w.series["margin_coupons"][-1] * 10, 44.0, places=10)
        self.assertAlmostEqual(w.series["own_margin"][-1] * 10, 0.0, places=10)
        np.testing.assert_allclose(w.acc["p_yield"][:2] - w.acc["charges"][:2], [(0.0416 - 0.014) * 600.0,
                                                                                 (0.0416 - 0.014) * 400.0], rtol=1e-12)
        w = close(200.0)
        self.assertAlmostEqual(w.series["float_pool"][-1] * 10, 8.32, places=10)
        self.assertAlmostEqual(w.series["R"][-1], (30.0 + 14.0 + 8.32) / 1000.0, places=12)
        self.assertAlmostEqual(w.window[-1]["margin"], 0.0, places=10)
        self.assertAlmostEqual(w.series["margin_coupons"][-1] * 10, 44.0, places=10)
        self.assertAlmostEqual(close(200.0, covered=20.0).series["margin_coupons"][-1] * 10, 44.0, places=10)


    def test_u_is_m1_with_no_demurrage_on_the_same_draws(self):
        """U is the same P with no demurrage, so U against M1 is what demurrage adds.

        An M1 world with demurrage turned off gives every record of U. On the same draws U and M1 share every record
        before launch, and their launch plans are the same (no demurrage is observed yet). In U demurrage and
        coverage are zero, a bridge pays the full coupon and wallet P earns rho_p - c_I on its balance-time; in M1 it
        earns that less the demurrage the pool takes. With no provider fee (100 people, 10 months after launch,
        r_out 4.44%) both pools form."""
        from scripts.run_economy_figures import engine_inputs
        economy, inputs = Economy(n=100, months=10), engine_inputs()

        class NoDemurrage(_World):
            def __init__(self, *args):
                super().__init__(*args)
                self.demurrage = False
        worlds = {arm: _World(inputs, 0.6, economy, arm) for arm in ("M1", "U")}
        runs = {arm: world.run() for arm, world in worlds.items()}
        off = NoDemurrage(inputs, 0.6, economy, "M1").run()
        self.assert_same_outcome(runs["U"], off, ("arm",))
        launch = economy.burn_in
        m1, u = runs["M1"], runs["U"]
        for key in m1["series"]:
            np.testing.assert_array_equal(m1["series"][key][:launch], u["series"][key][:launch], err_msg=key)
        np.testing.assert_array_equal(m1["wealth"][:launch + 1], u["wealth"][:launch + 1])
        np.testing.assert_equal(worlds["M1"].window[0], worlds["U"].window[0])
        s, after, p_net = u["series"], slice(launch, None), worlds["U"].p_net
        self.assertFalse(s["c"][after].any() or s["coverage"][after].any() or s["charges"][after].any())
        np.testing.assert_array_equal(s["r_b"], s["r_g"])
        np.testing.assert_array_equal(s["p_yield"][after], p_net)
        np.testing.assert_allclose(s["wallet_yield"][after], p_net * s["p_bt"][after], rtol=1e-12, atol=1e-18)
        t = m1["series"]
        np.testing.assert_allclose(t["p_yield"][after], p_net - t["c"][after], rtol=0, atol=1e-18)
        self.assertGreater(float(t["charges"][after].sum()), 0.0)
        self.assertTrue(np.all(t["N"][after] > 0) and np.all(s["N"][after] > 0))


    def test_a_small_run_forms_a_pool_at_its_limit_and_keeps_every_record(self):
        """In a small economy (100 people, 10 months after launch, r_out 4.44%, no provider fee, no test
        device) every pool arm's pool forms at launch, entry filling it to N*, which is the lending need P* since the
        launch plan's margin F is zero when the coupon carries the fixed cost at break-even, so the quote at N*
        is owners' alternative, rho_H plus the owners' spread; in no month is the quote at N* above it. In M1
        demurrage stays within its bound and is taken only while the pool serves; where it is below its bound and the
        cycle bridged it covers the whole capital cost of bridging, a bridge is sealed at the coupon less coverage
        times owners' alternative, the coupon is at least that alternative and o, and theta lies within the
        alternative's share of the coupon (a bridge's cut is at most the alternative and its rate at least o). In every
        pool arm the issuer's custody nets to zero every month the pool takes demurrage and its cash's return (its
        take pays exactly its 0.24% of P; in a wind-down the pool cash's return stays with the issuer), the yield on
        wallet P, the pool cash's return and the issuer's custody add up to the reserve return on all P, and P's
        published yield is rho_p - c_I - c plus M2's indexation. The total
        precautionary money is households' buffers plus the pool's idle cash (idle P, inside the buffers, is recorded
        beside it and not counted twice), and failures are the month's new failed payments. Wealth
        accounting is exact in every arm, U included, and backing in every pool arm."""
        from scripts.run_economy_figures import engine_inputs
        economy, inputs = Economy(n=100, months=10), engine_inputs()
        launch, after = economy.burn_in, slice(economy.burn_in, None)
        for arm in ("S0", "M0", "M1", "M2", "U"):
            world = _World(inputs, 0.6, economy, arm)
            run = world.run()
            s = run["series"]
            np.testing.assert_allclose(s["wealth_change"], s["external"] + s["valuation"] + s["inflation"],
                                       atol=1e-12, err_msg=arm)
            np.testing.assert_allclose(s["precautionary"], s["buffers"] + s["pool_idle"], rtol=1e-12, atol=1e-15)
            np.testing.assert_allclose(s["buffers"], run["buffers"].sum(axis=1) / economy.n, rtol=1e-12)
            np.testing.assert_allclose(s["failures"], run["failed"].sum(axis=1) / economy.n, rtol=1e-12, atol=1e-18)
            if arm in ("S0", "M0"):
                self.assertTrue(np.isnan(s["s_issuer"]).all() and not s["bridges"].any(), arm)
                self.assertFalse(s["wallet_yield"].any() or s["charges"].any(), arm)
                continue
            backing = s["backing"][after]
            np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9, err_msg=arm)
            rate = max(world.rho_p, 0.0)
            np.testing.assert_allclose(s["float_pool"][after] + s["float_issuer"][after] + s["wallet_yield"][after],
                                       rate * s["P_out"][after], rtol=1e-12, atol=1e-18)
            np.testing.assert_allclose(s["p_yield"][after], world.index + world.p_net - s["c"][after], rtol=0,
                                       atol=1e-18)
            custody = s["issuer_custodian"] + s["issuer_indexer"] + s["issuer_float"] + s["issuer_expense_holding"]
            takes = (s["N"] > 0) & (s["service"] > 0)
            self.assertTrue(takes[launch], arm)
            np.testing.assert_allclose(custody[takes], 0.0, atol=1e-15, err_msg=arm)
            np.testing.assert_allclose(s["float_issuer"][takes], world.s_issuer * rate * s["P_out"][takes], rtol=1e-12)
            alternative = world._owners_alternative()
            self.assertAlmostEqual(float(s["N"][launch]), float(s["Q"][launch]), places=15)
            self.assertAlmostEqual(float(s["R_hat"][launch]), alternative, places=15)
            quoted = np.isfinite(s["R_hat"][after])
            self.assertTrue(np.all(s["R_hat"][after][quoted] <= alternative * (1 + 1e-12)), arm)
            if arm != "M1":
                continue
            c, coverage = s["c"][launch + 1:], s["coverage"][launch + 1:]
            self.assertTrue(np.all((c >= 0) & (c <= world.p_net)))
            self.assertFalse(np.any(c[s["service"][launch + 1:] == 0]))
            free = (c > 0) & (c < world.p_net) & (s["bridge_capital_cost"][launch:-1] > 0)
            self.assertTrue(free.any())
            np.testing.assert_allclose(coverage[free], 1.0, rtol=0, atol=1e-15)
            np.testing.assert_allclose(s["r_b"][launch + 1:], s["r_g"][launch + 1:] - coverage * alternative, rtol=0,
                                       atol=1e-18)
            self.assertTrue(np.all(s["r_g"][after] >= alternative + inputs.o - 1e-18))
            self.assertGreater(float(s["bridges"][after].sum()), 0.0)
            theta = s["theta"][launch + 1:]
            seen = np.isfinite(theta)
            self.assertTrue(seen.any())
            self.assertTrue(np.all((theta[seen] > 0) & (theta[seen] <= alternative / (alternative + inputs.o) + 1e-12)))



    def test_owners_earn_their_alternative_on_a_steady_cycle_with_idle_standby(self):
        """Owners earn their alternative on a steady cycle with idle standby, as demurrage pays for liquidity kept
        available.

        Example, one model month standing for the year, the reserve rate 4.4%, c_I 0.24%, so idle cash earns p_net
        4.16%, no owners' spread and no fixed cost: a pool of $1,500 carries $1,500 of bridges for the first half
        of a month and $500 for the second, $1,000 of principal-time, its peak bridging need $1,500, so its cash, $0 and
        then $1,000, is all standby, $500 of cash-time. Bridges sealed at the coupon less their whole capital part pay
        o, $20, which the operating cost takes. Demurrage at c = (4.4% x 1,000 + 0.24% x 500) / 10,000 = 0.452% on
        $10,000 of wallet P takes $45.20 and the pool's cash earns $20.80, so owners earn (45.20 + 20.80) / 1,500 =
        4.4%, their alternative exactly; with demurrage covering bridging alone, 0.44%, they would earn 4.32%. The
        month's margin less the standby's part is zero, so the next terms read N* at the capital target, the peak $1,500
        (no term lending), the quote there is the alternative, and c on the same cycle is the same 0.452%. U reads the
        lending need, $1,000, as its target."""
        def close(c, arm="M1"):
            w = controlled_world(arm, cost=0.0)
            w.economy = replace(w.economy, owner_spread=0.0, issuer_cost=0.0024)
            w.inputs, w.rho_p = replace(w.inputs, rho_H=0.044), 0.044
            w.s_issuer = issuer_share(0.044, 0.0024)
            w.p_net, w.c = (1 - w.s_issuer) * 0.044, c
            funded_pool(w, 1500.0)
            w.capital, w.owners_held = 1500.0, w.shares * w.nav_ps
            w.pcash[:] = 0.0
            w.acc["p_bt"][:] = 0.0
            w.acc["p_bt"][:2] = 6000.0, 4000.0
            w.acc["p_yield"][:], w.acc["charges"][:] = 0.0, 0.0
            half = np.arange(DAYS) < DAYS // 2
            w.acc.update(p_all=10500.0, pool_cash_bt=500.0, coupons=20.0, covered=44.0, op_cost=20.0,
                         written_off=0.0, recovered=0.0, pool_pt=1000.0, refused=0.0, refused_bridging=0.0,
                         refused_term=0.0, exposure=np.array([1000.0, 0.0]), bridge_pt=np.r_[1000.0, np.zeros(9)],
                         bridge_day=np.where(half, 1500.0, 500.0), ready_day=np.where(half, 0.0, 1000.0))
            w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
            return w
        alternative, p_net = 0.044, (1 - issuer_share(0.044, 0.0024)) * 0.044
        self.assertAlmostEqual(p_net, 0.0416, places=15)
        c = (alternative * 1000.0 + (alternative - p_net) * 500.0) / 10000.0
        self.assertAlmostEqual(c, 0.00452, places=15)
        w = close(c)
        self.assertAlmostEqual(w.series["charges"][-1] * 10, 45.2, places=10)
        self.assertAlmostEqual(w.series["float_pool"][-1] * 10, 20.8, places=10)
        self.assertAlmostEqual(w.series["R"][-1], alternative, places=15)
        self.assertAlmostEqual(close(alternative * 1000.0 / 10000.0).series["R"][-1], 0.0432, places=15)
        month = w.window[-1]
        self.assertAlmostEqual(month["margin"], (alternative - p_net) * 500.0, places=10)
        w.window = [month, dict(month)]
        w._cycle_terms(2)
        self.assertEqual((w.peak, w.standby), (1500.0, 500.0))
        self.assertAlmostEqual(w.margin, 0.0, places=10)
        self.assertAlmostEqual(w.Q, 1500.0, places=6)
        self.assertAlmostEqual(w.R_hat, alternative, places=12)
        self.assertAlmostEqual(w.c, c, places=15)
        u = close(0.0, "U")
        u.window = [u.window[-1]] * 2
        u._cycle_terms(2)
        self.assertEqual(u.need, 1000.0)
        self.assertEqual(u.c, 0.0)

    def test_the_capital_target_is_the_term_need_plus_the_peak_bridging_need(self):
        """The capital target is the term need plus the peak bridging need.

        Example: over a two-month cycle whose term lending need is $300 and $500 a month, whose
        largest day carried $800 of bridging and which refused $50 and $30 of bridging, the peak bridging need is
        $800 + $80 = $880 and the capital target $400 + $880 = $1,280, where U's target is the mean lending need,
        (300 + 400 + 500 + 400) / 2 = $800. Standby is the cash held ready up to the peak beyond the bridging carried,
        at most the cash itself; with no margin to pay for it the other margin F is below zero, so N* is the target
        itself, its floor."""
        def limit(arm):
            w = controlled_world(arm)
            w.launched = True
            carried = np.full(DAYS, 400.0)
            carried[7] = 800.0
            cycle = [entry(need=700.0, need_term=300.0, bridging=carried, refused_bridging=50.0,
                           ready=np.full(DAYS, 300.0)),
                     entry(need=900.0, need_term=500.0, bridging=np.full(DAYS, 400.0), refused_bridging=30.0,
                           ready=np.full(DAYS, 600.0))]
            w.window = cycle
            w._cycle_terms(2)
            return w
        w = limit("M1")
        self.assertEqual(w.peak, 880.0)
        self.assertAlmostEqual(w.need, 1280.0, places=12)
        self.assertAlmostEqual(w.Q, 1280.0, places=12)
        standby = (29 * 300.0 + 80.0 + 30 * 480.0) / DAYS / 2           # a month, over the cycle
        self.assertAlmostEqual(w.standby, standby, places=12)
        u = limit("U")
        self.assertEqual((u.peak, u.need), (880.0, 800.0))

    def test_the_term_need_adds_the_growth_of_the_pool_term_book(self):
        """The term need adds the growth of the pool's term book, so the term part of the capital target funds next
        month's lending.

        Example, as arithmetic on one closed month's ``window`` entry. The pool's term book was $400 at the last
        close; in the month $40 of new term loans was asked and $20 repaid, the pool lent $30 and refused $10, so
        the book ends at $410. The carried term principal-time is set at $400, as if the month's lending and
        repayments all came on its last day. Without the growth the term need would be carried plus refused, $400 +
        $10 = $410, and next month only the $10 cushion and $20 repaid could be lent again, $30. With the book's
        growth, $410 - $400 = $10, added, the term need is $420, the cushion $20 and all $40 can be lent. U's
        lending need, the pool's principal-time plus refused lending, takes the same $10. A book that shrinks adds
        nothing (the growth is floored at zero), and the launch month's entry, with no earlier close, adds none."""
        def close(arm="M1", before=400.0, book=410.0):
            w = controlled_world(arm, cost=0.0)
            funded_pool(w, 100.0)
            w.capital, w.owners_held = 100.0, w.shares * w.nav_ps
            w.term_book = before
            w._add_loans(np.array([0, 1]), True, TERM, np.array([book / 2, book / 2]), 0.005, 0.005, BIG,
                         np.array([12, 12]), 0)
            w.acc.update(pool_pt=400.0, refused=10.0, refused_bridging=0.0, refused_term=10.0,
                         exposure=np.array([0.0, 400.0]))
            w._close(1, w.net_wealth(), np.ones(10), np.ones(10))
            return w
        w = close()
        self.assertAlmostEqual(w.window[-1]["need_term"], 420.0, places=9)
        self.assertAlmostEqual(w.window[-1]["need"], 420.0, places=9)
        self.assertAlmostEqual(w.term_book, 410.0, places=9)
        self.assertAlmostEqual(close("U").window[-1]["need"], 420.0, places=9)
        self.assertAlmostEqual(close(book=390.0).window[-1]["need_term"], 410.0, places=9)   # shrank: no growth
        self.assertAlmostEqual(close(before=None).window[-1]["need_term"], 410.0, places=9)  # launch month: none

    def test_each_window_entry_adds_the_floored_growth_of_the_pool_term_book(self):
        """On a tiny run whose pool forms (the test device), each month's ``window`` entry holds the term need as the
        month's carried term principal-time plus the term lending refused plus the growth of the pool's carried term
        principal over the month, floored at zero, and zero growth in the launch month's entry.
        The growth is read in the month's own units: the book at its close before CPI less the book at the last close
        after CPI, and in M1 CPI deflates pool loans by 1 / (1 + inflation), so the book before CPI is the book after
        it times 1 + inflation; with no inflation the two are the same. U's lending need takes the same growth. The
        bridging part, the peak bridging need, is read as before (``_kept_ready``)."""
        def rows(arm, inflation):
            records = []

            class Recording(PooledWorld):
                def _close(self, month, *args, **kwargs):
                    acc = self.acc
                    carried, refused = float(acc["exposure"][1]), float(acc["refused_term"])
                    lent, refused_all = float(acc["pool_pt"]), float(acc["refused"])
                    super()._close(month, *args, **kwargs)
                    if self.launched:
                        bk = self.book
                        book = float(bk["principal"][bk["pool"] & bk["carried"] & (bk["kind"] == TERM)].sum())
                        self.test_case.assertAlmostEqual(self.term_book, book, places=12)
                        entry = self.window[-1]
                        records.append((carried, refused, lent, refused_all, book, entry["need_term"], entry["need"]))

            Recording.test_case = self
            economy = replace(TINY, n=120, months=8, inflation=inflation)
            Recording(Inputs(), 0.6, economy, arm).run()
            self.assertEqual(len(records), economy.months)
            return records

        for arm, inflation in (("M1", 0.0), ("M1", TINY.inflation), ("U", TINY.inflation)):
            records = rows(arm, inflation)
            books = [row[4] for row in records]
            self.assertGreater(max(books), 0.0)
            growth = [0.0] + [max(b * (1 + inflation) - a, 0.0) for a, b in zip(books, books[1:])]
            self.assertTrue(any(g > 0 for g in growth[1:]))
            for (carried, refused, lent, refused_all, _, need_term, need), grown in zip(records, growth):
                self.assertAlmostEqual(need_term, carried + refused + grown, places=9)
                self.assertAlmostEqual(need, lent + refused_all + grown, places=9)

    def test_the_fixed_cost_is_sourced_and_the_runners_read_its_level(self):
        """The pool's fixed cost is sourced, and the runners read its level.

        Aave's 2025 paid service providers, $24.15m, over 134.556m consumer units (the 2023 survey's count, the year
        of the model's dollar unit) is 24.15 / 134.556 = $0.1795 a consumer unit a year; Compound's $13.1m gives
        $0.0974 and Sky's $67m $0.4979. In model units, a person a month of a month's mean spending ($6,440), the
        central level is 0.17948 / 12 / 6,440 = 2.3225e-6; a level of 5e-5 would be $3.864 a consumer unit a year,
        21.5 times it. Every runner's inputs carry the central level, a cell reads the level asked for, the
        population runner takes --fixed-cost low, central or high (central by default) and --m0-rates observed or
        fitted, and its run record names the level."""
        from scripts.run_economy_figures import (ENGINE_INPUTS, FIXED_COST, FIXED_COST_UNITS, FIXED_COST_USD,
                                                 engine_inputs)
        from scripts.run_economy_population import cell_inputs, options, run_record
        self.assertEqual((FIXED_COST_USD, FIXED_COST_UNITS), (dict(low=13.1e6, central=24.15e6, high=67.0e6), 134.556e6))
        yearly = {level: value * MONTH_USD * 12 for level, value in FIXED_COST.items()}
        self.assertAlmostEqual(yearly["central"], 0.17948, places=4)
        self.assertAlmostEqual(yearly["low"], 0.09736, places=4)
        self.assertAlmostEqual(yearly["high"], 0.49793, places=4)
        self.assertAlmostEqual(FIXED_COST["central"], 24.15e6 / 134.556e6 / 12 / 6440.0, places=18)
        self.assertAlmostEqual(FIXED_COST["central"], 2.3225e-6, places=9)
        self.assertAlmostEqual(5e-5 * MONTH_USD * 12, 3.864, places=12)
        self.assertAlmostEqual(5e-5 / FIXED_COST["central"], 21.5, places=1)
        self.assertEqual(engine_inputs().C_fix, FIXED_COST["central"])
        self.assertEqual(engine_inputs("low").C_fix, FIXED_COST["low"])
        self.assertEqual(engine_inputs(C_fix=0.0).C_fix, 0.0)
        self.assertEqual(cell_inputs(0.044, "high").C_fix, FIXED_COST["high"])
        self.assertEqual(cell_inputs(0.044).C_fix, FIXED_COST["central"])
        self.assertIn("C_fix", ENGINE_INPUTS)
        parsed = options().parse_args(["--seeds", "development"])
        self.assertEqual((parsed.fixed_cost, parsed.m0_rates), ("central", "observed"))
        parsed = options().parse_args(["--seeds", "development", "--fixed-cost", "low", "--m0-rates", "fitted"])
        self.assertEqual((parsed.fixed_cost, parsed.m0_rates), ("low", "fitted"))
        meta = run_record(Economy(n=40, m0_rates="fitted"), "development", 0, fixed_cost="high")
        self.assertEqual((meta["fixed_cost"], meta["inputs"]["C_fix"], meta["economy"]["m0_rates"]),
                         ("high", FIXED_COST["high"], "fitted"))


def loss_world(arm="M1"):
    """A controlled world under the loan-loss bound, at month 5, with no job without a wage in
    any earlier month, so the normal rates apply, and the month's loss records emptied."""
    w = controlled_world(arm)
    w.economy = replace(w.economy, loan_losses="sourced")
    w.series["laid_off"] = [0.0] * 5
    w.acc.update(written_off=0.0, lost=np.zeros(2), vintage_income=np.zeros((2, LOAN_YEARS)),
                 vintage_exposure=np.zeros((2, LOAN_YEARS)))
    return w


def carried_all_month(w):
    """Stand in for the month's days in a loan-loss example: the book as it is was carried all month, so each
    class's average principal over the month (``_loss_base``, the bound's base) is its principal now."""
    w.acc["loss_base"] = w._loss_base()[1]


def without_wage(w):
    """Lay off job 0 for good, so its earner, returned, is without a wage at every close."""
    w.spell_start[0], w.spell_end[0] = 0, BIG
    return int(w.pop["wage_to"][0])


class LoanLossTests(unittest.TestCase):
    """Loan losses at sourced rates, the bound reading: the rates, who bears them and how each lender books
    them."""

    def test_rates_move_from_normal_to_peak_with_jobs_without_a_wage_three_months_earlier(self):
        """J of 0.0232 or less gives the normal rates (3.402, 0.829 and 0.3315% a year), 0.0768 the peaks (10.54, 3.36
        and 2.57%), halfway the midpoints; month m reads J of month m - 3, and months 0 to 2 month 0's. The anchors are
        U-2 in payroll-job units: September 2009's 6.5% of the labor force times 153,827 / 130,246 thousand is 7.68%
        of payroll jobs.

        Example: at the month-35 stock of 7.983% (x = 5.663 / 5.36 = 1.0565) the card class's rate is 3.402 + 7.138
        x 1.0565 = 10.94%, where anchors per labor-force member would give 12.96%."""
        from cpm_abm.economy_abm import (CHARGE_OFF_NORMAL, CHARGE_OFF_PEAK, JOB_LOSER_NORMAL, JOB_LOSER_PEAK,
                                         charge_off_rates)
        self.assertEqual((JOB_LOSER_NORMAL, JOB_LOSER_PEAK), (0.0232, 0.0768))
        self.assertAlmostEqual(6.5 * 153827 / 130246, 7.68, places=2)
        np.testing.assert_allclose(CHARGE_OFF_NORMAL, [0.03402, 0.00829, 0.003315], rtol=1e-15)
        np.testing.assert_allclose(CHARGE_OFF_PEAK, [0.1054, 0.0336, 0.0257], rtol=1e-15)
        np.testing.assert_allclose(charge_off_rates(0.0232), CHARGE_OFF_NORMAL, rtol=1e-12)
        np.testing.assert_allclose(charge_off_rates(0.01), CHARGE_OFF_NORMAL, rtol=1e-15)
        np.testing.assert_allclose(charge_off_rates(0.0768), CHARGE_OFF_PEAK, rtol=1e-12)
        np.testing.assert_allclose(charge_off_rates((0.0232 + 0.0768) / 2), (CHARGE_OFF_NORMAL + CHARGE_OFF_PEAK) / 2,
                                   rtol=1e-12)
        self.assertAlmostEqual(float(charge_off_rates(0.07983)[0]), 0.03402 + 0.07138 * (0.07983 - 0.0232) / 0.0536,
                               places=15)
        self.assertAlmostEqual(float(charge_off_rates(0.07983)[0]), 0.1094, places=4)
        w = loss_world()
        w.series["laid_off"] = [0.01, 0.02, 0.03, 0.065, 0.05, 0.04]
        w.acc["laid_off"] = 0.07
        self.assertEqual([w._lagged_jobs_without_wage(m) for m in (6, 5, 4, 3, 2, 1)],
                         [0.065, 0.03, 0.02, 0.01, 0.01, 0.01])
        self.assertEqual(w._lagged_jobs_without_wage(0), 0.07)   # month 0's own, the earliest

    def test_a_pool_bridge_book_loses_the_card_rate_first_from_borrowers_without_a_wage(self):
        """A pool bridge book loses the card rate first, from borrowers without a wage.

        Example: a pool bridge book of 1,200 carried all month, 100 owed by a borrower without a wage and 1,100
        by one with a wage, at the normal card rate: 1,200 x 3.402% / 12 = 3.402 is discharged, all from the first,
        whose debt falls by it; the pool's assets (NAV) fall by it, it is written off, the loan-year record holds it
        and no outside flow or valuation moves. The coupon carries the same rate, so it is no loss the learned rate
        reads. With 2 owed by the first and 1,198 by the other: 2 from the first and 1.402 from the other. The base
        is the month's average principal, not the book at the close: the same book carried half the month (an average
        of 600) discharges 1.701."""
        for first, expected, share in ((100.0, (3.402, 0.0), 1.0), (2.0, (2.0, 1.402), 1.0),
                                       (100.0, (1.701, 0.0), 0.5)):
            w = loss_world()
            funded_pool(w, 10.0)
            jobless = without_wage(w)
            pair = np.array([jobless, 1 if jobless != 1 else 3])
            w._add_loans(pair, True, BRIDGE, np.array([first, 1200.0 - first]), 0.01, 0.02, BIG)
            carried_all_month(w)
            w.acc["loss_base"] = w.acc["loss_base"] * share
            np.testing.assert_allclose(w.acc["loss_base"], [[0.0, 1200.0 * share], [0.0, 0.0], [0.0, 0.0]], rtol=1e-15)
            assets, wealth = w._assets(), w.net_wealth()
            w._loan_losses(5)
            change = w.net_wealth() - wealth
            total = 3.402 * share
            np.testing.assert_allclose(change[pair], expected, atol=1e-12)
            self.assertAlmostEqual(assets - w._assets(), total, places=12)
            self.assertAlmostEqual(w.acc["written_off"], total, places=12)
            np.testing.assert_array_equal(w.acc["lost"], [0.0, 0.0])
            np.testing.assert_allclose(w.acc["discharged"], [total, 0.0, 0.0, 0.0, 0.0], atol=1e-12)
            self.assertAlmostEqual(float(w.acc["vintage_income"].sum()), -total, places=12)
            self.assertEqual((w.external, w.valuation), (0.0, 0.0))

    def test_the_pool_prices_the_sourced_rate_of_each_class(self):
        """The pool prices what the bound makes it lose.

        Example, with no job without a wage in any earlier month: the bridging coupon is owners' alternative, o and
        3.402% / 12, the consumer term coupon carries 0.829% / 12 and the business one 0.3315% / 12, and a learned loss
        of the engine's own write-offs (0.01 over 10 of lagged term exposure) is added to both term coupons. With 7.68%
        of jobs without a wage three months earlier (the peak in payroll-job units) each carries its peak rate (10.54,
        3.36 and 2.57%). A business request at an outside rate between the two term coupons is cheaper at the pool and a
        consumer one is not, and each loan is sealed at its own class's coupon. Without the bound nothing is priced and
        the business coupon is r_term."""
        w = loss_world()
        w.launched = True
        w._cycle_terms(5)
        base = w.rho_p + w.economy.owner_spread + w.inputs.o
        np.testing.assert_allclose(w._priced_loss(5), np.array([0.03402, 0.00829, 0.003315]) / 12, rtol=1e-15)
        np.testing.assert_allclose(w._priced_loss(0), np.array([0.03402, 0.00829, 0.003315]) / 12, rtol=1e-15)
        self.assertAlmostEqual(w.r_g, base + 0.03402 / 12, places=15)
        self.assertAlmostEqual(w.r_term, base + 0.00829 / 12, places=15)
        self.assertAlmostEqual(w.r_term_business, base + 0.003315 / 12, places=15)
        w.loss_net, w.exposure = np.array([0.0, 0.01]), np.array([[0.0, 10.0]] + [[0.0, 0.0]] * 3)
        w._cycle_terms(5)
        self.assertAlmostEqual(w.r_g, base + 0.03402 / 12, places=15)
        self.assertAlmostEqual(w.r_term, base + 0.001 + 0.00829 / 12, places=15)
        self.assertAlmostEqual(w.r_term_business, base + 0.001 + 0.003315 / 12, places=15)
        between = np.full(2, (w.r_term + w.r_term_business) / 2)
        business = np.array([False, True])
        np.testing.assert_array_equal(w._term_cheaper(between, business), [False, True])
        np.testing.assert_array_equal(w._term_coupon(business), [w.r_term, w.r_term_business])
        w.series["laid_off"] = [0.0, 0.0, 0.0768, 0.0, 0.0]
        w.loss_net[:] = 0.0
        w._cycle_terms(5)
        np.testing.assert_allclose([w.r_g - base, w.r_term - base, w.r_term_business - base],
                                   np.array([0.1054, 0.0336, 0.0257]) / 12, rtol=1e-12)
        plain = controlled_world()
        plain.launched = True
        plain._cycle_terms(5)
        np.testing.assert_array_equal(plain._priced_loss(5), np.zeros(3))
        self.assertEqual((plain.r_g, plain.r_term, plain.r_term_business), (base, base, base))

    def test_an_outside_term_loan_is_the_outside_lenders_loss(self):
        """An outside term loan is the outside lender's loss.

        Example: an outside business instalment loan of 1,000 and an outside personal one of 1,000, both
        borrowers with a wage, at the normal rates: 1,000 x 0.3315% / 12 and 1,000 x 0.829% / 12 discharged; each
        borrower's net wealth rises by its amount, an outside flow, so the conservation identity holds, and a pool
        written-off loan or fee debt loses nothing."""
        w = loss_world("S0")
        w._add_loans(np.array([3]), False, TERM, np.array([1000.0]), 0.074 / 12, 0.074 / 12, BIG, np.array([11]), 0,
                     business=True)
        w._add_loans(np.array([4]), False, TERM, np.array([1000.0]), 0.15 / 12, 0.15 / 12, BIG, np.array([24]), 0)
        w._add_loans(np.array([5]), False, FEE_DEBT, np.array([1.0]), 0.0, 0.0, BIG)
        w._add_loans(np.array([6]), True, BRIDGE, np.array([5.0]), 0.01, 0.02, BIG)
        w.book["carried"][3] = False                                    # the pool's written-off loan
        carried_all_month(w)
        wealth = w.net_wealth()
        w._loan_losses(5)
        change = w.net_wealth() - wealth
        business, consumer = 1000.0 * 0.003315 / 12, 1000.0 * 0.00829 / 12
        np.testing.assert_allclose(change, [0, 0, 0, business, consumer, 0, 0, 0, 0, 0], atol=1e-13)
        self.assertAlmostEqual(w.external, business + consumer, places=13)
        self.assertAlmostEqual(float(change.sum()), w.external + w.valuation, places=13)
        np.testing.assert_allclose(w.acc["discharged"], [0.0, 0.0, 0.0, consumer, business], atol=1e-13)
        self.assertEqual(w.acc["written_off"], 0.0)

    def test_comet_loans_lose_nothing_and_card_bridges_lose_the_card_rate(self):
        """In M0 an outside bridge from Comet (sealed at Comet's rate, secured by collateral) is untouched, while a
        card bridge beside it loses 3.402% / 12 of its principal."""
        w = loss_world("M0")
        self.assertNotEqual(w.comet_borrow, w.card_apr[3])
        w._add_loans(np.array([3]), False, BRIDGE, np.array([2.0]), w.comet_borrow, w.card_apr[3], BIG)
        w._add_loans(np.array([4]), False, BRIDGE, np.array([2.0]), w.card_apr[4], w.card_apr[4], BIG)
        carried_all_month(w)
        w._loan_losses(5)
        np.testing.assert_allclose(w.book["principal"], [2.0, 2.0 * (1 - 0.03402 / 12)], rtol=1e-15)
        self.assertAlmostEqual(w.external, 2.0 * 0.03402 / 12, places=15)

    def test_forced_runs_keep_wealth_exact_and_the_pool_loses_the_card_rate_on_its_average_bridges(self):
        """Short forced runs under the bound in S0, M0 (with collateral lending, so Comet's loans are present) and M1
        complete with the conservation identity exact. With normal job loss cut to 0.2% a month, so jobs without a
        wage stay below 2.32% in every month, M1's pool discharges each month exactly 3.402% / 12 of the bridging
        principal it carried on average over the month's days, its bridge principal-time, so 3.402% a year of it over
        the run (on the month-end book, as first built, it was 4.19%: that book exceeds the month's average). The
        bridging coupon carries the same 3.402% / 12 in every month."""
        for arm in ("S0", "M0", "M1"):
            series = ForcedRun(Inputs(), 0.6, replace(FORCED, loan_losses="sourced", crypto_share=0.1), arm).run()[
                "series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            self.assertGreater(float(series["discharged_outside_consumer"].sum()), 0.0)

        class Watched(ForcedRun):
            """The forced run, keeping the pool bridging principal each close discharges from: the month's average
            and the book at the close, and the loss the month's bridging coupon carries."""
            def __init__(self, *args):
                self.average, self.at_close, self.priced = [], [], []
                super().__init__(*args)

            def _loan_losses(self, month):
                bk = self.book
                self.average.append(float(self.acc["loss_base"][0, 1]))
                self.at_close.append(float(bk["principal"][bk["pool"] & bk["carried"] & (bk["kind"] == BRIDGE)].sum()))
                self.priced.append(float(self._priced_loss(month)[0]))
                super()._loan_losses(month)

        economy = replace(FORCED, loan_losses="sourced", job_loss=0.002)
        world = Watched(Inputs(), 0.6, economy, "M1")
        series = world.run()["series"]
        self.assertLess(float(series["laid_off"].max()), 0.0232)
        discharged = series["discharged_pool_bridge"] * economy.n
        self.assertGreater(float(discharged.sum()), 0.0)
        average, at_close = np.array(world.average), np.array(world.at_close)
        want = 0.03402 / 12 * average
        # At most all of the book at the close: in a month where the forced exits stop the pool's lending the book is
        # empty, and what it cannot absorb is carried to the next month's amount. At most one such month is read
        # here, a property of the forced run's path; the carry has its own example.
        self.assertLessEqual(int((want > at_close).sum()), 1)
        carry, expect = 0.0, []
        for owed, book in zip(want, at_close):
            expect.append(min(owed + carry, book))
            carry = owed + carry - expect[-1]
        np.testing.assert_allclose(discharged, expect, rtol=1e-12, atol=1e-15)
        np.testing.assert_allclose(average, series["P_bar"] * economy.n, rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(world.priced, 0.03402 / 12, rtol=1e-15)
        after = slice(economy.burn_in, None)
        yearly = 12 * series["discharged_pool_bridge"][after].sum() / series["P_bar"][after].sum()
        self.assertAlmostEqual(float(yearly), 0.034, places=3)
        self.assertGreater(float(at_close[after].sum() / average[after].sum()), 1.1)
        self.assertTrue(bool((series["r_term_business"] < series["r_term"]).all()))

    def test_an_amount_the_book_cannot_absorb_is_carried_to_the_next_month(self):
        """An amount the book cannot absorb is carried to the next month.

        Example: a pool bridge base of 1,200 (the month's average) with no pool bridge
        on the book at the close discharges nothing and carries 1,200 x 3.402% / 12 = 3.402. The next month a pool
        bridge book of 1,200 carried all month owes 3.402 + 3.402 = 6.804, all discharged, and nothing is carried. The
        carried total is recorded at the close. With the bound off nothing is discharged or carried."""
        w = loss_world()
        w.acc["loss_base"] = np.zeros((3, 2))
        w.acc["loss_base"][0, 1] = 1200.0
        w._loan_losses(5)
        np.testing.assert_allclose(w.acc["discharged"], np.zeros(5), atol=0.0)
        self.assertAlmostEqual(float(w.loss_carried[0, 1]), 3.402, places=12)
        self.assertEqual(float(w.loss_carried.sum() - w.loss_carried[0, 1]), 0.0)
        funded_pool(w, 2000.0)
        w._add_loans(np.array([1]), True, BRIDGE, np.array([1200.0]), 0.0, 0.0, BIG)
        carried_all_month(w)
        w._loan_losses(6)
        self.assertAlmostEqual(float(w.acc["discharged"][0]), 6.804, places=12)
        self.assertAlmostEqual(float(w.book["principal"][0]), 1200.0 - 6.804, places=12)
        self.assertEqual(float(w.loss_carried.sum()), 0.0)
        plain = controlled_world()
        plain.acc["loss_base"] = np.zeros((3, 2))
        plain.acc["loss_base"][0, 1] = 1200.0
        plain._loan_losses(5)
        self.assertNotIn("discharged", plain.acc)
        self.assertEqual(float(plain.loss_carried.sum()), 0.0)

    def test_without_the_bound_a_run_is_as_built(self):
        """Without the bound a run is the default run.

        With "none" (the default) nothing is discharged and no loss series is kept: a run equals the default's bit
        for bit, and the runner stores no discharge measure; under "sourced" it stores each."""
        from cpm_abm.economy_abm import LOAN_LOSS_SERIES
        from scripts.run_economy_population import measures, options, same
        self.assertEqual(Economy().loan_losses, "none")
        with self.assertRaises(ValueError):
            Economy(loan_losses="bound")
        economy = replace(TINY, months=3)
        default, none = (simulate(Inputs(), 0.6, w, "M1") for w in (economy, replace(economy, loan_losses="none")))
        self.assertTrue(same(default["series"], none["series"]) and same(default["wealth"], none["wealth"]))
        self.assertFalse(set(LOAN_LOSS_SERIES) & set(default["series"]))
        self.assertFalse(set(LOAN_LOSS_SERIES) & set(measures(default, economy)))
        sourced = replace(economy, loan_losses="sourced")
        stored = measures(simulate(Inputs(), 0.6, sourced, "M1"), sourced)
        self.assertTrue(set(LOAN_LOSS_SERIES) <= set(stored))
        self.assertEqual(len(stored["discharged_outside_consumer"]), economy.months)
        self.assertEqual(len(stored["loss_carried"]), economy.months)
        self.assertNotIn("loss_carried", default["series"])
        self.assertEqual(options().parse_args(["--seeds", "development"]).loan_losses, "none")
        self.assertEqual(options().parse_args(["--seeds", "development", "--loan-losses", "sourced"]).loan_losses,
                         "sourced")


class LendersInterestTests(unittest.TestCase):
    """Outside lenders' interest returned to households over the whole grid."""

    def test_a_map_with_lenders_interest_returned_runs_every_job_with_it(self):
        """With "returned" every task of the grid carries the convention and no extra baseline set is added; a tiny map
        of two jobs is decided, stored and read for its figures as a normal map, its cells under the convention, no
        separate baseline, and the economy record and provenance saying so; with "leaves" (the default) the full grid
        adds the baseline set and the record is the default's."""
        from scripts.run_economy_population import (GRID, decide_cells, job, options, run_record, selected, tasks_for,
                                                    write_stores)
        from scripts.run_region_figures import baseline_jobs
        self.assertEqual(options().parse_args(["--seeds", "development"]).lenders_interest, "leaves")
        self.assertEqual(options().parse_args(["--seeds", "development", "--lenders-interest", "returned"])
                         .lenders_interest, "returned")
        cross = len(GRID["r_out"]) * len(GRID["a0"]) * len(GRID["distress"])
        leaves, returned = tasks_for((1,), 40), tasks_for((1,), 40, returned=True)
        self.assertEqual((len(leaves), sum(task[-1] for task in leaves)), (cross + 1, 1))
        self.assertEqual((len(returned), sum(task[-1] for task in returned)), (cross, cross))
        w = replace(MAP_ECONOMY, lender_income_recirculated=True)
        selection = selected((0.044,), (0.6,), (0.0, 0.02))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            jobs = [job((0.044, 0.6, level, 20261021, 40, True), MAP_ECONOMY) for level in (0.0, 0.02)]
            cells, baseline = decide_cells(jobs, selection, w, 40)
        self.assertIsNone(baseline)
        self.assertEqual([(c["distress"], c["recirculated"], "M1" in c) for c in cells],
                         [(0.0, True, True), (0.02, True, True)])
        self.assertIn("region", cells[0]["M1"])
        meta = run_record(w, "development", 10, selection)
        self.assertEqual((meta["economy"]["lender_income_recirculated"], meta["provenance"]["lenders_interest"]),
                         (True, "returned"))
        plain = run_record(MAP_ECONOMY, "development", 10, selection)
        self.assertIsNone(plain["economy"]["lender_income_recirculated"])
        self.assertNotIn("lenders_interest", plain["provenance"])
        with tempfile.TemporaryDirectory() as folder:
            write_stores(Path(folder), meta, jobs, cells, baseline)
            measures = json.loads((Path(folder) / "measures.json").read_text(encoding="utf-8"))
            summary = json.loads((Path(folder) / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual([j["distress"] for j in baseline_jobs(measures, 0.0)], [0.0])
        self.assertIsNone(summary["baseline_lender_interest_recirculated"])
        self.assertEqual(len(summary["cells"]), 2)


def usd(dollars):
    """Dollars in the model's money (months of mean spending)."""
    return np.asarray(dollars, float) / MONTH_USD


def holder_world(arm="S0", line=1e6, start=0.0):
    """The controlled world with person 0 a card holder on a line of ``line`` dollars, ``start`` of it used."""
    w = controlled_world(arm)
    w.holder[0] = w.pop["holder"][0] = True
    w.card_line[0], w.card_start[0] = usd(line), usd(start)
    return w


def bills(w, amounts, card=False, at=30):
    """Payments of ``amounts`` dollars from person 0 to persons 1, 2, ..., settling on day ``at``."""
    k = len(amounts)
    w.ob = dict(buyer=np.zeros(k, int), seller=np.arange(1, k + 1), amount=usd(amounts), settle=np.full(k, at),
                card=np.full(k, card), kind=np.full(k, SERVICE))
    w.receivable[1:k + 1] = w.ob["amount"]
    w.payable[0] = w.ob["amount"].sum()


def open_ended(base):
    """Comparison device without card limits: ``base`` with every holder's line open-ended, no starting balance,
    and the card priced without limits, a holder's other payments bridged on the card at its purchase APR with no
    fee, dated at their covering date, and no minimum payment; the line's own rules are left in place."""
    class OpenEnded(base):
        def __init__(self, *args):
            super().__init__(*args)
            self.card_line, self.card_start = np.where(self.holder, 1e12, 0.0), np.zeros(self.n)
            self.cash_apr, self.advance_floor, self.advance_rate = self.card_apr.copy(), 0.0, 0.0

        def _minimum_due(self, statement):
            return np.zeros(self.n)

        def _book_advances(self, cash, t):
            took = cash > EPS
            who = np.flatnonzero(took)
            self._add_loans(who, False, BRIDGE, cash[took], self.card_apr[took], self.card_apr[took],
                            self._due_c1(who, cash[took], t, self.card_apr[took]))
    return OpenEnded


def pooled_device(base):
    """``PooledWorld``'s comparison on any engine's world: savers compare the pool with their own mixed return."""
    class Pooled(base):
        def _cycle_terms(self, month):
            base._cycle_terms(self, month)
            self.pool_alternative = self.r_out.copy()
    return Pooled


class CardLimitTests(unittest.TestCase):
    """Card limits, the outside-card contract."""

    def test_card_lines_follow_the_score_tiers_on_a_stream_of_their_own(self):
        """Each holder's line is its CFPB tier's 2023 line per cardholder (Fig 89), $5,696 for deep subprime (579 or
        below) to $41,654 for superprime (800 and above); nobody else has one. Its starting balance is 90 to 100% of the
        line with its tier's chance, else a band below 90% times the tier's revolving share.

        Example of the draw: a deep subprime holder drawing 0.5 (below 68.41%) and 0.3 within starts at 93% of $5,696; a
        superprime holder drawing 0.5 (above 5.2%), a band draw of 0.7 (the 20 to 60% band, past 52/82) and 0.5 within
        uses 40% of $41,654 times 19.64%, $3,272.34. On 4,000 people the shares at 90% or more follow the tiers and come
        to about 18% of holders, the mean line is near the CFPB's $26,218, and the draw is the same whoever holds a
        card."""
        self.assertEqual(card_tier(np.array([579.9, 580.0, 619.9, 620.0, 719.9, 720.0, 799.9, 800.0])).tolist(),
                         [0, 1, 1, 2, 3, 4, 4, 5])
        np.testing.assert_allclose(CARD_LINE * MONTH_USD, [5696, 8121, 12524, 22068, 29335, 41654], rtol=1e-12)

        class Draws:
            """A stream that returns the given draws."""
            def __init__(self, draws):
                self.draws = np.asarray(draws, float)

            def random(self, shape):
                return self.draws.reshape(shape)
        line, start = card_lines(np.array([True, True, False]), np.array([500.0, 820.0, 820.0]),
                                 Draws([[0.5, 0.5, 0.5], [0.0, 0.7, 0.7], [0.3, 0.5, 0.5]]))
        np.testing.assert_allclose(line * MONTH_USD, [5696.0, 41654.0, 0.0], rtol=1e-12)
        np.testing.assert_allclose(start * MONTH_USD, [0.93 * 5696.0, 0.4 * 41654.0 * 0.1964, 0.0], rtol=1e-12)
        self.assertAlmostEqual(float(start[1]) * MONTH_USD, 3272.34, places=2)
        pop = build_population(Economy(n=4000))
        holder, tier = pop["holder"], card_tier(pop["score"])
        np.testing.assert_array_equal(pop["card_line"][~holder], 0.0)
        np.testing.assert_array_equal(pop["card_start"][~holder], 0.0)
        np.testing.assert_allclose(pop["card_line"][holder], CARD_LINE[tier[holder]], rtol=1e-15)
        self.assertTrue(np.all(pop["card_start"] <= pop["card_line"]) and np.all(pop["card_start"] >= 0.0))
        maxed = pop["card_start"] >= 0.9 * pop["card_line"] - 1e-15
        for k in range(6):
            group = holder & (tier == k)
            spread = 3 * (CARD_MAXED[k] * (1 - CARD_MAXED[k]) / group.sum()) ** 0.5   # three binomial deviations
            self.assertAlmostEqual(float(maxed[group].mean()), CARD_MAXED[k], delta=spread, msg=k)
        self.assertAlmostEqual(float(maxed[holder].mean()), 0.18, delta=0.025)
        self.assertAlmostEqual(float(pop["card_line"][holder].mean()) * MONTH_USD, 26218.0, delta=0.05 * 26218.0)
        # Below 90% a holder uses at most 90% of its line times its tier's revolving share.
        np.testing.assert_array_less(pop["card_start"][holder & ~maxed],
                                     0.9 * CARD_LINE[tier[holder & ~maxed]] * CARD_REVOLVING[tier[holder & ~maxed]]
                                     + 1e-15)
        everyone = card_lines(np.ones(4000, bool), pop["score"], np.random.default_rng(
            np.random.SeedSequence([Economy().seed, 3106])))[1]
        np.testing.assert_array_equal(everyone[holder], pop["card_start"][holder])

    def test_card_purchases_stop_at_the_line_and_the_rest_goes_the_cash_route(self):
        """Card purchases stop at the line and the rest goes the cash route.

        Example ($): a holder with a $1,000 line and a $950 starting balance has $50 of room. Of card purchases of
        $30 and $40, smallest first, the $30 goes on the card and the $40, which the room cannot take whole, is paid by
        debit from its $100 of cash, with no merchant fee and no rewards on it. With the whole line used and no money,
        a $40 card purchase is declined without a fee: it is lost, counted as a declined purchase, and nothing is
        borrowed."""
        w = holder_world(line=1000.0, start=950.0)
        w.cash[0] = usd(100.0)
        w.acc["card_spilled"] = 0.0
        bills(w, [30.0, 40.0], card=True)
        w._settle(1, 30)
        self.assertAlmostEqual(float(w.card_unbilled[0]) * MONTH_USD, 30.0, places=9)
        self.assertAlmostEqual(float(w.cash[0]) * MONTH_USD, 60.0, places=9)
        np.testing.assert_allclose(w.cash[1:3] * MONTH_USD, [30.0 * (1 - Inputs().f_card), 40.0], rtol=1e-12)
        self.assertAlmostEqual(w.external * MONTH_USD, -30.0 * Inputs().f_card, places=9)
        self.assertAlmostEqual(float(w.acc["rewards"][0]) * MONTH_USD, 30.0 * CARD_REWARDS, places=9)
        self.assertAlmostEqual(w.acc["card_spilled"] * MONTH_USD, 40.0, places=9)
        self.assertEqual(int(w.book["borrower"].size), 0)
        w = holder_world(line=1000.0, start=1000.0)
        list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS + ("bought_lost",)))
        bills(w, [40.0], card=True)
        w._settle(1, 30)
        self.assertEqual((float(w.card_unbilled[0]), float(w.cash[1]), w.external), (0.0, 0.0, 0.0))
        self.assertEqual(int(w.book["borrower"].size), 0)                     # no fee debt, no advance
        self.assertAlmostEqual(float(w.acc["declined_shares"][0]), 1.0, places=12)
        self.assertAlmostEqual(float(w.acc["bought_lost"][0]) * MONTH_USD, 40.0, places=9)

    def test_a_holders_bill_is_a_cash_advance_up_to_its_cash_line_with_its_fee(self):
        """A holder's bill is a cash advance up to its cash line, with its fee.

        Example ($): a holder with a $1,000 line, nothing owed and no money owes a $300 bill. Its cash line is 20%
        of the line, $200, so $200 is advanced at the cash APR, 30% a year moved with r_out as the purchase APRs are,
        and a fee of the greater of $10 and 5%, $10, goes on the card's purchase balance at its purchase APR; the other
        $100 fails, a third of the bill, with $9 of failure fee. The advance and its fee are rows of their own, the fee
        leaves the economy, and a day's interest on the advance is $200 times the cash APR over 30. A $100 bill is
        advanced in full with the $10 floor (5% would be $5). With $10 of room nothing can be advanced, since the floor
        alone takes the room, and the bill fails with its $27."""
        def settle(bill, start=0.0):
            w = holder_world(line=1000.0, start=start)
            w.acc["advance_fees"] = w.acc["card_bridging"] = 0.0
            bills(w, [bill])
            w._settle(1, 30)
            kinds = {kind: float(w.book["principal"][w.book["kind"] == kind].sum()) * MONTH_USD
                     for kind in (CASH_ADVANCE, REVOLVE, FEE_DEBT)}
            return w, kinds
        w, kinds = settle(300.0)
        shift = 12 * Inputs().rho_H - BILL_MONTHLY
        self.assertAlmostEqual(float(w.cash_apr[0]) * 12, CASH_ADVANCE_APR + shift, places=15)
        np.testing.assert_allclose([kinds[CASH_ADVANCE], kinds[REVOLVE], kinds[FEE_DEBT]], [200.0, 10.0, 9.0],
                                   rtol=1e-12)
        advance = w.book["kind"] == CASH_ADVANCE
        self.assertEqual((float(w.book["rate"][advance][0]), int(w.book["due"][advance][0])), (w.cash_apr[0], BIG))
        self.assertEqual(float(w.book["rate"][w.book["kind"] == REVOLVE][0]), w.card_apr[0])
        self.assertAlmostEqual(float(w.cash[1]) * MONTH_USD, 200.0, places=9)
        self.assertAlmostEqual(w.external * MONTH_USD, -19.0, places=9)
        self.assertAlmostEqual(w.acc["advance_fees"] * MONTH_USD, 10.0, places=9)
        self.assertAlmostEqual(w.acc["card_bridging"] * MONTH_USD, 200.0, places=9)
        w._accrue()
        self.assertAlmostEqual(float(w.book["interest"][advance][0]) * MONTH_USD, 200.0 * w.cash_apr[0] / DAYS,
                               places=12)
        _, kinds = settle(100.0)
        np.testing.assert_allclose([kinds[CASH_ADVANCE], kinds[REVOLVE], kinds[FEE_DEBT]], [100.0, 10.0, 0.0],
                                   rtol=1e-12, atol=1e-12)
        _, kinds = settle(100.0, start=990.0)
        np.testing.assert_allclose([kinds[CASH_ADVANCE], kinds[REVOLVE], kinds[FEE_DEBT]], [0.0, 0.0, 27.0],
                                   rtol=1e-12, atol=1e-12)

    def test_a_maxed_holder_reaches_earned_wage_access(self):
        """Earned-wage access is open to holders, after their cash line: the earned-wage example's person 1, $330 earned
        and unpaid, made a holder with its whole line used, advances its $100 bill as a payer without a card does, and
        nothing fails."""
        w = EconomyAbmTests.wage_case()
        w.holder[1], w.card_line[1], w.card_start[1] = True, usd(1000.0), usd(1000.0)
        w._settle(1, 40)
        self.assertAlmostEqual(float(w.acc["ewa_value"][1]) * MONTH_USD, 100.0, places=9)
        self.assertEqual(float(w.acc["fail_shares"][1]), 0.0)
        self.assertFalse(bool((w.book["kind"] == CASH_ADVANCE).any()))

    def test_the_pools_limit_for_a_holder_reads_the_room_on_its_cash_line(self):
        """The pool's limit for a holder reads the room on its cash line.

        Examples of the partial limit (``limit_with_card``), receipts' spare S. Three pieces: a $300 shortfall, a
        $100 cash room at no cost beyond the unit, the pool at no cost beyond the unit, and a failure fee of $27 a bill
        on one $300 bill (9 cents a dollar, at most $27): D(0) = 100 + 18 = 118, rising at 0.91 a dollar the pool lends
        until nothing fails at $200, D = 300, then flat. S = 250 lends (250 - 118) / 0.91 = $145.05; S = 100 nothing;
        S = 300 all of it. Four pieces, with the fee's floor: a $500 shortfall, a $300 room at 10% to the date and the
        fee the greater of $10 and 5%, 10 cents a dollar of failure fee capped at $3: D(0) = 348, rising at 1 until the
        fee is at its cap at $170 (518), at 0.9 until nothing fails at $200 (545), then falling at 0.15 while the fee is
        5% and at 0.1 once it is the $10 floor. S = 400 lends $52, S = 530 $183.33, S = 545 all of it. With a room
        that takes the whole shortfall and no fee it is the holder's test without card limits: all of it where S repays
        it at card terms, else nothing. In a settlement the first example's numbers give the pool $145.05, the cash
        line $100, and the rest, $54.95, fails with its fee."""
        one = lambda x: np.array([float(x)])
        three = lambda spare: float(limit_with_card(one(300), one(spare), one(1.0), one(0.09), one(27.0), one(100),
                                                    one(1.0), 0.0, 0.0, one(1.0), one(0.0), 1.0245)[0])
        self.assertAlmostEqual(three(250.0), 132.0 / 0.91, places=9)
        self.assertEqual((three(100.0), three(300.0)), (0.0, 300.0))
        four = lambda spare: float(limit_with_card(one(500), one(spare), one(1.0), one(0.1), one(3.0), one(300),
                                                   one(1.1), 10.0, 0.05, one(1.0), one(0.0), 1.0245)[0])
        self.assertAlmostEqual(four(400.0), 52.0, places=9)
        self.assertAlmostEqual(four(530.0), 170.0 + 12.0 / 0.9, places=9)
        self.assertEqual((four(545.0), four(300.0)), (500.0, 0.0))
        before = lambda spare: float(limit_with_card(one(300), one(spare), one(1.0), one(0.09), one(27.0), one(1e9),
                                                     one(1.05), 0.0, 0.0, one(1.05), one(0.0), 1.0245)[0])
        self.assertEqual((before(315.0), before(314.9)), (300.0, 0.0))
        w = holder_world("M1", line=500.0)
        w.part[0] = True
        funded_pool(w)
        w.r_g = w.r_b = 0.0
        w.card_apr[:] = w.cash_apr[:] = 0.0
        w.advance_floor = w.advance_rate = 0.0   # no cost but the unit, as in the example
        w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
        w.last["receipts"][:], w.last["wages_paid"][:] = usd(125.0), 0.0
        bills(w, [300.0])
        w._settle(1, 30)
        kind = w.book["kind"]
        self.assertAlmostEqual(float(w.book["principal"][w.book["pool"]].sum()) * MONTH_USD, 132.0 / 0.91, places=6)
        self.assertAlmostEqual(float(w.book["principal"][kind == CASH_ADVANCE].sum()) * MONTH_USD, 100.0, places=6)
        self.assertAlmostEqual(float(w.book["principal"][kind == FEE_DEBT].sum()) * MONTH_USD,
                               27.0 * (200.0 - 132.0 / 0.91) / 300.0, places=6)

    def test_the_pools_statement_limit_counts_the_late_fee(self):
        """The pool's statement limit counts the late fee.

        Examples of the statement's limit (``limit_with_revolve``): a $100 unpaid statement revolving at 5% to the
        date, a pool at no cost beyond the unit, and own money leaving $40 of the minimum unmet, so a $30 late fee
        unless the pool pays it: D(0) = 105 + 30 = 135 and falling, so S = 135 pays all of it and S = 134 nothing. A
        pool dearer than the card, 10% to the date, rises at 5 cents a dollar: S = 136 pays $20 and S = 140 all of it.
        With no fee it is the test without card limits, all of it where the receipts repay it at card terms."""
        one = lambda x: np.array([float(x)])
        limit = lambda spare, pool=1.0, fee=30.0: float(limit_with_revolve(one(100), one(spare), one(pool), one(1.05),
                                                                           one(40), one(fee))[0])
        self.assertEqual((limit(135.0), limit(134.0)), (100.0, 0.0))
        self.assertAlmostEqual(limit(136.0, pool=1.1), 20.0, places=9)
        self.assertEqual(limit(140.0, pool=1.1), 100.0)
        self.assertEqual((limit(105.0, fee=0.0), limit(104.9, fee=0.0)), (100.0, 0.0))

    def test_the_pool_is_dearer_only_than_a_cash_advance_on_the_part_the_room_could_take(self):
        """The pool is dearer than a cash advance only on the part the room could take.

        Examples of the loan-cost comparison, APRs zero: a $100 draw due 25 days on costs 1 + 25/30 r_b
        a unit at the pool against a cash advance's 1 + its fee per unit, the greater of $10 and 5% over what the room
        takes. With $100 of cash room the advance costs 1.10, so a pool at 20% a month (1.167) is dearer and one at 0.5%
        is not; with $40 of room the fee is 25 cents a unit of it, 1.25, so the pool at 20% is not dearer; with no room
        and no earned-wage access the alternative is failure and the pool is never dearer."""
        def dearer(room, r_b):
            w = holder_world("M1")
            w.card_apr[:] = w.cash_apr[:] = 0.0
            w.r_b = r_b
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:], w.last["wages_paid"][:] = 1.0, 0.0
            draw = np.zeros(10)
            draw[0] = usd(100.0)
            return bool(w._dearer(draw, 35, np.zeros(10), None, np.r_[usd(room), np.zeros(9)])[0])
        self.assertEqual((dearer(100.0, 0.2), dearer(100.0, 0.005)), (True, False))
        self.assertEqual((dearer(40.0, 0.2), dearer(0.0, 0.2)), (False, False))

    def test_the_buffer_replay_prices_a_cash_advance_up_to_the_room_and_failure_beyond(self):
        """The buffer replay prices a cash advance up to the room and failure beyond it.

        Example: half a unit short from day 10 to day 20, no buffer, the cash line at 3% a month
        with a fee of the greater of 0.001 and 5% a new advance, failure at 0.3 a unit. With 0.3 of room: interest on
        0.3 for 10 days, 0.003, the fee on 0.3, 0.015, and 0.2 failing, 0.06, so 0.078. With a room of 1: interest on
        0.5, 0.005, and the fee 0.025, so 0.03. With no room the whole half unit fails, 0.15. With a fee rate of 0.1%
        the floor of 0.01 is the fee."""
        flows = np.zeros((1, DAYS))
        flows[0, 10], flows[0, 20] = -0.5, 0.5
        one = lambda x: np.full(1, x)
        cost = lambda room, floor=0.001, rate=0.05: float(replay_cost(
            flows, np.zeros((1, 1)), one(0.03), one(0.0), one(0.3), card_room=np.full((1, DAYS), room),
            card_rate=one(0.03), card_floor=one(floor), card_fee=one(rate))[0, 0])
        self.assertAlmostEqual(cost(0.3), 0.003 + 0.015 + 0.06, places=15)
        self.assertAlmostEqual(cost(1.0), 0.005 + 0.025, places=15)
        self.assertAlmostEqual(cost(0.0), 0.15, places=15)
        self.assertAlmostEqual(cost(1.0, floor=0.01, rate=0.001), 0.005 + 0.01, places=15)

    def test_the_minimum_payment_and_a_late_fee_never_above_it(self):
        """The minimum payment and a late fee never above it.

        Example ($, day 20 of month 1). A $20 statement and no money: the minimum is the whole $20, unpaid, so a
        late fee of $30 capped at the minimum, $20, goes on the card, $20 is past due and the card is delinquent from
        today, which puts its holder in arrears tomorrow. A $5,000 balance of $4,910 and $90 of interest charged in the
        cycle owes 1% plus the interest, $140; $100 of money below a $1,000 buffer is collected on the card (the
        interest first), $40 is past due and the fee is $30, or $41 for a repeat within six cycles of the last late
        fee. With $200 the whole $140 is collected from money below the buffer, nothing is late and a card delinquent
        before is current again."""
        t = DAYS + 20
        w = holder_world()
        w.card_statement[0] = usd(20.0)
        w._statement(20, t)
        revolving = w.book["kind"] == REVOLVE
        np.testing.assert_allclose(np.sort(w.book["principal"][revolving]) * MONTH_USD, [20.0, 20.0], rtol=1e-12)
        self.assertAlmostEqual(w.external * MONTH_USD, -20.0, places=9)
        self.assertAlmostEqual(w.acc["late_fees"] * MONTH_USD, 20.0, places=9)
        self.assertAlmostEqual(float(w.card_past_due[0]) * MONTH_USD, 20.0, places=9)
        self.assertEqual((int(w.card_late_since[0]), int(w.card_late_month[0])), (t, 1))
        w._arrears(t + 1)
        self.assertTrue(bool(w.arrears[0]))

        def balance(money, repeat=False, late_since=BIG):
            w = holder_world()
            w.cash[0], w.buffer[0] = usd(money), usd(1000.0)
            w._add_loans(np.array([0]), False, REVOLVE, usd([4910.0]), w.card_apr[0], w.card_apr[0], BIG)
            w.book["interest"][0] = w.card_interest[0] = usd(90.0)
            w.card_late_month[0] = 0 if repeat else -BIG
            w.card_late_since[0] = late_since
            self.assertAlmostEqual(float(w._minimum_due(np.zeros(10))[0]) * MONTH_USD, 140.0, places=9)
            w._statement(20, t)
            return w, float(w.book["principal"][w.book["kind"] == REVOLVE].sum()) * MONTH_USD
        w, owed = balance(100.0)
        self.assertAlmostEqual(owed, 4900.0 + 30.0, places=9)
        self.assertEqual((float(w.book["interest"][0]), float(w.cash[0])), (0.0, 0.0))
        self.assertAlmostEqual(float(w.card_past_due[0]) * MONTH_USD, 40.0, places=9)
        self.assertAlmostEqual(w.acc["late_fees"] * MONTH_USD, 30.0, places=9)
        w, owed = balance(100.0, repeat=True)
        self.assertAlmostEqual(w.acc["late_fees"] * MONTH_USD, 41.0, places=9)
        self.assertAlmostEqual(LATE_FEE_REPEAT * MONTH_USD, 41.0, places=12)
        w, owed = balance(200.0, late_since=t - DAYS)
        self.assertAlmostEqual(owed, 4860.0, places=9)
        self.assertAlmostEqual(float(w.cash[0]) * MONTH_USD, 60.0, places=9)
        self.assertEqual((w.acc["late_fees"], float(w.card_past_due[0]), int(w.card_late_since[0])), (0.0, 0.0, BIG))
        self.assertAlmostEqual(LATE_FEE * MONTH_USD, 30.0, places=12)

    def test_payments_on_the_card_since_the_statement_count_towards_the_minimum(self):
        """Payments on the card since the statement count towards the minimum.

        Example ($): a holder with no buffer owes $3,000 revolving, repays $1,500 of it
        on day 5 of the cycle from a wage, and holds $10 on day 20, when an $1,800 statement falls due. The minimum on
        the $3,300 balance is the $40 floor, and the $1,500 already paid meets it, so no late fee is charged, nothing
        is past due and the card stays current; the cycle's payments then start again from zero. Without the earlier
        payment the balance is $4,800, its minimum $48, and the $10 leaves $38 unmet: a $30 late fee, $38 past due and
        the card delinquent."""
        t = DAYS + 20

        def cycle(repaid, minimum):
            w = holder_world()
            w._add_loans(np.array([0]), False, REVOLVE, usd([3000.0]), w.card_apr[0], w.card_apr[0], BIG)
            if repaid:
                w.cash[0] = usd(repaid)
                w._repay(np.maximum(w.cash + w.pcash, 0.0))
            self.assertAlmostEqual(float(w.card_paid[0]) * MONTH_USD, repaid, places=9)
            w.cash[0], w.card_statement[0] = usd(10.0), usd(1800.0)
            self.assertAlmostEqual(float(w._minimum_due(w.card_statement)[0]) * MONTH_USD, minimum, places=9)
            w._statement(20, t)
            return w
        w = cycle(1500.0, 40.0)
        self.assertEqual((w.acc["late_fees"], float(w.card_past_due[0]), int(w.card_late_since[0])), (0.0, 0.0, BIG))
        self.assertEqual(float(w.card_paid[0]), 0.0)
        w._arrears(t + 1)
        self.assertFalse(bool(w.arrears[0]))
        w = cycle(0.0, 48.0)
        self.assertAlmostEqual(w.acc["late_fees"] * MONTH_USD, 30.0, places=9)
        self.assertAlmostEqual(float(w.card_past_due[0]) * MONTH_USD, 38.0, places=9)
        self.assertEqual(int(w.card_late_since[0]), t)

    def test_the_pool_paying_a_statement_spares_the_late_fee(self):
        """The pool paying a statement spares the late fee.

        Example ($, M1): a member with no money owes a $100 statement, so its own
        payment leaves the whole $40 minimum unmet. With receipts that repay it and a pool with cash the pool pays all
        $100: the minimum is met, so no late fee, nothing past due, the card current, and the draw is card credit
        whole in the real part. With no pool cash the statement revolves, the $30 late fee goes on the card and the
        card is delinquent."""
        t = DAYS + 20

        def statement(capital):
            w = holder_world("M1", line=500.0)
            w.part[0] = True
            funded_pool(w, capital)
            w._day_cache = {}   # the conversion rate read afresh for today's participants
            w.r_g = w.r_b = 0.0
            w.card_apr[:] = w.cash_apr[:] = 0.0
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:], w.last["wages_paid"][:] = usd(500.0), 0.0
            w.card_statement[0] = usd(100.0)
            w._statement(20, t)
            return w
        w = statement(10.0)
        pool = w.book["pool"]
        self.assertAlmostEqual(float(w.book["principal"][pool].sum()) * MONTH_USD, 100.0, places=9)
        self.assertEqual(float(w.book["card_part"][pool][0]), 1.0)
        self.assertEqual((w.acc["late_fees"], float(w.card_past_due[0]), int(w.card_late_since[0])), (0.0, 0.0, BIG))
        w = statement(0.0)
        self.assertFalse(bool(w.book["pool"].any()))
        self.assertAlmostEqual(w.acc["late_fees"] * MONTH_USD, 30.0, places=9)
        self.assertAlmostEqual(float(w.card_past_due[0]) * MONTH_USD, 40.0, places=9)
        self.assertEqual(int(w.card_late_since[0]), t)

    def test_a_holders_pool_rescue_is_what_its_cash_line_could_not_have_taken(self):
        """A holder's pool rescue is what its cash line could not have taken.

        Example ($, M1), from the partial limit's settlement: a $300 bill, $100 of
        cash room and a pool draw of $145.05 rationed by the receipts leave $54.95 failing, where without the draw $200
        would have failed, so the draw paid $145.05 in place of failing, 0.4835 of the bill, and none of it replaced
        card credit. With receipts that repay the whole $300 the pool pays all of it: $200 in place of failing and $100
        that the cash line would have taken, which the real part counts as card credit, a third of the draw. A payer
        without a card's draw is bridged whole."""
        def settle(receipts, holder=True):
            w = holder_world("M1", line=500.0)
            w.holder[0] = w.pop["holder"][0] = holder
            w.part[0] = True
            funded_pool(w)
            w._day_cache = {}   # the conversion rate read afresh for today's participants
            w.r_g = w.r_b = 0.0
            w.card_apr[:] = w.cash_apr[:] = 0.0
            w.advance_floor = w.advance_rate = 0.0
            w.pop["cycles"][:], w.pop["phases"][:] = 30, 0
            w.last["receipts"][:], w.last["wages_paid"][:] = usd(receipts), 0.0
            list(map(lambda key: w.acc[key].__setitem__(slice(None), 0.0), FAILURE_COUNTS))
            bills(w, [300.0])
            w._settle(1, 30)
            pool = w.book["pool"]
            return w, float(w.book["principal"][pool].sum()) * MONTH_USD, w.book["card_part"][pool]
        w, draw, part = settle(125.0)
        self.assertAlmostEqual(draw, 132.0 / 0.91, places=6)
        self.assertAlmostEqual(float(w.acc["bridged_shares"][0]), draw / 300.0, places=12)
        self.assertAlmostEqual(float(w.acc["bridged_shares"][0]), 0.4835, places=4)
        self.assertEqual(float(part[0]), 0.0)
        w, draw, part = settle(400.0)
        self.assertAlmostEqual(draw, 300.0, places=9)
        self.assertAlmostEqual(float(w.acc["bridged_shares"][0]), 200.0 / 300.0, places=12)
        self.assertEqual(float(w.acc["bridged_items"][0]), 1.0)
        self.assertAlmostEqual(float(part[0]), 1.0 / 3.0, places=12)
        w.acc["pt_pool_card"] = w.acc["pt_pool_card_credit"] = w.acc["pt_pool_nocard_card"] = 0.0
        w._accrue()
        self.assertAlmostEqual(w.acc["pt_pool_card"] * MONTH_USD, 300.0 / DAYS, places=9)
        self.assertAlmostEqual(w.acc["pt_pool_card_credit"] * MONTH_USD, 100.0 / DAYS, places=9)
        self.assertEqual(w.acc["pt_pool_nocard_card"], 0.0)
        w, draw, part = settle(400.0, holder=False)
        self.assertAlmostEqual(float(w.acc["bridged_shares"][0]), draw / 300.0, places=12)
        self.assertEqual(float(part[0]), 0.0)

    def test_the_replays_card_room_counts_only_the_months_advances_still_owed(self):
        """The replay's card room counts only the month's advances still owed.

        Example ($): a $1,000 line has a $200 cash line. A $200 bill with no money on
        day 3 is advanced whole, so day 4 records the cash room left, nothing, plus the month's advance still owed,
        $200. Once the advance and its fee are repaid on day 10, day 11 records the cash line, $200, not the $400 that
        counting every advance the month made would give, and no day records more than the cash line. An advance made
        in an earlier month is not added back."""
        w = holder_world(line=1000.0)
        bills(w, [200.0], at=33)
        w._settle(1, 33)
        self.assertAlmostEqual(float(w.book["principal"][w.book["kind"] == CASH_ADVANCE].sum()) * MONTH_USD, 200.0,
                               places=9)
        self.assertEqual(int(w.book["m0"][w.book["kind"] == CASH_ADVANCE][0]), 1)
        bills(w, [0.0], at=34)
        w._settle(1, 34)
        self.assertAlmostEqual(float(w.acc["card_room"][0, 4]) * MONTH_USD, 200.0, places=9)
        w.cash[0] = usd(300.0)
        w._repay(np.maximum(w.cash + w.pcash, 0.0))
        self.assertLess(float(w._card_owed(w._card_rows())[0]), EPS)
        bills(w, [0.0], at=41)
        w._settle(1, 41)
        self.assertAlmostEqual(float(w.acc["card_room"][0, 11]) * MONTH_USD, 200.0, places=9)
        self.assertTrue(np.all(w.acc["card_room"][:, [3, 4, 11]] <= CASH_LINE_SHARE * w.card_line[:, None] + EPS))
        later = holder_world(line=1000.0)
        later._add_loans(np.array([0]), False, CASH_ADVANCE, usd([200.0]), later.cash_apr[0], later.cash_apr[0], BIG,
                         m0=0)
        bills(later, [0.0], at=34)
        later._settle(1, 34)
        self.assertEqual(float(later.acc["card_room"][0, 4]), 0.0)

    def test_the_s0_counterfactual_takes_a_p_purchase_on_the_card_only_within_the_room(self):
        """The S0 counterfactual takes a P purchase on the card only within the room.

        Example ($, M1): a member holding a card pays a $1,000 card-eligible purchase in
        P to another member. With $300 of room on its line S0 would have paid it by debit, so the seller saved no
        merchant fee and the buyer had no float; with $2,000 of room S0 would have put it on the card, so the seller
        saved its 1.7% and the buyer floated the $1,000."""
        def settle(room):
            w = holder_world("M1", line=1000.0 + room, start=1000.0)
            funded_pool(w)
            w._day_cache = {}   # the conversion rate read afresh for today's participants
            w.pcash[0] = usd(1100.0)
            w.acc["merchant_saved"][:], w.acc["p_value"] = 0.0, 0.0
            bills(w, [1000.0], card=True)
            w._settle(1, 30)
            self.assertAlmostEqual(float(w.acc["p_value"]) * MONTH_USD, 1000.0, places=6)
            return float(w.acc["merchant_saved"][1]) * MONTH_USD, float(w.today["card_internal"][0]) * MONTH_USD
        self.assertEqual(settle(300.0), (0.0, 0.0))
        saved, floated = settle(2000.0)
        self.assertAlmostEqual(saved, 1000.0 * Inputs().f_card, places=9)
        self.assertAlmostEqual(floated, 1000.0, places=9)

    def test_the_card_fees_follow_outside_lenders_income_and_the_minimums_conversion_is_a_days_fee(self):
        """The card's fees follow outside lenders' income, and the minimum's conversion is a day's fee.

        Under the recirculation stress the card's fees are outside lenders' income that
        returns to households at the close, as its interest does: a $100 bill advanced on a $1,000 line puts its $10
        fee with the lenders and takes nothing from the outside account, and a missed $20 minimum's late fee goes there
        too; without the stress both leave the economy. A minimum collected from P under routine conversion pays its
        conversion fee, which is the day's fee, kept out of the S0 counterfactual's flow."""
        w = holder_world(line=1000.0)
        w.economy = replace(w.economy, lender_income_recirculated=True)
        bills(w, [100.0])
        w._settle(1, 30)
        self.assertAlmostEqual(w.sector["lenders"] * MONTH_USD, 10.0, places=9)
        self.assertEqual(w.external, 0.0)
        w = holder_world()
        w.economy = replace(w.economy, lender_income_recirculated=True)
        w.card_statement[0] = usd(20.0)
        w._statement(20, DAYS + 20)
        self.assertAlmostEqual(w.sector["lenders"] * MONTH_USD, 20.0, places=9)
        self.assertEqual(w.external, 0.0)
        w = holder_world("M1")
        w.part[0] = True
        w.economy = replace(w.economy, routine_conversion=True)
        w._day_cache = {}   # the conversion rate read afresh under routine conversion
        w.acc["conversion"][:] = 0.0
        w._add_loans(np.array([0]), False, REVOLVE, usd([500.0]), w.card_apr[0], w.card_apr[0], BIG)
        w.pcash[0] = usd(100.0)
        w._statement(20, DAYS + 20)
        self.assertAlmostEqual(float(w.book["principal"].sum()) * MONTH_USD, 460.0, places=9)
        self.assertGreater(float(w.acc["conversion"][0]), 0.0)
        np.testing.assert_allclose(w.today["fees"], w.acc["conversion"], rtol=1e-12)

    def test_the_replays_price_the_cash_line_at_its_own_terms_within_the_cash_line(self):
        """The replays price the cash line at its own terms, within the cash line.

        In a run, the dealing's replay and both experience replays read each holder's day
        room on its cash line, zero for anyone without a card and never above 20% of its line, and price what it
        takes at the cash APR and the advance's fee, scaled alike by the share of a shortfall the cash line meets: in
        S0 every holder's whole shortfall; in M1 what the pool did not admit, and in the S0 experience replay the whole
        shortfall."""
        from unittest import mock
        from cpm_abm import economy_abm
        from cpm_abm.engine import world_close, world_dealing   # where _dealing and _close look choose_buffer up

        def calls(world):
            """Each replay's card terms in a run, in the order they ran."""
            world._experience_unread = lambda: False   # an S0 run reads no experience replay and skips them; forced
            with mock.patch.object(world_dealing, "choose_buffer", wraps=economy_abm.choose_buffer) as replay, \
                    mock.patch.object(world_close, "choose_buffer", replay):
                world.run()
            return [{key: call.kwargs[key] for key in ("card_room", "card_rate", "card_floor", "card_fee")}
                    for call in replay.call_args_list]
        economy = replace(TINY, n=40, months=3, burn_in=2)
        for arm, base in (("S0", _World), ("M1", PooledWorld)):
            world = base(Inputs(), 0.6, economy, arm)
            seen = calls(world)
            self.assertGreater(len(seen), 4, arm)
            holder, line = world.pop["holder"], world.pop["card_line"]
            shares = []
            for terms in seen:
                share = terms["card_floor"] / CASH_ADVANCE_FEE_FLOOR
                shares.append(share)
                self.assertTrue(np.all((share >= 0.0) & (share <= holder + 1e-15)), arm)
                np.testing.assert_allclose(terms["card_rate"], share * world.cash_apr, rtol=1e-12, atol=0.0)
                np.testing.assert_allclose(terms["card_fee"], share * CASH_ADVANCE_FEE_RATE, rtol=1e-12, atol=0.0)
                room = terms["card_room"]
                self.assertEqual(room.shape, (economy.n, DAYS))
                np.testing.assert_array_equal(room[~holder], 0.0)
                self.assertTrue(np.all(room <= CASH_LINE_SHARE * line[:, None] + EPS), arm)
            if arm == "S0":
                for share in shares:
                    np.testing.assert_array_equal(share, holder.astype(float))
            else:
                # Some replay prices every holder's whole shortfall (the S0 experience replay).
                self.assertTrue(any(np.array_equal(share, holder.astype(float)) for share in shares))
            self.assertTrue(any(float(terms["card_room"].max()) > 0.0 for terms in seen), arm)

    def test_a_card_180_days_past_due_is_charged_off_and_its_debt_stays_owed(self):
        """A card 180 days past due is charged off and its debt stays owed.

        Example ($): a holder 179 days past due on a $500 revolving balance, a $100 cash advance, a $50 statement
        and $20 of this month's purchases keeps its card; at 180 days the line closes, so it holds no card, every
        balance, $670, stays owed as a charged-off balance at no further interest, net wealth does not move, and it is
        in arrears while it is owed. Its class, the population's card holding, is unchanged; repaid in full, it is out
        of arrears."""
        w = holder_world()
        w.acc["charged_off"] = w.acc["lines_closed"] = 0.0
        w._add_loans(np.array([0]), False, REVOLVE, usd([500.0]), w.card_apr[0], w.card_apr[0], BIG)
        w._add_loans(np.array([0]), False, CASH_ADVANCE, usd([100.0]), w.cash_apr[0], w.cash_apr[0], BIG)
        w.card_statement[0], w.card_unbilled[0] = usd(50.0), usd(20.0)
        t = 300
        w.card_late_since[0] = t - CHARGE_OFF_DAYS + 1
        w._charge_off(t)
        self.assertTrue(bool(w.holder[0]))
        w.card_late_since[0] = t - CHARGE_OFF_DAYS
        wealth = w.net_wealth()
        w._charge_off(t)
        self.assertEqual((bool(w.holder[0]), bool(w.pop["holder"][0]), float(w.card_line[0])), (False, True, 0.0))
        np.testing.assert_array_equal(w.net_wealth(), wealth)
        self.assertTrue(np.all(w.book["kind"] == CHARGED_OFF) and np.all(w.book["rate"] == 0.0))
        self.assertAlmostEqual(float(w.book["principal"].sum()) * MONTH_USD, 670.0, places=9)
        self.assertEqual((float(w.card_statement[0]), float(w.card_unbilled[0])), (0.0, 0.0))
        self.assertAlmostEqual(w.acc["charged_off"] * MONTH_USD, 670.0, places=9)
        self.assertEqual((w.acc["lines_closed"], int(w.card_late_since[0])), (1.0, BIG))
        list(map(lambda _: w._accrue(), range(DAYS)))
        self.assertEqual(float(w.book["interest"].sum()), 0.0)
        w._arrears(t + 1)
        self.assertTrue(bool(w.arrears[0]))
        self.assertEqual(float(w._card_room()[0]), 0.0)
        w.cash[0] = usd(1000.0)
        w._repay(np.maximum(w.cash + w.pcash, 0.0))
        w._arrears(t + 2)
        self.assertFalse(bool(w.arrears[0]))

    def test_a_closed_line_never_changes_a_persons_class(self):
        """A run in which a holder's card is charged off on the launch month's first day: the world holds no card for it
        from then, while the run's population, which fixes each person's class, still holds one, so the runner's
        classes, its card bridging per holder and the buffer means by card holding read the population's holding."""
        from scripts.run_economy_population import by_class, card_bridging

        class ChargedOff(_World):
            """The first holder's minimum read as missed 180 days before the launch month's first day."""
            def day(self, month, d):
                if month == self.economy.burn_in and d == 0:
                    self.card_late_since[self.first] = month * DAYS - CHARGE_OFF_DAYS
                super().day(month, d)
        economy = replace(TINY, months=3)
        world = ChargedOff.__new__(ChargedOff)
        _World.__init__(world, Inputs(), 0.6, economy, "S0")
        world.first = int(np.flatnonzero(world.holder)[0])
        run = world.run()
        people = run["population"]
        self.assertTrue(bool(people["holder"][world.first]) and not world.holder[world.first])
        self.assertEqual(float(run["series"]["lines_closed"].sum()), 1.0)
        kind = 2 * people["holder"].astype(int) + people["business"].astype(int)
        self.assertEqual(by_class(run, economy)["class_sizes"], np.bincount(kind, minlength=4).tolist())
        report = card_bridging(run, economy)
        self.assertAlmostEqual(report["lines_closed_share"], 1.0 / people["holder"].sum(), places=4)
        np.testing.assert_allclose(run["series"]["buffer_card"], run["buffers"][:, people["holder"]].mean(axis=1),
                                   rtol=1e-12)

    def test_the_distress_line_cut_is_a_side_check_off_by_default(self):
        """Lines are held through the distress year unless the side check is on (``card_line_cut``): then at the
        distress year's first month each open line falls by 60% of its tier's 2008-2012 fall times the level over 2%,
        32.58% deep subprime, 16.02% superprime and 19.44% between at 2%, half that at 1%, and nothing in other months
        or at level 0."""
        self.assertFalse(Economy().card_line_cut)
        np.testing.assert_allclose(CARD_CUT, [0.3258, 0.1944, 0.1944, 0.1944, 0.1944, 0.1602], rtol=1e-12)
        for level, on in ((0.02, True), (0.01, True), (0.02, False), (0.0, True)):
            w = _World(Inputs(), 0.6, Economy(n=40, card_line_cut=on, distress=level), "S0")
            before = w.card_line.copy()
            first = w.economy.burn_in + w.economy.distress_start
            w._cut_lines(first - 1)
            np.testing.assert_array_equal(w.card_line, before)
            w._cut_lines(first)
            cut = CARD_CUT[w.card_tier] * level / 0.02 if on else 0.0
            np.testing.assert_allclose(w.card_line, before * (1 - cut), rtol=1e-15)
            self.assertTrue(bool(w.pop["card_line"].any()))
            np.testing.assert_array_equal(w.pop["card_line"], before)

    def test_wealth_stays_exact_in_every_arm_with_lines_that_bind(self):
        """With every line a twentieth of its draw, so lines bind for many holders, a short run in every arm declines
        card purchases at the line, takes cash advances with their fees, charges late fees and keeps the conservation
        identity to 1e-12 every month; the card's fees go to outside lenders in the runner's transfers and gain split,
        which still adds up. One card in each run, the holder with most purchases on it on the tenth day of the month
        after launch, is read as 180 days past due then, so every run charges a card off (payments during the cycle
        count towards the minimum, so no card in so short a run reaches 180 days on its own); and with both bounds on
        the identity holds too."""
        from scripts.run_economy_population import split, transfers

        def tight(base):
            class Tight(base):
                def __init__(self, *args):
                    super().__init__(*args)
                    self.card_line, self.card_start = self.card_line / 20, self.card_start / 20

                def day(self, month, d):
                    if month == self.economy.burn_in + 1 and d == 10:
                        late = int(np.argmax(np.where(self.holder, self.card_unbilled, -1.0)))
                        self.card_late_since[late] = month * DAYS + d - CHARGE_OFF_DAYS
                    super().day(month, d)
            return Tight
        economy = replace(TINY, n=80, months=6, burn_in=3, shocks=True)
        runs = {}
        for arm in ("S0", "M0", "U", "M1", "M2"):
            base = PooledWorld if arm in ("U", "M1", "M2") else _World
            runs[arm] = run = tight(base)(Inputs(), 0.6, economy, arm).run()
            series = run["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            for key in ("advance_fees", "late_fees", "card_spilled", "card_bridging"):
                self.assertGreater(float(series[key].sum()), 0.0, f"{arm} {key}")
            paid = transfers(run, economy)["outside_lenders"]["paid_usd"]
            after = slice(economy.burn_in, None)
            self.assertAlmostEqual(paid, round(float(np.nansum((series["out_interest"] + series["advance_fees"]
                                                                + series["late_fees"])[after])) * MONTH_USD, 2),
                                   places=2)
            # The card read as 180 days past due is charged off, with wealth still exact.
            self.assertGreater(float(series["charged_off"].sum()), 0.0, arm)
        parts = split(runs["M1"], runs["S0"], economy)
        after = slice(economy.burn_in, None)
        whole = float(np.nansum(runs["M1"]["series"]["external"][after] - runs["S0"]["series"]["external"][after]))
        named = sum(value for key, value in parts.items() if key not in ("valuation", "inflation"))
        self.assertAlmostEqual(named, whole * MONTH_USD, places=6)
        # With both bounds on: loan losses at sourced rates, and outside lenders' interest
        # and the card's fees returned to households; the identity still holds with lines that bind.
        bounds = replace(economy, loan_losses="sourced", lender_income_recirculated=True)
        for arm in ("S0", "M1"):
            base = PooledWorld if arm == "M1" else _World
            series = tight(base)(Inputs(), 0.6, bounds, arm).run()["series"]
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            self.assertGreater(float(series["advance_fees"].sum() + series["late_fees"].sum()), 0.0, arm)
            self.assertGreater(float(series["charged_off"].sum()), 0.0, arm)


def sink_world(amount=1000.0, cash=0.0, kind=OUTSIDE_WAGE):
    """The controlled world ($) with job 0, paid by person 0 to person 1 monthly on day 29 (59 in month 1), owing a
    wage row of ``amount`` of ``kind`` on day 30, which a wage sent outside leaves out of the worker's receivable;
    person 0 holds ``cash``. The month's receipts and wages paid are emptied."""
    w = controlled_world("S0")
    w.pop["wage_to"][0], w.pop["pay_days"][0], w.pop["pay_phase"][0] = 1, 30, 29
    w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=usd([amount]), settle=np.array([30]),
                card=np.array([False]), kind=np.array([kind]))
    w.payable[0] = w.ob["amount"][0]
    if kind in (WAGE, LATE_WAGE):
        w.receivable[1] = w.ob["amount"][0]
    w.cash[0] = usd(cash)
    w.acc["receipts"][:], w.acc["wages_paid"][:] = 0.0, 0.0
    return w


class HarshStressTests(unittest.TestCase):
    """The harsh stress: the distress year's extra layoffs send the laid-off wage out of the household economy,
    owed by the payer to the outside on the job's pay dates, the worker receiving nothing; normal job loss keeps
    the payer-keeps rule, so level 0 is unchanged."""

    def test_an_extra_layoff_is_marked_from_the_draw_it_already_had(self):
        """An extra layoff is marked from the draw it already had.

        Example (``draw_spells``): at a rate of 0.03 with a normal rate of 0.01, draws of 0.005, 0.01, 0.02 and
        0.03 lay off the first three, the second and third as extra layoffs, and draw nothing more; without a normal
        rate it returns the three values it did. In a world at 2%, the distress year's first month marks exactly the
        jobs laid off whose uniform lies at or above the normal rate times their weight, on the layoff stream as it
        was; a month outside the year and any month at level 0 mark none, and a mark stays with its job until the job
        is laid off again."""
        class Draws:
            """A stream that returns the given layoff draws, day 0 and the median length."""
            def random(self, size):
                return np.array([0.005, 0.01, 0.02, 0.03])

            def integers(self, low, high, size):
                return np.zeros(size, int)

            def standard_normal(self, size):
                return np.zeros(size)
        rate, normal, every = np.full(4, 0.03), np.full(4, 0.01), np.ones(4, bool)
        laid_off, start, end, extra = draw_spells(Draws(), rate, every, 30, 61.0, 1.0, normal=normal)
        self.assertEqual((laid_off.tolist(), extra.tolist()), ([True, True, True, False], [False, True, True, False]))
        self.assertEqual((start.tolist(), end.tolist()), ([30] * 4, [91] * 4))
        self.assertEqual(len(draw_spells(Draws(), rate, every, 30, 61.0, 1.0)), 3)
        economy = Economy(n=1000, distress=0.02)
        first = economy.burn_in + economy.distress_start
        w = _World(Inputs(), 0.6, economy, "S0")
        eligible = w.spell_end <= first * DAYS
        w._layoffs(first)
        draw = np.random.default_rng(np.random.SeedSequence([economy.seed, 19, first])).random(economy.n)
        laid = eligible & (draw < (economy.job_loss + economy.distress) * w.layoff_rate)
        np.testing.assert_array_equal(w.spell_out, laid & (draw >= economy.job_loss * w.layoff_rate))
        self.assertTrue(bool(w.spell_out.any()) and bool((laid & ~w.spell_out).any()))
        marked = w.spell_out.copy()
        later = first + economy.distress_length
        eligible = w.spell_end <= later * DAYS
        w._layoffs(later)
        draw = np.random.default_rng(np.random.SeedSequence([economy.seed, 19, later])).random(economy.n)
        again = eligible & (draw < economy.job_loss * w.layoff_rate)
        np.testing.assert_array_equal(w.spell_out, marked & ~again)
        plain = _World(Inputs(), 0.6, replace(economy, distress=0.0), "S0")
        plain._layoffs(first)
        self.assertFalse(bool(plain.spell_out.any()))

    def test_the_distress_fork_still_equals_direct_runs(self):
        """The population runner runs each arm once up to the distress year and finishes every level from a copy
        (``forked``): the mark of an extra layoff is made only from the distress year's first month, so a forked run
        at 0 and at 20% equals its direct run bit for bit, in S0 and M1."""
        from scripts.run_economy_population import forked, same
        w = replace(TINY, n=60, months=5, burn_in=2, distress_start=1, distress_length=2)
        for arm in ("S0", "M1"):
            got = forked(Inputs(), 0.05, w, arm, (0.0, 0.2))
            for level in (0.0, 0.2):
                self.assertTrue(same(got[level], simulate(Inputs(), 0.05, replace(w, distress=level), arm)),
                                (arm, level))
            self.assertGreater(float(got[0.2]["series"]["wages_out"].sum()), 0.0)

    def test_an_extra_layoffs_wage_row_is_its_payers_payable_and_the_outside_is_credited_when_it_is_made(self):
        """An extra layoff's wage row is its payer's payable, and the outside is credited when it is made.

        Example (a sink row): job 0, laid off by an extra layoff for the whole month, makes no wage row; it makes
        wage rows sent outside of its whole wage, 58.3% of its payer's spending, from its payer to its worker on its
        own pay dates, in its payer's payable and in nobody's receivable, and the outside account is credited with
        it at once, so households' net wealth falls by it now; no wage is withheld. Job 1, paid monthly on day 29 and
        laid off by an extra layoff from day 15, owes a wage row of its first 15 days and a row sent outside of its
        last 15, both on day 29. Job 2, laid off at the normal rate all month, keeps the payer-keeps rule: no row, its
        wage withheld. The jobs' workers are the month's hit workers. The share of jobs without a wage is unchanged
        by the stress."""
        world = tiny_world()
        world.acc = dict(shocks=0.0, volume=0.0)
        world.spell_start[:], world.spell_end[:] = 0, 0
        world.spell_start[:3], world.spell_end[:3] = (0, 15, 0), (DAYS, BIG, DAYS)
        world.spell_out[:3] = True, True, False
        world.pop["pay_days"][1], world.pop["pay_phase"][1] = 30, 29
        before = float(world.net_wealth().sum())
        world._obligations(0)
        ob, s = world.ob, world.spending
        wage = lambda job, kind: ob["amount"][(ob["buyer"] == job) & (ob["kind"] == kind)]
        self.assertEqual(wage(0, WAGE).size, 0)
        self.assertAlmostEqual(float(wage(0, OUTSIDE_WAGE).sum()), LABOUR_SHARE * float(s[0]), places=14)
        sent = (ob["kind"] == OUTSIDE_WAGE)
        np.testing.assert_array_equal(np.unique(ob["seller"][sent & (ob["buyer"] == 0)]), [world.pop["wage_to"][0]])
        np.testing.assert_allclose([wage(1, WAGE).sum(), wage(1, OUTSIDE_WAGE).sum()], LABOUR_SHARE * s[1] / 2,
                                   rtol=1e-14)
        self.assertEqual((ob["settle"][(ob["buyer"] == 1) & (ob["kind"] != SERVICE)].tolist()), [29, 29])
        self.assertEqual((wage(2, WAGE).size, wage(2, OUTSIDE_WAGE).size), (0, 0))
        self.assertAlmostEqual(world.acc["withheld"], LABOUR_SHARE * float(s[2]), places=14)
        out = LABOUR_SHARE * float(s[0] + s[1] / 2)
        self.assertAlmostEqual(world.acc["wages_out"], out, places=14)
        self.assertAlmostEqual(world.external, -out, places=14)
        for person in range(world.n):
            mine = ob["buyer"] == person
            self.assertAlmostEqual(float(world.payable[person]), float(ob["amount"][mine].sum()), places=12)
            owed_to = (ob["seller"] == person) & ~sent
            self.assertAlmostEqual(float(world.receivable[person]), float(ob["amount"][owed_to].sum()), places=12)
        self.assertAlmostEqual(float(world.net_wealth().sum()) - before, world.external, places=12)
        self.assertAlmostEqual(world.acc["laid_off"], (DAYS + 15 + DAYS) / (TINY.n * DAYS), places=12)
        np.testing.assert_array_equal(np.flatnonzero(world.acc["hit"]), np.unique(world.pop["wage_to"][:3]))

    def test_a_wage_sent_outside_is_paid_by_its_payer_received_by_nobody_and_requeued_while_unpaid(self):
        """A wage sent outside is paid by its payer, received by nobody and requeued while unpaid.

        Example of settlement ($): person 0 owes a $1,000 wage row sent outside on day 30. With $1,500 it pays it:
        its money falls to $500 and its payable to 0, while its worker's money, receipts and the wages paid on the job
        do not move, and no outside flow is booked, since the row's wage left at its making. With $400 it pays $400:
        the other $600 is re-queued as a wage sent outside to the job's next pay date, day 59, still owed, carrying
        0.6 of a failure fee ($16.20), counted in failed shares (0.6) and in a record of its own, never in the failure
        share's failed or due or the wage arrears. On day 59, with no money, it fails again with no second fee or
        count and is re-queued to day 89. Paid later as an overdue wage from $600, it leaves the payer's money, the
        worker receiving nothing and the payable clearing."""
        usd_ = lambda value: round(float(value) * MONTH_USD, 9)
        w = sink_world(cash=1500.0)
        wealth = w.net_wealth()
        w._settle(1, 30)
        self.assertEqual((usd_(w.cash[0]), usd_(w.payable[0]), usd_(w.cash[1]), w.external), (500.0, 0.0, 0.0, 0.0))
        self.assertEqual((float(w.acc["receipts"].sum()), float(w.acc["wages_paid"].sum())), (0.0, 0.0))
        np.testing.assert_allclose(w.net_wealth(), wealth, atol=1e-15)
        self.assertEqual(float(w.receivable.sum()), 0.0)
        w = sink_world(cash=400.0)
        counts = {key: w.acc[key].copy() for key in ("fail_shares", "failed_new")}
        failed, due, arrears = w.acc["failed"], w.acc["due"], w.acc["wage_failed"]
        w._settle(1, 30)
        late = w.ob["kind"] == LATE_OUTSIDE_WAGE
        self.assertEqual((w.ob["settle"][late].tolist(), usd_(w.ob["amount"][late].sum())), ([59], 600.0))
        self.assertEqual((usd_(w.cash[0]), usd_(w.payable[0]), usd_(w.cash[1])), (0.0, 600.0, 0.0))
        fee = w.book["principal"][w.book["kind"] == FEE_DEBT]
        self.assertEqual((usd_(fee.sum()), usd_(-w.external)), (16.2, 16.2))
        self.assertAlmostEqual(float(w.acc["fail_shares"][0] - counts["fail_shares"][0]), 0.6, places=12)
        self.assertAlmostEqual(usd_(w.acc["failed_new"][0] - counts["failed_new"][0]), 600.0, places=6)
        self.assertEqual((w.acc["failed"], w.acc["due"], w.acc["wage_failed"]), (failed, due, arrears))
        self.assertAlmostEqual(usd_(w.acc["wage_out_failed"]), 600.0, places=6)
        self.assertEqual(float(w.receivable.sum()), 0.0)
        shares, out = float(w.acc["fail_shares"][0]), w.acc["wage_out_failed"]
        w._settle(1, 59)
        late = (w.ob["kind"] == LATE_OUTSIDE_WAGE) & (w.ob["amount"] > EPS)   # a settled row leaves at the close
        self.assertEqual((w.ob["settle"][late].tolist(), usd_(w.ob["amount"][late].sum())), ([89], 600.0))
        self.assertEqual((usd_(w.book["principal"][w.book["kind"] == FEE_DEBT].sum()), float(w.acc["fail_shares"][0]),
                          w.acc["wage_out_failed"]), (16.2, shares, out))
        w.cash[0] = usd(600.0)
        w._wage_arrears(np.maximum(w.cash + w.pcash, 0.0))
        self.assertEqual((usd_(w.cash[0]), usd_(w.payable[0]), usd_(w.cash[1]), float(w.ob["amount"].sum())),
                         (0.0, 0.0, 0.0, 0.0))
        self.assertEqual((float(w.acc["receipts"].sum()), float(w.acc["wages_paid"].sum())), (0.0, 0.0))

    def test_the_pools_budget_expects_no_wage_from_a_job_whose_wage_went_outside(self):
        """A $1,000 wage paid on its job's monthly pay date is a wage paid on the job and a receipt of its worker, so
        next month's budget expects $1,000 on each of the job's pay dates and the worker's other receipts exclude it;
        sent outside, it is neither, and nothing is expected from the job."""
        expected = {}
        for kind in (WAGE, OUTSIDE_WAGE):
            w = sink_world(cash=1500.0, kind=kind)
            w._settle(1, 30)
            w.last.update(wages_paid=w.acc["wages_paid"].copy(), receipts=w.acc["receipts"].copy())
            w._day_cache = None
            period, _, per_pay, other = w._receipt_streams()
            expected[kind] = (round(float(per_pay[0]) * MONTH_USD, 9), int(period[0]),
                              round(float(w.acc["receipts"][1]) * MONTH_USD, 9), float(other[1]))
        self.assertEqual(expected, {WAGE: (1000.0, 30, 1000.0, 0.0), OUTSIDE_WAGE: (0.0, 30, 0.0, 0.0)})

    def test_earned_wage_access_has_no_room_on_a_wage_sent_outside_and_it_repays_no_advance(self):
        """Earned-wage access has no room on a wage sent outside, and it repays no advance.

        The earned-wage example's world ($): job 2 back at work after an extra layoff's spell, nothing accrued,
        and $900 of its wage still owed. Owed to its worker (a late wage), it is earned and unpaid, so the $100 bill on
        day 40 is advanced and nothing fails; owed to the outside, the worker earned none of it, so nothing is advanced
        and the bill fails with its $27. With $102.45 owed on advances against job 2, the payer's $900 sent outside,
        on time on day 59 or as an overdue wage, repays none of it and pays the worker nothing."""
        usd_ = lambda value: round(float(value) * MONTH_USD, 9)
        for kind, advanced, fee in ((LATE_WAGE, 100.0, 0.0), (LATE_OUTSIDE_WAGE, 0.0, 27.0)):
            w = EconomyAbmTests.wage_case()
            w.accrued[2] = 0.0
            w.spell_out[2] = True
            w.ob["kind"][1] = kind
            if kind == LATE_OUTSIDE_WAGE:
                w.receivable[1] = 0.0
            w._settle(1, 40)
            self.assertEqual((usd_(w.acc["ewa_value"][1]), usd_(w.acc["fee"][1])), (advanced, fee), kind)
        for kind, collect in ((OUTSIDE_WAGE, lambda w: w._settle(1, 59)),
                              (LATE_OUTSIDE_WAGE, lambda w: w._wage_arrears(np.maximum(w.cash + w.pcash, 0.0)))):
            w = EconomyAbmTests.wage_case()
            w.ob = {key: value[1:] for key, value in w.ob.items()}
            w.ob["kind"][0] = kind
            w.receivable[1] = 0.0
            w.ewa_owed[2] = usd(102.45)
            w.cash[2] = usd(900.0)
            collect(w)
            self.assertEqual((usd_(w.cash[2]), usd_(w.cash[1]), usd_(w.ewa_owed[2]), usd_(w.payable[2])),
                             (0.0, 0.0, 102.45, 0.0), kind)

    def test_a_day_whose_completions_move_by_no_money_is_settled_at_the_sweep_cap(self):
        """A day whose completions move by no money is settled at the sweep cap.

        Under the harsh stress a payer with a tiny remainder due can have its completed share moved by rounding
        forever. At the sweep cap a day is settled where every payer's completion still moves by no more than EPS of
        money. Example, a one-sweep cap and no money anywhere: person 0 owes person 1 1e-13 and person 1 owes person
        2 1e-13; from full completion the second sweep moves person 1's completed share from 1 to 0, 1e-13 of money,
        so the day settles at that sweep's state, both payments failing. With amounts of 1 the same move is a whole
        unit of money and the cap is an error."""
        for amount, settles in ((1e-13, True), (1.0, False)):
            w = controlled_world("S0")
            w.economy = replace(w.economy, sweeps=1)
            w.ob = dict(buyer=np.array([0, 1]), seller=np.array([1, 2]), amount=np.full(2, amount),
                        settle=np.full(2, 30), card=np.zeros(2, bool), kind=np.full(2, SERVICE))
            np.add.at(w.receivable, w.ob["seller"], amount)
            np.add.at(w.payable, w.ob["buyer"], amount)
            if not settles:
                with self.assertRaises(RuntimeError):
                    w._settle(1, 30)
                continue
            w._settle(1, 30)
            self.assertEqual((float(w.cash[1]), float(w.cash[2])), (0.0, 0.0))
            self.assertEqual(float(w.payable[:2].sum()), 0.0)   # a failed purchase is lost, not owed

    def test_wealth_stays_exact_in_every_arm_under_the_harsh_stress_with_both_bounds_on(self):
        """Short runs at distress 20% in every arm, alone and with both bounds on (the loan-loss bound and outside
        lenders' interest returned), keep the conservation identity to 1e-12 every month, with wages sent outside in
        the distress year's months; with every payment between participants in P (routing "all"), M1's reserves still
        equal the P owed, since no wage sent outside is a P payment. Hit workers' failed shares are part of everyone's
        and their failure share is defined while they owe bills."""
        economy = replace(TINY, n=100, burn_in=2, months=6, distress=0.2, distress_start=1, distress_length=3)
        bounds = dict(loan_losses="sourced", lender_income_recirculated=True)
        first = economy.burn_in + economy.distress_start
        for arm in ("S0", "M0", "U", "M1", "M2"):
            world = PooledWorld if arm in ("U", "M1", "M2") else _World
            for setting in (economy, replace(economy, **bounds)):
                series = world(Inputs(), 0.6, setting, arm).run()["series"]
                np.testing.assert_allclose(series["wealth_change"],
                                           series["external"] + series["valuation"] + series["inflation"],
                                           atol=1e-12, err_msg=arm)
                self.assertEqual(float(series["wages_out"][:first].sum()), 0.0)
                self.assertTrue(bool((series["wages_out"][first:first + 3] > 0).all()), arm)
                self.assertTrue(bool((series["fail_shares_hit"] <= series["fail_shares"] + 1e-12).all()), arm)
                self.assertTrue(bool(np.isfinite(series["failure_share_hit"][first:first + 3]).all()), arm)
        series = PooledWorld(Inputs(), 0.6, replace(economy, routing="all"), "M1").run()["series"]
        np.testing.assert_allclose(series["wealth_change"], series["external"] + series["valuation"]
                                   + series["inflation"], atol=1e-12)
        backing = series["backing"][economy.burn_in:]
        self.assertTrue(np.isfinite(backing).any())
        np.testing.assert_allclose(backing[np.isfinite(backing)], 1.0, atol=1e-9)

    def test_the_runner_names_the_wages_sent_outside(self):
        """The gain split names the wages sent outside (``wages_to_outside``), so the other outside flows stay exact:
        an arm that sends $100 more of them outside than S0 in a year, its only outside flow, reads -$100 there and 0
        in the rest. The wage-loss records store them (``wages_out``), every arm's monthly series carry the harsh
        stress's read-outs, an undefined failure share stored as None, and the run record labels the headline level,
        2%, as 2009's wage loss before unemployment insurance."""
        from scripts.run_economy_population import (MONTHLY, STRESS, WAGE_LOSS, measures, monthly, run_record,
                                                    split)
        w = Economy(n=1, burn_in=1, months=12)
        keys = ("out_interest", "penalties", "merchant_fees", "rewards", "conversion_fees", "pool_operating",
                "savings_income", "valuation", "inflation", "external", "gas", "advance_fees", "late_fees", "wages_out")
        arm = EconomyAbmTests.year_of("M1", dict(wages_out=usd(100.0), external=-usd(100.0)), keys)
        parts = split(arm, EconomyAbmTests.year_of("S0", {}, keys), w)
        self.assertAlmostEqual(parts["wages_to_outside"], -100.0, places=9)
        self.assertAlmostEqual(parts["other_outside_flows"], 0.0, places=9)
        self.assertEqual(WAGE_LOSS["wages_out"], "wages_out")
        self.assertTrue(all(set(STRESS) <= set(stored) for stored in MONTHLY.values()))
        series = {key: np.zeros(3) for key in MONTHLY["S0"]}
        series["failure_share_hit"] = np.array([0.0, np.nan, 0.25])
        series.update(failure_share=np.zeros(3), laid_off=np.zeros(3), laid_off_last_day=np.zeros(3),
                      wages_withheld=np.zeros(3), wages_out=np.array([0.0, 0.01, 0.02]))
        run = dict(arm="S0", series=series)
        short = Economy(n=1, burn_in=1, months=2)
        self.assertEqual(monthly(run, short)["failure_share_hit"], [None, 0.25])
        self.assertEqual(measures(run, short)["wages_out"], [0.01, 0.02])
        labels = run_record(Economy(n=40), "development", 0)["distress_labels"]
        self.assertEqual((labels["headline_pct_a_month"], labels["headline_label"]),
                         (2.0, "2009's wage loss before unemployment insurance"))


class EngineSpeedDeviceTests(unittest.TestCase):
    """The engine's speed devices change no value."""

    def assertSameBits(self, mine, theirs, path=""):
        """Every leaf of two records equal bit for bit (arrays by dtype, shape and bytes)."""
        if isinstance(mine, dict):
            self.assertEqual(sorted(mine, key=repr), sorted(theirs, key=repr), path)
            for key in mine:
                self.assertSameBits(mine[key], theirs[key], f"{path}/{key}")
        elif isinstance(mine, (list, tuple)):
            self.assertEqual(len(mine), len(theirs), path)
            for i, (a, b) in enumerate(zip(mine, theirs)):
                self.assertSameBits(a, b, f"{path}[{i}]")
        elif isinstance(mine, np.ndarray) and mine.dtype != object:
            self.assertEqual((mine.dtype, mine.shape), (theirs.dtype, theirs.shape), path)
            self.assertEqual(np.ascontiguousarray(mine).tobytes(), np.ascontiguousarray(theirs).tobytes(), path)
        elif isinstance(mine, np.ndarray):
            self.assertSameBits(list(mine.ravel()), list(theirs.ravel()), path)
        else:
            self.assertEqual(repr(mine), repr(theirs), path)

    def test_a_world_copied_mid_run_finishes_as_an_uncopied_run(self):
        """The loan book keeps spare room behind views (``_World._append_book``) and a day keeps values fixed for it;
        a world deep-copied after the launch month, as the population runner forks its distress levels, finishes
        with every record identical bit for bit to a run never copied, in a pool arm and in S0."""
        import copy
        economy = replace(TINY, n=60, months=4, burn_in=2, shocks=True)
        for arm in ("M1", "S0"):
            whole = simulate(Inputs(), 0.6, economy, arm)
            world = _World(Inputs(), 0.6, economy, arm)
            for month in range(3):
                world.month(month)
            forked = copy.deepcopy(world)
            step = forked.month
            forked.month = lambda month: None if month < 3 else step(month)
            self.assertSameBits(whole, forked.run(), arm)

    def test_skipping_the_unread_experience_replays_changes_no_record(self):
        """The close skips its two experience replays where nothing reads them (``_World._experience_unread``): an S0
        run and a pool arm's burn-in. Forced to run them, every record is identical bit for bit, distress on too."""
        from unittest import mock
        economy = replace(TINY, n=60, months=3, burn_in=2, shocks=True, distress=0.02)
        for arm in ("S0", "M1"):
            skipped = simulate(Inputs(), 0.6, economy, arm)
            with mock.patch.object(_World, "_experience_unread", lambda self: False):
                forced = simulate(Inputs(), 0.6, economy, arm)
            self.assertSameBits(skipped, forced, arm)


class PoolRunRecordTests(unittest.TestCase):
    """Records and read-outs for the pool run under the harsh stress and the cash-advance bound: records only, so
    every other record of the engine is unchanged."""

    def test_the_new_records_add_up(self):
        """On a short run in every arm with lines a twentieth of their draw, so holders take cash advances and pay late
        fees, and distress on: every month the write-offs of bridges and of term loans add up to written_off (to
        rounding), the cash set aside for exits is the cash not owed to creditors less the cash new loans may take at
        the close, and with cash to lend while the pool serves, the two add up to it; the money offered that found no
        room is never above the money offered. Per person and month, the interest on cash advances is never above the
        card's interest, and the cash-advance fees plus the late fees are the card's fees; the cash-advance fees add up
        to the advance_fees series."""
        def tight(base):
            class Tight(base):
                def __init__(self, *args):
                    super().__init__(*args)
                    self.card_line, self.card_start = self.card_line / 20, self.card_start / 20
                    self.set_aside, self.late = [], np.zeros((self.total, self.n))

                def _close(self, month, *args):
                    self.late[month] = self.acc["late_fee_i"]
                    super()._close(month, *args)
                    self.set_aside.append((self._lendable() - self._cash_for_loans(), self._lendable()))
            return Tight
        economy = replace(TINY, n=80, months=8, burn_in=3, shocks=True, distress=0.2, distress_start=1,
                          distress_length=3)
        offered = 0.0
        for arm in ("S0", "M0", "U", "M1", "M2"):
            world = tight(PooledWorld if arm in ("U", "M1", "M2") else _World)(Inputs(), 0.6, economy, arm)
            run = world.run()
            series, credit, n = run["series"], run["credit"], economy.n
            np.testing.assert_allclose(series["written_off_bridge"] + series["written_off_term"],
                                       series["written_off"], rtol=1e-12, atol=1e-15)
            set_aside, lendable = np.array(world.set_aside).T
            np.testing.assert_array_equal(series["exit_set_aside"], set_aside / n)
            self.assertTrue(np.all(series["exit_set_aside"] >= 0.0))
            serves = series["service"] > 0
            np.testing.assert_allclose((series["cash_to_lend"] + series["exit_set_aside"])[serves],
                                       lendable[serves] / n, rtol=1e-12, atol=1e-15)
            self.assertTrue(np.all(series["offers_unused"] <= series["offers"]))
            self.assertTrue(np.all(credit["interest_advance"] <= credit["interest_card"]))
            np.testing.assert_allclose(credit["fees_advance"] + world.late, credit["fees_card"], rtol=1e-12,
                                       atol=1e-15)
            np.testing.assert_allclose(credit["fees_advance"].sum(axis=1), series["advance_fees"] * n, rtol=1e-12,
                                       atol=1e-15)
            self.assertGreater(float(credit["fees_advance"].sum() + credit["interest_advance"].sum()), 0.0, arm)
            offered += float(series["offers"].sum())
        self.assertGreater(offered, 0.0)
        # No pool loan is 90 days past due in so short a run; under the loan-loss bound the pool's principal is
        # discharged every month, by loan kind, and the parts still add up (the term part by hand, below).
        series = PooledWorld(Inputs(), 0.6, replace(economy, loan_losses="sourced"), "M1").run()["series"]
        self.assertGreater(float(series["written_off_bridge"].sum()), 0.0)
        np.testing.assert_allclose(series["written_off_bridge"] + series["written_off_term"], series["written_off"],
                                   rtol=1e-12, atol=1e-15)

    def test_a_write_off_is_split_by_loan_kind(self):
        """A write-off is split by loan kind.

        Example: a $100 pool bridge due on day 10 and a $200 pool term loan past due since day 0 are both written
        down on day 100, 90 days and more past due: $100 of bridges, $200 of term loans, $300 in all."""
        w = controlled_world()
        w.acc.update(written_off=0.0, written_off_bridge=0.0, written_off_term=0.0, lost=np.zeros(2))
        w._add_loans(np.array([0]), True, BRIDGE, np.array([100.0]), 0.0, 0.02, 10, None, 0)
        w._add_loans(np.array([1]), True, TERM, np.array([200.0]), 0.0, 0.02, BIG, np.array([12]), 0)
        rows = w.book["pool"] & (w.book["kind"] == TERM)
        w.book["since"][rows] = 0
        w._write_off(100)
        self.assertEqual((w.acc["written_off_bridge"], w.acc["written_off_term"], w.acc["written_off"]),
                         (100.0, 200.0, 300.0))

    def test_cash_advance_records_on_a_hand_case(self):
        """Cash-advance records on a worked example.

        Example: a holder takes a $100 cash advance at a 5% fee with a $10 floor, so its fee is $10, on the
        purchase balance; a day's accruals add the advance's interest to interest_advance and every card balance's,
        the fee's too, to interest_card. A missed $40 minimum's late fee of $30 goes to fees_card and not to
        fees_advance."""
        self.assertEqual((CASH_ADVANCE_FEE_RATE, CASH_ADVANCE_FEE_FLOOR * MONTH_USD), (0.05, 10.0))
        w = controlled_world()
        holder = 0
        w.holder[holder], w.card_line[holder] = True, usd(10000.0)
        for key in ("credit_fees_card", "credit_fees_advance", "credit_interest_card", "credit_interest_advance"):
            w.acc[key][:] = 0.0
        cash = np.zeros(w.n)
        cash[holder] = usd(100.0)
        w._book_advances(cash, 5)
        self.assertAlmostEqual(w.acc["credit_fees_advance"][holder] * MONTH_USD, 10.0, places=9)
        self.assertAlmostEqual(w.acc["credit_fees_card"][holder] * MONTH_USD, 10.0, places=9)
        bk = w.book
        advance = ~bk["pool"] & (bk["kind"] == CASH_ADVANCE) & (bk["borrower"] == holder)
        fee = ~bk["pool"] & (bk["kind"] == REVOLVE) & (bk["borrower"] == holder)
        w._accrue()
        on_advance = float((bk["principal"] * bk["rate"])[advance].sum()) / DAYS
        on_fee = float((bk["principal"] * bk["rate"])[fee].sum()) / DAYS
        self.assertGreater(on_advance, 0.0)
        self.assertAlmostEqual(w.acc["credit_interest_advance"][holder], on_advance, places=15)
        self.assertGreater(w.acc["credit_interest_card"][holder], w.acc["credit_interest_advance"][holder])
        self.assertAlmostEqual(w.acc["credit_interest_card"][holder] - w.acc["credit_interest_advance"][holder],
                               on_fee, delta=1e-15 + 1e-12 * on_fee)
        minimum = np.zeros(w.n)
        minimum[holder] = usd(40.0)
        w.cash[holder], w.pcash[holder], w.savings[holder] = 0.0, 0.0, 0.0
        w._minimum_paid(minimum, np.zeros(w.n), 20)
        self.assertAlmostEqual(w.acc["credit_fees_card"][holder] * MONTH_USD, 10.0 + LATE_FEE * MONTH_USD, places=9)
        self.assertAlmostEqual(w.acc["credit_fees_advance"][holder] * MONTH_USD, 10.0, places=9)

    def paired(self, credit_arm, credit_other, months=40):
        """Three people over ``months`` after launch (burn-in 1): billing cycles 7, 30 and 7 days, the first two
        holders earning wages (class 2) and the third neither (class 0). The arm ends $100, -$50 and $0 above the
        other ($30, -$15 and $0 a year over 40 months), $12, $0 and $0 above at 36 months; each person's cash-advance
        fees and interest in the first month after launch, $ (fees, interest) by person, in each."""
        from scripts.run_economy_population import differences
        w = Economy(n=3, burn_in=1, months=months)
        cycles, holder, business = np.array([7, 30, 7]), np.array([True, True, False]), np.zeros(3, bool)
        rows = w.burn_in + w.months
        record = lambda values: np.where((np.arange(rows) == 1)[:, None], np.array(values, float) / MONTH_USD, 0.0)
        credit = lambda given: dict(fees_advance=record([f for f, _ in given]),
                                    interest_advance=record([i for _, i in given]))
        wealth = np.zeros((rows + 1, 3))
        wealth[w.burn_in + 36], wealth[-1] = usd([12.0, 0.0, 0.0]), usd([100.0, -50.0, 0.0])
        run = lambda name, given, path: dict(EconomyAbmTests.paired_run(name, w, cycles, holder, business,
                                                                        credit=credit(given)), wealth=path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)                    # a W2 role read on no months
            return differences(run("M1", credit_arm, wealth), run("S0", credit_other, np.zeros((rows + 1, 3))), w)

    def test_the_gain_under_the_cash_advance_bound(self):
        """The gain under the cash-advance bound.

        Example over 40 months (a year is 0.3 of the sums): banks charge person 0 $20 of advance fees and $30 of
        interest and the arm $10 and $10, a saving of $30, $9 a year; banks charge person 1 $10 and the arm $20, a
        saving of -$3 a year; person 2 takes none. The gains, $30, -$15 and $0 a year, are $21, -$12 and $0 under the
        bound: a mean of $5.00 without the bound and $3.00 under it, one person in three worse off in both, by cycle
        (short: persons 0 and 2) $15 and -$15 without it and $10.50 and -$12 under it, by class $0 (class 0) and
        $7.50 (class 2) without it and $0 and $4.50 under it; the saving's mean is $2.00, $0 and $3.00 by class. With no
        purchase records both ends of the complete gain are the wealth gain, under the bound too. An arm that charges
        the same for cash advances has its gain under the bound equal to its gain."""
        got = self.paired([(10.0, 10.0), (20.0, 0.0), (0.0, 0.0)], [(20.0, 30.0), (10.0, 0.0), (0.0, 0.0)])
        bound = got["bound"]
        self.assertEqual((got["gain_usd_a_year"], bound["gain_usd_a_year"]), (5.0, 3.0))
        self.assertEqual((got["worse_off"], bound["worse_off"]), (0.333, 0.333))
        self.assertEqual((got["gain_usd_a_year_by_cycle"], bound["gain_usd_a_year_by_cycle"]),
                         ([15.0, -15.0], [10.5, -12.0]))
        np.testing.assert_equal(got["gain_usd_a_year_by_class"], [0.0, np.nan, 7.5, np.nan])
        np.testing.assert_equal(bound["gain_usd_a_year_by_class"], [0.0, np.nan, 4.5, np.nan])
        self.assertEqual(got["advance_saving_usd_a_year"], 2.0)
        np.testing.assert_equal(got["advance_saving_usd_a_year_by_class"], [0.0, np.nan, 3.0, np.nan])
        self.assertEqual(len(got["advance_saving_usd_a_year_by_quintile"]), 5)
        for end in ("face", "zero"):
            np.testing.assert_equal(got["complete_gain"][end]["bound"], bound)
            self.assertEqual(set(got["complete_gain"][end]["bound"]), set(got["complete_gain"][end]) - {"bound"})
        same = [(20.0, 30.0), (10.0, 0.0), (0.0, 0.0)]
        alike = self.paired(same, same)
        self.assertEqual(alike["advance_saving_usd_a_year"], 0.0)
        np.testing.assert_equal(alike["bound"], {key: alike[key] for key in alike["bound"]})
        for end in ("face", "zero"):
            block = alike["complete_gain"][end]
            np.testing.assert_equal(block["bound"], {key: block[key] for key in block if key != "bound"})

    def test_dispersion_and_the_gain_by_month(self):
        """Dispersion and the gain by month, in the same example: the gains $30, -$15 and $0 a year have one person in
        three below -$2 and, by linear interpolation over -15, 0 and 30, the 5th percentile -13.5, the 25th -7.5, the
        median 0, the 75th 15 and the 95th 27, the same at both ends of the complete gain. At 36 months the mean gain of
        $4 is $1.33 a year, and at the end (40 months) $16.67, $5.00 a year; month 48 is past the run's end and left
        out. Over 48 months the end is month 48 itself, $16.67 over 4 years, $4.17 a year."""
        got = self.paired([(0.0, 0.0)] * 3, [(0.0, 0.0)] * 3)
        expected = dict(below_margin_share=0.3333,
                        percentiles_usd_a_year={"5": -13.5, "25": -7.5, "50": 0.0, "75": 15.0, "95": 27.0})
        self.assertEqual(got["dispersion"], dict(wealth=expected, face=expected, zero=expected))
        self.assertEqual(got["gain_usd_a_year_at_month"], {"36": 1.33, "end": 5.0})
        longer = self.paired([(0.0, 0.0)] * 3, [(0.0, 0.0)] * 3, months=48)
        self.assertEqual(longer["gain_usd_a_year_at_month"], {"36": 1.33, "48": 4.17, "end": 4.17})

    def test_the_region_reads_the_bound_beside_the_clause_as_built(self):
        """The region reads the bound beside the clause without it.

        Example: twenty seeds (``map_seed``), every gain zero, are stable without the bound and under it, in the
        region both ways. With one class at -$3 under the bound at both ends against S0 (the arm saving $3 a year on
        cash advances it did not take in banks), the verdict without the bound stays stable, with the clause and every
        key unchanged, but the verdict under the bound is "a group loses", on a bare majority too, and the cell is not
        in the region both ways."""
        import copy
        from scripts.run_economy_population import decide

        def region(bound=None):
            rows = []
            for seed in range(20):
                row = copy.deepcopy(map_seed(seed))
                for arm in ("M1", "M2"):
                    for end in ("face", "zero"):
                        if bound is not None:
                            row["arms"][arm]["against"]["S0"]["complete_gain"][end]["bound"][
                                "gain_usd_a_year_by_class"] = [0.0, bound, 0.0, 0.0]
                rows.append(row)
            return decide(rows, 0.044, 0.6, 0.0, False, Economy())["M1"]["region"]
        clean, losing = region(), region(-3.0)
        self.assertEqual((clean["verdict"], clean["verdict_bound"], clean["in_region"], clean["in_region_both"]),
                         ("stable", "stable", True, True))
        self.assertEqual((losing["verdict"], losing["verdict_majority"], losing["in_region"]), ("stable", "stable", True))
        self.assertEqual((losing["verdict_bound"], losing["verdict_majority_bound"], losing["in_region_both"]),
                         ("a group loses", "a group loses", False))
        self.assertFalse(losing["complete_gain_bound"]["clause_holds"])
        self.assertEqual(losing["complete_gain_bound"]["zero"]["lowest"],
                         dict(lower_95=-3.0, mean=-3.0, group="no card and business income", against="S0"))
        self.assertEqual({key: value for key, value in losing.items() if not key.endswith(("_bound", "_both"))},
                         {key: value for key, value in clean.items() if not key.endswith(("_bound", "_both"))})


if __name__ == "__main__":
    unittest.main()

"""The run and the composed world.

The loop (run, and one month: obligations, the pool's terms, dealing, thirty days of settlement, then the close),
the class ``_World`` composed of the mixins in the order of events, ``simulate``, the public entry point, and the
burn-in computed once: ``launch_state``, a world at launch, and ``resume``, a run of any a0 and distress level
from it. Every method lives in exactly one mixin, so the class behaves as the single class it was before the split.
"""
import copy
from dataclasses import replace

import numpy as np

from cpm_abm.engine.constants import CREDIT_RECORDS, DAYS, EPS, FAILURE_COUNTS, LOAN_YEARS
from cpm_abm.engine.settings import Economy
from cpm_abm.engine.rates import money_market_share, outside_return
from cpm_abm.engine.ledger import _take
from cpm_abm.engine.measures import KNOCK_ON_BINS
from cpm_abm.engine.world_state import StateMixin
from cpm_abm.engine.world_payments import PaymentsMixin
from cpm_abm.engine.world_month import MonthMixin
from cpm_abm.engine.world_dealing import DealingMixin
from cpm_abm.engine.world_day import DayMixin
from cpm_abm.engine.world_credit import CreditMixin
from cpm_abm.engine.world_close import CloseMixin


class LoopMixin:
    """The run loop of ``_World``: ``run`` advances every month and returns the records, and ``month`` takes one
    month's steps in order."""
    # ----- run --------------------------------------------------------------------------------
    def run(self):
        """Run every month not yet run and return the records (see ``simulate`` for their meaning): every month from
        month 0 for a new world, and from launch for one resumed from its state at launch (``resume_at``,
        ``launch_state``)."""
        list(map(self.month, range(self.resume_at, self.total)))
        return dict(arm=self.arm, a0=self.a0,
                    series={key: np.array(value, float) for key, value in self.series.items()},
                    wealth=self.wealth_path, participant=self.status, owner=self.owner_path, borrower=self.borrow_path,
                    receipts=self.receipts_path, purchases=self.purchase_path, credit=self.credit_path,
                    velocity=self.velocity_path,
                    coinage=dict(self.coin.rec, residual=self.coin_residual),
                    fees=self.fee_path,
                    failed=self.failed_path,
                    failure_counts=self.failure_path, transfers=self.transfer_path, channels=self.channels,
                    owned=self.owned_path, crossings=self.cross_path, buffers=self.buffer_path, ewa=self.ewa_path,
                    chronic=self.chronic, population=self.pop, economy=self.economy,
                    exits=dict(started=self.exit_started, in_time=self.exit_in_time),
                    payments=self.payment_log, payout=self.payout_path,
                    loan_age={key: np.array(value, float) for key, value in self.loan_age.items()},
                    vintage={key: np.array(value, float) for key, value in self.vintage.items()}, rho_p=self.rho_p)

    def month(self, month):
        """One month: obligations, the pool's terms, dealing, thirty days of settlement, then close.

        ``launched`` means the pool exists (pool arms after the burn-in);
        ``adopting`` means participation can change (every arm but S0).
        """
        inputs, n, economy = self.inputs, self.n, self.economy
        self.this_month = month
        self.launched = month >= economy.burn_in and self.pool_arm
        self.adopting = month >= economy.burn_in and self.arm != "S0"
        # Wealth at the start of the month anchors the conservation check; outside returns follow current wealth rank.
        start_wealth = self.net_wealth()
        self.r_out = outside_return(start_wealth + self.pop["illiquid"], inputs.rho_H, economy.n12, self.deposit_rate)
        self.mm_share = money_market_share(start_wealth + self.pop["illiquid"], economy.n12)
        self.external = self.valuation = 0.0
        # Month accumulators. Per-person arrays: P balance-time and lowest P balance, pool principal-time, savings
        # on pool credit, charges, shortfalls asked/drawn, card-eligible P payments, fees, receipts, the
        # count and value of payments that could fail (due_n, due_amt: the failure fee's unit price), and the failure
        # fees paid and new failed payments (fee, failed_new; reported).
        # Scalars: pool income and costs, failures, write-offs, outside interest and penalties, new lending, exits.
        # Competitive P: per person, P's yield before demurrage (p_yield, in M0 USDC's savings rate) and the
        # demurrage withheld from it (charges); scalars, that yield on all wallet P (wallet_yield), the reserve return
        # the pool's own P cash earns (float_pool) and what the issuer keeps (float_issuer); the coupon cut demurrage
        # paid on carried bridges (covered), and the value of pool bridges drawn (bridges).
        # lost and exposure: write-offs net of recoveries and principal-time by product, bridging then term
        # (loss learning); age_loss and age_exposure: the same for term loans by year of life (reported only);
        # vintage_income and vintage_exposure: the pool's loans' income to owners and principal-time by product and
        # loan year (reported only).
        # The boundary rule's reports: per person, card rewards earned, outside interest accrued, launch
        # conversion fees, savings and pool-share balance-time and the spreads kept on its money and savings; scalars,
        # payments by rail, pool bridges to payers without a card and principal-time of card and term credit. The
        # failure counts, per person; crossings between E and P, each person's count and value, routine
        # (row 0) and conversions (row 1). fee_units: each person's failure fees charged this month, in fee units, which
        # the monthly cap reads; rebuilt here, so the count resets on day 1. pt_pool_nocard_card: principal-time
        # of pool bridges to payers without a card that paid card-eligible purchases (reported), and
        # pt_pool_card_credit, of the part of pool bridges to card holders that replaced card credit
        # (reported). Earned-wage access: each person's room on each day (ewa_room, read by the replays) and its
        # payer-days with an advance, advances and their fees (ewa_uses, ewa_value, ewa_fees; reported). card_bridging:
        # holders' card bridging of the bills and wages their money could not pay (reported, for the S0 check),
        # and their cash advances. gas and gas_paid: each payer's gas on P and USDC payments and their total
        # (``_pay_gas``). The yardsticks: recovered_principal, the principal part of payments on written-off pool loans,
        # and pool_cash_bt, the pool's own P cash over the month, which M2 indexes (records only); p_term_n and
        # p_term_value, the term purchases among P payments (records only). Demurrage pays for liquidity kept available:
        # by day, the pool bridging principal carried and the pool cash held ready (cash not owed to its creditors) at
        # each day's accruals (bridge_day, ready_day), and in all the bridging and the term lending the pool refused
        # (refused_bridging, refused_term), which the next terms read; and the owners who filed a new exit request at
        # the dealing (exits_filed, a record). Purchases, per person, records only: service and shock purchases
        # completed and lost as buyer, durables bought, and sales at face value as seller (bought_completed,
        # bought_lost, bought_durables, sold; ``purchase_path``). Credit, per person, records only: credit_ and each of
        # ``CREDIT_RECORDS`` but the pool's bridges and refusals, which the close reads from drawn and want
        # (``credit_path``). Records only, read by no rule: each person's payments to others out of its E and P
        # (outflow, ``_debit``, MicroVelocity's numerator), and the number of service and shock purchases completed,
        # each counted at the share completed (bought_n), and of durables settled (durables_n). Card limits: each
        # holder's room on its cash line by day for the replays (card_room), gross of the month's own advances still
        # owed; per person the cash-advance and late fees charged (advance_fee_i, late_fee_i); scalars, those fees, the
        # balances charged off, the lines closed and the card-eligible purchases past a holder's room (records only).
        # The harsh stress, records only: the part of an extra layoff's wage not paid on its first due date
        # (wage_out_failed), and the failure share's failed and due of hit workers as payers (failed_hit, due_hit);
        # ``_obligations`` sets the month's wages sent outside (wages_out) and its hit workers (hit). The pool run under
        # the harsh stress, records only: the money offered at the dealing and the part that found no room (offers,
        # offers_unused), and the pool's write-offs of bridges and of term loans (written_off_bridge, written_off_term).
        # Reserved standby (a record only): the month's mean of the cash held back from term loans for bridges
        # (standby_held), zero unless it is on. The edge (a record only): what the month booked across the edge when a
        # debt to the outside was created (edge_accrued, ``_edge_debt``), and the part of the payout not returned to
        # households under ``Economy.edge_returned`` (edge_kept), and the most the pool owed its operating provider on
        # any day of the month (pool_payable_most), and the days whose settlement was held under
        # ``Economy.settle_cycle`` "hold" (settle_held, a count).
        self.acc = dict(
            flows=np.zeros((n, DAYS)), flows_s0=np.zeros((n, DAYS)), bridge_path=np.zeros((n, DAYS)),
            p_low=np.full(n, np.inf), ewa_room=np.zeros((n, DAYS)), bridge_day=np.zeros(DAYS),
            ready_day=np.zeros(DAYS), card_room=np.zeros((n, DAYS)),
            **{key: np.zeros(n) for key in ("p_bt", "bridge_pt", "term_saving", "charges", "want", "drawn",
                                             "card_internal", "gas", "conversion", "merchant",
                                             "merchant_saved", "receipts", "wages_paid", "failed_cum", "liquid_bt",
                                             "p_yield",
                                             "due_n", "due_amt", "fee", "failed_new", "rewards", "out_interest_i",
                                             "launch_conversion", "savings_bt", "shares_bt", "spread", "fee_units",
                                             "ewa_uses", "ewa_value", "ewa_fees", "bought_completed",
                                             "bought_durables", "bought_lost", "sold", "outflow",
                                             "advance_fee_i", "late_fee_i")},
            **{key: np.zeros(n) for key in FAILURE_COUNTS},
            **{"credit_" + key: np.zeros(n) for key in CREDIT_RECORDS if key not in ("bridge_pool", "bridge_refused")},
            **{key: 0.0 for key in ("slow_days", "most_sweeps", "coupons", "op_cost", "failed", "due", "wage_failed",
                                    "refused",
                                    "written_off", "recovered", "interest_collected", "p_all", "new_pool_loans",
                                    "utilisation", "bridge_coupons", "pool_pt", "out_interest", "penalties",
                                    "new_term_pool", "new_term_outside", "exit_requested", "exit_paid",
                                    "shocks", "idle", "fee_refused", "fee_refused_n", "card_n", "card_value", "p_n",
                                    "p_value", "nocard_bridges", "pt_card", "pt_term", "pt_pool_card", "pt_pool_term",
                                    "deposit_spread", "pool_operating", "pt_pool_nocard_card", "pt_pool_card_credit",
                                    "card_bridging", "recovered_principal", "gas_paid",
                                    "pool_cash_bt", "p_term_n", "p_term_value", "wallet_yield", "float_pool",
                                    "float_issuer", "covered", "bridges", "revolved", "comet_bridging",
                                    "refused_bridging", "refused_term", "exits_filed", "bought_n", "durables_n",
                                    "advance_fees", "late_fees", "charged_off", "lines_closed", "card_spilled",
                                    "wage_out_failed", "failed_hit", "due_hit", "offers", "offers_unused",
                                    "written_off_bridge", "written_off_term", "standby_held", "edge_accrued",
                                    "edge_kept", "pool_payable_most", "settle_held",
                                    "edge_discharged")},
            # The settlement's records of failure passed along and of dependence on netting (``_chain_records``).
            **{key: 0.0 for key in ("own_shortfall", "knock_on", "knock_on_positive", "own_shortfall_n", "knock_on_n",
                                    "cash_completed", "netting_days", "netting_n", "netting_value", "netting_lost")},
            knock_on_days=np.zeros(len(KNOCK_ON_BINS)),
            lost=np.zeros(2),
            crossings=np.zeros((2, n)), crossed=np.zeros((2, n)), exposure=np.zeros(2), loss_base=np.zeros((3, 2)),
            age_loss=np.zeros(LOAN_YEARS), age_exposure=np.zeros(LOAN_YEARS), borrowed=np.zeros(n, bool), log=[],
            vintage_income=np.zeros((2, self.vintage_years)), vintage_exposure=np.zeros((2, self.vintage_years)))
        self.coin_mark = np.zeros(n)   # the month's outflow already handed to the money's ages (``_coin_day``)
        # Payers in chronic deficit (reported only): each burn-in month's spending is added up, and the flag is
        # set at launch, before the launch conversion, in every arm.
        if month < economy.burn_in:
            self.burn_spent += self.spending
        if month == economy.burn_in:
            self._chronic()
        if month == economy.burn_in and self.arm != "S0":
            # Launch: the initial participants are drawn with probability a0 and convert their working
            # balance into P (the switching cost chi). This sunk adoption cost is recorded with the fees but
            # kept out of the experience of using P, as for any later joiner.
            # Under the launch switch (``Economy.launch``) the same number of people start in one neighbourhood or
            # among the largest sellers instead (``Network.launch_set``).
            self.part = (self.start_draw < self.a0 if economy.launch == "scattered"
                         else self.network.launch_set(economy.launch, self.a0, self.start_draw))
            self._join(self.part, np.full(n, 1.0) if not economy.routine_conversion else self.a0 * self._p_need())
            self.channels["conversion_paid"] += self.acc["conversion"]
            self.acc["launch_conversion"] = self.acc["conversion"].copy()
            self.acc["conversion"][:] = 0.0
        # Draw adoption numbers now, in every arm, so the random streams stay aligned across arms.
        self._layoffs(month)
        self._cut_lines(month)
        self._obligations(month)
        join_draw, review_draw = self.adopt_rng.random(n), self.adopt_rng.random(n)
        leave_draw = self.leave_rng.random(n)
        # The owners' review and leaving draws, every month in every arm, on their own stream.
        self.owner_draws = self.owner_rng.random(n), self.owner_rng.random(n)
        # The savers' entry-review draw, every month in every arm, on its own stream.
        self.entry_draw = self.entry_rng.random(n)
        self._cycle_terms(month)
        # Conversions paid at dealing belong to investing, not to holding P, so the leaving rule leaves them out.
        before = self.acc["conversion"].copy()
        self.capital = self._dealing(month)
        self.acc["dealing_conversion"] = self.acc["conversion"] - before
        self._count_crossings()   # the dealing, with the launch conversions, is one step (reported only)
        if self.defi and self.economy.comet == "pinned":
            self._comet_rates()
        # The pool serves (lends) only while it has owners; P payments do not depend on it.
        self.asking = bool(self.launched and not self.winding)
        self.service = bool(self.asking and self._all_shares() > EPS)
        list(map(lambda d: self.day(month, d), range(DAYS)))
        # Keep only obligations and requests settling in later months; the card statement closes on day 29 (under each
        # holder's own date it closes at the end of its own closing day, ``_close_statements``).
        self.ob = _take(self.ob, self.ob["settle"] >= (month + 1) * DAYS)
        self.req = _take(self.req, self.req["settle"] >= (month + 1) * DAYS)
        if economy.statement_dates == "common":
            self.card_statement += self.card_unbilled
            self.card_unbilled[:] = 0.0
        self._close(month, start_wealth, join_draw, review_draw, leave_draw)
        self._coin_day(month * DAYS + DAYS - 1)   # the last day and the close, one day of the money's ages
        self.coin_residual[month] = float(np.abs(self.coin_gap).max()) if n else 0.0
        self.coin_gap[:] = 0.0


# ====================================================================================================================
# One simulated economy
# ====================================================================================================================
class _World(StateMixin, PaymentsMixin, MonthMixin, DealingMixin, DayMixin, CreditMixin, CloseMixin, LoopMixin):
    """One arm of the economy: every account, the pool, completed observations and the monthly records.

    The state is held in arrays over the n people (balances, debts, status)
    and in record tables (obligations, term requests, the loan book,
    durables). ``run`` advances it month by month; ``simulate`` is the public
    entry point. Methods starting with an underscore are steps of the monthly
    or daily sequence described in the module docstring.
    """


def simulate(inputs, a0, economy=Economy(), arm="M1"):
    """Run one arm of the economy and return its records.

    Parameters
    ----------
    inputs:  ``core_model.Inputs``; contract and price parameters shared with the core model.
    a0:      initial participation share at launch (the control a0).
    economy: ``Economy``; population, calendar, switches and stresses.
    arm:     "S0", "M0", "M1", "M2" or "U" (M1 with no demurrage).

    Returns a dict with ``series`` (monthly aggregates, one value per month,
    amounts per capita in months of mean spending), ``wealth`` (net wealth of
    every person after each month), ``participant``, ``owner`` and
    ``borrower`` (person-by-month flags), ``receipts``, ``purchases``
    (person-by-month records: as buyer, service and
    shock purchases ``completed`` and ``lost`` and the price of durables
    bought that settled, ``durables``; as seller, ``sales``, the face value
    of service and shock purchases completed to it plus the price of
    durables it sold; wages in none), ``velocity`` (the records read by
    ``turnover`` and ``microvelocity``, ``VELOCITY_RECORDS``: person-by-year-after-launch sums of
    payments to others out of E and P, ``outflow``, and of balance-time in
    unit-months of E and P, ``money_bt``, outside savings, ``savings_bt``,
    and pool shares at NAV, ``shares_bt``), ``coinage`` (records only:
    the holding times of money by convention, year after launch and person,
    ``Coinage`` and ``COINAGE_RECORDS``, read by ``holding_velocity``, and
    ``residual``, each month's largest unreconciled money of one person),
    ``credit`` (person-by-month records,
    in the model's money, by the borrower or payer
    named, ``CREDIT_RECORDS``): ``bridge_pool``, pool bridging principal
    drawn for payments and card statements (the ``bridges`` series, by
    payer; P in M2); ``bridge_card``, card bridging of payments the
    holder's money could not pay (its cash advances) plus
    statement balances left to revolve
    (the ``card_bridging`` and ``revolved`` series; card purchases paid at
    the statement are not credit here), with ``advance_card``, the cash
    advances alone, ``fees_card``, the card's cash-advance and late fees
    charged, and ``charged_off_card``, the card balance charged off at 180
    days past due; ``bridge_comet``, M0's Comet
    borrowing (the ``comet_bridging`` series); ``bridge_refused``, pool
    bridging asked for and not drawn, payments and statements (the
    bridging part of the ``refused`` series); ``term_pool`` and ``term_outside``,
    instalment principal lent by each lender (the ``new_term_pool`` and
    ``new_term_outside`` series); ``term_cancelled``, the price of
    instalment requests that needed credit and did not qualify;
    ``interest_pool``, ``interest_card`` and ``interest_outside``, interest
    accrued on the person's pool loans (written-off loans included), card
    balances (revolving, cash advances) and every other outside loan
    (instalment loans, Comet bridges, overdrafts); ``wages_late``, as
    payer, the part of each wage not paid on its first due date, a
    re-queued wage not counted again; and ``interest_advance``, the part of ``interest_card``
    accrued on cash advances alone, and ``fees_advance``, the part of
    ``fees_card`` that is cash-advance fees, the late fees its rest),
    ``fees`` and
    ``failed`` (person-by-month failure fees charged, under the daily and
    monthly caps, and new failed payments, a
    re-queued wage not counted again), ``failure_counts`` (person-by-month
    counts of failed, declined and bridged payments, ``FAILURE_COUNTS``),
    ``transfers`` (person-by-month payments
    to intermediaries outside the economy, net of card rewards: outside
    interest, failure fees, card fees as a seller, conversion fees, gas in M0,
    the spreads banks and issuers keep on its money and savings,
    earned-wage fees and the card's cash-advance and late fees), ``ewa``
    (person-by-month earned-wage access:
    payer-days with an advance as ``uses``, advances as ``value`` and their
    ``fees``), ``chronic`` (each person's flag as a payer in chronic deficit
    at launch, reported only),
    ``channels`` (cumulative per-person fees, rewards and the demurrage
    withheld from P's yield), ``owned`` (person-by-month pool capital after dealing; with the
    R series, each owner's own realised return, ``own_returns``),
    ``crossings`` (person-by-month routine crossings between E and P, at
    most one a step: a day, the dealing or the close), ``buffers``
    (person-by-month buffer chosen at dealing), the
    ``population``, a ``payments`` log for the launch and final months,
    ``payout`` (person-by-month, a record only: what
    each person received from the conserved edge's monthly payout, each
    month summing to the ``returned`` series times n; zero with the edge
    open), and
    ``loan_age``: per month and per capita, pool term-loan write-offs by the
    loan's year of life when it first missed a payment, and term exposure by
    year of life (years 1 to 5; the last band holds year 5 and later);
    ``vintage``: per month and per capita, arrays of month x product
    (bridging, then term) x loan year (the year after launch a pool loan was
    made, years 1 to 5, the last band holding year 5 and later; in a run longer than
    60 months one band for every year after launch), the pool's
    loans' income to owners (coupons less the operating cost they carry,
    write-offs and recoveries) and their carried principal-time, with the
    month's pool-wide cost (the fixed cost, whose coupon part is in the
    loans' income) as ``shared`` (reported only); and ``rho_p``, the reserve rate the
    contract runs at, per month (real in M2).

    Random numbers (population, purchases, wages, shocks, term requests,
    adoption draws) are common across arms for one seed, so an arm and its
    S0 pair differ only through CPM. Compare arms person by person on
    ``wealth`` at the same month.
    """
    if arm not in ("S0", "M0", "M1", "M2", "U"):
        raise ValueError("The engine runs S0, M0, M1, M2 and U")
    return _World(inputs, a0, economy, arm).run()


# ====================================================================================================================
# The burn-in computed once
# ====================================================================================================================
# What a state at launch may serve: the engine reads a0 only at launch and the distress level only from the distress
# year, which starts distress_start months after launch, so a world run through the burn-in is the same at every a0
# and every distress level. It is not the same in every arm: the arms set their own terms when the world is opened
# (P's yield, the conversion fee, the coupons, the issuer's share) and some of them enter the burn-in's records and,
# in M0, its arithmetic, so each arm keeps a state of its own. Everything else the world was opened with counts: the
# Inputs, and every Economy field but the distress level (the seed, the population, the burn-in, the run's length,
# which sizes the records, the convention for lenders' interest and every switch).
def launch_state(inputs, economy=Economy(), arm="M1"):
    """The world of ``arm`` at launch: every burn-in month run and no later one, a state that ``resume`` copies to
    start runs of this arm at any a0 and any distress level.

    The state is opened with no launch share (a0 NaN), which nothing reads before launch; ``resume`` sets it.
    """
    if arm not in ("S0", "M0", "M1", "M2", "U"):
        raise ValueError("The engine runs S0, M0, M1, M2 and U")
    world = _World(inputs, np.nan, economy, arm)
    launch = min(economy.burn_in, world.total)
    list(map(world.month, range(launch)))
    world.resume_at = launch
    return world


def resume(state, inputs, a0, economy, keep=True):
    """A copy of a ``launch_state`` set to launch share ``a0`` and the Economy ``economy``, ready to ``run`` from
    launch; its run equals ``simulate(inputs, a0, economy, state.arm)`` bit for bit.

    Refuses (ValueError) a state opened with other Inputs or with an Economy that differs from ``economy`` in any
    field but the distress level, the only cases in which a run from the state would not be that direct run. Values
    are compared by their exact representation, so a rate that differs in its last bit is refused. With ``keep`` the
    state itself is left as it was, so it can serve every run that shares it; without, the state is used in place of
    a copy (for a state read fresh from disk, which serves one run).
    """
    if repr(state.inputs) != repr(inputs):
        raise ValueError("This state at launch was opened with other Inputs; it serves only runs of its own Inputs")
    if repr(replace(state.economy, distress=economy.distress)) != repr(economy):
        raise ValueError("This state at launch was opened with another Economy; it serves runs that differ from it "
                         "in the distress level alone")
    if state.resume_at != min(state.economy.burn_in, state.total) or state.this_month != max(state.resume_at - 1, 0):
        raise ValueError("This world is not a state at launch (``launch_state``): it has run past launch or not to it")
    world = copy.deepcopy(state) if keep else state
    world.a0, world.economy = a0, economy
    return world

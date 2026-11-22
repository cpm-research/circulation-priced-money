"""The world's state: opening every account from the population, net wealth, pool assets and the loan book.
"""
import numpy as np

from cpm_abm.engine.constants import (BIG, BOOK_FIELDS, CASH_ADVANCE_APR, CASH_ADVANCE_FEE_FLOOR, CASH_ADVANCE_FEE_RATE,
                                      CONVERSION_FEE, CREDIT_RECORDS, DAYS, FAILURE_COUNTS, GAS_PER_P_PAYMENT,
                                      GAS_PER_PAYMENT, ISSUER_BOOKS, LOAN_LOSS_SERIES, LOSS_CARRIED, MARGIN_PARTS,
                                      MEASURE_SERIES, TERM, USDC_CONVERSION, VELOCITY_RECORDS)
from cpm_abm.engine.population import build_population, card_tier, income_bracket, layoff_weight, spell_law, spell_stock
from cpm_abm.engine.rates import issuer_share, m0_rates, money_market_share, outside_prices, outside_return
from cpm_abm.engine.ledger import _empty, _overdue_of, Coinage
from cpm_abm.engine.measures import CHAIN_SERIES
from cpm_abm.engine.network import build_network


class StateMixin:
    """The world's state, one part of ``_World``: opens every account from the population and reads net wealth, the
    pool's assets and the loan book."""

    def __init__(self, inputs, a0, economy, arm):
        """Open every account from the population; nobody participates before launch.

        inputs:  ``core_model.Inputs`` (contract and price parameters, shared with the core model)
        a0:      initial participation share at launch (the experiment's control a0)
        economy: ``Economy`` (population, calendar and switches)
        arm:     "S0", "M0", "M1", "M2" or "U" (M1 with no demurrage, decided 4 Nov)
        """
        # --- the population and its fixed characteristics -------------------------------------------------------
        self.inputs, self.a0, self.economy, self.arm = inputs, a0, economy, arm
        self.n = n = economy.n
        self.pop = build_population(economy)
        # The robustness switches' fixed network, thresholds and launch places (``network``), built from the seed and the
        # population alone, so every arm shares them; with every switch off it holds nothing and draws nothing.
        self.network = build_network(economy, self.pop["spending"])
        # Who holds an open card line now: the population's holders, until a charge-off closes a line (decided
        # 14 Nov 2026). A copy, so the population's own flag, which fixes each person's class, never changes.
        self.holder, self.card_apr = self.pop["holder"].copy(), self.pop["card_apr"] / 12
        self.spending = self.pop["spending"].copy()
        if economy.card_base_all:
            # Card-eligible share of service spending (decided 3 Nov): every non-housing bundle, 28% of spending.
            # The same uniform draw decides, so every bundle eligible as built stays eligible. Housing bundles are not
            # otherwise told apart, so a bundle is non-housing with probability 1 - housing on that draw:
            # a reading of the rule (4 Nov).
            self.card_share = 1 - inputs.housing
        else:
            # As built: non-housing spending times the core's card share (18.2% of spending).
            self.card_share = (1 - inputs.housing) * inputs.card_share
        # Outside prices (decided 3 Nov), the same in every arm: the savings deposit rate and, sealed in each loan
        # when it is made, card APRs and new term loans' rates follow r_out (``outside_prices``). The checking yield
        # (buffer_yield) and r_ext stay fixed, the 0.08 and 0.06% being the savings deposit series:
        # a reading of the rule (4 Nov). term_shift (a year, by product) is read when term requests
        # are made, so a loan's rate is fixed in the book once made; None with fixed prices (as built).
        self.deposit_rate, card_shift, self.term_shift = outside_prices(inputs.rho_H, economy)
        if economy.linked_rates:
            self.card_apr = (self.pop["card_apr"] + card_shift) / 12
        # Card limits (decided 14 Nov 2026), the same in every arm: each holder's line, closed (zero) by a
        # charge-off and cut only under the side check, its fixed starting balance and its score tier; the cash-advance
        # APR a month, which moves with r_out as the purchase APRs do, and the advance's fee, the greater of the floor
        # and the rate per unit. Per card the minimum's terms since the last statement: the interest charged and the
        # fees charged, the payments made on the card's balances, which count towards the next minimum, and the
        # minimum left unpaid at it (past due); the day the oldest unpaid minimum fell due (BIG while current) and the
        # month of the last late fee, which a repeat within six cycles reads.
        self.card_line, self.card_start = self.pop["card_line"].copy(), self.pop["card_start"]
        self.card_tier = card_tier(self.pop["score"])
        self.cash_apr = np.full(n, CASH_ADVANCE_APR + (card_shift if economy.linked_rates else 0.0)) / 12
        self.advance_floor, self.advance_rate = CASH_ADVANCE_FEE_FLOOR, CASH_ADVANCE_FEE_RATE
        self.card_interest, self.card_fees, self.card_past_due = np.zeros(n), np.zeros(n), np.zeros(n)
        self.card_paid = np.zeros(n)
        self.card_late_since, self.card_late_month = np.full(n, BIG), np.full(n, -BIG)
        # --- arm-specific contract terms -------------------------------------------------------------------------
        # The pool arms: M1, M2 and U, which is M1 with no demurrage (decided 4 and 5 Nov: the same P with c = 0).
        self.pool_arm, self.demurrage = arm in ("M1", "M2", "U"), arm in ("M1", "M2")
        # M2: P is indexed to the CPI, so the contract runs in P terms at rho_H - dJ/J. M0: Comet.
        self.indexed, self.defi = arm == "M2", arm == "M0"
        self.index = economy.inflation if self.indexed else 0.0
        # Values fixed for one day, kept while ``day`` runs (a speed device; None outside a day): last month's receipt
        # streams and the day's receipt side of the budget (``_receipt_streams``, ``_receipts_side``).
        self._day_cache = None
        self.rho_p = inputs.rho_H - self.index
        # The issuer's share of the reserve return on P (decided 4 Nov), derived from its cost in its books
        # (``Economy.issuer_cost``) at the contract's reserve rate (``issuer_share``); undefined outside the pool arms.
        # Under competitive P (decided 5 Nov) the issuer keeps s_I rate = c_I of every unit of P, and wallet P and
        # the pool's own P cash earn the rest, ``p_net`` = (1 - s_I) rate = rho_p - c_I a month (zero where rho_p is at
        # or below c_I, the declared limit), wallet P less demurrage c.
        rate = max(self.rho_p, 0.0)
        self.s_issuer = issuer_share(rate, economy.issuer_cost) if self.pool_arm else np.nan
        self.p_net = (1 - self.s_issuer) * rate if self.pool_arm else 0.0
        # The coupons on pool bridging (r_g) and pool term loans (r_term): the coupon's capital part, owners'
        # alternative (the reserve rate and the owners' spread, 3 Nov), plus o, before any loss is learned or any fixed
        # cost priced (r_fix, 5 Nov); r_b is the rate a bridge drawn this month is sealed at, r_g less demurrage's
        # coverage of the capital part (4 Nov).
        self.r_g = self.r_term = self.r_b = max(rate + economy.owner_spread + inputs.o, 0.0)
        # The coupon on pool term loans for business products: r_term but for the class's priced loss under the
        # loan-loss bound (decided 12 Nov, ``_priced_loss``), so equal to r_term without the bound.
        self.r_term_business = self.r_term
        self.r_fix = 0.0
        # Loss learning by product, bridging then term (decided 29 Oct): losses net of recoveries over the
        # principal-time carried at least LOSS_LAG_MONTHS ago, so every unit counted has had time to show its loss.
        # exposure holds each completed month's principal-time by product.
        self.loss_net, self.exposure = np.zeros(2), np.zeros((0, 2))
        # Reported only: term-loan write-offs (by the loan's year of life when it first missed a payment) and exposure
        # (by its year of life), per month, so a run shows when defaults come. this_month dates a loan's age.
        self.loan_age, self.this_month = dict(written_off=[], exposure=[]), 0
        # Reported only (owners' return by loan year, decided 4 Nov): per month, the pool's loans by product
        # (bridging, then term) and by loan year, their income to owners and their carried principal-time; and the
        # month's pool-wide cost, the fixed cost, which the reading spreads over the loan years (the coupon's part that
        # pays it, 5 Nov, is in the loans' income).
        self.vintage = dict(income=[], exposure=[], shared=[])
        # Job loss: each wage contract is a job, indexed by its payer, that pays nothing on days spell_start <= t <
        # spell_end. layoff_rate is each job's monthly layoff probability per unit of the monthly rate (normal job loss
        # and the distress control's extra rate): its earner's bracket weight over the average job's. spell_out marks a
        # job whose spell came from a distress year's extra layoff (decided 14 Nov 2026: the harsh stress), whose
        # wage leaves the household economy for the whole spell; the month-0 stock and normal job loss are never marked.
        self.spell_start, self.spell_end = np.zeros(n, int), np.zeros(n, int)
        self.spell_out = np.zeros(n, bool)
        weight = layoff_weight()[income_bracket(self.pop["spending"])[self.pop["wage_to"]]]
        self.layoff_rate = weight / weight.mean()
        if economy.job_loss > 0:
            # Normal job loss starts from its steady stock at month 0 (decided 3 Nov), drawn on a stream of its own,
            # the same in every arm and at every distress level (``spell_stock``). Without it no job starts in a spell.
            stock = np.random.default_rng(np.random.SeedSequence([economy.seed, 23]))
            self.spell_start, self.spell_end = spell_stock(stock, economy.job_loss * self.layoff_rate,
                                                           *spell_law(economy))
        # p_yield is what a unit of P (USDC in M0) earns its holder a month, in nominal terms: in the pool arms the
        # published y_P plus M2's indexation (``_cycle_terms`` resets it each month, net of that month's demurrage); in
        # M0 the savings rate, the bill less the Sky spread in the "reserve" mode (decided 5 Nov), the Comet supply
        # rate otherwise; 0 in S0. comet_borrow is M0's secured borrowing rate: in the "reserve" mode Comet's borrow
        # rate moving with r_out (decided 5 Nov, ``m0_rates``); otherwise that supply rate plus the pin's margin.
        # comet_supply is Comet's own supply rate in the "reserve" mode, which no rule there reads (USDC earns the
        # savings rate), kept as a record. cover is each person's share of an uncovered need Comet lends against: 1 for
        # M0's crypto collateral holders (``Economy.crypto_share``), 0 for everyone else and in every other arm.
        reserve = self.defi and economy.comet == "reserve"
        savings, borrow, self.comet_supply = m0_rates(inputs.rho_H, economy.m0_rates)
        supply = savings if reserve else inputs.rho_H + inputs.supply_premium
        self.p_yield = self.index + self.p_net if self.pool_arm else (supply if self.defi else 0.0)
        self.comet_borrow = borrow if reserve else supply + inputs.borrow_margin
        self.cover = (self.pop["crypto"] & self.defi).astype(float)
        # What the issuer keeps a month on each unit of a household's P or USDC, for the spreads households pay
        # (``_accrue``, a record): its custody s_I rate in the pool arms (the demurrage c goes to the pool, inside the
        # household economy), the Sky spread in M0's "reserve" mode, otherwise the whole reserve return, as built.
        self.issuer_keeps = (self.rho_p - self.p_net if self.pool_arm
                             else inputs.rho_H - supply if reserve else inputs.rho_H - self.index)
        # The conversion fee between dollars and P, or USDC in M0, which converts at no fee (decided 5 Nov).
        self.conversion = USDC_CONVERSION if self.defi else CONVERSION_FEE
        # The gas a completed payment costs its payer (decided 5 Nov): two transfers for USDC, one for P.
        self.gas = GAS_PER_PAYMENT if self.defi else GAS_PER_P_PAYMENT
        self.total = economy.burn_in + economy.months
        # --- household accounts (one entry per person) -------------------------------------------------------------
        # cash: E (bank money); pcash: P (or USDC in M0); savings: one-month outside deposits (own outside rate);
        # shares: pool shares, valued at nav_ps; receivable/payable: invoices not yet settled; card balances;
        # od_pending: overdraft booked at the end of the current step; durable: term-credit purchases.
        zeros = lambda: np.zeros(n)
        self.cash, self.pcash = self.pop["wealth"].copy(), zeros()  # E and P balances (participants hold both)
        self.savings, self.shares, self.od_pending = zeros(), zeros(), zeros()
        self.receivable, self.payable = zeros(), zeros()
        self.card_unbilled, self.card_statement = zeros(), zeros()
        # Earned-wage access (decided 3 Nov), per job (indexed by its payer): accrued, the wages earned and not yet
        # due; ewa_owed, what the job's earner owes on advances against them, fee included. Reported only (3 Nov):
        # each person's spending over the burn-in and its chronic-deficit flag at launch (``_chronic``).
        self.accrued, self.ewa_owed = zeros(), zeros()
        self.burn_spent, self.chronic = zeros(), np.zeros(n, bool)
        self.durable = dict(owner=np.zeros(0, int), value=zeros()[:0], step=zeros()[:0], left=np.zeros(0, int))
        # sector holds outside lenders' interest until the close, under the recirculation stress only.
        self.nav_ps, self.pool_cash, self.sector = 1.0, 0.0, dict(lenders=0.0)
        # Costs the pool has incurred but could not yet pay: an unpaid operating payable, as in the October 2026
        # draft's ledger appendix.
        self.pool_payable = 0.0
        # Exit test: each owner's open exit request (start month, start NAV, shares still to pay), and per start month
        # the value requested and the value paid within two months.
        self.exit_start, self.exit_nav, self.exit_left = np.full(n, -1), zeros(), zeros()
        # The dealing's executed exits that pool cash left unpaid, by owner at this NAV, and who wants out, which the
        # dealing's offers buy first (decided 5 Nov: subscriptions meet redemptions, as in an open-ended fund).
        self.exit_unpaid, self.exit_want = zeros(), np.zeros(n, bool)
        # Who was paid any part of its holding at this dealing's exits; it offers nothing at the same dealing.
        self.exit_paid_out = np.zeros(n, bool)
        # The money offered to the pool at the last dealing that found no room (decided 12 Nov: new subscriptions
        # pay leaving owners first), which ``_cash_for_loans`` counts on to pay the next dealing's due exits; zero
        # before the first dealing after launch, so until then every exit falling due is set aside.
        self.unused_offers = 0.0
        self.exit_started, self.exit_in_time = np.zeros(economy.burn_in + economy.months), \
            np.zeros(economy.burn_in + economy.months)
        # --- participation, buffers and the record tables -----------------------------------------------------------
        # part: who holds and accepts P; exp_hist and p_hist: the last 12 monthly experiences and average P balances
        # while in P (the leaving rule and its threshold, 3 Nov); arrears: arrears flag; buffer: the cash buffer chosen
        # at dealing; ob: open payment obligations; req: term credit requests; book: every loan (BOOK_FIELDS).
        self.part = np.zeros(n, bool)
        self.exp_hist = np.zeros((0, n))
        self.p_hist = np.zeros((0, n))
        self.arrears = np.zeros(n, bool)
        self.buffer = self.cash.copy()
        self.ob = _empty(("buyer", "seller", "amount", "settle", "card", "kind"), (int, int, float, int, bool, int))
        self.req = _empty(("buyer", "seller", "price", "settle", "product", "rate", "months"),
                          (int, int, float, int, int, float, int))
        self.book = _empty(BOOK_FIELDS, (int, bool, int, float, float, float, float, float, int, float, float, int,
                                         int, int, int, bool, float, float, bool))
        self._book_store = None   # the book's backing arrays with spare room (``_append_book``)
        # Adoption draws come from their own stream, so every arm sees the same random numbers (common random
        # numbers): an arm and its S0 pair differ only through CPM.
        self.adopt_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 7]))
        self.start_draw = self.adopt_rng.random(n)
        # The leaving rule's logistic draws (decided 4 Nov) come from a stream of their own, one a person a month in
        # every arm, so no earlier draw moves and every arm sees the same numbers.
        self.leave_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 29]))
        # Owners leave by the users' rule (decided 5 Nov) on a stream of their own: each month, in every arm, a
        # review draw and a leaving draw a person, so no other stream moves and every arm sees the same numbers.
        self.owner_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 31]))
        self.owner_draws = np.ones(n), np.ones(n)   # each month's draws (``month``); before any, nobody reviews
        # Savers review entry at the users' rate (decided 13 Nov) on a stream of their own: each month, in every
        # arm and the burn-in, one entry-review draw a person, so no other stream moves and every arm sees the same
        # numbers. A person offers its money-market part to the pool only in a month its draw is below upsilon.
        self.entry_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 41]))
        self.entry_draw = np.ones(n)                # each month's draws (``month``); before any, nobody reviews
        # --- pool status --------------------------------------------------------------------------------------------
        # ready: readiness (reported only); asking: the pool takes requests (launched, not winding); service: it has
        # owners and can pay and lend; winding: every owner wants out, until the last share is paid out (5 Nov: free
        # entry applies in every month, so the pool is then open again).
        # The month's terms (``_cycle_terms``, decided 4 and 5 Nov): Q, the capital limit N*; R_hat, the quote at
        # it; need and margin, the capital target and the margin F a month that set both; c, demurrage a month on
        # wallet P balance-time; coverage, the share of the capital cost of the liquidity kept available that demurrage
        # pays; s_monopoly, the most a monopoly issuer could take (a bound, recorded only). Demurrage pays for liquidity
        # kept available (decided 5 Nov): peak, the last cycle's peak bridging need; standby, its standby cash-time
        # a month (pool cash held ready up to that peak beyond what was lent), both records. window holds one entry a
        # month since launch, the launch plan first; the terms read the last two, the last cycle.
        self.ready = self.service = self.asking = self.winding = False
        self.c, self.R_hat, self.Q, self.window = 0.0, np.nan, 0.0, []
        # The pool's carried term principal at the last launched close, after CPI, from which each month's window
        # entry reads the growth of the term book (decided 12 Nov); None before the launch month's close.
        self.term_book = None
        self.need = self.margin = self.coverage = self.peak = self.standby = 0.0
        self.s_monopoly = np.nan
        # The issuer is a pure custodian (decided 5 Nov), outside the household economy, with no pool shares: its
        # complete wallet per person in every month since launch (the stay test) and whether that test has recorded
        # "issuer would leave".
        self.issuer_leaves = False
        self.issuer_wallets = []
        # The reserve account (decided 30 Oct): the T-bills behind P. It moves wherever P is issued or redeemed,
        # so each month it can be checked against P owed (people's P and the pool's cash).
        self.reserves = 0.0
        # Crossings between E and P (reported only, decided 3 Nov): each person's moves in the current step, net, E
        # into P less P into E, as routine crossings (row 0, free) and conversions (row 1, paying the fee).
        self.crossed = np.zeros((2, n))
        # Reported only (decided 3 Nov): each household's pool capital after dealing; no rule reads it. Households
        # alone own the pool (decided 5 Nov).
        self.owners_held = zeros()
        # Reported only (decided 4 Nov: the 90% household test reads capital net of queued exits): households'
        # capital in exit requests filed and still unpaid after dealing (``_queued``).
        self.owners_queued = 0.0
        # Monthly flows with the outside and write-off valuation: terms of the conservation identity.
        # self.last holds completed observations from the previous month: what the rules are allowed to read (the
        # pool's terms read the last two months from ``window``). Nothing reads the current month before it is
        # complete. p_low is each person's lowest P balance in the month (idle P's measure, a record since 5 Nov: no
        # rule charges it). avg_payment is the value
        # of each person's payments that could fail per payment carrying the failure fee (the fee's unit price), to
        # begin with a month's spending over its service bills and one wage payment. ewa_room is each person's
        # earned-wage room on each day (3 Nov), which the buffer replay reads, and card_room each holder's room on its
        # cash line on each day, gross of the month's own advances still owed (14 Nov 2026), which it reads too.
        self.external = self.valuation = 0.0
        self.last = dict(flows=np.zeros((n, DAYS)), flows_s0=np.zeros((n, DAYS)), monthly=zeros(), p_low=zeros(),
                         card_internal=zeros(), bridge_path=np.zeros((n, DAYS)), admitted=zeros(), p_share=zeros(),
                         receipts=zeros(), wages_paid=zeros(), ewa_room=np.zeros((n, DAYS)),
                         card_room=np.zeros((n, DAYS)),
                         avg_payment=self.pop["spending"] / ((1 - self.card_share) * economy.bundles + 1))
        # Monthly aggregate records (one value per month, per capita where it is an amount). See ``_close``.
        self.series = {key: [] for key in (
            "A", "failure_share", "wage_arrears", "slow_days", "most_sweeps", "ready", "service", "N", "Q", "p_yield",
            *("issuer_" + key for key in ISSUER_BOOKS), "issuer_stay", "issuer_would_leave", "P_out", "reserves",
            "backing", "backing_topup", "P_bar",
            "term_pool", "term_outside",
            "c", "idle", "charges", "theta", "R", "R_hat", "r_g", "r_term",
            "issuer",
            # Demurrage and competitive P (decided 4 and 5 Nov), per capita where money: the issuer's derived share
            # of the reserve return and, as a bound, the most a monopoly issuer could take, the reserve return the
            # pool's own P cash earns and the issuer's custody take, the yield on wallet P before demurrage, the
            # coverage of the bridging capital cost, the rate a bridge drawn this month is sealed at (r_b), the coupon
            # cut demurrage paid, the capital cost of the month's bridging, the published quote, households' buffers,
            # the pool's idle cash and the total precautionary money, and the month's pool bridges and failures by
            # value.
            "s_issuer", "s_monopoly", "float_pool", "float_issuer", "wallet_yield", "coverage", "r_b", "covered",
            "bridge_capital_cost", "quote", "buffers", "pool_idle", "precautionary", "bridges", "failures",
            # Demurrage pays for liquidity kept available (decided 5 Nov), records only, per capita: the capital
            # target N* starts from, the peak bridging need and the standby cash-time a month the terms read, and the
            # standby's capital cost a month, owners' alternative less what idle cash earns on it.
            "target", "bridge_peak", "standby", "standby_cost",
            # Records only, per capita, for the runner's shortfall covered in every arm alike (5 Nov): card statements
            # left to revolve on the card, and M0's collateralised Comet bridging.
            "revolved", "comet_bridging",
            # The gas payers paid validators on P and USDC payments (decided 5 Nov), per capita.
            "gas",
            "merchant_fees", "conversion_fees",
            "gini", "mean_wealth", "external", "valuation", "wealth_change", "card_debt", "overdraft", "fee_debt",
            "savings",
            "liquid", "bridges_drawn_over_wanted", "experience", "arrears_share", "written_off", "write_off_rate",
            "new_pool_loans", "new_term_pool", "new_term_outside", "refused", "exit_requested", "exit_paid",
            "exits_filed",
            "interest_collected", "pool_costs", "K", "owners", "durable", "shocks", "pool_cash", "cash_to_lend",
            "exp_liquidity", "exp_term",
            "exp_merchant", "exp_charges", "exp_gas", "exp_conversion", "out_interest", "penalties",
            "savings_income", "pool_pt", "inflation", "exp_yield", "laid_off", "laid_off_last_day", "wages_withheld",
            # The harsh stress (decided 14 Nov 2026), records only: the wages of extra layoffs owed to the outside,
            # per capita, the part of them not paid on its first due date, the failure share of hit workers (the
            # earners of a job with a day in a spell that month) and of everyone else, and hit workers' failed shares
            # a person.
            "wages_out", "wages_out_late", "failure_share_hit", "failure_share_rest", "fail_shares_hit",
            "fee_refused",
            "fee_refused_n", "rewards", "pool_operating", "liquid_low",
            # The settlement's records of failure passed along and of dependence on netting (``CHAIN_SERIES``).
            *CHAIN_SERIES,
            # The boundary rule's reports (decided 31 Oct and 1 Nov): payments by rail (count and value), pool
            # bridges to payers without a card, principal-time of outside card and term credit and of pool bridges to
            # card holders and pool term loans, balance-time of money (E and P), E, P, savings and pool shares, and
            # the spreads banks and issuers keep on households' money and savings.
            "card_payments", "card_value", "p_payments", "p_value", "nocard_bridges", "pt_card", "pt_term",
            "pt_pool_card", "pt_pool_term", "money_bt", "e_bt", "p_bt", "savings_bt", "shares_bt", "deposit_spread",
            "issuer_spread",
            # Reported (3 Nov): principal-time of pool bridges to payers without a card that paid card-eligible
            # purchases (new lending), and (14 Nov 2026) of the part of pool bridges to card holders that replaced
            # card credit.
            "pt_pool_nocard_card", "pt_pool_card_credit",
            # The failure counts (3 Nov), a person a month (``FAILURE_COUNTS``).
            *FAILURE_COUNTS,
            # Reported (decided 3 Nov): households' capital, the income credited to it in all and net of issuer
            # money, R net of issuer money, and crossings between E and P.
            "owners_capital", "owners_income", "owners_income_net", "R_net",
            "crossings", "crossed", "conversions", "converted",
            # Reported (the 3 Nov review): the mean buffer chosen at dealing by people without a card and by card
            # holders.
            "buffer_nocard", "buffer_card",
            # Earned-wage access (3 Nov), per capita: payer-days with an advance, advances and their fees, and what is
            # owed on advances at the close.
            "ewa_uses", "ewa_value", "ewa_fees", "ewa_owed",
            # Reported (3 Nov, for the S0 check): holders' card bridging of their bills and wages, per capita, since
            # card limits (14 Nov 2026) their cash advances.
            "card_bridging",
            # Card limits (decided 14 Nov 2026), records only, per capita where money: the cash-advance fees and
            # late fees charged, the card balances charged off and the lines closed by it (a count), the card-eligible
            # purchases past a holder's room that went the cash route, and the share of people behind on a minimum.
            "advance_fees", "late_fees", "charged_off", "lines_closed", "card_spilled", "card_delinquent",
            # The yardsticks (decided 3 and 4 Nov), per capita, records only (NaN outside the pool arms): the
            # pool's own margin and its parts (``MARGIN_PARTS``), the joint issuer-and-pool test, households' capital
            # in exit requests still unpaid after dealing, and the principal part of payments on written-off pool
            # loans.
            "own_margin", *("margin_" + key for key in MARGIN_PARTS), "joint", "owners_queued", "recovered_principal",
            # The term purchases among P payments (the 4 Nov review), count and value, per capita.
            "p_term_payments", "p_term_value",
            # Records only, read by no rule: completed purchases as a count a person a month, beside their value
            # (3 Nov: service and shock purchases at the share completed, and durables settled), and the largest
            # single pool loan outstanding and the largest pool debt of one borrower, each as a share of pool capital
            # at the close (12 Nov), NaN with no pool capital.
            *MEASURE_SERIES,
            # The pool run under the harsh stress (decided 15 Nov 2026), records only, per capita: the money offered
            # to the pool at the month's dealing and the part that found no room, the pool cash set aside for exits at
            # the close (cash not owed to creditors less the cash new loans may take), and the month's write-offs of
            # pool bridges and of pool term loans, which add up to written_off.
            "offers", "offers_unused", "exit_set_aside", "written_off_bridge", "written_off_term")}
        if economy.loan_losses == "sourced":
            # The loan-loss bound's records (decided 12 Nov), kept only under it, so a run without it is as built:
            # the principal discharged, and the coupon on pool term loans for business products (r_term is the
            # consumer class's under the bound).
            self.series.update({key: [] for key in (*LOAN_LOSS_SERIES, LOSS_CARRIED, "r_term_business")})
        # The bound's amount not yet discharged by class and lender group (13 Nov review): what the
        # loans on the book at a close could not absorb, carried to the next month's amount (``_loan_losses``).
        self.loss_carried = np.zeros((3, 2))
        # Person-level paths: net wealth after each month, participation, pool ownership, pool borrowing, receipts,
        # and (reported, decided 31 Oct) the failure fees each person paid and its new failed payments, a re-queued
        # wage not counted again, and the failure counts by person and month (3 Nov, ``FAILURE_COUNTS``).
        self.wealth_path = np.zeros((self.total + 1, n))
        self.status = np.zeros((self.total, n), bool)
        self.owner_path = np.zeros((self.total, n), bool)
        self.borrow_path = np.zeros((self.total, n), bool)
        self.receipts_path = np.zeros((self.total, n))
        self.fee_path, self.failed_path = np.zeros((self.total, n)), np.zeros((self.total, n))
        # Purchases by person and month (decided 11 Nov: claim (d) reads the wealth change plus purchases received),
        # records only, no rule reads them: as buyer, the service and shock purchases completed (amount times the
        # completed share) and lost (amount times the share not completed), and the price of each durable bought that
        # settled; as seller, the face value of the service and shock purchases completed to it, before any merchant
        # fee, plus the price of each durable it sold. Wages are in none of them. Each month the sum over people of
        # completed and durables equals the sum of sales.
        self.purchase_path = {key: np.zeros((self.total, n)) for key in ("completed", "durables", "lost", "sales")}
        # MicroVelocity (3 Nov), records only, no rule reads them: each person's sums over each year after launch (row
        # k holds launch months 12k to 12k + 11, the last row any part year), ``VELOCITY_RECORDS``. Its turnover in a
        # year on a definition of money is 12 x outflow / its own balance-time, in turns a year: a person holding 100
        # all year (balance-time 1,200 unit-months) that pays out 1,200 turns its money 12 times a year
        # (``turnover``); its MicroVelocity divides by everyone's balance-time instead (``microvelocity``, 13 Nov).
        self.velocity_path = {key: np.zeros((-(-economy.months // 12), n)) for key in VELOCITY_RECORDS}
        # MicroVelocity as its authors define it (13 Nov), records only, no rule reads them: the age of each person's
        # money (E, P and outside savings) by convention (``Coinage``). Each step's receipts (``coin_flow`` row 0),
        # removals that are not spending (row 1: pool shares bought, conversion fees not in the outflow), CPI's pro
        # rata loss of value (row 2) and the outflow are handed to it once a day (``_coin_day``); ``coin_open`` is the
        # stock at the last hand-over and ``coin_gap`` each person's unreconciled money this month, whose largest
        # absolute value a month is ``coin_residual``.
        self.coin = Coinage(self.cash + self.pcash + self.savings, self.total * DAYS, economy.burn_in * DAYS,
                            -(-economy.months // 12))
        self.coin_flow, self.coin_mark = np.zeros((3, n)), zeros()
        self.coin_open, self.coin_gap = self.cash + self.pcash + self.savings, zeros()
        self.coin_residual = np.zeros(self.total)
        # Credit by person and month (decided 11 Nov), records only, no rule reads them: who borrowed what from
        # whom, what was refused or cancelled, the interest accrued by lender, and wages paid late (``CREDIT_RECORDS``).
        self.credit_path = {key: np.zeros((self.total, n)) for key in CREDIT_RECORDS}
        self.failure_path = {key: np.zeros((self.total, n)) for key in FAILURE_COUNTS}
        # Reported (decided 3 Nov): each household's pool capital after dealing (with R, each owner's own realised
        # return, ``own_returns``) and its routine crossings between E and P, per month.
        self.owned_path, self.cross_path = np.zeros((self.total, n)), np.zeros((self.total, n))
        # What each owner's exit reads (``_own_return``, decided 3 Nov), kept apart from the records above so that
        # they stay records: each household's pool capital after dealing, and each month's R, never a loss beyond the
        # holding, NaN with no pool.
        self.held_path, self.r_owners = np.zeros((self.total, n)), np.full(self.total, np.nan)
        # Reported (the 3 Nov review): each person's buffer chosen at dealing, per month.
        self.buffer_path = np.zeros((self.total, n))
        # Earned-wage access (3 Nov): each person's payer-days with an advance, advances and their fees, per month.
        self.ewa_path = {key: np.zeros((self.total, n)) for key in ("uses", "value", "fees")}
        # What each person paid intermediaries outside the household economy each month, net of card rewards
        # (decided 31 Oct: the transfer report by payer): outside interest, failure fees, card fees as a seller,
        # conversion fees, gas on P and USDC payments (5 Nov), the spreads banks and issuers keep on its money and
        # savings and (3 Nov) earned-wage fees.
        self.transfer_path = np.zeros((self.total, n))
        # Cumulative per-person fee and charge flows, used to split each person's gain into channels. The charge is
        # demurrage on each holder's wallet P balance-time, withheld from its yield and paid to the pool (decided
        # 5 Nov).
        self.channels = {key: zeros() for key in ("merchant_paid", "rewards", "conversion_paid", "gas_paid",
                                                   "recirc_lenders", "charges")}
        self.payment_log = {}
        self.wealth_path[0] = self.net_wealth()
        # Wealth groups (DFA) rank total net worth, the illiquid part included.
        self.r_out = outside_return(self.wealth_path[0] + self.pop["illiquid"], inputs.rho_H, economy.n12,
                                    self.deposit_rate)
        # Each person's money market share of outside savings, and the rate their outside savings earn this month:
        # the blended outside rate, or rho_H when the deposit part stays in cash (where idle money sits, ``_dealing``).
        self.mm_share = money_market_share(self.wealth_path[0] + self.pop["illiquid"], economy.n12)
        self.saving_rate = self.r_out.copy()
        # One savings rule for every vehicle (decided 1 Nov): only the money-market part of savings can go to the
        # pool, so the alternative it is compared with, joining and leaving, is that part's own return, rho_H.
        self.pool_alternative = np.full(n, inputs.rho_H)

    # ----- accounts ---------------------------------------------------------------------------
    def net_wealth(self):
        """Every person's net financial wealth at current marks.

        Assets: E and P cash, outside savings, pool shares at NAV, invoices
        receivable. Liabilities: invoices payable, card balances, every loan
        (principal and accrued interest), pending overdraft and earned-wage
        advances owed (3 Nov). Durables bought on term credit are consumption
        here; they only enter the spending rule.
        """
        bk = self.book
        debt = np.bincount(bk["borrower"], weights=bk["principal"] + bk["interest"], minlength=self.n) + self.od_pending
        if self.economy.earned_wage_share > 0:
            # What each earner owes on advances against its jobs' wages, fee included (3 Nov).
            debt = debt + np.bincount(self.pop["wage_to"], weights=self.ewa_owed, minlength=self.n)
        return (self.cash + self.pcash + self.savings + self.shares * self.nav_ps + self.receivable - self.payable
                - self.card_unbilled - self.card_statement - debt)

    def _assets(self):
        """Pool assets behind NAV: pool cash plus the carrying value of pool loans (written-off loans carry zero)."""
        bk = self.book
        carried = bk["pool"] & bk["carried"]
        return self.pool_cash + (bk["principal"] + bk["interest"])[carried].sum() - self.pool_payable

    def _overdue(self, idx=None):
        """Term records' scheduled but unpaid amount (arrears): overdue principal plus due interest; ``idx`` None is
        the whole book, read without gathering it."""
        bk = self.book
        if idx is None:
            return _overdue_of(bk)
        scheduled = np.minimum(bk["instal"][idx] * bk["ndue"][idx], bk["original"][idx])
        owed = np.maximum(scheduled - (bk["original"][idx] - bk["principal"][idx]), 0.0)
        return np.where(bk["kind"][idx] == TERM, owed + bk["interest_due"][idx], 0.0)

    def _add_loans(self, borrower, pool, kind, principal, rate, alt, due, months=None, m0=0, card_part=0.0, cover=0.0,
                   business=False):
        """Append loans to the book.

        Bridges carry a due day (the covering date) and no instalments; term loans repay equal
        principal instalments over ``months`` starting the month after ``m0``
        with simple interest on the declining balance. ``m0`` is the month a
        term loan, a pool bridge or a cash advance is made; a bridge's is read
        only by the loan-year record (4 Nov), an advance's only by the
        replays' record of the card room (14 Nov 2026). ``card_part`` is the
        share of a pool bridge the real part counts as card credit (3 Nov;
        holders' bridges too, 14 Nov 2026), read only by the real part's
        records (``BOOK_FIELDS``). ``cover`` is the cut a month in a
        pool bridge's coupon that demurrage pays (4 Nov), read only by theta.
        ``business`` marks a term loan for a business product (decided
        12 Nov), read only by the loan-loss bound's class.
        """
        size = borrower.size
        if size == 0:
            return   # nothing to book (most calls in a day's settlement): the book is left as it is
        months = np.zeros(size, int) if months is None else months
        # Each field's value, a scalar or one per loan, written into the rows the loans take (``_append_book``).
        new = dict(borrower=borrower, pool=pool, kind=kind, principal=principal, interest=0.0, interest_due=0.0,
                   rate=rate, alt=alt, due=due, original=principal,
                   instal=np.where(months > 0, principal / np.maximum(months, 1), 0.0), ndue=0, months=months, m0=m0,
                   since=BIG, carried=True, card_part=card_part, cover=cover, business=business)
        self._append_book(new, size)

    def _book_is_stored(self):
        """Whether every book field is still the view of its backing array that ``_append_book`` made."""
        bk, store = self.book, self._book_store
        return (store is not None and store.keys() == bk.keys()
                and all(bk[key].base is store[key] for key in bk))

    def _append_book(self, new, size):
        """Append ``size`` loans to the book (``new``: each field's value, a scalar or one per loan).

        A speed device that changes no value: the book's fields are views of backing arrays with spare room, so a
        booking writes its rows in place instead of copying the whole book. Any book not built here (a fresh one from
        ``_compact``, a copied world, one a test sets) is first copied into new backing arrays.
        """
        bk = self.book
        length = bk["borrower"].size
        if not self._book_is_stored() or length + size > self._book_store["borrower"].size:
            room = 2 * (length + size) + 64
            fresh = {key: np.empty(room, value.dtype) for key, value in bk.items()}
            for key, value in bk.items():
                fresh[key][:length] = value
            self._book_store = fresh
        for key, field in self._book_store.items():
            field[length:length + size] = np.asarray(new[key], field.dtype)
        self.book = {key: field[:length + size] for key, field in self._book_store.items()}

    def _pool_factor(self, t, dates):
        """What one unit of pool principal drawn on day t costs to repay on each date, in E (loan-cost comparison).

        Simple interest for the days held at r_b, the rate a bridge drawn this
        month is sealed at (the coupon less demurrage's coverage of its capital
        part, decided 4 Nov). In M2 principal and
        coupon are P, whose E value rises by the index at every monthly CPI mark
        crossed (``_deflate`` runs at each month's close); elsewhere the index is 0.
        """
        return (1 + self.r_b * (dates - t) / DAYS) * (1 + self.index) ** (dates // DAYS - t // DAYS)

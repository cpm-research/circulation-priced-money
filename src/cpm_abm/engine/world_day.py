"""One day in its fixed order.

Earned wages accrued, arrears flags, instalments falling due, term purchases settling today, then the settlement
of every obligation due today and its failure counts.
"""
import numpy as np

from cpm_abm.engine.constants import (BIG, BRIDGE, BUSINESS_PRODUCT, CARD_REWARDS, CASH_ADVANCE, CASH_LINE_SHARE,
                                      CENT, CHARGED_OFF, DAYS, DTI_CAP, EPS, EWA_FEE, EWA_LIMIT, FAIL_FEE, FEE_DEBT,
                                      LABOUR_SHARE, LATE_OUTSIDE_WAGE, LATE_WAGE, OUTSIDE_WAGE, OVERDRAFT, ROUTE_CARD,
                                      ROUTE_E, ROUTE_P, SERVICE, SHOCK, SLOW_SWEEPS, TERM, WAGE)
from cpm_abm.engine.population import last_billing, next_billing
from cpm_abm.engine.lending_rules import limit_with_advance, limit_with_card, limit_with_fee
from cpm_abm.engine.ledger import _concat, _merge_sorted, allocate, in_order
from cpm_abm.engine.measures import netting_loss, netting_set, shortfall_split


class DayMixin:
    """One day in its fixed order, one part of ``_World``: earned wages, arrears flags, instalments, term purchases,
    and the settlement of every obligation due that day with its failure counts."""

    # ----- one day ----------------------------------------------------------------------------
    def day(self, month, d):
        """One day, in a fixed order.

        1. Arrears flags (read by today's credit eligibility).
        2. Instalments falling due today, collected from all cash.
        3. Term purchases settling today (own money, pool or outside loan).
        4. Today's payment obligations: routing, receipts, bridging, earned-wage
           advances, failures.
        5. The card statement on day 20, with its minimum payment and late fee
           (14 Nov 2026).
        6. The day's own cash flow is recorded for next month's buffer replay.
        7. Repayment from cash above the buffer: overdue wages, then debts.
           Before both, everything that is due (missed instalments, then
           bridges that have reached their due date) is collected from all
           the borrower's money (decided 12 Nov; ``_collect_due``).
        8. Overdrafts are booked, interest and costs accrue, write-offs apply,
           and a card 180 days past due is charged off (14 Nov 2026).
        9. In the pool arms, in the burn-in's last month, the bridging-need path
           is recorded (the launch plan's lending need).
        10. The day's crossings between E and P are counted (reported only).
        With earned-wage access (3 Nov), today's wages are first earned on
        every job not in a spell (``_accrue_wages``).
        """
        t = month * DAYS + d
        self._day_cache = {}
        cash_start = self.cash + self.pcash
        # Day accumulators: financing received, fees paid, merchant fees saved, card-eligible P payments,
        # discretionary term-purchase spending, unpaid obligations and same-day savings drawn (all per person).
        self.today = {key: np.zeros(self.n) for key in ("financing", "fees", "saved", "card_internal", "discretionary",
                                                         "unpaid", "savings")}
        if self.economy.earned_wage_share > 0:
            self._accrue_wages(t)
        self._arrears(t)
        self._instalments(t)
        self._term_purchases(t)
        self._settle(month, t)
        self._statement(d, t)
        today = self.today
        # The buffer replay sees every payment that fell due, paid or not, so a failure is a visible need next month;
        # savings drawn today are not income (the replay draws them itself). today["unpaid"] corrects the day's flow to
        # each payment's first due date, so a re-queued wage counts once (decided 3 Nov).
        flow = (self.cash + self.pcash - cash_start - today["financing"] - today["savings"] + today["discretionary"]
                - today["unpaid"])
        self.acc["flows"][:, d] = flow
        # The same day as it would have looked without P: no fees, merchant fees paid on what was received in P,
        # and card-eligible P payments deferred to the card statement on day 20 (the card float).
        self.acc["flows_s0"][:, d] = (flow + today["fees"] - today["saved"] + today["card_internal"]
                                      - (self.last["card_internal"] if d == 20 else 0.0))
        # What is due (a missed instalment, then a bridge that has reached its due date) ranks ahead of overdue wages
        # and of debts not yet due, as an instalment falling due does (decided 12 Nov): repaid first, the payer
        # keeps its pool credit and pays the next wage on time; paid after overdue wages, a payer with no buffer never
        # clears it and stays refused.
        self._collect_due(t)
        self._wage_arrears(np.maximum(self.cash + self.pcash - self.buffer, 0.0))
        self._repay(np.maximum(self.cash + self.pcash - self.buffer, 0.0))
        self._book_overdrafts()
        self._accrue()
        if self.pool_arm:
            # Demurrage pays for liquidity kept available (decided 5 Nov): the day's carried pool bridging principal
            # and the pool cash held ready, the cash new loans may take (``_cash_for_loans``: cash not owed to the
            # pool's creditors less the due exits the last dealing's unused offers would not cover, 12 Nov), at the
            # day's accruals, as the bridging principal-time counts them; next month's terms read the standby from
            # them (``_kept_ready``).
            bk = self.book
            bridge = bk["pool"] & bk["carried"] & (bk["kind"] != TERM)
            self.acc["bridge_day"][d] = float(bk["principal"][bridge].sum())
            self.acc["ready_day"][d] = self._cash_for_loans()
        self._write_off(t)
        self._charge_off(t)
        if self.pool_arm and month == self.economy.burn_in - 1:
            # The bridging need path, which only the launch plan reads, from the burn-in's last month.
            bk = self.book
            bridging = bk["kind"] == BRIDGE
            self.acc["bridge_path"][:, d] = (np.bincount(bk["borrower"][bridging], weights=bk["principal"][bridging],
                                                         minlength=self.n) + self.acc["failed_cum"])
        # Keep this the day's last statement (3 Nov): it closes the day's crossings, so a move between E and P added
        # after it would be counted with the next step's.
        self._count_crossings()
        self._day_cache = None
        if d < DAYS - 1:
            self._coin_day(t)   # a record only; the last day is handed over with the close (``month``)

    def _accrue_wages(self, t):
        """Earned-wage access (decided 3 Nov): each job not in a spell earns today's wage, the daily accrual its
        obligations were made of, so it is earned and still unpaid until its pay date (``_settle`` takes it out of the
        base when it falls due). A day's earnings count as earned that day, its pay date included:
        a reading of the rule (4 Nov)."""
        active = ~((self.spell_start <= t) & (t < self.spell_end))
        self.accrued += np.where(active, LABOUR_SHARE * self.spending / DAYS, 0.0)

    def _arrears(self, t):
        """Flag people in arrears with any lender (a bridge past its due date, or an overdue instalment; since card
        limits, 14 Nov 2026, a card minimum missed and not yet made up at a later statement, or a charged-off card
        balance still owed, as a written-off pool loan still owed keeps its borrower past due).

        Arrears block new pool credit and business term credit.
        """
        bk = self.book
        owed = bk["principal"] + bk["interest"] > EPS
        late = (((bk["kind"] == BRIDGE) & (bk["due"] < t) & owed) | (self._overdue() > EPS)
                | ((bk["kind"] == CHARGED_OFF) & owed))
        self.arrears = (np.bincount(bk["borrower"][late], minlength=self.n) > 0) | (self.card_late_since < BIG)

    def _instalments(self, t):
        """Instalments fall due on the borrower's first billing date on or after each month.

        The number due so far is computed from the last billing date, so a
        60-day biller can owe two instalments on one date. Due amounts are
        collected from all cash, then same-day savings; any unpaid part is
        overdue from today and is collected the same way at each day's end
        until it is paid (``_collect_due``, decided 12 Nov), and the loan
        is written off if it stays overdue 90 days.
        """
        bk = self.book
        idx = np.flatnonzero((bk["kind"] == TERM) & (bk["principal"] + bk["interest"] > EPS))
        if idx.size == 0:
            return
        who = bk["borrower"][idx]
        latest = last_billing(self.pop["cycles"][who], self.pop["phases"][who], t)
        ndue = np.clip(latest // DAYS - bk["m0"][idx], 0, bk["months"][idx])
        due = idx[ndue > bk["ndue"][idx]]
        bk["ndue"][due] = ndue[ndue > bk["ndue"][idx]]
        bk["interest_due"][due] = bk["interest"][due]
        owed = np.bincount(bk["borrower"][due], weights=self._overdue(due), minlength=self.n)
        self._use_savings(owed - np.maximum(self.cash + self.pcash, 0.0))
        self._pay(due, self._overdue(due), np.maximum(self.cash + self.pcash, 0.0))
        late = due[self._overdue(due) > EPS]
        bk["since"][late] = np.minimum(bk["since"][late], t)

    def _term_purchases(self, t):
        """Instalment purchases settling today.

        Funding order: own spare money above the buffer, then credit for the
        rest. Households need debt service within the 43% DTI cap, with one
        household's same-day requests sharing it in arrival order; firms must
        not be in arrears. Pool credit goes to participants not in arrears
        while the pool takes requests and its nominal-equivalent coupon is no
        dearer than the outside rate (the pool's lending in the paper's model
        section, paper/sections/model.tex), pro rata to pool cash; any
        unfunded part is refused (it counts toward capacity) and lent
        by the outside lender on the same schedule. A request that needs
        credit and does not qualify is cancelled. The purchase is a durable.
        """
        inputs, n, acc, r = self.inputs, self.n, self.acc, self.req
        lo, hi = np.searchsorted(r["settle"], [t, t + 1])
        if hi == lo:
            return
        sl = slice(lo, hi)
        b, s, price, rate, months = r["buyer"][sl], r["seller"][sl], r["price"][sl], r["rate"][sl], r["months"][sl]
        business = BUSINESS_PRODUCT[r["product"][sl]]
        order = np.arange(b.size)
        own = allocate(b, price, (order,), np.maximum(self.cash + self.pcash - self.buffer, 0.0))
        need = price - own
        bk = self.book
        term = bk["kind"] == TERM
        debt_service = np.bincount(bk["borrower"][term], weights=(bk["instal"] + bk["principal"] * bk["rate"])[term],
                                   minlength=n)
        # Debt service in the coming month: existing instalments plus interest, and the new loan at the outside rate.
        new = need / months + need * rate
        qualifies = np.where(business, ~self.arrears[b], debt_service[b] + new <= DTI_CAP * self.spending[b])
        # Same-day requests by one household share its limit (decided 30 Oct): in arrival order, the order its own
        # money was used in, each also counts the new debt service of its earlier requests today that qualified. Taken
        # rank by rank, every household's first request, then every second one, ...: each household's load adds the
        # same amounts in the same order as request by request.
        household = np.flatnonzero(~business)
        household = household[np.argsort(b[household], kind="stable")]
        place = np.arange(household.size)
        opens = np.concatenate([[True], b[household][1:] != b[household][:-1]])
        rank = place - np.maximum.accumulate(np.where(opens, place, 0))
        load = debt_service.astype(float)   # integer zeros when no term loan is on the book
        for r in range(int(rank.max()) + 1 if rank.size else 0):
            rows = household[rank == r]
            person = b[rows]
            qualifies[rows] = load[person] + new[rows] <= DTI_CAP * self.spending[person]
            load[person] += np.where(qualifies[rows], new[rows], 0.0)
        go = (need <= EPS) | qualifies
        eligible = (go & (need > EPS) & self.part[b] & self.asking & ~self.arrears[b]
                    & self._term_cheaper(rate, business))
        want = np.where(eligible, need, 0.0)
        capacity = self._cash_for_loans() if self.service else 0.0
        lend = want * min(1.0, capacity / want.sum()) if want.sum() > 0 else want
        acc["refused"] += float((want - lend).sum())
        acc["refused_term"] += float((want - lend).sum())   # the term part of the capital target (5 Nov)
        outside = np.where(go, need - lend, 0.0)
        # Records only (decided 11 Nov): the principal lent today by the pool and by the outside lender, and the
        # price of each request that needed credit and did not qualify, so was cancelled, by buyer.
        acc["credit_term_pool"] += np.bincount(b, weights=lend, minlength=n)
        acc["credit_term_outside"] += np.bincount(b, weights=outside, minlength=n)
        acc["credit_term_cancelled"] += np.bincount(b, weights=np.where(go, 0.0, price), minlength=n)
        price, own = np.where(go, price, 0.0), np.where(go, own, 0.0)
        # Under fee routing a term purchase is not card-eligible, so it is an E payment; under "all" routing, P,
        # whenever P is issued (3 Nov), at one transfer's gas (decided 5 Nov).
        p_route = self.part[b] & self.part[s] & self.launched & (self.economy.routing == "all")
        paid_p = (p_route & (price > EPS)).astype(float)
        gas = self.gas * paid_p
        np.add.at(self.pcash, b, lend)
        np.add.at(self.cash, b, outside)
        self._coin_in(lend + outside, b)   # a record only (``_coin_day``): the loans drawn
        before = self.acc["conversion"].copy()
        self._debit(np.bincount(b, weights=np.where(p_route, price + gas, 0.0), minlength=n),
                    np.bincount(b, weights=np.where(p_route, 0.0, price), minlength=n))
        self._cover()
        np.add.at(self.today["discretionary"], b, own)
        np.add.at(self.today["fees"], b, gas)
        self.today["fees"] += self.acc["conversion"] - before
        self._pay_gas(b, gas)
        self.pool_cash -= lend.sum()
        # A term purchase paid in P is a P payment, counted among P payments, which the real part's P rail prices, and
        # kept apart too (the 4 Nov review).
        acc["p_n"] += float(paid_p.sum())
        acc["p_value"] += float((price * p_route).sum())
        acc["p_term_n"] += float(paid_p.sum())
        acc["p_term_value"] += float((price * p_route).sum())
        self._receive(s, price, p_route)
        # A record only (decided 11 Nov): the price of each durable that settled, received by its buyer and sold
        # by its seller; a cancelled request has price 0 here.
        np.add.at(acc["bought_durables"], b, price)
        np.add.at(acc["sold"], s, price)
        acc["durables_n"] += float((price > EPS).sum())   # a record only (3 Nov): durables settled, a count
        m0 = t // DAYS
        take = lend > EPS
        # Each loan marks whether its product is a business one (a record, decided 12 Nov: the loan-loss class).
        self._add_loans(b[take], True, TERM, lend[take], self._term_coupon(business[take]), rate[take], BIG,
                        months[take], m0, business=business[take])
        take = outside > EPS
        self._add_loans(b[take], False, TERM, outside[take], rate[take], rate[take], BIG, months[take], m0,
                        business=business[take])
        acc["new_term_pool"] += float(lend.sum())
        acc["new_term_outside"] += float(outside.sum())
        acc["new_pool_loans"] += float((lend > EPS).sum())
        bought = go & (price > EPS)
        self.durable = _concat(self.durable, dict(owner=b[bought], value=price[bought],
                                                  step=price[bought] / months[bought], left=months[bought]))
        acc["borrowed"] |= np.bincount(b[lend > EPS], minlength=n) > 0

    def _term_coupon(self, business):
        """The pool's term coupon a month for each loan: r_term, and for a business product r_term_business, which
        differs only under the loan-loss bound (decided 12 Nov: each class carries its own sourced rate)."""
        return np.where(business, self.r_term_business, self.r_term)

    def _term_cheaper(self, rate, business):
        """Loan-cost comparison for instalment credit: pool terms no dearer than the outside rate, month by month.

        Instalment loans run whole months, so each month the pool's P balance
        costs its term coupon (``_term_coupon``) and, in M2, one month's
        indexation: (1 + r_term)(1 + index) against 1 + the outside monthly rate.
        """
        return (1 + self._term_coupon(business)) * (1 + self.index) <= 1 + rate

    def _settle(self, month, t):
        """Settle every obligation due today.

        Routing: P between participants for fee-saving payments (or USDC with
        gas in M0), card for other card-eligible purchases by holders, E
        otherwise. A holder whose own money cannot pay the day's payments puts
        that day's card purchases on the card. Card limits (decided 14 Nov
        2026): card purchases go on the card up to the holder's room on its
        line, smallest first, and the rest goes the cash route, in P where P
        could carry it, else E. Shortfalls are paid first from
        the payer's outside savings the same day (decided 30 Oct), then
        financed in order: pool draw (participants, pro rata to pool cash),
        Comet against collateral (M0), a cash advance on the card (holders, up
        to the cash line within the room, at the cash APR and its fee; 14 Nov
        2026), earned-wage
        access (3 Nov: up to half of the payer's wages earned and still unpaid,
        repaid first from those wages; holders too since card limits), else
        the payment fails. Today's
        receipts, net of the advances today's wages repay at source, can fund
        today's payments; a few fixed-point sweeps settle the circular
        dependence.
        A failed service or shock purchase is lost; a failed wage is re-queued
        to its job's next pay date. An extra layoff's wage (14 Nov 2026: the
        harsh stress) is settled by its payer as a wage and received by
        nobody. Every failed bill or wage carries the flat
        failure fee once, at most one fee a payer a day and ``fees_a_month``
        a month (3 Nov), booked as interest-free fee debt repaid first; a
        failed card-eligible purchase carries none.
        """
        inputs, n, acc = self.inputs, self.n, self.acc
        lo, hi = np.searchsorted(self.ob["settle"], [t, t + 1])
        sl = slice(lo, hi)
        b, s, amt = self.ob["buyer"][sl], self.ob["seller"][sl], self.ob["amount"][sl]
        crd, kind = self.ob["card"][sl], self.ob["kind"][sl]
        # The harsh stress (decided 14 Nov 2026): an extra layoff's wage (``sink``) is settled as a wage by its
        # payer, fee-bearing the first time and re-queued while unpaid, but paid out of the household economy: nobody
        # receives it, so it is no receipt, no wage paid, no earned-wage room and never a P payment. ``requeued_row``
        # marks the re-queued wages of both kinds.
        sink = (kind == OUTSIDE_WAGE) | (kind == LATE_OUTSIDE_WAGE)
        requeued_row = (kind == LATE_WAGE) | (kind == LATE_OUTSIDE_WAGE)
        # Routing (decided 21 Oct): P where it saves the card fee, i.e. card-eligible purchases by card holders;
        # routing="all": every payment between participants in P.
        fee_saving = crd & self.holder[b] if self.economy.routing == "fee" else ~sink
        # Gas on Base, the same for every payment whatever its value (decided 5 Nov): two legs a USDC payment in
        # M0, one transfer a P payment, and no provider fee (P payments run on stablecoin rails); written as a rate on
        # each payment's own value. P payments do not depend on the pool (3 Nov): they settle whenever P is issued, in
        # the pool arms from launch.
        rail_fee = self.gas / np.maximum(amt, EPS)
        p_route = self.part[b] & self.part[s] & (self.launched | self.defi) & fee_saving
        # The October 2026 draft's fee lock, applied to gas: a payment's gas comes from funds the payer already owns.
        # A payer that cannot fund today's gas settles those payments outside P instead (by card, or E under routing
        # "all").
        owned = np.maximum(self.cash + self.pcash, 0.0)
        fees_due = np.bincount(b, weights=rail_fee * amt * p_route, minlength=n)
        p_route = p_route & (owned >= fees_due - EPS)[b]
        # A card holder whose own money cannot pay the day's payments puts that day's card purchases on the card,
        # free until the statement is due as in S0, rather than borrowing for them (decided 29 Oct).
        payments = np.bincount(b, weights=amt * (1 + rail_fee * p_route), minlength=n)
        p_ready = p_route
        p_route = p_route & ~(crd & (self.holder & (owned < payments - EPS))[b])
        card = crd & self.holder[b] & ~p_route
        # Card limits (decided 14 Nov 2026): the day's card purchases go on the card up to the holder's room on its
        # line, whole purchases smallest first (``in_order``); the rest goes the cash route, funded like any payment, in
        # P where P could carry it before the short holder's purchases went to the card, else E, and if it still
        # cannot be paid it is declined without a fee. What the card takes leaves the room the cash line reads.
        line_room = room_before = self._card_room()
        if card.any():
            fits = np.zeros(b.size, bool)
            fits[card] = in_order(b[card], amt[card]) <= line_room[b[card]] + EPS
            spilled = card & ~fits
            card = card & fits
            p_route = p_route | (spilled & p_ready)
            line_room = line_room - np.bincount(b[card], weights=amt[card], minlength=n)
        else:
            spilled = card
        cash_room = self._cash_room(line_room)
        cash_route = ~card
        need_p = np.bincount(b, weights=amt * (1 + rail_fee) * p_route, minlength=n)
        need_e = np.bincount(b, weights=amt * (cash_route & ~p_route), minlength=n)
        need = need_p + need_e
        # The seller pays the 1.7% merchant fee on card purchases, to the card network and issuers (31 Oct).
        merchant = inputs.f_card * amt * card
        received = amt - merchant
        received[sink] = 0.0   # an extra layoff's wage leaves the household economy: its payee receives nothing
        card_rec = np.bincount(s[card], weights=received[card], minlength=n)
        # Who may ask the pool, and the collateralised share Comet can lend (M0).
        eligible = self.part & self.asking & ~self.arrears
        comet = self.part * self.cover
        # Covering-date budget: the receipts of the next two months left after the debts that rank ahead of the pool,
        # and what one unit of each financing costs by the last receipt date in that horizon (12 Nov: wages expected
        # on their jobs' pay dates, other receipts on own billing dates).
        _, spare_rec, _, last = self._c1_budget(t)
        f_pool = self._pool_factor(t, last)
        f_card = 1 + self.card_apr * (last - t) / DAYS
        # A cash advance costs its APR to that date and its fee, the greater of the floor and the rate on it, which goes
        # on the card's purchase balance at the purchase APR (14 Nov 2026).
        f_cash = 1 + self.cash_apr * (last - t) / DAYS
        card_fee = lambda advanced: np.where(advanced > EPS,
                                             np.maximum(self.advance_floor, self.advance_rate * advanced), 0.0)
        line_open = cash_room > EPS
        # Each holder's cash room today, gross of the month's own advances still owed, kept by day for the replays (14
        # Nov 2026), since the replay's path takes the month's shortfalls itself: an advance repaid within the month
        # has given its room back already, so it is not added again (the review), and the room is never above the cash
        # line. Hand case: a $1,000 line takes a $200 advance on day 3, repaid on day 10; day 11 records $200, not $400.
        this_month = ~self.book["pool"] & (self.book["kind"] == CASH_ADVANCE) & (self.book["m0"] == month)
        acc["card_room"][:, t - month * DAYS] = np.minimum(cash_room + self._card_owed(this_month),
                                                           CASH_LINE_SHARE * self.card_line)
        # Fixed for the day's sweeps (no sweep moves money): each payer's own money, the pool's cash for loans, and the
        # cash-route payments' payees, payers and receipts.
        money = self.cash + self.pcash
        capacity = self._cash_for_loans() if self.service else 0.0
        s_cash, b_cash, received_cash = s[cash_route], b[cash_route], received[cash_route]
        # The failure fee (decided 30 Oct): a flat fee per failed bill or wage, at most one a payer a day; a failed
        # card-eligible purchase is declined without one, and a re-queued wage carries none. A payer completes the same
        # share of each of its payments today, so a payment left partly unpaid counts as that share of a failed
        # payment: until the cap, a unit of the payer's need that fails costs the fee times its fee-bearing payments
        # over its need. Fee debt bears no interest (decided 3 Nov; as built, it grew at r_ext to the covering
        # horizon). At most fees_a_month fees a payer a model month (3 Nov): today's cap is one fee or what the month
        # still allows, whichever is less, and the pool's same-day limit counts that capped fee exactly.
        fee_bearing = cash_route & ~crd & ~requeued_row
        count = np.bincount(b, weights=fee_bearing.astype(float), minlength=n)
        grow = np.ones(n) if self.economy.fee_debt_free else 1 + inputs.r_ext * (last - t) / DAYS
        f_fail = FAIL_FEE * count / np.where(need > EPS, need, 1.0) * grow   # the fee debt per failed unit
        monthly_cap = np.isfinite(self.economy.fees_a_month)
        left = np.maximum(self.economy.fees_a_month - acc["fee_units"], 0.0)   # fee units the month still allows
        cap_today = FAIL_FEE * grow * np.minimum(left, 1.0) if monthly_cap else FAIL_FEE * grow
        fee_debt = lambda fail: np.minimum(fail * f_fail, cap_today)         # at most one fee, and the month's rest
        ewa = self.economy.earned_wage_share > 0
        if ewa:
            # Earned-wage access (decided 3 Nov). Wages falling due today leave the base; what remains is earned and
            # still unpaid: accrued wages and a job's failed wages re-queued to a later date (that these count is
            # a reading of the rule (4 Nov)), on a job not in a spell today, for an earner who holds
            # access. The room is half of that base less the advances already owed against it, the fee left out, since
            # the half limits the advance and not its fee: a reading of the rule (4 Nov). Holders
            # reach it too since card limits (decided 14 Nov 2026), after their cash line. Instalments, term
            # purchases and the card statement draw no advance, only today's bills, wages and purchases settled here:
            # a reading of the rule (4 Nov). A wage paid to the outside (14 Nov 2026) was never earned
            # by its worker, so it is in neither the base nor the wages that repay advances.
            wage_row = (kind == WAGE) | (kind == LATE_WAGE)
            np.subtract.at(self.accrued, b[kind == WAGE], amt[kind == WAGE])
            self.accrued = np.maximum(self.accrued, 0.0)
            ob, wage_to = self.ob, self.pop["wage_to"]
            requeued = (ob["kind"] == LATE_WAGE) & (ob["settle"] > t)
            late = np.bincount(ob["buyer"][requeued], weights=ob["amount"][requeued], minlength=n)
            usable = ~((self.spell_start <= t) & (t < self.spell_end)) & self.pop["ewa"][wage_to]
            base = np.where(usable, self.accrued + late, 0.0)
            room_job = np.maximum(EWA_LIMIT * base - self.ewa_owed / (1 + EWA_FEE), 0.0)
            room = np.bincount(wage_to, weights=room_job, minlength=n)
            room = np.where(room <= EPS, 0.0, room)
            any_room = bool((room > EPS).any())
            # Each earner's room, gross of the month's advances, is kept by day for the replays.
            acc["ewa_room"][:, t - month * DAYS] = np.bincount(wage_to, weights=EWA_LIMIT * base, minlength=n)
            wage_amt = amt * wage_row

        ewa_room = room if ewa else np.zeros(n)

        def receipts(f):
            """Each payee's receipts today when the payers complete the shares ``f``."""
            rec = card_rec + np.bincount(s_cash, weights=received_cash * f[b_cash], minlength=n)
            if ewa:
                # Advances owed at the start of the day are repaid first from today's wages of their own job, so no
                # earner spends that part of its wage (``_repay_advances`` books it).
                wage_paid = wage_amt * f[b]
                by_job = np.bincount(b, weights=wage_paid, minlength=n)
                repaid = np.divide(np.minimum(self.ewa_owed, by_job), by_job, out=np.zeros(n), where=by_job > EPS)
                rec = rec - np.bincount(s, weights=wage_paid * repaid[b], minlength=n)
            return rec

        def sweep(state, allowed):
            """Receipts from today's completions, then pool, the card's cash advance, earned-wage access and
            failures. It moves no money and changes nothing outside itself."""
            rec = receipts(state["f"])
            # Same-day savings (decided 30 Oct) pay what own money and today's receipts cannot.
            gap = np.maximum(need - (money + rec), 0.0)
            used = np.minimum(gap, self.savings)
            short = gap - used
            # The pool lends only what the receipts repay with its coupon after every debt ranked ahead of it,
            # including whatever finances the rest of today's shortfall, however capacity rations it. Without a card
            # the rest fails and leaves its fee debt, at most one fee and the month's rest, so the pool lends what is
            # repaid after that debt. A card holder's rest goes to its cash line, repaid first, up to its room, and
            # only what is beyond it fails (decided 14 Nov 2026: the holder's test is partial,
            # ``limit_with_card``); a holder with no room left on its cash line is read as a payer without a card.
            limit = limit_with_fee(short, spare_rec, f_pool, f_fail, cap_today)
            if ewa and any_room:
                # With earned-wage room the rest is advanced up to the room, repaid first from the wage with its fee,
                # and only what is left fails, so the receipts must repay the draw after the advance and that fee debt.
                limit = np.where(room > EPS, limit_with_advance(short, spare_rec, f_pool, f_fail, cap_today, room,
                                                                1 + EWA_FEE), limit)
            # Read only where it can matter, payers the pool may serve that are short today (a speed device: the limit
            # of anyone else enters nothing).
            pick = np.flatnonzero(line_open & allowed & (short > 0))
            if pick.size:
                limit[pick] = limit_with_card(short[pick], spare_rec[pick], f_pool[pick], f_fail[pick],
                                              cap_today[pick], cash_room[pick], f_cash[pick], self.advance_floor,
                                              self.advance_rate, f_card[pick], ewa_room[pick], 1 + EWA_FEE)
            want = np.where(allowed, np.minimum(short, limit), 0.0)
            total = want.sum()
            draw = want * (min(1.0, capacity / total) if total > 0 else 0.0)
            secured = comet * (short - draw)  # M0: collateralised Comet borrowing for the covered share
            cash = np.minimum(short - draw - secured, cash_room)   # the card's cash advance, up to its cash line
            if ewa:
                # Earned-wage access after the card's cash line, before failure (3 Nov; holders too, 14 Nov 2026).
                advance = np.minimum(short - draw - secured - cash, room)
                fail = short - draw - secured - cash - advance
            else:
                fail = short - draw - secured - cash
            f = np.where(need > 0, 1.0 - fail / np.where(need > 0, need, 1.0), 1.0)
            # Reported (decided 31 Oct): what the pool refuses a payer whose rest would partly fail (without a card,
            # or beyond a holder's cash line, 14 Nov 2026) although the loan alone would be repaid, because the
            # receipts would not also cover the fee were capacity to ration the draw.
            refused = np.where(allowed & (cash_room < short) & (short * f_pool <= spare_rec),
                               short - np.minimum(short, limit), 0.0)
            out = dict(f=f, draw=draw, cash=cash, fail=fail, want=want, secured=secured, used=used, short=short,
                       fee_refused=refused, fails_screen=(short > EPS) & (limit <= EPS))
            if ewa:
                out["advance"] = advance
            return out

        first = {}   # the latest sweep started from every payer completing in full

        def fixed_point(allowed):
            """Find each payer's completed share and return the remaining queue.

            Receipts depend on others' f. Only a fixed point makes the receipts
            that financed each payment equal those actually posted. If two
            states repeat, a request that fails the repayment check in either
            state and qualifies in the other is deferred for the day. At the
            sweep cap a day whose completions move by no more than EPS of money
            is settled (14 Nov 2026); otherwise the cap is an error.
            """
            full = dict(f=np.ones(n))
            flow = previous = None
            sweeps = 0

            def slow(state, used):
                """Counts a day that needed more than SLOW_SWEEPS sweeps (decided 14 Nov 2026), and the most used."""
                if used > SLOW_SWEEPS:
                    self.acc["slow_days"] += 1
                self.acc["most_sweeps"] = max(self.acc["most_sweeps"], used)
                return state

            while True:
                if flow is None:
                    flow = sweep(full, allowed)
                    first["full"] = flow   # kept for the own-shortfall record (below), read by no rule
                    sweeps += 1
                following = sweep(flow, allowed)
                sweeps += 1
                change = float(np.abs(following["f"] - flow["f"]).max())
                if change <= 1e-14:
                    return slow(following, sweeps), allowed
                if sweeps >= self.economy.sweeps:
                    # At the cap, a day whose completions still move by no more than EPS of money is at its fixed point
                    # up to rounding (14 Nov 2026): a payer whose amount due is tiny (the remainder of a re-queued wage)
                    # has its completed share moved by the rounding of its receipts, which no sweep removes, while the
                    # money it moves is nil. Only a day that would otherwise stop is read so, so no other day changes.
                    if float((np.abs(following["f"] - flow["f"]) * need).max()) <= EPS:
                        return slow(following, sweeps), allowed
                    # What the error names (14 Nov 2026), so a failed day can be read without rerunning it: whether the
                    # last sweeps repeat two states, and the payers whose completion or request still moves.
                    back = (float(np.abs(following["f"] - previous["f"]).max()) if previous is not None
                            else float("nan"))
                    moving = np.flatnonzero(np.abs(following["f"] - flow["f"]) > 1e-14)
                    asks = np.flatnonzero(np.abs(following["want"] - flow["want"]) > EPS)
                    among = np.isin(b, moving) & np.isin(s, moving)   # the movers' payments to each other today
                    raise RuntimeError(
                        f"Day {t}: settlement did not reach its fixed point in {sweeps} sweeps. "
                        f"Arm={self.arm}, seed={self.economy.seed}, n={n}, a0={self.a0}, "
                        f"r_out={12 * inputs.rho_H:.12g}, distress={self.economy.distress}, "
                        f"lender income recirculated={self.economy.lender_income_recirculated}. "
                        f"Largest change in payment completion in the last sweep: {change:.6g}; against the sweep "
                        f"before: {back:.6g}. Payers whose completion moves: {moving[:12].tolist()} "
                        f"({moving.size} in all); whose pool request moves: {asks[:12].tolist()} ({asks.size}); "
                        f"of them holders {asks[self.holder[asks]][:12].tolist()}, screened out in either sweep "
                        f"{asks[(following['fails_screen'] | flow['fails_screen'])[asks]][:12].tolist()}. The movers "
                        f"hold a card: {self.holder[moving][:12].tolist()}; their money: {money[moving][:12].tolist()}; "
                        f"their amounts due today: {need[moving][:12].tolist()}; "
                        f"their payments to each other today: {int(among.sum())}, in P {int((among & p_route).sum())}, "
                        f"by card {int((among & card).sum())}, past a holder's room {int((among & spilled).sum())}, "
                        f"of kinds {np.bincount(kind[among], minlength=6).tolist()}; their other payments: "
                        f"{int((np.isin(b, moving) & ~among).sum())}."
                    )
                if previous is not None and float(np.abs(following["f"] - previous["f"]).max()) <= 1e-14:
                    # A request can use enough of the pool to cut the receipts that made it qualify (6 Nov).
                    defer = allowed & (((flow["want"] > EPS) & following["fails_screen"])
                                       | ((following["want"] > EPS) & flow["fails_screen"]))
                    if defer.any():
                        allowed = allowed & ~defer
                        flow = previous = None
                        continue
                previous, flow = flow, following

        # Same-day financing repaid before the pool: the card's cash advance and its fee, Comet bridging, and the fee
        # debt on failures.
        comet_rate = self.comet_borrow
        ahead = lambda flow: (flow["cash"] * f_cash + card_fee(flow["cash"]) * f_card
                              + flow["secured"] * (1 + comet_rate * (last - t) / DAYS) + fee_debt(flow["fail"]))
        if ewa:
            # An earned-wage advance and its fee are repaid from the wage before the pool (3 Nov).
            debts = ahead
            ahead = lambda flow: debts(flow) + flow["advance"] * (1 + EWA_FEE)
        # Loan-cost comparison: a card holder borrows from the pool only if, on the draw's own covering date,
        # repaying it costs no more than a cash advance on the part its room could take (14 Nov 2026), and a payer
        # with earned-wage room and no cash line only if it costs no more than the advance (3 Nov). Payers whose draw
        # would be dearer leave the pool's queue and the day is settled again; the queue only shrinks, so this ends.
        held = room if ewa else None
        flow, eligible = fixed_point(eligible)
        dearer = self._dearer(flow["draw"], t, ahead(flow), held, cash_room)
        while dearer.any():
            eligible = eligible & ~dearer
            flow, eligible = fixed_point(eligible)
            dearer = self._dearer(flow["draw"], t, ahead(flow), held, cash_room)
        f, draw, cash, fail = flow["f"], flow["draw"], flow["cash"], flow["fail"]
        secured = flow.get("secured", np.zeros(n))
        self._chain_records(flow, first["full"], receipts, b, b_cash, s_cash, received_cash,
                            amt * cash_route, amt * (cash_route & ~requeued_row), need, money, card_rec)
        # The part of each payer's pool draw that paid in place of failing (records only, the review of 14 Nov 2026):
        # without the draw a holder's cash line would take the shortfall up to its room, so it is what the draw took
        # of the rest; for a payer without a card, whose room is zero, the whole draw.
        rescued = np.minimum(draw, np.maximum(flow["short"] - cash_room, 0.0))
        done = np.where(card, 1.0, f[b])
        self._receive(s, received * done, p_route)
        # Each job's wages paid to its recipient, on time or late: next month's budget expects them on that job's pay
        # dates (decided 12 Nov).
        wage_paid = received * done * ((kind == WAGE) | (kind == LATE_WAGE))
        acc["wages_paid"] += np.bincount(b, weights=wage_paid, minlength=n)
        # A record only (decided 11 Nov): service and shock purchases completed and lost by their buyers, and
        # completed to their sellers at face value, before the merchant fee. Wages are not purchases.
        purchase = (kind == SERVICE) | (kind == SHOCK)
        completed = amt * done * purchase
        acc["bought_completed"] += np.bincount(b, weights=completed, minlength=n)
        acc["bought_lost"] += np.bincount(b, weights=amt * (1 - done) * purchase, minlength=n)
        acc["sold"] += np.bincount(s, weights=completed, minlength=n)
        # A record only (3 Nov): how many purchases completed, a partly completed one counted at its completed share,
        # as completed P payments are counted.
        acc["bought_n"] += float((done * purchase).sum())
        if ewa:
            # Today's wages repay the advances owed against them before they reach their earners, and the replay sees
            # the whole wage; today's advances are paid in E and are financing, not trade.
            repaid = self._repay_advances(b[wage_row], s[wage_row], (received * done)[wage_row], p_route[wage_row])
            advance = flow["advance"]
            self.cash += advance
            self._coin_in(advance)   # a record only (``_coin_day``)
            self.today["financing"] += advance - repaid
        self.pcash += draw + secured
        self.cash += cash
        self._coin_in(draw + secured + cash)   # a record only (``_coin_day``): the credit drawn
        self.today["financing"] += draw + cash + secured
        self._use_savings(flow["used"])
        before = acc["conversion"].copy()
        self._debit(need_p * f, need_e * f)
        self._cover()
        gas = rail_fee * amt * done * p_route
        self._pay_gas(b, gas)
        self.pool_cash -= draw.sum()
        # The card fee leaves the economy (the boundary rule, 31 Oct); the buyer earns card rewards on the purchase,
        # paid at the close. Payments by rail are counted for the real-part report: card payments, and completed P
        # (USDC in M0) payments.
        acc["merchant"] += np.bincount(s, weights=merchant, minlength=n)
        self.external -= float(merchant.sum())
        acc["rewards"] += np.bincount(b, weights=CARD_REWARDS * amt * card, minlength=n)
        acc["card_n"] += float(card.sum())
        acc["card_value"] += float(amt[card].sum())
        acc["p_n"] += float((done * p_route).sum())
        acc["p_value"] += float((amt * done * p_route).sum())
        # The merchant fee a seller avoided because the buyer paid in P: a transfer, reported as a channel. In S0 a
        # holder's card-eligible purchase paid in P would have gone on its card only where its room could take it with
        # the day's other card-eligible purchases, whole purchases smallest first, as the card route takes them (the
        # review, 14 Nov 2026); past the room S0 pays it by debit, with no merchant fee and no float to its buyer.
        in_s0 = np.ones(b.size, bool)
        if (p_route & crd).any():
            held = crd & self.holder[b]
            in_s0[held] = in_order(b[held], amt[held]) <= room_before[b[held]] + EPS
        saved = inputs.f_card * amt * done * p_route * crd * self.holder[b] * in_s0
        acc["merchant_saved"] += np.bincount(s, weights=saved, minlength=n)
        self.today["fees"] += np.bincount(b, weights=gas, minlength=n) + acc["conversion"] - before
        self.today["saved"] += np.bincount(s, weights=saved, minlength=n)
        card_internal = np.bincount(b, weights=amt * done * p_route * crd * self.holder[b] * in_s0, minlength=n)
        self.today["card_internal"] += card_internal
        acc["card_internal"] += card_internal
        np.add.at(self.card_unbilled, b[card], amt[card])
        acc["card_spilled"] += float(amt[spilled].sum())   # card purchases past the room (a record only, 14 Nov 2026)
        # Bridging is booked in repayment order: Comet bridging first, due on its covering date (outside debt is repaid
        # first, dated at its own nominal rate), and the card's cash advances, with no due date (14 Nov 2026), then
        # pool draws, whose dates count the same day's outside financing and fee debt.
        who = np.flatnonzero(secured > EPS)
        self._add_loans(who, False, BRIDGE, secured[who], comet_rate, self.card_apr[who],
                        self._due_c1(who, secured[who], t, np.full(who.size, comet_rate)))
        self._book_advances(cash, t)
        # Reported (3 Nov, for the S0 check): holders' card bridging of what their money could not pay, since card
        # limits their cash advances (14 Nov 2026), against US cash advances. No rule reads it.
        acc["card_bridging"] += float(cash.sum())
        acc["comet_bridging"] += float(secured.sum())   # a record only (5 Nov)
        acc["credit_bridge_card"] += cash               # the same two, by payer (records only, decided 11 Nov)
        acc["credit_bridge_comet"] += secured
        acc["credit_advance_card"] += cash              # the cash advances alone (records only, 14 Nov 2026)
        took = draw > EPS
        who = np.flatnonzero(took)
        if ewa:
            # Today's advance and its fee rank ahead of the draw too (3 Nov); the advance is booked below, after the
            # draw's date, so it is not counted twice.
            due = self._due_c1(who, draw[took], t, ahead=(fee_debt(flow["fail"]) + advance * (1 + EWA_FEE))[took])
        else:
            due = self._due_c1(who, draw[took], t, ahead=fee_debt(flow["fail"])[took])
        # Reported (3 Nov): the share of the draw of a payer without a card that paid its card-eligible purchases, new
        # lending rather than a replaced failure. The draw pays the same share of each payment, so it is their share of
        # the payer's need (each with its rail fee in P). No rule reads it. For a holder (the review, 14 Nov 2026) the
        # share the real part counts as card credit is the part of the draw its cash line would otherwise have taken,
        # and of the part that paid in place of failing, the share that paid purchases past its room, read as a payer
        # without a card's purchases are; the rest the real failure line counts, so no dollar is counted twice. Hand
        # case: a $150 draw for a $150 bill with $50 of room counts $50 as card credit and $100 as bridged.
        bought = crd & cash_route & (~self.holder[b] | spilled)
        purchases = np.bincount(b, weights=amt * (1 + rail_fee * p_route) * bought, minlength=n)
        share = purchases / np.where(need > EPS, need, 1.0)
        card_part = np.where(self.holder, np.divide(draw - rescued * (1 - share), draw, out=np.zeros(n),
                                                    where=draw > EPS),
                             np.where(need > EPS, share, 0.0))
        # Dated by the month made, which only the loan-year record reads for a bridge (4 Nov). Sealed at this month's
        # bridging rate r_b, the coupon less the part of its capital part demurrage pays (decided 4 Nov).
        self._add_loans(who, True, BRIDGE, draw[took], self.r_b, self.card_apr[took], due, m0=t // DAYS,
                        card_part=card_part[took], cover=self.r_g - self.r_b)
        acc["new_pool_loans"] += float(took.sum())
        acc["bridges"] += float(draw.sum())
        # Payer-days with a pool bridge to a payer without a card (the real part's count as built).
        acc["nocard_bridges"] += float((took & ~self.holder).sum())
        acc["want"] += flow["want"]
        acc["drawn"] += draw
        acc["refused"] += float((flow["want"] - draw).sum())
        acc["refused_bridging"] += float((flow["want"] - draw).sum())   # the peak bridging need's part (5 Nov)
        acc["fee_refused"] += float(flow["fee_refused"].sum())
        acc["fee_refused_n"] += float((flow["fee_refused"] > EPS).sum())
        acc["borrowed"] |= took
        if ewa:
            # Each earner's advance is owed against its jobs, with its fee, spread over them by their room
            # (a reading of the rule (4 Nov)), and repaid from those jobs' wages; the fee goes to
            # the provider, outside the economy, and is still owed if the wage fails. A use is a payer-day with an
            # advance.
            per_room = np.divide(advance, room, out=np.zeros(n), where=room > EPS)
            self.ewa_owed += per_room[wage_to] * room_job * (1 + EWA_FEE)
            fee = EWA_FEE * advance
            self.external -= float(fee.sum())
            acc["ewa_uses"] += advance > EPS
            acc["ewa_value"] += advance
            acc["ewa_fees"] += fee
        # Failures (decided 30 Oct): the flat fee on each failed bill or wage, or its unpaid share, at most one a
        # payer a day and fees_a_month a model month (3 Nov), once per obligation, booked as fee debt (no interest,
        # repaid first; as built, outside debt at r_ext); a service or shock purchase is lost, an unpaid wage stays
        # owed and is re-queued to its job's next pay date (as built, the recipient's next billing date). The payer's
        # fee-bearing payments and need are counted for its average payment, next month's price of the fee in the
        # buffer choice. An extra layoff's wage (14 Nov 2026) is a wage here: re-queued while unpaid, still owed, and
        # out of the failure share's failed and due; it was nobody's receivable.
        wage = (kind == WAGE) | (kind == LATE_WAGE) | sink
        unpaid = amt * (1 - done) * cash_route
        if self.economy.requeued_once:
            # Each obligation once, on the day it first fell due (decided 3 Nov): a re-queued wage adds nothing to
            # the replay's flow when it fails again, and what it pays on a later date is taken back out of that day's
            # flow; the paid case is a reading of the rule (4 Nov).
            timing = np.where(requeued_row, -amt * done * cash_route, unpaid)
        else:
            timing = unpaid
        self.today["unpaid"] += np.bincount(b, weights=timing, minlength=n)
        requeue = wage & (done < 1 - EPS)
        settled = amt * np.where(wage, done, 1.0)
        np.subtract.at(self.receivable, s, np.where(sink, 0.0, settled))
        np.subtract.at(self.payable, b, settled)
        acc["due_n"] += count
        acc["due_amt"] += need
        unpaid_shares = np.bincount(b, weights=(1 - done) * fee_bearing, minlength=n)
        units = np.minimum(unpaid_shares, 1.0)
        if monthly_cap:
            # The month's fee count in shares of a fee, so a day can carry a fractional last fee:
            # a reading of the rule (4 Nov).
            units = np.minimum(units, left)
        acc["fee_units"] += units
        penalty = FAIL_FEE * units
        who = np.flatnonzero(penalty > EPS)
        if self.economy.fee_debt_free:
            self._add_loans(who, False, FEE_DEBT, penalty[who], 0.0, 0.0, BIG)
        else:
            self._add_loans(who, False, OVERDRAFT, penalty[who], inputs.r_ext, inputs.r_ext, BIG)
        self.external -= penalty.sum()
        acc["penalties"] += float(penalty.sum())
        acc["fee"] += penalty
        acc["failed_new"] += np.bincount(b, weights=unpaid * ~requeued_row, minlength=n)
        acc["failed_cum"] += np.bincount(b, weights=amt * (1 - done) * cash_route, minlength=n)
        acc["failed"] += float((amt * (1 - done))[cash_route & ~wage].sum())
        acc["wage_failed"] += float((amt * (1 - done))[kind == WAGE].sum())
        # The same by payer (a record only, decided 11 Nov): a wage not paid on its first due date, once.
        acc["credit_wages_late"] += np.bincount(b, weights=amt * (1 - done) * (kind == WAGE), minlength=n)
        acc["due"] += float(amt[~wage].sum())
        # Records only (14 Nov 2026): an extra layoff's wage not paid on its first due date, in a record of its own, so
        # the wage arrears keep their meaning; and the failure share's failed and due of hit workers as payers.
        acc["wage_out_failed"] += float((amt * (1 - done))[kind == OUTSIDE_WAGE].sum())
        hit = acc["hit"][b] & ~wage
        acc["failed_hit"] += float((amt * (1 - done))[cash_route & hit].sum())
        acc["due_hit"] += float(amt[hit].sum())
        # The failure counts (3 Nov), from the money this settlement paid each payer, read before today's amounts are
        # cleared. Each payment takes its amount (with the rail fee in P) from its payer's money, nothing by card.
        # A holder's draw replaces a failure only beyond what its cash line could take (14 Nov 2026): without the draw
        # the cash line would take the shortfall up to its room, so the draw paid in place of failing what it took of
        # the rest, min(draw, shortfall less room), whether the pool lent the whole shortfall or part of it (the
        # review); for a payer without a card that is the whole draw. Hand case: a $300 bill, $100 of room and a draw
        # of $145.05 paid $145.05 in place of failing, of $200 that would have failed.
        self._count_failures(b, np.where(cash_route, amt * (1 + rail_fee * p_route), 0.0), cash_route, crd,
                             fee_bearing, done, need * f, rescued, need, count, unpaid_shares, spilled)
        if month in (self.economy.burn_in, self.total - 1):
            # The payment network's log: an extra layoff's wage pays nobody in the household economy, so it is left out.
            route = np.where(p_route, ROUTE_P, np.where(card, ROUTE_CARD, ROUTE_E))
            acc["log"].append(np.stack([b, s, amt * done, route])[:, ~sink])
        back = (amt * (1 - done))[requeue]
        self.ob["amount"][sl] = 0.0  # settled, lost or re-queued: no entry is paid twice
        if requeue.any():
            seller = s[requeue]
            if self.economy.pay_dates:
                # To the job's next pay date (as built, the recipient's next billing date):
                # a reading of the rule (4 Nov).
                job = b[requeue]
                later = next_billing(self.pop["pay_days"][job], self.pop["pay_phase"][job], t, strict=True)
            else:
                later = next_billing(self.pop["cycles"][seller], self.pop["phases"][seller], t, strict=True)
            # Inserted in settle order, as a stable sort of the list with them appended would place them. An extra
            # layoff's wage is re-queued as a wage paid to the outside still (14 Nov 2026).
            again = np.full(seller.size, LATE_WAGE)
            again[sink[requeue]] = LATE_OUTSIDE_WAGE
            self.ob = _merge_sorted(self.ob, dict(buyer=b[requeue], seller=seller, amount=back, settle=later,
                                                  card=np.zeros(seller.size, bool), kind=again))

    def _chain_records(self, flow, full, receipts, b, b_cash, s_cash, received_cash, face, fresh, need, money,
                       card_rec):
        """Two records of one day's settlement (the robustness plan, section 4), read by no rule: no random number is
        drawn, no money moves and nothing the model reads is written.

        ``flow`` is the day's final solution and ``full`` the first sweep of the settlement that reached it, started
        from every payer completing in full under the day's final pool queue; ``receipts`` maps completed shares to
        receipts as the sweeps compute them. ``face`` and ``fresh`` are each payment's face value on the cash route,
        and the same for payments not yet re-queued; ``need``, ``money`` and ``card_rec`` are each payer's cash-route
        payments due with their rail fees, its own money at the start of settlement and its card receipts.

        Own shortfall and knock-on (``shortfall_split``): each payer's failed amount at face value, a wage counted on
        the day it first falls due, as the month's failures (``failed_new``) count it; the own-shortfall part is the
        share of its need it fails in ``full``, at the same face value. Dependence on netting (``netting_set``,
        ``netting_loss``): the members complete at least a cent of the cash-route payments they have due (rounding
        remainders of a payment are not payments), hold no own money and no outside savings, draw no pool, Comet, cash-advance or earned-wage credit today and receive
        nothing by card; values are completed face value on the cash route.
        """
        acc, n, f = self.acc, self.n, flow["f"]
        failed = np.bincount(b, weights=fresh * (1 - f[b]), minlength=n)
        own = np.divide(full["fail"], need, out=np.zeros(n), where=need > 0) * np.bincount(b, weights=fresh,
                                                                                           minlength=n)
        split = shortfall_split(failed, own)
        acc["own_shortfall"] += split["own"]
        acc["knock_on"] += split["knock_on"]
        acc["knock_on_positive"] += split["knock_on_positive"]
        acc["own_shortfall_n"] += split["own_n"]
        acc["knock_on_n"] += split["knock_on_n"]
        acc["knock_on_days"][split["bin"]] += 1
        value = np.bincount(b, weights=face, minlength=n)
        acc["cash_completed"] += float(value.dot(f))
        advance = flow.get("advance", np.zeros(n))
        candidate = ((need * f >= CENT) & (np.abs(money) <= EPS) & (self.savings <= EPS) & (card_rec <= EPS)
                     & (flow["draw"] <= EPS) & (flow["secured"] <= EPS) & (flow["cash"] <= EPS) & (advance <= EPS))
        if not candidate.any():
            return
        inside = netting_set(candidate, b_cash, s_cash, received_cash * f[b_cash])
        if not inside.any():
            return
        means = money + flow["used"] + flow["draw"] + flow["secured"] + flow["cash"] + advance
        lost, _ = netting_loss(f, inside, means, need, receipts, value)
        acc["netting_days"] += 1
        acc["netting_n"] += int(inside.sum())
        acc["netting_value"] += float(value[inside].dot(f[inside]))
        acc["netting_lost"] += lost

    def _count_failures(self, b, cost, cash_route, crd, fee_bearing, done, paid, draw, need, count, unpaid_shares,
                        spilled=None):
        """Failure counts by payer for one settlement (decided 3 Nov), reported only: no rule reads them.

        A payer's bills and wages each count their unpaid share once, capped at one a day in fail_units as the fee is
        and without a cap in fail_shares. Whole items are the fewest of the payer's payments today that a bank paying
        whole payments would return from the money this settlement paid them (``in_order``): the engine pays every
        payment the same share, so this counts on today's path and settles nothing. The pool's draw pays the same
        share of each of a payer's payments: for a payer without a card, in place of failing for its bills and wages,
        and as new lending for its card-eligible purchases. ``cost`` is what each payment takes from its payer's money,
        ``paid`` and ``need`` what the settlement paid and owed each payer's payments, and ``count`` its bills and
        wages that can carry the fee. Since card limits (14 Nov 2026) ``draw`` is the part of each payer's pool draw
        that replaced a failure, for a holder what its cash line could not have taken, and ``spilled`` flags the card
        purchases past a holder's room, which compete and are declined as a payer without a card's are. No random
        number is drawn and no money moves.
        """
        acc, n = self.acc, self.n
        # Re-queued wages compete for the day's money but are never counted again, in failures or in bridges; a payer
        # without a card has its card-eligible purchases compete in the same pass, counted apart as declined with no
        # fee (decided 4 Nov), and so do a holder's purchases past its room (14 Nov 2026).
        nocard = ~self.holder
        purchases = crd & cash_route & (nocard[b] if spilled is None else nocard[b] | spilled)
        within = in_order(b, cost)
        # Only a payer left short returns a payment; one the draw paid is bridged if it would be returned without it.
        # Only the pool's draw counts as a bridge, as in nocard_bridges, not M0's Comet borrowing against collateral
        # (none at collateral cover 0), as decided 4 Nov.
        short, bridging = need - paid > EPS, draw > EPS
        returned = cash_route & short[b] & (within > paid[b] + EPS)
        rescued = cash_route & ~returned & bridging[b] & (within > (paid - draw)[b] + EPS)
        bridged = np.where(bridging & (need > EPS), draw / np.where(need > EPS, need, 1.0), 0.0)
        items = lambda flag: np.bincount(b, weights=flag, minlength=n)
        acc["fail_units"] += np.minimum(unpaid_shares, 1.0)
        acc["fail_shares"] += unpaid_shares
        acc["fail_items"] += items(returned & fee_bearing)
        acc["fail_days"] += unpaid_shares > EPS
        acc["declined_shares"] += items((1 - done) * purchases)
        acc["declined_items"] += items(returned & purchases)
        acc["bridged_shares"] += count * bridged
        acc["bridged_items"] += items(rescued & fee_bearing)
        acc["bridged_card"] += items(purchases) * bridged

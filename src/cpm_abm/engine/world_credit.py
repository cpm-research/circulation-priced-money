"""Credit on the books.

The outside card (statement, balances, room on the line, cash advances, the card's lender, minimum payment, late
fee, charge-off), each day's interest and costs, the pool's lendable cash, gas, owners' alternative, inflation in
real units and the book's housekeeping, and loan losses at sourced rates with write-offs of loans long past due.
"""
import numpy as np

from cpm_abm.engine.constants import (BIG, BRIDGE, CARD_MINIMUM_FLOOR, CARD_MINIMUM_SHARE, CASH_ADVANCE,
                                      CASH_LINE_SHARE, CHARGE_OFF_DAYS, CHARGED_OFF, DAYS, EPS, EXIT_NOTICE_MONTHS,
                                      FEE_DEBT, LATE_FEE, LATE_FEE_CYCLES, LATE_FEE_REPEAT, LATE_OUTSIDE_WAGE,
                                      LOAN_YEARS, LOSS_CLASSES, LOSS_LAG, OUTSIDE_WAGE, OVERDRAFT, REVOLVE, TERM,
                                      WRITE_OFF_DAYS)
from cpm_abm.engine.rates import charge_off_rates
from cpm_abm.engine.lending_rules import limit_with_revolve
from cpm_abm.engine.ledger import _concat, _is_kind, _take


class CreditMixin:
    """Credit on the books, one part of ``_World``: the outside card, each day's interest and costs, the pool's
    lendable cash, gas, owners' alternative, inflation in real units and loan losses with write-offs."""

    def _statement(self, d, t):
        """The card statement (closed on day 29 of last month) is due on day 20.

        It is paid from cash, then same-day savings; a participant's unpaid part is a pool draw (borrowed P redeemed
        to pay the card issuer); the rest revolves at the holder's card APR. The minimum payment is due with it
        (``_minimum_due``); what the day's payment, the pool's draw and the payments on the card since the last
        statement leave of it is collected from all money, and what is still unpaid is past due and costs the late fee
        (``_minimum_paid``).

        Under each holder's own date (``Economy.statement_dates`` "own") the same happens on each person's own due
        day, 21 days after its own closing day (``_close_statements``), for the people due today only (``on``);
        everyone else's statement, minimum and card terms are left as they are. Example: a holder closing on day 3 is
        due on day 24 of the same month, one closing on day 15 on day 6 of the next, and one closing on day 29 on day
        20 of the next, as under the default.
        """
        if self.economy.statement_dates == "common":
            if d != 20:
                return
            on = None
        else:
            on = self.card_due == d
            if not on.any():
                return
        acc = self.acc
        due = self.card_statement.copy() if on is None else np.where(on, self.card_statement, 0.0)
        minimum = self._minimum_due(due)
        if on is not None:
            minimum = np.where(on, minimum, 0.0)
        before = acc["conversion"].copy()
        mult = 1 + self._rate()
        self._use_savings(due - (np.maximum(self.cash, 0.0) + np.maximum(self.pcash, 0.0) / mult))
        pay = np.minimum(np.maximum(self.cash, 0.0) + np.maximum(self.pcash, 0.0) / mult, due)
        self._debit(np.zeros(self.n), pay)
        self._card_edge(paid=pay)   # a payment to the card clears its fees and interest first
        remaining = due - pay
        # Budget: whatever the pool does not pay revolves on the card and is repaid first, and while the minimum is
        # unmet the late fee is owed too, so the pool pays a statement only if the receipts of the next
        # two months repay all of it at card terms and that fee, however capacity rations it (``limit_with_revolve``).
        # Under each holder's own date only the people due today may ask, so only their debts are read.
        _, spare_rec, _, last = self._c1_budget(t, on, statement=True)
        f_card = 1 + self.card_apr * (last - t) / DAYS
        capacity = self._cash_for_loans() if self.service else 0.0
        unmet = np.maximum(minimum - pay, 0.0)                          # what own money leaves of the minimum
        late = np.where(unmet > EPS, self._late_fee(minimum, t), 0.0)  # the fee missing it would cost
        limit = limit_with_revolve(remaining * mult, spare_rec, self._pool_factor(t, last), f_card, unmet * mult, late)
        asking = self.part & self.asking & ~self.arrears
        if on is not None:
            asking = asking & on
        share = lambda want: want * (min(1.0, capacity / want.sum()) if want.sum() > 0 else 0.0)
        want = np.where(asking, np.minimum(remaining * mult, limit), 0.0)
        draw = share(want)
        ahead = lambda draw: (remaining - draw / mult) * f_card + np.where(draw / mult < unmet - EPS, late, 0.0)
        # Loan-cost comparison: the pool pays the statement only where it is no dearer than revolving on the card
        # at the draw's covering date; the queue only shrinks, so this ends.
        dearer = self._dearer(draw, t, ahead(draw), statement=True)
        while dearer.any():
            asking = asking & ~dearer
            want = np.where(asking, np.minimum(remaining * mult, limit), 0.0)
            draw = share(want)
            dearer = self._dearer(draw, t, ahead(draw), statement=True)
        acc["want"] += want
        acc["drawn"] += draw
        acc["refused"] += float((want - draw).sum())
        acc["refused_bridging"] += float((want - draw).sum())   # the peak bridging need's part
        self.pcash += draw
        self._coin_in(draw)   # a record only (``_coin_day``)
        self._debit(np.zeros(self.n), draw / mult)
        self._card_edge(paid=draw / mult)   # the pool's draw pays the card in cash too
        self._cover()
        self.pool_cash -= draw.sum()
        took = draw > EPS
        who = np.flatnonzero(took)
        # Dated by the month made, which only the loan-year record reads for a bridge, and sealed at this month's
        # bridging rate r_b, as a bridge for a bill is. The whole draw replaces revolving on the card, so the real
        # part counts all of it as card credit.
        self._add_loans(who, True, BRIDGE, draw[took], self.r_b, self.card_apr[took],
                        self._due_c1(who, draw[took], t, ahead=ahead(draw)[took], statement=True), m0=t // DAYS,
                        card_part=1.0,
                        cover=self.r_g - self.r_b)
        acc["new_pool_loans"] += float(took.sum())
        acc["bridges"] += float(draw.sum())
        acc["borrowed"] |= took
        revolve = remaining - draw / mult
        who = np.flatnonzero(revolve > EPS)
        self._add_loans(who, False, REVOLVE, revolve[who], self.card_apr[who], self.card_apr[who], BIG)
        acc["revolved"] += float(revolve[who].sum())   # a record only
        np.add.at(acc["credit_bridge_card"], who, revolve[who])   # by holder (a record only)
        if on is None:
            self.card_statement[:] = 0.0
        else:
            self.card_statement[on] = 0.0
        # The minimum counts the day's payment, the pool's draw and every payment on the card's balances since the last
        # statement (a payment received before the due date counts towards it).
        self._minimum_paid(minimum, pay + draw / mult + self.card_paid, t, on)
        # The conversion paid on the statement and on the minimum collected from P is the day's fee, as in settlement.
        self.today["fees"] += acc["conversion"] - before

    def _card_rows(self):
        """The loan book's card balances: each outside revolving balance (statements left to revolve and the card's
        fees) and cash advance, and an outside bridge sealed at its borrower's own card rate (no rule books one
        now)."""
        bk = self.book
        return ~bk["pool"] & (_is_kind(bk["kind"], (REVOLVE, CASH_ADVANCE))
                              | ((bk["kind"] == BRIDGE) & (bk["rate"] == bk["alt"])))

    def _card_owed(self, rows):
        """What each person owes on the book's ``rows`` (a mask), principal and interest."""
        bk = self.book
        return np.bincount(bk["borrower"][rows], weights=(bk["principal"] + bk["interest"])[rows], minlength=self.n)

    def _card_room(self):
        """Each holder's room on its line now: the line less its starting balance, the card purchases of this month and
        the last statement not yet paid, and every card balance on the book, principal and interest; zero for anyone
        without an open line, never below zero."""
        room = (self.card_line - self.card_start - self.card_unbilled - self.card_statement
                - self._card_owed(self._card_rows()))
        return np.where(self.holder, np.maximum(room, 0.0), 0.0)

    def _cash_room(self, room):
        """The most each holder can take as a cash advance today out of ``room``, its room on the line after today's
        card purchases: at most its cash line, 20% of its line less its cash advances outstanding, and with the
        advance's fee, the greater of the floor and the rate on it, still within the room.
        Example: a $1,000 line with nothing owed has a cash line of $200 and takes $200 with its $10 fee; with $150
        of room left it takes $140, the fee its $10 floor; with $8 it takes nothing."""
        advances = self._card_owed(~self.book["pool"] & (self.book["kind"] == CASH_ADVANCE))
        with_fee = np.minimum(room - self.advance_floor, room / (1 + self.advance_rate))
        return np.where(self.holder, np.maximum(np.minimum(CASH_LINE_SHARE * self.card_line - advances, with_fee),
                                                0.0), 0.0)

    def _book_advances(self, cash, t):
        """Book today's cash advances ``cash`` by payer: each a card balance of its own kind at the cash APR, with no
        due date, repaid from money above the buffer dearest first; its fee, the greater of the floor and the rate on
        it, goes on the card's purchase balance at the purchase APR (a fee on the purchase balance leans against
        CPM), is charged by the card's lender, outside the economy (``_card_lender``), and is one of the fees the next
        minimum payment adds."""
        took = cash > EPS
        who = np.flatnonzero(took)
        # Dated by the month taken, which only the replays' record of the card room reads.
        self._add_loans(who, False, CASH_ADVANCE, cash[took], self.cash_apr[took], self.cash_apr[took], BIG,
                        m0=t // DAYS)
        fee = np.where(took, np.maximum(self.advance_floor, self.advance_rate * cash), 0.0)
        charged = np.flatnonzero(fee > EPS)
        self._add_loans(charged, False, REVOLVE, fee[charged], self.card_apr[charged], self.card_apr[charged], BIG)
        self._card_lender(fee)
        self.card_fees += fee
        acc = self.acc
        acc["advance_fees"] += float(fee.sum())
        acc["advance_fee_i"] += fee
        acc["credit_fees_card"] += fee
        acc["credit_fees_advance"] += fee   # the cash-advance fees alone (records only, the cash-advance bound)

    def _card_lender(self, fees):
        """The card's fees, ``fees`` by holder, go to its lender outside the economy, or under the recirculation stress
        back to households at the close with outside lenders' interest: the runner counts them in outside lenders'
        income. Each fee is a debt on the card when it is charged (``_edge_debt``), held in the card's own tracker of
        fees and interest not yet paid (``_card_edge``)."""
        total = float(fees.sum())
        if self.economy.lender_income_recirculated:
            self.sector["lenders"] += total
        else:
            self.external -= total
            self._edge_debt(fees)
            self._card_edge(fees)

    def _edge_debt(self, owed):
        """Book money that crosses the edge when a debt to the outside is created, not when cash moves: ``owed`` by
        person, the outside interest accrued, the card's fees, the failure fee, the earned-wage fee and the wages owed
        outside. A record only (``edge_accrued``); ``external`` is booked by the caller, and what is still owed is read
        from each liability (``_edge_owed``). Example: a day's $10 of card interest adds $10 to the month's
        ``edge_accrued``."""
        acc = getattr(self, "acc", None)
        if acc is not None and "edge_accrued" in acc:
            acc["edge_accrued"] += float(owed.sum())

    def _card_edge(self, charged=None, paid=None):
        """The card's fees and interest charged and not yet paid, by holder, the one part of the stock owed across the
        edge the engine does not carry apart: the card's fees join its revolving balance and its interest is merged
        with it. ``charged`` adds to the tracker; ``paid``, a cash payment to the card (on its balances, its
        charged-off balance or its statement, the pool's draw for a statement included), clears it first, as a card
        lender applies a payment to fees and interest before principal. No other payment clears it. Example: $10 of
        interest charged, then a $50 statement paid: the tracker is $10, then $0; a $4 payment would leave $6."""
        if not hasattr(self, "card_edge_owed"):
            return
        if charged is not None:
            self.card_edge_owed = self.card_edge_owed + charged
        if paid is not None:
            self.card_edge_owed = self.card_edge_owed - np.minimum(self.card_edge_owed, np.maximum(paid, 0.0))

    def _edge_discharged(self, amount):
        """Record an amount that leaves the stock owed across the edge because its liability is discharged, not paid:
        the card's share of a discharged balance, or the pool's payable when a wound-down pool is closed. A record
        only (``acc["edge_discharged"]``); it keeps the month's cash reconciliation exact (``edge_cleared``)."""
        acc = getattr(self, "acc", None)
        if acc is not None and "edge_discharged" in acc:
            acc["edge_discharged"] += amount

    def _edge_owed(self):
        """Each person's stock owed across the edge and not yet paid, read liability by liability from what the engine
        carries: the interest accrued on its loans from outside lenders other than the card, its fee debt, the card's
        fees and interest not yet paid (``_card_edge``, at most what the card is owed), the earned-wage fees still owed
        with their advances, and the wages it owes outside. A payment on one liability clears only that liability, and
        one discharged leaves the stock. Example: $100 owed as a wage outside and a separate loan whose principal is
        paid: $100 until the wage itself is paid."""
        bk, n = self.book, self.n
        outside = ~bk["pool"]
        card = self._card_rows() | (bk["kind"] == CHARGED_OFF)
        on_card = outside & card
        card_owed = np.bincount(bk["borrower"][on_card], weights=(bk["principal"] + bk["interest"])[on_card],
                                minlength=n)
        # The card's tracker never exceeds what the card is owed, so a balance discharged takes its part with it; the
        # cap is kept in the tracker itself.
        capped = np.minimum(self.card_edge_owed, card_owed)
        self._edge_discharged(float((self.card_edge_owed - capped).sum()))
        self.card_edge_owed = capped
        loans = outside & ~card
        accrued = np.where(bk["kind"] == FEE_DEBT, bk["principal"] + bk["interest"], bk["interest"])
        stock = np.bincount(bk["borrower"][loans], weights=accrued[loans], minlength=n) + self.card_edge_owed
        stock = stock + np.bincount(self.pop["wage_to"], weights=self.ewa_fee_owed, minlength=n)
        ob = self.ob
        wages = (ob["kind"] == OUTSIDE_WAGE) | (ob["kind"] == LATE_OUTSIDE_WAGE)
        return stock + np.bincount(ob["buyer"][wages], weights=ob["amount"][wages], minlength=n)

    def _minimum_due(self, statement):
        """Each holder's minimum payment due today with ``statement``, the purchases it bills: on the balance, the
        statement and every card balance on the book, principal and interest, the greater of $40, or the whole balance
        if smaller, and 1% of it plus the interest and fees charged since the last statement and the minimum then
        left unpaid, never above the balance; zero without an open line or a balance.
        Example: a $5,000 balance with $90 of interest and no fee owes $140; a $2,000 one with $20 of interest, $40;
        a $25 one, $25."""
        balance = statement + self._card_owed(self._card_rows())
        due = np.maximum(np.minimum(CARD_MINIMUM_FLOOR, balance), CARD_MINIMUM_SHARE * balance + self.card_interest
                         + self.card_fees + self.card_past_due)
        return np.where(self.holder & (balance > EPS), np.minimum(due, balance), 0.0)

    def _late_fee(self, minimum, t):
        """The late fee a missed ``minimum`` costs today: $30, or $41 for a repeat within the next six billing cycles
        of the last late fee, never above the minimum due."""
        repeat = t // DAYS - self.card_late_month <= LATE_FEE_CYCLES
        return np.minimum(np.where(repeat, LATE_FEE_REPEAT, LATE_FEE), minimum)

    def _minimum_paid(self, minimum, paid, t, on=None):
        """Settle each holder's ``minimum`` after the statement has been ``paid`` (own money, the pool's draw and every
        payment on the card's balances since the last statement), on day 20. What it leaves is collected from all
        money, then same-day savings, on the card's balances, dearest first; what is still unpaid is past due, the
        card is delinquent from the first such due date until a later minimum is paid in full, which blocks pool
        credit (``_arrears``) and at 180 days charges it off (``_charge_off``), and the late fee goes on the purchase
        balance at the purchase APR, charged by the card's lender, outside the economy (``_card_lender``). The next
        minimum starts its interest, fees and payments from here. Example: a holder that paid $1,500 on its revolving
        balance on day 5 and holds $10 on day 20 has met a $40 minimum, so no fee is charged and the card stays
        current. Under each holder's own date ``on`` marks the people due today: only their delinquency, amount past
        due and terms since the last statement are reset here; None is everyone."""
        short = np.maximum(minimum - paid, 0.0)
        if (short > EPS).any():
            self._use_savings(short - np.maximum(self.cash + self.pcash, 0.0))
            budget = np.minimum(short, np.maximum(self.cash + self.pcash, 0.0))
            bk = self.book
            live = self._card_rows() & (bk["principal"] + bk["interest"] > EPS)
            # Under own dates only the balances of the people due today are offered, so no rounding of the allocation
            # reaches anyone else's.
            rows = np.flatnonzero(live if on is None else live & on[bk["borrower"]])
            self._pay(rows, bk["principal"][rows] + bk["interest"][rows], budget)
            short = short - budget
        missed = short > EPS
        late = np.where(missed, self._late_fee(minimum, t), 0.0)
        who = np.flatnonzero(late > EPS)
        if who.size:
            self._add_loans(who, False, REVOLVE, late[who], self.card_apr[who], self.card_apr[who], BIG)
            self._card_lender(late)
            acc = self.acc
            acc["late_fees"] += float(late.sum())
            acc["late_fee_i"] += late
            acc["credit_fees_card"] += late
        self.card_late_month = np.where(late > EPS, t // DAYS, self.card_late_month)
        if on is None:
            self.card_late_since = np.where(missed, np.minimum(self.card_late_since, t), BIG)
            self.card_past_due = np.where(missed, short, 0.0)
            self.card_fees, self.card_interest, self.card_paid = late, np.zeros(self.n), np.zeros(self.n)
            return
        self.card_late_since = np.where(on, np.where(missed, np.minimum(self.card_late_since, t), BIG),
                                        self.card_late_since)
        self.card_past_due = np.where(on, np.where(missed, short, 0.0), self.card_past_due)
        self.card_fees = np.where(on, late, self.card_fees)
        self.card_interest = np.where(on, 0.0, self.card_interest)
        self.card_paid = np.where(on, 0.0, self.card_paid)

    def _close_statements(self, d):
        """Close the card statements whose closing day is today, at the day's end (``Economy.statement_dates`` "own";
        under the default, "common", every statement closes after day 29 in ``month`` and this does nothing): the card
        purchases since the last close go on the statement, due 21 days later (``_statement``), and the day's
        card-eligible P payments join the cycle the buffer replay's view without P defers to that due day
        (``_s0_deferred``). No money moves. Example: a holder closing on day 9 with $120 of card purchases on days 10
        to 29 of last month and $80 on days 0 to 9 of this one has a statement of $200 at the end of day 9, due on
        day 0 of the next month, and its purchases of day 10 go on the next statement."""
        if self.economy.statement_dates == "common":
            return
        self.s0_unbilled += self.today["card_internal"]
        closing = self.card_close == d
        self.card_statement[closing] += self.card_unbilled[closing]
        self.card_unbilled[closing] = 0.0
        self.s0_statement[closing] += self.s0_unbilled[closing]
        self.s0_unbilled[closing] = 0.0

    def _s0_deferred(self, d):
        """The card-eligible P payments the buffer replay's view without P pays today, at the statement due date (the
        card float): under the default, on day 20, last month's (``last["card_internal"]``); under each holder's own
        date, on each person's own due day, those of its cycle that closed 21 days earlier, then cleared. Zero on any
        other day."""
        if self.economy.statement_dates == "common":
            return self.last["card_internal"] if d == 20 else 0.0
        due = self.card_due == d
        deferred = np.where(due, self.s0_statement, 0.0)
        self.s0_statement[due] = 0.0
        return deferred

    def _charge_off(self, t):
        """Charge off every card 180 days past due: its line closes for the rest of the run,
        so its holder holds no card from now on, and every balance on it, the book's card balances and the purchases
        not yet paid, stays owed at no further interest as a charged-off balance, with no due date, repaid from money
        above the buffer and keeping its borrower in arrears while owed. No money moves: the debt changes kind, not
        size. The population's own flag, which fixes each person's class, is unchanged."""
        hit = self.holder & (t - self.card_late_since >= CHARGE_OFF_DAYS)
        if not hit.any():
            return
        bk, acc = self.book, self.acc
        rows = self._card_rows() & hit[bk["borrower"]]
        balance = self._card_owed(rows) + self.card_statement + self.card_unbilled
        bk["kind"][rows], bk["rate"][rows], bk["alt"][rows] = CHARGED_OFF, 0.0, 0.0
        unpaid = np.where(hit, self.card_statement + self.card_unbilled, 0.0)
        who = np.flatnonzero(unpaid > EPS)
        self._add_loans(who, False, CHARGED_OFF, unpaid[who], 0.0, 0.0, BIG)
        self.card_statement[hit], self.card_unbilled[hit] = 0.0, 0.0
        self.holder[hit], self.card_line[hit] = False, 0.0
        self.card_late_since[hit], self.card_past_due[hit], self.card_fees[hit], self.card_interest[hit] = BIG, 0, 0, 0
        self.card_paid[hit] = 0.0
        acc["charged_off"] += float(balance[hit].sum())
        acc["lines_closed"] += float(hit.sum())
        acc["credit_charged_off_card"] += np.where(hit, balance, 0.0)

    def _accrue(self):
        """One day of accruals.

        * Simple interest on every loan (written-off pool loans stop accruing).
          Outside interest is an outside flow (or recirculated under the
          lender-income stress); pool interest is owners' income.
        * The pool's operating cost o on carried principal, paid to its
          operating provider outside the economy.
        * Principal-time and the borrowers' savings on term credit against
          their outside rates (inputs to experience and the charge's rate).
        * P balance-time (the base of P's yield and of demurrage, paid at the
          close), each person's lowest P balance (idle P's measure, a
          record), the issuer's reserve base and the pool's own P cash, and
          the coupon cut demurrage pays on carried pool bridges.
        * M0: USDC's savings rate (or Comet supply interest) on participants'
          USDC. Everyone: the checking yield on E.
        * For the real-part and transfer reports: principal-time of card and
          term credit, balance-time of savings and pool shares, and the
          spreads banks and issuers keep on households' money and savings;
          and the principal-time of the part of pool bridges to payers
          without a card that paid card-eligible purchases. Fee debt accrues
          nothing (its rate is 0).
        """
        inputs, acc, bk, n = self.inputs, self.acc, self.book, self.n
        # Legal interest accrues on every loan, written off or not (paper/cpm.tex, section (Loss learning): impairment
        # changes carrying value, not principal or rate). On a written-off pool loan the legal claim grows while its
        # carrying value stays zero, so the borrower's extra liability is a valuation change.
        accrual = bk["principal"] * bk["rate"] / DAYS
        bk["interest"] += accrual
        pool, term = bk["pool"], bk["kind"] == TERM
        # Once a term loan's last instalment has fallen due, all its accrued interest is due: the interest that
        # accrues while the final instalment is overdue is collected with it, and the loan clears when paid.
        # Example: a 2-month loan whose second instalment is paid a month late pays that month's interest too.
        final = term & (bk["ndue"] >= bk["months"])
        bk["interest_due"][final] = bk["interest"][final]
        self.valuation -= float(accrual[pool & ~bk["carried"]].sum())
        if self.economy.lender_income_recirculated:
            self.sector["lenders"] += float(accrual[~pool].sum())
        else:
            self.external -= accrual[~pool].sum()
            self._edge_debt(np.bincount(bk["borrower"][~pool], weights=accrual[~pool], minlength=n))
        acc["out_interest"] += float(accrual[~pool].sum())
        acc["out_interest_i"] += np.bincount(bk["borrower"][~pool], weights=accrual[~pool], minlength=n)
        # Records only, each borrower's interest by lender: pool loans (legal interest, written-off loans included);
        # card balances (revolving statements and the card's fees, cash advances, and bridges sealed at the card rate
        # as their own alternative); every other outside loan (instalment loans, Comet bridges and overdrafts; fee
        # debt and charged-off balances accrue none). The card's interest is also kept since its last statement,
        # which the minimum payment reads.
        on_card = self._card_rows()
        by = lambda keep: np.bincount(bk["borrower"][keep], weights=accrual[keep], minlength=n)
        acc["credit_interest_pool"] += by(pool)
        card_interest = by(on_card)
        if not self.economy.lender_income_recirculated:
            self._card_edge(card_interest)   # the card's interest, owed across the edge until paid
        acc["credit_interest_card"] += card_interest
        # The part accrued on cash advances alone (records only, the cash-advance bound); the interest on
        # an advance's fee, booked on the purchase balance, is not in it.
        acc["credit_interest_advance"] += by(on_card & (bk["kind"] == CASH_ADVANCE))
        self.card_interest += card_interest
        acc["credit_interest_outside"] += by(~pool & ~on_card)
        # Principal-time for the real-part report: outside card credit (Comet bridges, revolving balances, cash
        # advances and charged-off balances, still owed and collected) and outside term credit, then (below) carried
        # pool bridges to card holders, which replace card credit.
        acc["pt_card"] += float(bk["principal"][~pool & _is_kind(bk["kind"], (BRIDGE, REVOLVE, CASH_ADVANCE,
                                                                               CHARGED_OFF))].sum()) / DAYS
        acc["pt_term"] += float(bk["principal"][~pool & term].sum()) / DAYS
        carried = pool & bk["carried"]
        acc["coupons"] += float(accrual[carried].sum())
        acc["bridge_coupons"] += float(accrual[carried & ~term].sum())   # theta's base (Proposition (The share))
        acc["pool_pt"] += bk["principal"][carried].sum() / DAYS
        # Loss learning's exposure: the principal-time of every carried pool loan, by product.
        acc["exposure"] += np.bincount(term[carried].astype(int), weights=bk["principal"][carried], minlength=2) / DAYS
        if self.economy.loan_losses == "sourced":
            # The loan-loss bound's base: each class's average principal over the month, by lender.
            acc["loss_base"] += self._loss_base()[1] / DAYS
        op = bk["principal"][carried].sum() * inputs.o / DAYS
        self._pool_cost(op)                                              # operating cost, paid only from pool cash
        acc["op_cost"] += float(op)
        # Reported: the same coupons less the operating cost they carry, and the principal-time, by product
        # and loan year.
        self._by_loan_year(carried, accrual[carried] - bk["principal"][carried] * inputs.o / DAYS,
                           bk["principal"][carried] / DAYS)
        bridge = carried & ~term
        acc["bridge_pt"] += np.bincount(bk["borrower"][bridge], weights=bk["principal"][bridge], minlength=n) / DAYS
        # The coupon cut demurrage pays on carried pool bridges, theta's numerator.
        acc["covered"] += float((bk["principal"] * bk["cover"])[bridge].sum()) / DAYS
        # The real part's pool principal-time (records only) counts every pool loan still owed, written off or not, as
        # the outside records count a defaulted outside loan for as long as it is owed: pool bridges to card holders,
        # and (below) pool term loans in ``pt_pool_term``. Example: a written-off pool bridge of 3 to a holder adds
        # 3 / DAYS a day to ``pt_pool_card`` and nothing to the loss-learning exposure.
        owed, holds = pool & ~term, self.holder[bk["borrower"]]
        acc["pt_pool_card"] += float(bk["principal"][owed & holds].sum()) / DAYS
        acc["pt_pool_term"] += float(bk["principal"][pool & term].sum()) / DAYS
        # Reported: the part of pool bridges to payers without a card that paid card-eligible purchases, new lending
        # the real part counts as card credit; written-off bridges still owed count too. The same for card holders:
        # the part of their pool bridges that replaced card credit, the rest having paid in place of failing, which
        # the real failure line counts.
        part = bk["principal"] * bk["card_part"]
        acc["pt_pool_nocard_card"] += float((part * ~holds)[owed].sum()) / DAYS
        acc["pt_pool_card_credit"] += float(part[owed & holds].sum()) / DAYS
        lent = carried & term
        saving = bk["principal"][lent] * (bk["alt"] - bk["rate"] - self.index)[lent]
        acc["term_saving"] += np.bincount(bk["borrower"][lent], weights=saving, minlength=n) / DAYS
        year = np.minimum((self.this_month - bk["m0"][lent]) // 12, LOAN_YEARS - 1)   # the loan's year of life
        acc["age_exposure"] += np.bincount(year, weights=bk["principal"][lent], minlength=LOAN_YEARS) / DAYS
        held = np.maximum(self.pcash, 0.0)
        acc["p_bt"] += held / DAYS
        acc["p_low"] = np.minimum(acc["p_low"], held)   # the lowest P balance of the month (idle P's measure)
        acc["liquid_bt"] += (held + np.maximum(self.cash, 0.0)) / DAYS
        if self.pool_arm:
            # All P the issuer's reserves back, and the pool's own P cash, its part: the bases of the month's reserve
            # return and of the pool's own cash's share of it (``_reserve_return``).
            acc["p_all"] += (held.sum() + max(self.pool_cash, 0.0)) / DAYS
            acc["pool_cash_bt"] += max(self.pool_cash, 0.0) / DAYS
        if self.defi:
            supplied = np.where(self.part, np.maximum(self.pcash, 0.0), 0.0) * self.p_yield / DAYS
            self.pcash += supplied
            self._coin_in(supplied)   # a record only (``_coin_day``)
            self.external += supplied.sum()
            acc["p_yield"] += supplied
        idle = np.maximum(self.cash, 0.0) * inputs.buffer_yield / DAYS
        self.cash += idle
        self._coin_in(idle)   # a record only (``_coin_day``)
        self.external += idle.sum()
        # Balance-time of savings and households' pool shares, and the spreads kept on each person's money and savings:
        # banks earn rho_H on E and deposits and pay the checking yield and the savings rate; the issuer keeps its
        # custody on P (s_I of the reserve return, c_I a year, since P's yield and demurrage stay in the household
        # economy), and in M0 the stablecoin issuer keeps the Sky spread on USDC in the "reserve" mode and rho_H
        # otherwise (``issuer_keeps``).
        acc["savings_bt"] += self.savings / DAYS
        acc["shares_bt"] += self.shares * self.nav_ps / DAYS
        banks = ((inputs.rho_H - inputs.buffer_yield) * np.maximum(self.cash, 0.0)
                 + (inputs.rho_H - self.saving_rate) * self.savings) / DAYS
        acc["deposit_spread"] += float(banks.sum())
        acc["spread"] += banks + self.issuer_keeps * np.maximum(self.pcash, 0.0) / DAYS

    def _lendable(self):
        """Pool cash available for exits: cash not owed to the pool's own creditors."""
        return max(self.pool_cash - self.pool_payable, 0.0)

    def _term_book(self):
        """The pool's carried term principal, the term book whose growth over a month the term part of the capital
        target adds (it funds next month's lending), principal only."""
        bk = self.book
        return float(bk["principal"][bk["pool"] & bk["carried"] & (bk["kind"] == TERM)].sum())

    def _cash_for_loans(self):
        """Pool cash new bridges and term loans may take: cash not owed to the pool's creditors less the part of the
        exits falling due at the next dealing that the last dealing's unused offers would not have covered.

        New subscriptions pay leaving owners first, so only the part of the due exits that offers would not cover ranks
        ahead of new loans. The exits falling due are the requests whose notice ends by the next dealing, executed
        ones still unpaid among them, on the shares they still have to pay at this NAV. At each dealing households
        offer far more than the pool has room for, and the dealing's accepted offers buy the executed exits pool cash
        leaves unpaid (``_dealing``), so the pool sets aside during the month only the due exits beyond the money
        offered at the last dealing that found no room (``unused_offers``). Before the first dealing after launch
        that is zero, and every exit falling due is set aside. A request may still lapse at a review before then; it
        is counted all the same. Exits themselves are paid from all cash not owed to creditors (``_lendable``)."""
        filed = (self.exit_start >= 0) & (self.this_month + 1 - self.exit_start >= EXIT_NOTICE_MONTHS)
        due = float((np.minimum(self.exit_left, self.shares) * self.nav_ps)[filed].sum())
        return max(self._lendable() - max(due - self.unused_offers, 0.0), 0.0)

    def _standby_held(self):
        """The pool cash held back from term loans for bridges (``Economy.standby``), the standby the charge pays for:
        under "reserved", in the arrangements with demurrage, min(cash for loans, max(peak - B, 0)), with the peak
        bridging need this month's terms read (``self.peak``, the capital target's and the charge's) and B the pool
        bridging principal carried now, statement draws included; zero by default and in the pool without demurrage,
        where nothing pays its owners for standing cash, unless ``Economy.uncharged_standby`` is "reserved", when that
        pool holds back cash by the same rule, so that with the same capital target (``uncharged_target`` "peak") the
        two pools differ only by the charge.

        Example (dollars a person, peak 240 and 80 carried): cash 300 holds 160; cash 160 holds 160; cash 150 holds
        150; and with 240 carried nothing is held."""
        holds = self.demurrage or (self.pool_arm and self.economy.uncharged_standby == "reserved")
        if self.economy.standby != "reserved" or not holds:
            return 0.0
        bk = self.book
        carried = float(bk["principal"][bk["pool"] & bk["carried"] & (bk["kind"] != TERM)].sum())
        return min(self._cash_for_loans(), max(self.peak - carried, 0.0))

    def _cash_for_term(self):
        """Pool cash new term loans may take (``Economy.standby``): the cash for loans (``_cash_for_loans``) less the
        standby held for bridges (``_standby_held``), max(cash for loans - max(peak - B, 0), 0). By default, and in the
        pool without demurrage unless ``uncharged_standby`` is "reserved", it is the cash for loans itself. Bridges and
        card statement draws keep the whole cash for loans.

        Example (dollars a person, peak 240): cash 300 with 80 carried leaves 140 open; cash 160 or 150 with 80
        carried leaves none; cash 400 with 240 carried leaves all 400."""
        cash = self._cash_for_loans()
        return max(cash - self._standby_held(), 0.0) if self.economy.standby == "reserved" else cash

    def _pay_gas(self, payer, gas):
        """Book the gas on completed P payments, or USDC payments in M0 (P payments run on stablecoin rails): ``gas``
        per payment, paid by its ``payer`` to the chain's validators outside the household economy. Nobody inside it
        receives any of it: there is no provider fee and the issuer is not a payment operator. In the pool arms the
        gas leaves as P, which is redeemed, so the reserves behind it fall with it."""
        self.acc["gas"] += np.bincount(payer, weights=gas, minlength=self.n)
        total = float(gas.sum())
        self.acc["gas_paid"] += total
        self.external -= total
        if self.pool_arm:
            self.reserves -= total

    def _owners_alternative(self):
        """Owners' alternative a month on a unit of pool capital, in P terms (nominal in M1, real in M2): the reserve
        rate plus the owners' spread, on every share, all households'. The one place the yardsticks read it. The rate
        is floored at zero, which changes nothing on the grid (M2 at r_out 2% runs at zero) and raises the alternative
        below it."""
        return max(self.rho_p, 0.0) + self.economy.owner_spread

    def _owners_alternative_nominal(self):
        """Each saver's and owner's alternative to the pool a month in nominal terms, the money-market part's own
        return (``pool_alternative``, rho_H), plus the owners' spread: what dealing and exits compare the pool's
        nominal-equivalent return with."""
        return self.pool_alternative + self.economy.owner_spread

    def _cash_to_lend(self):
        """Cash to lend, recorded for the credit-death test: the cash new loans may take (``_cash_for_loans``, with the
        set-aside for due exits) while the pool serves, and none while it does not. It mirrors the lending capacity
        lines of ``_term_purchases``, ``_settle`` and ``_statement``, which write the same expression out, so a change
        to those lines needs a deliberate choice here too. Under reserved standby term loans read ``_cash_for_term``
        instead, and this record stays the cash bridges and statement draws may take, the whole cash for loans, with
        the part held back recorded apart (``standby_held``). A record only: nothing in the engine reads it."""
        return self._cash_for_loans() if self.service else 0.0

    def _pool_cost(self, amount):
        """Pay a pool cost (operating or fixed) only from pool cash; the unpaid rest is a payable.

        The pool's operating provider sits outside the household economy (the boundary rule). So the cost leaves
        household wealth when it is incurred (owners bear it through NAV), and paying a payable later moves no wealth.
        If the pool closes with a payable outstanding, that is the provider's loss, and no money is created.
        """
        due = self.pool_payable + amount
        pay = min(due, max(self.pool_cash, 0.0))
        # A record only: the part of this cost the pool's cash does not pay now, after what it already
        # owed, is a debt to the provider when it is booked (``edge_accrued``).
        acc = getattr(self, "acc", None)
        if acc is not None and "edge_accrued" in acc:
            acc["edge_accrued"] += amount - min(amount, max(pay - self.pool_payable, 0.0))
        self.pool_cash -= pay
        self.pool_payable = due - pay
        if acc is not None and "pool_payable_most" in acc:
            # A record only: the most the pool has owed its provider on any day of the month.
            acc["pool_payable_most"] = max(acc["pool_payable_most"], self.pool_payable)
        self.reserves -= pay   # the provider is paid in E, so the pool's P is redeemed
        self.external -= amount
        self.acc["pool_operating"] += amount

    def _lagged_jobs_without_wage(self, month):
        """The share of jobs without a wage LOSS_LAG months before ``month``, the month's average (the ``laid_off``
        series, which the runner stores as jobs_without_wage); before month 3, the earliest month's, month 0's.
        Read at the close, when this month's own share is known and earlier months' are recorded."""
        if month == 0:
            return float(self.acc["laid_off"])
        return float(self.series["laid_off"][max(month - LOSS_LAG, 0)])

    def _loss_base(self):
        """The loan-loss bound's classes and base today: each loan's class (``LOSS_CLASSES``' index, -1 for a loan that
        loses nothing: fee debt, Comet's loans, a pool loan no longer carried, an empty loan, and a card balance the
        engine has charged off itself, so no loss is counted twice), and the principal by class and lender group,
        outside lenders then the pool. Cash advances are card debt. ``_accrue`` adds a day's over DAYS to the month's
        base, so the base at the close is each class's average principal over the month."""
        bk = self.book
        kind, pool = bk["kind"], bk["pool"]
        comet = ~pool & (kind == BRIDGE) & (bk["rate"] != bk["alt"])
        term = kind == TERM
        cls = np.select([np.isin(kind, (BRIDGE, REVOLVE, OVERDRAFT, CASH_ADVANCE)) & ~comet, term & ~bk["business"],
                         term & bk["business"]], [0, 1, 2], -1)
        cls = np.where((~pool | bk["carried"]) & (bk["principal"] > EPS), cls, -1)
        live = cls >= 0
        base = np.bincount(2 * cls[live] + pool[live], weights=bk["principal"][live], minlength=6).reshape(3, 2)
        return cls, base

    def _loan_losses(self, month):
        """Loan losses at sourced rates, the bound reading, with ``Economy.loan_losses``
        "sourced", once a month in every arm, burn-in included, at the start of the close; with "none" nothing.

        Every loan is in one class (``LOSS_CLASSES``): card for bridges, revolving card debt and overdrafts, except
        Comet's loans (secured by collateral; told apart as the engine's accrual records do, an outside bridge sealed
        at a rate other than its borrower's card rate); consumer and business for term loans by the ``business``
        record; fee debt is in none. The month's rate a year of class k is ``charge_off_rates`` at the share of jobs
        without a wage three months earlier. For each class and each lender group (the pool; outside lenders) the
        amount discharged is that rate over 12 times the class's average principal with that group over the month's
        days (``_loss_base``, the published rate's own base: net charge-offs over average balances), the pool's
        counting only the loans it still carries. It is taken from the loans on the book at the close, at most all of
        them: first from borrowers without a wage now (the earner of a job in a spell on the month's last day), pro
        rata to their principal in that class and group, and the rest pro rata from the others' principal.

        The principal falls for good, as if repaid by no one, and no cash moves: a term loan's schedule ends earlier,
        and one no longer overdue is no longer in arrears. A pool loan's discharge is the owners' loss for good: the
        pool's assets and so NAV fall by it, it counts as written off, the loan-year record holds it, and nothing of
        it can be recovered; the coupon carries the same rate (``_priced_loss``), so it is no loss of the product the
        coupon's learned rate reads, which keeps to the engine's own write-offs. The borrower's debt falls by the same
        amount, so households' wealth does not change and no valuation is booked. An outside loan's discharge is the
        outside lender's loss: households' wealth rises by it, an outside flow (``external``). Example: a pool
        bridge book of 1,200 carried all month at the normal card rate, 100 owed by a borrower without a wage and
        1,100 by one with a wage, discharges 1,200 x 3.402% / 12 = 3.402, all from the first; with 2 owed by the
        first, 2 from it and 1.402 from the other. No random number is drawn.

        An amount larger than the principal on the book at the close (a book that turned over or ran down within the
        month) is not dropped: the part not discharged is carried, by class and lender group (``loss_carried``, zero
        at the start), and added to the next month's amount for the same class and group, until a book absorbs it. The
        total carried at each close is recorded (``LOSS_CARRIED``, per person).
        Example: a pool bridge base of 1,200 with no pool bridge on the book at the close discharges nothing and
        carries 3.402; the next month, with a book of 1,200 carried all month, the amount is 3.402 + 3.402 = 6.804,
        all discharged, and nothing is carried.
        """
        if self.economy.loan_losses != "sourced":
            return
        bk, acc, n = self.book, self.acc, self.n
        kind, pool = bk["kind"], bk["pool"]
        rates = charge_off_rates(self._lagged_jobs_without_wage(month))
        term = kind == TERM
        cls = self._loss_base()[0]
        live = cls >= 0
        t = month * DAYS + DAYS - 1
        spell = (self.spell_start <= t) & (t < self.spell_end)
        without = np.zeros(n, bool)
        without[self.pop["wage_to"][spell]] = True
        jobless = without[bk["borrower"]]
        # Every class and lender group at once, one row each (class k, lender l at 2k + l, as ``loss_carried`` holds
        # them): each loan is in one group, so its cut is its own group's share alone.
        group = np.where(live, 2 * cls + pool, -1)
        principal = np.where(group[None, :] == np.arange(2 * len(LOSS_CLASSES))[:, None], bk["principal"], 0.0)
        first = np.where(jobless, principal, 0.0)
        others = principal - first
        held, base = first.sum(axis=1), others.sum(axis=1)
        amount = np.repeat(rates, 2) / 12 * acc["loss_base"].reshape(-1) + self.loss_carried.reshape(-1)
        active = amount > 0                                   # a group with nothing to discharge is left as it is
        taken = np.minimum(amount, held)
        share_first = np.where(taken < held, taken / np.where(held > 0, held, 1.0), 1.0)
        rest = amount - taken
        share_others = np.minimum(rest / np.where(base > 0, base, 1.0), 1.0)
        # What the book at the close could not absorb is carried to the next month.
        self.loss_carried = np.where(active, np.maximum(rest - base, 0.0), self.loss_carried.reshape(-1)).reshape(
            self.loss_carried.shape)
        at = np.maximum(group, 0)
        from_first = (group >= 0) & jobless & (active & (held > 0))[at]
        from_others = (group >= 0) & ~jobless & (active & (rest > 0) & (base > 0))[at]
        cut = np.where(from_first, bk["principal"] * share_first[at],
                       np.where(from_others, bk["principal"] * share_others[at], 0.0))
        cut = np.minimum(cut, bk["principal"])
        # What the card is owed before the discharge, for the card's fees and interest not yet paid (below).
        card = ~pool & (self._card_rows() | (kind == CHARGED_OFF))
        card_owed = lambda: np.bincount(bk["borrower"][card], weights=(bk["principal"] + bk["interest"])[card],
                                        minlength=n)
        before = card_owed()
        bk["principal"] -= cut
        # The card's fees and interest not yet paid are part of its balance, so a discharge takes its share of them:
        # they leave the stock owed across the edge with the balance, never to be returned. The interest accrued on
        # any other loan is not discharged and stays owed. Example: a $100 card balance holding $10 of fees, half of
        # it discharged, leaves $5 of fees in the stock.
        kept = self.card_edge_owed * np.divide(card_owed(), before, out=np.ones(n), where=before > EPS)
        self._edge_discharged(float((self.card_edge_owed - kept).sum()))
        self.card_edge_owed = kept
        idx = np.flatnonzero(term & (cut > 0))
        bk["since"][idx[self._overdue(idx) <= EPS]] = BIG
        rows = pool & (cut > 0)
        lost = np.bincount(term[rows].astype(int), weights=cut[rows], minlength=2)
        acc["written_off"] += float(lost.sum())
        acc["written_off_bridge"] += float(lost[0])   # records only: by loan kind, bridges then term loans
        acc["written_off_term"] += float(lost[1])
        self._by_loan_year(rows, -cut[rows])
        outside = np.bincount(cls[~pool & (cut > 0)], weights=cut[~pool & (cut > 0)], minlength=3)
        self.external += float(outside.sum())
        acc["discharged"] = np.concatenate([lost, outside])

    def _write_off(self, t):
        """A pool loan 90 days past due is written down to zero; owners bear it in NAV, the legal debt remains.

        The write-down is a valuation term in the conservation identity.
        """
        bk = self.book
        age = np.where(bk["kind"] == TERM, t - bk["since"], t - bk["due"])
        hit = bk["pool"] & bk["carried"] & (age >= WRITE_OFF_DAYS) & (bk["principal"] + bk["interest"] > EPS)
        lost = (bk["principal"] + bk["interest"])[hit]
        loss = float(lost.sum())
        bk["carried"][hit] = False
        self.valuation -= loss
        self.acc["written_off"] += loss
        term = bk["kind"][hit] == TERM
        by_kind = np.bincount(term.astype(int), weights=lost, minlength=2)
        self.acc["lost"] += by_kind
        # Records only: the write-down by loan kind, bridges then term loans.
        self.acc["written_off_bridge"] += float(by_kind[0])
        self.acc["written_off_term"] += float(by_kind[1])
        self._by_loan_year(hit, -lost)   # reported: the write-down by product and loan year
        # Reported: a term loan's year of life when it first missed a payment (when defaults come).
        year = np.minimum((bk["since"][hit][term] // DAYS - bk["m0"][hit][term]) // 12, LOAN_YEARS - 1)
        self.acc["age_loss"] += np.bincount(year, weights=lost[term], minlength=LOAN_YEARS)

    def _by_loan_year(self, rows, income, exposure=0.0):
        """Add pool loans' income to owners and carried principal-time by product (bridging, then term) and by loan
        year, the year after launch the loan was made (a pool lends only from launch), the last band taking any later
        year (reported only, owners' return by loan year). There are ``vintage_years`` bands, one for every year of the
        run after launch and never fewer than LOAN_YEARS, so a run of 60 months or less keeps its five bands. ``rows``
        selects the loans in the book; no rule reads the record.

        Called where the engine books each amount, from the same arrays: coupons accrued on carried loans less the
        operating cost they carry (``_accrue``), write-offs of principal and interest (``_write_off``) and recoveries,
        payments on written-off loans (``_pay``). The record holds these loan-attributable items only, on the NAV
        basis. Provider fees and the fixed cost are not by loan: the close keeps them as one monthly amount, which the
        reading spreads over the loan years by principal-time. Demurrage's revenue, the pool's float and the charge,
        is not by loan and stays out, while a bridge's coupons are those its borrower accrued, after the cut
        demurrage pays, which leans against CPM by that cut.
        """
        bk, acc, bands = self.book, self.acc, self.vintage_years
        year = np.clip((bk["m0"][rows] - self.economy.burn_in) // 12, 0, bands - 1)
        cell = (bk["kind"][rows] == TERM) * bands + year
        add = lambda weights: np.bincount(cell, weights=weights, minlength=2 * bands).reshape(2, bands)
        acc["vintage_income"] += add(income)
        acc["vintage_exposure"] += add(np.broadcast_to(exposure, cell.shape))

    def _deflate(self):
        """CPI inflation in real units: every nominal stock loses dJ/J a month; indexed P (M2) and its loans do not.

        Earned-wage accruals and advances owed are nominal too. Returns the real wealth change, the
        conservation identity's inflation term.
        """
        f = 1.0 / (1.0 + self.economy.inflation)
        if f == 1.0:
            return 0.0
        before = self.net_wealth().sum()
        money = self.cash + self.pcash + self.savings   # a record only (``_coin_day``): CPI's loss of the money's value
        scale = lambda name: setattr(self, name, getattr(self, name) * f)
        # The card's interest, fees and payments since its statement and its amount past due are nominal too; its line
        # and starting balance are held fixed in real terms. So are the card's fees and interest not yet paid and the
        # earned-wage fees still owed, as the debts they are part of are.
        list(map(scale, ("cash", "savings", "receivable", "payable", "card_unbilled", "card_statement", "od_pending",
                         "accrued", "ewa_owed", "card_interest", "card_fees", "card_past_due", "card_paid",
                         "card_edge_owed", "ewa_fee_owed")))
        self.ob["amount"] = self.ob["amount"] * f
        self.req["price"] = self.req["price"] * f
        bk = self.book
        nominal = np.where(bk["pool"] & self.indexed, 1.0, f)
        list(map(lambda key: bk.__setitem__(key, bk[key] * nominal),
                 ("principal", "interest", "interest_due", "original", "instal")))
        if not self.indexed:
            self.pcash, self.pool_cash, self.pool_payable = self.pcash * f, self.pool_cash * f, self.pool_payable * f
            self.reserves *= f   # nominal T-bills behind nominal P
        self._coin_net(self.cash + self.pcash + self.savings - money, row=2)
        if self._all_shares() > EPS:
            self.nav_ps = self._assets() / self._all_shares()
        return float(self.net_wealth().sum() - before)

    def _compact(self):
        """Housekeeping: drop settled loans and merge undated debts (revolving, overdraft, fee debt, cash advances and
        charged-off balances) per borrower and kind.

        No economic change; it keeps the loan book small. The key's multiplier exceeds the largest kind, so the merge
        keeps the order of (borrower, kind). Each kind's rows of one borrower carry one rate (its purchase APR, its
        cash APR, or none), so keeping the first row's rate reprices nothing.
        """
        bk = self.book
        live = bk["principal"] + bk["interest"] > EPS
        undated = live & np.isin(bk["kind"], (REVOLVE, OVERDRAFT, FEE_DEBT, CASH_ADVANCE, CHARGED_OFF))
        keep = _take(bk, live & ~undated)
        loose = _take(bk, undated)
        key, inverse = np.unique(loose["borrower"] * 7 + loose["kind"], return_inverse=True)
        first = np.unique(inverse, return_index=True)[1]
        merged = _take(loose, first)
        merged["principal"] = np.bincount(inverse, weights=loose["principal"], minlength=key.size)
        merged["interest"] = np.bincount(inverse, weights=loose["interest"], minlength=key.size)
        merged["original"] = merged["principal"].copy()
        self.book = _concat(keep, merged)
        durable = self.durable
        self.durable = _take(durable, durable["left"] > 0)

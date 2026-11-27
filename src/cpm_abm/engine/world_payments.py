"""What a day's credit decisions read and how money moves.

Each person's expected receipts, its budget over the horizon, a loan's covering date and whether a pool draw costs
more than the line the payer holds; then conversion fees, crossings, rewards, debits and credits, the end-of-step
clean-up, paying, repaying, collecting what is due, overdue wages, earned-wage repayment and the money's ages.
"""
import numpy as np

from cpm_abm.engine.constants import (BIG, BRIDGE, C1_HORIZON_DAYS, C1_PERIOD_DAYS, CASH_ADVANCE, CHARGED_OFF, DAYS,
                                      EPS, EWA_FEE, FAIL_FEE, FEE_DEBT, LATE_OUTSIDE_WAGE, LATE_WAGE, OVERDRAFT,
                                      REVOLVE, TERM)
from cpm_abm.engine.population import next_billing
from cpm_abm.engine.ledger import _DUE_SOON_FIELDS, _is_kind, _overdue_of, _take, allocate


class PaymentsMixin:
    """How money moves, one part of ``_World``: the expected receipts and budgets credit decisions read, fees,
    crossings, rewards, debits and credits, repayments and collections, overdue wages and the money's ages."""

    def _receipt_streams(self):
        """Each person's expected receipts by stream, from last month's observed receipts.

        A wage arrives on its job's own pay dates, so the budget
        expects each job's last-month wage paid to its recipient, on time or
        late, on that job's pay dates, one pay period's amount (the month's
        wage times the period over the month's days) on each. A job that paid
        nothing last month, as in a spell, is expected to pay nothing. The
        person's other receipts, everything that is not a wage, are spread
        over its own billing dates. Without pay dates a wage
        settles on the recipient's billing dates, so its job's dates are those.

        Under ``Economy.receipts_window`` 2 the other
        receipts are the mean of the last two completed months', the one
        month while only one exists; wages are read from last month.
        Example: a person paid $2,000 every 60 days for $1,000 a
        month of sales is expected to receive $2,000 over the next two months
        whether last month held the receipt or not, where one month's reading
        expects $4,000 after a receipt and $0 after none.

        Returns (each job's pay period, its phase, its expected wage per pay
        date, each person's other receipts per own billing date).
        """
        cache = self._day_cache
        if cache is not None and "streams" in cache:
            return cache["streams"]
        pop = self.pop
        wage_to, wages = pop["wage_to"], np.maximum(self.last["wages_paid"], 0.0)
        if self.economy.pay_dates:
            period, phase = pop["pay_days"], pop["pay_phase"]
        else:
            period, phase = pop["cycles"][wage_to], pop["phases"][wage_to]
        other = self._other_receipts()
        if self.other_before is not None:
            # Two months of receipts (``Economy.receipts_window`` 2): the mean of the last two
            # completed months' receipts other than wages (``other_before``, kept at the close only under it).
            other = (other + self.other_before) / 2
        other = other * pop["cycles"] / DAYS
        streams = period, phase, wages * period / DAYS, other
        if cache is not None:
            cache["streams"] = streams   # last month's observations: the same all day (``day``)
        return streams

    def _other_receipts(self):
        """Each person's receipts last month other than wages: its receipts less the wages its incoming jobs paid it,
        on time or late, floored at zero."""
        incoming = np.bincount(self.pop["wage_to"], weights=np.maximum(self.last["wages_paid"], 0.0), minlength=self.n)
        return np.maximum(self.last["receipts"] - incoming, 0.0)

    def _receipts_side(self, t):
        """The budget's receipt side on day ``t`` (``_c1_budget``): the receipts expected in the horizon and each
        person's last receipt date in it. It reads only ``t``, the population and last month's receipts, so within a
        day it is computed once (``day``); callers never write into the arrays returned."""
        cache = self._day_cache
        if cache is not None and cache.get("receipts_t") == t:
            return cache["receipts"]
        cycles, phases = self.pop["cycles"], self.pop["phases"]
        period, phase, per_pay, other = self._receipt_streams()
        first = next_billing(cycles, phases, t, strict=True)
        dates = np.maximum((t + C1_HORIZON_DAYS - first) // cycles + 1, 0)
        # Each job's pay dates in the horizon and the last of them, for the jobs that paid last month.
        wage_to = self.pop["wage_to"]
        pay_first = next_billing(period, phase, t, strict=True)
        pays = np.maximum((t + C1_HORIZON_DAYS - pay_first) // period + 1, 0)
        expected = other * dates + np.bincount(wage_to, weights=per_pay * pays, minlength=self.n)
        last = first + np.maximum(dates - 1, 0) * cycles
        paying = (per_pay > 0) & (pays > 0)
        np.maximum.at(last, wage_to[paying], (pay_first + (pays - 1) * period)[paying])
        if cache is not None:
            cache["receipts_t"], cache["receipts"] = t, (expected, last)
        return expected, last

    def _due_soon(self, t, rows=None):
        """What each loan (``rows`` of the book, or every loan) puts ahead of a new bridge in the budget on day ``t``
        (``_c1_budget``), element by element."""
        bk = self.book
        f = bk if rows is None else {key: bk[key][rows] for key in _DUE_SOON_FIELDS}
        term = f["kind"] == TERM
        until = np.clip(f["due"], t, t + C1_HORIZON_DAYS)
        bridge = f["principal"] * (1 + f["rate"] * (until - t) / DAYS) + f["interest"]
        if self.index:
            # M2's indexation of pool credit; with no index the factor is exactly 1 and is not computed.
            bridge = bridge * np.where(f["pool"], (1 + self.index) ** (until // DAYS - t // DAYS), 1.0)
        # Term loans: what is overdue, the next two principal instalments and the interest they carry.
        months = np.minimum(2.0, np.divide(f["principal"], f["instal"], out=np.zeros(f["principal"].size),
                                           where=f["instal"] > EPS))
        interest = np.maximum(f["interest"] - f["interest_due"], 0.0) + f["rate"] * f["principal"] * months
        return np.where(term, _overdue_of(f) + np.minimum(2 * f["instal"], f["principal"]) + interest, bridge)

    def _c1_budget(self, t, who=None, statement=False):
        """Covering-date budget for every person: the receipts expected in the horizon and what is already owed.

        Receipts are last month's observed receipts on the dates they are
        expected (``_receipt_streams``): each incoming
        job's wage on that job's pay dates, the rest on the person's own
        billing dates. Already owed:
        every debt that ``_pay`` serves before new pool credit or that falls
        due in the next two months. That is every bridging, revolving,
        overdraft and fee-debt balance (any lender; fee debt is repaid first,
        then outside debt, dearest first) with the interest it accrues up to
        its due date within the horizon
        (and, for M2 pool credit, its indexation), plus term instalments
        falling due in the next two months with their interest: the interest
        already accrued plus two months at the loan's own rate on its balance,
        fewer when fewer instalments remain. Earned-wage
        advances owed, fee included, count too: their own wages repay
        them before anything else.

        Returns (expected receipts, spare, owed, last). Expected receipts are
        those of the next two months; spare is what they leave after those
        debts; last is the person's last receipt date in the horizon: its last
        own billing date, or a later pay date of an incoming job that paid last
        month. Every receipt expected in the horizon arrives by then, so the
        admission limits, which compare spare with each financing's cost on
        that date, read the same schedule as ``_due_c1``. Receipts are
        valued in E, so an M2 participant paid in P is budgeted conservatively.

        With ``who`` (a mask of people) only their debts are read, every loan of each in book order, so each of them
        is owed exactly what the whole book gives it (as ``_due_c1`` reads them); everyone else's owed is zero there,
        a speed device for a caller that reads the budget of those people alone.

        Under ``Economy.screen_card_owed`` what the card is already owed counts too: each
        holder's closed statement not yet due and its card purchases not yet billed, both due within the horizon. With
        ``statement`` (the caller is refinancing the statement due today, ``_statement``) only the unbilled purchases
        are added, since the statement is the very amount the pool is asked to pay. The covering date counts the same
        card term (``_due_c1``), so both read one schedule. Example: $100 of expected
        receipts, an empty book and a $100 statement owed leave $100 spare, and $0 under the setting.
        """
        expected, last = self._receipts_side(t)
        if who is None:
            owed = np.bincount(self.book["borrower"], weights=self._due_soon(t), minlength=self.n)
        else:
            rows = np.flatnonzero(who[self.book["borrower"]])
            owed = np.bincount(self.book["borrower"][rows], weights=self._due_soon(t, rows), minlength=self.n)
        if self.economy.earned_wage_share > 0:
            owed = owed + np.bincount(self.pop["wage_to"], weights=self.ewa_owed, minlength=self.n)
        if self.economy.screen_card_owed:
            card = self.card_unbilled if statement else self.card_unbilled + self.card_statement
            owed = owed + (card if who is None else np.where(who, card, 0.0))
        return expected, np.maximum(expected - owed, 0.0), owed, last

    def _due_c1(self, who, amount, t, rate=None, ahead=None, statement=False):
        """Covering date: the first receipt date whose expected receipts cover what is owed plus this loan.

        Receipt dates and amounts are the budget's (``_receipt_streams``): each incoming job's last-month wage on
        that job's pay dates, the person's other receipts on its own billing dates, so a bridge falls due when the
        money that repays it is expected to arrive.
        The loan counts with the interest it accrues to that date (and, for M2
        pool credit, its indexation), so the receipts cover the whole repayment.
        A pool loan (``rate`` None) is admitted only within the
        two-month horizon by the settlement's covering-date limit; should rounding leave it uncovered, it
        falls due on the last receipt date in the horizon (the budget's last). An outside loan
        (``rate`` its nominal rate) is due on its own covering date however
        late: the horizon limits pool admission, not the maturity of outside
        credit (the covering-date rule applies to both lenders). Beyond the
        horizon the schedule repeats every ``C1_PERIOD_DAYS``. ``ahead`` is new debt booked the
        same day that ranks ahead of this loan in repayment. Under ``Economy.screen_card_owed`` what is owed counts
        the card term ``_c1_budget`` counts, the closed statement and the unbilled purchases, or with ``statement``
        (refinancing the statement, ``_statement``) the unbilled purchases alone, so the admission limit and the due
        date read the same schedule. Example: a $60 statement owed and receipts of
        $100 on days 40 and 70 admit a $70 bridge drawn on day 30, due on day 70; without the card term it falls due on
        day 40, when only $40 of that receipt is free.
        """
        pop, n = self.pop, self.n
        if who.size == 0:
            return np.zeros(0, np.int64)
        # The budget's owed for the asked borrowers only: every loan of each, in book order, so each bin adds the same
        # amounts in the same order as over the whole book (``_c1_budget``).
        _, last = self._receipts_side(t)
        bk = self.book
        asked = np.zeros(n, bool)
        asked[who] = True
        rows = np.flatnonzero(asked[bk["borrower"]])
        owed = np.bincount(bk["borrower"][rows], weights=self._due_soon(t, rows), minlength=n)
        if self.economy.earned_wage_share > 0:
            owed = owed + np.bincount(pop["wage_to"], weights=self.ewa_owed, minlength=n)
        if self.economy.screen_card_owed:
            owed = owed + (self.card_unbilled if statement else self.card_unbilled + self.card_statement)
        owed, last = owed[who] + (0.0 if ahead is None else ahead), last[who]
        period, phase, per_pay, other = self._receipt_streams()
        # Each borrower's expected receipts on each day after t: one full repeat of its schedule for an outside loan,
        # the horizon for a pool loan. A receipt date is an own billing date or a pay date of a job that paid.
        width = C1_HORIZON_DAYS if rate is None else C1_PERIOD_DAYS
        days = t + 1 + np.arange(width)
        dated = (days[None, :] - pop["phases"][who, None]) % pop["cycles"][who, None] == 0
        receipts = dated * other[who, None]
        row = np.full(n, -1)
        row[who] = np.arange(who.size)
        jobs = np.flatnonzero((row[pop["wage_to"]] >= 0) & (per_pay > 0))
        paid = (days[None, :] - phase[jobs, None]) % period[jobs, None] == 0
        rows = row[pop["wage_to"][jobs]]
        np.add.at(receipts, rows, paid * per_pay[jobs, None])
        np.logical_or.at(dated, rows, paid)
        cum = np.cumsum(receipts, axis=1)
        factor = self._pool_factor(t, days[None, :]) if rate is None else 1 + rate[:, None] * (days - t) / DAYS
        gap = owed[:, None] + amount[:, None] * factor - cum   # what the receipts still leave unpaid on each day
        covered = dated & (days <= t + C1_HORIZON_DAYS) & (gap <= 1e-9)
        if rate is None:
            return np.where(covered.any(axis=1), days[covered.argmax(axis=1)], last)
        # On each receipt date of the first repeat, every later repeat adds that repeat's receipts and the loan's
        # interest for its days; the least number of repeats that covers the gap there, and the earliest such date.
        slope = (cum[:, -1] - amount * rate * C1_PERIOD_DAYS / DAYS)[:, None]
        repeats = np.where(gap <= 1e-9, 0.0,
                           np.where(slope > EPS, np.ceil(gap / np.maximum(slope, EPS) - 1e-9), 10 ** 6))
        due = np.where(dated, days[None, :] + np.clip(repeats, 0, 10 ** 6).astype(np.int64) * C1_PERIOD_DAYS, BIG)
        return due.min(axis=1)

    def _dearer(self, draw, t, ahead, room=None, cash_room=None, statement=False):
        """Payers whose pool draw would cost more than the line they hold, on its covering date.

        Both repayments are valued in E on the draw's own covering date: the pool's
        with its coupon and, in M2, the indexation of every CPI mark crossed;
        a card holder's card at its own APR. With ``room``, each payer's
        earned-wage room today, a payer without a card whose room is
        positive holds the advance, at 1 + its fee whenever repaid. Without a
        card or that room the alternative is failure, so the pool is never
        dearer. ``ahead`` is the same day's outside financing, repaid before
        the pool. With ``cash_room``,
        each holder's room on its cash line today, a bill's draw is compared
        with a cash advance only on the part that room could take, at the cash
        APR and, per unit of that part, the advance's fee (owed at the purchase
        APR); a holder with no cash room left holds earned-wage access or
        nothing, as a payer without a card does. Without ``cash_room`` (the
        statement) a holder's alternative is to revolve at its purchase APR. ``statement`` marks the statement's
        draw, whose covering date counts the card as the statement's budget does (``_due_c1``).
        """
        if cash_room is None:
            cash, rate = self.holder, self.card_apr
        else:
            cash, rate = cash_room > EPS, self.cash_apr
        holds = cash if room is None else cash | (room > EPS)
        who = np.flatnonzero((draw > EPS) & holds)
        due = self._due_c1(who, draw[who], t, ahead=ahead[who], statement=statement)
        line = 1 + rate[who] * (due - t) / DAYS
        if cash_room is not None:
            part = np.minimum(draw[who], cash_room[who])
            per = np.maximum(self.advance_floor / np.where(part > EPS, part, 1.0), self.advance_rate)
            line = line + np.where(part > EPS, per, 0.0) * (1 + self.card_apr[who] * (due - t) / DAYS)
        if room is not None:
            # A payer without a card whose draw is dearer than the advance leaves the pool's queue for the whole draw,
            # as a holder does for the card.
            line = np.where(cash[who], line, 1 + EWA_FEE)
        dearer = np.zeros(self.n, bool)
        dearer[who] = self._pool_factor(t, due) > line + 1e-15
        return dearer

    def _fee(self, fee):
        """Book each person's conversion fees: paid to the conversion provider, outside the economy."""
        self.acc["conversion"] += fee
        self.external -= float(fee.sum())

    def _crossed(self, to_p, to_e, fee, conversion=False):
        """Reported only: add each person's moves between E and P, before any fee, to the current
        step: a conversion where the move pays the conversion fee or is one by its kind (``conversion``: joining,
        leaving and P redeemed for a non-participant, which convert whatever the fee, so M0's free USDC conversion
        is not counted as routine), else a routine crossing. No rule reads it."""
        if np.ndim(fee) == 0 and (conversion or not fee > 0):
            # One kind for every person (a speed device): the other kind's row would add zeros, which changes nothing.
            self.crossed[1 if conversion or fee > 0 else 0] += to_p - to_e
            return
        net, paid = to_p - to_e, conversion | (np.asarray(fee) > 0)
        self.crossed[0] += np.where(paid, 0.0, net)
        self.crossed[1] += np.where(paid, net, 0.0)

    def _count_crossings(self):
        """Close one step's crossings between E and P (reported only).

        A step is a day, the dealing (with the launch conversions) or the close. A person crosses at most once a step
        in each kind, in the direction its moves net to, for that net value. So money that enters P and leaves it again
        within the step, as savings that mature into cash at dealing, are swept into P and are saved again, does not
        cross. Payouts, rebates and refunds credited in P to participants never cross; credited to anyone else they
        are redeemed, a conversion.
        """
        moved = np.abs(self.crossed)
        crossed = moved > EPS
        self.acc["crossings"] += crossed
        self.acc["crossed"] += np.where(crossed, moved, 0.0)
        self.crossed[:] = 0.0

    def _pay_rewards(self):
        """Card rewards: the card issuers, outside the economy, pay each cardholder its rewards on
        the month's card purchases at the close; returns them per person."""
        rewards = self.acc["rewards"]
        self.cash += rewards
        self._coin_in(rewards)   # a record only (``_coin_day``)
        self.external += float(rewards.sum())
        return rewards

    def _recirculate(self):
        """The recirculation stress: the month's outside lenders' interest, and the card's fees (``_card_lender``),
        return to households pro rata to spending; returns it per person (zero without the stress)."""
        back = self.sector["lenders"] * self.spending / self.spending.sum()
        self.cash += back
        self._coin_in(back)   # a record only (``_coin_day``)
        self.sector["lenders"] = 0.0
        return back

    def _rate(self):
        """Conversion fee per unit for each person: zero for participants under the core convention, else the arm's fee
        (``conversion``: none for USDC in M0)."""
        cache = self._day_cache
        if cache is not None and "rate" in cache:
            return cache["rate"]   # participation changes only at launch and at the close, never within a day
        free = self.part & (not self.economy.routine_conversion)
        rate = np.where(free, 0.0, self.conversion)
        if cache is not None:
            cache["rate"] = rate
        return rate

    def _fail_rate(self):
        """Failure fee per unit failed in a buffer choice, before the daily cap: the fee over last month's average."""
        return FAIL_FEE / np.maximum(self.last["avg_payment"], EPS)

    def _use_savings(self, short):
        """Same-day savings: move up to ``short`` of each person's outside savings into its cash.

        The money gives up its outside interest for the month (savings earn on
        the month-end balance) and comes back to savings only at dealing. The
        draw is recorded so the day's own cash flow (the buffer replay) does
        not count it as income.
        """
        used = np.minimum(np.maximum(short, 0.0), self.savings)
        self.savings -= used
        self.cash += used
        if hasattr(self, "today"):
            self.today["savings"] += used
        return used

    def _consolidate(self):
        """Core convention: a participant's working cash is P, so E it receives joins its P balance (no fee)."""
        if self.economy.routine_conversion:
            return
        moved = np.where(self.part, np.maximum(self.cash, 0.0), 0.0)
        self.cash -= moved
        self.pcash += moved
        self.reserves += float(moved.sum())   # E turned into P is backed one for one
        self._crossed(moved, 0.0, 0.0)

    def _debit(self, from_p, from_e, spend=True):
        """Take payments due in P and in E from each person's own balances (participants hold both).

        Each unit is used first for payments in that unit; a shortfall is
        converted from the other unit at the person's conversion rate. A
        balance may go negative here; ``_cover`` settles that afterwards.

        ``spend`` (a record only, MicroVelocity): a payment to someone
        else, added to each payer's month's outflow (``acc["outflow"]``), the
        whole amount the debit takes from its E and P, conversion fee
        included. The dealing's move of a person's own money into its savings
        and pool shares is not spending and passes ``spend=False``; the
        conversion fee such a move pays is paid to an outsider, so the fee
        alone is outflow, never the principal
        moved between the person's own balances. No rule reads the outflow.
        Example: a debit of 3 in P and 2 in E from a person holding 5 in P
        and nothing in E, at a conversion rate of 1%, takes 3 + 2 x 1.01 =
        5.02 and adds 5.02 to its outflow; the same debit with
        ``spend=False`` adds only the fee, 0.02.
        """
        if not (np.any(from_p) or np.any(from_e)):
            # Nothing to take (about a third of the calls): every step below would add or take zeros, which changes no
            # balance or record, so it is skipped (a speed device that changes no value).
            return
        rate = self._rate()
        take_p = np.minimum(from_p, np.maximum(self.pcash, 0.0))
        take_e = np.minimum(from_e, np.maximum(self.cash, 0.0))
        rest_p, rest_e = from_p - take_p, from_e - take_e
        outflow = getattr(self, "acc", {}).get("outflow")   # absent only where a test builds a partial month
        if outflow is not None:
            outflow += (take_p + take_e + (rest_p + rest_e) * (1 + rate) if spend else (rest_p + rest_e) * rate)
        self.pcash -= take_p + rest_e * (1 + rate)
        self.cash -= take_e + rest_p * (1 + rate)
        self._fee((rest_p + rest_e) * rate)
        # P issued for P payments made from E; P redeemed, with its fee, for E payments made from P.
        self.reserves += float((rest_p - rest_e * (1 + rate)).sum())
        self._crossed(rest_p, rest_e, rate)

    def _credit_p(self, who, amount):
        """Credit P: participants hold it; anyone else redeems it to E at the conversion fee."""
        held = self.part[who]
        np.add.at(self.pcash, who, np.where(held, amount, 0.0))
        np.add.at(self.cash, who, np.where(held, 0.0, amount * (1 - self.conversion)))
        self._coin_in(np.where(held, amount, amount * (1 - self.conversion)), who)   # a record only (``_coin_day``)
        self.reserves -= float(np.sum(np.where(held, 0.0, amount)))   # P paid to a non-participant is redeemed
        fee = np.zeros(self.n)
        np.add.at(fee, who, np.where(held, 0.0, amount * self.conversion))
        self._fee(fee)
        # The redemptions as conversions (reported only), summed apart so the fee's arithmetic is unchanged.
        redeemed = np.zeros(self.n)
        np.add.at(redeemed, who, np.where(held, 0.0, amount))
        self._crossed(0.0, redeemed, self.conversion, conversion=True)

    def _cover(self):
        """End-of-step clean-up: refill a negative balance from the other unit, then book any rest as overdraft.

        The overdraft is outside credit at r_ext. It is held in
        ``od_pending`` and booked as a loan by ``_book_overdrafts`` so no caller
        holds a stale view of the loan book.
        """
        self._consolidate()
        if not (np.signbit(self.cash).any() or np.signbit(self.pcash).any()):
            # No balance is negative (nor a negative zero): nothing is refilled or overdrawn, and every step below
            # would add zeros to balances and records that are never a negative zero, so it is skipped (a speed device
            # that changes no value; the second consolidation would move nothing).
            return
        rate = self._rate()
        x = np.minimum(np.maximum(-self.cash, 0.0), np.maximum(self.pcash, 0.0) / (1 + rate))
        y = np.minimum(np.maximum(-self.pcash, 0.0), np.maximum(self.cash, 0.0) / (1 + rate))
        self.cash += x - y * (1 + rate)
        self.pcash += y - x * (1 + rate)
        od_e, od_p = np.maximum(-self.cash, 0.0), np.maximum(-self.pcash, 0.0)
        self.cash += od_e
        self.pcash += od_p
        self._fee((x + y + od_p) * rate)
        # Records only (``_coin_day``): the overdraft drawn is money received; the fee on refilling one unit from the
        # other leaves the person's money without being in the outflow, a removal.
        self._coin_in(od_e + od_p)
        self.coin_flow[1] += (x + y) * rate
        # P redeemed to refill E, issued to refill P from E or from an overdraft.
        self.reserves += float((y - x * (1 + rate) + od_p).sum())
        self._crossed(y + od_p, x, rate)
        self.od_pending += od_e + od_p * (1 + rate)
        self._consolidate()
        # Overdraft is financing, not a trade flow, so it is excluded from the buffer replay. During dealing and close
        # ``today`` still refers to the last day of the previous month; adding to it there has no effect.
        if hasattr(self, "today"):
            self.today["financing"] += od_e + od_p

    def _book_overdrafts(self):
        """Book the step's overdrafts as outside debt at r_ext (deferred so no caller holds a stale loan book)."""
        who = np.flatnonzero(self.od_pending > EPS)
        owed = self.od_pending[who]
        self.od_pending[:] = 0.0
        self._add_loans(who, False, OVERDRAFT, owed, self.inputs.r_ext, self.inputs.r_ext, BIG)

    def _pay(self, idx, payable, budget):
        """Pay records idx their payable amounts from each borrower's budget.

        Priority: fee debt (interest-free), then overdue
        instalments, then the dearest outside debt, then pool bridging;
        interest due before principal. The pool is paid in P and outside
        lenders in E, converting only what one unit lacks.
        """
        bk, acc, n = self.book, self.acc, self.n
        keep = payable > EPS
        idx, payable = idx[keep], payable[keep]
        if idx.size == 0:
            return
        owner, pool, term = bk["borrower"][idx], bk["pool"][idx], bk["kind"][idx] == TERM
        # Priority classes: -1 fee debt, 0 overdue instalments, 1 outside debt (dearest rate first), 2 pool bridging.
        # Fee debt is repaid first from receipts, read as first in every repayment the engine makes: the dealing's
        # from all money and each day's from money above the buffer. A receipt that leaves money below the buffer is
        # not taken for the fee, as a bank would net a deposit against a negative balance; instalments due today are
        # still collected from all cash before anything else (``_instalments``), and overdue wages are still paid
        # (``_wage_arrears``) before these debts.
        # What is due (a missed instalment, a bridge that has reached its due date) is collected from all the
        # borrower's money at the day's end, before overdue wages and the repayment from money above the buffer
        # (``_collect_due``); that call passes only those records, in this order. The monthly dealing does the same
        # first for what was due before its day, then pays overdue wages and then every debt, both from all money
        # (``_dealing``). With no fee debt booked the order is otherwise unchanged.
        cls = np.where(bk["kind"][idx] == FEE_DEBT, -1, np.where(term, 0, np.where(pool, 2, 1)))
        paid = allocate(owner, payable, (bk["due"][idx], -bk["rate"][idx], cls), budget)
        # Interest is paid before principal; for a term loan only interest already due counts.
        interest_payable = np.where(term, bk["interest_due"][idx], bk["interest"][idx])
        pi = np.minimum(paid, interest_payable)
        bk["interest"][idx] -= pi
        bk["interest_due"][idx] = np.maximum(bk["interest_due"][idx] - pi, 0.0)
        bk["principal"][idx] = np.maximum(bk["principal"][idx] - (paid - pi), 0.0)
        # What is paid on the card's balances counts towards the next minimum payment, as a payment received before
        # the due date does (``_minimum_paid``).
        kind = bk["kind"][idx]
        on_card = ~pool & (_is_kind(kind, (REVOLVE, CASH_ADVANCE))
                           | ((kind == BRIDGE) & (bk["rate"][idx] == bk["alt"][idx])))
        self.card_paid += np.bincount(owner, weights=paid * on_card, minlength=n)
        # The pool is repaid in P, outside lenders in E. What is paid on the card, its charged-off balance included,
        # clears the card's fees and interest not yet paid first (``_card_edge``); a payment on any other
        # loan clears that loan's own accrued interest, in the book above.
        self._debit(np.bincount(owner, weights=paid * pool, minlength=n),
                    np.bincount(owner, weights=paid * ~pool, minlength=n))
        self._card_edge(paid=np.bincount(owner, weights=paid * (on_card | (~pool & (kind == CHARGED_OFF))),
                                         minlength=n))
        self._cover()
        self.pool_cash += paid[pool].sum()
        # A payment on a written-off pool loan is recovery income: it raises NAV, a valuation gain.
        back = pool & ~bk["carried"][idx]
        recovered = paid[back].sum()
        self.valuation += recovered
        acc["recovered"] += recovered
        acc["lost"] -= np.bincount(term[back].astype(int), weights=paid[back], minlength=2)
        self._by_loan_year(idx[back], paid[back])   # reported: the recovery by product and loan year
        acc["interest_collected"] += pi[pool].sum()
        # Recoveries credited: interest_collected already holds a recovery's interest; its principal
        # is kept apart for the old ratio's numerator (a record only).
        acc["recovered_principal"] += float((paid - pi)[back].sum())
        cleared = term & (self._overdue(idx) <= EPS)
        bk["since"][idx[cleared]] = BIG

    def _repay(self, budget):
        """Repay whenever able from ``budget``: fee debt, overdue instalments, then bridging and revolving debt.

        Term principal is never prepaid; it is collected only as instalments fall due.
        Each day ``budget`` is the money above the buffer, which repays every
        debt in this order whether due or not; before it, what is due (a
        missed instalment, a bridge that has reached its due date) is
        collected from all the borrower's money (``_collect_due``). At the
        monthly dealing ``budget`` is all the
        borrower's money, and there too what was already due
        before the dealing day is collected first, then overdue wages are
        paid, and only then does this run (``_dealing``).
        Example: a borrower with 1 at the dealing, a bridge of 1 due
        yesterday and a dearer one not yet due pays the due one there, so
        this finds nothing left for the dearer one.
        """
        bk = self.book
        idx = np.arange(bk["borrower"].size)
        payable = np.where(bk["kind"] == TERM, self._overdue(), bk["principal"] + bk["interest"])
        self._pay(idx, payable, budget)

    def _collect_due(self, t):
        """Everything that is due is collected from all the borrower's money.

        A bridge falls due on its covering date, the day the borrower's
        receipts are expected to repay it, so from then on it is collected
        from all cash, then same-day savings, as instalments falling due are
        (``_instalments``), in every arm and for every lender: pool, card and
        Comet bridges alike. Otherwise a borrower holding cash below its
        buffer would stay past due and the arrears test would refuse its next
        credit. An instalment that was missed is due too, so it is collected
        here with the due bridges, every day until it is paid. If it had all
        the borrower's money only on the day it fell due and afterwards only
        the money above the buffer, a due bridge would take the money, the
        missed instalment would wait behind the buffer, the borrower would stay
        in arrears and the whole loan would be written down at 90 days; the
        pool's losses would then sit on its instalment loans alone (development
        seeds, M1, a0 0.2 and 0.6: the instalment coupon rises from about 7%
        to 8.2 to 9.0%, so the pool lends 13 to 19% fewer instalment loans).

        It runs at the day's end, after the day's payments and the card
        statement, so the receipts expected on the due date have arrived, and
        before overdue wages and the repayment from money above the buffer:
        what is due ranks ahead of both, as an instalment falling due does.
        On the development seeds (M1, a0 0.2), collecting a due bridge after
        overdue wages leaves 23.5% of pool bridge principal past due and
        collecting it first 4.6%, with overdue wages outstanding no higher
        (19.6 against 20.1 dollars a person). Among
        what is due ``_pay``'s standing order holds: overdue instalments,
        then outside bridges, dearest first, then pool bridges; interest
        before principal. So a missed instalment ranks ahead of a due bridge,
        as it does on the day it falls due, when ``_instalments`` collects it
        in the morning and this collects the bridge at the day's end. The
        day's own cash flow is recorded before it, so the buffer replay sees
        neither the bridge drawn nor its repayment. A card statement's unpaid
        part is revolving debt with no due date, so it is not collected here;
        only card bridges are.
        """
        bk = self.book
        due = np.where(bk["kind"] == TERM, self._overdue(),
                       np.where((bk["kind"] == BRIDGE) & (bk["due"] <= t), bk["principal"] + bk["interest"], 0.0))
        idx = np.flatnonzero(due > EPS)
        if idx.size == 0:
            return
        payable = due[idx]
        owed = np.bincount(bk["borrower"][idx], weights=payable, minlength=self.n)
        self._use_savings(owed - np.maximum(self.cash + self.pcash, 0.0))
        self._pay(idx, payable, np.maximum(self.cash + self.pcash, 0.0))

    def _wage_arrears(self, budget):
        """Debts first: overdue wages are paid, oldest first, from the payer's budget.

        Without this, a payer could keep savings while its wages stayed unpaid,
        and recipients would spend against receivables never collected. An
        overdue wage paid repays the earner's advances against it first.
        An overdue wage of an extra layoff (the harsh stress) is
        paid the same way, in the same order, and leaves the household economy:
        nobody receives it, so it is no wage paid and repays no advance.
        """
        inputs, n, ob = self.inputs, self.n, self.ob
        idx = np.flatnonzero((ob["kind"] == LATE_WAGE) | (ob["kind"] == LATE_OUTSIDE_WAGE))
        if idx.size == 0:
            return
        b, s, owed = ob["buyer"][idx], ob["seller"][idx], ob["amount"][idx]
        kept = ob["kind"][idx] == LATE_WAGE   # paid to its worker; the rest is paid to the outside
        # P payments do not depend on the pool: in the pool arms they settle whenever P is issued, after
        # launch. Each costs its payer one transfer's gas, the share it completes of it. A wage
        # paid to the outside goes by debit, never in P.
        p_route = self.part[b] & self.part[s] & self.launched & (self.economy.routing == "all") & kept
        gas_rate = np.where(p_route, self.gas / np.maximum(owed, EPS), 0.0)
        paid = allocate(b, owed * (1 + gas_rate), (ob["settle"][idx],), budget)
        paid /= 1 + gas_rate
        gas = gas_rate * paid
        self._debit(np.bincount(b, weights=(paid + gas) * p_route, minlength=n),
                    np.bincount(b, weights=paid * ~p_route, minlength=n))
        self._cover()
        self._receive(s[kept], paid[kept], p_route[kept])
        # Each job's wages paid to its recipient this month, on time or late, which next month's budget expects on
        # that job's pay dates.
        self.acc["wages_paid"] += np.bincount(b[kept], weights=paid[kept], minlength=n)
        if self.economy.earned_wage_share > 0:
            # The advance is collected from its own job's wage only, paid on time or late, never from the earner's
            # other receipts.
            self._repay_advances(b[kept], s[kept], paid[kept], p_route[kept])
        # A late wage paid in P counts as the share of what it still owed that this payment completed, as ``_settle``
        # counts a payment, and pays that share of its gas.
        count = np.divide(paid, owed, out=np.zeros(paid.size), where=owed > EPS) * p_route
        self._pay_gas(b, gas)
        self.acc["p_n"] += float(count.sum())
        self.acc["p_value"] += float(paid[p_route].sum())
        np.subtract.at(self.receivable, s[kept], paid[kept])   # a wage paid to the outside was nobody's receivable
        np.subtract.at(self.payable, b, paid)
        ob["amount"][idx] -= paid
        # Fully paid entries leave the obligation list. They are almost always a leading block (the days already
        # settled), and then the list is kept as a view past it, with no copy.
        keep = ob["amount"] > EPS
        first = int(keep.argmax()) if keep.size else 0
        if keep[first:].all():
            self.ob = {key: value[first:] for key, value in ob.items()}
        else:
            self.ob = _take(ob, keep)

    def _repay_advances(self, job, payee, paid, p_side):
        """Earned-wage advances repaid at source: the wage payments just received, ``paid`` by
        ``job`` (its payer) to ``payee``, repay what the earner owes on advances against that job, before the earner
        can use the money, in the unit each was paid in. Returns what each person repaid.

        The provider sits outside the economy, so a repayment made in P (a wage routed in P, routing "all") is
        redeemed: the reserves behind it go too (no rule reads them).
        """
        n = self.n
        wage_paid = np.bincount(job, weights=paid, minlength=n)
        repay = np.minimum(self.ewa_owed, wage_paid)
        taken = np.divide(repay, wage_paid, out=np.zeros(n), where=wage_paid > EPS)[job] * paid   # each payment's part
        in_p = np.bincount(payee, weights=taken * p_side, minlength=n)
        self._debit(in_p, np.bincount(payee, weights=taken * ~p_side, minlength=n))
        self.reserves -= float(in_p.sum())
        self.ewa_owed -= repay
        # The repayment pays each advance's fee before the advance: the fees still owed, by job, never
        # above what the job's earner owes on its advances.
        self.ewa_fee_owed = self.ewa_fee_owed - np.minimum(self.ewa_fee_owed, repay)
        return np.bincount(payee, weights=taken, minlength=n)

    def _receive(self, who, amount, p_side):
        """Credit receipts in the unit they were paid in; ``_consolidate`` then moves a participant's E into P.

        ``acc["receipts"]`` records gross receipts (income) for the income-volatility check.
        """
        self._credit_p(who[p_side], amount[p_side])
        np.add.at(self.cash, who[~p_side], amount[~p_side])
        self._coin_in(amount[~p_side], who[~p_side])
        np.add.at(self.acc["receipts"], who, amount)

    # ----- the age of money (MicroVelocity): records only, read by no rule ----------------------------------
    def _coin_in(self, amount, who=None):
        """Record money a person receives from others (new units dated today): ``amount`` per person, or per payment
        to ``who``. A record only."""
        if who is None:
            self.coin_flow[0] += amount
        else:
            np.add.at(self.coin_flow[0], who, amount)

    def _coin_net(self, change, row=1):
        """Record a change of each person's money that is not a payment between persons: a rise is a receipt, a fall
        a removal (``row`` 1, by the convention) or CPI's pro rata loss (``row`` 2). A record only."""
        self.coin_flow[0] += np.maximum(change, 0.0)
        self.coin_flow[row] += np.maximum(-change, 0.0)

    def _coin_day(self, t):
        """Hand one day's receipts, spending, removals and CPI loss to the money's ages (``Coinage``), a record only.

        Spending is exactly the day's outflow (``acc["outflow"]``, ``_debit``). Each person's money is E, P and
        outside savings, so a move among them is no flow and the unit keeps its age. The reconciliation, opening money
        plus receipts less spending, removals and CPI loss less closing money, is added to ``coin_gap`` (zero when
        every flow is recorded). Example: a person with 10 who receives 3 and pays 4 today, with no removal, closes
        with 9 and leaves a gap of 10 + 3 - 4 - 9 = 0."""
        spend = self.acc["outflow"] - self.coin_mark
        self.coin_mark = self.acc["outflow"].copy()
        stock = self.cash + self.pcash + self.savings
        inflow, removal, scale = self.coin_flow
        self.coin_gap += self.coin_open + inflow - spend - removal - scale - stock
        self.coin.step(t, inflow, spend, removal, scale)
        self.coin_open = stock
        self.coin_flow = np.zeros((3, self.n))

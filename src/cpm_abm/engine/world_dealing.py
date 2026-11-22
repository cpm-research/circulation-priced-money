"""The monthly dealing.

Buffers and the dealing's records, the issuer's books and stay test, M0's Comet rates, pool owners (realised
returns, entry, exits and the pool's wind-down) and joining and leaving P under the leaving rule.
"""
import numpy as np

from cpm_abm.comet import load_pin, rate as comet_curve
from cpm_abm.engine.constants import (CONSUMER_UNITS, DAYS, EPS, EWA_FEE, EXIT_NOTICE_MONTHS, FAIL_FEE, LABOUR_SHARE,
                                      MONTH_USD, OWN_RETURN_MONTHS, RATE_TIE, SECONDS_PER_MONTH, STAY_MONTHS)
from cpm_abm.engine.rates import logistic, own_returns, own_window
from cpm_abm.engine.lending_rules import choose_buffer, reviewed_buffer


class DealingMixin:
    """The monthly dealing, one part of ``_World``: buffers, the issuer's books and stay test, M0's Comet rates,
    pool owners' entry and exits and the pool's wind-down, and joining and leaving P."""

    def _dealing(self, month):
        """Monthly dealing, in this order:

        1. Outside savings mature back into cash.
        2. Owners file to exit, with the two-month notice, by the users'
           leaving rule (decided 5 Nov): a reviewing owner leaves with the
           logistic probability of its 12-month realised return gap in dollars
           against its own outside rate, rho_H plus the owners' spread,
           falling short of its leaving cost spread over 12 months
           (``_exits``; standing requests); capital already above N* (``Q``)
           stays (the 5 Nov review); payouts are limited by pool cash, and
           the accepted offers of step 5 buy the executed exits pool cash
           left unpaid before taking room up to N*. The money offered that
           found no room is kept (``unused_offers``): new subscriptions pay
           leaving owners first (decided 12 Nov), so the month's lending
           sets aside cash only for the next dealing's due exits beyond it
           (``_cash_for_loans``).
        3. Debts first, from all money (savings released in step 1 included):
           what was already due before today, a missed instalment or a
           bridge past its due date (``_collect_due``, decided 12 Nov:
           what is due ranks first), then overdue wages, then every debt,
           due or not, in ``_pay``'s standing order (``_repay``). A bridge
           falling due on the dealing day itself is not collected here but
           at that day's end, after the day's receipts. Hand case: savings
           of 1, a bridge of 1 due on day 29 at 1% and a dearer one due on
           day 45 at 2%, dealing on day 30: the due bridge is paid and the
           dearer current one is not.
        4. Buffer replay: each person picks its buffer from its own last month.
        5. Spare money splits by the person's own deposit and money-market mix
           (one savings rule, decided 1 Nov). The money-market part goes to
           pool shares while the quote (plus CPI in M2) is at least the
           person's own outside rate (decided 4 Nov, the rule as first set
           out that day; now section (Entry and exit) of paper/cpm.tex),
           accepted pro rata up to N*, and otherwise to one-month outside
           savings; the deposit part stays as cash if the cash pays at least
           what deposits pay (P's published yield, net of demurrage, 5 Nov; in
           M0 USDC's savings rate), else it is saved at the deposit rate.
           Only a saver reviewing entry this month offers (decided 13 Nov:
           probability upsilon, ``_reviews_entry``), and an owner with a
           standing exit request or paid out at this dealing offers nothing
           (``_no_offer``); a saver that does not offer places its money-market
           part in outside savings.

        The quote entry reads is the one at N* (``R_hat``): entry stops at N*,
        where the quote is owners' alternative exactly while F > 0 (the
        free-entry equilibrium, 5 Nov). Capital already above N* stays (the
        5 Nov review: no pro-rata return), so after a fall in N* capital can
        exceed it until exits bring it down. A household's own outside rate is
        that alternative in nominal terms, so households invest up to N* while
        F > 0. Exits read no quote: each owner reads its own realised return
        (``_exits``), not a comparator common to every owner (the 5 Nov
        review), so owners who bought at different times or are paid in
        different units can read differently. Reading the quote at
        N* rather than at the capital the
        dealing leaves is a reading of the rule (4 Nov): it
        leans against CPM wherever own rates differ, and changes nothing where
        they are all rho_H plus the spread. The quote is the decided rule; under
        the sensitivity ``Economy.entry_reads`` "realised" (decided 11 Nov:
        the entry check) entry reads the pool's trailing realised return
        (``_track_record``) instead, and the quote while there is none.

        Returns the pool capital (owners' NAV) after dealing.
        """
        inputs, n, last, acc = self.inputs, self.n, self.last, self.acc
        self.cash += self.savings
        self.savings[:] = 0.0
        owners = self.shares > EPS
        self.exit_unpaid = np.zeros(n)
        self.exit_paid_out = np.zeros(n, bool)
        if owners.any():
            self._exits(month, owners)
        # An owner with a standing exit request (filed and not lapsed), or paid out at this dealing, offers nothing at
        # it (``_no_offer``): shares bought after filing would skip the notice and draw cash nobody set aside.
        no_offer = self._no_offer()
        # A dealing whose exits wind the pool down takes no entry; once its last share is paid out the pool is open
        # again from the next dealing (decided 5 Nov: free entry applies in every month).
        winding = self.winding
        self._clean_shares()
        # What was already due before today (a missed instalment, a bridge past its due date) is collected first, from
        # all money, ahead of overdue wages and debts not yet due (decided 12 Nov; the 13 Nov review).
        # A bridge falling due today is left to this day's end (``_collect_due``), after the day's receipts.
        self._collect_due(month * DAYS - 1)
        self._wage_arrears(np.maximum(self.cash + self.pcash, 0.0))
        self._repay(np.maximum(self.cash + self.pcash, 0.0))
        liquid = self.cash + self.pcash
        open_pool = bool(self.launched and not winding and np.isfinite(self.R_hat)
                         and self.Q > 0)
        pool_nominal = self.R_hat + self.index
        # The money-market part is offered to the pool while the quote is at least the person's own outside rate; ties
        # invest (RATE_TIE: at N* the two are equal but for rounding).
        # Under the sensitivity ``entry_reads`` "realised" (decided 11 Nov: the entry check) entrants compare the
        # pool's own track record, plus CPI in M2 as the quote has, instead of the quote; with no track record they read
        # the quote. Everything below reads ``invest`` and ``pool_nominal`` as built.
        entry_nominal = pool_nominal
        if self.economy.entry_reads != "quote":
            record = self._track_record(month)
            if np.isfinite(record):
                entry_nominal = record + self.index
        invest = open_pool & (entry_nominal >= self._owners_alternative_nominal() - RATE_TIE)
        if self.economy.entry_reads == "leaving_rule":
            # The third reading (decided 12 Nov): each saver reads the same record with the leaving rule's own
            # dispersion, on the dollars a month its money-market money at hand would gain or lose (``_enters``): its
            # money above the buffer it last chose (at least EPS, so with nothing at hand the gap keeps its sign).
            # A saver with no noise reads the realised predicate itself (``invest`` as just computed), not the sign of
            # the dollar gap, so the two readings agree exactly at the tie cutoff (13 Nov review).
            at_hand = np.maximum((liquid - self.buffer) * self.mm_share, EPS)
            gap = (entry_nominal - self._owners_alternative_nominal() + RATE_TIE) * at_hand
            noisy = self.inputs.noise * self.economy.leave_noise * self.spending > 0
            invest = open_pool & np.where(noisy, self._enters(month, gap), invest)
        # Savers review entry at the users' rate (decided 13 Nov): only a person whose entry-review draw is below
        # upsilon offers this month, under every entry reading; a person with a standing exit request or paid out at
        # this dealing offers nothing. A person who does not offer places its money-market part in outside savings
        # below, and shares it already holds stay.
        invest = invest & self._reviews_entry() & ~no_offer
        # The return a person forgoes by holding money as a buffer: its own mix's return, with the money-market part at
        # the better of the pool and rho_H.
        alternative = self.r_out + self.mm_share * np.where(invest, pool_nominal - self.pool_alternative, 0.0)
        if self.defi:
            # M0: participants' outside savings earn their own rate plus the premium (zero by default; in the "reserve"
            # mode USDC's savings rate is earned in the wallet, through p_yield, 5 Nov).
            alternative = self.r_out + self.inputs.supply_premium * self.part   # each person's own savings rate
        # The deposit part of spare money stays as the person's own cash when that cash pays at least the deposit rate
        # (below), so the deposit part of a buffer kept in P (or USDC) forgoes that cash's own yield, not the deposit
        # rate (the 5 Nov review): the buffer replay's forgone return adds the gap on the deposit part, and a
        # participant's cost of holding a buffer is mm_share x (rho_H - y_P), never negative. The experience replays
        # keep the alternative for spare money as built (``acc["alternative"]``), with the deposit rate on the deposit
        # part, as the switch back to E would place it: a reading of the rule (5 Nov).
        cash_yield = np.where(self.part, self.p_yield, inputs.buffer_yield)
        keep = cash_yield >= self.deposit_rate                               # ties stay in cash (decided 27 Oct)
        forgone = alternative + np.where(keep, (1 - self.mm_share) * (cash_yield - self.deposit_rate), 0.0)
        if month > 0:
            admitted = np.where(self.part, last["admitted"], 0.0)
            # Replay prices: savings above the buffer pay a shortfall the same day for the outside interest they give
            # up (decided 30 Oct), except money that will be offered to the pool, which a shortfall cannot draw;
            # then shortfall credit at this month's bridging rate r_b (4 Nov) for the share the pool admitted last
            # month, otherwise the card (holders) or failure (no card), with its flat fee priced at the person's average
            # payment and at most one fee a day. Holding a buffer costs the forgone return minus P's own published
            # yield (decided 5 Nov: y_P, net of demurrage on the whole wallet balance, plus M2's indexation; USDC's
            # savings rate in M0), so no charge falls on the idle part apart.
            # M0's crypto collateral holders using USDC borrow from Comet at full cover before the card or failure, as
            # the settlement and the experience replay price it (the 5 Nov review: wherever collateral is drawn, the
            # replay prices it too; it leans against CPM). Known approximation: M2 credit here is the P-terms coupon
            # (experience adds dJ/J), which affects only the buffer choice slightly.
            # Card limits (decided 14 Nov 2026): a holder's shortfall goes to its cash line, up to last month's room
            # each day, at the cash APR and the advance's fee, and beyond the room to earned-wage access and failure
            # as anyone's does.
            cover = self.part * self.cover
            credit = admitted * self.r_b + (1 - admitted) * (cover * self.comet_borrow
                                                             + (1 - cover) * self.holder * self.cash_apr)
            hold = np.where(self.part, forgone - self.p_yield * last["p_share"]
                            - (1 - last["p_share"]) * inputs.buffer_yield, forgone - inputs.buffer_yield)
            flows = np.where(self.part[:, None], last["flows"], last["flows_s0"])
            fail_cost = (1 - admitted) * (1 - cover) * self._fail_rate()
            card = (1 - admitted) * (1 - cover) * self.holder   # the share of a shortfall the cash line prices
            # Money offered to the pool cannot pay a shortfall the same day: the money-market part when it invests.
            drawable = np.where(invest, liquid * (1 - self.mm_share), liquid)
            # Failures past the monthly cap of fees (decided 3 Nov): this replay still prices them at $27, a
            # declared device standing in for the closure and lost service the model omits, for every payer without
            # pool access in every arm (pool members price pool credit, whatever the cap); with the device off, at $0,
            # as the experience replays do (no monthly limit with no monthly cap).
            past_cap = self.economy.buffer_prices_past_cap or not np.isfinite(self.economy.fees_a_month)
            fail_month = None if past_cap else self.economy.fees_a_month * FAIL_FEE
            # Earned-wage access (decided 3 Nov): a payer who holds access advances what the pool did not admit and
            # a holder's cash line did not take (14 Nov 2026), up to last month's room each day, at its fee per unit
            # drawn, before failing.
            advance = advance_rate = None
            if self.economy.earned_wage_share > 0:
                advance = last["ewa_room"]
                advance_rate = (1 - admitted) * (1 - cover) * self.pop["ewa"] * EWA_FEE
            chosen, _ = choose_buffer(flows, self.spending, liquid, credit, hold, fail_cost,
                                      draw_rate=self.r_out, drawable=drawable, fail_cap=FAIL_FEE,
                                      fail_month=fail_month, advance=advance, advance_rate=advance_rate,
                                      card_room=np.where(self.holder[:, None], last["card_room"], 0.0),
                                      card_rate=card * self.cash_apr, card_floor=card * self.advance_floor,
                                      card_fee=card * self.advance_rate)
            self.buffer = reviewed_buffer(chosen, self.buffer, self.economy, month)
        spare = np.maximum(liquid - self.buffer, 0.0)
        # One savings rule for every vehicle (decided 1 Nov): spare money splits by the person's own DFA mix before
        # any vehicle is chosen. The money-market part is offered to the pool while the quote reaches the person's own
        # rate, accepted pro rata up to N*, and otherwise goes to outside savings at rho_H. The deposit part
        # (decided 27 Oct) stays as the person's own cash when that cash pays at least the deposit rate (P: its
        # published yield y_P, net of demurrage, plus M2's indexation, decided 5 Nov; USDC: its savings rate; E:
        # checking), with no deposit cap (4 Nov), and otherwise goes to outside savings at the deposit rate. Shares are
        # P and savings are E. Each draws on its own unit first; only the part converted from the other unit pays the
        # conversion fee, out of the same spare money, so neither investing nor saving borrows. Under the core
        # convention the fee is zero.
        rate = self._rate()
        mobile = spare * self.mm_share
        own_p, own_e = np.maximum(self.pcash, 0.0), np.maximum(self.cash, 0.0)
        native = np.minimum(mobile, own_p)
        offer = np.where(invest, native + (mobile - native) / (1 + rate), 0.0)
        # Room (decided 30 Oct): N* less every pool share at NAV, all households' since the issuer is a pure
        # custodian (decided 5 Nov), so entry never takes capital after dealing above N*; capital already above it
        # stays (the 5 Nov review) and takes no entry. N* is unbounded only where idle cash earns the alternative itself
        # (``paper_capital``), and then every offer is accepted.
        # Offers first buy the executed exits pool cash left unpaid, at NAV (decided 5 Nov: subscriptions meet
        # redemptions, as in an open-ended fund), which leaves capital where it was, and only the rest takes room up
        # to N*.
        due = float(self.exit_unpaid.sum())
        room = max(self.Q - self._all_shares() * self.nav_ps, 0.0) + due
        accepted = offer * min(1.0, room / offer.sum()) if offer.sum() > 0 else offer
        # New subscriptions pay leaving owners first (decided 12 Nov): the money offered that found no room is
        # what the month's lending counts on to buy the exits falling due at the next dealing (``_cash_for_loans``).
        self.unused_offers = max(float(offer.sum() - accepted.sum()), 0.0)
        self.acc["offers"], self.acc["offers_unused"] = float(offer.sum()), self.unused_offers   # records only
        converted = np.maximum(accepted - own_p, 0.0) * (1 + rate)          # E spent buying P for shares
        mobile_left = np.maximum(mobile - np.minimum(accepted, own_p) - converted, 0.0)
        deposit = np.where(keep, 0.0, spare - mobile)                       # the deposit part kept stays as cash
        placed = mobile_left + deposit
        # The month's savings earn rho_H on the money-market part placed and the deposit rate on the deposit part.
        self.saving_rate = np.divide(mobile_left * inputs.rho_H + deposit * self.deposit_rate, placed,
                                     out=self.r_out.copy(), where=placed > EPS)
        e_left = np.maximum(own_e - converted, 0.0)
        to_savings = np.minimum(placed, e_left) + np.maximum(placed - e_left, 0.0) / (1 + rate)
        self._debit(accepted, to_savings, spend=False)   # own money into own savings and shares: only the fee is outflow
        self.coin_flow[1] += accepted   # a record only (``_coin_day``): pool shares bought remove money unspent
        self._cover()
        self._book_overdrafts()
        self.shares += accepted / self.nav_ps
        self.pool_cash += accepted.sum()
        bought = min(float(accepted.sum()), due)
        if bought > EPS:
            # The new money pays the due exits pro rata at this NAV, in P, as pool cash pays them (``_exits``).
            pay = self.exit_unpaid * (bought / due)
            self.shares = np.maximum(self.shares - pay / self.nav_ps, 0.0)
            self.pool_cash -= bought
            self._credit_p(np.arange(n), pay)
            # Only requests still standing are paid here (every unpaid executed exit has one), so no request is opened
            # for an owner who filed none: one paid out in full above has none left.
            self._track_exits(month, self.exit_want & (self.exit_start >= 0), pay)
            acc["exit_paid"] += bought
        self.savings += to_savings
        # Reported only (3 Nov, M2's savings held in P): the deposit part of spare money kept as the person's own cash.
        acc["deposit_kept"] = np.where(keep, spare - mobile, 0.0)
        acc["alternative"] = alternative
        acc["drawable"] = self.cash + self.pcash + self.savings   # what the month's shortfalls can draw on the same day
        capital = float(self._all_shares() * self.nav_ps)
        self.held_path[month] = self.shares * self.nav_ps   # what later exits read (``_own_return``, 3 Nov)
        self._holdings()
        self.owners_queued = self._queued()
        return capital

    def _holdings(self):
        """Each household's pool capital after dealing (reported only, decided 3 Nov). Households alone own the
        pool (decided 5 Nov: the issuer is a pure custodian), so their capital is all of it. All shares carry one
        NAV and change only in dealing, so it holds through the month to the close. No rule reads it (4 Nov)."""
        self.owners_held = self.shares * self.nav_ps

    def _queued(self):
        """Households' capital in exit requests filed and still unpaid after this dealing (reported only, decided
        4 Nov: the 90% household test reads capital net of queued exits, the base that leans against CPM, with the
        decided record's base, all pool capital, beside it), at this dealing's NAV, on the shares still to pay.

        A request is queued from its filing, within its notice as well as executed and unpaid, which takes the most
        from households' side of the reading: a reading of the rule (4 Nov). A request that lapsed
        has left the queue."""
        filed = self.exit_start >= 0
        return float((np.minimum(self.exit_left, self.shares) * self.nav_ps)[filed].sum())

    def _buffers(self):
        """Each person's buffer chosen at this month's dealing, and its mean among people without a card and among card
        holders, NaN for a group with nobody (reported only, the 3 Nov review), in months of mean spending.

        Nothing between the dealing and the close changes the buffer; in the first month, before any replay, it is
        the starting cash. No rule reads the record. Means by card holding (decided 4 Nov), by each person's class,
        the population's holding, which a closed line does not change (14 Nov 2026).
        """
        mean = lambda group: float(self.buffer[group].mean()) if group.any() else np.nan
        holder = self.pop["holder"]
        return self.buffer, mean(~holder), mean(holder)

    def _all_shares(self):
        """Every pool share outstanding, all households' (decided 5 Nov: the issuer holds none)."""
        return float(self.shares.sum())

    def _own_return(self, month):
        """Each household's own realised return a month since buying, over at most 12 months, net of issuer money, on
        the NAV basis and before CPI (decided 3 Nov), as this dealing's exits read it: ``own_returns``, the
        record's own definition, on the capital after dealing (``held_path``) and R (``r_owners``) of the closed
        months before this one, so a holding bought at the last dealing reads its one month. NaN where the person held
        nothing last month."""
        start = max(month - OWN_RETURN_MONTHS, 0)
        if month <= start:
            return np.full(self.n, np.nan)
        return own_returns(self.held_path[start:month], self.r_owners[start:month], OWN_RETURN_MONTHS)[-1]

    def _track_record(self, month):
        """The pool's trailing realised return a month, read by entry under the sensitivity ``entry_reads`` "realised"
        (decided 11 Nov: the entry check; "quote" is the decided rule): the mean of the monthly return on a unit of
        pool capital (``r_owners``, the series exits read) over the last OWN_RETURN_MONTHS closed months before this
        dealing, each month weighted by the pool capital after its dealing (``held_path`` summed over people), on the
        NAV basis and before CPI. Only months with pool capital and a finite return count. NaN when no month does (the
        launch dealing, or a pool emptied by a wind-down): there is no track record, and entry reads the quote."""
        start = max(month - OWN_RETURN_MONTHS, 0)
        capital = self.held_path[start:month].sum(axis=1)
        rate = self.r_owners[start:month]
        counted = (capital > EPS) & np.isfinite(rate)
        if not counted.any():
            return np.nan
        return float((capital[counted] * rate[counted]).sum() / capital[counted].sum())

    def _enters(self, month, gap):
        """Who offers money to the pool under the third entry reading, ``entry_reads`` "leaving_rule" (decided
        12 Nov), for every person at once: a saver offers when its draw, on a stream of its own for the month, is at
        least the decided leaving rule's probability (``_leave_chance``, no threshold) of leaving at the same gap, so
        it enters with probability logistic(gap / scale), the scale 1e-4 of its own monthly spending times
        ``Economy.leave_noise``, as owners leave. ``gap`` is the dollars a month, in the model's money, by which the
        pool's record (the quote while there is none) exceeds the saver's own alternative on its money-market money
        at hand. At no gap half the savers offer; with no noise everyone offers exactly when the gap is not negative,
        which is the "realised" reading; ``_dealing`` uses the realised comparison itself for a saver with no noise, so
        rounding in the dollar gap cannot split the two at the tie cutoff (the 13 Nov review). Hand case: an offer of $100 against a record 1 point a year low is a gap of
        -$0.083 a month, and with the scale of $0.64 the saver enters with probability logistic(-0.13) = 0.47."""
        draw = np.random.default_rng(np.random.SeedSequence([self.economy.seed, 37, month])).random(self.n)
        return draw >= self._leave_chance(gap, 0.0)

    def _own_gap(self, month):
        """Each owner's 12-month realised return gap in dollars a month (decided 5 Nov: owners leave by the users'
        rule), as this dealing's exits read it: its own realised return since buying, over at most 12 months
        (``_own_return``), plus CPI in M2, less its own outside rate, rho_H plus the owners' spread, times its mean
        capital over the same months (``own_window``), so the gap a month its holding realised against the alternative,
        in the model's money (months of mean spending), as a user's experience is. NaN where it held nothing last
        month."""
        start = max(month - OWN_RETURN_MONTHS, 0)
        if month <= start:
            return np.full(self.n, np.nan)
        _, _, capital, months = own_window(self.held_path[start:month], self.r_owners[start:month], OWN_RETURN_MONTHS)
        mean = capital[-1] / months[-1]
        return (self._own_return(month) + self.index - self._owners_alternative_nominal()) * mean

    def _exits(self, month, owners):
        """Owners' exits under the two-month notice rule; the issuer is a pure custodian (decided 5 Nov), so every
        share is a household's and exits are paid from pool cash alone.

        Owners leave by the users' rule (decided 5 Nov; it amends the 3 Nov owner exit row's timing): each month a
        share upsilon (0.153 a month, the users' decided review chance) of owners reviews, on a stream of its own
        (``owner_draws``), and a reviewer files a request for its whole holding when its leaving draw falls below the
        decided leaving rule's logistic probability (``_leave_chance``) of its 12-month realised return gap in dollars
        (``_own_gap``) falling short of minus its leaving cost spread over 12 months: logistic((-gap - threshold) /
        scale), the threshold one conversion of the holding at this dealing's NAV for anyone paid in E and nothing for
        a participant, whose payout is credited in P without a fee, over 12 months, and the scale 1e-4 of its own
        monthly spending times ``Economy.leave_noise``, as the users' rule. An owner with no record yet has no reading.
        The first review comes one month after buying, since exits are read before the month's entry. A request stands
        until it executes EXIT_NOTICE_MONTHS later at that month's NAV, so the exiter bears the losses of the notice
        period, unless the owner reviews again within the notice and its draw no longer says leave, when it lapses
        (22 Oct: cancellable): reading a standing request again only at a review is a reading of the rule (5 Nov). A
        winding-down pool pays at once. Capital above N* (``Q``) stays: nobody is
        returned capital pro rata (the 3 Nov quote row; the 5 Nov review). Payment is limited by pool cash; the same
        dealing's accepted offers buy the unpaid part of an executed request (``_dealing``), and what they leave is
        paid later at later NAVs. New subscriptions pay leaving owners first (decided 12 Nov), so the month before
        sets pool cash aside only for the due exits the last dealing's unused offers would not have covered
        (``_cash_for_loans``), and pool cash can be short at the dealing by design. The irreversible wind-down follows
        once every owner's exit is executing (3 Nov: every remaining share has filed).
        """
        acc, n = self.acc, self.n
        value = self.shares * self.nav_ps
        review, leave_draw = self.owner_draws
        gap = self._own_gap(month)
        threshold = np.where(self.part, 0.0, self.conversion) * value / OWN_RETURN_MONTHS
        reviews = owners & (review < self.inputs.upsilon) & np.isfinite(gap)
        leaves = reviews & (leave_draw < self._leave_chance(np.nan_to_num(gap), threshold))
        filed = self.exit_start >= 0
        immediate = bool(self.winding)
        want = owners & (((filed & ~reviews) | leaves) | immediate)
        due = want & (immediate | ((self.exit_start >= 0) & (month - self.exit_start >= EXIT_NOTICE_MONTHS)))
        ending = immediate or bool(due[owners].all())
        # Capital already above N* stays: nobody is returned capital pro rata (the 3 Nov quote row, the 5 Nov free-entry
        # row; the 5 Nov review), which replaced the 30 Oct capacity return. Entry still stops at N* (``_dealing``'s
        # room).
        request = np.where(due, value, 0.0)
        total = request.sum()
        share_paid = min(1.0, self._lendable() / total) if total > 0 else 0.0
        pay = request * share_paid
        acc["exits_filed"] = float((want & ~filed).sum())
        self._track_exits(month, want, pay)
        self.shares = np.maximum(self.shares - pay / self.nav_ps, 0.0)
        self.pool_cash -= pay.sum()
        self._credit_p(np.arange(n), pay)
        acc["exit_requested"] = float(total)
        acc["exit_paid"] = float(pay.sum())
        self.exit_unpaid, self.exit_want = request - pay, want
        self.exit_paid_out = pay > 0
        self.winding = self.winding or ending

    def _reviews_entry(self):
        """Who reviews entry at this dealing (decided 13 Nov; the register row on the pool's published quote and
        entry): a saver reviews with probability upsilon (0.153 a month, the chance owners and users review leaving at),
        when its entry-review draw for the month (``entry_draw``, a stream of its own) is below upsilon, and only a
        reviewer offers its money-market part to the pool. A saver who does not review keeps its position: its
        money-market part goes to outside savings and shares it holds stay. Hand case: draws of 0.1 and 0.5 with
        upsilon 0.153: the first reviews, the second does not."""
        return self.entry_draw < self.inputs.upsilon

    def _no_offer(self):
        """Who may not offer to the pool at this dealing, read after its exits (the register row "An owner files to
        exit, for its whole holding, at a review from one month after buying"): an owner with a standing exit request,
        filed and not lapsed, and an owner paid any part of its holding at this dealing. Its money-market part goes to
        outside savings. Shares bought after filing would otherwise skip the two-month notice and be paid at execution
        from cash nobody set aside. Hand case: an owner files for 10 shares and has money for 5 more at the next
        dealing: it buys none, and is paid 10 at execution."""
        return (self.exit_start >= 0) | self.exit_paid_out

    def _issuer_books(self):
        """The issuer's books for the month (decided 26 Oct; a pure custodian, 5 Nov).

        Profit and loss, one line per job, adding up to the complete wallet: custodian (rho_H on all P its reserves
        back), indexer (minus M2's indexation of that P), float (minus what it pays out of the reserve return,
        decided 5 Nov: rho_p - c_I on wallet P, which its holders receive less demurrage and the pool receives as
        demurrage, and on the pool's own P cash, so custodian, indexer and float leave it s_I rho_p of P, its cost of
        P, in every pool arm) and expenses (3 Nov: its cost of P, 0.24% a year of the P outstanding the custodian line
        earns on; none as built). It holds no pool shares and no support fund and buys no exits (decided 5 Nov), so
        it has no owner or fund line; it is not a payment operator (5 Nov: P payments run on stablecoin rails), so it
        has no fee income and bears no rail. M1 books are nominal and M2 books real. Cash: the month's wallet is paid
        to its owners, who add cash when it is negative. The issuer is outside the household economy, so none of this
        enters the conservation identity.
        """
        # The issuer's expense (decided 3 Nov), negative: its cost of P outstanding. Zero in S0 and M0 (no P from
        # this issuer) and as built.
        holding = 0.0 - self.economy.issuer_cost * self.acc["p_all"]
        lines = dict(custodian=self.inputs.rho_H * self.acc["p_all"], indexer=-self.index * self.acc["p_all"],
                     float=-(self.acc["wallet_yield"] + self.acc["float_pool"]),
                     expenses=holding)   # an expense is negative
        wallet = sum(lines.values())
        return dict(lines, wallet=wallet, owners_in=max(-wallet, 0.0), payout=max(wallet, 0.0),
                    expense_holding=holding)

    def _stay_test(self, wallet):
        """The issuer's stay test for one month since launch (decided 30 Oct): returns this month's reading.

        Every month enters with the issuer's complete wallet per person, with
        or without a pool, its cost of P included (3 Nov).
        From the 12th month the reading is the average
        of the last 12, undefined before. A negative reading records "issuer
        would leave" from that month on; zero counts as staying. The issuer
        keeps operating either way, so the arms stay comparable, and the
        record is falsifier X6 in the report.
        """
        self.issuer_wallets.append(wallet)
        if len(self.issuer_wallets) < STAY_MONTHS:
            return np.nan
        stay = float(np.mean(self.issuer_wallets[-STAY_MONTHS:]))
        self.issuer_leaves = self.issuer_leaves or stay < -EPS
        return stay

    def _comet_rates(self):
        """M0: this month's Comet supply and borrow rates from the pinned curves at the utilisation it causes.

        The pinned USDC market (block 26,214,368) had $381m supplied and $348m
        borrowed. Its borrowers must post crypto collateral, so their demand
        is taken as given. This economy's participants supply their USDC
        balances, scaled from the N people to the US consumer units they
        stand for. Utilisation is outside borrowing over total supply, and
        each rate follows the market's own kinked curve (`comet.rate`).
        """
        pin = load_pin()
        supplied = float(np.maximum(self.pcash, 0.0)[self.part].sum()) * MONTH_USD * CONSUMER_UNITS / self.n
        borrowed, base = pin.getters["total_borrow"] / 1e6, pin.getters["total_supply"] / 1e6
        u = int(min(borrowed / (base + supplied), 1.0) * 1e18)
        monthly = lambda side: comet_curve(u, side) * SECONDS_PER_MONTH / 1e18
        self.p_yield, self.comet_borrow = monthly(pin.supply_curve), monthly(pin.borrow_curve)
        self.acc["utilisation"] = u / 1e18

    def _track_exits(self, month, out, paid):
        """Exit-payment test bookkeeping: value of exit requests by start month, and the part paid within two months.

        A request starts the first month an owner asks to exit; it is valued at
        that month's NAV. Payments count toward its start month if made within
        two months. A request withdrawn within its two months leaves the base
        (it was cancelled, not refused); one withdrawn after its deadline has
        already been missed stays in the base as a failure.
        """
        new = out & (self.exit_start < 0)
        self.exit_start[new], self.exit_nav[new] = month, self.nav_ps
        self.exit_left[new] = self.shares[new]
        self.exit_started[month] += float((self.shares[new] * self.nav_ps).sum())
        withdrawn = (self.exit_start >= 0) & ~out
        cancelled = withdrawn & (month - self.exit_start <= 2)
        np.subtract.at(self.exit_started, self.exit_start[cancelled], (self.exit_left * self.exit_nav)[cancelled])
        self.exit_started[np.abs(self.exit_started) < EPS] = 0.0   # a lapsed request leaves no rounding residue
        paid_shares = np.where(self.exit_start >= 0, np.minimum(paid / self.nav_ps, self.exit_left), 0.0)
        timely = (self.exit_start >= 0) & (month - self.exit_start <= 2) & ~withdrawn
        np.add.at(self.exit_in_time, self.exit_start[timely], (paid_shares * self.exit_nav)[timely])
        self.exit_left = np.where(withdrawn, 0.0, self.exit_left - paid_shares)
        finished = withdrawn | ((self.exit_start >= 0) & (self.exit_left <= EPS))
        self.exit_start[finished] = -1
        self.exit_left[finished] = 0.0

    def _p_need(self):
        """Share of own spending that would settle in P if every counterparty participated.

        Under fee routing only card-eligible service purchases by card
        holders use P; under routing "all" every payment does. Used
        only by the routine-conversion sensitivity.
        """
        if self.economy.routing == "all":
            return np.ones(self.n)
        return (1 - LABOUR_SHARE) * self.card_share * self.holder

    def _join(self, join, share):
        """Joiners convert ``share`` of their E working balance into P, paying the conversion fee once.

        Under the core convention share is 1: the whole working cash
        becomes P, and this one conversion is the switching cost chi.
        The fee is paid to an outsider, so it is added to the person's
        outflow (a record only, the 13 Nov review); the E moved
        into its own P is not. Hand case: 101 of E at a 1% fee becomes 100
        of P and adds 1 to the outflow.
        """
        amount = np.where(join, share * np.maximum(self.cash, 0.0) / (1 + self.conversion), 0.0)
        self.cash -= amount * (1 + self.conversion)
        self.pcash += amount
        self._fee(amount * self.conversion)
        self._fee_outflow(amount * self.conversion)
        self.reserves += float(amount.sum())
        self._crossed(amount, 0.0, self.conversion, conversion=True)

    def _leave(self, leave):
        """Leavers redeem their idle P to E, paying the conversion fee; pool shares and debts persist.

        The fee, paid to an outsider, is added to the person's outflow (a record only, the 13 Nov
        review); the P redeemed into its own E is not. Hand case: 100 of P at a 1% fee becomes 99 of E and adds 1 to the
        outflow."""
        amount = np.where(leave, np.maximum(self.pcash, 0.0), 0.0)
        self.pcash -= amount
        self.cash += amount * (1 - self.conversion)
        self._fee(amount * self.conversion)
        self._fee_outflow(amount * self.conversion)
        self.reserves -= float(amount.sum())
        self._crossed(0.0, amount, self.conversion, conversion=True)

    def _fee_outflow(self, fee):
        """Add a conversion fee each person paid at joining or leaving to its month's outflow (a record only, read by
        no rule; ``acc["outflow"]``, absent only where a test builds a partial month)."""
        outflow = getattr(self, "acc", {}).get("outflow")
        if outflow is not None:
            outflow += fee

    def _leaving(self, experience, balance, contact, review_draw, leave_draw):
        """Who leaves P this month: the leaving rule (decided 21 Oct; the threshold, 3 Nov; the noise,
        4 Nov), for every person at once.

        Each month a participant reviews when its review draw is below upsilon (0.153 a month: the decided review rate
        0.166 as a monthly chance, 1 - exp(-0.166)), and a reviewer leaves when its leaving draw, on a stream of its
        own, is below the core model's logistic probability
        (``logistic``, as in ``core_model.adopt``) of its experience falling short of the threshold:
        logistic((-experience - threshold) / scale). ``experience`` is its average monthly experience over the last 12
        months in P; the threshold is one conversion (the arm's fee, none for USDC in M0) of ``balance``, its average P
        balance over those months, spread over the 12 months; and the scale is the core model's noise, 1e-4 of the
        person's own monthly spending (``Inputs.noise``), times ``Economy.leave_noise`` (1; every result reports 0.5
        and 2 beside it). At experience exactly minus the threshold half the reviewers leave. With no noise
        (``leave_noise`` 0) a reviewer leaves exactly when experience is below minus the threshold, the rule as first
        built. Under the routine-conversion sensitivity the balance is the P its spending would hold, as built, spread
        over the window the same way: a reading of the rule (5 Nov). With a one-cycle window
        (``h4_months`` 0) the spread is over one month.
        """
        months = max(self.economy.h4_months, 1)
        base = self._p_need() * contact * self.buffer if self.economy.routine_conversion else balance
        threshold = self.conversion * np.maximum(base, 0.0) / months
        chance = self._leave_chance(experience, threshold)
        return self.part & (review_draw < self.inputs.upsilon) & (leave_draw < chance)

    def _leave_chance(self, experience, threshold):
        """The decided leaving rule's probability for every person at once (decided 21 Oct; the noise, 4 Nov), the
        part the users' rule (``_leaving``) and the owners' (``_exits``, decided 5 Nov) share: the core model's
        logistic of (-experience - threshold) / scale, the scale 1e-4 of the person's own monthly spending
        (``Inputs.noise``) times ``Economy.leave_noise``; with no noise, 1 exactly when experience is below minus the
        threshold. Experience and threshold are a month, in the model's money."""
        gap = -experience - threshold
        scale = self.inputs.noise * self.economy.leave_noise * self.spending
        noisy = scale > 0
        return np.where(noisy, logistic(gap / np.where(noisy, scale, 1.0)), (gap > 0).astype(float))

    def _clean_shares(self):
        """Wind-down's end: once every share is withdrawn the pool is emptied and open again.

        Any ownerless residual leaves the household sector: pool cash is an
        outside flow, and carried loans become a valuation loss (their later
        repayments are recoveries), so the conservation identity still holds.
        Free entry applies in every month (decided 5 Nov), so the pool is
        not closed for good: the wind-down ends, and households enter again at
        the published quote in any later dealing with a lending need, as at
        launch (``_dealing``).
        """
        if self._all_shares() * max(self.nav_ps, 0.0) < 1e-12 or self.nav_ps <= 0:
            self.winding = False
            # An unpayable operating payable is the provider's loss (the October 2026 draft's ledger appendix, whose
            # port to paper/cpm.tex is pending). Its cost was booked as an outside outflow when incurred; since it is
            # never paid, that booking is reversed.
            self.external += self.pool_payable
            self.pool_payable = 0.0
            bk = self.book
            orphan = bk["pool"] & bk["carried"]
            self.valuation -= float((bk["principal"] + bk["interest"])[orphan].sum())
            bk["carried"][orphan] = False
            self.external -= self.pool_cash
            self.reserves -= self.pool_cash
            self.pool_cash = 0.0
            self.shares[:] = 0.0
            self.nav_ps = 1.0

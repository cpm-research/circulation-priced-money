"""The start of each month.

Layoffs, the distress line cut, the reported job and deficit flags, the month's payment obligations and term-credit
requests, and the pool's terms set from completed observations only: coupons, the charge, the launch plan, the
fixed cost, the capital limit and quote, and the loss each coupon carries.
"""
import numpy as np

from cpm_abm.engine.constants import (BUSINESS_PRODUCT, CARD_CUT, CARD_CUT_LEVEL, CHARGE_OFF_NORMAL, DAYS, EPS,
                                      LABOUR_SHARE, LOSS_CLASSES, LOSS_LAG_MONTHS, OUTSIDE_WAGE, PURCHASE_COUNT_STREAM,
                                      PURCHASE_STREAM, REQUEST_RATE, SERVICE, DROP_STREAM,
                                      SHOCK, SHOCK_ANNUAL, SHOCK_SIZE, TERM_MONTHS, TERM_SIZE, VEHICLE_NEW_SHARE,
                                      VEHICLE_SIZE, WAGE)
from cpm_abm.engine.population import draw_spells, next_billing, spell_law, term_outside_apr
from cpm_abm.engine.rates import charge_off_rates, paper_capital, paper_return
from cpm_abm.engine.ledger import _concat, _take


class MonthMixin:
    """The start of each month, one part of ``_World``: layoffs and line cuts, the month's payment obligations and
    term-credit requests, and the pool's terms set from completed observations only."""

    def _layoffs(self, month):
        """Job loss: each month, each job not already interrupted is laid off with its
        monthly probability, normal job loss (``job_loss``) and in the distress year the distress control's extra rate
        too, times its earner's bracket weight, from a uniform day of the month, for a log-normal number of days
        (``spell_law``: completed lengths consistent with the BLS figures for spells in progress). Normal job loss runs
        in every month, burn-in included (``JOB_LOSS``); with ``job_loss`` 0 and ``completed_spells`` off there is
        no job loss outside the distress year, and those figures read as completed lengths.

        A spell runs its full length, past the distress year if need be. The draws have their own stream per month
        (``draw_spells``), so every arm sees the same draws, and every distress level the same spells before the
        distress year. One uniform per job and month decides at every level, so a level's layoffs contain a lower
        level's in the month they are drawn, and the extra rate adds to normal job loss with the same bracket weight.

        The harsh stress: a layoff is extra when its draw lies at or above the normal rate
        times its weight, so only the distress year has any, and none at level 0. The mark stays with the spell to its
        end, past the distress year if need be (``spell_out``, read by ``_obligations``). A normal layoff that an extra
        spell crowds out, its job being in a spell already, is replaced by the extra one.

        Under random distress years (``Economy.distress_dates`` "random") the
        extra rate applies in every month of the run's distress years (``distress_calendar``) instead of the one dated
        year, on the same layoff stream, so inside each year one uniform per job still decides at every level.
        """
        economy = self.economy
        if economy.distress_dates == "dated":
            first = economy.burn_in + economy.distress_start
            inside = first <= month < first + economy.distress_length
        else:
            inside = bool(self.distressed[month])
        rate = economy.job_loss + (economy.distress if inside else 0.0)
        if rate <= 0:
            return
        rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 19, month]))
        laid_off, start, end, extra = draw_spells(rng, rate * self.layoff_rate, self.spell_end <= month * DAYS,
                                                  month * DAYS, *spell_law(economy),
                                                  normal=economy.job_loss * self.layoff_rate)
        self.spell_start = np.where(laid_off, start, self.spell_start)
        self.spell_end = np.where(laid_off, end, self.spell_end)
        self.spell_out = np.where(laid_off, extra, self.spell_out)

    def _cut_lines(self, month):
        """The distress line cut (``Economy.card_line_cut``, off by default and on in the second run): at the start
        of the distress year each open line falls by its tier's share of the 2008 to 2012 cut times the distress
        level over 2% (``CARD_CUT``), for the rest of the run, or with ``Economy.card_cut_months`` m above 0 for m
        months; the starting balance stays, so a line cut below what is owed on it leaves no room. Under
        ``Economy.card_cut_on`` "room" the share is taken from the line above the starting balance instead,
        line - share x max(line - start, 0), so the cut never leaves a holder without room only because of a balance
        the model never lets it repay. Example: a $1,000 line with a $950 starting balance cut by 32.58% falls to
        $674.20 by default and to $983.71 under "room", $33.71 of room. With the cut off lines are held, and at
        distress level 0 nothing is cut. No random number is drawn and no money moves.

        With m above 0, m months after the cut each line still open returns to what it would have been without the
        cut: lenders restore the lines they cut once the downturn is behind them, as total card lines
        did about ten years after 2008. A line charged off in the meantime stays closed. Nothing but the cut and a
        charge-off moves a line, so undoing the cut's factor on an open line gives back its line from before the cut,
        kept for that (``card_uncut``), which is exact also where the cut took the whole line. Example: a $1,000 deep
        subprime line cut at 2% falls by 32.58% to $674.20 and, still open m months later, is $1,000 again."""
        economy = self.economy
        if not economy.card_line_cut:
            return
        cut = economy.burn_in + economy.distress_start
        if month == cut:
            if economy.card_cut_months > 0:
                self.card_uncut = self.card_line.copy()
            share = np.minimum(CARD_CUT[self.card_tier] * economy.distress / CARD_CUT_LEVEL, 1.0)
            if economy.card_cut_on == "room":
                self.card_line = self.card_line - share * np.maximum(self.card_line - self.card_start, 0.0)
            else:
                self.card_line = self.card_line * (1 - share)
        elif economy.card_cut_months > 0 and month == cut + economy.card_cut_months:
            self.card_line = np.where(self.holder, self.card_uncut, self.card_line)

    def _laid_off_last_day(self, spell):
        """The share of jobs in a spell on the month's last day, reported only: no rule reads it.

        laid_off is the month's average share of job-days in a spell; this is the stock at the month's end, which the
        label of jobs without a wage at month 36 may read instead. Both are kept. ``spell`` flags
        the month's job-days in a spell, each payer's days in order; no random number is drawn.
        """
        return float(spell.reshape(self.n, DAYS)[:, -1].mean())

    def _chronic(self):
        """Payers in chronic deficit, flagged at launch from the burn-in and reported only: no rule
        reads the flag, and it is the same in every arm, whose burn-in is shared.

        A payer is flagged when its spending over the burn-in exceeds the income it received, with a liquid cushion
        below one month of its own bills. Spending is the burn-in months' spending (the obligations each month
        creates), income the gross receipts, the cushion E, P and outside savings at the start of the launch month and
        one month of own bills the launch month's spending. No random
        number is drawn and no money moves.
        """
        received = self.receipts_path[:self.economy.burn_in].sum(axis=0)
        liquid = self.cash + self.pcash + self.savings
        self.chronic = (self.burn_spent > received) & (liquid < self.spending)

    def _purchase_counts(self, month):
        """Each person's number of purchases this month and what each purchase's share of its spending is divided by
        (``Economy.purchases``).

        * "fixed": ``bundles`` purchases for everyone, each 41.7% of spending over ``bundles``. No number
          is drawn here.
        * "poisson_size": a Poisson number with mean ``bundles``, independently for each person and month, each
          purchase still 41.7% of spending over ``bundles``, so the month's total is the count times that size: the
          same on average, more in some months and less in others.
        * "poisson_month": the same Poisson number, a count of zero taken as one, each purchase 41.7% of spending over
          the count, so the month's total is exactly as under "fixed".

        The counts come from a stream of their own (``PURCHASE_COUNT_STREAM``, by month), drawn for every person in
        every arm, so all arms see the same counts. Example, a person with mean spending ($6,440 a month, purchases
        $2,685): under "fixed" 32 purchases of $83.92; under "poisson_size" 40 purchases spend $3,357, 25% above the
        mean, and under "poisson_month" 40 purchases of $67.14 spend $2,685. Returns (counts, divisor): the divisor
        is the integer ``bundles`` under "fixed" and "poisson_size", each person's count under "poisson_month"."""
        economy = self.economy
        if economy.purchases == "fixed":
            return economy.bundles, economy.bundles
        rng = np.random.default_rng(np.random.SeedSequence([economy.seed, PURCHASE_COUNT_STREAM, month]))
        count = rng.poisson(economy.bundles, size=self.n)
        if economy.purchases == "poisson_size":
            return count, economy.bundles
        count = np.maximum(count, 1)
        return count, count

    def _obligations(self, month):
        """Create the month's payment obligations and term-credit requests.

        * Services: 32 bundles per person, 41.7% of its spending,
          each to a uniform other person on a uniform day; card-eligible when
          non-housing (with the core's card share of them);
          settles on the seller's billing date. Under random purchases
          the number is Poisson with mean 32
          (``_purchase_counts``).
        * Wages: 58.3% of spending, earned daily, settled on the job's next
          pay date (the recipient's billing dates without ``pay_dates``), accruals settling on one date merged. A
          job in a spell pays its worker nothing for those days. After normal job loss its
          payer keeps the money and owes nothing later; after a distress
          year's extra layoff (the harsh stress) the
          payer still owes the wage on the same pay dates, in rows of their
          own (``OUTSIDE_WAGE``), a payable with no receivable, paid out of the
          household economy: the outside is credited when each row is made.
        * Shocks (SHED, optional): unplanned purchases of 0.22 months of own
          spending with the SHED annual incidences.
        * Term requests: one draw per eligible product (households:
          vehicle and personal; firms: business), sized on annual spending,
          priced at the borrower's score-based outside APR, which follows
          r_out at the time of the request and is sealed with it.

        Each stream has its own seed per month, so all arms see identical draws.
        """
        economy, n, inputs = self.economy, self.n, self.inputs
        cycles, phases, s = self.pop["cycles"], self.pop["phases"], self.spending
        # Services: buyer, seller (uniform over the others), day, card eligibility and amount per bundle. Under random
        # purchases (``Economy.purchases``) each person's number of them is drawn first and the
        # rest on a stream of their own, sized by the realised number (``_purchase_counts``).
        count, size = self._purchase_counts(month)
        buyer = np.repeat(np.arange(n), count)
        stream = 11 if economy.purchases == "fixed" else PURCHASE_STREAM
        rng = np.random.default_rng(np.random.SeedSequence([economy.seed, stream, month]))
        seller = (buyer + 1 + rng.integers(0, n - 1, size=buyer.size)) % n
        day = month * DAYS + rng.integers(0, DAYS, size=buyer.size)
        card = rng.random(buyer.size) < self.card_share
        # Under the seller switch (``Economy.sellers``) the seller comes from the world's rule, on a stream of its own;
        # the base's draw above is made and set aside, so the days, card flags and amounts are the same in every world.
        seller = self.network.draw_sellers(buyer, seller, economy.seed, "service", month)
        amount = (1 - LABOUR_SHARE) * s[buyer] / (size if np.isscalar(size) else size[buyer])
        # The stress year as a slowdown (``Economy.distress_purchases``; off by default): in a
        # distress month each purchase is dropped where its own uniform, drawn after every draw above on a stream of
        # its own, is below x, so the purchases kept are the same in every arm and at a higher level a subset of those
        # at a lower. A dropped purchase is simply not made: no obligation, no receivable, no failure.
        self.acc["purchases_dropped"] = 0.0
        if economy.distress_purchases > 0 and self.distressed[month]:
            x = economy.distress_purchases * economy.distress / CARD_CUT_LEVEL
            drop_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, DROP_STREAM, month]))
            kept = ~(drop_rng.random(buyer.size) < x)
            self.acc["purchases_dropped"] = float((~kept).sum())
            buyer, seller, day, card, amount = buyer[kept], seller[kept], day[kept], card[kept], amount[kept]
        # Wages: earned daily, settled on the job's first pay date on or after each day (the recipient's first
        # billing date without ``pay_dates``), merged per date. Pay comes with no lag after its period, which sets the
        # earned-wage room and the timing of receipts.
        payer = np.repeat(np.arange(n), DAYS)
        earned = month * DAYS + np.tile(np.arange(DAYS), n)
        daily = LABOUR_SHARE * s[payer] / DAYS
        # Distress: a job in a spell earns nothing on those days. After normal job loss the payer keeps the money and
        # owes nothing later; on the days of an extra layoff's spell (``spell_out``, the harsh stress) it
        # owes the wage to the outside (``out``), so withheld is the wages payers keep.
        spell = (self.spell_start[payer] <= earned) & (earned < self.spell_end[payer])
        out = spell & self.spell_out[payer]
        self.acc["withheld"] = float(daily[spell & ~out].sum())
        self.acc["laid_off"] = float(spell.mean())
        self.acc["laid_off_last_day"] = self._laid_off_last_day(spell)
        # Hit workers (a record only): the earners of a job with a day in a spell this month, whose
        # failures the close reports apart from everyone else's.
        self.acc["hit"] = np.zeros(n, bool)
        self.acc["hit"][self.pop["wage_to"][spell.reshape(n, DAYS).any(axis=1)]] = True

        def wage_rows(days):
            """The payer-days ``days`` as wage rows (payer, settle date, amount): each job's accruals settling on one
            date merged."""
            who, when = payer[days], earned[days]
            if economy.pay_dates:
                # Pay dates: the job's own pay period and phase, whatever the recipient's cycle.
                settle = next_billing(self.pop["pay_days"][who], self.pop["pay_phase"][who], when)
            else:
                recipient = self.pop["wage_to"][who]
                settle = next_billing(cycles[recipient], phases[recipient], when)
            key, inverse = np.unique(who * (4 * DAYS) + (settle - month * DAYS), return_inverse=True)
            return key // (4 * DAYS), key % (4 * DAYS) + month * DAYS, np.bincount(inverse, weights=daily[days])
        wage_payer, wage_settle, wage_amount = wage_rows(~spell)
        # SHED shocks: one draw per person and type, paid to a uniform seller on a uniform day.
        shock_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 13, month]))
        hazard = 1 - (1 - SHOCK_ANNUAL) ** (1 / 12)
        hit = (shock_rng.random((n, 3)) < hazard[None, :]) & economy.shocks
        shock_seller = (np.arange(n)[:, None] + 1 + shock_rng.integers(0, n - 1, size=(n, 3))) % n
        shock_day = month * DAYS + shock_rng.integers(0, DAYS, size=(n, 3))
        shock_card = shock_rng.random((n, 3)) < self.card_share
        shock_buyer = np.repeat(np.arange(n)[:, None], 3, axis=1)
        shock_seller = self.network.draw_sellers(shock_buyer, shock_seller, economy.seed, "shock", month)
        sb, ss = shock_buyer[hit], shock_seller[hit]
        self.acc["shocks"] = float(SHOCK_SIZE * s[sb].sum())
        wage_recipient = self.pop["wage_to"][wage_payer]
        settle_all = np.concatenate([next_billing(cycles[seller], phases[seller], day), wage_settle,
                                     next_billing(cycles[ss], phases[ss], shock_day[hit])])
        new = dict(buyer=np.concatenate([buyer, wage_payer, sb]), seller=np.concatenate([seller, wage_recipient, ss]),
                   amount=np.concatenate([amount, wage_amount, SHOCK_SIZE * s[sb]]), settle=settle_all,
                   card=np.concatenate([card, np.zeros(wage_payer.size, bool), shock_card[hit]]),
                   kind=np.concatenate([np.full(buyer.size, SERVICE), np.full(wage_payer.size, WAGE),
                                        np.full(sb.size, SHOCK)]))
        # Every obligation is a receivable for the payee and a payable for the payer until it settles.
        np.add.at(self.receivable, new["seller"], new["amount"])
        np.add.at(self.payable, new["buyer"], new["amount"])
        self.acc["wages_out"] = self.acc["wages_kept"] = 0.0
        if out.any() and economy.distress_wages == "kept":
            # The stress year as a slowdown: the payer of an extra layoff owes the wage to
            # nobody and keeps the money, as after normal job loss; its worker still receives nothing. No row is made
            # and nothing crosses the edge; the amount is recorded.
            self.acc["wages_kept"] = float(daily[out].sum())
        elif out.any():
            # The harsh stress: an extra layoff's wage rows, on the job's pay dates, kept apart
            # from its paid days. Each is its payer's payable and nobody's receivable, so the payer's net wealth falls
            # by it now and the outside account is credited with it now, as outside interest and fee debt are when
            # they arise; paying it later moves no wealth. The job's worker is named as the row's payee, and no
            # settlement credits it.
            out_payer, out_settle, out_amount = wage_rows(out)
            np.add.at(self.payable, out_payer, out_amount)
            self.acc["wages_out"] = float(out_amount.sum())
            self.external -= self.acc["wages_out"]
            self._edge_debt(np.bincount(out_payer, weights=out_amount, minlength=n))   # a record only
            new = _concat(new, dict(buyer=out_payer, seller=self.pop["wage_to"][out_payer], amount=out_amount,
                                    settle=out_settle, card=np.zeros(out_payer.size, bool),
                                    kind=np.full(out_payer.size, OUTSIDE_WAGE)))
        merged = _concat(self.ob, new)
        self.ob = _take(merged, np.argsort(merged["settle"], kind="stable"))
        # Counterparties for the joining rule's contact share: service and wage partners this month.
        self.month_pairs = (np.concatenate([buyer, wage_payer]), np.concatenate([seller, wage_recipient]))
        # Instalment credit: one request per eligible product per person, each a purchase from a uniform seller.
        term_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 17, month]))
        draw, used = term_rng.random((n, 3)), term_rng.random(n) >= VEHICLE_NEW_SHARE
        t_seller = (np.arange(n)[:, None] + 1 + term_rng.integers(0, n - 1, size=(n, 3))) % n
        t_day = month * DAYS + term_rng.integers(0, DAYS, size=(n, 3))
        t_seller = self.network.draw_sellers(np.repeat(np.arange(n)[:, None], 3, axis=1), t_seller, economy.seed,
                                             "term", month)
        eligible = BUSINESS_PRODUCT[None, :] == self.pop["business"][:, None]
        ask = eligible & (draw < REQUEST_RATE[None, :])
        who, product = np.nonzero(ask)
        size = np.where(product == 0, VEHICLE_SIZE[used[who].astype(int)], TERM_SIZE[product])
        t_settle = t_day[ask] + (phases[t_seller[ask]] - t_day[ask]) % cycles[t_seller[ask]]
        request = dict(buyer=who, seller=t_seller[ask], price=size * 12 * s[who], settle=t_settle, product=product,
                       rate=term_outside_apr(product, self.pop["score"][who], used[who], self.term_shift) / 12,
                       months=TERM_MONTHS[product])
        merged = _concat(self.req, request)
        self.req = _take(merged, np.argsort(merged["settle"], kind="stable"))

    def _cycle_terms(self, month):
        """Set this month's pool terms from completed observations only, published at the start of the month.

        * Coupons r_g (bridging) and r_term (term loans) = max(0, capital part
          + o + the fixed cost's part + that product's learned loss rate) (the
          coupon, equation (coupon) of paper/cpm.tex, each loan pricing its
          own product's loss);
          the capital part is owners' alternative, the reserve rate rho_p (rho_H
          in M1, rho_H - dJ/J in M2, the contract in P terms) plus the owners'
          spread (applied alike to owners' alternative and
          the coupon's capital part). The fixed cost's part (P payments run on
          stablecoin rails, so no fee carries the fixed cost)
          is the last cycle's fixed cost over its loans' principal-time, the
          break-even price (``_fixed_rate``), added to the operating part o, so
          a bridge pays it after demurrage covers the capital part.
        * The capital limit N* (``Q``) and the quote at it (``R_hat``), the
          free-entry equilibrium, from the last cycle, the last
          two months (at launch the launch plan): ``_limit``, with the cycle's
          peak bridging need and standby cash-time (``_kept_ready``).
        * Demurrage pays for liquidity kept available (the holding
          charge, equation (charge) of paper/cpm.tex), in M1 and M2, derived
          from the last cycle, never a residual of this month: c = [owners'
          alternative on the cycle's bridging principal-time + (alternative -
          p_net) on its standby cash-time] over the cycle's wallet P
          balance-time, a month, at most rho_p - c_I (``p_net``, so P's yield
          is never below zero), zero with nothing kept available or no wallet P
          in the cycle. Standby is pool cash held ready up to the cycle's peak
          bridging need beyond what was lent: idle cash earns p_net, so
          demurrage pays it the rest of owners' alternative, and owners earn
          their alternative on every unit kept ready. Coverage, the share of
          that whole capital cost demurrage at c pays on the cycle's wallet P,
          min(1, c wallet / cost), is 1 whenever c is not bounded and zero with
          nothing kept available; a bridge drawn this month is sealed at r_b,
          the coupon less coverage times its capital part, so a bounded c cuts
          bridging and standby alike. Term
          loans keep the full coupon. U, the same P with c = 0,
          has neither. P's published yield is y_P = rho_p - c_I - c, with M2's
          indexation added in nominal terms (``p_yield``). c is published only
          while the pool takes demurrage (``_takes_demurrage``: it has shares
          and is not winding down), so no month publishes a charge the pool
          will not take.
        * The most a monopoly issuer could take (``s_monopoly``), a bound
          recorded only (``_monopoly_share``).
        * Readiness (the quote reaching owners' alternative, m >= 0),
          reported only.
        """
        inputs = self.inputs
        alternative = self._owners_alternative()
        if month == self.economy.burn_in and self.pool_arm:
            self.window = [self._launch_plan()]
        cycle = self.window[-2:] if self.launched else []
        # The fixed cost's part at break-even (``_fixed_rate``), and learned loss by product:
        # losses net of recoveries over the principal-time that product carried at least
        # LOSS_LAG_MONTHS ago (lagged exposure); zero before any. kappa is 1: lost interest is in it.
        # Under the loan-loss bound each coupon also carries its class's sourced rate of the month
        # (``_priced_loss``: card for bridging, consumer and business for term loans), which the learned rate then
        # leaves out (``_loan_losses``); nothing without the bound, where the business coupon is r_term.
        self.r_fix = self._fixed_rate(cycle)
        learned, priced = self._loss_rates(), self._priced_loss(month)
        base = alternative + inputs.o + self.r_fix
        self.r_g = float(max(0.0, base + learned[0] + priced[0]))
        self.r_term = float(max(0.0, base + learned[1] + priced[1]))
        self.r_term_business = float(max(0.0, base + learned[1] + priced[2]))
        self.peak, standby = self._kept_ready(cycle)
        self.standby = standby / len(cycle) if cycle else 0.0   # a month
        self.Q, self.R_hat = self._limit(cycle)
        # Readiness is reported, not imposed: the capital game decides whether the pool operates.
        self.ready = bool(cycle and self.margin >= 0)
        self.c = self.coverage = 0.0
        self.s_monopoly = self._monopoly_share(cycle) if cycle and self.pool_arm else np.nan
        if cycle and self.demurrage and self._takes_demurrage():
            total = lambda key: float(sum(entry[key] for entry in cycle))
            # The capital cost of all the liquidity kept available: bridging at owners'
            # alternative and the standby at the alternative less what idle cash earns, over the cycle's months.
            cost = total("capital_cost") + (alternative - self.p_net) * standby
            wallet = total("wallet")
            self.c = min(cost / wallet, self.p_net) if wallet > EPS else 0.0
            # With nothing kept available in the cycle there is no observed cost to cover, so a bridge drawn this
            # month pays the full coupon.
            self.coverage = min(1.0, self.c * wallet / cost) if cost > EPS else 0.0
        self.r_b = self.r_g - self.coverage * alternative
        if self.pool_arm:
            self.p_yield = self.index + self.p_net - self.c

    def _launch_plan(self):
        """The launch plan, the cycle the launch month's terms read, from the completed
        burn-in month of the initial participants, in the form of a closed month's ``window`` entry.

        The lending need P* is the mean of their bridging need path. No fee exists (P payments run
        on stablecoin rails), so the plan's only cost beyond its loans is the fixed cost a month, which the coupon
        prices on that lending need at break-even (``_fixed_rate``): the coupons pay it exactly, and the plan's margin
        F is zero, or minus the fixed cost where there is no lending need to price it on. Under competitive P
        the wallets' reserve return goes to their holders, the plan observes no bridging, so no
        demurrage, and the pool holds no cash yet, so the plan counts no demurrage revenue in any pool arm, U, M1 and M2
        alike, and sets no charge and no coverage. Demurrage pays for liquidity kept available: the
        plan's daily bridging is the same need path, so its peak bridging need is the path's largest day, and the
        launch month's capital target in M1 and M2 is that peak (the plan has no term lending); it holds no cash ready,
        so it has no standby.
        """
        path = self.last["bridge_path"][self.part].sum(axis=0)
        need, fixed = float(path.mean()), self.inputs.C_fix * self.n
        return dict(need=need, margin=0.0 if need > EPS else -fixed, fixed=fixed, lent=need, revenue=0.0, covered=0.0,
                    capital_cost=0.0, wallet=0.0, float_pool=0.0, charges=0.0, need_term=0.0, bridging=path,
                    refused_bridging=0.0, ready=np.zeros(DAYS))

    def _fixed_rate(self, cycle):
        """The pool's fixed cost a month on each unit of principal lent, priced into every pool loan's coupon at
        break-even (P payments run on stablecoin rails, so no fee carries the fixed cost; derived
        from the zero-profit principle, as for the issuer, competitive P and free entry; borrowers pay for the credit
        service, as a lending protocol's reserve spread does): the fixed cost the pool bore over the last cycle, the
        last two months (``window``), over the principal-time its loans carried then, bridging and term, so the
        coupons accrued on that lending would have paid it exactly. At launch the cycle is the launch plan, whose fixed
        cost is priced on its lending need. A cycle that carried no loans has no principal-time to read, so its fixed
        cost a month is priced on its lending need P*, as the plan's is. Zero with no
        cycle or no lending need."""
        if not cycle:
            return 0.0
        total = lambda key: float(sum(entry[key] for entry in cycle))
        lent = total("lent")
        if lent > EPS:
            return total("fixed") / lent
        need = total("need")
        return self.inputs.C_fix * self.n * len(cycle) / need if need > EPS else 0.0

    def _limit(self, cycle):
        """The capital limit N* and the quote at it, the free-entry equilibrium (derived from the
        zero-profit principle, as for the issuer and competitive P), from the last cycle.

        In the free-entry row F is the fee margin, the pool's margin without the return on its own cash. P payments
        run on stablecoin rails, so no fee exists, and the coupon carries the fixed cost at break-even
        (``_fixed_rate``): F = 0 with no fees, so N* is the capital target. Realised write-offs,
        recoveries and any fixed cost under- or over-recovered stay in owners' NAV, not in N*; the realised margin is
        kept in each ``window`` entry as a record, which the monopoly bound reads. The capital target is the lending
        need with its bridging part at the cycle's peak in M1 and M2 (``_kept_ready``: demurrage
        pays for liquidity kept available): the term lending need, the mean carried term principal plus refused term
        lending plus the growth of the pool's term book a month, plus the peak bridging need. The term part of the
        capital target funds next month's lending: the growth, the pool's carried term principal
        at the close less at the last close, floored at zero, is the book the pool would carry next month had it lent
        all that was asked, where carried plus refused alone holds a cushion of one month's refused lending that never
        grows to meet demand. U has no demurrage, so nothing pays for standby: its target is the lending need P*, the
        mean carried pool principal plus refused principal plus the same growth a month. Under
        ``Economy.uncharged_target`` "peak" U's target is the term lending need plus the peak bridging need, as in M1
        and M2; example: with a term lending need of 1,400 and a peak of 240 a person, both targets are 1,640, where by
        default U's is its mean lending need. N* = ``paper_capital`` at F = 0, the target itself, and the quote at
        capital N is ``paper_return``, owners' alternative on capital up to the target plus p_net on the rest,
        over N (``_quote``): at N* it is the alternative, above N* below it.
        Returns (N*, the quote at N*), (0, NaN) with no cycle or no N*.
        """
        if not cycle:
            self.need = self.margin = 0.0
            return 0.0, np.nan
        mean = lambda key: float(np.mean([entry[key] for entry in cycle]))
        # Under uncharged_target "peak" U takes the target of the pool with
        # demurrage, with no charge and no other change.
        peak_target = self.demurrage or (self.pool_arm and self.economy.uncharged_target == "peak")
        self.need = mean("need_term") + self.peak if peak_target else mean("need")
        self.margin = 0.0                                     # F, the fee margin: no fee exists
        limit = paper_capital(self.need, self.margin, self._owners_alternative(), self.rho_p, self.p_net)
        return limit, (self._quote(limit) if limit > EPS else np.nan)

    def _kept_ready(self, cycle):
        """The liquidity the pool kept available over the last cycle (demurrage pays for liquidity
        kept available), from its ``window`` entries: the peak bridging need, the largest daily carried bridging
        principal of the cycle plus the bridging it refused in the cycle, and the standby cash-time, the pool cash held
        ready each day up to that peak beyond the bridging it carried, min(ready, max(peak - carried, 0)), summed over
        the cycle's days in months. Reading the refused bridging as the cycle's total beside the largest day, the
        literal reading that gives the larger peak, is the rule (docs/DECISIONS.md, "The peak bridging need");
        at the launch plan the need path holds both parts, so its peak is the path's largest
        day. Returns (0, 0) with no cycle."""
        if not cycle:
            return 0.0, 0.0
        carried = np.concatenate([entry["bridging"] for entry in cycle])
        ready = np.concatenate([entry["ready"] for entry in cycle])
        peak = float(carried.max()) + float(sum(entry["refused_bridging"] for entry in cycle))
        standby = float(np.minimum(ready, np.maximum(peak - carried, 0.0)).sum()) / DAYS
        return peak, standby

    def _quote(self, capital):
        """The pool's quote at ``capital`` a month, in P terms (the free-entry quote):
        ``paper_return`` at this month's lending need and margin F, with loan income at owners' alternative and the
        pool's own cash beyond the lending need at p_net; NaN with no capital."""
        return paper_return(self.need, self.margin, capital, self._owners_alternative(), self.p_net)

    def _monopoly_share(self, cycle):
        """The largest share of the reserve return on P an issuer could keep with the pool's quote still reaching
        owners' alternative (what a monopoly issuer could take is reported as a bound), a record
        only, from the cycle the terms read; NaN where no share, not even none, reaches it.

        The quote reaches the alternative at some capital exactly when F >= 0 (``paper_capital``). Under competitive P
        an issuer keeping a share s of the reserve return rho_p leaves wallet P (1 - s) rho_p before demurrage,
        and demurrage, at most that, pays the cycle's bridging capital cost K on its wallet P balance-time W:
        D(s) = min(K, (1 - s) rho_p W). With A the rest of F, F less the demurrage the cycle took, F(s) = A + D(s), so
        the bound is 1 where A >= 0, else 1 + A / (rho_p W) where K + A >= 0 and that is not negative, else NaN. In U
        demurrage pays nothing, so the bound is 1 or NaN. The pool cash's own return enters the quote beyond P*, not F
        (``_limit``), so it does not move the bound. Sums over the cycle's months; the competitive issuer keeps s_I
        (``issuer_share``), and the bound below s_I says that even its custody leaves the quote short. Demurrage pays
        for liquidity kept available: K holds the standby's capital cost beside bridging's, and
        the bound reads the cycle's realised margin less the standby's cost, read at the competitive p_net, where N*
        reads no margin (F = 0 with no fees, ``_limit``).
        """
        total = lambda key: float(sum(entry[key] for entry in cycle))
        standby = (self._owners_alternative() - self.p_net) * self.standby * len(cycle) if self.demurrage else 0.0
        rest = total("margin") - standby - total("charges")
        if rest >= 0:
            return 1.0
        base = max(self.rho_p, 0.0) * total("wallet")
        if not self.demurrage or total("capital_cost") + standby + rest < 0 or base <= EPS:
            return np.nan
        share = 1 + rest / base
        return share if share >= 0 else np.nan

    def _loss_rates(self):
        """Learned loss per unit of principal-time, bridging then term: losses net of recoveries over lagged exposure.

        A missed payment becomes a loss LOSS_LAG_MONTHS later, so only the
        principal-time of months at least that old is counted: it has had time
        to show its losses. This is exact when defaults are spread evenly over
        a loan's life; if they come late in its life it is too low early on.
        """
        seen = self.exposure[:-LOSS_LAG_MONTHS].sum(axis=0)
        return np.divide(np.maximum(self.loss_net, 0.0), seen, out=np.zeros(2), where=seen > 0)

    def _priced_loss(self, month):
        """The loss a month each pool coupon carries under the loan-loss bound (the pool prices
        the published rate), by class (``LOSS_CLASSES``): the sourced charge-off rate of the month over 12, the rate
        this month's close discharges at (``_loan_losses``), read at the share of jobs without a wage three months
        earlier, a published figure known when the month's terms are set. Month 0, with no earlier month, reads the
        normal rates. Zero without the bound.

        The pool earns it on each loan's principal-time and loses the same rate on the class's average principal, so
        in a month whose loans were all sealed at the month's rate the two are equal. A bridge is sealed for its days
        and a term loan for its life, so when the rate moves with job loss the loans sealed earlier lose more or less
        than they carry: that difference is the owners'. Example: with 1.8% of jobs without a wage three months
        earlier, the bridging coupon carries 3.402% / 12 a month and the business coupon 0.3315% / 12."""
        if self.economy.loan_losses != "sourced":
            return np.zeros(len(LOSS_CLASSES))
        if month == 0:
            return CHARGE_OFF_NORMAL / 12
        return charge_off_rates(self._lagged_jobs_without_wage(month)) / 12

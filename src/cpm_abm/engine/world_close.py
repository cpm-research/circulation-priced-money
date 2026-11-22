"""The month's close.

Whether the pool takes demurrage, the reserve return on P, owners' income, the pool's own margin, the joint issuer
and pool test and the largest loans, then the close itself and its records with the experience replays it reads.
"""
from functools import reduce

import numpy as np

from cpm_abm.engine.constants import (BIG, BRIDGE, CASH_ADVANCE, CHARGED_OFF, CREDIT_RECORDS, DAYS, EPS, EWA_FEE,
                                      FAIL_FEE, FAILURE_COUNTS, FEE_DEBT, LOAN_LOSS_SERIES, LOSS_CARRIED, MARGIN_PARTS,
                                      MEASURE_SERIES, OVERDRAFT, REVOLVE, TERM, VELOCITY_RECORDS)
from cpm_abm.engine.lending_rules import choose_buffer
from cpm_abm.engine.measures import KNOCK_ON_BINS, gini
from cpm_abm.engine.network import threshold_chance


class CloseMixin:
    """The month's close, one part of ``_World``: whether the pool takes demurrage, the reserve return on P, owners'
    income, the pool's own margin, the joint issuer and pool test, and the close's records and experience replays."""

    def _admitted(self):
        """Each participant's experienced share of its own shortfalls the pool admitted this month.

        With no own shortfall, the participants' pooled share stands in; with
        no pool taking requests it is zero.
        """
        acc = self.acc
        if not self.asking:
            return np.zeros(self.n)
        pooled = acc["drawn"].sum() / acc["want"].sum() if acc["want"].sum() > 0 else 1.0
        own = np.divide(acc["drawn"], acc["want"], out=np.full(self.n, pooled), where=acc["want"] > EPS)
        return np.clip(own, 0.0, 1.0)

    # ----- cycle close ------------------------------------------------------------------------
    def _takes_demurrage(self):
        """Whether the pool takes demurrage and its own cash's reserve return this month: while it has shares and is
        not winding down. Otherwise no demurrage is withheld from P's yield and the pool cash's part stays with the
        issuer: a reading of the rule (4 Nov)."""
        return bool(self._all_shares() > EPS and not self.winding)

    def _reserve_return(self):
        """The month's reserve return on P under competitive P (decided 5 Nov; it replaced the float to the pool
        and the charge on idle P of 4 Nov), in the pool arms after launch, at the close; returns the demurrage the pool
        took.

        The reserves' T-bills earn rho_p (real in M2, net of indexation; zero where not positive) on all P, from outside
        the household economy. The issuer keeps its custody, s_I rho_p = c_I (``issuer_share``), on every unit. Each
        holder of wallet P is paid the rest, rho_p - c_I (``p_net``), less demurrage c (published in ``_cycle_terms``),
        on its wallet P balance-time this month, credited as P, so y_P = rho_p - c_I - c, never below zero; the c part
        goes to the pool's cash. The pool's own P cash earns rho_p - c_I. In U c is zero. While the pool does not take
        demurrage (``_takes_demurrage``) holders are paid rho_p - c_I in full and the pool cash's part stays with the
        issuer. All of it stays behind the new P as reserves (``_close``).

        Books, per person, P's yield before demurrage (``p_yield``, which experience reads) and the demurrage withheld
        (``charges``); and in all, that yield on wallet P (``wallet_yield``), the pool's own cash's return
        (``float_pool``) and what the issuer keeps (``float_issuer``), which add up to rho_p on all P.
        """
        acc, rate = self.acc, max(self.rho_p, 0.0)
        takes = self._takes_demurrage()
        if not takes and self.pool_arm:
            # A pool that began winding down at this month's dealing takes none of the c published before it, so the
            # month records the c and the yield holders were paid (the 5 Nov review: no c recorded that nobody paid).
            self.c, self.p_yield = 0.0, self.index + self.p_net
        gross = self.p_net * acc["p_bt"]                          # rho_p - c_I on each holder's wallet balance-time
        charge = self.c * acc["p_bt"]                              # demurrage, withheld from that yield
        self.pcash += gross - charge
        self._coin_net(gross - charge)   # a record only (``_coin_day``): the yield credited, net of demurrage
        acc["p_yield"] += gross
        acc["charges"] += charge
        acc["wallet_yield"] = float(gross.sum())
        acc["float_pool"] = self.p_net * acc["pool_cash_bt"] if takes else 0.0
        acc["float_issuer"] = rate * acc["p_all"] - acc["wallet_yield"] - acc["float_pool"]
        D = float(charge.sum())
        self.pool_cash += D + acc["float_pool"]
        self.external += acc["wallet_yield"] + acc["float_pool"]
        return D

    def _owners_income(self, R):
        """What the month credited to households' pool shares (reported only, decided 3 Nov).

        Dealing is at NAV, so every share held through the month earns R, before CPI (in P terms in M2).
        Households' capital after dealing times R, at most their whole holding (the 3 Nov review,
        decided 4 Nov), is the income the month credited to their shares. Net of issuer money it is the same:
        demurrage replaced the reserve pass-through and the idle windfall, and the pool's share of the reserve return is
        the contract's, not issuer money (decided 4 Nov), so no issuer money reaches the pool's income; the net
        reading is kept because the population runner reads it. Returns R net of issuer money (R), households' capital
        and the income credited to it in all and net. No rule reads any of it.
        """
        owners_capital = float(self.owners_held.sum())
        owners_income = owners_capital * max(R, -1.0) if np.isfinite(R) else 0.0
        return R, owners_capital, owners_income, owners_income

    def _own_margin(self, fixed, demurrage=0.0):
        """The pool's own margin this month and its parts (``MARGIN_PARTS``), in P terms (decided 3 Nov: "The pool
        pays its own way"); a record only, which the runner reads as persistence test 4 and falsifier 3.

        Coupons accrued on carried pool loans (their fixed cost's part among
        them, decided 5 Nov: the coupon carries the fixed cost at
        break-even, ``_fixed_rate``, so over a steady cycle it nets the fixed
        cost to zero) and every payment on a written-off pool loan, principal
        and interest, less the operating cost, the fixed cost, write-offs with
        the interest accrued on them and owners' alternative
        (``_owners_alternative``, the owners' spread included) on lent
        principal-time. No provider fee exists (5 Nov), so there is neither a
        fee part nor owners' own fees. A loan written off and then
        repaid in full nets to its whole interest. Left out: share purchases
        (capital, not income) and
        demurrage revenue (demurrage on wallet P and the reserve return on the
        pool's own P cash, 5 Nov), as the decided row leaves holding charges
        out, except the part that pays the
        coupon cut on bridges (decided 4 Nov): the coupons part is the
        full coupon, what borrowers accrued plus the cut demurrage paid
        (``covered``), at most this month's ``demurrage`` D, the charge on
        wallet P (the 5 Nov review: not D plus the pool cash's own return,
        which is no coupon income), as the full coupon was counted when the
        holding charge went back to borrowers as rebates.
        A reading of the rule (4 Nov): counting the coupons
        borrowers paid alone leans further against CPM, by the ``covered``
        record. With coupons sealed at the alternative plus o, the fixed
        cost's part and losses as learned, it is the October 2026 draft's
        margin m less the shortfall e (its propositions on owner return and
        readiness and on a restoring capital incentive; that contract was
        replaced). In paper/cpm.tex it is the loss-pricing and fixed-cost
        timing terms of the identity in Proposition (The quote is right on
        average under a stationary loss rate), prop:fair. Read before ``_clean_shares``, as R is; NaN outside the
        pool arms. Returns the parts and their sum.
        """
        acc = self.acc
        if not self.pool_arm:
            return dict.fromkeys(MARGIN_PARTS, np.nan), np.nan
        coupons = acc["coupons"] + min(acc["covered"], max(demurrage, 0.0))
        parts = dict(coupons=coupons, recovered=acc["recovered"], operating=-acc["op_cost"], fixed=-fixed,
                     written_off=-acc["written_off"], alternative=-self._owners_alternative() * acc["pool_pt"])
        return parts, sum(parts.values())

    def _joint(self, books, owners_income, owners_capital):
        """The joint issuer-and-pool test this month, in P terms (decided 3 Nov: "net of all costs and capital
        charges"); a record only.

        The issuer's complete wallet (its 0.24% of P and M2's indexation among its lines), plus the income credited to
        households' shares less their alternative on their capital. It reads the issuer and the pool as one firm: the
        reserve return on the pool's own cash (in the books' float line) cancels between them, every cost is charged
        once, and every unit of capital is charged its holder's alternative; the issuer holds no shares (decided
        5 Nov), so households' capital is all of it. While R stays above -1 it equals the own margin, less the
        alternative on capital not lent, plus the custodian, indexer and expenses lines, less the yield the firm pays on
        wallet P before demurrage, plus demurrage (5 Nov: withheld from that yield into the pool, which the margin
        leaves out) and less the part of the coupon cut the margin counts (4 Nov: the demurrage pays it, so it is
        income only once). NaN outside the pool arms.
        """
        if not self.pool_arm:
            return np.nan
        return books["wallet"] + owners_income - self._owners_alternative() * owners_capital

    def _largest_shares(self):
        """Granularity (decided 12 Nov), a record only, read by no rule: the largest single pool loan outstanding
        and the largest pool debt of one borrower, principal on loans the pool still carries (a written-off loan is
        carried at zero), each over pool capital, all shares at NAV. NaN with no pool capital (S0, M0, or a pool
        without owners). Hand case: pool capital 100, carried pool loans of 10 and 6 to one borrower and 12 to
        another give 0.12 and 0.16, against the 15% of capital US law lets a national bank lend one borrower
        (12 U.S.C. 84)."""
        capital = self._all_shares() * self.nav_ps
        if not capital > EPS:
            return np.nan, np.nan
        bk = self.book
        carried = bk["pool"] & bk["carried"]
        if not carried.any():
            return 0.0, 0.0
        principal = bk["principal"][carried]
        debt = np.bincount(bk["borrower"][carried], weights=principal, minlength=self.n)
        return float(principal.max()) / capital, float(debt.max()) / capital

    def _experience_unread(self):
        """Whether nothing reads this close's two experience replays, which are then not computed (a speed device; no
        output changes): nobody participates and nobody adopts (S0, and every arm's burn-in), so every reader is masked
        to participants (the experience records and window), and under the 12-month window (``h4_months``) the
        month's experience kept for the next (``last["monthly"]``) is overwritten before any use."""
        return not self.part.any() and not self.adopting and self.economy.h4_months > 0

    def _close(self, month, start_wealth, join_draw, review_draw, leave_draw=None):
        """Close the month, in this order (``leave_draw``, the leaving rule's draws, None: nobody leaves).

        0. Under the loan-loss bound (decided 12 Nov), the month's loan losses at sourced rates
           (``_loan_losses``); nothing as built.
        1. Outside savings earn their rate (Comet's for M0 participants).
        2. The reserve return on P (decided 5 Nov), in the pool arms after
           launch (``_reserve_return``): wallet P's yield to its holders, net
           of demurrage, and demurrage and the pool's own cash's return into
           the pool's cash; idle P is recorded in every arm.
        3. Fixed pool cost, NAV per share, the owners' realised return R and
           what it credited to households' shares (reported only), and
           the month's ``window`` entry, which next month's terms read: the
           lending need (mean carried pool principal plus refused principal
           plus the growth of the pool's term book, floored at zero,
           decided 12 Nov) and its term part likewise,
           the margin F beyond owners' alternative on lent principal-time
           (``_limit``), the fixed cost and the loans' principal-time the
           coupon's fixed part reads (``_fixed_rate``), and demurrage's parts
           (the bridging capital cost, the
           wallet P balance-time it is charged on, the demurrage taken, the
           pool's own cash's return, the coupon cut it paid).
        4. Experience of using P: the buffer replay with and without P on the same
           flows, plus term-credit savings, yield, fees and net charges.
        5. Adoption: joining at p + q x contact share; leaving by the decided
           rule (``_leaving``): a reviewer leaves with the logistic probability
           of its 12-month average experience falling short of one conversion
           of its 12-month average P balance, spread over the 12 months.
        6. Card rewards come in from the card issuers; under the recirculation
           stress, outside lenders' interest goes back to households pro rata to
           spending; durables depreciate; CPI deflates nominal stocks.
        7. Spending: next month's spending from relative net worth incl. durables.
        8. Records: the monthly series and person-level paths.
        """
        inputs, n, acc, ch = self.inputs, self.n, self.acc, self.channels
        # 0. Loan losses at sourced rates, the bound (decided 12 Nov; nothing as built): first in the close, after
        # the month's settlement and before the pool's NAV, R and the month's losses are read, so the owners bear the
        # pool's part in this month's NAV and R and next month's coupons learn it (``_loan_losses``).
        self._loan_losses(month)
        # 1. Savings income (an outside flow).
        # Savings earn each person's own outside rate in every arm, or rho_H when only the money market part was saved
        # (the deposit part stayed as cash). M0 adds only the Comet supply premium over that rate: the core's M0
        # savings part is (supply rate - control rate) x savings.
        saving_rate = self.saving_rate + (self.inputs.supply_premium * self.part if self.defi else 0.0)
        returns = self.savings * saving_rate
        self.savings += returns
        self._coin_net(returns)   # a record only (``_coin_day``)
        self.external += returns.sum()
        # 2. The reserve return on P (decided 5 Nov): P's yield to wallet holders, demurrage and the pool's own
        # cash's return into the pool's cash. Idle P, each person's lowest P balance over the last two months, is a
        # record in every arm (the precautionary total's part); no rule charges it since 5 Nov.
        acc["idle"] = float(np.minimum(acc["p_low"], self.last["p_low"]).sum())
        D = self._reserve_return() if self.launched else 0.0
        revenue = acc["float_pool"] + D
        # 3. Pool costs, NAV and the owners' realised return over the month (demurrage revenue is pool income).
        fixed = inputs.C_fix * n if self.service else 0.0
        self._pool_cost(fixed)
        if self._all_shares() > EPS:
            self.nav_ps = self._assets() / self._all_shares()
        # No provider fee reaches the pool (decided 5 Nov); the coupons carry the fixed cost's part.
        loans = acc["coupons"] - acc["op_cost"] - acc["written_off"] + acc["recovered"]
        R = (loans - fixed + revenue) / self.capital if self.capital > 0 else np.nan
        # Reported (3 Nov): read before ``_clean_shares``, so a month that winds down still credits its owners.
        # Owners' exits read R from next month's dealing (3 Nov). No issuer money reaches the pool's income since
        # demurrage (4 Nov), so R is net of it (``_owners_income``).
        self.r_owners[month] = np.maximum(R, -1.0)
        R_net, owners_capital, owners_income, owners_net = self._owners_income(R)
        # The yardsticks (decided 3 Nov), records only, read before ``_clean_shares`` as R is: the pool's own
        # margin. What the issuer paid each household is read as the close deflates, below.
        margin_parts, margin = self._own_margin(fixed, D)
        self._clean_shares()
        self.loss_net += acc["lost"]
        self.exposure = np.vstack([self.exposure, acc["exposure"]])
        self.loan_age["written_off"].append(acc["age_loss"] / n)
        self.loan_age["exposure"].append(acc["age_exposure"] / n)
        self.vintage["income"].append(acc["vintage_income"] / n)       # reported (4 Nov): the month's, as R reads it
        self.vintage["exposure"].append(acc["vintage_exposure"] / n)
        self.vintage["shared"].append(-fixed / n)   # pool-wide, spread by principal-time when read
        # The month's window entry, which next month's terms read with the month before (``_cycle_terms``, ``_limit``).
        # The realised margin is a record: N* reads none (F = 0 with no fees, decided 5 Nov). The margin's fixed
        # cost is the pool's whole fixed cost a month, also in a month it did not serve, the cost it bears once it
        # does: a reading of the rule (4 Nov). The entry's ``fixed`` is the fixed cost the pool
        # bore, zero in a month it did not serve (source audit, 13 Nov 2026: the whole-cost reading is the margin's
        # only). It counts demurrage D but not the reserve return on the pool's own
        # cash, which the free-entry quote counts on capital beyond the target (derived 5 Nov); the monopoly bound
        # reads it. The coupon's fixed part reads the fixed cost the pool bore and the principal-time its loans
        # carried, bridging and term (``_fixed_rate``, 5 Nov). Demurrage pays for liquidity kept available
        # (decided 5 Nov): the entry also holds the term lending need, the day by day carried bridging and cash
        # held ready and the bridging refused, from which the next terms read the peak bridging need and the standby
        # (``_kept_ready``).
        bridge_pt = acc["bridge_pt"].sum()
        alternative = self._owners_alternative()
        if self.launched:
            margin_m = D - inputs.C_fix * n + loans - alternative * acc["pool_pt"]
            # The term part of the capital target funds next month's lending (decided 12 Nov): the lending need
            # adds the month's growth in the pool's carried term principal, floored at zero, so the target holds the
            # book the pool would carry next month had it lent all that was asked; none in the launch month's entry.
            # The growth is read in this month's units, from the book at the last close after CPI (below).
            growth = max(self._term_book() - self.term_book, 0.0) if self.term_book is not None else 0.0
            self.window.append(dict(need=acc["pool_pt"] + acc["refused"] + growth, margin=margin_m, fixed=fixed,
                                    lent=acc["pool_pt"], revenue=revenue, covered=acc["covered"],
                                    capital_cost=alternative * bridge_pt, wallet=float(acc["p_bt"].sum()),
                                    float_pool=acc["float_pool"], charges=D,
                                    need_term=float(acc["exposure"][1]) + acc["refused_term"] + growth,
                                    bridging=acc["bridge_day"].copy(), refused_bridging=acc["refused_bridging"],
                                    ready=acc["ready_day"].copy()))
        # Demurrage's share of bridging finance (theta, Proposition (The share) of paper/cpm.tex; decided 4 Nov):
        # the coupon cut it paid on carried pool bridges over that cut plus the coupons borrowers accrued on them;
        # undefined with neither.
        theta = (acc["covered"] / (acc["covered"] + acc["bridge_coupons"])
                 if acc["covered"] + acc["bridge_coupons"] > 0 else np.nan)
        # Experience: the liquidity replay against the posted-price S0 alternative, plus actual fees and charges.
        wealth = self.net_wealth()
        admitted = self._admitted()
        cover = self.cover   # M0's crypto collateral holders (5 Nov), full cover; zero elsewhere
        comet_rate = self.comet_borrow
        # Card limits (decided 14 Nov 2026): a holder's shortfall goes to its cash line, up to this month's room
        # each day, at the cash APR and the advance's fee, and beyond it to earned-wage access and failure, in both
        # replays.
        credit_cpm = (admitted * (self.r_b + self.index) + (1 - admitted) * (cover * comet_rate
                      + (1 - cover) * self.holder * self.cash_apr))
        # The failure fee per unit failed (decided 30 Oct): the flat fee over the month's average payment.
        avg_payment = np.where(acc["due_n"] > 0, acc["due_amt"] / np.maximum(acc["due_n"], 1.0),
                               self.last["avg_payment"])
        fail_rate = FAIL_FEE / np.maximum(avg_payment, EPS)
        fail_cpm = (1 - admitted) * (1 - cover) * fail_rate
        card_cpm = (1 - admitted) * (1 - cover) * self.holder   # the share of a shortfall the cash line prices
        # A line closed this month leaves no room (``_charge_off``).
        cards = lambda share: dict(card_room=np.where(self.holder[:, None], acc["card_room"], 0.0),
                                   card_rate=share * self.cash_apr, card_floor=share * self.advance_floor,
                                   card_fee=share * self.advance_rate)
        # Experience compares holding P with switching back in the same economy: the same alternative for spare money, E
        # earning checking on its part of the buffer, the same savings a shortfall could draw on that day; P's yield
        # before demurrage and the demurrage withheld from it enter separately below (5 Nov).
        p_share = np.divide(acc["p_bt"], acc["liquid_bt"], out=np.zeros(n), where=acc["liquid_bt"] > EPS)
        # P's yield in experience (the 5 Nov review): the deposit part of spare money kept in P (or USDC) would earn the
        # deposit rate were the person to leave, so experience credits only the yield above it on that part, at most
        # the month's P balance-time; the rest of the balance earns its full yield, M2's indexation included.
        yield_kept = (acc["p_yield"] + self.index * acc["p_bt"]
                      - self.deposit_rate * np.minimum(acc["deposit_kept"], acc["p_bt"]))
        # Both experience replays price failures past the monthly cap of fees at $0, what the wallet pays (decided
        # 3 Nov): at $27 they would credit a P user with a fee S0 never charges.
        fail_month = self.economy.fees_a_month * FAIL_FEE if np.isfinite(self.economy.fees_a_month) else None
        # Earned-wage access (decided 3 Nov), in both replays: the month's room each day, at its fee per unit
        # drawn, for holders of access, on the share neither the pool, Comet nor a holder's cash line covers.
        room = rate_cpm = rate_s0 = None
        if self.economy.earned_wage_share > 0:
            access = self.pop["ewa"] * EWA_FEE
            room, rate_cpm, rate_s0 = acc["ewa_room"], (1 - admitted) * (1 - cover) * access, access
        if self._experience_unread():
            cost_cpm = cost_s0 = np.zeros(n)   # read by nothing (``_experience_unread``)
        else:
            _, cost_cpm = choose_buffer(acc["flows"], self.spending, wealth, credit_cpm,
                                        acc["alternative"] - (1 - p_share) * inputs.buffer_yield, fail_cpm,
                                        draw_rate=self.r_out, drawable=acc["drawable"], fail_cap=FAIL_FEE,
                                        fail_month=fail_month, advance=room, advance_rate=rate_cpm, **cards(card_cpm))
            _, cost_s0 = choose_buffer(acc["flows_s0"], self.spending, wealth, self.holder * self.cash_apr,
                                       acc["alternative"] - inputs.buffer_yield, fail_rate,
                                       draw_rate=self.r_out, drawable=acc["drawable"], fail_cap=FAIL_FEE,
                                       fail_month=fail_month, advance=room, advance_rate=rate_s0,
                                       **cards(self.holder))
        parts = dict(exp_liquidity=cost_s0 - cost_cpm, exp_term=acc["term_saving"], exp_merchant=acc["merchant_saved"],
                     exp_charges=-acc["charges"], exp_gas=-acc["gas"],
                     exp_conversion=-(acc["conversion"] - acc["dealing_conversion"]),
                     exp_yield=yield_kept)
        counted = {key: value for key, value in parts.items()
                   if key != "exp_merchant" or self.economy.merchant_in_experience}
        monthly = reduce(np.add, counted.values())
        # 4. The experience window: one cycle (two months for 60-day billers) or the 12-month average.
        two_month = self.pop["cycles"] > DAYS
        experience = np.where(two_month, monthly + self.last["monthly"], monthly)
        if self.economy.h4_months > 0:
            # Decided 21 Oct: the average monthly experience over the last 12 months in P, or since joining.
            self.exp_hist = np.vstack([self.exp_hist, np.where(self.part, monthly, np.nan)[None, :]])[-self.economy.h4_months:]
            seen = np.isfinite(self.exp_hist)
            experience = np.where(seen.any(axis=0), np.where(seen, self.exp_hist, 0.0).sum(axis=0)
                                  / np.maximum(seen.sum(axis=0), 1), monthly)
            # The threshold's balance (decided 3 Nov): the average P balance over the same months in P, each month's
            # wallet P balance-time.
            this = np.where(self.part, acc["p_bt"], np.nan)[None, :]
            self.p_hist = np.vstack([self.p_hist, this])[-self.economy.h4_months:]
            held = np.isfinite(self.p_hist)
            balance = np.where(held.any(axis=0), np.where(held, self.p_hist, 0.0).sum(axis=0)
                               / np.maximum(held.sum(axis=0), 1), acc["p_bt"])
        else:
            balance = acc["p_bt"]
        # 5. Adoption at month end: leavers redeem P, joiners convert E (both pay one conversion).
        self.status[month] = self.part
        if self.adopting:
            buyer, seller = self.month_pairs
            ends = np.concatenate([buyer, seller])
            other = np.concatenate([seller, buyer])
            contact = np.bincount(ends, weights=self.part[other].astype(float), minlength=n) / np.bincount(ends, minlength=n)
            # Under the threshold rule (``Economy.joining``) imitation works only where the contact share reaches the
            # person's own threshold (``threshold_chance``); the draw is the same.
            threshold = self.network.threshold
            chance = (inputs.xi0 + inputs.xi1 * contact if threshold is None
                      else threshold_chance(contact, threshold, inputs.xi0, inputs.xi1))
            join = ~self.part & (join_draw < chance)
            leave = self._leaving(experience, balance, contact, review_draw,
                                  np.ones(n) if leave_draw is None else leave_draw)
            self._leave(leave)
            self.exp_hist[:, leave] = np.nan
            self.p_hist[:, leave] = np.nan
            self._join(join, np.ones(n) if not self.economy.routine_conversion else contact * self._p_need())
            self.part = (self.part | join) & ~leave
        if acc["log"]:
            self.payment_log[month] = np.concatenate(acc["log"], axis=1)
        # 6. Card rewards from the card issuers, outside the economy, and under the recirculation stress only, outside
        # lenders' interest back to households pro rata to spending (the boundary rule, 31 Oct: nothing else comes
        # back).
        rewards = self._pay_rewards()
        lenders = self._recirculate()
        self._cover()
        self._book_overdrafts()
        self._count_crossings()   # the close: leaving, joining, rewards (reported only, 3 Nov)
        list(map(lambda item: ch[item[0]].__iadd__(item[1]), (
            ("merchant_paid", acc["merchant"]), ("rewards", rewards), ("conversion_paid", acc["conversion"]),
            ("gas_paid", acc["gas"]), ("recirc_lenders", lenders), ("charges", acc["charges"]))))
        # Durables depreciate straight-line over the loan term; then CPI deflates nominal stocks.
        durable = self.durable
        held = np.bincount(durable["owner"], weights=durable["value"], minlength=n)
        durable["value"] = np.maximum(durable["value"] - durable["step"], 0.0)
        durable["left"] = durable["left"] - 1
        self._compact()
        # Reserve income (decided 30 Oct): the reserves earn the custodian line on P outstanding, net of M2's
        # indexation, and the issuer takes it out except what it paid out as P (5 Nov: the yield on wallet P, demurrage
        # included, and the pool's own cash's return), which stays behind the new P. When that income is negative (M2
        # below zero real rates) the issuer's owners put in the cash that keeps backing at 1: the month's backing
        # top-up. Booked before CPI, which deflates the reserves with the P in M1.
        earned = (self.inputs.rho_H - self.index) * acc["p_all"]
        withdrawn = earned - acc["wallet_yield"] - acc["float_pool"]
        self.reserves += earned - withdrawn
        topup = max(-withdrawn, 0.0)
        inflation = self._deflate()
        if self.launched:
            self.term_book = self._term_book()   # the book next month's growth starts from, in its units (12 Nov)
        # The issuer is a pure custodian (decided 5 Nov): no shares of its own take pool income, so its books are
        # its custody alone.
        books = self._issuer_books()
        joint = self._joint(books, owners_income, owners_capital)   # a record only (3 Nov)
        # Net reserve income: rho_H on P outstanding (participants' P and pool cash), less M2's indexation and what the
        # issuer paid out of it (5 Nov), its custody.
        issuer = (books["custodian"] + books["indexer"] + books["float"]) / n
        stay = self._stay_test(books["wallet"] / n) if self.launched else np.nan
        wealth = self.net_wealth()
        # 7. Spending follows relative net worth including durables, floored at 2% of the mean, mean 1.
        # Illiquid wealth (decided 30 Oct) counts toward net worth here, though it never pays a bill.
        spending_wealth = (wealth + np.bincount(self.durable["owner"], weights=self.durable["value"], minlength=n)
                           + self.pop["illiquid"])
        mean = max(spending_wealth.mean(), EPS)
        relative = np.maximum(spending_wealth, self.economy.wealth_floor * mean) / mean
        spending = relative ** self.economy.beta
        self.spending = spending / spending.mean()
        # 8. Records.
        owed = float(self.pcash.sum() + self.pool_cash)   # P owed: people's P and the pool's cash
        # The old self-financing ratio's numerator and owners' compensation K. Under the own margin (decided 3 Nov)
        # the ratio is kept for one map, labelled "about 1 at the capital limit by construction": K is owners'
        # alternative, without the 0.9, and the numerator credits recovered principal (a written-off bridge repaid in
        # full no longer costs the ratio its principal). As built: K at about 0.9 of r_out and no recovered principal.
        # Otherwise the ratio stays as built, the pool's cash income in its numerator, which now holds demurrage's
        # revenue (the pool's float and the charge) where it held the reserve pass-through, since it is labelled and
        # never tested: a reading of the rule (4 Nov).
        collected = acc["interest_collected"] + revenue
        if self.economy.self_financing == "margin":
            collected += acc["recovered_principal"]
            compensation = self._owners_alternative()
        else:
            compensation = max(0.9 * inputs.rho_H - self.index, 0.0)
        self.wealth_path[month + 1] = wealth
        self.owner_path[month] = self.shares > EPS
        self.borrow_path[month] = acc["borrowed"]
        self.receipts_path[month] = acc["receipts"]
        self.fee_path[month], self.failed_path[month] = acc["fee"], acc["failed_new"]
        for key, source in (("completed", "bought_completed"), ("durables", "bought_durables"), ("lost", "bought_lost"),
                            ("sales", "sold")):
            self.purchase_path[key][month] = acc[source]
        if month >= self.economy.burn_in:
            # MicroVelocity's records (3 Nov), read by no rule: the month's outflow and balance-times into its year.
            row = (month - self.economy.burn_in) // 12
            for key, source in zip(VELOCITY_RECORDS, ("outflow", "liquid_bt", "savings_bt", "shares_bt")):
                self.velocity_path[key][row] += acc[source]
        # Credit (records only, decided 11 Nov): the pool's bridges drawn and the bridging it refused, from the
        # draws and requests the settlement and the statement keep by payer; the rest as accumulated.
        self.credit_path["bridge_pool"][month] = acc["drawn"]
        self.credit_path["bridge_refused"][month] = acc["want"] - acc["drawn"]
        for key in CREDIT_RECORDS:
            if key not in ("bridge_pool", "bridge_refused"):
                self.credit_path[key][month] = acc["credit_" + key]
        list(map(lambda key: self.failure_path[key].__setitem__(month, acc[key]), FAILURE_COUNTS))
        self.owned_path[month], self.cross_path[month] = self.owners_held, acc["crossings"][0]
        chosen, buffer_nocard, buffer_card = self._buffers()   # reported only (the 3 Nov review)
        self.buffer_path[month] = chosen
        self.transfer_path[month] = (acc["out_interest_i"] + acc["fee"] + acc["merchant"] - rewards + acc["conversion"]
                                     + acc["launch_conversion"] + acc["gas"] + acc["spread"])
        if self.economy.earned_wage_share > 0:
            self.transfer_path[month] += acc["ewa_fees"]   # earned-wage fees, paid to the provider (3 Nov)
        # The card's cash-advance and late fees, paid to its lender (14 Nov 2026).
        self.transfer_path[month] += acc["advance_fee_i"] + acc["late_fee_i"]
        list(map(lambda key: self.ewa_path[key].__setitem__(month, acc["ewa_" + key]), self.ewa_path))
        money = self.cash + self.pcash
        bk = self.book
        pool = bk["pool"] & bk["carried"]
        pool_principal = bk["principal"][pool].sum()
        late = pool & ((((bk["kind"] == BRIDGE) & (bk["due"] < (month + 1) * DAYS))
                        | (self._overdue() > EPS)))
        # What next month's rules may read of this month (demurrage's terms read ``window``).
        self.last.update(flows=acc["flows"], flows_s0=acc["flows_s0"], monthly=monthly, p_low=acc["p_low"],
                         card_internal=acc["card_internal"], bridge_path=acc["bridge_path"], avg_payment=avg_payment,
                         ewa_room=acc["ewa_room"], card_room=acc["card_room"], admitted=admitted,
                         receipts=acc["receipts"], wages_paid=acc["wages_paid"], p_share=p_share)
        # Demurrage's records (decided 4 Nov): the published quote at capital after dealing, the pool's idle cash
        # and the total precautionary money, households' buffers chosen at dealing plus the pool's idle cash. Idle P
        # sits inside the buffers it is part of, so it is recorded beside the total, not in it (the 5 Nov review: as
        # first built the total counted it twice).
        quote = self._quote(self.capital) if self.launched else np.nan
        pool_idle = self._lendable()
        buffers = float(self.buffer.sum())   # the buffers the dealing chose, read from the state, not the record
        precautionary = buffers + pool_idle
        record = (
            ("A", self.status[month].mean()), ("failure_share", acc["failed"] / acc["due"] if acc["due"] > 0 else 0.0),
            ("wage_arrears", acc["wage_failed"] / n),
            ("slow_days", acc["slow_days"]), ("most_sweeps", acc["most_sweeps"]),
            ("ready", float(self.ready)), ("service", float(self.service)), ("r_g", self.r_g), ("r_term", self.r_term),
            ("N", self.capital / n), ("Q", self.Q / n if np.isfinite(self.Q) else np.nan), ("p_yield", self.p_yield),
            # Reported (decided 3 Nov): households' capital after dealing, all pool capital since the issuer holds
            # none (5 Nov), with the income the month credited to it, before CPI.
            ("owners_capital", owners_capital / n),
            ("owners_income", owners_income / n), ("owners_income_net", owners_net / n),
            *(("issuer_" + key, value / n) for key, value in books.items()),
            # The stay test's reading and record (undefined before the 12th month after launch), and all P the
            # issuer's reserves back (participants' P and the pool's cash, the month's average).
            ("issuer_stay", stay), ("issuer_would_leave", float(self.issuer_leaves) if np.isfinite(stay) else np.nan),
            ("P_out", acc["p_all"] / n),
            # Backing: the reserve account against P owed at the close, and the owners' backing top-up (pool arms).
            ("reserves", self.reserves / n), ("backing", self.reserves / owed if self.pool_arm and owed > EPS else np.nan),
            ("backing_topup", topup / n), ("P_bar", bridge_pt / n), ("term_pool", bk["principal"][pool & (bk["kind"] == TERM)].sum() / n),
            ("term_outside", bk["principal"][~bk["pool"] & (bk["kind"] == TERM)].sum() / n), ("c", self.c),
            # Demurrage and competitive P (decided 4 and 5 Nov): idle P (a record), the demurrage the pool took,
            # the issuer's derived share of the reserve return and the monopoly bound, the pool's own cash's reserve
            # return, what the issuer
            # kept and the yield on wallet P before demurrage, the coverage of the bridging capital cost, the rate a
            # bridge drawn this month is sealed at, the coupon cut demurrage paid and the capital cost of the month's
            # bridging (owners' alternative on its principal-time), theta, the published quote at capital after
            # dealing and the quote at N* that dealing read, the parts of the precautionary money and their total, and
            # the month's pool bridges and failed payments by value.
            ("idle", acc["idle"] / n), ("charges", D / n), ("s_issuer", self.s_issuer), ("s_monopoly", self.s_monopoly),
            ("float_pool", acc["float_pool"] / n), ("float_issuer", acc["float_issuer"] / n),
            ("wallet_yield", acc["wallet_yield"] / n),
            ("coverage", self.coverage), ("r_b", self.r_b), ("covered", acc["covered"] / n),
            ("bridge_capital_cost", alternative * bridge_pt / n), ("theta", theta), ("quote", quote),
            ("R_hat", self.R_hat), ("buffers", buffers / n), ("pool_idle", pool_idle / n),
            # Demurrage pays for liquidity kept available (decided 5 Nov), records only: the capital target, the
            # peak bridging need and the standby cash-time a month this month's terms read, and the standby's capital
            # cost a month.
            ("target", self.need / n), ("bridge_peak", self.peak / n), ("standby", self.standby / n),
            ("standby_cost", (alternative - self.p_net) * self.standby / n),
            ("precautionary", precautionary / n), ("bridges", acc["bridges"] / n),
            ("failures", float(acc["failed_new"].sum()) / n),
            # Records only (5 Nov): statements left to revolve on the card, and M0's Comet bridging.
            ("revolved", acc["revolved"] / n), ("comet_bridging", acc["comet_bridging"] / n),
            ("R", R), ("R_net", R_net), ("issuer", issuer),
            ("gas", acc["gas_paid"] / n), ("merchant_fees", acc["merchant"].sum() / n),
            ("conversion_fees", (acc["conversion"] + acc["launch_conversion"]).sum() / n),
            ("gini", gini(spending_wealth)), ("mean_wealth", wealth.mean()),
            ("external", self.external / n), ("valuation", self.valuation / n), ("inflation", inflation / n),
            ("wealth_change", (wealth - start_wealth).mean()),
            ("card_debt", (bk["principal"] + bk["interest"])[
                ~bk["pool"] & np.isin(bk["kind"], (BRIDGE, REVOLVE, CASH_ADVANCE, CHARGED_OFF))].sum() / n),
            # Overdraft holds rounding overdrafts and the failure fees, booked as fee debt from 3 Nov, so the series
            # keeps its meaning; fee_debt holds the fees alone.
            ("overdraft", (bk["principal"] + bk["interest"])[np.isin(bk["kind"], (OVERDRAFT, FEE_DEBT))].sum() / n),
            ("fee_debt", (bk["principal"] + bk["interest"])[bk["kind"] == FEE_DEBT].sum() / n),
            ("savings", self.savings.mean()), ("liquid", (self.cash + self.pcash).mean()),
            # Pool bridges drawn over bridges wanted (named for what it holds, not coverage, the 3 Nov review): of the
            # asks the repayment limit admitted (bills, wages and card statements), the share the pool's cash funded
            # this month; undefined with no ask.
            ("bridges_drawn_over_wanted", acc["drawn"].sum() / acc["want"].sum() if acc["want"].sum() > 0 else np.nan),
            ("experience", experience[self.status[month]].mean() if self.status[month].any() else np.nan),
            ("arrears_share", bk["principal"][late].sum() / pool_principal if pool_principal > 0 else np.nan),
            ("written_off", acc["written_off"] / n),
            ("write_off_rate", acc["written_off"] / pool_principal if pool_principal > 0 else np.nan),
            ("new_pool_loans", acc["new_pool_loans"]), ("new_term_pool", acc["new_term_pool"] / n),
            ("new_term_outside", acc["new_term_outside"] / n), ("refused", acc["refused"] / n),
            ("exit_requested", acc["exit_requested"] / n), ("exit_paid", acc["exit_paid"] / n),
            ("exits_filed", acc["exits_filed"]),   # owners filing a new exit request at the dealing (5 Nov), a count
            # Coverage numerator: the pool's cash income, i.e. interest collected and the reserve return the contract
            # assigns on standby capital, which the compensation base min(NAV, Q) now includes. The idle windfall is
            # left out (decided 30 Oct), so no pool pays for itself on the issuer's transfer; no provider fee exists
            # (5 Nov); recovered principal under the own margin.
            ("interest_collected", collected / n),
            ("pool_costs", (acc["op_cost"] + fixed + acc["written_off"]) / n),
            # interest_collected is the pool's cash income (interest paid), the coverage numerator.
            # Owners' compensation K as built at rho = (1 + 0.9 Rout)/(1 + g) - 1 ~ 0.9 rho_H - g, with g = dJ/J in M2
            # and 0 otherwise, and under the own margin at owners' alternative, on min(NAV, capacity): the coverage
            # denominator with costs and write-offs.
            ("K", compensation * min(self.capital, self.Q) / n), ("owners", (self.shares > EPS).mean()),
            ("durable", held.sum() / n), ("out_interest", acc["out_interest"] / n), ("penalties", acc["penalties"] / n),
            ("savings_income", returns.sum() / n), ("shocks", acc["shocks"] / n), ("pool_cash", self.pool_cash / n),
            # Cash to lend at the close (the credit-death test, the 3 Nov review), beside the gross pool cash.
            ("cash_to_lend", self._cash_to_lend() / n),
            # The pool run under the harsh stress (15 Nov 2026), records only: the cash set aside for exits at the same
            # moment, whether or not the pool serves; the money offered at the dealing and the part that found no
            # room; the month's write-offs by loan kind.
            ("exit_set_aside", (self._lendable() - self._cash_for_loans()) / n),
            ("offers", acc["offers"] / n), ("offers_unused", acc["offers_unused"] / n),
            ("written_off_bridge", acc["written_off_bridge"] / n), ("written_off_term", acc["written_off_term"] / n),
            ("pool_pt", acc["pool_pt"] / n),
            # Distress: the share of job-days interrupted this month, and the wages their payers kept; reported only
            # (3 Nov), the share of jobs interrupted on the month's last day.
            ("laid_off", acc["laid_off"]), ("laid_off_last_day", acc["laid_off_last_day"]),
            ("wages_withheld", acc["withheld"] / n),
            # The harsh stress (decided 14 Nov 2026), records only: the wages of the month's extra layoffs owed to
            # the outside (booked as they arise, at the obligations) and the part of them not paid on its first due
            # date, per capita; the failure share of hit workers and of everyone else (undefined with nothing due);
            # and hit workers' failed shares a person, so everyone else's are fail_shares less these.
            ("wages_out", acc["wages_out"] / n), ("wages_out_late", acc["wage_out_failed"] / n),
            ("failure_share_hit", acc["failed_hit"] / acc["due_hit"] if acc["due_hit"] > EPS else np.nan),
            ("failure_share_rest", (acc["failed"] - acc["failed_hit"]) / (acc["due"] - acc["due_hit"])
             if acc["due"] - acc["due_hit"] > EPS else np.nan),
            ("fail_shares_hit", float(acc["fail_shares"][acc["hit"]].sum()) / n),
            # Reported (decided 31 Oct): the pool's refusals of payers without a card whose loan alone would have
            # been repaid but not the fee on the rest (value per capita, and how many payer-days).
            ("fee_refused", acc["fee_refused"] / n), ("fee_refused_n", acc["fee_refused_n"]),
            # The boundary rule (31 Oct): card rewards received, the pool's operating and fixed costs (paid outside),
            # the money (E and P) of the half of households holding least at the close (the cash check), and the
            # volumes the real-part and transfer reports price.
            ("rewards", rewards.sum() / n), ("pool_operating", acc["pool_operating"] / n),
            ("liquid_low", float(np.sort(money)[:max(n // 2, 1)].mean())),
            ("card_payments", acc["card_n"] / n), ("card_value", acc["card_value"] / n),
            ("p_payments", acc["p_n"] / n), ("p_value", acc["p_value"] / n),
            # The term purchases among them (the 4 Nov review), which the margin's re-count at other payment sizes
            # keeps at their own count.
            ("p_term_payments", acc["p_term_n"] / n), ("p_term_value", acc["p_term_value"] / n),
            ("nocard_bridges", acc["nocard_bridges"] / n), ("pt_card", acc["pt_card"] / n),
            ("pt_term", acc["pt_term"] / n), ("pt_pool_card", acc["pt_pool_card"] / n),
            ("pt_pool_term", acc["pt_pool_term"] / n), ("pt_pool_nocard_card", acc["pt_pool_nocard_card"] / n),
            ("pt_pool_card_credit", acc["pt_pool_card_credit"] / n),
            ("money_bt", acc["liquid_bt"].sum() / n), ("e_bt", (acc["liquid_bt"] - acc["p_bt"]).sum() / n),
            ("p_bt", acc["p_bt"].sum() / n), ("savings_bt", acc["savings_bt"].sum() / n),
            ("shares_bt", acc["shares_bt"].sum() / n), ("deposit_spread", acc["deposit_spread"] / n),
            ("issuer_spread", (acc["spread"].sum() - acc["deposit_spread"]) / n),
            # The failure counts (3 Nov), a person a month, reported only.
            *((key, acc[key].sum() / n) for key in FAILURE_COUNTS),
            # Crossings between E and P (decided 3 Nov), per capita: routine crossings (free) and conversions
            # (paying the fee), how many and their value.
            ("crossings", acc["crossings"][0].sum() / n), ("crossed", acc["crossed"][0].sum() / n),
            ("conversions", acc["crossings"][1].sum() / n), ("converted", acc["crossed"][1].sum() / n),
            # The mean buffer chosen at dealing (the 3 Nov review), people without a card and card holders.
            ("buffer_nocard", buffer_nocard), ("buffer_card", buffer_card),
            # Earned-wage access (3 Nov), per capita: payer-days with an advance, advances, their fees and what is
            # owed on advances at the close.
            ("ewa_uses", acc["ewa_uses"].sum() / n), ("ewa_value", acc["ewa_value"].sum() / n),
            ("ewa_fees", acc["ewa_fees"].sum() / n), ("ewa_owed", self.ewa_owed.sum() / n),
            # Holders' card bridging of the bills and wages their money could not pay (3 Nov), per capita: their cash
            # advances since card limits (14 Nov 2026).
            ("card_bridging", acc["card_bridging"] / n),
            # Card limits (14 Nov 2026), records only: the month's cash-advance and late fees, the card balances charged
            # off and the lines closed (a count), the card purchases past a holder's room, per capita, and the share of
            # people behind on a card's minimum at the close.
            ("advance_fees", acc["advance_fees"] / n), ("late_fees", acc["late_fees"] / n),
            ("charged_off", acc["charged_off"] / n), ("lines_closed", acc["lines_closed"]),
            ("card_spilled", acc["card_spilled"] / n), ("card_delinquent", float((self.card_late_since < BIG).mean())),
            # The yardsticks (decided 3 and 4 Nov), per capita, records only: the pool's own margin and its parts,
            # the joint issuer-and-pool test, households' capital in exit requests still unpaid after dealing (the
            # 90% test's base) and the principal part of payments on written-off pool loans.
            ("own_margin", margin / n), *(("margin_" + key, value / n) for key, value in margin_parts.items()),
            ("joint", joint / n), ("owners_queued", self.owners_queued / n),
            ("recovered_principal", acc["recovered_principal"] / n),
            # Records only (3 and 12 Nov, ``MEASURE_SERIES``): completed purchases as a count a person a month, and the
            # largest single pool loan and the largest borrower's pool debt as shares of pool capital at the close.
            ("purchases_n", acc["bought_n"] / n), ("durables_n", acc["durables_n"] / n),
            *zip(MEASURE_SERIES[2:], self._largest_shares()),
            # The settlement's records (``_chain_records``, ``CHAIN_SERIES``): amounts a person, counts as counted.
            *((key, acc[key] / n) for key in ("own_shortfall", "knock_on", "knock_on_positive")),
            *((key, acc[key]) for key in ("own_shortfall_n", "knock_on_n")),
            *(("knock_on_days_" + key, acc["knock_on_days"][k]) for k, key in enumerate(KNOCK_ON_BINS)),
            ("netting_days", acc["netting_days"]), ("netting_n", acc["netting_n"]),
            *((key, acc[key] / n) for key in ("netting_value", "cash_completed", "netting_lost")))
        # Experience channels, averaged over this month's participants.
        participants = self.status[month]
        record += tuple((key, value[participants].mean() if participants.any() else np.nan) for key, value in parts.items())
        if self.economy.loan_losses == "sourced":
            # The loan-loss bound's records (decided 12 Nov), per person: the pool's bridging and term principal
            # discharged, then outside lenders' by class.
            record += tuple(zip(LOAN_LOSS_SERIES, acc.get("discharged", np.zeros(5)) / n))
            record += ((LOSS_CARRIED, float(self.loss_carried.sum()) / n), ("r_term_business", self.r_term_business))
        list(map(lambda item: self.series[item[0]].append(item[1]), record))

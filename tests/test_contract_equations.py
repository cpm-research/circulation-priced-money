"""The contract's equations, checked against the engine's own runs.

Each test states one equation the paper states, runs small economies with the engine itself and checks, month by month,
that the engine's recorded series and state satisfy it, computed here from the inputs the equation names. The runs use
the test device of ``tests.test_economy_abm`` (``PooledWorld``: savers compare the pool with their own mixed return,
so a pool forms in a small run) with a recorder that copies what the engine read and wrote at each step; the recorder
changes no number the engine computes, except that it forces one pool bridge and one pool term loan 90 days past due
(``Recorded._write_off``), so a short run has write-offs and recoveries for the learned loss to read.

Comparisons are exact where the test repeats the engine's own floating-point operations on the same numbers, and
``np.isclose`` at a relative 1e-12 (``close``) where the test computes the same quantity another way (another order of
summation, or a ratio inverted); each test says which. The equations and the code lines that compute them are tabulated
in the appendix of paper/cpm.tex (Equations and the code that computes them, table tab:code), one row per test; each
test's docstring opens with its row and names the paper's equations by their labels.
"""
from dataclasses import replace
from functools import lru_cache
import unittest

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import (BRIDGE, CHARGE_OFF_NORMAL, DAYS, EPS, EXIT_NOTICE_MONTHS, LOSS_LAG, LOSS_LAG_MONTHS,
                                 OWN_RETURN_MONTHS, RATE_TIE, TERM, WRITE_OFF_DAYS, charge_off_rates, issuer_share)
from tests.test_economy_abm import TINY, PooledWorld


RTOL = 1e-12   # relative tolerance where the test cannot repeat the engine's floating-point operations


def close(a, b, rtol=RTOL, atol=1e-18):
    """Element-wise agreement at a relative 1e-12 (and 1e-18 absolute, for zeros)."""
    return np.allclose(a, b, rtol=rtol, atol=atol, equal_nan=True)


class Recorded(PooledWorld):
    """The test device with a recorder: copies of what each step read and wrote, by month. Nothing it records feeds back
    into the run. One pool bridge (from month FORCE_BRIDGE) and one pool term loan (from month FORCE_TERM) are set 90
    days past due on the first day such a loan is carried, so the run writes both products off and later recovers what
    their borrowers still pay."""

    FORCE_BRIDGE, FORCE_TERM = 7, 7

    def __init__(self, *args):
        """Build the engine's world as it is and add empty records; nothing the engine computes changes."""
        super().__init__(*args)
        self.rec = dict(terms={}, close={}, deal={}, exits={}, reserve={})
        self.forced = np.zeros(2, bool)
        self.book_reads = []
        self.days_now = None
        self._entry = None

    def month(self, month):
        """Run the engine's month after resetting the recorder's own day-by-day sums; nothing the engine computes
        changes."""
        # The month's own accumulators, from the loan book and wallets at each day's accruals.
        self.days_now = dict(B=0.0, W=0.0, covered=0.0, coupons=0.0, bridge_day=np.zeros(DAYS),
                             ready_day=np.zeros(DAYS), sealed=np.zeros((0, 3)), day=0)
        super().month(month)

    def _cycle_terms(self, month):
        """Record the month's published terms and the loss records and cycle they read; nothing the engine computes
        changes."""
        loss_net, exposure = self.loss_net.copy(), self.exposure.copy()
        super()._cycle_terms(month)
        cycle = list(self.window[-2:]) if self.launched else []
        self.rec["terms"][month] = dict(
            launched=self.launched, cycle=cycle, loss_net=loss_net, exposure=exposure,
            learned=self._loss_rates(), r_fix=self.r_fix, r_g=self.r_g, r_term=self.r_term, peak=self.peak,
            standby=self.standby, Q=self.Q, R_hat=self.R_hat, need=self.need, c=self.c, coverage=self.coverage,
            r_b=self.r_b, p_yield=self.p_yield, takes=self._takes_demurrage())

    def _accrue(self):
        """Add the day's pool bridge principal-time, covered cut, coupons, wallet P, sealing terms, carried bridging and
        cash ready to the recorder's sums; nothing the engine computes changes."""
        bk, now = self.book, self.days_now
        bridge = bk["pool"] & bk["carried"] & (bk["kind"] != TERM)
        principal = bk["principal"][bridge]
        now["B"] += principal.sum() / DAYS
        now["covered"] += (principal * bk["cover"][bridge]).sum() / DAYS
        now["coupons"] += (principal * bk["rate"][bridge]).sum() / DAYS
        now["W"] += np.maximum(self.pcash, 0.0).sum() / DAYS
        live = principal > 0
        rows = np.column_stack([bk["m0"][bridge][live], bk["rate"][bridge][live], bk["cover"][bridge][live]])
        now["sealed"] = np.unique(np.vstack([now["sealed"], rows]), axis=0)
        super()._accrue()
        bk = self.book
        now["bridge_day"][now["day"]] = float(bk["principal"][bk["pool"] & bk["carried"] & (bk["kind"] != TERM)].sum())
        now["ready_day"][now["day"]] = self._cash_for_loans() if self.pool_arm else 0.0
        now["day"] += 1

    def _write_off(self, t):
        """Force one pool bridge (from FORCE_BRIDGE) and one pool term loan (from FORCE_TERM) 90 days past due, then
        run the engine's write-off, so a short run has write-offs and recoveries for the learned loss to read."""
        bk, month = self.book, t // DAYS
        live = bk["pool"] & bk["carried"] & (bk["principal"] > EPS)
        # The bridge on a month's last day, so its write-off closes that month and its recovery (collected at the next
        # dealing, the bridge being past due) falls in the next: the learned bridging loss is positive in between.
        last = t % DAYS == DAYS - 1
        bridge = np.flatnonzero(live & (bk["kind"] == BRIDGE))[:1] \
            if month >= self.FORCE_BRIDGE and last and not self.forced[0] else np.zeros(0, int)
        # A term loan made at least 90 days ago, so its first missed payment can be dated within its life.
        old = bk["m0"] * DAYS <= t - WRITE_OFF_DAYS
        term = np.flatnonzero(live & (bk["kind"] == TERM) & old)[:1] \
            if month >= self.FORCE_TERM and not self.forced[1] else np.zeros(0, int)
        bk["due"][bridge] = t - WRITE_OFF_DAYS
        bk["since"][term] = t - WRITE_OFF_DAYS
        self.forced |= np.array([bridge.size > 0, term.size > 0])
        super()._write_off(t)

    def _exits(self, month, owners):
        """Record what the exit rule reads (gap, draws, holdings, requests, cash) and who filed, lapsed and was paid;
        nothing the engine computes changes."""
        review, leave_draw = self.owner_draws
        rec = dict(owners=owners.copy(), gap=self._own_gap(month), review=review.copy(), leave_draw=leave_draw.copy(),
                   value=self.shares * self.nav_ps, start=self.exit_start.copy(), winding=bool(self.winding),
                   lendable=self._lendable(), part=self.part.copy(), spending=self.spending.copy())
        super()._exits(month, owners)
        rec.update(after_start=self.exit_start.copy(), paid_out=self.exit_paid_out.copy(), paid=self.acc["exit_paid"],
                   filed=self.acc["exits_filed"])
        self.rec["exits"][month] = rec

    def _reviews_entry(self):
        """Record the state entry reads after the exits (reviews, money, capital, unpaid exits, who may offer); nothing
        the engine computes changes."""
        out = super()._reviews_entry()
        self._entry = dict(reviews=out.copy(), liquid=self.cash + self.pcash, pcash=self.pcash.copy(),
                           capital=self._all_shares() * self.nav_ps, due=float(self.exit_unpaid.sum()),
                           no_offer=(self.exit_start >= 0) | self.exit_paid_out, mm_share=self.mm_share.copy(),
                           open=bool(self.launched and not self.winding and np.isfinite(self.R_hat) and self.Q > 0))
        return out

    def _debit(self, from_p, from_e, spend=True):
        """Record the accepted offers, buffers and conversion fees at the dealing's move into shares; nothing the
        engine computes changes."""
        # The dealing's one call with spend False moves the accepted offers into shares (``_dealing``).
        if not spend and self._entry is not None and "accepted" not in self._entry:
            self._entry.update(accepted=np.array(from_p, float).copy(), buffer=self.buffer.copy(), rate=self._rate())
        return super()._debit(from_p, from_e, spend)

    def _dealing(self, month):
        """Run the engine's dealing and record its offers, unused offers, target, quote and own alternatives; nothing
        the engine computes changes."""
        self._entry = None
        capital = super()._dealing(month)
        if self._entry is not None and "accepted" in self._entry:
            self._entry.update(offers=self.acc["offers"], unused=self.unused_offers, Q=self.Q, R_hat=self.R_hat,
                               own_alt=self._owners_alternative_nominal().copy())
            self.rec["deal"][month] = self._entry
        self._entry = None
        return capital

    def _reserve_return(self):
        """Record pool cash, wallets, outside flows and charges before and after the reserve return; nothing the
        engine computes changes."""
        acc = self.acc
        rec = dict(pool_cash=self.pool_cash, pcash=self.pcash.copy(), external=self.external, p_bt=acc["p_bt"].copy(),
                   charges_before=acc["charges"].copy())
        D = super()._reserve_return()
        rec.update(D=D, c=self.c, pool_cash_after=self.pool_cash, pcash_after=self.pcash.copy(),
                   external_after=self.external, charges=acc["charges"].copy(), float_pool=acc["float_pool"],
                   wallet_yield=acc["wallet_yield"])
        self.rec["reserve"][self.this_month] = rec
        return D

    def _term_book(self):
        """Record each read of the pool's term book; nothing the engine computes changes."""
        value = super()._term_book()
        self.book_reads.append(value)
        return value

    def _close(self, month, start_wealth, join_draw, review_draw, leave_draw=None):
        """Record the month's sums, losses, exposure, term book, window entry, theta and quote around the engine's
        close; nothing the engine computes changes."""
        acc = self.acc
        # The term book at the last close (None before launch's first close), which the growth reads.
        prev = self.term_book
        rec = dict(self.days_now, covered_acc=acc["covered"], coupons_acc=acc["bridge_coupons"], capital=self.capital,
                   need=self.need, Q=self.Q, term_book_prev=np.nan if prev is None else prev, launched=self.launched,
                   bridge_pt=float(acc["bridge_pt"].sum()))
        self.book_reads = []
        super()._close(month, start_wealth, join_draw, review_draw, leave_draw)
        # With a book at the last close, the close's first read of the term book is the one its growth subtracts from.
        rec.update(lost=acc["lost"].copy(), exposure=acc["exposure"].copy(), refused_term=acc["refused_term"],
                   written_off=acc["written_off"], recovered=acc["recovered"],
                   discharged=float(acc.get("discharged", np.zeros(5))[:2].sum()),
                   book_now=self.book_reads[0] if prev is not None and self.launched else np.nan,
                   entry=self.window[-1] if self.launched else None, theta=self.series["theta"][-1],
                   quote=self.series["quote"][-1])
        self.rec["close"][month] = rec


BASE = replace(TINY, n=100, months=14, distress=0.02, distress_start=1, distress_length=6)
VARIANTS = dict(base=BASE, sourced=replace(BASE, loan_losses="sourced"),
                bound=replace(BASE, issuer_cost=0.995 * Inputs().rho_H))
RUNS = (("M1", "base"), ("U", "base"), ("M2", "base"), ("M1", "sourced"), ("M1", "bound"))


@lru_cache(maxsize=None)
def run(arm, variant="base"):
    """One recorded run at a0 0.6 of ``arm`` in economy ``variant``, kept for every test that reads it."""
    world = Recorded(Inputs(), 0.6, VARIANTS[variant], arm)
    return world, world.run()["series"]


def months(world, key):
    """The months with a record ``key``, in order."""
    return sorted(world.rec[key])


def column(world, key, field, chosen=None):
    """One field of record ``key`` over ``chosen`` months (all by default), as an array."""
    return np.array([world.rec[key][m][field] for m in (months(world, key) if chosen is None else chosen)], float)


def alternative(world):
    """Owners' alternative a, a month: the reserve rate in P terms (rho_H less M2's index), floored at zero, plus the
    owners' spread, from the inputs."""
    return max(world.inputs.rho_H - world.index, 0.0) + world.economy.owner_spread


def p_idle(world):
    """p, what idle P earns a month: the reserve rate in P terms less the issuer's derived custody share of it."""
    rate = max(world.inputs.rho_H - world.index, 0.0)
    return (1 - issuer_share(rate, world.economy.issuer_cost)) * rate


def cycle_months(world, month):
    """The closed months a month's terms read: the last two, from launch (the launch plan stands for the months
    before)."""
    return [m for m in (month - 2, month - 1) if m >= world.economy.burn_in]


def cycle_sum(world, month, field):
    """A month-accumulator summed over the closed months of ``month``'s cycle (the plan carries none)."""
    return float(sum(world.rec["close"][m][field] for m in cycle_months(world, month)))


def launched_terms(world):
    """The months whose terms read a cycle: launch onwards."""
    return [m for m in months(world, "terms") if world.rec["terms"][m]["launched"]]


def learned_loss(world):
    """The learned loss, equation (loss), from the closes' own records: cumulative write-offs less recoveries
    (``acc["lost"]``) before each month, floored at zero, over the principal-time carried up to LOSS_LAG_MONTHS months
    before it. One row a month."""
    closes = months(world, "close")
    lost = np.cumsum(np.vstack([np.zeros(2), column_rows(world, "lost", closes)]), axis=0)[:-1]
    exposure = np.vstack([np.zeros(2), np.cumsum(column_rows(world, "exposure", closes), axis=0)])
    seen = exposure[np.maximum(np.arange(len(closes)) - LOSS_LAG_MONTHS, 0)]
    return np.divide(np.maximum(lost, 0.0), seen, out=np.zeros_like(seen), where=seen > 0)


def column_rows(world, field, chosen):
    """A vector field of the close records, one row a month."""
    return np.vstack([world.rec["close"][m][field] for m in chosen])


def priced_loss(world, series):
    """The loss a month each coupon carries under the loan-loss bound: the sourced charge-off rate at the share of jobs
    without a wage LOSS_LAG months earlier, over 12 (the normal rates in month 0); zero without the bound."""
    total = len(series["laid_off"])
    if world.economy.loan_losses != "sourced":
        return np.zeros((total, 3))
    lagged = series["laid_off"][np.maximum(np.arange(total) - LOSS_LAG, 0)]
    return np.vstack([CHARGE_OFF_NORMAL / 12, *map(lambda share: charge_off_rates(share) / 12, lagged[1:])])


def fixed_rate(world, cycle):
    """f: the cycle's fixed cost over its loans' principal-time; with none lent, the fixed cost a month on the lending
    need; zero with neither or no cycle."""
    lent = sum(entry["lent"] for entry in cycle)
    need = sum(entry["need"] for entry in cycle)
    if lent > EPS:
        return sum(entry["fixed"] for entry in cycle) / lent
    return world.inputs.C_fix * world.n * len(cycle) / need if need > EPS else 0.0


def kept_ready(cycle):
    """The peak bridging need (largest day's carried bridging plus the cycle's refused bridging) and the standby S,
    cash-time held ready up to that peak beyond the bridging carried, in months."""
    if not cycle:
        return 0.0, 0.0
    carried = np.concatenate([entry["bridging"] for entry in cycle])
    ready = np.concatenate([entry["ready"] for entry in cycle])
    peak = carried.max() + sum(entry["refused_bridging"] for entry in cycle)
    return peak, np.minimum(ready, np.maximum(peak - carried, 0.0)).sum() / DAYS


def capital_cost(world, month):
    """K = a B + (a - p) S over ``month``'s cycle, from the principal-time of pool bridges the recorder counted at each
    day's accruals and the standby the cycle's day-by-day records give."""
    a, p = alternative(world), p_idle(world)
    S = kept_ready(world.rec["terms"][month]["cycle"])[1] if world.demurrage else 0.0
    return a * cycle_sum(world, month, "B") + (a - p) * S


class ContractEquationTests(unittest.TestCase):
    """One test per row of the table of equations and the code that computes them (tab:code of paper/cpm.tex)."""

    def test_eq01_coupon_is_alternative_plus_operating_plus_fixed_plus_loss(self):
        """Row 1, the coupon, equations (coupon) and (fixed): each product k (bridging g, term) pays r_k = a + o + f +
        loss_k, floored at zero, a owners' alternative (reserve rate plus owners' spread), o the operating cost, f the
        last two months' fixed cost over their lending (``_fixed_rate``), loss_k the learned loss rate (equation
        (loss)), plus the sourced rate priced under the loan-loss bound (``_priced_loss``) and nothing without it.
        Checked in every month of M1, U, M2, M1 under the loan-loss bound and M1 at the cap on c, at a relative 1e-12
        (the test sums the cycle in another order)."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "terms")
            a, o = alternative(world), world.inputs.o
            f = np.array([fixed_rate(world, world.rec["terms"][m]["cycle"]) for m in chosen])
            learned, priced = learned_loss(world), priced_loss(world, series)
            self.assertTrue(close(column(world, "terms", "r_fix"), f), (arm, variant))
            want_g = np.maximum(0.0, a + o + f + learned[:, 0] + priced[:, 0])
            want_term = np.maximum(0.0, a + o + f + learned[:, 1] + priced[:, 1])
            self.assertTrue(close(column(world, "terms", "r_g"), want_g), (arm, variant))
            self.assertTrue(close(column(world, "terms", "r_term"), want_term), (arm, variant))
            self.assertTrue(close(series["r_g"], want_g) and close(series["r_term"], want_term), (arm, variant))
            # The fixed part is priced on lending after launch, and the bound run prices a loss.
            self.assertTrue(np.any(f > 0), (arm, variant))
            if variant == "sourced":
                self.assertTrue(np.all(priced[:, :2] > 0))

    def test_eq02_capital_cost_of_liquidity_kept_ready(self):
        """Row 2, the capital cost of the liquidity kept ready over the last two months, equations (peak), (standby) and
        (cost): K = a B + (a - p) S, B the pool's bridge book (principal-time), S the standby (pool cash held ready, up
        to the cycle's peak bridging need beyond the bridging carried, cash-time), p what idle P earns. Checked in M1,
        M2 and M1 under the loan-loss bound: each month's bridging capital cost the engine records is a B (relative
        1e-12: the recorder sums B day by day as principal over 30, the engine as each borrower's principal-time), its
        standby is S from the cycle's day-by-day records (relative 1e-12), and in every month c is below its cap, c W
        reproduces K (relative 1e-12: K / W times W)."""
        for arm, variant in (("M1", "base"), ("M2", "base"), ("M1", "sourced")):
            world, series = run(arm, variant)
            closes = [m for m in months(world, "close") if world.rec["close"][m]["launched"]]
            a = alternative(world)
            B = column(world, "close", "B", closes)
            self.assertTrue(close(column(world, "close", "bridge_pt", closes), B))
            self.assertTrue(close([world.rec["close"][m]["entry"]["capital_cost"] for m in closes], a * B))
            # The day-by-day records the standby is read from are the bridging carried and the cash new loans may take.
            self.assertTrue(close(np.concatenate([world.rec["close"][m]["entry"]["bridging"] for m in closes]),
                                  np.concatenate([world.rec["close"][m]["bridge_day"] for m in closes])))
            self.assertTrue(close(np.concatenate([world.rec["close"][m]["entry"]["ready"] for m in closes]),
                                  np.concatenate([world.rec["close"][m]["ready_day"] for m in closes])))
            terms = launched_terms(world)
            cycles = [world.rec["terms"][m]["cycle"] for m in terms]
            S = np.array([kept_ready(cycle)[1] for cycle in cycles])
            peak = np.array([kept_ready(cycle)[0] for cycle in cycles])
            self.assertTrue(close(column(world, "terms", "standby", terms) * np.array(list(map(len, cycles))), S))
            self.assertTrue(close(column(world, "terms", "peak", terms), peak))
            self.assertTrue(np.any(S > 0), arm)
            K = np.array([capital_cost(world, m) for m in terms])
            W = np.array([cycle_sum(world, m, "W") for m in terms])
            c = column(world, "terms", "c", terms)
            free = (c > 0) & (c < p_idle(world))
            self.assertTrue(free.any(), arm)
            self.assertTrue(close((c * W)[free], K[free]), arm)

    def test_eq03_holding_charge_is_capital_cost_over_wallet_capped_at_p(self):
        """Row 3, the holding charge, equation (charge): c = min(K / W, p), W the wallet P balance-time over the last
        two months; zero while the pool takes no charge (no shares, or winding down), with no cycle, with no wallet P,
        and in U. Checked every month in M1, M2, M1 under the bound and M1 with the issuer's cost at 0.995 of the
        reserve rate, where p is small and the cap binds; relative 1e-12 (K is summed another way). The c recorded for
        the month is the one published unless the pool began winding down at the month's dealing, when none is taken and
        0 is recorded."""
        for arm, variant in (("M1", "base"), ("M2", "base"), ("M1", "sourced"), ("M1", "bound"), ("U", "base")):
            world, series = run(arm, variant)
            chosen = months(world, "terms")
            p = p_idle(world)
            K = np.array([capital_cost(world, m) if world.rec["terms"][m]["launched"] else 0.0 for m in chosen])
            W = np.array([cycle_sum(world, m, "W") if world.rec["terms"][m]["launched"] else 0.0 for m in chosen])
            charged = (np.array([bool(world.rec["terms"][m]["cycle"]) for m in chosen])
                       & column(world, "terms", "takes", chosen).astype(bool) & (W > EPS) & world.demurrage)
            want = np.where(charged, np.minimum(np.divide(K, W, out=np.zeros_like(K), where=W > EPS), p), 0.0)
            c = column(world, "terms", "c", chosen)
            self.assertTrue(close(c, want), (arm, variant))
            self.assertTrue(np.all(c <= p), (arm, variant))
            taken = np.array([world.rec["reserve"].get(m, dict(c=0.0))["c"] for m in chosen])
            self.assertTrue(close(series["c"], taken))
            self.assertTrue(np.all((series["c"] == c) | (series["c"] == 0.0)))
            if variant == "bound":
                self.assertTrue(np.any(charged & (c == p)))
            elif arm != "U":
                self.assertTrue(np.any(charged & (c > 0) & (c < p)), arm)

    def test_eq04_coverage_and_the_bridge_price(self):
        """Row 4, coverage and the bridge price, equations (coverage) and (bridgeprice): kappa = min(1, c W / K), zero
        with no capital cost to cover and in U; a bridge drawn in the month is sealed at r_b = r_g - kappa a, and with
        kappa = 1, r_b = o + f + loss (plus the priced loss under the bound). kappa is checked at a relative 1e-12 (K
        summed another way), r_b exactly against the engine's own r_g and kappa (the same operations), the kappa = 1
        form at a relative 1e-12 (r_g - a against the sum without a) wherever the coupon's floor at zero does not bind,
        and every pool bridge carried on any day is sealed at the r_b of the month it was made, with the cut r_g - r_b
        of that month (exact)."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "terms")
            a = alternative(world)
            K = np.array([capital_cost(world, m) if world.rec["terms"][m]["launched"] else 0.0 for m in chosen])
            W = np.array([cycle_sum(world, m, "W") if world.rec["terms"][m]["launched"] else 0.0 for m in chosen])
            c = column(world, "terms", "c", chosen)
            kappa = np.where((K > EPS) & (c > 0), np.minimum(1.0, c * W / np.where(K > EPS, K, 1.0)), 0.0)
            coverage = column(world, "terms", "coverage", chosen)
            self.assertTrue(close(coverage, kappa), (arm, variant))
            r_g, r_b = column(world, "terms", "r_g", chosen), column(world, "terms", "r_b", chosen)
            np.testing.assert_array_equal(r_b, r_g - coverage * a)
            np.testing.assert_array_equal(series["r_b"], r_b)
            learned, priced = learned_loss(world), priced_loss(world, series)
            f = column(world, "terms", "r_fix", chosen)
            # kappa = 1: min(1, c W / K) with c = K / W, which rounding can leave one unit in the last place below 1.
            full = (coverage >= 1.0 - RTOL) & (r_g > 0)
            self.assertTrue(close(r_b[full], (world.inputs.o + f + learned[:, 0] + priced[:, 0])[full]), (arm, variant))
            if world.demurrage and variant != "bound":
                self.assertTrue(full.any(), (arm, variant))
            if variant == "bound":
                self.assertTrue(np.any((coverage > 0) & (coverage < 1)))
            # Every bridge carried on any day: its rate and its cut are its month's.
            sealed = np.vstack([world.rec["close"][m]["sealed"] for m in months(world, "close")])
            made = sealed[:, 0].astype(int)
            self.assertTrue(sealed.size > 0, (arm, variant))
            np.testing.assert_array_equal(sealed[:, 1], r_b[made])
            np.testing.assert_array_equal(sealed[:, 2], (r_g - r_b)[made])

    def test_eq05_p_yield(self):
        """Row 5, P's yield, equation (yield): y = index + p - c, p = (1 - s_I) rho_p with s_I = c_I / rho_p, the
        issuer's derived custody share, and the index M2's CPI indexation (zero in M1 and U). Exact against the
        published c (the same operations); p from the inputs at a relative 1e-12. The month's recorded yield is the
        published one unless the pool began winding down at the month's dealing, when no c is taken."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "terms")
            self.assertTrue(close(world.p_net, p_idle(world)))
            self.assertEqual(world.index, world.economy.inflation if arm == "M2" else 0.0)
            c = column(world, "terms", "c", chosen)
            np.testing.assert_array_equal(column(world, "terms", "p_yield", chosen), world.index + world.p_net - c)
            np.testing.assert_array_equal(series["p_yield"], world.index + world.p_net - series["c"])
        self.assertGreater(run("M2")[0].index, 0.0)

    def test_eq06_theta_is_the_charges_share_of_bridging_finance(self):
        """Row 6, the charge's share of bridging finance, Proposition (The share): theta = covered / (covered + bridge
        coupons accrued), covered the cut kappa a demurrage pays on each carried pool bridge's principal-time. General
        form exact against the engine's own sums, and at a relative 1e-12 against the recorder's (principal times rate,
        summed per day then over 30). Each carried bridge has cut plus coupon r_g of its month, so theta always lies
        between the least and the greatest kappa_m a / r_g(m) over the months its bridges were sealed (to 1e-12); where
        every bridge carried in the month was sealed in one month at kappa = 1, theta = a / r_g of that month (relative
        1e-12). In other months theta differs from a / r_g by the coupon's change between sealing months; the test
        states how far in M1 (the October 2026 draft read theta = a / r_g only as that ceiling; Proposition (The share)
        of paper/cpm.tex states theta = a over the gross coupon weighted by principal-time)."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "close")
            covered = column(world, "close", "covered_acc", chosen)
            coupons = column(world, "close", "coupons_acc", chosen)
            total = covered + coupons
            general = np.divide(covered, total, out=np.full(total.shape, np.nan), where=total > 0)
            np.testing.assert_array_equal(series["theta"], general)
            mine_cov, mine_cpn = column(world, "close", "covered", chosen), column(world, "close", "coupons", chosen)
            mine = np.divide(mine_cov, mine_cov + mine_cpn, out=np.full(total.shape, np.nan), where=total > 0)
            self.assertTrue(close(series["theta"], mine), (arm, variant))
            if not world.demurrage:
                continue
            a = alternative(world)
            r_g, kappa = column(world, "terms", "r_g", chosen), column(world, "terms", "coverage", chosen)
            ratio = kappa * a / r_g
            sealed = [world.rec["close"][m]["sealed"][:, 0].astype(int) for m in chosen]
            low = np.array([ratio[s].min() if s.size else np.nan for s in sealed])
            high = np.array([ratio[s].max() if s.size else np.nan for s in sealed])
            seen = np.isfinite(general) & np.isfinite(low)
            self.assertTrue(seen.any(), (arm, variant))
            self.assertTrue(np.all(general[seen] >= low[seen] * (1 - RTOL)), (arm, variant))
            self.assertTrue(np.all(general[seen] <= high[seen] * (1 + RTOL)), (arm, variant))
            # kappa = 1 on every bridge carried in the month (each sealed in a month of full coverage): each bridge's
            # cut is a, so theta = a B / (covered + coupons) = a / (the coupon r_g its bridges were sealed under,
            # weighted by principal-time), exactly a / r_g when that coupon did not change (relative 1e-12).
            full = seen & np.array([s.size > 0 and np.all(kappa[s] >= 1.0 - RTOL) for s in sealed])
            self.assertEqual(bool(full.any()), variant != "bound", (arm, variant))   # at the cap kappa is below 1
            B = column(world, "close", "B", chosen)
            self.assertTrue(close(mine_cov[full], a * B[full]), (arm, variant))
            weighted = (mine_cov + mine_cpn)[full] / B[full]
            self.assertTrue(close(general[full], a / weighted), (arm, variant))
            # The special form against this month's coupon alone, theta = a / r_g, needs a constant coupon: where the
            # coupons of every sealing month are within 1% of each other, it holds within 1% relative. (The weighted
            # coupon lies between the sealing months' coupons, so the gap is at most their spread.) The coupon moves
            # month to month with the fixed cost's part and the learned loss; the forced write-off moves it most.
            spread = np.array([r_g[s].max() / r_g[s].min() - 1 if s.size else np.inf for s in sealed])
            steady = full & (spread <= 0.01)
            self.assertTrue(steady.any() or variant == "bound", (arm, variant))
            self.assertTrue(np.all(np.abs(general[steady] / (a / r_g)[steady] - 1) <= 0.01), (arm, variant))

    def test_eq07_capital_target_and_quote(self):
        """Row 7, the capital target and the quote, equations (target) and (quote): N* = term lending need + peak
        bridging need in M1 and M2 (the mean of the cycle's term lending needs, each carried term principal-time plus
        refused term lending plus the growth of the term book, floored at zero, and the cycle's peak bridging need), the
        lending need alone in U (mean carried pool principal-time plus refused plus the same growth). The quote at
        capital N is (a min(N, N*) + p max(N - N*, 0)) / N, so the quote at N* is a. N* and the need are checked at a
        relative 1e-12 (a mean taken another way), the need's parts and the quote at N exactly (the same operations),
        the quote at N* exactly in the form a N* / N* and at a relative 1e-12 against a."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            terms = launched_terms(world)
            cycles = [world.rec["terms"][m]["cycle"] for m in terms]
            mean = lambda key: np.array([np.mean([entry[key] for entry in cycle]) for cycle in cycles])
            peak = np.array([kept_ready(cycle)[0] for cycle in cycles])
            need = mean("need_term") + peak if world.demurrage else mean("need")
            Q = column(world, "terms", "Q", terms)
            self.assertTrue(close(column(world, "terms", "need", terms), need), (arm, variant))
            np.testing.assert_array_equal(Q, column(world, "terms", "need", terms))   # N* is the target, F = 0
            a, p = alternative(world), world.p_net
            R_hat = column(world, "terms", "R_hat", terms)
            quoted = Q > EPS
            np.testing.assert_array_equal(R_hat[quoted], (a * Q[quoted]) / Q[quoted])
            self.assertTrue(close(R_hat[quoted], a), (arm, variant))
            # The quote at the capital after dealing, as published at the close.
            closes = [m for m in months(world, "close") if world.rec["close"][m]["launched"]]
            N, Qc = column(world, "close", "capital", closes), column(world, "close", "Q", closes)
            held = N > 0
            want = (a * np.minimum(N, Qc) + 0.0 + p * np.maximum(N - Qc, 0.0)) / np.where(held, N, 1.0)
            np.testing.assert_array_equal(column(world, "close", "quote", closes)[held], want[held])
            # The parts of each month's term lending need (and the lending need) in its window entry.
            prev = column(world, "close", "term_book_prev", closes)
            now = column(world, "close", "book_now", closes)
            growth = np.where(np.isfinite(prev), np.maximum(now - prev, 0.0), 0.0)
            entries = [world.rec["close"][m]["entry"] for m in closes]
            exposure = column_rows(world, "exposure", closes)
            np.testing.assert_array_equal([entry["need_term"] for entry in entries],
                                          exposure[:, 1] + column(world, "close", "refused_term", closes) + growth)
            self.assertTrue(np.any(growth > 0) and np.any(exposure[:, 1] > 0), (arm, variant))

    def test_eq08_entry_pro_rata_to_the_target_and_exit_by_the_logistic(self):
        """Row 8, entry and exit, equation (exit) and section (Entry and exit). Entry: a saver offers the money-market
        part of its spare money (its liquid money above its buffer, one conversion off for the part held in E) when the
        quote at N* plus the index is at least its own alternative (here the test device's own mixed return plus the
        owners' spread), it reviews entry this month and has no standing exit request; offers are accepted pro rata up
        to N* less current capital plus the executed exits pool cash left unpaid. Exit: an owner reviewing (draw below
        upsilon) files for its whole holding when its draw is below logistic((-g - h) / s), g its 12-month realised
        return less a, times its own capital, a month, h one conversion of its holding over 12 months for an owner paid
        in E (zero for a participant), s 1e-4 of its monthly spending; a standing request is paid after the two-month
        notice from pool cash, pro rata if cash is short, and lapses if the owner reviews again and its draw no longer
        says leave. Accepted offers at a relative 1e-12 (the test repeats the engine's operations, compared loosely for
        safety); the logistic is computed here as 1 / (1 + exp(x)), not the engine's tanh form, so people whose draw
        lies within 1e-9 of their probability are left out of the comparison of who files."""
        for arm, variant in (("M1", "base"), ("U", "base"), ("M2", "base"), ("M1", "sourced")):
            world, series = run(arm, variant)
            deals = [world.rec["deal"][m] for m in months(world, "deal")]
            invest = [d["open"] & (d["R_hat"] + world.index >= d["own_alt"] - RATE_TIE) & d["reviews"] & ~d["no_offer"]
                      for d in deals]
            mobile = [np.maximum(d["liquid"] - d["buffer"], 0.0) * d["mm_share"] for d in deals]
            native = [np.minimum(m, np.maximum(d["pcash"], 0.0)) for m, d in zip(mobile, deals)]
            offer = [np.where(i, n + (m - n) / (1 + d["rate"]), 0.0)
                     for i, m, n, d in zip(invest, mobile, native, deals)]
            room = [max(d["Q"] - d["capital"], 0.0) + d["due"] for d in deals]
            want = [o * min(1.0, r / o.sum()) if o.sum() > 0 else o for o, r in zip(offer, room)]
            self.assertTrue(close(np.concatenate([d["accepted"] for d in deals]), np.concatenate(want)), (arm, variant))
            self.assertTrue(close([d["offers"] for d in deals], [o.sum() for o in offer]))
            self.assertTrue(any(d["accepted"].sum() > 0 for d in deals))
            self.assertTrue(any(d["offers"] > r + EPS for d, r in zip(deals, room)))   # some dealing rations
            # The quote at N* is a in every month, never below an entrant's own alternative here (each own rate is at
            # most rho_H), so the quote test never excludes a saver who reviews, may offer and has spare money: entry
            # is perfectly elastic at the quote (the paper's proposition on capital at the target). Entry is limited
            # by the reviews, the standing requests and the room alone.
            self.assertFalse(any((d["open"] & d["reviews"] & ~d["no_offer"] & ~i).any()
                                 for i, d in zip(invest, deals)), (arm, variant))
            # Exits.
            chosen = months(world, "exits")
            exits = [world.rec["exits"][m] for m in chosen]
            scale = [world.inputs.noise * world.economy.leave_noise * e["spending"] for e in exits]
            threshold = [np.where(e["part"], 0.0, world.conversion) * e["value"] / OWN_RETURN_MONTHS for e in exits]
            with np.errstate(over="ignore"):
                chance = [1.0 / (1.0 + np.exp((np.nan_to_num(e["gap"]) + h) / s))
                          for e, h, s in zip(exits, threshold, scale)]
            reviews = [e["owners"] & (e["review"] < world.inputs.upsilon) & np.isfinite(e["gap"]) for e in exits]
            leaves = [r & (e["leave_draw"] < p) for r, e, p in zip(reviews, exits, chance)]
            clear = [np.abs(e["leave_draw"] - p) > 1e-9 for e, p in zip(exits, chance)]
            filed = [e["start"] >= 0 for e in exits]
            calm = np.array([not e["winding"] for e in exits])
            new = [(e["after_start"] == m) & ~f for e, m, f in zip(exits, chosen, filed)]
            self.assertTrue(all(np.array_equal((n & c), (l & ~f & c)) for n, l, f, c, ok in
                                zip(new, leaves, filed, clear, calm) if ok), (arm, variant))
            lapsed = [f & r & ~l & c for f, r, l, c in zip(filed, reviews, leaves, clear)]
            self.assertTrue(all(np.all(e["after_start"][x] == -1) for e, x, ok in zip(exits, lapsed, calm) if ok))
            wants = [e["owners"] & ((f & ~r) | l) for e, f, r, l in zip(exits, filed, reviews, leaves)]
            due = [w & f & (m - e["start"] >= EXIT_NOTICE_MONTHS) for w, f, e, m in zip(wants, filed, exits, chosen)]
            self.assertTrue(all(np.all(~e["paid_out"] | d) for e, d, ok in zip(exits, due, calm) if ok))
            asked = np.array([e["value"][d].sum() for e, d in zip(exits, due)])
            lendable = np.array([e["lendable"] for e in exits])
            self.assertTrue(close(column(world, "exits", "paid", chosen)[calm], np.minimum(asked, lendable)[calm]))
            self.assertTrue(close(column(world, "exits", "filed", chosen)[calm],
                                  np.array([(l & ~f).sum() for l, f in zip(leaves, filed)])[calm]))
            self.assertGreater(float(column(world, "exits", "filed", chosen).sum()), 0.0, (arm, variant))
        self.assertTrue(any(column(run(*key)[0], "exits", "paid").sum() > 0 for key in RUNS[:4]))

    def test_eq09_learned_loss(self):
        """Row 9, the learned loss, equation (loss): loss_k = max(cumulative write-offs less recoveries of product k to
        date, 0) over the product's cumulative principal-time up to LOSS_LAG_MONTHS (3) months before the month; zero
        before any exposure. The month's write-offs less recoveries are the engine's own write-downs less payments on
        written-off loans (exactly, without the bound; under it the sourced discharges count as written off but not in
        the learned loss). Relative 1e-12 (cumulative sums against the engine's running sum). The runs force one bridge
        and one term loan 90 days past due, so both products write off and recover."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "close")
            learned = learned_loss(world)
            self.assertTrue(close(np.vstack([world.rec["terms"][m]["learned"] for m in chosen]), learned))
            lost = column_rows(world, "lost", chosen).sum(axis=1)
            booked = (column(world, "close", "written_off", chosen) - column(world, "close", "discharged", chosen)
                      - column(world, "close", "recovered", chosen))
            self.assertTrue(close(lost, booked, atol=1e-15), (arm, variant))
            if variant != "bound":
                self.assertTrue(np.all(world.forced), (arm, variant))
                self.assertTrue(np.all(learned.max(axis=0) > 0), (arm, variant))
                self.assertGreater(float(column(world, "close", "recovered", chosen).sum()), 0.0)
        # The lag: a month's exposure counts only from the fourth month's terms after it (hand case on the records).
        world = run("M1")[0]
        m = max(months(world, "terms"))
        exposure = world.rec["terms"][m]["exposure"]
        self.assertEqual(exposure.shape[0], m)
        seen = exposure[:-LOSS_LAG_MONTHS].sum(axis=0)
        terms = world.rec["terms"][m]
        self.assertTrue(close(terms["learned"], np.maximum(terms["loss_net"], 0) / seen))

    def test_eq10_no_charge_in_u(self):
        """Row 10, arm U: the same pool and P with no holding charge, so c = 0, kappa = 0, r_b = r_g and no charge is
        taken, in every month (exact); N* is the lending need (the text after equation (target)). The engine's own U and
        M1 comparison on the same draws is ``test_u_is_m1_with_no_demurrage_on_the_same_draws`` in
        tests.test_economy_abm."""
        world, series = run("U")
        self.assertFalse(world.demurrage)
        self.assertFalse(series["c"].any() or series["coverage"].any() or series["charges"].any())
        np.testing.assert_array_equal(series["r_b"], series["r_g"])
        np.testing.assert_array_equal(column(world, "terms", "c"), 0.0)
        reserve = [world.rec["reserve"][m] for m in months(world, "reserve")]
        self.assertFalse(any(r["D"] for r in reserve))
        self.assertTrue(np.any(series["N"] > 0) and np.any(series["bridges"] > 0))

    def test_eq11_charges_stay_in_the_household_economy(self):
        """Row 11, conservation, Proposition (Incidence at full coverage): the charges collected in a month are c times
        each wallet's P balance-time (exact, the same operation), their sum D is credited to the pool's cash with the
        pool cash's own reserve return (exact), each wallet is credited its yield before the charge less the charge
        (exact), and the money coming into the household economy at that step is the yield on wallet P and the pool
        cash's return alone (exact): the charge moves money from holders to the household-owned pool and nothing leaves.
        The month's wealth change equals its outside flows, valuation and inflation (1e-12 absolute, as the engine's own
        check)."""
        for arm, variant in RUNS:
            world, series = run(arm, variant)
            chosen = months(world, "reserve")
            records = [world.rec["reserve"][m] for m in chosen]
            for_each = lambda check: all(map(check, records))
            self.assertTrue(for_each(lambda r: np.array_equal(r["charges"] - r["charges_before"], r["c"] * r["p_bt"])))
            self.assertTrue(for_each(lambda r: r["D"] == float((r["c"] * r["p_bt"]).sum())))
            self.assertTrue(for_each(lambda r: r["pool_cash_after"] == r["pool_cash"] + (r["D"] + r["float_pool"])))
            self.assertTrue(for_each(lambda r: np.array_equal(
                r["pcash_after"], r["pcash"] + (world.p_net * r["p_bt"] - r["c"] * r["p_bt"]))))
            self.assertTrue(for_each(
                lambda r: r["external_after"] == r["external"] + (r["wallet_yield"] + r["float_pool"])))
            np.testing.assert_allclose(series["charges"][chosen], column(world, "reserve", "D") / world.n, rtol=0)
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            if world.demurrage:
                self.assertGreater(float(column(world, "reserve", "D").sum()), 0.0, (arm, variant))


if __name__ == "__main__":
    unittest.main()

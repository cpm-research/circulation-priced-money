"""Tests for random purchases and card statements on each holder's own date, each off by
default (``Economy.purchases``, ``Economy.statement_dates``), at small scale.

What is covered
---------------
* Random purchases: over many person-months the Poisson count has mean and variance near 32; under "poisson_size"
  each purchase keeps its size, so expected spending is unchanged and each month's spending is the count times that
  size; under "poisson_month" each person's month of purchases is exactly the default month, a count of zero taken
  as one; the draws are the same in every arm of a seed, with uniform, ring and hub sellers; "fixed" builds the month
  exactly as the default recipe does; an example of a person with mean spending.
* Own statement dates: closing days drawn once and the same in every arm; every holder's cycle is 30 days and each
  statement is due 21 days after it closes; every card purchase falls due 21 to 50 days after it is made; the
  statements of a cycle sum to its card purchases; a statement due day leaves everyone not due that day as it was;
  the replay's view without P defers each cycle's card-eligible P payments to its due day; "common" closes on day 29
  and is due on day 20 only.
* Money is conserved every month in every arm with each setting on; an unknown value is refused.

That every value a run produces with both settings at their defaults is unchanged bit for bit is checked outside the
suite, against the commit before the settings.
"""
import unittest
from dataclasses import replace

import numpy as np
from scipy.stats import poisson

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import Economy, _World
from cpm_abm.engine.constants import DAYS, LABOUR_SHARE, SERVICE, STATEMENT_DATE_STREAM

ARMS = ("S0", "M0", "U", "M1", "M2")
TINY = Economy(n=80, months=6, burn_in=3)


def month_of_purchases(w, month):
    """The service purchases ``w`` makes for ``month`` (buyer, seller, amount, settle, card), from an empty table of
    obligations, nothing else run."""
    w.acc = {}
    w.ob = {key: value[:0] for key, value in w.ob.items()}
    w.req = {key: value[:0] for key, value in w.req.items()}
    w._obligations(month)
    service = w.ob["kind"] == SERVICE
    return {key: w.ob[key][service] for key in ("buyer", "seller", "amount", "settle", "card")}


def identity_holds(test, economy, a0=0.4):
    """Money is conserved every month in every arm of ``economy``, as the existing identity tests read it."""
    for arm in ARMS:
        series = _World(Inputs(), a0, economy, arm).run()["series"]
        np.testing.assert_allclose(series["wealth_change"],
                                   series["external"] + series["valuation"] + series["inflation"], atol=1e-12,
                                   err_msg=f"{arm}, {economy.purchases}, {economy.statement_dates}")


class PurchaseTests(unittest.TestCase):
    """Purchases arrive at random."""

    def test_the_count_has_mean_and_variance_near_32(self):
        """Over 40,000 person-months the count's mean is 32 within 0.1 (four standard errors) and its variance 32
        within 1 (about four standard errors); under "poisson_month" a count of zero is taken as one."""
        w = _World(Inputs(), 0.2, replace(TINY, n=2000, purchases="poisson_size"), "S0")
        counts = np.concatenate([w._purchase_counts(month)[0] for month in range(20)])
        self.assertEqual(counts.size, 40_000)
        self.assertLess(abs(counts.mean() - 32), 0.1)
        self.assertLess(abs(counts.var() - 32), 1.0)
        w = _World(Inputs(), 0.2, replace(TINY, n=2000, purchases="poisson_month"), "S0")
        month_counts, divisor = w._purchase_counts(0)
        self.assertGreaterEqual(int(month_counts.min()), 1)
        np.testing.assert_array_equal(month_counts, divisor)

    def test_poisson_size_keeps_each_purchase_and_expected_spending(self):
        """Under "poisson_size" every purchase is 41.7% of its buyer's spending over 32, each person's month is its
        count times that, and over 4,000 person-months spending on purchases is within 0.5% of the as-built total
        (one standard deviation is 0.28% at 4,000 people)."""
        w = _World(Inputs(), 0.2, replace(TINY, n=400, purchases="poisson_size"), "S0")
        size = (1 - LABOUR_SHARE) * w.spending / 32
        spent, built = 0.0, 0.0
        for month in range(10):
            count = w._purchase_counts(month)[0]
            rows = month_of_purchases(w, month)
            np.testing.assert_allclose(rows["amount"], size[rows["buyer"]], rtol=1e-15)
            np.testing.assert_array_equal(np.bincount(rows["buyer"], minlength=w.n), count)
            np.testing.assert_allclose(np.bincount(rows["buyer"], weights=rows["amount"], minlength=w.n),
                                       count * size, rtol=1e-12)
            spent += rows["amount"].sum()
            built += (1 - LABOUR_SHARE) * w.spending.sum()
        self.assertLess(abs(spent / built - 1), 0.005)

    def test_poisson_month_keeps_each_persons_month_exactly(self):
        """Under "poisson_month" each person's purchases sum to 41.7% of its spending exactly, in as many purchases
        as its count, each of equal size."""
        w = _World(Inputs(), 0.2, replace(TINY, n=400, purchases="poisson_month"), "S0")
        for month in range(3):
            count = w._purchase_counts(month)[0]
            rows = month_of_purchases(w, month)
            np.testing.assert_array_equal(np.bincount(rows["buyer"], minlength=w.n), count)
            np.testing.assert_allclose(np.bincount(rows["buyer"], weights=rows["amount"], minlength=w.n),
                                       (1 - LABOUR_SHARE) * w.spending, rtol=1e-12)
            np.testing.assert_allclose(rows["amount"], (1 - LABOUR_SHARE) * w.spending[rows["buyer"]]
                                       / count[rows["buyer"]], rtol=1e-15)
        self.assertGreater(len(np.unique(count)), 10)   # the counts do vary

    def test_the_draws_are_the_same_in_every_arm_with_every_seller_rule(self):
        """Under each random reading and each seller rule, every arm of a seed makes the same purchases: buyers,
        sellers, amounts, settle dates and card flags; the days are uniform over the month and nobody buys from
        itself."""
        for purchases in ("poisson_size", "poisson_month"):
            for sellers in ("uniform", "ring", "hubs"):
                economy = replace(TINY, n=200, purchases=purchases, sellers=sellers)
                made = {arm: month_of_purchases(_World(Inputs(), 0.2, economy, arm), 4) for arm in ARMS}
                for arm in ARMS[1:]:
                    for key in made["S0"]:
                        np.testing.assert_array_equal(made[arm][key], made["S0"][key], err_msg=f"{arm} {key}")
                rows = made["S0"]
                self.assertFalse(np.any(rows["buyer"] == rows["seller"]))
                self.assertTrue(np.all((rows["settle"] >= 4 * DAYS)))

    def test_fixed_is_the_recipe_as_built(self):
        """Under "fixed" (the default) the month is built exactly as before the setting: 32 purchases a person on
        stream 11, seller, day and card flag in that order, each 41.7% of spending over 32, and nothing is drawn for
        the count."""
        economy = replace(TINY, n=100)
        self.assertEqual(Economy().purchases, "fixed")
        w = _World(Inputs(), 0.2, economy, "M1")
        self.assertEqual(w._purchase_counts(2), (32, 32))
        rows = month_of_purchases(w, 2)
        n, rng = economy.n, np.random.default_rng(np.random.SeedSequence([economy.seed, 11, 2]))
        buyer = np.repeat(np.arange(n), 32)
        seller = (buyer + 1 + rng.integers(0, n - 1, size=buyer.size)) % n
        rng.integers(0, DAYS, size=buyer.size)
        card = rng.random(buyer.size) < w.card_share
        amount = (1 - LABOUR_SHARE) * w.spending[buyer] / 32
        self.assertEqual(rows["buyer"].size, buyer.size)
        made = sorted(zip(rows["buyer"].tolist(), rows["seller"].tolist(), rows["amount"].tolist(),
                          rows["card"].tolist()))
        built = sorted(zip(buyer.tolist(), seller.tolist(), amount.tolist(), card.tolist()))
        self.assertEqual(made, built)

    def test_the_hand_case_of_a_person_with_mean_spending(self):
        """$6,440 a month: purchases take $2,685, $83.92 each; 24, 40 and 44 purchases spend $2,014, $3,357 and $3,693
        under "poisson_size", and 40 purchases of $67.14 spend $2,685 under "poisson_month". The count's standard
        deviation is 5.66, 17.7% of the mean; 40 or more comes with probability 0.096 and 44 or more 0.025."""
        month = (1 - LABOUR_SHARE) * 6440.0
        self.assertAlmostEqual(month, 2685.48, places=2)
        self.assertAlmostEqual(month / 32, 83.92, places=2)
        self.assertEqual([round(k * month / 32) for k in (24, 40, 44)], [2014, 3357, 3693])
        self.assertAlmostEqual(month / 40, 67.14, places=2)
        self.assertAlmostEqual(np.sqrt(32), 5.66, places=2)
        self.assertAlmostEqual(np.sqrt(32) / 32, 0.177, places=3)
        self.assertAlmostEqual(poisson.sf(39, 32), 0.096, places=3)
        self.assertAlmostEqual(poisson.sf(43, 32), 0.025, places=3)

    def test_money_is_conserved_with_random_purchases(self):
        """With each random reading on, and shocks on, the identity holds every month in every arm."""
        for purchases in ("poisson_size", "poisson_month"):
            identity_holds(self, replace(TINY, n=100, shocks=True, purchases=purchases))

    def test_an_unknown_reading_is_refused(self):
        """A misspelt reading of either setting is refused."""
        with self.assertRaises(ValueError):
            Economy(purchases="poisson")
        with self.assertRaises(ValueError):
            Economy(statement_dates="spread")


class Recorder(_World):
    """A world that records, by day, each holder's card purchases, the statements that close and those that fall
    due, and what a due day changes for people not due on it."""

    def __init__(self, *args):
        super().__init__(*args)
        self.bought, self.closed, self.due_on, self.untouched = [], [], [], True
        self.deferred_total, self.internal_total = 0.0, 0.0

    def _settle(self, month, t):
        before = self.card_unbilled.copy()
        super()._settle(month, t)
        self.bought.append((t, self.card_unbilled - before))

    def _statement(self, d, t):
        names = ("card_statement", "card_late_since", "card_late_month", "card_past_due", "card_fees",
                 "card_interest", "card_paid")
        before = {name: getattr(self, name).copy() for name in names}
        super()._statement(d, t)
        on = self.card_due == d
        if self.economy.statement_dates == "own" or d == 20:
            self.due_on.append((t, on.copy(), before["card_statement"]))
        for name in names:
            self.untouched &= bool(np.array_equal(getattr(self, name)[~on], before[name][~on]))

    def _close_statements(self, d):
        if self.economy.statement_dates == "own":
            self.internal_total += float(self.today["card_internal"].sum())
        unbilled = self.card_unbilled.copy()
        super()._close_statements(d)
        t = self.this_month * DAYS + d
        closing = self.card_close == d if self.economy.statement_dates == "own" else np.zeros(self.n, bool)
        self.closed.append((t, closing, unbilled))

    def _s0_deferred(self, d):
        deferred = super()._s0_deferred(d)
        self.deferred_total += float(np.sum(deferred))
        return deferred


class StatementDateTests(unittest.TestCase):
    """Card statements fall on each holder's own date."""

    @classmethod
    def setUpClass(cls):
        """One small world under each reading, no inflation (so no statement is scaled), run to its end in M1."""
        cls.economy = replace(TINY, n=150, burn_in=2, months=3, inflation=0.0, statement_dates="own")
        cls.own = Recorder(Inputs(), 0.5, cls.economy, "M1")
        cls.own.run()
        cls.common = Recorder(Inputs(), 0.5, replace(cls.economy, statement_dates="common"), "M1")
        cls.common.run()

    def test_closing_days_are_drawn_once_and_shared_by_every_arm(self):
        """Each person's closing day is uniform over the 30 days on its own stream, the same in every arm; its due
        day is 21 days later; by default every statement closes on day 29 and is due on day 20."""
        days = {arm: _World(Inputs(), 0.2, self.economy, arm).card_close for arm in ARMS}
        for arm in ARMS[1:]:
            np.testing.assert_array_equal(days[arm], days["S0"])
        drawn = np.random.default_rng(np.random.SeedSequence([self.economy.seed, STATEMENT_DATE_STREAM])).integers(
            0, DAYS, size=self.economy.n)
        np.testing.assert_array_equal(days["S0"], drawn)
        np.testing.assert_array_equal(self.own.card_due, (self.own.card_close + 21) % DAYS)
        big = _World(Inputs(), 0.2, replace(self.economy, n=3000), "S0").card_close
        self.assertEqual(set(np.unique(big).tolist()), set(range(DAYS)))
        self.assertLess(abs(big.mean() - 14.5), 0.5)
        np.testing.assert_array_equal(self.common.card_close, 29)
        np.testing.assert_array_equal(self.common.card_due, 20)

    def test_every_holders_cycle_is_thirty_days_and_due_21_days_after_it_closes(self):
        """Each person's statements close every 30 days on its own closing day and each falls due 21 days after
        it closes, with the minimum payment and late fee on that day only; due days are spread over the month."""
        w = self.own
        holders = np.flatnonzero(w.pop["holder"])
        closes = {i: [t for t, closing, _ in w.closed if closing[i]] for i in holders}
        dues = {i: [t for t, on, _ in w.due_on if on[i]] for i in holders}
        for i in holders:
            self.assertTrue(np.all(np.diff(closes[i]) == DAYS))
            self.assertTrue(all(t % DAYS == w.card_close[i] for t in closes[i]))
            self.assertTrue(np.all(np.diff(dues[i]) == DAYS))
            # Every statement that closed and fell due within the run was due 21 days after it closed.
            self.assertEqual([t for t in dues[i] if t - 21 >= 0], [t + 21 for t in closes[i] if t + 21 < w.total * DAYS])
        self.assertGreater(len(np.unique(w.card_due[holders])), 20)
        self.assertTrue(w.untouched)   # a due day leaves everyone not due on it as it was

    def test_every_purchase_falls_due_21_to_50_days_after_it_is_made(self):
        """Every card purchase is on the statement due on the holder's first due day at least 21 days after it, and
        that is never more than 50 days after it; the statements of each cycle sum to its card purchases."""
        w = self.own
        bought = np.array([amounts for _, amounts in w.bought])          # day x person
        days = np.array([t for t, _ in w.bought])
        waits, checked = [], 0
        for t_due, on, statement in w.due_on:
            for i in np.flatnonzero(on & w.pop["holder"]):
                t_close = t_due - 21
                cycle = (days > t_close - DAYS) & (days <= t_close)
                if t_close < 0:
                    self.assertEqual(statement[i], 0.0)
                    continue
                self.assertAlmostEqual(float(statement[i]), float(bought[cycle, i].sum()), places=12)
                made = days[cycle][bought[cycle, i] > 0]
                waits.extend((t_due - made).tolist())
                checked += int(bought[cycle, i].sum() > 0)
        self.assertGreater(checked, 50)
        self.assertGreaterEqual(min(waits), 21)
        self.assertLessEqual(max(waits), 50)
        self.assertEqual(set(range(21, 51)) - set(waits), set())

    def test_the_view_without_p_defers_each_cycle_to_its_due_day(self):
        """The card-eligible P payments of every cycle are deferred to its due day once each: what the replay's view
        without P deferred, with what is still unbilled or not yet due at the end, is every such payment of the run."""
        w = self.own
        self.assertGreater(w.internal_total, 0.0)
        left = float(w.s0_unbilled.sum() + w.s0_statement.sum())
        self.assertAlmostEqual(w.deferred_total + left, w.internal_total, places=10)

    def test_common_closes_on_day_29_and_is_due_on_day_20_only(self):
        """By default ("common") no statement closes inside a day, every statement falls due on day 20,
        and the statement due then is the card purchases of the last calendar month."""
        w = self.common
        self.assertEqual(Economy().statement_dates, "common")
        self.assertFalse(any(closing.any() for _, closing, _ in w.closed))
        self.assertTrue(all(t % DAYS == 20 for t, _, _ in w.due_on))
        bought = np.array([amounts for _, amounts in w.bought])
        days = np.array([t for t, _ in w.bought])
        for t_due, _, statement in w.due_on[1:]:
            last_month = (days // DAYS) == t_due // DAYS - 1
            np.testing.assert_allclose(statement, bought[last_month].sum(axis=0), rtol=1e-12, atol=1e-15)

    def test_money_is_conserved_with_own_dates(self):
        """With own statement dates, shocks and CPI on, the identity holds every month in every arm, and with
        random purchases too."""
        identity_holds(self, replace(TINY, n=100, shocks=True, statement_dates="own"))
        identity_holds(self, replace(TINY, n=100, purchases="poisson_size", statement_dates="own"))


if __name__ == "__main__":
    unittest.main()

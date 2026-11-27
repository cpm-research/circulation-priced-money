"""Tests for the four settings of the pool's cash and its order of collection, at tiny scale.

What is covered
---------------
* Reserved standby (``Economy.standby``): the four rows of the example table; with cash at or below the amount held
  no pool term loan is made while a bridge is still served; the pool without demurrage and the default are untouched.
* Two months of receipts (``Economy.receipts_window``): a person paid $2,000 every 60 days is expected to receive
  $2,000 over the next two months in both kinds of month, against $4,000 and $0 by default; steady monthly receipts are
  unchanged; the close keeps the month before last's receipts other than wages.
* Overdue wages ranked ahead of the pool (``Economy.collect_first``): the example.
* The pool without demurrage given the same capital target (``Economy.uncharged_target``): with identical cycle
  records the two targets are equal under "peak" and differ by default.
* The conservation identity every month in every arm with each new setting on.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import BRIDGE, DAYS, LATE_WAGE, MONTH_USD, SERVICE, TERM, Economy, _World
from tests.test_economy_abm import TINY, controlled_world, entry, funded_pool

SMALL = replace(TINY, n=60, burn_in=2, months=4)
SETTINGS = dict(standby="reserved", receipts_window=2, collect_first="wages", uncharged_target="peak")
# The settings beside them, each checked alone in the conservation test.
MATCHED = dict(collect_first="wages_same_budget", uncharged_standby="reserved")


def with_economy(w, **settings):
    """``w`` with its Economy's settings replaced (the world reads these four live)."""
    w.economy = replace(w.economy, **settings)
    return w


def pool_bridge(w, who, dollars, due=10_000):
    """A pool bridge of ``dollars`` carried by ``who``, due on day ``due``."""
    w._add_loans(np.array([who]), True, BRIDGE, np.array([dollars / MONTH_USD]), 0.0, 0.0, due)


class SettingsTest(unittest.TestCase):
    def test_the_defaults_are_as_built_and_a_misspelt_setting_is_refused(self):
        economy = Economy()
        self.assertEqual((economy.standby, economy.receipts_window, economy.collect_first, economy.uncharged_target),
                         ("measured", 1, "bridge", "mean"))
        for bad in (dict(standby="reserve"), dict(receipts_window=3), dict(receipts_window=True),
                    dict(collect_first="wage"), dict(uncharged_target="max")):
            with self.assertRaises(ValueError, msg=bad):
                Economy(**bad)


class ReservedStandbyTest(unittest.TestCase):
    """Reserved standby: term loans take only the cash above the standby held for bridges, in the arrangements with
    demurrage."""

    def world(self, arm, cash, peak, carried, standby="reserved"):
        """A ten-person pool holding ``cash`` dollars a person, a peak bridging need of ``peak`` a person and
        ``carried`` a person of pool bridging carried (all by person 0)."""
        w = with_economy(controlled_world(arm), standby=standby)
        funded_pool(w, cash * w.n / MONTH_USD)
        w.peak = peak * w.n / MONTH_USD
        if carried:
            pool_bridge(w, 0, carried * w.n)
        return w

    def test_the_hand_case_table(self):
        # Cash for loans, peak need, bridges carried -> held for bridges, open to long loans (dollars a person).
        rows = ((300, 240, 80, 160, 140), (160, 240, 80, 160, 0), (150, 240, 80, 150, 0), (400, 240, 240, 0, 400))
        for cash, peak, carried, held, open_ in rows:
            for arm in ("M1", "M2"):
                w = self.world(arm, cash, peak, carried)
                per = lambda value: value * MONTH_USD / w.n
                self.assertAlmostEqual(per(w._cash_for_loans()), cash, places=9)       # bridges keep all of it
                self.assertAlmostEqual(per(w._standby_held()), held, places=9, msg=(arm, cash))
                self.assertAlmostEqual(per(w._cash_for_term()), open_, places=9, msg=(arm, cash))
                built = self.world(arm, cash, peak, carried, standby="measured")
                self.assertEqual((built._standby_held(), built._cash_for_term()), (0.0, built._cash_for_loans()))
            # The pool without demurrage holds nothing back.
            u = self.world("U", cash, peak, carried)
            self.assertEqual((u._standby_held(), u._cash_for_term()), (0.0, u._cash_for_loans()))
            # Under uncharged_standby "reserved" it holds back the same cash as the pool with it.
            u = with_economy(self.world("U", cash, peak, carried), uncharged_standby="reserved")
            self.assertAlmostEqual(per(u._standby_held()), held, places=9, msg=("U", cash))
            self.assertAlmostEqual(per(u._cash_for_term()), open_, places=9, msg=("U", cash))

    def test_no_term_loan_at_or_below_the_amount_held_while_a_bridge_is_served(self):
        for cash in (160, 150):
            w = self.world("M1", cash, 240, 80)
            w.r_term = w.r_term_business = 0.0
            w.r_g = w.r_b = 0.005
            w.spending[0] = 1.0
            w.req = dict(buyer=np.array([0]), seller=np.array([1]), price=np.array([1.0]), settle=np.array([30]),
                         product=np.array([0]), rate=np.array([0.01]), months=np.array([60]))
            w._term_purchases(30)
            bk = w.book
            self.assertEqual(float(bk["principal"][bk["pool"] & (bk["kind"] == TERM)].sum()), 0.0)
            self.assertGreater(float(bk["principal"][~bk["pool"] & (bk["kind"] == TERM)].sum()), 0.0)  # lent outside
            self.assertAlmostEqual(w.acc["refused_term"], 1.0, places=12)   # it enters the term lending need
            # A bill person 3 cannot pay is still bridged by the pool, from the cash for loans.
            w.last["receipts"][:], w.last["wages_paid"][:] = 1.0, 0.0
            w.ob = dict(buyer=np.array([3]), seller=np.array([4]), amount=np.array([0.1]), settle=np.array([30]),
                        card=np.array([False]), kind=np.array([SERVICE]))
            w.receivable[4] = w.payable[3] = 0.1
            before = float(bk["principal"][bk["pool"] & (bk["kind"] == BRIDGE)].sum())
            w._settle(1, 30)
            bk = w.book
            self.assertGreater(float(bk["principal"][bk["pool"] & (bk["kind"] == BRIDGE)].sum()), before)
        # The same request, by default, is lent by the pool.
        w = self.world("M1", 160, 240, 80, standby="measured")
        w.r_term = w.r_term_business = 0.0
        w.spending[0] = 1.0
        w.req = dict(buyer=np.array([0]), seller=np.array([1]), price=np.array([1.0]), settle=np.array([30]),
                     product=np.array([0]), rate=np.array([0.01]), months=np.array([60]))
        w._term_purchases(30)
        self.assertGreater(float(w.book["principal"][w.book["pool"] & (w.book["kind"] == TERM)].sum()), 0.0)

    def test_the_pool_without_demurrage_reproduces_its_run_and_the_record_is_kept(self):
        built = _World(Inputs(), 0.6, SMALL, "U").run()["series"]
        reserved = _World(Inputs(), 0.6, replace(SMALL, standby="reserved"), "U").run()["series"]
        self.assertEqual(set(reserved) - set(built), {"standby_held"})
        for key in built:
            np.testing.assert_array_equal(reserved[key], built[key], err_msg=key)
        self.assertTrue(np.all(reserved["standby_held"] == 0.0))
        # With uncharged_standby "reserved" the record is kept in U too, never below zero.
        held = _World(Inputs(), 0.6, replace(SMALL, standby="reserved", uncharged_standby="reserved"), "U").run()
        self.assertTrue(np.all(held["series"]["standby_held"] >= 0.0))
        with self.assertRaises(ValueError):
            Economy(uncharged_standby="reserved")   # needs reserved standby
        with self.assertRaises(ValueError):
            Economy(standby="reserved", uncharged_standby="held")
        # In M1 the record is live and never above the cash held ready.
        m1 = _World(Inputs(), 0.6, replace(SMALL, standby="reserved"), "M1").run()["series"]
        self.assertNotIn("standby_held", _World(Inputs(), 0.6, SMALL, "M1").run()["series"])
        self.assertTrue(np.all(m1["standby_held"] >= 0.0))
        self.assertGreater(float(np.max(m1["standby_held"])), 0.0)


class ReceiptsWindowTest(unittest.TestCase):
    """Two months of receipts: the receipts other than wages are the mean of the last two completed months."""

    def world(self, cycle, last, before):
        """Person 0 bills every ``cycle`` days (next date day 45) with ``last`` dollars of receipts last month and
        ``before`` the month before, none of them wages; ``before`` None reads as the default."""
        w = controlled_world()
        w.pop["cycles"][0], w.pop["phases"][0] = cycle, 45 % cycle
        w.last["wages_paid"][:], w.last["receipts"][:] = 0.0, 0.0
        w.last["receipts"][0] = last / MONTH_USD
        if before is not None:
            w.other_before = np.zeros(w.n)
            w.other_before[0] = before / MONTH_USD
        return w

    def expected(self, w, t=30):
        """The receipts the budget expects person 0 to get over the next two months, dollars."""
        return float(w._receipts_side(t)[0][0]) * MONTH_USD

    def test_the_sixty_day_biller(self):
        # By default: $4,000 the month after a receipt, $0 the month after none.
        self.assertAlmostEqual(self.expected(self.world(60, 2000.0, None)), 4000.0, places=6)
        self.assertAlmostEqual(self.expected(self.world(60, 0.0, None)), 0.0, places=6)
        # Two months: $2,000 in both kinds of month.
        self.assertAlmostEqual(self.expected(self.world(60, 2000.0, 0.0)), 2000.0, places=6)
        self.assertAlmostEqual(self.expected(self.world(60, 0.0, 2000.0)), 2000.0, places=6)

    def test_steady_monthly_receipts_are_unchanged(self):
        built = self.expected(self.world(30, 1000.0, None))
        self.assertAlmostEqual(built, 2000.0, places=6)
        self.assertEqual(self.expected(self.world(30, 1000.0, 1000.0)), built)

    def test_the_close_keeps_the_month_before_last(self):
        w = _World(Inputs(), 0.6, replace(SMALL, months=2, receipts_window=2), "M1")
        for month in range(w.total):
            before = w._other_receipts()          # the month just completed, before this one runs
            w.month(month)
            if month == 0:
                self.assertIsNone(w.other_before)   # the first close has no completed month before it
            else:
                np.testing.assert_array_equal(w.other_before, before)
        self.assertIsNone(_World(Inputs(), 0.6, SMALL, "M1").other_before)   # by default nothing is kept


class CollectFirstTest(unittest.TestCase):
    """Wages collected first: overdue wages paid from all the borrower's money before the due bridge."""

    def world(self, collect_first):
        """Person 0 holds $400 with a buffer of $300, a pool bridge of $250 due yesterday and an overdue wage of
        $200 to person 1."""
        w = with_economy(controlled_world(), collect_first=collect_first)
        funded_pool(w)
        w.pcash[0], w.buffer[0] = 400.0 / MONTH_USD, 300.0 / MONTH_USD
        pool_bridge(w, 0, 250.0, due=29)
        wage = 200.0 / MONTH_USD
        w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([wage]), settle=np.array([20]),
                    card=np.array([False]), kind=np.array([LATE_WAGE]))
        w.payable[0] = w.receivable[1] = wage
        w._end_of_day_collection(30)
        bridge = float(w.book["principal"][0] + w.book["interest"][0]) * MONTH_USD
        wage_left = float(w.ob["amount"].sum()) * MONTH_USD if w.ob["amount"].size else 0.0
        return 250.0 - bridge, 200.0 - wage_left, bridge, wage_left

    def test_the_hand_case(self):
        paid_bridge, paid_wage, bridge_left, wage_left = self.world("bridge")
        self.assertAlmostEqual(paid_bridge, 250.0, places=9)
        self.assertAlmostEqual(paid_wage, 0.0, places=9)          # the 150 left is below the buffer
        self.assertAlmostEqual(wage_left, 200.0, places=9)
        paid_bridge, paid_wage, bridge_left, wage_left = self.world("wages")
        self.assertAlmostEqual(paid_wage, 200.0, places=9)
        self.assertAlmostEqual(paid_bridge, 200.0, places=9)
        self.assertAlmostEqual(bridge_left, 50.0, places=9)        # past due, so no new pool credit until it clears
        # Wages first on their own budget: the wage takes the $100 above the buffer, then the
        # bridge is collected in full from the $300 left.
        paid_bridge, paid_wage, bridge_left, wage_left = self.world("wages_same_budget")
        self.assertAlmostEqual(paid_wage, 100.0, places=9)
        self.assertAlmostEqual(wage_left, 100.0, places=9)
        self.assertAlmostEqual(paid_bridge, 250.0, places=9)
        self.assertAlmostEqual(bridge_left, 0.0, places=9)


class UnchargedTargetTest(unittest.TestCase):
    """The peak target without demurrage: the pool without demurrage given the capital target of the pool with it."""

    def target(self, arm, uncharged_target):
        """The capital target a person from one cycle of identical records: a term lending need of 1,400, a mean
        lending need of 1,500 and a peak bridging need of 240, dollars a person."""
        w = with_economy(controlled_world(arm), uncharged_target=uncharged_target)
        bridging = np.zeros(DAYS)
        bridging[10] = 240.0 * w.n / MONTH_USD
        cycle = [entry(need=1500.0 * w.n / MONTH_USD, need_term=1400.0 * w.n / MONTH_USD, bridging=bridging)] * 2
        w.peak, _ = w._kept_ready(cycle)
        w._limit(cycle)
        return w.need * MONTH_USD / w.n

    def test_the_targets_are_equal_under_peak_and_differ_as_built(self):
        self.assertAlmostEqual(self.target("M1", "mean"), 1640.0, places=9)
        self.assertAlmostEqual(self.target("U", "mean"), 1500.0, places=9)
        self.assertAlmostEqual(self.target("U", "peak"), self.target("M1", "peak"), places=12)
        self.assertAlmostEqual(self.target("M1", "peak"), 1640.0, places=9)   # the pool with demurrage is unchanged


class ConservationTest(unittest.TestCase):
    def test_the_identity_holds_every_month_in_every_arm_with_each_setting_on(self):
        for name, value in [*SETTINGS.items(), *MATCHED.items(), ("all", None)]:
            # uncharged_standby is read only with reserved standby, so it runs with it.
            alone = dict(standby="reserved", uncharged_standby=value) if name == "uncharged_standby" else {name: value}
            economy = replace(SMALL, **(SETTINGS if value is None else alone))
            for arm in ("S0", "M0", "M1", "M2", "U"):
                series = _World(Inputs(), 0.6, economy, arm).run()["series"]
                np.testing.assert_allclose(series["wealth_change"],
                                           series["external"] + series["valuation"] + series["inflation"],
                                           atol=1e-12, err_msg=f"{name} {arm}")


if __name__ == "__main__":
    unittest.main()

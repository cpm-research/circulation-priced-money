"""Tests for the settings that change one rule each, every one at the first run's rule by default, at small scale.

What is covered
---------------
* ``experience_rewards``: the rewards a participant gives up on card-eligible purchases paid from its wallet are
  charged to its experience; the example; the default changes no number and adds no record.
* ``card_cut_on``: the stress line cut takes the tier's share of the room above the starting balance instead of the
  whole line; the example; restoration returns the line as before.
* ``screen_card_owed``: the covering budget counts the closed statement and the unbilled card purchases; where the
  statement itself is refinanced only the unbilled purchases; the example.
* ``buffer_reserve``: the buffer replay's savings a saver offering to the pool can draw, the deposit share of what is
  above each candidate buffer; the example.
* ``stress_paydays``: the worker's wage and the wage owed outside for one job and pay date count as one obligation;
  the example.
* Every default is the first run's rule and a misspelt value is refused; the conservation identity holds every month in
  every arrangement with each setting on.
"""
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import BRIDGE, MONTH_USD, OUTSIDE_WAGE, SERVICE, WAGE, Economy, _World
from cpm_abm.engine.lending_rules import savings_above
from cpm_abm.engine.world_close import CloseMixin
from cpm_abm.engine.world_month import MonthMixin
from tests.test_economy_abm import TINY, controlled_world, funded_pool

SMALL = replace(TINY, n=60, burn_in=2, months=4)
# Each setting of this module at its value away from the default (the line cut on, from month 1 after launch, for
# card_cut_on).
SETTINGS = dict(experience_rewards=True, card_cut_on="room", screen_card_owed=True,
                buffer_reserve="share_of_spare", stress_paydays="merged")
STRESS = dict(card_line_cut=True, card_cut_months=2, distress=0.02, distress_start=1, distress_length=2)


def identical(a, b):
    """Bit for bit: arrays by dtype, shape and bytes, dicts and lists of them item by item, anything else by value."""
    if isinstance(a, dict):
        return list(a) == list(b) and all(identical(a[key], b[key]) for key in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(map(identical, a, b))
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a), np.asarray(b)
        return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    return a == b or (a != a and b != b)


class DefaultsTest(unittest.TestCase):
    def test_the_defaults_are_as_built_and_a_misspelt_value_is_refused(self):
        self.assertFalse(Economy().experience_rewards)
        for bad in (dict(experience_rewards="yes"),):
            with self.assertRaises(ValueError, msg=bad):
                Economy(**bad)


class ExperienceRewardsTest(unittest.TestCase):
    def test_the_hand_case(self):
        """A $1,000 card purchase paid from the wallet gives up $7.50 of rewards."""
        world = SimpleNamespace(acc=dict(card_internal=np.array([1000.0, 0.0])))
        np.testing.assert_allclose(CloseMixin._forgone_rewards(world), [-7.5, 0.0], rtol=1e-15)

    def test_a_small_world(self):
        built = _World(Inputs(), 0.6, SMALL, "M1").run()["series"]
        charged = _World(Inputs(), 0.6, replace(SMALL, experience_rewards=True), "M1").run()["series"]
        self.assertNotIn("exp_rewards", built)
        self.assertEqual(set(charged) - set(built), {"exp_rewards"})
        rewards = charged["exp_rewards"][SMALL.burn_in:]
        self.assertTrue(np.all(rewards <= 0.0))
        self.assertLess(float(rewards.sum()), 0.0)
        # The experience of the launch month, before anyone has left on it, is lower by the rewards given up.
        launch = SMALL.burn_in
        self.assertLess(charged["experience"][launch], built["experience"][launch])
        # The bank arrangement has no participants: nothing changes.
        s0 = _World(Inputs(), 0.6, SMALL, "S0").run()
        s0_charged = _World(Inputs(), 0.6, replace(SMALL, experience_rewards=True), "S0").run()
        self.assertTrue(identical(s0["wealth"], s0_charged["wealth"]))


class CardCutOnTest(unittest.TestCase):
    def lines(self, cut_on):
        """A deep subprime holder with a $1,000 line and a $950 starting balance, and a holder of the top tier with a
        $1,000 line and none, through a cut at 2 points in month 0 restored five months later: the lines in dollars
        after the cut and after the restoration."""
        economy = Economy(burn_in=0, distress_start=0, distress=0.02, card_line_cut=True, card_cut_months=5,
                          card_cut_on=cut_on)
        world = SimpleNamespace(economy=economy, card_line=np.array([1000.0, 1000.0]),
                                card_start=np.array([950.0, 0.0]), card_tier=np.array([0, 5]),
                                holder=np.array([True, True]))
        MonthMixin._cut_lines(world, 0)
        cut = world.card_line.copy()
        MonthMixin._cut_lines(world, 5)
        return cut, world.card_line

    def test_the_hand_case_and_the_restoration(self):
        cut, back = self.lines("line")
        np.testing.assert_allclose(cut, [674.2, 1000.0 * (1 - 0.6 * 0.267)], rtol=1e-12)
        np.testing.assert_array_equal(back, [1000.0, 1000.0])
        cut, back = self.lines("room")
        np.testing.assert_allclose(cut, [983.71, 1000.0 * (1 - 0.6 * 0.267)], rtol=1e-12)   # $33.71 of room
        np.testing.assert_array_equal(back, [1000.0, 1000.0])

    def test_the_lines_cut_as_built_are_unchanged_by_the_default(self):
        self.assertEqual(Economy().card_cut_on, "line")
        with self.assertRaises(ValueError):
            Economy(card_cut_on="balance")


class ScreenCardOwedTest(unittest.TestCase):
    def budget(self, screen, statement=False, unbilled=0.0):
        """Person 0 of the controlled world expects some receipts over the horizon, owes nothing on the book and owes a
        statement equal to those receipts, plus ``unbilled`` of them in card purchases not yet billed: its receipts
        and its spare, in units of its receipts."""
        w = controlled_world()
        w.economy = replace(w.economy, screen_card_owed=screen)
        w.last["receipts"][:], w.last["wages_paid"][:] = 0.0, 0.0
        w.last["receipts"][0] = 100.0 / MONTH_USD
        expected = float(w._c1_budget(30)[0][0])
        self.assertGreater(expected, 0.0)
        w.holder[0] = True
        w.card_statement[0], w.card_unbilled[0] = expected, unbilled * expected
        spare = w._c1_budget(30, statement=statement)[1][0]
        return float(spare) / expected

    def test_the_hand_case(self):
        self.assertEqual(self.budget(False), 1.0)                       # by default the statement is not seen
        self.assertEqual(self.budget(True), 0.0)                        # under the setting nothing is spare
        self.assertAlmostEqual(self.budget(True, statement=True), 1.0, places=12)   # the statement refinanced itself
        self.assertAlmostEqual(self.budget(True, statement=True, unbilled=0.25), 0.75, places=12)
        self.assertEqual(self.budget(False, statement=True, unbilled=0.25), 1.0)

    def test_the_due_date_reads_the_same_card_bill(self):
        """A $60 statement owed before the first of two $100 receipts, on days 40 and 70: the screen leaves $140 over
        both and admits a $70 bridge, which falls due on day 40 by default, when only $40 of that receipt is free, and
        on day 70 under the setting. Refinancing the statement itself, only unbilled purchases count."""
        dues = {}
        for screen in (False, True):
            w = controlled_world()
            w.economy = replace(w.economy, screen_card_owed=screen)
            w.pop["cycles"][0], w.pop["phases"][0] = 30, 10
            w.last["receipts"][:], w.last["wages_paid"][:] = 0.0, 0.0
            w.last["receipts"][0] = 100.0 / MONTH_USD
            w.holder[0] = True
            w.card_statement[0] = 60.0 / MONTH_USD
            expected, spare = (float(x[0]) * MONTH_USD for x in w._c1_budget(30)[:2])
            self.assertAlmostEqual(expected, 200.0, places=9)
            self.assertAlmostEqual(spare, 140.0 if screen else 200.0, places=9)
            bridge = np.array([70.0 / MONTH_USD])
            dues[screen] = (int(w._due_c1(np.array([0]), bridge, 30)[0]),
                            int(w._due_c1(np.array([0]), bridge, 30, statement=True)[0]))
        self.assertEqual(dues[False], (40, 40))
        self.assertEqual(dues[True], (70, 40))

    def bridge_with_a_card_purchase(self, screen, receipts):
        """Through the real settlement: a holder with no money expects ``receipts`` dollars over the horizon, puts a $60
        purchase on its card today (its line takes exactly that) and owes a $70 bill it can only bridge. Returns the
        pool bridge drawn and its due date."""
        w = controlled_world()
        funded_pool(w)
        w.economy = replace(w.economy, screen_card_owed=screen)
        w.pop["cycles"][0], w.pop["phases"][0] = 30, 10
        w.last["receipts"][:], w.last["wages_paid"][:] = 0.0, 0.0
        w.last["receipts"][0] = receipts / 2 / MONTH_USD   # two receipt dates in the horizon, days 40 and 70
        w.holder[0] = True
        w.card_line[0] = 60.0 / MONTH_USD
        amounts = np.array([60.0, 70.0]) / MONTH_USD
        w.ob = dict(buyer=np.array([0, 0]), seller=np.array([1, 2]), amount=amounts, settle=np.array([30, 30]),
                    card=np.array([True, False]), kind=np.array([SERVICE, SERVICE]))
        w.payable[0] = amounts.sum()
        w.receivable[1], w.receivable[2] = amounts
        w._settle(1, 30)
        bk = w.book
        drawn = bk["pool"] & (bk["borrower"] == 0) & (bk["kind"] == BRIDGE)
        return float(bk["principal"][drawn].sum()) * MONTH_USD, bk["due"][drawn].tolist()

    def test_todays_card_purchases_are_owed_in_the_screen(self):
        """$100 expected and a $60 card purchase today: with the setting off the $70 bridge passes and falls due on the
        last date, uncovered; counting the purchase leaves $40, so the bridge is cut to what $40 repays after the
        failure fee on the rest ($20.91). With $200 expected the purchase leaves enough and the bridge is the same
        either way."""
        built, built_due = self.bridge_with_a_card_purchase(False, 100.0)
        counted, counted_due = self.bridge_with_a_card_purchase(True, 100.0)
        self.assertAlmostEqual(built, 70.0, places=6)
        self.assertAlmostEqual(counted, 20.91, places=2)
        self.assertEqual(counted_due, [70])
        # With $200 expected the bridge is $70 either way; counting the card, it falls due on day 70, when the
        # receipts cover the purchase and the bridge, not on day 40.
        enough = [self.bridge_with_a_card_purchase(screen, 200.0) for screen in (False, True)]
        self.assertEqual((enough[0][0], enough[1][0]), (70.0, 70.0))
        self.assertEqual((enough[0][1], enough[1][1]), ([40], [70]))

    def test_the_statement_refinanced_is_not_counted_against_itself(self):
        """Through the real statement: a $250 statement, no money, and $100 expected on each of days 55, 70, 85 and
        100. The pool pays the statement, as its own amount is not counted among what is owed, and the draw falls due
        on day 85, the first date whose receipts repay it; counted twice it would be refused, or due on day 100."""
        w = controlled_world()
        funded_pool(w)
        w.economy = replace(w.economy, screen_card_owed=True)
        w.pop["cycles"][0], w.pop["phases"][0] = 15, 10
        w.last["receipts"][:], w.last["wages_paid"][:] = 0.0, 0.0
        w.last["receipts"][0] = 200.0 / MONTH_USD
        w.holder[0] = True
        w.card_statement[0] = 250.0 / MONTH_USD
        w._statement(20, 50)
        bk = w.book
        drawn = bk["pool"] & (bk["borrower"] == 0) & (bk["kind"] == BRIDGE)
        self.assertAlmostEqual(float(bk["principal"][drawn].sum()) * MONTH_USD, 250.0, places=6)
        self.assertEqual(bk["due"][drawn].tolist(), [85])

    def test_the_default_and_a_misspelt_value(self):
        self.assertFalse(Economy().screen_card_owed)
        with self.assertRaises(ValueError):
            Economy(screen_card_owed=1)


class BufferReserveTest(unittest.TestCase):
    def test_the_hand_case(self):
        """$100 of money, a money-market share of 50% and a candidate of $40: a saver offering to the pool may draw
        $10 above it by default (its drawable $50 less $40) and $30 under the setting (half of the $60 above it); a
        saver offering nothing draws all $60 under both."""
        candidates, wealth = np.array([[40.0], [40.0]]), np.array([100.0, 100.0])
        offers = np.array([True, False])
        drawable = np.where(offers, 50.0, 100.0)
        np.testing.assert_allclose(savings_above(candidates, wealth, drawable)[:, 0], [10.0, 60.0])
        share = np.where(offers, 0.5, 1.0)
        np.testing.assert_allclose(savings_above(candidates, wealth, drawable, share)[:, 0], [30.0, 60.0])

    def test_a_small_world(self):
        built = _World(Inputs(), 0.6, SMALL, "M1").run()
        spare = _World(Inputs(), 0.6, replace(SMALL, buffer_reserve="share_of_spare"), "M1").run()
        # Before launch nobody offers to a pool, so the buffers are the same; after it they may differ.
        launch = SMALL.burn_in
        self.assertTrue(identical(built["buffers"][:launch], spare["buffers"][:launch]))
    def test_the_default_and_a_misspelt_value(self):
        self.assertEqual(Economy().buffer_reserve, "share_of_liquid")
        with self.assertRaises(ValueError):
            Economy(buffer_reserve="share")


class StressPaydaysTest(unittest.TestCase):
    def payday(self, reading):
        """Person 0 holds $50, no card, no pool and no savings, and its job's $100 payday is split: $60 to its worker,
        person 1, and $40 owed outside. Returns its failed shares, its fee in dollars and what person 1 received."""
        w = controlled_world()
        w.economy = replace(w.economy, stress_paydays=reading)
        w.cash[0] = 50.0 / MONTH_USD
        amounts = np.array([60.0, 40.0]) / MONTH_USD
        w.ob = dict(buyer=np.array([0, 0]), seller=np.array([1, 1]), amount=amounts, settle=np.array([30, 30]),
                    card=np.array([False, False]), kind=np.array([WAGE, OUTSIDE_WAGE]))
        w.payable[0], w.receivable[1] = amounts.sum(), amounts[0]
        before = {key: w.acc[key].copy() for key in ("fail_shares", "fee", "receipts")}
        w._settle(1, 30)
        change = {key: w.acc[key] - before[key] for key in before}
        return (float(change["fail_shares"][0]), float(change["fee"][0]) * MONTH_USD,
                float(change["receipts"][1]) * MONTH_USD)

    def test_the_hand_case(self):
        shares, fee, received = self.payday("split")
        self.assertAlmostEqual(shares, 1.0, places=12)
        self.assertAlmostEqual(fee, 27.0, places=9)
        merged_shares, merged_fee, merged_received = self.payday("merged")
        self.assertAlmostEqual(merged_shares, 0.5, places=12)
        self.assertAlmostEqual(merged_fee, 13.5, places=9)
        self.assertEqual(merged_received, received)   # the money goes where it went
        self.assertAlmostEqual(received, 30.0, places=9)

    @staticmethod
    def rows(reading, rows):
        """$50 of money and a $100 payday of one job in ``rows`` (dollars, kind), all due today: the payer's failed
        shares, fee in dollars, whole items returned and fee units, through the real settlement."""
        w = controlled_world()
        w.economy = replace(w.economy, stress_paydays=reading)
        w.cash[0] = 50.0 / MONTH_USD
        amounts = np.array([a for a, _ in rows]) / MONTH_USD
        kinds = np.array([k for _, k in rows])
        k = len(rows)
        w.ob = dict(buyer=np.zeros(k, int), seller=np.ones(k, int), amount=amounts, settle=np.full(k, 30),
                    card=np.zeros(k, bool), kind=kinds)
        w.payable[0], w.receivable[1] = amounts.sum(), amounts[kinds == WAGE].sum()
        keys = ("fail_shares", "fee", "fail_items", "fee_units")
        before = {key: w.acc[key].copy() for key in keys}
        w._settle(1, 30)
        out = [float((w.acc[key] - before[key])[0]) for key in keys]
        out[1] *= MONTH_USD
        return out

    def test_every_payday_is_one_obligation(self):
        """Worker and outside rows of $60 and $40, two worker rows of $50, two outside rows of $50, and $40 and $60:
        each gives failed shares 0.5, a fee of $13.50 and the whole items one $100 row gives; by default each split
        payday counts twice."""
        one = self.rows("merged", [(100.0, WAGE)])
        np.testing.assert_allclose(one, [0.5, 13.5, 1.0, 0.5], atol=1e-9)
        self.assertEqual(self.rows("split", [(100.0, WAGE)]), one)
        for split in ([(60.0, WAGE), (40.0, OUTSIDE_WAGE)], [(50.0, WAGE), (50.0, WAGE)],
                      [(50.0, OUTSIDE_WAGE), (50.0, OUTSIDE_WAGE)], [(40.0, WAGE), (60.0, OUTSIDE_WAGE)]):
            np.testing.assert_allclose(self.rows("merged", split), one, atol=1e-9, err_msg=str(split))
            built = self.rows("split", split)
            np.testing.assert_allclose(built[:2], [1.0, 27.0], atol=1e-9, err_msg=str(split))

    def test_the_default_and_a_misspelt_value(self):
        self.assertEqual(Economy().stress_paydays, "split")
        with self.assertRaises(ValueError):
            Economy(stress_paydays="one")


class SettleCycleTest(unittest.TestCase):
    """A day whose settlement does not reach a fixed point (``Economy.settle_cycle``)."""

    def test_the_default_and_a_misspelt_value(self):
        self.assertEqual(Economy().settle_cycle, "raise")
        with self.assertRaises(ValueError):
            Economy(settle_cycle="settle")

    def toggling_day(self, mode):
        """Person 0 holds nothing and owes person 1 $100 today; the pool can lend it all. The pool's screen is made to
        alternate, by sweep, between lending the whole shortfall and lending next to nothing (an amount above zero, so
        nothing is deferred): the request toggles as in the cycles found in real runs, where a payer's own receipts
        arrive once it is paid and it stops asking."""
        w = controlled_world()
        funded_pool(w)
        w.economy = replace(w.economy, settle_cycle=mode, sweeps=200)
        w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([100.0 / MONTH_USD]),
                    settle=np.array([30]), card=np.array([False]), kind=np.array([SERVICE]))
        w.payable[0] = w.receivable[1] = 100.0 / MONTH_USD
        calls = []

        def screen(short, *rest):
            calls.append(1)
            return short if len(calls) % 2 else np.minimum(short, 1e-10)

        received = w.acc["receipts"][1]
        with mock.patch("cpm_abm.engine.world_day.limit_with_fee", screen):
            w._settle(1, 30)
        return w, (w.acc["receipts"][1] - received) * MONTH_USD

    def test_a_toggling_request_raises_as_built_and_is_held_under_hold(self):
        with self.assertRaises(RuntimeError):
            self.toggling_day("raise")
        w, received = self.toggling_day("hold")
        bk = w.book
        bridge = bk["pool"] & (bk["kind"] == BRIDGE) & (bk["borrower"] == 0)
        self.assertAlmostEqual(float(bk["principal"][bridge].sum()) * MONTH_USD, 100.0, places=6)
        self.assertAlmostEqual(float(received), 100.0, places=6)   # the bill is paid in full
        self.assertEqual(w.acc["settle_held"], 1)

    def test_every_day_that_settles_as_built_is_unchanged(self):
        for arm in ("S0", "M0", "U", "M1", "M2"):
            economy = replace(SMALL, **STRESS)
            built = _World(Inputs(), 0.6, economy, arm).run()
            held = _World(Inputs(), 0.6, replace(economy, settle_cycle="hold"), arm).run()
            for key in built:
                if key != "economy":
                    self.assertTrue(identical(built[key], held[key]), (arm, key))
            self.assertTrue(np.all(held["series"]["settle_held"] == 0))


class ConservationTest(unittest.TestCase):
    def test_the_identity_holds_every_month_in_every_arm_with_each_setting_on(self):
        for name, value in [*SETTINGS.items(), ("all", None)]:
            economy = replace(SMALL, **STRESS, **(SETTINGS if value is None else {name: value}))
            for arm in ("S0", "M0", "M1", "M2", "U"):
                series = _World(Inputs(), 0.6, economy, arm).run()["series"]
                np.testing.assert_allclose(series["wealth_change"],
                                           series["external"] + series["valuation"] + series["inflation"],
                                           atol=1e-12, err_msg=f"{name} {arm}")


if __name__ == "__main__":
    unittest.main()

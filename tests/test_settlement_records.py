"""Tests for the settlement's two records (the robustness plan, section 4), at tiny scale.

What is covered
---------------
* Own shortfall and knock-on, same day (``shortfall_split``): the plan's hand case on the arithmetic and through the
  settlement itself.
* Dependence on netting (``netting_set``, ``netting_loss``): the plan's hand case, the same pair when one of them holds
  money, and the pair when one of them is paid by an outsider with money, on the arithmetic and through the
  settlement.
* Every arm stores the new monthly series, finite, and own shortfall plus signed knock-on is the month's failures.

Neither record is read by a rule; that every other record is unchanged bit for bit is checked outside the suite, on a
small economy in every arm, against the commit before them.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import SERVICE, simulate
from cpm_abm.engine.constants import CENT
from cpm_abm.engine.measures import (CHAIN_SERIES, KNOCK_ON_BINS, netting_loss, netting_set, shortfall_split)
from tests.test_economy_abm import TINY, controlled_world

RECORDS = ("own_shortfall", "knock_on", "knock_on_positive", "own_shortfall_n", "knock_on_n", "cash_completed",
           "netting_days", "netting_n", "netting_value", "netting_lost")


def payments(w, buyer, seller, amount):
    """Today's service bills (day 30), none card-eligible, with their receivables and payables."""
    w.ob = dict(buyer=np.array(buyer), seller=np.array(seller), amount=np.array(amount, float),
                settle=np.full(len(buyer), 30), card=np.zeros(len(buyer), bool), kind=np.full(len(buyer), SERVICE))
    np.add.at(w.receivable, w.ob["seller"], w.ob["amount"])
    np.add.at(w.payable, w.ob["buyer"], w.ob["amount"])


def settled(w):
    """Settle day 30 and return what it added to the two records and to the month's failures."""
    before = {key: float(w.acc[key]) for key in RECORDS}
    days, failed = w.acc["knock_on_days"].copy(), float(w.acc["failed_new"].sum())
    w._settle(1, 30)
    added = {key: float(w.acc[key]) - before[key] for key in RECORDS}
    added.update(knock_on_days=w.acc["knock_on_days"] - days, failed=float(w.acc["failed_new"].sum()) - failed)
    return added


class ShortfallSplitTests(unittest.TestCase):

    def test_the_plans_hand_case_on_the_arithmetic(self):
        """A fails 10 on its own; B fails nothing with full receipts and 6 in the solution: failed 16, own shortfall
        10, knock-on 6, one payer with a knock-on failure."""
        split = shortfall_split(np.array([10.0, 6.0, 0.0]), np.array([10.0, 0.0, 0.0]))
        self.assertEqual(split, dict(own=10.0, knock_on=6.0, knock_on_positive=6.0, own_n=1, knock_on_n=1, bin=1))

    def test_a_negative_knock_on_part_is_kept_in_the_signed_sum_only(self):
        """With pool rationing a payer can fail less than on its own; the bins are 0, 1, 2 to 3, ... 32 or more."""
        split = shortfall_split(np.array([1.0, 3.0]), np.array([1.5, 1.0]))
        self.assertEqual((split["knock_on"], split["knock_on_positive"], split["knock_on_n"]), (1.5, 2.0, 1))
        bins = [shortfall_split(np.ones(k), np.zeros(k))["bin"] for k in (0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 99)]
        self.assertEqual(bins, [0, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6])
        self.assertEqual(len(KNOCK_ON_BINS), 7)

    def test_the_plans_hand_case_through_the_settlement(self):
        """A (0) holds nothing and owes B (1) 10; B holds 4 and owes C (2) 10. The day records own shortfall 10,
        knock-on 6 and one payer with a knock-on failure, and the two parts add up to the month's failures."""
        w = controlled_world("S0")
        w.cash[1] = 4.0
        payments(w, [0, 1], [1, 2], [10.0, 10.0])
        added = settled(w)
        self.assertAlmostEqual(added["failed"], 16.0, places=12)
        self.assertAlmostEqual(added["own_shortfall"], 10.0, places=12)
        self.assertAlmostEqual(added["knock_on"], 6.0, places=12)
        self.assertAlmostEqual(added["knock_on_positive"], 6.0, places=12)
        self.assertEqual((added["own_shortfall_n"], added["knock_on_n"]), (1.0, 1.0))
        np.testing.assert_array_equal(added["knock_on_days"], [0, 1, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(added["cash_completed"], 4.0, places=12)
        self.assertEqual(added["netting_days"], 0.0)


class NettingTests(unittest.TestCase):

    def test_the_plans_hand_case_on_the_arithmetic(self):
        """A and B hold nothing and owe each other 10, and both pay: the set is {A, B}; held at zero both stay at
        zero, and the value lost is 20."""
        b, s, paid = np.array([0, 1]), np.array([1, 0]), np.array([10.0, 10.0])
        inside = netting_set(np.array([True, True]), b, s, paid)
        np.testing.assert_array_equal(inside, [True, True])
        receipts = lambda f: np.bincount(s, weights=paid * f[b], minlength=2)
        lost, share = netting_loss(np.ones(2), inside, np.zeros(2), np.full(2, 10.0), receipts, np.full(2, 10.0))
        self.assertEqual(lost, 20.0)
        np.testing.assert_array_equal(share, [0.0, 0.0])

    def test_a_pair_paid_from_outside_is_no_netting_set(self):
        """If A holds 1 it is no candidate, and B, paid by A, leaves too. If a third payer with money pays A, A leaves
        and then B, paid by A, leaves: the set is empty either way."""
        inside = netting_set(np.array([False, True]), np.array([0, 1]), np.array([1, 0]), np.array([10.0, 10.0]))
        np.testing.assert_array_equal(inside, [False, False])
        inside = netting_set(np.array([True, True, False]), np.array([0, 1, 2]), np.array([1, 0, 0]),
                             np.array([10.0, 10.0, 5.0]))
        np.testing.assert_array_equal(inside, [False, False, False])

    def test_a_loss_reaches_a_payer_outside_the_set(self):
        """The map runs downward on everyone, a case of the arithmetic alone: A (0) and B (1) are held at zero; C (2),
        outside the set with means 2, owes D (3) 6 and was paid 4 by A. With A at zero C completes 2 of 6, so the value
        lost is A's 10, B's 10 and C's 4."""
        b, s, owed = np.array([0, 0, 1, 2]), np.array([1, 2, 0, 3]), np.array([10.0, 4.0, 10.0, 6.0])
        f = np.array([10 / 14, 1.0, 1.0, 1.0])
        receipts = lambda share: np.bincount(s, weights=owed * share[b], minlength=4)
        need = np.bincount(b, weights=owed, minlength=4)
        lost, share = netting_loss(f, np.array([True, True, False, False]), np.array([0.0, 0.0, 2.0, 0.0]), need,
                                   receipts, need)
        np.testing.assert_allclose(share, [0.0, 0.0, 1 / 3, 1.0], atol=1e-15)
        self.assertAlmostEqual(lost, 10.0 + 10.0 + 4.0, places=12)

    def test_the_plans_hand_case_through_the_settlement(self):
        """A (0) and B (1) hold nothing and owe each other 10: both pay, the set is {A, B}, its value 20 and the value
        lost when it is held at zero 20. If A holds 1, or a third payer (2) with money pays A, the set is empty."""
        w = controlled_world("S0")
        payments(w, [0, 1], [1, 0], [10.0, 10.0])
        added = settled(w)
        self.assertEqual((added["netting_days"], added["netting_n"]), (1.0, 2.0))
        self.assertAlmostEqual(added["netting_value"], 20.0, places=12)
        self.assertAlmostEqual(added["netting_lost"], 20.0, places=12)
        self.assertAlmostEqual(added["cash_completed"], 20.0, places=12)
        self.assertAlmostEqual(added["failed"], 0.0, places=12)
        w = controlled_world("S0")
        w.cash[0] = 1.0
        payments(w, [0, 1], [1, 0], [10.0, 10.0])
        added = settled(w)
        self.assertEqual((added["netting_days"], added["netting_n"], added["netting_value"]), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(added["cash_completed"], 20.0, places=12)
        w = controlled_world("S0")
        w.cash[2] = 5.0
        payments(w, [0, 1, 2], [1, 0, 0], [10.0, 10.0, 5.0])
        added = settled(w)
        self.assertEqual((added["netting_days"], added["netting_n"], added["netting_lost"]), (0.0, 0.0, 0.0))

    def test_a_loop_of_less_than_a_cent_is_not_counted(self):
        """A and B hold nothing and owe each other a tenth of a cent: both pay in the solution, but a remainder
        below one cent is no payment, so the day counts no set. At one cent each the pair is counted."""
        w = controlled_world("S0")
        payments(w, [0, 1], [1, 0], [CENT / 10, CENT / 10])
        added = settled(w)
        self.assertEqual((added["netting_days"], added["netting_n"], added["netting_value"]), (0.0, 0.0, 0.0))
        w = controlled_world("S0")
        payments(w, [0, 1], [1, 0], [CENT, CENT])
        added = settled(w)
        self.assertEqual((added["netting_days"], added["netting_n"]), (1.0, 2.0))


class StoredSeriesTests(unittest.TestCase):

    def test_every_arm_stores_the_records_and_they_add_up_to_the_failures(self):
        """In every arm of a tiny economy under distress the new series exist and are finite, every day of a month
        falls in one bin, and each month's own shortfall plus signed knock-on is the month's failures (``failures``,
        new failed payments at face value a person, as the run already records them)."""
        economy = replace(TINY, distress=0.02, distress_start=1, distress_length=3)
        for arm in ("S0", "M0", "U", "M1", "M2"):
            series = simulate(Inputs(), 0.6, economy, arm)["series"]
            for key in CHAIN_SERIES:
                self.assertEqual(series[key].shape, (economy.burn_in + economy.months,))
                self.assertTrue(np.isfinite(series[key]).all(), (arm, key))
            np.testing.assert_allclose(series["own_shortfall"] + series["knock_on"], series["failures"], rtol=0,
                                       atol=1e-12)
            days = sum(series["knock_on_days_" + key] for key in KNOCK_ON_BINS)
            np.testing.assert_array_equal(days, 30)
            self.assertTrue((series["knock_on_positive"] >= series["knock_on"] - 1e-12).all())
            self.assertTrue((series["netting_value"] <= series["cash_completed"] + 1e-12).all())
            self.assertTrue((series["own_shortfall"] > 0).any(), arm)


if __name__ == "__main__":
    unittest.main()

"""Tests for the rule on savings and durables, ``Economy.durable_savings``, at small scale.

What is covered
---------------
* The own money a durable may take before credit: by default everything above the buffer; under "kept" above the
  savings kept in own cash at the last dealing too, never below zero. The setting's example.
* The default is "used", and an unknown value is refused.
* A small world: the dealing records each person's kept savings, nothing for anyone whose cash pays less than the
  deposit rate, so nothing under banks; the bank arrangement is the same bit for bit under either value; under CPM
  the same durables are bought with more credit under "kept"; and the accounting identity holds every month.
"""
import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import Economy, _World
from cpm_abm.economy_abm import BIG, LATE_WAGE, MONTH_USD, SERVICE, TERM
from cpm_abm.engine.world_day import DayMixin
from tests.test_economy_abm import controlled_world

# A small world: a burn-in of 6 months under banks, then 18 months after launch.
SMALL = Economy(n=300, burn_in=6, months=18)


def identical(a, b):
    """Bit for bit: arrays by dtype, shape and bytes, dicts of them key by key in order."""
    if isinstance(a, dict):
        return list(a) == list(b) and all(identical(a[key], b[key]) for key in a)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def person(durable_savings):
    """Two people in dollars. The first holds $70,000, $20,000 in the bank and $50,000 in the wallet, with a buffer of
    $9,000 and $50,000 of savings kept at the last dealing; the second holds $30,000 after drawing on its kept savings
    of $50,000, with the same buffer."""
    return SimpleNamespace(cash=np.array([20000.0, 30000.0]), pcash=np.array([50000.0, 0.0]),
                           buffer=np.array([9000.0, 9000.0]), kept_savings=np.array([50000.0, 50000.0]),
                           economy=SimpleNamespace(durable_savings=durable_savings))


class DurableSavingsTests(unittest.TestCase):
    def test_own_money_for_a_durable(self):
        """By default a durable may take everything above the buffer, $61,000 and $21,000. Under "kept" the kept savings
        are left alone: $11,000 for the first, and nothing for the second, whose money is already below them."""
        np.testing.assert_array_equal(DayMixin._durable_money(person("used")), [61000.0, 21000.0])
        np.testing.assert_array_equal(DayMixin._durable_money(person("kept")), [11000.0, 0.0])

    def test_kept_savings_run_down_as_outside_savings(self):
        """Example of the run-down: a buffer of $100 and $100 of savings, then a $200 bill
        and a $150 receipt. The bank customer's savings pay half the bill and are not refilled, so $50 of bank money is
        above its buffer; the wallet's kept savings fall to the wallet's $0 and stay there, so the same $50 is free for
        a durable. Under "used" the kept savings are not touched."""
        for reading, after in (("kept", [50.0]), ("used", [50.0])):
            wallet = SimpleNamespace(cash=np.zeros(1), pcash=np.array([200.0]), buffer=np.array([100.0]),
                                     kept_savings=np.array([100.0]),
                                     economy=SimpleNamespace(durable_savings=reading))
            wallet.pcash -= 200.0   # the bill
            DayMixin._run_down_kept(wallet)
            wallet.pcash += 150.0   # the receipt, on a later day
            DayMixin._run_down_kept(wallet)
            np.testing.assert_array_equal(wallet.kept_savings, [0.0] if reading == "kept" else [100.0])
            np.testing.assert_array_equal(DayMixin._durable_money(wallet), after)
        bank = SimpleNamespace(cash=np.array([100.0]), pcash=np.zeros(1), buffer=np.array([100.0]),
                               kept_savings=np.zeros(1), economy=SimpleNamespace(durable_savings="kept"))
        savings = 100.0
        drawn = min(200.0 - bank.cash[0], savings)   # the bill draws on outside savings once bank money is gone
        bank.cash += drawn - 200.0
        bank.cash += 150.0
        np.testing.assert_array_equal(DayMixin._durable_money(bank), [50.0])
        # Own money above the kept savings leaves them as they are; own money below zero counts as zero.
        wallet = SimpleNamespace(cash=np.zeros(1), pcash=np.array([160.0]), kept_savings=np.array([100.0]),
                                 economy=SimpleNamespace(durable_savings="kept"))
        DayMixin._run_down_kept(wallet)
        np.testing.assert_array_equal(wallet.kept_savings, [100.0])
        wallet.pcash[:] = -20.0   # an overdraft floors own money at zero
        DayMixin._run_down_kept(wallet)
        np.testing.assert_array_equal(wallet.kept_savings, [0.0])

    @staticmethod
    def day_world():
        """The controlled world under "kept": person 0 in P with $200 of its own, a buffer of $100 and $100 of savings
        kept at the last dealing; person 3 holds $500 of bank money and no buffer."""
        w = controlled_world()
        w.economy = replace(w.economy, durable_savings="kept")
        w.part[0] = True
        w.pcash[0], w.buffer[0], w.kept_savings[0] = 200.0 / MONTH_USD, 100.0 / MONTH_USD, 100.0 / MONTH_USD
        w.cash[3] = 500.0 / MONTH_USD
        w.pop["cycles"][0], w.pop["phases"][0] = 1, 0   # a daily biller, so an instalment falls due on day 30
        return w

    def test_a_morning_instalment_is_seen_after_the_day_refills_the_wallet(self):
        """A $200 instalment takes the wallet to $0 in the morning, then a $150 bill paid to it refills it: the savings
        are $0 at the day's end, as a bank customer's would be after its savings paid the instalment."""
        w = self.day_world()
        w._add_loans(np.array([0]), False, TERM, np.array([200.0 / MONTH_USD]), 0.0, 0.0, BIG, np.array([1]), 0)
        w.ob = dict(buyer=np.array([3]), seller=np.array([0]), amount=np.array([150.0 / MONTH_USD]),
                    settle=np.array([30]), card=np.array([False]), kind=np.array([SERVICE]))
        w.payable[3] = w.receivable[0] = 150.0 / MONTH_USD
        w.day(1, 0)
        self.assertAlmostEqual(float(w.pcash[0] + w.cash[0]) * MONTH_USD, 150.0, places=2)   # with the day's yield
        self.assertAlmostEqual(float(w.kept_savings[0]) * MONTH_USD, 0.0, places=9)

    def test_a_late_wage_received_at_the_day_end_does_not_refill_the_savings(self):
        """A $200 bill empties the wallet in the settlement, then a $150 overdue wage is paid to it at the day's end:
        the savings are $0, not the $100 the dealing kept."""
        w = self.day_world()
        w.ob = dict(buyer=np.array([0, 3]), seller=np.array([4, 0]),
                    amount=np.array([200.0, 150.0]) / MONTH_USD, settle=np.array([30, 45]),
                    card=np.array([False, False]), kind=np.array([SERVICE, LATE_WAGE]))
        w.payable[0], w.receivable[4] = 200.0 / MONTH_USD, 200.0 / MONTH_USD
        w.payable[3], w.receivable[0] = 150.0 / MONTH_USD, 150.0 / MONTH_USD
        w.day(1, 0)
        self.assertAlmostEqual(float(w.pcash[0] + w.cash[0]) * MONTH_USD, 150.0, places=2)   # with the day's yield
        self.assertAlmostEqual(float(w.kept_savings[0]) * MONTH_USD, 0.0, places=9)

    def test_default_and_refusal(self):
        self.assertEqual(Economy().durable_savings, "used")
        with self.assertRaises(ValueError):
            Economy(durable_savings="spent")

    def test_a_small_world_under_both_readings(self):
        after = slice(SMALL.burn_in, SMALL.burn_in + SMALL.months)
        borrowed = {}
        for reading in ("used", "kept"):
            economy = replace(SMALL, durable_savings=reading)
            banks = _World(Inputs(), 0.6, economy, "S0")
            s0 = banks.run()
            # Bank money pays less than the deposit rate, so no bank customer keeps savings in its own cash.
            self.assertEqual(float(banks.kept_savings.sum()), 0.0)
            pool = _World(Inputs(), 0.6, economy, "M1")
            m1 = pool.run()
            # A participant's wallet pays at least the deposit rate, so its deposit savings stay in it; nobody else's.
            self.assertGreater(float(pool.kept_savings[pool.part].sum()), 0.0)
            self.assertEqual(float(pool.kept_savings[~pool.part].sum()), 0.0)
            for run in (s0, m1):
                series = run["series"]
                np.testing.assert_allclose(series["wealth_change"],
                                           series["external"] + series["valuation"] + series["inflation"], atol=1e-12)
            credit = m1["credit"]
            borrowed[reading] = (float((credit["term_pool"] + credit["term_outside"])[after].sum()),
                                 float(m1["purchases"]["durables"][after].sum()), s0)
        # The bank arrangement never spent savings on a durable, so the setting changes nothing in it.
        for key in ("series", "wealth", "failed", "credit"):
            self.assertTrue(identical(borrowed["used"][2][key], borrowed["kept"][2][key]), key)
        # Under CPM people who keep their savings borrow more of each durable's price.
        self.assertGreater(borrowed["kept"][0] / borrowed["kept"][1], borrowed["used"][0] / borrowed["used"][1])


if __name__ == "__main__":
    unittest.main()

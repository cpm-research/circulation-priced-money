"""Tests for the recording-only measures, at tiny scale. No rule reads any of these records.

What is covered
---------------
* Velocity records: each person's payments to others out of E and P (the outflow, ``_debit``), conversion fees paid
  to outsiders included and the dealing's move into own savings and shares left out, the yearly records against the
  monthly balance-time series, and two readings by year on three definitions of money, for participants and
  non-participants apart: wallet turnover, outflow over the person's own average balance (``turnover``), and
  MicroVelocity (Campajola, D'Errico and Tessone, equations 5 to 7), the person's contribution to the aggregate
  velocity, outflow over everyone's average balance (``microvelocity``).
* MicroVelocity as its authors define it, from the holding time of every unit of money, first in first out and last
  in first out (``Coinage``, ``holding_velocity``): worked examples, removals, CPI's pro rata loss, a year end, the
  monthly cohorts' mean receipt day, the reconciliation of every person's money in every arm, and the aggregate
  against the outflow-based reading.
* Completed purchases as a count, at the share completed.
* The largest single pool loan, and the largest borrower's pool debt, as shares of pool capital.
* The runner's ``measures`` stores them, None where undefined.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import (BRIDGE, COIN_CONVENTIONS, MEASURE_SERIES, VELOCITY_RECORDS, Coinage, Economy,
                                 _World, holding_velocity, microvelocity, simulate, turnover)
from tests.test_economy_abm import TINY, controlled_world, funded_pool, one_invoice


def records(outflow, money, savings=None, shares=None):
    """A run's ``velocity`` records from per-person rows by year (lists of lists)."""
    money = np.array(money, float)
    zero = np.zeros_like(money)
    return dict(outflow=np.array(outflow, float), money_bt=money,
                savings_bt=zero if savings is None else np.array(savings, float),
                shares_bt=zero if shares is None else np.array(shares, float))


class MicroVelocityReading(unittest.TestCase):
    def test_hand_case_two_people_turnover_and_microvelocity(self):
        """Turnover is outflow over the person's own average balance; MicroVelocity (Campajola, D'Errico and Tessone,
        equations 5 to 7) is each person's contribution to the aggregate velocity, outflow over everyone's average
        balance.

        Example: a person holding 100 all year (balance-time 1,200 unit-months) and one holding 300 (3,600), each
        paying out 1,200. Turnover: 12 and 4. MicroVelocity: 12 x 1,200 / 4,800 = 3 and 3, summing to 6, the aggregate
        velocity 2,400 / 400, which is also turnover's balance-weighted mean. Each person is half the sum; the top
        tenth of two persons is one, so its share is 0.5."""
        flows = records([[1200, 1200]], [[1200, 3600]])
        nobody = np.zeros((12, 2), bool)
        rate = turnover(flows, nobody)["broad"]["non_participants"]
        self.assertAlmostEqual(rate["p90"][0], 11.2, places=12)                  # 4 + 0.9 x (12 - 4): 12 and 4
        self.assertAlmostEqual(rate["p10"][0], 4.8, places=12)
        contribution = microvelocity(flows, nobody)
        group = contribution["broad"]["non_participants"]
        self.assertEqual(group["people"], [2])
        self.assertAlmostEqual(group["sum"][0], 6.0, places=12)
        self.assertAlmostEqual(group["median"][0], 3.0, places=12)
        self.assertAlmostEqual(group["p90"][0], 3.0, places=12)
        self.assertAlmostEqual(group["top_tenth_share"][0], 0.5, places=12)
        self.assertEqual(contribution["broad"]["participants"], dict(people=[0], sum=[None], median=[None], p90=[None],
                                                                     top_tenth_share=[None]))

    def test_microvelocity_groups_share_one_total_stock(self):
        """Contributions divide by everyone's balance-time, so the two groups' sums add to the aggregate velocity.
        Person 0 participates (all 12 months), holds 100 and pays out 2,400; person 1 does not, holds 300 and pays out
        1,200: total balance-time 4,800, so the participants' sum is 12 x 2,400 / 4,800 = 6 and the others' 3, adding
        to 9 = 3,600 / 400. A person with no balance and no outflow contributes 0 and still counts."""
        flags = np.zeros((12, 3), bool)
        flags[:, 0] = True
        out = microvelocity(records([[2400, 1200, 0]], [[1200, 3600, 0]]), flags)["e_p"]
        self.assertAlmostEqual(out["participants"]["sum"][0], 6.0, places=12)
        self.assertAlmostEqual(out["non_participants"]["sum"][0], 3.0, places=12)
        self.assertEqual(out["non_participants"]["people"], [2])
        self.assertAlmostEqual(out["non_participants"]["median"][0], 1.5, places=12)
        self.assertAlmostEqual(out["non_participants"]["top_tenth_share"][0], 1.0, places=12)

    def test_turnover_hand_case_two_people(self):
        """Example: a person holding 100 all year (balance-time 100 x 12 = 1,200 unit-months) that pays out 1,200
        turns its money 12 times a year; a person holding 300 (balance-time 3,600) that pays out 1,200 turns it 4 times.
        Their mean is 8, their median 8, and the balance-weighted mean (the aggregate velocity) is
        (100 x 12 + 300 x 4) / (100 + 300) = 2,400 / 400 = 6. Nobody participates, so the participants' group is empty
        (None) and counts 0 people."""
        out = turnover(records([[1200, 1200]], [[1200, 3600]]), np.zeros((12, 2), bool))
        group = out["broad"]["non_participants"]
        self.assertEqual(group["people"], [2])
        self.assertAlmostEqual(group["mean"][0], 8.0, places=12)
        self.assertAlmostEqual(group["median"][0], 8.0, places=12)
        self.assertAlmostEqual(group["weighted"][0], 6.0, places=12)
        self.assertAlmostEqual(group["p10"][0], 4.8, places=12)    # numpy's linear rule: 4 + 0.1 x (12 - 4)
        self.assertAlmostEqual(group["p90"][0], 11.2, places=12)
        self.assertEqual(out["broad"]["participants"], dict(people=[0], mean=[None], weighted=[None], median=[None],
                                                            p10=[None], p90=[None]))

    def test_definitions_add_savings_then_shares(self):
        """Example: one person pays out 1,200 in the year and holds 100 of E and P, 100 of savings and 200 of pool
        shares all year (balance-times 1,200, 1,200 and 2,400). On E and P alone it turns 12 times a year, on E, P and
        savings 1,200 / 200 = 6, on broad money 1,200 / 400 = 3: the same payments over a wider stock."""
        out = turnover(records([[1200]], [[1200]], [[1200]], [[2400]]), np.zeros((12, 1), bool))
        read = lambda name: out[name]["non_participants"]["weighted"][0]
        self.assertAlmostEqual(read("e_p"), 12.0, places=12)
        self.assertAlmostEqual(read("e_p_savings"), 6.0, places=12)
        self.assertAlmostEqual(read("broad"), 3.0, places=12)

    def test_groups_years_and_empty_balances(self):
        """A participant in a year is in the network in at least half its months: person 0 in 6 of 12 is one, person 1
        in 5 of 12 is not. Year two is a part year of 6 months: person 0 holds 50 for it (balance-time 300) and pays out
        150, so it turns 12 x 150 / 300 = 6 times a year, its rate over the half year scaled to a year. A person with no
        balance on a definition has no MicroVelocity and is left out, not read as zero or infinite."""
        flags = np.zeros((18, 3), bool)
        flags[:6, 0], flags[:5, 1] = True, True
        flags[12:, 0] = True
        out = turnover(records([[120, 240, 5], [150, 0, 0]], [[120, 120, 0], [300, 60, 0]]), flags)
        broad = out["broad"]
        self.assertEqual(broad["participants"]["people"], [1, 1])
        self.assertEqual(broad["non_participants"]["people"], [1, 1])   # person 2 has no balance: left out
        self.assertAlmostEqual(broad["participants"]["mean"][0], 12.0, places=12)
        self.assertAlmostEqual(broad["non_participants"]["mean"][0], 24.0, places=12)
        self.assertAlmostEqual(broad["participants"]["mean"][1], 6.0, places=12)
        self.assertAlmostEqual(broad["non_participants"]["mean"][1], 0.0, places=12)


class MeasuresInTheEngine(unittest.TestCase):
    def test_outflow_counts_payments_to_others_with_their_fee(self):
        """Example: a person holding 5 in P and nothing in E pays 3 in P and 2 in E, converting the 2 at its
        conversion rate r, so the debit takes 3 + 2 x (1 + r) from its money and that is its outflow. The dealing's move
        of its own money into its savings and shares (``spend=False``) is no outflow."""
        w = controlled_world()
        w.acc["outflow"][:] = 0.0
        w.pcash[0] = 5.0
        rate = float(w._rate()[0])
        w._debit(np.where(np.arange(10) == 0, 3.0, 0.0), np.where(np.arange(10) == 0, 2.0, 0.0))
        self.assertAlmostEqual(float(w.acc["outflow"][0]), 3.0 + 2.0 * (1 + rate), places=12)
        self.assertEqual(float(w.acc["outflow"][1:].sum()), 0.0)
        w.cash[1] = 4.0
        w._debit(np.zeros(10), np.where(np.arange(10) == 1, 4.0, 0.0), spend=False)
        self.assertEqual(float(w.acc["outflow"][1]), 0.0)

    def test_conversion_fees_at_joining_leaving_and_subscribing_are_outflow(self):
        """A conversion fee is paid to an outsider, so it is outflow, while the principal moved between a person's
        own balances is not.

        Examples at the arm's conversion rate r: leaving with 1 of P adds r (about 0.001979 in M1); joining with E of
        1 + r adds r; a subscription of 3 in P paid from E alone (``spend=False``) adds 3r, the fee on the part
        converted."""
        w = controlled_world("M1")
        w.acc["outflow"][:], w.acc["conversion"][:] = 0.0, 0.0
        w.part[0], w.pcash[0] = True, 1.0
        w._leave(np.arange(w.n) == 0)
        self.assertGreater(float(w.acc["conversion"][0]), 0.0)
        self.assertAlmostEqual(float(w.acc["outflow"][0]), float(w.acc["conversion"][0]), places=15)
        self.assertAlmostEqual(float(w.acc["outflow"][0]), w.conversion, places=15)
        self.assertEqual(float(w.acc["outflow"][1:].sum()), 0.0)
        w = controlled_world("M1")
        w.acc["outflow"][:] = 0.0
        w.cash[:] = 0.0
        w.cash[1] = 1.0 + w.conversion
        w._join(np.arange(w.n) == 1, np.ones(w.n))
        self.assertAlmostEqual(float(w.pcash[1]), 1.0, places=15)
        self.assertAlmostEqual(float(w.acc["outflow"][1]), w.conversion, places=15)
        w = controlled_world("M1")
        w.acc["outflow"][:] = 0.0
        w.pcash[:], w.cash[:] = 0.0, 0.0
        w.cash[2] = 10.0
        rate = float(w._rate()[2])
        w._debit(np.where(np.arange(w.n) == 2, 3.0, 0.0), np.zeros(w.n), spend=False)
        self.assertGreater(rate, 0.0)
        self.assertAlmostEqual(float(w.acc["outflow"][2]), 3.0 * rate, places=15)

    def test_completed_purchases_count_at_the_share_completed(self):
        """Example: a payer with no card, no savings, no pool and 0.4 of money owes a service invoice of 1.0; it pays
        0.4 and the rest fails, so 0.4 of a purchase is completed (counted as completed P payments are) and its
        outflow is 0.4. The same invoice paid in full counts one purchase."""
        w = controlled_world()
        w.acc["outflow"][:], w.acc["bought_n"] = 0.0, 0.0
        w.cash[0] = 0.4
        one_invoice(w, 1.0, card=False)
        w._settle(1, 30)
        self.assertAlmostEqual(w.acc["bought_n"], 0.4, places=12)
        self.assertAlmostEqual(float(w.acc["outflow"][0]), 0.4, places=12)
        w = controlled_world()
        w.acc["bought_n"] = 0.0
        w.cash[0] = 2.0
        one_invoice(w, 1.0, card=False)
        w._settle(1, 30)
        self.assertAlmostEqual(w.acc["bought_n"], 1.0, places=12)

    def test_largest_pool_loan_share(self):
        """Example: pool capital 100 (100 shares at NAV 1), carried pool bridges of 10 and 6 to person 0 and 12 to
        person 1: the largest single loan is 12 / 100 = 0.12 of capital and the largest borrower's debt 16 / 100 = 0.16
        (12 U.S.C. 84 caps one borrower at 0.15). A written-off loan is carried at zero and drops out; with no capital
        the share is undefined (NaN)."""
        w = controlled_world()
        funded_pool(w, 100.0)
        w._add_loans(np.array([0, 0, 1]), True, BRIDGE, np.array([10.0, 6.0, 12.0]), 0.0, 0.0, np.array([60, 60, 60]))
        loan, borrower = w._largest_shares()
        self.assertAlmostEqual(loan, 0.12, places=12)
        self.assertAlmostEqual(borrower, 0.16, places=12)
        w.book["carried"][2] = False
        self.assertEqual(w._largest_shares(), (0.10, 0.16))
        w.shares[:] = 0.0
        self.assertTrue(all(np.isnan(w._largest_shares())))

    def test_runs_store_the_records(self):
        """A tiny run of each kind stores the four series a month and the yearly records; the yearly balance-times add
        up exactly to the monthly balance-time series after launch (burn-in left out), the counts are positive, and the
        pool shares are NaN in S0 and M0 (no pool) and finite in M1 whenever it has capital. A participant's broad
        money holds its narrower money, so its MicroVelocity is never higher on broad money."""
        economy = replace(TINY, n=60, burn_in=2, months=14)
        after = slice(economy.burn_in, economy.burn_in + economy.months)
        for arm in ("S0", "M0", "M1"):
            run = simulate(Inputs(), 0.6, economy, arm)
            series, velocity = run["series"], run["velocity"]
            self.assertTrue(set(MEASURE_SERIES) <= set(series))
            self.assertEqual(set(velocity), set(VELOCITY_RECORDS))
            self.assertEqual(velocity["outflow"].shape, (2, economy.n))   # 14 months: one year and a part year
            for key in ("money_bt", "savings_bt", "shares_bt"):
                self.assertAlmostEqual(float(velocity[key].sum()), float(series[key][after].sum()) * economy.n,
                                       places=8)
            self.assertTrue(np.all(velocity["outflow"] >= 0) and velocity["outflow"].sum() > 0)
            self.assertTrue(np.all(series["purchases_n"] > 0))
            share = series["largest_loan_share"][after]
            if arm == "M1":
                capital = series["owners_capital"][after] > 0
                self.assertTrue(np.all(np.isfinite(share[capital])))
                self.assertTrue(np.all(series["largest_borrower_share"][after][capital] >= share[capital]))
            else:
                self.assertTrue(np.all(np.isnan(share)))
            read = turnover(velocity, run["participant"][after])
            for group in ("participants", "non_participants"):
                for k in range(2):
                    broad, narrow = read["broad"][group]["weighted"][k], read["e_p"][group]["weighted"][k]
                    if broad is not None and narrow is not None:
                        self.assertLessEqual(broad, narrow + 1e-12)

    def test_runner_stores_them(self):
        """The runner's ``measures`` stores the four series a month after launch, None where undefined, and the
        turnover and MicroVelocity readings on their three definitions for both groups; the groups' MicroVelocity sums
        add to the aggregate velocity, the population's total outflow over its total average balance."""
        from scripts.run_economy_population import measures
        economy = replace(TINY, n=40, burn_in=2, months=12)
        run = simulate(Inputs(), 0.6, economy, "S0")
        stored = measures(run, economy)
        self.assertTrue(set(MEASURE_SERIES) <= set(stored))
        self.assertEqual(stored["largest_loan_share"], [None] * 12)
        self.assertEqual(len(stored["purchases_n"]), 12)
        for name in ("turnover", "microvelocity"):
            self.assertEqual(set(stored[name]), {"broad", "e_p_savings", "e_p"})
            self.assertEqual(stored[name]["broad"]["participants"]["people"], [0])
            self.assertEqual(stored[name]["broad"]["non_participants"]["people"], [economy.n])
        holding = stored["holding_velocity"]    # MicroVelocity from holding times, both conventions
        self.assertEqual(set(holding), {"edges", "fifo", "lifo"})
        self.assertEqual(len(holding["fifo"]["non_participants"]["histogram"][0]), len(holding["edges"]))
        self.assertGreater(holding["lifo"]["non_participants"]["sum"][0], 0.0)
        self.assertEqual(holding["fifo"]["participants"]["mean_tau"], [None])
        velocity = run["velocity"]
        broad = velocity["money_bt"] + velocity["savings_bt"] + velocity["shares_bt"]
        aggregate = 12 * velocity["outflow"][0].sum() / broad[0].sum()
        self.assertAlmostEqual(stored["microvelocity"]["broad"]["non_participants"]["sum"][0], aggregate, places=9)
        self.assertAlmostEqual(stored["turnover"]["broad"]["non_participants"]["weighted"][0], aggregate, places=9)


def ledger(days=720, years=2, launch=0):
    """An empty one-person ``Coinage`` ledger."""
    return Coinage(np.zeros(1), days, launch, years)


def day(book, t, inflow=0.0, spend=0.0, removal=0.0, scale=None):
    """One day of one person's flows."""
    book.step(t, np.array([inflow]), np.array([spend]), np.array([removal]),
              None if scale is None else np.array([scale]))


class HoldingTimes(unittest.TestCase):
    """MicroVelocity as Campajola, D'Errico and Tessone define it (arXiv 2201.13416, equations 4 to 7 and their
    estimator): the holding time of every unit of money, under first in first out (index 0) and last in first out
    (index 1)."""

    def test_one_unit_held_ten_days(self):
        """Example: 100 received on day 0 and spent on day 10 (launch day 0). Its holding time is tau = 10 under
        both conventions; its spell is days 1 to 10, all in year 0, so it adds 100 x 10 / 10 = 100 to ``held``, 100 to
        ``spent``, 100 / 10 = 10 to ``inverse`` and 100 x 10 = 1,000 to ``spent_tau``, in the bin [8, 15). The year's
        balance-time is 100 for 10 days, 100 x 10 / 30 = 33.33 unit-months, so V = 12 x 100 / 33.33 = 36 turns a
        year, 360 days over a ten-day holding time. Nothing is left in the ledger."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 10, spend=100.0)
        rec = book.rec
        np.testing.assert_allclose(rec["held"][:, 0, 0], [100.0, 100.0], rtol=0, atol=1e-12)
        np.testing.assert_allclose(rec["held"][:, 1, 0], [0.0, 0.0], atol=1e-12)
        np.testing.assert_allclose(rec["spent"][:, 0, 0], [100.0, 100.0], atol=1e-12)
        np.testing.assert_allclose(rec["inverse"][:, 0, 0], [10.0, 10.0], atol=1e-12)
        np.testing.assert_allclose(rec["spent_tau"][:, 0, 0], [1000.0, 1000.0], atol=1e-9)
        self.assertEqual(int(np.argmax(rec["histogram"][0, 0, 0])), 3)   # [8, 15)
        self.assertAlmostEqual(12 * rec["held"][0, 0, 0] / (100.0 * 10 / 30), 36.0, places=9)
        np.testing.assert_allclose(book.total(), 0.0, atol=1e-12)

    def test_first_in_first_out_and_last_in_first_out(self):
        """Example: 100 received on day 0 and 100 on day 20, then 100 spent on day 30: tau 30 under first in first
        out (the day 0 units, ``spent_tau`` 3,000) and 10 under last in first out (the day 20 units, 1,000). Then 100
        spent on day 40: tau 20 (the day 20 units) and 40 (the day 0 units)."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 20, inflow=100.0)
        day(book, 30, spend=100.0)
        np.testing.assert_allclose(book.rec["spent_tau"][:, 0, 0], [3000.0, 1000.0], atol=1e-9)
        np.testing.assert_allclose(book.rec["inverse"][:, 0, 0], [100 / 30, 10.0], atol=1e-12)
        day(book, 40, spend=100.0)
        np.testing.assert_allclose(book.rec["spent_tau"][:, 0, 0], [3000.0 + 2000.0, 1000.0 + 4000.0], atol=1e-9)

    def test_spending_received_the_same_day_has_tau_one(self):
        """Last in first out spends today's receipt first, at the least holding time, 1 day, over the day itself;
        first in first out spends the older 100 received on day 0, tau 5."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 5, inflow=50.0, spend=50.0)
        np.testing.assert_allclose(book.rec["spent_tau"][:, 0, 0], [250.0, 50.0], atol=1e-9)
        np.testing.assert_allclose(book.rec["held"][:, 0, 0], [50.0, 50.0], atol=1e-12)

    def test_a_unit_held_across_a_year_end_is_split(self):
        """Example: 100 received on day 300 and spent on day 400 (launch day 0, years of 360 days): tau 100, held on
        days 301 to 400, 59 of them in year 0 and 41 in year 1, so ``held`` adds 100 x 59 / 100 = 59 to year 0 and
        41 to year 1; the spending (100, tau 100) is recorded in year 1, the year it is spent. The unit passes through
        the monthly cohorts (older than 90 days), whose mean receipt day is exactly 300 here."""
        book = ledger()
        day(book, 300, inflow=100.0)
        day(book, 400, spend=100.0)
        np.testing.assert_allclose(book.rec["held"][0, :, 0], [59.0, 41.0], atol=1e-9)
        np.testing.assert_allclose(book.rec["spent"][0, :, 0], [0.0, 100.0], atol=1e-12)
        np.testing.assert_allclose(book.rec["spent_tau"][0, 1, 0], 10000.0, atol=1e-7)

    def test_a_merged_month_reads_its_mean_receipt_day(self):
        """Money older than 90 days sits in one cohort a calendar month, at its amount-weighted mean receipt day: 100
        received on day 0 and 100 on day 20, all 200 spent on day 300, read tau 300 - 10 = 290 for both (in place of
        300 and 280), so ``inverse`` is 200 / 290 = 0.68966 against the exact 100 / 300 + 100 / 280 = 0.69048, 0.1%
        lower, the second-order error the class bounds."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 20, inflow=100.0)
        day(book, 300, spend=200.0)
        np.testing.assert_allclose(book.rec["inverse"][:, 0, 0], [200 / 290, 200 / 290], atol=1e-12)
        self.assertLess(abs(200 / 290 / (100 / 300 + 100 / 280) - 1), 0.002)

    def test_a_share_purchase_removes_units_without_a_holding_time(self):
        """Example: 100 received on day 0 and 100 on day 20; pool shares bought for 100 on day 25 take the day 0
        units under first in first out and the day 20 units under last in first out, recording nothing; 100 spent on
        day 30 then has tau 10 under first in first out and 30 under last in first out, and only 100 is spent."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 20, inflow=100.0)
        day(book, 25, removal=100.0)
        np.testing.assert_allclose(book.rec["spent"][:, 0, 0], [0.0, 0.0], atol=1e-12)
        day(book, 30, spend=100.0)
        np.testing.assert_allclose(book.rec["spent"][:, 0, 0], [100.0, 100.0], atol=1e-12)
        np.testing.assert_allclose(book.rec["spent_tau"][:, 0, 0], [1000.0, 3000.0], atol=1e-9)

    def test_cpi_loss_is_pro_rata(self):
        """CPI's loss of value takes every cohort pro rata, under either convention: 100 on day 0 and 100 on day 20,
        a loss of 20 on day 25 leaves 90 of each; spending 90 on day 30 takes the day 0 units under first in first out
        (tau 30) and the day 20 units under last in first out (tau 10)."""
        book = ledger()
        day(book, 0, inflow=100.0)
        day(book, 20, inflow=100.0)
        day(book, 25, scale=20.0)
        np.testing.assert_allclose(book.total(), [[180.0], [180.0]], atol=1e-12)
        day(book, 30, spend=90.0)
        np.testing.assert_allclose(book.rec["spent_tau"][:, 0, 0], [2700.0, 900.0], atol=1e-9)

    def test_spending_before_launch_is_not_recorded(self):
        """Launch on day 40. A unit received on day 0 and spent on day 30 is spent before launch, so no record; one
        spent on day 60 has tau 60, held on days 1 to 60, of which only days 40 to 60, 21 days, count in ``held``:
        100 x 21 / 60 = 35."""
        book = ledger(launch=40)
        day(book, 0, inflow=200.0)
        day(book, 30, spend=100.0)
        self.assertEqual(float(book.rec["spent"].sum()), 0.0)
        day(book, 60, spend=100.0)
        np.testing.assert_allclose(book.rec["held"][:, 0, 0], [100 * 21 / 60] * 2, atol=1e-12)

    def test_moves_to_and_from_savings_keep_the_age(self):
        """Money is E, P and outside savings, so a move among them records no flow and the unit keeps its age:
        drawing savings into cash the same day, a participant's E consolidated into P and the dealing's move of spare
        E into savings all leave the day's receipts and removals at zero."""
        w = controlled_world("M1")
        w.coin_flow[:] = 0.0
        w.savings[0], w.cash[1], w.part[1] = 5.0, 2.0, True
        w._use_savings(np.where(np.arange(w.n) == 0, 3.0, 0.0))
        w._consolidate()
        w._debit(np.zeros(w.n), np.where(np.arange(w.n) == 0, 3.0, 0.0), spend=False)
        w.savings[0] += 3.0
        self.assertEqual(float(np.abs(w.coin_flow).sum()), 0.0)
        self.assertAlmostEqual(float(w.cash[0] + w.pcash[0] + w.savings[0]), 5.0, places=12)

    def test_windows_change_nothing(self):
        """The tiers of ``Coinage._consume`` (the edge cohort, then windows of cohorts, then every cohort) are a speed
        device: 40 persons with random receipts, spending, removals and CPI losses over 400 days give the same records
        and the same ledger, to rounding, with the default windows and with windows of 2 and 6 cohorts (so the windows
        are passed in a 400-day run) as with windows as wide as every cohort."""
        import cpm_abm.engine.ledger as engine   # the module ``Coinage`` reads its window from
        rng = np.random.default_rng(5)
        n, days = 40, 400
        flows = rng.random((days, 4, n)) * (rng.random((days, 4, n)) < [[0.3], [0.5], [0.05], [0.01]])
        flows[:, 1:3] *= 0.6

        def run(window):
            saved = engine.COIN_WINDOW
            engine.COIN_WINDOW = window
            try:
                book = Coinage(np.full(n, 2.0), days, 100, 1)
                list(map(lambda t: book.step(t, flows[t, 0], flows[t, 1], flows[t, 2], flows[t, 3] * 0.01),
                         range(days)))
            finally:
                engine.COIN_WINDOW = saved
            return book

        wide = run(10 ** 6)
        for narrow in (run(engine.COIN_WINDOW), run(2)):
            for key in narrow.rec:
                np.testing.assert_allclose(narrow.rec[key], wide.rec[key], rtol=1e-12, atol=1e-12, err_msg=key)
            np.testing.assert_allclose(narrow.amt, wide.amt, rtol=1e-12, atol=1e-12)
        self.assertGreater(float(wide.rec["held"].sum()), 0.0)

    def test_runs_reconcile_in_every_arm(self):
        """For every person and month of a 100-person run of every arm, opening money (E, P and savings) plus
        receipts less spending (the outflow), removals and CPI's loss equals closing money to 1e-9; the ledger holds
        each person's closing money under both conventions; the value spent after launch is the outflow after launch,
        year by year; and the histogram adds up to it."""
        economy = replace(TINY, n=100, burn_in=3, months=15)
        for arm in ("S0", "M0", "U", "M1", "M2"):
            w = _World(Inputs(), 0.6, economy, arm)
            run = w.run()
            coin, velocity = run["coinage"], run["velocity"]
            self.assertLess(float(coin["residual"].max()), 1e-9, arm)
            stock = w.cash + w.pcash + w.savings
            np.testing.assert_allclose(w.coin.total(), np.vstack([stock, stock]), rtol=0, atol=1e-9, err_msg=arm)
            np.testing.assert_allclose(coin["spent"], np.stack([velocity["outflow"]] * 2), rtol=0, atol=1e-9,
                                       err_msg=arm)
            np.testing.assert_allclose(coin["histogram"].sum(axis=3), coin["spent"], rtol=0, atol=1e-9, err_msg=arm)
            self.assertTrue(np.all(coin["held"] >= 0) and coin["held"].sum() > 0, arm)

    def test_aggregate_close_to_outflow_velocity(self):
        """With short holding times the sum over persons of a year's V_i is close to the year's outflow over its total
        balance-time (``microvelocity``'s aggregate): every unit spent adds its value once to ``held``, spread over its
        spell. A synthetic case: one person spends and receives its 100 every ten days, all year, with 36 spells
        inside the year, gives exactly the outflow, 3,600. On a 300-person M1 run (30 months, the last a part year)
        year 1 reads 11.153 turns a year on the outflow, 11.113 first in first out and 11.102 last in first out (0.4%
        and 0.5% lower: spells that began before launch count only their days after it, and spells running into year
        2 move value into it); year 2 reads 10.926, 10.985 and 10.925; the part year at the end 9.794, 8.872 and
        9.341, lower since money unspent when the run ends is right-censored, more so under first in first out, whose
        units are older (mean holding time of money spent about 32 days against 17 to 23). The test holds year 1
        within 3%."""
        book = ledger(days=400, years=1)
        day(book, 0, inflow=100.0)
        list(map(lambda k: day(book, 10 * k, inflow=100.0, spend=100.0), range(1, 36)))
        day(book, 359, spend=100.0)
        self.assertAlmostEqual(float(book.rec["spent"][0, 0, 0]), 3600.0, places=9)
        self.assertGreater(float(book.rec["held"][0, 0, 0]), 3500.0)
        economy = Economy(n=300, months=30, seed=20261021)
        run = simulate(Inputs(), 0.6, economy, "M1")
        velocity, coin = run["velocity"], run["coinage"]
        bt = (velocity["money_bt"] + velocity["savings_bt"]).sum(axis=1)
        outflow = 12 * velocity["outflow"].sum(axis=1) / bt
        held = 12 * coin["held"].sum(axis=2) / bt
        np.testing.assert_allclose(held[:, 0], outflow[0], rtol=0.03)
        read = holding_velocity(coin, velocity, run["participant"][economy.burn_in:])
        for name in ("fifo", "lifo"):
            total = sum(read[name][g]["sum"][0] or 0.0 for g in ("participants", "non_participants"))
            self.assertAlmostEqual(total, float(held[COIN_CONVENTIONS.index(name), 0]), places=9)


if __name__ == "__main__":
    unittest.main()

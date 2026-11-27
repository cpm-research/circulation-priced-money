"""The evaluation windows follow the run: a long run reads both of its steady windows.

What is covered
---------------
* The rule: in the first run, W1 is months 13 to 36 after launch and W2 months 37 to 60, whatever the run's length; in a
  long run, the last five whole years before the stress year and the last five whole years of the run, so the second
  run reads years 6 to 10 and years 21 to 25. A long run with no settled years after its stress year is refused.
* The conjunction: a reading read in both windows holds only if it holds in each, and a falsifier fires if it fires in
  either, on made-up values and series (households holding 90% of pool capital with P routing).
* A tiny long run (the window shortened to one year so that both windows fit in a short run): every reading by window
  is stored for each window under its name, and each verdict that reads a steady window is the conjunction of the two.
* The stored development map: its rows read as the first run's (W1 and W2), and its cells evaluated again keep the
  stored keys and values of every reading by window.
* The runner's plumbing: the --distress-start bound reads the run's own months, and the distress labels of a first-run
  store are the first run's word for word.
"""
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from scripts import run_economy_population as runner   # puts src and scripts on the path, as the other tests do
import run_economy_figures as figures   # the module the experiment's readers import (not scripts.run_economy_figures)
import run_region_figures as map_figures
from cpm_abm.economy_abm import Economy
from cpm_abm.experiment import second_run
from cpm_abm.experiment.accounts import households_pool
from cpm_abm.experiment.region import decide_cells, names_of, steady_of
from cpm_abm.experiment.store import distress_note, run_record
from tests.test_second_run import available

STORE = Path(__file__).resolve().parents[1] / "results" / "development_map"
RELEASED = Economy(n=40)
SECOND = Economy(n=40, **second_run.LENGTHS)
# The first run's note on the distress levels, word for word.
RELEASED_NOTE = ("each distress level is the extra monthly rate per job in the distress year above normal job loss, "
                 "labelled by its total rate and by the share of jobs without a wage at month 36 (with normal job loss "
                 "at 0.55% a month, by hand, unverified); under the harsh stress the extra "
                 "layoffs' wages leave the household economy, owed by their payers to the outside, with no "
                 "unemployment insurance (declared), and the stress clause reads the headline level, 2009's wage loss "
                 "before unemployment insurance, while every level still runs")


class TheRule(unittest.TestCase):
    def test_released_windows(self):
        """In the first run: months 13 to 36 and 37 to 60 after launch, named W1 and W2, the claim reading W2."""
        self.assertEqual(figures.run_windows(RELEASED), (slice(18, 42), slice(42, 66)))
        self.assertEqual(figures.window_names(RELEASED), ("W1", "W2"))
        self.assertEqual(figures.steady_names(RELEASED), ("W2",))
        self.assertEqual(figures.windows(dict(economy=RELEASED)), (slice(18, 42), slice(42, 66)))
        # The first run's design at any length, or a stress month before five whole years, keeps its pair.
        for w in (Economy(n=4, burn_in=0, months=24, distress_start=3), Economy(n=4, distress_start=48)):
            self.assertFalse(figures.settled(w))
            self.assertEqual(figures.run_windows(w), (slice(w.burn_in + 12, w.burn_in + 36),
                                                     slice(w.burn_in + 36, w.burn_in + 60)))

    def test_second_run_windows(self):
        """The second run (burn-in 60, 300 months, the stress year at months 121 to 132): years 6 to 10, months 61 to
        120, and years 21 to 25, months 241 to 300, both read by the claim."""
        w = Economy(n=40, **available())
        self.assertTrue(figures.settled(w))
        first, second = figures.run_windows(w)
        self.assertEqual((first.start - 60 + 1, first.stop - 60), (61, 120))
        self.assertEqual((second.start - 60 + 1, second.stop - 60), (241, 300))
        self.assertEqual(figures.window_names(w), ("years_6_to_10", "years_21_to_25"))
        self.assertEqual(figures.steady_names(w), ("years_6_to_10", "years_21_to_25"))
        # Whole years: a stress year from month 127 reads the five years before month 121, and a run of 305 months
        # the last five whole years, 241 to 300.
        odd = Economy(n=4, burn_in=0, months=305, distress_start=126)
        self.assertEqual(figures.run_windows(odd), (slice(60, 120), slice(240, 300)))

    def test_no_settled_years_after_the_stress(self):
        """A long run whose last five whole years reach back into its stress year is refused."""
        with self.assertRaises(ValueError):
            figures.run_windows(Economy(n=4, burn_in=0, months=180, distress_start=120))
        self.assertEqual(figures.run_windows(Economy(n=4, burn_in=0, months=192, distress_start=120)),
                         (slice(60, 120), slice(132, 192)))


class TheConjunction(unittest.TestCase):
    def test_hand_made_values(self):
        """Holds in both: True only if True in each, False if False in either, otherwise not evaluated; a falsifier
        fires if it fires in either."""
        self.assertIs(figures.all_hold([True, True]), True)
        self.assertIs(figures.all_hold([True, False]), False)
        self.assertIs(figures.all_hold([None, False]), False)
        self.assertIs(figures.all_hold([True, None]), None)
        self.assertIs(figures.all_hold([True]), True)
        self.assertIs(figures.any_fires([False, True]), True)
        self.assertIs(figures.any_fires([None, True]), True)
        self.assertIs(figures.any_fires([False, None]), None)
        self.assertIs(figures.any_fires([False, False]), False)

    def test_hand_made_rows(self):
        """Stored rows of a long run: the windows and their positions come from the row, a first-run row reads W2."""
        self.assertEqual(steady_of({}), (("W2", 1),))
        self.assertEqual(names_of({}), ("W1", "W2"))
        row = dict(windows=["years_6_to_10", "years_21_to_25"])
        self.assertEqual(steady_of(row), (("years_6_to_10", 0), ("years_21_to_25", 1)))
        self.assertEqual(names_of(row), ("years_6_to_10", "years_21_to_25"))

    def test_households_in_both_windows(self):
        """Households hold all pool capital and P routes in every month, except that in one month of years 21 to 25
        households hold 80%: the first window holds, the second does not, and the seed does not count."""
        w = Economy(n=4, burn_in=0, months=132, distress_start=60)
        size = w.months
        series = dict(N=np.ones(size), owners_queued=np.zeros(size), owners_capital=np.ones(size),
                      p_value=np.ones(size))
        run = dict(series=series, economy=w)
        self.assertEqual(figures.window_names(w), ("years_1_to_5", "years_7_to_11"))
        held = households_pool(run, w)
        self.assertIs(held["counts"], True)
        series["owners_capital"][100] = 0.8
        held = households_pool(run, w)
        self.assertIs(held["households_hold_90_years_1_to_5"], True)
        self.assertIs(held["households_hold_90_years_7_to_11"], False)
        self.assertEqual(held["household_share_years_7_to_11_lowest"], 0.8)
        self.assertIs(held["counts"], False)
        # The first run's reading on the same series: W2 alone, months 37 to 60, which the low month is not in.
        held = households_pool(dict(series=series, economy=Economy(n=4, burn_in=0, months=132)), w)
        self.assertEqual(list(held), ["households_hold_90_W2", "households_hold_90_W2_all_capital",
                                      "household_share_W2_lowest", "household_share_W2_lowest_all_capital",
                                      "p_routes_W2", "counts"])
        self.assertIs(held["counts"], True)

    def test_capital_over_its_target_beside_the_90_reading(self):
        """In a run of the second run each window stores the pool's mean capital over its mean target: 0.6 over 0.8 is
        0.75 in the first window, and over a zero target None; a first-run store has no such key."""
        second = Economy(n=4, burn_in=0, months=132, distress_start=60, edge="conserved")
        size = second.months
        series = dict(N=np.full(size, 0.6), owners_queued=np.zeros(size), owners_capital=np.full(size, 0.6),
                      p_value=np.ones(size), target=np.full(size, 0.8))
        series["target"][72:] = 0.0
        held = households_pool(dict(series=series, economy=second), second)
        self.assertEqual(held["capital_over_target_years_1_to_5"], 0.75)
        self.assertIsNone(held["capital_over_target_years_7_to_11"])
        plain = Economy(n=4, burn_in=0, months=132, distress_start=60)
        self.assertFalse(any(key.startswith("capital_over") for key in households_pool(dict(series=series,
                                                                                          economy=plain), plain)))


def exit_run(filed, burn_in=60, months=300, paid=0.0, distress_start=120):
    """A pool arm's run as the persistence reader reads it, every test met, with one request to withdraw filed in month
    ``filed`` after launch and ``paid`` of it paid in time (none by default); the rest of the run has none."""
    total = burn_in + months
    economy = SimpleNamespace(burn_in=burn_in, months=months, distress_start=distress_start, distress_length=12,
                              self_financing="margin")
    series = {key: np.ones(total) for key in ("A", "pool_pt", "K", "pool_costs", "interest_collected",
                                              "new_pool_loans", "cash_to_lend", "N", "service", "owners_capital",
                                              "own_margin", "R")}
    series["A"][:] = 0.5
    series["write_off_rate"], series["arrears_share"] = np.zeros(total), np.zeros(total)
    started, in_time = np.zeros(total), np.zeros(total)
    started[burn_in + filed - 1], in_time[burn_in + filed - 1] = 1.0, paid
    return dict(series=series, economy=economy, exits=dict(started=started, in_time=in_time), arm="M1")


class WithdrawalsAgainstTheRunsEnd(unittest.TestCase):
    """The exit-payment test reads each request against the run's real end."""

    def test_a_request_never_paid_fails_wherever_it_is_filed(self):
        """300 months after launch: one request never paid, filed in month 118, 119 or 120 (paid in month 122 at the
        latest, inside the run), fails the owners-stay test in years 6 to 10 and so in the run; filed in month 298 it is
        due by month 300 and fails in years 21 to 25."""
        for filed in (118, 119, 120, 298):
            reading = figures.persistence(exit_run(filed), 0.5)
            self.assertIs(reading["P"]["P3"], False, filed)
        early = figures.persistence(exit_run(119), 0.5)["detail"]["by_window"]["years_6_to_10"]
        self.assertIs(early["P"]["P3"], False)
        self.assertEqual(early["detail"]["exit_requests_started_W2"], 1.0)
        self.assertEqual(early["detail"]["exit_requests_without_follow_up_W2"], 0.0)

    def test_a_request_in_the_runs_last_two_months_is_left_out(self):
        """Filed in month 299 or 300 a request cannot have been paid by the run's end (the pool pays two months after
        filing): it is left out of both sums and its value kept. Beside one request filed in month 250 and paid in
        full, the test reads True; alone, nothing is judged and it reads True too."""
        for filed in (299, 300):
            run = exit_run(filed)
            alone = figures.persistence(run, 0.5)["detail"]["by_window"]["years_21_to_25"]
            self.assertIs(alone["P"]["P3"], True, filed)
            self.assertEqual(alone["detail"]["exit_requests_without_follow_up_W2"], 1.0)
            self.assertEqual(alone["detail"]["exit_requests_started_W2"], 0.0)
            run["exits"]["started"][60 + 249] = run["exits"]["in_time"][60 + 249] = 2.0
            beside = figures.persistence(run, 0.5)["detail"]["by_window"]["years_21_to_25"]
            self.assertIs(beside["P"]["P3"], True, filed)
            self.assertEqual(beside["detail"]["exit_paid_within_two_months_W2"], 1.0)

    def test_the_released_reading_is_as_before(self):
        """In the first run W2 ends with the run: a request filed in its last two months is left out, so the test holds
        with no other request, and one filed in month 58 is late."""
        for filed, expected in ((59, True), (60, True), (58, False)):
            reading = figures.persistence(exit_run(filed, burn_in=6, months=60, distress_start=24), 0.5)
            self.assertIs(reading["P"]["P3"], expected, filed)
            self.assertEqual(reading["detail"]["exit_requests_without_follow_up_W2"], 0.0)


class ATinyLongRun(unittest.TestCase):
    """Three seeds of one cell of a long run, at 100 people over 36 months after a burn-in of 2 with the stress year at
    months 13 to 24, the window shortened to one year: years 1 and 3 are its two windows."""

    @classmethod
    def setUpClass(cls):
        cls.patch = mock.patch.object(figures, "WINDOW_YEARS", 1)
        cls.patch.start()
        cls.w = Economy(n=100, burn_in=2, months=36, distress_start=12, distress_length=12, crypto_share=0.0)
        cls.jobs = [runner.job((0.044, 0.6, 0.0, seed, 100, False), cls.w) for seed in runner.SEEDS["development"]]
        cls.names = ("years_1_to_1", "years_3_to_3")

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def test_windows(self):
        self.assertEqual(figures.window_names(self.w), self.names)
        self.assertEqual(figures.run_windows(self.w), (slice(2, 14), slice(26, 38)))

    def test_values_by_window(self):
        """Every reading by window is stored for each window under its name, and none under W1 or W2."""
        for job in self.jobs:
            self.assertEqual(set(job["S0"]["by_window"]), set(self.names))
            for arm, row in job["arms"].items():
                keys = set(row)
                for name in self.names:
                    self.assertIn(f"A_{name}", keys)
                    self.assertIn(name, row["by_window"])
                self.assertNotIn("A_W1", keys)
                self.assertFalse([key for key in keys if key.endswith("_W2")], arm)
                if arm == "M0":
                    continue
                self.assertEqual(row["windows"], list(self.names))
                for name in self.names:
                    self.assertIn(f"pays_its_way_{name}", row)
                    self.assertIn(f"households_hold_90_{name}", row["households"])
                    self.assertIn(f"s_monopoly_{name}", row["demurrage"])
                    self.assertIn(f"capital_{name}_usd", row["owners"])
                    self.assertIn(name, row["owners"]["net_pct"])
                    self.assertIn(name, row["owners_excess"])
                    self.assertEqual(set(row["by_window"][name]["P"]), {"P1", "P2", "P3", "P4", "P5"})
                self.assertEqual(len(row["own_margin_usd_a_year"]), 2)

    def test_verdicts_are_conjunctions(self):
        """Each test holds only where it holds in both windows' readings, each falsifier fires where it fires in
        either, V1 is worse where it is worse in either, and the seed counts only where it counts in both."""
        for job in self.jobs:
            for arm in ("U", "M1", "M2"):
                row = job["arms"][arm]
                readings = [row["by_window"][name] for name in self.names]
                for key in row["P"]:
                    self.assertIs(row["P"][key], figures.all_hold(r["P"][key] for r in readings))
                for key in row["X"]:
                    self.assertIs(row["X"][key], figures.any_fires(r["X"][key] for r in readings))
                self.assertIs(row["V1_worse"], any(r["V1_worse"] for r in readings))
                for name, reading in zip(self.names, readings):
                    self.assertIs(row[f"pays_its_way_{name}"], reading["P"]["P4"])
                held = row["households"]
                self.assertIs(held["counts"], figures.all_hold(
                    held[f"households_hold_90_{name}"] and held[f"p_routes_{name}"] for name in self.names))

    def test_decided_cell_and_claim(self):
        """A cell and the claim read both windows: participation, owners' excess, the margin by seed and the
        households' shares by window, V4 by window, and clause (a)'s margin and joint test in each."""
        selection = dict(r_out=(0.044,), a0=(0.6,), distress=(0.0,))
        cells, _ = decide_cells(self.jobs, selection, self.w, 100)
        stats = runner.claim_statistics(cells, self.jobs, self.w)
        self.assertIn("M1", stats["bonferroni"])
        m1 = cells[0]["M1"]
        for name in self.names:
            self.assertIn(f"A_{name}", m1)
            self.assertIn(name, m1["owners_excess_pct"])
            self.assertIn(f"own_margin_{name}_by_seed", m1)
            self.assertIn(f"households_hold_90_{name}_share", m1)
            self.assertIn(name, m1["by_window"])
            self.assertIn(name, m1["better_than_M0"]["V4"]["by_window"])
            self.assertIn(f"own_margin_{name}", m1["claim"]["a"]["at_95"])
        self.assertIn("S0_by_window", cells[0])
        v4 = m1["better_than_M0"]["V4"]
        self.assertIs(v4["shown_worse"], any(block["shown_worse"] for block in v4["by_window"].values()))

    def test_record_names_the_windows(self):
        record = run_record(self.w, "development", 3, dict(r_out=(0.044,), a0=(0.6,), distress=(0.0,)))
        self.assertEqual(record["windows"], {"years_1_to_1": "months 1 to 12 after launch",
                                             "years_3_to_3": "months 25 to 36 after launch"})


class TheReleasedRun(unittest.TestCase):
    @unittest.skipUnless((STORE / "cells.json.gz").exists(), "the stored development map is not here")
    def test_the_development_map_reads_as_stored(self):
        """The stored development map's rows read as the first run's (W2), and its cell at 4.4%, launch 0.6 and no
        distress, evaluated again from its stored jobs, keeps every stored value of the readings by window and the
        shares read on W2."""
        with gzip.open(STORE / "summary.json.gz", "rt", encoding="utf-8") as source:
            summary = json.load(source)
        with gzip.open(STORE / "cells.json.gz", "rt", encoding="utf-8") as source:
            stored = json.load(source)
        economy = summary["economy"]
        w = SimpleNamespace(**{**economy, "m0_rates": economy.get("m0_rates", "observed"),
                               "lender_income_recirculated": bool(economy.get("lender_income_recirculated"))})
        self.assertFalse(figures.settled(w))
        # The cells without distress: cells.json keeps no measures, which a distress cell's paired reading reads.
        jobs = [j for j in stored["jobs"] if (j["r_out"], j["a0"], j["distress"]) == (0.044, 0.6, 0.0)]
        row = jobs[0]["arms"]["M1"]
        self.assertEqual(steady_of(row), (("W2", 1),))
        cells, _ = decide_cells(jobs, dict(r_out=(0.044,), a0=(0.6,), distress=(0.0,)), w, economy["n"])
        before = {(c["r_out"], c["a0"], c["distress"]): c for c in summary["cells"]}
        keys = ("A_W1", "A_W2", "owners_excess_pct", "own_margin_usd_a_year", "own_margin_W2_by_seed",
                "own_margin_held_months_W2_by_seed", "joint_W2_by_seed", "pays_its_way_share",
                "households_hold_90_W2_share", "households_hold_90_W2_all_capital_share", "p_routes_W2_share",
                "counts_share", "c_pct", "N", "persistent_share")
        for cell in cells:
            old = before[(cell["r_out"], cell["a0"], cell["distress"])]
            for arm in ("U", "M1", "M2"):
                for key in keys:
                    self.assertEqual(json.loads(json.dumps(cell[arm][key])), old[arm][key], (arm, key))
                self.assertNotIn("by_window", cell[arm])
            self.assertNotIn("S0_by_window", cell)

    def test_released_labels(self):
        """The first run's distress labels and note, word for word, and no windows record."""
        self.assertEqual(distress_note(RELEASED), RELEASED_NOTE)
        record = run_record(RELEASED, "development", 3, dict(r_out=(0.044,), a0=(0.6,), distress=(0.0,)))
        self.assertEqual(record["distress_labels"]["note"], RELEASED_NOTE)
        self.assertIn("jobs_without_wage_month_36_pct", record["distress_labels"])
        self.assertNotIn("windows", record)

    def test_second_run_labels(self):
        """The second run's note names its own stress: the payers still owe the wages of the extra layoffs to the
        outside, and the conserved edge pays them back to all households with everything else that crossed it;
        purchases are dropped and lines are cut for 120 months; the hand labels are read at month 132. The side
        reading in which the payers keep the wages says so, and names no wage among what is paid back."""
        w = Economy(n=40, **available())
        note = distress_note(w)
        self.assertIn("month 132", note)
        self.assertIn("leave the household economy", note)
        self.assertNotIn("keep their wages", note)
        self.assertIn("1.74%", note)
        self.assertIn("the extra layoffs' wages among it, is paid back to them", note)
        self.assertIn(f"restored {w.card_cut_months} months after the cut", note)
        kept = distress_note(Economy(n=40, **available("wages_kept")))
        self.assertIn("keep their wages", kept)
        self.assertNotIn("leave the household economy", kept)
        self.assertIn("to inflation is paid back to them", kept)


class TheRunnerPlumbing(unittest.TestCase):
    def args(self, start):
        return SimpleNamespace(custody_cost=None, owners_spread=None, distress_start=start, fixed_cost="central",
                               r_out=[0.044], seeds="side")

    def test_distress_start_bound(self):
        """--distress-start is bounded by the run's own months less the stress year's length: 48 in the first run,
        288 in a run of 300 months."""
        self.assertIsNone(runner.side_check_refused(self.args(48)))
        self.assertIn("from 0 to 48", runner.side_check_refused(self.args(49)))
        self.assertIn("from 0 to 48", runner.side_check_refused(self.args(49), RELEASED))
        self.assertIsNone(runner.side_check_refused(self.args(200), SECOND))
        self.assertIn("from 0 to 288", runner.side_check_refused(self.args(289), SECOND))

    def test_worker_memory_text(self):
        self.assertIn("about 1.0 GB", runner.options().format_help().replace("\n", " ").replace("  ", " "))


class TheFiguresOfAMap(unittest.TestCase):
    """The map's figures read the last window from an evaluated cell, which carries its windows as the names of its
    window means and no list of them."""
    RELEASED_ROW = dict(A_W1=0.4, A_W2=0.5)
    LONG_ROW = dict(A_years_6_to_10=0.6, A_years_21_to_25=0.7,
                    by_window=dict(years_6_to_10=dict(), years_21_to_25=dict()))

    def test_the_last_window_of_a_decided_cell(self):
        self.assertEqual(map_figures.window_names(self.RELEASED_ROW), ("W1", "W2"))
        self.assertEqual(map_figures.late(self.RELEASED_ROW, "A"), 0.5)
        self.assertEqual(map_figures.late_label([dict(M1=self.RELEASED_ROW)]), "years 4 and 5")
        self.assertEqual(map_figures.window_names(self.LONG_ROW), ("years_6_to_10", "years_21_to_25"))
        self.assertEqual(map_figures.late(self.LONG_ROW, "A"), 0.7)
        self.assertEqual(map_figures.late_label([dict(S0_failures_pct=2.4), dict(M1=self.LONG_ROW)]), "years 21 to 25")
        # A seed's row lists its windows, and the list is read first.
        self.assertEqual(map_figures.window_names(dict(self.LONG_ROW, windows=["a", "b"])), ("a", "b"))

    def test_what_demurrage_adds_is_signed_by_row(self):
        """M1 less U by default; with sign -1 U less M1, so a lower bridge price reads above zero.

        Example: a bridge at 2% a year with demurrage and 6.5% without reads -4.5 as M1 less U and +4.5 as the
        price cut."""
        cell = dict(M1=dict(r_b_pct=2.0, N=0.25, liquidity=dict(pool_bridges_usd_a_year=[0.0, 4830.0])),
                    U=dict(r_b_pct=6.5, N=0.0, liquidity=dict(pool_bridges_usd_a_year=[0.0, 0.0])))
        grid = ((0.044,), (0.6,), {(0.044, 0.6, 0.0): cell})
        read = lambda c, arm: c[arm]["r_b_pct"]
        self.assertEqual(map_figures.effect_grid(read, 0.0, grid)[0, 0], -4.5)
        self.assertEqual(map_figures.effect_grid(read, 0.0, grid, -1)[0, 0], 4.5)
        # $4,830 a person a year lent on a quarter of a month's spending of capital ($1,610) is 3 times a year;
        # with no capital there is no ratio.
        self.assertAlmostEqual(map_figures.bridges_per_capital(cell, "M1"), 3.0)
        self.assertTrue(np.isnan(map_figures.bridges_per_capital(cell, "U")))
        # In a run that conserves money the mean gain against S0 is near zero (revaluation, the stock owed across
        # the edge and what the payout keeps back) and is not drawn.
        self.assertIn(map_figures.gain_against_s0, [row[0] for row in map_figures.EFFECTS])
        self.assertNotIn(map_figures.gain_against_s0, [row[0] for row in map_figures.EFFECTS_CONSERVED])


if __name__ == "__main__":
    unittest.main()

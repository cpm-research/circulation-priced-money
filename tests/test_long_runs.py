"""Runs of any length and the burn-in computed once, at small scale.

What is covered
---------------
* Runs of any length: a small world run for 300 months after a burn-in of 60, in every arm, keeps the conservation
  identity every month; every record follows the run's length (one row a month, one year row a year after launch for
  MicroVelocity and the money's ages, one loan-year band a year for the owners' record by loan year, the loan's own
  years of life still five bands); the distress year falls 24 months after launch; and the job's readings
  (``assemble``) are made from the five runs. A run of 60 months or less keeps its five loan-year bands.
* The burn-in computed once: for every arm a run resumed from the arm's state at launch (``launch_state``,
  ``resume``) equals the direct run bit for bit in every stored record, at two launch levels and two distress
  levels from one state, after a round trip through pickle, and through the runner's fork of the distress year; the
  state is left as it was; a state opened with other Inputs, another Economy or past launch is refused; and the
  runner's tasks with the shared states give exactly the jobs ``job`` gives.
"""
import pickle
import sys
import unittest
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cpm_abm.core_model import Inputs  # noqa: E402
from cpm_abm.economy_abm import (COINAGE_RECORDS, LOAN_YEARS, VELOCITY_RECORDS, Economy, _World,  # noqa: E402
                                 launch_state, resume, simulate)
from cpm_abm.experiment.jobs import assemble, forked, job, run_tasks, same  # noqa: E402
from cpm_abm.experiment.store import _counts_text  # noqa: E402

ARMS = ("S0", "M0", "U", "M1", "M2")
# A small world for 300 months after a burn-in of 60. Its cushion is twelve months of spending, not the 0.6 of the
# base: the household economy pays the outside fees and interest with no income from it, so over 30 years a small
# world's payers run out of money and the late wages among them leave a day's settlement without a fixed point; with
# the base cushion the test would read that drift rather than the calendar.
LONG = Economy(n=20, burn_in=60, months=300, distress=0.02, buffer_months=12.0)
# A small world whose distress year comes early, for the resumed runs.
SHORT = Economy(n=40, burn_in=4, months=8, distress_start=2, distress_length=3, shocks=True)


class LongRunTest(unittest.TestCase):
    """One small world run for 300 months after a burn-in of 60 in every arm (each run well under a minute)."""

    @classmethod
    def setUpClass(cls):
        cls.runs = {arm: simulate(Inputs(), 0.3, LONG, arm) for arm in ARMS}

    def test_money_is_conserved_every_month_in_every_arm(self):
        for arm, run in self.runs.items():
            series = run["series"]
            self.assertEqual(series["wealth_change"].size, LONG.burn_in + LONG.months, arm)
            np.testing.assert_allclose(series["wealth_change"],
                                       series["external"] + series["valuation"] + series["inflation"], atol=1e-12,
                                       err_msg=arm)
            # Net wealth after each month, summed over people, moves by the month's change.
            np.testing.assert_allclose(np.diff(run["wealth"].mean(axis=1)), series["wealth_change"], atol=1e-12,
                                       err_msg=arm)

    def test_every_record_follows_the_run_length(self):
        total, years = LONG.burn_in + LONG.months, LONG.months // 12
        for arm, run in self.runs.items():
            self.assertEqual(run["wealth"].shape, (total + 1, LONG.n), arm)
            for key in ("participant", "owner", "borrower", "receipts", "fees", "failed", "transfers", "owned",
                        "crossings", "buffers"):
                self.assertEqual(run[key].shape, (total, LONG.n), (arm, key))
            for group in ("purchases", "credit", "failure_counts", "ewa"):
                self.assertTrue(all(value.shape == (total, LONG.n) for value in run[group].values()), (arm, group))
            self.assertTrue(all(run["velocity"][key].shape == (years, LONG.n) for key in VELOCITY_RECORDS), arm)
            self.assertTrue(all(run["coinage"][key].shape[:3] == (2, years, LONG.n) for key in COINAGE_RECORDS), arm)
            self.assertEqual(run["coinage"]["residual"].shape, (total,), arm)
            self.assertEqual(run["exits"]["started"].shape, (total,), arm)
            # The loan's own years of life keep their five bands; the loan years (the year after launch a loan was
            # made) have one band a year.
            self.assertEqual(run["loan_age"]["exposure"].shape, (total, LOAN_YEARS), arm)
            self.assertEqual(run["vintage"]["income"].shape, (total, 2, years), arm)
            self.assertEqual(sorted(run["payments"]), [LONG.burn_in, total - 1], arm)

    def test_the_late_years_are_recorded(self):
        """The records past month 60 after launch are filled: payments in every year after launch, and in the pool arms
        pool loans made in a loan year past the fifth, which a 60-month run's last band would have taken."""
        for arm, run in self.runs.items():
            spent = run["velocity"]["outflow"].sum(axis=1)
            self.assertTrue(bool((spent > 0).all()), arm)
        for arm in ("U", "M1", "M2"):
            exposure = self.runs[arm]["vintage"]["exposure"].sum(axis=0)   # (product, loan year)
            self.assertGreater(float(exposure[:, LOAN_YEARS:].sum()), 0.0, arm)

    def test_the_distress_year_falls_after_the_burn_in(self):
        """Extra layoffs send wages outside in the distress year alone: months 85 to 96 of the run, 25 to 36 after a
        launch at month 60."""
        out = self.runs["S0"]["series"]["wages_out"]
        first = LONG.burn_in + LONG.distress_start
        self.assertGreater(float(out[first:first + LONG.distress_length].sum()), 0.0)
        self.assertEqual(float(out[:first].sum()), 0.0)

    def test_the_jobs_readings_are_made_from_long_runs(self):
        made = assemble((0.044, 0.3, LONG.distress, LONG.seed, LONG.n, False), self.runs, LONG)
        self.assertEqual(set(made["arms"]), set(ARMS[1:]))
        self.assertEqual(set(made["monthly"]), set(ARMS))
        self.assertEqual(len(made["monthly"]["M1"]["A"]), LONG.months)

    def test_a_run_of_sixty_months_or_less_keeps_five_loan_years(self):
        for months in (6, 60):
            self.assertEqual(_World(Inputs(), 0.3, replace(LONG, months=months), "M1").vintage_years, LOAN_YEARS)
        self.assertEqual(_World(Inputs(), 0.3, replace(LONG, months=61), "M1").vintage_years, 6)


class SharedBurnInTest(unittest.TestCase):
    """A run resumed from its arm's state at launch equals the direct run bit for bit."""

    def test_a_resumed_run_equals_the_direct_run_in_every_arm(self):
        for arm in ARMS:
            direct = {(a0, level): simulate(Inputs(), a0, replace(SHORT, distress=level), arm)
                      for a0 in (0.05, 0.6) for level in (0.0, 0.2)}
            # One state, opened at the highest level, serves both launch levels and both distress levels.
            state = launch_state(Inputs(), replace(SHORT, distress=0.2), arm)
            before = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
            for (a0, level), run in direct.items():
                self.assertTrue(same(resume(state, Inputs(), a0, replace(SHORT, distress=level)).run(), run),
                                (arm, a0, level))
            # The state served every run and is as it was; read back from pickle it starts a run in place.
            self.assertEqual(pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL), before, arm)
            self.assertTrue(same(resume(pickle.loads(before), Inputs(), 0.05, SHORT, keep=False).run(),
                                 direct[0.05, 0.0]), arm)
            # The runner's fork of the distress year from a state at launch.
            got = forked(Inputs(), 0.6, SHORT, arm, (0.0, 0.2), state)
            for level in (0.0, 0.2):
                self.assertTrue(same(got[level], direct[0.6, level]), (arm, "forked", level))

    def test_a_state_is_refused_for_another_world(self):
        state = launch_state(Inputs(), SHORT, "M1")
        for economy in (replace(SHORT, seed=SHORT.seed + 1), replace(SHORT, months=SHORT.months + 1),
                        replace(SHORT, burn_in=SHORT.burn_in + 1), replace(SHORT, lender_income_recirculated=True),
                        replace(SHORT, n=SHORT.n + 1), replace(SHORT, distress_start=SHORT.distress_start + 1)):
            with self.assertRaises(ValueError):
                resume(state, Inputs(), 0.3, economy)
        with self.assertRaises(ValueError):
            resume(state, replace(Inputs(), rho_H=Inputs().rho_H * (1 + 1e-15)), 0.3, SHORT)
        with self.assertRaises(ValueError):
            forked(Inputs(), 0.3, SHORT, "M2", (0.0,), state)   # a state of another arm
        past = resume(state, Inputs(), 0.3, SHORT)
        past.month(SHORT.burn_in)
        with self.assertRaises(ValueError):
            resume(past, Inputs(), 0.3, SHORT)

    def test_the_runner_with_shared_states_gives_the_jobs_job_gives(self):
        template = Economy(n=40, burn_in=3, months=6, distress_start=1, distress_length=3)
        tasks = [(0.044, a0, level, 20261021, template.n, False) for a0 in (0.05, 0.6) for level in (0.0, 0.02)]
        with warnings.catch_warnings():
            # A six-month run's second window, months 37 to 60 after launch, is empty, and its means say so.
            warnings.simplefilter("ignore", RuntimeWarning)
            pairs = list(zip(tasks, run_tasks(tasks, template, workers=2)))
            wanted = [job(task, template) for task in tasks]
        for (task, got), want in zip(pairs, wanted):
            self.assertTrue(same({k: v for k, v in got.items() if k != "failure_counts"},
                                 {k: v for k, v in want.items() if k != "failure_counts"}), task)
            self.assertEqual(_counts_text(got["failure_counts"]), _counts_text(want["failure_counts"]), task)


if __name__ == "__main__":
    unittest.main()

"""A job's memory: the same stored records with one whole run held at a time.

What is covered
---------------
* The records are the same: on a small world with the second run's settings (the conserved edge, reserved standby,
  two months of receipts, purchases of fixed size at random, each holder's own statement date, the slowdown's kept
  wages and dropped purchases), at a distress level of zero and one above it, on a development seed (whose records
  keep fees and counts by payer) and on another, ``job`` and the runner's tasks (``run_tasks``: S0 shared through the
  cache, each arm from its state at launch, each level from its prefix read back from disk) give exactly the job
  that reading every record from the five runs held together gives, key by key and bit for bit.
* One run at a time: ``assemble`` asks for each run only once the run before it is gone, ``levels_of`` keeps no world
  between levels and gives what ``forked`` gives, and a record let go of S0, M0 or U raises if anything reads it.
"""
import sys
import unittest
import warnings
import weakref
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cpm_abm.economy_abm import _World, Economy, simulate  # noqa: E402
from cpm_abm.experiment.accounts import (by_chronic, by_class, by_quintile, card_bridging, cash_check,  # noqa: E402
                                         ewa_report, failure_report, liquidity, measures, monthly, real_part,
                                         transfers)
from cpm_abm.experiment.gains import arm_row, payout_by_group  # noqa: E402
from cpm_abm.experiment.notes import conserves_money  # noqa: E402
from cpm_abm.experiment.grid import SEEDS, cell_inputs  # noqa: E402
from cpm_abm.experiment.jobs import _kept, assemble, forked, job, levels_of, run_tasks, same  # noqa: E402
from cpm_abm.experiment.store import _counts_text  # noqa: E402
from run_economy_figures import windows  # noqa: E402

ARMS = ("S0", "M0", "U", "M1", "M2")
# A few hundred people, a burn-in of 6 and 30 months after launch, the distress year 12 months after launch, with the
# second run's settings.
SMALL = Economy(n=200, burn_in=6, months=30, distress_start=12, edge="conserved", standby="reserved",
                receipts_window=2, purchases="poisson_size", statement_dates="own", distress_wages="kept",
                distress_purchases=0.0174)
LEVELS = (0.0, 0.02)
SEED_SET = (SEEDS["development"][0], 20261101)


def whole(args, runs, template):
    """Every record of a job read from its five runs held together, in the order of the keys the stores keep: the
    reading ``assemble`` makes one run at a time."""
    rate, a0, distress, seed, n, recirculated = args
    w = replace(template, seed=seed, distress=distress, lender_income_recirculated=recirculated)
    rows = {arm: arm_row(runs[arm], runs["S0"], runs["M0"], a0, w, runs["U"]) for arm in ARMS[1:]}
    after = slice(w.burn_in, w.burn_in + w.months)
    s0, (_, w2) = runs["S0"], windows(runs["S0"])
    by_payer = seed in SEEDS["development"]
    failures = {arm: failure_report(runs[arm], w, by_payer) for arm in ARMS}
    if by_payer:
        failures["S0"]["buffers"] = np.round(s0["buffers"][after], 6).tolist()
    banks = dict(failures_pct=float(s0["series"]["failure_share"][w2].mean() * 100),
                 merchant_fees_pct=float(s0["series"]["merchant_fees"][w2].mean() * 100),
                 real_part=real_part(s0, w), transfers=transfers(s0, w), cash=cash_check(s0, w),
                 earned_wage=ewa_report(s0, w), chronic=by_chronic(s0, w), card_bridging=card_bridging(s0, w),
                 liquidity=liquidity(s0, w), by_class=by_class(s0, w), **by_quintile(s0, w))
    if conserves_money(w):
        banks["payout_by_group"] = payout_by_group(s0, s0, w)   # banks' own table of who pays and who receives
    return dict(r_out=rate, a0=a0, distress=distress, seed=seed, recirculated=recirculated, arms=rows, S0=banks,
                measures={arm: measures(runs[arm], w) for arm in ARMS},
                monthly={arm: monthly(runs[arm], w) for arm in ARMS},
                failure_counts=failures)


class Run(dict):
    """A run that can be watched (``weakref``), to see when it is let go."""


class SameRecordsTest(unittest.TestCase):
    """The memory-lean job gives the records of the five runs held together, bit for bit."""

    @classmethod
    def setUpClass(cls):
        cls.tasks = [(0.044, 0.6, level, seed, SMALL.n, False) for seed in SEED_SET for level in LEVELS]
        with warnings.catch_warnings():
            # The second window, months 37 to 60 after launch, is empty in a 30-month run, and its means say so.
            warnings.simplefilter("ignore", RuntimeWarning)
            cls.wanted = [whole(task, {arm: simulate(cell_inputs(task[0]), task[1],
                                                     replace(SMALL, seed=task[3], distress=task[2]), arm)
                                       for arm in ARMS}, SMALL) for task in cls.tasks]
            cls.jobs = [job(task, SMALL) for task in cls.tasks]
            cls.ran = run_tasks(cls.tasks, SMALL, workers=2)

    def test_job_gives_the_records_of_the_runs_held_together(self):
        for task, got, want in zip(self.tasks, self.jobs, self.wanted):
            self.assertEqual(list(got), list(want), task)
            for key in want:
                self.assertTrue(same(got[key], want[key]), (task, key))

    def test_the_runners_tasks_give_the_same_records(self):
        for task, got, want in zip(self.tasks, self.ran, self.wanted):
            self.assertEqual(list(got), list(want), task)
            for key in want:
                if key != "failure_counts":
                    self.assertTrue(same(got[key], want[key]), (task, key))
            self.assertEqual(_counts_text(got["failure_counts"]), _counts_text(want["failure_counts"]), task)

    def test_a_level_above_zero_and_the_payer_records_are_covered(self):
        self.assertTrue(any(task[2] > 0 for task in self.tasks))
        self.assertTrue(any("buffers" in want["failure_counts"]["S0"] for want in self.wanted))
        self.assertTrue(any("buffers" not in want["failure_counts"]["S0"] for want in self.wanted))


class OneRunAtATimeTest(unittest.TestCase):
    """A job holds one whole run at a time."""

    def test_each_run_is_let_go_before_the_next_is_asked_for(self):
        w = replace(SMALL, n=60, seed=SEED_SET[1], distress=LEVELS[1])
        runs = {arm: simulate(cell_inputs(0.044), 0.6, w, arm) for arm in ARMS}
        watched, alive = [], []

        def given():
            for arm in ARMS:
                alive.append([ref() is not None for ref in watched])
                run = Run(runs.pop(arm))
                watched.append(weakref.ref(run))
                yield arm, run
                del run

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            assemble((0.044, 0.6, LEVELS[1], SEED_SET[1], w.n, False), given(), SMALL)
        self.assertEqual(alive, [[False] * k for k in range(len(ARMS))])

    def test_runs_in_another_order_are_refused(self):
        w = replace(SMALL, n=60, seed=SEED_SET[1])
        given = iter([("M0", simulate(cell_inputs(0.044), 0.6, w, "M0"))])
        with self.assertRaises(ValueError):
            assemble((0.044, 0.6, 0.0, SEED_SET[1], w.n, False), given, SMALL)

    def test_levels_one_at_a_time_give_the_fork_and_keep_no_world(self):
        w = replace(SMALL, n=60, seed=SEED_SET[1])
        for arm in ("S0", "M1"):
            wanted = forked(cell_inputs(0.044), 0.6, w, arm, LEVELS)
            runs = levels_of(cell_inputs(0.044), 0.6, w, arm, LEVELS)
            for level in LEVELS:
                got, run = next(runs)
                self.assertEqual(got, level)
                self.assertTrue(same(run, wanted[level]), (arm, level))
                held = [value for value in runs.gi_frame.f_locals.values()
                        if isinstance(value, _World) or (isinstance(value, list) and value)]
                self.assertEqual(held, [], (arm, level))
            with self.assertRaises(StopIteration):
                next(runs)

    def test_a_record_let_go_raises_when_read(self):
        w = replace(SMALL, n=60, seed=SEED_SET[1])
        kept = _kept(simulate(cell_inputs(0.044), 0.6, w, "M0"))
        self.assertEqual(kept["arm"], "M0")
        for key in ("failure_counts", "fees", "coinage"):
            with self.assertRaises(KeyError):
                kept[key]
            with self.assertRaises(KeyError):
                kept.get(key)
        with self.assertRaises(KeyError):
            kept["credit"]["term_pool"]
        self.assertIsNone(kept.get("no such record"))


if __name__ == "__main__":
    unittest.main()

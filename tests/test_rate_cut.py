"""The rate cut: finer outside rates beside the grid (cpm_abm.experiment.notes.SIDE_RATES), run on the exploratory
seeds after the confirmation was read. A run of the grid's own rates is selected, counted, recorded and joined into a
region exactly as before;
a run of the cut covers its own 105 cells, with no extra accounting job, and its region joins along its own rates.
Nothing is simulated here."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_confirmation as driver  # noqa: E402
from cpm_abm.experiment.claims import _region_slice  # noqa: E402
from cpm_abm.experiment.grid import CONFIRMATION_RESERVED, RETIRED_SEEDS, SEEDS, selected, tasks_for  # noqa: E402
from cpm_abm.experiment.notes import A0S, DISTRESS, GRID, RATES, SIDE_RATES, rate_axis  # noqa: E402

CUT = ["--r_out", *map(str, SIDE_RATES)]


def passing_map(places):
    """Cells with no distress at ``places`` (rate, launch), each passing the claim and not underpowered."""
    return {(rate, a0, 0.0): dict(M1=dict(claim=dict(all=True, underpowered=False, in_region=False)))
            for rate, a0 in places}


class RateCutTest(unittest.TestCase):
    def test_the_cut_lies_between_two_grid_rates_and_is_no_part_of_the_grid(self):
        self.assertEqual(SIDE_RATES, (0.025, 0.03, 0.035))
        self.assertTrue(all(RATES[0] < rate < RATES[1] for rate in SIDE_RATES))
        self.assertEqual(GRID["r_out"], (0.02, 0.044, 0.06))
        self.assertEqual(selected(), GRID)                           # the default is still the grid and nothing else

    def test_the_rates_a_run_is_read_along(self):
        # A run of the grid, whole or in part, is read along the grid's three rates; a run of the cut along its own;
        # a run of both along all it covers, in order.
        self.assertEqual(rate_axis(RATES), RATES)
        self.assertEqual(rate_axis((0.044,)), RATES)
        self.assertEqual(rate_axis(SIDE_RATES), SIDE_RATES)
        self.assertEqual(rate_axis((0.03, 0.02, 0.044)), (0.02, 0.03, 0.044))

    def test_a_run_of_the_cut_is_105_cells_a_seed_with_no_extra_job(self):
        cut = selected(r_out=SIDE_RATES)
        self.assertEqual(cut, dict(r_out=SIDE_RATES, a0=A0S, distress=DISTRESS))
        tasks = tasks_for((11, 12), 4000, cut)
        self.assertEqual(len(tasks), 2 * 3 * 7 * 5)
        self.assertEqual({task[0] for task in tasks}, set(SIDE_RATES))
        self.assertFalse(any(task[5] for task in tasks))              # the accounting job belongs to the full grid
        self.assertEqual(len(tasks_for((11, 12), 4000)), 2 * 106)     # the grid's own count is as it was
        with self.assertRaises(ValueError):
            selected(r_out=(0.04,))                                   # a rate that is neither is refused

    def test_the_exploratory_seeds_are_a_block_of_their_own(self):
        # Seeds from 20261601 upward, as the plan requires of any run made after the confirmation is read: 30 of
        # them, touching no other set, no retired block and no seed the confirmation block reserves.
        seeds = SEEDS["exploratory"]
        self.assertEqual((seeds[0], seeds[-1], len(seeds)), (20261601, 20261630, 30))
        others = set(CONFIRMATION_RESERVED) | {s for block in RETIRED_SEEDS for s in block}
        others |= {s for name, block in SEEDS.items() if name != "exploratory" for s in block}
        self.assertFalse(set(seeds) & others)

    def test_the_driver_runs_the_cut_on_the_exploratory_seeds_one_seed_a_part(self):
        args, parts = driver.plan("exploratory", CUT)
        self.assertEqual((len(parts), {len(tasks) for _, tasks in parts}), (30, {105}))
        self.assertEqual((parts[0][0], parts[-1][0]), (20261601, 20261630))
        # The registered map's plan is as it was. The confirmation seeds never see the cut, the stress boundary's
        # levels or a switch, and the exploratory seeds see no switch.
        args, parts = driver.plan("confirmation", [])
        self.assertEqual((len(parts), {len(tasks) for _, tasks in parts}), (30, {106}))
        self.assertEqual((parts[0][0], parts[-1][0]), (20261401, 20261430))
        for seeds, refused in (("confirmation", CUT), ("confirmation", ["--distress", "0.0", "0.016"]),
                               ("exploratory", [*CUT, "--joining", "threshold"])):
            with self.assertRaises(SystemExit):
                driver.plan(seeds, refused)

    def test_a_region_joins_along_the_runs_own_rates(self):
        # The cut: 2.5% and 3% at one launch level share an edge; 3.5% at the next launch level touches only a corner.
        mine = passing_map([(0.025, 0.05), (0.03, 0.05), (0.035, 0.1)])
        found = _region_slice("M1", 0.0, mine, mine)
        self.assertEqual(found["region"], [[0.025, 0.05], [0.03, 0.05]])
        self.assertEqual(found["passing"], [[0.025, 0.05], [0.03, 0.05], [0.035, 0.1]])
        self.assertTrue(mine[(0.025, 0.05, 0.0)]["M1"]["claim"]["in_region"])
        self.assertFalse(mine[(0.035, 0.1, 0.0)]["M1"]["claim"]["in_region"])
        # The grid as before: 2% and 4.4% are neighbours, 2% and 6% are not, whichever rates a run selects.
        grid = passing_map([(0.02, 0.05), (0.044, 0.05)])
        self.assertEqual(_region_slice("M1", 0.0, grid, grid)["region"], [[0.02, 0.05], [0.044, 0.05]])
        apart = passing_map([(0.02, 0.05), (0.06, 0.05)])
        self.assertEqual(len(_region_slice("M1", 0.0, apart, apart)["region"]), 1)


if __name__ == "__main__":
    unittest.main()

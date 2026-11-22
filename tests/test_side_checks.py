"""The exploratory side checks made after the confirmation was read: the fixed cost at multiples of its sourced
level, the custody cost, the owners' spread, the shock date and two low outside rates. Each is a setting the engine
already reads; a run that names none builds exactly what it built before; and they run on the side seeds only.
Nothing is simulated here."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_confirmation as driver  # noqa: E402
import run_economy_population as runner  # noqa: E402
from cpm_abm.economy_abm import Economy  # noqa: E402
from cpm_abm.experiment.grid import CONFIRMATION_RESERVED, RETIRED_SEEDS, SEEDS, cell_inputs, selected  # noqa: E402
from cpm_abm.experiment.notes import GRID, LOW_RATES, RATES, rate_axis  # noqa: E402
from run_economy_figures import FIXED_COST, FIXED_COST_TIMES  # noqa: E402

CELLS = ["--r_out", "0.044", "--a0", "0.05", "0.2", "0.6", "--distress", "0.0", "0.02"]


def parsed(*words):
    """The runner's options as it reads them for a run on the side seeds."""
    return runner.options().parse_args(["--seeds", "side", *words])


class SideCheckTest(unittest.TestCase):
    def test_the_side_seeds_are_three_of_the_exploratory_block_and_touch_nothing_else(self):
        seeds = SEEDS["side"]
        self.assertEqual(seeds, (20261631, 20261632, 20261633))
        others = set(CONFIRMATION_RESERVED) | {s for block in RETIRED_SEEDS for s in block}
        others |= {s for name, block in SEEDS.items() if name != "side" for s in block}
        self.assertFalse(set(seeds) & others)

    def test_the_fixed_cost_multiples_are_multiples_of_the_central_level(self):
        self.assertEqual(FIXED_COST_TIMES, dict(times10=10, times100=100, times1000=1000))
        for level, times in FIXED_COST_TIMES.items():
            self.assertEqual(FIXED_COST[level], FIXED_COST["central"] * times)
            self.assertEqual(cell_inputs(0.044, level).C_fix, FIXED_COST["central"] * times)
        self.assertEqual(cell_inputs(0.044).C_fix, FIXED_COST["central"])     # the default is as it was

    def test_the_low_rates_lie_under_the_grid_and_are_no_part_of_it(self):
        self.assertEqual(LOW_RATES, (0.005, 0.01))
        self.assertTrue(all(rate < RATES[0] for rate in LOW_RATES))
        self.assertEqual(selected(), GRID)
        self.assertEqual(selected(r_out=LOW_RATES)["r_out"], LOW_RATES)
        self.assertEqual(rate_axis(LOW_RATES), LOW_RATES)

    def test_a_run_that_names_no_side_check_builds_the_economy_it_built_before(self):
        self.assertEqual(runner.side_economy(parsed()), {})
        self.assertIsNone(runner.side_check_refused(parsed()))                # the base run on the side seeds

    def test_the_settings_reach_the_economy_in_its_own_units(self):
        # 0.44% a year is 0.44 / 100 / 12 a month; the spread likewise; the shock date is in months.
        found = runner.side_economy(parsed("--custody-cost", "0.44", "--owners-spread", "0.5", "--distress-start", "12"))
        self.assertEqual(found, dict(issuer_cost=0.44 / 100 / 12, owner_spread=0.5 / 100 / 12, distress_start=12))
        economy = Economy(n=4000, **found)
        self.assertEqual((economy.issuer_cost, economy.owner_spread, economy.distress_start),
                         (0.44 / 1200, 0.5 / 1200, 12))
        # As built: 0.24% a year and 0.25 point a year, the shock from month 24.
        self.assertAlmostEqual(Economy.issuer_cost * 1200, 0.24, places=12)
        self.assertAlmostEqual(Economy.owner_spread * 1200, 0.25, places=12)
        self.assertEqual((Economy.distress_start, Economy.distress_length, Economy.months), (24, 12, 60))

    def test_the_side_checks_run_on_the_side_seeds_only(self):
        checks = (["--custody-cost", "0.44"], ["--owners-spread", "0"], ["--distress-start", "36"],
                  ["--fixed-cost", "times100"], ["--r_out", "0.005", "0.01"])
        for words in checks:
            cells = words if "--r_out" in words else [*CELLS, *words]
            args, parts = driver.plan("side", cells)
            self.assertEqual([seed for seed, _ in parts], list(SEEDS["side"]), words)
            for other in ("confirmation", "exploratory", "development"):
                with self.assertRaises(SystemExit, msg=(other, words)):
                    driver.plan(other, cells)
        # The base of the side checks: the same cells at the build's settings, 6 cells a seed.
        args, parts = driver.plan("side", CELLS)
        self.assertEqual({len(tasks) for _, tasks in parts}, {6})
        # A shock date that would push the distress year past the end of the run is refused.
        with self.assertRaises(SystemExit):
            driver.plan("side", [*CELLS, "--distress-start", "49"])
        self.assertIsNone(runner.side_check_refused(parsed("--distress-start", "48")))


if __name__ == "__main__":
    unittest.main()

"""The second registered run's own layer (cpm_abm.experiment.second_run and the runner's --second-run).

What is covered
---------------
* The grid: the second run's 210 cells (six outside rates), each rate's inputs, with the first run's grid of 105
  cells still the default and its jobs as they were.
* The settings: the base builds a valid Economy with every value of the run, and every side set builds one at each
  of its saver readings, changing only what it names, on cells of the second run's grid. The base names rules of the
  Economy (``second_run.BASE``); while the Economy lacks one, every test that builds a set it reaches is skipped and
  says which (``pending``), and ``second_run.economy`` refuses the set.
* The command line: without --second-run every option reads as the first run's; with it the cells, the readings and the
  refusals follow the run, for the population runner and for the driver that runs a map in parts.
* End to end, on a tiny world (200 people, 60 months after a burn-in of 8, the stress year from month 30): the second
  run's option on one cell at two distress levels and on the development seeds runs all five arrangements on both
  saver readings and stores what the first run stores. The first run's option on a small case writes exactly the
  stores its own steps write.
"""
import contextlib
from dataclasses import fields
import io
from itertools import chain, product
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import warnings

from scripts import run_confirmation as driver
from scripts import run_economy_population as runner
from cpm_abm.catalogue import finite_catalogue
from cpm_abm.economy_abm import Economy
from cpm_abm.experiment import second_run
from cpm_abm.experiment.grid import SEEDS, cell_inputs, selected, tasks_for
from cpm_abm.experiment.notes import A0S, ARMS, DISTRESS, GRID, RATES, SIDE_RATES

ROOT = Path(__file__).resolve().parents[1]
STORES = ("summary.json", "cells.json", "measures.json", "failure_counts.json")
CELL = ["--r_out", "0.044", "--a0", "0.6", "--distress", "0", "0.02"]
# A tiny second run: the run's settings at lengths a test can afford, with the stress year inside the second window.
TINY = dict(burn_in=8, months=60, distress_start=30)
KNOWN = {field.name for field in fields(Economy)}


def pending(name="base", reading="quote"):
    """Why the Economy cannot yet build the second run's ``name`` at ``reading``, or None when it can: the settings it
    does not have (``second_run.unknown``), or a value of ``collect_first`` it does not take yet. A test that builds
    such a set is skipped, saying why, until both exist."""
    missing = second_run.unknown(name, reading)
    if missing:
        return f"{name}: the Economy does not have {missing} yet"
    order = second_run.settings(name, reading).get("collect_first")
    try:
        Economy(**({} if order is None else dict(collect_first=order)))
    except ValueError as refused:
        return f"{name}: the Economy does not take this value yet: {refused}"
    return None


def available(name="base", reading="quote"):
    """The settings of ``name`` at ``reading`` that the Economy has, for a test that needs only the run's lengths and
    the settings its readers look at (the edge, the stress year, DeFi's yield)."""
    return {key: value for key, value in second_run.settings(name, reading).items() if key in KNOWN}


def parsed(*words, seeds="development"):
    """The population runner's options as it reads them."""
    return runner.options().parse_args(["--seeds", seeds, *words])


def cells_of(selection):
    """The cells of a selection, in the catalogue's order."""
    return [(p["r_out"], p["a0"], p["distress"])
            for p in finite_catalogue({name: list(values) for name, values in selection.items()})]


class SecondRunValues(unittest.TestCase):
    """The run's values and the command line. Nothing is simulated here."""

    def test_the_grid_has_210_cells_and_the_released_grid_still_105(self):
        grid = selected(*second_run.GRID.values())
        self.assertEqual(len(cells_of(grid)), 210)
        self.assertEqual(grid["r_out"], (0.02, 0.025, 0.03, 0.035, 0.044, 0.06))
        # The launch and distress levels are the first run's grid's; the rates are its three and the rate cut's three.
        self.assertEqual((second_run.A0S, second_run.DISTRESS), (A0S, DISTRESS))
        self.assertEqual(second_run.RATES, tuple(sorted(RATES + SIDE_RATES)))
        tasks = tasks_for((11, 12), 4000, grid)
        self.assertEqual(len(tasks), 2 * 210)
        self.assertFalse(any(task[5] for task in tasks))        # no accounting job: the edge returns that money
        # The first run's grid is the default, with its own jobs: 105 cells and the accounting job a seed.
        self.assertEqual(selected(), GRID)
        self.assertEqual(len(cells_of(selected())), 105)
        self.assertEqual(len(tasks_for((11, 12), 4000)), 2 * 106)

    def test_every_rate_has_its_inputs(self):
        for rate in second_run.RATES:
            self.assertAlmostEqual(cell_inputs(rate).rho_H, rate / 12, places=15)

    def test_the_base_settings_build_the_run(self):
        if pending():
            self.skipTest(pending())
        for reading in second_run.READS:
            w = Economy(n=4000, **second_run.economy("base", reading))
            wanted = {**second_run.LENGTHS, **second_run.BASE, "entry_reads": reading}
            for name, value in wanted.items():
                if name in KNOWN:
                    self.assertEqual(getattr(w, name), value, name)
            self.assertEqual((w.burn_in, w.months, w.distress_start, w.distress_start + w.distress_length),
                             (60, 300, 120, 132))
        # Every setting of the run is a field of the Economy, so each is applied.
        self.assertEqual("usdc_yield" in second_run.economy(), "usdc_yield" in KNOWN)
        self.assertEqual(second_run.reads("base"), ("quote", "realised"))
        with self.assertRaises(ValueError):
            second_run.economy("no_such_set")
        with self.assertRaises(ValueError):
            second_run.economy("base", "leaving_rule")

    def test_every_side_set_builds_a_valid_economy_on_cells_of_the_grid(self):
        self.assertEqual(len(second_run.SIDE_SETS), 43)
        grid = set(cells_of(selected(*second_run.GRID.values())))
        for name, changes in second_run.SIDE_SETS.items():
            self.assertTrue(set(cells_of(selected(*second_run.cells(name).values()))) <= grid, name)
        if pending():
            self.skipTest(pending())
        for name, changes in second_run.SIDE_SETS.items():
            for reading in second_run.reads(name):
                settings = second_run.economy(name, reading)
                w = Economy(n=4000, **settings)
                base = second_run.economy("base", reading)
                # Only what the set names differs from the base.
                self.assertEqual({key for key in settings if settings[key] != base.get(key)},
                                 {key for key in changes if key in KNOWN and changes[key] != base.get(key)}, name)
                for key, value in changes.items():
                    if key in KNOWN:
                        self.assertEqual(getattr(w, key), value, (name, key))
        # The base cuts card lines in the stress year; banks with outside support hold them, and so do the random
        # distress years, since the cut is defined at the one dated year and the Economy refuses it with random ones.
        self.assertTrue(second_run.economy()["card_line_cut"])
        for name in ("banks_supported", "random_distress_1", "random_distress_4"):
            self.assertFalse(second_run.economy(name)["card_line_cut"], name)
        with self.assertRaises(ValueError):
            Economy(**dict(second_run.economy("random_distress_1"), card_line_cut=True))
        # Savers' trust mixes the readings, so it runs on the quote alone, which the Economy itself requires.
        self.assertEqual(second_run.reads("savers_trust_0.5"), ("quote",))
        with self.assertRaises(ValueError):
            Economy(**dict(second_run.economy("savers_trust_0.5"), entry_reads="realised"))
        # The shares of record-readers run from 0 to 1 in steps of 0.1, and the cells are those of each study.
        self.assertEqual([second_run.SIDE_SETS[f"savers_trust_{k / 10:.1f}"]["sceptical_share"] for k in range(11)],
                         [k / 10 for k in range(11)])
        self.assertEqual(second_run.cells("owners_follow_all"), dict(r_out=(0.044,), a0=(0.45, 0.8), distress=DISTRESS))
        self.assertEqual(second_run.cells("slowdown_0.133"), dict(r_out=(0.044,), a0=(0.2, 0.6), distress=(0.0, 0.02)))

    def test_the_base_owes_the_laid_off_wage_outside(self):
        """The laid-off wage of the stress year: the payer still pays it, across the edge, and the
        payer keeping it is a side set."""
        if pending():
            self.skipTest(pending())
        for reading in second_run.READS:
            settings = second_run.economy("base", reading)
            self.assertEqual(settings["distress_wages"], "outside")
            self.assertEqual(Economy(**settings).distress_wages, "outside")
            self.assertEqual(settings["edge"], "conserved")
        self.assertEqual(second_run.economy("wages_kept")["distress_wages"], "kept")

    def test_the_sets_of_25_november(self):
        """The four decisions' sets, each on the default side cells and both saver readings, changing one setting."""
        wanted = dict(wages_kept=("distress_wages", "kept"), one_wage_each=("wage_links", "one_each"),
                      loan_losses_sourced=("loan_losses", "sourced"), shocks_on=("shocks", True),
                      **{"slowdown_0.089": ("distress_purchases", 0.089)})
        side_cells = dict(r_out=(0.044,), a0=(0.2, 0.6), distress=(0.0, 0.02))
        for name, (key, value) in wanted.items():
            self.assertEqual(second_run.SIDE_SETS[name], {key: value}, name)
            self.assertEqual(second_run.cells(name), side_cells, name)
            self.assertEqual(second_run.reads(name), ("quote", "realised"), name)
        self.assertEqual(sorted(second_run.STUDIES["slowdown"]["sets"]),
                         [f"slowdown_{x}" for x in (0.062, 0.089, 0.099, 0.119, 0.133)])
        # Kept as they were.
        self.assertEqual(second_run.SIDE_SETS["banks_supported"], dict(card_line_cut=False, card_cut_months=0))
        self.assertEqual(second_run.SIDE_SETS["defi_reserve_yield"], dict(usdc_yield="reserve"))

    def test_the_settings_of_26_november(self):
        """The base sets six rules, each rule at its first-run value a side set on the side cells, the matched pool
        without demurrage and the clean wages-first order on their studies' cells, and the failure fee off through the
        Economy's existing settings. Until the Economy has them the base is refused, naming them."""
        decided = dict(experience_rewards=True, card_cut_on="room", screen_card_owed=True,
                       buffer_reserve="share_of_spare", stress_paydays="merged", payout="paid")
        self.assertEqual({key: second_run.BASE[key] for key in decided}, decided)
        side_cells = dict(r_out=(0.044,), a0=(0.2, 0.6), distress=(0.0, 0.02))
        wanted = dict(rewards_uncounted=(dict(experience_rewards=False), side_cells),
                      cut_whole_line=(dict(card_cut_on="line"), side_cells),
                      payout_accrued=(dict(payout="accrued"), side_cells),
                      no_failure_fee=(dict(fees_a_month=0.0, buffer_prices_past_cap=False), side_cells),
                      uncharged_matched=(dict(uncharged_target="peak", uncharged_standby="reserved"),
                                         second_run.cells("uncharged_peak")),
                      wages_first_same_budget=(dict(collect_first="wages_same_budget"),
                                               second_run.cells("wages_first")))
        for name, (changes, cells) in wanted.items():
            self.assertEqual((second_run.SIDE_SETS[name], second_run.cells(name)), (changes, cells), name)
            self.assertEqual(second_run.reads(name), ("quote", "realised"), name)
        self.assertEqual(second_run.cells("owners_everything"), side_cells)
        missing = second_run.unknown()
        if missing:
            with self.assertRaises(ValueError) as said:
                second_run.economy()
            self.assertIn(str(missing), str(said.exception))
        else:
            self.assertEqual(second_run.economy(), second_run.settings())
        # The failure fee off reads the Economy's existing settings, which it has: no fee is charged.
        self.assertEqual(Economy(fees_a_month=0.0, buffer_prices_past_cap=False).fees_a_month, 0.0)

    def test_every_set_builds_at_no_distress_and_at_2_points(self):
        """The base and every side set, old and new, build a valid Economy at distress 0 and at 2 points, at each of
        their saver readings; a set the Economy cannot build yet is skipped, saying why (``pending``)."""
        for name, reading, level in product(second_run.NAMES, second_run.READS, (0.0, 0.02)):
            if reading not in second_run.reads(name):
                continue
            with self.subTest(name=name, reading=reading, level=level):
                if pending(name, reading):
                    self.skipTest(pending(name, reading))
                w = Economy(n=4000, **dict(second_run.economy(name, reading), distress=level))
                self.assertEqual(w.distress, level, (name, reading))

    def test_without_the_option_every_option_reads_as_released(self):
        args = parsed()
        self.assertIsNone(args.second_run)
        self.assertEqual((args.r_out, args.a0, args.distress), (RATES, A0S, DISTRESS))
        self.assertEqual(args.entry_reads, "quote")
        self.assertIsNone(runner.cut_refused(args))
        self.assertIsNotNone(runner.cut_refused(parsed("--r_out", "0.03", seeds="confirmation")))
        args, parts = driver.plan("confirmation", [])
        self.assertEqual((len(parts), {len(tasks) for _, tasks in parts}), (30, {106}))

    def test_the_option_selects_the_runs_cells_and_readings(self):
        args = parsed("--second-run", "base")
        self.assertEqual(selected(args.r_out, args.a0, args.distress), selected(*second_run.GRID.values()))
        self.assertEqual(runner.second_reads(args), ("quote", "realised"))
        self.assertEqual(runner.second_reads(parsed("--second-run", "base", "--entry-reads", "quote")), ("quote",))
        # Cells named before or after the option are kept; a side set runs on its own cells.
        for words in (["--a0", "0.6", "--second-run", "base"], ["--second-run", "base", "--a0", "0.6"]):
            args = parsed(*words)
            self.assertEqual((list(args.a0), len(args.r_out)), ([0.6], 6), words)
        args = parsed("--second-run", "wages_first")
        self.assertEqual(selected(args.r_out, args.a0, args.distress), second_run.cells("wages_first"))
        # The driver runs the registered run one seed a part, one reading at a time, and a side set off the
        # confirmation seeds, which are the second run's own block: refused while its count is
        # not set, and with a count of 30 the seeds 20261701 to 20261730.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            driver.plan("confirmation", ["--second-run", "base", "--entry-reads", "realised"])
        with mock.patch("cpm_abm.experiment.grid.SECOND_CONFIRMATION_COUNT", 30):
            args, parts = driver.plan("confirmation", ["--second-run", "base", "--entry-reads", "realised"])
        self.assertEqual((len(parts), {len(tasks) for _, tasks in parts}), (30, {210}))
        self.assertEqual(parts[0][0], 20261701)
        args, parts = driver.plan("side", ["--second-run", "owners_follow_all", "--entry-reads", "quote"])
        self.assertEqual((len(parts), {len(tasks) for _, tasks in parts}), (3, {10}))

    def test_the_option_refuses_what_it_does_not_run(self):
        refused = [(["--second-run", "wages_first", "--entry-reads", "quote"], "confirmation"),
                   (["--second-run", "savers_trust_0.3", "--entry-reads", "realised"], "side"),
                   (["--second-run", "base", "--card-lines", "cut"], "development"),
                   (["--second-run", "base", "--lenders-interest", "returned"], "development"),
                   (["--second-run", "base", "--distress-start", "24"], "development")]
        for words, seeds in refused:
            with self.assertRaises(SystemExit, msg=words), contextlib.redirect_stderr(io.StringIO()):
                driver.plan(seeds, words)
        # A part of a map runs one reading, so it names it.
        self.assertIn("one saver reading", runner.cut_refused(parsed("--second-run", "base", "--only-seeds",
                                                                     str(SEEDS["development"][0]))))
        self.assertIsNone(runner.cut_refused(parsed("--second-run", "base", "--entry-reads", "quote", "--only-seeds",
                                                    str(SEEDS["development"][0]))))


def keys(value, depth=3):
    """The nested keys of a stored record down to ``depth``, as a set of paths."""
    if not isinstance(value, dict) or depth == 0:
        return set()
    return {(name,) for name in value} | {(name, *rest) for name, inner in value.items()
                                         for rest in keys(inner, depth - 1)}


def stored_jobs(folder, name):
    """The jobs of one store."""
    if name == "cells.json":
        return json.loads((folder / name).read_text(encoding="utf-8"))["jobs"]
    return list(runner._stored_jobs((folder / name).read_text(encoding="utf-8")))


def without_provenance(value):
    """A store's record with every provenance left out (it names the code's hashes)."""
    if isinstance(value, dict):
        return {key: without_provenance(inner) for key, inner in value.items() if key != "provenance"}
    if isinstance(value, list):
        return [without_provenance(inner) for inner in value]
    return value


def run_main(words):
    """The population runner's main on ``words``, its printing kept from the test's output."""
    with mock.patch.object(sys, "argv", ["run_economy_population.py", *words]), warnings.catch_warnings(), \
            contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        runner.main()


class SecondRunEndToEnd(unittest.TestCase):
    """The second run's option and the first run's option on one cell at two distress levels, the development seeds."""

    @classmethod
    def setUpClass(cls):
        # Inside the workspace, as the runner's output must be; .cache is not tracked.
        (ROOT / ".cache").mkdir(exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        top = Path(cls.scratch.name)
        cls.released, cls.second, cls.direct = top / "released", top / "second", top / "direct"
        common = ["--seeds", "development", *CELL, "--workers", "3"]
        run_main([*common, "--n", "40", "--output", str(cls.released.relative_to(ROOT))])
        # The second run's base needs its rules in the Economy (``pending``); until then its part is skipped, saying
        # why, and the first run's part still runs.
        cls.pending = pending()
        if cls.pending is None:
            with mock.patch.dict(second_run.LENGTHS, TINY):
                run_main([*common, "--n", "200", "--second-run", "base", "--output",
                          str(cls.second.relative_to(ROOT))])
        # The first run's map made from its own steps, outside main, to compare with what main wrote.
        template, selection = Economy(n=40), selected((0.044,), (0.6,), (0.0, 0.02))
        tasks = tasks_for(SEEDS["development"], 40, selection)
        cls.direct.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            jobs = runner.run_tasks(tasks, template, 3)
            cells, recirculated = runner.decide_cells(jobs, selection, template, 40)
            statistics = runner.claim_statistics(cells, jobs, template)
        total = sum(map(runner.runs_in, tasks))
        runner.write_stores(cls.direct, runner.run_record(template, "development", total, selection), jobs, cells,
                            recirculated, statistics)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        if self.pending is not None and "second_run" in self._testMethodName:
            self.skipTest(self.pending)

    def test_the_second_run_completes_for_every_arrangement_on_both_readings(self):
        for reading in second_run.READS:
            folder = self.second / reading
            self.assertTrue(all((folder / name).exists() for name in STORES), reading)
            summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            economy = summary["economy"]
            self.assertEqual(economy["entry_reads"], reading)
            for name, value in {**second_run.BASE, **TINY}.items():
                if name in KNOWN:
                    self.assertEqual(economy[name], value, (reading, name))
            jobs = stored_jobs(folder, "cells.json")
            self.assertEqual(len(jobs), 2 * len(SEEDS["development"]))
            self.assertTrue(all(sorted(job["arms"]) == sorted(ARMS) for job in jobs))
            for name in ("measures.json", "failure_counts.json"):
                for job in stored_jobs(folder, name):
                    self.assertEqual(sorted(job["series" if name == "measures.json" else "failure_counts"]),
                                     sorted(("S0", *ARMS)), (reading, name))

    def test_the_second_run_stores_what_the_released_run_stores(self):
        figures = sorted(path.name for path in self.released.iterdir() if path.suffix in (".pdf", ".png"))
        for reading in second_run.READS:
            folder = self.second / reading
            self.assertEqual(sorted(path.name for path in folder.iterdir() if path.suffix in (".pdf", ".png")),
                             figures, reading)
            mine = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            theirs = json.loads((self.released / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(mine), sorted(theirs), reading)
            for name in STORES[1:]:
                found, wanted = stored_jobs(folder, name), stored_jobs(self.released, name)
                self.assertTrue(keys(wanted[0]) <= keys(found[0]), (reading, name, keys(wanted[0]) - keys(found[0])))

    def test_the_second_run_reads_the_signed_claim(self):
        """A run that conserves money: every arm's row stores each group's own failed payments by steady window; clause
        (d) is the group test, with the first run's clause beside it; the region reading holds the group test and the
        table of who pays and who receives; the stores carry the second run's notes. The first run's map stores none
        of it and keeps its notes."""
        for reading in second_run.READS:
            folder = self.second / reading
            summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("no group is harmed", summary["claim_note"])
            self.assertEqual(summary["verdicts"][4], "a group is harmed")
            rows = list(chain.from_iterable(job["arms"].values() for job in stored_jobs(folder, "cells.json")))
            self.assertEqual(len(rows), len(ARMS) * 2 * len(SEEDS["development"]))
            self.assertTrue(all(row["failed_by_group"]["windows"] == ["W2"] for row in rows))
            cell = next(c for c in summary["cells"] if c["distress"] == 0.0)
            block = cell["M1"]["claim"]
            self.assertIn("d_as_first_registered", block)
            self.assertNotIn("d_bound", block)
            self.assertEqual(sorted(block["d"]["at_95"]["passes"]), ["M0_W2", "S0_W2"])
            self.assertIn("groups_harmed", cell["M1"]["region"])
            self.assertIn("who_pays_who_receives", cell["M1"])
            # Banks and DeFi have their table too, built from their own payout, and it closes for everyone.
            for table in (cell["S0_who_pays_who_receives"], cell["M0"]["who_pays_who_receives"],
                          cell["M1"]["who_pays_who_receives"]):
                self.assertEqual(set(table) >= {"received", "paid_across_edge", "closure_everyone"}, True, reading)
                self.assertNotIn("net", table)
                self.assertLess(abs(table["closure_everyone"]["gap"]), 0.05, (reading, table["closure_everyone"]))
            # The requests to withdraw by month of filing, from which the exit-payment test can be read again.
            monthly = stored_jobs(folder, "measures.json")[0]["monthly"]
            self.assertTrue({"exits_started", "exits_paid_in_time"} <= set(monthly["M1"]))
            self.assertNotIn("exits_started", monthly["S0"])
            header = json.loads((folder / "measures.json").read_text(encoding="utf-8"))
            self.assertIn("pool_payable_most", header["second_monthly_note"])
            row = stored_jobs(folder, "cells.json")[0]["arms"]["M1"]
            self.assertEqual(set(row["pool_payable"]) - {"within_month"}, {"months", "read_by_clause", "after_launch"})
        released = json.loads((self.released / "summary.json").read_text(encoding="utf-8"))
        header = json.loads((self.released / "measures.json").read_text(encoding="utf-8"))
        self.assertNotIn("second_monthly_note", header)
        self.assertEqual(released["verdicts"][4], "a group loses")
        self.assertNotIn("no group is harmed", released["claim_note"])
        self.assertTrue(all("failed_by_group" not in job["arms"]["M1"]
                            for job in stored_jobs(self.released, "cells.json")))

    def test_the_released_option_writes_what_its_own_steps_write(self):
        for name in STORES:
            mine = json.loads((self.released / name).read_text(encoding="utf-8"))
            theirs = json.loads((self.direct / name).read_text(encoding="utf-8"))
            self.assertEqual(without_provenance(mine), without_provenance(theirs), name)
        self.assertEqual(json.loads((self.released / "summary.json").read_text(encoding="utf-8"))["economy"]["edge"],
                         "open")


if __name__ == "__main__":
    unittest.main()

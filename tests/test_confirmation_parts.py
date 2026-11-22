"""Tests for running a map in parts and joining them (scripts/run_confirmation.py, scripts/join_parts.py), on tiny
economies and the development seeds only.

What is covered
---------------
* The runner's --only-seeds: some seeds of the set, in the set's order, its stores naming the part; a seed outside
  the set refused before anything runs; without it the run record is as before.
* The join: three parts of one seed each, written as the runner writes a part, join into the four stores one run over
  the three seeds writes, every value equal but the provenance's record of the join.
* Restart: a part stopped midway has no marker, is removed and run again, and a complete part is not run again; the
  join refuses parts without their marker.
* The integrity check: a part missing a job fails it, and so does one whose gain does not add up to its split by
  outside flow.
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import warnings

from scripts import join_parts
from scripts import run_confirmation as driver
from scripts import run_economy_population as pop
from cpm_abm.experiment.store import PART_NOTE
from tests.test_economy_abm import MAP_ECONOMY

ROOT = Path(__file__).resolve().parents[1]
SEEDS = pop.SEEDS["development"]
SELECTION = pop.selected((0.044,), (0.6,), (0.0, 0.02))
CELLS = ["--r_out", "0.044", "--a0", "0.6", "--distress", "0", "0.02", "--n", "40"]
STORES = ("summary.json", "cells.json", "measures.json", "failure_counts.json")


def tiny_jobs():
    """Every job of two cells (r_out 4.4%, a0 0.6, distress 0 and 2 points) on the three development seeds, on the
    short map economy, in the order one run makes them, each with its failure counts encoded as a run returns them."""
    tasks = pop.tasks_for(SEEDS, 40, SELECTION)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return tasks, [pop.compacted(pop.job(task, MAP_ECONOMY)) for task in tasks]


def write_part(folder, tasks, jobs, seed, drop=0, add=0.0):
    """One part as the runner writes it with --only-seeds ``seed``, and its marker; ``drop`` leaves out that many of
    its last jobs and ``add`` adds dollars to one arm's mean gain, for the integrity check."""
    own = [(task, found) for task, found in zip(tasks, jobs) if task[3] == seed]
    total = sum(pop.runs_in(task) for task, _ in own)
    kept = [found for _, found in own][:len(own) - drop]
    if add:
        first = kept[0]
        kept[0] = dict(first, arms=dict(first["arms"], M1=dict(first["arms"]["M1"],
                                                               mean_gain_usd=first["arms"]["M1"]["mean_gain_usd"] + add)))
    Path(folder).mkdir(parents=True)
    meta = pop.run_record(MAP_ECONOMY, "development", total, SELECTION, only=(seed,))
    pop.write_stores(Path(folder), meta, kept, [], None)
    (Path(folder) / join_parts.COMPLETE).write_text("{}", encoding="utf-8")
    return [task for task, _ in own]


def stored(folder):
    """The four stores of ``folder``, parsed with NaN kept as its text so that equal stores compare equal, and the
    provenance's record of a join set aside."""
    found = {}
    for name in STORES:
        value = json.loads((Path(folder) / name).read_text(encoding="utf-8"), parse_constant=str)
        value["provenance"].pop("joined_from_parts", None)
        found[name] = value
    return found


class TinyMap(unittest.TestCase):
    """The short map of two cells on three seeds, run once: its jobs, its parts and the stores one run writes."""

    @classmethod
    def setUpClass(cls):
        # Inside the workspace, as the driver's output must be; .cache is not tracked.
        (ROOT / ".cache").mkdir(exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        cls.tasks, cls.jobs = tiny_jobs()
        cls.parts = Path(cls.scratch.name) / "parts"
        for seed in SEEDS:   # the parts first: a part decides nothing, so it is written before the cells are
            write_part(cls.parts / f"seed_{seed}", cls.tasks, cls.jobs, seed)
        cls.whole = Path(cls.scratch.name) / "whole"
        cls.whole.mkdir()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            cells, recirculated = pop.decide_cells(cls.jobs, SELECTION, MAP_ECONOMY, 40)
            statistics = pop.claim_statistics(cells, cls.jobs, MAP_ECONOMY)
        total = sum(map(pop.runs_in, cls.tasks))
        pop.write_stores(cls.whole, pop.run_record(MAP_ECONOMY, "development", total, SELECTION), cls.jobs, cells,
                         recirculated, statistics)

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def joined(self, output):
        """The parts copied into ``output`` and joined there, without figures."""
        shutil.copytree(self.parts, Path(output) / "parts")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            join_parts.join(output, figures=False)
        return Path(output)

    def test_the_join_writes_the_stores_one_run_writes(self):
        """Three parts of one seed each join into the four stores of one run over the three seeds, every value of
        every key equal, the jobs in the run's order, the summary's cells and claim statistics read over all the
        seeds; only the provenance differs, by its record of the join naming the three parts."""
        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            output = self.joined(folder)
            whole, joined = stored(self.whole), stored(output)
            for name in STORES:
                self.assertEqual(joined[name], whole[name], name)
            record = json.loads((output / "summary.json").read_text(encoding="utf-8"))["provenance"]
            self.assertEqual([part["seeds"] for part in record["joined_from_parts"]["parts"]], [[s] for s in SEEDS])
            self.assertEqual(len(joined["summary.json"]["cells"]), 2)
            self.assertEqual(joined["summary.json"]["seeds"], list(SEEDS))
            self.assertNotIn("part", joined["cells.json"])
            self.assertTrue((output / join_parts.JOINED).exists())

    def test_a_seed_set_aside_is_left_out_of_the_join_and_named(self):
        """A map whose folder names a seed set aside joins the other seeds: its stores are those one run over those
        seeds writes, its summary lists them alone, and the provenance and the marker name the seed with the reason
        recorded. A seed both set aside and complete is refused."""
        lost, kept = SEEDS[1], [seed for seed in SEEDS if seed != SEEDS[1]]
        reason = dict(reason="a job failed", message="Job failed: settlement did not reach its fixed point",
                      at="2026-11-18 15:08")
        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            output = Path(folder)
            shutil.copytree(self.parts, output / "parts")
            shutil.rmtree(output / "parts" / f"seed_{lost}")
            (output / "parts" / f"seed_{lost}").mkdir()        # what a run that stopped leaves: no marker
            (output / join_parts.SET_ASIDE).write_text(json.dumps({str(lost): reason}), encoding="utf-8")
            # One run over the two seeds kept, written as a run writes it.
            pairs = [(task, job) for task, job in zip(self.tasks, self.jobs) if task[3] != lost]
            tasks, jobs = [task for task, _ in pairs], [job for _, job in pairs]
            direct = output / "direct"
            direct.mkdir()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                cells, recirculated = pop.decide_cells(jobs, SELECTION, MAP_ECONOMY, 40)
                statistics = pop.claim_statistics(cells, jobs, MAP_ECONOMY)
                join_parts.join(output, figures=False)
            total = sum(map(pop.runs_in, tasks))
            record = dict(pop.run_record(MAP_ECONOMY, "development", total, SELECTION), seeds=kept)
            pop.write_stores(direct, record, jobs, cells, recirculated, statistics)
            whole, joined = stored(direct), stored(output)
            for name in STORES:
                self.assertEqual(joined[name], whole[name], name)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["seeds"], kept)
            self.assertEqual({cell["seeds"] for cell in summary["cells"] if cell}, {len(kept)})
            named = summary["provenance"]["joined_from_parts"]
            self.assertEqual([part["seeds"] for part in named["parts"]], [[seed] for seed in kept])
            self.assertEqual(named["set_aside"], [dict(seed=lost, **reason)])
            marker = json.loads((output / join_parts.JOINED).read_text(encoding="utf-8"))
            self.assertEqual(marker["set_aside"], [lost])
        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            output = Path(folder)
            shutil.copytree(self.parts, output / "parts")   # the seed set aside still has its complete part
            (output / join_parts.SET_ASIDE).write_text(json.dumps({str(lost): reason}), encoding="utf-8")
            with self.assertRaises(ValueError):
                join_parts.join(output, figures=False)

    def test_a_part_names_itself_and_decides_nothing(self):
        """A part's stores hold its seed alone and name the set and all its seeds; its summary has no cells and no
        claim statistics; without --only-seeds the run record has no part."""
        summary = json.loads((self.parts / f"seed_{SEEDS[1]}" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["seeds"], [SEEDS[1]])
        self.assertEqual(summary["part"], dict(seed_set="development", set_seeds=list(SEEDS), note=PART_NOTE))
        self.assertEqual((summary["cells"], "claim_statistics" in summary), ([], False))
        whole = pop.run_record(MAP_ECONOMY, "development", 30, SELECTION)
        self.assertNotIn("part", whole)
        self.assertEqual(list(whole["seeds"]), list(SEEDS))

    def test_only_seeds_runs_some_seeds_of_the_set_and_refuses_others(self):
        """--only-seeds keeps the named seeds in the set's order (the dry run's plan); a seed outside the set, here
        the first confirmation seed under the development set, is refused before anything runs or is written."""
        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            target = Path(folder) / "never"
            argv = ["run_economy_population.py", "--seeds", "development", *CELLS, "--output", str(target)]
            out = io.StringIO()
            with mock.patch.object(sys, "argv", argv + ["--only-seeds", str(SEEDS[2]), str(SEEDS[0]), "--dry-run"]), \
                    contextlib.redirect_stdout(out):
                pop.main()
            plan = json.loads(out.getvalue().split("\ncells (r_out")[0])
            self.assertEqual((plan["seeds"], plan["part_of"], plan["jobs"]), ([SEEDS[0], SEEDS[2]], list(SEEDS), 4))
            out = io.StringIO()
            with mock.patch.object(sys, "argv", argv + ["--dry-run"]), contextlib.redirect_stdout(out):
                pop.main()
            self.assertNotIn("part_of", json.loads(out.getvalue().split("\ncells (r_out")[0]))
            err = io.StringIO()
            with mock.patch.object(sys, "argv", argv + ["--only-seeds", "20261401"]), \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                pop.main()
            self.assertIn("--only-seeds must name seeds of the development set", err.getvalue())
            self.assertFalse(target.exists())

    def test_the_integrity_check_fails_a_part_missing_a_job_or_not_conserving_money(self):
        """A whole part passes every check; one missing its last job fails the check that every job of the grid is
        there; one whose gain against S0 is a dollar off its split by outside flow fails the conservation check."""
        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            seed = SEEDS[0]
            whole = driver.check_part(self.parts / f"seed_{seed}", "development", seed,
                                      [t for t in self.tasks if t[3] == seed], 0)
            self.assertTrue(whole["passed"], whole)
            short = Path(folder) / "short"
            own = write_part(short, self.tasks, self.jobs, seed, drop=1)
            result = driver.check_part(short, "development", seed, own, 0)
            failed = [check["check"] for check in result["checks"] if not check["passed"]]
            self.assertFalse(result["passed"])
            self.assertIn("every job of the grid is in cells.json", failed)
            self.assertIn("every job is in measures.json", failed)
            off = Path(folder) / "off"
            write_part(off, self.tasks, self.jobs, seed, add=1.0)
            result = driver.check_part(off, "development", seed, own, 0)
            self.assertEqual([check["check"] for check in result["checks"] if not check["passed"]],
                             ["money is conserved"])
            self.assertFalse(driver.check_part(self.parts / f"seed_{seed}", "development", seed, own, 1)["passed"])

    def test_a_stopped_map_restarts_where_it_stopped(self):
        """The driver over three seeds: the second part's run stops having written two stores, so the driver stops
        with the first part complete and the second without its marker, and the join refuses them; run again, the
        first part is not run again, the second is removed and run again, the third is run, and the joined stores are
        the ones one run writes; a third call runs nothing."""
        calls = []

        def runner(stop):
            """A stand-in for the population runner's process: it writes the part it is asked for from the parts
            made above (or, for ``stop``, two stores of it and a failing exit code)."""
            def run(command, cwd, stdout, stderr):
                seed = int(command[command.index("--only-seeds") + 1])
                target = ROOT / command[command.index("--output") + 1]
                calls.append(seed)
                target.mkdir(parents=True)
                for name in STORES[:2] if seed == stop else STORES:
                    shutil.copy(self.parts / f"seed_{seed}" / name, target / name)
                return mock.Mock(returncode=1 if seed == stop else 0)
            return run

        with tempfile.TemporaryDirectory(dir=self.scratch.name) as folder:
            output = Path(folder) / "map"
            argv = ["run_confirmation.py", "--seeds", "development", "--output", str(output), *CELLS, "--no-figures"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(driver.subprocess, "run", runner(SEEDS[1])), \
                    self.assertRaises(SystemExit):
                driver.main()
            self.assertEqual(calls, [SEEDS[0], SEEDS[1]])
            self.assertTrue((join_parts.part_folder(output, SEEDS[0]) / join_parts.COMPLETE).exists())
            self.assertTrue(join_parts.part_folder(output, SEEDS[1]).exists())
            self.assertFalse((join_parts.part_folder(output, SEEDS[1]) / join_parts.COMPLETE).exists())
            with self.assertRaises(ValueError):
                join_parts.join(output, figures=False)
            calls.clear()
            with warnings.catch_warnings(), mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(driver.subprocess, "run", runner(None)), \
                    contextlib.redirect_stdout(io.StringIO()):
                warnings.simplefilter("ignore", RuntimeWarning)
                driver.main()
            self.assertEqual(calls, [SEEDS[1], SEEDS[2]])
            whole, joined = stored(self.whole), stored(output)
            for name in STORES:
                self.assertEqual(joined[name], whole[name], name)
            progress = (output / driver.PROGRESS).read_text(encoding="utf-8")
            self.assertEqual(progress.count("integrity passed"), 3)
            self.assertIn("FAILED", progress)
            calls.clear()
            with mock.patch.object(sys, "argv", argv), mock.patch.object(driver.subprocess, "run", runner(None)), \
                    contextlib.redirect_stdout(io.StringIO()):
                driver.main()
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()

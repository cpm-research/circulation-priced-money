"""Tests for scripts/set_second_count.py: the second run's count of confirmation seeds, fixed from its development
map by the registered rule and written into grid.py. No simulation.

What is covered
---------------
* The count read from a map's summary is the rule's (26 gives 30, 33 gives 40, 44 gives 50); a summary without the
  second run's count, without any count, or storing a count that is not the rule's is refused.
* The checks of the map: the registered development map passes, and a map on other seeds, with another population,
  on part of the grid, under the other saver reading or with a setting changed is named as such.
* The checks of the code: a joined map whose recorded sources hash to the files here passes; a map that is not
  joined, whose code had uncommitted changes, or one of whose sources differs is named; and grid.py alone may differ
  once this script's own record shows it before and after the count was written.
* The one line of grid.py: set once, left alone when set to the same number, refused when set to another, on a copy
  of the file; the tracked grid.py itself still leaves the count unset or holds a whole number in the rule's range.
"""
import json
import tempfile
import unittest
from pathlib import Path

from scripts import set_second_count as fix
from cpm_abm.experiment import grid, second_run
from cpm_abm.experiment.notes import POPULATION


def summary(registered=33, **changed):
    """A joined development map's summary as far as the script reads it, with the planner's registered count."""
    rounded = grid.second_confirmation_count(registered)
    economy = dict(second_run.economy("base", "quote"), n=POPULATION)
    economy.update(changed.pop("economy", {}))
    found = dict(seed_set="development", seeds=list(grid.SEEDS["development"]), economy=economy,
                 selected={name: list(levels) for name, levels in second_run.GRID.items()},
                 claim_statistics=dict(seeds=dict(second_run=dict(registered=registered, rounded=rounded))))
    found.update(changed)
    return found


class TheCount(unittest.TestCase):
    def test_the_count_is_the_rules(self):
        for registered, count in ((26, 30), (33, 40), (44, 50)):
            self.assertEqual(fix.planned(summary(registered))[0], count)

    def test_a_summary_without_a_count_is_refused(self):
        with self.assertRaises(ValueError):
            fix.planned(dict(claim_statistics=dict(seeds=dict())))
        with self.assertRaises(ValueError):
            fix.planned(summary(None))
        wrong = summary(33)
        wrong["claim_statistics"]["seeds"]["second_run"]["rounded"] = 30
        with self.assertRaises(ValueError):
            fix.planned(wrong)


class TheRegisteredMap(unittest.TestCase):
    def test_the_registered_map_passes(self):
        self.assertEqual(fix.not_registered(summary()), [])

    def test_another_map_is_named(self):
        cases = dict(seeds=summary(seed_set="side", seeds=[20261631, 20261632, 20261633]),
                     people=summary(economy=dict(n=1000)),
                     grid=summary(selected=dict(second_run.GRID, r_out=[0.044])),
                     reading=summary(economy=dict(entry_reads="realised")),
                     setting=summary(economy=dict(edge="open")))
        for name, found in cases.items():
            with self.subTest(name):
                self.assertEqual(len(fix.not_registered(found)), 1)


class TheCodeThatMadeTheMap(unittest.TestCase):
    def setUp(self):
        """A code tree of two source files, grid.py among them, and a joined map made by it."""
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.grid = fix.GRID_FILE.relative_to(fix.ROOT).as_posix()
        for name, text in ((self.grid, b"SECOND_CONFIRMATION_COUNT = None\n"), ("src/other.py", b"X = 1\n")):
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(text)
        self.folder = self.root / "runs" / "development_quote"
        self.folder.mkdir(parents=True)
        (self.folder / "joined.json").write_text("{}", encoding="utf-8")
        sources = {name: fix.source_digest(self.root / name) for name in (self.grid, "src/other.py")}
        self.made = dict(provenance=dict(sources=sources, uncommitted_source_changes=False, git_commit=None))

    def tearDown(self):
        self.scratch.cleanup()

    def test_a_map_made_by_this_code_passes(self):
        self.assertEqual(fix.stale(self.made, self.folder, self.root), [])

    def test_a_map_from_other_code_is_named(self):
        dirty = dict(provenance=dict(self.made["provenance"], uncommitted_source_changes=True))
        self.assertEqual(len(fix.stale(dirty, self.folder, self.root)), 1)
        other = dict(provenance=dict(self.made["provenance"], sources=dict(self.made["provenance"]["sources"],
                                                                         **{"src/other.py": "0" * 64})))
        self.assertIn("src/other.py", fix.stale(other, self.folder, self.root)[0])
        self.assertEqual(len(fix.stale(dict(self.made, part=dict(seeds=[1])), self.folder, self.root)), 1)
        (self.folder / "joined.json").unlink()
        self.assertEqual(len(fix.stale(self.made, self.folder, self.root)), 1)

    def test_grid_py_may_differ_only_by_this_scripts_own_count(self):
        before = fix.source_digest(self.root / self.grid)
        fix.write_count(40, self.root / self.grid)
        self.assertIn(self.grid, fix.stale(self.made, self.folder, self.root)[0])
        record = dict(grid_py=dict(before=before, after=fix.source_digest(self.root / self.grid)))
        (self.folder.parent / fix.RECORD).write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(fix.stale(self.made, self.folder, self.root), [])
        (self.root / self.grid).write_bytes(b"SECOND_CONFIRMATION_COUNT = 50\n")
        self.assertIn(self.grid, fix.stale(self.made, self.folder, self.root)[0])


class TheLine(unittest.TestCase):
    def test_the_line_is_set_once(self):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "grid.py"
            copy.write_bytes(b"A = 1\nSECOND_CONFIRMATION_COUNT = None\nB = 2\n")
            self.assertEqual(fix.write_count(40, copy), "set")
            self.assertEqual(copy.read_bytes(), b"A = 1\nSECOND_CONFIRMATION_COUNT = 40\nB = 2\n")
            self.assertEqual(fix.write_count(40, copy), "already set")
            with self.assertRaises(ValueError):
                fix.write_count(50, copy)
            copy.write_bytes(b"A = 1\n")
            with self.assertRaises(ValueError):
                fix.write_count(40, copy)

    def test_the_text_with_the_count_is_made_before_anything_is_written(self):
        """``counted`` gives the text with the count and "set", the same text and "already set" once it holds it,
        and refuses another number; nothing is written by it."""
        text = "A = 1\nSECOND_CONFIRMATION_COUNT = None\nB = 2\n"
        made, done = fix.counted(40, text)
        self.assertEqual((made, done), ("A = 1\nSECOND_CONFIRMATION_COUNT = 40\nB = 2\n", "set"))
        self.assertEqual(fix.counted(40, made), (made, "already set"))
        with self.assertRaises(ValueError):
            fix.counted(50, made)

    def test_the_tracked_file_has_the_line(self):
        text = fix.GRID_FILE.read_text(encoding="utf-8")
        if grid.SECOND_CONFIRMATION_COUNT is None:
            self.assertEqual(len(fix.UNSET.findall(text)), 1)
        else:
            self.assertIn(f"\nSECOND_CONFIRMATION_COUNT = {grid.SECOND_CONFIRMATION_COUNT}\n", text)
            self.assertIn(grid.SECOND_CONFIRMATION_COUNT, range(30, 101, 10))


if __name__ == "__main__":
    unittest.main()

"""Shipping stored results (scripts/pack_results.py): a store over the size limit is cut into volumes that join back
to the same bytes, the paper's scripts read the volumes as they read the store, and the list of checksums tells a
changed file from an absent one. Every file here is made by hand in a temporary folder; nothing is run."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts import pack_results
from scripts import paper_figures as pf
from scripts import paper_numbers as pn

LIMIT = 20_000                                         # bytes a file, small so that a hand-made store needs volumes


def run_folder(folder, numbers=40_000):
    """A run folder with a small summary.json and a measures.json of ``numbers`` drawn numbers, far over LIMIT."""
    run = Path(folder) / "run"
    run.mkdir()
    (run / "summary.json").write_text('{"cells": []}', encoding="utf-8")
    values = np.random.default_rng(7).random(numbers).tolist()
    (run / "measures.json").write_text(json.dumps(dict(jobs=[dict(series=values)])), encoding="utf-8")
    return run


class VolumeTest(unittest.TestCase):
    def test_a_store_over_the_limit_is_cut_into_volumes_that_join_back_to_it(self):
        with tempfile.TemporaryDirectory() as folder:
            run = run_folder(folder)
            data = (run / "measures.json").read_bytes()
            target = Path(folder) / "shipped"
            written = pack_results.pack(run, target, limit=LIMIT)
            volumes = [name for name in written if name.startswith("measures.json")]
            count = len(volumes)
            self.assertGreaterEqual(count, 10)                               # enough for the padded names to matter
            self.assertEqual(volumes, [f"measures.json.gz.{k:02d}of{count}" for k in range(1, count + 1)])
            self.assertEqual(sorted(volumes), volumes)                       # so a shell joins them in order
            self.assertEqual(written[0], "summary.json.gz")                  # a small store stays one file
            self.assertTrue(all((target / name).stat().st_size <= LIMIT for name in written))
            # Joined in order, the volumes are one gzip file of the whole store, and the store's own bytes.
            joined = b"".join((target / name).read_bytes() for name in volumes)
            self.assertEqual(gzip.decompress(joined), data)
            self.assertEqual(pack_results.unpacked(target, "measures.json"), data)
            # The paper's two readers read the volumes as they read the store the runner wrote.
            plain = (run / "measures.json").read_text(encoding="utf-8")
            self.assertEqual(pn.stored_text(target, "measures.json"), plain)
            self.assertEqual(pf.stored_text(target, "measures.json"), plain)
            self.assertEqual(json.loads(pn.stored_text(target, "measures.json")), json.loads(plain))

    def test_the_same_store_gives_the_same_volumes_and_a_new_packing_leaves_no_old_one(self):
        with tempfile.TemporaryDirectory() as folder:
            run = run_folder(folder)
            a, b = Path(folder) / "a", Path(folder) / "b"
            first = pack_results.pack(run, a, limit=LIMIT)
            self.assertEqual(pack_results.pack(run, b, limit=LIMIT), first)
            self.assertTrue(all((a / name).read_bytes() == (b / name).read_bytes() for name in first))
            again = pack_results.pack(run, a)                                # the default limit: one file a store
            self.assertEqual(again, ["summary.json.gz", "measures.json.gz"])
            self.assertEqual(sorted(p.name for p in a.iterdir()), ["measures.json.gz", "summary.json.gz"])

    def test_a_set_of_volumes_with_one_missing_is_refused_by_every_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "shipped"
            written = pack_results.pack(run_folder(folder), target, limit=LIMIT)
            (target / written[-1]).unlink()                                  # the last volume
            for read in (pn.stored_text, pf.stored_text, pack_results.unpacked):
                with self.assertRaises(ValueError):
                    read(target, "measures.json")

    def test_line_ends_are_read_alike_whole_and_across_a_cut(self):
        # A store written on Windows ends its lines \r\n; a cut between the two bytes must read as one line end.
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "cells.json.gz.1of2").write_bytes(pack_results.packed(b'{"a":\r'))
            (folder / "cells.json.gz.2of2").write_bytes(pack_results.packed(b'\n1}'))
            self.assertEqual(pn.stored_text(folder, "cells.json"), '{"a":\n1}')
            self.assertEqual(pf.stored_text(folder, "cells.json"), '{"a":\n1}')

    def test_an_absent_store_reads_as_none_in_the_numbers_and_is_refused_by_the_figures(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(pn.stored_text(folder, "measures.json"))
            self.assertIsNone(pack_results.unpacked(folder, "measures.json"))
            with self.assertRaises(FileNotFoundError):
                pf.stored_text(folder, "measures.json")


class RecordsTest(unittest.TestCase):
    def test_a_run_made_in_parts_ships_its_records_and_no_machine_path(self):
        with tempfile.TemporaryDirectory() as folder:
            run = run_folder(folder)
            for name, text in (("command.json", '{"seed_set": "development"}'), ("progress.txt", "seed 11: done\n"),
                               ("joined.json", '{"jobs": 6}')):
                (run / name).write_text(text, encoding="utf-8")
            for seed in (11, 12):
                part = run / "parts" / f"seed_{seed}"
                part.mkdir(parents=True)
                (part / "integrity.json").write_text('{"passed": true}', encoding="utf-8")
                (part / "complete.json").write_text('{"command": ["C:/somewhere/run.py"]}', encoding="utf-8")
            target = Path(folder) / "shipped"
            written = pack_results.pack(run, target)
            records = sorted(p.name for p in (target / "run_records").iterdir())
            self.assertEqual(records, ["command.json", "integrity_seed_11.json", "integrity_seed_12.json",
                                       "joined.json", "progress.txt"])       # complete.json names a local path: left
            self.assertEqual(sorted(name for name in written if name.startswith("run_records/")),
                             [f"run_records/{name}" for name in records])
            self.assertEqual((target / "run_records" / "integrity_seed_12.json").read_text(encoding="utf-8"),
                             '{"passed": true}')


class SumsTest(unittest.TestCase):
    def test_the_list_of_checksums_tells_changed_absent_and_unlisted_files_apart(self):
        with tempfile.TemporaryDirectory() as folder:
            into = Path(folder) / "results"
            pack_results.pack(run_folder(folder), into / "map", limit=LIMIT)
            count = pack_results.write_sums(into)
            lines = (into / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), count)
            self.assertTrue(all(len(line.split("  ")[0]) == 64 and line.split("  ")[1].startswith("map/")
                                for line in lines))                          # the format sha256sum reads
            self.assertEqual([line.split("  ")[1] for line in lines], sorted(line.split("  ")[1] for line in lines))
            verified, absent, changed, unlisted = pack_results.check_sums(into)
            self.assertEqual((len(verified), absent, changed, unlisted), (count, [], [], []))
            self.assertEqual(pack_results.main(["--check", "--into", str(into), "--complete"]), 0)
            # One file changed, one removed, one added: each is named under its own heading.
            names = [line.split("  ")[1] for line in lines]
            (into / names[0]).write_bytes((into / names[0]).read_bytes() + b"x")
            (into / names[1]).unlink()
            (into / "map" / "note.txt").write_text("not data, so never listed", encoding="utf-8")
            (into / "map" / "extra.json.gz").write_bytes(pack_results.packed(b"{}"))
            verified, absent, changed, unlisted = pack_results.check_sums(into)
            self.assertEqual((len(verified), absent, changed, unlisted),
                             (count - 2, [names[1]], [names[0]], ["map/extra.json.gz"]))
            self.assertEqual(pack_results.main(["--check", "--into", str(into)]), 1)        # a changed file fails
            (into / names[0]).write_bytes((into / names[0]).read_bytes()[:-1])
            self.assertEqual(pack_results.main(["--check", "--into", str(into)]), 0)        # absent alone passes
            self.assertEqual(pack_results.main(["--check", "--into", str(into), "--complete"]), 1)

    def test_the_results_shipped_here_are_the_ones_the_list_names(self):
        # The list at results/SHA256SUMS against the files beside it: none changed, none shipped without a line.
        into = Path(pack_results.__file__).resolve().parents[1] / "results"
        verified, absent, changed, unlisted = pack_results.check_sums(into)
        self.assertTrue(verified)
        self.assertEqual((changed, unlisted), ([], []))


if __name__ == "__main__":
    unittest.main()

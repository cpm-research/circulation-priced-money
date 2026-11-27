"""scripts/bank_support.py on synthetic stores: its numbers equal the hand values, and stores with nothing in common
or that are not one model with card lines held and cut are refused."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bank_support                                                          # noqa: E402
from run_economy_figures import DOLLARS                                      # noqa: E402


def job(seed, distress, card_debt, failure, interest, unbilled=None, a0=0.6, bridges=None):
    """A job as measures.json stores it, 24 months: card debt, money 2.0 (1.5 and 0.5), the given interest, pool
    capital 2.0 and term credit 0.4 in M1; with ``bridges``, the pool's carried bridges (P_bar) and every loan it
    carried, the term credit and the bridges together (pool_pt)."""
    monthly = dict(card_debt=[card_debt] * 24, money_bt=[1.5] * 24, savings_bt=[0.5] * 24, out_interest=[interest] * 24)
    if unbilled is not None:
        monthly["card_unbilled"] = [unbilled] * 24
    pool = dict(monthly, N=[2.0] * 24, term_pool=[0.4] * 24)
    if bridges is not None:
        pool.update(P_bar=[bridges] * 24, pool_pt=[0.4 + bridges] * 24)
    return dict(r_out=0.044, a0=a0, distress=distress, seed=seed, recirculated=False,
                series=dict(S0=dict(failures=[failure] * 24), M1=dict(failures=[failure / 2] * 24)),
                monthly=dict(S0=monthly, M1=pool))


def summary(held, **changes):
    """A joined map's summary as far as the pairing check reads it: the settings of a run with card lines held or
    cut, and the code that made it; ``changes`` replace settings, and ``sources`` or ``git_commit`` the code."""
    made = dict(git_commit=changes.pop("git_commit", "c0ffee1"), uncommitted_source_changes=False,
                sources=changes.pop("sources", {"src/a.py": "1", bank_support.GRID_SOURCE: "g0"}))
    economy = dict(n=4000, entry_reads="quote", edge="conserved", card_line_cut=not held,
                   card_cut_months=0 if held else 120)
    return dict(economy={**economy, **changes}, provenance=made)


def store(folder, jobs, held, **changes):
    """Write a joined map's summary.json and measures.json in ``folder``, for a run with lines held or cut."""
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps(summary(held, **changes)), encoding="utf-8")
    (folder / "measures.json").write_text(json.dumps(dict(jobs=jobs)), encoding="utf-8")


def jobs_for(seeds, held, unbilled=None, bridges=None):
    """The cell with distress 0.02 and its zero-distress twin for each seed, with lines held or cut."""
    debt, interest, failure = (0.3, 0.004, 0.02) if held else (0.2, 0.003, 0.05)
    return [job(seed, level, debt, failure, interest, unbilled, bridges=bridges)
            for seed in seeds for level in (0.02, 0.0)]


class BankSupport(unittest.TestCase):
    def test_hand_values(self):
        """Card debt 0.30 held and 0.20 cut, money 2.0, interest 0.004 against 0.003, failures 2% against 5% of value
        due: 0.10 supported ($644 a person), 0.012 extra interest a year, and the matched cells only (seed 3 is held
        only, distress 0.02 and 0 both read)."""
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs_for((1, 2, 3), True), True)
            store(cut_dir, jobs_for((1, 2), False), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                bank_support.main()
            result = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual([c["distress"] for c in result["cells"]], [0.0, 0.02])
        for cell in result["cells"]:
            self.assertEqual(cell["seeds"], [1, 2])
            banks, cpm = cell["arms"]["S0"], cell["arms"]["M1"]
            support = banks["support"]
            self.assertEqual(support["seeds"], 2)
            self.assertEqual(support["card_credit_reads"], "card_debt")
            self.assertAlmostEqual(support["by_year"]["supported"][0]["mean"], 0.1)
            self.assertAlmostEqual(support["by_year"]["supported_usd"][1]["mean"], 0.1 * DOLLARS)
            self.assertAlmostEqual(support["by_year"]["extra_outside_interest"][0]["mean"], 0.012)
            self.assertAlmostEqual(support["by_year"]["share_of_money"][0]["mean"], 0.05)
            self.assertAlmostEqual(banks["failed_payment_share_pct"]["held"][0]["mean"], 2.0)
            self.assertAlmostEqual(banks["failed_payment_share_pct"]["cut"][1]["mean"], 5.0)
            self.assertAlmostEqual(cpm["failed_payment_share_pct"]["held"][0]["mean"], 1.0)
            self.assertAlmostEqual(cpm["pool_capital"]["held"][0]["mean"], 2.0)
            self.assertAlmostEqual(cpm["term_credit"]["cut_usd"][0]["mean"], 0.4 * DOLLARS)
            self.assertIsNone(cpm["bridge_credit"]["held"])
            self.assertIsNone(cpm["credit_carried"]["held"])

    def test_bridge_credit_is_the_bridges_alone(self):
        """Term credit 0.40 and bridges 0.02 held, 0.05 cut: bridge credit reads 0.02 and 0.05, not the 0.42 and 0.45
        of all the loans the pool carried, which is reported beside it."""
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs_for((1, 2), True, bridges=0.02), True)
            store(cut_dir, jobs_for((1, 2), False, bridges=0.05), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                bank_support.main()
            cpm = json.loads(out.read_text(encoding="utf-8"))["cells"][0]["arms"]["M1"]
        self.assertAlmostEqual(cpm["bridge_credit"]["held"][0]["mean"], 0.02)
        self.assertAlmostEqual(cpm["bridge_credit"]["cut"][1]["mean"], 0.05)
        self.assertAlmostEqual(cpm["bridge_credit"]["cut_usd"][0]["mean"], 0.05 * DOLLARS)
        self.assertAlmostEqual(cpm["credit_carried"]["held"][0]["mean"], 0.42)
        self.assertAlmostEqual(cpm["credit_carried"]["cut"][0]["mean"], 0.45)
        self.assertAlmostEqual(cpm["term_credit"]["held"][0]["mean"], 0.4)

    def test_card_unbilled_is_read_where_stored(self):
        """With card_unbilled 0.05 held and 0.02 cut the support is 0.13 and the reading says it read both series."""
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs_for((1, 2), True, 0.05), True)
            store(cut_dir, jobs_for((1, 2), False, 0.02), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                bank_support.main()
            support = json.loads(out.read_text(encoding="utf-8"))["cells"][0]["arms"]["S0"]["support"]
        self.assertEqual(support["card_credit_reads"], "card_debt + card_unbilled")
        self.assertAlmostEqual(support["by_year"]["supported"][0]["mean"], 0.13)

    def test_only_one_model_with_lines_held_and_cut_is_a_pair(self):
        """The pair passes; swapped, on another saver reading, at another population, from other code or at another
        commit it is refused with the reason; grid.py alone may differ where the count record shows it before and
        after exactly as the two stores have it."""
        reasons = bank_support.pair_reasons
        self.assertEqual(reasons(summary(True), summary(False)), [])
        self.assertEqual(len(reasons(summary(False), summary(True))), 2)
        self.assertIn("entry_reads", reasons(summary(True, entry_reads="realised"), summary(False))[0])
        self.assertIn("the setting n differs", reasons(summary(True, n=1000), summary(False))[0])
        self.assertIn("different code: src/a.py", reasons(summary(True, sources={"src/a.py": "2"}), summary(False))[0])
        self.assertIn("different commits", reasons(summary(True, git_commit="abc"), summary(False))[0])
        self.assertEqual(reasons({}, summary(False)), ["a store does not record its settings"])
        counted = summary(True, sources={"src/a.py": "1", bank_support.GRID_SOURCE: "g1"})
        self.assertIn("grid.py", reasons(counted, summary(False))[0])
        self.assertEqual(reasons(counted, summary(False), dict(grid_py=dict(before="g0", after="g1"))), [])
        self.assertIn("grid.py", reasons(counted, summary(False), dict(grid_py=dict(before="g0", after="g2")))[0])

    def test_a_pair_that_is_not_one_writes_nothing(self):
        """A held store of 1,000 people against a cut store of 4,000 is refused by name and nothing is written."""
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs_for((1, 2), True), True, n=1000)
            store(cut_dir, jobs_for((1, 2), False), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            with self.assertRaises(SystemExit) as stop:
                bank_support.main()
            self.assertIn("the setting n differs", str(stop.exception))
            self.assertFalse(out.exists())

    def test_the_console_names_the_year_of_the_largest_support(self):
        """Card debt equal for ten years and 0.10 apart in year 11: the line printed names year 11 and $644."""
        def jobs(held):
            made = jobs_for((1, 2), held)
            for one in made:
                for arm in ("S0", "M1"):
                    one["monthly"][arm] = {key: (values * 6)[:132] for key, values in one["monthly"][arm].items()}
                    one["monthly"][arm]["card_debt"] = [0.2] * 120 + [0.3 if held else 0.2] * 12
                    one["series"][arm] = {key: (values * 6)[:132] for key, values in one["series"][arm].items()}
            return made
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs(True), True)
            store(cut_dir, jobs(False), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                bank_support.main()
            pair = json.loads(out.read_text(encoding="utf-8"))["pair"]
        self.assertIn("largest in year 11, 644.00 $ a person", printed.getvalue())
        self.assertEqual((pair["population"], pair["entry_reads"]), (4000, "quote"))
        self.assertEqual((pair["held"]["card_line_cut"], pair["cut"]["card_line_cut"]), (False, True))

    def test_stores_with_nothing_in_common_are_refused(self):
        """Disjoint seeds share no cell and seed: the script stops with a plain message and writes nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            held_dir, cut_dir, out = Path(tmp) / "held", Path(tmp) / "cut", Path(tmp) / "out.json"
            store(held_dir, jobs_for((1,), True), True)
            store(cut_dir, jobs_for((2,), False), False)
            sys.argv = ["bank_support", str(held_dir), str(cut_dir), "--out", str(out)]
            with self.assertRaises(SystemExit) as stop:
                bank_support.main()
            self.assertIn("share no cell and seed", str(stop.exception))
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()

"""The parameter table (docs/PARAMETERS.csv, table tab:parameters in the appendix of paper/cpm.tex, Parameters and
sources) against the code: every row's value must equal
the value the code holds under that name, so a constant or default changed in the code without the table fails here.

Name rule (one row per number):
* ``NAME`` is a module constant of ``cpm_abm.economy_abm``;
* ``Economy.field`` and ``Inputs.field`` are the defaults of ``economy_abm.Economy`` and ``core_model.Inputs``;
* ``runner.NAME`` and ``figures.NAME`` are constants of ``scripts/run_economy_population.py`` and
  ``scripts/run_economy_figures.py`` (the grid, seeds, population size and the sourced fixed cost the runs use);
* flattening: an array or tuple has one row per element, named with its index, ``NAME[i]`` (``NAME[i][j]`` for a
  two-dimensional array, row first); a dict has one row per key used, named ``NAME.key``.
Numbers are compared to a relative 1e-12 (a zero exactly); flags and labels are compared as text.
"""
import csv
import re
import unittest
from dataclasses import fields
from functools import reduce
from pathlib import Path

import numpy as np

from cpm_abm import core_model, economy_abm

TABLE = Path(__file__).resolve().parents[1] / "docs" / "PARAMETERS.csv"
TOKEN = re.compile(r"\.?([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]")


def _defaults(cls):
    """A dataclass's field defaults by name."""
    return {f.name: f.default for f in fields(cls)}


def _roots():
    """The scopes a name may start with (``economy_abm`` when it starts with none of them)."""
    from scripts import run_economy_figures, run_economy_population
    return dict(Economy=_defaults(economy_abm.Economy), Inputs=_defaults(core_model.Inputs),
                runner=run_economy_population, figures=run_economy_figures)


def _step(obj, token):
    """One step of a name: a dict key or attribute (``.name``) or an index (``[i]``)."""
    key, index = token
    if index:
        return obj[int(index)]
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def resolve(name, roots=None):
    """The value the code holds under ``name`` (the name rule in the module docstring)."""
    roots = _roots() if roots is None else roots
    tokens = TOKEN.findall(name)
    if "".join(f".{k}" if k else f"[{i}]" for k, i in tokens).lstrip(".") != name:
        raise ValueError(f"not a parameter name: {name!r}")
    start = roots.get(tokens[0][0])
    obj, rest = (economy_abm, tokens) if start is None else (start, tokens[1:])
    return reduce(_step, rest, obj)


def _same(code, text):
    """Whether the table's ``text`` states the code's value: flags and labels as text, numbers to 1e-12."""
    if isinstance(code, (bool, np.bool_, str)):
        return str(code) == text
    value, want = float(code), float(text)
    return value == want or bool(np.isclose(value, want, rtol=1e-12, atol=0.0))


class ParameterTable(unittest.TestCase):

    def test_every_row_matches_the_code(self):
        """Each row's value is the code's value of that name; the table is complete in its columns and has no
        duplicate name."""
        with TABLE.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            self.assertEqual(reader.fieldnames, ["name", "value", "unit", "meaning", "source"])
            rows = list(reader)
        self.assertGreater(len(rows), 100)
        names = [row["name"] for row in rows]
        self.assertEqual(len(names), len(set(names)), "duplicate names in the table")
        self.assertTrue(all(row["value"] and row["unit"] and row["meaning"] and row["source"] for row in rows),
                        "a row has an empty column")
        roots = _roots()
        wrong = [(row["name"], row["value"], resolve(row["name"], roots)) for row in rows
                 if not _same(resolve(row["name"], roots), row["value"])]
        self.assertEqual(wrong, [], "rows whose value differs from the code (name, table, code)")

    def test_the_rule_catches_a_change(self):
        """A table value that differs from the code in the twelfth significant digit is caught, and a name that
        does not follow the rule is refused."""
        self.assertFalse(_same(economy_abm.FAIL_FEE, repr(economy_abm.FAIL_FEE * (1 + 1e-11))))
        self.assertTrue(_same(economy_abm.FAIL_FEE, repr(economy_abm.FAIL_FEE)))
        self.assertEqual(resolve("VEHICLE_APR[1][0]"), economy_abm.VEHICLE_APR[1, 0])
        self.assertEqual(resolve("Economy.burn_in"), 6)
        with self.assertRaises(ValueError):
            resolve("FAIL FEE")


if __name__ == "__main__":
    unittest.main()

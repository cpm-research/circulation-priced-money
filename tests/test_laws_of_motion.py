"""The capital law of the model section (pool capital after a dealing is last month's capital with its realised
return, deflated, plus subscriptions accepted less redemptions paid) recomputed from the stored monthly records of
the development map, in every run and month, for the three arrangements with a pool. Nothing is run."""
import json
import unittest
from pathlib import Path

import numpy as np

from scripts import paper_figures as pf

MAP = Path(__file__).resolve().parents[1] / "results" / "development_map"
SERIES = ("N", "owners_income", "offers", "offers_unused", "exit_paid")
POOL_ARMS = ("U", "M1", "M2")                      # the pool without the charge, CPM, indexed CPM
INDEXED = "M2"                                     # its pool is not deflated: P and its loans keep their real value


@unittest.skipUnless(pf.shipped_files(MAP, "measures.json") or (MAP / "measures.json").exists(),
                     "the development map's monthly records are not shipped here")
class CapitalLawTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        summary = json.loads(pf.stored_text(MAP, "summary.json"))
        cls.inflation = float(summary["economy"]["inflation"])
        cls.runs = []                              # (arrangement, place, seed, series)
        for job in pf.each_job(pf.stored_text(MAP, "measures.json")):
            if job.get("recirculated"):            # the one cell rerun with lenders' interest returned is not the map
                continue
            for arm in POOL_ARMS:
                stored = (job.get("monthly") or {}).get(arm)
                if stored is not None and all(name in stored for name in SERIES):
                    series = {name: np.array([np.nan if v is None else v for v in stored[name]], float)
                              for name in SERIES}
                    cls.runs.append((arm, pf.place(job), job["seed"], series))

    def test_the_map_holds_the_runs(self):
        self.assertEqual(len(self.runs), 105 * 3 * len(POOL_ARMS))

    def test_capital_follows_its_law_in_every_month(self):
        worst = 0.0
        for arm, where, seed, s in self.runs:
            deflator = 1.0 if arm == INDEXED else 1.0 + self.inflation
            ahead = (s["N"][:-1] + s["owners_income"][:-1]) / deflator + s["offers"][1:] - s["offers_unused"][1:] \
                - s["exit_paid"][1:]
            residual = np.abs(s["N"][1:] - ahead)
            self.assertTrue(np.isfinite(residual).all(), (arm, where, seed))
            worst = max(worst, float(residual.max()))
            # Stored values are rounded to twelve decimals, so the law holds to a few parts in a million million.
            self.assertLess(residual.max(), 1e-9, (arm, where, seed))
        self.assertLess(worst, 1e-10)


if __name__ == "__main__":
    unittest.main()

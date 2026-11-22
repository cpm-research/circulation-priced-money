"""The stored wage network (results/population_network) is the population the engine builds for the confirmation
map's first seed: rebuilt here and compared value for value. Nothing is run."""
import json
import unittest
from pathlib import Path

from scripts import paper_figures as pf
from scripts import population_network as pnet

RESULTS = Path(__file__).resolve().parents[1] / "results"
STORED, MAP = RESULTS / "population_network", RESULTS / "confirmation_quote"


@unittest.skipUnless((STORED / "network.json.gz").exists() and pf.shipped_files(MAP, "summary.json"),
                     "the stored network or the map's summary is not shipped here")
class PopulationNetworkTest(unittest.TestCase):
    def setUp(self):
        self.stored = json.loads(pf.stored_text(STORED, "network.json"))

    def test_the_stored_network_is_the_engines_population(self):
        built = pnet.network(MAP)
        for name in ("map", "seed", "n", "wage_to", "spending", "holder", "business"):
            self.assertEqual(self.stored[name], built[name], name)

    def test_each_person_pays_one_wage_to_another_person(self):
        n, to = self.stored["n"], self.stored["wage_to"]
        self.assertEqual(len(to), n)
        self.assertTrue(all(0 <= payee < n and payee != payer for payer, payee in enumerate(to)))


if __name__ == "__main__":
    unittest.main()

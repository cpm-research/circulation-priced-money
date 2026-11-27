"""Tests for wage links, ``Economy.wage_links``, off by default, at small scale.

What is covered
---------------
* "random", the default, is the link drawn by default, bit for bit: one other person drawn uniformly for each payer.
* "one_each": every person pays one wage and receives exactly one, nobody pays itself, the links differ by seed, and
  every other array of the population is the one "random" draws.
* An unknown value is refused.
* A tiny world runs to its end under "one_each" in two arrangements, with the stress year inside it, and the readers
  of the links at the opening (layoff risk by the worker's bracket, the steady stock of spells) read the new links.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import Economy, _World
from cpm_abm.engine.constants import WAGE_LINK_STREAM
from cpm_abm.engine.population import (build_population, income_bracket, layoff_weight, spell_law, spell_stock,
                                       wage_links_one_each)

# A small world whose distress year covers months 3 to 5 of an eight-month run.
SMALL = Economy(n=200, months=6, burn_in=2, distress_start=1, distress_length=3)


class WageLinkTests(unittest.TestCase):
    """Who each wage goes to."""

    def test_random_is_the_link_as_built(self):
        """Under "random" each payer i pays (i + 1 + k) mod n, k uniform on 0 to n - 2 from SeedSequence([seed, 3102]),
        the first draw of that stream, so nobody pays itself."""
        for seed in (20261021, 20261101):
            economy = replace(SMALL, seed=seed)
            extra = np.random.default_rng(np.random.SeedSequence([seed, 3102]))
            expected = (np.arange(economy.n) + 1 + extra.integers(0, economy.n - 1, size=economy.n)) % economy.n
            np.testing.assert_array_equal(build_population(economy)["wage_to"], expected)
        self.assertEqual(Economy().wage_links, "random")

    def test_one_each_pays_and_receives_exactly_one_wage(self):
        """Every person receives exactly one wage and pays exactly one, and nobody pays itself; by default some receive
        none (about 1/e of them)."""
        for n in (2, 3, 200, 1000):
            pop = build_population(replace(SMALL, n=n, wage_links="one_each"))
            wage_to = pop["wage_to"]
            self.assertEqual(wage_to.shape, (n,))
            np.testing.assert_array_equal(np.bincount(wage_to, minlength=n), np.ones(n, int))
            self.assertFalse(np.any(wage_to == np.arange(n)), n)
        as_built = build_population(replace(SMALL, n=1000))["wage_to"]
        none = float(np.mean(np.bincount(as_built, minlength=1000) == 0))
        self.assertAlmostEqual(none, np.exp(-1), delta=0.05)

    def test_one_each_is_drawn_on_its_own_stream_and_differs_by_seed(self):
        """The links are the first permutation without a fixed point on SeedSequence([seed, 3114]), and two seeds give
        different links."""
        economy = replace(SMALL, wage_links="one_each")
        rng = np.random.default_rng(np.random.SeedSequence([economy.seed, WAGE_LINK_STREAM]))
        while True:
            expected = rng.permutation(economy.n)
            if not np.any(expected == np.arange(economy.n)):
                break
        np.testing.assert_array_equal(wage_links_one_each(economy), expected)
        np.testing.assert_array_equal(build_population(economy)["wage_to"], expected)
        other = build_population(replace(economy, seed=20261101))["wage_to"]
        self.assertFalse(np.array_equal(other, expected))

    def test_one_each_moves_no_other_array_of_the_population(self):
        """Wealth, spending, cycles, cards, scores, pay days, earned-wage access, crypto and card lines are the arrays
        "random" draws; only the links differ."""
        for seed in (20261021, 20261101):
            random = build_population(replace(SMALL, seed=seed))
            one_each = build_population(replace(SMALL, seed=seed, wage_links="one_each"))
            self.assertEqual(sorted(random), sorted(one_each))
            for key in random:
                if key != "wage_to":
                    np.testing.assert_array_equal(random[key], one_each[key], err_msg=key)
            self.assertFalse(np.array_equal(random["wage_to"], one_each["wage_to"]))
            # Earned-wage access stays with wage earners: everyone earns one under one wage each.
            self.assertTrue(np.all(np.bincount(one_each["wage_to"], minlength=SMALL.n)[one_each["ewa"]] == 1))

    def test_unknown_values_are_refused(self):
        for value in ("uniform", "one-each", "", None, 1):
            with self.assertRaises(ValueError, msg=value):
                Economy(wage_links=value)

    def test_a_tiny_world_runs_to_the_end_under_one_each(self):
        """In two arrangements, with the stress year at 2 points and normal job loss on, a world under one wage each
        runs to its end with the conserved edge closing; at the opening each job's layoff risk is read from its own
        worker under the new links, and the steady stock of spells is drawn at those risks."""
        economy = replace(SMALL, distress=0.02, edge="conserved", purchases="poisson_size", statement_dates="own",
                          distress_purchases=0.0174)
        for arm in ("S0", "M1"):
            w = _World(Inputs(), 0.4, replace(economy, wage_links="one_each"), arm)
            wage_to = w.pop["wage_to"]
            weight = layoff_weight()[income_bracket(w.pop["spending"])[wage_to]]
            np.testing.assert_allclose(w.layoff_rate, weight / weight.mean())
            self.assertGreater(economy.job_loss, 0)
            stock = spell_stock(np.random.default_rng(np.random.SeedSequence([economy.seed, 23])),
                                economy.job_loss * w.layoff_rate, *spell_law(economy))
            np.testing.assert_array_equal(w.spell_start, stock[0])
            np.testing.assert_array_equal(w.spell_end, stock[1])
            series = w.run()["series"]
            as_built = _World(Inputs(), 0.4, economy, arm).run()["series"]
            self.assertEqual(len(series["wealth_change"]), economy.burn_in + economy.months, arm)
            # The conserved edge still closes, and a record is undefined (a ratio with nothing below it, say) exactly
            # where it is undefined by default.
            np.testing.assert_allclose(series["wealth_change"] - series["valuation"], 0.0, atol=1e-9, err_msg=arm)
            self.assertEqual(undefined(series), undefined(as_built), arm)


def undefined(series):
    """The records of a run's series with a value that is not finite."""
    return {key for key, value in series.items()
            if np.asarray(value).dtype.kind == "f" and not np.all(np.isfinite(np.asarray(value, float)))}


if __name__ == "__main__":
    unittest.main()

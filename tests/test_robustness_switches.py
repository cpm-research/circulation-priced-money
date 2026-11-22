"""Tests for the robustness switches (docs/ROBUSTNESS_PLAN.md, section 5), each off by default, at small scale.

What is covered
---------------
* The buffer review share: a person re-chooses its buffer only when its review draw is below alpha, the draws on a
  stream of their own; the base draws nothing.
* The joining rule: the threshold rule on a few people, a person with no partners never joining, as in the base;
  uniform thresholds giving the base's mean chance; measured thresholds' share met at a contact share of 5% and share
  above 1; a common threshold of 0.2 letting nobody join by imitation below it.
* Sellers: on the ring the person at position 100 buys only from positions 84 to 116, never from itself, and every
  person's expected number of sales is the same; with hubs at 4,000 people the largest seller takes about 0.9% of
  sales and nobody buys from itself; the month's partners are the sellers used; the base's draws stay as they are.
* Launch placement: a neighbourhood and the largest sellers, each with exactly round(a0 n) people, nested across
  launch levels; every combination the plan does not define refused.
* Pairing: the network, thresholds, sellers and launch set are the same in every arm.
* The runner: the options, the seeds they may run on, the run record naming the variant, and the stress boundary's
  finer distress levels read end to end on a tiny side run.

That every value a run produces with every switch at its default is unchanged bit for bit is checked outside the
suite, against the commit before the switches.
"""
import contextlib
import io
import json
import tempfile
import unittest
import warnings
from dataclasses import asdict, replace
from pathlib import Path
from unittest import mock

import numpy as np
from scipy.stats import norm

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import (BUFFER_REVIEW_STREAM, HUB_WEIGHT_EXPONENT, RING_SIDE, RING_STREAM,
                                 SARAFU_DEGREE_EXPONENT, SELLER_STREAMS, THRESHOLD_STREAM, Economy, _World,
                                 build_network, build_population, review, reviewed_buffer, threshold_chance,
                                 thresholds)

ARMS = ("S0", "M0", "U", "M1", "M2")
A0S = (0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8)
XI0, XI1 = Inputs().xi0, Inputs().xi1


def worlds(economy, a0=0.2):
    """One world of every arm on ``economy``, nothing run yet."""
    return {arm: _World(Inputs(), a0, economy, arm) for arm in ARMS}


class BufferReviewTests(unittest.TestCase):
    """The buffer review share alpha (5.1)."""

    def test_alpha_one_half_with_draws_three_and_seven_tenths(self):
        """The plan's hand case: alpha 0.5, draws 0.3 and 0.7: the first re-chooses, the second keeps its buffer."""
        np.testing.assert_array_equal(review(np.array([4.0, 5.0]), np.array([1.0, 2.0]), np.array([0.3, 0.7]), 0.5),
                                      [4.0, 2.0])

    def test_the_base_takes_every_choice_and_draws_nothing(self):
        """With alpha 1 the chosen buffer itself comes back, no stream is opened; below 1 the draws are the month's
        own stream, SeedSequence([seed, 43, month])."""
        chosen, kept = np.arange(5.0), -np.ones(5)
        with mock.patch("numpy.random.default_rng") as rng:
            self.assertIs(reviewed_buffer(chosen, kept, Economy(n=5), 3), chosen)
        rng.assert_not_called()
        self.assertEqual(BUFFER_REVIEW_STREAM, 43)
        economy = Economy(n=5, buffer_review=0.5)
        draw = np.random.default_rng(np.random.SeedSequence([economy.seed, 43, 3])).random(5)
        np.testing.assert_array_equal(reviewed_buffer(chosen, kept, economy, 3), np.where(draw < 0.5, chosen, kept))

    def test_people_who_do_not_review_keep_last_months_buffer(self):
        """In a short run each person whose draw is at or above alpha holds last month's buffer after the dealing,
        month 0 keeps the base's starting buffer, and some people do re-choose."""
        economy = Economy(n=60, burn_in=2, months=3, buffer_review=0.5)
        world, moved = _World(Inputs(), 0.2, economy, "M1"), 0
        start = world.buffer.copy()
        for month in range(world.total):
            before = world.buffer.copy()
            world.month(month)
            if month == 0:
                np.testing.assert_array_equal(world.buffer, start)
                continue
            draw = np.random.default_rng(np.random.SeedSequence([economy.seed, 43, month])).random(economy.n)
            np.testing.assert_array_equal(world.buffer[draw >= 0.5], before[draw >= 0.5])
            moved += int((world.buffer[draw < 0.5] != before[draw < 0.5]).sum())
        self.assertGreater(moved, 0)


class JoiningTests(unittest.TestCase):
    """The joining rule (5.2)."""

    def test_the_threshold_rule_on_a_few_people(self):
        """xi0 + xi1 where the contact share is at least the threshold, xi0 below it; with no partners (NaN) the
        chance is undefined and nobody joins, whatever the draw, as in the base."""
        contact = np.array([0.0, 0.19, 0.2, 0.5, np.nan])
        chance = threshold_chance(contact, np.full(5, 0.2), XI0, XI1)
        np.testing.assert_array_equal(chance[:4], [XI0, XI0, XI0 + XI1, XI0 + XI1])
        self.assertTrue(np.isnan(chance[4]))
        self.assertFalse(bool(np.zeros(5)[4] < chance[4]))
        self.assertFalse(bool(0.0 < XI0 + XI1 * np.nan))                 # the base: the same person never joins

    def test_a_common_threshold_of_one_fifth_admits_nobody_by_imitation_below_it(self):
        """With every threshold 0.2, at any contact share below it the chance is xi0 alone, so a person joins only
        when its draw is below xi0; from 0.2 up it is xi0 + xi1."""
        common = thresholds(0.2, 1000, 1)
        np.testing.assert_array_equal(common, np.full(1000, 0.2))
        contact = np.linspace(0.0, 0.199, 1000)
        draw = np.random.default_rng(5).random(1000) * (XI0 + XI1)
        joined = draw < threshold_chance(contact, common, XI0, XI1)
        np.testing.assert_array_equal(joined, draw < XI0)
        np.testing.assert_array_equal(threshold_chance(np.array([0.2, 0.7]), common[:2], XI0, XI1), XI0 + XI1)

    def test_uniform_thresholds_give_the_base_mean_chance(self):
        """Uniform thresholds on 0 to 1: at a contact share c the share met is c, so the mean chance is the base's
        xi0 + xi1 c. 200,000 thresholds on a fixed seed: the mean chance is within 1.5e-4 of the base's at every c
        tried (the standard error is at most xi1 x 0.5 / 447, 3.5e-5)."""
        drawn = thresholds("uniform", 200_000, 20261021)
        for c in (0.02, 0.05, 0.2, 0.5, 0.8):
            mean = threshold_chance(np.full(drawn.size, c), drawn, XI0, XI1).mean()
            self.assertAlmostEqual(mean, XI0 + XI1 * c, delta=1.5e-4)

    def test_measured_thresholds_at_a_contact_share_of_five_percent(self):
        """Log-normal with log-mean -2 and log-spread 1: at c = 0.05 the threshold is met for Phi(ln 0.05 + 2) = 0.16
        of people, so the mean chance is 0.0076 a month against the base's 0.0041; 2.3% of thresholds exceed 1.
        200,000 thresholds on a fixed seed, within 0.005 of each share."""
        met = norm.cdf(np.log(0.05) + 2)
        self.assertEqual(round(met, 2), 0.16)
        self.assertEqual((round(XI0 + XI1 * met, 4), round(XI0 + XI1 * 0.05, 4)), (0.0076, 0.0041))
        self.assertEqual(round(1 - norm.cdf(2), 3), 0.023)
        drawn = thresholds("measured", 200_000, 20261021)
        self.assertAlmostEqual(float((drawn <= 0.05).mean()), met, delta=0.005)
        self.assertAlmostEqual(float((drawn > 1).mean()), 1 - norm.cdf(2), delta=0.005)
        self.assertAlmostEqual(float(np.exp(np.log(drawn).mean())), np.exp(-2), delta=0.002)

    def test_the_common_thresholds_hand_case_in_a_well_mixed_population(self):
        """Below the threshold only innovation works, so reaching 0.2 takes ln((1 - a0) / 0.8) / xi0 months: 69 from
        a launch of 5% and 47 from 10%."""
        self.assertEqual([round(np.log((1 - a0) / 0.8) / XI0) for a0 in (0.05, 0.1)], [69, 47])

    def test_thresholds_are_fixed_drawn_on_their_own_stream_and_shared_by_every_arm(self):
        """The thresholds are drawn once, on SeedSequence([seed, 3107]), and are the same in all five arms."""
        economy = Economy(n=60, joining="threshold", thresholds="measured")
        made = worlds(economy)
        self.assertEqual(THRESHOLD_STREAM, 3107)
        expected = np.random.default_rng(np.random.SeedSequence([economy.seed, 3107])).lognormal(-2.0, 1.0, 60)
        for world in made.values():
            np.testing.assert_array_equal(world.network.threshold, expected)
        self.assertIsNone(_World(Inputs(), 0.2, Economy(n=60), "M1").network.threshold)


class SellerTests(unittest.TestCase):
    """Sellers on the ring and with hubs (5.3)."""

    def test_the_person_at_position_one_hundred_buys_only_from_84_to_116(self):
        """With local share 1 the person at position 100 buys only from positions 84 to 116, never from itself, and
        from each of those 32 positions; positions are a random permutation drawn on SeedSequence([seed, 3108])."""
        network = build_network(Economy(n=400, sellers="ring"), np.ones(400))
        self.assertEqual((RING_STREAM, RING_SIDE), (3108, 16))
        np.testing.assert_array_equal(network.position,
                                      np.random.default_rng(np.random.SeedSequence([20261021, 3108])).permutation(400))
        buyer = np.full(20_000, network.at[100])
        sold = network.position[network.draw_sellers(buyer, buyer, 20261021, "service", 0)]
        self.assertEqual(set(sold.tolist()), set(range(84, 117)) - {100})

    def test_every_person_expects_the_same_number_of_sales_on_the_ring(self):
        """Each position is among the 32 neighbours of exactly 32 others, so at any local share every person's
        expected number of sales is the number of purchases a person makes. 100 people buying 4,000 times each:
        every count within six standard errors (6 x 63) of 4,000."""
        for local in (1.0, 0.35):
            network = build_network(Economy(n=100, sellers="ring", local_share=local), np.ones(100))
            buyer = np.repeat(np.arange(100), 4000)
            sold = network.draw_sellers(buyer, buyer, 20261021, "service", 0)
            self.assertFalse(bool((sold == buyer).any()))
            self.assertLess(np.abs(np.bincount(sold, minlength=100) - 4000).max(), 6 * np.sqrt(4000))

    def test_the_largest_hub_takes_about_nine_tenths_of_a_percent_of_sales(self):
        """At 4,000 people a seller is drawn with chance proportional to k^(-0.526) among everyone but the buyer,
        k the rank of initial spending: the largest spender takes about 0.9% of 32 purchases a person (exactly
        0.945% in expectation), nobody buys from itself, and the weights fall with spending."""
        self.assertAlmostEqual(HUB_WEIGHT_EXPONENT, 1 / (SARAFU_DEGREE_EXPONENT - 1), places=15)
        self.assertEqual(round(HUB_WEIGHT_EXPONENT, 3), 0.526)
        spending = build_population(Economy(n=4000))["spending"]
        network = build_network(Economy(n=4000, sellers="hubs"), spending)
        weight = network.weight
        top = int(np.argmax(spending))
        self.assertEqual(int(np.argmax(weight)), top)
        self.assertEqual(weight[top], 1.0)
        buyer = np.repeat(np.arange(4000), 32)
        sold = network.draw_sellers(buyer, buyer, 20261021, "service", 0)
        self.assertFalse(bool((sold == buyer).any()))
        share = float((sold == top).mean())
        expected = float(np.delete(weight[top] / (weight.sum() - weight), top).sum() / 4000)
        self.assertEqual(round(expected, 3), 0.009)
        self.assertAlmostEqual(share, expected, delta=4 * np.sqrt(expected / buyer.size))

    def test_hub_draws_are_exact_on_a_small_case(self):
        """Three people with weights 1, 1/2 and 1/4 (as ranks give with exponent 1): person 0 buys from 1 with chance
        2/3 and from 2 with 1/3, within 0.005 on 200,000 draws."""
        from cpm_abm.economy_abm import hub_sellers
        sold = hub_sellers(np.random.default_rng(3), np.zeros(200_000, int), np.array([1.0, 0.5, 0.25]))
        self.assertAlmostEqual(float((sold == 1).mean()), 2 / 3, delta=0.005)
        self.assertEqual(set(sold.tolist()), {1, 2})

    def test_the_base_draws_stay_and_the_months_partners_are_the_sellers_used(self):
        """Under ring and hubs the month's buyers, amounts, card flags and kinds are those of the base (its draws are
        made and set aside); the service sellers are the world's own, from SeedSequence([seed, 47, month]); the
        month's partners the joining rule reads are those sellers; wages stay with the population's uniform links.
        Every arm builds the same obligations."""
        self.assertEqual(SELLER_STREAMS, dict(service=47, shock=53, term=59))
        base = Economy(n=60, burn_in=2, months=2, shocks=True)
        rows = lambda world: sorted(zip(world.ob["buyer"].tolist(), world.ob["amount"].tolist(),
                                        world.ob["card"].tolist(), world.ob["kind"].tolist()))

        def obligations(world):
            """The world's month-0 obligations, outside a month (its accumulators open empty)."""
            world.acc = {}
            world._obligations(0)

        reference = _World(Inputs(), 0.2, base, "M1")
        obligations(reference)
        for sellers in ("ring", "hubs"):
            economy = replace(base, sellers=sellers)
            made = worlds(economy)
            for world in made.values():
                obligations(world)
            world = made["M1"]
            self.assertEqual(rows(world), rows(reference))
            services = economy.n * economy.bundles
            buyer = world.month_pairs[0][:services]
            np.testing.assert_array_equal(world.month_pairs[1][:services],
                                          world.network.draw_sellers(buyer, None, economy.seed, "service", 0))
            np.testing.assert_array_equal(world.month_pairs[1][services:], reference.month_pairs[1][services:])
            np.testing.assert_array_equal(world.pop["wage_to"], reference.pop["wage_to"])
            for other in made.values():
                for key in world.ob:
                    np.testing.assert_array_equal(other.ob[key], world.ob[key])
                for key in world.req:
                    np.testing.assert_array_equal(other.req[key], world.req[key])
                np.testing.assert_array_equal(other.month_pairs[1], world.month_pairs[1])


class LaunchTests(unittest.TestCase):
    """Launch placement (5.4) and the combinations refused."""

    def test_a_neighbourhood_and_the_largest_sellers_are_nested_launch_sets_of_the_right_size(self):
        """round(a0 n) people at every launch level, each level's set inside the next: on the ring the people on
        positions 0 up to that count, with hubs the largest spenders."""
        n = 400
        spending = build_population(Economy(n=n))["spending"]
        start = np.random.default_rng(0).random(n)
        for sellers, launch in (("ring", "neighbourhood"), ("hubs", "largest")):
            network = build_network(Economy(n=n, sellers=sellers, launch=launch), spending)
            sets = [network.launch_set(launch, a0, start) for a0 in A0S]
            for a0, members in zip(A0S, sets):
                self.assertEqual(int(members.sum()), int(round(a0 * n)))
            for small, large in zip(sets, sets[1:]):
                self.assertTrue(bool((large | ~small).all()))
            if launch == "neighbourhood":
                np.testing.assert_array_equal(np.sort(network.position[sets[2]]), np.arange(80))
            else:
                self.assertGreaterEqual(spending[sets[2]].min(), spending[~sets[2]].max())

    def test_every_arm_launches_the_same_people(self):
        """At launch the members are the launch set, the same in every arm that launches."""
        for sellers, launch in (("ring", "neighbourhood"), ("hubs", "largest")):
            economy = Economy(n=60, burn_in=1, months=1, sellers=sellers, launch=launch)
            launched = []
            for arm, world in worlds(economy, a0=0.3).items():
                world.month(0)
                world.month(1)
                if arm != "S0":
                    launched.append(world.status[1].copy())
            self.assertEqual(int(launched[0].sum()), 18)
            for status in launched[1:]:
                np.testing.assert_array_equal(status, launched[0])

    def test_combinations_the_plan_does_not_define_are_refused(self):
        """A neighbourhood launch needs the ring and a largest-first launch needs hubs; thresholds are read only under
        the threshold rule and a local share only on the ring; misspelt or out-of-range settings are refused."""
        refused = [dict(launch="neighbourhood"), dict(launch="neighbourhood", sellers="hubs"),
                   dict(launch="largest"), dict(launch="largest", sellers="ring"), dict(launch="clustered"),
                   dict(sellers="lattice"), dict(joining="cascade"), dict(thresholds="measured"),
                   dict(thresholds=0.2), dict(joining="threshold", thresholds="normal"),
                   dict(joining="threshold", thresholds=1.5), dict(joining="threshold", thresholds=True),
                   dict(local_share=0.35), dict(sellers="hubs", local_share=0.35),
                   dict(sellers="ring", local_share=1.5), dict(buffer_review=0.0), dict(buffer_review=1.5),
                   dict(sellers="ring", n=32)]
        for settings in refused:
            with self.subTest(**settings), self.assertRaises(ValueError):
                Economy(**settings)
        for settings in (dict(sellers="ring", launch="neighbourhood", local_share=0.35),
                         dict(sellers="hubs", launch="largest", joining="threshold", thresholds="measured"),
                         dict(joining="threshold", thresholds=0.3), dict(buffer_review=0.153),
                         dict(sellers="ring", n=33)):
            Economy(**settings)

    def test_defaults_are_the_base(self):
        """Every switch is off by default, and off it builds nothing."""
        economy = Economy()
        self.assertEqual((economy.buffer_review, economy.joining, economy.thresholds, economy.sellers,
                          economy.local_share, economy.launch), (1.0, "linear", "uniform", "uniform", 1.0, "scattered"))
        network = build_network(Economy(n=50), np.ones(50))
        self.assertEqual([network.position, network.at, network.weight, network.threshold], [None] * 4)
        base = np.arange(5)
        self.assertIs(network.draw_sellers(base, base, 1, "service", 0), base)


class RunnerTests(unittest.TestCase):
    """The runner's options, their seeds and records, and the stress boundary's levels."""

    def test_the_options_and_the_development_seeds_rule(self):
        """Each switch has an option defaulting to the base; the switches and the stress boundary's levels run on
        development seeds only, and a combination the plan does not define is refused before anything runs; the dry
        run names the switches."""
        import scripts.run_economy_population as population
        args = population.options().parse_args(["--seeds", "development"])
        self.assertEqual(population.side_settings(args), ([], []))
        given = population.options().parse_args(
            ["--seeds", "development", "--buffer-review", "0.5", "--joining", "threshold", "--thresholds", "0.2",
             "--sellers", "ring", "--local-share", "0.35", "--launch", "neighbourhood", "--distress", "0", "0.017"])
        self.assertEqual([getattr(given, name) for name in population.SWITCHES],
                         [0.5, "threshold", 0.2, "ring", 0.35, "neighbourhood"])
        self.assertEqual(population.side_settings(given)[1], [0.017])
        self.assertEqual(population.options().parse_args(["--seeds", "development", "--thresholds", "measured"])
                         .thresholds, "measured")

        def launch(*words):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch("sys.argv", ["run_economy_population.py", *words, "--dry-run"]), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    population.main()
                except SystemExit:
                    return None, err.getvalue()
            return json.loads(out.getvalue().split("cells (r_out")[0]), err.getvalue()

        for words in (["--seeds", "confirmation", "--sellers", "hubs"],
                      ["--seeds", "confirmation", "--distress", "0", "0.016"],
                      ["--seeds", "development", "--launch", "largest"],
                      ["--seeds", "development", "--thresholds", "0.2"]):
            printed, err = launch(*words)
            self.assertIsNone(printed, words)
            self.assertIn("error", err)
        printed, _ = launch("--seeds", "development", "--sellers", "hubs", "--launch", "largest", "--r_out", "0.044",
                            "--distress", "0")
        self.assertEqual(printed["switches"], dict(buffer_review=1.0, joining="linear", thresholds="uniform",
                                                   sellers="hubs", local_share=1.0, launch="largest"))
        self.assertEqual(printed["jobs"], 21)

    def test_the_run_record_names_the_variant(self):
        """Every stored file opens with the run record, whose Economy holds each switch."""
        from scripts.run_economy_population import run_record
        economy = Economy(n=40, sellers="ring", local_share=0.35, launch="neighbourhood", joining="threshold",
                          thresholds=0.2, buffer_review=0.5)
        stored = json.loads(json.dumps(run_record(economy, "development", 10)))["economy"]
        self.assertEqual({key: stored[key] for key in ("buffer_review", "joining", "thresholds", "sellers",
                                                       "local_share", "launch")},
                         dict(buffer_review=0.5, joining="threshold", thresholds=0.2, sellers="ring", local_share=0.35,
                              launch="neighbourhood"))

    def test_the_stress_boundary_levels_sit_beside_the_grid(self):
        """0.016 to 0.019 may be selected beside the grid's levels, in order, and are never part of the full grid;
        any other value outside the grid is still refused."""
        from scripts.run_economy_population import DISTRESS, GRID, SEEDS, selected, tasks_for
        from cpm_abm.experiment.grid import SIDE_DISTRESS
        self.assertEqual(SIDE_DISTRESS, (0.016, 0.017, 0.018, 0.019))
        self.assertEqual(selected(), GRID)
        self.assertEqual(GRID["distress"], DISTRESS)
        chosen = selected((0.044,), (0.2, 0.3, 0.45), (0.019, 0.0, 0.017, 0.016, 0.018))
        self.assertEqual(chosen["distress"], (0.0, 0.016, 0.017, 0.018, 0.019))
        self.assertEqual(len(tasks_for(SEEDS["development"], 4000, chosen)), 45)
        for value in (0.0165, 0.021):
            with self.assertRaises(ValueError):
                selected(distress=(value,))

    def test_a_tiny_stress_boundary_run_is_read_end_to_end(self):
        """Jobs at level 0 and at 1.7 points on a tiny economy: the cell at 1.7 points carries its paired reading
        against level 0, the claim statistics read it as a stress leg, and the stores are written with the levels
        selected."""
        from scripts.run_economy_population import claim_statistics, decide_cells, job, run_record, selected, \
            write_stores
        economy = Economy(n=40, burn_in=2, months=12, distress_start=3, distress_length=3)
        selection = selected((0.044,), (0.6,), (0.0, 0.017))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            jobs = [job((0.044, 0.6, level, 20261021, 40, False), economy) for level in (0.0, 0.017)]
            cells, recirculated = decide_cells(jobs, selection, economy, 40)
            statistics = claim_statistics(cells, jobs, economy)
        self.assertEqual([c["distress"] for c in cells], [0.0, 0.017])
        self.assertEqual(cells[1]["distress_reading"]["seeds_paired"], 1)
        self.assertIn("stress_leg", cells[1]["M1"])
        with tempfile.TemporaryDirectory() as folder:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                write_stores(Path(folder), run_record(economy, "development", 10, selection), jobs, cells,
                             recirculated, statistics)
            summary = json.loads((Path(folder) / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["selected"]["distress"], [0.0, 0.017])


if __name__ == "__main__":
    unittest.main()

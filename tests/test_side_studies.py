"""Tests for the side studies of the second run, each a setting of ``Economy`` off by default, at small scale.

What is covered
---------------
* Savers who wait for a record (``sceptical_share``): each person fixed for the run as a record-reader below the
  share on a stream of its own, the readers nested across shares; an example of what each reader compares; at a
  share of 0 a run is the quote reading's and at 1 the realised reading's, bit for bit; the default draws nothing.
* Owners who react to unpaid exits (``owners_follow``): the trigger set only by a dealing that leaves an executed
  exit unpaid after its offers; who files at the next dealing under each value; the share filed six months after
  the trigger at exact indifference (0.38, 0.63 and 1.00); the default, "none", under which nobody reacts.
* Distress years that arrive at random (``distress_dates``, ``distress_expected``): an example of the drawing
  rule; no overlap; nesting across dials 1, 2 and 4; the mean number of years at a dial a quarter of the dial times
  the mean at 4; the Poisson table of the share of seeds meeting each number of years; the same dates in every arm;
  a run with one random year equal to the dated run with that year bit for bit; the fork at the distress year equal
  to direct runs; the default dated calendar.
* With each setting on, wealth accounting is exact every month.
* Every setting refuses values and combinations it does not define.
"""
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cpm_abm.core_model import Inputs  # noqa: E402
from cpm_abm.economy_abm import (DISTRESS_DIAL_MAX, DISTRESS_KEEP_STREAM, DISTRESS_START_STREAM, EPS,  # noqa: E402
                                 SCEPTIC_STREAM, Economy, _World, distress_calendar, distress_years, simulate)
from tests.test_economy_abm import FORCED, ForcedRun, controlled_world, earning  # noqa: E402

ARMS = ("S0", "M0", "U", "M1", "M2")


def balanced(series):
    """Whether the conservation identity holds every month: the change in net wealth is the outside flow, the
    valuation change and inflation's, as the engine's own accounting tests read it."""
    np.testing.assert_allclose(series["wealth_change"], series["external"] + series["valuation"] + series["inflation"],
                               atol=1e-12)
    return True


class RecordReaderTests(unittest.TestCase):
    """The share of savers who wait for a record."""

    def test_readers_are_drawn_once_below_the_share_and_nested(self):
        """One draw a person for the run on SeedSequence([seed, 3109]); a record-reader where it is below the share,
        so a higher share's readers contain a lower one's; the default opens no stream and has no readers."""
        self.assertEqual(SCEPTIC_STREAM, 3109)
        economy = Economy(n=200)
        draw = np.random.default_rng(np.random.SeedSequence([economy.seed, SCEPTIC_STREAM])).random(200)
        readers = {}
        for share in (0.0, 0.1, 0.35, 0.6, 1.0):
            world = _World(Inputs(), 0.2, replace(economy, sceptical_share=share), "M1")
            readers[share] = world.record_reader
            np.testing.assert_array_equal(world.record_reader, draw < share)
        self.assertFalse(readers[0.0].any())
        self.assertTrue(readers[1.0].all())
        shares = sorted(readers)
        for low, high in zip(shares, shares[1:]):
            self.assertTrue(np.all(readers[low] <= readers[high]))
        self.assertIsNone(_World(Inputs(), 0.2, economy, "M1").record_reader)
        # The same readers in every arm.
        for arm in ARMS:
            np.testing.assert_array_equal(_World(Inputs(), 0.2, replace(economy, sceptical_share=0.35), arm)
                                          .record_reader, readers[0.35])

    def test_each_reader_compares_its_own_reading(self):
        """A record-reader compares the pool's track record and everyone else the quote.

        Example: a quote of 0.004 a month, a track record of 0.0025 and readers [True, False, ...]: the first
        compares 0.0025 and the rest 0.004; with no track record everyone compares the quote. With no share set,
        everyone compares the quote under the default reading and the record under ``entry_reads`` "realised"."""
        w = controlled_world()
        w.held_path[0, 1], w.r_owners[0] = 100.0, 0.0025          # the pool's last closed month
        w.economy = replace(w.economy, sceptical_share=0.5)
        w.record_reader = np.arange(10) == 0
        got = w._entry_nominal(1, 0.004)
        np.testing.assert_array_equal(got, np.where(np.arange(10) == 0, 0.0025, 0.004))
        self.assertEqual(w._entry_nominal(0, 0.004), 0.004)        # the first dealing has no track record
        w.economy = replace(w.economy, sceptical_share=None)
        self.assertEqual(w._entry_nominal(1, 0.004), 0.004)
        w.economy = replace(w.economy, entry_reads="realised")
        self.assertEqual(w._entry_nominal(1, 0.004), 0.0025)

    def test_a_share_of_zero_is_the_quote_reading_and_one_the_realised_bit_for_bit(self):
        """In a forced run, where the quote and the realised record lead to different capital, a share of 0 gives
        the quote reading's run and a share of 1 the realised reading's, bit for bit; a share between gives a third
        run, and wealth accounting is exact in it."""
        runs = {}
        for name, fields in (("quote", dict()), ("realised", dict(entry_reads="realised")),
                             ("none", dict(sceptical_share=0.0)), ("all", dict(sceptical_share=1.0)),
                             ("half", dict(sceptical_share=0.5))):
            world = ForcedRun(Inputs(), 0.6, replace(FORCED, **fields), "M1")
            runs[name] = (world, world.run())
        quote, realised = runs["quote"][0], runs["realised"][0]
        self.assertFalse(np.array_equal(quote.held_path, realised.held_path))   # the two readings differ here
        for name, built in (("none", "quote"), ("all", "realised")):
            np.testing.assert_array_equal(runs[name][0].held_path, runs[built][0].held_path)
            np.testing.assert_array_equal(runs[name][0].wealth_path, runs[built][0].wealth_path)
            for key, value in runs[built][1]["series"].items():
                np.testing.assert_array_equal(runs[name][1]["series"][key], value, err_msg=key)
        self.assertTrue(balanced(runs["half"][1]["series"]))


class OwnersFollowTests(unittest.TestCase):
    """Owners who react to unpaid exits."""

    def owned(self, follow, unpaid):
        """Four owners of 1 share each at NAV 1 earning their own rate exactly, so none files on its return: owner 0's
        review comes up and owners 1 to 3's do not; owner 3 has a standing request. ``unpaid`` is the trigger."""
        w = controlled_world()
        w.economy = replace(w.economy, owners_follow=follow, leave_noise=0.0)
        w.shares[:4], w.nav_ps, w.pool_cash, w.Q, w.had_owners, w.launched = 1.0, 1.0, 4.0, 10.0, True, True
        w.pool_alternative[:] = 0.001 - w.economy.owner_spread
        earning(w, 0.001)
        w.exit_start[3], w.exit_left[3], w.exit_nav[3] = 0, 1.0, 1.0      # filed at month 0, due at month 2
        w.owner_draws = np.where(np.arange(10) == 0, 0.0, 0.9), np.full(10, 0.99)
        w.exit_left_unpaid = unpaid
        return w

    def test_who_files_at_the_dealing_after_an_unpaid_exit(self):
        """With the trigger standing: under "none" nobody new files (owner 3's request, not reviewed, stands); under
        "reviewers" owner 0, whose review came up, files too; under "all" every owner wants out. Without the trigger
        every value files as "none" does."""
        owners = np.arange(10) < 4
        for follow, want in (("none", [3]), ("reviewers", [0, 3]), ("all", [0, 1, 2, 3])):
            w = self.owned(follow, True)
            w._exits(1, owners)
            np.testing.assert_array_equal(np.flatnonzero(w.exit_want), want, err_msg=follow)
            w = self.owned(follow, False)
            w._exits(1, owners)
            np.testing.assert_array_equal(np.flatnonzero(w.exit_want), [3], err_msg=follow)

    def test_the_trigger_is_an_executed_exit_the_dealing_left_unpaid(self):
        """An owner's request falling due at a dealing with no pool cash and no offers is left unpaid, which sets the
        trigger; with the cash to pay it, or once it is paid, the trigger is off at the next dealing."""
        def dealt(cash):
            w = self.owned("none", False)
            w.pool_cash = cash
            w.owner_draws = np.ones(10), np.ones(10)                   # nobody reviews
            w._dealing(2)
            return w
        w = dealt(0.0)
        self.assertGreater(float(w.exit_unpaid[3]), 0.0)
        self.assertTrue(w.exit_left_unpaid)
        w.pool_cash = 5.0
        w.owner_draws = np.ones(10), np.ones(10)
        w._dealing(3)                                                  # now paid in full
        self.assertFalse(w.exit_left_unpaid)
        self.assertFalse(dealt(4.0).exit_left_unpaid)

    def test_the_hand_case_share_filed_six_months_on(self):
        """The rule's rates at exact indifference, where the logistic gives one half: each month a share upsilon
        reviews; under "none" half the reviewers file, under "reviewers" all of them, under "all" every owner. Six
        months after the trigger: 0.38, 0.63 and 1.00. The engine's own leaving chance at the indifference point is
        one half."""
        upsilon = Inputs().upsilon
        self.assertAlmostEqual(upsilon, 1 - math.exp(-0.166), places=12)
        w = controlled_world()
        # An experience of -0.01 a month against a leaving cost of 0.01: the gap the logistic reads is zero.
        half = float(w._leave_chance(np.full(w.n, -0.01), np.full(w.n, 0.01))[0])
        self.assertAlmostEqual(half, 0.5, places=15)
        monthly = dict(none=upsilon * half, reviewers=upsilon, all=1.0)
        filed = {rule: 1 - (1 - rate) ** 6 for rule, rate in monthly.items()}
        self.assertEqual([round(filed[rule], 2) for rule in ("none", "reviewers", "all")], [0.38, 0.63, 1.00])

    def test_reacting_owners_in_a_forced_run_keep_the_books_exact(self):
        """In the forced run, whose exits run past pool cash, the trigger comes up; owners who react ask for more than
        under "none", and more under "all" than under "reviewers"; wealth accounting is exact under each, and "none"
        is the default run bit for bit."""
        built = ForcedRun(Inputs(), 0.6, FORCED, "M1").run()["series"]
        requested = {}
        for follow in ("none", "reviewers", "all"):
            series = ForcedRun(Inputs(), 0.6, replace(FORCED, owners_follow=follow), "M1").run()["series"]
            self.assertTrue(balanced(series))
            requested[follow] = float(series["exit_requested"].sum())
            if follow == "none":
                for key, value in built.items():
                    np.testing.assert_array_equal(series[key], value, err_msg=key)
        self.assertLess(requested["none"], requested["reviewers"])
        self.assertLess(requested["reviewers"], requested["all"])


class RandomDistressTests(unittest.TestCase):
    """Distress years that arrive at random."""

    def test_the_drawing_rule_hand_case(self):
        """A distress year starts in a month whose start draw is below 4 / months, unless it lies inside the year
        before; a year is kept at a dial where its keeping draw is below the dial over 4.

        Example: 48 months, years of 12, start draws below 4 / 48 in months 3, 9 and 20: years from months 3 and 20
        (month 9 lies inside the first); keeping draws of 0.3 and 0.8 keep the first at a dial of 2 and both at 4,
        none at 0. The streams are SeedSequence([seed, 3110]) and ([seed, 3111])."""
        self.assertEqual((DISTRESS_START_STREAM, DISTRESS_KEEP_STREAM, DISTRESS_DIAL_MAX), (3110, 3111, 4.0))
        start = np.full(48, 0.5)
        start[[3, 9, 20]] = 0.01
        keep = np.array([0.3, 0.8])
        real = np.random.default_rng

        def fake(seq):
            stream = seq.entropy[1] if isinstance(seq.entropy, list) else None
            values = dict([(DISTRESS_START_STREAM, start), (DISTRESS_KEEP_STREAM, keep)])
            if stream in values:
                return mock.Mock(random=lambda size, v=values[stream]: v[:size])
            return real(seq)
        economy = Economy(n=10, months=48, distress_dates="random")
        with mock.patch("numpy.random.default_rng", side_effect=fake):
            got = {dial: distress_years(economy, dial).tolist() for dial in (0.0, 2.0, 4.0)}
        self.assertEqual(got, {0.0: [], 2.0: [3], 4.0: [3, 20]})

    def test_years_never_overlap_and_lower_dials_nest(self):
        """Over 200 seeds of 264 months: years start at least twelve months apart, and the years at dials 1 and 2 are
        among those at 2 and 4."""
        for seed in range(200):
            economy = Economy(n=10, months=264, seed=seed, distress_dates="random")
            years = {dial: distress_years(economy, dial) for dial in (1.0, 2.0, 4.0)}
            self.assertTrue(np.all(np.diff(years[4.0]) >= economy.distress_length))
            self.assertTrue(np.all((years[4.0] >= 0) & (years[4.0] < 264)))
            self.assertTrue(set(years[1.0]) <= set(years[2.0]) <= set(years[4.0]))
            np.testing.assert_array_equal(years[2.0], distress_years(replace(economy, distress_expected=2.0)))

    def test_the_mean_number_of_years_is_the_dial_over_four_of_the_mean_at_four(self):
        """Over 2,000 seeds the mean number of years at dials 1 and 2 is within 0.05 of a quarter and a half of the
        mean at 4, which is a little below 4 since years may not overlap; and the share of seeds with no year, and
        with the first year within five years of launch at a dial of 1, are near the Poisson table's."""
        counts, first = {dial: [] for dial in (1.0, 2.0, 4.0)}, []
        for seed in range(2000):
            economy = Economy(n=10, months=264, seed=seed, distress_dates="random")
            for dial in counts:
                years = distress_years(economy, dial)
                counts[dial].append(years.size)
                if dial == 1.0:
                    first.append(years[0] if years.size else 264)
        mean = {dial: float(np.mean(found)) for dial, found in counts.items()}
        self.assertTrue(3.0 < mean[4.0] < 4.0)
        for dial in (1.0, 2.0):
            self.assertAlmostEqual(mean[dial], dial / 4 * mean[4.0], delta=0.05)
        # The table is Poisson at the dial; refusing overlaps leaves a few more seeds with no year.
        table = {1.0: (0.37, 0.37, 0.18, 0.06, 0.02), 2.0: (0.14, 0.27, 0.27, 0.18, 0.14),
                 4.0: (0.02, 0.07, 0.15, 0.20, 0.57)}
        for dial, shares in table.items():
            poisson = [math.exp(-dial) * dial ** k / math.factorial(k) for k in range(4)]
            self.assertEqual([round(p, 2) for p in poisson] + [round(1 - sum(poisson), 2)], list(shares))
            found = np.array(counts[dial])
            self.assertGreaterEqual(float((found == 0).mean()), shares[0] - 0.01)
        self.assertAlmostEqual(float((np.array(counts[1.0]) == 0).mean()), 0.37, delta=0.05)
        self.assertAlmostEqual(1 - math.exp(-60 / 264), 0.20, places=2)
        self.assertAlmostEqual(float((np.array(first) < 60).mean()), 0.20, delta=0.03)

    def test_the_dates_depend_on_the_seed_and_run_length_only(self):
        """Every arm and every distress level of a seed meets the same dates, and the calendar flags twelve months
        from each start, after the burn-in."""
        economy = Economy(n=60, burn_in=3, months=120, seed=20261711, distress_dates="random", distress_expected=4.0,
                          distress=0.02)
        calendar = distress_calendar(economy)
        starts = distress_years(economy)
        self.assertGreater(starts.size, 0)
        expected = np.zeros(123, bool)
        for start in starts:
            expected[3 + start:3 + start + 12] = True
        np.testing.assert_array_equal(calendar, expected)
        for arm in ARMS:
            for level in (0.0, 0.01, 0.02):
                world = _World(Inputs(), 0.2, replace(economy, distress=level), arm)
                np.testing.assert_array_equal(world.distressed, calendar)
        np.testing.assert_array_equal(distress_calendar(replace(economy, n=200, buffer_review=0.5)), calendar)

    def test_the_dated_calendar_is_months_25_to_36_after_launch(self):
        """The default: burn-in 6, distress from 24 months after launch for 12, months 30 to 41 of the run."""
        calendar = distress_calendar(Economy())
        np.testing.assert_array_equal(np.flatnonzero(calendar), np.arange(30, 42))

    def test_one_random_year_runs_as_the_dated_year_at_its_date(self):
        """Where the random years of a short run are exactly one, the run equals the dated run with that year bit
        for bit in every arm, so the layoff rule, its one uniform per job and the harsh stress work inside a random
        year as in the dated one; and wealth accounting is exact."""
        base = Economy(n=60, burn_in=2, months=12, distress=0.05, distress_length=4)
        for seed in range(20261701, 20261801):
            economy = replace(base, seed=seed, distress_dates="random", distress_expected=4.0)
            starts = distress_years(economy)
            if starts.size == 1 and starts[0] + 4 <= 12:
                break
        else:
            self.fail("no seed with one random year")
        dated = replace(base, seed=seed, distress_start=int(starts[0]))
        for arm in ("S0", "M1"):
            got, built = simulate(Inputs(), 0.6, economy, arm), simulate(Inputs(), 0.6, dated, arm)
            self.assertTrue(balanced(got["series"]))
            self.assertGreater(float(got["series"]["wages_out"].sum()), 0.0)
            for key, value in built["series"].items():
                np.testing.assert_array_equal(got["series"][key], value, err_msg=f"{arm} {key}")

    def test_random_years_keep_the_books_exact_in_every_arm_and_the_fork_matches(self):
        """With several random years in a short run, wealth accounting is exact every month in every arm, layoffs
        beyond normal job loss fall only inside the years, and the runner's fork at the first year equals direct runs
        at two distress levels."""
        from cpm_abm.experiment.jobs import fork_month, forked
        economy = Economy(n=60, burn_in=2, months=14, distress=0.05, distress_length=3, seed=20261702,
                          distress_dates="random", distress_expected=4.0)
        calendar = distress_calendar(economy)
        self.assertGreater(int(calendar.sum()), 0)
        self.assertEqual(fork_month(economy), int(np.flatnonzero(calendar)[0]))
        for arm in ARMS:
            series = simulate(Inputs(), 0.6, economy, arm)["series"]
            self.assertTrue(balanced(series))
            out = np.asarray(series["wages_out"])
            self.assertTrue(np.all(out[:int(np.flatnonzero(calendar)[0])] == 0.0))
        got = forked(Inputs(), 0.6, economy, "M1", (0.0, 0.05))
        for level, run in got.items():
            direct = simulate(Inputs(), 0.6, replace(economy, distress=level), "M1")
            for key, value in direct["series"].items():
                np.testing.assert_array_equal(run["series"][key], value, err_msg=f"{level} {key}")
        quiet = replace(economy, distress_expected=0.0)
        self.assertFalse(distress_calendar(quiet).any())
        self.assertEqual(fork_month(quiet), quiet.burn_in + quiet.months)


class SettingsTests(unittest.TestCase):
    """Every side-study setting refuses what it does not define; the defaults leave each study off."""

    def test_defaults_and_refusals(self):
        economy = Economy()
        self.assertEqual((economy.sceptical_share, economy.owners_follow, economy.distress_dates,
                          economy.distress_expected), (None, "none", "dated", 1.0))
        for fields in (dict(sceptical_share=-0.1), dict(sceptical_share=1.5), dict(sceptical_share=True),
                       dict(sceptical_share="half"), dict(sceptical_share=0.5, entry_reads="realised"),
                       dict(owners_follow="some"), dict(distress_dates="sometimes"),
                       dict(distress_dates="random", distress_expected=5.0),
                       dict(distress_dates="random", distress_expected=-1.0), dict(distress_expected=2.0),
                       dict(distress_dates="random", card_line_cut=True)):
            with self.assertRaises(ValueError, msg=str(fields)):
                replace(economy, **fields)
        for fields in (dict(sceptical_share=0), dict(sceptical_share=1.0), dict(owners_follow="all"),
                       dict(distress_dates="random", distress_expected=0.0), dict(distress_dates="random")):
            replace(economy, **fields)


if __name__ == "__main__":
    unittest.main()

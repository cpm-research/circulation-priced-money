"""The readings of a long run's stored series (``cpm_abm.experiment.steady``): hand-made series with a known
answer, no population run. Each test's docstring works its numbers by hand."""
import gzip
import json
import unittest
from dataclasses import fields
from pathlib import Path

import numpy as np

from scripts import run_economy_population  # noqa: F401  (puts src and scripts on the path, as the other tests do)
from cpm_abm.economy_abm import Economy
from cpm_abm.engine.population import distress_calendar
from cpm_abm.experiment import steady
from cpm_abm.experiment.notes import MONTHLY, SECOND_MONTHLY, monthly_keys
from cpm_abm.experiment.region import paired, recovery
from cpm_abm.experiment.statistics import DIP_YEARS, dip_months, dips, yearly_dips
from scripts.run_economy_figures import DOLLARS

RELEASED = Economy(n=40)
SECOND = Economy(n=40, burn_in=60, months=300, distress_start=120, distress_length=12)
STORE = Path(__file__).resolve().parents[1] / "results" / "development_map"


def stress_effect(w, after):
    """A run of ``w.months`` months whose effect against its twin is 0 before the stress year, 1.0 through it and
    ``after(k)`` in the k-th month after it (k from 1), with the twin all zeros."""
    first, end = steady.stress_year(w)
    run = np.zeros(w.months)
    run[first:end] = 1.0
    run[end:] = [after(k) for k in range(1, w.months - end + 1)]
    return run, np.zeros(w.months)


class StressMonths(unittest.TestCase):
    def test_the_stress_months_are_the_runs_own(self):
        """In the first run the stress year is months 25 to 36 after launch, indices 24 to 35; in the second run months
        121 to 132, indices 120 to 131, and its dip runs from month 121 to the end, 180 months. A stored economy
        (summary.json's dict) and a stub without the settings read the first run's design."""
        self.assertEqual(steady.stress_months(RELEASED).tolist(), list(range(24, 36)))
        self.assertEqual(steady.stress_year(RELEASED), (24, 36))
        self.assertEqual(steady.dip_window(RELEASED), (24, 60))
        self.assertEqual(dip_months(), (24, 60))
        self.assertEqual(dip_months(RELEASED), dip_months())
        self.assertEqual(steady.stress_year(SECOND), (120, 132))
        self.assertEqual(steady.dip_window(SECOND), (120, 156))
        stored = dict(burn_in=6, months=60, distress_start=24, distress_length=12, seed=None, distress=None)
        self.assertEqual(steady.stress_year(stored), (24, 36))
        self.assertEqual(steady.stress_year(object()), (24, 36))

    def test_a_year_cut_at_the_end_and_a_run_with_none(self):
        """A year from 54 months after launch in a 60-month run is cut at the end, (54, 60); a year from 70 months
        never starts, so there is no stress month and no dip."""
        self.assertEqual(steady.stress_year(Economy(n=40, distress_start=54)), (54, 60))
        none = Economy(n=40, distress_start=70)
        self.assertEqual(steady.stress_months(none).size, 0)
        self.assertIsNone(steady.stress_year(none))
        self.assertIsNone(steady.dip_window(none))

    def test_random_years_are_read_from_the_seed(self):
        """Under random distress years the months are the engine's own calendar after launch for the job's seed, and
        the first year starts at its first flagged month; without a seed the reading refuses."""
        w = Economy(n=40, burn_in=60, months=300, distress_dates="random")
        for seed in (1, 2, 3):
            flagged = np.flatnonzero(distress_calendar(steady.economy_of(w, seed))[60:])
            self.assertEqual(steady.stress_months(w, seed).tolist(), flagged.tolist())
            if flagged.size:
                self.assertEqual(steady.stress_year(w, seed), (int(flagged[0]), min(int(flagged[0]) + 12, 300)))
        with self.assertRaises(ValueError):
            steady.stress_months(dict(distress_dates="random", months=300, burn_in=60))


class Settled(unittest.TestCase):
    def test_window_means(self):
        """A series equal to its year number has mean 8 over years 6 to 10 and 23 over 21 to 25; undefined months are
        left out, and a window past the series is refused."""
        series = np.repeat(np.arange(1, 26), 12).astype(float)
        self.assertEqual(steady.window_means(series, (6, 10)).tolist(), [8.0])
        self.assertEqual(steady.window_means(series, (21, 25)).tolist(), [23.0])
        holes = series.tolist()
        holes[60:72] = [None] * 12   # year 6 undefined: years 7 to 10 average 8.5
        self.assertEqual(steady.window_means(holes, (6, 10)).tolist(), [8.5])
        with self.assertRaises(ValueError):
            steady.window_means(series[:250], (21, 25))

    def test_a_change_read_against_its_interval(self):
        """Three seeds whose years 21 to 25 sit above years 6 to 10 by 0.01, 0.03 and 0.02: mean change 0.02,
        standard error 0.01 / sqrt(3) = 0.00577, 95% interval 0.02 -/+ 4.303 x 0.00577 = -0.0048 to 0.0448: settled
        under a margin of 0.05, undecided under 0.01 (the interval reaches below zero, so it is not wholly outside
        it)."""
        base = np.full((3, 300), 0.05)
        base[:, 240:] += np.array([0.01, 0.03, 0.02])[:, None]
        out = steady.settled(base, margin=0.05)
        self.assertAlmostEqual(out["change_mean"], 0.02)
        self.assertAlmostEqual(out["change_se"], 0.01 / np.sqrt(3))
        self.assertAlmostEqual(out["change_lower_95"], 0.02 - 4.302653 * 0.01 / np.sqrt(3), places=5)
        self.assertEqual((out["inside_margin"], out["outside_zero"], out["verdict"]), (True, False, "settled"))
        self.assertEqual(steady.settled(base, margin=0.01)["verdict"], "undecided")

    def test_imprecision_does_not_settle(self):
        """A mean change of 0.02 under a margin of 0.05: with changes 0.019, 0.020 and 0.021 (standard error 0.00058)
        the interval 0.0175 to 0.0225 is inside the margin and the measure is settled; with -0.18, 0.02 and 0.22
        (standard error 0.115) the interval reaches far past the margin and the reading is undecided, though the
        mean alone lies inside the margin and within two standard errors of zero. Changes of 0.10, 0.11 and 0.12 lie
        wholly above zero with a mean beyond the margin: moving. One seed has no standard error and no verdict."""
        def series(changes):
            base = np.full((len(changes), 300), 0.05)
            base[:, 240:] += np.array(changes)[:, None]
            return base
        self.assertEqual(steady.settled(series([0.019, 0.020, 0.021]), 0.05)["verdict"], "settled")
        wide = steady.settled(series([-0.18, 0.02, 0.22]), 0.05)
        self.assertAlmostEqual(wide["change_mean"], 0.02)
        self.assertEqual((wide["inside_margin"], wide["verdict"]), (False, "undecided"))
        self.assertEqual(steady.settled(series([0.10, 0.11, 0.12]), 0.05)["verdict"], "moving")
        one = steady.settled(series([0.01]), 0.005)
        self.assertEqual((one["seeds"], one["change_se"], one["change_lower_95"], one["verdict"]),
                         (1, None, None, None))
        with self.assertRaises(ValueError):
            steady.settled(series([0.01, 0.02]), None)

    def test_the_two_pairs(self):
        """A series that drifts until year 15 and is flat after: years 6 to 10 against 21 to 25 move, years 16 to 20
        against 21 to 25 are settled."""
        rng = np.random.default_rng(1)
        years = np.minimum(np.arange(300) // 12 + 1, 15).astype(float)
        series = years[None, :] * 0.01 + rng.normal(0, 1e-4, (5, 300))
        out = steady.settled_readings(series, margin=0.001)
        self.assertEqual(set(out), {"early_to_late", "within_late"})
        self.assertEqual(out["early_to_late"]["verdict"], "moving")
        self.assertEqual(out["within_late"]["verdict"], "settled")
        self.assertEqual(out["within_late"]["early"], [16, 20])


class StressReturn(unittest.TestCase):
    def test_a_halving_effect_returns(self):
        """Released year, months 25 to 36: an effect of 1.0 through the year halving every month after it. The peak
        is 1.0 in month 25 (the first of its size); under a margin of 0.1 the effect is 0.0625 in month 40 and below
        after, so back_month is 40, 4 months after the year, and it stays back; half of the peak (0.5) is first
        reached in month 37, a half-life of 12 months from month 25."""
        run, twin = stress_effect(RELEASED, lambda k: 0.5 ** k)
        out = steady.stress_return(run, twin, RELEASED, margin=0.1)
        self.assertEqual((out["peak"], out["peak_month"]), (1.0, 25))
        self.assertEqual((out["back_month"], out["months_to_return"], out["stays_back"]), (40, 4, True))
        self.assertEqual(out["half_life"], 12)
        self.assertEqual(out["effect_months"][0], 13)   # a year before the stress
        self.assertEqual(len(out["effect"]), 48)

    def test_the_same_in_the_second_run(self):
        """The same shape in a 300-month run with its year at months 121 to 132 reads the same months to return and
        half-life, at months shifted by 96."""
        run, twin = stress_effect(SECOND, lambda k: 0.5 ** k)
        out = steady.stress_return(run, twin, SECOND, margin=0.1)
        self.assertEqual((out["peak_month"], out["back_month"], out["months_to_return"], out["half_life"]),
                         (121, 136, 4, 12))

    def test_never_returns(self):
        """An effect that stays at 0.5 after the year never comes inside a margin of 0.1, and halves in the first
        month after the year: back_month None, half-life 12."""
        run, twin = stress_effect(RELEASED, lambda k: 0.5)
        out = steady.stress_return(run, twin, RELEASED, margin=0.1)
        self.assertIsNone(out["back_month"])
        self.assertIsNone(out["months_to_return"])
        self.assertEqual(out["half_life"], 12)

    def test_returns_and_leaves_inside_the_twelve_months(self):
        """Inside the margin for months 37 to 42 and outside again in month 43, then inside from month 44: the first
        run of twelve inside starts in month 44, 8 months after the year."""
        run, twin = stress_effect(RELEASED, lambda k: 0.5 if k == 7 else 0.0)
        out = steady.stress_return(run, twin, RELEASED, margin=0.1)
        self.assertEqual((out["back_month"], out["months_to_return"], out["stays_back"]), (44, 8, True))

    def test_a_peak_in_the_last_month(self):
        """An effect of 0.2 after the year rising to 3.0 in the last month: the peak is 3.0 in month 60, it never
        halves after it, and it never stays inside a margin of 0.1."""
        run, twin = stress_effect(RELEASED, lambda k: 3.0 if k == 24 else 0.2)
        out = steady.stress_return(run, twin, RELEASED, margin=0.1)
        self.assertEqual((out["peak"], out["peak_month"], out["half_life"], out["back_month"]), (3.0, 60, None, None))

    def test_back_then_out_again_after_the_hold(self):
        """Inside for months 37 to 50 and outside from 51: back in month 37 (1 month after the year) on the twelve
        months running, and not staying back."""
        run, twin = stress_effect(RELEASED, lambda k: 0.5 if k >= 15 else 0.0)
        out = steady.stress_return(run, twin, RELEASED, margin=0.1)
        self.assertEqual((out["back_month"], out["months_to_return"], out["stays_back"]), (37, 1, False))

    def test_no_stress_months(self):
        """A run whose distress year never starts has nothing to return from: every reading None."""
        none = Economy(n=40, distress_start=70)
        out = steady.stress_return(np.ones(60), np.zeros(60), none, margin=0.1)
        self.assertFalse(out["stress"])
        self.assertTrue(all(out[key] is None for key in ("peak", "back_month", "half_life", "effect")))

    def test_no_effect(self):
        """A run equal to its twin: peak 0, half-life 0, back in the first month after the year."""
        out = steady.stress_return(np.zeros(60), np.zeros(60), RELEASED, margin=0.1)
        self.assertEqual((out["peak"], out["half_life"], out["back_month"], out["months_to_return"]), (0.0, 0, 37, 1))

    def test_seed_means(self):
        """Two seeds that return 4 and 8 months after the year and one that never does: months to return mean 6,
        standard error 2, returned share 2/3; every peak 1.0 with standard error 0; the mean effect in month 43 is
        (0.0078 + 0.5 + 0.5) / 3."""
        shapes = (lambda k: 0.5 ** k, lambda k: 0.5 if k == 7 else 0.0, lambda k: 0.5)
        pairs = [stress_effect(RELEASED, shape) for shape in shapes]
        out = steady.stress_return_seeds([p[0] for p in pairs], [p[1] for p in pairs], RELEASED, 0.1)
        self.assertEqual(out["months_to_return"], dict(mean=6.0, se=2.0, seeds=2))
        self.assertAlmostEqual(out["returned_share"], 2 / 3)
        self.assertEqual(out["peak"], dict(mean=1.0, se=0.0, seeds=3))
        self.assertAlmostEqual(out["effect_mean"][42], (0.5 ** 7 + 0.5 + 0.5) / 3)


def stored_job(seed, distress, failure_share, card_debt=0.3, returned=0.01, rate=0.044, a0=0.6):
    """A job as measures.json stores it: distress measures under "series", monthly records under "monthly"."""
    monthly = dict(card_debt=[card_debt] * 24, money_bt=[1.5] * 24, savings_bt=[0.5] * 24,
                   out_interest=[0.004 if card_debt > 0.25 else 0.003] * 24, returned=[returned] * 24,
                   N=[2.0] * 24, Q=[4.0] * 24)
    return dict(r_out=rate, a0=a0, distress=distress, seed=seed, recirculated=False,
                series=dict(S0=dict(failures=list(failure_share))), monthly=dict(S0=monthly, M1=dict(monthly)),
                failure_counts=dict(S0=dict(monthly=dict(fail_shares=[0.1] * 24))))


class Jobs(unittest.TestCase):
    def test_series_of(self):
        """A stored series by its monthly name, by measure name or engine series name, from the failure counts, and
        as a ratio: pool capital 2 over its limit 4 is one half; a series not stored reads None."""
        job = stored_job(1, 0.0, [0.02] * 24)
        self.assertEqual(steady.series_of(job, "S0", "card_debt").tolist(), [0.3] * 24)
        self.assertEqual(steady.series_of(job, "S0", "failures").tolist(), [0.02] * 24)
        self.assertEqual(steady.series_of(job, "S0", "failure_share").tolist(), [0.02] * 24)
        self.assertEqual(steady.series_of(job, "S0", "fail_shares").tolist(), [0.1] * 24)
        self.assertEqual(steady.series_of(job, "M1", ("N", "Q")).tolist(), [0.5] * 24)
        self.assertIsNone(steady.series_of(job, "S0", "nothing"))

    def test_twins_and_return_from_jobs(self):
        """Each distress job meets the level-0 job of its seed; a seed with no twin is left out. The effect is 0.01
        through the 24 months after launch of a short run whose year is months 4 to 9, and 0 after: back in month 10,
        1 month after the year."""
        w = Economy(n=40, burn_in=2, months=24, distress_start=3, distress_length=6)
        effect = [0.0] * 3 + [0.01] * 6 + [0.0] * 15
        level = [stored_job(s, 0.01, np.array(effect) + 0.02) for s in (1, 2, 3)]
        base = [stored_job(s, 0.0, [0.02] * 24) for s in (1, 2)]
        self.assertEqual([(j["seed"], b["seed"]) for j, b in steady.twins(level, base)], [(1, 1), (2, 2)])
        out = steady.stress_return_jobs(level, base, "S0", "failures", w, margin=0.001)
        self.assertEqual(out["seeds"], 2)
        self.assertEqual(out["months_to_return"]["mean"], 1.0)
        self.assertAlmostEqual(out["peak"]["mean"], 0.01)
        settled = steady.settled_jobs([stored_job(s, 0.0, [0.02] * 300) for s in (1, 2)], "S0", "failures", 0.001)
        self.assertEqual(settled["early_to_late"]["change_mean"], 0.0)

    def test_outside_support(self):
        """Card debt 0.30 with lines held and 0.20 with lines cut, money 2.0, interest 0.004 against 0.003 a month:
        0.10 supported ($644 a person), a third of card credit in use and 5% of money; lenders earn 0.012 more a
        year ($77.28 a person)."""
        out = steady.outside_support([0.3] * 24, [0.2] * 24, [2.0] * 24, [0.004] * 24, [0.003] * 24)
        self.assertAlmostEqual(out["by_month"]["supported"][0], 0.1)
        self.assertAlmostEqual(out["by_month"]["share_of_card"][5], 1 / 3)
        self.assertAlmostEqual(out["by_year"]["share_of_money"][1], 0.05)
        self.assertAlmostEqual(out["by_year"]["supported_usd"][0], 644.0)
        self.assertAlmostEqual(out["by_year"]["extra_outside_interest"][0], 0.012)
        self.assertAlmostEqual(out["by_year"]["extra_outside_interest_usd"][1], 77.28)
        self.assertEqual(len(out["by_year"]["supported"]), 2)
        none = steady.outside_support([0.0] * 12, [0.0] * 12, [0.0] * 12, [0.0] * 12, [0.0] * 12)
        self.assertIsNone(none["by_year"]["share_of_card"][0])
        held = [stored_job(s, 0.02, [0.02] * 24) for s in (1, 2)]
        cut = [stored_job(s, 0.02, [0.02] * 24, card_debt=0.2) for s in (1, 2)]
        jobs = steady.outside_support_jobs(held, cut)
        self.assertEqual(jobs["seeds"], 2)
        self.assertAlmostEqual(jobs["by_year"]["share_of_money"][0]["mean"], 0.05)
        self.assertAlmostEqual(jobs["by_year"]["extra_outside_interest"][0]["se"], 0.0)
        self.assertEqual(jobs["card_credit_reads"], "card_debt")

    def test_outside_support_reads_card_unbilled(self):
        """Where both jobs store card_unbilled the card credit in use is card_debt plus it: 0.30 + 0.05 with lines
        held and 0.20 + 0.02 with lines cut supports 0.13, 0.13 / 0.35 of card credit in use."""
        def with_unbilled(job, value):
            job["monthly"]["S0"]["card_unbilled"] = [value] * 24
            return job
        held = [with_unbilled(stored_job(s, 0.02, [0.02] * 24), 0.05) for s in (1, 2)]
        cut = [with_unbilled(stored_job(s, 0.02, [0.02] * 24, card_debt=0.2), 0.02) for s in (1, 2)]
        jobs = steady.outside_support_jobs(held, cut)
        self.assertEqual(jobs["card_credit_reads"], "card_debt + card_unbilled")
        self.assertAlmostEqual(jobs["by_year"]["supported"][0]["mean"], 0.13)
        self.assertAlmostEqual(jobs["by_year"]["share_of_card"][0]["mean"], 0.13 / 0.35)
        mixed = steady.outside_support_jobs(held[:1] + [stored_job(2, 0.02, [0.02] * 24)], cut)
        self.assertEqual(mixed["card_credit_reads"], "mixed")

    def test_handed_back(self):
        """0.01 every month is 0.12 a year, $772.80 a person; an arm with no returned series reads None."""
        out = steady.handed_back([0.01] * 24)
        self.assertEqual(len(out["units"]), 2)
        self.assertAlmostEqual(out["units"][0], 0.12)
        self.assertAlmostEqual(out["usd"][1], 0.12 * DOLLARS)
        self.assertAlmostEqual(out["usd"][0], 772.80)
        jobs = steady.handed_back_jobs([stored_job(1, 0.0, [0.0] * 24), stored_job(2, 0.0, [0.0] * 24, returned=0.02)],
                                       ("S0", "M2"))
        self.assertAlmostEqual(jobs["S0"]["units"][0]["mean"], 0.18)
        self.assertAlmostEqual(jobs["S0"]["usd"][0]["se"], 0.06 * DOLLARS)
        self.assertIsNone(jobs["M2"])


class ReleasedReadings(unittest.TestCase):
    def test_monthly_keys(self):
        """A first-run store keeps MONTHLY alone; a run with the conserved edge, the slowdown or random years stores the
        second run's records after it."""
        for arm in MONTHLY:
            self.assertEqual(monthly_keys(arm, RELEASED), MONTHLY[arm])
            for changed in (dict(edge="conserved"), dict(distress_wages="kept"), dict(distress_dates="random")):
                self.assertEqual(monthly_keys(arm, Economy(n=40, **changed)), MONTHLY[arm] + SECOND_MONTHLY[arm])
        self.assertIn("returned", SECOND_MONTHLY["S0"])
        self.assertIn("target", SECOND_MONTHLY["M1"])
        # The series behind every line of the real cost, so the cost can be read by window from the store.
        self.assertTrue({"card_payments", "card_value", "gas", "pt_card", "fail_shares"} <= set(SECOND_MONTHLY["S0"]))

    def test_the_dip_reads_the_runs_months(self):
        """The default Economy's dip is the dip with no Economy, 0.6 a year from 1.8 over 36 months. In the second
        run the dip keeps that span from its own stress year, months 121 to 156: 0.05 more failed shares a month
        in every month gives 1.8, 0.6 a year over its 3 years, however long the run goes on afterwards."""
        def job(seed, level, value, months):
            counts = {arm: dict(monthly=dict(fail_shares=[value] * months)) for arm in ("S0", "M0", "M1")}
            counts["S0"]["monthly"]["fail_shares"] = [0.05] * months
            counts["M0"]["monthly"]["fail_shares"] = [0.05] * months
            return dict(seed=seed, distress=level, failure_counts=counts)
        level, base = [job(0, 0.01, 0.1, 60)], [job(0, 0.0, 0.05, 60)]
        self.assertEqual(dips("M1", level, base, RELEASED), dips("M1", level, base))
        self.assertAlmostEqual(yearly_dips(dips("M1", level, base, RELEASED)["own"])[0], 0.6)
        self.assertEqual(DIP_YEARS, 3.0)
        level, base = [job(0, 0.01, 0.1, 300)], [job(0, 0.0, 0.05, 300)]
        out = dips("M1", level, base, SECOND)
        self.assertAlmostEqual(out["own"][0], 1.8)
        self.assertEqual(out["years"], [3.0])
        self.assertAlmostEqual(yearly_dips(out["own"], out["years"])[0], 0.6)

    def test_recovery_in_the_second_run(self):
        """Example, in the second run's year as in the first run's: failures peaking at 1 point in the year's last month
        and halving every two months recover 4 months after the year."""
        for w in (RELEASED, SECOND):
            first, end = steady.stress_year(w)
            months = np.arange(1, w.months + 1)
            ramp = np.clip((months - first) / 12, 0.0, 1.0)
            r = recovery(np.where(months > end, 0.5 ** ((months - end) / 2), ramp), w)
            self.assertEqual((r["gap"], r["month"], r["months_to_recover"]), (1.0, end, 4))
        self.assertEqual(recovery(np.ones(60), Economy(n=40, distress_start=70))["months_to_recover"], 0)

    @unittest.skipUnless((STORE / "measures.json.gz").exists(), "the stored development map is not here")
    def test_the_development_map_reads_as_stored(self):
        """The stored development map (60 months, the year at months 25 to 36) read again: its economy's stress year
        is (24, 36), and the paired distress reading of every distress cell, recomputed from measures.json with the
        stored economy, equals the reading stored in summary.json."""
        with gzip.open(STORE / "summary.json.gz", "rt", encoding="utf-8") as source:
            summary = json.load(source)
        with gzip.open(STORE / "measures.json.gz", "rt", encoding="utf-8") as source:
            stored = json.load(source)
        self.assertEqual(steady.stress_year(summary["economy"]), (24, 36))
        names = {f.name for f in fields(Economy)}
        w = Economy(**{k: v for k, v in summary["economy"].items() if k in names and v is not None})
        by_cell = {}
        for job in stored["jobs"]:
            by_cell.setdefault((job["r_out"], job["a0"], job["distress"], job["recirculated"]), []).append(
                dict(job, measures=job["series"]))
        read = 0
        for cell in summary["cells"]:
            if not cell or not cell["distress"]:
                continue
            place = (cell["r_out"], cell["a0"])
            mine = by_cell[(*place, cell["distress"], cell["recirculated"])]
            base = by_cell[(*place, 0.0, cell["recirculated"])]
            self.assertEqual(json.loads(json.dumps(paired(mine, base, w))), cell["distress_reading"])
            read += 1
        self.assertEqual(read, 84)


if __name__ == "__main__":
    unittest.main()

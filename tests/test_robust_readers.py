"""The paper's readers of the robustness sets, the settlement records, the stress boundary, the period-two reading
and the spread of distress (scripts/paper_numbers.py), on small hand-made stores: every value is set by hand here,
so each table cell and macro can be checked against a number worked out in the test. Nothing is run and no stored
result is read."""
import copy
import unittest

import numpy as np

from scripts import paper_numbers as pn

SEEDS = [11, 12, 13]
RATE = 0.044
MONTHS = 60


def path_of(a0, end):
    """A participation path of MONTHS months from a0 rising in a straight line to ``end`` at month 60."""
    return list(np.linspace(a0, end, MONTHS + 1)[1:])


def robust_store(ends, gains, means, economy=None):
    """A robustness set of three launch cells (5, 20 and 60%) with no distress: ``ends`` the participation at month 60
    by launch (the same for every seed), ``gains`` each launch's per-seed money gain over banks and over DeFi, and
    ``means`` the seed-mean gain the summary stores."""
    launches = (0.05, 0.2, 0.6)
    cells, jobs, monthly = [], [], []
    for a0 in launches:
        gain = means[a0]
        cells.append(dict(r_out=RATE, a0=a0, distress=0.0, seeds=3, recirculated=False, S0_failures_pct=3.6,
                          M1=dict(failures_pct=2.0, r_b_pct=2.1, c_pct=0.14,
                                  against=dict(S0=dict(gain_usd_a_year=gain), M0=dict(gain_usd_a_year=gain)))))
        for seed, value in zip(SEEDS, gains[a0]):
            against = dict(S0=dict(gain_usd_a_year=value), M0=dict(gain_usd_a_year=value))
            jobs.append(dict(r_out=RATE, a0=a0, distress=0.0, seed=seed, recirculated=False,
                             arms=dict(M1=dict(against=against))))
            monthly.append(pn.kept_monthly(dict(r_out=RATE, a0=a0, distress=0.0, seed=seed, recirculated=False,
                                                monthly=dict(M1=dict(A=path_of(a0, ends[a0]))))))
    summary = dict(economy=dict(n=4000, months=MONTHS, lender_income_recirculated=None, **(economy or {})),
                   seeds=SEEDS, cells=cells)
    return pn.Store(summary, jobs=jobs, monthly=monthly, folder="robust_hand")


class RobustTest(unittest.TestCase):
    def setUp(self):
        # At 5% two of three seeds gain (the mean is positive): it survives. At 20% one seed of three: it does not.
        # At 60% the mean is negative: it does not.
        self.gains = {0.05: [10.0, 5.0, -1.0], 0.2: [10.0, -5.0, -1.0], 0.6: [-10.0, -5.0, 1.0]}
        self.means = {0.05: 4.67, 0.2: 1.33, 0.6: -4.67}
        self.ends = {0.05: 0.08, 0.2: 0.3, 0.6: 0.7}           # rises of 0.03, 0.10 and 0.10

    def test_rows_and_macros(self):
        threshold = robust_store(self.ends, self.gains, self.means, dict(joining="threshold", thresholds=0.2))
        robust = [("Uniform", "Base", "the base", robust_store(self.ends, self.gains, self.means)),
                  ("Uniform", "ThresholdTwenty", "common threshold 0.2", threshold),
                  ("Ring", "Ring", "ring", pn.Store.pending("robust_ring"))]
        ledger = pn.Ledger()
        table, macros = pn.robust_table(robust, ledger)
        base, common, ring = table["rows"]
        self.assertEqual(base[:5], ["Uniform", "the base", "0.08", "0.30", "0.70"])
        self.assertEqual(base[9:11], ["1 of 3", "1 of 3"])
        self.assertEqual(base[-1], "")                               # the linear rule has no critical mass
        # The lowest launch whose participation at month 60 rises by at least 0.05 is 20%.
        self.assertEqual(common[-1], r"20\%")
        self.assertEqual(macros["RobustThresholdTwentyCriticalMass"], r"20\%")
        self.assertEqual((macros["RobustBaseSurviveBanks"], macros["RobustBasePartFive"]), ("1", "0.08"))
        # A set not yet run: every number is a placeholder, and its macros still exist.
        self.assertEqual(ring[0], "Ring")
        self.assertTrue(all(value == pn.PLACEHOLDER for value in ring[2:]))
        self.assertEqual(macros["RobustRingSurviveDefi"], pn.PLACEHOLDER)
        self.assertEqual(table["rule_before"], [2])                  # a rule between the uniform and the ring rows
        self.assertTrue(any("robust_ring: set not yet run" in line for line in ledger.missing))

    def test_survival_rule(self):
        self.assertEqual([pn.seeds_needed_to_survive(n) for n in (3, 6, 30)], [2, 4, 20])

    def test_rule_check(self):
        base = robust_store(self.ends, self.gains, self.means)
        check = copy.deepcopy(base)
        check.summary["cells"] = [c for c in check.summary["cells"] if c["a0"] == 0.2]
        check = pn.Store(check.summary, jobs=[j for js in check.jobs.values() for j in js],
                         monthly=[j for js in check.monthly.values() for j in js], folder="rule_check")
        # Seed 12 is 0.02 higher in month 10 and seed 13 0.04 lower in month 30: the seed mean moves 0.02/3 and
        # 0.04/3.
        jobs = check.monthly[(RATE, 0.2, 0.0)]
        jobs[1]["monthly"]["M1"]["A"][9] += 0.02
        jobs[2]["monthly"]["M1"]["A"][29] -= 0.04
        macros = pn.rule_check_macros(base, check, pn.Ledger())
        self.assertEqual(macros, dict(RuleCheckGapMean="0.013", RuleCheckGapFirstSeed="0.000",
                                      RuleCheckGapSecondSeed="0.020", RuleCheckGapThirdSeed="0.040"))


def records_store():
    """A records run of two cells (launch 5%, no distress and 2 points), three seeds, every arrangement. Each month
    every seed's own shortfall is 10 / 60 and its knock-on 6 / 60 (over the run), 3 payers have a
    knock-on failure a day and on 3 of 30 days 32 or more do; netting holds 0.5 of 40 completed in month 1 of seed
    12."""
    cells, monthly = [], []
    for level in (0.0, 0.02):
        cells.append(dict(r_out=RATE, a0=0.05, distress=level, seeds=3, recirculated=False))
        for seed in SEEDS:
            series = dict(own_shortfall=[10 / 60] * MONTHS, knock_on=[6 / 60] * MONTHS, knock_on_n=[90.0] * MONTHS,
                          netting_days=[1.0] * MONTHS, netting_value=[0.0] * MONTHS, cash_completed=[40 / 60] * MONTHS,
                          **{name: [0.0] * MONTHS for name in pn.KNOCK_DAYS})
            series["knock_on_days_0"] = [27.0] * MONTHS
            series["knock_on_days_32_up"] = [3.0] * MONTHS
            if seed == 12:
                series["netting_value"] = [0.5] + [0.0] * (MONTHS - 1)
            arms = {arm: copy.deepcopy(series) for arm in pn.ARMS}
            arms["M1"]["knock_on"] = [5 / 60] * MONTHS          # CPM: 5 of 15 is knock-on
            monthly.append(pn.kept_monthly(dict(r_out=RATE, a0=0.05, distress=level, seed=seed, recirculated=False,
                                                monthly=arms)))
    summary = dict(economy=dict(n=4000, months=MONTHS, lender_income_recirculated=None), constants=dict(DAYS=30),
                   seeds=SEEDS, cells=cells)
    return pn.Store(summary, jobs=None, monthly=monthly, folder="records_hand")


class ChainsTest(unittest.TestCase):
    def test_hand_case(self):
        sums = dict(own_shortfall=np.array([10.0]), knock_on=np.array([6.0]), knock_on_n=np.array([1.0]),
                    netting_days=np.array([0.0]), netting_value=np.array([0.0]), cash_completed=np.array([4.0]),
                    **{name: np.array([0.0]) for name in pn.KNOCK_DAYS})
        sums["knock_on_days_1"] = np.array([1.0])
        found = pn.chain_readings(sums, 1)
        self.assertAlmostEqual(found["knock_share"][0], 6 / 16)
        self.assertEqual((found["payers_a_day"][0], found["many_days"][0]), (1.0, 0.0))

    def test_table_and_macros(self):
        ledger = pn.Ledger()
        table, macros = pn.chain_table(records_store(), ledger)
        banks = table["rows"][0]
        self.assertEqual(banks[:4], ["None", "Banks and cards", r"37.50\%", r"37.50\%"])
        self.assertEqual(banks[4], "3.0")                            # 5,400 payer-days over 1,800 days
        self.assertEqual(banks[6], r"10.0\%")                         # 3 of 30 days
        self.assertEqual(macros["KnockOnCpm"], r"33.33\%")
        self.assertEqual(macros["KnockOnGap"], r"$-$4.17\%")
        self.assertEqual(macros["ManyKnockOnPoolStress"], r"10.0\%")
        # Seed 12 rests 0.5 of 40 on netting, 1.25%; its cell's seed mean is a third of that.
        self.assertEqual(macros["NettingShareMost"], r"1.250\%")
        self.assertEqual(banks[8], r"0.417\%")
        self.assertEqual(len(table["rows"]), 10)

    def test_a_pending_records_run(self):
        table, macros = pn.chain_table(pn.Store.pending("records_base"), pn.Ledger())
        self.assertTrue(all(v == pn.PLACEHOLDER for v in macros.values()))
        self.assertEqual(table["rows"][0][2], pn.PLACEHOLDER)


def stress_store(served, folder):
    """A store of CPM's bridges served by (launch, level): each a list by seed, at the stress rate."""
    cells, jobs = [], []
    for (a0, level), values in served.items():
        cells.append(dict(r_out=RATE, a0=a0, distress=level, seeds=len(values), recirculated=False, M1=dict()))
        jobs += [dict(r_out=RATE, a0=a0, distress=level, seed=seed, recirculated=False,
                      arms=dict(M1=dict(bridges_drawn_over_wanted=value))) for seed, value in zip(SEEDS, values)]
    summary = dict(cells=cells, economy=dict(n=4000, lender_income_recirculated=None))
    return pn.Store(summary, jobs=jobs, monthly=[], folder=folder)


class BoundaryTest(unittest.TestCase):
    def test_lowest_majority_level(self):
        # Launch 20%: one seed runs at 1.6, two at 1.8. Launch 30%: never a majority. Launch 45%: missing levels.
        main = stress_store({(0.2, 0.0): [0.9] * 3, (0.2, 0.015): [0.9] * 3, (0.2, 0.02): [0.5] * 3,
                             (0.3, 0.015): [0.9] * 3, (0.3, 0.02): [0.5, 0.9, 0.9]}, "map")
        boundary = stress_store({(0.2, 0.0): [0.9] * 3, (0.2, 0.016): [0.5, 0.9, 0.9], (0.2, 0.017): [0.5, 0.9, 0.9],
                                 (0.2, 0.018): [0.5, 0.5, 0.9], (0.2, 0.019): [0.5, 0.5, 0.5],
                                 **{(0.3, level): [0.9] * 3 for level in (0.016, 0.017, 0.018, 0.019)}}, "boundary")
        ledger = pn.Ledger()
        table, macros = pn.boundary_table(main, boundary, ledger)
        self.assertEqual(macros["BoundaryTwenty"], "1.8 points")
        self.assertEqual(macros["BoundaryThirty"], "none up to 2 points")
        self.assertEqual(macros["BoundaryFortyFive"], pn.PLACEHOLDER)
        self.assertEqual(table["rows"][0][:3], ["1.5", "0.900", "0 of 3"])    # 1.5 points from the map
        self.assertEqual(table["rows"][3][1:3], ["0.633", "2 of 3"])          # 1.8 points from the boundary set
        # The level-0 cell is the same in both: six cells.json values a seed, none differs.
        self.assertEqual((macros["BoundaryRepeatValues"], macros["BoundaryRepeatDiffer"]), ("18", "0"))
        boundary.jobs[(RATE, 0.2, 0.0)][1]["arms"]["M1"]["bridges_drawn_over_wanted"] = 0.91
        found = pn.repeat_check(main, boundary, pn.Ledger())
        self.assertEqual(found["BoundaryRepeatDiffer"], "1")

    def test_same_values(self):
        differ = []
        self.assertEqual(pn.same_values(dict(a=[1.0, None, 2.0], b=dict(c=np.array([1.0, np.nan]))),
                                        dict(a=[1.0, None, 3.0], b=dict(c=np.array([1.0, np.nan])), d=5), [], differ),
                         5)
        self.assertEqual(differ, [["a", 2]])


class PeriodTwoTest(unittest.TestCase):
    def test_reference_cases(self):
        noise, top, flip = pn.reference_shares()
        self.assertAlmostEqual(noise, 0.015, delta=0.002)
        self.assertAlmostEqual(top, 0.059, delta=0.005)
        self.assertAlmostEqual(flip, 0.93, delta=0.01)

    def test_hand_series(self):
        # A pure alternation on a trend: the five-month mean removes the trend and leaves the alternation, all of it
        # at a period of two; its first remainder month (index 2) is even and high, so the amplitude is positive.
        x = 0.01 * np.arange(60) + np.where(np.arange(60) % 2 == 0, 1.0, -1.0)
        remainder = pn.trend_remainder(x)
        self.assertEqual(remainder.size, 56)
        self.assertAlmostEqual(pn.period_two_share(remainder), 1.0)
        self.assertAlmostEqual(pn.alternating_amplitude(remainder), 0.8)    # 1 less the centred mean 0.2
        self.assertTrue(np.isnan(pn.period_two_share(np.zeros(10))))
        share, amplitude, ratio = pn.series_reading(list(x[:20]))           # shorter than two years
        self.assertTrue(np.isnan(share) and np.isnan(amplitude))

    def test_table_on_a_store(self):
        rng = np.random.default_rng(3)
        flip = np.where(np.arange(60) % 2 == 0, 1.0, -1.0)
        monthly = []
        for seed, sign in zip(SEEDS, (1, -1, 1)):
            arms = {arm: dict(failure_share_rest=list(10 + sign * 0.1 * flip + 0.01 * rng.standard_normal(60)),
                              liquid=list(5 + rng.standard_normal(60))) for arm in pn.ARMS}
            monthly.append(pn.kept_monthly(dict(r_out=RATE, a0=0.05, distress=0.0, seed=seed, recirculated=False,
                                                monthly=arms)))
        store = pn.Store(dict(cells=[dict(r_out=RATE, a0=0.05, distress=0.0, recirculated=False)],
                              economy=dict(lender_income_recirculated=None)), jobs=None,
                         monthly=monthly, folder="hand")
        table, macros = pn.period_two_table(store, pn.Ledger())
        self.assertEqual(macros["PeriodTwoSignSecondSeed"], r"0\%")
        self.assertEqual(macros["PeriodTwoSignFirstSeed"], r"100\%")
        self.assertGreater(float(macros["PeriodTwoBanks"]), 0.9)
        self.assertLess(float(macros["PeriodTwoOthersJobMost"]), 0.5)
        self.assertEqual(macros["PeriodTwoAmplitude"], r"0.8\%")            # 0.08 of a level of 10
        self.assertEqual(len(table["rows"]), 5 + 3)


def spread_store(store):
    """A spread.json of one cell at each level, three seeds: banks' excess 3, 3, 3 and CPM's 2, 3, 4 at 2 points
    (others 2.4 and narrow 2.7 in every seed and arrangement), and in the distress year 1 against 0.9."""
    cells = []
    for level, _ in pn.SPREAD_LEVELS:
        arms = {}
        for arm in pn.ARMS:
            excess = [2.0, 3.0, 4.0] if arm == "M1" else [3.0] * 3
            arms[arm] = dict(excess=excess, others=[2.4] * 3, others_narrow=[2.7] * 3,
                             excess_year=[0.9] * 3 if arm == "M1" else [1.0] * 3, others_year=[0.6] * 3)
        cells.append(dict(r_out=RATE, a0=0.05, distress=level, seeds=SEEDS, people_hit=[200] * 3, arms=arms))
    store.spread = dict(cells=cells, levels=[level for level, _ in pn.SPREAD_LEVELS])
    return store


class SpreadTest(unittest.TestCase):
    def test_table_and_macros(self):
        store = spread_store(pn.Store(dict(cells=[]), folder="hand"))
        table, macros = pn.spread_table(store, pn.Ledger())
        self.assertEqual(len(table["rows"]), 4 * 4)
        cpm = table["rows"][-1]
        self.assertEqual(cpm[1:], ["CPM", "3.000", "3.000", "0.80", "0.90", "0.900", "0.900", "0.67"])
        # CPM's seed mean is 3, the same as banks', so it is not lower over months 25 to 60; it is in the year.
        self.assertEqual((macros["SpreadLowerTwo"], macros["SpreadLowerYearTwo"]), ("0", "1"))
        self.assertEqual((macros["SpreadGapTwo"], macros["SpreadGapYearTwo"]), ("0.000", r"$-$0.100"))
        self.assertEqual((macros["SpreadCells"], macros["SpreadWideLow"], macros["SpreadNarrowHigh"]),
                         ("1", "0.80", "0.90"))

    def test_absent_store(self):
        table, macros = pn.spread_table(pn.Store(dict(cells=[]), folder="no_spread"), pn.Ledger())
        self.assertTrue(all(v == pn.PLACEHOLDER for v in macros.values()))
        self.assertEqual(table["rows"][0][2], pn.PLACEHOLDER)


class ResultsCardTest(unittest.TestCase):
    def setUp(self):
        from scripts import results_card
        self.card = results_card
        gains = {0.05: [10.0, 5.0, -1.0], 0.2: [10.0, -5.0, -1.0], 0.6: [-10.0, -5.0, 1.0]}
        self.store = robust_store({0.05: 0.08, 0.2: 0.3, 0.6: 0.7}, gains, {0.05: 4.67, 0.2: 1.33, 0.6: -4.67},
                                  dict(joining="threshold", thresholds=0.2))

    def rows(self, store):
        """The card's rows as {label: (no distress, 2 points, field)}."""
        return {row[1]: row[2:] for row in self.card.card_rows(store)}

    def test_rows_against_hand_values(self):
        rows = self.rows(self.store)
        self.assertEqual(rows["CPM at month 60"][:2], ("0.300 (0.080 to 0.700)", "not in this run"))
        self.assertEqual(rows["Banks and cards, % of spending, years 4 and 5"][0], "3.60%")
        self.assertEqual(rows["Cells where the money gain over banks and cards is positive"][0], "2 of 3")
        self.assertEqual(rows["Holding charge c, % a year"][0], "0.140%")
        self.assertEqual(rows["CPM at launch"][0], "not stored")          # the hand store has no A_launch
        self.assertEqual(rows["Settings that differ from the base"][0], "joining 'threshold'; thresholds 0.2")
        self.assertEqual(rows["Dip against best-case DeFi"][:2], ("not in this run", "not in this run"))
        self.assertEqual(rows["Knock-on share of failed value, CPM"][0], "not stored")
        self.assertEqual(rows["Cells passing the registered claim (a whole map only)"][0], "not in this run")

    def test_the_rows_are_fixed(self):
        # The same rows in the same order for any folder, even one with no cells.
        labels = lambda store: [row[1] for row in self.card.card_rows(store)]
        empty = pn.Store(dict(cells=[], economy=dict(lender_income_recirculated=None)), folder="empty")
        self.assertEqual(labels(self.store), labels(empty))
        self.assertTrue(all(row[2] in ("not in this run", "not stored") or row[0] == "Setup"
                            for row in self.card.card_rows(empty)))
        text = self.card.card(self.store)
        self.assertTrue(text.startswith("# Results card: robust_hand"))
        self.assertNotIn(r"\%", text)


class FigureReadersTest(unittest.TestCase):
    def test_threshold_shares_and_the_hand_case(self):
        from types import SimpleNamespace

        from scripts import paper_figures as pf
        run = lambda rule, joining="threshold": SimpleNamespace(summary=dict(
            economy=dict(joining=joining, thresholds=rule),
            constants=dict(THRESHOLD_LOG_MEAN=-2.0, THRESHOLD_LOG_SPREAD=1.0)))
        self.assertIsNone(pf.threshold_values(run("uniform", "linear")))
        self.assertAlmostEqual(float(np.mean(pf.threshold_values(run("uniform")) <= 0.3)), 0.3, places=2)
        # Example: at a contact share of 0.05 a share Phi((ln 0.05 + 2) / 1) = 0.16 of thresholds is met.
        self.assertAlmostEqual(float(np.mean(pf.threshold_values(run("measured")) <= 0.05)), 0.16, delta=0.005)
        self.assertEqual(list(pf.threshold_values(run(0.2))), [0.2])
        # Reaching 0.2 by innovation alone takes ln((1 - a0) / 0.8) / 0.0025 months: 69 from 5%, 47 from 10%, so
        # the launch that reaches it within 60 months is 1 - 0.8 exp(0.15) = 0.0705.
        self.assertAlmostEqual(pf.hand_boundary(0.2, 0.0025), 0.0705, places=4)
        self.assertEqual(pf.hand_boundary(0.1, 0.0025), 0.0)
        # Thresholds kept per person: with uniform thresholds the path starts on the base's one curve (the first
        # month's chance is the same) and then falls behind it, since those still outside hold the higher
        # thresholds; with a common threshold of 0.2 and nobody leaving, a 5% launch has only innovation, so
        # participation after 60 months is 1 - 0.95 (1 - 0.0025)^60 = 0.182, below the threshold.
        launch = np.array([0.05, 0.2])
        lambdas = np.array([0.0, 0.01])
        kept = pf.mean_field(launch, 0.0025, 0.03, lambdas, 60, pf.threshold_values(run("uniform")))
        base = pf.one_curve(launch, 0.0025, 0.03, lambdas, 60)
        self.assertTrue(np.allclose(kept[:, :, 1], base[:, :, 1], atol=2e-4))
        self.assertTrue((kept[:, :, 60] < base[:, :, 60] - 0.02).all())
        alone = pf.mean_field(np.array([0.05]), 0.0025, 0.03, np.array([0.0]), 60, np.array([0.2]))
        self.assertAlmostEqual(float(alone[0, 0, 60]), 1 - 0.95 * (1 - 0.0025) ** 60, places=12)


class PackTest(unittest.TestCase):
    def test_a_packed_store_reads_back_and_has_the_same_bytes_every_time(self):
        import gzip
        import tempfile
        from pathlib import Path

        from scripts import pack_results
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / "run"
            run.mkdir()
            (run / "summary.json").write_text('{"cells": []}', encoding="utf-8")
            (run / "failure_counts.json").write_text("{}", encoding="utf-8")
            first = pack_results.pack(run, Path(folder) / "a")
            pack_results.pack(run, Path(folder) / "b")
            self.assertEqual(first, ["summary.json.gz"])                     # the failure counts are not shipped
            a, b = ((Path(folder) / name / "summary.json.gz").read_bytes() for name in ("a", "b"))
            self.assertEqual(a, b)
            self.assertEqual(gzip.decompress(a), b'{"cells": []}')
            self.assertEqual(pn.stored_text(Path(folder) / "a", "summary.json"), '{"cells": []}')


if __name__ == "__main__":
    unittest.main()

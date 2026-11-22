"""The registered claim's statistics in the population runner (docs/ANALYSIS_PLAN.md): hand cases on small
synthetic inputs, no population run. Each test's docstring works its numbers by hand."""
import contextlib
import io
import unittest
from itertools import product

import numpy as np

from cpm_abm.economy_abm import FAIL_COST, Economy, m0_rates
from scripts import run_economy_population as pop
from scripts.run_economy_figures import DOLLARS as ENGINE_DOLLARS

W = Economy(n=40)
SEEDS20 = tuple(range(20))


def synthetic_job(rate, a0, level, seed, saving_m0=1.0, saving_s0=10.0, gain=5.0, margin=1.0, failed=1.0,
                  failed_m0=2.0, monthly=0.01, monthly_m0=0.01, monthly_s0=0.01, owners=10.0, bound=None):
    """One job with every field the claim reads, for M1 and M2 alike (M0 and S0 beside). The seed adds a small
    spread (+/- 0.1 a seed in turn) so every interval is defined. Owners earn 10% a year in W2 by default, above
    DeFi's savings rate at every r_out, so V4 fires only where a test lowers it (owners=3.0 is the review's case).
    The gain under the cash-advance bound (15 Nov 2026) is ``bound`` in every group, the gain itself by default (the
    arm saves nothing on cash advances)."""
    wiggle = 0.1 * (1 if seed % 2 else -1)
    groups = lambda value: dict(**{f"gain_usd_a_year_by_{name}": [value + wiggle] * size
                                   for name, size in (("class", 4), ("quintile", 5), ("cycle", 2))},
                                worse_off=0.1)
    end = lambda: dict(groups(gain), bound=groups(gain if bound is None else bound))

    def against(saving):
        return dict(real_saving_usd_a_year=dict(total=saving + wiggle),
                    complete_gain=dict(face=end(), zero=end()),
                    complete_gain_parts_usd_a_year=dict(purchases_completed=50.0 + wiggle, durables=1.0))

    by_class = dict(class_sizes=[10, 10, 10, 10], completed=[1000.0] * 4, interest_pool=[1.0] * 4,
                    interest_card=[2.0] * 4, interest_outside=[3.0] * 4)
    real = dict(total=60.0, card_credit=0.0, term_credit=0.0)
    arm = dict(households=dict(counts=True), own_margin_usd_a_year=[margin, margin + wiggle],
               joint_usd_a_year=[margin, margin + wiggle], X=dict(X6=False), backing_topup_usd=0.0,
               against=dict(S0=against(saving_s0), M0=against(saving_m0)), real_part=real, by_class=by_class,
               owners=dict(net_pct=dict(W2=owners + wiggle)))
    count = lambda fails, bridged, path: dict(a_year=dict(fail_shares=fails, bridged_shares=bridged),
                                             monthly=dict(fail_shares=[path] * 60))
    base = lambda value: 0.0 if level == 0 else value
    return dict(r_out=rate, a0=a0, distress=level, seed=seed, recirculated=False,
                S0=dict(real_part=dict(real), by_class=by_class),
                arms=dict(M0=dict(real_part=dict(real), by_class=by_class), U=dict(arm), M1=dict(arm), M2=dict(arm)),
                failure_counts=dict(S0=count(failed_m0, 0.0, base(monthly_s0)), M0=count(failed_m0, 0.0, base(monthly_m0)),
                                    U=count(failed, 1.0, base(monthly)), M1=count(failed, 1.0, base(monthly)),
                                    M2=count(failed, 1.0, base(monthly))))


def synthetic_cell(rate, a0, level, seeds=20, persistent=20):
    """The decided cell as ``decide`` stores it, as far as the claim reads it: seeds and each pool arm's region."""
    interval = pop.wilson(persistent, seeds)
    region = dict(persistent_seeds=persistent, persistent_interval=interval)
    return dict(r_out=rate, a0=a0, distress=level, seeds=seeds,
                **{arm: dict(region=dict(region)) for arm in ("U", "M1", "M2")})


class Intervals(unittest.TestCase):
    def test_t_interval_hand_case(self):
        """1, 2, 3: mean 2, sd 1, t(0.975, 2) = 4.303, half-width 4.303 / sqrt(3) = 2.484: -0.484 to 4.484. One seed
        gives a mean and no interval; none gives nothing."""
        bounds = pop.t_bounds([1, 2, None, 3])
        self.assertAlmostEqual(bounds["mean"], 2.0)
        self.assertAlmostEqual(bounds["lower"], -0.484, places=3)
        self.assertAlmostEqual(bounds["upper"], 4.484, places=3)
        self.assertEqual(bounds["seeds"], 3)
        self.assertIsNone(pop.t_bounds([5.0])["lower"])
        self.assertEqual(pop.t_bounds([None, float("nan")])["seeds"], 0)

    def test_readings(self):
        """Against -2 from above: -1 to 3 supported; -2.5 to 1 inconclusive (it straddles); -5 to -3 falsified; the
        margin itself passes unless strict. From below, at most 1: 0 to 0.9 supported, 1.1 to 2 falsified."""
        self.assertEqual(pop.reading(-1, 3, -2), "supported")
        self.assertEqual(pop.reading(-2.5, 1, -2), "inconclusive")
        self.assertEqual(pop.reading(-5, -3, -2), "falsified")
        self.assertEqual(pop.reading(-2, 1, -2), "supported")
        self.assertEqual(pop.reading(0, 1, 0, strict=True), "inconclusive")
        self.assertEqual(pop.reading(0, 0.9, 1, side="below"), "supported")
        self.assertEqual(pop.reading(1.1, 2, 1, side="below"), "falsified")
        self.assertEqual(pop.reading(None, 2, 1), "undefined")

    def test_check_needs_the_bootstrap_to_agree(self):
        """Savings -1, -2, -3: mean -2, 95% t lower bound -2 - 4.303 / sqrt(3) = -4.48, inconclusive against -2,
        near the line. The bootstrap interval of the mean lies within the seeds' range, -3 to -1. Savings 5, 6, 7 read
        supported on both and hold."""
        weak = pop.check([-1, -2, -3], -2.0)
        self.assertAlmostEqual(weak["lower"], -4.4841, places=3)
        self.assertEqual((weak["reading"], weak["holds"], weak["near_the_line"]), ("inconclusive", False, True))
        self.assertTrue(-3 <= weak["bootstrap"][0] <= weak["bootstrap"][1] <= -1)
        strong = pop.check([5, 6, 7], -2.0)
        self.assertEqual((strong["reading"], strong["bootstrap_reading"], strong["holds"]),
                         ("supported", "supported", True))

    def test_wilson_seed_thresholds(self):
        """The claim row: 15 of 20 seeds is the least whose 95% Wilson lower bound is above one half (0.531; 14 gives
        0.481); under Bonferroni over 21 cells, z = 3.038, 17 of 20 (0.510; 16 gives 0.461). Three of three seeds
        reads 0.438 at 95%, so the development map's three seeds can never read Persistent by the rule."""
        alpha = pop.bonferroni_alpha("M1", W)
        self.assertGreater(pop.wilson_bounds(15, 20)[0], 0.5)
        self.assertLess(pop.wilson_bounds(14, 20)[0], 0.5)
        self.assertGreater(pop.wilson_bounds(17, 20, alpha)[0], 0.5)
        self.assertLess(pop.wilson_bounds(16, 20, alpha)[0], 0.5)
        self.assertAlmostEqual(pop.wilson_bounds(3, 3)[0], 0.4385, places=4)
        self.assertIsNone(pop.wilson_bounds(0, 0))


class Statistics(unittest.TestCase):
    def test_bonferroni_cells(self):
        """21 cells for M1 (3 r_out x 7 a0) and 14 for M2, whose r_out 2% cells at 2% CPI are its declared limit:
        levels 0.05 / 21 = 0.00238 and 0.05 / 14 = 0.00357."""
        self.assertEqual((pop.bonferroni_cells("M1", W), pop.bonferroni_cells("M2", W)), (21, 14))
        self.assertAlmostEqual(pop.bonferroni_alpha("M1", W), 0.05 / 21)
        self.assertAlmostEqual(pop.bonferroni_alpha("M2", W), 0.05 / 14)

    def test_seed_count_matches_the_statistics_row(self):
        """The statistics row's numbers, margin $2, 80% power at a true zero: 20 seeds carry a spread of $3.03 at 95%
        (3.02 needs 20, 3.04 needs 21) and $2.02 under Bonferroni over 21 cells; at spreads of $4, $6 and $8 the
        Bonferroni count is 65, 141 and 246; and $4.27 at 20 seeds is the spread at which a true zero passes half the
        time (power 0.5). A zero spread needs the least, 2; an undefined one gives None."""
        bonferroni = 0.05 / 21
        self.assertEqual(pop.seeds_needed(3.02, 2.0, 0.05), 20)
        self.assertEqual(pop.seeds_needed(3.04, 2.0, 0.05), 21)
        self.assertEqual(pop.seeds_needed(2.02, 2.0, bonferroni), 20)
        self.assertEqual([pop.seeds_needed(s, 2.0, bonferroni) for s in (4.0, 6.0, 8.0)], [65, 141, 246])
        self.assertEqual(pop.seeds_needed(4.26, 2.0, 0.05, power=0.5), 20)
        self.assertEqual(pop.seeds_needed(0.0, 2.0, 0.05), 2)
        self.assertIsNone(pop.seeds_needed(None, 2.0, 0.05))

    def test_pooled_spread(self):
        """Cells (1, 3) and (0, 4): variances 2 and 8 on one degree of freedom each, pooled sqrt((2 + 8) / 2) =
        sqrt(5) = 2.236; a cell with one seed adds nothing."""
        self.assertAlmostEqual(pop.pooled_spread([[1, 3], [0, 4], [7]]), np.sqrt(5))
        self.assertIsNone(pop.pooled_spread([[1], [None]]))

    def test_pooled_freedom(self):
        """The same cells pool 1 + 1 = 2 degrees of freedom, the one-seed cell adding none; 21 cells of 3 seeds, the
        final development map's cells, pool 42."""
        self.assertEqual(pop.pooled_freedom([[1, 3], [0, 4], [7]]), 2)
        self.assertEqual(pop.pooled_freedom([[0.0, 1.0, None, 2.0]] * 21), 42)
        self.assertEqual(pop.pooled_freedom([[1], [None]]), 0)

    def test_spread_bound_hand_case(self):
        """The rule of 17 Nov 2026: s x sqrt(nu / chi2_0.2(nu)). The final development map's binding reading, 1.1658
        over 42 degrees of freedom, has chi2_0.2(42) = 34.157, so 1.1658 x sqrt(42 / 34.157) = 1.293 at 0.8 (1.362
        at 0.9, 1.424 at 0.95); at M1's Bonferroni level and the dip's margin of one these need 30, 33 and 36 seeds
        against 26 at the point estimate. No spread, or no degree of freedom, has no bound."""
        alpha = pop.bonferroni_alpha("M1", W)
        self.assertEqual(pop.SEED_ASSURANCE, 0.8)
        bounds = [pop.spread_bound(1.1658, 42, q) for q in (0.8, 0.9, 0.95)]
        self.assertAlmostEqual(pop.spread_bound(1.1658, 42), 1.2927, places=4)
        np.testing.assert_allclose(bounds, [1.2927, 1.3621, 1.4241], atol=1e-4)
        self.assertEqual([pop.seeds_needed(s, 1.0, alpha) for s in [1.1658] + bounds], [26, 30, 33, 36])
        self.assertIsNone(pop.spread_bound(None, 42))
        self.assertIsNone(pop.spread_bound(1.0, 0))

    def test_spread_resolved(self):
        """``seeds_needed`` read the other way, margin $2, 80% power: 20 seeds resolve a spread up to $3.03 at 95%
        and $2.02 at the Bonferroni level over 21 cells, the statistics row's figures; 30 seeds up to $3.78 and
        $2.597, which 30 seeds resolve and a cent more does not."""
        alpha = pop.bonferroni_alpha("M1", W)
        self.assertAlmostEqual(pop.spread_resolved(20, 2.0, 0.05), 3.0283, places=4)
        self.assertAlmostEqual(pop.spread_resolved(20, 2.0, alpha), 2.0226, places=4)
        self.assertAlmostEqual(pop.spread_resolved(30, 2.0, 0.05), 3.7790, places=4)
        edge = pop.spread_resolved(30, 2.0, alpha)
        self.assertAlmostEqual(edge, 2.5971, places=4)
        self.assertEqual((pop.seeds_needed(edge - 0.001, 2.0, alpha), pop.seeds_needed(edge + 0.01, 2.0, alpha)),
                         (30, 31))

    def test_connected_blocks(self):
        """{(0, 0), (0, 1), (1, 1), (2, 3)}: the first three join by edges, (2, 3) stands alone; a corner does not
        join, so (0, 0) and (1, 1) alone would be two blocks of one, tied."""
        self.assertEqual(pop.connected_blocks({(0, 0), (0, 1), (1, 1), (2, 3)}), [[(0, 0), (0, 1), (1, 1)], [(2, 3)]])
        self.assertEqual(pop.connected_blocks({(0, 0), (1, 1)}), [[(0, 0)], [(1, 1)]])
        self.assertEqual(pop.connected_blocks(set()), [])

    def test_registered_shares(self):
        """P1 as first registered True, True, False over three seeds reads 0.667; X1 fires in one, 0.333."""
        rows = [dict(registered_tests=dict(P1=True, X1=False)), dict(registered_tests=dict(P1=True, X1=False)),
                dict(registered_tests=dict(P1=False, X1=True))]
        self.assertEqual(pop.registered_shares(rows), dict(P1=0.667, X1=0.333))
        self.assertEqual(pop.registered_shares([dict()]), {})


class Clauses(unittest.TestCase):
    def test_clause_b_real_cost(self):
        """Savings against M0 of -1, -2, -3 (mean -2, lower bound -4.48) fail the -$2 bound; against S0 of 9, 10, 11
        pass. With savings of 0.9 to 1.1 against M0 and 9.9 to 10.1 against S0 over 20 seeds both lower bounds are
        above zero: it holds and reads a saving."""
        jobs = [synthetic_job(0.044, 0.6, 0.0, s, saving_m0=-2.0 + (s - 1)) for s in range(3)]
        for j, value in zip(jobs, (-1.0, -2.0, -3.0)):
            j["arms"]["M1"]["against"]["M0"]["real_saving_usd_a_year"]["total"] = value
        weak = pop.clause_b("M1", jobs, None, 0.05)
        self.assertFalse(weak["holds"])
        self.assertAlmostEqual(weak["against_M0"]["lower"], -4.4841, places=3)
        good = pop.clause_b("M1", [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20], None, 0.05)
        self.assertTrue(good["holds"] and good["saving"])

    def test_break_even_rescue_and_cents(self):
        """The arm uses $1.40 a year more than M0 (saving -1.40) with 2.41 rescued shares a person a year and M0 none:
        a rescue at x leaves the arm 1.40 - (2 - x) 2.41 above M0, zero at x = 2 - 1.40 / 2.41 = 1.4191. Real cost $60
        over 60 months is $12 a year, over $1,000 of purchases completed: 1.2 cents a dollar. The $2 is the engine's
        failure cost."""
        self.assertAlmostEqual(pop.FAIL_USD, FAIL_COST * ENGINE_DOLLARS)
        jobs = [synthetic_job(0.044, 0.6, 0.0, s, saving_m0=-1.40) for s in (0, 1)]
        for j in jobs:
            j["arms"]["M1"]["against"]["M0"]["real_saving_usd_a_year"]["total"] = -1.40
            j["failure_counts"]["M1"]["a_year"]["bridged_shares"] = 2.41
        out = pop.real_cost_readouts("M1", jobs, W)
        self.assertAlmostEqual(out["break_even_rescue_usd"]["against_M0"]["cell"], 2 - 1.40 / 2.41, places=4)
        self.assertEqual(out["break_even_rescue_usd"]["against_M0"]["by_seed"], [1.4191, 1.4191])
        self.assertAlmostEqual(out["cents_per_dollar_completed"]["M1"], 1.2)
        self.assertAlmostEqual(out["real_cost_usd_a_year"]["S0"], 12.0)

    def test_clause_c_and_d(self):
        """(c): 1 failed share a year against M0's 2 and $51 more purchases completed (50 + 1 of durables), on 20
        seeds, holds. (d): every group gains $5 +/- 0.1, above -$2, holds; at -$3 every bound is below -$2, and the
        lowest is the first class against S0 at face."""
        jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
        c = pop.clause_c("M1", jobs, None, 0.05)
        self.assertTrue(c["holds"])
        self.assertAlmostEqual(c["against_M0"]["failed_shares"]["mean"], -1.0)
        self.assertAlmostEqual(c["against_M0"]["completed_usd"]["mean"], 51.0)
        self.assertTrue(pop.clause_d("M1", jobs, None, 0.05)["holds"])
        losing = pop.clause_d("M1", [synthetic_job(0.044, 0.6, 0.0, s, gain=-3.0) for s in SEEDS20], None, 0.05)
        self.assertFalse(losing["holds"])
        self.assertEqual((losing["lowest"]["group"], losing["lowest"]["against"], losing["lowest"]["end"]),
                         (pop.CLASSES[0], "S0", "face"))

    def test_clause_a(self):
        """20 seeds with households holding 90% and P routing (Wilson lower bound 0.839), the own margin and joint
        test at $1 +/- 0.1 in W2, no issuer leaving, no top-up, 20 Persistent seeds: holds. A seed whose issuer would
        leave fails it, and so does a cell with 14 Persistent seeds of 20 (lower bound 0.481)."""
        jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
        cell = synthetic_cell(0.044, 0.6, 0.0)
        self.assertTrue(pop.clause_a("M1", jobs, cell, 0.05)["holds"])
        self.assertFalse(pop.clause_a("M1", jobs, synthetic_cell(0.044, 0.6, 0.0, persistent=14), 0.05)["holds"])
        jobs[3]["arms"]["M1"] = dict(jobs[3]["arms"]["M1"], X=dict(X6=True))
        self.assertFalse(pop.clause_a("M1", jobs, cell, 0.05)["holds"])

    def test_clause_a_reads_paying_its_way_as_running_without_outside_money(self):
        """Since 5 Nov the pool pays its own way when it runs without outside money: with break-even coupons its own
        margin centres on zero by construction. Twenty seeds whose W2 margin and joint test are zero on average (+0.1
        and -0.1 by seed) pass the clause; the clause as first worded, which also asks the margin's lower bound above
        zero, does not, and both are stored. A margin of $1 passes both. A backing top-up in one seed is outside money
        and fails both."""
        cell = synthetic_cell(0.044, 0.6, 0.0)
        zero = pop.clause_a("M1", [synthetic_job(0.044, 0.6, 0.0, s, margin=0.0) for s in SEEDS20], cell, 0.05)
        self.assertTrue(zero["holds"])
        self.assertFalse(zero["holds_as_first_registered"])
        self.assertFalse(zero["own_margin_W2"]["holds"])
        one = pop.clause_a("M1", [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20], cell, 0.05)
        self.assertTrue(one["holds"] and one["holds_as_first_registered"])
        jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
        jobs[5]["arms"]["M1"] = dict(jobs[5]["arms"]["M1"], backing_topup_usd=3.0)
        topped = pop.clause_a("M1", jobs, cell, 0.05)
        self.assertFalse(topped["holds"] or topped["holds_as_first_registered"])

    def test_dips(self):
        """Failed shares a person a month of 0.1 under distress against 0.05 without, over months 25 to 60 (36
        months): a dip of 36 x 0.05 = 1.8, 0.6 a year; S0's dip 36 x 0.02 = 0.72, so against S0 1.08."""
        level = [synthetic_job(0.044, 0.6, 0.01, 0, monthly=0.1, monthly_s0=0.07, monthly_m0=0.05)]
        base = [synthetic_job(0.044, 0.6, 0.0, 0)]
        for arm in ("S0", "M0", "M1"):
            base[0]["failure_counts"][arm]["monthly"]["fail_shares"] = [0.05] * 60
        out = pop.dips("M1", level, base)
        self.assertAlmostEqual(out["own"][0], 1.8)
        self.assertAlmostEqual(out["against_S0"][0], 1.8 - 0.72)
        self.assertAlmostEqual(out["against_M0"][0], 1.8)
        self.assertEqual(pop.DIP_MONTHS, (25, 60))

    def test_the_dip_is_read_a_year(self):
        """The distress row reads the dip per consumer unit a year against one failed payment a year. Twenty seeds
        whose dip against S0 and against M0 is 2.4 failed payments over the 36 months (0.8 a year, a little more or
        less by seed) are within it; at 3.6 over the 36 months (1.2 a year) they are not. Read on the 36-month sum,
        2.4 would have failed."""
        def leg(monthly):
            level = [synthetic_job(0.044, 0.6, 0.01, s, monthly=0.05 + monthly + (0.001 if s % 2 else -0.001),
                                   monthly_s0=0.05, monthly_m0=0.05) for s in SEEDS20]
            base = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
            for job in base:
                for arm in ("S0", "M0", "M1"):
                    job["failure_counts"][arm]["monthly"]["fail_shares"] = [0.05] * 60
            return pop.stress_leg("M1", synthetic_cell(0.044, 0.6, 0.01), level, base, 0.05)
        within, beyond = leg(2.4 / 36), leg(3.6 / 36)
        self.assertAlmostEqual(within["dip"]["against_S0"]["mean"], 0.8, places=6)
        self.assertAlmostEqual(within["dip_36_months_against_S0"], 2.4, places=3)
        self.assertTrue(within["dip"]["against_S0"]["holds"] and within["dip"]["against_M0"]["holds"])
        self.assertAlmostEqual(beyond["dip"]["against_S0"]["mean"], 1.2, places=6)
        self.assertFalse(beyond["dip"]["against_S0"]["holds"])

    def test_better_than_m0(self):
        """V2: the same interest ($6 a person a year) in the arm and M0 is not shown worse. V4: owners earn 3% +/-
        0.1 in W2; DeFi's savings rate at r_out 4.4% is m0_rates' (4.4% less the Sky spread); M2 adds 2% CPI."""
        jobs = [synthetic_job(0.044, 0.6, 0.0, s, owners=3.0) for s in SEEDS20]
        savings = 1200 * m0_rates(0.044 / 12)[0]
        out = pop.better_than_m0("M1", 0.044, jobs, W)
        self.assertFalse(out["V2"]["shown_worse"])
        self.assertAlmostEqual(out["V2"]["interest_usd_a_year"]["mean"], 0.0)
        self.assertGreater(savings, 3.0)                    # so the review's owners at 3% are shown worse
        self.assertAlmostEqual(out["V4"]["mean"], 3.0 - savings, places=3)
        self.assertEqual(out["V4"]["shown_worse"], 3.0 < savings)
        self.assertAlmostEqual(pop.better_than_m0("M2", 0.044, jobs, W)["V4"]["mean"], 5.0 - savings, places=3)


class Map(unittest.TestCase):
    def build(self):
        """A map of four (r_out, a0) cells at r_out 4.4% and 6% and a0 0.05 and 0.1, each at distress 0 and 0.5%, 20
        seeds: three cells pass everything, the fourth (6%, 0.1) saves -$5 against M0, failing (b); its dips are
        none (the same failures at both levels)."""
        cells, jobs = [], []
        for rate in (0.044, 0.06):
            for a0 in (0.05, 0.1):
                bad = (rate, a0) == (0.06, 0.1)
                for level in (0.0, 0.005):
                    cells.append(synthetic_cell(rate, a0, level))
                    jobs += [synthetic_job(rate, a0, level, s, saving_m0=-5.0 if bad else 1.0) for s in SEEDS20]
        return cells, jobs

    def test_claim_block_region_and_seed_count(self):
        """Three cells pass (a) to (d) and withstand 0.5% (no dip), so (e) passes with highest level 0.005 and all is
        true; the fourth fails (b) and so (e) is not applicable. The three passing cells, (4.4%, 0.05), (4.4%, 0.1) and
        (6%, 0.05), join by edges into one block, the region at level 0 and at 0.5%. The seed count is the pooled
        spread's: every saving moves by 0.1 a seed, so 0.1026 (20 seeds, ddof 1), and needs few seeds (at least 2)."""
        cells, jobs = self.build()
        stats = pop.claim_statistics(cells, jobs, W)
        at = {(c["r_out"], c["a0"], c["distress"]): c for c in cells}
        good = at[(0.044, 0.05, 0.0)]["M1"]["claim"]
        self.assertEqual([good[k]["status"] for k in "abcde"], ["pass"] * 5)
        self.assertTrue(good["all"] and good["all_bonferroni"] and good["in_region"])
        self.assertEqual(good["e"]["highest_level"], 0.005)
        bad = at[(0.06, 0.1, 0.0)]["M1"]["claim"]
        self.assertEqual((bad["b"]["status"], bad["e"]["status"], bad["all"], bad["in_region"]),
                         ("fail", "not applicable", False, False))
        self.assertEqual(stats["regions"]["M1"][0]["region"], [[0.044, 0.05], [0.044, 0.1], [0.06, 0.05]])
        self.assertEqual(stats["regions"]["M1"][1]["region"], [[0.044, 0.05], [0.044, 0.1], [0.06, 0.05]])
        self.assertEqual(len(stats["holds_somewhere"]["M1"]), 3)
        real = at[(0.044, 0.05, 0.0)]["M1"]["real_cost"]
        self.assertTrue(real["holds"] and real["saving"])
        self.assertIn("break_even_rescue_usd", real)
        self.assertIn("better_than_M0", at[(0.044, 0.05, 0.005)]["U"])
        self.assertTrue(at[(0.044, 0.05, 0.005)]["M1"]["stress_leg"]["withstands"])
        self.assertEqual(stats["bonferroni"]["M2"]["cells"], 14)
        self.assertLessEqual(stats["seeds"]["seeds"], pop.SEED_CAP)
        self.assertGreaterEqual(stats["seeds"]["seeds"], 2)
        self.assertAlmostEqual(stats["seeds"]["readings"][0]["spread"], round(np.std([0.1, -0.1] * 10, ddof=1), 4))

    def test_the_stress_clause_reads_two_points_as_its_headline(self):
        """The harsh stress (decided 14 Nov 2026): every level still runs and is tested in order, and (e) reads the
        2% level as its headline, labelled 2009's wage loss before unemployment insurance. One cell at r_out 4.4% and
        a0 0.05, 20 seeds, at every level. With no dip every level is withstood: highest 0.02, the headline withstood.
        With M1's failed shares 0.11 a month at 1.5% against S0's 0.01 (a dip of 3.6 over the 36 months, 1.2 a year,
        beyond one failed payment) the levels stop there: highest 0.01, the headline not withstood. With only 0.5% and
        1% run the headline cannot be read: None. A cell failing (b) at level 0 has (e) not applicable and no
        headline reading."""
        def read(levels, worse=None, bad=False):
            cells = [synthetic_cell(0.044, 0.05, level) for level in levels]
            jobs = [synthetic_job(0.044, 0.05, level, s, saving_m0=-5.0 if bad else 1.0,
                                  **(dict(monthly=0.11) if level == worse else {})) for level in levels for s in SEEDS20]
            pop.claim_statistics(cells, jobs, W)
            return cells[0]["M1"]["claim"]["e"]
        self.assertEqual(pop.STRESS_HEADLINE, pop.DISTRESS[-1])
        label = "2009's wage loss before unemployment insurance"
        every = read(pop.DISTRESS)
        self.assertEqual((every["status"], every["highest_level"]), ("pass", 0.02))
        self.assertEqual(every["headline"], dict(distress=0.02, label=label, withstands=True))
        self.assertEqual([level["distress"] for level in every["tested"]], list(pop.STRESS_LEVELS))
        stopped = read(pop.DISTRESS, worse=0.015)
        self.assertEqual((stopped["status"], stopped["highest_level"]), ("pass", 0.01))
        self.assertEqual([level["withstands"] for level in stopped["tested"]], [True, True, False])
        self.assertFalse(stopped["headline"]["withstands"])
        self.assertIsNone(read((0.0, 0.005, 0.01))["headline"]["withstands"])
        failing = read((0.0, 0.005), bad=True)
        self.assertEqual((failing["status"], failing["headline"]["withstands"]), ("not applicable", None))

    def test_declared_limit_and_underpowered(self):
        """M2 at r_out 2% is its declared limit: every clause not applicable, all false. A cell whose savings spread
        $30 a seed needs far more than its 20 seeds: underpowered, so it cannot enter the region though it passes.
        M1's own cell at 2% passes (a), (b) and (d), which is what a passing cell is (the claim row; (e) is read for
        passing cells and no stress level was run here), so it is the region."""
        cells = [synthetic_cell(0.02, 0.05, 0.0), synthetic_cell(0.044, 0.05, 0.0)]
        jobs = [synthetic_job(0.02, 0.05, 0.0, s) for s in SEEDS20]
        jobs += [synthetic_job(0.044, 0.05, 0.0, s, saving_s0=50.0) for s in SEEDS20]
        for j in jobs[20:]:
            j["arms"]["M1"]["against"]["S0"]["real_saving_usd_a_year"]["total"] = 50.0 + (30 if j["seed"] % 2 else -30)
        stats = pop.claim_statistics(cells, jobs, W)
        limit = cells[0]["M2"]["claim"]
        self.assertEqual((limit["a"]["status"], limit["all"]), ("not applicable", False))
        wide = cells[1]["M1"]["claim"]
        self.assertTrue(wide["underpowered"])
        self.assertFalse(wide["in_region"])
        self.assertEqual(stats["regions"]["M1"][0]["region"], [[0.02, 0.05]])
        self.assertTrue(cells[0]["M1"]["claim"]["all"] and cells[0]["M1"]["claim"]["e"]["status"] == "not applicable")


def decided_cell(rate, a0, level, seeds):
    """A level's decided cell as ``decide`` stores it from the hand-case seeds of test_economy_abm (``map_seed``),
    wrapped with the cell's own coordinates for ``claim_statistics``."""
    decided = pop.decide(seeds, 0.044, 0.6, 0.0, False, Economy())
    return dict(decided, r_out=rate, a0=a0, distress=level, seeds=len(seeds))


def credit_jobs(arm_balance, m0_balance, arm_interest=None):
    """Twenty synthetic jobs whose borrowers carry instalment principal-time ``arm_balance`` in M1 and ``m0_balance`` in
    M0 ($ a person, a seed's wiggle of 1% in M1), each paying $6 a person a year of interest, M1 ``arm_interest`` if
    given: the rate is the interest over that balance."""
    jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
    unit = pop.TERM_LENDING_COST * W.months
    for j in jobs:
        bump = 1.0 + (0.01 if j["seed"] % 2 else -0.01)
        j["arms"]["M1"]["real_part"] = dict(total=60.0, card_credit=0.0, term_credit=unit * arm_balance * bump)
        j["arms"]["M0"]["real_part"] = dict(total=60.0, card_credit=0.0, term_credit=unit * m0_balance)
        if arm_interest is not None:
            by_class = dict(j["arms"]["M1"]["by_class"])
            by_class.update(interest_pool=[arm_interest / 3] * 4, interest_card=[arm_interest / 3] * 4,
                            interest_outside=[arm_interest / 3] * 4)
            j["arms"]["M1"]["by_class"] = by_class
    return jobs


class WorseThanM0(unittest.TestCase):
    """The row '"Worse than M0" uses completed trade, harm to any group, borrowers' credit cost and owners' realised
    return': each of the four parts firing alone leaves the cell not Persistent, failing (a), out of the region and
    falsified, with the part named."""

    def assert_falsified_by(self, cell, part):
        claim = cell["M1"]["claim"]
        self.assertEqual(claim["worse_than_M0"]["fired"], [part])
        self.assertTrue(claim["worse_than_M0"]["fires"])
        self.assertEqual(set(claim["worse_than_M0"]) - {"fires", "fired"},
                         {"completed_trade", "group_harm", "credit_cost", "owners_return"})
        self.assertLess(pop.wilson_bounds(cell["M1"]["region"]["persistent_seeds"], cell["seeds"])[0], 0.5)
        self.assertEqual(claim["a"]["status"], "fail")
        self.assertFalse(claim["in_region"] or claim["all"])
        self.assertEqual(claim["reading"], "falsified")
        self.assertIn(f"worse_than_M0.{part}", claim["decided_by"])

    def test_the_reviews_reproducer_owners_return(self):
        """Owners earn 3% +/- 0.1 in W2, below DeFi's savings rate at r_out 4.4%: V4 is shown worse, so (a) fails and
        the cell is out of the region (the review printed True, pass, True)."""
        c = synthetic_cell(.044, .6, 0)
        p = pop.claim_statistics([c], [synthetic_job(.044, .6, 0, s, owners=3.0) for s in range(20)], W)
        self.assertEqual((c["M1"]["better_than_M0"]["V4"]["shown_worse"], c["M1"]["claim"]["a"]["status"],
                          c["M1"]["claim"]["in_region"]), (True, "fail", False))
        self.assert_falsified_by(c, "owners_return")
        self.assertEqual(c["M1"]["region"]["persistent_seeds"], 0)
        self.assertEqual(p["regions"]["M1"][0]["region"], [])
        # The same jobs with owners at 10% pass: nothing fires.
        good = synthetic_cell(.044, .6, 0)
        pop.claim_statistics([good], [synthetic_job(.044, .6, 0, s) for s in range(20)], W)
        self.assertFalse(good["M1"]["claim"]["worse_than_M0"]["fires"])
        self.assertEqual((good["M1"]["claim"]["reading"], good["M1"]["claim"]["in_region"]), ("supported", True))

    def test_credit_cost_fires_on_the_rate_only(self):
        """M1's borrowers pay $6 a year on $100 of principal-time (6% +/- 1%), M0's on $200 (3%): the rate is 3 points
        higher in every seed, its t and bootstrap intervals wholly above zero, so V2 fires alone. Paying twice the
        interest ($12) on twice M0's principal-time ($400, the same 3%) is borrowing more at the same price: the
        interest report's interval lies above zero, but it fires nothing and the cell passes."""
        cell = synthetic_cell(.044, .6, 0)
        pop.claim_statistics([cell], credit_jobs(100.0, 200.0), W)
        v2 = cell["M1"]["better_than_M0"]["V2"]
        self.assertGreater(v2["rate_pct"]["lower"], 0)
        self.assertTrue(v2["shown_worse"] and v2["rate_pct"]["fires"])
        self.assertFalse(v2["interest_usd_a_year"]["fires"])
        self.assert_falsified_by(cell, "credit_cost")
        more = synthetic_cell(.044, .6, 0)
        pop.claim_statistics([more], credit_jobs(400.0, 200.0, arm_interest=12.0), W)
        v2 = more["M1"]["better_than_M0"]["V2"]
        self.assertTrue(v2["interest_usd_a_year"]["shown_worse"])
        self.assertFalse(v2["interest_usd_a_year"]["fires"] or v2["shown_worse"])
        self.assertEqual((more["M1"]["claim"]["reading"], more["M1"]["claim"]["in_region"]), ("supported", True))

    def test_trade_or_a_group_alone(self):
        """Twenty hand-case seeds (test_economy_abm's ``map_seed``), every persistence test holding: trade worse than
        M0 in all of them, or one group harmed in all of them, fires X4 in ``decide``, no seed is Persistent, and the
        claim then fails (a) and reads falsified by that part."""
        from tests.test_economy_abm import map_seed
        jobs = [synthetic_job(.044, .6, 0, s) for s in SEEDS20]
        for part, given in (("completed_trade", dict(worse_trade=True)), ("group_harm", dict(harmed=(2,)))):
            cell = decided_cell(.044, .6, 0.0, [map_seed(seed, **given) for seed in SEEDS20])
            self.assertTrue(cell["M1"]["X4"])
            self.assertTrue(cell["M1"]["verdict"].startswith("Against CPM"))
            self.assertEqual(cell["M1"]["region"]["persistent_seeds"], 0)
            pop.claim_statistics([cell], jobs, W)
            self.assert_falsified_by(cell, part)

    def test_decide_reads_v2_and_v4_before_the_persistent_count(self):
        """``decide`` itself: twenty hand-case seeds, all Persistent, whose owners earn 0% +/- 0.1 in W2, below DeFi's
        savings rate: V4 fires, so X4 fires, every seed counts worse than M0, the verdict is Against CPM, none is
        Persistent and the region reads "not persistent"; with no owner reading nothing fires and all 20 stay
        Persistent."""
        from tests.test_economy_abm import map_seed
        seeds = [map_seed(seed) for seed in SEEDS20]
        for seed in seeds:
            seed["arms"]["M1"]["owners"]["net_pct"]["W2"] = 0.1 if seed["seed"] % 2 else -0.1
        cell = decided_cell(.044, .6, 0.0, seeds)["M1"]
        self.assertTrue(cell["X4"] and cell["better_than_M0"]["V4"]["shown_worse"])
        self.assertEqual(cell["worse_than_M0"]["fired"], ["owners_return"])
        self.assertEqual((cell["verdict"], cell["persistent_share"], cell["worse_than_M0_seeds"]),
                         ("Against CPM", 0.0, 20))
        self.assertEqual((cell["region"]["persistent_seeds"], cell["region"]["verdict"]), (0, "not persistent"))
        clean = decided_cell(.044, .6, 0.0, [map_seed(seed) for seed in SEEDS20])["M1"]
        self.assertFalse(clean["X4"] or clean["worse_than_M0"]["fires"])
        self.assertEqual(clean["region"]["persistent_seeds"], 20)
        self.assertTrue(clean["verdict"].startswith("Persistent, no falsifier"))


class Review13Nov(unittest.TestCase):
    """Cases from the 13 Nov review, on its own reproducers."""

    def test_the_seed_planner_reads_the_yearly_dip(self):
        """Dips of 0.2 +/- 0.15 failed shares a month in the level's run against 0.2 in S0's and M0's, so
        +/- 5.4 over months 25 to 60 by seed, +/- 1.8 a year: the yearly spread pooled is 1.8468 (5.5403 on the
        36-month sums), and the planner's dip reading asks the same seeds as the cell's own stress leg, 56."""
        cells = [synthetic_cell(.044, .6, d) for d in (0, .005)]
        base = [synthetic_job(.044, .6, 0, s) for s in range(20)]
        stress = [synthetic_job(.044, .6, .005, s, monthly=.2 + (.15 if s % 2 else -.15), monthly_s0=.2,
                                monthly_m0=.2) for s in range(20)]
        stats = pop.claim_statistics(cells, base + stress, W)
        reading = next(x for x in stats["seeds"]["readings"] if (x["arm"], x["reading"]) == ("M1", "dip against M0"))
        self.assertAlmostEqual(reading["spread"], 1.8468, places=4)
        self.assertEqual(reading["seeds"], cells[1]["M1"]["stress_leg"]["seeds_needed"])
        self.assertEqual(reading["seeds"], 56)
        self.assertEqual(stats["seeds"]["confirmation_seeds_now"], 30)
        # Beside it (17 Nov 2026): one cell of 20 seeds has 19 degrees of freedom, and the bound needs more seeds.
        self.assertEqual(reading["freedom"], 19)
        self.assertAlmostEqual(reading["spread_bound"], pop.spread_bound(reading["spread"], 19), places=3)
        self.assertGreater(reading["seeds_assured"], reading["seeds"])

    def test_the_planner_assures_thirty_seeds_on_the_binding_reading(self):
        """The final development map's binding reading made by hand: 21 cells of 3 seeds at 0.5 points whose yearly
        dip against S0 and against M0 is -1.1658, 0 and +1.1658 in every cell (monthly failed shares 0.2 less, at and
        above 1.1658 / 12 against 0.2 for S0 and M0), so a pooled spread of 1.1658 on 42 degrees of freedom. At M1's
        Bonferroni level that reading needs 26 seeds and, at the bound 1.293, 30, and the planner's counts are 26
        and 30; the cost readings, spread 0.1155 from the +/- 0.1 a seed, need few. Indexed CPM has 14 cells and 28
        degrees of freedom, so a wider bound, 1.328, at its own level, 0.05 / 14: 24 seeds and 30 assured."""
        cells, jobs, step = [], [], 1.1658 / 12
        for rate, a0 in product(pop.RATES, pop.A0S):
            cells += [synthetic_cell(rate, a0, level, seeds=3, persistent=3) for level in (0.0, 0.005)]
            for seed, side in zip(range(3), (-1, 0, 1)):
                jobs.append(synthetic_job(rate, a0, 0.0, seed))
                jobs.append(synthetic_job(rate, a0, 0.005, seed, monthly=0.2 + side * step, monthly_s0=0.2,
                                          monthly_m0=0.2))
        key = lambda item: (item["r_out"], item["a0"], item["distress"])
        by_cell = {}
        for j in jobs:
            by_cell.setdefault(key(j), []).append(j)
        planner = pop.confirmation_seeds({key(c): c for c in cells}, by_cell, W)
        dip = {(r["arm"], r["reading"]): r for r in planner["readings"] if r["distress"] == 0.005}
        for other in ("S0", "M0"):
            got = dip[("M1", f"dip against {other}")]
            self.assertEqual((got["spread"], got["cells"], got["freedom"], got["seeds"], got["seeds_assured"]),
                             (1.1658, 21, 42, 26, 30))
            self.assertAlmostEqual(got["spread_bound"], 1.2927, places=4)
            indexed = dip[("M2", f"dip against {other}")]
            self.assertEqual((indexed["cells"], indexed["freedom"], indexed["seeds"], indexed["seeds_assured"]),
                             (14, 28, 24, 30))
            self.assertAlmostEqual(indexed["spread_bound"], 1.3277, places=4)
        self.assertEqual((planner["seeds"], planner["seeds_assured"], planner["assurance"], planner["capped_assured"]),
                         (26, 30, 0.8, False))
        # At the tie of 30 the reading with the larger bound is named, here indexed CPM's.
        self.assertEqual((planner["largest_assured"]["arm"], planner["largest_assured"]["reading"][:3],
                          planner["largest_assured"]["seeds_assured"]), ("M2", "dip", 30))
        self.assertEqual(planner["seeds_assured"], pop.CONFIRMATION_COUNT)
        cost = next(r for r in planner["readings"] if (r["arm"], r["reading"]) == ("M1", "cost against M0"))
        self.assertEqual((cost["spread"], cost["freedom"]), (0.1155, 42))
        self.assertLess(cost["seeds_assured"], 10)

    def test_clause_d_reads_t_and_bootstrap_for_every_group(self):
        """The first class's complete gain against M0 at face is -8.1 in two seeds and 0 in eighteen: the t
        lower bound -1.9768 is above -$2 but the bootstrap's -2.025 straddles it, so the group is not supported and
        (d) does not hold, inconclusive, near the line, the group named. A group with no value in any seed is
        undefined: (d) does not hold and names it."""
        values = [-8.1, -8.1] + [0.] * 18
        jobs = [synthetic_job(.044, .6, 0, s) for s in range(20)]
        for j, x in zip(jobs, values):
            j["arms"]["M1"]["against"]["M0"]["complete_gain"]["face"]["gain_usd_a_year_by_class"][0] = x
        reference = pop.check(values, -2)
        self.assertEqual((reference["reading"], reference["bootstrap_reading"]), ("supported", "inconclusive"))
        d = pop.clause_d("M1", jobs, None, .05)
        self.assertFalse(d["holds"])
        self.assertEqual((d["reading"], d["decided_by"]), ("inconclusive", [f"M0_face.{pop.CLASSES[0]}"]))
        self.assertTrue(d["groups"]["M0_face"][pop.CLASSES[0]]["near_the_line"])
        cell = synthetic_cell(.044, .6, 0)
        pop.claim_statistics([cell], jobs, W)
        self.assertIn(f"d.groups.M0_face.{pop.CLASSES[0]}", cell["M1"]["claim"]["near_the_line_parts"])
        self.assertEqual(cell["M1"]["claim"]["d"]["status"], "fail")
        empty = [synthetic_job(.044, .6, 0, s) for s in range(20)]
        for j in empty:
            j["arms"]["M1"]["against"]["S0"]["complete_gain"]["zero"]["gain_usd_a_year_by_cycle"][1] = None
        d = pop.clause_d("M1", empty, None, .05)
        self.assertFalse(d["holds"])
        self.assertEqual([(u["group"], u["against"], u["end"]) for u in d["undefined_groups"]],
                         [(pop.GROUP_NAMES["cycle"][1], "S0", "zero")])

    def test_three_way_readings(self):
        """Savings against M0 of -2 +/- 0.1 straddle the -$2 margin, (b) inconclusive and the cell
        inconclusive; at -5 +/- 0.1 the interval lies wholly below it, (b) falsified and the cell falsified, each naming
        (b)'s comparison against M0. status keeps pass and fail."""
        found = {}
        for saving in (-2., -5.):
            c = synthetic_cell(.044, .6, 0)
            pop.claim_statistics([c], [synthetic_job(.044, .6, 0, s, saving_m0=saving) for s in range(20)], W)
            claim = c["M1"]["claim"]
            found[saving] = (claim["b"]["status"], claim["b"]["reading"], claim["b"]["decided_by"],
                             claim["reading"], claim["decided_by"], claim["a"]["reading"], claim["d"]["reading"])
        self.assertEqual(found[-2.], ("fail", "inconclusive", ["against_M0"], "inconclusive", ["(b).against_M0"],
                                      "supported", "supported"))
        self.assertEqual(found[-5.], ("fail", "falsified", ["against_M0"], "falsified", ["(b).against_M0"],
                                      "supported", "supported"))
        self.assertEqual(pop.three_way([("x", "supported"), ("y", "inconclusive")]),
                         dict(reading="inconclusive", decided_by=["y"]))
        self.assertEqual(pop.share_reading([0.2, 0.5]), "falsified")
        self.assertEqual(pop.share_reading([0.45, 0.8]), "inconclusive")

    def test_stress_legs_keep_every_clause(self):
        """At 0.5% every stress leg keeps each clause's full block (clause (b)'s two intervals, clause (a)'s
        first-worded reading) with three-way readings, and clause (b)'s two read-outs are stored at that level."""
        cells, jobs = Map().build()
        pop.claim_statistics(cells, jobs, W)
        stress = next(c["M1"] for c in cells if c["distress"] > 0)
        leg = stress["stress_leg"]
        self.assertEqual(set(leg["clauses"]), {"a", "b", "c", "d"})
        self.assertIn("lower", leg["clauses"]["b"]["against_M0"])
        self.assertIn("holds_as_first_registered", leg["clauses"]["a"])
        self.assertEqual(leg["reading"], "supported")
        self.assertIn("break_even_rescue_usd", stress["real_cost"])
        self.assertIn("cents_per_dollar_completed", stress["real_cost"])
        self.assertIn("worse_than_M0", leg)

    def test_the_claim_map(self):
        """The claim map reads the stored claim blocks: in the Map build, three cells are in the region at
        level 0 and at 0.5%, the fourth falsified by (b) at level 0; the older figures are the persistence-and-groups
        view. The figure is written from a store holding them."""
        import json
        import tempfile
        from pathlib import Path
        from scripts import run_region_figures as figures
        cells, jobs = Map().build()
        pop.claim_statistics(cells, jobs, W)
        at = {(c["r_out"], c["a0"], c["distress"]): c for c in cells}
        self.assertEqual(figures.claim_reading(at[(0.044, 0.05, 0.0)], "M1"), "in the region")
        self.assertEqual(figures.claim_reading(at[(0.06, 0.1, 0.0)], "M1"), "falsified")
        self.assertEqual(figures.claim_reading(at[(0.044, 0.05, 0.005)], "M1"), "in the region")
        self.assertIsNone(figures.claim_reading(dict(distress=0.0, M1=dict(region=dict(verdict="stable"))), "M1"))
        self.assertIn("not the claim map", figures.PERSISTENCE_VIEW)
        with tempfile.TemporaryDirectory() as folder:
            written = []
            figures.setup()
            figures.claim_map(json.loads(json.dumps(cells)), Path(folder), written)
            self.assertEqual(written, ["claim_map"])
            self.assertGreater((Path(folder) / "claim_map.png").stat().st_size, 1000)


class Settings(unittest.TestCase):
    def test_seeds_and_population(self):
        """The confirmation block runs from 20261401, at most 100 seeds (20261401 to 20261500), never run, touching no
        retired block (20261101 to 20261120, 20261201 to 20261220, 20261301 to 20261308) and no development seed; its
        count is 30 (decided 17 Nov 2026), so SEEDS["confirmation"] is 20261401 to 20261430, and the one declared
        extension runs to 60 seeds, adding 20261431 to 20261460, inside the block. The sweep entry records the size
        sweep's seeds. The runner's default population is 4,000 (decided 12 Nov)."""
        self.assertEqual((pop.CONFIRMATION_COUNT, pop.CONFIRMATION_EXTENSION), (30, 60))
        self.assertEqual(pop.SEEDS["confirmation"], tuple(range(20261401, 20261431)))
        extension = pop.confirmation_block(pop.CONFIRMATION_EXTENSION)[pop.CONFIRMATION_COUNT:]
        self.assertEqual(extension, tuple(range(20261431, 20261461)))
        self.assertTrue(set(extension) <= set(pop.CONFIRMATION_RESERVED))
        self.assertEqual(pop.CONFIRMATION_RESERVED, tuple(range(20261401, 20261501)))
        retired = set().union(*map(set, pop.RETIRED_SEEDS))
        self.assertFalse(set(pop.CONFIRMATION_RESERVED) & (retired | set(pop.SEEDS["development"])
                                                           | set(pop.SEEDS["sweep"])))
        self.assertEqual(pop.SEEDS["sweep"], tuple(range(20261301, 20261309)))
        self.assertEqual(pop.POPULATION, 4000)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pop.options().parse_args(["--seeds", "development"]).n, 4000)

    def test_confirmation_uses_exactly_the_frozen_count(self):
        """n = 14 is 20261401 to 20261414 and n = 37 is 20261401 to 20261437 (below and above the old placeholder
        20), with no simulation; any count outside 2 to 100, or not a whole number, is refused; the count of 30
        gives 20261401 to 20261430; with no count the confirmation set is refused while the development set is given
        as before."""
        from unittest import mock
        self.assertEqual(pop.confirmation_block(14), tuple(range(20261401, 20261415)))
        self.assertEqual(pop.confirmation_block(37), tuple(range(20261401, 20261438)))
        self.assertEqual(pop.seeds_for("confirmation", 37), tuple(range(20261401, 20261438)))
        self.assertEqual(len(pop.confirmation_block(2)) + len(pop.confirmation_block(100)), 102)
        for bad in (0, 1, 101, 500, -3, 20.0, "20", True, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                pop.confirmation_block(bad)
        self.assertEqual(pop.seeds_for("confirmation"), tuple(range(20261401, 20261431)))
        # ``seeds_for`` reads the count where it is defined, so removing it there brings the refusal back.
        with mock.patch("cpm_abm.experiment.grid.CONFIRMATION_COUNT", None), self.assertRaises(ValueError):
            pop.seeds_for("confirmation")
        self.assertEqual(pop.seeds_for("development"), (20261021, 20261022, 20261023))

    def test_a_confirmation_run_is_refused_without_a_count_and_workers_are_capped(self):
        """With no confirmation count, ``main`` with --seeds confirmation exits with a message naming the count and
        writes nothing (its output folder is never made); so does --workers 13 on the development seeds. The default
        is 12 workers."""
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pop.options().parse_args(["--seeds", "development"]).workers, 12)
        self.assertEqual((pop.WORKERS, pop.WORKERS_MOST), (12, 12))
        with tempfile.TemporaryDirectory() as folder, mock.patch("cpm_abm.experiment.grid.CONFIRMATION_COUNT", None):
            for argv, said in ((["--seeds", "confirmation"], "confirmation seed count is not set"),
                               (["--seeds", "confirmation", "--timing"], "confirmation seed count is not set"),
                               (["--seeds", "development", "--workers", "13"], "--workers must be from 1 to 12")):
                target = Path(folder) / "never"
                err = io.StringIO()
                with mock.patch.object(sys, "argv", ["run_economy_population.py", *argv, "--output", str(target)]), \
                        contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                    pop.main()
                self.assertIn(said, err.getvalue())
                self.assertFalse(target.exists())


def skewed_sample():
    """26 seeds, 23 at 0 and 3 at 10 (mean 1.154, sd 3.258): the 95% t upper bound is 2.470 and the bootstrap's upper
    bound 2.692 (resampled means reach 7 tens in 26 often enough), so against 2.6 from above the t interval lies wholly
    below the margin and the bootstrap interval straddles it."""
    return [0.0] * 23 + [10.0] * 3


class Audit13Nov(unittest.TestCase):
    """The 13 Nov source audit of the analysis scripts: decisions read unrounded bounds, falsified needs both
    intervals, and the owners'-return part of worse than M0 uses both."""

    def test_the_persistent_reading_uses_the_unrounded_wilson_bound(self):
        """15 of 21 (lower bound 0.50044), 18 of 26 (0.50011), 46 of 75 (0.50017) and 51 of 84 (0.50022) are stored as
        0.500 but read Persistent and not near the line; 14 of 20 (0.481) reads neither Persistent nor clear."""
        for hits, total in ((15, 21), (18, 26), (46, 75), (51, 84)):
            self.assertEqual(pop.wilson(hits, total)[0], 0.5)
            self.assertGreater(pop.wilson_unrounded(hits, total)[0], 0.5)
            self.assertEqual(pop.persistent_on_wilson(hits, total), (True, False), (hits, total))
        self.assertAlmostEqual(pop.wilson(14, 20)[0], 0.481)
        self.assertEqual(pop.persistent_on_wilson(14, 20), (False, True))
        self.assertEqual(pop.persistent_on_wilson(0, 0), (False, False))

    def test_falsified_needs_both_intervals(self):
        """The skewed sample against 2.6 from above: t reads falsified, the bootstrap straddles, so the check is
        inconclusive and near the line, and a clause with it as a component reads inconclusive. Against 3.0 both lie
        wholly below: falsified."""
        block = pop.check(skewed_sample(), 2.6, "above")
        self.assertLess(block["upper"], 2.6)
        self.assertTrue(block["bootstrap"][0] < 2.6 <= block["bootstrap"][1])
        self.assertEqual((block["reading"], block["bootstrap_reading"]), ("falsified", "inconclusive"))
        self.assertEqual(pop.combined(block), "inconclusive")
        self.assertTrue(block["near_the_line"])
        self.assertEqual(pop.three_way([("x", pop.combined(block))])["reading"], "inconclusive")
        both = pop.check(skewed_sample(), 3.0, "above")
        self.assertEqual(pop.combined(both), "falsified")
        self.assertEqual(pop.combined(dict(reading="supported", bootstrap_reading="falsified")), "inconclusive")

    def test_owners_return_fires_only_when_both_intervals_are_below_zero(self):
        """Owners' W2 return less DeFi's savings rate is the skewed sample less 2.6 (t upper -0.130, bootstrap upper
        0.092): the t interval alone lies below zero, so V4 is not shown worse and nothing fires; less 3.0 both lie
        below zero and V4 fires."""
        savings = 1200 * m0_rates(0.044 / 12)[0]

        def v4(shift):
            jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in range(26)]
            for job, value in zip(jobs, skewed_sample()):
                job["arms"]["M1"]["owners"] = dict(net_pct=dict(W2=value - shift + savings))
            return pop.better_than_m0("M1", 0.044, jobs, W)

        straddles = v4(2.6)
        self.assertLess(straddles["V4"]["upper"], 0)
        self.assertEqual((straddles["V4"]["shown_worse"], straddles["shown_worse"]), (False, False))
        below = v4(3.0)
        self.assertEqual((below["V4"]["shown_worse"], below["shown_worse"]), (True, True))
        self.assertEqual(pop.worse_than_m0({}, below)["fired"], ["owners_return"])

    def test_saving_reads_the_unrounded_lower_bound(self):
        """Clause (b)'s saving: savings of m +/- 0.1 over 20 seeds have sd 0.10260 and 95% t half-width 0.04802; with m
        that half-width plus 0.00002 the lower bound is 0.00002, above zero, though stored as 0.0."""
        half = float(pop._t_quantile(0.975, 19)) * float(np.std([0.1, -0.1] * 10, ddof=1)) / np.sqrt(20)
        jobs = [synthetic_job(0.044, 0.6, 0.0, s, saving_m0=half + 2e-5, saving_s0=half + 2e-5) for s in SEEDS20]
        out = pop.clause_b("M1", jobs, synthetic_cell(0.044, 0.6, 0.0), 0.05)
        self.assertEqual(out["against_M0"]["lower"], 0.0)
        self.assertTrue(out["saving"])


class CashAdvanceBound(unittest.TestCase):
    """The cash-advance bound (decided 15 Nov 2026): clause (d) read a second time on the gains less the
    cash-advance fees and interest the person saves, and a cell in the region only if it passes both."""

    def read(self, bound=None, levels=(0.0, 0.005)):
        """One cell at r_out 4.4% and a0 0.05 at each level, 20 seeds, every group gaining $5 +/- 0.1 as built and
        ``bound`` +/- 0.1 under the bound (the gain itself when None); the cells by level and the map's readings."""
        cells = [synthetic_cell(0.044, 0.05, level) for level in levels]
        jobs = [synthetic_job(0.044, 0.05, level, s, bound=bound) for level in levels for s in SEEDS20]
        stats = pop.claim_statistics(cells, jobs, W)
        return {c["distress"]: c["M1"] for c in cells}, stats

    def test_a_cell_failing_under_the_bound_is_out_of_the_region(self):
        """As built every group gains $5 +/- 0.1, (d) supported; under the bound -$3 +/- 0.1, its t and bootstrap
        intervals wholly below -$2, so d_bound fails, falsified. The cell passes all as built and not all: out of the
        region at level 0 and at 0.5%, though it withstands 0.5% as built; its reading is falsified, decided by d_bound
        alone, and as built supported; holds somewhere is empty. Clauses (a) to (e) are the same blocks, number for
        number, as with no saving on cash advances."""
        cells, stats = self.read(bound=-3.0)
        claim = cells[0.0]["claim"]
        self.assertEqual((claim["d"]["status"], claim["d_bound"]["status"], claim["d_bound"]["reading"]),
                         ("pass", "fail", "falsified"))
        self.assertEqual((claim["all_as_built"], claim["all"], claim["all_bonferroni_as_built"],
                          claim["all_bonferroni"], claim["in_region"]), (True, False, True, False, False))
        self.assertEqual((claim["reading"], claim["reading_as_built"]), ("falsified", "supported"))
        self.assertEqual((claim["reading_bonferroni"], claim["reading_bonferroni_as_built"]),
                         ("falsified", "supported"))
        self.assertTrue(claim["decided_by"] and all(name.startswith("(d_bound).") for name in claim["decided_by"]))
        self.assertIn(f"(d_bound).S0_face.{pop.CLASSES[0]}", claim["decided_by"])
        self.assertEqual(claim["decided_by_as_built"], [])
        self.assertAlmostEqual(claim["d_bound"]["at_95"]["lowest"]["mean"], -3.0, places=6)
        self.assertTrue(cells[0.005]["stress_leg"]["withstands"])
        self.assertEqual(claim["e"]["highest_level"], 0.005)
        self.assertEqual([stats["regions"]["M1"][k]["region"] for k in (0, 1)], [[], []])
        self.assertNotIn("in_region", cells[0.005]["stress_leg"])
        self.assertEqual(stats["holds_somewhere"]["M1"], [])
        plain, _ = self.read()
        for name in "abcde":
            self.assertEqual(claim[name], plain[0.0]["claim"][name], name)

    def test_a_cell_passing_both_is_in_the_region(self):
        """Under the bound every group gains $4 +/- 0.1: d_bound passes, supported, all and all_bonferroni hold, and
        the cell is in the region at level 0 and at 0.5%. With no saving, d_bound is (d) itself, number for number."""
        cells, stats = self.read(bound=4.0)
        claim = cells[0.0]["claim"]
        self.assertEqual((claim["d_bound"]["status"], claim["d_bound"]["reading"], claim["all"],
                          claim["all_bonferroni"], claim["in_region"], claim["reading"]),
                         ("pass", "supported", True, True, True, "supported"))
        self.assertEqual([stats["regions"]["M1"][k]["region"] for k in (0, 1)], [[[0.044, 0.05]], [[0.044, 0.05]]])
        same, _ = self.read()
        self.assertEqual(same[0.0]["claim"]["d_bound"], same[0.0]["claim"]["d"])

    def test_the_cell_takes_the_worse_reading_of_the_two(self):
        """Under the bound every group gains -$2 +/- 0.1, straddling the margin: d_bound inconclusive, so the cell
        reads inconclusive though (d) as built is supported."""
        cells, _ = self.read(bound=-2.0, levels=(0.0,))
        claim = cells[0.0]["claim"]
        self.assertEqual((claim["d"]["reading"], claim["d_bound"]["reading"], claim["reading"],
                          claim["reading_as_built"], claim["all"]), ("supported", "inconclusive", "inconclusive",
                                                                     "supported", False))

    def test_a_store_without_the_bound_does_not_pass_it(self):
        """Jobs stored before the bound hold no gains under it: every required group is undefined there (3 readings x
        11 groups), so d_bound does not hold, while (d) as built still holds."""
        jobs = [synthetic_job(0.044, 0.6, 0.0, s) for s in SEEDS20]
        for job in jobs:
            for other in ("S0", "M0"):
                for end in ("face", "zero"):
                    del job["arms"]["M1"]["against"][other]["complete_gain"][end]["bound"]
        bound = pop.clause_d_bound("M1", jobs, None, 0.05)
        self.assertFalse(bound["holds"])
        self.assertEqual(len(bound["undefined_groups"]), 33)
        self.assertTrue(pop.clause_d("M1", jobs, None, 0.05)["holds"])


class StressSweep(unittest.TestCase):
    def test_the_stress_sweep_is_the_catalogue_of_the_old_product(self):
        """The stress runner's jobs and summary keys come from PySPG's catalogue in the same order as the
        ``itertools.product`` they replaced (the last dimension fastest): 4 stresses x 2 arms x 3 seeds = 24 jobs.
        Nothing is simulated."""
        from itertools import product
        from scripts import run_economy_stress as stress
        self.assertEqual(stress.jobs(100), [(st, arm, seed, 100) for st, arm, seed
                                            in product(stress.STRESSES, stress.ARMS, stress.SEEDS)])
        self.assertEqual(len(stress.jobs(100)), 24)
        self.assertEqual(stress.summary_keys(), list(product(stress.ARMS, stress.STRESSES)))


if __name__ == "__main__":
    unittest.main()

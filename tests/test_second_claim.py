"""The claim of the second run, in the code that reads runs: small synthetic examples, no population run.

What is covered
---------------
* Clause (d), no group is harmed, in a run that conserves money: each group's own failed payments, the arm less S0 and
  less M0, upper bound at or below one failed payment a person a year on the t interval and the bootstrap, in both
  windows. A difference of 0.5 in every seed is supported, 1.5 is falsified, a spread across the margin is
  inconclusive; holding in one window and failing in the other fails; a group defined in one seed fails and is named.
* What a cell passes on there: (a), (b) and (d), with the first run's clause (d) stored beside and read by no
  verdict; the region reading's group test and its label; the table of who pays and who receives.
* The per-person record each row stores (``gains.failed_by_group``) on an example: failed shares of bills and wages
  and declined shares of card-eligible purchases, each apart and their sum, which the clause reads.
* The stricter level counts the run's own cells: 42 and 35 in the second run, 21 and 14 in the first.
* The second run's confirmation block, its rounding rule and the refusal while its count is not set.
* The note of a second-run store and of a first-run one; the side set owners_nothing.
"""
import contextlib
from copy import deepcopy
import io
from itertools import product
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

from scripts import run_economy_population as runner   # puts src and scripts on the path, as the other tests do
from cpm_abm.economy_abm import Economy
from run_economy_figures import DOLLARS
from cpm_abm.experiment import grid, second_run
from cpm_abm.experiment.claims import CLAUSES, _region_slice, claim_note, claim_statistics, clause_d_harm, clauses_of
from cpm_abm.experiment import claims
from cpm_abm.experiment.accounts import pool_payable
from cpm_abm.experiment.gains import defi_credit, failed_by_group, payout_by_group, rail_apart, real_saving_by_window
from cpm_abm.experiment.notes import (CLAIM_NOTE, FAILED_GROUPS_NOTE, REGION_NOTE, REGION_NOTE_CONSERVED, VERDICTS,
                                      VERDICTS_CONSERVED, WHO_PAYS_NOTE, MONEY_CHANGE_NOTE, conserves_money,
                                      verdicts_of)
from cpm_abm.experiment.region import groups_harmed, money_change_at_zero_end, region, who_pays
from cpm_abm.experiment.statistics import (bonferroni_alpha, bonferroni_cells, bootstrap_bounds, bootstrap_draws,
                                           least_passing, resampled, wilson_bounds)
from cpm_abm.experiment.store import write_stores
from scripts import run_confirmation as driver
from tests.test_claim_statistics import SEEDS20, synthetic_cell, synthetic_job
from tests.test_second_run import available

ROOT = Path(__file__).resolve().parents[1]
CONSERVED = Economy(n=40, edge="conserved")          # the first run's lengths, so W2 alone unless a row names windows
# The second run's base, quote reading, with the settings the Economy has (``test_second_run.available``): these
# readers look at its lengths, its edge, its stress year and its DeFi only.
SECOND = Economy(n=40, **available())
TWO = ["years_6_to_10", "years_21_to_25"]


def harm(job, by_window, arm="M1"):
    """``job`` with the arm's row storing each window's differences against S0 and M0 (``failed_by_group``):
    ``by_window`` maps a window to the difference every group has in it, or to a dict by kind of lists; the row then
    reads its windows from that order. Returns the job."""
    row = job["arms"][arm]
    sizes = dict(zip(("class", "quintile", "cycle"), (4, 5, 2)))
    lists = lambda value: value if isinstance(value, dict) else {name: [value] * size for name, size in sizes.items()}
    row["failed_by_group"] = dict(windows=list(by_window), by_window={
        window: dict(against_S0=lists(value), against_M0=lists(value)) for window, value in by_window.items()})
    if list(by_window) != ["W2"]:
        row["windows"] = list(by_window)
    return job


def jobs_with(values, windows=("W2",)):
    """Twenty synthetic jobs at one cell whose M1 row's group differences are ``values(seed)`` in every window (a
    number) or ``values(seed, window)`` where it takes two arguments."""
    two = values.__code__.co_argcount == 2
    return [harm(synthetic_job(0.044, 0.05, 0.0, s),
                 {window: values(s, window) if two else values(s) for window in windows}) for s in SEEDS20]


class SignedClauseD(unittest.TestCase):
    """``clause_d_harm`` on twenty seeds at the 95% level."""

    def read(self, values, windows=("W2",)):
        return clause_d_harm("M1", jobs_with(values, windows), synthetic_cell(0.044, 0.05, 0.0), 0.05)

    def test_half_a_failed_payment_more_is_supported(self):
        """Every group 0.5 more failed payments a year than S0 and M0 (0.4 and 0.6 in turn): mean 0.5, sd 0.1026, t
        upper bound 0.5 + 2.093 x 0.1026 / sqrt(20) = 0.548, at or below 1, and the bootstrap within 0.4 to 0.6:
        supported, in 11 groups x 2 yardsticks, 22 checks in one window."""
        d = self.read(lambda s: 0.5 + (0.1 if s % 2 else -0.1))
        self.assertTrue(d["holds"])
        self.assertEqual(d["reading"], "supported")
        self.assertEqual(sorted(d["passes"]), ["M0_W2", "S0_W2"])
        self.assertEqual(sum(map(len, d["groups"].values())), 22)
        self.assertAlmostEqual(d["highest"]["upper"], 0.548, places=3)
        self.assertEqual(d["undefined_groups"], [])

    def test_one_and_a_half_is_falsified(self):
        """1.5 more in every seed (1.4 and 1.6): both intervals lie wholly above 1, falsified, every check named."""
        d = self.read(lambda s: 1.5 + (0.1 if s % 2 else -0.1))
        self.assertFalse(d["holds"])
        self.assertEqual(d["reading"], "falsified")
        self.assertEqual(len(d["decided_by"]), 22)

    def test_a_spread_across_the_margin_is_inconclusive(self):
        """0 and 2 in turn: mean 1, the t interval 1 -/+ 0.48 straddles the margin, so the clause is inconclusive and
        does not hold."""
        d = self.read(lambda s: 2.0 if s % 2 else 0.0)
        self.assertFalse(d["holds"])
        self.assertEqual(d["reading"], "inconclusive")

    def test_holding_in_one_window_and_failing_in_the_other_fails(self):
        """0.5 in years 6 to 10 and 1.5 in years 21 to 25: 44 checks, those of the first window pass and those of the
        second do not, so the clause fails on the second window, whose highest bound is stored."""
        d = self.read(lambda s, window: (0.5 if window == TWO[0] else 1.5) + (0.1 if s % 2 else -0.1), TWO)
        self.assertEqual(sum(map(len, d["groups"].values())), 44)
        self.assertEqual(d["passes"], {"S0_years_6_to_10": True, "M0_years_6_to_10": True,
                                       "S0_years_21_to_25": False, "M0_years_21_to_25": False})
        self.assertFalse(d["holds"])
        self.assertTrue(all("years_21_to_25" in name for name in d["decided_by"]))
        self.assertEqual(d["highest"]["window"], "years_21_to_25")
        self.assertEqual(d["windows"], TWO)

    def test_a_group_defined_in_one_seed_fails_and_is_named(self):
        """The richest quintile has a value in the first seed only: no interval, so it does not support the clause and
        is named against both yardsticks; every other group is supported."""
        def values(s):
            groups = dict(**{"class": [0.5] * 4}, quintile=[0.5] * 4 + [0.5 if s == 0 else None], cycle=[0.5] * 2)
            return groups
        d = self.read(values)
        self.assertFalse(d["holds"])
        named = {(entry["group"], entry["against"], entry["seeds"]) for entry in d["undefined_groups"]}
        self.assertEqual(named, {("launch-wealth quintile 5", "S0", 1), ("launch-wealth quintile 5", "M0", 1)})
        self.assertIsNone(d["highest"]["upper"])     # a group with no interval counts highest
        self.assertEqual(d["highest"]["group"], "launch-wealth quintile 5")

    def test_one_seed_without_the_record_fails(self):
        """Nineteen seeds supporting the clause and one whose row stores no failed_by_group: the clause does not hold,
        reads inconclusive and names the seed; one lacking a window fails the same way."""
        jobs = jobs_with(lambda s: 0.5 + (0.1 if s % 2 else -0.1))
        del jobs[-1]["arms"]["M1"]["failed_by_group"]
        d = clause_d_harm("M1", jobs, synthetic_cell(0.044, 0.05, 0.0), 0.05)
        self.assertFalse(d["holds"])
        self.assertEqual(d["reading"], "inconclusive")
        self.assertEqual(d["seeds_without_record"], [SEEDS20[-1]])
        jobs = jobs_with(lambda s, window: 0.5 + (0.1 if s % 2 else -0.1), TWO)
        del jobs[0]["arms"]["M1"]["failed_by_group"]["by_window"][TWO[1]]
        self.assertFalse(clause_d_harm("M1", jobs, synthetic_cell(0.044, 0.05, 0.0), 0.05)["holds"])

    def test_a_row_that_stores_nothing_does_not_pass(self):
        """A seed without the record has every group undefined: the clause does not hold."""
        jobs = [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20]
        d = clause_d_harm("M1", jobs, synthetic_cell(0.044, 0.05, 0.0), 0.05)
        self.assertFalse(d["holds"])
        self.assertEqual(len(d["undefined_groups"]), 22)


class WhatACellPassesOn(unittest.TestCase):
    """``claim_statistics`` in a run that conserves money."""

    def cells_and_jobs(self, difference, gain=5.0):
        cells = [synthetic_cell(0.044, 0.05, 0.0)]
        jobs = [harm(synthetic_job(0.044, 0.05, 0.0, s, gain=gain), {"W2": difference + (0.1 if s % 2 else -0.1)})
                for s in SEEDS20]
        jobs = [harm(job, {"W2": difference + (0.1 if job["seed"] % 2 else -0.1)}, arm="M2") for job in jobs]
        return cells, jobs

    def test_a_cell_passes_on_a_b_and_d_as_signed(self):
        """Every group fails half a payment a year more, and every group's complete gain is -$50, far below the -$2 of
        the first run's clause: the cell passes on (a), (b) and (d), is in the region and holds somewhere; the first
        run's clause and the bound clause are stored, both failing, and read by no verdict; there is no d_bound key."""
        cells, jobs = self.cells_and_jobs(0.5, gain=-50.0)
        stats = claim_statistics(cells, jobs, CONSERVED)
        block = cells[0]["M1"]["claim"]
        self.assertEqual([block[name]["status"] for name in "abd"], ["pass"] * 3)
        self.assertEqual((block["d_as_first_registered"]["status"], block["d_bound_as_first_registered"]["status"]),
                         ("fail", "fail"))
        self.assertNotIn("d_bound", block)
        self.assertNotIn("all_as_built", block)
        self.assertTrue(block["all"] and block["all_bonferroni"] and block["in_region"])
        self.assertEqual(block["reading"], "supported")
        self.assertEqual(stats["regions"]["M1"][0]["region"], [[0.044, 0.05]])
        self.assertEqual(stats["holds_somewhere"]["M1"], [[0.044, 0.05]])
        self.assertIn("highest", block["d"]["at_95"])

    def test_a_harmed_group_fails_the_cell(self):
        """1.5 more failed payments a year in every group: (d) fails, so all fails, the cell is out of the region and
        its reading is falsified by (d)'s checks."""
        cells, jobs = self.cells_and_jobs(1.5)
        stats = claim_statistics(cells, jobs, CONSERVED)
        block = cells[0]["M1"]["claim"]
        self.assertEqual(block["d"]["status"], "fail")
        self.assertFalse(block["all"] or block["in_region"])
        self.assertEqual(block["reading"], "falsified")
        self.assertTrue(all(name.startswith("(d).") for name in block["decided_by"]))
        self.assertEqual(stats["regions"]["M1"][0]["region"], [])

    def test_the_map_shows_both_regions(self):
        """Each group 0.6 more failed payments a year, spread 0.6 across seeds: the t upper bound is 0.88 at 95% and
        above 1 at M1's stricter level, so the cell is in the pointwise region and not in the stricter one; each slice
        says what it reads. A first-run store has no stricter region."""
        cells = [synthetic_cell(0.044, 0.05, 0.0)]
        jobs = [harm(synthetic_job(0.044, 0.05, 0.0, s), {"W2": 0.6 + (0.6 if s % 2 else -0.6)}) for s in SEEDS20]
        stats = claim_statistics(cells, jobs, CONSERVED)
        block = cells[0]["M1"]["claim"]
        self.assertTrue(block["all"] and block["in_region"])
        self.assertFalse(block["all_bonferroni"] or block["in_region_bonferroni"])
        self.assertEqual(stats["regions"]["M1"][0]["region"], [[0.044, 0.05]])
        self.assertEqual(stats["regions_bonferroni"]["M1"][0]["region"], [])
        self.assertIn("pointwise", stats["regions"]["M1"][0]["reads"])
        self.assertIn("stricter", stats["regions_bonferroni"]["M1"][0]["reads"])
        released = claim_statistics([synthetic_cell(0.044, 0.05, 0.0)],
                                    [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20], Economy(n=40))
        self.assertNotIn("regions_bonferroni", released)
        self.assertNotIn("reads", released["regions"]["M1"][0])

    def test_a_stressed_cell_needs_its_base_cell_powered(self):
        """A stressed slice's cell whose no-distress cell passes and withstands the level but is underpowered is out
        of both regions in the second run, and in the region of the first run."""
        base = dict(all=True, all_bonferroni=True, underpowered=True, e=dict(highest_level=0.02))
        leg = dict(underpowered=False)
        mine = {(0.044, 0.05, 0.0): {"M1": dict(claim=base)}, (0.044, 0.05, 0.02): {"M1": dict(stress_leg=leg)}}
        stressed = {k: v for k, v in mine.items() if k[2] == 0.02}
        self.assertEqual(_region_slice("M1", 0.02, stressed, mine, CONSERVED)["region"], [])
        self.assertEqual(_region_slice("M1", 0.02, stressed, mine, CONSERVED, strict=True)["region"], [])
        self.assertEqual(_region_slice("M1", 0.02, stressed, mine)["region"], [[0.044, 0.05]])

    def test_released_runs_keep_their_clauses(self):
        """With the edge open (the first run), (d) is the complete gain's clause and the block keeps d_bound and its
        readings; the Economy without an edge reads the same."""
        self.assertIs(clauses_of(Economy(n=40)), CLAUSES)
        self.assertIs(clauses_of(None), CLAUSES)
        self.assertIs(clauses_of(CONSERVED)["d"], clause_d_harm)
        cells = [synthetic_cell(0.044, 0.05, 0.0)]
        claim_statistics(cells, [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20], Economy(n=40))
        block = cells[0]["M1"]["claim"]
        self.assertIn("d_bound", block)
        self.assertIn("all_as_built", block)
        self.assertNotIn("d_as_first_registered", block)

    def test_the_declared_limit_names_the_clauses_as_first_registered(self):
        """M2 at 2% is its declared limit in a run that conserves money too, with the first-registered names."""
        cells = [synthetic_cell(0.02, 0.05, 0.0)]
        jobs = [harm(harm(synthetic_job(0.02, 0.05, 0.0, s), {"W2": 0.5}), {"W2": 0.5}, "M2") for s in SEEDS20]
        claim_statistics(cells, jobs, CONSERVED)
        limit = cells[0]["M2"]["claim"]
        self.assertEqual(limit["reading"], "declared limit")
        self.assertIn("d_bound_as_first_registered", limit)
        self.assertNotIn("d_bound", limit)


def region_rows(difference, seeds=20):
    """Pool-arm rows as ``region`` reads them, the pool formed in every seed, the issuer staying, every group's complete
    gain $5 against both yardsticks, and each group's failed payments ``difference`` (plus or minus 0.1) more."""
    groups = lambda value: dict(gain_usd_a_year=value, **{f"gain_usd_a_year_by_{name}": [value] * size
                                                          for name, size in (("class", 4), ("quintile", 5),
                                                                             ("cycle", 2))})
    against = lambda: dict(groups(5.0), complete_gain=dict(face=dict(groups(5.0), bound=groups(5.0)),
                                                           zero=dict(groups(-1.5), bound=groups(-1.5))))
    rows = [dict(pool_formed=True, X=dict(X6=False), against=dict(S0=against(), M0=against())) for _ in range(seeds)]
    return [harm(dict(arms=dict(M1=row)), {"W2": difference + (0.1 if k % 2 else -0.1)})["arms"]["M1"]
            for k, row in enumerate(rows)]


class RegionView(unittest.TestCase):
    """The persistence-and-groups reading beside the claim."""

    def test_the_group_test_is_the_signed_clause_on_t_upper_bounds(self):
        """In a run that conserves money: half a payment more reads stable; 1.5 more reads "a group is harmed", in
        place of the complete gain's clause, which holds and is still stored; under the bound the same test."""
        stable = region("M1", 0.044, region_rows(0.5), [True] * 20, CONSERVED)
        self.assertEqual(stable["verdict"], "stable")
        self.assertTrue(stable["groups_harmed"]["clause_holds"])
        self.assertAlmostEqual(stable["groups_harmed"]["highest"]["upper_95"], 0.548, places=3)
        harmed = region("M1", 0.044, region_rows(1.5), [True] * 20, CONSERVED)
        self.assertEqual((harmed["verdict"], harmed["verdict_bound"], harmed["in_region_both"]),
                         ("a group is harmed", "a group is harmed", False))
        self.assertTrue(harmed["complete_gain"]["clause_holds"])
        self.assertEqual(verdicts_of(CONSERVED), VERDICTS_CONSERVED)

    def test_released_stores_keep_a_group_loses(self):
        """In the first run the group test is the complete gain's, named "a group loses", and nothing new is stored."""
        rows = region_rows(1.5)
        lost = deepcopy(rows)
        for row in lost:
            row["against"]["S0"]["complete_gain"]["face"]["gain_usd_a_year_by_class"] = [-50.0] * 4
        reading = region("M1", 0.044, lost, [True] * 20, Economy(n=40))
        self.assertEqual(reading["verdict"], "a group loses")
        self.assertNotIn("groups_harmed", reading)
        self.assertEqual(region("M1", 0.044, rows, [True] * 20, Economy(n=40))["verdict"], "stable")
        self.assertEqual(verdicts_of(Economy(n=40)), VERDICTS)

    def test_a_window_missing_does_not_pass(self):
        """Every group half a payment more, but one seed's row lacks the record: the region's group test does not pass
        and counts the seed."""
        rows = region_rows(0.5)
        del rows[3]["failed_by_group"]
        found = groups_harmed(rows)
        self.assertFalse(found["clause_holds"])
        self.assertEqual(found["seeds_without_record"], 1)
        self.assertTrue(groups_harmed(region_rows(0.5))["clause_holds"])

    def test_two_seeds_hand_case(self):
        """0.4 and 0.6 in two seeds: mean 0.5, upper bound 0.5 + 12.706 x 0.1414 / sqrt(2) = 1.77: harmed."""
        found = groups_harmed(region_rows(0.5, seeds=2))
        self.assertAlmostEqual(found["highest"]["upper_95"], 1.7706, places=3)
        self.assertFalse(found["clause_holds"])

    def test_who_pays_who_receives(self):
        """From the payout itself where every seed stores it: the seed means of what each group received, paid across
        the edge and the difference; where no seed stores it, "not stored". The zero end's table stays beside under
        its own name, with its note."""
        rows = region_rows(0.5)
        self.assertEqual(who_pays(rows), dict(note=WHO_PAYS_NOTE, payout="not stored"))
        table = lambda value: dict(everyone=value, **{"class": [value] * 4}, quintile=[value] * 5, cycle=[value] * 2)
        for k, row in enumerate(rows):
            row["payout_by_group"] = dict(received=table(120.0 + k), paid_across_edge=table(48.0),
                                          returned_usd_a_year=120.0 + k, reconciled_gap_usd_a_year=0.0)
        found = who_pays(rows)
        self.assertEqual(found["received"]["quintile"], [129.5] * 5)
        self.assertEqual(found["paid_across_edge"]["everyone"], 48.0)
        self.assertEqual(found["seeds"], 20)
        zero = money_change_at_zero_end(rows)
        self.assertEqual(zero["note"], MONEY_CHANGE_NOTE)
        self.assertEqual(zero["against_S0"]["quintile"], [-1.5] * 5)
        self.assertEqual(zero["against_M0"]["everyone"], -1.5)

    def test_the_payout_by_group_hand_case(self):
        """Four people over the first run's 60 months after launch: person 0 receives 10 a month from the payout and
        pays 4 a month across the edge, in dollars, everyone else nothing. Person 0 receives $120 a year, pays $48 and
        is $72 ahead; its quintile (the poorest) reads the same, everyone a quarter of it. The stored total returned
        reconciles with the payout's mean, and the closure for everyone holds: the payout's $30 a person is the $12
        paid across the edge, $8 more that crossed it ($20 out in all as booked), $6 of inflation and $4 of the stock
        paid down, with nothing kept. No difference by group is stored. A run without the payout says so."""
        w = Economy(n=4, edge="conserved", payout="paid")
        months = w.burn_in + w.months
        people = dict(holder=np.zeros(4, bool), business=np.zeros(4, bool), cycles=np.array([5, 5, 30, 30]))
        wealth = np.tile(np.array([1.0, 2.0, 3.0, 4.0]), (months + 1, 1))
        payout, paid = np.zeros((months, 4)), np.zeros((months, 4))
        payout[w.burn_in:, 0], paid[w.burn_in:, 0] = 10.0 / DOLLARS, 4.0 / DOLLARS
        returned = payout.mean(axis=1)
        months_after = w.months
        external = np.zeros(months)
        external[w.burn_in:] = -20.0 / 12 / DOLLARS                  # $20 a year a person out across the edge
        inflation = np.zeros(months)
        inflation[w.burn_in:] = -6.0 / 12 / DOLLARS                  # $6 a year lost to inflation
        owed = np.zeros(months)
        owed[w.burn_in - 1] = 4.0 * months_after / 12 / DOLLARS      # the stock paid down by $4 a year
        series = dict(returned=returned, external=external, inflation=inflation, edge_owed=owed,
                      edge_kept=np.zeros(months))
        arm = dict(arm="M1", economy=w, payout=payout, transfers=paid, series=series)
        s0 = dict(arm="S0", population=people, wealth=wealth)
        found = payout_by_group(arm, s0, w)
        self.assertAlmostEqual(found["received"]["quintile"][0], 120.0)
        self.assertAlmostEqual(found["paid_across_edge"]["quintile"][0], 48.0)
        self.assertNotIn("net", found)
        closure = found["closure_everyone"]
        self.assertAlmostEqual(closure["received"], 30.0)
        self.assertAlmostEqual(closure["paid_across_edge"], 12.0)
        self.assertAlmostEqual(closure["other_across_edge"], 8.0)
        self.assertAlmostEqual(closure["inflation"], 6.0)
        self.assertAlmostEqual(closure["stock_change"], 4.0)
        self.assertAlmostEqual(closure["gap"], 0.0)
        self.assertAlmostEqual(found["returned_usd_a_year"], 30.0)
        self.assertAlmostEqual(found["reconciled_gap_usd_a_year"], 0.0)
        without = {key: value for key, value in arm.items() if key != "payout"}
        self.assertEqual(payout_by_group(without, s0, w), "not stored")


class PerPersonRecord(unittest.TestCase):
    def test_failed_by_group_hand_case(self):
        """Four people over the first run's W2 (months 37 to 60 after launch, 24 months): the arm fails 0.1 a month for
        person 0 and nothing for the rest, S0 0.05 for person 0, M0 nothing; person 0 also has 0.05 declined shares a
        month under the arm and under S0 and none under M0. Person 0 fails 0.1 x 24 / 2 = 1.2 a year under the arm and
        0.6 under S0, and has 0.6 declined under both, so its group (the poorest quintile, short cycle, no card and
        wage income) is 0.6 above S0 and 1.2 above M0 on failed shares, 0 and 0.6 on declined shares, and 0.6 and 1.8
        on their sum, which the clause reads. A month outside W2 does not count."""
        w = Economy(n=4, edge="conserved")
        months = w.burn_in + w.months
        people = dict(holder=np.zeros(4, bool), business=np.zeros(4, bool), cycles=np.array([5, 5, 30, 30]))
        wealth = np.tile(np.array([1.0, 2.0, 3.0, 4.0]), (months + 1, 1))

        def run(name, rate, declined_rate):
            shares, declined = np.zeros((months, 4)), np.zeros((months, 4))
            shares[w.burn_in + 36:w.burn_in + 60, 0] = rate
            declined[w.burn_in + 36:w.burn_in + 60, 0] = declined_rate
            shares[w.burn_in + 5, 1] = declined[w.burn_in + 5, 1] = 9.0     # outside the window
            return dict(arm=name, economy=w, population=people, wealth=wealth,
                        failure_counts=dict(fail_shares=shares, declined_shares=declined))
        arm, s0, m0 = run("M1", 0.1, 0.05), run("S0", 0.05, 0.05), run("M0", 0.0, 0.0)
        kept = dict(s0, **s0["failure_counts"])                  # S0 as a job keeps it for the later arms
        found = failed_by_group(arm, kept, m0, w)
        self.assertEqual(found["windows"], ["W2"])
        window = found["by_window"]["W2"]
        self.assertAlmostEqual(window["failed"]["level"]["class"][0], 0.3)   # 1.2 over the four people of the class
        self.assertAlmostEqual(window["failed"]["against_S0"]["quintile"][0], 0.6)
        self.assertAlmostEqual(window["failed"]["against_M0"]["quintile"][0], 1.2)
        self.assertAlmostEqual(window["failed"]["S0"]["cycle"][0], 0.3)     # 0.6 over the two short-cycle people
        self.assertAlmostEqual(window["declined"]["against_S0"]["quintile"][0], 0.0)
        self.assertAlmostEqual(window["declined"]["against_M0"]["quintile"][0], 0.6)
        self.assertAlmostEqual(window["level"]["class"][0], 0.45)           # 1.8 over the four people
        self.assertAlmostEqual(window["against_S0"]["quintile"][0], 0.6)
        self.assertAlmostEqual(window["against_M0"]["quintile"][0], 1.8)
        self.assertTrue(np.isnan(window["level"]["class"][3]))            # no card holder with business income
        self.assertNotIn("against_M0", failed_by_group(m0, kept, m0, w)["by_window"]["W2"])
        self.assertNotIn("against_M0", failed_by_group(m0, kept, m0, w)["by_window"]["W2"]["declined"])


class StricterLevel(unittest.TestCase):
    def test_the_run_counts_its_own_cells(self):
        """Six registered rates in the second run: 42 cells for M1 and 35 for M2 (its 2% cells are its declared limit),
        levels 0.05 / 42 = 0.001190 and 0.05 / 35 = 0.001429; in the first run 21 and 14."""
        self.assertEqual((bonferroni_cells("M1", SECOND), bonferroni_cells("M2", SECOND)), (42, 35))
        self.assertAlmostEqual(bonferroni_alpha("M1", SECOND), 0.001190, places=6)
        self.assertAlmostEqual(bonferroni_alpha("M2", SECOND), 0.001429, places=6)
        self.assertEqual((bonferroni_cells("M1", Economy()), bonferroni_cells("M2", Economy())), (21, 14))


class DefiLabels(unittest.TestCase):
    def test_m0_is_named_by_the_store(self):
        """A store of the second run names M0 DeFi (stablecoin payments) on its figures and card; a first-run store,
        whose economy has none of the second run's settings or predates them, keeps best-case DeFi."""
        from scripts import paper_numbers as pn
        second = dict(economy=dict(edge="conserved"))
        self.assertTrue(pn.second_run_store(second))
        self.assertFalse(pn.second_run_store(dict(economy=dict(edge="open", distress_purchases=0.0))))
        self.assertFalse(pn.second_run_store(dict(economy={})))
        self.assertEqual(pn.defi_named("CPM over best-case DeFi, money", second),
                         "CPM over DeFi (stablecoin payments), money")
        self.assertEqual(pn.defi_named("Best-case DeFi", dict(economy={})), "Best-case DeFi")


class RealCostByWindow(unittest.TestCase):
    def test_the_rail_apart(self):
        """A total saving of 5.00 with card rails 4.00 and the P rail -0.50: 3.50 on the rail and 1.50 on the rest."""
        self.assertEqual(rail_apart(dict(card_rails=4.0, p_rail=-0.5, total=5.0)), dict(rail=3.5, other=1.5, total=5.0))

    def test_the_saving_in_each_window(self):
        """Two arms over 132 months, windows years 1 to 5 and 7 to 11: S0 pays the card rails on 10 card payments of
        value 1.0 a month in the first window only, the arm nothing. The arm saves the rails' cost on the first window
        and nothing on the second, all of it on the rail; the whole run's saving is handed in."""
        w = Economy(n=4, burn_in=0, months=132, distress_start=60, edge="conserved")
        keys = ("pt_card", "pt_pool_card_credit", "pt_pool_nocard_card", "pt_pool_term", "pt_term", "fail_shares",
                "bridged_shares", "card_payments", "card_value", "gas", "money_bt", "savings_bt", "shares_bt",
                "ewa_uses", "penalties", "nocard_bridges", "pt_pool_card", "pool_operating", "fail_items",
                "bridged_items", "bridged_card")
        series = lambda: {key: np.zeros(132) for key in keys}
        arm, s0 = dict(arm="M1", economy=w, series=series()), dict(arm="S0", economy=w, series=series())
        s0["series"]["card_payments"][:60], s0["series"]["card_value"][:60] = 10.0, 1.0
        whole = dict(card_rails=1.0, p_rail=0.0, total=1.0)
        found = real_saving_by_window(arm, s0, w, whole)
        first = found["real_saving_by_window_usd_a_year"]["years_1_to_5"]
        self.assertGreater(first["card_rails"], 0)
        self.assertEqual(first["total"], first["card_rails"])
        self.assertEqual(found["real_saving_by_window_usd_a_year"]["years_7_to_11"]["total"], 0.0)
        self.assertEqual(found["real_saving_rail_apart_usd_a_year"]["years_1_to_5"]["other"], 0.0)
        self.assertEqual(found["real_saving_rail_apart_usd_a_year"]["whole_run"], dict(rail=1.0, other=0.0, total=1.0))

    def test_clause_b_reads_each_window_beside(self):
        """Rows that store the saving by window: clause (b) keeps its verdict on the whole run and stores each window's
        check and the rail apart; the late window's saving below the margin shows there and changes nothing. Rows
        without it store neither."""
        jobs = [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20]
        lines = lambda total: dict(card_rails=total, p_rail=0.0, total=total)
        for job, other in product(jobs, ("M0", "S0")):
            by = dict(W1=lines(10.0), W2=lines(-8.0 + 0.1 * (1 if job["seed"] % 2 else -1)))
            apart = dict(whole_run=rail_apart(lines(5.0)), W1=rail_apart(by["W1"]), W2=rail_apart(by["W2"]))
            job["arms"]["M1"]["against"][other] = dict(job["arms"]["M1"]["against"][other],
                                                       real_saving_by_window_usd_a_year=by,
                                                       real_saving_rail_apart_usd_a_year=apart)
        b = claims.clause_b("M1", jobs, None, 0.05)
        self.assertTrue(b["holds"])
        self.assertTrue(b["by_window"]["W1"]["against_M0"]["holds"])
        self.assertFalse(b["by_window"]["W2"]["against_S0"]["holds"])
        self.assertEqual(b["rail_apart"]["whole_run"]["against_M0"]["rail"]["mean"], 5.0)
        self.assertEqual(set(b["rail_apart"]), {"whole_run", "W1", "W2"})
        plain = claims.clause_b("M1", [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20], None, 0.05)
        self.assertNotIn("by_window", plain)


class DefiAsItIs(unittest.TestCase):
    def test_nobody_can_borrow(self):
        """DeFi's credit beside its results: no one holds collateral and Comet lends nothing, so both read zero; one
        holder and $0.10 a month of bridging over 60 months read 1 and $1.20 a year."""
        w = Economy(n=4, edge="conserved")
        months = w.burn_in + w.months
        run = dict(population=dict(crypto=np.zeros(4, bool)), series=dict(comet_bridging=np.zeros(months)))
        self.assertEqual(defi_credit(run, w), dict(people_able_to_borrow=0, borrowing_drawn_usd_a_year=0.0))
        run["population"]["crypto"][0] = True
        run["series"]["comet_bridging"][w.burn_in:] = 0.10 / DOLLARS
        self.assertEqual(defi_credit(run, w), dict(people_able_to_borrow=1, borrowing_drawn_usd_a_year=1.2))


class NoOutsideMoney(unittest.TestCase):
    def test_what_the_pool_owes_its_provider(self):
        """300 months after launch, years 6 to 10 the early window: $3 owed at the end of month 125, in the stress year,
        is read by the clause (one month owing); $2 owed in month 20, before the early window, is in after_launch
        alone; a month with no value is counted apart; the most owed within a month is reported where stored. A run
        without the series says it is not stored."""
        w = Economy(n=4, burn_in=0, months=300, distress_start=120, edge="conserved")
        owed, most = np.zeros(300), np.zeros(300)
        owed[124], owed[19], owed[200] = 3.0 / DOLLARS, 2.0 / DOLLARS, np.nan
        most[150] = 7.0 / DOLLARS
        found = pool_payable(dict(economy=w, series=dict(pool_payable=owed, pool_payable_most=most)))
        self.assertEqual(found["months"], [61, 300])
        self.assertEqual(found["read_by_clause"], dict(most_usd=3.0, months_owing=1, months_undefined=1))
        self.assertEqual(found["after_launch"], dict(most_usd=3.0, months_owing=2, months_undefined=1))
        self.assertEqual(found["within_month"], dict(most_usd=7.0, months_owing=1, months_undefined=0))
        self.assertNotIn("within_month", pool_payable(dict(economy=w, series=dict(pool_payable=owed))))
        self.assertEqual(pool_payable(dict(economy=w, series={})), "not stored")

    def test_clause_a_asks_the_provider_is_owed_nothing(self):
        """Rows of a run of the second run: a pool that owed its provider nothing in every seed passes (a); one seed
        owing $3 at one month's end falsifies its no-outside-money part; a seed keeping no record, or with a month
        with no value, does not pass and is named; credit inside a month is reported and decides nothing. First-run
        rows read as before, with no provider part."""
        def read(records):
            jobs = [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20]
            for job, record in zip(jobs, records):
                job["arms"]["M1"] = dict(job["arms"]["M1"], pool_payable=record)
            return claims.clause_a("M1", jobs, synthetic_cell(0.044, 0.05, 0.0), 0.05)
        reading = lambda most, owing, undefined=0: dict(most_usd=most, months_owing=owing, months_undefined=undefined)
        record = lambda clause, within=reading(0.0, 0): dict(months=[61, 300], read_by_clause=clause,
                                                            after_launch=clause, within_month=within)
        nothing = record(reading(0.0, 0))
        clean = read([nothing] * 19 + [record(reading(0.0, 0), within=reading(7.0, 1))])
        self.assertTrue(clean["holds"])
        self.assertTrue(clean["provider"]["owes_nothing"])
        self.assertEqual((clean["provider"]["most_usd_within_month"], clean["provider"]["owing_within_month_seeds"]),
                         (7.0, 1))
        owing = read([nothing] * 19 + [record(reading(3.0, 1))])
        self.assertFalse(owing["holds"])
        self.assertEqual(owing["provider"]["owing_seeds"], 1)
        self.assertEqual(owing["reading"], "falsified")
        self.assertIn("no_outside_money", owing["decided_by"])
        missing = read([nothing] * 19 + ["not stored"])
        self.assertFalse(missing["holds"])
        self.assertIn("1 seeds keep no record", missing["provider"]["reason"])
        blank = read([nothing] * 19 + [record(reading(0.0, 0, undefined=1))])
        self.assertFalse(blank["holds"])
        self.assertEqual(blank["provider"]["undefined_seeds"], 1)
        self.assertIn("no value", blank["provider"]["reason"])
        released = claims.clause_a("M1", [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20],
                                   synthetic_cell(0.044, 0.05, 0.0), 0.05)
        self.assertTrue(released["holds"])
        self.assertNotIn("provider", released)


class Resamples(unittest.TestCase):
    def test_the_second_run_draws_200000(self):
        """A run of the second run draws 200,000 resamples on the same stream, a first run 10,000; the count is in
        force only inside the reading and is restored after it. A clause's stored bootstrap in a run that conserves
        money is the 200,000-draw interval of its values."""
        self.assertEqual((bootstrap_draws(SECOND), bootstrap_draws(Economy())), (200_000, 10_000))
        values = [0.5 + (0.1 if s % 2 else -0.1) + 0.01 * k for k, s in enumerate(SEEDS20)]
        released = bootstrap_bounds(values, 0.05 / 42)
        with resampled(200_000):
            many = bootstrap_bounds(values, 0.05 / 42)
        self.assertEqual(bootstrap_bounds(values, 0.05 / 42), released)
        self.assertEqual(many, bootstrap_bounds(values, 0.05 / 42, draws=200_000))
        self.assertNotEqual(many, released)
        jobs = jobs_with(lambda s: values[SEEDS20.index(s)])
        cells = [synthetic_cell(0.044, 0.05, 0.0)]
        claim_statistics(cells, jobs, CONSERVED)
        stored = cells[0]["M1"]["claim"]["d"]["at_bonferroni"]["groups"]["S0_W2"]["no card and wage income"]
        alpha = bonferroni_alpha("M1", CONSERVED)
        self.assertEqual(stored["bootstrap"], [round(b, 4) for b in bootstrap_bounds(values, alpha, draws=200_000)])


class SecondSeeds(unittest.TestCase):
    def test_the_rounding_rule(self):
        """The larger of 30 and the count rounded up to the next ten: 8 gives 30, 26 gives 30, 30 gives 30, 33 gives 40,
        44 gives 50; at most 100; None stays None."""
        self.assertEqual([grid.second_confirmation_count(n) for n in (8, 1, 26, 30, 33, 44, 95, 120, None)],
                         [30, 30, 30, 30, 40, 50, 100, 100, None])

    def test_the_decisions_a_count_can_reach(self):
        """The fewest passing seeds for a Wilson lower bound above one half: 15 of 20 at 95%; at 10 seeds 9 at 95% and
        none at 0.05 / 42 (10 of 10 has lower bound 0.48768); at 30 seeds 21 and 24. The vector reading agrees with
        the Wilson bound at 47 seeds."""
        self.assertEqual(least_passing(20), 15)
        self.assertEqual((least_passing(10), least_passing(10, 0.05 / 42), least_passing(10, 0.05 / 35)),
                         (9, None, None))
        self.assertEqual((least_passing(30), least_passing(30, 0.05 / 42), least_passing(30, 0.05 / 35)), (21, 24, 24))
        self.assertAlmostEqual(wilson_bounds(10, 10, 0.05 / 42)[0], 0.48768, places=5)
        first = next((k for k in range(48) if wilson_bounds(k, 47, 0.05 / 42)[0] > 0.5), None)
        self.assertEqual(least_passing(47, 0.05 / 42), first)

    def test_the_block(self):
        """From 20261701, never run: 40 seeds are 20261701 to 20261740 and the extension the next 40; the block touches
        no other set, the first run's block included."""
        self.assertEqual(grid.second_confirmation_block(40), tuple(range(20261701, 20261741)))
        self.assertEqual(grid.second_confirmation_block(40, extended=True), tuple(range(20261741, 20261781)))
        self.assertEqual(grid.seeds_for("confirmation", 30, second=True), tuple(range(20261701, 20261731)))
        others = set(grid.CONFIRMATION_RESERVED).union(*map(set, grid.RETIRED_SEEDS),
                                                         *(set(v) for v in grid.SEEDS.values() if v))
        self.assertFalse(set(grid.SECOND_CONFIRMATION_RESERVED) & others)
        self.assertTrue(set(grid.second_confirmation_block(100, extended=True))
                        <= set(grid.SECOND_CONFIRMATION_RESERVED))
        for bad in (1, 101, 30.0, True, None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                grid.second_confirmation_block(bad)
        # Every other set is the first run's, second run or not.
        self.assertEqual(grid.seeds_for("development", second=True), grid.SEEDS["development"])
        self.assertEqual(grid.seeds_for("confirmation"), tuple(range(20261401, 20261431)))

    def test_refused_while_the_count_is_not_set(self):
        """SECOND_CONFIRMATION_COUNT is None until the three-seed map is read: the seeds, the runner and the driver
        refuse a confirmation run of the second run and say why; with a count set they run its block."""
        self.assertIsNone(grid.SECOND_CONFIRMATION_COUNT)
        with self.assertRaises(ValueError) as said:
            grid.seeds_for("confirmation", second=True)
        self.assertIn("three-seed map", str(said.exception))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            driver.plan("confirmation", ["--second-run", "base", "--entry-reads", "quote"])
        self.assertIn("second run's confirmation seed count is not set", err.getvalue())
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "never"
            err = io.StringIO()
            with mock.patch.object(sys, "argv", ["run_economy_population.py", "--seeds", "confirmation", "--second-run",
                                                 "base", "--output", str(target)]), \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                runner.main()
            self.assertIn("second run's confirmation seed count is not set", err.getvalue())
            self.assertFalse(target.exists())
        with mock.patch("cpm_abm.experiment.grid.SECOND_CONFIRMATION_COUNT", 40):
            _, parts = driver.plan("confirmation", ["--second-run", "base", "--entry-reads", "quote"])
            self.assertEqual([seed for seed, _ in parts], list(range(20261701, 20261741)))
        # Without --second-run the confirmation set is the first run's block.
        _, parts = driver.plan("confirmation", [])
        self.assertEqual(parts[0][0], 20261401)

    def test_the_planner_reports_the_rounded_count(self):
        """On a map of the second run the planner stores the registered count, the rounded count and the run's own
        count now (None); a first-run map stores neither."""
        cells = [synthetic_cell(0.044, 0.05, 0.0)]
        jobs = [harm(harm(synthetic_job(0.044, 0.05, 0.0, s), {"W2": 0.5}), {"W2": 0.5}, "M2") for s in SEEDS20]
        seeds = claim_statistics(cells, jobs, CONSERVED)["seeds"]
        self.assertEqual(seeds["second_run"]["rounded"], grid.second_confirmation_count(seeds["seeds_assured"]))
        self.assertEqual(seeds["second_run"]["first_seed"], 20261701)
        self.assertIsNone(seeds["confirmation_seeds_now"])
        attainable = seeds["second_run"]["attainable"]
        self.assertEqual(attainable["count"], seeds["second_run"]["rounded"])
        self.assertEqual(attainable["least_passing"]["95%"], least_passing(attainable["count"]))
        self.assertEqual(set(attainable["least_passing"]), {"95%", "M1", "M2"})
        freedom = seeds["second_run"]["by_seed_freedom"]
        cost = next(r for r in seeds["readings"] if r["reading"] == "cost against M0" and r["arm"] == "M1")
        self.assertEqual(cost["freedom_by_seed"], 19)                    # twenty seeds less one
        self.assertGreaterEqual(freedom["seeds_assured"] or 0, seeds["seeds_assured"] or 0)
        released = claim_statistics([synthetic_cell(0.044, 0.05, 0.0)],
                                    [synthetic_job(0.044, 0.05, 0.0, s) for s in SEEDS20], Economy(n=40))["seeds"]
        self.assertNotIn("second_run", released)
        self.assertFalse(any("freedom_by_seed" in r for r in released["readings"]))
        self.assertEqual(released["confirmation_seeds_now"], 30)


class StoreNotes(unittest.TestCase):
    def test_the_note_of_a_second_run_store(self):
        """The second run's note names both windows, (d), months 121 to 156, 42 and 35 cells, DeFi without yield and the
        seed rule, and nothing of the first run's dip months or cell counts."""
        note = claim_note(SECOND)
        for words in ("years 6 to 10 and years 21 to 25", "months 121 to 156 after launch", "0.05 over 42 cells",
                      "over 35 for M2", "pays its holder nothing", "no group is harmed", "44 checks",
                      "from 20261701 upward", "rounded up to the next ten", "d_as_first_registered",
                      "no yield and no credit", "meets the entry hurdle by construction",
                      "the realised record is the reading that tests whether savers stay"):
            self.assertIn(words, note)
        for words in ("months 25 to 60", "21 cells", "14 for M2", "best-case", "over-collateralised lending"):
            self.assertNotIn(words, note)
        reserve = claim_note(Economy(n=40, **available("defi_reserve_yield")))
        self.assertIn("reserve yield", reserve)
        self.assertEqual(claim_note(Economy()), CLAIM_NOTE)

    def test_the_stores_write_their_own_notes(self):
        """A store of a run that conserves money writes the second claim note, the region note and readings that
        name the second run's group test, and the rows' note; a first-run store writes the first run's notes word for
        word."""
        (ROOT / ".cache").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as top:
            for name, w in (("second", SECOND), ("released", Economy(n=40))):
                folder = Path(top) / name
                folder.mkdir()
                meta = dict(economy=dict(edge=w.edge))
                write_stores(folder, meta, [], [], None, dict(note=claim_note(w)))
                summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
                cells = json.loads((folder / "cells.json").read_text(encoding="utf-8"))
                if name == "second":
                    self.assertEqual(summary["claim_note"], claim_note(SECOND))
                    self.assertEqual((summary["region_note"], summary["verdicts"]),
                                     (REGION_NOTE_CONSERVED, list(VERDICTS_CONSERVED)))
                    self.assertEqual(cells["failed_by_group_note"], FAILED_GROUPS_NOTE)
                    self.assertEqual(set(cells["failure_crosswalk"]) - {"note"},
                                     {"bill", "first_due_wage", "requeued_wage", "wage_owed_outside",
                                      "card_eligible_purchase", "durable_needing_credit"})
                else:
                    self.assertEqual((summary["claim_note"], summary["region_note"], summary["verdicts"]),
                                     (CLAIM_NOTE, REGION_NOTE, list(VERDICTS)))
                    self.assertNotIn("failed_by_group_note", cells)
                    self.assertNotIn("failure_crosswalk", cells)
        self.assertTrue(conserves_money(SECOND) and not conserves_money(Economy()))


class OwnersNothing(unittest.TestCase):
    def test_the_side_set(self):
        """owners_share 0.0 on the cells and readings of owners_everything, so the table can be read at 0, 0.10 and
        1; 43 side sets in all."""
        self.assertEqual(second_run.SIDE_SETS["owners_nothing"], dict(owners_share=0.0))
        self.assertEqual(second_run.cells("owners_nothing"), second_run.cells("owners_everything"))
        self.assertEqual(second_run.reads("owners_nothing"), second_run.reads("owners_everything"))
        self.assertEqual(Economy(**available("owners_nothing")).owners_share, 0.0)
        self.assertEqual(len(second_run.SIDE_SETS), 43)


if __name__ == "__main__":
    unittest.main()

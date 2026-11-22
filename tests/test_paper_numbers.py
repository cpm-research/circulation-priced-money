"""The paper's numbers script (scripts/paper_numbers.py) on a tiny hand-made map: two cells, two seeds, every value
set by hand here, so each macro, the arrangements table and the circulation table can be checked against a number
worked out in the test.
Nothing is run and no stored result is read."""
import copy
import tempfile
import unittest
from pathlib import Path

from scripts import paper_numbers as pn

SEEDS = [11, 12]
NO_DISTRESS, HEADLINE = (0.044, 0.05, 0.0), (0.044, 0.05, 0.02)   # the two cells: (r_out, a0, distress)


def arm(failures, completed, c=None):
    """One arrangement's block in a cell: its failure share (% of spending), its by-class purchases completed (two
    classes of sizes 1 and 3) and, for CPM, the holding charge c (% a year)."""
    block = dict(failures_pct=failures, by_class=dict(class_sizes=[1.0, 3.0], completed=completed))
    if c is not None:
        block["c_pct"] = c
    return block


def cell(place, banks, defi, pool, cpm, indexed, charge):
    """One summary cell at ``place`` with each arrangement's failure share; purchases the same in every cell."""
    r_out, a0, distress = place
    return dict(r_out=r_out, a0=a0, distress=distress, seeds=len(SEEDS), recirculated=False,
                S0_failures_pct=banks, S0_by_class=dict(class_sizes=[1.0, 3.0], completed=[100.0, 100.0]),
                M0=arm(defi, [100.0, 120.0]), U=arm(pool, [100.0, 140.0]), M1=arm(cpm, [100.0, 200.0], charge),
                M2=arm(indexed, [100.0, 160.0], charge))


def tiny_map():
    """The hand-made map: summary.json's dictionary and cells.json's jobs (CPM's bridges served in years 4 and 5,
    by seed). At 2 points the first seed's bridges served, 0.55, is below the run line of 0.6."""
    summary = dict(provenance=dict(git_commit="abc", sources={"src/x.py": "hash"}, uncommitted_source_changes=False),
                   economy=dict(n=4000, lender_income_recirculated=None), seed_set="development", seeds=SEEDS,
                   inputs=dict(o=0.0016666666666666668, xi0=0.0025, xi1=0.03), constants=dict(MONTH_USD=6440.0),
                   r_out=[0.044], a0=[0.05], distress=[0.0, 0.02],
                   cells=[cell(NO_DISTRESS, 3.6, 3.45, 2.5, 2.25, 2.2, 0.125),
                          cell(HEADLINE, 5.9, 5.75, 4.75, 4.5, 4.45, 0.25)])
    served = {NO_DISTRESS: [0.9, 0.8], HEADLINE: [0.55, 0.7]}
    jobs = [dict(r_out=place[0], a0=place[1], distress=place[2], seed=seed, recirculated=False,
                 arms=dict(M1=dict(bridges_drawn_over_wanted=value)))
            for place in served for seed, value in zip(SEEDS, served[place])]
    return summary, jobs


# The circulation records of the hand-made measures.json: for each stored statistic, its base value b by arrangement
# and its step d. Seed 11 holds (b - d, b + d) in years 4 and 5 and seed 12 (b + d, b + 3d); years 1 to 3 hold 999,
# which the table must not read. So the seed means of years 4 and 5 are b and b + 2d and the cell's mean is b + d.
CIRCULATION = {("turnover", "e_p", "median"): (dict(S0=50, M0=20, U=23, M1=24), 1.0),
               ("turnover", "e_p", "weighted"): (dict(S0=48, M0=13, U=15, M1=16), 1.0),
               ("holding_velocity", "lifo", "top_tenth_share"): (dict(S0=0.25, M0=0.24, U=0.242, M1=0.243), 0.001),
               ("holding_velocity", "lifo", "median"): (dict(S0=0.002, M0=0.0023, U=0.0025, M1=0.0026), 0.00001),
               ("holding_velocity", "lifo", "mean_tau"): (dict(S0=26, M0=30, U=28, M1=27), 1.0),
               ("holding_velocity", "fifo", "mean_tau"): (dict(S0=35, M0=34, U=29, M1=28), 1.0),
               ("holding_velocity", "lifo", "sum"): (dict(S0=10, M0=4, U=6, M1=6.5), 0.5),
               ("microvelocity", "e_p_savings", "sum"): (dict(S0=10.2, M0=4.1, U=6.1, M1=6.6), 0.5)}
# The people of each arrangement's group; the other group's aggregate velocity part (non-participants for the
# network arrangements) is a fixed 5 a year with 2,000 people, and banks and cards have no participants at all.
GROUP = dict(S0="non_participants", M0="participants", U="participants", M1="participants")


def years(base, step, seed):
    """One stored yearly list (five years after launch) for ``seed``, as CIRCULATION describes."""
    low = base - step if seed == SEEDS[0] else base + step
    return [999.0, 999.0, 999.0, low, low + 2 * step]


def measures_job(place, seed):
    """One measures.json job at ``place`` holding the circulation records the table reads, for every arrangement."""
    series = {}
    for arm, group in GROUP.items():
        other = "participants" if group == "non_participants" else "non_participants"
        block = {}
        for (record, money, stat), (bases, step) in CIRCULATION.items():
            block.setdefault(record, {}).setdefault(money, {}).setdefault(group, {})[stat] = years(bases[arm], step,
                                                                                                    seed)
        for record, money in (("holding_velocity", "lifo"), ("microvelocity", "e_p_savings")):
            block[record][money][group]["people"] = [1000] * 5
            # Banks and cards: nobody in the network, whose sum the engine stores as undefined.
            block[record][money][other] = (dict(sum=[None] * 5, people=[0] * 5) if arm == "S0"
                                           else dict(sum=[5.0] * 5, people=[2000] * 5))
        series[arm] = block
    return dict(r_out=place[0], a0=place[1], distress=place[2], seed=seed, recirculated=False, series=series)


class CirculationTest(unittest.TestCase):
    def setUp(self):
        summary, jobs = tiny_map()
        self.raw = [measures_job(place, seed) for place in (NO_DISTRESS, HEADLINE) for seed in SEEDS]
        self.store = pn.Store(summary, jobs=jobs, monthly=list(map(pn.kept_monthly, self.raw)))
        self.macros, self.tables, self.ledger = pn.build(self.store)

    def rows(self):
        """The circulation table's rows as {(statistic, arrangement): (people, median, range)}; a statistic's label
        is written on its first row only, so it is carried down."""
        found, label = {}, None
        for row in self.tables["circulation"]["rows"]:
            label = row[1] or label
            found[(label, row[3])] = tuple(row[4:])
        return found

    def test_table_against_hand_values(self):
        # One cell with no distress, so median and range are the cell's value b + d (CIRCULATION).
        rows = self.rows()
        self.assertEqual(rows[("Wallet turnover, median person", "CPM")], ("participants", "25.0", "25.0"))
        self.assertEqual(rows[("Wallet turnover, median person", "Banks and cards")], ("everyone", "51.0", "51.0"))
        self.assertEqual(rows[("Wallet turnover, balance-weighted mean", "Best-case DeFi")][1], "14.0")
        self.assertEqual(rows[("MicroVelocity, top tenth's share of the group's sum", "CPM")][1], "0.244")
        self.assertEqual(rows[("MicroVelocity, median person", "Pool without the holding charge")][1], "0.00251")
        self.assertEqual(rows[("Mean holding time of money spent, last in first out", "CPM")][1], "28.0")
        self.assertEqual(rows[("Mean holding time of money spent, first in first out", "Banks and cards")][1], "36.0")
        # The aggregate velocity covers everyone: CPM's participants 6.5 + 0.5 and the others' fixed 5, so 12.00;
        # banks and cards have no participants, whose undefined sum counts zero: 10 + 0.5 = 10.50.
        aggregate = "Aggregate velocity, MicroVelocity summed over everyone"
        self.assertEqual(rows[(aggregate, "CPM")], ("everyone", "12.00", "12.00"))
        self.assertEqual(rows[(aggregate, "Banks and cards")], ("everyone", "10.50", "10.50"))
        self.assertEqual(len(rows), 7 * 4)                          # seven statistics, four arrangements

    def test_macros_and_report(self):
        # The holding times the prose quotes: last in first out, participants, b + d.
        self.assertEqual((self.macros["HoldingDaysCpm"], self.macros["HoldingDaysPool"]), ("28.0", "29.0"))
        line = next(line for line in self.ledger.lines if line.startswith("HoldingDaysCpm"))
        self.assertIn("series.M1.holding_velocity.lifo.participants.mean_tau", line)
        # The coin-age aggregate against the outflow one, in the notes: 12.0 and 6.6 + 0.5 + 5 = 12.1.
        self.assertTrue(any("CPM, aggregate velocity" in note and "12.000" in note and "12.100" in note
                            for note in self.ledger.notes))

    def test_a_record_not_stored_is_a_placeholder(self):
        summary, jobs = tiny_map()
        raw = copy.deepcopy(self.raw)
        del raw[1]["series"]["M1"]["holding_velocity"]               # one seed of the no-distress cell lacks it
        macros, tables, ledger = pn.build(pn.Store(summary, jobs=jobs, monthly=list(map(pn.kept_monthly, raw))))
        self.assertEqual(macros["HoldingDaysCpm"], pn.PLACEHOLDER)
        self.assertEqual(macros["HoldingDaysPool"], "29.0")            # the pool's records are all there
        self.assertTrue(any(line.startswith("circulation[Mean holding time of money spent, last in first out, CPM")
                            for line in ledger.missing))


class PaperNumbersTest(unittest.TestCase):
    def setUp(self):
        summary, jobs = tiny_map()
        self.store = pn.Store(summary, jobs=jobs, monthly=[])
        self.macros, self.tables, self.ledger = pn.build(self.store)

    def test_macros_against_hand_values(self):
        # Banks are the same in the one no-distress cell, so one value; DeFi and CPM low and high are that cell's;
        # the charge is CPM's c with no distress only (0.125, not the 0.25 under distress); RunAdoption is a0 = 5%,
        # since a seed at 2 points serves 0.55 < 0.6.
        expected = dict(NumPeople="4{,}000", NumSeedsDev="2", FailBanks=r"3.6\%", FailDefiLow=r"3.45\%",
                        FailDefiHigh=r"3.45\%", FailCpmLow=r"2.25\%", FailCpmHigh=r"2.25\%",
                        FailBanksStress=r"5.9\%", FailCpmStressLow=r"4.5\%", FailCpmStressHigh=r"4.5\%",
                        ChargeLow=r"0.125\%", ChargeHigh=r"0.125\%", RunAdoption=r"5\%")
        self.assertEqual({name: self.macros[name] for name in expected}, expected)
        self.assertTrue(all(name.isalpha() for name in self.macros))

    def test_arrangements_table_against_hand_values(self):
        # CPM's purchases completed weighted by class size: (1 x 100 + 3 x 200) / 4 = $175; banks' (100 + 300) / 4 =
        # $100. One cell at each level, so mean and range are that cell's value. Each arrangement's shares are quoted
        # to the most decimals it stores at either level: CPM's 2.25 sets two places, so 4.5 reads 4.50.
        rows = {row[0]: row[1:] for row in self.tables["arrangements"]["rows"]}
        self.assertEqual(rows["CPM"], [r"2.25\%", r"2.25\%", r"4.50\%", r"4.50\%", r"\$175"])
        self.assertEqual(rows["Banks and cards"], [r"3.6\%", r"3.6\%", r"5.9\%", r"5.9\%", r"\$100"])
        self.assertEqual(rows["Best-case DeFi"][-1], r"\$115")     # (100 + 3 x 120) / 4

    def test_missing_field_is_a_placeholder_and_a_report_line(self):
        summary, jobs = tiny_map()
        broken = copy.deepcopy(summary)
        del broken["cells"][0]["M1"]["c_pct"]                       # an older result without the holding charge
        macros, tables, ledger = pn.build(pn.Store(broken, jobs=jobs, monthly=[]))
        self.assertEqual(macros["ChargeLow"], pn.PLACEHOLDER)
        self.assertEqual(macros["ChargeHigh"], pn.PLACEHOLDER)
        self.assertTrue(any(line.startswith("ChargeLow") and "M1.c_pct" in line for line in ledger.missing))
        # The monthly series were not given at all: those numbers are placeholders too, never invented.
        self.assertTrue(any("registered flag" in line for line in ledger.missing))
        # Everything is still written: numbers.tex carries the placeholder, the report names what is missing.
        with tempfile.TemporaryDirectory() as folder:
            pn.write(folder, pn.Store(broken, jobs=jobs, monthly=[]), macros, tables, ledger)
            text = (Path(folder) / "numbers.tex").read_text(encoding="utf-8")
            report = (Path(folder) / "numbers_report.txt").read_text(encoding="utf-8")
            self.assertIn(r"\newcommand{\ChargeLow}{" + pn.PLACEHOLDER + "}", text)
            self.assertIn("NOT STORED", report)
            self.assertTrue((Path(folder) / "tables" / "arrangements.tex").exists())

    def test_ambiguous_numbers_stop_the_script(self):
        summary, jobs = tiny_map()
        twice = copy.deepcopy(summary)
        twice["cells"].append(copy.deepcopy(twice["cells"][0]))     # two cells at one grid place
        with self.assertRaises(ValueError):
            pn.Store(twice, jobs=jobs, monthly=[])
        fewer = copy.deepcopy(summary)
        fewer["cells"][0]["seeds"] = 1                              # a cell ran fewer seeds than the map lists
        with self.assertRaises(ValueError):
            pn.build(pn.Store(fewer, jobs=jobs, monthly=[]))

    def test_the_seed_design_from_the_code(self):
        """The registered seed design (17 Nov 2026), each macro traced in the report: 30 confirmation seeds and an
        extension to 60, at assurance 0.8; of 30 seeds 21 read above one half at 95%, 24 at CPM's Bonferroni level
        over 21 cells and 23 at indexed CPM's over 14 (wilson_bounds), and of 60, 38, 42 and 42; 30 seeds resolve the
        $2 margin at CPM's Bonferroni level up to a spread of $2.597, quoted at the cent below, $2.59."""
        expected = dict(SeedsConfirm="30", SeedsExtended="60", SeedAssurance="0.8", WilsonConfirm="21",
                        WilsonConfirmBonf="24", WilsonConfirmBonfIndexed="23", WilsonExtended="38",
                        WilsonExtendedBonf="42", WilsonExtendedBonfIndexed="42", SpreadResolved=r"\$2.59")
        self.assertEqual({name: self.macros[name] for name in expected}, expected)
        for name in expected:
            self.assertTrue(any(line.startswith(f"{name} = ") and "<-" in line for line in self.ledger.lines), name)
        self.assertEqual(pn.CONFIRMATION_SEEDS, 30)
        # The map stores no planner block, so its counts are placeholders and say so.
        self.assertEqual(self.macros["SeedsAssured"], pn.PLACEHOLDER)
        self.assertTrue(any(line.startswith("SeedsAssured") for line in self.ledger.missing))

    def test_the_assured_count_from_the_stored_readings(self):
        """A stored planner block like the final development map's: the binding reading, CPM's dip against best-case
        DeFi, spread 1.1658 on 21 cells; with this map's two seeds a cell and no stored degrees of freedom that is
        21 x (2 - 1) = 21, so its bound is 1.1658 x sqrt(21 / chi2_0.2(21)) = 1.359, which needs 33 seeds. Stored with
        42 degrees of freedom, as the planner now stores them, its bound is 1.293 and it needs 30, the count the
        development map gives. A cost reading of $1.0653 needs few; a reading with no spread is skipped."""
        summary, jobs = tiny_map()
        alpha = 0.05 / 21
        readings = [dict(arm="M1", reading="cost against M0", distress=0.0, spread=1.0653, cells=21, seeds=9),
                    dict(arm="M1", reading="dip against M0", distress=0.02, spread=1.1658, cells=21, seeds=26),
                    dict(arm="M2", reading="dip against M0", distress=0.02, spread=None, cells=0, seeds=None)]
        summary["claim_statistics"] = dict(seeds=dict(readings=readings, seeds=26),
                                           bonferroni=dict(M1=dict(alpha=alpha), M2=dict(alpha=0.05 / 14)))
        macros, _, ledger = pn.build(pn.Store(summary, jobs=jobs, monthly=[]))
        self.assertEqual((macros["SeedsPlanned"], macros["SeedsAssured"], macros["SpreadBinding"],
                          macros["FreedomBinding"], macros["SpreadBindingBound"]), ("26", "33", "1.1658", "21", "1.359"))
        stored = copy.deepcopy(summary)
        stored["claim_statistics"]["seeds"]["readings"][1]["freedom"] = 42
        macros, _, ledger = pn.build(pn.Store(stored, jobs=jobs, monthly=[]))
        self.assertEqual((macros["SeedsAssured"], macros["FreedomBinding"], macros["SpreadBindingBound"]),
                         ("30", "42", "1.293"))
        line = next(line for line in ledger.lines if line.startswith("SeedsAssured"))
        self.assertIn("dip against M0, distress 0.02", line)

    def test_formatting(self):
        self.assertEqual(pn.usd(1234.5), r"\$1{,}235")
        self.assertEqual(pn.usd(-3.21), r"$-$\$3.2")
        self.assertEqual(pn.span(1.0, 2.0, pn.usd), r"\$1.0 to \$2.0")
        self.assertEqual(pn.stored_places([3.631, 2.5]), 3)


def with_gains(summary, banks, defi):
    """``summary`` with CPM's gain in money over banks and cards and over best-case DeFi set in its cell with no
    distress."""
    summary["cells"][0]["M1"]["against"] = dict(S0=dict(gain_usd_a_year=banks), M0=dict(gain_usd_a_year=defi))
    return summary


def confirmation_map():
    """The tiny map as a confirmation run stores it: three other seeds, banks failing 4.5% and not 3.6%, gains of
    $300 and $200, a claim block in the cell with no distress (passing both ways, 7 seeds needed, no falsifier) and
    the claim's statistics (that cell in the region with no distress, none at 2 points, a planner count of 9)."""
    summary, _ = tiny_map()
    summary = with_gains(copy.deepcopy(summary), 300.0, 200.0)
    seeds = [101, 102, 103]
    summary.update(seed_set="confirmation", seeds=seeds)
    for one in summary["cells"]:
        one["seeds"] = len(seeds)
    summary["cells"][0]["S0_failures_pct"] = 4.5
    summary["cells"][0]["M1"]["claim"] = dict(all_as_built=True, all=True, in_region=True, underpowered=False,
                                              seeds_needed=7, d_bound=dict(status="pass"),
                                              worse_than_M0=dict(fires=False))
    place = [NO_DISTRESS[0], NO_DISTRESS[1]]
    summary["claim_statistics"] = dict(regions=dict(M1=[dict(distress=0.0, passing=[place], region=[place]),
                                                        dict(distress=0.02, passing=[], region=[])]),
                                       holds_somewhere=dict(M1=[place]), seeds=dict(seeds=9, readings=[]))
    jobs = [dict(r_out=p[0], a0=p[1], distress=p[2], seed=seed, recirculated=False,
                 arms=dict(M1=dict(bridges_drawn_over_wanted=0.9))) for p in (NO_DISTRESS, HEADLINE) for seed in seeds]
    return summary, jobs


class BaseTest(unittest.TestCase):
    """A confirmation map read beside the development map: the headline and the claim come from the map, and what
    was run on the development seeds stands beside the development map (``base``)."""

    def setUp(self):
        dev, dev_jobs = tiny_map()
        dev = with_gains(dev, 100.0, 50.0)
        dev["claim_statistics"] = dict(seeds=dict(seeds=26, readings=[]))
        self.base = pn.Store(dev, jobs=dev_jobs, monthly=[], folder="development_map")
        summary, jobs = confirmation_map()
        self.store = pn.Store(summary, jobs=jobs, monthly=[], folder="confirmation_quote")
        changed = with_gains(copy.deepcopy(dev), 90.0, 40.0)
        self.sides = [("one setting changed", pn.Store(changed, jobs=dev_jobs, monthly=[], folder="side_x"))]
        self.macros, self.tables, self.ledger = pn.build(self.store, self.sides, bounds=self.sides, base=self.base)

    def test_the_headline_and_the_claim_come_from_the_map(self):
        expected = dict(NumSeeds="3", FailBanks=r"4.5\%", GainBanksMedian=r"\$300", GainDefiMedian=r"\$200",
                        RegionCellsZero="1", RegionCellsTwo="0", ClaimCellsAsBuilt="1", ClaimCellsBoth="1",
                        ClaimCellsFalsified="no", ClaimCellsUnderpowered="no", ClaimHoldsSomewhere="1",
                        ClaimSeedsPlanned="9", ClaimSeedsCellMost="7")
        self.assertEqual({name: self.macros[name] for name in expected}, expected)
        # A distress level whose region the summary does not store is a placeholder, never a zero.
        self.assertEqual(self.macros["RegionCellsHalf"], pn.PLACEHOLDER)

    def test_the_seed_plan_and_the_side_sets_stand_beside_the_base(self):
        self.assertEqual((self.macros["NumSeedsDev"], self.macros["SeedsPlanned"]), ("2", "26"))
        # The first row of each table is the development map's own cell, $100 and $50, and not the confirmation
        # map's $300 and $200; the side set, on the same seeds, reads $90 and $40 beside it.
        for name in ("side", "bounds"):
            rows = self.tables[name]["rows"]
            self.assertEqual([row[:3] for row in rows], [["development map", r"\$100", r"\$50"],
                                                         ["one setting changed", r"\$90", r"\$40"]], name)
        self.assertFalse(any("NumSeedsDev counts" in note for note in self.ledger.notes))
        self.assertIn("read beside: development_map (seed set development, 2 seeds)",
                      pn.header(self.store, self.base))

    def test_the_two_entry_readings_stand_side_by_side(self):
        # The same map under the second reading: gains of $250 and $150 where the first has $300 and $200.
        summary, jobs = confirmation_map()
        second = pn.Store(with_gains(summary, 250.0, 150.0), folder="confirmation_realised")
        macros, tables, _ = pn.build(self.store, base=self.base, second=second)
        self.assertEqual((macros["ReadFirstGainBanks"], macros["ReadSecondGainBanks"]), (r"\$300", r"\$250"))
        self.assertEqual((macros["ReadFirstGainDefi"], macros["ReadSecondGainDefi"]), (r"\$200", r"\$150"))
        self.assertEqual((macros["ReadFirstRegion"], macros["ReadSecondRegion"]), ("1", "1"))
        rows = {row[0]: row[1:] for row in tables["readings"]["rows"]}
        self.assertEqual(list(rows), list(pn.READING_LABELS))
        self.assertEqual(rows["Gain over banks and cards"], [r"\$300", r"\$250"])
        # What a summary does not store is a placeholder in its own column, never a number.
        self.assertEqual(rows["Pool capital over its target"], [pn.PLACEHOLDER, pn.PLACEHOLDER])
        self.assertNotIn("readings", pn.build(self.store, base=self.base)[1])    # no second map, no table

    def test_a_map_alone_is_its_own_base(self):
        macros, tables, ledger = pn.build(self.store, self.sides)
        self.assertEqual((macros["NumSeeds"], macros["NumSeedsDev"], macros["SeedsPlanned"]), ("3", "3", "9"))
        self.assertEqual(tables["side"]["rows"][0][:3], ["main map", r"\$300", r"\$200"])
        self.assertTrue(any("NumSeedsDev counts the 'confirmation' seed set" in note for note in ledger.notes))
        self.assertNotIn("read beside", pn.header(self.store))
        # The development map alone, as before the confirmation: both counts are its own.
        macros, tables, _ = pn.build(self.base, self.sides)
        self.assertEqual((macros["NumSeeds"], macros["NumSeedsDev"]), ("2", "2"))
        self.assertEqual(tables["side"]["rows"][0][0], "development map")


def pool_cell(rate, launch, scale, served, capital, target):
    """One cell with no distress holding what the sources and lending tables read of CPM: the split of the gain over
    the run (``scale`` times a fixed set of parts), the by-class instalment lending and bridging refused (classes of
    sizes 1 and 3), pool capital, its target and bridges served."""
    split = dict(other_outside_flows=100.0, outside_interest_saved=200.0, card_fees_saved=50.0, card_rewards=-10.0,
                 advance_fees_saved=30.0, late_fees_saved=20.0, penalties_saved=10.0, pool_costs=-40.0,
                 savings_income=-60.0, inflation=0.0, valuation=0.0, conversion_fees_saved=5.0,
                 gas_to_validators=-5.0, wages_to_outside=0.0)
    by_class = dict(class_sizes=[1.0, 3.0], term_pool=[100.0 * scale, 300.0 * scale],
                    bridge_refused=[40.0 * scale, 80.0 * scale])
    return dict(r_out=rate, a0=launch, distress=0.0, seeds=len(SEEDS), recirculated=False,
                M1=dict(split={name: value * scale for name, value in split.items()}, by_class=by_class, N=capital,
                        N_star=target, bridges_drawn_over_wanted=served))


def pool_map(rate, coupons=None):
    """A map of two launch levels at one outside rate for the two tables, the second cell's flows twice the first's;
    with ``coupons``, each cell's instalment coupon by seed, its per-seed store too."""
    cells = [pool_cell(rate, 0.05, 1.0, 0.7, 0.2, 0.25), pool_cell(rate, 0.3, 2.0, 0.9, 0.35, 0.35)]
    vehicle = [[0.16, 0.13, 0.09, 0.0455, 0.03], [0.21, 0.19, 0.13, 0.08, 0.0469]]
    summary = dict(provenance=dict(git_commit="abc"), economy=dict(months=60, lender_income_recirculated=None),
                   constants=dict(MONTH_USD=6440.0, VEHICLE_TIER_SCORES=[501, 601, 661, 781]), seeds=SEEDS,
                   r_out=[rate], a0=[0.05, 0.3], distress=[0.0], outside_rates=[dict(r_out=rate, vehicle=vehicle)],
                   cells=cells)
    jobs = None if coupons is None else [
        dict(r_out=rate, a0=launch, distress=0.0, seed=seed, recirculated=False, arms=dict(M1=dict(r_term_pct=value)))
        for launch, values in zip((0.05, 0.3), coupons) for seed, value in zip(SEEDS, values)]
    return pn.Store(summary, jobs=jobs, folder="confirmation_quote" if jobs else "rate_cut")


class SourcesAndLendingTest(unittest.TestCase):
    """The gain split by the flow it comes from, and what is asked of the pool by outside rate, on hand values."""

    def setUp(self):
        self.store = pool_map(0.02, coupons=([4.0, 4.4], [4.4, 4.8]))
        self.cut = pool_map(0.03)                                  # read from its summary alone: no per-seed store

    def test_the_split_adds_up_a_year(self):
        # Over 60 months the first cell's parts are 100, 200, 40, 60, -40, -60 and 0, a fifth of that a year, and
        # the second cell's twice that; the median of two cells is their mean.
        table, macros = pn.sources_table(self.store, pn.Ledger())
        self.assertEqual([row[1] for row in table["rows"]],
                         [r"\$30", r"\$60", r"\$12", r"\$18", r"$-$\$12", r"$-$\$18", r"\$0.0", r"\$90"])
        self.assertEqual((macros["SourceYieldTwo"], macros["SourceTotalTwo"]), (r"\$30", r"\$90"))
        self.assertEqual(table["rule_before"], [len(pn.SOURCE_ROWS)])

    def test_what_is_asked_of_the_pool(self):
        ledger = pn.Ledger()
        table, macros = pn.lending_table(self.store, self.cut, ledger)
        self.assertEqual(table["head"], ["Outside rate", r"2.0\%", r"3.0\%" + pn.CUT_MARK])
        rows = {row[0]: row[1:] for row in table["rows"]}
        # The coupon: each cell's mean over seeds, 4.2 and 4.6, then the median over the two launch levels. The cut
        # was read without its per-seed store, so its coupon is a placeholder and never a number.
        self.assertEqual(rows["Pool's instalment coupon"], [r"4.40\%", pn.PLACEHOLDER])
        self.assertEqual(rows["Outside lender, new car, scores 661 to 780"], [r"4.55\%", r"4.55\%"])
        self.assertEqual(rows["Outside lender, used car, scores 781 and above"], [r"4.69\%", r"4.69\%"])
        # By class, weighted by the sizes 1 and 3: lending (100 + 900) / 4 = 250 and 500, refused 70 and 140.
        self.assertEqual(rows[r"Pool instalment lending, \$ a person a year"], [r"\$375", r"\$375"])
        self.assertEqual(rows[r"Bridging refused, \$ a person a year"], [r"\$105", r"\$105"])
        # Targets of 0.25 and 0.35 months of 6,440 dollars; capital 0.8 and 1.0 of them; bridges served 0.7, 0.9.
        self.assertEqual(rows[r"Capital target, \$ a person"], [r"\$1{,}932", r"\$1{,}932"])
        self.assertEqual(rows["Pool capital over its target"], ["0.90", "0.90"])
        self.assertEqual(rows["Bridges served"], ["0.80", "0.80"])
        self.assertEqual((macros["LendCouponTwo"], macros["LendCouponThree"], macros["LendTermThree"]),
                         (r"4.40\%", pn.PLACEHOLDER, r"\$375"))
        self.assertTrue(any("LendCouponThree" in line for line in ledger.missing))
        # With no cut the table holds the map's own rates alone.
        self.assertEqual(pn.lending_table(self.store, None, pn.Ledger())[0]["head"], ["Outside rate", r"2.0\%"])


class PercentTest(unittest.TestCase):
    """The scale-free readings that stand beside the dollar figures, on hand values."""

    def test_relative_cuts_and_shares_of_spending(self):
        summary, jobs = tiny_map()
        summary["economy"]["months"] = 60
        line = lambda lenders, spread: dict(outside_lenders=dict(paid_usd=lenders), banks_and_funds=dict(paid_usd=spread),
                                            total=dict(paid_usd=lenders + spread))
        for one in summary["cells"]:
            # Over 60 months: banks 4,000 to lenders and 1,000 of spread, best-case DeFi 4,000 and 375, CPM 3,000 and
            # 500. A bridge costs 2% under CPM and 8% without the charge; the gain is 1% of a year of 6,440 a month.
            one["S0_transfers"], one["M0"]["transfers"], one["M1"]["transfers"] = line(4000.0, 1000.0), line(4000.0, 375.0), \
                line(3000.0, 500.0)
            one["M1"]["r_b_pct"], one["U"]["r_b_pct"] = 2.0, 8.0
            one["M1"]["against"] = dict(S0=dict(gain_usd_a_year=772.8))
        macros = pn.percent_macros(pn.Store(summary, jobs=jobs, folder="map"), pn.Ledger())
        # Failed shares: 2.25% against 3.6% with no distress, 4.5% against 5.9% and 5.75% at 2 points.
        self.assertEqual((macros["FailCutBanks"], macros["FailCutBanksStress"], macros["FailCutDefiStress"]),
                         (r"38\%", r"24\%", r"22\%"))
        # A year: 1,000 under banks, 875 under DeFi, 700 under CPM; in cash 800 against 600.
        self.assertEqual((macros["OutsidePaidBanks"], macros["OutsidePaidCpm"]), (r"\$1{,}000", r"\$700"))
        self.assertEqual((macros["OutsideCutBanks"], macros["OutsideCutDefi"], macros["OutsideCashCutBanks"]),
                         (r"30\%", r"20\%", r"25\%"))
        self.assertEqual((macros["BridgeCutLow"], macros["BridgeCutHigh"]), (r"75\%", r"75\%"))
        self.assertEqual(macros["GainBanksSpending"], r"1.00\%")
        # What the map does not store is a placeholder, never a number.
        self.assertEqual(macros["GainDefiSpending"], pn.PLACEHOLDER)

    def test_a_change_is_its_size_and_needs_both_levels(self):
        ledger = pn.Ledger()
        self.assertEqual(pn.change_macro(ledger, "Up", 50.0, 40.0, "x"), r"25\%")
        self.assertEqual(pn.change_macro(ledger, "Down", 30.0, 40.0, "x"), r"25\%")
        self.assertEqual(pn.change_macro(ledger, "None", float("nan"), 40.0, "x"), pn.PLACEHOLDER)
        self.assertEqual(pn.change_macro(ledger, "Zero", 30.0, 0.0, "x"), pn.PLACEHOLDER)


class ChargeGainTest(unittest.TestCase):
    """CPM less the pool without the charge by distress level, with its interval across seeds, on hand values."""

    def test_the_gain_over_the_pool_without_the_charge(self):
        summary, jobs = tiny_map()
        by_seed = {NO_DISTRESS: [18.0, 22.0], HEADLINE: [10.0, 10.2]}
        for one in summary["cells"]:
            place = (one["r_out"], one["a0"], one["distress"])
            one["M1"]["against"] = dict(U=dict(gain_usd_a_year=sum(by_seed[place]) / 2))
        for job in jobs:
            place = (job["r_out"], job["a0"], job["distress"])
            job["arms"]["M1"]["against"] = dict(U=dict(gain_usd_a_year=by_seed[place][SEEDS.index(job["seed"])]))
        table, macros = pn.charge_gain_table(pn.Store(summary, jobs=jobs, folder="map"), None, pn.Ledger())
        rows = {row[0]: row[1:] for row in table["rows"]}
        # No distress: seeds 18 and 22, mean 20, standard error 2, and t at one degree of freedom is 12.706, so the
        # lower end is 20 - 25.41: below zero. CPM fails 2.25% against the pool's 2.5%.
        self.assertEqual(rows["0 pt"], [r"\$20", r"$-$\$5.4", "0", "1"])
        # 2 points: seeds 10 and 10.2, mean 10.1, standard error 0.1, lower end 10.1 - 1.27.
        self.assertEqual(rows["2 pt"], [r"\$10", r"\$8.8", "1", "1"])
        # A level the map did not run is a placeholder, and so is a count over the whole grid that needs it.
        self.assertEqual(rows["1 pt"], [pn.PLACEHOLDER] * 4)
        self.assertEqual((macros["ChargeGainFirstAboveAll"], macros["ChargeGainFirstCells"]), (pn.PLACEHOLDER, "2"))
        self.assertEqual(len(table["head"]), 5)                       # one reading: no second map was given


class PathTest(unittest.TestCase):
    """The pool year by year after launch under the two entry readings, on hand values."""

    def test_the_path_year_by_year(self):
        summary, _ = tiny_map()
        two_years = lambda first, second: pn.np.array([first] * 12 + [second] * 12, float)
        # Two seeds, two years stored. Capital 0.1 months of income in year 1 and 0.2 or 0.25 in year 2, against a
        # target of 0.1 and then 0.25; bridges served 0.9 and then 0.8 or 0.6.
        seeds = {11: (two_years(0.1, 0.2), two_years(0.9, 0.8)), 12: (two_years(0.1, 0.25), two_years(0.9, 0.6))}
        monthly = [dict(r_out=NO_DISTRESS[0], a0=NO_DISTRESS[1], distress=NO_DISTRESS[2], seed=seed, recirculated=False,
                        monthly=dict(M1=dict(N=capital, Q=two_years(0.1, 0.25), bridges_drawn_over_wanted=served)))
                   for seed, (capital, served) in seeds.items()]
        first = pn.Store(summary, monthly=monthly, folder="confirmation_quote")
        second = pn.Store(copy.deepcopy(summary), folder="confirmation_realised")      # its summary alone
        ledger = pn.Ledger()
        table, macros = pn.path_table(first, second, ledger)
        # Year 1: capital at its target, 0.1 x 6,440 dollars. Year 2: 0.8 and 1.0 of the target, 0.225 x 6,440.
        self.assertEqual(table["rows"][0][:5], ["1", "1.00", r"\$644", r"\$644", "0.90"])
        self.assertEqual(table["rows"][1][:5], ["2", "0.90", r"\$1{,}449", r"\$1{,}610", "0.70"])
        # A year the run did not reach, and a reading whose monthly store was not read, are placeholders.
        self.assertEqual(table["rows"][4][1:], [pn.PLACEHOLDER] * 8)
        self.assertEqual(table["rows"][0][5:], [pn.PLACEHOLDER] * 4)
        self.assertEqual((macros["PathFirstRatioTwo"], macros["PathSecondRatioTwo"]), ("0.90", pn.PLACEHOLDER))
        self.assertEqual(len(table["head"]), 9)


if __name__ == "__main__":
    unittest.main()

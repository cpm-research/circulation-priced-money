"""The seeds and the cells: which runs the map is made of.

The seed sets (development, sweep and the confirmation block fixed at the freeze, with the retired blocks), the one
definition of the confirmation count and the planner that reads the development map for it, each cell's inputs,
the selection of cells from the grid and the jobs it gives (built with the pinned PySPG catalogue), and the number of
runs in a job.
"""
from itertools import chain, product

import numpy as np

from cpm_abm.catalogue import finite_catalogue
from run_economy_figures import engine_inputs
from cpm_abm.experiment.notes import (A0S, ARMS, BASE, CLAIM_ARMS, CLAIM_MARGIN, DIP_MARGIN, DISTRESS, GRID, RATES,
                                      LOW_RATES, SEED_ASSURANCE, SEED_CAP, SEED_POWER, SIDE_RATES, STRESS_LEVELS)
from cpm_abm.experiment.statistics import (bonferroni_alpha, dips, limited, pooled_freedom, pooled_spread,
                                           seeds_needed, spread_bound, yearly_dips)

# Seed sets (decided 31 Oct; new blocks 3 and 12 Nov): the three seeds used so far stay for
# development checks. Three blocks are retired, each touched before its frozen run: 20261101 to 20261120 (review
# scripts rebuilt a population on 20261101, 3 Nov row); 20261201 to 20261220 (the 5 Nov confirmation attempt ran on it
# and its crash was debugged on 20261210, no outcome stored or read); and 20261301 to 20261308 (the 12 Nov population
# size sweep ran on it). The confirmation map uses the first n seeds of a block never run, from 20261401, never used
# in development. n is 30 (decided 17 Nov 2026, before any confirmation seed was run or read; it replaces the round
# count of 15 Nov): the planner's count (``confirmation_seeds``) with each reading's pooled spread taken at the upper end of
# its one-sided interval at assurance 0.8 (SEED_ASSURANCE), s x sqrt(nu / chi2_0.2(nu)) (``spread_bound``), the
# largest count over the readings, at most 100. On the final development map the binding reading, the dip against M0
# at 2 points, has s = 1.1658 over 21 cells of 3 seeds, nu = 42, so 1.293 and 30 seeds (26 at the point estimate).
# The confirmation seeds are 20261401 to 20261430. The one declared extension takes the cells the planner marks
# underpowered at 30 to 60 seeds (CONFIRMATION_EXTENSION), adding 20261431 to 20261460. CONFIRMATION_COUNT holds n.
# Were it None, SEEDS["confirmation"] would be None and a run with
# --seeds confirmation would be refused (``seeds_for``), so no run can use a placeholder count. The sweep entry records
# the seeds the size sweep used (decided 12 Nov); it is kept so that run can be reproduced, and it is not a block
# for any new run.
CONFIRMATION_START = 20261401
CONFIRMATION_LEAST, CONFIRMATION_MOST = 2, 100
CONFIRMATION_COUNT = 30               # decided 17 Nov 2026 by the rule above (docs/ANALYSIS_PLAN.md)
CONFIRMATION_EXTENSION = 60           # the one declared extension: underpowered cells at 30 run to 60 seeds


def confirmation_block(count):
    """The confirmation seeds for a frozen count n: exactly 20261401 to 20261400 + n. A count that is not a whole
    number from 2 to 100 is refused (ValueError). Hand case: 14 gives 20261401 to 20261414."""
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or not (
            CONFIRMATION_LEAST <= count <= CONFIRMATION_MOST):
        raise ValueError(f"The confirmation count must be a whole number from {CONFIRMATION_LEAST} to "
                         f"{CONFIRMATION_MOST}, fixed at the freeze; got {count!r}")
    return tuple(range(CONFIRMATION_START, CONFIRMATION_START + int(count)))


# The exploratory seeds (the 12 Nov row on the seeds for the frozen run): any run made after the confirmation is read
# uses seeds from 20261601 upward and is labelled exploratory. The rate cut (decided 17 Nov 2026) is the first such
# run, on the first 30 of them, as many seeds as the confirmation map has.
EXPLORATORY_START, EXPLORATORY_COUNT = 20261601, 30
# The side seeds (decided 18 Nov 2026): the next three of the exploratory block, for the exploratory side checks
# made after the confirmation was read (the fixed cost at multiples, the custody cost, the owners' spread, the
# shock date, the low rates), each beside a base run of the same cells on the same three seeds.
SIDE_SEEDS = (20261631, 20261632, 20261633)
SEEDS = dict(development=(20261021, 20261022, 20261023),
             confirmation=None if CONFIRMATION_COUNT is None else confirmation_block(CONFIRMATION_COUNT),
             sweep=tuple(range(20261301, 20261309)),
             exploratory=tuple(range(EXPLORATORY_START, EXPLORATORY_START + EXPLORATORY_COUNT)), side=SIDE_SEEDS)
# The whole block the confirmation seeds are drawn from, at its largest (100 seeds): no other set may touch it.
CONFIRMATION_RESERVED = tuple(range(CONFIRMATION_START, CONFIRMATION_START + CONFIRMATION_MOST))


def seeds_for(name, count=None):
    """The seeds a run named ``name`` uses: the development or sweep set, or for "confirmation" the first ``count``
    seeds of its block (``confirmation_block``; by default CONFIRMATION_COUNT). With no count the confirmation run
    is refused (ValueError), so it can never silently run a placeholder number of seeds."""
    if name != "confirmation":
        return SEEDS[name]
    count = CONFIRMATION_COUNT if count is None else count
    if count is None:
        raise ValueError("The confirmation seed count is not set: CONFIRMATION_COUNT is fixed at the freeze, 2 to "
                         "100; nothing was run")
    return confirmation_block(count)
# The retired blocks (above): no run may use one of these seeds again.
RETIRED_SEEDS = (tuple(range(20261101, 20261121)), tuple(range(20261201, 20261221)), tuple(range(20261301, 20261309)))


def cell_inputs(rate, fixed_cost="central"):
    """The Inputs a cell runs on: the core model's values with rho_H = r_out / 12 (the map's convention), no provider
    fee (decided 5 Nov: P payments run on stablecoin rails) and the sourced fixed cost at ``fixed_cost``
    (decided 5 Nov: "central", "low" or "high", ``engine_inputs``)."""
    return engine_inputs(fixed_cost, rho_H=rate / 12)


# The stress boundary's levels (docs/ROBUSTNESS_PLAN.md, section 6): finer distress levels between the grid's 1.5 and
# 2 points, for a side run on development seeds only, beside the grid's levels and never part of the grid, so the
# full grid, the confirmation run and every reading tied to the grid's levels stay as they are. A side level is read
# against the same seed's level 0 as any level is, so a side run selects 0 too.
SIDE_DISTRESS = (0.016, 0.017, 0.018, 0.019)


def selected(r_out=RATES, a0=A0S, distress=DISTRESS):
    """The cells a run covers (the 3 Nov review): the chosen values of each dimension in the grid's order, each once;
    by default the full grid. A value outside the grid is refused, so a selection never adds a cell, except a stress
    boundary level (``SIDE_DISTRESS``), which takes its place among the distress levels in order, and a rate of the
    rate cut or a low rate (``SIDE_RATES``, ``LOW_RATES``, cpm_abm.experiment.notes), which takes its place among
    the outside rates."""
    chosen = dict(r_out=r_out, a0=a0, distress=distress)
    allowed = dict(GRID, r_out=tuple(sorted(GRID["r_out"] + SIDE_RATES + LOW_RATES)),
                   distress=tuple(sorted(GRID["distress"] + SIDE_DISTRESS)))
    if any(not values or set(values) - set(allowed[name]) for name, values in chosen.items()):
        raise ValueError(f"Select one or more values of each dimension of the grid {GRID}, or among the distress levels "
                         f"a stress boundary level {SIDE_DISTRESS}, or among the outside rates a rate of the rate cut "
                         f"{SIDE_RATES} or a low rate {LOW_RATES}")
    return {name: tuple(value for value in allowed[name] if value in chosen[name]) for name in GRID}


def tasks_for(seeds, n, selection=GRID, returned=False):
    """Every job of the selected cells (``selected``, by default the full grid): their cross (a PySPG catalogue, last
    dimension fastest), then with the full grid the baseline cell without distress under the recirculation
    convention. With ``returned`` (decided 12 Nov: ``--lenders-interest returned``) every job runs with outside
    lenders' interest returned to households, and no extra set is added."""
    sweep = finite_catalogue(dict(**{name: list(values) for name, values in selection.items()}, seed=list(seeds)))
    tasks = [(p["r_out"], p["a0"], p["distress"], p["seed"], n, returned) for p in sweep]
    # A selection of cells runs those cells only, without the recirculation set (Step 2 of the 3 Nov round is its own
    # 6 jobs), as decided 4 Nov; a map with lenders' interest returned over the whole grid has no
    # separate set to add (12 Nov).
    if selection != GRID or returned:
        return tasks
    return tasks + [(p["r_out"], p["a0"], 0.0, p["seed"], n, True)
                    for p in finite_catalogue(dict(r_out=[BASE[0]], a0=[BASE[1]], seed=list(seeds)))]


def runs_in(task, s0_only=False):
    """Population runs in one job: S0 and each arm beside it, or with ``s0_only`` S0's run alone."""
    return 1 if s0_only else 1 + len(ARMS)


def confirmation_seeds(index, by_cell, w):
    """The confirmation seed count from the development map's spread (the statistics row): for each claim arm, the
    level-0 cost reading (clause (b)'s savings against M0 and against S0, margin $2) with its spread pooled across the
    level-0 cells, and at each distress level the dip (against S0 and against M0, margin one failed payment) with its
    spread pooled across that level's cells, each at the arm's Bonferroni level and 80% power (``seeds_needed``);
    the largest is taken, at most 100. The dip's spread is the yearly dip's (the 36-month sum over 3), the series
    the stress leg tests against one failed payment a year. Beside that count, the assured count (decided 17 Nov 2026,
    the rule CONFIRMATION_COUNT follows): the same largest count with each reading's spread at the upper end of its
    one-sided interval at SEED_ASSURANCE (``spread_bound``, the reading's seeds_assured), at most 100.
    CONFIRMATION_COUNT is not changed here; it is stored beside the planner's counts (confirmation_seeds_now). Hand
    cases: a pooled cost spread of $4 at M1's level needs 65 seeds; the final development map's binding reading, a dip
    spread of 1.1658 over 21 cells of 3 seeds, needs 26 at the point estimate and 30 assured."""
    readings = list(chain.from_iterable(_seed_readings(arm, index, by_cell, w) for arm in CLAIM_ARMS))
    counted = [r for r in readings if r["spread"] is not None]
    largest = max(counted, key=lambda r: np.inf if r["seeds"] is None else r["seeds"], default=None)
    most = None if largest is None else (np.inf if largest["seeds"] is None else largest["seeds"])
    bounded = [r for r in counted if r["spread_bound"] is not None]
    # The reading that sets the assured count; at a tie, the one with the larger bound.
    assured = max(bounded, key=lambda r: (np.inf if r["seeds_assured"] is None else r["seeds_assured"],
                                          r["spread_bound"]), default=None)
    most_assured = None if assured is None else (np.inf if assured["seeds_assured"] is None
                                                 else assured["seeds_assured"])
    return dict(readings=readings, largest=largest, seeds=None if most is None else int(min(most, SEED_CAP)),
                capped=bool(most is not None and most > SEED_CAP), cap=SEED_CAP, power=SEED_POWER,
                confirmation_seeds_now=CONFIRMATION_COUNT, largest_assured=assured,
                seeds_assured=None if most_assured is None else int(min(most_assured, SEED_CAP)),
                capped_assured=bool(most_assured is not None and most_assured > SEED_CAP), assurance=SEED_ASSURANCE)


def _seed_readings(arm, index, by_cell, w):
    """One claim arm's readings for the seed count (``confirmation_seeds``): the level-0 cost against M0 and against
    S0, then at each distress level the dip against S0 and against M0, each with its pooled spread and the seeds it
    needs at the arm's Bonferroni level, and beside them the spread's degrees of freedom, its upper bound at
    SEED_ASSURANCE and the seeds that bound needs; none outside the arm's declared limit's cells."""
    cells = {k: c for k, c in index.items() if arm in c and by_cell.get(k) and not limited(arm, k[0], w)}
    if not cells:
        return []
    alpha = bonferroni_alpha(arm, w)

    def entry(reading, distress, columns, margin):
        """One reading from its cells' columns of seed values at ``margin``: the pooled spread and the seeds it
        needs, then its degrees of freedom, its upper bound and the seeds the bound needs."""
        spread, freedom = pooled_spread(columns), pooled_freedom(columns)
        bound = spread_bound(spread, freedom)
        return dict(arm=arm, reading=reading, distress=distress,
                    spread=None if spread is None else round(spread, 4), cells=len(columns),
                    seeds=seeds_needed(spread, margin, alpha), freedom=freedom,
                    spread_bound=None if bound is None else round(bound, 4),
                    seeds_assured=seeds_needed(bound, margin, alpha))

    def cost(other):
        """The level-0 real-cost reading against ``other``: the spread of each seed's yearly real saving against it,
        pooled over the cells, and the seeds that spread needs at the claim's margin."""
        columns = [[j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in by_cell[k]]
                   for k in cells if k[2] == 0]
        return entry(f"cost against {other}", 0.0, columns, abs(CLAIM_MARGIN))

    found = {level: [dips(arm, by_cell[k], by_cell.get((k[0], k[1], 0.0), [])) for k in cells if k[2] == level]
             for level in STRESS_LEVELS}

    def dip(level, other):
        """The dip reading at distress ``level`` against ``other``: the spread of the yearly dips, pooled over the
        level's cells, and the seeds that spread needs at the dip margin."""
        # The yearly dip, the series the stress leg tests (the 36-month sum over 3), against a margin of one failed
        # payment a year.
        return entry(f"dip against {other}", level, [yearly_dips(d[f"against_{other}"]) for d in found[level]],
                     DIP_MARGIN)

    return [cost("M0"), cost("S0")] + [dip(level, other) for level, other in product(STRESS_LEVELS, ("S0", "M0"))]

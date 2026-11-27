"""The seeds and the cells: which runs the map is made of.

The seed sets (development, sweep and the confirmation block fixed at the freeze, with the retired blocks), the one
definition of the confirmation count and the planner that reads the development map for it, each cell's inputs,
the selection of cells from the grid and the jobs it gives (built with the pinned PySPG catalogue), and the number of
runs in a job. The second registered run's grid of 210 cells (six outside rates, ``second_run.GRID``) is selected the
same way; the released grid of 105 cells stays the default.
"""
from itertools import chain, product

import numpy as np

from cpm_abm.catalogue import finite_catalogue
from run_economy_figures import engine_inputs
from cpm_abm.experiment.notes import (A0S, ARMS, BASE, CLAIM_ARMS, CLAIM_MARGIN, DIP_MARGIN, DISTRESS, GRID, RATES,
                                      LOW_RATES, SEED_ASSURANCE, SEED_CAP, SEED_POWER, SIDE_RATES, STRESS_LEVELS)
from cpm_abm.experiment.notes import second_run as of_second_run
from cpm_abm.experiment import second_run
from cpm_abm.experiment.statistics import (_finite, bonferroni_alpha, dips, least_passing, limited, pooled_freedom,
                                           pooled_spread, seeds_needed, spread_bound, yearly_dips)

# Seed sets. The three development seeds are for development checks only. Three blocks are retired because each was
# touched before a frozen run: 20261101 to 20261120 (a population was rebuilt on 20261101), 20261201 to 20261220 (a
# confirmation attempt ran on it and crashed, with no outcome stored or read) and 20261301 to 20261308 (the population
# size sweep ran on it; the sweep entry keeps those seeds so that run can be reproduced, and it is not a block for any
# new run). The confirmation map uses the first n seeds of a block never run, from 20261401, never used in
# development. n is 30, fixed before any confirmation seed was run or read: the planner's count
# (``confirmation_seeds``) with each reading's pooled spread taken at the upper end of its one-sided interval at
# assurance 0.8 (SEED_ASSURANCE), s x sqrt(nu / chi2_0.2(nu)) (``spread_bound``), the largest count over the
# readings, at most 100. On the development map the binding reading, the dip against M0 at 2 points, has
# s = 1.1658 over 21 cells of 3 seeds, nu = 42, so 1.293 and 30 seeds (26 at the point estimate). The confirmation
# seeds are 20261401 to 20261430. The one declared extension takes the cells the planner marks underpowered at 30 to
# 60 seeds (CONFIRMATION_EXTENSION), adding 20261431 to 20261460. CONFIRMATION_COUNT holds n. Were it None,
# SEEDS["confirmation"] would be None and a run with --seeds confirmation would be refused (``seeds_for``), so no run
# can use a placeholder count.
CONFIRMATION_START = 20261401
CONFIRMATION_LEAST, CONFIRMATION_MOST = 2, 100
CONFIRMATION_COUNT = 30               # by the rule above (docs/ANALYSIS_PLAN.md)
CONFIRMATION_EXTENSION = 60           # the one declared extension: underpowered cells at 30 run to 60 seeds


def confirmation_block(count):
    """The confirmation seeds for a frozen count n: exactly 20261401 to 20261400 + n. A count that is not a whole
    number from 2 to 100 is refused (ValueError). Example: 14 gives 20261401 to 20261414."""
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or not (
            CONFIRMATION_LEAST <= count <= CONFIRMATION_MOST):
        raise ValueError(f"The confirmation count must be a whole number from {CONFIRMATION_LEAST} to "
                         f"{CONFIRMATION_MOST}, fixed at the freeze; got {count!r}")
    return tuple(range(CONFIRMATION_START, CONFIRMATION_START + int(count)))


# The exploratory seeds: any run made after the confirmation is read uses seeds from 20261601 upward and is labelled
# exploratory. The rate cut is the first such run, on the first 30 of them, as many seeds as the confirmation map has.
EXPLORATORY_START, EXPLORATORY_COUNT = 20261601, 30
# The side seeds: the next three of the exploratory block, for the exploratory side checks made after the
# confirmation was read (the fixed cost at multiples, the custody cost, the owners' spread, the shock date, the low
# rates), each beside a base run of the same cells on the same three seeds.
SIDE_SEEDS = (20261631, 20261632, 20261633)
SEEDS = dict(development=(20261021, 20261022, 20261023),
             confirmation=None if CONFIRMATION_COUNT is None else confirmation_block(CONFIRMATION_COUNT),
             sweep=tuple(range(20261301, 20261309)),
             exploratory=tuple(range(EXPLORATORY_START, EXPLORATORY_START + EXPLORATORY_COUNT)), side=SIDE_SEEDS)
# The whole block the confirmation seeds are drawn from, at its largest (100 seeds): no other set may touch it.
CONFIRMATION_RESERVED = tuple(range(CONFIRMATION_START, CONFIRMATION_START + CONFIRMATION_MOST))


# The second run's confirmation seeds: a block never run, from 20261701 upward; the first run's
# block (20261401 to 20261460) is not reused. The count is fixed only once the three-seed map of the second run at
# 4,000 people is read, by the rule ``second_confirmation_count``: until then it is None and a confirmation run of
# the second run is refused (``seeds_for``). The block is reserved at twice the most seeds, 20261701 to 20261900, so
# the one declared extension, which takes underpowered cells to twice the count on the next seeds of the same block,
# always fits.
SECOND_CONFIRMATION_START = 20261701
SECOND_CONFIRMATION_COUNT = None
# The floor of the second run's count: no count is below 30. At 10 seeds the stricter levels'
# Wilson test of a share of seeds cannot pass even with every seed passing (10 of 10 has lower bound 0.48768 for M1
# and 0.49582 for M2); at 30 it passes with 24 of them.
SECOND_CONFIRMATION_FLOOR = 30
SECOND_CONFIRMATION_RESERVED = tuple(range(SECOND_CONFIRMATION_START,
                                           SECOND_CONFIRMATION_START + 2 * CONFIRMATION_MOST))


def second_confirmation_count(planned):
    """The second run's confirmation count: the larger of 30 (``SECOND_CONFIRMATION_FLOOR``) and the planner's count at
    the spreads' bounds (``confirmation_seeds``' seeds_assured, the count as first registered) rounded up to the next
    ten, at most the registered cap of 100.

    Examples: 8 gives 30, 26 gives 30, 30 gives 30, 33 gives 40, 44 gives 50, 95 gives 100 and 120 gives 100. None (no
    count) gives None."""
    if planned is None:
        return None
    rounded = -(-max(int(planned), CONFIRMATION_LEAST) // 10) * 10
    return int(min(max(rounded, SECOND_CONFIRMATION_FLOOR), CONFIRMATION_MOST))


def second_confirmation_block(count, extended=False):
    """The second run's confirmation seeds for a fixed count n: exactly 20261701 to 20261700 + n; with ``extended``
    the one declared extension's seeds, the next n of the same block, 20261701 + n to 20261700 + 2n. A count that is
    not a whole number from 2 to 100 is refused (ValueError).

    Examples: 40 gives 20261701 to 20261740, and its
    extension 20261741 to 20261780."""
    if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or not (
            CONFIRMATION_LEAST <= count <= CONFIRMATION_MOST):
        raise ValueError(f"The second run's confirmation count must be a whole number from {CONFIRMATION_LEAST} to "
                         f"{CONFIRMATION_MOST}, fixed from its three-seed map; got {count!r}")
    first = SECOND_CONFIRMATION_START + (int(count) if extended else 0)
    return tuple(range(first, first + int(count)))


def seeds_for(name, count=None, second=False):
    """The seeds a run named ``name`` uses: the development or sweep set, or for "confirmation" the first ``count``
    seeds of its block (``confirmation_block``; by default CONFIRMATION_COUNT). With no count the confirmation run
    is refused (ValueError), so it can never silently run a placeholder number of seeds. With ``second`` (a run of the
    second run) "confirmation" is the second run's own block (``second_confirmation_block``; by default
    SECOND_CONFIRMATION_COUNT), refused while that count is None; every other set is as in the first run."""
    if name != "confirmation":
        return SEEDS[name]
    if second:
        count = SECOND_CONFIRMATION_COUNT if count is None else count
        if count is None:
            raise ValueError("The second run's confirmation seed count is not set: SECOND_CONFIRMATION_COUNT is fixed "
                             "only once the three-seed map of the second run at 4,000 people is read, as the planner's "
                             "count at the spreads' bounds rounded up to the next ten, at most 100; nothing was run")
        return second_confirmation_block(count)
    count = CONFIRMATION_COUNT if count is None else count
    if count is None:
        raise ValueError("The confirmation seed count is not set: CONFIRMATION_COUNT is fixed at the freeze, 2 to "
                         "100; nothing was run")
    return confirmation_block(count)
# The retired blocks (above): no run may use one of these seeds again.
RETIRED_SEEDS = (tuple(range(20261101, 20261121)), tuple(range(20261201, 20261221)), tuple(range(20261301, 20261309)))


def cell_inputs(rate, fixed_cost="central"):
    """The Inputs a cell runs on: the core model's values with rho_H = r_out / 12 (the map's convention), no provider
    fee (P payments run on stablecoin rails) and the sourced fixed cost at ``fixed_cost`` ("central", "low" or "high",
    ``engine_inputs``)."""
    return engine_inputs(fixed_cost, rho_H=rate / 12)


# The stress boundary's levels (docs/ROBUSTNESS_PLAN.md, section 6): finer distress levels between the grid's 1.5 and
# 2 points, for a side run on development seeds only, beside the grid's levels and never part of the grid, so the
# full grid, the confirmation run and every reading tied to the grid's levels stay as they are. A side level is read
# against the same seed's level 0 as any level is, so a side run selects 0 too.
SIDE_DISTRESS = (0.016, 0.017, 0.018, 0.019)


def selected(r_out=RATES, a0=A0S, distress=DISTRESS):
    """The cells a run covers: the chosen values of each dimension in the grid's order, each once;
    by default the full grid. A value outside the grid is refused, so a selection never adds a cell, except a stress
    boundary level (``SIDE_DISTRESS``), which takes its place among the distress levels in order, and a rate of the
    rate cut or a low rate (``SIDE_RATES``, ``LOW_RATES``, cpm_abm.experiment.notes), or a rate of the second run
    (``second_run.RATES``), which takes its place among the outside rates. ``selected(*second_run.GRID.values())``
    is the second run's 210 cells."""
    chosen = dict(r_out=r_out, a0=a0, distress=distress)
    allowed = dict(GRID, r_out=tuple(sorted(set(GRID["r_out"] + SIDE_RATES + LOW_RATES + second_run.RATES))),
                   distress=tuple(sorted(GRID["distress"] + SIDE_DISTRESS)))
    if any(not values or set(values) - set(allowed[name]) for name, values in chosen.items()):
        raise ValueError(f"Select one or more values of each dimension of the grid {GRID}, or among the distress levels "
                         f"a stress boundary level {SIDE_DISTRESS}, or among the outside rates a rate of the rate cut "
                         f"{SIDE_RATES} or a low rate {LOW_RATES}")
    return {name: tuple(value for value in allowed[name] if value in chosen[name]) for name in GRID}


def tasks_for(seeds, n, selection=GRID, returned=False):
    """Every job of the selected cells (``selected``, by default the full grid): their cross (a PySPG catalogue, last
    dimension fastest), then with the full grid the baseline cell without distress under the recirculation
    convention. With ``returned`` (``--lenders-interest returned``) every job runs with outside
    lenders' interest returned to households, and no extra set is added."""
    sweep = finite_catalogue(dict(**{name: list(values) for name, values in selection.items()}, seed=list(seeds)))
    tasks = [(p["r_out"], p["a0"], p["distress"], p["seed"], n, returned) for p in sweep]
    # A selection of cells runs those cells only, without the recirculation set; a map with lenders' interest returned
    # over the whole grid has no separate set to add.
    if selection != GRID or returned:
        return tasks
    return tasks + [(p["r_out"], p["a0"], 0.0, p["seed"], n, True)
                    for p in finite_catalogue(dict(r_out=[BASE[0]], a0=[BASE[1]], seed=list(seeds)))]


def runs_in(task, s0_only=False):
    """Population runs in one job: S0 and each arm beside it, or with ``s0_only`` S0's run alone."""
    return 1 if s0_only else 1 + len(ARMS)


def confirmation_seeds(index, by_cell, w):
    """The confirmation seed count from the development map's spread: for each claim arm, the level-0 cost reading
    (clause (b)'s savings against M0 and against S0, margin $2) with its spread pooled across the level-0 cells, and at
    each distress level the dip (against S0 and against M0, margin one failed payment) with its spread pooled across
    that level's cells, each at the arm's Bonferroni level and 80% power (``seeds_needed``); the largest is taken, at
    most 100. The dip's spread is the yearly dip's (the 36-month sum over 3), the series the stress leg tests against
    one failed payment a year. Beside that count, the assured count (the rule CONFIRMATION_COUNT follows): the same
    largest count with each reading's spread at the upper end of its one-sided interval at SEED_ASSURANCE
    (``spread_bound``, the reading's seeds_assured), at most 100. CONFIRMATION_COUNT is not changed here; it is stored
    beside the planner's counts (confirmation_seeds_now).

    Examples: a pooled cost spread of $4 at M1's level needs 65 seeds; the development map's binding reading, a dip
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
    seeds_assured = None if most_assured is None else int(min(most_assured, SEED_CAP))
    out = dict(readings=readings, largest=largest, seeds=None if most is None else int(min(most, SEED_CAP)),
               capped=bool(most is not None and most > SEED_CAP), cap=SEED_CAP, power=SEED_POWER,
               confirmation_seeds_now=CONFIRMATION_COUNT, largest_assured=assured, seeds_assured=seeds_assured,
               capped_assured=bool(most_assured is not None and most_assured > SEED_CAP), assurance=SEED_ASSURANCE)
    if not of_second_run(w):
        return out
    # A map of the second run: its own count now (None until its three-seed map is read), and
    # the count its rule gives from this map, the registered count rounded up to the next ten, on its own block.
    rounded = second_confirmation_count(seeds_assured)
    out.update(confirmation_seeds_now=SECOND_CONFIRMATION_COUNT, second_run=dict(
        registered=seeds_assured, rounded=rounded, extension=None if rounded is None else 2 * rounded,
        first_seed=SECOND_CONFIRMATION_START,
        rule="the larger of 30 and the registered count (seeds_assured) rounded up to the next ten, at most 100; the "
             "one declared extension takes underpowered cells to twice it on the next seeds of the same block",
        attainable=_attainable(rounded, w), by_seed_freedom=_by_seed_freedom(readings)))
    return out


def _attainable(count, w):
    """For a seed count, the fewest passing seeds a Wilson reading of a share of seeds needs for its lower bound to be
    above one half (``least_passing``), at 95% and at each claim arm's stricter level: the decisions the count can
    reach. None marks a level that no number of passing seeds reaches.

    Examples: at 30 seeds, 21 at 95% and 24 at M1's 0.05 / 42 and at M2's 0.05 / 35; at 10 seeds, 9 at 95% and none at
    either stricter level."""
    levels = {"95%": 0.05, **{arm: bonferroni_alpha(arm, w) for arm in CLAIM_ARMS}}
    return dict(count=count, least_passing={name: None if count is None else least_passing(count, alpha)
                                            for name, alpha in levels.items()},
                alpha={name: round(alpha, 6) for name, alpha in levels.items()})


def _by_seed_freedom(readings):
    """The count the planner would give were each reading's pooled spread given one degree of freedom a seed (the seeds
    of a cell less one) in place of one a seed and cell, its upper bound and the seeds that bound needs read the same
    way, and that count by the rule (``second_confirmation_count``); reported beside the count, changing nothing. A
    seed's draw is shared by every cell of the grid, so the cells' spreads are not independent.

    Example: three seeds give two degrees of freedom, and a spread of 1 has the bound sqrt(2 / chi2_0.2(2)) = 2.117 in
    place of 1.109 at 42."""
    counted = [r for r in readings if r.get("seeds_assured_by_seed") is not None]
    largest = max(counted, key=lambda r: r["seeds_assured_by_seed"], default=None)
    seeds = None if largest is None else int(min(largest["seeds_assured_by_seed"], SEED_CAP))
    return dict(seeds_assured=seeds, rounded=second_confirmation_count(seeds),
                reading=None if largest is None else dict(arm=largest["arm"], reading=largest["reading"],
                                                          distress=largest["distress"]),
                note="reported beside the count and read by nothing: the pooled spread's bound at one degree of "
                     "freedom a seed (the seeds of a cell less one) in place of one a seed and cell")


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
        out = dict(arm=arm, reading=reading, distress=distress,
                   spread=None if spread is None else round(spread, 4), cells=len(columns),
                   seeds=seeds_needed(spread, margin, alpha), freedom=freedom,
                   spread_bound=None if bound is None else round(bound, 4),
                   seeds_assured=seeds_needed(bound, margin, alpha))
        if of_second_run(w):
            # In a map of the second run, beside them: the bound with one degree of freedom a
            # seed, the seeds of a cell less one, and the seeds it needs (``_by_seed_freedom``).
            per_seed = max((part.size for part in map(_finite, columns)), default=0) - 1
            by_seed = spread_bound(spread, per_seed)
            out.update(freedom_by_seed=per_seed, spread_bound_by_seed=None if by_seed is None else round(by_seed, 4),
                       seeds_assured_by_seed=seeds_needed(by_seed, margin, alpha))
        return out

    def cost(other):
        """The level-0 real-cost reading against ``other``: the spread of each seed's yearly real saving against it,
        pooled over the cells, and the seeds that spread needs at the claim's margin."""
        columns = [[j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in by_cell[k]]
                   for k in cells if k[2] == 0]
        return entry(f"cost against {other}", 0.0, columns, abs(CLAIM_MARGIN))

    found = {level: [dips(arm, by_cell[k], by_cell.get((k[0], k[1], 0.0), []), w) for k in cells if k[2] == level]
             for level in STRESS_LEVELS}

    def dip(level, other):
        """The dip reading at distress ``level`` against ``other``: the spread of the yearly dips, pooled over the
        level's cells, and the seeds that spread needs at the dip margin."""
        # The yearly dip, the series the stress leg tests (the 36-month sum over 3), against a margin of one failed
        # payment a year.
        return entry(f"dip against {other}", level,
                     [yearly_dips(d[f"against_{other}"], d["years"]) for d in found[level]],
                     DIP_MARGIN)

    return [cost("M0"), cost("S0")] + [dip(level, other) for level, other in product(STRESS_LEVELS, ("S0", "M0"))]

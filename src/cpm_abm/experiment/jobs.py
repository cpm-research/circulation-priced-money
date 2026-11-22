"""Running the jobs: one job, and many in parallel.

A job is one (r_out, a0, distress, seed, convention) with every arm on common random numbers. The faster path shares
S0 across a0 through a temporary cache on disk and forks each arm at the distress year from one prefix; ``preflight``
checks both bit for bit against direct runs before a map. Every function handed to a worker lives here, so a worker
reaches it by its module path.
"""
import copy
from concurrent.futures import FIRST_EXCEPTION, ProcessPoolExecutor, wait
from dataclasses import replace
from functools import partial
from itertools import chain
from pathlib import Path
import os
import pickle
import sys
import tempfile
import time

import numpy as np

from cpm_abm.economy_abm import CRYPTO_SHARE, Economy, _World, simulate
from run_economy_figures import windows
from cpm_abm.experiment.notes import A0S, ARMS, BASE, DISTRESS
from cpm_abm.experiment.grid import SEEDS, cell_inputs
from cpm_abm.experiment.accounts import (by_chronic, by_class, by_quintile, card_bridging, cash_check, ewa_report,
                                         failure_report, liquidity, measures, monthly, real_part, transfers)
from cpm_abm.experiment.gains import arm_row
from cpm_abm.experiment.store import compacted

def job(args, template=None, s0_only=False, fixed_cost="central"):
    """One (r_out, a0, distress, seed, convention) job: S0, M0, U, M1 and M2 on common random numbers, or with
    ``s0_only`` S0 alone, without arm rows (the S0 check of the 3 Nov round, which runs S0 only).

    ``template`` replaces the default Economy (tests use a short one); the seed, distress level and convention are set
    on it. ``fixed_cost`` is the pool's sourced fixed cost level (``cell_inputs``).
    """
    rate, a0, distress, seed, n, recirculated = args
    inputs = cell_inputs(rate, fixed_cost)
    # The runner's crypto collateral share (``CRYPTO_SHARE``, 0: decided 12 Nov, collateral lending by Compound III
    # is not run), as in ``main``.
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=distress,
                lender_income_recirculated=recirculated)
    ran = ("S0",) if s0_only else ("S0",) + ARMS
    runs = dict(map(lambda arm: (arm, simulate(inputs, a0, w, arm)), ran))
    return assemble(args, runs, template, s0_only)


def assemble(args, runs, template=None, s0_only=False):
    """A job's records from its runs (``runs``: arm to run), however they were made (``job``, ``cell_task``)."""
    rate, a0, distress, seed, n, recirculated = args
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=distress,
                lender_income_recirculated=recirculated)
    ran = ("S0",) if s0_only else ("S0",) + ARMS
    rows = dict(map(lambda arm: (arm, arm_row(runs[arm], runs["S0"], runs["M0"], a0, w, runs["U"])), ran[1:]))
    after = slice(w.burn_in, w.burn_in + w.months)
    s0_series = runs["S0"]["series"]
    _, w2 = windows(runs["S0"])
    # Failure counts (3 Nov): every arm's monthly series and spread of fee units, and with the development seeds every
    # arm's fees and counts by person and month; the map's seed sets store the monthly series and spread only
    # (decided 4 Nov). The seed sets share no seed, so the seed names its set.
    by_payer = seed in SEEDS["development"]
    failures = dict(map(lambda arm: (arm, failure_report(runs[arm], w, by_payer)), ran))
    # With the development seeds, S0's buffer chosen at dealing by person and month after launch (the 3 Nov review),
    # beside its fees by payer: dense, a row a month, in months of mean spending. Only S0 and only those seeds
    # (decided 4 Nov).
    if by_payer:
        failures["S0"]["buffers"] = np.round(runs["S0"]["buffers"][after], 6).tolist()
    return dict(r_out=rate, a0=a0, distress=distress, seed=seed, recirculated=recirculated, arms=rows,
                S0=dict(failures_pct=float(s0_series["failure_share"][w2].mean() * 100),
                        merchant_fees_pct=float(s0_series["merchant_fees"][w2].mean() * 100),
                        real_part=real_part(runs["S0"], w), transfers=transfers(runs["S0"], w),
                        cash=cash_check(runs["S0"], w), earned_wage=ewa_report(runs["S0"], w),
                        chronic=by_chronic(runs["S0"], w), card_bridging=card_bridging(runs["S0"], w),
                        liquidity=liquidity(runs["S0"], w), by_class=by_class(runs["S0"], w),
                        **by_quintile(runs["S0"], w)),
                measures=dict(map(lambda arm: (arm, measures(runs[arm], w)), ran)),
                monthly=dict(map(lambda arm: (arm, monthly(runs[arm], w)), ran)),
                failure_counts=failures)


# The 5 Nov speed review: the same jobs with less work, bit for bit. (1) The engine reads the distress level only in
# ``_World._layoffs``, from the month the distress year starts, on a layoff stream of its own per month, so every
# level's run is the same up to then: each arm runs those months once and each level continues from a deep copy
# (``prefix``, ``finish``). (2) S0 reads a0 nowhere (a0 enters only at launch, outside S0), so S0 runs once per r_out,
# seed and convention and serves every a0, its ``a0`` key set to the cell's; its runs wait on disk, in a temporary
# directory removed at the end (``run_tasks``), for the cell tasks. Both are checked bit for bit on the engine as it
# stands before every map (``preflight``).
def fork_month(w):
    """The first month whose run depends on the distress level."""
    return w.burn_in + w.distress_start


def prefix(inputs, a0, w, arm):
    """A world of ``arm`` run through every month before the distress year (which no level changes)."""
    world = _World(inputs, a0, w, arm)
    for month in range(min(fork_month(w), world.total)):
        world.month(month)
    return world


def finish(world, w, level):
    """Finish a ``prefix`` world at one distress level: the records ``simulate`` returns at that level."""
    first = min(fork_month(w), world.total)
    world.economy = replace(w, distress=level)
    step = world.month
    world.month = lambda month: None if month < first else step(month)   # run() maps self.month over every month
    try:
        return world.run()
    finally:
        del world.month


def forked(inputs, a0, w, arm, levels):
    """One ``prefix`` and every level finished from a copy of it: {level: run}."""
    base = prefix(inputs, a0, w, arm)
    return {level: finish(base if k == len(levels) - 1 else copy.deepcopy(base), w, level)
            for k, level in enumerate(levels)}


def _s0_file(cache, rate, seed, level, recirculated):
    """Where in ``cache`` the pickled S0 run of one r_out, seed, distress level and lenders' interest convention is
    kept."""
    return Path(cache) / f"s0_{rate}_{seed}_{level}_{int(recirculated)}.pkl"


def s0_task(args, template, cache, fixed_cost="central"):
    """S0 at every level of one (r_out, seed, convention), each run pickled into ``cache`` for the cell tasks."""
    rate, seed, n, recirculated, levels = args
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=levels[0],
                lender_income_recirculated=recirculated)
    try:
        for level, run in forked(cell_inputs(rate, fixed_cost), A0S[0], w, "S0", levels).items():
            target = _s0_file(cache, rate, seed, level, recirculated)
            with target.with_suffix(".tmp").open("wb") as out:
                pickle.dump(run, out, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(target.with_suffix(".tmp"), target)
    except BaseException:
        for level in levels:   # the cell tasks waiting on these runs stop instead of waiting for ever
            _s0_file(cache, rate, seed, level, recirculated).with_suffix(".err").touch()
        raise
    return len(levels)


def _wait_for_s0(target):
    """Wait until S0's run ``target`` is on disk (``s0_task`` writes it); raise if S0's task failed."""
    while not target.exists():   # S0's tasks go first and are shorter, so this waits only in a short map
        if target.with_suffix(".err").exists():
            raise RuntimeError(f"S0's task for {target.name} failed")
        time.sleep(0.5)


def cell_task(args, template, cache, fixed_cost="central"):
    """M0, U, M1 and M2 of one (r_out, a0, seed, convention) at every level, each arm forked, and S0's run from the
    cache with this a0: the job of each level, as ``job`` returns it."""
    rate, a0, seed, n, recirculated, levels = args
    inputs = cell_inputs(rate, fixed_cost)
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=levels[0],
                lender_income_recirculated=recirculated)
    worlds = {arm: prefix(inputs, a0, w, arm) for arm in ARMS}
    jobs = []
    for k, level in enumerate(levels):
        last = k == len(levels) - 1
        runs = {arm: finish(world if last else copy.deepcopy(world), w, level) for arm, world in worlds.items()}
        target = _s0_file(cache, rate, seed, level, recirculated)
        _wait_for_s0(target)
        with target.open("rb") as source:
            runs["S0"] = dict(pickle.load(source), a0=a0)
        jobs.append(assemble((rate, a0, level, seed, n, recirculated), runs, template))
    return jobs


def grouped(tasks):
    """The jobs of ``tasks`` (``tasks_for``) grouped: S0's by (r_out, seed, convention) and the cells' by (r_out, a0,
    seed, convention), each with its levels in the grid's order."""
    s0, cells = {}, {}
    for rate, a0, level, seed, n, recirculated in tasks:
        levels = s0.setdefault((rate, seed, n, recirculated), [])
        if level not in levels:
            levels.append(level)
        cells.setdefault((rate, a0, seed, n, recirculated), []).append(level)
    return [(*key, tuple(v)) for key, v in s0.items()], [(*key, tuple(v)) for key, v in cells.items()]


def run_tasks(tasks, template, workers, fixed_cost="central"):
    """Every job of ``tasks`` in their order, as ``job`` would return them, each job's failure counts encoded where it
    ran (``compacted``): S0's tasks first, then the cells'. A task that fails stops the run, naming its cell and seed
    (``gathered``)."""
    s0_tasks, cell_tasks = grouped(tasks)
    convention = lambda flag: "lenders' interest returned" if flag else "lenders' interest leaving"
    with tempfile.TemporaryDirectory(prefix="cpm_s0_") as cache, ProcessPoolExecutor(max_workers=workers) as pool:
        heads = {pool.submit(s0_task, t, template, cache, fixed_cost):
                 f"S0 at r_out {t[0]}, seed {t[1]}, distress {list(t[4])}, {convention(t[3])}" for t in s0_tasks}
        bodies = {pool.submit(_stored, cell_task, t, template, cache, fixed_cost):
                  f"cell r_out {t[0]}, a0 {t[1]}, distress {list(t[5])}, seed {t[2]}, {convention(t[4])}"
                  for t in cell_tasks}
        done = gathered(pool, {**heads, **bodies})
        found = {(j["r_out"], j["a0"], j["distress"], j["seed"], j["recirculated"]): j
                 for j in chain.from_iterable(map(done.get, bodies))}
    return [found[(rate, a0, level, seed, recirculated)] for rate, a0, level, seed, _, recirculated in tasks]


def _stored(task, *args, **kwargs):
    """``task``'s job or jobs with each job's failure counts encoded (``compacted``), run in a worker, so a job crosses
    to the parent with its largest record as one string."""
    return compacted(task(*args, **kwargs))


def gathered(pool, named):
    """The results of the futures ``named`` (future to the job it runs, by cell and seed), each future's result by
    future. The first task to fail stops the run: its name and error are printed at once, the tasks not yet started
    are cancelled, and a RuntimeError naming the job is raised from the worker's error."""
    done, _ = wait(named, return_when=FIRST_EXCEPTION)
    failed = [future for future in named if future in done and future.exception() is not None]
    if failed:
        error = failed[0].exception()
        message = f"Job failed: {named[failed[0]]}: {type(error).__name__}: {error}"
        print(message, file=sys.stderr, flush=True)
        pool.shutdown(wait=False, cancel_futures=True)
        raise RuntimeError(message) from error
    return {future: future.result() for future in named}


def same(a, b):
    """Bit for bit: arrays by dtype, shape and bytes, floats by bits, containers element by element."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return (isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and a.dtype == b.dtype and a.shape == b.shape
                and (all(map(same, a.ravel(), b.ravel())) if a.dtype == object else a.tobytes() == b.tobytes()))
    if isinstance(a, dict):
        return isinstance(b, dict) and list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, float):
        return type(b) is float and np.float64(a).tobytes() == np.float64(b).tobytes()
    return type(a) is type(b) and a == b


def preflight_arm(arm, template, fixed_cost="central"):
    """One arm's check on a small economy whose distress year comes early: forked runs equal direct runs at the lowest
    and highest level, and for S0 the run at the lowest a0 equals the run at the highest with its a0 set."""
    w = replace(template, n=100, months=14, distress_start=4, distress_length=6, seed=SEEDS["development"][0])
    inputs, levels = cell_inputs(BASE[0], fixed_cost), (DISTRESS[0], DISTRESS[-1])
    got = forked(inputs, A0S[0], w, arm, levels)
    ok = all(same(got[level], simulate(inputs, A0S[0], replace(w, distress=level), arm)) for level in levels)
    if arm == "S0":
        ok = ok and same(dict(got[levels[-1]], a0=A0S[-1]), simulate(inputs, A0S[-1], replace(w, distress=levels[-1]),
                                                                     "S0"))
    return ok


def preflight(template, workers, fixed_cost="central"):
    """Refuse to run the shared S0 and the distress fork unless both are bit-identical on the engine as it stands."""
    with ProcessPoolExecutor(max_workers=min(workers, 1 + len(ARMS))) as pool:
        results = dict(zip(("S0",) + ARMS, pool.map(partial(preflight_arm, template=template, fixed_cost=fixed_cost),
                                                    ("S0",) + ARMS)))
    if not all(results.values()):
        raise RuntimeError(f"The shared S0 or the distress fork no longer matches direct runs: {results}; run --plain")

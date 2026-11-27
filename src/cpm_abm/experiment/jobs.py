"""Running the jobs: one job, and many in parallel.

A job is one (r_out, a0, distress, seed, convention) with every arm on common random numbers. The faster path shares
S0 across a0 through a temporary cache on disk, starts each other arm of every a0 from one state of that arm at launch
kept in the same cache (the burn-in computed once) and forks each arm at the distress year from
one prefix; ``preflight`` checks all three bit for bit against direct runs before a map. A job holds one whole run
at a time: each prefix waits compressed on disk and each level's runs are made, read and let go one after another
(``levels_of``, ``assemble``), so a 25-year job at 4,000 people peaks near 1 GB, not 7. Every function handed to a
worker lives here, so a worker reaches it by its module path.
"""
import copy
from concurrent.futures import FIRST_EXCEPTION, ProcessPoolExecutor, wait
from dataclasses import replace
from functools import partial
from itertools import chain, product
from pathlib import Path
import gzip
import os
import pickle
import sys
import tempfile
import time

import numpy as np

from cpm_abm.economy_abm import CRYPTO_SHARE, Economy, _World, launch_state, resume, simulate
from cpm_abm.engine.population import distress_calendar
from run_economy_figures import settled, window_names, windows
from cpm_abm.experiment.notes import A0S, ARMS, BASE, DISTRESS
from cpm_abm.experiment.grid import SEEDS, cell_inputs
from cpm_abm.experiment.accounts import (by_chronic, by_class, by_quintile, card_bridging, cash_check, ewa_report,
                                         failure_report, liquidity, measures, monthly, real_part, transfers)
from cpm_abm.experiment.gains import WINDOW_MEANS, arm_row, payout_by_group
from cpm_abm.experiment.notes import conserves_money
from cpm_abm.experiment.store import compacted

S0_MEANS = ("failures_pct", "merchant_fees_pct")   # S0's means of W2, which a long run stores by window too

def job(args, template=None, s0_only=False, fixed_cost="central"):
    """One (r_out, a0, distress, seed, convention) job: S0, M0, U, M1 and M2 on common random numbers, or with
    ``s0_only`` S0 alone, without arm rows.

    ``template`` replaces the default Economy (tests use a short one); the seed, distress level and convention are set
    on it. ``fixed_cost`` is the pool's sourced fixed cost level (``cell_inputs``).
    """
    rate, a0, distress, seed, n, recirculated = args
    inputs = cell_inputs(rate, fixed_cost)
    # The runner's crypto collateral share (``CRYPTO_SHARE``, 0: collateral lending by Compound III is not run), as
    # in ``main``.
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=distress,
                lender_income_recirculated=recirculated)
    ran = ("S0",) if s0_only else ("S0",) + ARMS
    # Each run is made when ``assemble`` asks for it, so the job never holds every run at once.
    return assemble(args, ((arm, simulate(inputs, a0, w, arm)) for arm in ran), template, s0_only)


def assemble(args, runs, template=None, s0_only=False):
    """A job's records from its runs, however they were made (``job``, ``cell_task``): ``runs`` maps each arm to its
    run, or yields (arm, run) pairs in the order S0, M0, U, M1, M2, each made only when it is asked for.

    The records are taken one run at a time and each run is let go once its own are taken, so a job holds one whole
    run and, of S0, M0 and U, only what the later arms' rows read of them (``_kept``): the same records from the same
    arrays, in the same order of keys."""
    rate, a0, distress, seed, n, recirculated = args
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=distress,
                lender_income_recirculated=recirculated)
    ran = ("S0",) if s0_only else ("S0",) + ARMS
    after = slice(w.burn_in, w.burn_in + w.months)
    # Failure counts: every arm's monthly series and spread of fee units, and with the development seeds every arm's
    # fees and counts by person and month; the map's seed sets store the monthly series and spread only. The seed sets
    # share no seed, so the seed names its set.
    by_payer = seed in SEEDS["development"]
    pairs = iter(runs.items() if isinstance(runs, dict) else runs)
    kept, rows, failures, measured, months = {}, {}, {}, {}, {}
    for arm in ran:
        named, run = next(pairs)
        if named != arm:
            raise ValueError(f"A job's runs come in the order {list(ran)}; got {named} in place of {arm}")
        if arm == "S0":
            s0_series = run["series"]
            _, w2 = windows(run)
            s0 = dict(failures_pct=float(s0_series["failure_share"][w2].mean() * 100),
                      merchant_fees_pct=float(s0_series["merchant_fees"][w2].mean() * 100),
                      real_part=real_part(run, w), transfers=transfers(run, w),
                      cash=cash_check(run, w), earned_wage=ewa_report(run, w),
                      chronic=by_chronic(run, w), card_bridging=card_bridging(run, w),
                      liquidity=liquidity(run, w), by_class=by_class(run, w),
                      **by_quintile(run, w))
            if conserves_money(w):
                # Who pays and who receives in banks too, from S0's own payout, taken before the run is let go.
                s0["payout_by_group"] = payout_by_group(run, run, w)
            if settled(run["economy"]):
                # In a long run S0's two window means for each window by its years as well.
                s0["by_window"] = {name: {key: WINDOW_MEANS[key](s0_series, span) for key in S0_MEANS}
                                   for name, span in zip(window_names(run["economy"]), windows(run))}
        else:
            # M0 is read against S0 alone, so its row needs no U; U is read only by M1's row.
            rows[arm] = arm_row(run, kept["S0"], run if arm == "M0" else kept["M0"], a0, w, kept.get("U"))
        failures[arm] = failure_report(run, w, by_payer)
        # With the development seeds, S0's buffer chosen at dealing by person and month after launch, beside its fees by
        # payer: dense, a row a month, in months of mean spending. Only S0 and only those seeds.
        if arm == "S0" and by_payer:
            failures["S0"]["buffers"] = np.round(run["buffers"][after], 6).tolist()
        measured[arm], months[arm] = measures(run, w), monthly(run, w)
        if arm in ("S0", "M0", "U"):
            kept[arm] = _kept(run)
        del run
    return dict(r_out=rate, a0=a0, distress=distress, seed=seed, recirculated=recirculated, arms=rows, S0=s0,
                measures=measured, monthly=months, failure_counts=failures)


# What a later arm's row reads of the S0, M0 and U runs (``arm_row``: the gains, the split, the paired differences
# and the harm test): their series, end and launch wealth, the purchase records, the two cash-advance records of
# ``credit``, the population and the chronic flags, and beside them, as fail_shares and declined_shares, each person's
# failed and declined shares a month from ``failure_counts`` (each group's own payments that did not complete, which a
# run that conserves money stores). Every other record of those runs is let go once their own
# records are taken; a read of one raises instead of finding nothing.
KEPT = ("arm", "series", "wealth", "purchases", "population", "chronic")
KEPT_CREDIT = ("fees_advance", "interest_advance")


class _Released(dict):
    """A run's records kept for the later arms' rows (``_kept``); a record let go raises a KeyError naming it,
    through ``get`` too, so a reading that came to need it would stop the job and not read a default."""

    def __init__(self, records, released):
        super().__init__(records)
        self.released = frozenset(released)

    def __missing__(self, key):
        raise KeyError(f"{key!r} was let go once its own records were taken (``KEPT`` in experiment/jobs.py)")

    def get(self, key, default=None):
        return self[key] if key in self.released else super().get(key, default)


def _kept(run):
    """The records of ``run`` a later arm's row reads (``KEPT``, ``KEPT_CREDIT``, fail_shares and declined_shares),
    the same arrays, not copies."""
    credit = run["credit"]
    records = {key: run[key] for key in KEPT}
    records["credit"] = _Released({key: credit[key] for key in KEPT_CREDIT}, set(credit) - set(KEPT_CREDIT))
    records["fail_shares"] = run["failure_counts"]["fail_shares"]
    records["declined_shares"] = run["failure_counts"]["declined_shares"]
    return _Released(records, set(run) - set(records))


# The same jobs with less work, bit for bit. (1) The engine reads the distress level only in ``_World._layoffs``, from
# the month the distress year starts, on a layoff stream of its own per month, so every level's run is the same up to
# then: each arm runs those months once and each level continues from a deep copy (``prefix``, ``finish``). (2) S0 reads
# a0 nowhere (a0 enters only at launch, outside S0), so S0 runs once per r_out, seed and convention and serves every a0,
# its ``a0`` key set to the cell's; its runs wait on disk, in a temporary directory removed at the end (``run_tasks``),
# for the cell tasks. Both are checked bit for bit on the engine as it stands before every map (``preflight``).
def fork_month(w):
    """The first month whose run depends on the distress level: the dated distress year's first month, or under
    random distress years the first month of the first, and the run's end when it meets none."""
    if w.distress_dates == "random":
        inside = np.flatnonzero(distress_calendar(w))
        return int(inside[0]) if inside.size else w.burn_in + w.months
    return w.burn_in + w.distress_start


# (3) The burn-in computed once: the engine reads a0 only at launch, so each arm's world at launch (``launch_state``)
# serves every a0 and every distress level of its r_out, seed and convention, and a run of any of them continues from a
# copy (``resume``), which refuses a state opened with other Inputs or another Economy but for the distress level. The
# arms set their own terms when the world is opened and some enter the burn-in, so each arm has its own state; S0 runs
# once per r_out, seed and convention already and keeps its own burn-in.
def prefix(inputs, a0, w, arm, launched=None, keep=True):
    """A world of ``arm`` run through every month before the distress year (which no level changes): from month 0,
    or with ``launched``, a state of ``arm`` at launch (``launch_state``), from launch, on a copy of the state with
    ``keep`` and on the state itself without (``resume``)."""
    if launched is not None and launched.arm != arm:
        raise ValueError(f"A state at launch of {launched.arm} cannot start a run of {arm}")
    world = _World(inputs, a0, w, arm) if launched is None else resume(launched, inputs, a0, w, keep)
    for month in range(world.resume_at, min(fork_month(w), world.total)):
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


def forked(inputs, a0, w, arm, levels, launched=None):
    """One ``prefix`` (from ``launched``, a state of ``arm`` at launch, when given) and every level finished from a
    copy of it: {level: run}."""
    base = prefix(inputs, a0, w, arm, launched)
    return {level: finish(base if k == len(levels) - 1 else copy.deepcopy(base), w, level)
            for k, level in enumerate(levels)}


def _save(thing, target):
    """Pickle ``thing`` into the file ``target``, compressed as it is written, so no second copy of it is made in
    memory; the file appears whole or not at all."""
    part = target.with_name(target.name + ".tmp")
    with gzip.open(part, "wb", compresslevel=1) as out:
        pickle.dump(thing, out, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(part, target)


def _load(target):
    """What ``_save`` wrote into ``target``."""
    with gzip.open(target, "rb") as source:
        return pickle.load(source)


def levels_of(inputs, a0, w, arm, levels, launched=None, keep=True, folder=None):
    """``forked`` one level at a time: (level, run) for each of ``levels``, each made when it is asked for, from
    ``launched`` (a state of ``arm`` at launch, used in place with ``keep`` False, ``prefix``, or a function that
    reads one, called only when the first level is asked for) when given. The prefix
    waits compressed in a file in a temporary folder inside ``folder`` (the system's without it), not as a live copy,
    and each level but the first continues from a world read back from it, which is the prefix as a copy of it is.
    So no world is live here between levels, and a run is gone once its caller lets it go."""
    with tempfile.TemporaryDirectory(prefix="cpm_prefix_", dir=folder) as kept:
        target = Path(kept) / "prefix.pkl.gz"
        held = [prefix(inputs, a0, w, arm, launched() if callable(launched) else launched, keep)]
        if len(levels) > 1:
            _save(held[0], target)
        for level in levels:
            # The world is taken out of ``held`` as it is finished, so this frame keeps no run between levels.
            yield level, finish(held.pop() if held else _load(target), w, level)


def _s0_file(cache, rate, seed, level, recirculated):
    """Where in ``cache`` the pickled S0 run of one r_out, seed, distress level and lenders' interest convention is
    kept, compressed (``_save``)."""
    return Path(cache) / f"s0_{rate}_{seed}_{level}_{int(recirculated)}.pkl.gz"


def s0_task(args, template, cache, fixed_cost="central"):
    """S0 at every level of one (r_out, seed, convention), each run pickled into ``cache`` for the cell tasks."""
    rate, seed, n, recirculated, levels = args
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=levels[0],
                lender_income_recirculated=recirculated)
    try:
        # One level at a time, each run written and let go before the next is made.
        for level, run in levels_of(cell_inputs(rate, fixed_cost), A0S[0], w, "S0", levels, folder=cache):
            _save(run, _s0_file(cache, rate, seed, level, recirculated))
            del run
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


def _launch_file(cache, rate, seed, arm, recirculated):
    """Where in ``cache`` the pickled state at launch of one arm, r_out, seed and lenders' interest convention is
    kept, compressed (``launch_task``); the population and every other setting are the map's own, the same for every
    task."""
    return Path(cache) / f"launch_{arm}_{rate}_{seed}_{int(recirculated)}.pkl.gz"


def launch_task(args, template, cache, fixed_cost="central"):
    """The state at launch of one arm of one (r_out, seed, convention) (``launch_state``), pickled into ``cache`` for
    the cell tasks of every a0. It is opened at the first of ``levels``, a level it never reads."""
    rate, seed, n, recirculated, arm, levels = args
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=levels[0],
                lender_income_recirculated=recirculated)
    target = _launch_file(cache, rate, seed, arm, recirculated)
    try:
        state = launch_state(cell_inputs(rate, fixed_cost), w, arm)
        # Compressed: the records of the months after launch are still empty, so the file is a twentieth of the
        # state's size (123 MB to 6 MB at 4,000 people and 66 months) and the bytes read back are the same.
        _save(state, target)
    except BaseException:
        target.with_suffix(".err").touch()   # the cell tasks waiting on this state stop instead of waiting for ever
        raise
    return 1


def _launched(cache, rate, seed, arm, recirculated):
    """The state at launch ``launch_task`` keeps for one arm, r_out, seed and convention, once it is on disk."""
    target = _launch_file(cache, rate, seed, arm, recirculated)
    _wait_for_s0(target)
    return _load(target)


def cell_task(args, template, cache, fixed_cost="central", s0_cache=None):
    """M0, U, M1 and M2 of one (r_out, a0, seed, convention) at every level, each arm started from its state at launch
    in the cache and forked, and S0's run from the cache (or from ``s0_cache``, S0's shared folder, ``run_tasks``) with
    this a0: the job of each level, as ``job`` returns it."""
    rate, a0, seed, n, recirculated, levels = args
    inputs = cell_inputs(rate, fixed_cost)
    w = replace(template or Economy(n=n, crypto_share=CRYPTO_SHARE), seed=seed, distress=levels[0],
                lender_income_recirculated=recirculated)
    # Each state is read fresh from disk for this cell alone, so it is run in place of a copy. Each arm's levels come
    # one at a time (``levels_of``), its prefix waiting compressed on disk, and each level's runs are made in the order
    # ``assemble`` takes their records, so the cell holds one whole run at a time.
    arms = {arm: levels_of(inputs, a0, w, arm, levels, partial(_launched, cache, rate, seed, arm, recirculated),
                           keep=False, folder=cache) for arm in ARMS}
    try:
        return [assemble((rate, a0, level, seed, n, recirculated),
                         _level_runs(cache, rate, a0, seed, recirculated, level, arms, s0_cache, w), template)
                for level in levels]
    finally:
        for runs in arms.values():
            runs.close()   # their prefixes' files go now, not when the cache does


def _level_runs(cache, rate, a0, seed, recirculated, level, arms, s0_cache=None, w=None):
    """One level's runs in the order ``assemble`` takes them: S0's from the cache with this a0, then the next run of
    each arm's ``levels_of``, each made when it is asked for. From ``s0_cache``, S0's run may have been made under
    another saver reading, which S0 never reads, so its Economy is given this map's reading (of ``w``)."""
    target = _s0_file(s0_cache or cache, rate, seed, level, recirculated)
    _wait_for_s0(target)
    run = dict(_load(target), a0=a0)
    if s0_cache is not None:
        run["economy"] = replace(run["economy"], entry_reads=w.entry_reads)
    yield "S0", run
    del run
    for arm, runs in arms.items():
        yield arm, _at(level, *next(runs))


def _at(level, got, run):
    """``run``, made at the distress level ``got``, which must be ``level``."""
    if got != level:
        raise ValueError(f"A run at distress {got} came in place of one at {level}")
    return run


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


def run_tasks(tasks, template, workers, fixed_cost="central", s0_cache=None):
    """Every job of ``tasks`` in their order, as ``job`` would return them, each job's failure counts encoded where it
    ran (``compacted``): S0's tasks and the arms' states at launch first (one an arm, r_out, seed and convention),
    then the cells'. A task that fails stops the run, naming its cell and seed (``gathered``).

    ``s0_cache``, a folder that outlives the call, keeps S0's runs for another map whose Economy differs from this one
    in entry_reads alone (the runner's two saver readings): S0 has no pool, so no saver reads anything in it. S0's
    tasks whose runs are all there already are not run again, and the cells read S0 from it; the arms' states at
    launch and their prefixes stay in this call's own cache."""
    s0_tasks, cell_tasks = grouped(tasks)
    s0_folder = lambda cache: cache if s0_cache is None else s0_cache
    made = lambda t: s0_cache is not None and all(
        _s0_file(s0_cache, t[0], t[1], level, t[3]).exists() for level in t[4])
    convention = lambda flag: "lenders' interest returned" if flag else "lenders' interest leaving"
    launches = [(rate, seed, n, recirculated, arm, levels)
                for (rate, seed, n, recirculated, levels), arm in product(s0_tasks, ARMS)]
    with tempfile.TemporaryDirectory(prefix="cpm_s0_") as cache, ProcessPoolExecutor(max_workers=workers) as pool:
        heads = {pool.submit(s0_task, t, template, s0_folder(cache), fixed_cost):
                 f"S0 at r_out {t[0]}, seed {t[1]}, distress {list(t[4])}, {convention(t[3])}" for t in s0_tasks
                 if not made(t)}
        heads.update({pool.submit(launch_task, t, template, cache, fixed_cost):
                      f"{t[4]} at launch, r_out {t[0]}, seed {t[1]}, {convention(t[3])}" for t in launches})
        bodies = {pool.submit(_stored, cell_task, t, template, cache, fixed_cost, s0_cache):
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
    and highest level; for S0 the run at the lowest a0 equals the run at the highest with its a0 set, and for every
    other arm runs at the highest a0 started from its state at launch (opened at the highest level) equal direct runs
    at both levels."""
    w = replace(template, n=100, months=14, distress_start=4, distress_length=6, seed=SEEDS["development"][0])
    inputs, levels = cell_inputs(BASE[0], fixed_cost), (DISTRESS[0], DISTRESS[-1])
    got = forked(inputs, A0S[0], w, arm, levels)
    ok = all(same(got[level], simulate(inputs, A0S[0], replace(w, distress=level), arm)) for level in levels)
    if arm == "S0":
        ok = ok and same(dict(got[levels[-1]], a0=A0S[-1]), simulate(inputs, A0S[-1], replace(w, distress=levels[-1]),
                                                                     "S0"))
    else:
        launched = launch_state(inputs, replace(w, distress=levels[-1]), arm)
        got = forked(inputs, A0S[-1], w, arm, levels, launched)
        ok = ok and all(same(got[level], simulate(inputs, A0S[-1], replace(w, distress=level), arm))
                        for level in levels)
    return ok


def preflight(template, workers, fixed_cost="central"):
    """Refuse to run the shared S0, the shared states at launch and the distress fork unless all three are
    bit-identical on the engine as it stands."""
    with ProcessPoolExecutor(max_workers=min(workers, 1 + len(ARMS))) as pool:
        results = dict(zip(("S0",) + ARMS, pool.map(partial(preflight_arm, template=template, fixed_cost=fixed_cost),
                                                    ("S0",) + ARMS)))
    if not all(results.values()):
        raise RuntimeError(f"The shared S0, a shared state at launch or the distress fork no longer matches direct "
                           f"runs: {results}; run --plain")

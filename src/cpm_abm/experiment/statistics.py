"""The interval arithmetic the verdicts and the claim read.

Wilson intervals on seed counts, t intervals and their quantiles, the percentile bootstrap, the Bonferroni level, the
three-way reading of a comparison (supported, falsified or inconclusive), the seeds a margin needs at a given power,
the spread pooled across cells with its degrees of freedom and its upper bound, edge-joined blocks of cells, and the
dip in failed payments under distress that the stress leg and the seed planner read. Pure functions of numbers and stored job records.
"""
from contextlib import contextmanager
from functools import lru_cache
from itertools import product

import networkx as nx
import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2, nct, norm, t as student

from cpm_abm.experiment.notes import (A0S, BOOTSTRAP_DRAWS, BOOTSTRAP_DRAWS_SECOND, BOOTSTRAP_SEED, CLAIM_ALPHA,
                                      DIP_MONTHS, RATES, SEED_ASSURANCE, SEED_POWER, second_run)
from cpm_abm.experiment.second_run import RATES as SECOND_RATES
from cpm_abm.experiment.steady import dip_window

def t_interval(values):
    """The mean across seeds and its 95% t interval, over the seeds that define a value (None skipped): None for the
    mean with no such seed, and for the interval with fewer than two."""
    seen = np.array([value for value in values if value is not None and np.isfinite(value)], float)
    if seen.size == 0:
        return dict(mean=None, lower_95=None, upper_95=None, seeds=0)
    mean = float(seen.mean())
    if seen.size < 2:
        return dict(mean=round(mean, 3), lower_95=None, upper_95=None, seeds=1)
    half = float(_t_quantile(0.975, seen.size - 1) * np.std(seen, ddof=1) / np.sqrt(seen.size))
    return dict(mean=round(mean, 3), lower_95=round(mean - half, 3), upper_95=round(mean + half, 3),
                seeds=int(seen.size))


def wilson_unrounded(hits, total, z=1.96):
    """The 95% Wilson interval for a share of seeds, hits out of total, unrounded: the bounds every decision reads.
    Example: 15 of 21 has lower bound 0.50044, above one half, which ``wilson`` stores as 0.5."""
    if total == 0:
        return None
    share, scale = hits / total, 1 + z * z / total
    centre = (share + z * z / (2 * total)) / scale
    half = z * np.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / scale
    return [float(centre - half), float(centre + half)]


def wilson(hits, total, z=1.96):
    """The 95% Wilson interval for a share of seeds, hits out of total, rounded to three places as stored for display;
    no decision reads it (``wilson_unrounded``)."""
    bounds = wilson_unrounded(hits, total, z)
    return None if bounds is None else [round(value, 3) for value in bounds]


def persistent_on_wilson(hits, total):
    """Whether a cell reads Persistent by its Persistent seeds' 95% Wilson interval, and whether that interval
    contains one half (near the line), both on the unrounded bounds (a lower bound just above one half
    must not round down to 0.500 and fail). Examples: 15 of 21 (lower 0.50044), 18 of 26, 46 of 75 and 51 of 84
    are Persistent and not near the line; 14 of 20 (lower 0.481) is neither Persistent nor clear of one half."""
    bounds = wilson_unrounded(hits, total)
    if bounds is None:
        return False, False
    return bool(bounds[0] > 0.5), bool(bounds[0] <= 0.5 <= bounds[1])


@lru_cache(maxsize=None)
def _t_quantile(q, dof):
    """Student's t quantile ``q`` at ``dof`` degrees of freedom, scipy's own value, kept once worked out, since the
    same few are asked for thousands of times."""
    return student.ppf(q, dof)


def _t_quantiles(q, dofs):
    """``_t_quantile`` for an array of degrees of freedom, element by element as one scipy call gives them."""
    values, where = np.unique(dofs, return_inverse=True)
    return np.array([_t_quantile(q, int(value)) for value in values], float)[where].reshape(np.shape(dofs))


def _group_bounds(values):
    """Each column's seed mean, 95% t lower bound and number of seeds defining it, unrounded, of ``values``, seeds x
    readings x groups (NaN where a group is empty in a seed), each a readings x groups array; a column with a value in
    one seed only has no bound (NaN). The mean sums each column over seeds and the spread is each column's own sd
    (ddof 1), as one reading's seeds x groups table at a time gives them, number for number: several readings at
    once, with the summing order the same for two or more groups."""
    seeds, readings, size = values.shape
    flat = np.ascontiguousarray(values.reshape(seeds, readings * size))
    seen = np.isfinite(flat).sum(axis=0)
    if size > 1:
        total = np.nansum(flat, axis=0)
    else:     # one group: each reading summed alone, as its own table is
        total = np.concatenate([np.nansum(np.ascontiguousarray(values[:, k, :]), axis=0) for k in range(readings)])
    mean = np.divide(total, seen, out=np.full(seen.size, np.nan), where=seen > 0)
    spread = np.full(seen.size, np.nan)
    whole = (seen == seeds) & (seen > 1)
    if whole.any():
        spread[whole] = np.std(np.ascontiguousarray(flat[:, whole].T), axis=1, ddof=1)
    for k in np.flatnonzero(~whole & (seen > 1)):    # a column with a group empty in some seeds
        spread[k] = np.std(flat[:, k][np.isfinite(flat[:, k])], ddof=1)
    lower = mean - _t_quantiles(0.975, np.maximum(seen - 1, 1)) * spread / np.sqrt(np.maximum(seen, 1))
    shape = (readings, size)
    return dict(mean=mean.reshape(shape), lower_95=lower.reshape(shape), seen=seen.reshape(shape))


def _finite(values):
    """The values that are numbers (None and NaN dropped), as an array."""
    return np.array([float(v) for v in values if v is not None and np.isfinite(float(v))], float)


def limited(arm, rate, w):
    """M2 at a zero real reserve rate is its declared limit, as ``region`` reads it."""
    return bool(arm == "M2" and rate - 12 * w.inflation <= 1e-12)


def bonferroni_cells(arm, w):
    """The cells "holds somewhere" is corrected over : every (r_out, a0) of the run's registered grid at
    distress 0 outside the arm's declared limit (r_out 2% at 2% CPI is M2's limit). The first run's grid has three
    rates, 21 cells for M1 and 14 for M2; a run of the second run (``second_run``) registers its six rates, 42 cells
    for M1 and 35 for M2."""
    rates = SECOND_RATES if second_run(w) else RATES
    return len(A0S) * sum(not limited(arm, rate, w) for rate in rates)


def bonferroni_alpha(arm, w):
    """The arm's Bonferroni level: 0.05 over its cells. Examples: 0.05 / 21 = 0.002381 for M1 in the first run; in the
    second run 0.05 / 42 = 0.001190 for M1 and 0.05 / 35 = 0.001429 for M2."""
    return CLAIM_ALPHA / bonferroni_cells(arm, w)


def t_bounds(values, alpha=CLAIM_ALPHA):
    """The seed mean and its two-sided t interval at 1 - alpha over the seeds that define a value, unrounded, with the
    spread (sd, ddof 1). Example: 1, 2, 3 has mean 2, sd 1 and 95% interval 2 -/+ 4.303 / sqrt(3) = -0.484 to 4.484."""
    seen = _finite(values)
    if seen.size == 0:
        return dict(mean=None, lower=None, upper=None, sd=None, seeds=0)
    mean = float(seen.mean())
    if seen.size < 2:
        return dict(mean=mean, lower=None, upper=None, sd=None, seeds=1)
    sd = float(np.std(seen, ddof=1))
    half = float(_t_quantile(1 - alpha / 2, seen.size - 1)) * sd / np.sqrt(seen.size)
    return dict(mean=mean, lower=mean - half, upper=mean + half, sd=sd, seeds=int(seen.size))


@lru_cache(maxsize=8)
def _resamples(size, draws, seed):
    """The bootstrap's resampled seeds, draws x size places into the seeds: each interval starts the same fixed
    stream, so every interval over ``size`` seeds draws these same numbers, and they are drawn once.
    Read-only."""
    places = np.random.default_rng(seed).integers(0, size, (draws, size))
    places.flags.writeable = False
    return places


@lru_cache(maxsize=2)
def _resamples_many(size, draws, seed):
    """``_resamples`` at the second run's draws, the same stream, with room for two sizes of seeds only: at 200,000
    draws of 40 seeds the places take 64 MB."""
    return _resamples.__wrapped__(size, draws, seed)


@lru_cache(maxsize=512)
def _resampled_means(seen, draws, seed):
    """The seed mean in each resample of the seeds' values (``seen``, their bytes): kept for the same values read again
    at another level (each clause is read at 95% and at the Bonferroni level). Read-only."""
    values = np.frombuffer(seen, float)
    means = values[_resamples(values.size, draws, seed)].mean(axis=1)
    means.flags.writeable = False
    return means


@lru_cache(maxsize=64)
def _resampled_means_many(seen, draws, seed):
    """``_resampled_means`` at the second run's draws, keeping 64 sets of means (1.6 MB each at 200,000 draws)."""
    values = np.frombuffer(seen, float)
    means = values[_resamples_many(values.size, draws, seed)].mean(axis=1)
    means.flags.writeable = False
    return means


# The resamples a bootstrap draws when its caller names none: BOOTSTRAP_DRAWS in the first run, and the second
# run's within ``resampled``.
_DRAWS = [BOOTSTRAP_DRAWS]


def bootstrap_draws(w):
    """The bootstrap's resamples for a run on the Economy ``w``: 10,000 in the first run; 200,000 in a run of the second
    run, whose stricter level's two-sided tail, 0.05 / (2 x 42), then rests on about 119 resamples
    in place of about 6 (``BOOTSTRAP_DRAWS_SECOND``). The stream's seed is the same."""
    return BOOTSTRAP_DRAWS_SECOND if second_run(w) else BOOTSTRAP_DRAWS


@contextmanager
def resampled(draws):
    """Within the block every bootstrap that names no draws draws ``draws`` resamples (``bootstrap_draws``); the
    released count is restored after it, whatever happens."""
    _DRAWS.append(int(draws))
    try:
        yield
    finally:
        _DRAWS.pop()


def bootstrap_bounds(values, alpha=CLAIM_ALPHA, draws=None, seed=BOOTSTRAP_SEED):
    """The bootstrap check: the percentile interval at 1 - alpha of the seed mean over seeds drawn
    with replacement, on a fixed stream; None with fewer than two seeds. It always lies within the seeds' range.
    ``draws`` by default is the count in force (``resampled``): 10,000 in the first run."""
    seen = _finite(values)
    if seen.size < 2:
        return None
    draws = _DRAWS[-1] if draws is None else draws
    means = (_resampled_means if draws <= BOOTSTRAP_DRAWS else _resampled_means_many)(seen.tobytes(), draws, seed)
    lower, upper = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return [float(lower), float(upper)]


def reading(lower, upper, margin, side="above", strict=False):
    """A condition's reading from an interval (the claim row): "supported" when the interval lies wholly on the
    condition's side of the margin, "falsified" when wholly on the wrong side, "inconclusive" when it straddles,
    "undefined" without an interval. side "above" asks the value at or above the margin (above it with ``strict``),
    "below" at or below it (below it with ``strict``). Example: -2.5 to 1 against -2 above is inconclusive."""
    if lower is None or upper is None:
        return "undefined"
    if side == "above":
        ok = (lambda x: x > margin) if strict else (lambda x: x >= margin)
        return "supported" if ok(lower) else "falsified" if not ok(upper) else "inconclusive"
    ok = (lambda x: x < margin) if strict else (lambda x: x <= margin)
    return "supported" if ok(upper) else "falsified" if not ok(lower) else "inconclusive"


def check(values, margin, side="above", alpha=CLAIM_ALPHA, strict=False):
    """One interval check of the claim over the seeds' values: the t interval and the bootstrap check at 1 - alpha,
    the reading on each, holds when both read supported (the check leans against CPM), and near_the_line when the t
    interval straddles the margin or the two readings differ. Numbers rounded to 4 places as stored."""
    t = t_bounds(values, alpha)
    boot = bootstrap_bounds(values, alpha)
    on_t = reading(t["lower"], t["upper"], margin, side, strict)
    on_boot = reading(*(boot or (None, None)), margin, side, strict)
    clean = lambda value: None if value is None else round(float(value), 4)
    return dict(mean=clean(t["mean"]), lower=clean(t["lower"]), upper=clean(t["upper"]), sd=clean(t["sd"]),
                seeds=t["seeds"], bootstrap=None if boot is None else [clean(b) for b in boot], margin=margin,
                side=side, strict=strict, reading=on_t, bootstrap_reading=on_boot,
                holds=bool(on_t == "supported" and on_boot == "supported"),
                near_the_line=bool(on_t == "inconclusive" or (on_t != on_boot and "undefined" not in (on_t, on_boot))))


def combined(block):
    """One interval check's three-way reading (``check``): a test holds only when the t and the
    bootstrap interval both read supported, and reads inconclusive where an interval straddles its margin:
    "supported" when both lie wholly on the condition's side, "falsified" only when both lie wholly on the wrong side,
    and "inconclusive" otherwise (the two disagree, either straddles, or one is undefined; ``check`` puts such a block
    near the line). Examples: t supported and bootstrap straddling is inconclusive; t falsified and bootstrap
    straddling is inconclusive; both falsified is falsified."""
    readings = (block["reading"], block["bootstrap_reading"])
    if all(r == "falsified" for r in readings):
        return "falsified"
    return "supported" if all(r == "supported" for r in readings) else "inconclusive"


def share_reading(interval, half=0.5):
    """A Wilson interval's three-way reading against one half (claim (a)'s seed shares): supported when its lower bound
    is above one half, falsified when its upper bound is at or below it, inconclusive between; None is inconclusive."""
    if interval is None:
        return "inconclusive"
    return "supported" if interval[0] > half else "falsified" if interval[1] <= half else "inconclusive"


def three_way(components):
    """A clause's or a cell's three-way reading from its required components, each (name, reading): "falsified" when
    any is falsified, naming those; else "inconclusive" when any is not supported, naming those; else "supported".
    Example: [("x", "supported"), ("y", "inconclusive")] is inconclusive, decided by ["y"]."""
    falsified = [name for name, value in components if value == "falsified"]
    if falsified:
        return dict(reading="falsified", decided_by=falsified)
    short = [name for name, value in components if value != "supported"]
    return dict(reading="inconclusive" if short else "supported", decided_by=short)


def wilson_bounds(hits, total, alpha=CLAIM_ALPHA):
    """The Wilson interval of a share of seeds at 1 - alpha, unrounded, None with no seed. Example: 15 of 20 at 95%
    has lower bound 0.531, above one half; under Bonferroni over 21 cells (z 3.038) 17 of 20 has 0.510 and 16 has
    0.461, so 17 are needed, as the claim row says."""
    if total == 0:
        return None
    z = float(norm.ppf(1 - alpha / 2))
    share, scale = hits / total, 1 + z * z / total
    centre = (share + z * z / (2 * total)) / scale
    half = z * np.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / scale
    return [float(centre - half), float(centre + half)]


def least_passing(total, alpha=CLAIM_ALPHA):
    """The fewest of ``total`` seeds that must pass for the Wilson interval of their share at 1 - alpha to have its
    lower bound above one half (``wilson_bounds``, claim (a)'s seed shares and the Persistent share), None when even
    all of them do not suffice: the decisions a count can reach. Examples: 15 of 20 at 95%;
    10 of 10 at 0.05 / 42 has lower bound 0.48768, so 10 seeds can never pass there and give None."""
    if total < 1:
        return None
    hits = np.arange(total + 1, dtype=float)
    z = float(norm.ppf(1 - alpha / 2))
    share, scale = hits / total, 1 + z * z / total
    centre = (share + z * z / (2 * total)) / scale
    half = z * np.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / scale
    above = np.flatnonzero(centre - half > 0.5)
    return int(above[0]) if above.size else None


@lru_cache(maxsize=4096)
def seeds_needed(spread, distance, alpha, power=SEED_POWER, most=1_000_000):
    """The fewest seeds (at least 2) at which the paired t test at 1 - alpha two-sided shows a true difference of zero
    clear of a margin ``distance`` away with probability ``power``: the noncentral t's tail beyond the critical value,
    noncentrality distance x sqrt(n) / spread. None when the spread is undefined or more than ``most`` are needed.
    Examples: a spread of $4.27 is the one at which a true zero passes half the time at
    20 seeds; at 80% power 20 seeds need a spread of at most $3.03 ($2.02 under Bonferroni over 21 cells); at spreads
    of $4, $6 and $8 the Bonferroni count is 65, 141 and 246. Each answer is kept once worked out."""
    if spread is None or not np.isfinite(spread):
        return None
    if spread <= 0:
        return 2

    def powered(n):
        """Whether ``n`` seeds reach the power: the noncentral t's tail beyond the two-sided critical value at
        ``alpha`` is at least ``power``."""
        critical = _t_quantile(1 - alpha / 2, n - 1)
        return bool(nct.sf(critical, n - 1, distance * np.sqrt(n) / spread) >= power)

    high = 2
    while not powered(high):
        if high > most:
            return None
        high *= 2
    low = max(high // 2, 2)            # not powered unless high is 2
    if powered(low):
        return low
    while high - low > 1:
        middle = (low + high) // 2
        low, high = (low, middle) if powered(middle) else (middle, high)
    return high


def pooled_spread(columns):
    """The spread pooled across cells (``seeds_needed``): the square root of the cells' variances weighted by their
    degrees of freedom, over cells with at least two seeds; None with none. Example: cells (1, 3) and (0, 4) have
    variances 2 and 8, pooled sqrt(5) = 2.236."""
    parts = [part for part in map(_finite, columns) if part.size >= 2]
    dof = sum(part.size - 1 for part in parts)
    if dof == 0:
        return None
    return float(np.sqrt(sum((part.size - 1) * np.var(part, ddof=1) for part in parts) / dof))


def pooled_freedom(columns):
    """The degrees of freedom of the spread pooled across cells (``pooled_spread``): the sum over cells with at least
    two seeds of their seeds less one. Example: 21 cells of 3 seeds have 42."""
    return int(sum(part.size - 1 for part in map(_finite, columns) if part.size >= 2))


def spread_bound(spread, freedom, assurance=SEED_ASSURANCE):
    """The upper end of a pooled spread's one-sided interval at ``assurance`` (the seed count's
    allowance for the spread being an estimate): s x sqrt(nu / chi2_q(nu)), with nu the pooled degrees of freedom and
    chi2_q the chi-square quantile at q = 1 - assurance. None when the spread is undefined or nu is below one. Example:
    1.1658 at 42 degrees of freedom gives 1.293 at 0.8."""
    if spread is None or not np.isfinite(spread) or freedom < 1:
        return None
    return float(spread * np.sqrt(freedom / chi2.ppf(1 - assurance, freedom)))


def spread_resolved(seeds, distance, alpha, power=SEED_POWER):
    """The largest spread at which ``seeds`` seeds reach ``power`` (``seeds_needed`` read the other way): the spread at
    which the paired t test at 1 - alpha two-sided shows a true difference of zero clear of a margin ``distance`` away
    with that probability. Examples: 20 seeds resolve the $2 margin up to a spread of $3.03 at 95% and $2.02 at the
    Bonferroni level over 21 cells; 30 seeds up to $3.78 and $2.597."""
    critical = _t_quantile(1 - alpha / 2, seeds - 1)
    return float(brentq(lambda spread: nct.sf(critical, seeds - 1, distance * np.sqrt(seeds) / spread) - power,
                        1e-6 * distance, 1e6 * distance, xtol=1e-12))


def connected_blocks(passing):
    """The blocks of grid cells (row, column) joined by a shared edge (a region is a connected
    block of passing cells; a corner does not join, the reading that leans against CPM), largest first and, at a tie,
    the one whose first cell comes first. Example: {(0, 0), (0, 1), (1, 1), (2, 3)} is [[(0, 0), (0, 1), (1, 1)],
    [(2, 3)]]. The cells are a networkx graph, an edge joining two cells one step apart in a row or a column."""
    graph = nx.Graph()
    graph.add_nodes_from(passing)
    graph.add_edges_from((one, two) for one, two in product(passing, repeat=2)
                         if abs(one[0] - two[0]) + abs(one[1] - two[1]) == 1)
    blocks = [sorted(block) for block in nx.connected_components(graph)]
    return sorted(blocks, key=lambda block: (-len(block), block[0]))


DIP_YEARS = (DIP_MONTHS[1] - DIP_MONTHS[0] + 1) / 12   # the 36 months of the dip, 3 years in the first run


def yearly_dips(values, years=None):
    """The dip a year (one failed payment per consumer unit a year): each dip summed over its
    months over the years they span, None kept. ``years`` is the span, one number or one a seed (``dips`` stores it);
    by default the first run's 36 months, 3 years. The stress leg's interval and the seed planner's pooled spread read
    this same series. Examples: 1.8 over the first run's 36 months is 0.6 a year, and the same over a second run's 36
    months from its stress year (months 121 to 156); 1.8 over a span of 18 months is 1.2 a year."""
    years = [DIP_YEARS] * len(values) if years is None else (
        list(years) if np.ndim(years) else [years] * len(values))
    return [None if value is None else value / span for value, span in zip(values, years)]


def dip_months(w=None, seed=None):
    """The months the dip is summed over, as indices (first, end) into a monthly series after launch, end excluded:
    36 months from the first stress month, read from the run's own Economy ``w`` (``dip_window``); with no
    Economy the released months 25 to 60 (``DIP_MONTHS``), (24, 60), which a released Economy also gives. None for a
    run with no stress month."""
    if w is None:
        return DIP_MONTHS[0] - 1, DIP_MONTHS[1]
    return dip_window(w, seed)


def dips(arm, level_jobs, base_jobs, w=None):
    """Clause (e)'s dip seed by seed: each run's cumulative excess of failed shares a person from the first
    stress month over the 36 months that follow (``dip_months``: months 25 to 60 after launch in the first run, months
    121 to 156 in the second run), the level's run less the same seed's run without distress, in the real failure
    line's unit; then the arm's dip less S0's and less M0's; and beside them the years each seed's dip spans
    (``years``), which ``yearly_dips`` divides by. Example: monthly failed shares 0.1 over the 36 months in the
    level's run and 0.05 at level 0 is a dip of 1.8, 0.6 a year."""
    base = {j["seed"]: j for j in base_jobs}

    def excess(job, other, who, first, last):
        """``who``'s monthly failed shares summed over the dip months in ``job`` less the same in ``other``; None
        where either lacks the counts."""
        mine, theirs = ((x.get("failure_counts") or {}).get(who) for x in (job, other))
        if mine is None or theirs is None:
            return None
        return float(np.sum(mine["monthly"]["fail_shares"][first:last])
                     - np.sum(theirs["monthly"]["fail_shares"][first:last]))

    less = lambda own, theirs: None if own is None or theirs is None else own - theirs
    out = dict(own=[], against_S0=[], against_M0=[], years=[])
    for job in level_jobs:
        other = base.get(job["seed"])
        if other is None:
            continue
        span = dip_months(w, job["seed"])
        if span is None:   # a run with no stress month has no dip
            out["own"].append(None), out["against_S0"].append(None), out["against_M0"].append(None)
            out["years"].append(None)
            continue
        own = excess(job, other, arm, *span)
        out["own"].append(own)
        out["against_S0"].append(less(own, excess(job, other, "S0", *span)))
        out["against_M0"].append(less(own, excess(job, other, "M0", *span)))
        out["years"].append(DIP_YEARS if w is None else (span[1] - span[0]) / 12)
    return out

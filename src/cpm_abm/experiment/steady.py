"""Readings of a long run's stored monthly series: whether a measure has settled, how it comes back after a stress
year, the credit that card lines held through the stress support, and what the conserved edge hands back.

Pure functions of plain arrays and of stored jobs (a job as ``assemble`` returns it, or as measures.json stores it,
its distress measures under "series"). Every series is one value a month after launch, index 0 the first month after
launch, None or NaN where a value is undefined. The stress months are read from the run's own Economy (its burn-in,
length, distress start and length, or the random calendar), never assumed. No margin is chosen here: every reading
that compares against a margin takes it from the caller.
"""
from dataclasses import fields
from itertools import product
from types import SimpleNamespace

import numpy as np
from scipy.stats import t as student

from cpm_abm.engine.population import distress_calendar
from cpm_abm.engine.settings import Economy
from cpm_abm.experiment.notes import MEASURES
from run_economy_figures import DOLLARS

YEAR = 12
# The windows of whole years after launch a settled state is read on (docs/DECISIONS.md, "The horizon and
# the windows"): years 6 to 10 against years 21 to 25, the long drift, and years 16 to 20 against 21 to 25, a pair
# inside the late period.
EARLY, LATE_FIRST, LATE = (6, 10), (16, 20), (21, 25)
SETTLED_PAIRS = dict(early_to_late=(EARLY, LATE), within_late=(LATE_FIRST, LATE))
# The return after the stress: the effect must stay inside the caller's margin this many months running, and the
# effect is reported from this many months before the stress year.
RETURN_HOLD, BEFORE = 12, 12
# The settings a reading of the calendar needs, each at the Economy's default when a stored economy predates it.
CALENDAR = ("burn_in", "months", "distress_start", "distress_length", "distress_dates", "distress_expected", "seed")


def economy_of(w, seed=None):
    """The settings of ``w`` that fix the stress months, from an Economy or from a stored economy dict
    (summary.json's "economy"), each missing or None one at the Economy's default, which is the released design (a
    burn-in of 6, 60 months after launch, a distress year from 24 months after launch for 12); ``seed`` sets the seed,
    which a stored economy leaves to each job and the random calendar is drawn from."""
    known = {f.name for f in fields(Economy)}
    read = w.get if isinstance(w, dict) else (lambda name: getattr(w, name, None))
    default = Economy()
    values = {name: read(name) for name in CALENDAR if name in known}
    values = {name: getattr(default, name) if value is None and name != "seed" else value
              for name, value in values.items()}
    if seed is not None:
        values["seed"] = seed
    return SimpleNamespace(**values)


def stress_months(w, seed=None):
    """The months after launch inside a distress year, as indices into a stored monthly series (0 the first month
    after launch), read from the run's own calendar (``distress_calendar``): the dated year from ``distress_start``
    for ``distress_length`` months, or the random years drawn from the seed. Examples: the first run gives
    indices 24 to 35 (months 25 to 36 after launch); the second run, distress_start 120 and a year of 12 in 300 months
    after a burn-in of 60, gives indices 120 to 131 (months 121 to 132)."""
    e = economy_of(w, seed)
    if e.distress_dates == "random" and e.seed is None:
        raise ValueError("random distress years are drawn from the seed: pass the job's seed")
    return np.flatnonzero(distress_calendar(e)[e.burn_in:])


def stress_year(w, seed=None):
    """The first stress year after launch as (first, end), indices into a monthly series with end excluded, the year
    cut at the run's end; None when the run has no stress month. Examples: (24, 36) in the first run, (120, 132) in the
    second run, and (54, 60) for a year from 54 months after launch in a 60-month run."""
    months = stress_months(w, seed)
    if not months.size:
        return None
    e = economy_of(w, seed)
    first = int(months[0])
    return first, min(first + e.distress_length, e.months)


# The span of clause (e)'s dip: the stress year and the two years after it, in the first run (months 25 to 60).
DIP_SPAN = 36


def dip_window(w, seed=None):
    """The months clause (e)'s dip is summed over, as indices (first, end) with end excluded: ``DIP_SPAN`` months
    from the first stress month, cut at the run's end; None with no stress month. The span is the first run's, so
    the margin of one failed payment a year means the same in a run of any length: a run that goes on for 14 years
    after its stress year does not dilute the dip over them. What happens later is read by the return after the
    stress (``stress_return``). Examples: (24, 60) in the first run, months 25 to 60 after launch (``DIP_MONTHS``);
    (120, 156) in the second run, months 121 to 156."""
    year = stress_year(w, seed)
    return None if year is None else (year[0], min(year[0] + DIP_SPAN, economy_of(w, seed).months))


def _array(values):
    """A series (or seeds by months) as floats, None read as NaN."""
    return np.array(values, dtype=float)


def mean_and_se(values):
    """The mean across seeds and its standard error (the sample standard deviation over the square root of the
    count), over the seeds that define a value: mean None with none, se None with fewer than two. Example: 1, 2
    and 3 have mean 2 and standard error 1 / sqrt(3) = 0.577."""
    seen = np.array([v for v in values if v is not None and np.isfinite(v)], float)
    if not seen.size:
        return dict(mean=None, se=None, seeds=0)
    se = float(np.std(seen, ddof=1) / np.sqrt(seen.size)) if seen.size > 1 else None
    return dict(mean=float(seen.mean()), se=se, seeds=int(seen.size))


def _finite_mean(rows):
    """Each row's mean over its defined values, NaN for a row with none (no warning)."""
    seen = np.isfinite(rows)
    count = seen.sum(axis=1)
    total = np.where(seen, rows, 0.0).sum(axis=1)
    return np.divide(total, count, out=np.full(rows.shape[0], np.nan), where=count > 0)


def window_means(series, years):
    """Each seed's mean of a monthly series over the whole years ``years`` = (first, last) after launch, both
    included, from year 1; ``series`` is one seed's months or seeds by months. Undefined months are left out of the
    mean, and a seed with none in the window reads NaN. Example: a series equal to its year number (12 values of 1,
    then 12 of 2, ...) has mean 8 over years 6 to 10."""
    rows = np.atleast_2d(_array(series))
    first, last = years
    if not 1 <= first <= last:
        raise ValueError(f"years run from 1, first to last: not {years!r}")
    if rows.shape[1] < YEAR * last:
        raise ValueError(f"years {first} to {last} need {YEAR * last} months; the series has {rows.shape[1]}")
    return _finite_mean(rows[:, YEAR * (first - 1):YEAR * last])


def settled(series, margin, early=EARLY, late=LATE):
    """Whether a measure has settled, as an equivalence test: each seed's mean over the
    ``early`` and the ``late`` window of whole years, the change between them seed by seed, its mean across seeds,
    its standard error and its two-sided 95% t interval. The verdict is "settled" when the whole interval lies inside
    the margin (from minus ``margin`` to ``margin``, the caller's, on the measure's own scale), so imprecision cannot
    settle a measure; "moving" when the interval lies wholly on one side of zero and the mean is beyond the margin;
    "undecided" otherwise; and None with fewer than two seeds defining a change. The mean, the interval and the margin
    are returned with it. Equal window means do not rule out a long interruption between them, which the series
    itself shows.

    Examples: three seeds whose late mean is above their early mean by 0.01, 0.03 and 0.02 change by 0.02 on mean
    with a standard error of 0.00577 and a 95% interval of 0.02 -/+ 4.303 x 0.00577, -0.0048 to 0.0448: settled
    under a margin of 0.05, undecided under 0.01 (the interval reaches below zero). A mean change of 0.02 under a
    margin of 0.05 is settled with a standard error of 0.001 and undecided with one of 0.1."""
    if margin is None or margin < 0:
        raise ValueError(f"the margin is the caller's, at least 0: not {margin!r}")
    before, after = window_means(series, early), window_means(series, late)
    change = after - before
    stats = mean_and_se(change)
    clean = lambda values: [None if not np.isfinite(v) else float(v) for v in values]
    out = dict(early=list(early), late=list(late), margin=margin, early_by_seed=clean(before),
               late_by_seed=clean(after), change_by_seed=clean(change), change_mean=stats["mean"],
               change_se=stats["se"], change_lower_95=None, change_upper_95=None, seeds=stats["seeds"],
               inside_margin=None, outside_zero=None, verdict=None)
    if stats["se"] is not None:
        half = float(student.ppf(0.975, stats["seeds"] - 1)) * stats["se"]
        lower, upper = stats["mean"] - half, stats["mean"] + half
        out.update(change_lower_95=lower, change_upper_95=upper,
                   inside_margin=bool(-margin <= lower and upper <= margin), outside_zero=bool(lower > 0 or upper < 0))
        beyond = abs(stats["mean"]) > margin
        out["verdict"] = ("settled" if out["inside_margin"] else "moving" if out["outside_zero"] and beyond
                          else "undecided")
    return out


def settled_readings(series, margin, pairs=None):
    """``settled`` on each pair of windows in ``pairs`` (by default SETTLED_PAIRS: years 6 to 10 against 21 to 25,
    and 16 to 20 against 21 to 25), by the pair's name."""
    pairs = SETTLED_PAIRS if pairs is None else pairs
    return {name: settled(series, margin, early, late) for name, (early, late) in pairs.items()}


def stress_return(run, twin, w, margin, seed=None, hold=RETURN_HOLD, before=BEFORE):
    """How one seed's measure comes back after the stress: the effect is the distress run less its no-distress twin
    (the level-0 run of the same outside rate, launch level, seed and saver reading), month by month.

    Returns, with months after launch counted from 1: stress, whether the run has a stress month; effect_months and
    effect, the effect from ``before`` months before the first stress year to the end; peak and peak_month, the
    effect of largest size from the first stress month on (signed); back_month, the first month after the stress
    year from which the effect stays inside ``margin`` (the caller's) for ``hold`` months running, None when it never
    does within the run, and months_to_return, the months from the stress year's last month to it (1 when the run of
    ``hold`` starts in the first month after the year); stays_back, whether the effect then stays inside the margin to the
    end of the run; half_life, the months from the peak to the first month at or below half of its size (0 with no
    effect), None when it never gets there. An undefined month counts as outside the margin and above half.

    Example: a stress year at indices 24 to 35 and an effect of 1.0 in month 36 halving every month after it: the
    peak is 1.0 in month 36, half of it is reached in month 37, a half-life of 1; under a margin of 0.1 the effect is
    inside from month 40 (0.0625) on, so back_month is 40 and months_to_return 4, as the paired distress reading
    counts its months to recover."""
    effect = _array(run) - _array(twin)
    year = stress_year(w, seed)
    empty = dict(stress=False, effect_months=None, effect=None, peak=None, peak_month=None, back_month=None,
                 months_to_return=None, stays_back=None, half_life=None)
    if year is None:
        return empty
    first, end = year
    start = max(first - before, 0)
    size = np.abs(effect)
    tail = np.where(np.isfinite(size[first:]), size[first:], -1.0)
    out = dict(empty, stress=True, effect_months=list(range(start + 1, effect.size + 1)),
               effect=[None if not np.isfinite(v) else float(v) for v in effect[start:]])
    if tail.size == 0 or tail.max() < 0:
        return out
    at = first + int(np.argmax(tail))
    peak = float(effect[at])
    # Inside the margin: defined and no larger than it. A run of ``hold`` months inside starts at each index where
    # the next ``hold`` months are all inside; the first such index at or after the stress year's end is the return.
    inside = np.isfinite(size) & (size <= margin)
    runs = np.convolve(inside[end:].astype(int), np.ones(hold, int), "valid") if effect.size - end >= hold \
        else np.zeros(0, int)
    held = np.flatnonzero(runs == hold)
    halved = np.flatnonzero(np.isfinite(size[at:]) & (size[at:] <= abs(peak) / 2))
    out.update(peak=peak, peak_month=at + 1, half_life=int(halved[0]) if halved.size else None)
    if held.size:
        back = end + int(held[0])
        out.update(back_month=back + 1, months_to_return=back + 1 - end, stays_back=bool(inside[back:].all()))
    return out


def stress_return_seeds(runs, twins, w, margin, seeds=None, hold=RETURN_HOLD, before=BEFORE):
    """``stress_return`` over paired seeds (``runs`` and ``twins`` in the same order, ``seeds`` their seeds, needed
    under the random calendar), with the seed means and standard errors: of the peak, of the half-life over the seeds
    that halve, and of the months to return over the seeds that return, with the share that return; and the effect's
    mean and standard error across seeds in each month after launch."""
    seeds = [None] * len(runs) if seeds is None else list(seeds)
    readings = [stress_return(run, twin, w, margin, seed, hold, before) for run, twin, seed in zip(runs, twins, seeds)]
    effects = np.atleast_2d(_array(runs) - _array(twins)) if runs else np.zeros((0, 0))
    by_month = [mean_and_se(column) for column in effects.T]
    returned = [r["months_to_return"] for r in readings if r["months_to_return"] is not None]
    return dict(seeds=len(readings), by_seed=readings, peak=mean_and_se([r["peak"] for r in readings]),
                half_life=mean_and_se([r["half_life"] for r in readings if r["half_life"] is not None]),
                months_to_return=mean_and_se(returned),
                returned_share=len(returned) / len(readings) if readings else None,
                effect_mean=[m["mean"] for m in by_month], effect_se=[m["se"] for m in by_month])


def series_of(job, arm, key):
    """One arm's stored monthly series in a job, as floats: from its monthly records, its distress measures (by the
    measure's name or by the engine series it holds, "failures" or "failure_share") or its failure counts' monthly
    records. ``key`` may be a pair (numerator, denominator) for their ratio month by month, such as ("N", "Q"), pool
    capital over its limit. None when the job stores no such series."""
    if isinstance(key, tuple):
        top, bottom = (series_of(job, arm, part) for part in key)
        if top is None or bottom is None:
            return None
        return np.divide(top, bottom, out=np.full(top.size, np.nan), where=np.isfinite(bottom) & (bottom != 0))
    names = [key] + [name for name, series in MEASURES.items() if series == key]
    measures = job.get("measures", job.get("series")) or {}
    # The monthly records first, then the distress measures; in each, the key itself before the measures holding it.
    for found, name in product([part.get(arm) or {} for part in (job.get("monthly") or {}, measures)], names):
        if name in found:
            return _array(found[name])
    counts = ((job.get("failure_counts") or {}).get(arm) or {}).get("monthly") or {}
    return _array(counts[key]) if key in counts else None


def twins(level_jobs, base_jobs):
    """Each distress job with its no-distress twin: the level-0 job of the same outside rate, launch level, seed and
    lenders'-income convention, in the order of ``level_jobs``; a job without a twin is left out. A job does not
    carry the saver reading: that is its store's, and both lists are one store's jobs."""
    ident = lambda job: (float(job["r_out"]), float(job["a0"]), job["seed"], bool(job["recirculated"]))
    base = {ident(job): job for job in base_jobs if float(job["distress"]) == 0.0}
    return [(job, base[ident(job)]) for job in level_jobs if ident(job) in base]


def stress_return_jobs(level_jobs, base_jobs, arm, key, w, margin, hold=RETURN_HOLD, before=BEFORE):
    """``stress_return_seeds`` on one arm's stored series ``key`` (``series_of``) over the jobs of one distress cell
    and their twins, ``w`` the run's Economy or stored economy."""
    pairs = [(job, twin) for job, twin in twins(level_jobs, base_jobs)
             if series_of(job, arm, key) is not None and series_of(twin, arm, key) is not None]
    return stress_return_seeds([series_of(job, arm, key) for job, _ in pairs],
                               [series_of(twin, arm, key) for _, twin in pairs], w, margin,
                               [job["seed"] for job, _ in pairs], hold, before)


def settled_jobs(jobs, arm, key, margin, pairs=None):
    """``settled_readings`` on one arm's stored series ``key`` over the seeds of one cell (its jobs)."""
    found = [series_of(job, arm, key) for job in jobs]
    return settled_readings([s for s in found if s is not None], margin, pairs)


def _by_year(values, how):
    """A monthly series by whole year after launch: "sum" for a flow, "mean" for a stock (undefined months left
    out); a part year at the end is left out."""
    years = values.size // YEAR
    rows = values[:YEAR * years].reshape(years, YEAR)
    return rows.sum(axis=1) if how == "sum" else _finite_mean(rows)


def outside_support(card_held, card_cut, money_held, interest_held, interest_cut):
    """The credit card lines held through the stress support (outside support): card debt with lines held less with
    lines cut, month by month; as a share of card credit in use with lines held and of the money households hold
    with lines held; and the change in all the interest outside lenders earn, on cards and on every other outside
    loan, which is not the interest on the supported credit alone. Money in the model's units (months of mean
    spending a person), with dollars (``DOLLARS``) beside. By year: card debt, money and the supported credit are
    year means (stocks) and the change in interest a year's sum (a flow); each year's shares are the ratio of its
    means. A share is None where its base is zero or undefined.

    Example: card debt 0.30 with lines held and 0.20 with lines cut in every month, money 2.0 and interest 0.004
    against 0.003 a month: the supported credit is 0.10 ($644 a person), a third of card credit in use and 5% of
    money, and lenders earn 0.012 more a year ($77.28 a person)."""
    held, cut, money = _array(card_held), _array(card_cut), _array(money_held)
    supported, extra = held - cut, _array(interest_held) - _array(interest_cut)
    share = lambda part, base: [float(p / b) if np.isfinite(p) and np.isfinite(b) and b != 0 else None
                                for p, b in zip(part, base)]
    clean = lambda values: [None if not np.isfinite(v) else float(v) for v in values]
    year = {name: _by_year(values, "mean") for name, values in dict(supported=supported, held=held, money=money).items()}
    year_extra = _by_year(extra, "sum")
    return dict(
        by_month=dict(supported=clean(supported), share_of_card=share(supported, held),
                      share_of_money=share(supported, money), extra_outside_interest=clean(extra),
                      supported_usd=clean(supported * DOLLARS), extra_outside_interest_usd=clean(extra * DOLLARS)),
        by_year=dict(supported=clean(year["supported"]), share_of_card=share(year["supported"], year["held"]),
                     share_of_money=share(year["supported"], year["money"]),
                     extra_outside_interest=clean(year_extra), supported_usd=clean(year["supported"] * DOLLARS),
                     extra_outside_interest_usd=clean(year_extra * DOLLARS)))


# The stored series the outside-support reading takes from a job: card debt to outside lenders and, where the job
# stores it, what holders owe their card that is not yet a loan (purchases not yet billed and the closed statement not
# yet due), the money households hold (E and P, and outside savings, each a month's average balance) and outside
# lenders' interest.
CARD_DEBT, CARD_UNBILLED = "card_debt", "card_unbilled"
MONEY_HELD, LENDER_INTEREST = ("money_bt", "savings_bt"), "out_interest"
CARD_READS = {True: "card_debt + card_unbilled", False: "card_debt"}


def outside_support_jobs(held_jobs, cut_jobs, arm="S0"):
    """``outside_support`` seed by seed from the jobs of one cell run with card lines held and with lines cut (matched
    on outside rate, launch level, distress level, seed and lenders'-income convention), for one arm (banks, S0, by
    default), with the seed means and standard errors of each yearly reading. A job does not carry the saver reading
    or its settings: the caller checks that the two stores are one model apart from the card lines
    (``scripts/bank_support.py``).

    Card credit in use is card_debt plus card_unbilled where both jobs of a seed store card_unbilled, and card_debt
    alone where they do not (the first run's stores, which count a purchase not yet billed as zero). The result's
    ``card_credit_reads`` names what was read: one of those two, or "mixed" when seeds differ."""
    ident = lambda job: (float(job["r_out"]), float(job["a0"]), float(job["distress"]), job["seed"],
                         bool(job["recirculated"]))
    cut = {ident(job): job for job in cut_jobs}

    def card(job, unbilled):
        """The card credit in use in one job, card_debt alone or with card_unbilled; None if card_debt is missing."""
        debt = series_of(job, arm, CARD_DEBT)
        return debt + series_of(job, arm, CARD_UNBILLED) if unbilled and debt is not None else debt

    def parts(job, other):
        """The five series ``outside_support`` reads for one seed and whether card_unbilled was read, None when either
        job lacks one."""
        money = [series_of(job, arm, key) for key in MONEY_HELD]
        unbilled = all(series_of(j, arm, CARD_UNBILLED) is not None for j in (job, other))
        found = [card(job, unbilled), card(other, unbilled), None if any(m is None for m in money) else sum(money),
                 series_of(job, arm, LENDER_INTEREST), series_of(other, arm, LENDER_INTEREST)]
        return None if any(f is None for f in found) else (found, unbilled)

    found = [parts(job, cut[ident(job)]) for job in held_jobs if ident(job) in cut]
    found = [seed for seed in found if seed is not None]
    by_seed = [outside_support(*seed) for seed, _ in found]
    reads = {unbilled for _, unbilled in found}
    years = {name: [mean_and_se(column) for column in zip(*(seed["by_year"][name] for seed in by_seed))]
             for name in (by_seed[0]["by_year"] if by_seed else ())}
    return dict(seeds=len(by_seed), card_credit_reads=(CARD_READS[reads.pop()] if len(reads) == 1 else
                                                       "mixed" if reads else None), by_seed=by_seed, by_year=years)


def handed_back(returned):
    """What the conserved edge hands back to households (the series ``returned``, a person a month in months of mean
    spending), summed by whole year after launch, in the model's units and in dollars. Example: 0.01 every month is
    0.12 a year, $772.80 a person."""
    yearly = _by_year(_array(returned), "sum")
    return dict(units=[float(v) for v in yearly], usd=[float(v * DOLLARS) for v in yearly])


def handed_back_jobs(jobs, arms):
    """``handed_back`` for each arrangement in ``arms`` over the seeds of one cell (its jobs), with the seed means and
    standard errors of each year, in units and in dollars; an arm whose jobs store no ``returned`` reads None."""
    out = {}
    for arm in arms:
        found = [series_of(job, arm, "returned") for job in jobs]
        seen = [handed_back(s) for s in found if s is not None]
        out[arm] = None if not seen else dict(
            seeds=len(seen), by_seed=seen,
            **{unit: [mean_and_se(column) for column in zip(*(s[unit] for s in seen))] for unit in ("units", "usd")})
    return out

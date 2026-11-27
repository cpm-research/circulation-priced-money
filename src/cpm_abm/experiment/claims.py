"""The registered claim, read cell by cell from the cells and their jobs.

Clauses (a) to (d) with (d) under the cash-advance bound, the real cost read-outs, the stress leg under each distress
level (clause (e)), the worse-than-M0 falsifier, near the line, the seed count each cell needs, and the region of
passing cells in each distress slice. In a run that conserves money clause (d) reads
each group's own failed payments (``clause_d_harm``), with the clause as first registered stored beside it, and a
store of the second run carries that claim's note (``claim_note``). Analysis only: nothing here runs the engine.
"""
from itertools import chain, product, repeat

import numpy as np
from scipy.stats import norm

from cpm_abm.economy_abm import EPS
from run_economy_figures import issuer_clause, steady_names
from cpm_abm.experiment.notes import (A0S, CLAIM_ALPHA, CLAIM_ARMS, CLAIM_MARGIN, CLAIM_NOTE, CLASSES, DIP_MARGIN,
                                      DISTRESS, FAIL_USD, GROUP_NAMES, POOL_ARMS, REGION_GROUPS, SECOND_CLAIM_D,
                                      SECOND_CLAIM_D_REGISTERED, SECOND_CLAIM_DEFI, SECOND_CLAIM_NOTE,
                                      SECOND_CLAIM_SEEDS, STRESS_HEADLINE, STRESS_HEADLINE_LABEL, STRESS_LEVELS,
                                      conserves_money, rate_axis, second_run)
from cpm_abm.experiment.second_run import RATES as SECOND_RATES
from cpm_abm.experiment.statistics import (DIP_YEARS, bonferroni_alpha, bonferroni_cells, bootstrap_draws, check,
                                           combined, connected_blocks, dip_months, dips, _finite, limited,
                                           persistent_on_wilson, resampled, seeds_needed, share_reading, t_bounds,
                                           three_way, wilson, wilson_bounds, yearly_dips)
from cpm_abm.experiment.grid import confirmation_seeds
from cpm_abm.experiment.region import better_than_m0, _class_mean, _gap, steady_of, w2_of, worse_than_m0  # noqa: F401

def _counts(job, arm, key):
    """One arm's failure count a person a year after launch (``failure_report``'s a_year), None without the record."""
    record = (job.get("failure_counts") or {}).get(arm)
    return None if record is None else record["a_year"].get(key)


def _run(job, arm):
    """One arm's stored record in a job: S0's own, or the arm's row."""
    return job["S0"] if arm == "S0" else job["arms"].get(arm)


def clause_a(arm, jobs, cell, alpha):
    """Clause (a), CPM operates and pays its own way, at 1 - alpha. Holds when the seeds counting
    (households hold 90% of pool capital in every W2 month and P routes through W2, ``households_pool``) form a share
    whose Wilson lower bound is above one half (15 of 20 seeds, 17 under Bonferroni); no seed records the issuer would
    leave; and nothing rests on outside money: no seed has issuer backing top-ups (a seed without the record does not
    pass). That is what "pays its own way" means (docs/DECISIONS.md, "The pool pays its own way when it runs without
    outside money"): with break-even coupons and free entry the pool's own margin and the joint
    issuer-and-pool test centre on zero by construction, so a bound strictly above zero cannot hold and says nothing
    about the pool. Both are still computed and stored (the margin's lower bound above zero, the joint test's at or
    above zero, as the claim first worded them), with ``holds_as_first_registered``, the clause with them
    required. Leaning against CPM, the clause also asks that the cell read Persistent by the statistics rule (its
    Persistent seeds' Wilson lower bound above one half). Households are the pool's only owners, so the 90% reading
    is a household-owned pool with capital present in every month; how much of its target that capital reaches is
    stored beside it in a run of the second run (``households_pool``) and decides nothing."""
    rows = [j["arms"][arm] for j in jobs]
    seeds = len(rows)
    # A seed counts in a long run only where it counts in both windows (``households_pool``).
    hits = sum(row["households"]["counts"] is True for row in rows)
    share = wilson_bounds(hits, seeds, alpha)
    # The margin and the joint test in W2, and in a long run in each window by its years, the first-registered
    # reading asking them in both.
    at = lambda pair, k: None if pair is None else pair[k]
    steady = steady_of(rows[0])
    margins = {name: check([at(row.get("own_margin_usd_a_year"), k) for row in rows], 0.0, "above", alpha, strict=True)
               for name, k in steady}
    joints = {name: check([at(row.get("joint_usd_a_year"), k) for row in rows], 0.0, "above", alpha)
              for name, k in steady}
    margin = dict(holds=all(block["holds"] for block in margins.values()))
    joint = dict(holds=all(block["holds"] for block in joints.values()))
    leaves = sum(row["X"]["X6"] is True for row in rows)
    topups = [row.get("backing_topup_usd") for row in rows]
    free = all(value is not None and value <= 0.005 for value in topups)
    # In a run of the second run no outside money also means the pool owes its operating
    # provider nothing at any month's end in either window (``accounts.pool_payable``); a seed whose run keeps no such
    # series does not pass that part, and provider says why.
    provider = _provider(rows) if any("pool_payable" in row for row in rows) else None
    owes_nothing = provider is None or provider["owes_nothing"]
    persistent_seeds = cell[arm]["region"]["persistent_seeds"]
    persistent = wilson_bounds(persistent_seeds, seeds, alpha)
    households = bool(share is not None and share[0] > 0.5)
    persists = bool(persistent is not None and persistent[0] > 0.5)
    clean = lambda pair: None if pair is None else [round(value, 4) for value in pair]
    decided = bool(households and leaves == 0 and free and persists and owes_nothing)
    outside = ("falsified" if any(value is not None and value > 0.005 for value in topups)
               or (provider is not None and provider["owing_seeds"]) else
               "supported" if free and owes_nothing else "inconclusive")
    three = three_way([("households_hold_90", share_reading(share)), ("persistent_share", share_reading(persistent)),
                       ("issuer_never_leaves", "falsified" if leaves else "supported"),
                       ("no_outside_money", outside)])
    return dict(**three, holds=decided, holds_as_first_registered=bool(decided and margin["holds"] and joint["holds"]),
                households_seeds=int(hits), seeds=seeds, households_interval=clean(share), households_holds=households,
                **{f"own_margin_{name}": block for name, block in margins.items()},
                **{f"joint_{name}": block for name, block in joints.items()}, issuer_leaves_seeds=int(leaves), issuer_money_free=bool(free),
                backing_topup_usd_mean=None if not _finite(topups).size else round(float(_finite(topups).mean()), 4),
                persistent_seeds=int(persistent_seeds), persistent_interval=clean(persistent),
                persistent_holds=persists, **({} if provider is None else dict(provider=provider)))


def _provider(rows):
    """Clause (a)'s part on the pool's operating provider in a run of the second run (``clause_a``), read at month ends
    from the first month of the early window to the run's end (``accounts.pool_payable``'s read_by_clause): owes_nothing
    when every seed's pool owed it no more than half a cent a person at every such month's end; owing_seeds, the seeds
    where it owed more; undefined_seeds, the seeds with a month that has no value, which do not pass; not_stored_seeds,
    the seeds whose run keeps no record, which do not pass; most_usd, the most owed over the seeds, with beside it,
    deciding nothing, the most over every month after launch and, where the engine keeps it, the most owed on any day
    of a month (most_usd_within_month, with the seeds owing more than half a cent then); reason names each failure."""
    found = [row.get("pool_payable", "not stored") for row in rows]
    stored = [one for one in found if isinstance(one, dict)]
    clause = [one["read_by_clause"] for one in stored]
    owing = sum(one["months_owing"] > 0 for one in clause)
    undefined = sum(one["months_undefined"] > 0 for one in clause)
    missing = len(found) - len(stored)
    within = [one["within_month"] for one in stored if "within_month" in one]
    most = lambda readings: max((one["most_usd"] for one in readings), default=None)
    reasons = [text for count, text in (
        (missing, f"{missing} seeds keep no record of what the pool owes its operating provider (pool_payable)"),
        (undefined, f"{undefined} seeds have a month with no value of what the pool owes its provider")) if count]
    return dict(owes_nothing=bool(not missing and not owing and not undefined), owing_seeds=int(owing),
                undefined_seeds=int(undefined), not_stored_seeds=int(missing), most_usd=most(clause),
                most_usd_after_launch=most([one["after_launch"] for one in stored]),
                most_usd_within_month=most(within),
                owing_within_month_seeds=int(sum(one["months_owing"] > 0 for one in within)) if within else None,
                reason="; ".join(reasons) or None)


def clause_b(arm, jobs, cell, alpha):
    """Clause (b), real cost, at 1 - alpha (the claim and the real cost): the paired t interval
    of the real resources saved against M0 and against S0, $ a person a year (each job's real_saving_usd_a_year total,
    positive favouring the arm); holds when both lower bounds are at or above -$2; saving only where both lower
    bounds are above zero. Example: savings -1, -2, -3 against M0 have mean -2 and 95% lower bound -4.48, so the
    clause fails.

    Where the rows store the saving by window (a run of the second run, ``gains``), the same
    check is stored beside, deciding nothing: by_window, the saving against M0 and against S0 in each window; and
    rail_apart, for the whole run and each window, the saving on the payment-rail lines (card rails and the P rail)
    and on all other lines, each against M0 and against S0. The saving the clause reads includes the rail's."""
    values = {other: [j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in jobs]
              for other in ("M0", "S0")}
    out = {f"against_{other}": check(values[other], CLAIM_MARGIN, "above", alpha) for other in ("M0", "S0")}
    # saving reads the unrounded lower bounds; the stored ones are rounded to 4 places.
    lowers = [t_bounds(values[other], alpha)["lower"] for other in ("M0", "S0")]
    three = three_way([(f"against_{other}", combined(out[f"against_{other}"])) for other in ("M0", "S0")])
    beside = _real_cost_beside(arm, jobs, alpha)
    return dict(out, **three, holds=bool(out["against_M0"]["holds"] and out["against_S0"]["holds"]),
                saving=bool(all(low is not None and low > 0 for low in lowers)), **beside)


def _real_cost_beside(arm, jobs, alpha):
    """Clause (b)'s readings beside it in a run of the second run (``clause_b``), {} where the rows store no saving by
    window: each window's saving and the rail apart, each a check at the clause's margin and level, read by nothing."""
    against = lambda j, other: j["arms"][arm]["against"][other]
    if "real_saving_by_window_usd_a_year" not in against(jobs[0], "M0"):
        return {}
    windows = list(against(jobs[0], "M0")["real_saving_by_window_usd_a_year"])
    spans = ["whole_run", *windows]
    read = lambda values: check(values, CLAIM_MARGIN, "above", alpha)
    by_window, apart = {}, {}
    for window, other in product(windows, ("M0", "S0")):
        values = [against(j, other)["real_saving_by_window_usd_a_year"][window]["total"] for j in jobs]
        by_window.setdefault(window, {})[f"against_{other}"] = read(values)
    for span, other, part in product(spans, ("M0", "S0"), ("rail", "other")):
        values = [against(j, other)["real_saving_rail_apart_usd_a_year"][span][part] for j in jobs]
        apart.setdefault(span, {}).setdefault(f"against_{other}", {})[part] = read(values)
    return dict(by_window=by_window, rail_apart=apart)


def real_cost_readouts(arm, jobs, w):
    """The two read-outs beside clause (b), from counts already stored.

    break_even_rescue_usd: the cost x of one rescued payment at which the arm and the yardstick use the same real
    resources. The arm's real cost with rescues at x is its total less (2 - x) for each rescued share, so x = 2 - (the
    arm's real cost less the yardstick's) / (the arm's rescued shares less the yardstick's), $ and shares a person a
    year, on the cell's seed means (``cell``) and seed by seed (``by_seed``); None where the arm rescues no more than
    the yardstick. Example: the arm uses $1.40 more than M0 with 2.41 rescued shares: x = 2 - 1.40 / 2.41 = 1.42.
    cents_per_dollar_completed: each arm's total real cost a year over its purchases completed a year (the by-class
    record weighted by class size), cents, the seed mean; real_cost_usd_a_year the totals beside."""
    year = 12 / w.months
    out = {}
    for other in ("M0", "S0"):
        used = [None if j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] is None
                else -j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in jobs]
        rescued = _gap([(_counts(j, arm, "bridged_shares"), _counts(j, other, "bridged_shares")) for j in jobs])
        point = lambda more, extra: None if more is None or extra is None or extra <= EPS else FAIL_USD - more / extra
        pairs = [(u, r) for u, r in zip(used, rescued) if u is not None and r is not None]
        out[f"against_{other}"] = dict(
            cell=None if not pairs else (lambda v: None if v is None else round(v, 4))(
                point(float(np.mean([u for u, _ in pairs])), float(np.mean([r for _, r in pairs])))),
            by_seed=[None if point(u, r) is None else round(point(u, r), 4) for u, r in zip(used, rescued)],
            more_real_cost_usd_a_year=None if not pairs else round(float(np.mean([u for u, _ in pairs])), 4),
            more_rescued_shares_a_year=None if not pairs else round(float(np.mean([r for _, r in pairs])), 4))
    cents, totals = {}, {}
    for name in ("S0", "M0", arm):
        total = [_run(j, name)["real_part"]["total"] * year for j in jobs]
        completed = [_class_mean(_run(j, name).get("by_class"), "completed") for j in jobs]
        ratio = [100 * t / c for t, c in zip(total, completed) if c is not None and c > EPS]
        cents[name] = round(float(np.mean(ratio)), 5) if ratio else None
        totals[name] = round(float(np.mean(total)), 4)
    return dict(break_even_rescue_usd=out, cents_per_dollar_completed=cents, real_cost_usd_a_year=totals)


def clause_c(arm, jobs, cell, alpha):
    """Clause (c), at 1 - alpha: failed shortfall payments lower than in M0, in the real failure line's
    unit (each seed's failed shares a person a year, the arm's less M0's, upper bound below zero), and completed trade
    higher (purchases completed plus durables bought, the complete gain's parts against M0, lower bound above zero).
    It holds by construction once a pool lends to payers without a card, so it is reported and is not evidence;
    against S0 is reported beside and read by nothing."""
    out = {}
    for other in ("M0", "S0"):
        failed = _gap([(_counts(j, arm, "fail_shares"), _counts(j, other, "fail_shares")) for j in jobs])
        parts = [j["arms"][arm]["against"][other]["complete_gain_parts_usd_a_year"] for j in jobs]
        completed = [p["purchases_completed"] + p["durables"] for p in parts]
        out[f"against_{other}"] = dict(failed_shares=check(failed, 0.0, "below", alpha, strict=True),
                                       completed_usd=check(completed, 0.0, "above", alpha, strict=True))
    mine = out["against_M0"]
    three = three_way([(f"against_M0.{part}", combined(mine[part])) for part in ("failed_shares", "completed_usd")])
    return dict(out, **three, holds=bool(mine["failed_shares"]["holds"] and mine["completed_usd"]["holds"]),
                evidence=False)


def clause_d(arm, jobs, cell, alpha, under=None):
    """Clause (d), no group loses, at 1 - alpha: every class, launch-wealth quintile
    and billing-cycle group has a t lower bound of its mean complete gain at or above -$2 against S0 at both ends of
    the bracket (sellers' extra sales at face value and at zero) and against M0 at face. Each group is read with the
    same interval check as every other clause (``check``: the t interval and the bootstrap both supported), so a
    disagreement between them shows in near_the_line. A required group with no finite value, or with a value in one
    seed only, has no interval: it does not support the clause, so (d) does not hold, and ``undefined_groups`` names
    it. No issuer transfers exist to net out (the issuer is a pure custodian). The lowest t bound is stored
    with its group, yardstick and end, each group's check under ``groups`` by yardstick and end, and the share worse
    off at each end.

    With ``under`` "bound" the clause is read on the gains under the cash-advance bound, each
    end's ``bound`` (``differences``), with the same groups, yardsticks, ends, intervals and margin; a seed that stores
    no bound has no value in any group, so the clause does not hold there."""
    lowest, undefined, components = None, [], []
    readings =(("S0", "face"), ("S0", "zero"), ("M0", "face"))
    labels = [f"{other}_{end}" for other, end in readings]
    checks, passes = {label: {} for label in labels}, dict.fromkeys(labels, True)

    def gains(j, other, end):
        """One seed's end of the complete gain against ``other``, as stored or under ``under``."""
        stored = j["arms"][arm]["against"][other]["complete_gain"][end]
        return stored if under is None else stored.get(under, {})

    # Every group's column of seeds, each (yardstick, end, group kind) read once into a seeds x groups table, then one
    # flat pass over the columns in the order the clause reads them.
    size = dict(zip(REGION_GROUPS, map(len, (CLASSES, GROUP_NAMES["quintile"], GROUP_NAMES["cycle"]))))
    read = lambda j, other, end, name: [np.nan if v is None else v for v in gains(j, other, end).get(
        f"gain_usd_a_year_by_{name}", [None] * size[name])]
    tables = {(other, end, name): np.array([read(j, other, end, name) for j in jobs], float)
              for (other, end), name in product(readings, REGION_GROUPS)}
    columns = chain.from_iterable(zip(repeat(other), repeat(end), GROUP_NAMES[name], values.T)
                                  for (other, end, name), values in tables.items())
    for other, end, group, column in columns:
        label = f"{other}_{end}"
        result = check(column, CLAIM_MARGIN, "above", alpha)
        checks[label][group] = result
        components.append((f"{label}.{group}", combined(result)))
        passes[label] = bool(passes[label] and result["holds"])
        if result["lower"] is None:
            undefined.append(dict(group=group, against=other, end=end, seeds=result["seeds"]))
        low = -np.inf if result["lower"] is None else result["lower"]
        if lowest is None or low < lowest[0]:
            lowest = (low, result["mean"], group, other, end)
    worse_off = lambda j, other, end: gains(j, other, end).get("worse_off", np.nan)
    worse = {f"{other}_{end}": round(float(np.mean([worse_off(j, other, end) for j in jobs])), 4)
             for other, end in readings}
    low = None if lowest is None or not np.isfinite(lowest[0]) else round(lowest[0], 4)
    three = three_way(components)
    return dict(**three, holds=bool(all(passes.values()) and not undefined), passes=passes,
                lowest=None if lowest is None else dict(lower=low, mean=lowest[1], group=lowest[2],
                                                        against=lowest[3], end=lowest[4]),
                undefined_groups=undefined, groups=checks,
                worse_off_share=worse, issuer_transfers="none: the issuer is a pure custodian")


def clause_d_bound(arm, jobs, cell, alpha):
    """Clause (d) read a second time on the gains under the cash-advance bound: a cell counts in the
    region only if it passes both as stored and under the bound. It has the same fields as clause (d)."""
    return clause_d(arm, jobs, cell, alpha, under="bound")


def clause_d_harm(arm, jobs, cell, alpha):
    """Clause (d), no group is harmed, for a run that conserves money, at 1 - alpha: for each
    of the run's steady windows (the rows' own, years 6 to 10 and years 21 to 25 in the second run), each yardstick
    (S0 and M0) and each of the eleven groups (the four classes, the five launch-wealth quintiles, the short and the
    long billing cycle, ``gains.failed_by_group``), the seed mean of the group's own payments that did not complete,
    as payer (its failed shares of bills and wages plus its declined shares of card-eligible purchases), the arm less
    the yardstick paired by seed, a person a year, has an upper bound at or below one failed payment
    (``DIP_MARGIN``, the stress dip's margin, in the same unit) on the t interval and on the bootstrap (``check``, read
    "below"): 11 groups x 2 yardsticks x 2 windows, 44 checks, and the clause holds only when every one is supported.
    A group defined in fewer than two seeds has no interval: it does not support the clause and ``undefined_groups``
    names it, as does every group of a seed that stores no failed_by_group. Stored: each check under ``groups`` by
    yardstick and window (label "S0_years_6_to_10" and so on), which labels pass (``passes``), and the highest upper
    bound with its group, yardstick and window (``highest``; a group with no interval counts highest). Example, 20
    seeds: a difference of 0.5 in every seed (with a spread of 0.1) is supported; 1.5 is falsified; values spread
    across the margin read inconclusive."""
    rows = [j["arms"][arm] for j in jobs]
    windows = [name for name, _ in steady_of(rows[0])]
    size = dict(zip(REGION_GROUPS, (len(GROUP_NAMES[name]) for name in REGION_GROUPS)))
    places = tuple(product(windows, ("S0", "M0"), REGION_GROUPS))
    read = lambda row, window, other, name: [np.nan if v is None else v for v in (
        ((row.get("failed_by_group") or {}).get("by_window") or {}).get(window, {}).get(f"against_{other}", {})
        .get(name, [None] * size[name]))]
    tables = {place: np.array([read(row, *place) for row in rows], float) for place in places}
    # Every group's column of seeds, in the order (window, yardstick, kind, group), read in one flat pass.
    columns = chain.from_iterable(zip(repeat(window), repeat(other), GROUP_NAMES[name], values.T)
                                  for (window, other, name), values in tables.items())
    labels = [f"{other}_{window}" for window, other in product(windows, ("S0", "M0"))]
    checks, passes = {label: {} for label in labels}, dict.fromkeys(labels, True)
    highest, undefined, components = None, [], []
    for window, other, group, column in columns:
        label = f"{other}_{window}"
        result = check(column, DIP_MARGIN, "below", alpha)
        checks[label][group] = result
        components.append((f"{label}.{group}", combined(result)))
        passes[label] = bool(passes[label] and result["holds"])
        if result["upper"] is None:
            undefined.append(dict(group=group, against=other, window=window, seeds=result["seeds"]))
        high = np.inf if result["upper"] is None else result["upper"]
        if highest is None or high > highest[0]:
            highest = (high, result["mean"], group, other, window)
    upper = None if highest is None or not np.isfinite(highest[0]) else round(highest[0], 4)
    # A seed whose row stores no failed_by_group, or lacks one of the windows, has no value in any group there: it
    # does not support the clause, however many other seeds do, and is named (seeds_without_record).
    stored = lambda row: set((row.get("failed_by_group") or {}).get("by_window") or {})
    lacking = [job["seed"] for job, row in zip(jobs, rows) if not set(windows) <= stored(row)]
    if lacking:
        components.append(("seeds_without_record", "inconclusive"))
    three = three_way(components)
    return dict(**three, holds=bool(all(passes.values()) and not undefined and not lacking), passes=passes,
                seeds_without_record=lacking,
                highest=None if highest is None else dict(upper=upper, mean=highest[1], group=highest[2],
                                                          against=highest[3], window=highest[4]),
                undefined_groups=undefined, groups=checks, margin=DIP_MARGIN, windows=windows,
                unit="payments that did not complete as payer a person a year: unpaid shares of bills and wages plus "
                     "declined shares of card-eligible purchases")


CLAUSES = dict(a=clause_a, b=clause_b, c=clause_c, d=clause_d)
# In a run that conserves money clause (d) reads each group's own failed payments; the clause as first registered and
# its reading under the cash-advance bound are stored beside it under names that say so.
CLAUSES_CONSERVED = dict(CLAUSES, d=clause_d_harm)


def clauses_of(w):
    """The clauses (a) to (d) a run on the Economy ``w`` is read on: ``CLAUSES``, and in a run that conserves
    money ``CLAUSES_CONSERVED``, with (d) on each group's own failed payments. With no Economy, ``CLAUSES``."""
    return CLAUSES_CONSERVED if w is not None and conserves_money(w) else CLAUSES


PASS_CLAUSES = ("a", "b", "d")        # a cell passes on these; (c) is reported, (e) is the highest level withstood


def stress_leg(arm, cell, level_jobs, base_jobs, alpha, w=None):
    """One distress level's leg of clause (e) at its alpha (level 0's Bonferroni level): clauses (a)
    to (d) on the level's paired run (``clauses_of``), and the dip's upper
    bound against S0's and M0's at most one failed payment a year: the cumulative excess over the
    36 months from the first stress month (``dips``, read from the run's Economy ``w``: months 25 to 60 in the first run
    and with no Economy; months 121 to 156 in the second run) per consumer unit a year, the 36-month sum over 3;
    withstands when all hold. The sums are stored beside (dip_36_months_*). Example: a dip of 2.4 failed payments
    over the 36 months against S0's in every seed is 0.8 a year and is withstood; 3.6 is 1.2 a year and is not."""
    clauses = {key: clause(arm, level_jobs, cell, alpha) for key, clause in clauses_of(w).items()}
    legs = {key: block["holds"] for key, block in clauses.items()}
    seen = dips(arm, level_jobs, base_jobs, w)
    spans = [span for span in seen["years"] if span is not None]
    years = float(np.mean(spans)) if w is not None and spans else DIP_YEARS
    dip = {key: check(yearly_dips(seen[key], seen["years"]), DIP_MARGIN, "below", alpha)
           for key in ("against_S0", "against_M0")}
    own = _finite(seen["own"])
    total = lambda key: None if dip[key]["mean"] is None else round(dip[key]["mean"] * years, 4)
    # Every clause's full block is kept: clause (b)'s intervals, clause (a)'s first-worded
    # reading (holds_as_first_registered) and each clause's three-way reading; the leg's own three-way reading names
    # the clause or dip that decided it.
    three = three_way([(key, block["reading"]) for key, block in clauses.items()]
                      + [(f"dip_{key}", combined(d)) for key, d in dip.items()])
    return dict(withstands=bool(all(legs.values()) and all(d["holds"] for d in dip.values())), legs=legs,
                clauses=clauses, **three, dip=dip,
                dip_own_mean=None if not own.size else round(float(own.mean()), 4),
                dip_a_year=None if not own.size else round(float(own.mean()) / years, 4),
                dip_36_months_against_S0=total("against_S0"), dip_36_months_against_M0=total("against_M0"),
                alpha=alpha)


def fire_interval_falsifier(summary, rows, seeds):
    """A cell where V2 or V4 is shown worse treated as a cell where the worse-than-M0 falsifier (X4) fires, as ``decide``
    forms it: V2 and V4 are readings of the cell's seed mean, with no seed-level threshold, so every paired seed
    counts worse and none is Persistent; the verdict is Against CPM (naming the issuer as ``decide`` does), and the
    region reading follows (no Persistent seed, so "not persistent" unless an earlier condition fails). Applied in
    place to the ``summary`` of one pool arm (``decide``'s, or a stored one formed before this rule); ``rows``
    are the arm's rows in the cell's jobs. Idempotent."""
    summary["X4"] = True
    if "verdict" in summary and not str(summary["verdict"]).startswith("Against"):
        verdict = "Against CPM"
        leaves = float(np.mean([(row.get("X") or {}).get("X6") is True for row in rows])) if rows else 0.0
        if leaves > 0.5:
            verdict += issuer_clause(all(row.get("issuer_limit") for row in rows))
        summary["verdict"] = verdict
    if "seed_verdicts" in summary:
        summary["seed_verdicts"] = ["Against CPM"] * seeds
    if "worse_than_M0_seeds" in summary:
        summary["worse_than_M0_seeds"] = int(seeds)
    if "persistent_share" in summary:
        summary.update(persistent_share=0.0, persistent_share_interval=wilson(0, seeds))
    region_reading = summary.get("region")
    if region_reading is not None:
        region_reading.update(persistent_seeds=0, persistent_share=0.0, persistent_interval=wilson(0, seeds),
                              persistent=False, persistent_majority=False)
        for key in ("verdict", "verdict_majority"):
            if key in region_reading and region_reading[key] not in ("declared limit", "no pool"):
                region_reading[key] = "not persistent"
        if "in_region" in region_reading:
            region_reading["in_region"] = region_reading.get("verdict") == "stable"


def _near_parts(block, prefix=""):
    """The names of the interval checks inside a clause block that are near the line."""
    found = []
    for key, value in block.items():
        if isinstance(value, dict):
            if value.get("near_the_line") is True:
                found.append(prefix + key)
            found += _near_parts(value, prefix + key + ".")
    return found


def claim_note(w):
    """The claim's note a store of a run on the Economy ``w`` carries: ``CLAIM_NOTE`` word for word in the first run,
    and in a run of the second run (``second_run``) ``SECOND_CLAIM_NOTE``, filled from
    the run's own Economy: its windows by their years, its cells for M1 and M2 (``bonferroni_cells``: 42 and 35 with
    six rates), DeFi as the run sets it, clause (d) on each group's own failed payments where the run conserves
    money (as first registered otherwise), and the dip's months from its first stress month (``dip_months``: 121 to
    156 in the second run)."""
    if not second_run(w):
        return CLAIM_NOTE
    # Random distress years fall on each seed's own months, so the note names no month there.
    span = None if getattr(w, "distress_dates", "dated") == "random" else dip_months(w)
    months = ("each seed's own months from its first stress month" if span is None
              else f"months {span[0] + 1} to {span[1]} after launch")
    return SECOND_CLAIM_NOTE.format(
        windows=" and ".join(name.replace("_", " ") for name in steady_names(w)),
        cells_m1=bonferroni_cells("M1", w), cells_m2=bonferroni_cells("M2", w),
        rates=len(SECOND_RATES), defi=SECOND_CLAIM_DEFI[getattr(w, "usdc_yield", "reserve")],
        clause_d=SECOND_CLAIM_D if conserves_money(w) else SECOND_CLAIM_D_REGISTERED, dip_months=months,
        seeds=SECOND_CLAIM_SEEDS)


def claim_statistics(cells, jobs, w):
    """The registered claim read cell by cell (``CLAIM_NOTE``), added to the cells in place, with the map-wide
    readings returned for summary.json: the Bonferroni levels, "holds somewhere", the region by distress slice as a
    connected block, and the confirmation seed count (``confirmation_seeds``).

    Adds to each pool arm of every cell better_than_M0 (V2 and V4); to M1 and M2 of each cell at distress 0 claim
    (each clause's status and numbers, all, all_bonferroni, near_the_line, underpowered, in_region) and real_cost
    (clause (b)'s intervals and flags with its two read-outs); and to M1 and M2 of each cell under distress
    stress_leg (``stress_leg`` at the Bonferroni level, with underpowered and in_region). ``jobs`` must carry their
    failure counts (as the run returns them, or from failure_counts.json); the grid's convention is ``w``'s. Every
    bootstrap inside draws the run's resamples (``bootstrap_draws``: 200,000 in a run of the second run)."""
    with resampled(bootstrap_draws(w)):
        return _claim_statistics(cells, jobs, w)


def _claim_statistics(cells, jobs, w):
    """``claim_statistics`` at the resamples in force."""
    returned = bool(getattr(w, "lender_income_recirculated", False))
    key = lambda item: (float(item["r_out"]), float(item["a0"]), float(item["distress"]))
    index = {key(c): c for c in cells if c is not None}
    by_cell = {}
    for job in jobs:
        if bool(job["recirculated"]) == returned:
            by_cell.setdefault(key(job), []).append(job)
    for group in by_cell.values():
        group.sort(key=lambda job: job["seed"])
    stats = dict(note=claim_note(w), bonferroni={}, holds_somewhere={}, regions={})
    if second_run(w):
        stats["regions_bonferroni"] = {}   # the region at each arm's stricter level beside it
    for ((rate, a0, level), cell), arm in product(index.items(), POOL_ARMS):
        if arm in cell and by_cell.get((rate, a0, level)):
            group = by_cell[(rate, a0, level)]
            better = better_than_m0(arm, rate, group, w)
            cell[arm]["better_than_M0"] = better
            cell[arm]["worse_than_M0"] = worse_than_m0(cell[arm], better)
            # V2 or V4 shown worse fires the worse-than-M0 falsifier as trade or a harmed group does, before any
            # clause reads the cell's Persistent count.
            if better["shown_worse"]:
                fire_interval_falsifier(cell[arm], [j["arms"][arm] for j in group], len(group))
    for arm in CLAIM_ARMS:
        _claim_arm(arm, index, by_cell, stats, w)
    stats["seeds"] = confirmation_seeds(index, by_cell, w)
    return stats


def _claim_arm(arm, index, by_cell, stats, w):
    """``claim_statistics`` for one claim arm: its Bonferroni level, every stress leg, every level-0 claim, the region by
    distress slice and "holds somewhere", added to the cells in ``index`` and to ``stats`` in place."""
    mine = {k: c for k, c in index.items() if arm in c and by_cell.get(k)}
    if not mine:
        return
    alpha = bonferroni_alpha(arm, w)
    stats["bonferroni"][arm] = dict(cells=bonferroni_cells(arm, w), alpha=alpha, confidence=1 - alpha,
                                    z=float(norm.ppf(1 - alpha / 2)))
    # Every level's leg first, so clause (e) reads them in order.
    for (rate, a0, level), cell in mine.items():
        if level != 0:
            _stress_cell(arm, (rate, a0, level), cell, by_cell, alpha, w)
    for (rate, a0, level), cell in mine.items():
        if level == 0:
            _claim_cell(arm, (rate, a0, level), cell, index, by_cell, alpha, w)
    # The region by distress slice: the largest edge-joined block of passing cells that are not underpowered; in a
    # run of the second run the region of cells passing at the stricter level beside it.
    stats["regions"][arm] = [_region_slice(arm, level, mine, index, w) for level in DISTRESS]
    if "regions_bonferroni" in stats:
        stats["regions_bonferroni"][arm] = [_region_slice(arm, level, mine, index, w, strict=True)
                                            for level in DISTRESS]
    stats["holds_somewhere"][arm] = [[rate, a0] for (rate, a0, level), cell in mine.items()
                                     if level == 0 and cell[arm]["claim"]["all_bonferroni"]]


def _stress_cell(arm, place, cell, by_cell, alpha, w):
    """One cell's stress leg under distress (``stress_leg``, at the arm's Bonferroni level ``alpha``) with its seed
    count, and clause (b)'s intervals and read-outs at that level, added to ``cell`` in place; ``place`` is its
    (r_out, a0, distress)."""
    rate, a0, level = place
    if limited(arm, rate, w):
        cell[arm]["stress_leg"] = dict(withstands=False, status="not applicable", reason="declared limit",
                                       reading="declared limit", decided_by=[],
                                       worse_than_M0=cell[arm]["worse_than_M0"])
        return
    base_jobs = by_cell.get((rate, a0, 0.0), [])
    leg = stress_leg(arm, cell, by_cell[place], base_jobs, alpha, w)
    # The seed count reads the dips' unrounded spreads; the stored sd is rounded to 4 places.
    seen = dips(arm, by_cell[place], base_jobs, w)
    spread = max((sd for sd in (t_bounds(yearly_dips(seen[key], seen["years"]))["sd"] for key in leg["dip"])
                  if sd is not None), default=None)
    needed = seeds_needed(spread, DIP_MARGIN, alpha)
    worse = cell[arm]["worse_than_M0"]
    if worse["fires"]:
        leg.update(reading="falsified", decided_by=[f"worse_than_M0.{part}" for part in worse["fired"]]
                   + [name for name in leg["decided_by"] if leg["reading"] == "falsified"])
    leg.update(seeds_needed=needed, underpowered=bool(needed is None or needed > cell["seeds"]),
               worse_than_M0=worse)
    cell[arm]["stress_leg"] = leg
    # Clause (b)'s intervals and its two read-outs at this level too, at the stress leg's level.
    cell[arm]["real_cost"] = dict(at_bonferroni=leg["clauses"]["b"], holds=leg["legs"]["b"],
                                  saving=leg["clauses"]["b"]["saving"], **real_cost_readouts(arm, by_cell[place], w))


def _clause_entry(clause, arm, group, cell, alpha):
    """One clause read at 95% and at the Bonferroni level ``alpha``, as a cell's claim block stores it."""
    at_95, at_b = clause(arm, group, cell, CLAIM_ALPHA), clause(arm, group, cell, alpha)
    return dict(status="pass" if at_95["holds"] else "fail", status_bonferroni="pass" if at_b["holds"] else "fail",
                reading=at_95["reading"], decided_by=at_95["decided_by"], reading_bonferroni=at_b["reading"],
                decided_by_bonferroni=at_b["decided_by"], at_95=at_95, at_bonferroni=at_b)


def _cell_reading(block, fired, suffix, clauses=PASS_CLAUSES):
    """The cell's three-way reading at 95% (``suffix`` "") or the Bonferroni level ("_bonferroni") from ``clauses``,
    (a), (b) and (d) as stored, and the parts of worse than M0 that fired, each deciding clause named with the
    comparison or group inside it that decided it. With (d) under the cash-advance bound among ``clauses`` the
    reading is the worse of the two (d) readings."""
    three = three_way([(f"({name})", block[name]["reading" + suffix]) for name in clauses]
                      + [(name, "falsified") for name in fired])

    def named(name):
        """The entries for one deciding name: a clause "(x)" once for each comparison or group inside it that decided
        it ("(x)." when its own reading names none), a fired part of worse than M0 as it is."""
        if not name.startswith("("):
            return [name]
        return [f"{name}.{part}" for part in block[name[1:-1]]["decided_by" + suffix] or [""]]

    decided = chain.from_iterable(map(named, three["decided_by"]))
    return {"reading" + suffix: three["reading"], "decided_by" + suffix: [entry.rstrip(".") for entry in decided]}


def _withstood(arm, rate, a0, index, passes_0):
    """Clause (e) for a cell at (r_out, a0): the levels in order, stopping at the first failure or the first level not
    run; the levels tested and the highest withstood."""
    tested, highest = [], 0.0
    for stress in STRESS_LEVELS:
        leg = index.get((rate, a0, stress), {}).get(arm, {}).get("stress_leg")
        if leg is None or not passes_0:
            break
        tested.append(dict(distress=stress, withstands=leg["withstands"]))
        if not leg["withstands"]:
            break
        highest = stress
    return tested, highest


def _headline(tested, highest):
    """Clause (e)'s headline (the harsh stress): whether the cell withstands the headline level,
    2 points, 2009's wage loss before unemployment insurance, read from the levels tested in order. True when the
    highest level withstood reaches it; False when a level up to it was tested and not withstood; None when (e) is not
    applicable or the headline level was not run. Examples: withstanding 0.5% to 2% is True; 0.5% and 1% withstood
    and 1.5% not is False; only 0.5% and 1% run, both withstood, is None."""
    failed = bool(tested) and not tested[-1]["withstands"]
    withstands = True if highest >= STRESS_HEADLINE - 1e-12 else (False if failed else None)
    return dict(distress=STRESS_HEADLINE, label=STRESS_HEADLINE_LABEL, withstands=withstands)


def _claim_cell(arm, place, cell, index, by_cell, alpha, w):
    """One level-0 cell's claim block (each clause at 95% and at the Bonferroni level ``alpha``, worse than M0, the
    three-way readings, clause (e), all, near the line, the seed count) and clause (b)'s real cost, added to ``cell``
    in place; ``place`` is its (r_out, a0, distress)."""
    rate, a0, _ = place
    group = by_cell[place]
    # In a run that conserves money (d) reads each group's own failed payments, and the clause as first registered and
    # its reading under the cash-advance bound are stored under names that say so, read by no verdict.
    conserved = conserves_money(w)
    if limited(arm, rate, w):
        skip = dict(status="not applicable", status_bonferroni="not applicable", reason="declared limit")
        limit = dict(skip, reading="declared limit", reading_bonferroni="declared limit")
        if conserved:
            cell[arm]["claim"] = dict(**{name: dict(limit) for name in "abcde"}, d_as_first_registered=dict(limit),
                                      d_bound_as_first_registered=dict(limit), all=False, all_bonferroni=False,
                                      near_the_line=False, near_the_line_parts=[], underpowered=None,
                                      seeds_needed=None, in_region=False, in_region_bonferroni=False,
                                      reading="declared limit", decided_by=[],
                                      reading_bonferroni="declared limit", decided_by_bonferroni=[],
                                      worse_than_M0=cell[arm]["worse_than_M0"])
            return
        cell[arm]["claim"] = dict(**{name: dict(skip, reading="declared limit",
                                                reading_bonferroni="declared limit") for name in "abcde"},
                                  d_bound=dict(skip, reading="declared limit", reading_bonferroni="declared limit"),
                                  all=False, all_bonferroni=False, all_as_built=False,
                                  all_bonferroni_as_built=False,
                                  near_the_line=False, near_the_line_parts=[], underpowered=None,
                                  seeds_needed=None, in_region=False, reading="declared limit",
                                  decided_by=[], reading_bonferroni="declared limit",
                                  decided_by_bonferroni=[],
                                  **{key + "_as_built": value for key, value in (
                                      ("reading", "declared limit"), ("decided_by", []),
                                      ("reading_bonferroni", "declared limit"), ("decided_by_bonferroni", []))},
                                  worse_than_M0=cell[arm]["worse_than_M0"])
        return
    clauses = clauses_of(w)
    block = {name: _clause_entry(clause, arm, group, cell, alpha) for name, clause in clauses.items()}
    if conserved:
        block["d_as_first_registered"] = _clause_entry(clause_d, arm, group, cell, alpha)
        block["d_bound_as_first_registered"] = _clause_entry(clause_d_bound, arm, group, cell, alpha)
    else:
        # Clause (d) read a second time under the cash-advance bound, in its own block.
        block["d_bound"] = _clause_entry(clause_d_bound, arm, group, cell, alpha)
    # The four parts of "worse than M0", each named with whether it fired; any firing falsifies the cell (its
    # Persistent count, and so (a), already follow, ``fire_interval_falsifier``).
    worse = cell[arm]["worse_than_M0"]
    block["worse_than_M0"] = worse
    fired = [f"worse_than_M0.{part}" for part in worse["fired"]]
    # By default the cell's reading takes the worse of (d) as stored and under the bound, and the reading as stored is
    # kept beside; in a run that conserves money it reads (a), (b) and (d) alone.
    for suffix in ("", "_bonferroni"):
        if conserved:
            block.update(_cell_reading(block, fired, suffix))
            continue
        block.update({key + "_as_built": value for key, value in _cell_reading(block, fired, suffix).items()})
        block.update(_cell_reading(block, fired, suffix, PASS_CLAUSES + ("d_bound",)))
    # A cell passes when (a), (b) and (d) are supported; (c) is reported and is not evidence, and (e) is
    # read for passing cells, as the highest level withstood.
    passes_0 = all(block[name]["status"] == "pass" for name in PASS_CLAUSES)
    tested, highest = _withstood(arm, rate, a0, index, passes_0)
    state = ("not applicable" if not passes_0 or not tested else
             "pass" if highest >= STRESS_LEVELS[0] else "fail")
    block["e"] = dict(status=state, status_bonferroni=state, highest_level=highest if tested else None,
                      tested=tested, reason=None if passes_0 else "(a), (b) and (d) do not all pass at level 0",
                      headline=_headline(tested, highest))
    passes_b = bool(all(block[name]["status_bonferroni"] == "pass" for name in PASS_CLAUSES))
    if conserved:
        # In a run that conserves money a cell passes on (a), (b) and (d), which the region and "holds somewhere"
        # read.
        block.update(all=bool(passes_0), all_bonferroni=passes_b)
    else:
        # all and all_bonferroni ask (d) both as stored and under the cash-advance bound, so the region and "holds
        # somewhere" do too; the readings as stored are kept beside.
        block["all_as_built"] = bool(passes_0)
        block["all_bonferroni_as_built"] = passes_b
        block["all"] = bool(passes_0 and block["d_bound"]["status"] == "pass")
        block["all_bonferroni"] = bool(passes_b and block["d_bound"]["status_bonferroni"] == "pass")
    parts = _near_parts({name: block[name]["at_95"] for name in clauses})
    # The Persistent share near one half on its unrounded interval, from the stored count (the stored interval is
    # rounded for display).
    if persistent_on_wilson(cell[arm]["region"]["persistent_seeds"], cell["seeds"])[1]:
        parts.insert(0, "persistent_share")
    block["near_the_line"], block["near_the_line_parts"] = bool(parts), parts
    # The seed count reads the savings' unrounded spreads; the stored sd is rounded to 4 places.
    spreads = [t_bounds([j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in group])["sd"]
               for other in ("M0", "S0")]
    spread = max((sd for sd in spreads if sd is not None), default=None)
    needed = seeds_needed(spread, abs(CLAIM_MARGIN), alpha)
    block.update(seeds_needed=needed, underpowered=bool(needed is None or needed > cell["seeds"]),
                 in_region=False, **({"in_region_bonferroni": False} if second_run(w) else {}))
    cell[arm]["claim"] = block
    cell[arm]["real_cost"] = dict(at_95=block["b"]["at_95"], at_bonferroni=block["b"]["at_bonferroni"],
                                  holds=block["b"]["status"] == "pass", saving=block["b"]["at_95"]["saving"],
                                  **real_cost_readouts(arm, group, w))


def _region_slice(arm, level, mine, index, w=None, strict=False):
    """One distress slice of the arm's region: its passing cells, their edge-joined blocks and the largest, whose
    cells are marked in_region in place (level 0 on the claim block, else on the stress leg). Cells join along the
    run's outside rates (``rate_axis``): the grid's for a run of the grid.

    In a run of the second run on the Economy ``w`` the slice is labelled: the region as above
    reads each cell at 95%, pointwise, and with ``strict`` the region reads all_bonferroni, each cell at the arm's
    stricter level, marking in_region_bonferroni; and a stressed slice's cell also needs its no-distress cell not to
    be underpowered, in both. Example: a level-0 cell passing at 95% and not at the stricter level is in the
    pointwise region only."""
    second = second_run(w)
    passed = "all_bonferroni" if strict else "all"
    rates = rate_axis(rate for rate, _, _ in mine)
    passing = set()
    for (rate, a0, at), cell in mine.items():
        if at != level:
            continue
        if level == 0:
            block = cell[arm]["claim"]
            ok = block[passed] and not block["underpowered"]
        else:
            base = index.get((rate, a0, 0.0), {}).get(arm, {}).get("claim", {})
            leg = cell[arm]["stress_leg"]
            # The level-0 cell must pass all, which includes (d) under the cash-advance bound: (e) is tested only for
            # a cell passing (a), (b) and (d), so this adds the bound alone; in a run that conserves money all is
            # (a), (b) and (d), so it adds nothing.
            ok = bool((base.get("e", {}).get("highest_level") or 0.0) >= level and not leg.get("underpowered", True)
                      and base.get(passed, False) and not (second and base.get("underpowered", True)))
        if ok:
            passing.add((rates.index(rate), A0S.index(a0)))
    blocks = connected_blocks(passing)
    region = blocks[0] if blocks else []
    mark = "in_region_bonferroni" if strict else "in_region"
    for row, column in region:
        target = mine[(rates[row], A0S[column], level)][arm]
        (target["claim"] if level == 0 else target["stress_leg"])[mark] = True
    named = lambda block: [[rates[row], A0S[column]] for row, column in block]
    found = dict(distress=level, passing=named(sorted(passing)), blocks=[named(b) for b in blocks],
                 region=named(region), tied=bool(len(blocks) > 1 and len(blocks[1]) == len(blocks[0])))
    if second:
        found["reads"] = ("each cell at the arm's stricter level (all_bonferroni)" if strict
                          else "each cell at 95%, pointwise (all)")
    return found

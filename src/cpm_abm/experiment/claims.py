"""The registered claim, read cell by cell from the decided cells and their jobs.

Clauses (a) to (d) with (d) under the cash-advance bound, the real cost read-outs, the stress leg under each distress
level (clause (e)), the worse-than-M0 falsifier, near the line, the seed count each cell needs, and the region of
passing cells in each distress slice. Analysis only: nothing here runs the engine.
"""
from itertools import product

import numpy as np
from scipy.stats import norm

from cpm_abm.economy_abm import EPS
from run_economy_figures import issuer_clause
from cpm_abm.experiment.notes import (A0S, CLAIM_ALPHA, CLAIM_ARMS, CLAIM_MARGIN, CLAIM_NOTE, CLASSES, DIP_MARGIN,
                                      DISTRESS, FAIL_USD, GROUP_NAMES, POOL_ARMS, REGION_GROUPS, STRESS_HEADLINE,
                                      STRESS_HEADLINE_LABEL, STRESS_LEVELS, rate_axis)
from cpm_abm.experiment.statistics import (DIP_YEARS, bonferroni_alpha, bonferroni_cells, check, combined,
                                           connected_blocks, dips, _finite, limited, persistent_on_wilson, seeds_needed,
                                           share_reading, t_bounds, three_way, wilson, wilson_bounds, yearly_dips)
from cpm_abm.experiment.grid import confirmation_seeds
from cpm_abm.experiment.region import better_than_m0, _class_mean, _gap, w2_of, worse_than_m0

def _counts(job, arm, key):
    """One arm's failure count a person a year after launch (``failure_report``'s a_year), None without the record."""
    record = (job.get("failure_counts") or {}).get(arm)
    return None if record is None else record["a_year"].get(key)


def _run(job, arm):
    """One arm's stored record in a job: S0's own, or the arm's row."""
    return job["S0"] if arm == "S0" else job["arms"].get(arm)


def clause_a(arm, jobs, cell, alpha):
    """Clause (a), CPM operates and pays its own way, at 1 - alpha (the claim row). Holds when the seeds counting
    (households hold 90% of pool capital in every W2 month and P routes through W2, ``households_pool``) form a share
    whose Wilson lower bound is above one half (15 of 20 seeds, 17 under Bonferroni); no seed records the issuer would
    leave; and nothing rests on outside money: no seed has issuer backing top-ups (a seed without the record does not
    pass). That is what "pays its own way" has meant since 5 Nov (the row "The pool pays its own way when it runs
    without outside money"): with break-even coupons and free entry the pool's own margin and the joint
    issuer-and-pool test centre on zero by construction, so a bound strictly above zero cannot hold and says nothing
    about the pool. Both are still computed and stored (the margin's lower bound above zero, the joint test's at or
    above zero, as the claim row first worded them), with ``holds_as_first_registered``, the clause with them
    required. Leaning against CPM, the clause also asks that the cell read Persistent by the statistics rule (its
    Persistent seeds' Wilson lower bound above one half)."""
    rows = [j["arms"][arm] for j in jobs]
    seeds = len(rows)
    hits = sum(row["households"]["counts"] is True for row in rows)
    share = wilson_bounds(hits, seeds, alpha)
    margin = check([w2_of(row.get("own_margin_usd_a_year")) for row in rows], 0.0, "above", alpha, strict=True)
    joint = check([w2_of(row.get("joint_usd_a_year")) for row in rows], 0.0, "above", alpha)
    leaves = sum(row["X"]["X6"] is True for row in rows)
    topups = [row.get("backing_topup_usd") for row in rows]
    free = all(value is not None and value <= 0.005 for value in topups)
    persistent_seeds = cell[arm]["region"]["persistent_seeds"]
    persistent = wilson_bounds(persistent_seeds, seeds, alpha)
    households = bool(share is not None and share[0] > 0.5)
    persists = bool(persistent is not None and persistent[0] > 0.5)
    clean = lambda pair: None if pair is None else [round(value, 4) for value in pair]
    decided = bool(households and leaves == 0 and free and persists)
    outside = ("falsified" if any(value is not None and value > 0.005 for value in topups) else
               "supported" if free else "inconclusive")
    three = three_way([("households_hold_90", share_reading(share)), ("persistent_share", share_reading(persistent)),
                       ("issuer_never_leaves", "falsified" if leaves else "supported"),
                       ("no_outside_money", outside)])
    return dict(**three, holds=decided, holds_as_first_registered=bool(decided and margin["holds"] and joint["holds"]),
                households_seeds=int(hits), seeds=seeds, households_interval=clean(share), households_holds=households,
                own_margin_W2=margin, joint_W2=joint, issuer_leaves_seeds=int(leaves), issuer_money_free=bool(free),
                backing_topup_usd_mean=None if not _finite(topups).size else round(float(_finite(topups).mean()), 4),
                persistent_seeds=int(persistent_seeds), persistent_interval=clean(persistent),
                persistent_holds=persists)


def clause_b(arm, jobs, cell, alpha):
    """Clause (b), real cost, at 1 - alpha (the claim row and the real cost row, 12 Nov, night): the paired t interval
    of the real resources saved against M0 and against S0, $ a person a year (each job's real_saving_usd_a_year total,
    positive favouring the arm); holds when both lower bounds are at or above -$2; saving only where both lower
    bounds are above zero. Hand case: savings -1, -2, -3 against M0 have mean -2 and 95% lower bound -4.48, so the
    clause fails."""
    values = {other: [j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in jobs]
              for other in ("M0", "S0")}
    out = {f"against_{other}": check(values[other], CLAIM_MARGIN, "above", alpha) for other in ("M0", "S0")}
    # saving reads the unrounded lower bounds; the stored ones are rounded to 4 places (the 13 Nov audit).
    lowers = [t_bounds(values[other], alpha)["lower"] for other in ("M0", "S0")]
    three = three_way([(f"against_{other}", combined(out[f"against_{other}"])) for other in ("M0", "S0")])
    return dict(out, **three, holds=bool(out["against_M0"]["holds"] and out["against_S0"]["holds"]),
                saving=bool(all(low is not None and low > 0 for low in lowers)))


def real_cost_readouts(arm, jobs, w):
    """The two read-outs beside clause (b) (the real cost row, 12 Nov, night), from counts already stored.

    break_even_rescue_usd: the cost x of one rescued payment at which the arm and the yardstick use the same real
    resources. The arm's real cost with rescues at x is its total less (2 - x) for each rescued share, so x = 2 - (the
    arm's real cost less the yardstick's) / (the arm's rescued shares less the yardstick's), $ and shares a person a
    year, on the cell's seed means (``cell``) and seed by seed (``by_seed``); None where the arm rescues no more than
    the yardstick. Hand case: the arm uses $1.40 more than M0 with 2.41 rescued shares: x = 2 - 1.40 / 2.41 = 1.42.
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
    """Clause (c), at 1 - alpha (the claim row): failed shortfall payments lower than in M0, in the real failure line's
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
    """Clause (d), no group loses, at 1 - alpha (the claim row as amended 11 Nov): every class, launch-wealth quintile
    and billing-cycle group has a t lower bound of its mean complete gain at or above -$2 against S0 at both ends of
    the bracket (sellers' extra sales at face value and at zero) and against M0 at face. Each group is read with the
    same interval check as every other clause (``check``: the t interval and the bootstrap both supported), so a
    disagreement between them shows in near_the_line. A required group with no finite value, or with a value in one
    seed only, has no interval: it does not support the clause, so (d) does not hold, and ``undefined_groups`` names
    it. No issuer transfers exist to net out (the issuer is a pure custodian, 5 Nov). The lowest t bound is stored
    with its group, yardstick and end, each group's check under ``groups`` by yardstick and end, and the share worse
    off at each end.

    With ``under`` "bound" the clause is read on the gains under the cash-advance bound (decided 15 Nov 2026), each
    end's ``bound`` (``differences``), with the same groups, yardsticks, ends, intervals and margin; a seed that stores
    no bound has no value in any group, so the clause does not hold there."""
    lowest, undefined = None, []
    readings = (("S0", "face"), ("S0", "zero"), ("M0", "face"))
    labels = [f"{other}_{end}" for other, end in readings]
    checks, passes = {label: {} for label in labels}, dict.fromkeys(labels, True)

    def gains(j, other, end):
        """One seed's end of the complete gain against ``other``, as built or under ``under``."""
        stored = j["arms"][arm]["against"][other]["complete_gain"][end]
        return stored if under is None else stored.get(under, {})

    # Every group's column of seeds, each (yardstick, end, group kind) read once into a seeds x groups table, then one
    # flat pass over the columns in the order the clause reads them.
    size = dict(zip(REGION_GROUPS, map(len, (CLASSES, GROUP_NAMES["quintile"], GROUP_NAMES["cycle"]))))
    read = lambda j, other, end, name: [np.nan if v is None else v for v in gains(j, other, end).get(
        f"gain_usd_a_year_by_{name}", [None] * size[name])]
    tables = {(other, end, name): np.array([read(j, other, end, name) for j in jobs], float)
              for (other, end), name in product(readings, REGION_GROUPS)}
    columns = [(other, end, GROUP_NAMES[name][k], column) for (other, end, name), values in tables.items()
               for k, column in enumerate(values.T)]
    for other, end, group, column in columns:
        label = f"{other}_{end}"
        result = check(column, CLAIM_MARGIN, "above", alpha)
        checks[label][group] = result
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
    three = three_way([(f"{label}.{group}", combined(result)) for label, groups in checks.items()
                       for group, result in groups.items()])
    return dict(**three, holds=bool(all(passes.values()) and not undefined), passes=passes,
                lowest=None if lowest is None else dict(lower=low, mean=lowest[1], group=lowest[2],
                                                        against=lowest[3], end=lowest[4]),
                undefined_groups=undefined, groups=checks,
                worse_off_share=worse, issuer_transfers="none: the issuer is a pure custodian")


def clause_d_bound(arm, jobs, cell, alpha):
    """Clause (d) read a second time on the gains under the cash-advance bound (decided 15 Nov 2026: a cell counts
    in the region only if it passes both as built and under the bound), the same fields as clause (d)."""
    return clause_d(arm, jobs, cell, alpha, under="bound")


CLAUSES = dict(a=clause_a, b=clause_b, c=clause_c, d=clause_d)


PASS_CLAUSES = ("a", "b", "d")        # a cell passes on these; (c) is reported, (e) is the highest level withstood


def stress_leg(arm, cell, level_jobs, base_jobs, alpha):
    """One distress level's leg of clause (e) at its alpha (level 0's Bonferroni level, the distress row): clauses (a)
    to (d) on the level's paired run, and the dip's upper bound against S0's and M0's at most one failed payment
    a year, as the row words it: the cumulative excess over months 25 to 60 (``dips``) per consumer unit a year, so
    the 36-month sum over 3; withstands when all hold. The 36-month sums are stored beside. Hand case: a dip of 2.4
    failed payments over the 36 months against S0's in every seed is 0.8 a year and is withstood; 3.6 is 1.2 a year
    and is not."""
    clauses = {key: clause(arm, level_jobs, cell, alpha) for key, clause in CLAUSES.items()}
    legs = {key: block["holds"] for key, block in clauses.items()}
    seen = dips(arm, level_jobs, base_jobs)
    years = DIP_YEARS
    dip = {key: check(yearly_dips(seen[key]), DIP_MARGIN, "below", alpha) for key in ("against_S0", "against_M0")}
    own = _finite(seen["own"])
    total = lambda key: None if dip[key]["mean"] is None else round(dip[key]["mean"] * years, 4)
    # Every clause's full block is kept (the 13 Nov review): clause (b)'s intervals, clause (a)'s first-worded
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
    place to the decided ``summary`` of one pool arm (``decide``'s, or a stored one formed before this rule); ``rows``
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


def claim_statistics(cells, jobs, w):
    """The registered claim read cell by cell (``CLAIM_NOTE``), added to the decided cells in place, with the map-wide
    readings returned for summary.json: the Bonferroni levels, "holds somewhere", the region by distress slice as a
    connected block, and the confirmation seed count (``confirmation_seeds``).

    Adds to each pool arm of every cell better_than_M0 (V2 and V4); to M1 and M2 of each cell at distress 0 claim
    (each clause's status and numbers, all, all_bonferroni, near_the_line, underpowered, in_region) and real_cost
    (clause (b)'s intervals and flags with its two read-outs); and to M1 and M2 of each cell under distress
    stress_leg (``stress_leg`` at the Bonferroni level, with underpowered and in_region). ``jobs`` must carry their
    failure counts (as the run returns them, or from failure_counts.json); the grid's convention is ``w``'s."""
    returned = bool(getattr(w, "lender_income_recirculated", False))
    key = lambda item: (float(item["r_out"]), float(item["a0"]), float(item["distress"]))
    index = {key(c): c for c in cells if c is not None}
    by_cell = {}
    for job in jobs:
        if bool(job["recirculated"]) == returned:
            by_cell.setdefault(key(job), []).append(job)
    for group in by_cell.values():
        group.sort(key=lambda job: job["seed"])
    stats = dict(note=CLAIM_NOTE, bonferroni={}, holds_somewhere={}, regions={})
    for ((rate, a0, level), cell), arm in product(index.items(), POOL_ARMS):
        if arm in cell and by_cell.get((rate, a0, level)):
            group = by_cell[(rate, a0, level)]
            better = better_than_m0(arm, rate, group, w)
            cell[arm]["better_than_M0"] = better
            cell[arm]["worse_than_M0"] = worse_than_m0(cell[arm], better)
            # V2 or V4 shown worse fires the worse-than-M0 falsifier as trade or a harmed group does, before any
            # clause reads the cell's Persistent count (13 Nov review).
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
    # The region by distress slice: the largest edge-joined block of passing cells that are not underpowered.
    stats["regions"][arm] = [_region_slice(arm, level, mine, index) for level in DISTRESS]
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
    leg = stress_leg(arm, cell, by_cell[place], base_jobs, alpha)
    # The seed count reads the dips' unrounded spreads; the stored sd is rounded to 4 places (the 13 Nov audit).
    seen = dips(arm, by_cell[place], base_jobs)
    spread = max((sd for sd in (t_bounds(yearly_dips(seen[key]))["sd"] for key in leg["dip"]) if sd is not None),
                 default=None)
    needed = seeds_needed(spread, DIP_MARGIN, alpha)
    worse = cell[arm]["worse_than_M0"]
    if worse["fires"]:
        leg.update(reading="falsified", decided_by=[f"worse_than_M0.{part}" for part in worse["fired"]]
                   + [name for name in leg["decided_by"] if leg["reading"] == "falsified"])
    leg.update(seeds_needed=needed, underpowered=bool(needed is None or needed > cell["seeds"]),
               worse_than_M0=worse)
    cell[arm]["stress_leg"] = leg
    # Clause (b)'s intervals and its two read-outs at this level too (13 Nov review), at the
    # stress leg's level.
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
    (a), (b) and (d) as built, and the parts of worse than M0 that fired, each deciding clause named with the
    comparison or group inside it that decided it. With (d) under the cash-advance bound among ``clauses`` (15 Nov
    2026) the reading is the worse of the two (d) readings."""
    three = three_way([(f"({name})", block[name]["reading" + suffix]) for name in clauses]
                      + [(name, "falsified") for name in fired])
    decided = [f"{name}.{part}" if name.startswith("(") else name for name in three["decided_by"]
               for part in (block[name[1:-1]]["decided_by" + suffix] or [""] if name.startswith("(") else [None])]
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
    """Clause (e)'s headline (decided 14 Nov 2026: the harsh stress): whether the cell withstands the headline level,
    2 points, 2009's wage loss before unemployment insurance, read from the levels tested in order. True when the
    highest level withstood reaches it; False when a level up to it was tested and not withstood; None when (e) is not
    applicable or the headline level was not run. Hand cases: withstanding 0.5% to 2% is True; 0.5% and 1% withstood
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
    if limited(arm, rate, w):
        skip = dict(status="not applicable", status_bonferroni="not applicable", reason="declared limit")
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
    block = {name: _clause_entry(clause, arm, group, cell, alpha) for name, clause in CLAUSES.items()}
    # Clause (d) read a second time under the cash-advance bound (decided 15 Nov 2026), its own block.
    block["d_bound"] = _clause_entry(clause_d_bound, arm, group, cell, alpha)
    # The four parts of "worse than M0", each named with whether it fired; any firing falsifies the cell (its
    # Persistent count, and so (a), already follow, ``fire_interval_falsifier``).
    worse = cell[arm]["worse_than_M0"]
    block["worse_than_M0"] = worse
    fired = [f"worse_than_M0.{part}" for part in worse["fired"]]
    # The cell's reading takes the worse of (d) as built and under the bound; the reading as built is kept beside.
    for suffix in ("", "_bonferroni"):
        block.update({key + "_as_built": value for key, value in _cell_reading(block, fired, suffix).items()})
        block.update(_cell_reading(block, fired, suffix, PASS_CLAUSES + ("d_bound",)))
    # A cell passes when (a), (b) and (d) are supported; (c) is reported and is not evidence, and (e) is
    # read for passing cells, as the highest level withstood (the claim row and the distress row).
    passes_0 = all(block[name]["status"] == "pass" for name in PASS_CLAUSES)
    tested, highest = _withstood(arm, rate, a0, index, passes_0)
    state = ("not applicable" if not passes_0 or not tested else
             "pass" if highest >= STRESS_LEVELS[0] else "fail")
    block["e"] = dict(status=state, status_bonferroni=state, highest_level=highest if tested else None,
                      tested=tested, reason=None if passes_0 else "(a), (b) and (d) do not all pass at level 0",
                      headline=_headline(tested, highest))
    # all and all_bonferroni ask (d) both as built and under the cash-advance bound (decided 15 Nov 2026), so the
    # region and "holds somewhere" do too; the readings as built are kept beside.
    block["all_as_built"] = bool(passes_0)
    block["all_bonferroni_as_built"] = bool(all(block[name]["status_bonferroni"] == "pass" for name in PASS_CLAUSES))
    block["all"] = bool(passes_0 and block["d_bound"]["status"] == "pass")
    block["all_bonferroni"] = bool(block["all_bonferroni_as_built"] and block["d_bound"]["status_bonferroni"] == "pass")
    parts = _near_parts({name: block[name]["at_95"] for name in CLAUSES})
    # The Persistent share near one half on its unrounded interval, from the stored count (the 13 Nov audit: the
    # stored interval is rounded for display).
    if persistent_on_wilson(cell[arm]["region"]["persistent_seeds"], cell["seeds"])[1]:
        parts.insert(0, "persistent_share")
    block["near_the_line"], block["near_the_line_parts"] = bool(parts), parts
    # The seed count reads the savings' unrounded spreads; the stored sd is rounded to 4 places (the 13 Nov audit).
    spreads = [t_bounds([j["arms"][arm]["against"][other]["real_saving_usd_a_year"]["total"] for j in group])["sd"]
               for other in ("M0", "S0")]
    spread = max((sd for sd in spreads if sd is not None), default=None)
    needed = seeds_needed(spread, abs(CLAIM_MARGIN), alpha)
    block.update(seeds_needed=needed, underpowered=bool(needed is None or needed > cell["seeds"]),
                 in_region=False)
    cell[arm]["claim"] = block
    cell[arm]["real_cost"] = dict(at_95=block["b"]["at_95"], at_bonferroni=block["b"]["at_bonferroni"],
                                  holds=block["b"]["status"] == "pass", saving=block["b"]["at_95"]["saving"],
                                  **real_cost_readouts(arm, group, w))


def _region_slice(arm, level, mine, index):
    """One distress slice of the arm's region: its passing cells, their edge-joined blocks and the largest, whose
    cells are marked in_region in place (level 0 on the claim block, else on the stress leg). Cells join along the
    run's outside rates (``rate_axis``): the grid's for a run of the grid."""
    rates = rate_axis(rate for rate, _, _ in mine)
    passing = set()
    for (rate, a0, at), cell in mine.items():
        if at != level:
            continue
        if level == 0:
            block = cell[arm]["claim"]
            ok = block["all"] and not block["underpowered"]
        else:
            base = index.get((rate, a0, 0.0), {}).get(arm, {}).get("claim", {})
            leg = cell[arm]["stress_leg"]
            # The level-0 cell must pass all, (d) under the cash-advance bound with it (15 Nov 2026): as built (e) is
            # tested only for a cell passing (a), (b) and (d), so this adds the bound alone.
            ok = bool((base.get("e", {}).get("highest_level") or 0.0) >= level and not leg.get("underpowered", True)
                      and base.get("all", False))
        if ok:
            passing.add((rates.index(rate), A0S.index(a0)))
    blocks = connected_blocks(passing)
    region = blocks[0] if blocks else []
    for row, column in region:
        target = mine[(rates[row], A0S[column], level)][arm]
        (target["claim"] if level == 0 else target["stress_leg"])["in_region"] = True
    named = lambda block: [[rates[row], A0S[column]] for row, column in block]
    return dict(distress=level, passing=named(sorted(passing)), blocks=[named(b) for b in blocks],
                region=named(region), tied=bool(len(blocks) > 1 and len(blocks[1]) == len(blocks[0])))

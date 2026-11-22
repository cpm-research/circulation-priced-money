"""The per-cell verdicts: seed means, persistence and the groups.

Seed means of the stored rows, the paired distress reading and recovery, the region reading of each arm (the pool
forms and persists, the issuer stays and no group loses, read with Wilson and t intervals), the interval parts of
"worse than M0", and ``decide``, which turns a cell's jobs into its summary and verdict.
"""
from itertools import product

import numpy as np

from cpm_abm.catalogue import finite_catalogue
from cpm_abm.economy_abm import CARD_LENDING_COST, EPS, TERM_LENDING_COST, m0_rates
from run_economy_figures import issuer_clause
from cpm_abm.experiment.notes import (APPLIES, ARMS, BASE, GROUP_NAMES, POOL_ARMS, REAL_LINES, RECOVERY_MONTHS,
                                      RECOVERY_SHARE, REGION_AGAINST, REGION_GROUPS, REGION_MARGIN, REWARD_SHARE, SCALE)
from cpm_abm.experiment.statistics import check, _group_bounds, persistent_on_wilson, t_interval, wilson

def seed_means(rows):
    """Seed means of report dicts with the same keys, nested dicts and lists included (None stays None)."""
    first = rows[0]
    if isinstance(first, dict):
        return {key: seed_means([row[key] for row in rows]) for key in first}
    if isinstance(first, list):
        return np.round(np.mean(rows, axis=0), 2).tolist()
    return None if first is None else round(float(np.mean(rows)), 2)


def seed_nanmeans(rows):
    """Seed means like ``seed_means`` where a seed's value may be undefined (None, or NaN for an empty group): the mean
    over the seeds that define it, or None if none does (3 Nov)."""
    first = rows[0]
    if isinstance(first, dict):
        return {key: seed_nanmeans([row[key] for row in rows]) for key in first}
    if isinstance(first, list):
        return [seed_nanmeans(list(values)) for values in zip(*rows)]
    values = [value for value in rows if value is not None and not (isinstance(value, float) and np.isnan(value))]
    return round(float(np.mean(values)), 4) if values else None


def share_of(rows, read):
    """The share of seeds whose reading is True (3 Nov); a test that cannot be evaluated (None) counts as not
    holding."""
    return round(float(np.mean([read(row) is True for row in rows])), 3)


def registered_shares(rows):
    """The share of seeds in which each use and collapse test as first registered holds or fires (from
    ``persistence``'s registered_tests), None for a test no seed stores. Hand case: P1 True, True, False over three
    seeds reads 0.667."""
    names = sorted({name for row in rows for name in (row.get("registered_tests") or {})})
    return {name: share_of(rows, lambda row, name=name: (row.get("registered_tests") or {}).get(name)) for name in names}


def w2_of(pair):
    """The second window's value of a reading by window, None where the reading is (3 Nov)."""
    return None if pair is None else pair[1]


def recovery(gap, w):
    """The paired distress reading of one measure in one seed (decided 31 Oct).

    ``gap`` is the measure's gap from the same seed's run without distress in each month after launch. Returns the
    largest gap from the start of the distress year and its month after launch; the months after the distress year
    until the gap stays within a quarter of that largest gap for three months running after it (None if it never
    does, 0 if there was no gap); and the lasting gap, its average over the last 12 months.
    """
    start, end = w.distress_start, w.distress_start + w.distress_length
    window = np.nan_to_num(gap[start:])
    at = int(np.argmax(np.abs(window)))
    peak, lasting = float(window[at]), float(np.mean(np.nan_to_num(gap[-12:])))
    if abs(peak) <= EPS:
        return dict(gap=0.0, month=None, months_to_recover=0, lasting=lasting)
    # The three months come after both the distress year and the largest gap (the 31 Oct review), so a gap that peaks
    # late cannot read as recovered before its peak; with fewer than three months left after it, it has not recovered.
    first = max(end, start + at + 1)
    inside = np.abs(np.nan_to_num(gap[first:])) <= RECOVERY_SHARE * abs(peak)
    runs = (np.convolve(inside, np.ones(RECOVERY_MONTHS, int), "valid") if inside.size >= RECOVERY_MONTHS
            else np.zeros(0))
    held = np.flatnonzero(runs == RECOVERY_MONTHS)
    return dict(gap=peak, month=start + at + 1, months_to_recover=first - end + int(held[0]) + 1 if held.size else None,
                lasting=lasting)


def paired(mine, base, w):
    """The distress reading of one cell: each arm against its own run without distress, seed by seed (31 Oct).

    Per measure: the seed mean of the largest gap and of the lasting gap (on the measure's reporting scale), the share
    of seeds that recovered and their median months to recover. Each arm's failure dip against S0's: the mean
    difference and the share of seeds where it is smaller. For U, M1 and M2, the share of seeds whose distress-year
    issuer wallet is higher than without distress, and whether that makes the issuer rewarded for failure.
    """
    by_seed = {j["seed"]: j for j in base}
    pairs = [(j, by_seed[j["seed"]]) for j in mine if j["seed"] in by_seed]
    if not pairs:
        return dict(seeds_paired=0)
    gap = lambda j, b, arm, name: np.array(j["measures"][arm][name]) - np.array(b["measures"][arm][name])
    year = slice(w.distress_start, w.distress_start + w.distress_length)

    def reading(arm):
        """One arm's reading over the cell's paired seeds."""
        def measure(name):
            """One measure over the paired seeds: the mean largest gap on its reporting scale, the share of seeds that
            recovered, the median months to recover and the mean lasting gap."""
            seen = [recovery(gap(j, b, arm, name), w) for j, b in pairs]
            months = [r["months_to_recover"] for r in seen if r["months_to_recover"] is not None]
            return dict(gap=round(float(np.mean([r["gap"] for r in seen])) * SCALE[name], 4),
                        recovered_share=round(len(months) / len(seen), 3),
                        months_to_recover_median=float(np.median(months)) if months else None,
                        lasting_gap=round(float(np.mean([r["lasting"] for r in seen])) * SCALE[name], 4))
        out = dict(map(lambda name: (name, measure(name)), APPLIES[arm]))
        if arm != "S0":
            dips = [(recovery(gap(j, b, arm, "failures"), w)["gap"], recovery(gap(j, b, "S0", "failures"), w)["gap"])
                    for j, b in pairs]
            out["failures_against_S0"] = dict(
                gap_difference=round(float(np.mean([d - s for d, s in dips])) * SCALE["failures"], 4),
                share_smaller=round(float(np.mean([abs(d) < abs(s) for d, s in dips])), 3))
        if arm in POOL_ARMS:
            wallet = lambda job: float(np.sum(job["measures"][arm]["issuer_wallet"][year]))
            higher = float(np.mean([wallet(j) > wallet(b) for j, b in pairs]))
            out.update(issuer_higher_share=round(higher, 3), issuer_rewarded_for_failure=bool(higher >= REWARD_SHARE))
        return out

    ran = tuple(arm for arm in ("S0",) + ARMS if arm in pairs[0][0]["measures"])   # S0 alone in the S0 check
    return dict(seeds_paired=len(pairs), **dict(map(lambda arm: (arm, reading(arm)), ran)))


def region(arm, rate, rows, persistent, w):
    """The region reading of one pool arm in one cell (5 Nov, ``REGION_NOTE``) from its seeds' rows and whether each
    seed's own verdict is Persistent (``decide``).

    Each part is stored: the declared limit (M2 at a zero real reserve rate); the share of seeds whose pool formed; the
    seeds counted Persistent, their share and Wilson interval, and the cell Persistent on its lower bound above one half
    and, beside it, on a bare majority; the seeds whose issuer records "would leave"; and claim (d) on the complete gain
    (decided 11 Nov: the wealth change plus purchases received, ``differences``), complete_gain: at each end of the
    bracket, sellers' extra sales at face value ("face") and at zero ("zero"), every claim (d) group's 95% t lower
    bound across seeds of its mean gain against S0 and against M0 (``REGION_AGAINST``), read in full (decided
    5 Nov: M2's indexation is the holder's own yield, not an issuer transfer), with the seed mean beside it (the bound
    None with fewer than two seeds defining it, and then the group does not pass), the lowest bound with its group and
    yardstick, and whether all are at or above the margin. The value of completed trade is not assumed, and against
    DeFi the result is reported as a break-even value (decided 11 Nov, second round), so the clause
    (clause_holds) holds when every group's bound against S0 is at or above the margin at both ends and every group's
    bound against M0 is at the face end. by_yardstick holds, for S0 and for M0, face_passes and zero_passes (every
    group's bound at or above the margin at that end), break_even_share, the smallest surplus share s on a 0.01 grid
    from which every group's bound, on each seed's gain (1 - s) x zero + s x face, is at or above the margin at every
    larger grid share, and break_even_share_on_means, the same search on the groups' seed means; each None when it
    fails at s = 1, and 0.0 when it holds at every share. groups holds the same reading on the wealth
    gain alone, the wealth measure, stored beside and read by no verdict. A group empty in every seed is no group
    (None). The verdict names the first condition failed, in the order of ``VERDICTS``, "a group loses" reading the
    complete gain's clause, and "stable" when none is; verdict_majority reads the bare-majority Persistent instead. The
    issuer stays only when no seed records "would leave" (claim (a): it never records it), and the pool forms when it
    forms in any seed: each a reading of the rule (4 Nov). Owners' return less their alternative
    stays reported only (decided 11 Nov), and the entry rule's two readings, quote and realised
    (``Economy.entry_reads``), are run as bounds at confirmation, not read here.

    The cash-advance bound (decided 15 Nov 2026): complete_gain_bound holds the same clause on the gains under the
    bound (``differences``), verdict_bound and verdict_majority_bound the verdicts with the group test read on it, and
    in_region_both whether the cell is stable both as built and under the bound; the keys above are as built.
    """
    seeds = len(rows)
    limit = bool(arm == "M2" and rate - 12 * w.inflation <= 1e-12)
    formed = float(np.mean([row["pool_formed"] for row in rows]))
    counted = [bool(seed) for seed in persistent]
    interval = wilson(sum(counted), seeds)
    leaves = sum(row["X"]["X6"] is True for row in rows)
    pairs = tuple(product(REGION_AGAINST, REGION_GROUPS))

    def table(read):
        """Each yardstick's and group kind's seeds x groups array of the gain ``read(against, name)`` gives for one
        seed, NaN for an empty group."""
        return {pair: np.array([read(row["against"][pair[0]], pair[1]) for row in rows], float) for pair in pairs}

    def bounds(values, shares=None):
        """Each group's seed mean, 95% t lower bound and number of seeds defining it, unrounded, against S0 and against
        M0 (``REGION_AGAINST``), by (yardstick, group kind), of the gains ``values`` (``table``) or, with ``shares``,
        of each seed's gain (1 - s) x zero + s x face at every share s, ``values`` then holding the two ends'
        tables: each a shares x groups array, one row for each share (one row without ``shares``). A group with a
        mean in one seed only has no bound (NaN)."""
        if shares is None:
            return {pair: _group_bounds(values[pair][:, None, :]) for pair in pairs}
        return {pair: _group_bounds((1 - shares)[None, :, None] * values["zero"][pair][:, None, :]
                                    + shares[None, :, None] * values["face"][pair][:, None, :]) for pair in pairs}

    def holding(read, other, on="lower_95"):
        """For each share's row of ``read``, whether every group's bound (``on`` "lower_95") or seed mean (``on``
        "mean") against ``other`` is at or above the margin. A group empty in every seed is no group; a group with no
        bound reads below every margin."""
        each = [np.all((read[(other, name)]["seen"] == 0) | (np.isfinite(read[(other, name)][on])
                                                            & (read[(other, name)][on] >= REGION_MARGIN)), axis=1)
                for name in REGION_GROUPS]
        return np.logical_and.reduce(each)

    def groups(read, k=0):
        """The table of ``bounds`` at the share in row ``k`` as stored: each group's seed mean and t lower bound
        against S0 and against M0, the lowest bound with its group and yardstick, and whether every group's bound
        against both is at or above the margin (the 5 Nov review)."""
        clean = lambda array: [round(float(value), 2) if np.isfinite(value) else None for value in array]
        out, listed = {other: {} for other in REGION_AGAINST}, []
        for other, name in pairs:
            mean, lower, seen = (read[(other, name)][key][k] for key in ("mean", "lower_95", "seen"))
            out[other][name] = dict(mean=clean(mean), lower_95=clean(lower))
            listed += [(float(low) if np.isfinite(low) else -np.inf, float(average), GROUP_NAMES[name][g], other)
                       for g, (low, average, count) in enumerate(zip(lower, mean, seen)) if count > 0]
        lowest = min(listed, key=lambda item: item[0]) if listed else (None, None, None, None)   # the first on a tie
        bound = lowest[0] if lowest[0] is None or np.isfinite(lowest[0]) else None
        return dict(out, lowest=dict(lower_95=None if bound is None else round(bound, 2),
                                     mean=None if lowest[1] is None else round(lowest[1], 2), group=lowest[2],
                                     against=lowest[3]),
                    at_or_above_margin=all(bool(holding(read, other)[k]) for other in REGION_AGAINST))

    # The wealth measure (5 Nov), stored beside the clause.
    wealth = groups(bounds(table(lambda against, name: against[f"gain_usd_a_year_by_{name}"])))
    # Claim (d) on the complete gain (decided 11 Nov), at each surplus share s on the 0.01 grid, each seed's group
    # mean at s being (1 - s) zero + s face, so the grid's ends are the two ends exactly. Every share is read at once
    # (the 13 Nov speed pass), number for number as one share at a time (``_group_bounds``).
    def clause(block):
        """The clause on the complete gain, each seed's gains at each end being ``block(against, side)``: the stored
        end itself as built, or under the cash-advance bound its ``bound`` (15 Nov 2026)."""
        ends = {side: table(lambda against, name, side=side: block(against, side, f"gain_usd_a_year_by_{name}"))
                for side in ("zero", "face")}
        grid = bounds(ends, np.arange(101) / 100)

        def break_even(other, on):
            """The smallest grid share from which every group's ``on`` against ``other`` holds at every larger grid
            share, None when it fails at s = 1."""
            after = np.logical_and.accumulate(holding(grid, other, on)[::-1])[::-1]   # every share from k on holds
            return round(int(np.argmax(after)) / 100, 2) if after.any() else None

        # Per yardstick (decided 11 Nov, second round): each end's pass on bounds and the break-even share on
        # bounds and on means. The clause asks S0 at both ends and M0 at face: the value of completed trade is not
        # assumed against S0, and against DeFi the result is the break-even value.
        yardsticks = {other: dict(face_passes=bool(holding(grid, other)[100]),
                                  zero_passes=bool(holding(grid, other)[0]),
                                  break_even_share=break_even(other, "lower_95"),
                                  break_even_share_on_means=break_even(other, "mean")) for other in REGION_AGAINST}
        return dict(face=groups(grid, 100), zero=groups(grid, 0), by_yardstick=yardsticks,
                    clause_holds=bool(yardsticks["S0"]["face_passes"] and yardsticks["S0"]["zero_passes"]
                                      and yardsticks["M0"]["face_passes"]))

    complete = clause(lambda against, side, key: against["complete_gain"][side][key])
    # The same clause under the cash-advance bound (decided 15 Nov 2026); a seed that stores no bound reads every
    # group as empty there, so the clause does not hold.
    unstored = lambda against, side, key: [np.nan] * len(against["complete_gain"][side][key])
    bounded = clause(lambda against, side, key: against["complete_gain"][side].get("bound", {}).get(
        key, unstored(against, side, key)))

    def verdict(persists, read=complete):
        """The first condition failed, in the order of VERDICTS, or "stable"; the group test read on ``read``."""
        failed = ((limit, "declared limit"), (formed == 0, "no pool"), (not persists, "not persistent"),
                  (leaves > 0, "issuer leaves"), (not read["clause_holds"], "a group loses"))
        return next((name for fails, name in failed if fails), "stable")

    # Read on the unrounded bound; the interval is stored rounded (the 13 Nov audit).
    persists, majority = persistent_on_wilson(sum(counted), seeds)[0], bool(np.mean(counted) > 0.5)
    return dict(verdict=verdict(persists), verdict_majority=verdict(majority), in_region=verdict(persists) == "stable",
                declared_limit=limit, pool_forms_share=round(formed, 3), persistent_seeds=int(sum(counted)),
                persistent_share=round(float(np.mean(counted)), 3), persistent_interval=interval,
                persistent=persists, persistent_majority=majority, issuer_leaves_seeds=int(leaves),
                margin_usd_a_year=REGION_MARGIN, complete_gain=complete, groups=wealth, groups_measure="wealth",
                # Under the cash-advance bound (decided 15 Nov 2026): the clause and the verdicts with the group
                # test read on the gains under the bound, and in the region only when stable both as built and so.
                complete_gain_bound=bounded, verdict_bound=verdict(persists, bounded),
                verdict_majority_bound=verdict(majority, bounded),
                in_region_both=bool(verdict(persists) == "stable" and verdict(persists, bounded) == "stable"))


def decide(jobs, rate, a0, distress, recirculated, w):
    """Seed means and the verdict per arm for one cell, with worse-than-M0 over the cell's paired seeds.

    With distress, the cell also carries the paired reading against the same r_out, a0 and seeds without distress.
    ``w`` is the Economy the jobs ran on (its distress year and length). Jobs that ran S0 alone give S0's reports and
    no arm (no highest mean gain).
    """
    cell = lambda j, level: (j["r_out"], j["a0"], j["distress"], j["recirculated"]) == (rate, a0, level, recirculated)
    mine = [j for j in jobs if cell(j, distress)]
    if not mine:
        return None
    seeds = len(mine)
    arms = tuple(arm for arm in ARMS if arm in mine[0]["arms"])
    mean = lambda arm, key: float(np.mean([j["arms"][arm][key] for j in mine]))
    by_group = lambda rows, key: np.round(np.mean([row[key] for row in rows], axis=0), 2).tolist()
    split_mean = lambda arm: dict(zip(mine[0]["arms"][arm]["split"], np.round(np.mean(
        list(map(lambda j: list(j["arms"][arm]["split"].values()), mine)), axis=0), 1).tolist()))

    def summary(arm):
        """Seed means for one arm, and for the pool arms worse-than-M0 and the verdict."""
        rows = [j["arms"][arm] for j in mine]
        # The headline (decided 31 Oct): the real part, each line's saving against S0, beside the transfers and
        # the cash check.
        saving = lambda j: {key: j["S0"]["real_part"][key] - j["arms"][arm]["real_part"][key] for key in REAL_LINES}
        end_money = lambda run: run["cash"]["everyone"]["end_usd"]
        out = dict(mean_gain_usd=round(mean(arm, "mean_gain_usd")), median_gain_usd=round(mean(arm, "median_gain_usd")),
                   issuer_usd=round(mean(arm, "issuer_usd"), 1),
                   p_yield_pct=round(mean(arm, "p_yield_pct"), 3),
                   better_off=round(mean(arm, "better_off"), 3), A_launch=round(mean(arm, "A_launch"), 3),
                   A_W1=round(mean(arm, "A_W1"), 3), A_W2=round(mean(arm, "A_W2"), 3),
                   failures_pct=round(mean(arm, "failures_pct"), 3),
                   merchant_fees_pct=round(mean(arm, "merchant_fees_pct"), 3), split=split_mean(arm),
                   real_saving_against_S0_usd=seed_means(list(map(saving, mine))),
                   real_part=seed_means([row["real_part"] for row in rows]),
                   transfers=seed_means([row["transfers"] for row in rows]),
                   cash=seed_means([row["cash"] for row in rows]),
                   cash_end_against_S0_usd=round(float(np.mean([end_money(j["arms"][arm]) - end_money(j["S0"])
                                                                for j in mine])), 2),
                   fees_usd_a_year_by_quintile=by_group(rows, "fees_usd_a_year"),
                   failed_usd_a_year_by_quintile=by_group(rows, "failed_usd_a_year"),
                   transfers_usd_a_year_by_quintile=by_group(rows, "transfers_usd_a_year"),
                   crossings=seed_nanmeans([row["crossings"] for row in rows]),
                   # Liquidity by window and the paired differences' seed means against each arm read (5 Nov): the
                   # gain overall, by class, quintile, billing cycle and role, read in full (5 Nov).
                   liquidity=seed_nanmeans([row["liquidity"] for row in rows]),
                   # Credit and purchases by class (11 Nov), reported only.
                   by_class=seed_nanmeans([row["by_class"] for row in rows]),
                   against={other: seed_nanmeans([row["against"][other] for row in rows])
                            for other in rows[0]["against"]})
        if arm == "M0":
            return out
        worse_trade = np.array([j["arms"][arm]["V1_worse"] for j in mine], bool)
        harm = np.array([j["arms"][arm]["V3_harmed"] for j in mine], bool)      # seeds x harm groups
        v1 = float(worse_trade.mean()) >= 0.8
        harmed = harm.mean(axis=0) >= 0.8
        # Borrowers' credit cost (V2, the rate) and owners' realised return (V4) against M0, the falsifier's other two
        # parts (the row '"Worse than M0" uses completed trade, harm to any group, borrowers' credit cost and owners'
        # realised return'), read on the cell's seed mean.
        better = better_than_m0(arm, rate, mine, w)
        interval = bool(better["shown_worse"])
        x4 = bool(v1 or harmed.any() or interval)
        # Worse than M0 is read over the cell's paired seeds: worse in at least 80% of them. Decided
        # 4 Nov: a seed counts it only where the cell is systematically worse and that seed is one of the seeds
        # worse on the part that fired, on trade when trade fires or in a group that fires (the 3 Nov review).
        # Elsewhere it counts in no seed, so the majority verdict is unchanged and a cell Against on it cannot show its
        # seeds Persistent. V2 and V4 have no seed-level threshold, so where either is shown worse every seed counts
        # worse (``fire_interval_falsifier``, which applies the same to a stored cell).
        worse = (worse_trade & v1) | (harm & harmed).any(axis=1) | interval
        falsifiers = [bool(bad) or any(v is True for v in j["arms"][arm]["X"].values()) for j, bad in zip(mine, worse)]
        # A seed is Persistent only when its own verdict is: every persistence test holds and no falsifier fires (the
        # 31 Oct review). A cell Persistent by majority says in how many seeds a falsifier fired.
        persistent = [not x and all(v is True for v in j["arms"][arm]["P"].values()) for j, x in zip(mine, falsifiers)]
        fired = f"a falsifier in {sum(falsifiers)} of {seeds} seeds" if any(falsifiers) else "no falsifier"
        verdict = ("Against CPM" if x4 or np.mean(falsifiers) > 0.5 else
                   f"Persistent, {fired} (not shown worse than M0 on trade, groups, credit cost or owners' return; "
                   "better than M0 not established)"
                   if np.mean(persistent) > 0.5 else "Inconclusive")
        # The issuer would leave (X6) in most seeds: the verdict names it, with M2's declared limit at zero real rates.
        leaves = float(np.mean([j["arms"][arm]["X"]["X6"] is True for j in mine]))
        if verdict.startswith("Against") and leaves > 0.5:
            verdict += issuer_clause(all(j["arms"][arm]["issuer_limit"] for j in mine))
        seed_mean = lambda key: float(np.nanmean([np.nan if j["arms"][arm][key] is None else j["arms"][arm][key]
                                                  for j in mine]))
        return dict(out, X4=x4, V1_systematically_worse=bool(v1), V3_groups_harmed=int(harmed.sum()),
                    better_than_M0=better,
                    worse_than_M0=worse_than_m0(dict(V1_systematically_worse=bool(v1),
                                                     V3_groups_harmed=int(harmed.sum())), better),
                    seed_verdicts=[("Against CPM" if bad else j["arms"][arm]["verdict"])[:12]
                                   for j, bad in zip(mine, worse)],
                    worse_than_M0_seeds=int(worse.sum()), verdict=verdict,
                    # The tests as first registered beside the decided ones: the share of seeds
                    # in which each holds or fires, read by no verdict.
                    registered_tests_share=registered_shares(rows),
                    persistent_share=round(float(np.mean(persistent)), 3),
                    persistent_share_interval=wilson(int(np.sum(persistent)), seeds),
                    c_pct=round(mean(arm, "c_pct"), 3), r_g_pct=round(mean(arm, "r_g_pct"), 3),
                    theta=round(mean(arm, "theta"), 3), N=round(mean(arm, "N"), 3),
                    bridges_drawn_over_wanted=round(mean(arm, "bridges_drawn_over_wanted"), 3),
                    # The contract's other W2 means and demurrage by window (5 Nov).
                    N_star=round(mean(arm, "N_star"), 4), coverage=round(mean(arm, "coverage"), 3),
                    r_b_pct=round(mean(arm, "r_b_pct"), 3), quote_pct=round(mean(arm, "quote_pct"), 3),
                    pool_formed_share=share_of(rows, lambda row: row["pool_formed"]),
                    demurrage=seed_nanmeans([row["demurrage"] for row in rows]),
                    # The region reading (5 Nov, ``REGION_NOTE``), on the seeds' own Persistent verdicts.
                    region=region(arm, rate, rows, persistent, w),
                    issuer_would_leave_seeds=round(leaves, 3),
                    # The issuer's headroom beyond its own costs, those costs and the most cost it could bear in all
                    # (the 4 Nov review), seed means, $ a person a year and % of P.
                    **{f"issuer_{key}_usd_a_year": round(seed_mean(f"issuer_{key}_usd_a_year"), 2)
                       for key in ("headroom", "costs", "most_cost")},
                    **{f"issuer_{key}_pct_of_P": round(100 * seed_mean(f"issuer_{key}_share_of_P"), 3)
                       for key in ("headroom", "costs", "most_cost")},
                    backing_lowest=float(np.nanmin([np.nan if j["arms"][arm]["backing_lowest"] is None
                                                    else j["arms"][arm]["backing_lowest"] for j in mine])),
                    backing_topup_usd=round(seed_mean("backing_topup_usd"), 2),
                    fee_refused_usd=round(mean(arm, "fee_refused_usd"), 2),
                    fee_refused_n=round(mean(arm, "fee_refused_n"), 1),
                    owners=seed_nanmeans([row["owners"] for row in rows]),
                    # Owners' net return less their alternative by window (11 Nov), reported only: the seed mean and
                    # its 95% t interval across the seeds whose households held capital in the window.
                    owners_excess_pct={window: t_interval([row["owners_excess"][window] for row in rows])
                                       for window in ("W1", "W2")},
                    # The yardsticks (decided 3 Nov): seed means by window and each seed's W2 value, which Step 7's
                    # intervals read, of the pool's own margin and the joint issuer-and-pool test; and the shares of
                    # seeds whose pool pays its own way, whose issuer never records "would leave", whose households hold
                    # 90% on each base, where P routes and counting toward claim (a) (a test that cannot be evaluated
                    # counts as not holding).
                    own_margin_usd_a_year=seed_nanmeans([row["own_margin_usd_a_year"] for row in rows]),
                    joint_usd_a_year=seed_nanmeans([row["joint_usd_a_year"] for row in rows]),
                    own_margin_W2_by_seed=[w2_of(row["own_margin_usd_a_year"]) for row in rows],
                    # The household-held months each seed's W2 margin is annualised from (the 4 Nov review).
                    own_margin_held_months_W2_by_seed=[w2_of(row["own_margin_held_months"]) for row in rows],
                    joint_W2_by_seed=[w2_of(row["joint_usd_a_year"]) for row in rows],
                    pays_its_way_share=share_of(rows, lambda row: row["pays_its_way_W2"]),
                    issuer_never_leaves_share=share_of(rows, lambda row: row["issuer_never_leaves"]),
                    **{key + "_share": share_of(rows, lambda row, key=key: row["households"][key])
                       for key in ("households_hold_90_W2", "households_hold_90_W2_all_capital", "p_routes_W2",
                                   "counts")})

    best = max(arms, key=lambda arm: mean(arm, "mean_gain_usd")) if arms else None
    base = [j for j in jobs if cell(j, 0.0)] if distress > 0 else []
    return dict(r_out=rate, a0=a0, distress=distress, seeds=seeds, recirculated=recirculated, highest_mean_gain=best,
                S0_failures_pct=round(float(np.mean([j["S0"]["failures_pct"] for j in mine])), 3),
                S0_merchant_fees_pct=round(float(np.mean([j["S0"]["merchant_fees_pct"] for j in mine])), 3),
                S0_fees_usd_a_year_by_quintile=by_group([j["S0"] for j in mine], "fees_usd_a_year"),
                S0_failed_usd_a_year_by_quintile=by_group([j["S0"] for j in mine], "failed_usd_a_year"),
                S0_transfers_usd_a_year_by_quintile=by_group([j["S0"] for j in mine], "transfers_usd_a_year"),
                S0_real_part=seed_means([j["S0"]["real_part"] for j in mine]),
                S0_transfers=seed_means([j["S0"]["transfers"] for j in mine]),
                S0_cash=seed_means([j["S0"]["cash"] for j in mine]),
                S0_liquidity=seed_nanmeans([j["S0"]["liquidity"] for j in mine]),
                S0_by_class=seed_nanmeans([j["S0"]["by_class"] for j in mine]),
                **dict(map(lambda arm: (arm, summary(arm)), arms)),
                distress_reading=paired(mine, base, w) if distress > 0 else None)


def decide_cells(jobs, selection, w, n):
    """Every selected cell decided (``decide``) in the catalogue's order, each with its N, and the baseline cell under
    the recirculation convention (None when that set did not run). The grid's cells are read under the convention
    the Economy ``w`` runs them at: lenders' interest returned over the whole grid (decided 12 Nov), or as built,
    leaving the economy; with it returned there is no separate set, so None."""
    returned = w.lender_income_recirculated
    # Each cell's jobs found once (the 13 Nov speed pass): ``decide`` reads only a cell's own jobs and, under distress,
    # those of the same r_out and a0 without it, so it is handed those alone, in the run's order.
    by_cell = {}
    for j in jobs:
        by_cell.setdefault((j["r_out"], j["a0"], j["recirculated"]), []).append(j)
    near = lambda rate, a0, flag: by_cell.get((rate, a0, flag), [])
    cells = [dict(decide(near(p["r_out"], p["a0"], returned), p["r_out"], p["a0"], p["distress"], returned, w), n=n)
             for p in finite_catalogue({name: list(values) for name, values in selection.items()})]
    return cells, None if returned else decide(near(BASE[0], BASE[1], True), BASE[0], BASE[1], 0.0, True, w)


def _class_mean(by_class, key):
    """A person's mean of one by-class record (``by_class``), weighting each class's mean by its size (NaN classes,
    which are empty, carry no weight); None when the record is missing."""
    if by_class is None or key not in by_class:
        return None
    sizes = np.array(by_class["class_sizes"], float)
    values = np.array([np.nan if v is None else v for v in by_class[key]], float)
    seen = np.isfinite(values) & (sizes > 0)
    return float(np.dot(sizes[seen], values[seen]) / sizes[seen].sum()) if seen.any() else None


def _gap(values):
    """Each defined difference, None where either side is undefined."""
    return [None if a is None or b is None else a - b for a, b in values]


def better_than_m0(arm, rate, jobs, w):
    """The two interval parts of "worse than M0" (the row '"Worse than M0" uses completed trade, harm to any group,
    borrowers' credit cost and owners' realised return'), read from stored parts. Each fires only when the arm is shown
    worse, and a part that fires makes the cell's worse-than-M0 falsifier fire as trade or a harmed group does
    (``worse_than_m0``, ``decide`` and ``claim_statistics``).

    V2, borrowers' credit cost, fires on the rate only (decided 13 Nov): the interest borrowers pay over the
    principal-time they borrow, % a year, the arm less M0, paired by seed; shown worse when the interval lies wholly
    above zero on the t interval and on the bootstrap both. The interest is accrued by borrowers to every lender (pool,
    card, outside), $ a person a year from the by-class records, and the principal-time is recovered from the real
    part's credit lines (card-type and instalment principal-time at their sourced rates). Interest a person a year, the
    arm less M0, is stored beside as a report and fires nothing: borrowing more at a lower price is not a worse cost
    (its ``shown_worse`` says only where its interval lies; ``fires`` is always False). Missing: interest and balances
    by person, so this is the population's mean, not a borrower's; overdraft interest is in the interest but no
    overdraft balance is in the principal-time.
    V4, owners' realised return: households' W2 return as pool owners, net of issuer money, % a year, less what the
    same money earns in DeFi, USDC's savings rate at the cell's r_out (``m0_rates``), with CPI added to M2's return
    (P terms); shown worse, as V2 is, when the t interval and the bootstrap interval both lie wholly below zero (the
    13 Nov audit; the t upper bound alone before). None where households held no capital in W2."""
    rows = [j["arms"][arm] for j in jobs]
    interest = lambda run: None if run.get("by_class") is None else sum(
        _class_mean(run["by_class"], key) or 0.0 for key in ("interest_pool", "interest_card", "interest_outside"))

    def rate_pct(run):
        """The interest borrowers accrued over the principal-time they bore, % a year: the by-class interest over the
        card and instalment principal-time recovered from the real part's credit lines; None without by-class records
        or with no principal-time."""
        lines = run["real_part"]
        balance = (lines["card_credit"] / CARD_LENDING_COST + lines["term_credit"] / TERM_LENDING_COST) / w.months
        owed = interest(run)
        return None if owed is None or balance <= EPS else 100 * owed / balance

    v2 = dict(interest_usd_a_year=check(_gap([(interest(j["arms"][arm]), interest(j["arms"]["M0"])) for j in jobs]),
                                        0.0, "below"),
              rate_pct=check(_gap([(rate_pct(j["arms"][arm]), rate_pct(j["arms"]["M0"])) for j in jobs]), 0.0,
                             "below"))
    wrong_side = lambda block: bool(block["reading"] == "falsified" and block["bootstrap_reading"] == "falsified")
    v2["interest_usd_a_year"].update(shown_worse=wrong_side(v2["interest_usd_a_year"]), fires=False,
                                     role="report: borrowing more at a lower price is not a worse cost")
    v2["rate_pct"].update(shown_worse=wrong_side(v2["rate_pct"]), role="fires: the rate, t and bootstrap both")
    v2["rate_pct"]["fires"] = v2["rate_pct"]["shown_worse"]
    v2["shown_worse"] = bool(v2["rate_pct"]["shown_worse"])
    savings = 1200 * m0_rates(rate / 12, getattr(w, "m0_rates", "observed"))[0]
    cpi = 1200 * w.inflation if arm == "M2" else 0.0
    owners = [((row.get("owners") or {}).get("net_pct") or {}).get("W2") for row in rows]
    v4 = check([None if value is None else value + cpi - savings for value in owners], 0.0, "above")
    # Shown worse as V2 is: the t and the bootstrap interval both wholly below zero, read on the unrounded bounds
    # (the 13 Nov audit; it fired on the stored, rounded t upper bound alone before).
    v4.update(defi_savings_pct=round(savings, 4), cpi_added_pct=round(cpi, 4), shown_worse=wrong_side(v4),
              computed=bool(v4["seeds"] > 0))
    return dict(V2=v2, V4=v4, shown_worse=bool(v2["shown_worse"] or v4["shown_worse"]))


def worse_than_m0(summary, better):
    """The four registered parts of "worse than M0" and whether each fired, for one pool arm in one cell: completed
    trade (V1, systematically worse in at least 80% of paired seeds) and harm to any group (V3), as ``decide`` stored
    them in ``summary`` (False where the decided cell does not carry them), borrowers' credit cost (V2, the rate) and
    owners' realised return (V4) from ``better`` (``better_than_m0``). fires when any part fires."""
    parts = dict(completed_trade=bool(summary.get("V1_systematically_worse") is True),
                 group_harm=bool((summary.get("V3_groups_harmed") or 0) > 0),
                 credit_cost=bool(better["V2"]["shown_worse"]), owners_return=bool(better["V4"]["shown_worse"]))
    return dict(parts, fires=any(parts.values()),
                fired=[name for name, fired in parts.items() if fired])

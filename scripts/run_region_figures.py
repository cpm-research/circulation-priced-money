"""Publication figures of the stable region, drawn from a population map's store in seconds.

Reads ``summary.json`` (the decided cells, with each pool arm's region reading) and ``measures.json`` (each job's
monthly series) that ``scripts/run_economy_population.py`` writes, runs nothing, and writes each figure as PNG at
200 dpi and as PDF:

* ``claim_map``                 the claim map (the 13 Nov review): M1's and M2's stored claim readings over (r_out, a0),
                                one row per distress slice: in the region, supported outside it, inconclusive,
                                falsified, declared limit (skipped when the store holds no claim reading);
* ``region_3d``                 the persistence-and-groups view (not the claim map) over r_out x a0 x distress, one
                                panel per pool arm (U, M1, M2): cells in the stable region solid, the others faint,
                                coloured by the reading;
* ``region_slice_distress_<k>`` the persistence-and-groups view, one per distress level k, in % a month ("0p5" for
                                0.5): the M1 and M2 readings over (r_out, a0), each cell with its mean gain against S0,
                                read in full (decided 5 Nov), $ a person a year;
* ``paths_baseline``            participation, pool capital N with its limit N*, the charge c, theta and the bridging
                                rate with the coupon, month by month at the baseline cell without distress, for U, M1
                                and M2 (seed mean, with the seeds' range shaded);
* ``paths_distress``            the same paths at the baseline r_out and a0 for M1 and M2, one line per distress level,
                                the distress year shaded;
* ``demurrage_effect``          M1 less U over the grid, one column per distress level: participation in years 4 and 5,
                                pool capital, the mean gain against S0 and failed payments;
* ``bridging_vs_card``          the bridging rate and the coupon against the card APR tiers at each r_out;
* ``liquidity_vs_s0``           precautionary money and failed payments against S0, and the money held per dollar of
                                shortfall covered.

A figure the store cannot support (a selection without the baseline cell, a run without U, S0 alone) is skipped with
a printed note. Existing figures are never overwritten. With ``--majority`` the region figures read each cell's
bare-majority reading instead of the decided one (statistics, 3 Nov), and their names end in ``_majority``.

Usage (from the repository root):
    python -X utf8 scripts/run_region_figures.py --store results/<map>
    python -X utf8 scripts/run_region_figures.py --store results/<map> --majority
"""
import argparse
from itertools import product
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from run_economy_figures import (AQUA, BLUE, DOLLARS, GRID, INK, MUTED, ORANGE, RED, SURFACE, VIOLET,  # noqa: E402
                                 YELLOW, style)
from run_economy_population import BASE, POOL_ARMS, VERDICTS  # noqa: E402

DPI = 200
YEAR = 1200.0                     # a monthly rate to % a year
# One palette for every figure. Arms keep one colour, line style and marker throughout; the region readings their own
# colours, the stable region the only saturated green; distress levels one blue ramp, light to dark.
ARM_STYLE = dict(S0=(MUTED, "-", "o"), M0=(YELLOW, ":", "s"), U=(VIOLET, "--", "^"), M1=(BLUE, "-", "o"),
                 M2=(ORANGE, "-.", "D"))
VERDICT_COLOURS = {"stable": AQUA, "a group loses": "#f2c46d",
                   "issuer leaves": RED, "not persistent": "#c9d3de", "no pool": "#ecebe6", "declared limit": "#ffffff"}
# M1 less U: orange where M1 is lower, blue where it is higher, a neutral grey at zero.
DIVERGING = LinearSegmentedColormap.from_list("m1_less_u", [ORANGE, "#efeeea", BLUE])
# The older region figures read each cell's persistence-and-groups reading (``region``), not the registered claim:
# labelled so, so nobody reads them as the claim map (13 Nov review), which is ``claim_map``.
PERSISTENCE_VIEW = "Persistence-and-groups view (not the claim map; see claim_map)"
LABELS = dict(a0="initial participation a0", r_out="r_out (% a year)", distress="extra job loss (% a month)",
              month="months after launch")


def setup():
    """Type sizes and colours shared by every figure."""
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 7,
                         "ytick.labelsize": 7, "legend.fontsize": 7, "axes.edgecolor": GRID, "text.color": INK,
                         "axes.labelcolor": MUTED, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                         "savefig.facecolor": SURFACE, "pdf.fonttype": 42})


def load(store):
    """The store's opening record and decided cells (summary.json), and the jobs' monthly series (measures.json, None
    when absent)."""
    summary = json.loads((store / "summary.json").read_text(encoding="utf-8"))
    path = store / "measures.json"
    measures = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return summary, measures


def number(value):
    """A stored value as a float, NaN for None."""
    return np.nan if value is None else float(value)


def w2(pair):
    """The second window's value (years 4 and 5 after launch) of a reading stored by window, NaN where undefined."""
    return np.nan if pair is None else number(pair[1])


def grid_of(cells):
    """The grid the cells cover: r_out, a0 and distress values in order, and each cell by its (r_out, a0, distress)."""
    axis = lambda key: sorted({cell[key] for cell in cells})
    return axis("r_out"), axis("a0"), axis("distress"), {(c["r_out"], c["a0"], c["distress"]): c for c in cells}


def reading(cell, arm, majority):
    """A pool arm's region reading in a cell, decided or bare majority; None where the arm did not run."""
    if arm not in cell or "region" not in cell[arm]:
        return None
    return cell[arm]["region"]["verdict_majority" if majority else "verdict"]


# The claim map (13 Nov review): each cell's stored claim reading (``claim_statistics``), not the
# persistence-and-groups view above. In order of the legend.
CLAIM_READINGS = ("in the region", "supported outside it", "inconclusive", "falsified", "declared limit")
CLAIM_COLOURS = {"in the region": AQUA, "supported outside it": "#a9d8cf", "inconclusive": "#c9d3de",
                 "falsified": RED, "declared limit": "#ffffff"}


def claim_reading(cell, arm):
    """A claim arm's stored claim reading in a cell, one of CLAIM_READINGS, or None where the store holds none: at
    distress 0 the claim block (``claim``), under distress the stress leg (``stress_leg``); "in the region" when the
    cell is in its slice's region, "supported outside it" when it reads supported but is not (underpowered or not in
    the largest connected block), else the three-way reading (inconclusive or falsified), or the declared limit."""
    if not cell:
        return None
    stored = cell.get(arm) or {}
    block = stored.get("claim") if cell.get("distress", 0) == 0 else stored.get("stress_leg")
    if not block:
        return None
    if block.get("reason") == "declared limit" or block.get("reading") == "declared limit":
        return "declared limit"
    if block.get("in_region"):
        return "in the region"
    found = block.get("reading")
    if found is None:
        return None
    return "supported outside it" if found == "supported" else found


def claim_map(cells, output, written):
    """The claim map: M1's and M2's stored claim readings over (r_out, a0), one row per distress slice, from the
    stored claim blocks and stress legs (in the region, supported outside it, inconclusive, falsified, declared
    limit). Skipped with a note when the store holds no claim reading."""
    rates, a0s, levels, by_key = grid_of(cells)
    arms = [arm for arm in ("M1", "M2") if any(claim_reading(c, arm) for c in cells)]
    if not arms:
        print("claim_map skipped: the store holds no claim reading (claim_statistics).")
        return
    order = list(CLAIM_READINGS)
    palette = ListedColormap([CLAIM_COLOURS[name] for name in order])
    fig, axes = plt.subplots(len(levels), len(arms), figsize=(0.95 * len(a0s) * len(arms) + 1.2,
                                                              (0.55 * len(rates) + 0.9) * len(levels) + 0.8),
                             squeeze=False, constrained_layout=True)
    shown = set()
    # One panel a distress level (row) and arm (column), in that order.
    for (row, column), axis in np.ndenumerate(axes):
        claim_panel(axis, arms[column], levels[row], (rates, a0s, by_key), order, palette, shown)
    handles = [Patch(facecolor=CLAIM_COLOURS[name], edgecolor=MUTED if name == "declared limit" else "none",
                     hatch="///" if name == "declared limit" else None, label=name)
               for name in CLAIM_READINGS if name in shown]
    fig.legend(handles=handles, ncol=min(len(handles), 5), frameon=False, loc="outside lower center")
    fig.suptitle("Claim map: the registered claim's stored reading by distress slice (claim_statistics; the region is "
                 "the largest edge-joined block of supported cells that are not underpowered)", x=0.01, ha="left",
                 color=INK, fontsize=9)
    save(fig, output, "claim_map", written)


def claim_panel(axis, arm, level, grid, order, palette, shown):
    """One panel of the claim map: the arm's stored claim reading in every (r_out, a0) cell at one distress level,
    with the names shown added to ``shown``; ``grid`` is ``grid_of``'s r_out values, a0 values and cells by key."""
    rates, a0s, by_key = grid
    index = np.full((len(rates), len(a0s)), np.nan)
    for (j, rate), (i, a0) in product(enumerate(rates), enumerate(a0s)):
        name = claim_reading(by_key.get((rate, a0, level)), arm)
        if name is None:
            continue
        shown.add(name)
        index[j, i] = order.index(name)
        if name == "declared limit":
            axis.add_patch(Rectangle((i - 0.5, j - 0.5), 1, 1, fill=False, hatch="///", edgecolor=GRID, linewidth=0))
    axis.imshow(np.ma.masked_invalid(index), cmap=palette, vmin=-0.5, vmax=len(order) - 0.5, origin="lower",
                aspect="auto")
    list(map(lambda x: axis.axvline(x, color=SURFACE, linewidth=2), np.arange(len(a0s) - 1) + 0.5))
    list(map(lambda y: axis.axhline(y, color=SURFACE, linewidth=2), np.arange(len(rates) - 1) + 0.5))
    axis.set_xticks(range(len(a0s)), labels=[f"{a:g}" for a in a0s])
    axis.set_yticks(range(len(rates)), labels=[percent(r) for r in rates])
    style(axis, f"{arm}, extra job loss {percent(level)}% a month", LABELS["a0"], LABELS["r_out"])
    axis.grid(False)
    list(map(lambda side: axis.spines[side].set_visible(False), ("left", "bottom")))


def gain_against_s0(cell, arm):
    """The arm's seed-mean gain against S0, read in full (decided 5 Nov: M2's indexation is the holder's own
    yield, not an issuer transfer), $ a person a year (claim (d)'s basis)."""
    against = cell.get(arm, {}).get("against", {}).get("S0")
    return np.nan if against is None else number(against["gain_usd_a_year"])


def percent(value):
    """A share or rate in % for an axis label."""
    return f"{100 * value:g}"


def save(fig, output, name, written):
    """Write one figure as PNG at DPI and as PDF, and note its name; a figure already there is never overwritten."""
    targets = [output / f"{name}{suffix}" for suffix in (".png", ".pdf")]
    if any(target.exists() for target in targets):
        plt.close(fig)
        raise FileExistsError(f"{name} is already in {output}: figures are never overwritten")
    for target in targets:
        fig.savefig(target, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    written.append(name)


def legend_of_readings(fig, shown, outside=False):
    """A figure legend of the region readings shown, in the order of VERDICTS, below the panels (``outside`` for a
    figure laid out by constrained layout, which then makes room for it)."""
    handles = [Patch(facecolor=VERDICT_COLOURS[name], edgecolor=MUTED if name == "declared limit" else "none",
                     hatch="///" if name == "declared limit" else None, label=name)
               for name in VERDICTS if name in shown]
    place = dict(loc="outside lower center") if outside else dict(loc="lower center", bbox_to_anchor=(0.5, -0.02))
    fig.legend(handles=handles, ncol=min(len(handles), 4), frameon=False, **place)


def region_3d(cells, output, majority, written):
    """The region reading over r_out x a0 x distress, one 3D panel per pool arm: stable cells solid, the rest faint."""
    rates, a0s, levels, by_key = grid_of(cells)
    arms = [arm for arm in POOL_ARMS if any(reading(c, arm, majority) for c in cells)]
    if not arms:
        print("region_3d skipped: the store holds no pool arm's region reading.")
        return
    fig = plt.figure(figsize=(4.4 * len(arms), 4.6))
    shown = set()
    for place, arm in enumerate(arms, 1):
        axis = fig.add_subplot(1, len(arms), place, projection="3d")
        filled, colours = voxel_colours(arm, (rates, a0s, levels, by_key), majority, shown)
        axis.voxels(filled, facecolors=colours, edgecolors=matplotlib.colors.to_rgba(MUTED, 0.25), linewidth=0.3)
        stable = int(sum(reading(c, arm, majority) == "stable" for c in cells))
        axis.set_title(f"{arm}: stable in {stable} of {int(filled.sum())} cells", loc="left", color=INK)
        ticks = lambda values: np.arange(len(values)) + 0.5
        axis.set_xticks(ticks(a0s), labels=[f"{a:g}" for a in a0s])
        axis.set_yticks(ticks(rates), labels=[percent(r) for r in rates])
        axis.set_zticks(ticks(levels), labels=[percent(d) for d in levels])
        axis.set_xlabel(LABELS["a0"])
        axis.set_ylabel(LABELS["r_out"])
        axis.set_zlabel(LABELS["distress"])
        axis.set_box_aspect((len(a0s), 1.4 * len(rates), len(levels)), zoom=0.85)
        axis.view_init(elev=22, azim=-58)
        list(map(lambda pane: (pane.set_pane_color(matplotlib.colors.to_rgba(SURFACE, 1.0)), pane.line.set_color(GRID)),
                 (axis.xaxis, axis.yaxis, axis.zaxis)))
        axis.tick_params(colors=MUTED, labelsize=6)
    legend_of_readings(fig, shown)
    fig.suptitle(PERSISTENCE_VIEW, x=0.01, ha="left", color=INK, fontsize=9)
    save(fig, output, "region_3d" + ("_majority" if majority else ""), written)


def voxel_colours(arm, grid, majority, shown):
    """The 3D panel's cells for one arm: which (a0, r_out, distress) cells hold a reading and each one's colour, the
    stable region solid and the rest faint, with the names shown added to ``shown``; ``grid`` is ``grid_of``'s."""
    rates, a0s, levels, by_key = grid
    filled = np.zeros((len(a0s), len(rates), len(levels)), bool)
    colours = np.zeros(filled.shape + (4,))
    for (i, a0), (j, rate), (k, level) in product(enumerate(a0s), enumerate(rates), enumerate(levels)):
        name = reading(by_key.get((rate, a0, level), {}), arm, majority)
        if name is None:
            continue
        shown.add(name)
        filled[i, j, k] = True
        alpha = 0.95 if name == "stable" else 0.06 if name == "declared limit" else 0.22
        colours[i, j, k] = matplotlib.colors.to_rgba(VERDICT_COLOURS[name], alpha)
    return filled, colours


def region_slices(cells, output, majority, written):
    """One figure per distress level: the M1 and M2 readings over (r_out, a0), each cell labelled with its mean gain
    against S0, read in full, $ a person a year."""
    rates, a0s, levels, by_key = grid_of(cells)
    arms = [arm for arm in ("M1", "M2") if any(reading(c, arm, majority) for c in cells)]
    if not arms:
        print("region slices skipped: the store holds no M1 or M2 region reading.")
        return
    order = list(VERDICTS)
    palette = ListedColormap([VERDICT_COLOURS[name] for name in order])
    for level in levels:
        fig, axes = plt.subplots(1, len(arms), figsize=(0.95 * len(a0s) * len(arms) + 1.2, 0.7 * len(rates) + 1.6),
                                 squeeze=False, constrained_layout=True)
        shown = set()
        list(map(lambda axis, arm: slice_panel(axis, arm, level, (rates, a0s, by_key), majority, (order, palette),
                                               shown), axes[0], arms))
        fig.suptitle(f"{PERSISTENCE_VIEW}\nRegion reading at extra job loss {percent(level)}% a month; each cell's "
                     "mean gain against S0, read in full, $ a person a year", x=0.01, ha="left", color=INK, fontsize=9)
        legend_of_readings(fig, shown, outside=True)
        name = f"region_slice_distress_{percent(level).replace('.', 'p')}" + ("_majority" if majority else "")
        save(fig, output, name, written)


def slice_panel(axis, arm, level, grid, majority, colours, shown):
    """One panel of a region slice: the arm's reading in every (r_out, a0) cell at one distress level, each cell
    labelled with its mean gain against S0, with the names shown added to ``shown``; ``grid`` is ``grid_of``'s r_out
    values, a0 values and cells by key, ``colours`` the readings' order and palette."""
    rates, a0s, by_key = grid
    order, palette = colours
    index = np.full((len(rates), len(a0s)), np.nan)
    for (j, rate), (i, a0) in product(enumerate(rates), enumerate(a0s)):
        cell = by_key.get((rate, a0, level))
        name = reading(cell, arm, majority) if cell else None
        if name is None:
            continue
        shown.add(name)
        index[j, i] = order.index(name)
        gain = gain_against_s0(cell, arm)
        text = "n/a" if not np.isfinite(gain) else f"{gain:+.0f}" if abs(gain) >= 10 else f"{gain:+.1f}"
        axis.text(i, j, text, ha="center", va="center", fontsize=7, color=INK)
        if name == "declared limit":
            axis.add_patch(Rectangle((i - 0.5, j - 0.5), 1, 1, fill=False, hatch="///", edgecolor=GRID, linewidth=0))
    axis.imshow(np.ma.masked_invalid(index), cmap=palette, vmin=-0.5, vmax=len(order) - 0.5, origin="lower",
                aspect="auto")
    # A surface gap between cells.
    list(map(lambda x: axis.axvline(x, color=SURFACE, linewidth=2), np.arange(len(a0s) - 1) + 0.5))
    list(map(lambda y: axis.axhline(y, color=SURFACE, linewidth=2), np.arange(len(rates) - 1) + 0.5))
    axis.set_xticks(range(len(a0s)), labels=[f"{a:g}" for a in a0s])
    axis.set_yticks(range(len(rates)), labels=[percent(r) for r in rates])
    style(axis, arm, LABELS["a0"], LABELS["r_out"])
    axis.grid(False)
    list(map(lambda side: axis.spines[side].set_visible(False), ("left", "bottom")))


# The monthly paths drawn (key, title, unit, scale; a dashed companion series), from the contract's stored path.
PATHS = (("A", "Participation", "share of people", 1.0, None),
         ("N", "Pool capital N (dashed: N*)", "$ a person", DOLLARS, "Q"),
         ("c", "Demurrage on wallet P, c", "% a year", YEAR, None),
         ("theta", "Demurrage's share, theta", "share of bridging finance", 1.0, None),
         ("r_b", "Bridging rate r_b (dashed: r_g)", "% a year, P terms", YEAR, "r_g"))


def paths(jobs, arm, key, scale):
    """Seed mean, lowest and highest of one stored monthly series over ``jobs``, scaled; NaN in a month no seed
    defines."""
    rows = np.array([[np.nan if v is None else v for v in job["monthly"][arm][key]] for job in jobs], float) * scale
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # a month no seed defines stays NaN
        return np.nanmean(rows, axis=0), np.nanmin(rows, axis=0), np.nanmax(rows, axis=0)


def baseline_jobs(measures, level):
    """The stored jobs at the baseline r_out and a0 at one distress level, under the map's own convention: without
    lenders' interest recirculated, or, in a map that returns it over the whole grid (decided 12 Nov: its economy
    record says so), with it."""
    if measures is None:
        return []
    returned = bool((measures.get("economy") or {}).get("lender_income_recirculated"))
    return [job for job in measures["jobs"] if (job["r_out"], job["a0"], job["distress"]) == (*BASE, level)
            and bool(job["recirculated"]) == returned]


def paths_baseline(measures, output, written):
    """The contract's monthly paths at the baseline cell without distress for U, M1 and M2."""
    jobs = baseline_jobs(measures, 0.0)
    arms = [arm for arm in POOL_ARMS if jobs and arm in jobs[0]["monthly"] and "N" in jobs[0]["monthly"][arm]]
    if not arms:
        print(f"paths_baseline skipped: the store holds no pool arm's monthly path at r_out {percent(BASE[0])}%, "
              f"a0 {BASE[1]} without distress.")
        return
    fig, axes = plt.subplots(1, len(PATHS), figsize=(16, 3.4), constrained_layout=True)
    list(map(lambda axis, path: baseline_panel(axis, path, arms, jobs), axes, PATHS))
    axes[0].legend(frameon=False, loc="best")
    fig.suptitle(f"The contract month by month at r_out {percent(BASE[0])}% and a0 {BASE[1]}, without distress "
                 f"(seed mean, the seeds' range shaded; {len(jobs)} seed{'s' * (len(jobs) != 1)})", x=0.01, ha="left",
                 color=INK, fontsize=9)
    save(fig, output, "paths_baseline", written)


def baseline_panel(axis, path, arms, jobs):
    """One panel of the baseline paths: one stored monthly series (``PATHS``' entry ``path``) for each arm, its seed
    mean with the seeds' range shaded, and the dashed companion series where there is one."""
    key, title, unit, scale, beside = path
    for arm in arms:
        colour, _, _ = ARM_STYLE[arm]
        mean, low, high = paths(jobs, arm, key, scale)
        months = np.arange(1, mean.size + 1)
        axis.fill_between(months, low, high, color=colour, alpha=0.12, linewidth=0)
        axis.plot(months, mean, color=colour, linewidth=2, label=arm)
        if beside:
            axis.plot(months, paths(jobs, arm, beside, scale)[0], color=colour, linewidth=1.2, linestyle="--")
    style(axis, title, LABELS["month"], unit)


def paths_distress(measures, summary, output, written):
    """The contract's monthly paths at the baseline r_out and a0 for M1 and M2, one line per distress level, with the
    distress year shaded."""
    levels = sorted({job["distress"] for job in (measures or {}).get("jobs", [])})
    sets = {level: baseline_jobs(measures, level) for level in levels}
    sets = {level: jobs for level, jobs in sets.items() if jobs}
    arms = [arm for arm in ("M1", "M2") if sets and all(arm in jobs[0]["monthly"] for jobs in sets.values())]
    if len(sets) < 2 or not arms:
        print("paths_distress skipped: it needs M1 or M2 at the baseline r_out and a0 at two distress levels or more.")
        return
    economy = summary["economy"]
    start, length = economy["distress_start"], economy["distress_length"]
    shades = plt.cm.Blues(np.linspace(0.35, 0.95, len(sets)))
    fig, axes = plt.subplots(len(arms), len(PATHS), figsize=(16, 3.0 * len(arms)), squeeze=False,
                             constrained_layout=True)
    # One panel an arm (row) and path (column), in that order.
    for (row, column), axis in np.ndenumerate(axes):
        distress_panel(axis, arms[row], PATHS[column], sets, shades, (start, length))
    axes[0][0].legend(frameon=False, title="extra job loss", title_fontsize=7, loc="best")
    fig.suptitle(f"The contract through a distress year (shaded, months {start + 1} to {start + length}) at r_out "
                 f"{percent(BASE[0])}% and a0 {BASE[1]} (seed means)", x=0.01, ha="left", color=INK, fontsize=9)
    save(fig, output, "paths_distress", written)


def distress_panel(axis, arm, path, sets, shades, year):
    """One panel of the distress paths: the arm's seed mean of one stored monthly series (``PATHS``' entry ``path``) at
    each distress level (``sets``, level to jobs, each in its shade), with the distress year (start, length) shaded."""
    key, title, unit, scale, _ = path
    start, length = year
    axis.axvspan(start + 0.5, start + length + 0.5, color=GRID, alpha=0.6, linewidth=0)
    for shade, (level, jobs) in zip(shades, sets.items()):
        mean = paths(jobs, arm, key, scale)[0]
        axis.plot(np.arange(1, mean.size + 1), mean, color=shade, linewidth=1.6, label=f"+{percent(level)}% a month")
    style(axis, f"{arm}: {title.split(' (')[0]}", LABELS["month"], unit)


# What demurrage adds, M1 less U (key reader, title, unit).
EFFECTS = ((lambda c, arm: number(c[arm]["A_W2"]) * 100, "Participation, years 4 and 5", "points"),
           (lambda c, arm: number(c[arm]["N"]) * DOLLARS, "Pool capital N, years 4 and 5", "$ a person"),
           (gain_against_s0, "Mean gain against S0", "$ a person a year"),
           (lambda c, arm: w2(c[arm]["liquidity"]["failed_usd_a_year"]), "Failed payments, years 4 and 5",
            "$ a person a year"))


def demurrage_effect(cells, output, written):
    """M1 less U over (r_out, a0), one column per distress level and one row per measure."""
    rates, a0s, levels, by_key = grid_of(cells)
    if not any("U" in c and "M1" in c for c in cells):
        print("demurrage_effect skipped: it needs U and M1.")
        return
    fig, axes = plt.subplots(len(EFFECTS), len(levels), figsize=(2.6 * len(levels) + 1.0, 2.0 * len(EFFECTS)),
                             squeeze=False, constrained_layout=True)
    for row, (read, title, unit) in zip(axes, EFFECTS):
        values = {level: effect_grid(read, level, (rates, a0s, by_key)) for level in levels}
        top = max([float(np.nanmax(np.abs(grid))) for grid in values.values() if np.isfinite(grid).any()] + [1e-9])
        norm = TwoSlopeNorm(vcenter=0.0, vmin=-top, vmax=top)
        images = list(map(lambda axis, level: effect_panel(axis, values[level], norm, f"{title}\nextra job loss "
                                                           f"{percent(level)}% a month", (rates, a0s)), row, levels))
        fig.colorbar(images[-1], ax=row.tolist(), fraction=0.02, pad=0.01, label=f"M1 less U, {unit}")
    fig.suptitle("What demurrage adds: M1 less U on the same draws (seed means)", x=0.01, ha="left", color=INK,
                 fontsize=9)
    save(fig, output, "demurrage_effect", written)


def effect_grid(read, level, grid):
    """M1 less U on one measure (``read``) in every (r_out, a0) cell at one distress level, NaN where either is missing;
    ``grid`` is ``grid_of``'s r_out values, a0 values and cells by key."""
    rates, a0s, by_key = grid
    values = np.full((len(rates), len(a0s)), np.nan)
    for (j, rate), (i, a0) in product(enumerate(rates), enumerate(a0s)):
        cell = by_key.get((rate, a0, level))
        if cell and "U" in cell and "M1" in cell:
            values[j, i] = read(cell, "M1") - read(cell, "U")
    return values


def effect_panel(axis, values, norm, title, ticks):
    """One panel of what demurrage adds: the grid ``values`` (``effect_grid``) on the shared colour scale ``norm``,
    each cell labelled; returns the image for the row's colour bar. ``ticks`` are the r_out and a0 values."""
    rates, a0s = ticks
    image = axis.imshow(np.ma.masked_invalid(values), cmap=DIVERGING, norm=norm, origin="lower", aspect="auto")
    for (j, i), value in np.ndenumerate(values):
        axis.text(i, j, "n/a" if not np.isfinite(value) else f"{value:+.1f}", ha="center", va="center", fontsize=6,
                  color=INK if np.isfinite(value) else MUTED)
    axis.set_xticks(range(len(a0s)), labels=[f"{a:g}" for a in a0s])
    axis.set_yticks(range(len(rates)), labels=[percent(r) for r in rates])
    style(axis, title, LABELS["a0"], LABELS["r_out"])
    axis.grid(False)
    return image


def bridging_vs_card(cells, summary, output, written):
    """The bridging rate r_b (solid) and the coupon r_g (dashed) of each pool arm in years 4 and 5 against the card
    APR tiers at each r_out, without distress; M2's rates are put in nominal terms by adding CPI."""
    rates, a0s, _, by_key = grid_of(cells)
    arms = [arm for arm in POOL_ARMS if any(arm in c for c in cells)]
    card = {row["r_out"]: row["card"] for row in summary.get("outside_rates", [])}
    if not arms or 0.0 not in {c["distress"] for c in cells}:
        print("bridging_vs_card skipped: it needs a pool arm without distress.")
        return
    inflation = 12 * summary["economy"]["inflation"] * 100
    fig, axes = plt.subplots(1, len(rates), figsize=(4.2 * len(rates), 3.4), squeeze=False, sharey=True,
                             constrained_layout=True)
    list(map(lambda axis, rate: bridging_panel(axis, rate, card, arms, (a0s, by_key), inflation), axes[0], rates))
    axes[0][0].legend(frameon=False, loc="best")
    fig.suptitle("A pool bridge against the card, years 4 and 5 without distress (dashed: the coupon r_g, the rate "
                 "before demurrage's cut)", x=0.01, ha="left", color=INK, fontsize=9)
    save(fig, output, "bridging_vs_card", written)


def bridging_panel(axis, rate, card, arms, grid, inflation):
    """One panel of the bridge against the card at one r_out: the card APR tiers shaded, and each pool arm's bridging
    rate (solid) and coupon (dashed) over a0 without distress, M2's with CPI added (``inflation``, % a year); ``grid``
    is the a0 values and the cells by key."""
    a0s, by_key = grid
    if rate in card:
        axis.axhspan(100 * min(card[rate]), 100 * max(card[rate]), color=GRID, alpha=0.8, linewidth=0,
                     label="card APR, by score tier")
    for arm in arms:
        colour, _, marker = ARM_STYLE[arm]
        shift = inflation if arm == "M2" else 0.0
        read = lambda key: np.array([number(by_key.get((rate, a0, 0.0), {}).get(arm, {}).get(key)) for a0 in a0s])
        axis.plot(a0s, read("r_b_pct") + shift, color=colour, marker=marker, markersize=4, linewidth=2,
                  label=f"{arm} bridging rate" + (" (+ CPI)" if shift else ""))
        axis.plot(a0s, read("r_g_pct") + shift, color=colour, linewidth=1.2, linestyle="--")
    style(axis, f"r_out {percent(rate)}% a year", LABELS["a0"], "% a year, nominal")


def liquidity_vs_s0(cells, output, written):
    """Precautionary money and failed payments against S0 over a0 at each r_out without distress, in years 4 and 5,
    and the money held per dollar of shortfall covered a year, each arm with S0 beside."""
    rates, a0s, _, by_key = grid_of(cells)
    arms = [arm for arm in ("M0",) + POOL_ARMS if any(arm in c for c in cells)]
    if not arms or 0.0 not in {c["distress"] for c in cells}:
        print("liquidity_vs_s0 skipped: it needs an arm beside S0 without distress.")
        return
    rows = (("precautionary_usd", "Precautionary money, less S0", "$ a person", True),
            ("precautionary_per_dollar_covered", "Precautionary money per $ of shortfall covered a year", "$", False),
            ("failed_usd_a_year", "Failed payments, less S0", "$ a person a year", True))
    fig, axes = plt.subplots(len(rows), len(rates), figsize=(4.2 * len(rates), 2.7 * len(rows)), squeeze=False,
                             sharex=True, constrained_layout=True)
    # One panel a measure (row) and r_out (column), in that order.
    for (place, column), axis in np.ndenumerate(axes):
        liquidity_panel(axis, rows[place], rates[column], arms, (a0s, by_key), place == len(rows) - 1)
    axes[1][0].legend(frameon=False, loc="best")
    fig.suptitle("Liquidity against S0, years 4 and 5 without distress (seed means)", x=0.01, ha="left", color=INK,
                 fontsize=9)
    save(fig, output, "liquidity_vs_s0", written)


def liquidity_panel(axis, measure, rate, arms, grid, last):
    """One panel of liquidity against S0 at one r_out without distress, in years 4 and 5: one measure (key, title, unit
    and whether it is read less S0) over a0 for each arm, S0 drawn beside a level; ``grid`` is the a0 values and the
    cells by key, and ``last`` labels the bottom row's a0 axis."""
    key, title, unit, against = measure
    a0s, by_key = grid
    cell = lambda a0: by_key.get((rate, a0, 0.0), {})
    s0 = np.array([w2(cell(a0).get("S0_liquidity", {}).get(key)) for a0 in a0s])
    if against:
        axis.axhline(0, color=MUTED, linewidth=0.8)
    else:
        colour, line, marker = ARM_STYLE["S0"]
        axis.plot(a0s, s0, color=colour, linestyle=line, marker=marker, markersize=4, linewidth=1.6, label="S0")
    for arm in arms:
        colour, line, marker = ARM_STYLE[arm]
        values = np.array([w2(cell(a0).get(arm, {}).get("liquidity", {}).get(key)) for a0 in a0s])
        axis.plot(a0s, values - s0 if against else values, color=colour, linestyle=line, marker=marker, markersize=4,
                  linewidth=1.6, label=arm)
    style(axis, f"{title}\nr_out {percent(rate)}% a year", LABELS["a0"] if last else "", unit)


def draw(store, output=None, majority=False):
    """Every figure the store at ``store`` supports, written into ``output`` (by default the store), each as PNG and
    PDF; returns the names written. A figure already there is never overwritten (``save``)."""
    store = Path(store)
    output = Path(output) if output else store
    output.mkdir(parents=True, exist_ok=True)
    setup()
    summary, measures = load(store)
    cells = [cell for cell in summary["cells"] if cell]
    written = []
    region_3d(cells, output, majority, written)
    region_slices(cells, output, majority, written)
    if not majority:
        claim_map(cells, output, written)
        paths_baseline(measures, output, written)
        paths_distress(measures, summary, output, written)
        demurrage_effect(cells, output, written)
        bridging_vs_card(cells, summary, output, written)
        liquidity_vs_s0(cells, output, written)
    return written


def main():
    """Draw the figures of the store named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True, help="the map's folder, holding summary.json")
    parser.add_argument("--output", type=Path, help="where to write the figures (default: the store)")
    parser.add_argument("--majority", action="store_true",
                        help="the region figures on each cell's bare-majority reading")
    args = parser.parse_args()
    store = args.store if args.store.is_absolute() else ROOT / args.store
    output = None if args.output is None else args.output if args.output.is_absolute() else ROOT / args.output
    print("Wrote " + ", ".join(draw(store, output, args.majority)))


if __name__ == "__main__":
    main()

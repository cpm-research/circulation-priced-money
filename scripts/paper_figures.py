"""The paper's figures, drawn from a stored map's JSON, so that no figure is drawn by hand.

Run from the repository root once a map has finished:
    python -X utf8 scripts/paper_figures.py --map results/<map> [--sizes results/<size folder> ...]
                                            [--side name=results/<folder> ...] [--out paper/figures]

It reads only the JSON the population runner wrote (summary.json, cells.json, measures.json) and imports nothing
from the runner or the engine. It runs no simulation. Each figure is written as a PDF and a 200 dpi PNG. A field a
figure needs that the result does not store is never filled in: the figure draws what it can and one line names
what is missing.

The JSON keeps the runner's code names for the arrangements: S0 banks and cards, M0 best-case DeFi, U the pool
without the holding charge, M1 CPM, M2 indexed CPM.
"""
import argparse
import gzip
import io
import json
import math
import re
import textwrap
from statistics import NormalDist
from itertools import chain, product
from pathlib import Path
import sys

import matplotlib as mpl

mpl.use("Agg")                                         # files only, no window
import matplotlib.pyplot as plt                        # noqa: E402  (after the backend is chosen)
import networkx as nx                                  # noqa: E402
import numpy as np                                     # noqa: E402
from matplotlib.collections import LineCollection      # noqa: E402
from matplotlib.colors import ListedColormap           # noqa: E402
from matplotlib.lines import Line2D                    # noqa: E402
from matplotlib.patches import Patch                   # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so that ``scripts`` imports as a package
from scripts.paper_numbers import defi_named, second_run_store   # noqa: E402  (after the path is set)

# ----------------------------------------------------------------------------------------------------------------------
# Fixed choices: colours, names, lines and thresholds
# ----------------------------------------------------------------------------------------------------------------------
# Arrangement colours, checked for colour-vision deficiency; fixed by arrangement in every figure, never by rank.
ARM_COL = {"S0": "#4d4d4d", "M0": "#2166ac", "U": "#e08214", "M1": "#1b7837", "M2": "#762a83"}
ARM_LAB = {"S0": "Banks and cards", "M0": "Best-case DeFi", "U": "Pool without the charge", "M1": "CPM",
           "M2": "Indexed CPM"}
CPM = "M1"                                             # the paper's CPM is the nominal one
INK, SOFT = "#222222", "#666666"                       # text and reference lines: dark grey, never a series colour
RATE_STYLE = {0.02: ("-", "o"), 0.044: ("--", "s"), 0.06: (":", "^")}   # line and marker by outside rate
RUN_LINE = 0.6                                         # a pool run: bridges served in years 4 and 5 below this
HEADLINE = 0.02                                        # 2 points of distress, the stress headline
MARGIN = -2.0                                          # the claim's margin, $ a person a year
OWNER_SPREAD = 0.25                                    # owners' alternative a = outside rate + 0.25 point
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}   # Student t, 97.5% point, by degrees of freedom
LAMBDAS = np.linspace(0.0, 0.2, 4001)                  # the grid one leaving rate lambda is fitted on, a month
MM = 1 / 25.4                                          # inches in a millimetre
WIDTH = 164 * MM                                       # the paper's column width

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"], "mathtext.fontset": "stix",
    "font.size": 8.5, "axes.labelsize": 8.5, "axes.titlesize": 8.5, "legend.fontsize": 8, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": "#888888", "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": "#e6e6e6", "grid.linewidth": 0.5, "axes.axisbelow": True, "lines.linewidth": 1.75,
    "lines.markersize": 5, "legend.frameon": False, "axes.titlelocation": "left", "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03})


# ----------------------------------------------------------------------------------------------------------------------
# Reading the stored JSON
# ----------------------------------------------------------------------------------------------------------------------
def shipped_files(folder, name):
    """The files a store is shipped as in ``folder``, in order: ``name``.gz, or its volumes ``name``.gz.1of6 to .6of6
    (scripts/pack_results.py cuts a store over 50 MB into them); empty when the folder holds none."""
    folder = Path(folder)
    if (folder / (name + ".gz")).exists():
        return [folder / (name + ".gz")]
    found = sorted((int(m.group(1)), int(m.group(2)), p) for p in folder.glob(name + ".gz.*of*")
                   if (m := re.search(r"\.gz\.(\d+)of(\d+)$", p.name)))
    if [(k, n) for k, n, _ in found] != [(k, len(found)) for k in range(1, len(found) + 1)]:
        raise ValueError(f"{folder}: the volumes of {name} are not a whole set: {[p.name for _, _, p in found]}")
    return [p for _, _, p in found]


def stored_text(folder, name):
    """The text of one stored file of a results folder: ``name`` as the runner writes it, or as results are shipped,
    compressed (``shipped_files``; volumes are joined in order)."""
    plain = Path(folder) / name
    if plain.exists():
        return plain.read_text(encoding="utf-8")
    files = shipped_files(folder, name)
    if not files:
        raise FileNotFoundError(f"{folder} holds no {name}, plain or compressed")
    data = b"".join(gzip.decompress(p.read_bytes()) for p in files)
    with io.TextIOWrapper(io.BytesIO(data), encoding="utf-8") as source:     # line ends read as read_text reads them
        return source.read()


def dig(item, path):
    """The value at ``path`` (keys, or indices for lists) inside ``item``, or None where the JSON stops short."""
    for key in path:
        if isinstance(item, dict) and key in item:
            item = item[key]
        elif isinstance(item, list) and isinstance(key, int) and -len(item) <= key < len(item):
            item = item[key]
        else:
            return None
    return item


def number(value):
    """A stored value as a float, NaN where it is absent, None or not a number."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else np.nan


def place(item):
    """A cell's or job's place on the grid, (outside rate, launch level, distress), rounded so floats match."""
    return tuple(round(float(item[k]), 6) for k in ("r_out", "a0", "distress"))


def grouped(jobs):
    """Jobs grouped by grid place, each group in seed order."""
    found = {}
    for job in sorted(jobs, key=lambda j: j["seed"]):
        found.setdefault(place(job), []).append(job)
    return found


# Circulation (fig_circulation): the arrangements drawn and whose people each is read for (banks and cards have no
# network, so everyone, whom the engine files as non-participants; the others their participants), the two orderings
# of the coin ages with their line styles, and the years read (yearly records, index k is year k + 1 after launch).
CIRC_ARMS = ("S0", "M0", "U", "M1")
CIRC_GROUP = dict(S0="non_participants", M0="participants", U="participants", M1="participants")
ORDERINGS = (("lifo", "-", "last in first out"), ("fifo", "--", "first in first out"))
CIRC_YEARS = slice(3, 5)                               # years 4 and 5 after launch


def kept_monthly(job):
    """What is kept of a measures.json job: its place, seed, CPM's monthly series and, for each arrangement drawn
    in fig_circulation and each ordering, the yearly mean holding time of money spent and the histogram of value
    spent by holding time for the arrangement's group, with the histogram's bin edges (None where not stored)."""
    hold = lambda arm, conv, key: dig(job, ["series", arm, "holding_velocity", conv, CIRC_GROUP[arm], key])
    circulation = {arm: {conv: dict(mean_tau=hold(arm, conv, "mean_tau"), histogram=hold(arm, conv, "histogram"))
                         for conv, _, _ in ORDERINGS} for arm in CIRC_ARMS}
    return dict(r_out=job["r_out"], a0=job["a0"], distress=job["distress"], seed=job["seed"],
                recirculated=job.get("recirculated", False), monthly=dig(job, ["monthly", CPM]) or {},
                circulation=circulation, edges=dig(job, ["series", CPM, "holding_velocity", "edges"]))


class Result:
    """One stored results folder: summary.json's cells, cells.json's jobs and CPM's monthly series of measures.json,
    each indexed by grid place. Only the cells of the map's own convention (lenders' interest kept or returned)."""

    def __init__(self, folder):
        self.folder = Path(folder)
        # Each store is read as the runner writes it (name.json) or as results are shipped (name.json.gz, or volumes).
        has = lambda name: (self.folder / name).exists() or bool(shipped_files(self.folder, name))
        read = lambda name: json.loads(stored_text(self.folder, name))
        self.summary = read("summary.json")
        own = bool(dig(self.summary, ["economy", "lender_income_recirculated"]) or False)
        same = lambda item: item is not None and bool(item.get("recirculated")) == own
        self.cells = {place(c): c for c in self.summary.get("cells", []) if same(c)}
        self.jobs = grouped([j for j in (read("cells.json")["jobs"] if has("cells.json") else []) if same(j)])
        raw = read("measures.json")["jobs"] if has("measures.json") else []
        self.monthly = grouped([j for j in map(kept_monthly, raw) if same(j)])
        # The grid's axes: the places' columns (outside rates, launch levels, distress levels), each sorted.
        self.rates, self.launches, self.levels = map(sorted, map(set, list(zip(*self.cells)) or [(), (), ()]))
        self.n = dig(self.summary, ["economy", "n"])
        # The holding-time histogram's bin edges in days (the last bin open above its edge), as the first job stores.
        self.edges = next((job["edges"] for job in chain.from_iterable(self.monthly.values()) if job.get("edges")),
                          None)

    def mean(self, path, r, a, d):
        """The seed mean summary.json stores at ``path`` in cell (r, a, d); NaN where not stored."""
        return number(dig(self.cells.get((r, a, d)), path))

    def seeds(self, path, r, a, d):
        """Each seed's value at ``path`` in cells.json's jobs of cell (r, a, d); empty where not stored."""
        values = np.array([number(dig(job, path)) for job in self.jobs.get((r, a, d), [])])
        return values if values.size and np.isfinite(values).all() else np.array([])

    def series(self, name, r, a, d):
        """CPM's monthly ``name`` in cell (r, a, d) as a seeds x months array, or None where any seed lacks it."""
        found = [job["monthly"].get(name) for job in self.monthly.get((r, a, d), [])]
        return np.array(found, float) if found and all(v is not None for v in found) else None

    def holding(self, arm, conv, r, a, d):
        """Each seed's mean holding time of money spent (days) for ``arm`` under ordering ``conv`` in cell (r, a, d),
        the mean of years 4 and 5; empty where any seed does not store it or it is undefined."""
        found = [dig(job, ["circulation", arm, conv, "mean_tau"]) for job in self.monthly.get((r, a, d), [])]
        if not found or any(not isinstance(v, list) or len(v) < CIRC_YEARS.stop for v in found):
            return np.array([])
        values = np.array([np.mean(np.array(v, float)[CIRC_YEARS]) for v in found])
        return values if np.isfinite(values).all() else np.array([])

    def spent_shares(self, arm, conv, r, a, d):
        """The share of value spent in each holding-time bin over years 4 and 5 for ``arm`` under ordering ``conv``
        in cell (r, a, d), the mean over seeds of each seed's shares; None where any seed does not store it."""
        found = [dig(job, ["circulation", arm, conv, "histogram"]) for job in self.monthly.get((r, a, d), [])]
        if not found or any(not isinstance(v, list) or len(v) < CIRC_YEARS.stop for v in found):
            return None
        spent = np.array([np.array(v, float)[CIRC_YEARS].sum(axis=0) for v in found])   # seeds x bins
        totals = spent.sum(axis=1, keepdims=True)
        return np.mean(spent / totals, axis=0) if (totals > 0).all() else None

    def curve(self, path, r, d):
        """The stored seed mean at ``path`` across the launch levels, at outside rate r and distress d."""
        return np.array([self.mean(path, r, a, d) for a in self.launches])

    def seed_band(self, path, r, d):
        """The lowest and highest seed at ``path`` across the launch levels (NaN where not stored)."""
        found = [self.seeds(path, r, a, d) for a in self.launches]
        low = np.array([v.min() if v.size else np.nan for v in found])
        return low, np.array([v.max() if v.size else np.nan for v in found])


class Missing:
    """What one figure could not draw: collects the JSON paths not stored and prints them on one line."""

    def __init__(self, name):
        self.name, self.what = name, []

    def check(self, values, what):
        """Note ``what`` as missing when ``values`` holds no finite number; returns whether anything is there."""
        there = values is not None and np.size(values) > 0 and np.isfinite(np.asarray(values, float)).any()
        if not there and what not in self.what:
            self.what.append(what)
        return there

    def report(self):
        """Print the one line naming what is missing (nothing when the figure is complete)."""
        if self.what:
            print(f"{self.name}: not stored, not drawn: " + "; ".join(self.what))


# ----------------------------------------------------------------------------------------------------------------------
# Drawing helpers
# ----------------------------------------------------------------------------------------------------------------------
def pct(value):
    """A share as a per cent label: 0.044 reads 4.4%."""
    return f"{value * 100:g}%"


def launch_axis(ax, res, label=True):
    """The launch-participation x axis in per cent."""
    ax.set_xticks(res.launches)
    ax.set_xticklabels([f"{a * 100:g}" for a in res.launches])
    if label:
        ax.set_xlabel("Launch participation (%)")


def tag(ax, text):
    """A panel's small descriptive heading on the left (never a result)."""
    ax.set_title(text, loc="left", fontsize=8.5, color=INK)


def save(fig, out, name, whole=False):
    """Write the figure as PDF and 200 dpi PNG and close it. The files carry no creation date, so the same result
    gives the same bytes on every run. ``whole`` keeps the figure's own canvas where the default trims to its
    marks (for a figure whose frames reach past the canvas on purpose)."""
    box = dict(bbox_inches=fig.bbox_inches) if whole else {}
    fig.savefig(out / f"{name}.pdf", metadata={"CreationDate": None, "ModDate": None}, **box)
    fig.savefig(out / f"{name}.png", dpi=200, metadata={"Software": None}, **box)
    plt.close(fig)
    print(f"wrote {name}")


def bottom_legend(fig, handles, ncol, y=0.0):
    """One legend for the whole figure, centred under the panels."""
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, y), ncol=ncol, handlelength=2.2,
               columnspacing=1.4)


def arm_handles(arms, marker="o"):
    """Legend entries for arrangements in their fixed colours."""
    return [Line2D([], [], color=ARM_COL[a], marker=marker, label=ARM_LAB[a]) for a in arms]


def rate_handles(rates, color=INK):
    """Legend entries for outside rates by line style and marker."""
    return [Line2D([], [], color=color, ls=RATE_STYLE.get(r, ("-", "o"))[0], marker=RATE_STYLE.get(r, ("-", "o"))[1],
                   label=f"outside rate {pct(r)}") for r in rates]


def t_interval(values):
    """Mean and half-width of the 95% interval of a seed sample (Student t); NaN when fewer than two seeds."""
    if values.size < 2:
        return (values.mean() if values.size else np.nan), np.nan
    df = values.size - 1
    t = T975[max(k for k in T975 if k <= df)] if df <= 30 else 1.96
    return values.mean(), t * values.std(ddof=1) / np.sqrt(values.size)


# ----------------------------------------------------------------------------------------------------------------------
# Figure 1: failed payments
# ----------------------------------------------------------------------------------------------------------------------
FAIL_MEAN = {"S0": ["S0_failures_pct"], **{a: [a, "failures_pct"] for a in ("M0", "U", "M1")}}
FAIL_SEED = {"S0": ["S0", "failures_pct"], **{a: ["arms", a, "failures_pct"] for a in ("M0", "U", "M1")}}


def seed_alpha(count):
    """How strongly one seed's thin line is drawn, fainter the more seeds there are (3 seeds 0.5, 30 seeds 0.08)."""
    return float(min(0.5, max(0.08, 1.5 / max(count, 1))))


def failure_panel(ax, res, r, d, miss):
    """One panel: failed payments against launch participation for the four arrangements: the seed mean, the range
    of the seeds as a band and each seed as a thin line, since a mean is not what any one run does."""
    for arm in ("S0", "M0", "U", "M1"):
        y = res.curve(FAIL_MEAN[arm], r, d)
        lo, hi = res.seed_band(FAIL_SEED[arm], r, d)
        if miss.check(y, f"summary.json cells[].{'.'.join(FAIL_MEAN[arm])}"):
            ax.plot(res.launches, y, color=ARM_COL[arm], marker="o", ms=4)
        if miss.check(lo, f"cells.json jobs[].{'.'.join(FAIL_SEED[arm])}"):
            ax.fill_between(res.launches, lo, hi, color=ARM_COL[arm], alpha=0.18, lw=0)
        # Each seed's own curve, where every launch level stores the same seeds (jobs are kept in seed order).
        each = [res.seeds(FAIL_SEED[arm], r, a, d) for a in res.launches]
        if each and each[0].size and len({v.size for v in each}) == 1:
            ax.plot(res.launches, np.array(each), color=ARM_COL[arm], lw=0.5, alpha=seed_alpha(each[0].size),
                    zorder=1)


def fig_failed_payments(res, out):
    """Failed payments against launch participation, one panel per outside rate, no distress and 2 points."""
    miss = Missing("fig_failed_payments")
    levels = [d for d in (0.0, HEADLINE) if d in res.levels]
    fig, axes = plt.subplots(len(levels), len(res.rates), figsize=(WIDTH, 2.0 * len(levels) + 0.4), sharex=True,
                             sharey="row", squeeze=False)
    for ax, (d, r) in zip(axes.flat, product(levels, res.rates)):
        failure_panel(ax, res, r, d, miss)
        launch_axis(ax, res, label=ax in axes[-1])
    # Each row has its own scale (failures are higher under distress), from zero to just above the row's largest
    # value; it is set once per row after every panel is drawn, so no panel's data is cut off.
    [row[0].set_ylim(0, 1.05 * max(ax.dataLim.y1 for ax in row)) for row in axes]
    [tag(ax, f"Outside rate {pct(r)}") for ax, r in zip(axes[0], res.rates)]
    [ax.set_ylabel(f"Failed payments (%)\n{'no distress' if d == 0 else f'{d * 100:g} points of distress'}")
     for ax, d in zip(axes[:, 0], levels)]
    fig.tight_layout(h_pad=0.8, w_pad=0.6)
    bottom_legend(fig, arm_handles(("S0", "M0", "U", "M1")), ncol=4)
    save(fig, out, "fig_failed_payments")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 2: CPM's gain against banks and against best-case DeFi
# ----------------------------------------------------------------------------------------------------------------------
def gain_path(yard, end, bound=False):
    """Where a cell stores CPM's complete gain over ``yard`` at one end of the bracket (zero or face value)."""
    return [CPM, "against", yard, "complete_gain", end] + (["bound"] if bound else []) + ["gain_usd_a_year"]


def gain_panel(ax, res, r, yard, miss):
    """One panel: the complete gain bracket without the bound (a band from zero to face value) and under the
    cash-advance bound (a lighter band with dashed edges), with the margin as a thin line."""
    x = np.array(res.launches)
    for bound, alpha, ls in ((False, 0.45, "-"), (True, 0.15, "--")):
        zero, face = (res.curve(gain_path(yard, end, bound), r, 0.0) for end in ("zero", "face"))
        what = f"summary.json cells[].{'.'.join(gain_path(yard, '<zero|face>', bound))}"
        if miss.check(zero, what) and miss.check(face, what):
            ax.fill_between(x, zero, face, color=ARM_COL[CPM], alpha=alpha, lw=0)
            ax.plot(x, zero, ls, color=ARM_COL[CPM], lw=1.5, marker="o" if not bound else None, ms=4)
            ax.plot(x, face, ls, color=ARM_COL[CPM], lw=1.5, marker="o" if not bound else None, ms=4, mfc="white")
    ax.axhline(0, color=SOFT, lw=0.6)
    ax.axhline(MARGIN, color=INK, lw=0.7, ls=":")


def fig_gains(res, out):
    """CPM's gain a person a year against banks (top row) and best-case DeFi (bottom row), no distress."""
    miss = Missing("fig_gains")
    yards = ("S0", "M0")
    fig, axes = plt.subplots(2, len(res.rates), figsize=(WIDTH, 4.4), sharex=True, sharey="row", squeeze=False)
    for ax, (yard, r) in zip(axes.flat, product(yards, res.rates)):
        gain_panel(ax, res, r, yard, miss)
        launch_axis(ax, res, label=ax in axes[-1])
    [tag(ax, f"Outside rate {pct(r)}") for ax, r in zip(axes[0], res.rates)]
    names = {"S0": "banks and cards", "M0": defi_named("best-case DeFi", res.summary)}
    [ax.set_ylabel(f"Gain over {names[y]}\n(\\$ a person a year)") for ax, y in zip(axes[:, 0], yards)]
    fig.tight_layout(h_pad=0.8, w_pad=0.6)
    col = ARM_COL[CPM]
    bound = [Patch(facecolor=col, alpha=0.15, edgecolor=col, ls="--", label="bracket under the cash-advance bound")]
    bottom_legend(fig, [
        Line2D([], [], color=col, marker="o", ms=4, label="sellers' extra sales at zero"),
        Line2D([], [], color=col, marker="o", ms=4, mfc="white", label="sellers' extra sales at face value"),
        Patch(color=col, alpha=0.45, label="bracket as built")]
        + (bound if not any("bound" in w for w in miss.what) else [])   # only what was drawn
        + [Line2D([], [], color=INK, lw=0.7, ls=":", label="-\\$2 margin")], ncol=3)
    save(fig, out, "fig_gains")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 3: what the holding charge does
# ----------------------------------------------------------------------------------------------------------------------
def price_panel(ax, res, miss):
    """(a) The bridge price to the borrower by outside rate, CPM and the pool without the charge: the median over
    the launch levels with no distress, bars from the lowest to the highest launch level."""
    x = np.arange(len(res.rates))
    for arm, dx in (("U", -0.12), (CPM, 0.12)):
        values = np.array([res.curve([arm, "r_b_pct"], r, 0.0) for r in res.rates])   # rates x launches
        if miss.check(values, f"summary.json cells[].{arm}.r_b_pct"):
            mid = np.nanmedian(values, axis=1)
            err = [mid - np.nanmin(values, axis=1), np.nanmax(values, axis=1) - mid]
            ax.errorbar(x + dx, mid, yerr=err, fmt="o", color=ARM_COL[arm], ms=5, capsize=2.5, lw=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels([pct(r) for r in res.rates])
    ax.set_xlim(-0.5, len(res.rates) - 0.5)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Outside rate")
    ax.set_ylabel("Bridge price to the borrower (% a year)")


def served_lines(ax, res, arm, miss):
    """(b) Bridges served against launch participation for one arrangement, a line per outside rate."""
    for r in res.rates:
        y = res.curve([arm, "bridges_drawn_over_wanted"], r, 0.0)
        ls, mk = RATE_STYLE.get(r, ("-", "o"))
        if miss.check(y, f"summary.json cells[].{arm}.bridges_drawn_over_wanted"):
            ax.plot(res.launches, 100 * y, ls=ls, marker=mk, color=ARM_COL[arm], ms=4)


def charge_theory(res, r, a):
    """The holding charge the theory gives, c = a B / W in % a year, in one cell with no distress: a the owners'
    alternative each seed stores, B / W the seed mean of the years 4 and 5 bridge book over the wallet balance
    (monthly P_bar over p_bt). NaN where any input is not stored."""
    alt = res.seeds(["arms", CPM, "owners_excess", "alternative_pct"], r, a, 0.0)
    book, wallet = res.series("P_bar", r, a, 0.0), res.series("p_bt", r, a, 0.0)
    if not alt.size or book is None or wallet is None:
        return np.nan
    return float(np.mean(alt * np.nanmean(book[:, 36:60], axis=1) / np.nanmean(wallet[:, 36:60], axis=1)))


def charge_lines(ax, res, miss):
    """(c) CPM's holding charge c against launch participation, a line per outside rate, with the theory a B / W
    as open markers where the stored fields allow."""
    for r in res.rates:
        ls, mk = RATE_STYLE.get(r, ("-", "o"))
        y = res.curve([CPM, "c_pct"], r, 0.0)
        if miss.check(y, f"summary.json cells[].{CPM}.c_pct"):
            ax.plot(res.launches, y, ls=ls, marker=mk, color=ARM_COL[CPM], ms=4)
        theory = np.array([charge_theory(res, r, a) for a in res.launches])
        if miss.check(theory, f"theory c = aB/W: measures.json jobs[].monthly.{CPM}.P_bar and .p_bt"):
            ax.plot(res.launches, theory, ls="", marker=mk, ms=7, mfc="none", mec=INK, mew=0.9)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Demurrage c (% a year)")


def theta_panel(ax, res, miss):
    """(d) CPM's theta against the outside rate (every launch level with no distress) and the theory ceiling
    a / (a + o), a = outside rate + 0.25 point, o the stored inputs.o (2% a year)."""
    o = 1200 * number(dig(res.summary, ["inputs", "o"]))
    rates = np.repeat(res.rates, len(res.launches))
    theta = np.concatenate([res.curve([CPM, "theta"], r, 0.0) for r in res.rates])
    if miss.check(theta, f"summary.json cells[].{CPM}.theta"):
        ax.plot(100 * rates, theta, "o", color=ARM_COL[CPM], ms=5, mfc="none", mew=1.1)
    grid = np.linspace(min(res.rates) - 0.005, max(res.rates) + 0.005, 50) * 100
    if miss.check(np.array([o]), "summary.json inputs.o"):
        ax.plot(grid, (grid + OWNER_SPREAD) / (grid + OWNER_SPREAD + o), color=INK, lw=1.2)
    ax.set_xticks([100 * r for r in res.rates])
    ax.set_xticklabels([pct(r) for r in res.rates])
    ax.set_xlabel("Outside rate")
    ax.set_ylabel("Theta, share of bridging the charge pays")
    ax.set_ylim(0, 1)


def fig_charge(res, out):
    """What the holding charge does: CPM against the pool without the charge, no distress, four panels."""
    miss = Missing("fig_charge")
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 5.0))
    (a, b), (c, d) = axes
    price_panel(a, res, miss)
    tag(a, "(a) Bridge price")
    [served_lines(b, res, arm, miss) for arm in ("U", CPM)]
    b.set_ylabel("Bridges served, years 4 and 5 (%)")
    launch_axis(b, res)
    tag(b, "(b) Bridges served")
    charge_lines(c, res, miss)
    launch_axis(c, res)
    tag(c, "(c) Holding charge")
    theta_panel(d, res, miss)
    tag(d, "(d) Theta")
    fig.tight_layout(h_pad=1.2, w_pad=1.5)
    theory = [] if any("theory c" in w for w in miss.what) else [   # only when the markers were drawn
        Line2D([], [], ls="", marker="o", ms=7, mfc="none", mec=INK, label="theory c = aB/W (c)")]
    # The legend fills column by column: arrangements, then outside rates, then the theory entries.
    bottom_legend(fig, arm_handles(("U", CPM)) + [Line2D([], [], ls="", label=" ")] + rate_handles(res.rates)
                  + theory + [Line2D([], [], color=INK, lw=1.2, label="theory ceiling a/(a+o) (d)"),
                              Line2D([], [], ls="", marker="o", mfc="none", color=ARM_COL[CPM],
                                     label="CPM, each launch level (d)")], ncol=3)
    save(fig, out, "fig_charge")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 4: the claim's region
# ----------------------------------------------------------------------------------------------------------------------
# Each cell's reading: code, legend text, marker, face, edge.
REGION_KINDS = ((3, "passes as built and under the bound", "o", ARM_COL[CPM], ARM_COL[CPM]),
                (2, "passes as built only", "o", "white", ARM_COL[CPM]),
                (1, "passes as built, bound not stored", "D", "#bbbbbb", INK),
                (0, "does not pass", "x", INK, INK),
                (-1, "not stored", "$?$", SOFT, SOFT))


def region_code(res, slices, bound_era, r, a, d):
    """One cell's reading of the whole claim, (a), (b) and (d), for CPM: 3 passes without the bound and under it,
    2 without the bound only, 1 without the bound with the bound not stored, 0 does not pass, -1 not stored. From
    the cell's own claim block where it has one, else from claim_statistics.regions (whose 'passing' list follows
    the map's own 'all': without the bound on a map that stores none, without and under it on a map that does).

    With ``res.reading`` "majority" the cell is read on a majority of its seeds instead (the runner's stored
    ``verdict_majority`` and ``verdict_majority_bound``, "stable" or the reason it is not). That is the reading
    for a map with too few seeds for the interval on the share of seeds, such as a three-seed development map."""
    if getattr(res, "reading", "registered") == "majority":
        view = dig(res.cells.get((r, a, d)), [CPM, "region"])
        if dig(view, ["verdict_majority"]) is None:
            return -1
        bound = dig(view, ["verdict_majority_bound"])
        stable = dig(view, ["verdict_majority"]) == "stable"
        return 0 if not stable else 1 if bound is None else 3 if bound == "stable" else 2
    block = dig(res.cells.get((r, a, d)), [CPM, "claim"])
    if block is not None:
        as_built = dig(block, ["all_as_built"]) if bound_era else dig(block, ["all"])
        both = dig(block, ["all"]) if bound_era else None
    else:
        passing = dig(slices.get(d), ["passing"])
        listed = None if passing is None else any(abs(p[0] - r) < 1e-9 and abs(p[1] - a) < 1e-9 for p in passing)
        if bound_era and listed is not None:
            # A level of distress stores one reading for a cell, on the list or off it: its cell with no distress
            # passes both ways and it withstands every level up to this one, or it does not.
            return 3 if listed else 0
        as_built, both = (None, listed) if bound_era else (listed, None)
    if both:
        return 3
    if as_built is None:
        return -1
    return 0 if not as_built else 2 if both is False else 1


def region_panel(ax, res, slices, bound_era, d):
    """One distress level: the grid of outside rate by launch level, each cell marked by its reading."""
    places = list(product(range(len(res.rates)), range(len(res.launches))))
    codes = np.array([region_code(res, slices, bound_era, res.rates[i], res.launches[j], d) for i, j in places])
    rows, cols = np.array(places).T
    # A line marker (x, ?) takes its colour from the face; only a filled marker has an edge of its own.
    [ax.scatter(cols[codes == k], rows[codes == k], marker=m, s=34, facecolor=f,
                edgecolor=e if m in ("o", "D") else None, linewidths=1.1, zorder=3) for k, _, m, f, e in REGION_KINDS]
    ax.set_xticks(range(len(res.launches)))
    ax.set_xticklabels([f"{a * 100:g}" for a in res.launches])
    ax.set_yticks(range(len(res.rates)))
    ax.set_yticklabels([pct(r) for r in res.rates])
    ax.set_xlim(-0.6, len(res.launches) - 0.4)
    ax.set_ylim(-0.6, len(res.rates) - 0.4)
    ax.grid(False)
    tag(ax, f"{d * 100:g} point{'' if d == 0.01 else 's'} of distress" if d else "No distress")
    return set(codes.tolist())


def fig_region(res, out):
    """The claim's region, one small panel per distress level (outside rate by launch participation)."""
    miss = Missing("fig_region")
    slices = {round(float(s["distress"]), 6): s for s in (dig(res.summary, ["claim_statistics", "regions", CPM])
                                                           or [])}
    bound_era = any(dig(c, [CPM, "claim", "d_bound"]) is not None for c in res.cells.values())
    fig, axes = plt.subplots(2, 3, figsize=(WIDTH, 3.5))
    seen = set().union(*[region_panel(ax, res, slices, bound_era, d) for ax, d in zip(axes.flat, res.levels)])
    [ax.set_axis_off() for ax in axes.flat[len(res.levels):]]
    [ax.set_ylabel("Outside rate") for ax in axes[:, 0]]
    [ax.set_xlabel("Launch participation (%)") for ax in axes[-1, :2]]
    axes[0, -1].set_xlabel("Launch participation (%)")
    miss.check(np.array([0.0 if bound_era else np.nan]), f"summary.json cells[].{CPM}.claim.d_bound and "
               ".all_as_built (the reading under the cash-advance bound)")
    miss.check(np.array([np.nan if -1 in seen else 0.0]), "some cells' claim reading (no claim block and no "
               f"claim_statistics.regions.{CPM} entry)")
    handles = [Line2D([], [], ls="", marker=m, ms=6, mfc=f, mec=e, mew=1.1, label=t) for k, t, m, f, e in REGION_KINDS
               if k in seen or k in (3, 2, 0)]
    # The legend names the reading, so a development map is never mistaken for the registered test.
    reading = ("Read on a majority of seeds" if getattr(res, "reading", "registered") == "majority"
               else "Registered reading")
    axes.flat[-1].legend(handles=handles, loc="center left", fontsize=8, handletextpad=0.4, title=reading,
                         title_fontsize=8, alignment="left")
    fig.tight_layout(h_pad=1.0, w_pad=0.8)
    save(fig, out, "fig_region")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# The whole grid in the space of its three controls
# ----------------------------------------------------------------------------------------------------------------------
# Each lattice is drawn without perspective, so equal steps look equal wherever they sit; the layers are the distress
# levels, lifted well apart so that one never hides another.
GRID_VIEW = dict(elev=22, azim=-52)
GRID_LIFT = 2.9                                        # the height of the lattice against its depth
# The claim's reading of a cell: code, legend text, marker, face, edge.
GRID_KINDS = ((3, "in the region", "o", ARM_COL[CPM], ARM_COL[CPM]),
              (2, "passes, outside the largest joined block", "o", "white", ARM_COL[CPM]),
              (0, "does not pass", "x", SOFT, SOFT))
GAIN_MAP = ListedColormap(plt.get_cmap("Greens")(np.linspace(0.18, 1.0, 256)))    # one hue, light to dark
FAIL_MAP = plt.get_cmap("PRGn_r")                      # two hues about a neutral middle: green fewer, purple more


def summary_cells(folder):
    """A map read from its summary alone, as (summary, cells by place); None where no folder is given."""
    if folder is None:
        return None
    summary = json.loads(stored_text(Path(folder), "summary.json"))
    own = bool(dig(summary, ["economy", "lender_income_recirculated"]) or False)
    return summary, {place(c): c for c in summary.get("cells", []) if c is not None and bool(c.get("recirculated")) == own}


def claim_code(summary, r, a, d):
    """One cell's registered reading from the map's stored regions: 3 in the region, 2 passing outside the largest
    joined block, 0 not passing, -1 where the map stores no region at that level."""
    for piece in dig(summary, ["claim_statistics", "regions", CPM]) or []:
        if abs(float(piece["distress"]) - d) < 1e-9:
            inside = lambda cells: any(abs(p[0] - r) < 1e-9 and abs(p[1] - a) < 1e-9 for p in cells)
            return 3 if inside(piece["region"]) else 2 if inside(piece["passing"]) else 0
    return -1


def lattice(ax, rates, launches, levels, marked):
    """One empty lattice: a layer of faint lines for each distress level, the three axes named and ticked, the
    outside rates of ``marked`` carrying a dagger."""
    nx, ny, nz = len(launches), len(rates), len(levels)
    ax.set_proj_type("ortho")
    ax.view_init(**GRID_VIEW)
    ax.set_box_aspect((nx, 1.2 * ny, GRID_LIFT * max(nx, 1.2 * ny)), zoom=1.08)
    ax.patch.set_alpha(0.0)                            # the lattices' frames overlap; only their marks show
    for z in range(nz):
        [ax.plot([0, nx - 1], [y, y], [z, z], color="#dcdcdc", lw=0.4, zorder=1) for y in range(ny)]
        [ax.plot([x, x], [0, ny - 1], [z, z], color="#dcdcdc", lw=0.4, zorder=1) for x in range(nx)]
    [ax.plot([x, x], [y, y], [0, nz - 1], color="#ececec", lw=0.4, zorder=0)
     for x, y in product((0, nx - 1), (0, ny - 1))]
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_visible(False)
        axis.line.set_color("#888888")
    ax.grid(False)
    ax.set_xlim(-0.4, nx - 0.6)
    ax.set_ylim(-0.4, ny - 0.6)
    ax.set_zlim(-0.15, nz - 0.85)
    ax.set_xticks(range(nx))
    ax.set_xticklabels([f"{a * 100:g}" for a in launches], fontsize=5.8)
    ax.set_yticks(range(ny))
    ax.set_yticklabels([f"{r * 100:g}" for r in rates], fontsize=5.8, style="italic" if marked else "normal")
    [label.set_fontstyle("italic" if r in marked else "normal") for label, r in zip(ax.get_yticklabels(), rates)]
    ax.set_zticks(range(nz))
    ax.set_zticklabels([f"{d * 100:g}" for d in levels], fontsize=6.2)
    ax.tick_params(axis="both", which="major", pad=-4, length=2)
    ax.set_xlabel("Launch (%)", fontsize=7, labelpad=-11)
    ax.set_ylabel("Outside rate (%)", fontsize=7, labelpad=-11)


def fig_grid(res, cut, out):
    """Every cell of the map, and of the rate cut where one is given, in the space of the three controls: the
    registered claim, CPM's failed share against that of banks and cards, and its gain in money over banks and
    cards and over best-case DeFi as a share of a year's spending."""
    miss = Missing("fig_grid")
    maps = [(res.summary, res.cells, False)] + ([] if cut is None else [(cut[0], cut[1], True)])
    owner = {}
    for summary, cells, extra in reversed(maps):       # the map last, so a rate both ran is read on the map
        owner.update({r: (summary, cells, extra) for r, _, _ in cells})
    rates = sorted(owner)
    every = list(chain.from_iterable(cells for _, cells, _ in maps))
    launches = sorted({a for _, a, _ in every})
    levels = sorted({d for _, _, d in every})
    marked = {r for r in rates if owner[r][2]}
    places = [(i, j, k) for k, i, j in product(range(len(levels)), range(len(rates)), range(len(launches)))]
    cell = lambda i, j, k: owner[rates[i]][1].get((rates[i], launches[j], levels[k]))
    x, y, z = (np.array([p[n] for p in places], float) for n in (1, 0, 2))

    def read(path, scale=lambda i: 1.0):
        """The stored value at ``path`` in every cell of the lattice, NaN where the cell or the field is absent."""
        return np.array([number(dig(cell(i, j, k), path)) * scale(i) for i, j, k in places])

    def spending(i):
        """What turns dollars a year into per cent of a year of the model's unit of spending, on rate i's map."""
        unit = number(dig(owner[rates[i]][0], ["constants", "MONTH_USD"]))
        return 100 / (12 * unit) if unit > 0 else np.nan

    codes = np.array([claim_code(owner[rates[i]][0], rates[i], launches[j], levels[k]) if cell(i, j, k) is not None
                      else -1 for i, j, k in places])
    fails = 100 * (read([CPM, "failures_pct"]) / read(["S0_failures_pct"]) - 1)
    gains = [read([CPM, "against", yard, "gain_usd_a_year"], spending) for yard in ("S0", "M0")]
    miss.check(np.where(codes >= 0, 1.0, np.nan), f"summary.json claim_statistics.regions.{CPM}")
    miss.check(fails, f"summary.json cells[].{CPM}.failures_pct and S0_failures_pct")
    [miss.check(g, f"summary.json cells[].{CPM}.against.<yardstick>.gain_usd_a_year") for g in gains]

    fig = plt.figure(figsize=(WIDTH, 4.55))
    boxes = tuple((0.243 * k, 0.125) for k in range(4))
    tall = 0.90
    # Each lattice is far taller than wide, and a 3D frame is fitted to a square: the frames are twice a column wide
    # and overlap, so the lattices stand side by side at full height.
    axes = [fig.add_axes([left - 0.135, bottom, 0.5, tall], projection="3d") for left, bottom in boxes]
    [lattice(ax, rates, launches, levels, marked) for ax in axes]
    axes[-1].set_zlabel("Distress (points)", fontsize=7, labelpad=-13)
    size = 13

    for kind, _, marker, face, edge in GRID_KINDS:
        at = codes == kind
        if at.any():
            lined = marker == "x"
            axes[0].scatter(x[at], y[at], z[at], marker=marker, s=size * (0.75 if lined else 1.0), depthshade=False,
                            c=face if lined else None, facecolor=None if lined else face,
                            edgecolor=None if lined else edge, linewidths=0.8, zorder=3)
    fail_norm = mpl.colors.TwoSlopeNorm(vmin=min(np.nanmin(fails), -1.0), vcenter=0.0, vmax=max(np.nanmax(fails), 1.0))
    seen = np.isfinite(fails)
    fail_dots = axes[1].scatter(x[seen], y[seen], z[seen], c=fails[seen], cmap=FAIL_MAP, norm=fail_norm, s=size,
                                depthshade=False, edgecolor="#555555", linewidths=0.25, zorder=3)
    top = max(float(np.nanmax(g)) for g in gains)
    gain_norm = mpl.colors.Normalize(vmin=0.0, vmax=top)
    gain_dots = None
    for ax, values in zip(axes[2:], gains):
        seen = np.isfinite(values)
        below = seen & (values < 0)
        gain_dots = ax.scatter(x[seen & ~below], y[seen & ~below], z[seen & ~below], c=values[seen & ~below],
                               cmap=GAIN_MAP, norm=gain_norm, s=size, depthshade=False, edgecolor="#555555",
                               linewidths=0.25, zorder=3)
        # A gain below zero has no place on a scale that starts at zero: it is drawn as an open ring.
        ax.scatter(x[below], y[below], z[below], s=size, depthshade=False, facecolor="white", edgecolor=INK,
                   linewidths=0.9, zorder=4)
    for (left, bottom), text in zip(boxes, ("(a) The registered claim", "(b) Payments that fail",
                                            "(c) Gain over banks and cards",
                                            defi_named("(d) Gain over best-case DeFi", res.summary))):
        fig.text(left + 0.012, 0.955, text, fontsize=8.5, color=INK, va="bottom")
    handles = [Line2D([], [], ls="", marker=m, ms=4.5, mfc=f, mec=e, mew=0.9, label=t) for k, t, m, f, e in GRID_KINDS
               if (codes == k).any()]
    fig.legend(handles=handles, loc="center", bbox_to_anchor=(0.115, 0.068), ncol=1, fontsize=7.5, handletextpad=0.3,
               labelspacing=0.25)
    bar = fig.colorbar(fail_dots, cax=fig.add_axes([0.275, 0.090, 0.18, 0.016]), orientation="horizontal")
    bar.set_label("CPM against banks and cards (%)", fontsize=7.5, labelpad=2)
    bar.ax.tick_params(labelsize=7, length=2)
    bar = fig.colorbar(gain_dots, cax=fig.add_axes([0.555, 0.090, 0.36, 0.016]), orientation="horizontal")
    bar.set_label("Gain in money, % of a year's spending", fontsize=7.5, labelpad=2)
    bar.ax.tick_params(labelsize=7, length=2)
    save(fig, out, "fig_grid", whole=True)
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 5: where the pool runs under stress
# ----------------------------------------------------------------------------------------------------------------------
SERVED_SEED = ["arms", CPM, "bridges_drawn_over_wanted"]


def served_seeds(res, r, a, d):
    """Each seed's bridges served in years 4 and 5 for CPM: the stored figure in cells.json, else the mean of the
    monthly series over months 37 to 60."""
    values = res.seeds(SERVED_SEED, r, a, d)
    block = None if values.size else res.series("bridges_drawn_over_wanted", r, a, d)
    return values if block is None else np.nanmean(block[:, 36:60], axis=1)


def stress_panel(ax, res, r, cmap, miss):
    """One outside rate: bridges served (seed mean) by launch level and distress, each cell annotated with the
    number of seeds showing a pool run."""
    places = list(product(range(len(res.launches)), range(len(res.levels))))
    found = [served_seeds(res, r, res.launches[i], res.levels[j]) for i, j in places]
    mean = np.array([v.mean() if v.size else np.nan for v in found]).reshape(len(res.launches), len(res.levels))
    runs = [f"{int(np.sum(v < RUN_LINE))}" if v.size else "" for v in found]
    miss.check(mean, f"cells.json jobs[].{'.'.join(SERVED_SEED)}")
    # The scale starts at 50%, below the run line, so the cells near it stand out; lower values show as the lightest.
    image = ax.imshow(100 * mean, cmap=cmap, vmin=50, vmax=100, origin="lower", aspect="auto")
    [ax.text(j, i, text, ha="center", va="center", fontsize=8, color=INK) for (i, j), text in zip(places, runs)]
    ax.set_xticks(range(len(res.levels)))
    ax.set_xticklabels([f"{d * 100:g}" for d in res.levels])
    ax.set_yticks(range(len(res.launches)))
    ax.set_yticklabels([f"{a * 100:g}" for a in res.launches])
    ax.set_xlabel("Distress (points)")
    ax.grid(False)
    [s.set_visible(False) for s in ax.spines.values()]
    tag(ax, f"Outside rate {pct(r)}")
    return image


def fig_stress_boundary(res, out):
    """Bridges served in years 4 and 5 for CPM, launch participation by distress, one panel per outside rate."""
    miss = Missing("fig_stress_boundary")
    # One hue light to dark, cut before the darkest greens so the dark grey counts stay readable on every cell.
    cmap = ListedColormap(plt.cm.Greens(np.linspace(0.05, 0.62, 256)))
    fig, axes = plt.subplots(1, len(res.rates), figsize=(WIDTH, 2.7), sharey=True, squeeze=False)
    images = [stress_panel(ax, res, r, cmap, miss) for ax, r in zip(axes[0], res.rates)]
    axes[0, 0].set_ylabel("Launch participation (%)")
    fig.tight_layout(w_pad=0.6)
    bar = fig.colorbar(images[-1], ax=axes[0].tolist(), fraction=0.03, pad=0.02, extend="min")
    bar.set_label("Bridges served, years 4 and 5 (%)")
    bar.outline.set_visible(False)
    fig.text(0.0, -0.02, f"Number in each cell: seeds with a pool run (bridges served below {RUN_LINE * 100:g}%).",
             fontsize=8, color=INK, ha="left", va="top")
    save(fig, out, "fig_stress_boundary")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 6: participation paths and the one-curve prediction
# ----------------------------------------------------------------------------------------------------------------------
def one_curve(launch, j0, j1, lambdas, months):
    """A(t+1) = A + (j0 + j1 A)(1 - A) - lambda A from A(0) = launch, for every lambda and launch level at once:
    a lambdas x launches x (months + 1) array. One loop over time, which a recursion needs."""
    path = np.empty((lambdas.size, launch.size, months + 1))
    path[:, :, 0] = launch[None, :]
    for t in range(months):
        a = path[:, :, t]
        path[:, :, t + 1] = a + (j0 + j1 * a) * (1 - a) - lambdas[:, None] * a
    return path


def first_reach(curve, level):
    """The time, interpolated between months, at which ``curve`` (month 0 first) first reaches ``level``; NaN
    when it never does."""
    above = np.nonzero(curve >= level)[0]
    if not above.size:
        return np.nan
    k = above[0]
    if k == 0:
        return 0.0
    return k - 1 + (level - curve[k - 1]) / (curve[k] - curve[k - 1])


def fig_participation(res, out, r=0.044):
    """CPM's participation paths from the launch levels with no distress at outside rate ``r`` (seed means), with
    the one-curve prediction (one fitted lambda), and the paths shifted in time onto the lowest one."""
    miss = Missing("fig_participation")
    j0, j1 = (number(dig(res.summary, ["inputs", k])) for k in ("xi0", "xi1"))
    blocks = [res.series("A", r, a, 0.0) for a in res.launches]
    launch = np.array(res.launches)
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.8), sharey=True)
    shades = plt.cm.Greens(np.linspace(0.35, 0.95, len(launch)))   # light for low launch, dark for high
    if not miss.check(np.array([np.nan if any(b is None for b in blocks) else 0.0]),
                      f"measures.json jobs[].monthly.{CPM}.A at outside rate {pct(r)}, no distress"):
        plt.close(fig)
        return miss.report()
    # Month 0 is the launch level; the stored series' index k is month k + 1.
    paths = np.array([np.concatenate([[a], np.nanmean(b, axis=0)]) for a, b in zip(launch, blocks)])
    months = np.arange(paths.shape[1])
    # Each seed's own path as a thin line behind the mean of its launch level.
    [axes[0].plot(months, np.column_stack([np.full(len(b), a), b]).T, color=c, lw=0.5, alpha=seed_alpha(len(b)),
                  zorder=1) for a, b, c in zip(launch, blocks, shades)]
    [axes[0].plot(months, p, color=c, lw=1.6) for p, c in zip(paths, shades)]
    if miss.check(np.array([j0, j1]), "summary.json inputs.xi0 and inputs.xi1"):
        model = one_curve(launch, j0, j1, LAMBDAS, months[-1])
        best = int(np.argmin(np.nansum((model - paths[None]) ** 2, axis=(1, 2))))
        [axes[0].plot(months, p, color=INK, lw=0.9, ls="--") for p in model[best]]
        print(f"fig_participation: fitted lambda {LAMBDAS[best]:.5f} a month (xi0 {j0}, xi1 {j1})")
        # The lowest path continued past its last month by the prediction, so higher launch levels can be placed.
        tail = one_curve(paths[0, -1:], j0, j1, LAMBDAS[best:best + 1], 600)[0, 0, 1:]
        reference = np.concatenate([paths[0], tail])
        axes[1].plot(np.arange(reference.size)[months.size - 1:], reference[months.size - 1:], color=INK, lw=0.9,
                     ls="--")
    else:
        reference = paths[0]
    shift = np.array([first_reach(reference, a) for a in launch])
    [axes[1].plot(months + s, p, color=c, lw=1.6) for p, c, s in zip(paths, shades, shift) if np.isfinite(s)]
    if not np.isfinite(shift).all():
        print(f"fig_participation: launch levels {launch[~np.isfinite(shift)].tolist()} never reached by the "
              "lowest path, not shifted")
    axes[0].set_ylabel("Participation (share of people)")
    axes[0].set_xlabel("Months since launch")
    axes[1].set_xlabel("Months since launch, shifted onto the lowest path")
    axes[1].set_xlim(0, np.nanmax(shift) + months[-1] + 2 if np.isfinite(shift).any() else None)
    axes[0].set_ylim(0, 1)
    tag(axes[0], f"(a) Paths, outside rate {pct(r)}, no distress")
    tag(axes[1], "(b) Paths shifted in time")
    fig.tight_layout(w_pad=1.0)
    fig.legend(handles=[Line2D([], [], color=c, lw=1.6, label=f"{a * 100:g}%") for a, c in zip(launch, shades)]
               + [Line2D([], [], color=INK, lw=0.9, ls="--", label="one-curve prediction")], loc="upper center",
               bbox_to_anchor=(0.5, 0.0), ncol=len(launch) + 1, title="Launch participation", title_fontsize=8,
               handlelength=1.8, columnspacing=1.0)
    save(fig, out, "fig_participation")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figures: the adoption rule, the sellers' network and the launch (docs/ROBUSTNESS_PLAN.md, sections 5 and 8)
# ----------------------------------------------------------------------------------------------------------------------
GROUP_TITLE = {"Uniform": "Uniform sellers", "Ring": "Sellers on a ring", "Hubs": "Hub sellers"}
ROBUST_RATE = 0.044                                    # the outside rate every robustness set runs at
COMMON_THRESHOLDS = (0.1, 0.2, 0.3)                    # the common thresholds the plan runs (section 5.2)
END = 60                                               # participation at month 60 after launch


def pending_or_result(folder):
    """The stored result of ``folder``, or None for a set not yet run (no summary.json there)."""
    folder = Path(folder)
    has = (folder / "summary.json").exists() or (folder / "summary.json.gz").exists()
    return Result(folder) if has else None


def threshold_values(res, count=400):
    """Equally likely joining thresholds that stand for a run's threshold rule in the mean-field path: None under the
    linear rule; ``count`` evenly spread values on 0 to 1 for uniform thresholds; the log-normal law's quantiles at
    the same places, with the stored log-mean and log-spread, for measured ones; the one number for a common
    threshold."""
    economy = dig(res.summary, ["economy"]) or {}
    if economy.get("joining") != "threshold":
        return None
    rule = economy.get("thresholds")
    middle = (np.arange(count) + 0.5) / count
    if rule == "uniform":
        return middle
    if rule == "measured":
        mean, spread = (number(dig(res.summary, ["constants", k])) for k in ("THRESHOLD_LOG_MEAN",
                                                                              "THRESHOLD_LOG_SPREAD"))
        return np.exp(mean + spread * np.array([NormalDist().inv_cdf(p) for p in middle]))
    return np.array([float(rule)])


def mean_field(launch, j0, j1, lambdas, months, thresholds):
    """The well-mixed path of participation when each person keeps its own joining threshold, from A(0) = launch, for
    every lambda and launch level at once: a lambdas x launches x (months + 1) array.

    A person outside joins in a month with chance j0, and with j0 + j1 once participation has reached its
    threshold; a member leaves with chance lambda. Because thresholds are kept, the people still outside are, as
    time passes, those with the higher thresholds, so the share outside is followed threshold by threshold
    (``thresholds`` are equally likely values) and A = 1 - the mean share outside. This is not
    A + (j0 + j1 F(A))(1 - A) - lambda A with F the thresholds' cumulative share: that formula holds only when a
    threshold is drawn afresh every month, and with uniform thresholds it is the base's one curve. Everyone meets
    the population's share here; in a run a person meets the share among its own partners, which differs from
    person to person."""
    outside = np.broadcast_to((1 - launch)[None, :, None], (lambdas.size, launch.size, thresholds.size)).copy()
    path = np.empty((lambdas.size, launch.size, months + 1))
    path[:, :, 0] = launch[None, :]
    for t in range(months):
        met = thresholds[None, None, :] <= path[:, :, t][:, :, None] + 1e-12
        outside = outside * (1 - j0 - j1 * met) + lambdas[:, None, None] * (1 - outside)
        path[:, :, t + 1] = 1 - outside.mean(axis=2)
    return path


def paths_panel(ax, res, label, shades, miss):
    """One variant: CPM's participation month by month from each launch level with no distress (each seed thin,
    the seed mean thick) and, under a threshold rule, the mean-field path with one leaving rate fitted, dashed."""
    # A long label is broken over two lines so it stays within its panel.
    ax.set_title(textwrap.fill(label, 34), loc="left", fontsize=8, color=INK)
    if res is None:
        ax.text(0.5, 0.5, "not yet run", transform=ax.transAxes, ha="center", va="center", color=SOFT, fontsize=8)
        return
    launch = np.array([a for a in res.launches if (ROBUST_RATE, a, 0.0) in res.cells], float)
    blocks = [res.series("A", ROBUST_RATE, a, 0.0) for a in launch]
    if not miss.check(np.array([np.nan if not blocks or any(b is None for b in blocks) else 0.0]),
                      f"measures.json jobs[].monthly.{CPM}.A ({res.folder.name})"):
        return
    paths = np.array([np.concatenate([[a], np.nanmean(b, axis=0)]) for a, b in zip(launch, blocks)])
    months = np.arange(paths.shape[1])
    for a, b, c in zip(launch, blocks, shades[-len(launch):]):
        ax.plot(months, np.column_stack([np.full(len(b), a), b]).T, color=c, lw=0.5, alpha=seed_alpha(len(b)),
                zorder=1)
    [ax.plot(months, p, color=c, lw=1.4) for p, c in zip(paths, shades[-len(launch):])]
    j0, j1 = (number(dig(res.summary, ["inputs", k])) for k in ("xi0", "xi1"))
    values = threshold_values(res)
    if values is not None and miss.check(np.array([j0, j1]), "summary.json inputs.xi0 and inputs.xi1"):
        model = mean_field(launch, j0, j1, LAMBDAS, months[-1], values)
        best = int(np.argmin(np.nansum((model - paths[None]) ** 2, axis=(1, 2))))
        [ax.plot(months, p, color=INK, lw=0.8, ls="--") for p in model[best]]
        print(f"fig_robust_paths: {res.folder.name}: fitted lambda {LAMBDAS[best]:.5f} a month")


def fig_robust_paths(robust, out):
    """Participation under CPM month by month in every robustness variant, one panel each, a column for each
    sellers' world (uniform, ring, hubs), lines by launch level, with the mean-field path dashed where a threshold
    rule is on. ``robust`` lists (group, label, Result or None)."""
    miss = Missing("fig_robust_paths")
    groups = [g for g in GROUP_TITLE if any(r[0] == g for r in robust)]
    columns = {g: [r for r in robust if r[0] == g] for g in groups}
    rows = max(map(len, columns.values()))
    fig, axes = plt.subplots(rows, len(groups), figsize=(WIDTH, 1.7 * rows + 0.6), sharex=True, sharey=True,
                             squeeze=False)
    launches = sorted(set(chain.from_iterable(res.launches for _, _, res in robust if res is not None)))
    shades = plt.cm.Greens(np.linspace(0.35, 0.95, max(len(launches), 1)))   # light for low launch, dark for high
    for (j, g), i in product(enumerate(groups), range(rows)):
        ax = axes[i, j]
        if i >= len(columns[g]):
            ax.set_axis_off()
            continue
        _, label, res = columns[g][i]
        paths_panel(ax, res, label, shades, miss)
        ax.set_ylim(0, 1)
        ax.set_xticks([0, 12, 24, 36, 48, 60])
        if i == len(columns[g]) - 1:
            ax.set_xlabel("Months since launch")
            ax.xaxis.set_tick_params(labelbottom=True)
    [ax.set_ylabel("Participation") for ax in axes[:, 0]]
    fig.tight_layout(h_pad=0.5, w_pad=0.8)
    for j, g in enumerate(groups):
        box = axes[0, j].get_position()
        fig.text((box.x0 + box.x1) / 2, box.y1 + 0.045, GROUP_TITLE[g], ha="center", va="bottom", fontsize=9,
                 color=INK, fontweight="bold")
    fig.legend(handles=[Line2D([], [], color=c, lw=1.4, label=f"{a * 100:g}%") for a, c in zip(launches, shades)]
               + [Line2D([], [], color=INK, lw=0.8, ls="--", label="mean-field path")], loc="upper center",
               bbox_to_anchor=(0.5, 0.0), ncol=len(launches) + 1, title="Launch participation", title_fontsize=8,
               handlelength=1.8, columnspacing=1.0)
    save(fig, out, "fig_robust_paths")
    miss.report()


def hand_boundary(theta, j0, months=END):
    """The plan's worked example (section 5.2): in a well-mixed population with no leaving, below a common threshold
    theta only innovation works, so participation reaches theta from a launch a0 in ln((1 - a0) / (1 - theta)) / j0
    months; it does so within ``months`` from a launch of at least 1 - (1 - theta) exp(months j0) (0 if lower)."""
    return max(0.0, 1 - (1 - theta) * np.exp(months * j0))


def fig_threshold_map(base, thresholds, out):
    """Participation at month 60 less the launch share, CPM, seed means, by launch share (columns) and common
    threshold (rows: none, the base, then each threshold), with the example's boundary marked in each threshold
    row. ``thresholds`` lists (theta, Result or None)."""
    miss = Missing("fig_threshold_map")
    rows = [("no threshold", None, base)] + [(f"{theta:g}", theta, res) for theta, res in thresholds]
    launches = sorted(a for a in base.launches if (ROBUST_RATE, a, 0.0) in base.cells)

    def rise(res, a):
        """Seed-mean participation at month 60 less the launch share in one cell (NaN where not stored)."""
        block = None if res is None else res.series("A", ROBUST_RATE, a, 0.0)
        return np.nan if block is None or block.shape[1] < END else float(np.nanmean(block[:, END - 1])) - a

    grid = np.array([[rise(res, a) for a in launches] for _, _, res in rows])
    miss.check(grid, f"measures.json jobs[].monthly.{CPM}.A[{END - 1}]")
    fig, ax = plt.subplots(figsize=(WIDTH, 2.4))
    top = np.nanmax(np.abs(grid)) if np.isfinite(grid).any() else 1.0
    # Two hues about a neutral middle: participation that falls below its launch share in brown, that rises in
    # blue-green, no change pale.
    # The darkest ends are cut, so the dark grey numbers stay readable on every cell.
    cmap = ListedColormap(plt.cm.BrBG(np.linspace(0.15, 0.85, 256)))
    image = ax.imshow(grid, cmap=cmap, vmin=-top, vmax=top, aspect="auto")
    for (i, j), value in np.ndenumerate(grid):
        ax.text(j, i, "" if not np.isfinite(value) else f"{value:+.2f}", ha="center", va="center", fontsize=8,
                color=INK)
    j0 = number(dig(base.summary, ["inputs", "xi0"]))
    places = np.arange(len(launches))
    for i, (_, theta, res) in enumerate(rows):
        if res is None and theta is not None:
            ax.text(len(launches) / 2 - 0.5, i, "not yet run", ha="center", va="center", fontsize=8, color=SOFT)
        if theta is None or not np.isfinite(j0):
            continue
        # The boundary's place on the launch axis, between the columns it falls between (left of the first column
        # when every launch level reaches the threshold).
        x = np.interp(hand_boundary(theta, j0), [0.0] + launches, [-0.5] + list(places))
        ax.plot([x, x], [i - 0.45, i + 0.45], color=INK, lw=1.6, solid_capstyle="butt")
    ax.set_xticks(places)
    ax.set_xticklabels([f"{a * 100:g}" for a in launches])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([name for name, _, _ in rows])
    ax.set_xlabel("Launch participation (%)")
    ax.set_ylabel("Common threshold")
    ax.grid(False)
    [s.set_visible(False) for s in ax.spines.values()]
    bar = fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    bar.set_label("Participation at month 60\nless the launch share")
    bar.outline.set_visible(False)
    fig.text(0.0, -0.1, "Black mark: the hand case. To its right, innovation alone carries participation to the "
             "threshold within 60 months (well mixed, no one leaving).", fontsize=8, color=INK, ha="left", va="top")
    save(fig, out, "fig_threshold_map")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure: how long money is held before it is spent
# ----------------------------------------------------------------------------------------------------------------------
def spell_panel(ax, res, r, a, miss):
    """(a) The share of value spent by holding time over years 4 and 5, CPM and the pool without the charge, at
    one cell with no distress (seed mean), as steps over the stored bins on a log scale, one line style an ordering.
    The last bin is open above its edge; it is drawn as far again (a doubling, like the other bins)."""
    if not miss.check(np.asarray(res.edges if res.edges else [], float), "measures.json jobs[].series."
                      f"{CPM}.holding_velocity.edges"):
        return
    edges = np.append(res.edges, 2 * res.edges[-1])
    shown = []
    # The pool without the charge is drawn wide and pale under CPM's narrow line, so both show where they coincide.
    for (arm, width, alpha), (conv, ls, _) in product((("U", 3.2, 0.55), (CPM, 1.3, 1.0)), ORDERINGS):
        shares = res.spent_shares(arm, conv, r, a, 0.0)
        what = (f"measures.json jobs[].series.{arm}.holding_velocity.{conv}.{CIRC_GROUP[arm]}.histogram at "
                f"{place_text(r, a)}")
        if miss.check(shares, what):
            ax.stairs(100 * shares, edges, color=ARM_COL[arm], ls=ls, lw=width, alpha=alpha)
            shown.append(shares)
    # The axis ends at the last bin any line uses, so empty bins of very long holding take no room; every other
    # edge is labelled, so the labels do not run together on the log scale.
    used = max((np.nonzero(s > 0)[0].max() for s in shown), default=edges.size - 2)
    ax.set_xscale("log")
    ax.set_xlim(edges[0], edges[used + 1])
    ticks = edges[:used + 2][::2]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks])
    ax.minorticks_off()
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Holding time (days, log scale)")
    ax.set_ylabel("Share of value spent (%)")


def place_text(r, a):
    """A cell with no distress in words, for the missing-field line."""
    return f"outside rate {pct(r)}, launch {pct(a)}, no distress"


def holding_lines(ax, res, r, miss):
    """(b) The mean holding time of money spent against launch participation at outside rate ``r``, no distress,
    for the four arrangements (seed mean), one line style an ordering, filled markers last in first out."""
    for arm, (conv, ls, _) in product(CIRC_ARMS, ORDERINGS):
        y = np.array([np.mean(v) if (v := res.holding(arm, conv, r, a, 0.0)).size else np.nan for a in res.launches])
        if miss.check(y, f"measures.json jobs[].series.{arm}.holding_velocity.{conv}.{CIRC_GROUP[arm]}.mean_tau"):
            ax.plot(res.launches, y, ls=ls, marker="o", ms=4, color=ARM_COL[arm],
                    mfc=ARM_COL[arm] if conv == "lifo" else "white")
    ax.set_ylabel("Mean holding time of money spent (days)")


def gap_lines(ax, res, miss):
    """(c) CPM's mean holding time of money spent less the pool's without the charge, the same seeds paired (seed
    mean of the differences), against launch participation, a line style and marker an outside rate; filled
    markers last in first out, open first in first out."""
    for r, (conv, _, _) in product(res.rates, ORDERINGS):
        pairs = [(res.holding(CPM, conv, r, a, 0.0), res.holding("U", conv, r, a, 0.0)) for a in res.launches]
        y = np.array([np.mean(c - u) if c.size and c.size == u.size else np.nan for c, u in pairs])
        ls, mk = RATE_STYLE.get(r, ("-", "o"))
        if miss.check(y, f"measures.json jobs[].series.<{CPM}|U>.holding_velocity.{conv}.participants.mean_tau"):
            ax.plot(res.launches, y, ls=ls, marker=mk, ms=4, color=ARM_COL[CPM],
                    mfc=ARM_COL[CPM] if conv == "lifo" else "white", lw=1.2 if conv == "lifo" else 0.9,
                    alpha=1.0 if conv == "lifo" else 0.7)
    ax.axhline(0, color=SOFT, lw=0.7)
    ax.set_ylabel("CPM less the pool without the charge (days)")


def fig_circulation(res, out, r=0.044, a=0.2):
    """How long money is held before it is spent, from the stored coin ages (years 4 and 5, no distress): (a) the
    distribution at one cell for CPM and the pool without the charge, (b) the mean against launch participation for
    the four arrangements at outside rate ``r``, (c) CPM less the pool without the charge by outside rate. Banks and
    cards are read for everyone, the others for their participants."""
    miss = Missing("fig_circulation")
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 5.0))
    (spell, level), (gap, key) = axes
    spell_panel(spell, res, r, a, miss)
    tag(spell, f"(a) Distribution, outside rate {pct(r)}, launch {pct(a)}")
    holding_lines(level, res, r, miss)
    launch_axis(level, res)
    tag(level, f"(b) Mean, outside rate {pct(r)}")
    gap_lines(gap, res, miss)
    launch_axis(gap, res)
    tag(gap, "(c) CPM less the pool without the charge")
    # The fourth place holds the legend and the reading's terms, clear of the panels.
    key.set_axis_off()
    orderings = [Line2D([], [], color=INK, ls=ls, marker="o", ms=4, mfc=INK if conv == "lifo" else "white",
                        label=f"{name} (filled markers)" if conv == "lifo" else f"{name} (open markers)")
                 for conv, ls, name in ORDERINGS]
    key.legend(handles=arm_handles(CIRC_ARMS) + orderings + [
        Line2D([], [], color=ARM_COL[CPM], ls=RATE_STYLE.get(q, ("-", "o"))[0], marker=RATE_STYLE.get(q, ("-", "o"))[1],
               ms=4, label=f"(c) outside rate {pct(q)}") for q in res.rates],
        loc="center left", fontsize=8, handlelength=2.6)
    fig.tight_layout(h_pad=1.2, w_pad=1.5)
    fig.text(0.0, -0.01, "Years 4 and 5 after launch, no distress, seed means; money is E, P and outside savings. Banks "
             "and cards: everyone; the others: their participants.", fontsize=8, color=INK, ha="left", va="top")
    save(fig, out, "fig_circulation")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 7: population size check
# ----------------------------------------------------------------------------------------------------------------------
def size_points(ax, sizes, path, r, a, d, dx, filled):
    """CPM's seed mean and 95% interval at ``path`` across the population sizes, one marker style."""
    found = [t_interval(res.seeds(path, r, a, d)) for res in sizes]
    n = np.array([res.n for res in sizes], float)
    mean, half = np.array(found).T
    ax.errorbar(n * dx, mean, yerr=half, fmt="o", color=ARM_COL[CPM], mfc=ARM_COL[CPM] if filled else "white",
                ms=5, capsize=2, lw=1.2, mew=1.1)
    return mean


def size_gain(ax, sizes, yard, r, a, miss):
    """One cell, one yardstick: CPM's complete gain at both ends of the bracket against population size."""
    for end, dx, filled in (("zero", 0.94, True), ("face", 1.06, False)):
        path = ["arms", CPM, "against", yard, "complete_gain", end, "gain_usd_a_year"]
        miss.check(size_points(ax, sizes, path, r, a, 0.0, dx, filled), "cells.json jobs[]." + ".".join(path))
    ax.axhline(MARGIN, color=INK, lw=0.7, ls=":")


def size_runs(ax, sizes, r, a, miss):
    """One cell: the number of seeds with a pool run at 2 points of distress against population size."""
    found = [served_seeds(res, r, a, HEADLINE) for res in sizes]
    runs = np.array([np.sum(v < RUN_LINE) if v.size else np.nan for v in found], float)
    if miss.check(runs, f"cells.json jobs[].{'.'.join(SERVED_SEED)} at {HEADLINE * 100:g} points"):
        ax.plot([res.n for res in sizes], runs, "o-", color=ARM_COL[CPM], ms=5)
    ax.set_ylim(-0.3, max(len(res.jobs.get((r, a, HEADLINE), [])) for res in sizes) + 0.3)


def fig_size_check(sizes, out):
    """For each size-check cell, CPM's gain over banks, best-case DeFi and the pool without the charge, and the
    seeds with a pool run at 2 points, against population size."""
    miss = Missing("fig_size_check")
    sizes = sorted(sizes, key=lambda res: res.n)
    # The (outside rate, launch) cells any size ran with no distress.
    cells = sorted({k[:2] for k in set().union(*[res.cells for res in sizes]) if k[2] == 0.0})
    rows = [("S0", "Gain over banks\nand cards (\\$ a year)"),
            ("M0", "Gain over DeFi (stablecoin\npayments) (\\$ a year)" if second_run_store(sizes[0].summary)
             else "Gain over best-case\nDeFi (\\$ a year)"),
            ("U", "Gain over the pool\nwithout the charge (\\$ a year)"),
            (None, f"Seeds with a pool run\nat {HEADLINE * 100:g} points")]
    fig, axes = plt.subplots(len(rows), len(cells), figsize=(WIDTH, 6.6), sharex=True, sharey="row", squeeze=False)
    for ax, ((yard, _), (r, a)) in zip(axes.flat, product(rows, cells)):
        size_gain(ax, sizes, yard, r, a, miss) if yard else size_runs(ax, sizes, r, a, miss)
        ax.axvline(4000, color=SOFT, lw=0.8, ls="--", zorder=1)   # above the grid, below the points
        ax.set_xscale("log")
        ax.set_xticks([res.n for res in sizes])
        ax.set_xticklabels([f"{res.n:,}" for res in sizes], rotation=45)
        ax.minorticks_off()
    [tag(ax, f"Outside rate {pct(r)}, launch {pct(a)}") for ax, (r, a) in zip(axes[0], cells)]
    [ax.set_ylabel(label) for ax, (_, label) in zip(axes[:, 0], rows)]
    [ax.set_xlabel("People (log scale)") for ax in axes[-1]]
    fig.tight_layout(h_pad=0.6, w_pad=0.6)
    bottom_legend(fig, [
        Line2D([], [], ls="", marker="o", color=ARM_COL[CPM], label="sellers' extra sales at zero"),
        Line2D([], [], ls="", marker="o", color=ARM_COL[CPM], mfc="white", label="at face value"),
        Line2D([], [], color=INK, lw=0.7, ls=":", label="-\\$2 margin"),
        Line2D([], [], color=SOFT, lw=0.8, ls="--", label="4,000 people, the map")], ncol=4)
    fig.text(0.5, -0.045, "Seed means with 95% intervals.", ha="center", va="top", fontsize=8)
    save(fig, out, "fig_size_check")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# Figure 8: who pays whom
# ----------------------------------------------------------------------------------------------------------------------
NODES = {"reserve": ("Issuer\nreserve", (0.0, 1.3)), "wallets": ("Wallets\n(P)", (0.0, 0.0)),
         "pool": ("Pool", (2.0, 0.0)), "borrowers": ("Borrowers", (4.0, 0.0))}
# Each flow: from, to, curvature (positive bends to the right of travel), arrow style, label, label place, alignment.
FLOWS = (("reserve", "wallets", 0.0, "<|-|>", "issue and redeem\n(one for one)", (-0.12, 0.65), "right"),
         ("wallets", "pool", -0.3, "<|-|>", "buy and sell shares\nat net asset value", (1.0, 0.47), "center"),
         ("wallets", "pool", 0.3, "-|>", "holding charge c", (1.0, -0.4), "center"),
         ("pool", "borrowers", -0.3, "-|>", "loans", (3.0, 0.38), "center"),
         ("borrowers", "pool", -0.3, "-|>", "repayments with interest", (3.0, -0.4), "center"))
NODE_SIZE = 2200                                     # node area in points squared


def fig_network(out):
    """A schematic of who pays whom in CPM: the issuer reserve, the wallets, the pool and the borrowers, with the
    flows between them labelled. A diagram of the rules, not of stored data."""
    graph = nx.MultiDiGraph()
    graph.add_nodes_from(NODES)
    pos = {k: xy for k, (_, xy) in NODES.items()}
    fig, ax = plt.subplots(figsize=(WIDTH, 2.9))
    nx.draw_networkx_nodes(graph, pos, ax=ax, node_size=NODE_SIZE, node_shape="s", node_color="#eef4ee",
                           edgecolors=ARM_COL[CPM], linewidths=1.3)
    # One drawing call per flow, so each keeps its own curvature (two flows join the wallets and the pool); the
    # margins keep each arrow head outside the square nodes.
    [nx.draw_networkx_edges(graph, pos, edgelist=[(u, v)], ax=ax, connectionstyle=f"arc3,rad={rad}", arrows=True,
                            arrowstyle=style, arrowsize=10, width=1.3, edge_color="#555555", node_size=NODE_SIZE,
                            node_shape="s", min_source_margin=4, min_target_margin=4)
     for u, v, rad, style, _, _, _ in FLOWS]
    nx.draw_networkx_labels(graph, pos, labels={k: lab for k, (lab, _) in NODES.items()}, ax=ax, font_size=8.5,
                            font_family="serif", font_color=INK)
    [ax.text(x, y, text, ha=align, va="center", fontsize=8, color=INK) for *_, text, (x, y), align in FLOWS]
    # Payments run between wallets: a loop on the left of the wallets node, drawn by hand so its label sits clear.
    ax.annotate("", xy=(-0.33, -0.12), xytext=(-0.33, 0.12), arrowprops=dict(
        arrowstyle="-|>", color="#555555", lw=1.3, connectionstyle="arc3,rad=1.4", shrinkA=0, shrinkB=0))
    ax.text(-0.72, 0.0, "payments\nbetween\nwallets", ha="right", va="center", fontsize=8, color=INK)
    ax.set_xlim(-1.35, 4.45)
    ax.set_ylim(-0.7, 1.65)
    ax.set_axis_off()
    save(fig, out, "fig_network")


# ----------------------------------------------------------------------------------------------------------------------
# Maps read beside the main one: the second entry rule and the rate cut
# ----------------------------------------------------------------------------------------------------------------------
def each_job(text):
    """The jobs of a compact store, decoded and handed over one at a time, so a reader that keeps little of each
    never holds the whole store."""
    opening = '"jobs":['
    place_, decoder = text.find(opening) + len(opening), json.JSONDecoder()
    while text[place_] != "]":
        found, place_ = decoder.raw_decode(text, place_)
        yield found
        place_ += text[place_] == ","


class Light:
    """A map read beside the main one: its summary and cells; with ``jobs`` each seed's CPM block of cells.json; with
    ``series`` those monthly series of CPM, read one job at a time. It answers ``seeds`` and ``series`` as a Result
    does."""

    def __init__(self, folder, jobs=False, series=()):
        self.folder = Path(folder)
        self.summary, self.cells = summary_cells(folder)
        own = bool(dig(self.summary, ["economy", "lender_income_recirculated"]) or False)
        same = lambda item: bool(item.get("recirculated")) == own
        self.jobs, self.monthly = {}, {}
        if jobs:
            kept = [dict(r_out=j["r_out"], a0=j["a0"], distress=j["distress"], seed=j["seed"],
                         arms={CPM: dig(j, ["arms", CPM])}) for j in json.loads(stored_text(folder, "cells.json"))["jobs"]
                    if same(j)]
            self.jobs = grouped(kept)
        if series:
            kept = [dict(r_out=j["r_out"], a0=j["a0"], distress=j["distress"], seed=j["seed"],
                         monthly={name: dig(j, ["monthly", CPM, name]) for name in series})
                    for j in each_job(stored_text(folder, "measures.json")) if same(j)]
            self.monthly = grouped(kept)
        self.rates, self.launches, self.levels = map(sorted, map(set, list(zip(*self.cells)) or [(), (), ()]))

    seeds, series = Result.seeds, Result.series


def light(folder, **wanted):
    """``Light`` of ``folder``, or None where no folder is given."""
    return None if folder is None else Light(folder, **wanted)


# ----------------------------------------------------------------------------------------------------------------------
# Where the gain comes from, cell by cell
# ----------------------------------------------------------------------------------------------------------------------
# CPM's gain in money over banks and cards by the flow it comes from (each cell's ``split``): legend text, the
# components added, colour. Sources of gain take hues, costs take greys.
SOURCE_PARTS = (("Reserve return on P", ("other_outside_flows",), "#0072B2"),
                ("Interest no longer paid outside", ("outside_interest_saved",), "#009E73"),
                ("Cash-advance, late and failure fees saved", ("advance_fees_saved", "late_fees_saved", "penalties_saved"),
                 "#56B4E9"),
                ("Card fees saved, less rewards", ("card_fees_saved", "card_rewards"), "#E69F00"),
                ("Pool's operating cost", ("pool_costs",), "#8c8c8c"),
                ("Savings income given up, inflation, valuation", ("savings_income", "inflation", "valuation"), "#b9b9b9"),
                ("Conversion fees, gas, wages to the outside",
                 ("conversion_fees_saved", "gas_to_validators", "wages_to_outside"), "#dedede"))


def fig_sources(res, out):
    """The gain over banks and cards by the flow it comes from, in every cell with no distress: dollars a person a
    year (top) and each flow as a share of the cell's gain (bottom), by launch participation at each outside rate.
    The flows add up to the gain in each cell, which the dot marks."""
    miss = Missing("fig_sources")
    months = number(dig(res.summary, ["economy", "months"]))
    fig, axes = plt.subplots(2, len(res.rates), figsize=(WIDTH, 4.5), sharex=True, sharey="row")
    axes = np.atleast_2d(axes)
    spots = np.arange(len(res.launches))

    def stacked(ax, values):
        """One panel's bars: each part of the gain stacked on the parts before it, a positive part upwards from the
        positive parts' top and a negative one downwards from the negative parts' bottom."""
        up, down = np.zeros(spots.size), np.zeros(spots.size)
        for (_, _, colour), level in zip(SOURCE_PARTS, values):
            base = np.where(level >= 0, up, down)
            ax.bar(spots, level, bottom=base, width=0.72, color=colour, edgecolor="white", linewidth=0.5, zorder=2)
            up, down = up + np.where(level >= 0, level, 0.0), down + np.where(level < 0, level, 0.0)

    def rate_column(col, r):
        """The two panels of one outside rate, the gain's parts in dollars and as shares of the gain; none where a
        part is not stored."""
        parts = np.array([[sum(number(dig(res.cells.get((r, a, 0.0)), [CPM, "split", name])) for name in names)
                           * 12 / months for a in res.launches] for _, names, _ in SOURCE_PARTS])
        if not miss.check(parts, f"summary.json cells[r_out {r:g}].{CPM}.split"):
            return
        total = parts.sum(axis=0)
        for row, values in enumerate((parts, 100 * parts / total)):
            ax = axes[row, col]
            stacked(ax, values)
            ax.plot(spots, total if row == 0 else np.full(spots.size, 100.0), ls="", marker="o", ms=3.2, color=INK,
                    zorder=4)
            ax.axhline(0, color="#888888", lw=0.6, zorder=1)
            ax.grid(axis="x", visible=False)
        tag(axes[0, col], f"Outside rate {pct(r)}")
        axes[1, col].set_xticks(spots)
        axes[1, col].set_xticklabels([f"{a * 100:g}" for a in res.launches])
        axes[1, col].set_xlabel("Launch participation (%)")

    for col, r in enumerate(res.rates):
        rate_column(col, r)
    axes[0, 0].set_ylabel("\\$ a person a year")
    axes[1, 0].set_ylabel("Share of the gain (%)")
    handles = [Patch(facecolor=colour, edgecolor="white", label=text) for text, _, colour in SOURCE_PARTS]
    handles.append(Line2D([], [], ls="", marker="o", ms=3.2, color=INK, label="Gain over banks and cards"))
    fig.tight_layout(h_pad=0.8, w_pad=0.6)
    bottom_legend(fig, handles, ncol=2, y=0.0)
    save(fig, out, "fig_sources")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# The pool month by month under the two entry rules
# ----------------------------------------------------------------------------------------------------------------------
RULES = (("Quote rule", "-", 1.0), ("Record rule", "--", 0.55))     # legend text, line, how strong the band


def fig_path(res, second, out, r=0.044):
    """Pool capital over its target and bridges served, month by month after launch, under the quote rule (the map)
    and the record rule (``second``), with no distress and at the stress headline: the median over the launch levels
    of each cell's seed mean, and the range over them, at outside rate ``r``."""
    miss = Missing("fig_path")
    maps = [res] + ([] if second is None else [second])
    levels = [d for d in (0.0, HEADLINE) if d in res.levels]
    fig, axes = plt.subplots(2, len(levels), figsize=(WIDTH, 3.9), sharex=True, sharey="row", squeeze=False)

    def paths(one, d, read):
        """Each launch level's seed-mean path of ``read`` at distress d: launches x months, or None."""
        found = []
        for a in one.launches:
            blocks = {name: one.series(name, r, a, d) for name in ("N", "Q", "bridges_drawn_over_wanted")}
            if any(block is None for block in blocks.values()):
                return None
            found.append(np.nanmean(read(blocks), axis=0))
        return np.array(found) if found else None

    ratio = lambda b: np.divide(b["N"], b["Q"], out=np.full(b["N"].shape, np.nan), where=b["Q"] > 0)
    served = lambda b: b["bridges_drawn_over_wanted"]
    def bands(ax, d, read):
        """One panel's band and median line for each entry rule's map, at distress ``d``, of the reading ``read``."""
        for one, (_, line, strength) in zip(maps, RULES):
            block = paths(one, d, read)
            if not miss.check(block, f"measures.json monthly N, Q and bridges_drawn_over_wanted, {one.folder.name}"):
                continue
            month = np.arange(1, block.shape[1] + 1)
            ax.fill_between(month, np.nanmin(block, axis=0), np.nanmax(block, axis=0), color=ARM_COL[CPM],
                            alpha=0.16 * strength, lw=0, zorder=1)
            ax.plot(month, np.nanmedian(block, axis=0), ls=line, color=ARM_COL[CPM], lw=1.6, zorder=3)

    for (col, d), (row, read) in product(enumerate(levels), enumerate((ratio, served))):
        ax = axes[row, col]
        bands(ax, d, read)
        if d > 0:
            ax.axvspan(24.5, 36.5, color="#000000", alpha=0.06, lw=0, zorder=0)
        if row == 0:
            ax.axhline(1.0, color="#888888", lw=0.6, zorder=1)
            tag(ax, "No distress" if d == 0 else f"{d * 100:g} points of distress, months 25 to 36 shaded")
        else:
            ax.set_xlabel("Months after launch")
        ax.set_xlim(1, 60)
        ax.set_xticks(range(12, 61, 12))
    axes[0, 0].set_ylabel("Capital over its target")
    axes[1, 0].set_ylabel("Bridges served")
    handles = [Line2D([], [], color=ARM_COL[CPM], ls=line, lw=1.6, label=text) for (text, line, _), _ in zip(RULES, maps)]
    handles.append(Patch(facecolor=ARM_COL[CPM], alpha=0.16, label="range over launch levels"))
    fig.tight_layout(h_pad=0.8, w_pad=0.8)
    bottom_legend(fig, handles, ncol=3, y=0.0)
    save(fig, out, "fig_path")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# What demurrage adds, cell by cell, with its interval across seeds
# ----------------------------------------------------------------------------------------------------------------------
RATE_COL = {0.02: "#a6dba0", 0.044: "#5aae61", 0.06: "#00441b"}     # one hue, light to dark with the outside rate


def fig_charge_gain(res, second, out):
    """CPM's gain in money over the pool without the charge in every cell, the mean across seeds with its 95%
    interval, by distress level, under the quote rule (the map) and the record rule (``second``). Within a level the
    cells run by outside rate and then by launch participation."""
    miss = Missing("fig_charge_gain")
    maps = [("Quote rule", res)] + ([] if second is None else [("Record rule", second)])
    path = ["arms", CPM, "against", "U", "gain_usd_a_year"]
    fig, axes = plt.subplots(len(maps), 1, figsize=(WIDTH, 2.25 * len(maps) + 0.55), sharex=True, squeeze=False)
    width = 0.84

    def intervals(ax, one):
        """One map's intervals: at each distress level, one for each cell run, by outside rate and then launch."""
        cells = list(product(one.rates, one.launches))
        for (k, d), (j, (r, a)) in product(enumerate(one.levels), enumerate(cells)):
            values = one.seeds(path, r, a, d)
            if not miss.check(values, f"cells.json jobs[].{'.'.join(path)}, {one.folder.name}"):
                continue
            mean, half = t_interval(values)
            x = k + (j + 0.5) / len(cells) * width - width / 2
            colour = RATE_COL.get(r, SOFT)
            ax.plot([x, x], [mean - half, mean + half], color=colour, lw=0.9, zorder=2)
            ax.plot([x], [mean], ls="", marker="o", ms=2.3, color=colour, zorder=3)

    for ax, (text, one) in zip(axes[:, 0], maps):
        intervals(ax, one)
        ax.axhline(0, color=INK, lw=0.7, zorder=1)
        ax.set_ylabel("\\$ a person a year")
        ax.grid(axis="x", visible=False)
        tag(ax, text)
    last = axes[-1, 0]
    last.set_xticks(range(len(res.levels)))
    last.set_xticklabels([f"{d * 100:g}" for d in res.levels])
    last.set_xlabel("Distress (points)")
    handles = [Line2D([], [], color=RATE_COL.get(r, SOFT), marker="o", ms=3, lw=0.9, label=f"outside rate {pct(r)}")
               for r in res.rates]
    fig.tight_layout(h_pad=0.7)
    bottom_legend(fig, handles, ncol=len(handles), y=0.0)
    save(fig, out, "fig_charge_gain")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# The edge at low outside rates
# ----------------------------------------------------------------------------------------------------------------------
# The two vehicle-loan tiers on which the pool's term coupon and the outside lender's rate change sides within the
# rates run: legend text, the place in each stored ``outside_rates`` entry's ``vehicle``, line.
CROSSING_LOANS = (("new car, scores 661 to 780", (0, 3), "-"), ("used car, scores 781 and above", (1, 4), "--"))


def class_mean(record, name):
    """One by-class record of a cell averaged over people (the classes weighted by their sizes); NaN if absent."""
    values, sizes = dig(record, [name]), dig(record, ["class_sizes"])
    if values is None or sizes is None:
        return np.nan
    values, sizes = np.array([number(v) for v in values]), np.array([number(s) for s in sizes])
    seen = np.isfinite(values) & (sizes > 0)
    return float((values[seen] * sizes[seen]).sum() / sizes[seen].sum()) if seen.any() else np.nan


def fig_low_rates(res, cut, out):
    """Why the claim is weakest at low outside rates, across the map's rates and the rate cut's, with no distress:
    (a) the pool's term coupon less the outside lender's rate on two tiers of vehicle loan (the pool lends such a
    loan where the difference is not above zero); (b) what the pool lends in term loans, as an index with the
    stress table's rate at 100; (c) the bridges it serves. In (b) and (c) a thin line is one launch level and the
    thick line their median. Hollow markers are the rate cut."""
    miss = Missing("fig_low_rates")
    maps = [res] + ([] if cut is None else [cut])
    owner = {}
    for one in reversed(maps):                         # the map last, so a rate both ran is read on it
        owner.update(dict.fromkeys(one.rates, one))
    rates = sorted(owner)
    x = np.array(rates) * 100
    hollow = np.array([owner[r] is not res for r in rates])
    fig, axes = plt.subplots(1, 3, figsize=(WIDTH, 2.75))

    def marked(ax, values, colour, line="-", label=None):
        """A line over the rates with filled markers for the map and hollow ones for the cut."""
        ax.plot(x, values, ls=line, color=colour, lw=1.4, zorder=3, label=label)
        ax.plot(x[~hollow], values[~hollow], ls="", marker="o", ms=4, color=colour, zorder=4)
        ax.plot(x[hollow], values[hollow], ls="", marker="o", ms=4, mfc="white", mec=colour, mew=1.0, zorder=4)

    coupon = []
    for r in rates:
        one = owner[r]
        found = [one.seeds(["arms", CPM, "r_term_pct"], r, a, 0.0) for a in one.launches]
        coupon.append(np.nanmedian([v.mean() for v in found if v.size]) if any(v.size for v in found) else np.nan)
    coupon = np.array(coupon)
    miss.check(coupon, f"cells.json jobs[].arms.{CPM}.r_term_pct")
    axes[0].axhspan(-10, 0, color=ARM_COL[CPM], alpha=0.08, lw=0, zorder=0)
    axes[0].axhline(0, color=INK, lw=0.7, zorder=1)
    for (text, (kind, tier), line), colour in zip(CROSSING_LOANS, (ARM_COL[CPM], SOFT)):
        stored = chain.from_iterable(dig(one.summary, ["outside_rates"]) or [] for one in maps)
        listed = {round(float(row["r_out"]), 6): row for row in stored}
        values = np.array([100 * number(dig(listed.get(round(r, 6)), ["vehicle", kind, tier])) for r in rates])
        if miss.check(values, "summary.json outside_rates[].vehicle"):
            marked(axes[0], coupon - values, colour, line, label=text)
    axes[0].set_ylim(-0.45, 1.0)
    axes[0].text(0.97, 0.04, "pool is the cheaper lender", transform=axes[0].transAxes, ha="right", va="bottom",
                 fontsize=7, color=ARM_COL[CPM])
    axes[0].set_ylabel("coupon less outside rate (points)")
    axes[0].legend(loc="upper left", fontsize=6.4, handlelength=2.0, borderaxespad=0.2)
    tag(axes[0], "(a) Coupon against outside lender")

    def lines(ax, read, text, index=False):
        """One quantity over the rates: a thin line for each launch level and the median over them, thick; with
        ``index`` each launch level is set to 100 at the stress table's outside rate."""
        block = np.array([[read(owner[r].cells.get((r, a, 0.0))) for a in owner[r].launches] for r in rates])
        if not miss.check(block, text):
            return
        if index:
            at = int(np.argmin(np.abs(np.array(rates) - 0.044)))
            block = 100 * block / block[at]
        [ax.plot(x, column, color=ARM_COL[CPM], lw=0.6, alpha=0.45, zorder=2) for column in block.T]
        marked(ax, np.nanmedian(block, axis=1), ARM_COL[CPM])

    lines(axes[1], lambda cell: class_mean(dig(cell, [CPM, "by_class"]), "term_pool"),
          f"summary.json cells[].{CPM}.by_class.term_pool", index=True)
    axes[1].set_ylabel("index, 4.4% = 100")
    tag(axes[1], "(b) Pool's term lending")
    lines(axes[2], lambda cell: number(dig(cell, [CPM, "bridges_drawn_over_wanted"])),
          f"summary.json cells[].{CPM}.bridges_drawn_over_wanted")
    axes[2].set_ylabel("share of bridges asked")
    tag(axes[2], "(c) Bridges served")
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels([f"{v:g}" for v in x], fontsize=7)
        ax.set_xlabel("Outside rate (%)")
    fig.tight_layout(w_pad=0.9)
    save(fig, out, "fig_low_rates")
    miss.report()


# ----------------------------------------------------------------------------------------------------------------------
# The wage network of one population draw
# ----------------------------------------------------------------------------------------------------------------------
NO_CARD = ARM_COL["U"]                                 # people without a card stand out against the card holders


def fig_wage_network(folder, out):
    """Who pays a wage to whom in one population draw (scripts/population_network.py): each person pays one wage to
    one other person, so the network is a set of long chains and branches along which a failed wage passes on. A
    node's area follows the person's spending; the people without a card are picked out."""
    record = json.loads(stored_text(folder, "network.json"))
    n, to = int(record["n"]), np.array(record["wage_to"], int)
    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    graph.add_edges_from(zip(range(n), to.tolist()))
    # A force layout with a fixed seed, so the same population gives the same picture.
    pos = nx.spring_layout(graph, k=0.9 / np.sqrt(n), iterations=80, seed=7)
    xy = np.array([pos[k] for k in range(n)])
    holder = np.array(record["holder"], bool)
    size = 1.0 + 4.5 * np.array(record["spending"], float)
    fig, ax = plt.subplots(figsize=(0.8 * WIDTH, 0.8 * WIDTH))
    ax.add_collection(LineCollection(np.stack([xy, xy[to]], axis=1), colors="#9a9a9a", linewidths=0.22, alpha=0.75,
                                     zorder=1))
    ax.scatter(xy[holder, 0], xy[holder, 1], s=size[holder], color=ARM_COL[CPM], alpha=0.75, lw=0, zorder=2)
    ax.scatter(xy[~holder, 0], xy[~holder, 1], s=size[~holder], color=NO_CARD, alpha=0.95, lw=0, zorder=3)
    ax.set_aspect("equal")
    ax.set_axis_off()
    handles = [Line2D([], [], ls="", marker="o", ms=4, color=ARM_COL[CPM], alpha=0.75, label="holds a card"),
               Line2D([], [], ls="", marker="o", ms=4, color=NO_CARD, label="holds no card"),
               Line2D([], [], color="#9a9a9a", lw=0.8, label="pays a wage to")]
    fig.tight_layout()
    bottom_legend(fig, handles, ncol=3, y=0.02)
    save(fig, out, "fig_wage_network")


# ----------------------------------------------------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------------------------------------------------
def side_pair(text):
    """A --side argument name=folder as (name, folder)."""
    name, sep, folder = text.partition("=")
    if not sep or not name or not folder:
        raise argparse.ArgumentTypeError(f"--side takes name=<folder>, got {text!r}")
    return name, Path(folder)


def main(argv=None):
    """Read the map (and any size-check, side and robustness results) and draw the figures into --out."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", required=True, type=Path, help="the results folder of the map")
    parser.add_argument("--sizes", nargs="*", type=Path, default=[], help="the population size-check folders")
    parser.add_argument("--side", type=side_pair, action="append", default=[], help="a side result, name=<folder>")
    parser.add_argument("--robust", nargs=4, action="append", default=[], metavar=("GROUP", "STEM", "LABEL", "FOLDER"),
                        help="a robustness variant: its group (the sellers), macro stem, label and folder, the base "
                             "first; a folder not yet written is drawn as not yet run")
    parser.add_argument("--cut", type=Path, help="the rate cut, whose cells join the map's in the figure of the grid")
    parser.add_argument("--second", type=Path, help="the same map under the record rule for entry")
    parser.add_argument("--network", type=Path, help="the stored wage network of one population draw")
    parser.add_argument("--out", type=Path, default=Path("paper/figures"), help="where the figures go")
    parser.add_argument("--reading", choices=("registered", "majority"), default="registered",
                        help="how the region figure reads a cell: the registered claim, or a majority of seeds "
                             "(for a development map, whose seeds are too few for the interval on their share)")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    res = Result(args.map)
    res.reading = args.reading                           # read by the region figure only
    # M0's name in the legends: DeFi (stablecoin payments) for a map of the second run, its first-run name otherwise.
    ARM_LAB["M0"] = defi_named("Best-case DeFi", res.summary)
    print(f"map {args.map}: {len(res.cells)} cells, {sum(map(len, res.jobs.values()))} seed runs, {res.n} people")
    [print(f"side {name} ({folder}): read by no figure in this set") for name, folder in args.side]
    [f(res, args.out) for f in (fig_failed_payments, fig_gains, fig_charge, fig_region, fig_stress_boundary,
                                fig_participation, fig_circulation)]
    fig_grid(res, summary_cells(args.cut), args.out)
    fig_sources(res, args.out)
    second = light(args.second, jobs=True, series=("N", "Q", "bridges_drawn_over_wanted"))
    fig_path(res, second, args.out)
    fig_charge_gain(res, second, args.out)
    fig_low_rates(res, light(args.cut, jobs=True), args.out)
    if args.sizes:
        fig_size_check([Result(folder) for folder in args.sizes], args.out)
    else:
        print("fig_size_check: no --sizes given, not drawn")
    if args.robust:
        # A folder named twice (the map is the base) is read once.
        read = {args.map.resolve(): res}

        def get(folder):
            """The result of ``folder``, read once; None for a set not yet run."""
            place = Path(folder).resolve()
            if place not in read:
                read[place] = pending_or_result(folder)
            return read[place]

        robust = [(group, label, get(folder)) for group, _, label, folder in args.robust]
        fig_robust_paths(robust, args.out)
        # The threshold map: the base, then each common threshold with uniform sellers, in order of the threshold.
        common = sorted((float(dig(r.summary, ["economy", "thresholds"])), r) for g, _, r in robust[1:]
                        if r is not None and g == "Uniform" and isinstance(dig(r.summary, ["economy", "thresholds"]),
                                                                           (int, float)))
        named = {round(theta, 6) for theta, _ in common}
        waiting = [(theta, None) for theta in COMMON_THRESHOLDS if round(theta, 6) not in named]
        fig_threshold_map(robust[0][2], sorted(common + waiting, key=lambda item: item[0]), args.out)
    fig_network(args.out)
    if args.network is not None:
        fig_wage_network(args.network, args.out)


if __name__ == "__main__":
    main()

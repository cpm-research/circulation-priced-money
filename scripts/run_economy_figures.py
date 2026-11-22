"""One arm of the economy and its S0 pair: persistence tests, falsifiers, verdict and figures.

What it does
------------
Runs ``simulate`` for the chosen arm (M0, U, M1 or M2) and for S0 on the
same random numbers, then writes into a new output directory:

* ``dynamics.png``      twelve panels of monthly dynamics, arm against S0;
* ``distribution.png``  Lorenz curves and gains by wealth decile, billing
                        cycle and role;
* ``network.png``       settled payments among 120 sampled people at launch
                        and in the final month;
* ``summary.json``      the Inputs fields the engine reads and its
                        module-level constants, provenance (source
                        hashes, the Comet pin's block, versions, git
                        commit), W2 means, the five persistence tests,
                        the six falsifiers, the verdict, gains by
                        role and fee channels.

Usage (from the repository root)
--------------------------------
    python -X utf8 scripts/run_economy_figures.py --output results/<name> --n 100 --arm M2
    python -X utf8 scripts/run_economy_figures.py --output results/<name> --n 100 --arm M0 --crypto-share 1

N = 100 is the development size. At N = 1,000 a run is a
population run and is made only by a deliberate decision. The output
directory must not exist (results are never overwritten).
"""
import argparse
import hashlib
import platform
import subprocess
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpm_abm import economy_abm  # noqa: E402
from cpm_abm.comet import load_pin  # noqa: E402
from cpm_abm.core_model import Inputs  # noqa: E402
from cpm_abm.economy_abm import (BACKING_TOLERANCE, CRYPTO_SHARE, CYCLE_DAYS, EPS, MARGIN_PARTS,  # noqa: E402
                                 STAY_MONTHS, Economy, ROUTE_CARD, ROUTE_E, ROUTE_P, gini, simulate)

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, ORANGE, AQUA, YELLOW, VIOLET, RED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#7b5ea7", "#c2410c"
DOLLARS = 6440.0          # one month of mean spending, BLS CEX 2023
COMET_DATA = "data/raw/compound_usdc_20261017"   # the Comet pin's files, which comet.py reads
YEAR = 1200.0             # monthly rate to %/yr
HELD_CAPITAL_LABEL = "about 1 at the capital limit by construction"


# The pool's fixed cost is sourced (decided 5 Nov; it replaces the core model's placeholder of 5e-5 a capita a
# month, "unknown; swept" since 26 Oct). A lending pool's operating cost is fixed in total, so a US-scale pool's is a
# large lending protocol's paid service providers in 2025 over the US consumer units: central, Aave, $24.15m a year
# (insights.aave.com dashboard, TokenLogic data; TokenLogic, Aave DAO Funding Insights, 28 Feb 2026); low, Compound,
# $13.1m (Compound Foundation Financial Update, 21 Feb 2026); high, Sky, $67m (Sky Frontier Foundation Q4 2025 update);
# over 134.556m consumer units, the count of the survey year the model's dollar unit comes from (BLS Consumer
# Expenditure Survey 2023, Table A; ``economy_abm.CONSUMER_UNITS`` and ``MONTH_USD``, so one year throughout, source
# audit of 13 Nov; the 2024 survey counts 135.76m and the 2025 survey 137.99m): $0.18, $0.10 and $0.50 a
# consumer unit a year. Per-loan servicing stays in the coupon's operating cost o. Unit check: one model person stands
# for one consumer unit and one unit of money is a month of mean spending, $6,440 (``economy_abm.MONTH_USD``), so C_fix,
# a person a month, is $ a year / 134.556m / 12 / 6,440: the central $0.1795 is 2.322e-6, against the old 5e-5, which
# is 5e-5 x 6,440 x 12 = $3.86 a consumer unit a year, 21.5 times it.
FIXED_COST_USD = dict(low=13.1e6, central=24.15e6, high=67.0e6)
FIXED_COST_UNITS = economy_abm.CONSUMER_UNITS
FIXED_COST = {level: usd / FIXED_COST_UNITS / 12 / economy_abm.MONTH_USD for level, usd in FIXED_COST_USD.items()}
# Multiples of the central fixed cost (decided 18 Nov 2026), for the exploratory side check of the fixed-cost
# spiral: the same sourced bill carried by a tenth, a hundredth and a thousandth as many consumer units.
FIXED_COST_TIMES = dict(times10=10, times100=100, times1000=1000)
FIXED_COST.update({level: FIXED_COST["central"] * times for level, times in FIXED_COST_TIMES.items()})


def engine_inputs(fixed_cost="central", **changes):
    """The core model's Inputs every runner's cells run at: no provider fee (decided 5 Nov: P payments run on
    stablecoin rails, so a P payment costs its payer one transfer's gas and nothing else; the engine reads no provider
    fee, and the core model's alpha, its own default 0.2%, is set to zero so that nothing a run stores carries one) and
    the sourced fixed cost C_fix at ``fixed_cost`` ("central", "low" or "high", ``FIXED_COST``; decided 5 Nov), with
    ``changes`` (r_out as ``rho_H``) on top. The population, figures and stress runners build their inputs here."""
    return replace(Inputs(), **dict(dict(alpha=0.0, C_fix=FIXED_COST[fixed_cost]), **changes))


# The core model's Inputs fields the engine reads (the 3 Nov review). A run stores these and no other field. The core
# model's other defaults, among them its 3.7% inflation, 5% penalty, no card rewards and monthly shocks, are not what
# the engine uses: its inflation and shocks are the Economy's, its failure fee and rewards its own constants. A test
# checks the list against the engine's source.
# Gas per payment (5 Nov) is the engine's own sourced constant, so gas_per_unit is no longer read; M0's collateral is
# a draw of holders with full cover (``Economy.crypto_share``, the 5 Nov review), so collateral_cover is no longer read;
# the leaving rule reads the core model's logistic noise (4 Nov); P payments run on stablecoin rails (5 Nov), so the
# provider fee alpha is no longer read.
ENGINE_INPUTS = ("rho_H", "r_ext", "f_card", "card_share", "housing", "buffer_yield", "o", "C_fix", "xi0",
                 "xi1", "upsilon", "noise", "supply_premium", "borrow_margin")
# Engine constants that name things rather than set a number a run uses: payment routes, obligation and loan kinds,
# the no-date sentinel and the numerical zero.
CODES = ("ROUTE_E", "ROUTE_CARD", "ROUTE_P", "SERVICE", "WAGE", "SHOCK", "LATE_WAGE", "OUTSIDE_WAGE",
         "LATE_OUTSIDE_WAGE", "BRIDGE", "TERM", "REVOLVE", "OVERDRAFT", "FEE_DEBT", "CASH_ADVANCE", "CHARGED_OFF", "BIG",
         "EPS")


def provenance(script):
    """Identify the exact code and environment behind a result: source hashes, the Comet pin's block, versions and the
    git commit.

    Each file is hashed with CRLF read as LF, as git stores it (``.gitattributes``: eol=lf), so a hash is the hash of
    the file as committed (``git show <commit>:<path>``) whatever line endings the working copy has (the 3 Nov
    review). comet.py is hashed too: M0's rates come from it and its pin. The pin's own files are named by the hash of
    the manifest load_pin checks them against, taken on raw bytes (data/raw is stored as binary), and a change to them
    counts as an uncommitted change.
    """
    # The engine is a package (16 Nov 2026): every one of its modules is hashed, with the module that re-exports them.
    engine = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "src" / "cpm_abm" / "engine").glob("*.py"))
    # The population runner is a package too (16 Nov 2026): every module of the experiment is hashed beside it.
    experiment = sorted(path.relative_to(ROOT).as_posix()
                        for path in (ROOT / "src" / "cpm_abm" / "experiment").glob("*.py"))
    files = ("src/cpm_abm/economy_abm.py", *engine, "src/cpm_abm/core_model.py", "src/cpm_abm/comet.py",
             "scripts/run_economy_figures.py", *experiment, script)
    digest = lambda path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    try:
        # The block of the Compound III snapshot M0 reads, from the local files load_pin checks against their saved
        # byte hashes (no network).
        block = load_pin().block
    except (OSError, ValueError, KeyError):
        block = None
    manifest = ROOT / COMET_DATA / "sha256_manifest.json"
    pin_manifest = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None
    try:
        commit = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, timeout=10).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "-c", "safe.directory=*", "status", "--porcelain", "--", "src", "scripts",
                                     COMET_DATA], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    return dict(sources={path: digest(path) for path in dict.fromkeys(files)}, comet_pin_block=block,
                comet_pin_manifest=pin_manifest,
                git_commit=commit, uncommitted_source_changes=dirty, python=platform.python_version(),
                numpy=np.__version__, matplotlib=matplotlib.__version__)


def engine_record(inputs):
    """The Inputs fields the engine reads and its module-level constants (the 3 Nov review): the fields at the values
    given, in the units Inputs declares, and the engine's own sourced and declared constants ($27 a failed payment,
    0.75% card rewards, the conversion fee, the real cost rates and the rest), each as defined in economy_abm.py, in
    the units its source comment gives (the record says so beside them). Numbers written inside the engine's functions
    (the pay frequencies, the business split, the statement day, the 0.9 owners' factor of the as-built coverage
    test, which the own margin replaced on 3 Nov) and the Comet pin's values
    are not stored here: the source hash and the git commit fix them (provenance names the pin's block). The Economy
    is stored beside it.
    """
    number = lambda value: isinstance(value, (int, float, np.number, np.ndarray)) and not isinstance(value, bool)
    constants = {name: np.asarray(value).tolist() for name, value in vars(economy_abm).items()
                 if name.isupper() and name not in CODES and number(value)}
    return dict(inputs={name: getattr(inputs, name) for name in ENGINE_INPUTS}, constants=constants,
                constants_units="each constant is stored as defined in src/cpm_abm/economy_abm.py, in the units its "
                                "source comment gives")


def style(axis, title, xlabel="", ylabel=""):
    """Recessive grid and axes, text-ink labels."""
    axis.set_title(title, color=INK, fontsize=10, loc="left")
    axis.set_xlabel(xlabel, color=MUTED, fontsize=8)
    axis.set_ylabel(ylabel, color=MUTED, fontsize=8)
    axis.tick_params(colors=MUTED, labelsize=7)
    axis.grid(color=GRID, linewidth=0.6)
    list(map(lambda side: axis.spines[side].set_visible(False), ("top", "right")))
    list(map(lambda side: axis.spines[side].set_color(GRID), ("left", "bottom")))


def months_axis(run):
    """Month numbers relative to launch (negative during the S0 burn-in)."""
    economy = run["economy"]
    return np.arange(economy.burn_in + economy.months) - economy.burn_in


# --------------------------------------------------------------------------------------------------------------------
# The settled evaluation: windows, persistence tests, falsifiers and verdict
# --------------------------------------------------------------------------------------------------------------------
def windows(run):
    """Evaluation windows as slices of the monthly series: W1 = months 13-36 and W2 = months 37-60 after launch."""
    start = run["economy"].burn_in
    return slice(start + 12, start + 36), slice(start + 36, start + 60)


# --------------------------------------------------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------------------------------------------------
def network_figure(m1, output):
    """Payment network of a fixed sample at launch and in the final month, nodes on a circle by wealth rank."""
    economy = m1["economy"]
    rng = np.random.default_rng(5)
    sample = np.sort(rng.choice(economy.n, size=min(120, economy.n), replace=False))
    months = (economy.burn_in, economy.burn_in + economy.months - 1)
    figure, axes = plt.subplots(1, 2, figsize=(12, 6.2))
    colours = {ROUTE_P: BLUE, ROUTE_CARD: YELLOW, ROUTE_E: MUTED}
    names = {ROUTE_P: "P (internal)", ROUTE_CARD: "card (E)", ROUTE_E: "E transfer"}

    def panel(item):
        """Draw one month's settled payments within the sample."""
        axis, month = item
        log = m1["payments"][month]
        wealth = m1["wealth"][month + 1]
        order = sample[np.argsort(wealth[sample])]
        angle = 2 * np.pi * np.arange(order.size) / order.size
        position = {int(node): (np.cos(a), np.sin(a)) for node, a in zip(order, angle)}
        inside = np.isin(log[0], sample) & np.isin(log[1], sample) & (log[2] > 0)
        graph = nx.MultiDiGraph()
        graph.add_nodes_from(map(int, sample))
        edges = log[:, inside]
        list(map(lambda route: nx.draw_networkx_edges(
            graph, position, ax=axis, edgelist=list(zip(edges[0][edges[3] == route].astype(int),
                                                       edges[1][edges[3] == route].astype(int))),
            edge_color=colours[route], width=0.3 + 3 * edges[2][edges[3] == route], alpha=0.5, arrows=False),
            (ROUTE_E, ROUTE_CARD, ROUTE_P)))
        participant = m1["participant"][month][sample]
        size = 8 + 220 * np.sqrt(np.maximum(wealth[sample], 0.0) / max(wealth.max(), 1e-12))
        nx.draw_networkx_nodes(graph, position, ax=axis, nodelist=list(map(int, sample)), node_size=size,
                               node_color=np.where(participant, BLUE, "#c3c2b7"), edgecolors=SURFACE, linewidths=0.6)
        axis.set_title(f"Month {month - economy.burn_in} after launch: {participant.mean():.0%} of the sample in P",
                       color=INK, fontsize=10, loc="left")
        axis.set_axis_off()

    list(map(panel, zip(axes, months)))
    handles = [matplotlib.lines.Line2D([], [], color=colours[r], linewidth=2, label=names[r]) for r in (ROUTE_P, ROUTE_CARD, ROUTE_E)]
    handles += [matplotlib.lines.Line2D([], [], marker="o", linestyle="", color=BLUE, label="participant"),
                matplotlib.lines.Line2D([], [], marker="o", linestyle="", color="#c3c2b7", label="non-participant")]
    figure.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=8)
    figure.suptitle("Settled payments among 120 sampled people (circle ordered by net wealth; node area ~ wealth; "
                    "edge width ~ amount)", color=INK, fontsize=11, x=0.01, ha="left")
    figure.savefig(output / "network.png", dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)


def series_figure(m1, s0, inputs, output):
    """Small multiples of the dynamics, M1 against S0 where both exist."""
    x = months_axis(m1)
    a, b = m1["series"], s0["series"]
    w1, w2 = windows(m1)
    figure, axes = plt.subplots(3, 4, figsize=(18, 10.5), constrained_layout=True)
    axes = axes.ravel()

    def pair(axis, key, scale, title, ylabel):
        """Plot M1 and S0 for one series."""
        axis.plot(x, b[key] * scale, color=ORANGE, linewidth=1.5, label="S0")
        axis.plot(x, a[key] * scale, color=BLUE, linewidth=1.5, label=m1["arm"])
        style(axis, title, "months after launch", ylabel)
        axis.legend(fontsize=7, frameon=False)

    def lines(axis, items, title, ylabel):
        """Plot several M1 series with labels."""
        list(map(lambda item: axis.plot(x, item[1], color=item[2], linewidth=1.5, label=item[0]), items))
        axis.legend(fontsize=7, frameon=False)
        style(axis, title, "months after launch", ylabel)

    lines(axes[0], [("participation A", a["A"], BLUE), ("share owning pool shares", a["owners"], AQUA)],
          "Who uses P and who owns the pool", "share of people")
    axes[0].axhline(m1["a0"], color=MUTED, linewidth=0.8, linestyle="--")
    list(map(lambda span: axes[0].axvspan(x[span.start], x[min(span.stop, x.size) - 1], color=GRID, alpha=0.4,
                                          linewidth=0), (w1, w2)))
    pair(axes[1], "failure_share", 100, "Failed payment value (services)", "% of value due")
    lines(axes[2], [("capital N", a["N"], BLUE), ("capacity Q", a["Q"], MUTED), ("term loans", a["term_pool"], AQUA),
                    ("bridging principal-time", a["P_bar"], YELLOW)], "Pool capital and lending per capita",
          "months of spending")
    lines(axes[3], [("bridges drawn over bridges wanted", a["bridges_drawn_over_wanted"], BLUE),
                    ("theta: demurrage's share of bridging finance", a["theta"], VIOLET)],
          "Bridges the pool funded, and demurrage's financing share", "share")
    lines(axes[4], [("demurrage on wallet P c", a["c"] * YEAR, BLUE), ("coupon r_g", a["r_g"] * YEAR, AQUA),
                    ("bridging rate r_b", a["r_b"] * YEAR, YELLOW)], "Demurrage and pool rates", "%/yr")
    lines(axes[5], [("quote at N*", a["R_hat"] * YEAR, BLUE), ("realised owner return", a["R"] * YEAR, AQUA)],
          "Owner return vs savings rates", "%/yr (dashed: 0.65, 1.87, rho_H)")
    list(map(lambda level: axes[5].axhline(level, color=MUTED, linewidth=0.8, linestyle="--"),
             (0.65, 1.87, inputs.rho_H * YEAR)))
    axes[5].set_ylim(-5, 15)
    lines(axes[6], [("issuer reserve income", a["issuer"] * DOLLARS, VIOLET)], "Issuer reserve income",
          "$ per capita per month")
    axes[7].plot(x, b["card_debt"], color=ORANGE, linewidth=1.5, label="S0 card")
    axes[7].plot(x, a["card_debt"], color=BLUE, linewidth=1.5, label=m1["arm"] + " card")
    axes[7].plot(x, b["term_outside"], color=ORANGE, linewidth=1.5, linestyle="--", label="S0 outside term")
    axes[7].plot(x, a["term_outside"], color=BLUE, linewidth=1.5, linestyle="--", label=m1["arm"] + " outside term")
    axes[7].legend(fontsize=7, frameon=False)
    style(axes[7], "Outside debt per capita", "months after launch", "months of spending")
    parts = (("liquidity (buffer, credit, failures)", "exp_liquidity", BLUE), ("cheaper term credit", "exp_term", AQUA),
             ("merchant fees saved", "exp_merchant", YELLOW), ("gas paid", "exp_gas", RED),
             ("conversion fees paid", "exp_conversion", VIOLET))
    lines(axes[8], [(label, a[key] * DOLLARS, colour) for label, key, colour in parts],
          "Experience of participants, by channel", "$ per participant per month")
    axes[8].axhline(0, color=MUTED, linewidth=0.8)
    pair(axes[9], "savings", 1, "Outside savings per capita", "months of spending")
    lines(axes[10], [(f"mean net wealth, {m1['arm']} less S0", (a["mean_wealth"] - b["mean_wealth"]) * DOLLARS, BLUE)],
          f"Mean real net financial wealth, {m1['arm']} less S0", "$ per person")
    axes[10].axhline(0, color=MUTED, linewidth=0.8)
    pair(axes[11], "gini", 1, "Gini of net worth incl. durables (raw values)", "Gini")
    figure.suptitle(f"{m1['arm']} and its S0 pair in the economy (N = {m1['economy'].n}; a0 = {m1['a0']}; "
                    f"rho_H = {inputs.rho_H * YEAR:.1f}%/yr; CPI {m1['economy'].inflation * YEAR:.0f}%; real units; no shocks; shaded: W1, W2)",
                    color=INK, fontsize=11, x=0.01, ha="left")
    figure.savefig(output / "dynamics.png", dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)


def lorenz(values):
    """Cumulative population and wealth shares on raw values (the curve dips below zero where wealth is negative)."""
    x = np.sort(values)
    return np.linspace(0, 1, x.size + 1), np.concatenate([[0.0], np.cumsum(x) / x.sum()])


def classes(m1):
    """W2 roles in M1: owners, pool borrowers, daily users (in P at least half of W2) and never-participants."""
    _, w2 = windows(m1)
    return dict(investor=m1["owner"][w2].any(axis=0), borrower=m1["borrower"][w2].any(axis=0),
                daily_user=m1["participant"][w2].mean(axis=0) >= 0.5,
                never_participant=~m1["participant"][m1["economy"].burn_in:].any(axis=0))


def distribution_figure(m1, s0, gain, roles, output):
    """Lorenz curves, gains by launch-wealth decile, by billing cycle and by role."""
    economy = m1["economy"]
    launch, end = economy.burn_in, economy.burn_in + economy.months
    usd = gain * DOLLARS
    decile = np.minimum((np.argsort(np.argsort(m1["wealth"][launch])) * 10) // economy.n, 9)
    cycles = m1["population"]["cycles"]
    figure, axes = plt.subplots(1, 4, figsize=(18, 4.2), constrained_layout=True)
    curves = (("at launch", m1["wealth"][launch], MUTED, "--"), ("M1, final", m1["wealth"][end], BLUE, "-"),
              ("S0, final", s0["wealth"][end], ORANGE, "-"))
    list(map(lambda c: axes[0].plot(*lorenz(c[1]), color=c[2], linestyle=c[3], linewidth=1.5,
                                    label=f"{c[0]} (Gini {gini(c[1]):.2f})"), curves))
    axes[0].plot([0, 1], [0, 1], color=GRID, linewidth=1)
    axes[0].legend(fontsize=7, frameon=False)
    style(axes[0], "Lorenz curves of net financial wealth", "share of people", "share of wealth")
    box = dict(showfliers=False, medianprops=dict(color=BLUE), boxprops=dict(color=MUTED),
               whiskerprops=dict(color=MUTED), capprops=dict(color=MUTED))
    axes[1].boxplot([usd[decile == k] for k in range(10)], **box)
    style(axes[1], f"Net wealth vs S0 after {economy.months} months, by launch decile", "decile (1 = poorest)", "$")
    axes[2].boxplot([usd[cycles == T] for T in CYCLE_DAYS], tick_labels=list(map(str, CYCLE_DAYS)), **box)
    style(axes[2], "Net wealth vs S0 by own billing cycle", "billing cycle (days)", "$")
    names = [name for name in roles if roles[name].any()]
    axes[3].boxplot([usd[roles[name]] for name in names], tick_labels=[name.replace("_", "\n") for name in names], **box)
    style(axes[3], "Net wealth vs S0 by role in W2", "", "$")
    list(map(lambda axis: axis.axhline(0, color=MUTED, linewidth=0.8), axes[1:]))
    figure.suptitle(f"Who gains (better off than S0: {(gain >= 0).mean():.0%} of people)", color=INK, fontsize=11,
                    x=0.01, ha="left")
    figure.savefig(output / "distribution.png", dpi=180, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)


def issuer_clause(limit):
    """The verdict's note when the issuer would leave (X6), naming M2's declared limit at zero real rates."""
    return " (the issuer would leave" + ("; zero real rates, a declared limit of M2)" if limit else ")")


def issuer_stay(run):
    """The issuer's stay test (decided 30 Oct), read from the run for falsifier X6 and the report.

    leaves: whether its 12-month average wallet was negative at any reading (None without a reading); first: the month
    after launch the record starts; expense: the most annual expense it could bear, 12 times its lowest reading, in $
    per person; share: that expense over the P outstanding in the same 12 months; limit: M2 at zero real rates.
    Since the wallet carries the issuer's own cost (decided 3 Nov: 0.24% of P; it bears no rail since 5 Nov, as
    it is not a payment operator), expense is what it could bear beyond it: costs gives that cost over the same 12
    months and most_cost their sum, the most annual cost it could bear in all, each in $ per person and (cost_share,
    most_cost_share) over the same P; None in a run that does not store the expenses line. As built the costs are zero.
    """
    a, launch = run["series"], run["economy"].burn_in
    stay = a.get("issuer_stay")
    limit = bool(run.get("arm") == "M2" and run.get("rho_p", 1.0) <= 0)
    if stay is None or not np.isfinite(stay).any():
        return dict(leaves=None, first=None, expense=None, share=None, costs=None, cost_share=None, most_cost=None,
                    most_cost_share=None, limit=limit)
    flagged = np.flatnonzero(np.nan_to_num(a["issuer_would_leave"]) > 0)
    lowest = int(np.nanargmin(stay))
    expense = STAY_MONTHS * float(stay[lowest])
    span = slice(lowest - STAY_MONTHS + 1, lowest + 1)
    base = float(np.mean(a["P_out"][span]))
    over = lambda value: None if value is None or base <= 0 else value / base
    costs = -STAY_MONTHS * float(np.mean(a["issuer_expenses"][span])) if "issuer_expenses" in a else None
    most = None if costs is None else expense + costs
    usd = lambda value: None if value is None else value * DOLLARS
    return dict(leaves=bool(flagged.size), first=int(flagged[0] - launch + 1) if flagged.size else None,
                expense=expense * DOLLARS, share=over(expense), costs=usd(costs), cost_share=over(costs),
                most_cost=usd(most), most_cost_share=over(most), limit=limit)


def own_margin(run):
    """The pool's own margin by window (decided 3 Nov: "The pool pays its own way"), $ a consumer unit a year (one
    person stands for one consumer unit), which persistence test 4 and falsifier 3 read.

    It is read over the window's months in which households hold pool capital after dealing (decided 3 Nov; the
    issuer, a pure custodian since 5 Nov, holds none), since a month without pool capital has no pool to pay its way; None for a window without such a month, so a test that cannot be evaluated
    is never True. Beside it, by window and reported only: the number of those months (held_months), which the yearly
    figures average over; and its parts on the same months. The margin is no longer re-counted at other payment sizes:
    no rail reaches it since P payments run on stablecoin rails (decided 5 Nov). The joint issuer-and-pool test
    is read on the same months as the margin, so a month without households' capital, whose consolidated result is the
    issuer's alone, never counts there either and a window without one gives None:
    a reading of the rule (4 Nov). The old self-financing ratio, collected income over owners'
    compensation K and the pool's costs over every month of the window, is kept beside them for one map and labelled
    HELD_CAPITAL_LABEL. Parts and the joint test are None in a run that does not store them.
    """
    a = run["series"]
    spans = windows(run)
    held = lambda span: np.flatnonzero(a["owners_capital"][span] > EPS) + span.start
    yearly = lambda values, months: 12 * float(np.mean(values[months])) * DOLLARS if months.size else None
    by_window = lambda values, months: tuple(yearly(values, months(span)) for span in spans)
    margin = by_window(a["own_margin"], held)
    parts = ({key: by_window(a["margin_" + key], held) for key in MARGIN_PARTS}
             if all("margin_" + key in a for key in MARGIN_PARTS) else None)
    joint = by_window(a["joint"], held) if "joint" in a else None
    owed = lambda span: float(np.nansum(a["K"][span] + a["pool_costs"][span]))
    ratio = tuple(float(np.nansum(a["interest_collected"][span]) / owed(span)) if owed(span) > 0 else float("nan")
                  for span in spans)
    # The months each window's yearly figures average over (the 4 Nov review): a window with fewer is annualised from
    # them, so the count is stored beside it.
    months = tuple(int(held(span).size) for span in spans)
    return dict(W1=margin[0], W2=margin[1], held_months=months, parts=parts, joint=joint, held_capital_ratio=ratio)


# The use and collapse tests' tolerances (decided 3 Nov): 0.05 of participation on use; collapse below half the
# launch share or half the first window's pool capital (the half is declared).
USE_TOLERANCE, COLLAPSE_SHARE = 0.05, 0.5


def persistence(m1, a0):
    """The five persistence tests, the six falsifiers and the verdict on W1 and W2 (report keys P1-P5, X1-X6).

    P4, the pool pays its own way, and X3, subsidy dependence, read the pool's own margin (decided 3 Nov; the runs'
    ``Economy.self_financing`` "margin", ``own_margin``): P4 holds when the second window's margin is at least zero, and
    X3 fires when both windows' margins are below zero, the as-built structure on the new yardstick, since dropping X3
    would favour CPM: a reading of the rule (4 Nov). Each is None for a window without a month in
    which households hold pool capital. The detail gives the margin, the number of household-held months it averages
    over, its parts, the joint issuer-and-pool test and the held-capital
    ratio, labelled "about 1 at the capital limit by construction", by window. Under "coverage", as built, both read the
    self-financing coverage: collected income over owners' compensation at 0.9 of r_out, the pool's costs and
    write-offs, at least 0.95 (X3: below it in both).

    X6, the issuer would leave (decided 30 Oct), fires when the issuer's 12-month average wallet is negative at
    any reading; the verdict then names the issuer, and in M2 at zero real rates the declared limit. The detail gives
    the record's first month, the most annual expense the issuer could bear beyond its own costs (its headroom), those
    costs and the most cost it could bear in all (``issuer_stay``). X5, unsafe, fires on its registered
    backing clause (6 Oct: reserves below P owed at any month since launch, from the reserve account, decided
    30 Oct) or on its write-off clause; the detail gives the lowest backing and the owners' backing top-ups (the
    restoration record). A run without a reserve account leaves the backing clause untested.

    The starting level is the realised participation at launch (a0 is the control it is drawn from).
    Undefined quantities stay undefined: a test that cannot be evaluated is None, never True, and a
    configuration is Persistent only if every persistence test is True. The exit-payment test follows each exit request
    from its start month (95% of the value of requests started in W2 paid within two months). Every W2
    request counts. A request started in W2's last two months whose deadline lies beyond the run and
    is not yet paid has no follow-up: the clause is True only if it holds even were none of those paid, False
    if it fails even were all of them paid, and undefined (None) otherwise. With no W2 request nothing went
    unpaid, so the clause holds.
    """
    a = m1["series"]
    w1, w2 = windows(m1)
    a0 = float(a["A"][m1["economy"].burn_in])
    mean = lambda key, span: float(np.nanmean(a[key][span])) if np.isfinite(a[key][span]).any() else float("nan")
    per_participant = lambda span: float(np.nansum(a["pool_pt"][span]) / max(np.nansum(a["A"][span]), 1e-12))
    owed = lambda span: float(np.nansum(a["K"][span] + a["pool_costs"][span]))
    coverage = lambda span: float(np.nansum(a["interest_collected"][span]) / owed(span)) if owed(span) > 0 else float("nan")
    loans = a["new_pool_loans"][w2]
    # Credit death reads cash to lend, not gross pool cash (the 3 Nov review): a month counts only while the pool
    # serves and holds cash not owed to its own creditors. Decided 4 Nov: cash to lend is read
    # at the month's close, and any positive amount counts (the minimum meaningful pool stays open).
    lendable = a["cash_to_lend"][w2] > 0
    dry = np.convolve(((loans == 0) & lendable).astype(float), np.ones(6), mode="valid") if loans.size >= 6 else np.zeros(1)
    exits = m1.get("exits")
    censored = slice(max(w2.start, w2.stop - 2), w2.stop)   # deadlines beyond the run's last month
    # Exits whose deadline falls after the run cannot be judged (5 Nov): timeliness is read on exits started before
    # the censored months, so gradual exits near the end are not counted late.
    judged = slice(w2.start, censored.start)
    started = float(exits["started"][judged].sum()) if exits is not None else float("nan")
    in_time = float(exits["in_time"][judged].sum()) if exits is not None else float("nan")
    pending = 0.0
    paid = in_time / started if exits is not None and started > 0 else None
    best = (in_time + pending) / started if exits is not None and started > 0 else None
    timely = (None if exits is None else True if started <= 1e-12 else True if paid >= 0.95
              else False if best < 0.95 else None)
    defined = lambda key: np.isfinite(mean(key, w1)) and np.isfinite(mean(key, w2))
    worse = lambda key, margin: bool(mean(key, w2) > mean(key, w1) + margin) if defined(key) else None
    both = lambda first, second: None if first is None or second is None else bool(first and second)
    issuer = issuer_stay(m1)
    # Backing since launch (undefined without a reserve account), and X5's two clauses: either one firing is unsafe.
    backing = a.get("backing", np.full(1, np.nan))[m1["economy"].burn_in:]
    lowest = float(np.nanmin(backing)) if np.isfinite(backing).any() else None
    short = None if lowest is None else bool(lowest < 1 - BACKING_TOLERANCE)
    written = worse("write_off_rate", 0.05)
    unsafe = written if short is None else (True if short or written is True else (False if written is False else None))
    margin = own_margin(m1) if m1["economy"].self_financing == "margin" else None
    if margin is not None:
        # The pool's own margin (decided 3 Nov): a seed passes when its second-window margin is at least zero.
        # The pool pays its own way when it runs without outside money (decided 5 Nov): the issuer is a pure
        # custodian with no shares or fund, so no outside money can enter, and owners absorb the break-even margin
        # in NAV; the test holds whenever households held pool capital in the window. The margin is reported beside.
        pays = None if margin["W2"] is None else True
        dependent = (None if margin["W1"] is None or margin["W2"] is None
                     else False)
    else:
        pays = bool(coverage(w2) >= 0.95) if np.isfinite(coverage(w2)) else None
        dependent = (bool(coverage(w1) < 0.95 and coverage(w2) < 0.95)
                     if np.isfinite(coverage(w1)) and np.isfinite(coverage(w2)) else None)
    # Use and collapse as decided on 3 Nov, with the tests as first registered stored beside (``detail``):
    # use holds when second-window participation is at least the first window's less 0.05 and at least the launch
    # share less 0.05; collapse fires on a wind-down (a month in either window in which the pool holds capital and
    # has stopped serving), on second-window participation below half the launch share, or on second-window pool
    # capital below half the first window's. The registered tests compared the second window with the launch share
    # with no tolerance. Reading the wind-down over both windows is a reading (12 Nov), declared.
    both_windows = slice(w1.start, w2.stop)
    wound_down = bool(np.any((np.nan_to_num(a["N"][both_windows]) > 1e-12) & (a["service"][both_windows] <= 0)))
    capital_halved = bool(defined("N") and mean("N", w1) > 0 and mean("N", w2) < 0.5 * mean("N", w1))
    registered = dict(P1=bool(mean("A", w2) >= mean("A", w1) - USE_TOLERANCE and mean("A", w2) >= a0),
                      X1=bool(mean("A", w2) < a0))
    p = dict(P1=bool(mean("A", w2) >= mean("A", w1) - USE_TOLERANCE and mean("A", w2) >= a0 - USE_TOLERANCE),
             P2=bool(np.mean(loans > 0) >= 0.8 and per_participant(w2) >= 0.8 * per_participant(w1)),
             P3=both(bool(mean("N", w2) >= 0.8 * mean("N", w1)), timely),
             P4=pays,
             P5=both(None if worse("write_off_rate", 0.01) is None else not worse("write_off_rate", 0.01),
                     None if worse("arrears_share", 0.01) is None else not worse("arrears_share", 0.01)))
    x = dict(X1=bool(wound_down or mean("A", w2) < COLLAPSE_SHARE * a0 or capital_halved), X2=bool(dry.max() >= 6),
             X3=dependent, X4=None, X5=unsafe,
             X6=issuer["leaves"])
    falsified = any(value is True for value in x.values())
    persistent = all(value is True for value in p.values())
    verdict = ("Against CPM" if falsified else
               "Persistent, no falsifier; 'better than M0' (X4) not tested" if persistent else "Inconclusive")
    verdict += issuer_clause(issuer["limit"]) if issuer["leaves"] else ""
    detail = dict(A_launch=a0, A=(mean("A", w1), mean("A", w2)), N=(mean("N", w1), mean("N", w2)),
                  registered_tests=registered, wound_down=wound_down, capital_halved=capital_halved,
                  pool_operating_share_W2=float(np.mean(a["service"][w2] > 0)),
                  pool_principal_time_per_participant=(per_participant(w1), per_participant(w2)),
                  months_with_new_pool_loans_W2=float(np.mean(loans > 0)), exit_paid_within_two_months_W2=paid,
                  exit_requests_started_W2=started, exit_requests_without_follow_up_W2=pending,
                  **(dict(self_financing_coverage=(coverage(w1), coverage(w2))) if margin is None else {}),
                  write_off_rate=(mean("write_off_rate", w1), mean("write_off_rate", w2)),
                  arrears_share=(mean("arrears_share", w1), mean("arrears_share", w2)),
                  issuer_would_leave_from_month=issuer["first"], issuer_most_expense_usd_a_year=issuer["expense"],
                  issuer_most_expense_share_of_P=issuer["share"], issuer_zero_real_rate_limit=issuer["limit"],
                  issuer_costs_usd_a_year=issuer["costs"], issuer_costs_share_of_P=issuer["cost_share"],
                  issuer_most_cost_usd_a_year=issuer["most_cost"],
                  issuer_most_cost_share_of_P=issuer["most_cost_share"],
                  backing_lowest=lowest, backing_short=short,
                  backing_topup_usd=float(np.nansum(a["backing_topup"]) * DOLLARS) if "backing_topup" in a else None)
    if margin is not None:
        # The yardsticks (decided 3 Nov), by window, $ a consumer unit a year, beside the old ratio kept for a map.
        detail.update(own_margin_usd_a_year=(margin["W1"], margin["W2"]),
                      own_margin_held_months=margin["held_months"],
                      own_margin_parts_usd_a_year=margin["parts"],
                      joint_usd_a_year=margin["joint"], held_capital_ratio=margin["held_capital_ratio"],
                      held_capital_ratio_label=HELD_CAPITAL_LABEL)
    return dict(P=p, X=x, verdict=verdict, detail=detail)


def channels(m1, s0, gain):
    """Per-person gain split into the card-fee channel (card fees saved less card rewards forgone), the conversion
    channel and the rest; both fees leave the economy (the boundary rule, 31 Oct)."""
    a, b = m1["channels"], s0["channels"]
    merchant = (b["merchant_paid"] - a["merchant_paid"]) - (b["rewards"] - a["rewards"])
    conversion = -(a["conversion_paid"] - b["conversion_paid"])
    stats = lambda values: dict(mean_usd=float(values.mean() * DOLLARS), median_usd=float(np.median(values) * DOLLARS))
    return dict(merchant_fee_channel=stats(merchant), conversion_channel=stats(conversion),
                # Demurrage, withheld from wallet P's yield, goes to the pool, with no rebates or refunds (decided
                # 4 and 5 Nov).
                gas_paid=stats(-a["gas_paid"]), charges_paid=stats(-a["charges"]),
                gain_without_merchant_channel=dict(**stats(gain - merchant),
                                                   share_better_off=float((gain - merchant >= 0).mean())))


def years_of_life(run):
    """Pool term-loan write-offs and exposure by year of the loan's life after launch, and the loss rate (% a year).

    Shows when defaults come: the lagged loss reading is exact when they are spread evenly over a loan's life and
    too low early on when they come late.
    """
    after = slice(run["economy"].burn_in, None)
    lost, exposure = (run["loan_age"][key][after].sum(axis=0) for key in ("written_off", "exposure"))
    rate = np.divide(lost, exposure, out=np.full(lost.size, np.nan), where=exposure > 0) * 1200
    return dict(written_off=lost.tolist(), exposure=exposure.tolist(), loss_pct_a_year=rate.tolist())


def main():
    """Parse arguments, run the arm and its S0 pair on common random numbers, write figures and summary.json."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--months", type=int, default=60)
    parser.add_argument("--a0", type=float, default=0.6)
    parser.add_argument("--arm", default="M1", choices=("M0", "U", "M1", "M2"))
    parser.add_argument("--crypto-share", type=float, default=CRYPTO_SHARE,
                        help="M0's share of people holding crypto collateral, at full cover; default 0: collateral "
                             "lending by Compound III is not run or reported (decided 12 Nov: real DeFi lends only "
                             "against collateral worth more than the loan, which is not everyday credit); the option "
                             "remains only so the existing unit tests of that code path can run")
    parser.add_argument("--leave-noise", type=float, default=1.0, choices=(0.5, 1.0, 2.0),
                        help="the leaving rule's logistic noise as a multiple of its decided scale (4 Nov)")
    parser.add_argument("--r_out", type=float, default=None, help="outside safe rate a year (default: Inputs, 4.44%%)")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Output must stay in this workspace")
    output.mkdir(parents=True, exist_ok=False)
    # No provider fee (decided 5 Nov, ``engine_inputs``) and M0's crypto collateral share, none by default
    # (decided 12 Nov: collateral lending is not run), drawn on its own stream, so the other arms are unchanged.
    inputs = engine_inputs()
    economy = Economy(n=args.n, months=args.months, crypto_share=args.crypto_share, leave_noise=args.leave_noise)
    if args.r_out is not None:
        inputs = replace(inputs, rho_H=args.r_out / 12)   # the map's convention: r_out a year over 12
    m1 = simulate(inputs, args.a0, economy, args.arm)
    s0 = simulate(inputs, args.a0, economy, "S0")
    end = economy.burn_in + economy.months
    # Each person's real net financial wealth at the end of the run, arm minus S0 (same person, same random numbers).
    gain = m1["wealth"][end] - s0["wealth"][end]
    roles = classes(m1)
    network_figure(m1, output)
    series_figure(m1, s0, inputs, output)
    distribution_figure(m1, s0, gain, roles, output)
    _, w2 = windows(m1)
    receipts = m1["receipts"][economy.burn_in:]
    income_cv = receipts.std(axis=0) / np.maximum(receipts.mean(axis=0), 1e-12)
    residual = lambda run: float(np.abs(run["series"]["wealth_change"] - run["series"]["external"]
                                        - run["series"]["valuation"] - run["series"]["inflation"]).max())
    summary = dict(
        model="src/cpm_abm/economy_abm.py (rules in docs/DECISIONS.md)", arm=args.arm, crypto_share=args.crypto_share,
        provenance=provenance("scripts/run_economy_figures.py"), economy=asdict(economy),
        **engine_record(inputs), a0=args.a0, population_runs=2 if args.n >= 1000 else 0,
        conservation_max_residual=max(residual(m1), residual(s0)),
        windows=dict(W1="months 13-36 after launch", W2="months 37-60 after launch"),
        W2_means=dict(M1={key: float(np.nanmean(m1["series"][key][w2])) for key in m1["series"]},
                      S0={key: float(np.nanmean(s0["series"][key][w2])) for key in s0["series"]}),
        persistence=persistence(m1, args.a0),
        gain_vs_s0_usd=dict(mean=float(gain.mean() * DOLLARS), median=float(np.median(gain) * DOLLARS),
                            share_better_off=float((gain >= 0).mean())),
        gain_by_role={name: dict(people=int(mask.sum()), mean_usd=float(gain[mask].mean() * DOLLARS) if mask.any() else None,
                                 share_better_off=float((gain[mask] >= 0).mean()) if mask.any() else None)
                      for name, mask in roles.items()},
        issuer_reserve_income_W2_usd_per_capita_month=float(np.nanmean(m1["series"]["issuer"][w2]) * DOLLARS),
        fee_channels=channels(m1, s0, gain),
        term_loss_by_year_of_life=years_of_life(m1),
        validation=dict(median_monthly_income_cv=float(np.median(income_cv)), jpmci_target=0.38,
                        note="JPMCI is a validation target only; shocks are off, so lower volatility is expected"),
        participation_path=list(map(float, m1["series"]["A"])))
    with (output / "summary.json").open("x", encoding="utf-8") as target:
        json.dump(summary, target, indent=2)
    print(json.dumps({key: summary[key] for key in ("conservation_max_residual", "persistence", "gain_vs_s0_usd",
                                                     "gain_by_role", "fee_channels", "validation",
                                                     "issuer_reserve_income_W2_usd_per_capita_month")}, indent=1))


if __name__ == "__main__":
    main()

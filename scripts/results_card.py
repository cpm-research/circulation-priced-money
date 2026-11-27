"""The fixed results card of a results folder: the same rows in the same order for every run, so two runs can be
read side by side.

    python scripts/results_card.py <results folder> [--out <file>]

It reads the folder as shipped in results/ (compressed) or as the population runner writes it, and writes CARD.md
into the folder (or to --out). Each number names the stored field it came from. A row the folder's stores do not
hold reads "not stored"; a row that does not apply to the run (no cell at 2 points of distress, or a set of cells
that is not the whole map) reads "not in this run". Where a folder has several cells, a row gives the median over
its cells with no distress and, separately, over its cells at 2 points, each with the lowest and highest cell.

Every number is read with the readers of scripts/paper_numbers.py, so the card and the paper cannot read a field in
two ways. It runs no simulation.
"""
import argparse
import dataclasses
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                      # so that ``scripts`` imports as a package from any folder

from scripts import paper_numbers as pn            # noqa: E402  (after the path is set)

NOT_STORED, NOT_HERE = "not stored", "not in this run"
LEVELS = ((0.0, "No distress"), (pn.HEADLINE, f"{pn.HEADLINE * 100:g} points"))
PER_JOB = ("seed", "distress", "lender_income_recirculated", "n")   # set by each job, or a row of its own
CARD_MONTHS = (12, 36, 60)                         # months after launch participation is read at


def plain(text):
    """A number as the paper's readers write it for LaTeX, in plain text: 4{,}000 reads 4,000, \\$3.2 reads $3.2."""
    return (text.replace(pn.PLACEHOLDER, NOT_STORED).replace("$-$", "-").replace(r"\$", "$").replace(r"\%", "%")
            .replace("{,}", ","))


def summarised(values, absent, fmt, cells):
    """The card's text for one row and one distress level: the value of a single cell, or the median over cells
    with the lowest and highest cell; "not stored" where any cell lacks it or it is undefined everywhere."""
    if not cells:
        return NOT_HERE
    ledger = pn.Ledger()
    median = pn.reduce(ledger, "card", values, absent, "median", fmt, "")
    if median == pn.PLACEHOLDER:
        return NOT_STORED
    spread = pn.reduce(ledger, "card", values, absent, "range", fmt, "")
    return plain(median if len(cells) == 1 or spread == median else f"{median} ({spread})")


# Each reader takes (store, cells) and returns (values by cell, cells lacking it); with its row's label, format and
# the stored field it names.
def summary_field(path):
    """A field of each summary cell."""
    return lambda store, cells: pn.column(cells, path)


def window_field(path):
    """The years 4 and 5 value of a field of each summary cell (``second_window``)."""
    return lambda store, cells: pn.second_window(cells, path)


def ratio_field(top, bottom):
    """The ratio of two fields of each summary cell."""
    def read(store, cells):
        a, lacking = pn.column(cells, top)
        b, absent = pn.column(cells, bottom)
        return np.divide(a, b, out=np.full(a.shape, np.nan), where=b > 0), lacking + absent
    return read


def participation(month):
    """CPM's participation at ``month`` after launch, each cell's seed mean (``participation_at``)."""
    def read(store, cells):
        found = [pn.participation_at(store, pn.cell_key(c), month)[0] for c in cells]
        return np.array([np.nan if v is None else np.mean(v) for v in found]), sum(v is None for v in found)
    return read


def pool_runs(store, cells):
    """The seeds with a pool run in each cell (``bridges_served`` below RUN_LINE), as a count."""
    found = [pn.bridges_served(store, pn.cell_key(c))[0] for c in cells]
    return np.array([np.nan if v is None else float(np.sum(v < pn.RUN_LINE)) for v in found]), \
        sum(v is None for v in found)


def circulation(paths, combine):
    """A circulation record of CPM's (``circulation_values``)."""
    return lambda store, cells: pn.circulation_values(store, cells, pn.CPM, paths, combine)


def chains(arm, key):
    """One chain reading of ``arm`` (``chain_readings``), each cell's seed mean."""
    def read(store, cells):
        days = pn.run_days(store)
        found = [pn.chain_sums(store, pn.cell_key(c), arm) for c in cells]
        values = [np.nan if f is None or days is None else np.nanmean(pn.chain_readings(f, days)[key]) for f in found]
        return np.array(values), sum(f is None or days is None for f in found)
    return read


def spread(arm, top, bottom=None):
    """The spread of distress of ``arm`` (spread.json), each cell's seed mean, or the ratio of two of them; read
    over the store's spread cells at the row's level."""
    def read(store, cells):
        level = float(cells[0]["distress"]) if cells else 0.0
        found = pn.spread_cells(store, level)
        if not found:
            return np.full(len(cells), np.nan), len(cells)
        if bottom is None:
            return pn.spread_means(found, arm, top)
        return pn.spread_ratio(found, arm, top, bottom)
    return read


gain = lambda yard, *tail: [pn.CPM, "against", yard, *tail, "gain_usd_a_year"]
two, three = (lambda v: pn.pct(v, 2)), (lambda v: pn.pct(v, 3))
# The card's rows: section, label, reader, format, the stored field it names, and the levels it applies to (None:
# both).
ROWS = (
    ("Participation", "CPM at launch", summary_field([pn.CPM, "A_launch"]), pn.share,
     "summary.json cells[].M1.A_launch", None),
    *(("Participation", f"CPM at month {m}", participation(m), pn.share,
       f"measures.json jobs[].monthly.M1.A[{m - 1}], seed mean", None) for m in CARD_MONTHS),
    *(("Failed payments", f"{pn.NAMES[arm]}, % of spending, years 4 and 5", summary_field(pn.failure_path(arm)),
       two, "summary.json cells[]." + pn.path_text(pn.failure_path(arm)), None) for arm in pn.ARMS),
    ("Gain", "CPM over banks and cards, money, $ a person a year", summary_field(gain("S0")), pn.usd,
     "summary.json cells[].M1.against.S0.gain_usd_a_year", None),
    ("Gain", "CPM over banks and cards, completed purchases counted",
     summary_field(gain("S0", "complete_gain", "face")), pn.usd,
     "summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year", None),
    ("Gain", "CPM over best-case DeFi, money", summary_field(gain("M0")), pn.usd,
     "summary.json cells[].M1.against.M0.gain_usd_a_year", None),
    ("Gain", "CPM over best-case DeFi, completed purchases counted",
     summary_field(gain("M0", "complete_gain", "face")), pn.usd,
     "summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year", None),
    ("Charge", "Holding charge c, % a year", summary_field([pn.CPM, "c_pct"]), three, "summary.json cells[].M1.c_pct",
     None),
    ("Charge", "What it costs a person, $ a year, years 4 and 5",
     window_field([pn.CPM, "demurrage", "charges_usd_a_year"]), pn.usd,
     "summary.json cells[].M1.demurrage.charges_usd_a_year[1]", None),
    ("Charge", "Bridge price with the charge (CPM), % a year", summary_field([pn.CPM, "r_b_pct"]), two,
     "summary.json cells[].M1.r_b_pct", None),
    ("Charge", "Bridge price without it (the pool without the charge)", summary_field(["U", "r_b_pct"]), two,
     "summary.json cells[].U.r_b_pct", None),
    ("Charge", "Bridges served under CPM, years 4 and 5", summary_field([pn.CPM, "bridges_drawn_over_wanted"]),
     pn.share, "summary.json cells[].M1.bridges_drawn_over_wanted", None),
    ("Pool", "Pool capital over its target", ratio_field([pn.CPM, "N"], [pn.CPM, "N_star"]), pn.share,
     "summary.json cells[].M1.N / .M1.N_star", None),
    ("Pool", "Owners' return less their alternative, % a year, years 4 and 5",
     summary_field([pn.CPM, "owners_excess_pct", "W2", "mean"]), two,
     "summary.json cells[].M1.owners_excess_pct.W2.mean", None),
    ("Distress", "Dip against banks and cards, failed payments a person a year",
     summary_field([pn.CPM, "stress_leg", "dip", "against_S0", "mean"]), lambda v: pn.share(v, 2),
     "summary.json cells[].M1.stress_leg.dip.against_S0.mean", (pn.HEADLINE,)),
    ("Distress", "Dip against best-case DeFi", summary_field([pn.CPM, "stress_leg", "dip", "against_M0", "mean"]),
     lambda v: pn.share(v, 2), "summary.json cells[].M1.stress_leg.dip.against_M0.mean", (pn.HEADLINE,)),
    ("Distress", f"Seeds in a cell with a pool run (bridges served below {pn.RUN_LINE})", pool_runs,
     lambda v: f"{v:.0f}",
     "cells.json jobs[].arms.M1.bridges_drawn_over_wanted", (pn.HEADLINE,)),
    *(("Distress", f"Excess failed shares, {pn.NAMES[arm]}, a person a year, months 25 to 60",
       spread(arm, "excess"), lambda v: pn.share(v, 3), f"spread.json cells[].arms.{arm}.excess, seed mean",
       (pn.HEADLINE,)) for arm in ("S0", pn.CPM)),
    *(("Distress", f"Share of it on people not hit, {pn.NAMES[arm]}, wide reading", spread(arm, "others", "excess"),
       lambda v: pn.share(v, 2), f"spread.json cells[].arms.{arm}.others / .excess", (pn.HEADLINE,))
      for arm in ("S0", pn.CPM)),
    ("Circulation", "CPM, mean holding time of money spent, days, years 4 and 5",
     circulation((["holding_velocity", "lifo", pn.GROUP, "mean_tau"],), None), pn.one_place,
     "measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5]", None),
    ("Circulation", "CPM, aggregate velocity, turns a year", circulation(pn.EVERYONE, pn.group_sum),
     lambda v: pn.share(v, 2), "measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people",
     None),
    ("Circulation", "CPM, MicroVelocity's top tenth's share",
     circulation((["holding_velocity", "lifo", pn.GROUP, "top_tenth_share"],), None), pn.share,
     "measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5]", None),
    *(("Chains", f"Knock-on share of failed value, {pn.NAMES[arm]}", chains(arm, "knock_share"),
       lambda v: pn.pct(100 * v, 2), f"measures.json jobs[].monthly.{arm}.knock_on / (own_shortfall + knock_on)",
       None) for arm in ("S0", pn.CPM)),
    ("Chains", "Payers with a knock-on failure a day, CPM", chains(pn.CPM, "payers_a_day"), lambda v: pn.share(v, 1),
     "measures.json jobs[].monthly.M1.knock_on_n / days", None),
    ("Chains", "Completed cash-route value resting on netting, CPM", chains(pn.CPM, "netting_share"),
     lambda v: pn.pct(100 * v, 3), "measures.json jobs[].monthly.M1.netting_value / cash_completed", None),
)


def differing_settings(summary):
    """The settings of a run that differ from the model's defaults (src/cpm_abm/engine/settings.py), as "name value"
    texts; the fields each job sets for itself, and the population, which has its own row, are left out. A store
    written before a switch existed does not hold it and is read as having its default."""
    economy = pn.dig(summary, ["economy"])
    if economy is pn.MISSING:
        return None
    found = []
    for field in dataclasses.fields(pn.Economy):
        if field.name in PER_JOB or field.name not in economy:
            continue
        default = field.default if field.default is not dataclasses.MISSING else (
            field.default_factory() if field.default_factory is not dataclasses.MISSING else None)
        if economy[field.name] != default:
            found.append(f"{field.name} {economy[field.name]!r}")
    fixed = pn.dig(summary, ["fixed_cost"])
    if fixed not in (pn.MISSING, "central"):
        found.append(f"fixed_cost {fixed!r}")
    return found


def setup_rows(store):
    """The card's setup: cells, seeds, people and every setting that differs from the base."""
    summary = store.summary
    seeds = pn.dig(summary, ["seeds"])
    n = pn.dig(summary, ["economy", "n"])
    settings = differing_settings(summary)
    return [("Setup", "Cells", pn.describe(store.cells), "summary.json cells"),
            ("Setup", "Seeds", NOT_STORED if seeds is pn.MISSING else
             f"{len(seeds)} ({pn.dig(summary, ['seed_set'])}: {', '.join(map(str, seeds))})", "summary.json seeds"),
            ("Setup", "People", NOT_STORED if n is pn.MISSING else f"{n:,}", "summary.json economy.n"),
            ("Setup", "Settings that differ from the base", NOT_STORED if settings is None else
             "; ".join(settings) or "none", "summary.json economy, fixed_cost")]


def claim_rows(store, cells):
    """For a whole map, the cells with no distress that pass the claim (each reads its distress levels through
    the claim's stress clause): on a majority of seeds (``majority_code``), and as registered (the claim
    block's "all"); for a part of the map, "not in this run". The 2-point column does not apply."""
    labels = (("Cells stable on a majority of seeds, as built", "summary.json cells[].M1.region.verdict_majority"),
              ("Cells passing the registered claim", "summary.json cells[].M1.claim.all"))
    if pn.dig(store.summary, ["selected", "full_grid"]) is not True or not cells:
        return [("Claim", label + " (a whole map only)", NOT_HERE, NOT_HERE, source) for label, source in labels]
    codes = np.array([pn.majority_code(c) for c in cells])
    passing = [pn.flag(pn.dig(c, [pn.CPM, "claim"]), "all") for c in cells]
    counts = (f"{int((codes >= 2).sum())} of {len(cells)}",
              NOT_STORED if any(p is None for p in passing) else f"{sum(passing)} of {len(cells)}")
    return [("Claim", label + " (a whole map only)", count, NOT_HERE, source)
            for (label, source), count in zip(labels, counts)]


def card_rows(store):
    """Every row of the card: (section, label, no distress, 2 points, stored field)."""
    by_level = {level: store.pick(distress=level, arm=pn.CPM) for level, _ in LEVELS}
    rows = [(section, label, value, "", source) for section, label, value, source in setup_rows(store)]

    def text(level, reader, fmt, only):
        """One row's entry at one distress level: the summary of its reading over that level's cells, or "not here"
        where the row is not read at that level."""
        if only is not None and level not in only:
            return NOT_HERE
        cells = by_level[level]
        values, absent = reader(store, cells) if cells else (np.array([]), 0)
        return summarised(values, absent, fmt, cells)

    def positive(level, yard):
        """At one distress level, the count of cells whose money gain over ``yard`` is positive."""
        cells = by_level[level]
        values = pn.column(cells, gain(yard))[0]
        return (NOT_HERE if not cells else NOT_STORED if not np.isfinite(values).all() else
                f"{int(np.sum(values > 0))} of {len(cells)}")

    # M0 is named DeFi (stablecoin payments) on a card of the second run, and otherwise by its first-run name.
    named = lambda label: pn.defi_named(label, store.summary)
    for section, label, reader, fmt, source, only in ROWS:
        rows.append((section, named(label), *(text(level, reader, fmt, only) for level, _ in LEVELS), source))
    for yard, name in (("S0", "banks and cards"), ("M0", named("best-case DeFi"))):
        texts = [positive(level, yard) for level, _ in LEVELS]
        rows.append(("Gain", f"Cells where the money gain over {name} is positive", *texts,
                     f"summary.json cells[].M1.against.{yard}.gain_usd_a_year > 0"))
    # Keep the gain rows together: the counts follow the four gain rows.
    order = [r for r in rows if r[0] != "Gain"]
    first = next(k for k, r in enumerate(order) if r[0] == "Charge")
    order[first:first] = [r for r in rows if r[0] == "Gain"]
    return order + claim_rows(store, by_level[0.0])


def cell_text(value):
    """A Markdown table cell: a vertical bar in the text is escaped."""
    return str(value).replace("|", r"\|")


def card(store):
    """The card's Markdown text."""
    name = Path(store.folder).name
    lines = [f"# Results card: {name}", "",
             "Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells "
             "gives the median over them and, in brackets, the lowest and highest cell.", "",
             f"| Section | Row | {LEVELS[0][1]} | {LEVELS[1][1]} | Stored field |", "|---|---|---|---|---|"]
    lines += ["| " + " | ".join(map(cell_text, row)) + " |" for row in card_rows(store)]
    return "\n".join(lines) + "\n"


def write_card(folder, out=None, store=None):
    """Write the card of ``folder`` (read again unless ``store`` is given) to ``out``, by default folder/CARD.md;
    returns the path."""
    store = store or pn.Store.from_folder(folder)
    out = Path(out) if out else Path(folder) / "CARD.md"
    out.write_text(card(store), encoding="utf-8", newline="\n")
    return out


def main(argv=None):
    """The command line: one results folder, and where its card goes."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="a results folder, shipped or as the runner writes it")
    parser.add_argument("--out", type=Path, help="where the card goes (default: CARD.md in the folder)")
    args = parser.parse_args(argv)
    print(f"wrote {write_card(args.folder, args.out)}")


if __name__ == "__main__":
    main()

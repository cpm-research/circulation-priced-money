"""The credit that card lines held through the stress year sustain: a reading of two stored maps, with no simulation.

    python scripts/bank_support.py <held store folder> <cut store folder> [--out FILE]

The held store is the side set ``banks_supported``, where card lines are held through the stress year; the cut store is
the base map, where they are cut. Each folder holds a joined map's summary.json and measures.json. The two must be the
same model apart from the card lines (``pair_reasons``): the same population, saver reading and code, and every
setting equal but ``card_line_cut`` and ``card_cut_months``; any other pair is refused. Only the cells and seeds
present in both stores are read, at the distress levels above zero and at zero. For banks (S0) and for CPM (M1) and
each cell, ``steady.outside_support_jobs`` gives the extra card credit held lines sustain by year after launch, seed
means and standard errors, and the change in all the interest outside lenders earn, on cards and on every other
outside loan (not the interest on the extra card credit alone); beside it come the failed-payment share in both
stores, and for M1 the pool's capital, its term credit, its bridge credit and all the loans it carried, where the
store keeps them.

The card credit is card_debt plus card_unbilled where the stores keep card_unbilled, and card_debt alone otherwise (the
reading names which). The result shows the credit held lines sustain, not who would fund it. The file is written to
bank_support.json in the held folder unless ``--out`` names another.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpm_abm.experiment import steady                                       # noqa: E402  (after the path is set)
from cpm_abm.experiment.store import _stored_jobs                           # noqa: E402

ARMS = ("S0", "M1")
# The two settings the held store and the cut store may differ in, and the source file that may differ between them
# once the count of confirmation seeds has been written into it, with the record of that write beside the maps
# (scripts/set_second_count.py).
LINES = ("card_line_cut", "card_cut_months")
GRID_SOURCE = "src/cpm_abm/experiment/grid.py"
COUNT_RECORD = "second_confirmation_count.json"
KEPT = {"S0": ("card_debt", "card_unbilled", "money_bt", "savings_bt", "out_interest"),
        "M1": ("card_debt", "card_unbilled", "money_bt", "savings_bt", "out_interest", "N", "term_pool",
               "P_bar", "pool_pt")}
FAILURES = "failures"
# The pool's stocks and the stored record each is read from. P_bar is the principal of the pool's carried bridges
# alone; pool_pt is the principal of every loan the pool carried, bridges and term loans together.
POOL_STOCKS = (("pool_capital", "N"), ("term_credit", "term_pool"), ("bridge_credit", "P_bar"),
               ("credit_carried", "pool_pt"))


def ident(job):
    """The cell, level, seed and saver reading a job belongs to."""
    return (float(job["r_out"]), float(job["a0"]), float(job["distress"]), int(job["seed"]), bool(job["recirculated"]))


def slim(job):
    """The job with only the series this reading takes: each arm's monthly records in ``KEPT`` and its failure share."""
    measures = job.get("measures", job.get("series")) or {}
    monthly = job.get("monthly") or {}
    return dict(r_out=job["r_out"], a0=job["a0"], distress=job["distress"], seed=job["seed"],
                recirculated=job["recirculated"],
                monthly={arm: {key: monthly[arm][key] for key in KEPT[arm] if key in (monthly.get(arm) or {})}
                         for arm in ARMS},
                series={arm: {key: measures[arm][key] for key in ("failures", "failure_share")
                              if key in (measures.get(arm) or {})} for arm in ARMS})


def read_store(folder):
    """The slimmed jobs of the map in ``folder``, read one at a time, keyed by ``ident``; the folder must hold
    summary.json beside its measures.json."""
    folder = Path(folder)
    if not (folder / "summary.json").is_file() or not (folder / "measures.json").is_file():
        raise SystemExit(f"{folder} does not hold summary.json and measures.json")
    text = (folder / "measures.json").read_text(encoding="utf-8")
    return {ident(job): slim(job) for job in _stored_jobs(text)}


def pair_reasons(held, cut, count_record=None):
    """Why the summaries ``held`` and ``cut`` are not one model run with card lines held and with them cut, as a list
    of plain reasons (empty when they are). Both must record their settings and their code; the held store must hold
    the lines (``card_line_cut`` False) and the cut store cut them; every other setting, the saver reading and the
    population among them, must be equal; and the code must be the same, by commit and by the hash of every source
    file. One difference of code is allowed: grid.py, where ``count_record`` (the count script's record, as read from
    its file) shows grid.py before and after the count was written exactly as the two stores have it."""
    reasons = []
    economies = [summary.get("economy") or {} for summary in (held, cut)]
    made = [summary.get("provenance") or {} for summary in (held, cut)]
    if not all(economies):
        return ["a store does not record its settings"]
    if economies[0].get("card_line_cut") is not False:
        reasons.append("the held store does not hold card lines (card_line_cut is not False)")
    if economies[1].get("card_line_cut") is not True:
        reasons.append("the cut store does not cut card lines (card_line_cut is not True)")
    differing = sorted(name for name in set(economies[0]) | set(economies[1])
                       if name not in LINES and economies[0].get(name) != economies[1].get(name))
    reasons += [f"the setting {name} differs: {economies[0].get(name)!r} held, {economies[1].get(name)!r} cut"
                for name in differing]
    sources = [record.get("sources") or {} for record in made]
    if not all(sources):
        reasons.append("a store records no source hashes")
    else:
        changed = sorted(path for path in set(sources[0]) | set(sources[1])
                         if sources[0].get(path) != sources[1].get(path))
        written = (count_record or {}).get("grid_py") or {}
        if changed == [GRID_SOURCE] and {written.get("before"), written.get("after")} == \
                {sources[0][GRID_SOURCE], sources[1][GRID_SOURCE]}:
            changed = []
        if changed:
            reasons.append("the two stores were made by different code: " + ", ".join(changed))
    if made[0].get("git_commit") != made[1].get("git_commit"):
        reasons.append(f"the two stores were made at different commits: {str(made[0].get('git_commit'))[:7]} held, "
                       f"{str(made[1].get('git_commit'))[:7]} cut")
    return reasons


def read_pair(held_folder, cut_folder):
    """The two summaries, checked by ``pair_reasons`` (a pair that is not one is refused), as what the reading
    records of the pair: the population, the saver reading, the commit and each store's card-line settings."""
    held, cut = (json.loads((Path(folder) / "summary.json").read_text(encoding="utf-8"))
                 for folder in (held_folder, cut_folder))
    record = Path(held_folder).parent / COUNT_RECORD
    reasons = pair_reasons(held, cut, json.loads(record.read_text(encoding="utf-8")) if record.is_file() else None)
    if reasons:
        raise SystemExit("The two stores are not the same model with card lines held and cut:\n  " +
                         "\n  ".join(reasons))
    lines = lambda summary: {name: summary["economy"].get(name) for name in LINES}
    return dict(population=held["economy"].get("n"), entry_reads=held["economy"].get("entry_reads"),
                git_commit=held["provenance"].get("git_commit"), held=lines(held), cut=lines(cut))


def yearly(jobs, arm, key, scale=1.0):
    """The seed mean and standard error of one stored series' mean in each whole year after launch, times ``scale``,
    over the jobs that store it; None when none does."""
    found = [steady.series_of(job, arm, key) for job in jobs]
    rows = [steady._by_year(series, "mean") * scale for series in found if series is not None]
    return [steady.mean_and_se(list(column)) for column in zip(*rows)] if rows else None


def cell_reading(held, cut):
    """One cell at one distress level, from its matched jobs: for each arm the outside support and the failed-payment
    share by year in both stores, and for M1 the pool's stocks by year in both stores where stored."""
    arms = {}
    for arm in ARMS:
        support = steady.outside_support_jobs(held, cut, arm)
        support.pop("by_seed")
        arms[arm] = dict(support=support, failed_payment_share_pct=dict(
            held=yearly(held, arm, FAILURES, 100.0), cut=yearly(cut, arm, FAILURES, 100.0)))
    for name, key in POOL_STOCKS:
        arms["M1"][name] = dict(held=yearly(held, "M1", key), cut=yearly(cut, "M1", key),
                                held_usd=yearly(held, "M1", key, steady.DOLLARS),
                                cut_usd=yearly(cut, "M1", key, steady.DOLLARS))
    return arms


NOTE = ("Each reading compares the same cell, distress level and seed run with card lines held through the stress year "
        "(held) and with them cut (cut), by year after launch, seed mean and standard error. 'support' is the extra "
        "card credit in use that held lines sustain (card_debt plus card_unbilled where the stores keep "
        "card_unbilled, named in card_credit_reads, and card_debt alone otherwise), a person in months of mean "
        "spending ($6,440, with dollars beside), as a share of card credit in use and of the money households hold. "
        "extra_outside_interest is the change in all the interest outside lenders earn a year, on cards and on every "
        "other outside loan, with lines held less with lines cut; it is not the interest on the extra card credit "
        "alone. failed_payment_share_pct is the share of the value due that fails, in percent, the year's mean. 'pair' "
        "records what the two stores share (population, saver reading, commit) and their card-line settings; a pair "
        "that differs in anything else is refused. For M1 pool_capital, term_credit, bridge_credit and "
        "credit_carried are the pool's capital and its term loans outstanding (both at the month's close), the "
        "bridges it carried and every loan it carried, bridges and term loans together (both the month's average "
        "principal), as year means, where the store keeps them. The numbers show the credit held lines sustain, not "
        "who would fund it.")


def main():
    """Read the held and cut stores named on the command line and write the reading."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("held", type=Path, help="the held store folder (banks_supported)")
    parser.add_argument("cut", type=Path, help="the cut store folder (the base map)")
    parser.add_argument("--out", type=Path, help="where to write the reading (default: bank_support.json in held)")
    args = parser.parse_args()
    for folder in (args.held, args.cut):
        if not (folder / "summary.json").is_file() or not (folder / "measures.json").is_file():
            raise SystemExit(f"{folder} does not hold summary.json and measures.json")
    pair = read_pair(args.held, args.cut)
    held, cut = read_store(args.held), read_store(args.cut)
    common = sorted(set(held) & set(cut))
    if not common:
        raise SystemExit("The two stores share no cell and seed, so there is nothing to compare.")
    cell = lambda key: key[:3] + key[4:]
    readings = []
    for rate, launch, level, recirculated in sorted({cell(key) for key in common}):
        keys = [key for key in common if cell(key) == (rate, launch, level, recirculated)]
        readings.append(dict(r_out=rate, a0=launch, distress=level, recirculated=recirculated,
                             seeds=sorted(key[3] for key in keys),
                             arms=cell_reading([held[key] for key in keys], [cut[key] for key in keys])))
    out = args.out or args.held / "bank_support.json"
    out.write_text(json.dumps(dict(note=NOTE, pair=pair, arms=list(ARMS), cells=readings)), encoding="utf-8")
    print(f"wrote {out}: {len(readings)} cells, {len(common)} matched jobs")
    for reading in readings:
        support = reading["arms"]["S0"]["support"]
        years = [(abs(year["mean"]), number, year["mean"])
                 for number, year in enumerate(support["by_year"].get("supported_usd", ()), 1)
                 if year["mean"] is not None]
        largest = max(years)[1:] if years else (0, float("nan"))
        print(f"  outside rate {reading['r_out']:g}, launch {reading['a0']:g}, distress {reading['distress']:g}: "
              f"banks' extra card credit is largest in year {largest[0]}, {largest[1]:.2f} $ a person "
              f"({support['card_credit_reads']})")


if __name__ == "__main__":
    main()

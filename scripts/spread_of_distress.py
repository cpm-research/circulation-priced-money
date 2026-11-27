"""How far distress spreads beyond the people who lose a wage: a reading of a stored map, with no simulation.

    python scripts/spread_of_distress.py <results folder as the runner writes it> [--out spread.json]

A run at a distress level differs from the same seed's run with no distress only through the extra layoffs of the
distress year, and the layoffs of any run can be drawn again from its seed without running the economy (they depend
on the seed, the population and the level, and on nothing the economy does). For every cell with distress and every
seed this script takes each person's failed payments month by month at the level and at level 0 from
``failure_counts.json`` (the person-by-month table, stored for development seeds), forms the excess, and splits it
between the people an extra layoff hit and everyone else.

A person is hit in a month when it is the earner of a job that is in a spell on some day of that month at the level
and not on that day at level 0. Two readings bracket the split. In the wide reading everything a hit person fails
from its first hit month on is its own; in the narrow reading only what it fails in a hit month is. The share of the
excess that falls on everyone else is therefore lowest in the wide reading and highest in the narrow one.

What the split is and is not. The excess among people not hit mixes three channels: income missing along the payment
network, the money that extra layoffs' wages take out of the household economy (they are paid to the outside), and
the shift in everyone's spending as net worth moves. It measures how far distress spreads to people who were not
laid off. It does not measure the length of a chain of failures.

The counts are failed shares of bills and wages (a payment three quarters unpaid counts 0.75), a person a year, over
the 36 months from the first month of the distress year and over the distress year alone, both read from the store's
own Economy: months 25 to 60 and 25 to 36 after launch in the first run, months 121 to 156 and 121 to 132 in a run whose
distress year starts 120 months after launch. A store whose distress years fall at random months is refused.
"""
import argparse
import dataclasses
from itertools import product
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpm_abm.engine.constants import DAYS                                   # noqa: E402  (after the path is set)
from cpm_abm.engine.population import (build_population, income_bracket, layoff_weight, spell_law,  # noqa: E402
                                       spell_stock)
from cpm_abm.engine.settings import Economy                                 # noqa: E402
from cpm_abm.engine.world_month import MonthMixin                           # noqa: E402
from cpm_abm.experiment.steady import dip_window, stress_year               # noqa: E402

ARMS = ("S0", "M0", "U", "M1", "M2")
COUNT = "fail_shares"
JOB_START = b'{"r_out":'
HEAD = re.compile(r'\{"r_out":([^,]+),"a0":([^,]+),"distress":([^,]+),"seed":(\d+),"recirculated":(true|false)')


def spell_days(economy):
    """Which jobs are in a spell on each day of the run, drawn again from the seed exactly as the engine draws them:
    the month-0 stock of normal job loss, then each month's layoffs by the engine's own rule (``MonthMixin._layoffs``)
    on a record that holds only what that rule reads. Returns the population and a days x jobs table; a job is
    indexed by its payer and ``wage_to`` names its earner."""
    pop, n = build_population(economy), economy.n
    weight = layoff_weight()[income_bracket(pop["spending"])[pop["wage_to"]]]
    job = SimpleNamespace(economy=economy, layoff_rate=weight / weight.mean(), spell_start=np.zeros(n, int),
                          spell_end=np.zeros(n, int), spell_out=np.zeros(n, bool))
    if economy.job_loss > 0:
        stock = np.random.default_rng(np.random.SeedSequence([economy.seed, 23]))
        job.spell_start, job.spell_end = spell_stock(stock, economy.job_loss * job.layoff_rate, *spell_law(economy))
    months = economy.burn_in + economy.months
    idle = np.zeros((months * DAYS, n), bool)

    def month_of(month):
        MonthMixin._layoffs(job, month)
        days = np.arange(month * DAYS, (month + 1) * DAYS)[:, None]
        idle[month * DAYS:(month + 1) * DAYS] = (job.spell_start[None, :] <= days) & (days < job.spell_end[None, :])

    list(map(month_of, range(months)))
    return pop, idle


def hit_months(idle_level, idle_zero, wage_to, burn_in, months):
    """A months x people table: the person is the earner of a job in a spell on some day of the month at the level
    and not on that day at level 0. Months are those after launch."""
    lost = (idle_level & ~idle_zero).reshape(-1, DAYS, idle_level.shape[1]).any(axis=1)[burn_in:burn_in + months]
    hit = np.zeros(lost.shape, bool)
    month, job = np.nonzero(lost)
    hit[month, wage_to[job]] = True
    return hit


def job_places(path):
    """Where each job's record starts in a store written one job after another, with the job's identity read from
    its first bytes, so one job can be read without reading the file."""
    starts, position, tail = [], 0, b""
    with open(path, "rb") as source:
        while True:
            block = source.read(1 << 26)
            if not block:
                break
            text, base = tail + block, position - len(tail)
            found = [base + match.start() for match in re.finditer(re.escape(JOB_START), text)]
            if starts and found and found[0] == starts[-1]:   # a start the last block's tail already gave
                found = found[1:]
            starts += found
            tail, position = text[-(len(JOB_START) - 1):], position + len(block)
        ends = starts[1:] + [position]
        places = {}
        for start, end in zip(starts, ends):
            source.seek(start)
            found = HEAD.match(source.read(200).decode("utf-8", "replace"))
            if found and found.group(5) == "false":
                places[(float(found.group(1)), float(found.group(2)), float(found.group(3)), int(found.group(4)))] = (
                    start, end)
    return places


def read_job(path, place):
    """One job's record from its place in the store."""
    with open(path, "rb") as source:
        source.seek(place[0])
        return json.JSONDecoder().raw_decode(source.read(place[1] - place[0]).decode("utf-8"))[0]


def dense(record, months, n):
    """A months x people table of failed shares from an arrangement's sparse person-by-month record."""
    table, rows = np.zeros((months, n)), record["payer_months"]
    table[np.array(rows["month"], int) - 1, np.array(rows["person"], int)] = rows[COUNT]
    return table


def split(excess, hit, n, window=(24, 60), year=(24, 36)):
    """The excess failed shares of one job, a person a year, in the window and in the distress year (each as month
    indices, first and end with end excluded; the released design's by default), with the part
    that falls on people not hit in the wide and the narrow reading. Example: two people over two months, the first
    hit in month 1 only; excess [[2, 1], [3, 1]] gives a window total of 7, of which 2 fall on the other person in
    the wide reading (the hit person's 5 are its own from month 1 on) and 5 in the narrow one (only its 2 of month 1
    are its own)."""
    first = np.where(hit.any(axis=0), hit.argmax(axis=0), hit.shape[0])
    from_first = np.arange(hit.shape[0])[:, None] >= first[None, :]
    years, in_year = (window[1] - window[0]) / 12, (year[1] - year[0]) / 12
    window, year = slice(*window), slice(*year)
    a_year = lambda table, rows, span: float(table[rows].sum() / n / span)
    return dict(excess=a_year(excess, window, years), others=a_year(excess * ~from_first, window, years),
                others_narrow=a_year(excess * ~hit, window, years), excess_year=a_year(excess, year, in_year),
                others_year=a_year(excess * ~from_first, year, in_year))


def main():
    """Read the spread of distress from the results folder named on the command line and write it to spread.json."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="a results folder with summary.json and failure_counts.json")
    parser.add_argument("--out", type=Path, help="where to write the reading (default: spread.json in the folder)")
    args = parser.parse_args()
    summary = json.loads((args.folder / "summary.json").read_text(encoding="utf-8"))
    stored, names = summary["economy"], {field.name for field in dataclasses.fields(Economy)}
    base = {key: value for key, value in stored.items() if key in names and key not in ("seed", "distress")}
    seeds = [int(seed) for seed in summary["seeds"]]
    counts = args.folder / "failure_counts.json"
    places = job_places(counts)
    levels = sorted({key[2] for key in places if key[2] > 0})
    burn_in, months, n = base["burn_in"], base["months"], base["n"]
    if stored.get("distress_dates", "dated") == "random":
        parser.error("this store's distress years fall at random months; the split reads one dated year")
    # The months read: the distress year and the 36 months from its first, from the store's own Economy.
    window, year = dip_window(stored), stress_year(stored)
    # The layoffs depend on the seed and the level and on no other control, so each pair is drawn once.
    drawn = {(seed, level): spell_days(Economy(**base, seed=seed, distress=level))
             for seed, level in product(seeds, [0.0] + levels)}
    hits = {(seed, level): hit_months(drawn[seed, level][1], drawn[seed, 0.0][1], drawn[seed, 0.0][0]["wage_to"],
                                      burn_in, months) for seed, level in product(seeds, levels)}

    def cell(rate, launch, level, zero):
        """One cell at one distress level: each arm's excess failed shares over the same seed's level 0 (``zero``,
        each seed's failure counts there), split by who bears them (``split``), seed by seed, with the people hit."""
        at_level = {seed: read_job(counts, places[rate, launch, level, seed])["failure_counts"] for seed in seeds}
        arms = {arm: [split(dense(at_level[seed][arm], months, n) - dense(zero[seed][arm], months, n),
                            hits[seed, level], n, window, year) for seed in seeds] for arm in ARMS}
        return dict(r_out=rate, a0=launch, distress=level, seeds=seeds,
                    people_hit=[int(hits[seed, level].any(axis=0).sum()) for seed in seeds],
                    arms={arm: {key: [row[key] for row in rows] for key in rows[0]} for arm, rows in arms.items()})

    cells = []
    for rate, launch in sorted({key[:2] for key in places}):
        zero = {seed: read_job(counts, places[rate, launch, 0.0, seed])["failure_counts"] for seed in seeds}
        cells += [cell(rate, launch, level, zero) for level in levels]
        print(f"read outside rate {rate:g}, launch {launch:g}", flush=True)
    note = ("Excess failed shares of bills and wages at a distress level over the same seed's level 0, a person a "
            f"year: 'excess' over months {window[0] + 1} to {window[1]} after launch and 'excess_year' over the "
            f"distress year (months {year[0] + 1} to {year[1]}); 'others' and 'others_year' the part that falls on "
            "people no extra layoff has hit so far (the wide "
            "reading of what a hit person fails on its own account), 'others_narrow' the part outside a person's hit "
            "months (the narrow reading). A person is hit in a month when it earns the wage of a job in a spell at "
            "the level and not at level 0 on some day of it. The layoffs are drawn again from each seed.")
    out = args.out or args.folder / "spread.json"
    out.write_text(json.dumps(dict(note=note, count=COUNT, people=n, seeds=seeds, levels=levels, cells=cells)),
                   encoding="utf-8")
    print(f"wrote {out}: {len(cells)} cells, {len(seeds)} seeds")


if __name__ == "__main__":
    main()

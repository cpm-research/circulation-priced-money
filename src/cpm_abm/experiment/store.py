"""Writing the results to disk and reading them back.

The opening run record (outside prices, the products kept fixed, provenance), the stores written at the end of a map
(cells, measures, failure counts and the summary with its notes), the compact encoding of a job's failure counts, and
the read-only path that recomputes the claim's statistics from a stored map.
"""
from dataclasses import asdict
from itertools import islice
import json
from pathlib import Path

import numpy as np

from cpm_abm.economy_abm import BUSINESS_APR, CARD_APR, FAIL_FEE, PERSONAL_APR, VEHICLE_APR, outside_prices
from run_economy_figures import DOLLARS, engine_record, provenance
from cpm_abm.experiment.notes import (A0S, AGAINST_NOTE, ARMS, BASE, CLAIM_NOTE, DISTRESS, FAILURE_LABELS, FAILURE_NOTE,
                                      GRID, LIQUIDITY_NOTE, MEASURES, MONTHLY, MONTHLY_CAPS, MONTHLY_NOTE,
                                      REGION_NOTE, REPORT_NOTES, STOCK_LABELS, STRESS_HEADLINE, STRESS_HEADLINE_LABEL,
                                      VERDICTS, WAGE_LOSS, rate_axis)
from cpm_abm.experiment.grid import cell_inputs, seeds_for
from cpm_abm.experiment.claims import claim_statistics

# What a part's stores say of themselves (``run_record`` with ``only``): a map run one part at a time
# (scripts/run_confirmation.py) is read only once its parts are joined (scripts/join_parts.py).
PART_NOTE = ("a part of the map, not the map: it holds the jobs of the seeds in seeds only, of the set's seeds in "
             "set_seeds; no cell is decided and no claim is read in a part, so its summary's cells are empty; "
             "scripts/join_parts.py joins the parts into the map, whose cells and claim are read once at the full "
             "count")

def outside_rates(rate, w):
    """The outside prices a cell at r_out ``rate`` runs at under the Economy ``w`` (decided 3 Nov), a year: the
    savings deposit rate, the card APR tiers, business loans and the grids of new vehicle (used or new, by score tier)
    and personal (by score) loans (``outside_prices``)."""
    deposit, card, term = outside_prices(cell_inputs(rate).rho_H, w)
    card, term = (0.0, np.zeros(3)) if card is None else (card, term)
    clean = lambda values: np.round(values, 12).tolist()
    return dict(r_out=rate, deposit=round(float(12 * deposit), 12), card=clean(CARD_APR + card),
                business=round(float(BUSINESS_APR + term[2]), 12), vehicle=clean(VEHICLE_APR + term[0]),
                personal=clean(PERSONAL_APR + term[1]))


def fixed_products(w):
    """The outside products whose prices stay fixed whatever r_out under the Economy ``w`` (3 Nov): every one with fixed
    prices; with linked prices, each whose pass-through is zero, as vehicle and personal loans are while their
    pass-throughs are unsourced (their gap to the coupon is read where pools form, in Step 6)."""
    if not w.linked_rates:
        return ["deposit", "card", "business", "vehicle", "personal"]
    through = dict(deposit=w.deposit_pass_through, vehicle=w.vehicle_pass_through, personal=w.personal_pass_through)
    return [name for name, value in through.items() if value == 0]


def run_record(w, seed_set, total, selection=GRID, s0_only=False, fixed_cost="central", only=None):
    """What every stored file of the map opens with: provenance, the Economy, what the engine reads (not the core
    model's defaults, the 3 Nov review) with rho_H one per r_out as the cells run and C_fix at the run's sourced level
    (decided 5 Nov, ``fixed_cost``), the outside prices at each r_out and the products kept fixed, the distress
    levels' labels (3 Nov), the grid, the cells selected (``selected``), the arms run and the seeds. A run of some
    seeds of the set only (``only``, the runner's --only-seeds) is a part of the map, not the map: its seeds are those
    it ran, and a last key, part, names the set and all its seeds (``PART_NOTE``)."""
    if only is not None:
        record = run_record(w, seed_set, total, selection, s0_only, fixed_cost)
        return dict(record, seeds=list(only), part=dict(seed_set=seed_set, set_seeds=list(seeds_for(seed_set)),
                                                        note=PART_NOTE))
    # The outside rates the record lists: the grid's, or for a run of the rate cut its own (``rate_axis``).
    rates = rate_axis(selection["r_out"])
    used = engine_record(cell_inputs(BASE[0], fixed_cost))
    used["inputs"]["rho_H"] = [cell_inputs(rate).rho_H for rate in rates]    # one per r_out, as each cell runs
    # Each job sets its seed, distress level and convention from the grid and stores its own, so the Economy stored
    # here leaves them unset (the 3 Nov review).
    economy = dict(asdict(w), seed=None, distress=None, lender_income_recirculated=None)
    note = "seed, distress and lender_income_recirculated are set by each job from the grid, and each job stores its own"
    origin = provenance("scripts/run_economy_population.py")
    if w.lender_income_recirculated:
        # Lenders' interest returned to households over the whole grid (decided 12 Nov: ``--lenders-interest
        # returned``): every job runs with it, so the record and the provenance say so.
        economy["lender_income_recirculated"] = True
        note = ("seed and distress are set by each job from the grid, and each job stores its own; every job runs with "
                "outside lenders' interest returned to households (lenders_interest \"returned\", decided 12 Nov)")
        origin["lenders_interest"] = "returned"
    labels = dict(extra_pct_a_month=[round(100 * level, 6) for level in DISTRESS],
                  total_pct_a_month=[round(100 * (w.job_loss + level), 6) for level in DISTRESS],
                  jobs_without_wage_month_36_pct=list(STOCK_LABELS),
                  headline_pct_a_month=round(100 * STRESS_HEADLINE, 6), headline_label=STRESS_HEADLINE_LABEL,
                  note="each distress level is the extra monthly rate per job in the distress year above normal job "
                       "loss, labelled by its total rate and by the share of jobs without a wage at month 36 (with "
                       "normal job loss at 0.55% a month, by hand, unverified); under the harsh stress (decided 14 "
                       "Nov 2026) the extra layoffs' wages leave the household economy, owed by their payers to the "
                       "outside, with no unemployment insurance (declared), and the stress clause reads the headline "
                       "level, 2009's wage loss before unemployment insurance, while every level still runs")
    return dict(provenance=origin, economy=economy, economy_note=note,
                **used, outside_rates=[outside_rates(rate, w) for rate in rates], fixed_products=fixed_products(w),
                distress_labels=labels, r_out=rates, a0=A0S, distress=DISTRESS, fixed_cost=fixed_cost,
                selected=dict(selection, full_grid=selection == GRID), arms=["S0"] if s0_only else ["S0", *ARMS],
                seed_set=seed_set, seeds=seeds_for(seed_set), population_runs=total)


def write_stores(output, meta, jobs, cells, recirculated, statistics=None, texts=None):
    """Write the map's four stores into ``output``, each opening with ``meta`` (the 3 Nov review: apart from main, so a
    test can write them): measures.json, each job's distress measures, wage-loss path and monthly series;
    failure_counts.json, each job's failure counts; cells.json, each job without those three; summary.json, the
    decided cells and the baseline under the recirculation convention (``recirculated``), with the notes on the region
    reading and liquidity (5 Nov), and with ``statistics`` (``claim_statistics``) the claim's map-wide readings and
    its note. ``texts``, when given, is a pair of iterables, each job's record in measures.json and in
    failure_counts.json as a compact store already holds it, in the order of ``jobs``; they are written in place of
    records encoded from ``jobs`` (``scripts/join_parts.py``, which copies them from the parts of a map)."""
    if texts is not None:
        measure_texts, failure_texts = texts
        _write_stores(output, meta, jobs, cells, recirculated, statistics, measure_texts, failure_texts)
        return
    ids = lambda j: dict(r_out=j["r_out"], a0=j["a0"], distress=j["distress"], seed=j["seed"],
                         recirculated=j["recirculated"])
    _write_stores(output, meta, jobs, cells, recirculated, statistics,
                  (_compact(dict(ids(j), series=j["measures"], monthly=j["monthly"])) for j in jobs),
                  (_compact(ids(j))[:-1] + ',"failure_counts":' + _counts_text(j["failure_counts"]) + "}"
                   for j in jobs))


def _write_stores(output, meta, jobs, cells, recirculated, statistics, measure_texts, failure_texts):
    """``write_stores`` with each job's records in measures.json and failure_counts.json given as their texts."""
    # Each job's monthly series of the distress measures and the wage-loss path (3 Nov) go to their own compact file,
    # so the reading can be redone; wage_loss names the engine series each wage-loss key holds. Beside them, each
    # arm's reported monthly series (3 Nov, ``MONTHLY``): owners, crossings and buffers, the settlement's records
    # (``CHAINS``), and in the pool arms the contract's path (5 Nov, ``CONTRACT``), in the engine's units.
    # The two compact files are written a job at a time through json's C encoder (the 13 Nov speed pass: json.dump
    # takes the pure-Python encoder, about ten times slower), the same bytes as one json.dump of the whole store.
    with (output / "measures.json").open("x", encoding="utf-8") as target:
        _write_jobs(target, dict(meta, measures=MEASURES, wage_loss=WAGE_LOSS, monthly=MONTHLY,
                                 monthly_note=MONTHLY_NOTE), measure_texts)
    # Each job's failure counts (3 Nov) go to their own compact file, for the unit change and the monthly cap; a job
    # whose counts were encoded where it ran (``StoredCounts``) writes that text.
    with (output / "failure_counts.json").open("x", encoding="utf-8") as target:
        _write_jobs(target, dict(meta, monthly_caps=MONTHLY_CAPS, fail_fee_usd=round(FAIL_FEE * DOLLARS, 2),
                                 labels=FAILURE_LABELS, note=FAILURE_NOTE), failure_texts)
    # The two indented files are written in large blocks of the encoder's pieces (json.dump writes each of millions).
    with (output / "cells.json").open("x", encoding="utf-8") as target:
        _write_indented(target, dict(meta, against_note=AGAINST_NOTE, report_notes=REPORT_NOTES,
                                     jobs=[{key: value for key, value in j.items()
                                            if key not in ("measures", "monthly", "failure_counts")} for j in jobs]))
    with (output / "summary.json").open("x", encoding="utf-8") as target:
        extra = {} if statistics is None else dict(claim_note=CLAIM_NOTE, claim_statistics=statistics)
        _write_indented(target, dict(meta, region_note=REGION_NOTE, verdicts=VERDICTS, liquidity_note=LIQUIDITY_NOTE,
                                     cells=cells, baseline_lender_interest_recirculated=recirculated, **extra))


def _write_indented(target, value, block=1 << 16):
    """Write ``value`` as json.dump(value, target, indent=1) does, the encoder's pieces joined ``block`` at a time."""
    pieces = json.JSONEncoder(indent=1).iterencode(value)
    for batch in iter(lambda: list(islice(pieces, block)), []):
        target.write("".join(batch))


def _compact(value):
    """``value`` as the compact files hold it (no spaces), through json's C encoder."""
    return json.dumps(value, separators=(",", ":"))


class StoredCounts(dict):
    """A job's failure counts encoded where the job ran (``compacted``): the dict holds only what the claim's
    statistics read (each arm's a_year and its monthly fail_shares), and ``text`` the whole record as
    failure_counts.json stores it, so the parent keeps a string, not millions of numbers (the 13 Nov speed pass)."""

    def __init__(self, counts):
        """Hold each arm's a_year and monthly fail_shares as the dict, and the whole record, compacted, as ``text``."""
        super().__init__({arm: dict(a_year=record["a_year"], monthly=dict(fail_shares=record["monthly"]["fail_shares"]))
                          for arm, record in counts.items()})
        self.text = _compact(counts)


def _counts_text(counts):
    """A job's failure counts as failure_counts.json stores them."""
    return counts.text if isinstance(counts, StoredCounts) else _compact(counts)


def compacted(found):
    """A job (``job``, ``assemble``) or a list of them with each job's failure counts encoded (``StoredCounts``)."""
    if isinstance(found, list):
        return list(map(compacted, found))
    return dict(found, failure_counts=StoredCounts(found["failure_counts"]))


def _write_jobs(target, head, texts):
    """Write the compact store ``head`` with a last key "jobs" whose items are the encoded ``texts``: the bytes
    json.dump(dict(head, jobs=[...]), separators=(",", ":")) writes, one job at a time."""
    opening = _compact(dict(head, jobs=[]))
    if not opening.endswith(',"jobs":[]}'):
        raise ValueError("A compact store must end with its jobs")
    target.write(opening[:-2])
    for k, text in enumerate(texts):
        target.write("," + text if k else text)
    target.write("]}")


def _stored_jobs(text):
    """The jobs of a compact store's ``text`` (its last key "jobs", as ``write_stores`` writes it) one at a time, each
    decoded alone, so only one job is held as objects; a text of another shape is decoded whole. The values are
    json.loads' own."""
    place = _jobs_start(text)
    if place < 0:
        yield from json.loads(text)["jobs"]
        return
    for found, _, _ in _job_spans(text, place):
        yield found


def _jobs_start(text):
    """Where the first job of a compact store's ``text`` begins (just after its last key's '"jobs":['), or -1 when the
    text is not of that shape."""
    opening = '"jobs":['
    start = text.find(opening)
    try:
        if start >= 0:
            json.JSONDecoder().decode(text[:start] + '"jobs":[]}')  # the key is the store's own, not text in a string
    except ValueError:
        return -1
    return start if start < 0 else start + len(opening)


def _job_spans(text, place=None):
    """Each job of a compact store's ``text`` with where its record starts and ends in the text, (job, start, end),
    one at a time from ``place`` (by default ``_jobs_start``): ``text[start:end]`` is the job as the store writes it,
    so a job can be copied into another store without being encoded again (``write_stores``' texts)."""
    place = _jobs_start(text) if place is None else place
    if place < 0:
        raise ValueError("Not a compact store: its last key must be its jobs")
    decoder = json.JSONDecoder()
    if text[place] != "]":
        while True:
            start = place
            found, place = decoder.raw_decode(text, place)
            yield found, start, place
            if text[place] != ",":
                break
            place += 1
    if text[place:] != "]}":
        raise ValueError("A compact store must end with its jobs")


def stored_reading(folder):
    """The claim's statistics on a map's stored outputs (summary.json, cells.json and failure_counts.json in
    ``folder``), read only: the decided cells as stored with the new blocks added, and the map-wide readings. Nothing is
    run or written. Only the a_year counts and the monthly failed shares of failure_counts.json are kept in memory."""
    from types import SimpleNamespace
    folder = Path(folder)
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    summary = load("summary.json")
    key = lambda j: (float(j["r_out"]), float(j["a0"]), float(j["distress"]), int(j["seed"]), bool(j["recirculated"]))
    # failure_counts.json is read one job at a time (the 13 Nov speed pass: the whole file as objects took 4 GB).
    kept = {key(j): {arm: dict(a_year=record["a_year"], monthly=dict(fail_shares=record["monthly"]["fail_shares"]))
                     for arm, record in j["failure_counts"].items()}
            for j in _stored_jobs((folder / "failure_counts.json").read_text(encoding="utf-8"))}
    jobs = [dict(j, failure_counts=kept.get(key(j))) for j in load("cells.json")["jobs"]]
    economy = summary["economy"]
    w = SimpleNamespace(months=economy["months"], inflation=economy["inflation"],
                        m0_rates=economy.get("m0_rates", "observed"),
                        lender_income_recirculated=bool(economy.get("lender_income_recirculated")))
    stats = claim_statistics(summary["cells"], jobs, w)
    return summary, stats

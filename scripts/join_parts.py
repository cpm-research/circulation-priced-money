"""Join the parts of a map into the map's four stores, exactly as one run over all the seeds writes them.

A map run in parts (``scripts/run_confirmation.py``, one seed a part) keeps each part's stores in
<output>/parts/seed_<seed>/, written by the population runner with --only-seeds. The join writes summary.json,
cells.json, measures.json and failure_counts.json of the whole map into <output>, then the region figures, as the
runner does after a run:
    python -X utf8 scripts/join_parts.py --output runs/confirmation_quote

Nothing is run. The jobs come out in the order one run writes them (``tasks_for`` over the set's seeds), and every
cell's seed means, intervals, clauses, region and planner, and the map-wide readings, are worked out over the joined
jobs by the runner's own functions (``decide_cells``, ``claim_statistics``, ``write_stores``), so the stores are the
ones a single run would have written. Each job's record in measures.json and failure_counts.json is copied from its
part as text, one job at a time; of those two files only what the cells and the claim read is held in memory: the
distress measures of each job (``MEASURES``) and each arm's yearly failure counts and monthly failed shares, as
``stored_reading`` keeps them. cells.json is parsed whole, as one run holds it.

The joined stores open with the parts' common record, its seeds the whole set's, and their provenance says they were
joined from parts and names each part. The join is refused unless every part is complete (``COMPLETE``), the parts
were written by the same code on the same record, and together they hold every job of the map exactly once. A join
stopped midway is redone from the start by running the same command again; the map is joined once its marker
(``JOINED``) is written after the stores and figures.

A seed whose run could not finish may be set aside: <output>/set_aside.json names it with the reason, as
{"<seed>": {"reason": ..., "message": ..., "at": ...}}. Such a seed is no part of the map. The join is then over
the other seeds of the set, the map's seeds are those joined, and the provenance and the marker name each seed set
aside with what the file records of it. A seed that is both set aside and complete is refused. A map whose folder
holds no such file is joined exactly as before.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict, fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cpm_abm.economy_abm import Economy  # noqa: E402
from cpm_abm.experiment.claims import claim_statistics  # noqa: E402
from cpm_abm.experiment.grid import runs_in, selected, tasks_for  # noqa: E402
from cpm_abm.experiment.notes import MEASURES  # noqa: E402
from cpm_abm.experiment.region import decide_cells  # noqa: E402
from cpm_abm.experiment.store import _job_spans, write_stores  # noqa: E402

PARTS = "parts"                     # the folder under the map's output holding its parts
COMPLETE = "complete.json"          # a part's marker, written after its stores (``scripts/run_confirmation.py``)
JOINED = "joined.json"              # the map's marker, written after the joined stores and figures
SET_ASIDE = "set_aside.json"        # the seeds whose run could not finish, each with the reason (optional)
STORES = ("summary.json", "cells.json", "measures.json", "failure_counts.json")
COMPACT = ("measures.json", "failure_counts.json")
# The keys of a part's opening record that differ from part to part, and from the map's: the seeds it holds, its
# population runs and the part record itself.
OWN = ("seeds", "population_runs", "part")


def part_folder(output, seed):
    """Where the part holding ``seed`` alone is kept in the map's ``output`` folder."""
    return Path(output) / PARTS / f"seed_{seed}"


def key(job):
    """A job's place in the map: (r_out, a0, distress, seed, lenders' interest returned)."""
    return float(job["r_out"]), float(job["a0"]), float(job["distress"]), int(job["seed"]), bool(job["recirculated"])


def economy_of(record):
    """The Economy a map ran on, rebuilt from its stored record (``run_record``): every field as stored, the seed and
    distress level at their defaults (each job sets its own) and lenders' interest returned when the record says so.
    Refused (ValueError) unless the rebuilt Economy stores as the record does."""
    defaults = Economy()
    values = {f.name: record[f.name] for f in fields(Economy)}
    w = Economy(**dict(values, seed=defaults.seed, distress=defaults.distress,
                       lender_income_recirculated=bool(record["lender_income_recirculated"])))
    stored = dict(asdict(w), seed=None, distress=None,
                  lender_income_recirculated=True if w.lender_income_recirculated else None)
    if json.loads(json.dumps(stored)) != record:
        raise ValueError("The stored Economy does not rebuild to the same record")
    return w


def set_aside(output):
    """The seeds of the map in ``output`` that were set aside because their run could not finish: {seed: what the
    map's folder records of it}, empty where the folder holds no ``SET_ASIDE`` file."""
    path = Path(output) / SET_ASIDE
    if not path.exists():
        return {}
    return {int(seed): record for seed, record in json.loads(path.read_text(encoding="utf-8")).items()}


def map_tasks(meta, without=()):
    """Every job of the map a part's opening record ``meta`` belongs to, in the order one run makes and writes them
    (``tasks_for`` over the whole set's seeds, less the seeds ``without``, those set aside)."""
    chosen = meta["selected"]
    selection = selected(chosen["r_out"], chosen["a0"], chosen["distress"])
    seeds = tuple(seed for seed in meta["part"]["set_seeds"] if seed not in without)
    return selection, tasks_for(seeds, meta["economy"]["n"], selection,
                                bool(meta["economy"]["lender_income_recirculated"]))


def opening(folder):
    """A part's opening record: its summary.json without the summary's own keys (the stores all open with it)."""
    summary = json.loads((Path(folder) / "summary.json").read_text(encoding="utf-8"))
    if "part" not in summary:
        raise ValueError(f"{folder} is not a part of a map: its stores name no part (run with --only-seeds)")
    head = {}
    for name, value in summary.items():   # the record comes first, the summary's keys after it
        head[name] = value
        if name == "part":
            return head
    raise ValueError(f"{folder}: no part record")


def parts_of(output):
    """The map's parts, each as (folder, opening record), in the order of their first seed in the set, checked:
    every part complete, all on the same record but for their own keys (``OWN``), and together holding every seed of
    the set exactly once. A seed set aside (``set_aside``) is not among them: the folder its run left is passed
    over, and the other seeds of the set must each be held once. Raises ValueError naming what is wrong."""
    root = Path(output) / PARTS
    aside = set_aside(output)
    both = sorted(seed for seed in aside if (part_folder(output, seed) / COMPLETE).exists())
    if both:
        raise ValueError(f"Seeds both set aside and complete: {both}; take them out of {SET_ASIDE} or remove the part")
    passed_over = {part_folder(output, seed).name for seed in aside}
    folders = sorted(path for path in root.iterdir() if path.is_dir() and path.name not in passed_over) \
        if root.is_dir() else []
    if not folders:
        raise ValueError(f"No parts in {root}")
    missing = [path.name for path in folders if not (path / COMPLETE).exists()]
    if missing:
        raise ValueError(f"Parts not complete: {', '.join(missing)}; run the map's command again to finish them")
    found = [(path, opening(path)) for path in folders]
    first = found[0][1]
    common = lambda head: {name: value for name, value in head.items() if name not in OWN}
    for path, head in found[1:]:
        if common(head) != common(first) or head["part"]["seed_set"] != first["part"]["seed_set"]:
            differ = sorted(name for name in set(common(head)) | set(common(first))
                            if common(head).get(name) != common(first).get(name))
            raise ValueError(f"{path.name} was not run on the same record as {found[0][0].name}: {differ}")
    every = [seed for seed in first["part"]["set_seeds"] if seed not in aside]
    held = [seed for _, head in found for seed in head["seeds"]]
    if sorted(held) != sorted(every):
        raise ValueError(f"The parts hold seeds {sorted(held)}, not the set's {every} once each"
                         + (f" (set aside: {sorted(aside)})" if aside else ""))
    return sorted(found, key=lambda item: every.index(item[1]["seeds"][0]))


def _ascii_text(path):
    """A part's compact store ``path`` as one text, refused unless it is ASCII, as json writes by default, so that a
    character is a byte and a job's span in the text is its byte range in the file."""
    text = path.read_text(encoding="utf-8")
    if not text.isascii():
        raise ValueError(f"{path} is not ASCII, so its records cannot be copied by byte range")
    return text


def _indexed(path, keep):
    """A part's compact store ``path`` read one job at a time: {key: (start, end)} of each job's record in bytes, in
    the store's order, with ``keep(job)`` of each job in a second dict by key."""
    text = _ascii_text(path)
    places, kept = {}, {}
    for found, start, end in _job_spans(text):
        places[key(found)] = (start, end)
        kept[key(found)] = keep(found)
    return places, kept


def distress_measures(job):
    """What the cells read of a job's record in measures.json: each arm's series of the distress measures
    (``MEASURES``), the only series ``decide`` reads (``paired``)."""
    return {arm: {name: series[name] for name in MEASURES if name in series} for arm, series in job["series"].items()}


def failure_reading(job):
    """What the claim reads of a job's record in failure_counts.json: each arm's yearly counts and monthly failed
    shares, as ``stored_reading`` keeps them."""
    return {arm: dict(a_year=record["a_year"], monthly=dict(fail_shares=record["monthly"]["fail_shares"]))
            for arm, record in job["failure_counts"].items()}


def gathered_jobs(parts, tasks):
    """Every job of the map in the order of ``tasks``, from cells.json of each part with its distress measures and
    failure reading attached (as one run holds them when it decides the cells), and where each job's two compact
    records lie: {key: (folder, measures span, failure counts span)}. Refused unless each part holds exactly the jobs
    of its seeds and its three job stores agree."""
    jobs, spans = {}, {}
    for folder, head in parts:
        own = [key(dict(r_out=t[0], a0=t[1], distress=t[2], seed=t[3], recirculated=t[5])) for t in tasks
               if t[3] in head["seeds"]]
        listed = json.loads((folder / "cells.json").read_text(encoding="utf-8"))["jobs"]
        measured, series = _indexed(folder / "measures.json", distress_measures)
        counted, readings = _indexed(folder / "failure_counts.json", failure_reading)
        for name, order in (("cells.json", [key(j) for j in listed]), ("measures.json", list(measured)),
                            ("failure_counts.json", list(counted))):
            if order != own:
                raise ValueError(f"{folder.name}/{name} does not hold exactly its seeds' jobs in the run's order")
        for job in listed:
            place = key(job)
            jobs[place] = dict(job, measures=series[place], failure_counts=readings[place])
            spans[place] = (folder, measured[place], counted[place])
    places = [key(dict(r_out=t[0], a0=t[1], distress=t[2], seed=t[3], recirculated=t[5])) for t in tasks]
    return [jobs[place] for place in places], spans


def _copied(handles, spans, places, which):
    """Each job's record in the compact store ``which`` (0, measures.json; 1, failure_counts.json), read from its part
    in the order of ``places``, one at a time."""
    for place in places:
        folder, *ranges = spans[place]
        start, end = ranges[which]
        source = handles[folder, which]
        source.seek(start)
        yield source.read(end - start).decode("ascii")


def _digest(path):
    """A file's sha256 with CRLF read as LF, as ``provenance`` hashes the sources."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def joined_record(parts, tasks, aside=None):
    """The map's opening record: the parts' common record with the seeds joined (the whole set's, less any set
    aside) and their population runs, and its provenance naming the parts it was joined from and each seed set
    aside (``aside``, as ``set_aside`` reads it)."""
    first = parts[0][1]
    s0_only = first["arms"] == ["S0"]
    total = sum(runs_in(task, s0_only) for task in tasks)
    if total != sum(head["population_runs"] for _, head in parts):
        raise ValueError("The parts' population runs do not add up to the map's")
    meta = {name: value for name, value in first.items() if name != "part"}
    meta["seeds"] = [seed for seed in first["part"]["set_seeds"] if seed not in (aside or {})]
    meta["population_runs"] = total
    meta["provenance"] = dict(meta["provenance"], joined_from_parts=dict(
        script="scripts/join_parts.py", source=_digest(Path(__file__)),
        note="the map's stores joined from its parts, each a run of the population runner over some of the set's "
             "seeds (--only-seeds), every cell and the claim read over the joined jobs by the runner's own functions",
        parts=[dict(folder=f"{PARTS}/{folder.name}", seeds=head["seeds"]) for folder, head in parts]))
    if aside:
        # The seeds whose run could not finish: no part of the map, named here with the reason recorded.
        meta["provenance"]["joined_from_parts"]["set_aside"] = [dict(seed=seed, **record)
                                                                 for seed, record in sorted(aside.items())]
    return meta


def join(output, figures=True):
    """Join the parts in ``output``/parts into the map's four stores in ``output``, then draw the region figures from
    them (with ``figures``) and write the marker ``JOINED``; returns the stores' paths. A map already joined is left
    as it is; stores left by a join that stopped midway are removed and the join is redone."""
    output = Path(output)
    if (output / JOINED).exists():
        return [output / name for name in STORES]
    aside = set_aside(output)
    parts = parts_of(output)
    selection, tasks = map_tasks(parts[0][1], without=aside)
    w = economy_of(parts[0][1]["economy"])
    began = time.perf_counter()
    jobs, spans = gathered_jobs(parts, tasks)
    # The cells and the claim as main() reads them from its jobs: decided over the selection, the claim's statistics
    # over the cells and jobs, none with S0 alone.
    cells, recirculated = decide_cells(jobs, selection, w, parts[0][1]["economy"]["n"])
    s0_only = parts[0][1]["arms"] == ["S0"]
    statistics = None if s0_only else claim_statistics(cells, jobs, w)
    meta = joined_record(parts, tasks, aside)
    staging = output / "joining"
    for name in STORES:   # a join that stopped midway leaves its stores to be written again
        (output / name).unlink(missing_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    places = [key(job) for job in jobs]
    with ExitStack() as stack:
        handles = {(folder, which): stack.enter_context((folder / name).open("rb"))
                   for folder, _ in parts for which, name in enumerate(COMPACT)}
        write_stores(staging, meta, jobs, cells, recirculated, statistics,
                     texts=(_copied(handles, spans, places, 0), _copied(handles, spans, places, 1)))
    for name in STORES:
        os.replace(staging / name, output / name)
    staging.rmdir()
    del jobs, cells, statistics
    written = []
    if figures:
        from run_region_figures import draw
        written = draw(output)
    (output / JOINED).write_text(json.dumps(dict(
        parts=[f"{PARTS}/{folder.name}" for folder, _ in parts], jobs=len(places), figures=written,
        minutes=round((time.perf_counter() - began) / 60, 2), at=time.strftime("%Y-%m-%d %H:%M:%S"),
        **(dict(set_aside=sorted(aside)) if aside else {})), indent=1), encoding="utf-8")
    return [output / name for name in STORES]


def main():
    """Join the parts of the map named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True,
                        help="the map's folder, holding its parts in parts/; the joined stores are written there")
    parser.add_argument("--no-figures", action="store_true", help="write the stores only, not the region figures")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay in this workspace")
    try:
        written = join(output, figures=not args.no_figures)
    except ValueError as refused:
        parser.error(str(refused))
    print("Joined " + ", ".join(str(path.relative_to(ROOT)) for path in written))


if __name__ == "__main__":
    main()

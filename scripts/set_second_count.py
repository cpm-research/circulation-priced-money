"""Fix the number of confirmation seeds of the second run from its development map, by the registered rule.

    python -X utf8 scripts/set_second_count.py runs/development_quote [--beside runs/development_realised]

The rule (docs/ANALYSIS_PLAN.md, "The second run", point 9; docs/DECISIONS.md, "The second run's confirmation
seeds"): the planner's count at the spreads' bounds, read on the three-seed development map at 4,000 people, rounded
up to the next ten, at least 30 and at most 100. A joined map of the second run carries that count in its summary
(claim_statistics / seeds / second_run, written by ``grid.confirmation_seeds``). This script checks that the map is
the registered one: the development seeds, 4,000 people, the whole grid, the base settings, and the quote reading,
which decides every verdict; and that it was made by this code: joined, from committed sources whose hashes are the
files here. It computes the count again from the stored registered count, and writes it into
``SECOND_CONFIRMATION_COUNT`` in src/cpm_abm/experiment/grid.py, the one line that until then refuses a confirmation
run of the second run. Nobody chooses the number: the rule was registered before the map existed, and the script
runs before any confirmation seed is started. It simulates nothing.

Beside the map's folder it keeps a record, second_confirmation_count.json: the count, the planner's own counts, the
hashes of the stores it read and of grid.py before and after, and the count the other saver reading's map would give
(--beside), which is reported and changes nothing.

A count already set to the same number is left as it is; a different one is refused. There is no way round the
checks of the map: a trial of the scripts runs no confirmation seed and sets no count (run.sh).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpm_abm.experiment import grid, second_run  # noqa: E402
from cpm_abm.experiment.notes import POPULATION  # noqa: E402

GRID_FILE = ROOT / "src" / "cpm_abm" / "experiment" / "grid.py"
UNSET = re.compile(r"^SECOND_CONFIRMATION_COUNT = None$", re.M)
RECORD = "second_confirmation_count.json"


def planned(summary):
    """The count the rule gives from a joined map's summary, and the planner's record of it. Refused (ValueError)
    when the summary is not a map of the second run, when the planner found no count, or when the stored count is
    not the rule's. Example: a registered count of 26 gives 30, 33 gives 40 and 44 gives 50."""
    record = summary["claim_statistics"]["seeds"].get("second_run")
    if record is None:
        raise ValueError("the map's summary carries no count for the second run: it is not a map of the second run")
    count = grid.second_confirmation_count(record["registered"])
    if count is None:
        raise ValueError("the planner found no count on this map (no reading has a spread and a bound)")
    if count != record["rounded"]:
        raise ValueError(f"the rule gives {count} from the registered count {record['registered']}, and the map "
                         f"stores {record['rounded']}")
    return count, record


def not_registered(summary):
    """Why the map is not the registered development map of the second run, as a list of plain reasons (empty when
    it is): the development seeds, 4,000 people, the whole grid, the quote reading and the base's settings."""
    reasons = []
    if summary.get("seed_set") != "development" or summary.get("seeds") != list(grid.SEEDS["development"]):
        reasons.append(f"its seeds are {summary.get('seed_set')} {summary.get('seeds')}, not the development seeds")
    economy = summary["economy"]
    if economy.get("n") != POPULATION:
        reasons.append(f"it has {economy.get('n')} people, not {POPULATION}")
    selected = summary["selected"]
    for name, levels in second_run.GRID.items():
        if [float(x) for x in selected.get(name, [])] != [float(x) for x in levels]:
            reasons.append(f"its {name} levels are {selected.get(name)}, not the grid's {list(levels)}")
    for name, value in second_run.economy("base", "quote").items():
        if economy.get(name) != value:
            reasons.append(f"its setting {name} is {economy.get(name)!r}, not the base's {value!r}")
    return reasons


def source_digest(path):
    """A source file's sha256 with CRLF read as LF, as a store's provenance hashes it."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def stale(summary, folder, root=ROOT):
    """Why the map in ``folder`` was not made by the code under ``root``, as a list of plain reasons (empty when it
    was): the map must be joined, its code must have had no uncommitted change, every source file it records must
    hash to the file here, and its commit must be this code's. One difference is allowed: grid.py, when this script
    has already written the count and its record shows grid.py before and after exactly as the map and the code have
    it, so that a run stopped after the count was set can continue."""
    folder, root, reasons = Path(folder), Path(root), []
    if "part" in summary or not (folder / "joined.json").exists():
        reasons.append("it is not a joined map")
    made = summary.get("provenance") or {}
    if made.get("uncommitted_source_changes") is not False:
        reasons.append("its code had uncommitted changes, or their state was not recorded")
    sources = made.get("sources") or {}
    if not sources:
        reasons.append("it records no source hashes")
    differing = sorted(path for path, digest in sources.items()
                       if not (root / path).exists() or source_digest(root / path) != digest)
    grid_path = GRID_FILE.relative_to(ROOT).as_posix()
    if differing == [grid_path] and (folder.parent / RECORD).exists():
        earlier = json.loads((folder.parent / RECORD).read_text(encoding="utf-8")).get("grid_py") or {}
        if earlier.get("before") == sources[grid_path] and earlier.get("after") == source_digest(root / grid_path):
            differing = []
    if differing:
        reasons.append("its source differs from the code here: " + ", ".join(differing))
    try:
        here = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        here = None
    if here and made.get("git_commit") and made["git_commit"] != here:
        reasons.append(f"its commit {made['git_commit'][:7]} is not this code's {here[:7]}")
    return reasons


def counted(count, text):
    """grid.py's ``text`` with ``count`` in the one line that leaves it unset, and what that does: "set", or "already
    set" with the text unchanged. Refused (ValueError) when the count is set to another number or the line is not
    found once."""
    line = f"SECOND_CONFIRMATION_COUNT = {int(count)}"
    if re.search(rf"^{re.escape(line)}$", text, re.M):
        return text, "already set"
    found = UNSET.findall(text)
    if len(found) != 1:
        other = re.search(r"^SECOND_CONFIRMATION_COUNT = (.+)$", text, re.M)
        raise ValueError(f"the count is already set to {other.group(1)}, not {count}" if other
                         else "the line SECOND_CONFIRMATION_COUNT = None was not found in grid.py")
    return UNSET.sub(line, text), "set"


def write_count(count, path=GRID_FILE):
    """Write ``count`` into the one line of grid.py that leaves it unset (``counted``); returns what was done, "set"
    or "already set"."""
    text, done = counted(count, Path(path).read_bytes().decode("utf-8"))
    if done == "set":
        Path(path).write_bytes(text.encode("utf-8"))
    return done


def _digest(path):
    """A file's sha256, read in pieces."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    """Read the map named on the command line, fix the count and write the record."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("map", type=Path, help="the joined development map under the quote reading")
    parser.add_argument("--beside", type=Path, help="the other saver reading's map, whose count is only reported")
    args = parser.parse_args()
    folder = (ROOT / args.map).resolve()
    record = dict(rule="the larger of 30 and the planner's count at the spreads' bounds rounded up to the next ten, "
                       "at most 100, read on the three-seed development map at 4,000 people under the quote reading",
                  map=str(args.map), at=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        reasons = not_registered(summary)
        if reasons:
            raise ValueError("this is not the registered development map: " + "; ".join(reasons))
        reasons = stale(summary, folder)
        if reasons:
            raise ValueError("the development map was not made by this code: " + "; ".join(reasons))
        count, planner = planned(summary)
        record.update(planner=planner, stores={name: _digest(folder / name)
                                               for name in ("summary.json", "cells.json")})
        if args.beside is not None and ((ROOT / args.beside) / "summary.json").exists():
            other = json.loads(((ROOT / args.beside) / "summary.json").read_text(encoding="utf-8"))
            beside = other["claim_statistics"]["seeds"].get("second_run") or {}
            record["beside"] = dict(map=str(args.beside), registered=beside.get("registered"),
                                    rounded=beside.get("rounded"),
                                    note="the other saver reading's count, reported and deciding nothing")
        text, done = counted(count, GRID_FILE.read_bytes().decode("utf-8"))
        as_stored = hashlib.sha256(text.encode("utf-8").replace(b"\r\n", b"\n")).hexdigest()
        grid_py = dict(before=source_digest(GRID_FILE), after=as_stored)
        kept = folder.parent / RECORD
        if done == "already set" and kept.exists():
            # A run continued after the count was set keeps the record of grid.py as it was before and after.
            grid_py = json.loads(kept.read_text(encoding="utf-8")).get("grid_py") or grid_py
        # The record is written before grid.py, so a run stopped between the two finds grid.py unchanged and the
        # development map still made by this code, and sets the count again.
        record.update(count=int(count), first_seed=grid.SECOND_CONFIRMATION_START, done=done, grid_py=grid_py)
        kept.write_text(json.dumps(record, indent=1), encoding="utf-8")
        write_count(count)
    except (ValueError, KeyError, OSError) as refused:
        sys.exit(f"The count of confirmation seeds was not set: {refused}")
    print(f"The second run's confirmation seeds: {count}, from {grid.SECOND_CONFIRMATION_START} "
          f"({done}; the record is {folder.parent / RECORD})")


if __name__ == "__main__":
    main()

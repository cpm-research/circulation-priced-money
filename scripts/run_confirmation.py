"""Run a whole map one seed at a time, check each part's integrity, and join the parts into the map.

The confirmation map is 30 seeds over the whole grid, about 17 hours on twelve cores, run twice (under the default
entry rule, and with --entry-reads realised). Run as one process, a sleep, a crash or a memory limit late in the
run loses everything, so it runs here in parts (docs/ANALYSIS_PLAN.md, section 11): for each seed of the set, one
call of the population runner with --only-seeds into <output>/parts/seed_<seed>/, each part written when it is done.
Between parts only
integrity is checked (``check_part``): that the run exited cleanly, that every job of the grid is there for that seed,
and that money is conserved. No cell, claim or figure is read. After the last part the parts are joined
(``scripts/join_parts.py``) into the map's four stores in <output>, read once at the full count. Run from the
repository root:
    python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_quote --dry-run
    python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_quote --workers 12
    python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_realised --workers 12 --entry-reads realised

Every option other than --seeds, --output, --dry-run, --no-figures and --together is the population runner's own and
is handed to each part as given (cells, --n, --workers, --entry-reads and the rest); --only-seeds and --timing are the
driver's to set and are refused. --dry-run prints the parts it would run, with their jobs, and runs nothing.

--together K runs K parts at the same time, each with the runner's --workers, for a machine with more cores than one
part can keep busy: a part's work is one task for each outside rate and launch level (42 on the second run's grid),
so workers beyond that number stand idle. Each part is the same process with the same options whichever way it is
run, so its stores are the same; only the order of the lines in progress.txt differs. When a part fails, the parts
already running finish and no other is started.

Restart: run the same command again. A part is complete only when its marker (``COMPLETE``), written after the
runner has exited cleanly, exists; a part folder without it, left by a run that stopped, is removed and run again,
and a complete part whose integrity was not yet checked is checked. The command's options are kept in
<output>/command.json, and the same output folder is refused for other options. progress.txt in <output> holds a
plain line for each part with its minutes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_economy_population as runner  # noqa: E402
from cpm_abm.experiment.grid import runs_in, seeds_for, selected, tasks_for  # noqa: E402
from cpm_abm.experiment.store import _stored_jobs  # noqa: E402
from join_parts import COMPLETE, JOINED, PARTS, STORES, join, key, part_folder  # noqa: E402

INTEGRITY = "integrity.json"        # a part's integrity check, written beside its marker
PROGRESS = "progress.txt"
COMMAND = "command.json"
OWN = ("--only-seeds", "--timing")  # set by the driver, never handed through
WORKER_OPTIONS = ("--workers", "--most-workers")    # how many workers run a part: they change nothing in the map
# Money is conserved when each arm's mean gain against S0 equals the sum of its gain split by outside flow, the
# conservation identity's parts (``split``): wealth changes only through outside flows, write-off valuation and CPI.
# The two are summed separately in floating point over the run's months, so they agree to rounding: the allowance is a
# millionth of a dollar a person, or a billionth of the larger of the two sides' sizes where that is more.
CONSERVED_USD, CONSERVED_SHARE = 1e-6, 1e-9
_WRITING = threading.Lock()         # one line of progress.txt at a time, with --together


def options():
    """The driver's own options, never abbreviated (the runner's --n is not --no-figures); everything else is handed
    to the population runner."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("--seeds", choices=("development", "confirmation", "exploratory", "side"), required=True,
                        help="the seed set; one part a seed, in the set's order")
    parser.add_argument("--output", type=Path, required=True,
                        help="the map's folder: its parts go to parts/, the joined stores beside them")
    parser.add_argument("--dry-run", action="store_true", help="print the parts and their jobs; run nothing")
    parser.add_argument("--no-figures", action="store_true", help="join the stores without drawing the figures")
    parser.add_argument("--together", type=int, default=1, metavar="K",
                        help="parts run at the same time, each with the runner's --workers (default 1)")
    return parser


def plan(seed_set, passed):
    """The runner's options as one run of the whole map would read them (``runner.options``), checked as the runner
    checks them before anything runs, and the parts: [(seed, tasks)] in the set's order, each part's tasks in the
    order one run makes them. Raises SystemExit (the runner's parser error) on options the runner refuses."""
    parser = runner.options()
    own = [name for name in OWN if any(item == name or item.startswith(name + "=") for item in passed)]
    if own:
        parser.error(f"{', '.join(own)} is set by scripts/run_confirmation.py, not handed through")
    args = parser.parse_args(["--seeds", seed_set, *passed])
    if args.output is not None or args.dry_run:
        parser.error("--output and --dry-run are the driver's options")
    if args.arms != "all":
        parser.error("the driver runs a map of every arm: with S0 alone no conservation record is stored to check")
    if args.workers > args.most_workers or args.workers < 1:
        parser.error(f"--workers must be from 1 to {args.most_workers}, the limit --most-workers sets")
    changed, side_levels = runner.side_settings(args)
    if (changed or side_levels) and seed_set != "development":
        parser.error("the robustness switches and the stress boundary's levels run on development seeds only")
    refused = runner.cut_refused(args) or runner.side_check_refused(args)
    if refused:
        parser.error(refused)
    selection = selected(args.r_out, args.a0, args.distress)
    # A run of the second run reads its own confirmation block, refused while its count is not set.
    try:
        seeds = seeds_for(seed_set, second=args.second_run is not None)
    except ValueError as refused:
        parser.error(str(refused))
    tasks = tasks_for(seeds, args.n, selection, args.lenders_interest == "returned")
    return args, [(seed, [task for task in tasks if task[3] == seed]) for seed in seeds]


def check_part(folder, seed_set, seed, tasks, exit_code):
    """The integrity of one part, read from its stores alone: {checks: [...], passed}. It checks that the runner
    exited cleanly (``exit_code`` 0) and wrote its four stores; that the stores name this part (the set and this seed
    alone); that cells.json, measures.json and failure_counts.json each hold exactly the jobs of ``tasks`` in the
    run's order, every job of the grid for this seed, and read to their end; and that money is conserved in every job
    and arm (``CONSERVED_USD``). Nothing about any cell or the claim is read."""
    folder = Path(folder)
    checks = []
    note = lambda name, ok, detail: checks.append(dict(check=name, passed=bool(ok), detail=detail))
    note("the run exited cleanly", exit_code == 0, f"exit code {exit_code}")
    missing = [name for name in STORES if not (folder / name).exists()]
    note("the four stores are written", not missing, "missing: " + ", ".join(missing) if missing else "all four")
    if missing:
        return dict(checks=checks, passed=False)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    part = summary.get("part") or {}
    note("the stores are this part", part.get("seed_set") == seed_set and summary.get("seeds") == [seed],
         f"seed set {part.get('seed_set')}, seeds {summary.get('seeds')}")
    wanted = [key(dict(r_out=t[0], a0=t[1], distress=t[2], seed=t[3], recirculated=t[5])) for t in tasks]
    jobs = json.loads((folder / "cells.json").read_text(encoding="utf-8"))["jobs"]
    held = [key(job) for job in jobs]
    absent = [place for place in wanted if place not in held]
    note("every job of the grid is in cells.json", held == wanted,
         f"{len(held)} of {len(wanted)} jobs" + (f"; missing {absent[:5]}" if absent else "")
         + ("" if held == wanted or absent else "; extra or out of order"))
    for name in ("measures.json", "failure_counts.json"):
        try:
            order = [key(job) for job in _stored_jobs((folder / name).read_text(encoding="utf-8"))]
        except ValueError as broken:
            note(f"every job is in {name}", False, f"does not read to its end: {broken}")
            continue
        note(f"every job is in {name}", order == wanted, f"{len(order)} of {len(wanted)} jobs")
    worst, unbalanced = None, []
    balances = list(chain.from_iterable(map(_balances, jobs)))
    arms = len(balances)
    for share, gap, arm, place in balances:
        if not share <= 1:   # a gap past its allowance, or one that is not a number
            unbalanced.append(f"{arm} at {place}")
        if worst is None or share > worst[0]:
            worst = (share, gap, arm, place)
    if arms:
        note("money is conserved", not unbalanced,
             f"{arms} arm runs against S0; the largest gap between an arm's mean gain and the sum of its split by "
             f"outside flow is ${worst[1]:.3g} a person ({worst[2]} at {worst[3]}), {worst[0]:.3g} of its allowance"
             + (f"; past it: {', '.join(unbalanced[:5])}" if unbalanced else ""))
    else:
        note("money is conserved", False, "not checkable: no arm's gain against S0 is stored (S0 alone)")
    return dict(checks=checks, passed=all(check["passed"] for check in checks))


def _balances(job):
    """The conservation check of one job, for each arm run against S0: (share, gap, arm, job's key), the gap between
    the arm's mean gain and the sum of its split by outside flow, $ a person, and that gap as a share of its
    allowance (``CONSERVED_USD``).

    Example: a gain of $100.00 whose split sums to $100.0000001 has a gap of 1e-7, a tenth of the allowance of 1e-6
    (a billionth of $100 being smaller)."""
    place = key(job)
    out = []
    for arm, row in job["arms"].items():
        gain, parts = row["mean_gain_usd"], list(row["split"].values())
        gap = abs(gain - sum(parts))
        share = gap / max(CONSERVED_USD, CONSERVED_SHARE * max(abs(gain), sum(map(abs, parts))))
        out.append((share, gap, arm, place))
    return out


def _line(output, text):
    """One plain line in the map's progress file, with the time."""
    with _WRITING, (Path(output) / PROGRESS).open("a", encoding="utf-8") as target:
        target.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")


def run_part(output, seed_set, seed, passed):
    """One part: the population runner over ``seed`` alone into its folder, then its marker. A folder left without a
    marker is removed first. Returns (exit code, minutes)."""
    folder = part_folder(output, seed)
    if folder.exists():
        shutil.rmtree(folder)
    folder.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "run_economy_population.py"), "--seeds", seed_set,
               "--only-seeds", str(seed), "--output", str(folder.relative_to(ROOT)), *passed]
    began = time.perf_counter()
    with (folder.parent / f"seed_{seed}.log").open("w", encoding="utf-8") as log:
        code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    minutes = (time.perf_counter() - began) / 60
    if code == 0:
        (folder / COMPLETE).write_text(json.dumps(dict(seed=seed, exit_code=code, minutes=round(minutes, 2),
                                                       command=command[3:], at=time.strftime("%Y-%m-%d %H:%M:%S")),
                                                  indent=1), encoding="utf-8")
    return code, minutes


def passed_check(checked):
    """Whether the integrity record ``checked`` exists and says the part passed. A record that cannot be read, left
    half written by a run that stopped, counts as no check, so the part is checked again."""
    try:
        return bool(json.loads(checked.read_text(encoding="utf-8"))["passed"])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def same_map(passed):
    """The runner's options ``passed`` without those that set how many workers run a part (``WORKER_OPTIONS``, each
    with its value): they change how fast a map is made and nothing in it, so a map may be continued with another
    number of workers, as after a restart on a machine with less free memory."""
    kept, skip = [], False
    for item in passed:
        if skip:
            skip = False
        elif item in WORKER_OPTIONS:
            skip = True
        elif not item.startswith(tuple(option + "=" for option in WORKER_OPTIONS)):
            kept.append(item)
    return kept


def one_part(output, seed_set, seed, tasks, passed):
    """One part run where it is not complete, and its integrity checked where it is not yet: None, or why it failed.
    A complete part whose check passed is left as it is."""
    folder = part_folder(output, seed)
    checked = folder / INTEGRITY
    if (folder / COMPLETE).exists():
        if passed_check(checked):
            return None
        code, minutes = 0, None
    else:
        _line(output, f"seed {seed}: running {len(tasks)} jobs")
        code, minutes = run_part(output, seed_set, seed, passed)
    spent = "" if minutes is None else f" in {minutes:.1f} minutes"
    if code != 0:
        _line(output, f"seed {seed}: FAILED{spent}, exit code {code}; see {PARTS}/seed_{seed}.log")
        return f"Part seed_{seed} failed (exit code {code}): see {folder.parent / f'seed_{seed}.log'}"
    result = check_part(folder, seed_set, seed, tasks, code)
    whole = checked.with_name(checked.name + ".part")       # written under another name and renamed when whole
    whole.write_text(json.dumps(result, indent=1), encoding="utf-8")
    whole.replace(checked)
    failed = [check["check"] for check in result["checks"] if not check["passed"]]
    if failed:
        _line(output, f"seed {seed}: ran{spent}; integrity FAILED: {'; '.join(failed)}")
        return f"Part seed_{seed} failed its integrity check ({', '.join(failed)}): see {checked}"
    _line(output, f"seed {seed}: done{spent}, {len(tasks)} jobs, integrity passed")
    return None


def main():
    """Run, check and join the map named on the command line, or print its parts with --dry-run."""
    parser = options()
    ours, passed = parser.parse_known_args()
    args, parts = plan(ours.seeds, passed)
    output = (ROOT / ours.output).resolve()
    if not output.is_relative_to(ROOT):
        parser.error("--output must stay in this workspace")
    if ours.together < 1:
        parser.error("--together is the number of parts run at the same time, 1 or more")
    if ours.dry_run:
        print(json.dumps(dict(seed_set=ours.seeds, parts=len(parts), jobs=sum(len(tasks) for _, tasks in parts),
                              population=args.n, workers=args.workers, entry_reads=args.entry_reads,
                              output=str(output), passed_to_each_part=passed,
                              complete_already=[seed for seed, _ in parts
                                                if (part_folder(output, seed) / COMPLETE).exists()]), indent=1))
        for seed, tasks in parts:
            print(f"  part seed_{seed}: {len(tasks)} jobs, {sum(map(runs_in, tasks))} population runs")
        return
    output.mkdir(parents=True, exist_ok=True)
    record = dict(seed_set=ours.seeds, passed=passed)
    if (output / COMMAND).exists():
        begun = json.loads((output / COMMAND).read_text(encoding="utf-8"))
        if (begun.get("seed_set"), same_map(begun.get("passed", []))) != (ours.seeds, same_map(passed)):
            parser.error(f"{output} holds a map run with other options ({output / COMMAND}); use another folder")
    else:
        (output / COMMAND).write_text(json.dumps(record, indent=1), encoding="utf-8")
    stopped = threading.Event()

    def guarded(part):
        """One part, unless another has failed already; a failure stops the parts not yet started."""
        if stopped.is_set():
            return None
        failure = one_part(output, ours.seeds, *part, passed)
        if failure:
            stopped.set()
        return failure

    # In the set's order; with --together K, K at a time, each a process of its own.
    with ThreadPoolExecutor(max_workers=ours.together) as pool:
        failures = [failure for failure in pool.map(guarded, parts) if failure]
    if failures:
        sys.exit(failures[0])
    if not (output / JOINED).exists():
        _line(output, "joining the parts")
        began = time.perf_counter()
        join(output, figures=not ours.no_figures)
        _line(output, f"joined {len(parts)} parts in {(time.perf_counter() - began) / 60:.1f} minutes")
    print(f"The map is joined in {output}")


if __name__ == "__main__":
    main()

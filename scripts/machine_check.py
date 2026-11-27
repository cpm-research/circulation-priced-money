"""A short self-test of the machine and the installation, before any long run. Run through ./run.sh check, which
passes the number of workers. It simulates nothing that is kept: a few small worlds to prove the code runs here and
repeats itself, and one world of the run's real size to time it. Written for Linux; elsewhere it runs without the
readings of memory."""
import os
import platform
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import scipy

from cpm_abm.economy_abm import Economy, simulate
from cpm_abm.experiment import second_run
from cpm_abm.experiment.grid import cell_inputs

try:
    import resource
except ImportError:      # Windows has no such module
    resource = None

SEED = 20261021          # the first development seed
GB_A_WORKER = 3.0        # memory a worker is given at 4,000 people, GB (run.sh sets the workers by it)
DISK_GB = 100            # disk for the whole run, GB: the largest records are removed once they are read


def line(text=""):
    print(text, flush=True)


def memory():
    """(GB in all, GB free) on Linux, else None."""
    table = Path("/proc/meminfo")
    if not table.exists():
        return None
    rows = dict(row.split(":") for row in table.read_text().splitlines())
    return tuple(int(rows[name].split()[0]) / 1048576 for name in ("MemTotal", "MemAvailable"))


def world(n, months, burn_in, stress):
    """The second run's base model at ``n`` people, shortened to ``burn_in`` months before launch and ``months``
    after, the stress year starting ``stress`` months after launch."""
    settings = second_run.economy("base", "quote")
    settings.update(burn_in=burn_in, months=months, distress_start=stress)
    return replace(Economy(n=n, seed=SEED), distress=0.02, **settings)


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else os.cpu_count()
    ok = True
    free_disk = shutil.disk_usage(".").free / 2 ** 30
    held = memory()
    line("Second run: machine check")
    line(f"  system        {platform.system()} {platform.release()} on {platform.machine()}")
    line(f"  cores         {os.cpu_count()}")
    line(f"  memory        {held[0]:.0f} GB in all, {held[1]:.0f} GB free" if held else "  memory        not read")
    line(f"  disk here     {free_disk:.0f} GB free")
    line(f"  Python        {platform.python_version()}, NumPy {np.__version__}, SciPy {scipy.__version__}")
    line(f"  code          commit {os.environ.get('CPM_COMMIT', 'unknown')}")
    line(f"  workers       {workers}")
    line()

    line("1. Five small worlds (1,000 people, three years): does every arrangement run and keep its accounts?")
    small = world(1000, 24, 12, 12)
    inputs = cell_inputs(0.044)
    for arm in ("S0", "M0", "U", "M1", "M2"):
        start = time.perf_counter()
        series = simulate(inputs, 0.6, small, arm)["series"]
        # Wealth changes only through flows across the edge, write-off valuation, inflation and the monthly payout
        # that returns what crossed the edge.
        gap = float(np.max(np.abs(series["wealth_change"] - series["external"] - series["valuation"]
                                  - series["inflation"] - series["returned"])))
        good = gap < 1e-9
        ok = ok and good
        line(f"   {arm:<3} {time.perf_counter() - start:5.1f} s   accounts balance to {gap:.1e}   "
             f"{'ok' if good else 'FAILED'}")

    line("2. The same world twice: does it repeat itself exactly?")
    again = [simulate(inputs, 0.6, small, "M1") for _ in range(2)]
    same = all(again[0]["series"][key].tobytes() == again[1]["series"][key].tobytes() for key in again[0]["series"])
    same = same and again[0]["wealth"].tobytes() == again[1]["wealth"].tobytes()
    ok = ok and same
    line(f"   {'identical' if same else 'DIFFERENT: please report this'}")

    line("3. One world of the real size (4,000 people, four years): how fast is one core here?")
    timed = world(4000, 36, 12, 12)
    start = time.perf_counter()
    simulate(inputs, 0.6, timed, "M1")
    seconds = time.perf_counter() - start
    peak = f"; peak memory of this process {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20:.1f} GB" \
        if resource else ""
    line(f"   {seconds:.1f} seconds for 48 months{peak}")

    # One seed of the whole map, for one way savers read the pool: 6 rates x 7 launch levels x 4 arrangements, each
    # a shared first half and five second halves (3 runs' worth), plus banks for the 6 rates; each run is 360 months.
    runs = 6 * 7 * 4 * 3 + 6 * 3
    core_hours = runs * (seconds * 360 / 48) / 3600
    line()
    line("What this means for the run (both ways savers read the pool, so twice the above):")
    for label, seeds in (("development map, 3 seeds", 3), ("main run at 30 seeds", 30), ("main run at 40 seeds", 40)):
        total = 2 * seeds * core_hours
        line(f"   {label:<26} about {total:7.0f} core-hours, about {total / workers:6.1f} hours on {workers} workers")
    if held:
        enough = held[1] > workers * GB_A_WORKER
        line(f"   memory needed: about {workers * GB_A_WORKER:.0f} GB for {workers} workers "
             f"({'enough' if enough else 'NOT ENOUGH: use fewer workers'})")
    line(f"   disk needed: about {DISK_GB} GB for the development map, the main run and the side sets "
         f"({'enough' if free_disk > DISK_GB else 'LESS THAN THAT IS FREE HERE'})")
    line()
    line("RESULT: " + ("everything works here." if ok
                       else "SOMETHING FAILED. Please send this report back before running anything."))


if __name__ == "__main__":
    main()

# Running the second run on a Linux server

The second registered run (`docs/ANALYSIS_PLAN.md`, "The second run, registered 26 November 2026") is too large
for a laptop: about 60 core-hours a seed. `run.sh` in the repository's root runs all of it on one Linux server
from this folder alone, by one line. It installs nothing outside the folder, needs no administrator rights,
runs unattended and continues from where it stopped.

## The one line

```bash
git clone --depth 1 -b second-run-3 https://github.com/cpm-research/circulation-priced-money.git cpm && cd cpm && ./run.sh all
```

That is all there is to do. The line fetches the code into a new folder `cpm`, checks in a few seconds that the
machine can do the run, and starts the run in the background. It then shows the first minutes (setup and a
self-test) and says when the run is under way; the terminal can be closed at any moment, before or after that,
and the run goes on.

When the run has finished, everything to send back is in one folder, `cpm/send_back/`, and nowhere else.

## What the server needs

- Linux on x86-64 (or ARM64) with `bash`, `git`, `curl` and `tar`.
- The internet during the first minutes only (GitHub for the installer and Python, PyPI for the packages).
- Memory: 3 GB for each worker and 16 GB beside them. The script sets the number of workers from the cores and
  the free memory, so a machine with less memory runs fewer workers and takes longer.
- Disk: about 100 GB free in the folder. The largest record of a run, each person's failed payments by month on
  the development seeds, is read during the run and then compressed or removed, so the disk in use stays below
  that. The run's working files are kept in the folder too, not in the system's `/tmp`.

`all` checks these before it starts anything and says plainly which one is missing. The disk is asked for before
the first start only; `DISK_OK=1 ./run.sh all` starts on less.

## What `all` does

In the background, in this order, stopping with a plain message in its log if a step fails:

1. `setup`: Python 3.12 and the pinned packages, inside `.server/` (under a minute).
2. `check`: five small worlds and one of the real size (a few minutes). It writes `send_back/check_report.txt`:
   the machine, whether every arrangement runs and keeps its accounts, whether a world repeats itself exactly,
   and the speed of one core with the time the run will take here. If the check fails nothing is run.
3. The development map: three seeds, all 210 cells, both ways savers read the pool.
4. The side sets, each on its own few cells, on the same three seeds.
5. The count of confirmation seeds, computed from the development map by the registered rule and written into
   the code (`scripts/set_second_count.py`); nobody chooses it.
6. The main run on its own seeds, never run before.
7. The packing of the results into `send_back/`.

```bash
./run.sh status     # what is running and how far it is
./run.sh stop       # stop it; ./run.sh all continues from the last finished seed
```

## What comes back

`send_back/` holds four files once `status` says FINISHED:

| File | Contents |
|---|---|
| `MANIFEST.txt` | What the two archives hold, whether the run was complete when they were packed, any side set that did not finish, and the checksum of each file. |
| `cpm_summary.tar` | Every finished map's summary, the run's records and its logs. Small. |
| `cpm_results.tar` | The same, with every seed's readings and the monthly series. Roughly 10 to 15 GB. |
| `check_report.txt` | The self-test's report. |

The folder is also written once on the way, after the side sets, so that the development map and the side sets
can be sent back before the main run ends; `MANIFEST.txt` then says PARTIAL. Both archives unpack into one
folder, `cpm_second_run/`.

## How long it takes

On cores of the speed of the laptop the model was built on (27 seconds for a world of 4,000 people over 48
months), on about 96 of them:

| Step | Core-hours | Elapsed |
|---|---|---|
| Development map, 3 seeds | about 180 | about 5 hours |
| Side sets | about 250 | about 4 hours |
| Main run, 40 seeds | about 2,400 | about 30 hours |

`check` prints the speed of one core on the machine it runs on and the hours the run will take there. One seed of
a map is one task for each outside rate and launch level, 42 in all, so more workers than that on one seed would
stand idle: the script runs as many seeds at the same time as keep the workers busy (two on 96 cores). The
development map holds the most memory, since it keeps each person's failed payments by month, so it runs one
seed at a time with at most 42 workers.

## Workers

By default the script uses the cores less two, or fewer where memory is short (3 GB a worker). To set the number,
for example on a machine shared with others:

```bash
WORKERS=64 ./run.sh all
```

## If something stops

Every job survives a logout. A map runs one seed a part and each finished seed is kept, with a check that every
cell is there and that money is conserved. A map that stops, for want of memory for example, is started again by
the run itself after a minute, with half the workers and then a quarter; only after three stops does the run end.
After that, a reboot or `./run.sh stop`, give `./run.sh all` again
in the folder: setup and the self-test are not repeated, and finished seeds and finished maps are skipped. The
number of workers may differ from the first start. A side set that failed is not run again once the count of
confirmation seeds has been written, since that changes one line of the code; `MANIFEST.txt` names it.
`./run.sh status` shows the last lines of the job's log; the logs are in `.server/logs/` and each seed's own log
in `runs/<map>/parts/`.

Keep the whole run on one machine. Some library functions round differently from one processor to another, so a
map begun on one machine and continued on another could not be reproduced exactly.

## The steps one at a time

`./run.sh` without a command lists them: `setup`, `check`, `plan` (prints what each job would run and runs
nothing), `devmap`, `sides`, `main` and `pack`. `main` is refused until the development map has been joined, since
the count of its seeds comes from that map.

## What is where

| Path | Contents |
|---|---|
| `send_back/` | Everything to send back, and nothing else. |
| `runs/` | Each map as it runs: its parts, one a seed, and the joined stores; `second_confirmation_count.json`, the record of how the count was fixed. Large. |
| `.server/` | The installer, Python, the packages and the logs. |

None of these is tracked by git. Once the results have arrived, deleting the folder `cpm` removes everything the
script wrote.

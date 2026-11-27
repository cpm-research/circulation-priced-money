# Circulation-Priced Money: the model and the paper

Circulation-Priced Money (CPM) is a payment money whose holders pay a small holding charge, a demurrage. The proceeds go
to one liquidity pool owned by its users, and the pool lends short bridges and term loans against future
income, without collateral. This repository holds the agent-based model that tests the arrangement, the
paper that states it, and the tests that tie the two together.

The question: can CPM run itself with voluntary participants and leave every household group better off than
banks and cards, and than a best-case decentralised arrangement, and under which outside rates, launch
adoption and distress?

Research by Siddharth Totla, supervised by Claudio Tessone.

**Status.** Preliminary draft. The headline results and the registered claim are read on 30 confirmation seeds,
held back until the model was frozen and read once. The side checks, the bounds and the robustness sets are on
development seeds. The runs made after the confirmation was read, the rate cut and the side checks on side
seeds, are exploratory and are labelled so.

## Where to start

| Read | For |
|---|---|
| `paper/cpm.pdf` | The arrangement, the contract equation by equation, what it implies, the model, the claim and its limits |
| `docs/MODEL.md` | A short guide to the code: which module does what, in the order of events |
| `docs/DECISIONS.md` | Every rule in force, with its date and reason |
| `docs/ANALYSIS_PLAN.md` | The registered plan: the claim, its tests and the sample sizes |
| `docs/PARAMETERS.csv` | Every calibrated value under the code's own name, with its source |
| `docs/RUNNING_ON_A_SERVER.md` | The second run on a Linux server: setup, self-test, the maps and what comes back |

## Layout

| Folder | Contents |
|---|---|
| `src/cpm_abm/engine/` | The model: constants, settings, the population, the contract's arithmetic, and the world in the order of its events (16 modules) |
| `src/cpm_abm/experiment/` | The experiment: the grid, the jobs, the measured quantities, the statistics and the registered claim (11 modules) |
| `src/cpm_abm/` | `economy_abm.py` re-exports the engine under its older name; `core_model.py` holds the shared inputs; `comet.py` is the Compound III market in integer arithmetic; `catalogue.py` builds the parameter sweep with PySPG |
| `scripts/` | Command lines: the population map, one arrangement with figures, stress checks, the region figures, and the rebuild of the paper's numbers, tables and figures |
| `tests/` | The test suite, among it conservation of money in every arrangement, each contract equation against a run, and the parameter table against the code |
| `paper/` | The paper's source and the compiled draft |
| `docs/` | The decision register, the analysis plan, the parameter table and the calibration sources |
| `data/raw/` | The Compound III snapshot and the Federal Reserve series the calibration reads, checked by byte hashes |
| `results/` | The stored results the paper reads, compressed |
| `vendor/pyspg/` | The pinned PySPG release, with its licence |

## Install

Python 3.12.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lock.txt
```

On Linux and macOS the interpreter is `.venv/bin/python`, and the path separator in `PYTHONPATH` below is `:`.

## Check

```bash
PYTHONPATH="src;." .venv/Scripts/python -X utf8 -m unittest discover -s tests -t .
```

The whole suite takes about fifteen minutes. The two tests that tie the paper to the code take half a minute:

```bash
PYTHONPATH="src;." .venv/Scripts/python -X utf8 -m unittest tests.test_contract_equations tests.test_parameters
```

## Run

One job is one cell of the grid and one seed, run under all five arrangements on the same people and the
same random draws. At 4,000 people a job takes a few minutes; the full map of 105 cells on three seeds takes
about two hours on twelve cores.

```bash
# What a command would run, without running it
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_economy_population.py --seeds development --r_out 0.044 --a0 0.2 --distress 0 0.02 --output results/two_cells --dry-run

# Two cells: outside rate 4.4%, 20% of people in the network at launch, no distress and 2 points of distress
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_economy_population.py --seeds development --r_out 0.044 --a0 0.2 --distress 0 0.02 --output results/two_cells --workers 12

# The whole development map
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_economy_population.py --seeds development --output results/development_map_rerun --workers 12
```

A run writes `summary.json` (every cell's readings and the claim), `cells.json` (every seed), `measures.json`
(monthly series) and `failure_counts.json`, each with the hash of every source file that produced it. Each worker
needs about 1.5 GB at 4,000 people; twelve is the default limit, and `--most-workers` raises it on a larger
machine.

## Run the confirmation

The confirmation map is 30 seeds over the whole grid, 3,180 jobs and about 17 hours on twelve cores, run under the
quote rule (savers enter on the pool's published quote) and again under the record rule (they enter on its
realised twelve-month return). It runs one seed at a time: each seed is a part, written to
`parts/seed_<seed>/` in the output folder when it is done, and between parts only its integrity is checked (the run
exited cleanly, every job of the grid is there, money is conserved). After the last part the parts are joined into
the four stores one run over the 30 seeds writes, and the map is read once. A stopped run is restarted by running the
same command again: complete parts are kept and the rest run. `progress.txt` in the output folder has a line for each
part.

```bash
# The parts it would run, running nothing
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_quote --workers 12 --dry-run

# The quote rule: entrants read the pool's quote
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_quote --workers 12

# The record rule: entrants read the pool's realised return
PYTHONPATH="src;." .venv/Scripts/python -X utf8 scripts/run_confirmation.py --seeds confirmation --output runs/confirmation_realised --workers 12 --entry-reads realised
```

`scripts/join_parts.py --output <folder>` joins the parts on its own.

## The second run

A second run is registered in `docs/ANALYSIS_PLAN.md` ("The second run, registered 26 November 2026") and has not
been run. It is a new version of the model and of the claim; the paper and the results in this repository are the
first run's.

What changes: money is conserved (what households pay to lenders returns to households each month, so a long run
can settle), each run covers 25 years with a stress year ten years after launch, and the grid has six outside
rates and 210 cells. In it the DeFi arrangement (`M0`) is stablecoin payments with no yield and no credit. The
claim is registered anew, on seeds never used. Every change is a setting of the model
whose default is the first run's rule, so the first run's results rebuild from this code unchanged. The second
run's settings and side sets are in `src/cpm_abm/experiment/second_run.py`, each with its reason in
`docs/DECISIONS.md`, and `--second-run base` selects them in both runners.

The run takes about 60 core-hours a seed. One command, `./run.sh all`, runs all of it unattended on a Linux
server and leaves everything to send back in one folder, `send_back/` (`docs/RUNNING_ON_A_SERVER.md`).

## From the stored results to the paper

The results the paper reads are in `results/`, compressed (`results/README.md` lists them). `paper/README.md` maps
each table and figure of the paper to the function that writes it and the results it reads. The monthly series of
the three largest maps, about a gigabyte, are attached to the release `draft-2026-11` and have to be downloaded before
the rebuild; `results/README.md` gives the three commands.

```bash
# Every number, table and figure of the paper, with a report tracing each number to its stored field
.venv/Scripts/python -X utf8 scripts/rebuild_paper.py

# The paper
cd paper && tectonic cpm.tex
```

## How the paper and the code are kept the same

- **Equations.** Each equation of the contract names the function that computes it. `tests/test_contract_equations.py`
  runs the model and recomputes every equation, month by month, from the model's own records. Appendix B of
  the paper lists equation, function and test.
- **Parameters.** `tests/test_parameters.py` fails if any value in `docs/PARAMETERS.csv` differs from the code.
- **Numbers.** The headline results and every results table reach the paper through macros and table bodies that
  `scripts/paper_numbers.py` writes from a stored result, and `paper/numbers_report.txt` traces each to its stored
  field. `tests/test_paper_map.py` checks the map from tables and figures to that code.
- **Money.** Every flow has a payer and a receiver. The suite checks, every month and in every arrangement,
  that the change in households' net wealth equals the recorded flows to and from the outside.

## The five arrangements

| Name in the paper | Name in the code | What it is |
|---|---|---|
| Banks and cards | `S0` | Bank money, cards with limits, cash advances, outside lenders |
| Best-case DeFi | `M0` | A yield-bearing stablecoin for payments; its loan needs collateral worth more than the loan, so it covers no shortfall |
| Pool without the charge | `U` | The payment money and the pool, with no holding charge |
| CPM | `M1` | The payment money, the pool and the holding charge |
| Indexed CPM | `M2` | CPM with the contract in purchasing-power terms |

## Cite

`CITATION.cff` holds the citation: Siddharth Totla, "Circulation-Priced Money: a holding charge that pays for
pooled liquidity", preliminary draft, November 2026, https://github.com/cpm-research/circulation-priced-money.

## Licence

- The code, the documents in `docs/` and the stored results are under the MIT licence (`LICENSE`).
- The paper in `paper/` is under CC BY 4.0 (`paper/LICENSE.md`).
- `vendor/pyspg/` holds PySPG by Claudio J. Tessone, which the model uses to enumerate the grid, and a
  compatibility layer derived from it. Both keep PySPG's own licence, the GNU General Public License
  (`vendor/pyspg/upstream/LICENCE`), with which the MIT licence is compatible.
- `data/raw/` holds third-party data as supplied, a snapshot of the Compound III market read from the public
  chain and series published by the Federal Reserve, under their sources' terms.

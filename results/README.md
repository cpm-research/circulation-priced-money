# Stored results

The results the paper reads, compressed. `python scripts/rebuild_paper.py` rebuilds every number, table and figure
of the paper from them; no simulation is needed.

Three kinds of result are here, each on its own seeds, all at 4,000 people.

- **Confirmation**: the whole grid on 30 seeds held back until the model was frozen (20261401 to 20261430), run
  twice, with savers acting on the pool's published quote and on its realised record. The registered claim is
  read on these.
- **Development**: three seeds (20261021 to 20261023) on which the model was built, with the bounds, the side
  checks and the robustness sets of `docs/ROBUSTNESS_PLAN.md` (section 6), and eight separate seeds for the size
  check.
- **Exploratory**: runs made after the confirmation was read (`docs/ANALYSIS_PLAN.md`, the additions of 17 and 18
  November 2026), on seeds from 20261601: the rate cut and the exploratory side checks. No clause of the claim
  reads them.

| Folder | What it is | Stores |
|---|---|---|
| `confirmation_quote/` | The whole grid on the 30 confirmation seeds, savers acting on the published quote: the map the headline numbers and the registered claim are read from | summary, cells, measures, failure counts |
| `confirmation_realised/` | The same map on the same seeds with savers acting on the pool's realised twelve-month record | summary, cells, measures, failure counts |
| `rate_cut/` | Exploratory: outside rates of 2.5, 3 and 3.5% over the seven launch levels and five distress levels, 26 of 30 exploratory seeds (four set aside, named in `run_records/set_aside.json`) | summary, cells, measures, failure counts |
| `explore_base/`, `explore_*/` | Exploratory: six cells (outside rate 4.4%; launch 5%, 20%, 60%; distress 0 and 2 points) on three side seeds at the build's settings, and with one setting changed: the fixed cost at 10, 100 and 1,000 times, the custody cost, the owners' spread, the date of the shock; and outside rates of 0.5 and 1% | summary, cells, measures |
| `development_map/` | The whole grid: 3 outside rates, 7 launch levels, 5 distress levels, 3 seeds, 5 arrangements | summary, cells, measures |
| `bound_loan_losses/` | The same map with every lender, the pool included, losing and pricing the published charge-off rates | summary |
| `bound_interest_returned/` | The same map with outside lenders' interest and card fees handed back to households | summary |
| `side_*/` | Nine reruns of three cells (outside rate 4.4%; launch 5%, 20%, 60%; distress 0 and 2 points), one setting changed in each | summary |
| `size_500/` to `size_8000/` | The same three cells at five population sizes, eight seeds each | summary, cells |
| `population_network/` | The wage network of one population draw: 4,000 people at the first confirmation seed, who pays a wage to whom, with each person's spending and card holding. Written by `scripts/population_network.py`, which builds the population and runs no day of the economy | network |
| `records_base/` | The six side-check cells with the base settings, written with the settlement records (own shortfall and knock-on, dependence on netting) | summary, cells, measures |
| `robust_buffer_review_050/`, `robust_buffer_review_0153/` | The same six cells with half, and 15.3%, of people re-choosing their cash buffer each month | summary, cells, measures |
| `robust_threshold_uniform_check/` | Outside rate 4.4%, launch 20%, no distress, joining by thresholds drawn uniformly (the base's mean chance) | summary, cells, measures |
| `robust_threshold_*/` | Outside rate 4.4%, no distress, seven launch levels, joining by threshold: measured thresholds, and a common threshold of 0.1, 0.2 and 0.3 | summary, cells, measures |
| `robust_ring*/` | The same cells with sellers on a ring: local share 1 or 0.35, linear or threshold joining, launch scattered or in one neighbourhood (the base rule at 0 and 2 points) | summary, cells, measures |
| `robust_hubs*/` | The same cells with hub sellers: linear or measured-threshold joining, launch scattered or with the largest sellers (the base rule at 0 and 2 points) | summary, cells, measures |
| `robust_stress_boundary/` | Outside rate 4.4%; launch 20, 30, 45%; distress 0 and 1.6 to 1.9 points in steps of 0.1 | summary, cells, measures |

A robustness folder the paper lists that is not here is a set still running; its numbers print as placeholders
until it is shipped.

## The stores

- `summary.json.gz`: one record per cell (seed means, the claim's clauses, the region) and the run's settings,
  inputs and constants.
- `cells.json.gz`: one record per cell and seed.
- `measures.json.gz`: monthly series and circulation records per cell and seed.
- `spread.json.gz` (the development map only): the spread of distress to people not laid off, the excess failed
  shares at each distress level over the same seed's level 0 and the part of it on people no extra layoff hit,
  written from the run's `failure_counts.json` by `scripts/spread_of_distress.py`.
- `CARD.md`: the results card, written by `scripts/results_card.py` and rewritten by `scripts/rebuild_paper.py`. It
  gives the same rows in the same order for every folder (setup, participation, failed payments, the gains, the
  holding charge, the pool, distress, circulation, chains of failure, the claim), each number with the stored field
  it came from, and says "not stored" or "not in this run" where a row does not apply, so any two runs can be read
  side by side. `python scripts/results_card.py <folder>` writes the card of a run as the runner writes it.

The runner also writes `failure_counts.json`, the count of failed payments by person and month. It is several
gigabytes for a whole map on the development seeds and is not shipped; any rerun writes it again.

`python scripts/pack_results.py <run folder> <name>` copies a finished run's summary, cells and measures into
`results/<name>/` in this form, compressed with no time or file name in the header, so the same run gives the same
bytes.

The monthly series (`measures`) and the failure counts of the three 30-seed maps, `confirmation_quote/`,
`confirmation_realised/` and `rate_cut/`, are about a gigabyte together. They are not in the repository: they are
the three files attached to its release `draft-2026-11`, one for each map. Download them into the repository's top
folder and unpack each into `results/`:

```bash
gh release download draft-2026-11 --pattern "*.large.tar"
for f in *.large.tar; do tar -xf "$f" -C results; done
python scripts/pack_results.py --check --complete
```

Without the GitHub command line, the three files are on the release's page, https://github.com/cpm-research/circulation-priced-money/releases/tag/draft-2026-11.
`SHA256SUMS` lists every file inside them, so the last command checks the copy, and
`python scripts/rebuild_paper.py` says which files it needs when they are not there. Everything else the paper
reads is here.

No file here is larger than 50 MB. A store whose compressed copy would be larger is shipped as volumes,
`<store>.json.gz.1of6` to `.6of6`: the store's bytes cut into equal slices, each slice a complete gzip stream. The
paper's scripts read the volumes as they are, and joined in order they are one gzip file of the whole store
(`cat measures.json.gz.*of* > measures.json.gz`). The paper rebuilt from volumes was compared with the paper
rebuilt from whole files on the development results: 77 output files, none differing.

`SHA256SUMS` lists the SHA-256 of every store, volume and run record in this folder, in the format of
`sha256sum`. `python scripts/pack_results.py --check` compares the files with it and names any that changed or
is absent; `--sums` writes the list again after a store is added.

## Provenance

Each store carries the hashes of the source files that produced it. The development map, its bound maps, the
nine side checks and the size check were produced before the model was arranged into the modules of
`src/cpm_abm/engine` and `src/cpm_abm/experiment`, so those hashes name the earlier single files. The modular code
reproduces the results exactly: three cells of the map (18 jobs, 356,670 stored values) were rerun on it and
compared value by value, with no difference. The records run and the robustness sets were run on the modular code
with the settlement records and the switches of `docs/ROBUSTNESS_PLAN.md`, every switch off except the one a set
names; the stress boundary set's level-0 jobs repeat cells of the development map, and the paper's report
(`paper/numbers_report.txt`) compares them value by value. The commit recorded inside a store belongs to the
working history and is not part of this repository.

The free-text notes inside the stores made before 16 November 2026 (the development map, its two bound maps, the
nine side checks and the size check) were brought, on 22 November 2026, to the wording the code has written
since. A value-by-value comparison of each store before and after found every number, key and list unchanged.

## Rerunning

```bash
# three cells, about seven minutes on twelve cores
PYTHONPATH="src;." python -X utf8 scripts/run_economy_population.py --seeds development \
    --r_out 0.044 --a0 0.05 0.2 0.6 --distress 0.0 0.02 --output results/three_cells --workers 12

# the whole development map, about two hours on twelve cores
PYTHONPATH="src;." python -X utf8 scripts/run_economy_population.py --seeds development \
    --output results/development_map_rerun --workers 12
```

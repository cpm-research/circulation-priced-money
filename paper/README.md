# The paper

**Circulation-Priced Money: a holding charge that pays for pooled liquidity.**
Preliminary draft, November 2026. The headline results and the registered claim are read on the confirmation
seeds. Side checks and robustness sets are on development seeds, and runs made after the confirmation was read
are exploratory; each is labelled so.

| File | What it holds |
|---|---|
| `cpm.tex` | Title, abstract, sections 1 to 4 (introduction, the arrangement, the contract, what the contract implies), the conclusion, the appendices' frame and the references |
| `sections/model.tex` | Section 5, the model, in the order of the ODD protocol |
| `sections/measurement.tex` | Section 6, the experiment, the measured quantities, the registered claim and the sample sizes |
| `sections/results.tex` | Section 7, the results on the confirmation map: what the arrangement does, what demurrage does, the registered claim and where it ends |
| `sections/robustness.tex` | Section 8, the checks that stand beside the map: side checks and bounds, exploratory side checks, the update scheme, the adoption rule and network, chains of failure, population size |
| `sections/limits.tex` | Section 9, each limit with the direction it leans |
| `sections/appendix_parameters.tex` | The parameter table, the reader's form of `docs/PARAMETERS.csv` |
| `numbers.tex` | One macro for each number the text quotes, written by `scripts/paper_numbers.py` from a stored result |
| `tables/` | The tables' bodies, written by the same script |
| `numbers_report.txt` | Every number and table cell with the stored field it was read from |
| `figures/` | The figures, drawn by `scripts/paper_figures.py` from the same result |
| `cpm.pdf` | The compiled draft |

## How the paper is tied to the code

- Each equation of section 3 names the function that computes it, and `tests/test_contract_equations.py`
  recomputes it from a run's own records. Appendix B lists equation, function and test.
- `docs/PARAMETERS.csv` holds every calibrated value under the code's own name, and `tests/test_parameters.py`
  fails if a value in it differs from the code.
- The headline results and every results table come through the macros of `numbers.tex` and the files of `tables/`.
  A few numbers in the robustness and limits sections are typed from the stored results.
- Text in red square brackets marks a passage that waits for a run still to be made.

## Tables and figures

Each table and figure of the paper, in the order of the source, with the function that writes it and the folders
of `results/` it reads. Tables are written by `scripts/paper_numbers.py` and figures by `scripts/paper_figures.py`;
`scripts/rebuild_paper.py` calls both with the folders below. `tests/test_paper_map.py` fails if a table or figure
of the source is missing here, is numbered differently or names a function that is not in its script.

| | Label | File | Written by | Reads |
|---|---|---|---|---|
| Figure 1 | `fig:mechanism` | drawn in the source; a diagram of the arrangement | | |
| Table 1 | `tab:arms` | typed; the five arrangements and their names in the code | | |
| Table 2 | `tab:notation` | typed; the notation | | |
| Table 3 | `tab:onepage` | typed; the model on one page | | |
| Figure 2 | `fig:wagenet` | `figures/fig_wage_network.pdf` | `fig_wage_network` | `population_network` |
| Table 4 | `tab:outcomes` | typed; the measured quantities | | |
| Figure 3 | `fig:grid` | `figures/fig_grid.pdf` | `fig_grid` | `confirmation_quote`, `rate_cut` |
| Table 5 | `tab:arrangements` | `tables/arrangements.tex` | `arrangements_table` | `confirmation_quote` |
| Figure 4 | `fig:failed` | `figures/fig_failed_payments.pdf` | `fig_failed_payments` | `confirmation_quote` |
| Figure 5 | `fig:gains` | `figures/fig_gains.pdf` | `fig_gains` | `confirmation_quote` |
| Table 6 | `tab:gains` | `tables/gains.tex` | `gains_table` | `confirmation_quote` |
| Table 7 | `tab:sources` | `tables/sources.tex` | `sources_table` | `confirmation_quote` |
| Figure 6 | `fig:sources` | `figures/fig_sources.pdf` | `fig_sources` | `confirmation_quote` |
| Table 8 | `tab:chargegain` | `tables/chargegain.tex` | `charge_gain_table` | `confirmation_quote`, `confirmation_realised` |
| Figure 7 | `fig:chargegain` | `figures/fig_charge_gain.pdf` | `fig_charge_gain` | `confirmation_quote`, `confirmation_realised` |
| Table 9 | `tab:buys` | `tables/buys.tex` | `buys_table` | `confirmation_quote` |
| Table 10 | `tab:charge` | `tables/charge.tex` | `charge_table` | `confirmation_quote` |
| Figure 8 | `fig:charge` | `figures/fig_charge.pdf` | `fig_charge` | `confirmation_quote` |
| Table 11 | `tab:circulation` | `tables/circulation.tex` | `circulation_table` | `confirmation_quote` |
| Figure 9 | `fig:circulation` | `figures/fig_circulation.pdf` | `fig_circulation` | `confirmation_quote` |
| Table 12 | `tab:docking` | `tables/docking.tex` | `docking_table` | `confirmation_quote` |
| Figure 10 | `fig:participation` | `figures/fig_participation.pdf` | `fig_participation` | `confirmation_quote` |
| Table 13 | `tab:owners` | `tables/owners.tex` | `owners_table` | `confirmation_quote` |
| Table 14 | `tab:region` | `tables/region.tex` | `region_table` | `confirmation_quote` |
| Figure 11 | `fig:region` | `figures/fig_region.pdf` | `fig_region` | `confirmation_quote` |
| Table 15 | `tab:cut` | `tables/cut.tex` | `cut_table` | `confirmation_quote`, `rate_cut` |
| Table 16 | `tab:lending` | `tables/lending.tex` | `lending_table` | `confirmation_quote`, `rate_cut` |
| Figure 12 | `fig:lowrates` | `figures/fig_low_rates.pdf` | `fig_low_rates` | `confirmation_quote`, `rate_cut` |
| Figure 13 | `fig:stress` | `figures/fig_stress_boundary.pdf` | `fig_stress_boundary` | `confirmation_quote` |
| Table 17 | `tab:stress` | `tables/stress.tex` | `stress_table` | `confirmation_quote` |
| Table 18 | `tab:readings` | `tables/readings.tex` | `readings_table` | `confirmation_quote`, `confirmation_realised` |
| Table 19 | `tab:path` | `tables/path.tex` | `path_table` | `confirmation_quote`, `confirmation_realised` |
| Figure 14 | `fig:path` | `figures/fig_path.pdf` | `fig_path` | `confirmation_quote`, `confirmation_realised` |
| Table 20 | `tab:side` | `tables/side.tex` | `side_table` | `development_map`, `side_*`, `robust_buffer_review_*` |
| Table 21 | `tab:bounds` | `tables/bounds.tex` | `bounds_table` | `development_map`, `bound_*` |
| Table 22 | `tab:boundary` | `tables/boundary.tex` | `boundary_table` | `development_map`, `robust_stress_boundary` |
| Table 23 | `tab:explore` | `tables/explore.tex` | `explore_tables` | `explore_base`, `explore_*` |
| Table 24 | `tab:spiral` | `tables/spiral.tex` | `explore_tables` | `explore_base`, `explore_fixed_cost_*` |
| Table 25 | `tab:lowrates` | `tables/lowrates.tex` | `explore_tables` | `explore_base`, `explore_low_rates` |
| Table 26 | `tab:periodtwo` | `tables/periodtwo.tex` | `period_two_table` | `development_map` |
| Table 27 | `tab:robust` | `tables/robustness.tex` | `robust_table` | `development_map`, `robust_threshold_*`, `robust_ring*`, `robust_hubs*` |
| Figure 15 | `fig:robustpaths` | `figures/fig_robust_paths.pdf` | `fig_robust_paths` | `development_map`, `robust_threshold_*`, `robust_ring*`, `robust_hubs*` |
| Figure 16 | `fig:thresholdmap` | `figures/fig_threshold_map.pdf` | `fig_threshold_map` | `development_map`, `robust_threshold_*` |
| Table 28 | `tab:chains` | `tables/chains.tex` | `chain_table` | `records_base` |
| Table 29 | `tab:spread` | `tables/spread.tex` | `spread_table` | `development_map` (`spread.json.gz`) |
| Figure 17 | `fig:size` | `figures/fig_size_check.pdf` | `fig_size_check` | `size_500` to `size_8000` |
| Table 30 | `tab:ledger` | typed; each identity names the test that checks it | | |
| Table 31 | `tab:code` | typed; each equation names its function and its test in `tests/test_contract_equations.py` | | |
| Table 32 | `tab:parameters` | typed from `docs/PARAMETERS.csv`, which `tests/test_parameters.py` checks against the code | | |

`tables/region_majority.tex` and `figures/fig_network.pdf` are also written and are not used in this draft.

## Rebuild

```bash
python scripts/rebuild_paper.py
cd paper && tectonic cpm.tex
```

The first command writes `numbers.tex`, `tables/`, `numbers_report.txt` and `figures/` from the results stored in
`results/`. Tectonic 0.17 or any recent LaTeX with `amsmath`, `booktabs`, `tabularx`, `longtable` and `tikz`
compiles the paper.

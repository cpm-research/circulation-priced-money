# A guide to the model's code

The model is described in full, in the order of the ODD protocol, in section 5 of the paper
(`paper/sections/model.tex`), and the contract it runs is stated equation by equation in section 3
(`paper/cpm.tex`). This page is the map from that description to the code. The rules in force, each with its
date and reason, are in `docs/DECISIONS.md`; every calibrated value is in `docs/PARAMETERS.csv`.

## Units, time and names

- Money is in months of mean consumer-unit spending; one unit is $6,440. Rates are a month unless a name says
  otherwise.
- A month has 30 days. A run is a burn-in of six months under bank rules, shared by every arrangement,
  then 60 months after launch.
- The five arrangements keep their short names in the code: `S0` banks and cards, `M0` best-case DeFi, `U`
  the pool without the holding charge, `M1` CPM, `M2` indexed CPM.
- `P` is the payment money, `E` bank money. The pool's capital is `N`, its target `N*` (`Q` in the code), the
  holding charge `c`, coverage `coverage`, the bridge price `r_b`, the gross bridge coupon `r_g`.

## The engine, `src/cpm_abm/engine/`

One class, the world, holds every account. It is composed of one part per module, and the modules follow the
order of events.

| Module | What it holds | In the paper |
|---|---|---|
| `constants.py` | The calendar and every sourced or declared number, with its source | Appendix C |
| `settings.py` | The settings of one run: population size, calendar, switches, the stress | Sections 5 and 6 |
| `population.py` | Who the people are: wealth, spending, income, cards, scores, jobs, billing dates | Initialisation |
| `rates.py` | Outside rates, charge-off rates and the contract's arithmetic: the quote, the issuer's share, owners' returns | Section 3 |
| `lending_rules.py` | The buffer a person chooses from its own last month, and the most the pool lends a payer | Adaptation; the pool's lending |
| `ledger.py` | The record tables, the order in which payments are made, the age of every unit of money | Appendix A |
| `world_state.py` | Opening every account; net wealth; the loan book | Entities and state variables |
| `world_month.py` | The month's start: layoffs, obligations, credit requests, and the pool's terms (`_cycle_terms`) | Schedule, steps 1 to 3; equations of section 3 |
| `world_dealing.py` | The monthly dealing: buffers, entry to and exit from the pool, joining and leaving the network | Schedule, step 4; entry and exit |
| `world_day.py` | Each day in its fixed order: wages, arrears, instalments, settlement, failures | Schedule, step 5 |
| `world_payments.py` | How money moves: receipts, budgets, fees, paying, repaying, collecting what is due | Settlement and failed payments |
| `world_credit.py` | The card, the day's interest and costs, lendable cash, loan losses and write-offs | Cards; loss learning |
| `world_close.py` | The month's close: the reserve return, the charge paid to the pool, owners' income, the records | Schedule, step 7 |
| `world.py` | The composed world, one month, one run, and `simulate`, the entry point | |
| `measures.py` | Inequality, wallet turnover and the velocity measures read from the records | |

`src/cpm_abm/economy_abm.py` re-exports every name of the engine, so `from cpm_abm.economy_abm import
simulate, Economy` works as it did when the engine was one file.

## The experiment, `src/cpm_abm/experiment/`

| Module | What it holds | In the paper |
|---|---|---|
| `notes.py` | The grid's values, the arrangements, the stored series, the claim's levels and margins | Section 6, the experiment |
| `grid.py` | The seed sets, the confirmation count, the seed planner, the jobs (through PySPG) | Sample sizes |
| `jobs.py` | Running one job and many: the shared run of the bank arrangement and the fork at the distress year | Common random numbers |
| `accounts.py` | One run's accounts: real cost, transfers, failure counts, the pool and its owners | Outcomes |
| `gains.py` | Paired differences between arrangements: the gains, the complete gain, the cash-advance bound | Outcomes; bounds |
| `statistics.py` | Intervals (t, bootstrap, Wilson), the Bonferroni level, the seeds a margin needs | Sample sizes |
| `region.py` | Persistence, the falsifiers and the verdict of each cell | The claim |
| `claims.py` | The registered claim, clause by clause, the stress legs and the region | The claim |
| `store.py` | Writing a result and reading one back | |

## Reading one rule

To follow one rule from the paper to the code and back:

1. Find its equation in section 3 of the paper, and its row in Appendix B.
2. Open the function the row names. Its docstring states the rule in plain words, with the date it was
   decided.
3. Open the test the row names in `tests/test_contract_equations.py`. It recomputes the equation from a run's
   own records.

## What the model does not contain

Total spending is fixed. There is no production, growth or wider-economy effect, no unemployment insurance,
and no mortgages. The calibration is stylised United States data. Section 8 of the paper states each limit
and the direction in which it leans.

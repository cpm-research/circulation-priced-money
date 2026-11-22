"""The economy engine, one idea per module.

The model itself, its order of events and its records are described in the docstring of
``cpm_abm.economy_abm``, which re-exports every name defined here so that older imports keep working.
This is the code map.

Inputs
    constants.py       the calendar and every sourced or declared number, with its source
    settings.py        the Economy settings: population size, calendar, switches, stresses, the legacy rules
    population.py      who the people are: wealth, spending, income, cards, scores, jobs, spells, billing dates

Pure rules and helpers the world calls
    rates.py           outside rates and prices, charge-off rates, and the contract's arithmetic (capital limit,
                       issuer share, the pool's quote, owners' realised returns)
    lending_rules.py   the buffer choice (each person's month replayed from each candidate buffer) and the most
                       the pool lends a payer so that its receipts repay it
    network.py         the robustness switches' fixed network (ring places, hub weights), joining thresholds, sellers
                       and launch set, all off by default
    ledger.py          the record tables (obligations, requests, the loan book), the order payments are made in,
                       and the age of every unit of money (Coinage, a record for MicroVelocity)

The world, one class composed of one mixin per module, in the order of events
    world_state.py     opening every account, net wealth and the loan book
    world_month.py     the month's start: layoffs, line cuts, obligations and term requests, the pool's terms
    world_dealing.py   the monthly dealing: buffers, owners' entry and exit, joining and leaving P, issuer tests
    world_day.py       each day in its fixed order: wages accrued, arrears, instalments, term purchases,
                       settlement and failure counts
    world_payments.py  what a day reads and how money moves: receipts and budgets, the cost test, fees, paying,
                       repaying, collecting what is due, overdue wages
    world_credit.py    the outside card, the day's interest and costs, lendable cash, loan losses and write-offs
    world_close.py     the month's close: reserve return, owners' income, the pool's margin, the records
    world.py           run and month, the composed class ``_World`` and ``simulate``, the public entry point

Reading the records
    measures.py        inequality, wallet turnover, MicroVelocity and holding velocity
"""

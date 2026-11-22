"""The population map's experiment, one idea per module.

The command line, scripts/run_economy_population.py, describes the map, its options and what each store holds, and
re-exports every name defined here so that older imports keep working. This is the code map, in the order the
modules import one another.

    notes.py        the grid's values, the arms, the series and measures stored, the claim's levels, and every note
                    stored with the results
    statistics.py   intervals: Wilson, t and bootstrap, the Bonferroni level, the three-way reading, the seeds a
                    margin needs, pooled spreads, connected blocks, and the dip under distress
    grid.py         the seed sets and the confirmation count (its one definition) with the seed planner, each cell's
                    inputs, the selected cells and the jobs (the pinned PySPG catalogue)
    accounts.py     one run's accounts: the gain split, the real part, transfers, records by class, failure counts,
                    the pool and its owners, the monthly series, liquidity and demurrage over the windows
    gains.py        paired differences between arms: harm groups, the complete gain, the cash-advance bound, the
                    dispersion, and an arm's row
    region.py       per-cell seed means, the paired distress reading, the region verdict, "worse than M0", and
                    ``decide``
    claims.py       the registered claim: clauses (a) to (e), stress legs, the falsifier and the region by distress
                    slice
    store.py        writing the stores and reading a stored map back
    jobs.py         running one job and many: the shared S0 cache, the distress fork and their identity check
"""

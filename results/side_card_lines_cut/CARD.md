# Results card: side_card_lines_cut

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 6 cells: r_out 4.4% x a0 0.05,0.2,0.6 x distress 0,2 pt |  | summary.json cells |
| Setup | Seeds | 3 (development: 20261021, 20261022, 20261023) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | card_line_cut True |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.194 (0.047 to 0.603) | 0.194 (0.047 to 0.603) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | not stored | not stored | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | not stored | not stored | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | not stored | not stored | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.61% | 6.37% | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.53% (3.43% to 3.58%) | 6.15% (5.90% to 6.25%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.31% (1.90% to 2.82%) | 4.80% (4.58% to 4.97%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.23% (1.70% to 2.77%) | 4.61% (4.54% to 4.92%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.21% (1.68% to 2.76%) | 4.53% (4.49% to 4.92%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $243 ($119 to $465) | $215 ($114 to $380) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $546 ($280 to $969) | $586 ($357 to $886) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $124 ($62 to $226) | $119 ($71 to $179) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $414 ($216 to $704) | $462 ($300 to $623) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.140% (0.132% to 0.142%) | 0.328% (0.226% to 0.343%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $4.8 ($2.8 to $6.8) | $6.9 ($4.6 to $6.9) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.10% (2.05% to 2.13%) | 2.08% (2.07% to 2.15%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.70% (6.69% to 6.76%) | 6.73% (6.72% to 6.79%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.921 (0.892 to 0.921) | 0.758 (0.500 to 0.914) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.999 (0.992 to 1.004) | 0.887 (0.706 to 0.994) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.01% (-0.02% to 0.62%) | -0.12% (-0.14% to 0.39%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | -1.10 (-1.10 to -0.22) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | -0.90 (-1.00 to 0.18) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | not stored | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not stored | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not stored | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | not stored | not stored | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | not stored | not stored | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | not stored | not stored | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | not stored | not stored | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | not stored | not stored | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | not stored | not stored | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | not stored | not stored | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

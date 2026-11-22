# Results card: side_fixed_cost_low

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 6 cells: r_out 4.4% x a0 0.05,0.2,0.6 x distress 0,2 pt |  | summary.json cells |
| Setup | Seeds | 3 (development: 20261021, 20261022, 20261023) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | fixed_cost 'low' |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.194 (0.047 to 0.603) | 0.194 (0.047 to 0.603) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | not stored | not stored | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | not stored | not stored | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | not stored | not stored | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.61% | 5.70% | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.53% (3.43% to 3.58%) | 5.50% (5.28% to 5.59%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.31% (1.88% to 2.82%) | 4.31% (4.11% to 4.50%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.21% (1.71% to 2.76%) | 4.23% (4.07% to 4.44%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.21% (1.71% to 2.76%) | 4.10% (4.01% to 4.42%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $244 ($119 to $465) | $217 ($116 to $379) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $551 ($281 to $966) | $558 ($332 to $837) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $124 ($62 to $226) | $121 ($72 to $177) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $419 ($217 to $701) | $435 ($275 to $578) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.140% (0.131% to 0.142%) | 0.311% (0.201% to 0.320%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $4.8 ($2.7 to $6.8) | $6.1 ($4.3 to $6.6) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.08% (2.04% to 2.12%) | 2.11% (2.05% to 2.15%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.69% (6.69% to 6.74%) | 6.71% (6.70% to 6.77%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.920 (0.890 to 0.920) | 0.770 (0.465 to 0.921) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.999 (0.989 to 1.005) | 0.906 (0.706 to 0.994) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.01% (-0.03% to 0.62%) | -0.08% (-0.13% to 0.28%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | -0.48 (-0.62 to 0.71) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | -0.32 (-0.55 to 1.01) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
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

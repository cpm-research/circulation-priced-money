# Results card: explore_shock_month_36

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 6 cells: r_out 4.4% x a0 0.05,0.2,0.6 x distress 0,2 pt |  | summary.json cells |
| Setup | Seeds | 3 (side: 20261631, 20261632, 20261633) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | distress_start 36 |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.199 (0.046 to 0.599) | 0.199 (0.046 to 0.599) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.278 (0.090 to 0.685) | 0.278 (0.090 to 0.685) | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.488 (0.241 to 0.833) | 0.488 (0.241 to 0.833) | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.693 (0.448 to 0.918) | 0.689 (0.447 to 0.912) | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.61% | 5.04% | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.56% (3.46% to 3.60%) | 4.93% (4.79% to 5.01%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.36% (1.96% to 2.81%) | 3.73% (3.71% to 4.00%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.25% (1.83% to 2.77%) | 3.70% (3.62% to 3.95%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.26% (1.96% to 2.76%) | 3.86% (3.67% to 3.94%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $245 ($114 to $452) | $213 ($109 to $396) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $547 ($274 to $934) | $509 ($299 to $830) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $125 ($60 to $217) | $108 ($64 to $184) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $419 ($220 to $677) | $389 ($251 to $578) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.139% (0.135% to 0.150%) | 0.201% (0.198% to 0.244%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $4.7 ($2.7 to $7.1) | $4.9 ($3.6 to $7.0) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.12% (2.10% to 2.13%) | 2.16% (2.14% to 2.17%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.86% (6.76% to 6.93%) | 6.89% (6.79% to 6.95%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.917 (0.909 to 0.925) | 0.699 (0.632 to 0.898) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 1.002 (0.992 to 1.003) | 0.839 (0.805 to 0.985) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.01% (-0.01% to 0.11%) | -0.30% (-0.33% to -0.01%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | 0.10 (-0.36 to 0.57) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | 0.17 (-0.33 to 0.72) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | 0 (0 to 1) | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not stored | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not stored | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 27.1 (24.4 to 28.4) | 34.8 (29.7 to 37.4) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 12.01 (11.07 to 13.29) | 16.51 (15.03 to 18.36) | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.243 (0.243 to 0.244) | 0.245 (0.244 to 0.248) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 0.51% | 0.71% | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 0.44% (0.38% to 0.46%) | 0.62% (0.60% to 0.75%) | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 5.4 (3.2 to 11.5) | 17.0 (5.4 to 27.1) | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | 0.000% | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

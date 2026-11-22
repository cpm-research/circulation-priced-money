# Results card: robust_hubs_threshold_measured

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 7 cells: r_out 4.4% x a0 0.05,0.1,0.2,0.3,0.45,0.6,0.8 x distress 0 pt |  | summary.json cells |
| Setup | Seeds | 3 (development: 20261021, 20261022, 20261023) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | joining 'threshold'; thresholds 'measured'; sellers 'hubs' |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.296 (0.047 to 0.807) | not in this run | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.486 (0.172 to 0.856) | not in this run | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.751 (0.553 to 0.931) | not in this run | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.879 (0.780 to 0.964) | not in this run | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 5.09% | not in this run | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 4.99% (4.87% to 5.07%) | not in this run | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 3.28% (3.18% to 3.49%) | not in this run | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 3.12% (3.08% to 3.43%) | not in this run | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 3.08% (3.01% to 3.39%) | not in this run | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $381 ($249 to $530) | not in this run | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $856 ($573 to $1,130) | not in this run | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $191 ($128 to $250) | not in this run | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $658 ($454 to $824) | not in this run | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 7 of 7 | not in this run | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 7 of 7 | not in this run | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.204% (0.187% to 0.221%) | not in this run | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $8.9 ($8.2 to $9.8) | not in this run | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.19% (2.16% to 2.25%) | not in this run | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.83% (6.78% to 6.92%) | not in this run | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.809 (0.726 to 0.905) | not in this run | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.937 (0.893 to 0.993) | not in this run | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | 0.06% (-0.34% to 0.95%) | not in this run | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | not in this run | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | not in this run | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | not in this run | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not in this run | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not in this run | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not in this run | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not in this run | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 25.5 (23.1 to 28.0) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 13.27 (12.94 to 13.78) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.298 (0.297 to 0.300) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 1.38% | not in this run | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 1.07% (0.99% to 1.15%) | not in this run | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 18.1 (12.6 to 27.4) | not in this run | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | not in this run | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

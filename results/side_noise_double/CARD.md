# Results card: side_noise_double

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 6 cells: r_out 4.4% x a0 0.05,0.2,0.6 x distress 0,2 pt |  | summary.json cells |
| Setup | Seeds | 3 (development: 20261021, 20261022, 20261023) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | leave_noise 2.0 |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.194 (0.047 to 0.603) | 0.194 (0.047 to 0.603) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | not stored | not stored | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | not stored | not stored | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | not stored | not stored | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.61% | 5.70% | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.54% (3.43% to 3.58%) | 5.50% (5.28% to 5.59%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.28% (1.84% to 2.81%) | 4.43% (4.15% to 4.50%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.20% (1.70% to 2.76%) | 4.21% (4.06% to 4.45%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.20% (1.70% to 2.76%) | 4.19% (4.06% to 4.46%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $243 ($119 to $460) | $216 ($115 to $371) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $551 ($281 to $962) | $562 ($327 to $825) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $125 ($62 to $222) | $121 ($72 to $169) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $422 ($218 to $698) | $439 ($271 to $567) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.140% (0.132% to 0.142%) | 0.311% (0.203% to 0.320%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $4.8 ($2.8 to $6.8) | $6.2 ($4.3 to $6.6) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.10% (2.06% to 2.13%) | 2.13% (2.06% to 2.18%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.70% (6.70% to 6.76%) | 6.71% (6.70% to 6.79%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.915 (0.870 to 0.920) | 0.755 (0.461 to 0.908) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 1.000 (0.985 to 1.002) | 0.898 (0.706 to 0.995) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.01% (-0.02% to 0.62%) | -0.06% (-0.11% to 0.29%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | -0.45 (-0.60 to 0.75) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | -0.30 (-0.53 to 1.06) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
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

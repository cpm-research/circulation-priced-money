# Results card: confirmation_realised

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 105 cells: r_out 2,4.4,6% x a0 0.05,0.1,0.2,0.3,0.45,0.6,0.8 x distress 0,0.5,1,1.5,2 pt |  | summary.json cells |
| Setup | Seeds | 30 (confirmation: 20261401, 20261402, 20261403, 20261404, 20261405, 20261406, 20261407, 20261408, 20261409, 20261410, 20261411, 20261412, 20261413, 20261414, 20261415, 20261416, 20261417, 20261418, 20261419, 20261420, 20261421, 20261422, 20261423, 20261424, 20261425, 20261426, 20261427, 20261428, 20261429, 20261430) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | entry_reads 'realised' |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.302 (0.050 to 0.801) | 0.302 (0.050 to 0.801) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.397 (0.099 to 0.846) | 0.397 (0.099 to 0.846) | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.610 (0.252 to 0.915) | 0.610 (0.252 to 0.914) | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.772 (0.452 to 0.947) | 0.725 (0.439 to 0.898) | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.65% (3.58% to 3.69%) | 5.93% (5.76% to 6.06%) | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.58% (3.26% to 3.63%) | 5.73% (5.16% to 5.89%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 3.35% (2.71% to 3.54%) | 5.60% (4.92% to 5.85%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.86% (2.34% to 3.26%) | 5.22% (4.85% to 6.16%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.84% (2.38% to 3.17%) | 5.16% (4.95% to 6.08%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $217 ($72 to $526) | $152 ($56 to $432) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $375 ($191 to $888) | $350 ($172 to $779) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $90 ($48 to $147) | $61 ($41 to $105) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $278 ($175 to $440) | $220 ($86 to $320) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 21 of 21 | 21 of 21 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 21 of 21 | 21 of 21 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.085% (0.029% to 0.145%) | 0.108% (0.023% to 0.255%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $3.1 ($1.1 to $5.6) | $2.5 ($0.7 to $4.1) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.41% (2.19% to 2.77%) | 2.62% (2.36% to 3.06%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 11.43% (5.16% to 57.19%) | 11.44% (5.19% to 57.42%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.518 (0.288 to 0.741) | 0.227 (0.085 to 0.538) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.774 (0.653 to 0.906) | 0.484 (0.403 to 0.694) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.12% (-0.29% to -0.03%) | -0.21% (-0.41% to -0.05%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | 0.44 (-0.13 to 1.16) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | 0.79 (-0.05 to 1.42) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | 29 (20 to 30) | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not stored | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not stored | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 26.5 (23.9 to 29.5) | 26.3 (22.7 to 29.9) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 12.04 (11.07 to 13.87) | 19.25 (17.70 to 22.26) | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.245 (0.244 to 0.246) | 0.250 (0.247 to 0.251) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 0.53% (0.52% to 0.53%) | 0.82% (0.80% to 0.84%) | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 0.48% (0.46% to 0.59%) | 0.79% (0.75% to 0.94%) | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 11.9 (3.8 to 24.1) | 22.7 (8.5 to 37.1) | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | 0.000% | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | 9 of 21 | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | 2 of 21 | not in this run | summary.json cells[].M1.claim.all |

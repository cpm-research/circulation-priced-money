# Results card: rate_cut

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 105 cells: r_out 2.5,3,3.5% x a0 0.05,0.1,0.2,0.3,0.45,0.6,0.8 x distress 0,0.5,1,1.5,2 pt |  | summary.json cells |
| Setup | Seeds | 26 (exploratory: 20261601, 20261602, 20261604, 20261605, 20261606, 20261607, 20261608, 20261609, 20261610, 20261612, 20261613, 20261614, 20261615, 20261616, 20261617, 20261618, 20261619, 20261620, 20261622, 20261623, 20261624, 20261625, 20261626, 20261627, 20261628, 20261629) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | none |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.300 (0.052 to 0.800) | 0.300 (0.052 to 0.800) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.393 (0.100 to 0.847) | 0.393 (0.100 to 0.847) | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.609 (0.255 to 0.927) | 0.609 (0.255 to 0.926) | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.783 (0.463 to 0.963) | 0.750 (0.462 to 0.912) | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.63% (3.62% to 3.64%) | 5.87% (5.83% to 5.91%) | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.61% (3.47% to 3.64%) | 5.80% (5.55% to 5.88%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.59% (2.26% to 2.88%) | 5.29% (4.67% to 6.30%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.56% (2.18% to 2.83%) | 5.11% (4.59% to 6.33%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.54% (2.20% to 2.83%) | 5.23% (4.58% to 6.40%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $243 ($91 to $428) | $173 ($83 to $332) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $555 ($241 to $872) | $381 ($263 to $663) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $139 ($60 to $205) | $87 ($62 to $147) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $452 ($216 to $628) | $307 ($198 to $430) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 21 of 21 | 21 of 21 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 21 of 21 | 21 of 21 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.101% (0.080% to 0.119%) | 0.181% (0.102% to 0.280%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $3.6 ($1.7 to $5.6) | $3.6 ($2.6 to $5.2) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.09% (2.07% to 2.11%) | 2.12% (2.09% to 2.22%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 5.32% (4.81% to 5.84%) | 5.35% (4.83% to 5.88%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.811 (0.568 to 0.908) | 0.442 (0.241 to 0.864) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.967 (0.852 to 1.009) | 0.699 (0.571 to 0.965) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | 0.04% (-0.05% to 0.14%) | -0.02% (-0.20% to 0.11%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | 0.88 (-0.54 to 2.00) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | 0.96 (-0.51 to 2.08) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | 19 (0 to 23) | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not stored | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not stored | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 26.8 (22.6 to 29.8) | 24.6 (19.3 to 29.7) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 13.33 (11.23 to 15.38) | 23.12 (18.61 to 26.66) | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.244 (0.243 to 0.246) | 0.249 (0.244 to 0.254) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 0.55% | 0.84% (0.84% to 0.85%) | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 0.48% (0.45% to 0.60%) | 0.89% (0.72% to 1.11%) | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 10.0 (3.3 to 32.8) | 32.1 (7.3 to 54.2) | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | 0.000% | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

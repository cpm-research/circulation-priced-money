# Results card: explore_fixed_cost_x100

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 6 cells: r_out 4.4% x a0 0.05,0.2,0.6 x distress 0,2 pt |  | summary.json cells |
| Setup | Seeds | 3 (side: 20261631, 20261632, 20261633) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | fixed_cost 'times100' |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.199 (0.046 to 0.599) | 0.199 (0.046 to 0.599) | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.276 (0.083 to 0.688) | 0.276 (0.083 to 0.688) | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.486 (0.213 to 0.836) | 0.486 (0.212 to 0.836) | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.692 (0.408 to 0.922) | 0.691 (0.408 to 0.921) | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.61% | 5.89% | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.56% (3.46% to 3.60%) | 5.73% (5.51% to 5.84%) | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.23% (1.40% to 3.12%) | 3.49% (2.22% to 5.00%) | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.10% (1.38% to 3.05%) | 3.36% (2.19% to 4.86%) | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.12% (1.36% to 3.06%) | 3.38% (2.19% to 4.87%) | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $201 ($68 to $417) | $206 ($70 to $422) | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $515 ($162 to $1,016) | $666 ($233 to $1,235) | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $81 ($14 to $182) | $113 ($31 to $227) | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $388 ($109 to $759) | $547 ($186 to $982) | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 3 of 3 | 3 of 3 | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.118% (0.082% to 0.119%) | 0.282% (0.244% to 0.304%) | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $4.3 ($1.6 to $6.4) | $7.0 ($3.0 to $9.7) | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 23.08% (10.76% to 67.23%) | 13.09% (6.23% to 37.25%) | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 30.43% (17.56% to 84.59%) | 19.91% (12.67% to 49.80%) | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.977 (0.976 to 0.980) | 0.971 (0.968 to 0.973) | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 1.029 (1.004 to 1.061) | 1.026 (1.006 to 1.077) | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | 1.40% (0.75% to 4.74%) | 1.44% (1.29% to 3.35%) | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | -1.45 (-2.19 to -0.67) | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | -1.33 (-1.89 to -0.61) | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | 0 | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not stored | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not stored | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not stored | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 26.9 (25.5 to 28.9) | 27.5 (26.2 to 29.5) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 10.81 (10.53 to 11.10) | 17.29 (16.65 to 18.17) | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.243 (0.241 to 0.244) | 0.241 (0.240 to 0.243) | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 0.51% | 0.82% | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 0.37% (0.29% to 0.47%) | 0.52% (0.39% to 0.69%) | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 3.4 (2.7 to 4.4) | 5.5 (4.5 to 7.8) | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | 0.000% | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

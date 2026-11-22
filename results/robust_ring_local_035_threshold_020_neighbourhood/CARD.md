# Results card: robust_ring_local_035_threshold_020_neighbourhood

Written by `scripts/results_card.py` from the stored files of this folder. A row with several cells gives the median over them and, in brackets, the lowest and highest cell.

| Section | Row | No distress | 2 points | Stored field |
|---|---|---|---|---|
| Setup | Cells | 7 cells: r_out 4.4% x a0 0.05,0.1,0.2,0.3,0.45,0.6,0.8 x distress 0 pt |  | summary.json cells |
| Setup | Seeds | 3 (development: 20261021, 20261022, 20261023) |  | summary.json seeds |
| Setup | People | 4,000 |  | summary.json economy.n |
| Setup | Settings that differ from the base | joining 'threshold'; thresholds 0.2; sellers 'ring'; local_share 0.35; launch 'neighbourhood' |  | summary.json economy, fixed_cost |
| Participation | CPM at launch | 0.300 (0.050 to 0.800) | not in this run | summary.json cells[].M1.A_launch |
| Participation | CPM at month 12 | 0.493 (0.076 to 0.855) | not in this run | measures.json jobs[].monthly.M1.A[11], seed mean |
| Participation | CPM at month 36 | 0.776 (0.144 to 0.936) | not in this run | measures.json jobs[].monthly.M1.A[35], seed mean |
| Participation | CPM at month 60 | 0.901 (0.497 to 0.969) | not in this run | measures.json jobs[].monthly.M1.A[59], seed mean |
| Failed payments | Banks and cards, % of spending, years 4 and 5 | 3.65% | not in this run | summary.json cells[].S0_failures_pct |
| Failed payments | Best-case DeFi, % of spending, years 4 and 5 | 3.50% (3.39% to 3.63%) | not in this run | summary.json cells[].M0.failures_pct |
| Failed payments | Pool without the holding charge, % of spending, years 4 and 5 | 2.12% (2.07% to 3.00%) | not in this run | summary.json cells[].U.failures_pct |
| Failed payments | CPM, % of spending, years 4 and 5 | 2.09% (1.97% to 2.96%) | not in this run | summary.json cells[].M1.failures_pct |
| Failed payments | Indexed CPM, % of spending, years 4 and 5 | 2.08% (1.91% to 2.95%) | not in this run | summary.json cells[].M2.failures_pct |
| Gain | CPM over banks and cards, money, $ a person a year | $379 ($93 to $514) | not in this run | summary.json cells[].M1.against.S0.gain_usd_a_year |
| Gain | CPM over banks and cards, completed purchases counted | $791 ($222 to $1,025) | not in this run | summary.json cells[].M1.against.S0.complete_gain.face.gain_usd_a_year |
| Gain | CPM over best-case DeFi, money | $174 ($53 to $229) | not in this run | summary.json cells[].M1.against.M0.gain_usd_a_year |
| Gain | CPM over best-case DeFi, completed purchases counted | $566 ($178 to $696) | not in this run | summary.json cells[].M1.against.M0.complete_gain.face.gain_usd_a_year |
| Gain | Cells where the money gain over banks and cards is positive | 7 of 7 | not in this run | summary.json cells[].M1.against.S0.gain_usd_a_year > 0 |
| Gain | Cells where the money gain over best-case DeFi is positive | 7 of 7 | not in this run | summary.json cells[].M1.against.M0.gain_usd_a_year > 0 |
| Charge | Holding charge c, % a year | 0.132% (0.121% to 0.142%) | not in this run | summary.json cells[].M1.c_pct |
| Charge | What it costs a person, $ a year, years 4 and 5 | $6.0 ($2.2 to $6.8) | not in this run | summary.json cells[].M1.demurrage.charges_usd_a_year[1] |
| Charge | Bridge price with the charge (CPM), % a year | 2.08% (2.04% to 2.13%) | not in this run | summary.json cells[].M1.r_b_pct |
| Charge | Bridge price without it (the pool without the charge) | 6.74% (6.71% to 6.75%) | not in this run | summary.json cells[].U.r_b_pct |
| Charge | Bridges served under CPM, years 4 and 5 | 0.791 (0.686 to 0.891) | not in this run | summary.json cells[].M1.bridges_drawn_over_wanted |
| Pool | Pool capital over its target | 0.955 (0.906 to 0.999) | not in this run | summary.json cells[].M1.N / .M1.N_star |
| Pool | Owners' return less their alternative, % a year, years 4 and 5 | -0.04% (-0.07% to 0.11%) | not in this run | summary.json cells[].M1.owners_excess_pct.W2.mean |
| Distress | Dip against banks and cards, failed payments a person a year | not in this run | not in this run | summary.json cells[].M1.stress_leg.dip.against_S0.mean |
| Distress | Dip against best-case DeFi | not in this run | not in this run | summary.json cells[].M1.stress_leg.dip.against_M0.mean |
| Distress | Seeds in a cell with a pool run (bridges served below 0.6) | not in this run | not in this run | cells.json jobs[].arms.M1.bridges_drawn_over_wanted |
| Distress | Excess failed shares, Banks and cards, a person a year, months 25 to 60 | not in this run | not in this run | spread.json cells[].arms.S0.excess, seed mean |
| Distress | Excess failed shares, CPM, a person a year, months 25 to 60 | not in this run | not in this run | spread.json cells[].arms.M1.excess, seed mean |
| Distress | Share of it on people not hit, Banks and cards, wide reading | not in this run | not in this run | spread.json cells[].arms.S0.others / .excess |
| Distress | Share of it on people not hit, CPM, wide reading | not in this run | not in this run | spread.json cells[].arms.M1.others / .excess |
| Circulation | CPM, mean holding time of money spent, days, years 4 and 5 | 26.2 (23.6 to 31.4) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.participants.mean_tau[3:5] |
| Circulation | CPM, aggregate velocity, turns a year | 13.30 (10.90 to 13.49) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.<both groups>.sum and .people |
| Circulation | CPM, MicroVelocity's top tenth's share | 0.244 (0.243 to 0.245) | not in this run | measures.json jobs[].series.M1.holding_velocity.lifo.participants.top_tenth_share[3:5] |
| Chains | Knock-on share of failed value, Banks and cards | 0.55% | not in this run | measures.json jobs[].monthly.S0.knock_on / (own_shortfall + knock_on) |
| Chains | Knock-on share of failed value, CPM | 0.44% (0.40% to 0.50%) | not in this run | measures.json jobs[].monthly.M1.knock_on / (own_shortfall + knock_on) |
| Chains | Payers with a knock-on failure a day, CPM | 14.1 (3.1 to 20.9) | not in this run | measures.json jobs[].monthly.M1.knock_on_n / days |
| Chains | Completed cash-route value resting on netting, CPM | 0.000% | not in this run | measures.json jobs[].monthly.M1.netting_value / cash_completed |
| Claim | Cells stable on a majority of seeds, as built (a whole map only) | not in this run | not in this run | summary.json cells[].M1.region.verdict_majority |
| Claim | Cells passing the registered claim (a whole map only) | not in this run | not in this run | summary.json cells[].M1.claim.all |

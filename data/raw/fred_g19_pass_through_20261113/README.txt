FRED series behind Economy.vehicle_pass_through and Economy.personal_pass_through, fetched 13 Nov 2026, each
from https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=2021-01-01&coed=2024-12-01 (files as served).
RIFLPBCIANM60NM: Fed G.19, finance rate on new-car loans at commercial banks, 60-month term, % a year (quarterly,
  observed in Feb, May, Aug, Nov).
RIFLPBCIANM72NM: the same, 72-month term. TERMCBAUTO48NS: the same, 48-month term.
TERMCBPER24NS: Fed G.19, finance rate on 24-month personal loans at commercial banks, % a year (same months).
TB3MS: three-month Treasury bill, secondary market, monthly mean, discount basis, % a year.
Pass-through, February 2022 to February 2024 (nine quarterly observations, each with the same month's bill):
change in the loan rate over change in the bill, 60-month new car (8.22 - 4.52) / (5.24 - 0.33) = 0.754;
24-month personal (12.49 - 9.39) / (5.24 - 0.33) = 0.631. Least-squares slopes over the nine: 0.736 (OLS se 0.059)
and 0.657 (OLS se 0.075).

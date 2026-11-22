"""Population map at N = 4,000 (``POPULATION``, decided 12 Nov) over r_out x a0 x distress: M0, U, M1 and
M2 against S0, with the region reading and the registered claim's statistics (``claim_statistics``).

The (r_out, a0, distress, seed) sweep is a PySPG catalogue (`cpm_abm.catalogue`): the full cross of 3 r_out, 7 a0 and
5 distress levels, 105 cells (decided 31 Oct). Run from the repository root, only by a deliberate decision, naming
the seed set; ``--timing`` runs one job, prints how long the whole run would take, and writes nothing; ``--dry-run``
builds the job list and prints the jobs, seeds, cells, workers, population and output folder, running nothing:
    python -X utf8 scripts/run_economy_population.py --seeds confirmation --output results/YYYY-MM-DD_population_map
    python -X utf8 scripts/run_economy_population.py --seeds confirmation --timing
    python -X utf8 scripts/run_economy_population.py --seeds confirmation --output results/YYYY-MM-DD_map --dry-run
A job that fails stops the run with its cell and seed named. ``--only-seeds`` runs some seeds of the set only, a part
of the map whose stores say so; the confirmation map runs one seed a part (scripts/run_confirmation.py), and its parts
are joined into the map (scripts/join_parts.py), the stores one run over all the seeds would write.

``--r_out``, ``--a0`` and ``--distress`` select cells of the grid, each defaulting to all its values (the 3 Nov review):
only the selected cells run and are decided, and the recirculation set below runs with the full grid only. Step 2 of
the 3 Nov round adds ``--r_out 0.044 --a0 0.6 --distress 0 0.02`` on the development seeds: 6 jobs and 30 runs.
``--arms S0`` runs S0 alone in each job, without the other arms: the S0 check of Step 3 is ``--arms S0 --a0 0.6
--distress 0 0.01 0.02`` on the development seeds, 27 runs. After the stores are written the region figures are drawn
from them (``scripts/run_region_figures.py``), each figure the store can support.

Seeds (decided 31 Oct; new blocks 3 and 12 Nov): "development" is the three seeds used so far, kept
for development checks; "confirmation" is the first n seeds from 20261401, never run and never used in development,
with n = 30 in CONFIRMATION_COUNT (decided 17 Nov 2026: the planner's count, ``confirmation_seeds``, with each
reading's spread at the upper end of its one-sided interval at assurance 0.8; the planner names any cell that 30
seeds leave underpowered, and the one declared extension takes those cells to 60 seeds; with no count a run with
--seeds confirmation is refused, ``seeds_for``). At most 12
workers run by default, since more ran out of
memory on a 31 GB laptop; ``--most-workers M`` raises that limit on a machine with about 1.5 GB for every worker,
and more workers than the limit are refused. The blocks 20261101 to
20261120, 20261201 to 20261220 and 20261301 to 20261308 are retired (``RETIRED_SEEDS``); "sweep" records the last,
which the 12 Nov size sweep used.

Each job is one (r_out, a0, distress, seed). It runs S0, M0 (the strongest real DeFi, decided 5 Nov: USDC at the
bill less the Sky Savings Rate's spread under it, two legs of Base gas a payment, conversion at no fee, and no
collateral lending: collateral lending by Compound III is not run or reported, ``CRYPTO_SHARE`` 0, decided 12 Nov,
since real DeFi lends only against collateral worth more than the loan, which is not everyday credit), U, M1 and M2 on common random numbers, so every arm faces the same people, obligations
and draws, layoffs included. No cell has a provider fee (decided 5 Nov: P payments run on stablecoin rails, one
transfer's gas a P payment, ``engine_inputs``). The pool's fixed cost is sourced (decided 5 Nov): Aave's 2025 paid
service providers over US consumer units, $0.18 a consumer unit a year, with ``--fixed-cost low`` (Compound, $0.10) and
``high`` (Sky, $0.50) beside it (``FIXED_COST``). M0's rates move with r_out one for one from their observed October
2026 levels (decided 5 Nov, ``economy_abm.m0_rates``), with ``--m0-rates fitted``, the lag-3 OLS lines, beside it.
The issuer is a pure custodian (decided 5 Nov): it holds no pool shares and no support fund, so households alone
own the pool, and owners leave by the users' rule.
M1 and M2 run competitive P with demurrage (decided 5 Nov), which pays for the liquidity the pool keeps available;
U is the same P with no demurrage, so M1 against U on the same draws is what demurrage adds. Demurrage replaced the
reserve pass-through, so the check that passing reserve income never lowers the issuer's income has nothing to check
and is gone. With the full grid a second set repeats the
baseline cell (r_out = 4.4%, a0 = 0.6) with outside lenders' interest recirculated to households (the stress
convention). ``--lenders-interest returned`` (decided 12 Nov) instead runs every job of the requested grid with
that interest returned to households in proportion to spending, adds no extra set, and the stores, the region reading
and the figures are produced as for any map, the run record and its provenance saying so.

For every arm and cell it reports:

* the gain against S0 after 60 months (mean, median, share better off) and participation at launch, in years 2 and 3
  (W1) and in years 4 and 5 (W2);
* per job, each arm's paired differences against S0, for U, M1 and M2 against M0 too, and for M1 against U (what
  demurrage adds, 4 Nov) (decided 3 Nov): the real saving line by line and the gain, overall, by harm group,
  quintile, billing cycle and class (card holding x income source, decided 4 Nov), with the share worse off, $ a
  person a year after launch, so intervals across seeds need no rerun; each cell holds their seed means. The gains are
  read in full (decided 5 Nov: M2's indexation is the holder's own yield, not an issuer transfer). Beside the
  wealth gain, the complete gain claim (d) reads (decided 11 Nov), at both ends with the same breakdowns, its
  parts, and each group's difference in sales, so any surplus share can be read later; and, reported and not tested,
  the gain by the arm's own role in W2;
* for U, M1 and M2 the region reading (5 Nov, ``region``): whether the cell is in the stable region, its pool forming
  and persisting, the issuer staying and every group's lower bound of its mean complete gain (decided 11 Nov: the
  wealth change plus purchases received, sellers' extra sales at face value and at zero) at or above -$2 a person a
  year against S0 at both ends and against M0 at face (claim (d); decided 11 Nov, second round: the value of
  completed trade is not assumed, and against DeFi the result is a break-even value), with each yardstick's
  break-even surplus share on the bounds and on the means, the means, each part, the same reading on the wealth gain
  alone and the bare-majority reading beside. Owners' return less their alternative stays reported only, and the
  entry rule's quote and realised readings (``Economy.entry_reads``) are run as bounds at confirmation;
* liquidity in every arm (5 Nov, ``liquidity``), by window: the total precautionary money (households' buffers and
  the pool's idle cash, with idle P beside), the shortfall bridges covered and the money held per dollar of it, and
  failed payments;
* for U, M1 and M2 demurrage by window (5 Nov, ``demurrage``): the issuer's derived share of the reserve return, the
  yield on wallet P before demurrage, the reserve return on the pool's own cash, what the issuer keeps, demurrage, the
  coupon cut it paid and the capital cost of bridging, $ a person a year; and the issuer's complete wallet;
* the gain split exactly by the conservation identity (wealth changes only through outside flows, write-off
  valuation and CPI): outside interest, penalties, card, conversion and pool costs no longer paid, card rewards,
  extra savings and Comet yield received, and the rest;
* the issuer's reserve income ($ per capita over 60 months), reported apart: like S0's banks it sits outside the
  household economy (the boundary rule, decided 31 Oct), so no "system gain" adds it;
* the headline real part (decided 31 Oct and 1 Nov): the real resources each arm's intermediation uses, at the
  same sourced rate for the same service whoever provides it, and each arm's saving against S0; with the pool's
  priced costs against the sourced cost of its own lending, a gap the headline does not credit;
* beside it, the transfers: what households pay each intermediary outside the economy, net of what it pays back,
  against the real cost of its service, the margin going to its owners; and these payments by launch-wealth
  quintile;
* the cash check: households' money (E and P) at launch, at the end and at its lowest after launch, for everyone and
  for the half holding least, with each arm's end against S0's;
* the contract's state in W2: pool capital N and its limit N*, demurrage c on wallet P, its coverage of the
  bridging capital cost and its share theta of bridging finance, the bridging rate r_b, the coupon r_g and the
  published quote, and the share of bridges wanted the pool drew;
* for U, M1 and M2 the issuer's stay test (decided 30 Oct): the share of seeds in which it would leave (falsifier
  X6, which the cell's verdict names, with M2's declared limit at zero real rates) and the most annual expense it
  could bear, $ per person and as a share of P outstanding;
* for U, M1 and M2 backing (decided 30 Oct): the lowest ratio of reserves to P owed since launch over the cell's
  seeds (below 1 fires the unsafe falsifier) and the issuer's owners' backing top-ups, $ per capita over 60 months;
* for U, M1 and M2 the persistence tests, falsifiers and verdict, with worse-than-M0 decided against the paired M0
  run:
  - trade: in W2, failed-trade share no higher than M0's. Under the spending rule every arm owes the same
    spending, so the completed value is at least M0's exactly when the failed share is no higher;
  - no systematic harm: no position group (launch-wealth quintile x short (1-15 days) or long (30-60 days)
    billing cycle) has a median real-wealth change against M0 below -2% of its median starting wealth (any loss
    when that median is not positive);
  - "systematically" is read as for harm: worse in at least 80% of the cell's paired seeds. The falsifier fires
    if trade or any group fails that way.
  "Supports CPM" also needs credit cost and investor return against M0; the verdict string still says they are not
  computed (kept unchanged), and beside it ``better_than_M0`` now computes both from the stored parts (V2, borrowers'
  credit cost; V4, owners' realised return against DeFi's savings rate), so a configuration with no falsifier is
  still reported as persistent without "better than M0" established in its verdict;
* for U, M1 and M2 the yardsticks (decided 3 and 4 Nov), which claim (a) reads across seeds in Step 7: the pool's
  own margin (persistence test 4 and falsifier 3, read on months households hold pool capital) and the joint
  issuer-and-pool test by window, $ a person a year, with each seed's W2 value; the 90% household reading on capital
  net of queued exits, with all pool capital beside it (households alone own the pool, decided 5 Nov); whether P
  routes through W2; and in each cell the share of seeds that pass each;
* beside the majority verdict, the share of seeds whose own verdict is Persistent (every persistence test holds and
  no falsifier fires, worse than M0 counting in a seed where the cell is systematically worse and that seed is
  worse) with its 95% (Wilson) interval (decided 31 Oct; the 3 Nov review); a cell Persistent by majority says in
  how many seeds a falsifier fired;
* failure fees and new failed payments (a re-queued wage not counted again) by launch-wealth quintile, $ a person a
  year after launch (the 31 Oct review);
* in failure_counts.json (decided 3 Nov), each job's failed bills and wages after launch in every arm, a person a
  month, in fee units, unpaid shares and whole items, with the declined card-eligible purchases of payers without a
  card and the pool's bridges in place of failures apart; the spread of each person's fee units under a monthly cap
  of 2, 3 and 5; and with the development seeds, every arm's fees and counts by person and month, and S0's buffer
  chosen at dealing by person and month (the 3 Nov review). Reported only: nothing there enters the headline or a
  verdict;
* for U, M1 and M2 the small-bill loans the pool refused because the receipts would not also have covered the fee
  (the 31 Oct review);
* reported only (decided 3 Nov), none of it in the headline or a verdict: for U, M1 and M2 households' realised
  return as pool owners, the income credited to their shares over their capital-time, % a year before CPI, in all and
  net of issuer money (none reaches the pool's income under demurrage, 4 Nov), by window and by year after launch,
  and their net return less their alternative by window (11 Nov), with its seed mean and 95% t interval in each
  cell; and beside it by
  loan year (decided 4 Nov) the pool's loans' income over their principal-time, with the month's fixed cost
  spread over loan years by principal-time and the loans' own income beside, with each owner's
  own net return since buying (over at most 12 months) at its lowest and capital-weighted mean in W2; for M0, U, M1
  and M2 crossings
  between E and P, routine (free) and conversions (paying the fee), at most one a person a step (a day, the dealing or
  the close) in each kind, as counts and $ a person a year. measures.json stores their monthly series (``MONTHLY``),
  with every arm's mean buffer chosen at dealing by people without a card and by card holders (the 3 Nov review),
  every arm's read-outs of the harsh stress (14 Nov 2026, ``STRESS``: money, savings, wallet P, the bridge book,
  revolving, write-offs, the wages sent outside and hit workers' failures apart from everyone else's), every arm's
  settlement records (``CHAINS``: own shortfall and knock-on failure, and dependence on netting), and in U, M1
  and M2 the contract's monthly path (5 Nov: participation, N, N*, c, coverage, theta, r_b, r_g, the quote);
* at each distress level the paired reading (decided 30 and 31 Oct): each arm against its own run without
  distress for the same r_out, a0 and seed, on failures, participation, pool capital, exit requests and the issuer's
  wallet (those that apply to the arm). Per measure: the largest gap from the start of the distress year and its
  month; the months after the distress year until the gap stays within a quarter of that largest gap for three
  months running after it, or not recovered by the end; and the lasting gap, its average over the last 12 months.
  Each arm's failure dip is also read against S0's, and for U, M1 and M2 the issuer counts as rewarded for failure when
  its wallet over the distress year beats the run without distress in at least 80% of paired seeds (reported, not a
  falsifier). Each job stores the monthly series of these measures, and for every arm the share of jobs without a
  wage (the month's average and its last day) and the wages their payers kept (3 Nov), and since the harsh stress
  (decided 14 Nov 2026) the wages of extra layoffs sent outside the household economy, so the reading can be
  redone;
* for every arm (3 Nov, for the S0 check) card holders' card bridging of the bills and wages their money could not
  pay, since card limits (14 Nov 2026) their cash advances, with the card's fees and charge-offs beside, $ a person
  and a holder a year after launch; and in every store's opening record the outside prices each r_out
  runs at, the products kept fixed, and each distress level's total rate with normal job loss and its hand label of
  jobs without a wage at month 36.
"""
import os

# One BLAS/OpenMP thread per process (the 5 Nov speed review), set before numpy loads here and in every worker (each
# re-imports this module): numpy's and scipy's OpenBLAS otherwise start 24 threads each and commit about 1.5 GB of
# buffers per process, which is what ran out of memory past 12 workers. The engine's only BLAS calls are small dot
# products, and its runs are bit-identical with one thread or 24 (checked 5 Nov).
for _threads in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_threads] = "1"

import argparse  # noqa: E402
import copy  # noqa: E402
from concurrent.futures import FIRST_EXCEPTION, ProcessPoolExecutor, wait  # noqa: E402
from dataclasses import asdict, replace
from functools import lru_cache, partial
from itertools import chain, islice, product
import json
from pathlib import Path
import pickle
import sys
import tempfile
import time

import networkx as nx
import numpy as np
from scipy.stats import nct, norm, t as student

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from cpm_abm.catalogue import finite_catalogue  # noqa: E402  (the pinned, audited PySPG iterator)
from cpm_abm.economy_abm import (BUSINESS_APR, CARD_APR, CARD_FRAUD, CARD_LENDING_COST, CARD_NETWORK,  # noqa: E402
                                 CARD_PROCESSING, CREDIT_RECORDS, EPS, EWA_COST, FAIL_COST, FAIL_FEE,
                                 FAILURE_COUNTS,
                                 CRYPTO_SHARE, HOLDING_COST, LOAN_LOSS_SERIES, PERSONAL_APR, TERM_LENDING_COST,
                                 VEHICLE_APR, Economy, _World, m0_rates, outside_prices, own_returns, simulate)
from run_economy_figures import FIXED_COST_TIMES  # noqa: E402
from run_economy_figures import (DOLLARS, FIXED_COST, classes, engine_inputs, engine_record,  # noqa: E402
                                 issuer_clause, persistence, provenance, windows, years_of_life)

# The experiment's modules (src/cpm_abm/experiment, its code map in the package docstring): every name the
# runner defined when it was one file is importable from here as before.
from cpm_abm.experiment.notes import (A0S, AGAINST_NOTE, APPLIES, ARMS, BASE, BOOTSTRAP_DRAWS,  # noqa: E402,F401
                                      BOOTSTRAP_SEED, BUFFERS, CLAIM_ALPHA, CLAIM_ARMS, CLAIM_CONFIDENCE, CLAIM_MARGIN,
                                      CLAIM_NOTE, CLASSES, CONTRACT, CROSSINGS, DIP_MARGIN, DIP_MONTHS, DISTRESS,
                                      FAIL_USD, FAILURE_LABELS, FAILURE_NOTE, GAIN_MONTHS, GRID, GROUP_NAMES,
                                      LIQUIDITY_NOTE, MEASURES, MONTHLY, MONTHLY_CAPS, MONTHLY_NOTE, OWNERS,
                                      PERCENTILES, POOL_ARMS, POOL_RUN, POPULATION, RATES, REAL_LINES, RECOVERY_MONTHS,
                                      RECOVERY_SHARE, REGION_AGAINST, REGION_GROUPS, REGION_MARGIN, REGION_NOTE,
                                      REPORT_NOTES, REWARD_SHARE, SCALE, SEED_ASSURANCE, SEED_CAP, SEED_POWER, SHORT,
                                      STOCK_LABELS, STRESS, STRESS_HEADLINE, STRESS_HEADLINE_LABEL, STRESS_LEVELS,
                                      VERDICTS, WAGE_LOSS, WEALTH, WORKERS, WORKERS_MOST)
from cpm_abm.experiment.statistics import (DIP_YEARS, bonferroni_alpha, bonferroni_cells,  # noqa: E402,F401
                                           bootstrap_bounds, check, combined, connected_blocks, dips, _finite,
                                           _group_bounds, limited, persistent_on_wilson, pooled_freedom,
                                           pooled_spread, reading, _resampled_means, _resamples, seeds_needed,
                                           share_reading, spread_bound, spread_resolved, t_bounds, t_interval,
                                           _t_quantile, _t_quantiles, three_way, wilson, wilson_bounds,
                                           wilson_unrounded, yearly_dips)
from cpm_abm.experiment.grid import (CONFIRMATION_COUNT, CONFIRMATION_EXTENSION,  # noqa: E402,F401
                                     CONFIRMATION_LEAST, CONFIRMATION_MOST, CONFIRMATION_RESERVED, CONFIRMATION_START, RETIRED_SEEDS, SEEDS, cell_inputs,
                                     confirmation_block, confirmation_seeds, runs_in, _seed_readings, seeds_for,
                                     selected, tasks_for)
from cpm_abm.experiment.grid import SIDE_DISTRESS  # noqa: E402
from cpm_abm.experiment.notes import LOW_RATES, SIDE_RATES  # noqa: E402
from cpm_abm.experiment.accounts import (COVERED, HELD, by_chronic, by_class, by_quintile,  # noqa: E402,F401
                                         by_windows, card_bridging, cash_check, crossings, demurrage, ewa_report,
                                         failure_report, households_pool, liquidity, measures, monthly, owners_excess,
                                         owners_return, pool_report, real_part, split, transfers)
from cpm_abm.experiment.gains import arm_row, complete_gain, differences, groups, v3_harmed  # noqa: E402,F401
from cpm_abm.experiment.region import (better_than_m0, _class_mean, decide, decide_cells, _gap,  # noqa: E402,F401
                                       paired, recovery, region, registered_shares, seed_means, seed_nanmeans, share_of,
                                       w2_of, worse_than_m0)
from cpm_abm.experiment.claims import (CLAUSES, PASS_CLAUSES, _cell_reading, _claim_arm,  # noqa: E402,F401
                                       _claim_cell, claim_statistics, clause_a, clause_b, clause_c, clause_d,
                                       clause_d_bound, _clause_entry, _counts, fire_interval_falsifier, _headline,
                                       _near_parts, real_cost_readouts, _region_slice, _run, _stress_cell, stress_leg,
                                       _withstood)
from cpm_abm.experiment.store import (_compact, compacted, _counts_text, fixed_products,  # noqa: E402,F401
                                      outside_rates, run_record, _stored_jobs, stored_reading, StoredCounts,
                                      _write_indented, _write_jobs, write_stores)
from cpm_abm.experiment.jobs import (assemble, cell_task, finish, fork_month, forked, gathered,  # noqa: E402,F401
                                     grouped, job, prefix, preflight, preflight_arm, run_tasks, _s0_file, s0_task, same,
                                     _stored, _wait_for_s0)


def options():
    """The command line; the workers default is the default limit, 12 (``--most-workers``), and the cells default to the
    full grid (a selection, the 3 Nov review, takes grid values only)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", choices=tuple(SEEDS), required=True)
    parser.add_argument("--only-seeds", type=int, nargs="+", metavar="SEED",
                        help="run only these seeds of the set, a part of the map: a seed not in the set is refused, "
                             "and the stores name the part, its seeds and the set's (``run_record``), decide no cell, "
                             "read no claim and draw no figure; scripts/run_confirmation.py runs a map one seed a part "
                             "and scripts/join_parts.py joins the parts into the map")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--n", type=int, default=POPULATION,
                        help="people in the population: 4,000, the size decided 12 Nov")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--most-workers", type=int, default=WORKERS_MOST, metavar="M",
                        help="the most workers a run may use, 12 by default: each worker needs about 1.5 GB at 4,000 "
                             "people, so raise the limit only on a machine with that much memory for every worker; "
                             "--workers above it is refused before anything runs")
    parser.add_argument("--timing", action="store_true", help="time one job at the baseline cell; write nothing")
    parser.add_argument("--dry-run", action="store_true",
                        help="build the full job list and print the jobs, seeds, cells, workers, population and output "
                             "folder, then stop: nothing is simulated or written")
    parser.add_argument("--plain", action="store_true",
                        help="run every job whole (no shared S0, no distress fork): the same records, more work")
    parser.add_argument("--r_out", type=float, nargs="+", choices=sorted(RATES + SIDE_RATES + LOW_RATES),
                        default=RATES,
                        help="r_out a year to run; 0.025, 0.03 and 0.035 are the rate cut's levels beside the grid's, "
                             "run on the exploratory seeds (or development seeds) only; 0.005 and 0.01 are the low "
                             "rates, an exploratory side check on the side seeds only")
    parser.add_argument("--custody-cost", type=float, metavar="PCT",
                        help="the issuer's custody cost on P, %% a year (0.24 as built): an exploratory side check "
                             "on the side seeds only")
    parser.add_argument("--owners-spread", type=float, metavar="POINTS",
                        help="the owners' spread over the outside rate, points a year (0.25 as built): an exploratory "
                             "side check on the side seeds only")
    parser.add_argument("--distress-start", type=int, metavar="MONTHS",
                        help="months after launch at which the distress year starts (24 as built): an exploratory "
                             "side check on the side seeds only")
    parser.add_argument("--a0", type=float, nargs="+", choices=A0S, default=A0S, help="initial participation to run")
    parser.add_argument("--distress", type=float, nargs="+", choices=sorted(DISTRESS + SIDE_DISTRESS), default=DISTRESS,
                        help="distress levels to run; a level's paired reading needs 0 selected too; 0.016 to 0.019, "
                             "the stress boundary's levels beside the grid's, run on development seeds only")
    parser.add_argument("--arms", choices=("all", "S0"), default="all",
                        help="every arm (default), or S0 alone (the S0 check, 3 Nov)")
    parser.add_argument("--fees-a-month", type=float, default=Economy.fees_a_month,
                        help="the most failure fees a payer pays a month: 2, decided after the S0 check (4 Nov); "
                             "3 and 5 are read beside it")
    parser.add_argument("--past-cap", type=float, choices=(27.0, 0.0), default=27.0,
                        help="what the buffer replay prices a failure past the monthly cap at, $ (the S0 check, 3 Nov)")
    parser.add_argument("--crypto-share", type=float, default=CRYPTO_SHARE,
                        help="M0's share of people holding crypto collateral, at full cover; default 0: collateral "
                             "lending by Compound III is not run or reported (decided 12 Nov: real DeFi lends only "
                             "against collateral worth more than the loan, which is not everyday credit); the option "
                             "remains only so the existing unit tests of that code path can run")
    parser.add_argument("--leave-noise", type=float, choices=(0.5, 1.0, 2.0), default=1.0,
                        help="the leaving rule's logistic noise as a multiple of its decided scale, 1e-4 of each "
                             "person's own monthly spending (decided 4 Nov: half and twice are reported beside)")
    parser.add_argument("--fixed-cost", choices=tuple(FIXED_COST), default="central",
                        help="the pool's sourced fixed cost (decided 5 Nov): central, Aave's 2025 paid service "
                             "providers, $0.18 a consumer unit a year; low, Compound's, $0.10; high, Sky's, $0.50")
    parser.add_argument("--m0-rates", choices=("observed", "fitted"), default="observed",
                        help="how M0's rates follow r_out (decided 5 Nov): observed, one for one from the October "
                             "2026 levels; fitted, the lag-3 OLS lines, a sensitivity")
    parser.add_argument("--entry-reads", choices=("quote", "realised", "leaving_rule"), default="quote",
                        help="what entrants compare with their alternative at dealing: quote, the pool's quote at N*, "
                             "the decided rule; realised, the pool's trailing realised return, a sensitivity "
                             "(decided 11 Nov: the entry check); leaving_rule, the same return read by each saver "
                             "with the leaving rule's own dispersion, between the two (decided 12 Nov)")
    parser.add_argument("--loan-losses", choices=("none", "sourced"), default="none",
                        help="loan losses (decided 12 Nov): none, as built (a written-off loan stays owed); "
                             "sourced, the bound: every lender, the pool included, discharges each month the Federal "
                             "Reserve charge-off rate of the bank loans its loans replace on their average balance, "
                             "moving with jobs without a wage three months earlier, and the pool's coupons carry "
                             "that rate")
    parser.add_argument("--lenders-interest", choices=("leaves", "returned"), default="leaves",
                        help="outside lenders' interest (decided 12 Nov): leaves the economy, as built, with the "
                             "full grid's extra baseline set returning it; or returned to households in proportion to "
                             "spending in every job of the requested grid, with no extra set")
    parser.add_argument("--card-lines", choices=("held", "cut"), default="held",
                        help="card lines in the distress year (decided 14 Nov 2026): held, the main reading; or "
                             "cut at the start of the distress year by each tier's share of the 2008 to 2012 cut times "
                             "the distress level over 2%%, a side check only")
    # The robustness switches (docs/ROBUSTNESS_PLAN.md, section 5), side checks on development seeds only, each off
    # by default; the run record stores every Economy field, so a results folder names its variant.
    parser.add_argument("--buffer-review", type=float, default=Economy.buffer_review, metavar="ALPHA",
                        help="the share of people who re-choose their cash buffer each month, the rest keeping last "
                             "month's: 1, everyone every month, the base; 0.5 and 0.153, the review chance, beside it")
    parser.add_argument("--joining", choices=("linear", "threshold"), default=Economy.joining,
                        help="the joining rule: linear, the base, xi0 + xi1 times the contact share; threshold, xi0 + "
                             "xi1 where the contact share reaches the person's own threshold and xi0 below it")
    parser.add_argument("--thresholds", type=_thresholds, default=Economy.thresholds,
                        help="the thresholds under --joining threshold: uniform on 0 to 1, the check that the rule is "
                             "built right; measured, log-normal with log-mean -2 and log-spread 1; or one common number "
                             "from 0 to 1 (0.1, 0.2 and 0.3 are run)")
    parser.add_argument("--sellers", choices=("uniform", "ring", "hubs"), default=Economy.sellers,
                        help="who sells services, shocks and instalment purchases: uniform over the others, the base; "
                             "ring, one of the buyer's 32 nearest neighbours with chance --local-share and anyone else "
                             "otherwise; hubs, with chance falling with the rank of initial spending; wages stay uniform")
    parser.add_argument("--local-share", type=float, default=Economy.local_share,
                        help="on the ring, the chance a purchase goes to a neighbour: 1, the clustered end; 0.35 beside")
    parser.add_argument("--launch", choices=("scattered", "neighbourhood", "largest"), default=Economy.launch,
                        help="who is in P at launch: scattered, each person with chance a0, the base; neighbourhood, "
                             "round(a0 n) neighbours on the ring (needs --sellers ring); largest, the round(a0 n) "
                             "largest sellers (needs --sellers hubs)")
    return parser


def _thresholds(text):
    """--thresholds: "uniform", "measured" or one common number."""
    if text in ("uniform", "measured"):
        return text
    try:
        return float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"uniform, measured or a number from 0 to 1, not {text!r}") from None


SWITCHES = ("buffer_review", "joining", "thresholds", "sellers", "local_share", "launch")


CUT_SEEDS = ("exploratory", "development")       # the seed sets the rate cut's levels may run on
SIDE_CHECK_SEEDS = "side"                        # the seed set the exploratory side checks run on


def side_economy(args):
    """The Economy settings an exploratory side check sets away from the build, as the engine holds them (a month):
    the custody cost and the owners' spread from per cent a year, the shock date in months. Empty for a run that
    names none, so such a run builds exactly the Economy it built before."""
    found = {}
    if args.custody_cost is not None:
        found["issuer_cost"] = args.custody_cost / 100 / 12
    if args.owners_spread is not None:
        found["owner_spread"] = args.owners_spread / 100 / 12
    if args.distress_start is not None:
        found["distress_start"] = args.distress_start
    return found


def side_check_refused(args):
    """Why a run that asks for an exploratory side check is refused, or None. The side checks (a custody cost, an
    owners' spread or a shock date away from the build, the fixed cost at a multiple, a low outside rate) run on
    the side seeds only, and the shock date must leave the distress year inside the run."""
    asked = sorted(side_economy(args)) + [f"fixed cost {args.fixed_cost}"] * (args.fixed_cost in FIXED_COST_TIMES) \
        + [f"r_out {rate}" for rate in sorted(set(args.r_out) & set(LOW_RATES))]
    if asked and args.seeds != SIDE_CHECK_SEEDS:
        return (f"the exploratory side checks run on the side seeds only (--seeds {SIDE_CHECK_SEEDS}); got --seeds "
                f"{args.seeds} with {', '.join(asked)}")
    if args.distress_start is not None and not 0 <= args.distress_start <= Economy.months - Economy.distress_length:
        return (f"--distress-start is from 0 to {Economy.months - Economy.distress_length} months after launch, so "
                f"that the distress year ends inside the run; got {args.distress_start}")
    return None


def cut_refused(args):
    """Why a run that selects a level of the rate cut is refused, or None: the cut runs on the exploratory seeds (or
    development seeds), never on the confirmation seeds."""
    cut = sorted(set(args.r_out) & set(SIDE_RATES))
    if cut and args.seeds not in CUT_SEEDS:
        return (f"the rate cut's levels run on the exploratory seeds or development seeds only; got --seeds "
                f"{args.seeds} with r_out {', '.join(map(str, cut))}")
    return None


def side_settings(args):
    """The robustness switches and stress boundary levels a run asks for that the base does not have: the names of
    the switches set away from their defaults, and the side levels selected."""
    changed = [name for name in SWITCHES if getattr(args, name) != getattr(Economy, name)]
    return changed, sorted(set(args.distress) & set(SIDE_DISTRESS))


def main():
    """Run the selected cells (by default every cell) in parallel and write cells.json, measures.json,
    failure_counts.json, summary.json and the region figures the store supports (``run_region_figures``); or time
    one job; or, with --dry-run, print the launch and stop."""
    parser = options()
    args = parser.parse_args()
    # Refused before anything runs or is written: more workers than --most-workers allows (12 by default, since more
    # ran out of memory on a 31 GB laptop; each worker needs about 1.5 GB at 4,000 people), or the confirmation set
    # while its count is not fixed (``seeds_for``).
    if args.workers > args.most_workers or args.workers < 1:
        parser.error(f"--workers must be from 1 to {args.most_workers}, the limit --most-workers sets (12 by default, "
                     f"about 1.5 GB a worker at 4,000 people); got {args.workers}")
    try:
        seeds = seeds_for(args.seeds)
    except ValueError as refused:
        parser.error(str(refused))
    # A part of the map (--only-seeds): some seeds of the set, in the set's order; a seed outside the set is refused.
    part = args.only_seeds is not None
    if part:
        stray = sorted(set(args.only_seeds) - set(seeds))
        if stray:
            parser.error(f"--only-seeds must name seeds of the {args.seeds} set {list(seeds)}; got {stray}")
        seeds = tuple(seed for seed in seeds if seed in args.only_seeds)
    # The robustness switches and the stress boundary's levels are side checks, run on development seeds only
    # (docs/ROBUSTNESS_PLAN.md, section 6), so the confirmation seeds never see them. The rate cut's levels
    # (SIDE_RATES) run on the exploratory seeds, as the plan requires of any run made after the confirmation is
    # read, or on development seeds; the confirmation seeds never see them either (decided 17 Nov 2026).
    changed, side_levels = side_settings(args)
    if (changed or side_levels) and args.seeds != "development":
        parser.error(f"the robustness switches and the stress boundary's levels run on development seeds only; got "
                     f"--seeds {args.seeds} with {', '.join(changed + [f'distress {v}' for v in side_levels])}")
    refused = cut_refused(args) or side_check_refused(args)
    if refused:
        parser.error(refused)
    selection = selected(args.r_out, args.a0, args.distress)
    # Lenders' interest returned over the whole grid (decided 12 Nov): every job runs with it, no extra set.
    returned = args.lenders_interest == "returned"
    tasks = tasks_for(seeds, args.n, selection, returned)
    s0_only = args.arms == "S0"
    # The monthly cap and the replay's price of a failure past it, for the S0 check and its fallbacks (3 Nov); M0's
    # crypto collateral share (0 by default, decided 12 Nov: not run), the leaving rule's noise multiple (4 Nov) and
    # what entry reads (11 Nov, the entry check) and loan losses (12 Nov). The run record stores every Economy field,
    # so it shows the entry and loan-loss options.
    try:
        template = Economy(n=args.n, fees_a_month=args.fees_a_month, buffer_prices_past_cap=args.past_cap > 0,
                           crypto_share=args.crypto_share, leave_noise=args.leave_noise, m0_rates=args.m0_rates,
                           entry_reads=args.entry_reads, loan_losses=args.loan_losses,
                           lender_income_recirculated=returned, card_line_cut=args.card_lines == "cut",
                           **{name: getattr(args, name) for name in SWITCHES}, **side_economy(args))
    except ValueError as refused:
        parser.error(str(refused))
    count = partial(runs_in, s0_only=s0_only)
    total = sum(map(count, tasks))
    output = None if args.output is None else (ROOT / args.output).resolve()
    if output is not None and not output.is_relative_to(ROOT) and not args.timing:
        raise ValueError("Output must stay in this workspace")
    if args.dry_run:
        # The launch as it would run, built and printed, nothing simulated or written (the 13 Nov speed pass).
        cells = [[p["r_out"], p["a0"], p["distress"]]
                 for p in finite_catalogue({name: list(values) for name, values in selection.items()})]
        print(json.dumps(dict(seed_set=args.seeds, seeds=list(seeds),
                              **(dict(part_of=list(seeds_for(args.seeds))) if part else {}), cells=len(cells),
                              recirculation_set_jobs=sum(bool(task[5]) and not returned for task in tasks),
                              jobs=len(tasks), population_runs=total, arms=["S0"] if s0_only else ["S0", *ARMS],
                              workers=args.workers, population=args.n,
                              switches={name: getattr(template, name) for name in SWITCHES},
                              output=None if output is None else str(output),
                              output_exists=None if output is None else output.exists(),
                              mode="plain" if s0_only or args.plain else "shared S0 and distress fork"), indent=1))
        print("cells (r_out, a0, distress):\n" + "\n".join(f"  {rate}, {a0}, {level}" for rate, a0, level in cells))
        return
    if args.timing:
        # One job at the baseline cell with the most distress, and the whole run projected from it: a job's runs go one
        # after another and only as many workers as jobs are busy, so the longest job bounds a small selection.
        probe = (BASE[0], BASE[1], DISTRESS[-1], seeds[0], args.n, returned)
        began = time.perf_counter()
        job(probe, template, s0_only=s0_only, fixed_cost=args.fixed_cost)
        seconds = (time.perf_counter() - began) / count(probe)
        print(json.dumps(dict(seed_set=args.seeds, jobs=len(tasks), population_runs=total, workers=args.workers,
                              seconds_per_run=round(seconds, 1),
                              projected_hours=round(seconds * max(total / min(args.workers, len(tasks)),
                                                                  max(map(count, tasks))) / 3600, 2)), indent=1))
        return
    if output is None:
        parser.error("--output is required unless --timing or --dry-run")
    output.mkdir(parents=True, exist_ok=False)
    if s0_only or args.plain:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            work = partial(_stored, job, template=template, s0_only=s0_only, fixed_cost=args.fixed_cost)
            named = {pool.submit(work, task): (f"job r_out {task[0]}, a0 {task[1]}, distress {task[2]}, seed "
                                               f"{task[3]}, lenders' interest {'returned' if task[5] else 'leaving'}")
                     for task in tasks}
            done = gathered(pool, named)
            jobs = [done[future] for future in named]
    else:
        preflight(template, args.workers, args.fixed_cost)
        jobs = run_tasks(tasks, template, args.workers, args.fixed_cost)
    w = template
    if part:
        # A part decides no cell and reads no claim: those are read once, over every seed, on the joined map
        # (scripts/join_parts.py). Its stores hold its jobs and say which seeds of which set they are.
        write_stores(output, run_record(w, args.seeds, total, selection, s0_only, args.fixed_cost, only=seeds), jobs,
                     [], None)
        print(json.dumps(dict(seed_set=args.seeds, part_seeds=list(seeds), jobs=len(jobs)), indent=1))
        return
    cells, recirculated = decide_cells(jobs, selection, w, args.n)
    # The registered claim read cell by cell beside the verdict (docs/ANALYSIS_PLAN.md), none with S0 alone.
    statistics = None if s0_only else claim_statistics(cells, jobs, w)
    # The stores go first, so a figure that fails cannot lose the run's records.
    write_stores(output, run_record(w, args.seeds, total, selection, s0_only, args.fixed_cost), jobs, cells,
                 recirculated, statistics)
    from run_region_figures import draw
    draw(output)
    print(json.dumps(dict(baseline=[c for c in cells if (c["r_out"], c["a0"]) == BASE],
                          baseline_lender_interest_recirculated=recirculated), indent=1))


if __name__ == "__main__":
    main()

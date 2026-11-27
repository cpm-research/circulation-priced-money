"""The fixed values of the population map and every note stored with its results.

The grid's values (r_out, a0 and the distress levels), the population, the arms, the workers, the names of the
monthly series and measures each job stores, the region's margins and groups, the claim's levels and margins, and
the plain-words notes written into each store beside the numbers they explain. Nothing here computes; every other
module of the package reads these values.
"""
from cpm_abm.economy_abm import FAILURE_COUNTS
from cpm_abm.engine.measures import CHAIN_SERIES
from run_economy_figures import DOLLARS

A0S = (0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.8)
RATES = (0.02, 0.044, 0.06)        # r_out = rho_H, % a year
DISTRESS = (0.0, 0.005, 0.01, 0.015, 0.02)   # extra layoffs per job a month in the distress year
# Each distress level is the monthly layoff rate per job in the distress year above normal job loss. STOCK_LABELS
# labels each level by the share of jobs without a wage at month 36, in %: a hand calculation, which the S0 check
# compares with the runs' own share, within 0.5 points.
STOCK_LABELS = (1.9, 3.4, 4.9, 6.3, 7.7)


# The population of the map and of the confirmation runs, and the runner's default --n. The size check's written
# rule takes 8,000; 4,000 is a declared departure from it.
POPULATION = 4000
# The arms each job runs beside S0, and among them the pool arms. U is M1 without the holding charge (demurrage).
ARMS = ("M0", "U", "M1", "M2")
POOL_ARMS = ("U", "M1", "M2")
BASE = (0.044, 0.6)
GRID = dict(r_out=RATES, a0=A0S, distress=DISTRESS)   # the full grid, of which a run may select cells (``selected``)
# The rate cut: finer outside rates between the grid's 2% and 4.4%, where the claim's edge lies and the grid has no
# level. They stand beside the grid and are never part of it, so the full grid, the registered claim and every
# reading tied to the grid's rates are unaffected. A run that selects one is exploratory: it uses the exploratory
# seeds (from 20261601), never the confirmation seeds, and is labelled so wherever it is reported.
SIDE_RATES = (0.025, 0.03, 0.035)
# The low rates: outside rates under the grid's 2%, where the charge is squeezed against the custody cost. Like the
# rate cut they stand beside the grid; a run that selects one is exploratory and uses the side seeds only
# (``grid.SIDE_SEEDS``).
LOW_RATES = (0.005, 0.01)


def rate_axis(rates):
    """The outside rates a run's region is joined along and its record lists: the grid's rates when the run covers no
    other rate, else the run's own rates in ascending order (a run of the rate cut)."""
    rates = set(rates)
    return RATES if rates <= set(RATES) else tuple(sorted(rates))


SHORT = 15                          # billing cycles of 1-15 days are "short", 30-60 days "long" (harm groups)
WORKERS = 12                        # the default --workers: more runs out of memory on a machine with 31 GB
WORKERS_MOST = 12                   # the default of --most-workers; a larger --workers is refused (``main``)
# The paired distress reading: its measures (monthly series), the arms each applies to and the scale each is
# reported on (points of spending, points of participation, $ a person). A measure has recovered once its gap stays
# within RECOVERY_SHARE of its largest gap for RECOVERY_MONTHS running. The issuer is rewarded for failure when its
# distress-year wallet is higher in at least REWARD_SHARE of paired seeds.
MEASURES = dict(failures="failure_share", participation="A", pool_capital="N", exits="exit_requested",
                issuer_wallet="issuer_wallet")
APPLIES = dict(S0=("failures",), M0=("failures", "participation"), **dict.fromkeys(POOL_ARMS, tuple(MEASURES)))
SCALE = dict(failures=100.0, participation=100.0, pool_capital=DOLLARS, exits=DOLLARS, issuer_wallet=DOLLARS)
RECOVERY_SHARE, RECOVERY_MONTHS, REWARD_SHARE = 0.25, 3, 0.8
# The wage-loss path behind the distress reading, stored for every arm beside the measures and read by none of them.
# jobs_without_wage is the share of the month's job-days on a job in a spell (each wage contract is one job, so this
# is the month's average share of jobs paying no wage), jobs_without_wage_last_day the share of jobs in a spell on
# the month's last day, and wages_withheld the wages their payers kept, in months of mean spending a person (times
# DOLLARS, $ a person that month). The spells are the same in every arm; the wages withheld follow each arm's
# spending. By default payers keep only the wages of normal job loss: wages_out holds the wages of the distress
# year's extra layoffs, which their payers owe to the outside and nobody in the economy receives, in the same units.
WAGE_LOSS = dict(jobs_without_wage="laid_off", jobs_without_wage_last_day="laid_off_last_day",
                 wages_withheld="wages_withheld", wages_out="wages_out")
# Monthly series stored with every job, one value a month after launch, None where undefined: households' capital
# and credited income (pool arms), crossings between E and P (CPM arms), and in every arm the mean buffer chosen at
# dealing by people without a card and by card holders, in months of mean spending. S0's buffers are stored so that
# those of people without a card can be set against them.
CROSSINGS = ("crossings", "crossed", "conversions", "converted")
OWNERS = ("owners_capital", "owners_income", "owners_income_net")
BUFFERS = ("buffer_nocard", "buffer_card")
# The contract's monthly path in the pool arms, the engine's own series: participation A, pool capital N and its
# limit N* (Q), demurrage c on wallet P, its coverage of the bridging capital cost and its share theta of bridging
# finance, the rate a bridge is sealed at r_b, the coupon r_g and the published quote. Rates are a month (P terms in
# M2), money in months of mean spending a person.
CONTRACT = ("A", "N", "Q", "c", "coverage", "theta", "r_b", "r_g", "quote")
# The stress read-outs in every arm, the engine's own series, read by no rule: households' money (E and P) and
# outside savings at the close, wallet P (the month's average, the W that demurrage's terms read), the pool's bridge
# book (its average principal, the B they read), statements left to revolve on the card, pool loans written off, the
# wages of extra layoffs sent outside, the failure share of hit workers (the earners of a job with a day in a spell
# that month) and of everyone else, hit workers' failed shares a person, and the settlement's days above SLOW_SWEEPS
# (slow_days) and the most sweeps any day took (most_sweeps).
STRESS = ("liquid", "savings", "p_bt", "P_bar", "revolved", "written_off", "wages_out", "failure_share_hit",
          "failure_share_rest", "fail_shares_hit", "slow_days", "most_sweeps")
# The run on the pool under the harsh stress, the model's stress boundary, month by month in the pool arms: the
# engine's own series, read by no rule. The pool's cash and the cash new loans may take at the close, the cash set
# aside for exits, the money offered at the dealing and the part that found no room, exits paid and owners filing a
# new exit request (a count), pool term principal on the book, bridges drawn over wanted, and the month's write-offs
# of bridges and of term loans, each apart. Exit requests are stored monthly with the distress measures
# (measures["exits"]).
POOL_RUN = ("pool_cash", "cash_to_lend", "exit_set_aside", "offers", "offers_unused", "exit_paid", "exits_filed",
            "term_pool", "bridges_drawn_over_wanted", "written_off_bridge", "written_off_term")
# Mean net wealth in every arm, read by no rule. The failure share is stored monthly with the distress measures in
# every arm (measures["failures"]).
WEALTH = ("mean_wealth",)
# The settlement's records of failure passed along and of dependence on netting (docs/ROBUSTNESS_PLAN.md, section
# 4), in every arm, the engine's own series, read by no rule (``CHAIN_SERIES``).
CHAINS = CHAIN_SERIES
MONTHLY = dict(S0=BUFFERS + STRESS + WEALTH + CHAINS, M0=CROSSINGS + BUFFERS + STRESS + WEALTH + CHAINS,
               **dict.fromkeys(POOL_ARMS,
                               CONTRACT + OWNERS + CROSSINGS + BUFFERS + STRESS + POOL_RUN + WEALTH + CHAINS))
# The second run's monthly records, stored after MONTHLY's only in a run that uses one of the second run's settings
# (``second_run``); a run at the defaults stores MONTHLY's alone. In every arm: what the conserved edge hands back to
# households (returned), the extra layoffs' wages their payers kept (wages_kept), the purchases dropped (a count a
# person), card debt to outside lenders, households' money (E and P) and outside savings as the month's average
# balance (money_bt, savings_bt), outside lenders' interest and the card's cash-advance and late fees, a person a
# month in months of mean spending. In the pool arms also the capital target (target) and every loan the pool carried,
# bridges and term loans together, the month's average principal (pool_pt); the bridges alone (P_bar), pool capital N,
# its limit Q, bridges served (bridges_drawn_over_wanted) and the bridge price (r_b) are in MONTHLY. The failure share
# is stored with the distress measures and failed shares with the failure counts, in every run.
SECOND_RUN = ("returned", "wages_kept", "purchases_dropped", "card_debt", "money_bt", "savings_bt", "out_interest",
              "advance_fees", "late_fees")
SECOND_POOL = ("target", "pool_pt")
# After them in a run of the second run, in every arm: the series behind every line of the real cost
# (``accounts.real_part``) that SECOND_RUN does not hold, so that the cost can be read by window from the store.
# Principal-time on card credit, on the pool's card credit to holders and to payers without a card, on term credit
# (pool and outside) and on all pool bridges to holders (pt_pool_card, which the real cost reads when
# ``failure_shares`` is off); failed and bridged shares, failure fees and pool bridges to payers without a card; card
# payments by count and value; gas; pool shares held; earned-wage advances.
SECOND_REAL = ("pt_card", "pt_pool_card_credit", "pt_pool_nocard_card", "pt_pool_term", "pt_term", "pt_pool_card",
               "fail_shares", "bridged_shares", "penalties", "nocard_bridges", "card_payments", "card_value", "gas",
               "shares_bt", "ewa_uses")
# After them in a run of the second run, in every arm whose engine records them, each a person a month in months of
# mean spending: what the pool owes its operating provider at the month's end (pool_payable, which clause (a) reads)
# and the most it owed on any day of the month (pool_payable_most), the inflation part of the month's payout
# (payout_inflation), what was booked to the edge when a debt was created (edge_accrued) and when cash moved
# (edge_paid), the stock accrued to the edge and not yet paid (edge_owed), the part of the month's flow the
# payout does not return (edge_kept), what card holders owe their card that is not yet a loan (card_unbilled:
# purchases not yet billed plus the closed statement not yet due) and the cash paid in the month on amounts booked
# across the edge earlier (edge_cleared). A run whose engine does not keep one of them does not store it, and the
# readers that need it say so.
SECOND_RECORDS = ("pool_payable", "pool_payable_most", "payout_inflation", "edge_accrued", "edge_paid", "edge_owed",
                  "edge_kept", "settle_held", "card_unbilled", "edge_cleared")
SECOND_MONTHLY = dict(S0=SECOND_RUN + SECOND_REAL, M0=SECOND_RUN + SECOND_REAL,
                      **dict.fromkeys(POOL_ARMS, SECOND_RUN + SECOND_REAL + SECOND_POOL))


def second_run(w):
    """Whether the Economy ``w`` uses a setting of the second run: the conserved edge, the extra layoffs' wages kept,
    purchases dropped in the stress year, or distress years at random. Each is off at its default, so the first run
    reads False."""
    return (getattr(w, "edge", "open") != "open" or getattr(w, "distress_wages", "outside") != "outside"
            or getattr(w, "distress_purchases", 0.0) > 0 or getattr(w, "distress_dates", "dated") != "dated")


def conserves_money(w):
    """Whether the Economy ``w`` conserves money (``edge`` "conserved"): each month what households lose across the
    edge of the household economy and to inflation is paid back to them. The first run reads False.

    In a run that conserves money clause (d) is read on each group's own payments that did not complete
    (``claims.clause_d_harm``), since a group's money then rises almost only where another's falls. Mean wealth
    differs between arrangements only by their cumulative revaluation of loans, by the change in the stock booked
    across the edge and not yet paid in cash (under ``payout`` "paid") and by what the payout keeps back
    (``edge_kept``, zero at the second run's settings). Measured on one seed, M1 less S0 is +$7.88 a person: -$0.04
    of it revaluation and +$7.92 the stock."""
    return getattr(w, "edge", "open") == "conserved"


def monthly_keys(arm, w):
    """The monthly series a job stores for ``arm`` under the Economy ``w``: MONTHLY's, and in a second run
    (``second_run``) SECOND_MONTHLY's after them.

    Example: S0 at the defaults stores MONTHLY["S0"] alone; S0 with ``edge`` "conserved" stores it followed by
    returned, wages_kept and the rest of SECOND_RUN."""
    return MONTHLY[arm] + (SECOND_MONTHLY[arm] if second_run(w) else ())


MONTHLY_NOTE = (
    "One value a month after launch, None where undefined, in the engine's units: rates a month (P terms in M2), money "
    "in months of mean spending a person ($6,440), shares as shares. In the pool arms the pool run's read-outs: "
    "pool_cash and cash_to_lend at the close, exit_set_aside (the cash not owed to the pool's creditors "
    "less the cash new loans may take, at the same moment), offers and offers_unused (the money offered at the month's "
    "dealing and the part that found no room), exit_paid, exits_filed (owners filing a new exit request, a count), "
    "term_pool (pool term principal on the book), bridges_drawn_over_wanted, and written_off_bridge and "
    "written_off_term (the month's write-offs by loan kind, adding up to written_off). In every arm mean_wealth, mean "
    "net wealth at the close. Exit requests and the failure share are stored monthly with the distress measures "
    "(exits, failures). In every arm the settlement's records, read by no rule. Own shortfall and knock-on: each "
    "payer's failed amount on a day, a payment counted on the day it first falls due as failures counts it, is split "
    "into what it fails in the first sweep of the day's settlement, with every payment owed to it that day arriving in "
    "full under the day's final pool queue (own_shortfall), and the rest, failure that happens only because receipts "
    "were short (knock_on, signed, and knock_on_positive, its positive part); own_shortfall + knock_on is the month's "
    "failures. own_shortfall_n and knock_on_n count the payer-days with each part above zero, and knock_on_days_0, "
    "_1, _2_3, _4_7, _8_15, _16_31 and _32_up the days by how many payers had a knock-on failure. Dependence on "
    "netting: on each day the largest set of payers that complete a payment due on the cash route with no means of "
    "their own (no money, no outside savings, no credit drawn that day and no card receipts) and are paid only by each "
    "other; netting_days counts the days the set is not empty and netting_n the payer-days in it, netting_value is the "
    "value its members completed, cash_completed the value completed on the cash route on every day, and "
    "netting_lost the value lost when the set is held at zero and the completion map repeated downward with the day's "
    "credit held fixed. Amounts are at face value in months of mean spending a person, counts as counted.")
# The region reading. A cell of a pool arm is in the stable region when its pool forms and persists (the cell reads
# Persistent by the statistics rule: the Wilson lower bound of its share of Persistent seeds above one half), the
# issuer never records "would leave" (claim (a)), and every class, launch-wealth quintile and billing-cycle group
# (claim (d)'s groups) has a mean paired complete gain whose 95% t lower bound across seeds, against S0 and against M0
# (REGION_AGAINST), is at or above claim (d)'s margin, -$2 a person a year: the CFPB's servicing uplift per overdraft
# transaction (overdraft rule, December 2024), the value of the real failure cost. Gains are read in full: M2's
# indexation is the holder's own yield, so no gain is netted of issuer transfers. Claim (d) reads the bound against
# both yardsticks, since the mean against S0 alone reads wider than the claim; the means are kept beside. The complete
# gain is the wealth change plus purchases received, read at both ends of a bracket, sellers' extra sales counted at
# face value and at zero. The value of completed trade is not assumed, and against DeFi the result is reported as a
# break-even value: the clause holds when every group's bound against S0 passes at both ends and every group's bound
# against M0 passes at face, and each yardstick's break-even surplus share, on the bounds and on the means, is stored
# with the wealth gain's own reading beside. Owners' return less their alternative is reported only, and the entry
# rule's two readings, quote and realised (``Economy.entry_reads``), are run as bounds at confirmation.
# M2's cells at a zero real reserve rate are its declared limit, kept outside the region. VERDICTS names each reading,
# the first condition a cell fails, in the order checked, then the stable region.
REGION_MARGIN = -2.0
# The paired differences' dispersion and time read-outs, stored only: the percentiles of each person's gain, and the
# months after launch the mean wealth gain is also read at, beside the end.
PERCENTILES = (5, 25, 50, 75, 95)
GAIN_MONTHS = (36, 48)
REGION_GROUPS = ("class", "quintile", "cycle")
REGION_AGAINST = ("S0", "M0")
VERDICTS = ("declared limit", "no pool", "not persistent", "issuer leaves", "a group loses", "stable")
# In a run that conserves money (``conserves_money``) the group test of the region reading is clause (d) on each
# group's own failed payments, and its reading is named for it.
VERDICTS_CONSERVED = ("declared limit", "no pool", "not persistent", "issuer leaves", "a group is harmed", "stable")


def verdicts_of(w):
    """The region readings a run on the Economy ``w`` can store, in the order checked: ``VERDICTS`` otherwise and
    ``VERDICTS_CONSERVED`` in a run that conserves money."""
    return VERDICTS_CONSERVED if conserves_money(w) else VERDICTS
# A long run's windows, both read and stored in its run record beside them.
WINDOWS_NOTE = (
    "The run's two windows by their years after launch: the last five whole years before the stress year and the last "
    "five whole years of the run. Every reading by window is stored for each under its name (a list by window in the "
    "order above). Each steady-state reading the released claim read in W2 is read in both: the persistence tests, "
    "each read with the second window in turn each of the two and the first window the earlier, hold only if they "
    "hold in both and a falsifier fires if it fires in either; households holding 90% of pool capital with P routing, "
    "the pool paying its own way (P4), trade not worse than M0 (V1) and owners' return not shown worse than M0 (V4) "
    "likewise. A request to withdraw from the pool is judged against the run's real end: the "
    "pool pays a request two months after it is filed, so a request filed in the run's last two months cannot be "
    "judged and is left out of the test of exits paid within two months, in both of its sums; the value left out is "
    "stored (exit_requests_without_follow_up_W2), and the monthly requests filed and paid in time, by month of "
    "filing, are stored with the pool arms' monthly series (exits_started, exits_paid_in_time). A key without a "
    "window name (c_pct, "
    "failures_pct and the other window means) holds the last window's value; by_window holds both.")
REGION_NOTE = (
    "The region reading of each pool arm in each cell. In the stable region when the "
    "pool forms and persists, the issuer stays and no group loses: the pool forms in some seed (households hold pool "
    "capital in a month after launch); the cell reads Persistent by the statistics rule (the Wilson lower bound "
    "of its share of seeds above one half), a seed counting when its own verdict is Persistent; the issuer records "
    "\"would leave\" in no seed (claim (a)); and every class, launch-wealth quintile and billing-cycle group (claim "
    "(d)'s groups) has a mean paired complete gain whose 95% t lower bound across seeds is at or above -$2 a person a "
    "year (claim (d) and its margin) against S0 at both ends of the bracket and against M0 at the "
    "face end: the value of completed trade is not assumed, and against DeFi the result is reported as a break-even "
    "value. The "
    "complete gain is the end-wealth difference plus the difference in purchases received, a "
    "person's own service and shock purchases completed as buyer and the price of each durable it bought that "
    "settled, wages in neither; it is read with sellers' extra sales counted at face value (\"face\") and counted at "
    "zero (\"zero\", the face reading less the difference in sales, the face value of service and shock purchases "
    "completed to the person as seller before any merchant fee plus the price of each durable it sold). "
    "complete_gain holds each end's group means and bounds against both (face, zero), clause_holds, and by_yardstick, "
    "for S0 and for M0: face_passes and zero_passes, whether every group's bound against it is at or above the margin "
    "at that end; break_even_share, the smallest surplus share s on a 0.01 grid from which every group's bound, on "
    "each seed's (1 - s) x zero + s x face, is at or above the margin at every larger grid share; and "
    "break_even_share_on_means, the same search on the groups' seed means; each None when it fails at s = 1 and 0.0 "
    "when it holds at every share. "
    "groups holds the same reading on the wealth gain alone (groups_measure \"wealth\"), stored beside and read by no "
    "verdict. The gains are read in full ("
    "M2's indexation is the holder's own yield, not an issuer transfer, and the issuer, a pure custodian, holds "
    "no pool shares and no support fund, so no issuer money exists). A group with a mean in one seed only has no "
    "bound and does not pass. M2's cells at a zero real reserve rate are its declared limit, outside the region. "
    "verdict names the first condition failed, in the order of verdicts, \"a group loses\" reading clause_holds; "
    "verdict_majority reads Persistent on a bare "
    "majority of seeds instead, as the statistics rule reports beside. Each part is stored, with each group's seed "
    "mean beside its bound against each, and the lowest bound with its group and yardstick. Reading the issuer's stay "
    "in every seed and a pool as formed when it forms in any seed are each a reading of the "
    "rule. Owners' return less their alternative stays reported only, and the entry rule's "
    "two readings, quote and realised (Economy.entry_reads), are run as bounds at confirmation. Under the cash-advance "
    "bound, each gain less the cash-advance fees and interest the person saves against the "
    "yardstick, to first order with no feedback: complete_gain_bound holds the same clause on those gains, "
    "verdict_bound and verdict_majority_bound the verdicts with the group test read on it, and in_region_both whether "
    "the cell is stable both without and under the bound. A seed that stores no bound reads every group as empty "
    "there.")
# In a run that conserves money the region reading's group test is clause (d) on each group's own failed payments, read
# on the 95% t upper bounds alone, and the note says so after the default note.
REGION_NOTE_CONSERVED = REGION_NOTE + (
    " In this run, which conserves money, the group test is clause (d): "
    "every class, launch-wealth quintile and billing-cycle group's own payments that did not complete as payer, "
    "its failed shares of bills and wages plus its declined shares of card-eligible purchases, a person a year in the "
    "real failure line's unit, the arm less S0 and less M0 paired by seed, has a 95% t upper bound across seeds "
    "at or below one failed payment a person a year in each of the run's steady windows; groups_harmed holds each "
    "group's seed mean and upper bound by window and yardstick, the highest bound with its group, and clause_holds. "
    "The verdict names its failure \"a group is harmed\" and reads it in place of the complete gain, which is still "
    "stored (complete_gain, complete_gain_bound) and read by no verdict: with money conserved the mean gain with "
    "sellers' extra sales at zero differs from zero only by the arrangements' cumulative revaluation of loans, by "
    "the change in the stock booked across the edge and not yet paid (under the payout \"paid\") and by what the "
    "payout keeps back (edge_kept, zero in the base), so it "
    "measures a transfer between groups. The registered clause has no reading under the "
    "cash-advance bound, so verdict_bound, verdict_majority_bound and in_region_both read the same group test.")
# What the rows of a run that conserves money add, stored with cells.json in such a run only.
FAILED_GROUPS_NOTE = (
    "failed_by_group (a run that conserves money only): each group's own payments that did not complete as payer, the "
    "mean over the group's people of each person's failed bills and wages in unpaid shares (the real failure line's "
    "unit, the one clause (c) and the stress dip read) plus its declined card-eligible purchases in unpaid shares (a "
    "purchase of a payer without a card, or past a holder's room, lost with no fee), a person a year in each of the "
    "run's steady windows (windows), for the four classes, the five launch-wealth quintiles and the short and long "
    "billing cycle, in the order and with the definitions of the complete gain's groups: level, the arm's own; S0, "
    "banks' on the same seed; against_S0 and against_M0, the arm's less S0's and less M0's (M0's own row has "
    "against_S0 only), each of the sum of the two parts; failed and declined hold the same for each part alone. NaN "
    "marks an empty group. Clause (d) reads the sum's against_S0 and against_M0.")
# How each kind of obligation is counted by the three failure records, stored with cells.json in
# a run that conserves money: the headline percentage (failure_share, failures_pct, failed_usd_a_year), the failed
# shares (fail_shares) and the declined shares (declined_shares).
FAILURE_CROSSWALK = dict(
    note="How each kind of obligation enters the three failure records. headline: the failure share, the value not "
         "paid on the cash route over the value due there, wages left out of both; and failed dollars "
         "(failed_usd_a_year), that value not paid and with it each wage not paid on its first due date. "
         "failed_shares: "
         "the unpaid share of each bill or wage, each obligation once (the real failure line, clause (c), the stress "
         "dip). declined_shares: the unpaid share of each card-eligible purchase of a payer without a card or past a "
         "holder's room. Clause (d) in a run that conserves money reads failed_shares plus declined_shares.",
    bill=dict(headline="counted by value, in the value due and in the value not paid, and in failed dollars",
              failed_shares="its unpaid share, once", declined_shares="not counted"),
    first_due_wage=dict(headline="left out of the failure share (of the value due and of the value not paid); "
                        "counted in failed dollars, the part not paid on its first due date",
                        failed_shares="its unpaid share on its first due date, once, a wage being one obligation a "
                        "job and pay date",
                        declined_shares="not counted"),
    requeued_wage=dict(headline="not counted", failed_shares="not counted again: a wage is counted once, on its first "
                       "due date, and its later payment is not a new obligation", declined_shares="not counted",
                       recorded="wages_late (by_class, as payer) holds the wage not paid on its first due date"),
    wage_owed_outside=dict(headline="left out of the failure share, being a wage; counted in failed dollars, the "
                           "part not paid on its first due date", failed_shares="its unpaid share, once; under the first run's rule an "
                           "obligation of its own beside the worker's wage for the same job and pay date, and under "
                           "stress_paydays \"merged\" (the base) one obligation with every wage row of that job on "
                           "that pay date",
                           declined_shares="not counted"),
    card_eligible_purchase=dict(headline="counted by value when it is on the cash route and not paid (a holder's "
                                "purchase on its card within its room completes)", failed_shares="not counted",
                                declined_shares="its unpaid share, for a payer without a card or past a holder's "
                                "room; the purchase is lost with no fee"),
    durable_needing_credit=dict(headline="not counted", failed_shares="not counted", declined_shares="not counted",
                                recorded="a durable whose credit does not qualify is cancelled before any payment "
                                "falls due: its price is in term_cancelled (by_class, as buyer)"))
# The table of who pays and who receives, stored with each pool arm of each cell in a
# run that conserves money: a transfer, read by no verdict.
WHO_PAYS_NOTE = (
    "Who pays and who receives, from the monthly payout itself, in every arrangement of a cell "
    "(S0's as S0_who_pays_who_receives): each group's seed mean of the payout it received in cash (received) and of "
    "its own payments to intermediaries outside the economy as booked (paid_across_edge: outside interest, failure "
    "fees, card fees less rewards, conversion fees, gas, the spreads kept on its money and savings, earned-wage and "
    "the card's cash-advance and late fees), $ a person a year, by class, launch-wealth quintile and billing cycle, "
    "with everyone's mean beside (everyone). The two are not on one footing, so their difference is not stored: the "
    "payout returns the month's whole net flow across the edge, net of what households receive from outside, with "
    "money's loss of value made good and on a cash basis, and the engine records those terms for the economy only. "
    "closure_everyone closes them for everyone: received = paid_across_edge + other_across_edge (the rest of the net "
    "flow across the edge as booked: wages owed outside and other payments out, less savings income and yields "
    "received) + inflation (the part making good money's loss of value) + stock_change (minus the change in the stock "
    "booked across the edge and not yet paid, under the payout \"paid\") - kept (the part not returned, edge_kept), "
    "with gap the remainder; returned_usd_a_year is the stored total the payout returned, a person a year, and "
    "reconciled_gap_usd_a_year the payout's mean less it. \"not stored\" where the run keeps no payout. How the payout "
    "is shared, by receipts or by ownership shares, moves each group's money and so its later payments: the group test "
    "is not independent of the sharing, though the effect measured on small worlds was small (about 0.1 failed payment "
    "a person a year at most). No verdict reads it.")
# The table beside it: each group's change in money at the complete gain's zero end, stored under
# a name that says what it is.
MONEY_CHANGE_NOTE = (
    "Each group's seed-mean change in money against S0 and against M0 once completed purchases and sales net out, $ a "
    "person a year, the complete gain with sellers' extra sales counted at zero (the gain's \"zero\" end), by class, "
    "launch-wealth quintile and billing cycle, with everyone's mean beside (everyone). It is not the payout's "
    "incidence: two people with the same payout differ here when one completed a purchase the other lost "
    "(who_pays_who_receives reads the payout). Under conserved money everyone's mean differs from zero only by the "
    "arrangements' cumulative revaluation (a written-down pool loan lowers the pool's carrying value while the "
    "borrower still owes it, and a recovery reverses it), by the change in the stock booked across the edge and not "
    "yet paid in cash (under the payout \"paid\") and by what the payout keeps back (edge_kept, zero in the base); it "
    "is near zero, not zero by construction. No verdict reads it.")
# What a second run's monthly series add to MONTHLY_NOTE, in the header of its measures.json.
SECOND_MONTHLY_NOTE = (
    "In a run of the second run each arm also stores, a month after launch: returned, what the payout handed back; "
    "wages_kept, the extra layoffs' wages their payers kept; purchases_dropped, purchases dropped in the stress year "
    "(a count a person); card_debt, debt to outside card lenders; money_bt and savings_bt, households' money and "
    "outside savings as the month's average balance; out_interest, advance_fees and late_fees, outside lenders' "
    "interest and the card's cash-advance and late fees; and, behind every line of the real cost, principal-time on "
    "card credit (pt_card), on the pool's card credit to holders and to payers without a card (pt_pool_card_credit, "
    "pt_pool_nocard_card, and under the first run's rule pt_pool_card) and on term credit (pt_pool_term, pt_term), failed and bridged "
    "shares (fail_shares, bridged_shares), failure fees (penalties), pool bridges to payers without a card "
    "(nocard_bridges), card payments by count and value (card_payments, card_value), gas, pool shares held (shares_bt) "
    "and earned-wage advances (ewa_uses). Where the engine keeps them: pool_payable, what the pool owes its operating "
    "provider at the month's end, which clause (a) reads; pool_payable_most, the most it owed on any day of the month, "
    "read by nothing; payout_inflation, the inflation part of the payout; edge_accrued and edge_paid, what was booked "
    "to the edge when a debt was created and when cash moved; edge_owed, the stock booked and not yet paid; edge_kept, "
    "the part of the flow the payout does not return; card_unbilled, what holders owe their card that is not yet a "
    "loan (purchases not yet billed and the closed statement not yet due), which with card_debt is the card credit in "
    "use; edge_cleared, the cash paid in the month on amounts booked across the edge earlier; settle_held, the days "
    "held by the settlement's hold rule (a count). The pool arms add target, the capital target, pool_pt, the "
    "principal of every loan the pool carried, bridges and term loans together, the month's average (the bridges "
    "alone are P_bar), and exits_started "
    "and exits_paid_in_time, the requests to withdraw filed in the month and the part of them paid within two months, "
    "by month of filing. Money in months of mean spending a person, as above.")
# Liquidity: what each arm's ``liquidity`` record holds, stored with summary.json.
LIQUIDITY_NOTE = (
    "Liquidity by window (W1, W2), $ a person: precautionary_usd, the total precautionary money, the engine's record "
    "of households' buffers chosen at dealing and the pool's idle cash, each part beside, with idle P (the two-month "
    "lowest P balance) beside them and not in the total, since it sits inside the buffers, the "
    "month's mean; shortfall_covered_usd_a_year, what payers' own money and same-day savings could not pay "
    "and a lender paid, in every arm alike: pool bridges (bills, wages, purchases and card statements), holders' card "
    "bridging of bills and wages (their cash advances since card limits), card statements left to "
    "revolve on the card, Comet bridging (M0) and earned-wage "
    "advances, each part beside, a year; precautionary_per_dollar_covered, the first over the second; and failed "
    "payments a year, by value (failed_usd_a_year: bills and declined card-eligible purchases not paid, and wages "
    "not paid on their first due date) and in the real failure "
    "line's unpaid shares (failed_shares_a_year). Counting the shortfall the same way in every arm, card statements "
    "included, is a reading of the rule. None for a window the run does not reach.")
# The real part's lines, each arm's saving against S0 read line by line; earned-wage access's declared cost is $2 a
# use.
REAL_LINES = ("card_credit", "term_credit", "failed_payments", "card_rails", "p_rail", "holding", "earned_wage",
              "total")
# The classes of the no-harm test: card holding x income source, fixed at the population draw and
# the same in every arm, labelled 2 * card holder + business income, in this order.
CLASSES = ("no card and wage income", "no card and business income", "card and wage income",
           "card and business income")
# The region reading's groups by name, in the order the paired differences store them.
GROUP_NAMES = dict(**{"class": CLASSES}, quintile=tuple(f"launch-wealth quintile {k + 1}" for k in range(5)),
                   cycle=("short billing cycle", "long billing cycle"))
# What each arm's paired differences ("against", ``differences``) hold, stored with cells.json, with the class
# labels.
AGAINST_NOTE = ("Each arm's paired differences in one seed against S0, for U, M1 and M2 against M0 too, and for M1 "
                "against U (what demurrage adds), on the same "
                "random numbers, $ a person a year after launch; a positive saving or gain favours the arm. The gains "
                "are read in full (M2's indexation is the holder's own yield, not an issuer "
                "transfer; under demurrage the pool's share of the reserve return is the contract's), "
                "as claim (d) reads them. Groups are launch-wealth "
                "quintile x short (1-15 days) or long (30-60 days) billing cycle, labelled quintile * 2 + long, "
                "poorest first. "
                "Classes are card holding x income source, fixed at the population draw and the same in every arm"
                ", labelled 2 * card holder + business income: " + ", ".join(CLASSES)
                + ". Beside them, reported and not tested, the mean gain by the arm's own role in W2: investor (held "
                "pool shares in a W2 month), borrower (borrowed from the pool in a W2 month), daily user (in P at "
                "least half of W2) and never participant (never in P after launch); the roles arise in the run, "
                "differ by arm and overlap. Beside them too, the mean gain of people not flagged and flagged as payers "
                "in chronic deficit at launch (spending above income received over the burn-in, with a liquid cushion "
                "below one month of their own spending; the same in every arm), in that order: they "
                "stay in the headline and are reported apart. NaN marks an empty group, class, role or flag. "
                "gain_usd_a_year and its breakdowns are the wealth measure, the end-wealth difference. complete_gain"
                ", which claim (d) reads, adds the difference in purchases received (a person's "
                "own service and shock purchases completed as buyer and the price of each durable it bought that "
                "settled), with sellers' extra sales at face value (\"face\") and, less the difference in sales, at "
                "zero (\"zero\"), each with the same breakdowns; complete_gain_parts_usd_a_year holds the mean of each "
                "part (wealth, purchases_completed, durables, sales, with purchases_lost beside), and sales_usd_a_year "
                "and sales_usd_a_year_by_* each group's mean difference in sales (the face value of service and shock "
                "purchases completed to the person as seller, before any merchant fee, plus the price of each durable "
                "it sold), so the gain at a surplus share s is zero + s x sales. Wages are in none of them. "
                "The cash-advance bound: advance_saving_usd_a_year (with _by_quintile and "
                "_by_class) is the mean of what a person saves on the card's cash-advance fees and cash-advance "
                "interest in this arm, the other arm's less this arm's, to first order with no feedback; bound, beside "
                "the wealth gain and inside each end of complete_gain, holds the same breakdowns of the gain less that "
                "saving. Stored only, read by no rule: dispersion (wealth, face, zero), the share of people whose gain "
                "is below -$2 a year and the 5th, 25th, 50th, 75th and 95th percentiles of the gain; and "
                "gain_usd_a_year_at_month, the mean wealth gain at 36 and 48 months after launch and at the end "
                "(\"end\"), each annualised over the months elapsed, a month the run does not reach left out.")
# What each arm row's earned-wage, chronic-deficit and card-bridging reports hold, stored with cells.json.
REPORT_NOTES = dict(
    earned_wage="Earned-wage access after launch: holders and users (people with an advance after launch), each as a "
                "share of people, and per user a year the advances (payer-days with one), their fees and their "
                "value, $; None with no user. The S0 check reads it against the CFPB's 27 advances and $68.88 of "
                "fees a user a year.",
    chronic="Payers in chronic deficit, flagged at launch from the burn-in and the same in every arm: the share "
            "flagged and, for people not flagged and flagged, failure fees ($), failed bills and wages in unpaid "
            "shares (the real failure line's unit) and payments to intermediaries outside the economy ($), a person "
            "a year after launch; None for an empty group.",
    card_bridging="Card holders' card bridging of the bills and wages their money could not pay, after launch, since "
                  "card limits their cash advances, $ a person a year (over everyone) and a holder a "
                  "year; None with no holder. The S0 check reads it against US cash advances, $112 to $118 a consumer "
                  "unit a year (large issuers only). Beside it, a holder a year: the cash-advance and late fees "
                  "charged and the card balances charged off at 180 days past due, $, and the share of holders whose "
                  "line a charge-off closed after launch; holders are the population's card holders, their class.",
    by_class="Credit and purchases by class (business credit is read inside the one population, "
             "with no separate model or run), in every arm, S0 included: the arm's own levels, $ a person a year after "
             "launch, the mean in each class in the order of the classes (card holding x income source), NaN for an "
             "empty class, with class_sizes beside. Credit, by the person named, in the model's money (P in M2 for "
             "the pool's lending): bridge_pool, pool bridging drawn for payments and card statements; bridge_card, "
             "card bridging of payments the holder's money could not pay (its cash advances since card limits) "
             "plus statements left to revolve, not card purchases paid at the statement; advance_card, "
             "the cash advances alone; fees_card, the card's cash-advance and late fees charged; charged_off_card, "
             "the card balance charged off at 180 days past due; bridge_comet, Comet borrowing (M0); "
             "bridge_refused, pool bridging "
             "asked for and not drawn; term_pool and term_outside, instalment principal lent by each lender; "
             "term_cancelled, the price of instalment requests that needed credit and did not qualify; "
             "interest_pool, interest_card and interest_outside, interest accrued on the person's pool loans, card "
             "balances and other outside loans (instalment loans, Comet bridges, overdrafts); wages_late, as payer, "
             "wages not paid on their first due date. Purchases, as in the complete gain: completed and lost as "
             "buyer, durables bought, sales as seller. Failures, as payer (holders can fail since card "
             "limits): failure_fees, the failure fees charged, and failed, new failed payments by value. Classes "
             "are the population's card holding, which a charge-off does not change. Records only: no rule or "
             "verdict reads them.")
# Failure counts, stored for the unit change and the monthly cap: the monthly caps at which each arm's spread of fee
# units is read (2 a month, beside 3 and 5), and what each stored field holds, by the part of an arm's failure counts
# it sits in: monthly, a person a month in each month after launch; a_year, a person a year after launch; with the
# development seeds, payer_months, the columns of the table of every person-month with any count, and S0's buffers.
MONTHLY_CAPS = (2, 3, 5)
FAILURE_LABELS = dict(monthly=dict(
    fees_usd="failure fees charged, $ (at most one fee a payer a day and, under the monthly cap, the Economy's "
             "fees_a_month a payer a month)",
    fail_units="failed bills and wages in fee units: a payer-day's unpaid shares, at most one (the fee's count before "
               "the monthly cap, and the real part's under the first run's rule)",
    fail_shares="failed bills and wages in unpaid shares, each bill or wage once (a re-queued wage not again; the real "
                "failure line's unit)",
    fail_items="whole bills and wages a bank paying each payer's day smallest first would return from the money the "
               "day paid: the fewest any order returns",
    fail_days="payer-days with a failed bill or wage",
    declined_shares="declined card-eligible purchases of payers without a card, or past a holder's room on its line, "
                    "in unpaid shares (no fee; the purchase is lost; not a failed bill)",
    declined_items="declined card-eligible purchases in whole purchases, from the same smallest-first pass",
    bridged_shares="bills and wages that the pool's draw paid in place of failing, in shares: for payers without a "
                   "card, and for a holder the part of its draw that its cash line could not have taken, "
                   "the least of the draw and the shortfall beyond the cash line's room",
    bridged_items="whole bills and wages the pool's draw kept from being returned, read as bridged_shares is",
    bridged_card="card-eligible purchases of payers without a card, or past a holder's room, that the pool's draw "
                 "paid, in shares (new lending, not a replaced failure)",
    bridged_days="payer-days with a pool bridge to a payer without a card (the real part's count under the first run's rule)",
    payers="share of people with any fee unit in the month",
    binds="share of people whose month left a failed bill or wage without its fee: the run's monthly cap binds (the "
          "S0 check's share of payers the cap binds, over people)",
    binds_of_payers="share of the month's payers (people with any fee unit) whose month left a failed bill or wage "
                    "without its fee: the S0 check's share of payers the cap binds",
    capped_k="fee units a person left under a monthly cap of k",
    binds_k="share of people whose fee units exceed a monthly cap of k (over payers: binds_k / payers)",
    heaviest="fee units of the month's heaviest payer"))
FAILURE_LABELS.update(
    a_year=dict(**{key: FAILURE_LABELS["monthly"][key] for key in ("fees_usd", "bridged_days", *FAILURE_COUNTS)},
                fees_usd_cap_k="failure fees under a monthly cap of k fee units a person, $",
                heaviest_fee_units="fee units a year of the person with the most over the run (their total times "
                                   "12 / months; not the month's heaviest payer)"),
    payer_months=dict(month="month after launch, from 1", person="the person's place in the population",
                      **{key: FAILURE_LABELS["monthly"][key] for key in ("fees_usd", *FAILURE_COUNTS)}),
    buffers="S0's buffer chosen at dealing, in months of mean spending: a row a month after launch, a column a person")
# The uncapped counts are an accounting count with no cap applied.
FAILURE_NOTE = ("Counts only: no rule reads them and nothing here enters a verdict, though the real part's failure "
                "line reads the same fail_shares and bridged_shares series. fail_units is the daily-capped "
                "count before the monthly cap; the fee charged under it is fees_usd. No cap applies in "
                "counting fail_shares, fail_items or the declined and bridged counts, but the path they are counted on "
                "still depends on the caps, through the fee debt ranked ahead of the pool, the pool's "
                "same-day limit and the buffer replays' failure cost; a path free of the caps would need its own run. "
                "Whole items count on the settled path, where every payment of a payer is paid the same share. The "
                "dollar records keep declined card-eligible purchases with failed bills (failure_share, which "
                "leaves wages out) and with failed bills and wages not paid on their first due date "
                "(failed_usd_a_year); these counts keep them apart. The labels follow each arm's parts: monthly holds "
                "values a person a month in each month after launch, a_year a person a year after launch, and "
                "payer_months one person in one month.")


# The registered claim's statistics (docs/ANALYSIS_PLAN.md), read from the cells and their jobs: analysis only, no
# run. The register is docs/DECISIONS.md (the claim, clauses (a) to (e); the real cost; the statistics; the distress
# levels). Where it leaves a choice open, the reading taken is the one that leans against CPM, and CLAIM_NOTE names
# each.
CLAIM_ARMS = ("M1", "M2")             # the claim is read for M1 and M2 separately
CLAIM_CONFIDENCE = 0.95               # two-sided 95% t intervals
CLAIM_ALPHA = 1 - CLAIM_CONFIDENCE
CLAIM_MARGIN = REGION_MARGIN          # -$2 a person a year, clauses (b) and (d)
FAIL_USD = 2.0                        # the real failure line's $2 a unit, which a pool rescue is costed at as registered
DIP_MARGIN = 1.0                      # clause (e): the dip's upper bound is at most one failed payment
# The months after launch the dip is summed over, both included: the 36 months from the first stress
# month. A run's own months are read from its Economy (``steady.dip_window``): months 121 to 156 in the second run.
DIP_MONTHS = (25, 60)
STRESS_LEVELS = DISTRESS[1:]          # clause (e)'s levels, tested in this order at level 0's Bonferroni level
# Clause (e)'s headline level (the harsh stress), read beside the highest level withstood:
# 2 points, 2009's wage loss before unemployment insurance (US wages and salaries fell 4.29% in 2009 against 2008, FRED
# A576RC1A027NBEA, 6,531.9 to 6,251.4 $bn; at 2 points the stored development map has 4.34% more jobs without a wage
# over the stress year than at level 0, so that share of the year's wage bill goes outside). Every level still runs and
# is tested in order.
STRESS_HEADLINE = 0.02
STRESS_HEADLINE_LABEL = "2009's wage loss before unemployment insurance"
SEED_POWER, SEED_CAP = 0.8, 100       # the seed count: 80% power at a true difference of zero, at most 100 seeds
# The seed count's allowance for the spread being an estimate: each reading's pooled spread is
# taken at the upper end of its one-sided interval at this assurance, the same level as the power.
SEED_ASSURANCE = 0.8
BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 10000, 20261112   # the bootstrap check: resampled seeds, a fixed stream
# The bootstrap's resamples in a run of the second run, on the same stream: at the stricter level
# over 42 cells the two-sided tail, 0.05 / 84, rests on about 119 resamples in place of about 6.
BOOTSTRAP_DRAWS_SECOND = 200_000
CLAIM_NOTE = (
    "The registered claim read cell by cell for M1 and M2 (claim_statistics), beside the verdict, which is unchanged. "
    "Each clause holds status pass, fail or not applicable at 95% (status) and at the arm's Bonferroni level "
    "(status_bonferroni: 0.05 over 21 cells, 14 for M2's cells above its declared limit), with its numbers at both. "
    "An interval check stores the seed mean, the two-sided t interval, the bootstrap percentile interval of the seed "
    "mean (10,000 resamples of seeds), and the reading on each (supported, inconclusive when the interval straddles "
    "the margin, falsified when it lies wholly on the wrong side); a check holds only when both read supported. "
    "(a): households hold 90% with P routing in a share of seeds whose Wilson lower bound is above one half; "
    "no seed records the issuer would leave; no seed has issuer backing top-ups; and the cell reads Persistent by the "
    "statistics rule. The pool's own W2 margin (lower bound above zero) and the joint issuer-and-pool test (lower "
    "bound at or above zero) are stored beside and required only in holds_as_first_registered: because the pool "
    "pays its own way when it runs without outside money, and with break-even coupons both centre on zero by "
    "construction. (b): the real resources saved against M0 and against S0, each lower bound at or above -$2 a "
    "person a year; a saving only where both lower bounds are above zero; the read-outs beside it are the break-even "
    "cost of one rescued payment (the cost x at which the arm and M0 use the same real resources: x = 2 - (arm less "
    "M0 in real cost) / (rescued shares less M0's), on seed means) and the real cost per dollar of purchases "
    "completed in each arm, cents. (c): failed shares (the real failure line's unit) lower than M0's (upper bound "
    "below zero) and purchases completed plus durables bought higher (lower bound above zero); against S0 reported "
    "beside; it holds by construction, so it is reported and is not evidence. (d): every class, quintile and billing "
    "cycle group's lower bound of its mean complete gain at or above -$2 against S0 at both ends of the bracket and "
    "against M0 at face (no issuer transfers exist to net out). (e): for a cell passing (a), (b) and (d) at 95% at "
    "level 0, levels 0.5, 1, 1.5 and 2% are tested in order at level 0's Bonferroni level, stopping at the first "
    "failure; a level is withstood when (a) to (d) hold on its run and the dip's upper bound against S0's and against "
    "M0's is at most one failed payment a year; the dip is each seed's cumulative excess of failed shares a person "
    "over months 25 to 60, the level's run less the same seed's run at level 0, per year (the 36-month sum over 3; "
    "the sum is stored beside); (e) reports the highest level withstood and is not part of all. Under the harsh stress "
    "the extra layoffs' wages leave the household economy, with no unemployment insurance, "
    "and (e)'s headline is the 2% level, 2009's wage loss before unemployment insurance: headline.withstands is True "
    "when the highest level withstood reaches it, False when a level up to it was tested and not withstood, None when "
    "(e) is not applicable or the level was not run. "
    "all: (a), (b) and (d) pass, as the claim row words a passing cell; all_bonferroni the same at the Bonferroni "
    "level. near_the_line: the Persistent share's "
    "95% Wilson interval contains one half, or an interval check of (a) to (d) is inconclusive or its t and bootstrap "
    "readings differ. underpowered: the cell's own spread needs more seeds than it ran (the seed count's rule at its "
    "Bonferroni level), and an underpowered cell cannot enter the region. Leaning against CPM where a row is open: "
    "(a) also asks Persistent and no issuer top-up; the bootstrap must agree with the t interval; (c) counts durables "
    "with purchases; a region is the largest block of passing cells joined by an edge (not a corner), ties named; "
    "underpowered is read against the seeds the cell ran. "
    "Three-way readings: each clause and the cell store reading, supported, inconclusive (an "
    "interval straddles its margin, or the t and bootstrap readings disagree) or falsified (the t and the bootstrap "
    "interval both lie wholly on the wrong side, or a falsifier fires), with decided_by naming the comparison or group that "
    "decided it, at 95% and at the Bonferroni level; status keeps pass and fail. Worse than M0 (worse_than_M0) has "
    "four parts, each named with whether it fired: completed trade, harm to any group, borrowers' credit cost (V2, "
    "the rate: interest over principal-time, the arm less M0, interval wholly above zero on t and bootstrap; interest "
    "a person a year is a report) and owners' realised return (V4, W2 return less DeFi's savings rate, interval "
    "wholly below zero on t and bootstrap); V2 or V4 firing counts every paired seed worse, so the cell has no Persistent seed and fails (a) "
    "and the region, as trade or a harmed group does. (d) reads every required group with the t and bootstrap check; "
    "a group with no interval does not support it (undefined_groups). Each stress leg keeps every clause's full "
    "block and clause (b)'s read-outs (real_cost at that level). The seed planner pools the yearly dip's spread. "
    "The cash-advance bound: d_bound is clause (d) read a second time, with the same groups, "
    "yardsticks, ends, intervals and margin, on each gain less the cash-advance fees and interest the person saves "
    "against the yardstick, to first order with no feedback; d keeps the clause without the bound. all and all_bonferroni ask "
    "(d) both without and under the bound, so in_region, the region and holds somewhere do too, and a stress slice's "
    "cell needs its level-0 cell to pass all; all_as_built and all_bonferroni_as_built keep (a), (b) and (d) without the bound. "
    "The cell's reading and decided_by (at 95% and Bonferroni) take the worse of the two (d) readings, with the "
    "readings without the bound beside (reading_as_built and so on). (e), near_the_line and the stress legs read (d) without the bound.")
# The claim's note in a store of the second run, filled from the run's own Economy by ``claims.claim_note``: its
# windows, its cells, its DeFi, its clause (d) and its dip's months.
SECOND_CLAIM_NOTE = (
    "The claim of the second run, read cell by cell for M1 and M2 (claim_statistics), beside "
    "the verdict, which is unchanged. Every steady-state reading is read in both of the run's windows, {windows}, and "
    "holds only if it holds in both; a falsifier fires if it fires in either. Each clause holds status pass, fail or "
    "not applicable at 95% (status) and at the arm's Bonferroni level (status_bonferroni: 0.05 over {cells_m1} cells "
    "for M1, the {rates} registered outside rates by the seven launch levels, and over {cells_m2} for M2, whose cells "
    "at a zero real reserve rate are its declared limit), with its numbers at both. An interval check stores the seed "
    "mean, the two-sided t interval, the bootstrap percentile interval of the seed mean (200,000 resamples of seeds, "
    "so that the stricter level's tails rest on more than a handful of them), and the reading on each (supported, "
    "inconclusive when the interval straddles the margin, falsified when it lies wholly on the wrong side); a check "
    "holds only when both read supported. {defi} (a): in each window the pool is household-owned with capital present "
    "in every month, with P routing, in a share of seeds whose Wilson lower bound is above one half (the 90% reading: "
    "households are the pool's only owners, so it holds wherever the pool has capital and says nothing of how much of "
    "the pool's need that capital meets; the pool's capital over its target in each window is stored beside it, "
    "capital_over_target_<window>); no seed records the issuer would leave; no seed has issuer backing top-ups, and no "
    "seed's pool owes its operating provider more than half a cent a person at any month's end from the first month of "
    "the early window to the run's end, the stress year and every year after it included (provider; clause (a) reads "
    "month ends, and the most owed on any day of a month is reported beside it, deciding nothing; a seed whose run "
    "keeps no record of it, or has a month with no value, does not pass); and the cell reads "
    "Persistent by the statistics rule. The pool's own margin and the joint issuer-and-pool test are stored beside and "
    "required only in holds_as_first_registered. (b): the real resources saved against M0 and against S0 over the "
    "whole run, each lower bound at or above -$2 a person a year; a saving only where both lower bounds are above "
    "zero; it reads no destination of any money, so conserving money does not touch it. The saving it reads includes "
    "the saving on the payment rail: card payments' processing, fraud and network costs against the gas of P payments "
    "(card_rails and p_rail). Beside it, deciding nothing: the same intervals in each window "
    "(by_window), and for the whole run and each window the payment-rail lines apart from all other lines (rail_apart, "
    "rail and other); the monthly series behind every line are stored. The break-even cost of one rescued payment and "
    "the real cost per dollar of purchases completed are read beside. (c): failed shares (the real failure line's "
    "unit) lower than M0's and purchases completed plus durables bought higher; against S0 reported beside; reported "
    "and not evidence. {clause_d} (e): for a cell passing (a), (b) and (d) at 95% at level 0, levels 0.5, 1, 1.5 and 2 "
    "points are tested in order at level 0's Bonferroni level, stopping at the first failure; a level is withstood "
    "when (a) to (d) hold on its run and the dip's upper bound against S0's and against M0's is at most one failed "
    "payment a person a year; the dip is each seed's excess of failed shares a person over the 36 months from the "
    "first stress month, {dip_months}, the level's run less the same seed's run at level 0, per year (the 36-month sum "
    "over 3; the sum is stored beside); the headline is the 2-point level; (e) is reported and is not part of all. "
    "all: (a), (b) and (d) pass, as the claim words a passing cell; all_bonferroni the same at the Bonferroni level. "
    "The region (regions) is pointwise, each cell read at 95% (all, in_region); beside it regions_bonferroni is the "
    "region of cells passing at the arm's stricter level (all_bonferroni, in_region_bonferroni), the level of holds "
    "somewhere; a stressed slice's cell needs its no-distress cell to pass and not to be "
    "underpowered in both. near_the_line: the Persistent share's 95% Wilson interval contains one half, or an interval "
    "check of (a) to (d) is inconclusive or its t and bootstrap readings differ. underpowered: the cell's own spread "
    "needs more seeds than it ran, and an underpowered cell cannot enter either region. Three-way readings: each "
    "clause and the cell store reading, supported, inconclusive or falsified, with decided_by naming the comparison or "
    "group that decided it, at 95% and at the Bonferroni level. Worse than M0 has four parts, each named with whether "
    "it fired (completed trade, harm to any group, borrowers' credit cost, owners' realised return against DeFi's "
    "savings rate, read in each window); any firing counts every paired seed worse and fails (a) and the region. Under "
    "the quote reading the saver meets the entry hurdle by construction: at a positive capital target the quote is "
    "owners' alternative and a tie enters, so capital under it shows the pool's room and its exits, not a saver's "
    "choice; the realised record is the reading that tests whether savers stay. {seeds}")
# Clause (d)'s part of SECOND_CLAIM_NOTE in a run that conserves money: each group's own failed payments.
SECOND_CLAIM_D = (
    "(d), no group is harmed: for each of the eleven groups (the four classes, card or not by wage or business income; "
    "the five launch-wealth quintiles; the short and the long billing cycle, as the complete gain defines them), its "
    "own payments that did not complete as payer, its failed shares of bills and wages plus its declined shares of "
    "card-eligible purchases (each part stored beside the sum, and failure_crosswalk says how each kind of obligation "
    "enters each record), a person a year in the real failure line's unit, the arm less S0 and the arm less M0 paired "
    "by seed, has an upper bound at or below one failed payment a person a year on the t interval and on the "
    "bootstrap, in each window: 11 groups, 2 yardsticks, 2 windows, 44 checks, and the clause holds only when every "
    "check is supported. A group with no interval does not support it and is named (undefined_groups); groups holds "
    "each check by yardstick and window, passes which of them pass, and highest the highest upper bound with its "
    "group, yardstick and window. The clause as first registered, the complete gain at both ends, and its reading "
    "under the cash-advance bound are computed and stored as d_as_first_registered and d_bound_as_first_registered and "
    "read by no verdict: with money conserved the mean gain with sellers' extra sales at zero differs from zero only "
    "by the arrangements' cumulative revaluation of loans, by the change in the stock booked across the edge and not "
    "yet paid (under the payout \"paid\") and by what the payout keeps back (edge_kept, zero in the base), so it "
    "measures a transfer between groups. The stress legs, near_the_line, the region and holds somewhere read (d) in "
    "this form. The clause is not independent of how the payout is shared, which moves each group's money; the effect "
    "measured on small worlds was small. Who pays and who receives by group, from the payout itself, is stored with "
    "each arrangement of each cell (who_pays_who_receives, and S0_who_pays_who_receives for banks), and each group's "
    "change in money at the gain's zero end beside it (money_change_at_zero_end); neither decides anything.")
# Clause (d)'s part of SECOND_CLAIM_NOTE in a run of the second run that does not conserve money: as registered first.
SECOND_CLAIM_D_REGISTERED = (
    "(d): every class, quintile and billing cycle group's lower bound of its mean complete gain at or above -$2 "
    "against S0 at both ends of the bracket and against M0 at face, as first registered, and again under the "
    "cash-advance bound (d_bound); all asks both.")
# DeFi's part of SECOND_CLAIM_NOTE, by the run's ``usdc_yield``.
SECOND_CLAIM_DEFI = dict(
    none="DeFi (M0) is stablecoin payments with no yield and no credit: the stablecoin pays "
         "its holder nothing and nobody holds the collateral its lending needs, so nobody can borrow (defi_credit "
         "beside M0's results stores the people able to borrow and the borrowing drawn, both zero); owners' return "
         "is set against zero.",
    reserve="DeFi (M0) is stablecoin payments that pay their holder the reserve yield less the stablecoin issuer's "
            "spread, a side reading of the second run, with no credit, as in the base; owners' return is set against "
            "that savings rate.")
# The seed rule's part of SECOND_CLAIM_NOTE (the rule's count rounded up to the next ten).
SECOND_CLAIM_SEEDS = (
    "The seeds: the planner (seeds) reads the cost reading and the yearly dip at the Bonferroni level above, and the "
    "second run's confirmation seeds are a block never run, from 20261701 upward (the first run's block, 20261401 to "
    "20261460, is not reused); their count is the planner's count at the spreads' bounds from the three-seed map at "
    "4,000 people, rounded up to the next ten and at least 30 (8 gives 30, 26 gives 30, 33 gives 40, 44 gives 50), at "
    "most 100 (at 10 seeds a stricter level's Wilson test of a share of seeds cannot pass even with every seed "
    "passing; at 30 it passes with 24). The planner's second_run block stores the fewest passing seeds each level "
    "needs at the count (attainable) and, beside it, changing nothing, the count were each spread given one degree "
    "of freedom a seed (by_seed_freedom). The one declared extension takes underpowered cells to twice the count on "
    "the next seeds of the same block.")

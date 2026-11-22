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
DISTRESS = (0.0, 0.005, 0.01, 0.015, 0.02)   # layoffs per job a month in the distress year (decided 30 Oct)
# Each distress level is the extra monthly rate per job in the distress year, above normal job loss (decided 3 Nov),
# labelled by its total rate and by the share of jobs without a wage at month 36, about 1.9, 3.4, 4.9, 6.3 and 7.7%
# (by hand, unverified; the S0 check reads the runs' share against them, within 0.5 points).
STOCK_LABELS = (1.9, 3.4, 4.9, 6.3, 7.7)


# The population of the final map and the confirmation runs (decided 12 Nov: 4,000 people, a declared
# departure from the size check's written rule, which takes 8,000): the runner's default --n.
POPULATION = 4000
# The arms each job runs beside S0, and among them the pool arms: U is M1 with no demurrage (decided 4 Nov).
ARMS = ("M0", "U", "M1", "M2")
POOL_ARMS = ("U", "M1", "M2")
BASE = (0.044, 0.6)
GRID = dict(r_out=RATES, a0=A0S, distress=DISTRESS)   # the full grid, of which a run may select cells (``selected``)
# The rate cut (decided 17 Nov 2026, after the confirmation map under the quote rule was read): finer outside rates
# between the grid's 2% and 4.4%, where the claim's edge lies and the grid has no level. They stand beside the grid
# and are never part of it: the full grid, the registered claim and every reading tied to the grid's rates stay as
# they are. A run that selects one is exploratory, on the exploratory seeds (from 20261601, the 12 Nov row on
# seeds) and never on the confirmation seeds, and is labelled so wherever it is reported.
SIDE_RATES = (0.025, 0.03, 0.035)
# The low rates (decided 18 Nov 2026): outside rates under the grid's 2%, where the charge is squeezed against the
# custody cost. Beside the grid like the rate cut, for the exploratory side checks on the side seeds only.
LOW_RATES = (0.005, 0.01)


def rate_axis(rates):
    """The outside rates a run's region is joined along and its record lists: the grid's own when every rate the run
    covers is the grid's, so a run of the grid reads exactly as before; else the run's rates in order (a run of the
    rate cut)."""
    rates = set(rates)
    return RATES if rates <= set(RATES) else tuple(sorted(rates))


SHORT = 15                          # billing cycles of 1-15 days are "short", 30-60 days "long" (harm groups)
WORKERS = 12                        # the default: more ran out of memory on a 31 GB laptop (the 13 Nov review)
WORKERS_MOST = 12                   # the default of --most-workers; a larger --workers is refused (``main``)
# The paired distress reading (decided 31 Oct): its measures (monthly series), the arms each applies to and the
# scale each is reported on (points of spending, points of participation, $ a person); a measure has recovered once
# its gap stays within RECOVERY_SHARE of its largest gap for RECOVERY_MONTHS running; the issuer is rewarded for
# failure when its distress-year wallet is higher in at least REWARD_SHARE of paired seeds.
MEASURES = dict(failures="failure_share", participation="A", pool_capital="N", exits="exit_requested",
                issuer_wallet="issuer_wallet")
APPLIES = dict(S0=("failures",), M0=("failures", "participation"), **dict.fromkeys(POOL_ARMS, tuple(MEASURES)))
SCALE = dict(failures=100.0, participation=100.0, pool_capital=DOLLARS, exits=DOLLARS, issuer_wallet=DOLLARS)
RECOVERY_SHARE, RECOVERY_MONTHS, REWARD_SHARE = 0.25, 3, 0.8
# The wage-loss path behind the distress reading (decided 3 Nov), stored for every arm beside the measures and read
# by none of them yet: jobs_without_wage is the share of the month's job-days on a job in a spell (each wage contract is
# one job, so this is the month's average share of jobs paying no wage), jobs_without_wage_last_day the share of jobs in
# a spell on the month's last day, and wages_withheld the wages their payers kept, in months of mean spending a person
# (times DOLLARS, $ a person that month). Both the average and the last day are kept (decided 4 Nov). The spells
# are the same in every arm; the wages withheld follow each arm's spending. Since the harsh stress (decided 14 Nov
# 2026) payers keep only the wages of normal job loss, and wages_out holds the wages of the distress year's extra
# layoffs, which their payers owe to the outside and nobody in the economy receives, in the same units.
WAGE_LOSS = dict(jobs_without_wage="laid_off", jobs_without_wage_last_day="laid_off_last_day",
                 wages_withheld="wages_withheld", wages_out="wages_out")
# Monthly series stored with every job (3 Nov), one value a month after launch, None where undefined: households'
# capital and credited income (pool arms), crossings between E and P (CPM arms), and in every arm the mean buffer
# chosen at dealing by people without a card and by card holders, in months of mean spending (the 3 Nov review: S0's
# buffers are reported, and those of people without a card set against them).
CROSSINGS = ("crossings", "crossed", "conversions", "converted")
OWNERS = ("owners_capital", "owners_income", "owners_income_net")
BUFFERS = ("buffer_nocard", "buffer_card")
# The contract's monthly path in the pool arms (5 Nov), the engine's own series: participation A, pool capital N and
# its limit N* (Q), demurrage c on wallet P, its coverage of the bridging capital cost and its share theta of
# bridging finance, the rate a bridge is sealed at r_b, the coupon r_g and the published quote. Rates are a month (P
# terms in M2), money in months of mean spending a person.
CONTRACT = ("A", "N", "Q", "c", "coverage", "theta", "r_b", "r_g", "quote")
# The harsh stress's read-outs (decided 14 Nov 2026), in every arm, the engine's own series, read by no rule:
# households' money (E and P) and outside savings at the close, wallet P (the month's average, the W demurrage's
# terms read), the pool's bridge book (its average principal, the B they read), statements left to revolve on the card,
# pool loans written off, the wages of extra layoffs sent outside, the failure share of hit workers (the earners of a
# job with a day in a spell that month) and of everyone else, and hit workers' failed shares a person.
STRESS = ("liquid", "savings", "p_bt", "P_bar", "revolved", "written_off", "wages_out", "failure_share_hit",
          "failure_share_rest", "fail_shares_hit", "slow_days", "most_sweeps")
# The pool run under the harsh stress (decided 15 Nov 2026: declared as the stress boundary, shown month by month),
# in the pool arms, the engine's own series, read by no rule: the pool's cash and the cash new loans may take at the
# close, the cash set aside for exits, the money offered at the dealing and the part that found no room, exits paid and
# owners filing a new exit request (a count), pool term principal on the book, bridges drawn over wanted, and the
# month's write-offs of bridges and of term loans (with term lending kept, decided 15 Nov 2026, the two parts are
# shown apart). Exit requests are stored monthly already with the distress measures (measures["exits"]).
POOL_RUN = ("pool_cash", "cash_to_lend", "exit_set_aside", "offers", "offers_unused", "exit_paid", "exits_filed",
            "term_pool", "bridges_drawn_over_wanted", "written_off_bridge", "written_off_term")
# Mean net wealth in every arm (15 Nov 2026), read by no rule. The failure share is stored monthly already with the
# distress measures in every arm (measures["failures"]).
WEALTH = ("mean_wealth",)
# The settlement's records of failure passed along and of dependence on netting (the robustness plan, section 4), in
# every arm, the engine's own series, read by no rule (``CHAIN_SERIES``).
CHAINS = CHAIN_SERIES
MONTHLY = dict(S0=BUFFERS + STRESS + WEALTH + CHAINS, M0=CROSSINGS + BUFFERS + STRESS + WEALTH + CHAINS,
               **dict.fromkeys(POOL_ARMS,
                               CONTRACT + OWNERS + CROSSINGS + BUFFERS + STRESS + POOL_RUN + WEALTH + CHAINS))
MONTHLY_NOTE = (
    "One value a month after launch, None where undefined, in the engine's units: rates a month (P terms in M2), money "
    "in months of mean spending a person ($6,440), shares as shares. In the pool arms the pool run's read-outs "
    "(15 Nov 2026): pool_cash and cash_to_lend at the close, exit_set_aside (the cash not owed to the pool's creditors "
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
# The region reading (5 Nov), from the decided rows. A cell of a pool arm is in the stable region when its pool forms
# and persists (the cell reads Persistent by the statistics rule, 3 Nov: the Wilson lower bound of its share of
# Persistent seeds above one half), the issuer never records "would leave" (claim (a)), and every class, launch-wealth
# quintile and billing-cycle group (claim (d)'s groups) has a mean paired complete gain whose 95% t lower bound across
# seeds, against S0 and against M0 (REGION_AGAINST), read in full (decided 5 Nov: M2's indexation is the holder's
# own yield, so no gain is netted of issuer transfers), is at or above claim (d)'s margin, -$2 a
# person a year: the CFPB's servicing uplift per overdraft transaction (overdraft rule, December 2024), the value of the
# real failure cost (3 Nov). Claim (d) reads the bound against both (the 5 Nov review: the mean against S0 alone read
# wider than the claim); the means are kept beside. The complete gain (decided 11 Nov) is the wealth change plus
# purchases received, read at both ends of a bracket, sellers' extra sales counted at face value and at zero. The value
# of completed trade is not assumed, and against DeFi the result is reported as a break-even value (decided 11 Nov,
# second round): so the clause holds when every group's bound against S0 passes at both ends and every group's bound
# against M0 passes at face, and each yardstick's break-even surplus share, on the bounds and on the means, is stored
# with the wealth gain's own reading beside. Owners' return less their alternative stays reported only (decided
# 11 Nov), and the entry rule's two readings, quote and realised (``Economy.entry_reads``), are run as bounds at
# confirmation.
# M2's cells at a zero real reserve rate are its declared limit, kept outside the region (3 Nov). VERDICTS names each
# reading, the first condition a cell fails, in the order checked, then the stable region.
REGION_MARGIN = -2.0
# The paired differences' dispersion and time read-outs (15 Nov 2026), stored only: the percentiles of each person's
# gain, and the months after launch the mean wealth gain is also read at, beside the end.
PERCENTILES = (5, 25, 50, 75, 95)
GAIN_MONTHS = (36, 48)
REGION_GROUPS = ("class", "quintile", "cycle")
REGION_AGAINST = ("S0", "M0")
VERDICTS = ("declared limit", "no pool", "not persistent", "issuer leaves", "a group loses", "stable")
REGION_NOTE = (
    "The region reading of each pool arm in each cell (5 Nov), from the decided rows. In the stable region when the "
    "pool forms and persists, the issuer stays and no group loses: the pool forms in some seed (households hold pool "
    "capital in a month after launch); the cell reads Persistent by the statistics rule (3 Nov: the Wilson lower bound "
    "of its share of seeds above one half), a seed counting when its own verdict is Persistent; the issuer records "
    "\"would leave\" in no seed (claim (a)); and every class, launch-wealth quintile and billing-cycle group (claim "
    "(d)'s groups) has a mean paired complete gain whose 95% t lower bound across seeds is at or above -$2 a person a "
    "year (claim (d) and its margin; the 5 Nov review) against S0 at both ends of the bracket and against M0 at the "
    "face end: the value of completed trade is not assumed, and against DeFi the result is reported as a break-even "
    "value (decided 11 Nov, second round). The "
    "complete gain (decided 11 Nov) is the end-wealth difference plus the difference in purchases received, a "
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
    "verdict. The gains are read in full (decided "
    "5 Nov: M2's indexation is the holder's own yield, not an issuer transfer, and the issuer, a pure custodian, holds "
    "no pool shares and no support fund, so no issuer money exists). A group with a mean in one seed only has no "
    "bound and does not pass. M2's cells at a zero real reserve rate are its declared limit, outside the region. "
    "verdict names the first condition failed, in the order of verdicts, \"a group loses\" reading clause_holds; "
    "verdict_majority reads Persistent on a bare "
    "majority of seeds instead, as the statistics rule reports beside. Each part is stored, with each group's seed "
    "mean beside its bound against each, and the lowest bound with its group and yardstick. Reading the issuer's stay "
    "in every seed and a pool as formed when it forms in any seed are each a reading of the "
    "rule (4 Nov). Owners' return less their alternative stays reported only (decided 11 Nov), and the entry rule's "
    "two readings, quote and realised (Economy.entry_reads), are run as bounds at confirmation. Under the cash-advance "
    "bound (decided 15 Nov 2026), each gain less the cash-advance fees and interest the person saves against the "
    "yardstick, to first order with no feedback: complete_gain_bound holds the same clause on those gains, "
    "verdict_bound and verdict_majority_bound the verdicts with the group test read on it, and in_region_both whether "
    "the cell is stable both as built and under the bound. A seed that stores no bound reads every group as empty "
    "there.")
# Liquidity (5 Nov), what each arm's ``liquidity`` record holds, stored with summary.json.
LIQUIDITY_NOTE = (
    "Liquidity by window (W1, W2), $ a person: precautionary_usd, the total precautionary money, the engine's record "
    "of households' buffers chosen at dealing and the pool's idle cash, each part beside, with idle P (the two-month "
    "lowest P balance) beside them and not in the total, since it sits inside the buffers (the 5 Nov review), the "
    "month's mean; shortfall_covered_usd_a_year, what payers' own money and same-day savings could not pay "
    "and a lender paid, in every arm alike: pool bridges (bills, wages, purchases and card statements), holders' card "
    "bridging of bills and wages (their cash advances since card limits, 14 Nov 2026), card statements left to "
    "revolve on the card, Comet bridging (M0) and earned-wage "
    "advances, each part beside, a year; precautionary_per_dollar_covered, the first over the second; and failed "
    "payments a year, by value (failed_usd_a_year, with declined card-eligible purchases) and in the real failure "
    "line's unpaid shares (failed_shares_a_year). Counting the shortfall the same way in every arm, card statements "
    "included, is a reading of the rule (4 Nov). None for a window the run does not reach.")
# The real part's lines (decided 1 Nov), each arm's saving against S0 read line by line; earned-wage access's
# declared $2 a use from 3 Nov.
REAL_LINES = ("card_credit", "term_credit", "failed_payments", "card_rails", "p_rail", "holding", "earned_wage",
              "total")
# The classes of the no-harm test (decided 4 Nov): card holding x income source, fixed at the population draw and
# the same in every arm, labelled 2 * card holder + business income, in this order.
CLASSES = ("no card and wage income", "no card and business income", "card and wage income",
           "card and business income")
# The region reading's groups by name (5 Nov), in the order the paired differences store them.
GROUP_NAMES = dict(**{"class": CLASSES}, quintile=tuple(f"launch-wealth quintile {k + 1}" for k in range(5)),
                   cycle=("short billing cycle", "long billing cycle"))
# What each arm's paired differences ("against", ``differences``) hold, stored with cells.json (decided 3 and
# 4 Nov), with the class labels.
AGAINST_NOTE = ("Each arm's paired differences in one seed against S0, for U, M1 and M2 against M0 too, and for M1 "
                "against U (what demurrage adds, decided 4 Nov), on the same "
                "random numbers, $ a person a year after launch; a positive saving or gain favours the arm. The gains "
                "are read in full (decided 5 Nov: M2's indexation is the holder's own yield, not an issuer "
                "transfer; under demurrage the pool's share of the reserve return is the contract's, decided "
                "4 Nov), as claim (d) reads them. Groups are launch-wealth "
                "quintile x short (1-15 days) or long (30-60 days) billing cycle, labelled quintile * 2 + long, "
                "poorest first. "
                "Classes are card holding x income source, fixed at the population draw and the same in every arm "
                "(the rule decided 4 Nov), labelled 2 * card holder + business income: " + ", ".join(CLASSES)
                + ". Beside them, reported and not tested, the mean gain by the arm's own role in W2: investor (held "
                "pool shares in a W2 month), borrower (borrowed from the pool in a W2 month), daily user (in P at "
                "least half of W2) and never participant (never in P after launch); the roles arise in the run, "
                "differ by arm and overlap. Beside them too, the mean gain of people not flagged and flagged as payers "
                "in chronic deficit at launch (spending above income received over the burn-in, with a liquid cushion "
                "below one month of their own spending; the same in every arm, decided 3 Nov), in that order: they "
                "stay in the headline and are reported apart. NaN marks an empty group, class, role or flag. "
                "gain_usd_a_year and its breakdowns are the wealth measure, the end-wealth difference. complete_gain "
                "(decided 11 Nov), which claim (d) reads, adds the difference in purchases received (a person's "
                "own service and shock purchases completed as buyer and the price of each durable it bought that "
                "settled), with sellers' extra sales at face value (\"face\") and, less the difference in sales, at "
                "zero (\"zero\"), each with the same breakdowns; complete_gain_parts_usd_a_year holds the mean of each "
                "part (wealth, purchases_completed, durables, sales, with purchases_lost beside), and sales_usd_a_year "
                "and sales_usd_a_year_by_* each group's mean difference in sales (the face value of service and shock "
                "purchases completed to the person as seller, before any merchant fee, plus the price of each durable "
                "it sold), so the gain at a surplus share s is zero + s x sales. Wages are in none of them. "
                "The cash-advance bound (decided 15 Nov 2026): advance_saving_usd_a_year (with _by_quintile and "
                "_by_class) is the mean of what a person saves on the card's cash-advance fees and cash-advance "
                "interest in this arm, the other arm's less this arm's, to first order with no feedback; bound, beside "
                "the wealth gain and inside each end of complete_gain, holds the same breakdowns of the gain less that "
                "saving. Stored only, read by no rule: dispersion (wealth, face, zero), the share of people whose gain "
                "is below -$2 a year and the 5th, 25th, 50th, 75th and 95th percentiles of the gain; and "
                "gain_usd_a_year_at_month, the mean wealth gain at 36 and 48 months after launch and at the end "
                "(\"end\"), each annualised over the months elapsed, a month the run does not reach left out.")
# What each arm row's earned-wage, chronic-deficit and card-bridging reports hold (decided 3 Nov), stored with
# cells.json.
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
                  "card limits (14 Nov 2026) their cash advances, $ a person a year (over everyone) and a holder a "
                  "year; None with no holder. The S0 check reads it against US cash advances, $112 to $118 a consumer "
                  "unit a year (large issuers only). Beside it, a holder a year: the cash-advance and late fees "
                  "charged and the card balances charged off at 180 days past due, $, and the share of holders whose "
                  "line a charge-off closed after launch; holders are the population's card holders, their class.",
    by_class="Credit and purchases by class (decided 11 Nov: business credit is read inside the one population, "
             "with no separate model or run), in every arm, S0 included: the arm's own levels, $ a person a year after "
             "launch, the mean in each class in the order of the classes (card holding x income source), NaN for an "
             "empty class, with class_sizes beside. Credit, by the person named, in the model's money (P in M2 for "
             "the pool's lending): bridge_pool, pool bridging drawn for payments and card statements; bridge_card, "
             "card bridging of payments the holder's money could not pay (its cash advances since card limits, "
             "14 Nov 2026) plus statements left to revolve, not card purchases paid at the statement; advance_card, "
             "the cash advances alone; fees_card, the card's cash-advance and late fees charged; charged_off_card, "
             "the card balance charged off at 180 days past due; bridge_comet, Comet borrowing (M0); "
             "bridge_refused, pool bridging "
             "asked for and not drawn; term_pool and term_outside, instalment principal lent by each lender; "
             "term_cancelled, the price of instalment requests that needed credit and did not qualify; "
             "interest_pool, interest_card and interest_outside, interest accrued on the person's pool loans, card "
             "balances and other outside loans (instalment loans, Comet bridges, overdrafts); wages_late, as payer, "
             "wages not paid on their first due date. Purchases, as in the complete gain: completed and lost as "
             "buyer, durables bought, sales as seller. Failures, as payer (14 Nov 2026: holders can fail since card "
             "limits): failure_fees, the failure fees charged, and failed, new failed payments by value. Classes "
             "are the population's card holding, which a charge-off does not change. Records only: no rule or "
             "verdict reads them.")
# Failure counts (decided 3 Nov), stored for the unit change and the monthly cap: the monthly caps at which each
# arm's spread of fee units is read (2 a month, decided 4 Nov, the starting 3 and 5), and what each stored field holds,
# by the part of an arm's failure counts it sits in (the 3 Nov review): monthly, a person a month in each month after
# launch; a_year, a person a year after launch; with the development seeds, payer_months, the columns of the table of
# every person-month with any count, and S0's buffers.
MONTHLY_CAPS = (2, 3, 5)
FAILURE_LABELS = dict(monthly=dict(
    fees_usd="failure fees charged, $ (at most one fee a payer a day and, under the monthly cap, the Economy's "
             "fees_a_month a payer a month)",
    fail_units="failed bills and wages in fee units: a payer-day's unpaid shares, at most one (the fee's count before "
               "the monthly cap, and the real part's as built)",
    fail_shares="failed bills and wages in unpaid shares, each bill or wage once (a re-queued wage not again; the real "
                "failure line's unit, 3 Nov)",
    fail_items="whole bills and wages a bank paying each payer's day smallest first would return from the money the "
               "day paid: the fewest any order returns",
    fail_days="payer-days with a failed bill or wage",
    declined_shares="declined card-eligible purchases of payers without a card, or past a holder's room on its line "
                    "(14 Nov 2026), in unpaid shares (no fee; the purchase is lost; not a failed bill)",
    declined_items="declined card-eligible purchases in whole purchases, from the same smallest-first pass",
    bridged_shares="bills and wages that the pool's draw paid in place of failing, in shares: for payers without a "
                   "card, and for a holder (14 Nov 2026) the part of its draw that its cash line could not have taken, "
                   "the least of the draw and the shortfall beyond the cash line's room",
    bridged_items="whole bills and wages the pool's draw kept from being returned, read as bridged_shares is",
    bridged_card="card-eligible purchases of payers without a card, or past a holder's room, that the pool's draw "
                 "paid, in shares (new lending, not a replaced failure)",
    bridged_days="payer-days with a pool bridge to a payer without a card (the real part's count as built)",
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
# The uncapped counts are an accounting count with no cap applied (decided 4 Nov).
FAILURE_NOTE = ("Counts only: no rule reads them and nothing here enters a verdict, though the real part's failure "
                "line reads the same fail_shares and bridged_shares series (3 Nov). fail_units is the daily-capped "
                "count before the monthly cap; the fee charged under it is fees_usd. No cap applies in "
                "counting fail_shares, fail_items or the declined and bridged counts, but the path they are counted on "
                "still depends on the caps, through the fee debt ranked ahead of the pool, the pool's "
                "same-day limit and the buffer replays' failure cost; a path free of the caps would need its own run. "
                "Whole items count on the settled path, where every payment of a payer is paid the same share. The "
                "dollar records (failed_usd_a_year, failure_share) keep declined card-eligible purchases with failed "
                "bills and wages; these counts keep them apart. The labels follow each arm's parts: monthly holds "
                "values a person a month in each month after launch, a_year a person a year after launch, and "
                "payer_months one person in one month.")


# The registered claim's statistics (docs/ANALYSIS_PLAN.md), read from the decided cells and their jobs: analysis
# only, no run. The rows are in docs/DECISIONS.md: the claim (3 Nov, clauses (a) to (e)), claim (d) as amended (11 Nov),
# the real cost row (12 Nov, night), the statistics row (3 Nov) and the distress row (3 Nov). Where a row leaves a
# choice open, the reading taken is the one that leans against CPM, and CLAIM_NOTE names each.
CLAIM_ARMS = ("M1", "M2")             # the claim is read for M1 and M2 separately
CLAIM_CONFIDENCE = 0.95               # two-sided 95% t intervals
CLAIM_ALPHA = 1 - CLAIM_CONFIDENCE
CLAIM_MARGIN = REGION_MARGIN          # -$2 a person a year, clauses (b) and (d)
FAIL_USD = 2.0                        # the real failure line's $2 a unit, which a pool rescue is costed at as registered
DIP_MARGIN = 1.0                      # clause (e): the dip's upper bound is at most one failed payment
DIP_MONTHS = (25, 60)                 # the months after launch the dip is summed over, both included
STRESS_LEVELS = DISTRESS[1:]          # clause (e)'s levels, tested in this order at level 0's Bonferroni level
# Clause (e)'s headline level (decided 14 Nov 2026: the harsh stress), read beside the highest level withstood:
# 2 points, 2009's wage loss before unemployment insurance (US wages and salaries fell 4.29% in 2009 against 2008, FRED
# A576RC1A027NBEA, 6,531.9 to 6,251.4 $bn; at 2 points the stored development map has 4.34% more jobs without a wage
# over the stress year than at level 0, so that share of the year's wage bill goes outside). Every level still runs and
# is tested in order.
STRESS_HEADLINE = 0.02
STRESS_HEADLINE_LABEL = "2009's wage loss before unemployment insurance"
SEED_POWER, SEED_CAP = 0.8, 100       # the seed count: 80% power at a true difference of zero, at most 100 seeds
# The seed count's allowance for the spread being an estimate (decided 17 Nov 2026): each reading's pooled spread is
# taken at the upper end of its one-sided interval at this assurance, the same level as the power.
SEED_ASSURANCE = 0.8
BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 10000, 20261112   # the bootstrap check: resampled seeds, a fixed stream
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
    "bound at or above zero) are stored beside and required only in holds_as_first_registered: since 5 Nov the pool "
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
    "(decided 14 Nov 2026) the extra layoffs' wages leave the household economy, with no unemployment insurance, "
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
    "Three-way readings (the 13 Nov review): each clause and the cell store reading, supported, inconclusive (an "
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
    "The cash-advance bound (decided 15 Nov 2026): d_bound is clause (d) read a second time, with the same groups, "
    "yardsticks, ends, intervals and margin, on each gain less the cash-advance fees and interest the person saves "
    "against the yardstick, to first order with no feedback; d keeps the clause as built. all and all_bonferroni ask "
    "(d) both as built and under the bound, so in_region, the region and holds somewhere do too, and a stress slice's "
    "cell needs its level-0 cell to pass all; all_as_built and all_bonferroni_as_built keep (a), (b) and (d) as built. "
    "The cell's reading and decided_by (at 95% and Bonferroni) take the worse of the two (d) readings, with the "
    "readings as built beside (reading_as_built and so on). (e), near_the_line and the stress legs read (d) as built.")

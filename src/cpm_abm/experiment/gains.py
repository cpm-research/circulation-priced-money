"""Paired differences between arms: one arm's row against S0 and M0.

The harm groups, the complete gain (the money saving with completed purchases at their value), the differences
between two arms of the same seed with the cash-advance bound and the dispersion of the gain, each group's own failed
payments in a run that conserves money, and ``arm_row``, which
gathers an arm's own accounts and its differences into the row a job stores.
"""
import numpy as np

from cpm_abm.economy_abm import EPS
from run_economy_figures import (DOLLARS, classes, persistence, settled, steady_names, steady_windows,
                                 window_names, windows, years_of_life)
from cpm_abm.experiment.notes import (CLASSES, GAIN_MONTHS, PERCENTILES, REAL_LINES, REGION_GROUPS, REGION_MARGIN,
                                      SHORT, conserves_money, second_run)
from cpm_abm.experiment.accounts import (by_chronic, by_class, by_quintile, card_bridging, cash_check, crossings,
                                         demurrage, ewa_report, households_pool, liquidity, owners_excess,
                                         owners_return, pool_payable, pool_report, real_part, real_part_over,
                                         split, transfers)

def groups(population, launch_wealth):
    """Harm groups: launch-wealth quintile x short or long billing cycle (10 groups), as integer labels."""
    quintile = np.minimum((np.argsort(np.argsort(launch_wealth)) * 5) // launch_wealth.size, 4)
    return quintile * 2 + (population["cycles"] > SHORT)


def v3_harmed(arm, m0, w):
    """Harm test, one seed: groups whose median real-wealth change against M0 is below -2% of their starting wealth."""
    end, launch = w.burn_in + w.months, w.burn_in
    start = m0["wealth"][launch]
    label = groups(m0["population"], start)
    change = arm["wealth"][end] - m0["wealth"][end]
    median = lambda values: np.array(list(map(lambda g: np.median(values[label == g]), range(10))))
    base = median(start)
    line = np.where(base > 0, -0.02 * base, 0.0)
    return median(change) < line


def complete_gain(wealth, completed, durables, sales):
    """The complete gain of an arm against another, person by person, from the paired differences of end wealth, of
    service and shock purchases completed as buyer, of durables bought and of sales as seller, all in one unit. Returns
    the two ends of the bracket: at face, the wealth gain plus purchases received (sellers' extra sales counted at face
    value, already in their wealth), and at zero, that less the difference in sales (sellers' extra sales counted at
    zero). The gain at surplus share s is zero + s x sales."""
    face = wealth + completed + durables
    return face, face - sales


def differences(arm, other, w):
    """One seed's paired differences of an arm against another on the same random numbers, $ a person a year after
    launch. The claim is read paired within seed over all seeds, so each job keeps these and the intervals across
    seeds need no rerun.

    real_saving_usd_a_year: the real part line by line, the other arm's less this arm's, so a saving is positive.
    gain_usd_a_year: this arm's end wealth less the other's, the mean over people; by harm group (launch-wealth
    quintile x short or long billing cycle, in the harm test's order), by quintile, by short or long cycle and by
    class (``CLASSES``); and worse_off, the share of people whose gain is below zero. gain_usd_a_year_by_role,
    reported beside and not tested: the mean gain by the arm's own role in W2 (``classes``: investor, borrower, daily
    user, never participant), groups that overlap. gain_usd_a_year_by_chronic: the mean gain of people not
    flagged and flagged as payers in chronic deficit at launch, in that order. NaN marks an empty group, class, role
    or flag.

    The gains are read in full: M2's indexation is the holder's own yield, paid out of the reserve return on its own
    P while the issuer keeps only c_I, so no gain is netted of issuer transfers.

    The complete gain (claim (d) reads the wealth change plus purchases received, at both ends of a bracket) comes
    from the engine's purchase records over the months after launch: received is a person's own service
    and shock purchases completed as buyer plus the price of each durable it bought that settled; sales are the face
    value of service and shock purchases completed to it as seller, before any merchant fee, plus the price of each
    durable it sold; wages are in neither. complete_gain["face"] is the wealth gain plus the difference in received
    (sellers' extra sales counted at face value); complete_gain["zero"] is that less the difference in sales (counted
    at zero). Each holds the same reading as the wealth gain (``gains``: mean, share worse off, by group, quintile,
    cycle, class and chronic flag). complete_gain_parts_usd_a_year holds the mean of each part: wealth, purchases
    completed, durables and sales, with purchases lost beside. sales_usd_a_year and sales_usd_a_year_by_* hold the
    mean difference in sales overall and by each group, so the gain at any surplus share s, zero + s x sales, can be
    read later from stored numbers. The wealth gain keys above are unchanged: they are the wealth measure.

    The cash-advance bound, to first order with no feedback on behaviour: each person's
    saving on the card's cash-advance fees and cash-advance interest, the other arm's less this arm's over the months
    after launch (the engine's ``fees_advance`` and ``interest_advance`` records), $ a year; the gain under the bound is
    the gain less that saving, as if both arms charged the person the same for cash advances. ``bound`` beside the
    wealth gain, and inside complete_gain["face"] and complete_gain["zero"], holds the same reading (``gains``) of the
    gain under the bound; advance_saving_usd_a_year and its _by_quintile and _by_class hold the saving's means.

    Stored only, read by no rule: dispersion, for the wealth gain and each end of the complete gain, the
    share of people whose gain is below the claim's margin of -$2 a year and the 5th, 25th, 50th, 75th and 95th
    percentiles of the gain; and gain_usd_a_year_at_month, the mean wealth gain at 36 and 48 months after launch and at
    the end, each annualised over the months elapsed, a month the run does not reach left out.
    """
    end, year = w.burn_in + w.months, 12 / w.months
    gain = (arm["wealth"][end] - other["wealth"][end]) * DOLLARS * year
    # The two arms share the burn-in, so launch wealth and the harm groups are the same in both.
    label = groups(other["population"], other["wealth"][w.burn_in])
    # The class of the no-harm test is card holding x income source, fixed at the population draw and the same in
    # every arm, labelled 2 * card holder + business income (``CLASSES``).
    people = other["population"]
    if not all(np.array_equal(arm["population"][key], people[key]) for key in ("holder", "business")):
        raise ValueError("Both arms must hold the same population: card holding and income source fix the class")
    kind = 2 * people["holder"].astype(int) + people["business"].astype(int)
    # The arm's own W2 roles are reported beside the class, not tested: they arise in the run, differ by arm and
    # overlap, so each role's mean is read over its own members.
    roles = classes(arm)
    members = np.array(list(roles.values()), float)
    count = members.sum(axis=1)
    by_role = np.round(np.divide(members @ gain, count, out=np.full(count.size, np.nan), where=count > 0), 2)

    def mean_by(key, size, values=gain):
        """The mean of ``values`` (the gain) in each of `size` groups (NaN for an empty one)."""
        count, total = np.bincount(key, minlength=size), np.bincount(key, weights=values, minlength=size)
        return np.round(np.divide(total, count, out=np.full(size, np.nan), where=count > 0), 2).tolist()

    def gains(values):
        """The gain read for the claim: its mean, the share worse off, and its mean by group, quintile, short or long
        cycle, class and chronic flag."""
        return dict(gain_usd_a_year=round(float(values.mean()), 2), worse_off=round(float((values < 0).mean()), 3),
                    gain_usd_a_year_by_group=mean_by(label, 10, values),
                    gain_usd_a_year_by_quintile=mean_by(label // 2, 5, values),
                    gain_usd_a_year_by_cycle=mean_by(label % 2, 2, values),
                    gain_usd_a_year_by_class=mean_by(kind, len(CLASSES), values),
                    # The chronic-deficit flag is set from the shared burn-in, so both arms hold the same.
                    gain_usd_a_year_by_chronic=mean_by(other["chronic"].astype(int), 2, values))

    mine, theirs = real_part(arm, w), real_part(other, w)
    gross = gains(gain)
    # The complete gain: each part's difference by person over the months after launch, $ a year.
    after = slice(w.burn_in, end)
    part = lambda key: (arm["purchases"][key][after].sum(axis=0) - other["purchases"][key][after].sum(axis=0)) \
        * DOLLARS * year
    completed, durables, lost, sales = map(part, ("completed", "durables", "lost", "sales"))
    face, zero = complete_gain(gain, completed, durables, sales)
    sold = {key.replace("gain_", "sales_"): value for key, value in gains(sales).items() if key != "worse_off"}
    # The cash-advance bound: each person's saving on cash-advance fees and interest, $ a year.
    advances = lambda run: (run["credit"]["fees_advance"][after].sum(axis=0)
                            + run["credit"]["interest_advance"][after].sum(axis=0)) * DOLLARS * year
    saved = advances(other) - advances(arm)
    # Dispersion and the gain by month, stored only.
    spread = lambda values: dict(below_margin_share=round(float((values < REGION_MARGIN).mean()), 4),
                                 percentiles_usd_a_year=dict(zip(map(str, PERCENTILES), np.round(
                                     np.percentile(values, PERCENTILES), 2).tolist())))
    by_month = lambda m: round(float((arm["wealth"][w.burn_in + m] - other["wealth"][w.burn_in + m]).mean())
                               * DOLLARS * 12 / m, 2)
    at_month = dict({str(m): by_month(m) for m in GAIN_MONTHS if m <= w.months}, end=by_month(w.months))
    out = dict(real_saving_usd_a_year={key: round((theirs[key] - mine[key]) * year, 2) for key in REAL_LINES},
                **{key: gross[key] for key in ("gain_usd_a_year", "worse_off", "gain_usd_a_year_by_group",
                                               "gain_usd_a_year_by_quintile", "gain_usd_a_year_by_cycle",
                                               "gain_usd_a_year_by_class")},
                gain_usd_a_year_by_role=dict(zip(roles, by_role.tolist())),
                gain_usd_a_year_by_chronic=gross["gain_usd_a_year_by_chronic"],
                complete_gain=dict(face=dict(gains(face), bound=gains(face - saved)),
                                   zero=dict(gains(zero), bound=gains(zero - saved))),
                complete_gain_parts_usd_a_year={key: round(float(values.mean()), 2) for key, values in (
                    ("wealth", gain), ("purchases_completed", completed), ("durables", durables), ("sales", sales),
                    ("purchases_lost", lost))},
                **sold, bound=gains(gain - saved), advance_saving_usd_a_year=round(float(saved.mean()), 2),
                advance_saving_usd_a_year_by_quintile=mean_by(label // 2, 5, saved),
                advance_saving_usd_a_year_by_class=mean_by(kind, len(CLASSES), saved),
                dispersion=dict(wealth=spread(gain), face=spread(face), zero=spread(zero)),
                gain_usd_a_year_at_month=at_month)
    if second_run(w):
        out.update(real_saving_by_window(arm, other, w, out["real_saving_usd_a_year"]))
    return out


# The real cost's payment-rail lines: card payments' processing, fraud and network costs and the gas of P and USDC
# payments, read apart from every other line in a run of the second run.
RAIL_LINES = ("card_rails", "p_rail")


def rail_apart(saving):
    """A real saving's lines (``REAL_LINES``, $ a person a year) as the payment-rail lines (``RAIL_LINES``) and all
    the others, with the total beside.

    Example: a total of 5.00 with card rails 4.00 and the P rail -0.50 is a rail
    saving of 3.50 and 1.50 on everything else."""
    rail = sum(saving[key] for key in RAIL_LINES)
    return dict(rail=round(rail, 2), other=round(saving["total"] - rail, 2), total=saving["total"])


def real_saving_by_window(arm, other, w, whole):
    """The real saving of ``arm`` against ``other`` read in each of the run's steady windows as well as over the whole
    run, in a run of the second run: real_saving_by_window_usd_a_year, each window's lines, the
    other arm's real cost less this arm's over the window's months put a year (``real_part_over``); and
    real_saving_rail_apart_usd_a_year, for the whole run (``whole``, the saving clause (b) reads) and each window, the
    payment-rail lines apart from all the others (``rail_apart``).

    Example: $60 of real cost saved over the 60
    months of years 6 to 10 is $12 a year there."""
    def saving(span):
        """The lines saved over one window, $ a person a year."""
        mine, theirs = real_part_over(arm, w, span), real_part_over(other, w, span)
        return {key: round((theirs[key] - mine[key]) * 12 / (span.stop - span.start), 2) for key in REAL_LINES}

    by_window = {name: saving(span) for name, span in steady_windows(arm)}
    apart = {name: rail_apart(lines) for name, lines in by_window.items()}
    return dict(real_saving_by_window_usd_a_year=by_window,
                real_saving_rail_apart_usd_a_year=dict(whole_run=rail_apart(whole), **apart))


def failed_by_group(arm, s0, m0, w):
    """Each group's own payments that did not complete, as payer, in one seed (the claim's clause (d) in a run that
    conserves money): for each of the run's steady windows (``steady_windows``: W2 of the first run; years 6 to 10 and
    years 21 to 25 in the second run), each person's failed bills and wages in unpaid shares (the engine's per-person
    ``fail_shares``, the real failure line's unit that clause (c) and the stress dip read) plus its declined
    card-eligible purchases in unpaid shares (``declined_shares``: a purchase of a payer without a card, or past a
    holder's room, that its money could not pay and that is lost, with no fee), each summed over the window's months and
    put a year, then the mean over each group's people. A payment of the group's own that did not complete counts
    whichever record holds it, so a buyer without a card whose purchase is declined is not read as unharmed.

    The groups are the complete gain's (``differences``): the four classes, card holding by income source; the
    launch-wealth quintiles and the short and long billing cycle, from S0's launch wealth, which every arm shares.
    Each window holds the sum of the two parts as the arm's own level, S0's, and the arm's less S0's (against_S0) and,
    but for M0 itself, less M0's (against_M0), each by class, quintile and cycle, NaN for an empty group; and the same
    for each part alone under ``failed`` and ``declined``. The difference of two group means is the group's mean of
    each person's difference, since the groups are the same people in every arm.

    Example: a person with 0.1 unpaid
    shares of bills and wages and 0.05 declined shares in each of the 60 months of years 6 to 10 fails 0.1 x 60 / 5 =
    1.2 payments a year there and has 0.6 declined, 1.8 in all; with 0.05 and 0.05 a month under S0 (0.6 and 0.6) the
    difference is 0.6 failed, 0 declined and 0.6 in all."""
    people = s0["population"]
    label = groups(people, s0["wealth"][w.burn_in])
    kind = 2 * people["holder"].astype(int) + people["business"].astype(int)
    keys = dict(zip(REGION_GROUPS, (kind, label // 2, label % 2)))
    sizes = dict(zip(REGION_GROUPS, (len(CLASSES), 5, 2)))
    # A run's failed or declined shares a month by person: its own failure counts, or for S0's and M0's runs as a job
    # keeps them for the later arms (``jobs._kept``) the same arrays under their names.
    shares = lambda run, key: run[key] if key in run else run["failure_counts"][key]

    def by_group(values):
        """The mean of ``values`` (one a person) in each group of each kind, NaN for an empty group."""
        mean = lambda key, size: np.divide(np.bincount(key, weights=values, minlength=size),
                                           np.bincount(key, minlength=size), out=np.full(size, np.nan),
                                           where=np.bincount(key, minlength=size) > 0)
        return {name: np.round(mean(keys[name], sizes[name]), 6).tolist() for name in REGION_GROUPS}

    def read(own, banks, defi):
        """The levels and differences by group from each person's yearly count in the arm, S0 and M0 (None for M0
        itself)."""
        out = dict(level=by_group(own), S0=by_group(banks), against_S0=by_group(own - banks))
        if defi is not None:
            out["against_M0"] = by_group(own - defi)
        return out

    def window(span):
        """One steady window's levels and differences: each person's failed and declined shares a year over ``span``,
        their sum and each part."""
        yearly = lambda run, key: shares(run, key)[span].sum(axis=0) * 12 / (span.stop - span.start)
        runs = (arm, s0, None if arm["arm"] == "M0" else m0)
        of = lambda key: [None if run is None else yearly(run, key) for run in runs]
        failed, declined = of("fail_shares"), of("declined_shares")
        both = [None if one is None else one + two for one, two in zip(failed, declined)]
        return dict(read(*both), failed=read(*failed), declined=read(*declined))

    steady = steady_windows(arm)
    return dict(windows=[name for name, _ in steady], by_window={name: window(span) for name, span in steady})


def defi_credit(run, w):
    """What DeFi (M0) lends in one seed of a run of the second run: the people able to borrow,
    those holding the crypto collateral its lending needs (none at the runner's collateral share of 0), and the
    borrowing drawn after launch, Comet's bridging, $ a person a year; both zero in the second run, where M0 is
    stablecoin payments with no yield and no credit."""
    after, year = slice(w.burn_in, w.burn_in + w.months), 12 / w.months
    drawn = float(np.nansum(run["series"]["comet_bridging"][after])) * DOLLARS * year
    return dict(people_able_to_borrow=int(np.sum(run["population"]["crypto"])),
                borrowing_drawn_usd_a_year=round(drawn, 4))


def payout_by_group(arm, s0, w):
    """Who pays and who receives in one seed of a run that conserves money, from the monthly payout itself: received,
    each person's payout over the months after launch (the engine's ``payout``, months by people, in months of mean
    spending a person, whose mean over people each month is the stored total ``returned``); and paid_across_edge, its
    own payments to intermediaries outside the economy as booked (``transfers``: outside interest, failure fees, card
    fees less rewards, conversion fees, gas, the spreads kept on its money and savings, earned-wage and the card's
    cash-advance and late fees), each $ a year, as everyone's mean and by class, launch-wealth quintile and billing
    cycle (the complete gain's groups, from S0's launch wealth).

    The two do not close by group: the payout returns the month's whole net flow across the edge, net of what
    households receive from outside, with the inflation part and on a cash basis, and the engine records those terms
    for the economy only, not by person. So no difference by group is stored, and the closure is stored for everyone
    (closure_everyone, $ a person a year): received = paid_across_edge + other_across_edge + inflation + stock_change
    - kept, where other_across_edge is the rest of the net flow across the edge as booked (what households pay
    outside beyond the transfers, the wages owed outside among it, less what they receive from outside, savings
    income and yields), inflation the part of the payout that makes good money's loss of value, stock_change minus
    the change in the stock booked across the edge and not yet paid in cash (under ``payout`` "paid"; zero as
    accrued), and kept the part of the flow not returned (``edge_kept``, zero in the base, where the engine has it).
    gap is received less the right-hand side, zero to rounding when the records agree, and returned_usd_a_year the
    stored total. "not stored" in a run whose engine keeps no payout.

    Example: a person paid $10 a month and paying
    $4 a month across the edge receives $120 and pays $48 a year."""
    if "payout" not in arm:
        return "not stored"
    after, year = slice(w.burn_in, w.burn_in + w.months), 12 / w.months
    people = s0["population"]
    label = groups(people, s0["wealth"][w.burn_in])
    kind = 2 * people["holder"].astype(int) + people["business"].astype(int)
    keys = dict(zip(REGION_GROUPS, (kind, label // 2, label % 2)))
    sizes = dict(zip(REGION_GROUPS, (len(CLASSES), 5, 2)))
    received = np.asarray(arm["payout"], float)[after].sum(axis=0) * DOLLARS * year
    paid = arm["transfers"][after].sum(axis=0) * DOLLARS * year

    def table(values):
        """Everyone's mean of ``values`` (one a person) and its mean in each group of each kind, NaN when empty."""
        mean = lambda key, size: np.divide(np.bincount(key, weights=values, minlength=size),
                                           np.bincount(key, minlength=size), out=np.full(size, np.nan),
                                           where=np.bincount(key, minlength=size) > 0)
        return dict(everyone=round(float(values.mean()), 4),
                    **{name: np.round(mean(keys[name], sizes[name]), 4).tolist() for name in REGION_GROUPS})

    a = arm["series"]
    total = lambda key: float(np.nansum(a[key][after])) * DOLLARS * year if key in a else 0.0
    returned = total("returned")
    # The stock booked across the edge and not yet paid, a person at each close: its change over the months after
    # launch, from the last close before launch, enters the payout under "paid" only.
    paid_basis = "edge_owed" in a and getattr(w, "payout", "accrued") == "paid"
    stock = ((a["edge_owed"][w.burn_in + w.months - 1] - a["edge_owed"][w.burn_in - 1]) * DOLLARS * year
             if paid_basis else 0.0)
    closure = dict(received=round(float(received.mean()), 4), paid_across_edge=round(float(paid.mean()), 4),
                   other_across_edge=round(-total("external") - float(paid.mean()), 4),
                   inflation=round(-total("inflation"), 4), stock_change=round(-float(stock), 4),
                   kept=round(total("edge_kept"), 4))
    closure["gap"] = round(closure["received"] - (closure["paid_across_edge"] + closure["other_across_edge"]
                                                  + closure["inflation"] + closure["stock_change"]
                                                  - closure["kept"]), 4)
    return dict(received=table(received), paid_across_edge=table(paid), closure_everyone=closure,
                returned_usd_a_year=round(returned, 4),
                reconciled_gap_usd_a_year=round(float(received.mean()) - returned, 6))


# The means of one window an arm's row reports under names without a window, each as ``arm_row`` reads it in W2: the
# reader of each from a run's series and a window. A long run stores them for each of its windows (``by_window``).
WINDOW_MEANS = dict(
    p_yield_pct=lambda a, span: float(np.nanmean(a["p_yield"][span]) * 1200),
    failures_pct=lambda a, span: float(a["failure_share"][span].mean() * 100),
    merchant_fees_pct=lambda a, span: float(a["merchant_fees"][span].mean() * 100),
    c_pct=lambda a, span: float(np.nanmean(a["c"][span]) * 1200),
    r_g_pct=lambda a, span: float(np.nanmean(a["r_g"][span]) * 1200),
    r_term_pct=lambda a, span: float(np.nanmean(a["r_term"][span]) * 1200),
    theta=lambda a, span: float(np.nanmean(a["theta"][span])), N=lambda a, span: float(np.nanmean(a["N"][span])),
    N_star=lambda a, span: float(np.nanmean(a["Q"][span])),
    coverage=lambda a, span: float(np.nanmean(a["coverage"][span])),
    r_b_pct=lambda a, span: float(np.nanmean(a["r_b"][span]) * 1200),
    quote_pct=lambda a, span: float(np.nanmean(a["quote"][span]) * 1200),
    bridges_drawn_over_wanted=lambda a, span: float(np.nanmean(a["bridges_drawn_over_wanted"][span])))
ROW_MEANS = ("p_yield_pct", "failures_pct", "merchant_fees_pct")      # every arm's
POOL_MEANS = tuple(key for key in WINDOW_MEANS if key not in ROW_MEANS)   # the pool arms' beside them


def arm_row(arm, s0, m0, a0, w, u=None):
    """One arm in one seed: gains against S0, participation, the gain split, liquidity, and (pool arms) the contract,
    demurrage and the tests. u is the seed's U run, which M1 is also read against (what demurrage adds)."""
    end = w.burn_in + w.months
    gain = (arm["wealth"][end] - s0["wealth"][end]) * DOLLARS
    w1, w2 = windows(arm)
    names, long_run = window_names(arm["economy"]), settled(arm["economy"])
    a = arm["series"]
    after = slice(w.burn_in, w.burn_in + w.months)
    issuer = float(np.nansum(a["issuer"][after]) * DOLLARS)
    row = dict(mean_gain_usd=float(gain.mean()), median_gain_usd=float(np.median(gain)), issuer_usd=issuer,
               p_yield_pct=float(np.nanmean(a["p_yield"][w2]) * 1200),
               better_off=float((gain >= 0).mean()), A_launch=float(a["A"][w.burn_in]),
               # Participation in years 2 and 3 (W1) and in years 4 and 5 (W2) after launch, and in a long run in each
               # of its two windows, named by their years.
               **{f"A_{name}": float(a["A"][span].mean()) for name, span in zip(names, (w1, w2))},
               failures_pct=float(a["failure_share"][w2].mean() * 100),
               merchant_fees_pct=float(a["merchant_fees"][w2].mean() * 100), split=split(arm, s0, w),
               real_part=real_part(arm, w), transfers=transfers(arm, w), cash=cash_check(arm, w),
               # This seed's paired differences against S0, for the pool arms against M0, and for M1 against U, what
               # demurrage adds.
               against=dict(map(lambda other: (other["arm"], differences(arm, other, w)),
                                (s0,) if arm["arm"] == "M0" else (s0, m0, u) if arm["arm"] == "M1" and u
                                else (s0, m0))),
               # Precautionary money, the shortfall a lender paid and failed payments, by window.
               liquidity=liquidity(arm, w),
               # Crossings between E and P, reported only.
               crossings=crossings(arm, w),
               # Earned-wage access, payers in chronic deficit and holders' card bridging, reported only
               # (``REPORT_NOTES``).
               earned_wage=ewa_report(arm, w), chronic=by_chronic(arm, w), card_bridging=card_bridging(arm, w),
               # Credit and purchases by class, reported only.
               by_class=by_class(arm, w),
               **by_quintile(arm, w))
    if conserves_money(w):
        # In a run that conserves money each group's own payments that did not complete by window, which clause (d)
        # reads, and who pays and who receives from the payout itself; a first-run row has none.
        row["failed_by_group"] = failed_by_group(arm, s0, m0, w)
        row["payout_by_group"] = payout_by_group(arm, s0, w)
    # In a long run the window means the row reports under names without a window (``WINDOW_MEANS``), which read the
    # second window, are stored for each window under its name as well.
    window_means = lambda keys: {name: {key: WINDOW_MEANS[key](a, span) for key in keys}
                                 for name, span in zip(names, (w1, w2))}
    if arm["arm"] == "M0":
        if second_run(w):
            row["defi_credit"] = defi_credit(arm, w)   # DeFi's credit beside its results
        return dict(row, windows=list(names), by_window=window_means(ROW_MEANS)) if long_run else row
    verdict = persistence(arm, a0)
    detail = verdict["detail"]
    listed = lambda pair: None if pair is None else list(pair)
    # Trade worse than M0 (V1): failed payments in W2 above M0's; in a long run above M0's in either window, so the
    # arm is not worse only where it is not worse in both.
    worse_in = {name: bool(a["failure_share"][span].mean() > m0["series"]["failure_share"][span].mean())
                for name, span in steady_windows(arm)}
    v1_worse = any(worse_in.values())
    # The use and collapse tests as first registered (P1 against the launch share with no tolerance, X1 on
    # second-window participation below the launch share), stored beside the current ones; no verdict reads them.
    # A long run's own readings, stored only in a long run, so a first-run row is unchanged: the
    # names of its windows, in the order of every reading by window, and each window's tests, V1 and means.
    long = {} if not long_run else dict(
        windows=list(names), by_window={name: dict(P=reading["P"], X=reading["X"], verdict=reading["verdict"],
                                                   V1_worse=worse_in[name], **window_means(ROW_MEANS + POOL_MEANS)[name])
                                        for name, reading in detail["by_window"].items()})
    return dict(row, **long, P=verdict["P"], X=verdict["X"], registered_tests=dict(detail["registered_tests"]),
                verdict=verdict["verdict"], V1_worse=v1_worse,
                V3_harmed=v3_harmed(arm, m0, w).tolist(), c_pct=float(np.nanmean(a["c"][w2]) * 1200),
                r_g_pct=float(np.nanmean(a["r_g"][w2]) * 1200), r_term_pct=float(np.nanmean(a["r_term"][w2]) * 1200),
                theta=float(np.nanmean(a["theta"][w2])), N=float(np.nanmean(a["N"][w2])),
                # The contract's other W2 means: the capital limit N*, demurrage's coverage of the bridging
                # capital cost, the rate a bridge is sealed at and the published quote, % a year (P terms in M2).
                N_star=float(np.nanmean(a["Q"][w2])), coverage=float(np.nanmean(a["coverage"][w2])),
                r_b_pct=float(np.nanmean(a["r_b"][w2]) * 1200), quote_pct=float(np.nanmean(a["quote"][w2]) * 1200),
                # Whether households held pool capital in any month after launch, and demurrage by window.
                pool_formed=bool(np.nanmax(a["owners_capital"][after], initial=0.0) > EPS),
                demurrage=demurrage(arm, w),
                bridges_drawn_over_wanted=float(np.nanmean(a["bridges_drawn_over_wanted"][w2])),
                term_loss_by_year_of_life=years_of_life(arm),
                issuer_would_leave_from_month=detail["issuer_would_leave_from_month"],
                # The issuer's room: since its wallet carries its own costs, the figures' most expense is its headroom
                # beyond them, beside those costs and the most cost it could bear in all, each $ a person a year and as
                # a share of P (None where the run stores no expenses line).
                issuer_headroom_usd_a_year=detail["issuer_most_expense_usd_a_year"],
                issuer_headroom_share_of_P=detail["issuer_most_expense_share_of_P"],
                issuer_costs_usd_a_year=detail["issuer_costs_usd_a_year"],
                issuer_costs_share_of_P=detail["issuer_costs_share_of_P"],
                issuer_most_cost_usd_a_year=detail["issuer_most_cost_usd_a_year"],
                issuer_most_cost_share_of_P=detail["issuer_most_cost_share_of_P"],
                issuer_limit=detail["issuer_zero_real_rate_limit"],
                backing_lowest=detail["backing_lowest"], backing_topup_usd=detail["backing_topup_usd"],
                # In a run of the second run, what the pool owed its operating provider by window, which clause (a)
                # reads.
                **({"pool_payable": pool_payable(arm)} if second_run(w) else {}),
                # Households' realised return as owners, reported only.
                owners=owners_return(arm, w),
                # Their net return less their alternative by window, reported only.
                owners_excess=owners_excess(arm, w),
                # The yardsticks, by window, $ a person a year, for claim (a) across seeds: the pool's own margin
                # (persistence test 4) and the joint issuer-and-pool test (None under the first run's coverage test),
                # whether the issuer never records "would leave", and the 90% reading and P routing
                # (``households_pool``).
                own_margin_usd_a_year=listed(detail.get("own_margin_usd_a_year")),
                # The household-held months each window's margin averages over, beside it.
                own_margin_held_months=listed(detail.get("own_margin_held_months")),
                joint_usd_a_year=listed(detail.get("joint_usd_a_year")),
                # The pool pays its own way (P4) in W2, and in a long run in each window by its years.
                **{f"pays_its_way_{name}": (verdict["P"]["P4"] if not long_run else
                                            detail["by_window"][name]["P"]["P4"])
                   if "own_margin_usd_a_year" in detail else None for name in steady_names(arm["economy"])},
                issuer_never_leaves=None if verdict["X"]["X6"] is None else not verdict["X"]["X6"],
                households=households_pool(arm, w),
                **pool_report(arm, w))

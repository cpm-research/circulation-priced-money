"""Paired differences between arms: one arm's row against S0 and M0.

The harm groups, the complete gain (the money saving with completed purchases at their value), the differences
between two arms of the same seed with the cash-advance bound and the dispersion of the gain, and ``arm_row``, which
gathers an arm's own accounts and its differences into the row a job stores.
"""
import numpy as np

from cpm_abm.economy_abm import EPS
from run_economy_figures import DOLLARS, classes, persistence, windows, years_of_life
from cpm_abm.experiment.notes import CLASSES, GAIN_MONTHS, PERCENTILES, REAL_LINES, REGION_MARGIN, SHORT
from cpm_abm.experiment.accounts import (by_chronic, by_class, by_quintile, card_bridging, cash_check, crossings,
                                         demurrage, ewa_report, households_pool, liquidity, owners_excess,
                                         owners_return, pool_report, real_part, split, transfers)

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
    """The complete gain of an arm against another (decided 11 Nov), person by person, from the paired differences
    of end wealth, of service and shock purchases completed as buyer, of durables bought and of sales as seller, all in
    one unit. Returns the two ends of the bracket: at face, the wealth gain plus purchases received (sellers' extra
    sales counted at face value, already in their wealth), and at zero, that less the difference in sales (sellers'
    extra sales counted at zero). The gain at surplus share s is zero + s x sales."""
    face = wealth + completed + durables
    return face, face - sales


def differences(arm, other, w):
    """One seed's paired differences of an arm against another on the same random numbers, $ a person a year after
    launch (decided 3 Nov: the claim is read paired within seed over all seeds, so each job keeps these and the
    intervals across seeds need no rerun).

    real_saving_usd_a_year: the real part line by line, the other arm's less this arm's, so a saving is positive.
    gain_usd_a_year: this arm's end wealth less the other's, the mean over people; by harm group (launch-wealth
    quintile x short or long billing cycle, in the harm test's order), by quintile, by short or long cycle and by
    class (``CLASSES``); and worse_off, the share of people whose gain is below zero. gain_usd_a_year_by_role,
    reported beside and not tested: the mean gain by the arm's own role in W2 (``classes``: investor, borrower, daily
    user, never participant), groups that overlap. gain_usd_a_year_by_chronic (3 Nov): the mean gain of people not
    flagged and flagged as payers in chronic deficit at launch, in that order. NaN marks an empty group, class, role
    or flag.

    The gains are read in full (decided 5 Nov: M2's indexation is the holder's own yield, paid out of the reserve
    return on its own P while the issuer keeps only c_I, so no gain is netted of issuer transfers).

    The complete gain (decided 11 Nov: claim (d) reads the wealth change plus purchases received, at both ends of
    a bracket), from the engine's purchase records over the months after launch: received is a person's own service
    and shock purchases completed as buyer plus the price of each durable it bought that settled; sales are the face
    value of service and shock purchases completed to it as seller, before any merchant fee, plus the price of each
    durable it sold; wages are in neither. complete_gain["face"] is the wealth gain plus the difference in received
    (sellers' extra sales counted at face value); complete_gain["zero"] is that less the difference in sales (counted
    at zero). Each holds the same reading as the wealth gain (``gains``: mean, share worse off, by group, quintile,
    cycle, class and chronic flag). complete_gain_parts_usd_a_year holds the mean of each part: wealth, purchases
    completed, durables and sales, with purchases lost beside. sales_usd_a_year and sales_usd_a_year_by_* hold the
    mean difference in sales overall and by each group, so the gain at any surplus share s, zero + s x sales, can be
    read later from stored numbers. The wealth gain keys above are unchanged: they are the wealth measure.

    The cash-advance bound (decided 15 Nov 2026), to first order with no feedback on behaviour: each person's
    saving on the card's cash-advance fees and cash-advance interest, the other arm's less this arm's over the months
    after launch (the engine's ``fees_advance`` and ``interest_advance`` records), $ a year; the gain under the bound is
    the gain less that saving, as if both arms charged the person the same for cash advances. ``bound`` beside the
    wealth gain, and inside complete_gain["face"] and complete_gain["zero"], holds the same reading (``gains``) of the
    gain under the bound; advance_saving_usd_a_year and its _by_quintile and _by_class hold the saving's means.

    Stored only, read by no rule (15 Nov 2026): dispersion, for the wealth gain and each end of the complete gain, the
    share of people whose gain is below the claim's margin of -$2 a year and the 5th, 25th, 50th, 75th and 95th
    percentiles of the gain; and gain_usd_a_year_at_month, the mean wealth gain at 36 and 48 months after launch and at
    the end, each annualised over the months elapsed, a month the run does not reach left out.
    """
    end, year = w.burn_in + w.months, 12 / w.months
    gain = (arm["wealth"][end] - other["wealth"][end]) * DOLLARS * year
    # The two arms share the burn-in, so launch wealth and the harm groups are the same in both.
    label = groups(other["population"], other["wealth"][w.burn_in])
    # The class of the no-harm test is the rule decided 4 Nov: card holding x income source, fixed at the
    # population draw and the same in every arm, labelled 2 * card holder + business income (``CLASSES``).
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
                    # The chronic-deficit flag is set from the shared burn-in, so both arms hold the same (3 Nov).
                    gain_usd_a_year_by_chronic=mean_by(other["chronic"].astype(int), 2, values))

    mine, theirs = real_part(arm, w), real_part(other, w)
    gross = gains(gain)
    # The complete gain (decided 11 Nov), each part's difference by person over the months after launch, $ a year.
    after = slice(w.burn_in, end)
    part = lambda key: (arm["purchases"][key][after].sum(axis=0) - other["purchases"][key][after].sum(axis=0)) \
        * DOLLARS * year
    completed, durables, lost, sales = map(part, ("completed", "durables", "lost", "sales"))
    face, zero = complete_gain(gain, completed, durables, sales)
    sold = {key.replace("gain_", "sales_"): value for key, value in gains(sales).items() if key != "worse_off"}
    # The cash-advance bound (decided 15 Nov 2026): each person's saving on cash-advance fees and interest, $ a year.
    advances = lambda run: (run["credit"]["fees_advance"][after].sum(axis=0)
                            + run["credit"]["interest_advance"][after].sum(axis=0)) * DOLLARS * year
    saved = advances(other) - advances(arm)
    # Dispersion and the gain by month, stored only (15 Nov 2026).
    spread = lambda values: dict(below_margin_share=round(float((values < REGION_MARGIN).mean()), 4),
                                 percentiles_usd_a_year=dict(zip(map(str, PERCENTILES), np.round(
                                     np.percentile(values, PERCENTILES), 2).tolist())))
    by_month = lambda m: round(float((arm["wealth"][w.burn_in + m] - other["wealth"][w.burn_in + m]).mean())
                               * DOLLARS * 12 / m, 2)
    at_month = dict({str(m): by_month(m) for m in GAIN_MONTHS if m <= w.months}, end=by_month(w.months))
    return dict(real_saving_usd_a_year={key: round((theirs[key] - mine[key]) * year, 2) for key in REAL_LINES},
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


def arm_row(arm, s0, m0, a0, w, u=None):
    """One arm in one seed: gains against S0, participation, the gain split, liquidity, and (pool arms) the contract,
    demurrage and the tests. u is the seed's U run, which M1 is also read against (what demurrage adds, 4 Nov)."""
    end = w.burn_in + w.months
    gain = (arm["wealth"][end] - s0["wealth"][end]) * DOLLARS
    w1, w2 = windows(arm)
    a = arm["series"]
    after = slice(w.burn_in, w.burn_in + w.months)
    issuer = float(np.nansum(a["issuer"][after]) * DOLLARS)
    row = dict(mean_gain_usd=float(gain.mean()), median_gain_usd=float(np.median(gain)), issuer_usd=issuer,
               p_yield_pct=float(np.nanmean(a["p_yield"][w2]) * 1200),
               better_off=float((gain >= 0).mean()), A_launch=float(a["A"][w.burn_in]),
               # Participation in years 2 and 3 (W1) and in years 4 and 5 (W2) after launch (5 Nov).
               A_W1=float(a["A"][w1].mean()), A_W2=float(a["A"][w2].mean()),
               failures_pct=float(a["failure_share"][w2].mean() * 100),
               merchant_fees_pct=float(a["merchant_fees"][w2].mean() * 100), split=split(arm, s0, w),
               real_part=real_part(arm, w), transfers=transfers(arm, w), cash=cash_check(arm, w),
               # This seed's paired differences against S0, for the pool arms against M0 (decided 3 Nov), and for
               # M1 against U, what demurrage adds (decided 4 Nov).
               against=dict(map(lambda other: (other["arm"], differences(arm, other, w)),
                                (s0,) if arm["arm"] == "M0" else (s0, m0, u) if arm["arm"] == "M1" and u
                                else (s0, m0))),
               # Precautionary money, the shortfall a lender paid and failed payments, by window (5 Nov).
               liquidity=liquidity(arm, w),
               # Crossings between E and P (3 Nov), reported only.
               crossings=crossings(arm, w),
               # Earned-wage access, payers in chronic deficit and holders' card bridging (3 Nov), reported only
               # (``REPORT_NOTES``).
               earned_wage=ewa_report(arm, w), chronic=by_chronic(arm, w), card_bridging=card_bridging(arm, w),
               # Credit and purchases by class (11 Nov), reported only.
               by_class=by_class(arm, w),
               **by_quintile(arm, w))
    if arm["arm"] == "M0":
        return row
    verdict = persistence(arm, a0)
    detail = verdict["detail"]
    listed = lambda pair: None if pair is None else list(pair)
    v1_worse = bool(a["failure_share"][w2].mean() > m0["series"]["failure_share"][w2].mean())
    # The use and collapse tests as first registered (P1 against the launch share with no tolerance, X1 on
    # second-window participation below the launch share), stored beside the decided ones; no
    # verdict reads them.
    return dict(row, P=verdict["P"], X=verdict["X"], registered_tests=dict(detail["registered_tests"]),
                verdict=verdict["verdict"], V1_worse=v1_worse,
                V3_harmed=v3_harmed(arm, m0, w).tolist(), c_pct=float(np.nanmean(a["c"][w2]) * 1200),
                r_g_pct=float(np.nanmean(a["r_g"][w2]) * 1200), r_term_pct=float(np.nanmean(a["r_term"][w2]) * 1200),
                theta=float(np.nanmean(a["theta"][w2])), N=float(np.nanmean(a["N"][w2])),
                # The contract's other W2 means (5 Nov): the capital limit N*, demurrage's coverage of the bridging
                # capital cost, the rate a bridge is sealed at and the published quote, % a year (P terms in M2).
                N_star=float(np.nanmean(a["Q"][w2])), coverage=float(np.nanmean(a["coverage"][w2])),
                r_b_pct=float(np.nanmean(a["r_b"][w2]) * 1200), quote_pct=float(np.nanmean(a["quote"][w2]) * 1200),
                # Whether households held pool capital in any month after launch (5 Nov), and demurrage by window.
                pool_formed=bool(np.nanmax(a["owners_capital"][after], initial=0.0) > EPS),
                demurrage=demurrage(arm, w),
                bridges_drawn_over_wanted=float(np.nanmean(a["bridges_drawn_over_wanted"][w2])),
                term_loss_by_year_of_life=years_of_life(arm),
                issuer_would_leave_from_month=detail["issuer_would_leave_from_month"],
                # The issuer's room (the 4 Nov review): since its wallet carries its own costs (3 Nov), the figures'
                # most expense is its headroom beyond them, beside those costs and the most cost it could bear in all,
                # each $ a person a year and as a share of P (None where the run stores no expenses line).
                issuer_headroom_usd_a_year=detail["issuer_most_expense_usd_a_year"],
                issuer_headroom_share_of_P=detail["issuer_most_expense_share_of_P"],
                issuer_costs_usd_a_year=detail["issuer_costs_usd_a_year"],
                issuer_costs_share_of_P=detail["issuer_costs_share_of_P"],
                issuer_most_cost_usd_a_year=detail["issuer_most_cost_usd_a_year"],
                issuer_most_cost_share_of_P=detail["issuer_most_cost_share_of_P"],
                issuer_limit=detail["issuer_zero_real_rate_limit"],
                backing_lowest=detail["backing_lowest"], backing_topup_usd=detail["backing_topup_usd"],
                # Households' realised return as owners (3 Nov), reported only.
                owners=owners_return(arm, w),
                # Their net return less their alternative by window (11 Nov), reported only.
                owners_excess=owners_excess(arm, w),
                # The yardsticks (decided 3 Nov), by window, $ a person a year, for claim (a) across seeds in
                # Step 7: the pool's own margin (persistence test 4) and the joint issuer-and-pool test (None under the
                # as-built coverage test), whether the issuer never records "would leave", and the 90% reading and P
                # routing (``households_pool``).
                own_margin_usd_a_year=listed(detail.get("own_margin_usd_a_year")),
                # The household-held months each window's margin averages over (the 4 Nov review), beside it.
                own_margin_held_months=listed(detail.get("own_margin_held_months")),
                joint_usd_a_year=listed(detail.get("joint_usd_a_year")),
                pays_its_way_W2=verdict["P"]["P4"] if "own_margin_usd_a_year" in detail else None,
                issuer_never_leaves=None if verdict["X"]["X6"] is None else not verdict["X"]["X6"],
                households=households_pool(arm, w),
                **pool_report(arm, w))

"""One run's accounts, read from the engine's records.

The gain split by outside flow, the real part of the cost and the transfers, the cash check, earned wage access,
chronic shortfalls, card bridging, records by class and by quintile, failure counts, the pool's and its owners'
records, crossings between E and P, the distress measures, the monthly series stored with each job, and the
liquidity and demurrage read-outs over the windows after launch.
"""
import numpy as np

from cpm_abm.economy_abm import (CARD_FRAUD, CARD_LENDING_COST, CARD_NETWORK, CARD_PROCESSING, CREDIT_RECORDS, EPS,
                                 EWA_COST, FAIL_COST, FAIL_FEE, FAILURE_COUNTS, HOLDING_COST, LOAN_LOSS_SERIES,
                                 TERM_LENDING_COST, own_returns)
from run_economy_figures import DOLLARS, windows
from cpm_abm.experiment.notes import APPLIES, CLASSES, MEASURES, MONTHLY, MONTHLY_CAPS, POOL_ARMS, WAGE_LOSS

def split(arm, s0, w):
    """Mean gain per capita (USD) split by outside flow: the conservation identity makes the parts add up exactly."""
    a, b = arm["series"], s0["series"]
    after = slice(w.burn_in, w.burn_in + w.months)
    total = lambda key: float(np.nansum(a[key][after] - b[key][after]) * DOLLARS)
    parts = dict(outside_interest_saved=-total("out_interest"), penalties_saved=-total("penalties"),
                 card_fees_saved=-total("merchant_fees"), card_rewards=total("rewards"),
                 conversion_fees_saved=-total("conversion_fees"), pool_costs=-total("pool_operating"),
                 savings_income=total("savings_income"), valuation=total("valuation"), inflation=total("inflation"),
                 # Gas on P and USDC payments, paid to validators outside the household economy (decided 5 Nov).
                 gas_to_validators=-total("gas"),
                 # The card's cash-advance and late fees, paid to its lender (decided 14 Nov 2026: card limits).
                 advance_fees_saved=-total("advance_fees"), late_fees_saved=-total("late_fees"),
                 # The wages of the distress year's extra layoffs, owed by their payers to the outside (decided
                 # 14 Nov 2026: the harsh stress); they follow each arm's spending.
                 wages_to_outside=-total("wages_out"))
    # The rest of the outside flows: USDC's savings rate (M0), checking yield, the reserve return paid on P (its
    # yield to wallet holders and the pool's part, decided 5 Nov), unpaid pool payables, and under the
    # recirculation stress the outside interest that stays in the economy.
    outside = ("outside_interest_saved", "penalties_saved", "card_fees_saved", "card_rewards", "conversion_fees_saved",
               "pool_costs", "savings_income", "gas_to_validators", "advance_fees_saved", "late_fees_saved",
               "wages_to_outside")
    parts["other_outside_flows"] = total("external") - sum(map(parts.get, outside))
    return parts


def by_quintile(run, w):
    """Failure fees, new failed payments and payments to intermediaries outside the economy (net of card rewards) by
    launch-wealth quintile, $ a person a year after launch (31 Oct)."""
    after = slice(w.burn_in, w.burn_in + w.months)
    launch = run["wealth"][w.burn_in]
    quintile = np.minimum((np.argsort(np.argsort(launch)) * 5) // launch.size, 4)
    yearly = lambda path: path[after].sum(axis=0) * DOLLARS * 12 / w.months
    split_by = lambda values: [round(float(values[quintile == q].mean()), 2) for q in range(5)]
    return dict(fees_usd_a_year=split_by(yearly(run["fees"])), failed_usd_a_year=split_by(yearly(run["failed"])),
                transfers_usd_a_year=split_by(yearly(run["transfers"])))


def failure_report(run, w, by_payer=False):
    """Failed, declined and bridged payments after launch in the units of the real failure line (decided 3 Nov),
    stored for the unit change and the monthly cap; nothing here enters a verdict (the real part reads the engine's
    own series of the same counts, ``real_part``).

    monthly, a person a month in each month after launch: fees charged ($), the counts in FAILURE_COUNTS and
    bridged_days (payer-days with a pool bridge to a payer without a card, as the real part counted them as built);
    then the spread of each person's fee units in the month: the share of people with any (payers), the share whose
    month left a failure without its fee, the run's monthly cap binding (binds, 3 Nov), fee units left under a cap
    of 2, 3 and 5 a month (capped_k), the share of people each cap binds (binds_k) and the heaviest payer's units.
    Fee units are counted before the monthly cap, so capped_k and binds_k read hypothetical caps.
    a_year, a person a year after launch: fees charged and under each cap ($), each count, and the units of the person
    with the most over the run.
    payer_months (with ``by_payer``): every person-month with any count, as columns: month after launch from 1, person,
    fees charged ($) and each count in FAILURE_COUNTS. Named apart from the monthly payers, the share of people with
    any fee unit (the 3 Nov review). ``FAILURE_LABELS`` labels every stored key.
    """
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    counts = {key: run["failure_counts"][key][after] for key in FAILURE_COUNTS}
    units, fees = counts["fail_units"], run["fees"][after] * DOLLARS
    # binds: the people whose month left a failure without its fee, the run's own monthly cap binding (3 Nov); the
    # capped_k and binds_k beside it read hypothetical caps from the fee units before the monthly cap.
    spread = dict(payers=(units > EPS).mean(axis=1), heaviest=units.max(axis=1),
                  binds=(units * FAIL_FEE > run["fees"][after] + 1e-12).mean(axis=1),
                  # The share of the month's payers the cap binds, as the S0 check reads it (3 Nov).
                  binds_of_payers=np.divide((units * FAIL_FEE > run["fees"][after] + 1e-12).sum(axis=1),
                                            (units > EPS).sum(axis=1), out=np.zeros(units.shape[0]),
                                            where=(units > EPS).sum(axis=1) > 0),
                  **{f"capped_{cap}": np.minimum(units, cap).mean(axis=1) for cap in MONTHLY_CAPS},
                  **{f"binds_{cap}": (units > cap).mean(axis=1) for cap in MONTHLY_CAPS})
    monthly = dict(fees_usd=fees.mean(axis=1), bridged_days=a["nocard_bridges"][after],
                   **{key: a[key][after] for key in FAILURE_COUNTS}, **spread)
    yearly = lambda values: float(np.sum(values)) * 12 / w.months
    a_year = dict(fees_usd=round(yearly(monthly["fees_usd"]), 2),
                  **{f"fees_usd_cap_{cap}": round(yearly(spread[f"capped_{cap}"]) * FAIL_FEE * DOLLARS, 2)
                     for cap in MONTHLY_CAPS},
                  **{key: round(yearly(monthly[key]), 4) for key in ("bridged_days", *FAILURE_COUNTS)},
                  heaviest_fee_units=round(float(units.sum(axis=0).max()) * 12 / w.months, 4))
    out = dict(monthly={key: np.round(value, 8).tolist() for key, value in monthly.items()}, a_year=a_year)
    if by_payer:
        month, person = np.nonzero(np.logical_or.reduce([path > EPS for path in counts.values()]))
        out["payer_months"] = dict(month=(month + 1).tolist(), person=person.tolist(),
                                   fees_usd=np.round(fees[month, person], 4).tolist(),
                                   **{key: np.round(counts[key][month, person], 6).tolist() for key in FAILURE_COUNTS})
    return out


def real_part(run, w):
    """The real resources one arm's intermediation uses after launch, $ a person (the headline's real part, 31 Oct).

    The same rate for the same service whoever provides it (decided 1 Nov): card credit (outside card and Comet
    bridges, revolving balances, pool bridges to card holders (since card limits, 14 Nov 2026, the part that replaced
    card credit) and, from 3 Nov, the part of pool bridges to payers without a card that paid card-eligible purchases)
    and term credit (outside and pool) per unit of principal-time; a failed bill or wage, and a pool bridge in its
    place (to a payer without a card, or since card limits past a holder's cash line), per unpaid or bridged share, each
    obligation once (``Economy.failure_shares``, 3 Nov; as built, per fee unit and pool payer-day); card
    payments at the rails' processing, fraud and network costs; P payments (USDC in M0) at their gas, one transfer a
    P payment and two a USDC payment (decided 5 Nov: P payments run on stablecoin rails, with no card-style
    processing, fraud or network charge); money and savings held (E, P, USDC, deposits, money market funds,
    pool shares); earned-wage advances at the declared $2 a use (3 Nov), alike in every arm. Also the pool's priced
    costs against the sourced cost of its own lending: a gap the headline does not credit.
    """
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    total = lambda key: float(np.nansum(a[key][after]))
    defi = run["arm"] == "M0"
    if w.failure_shares:
        # The real failure line (decided 3 Nov): in every arm the unpaid share of each failed bill or wage and, for
        # payers without a card, the bridged share of each pool-bridged one, at $2 a unit whatever the fee and the
        # cap, each obligation once. A pool bridge of a card-eligible purchase for a payer without a card is new
        # lending, counted as card credit at 3.4% a year. Since card limits (the review, 14 Nov 2026) a holder's pool
        # bridge is card credit only for the part that replaced card credit: the part that paid in place of failing is
        # a bridged share, as it is for a payer without a card, so no dollar is counted twice.
        card = total("pt_card") + total("pt_pool_card_credit") + total("pt_pool_nocard_card")
        failed = FAIL_COST * (total("fail_shares") + total("bridged_shares"))
        pool = (CARD_LENDING_COST * (total("pt_pool_card_credit") + total("pt_pool_nocard_card"))
                + TERM_LENDING_COST * total("pt_pool_term") + FAIL_COST * total("bridged_shares"))
    else:
        # As built: fee units in every arm and payer-days with a pool bridge to a payer without a card.
        card = total("pt_card") + total("pt_pool_card")
        failed = FAIL_COST * (total("penalties") / FAIL_FEE + total("nocard_bridges"))
        pool = (CARD_LENDING_COST * total("pt_pool_card") + TERM_LENDING_COST * total("pt_pool_term")
                + FAIL_COST * total("nocard_bridges"))
    lines = dict(
        card_credit=CARD_LENDING_COST * card,
        term_credit=TERM_LENDING_COST * (total("pt_term") + total("pt_pool_term")),
        failed_payments=failed,
        card_rails=CARD_PROCESSING * total("card_payments") + (CARD_FRAUD + CARD_NETWORK) * total("card_value"),
        p_rail=total("gas"),
        holding=HOLDING_COST * (total("money_bt") + total("savings_bt") + total("shares_bt")))
    # Earned-wage access (decided 3 Nov): its declared real cost, $2 a use, in every arm's total; none without it.
    lines["earned_wage"] = EWA_COST * total("ewa_uses") if w.earned_wage_share > 0 else 0.0
    usd = lambda value: round(value * DOLLARS, 2)
    beside = {}
    if w.failure_shares:
        # Reported beside the line, outside the total (3 Nov): whole items, the $2 reading of bridged card-eligible
        # purchases, and the line as built.
        beside = dict(failed_payments_items=usd(FAIL_COST * (total("fail_items") + total("bridged_items"))),
                      bridged_card_at_2=usd(FAIL_COST * total("bridged_card")),
                      failed_payments_as_built=usd(FAIL_COST * (total("penalties") / FAIL_FEE
                                                                + total("nocard_bridges"))))
    return dict(**{key: usd(value) for key, value in lines.items()}, total=usd(sum(lines.values())),
                pool_priced_usd=usd(total("pool_operating")), pool_sourced_usd=usd(pool), **beside)


def transfers(run, w):
    """What households pay each intermediary outside the economy, net of what it pays back, against the real cost of
    its service, $ a person after launch; the margin is a transfer to its owners (the boundary rule, 31 Oct).

    Outside lenders: interest, and the card's cash-advance and late fees (decided 14 Nov 2026: card limits),
    against card and term credit. Failure fees: against the cost of a failed payment.
    Card rails: card fees less rewards, against processing, fraud and network. Conversion: fees (real cost not
    sourced). The pool's operating provider: the pool's priced costs (the sourced cost of its lending is in the real
    part). Banks and money funds: the spread kept on E and savings, against holding them. The issuer (U, M1, M2): its
    reserve income net of indexation and of what it pays out as P's yield and to the pool, its custody (decided
    5 Nov), against holding P; it is not a payment operator (5 Nov), so it receives no fee and bears no rail. M0: the
    stablecoin issuer's spread on USDC (the Sky spread in the "reserve" mode, 5 Nov), against holding it. Validators,
    in every arm with P or USDC payments: gas, all of it real (5 Nov). Earned-wage providers (3 Nov, with access
    on): the advances' fees, against the declared $2 a use. M2's indexation is the holder's own yield (decided
    5 Nov), so nothing is set beside the rows as paid by the issuer.
    """
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    total = lambda key: float(np.nansum(a[key][after]))
    # The failure fees' real cost stays $2 a fee unit charged, under the monthly cap too, not the real failure line's
    # unpaid shares (3 Nov): a reading of the rule (4 Nov).
    rows = dict(
        outside_lenders=(total("out_interest") + total("advance_fees") + total("late_fees"),
                         CARD_LENDING_COST * total("pt_card") + TERM_LENDING_COST * total("pt_term")),
        failure_fees=(total("penalties"), FAIL_COST * total("penalties") / FAIL_FEE),
        card_rails=(total("merchant_fees") - total("rewards"),
                    CARD_PROCESSING * total("card_payments") + (CARD_FRAUD + CARD_NETWORK) * total("card_value")),
        conversion=(total("conversion_fees"), None), pool_provider=(total("pool_operating"), None),
        banks_and_funds=(total("deposit_spread"), HOLDING_COST * (total("e_bt") + total("savings_bt"))))
    if w.earned_wage_share > 0:
        # Earned-wage providers (3 Nov): the fees, against the declared $2 a use.
        rows["earned_wage"] = (total("ewa_fees"), EWA_COST * total("ewa_uses"))
    if run["arm"] in POOL_ARMS:
        rows["issuer"] = (total("issuer"), HOLDING_COST * total("P_out"))
    if run["arm"] == "M0":
        rows["stablecoin_issuer"] = (total("issuer_spread"), HOLDING_COST * total("p_bt"))
    if run["arm"] in POOL_ARMS or run["arm"] == "M0":
        rows["validators"] = (total("gas"), total("gas"))
    usd = lambda value: None if value is None else round(value * DOLLARS, 2)
    row = lambda paid, real: dict(paid_usd=usd(paid), real_usd=usd(real), margin_usd=usd(None if real is None
                                                                                       else paid - real))
    known = [(paid, real) for paid, real in rows.values() if real is not None]
    return dict(**{key: row(*value) for key, value in rows.items()},
                total=dict(paid_usd=usd(sum(paid for paid, _ in rows.values())),
                           real_usd=usd(sum(real for _, real in known)),
                           margin_usd=usd(sum(paid - real for paid, real in known))))


def cash_check(run, w):
    """Households' money (E and P) at launch, at the end and at its lowest after launch, $ a person, for everyone and
    for the half holding least at each close: the boundary rule's check that money leaving the economy does not starve
    one arm of cash (31 Oct)."""
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    read = lambda key: dict(launch_usd=round(float(a[key][max(w.burn_in - 1, 0)]) * DOLLARS, 2),
                            end_usd=round(float(a[key][after][-1]) * DOLLARS, 2),
                            lowest_usd=round(float(np.nanmin(a[key][after])) * DOLLARS, 2))
    return dict(everyone=read("liquid"), poorer_half=read("liquid_low"))


def ewa_report(run, w):
    """Earned-wage access after launch (decided 3 Nov), for the S0 check: holders and users (people with an advance
    after launch) as shares of people, and per user a year the advances (payer-days with one), their fees and their
    value, $; None with no user (``REPORT_NOTES``)."""
    after, year = slice(w.burn_in, w.burn_in + w.months), 12 / w.months
    uses, fees, value = (run["ewa"][key][after].sum(axis=0) for key in ("uses", "fees", "value"))
    users = uses > 0
    per_user = lambda total, scale: round(float(total[users].mean()) * year * scale, 2) if users.any() else None
    return dict(holders=round(float(run["population"]["ewa"].mean()), 4), users=round(float(users.mean()), 4),
                advances_a_user_year=per_user(uses, 1.0), fees_usd_a_user_year=per_user(fees, DOLLARS),
                value_usd_a_user_year=per_user(value, DOLLARS))


def by_chronic(run, w):
    """Payers in chronic deficit reported apart (decided 3 Nov): the share flagged at launch and, for people not
    flagged and flagged, failure fees ($), failed bills and wages in unpaid shares (the real failure line's unit) and
    payments to intermediaries outside the economy ($), a person a year after launch; None for an empty group."""
    after, flag = slice(w.burn_in, w.burn_in + w.months), run["chronic"]
    yearly = lambda path, scale: path[after].sum(axis=0) * 12 / w.months * scale
    paths = (("fees_usd_a_year", yearly(run["fees"], DOLLARS)),
             ("failed_shares_a_year", yearly(run["failure_counts"]["fail_shares"], 1.0)),
             ("transfers_usd_a_year", yearly(run["transfers"], DOLLARS)))
    read = lambda group: {key: round(float(values[group].mean()), 4) if group.any() else None for key, values in paths}
    return dict(share=round(float(flag.mean()), 4), not_flagged=read(~flag), flagged=read(flag))


def card_bridging(run, w):
    """Card holders' card bridging of the bills and wages their money could not pay, after launch (decided 3 Nov),
    since card limits their cash advances (14 Nov 2026), for the S0 check against US cash advances: $ a person a year
    over everyone and a holder a year; None with no holder (``REPORT_NOTES``). Beside it (14 Nov 2026), a holder a year:
    the cash-advance and late fees charged and the card balances charged off, $, and the share of holders whose line a
    charge-off closed after launch; a holder is a person of the population's card holding, its class."""
    after = slice(w.burn_in, w.burn_in + w.months)
    a = run["series"]
    yearly = lambda key: float(np.sum(a[key][after])) * 12 / w.months
    total = yearly("card_bridging") * DOLLARS
    holders = float(run["population"]["holder"].mean())
    per_holder = lambda value: round(value / holders, 2) if holders > 0 else None
    return dict(usd_a_year=round(total, 2), usd_a_holder_year=per_holder(total),
                advance_fees_usd_a_holder_year=per_holder(yearly("advance_fees") * DOLLARS),
                late_fees_usd_a_holder_year=per_holder(yearly("late_fees") * DOLLARS),
                charged_off_usd_a_holder_year=per_holder(yearly("charged_off") * DOLLARS),
                lines_closed_share=(round(float(np.sum(a["lines_closed"][after])) / (holders * w.n), 4)
                                    if holders > 0 else None))


def by_class(run, w):
    """Credit and purchases by class in one run (decided 11 Nov, ``REPORT_NOTES``): the mean of each of the
    engine's credit and purchase records in each class (``CLASSES``, labelled 2 * card holder + business income as in
    ``differences``), $ a person a year after launch, NaN for an empty class, with the class sizes. Levels, not
    differences, so S0 has them too."""
    after, year = slice(w.burn_in, w.burn_in + w.months), 12 / w.months
    people = run["population"]
    kind = 2 * people["holder"].astype(int) + people["business"].astype(int)
    count = np.bincount(kind, minlength=len(CLASSES))
    mean = lambda path: np.round(np.divide(np.bincount(kind, weights=path[after].sum(axis=0) * DOLLARS * year,
                                                       minlength=len(CLASSES)),
                                           count, out=np.full(len(CLASSES), np.nan), where=count > 0), 2).tolist()
    # Since card limits (decided 14 Nov 2026) holders can fail too: beside the credit records, each class's failure
    # fees and new failed payments by value, as payer.
    return dict(class_sizes=count.tolist(), **{key: mean(run["credit"][key]) for key in CREDIT_RECORDS},
                **{key: mean(run["purchases"][key]) for key in ("completed", "lost", "durables", "sales")},
                failure_fees=mean(run["fees"]), failed=mean(run["failed"]))


def pool_report(run, w):
    """The pool's small-bill refusals after launch (31 Oct review): fee_refused_usd, the value, $ a person over the run,
    the pool refused payers without a card although the loan alone would have been repaid, because the receipts would
    not also have covered the fee; fee_refused_n, how many payer-days that was. The issuer is a pure custodian
    (decided 5 Nov), so no support fund buys exits."""
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    return dict(fee_refused_usd=round(float(np.nansum(a["fee_refused"][after]) * DOLLARS), 2),
                fee_refused_n=int(np.nansum(a["fee_refused_n"][after])))


def owners_return(run, w):
    """Households' realised return as pool owners (reported only, 3 Nov): the income credited to their shares over
    their capital-time, % a year, before CPI (P terms in M2, like R), in all and net of issuer money (none reaches
    the pool's income under demurrage, decided 4 Nov), by window and by year after launch; their capital in W2,
    $ a person; in W2 the lowest and the capital-weighted mean of each owner's own net return since buying (over at
    most 12 months); and by loan year (decided 4 Nov), for each year after launch in which the pool's loans were
    made (the last band taking any later year), those loans' income to owners over their carried principal-time
    since launch, % a year before CPI, for all pool loans and for bridges and term loans apart (the engine's
    ``vintage`` record): with each month's pool-wide income spread over them by principal-time, and their own income
    beside it; the pool-wide income of months with no pool loan carried, which no loan year takes, is stored as a
    total, $ a person.

    For M2's nominal equivalent add CPI, as the exit comparison adds the index. Owner level, value-weighted, on the NAV
    basis, before CPI and net of issuer money only (decided 4 Nov). "By year" is by year after launch, and by
    loan year beside it (decided 4 Nov). A loan year's income is its loans' coupons less the operating cost they
    carry, write-offs and recoveries, less its share of the month's fixed cost, in proportion
    to its principal-time that month, in the months the pool had capital; demurrage's revenue is not spread over
    them (the engine's record). The spread is an allocation, not an income observed by loan, so the loans' own income
    is kept beside it. None where households held no capital, or where a loan year has no principal-time.
    """
    a, (w1, w2) = run["series"], windows(run)
    years = [slice(w.burn_in + 12 * k, w.burn_in + 12 * (k + 1)) for k in range(w.months // 12)]
    held = lambda span: float(np.sum(a["owners_capital"][span]))
    rate = lambda key, span: round(1200 * float(np.sum(a[key][span])) / held(span), 3) if held(span) > EPS else None
    read = lambda key: dict(W1=rate(key, w1), W2=rate(key, w2), by_year=[rate(key, span) for span in years])
    # Each owner's net rate is at most a whole loss, as the engine's net income is (the 3 Nov review).
    own = own_returns(run["owned"], np.maximum(a["R_net"], -1.0))[w2]
    weight, seen = run["owned"][w2], np.isfinite(own)
    capital = a["owners_capital"][w2]
    # By loan year: each band's income and principal-time, bridging then term, summed over the months after launch in
    # which the pool had capital (R defined). After a final wind-down the loans left are written down outside R's
    # books, so a later payment on one is no owner's income. Each month's pool-wide income goes to the bands by their
    # share of that month's principal-time.
    after = slice(w.burn_in, w.burn_in + w.months)
    owned = np.isfinite(a["R"][after])
    record = {key: run["vintage"][key][after][owned] for key in ("income", "exposure", "shared")}
    carried_all = record["exposure"].sum(axis=(1, 2))
    share = np.divide(record["exposure"], carried_all[:, None, None], out=np.zeros_like(record["exposure"]),
                      where=carried_all[:, None, None] > EPS)
    loans_own, exposure = record["income"].sum(axis=0), record["exposure"].sum(axis=0)
    income = loans_own + (share * record["shared"][:, None, None]).sum(axis=0)
    unallocated = float(record["shared"][carried_all <= EPS].sum()) * DOLLARS
    loan_rate = lambda earned, carried: [round(1200 * float(e) / float(c), 3) if c > EPS else None
                                         for e, c in zip(earned, carried)]
    by_loan_year = lambda earned: dict(all=loan_rate(earned.sum(axis=0), exposure.sum(axis=0)),
                                       bridge=loan_rate(earned[0], exposure[0]), term=loan_rate(earned[1], exposure[1]))
    return dict(gross_pct=read("owners_income"), net_pct=read("owners_income_net"),
                capital_W2_usd=round(float(np.mean(capital)) * DOLLARS, 2) if capital.size else None,
                own_net_W2_lowest_pct=round(float(own[seen].min()) * 1200, 3) if seen.any() else None,
                own_net_W2_mean_pct=round(float((own * weight)[seen].sum() / weight[seen].sum()) * 1200, 3)
                if seen.any() else None,
                by_loan_year=by_loan_year(income), by_loan_year_own=by_loan_year(loans_own),
                shared_unallocated_usd=round(unallocated, 2))


def owners_excess(run, w):
    """Households' realised return as pool owners less their alternative by window (reported only, 11 Nov), % a year
    before CPI, P terms in M2: the income credited to their shares net of issuer money over their capital-time in the
    window (``owners_return``'s net_pct, unrounded), less owners' alternative on pool capital, the reserve rate the
    contract runs at floored at zero plus the owners' spread (the engine's ``_owners_alternative``, constant in a run),
    stored as alternative_pct. None where households held no capital in the window or the run does not reach it."""
    a = run["series"]
    alternative = 1200 * (max(float(run["rho_p"]), 0.0) + run["economy"].owner_spread)

    def excess(span):
        """Households' owner return over the months ``span``, % a year (income net of issuer money over capital-time),
        less the alternative; None where they held no capital."""
        held = float(np.sum(a["owners_capital"][span]))
        return round(1200 * float(np.sum(a["owners_income_net"][span])) / held - alternative, 3) if held > EPS else None

    return dict(alternative_pct=round(alternative, 3), **dict(zip(("W1", "W2"), map(excess, windows(run)))))


def households_pool(run, w):
    """Whether the pool is households' in W2 (decided 3 Nov: the 90% reading; reported, and read by claim (a) across
    seeds in Step 7).

    households_hold_90_W2: households hold at least 90% of pool capital in every W2 month, on capital net of their
    exit requests still unpaid, queued from filing (4 Nov: the base that leans against CPM; ``owners_queued``);
    households_hold_90_W2_all_capital: the same on the decided record's base, all pool capital, households' capital
    over it. Households alone own the pool (decided 5 Nov: the issuer is a pure custodian, with no shares and no
    support fund), so each share is 1 wherever the base has capital, and no issuer money exists to hold it. A W2 month
    without pool capital fails both, households holding 90% of nothing: a reading of the rule (4 Nov). The lowest
    household share in W2 on each base is beside them (None with no capital). p_routes_W2: P
    payments complete in every W2 month. counts: the seed counts toward claim (a)'s share, households holding 90% with
    P routing. A run that ends before W2 ends neither holds nor routes.
    """
    a, spans = run["series"], windows(run)
    _, w2 = spans
    complete = w2.stop <= a["N"].size
    capital, queued = a["N"][w2], a["owners_queued"][w2]
    net = np.divide(a["owners_capital"][w2] - queued, capital - queued, out=np.full(capital.size, np.nan),
                    where=capital - queued > EPS)
    shares = dict(net=net, all_capital=np.divide(a["owners_capital"][w2], capital, out=np.full(capital.size, np.nan),
                                                 where=capital > EPS))
    hold = {key: bool(complete and np.all(np.nan_to_num(value, nan=-1.0) >= 0.9 - 1e-12))
            for key, value in shares.items()}
    lowest = {key: round(float(np.nanmin(value)), 4) if np.isfinite(value).any() else None
              for key, value in shares.items()}
    routes = bool(complete and np.all(a["p_value"][w2] > EPS))
    return dict(households_hold_90_W2=hold["net"], households_hold_90_W2_all_capital=hold["all_capital"],
                household_share_W2_lowest=lowest["net"], household_share_W2_lowest_all_capital=lowest["all_capital"],
                p_routes_W2=routes, counts=bool(hold["net"] and routes))


def crossings(run, w):
    """Crossings between E and P after launch (reported only, 3 Nov): routine crossings, which are free, as a count a
    person a year and a participant a year and as value, $ a person a year; conversions, which pay the fee, as a count
    and value a person a year. A person crosses at most once a step (a day, the dealing or the close) in each kind, in
    the net direction, for the net value (decided 4 Nov)."""
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    total = lambda key: float(np.sum(a[key][after]))
    year, member_months = 12 / w.months, float(np.sum(a["A"][after]))
    return dict(routine=dict(a_year=round(total("crossings") * year, 2),
                             a_participant_year=round(total("crossings") * 12 / member_months, 2) if member_months > 0
                             else None,
                             usd_a_year=round(total("crossed") * DOLLARS * year, 2)),
                conversions=dict(a_year=round(total("conversions") * year, 2),
                                 usd_a_year=round(total("converted") * DOLLARS * year, 2)))


def measures(run, w):
    """The distress measures that apply to the arm and the wage-loss path it ran on (3 Nov, ``WAGE_LOSS``), one value
    per month after launch (stored to redo the reading), and beside them records no verdict reads: completed purchases
    as a count, the largest pool loan as a share of pool capital, and by year, on broad money, E, P and savings, and E
    and P, for participants and non-participants apart (13 Nov review): each person's wallet turnover,
    outflow over its own average balance (``turnover`` in the engine: the mean, the balance-weighted mean, the median
    and the 10th and 90th percentiles), and each person's MicroVelocity, its contribution to the aggregate velocity,
    outflow over everyone's average balance (``microvelocity`` in the engine: the group's sum, the median, the 90th
    percentile and the share of the sum from the top tenth of persons), and MicroVelocity as its authors define it,
    from the holding time of every unit of money under first in first out and last in first out (13 Nov,
    ``holding_velocity`` in the engine)."""
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    names = dict(map(lambda name: (name, MEASURES[name]), APPLIES[run["arm"]]), **WAGE_LOSS)
    # Under the loan-loss bound (decided 12 Nov) the principal discharged a person a month, by lender and class,
    # the bound's amount carried forward undischarged at the close (the 13 Nov review), and the pool's term coupon for
    # business products a month, stored beside them; a run without it has no such series and stores none.
    names.update({key: key for key in (*LOAN_LOSS_SERIES, "loss_carried", "r_term_business") if key in a})
    stored = dict(map(lambda item: (item[0], np.nan_to_num(a[item[1]][after]).round(12).tolist()), names.items()))
    # Records only, read by no verdict (3 and 12 Nov, the engine's ``MEASURE_SERIES``), a month after launch, None where
    # undefined (no pool capital): completed purchases as a count a person a month, and the largest single pool loan
    # and the largest borrower's pool debt as shares of pool capital. Turnover's and MicroVelocity's readings by year
    # after launch. The engine's names and readings are imported here, so these records stay inside this function.
    from cpm_abm.economy_abm import MEASURE_SERIES, holding_velocity, microvelocity, turnover
    clean = lambda values: [round(float(v), 12) if np.isfinite(v) else None for v in values]
    stored.update({key: clean(a[key][after]) for key in MEASURE_SERIES if key in a})
    if "velocity" in run:
        stored["turnover"] = turnover(run["velocity"], run["participant"][after])
        stored["microvelocity"] = microvelocity(run["velocity"], run["participant"][after])
    if "coinage" in run:
        # MicroVelocity from the holding time of every unit of money (13 Nov), first in first out and last in first
        # out, by year and group: the sum, median, 90th percentile and top tenth's share of V_i, the value-weighted
        # mean holding time of money spent and the histogram of value spent by holding time (``holding_velocity``).
        stored["holding_velocity"] = holding_velocity(run["coinage"], run["velocity"], run["participant"][after])
    return stored


def monthly(run, w):
    """The arm's stored monthly series after launch (``MONTHLY``, 3 Nov), None where a value is undefined: zero would
    wrongly read an undefined rate as a rate of zero."""
    a, after = run["series"], slice(w.burn_in, w.burn_in + w.months)
    clean = lambda values: [round(float(v), 12) if np.isfinite(v) else None for v in values]
    return {key: clean(a[key][after]) for key in MONTHLY[run["arm"]]}


def by_windows(run, key, how):
    """One series read over W1 and W2 (years 2 and 3, years 4 and 5 after launch), None for a window the run does not
    reach or where the series is undefined throughout (5 Nov): ``how`` "stock" is its monthly mean, $ a person; "flow"
    its monthly sum a year, $ a person a year."""
    values = run["series"][key]
    read = dict(stock=lambda part: float(np.nanmean(part)) * DOLLARS,
                flow=lambda part: float(np.nansum(part)) * DOLLARS * 12 / part.size)[how]
    spans = [values[span] for span in windows(run)]
    return [round(read(part), 4) if part.size and np.isfinite(part).any() else None for part in spans]


# The parts of the shortfall a lender paid and of the precautionary money (5 Nov, ``LIQUIDITY_NOTE``), each the
# engine series it reads.
COVERED = dict(pool_bridges="bridges", card_bridging="card_bridging", revolved="revolved",
               comet_bridging="comet_bridging", earned_wage="ewa_value")
HELD = dict(buffers="buffers", idle_p="idle", pool_idle="pool_idle")


def liquidity(run, w):
    """Precautionary money and the shortfall a lender paid, by window, in any arm (5 Nov, ``LIQUIDITY_NOTE``).

    The total precautionary money is the engine's record (households' buffers chosen at dealing and the pool's idle
    cash; idle P, inside the buffers, beside it), a mean stock, $ a person; the shortfall covered is what payers' own
    money and same-day savings could
    not pay and a lender paid, counted alike in every arm (``COVERED``), $ a person a year; the money held per dollar
    of it a year is their ratio, None without any. Failed payments a year beside them, by value and in unpaid shares.
    """
    covered = {name: by_windows(run, key, "flow") for name, key in COVERED.items()}
    shortfall = [None if None in parts else round(sum(parts), 4) for parts in zip(*covered.values())]
    held = by_windows(run, "precautionary", "stock")
    ratio = [round(money / need, 4) if money is not None and need is not None and need > EPS else None
             for money, need in zip(held, shortfall)]
    shares = [round(float(np.sum(part)) * 12 / part.size, 6) if part.size else None
              for part in (run["series"]["fail_shares"][span] for span in windows(run))]
    return dict(precautionary_usd=held, **{f"{name}_usd": by_windows(run, key, "stock") for name, key in HELD.items()},
                shortfall_covered_usd_a_year=shortfall,
                **{f"{name}_usd_a_year": value for name, value in covered.items()},
                precautionary_per_dollar_covered=ratio, failed_usd_a_year=by_windows(run, "failures", "flow"),
                failed_shares_a_year=shares)


def demurrage(run, w):
    """Competitive P and demurrage in a pool arm by window (decided 4 and 5 Nov; no demurrage in U), $ a person a
    year: the yield on wallet P before demurrage (rho_p - c_I on wallet balance-time), the reserve return on the pool's
    own P cash, what the issuer keeps (its custody), demurrage withheld from P's yield into the pool, the coupon cut
    demurrage paid and the capital cost of bridging (owners' alternative on its principal-time); the issuer's derived
    share s_issuer and, as a bound recorded only (decided 4 Nov), the W2 mean of the most a monopoly issuer could
    take (s_monopoly_W2, None where no share reaches owners' alternative); and the issuer's complete wallet, $ a person
    a year (5 Nov)."""
    a, (_, w2) = run["series"], windows(run)
    share = a["s_issuer"][np.isfinite(a["s_issuer"])]
    bound = a["s_monopoly"][w2]
    return dict(s_issuer=round(float(share[0]), 6) if share.size else None,
                s_monopoly_W2=round(float(np.nanmean(bound)), 4) if np.isfinite(bound).any() else None,
                **{f"{key}_usd_a_year": by_windows(run, key, "flow")
                   for key in ("wallet_yield", "float_pool", "float_issuer", "charges", "covered",
                               "bridge_capital_cost")},
                issuer_wallet_usd_a_year=by_windows(run, "issuer_wallet", "flow"))

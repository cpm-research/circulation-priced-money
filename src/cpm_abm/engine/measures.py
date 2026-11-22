"""Reading a run's records: the Gini coefficient, wallet turnover, MicroVelocity and holding velocity; and the
arithmetic of the day's records of failure passed along and of dependence on netting, which the settlement calls.
"""
import numpy as np

from cpm_abm.engine.constants import EPS
from cpm_abm.engine.ledger import COIN_CONVENTIONS, COIN_EDGES


def gini(values):
    """Gini coefficient (mean absolute difference over twice the mean) on raw values; negative wealth is kept.

    With negative values the coefficient can exceed 1; it is undefined when total wealth is not positive.
    """
    x = np.sort(values)
    total = x.sum()
    if total <= 0:
        return float("nan")
    n = x.size
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * total))


def _velocity_groups(velocity, participant):
    """The shared set-up of ``turnover`` and ``microvelocity``: the number of years, each person's group by year (a
    participant in a year is in the network in at least half of the year's months, a reading) and each person's
    balance-time by year on the three definitions of money (the 3 Nov row): ``broad``, E, P, outside savings and pool
    shares at NAV; ``e_p_savings``, E, P and savings; ``e_p``, E and P alone."""
    participant = np.asarray(participant, bool)
    years = velocity["outflow"].shape[0]
    member = np.array([participant[12 * k:12 * (k + 1)].mean(axis=0) >= 0.5 for k in range(years)], bool)
    money = dict(e_p=velocity["money_bt"])
    money["e_p_savings"] = money["e_p"] + velocity["savings_bt"]
    money["broad"] = money["e_p_savings"] + velocity["shares_bt"]
    return years, member, money


def turnover(velocity, participant):
    """Each person's wallet turnover (decided 3 Nov as MicroVelocity; renamed after the 13 Nov review,
    since it is not the paper's measure), a reading of records, used by no rule: by year after launch, on three
    definitions of money, for participants and non-participants apart, the distribution of each person's turnover.

    ``velocity`` is a run's ``velocity`` (``VELOCITY_RECORDS``, rows by year after launch), ``participant`` its
    participation flags for the months after launch. A person's turnover in a year is the rate at which it spends
    the money it holds: its payments to others out of its money over the year over its OWN average balance over the
    year, in turns a year, 12 x outflow / balance-time with balance-time in unit-months (the inverse of its average
    holding time; a part year gives the same formula). It carries no share of the money stock, so it is not the
    MicroVelocity of Campajola, D'Errico and Tessone (``microvelocity`` is). The outflow is the same on every
    definition: payments to others leave E and P, conversion fees paid to outsiders included, and a move between a
    person's own money and its savings or shares is not a payment. The definitions are ``_velocity_groups``'. A
    person with no balance-time on a definition has no turnover on it and is left out (``people`` counts those kept).
    For each group and year: ``mean``, ``median``, ``p10``, ``p90`` and ``weighted``, the balance-weighted mean, which
    is the group's total outflow over its total average balance. None where a group is empty.

    Hand case: a person holding 100 all year (balance-time 1,200) that pays out 1,200 turns its money 12 times a
    year; a second person holding 300 that pays out 1,200 turns it 4 times; the mean is 8 and the weighted mean is
    (1,200 + 1,200) / (100 + 300) = 6.
    """
    years, member, money = _velocity_groups(velocity, participant)
    stat = lambda read, v: round(float(read(v)), 12) if v.size else None

    def one_year(outflow, bt):
        """One group's turnover in one year: 12 x each person's outflow over its own balance-time, for those with a
        balance, summarised as the count kept, mean, balance-weighted mean, median and 10th and 90th percentiles."""
        kept = bt > EPS
        v, held = 12 * outflow[kept] / bt[kept], bt[kept] / 12
        return dict(people=int(kept.sum()), mean=stat(np.mean, v),
                    weighted=stat(lambda x: (x * held).sum() / held.sum(), v), median=stat(np.median, v), p10=stat(lambda x: np.percentile(x, 10), v),
                    p90=stat(lambda x: np.percentile(x, 90), v))

    def group(bt, inside):
        """``one_year`` for participants (``inside`` True) or non-participants on one definition of money, year by
        year, as one list per statistic."""
        rows = [one_year(velocity["outflow"][k][member[k] == inside], bt[k][member[k] == inside]) for k in range(years)]
        return {key: [row[key] for row in rows] for key in ("people", "mean", "weighted", "median", "p10", "p90")}

    return {name: dict(participants=group(bt, True), non_participants=group(bt, False)) for name, bt in money.items()}


def microvelocity(velocity, participant):
    """MicroVelocity (Campajola, D'Errico and Tessone, arXiv 2201.13416, equations 5 to 7; decided 3 Nov, corrected
    after the 13 Nov review), a reading of records, used by no rule: by year after launch, on three
    definitions of money (``_velocity_groups``), for participants and non-participants apart.

    In the paper a person's MicroVelocity carries its share of the total money stock: V_i = (M_i / M) x the mean of
    1 / tau over its money, and the aggregate velocity is the SUM of the V_i. Here a person's yearly contribution is
    12 x its outflow over the year over the total balance-time, in unit-months, of everyone (both groups) on the same
    definition of money, so the contributions of all persons sum to the aggregate velocity, 12 x total outflow over
    total balance-time, in turns a year (a part year gives the same formula). This equals the paper's measure only up
    to money held across the year's ends (a unit received before the year and spent in it, or received in it and
    spent after, is counted by its spending alone) and when the total stock is steady within the year (the paper
    weights each moment by that moment's stock; this divides by the year's average stock). No ages of money units
    are tracked: only each person's outflow and balance-time are recorded. The outflow is ``turnover``'s.

    For each group and year: ``people`` (everyone in the group), ``sum`` (the group's part of the aggregate
    velocity), ``median`` and ``p90`` of its members' contributions, and ``top_tenth_share``, the share of the
    group's sum from its top tenth of persons by contribution (the largest ceil(people / 10)). None where a group is
    empty or nobody holds money on the definition; ``top_tenth_share`` None where the sum is zero.

    Hand case: a person holding 100 all year (balance-time 1,200) and one holding 300 (3,600), each paying out 1,200:
    the total balance-time is 4,800, so each contributes 12 x 1,200 / 4,800 = 3, and the aggregate velocity is
    3 + 3 = 6, as their total outflow 2,400 over the total average balance 400.
    """
    years, member, money = _velocity_groups(velocity, participant)
    stat = lambda read, v: round(float(read(v)), 12) if v.size else None

    def top_share(v):
        """The share of the sum of ``v`` from its largest tenth (the top ceil(size / 10) values); None when ``v`` is
        empty or its sum is not positive."""
        total = v.sum()
        if v.size == 0 or total <= 0:
            return None
        top = np.sort(v)[::-1][:int(np.ceil(v.size / 10))]
        return round(float(top.sum() / total), 12)

    def one_year(outflow, bt, inside):
        """One group's contributions in one year: 12 x each member's outflow over everyone's total balance-time,
        summarised as the count, sum, median, 90th percentile and the top tenth's share."""
        total = float(bt.sum())
        v = 12 * outflow[inside] / total if total > EPS else np.zeros(0)
        return dict(people=int(inside.sum()), sum=stat(np.sum, v), median=stat(np.median, v),
                    p90=stat(lambda x: np.percentile(x, 90), v), top_tenth_share=top_share(v))

    def group(bt, inside):
        """``one_year`` for participants (``inside`` True) or non-participants on one definition of money, year by
        year, as one list per statistic."""
        rows = [one_year(velocity["outflow"][k], bt[k], member[k] == inside) for k in range(years)]
        return {key: [row[key] for row in rows] for key in ("people", "sum", "median", "p90", "top_tenth_share")}

    return {name: dict(participants=group(bt, True), non_participants=group(bt, False)) for name, bt in money.items()}


def holding_velocity(coinage, velocity, participant):
    """MicroVelocity from the holding time of every unit of money (Campajola, D'Errico and Tessone, arXiv 2201.13416,
    equations 4 to 7 and their estimator; 13 Nov), a reading of records, used by no rule: by year after launch, for
    each convention (``COIN_CONVENTIONS``) and for participants and non-participants apart (``_velocity_groups``).

    ``coinage`` is a run's ``coinage`` (``Coinage``'s records), ``velocity`` its ``velocity`` and ``participant`` its
    participation flags for the months after launch. Money is E, P and outside savings (``e_p_savings``). A person's
    V_i in a year is 12 x its ``held`` (the sum over its units spent of value x days of the holding spell inside the
    year / holding time) over the year's total balance-time of everyone, in unit-months: the time average of the
    paper's V_i(t) = sum over tau of (1 / tau) w_i(tau) / M(t), in turns a year, taking M(t) at its yearly average as
    ``microvelocity`` does. The V_i of all persons sum to the aggregate velocity. Units unspent when the run ends are
    right-censored and left out, as in the paper, so the last year reads low; spells that began before launch count
    only their days after it.

    For each convention, group and year: ``people``; ``sum`` of V_i (the group's part of the aggregate velocity);
    ``median`` and ``p90`` of V_i; ``top_tenth_share``, the share of the sum from the group's top tenth of persons;
    ``mean_tau``, the value-weighted mean holding time in days of money spent in the year; and ``histogram``, the value
    spent in the year by holding time (``COIN_EDGES``, the last bin 961 days and above). None where undefined.

    Hand case: one person, one year, holding 100 throughout (balance-time 1,200 unit-months), which it spends and
    receives again every ten days, so 36 ten-day spells of 100 lie inside the year: each adds 100 x 10 / 10 = 100 to
    ``held``, 3,600 in all, and V = 12 x 3,600 / 1,200 = 36 turns a year, one turn per ten-day holding time;
    ``mean_tau`` is 10.
    """
    years, member, money = _velocity_groups(velocity, participant)
    bt = money["e_p_savings"].sum(axis=1)
    stat = lambda read, v: round(float(read(v)), 12) if v.size else None

    def top_share(v):
        """The share of the sum of ``v`` from its largest tenth (the top ceil(size / 10) values); None when ``v`` is
        empty or its sum is not positive."""
        total = v.sum()
        if v.size == 0 or total <= 0:
            return None
        return round(float(np.sort(v)[::-1][:int(np.ceil(v.size / 10))].sum() / total), 12)

    def one_year(c, k, inside):
        """One group's V_i in year ``k`` under convention ``c``: 12 x each member's ``held`` over the year's total
        balance-time, summarised as the count, sum, median, 90th percentile and top tenth's share, with the
        value-weighted mean holding time of money spent and the histogram of that money by holding time."""
        v = 12 * coinage["held"][c, k][inside] / bt[k] if bt[k] > EPS else np.zeros(0)
        spent, spent_tau = float(coinage["spent"][c, k][inside].sum()), float(coinage["spent_tau"][c, k][inside].sum())
        return dict(people=int(inside.sum()), sum=stat(np.sum, v), median=stat(np.median, v),
                    p90=stat(lambda x: np.percentile(x, 90), v), top_tenth_share=top_share(v),
                    mean_tau=round(spent_tau / spent, 12) if spent > EPS else None,
                    histogram=np.round(coinage["histogram"][c, k][inside].sum(axis=0), 12).tolist())

    def group(c, inside):
        """``one_year`` for participants (``inside`` True) or non-participants under convention ``c``, year by
        year, as one list per statistic; empty with no year."""
        rows = [one_year(c, k, member[k] == inside) for k in range(years)]
        return {key: [row[key] for row in rows] for key in rows[0]} if rows else {}

    return dict(edges=COIN_EDGES.tolist(), **{name: dict(participants=group(c, True), non_participants=group(c, False))
                                              for c, name in enumerate(COIN_CONVENTIONS)})


# The bins of the days of a month by how many payers had a knock-on failure that day: 0, 1, 2 to 3, 4 to 7, 8 to 15,
# 16 to 31 and 32 or more. KNOCK_ON_EDGES holds each bin's lowest count after the first.
KNOCK_ON_BINS = ("0", "1", "2_3", "4_7", "8_15", "16_31", "32_up")
KNOCK_ON_EDGES = np.array([1, 2, 4, 8, 16, 32])
# The monthly series of the two records, in every arm: amounts a person in months of mean spending, at face value
# (own_shortfall, knock_on, knock_on_positive, netting_value, cash_completed, netting_lost), and counts in the month
# (payer-days in own_shortfall_n, knock_on_n and netting_n; days in knock_on_days_* and netting_days).
CHAIN_SERIES = ("own_shortfall", "knock_on", "knock_on_positive", "own_shortfall_n", "knock_on_n",
                *("knock_on_days_" + key for key in KNOCK_ON_BINS), "netting_days", "netting_n", "netting_value",
                "cash_completed", "netting_lost")


def shortfall_split(failed, own):
    """One day's failed amounts split into own shortfall and knock-on (the robustness plan, section 4.1), a record
    read by no rule.

    ``failed`` is each payer's failed amount in the day's final solution and ``own`` what it fails in one sweep
    started from every payer completing in full, so with every payment owed to it today arriving in full, under the
    day's final pool queue: its own shortfall. The knock-on part is the rest, failure that happens only because
    receipts were short; with pool rationing it can be slightly negative, since a neighbour's failure can free pool
    cash, so the signed sum and the positive part are both returned. A part counts as positive above EPS. Returns the
    day's own-shortfall amount, signed and positive knock-on amounts, the payers with each, and the bin of
    ``KNOCK_ON_BINS`` the day falls in by its payers with a knock-on failure.

    Hand case: A holds nothing and owes B 10; B holds 4, owes C 10 and is owed A's 10. With full receipts A fails 10
    and B nothing; in the solution B receives nothing, pays 4 and fails 6. Failed 16: own shortfall 10, knock-on 6,
    one payer with a knock-on failure, so the day is in bin "1".
    """
    knock = failed - own
    positive = knock > EPS
    payers = int(positive.sum())
    return dict(own=float(own.sum()), knock_on=float(knock.sum()), knock_on_positive=float(knock[positive].sum()),
                own_n=int((own > EPS).sum()), knock_on_n=payers,
                bin=int(np.searchsorted(KNOCK_ON_EDGES, payers, side="right")))


def netting_set(candidate, b, s, paid):
    """The largest set of payers whose completed payments exist only because the day is settled as one simultaneous
    solution (the robustness plan, section 4.2), a record read by no rule.

    ``candidate`` flags the payers that complete a positive share of a payment due today and have no means of their
    own today; ``b``, ``s`` and ``paid`` are the day's payments' payers, payees and the amounts their payees received
    in the final solution. A member must also receive nothing from a payer outside the set. Payers are removed until
    nothing changes: whoever is paid by a payer outside the set leaves it, which can make its own payees outsiders'
    payees in turn. The removal keeps every set with the three properties inside it, so what is left is the largest.

    Hand case: A and B hold nothing and owe each other 10, and both pay in the solution: the set is {A, B}. If A holds
    1 it is no candidate, B is paid by A and leaves too, and the set is empty.
    """
    inside = np.asarray(candidate, bool).copy()
    while inside.any():
        from_outside = np.bincount(s, weights=paid * ~inside[b], minlength=inside.size)
        kept = inside & (from_outside <= EPS)
        if (kept == inside).all():
            break
        inside = kept
    return inside


def netting_loss(f, inside, means, need, receipts, value, tolerance=1e-14, most=20000):
    """The completed value lost when the netting set is held at zero (the robustness plan, section 4.2), a record
    read by no rule.

    ``f`` is each payer's completed share of its payments in the day's final solution and ``inside`` the netting set
    (``netting_set``). The day's credit is held fixed in ``means``: each payer's own money with the savings it used,
    its pool draw, Comet cover, cash advance and earned-wage advance in the final solution. The set's shares are set to
    zero and the completion map is repeated downward from the final solution until no share moves by more than
    ``tolerance``: a payer's share becomes min(previous share, (means + receipts at the previous shares) / need), where
    ``receipts`` maps everyone's shares to everyone's receipts. ``value`` is each payer's payments at full completion;
    returns the fall in completed value and the shares reached.

    Hand case: A and B hold nothing and owe each other 10. Held at zero neither receives anything, so both stay at
    zero and the value lost is 20.
    """
    has_need = need > 0
    share = np.where(inside, 0.0, f)
    for _ in range(most):
        reach = np.divide(means + receipts(share), need, out=np.ones_like(share), where=has_need)
        lower = np.where(has_need, np.minimum(share, reach), share)
        moved = float(np.abs(lower - share).max()) if share.size else 0.0
        share = lower
        if moved <= tolerance:
            break
    return float(value.dot(f - share)), share

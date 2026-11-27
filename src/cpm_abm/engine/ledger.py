"""The record tables and the age of money.

The tables the world keeps (the obligation list, term requests, the loan book and durables), each a dict of
equal-length arrays, with the helpers that append to, filter, merge and read them; the order payments are made in
within an owner's budget or a payer's day; and Coinage, the age of every unit of each person's money for
MicroVelocity, a record only.
"""
from functools import reduce

import numpy as np

from cpm_abm.engine.constants import DAYS, TERM


def allocate(owner, cost, keys, budget):
    """Vectorised priority payment: pay each owner's claims in order from that owner's budget.

    Claims are sorted by owner, then by ``keys`` (lexsort order: the last key
    is primary). Each claim receives what is left of its owner's budget after
    the earlier claims, capped at its cost. Returns the amount paid per claim.
    """
    order = np.lexsort(tuple(keys) + (owner,))
    o, x = owner[order], cost[order]
    cum = np.cumsum(x)
    before = cum - x - np.concatenate(([0.0], cum))[np.searchsorted(o, o)]
    paid = np.empty_like(x)
    paid[order] = np.clip(budget[o] - before, 0.0, x)
    return paid


# Whole items are counted in the order that returns fewest, smallest first. It is the lower bound
# on returned items, and the model's day has no chronological order.
def in_order(payer, cost):
    """Each payment's running total within its payer's day, smallest first (the whole-item count).

    A bank paying whole payments returns those whose running total exceeds the money the payer has for them. Paying
    smallest first pays the most payments any order could, so the count is the fewest returned whatever the order.
    ``cost`` is what each payment takes from its payer's money.
    """
    order = np.lexsort((cost, payer))
    sorted_payer, sorted_cost = payer[order], cost[order]
    running = np.cumsum(sorted_cost)
    first = np.searchsorted(sorted_payer, sorted_payer)          # each payment's payer's first place in the order
    within = np.empty(payer.size)
    within[order] = running - running[first] + sorted_cost[first]
    return within


# --------------------------------------------------------------------------------------------------------------------
# Small record helpers: the obligation list, term requests, loan book and durables are dicts of equal-length arrays.
# --------------------------------------------------------------------------------------------------------------------
def _empty(fields, dtypes):
    """Empty record arrays with the given fields and dtypes."""
    return {key: np.zeros(0, dtype) for key, dtype in zip(fields, dtypes)}


def _concat(old, new):
    """Append records field by field."""
    return {key: np.concatenate([old[key], np.asarray(new[key], old[key].dtype)]) for key in old}


def _take(records, keep):
    """Keep the selected records (mask or index) in every field."""
    return {key: value[keep] for key, value in records.items()}


def _merge_sorted(records, new, key="settle"):
    """Insert ``new`` records into ``records`` sorted by ``key``: the order a stable sort of the two appended gives
    (each new record after the old ones of its key, new records in their own stable order), in one pass."""
    old_n = records[key].size
    k = np.asarray(new[key]).size
    order = np.argsort(np.asarray(new[key]), kind="stable")
    slot = np.searchsorted(records[key], np.asarray(new[key])[order], side="right") + np.arange(k)
    rest = np.ones(old_n + k, bool)
    rest[slot] = False
    out = {}
    for name, old in records.items():
        merged = np.empty(old_n + k, old.dtype)
        merged[rest] = old
        merged[slot] = np.asarray(new[name], old.dtype)[order]
        out[name] = merged
    return out


def _is_kind(kind, kinds):
    """Whether each loan's ``kind`` is one of ``kinds``: the values of ``np.isin(kind, kinds)``, at a fraction of its
    cost on the book's few kinds (a speed device)."""
    return reduce(np.logical_or, [kind == one for one in kinds])


def _overdue_of(f):
    """Term records' scheduled but unpaid amount (arrears) from book fields ``f`` (whole fields or gathered rows):
    overdue principal plus due interest (``_World._overdue``)."""
    scheduled = np.minimum(f["instal"] * f["ndue"], f["original"])
    owed = np.maximum(scheduled - (f["original"] - f["principal"]), 0.0)
    return np.where(f["kind"] == TERM, owed + f["interest_due"], 0.0)


# The loan book's fields a budget's debts read (``_World._due_soon``).
_DUE_SOON_FIELDS = ("kind", "due", "pool", "principal", "rate", "interest", "instal", "interest_due", "ndue",
                    "original")


# ====================================================================================================================
# Holding times of money (MicroVelocity as its authors define it), a record only
# ====================================================================================================================
# The bin edges of the holding-time histogram, in days: [1, 2), [2, 4), ..., [481, 961) and 961 and above.
COIN_EDGES = np.array([1, 2, 4, 8, 15, 31, 61, 121, 241, 481, 961], float)
# The two conventions for which units leave an account first: first in first out, last in first out.
COIN_CONVENTIONS = ("fifo", "lifo")
# Days kept as one cohort each; older money is kept in one cohort per calendar month of receipt.
COIN_RECENT = 90
# Cohorts a day's spending is taken from in the second tier, and three times as many in the third, after the edge
# cohort alone and before every cohort (``Coinage._consume``): a speed device that leaves the result unchanged to
# rounding.
COIN_WINDOW = 12
# The ledger's records, each with the convention as first axis and the year after launch as second (``Coinage``).
COINAGE_RECORDS = ("held", "spent", "inverse", "spent_tau", "histogram")


class Coinage:
    """The age of every unit of each person's money, for MicroVelocity (Campajola, D'Errico and Tessone, arXiv
    2201.13416, equations 4 to 7 and their estimator), a record only: no rule, price, decision or draw reads it.

    The paper: V = sum over persons of V_i, V_i(t) = sum over tau of (1 / tau) w_i(tau) / M(t), where w_i(tau) is
    the value person i holds at t whose holding time is tau, the whole time from the transaction in which i received
    the unit to the one in which i spends it (whole periods, at least 1), and M(t) is all money. Money still unspent
    when the data end is right-censored and left out. A move between a person's own balances is not a spending, so the
    unit keeps its age. An account ledger has no coin identities, so a convention says which units leave first; the
    authors suggest last in first out may be the most meaningful and leave it open. Both are kept here.

    The money tracked is one stock per person (the engine's E, P and outside savings, ``e_p_savings``). Each day the
    ledger takes the person's day totals: ``inflow`` (new units dated today), ``spend`` (units leaving in payments to
    others, which ends their holding spell), ``removal`` (units leaving without being spent, by the same convention,
    with no holding time recorded) and ``scale`` (units leaving pro rata over every cohort: CPI's loss of value).
    Within a day the spending and the removal are taken together, each cohort's part split between them in proportion,
    so their order within the day does not matter; today's inflow can be spent today (tau 1 under last in first out).

    Cohorts: one a day for the last ``COIN_RECENT`` days, then one a calendar month of receipt, each holding its amount
    and its amount-weighted receipt day. A unit from a merged month is given the cohort's mean receipt day s_bar, so its
    1 / tau is 1 / (t - s_bar) in place of the mean of 1 / (t - s) over the month: by Jensen's inequality the error is
    second order, about var(s) / (t - s_bar)^3, at most (30^2 / 12) / 90^3 = 1e-4 a unit of value against 1 / 90 =
    0.011, a relative error below 1% (75 / 90^2), and smaller for older money.

    A unit of value w received on day s and spent on day t has holding time tau = max(t - s, 1) days and is held over
    the tau days (t + 1 - tau, t + 1], the days after its receipt up to its spending, or its spending day alone; it adds
    w / (tau x M) to V_i on each, so w x (days of that spell inside a window) / tau to the window's sum of V_i x M.
    Records, by convention, year after launch (360 days from the launch day) and person (``COINAGE_RECORDS``):
    ``held``, the sum of w x overlap(spell, year) / tau over every unit spent (the numerator of the year's
    time-integrated V_i; 12 x it / the year's total balance-time in unit-months is V_i in turns a year), ``spent``, the
    value spent in the year, ``inverse``, the sum of w / tau over it, ``spent_tau``, the sum of w x tau, and
    ``histogram``, the value spent in the year by holding time (``COIN_EDGES``). Spending before launch is in none.

    Example: 100 received on day 0 and spent on day 10, launch day 0: tau = 10, the spell is days 1 to 10, all in
    year 0, so ``held`` adds 100 x 10 / 10 = 100, ``spent`` 100, ``inverse`` 10 and ``spent_tau`` 1,000, in the bin
    [8, 15). Received 100 on day 0 and 100 on day 20, then 100 spent on day 30: tau 30 under first in first out (the
    day 0 units) and 10 under last in first out (the day 20 units).
    """

    def __init__(self, stock, days, launch, years, recent=COIN_RECENT):
        """``stock``: each person's opening money, dated day 0; ``days``: the run's length in days; ``launch``: the
        launch day (year 0 starts there); ``years``: the record rows."""
        stock = np.asarray(stock, float)
        self.n, self.recent, self.launch, self.years = stock.size, recent, launch, years
        self.months = max(-(-days // DAYS), 1)
        self.t = 0
        # Per convention and person: one cohort a calendar month of receipt (column = month), and one a day for the
        # last ``recent`` days, receipt day d in column months + d mod recent (a ring, so nothing moves as days pass);
        # ``when`` holds amount x receipt day for the monthly cohorts. Cohorts in age order are the monthly ones up to
        # ``_last_month`` and then the recent days (``_column`` maps that order to the array). ``edge`` holds a receipt
        # day before which (first in first out) or after which (last in first out) the person holds nothing: where its
        # next spending starts.
        # Cohorts come first in the arrays (cohort, convention, person), so a day's column is contiguous.
        self.amt = np.zeros((self.months + recent, 2, self.n))
        self.when = np.zeros((self.months, 2, self.n))
        self.amt[self.months] = stock          # received on day 0
        self.edge = np.zeros((2, self.n), int)
        self.rec = dict(held=np.zeros((2, years, self.n)), spent=np.zeros((2, years, self.n)),
                        inverse=np.zeros((2, years, self.n)), spent_tau=np.zeros((2, years, self.n)),
                        histogram=np.zeros((2, years, self.n, COIN_EDGES.size)))

    def total(self):
        """Each person's money in the ledger, by convention (2, n)."""
        return self.amt.sum(axis=0)

    def _last_month(self):
        """The newest monthly cohort that can hold money today (-1 while no day is older than ``recent``)."""
        return (self.t - self.recent) // DAYS if self.t >= self.recent else -1

    def _column(self, pos, last):
        """The array column of each cohort position in age order (0 the oldest month)."""
        return np.where(pos <= last, pos, self.months + (self.t - self.recent + pos - last) % self.recent)

    def _first_day(self, pos, last):
        """The first receipt day of each cohort position (the day after today past the newest)."""
        return np.where(pos <= last, DAYS * pos, self.t - self.recent + pos - last)

    def _last_day(self, pos, last):
        """The last receipt day of each cohort position (negative before the oldest)."""
        return np.where(pos <= last, np.minimum(DAYS * pos + DAYS - 1, self.t - self.recent),
                        self.t - self.recent + pos - last)

    def _position(self, day, last):
        """The cohort position in age order that holds receipt day ``day``."""
        return np.where(day <= self.t - self.recent, day // DAYS, last + 1 + day - (self.t - self.recent + 1))

    def _advance(self, t):
        """Move the calendar to day ``t``: daily cohorts older than ``recent`` days join their month's cohort."""
        k = min(t - self.t, self.recent)
        if k > 0:
            day = self.t - self.recent + 1 + np.arange(k)            # the receipt days of the cohorts that leave
            col = self.months + day % self.recent
            touched, which = np.unique(np.clip(day, 0, None) // DAYS, return_inverse=True)
            onehot = (which.reshape(-1)[:, None] == np.arange(touched.size)[None, :]).astype(float)
            leaving = self.amt[col]
            self.amt[touched] += np.einsum("km,kcn->mcn", onehot, leaving)
            self.when[touched] += np.einsum("km,kcn->mcn", onehot * day[:, None], leaving)
            self.amt[col] = 0.0
        self.t = max(self.t, t)

    def step(self, t, inflow, spend, removal, scale=None):
        """One day's update from each person's day totals (see the class): inflow dated ``t``, then spending and
        removal by each convention, then the pro rata ``scale``."""
        self._advance(t)
        got = np.flatnonzero(inflow > 0)
        self.amt[self.months + t % self.recent][:, got] += inflow[got]
        self.edge[0, got] = np.minimum(self.edge[0, got], t)
        self.edge[1, got] = t
        out = spend + removal
        rows = np.flatnonzero(out > 0)
        if rows.size:
            self._consume(rows, out[rows], spend[rows] / out[rows])
        if scale is not None and np.any(scale > 0):
            left = self.amt.sum(axis=0)
            keep = np.clip(1 - np.divide(scale, left, out=np.ones_like(left), where=left > 0), 0.0, 1.0)
            self.amt *= keep
            self.when *= keep

    def _consume(self, rows, out, share):
        """Take ``out`` from each person in ``rows`` under both conventions at once (a line is a convention and a
        person: line c x n + i, first in first out then last in first out), with cumulative sums across the cohort
        axis, and record the spent part (``share`` of each cohort taken).

        For speed the cumulative sum runs over a few cohorts from each line's ``edge`` (all cohorts before it in the
        convention's order are empty): first the edge cohort alone, then ``COIN_WINDOW`` cohorts for the lines whose
        edge cohort holds less than the day's outflow, then three times as many, then every cohort for the lines whose
        windows hold less. The result is the same as over every cohort to rounding, not bit for bit (checked in the
        tests): a window admits a line by the sum of its cohorts and spends by their running total, which can differ
        in the last place."""
        last = self._last_month()
        size = last + 1 + self.recent
        day = dict(lines=np.concatenate([rows, rows + self.n]), lifo=np.repeat([False, True], rows.size),
                   out=np.tile(out, 2), share=np.tile(share, 2), last=last, size=size, pieces=[])
        day["at"] = self._position(self.edge.reshape(-1)[day["lines"]], last)
        # Each cohort position's column, first and last receipt day, for positions -1 to size (index position + 1):
        # looked up instead of recomputed for every line (the same integers; a speed device).
        span = np.arange(-1, size + 1)
        day["column"], day["first"], day["final"] = (self._column(span, last), self._first_day(span, last),
                                                     self._last_day(span, last))
        sel = self._edge_cohort(day)
        sel = self._tier(COIN_WINDOW, sel, day) if sel.size else sel
        sel = self._tier(3 * COIN_WINDOW, sel, day) if sel.size else sel
        if sel.size:
            self._tier(size, sel, day)
        self._record(*map(np.concatenate, zip(*day["pieces"])))

    def _edge_cohort(self, day):
        """The first tier: the lines whose edge cohort alone holds the day's outflow take it all there (the same
        arithmetic as ``_take`` over one cohort); returns the indices of the other lines."""
        lines, lifo, out, at, last = day["lines"], day["lifo"], day["out"], day["at"], day["last"]
        column, first, final = day["column"], day["first"], day["final"]
        pos = np.clip(at, 0, day["size"] - 1)
        flat = column[pos + 1] * (2 * self.n) + lines
        win = np.take(self.amt.reshape(-1), flat)
        fits = np.flatnonzero(win >= out)
        lines, lifo, out, pos, flat, win = lines[fits], lifo[fits], out[fits], pos[fits], flat[fits], win[fits]
        left = win - out
        self.amt.reshape(-1)[flat] = left
        emptied = left <= 0
        after = np.where(lifo, final[pos], first[pos + 2])
        edge = self.edge.reshape(-1)
        edge[lines[emptied]] = after[emptied]
        merged = pos <= last                                  # a monthly cohort: its position is its column
        when = self.when.reshape(self.months, 2 * self.n)
        mean = np.divide(when[np.where(merged, pos, 0), lines], win, out=np.zeros(lines.size), where=merged)
        np.subtract.at(when, (pos[merged], lines[merged]), (out * mean)[merged])
        tau = np.maximum(self.t - np.where(merged, mean, first[pos + 1]), 1.0)
        day["pieces"].append((lines, out * day["share"][fits], tau))
        rest = np.ones(day["lines"].size, bool)
        rest[fits] = False
        return np.flatnonzero(rest)

    def _tier(self, width, sel, day):
        """Take the day's outflow of lines ``sel`` (indices into ``day``) over ``width`` cohorts from their edge, for
        those whose cohorts there hold it all (every line when ``width`` covers every cohort); returns the others."""
        size, last = day["size"], day["last"]
        width = min(width, size)
        lines, lifo, out, share = (day[key][sel] for key in ("lines", "lifo", "out", "share"))
        if width == size:
            pos = np.where(lifo[:, None], np.arange(size)[::-1], np.arange(size))
        else:
            at = day["at"][sel]
            start = np.where(lifo, np.clip(at, width - 1, size - 1), np.clip(at, 0, size - width))
            pos = start[:, None] + np.where(lifo, -1, 1)[:, None] * np.arange(width)
        flat, win = self._window(lines, pos, day)
        fits = (win.sum(axis=1) >= out) | (width == size)
        if fits.all():
            day["pieces"].append(self._take(lines, lifo, out, share, pos, flat, win, day))
            return sel[:0]
        day["pieces"].append(self._take(lines[fits], lifo[fits], out[fits], share[fits], pos[fits], flat[fits],
                                        win[fits], day))
        return sel[~fits]

    def _window(self, lines, pos, day):
        """The flat index into the cohorts of each line's cohort positions ``pos``, and their amounts."""
        flat = day["column"][pos + 1] * (2 * self.n) + lines[:, None]
        return flat, np.take(self.amt.reshape(-1), flat)

    def _take(self, lines, lifo, out, share, pos, flat, win, day):
        """Take ``out`` from each line over its cohort positions ``pos`` (one row each, in the order they are spent,
        at ``flat`` holding ``win``), move its ``edge`` to the first cohort left, and return each spent piece's line,
        value and holding time in days (at least 1)."""
        when = self.when.reshape(self.months, 2 * self.n)
        ahead = np.cumsum(win, axis=1) - win
        take = np.minimum(np.maximum(out[:, None] - ahead, 0.0), win)
        left = win - take
        self.amt.reshape(-1)[flat] = left
        kept = left > 0
        first = np.argmax(kept, axis=1)
        edge_pos = np.where(kept.any(axis=1), pos[np.arange(lines.size), first], pos[:, -1] + np.where(lifo, -1, 1))
        self.edge.reshape(-1)[lines] = np.where(lifo, day["final"][edge_pos + 1], day["first"][edge_pos + 1])
        i, j = np.nonzero(take > 0)
        p, piece = pos[i, j], take[i, j]
        merged = p <= day["last"]                           # a monthly cohort: its position is its column
        mean = np.divide(when[np.where(merged, p, 0), lines[i]], win[i, j], out=np.zeros(i.size), where=merged)
        np.subtract.at(when, (p[merged], lines[i[merged]]), (piece * mean)[merged])
        tau = np.maximum(self.t - np.where(merged, mean, day["first"][p + 1]), 1.0)
        return lines[i], piece * share[i], tau

    def _record(self, line, w, tau):
        """Add the day's spent pieces (line, value, holding time) to the records."""
        t = self.t
        year = (t - self.launch) // (12 * DAYS)
        if t < self.launch or year >= self.years:
            return
        n, rec, bins = 2 * self.n, self.rec, COIN_EDGES.size
        sums = np.bincount(np.concatenate([line, line + n, line + 2 * n]),
                           weights=np.concatenate([w, w / tau, w * tau]), minlength=3 * n).reshape(3, 2, self.n)
        rec["spent"][:, year] += sums[0]
        rec["inverse"][:, year] += sums[1]
        rec["spent_tau"][:, year] += sums[2]
        tally = np.bincount(line * bins + np.searchsorted(COIN_EDGES, tau, side="right") - 1, weights=w,
                            minlength=n * bins)
        rec["histogram"][:, year] += tally.reshape(2, self.n, bins)
        # A spell inside this year adds its whole value to the year's ``held``; a spell that began before the year
        # (or before launch) is split by its days in each year, the days before launch left out.
        start = self.launch + 12 * DAYS * np.arange(self.years)
        rec["held"][:, year] += sums[0]
        cross = t + 1 - tau < start[year]
        if cross.any():
            line, w, tau = line[cross], w[cross], tau[cross]
            overlap = np.maximum(np.minimum(t + 1, start + 12 * DAYS)[None, :]
                                 - np.maximum(t + 1 - tau[:, None], start), 0.0)
            overlap[:, year] -= tau                                   # the whole value was added above
            # The index of (convention, year, person) in ``held``: line // persons is the convention.
            cell = ((line // self.n)[:, None] * self.years + np.arange(self.years)) * self.n + (line % self.n)[:, None]
            rec["held"] += np.bincount(cell.ravel(), weights=(overlap * (w / tau)[:, None]).ravel(),
                                       minlength=n * self.years).reshape(2, self.years, self.n)

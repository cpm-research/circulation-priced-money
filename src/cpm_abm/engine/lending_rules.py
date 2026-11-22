"""Pure lending rules.

The buffer choice: each person's own completed month replayed from each candidate buffer and the cheapest kept,
which the dealing calls for the month's buffers and the close for the experience replays. And the most the pool
lends a payer so that its receipts repay it: without a card, with earned-wage access, with a card's cash line,
and for a card statement's unpaid part.
"""
import numpy as np

from cpm_abm.engine.constants import BUFFER_MULTIPLES, BUFFER_REVIEW_STREAM, DAYS, EPS


def _rises(x, out):
    """Each day's rise of ``x`` over the day before (the first day's over zero), floored at zero, into ``out``: the
    values of ``np.maximum(np.diff(x, axis=2, prepend=0.0), 0.0)``, without its copies."""
    np.subtract(x[..., :1], 0.0, out=out[..., :1])
    np.subtract(x[..., 1:], x[..., :-1], out=out[..., 1:])
    return np.maximum(out, 0.0, out=out)


def replay_cost(flows, buffers, credit_rate, hold_rate, fail_cost=None, reserve=None, draw_rate=None, fail_cap=None,
                fail_month=None, advance=None, advance_rate=None, card_room=None, card_rate=None, card_floor=None,
                card_fee=None):
    """Own completed month replayed from each candidate buffer.

    Cost is holding the buffer, credit interest on the deficit path, the
    expected failure cost of each new shortfall (fail_cost per unit, the
    unfunded share times the failure fee per unit, at most ``fail_cap`` a
    day and, with ``fail_month``, at most that over the month: the monthly
    cap of fees, decided 3 Nov). Demurrage is in P's yield, which
    ``hold_rate`` nets (decided 5 Nov; the charge on the idle part of
    the buffer it replaced is gone). Same-day savings
    (decided 30 Oct): a shortfall first draws on ``reserve`` (n, k), the
    savings above each buffer, giving up ``draw_rate`` on what is drawn
    (savings earn on the month-end balance), and only the rest needs credit
    or fails. Earned-wage access (decided 3 Nov): with ``advance`` (n,
    DAYS), each day's room, the shortfall savings leave is advanced up to
    that room at ``advance_rate`` per unit drawn, and only the rest fails;
    the credit term still reads the whole shortfall. Card limits (decided
    14 Nov 2026): with ``card_room`` (n, DAYS), each day's room on a holder's
    cash line, the shortfall savings leave goes first to the cash line up to
    that room, each rise of what it takes a new advance paying the greater of
    ``card_floor`` and ``card_fee`` per unit, and the credit term gives back
    ``card_rate``, the cash line's part of ``credit_rate``, on the rest above
    the room, which earned-wage access and failure then meet. flows is (n,
    DAYS) own net trade cash flow; buffers is (n, k). Rates are per month.
    """
    # Three (n, k, days) work arrays, every step written in place (a speed and memory device: the same element-wise
    # operations on the same operands, and every sum over the same contiguous last axis).
    shape = buffers.shape + (np.shape(flows)[1],)
    shortfall, work, fresh = np.empty(shape), np.empty(shape), np.empty(shape)
    np.add(buffers[:, :, None], np.cumsum(flows, axis=1)[:, None, :], out=shortfall)   # the path
    np.negative(shortfall, out=shortfall)
    np.maximum(shortfall, 0.0, out=shortfall)
    drawn = np.zeros(buffers.shape)
    if reserve is not None:
        # Savings drawn stay out until the month's dealing, so the month's draws add up to the deepest covered point.
        np.minimum(shortfall, reserve[:, :, None], out=work)                             # covered
        np.subtract(shortfall, work, out=shortfall)
        drawn = work.max(axis=2)
    deficit = shortfall.sum(axis=2) / DAYS
    if card_room is not None:
        # The cash line takes the shortfall up to each day's room (14 Nov 2026), at the fee on each rise of what it
        # takes; what is above the room is left for earned-wage access and failure below, and owes no cash APR.
        np.minimum(shortfall, card_room[:, None, :], out=work)                       # the cash line takes this
        _rises(work, fresh)
        charged = fresh > EPS
        np.multiply(card_fee[:, None, None], fresh, out=fresh)
        np.maximum(fresh, card_floor[:, None, None], out=fresh)
        card_fees = np.multiply(fresh, charged, out=fresh).sum(axis=2)
        np.subtract(shortfall, work, out=shortfall)                                  # the rest, above the room
        above = shortfall.sum(axis=2) / DAYS
    if advance is None:
        _rises(shortfall, fresh)
    else:
        # The advance pays what savings leave, up to the day's room; each rise of what it pays is a new advance, paying
        # its fee, and only the rest of a new shortfall fails. The room is half of the wages earned and still unpaid,
        # gross of the month's advances, and the fee is priced per unit drawn:
        # a reading of the rule (4 Nov).
        np.minimum(shortfall, advance[:, None, :], out=work)                             # lent
        taken = _rises(work, fresh).sum(axis=2)
        np.subtract(shortfall, work, out=work)
        _rises(work, fresh)
    fail_cost = np.zeros(len(flows)) if fail_cost is None else fail_cost
    failed = np.multiply(fail_cost[:, None, None], fresh, out=fresh)
    if fail_cap is not None:
        failed = np.minimum(failed, fail_cap, out=failed) if np.ndim(fail_cap) == 0 else np.minimum(failed, fail_cap)
    failed = failed.sum(axis=2)
    if fail_month is not None:
        failed = np.minimum(failed, fail_month)   # failures past the month's cap cost nothing
    draw_rate = np.zeros(len(flows)) if draw_rate is None else draw_rate
    cost = hold_rate[:, None] * buffers + credit_rate[:, None] * deficit + failed + draw_rate[:, None] * drawn
    cost = cost if advance is None else cost + advance_rate[:, None] * taken
    return cost if card_room is None else cost - card_rate[:, None] * above + card_fees


def choose_buffer(flows, spending, wealth, credit_rate, hold_rate, fail_cost=None, draw_rate=None, drawable=None,
                  fail_cap=None, fail_month=None, advance=None, advance_rate=None, card_room=None, card_rate=None,
                  card_floor=None, card_fee=None):
    """Buffer replay: each person's cheapest buffer among declared multiples of own spending; ties go to less.

    Experiential, not optimising: the person replays its own last month of
    cash flows from each candidate buffer and keeps the one that would have
    cost least. Candidates never exceed the money it actually has. With
    ``draw_rate`` (same-day savings), the money above a candidate that a
    shortfall can draw on the same day (up to ``drawable``, else all of
    ``wealth``) counts as savings at that rate. A day's failures cost at most
    ``fail_cap``, and a month's at most ``fail_month`` when given. With
    ``advance``, each day's earned-wage room, the rest of a shortfall is
    advanced at ``advance_rate`` per unit before it fails (3 Nov). With
    ``card_room``, a holder's cash line takes it first, up to each day's room
    (14 Nov 2026, ``replay_cost``).
    """
    candidates = np.minimum(BUFFER_MULTIPLES[None, :] * spending[:, None], np.maximum(wealth, 0.0)[:, None])
    base = wealth if drawable is None else drawable
    reserve = None if draw_rate is None else np.maximum(np.maximum(base, 0.0)[:, None] - candidates, 0.0)
    cost = replay_cost(flows, candidates, credit_rate, hold_rate, fail_cost, reserve, draw_rate, fail_cap, fail_month,
                       advance, advance_rate, card_room, card_rate, card_floor, card_fee)
    pick = np.argmin(cost + 1e-15 * np.arange(cost.shape[1])[None, :], axis=1)
    rows = np.arange(len(spending))
    return candidates[rows, pick], cost[rows, pick]


def reviewed_buffer(chosen, kept, economy, month):
    """The buffer each person holds after this month's choice under the buffer review share alpha
    (``Economy.buffer_review``, a robustness switch): the one just chosen where the person's review draw is below
    alpha, last month's otherwise. With alpha 1, the base, everyone takes its choice and no draw is made; below 1 the
    draws come from a stream of their own for the month, so no other stream moves. Hand case: alpha 0.5 and draws 0.3
    and 0.7, the first re-chooses and the second keeps its buffer."""
    if economy.buffer_review >= 1:
        return chosen
    draw = np.random.default_rng(np.random.SeedSequence([economy.seed, BUFFER_REVIEW_STREAM, month])).random(chosen.size)
    return review(chosen, kept, draw, economy.buffer_review)


def review(chosen, kept, draw, alpha):
    """The chosen buffer where ``draw`` is below ``alpha``, the kept one elsewhere."""
    return np.where(draw < alpha, chosen, kept)


def limit_with_fee(short, spare, f_pool, unit, cap):
    """The most the pool lends a payer without a card, so that the receipts repay it however capacity rations it.

    What the pool does not lend fails and leaves a fee debt ranked ahead of
    the pool: ``unit`` per failed unit, at most ``cap`` (one fee a day). The
    debt the receipts must cover, the draw at ``f_pool`` per unit plus that
    fee, rises with the draw while the failed rest is large enough for the
    cap to bind, and then changes by ``f_pool - unit`` per unit drawn. The
    pool lends the largest draw whose debt, and the debt of every smaller
    draw, stays within ``spare``.
    """
    reach = np.where(unit > 0, cap / np.where(unit > 0, unit, 1.0), np.inf)  # the failed amount that reaches the cap
    capped = np.maximum(short - reach, 0.0)                                   # draws below this leave the cap binding
    rising = f_pool > unit
    rest = np.where(rising, (spare - unit * short) / np.where(rising, f_pool - unit, 1.0), np.inf)
    return np.where(np.minimum(unit * short, cap) > spare, 0.0,
                    np.where((capped > 0) & (capped * f_pool + cap > spare), (spare - cap) / f_pool,
                             np.minimum(rest, short)))


def limit_with_advance(short, spare, f_pool, unit, cap, room, f_advance):
    """The most the pool lends a payer without a card whose earned-wage access covers the rest up to ``room``.

    The receipts must repay the draw at ``f_pool``, the advance and its fee at
    ``f_advance`` (taken from the wage first, decided 3 Nov) and the fee
    debt on what still fails, ``unit`` per failed unit and at most ``cap``,
    for this draw and every smaller one, since capacity may ration it. The
    debt D(x) = x f_pool + f_advance min(short - x, room) + min(unit max(short
    - x - room, 0), cap) is piecewise linear: slope f_pool while the fee is
    at its cap, f_pool - unit while part of the rest fails below it, and
    f_pool - f_advance once the advance covers the whole rest. The pool lends
    nothing if D(0) exceeds ``spare``, else up to the first crossing of a
    rising piece, else the whole shortfall. With no room it is
    ``limit_with_fee``.
    """
    upper = np.maximum(short - room, 0.0)                                     # draws above this leave no failure
    reach = np.where(unit > 0, cap / np.where(unit > 0, unit, 1.0), np.inf)  # the failed amount that reaches the cap
    lower = np.maximum(upper - reach, 0.0)                                    # draws below this leave the cap binding
    debt = lambda x: (x * f_pool + f_advance * np.minimum(short - x, room)
                      + np.minimum(unit * np.maximum(short - x - room, 0.0), cap))
    # The debt at each piece's ends, once each: zero, lower, upper and the whole shortfall.
    zero = np.zeros_like(short)
    at = dict(zip(("zero", "lower", "upper", "short"), map(debt, (zero, lower, upper, short))))
    pieces = ((zero, "zero", "lower", f_pool), (lower, "lower", "upper", f_pool - unit),
              (upper, "upper", "short", f_pool - f_advance))
    crossing = lambda start, begin, slope: start + (spare - at[begin]) / np.where(slope > 0, slope, 1.0)
    return np.select([at["zero"] > spare, *(at[stop] > spare for _, _, stop, _ in pieces)],
                     [0.0, *(crossing(start, begin, slope) for start, begin, _, slope in pieces)], short)


def limit_with_card(short, spare, f_pool, unit, cap, room, f_cash, floor, rate, f_fee, ewa_room, f_ewa):
    """The most the pool lends a card holder whose cash line covers the rest up to ``room`` (decided 14 Nov 2026:
    the pool's test for holders is partial, the card room in place of the advance).

    What the pool does not lend goes to the cash line up to ``room``, at ``f_cash`` per unit and a fee, the greater of
    ``floor`` and ``rate`` per unit, owed on the card's purchase balance at ``f_fee``; then to earned-wage access up to
    ``ewa_room`` at ``f_ewa``; and what is left fails, with its fee debt of ``unit`` per failed unit, at most ``cap``.
    All of it is repaid before the pool, so the receipts must repay D(x) = x f_pool + A(min(short - x, room)) + f_ewa
    min(max(short - x - room, 0), ewa_room) + min(unit max(short - x - room - ewa_room, 0), cap), with A(a) = a f_cash
    + f_fee max(floor, rate a) for an advance, for this draw and every smaller one, since capacity may ration it. D is
    piecewise linear, five pieces: slope f_pool while the failure fee is at its cap, f_pool - unit while part of the
    rest fails below it, f_pool - f_ewa while earned-wage access takes the rest, f_pool - f_cash - f_fee rate while the
    advance's fee is its rate and f_pool - f_cash once the fee is the floor; it drops by the floor where the advance
    falls to nothing. The pool lends nothing if D(0) exceeds ``spare``, else up to the first crossing of a rising
    piece, else the whole shortfall. With a room covering the whole shortfall and no fee it lends the whole shortfall
    or nothing, the holder's test before card limits.
    """
    fee = lambda a: np.where(a > EPS, f_fee * np.maximum(floor, rate * a), 0.0)
    debt = lambda x: (x * f_pool + (np.minimum(short - x, room) * f_cash + fee(np.minimum(short - x, room)))
                      + f_ewa * np.minimum(np.maximum(short - x - room, 0.0), ewa_room)
                      + np.minimum(unit * np.maximum(short - x - room - ewa_room, 0.0), cap))
    reach = np.where(unit > 0, cap / np.where(unit > 0, unit, 1.0), np.inf)  # the failed amount that reaches the cap
    knee = np.where(rate > 0, floor / np.where(rate > 0, rate, 1.0), np.where(floor > 0, np.inf, 0.0))   # fee = floor
    # The pieces' ends in the draw x, in order: the fee reaches its cap, nothing fails, earned-wage access takes
    # nothing, the advance's fee becomes its floor, and the whole shortfall.
    capped = np.maximum(short - room - ewa_room - reach, 0.0)
    failing = np.maximum(short - room - ewa_room, 0.0)
    advancing = np.maximum(short - room, 0.0)
    flat = np.maximum(short - np.minimum(knee, room), 0.0)
    ends = (np.zeros_like(short), capped, failing, advancing, flat)
    at = list(map(debt, ends))
    # The left end of the last piece: the advance's floor is still owed just short of the whole shortfall.
    at.append(short * f_pool + np.where(room > EPS, f_fee * floor, 0.0))
    slopes = (f_pool, f_pool - unit, f_pool - f_ewa, f_pool - f_cash - f_fee * rate, f_pool - f_cash)
    crossing = lambda k: ends[k] + (spare - at[k]) / np.where(slopes[k] > 0, slopes[k], 1.0)
    return np.select([at[0] > spare, *(at[k + 1] > spare for k in range(5))],
                     [0.0, *(crossing(k) for k in range(5))], short)


def limit_with_revolve(short, spare, f_pool, f_card, unmet, fee):
    """The most the pool pays of a card statement's unpaid part (decided 14 Nov 2026: the pool's statement test is
    the same piecewise limit). What it does not pay revolves on the card at ``f_card``, repaid first, and while the
    payment leaves ``unmet`` of the minimum unpaid the late fee ``fee`` is owed too, so the receipts must repay D(x) =
    x f_pool + (short - x) f_card + fee [x < unmet] for this draw and every smaller one, since capacity may ration it.
    With the pool no dearer than the card, D falls, so it pays all of it or nothing, the late fee counted where nothing
    paid would leave the minimum unmet; dearer, it pays up to D's first crossing of ``spare``. A draw up to the minimum
    alone would leave the pool unrepaid wherever capacity rationed it below the minimum. With no late fee it is the
    test before card limits: all of it where the receipts repay all of it at card terms."""
    owed = np.where(unmet > EPS, fee, 0.0)
    start = short * f_card + owed
    slope = f_pool - f_card
    rising = slope > 0
    step = lambda base: (spare - base) / np.where(rising, slope, 1.0)
    upper = np.clip(unmet, 0.0, short)
    first, second = step(start), upper + step(start + slope * upper - owed)
    return np.select([start > spare, rising & (first < upper), rising & (second < short)], [0.0, first, second], short)

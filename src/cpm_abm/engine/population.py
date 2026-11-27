"""Who the people are, the same in every arm for one seed.

Wealth, spending, income, billing cycles and dates, wages and jobs, layoff risk and spells, card ownership, lines
and scores, and the outside rates term requests are offered at.
"""
import numpy as np
from scipy.stats import norm

from cpm_abm.engine.constants import (BUSINESS_APR, CARD_APR, CARD_BAND_SHARES, CARD_BANDS, CARD_LINE, CARD_LINE_SCORES,
                                      CARD_MAXED, CARD_OWNERSHIP, CARD_REVOLVING, CARD_TIER_SCORES,
                                      COMPLETED_SPELL_MEDIAN_DAYS, COMPLETED_SPELL_SIGMA, CYCLE_DAYS, DAYS,
                                      DISTRESS_DIAL_MAX, DISTRESS_KEEP_STREAM, DISTRESS_START_STREAM,
                                      FICO_CUMULATIVE, FICO_EDGES, HOUSEHOLDS_BY_EDUCATION, INCOME_BRACKETS,
                                      LABOUR_SHARE, MONTH_USD, PAY_DAYS, PAY_SHARES, PERSONAL_APR, PERSONAL_SCORES,
                                      SCORE_INCOME_CORRELATION, SPELL_MEDIAN_DAYS, SPELL_SIGMA, SURVEY_RANKS,
                                      SURVEY_SAVINGS, UNEMPLOYMENT_BY_EDUCATION, VEHICLE_APR, VEHICLE_TIER_SCORES,
                                      WAGE_LINK_STREAM)


def billing_cycle_shares():
    """Share of people on each billing cycle (1, 7, 15, 30, 60 days).

    Labour income (58.3%) follows BLS pay frequencies (weekly 27%, biweekly
    and semimonthly 62.8%, monthly 10.3%); business receipts (41.7%) are half
    daily card settlement, a quarter monthly and a quarter 60-day invoices.
    """
    labour, business = LABOUR_SHARE, 1 - LABOUR_SHARE
    pay = np.array([27.0, 43.0 + 19.8, 10.3])
    pay = pay / pay.sum()
    return np.array([business / 2, labour * pay[0], labour * pay[1], labour * pay[2] + business / 4, business / 4])


def pareto_stratum_means(n, alpha):
    """Mean of a Pareto(alpha, minimum 1) distribution within each of n equal quantile bands.

    Using band means instead of random draws gives the same wealth vector for
    every seed, so seeds vary only the economy's events, never the population.
    """
    if alpha <= 1.0:
        raise ValueError("Stratum means need a finite mean: alpha must exceed 1")
    lower = np.arange(n) / n
    upper = lower + 1.0 / n
    k = 1.0 - 1.0 / alpha
    return ((1.0 - lower) ** k - (1.0 - upper) ** k) / (k * (upper - lower))


def rank_share(values):
    """Each value's rank as a share in (0, 1), ties broken by position."""
    return (np.argsort(np.argsort(values, kind="stable"), kind="stable") + 0.5) / values.size


def income_bracket(spending):
    """Each person's Census income bracket (0 under $25,000 to 3 at $100,000 and over), with spending rank as income."""
    return np.searchsorted(np.cumsum(INCOME_BRACKETS)[:-1], rank_share(spending), side="right")


def layoff_weight():
    """Relative layoff risk of each income bracket: its householders' education mix times BLS unemployment by education.

    Normalised to the average household: 1.13, 1.09, 1.03 and 0.92 from the lowest bracket up.
    """
    households = HOUSEHOLDS_BY_EDUCATION.sum(axis=0)
    risk = UNEMPLOYMENT_BY_EDUCATION @ (HOUSEHOLDS_BY_EDUCATION / households)
    return risk / (risk @ households / households.sum())


def spell_law(economy):
    """The spell law in force, (median days, sigma) of log-normal completed lengths: consistent with the BLS figures for
    spells in progress, or with ``completed_spells`` off those figures read as completed lengths."""
    if economy.completed_spells:
        return COMPLETED_SPELL_MEDIAN_DAYS, COMPLETED_SPELL_SIGMA
    return SPELL_MEDIAN_DAYS, SPELL_SIGMA


def draw_spells(rng, rate, eligible, start_day, median, sigma, normal=None):
    """One month's layoffs: each eligible job is laid off with its monthly probability ``rate``, from a uniform day
    of the month that starts on ``start_day``, for a log-normal number of days (``median``, ``sigma``; at least one).
    Three draws over all jobs, in this order: the layoff, the day and the length. Returns the jobs laid off and each
    job's spell start and end day had it been laid off. Given ``normal``, each job's monthly probability without
    distress (the harsh stress), it also returns the extra layoffs, those whose draw lies at or above ``normal``,
    which a month without distress would not have laid off; no other number is drawn.

    Example: at a rate of 0.03 and a normal 0.01, draws of 0.005, 0.01 and 0.02 are laid off, the last two as extra
    layoffs, and 0.03 is not laid off."""
    draw, day, z = rng.random(rate.size), rng.integers(0, DAYS, size=rate.size), rng.standard_normal(rate.size)
    laid_off = (draw < rate) & eligible
    length = np.maximum(np.rint(median * np.exp(sigma * z)), 1).astype(int)
    spells = laid_off, start_day + day, start_day + day + length
    return spells if normal is None else (*spells, laid_off & (draw >= normal))


def distress_years(economy, dial=None):
    """The months after launch at which the random distress years start (``Economy.distress_dates`` "random"), in
    order, at the dial ``dial`` (by default ``economy.distress_expected``), the expected number of years in a run
    before overlaps are refused.

    The years are first drawn at the highest dial, DISTRESS_DIAL_MAX (4): in each month after launch not already
    inside a distress year, one starts with chance 4 over the number of months after launch, on one uniform draw a
    month from a stream of its own (DISTRESS_START_STREAM), and lasts ``distress_length`` months, so years never
    overlap and the realised mean is a little below the dial. Each year so drawn is then kept with probability dial / 4
    on one further uniform draw a year from a second stream (DISTRESS_KEEP_STREAM), so a lower dial's years are among a
    higher one's. Only the seed, the run length and ``distress_length`` enter, so every arm and every distress level
    of a seed meets the same dates. A year that starts late may run past the end of the run.

    Example: 48 months after launch, years of 12 months, draws below 4 / 48 in months 3, 9 and 20 at the dial of 4:
    the year from month 3 covers months 3 to 14, so month 9 starts none, and a second year starts in month 20. With
    keeping draws of 0.3 and 0.8, a dial of 2 (keep below 0.5) keeps the year from month 3 only, a dial of 4 both."""
    dial = economy.distress_expected if dial is None else dial
    months, length = economy.months, economy.distress_length
    draw = np.random.default_rng(np.random.SeedSequence([economy.seed, DISTRESS_START_STREAM])).random(months)
    starts, free = [], 0
    # A loop over the few candidate months of the run, not over people: whether a month starts a year depends on the
    # years already started.
    for month in np.flatnonzero(draw < DISTRESS_DIAL_MAX / months):
        if month >= free:
            starts.append(int(month))
            free = month + length
    starts = np.array(starts, int)
    keep = np.random.default_rng(np.random.SeedSequence([economy.seed, DISTRESS_KEEP_STREAM])).random(starts.size)
    return starts[keep < dial / DISTRESS_DIAL_MAX]


def distress_calendar(economy):
    """Which months of the run, burn-in included, lie inside a distress year, one flag a month: under
    ``distress_dates`` "dated" the one year from ``distress_start`` months after launch for ``distress_length`` months
    (months 25 to 36 after launch by default), under "random" the years of ``distress_years``, each cut at the end of
    the run.

    Example: a burn-in of 6, 60 months, a year of 12 from 24 months after launch: months 30 to 41 of the run are
    flagged."""
    total, length = economy.burn_in + economy.months, economy.distress_length
    starts = (np.array([economy.distress_start]) if economy.distress_dates == "dated" else distress_years(economy))
    months = (economy.burn_in + starts[:, None] + np.arange(length)).ravel()
    flagged = np.zeros(total, bool)
    flagged[months[(months >= 0) & (months < total)]] = True
    return flagged


def spell_stock(rng, hazard, median, sigma):
    """The jobs in a spell at month 0, at the steady stock of a monthly layoff probability ``hazard`` per job and
    log-normal spells (``median`` days, ``sigma``), the start of normal job loss.

    A job is in a spell with probability h D / (1 + h D), D the mean length in months (inflow (1 - p) h equals outflow
    p / D). A spell in progress has a length-biased total length L, log-normal at mu + sigma^2, and has run a uniform
    share u of it: it started on day -floor(u L) and ends rint(L) days later, on day 1 at the earliest. Each job's own
    hazard, the length-biased length and the uniform share are a reading of the rule. Three
    draws over all jobs, in this order: in a spell, the length and the share. Returns each job's spell start and end
    day, both 0 for a job not in a spell.
    """
    months = median * np.exp(sigma ** 2 / 2) / DAYS
    inside = rng.random(hazard.size) < hazard * months / (1 + hazard * months)
    length = median * np.exp(sigma ** 2 + sigma * rng.standard_normal(hazard.size))
    start = -np.floor(rng.random(hazard.size) * length).astype(int)
    end = np.maximum(start + np.maximum(np.rint(length), 1).astype(int), 1)
    return np.where(inside, start, 0), np.where(inside, end, 0)


def cards_and_scores(spending, rng):
    """Card ownership by income bracket in exact proportion, and a FICO-scale score by rank copula.

    Income rank (spending as the income proxy) places each person in a
    Census bracket; within each bracket the first round(share x size) people
    in a random order hold a card. A latent score, Gaussian with correlation
    ``SCORE_INCOME_CORRELATION`` (0.3036) with the normal score of income
    rank, so a rank correlation of 0.291, gives a score by the FICO
    distribution, uniform within its bands.
    """
    n = spending.size
    rank = rank_share(spending)
    bracket = income_bracket(spending)
    position = np.empty(n)
    position[rng.permutation(n)] = np.arange(n)
    counts = np.bincount(bracket, minlength=4)
    within = np.argsort(np.argsort(bracket * n + position, kind="stable"), kind="stable")
    first = np.concatenate(([0], np.cumsum(counts)[:-1]))
    holder = within - first[bracket] < np.round(CARD_OWNERSHIP[bracket] * counts[bracket])
    latent = (SCORE_INCOME_CORRELATION * norm.ppf(rank)
              + (1 - SCORE_INCOME_CORRELATION ** 2) ** 0.5 * rng.standard_normal(n))
    score = np.interp(rank_share(latent), FICO_CUMULATIVE, FICO_EDGES)
    return holder, score


def card_tier(score):
    """Each person's CFPB score tier, 0 deep subprime to 5 superprime
    (``CARD_LINE_SCORES``)."""
    return np.searchsorted(CARD_LINE_SCORES, score, side="right")


def card_lines(holder, score, rng):
    """Each holder's line and starting balance, zero for everyone else: the line of its score
    tier (``CARD_LINE``) and, with its tier's chance (``CARD_MAXED``), a balance of 90 to 100% of it, uniform, else a
    share of it in a band below 90% (``CARD_BANDS``, ``CARD_BAND_SHARES``), uniform within the band, times the tier's
    revolving share (``CARD_REVOLVING``). Three draws over all people, in this order: maxed or not, the band and the
    place within it, so the draw is the same whoever holds a card."""
    tier = card_tier(score)
    maxed, band, place = rng.random((3, holder.size))
    band = np.searchsorted(np.cumsum(CARD_BAND_SHARES)[:-1], band, side="right")
    used = np.where(maxed < CARD_MAXED[tier], 0.9 + 0.1 * place,
                    (CARD_BANDS[band] + (CARD_BANDS[band + 1] - CARD_BANDS[band]) * place) * CARD_REVOLVING[tier])
    line = np.where(holder, CARD_LINE[tier], 0.0)
    return line, line * used


def income_source(cycles, rng):
    """Business receipts are daily and 60-day billers plus the business share of monthly billers."""
    monthly_business = ((1 - LABOUR_SHARE) / 4) / billing_cycle_shares()[3]
    business = (cycles == 1) | (cycles == 60)
    monthly = np.flatnonzero(cycles == 30)
    business[rng.permutation(monthly)[:int(round(monthly_business * monthly.size))]] = True
    return business


def term_outside_apr(product, score, used, shift=None):
    """The outside APR of each term request from the borrower's score (vehicle tier, personal, business), plus, when
    outside prices follow r_out, its product's ``shift`` a year (vehicle, personal, business)."""
    vehicle = VEHICLE_APR[used.astype(int), np.searchsorted(VEHICLE_TIER_SCORES, score, side="right")]
    personal = np.interp(score, PERSONAL_SCORES, PERSONAL_APR)
    apr = np.select([product == 0, product == 1], [vehicle, personal], BUSINESS_APR)
    return apr if shift is None else apr + shift[product]


def wage_links_one_each(economy):
    """Who each person pays its wage to under ``Economy.wage_links`` "one_each": a random
    permutation with no fixed point, so every person pays one wage and receives exactly one, and nobody pays itself.

    By default each wage goes to one other person drawn uniformly, so the number of wages a person receives is close to
    Poisson with mean 1 and about 37% of people (1/e) receive none and live on sales alone. Here everybody has a wage
    coming in. Permutations are drawn on a stream of their own (WAGE_LINK_STREAM) until one has no fixed point; each
    has one with chance about 1 - 1/e, so about 2.7 are drawn, and the one kept is uniform over the permutations
    without a fixed point.

    Example, 4 people: the draw (1, 0, 3, 2) is kept, person 0 paying person 1 and 1 paying 0; the draw (0, 2, 3, 1)
    is refused, since person 0 would pay itself."""
    rng = np.random.default_rng(np.random.SeedSequence([economy.seed, WAGE_LINK_STREAM]))
    people = np.arange(economy.n)
    # A loop over the few draws, not over people: whether a draw is kept depends on all of it.
    while True:
        wage_to = rng.permutation(economy.n)
        if not (wage_to == people).any():
            return wage_to


def build_population(economy):
    """Create the population: wealth, spending, billing, wages, cards and scores; the same in every arm for one seed.

    Returns arrays over people: initial liquid wealth, illiquid wealth,
    spending (mean 1), billing cycle and phase, wage recipient, card
    ownership, credit score, card APR, whether income is business
    receipts, the pay period and phase of each person's job (as payer),
    who holds earned-wage access, who holds crypto collateral for M0's
    Comet, and each holder's card line and starting balance. Each of these
    last is drawn on a stream of its own, so no earlier draw moves.
    """
    rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 3101]))
    # Relative wealth from Pareto band means; spending rises with wealth^beta and is normalised to mean 1;
    # wealth is scaled so the median person holds 0.6 months of own spending.
    shape = pareto_stratum_means(economy.n, economy.alpha)
    relative = shape / np.median(shape)
    spending = relative ** economy.beta
    spending = spending / spending.mean()
    wealth = economy.buffer_months * np.median(spending) * relative
    # Starting cushions follow the Fed survey where it is lower: liquid wealth is the lower of
    # this level and the survey's at the same rank; the rest is illiquid wealth (a home, retirement savings) that
    # counts toward net worth for spending but never pays a bill and never changes.
    rank = rank_share(wealth)
    survey = np.where(rank <= SURVEY_RANKS[-1], np.interp(rank, SURVEY_RANKS, SURVEY_SAVINGS) / MONTH_USD, np.inf)
    liquid = np.minimum(wealth, survey)
    # Billing cycles in exact proportion (largest remainders), shuffled; each person gets a random phase.
    exact = billing_cycle_shares() * economy.n
    counts = np.floor(exact).astype(int)
    counts[np.argsort(exact - counts)[::-1][:economy.n - counts.sum()]] += 1
    cycles = rng.permutation(np.repeat(CYCLE_DAYS, counts))
    phases = np.floor(rng.random(economy.n) * cycles).astype(int)
    # A separate random stream keeps the draws above independent of the draws below.
    extra = np.random.default_rng(np.random.SeedSequence([economy.seed, 3102]))
    # Each person's wage contract goes to one other person drawn uniformly. Under ``wage_links`` "one_each" these links
    # are replaced below, but they are still drawn here so that the cards, scores and income sources after them on this
    # stream do not move.
    wage_to = (np.arange(economy.n) + 1 + extra.integers(0, economy.n - 1, size=economy.n)) % economy.n
    holder, score = cards_and_scores(spending, extra)
    card_apr = CARD_APR[np.searchsorted(CARD_TIER_SCORES, score, side="right")]
    business = income_source(cycles, extra)
    # Pay periods: each job (indexed by its payer) gets a BLS pay frequency in exact proportion (largest remainders,
    # as the cycles), shuffled, and a uniform phase within its period, on a stream of its own. Establishment shares
    # are used as job shares, twice a month is every 15 days and pay dates are not aligned to the calendar: a
    # reading of the source.
    pay_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 3103]))
    pay_exact = PAY_SHARES / PAY_SHARES.sum() * economy.n
    pay_counts = np.floor(pay_exact).astype(int)
    pay_counts[np.argsort(pay_exact - pay_counts)[::-1][:economy.n - pay_counts.sum()]] += 1
    pay_days = pay_rng.permutation(np.repeat(PAY_DAYS, pay_counts))
    pay_phase = np.floor(pay_rng.random(economy.n) * pay_days).astype(int)
    # Earned-wage access: held by a share drawn once on a stream of its own, independent of card holding. One order
    # of the wage earners is drawn whatever the share and its first round(share x n) hold access, so a smaller
    # share's holders are among a larger one's. Exactly that many, and wage earners only, since access needs a wage.
    ewa_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 3104]))
    earners = ewa_rng.permutation(np.flatnonzero(np.isin(np.arange(economy.n), wage_to)))
    ewa = np.isin(np.arange(economy.n), earners[:min(int(round(economy.earned_wage_share * economy.n)), earners.size)])
    if economy.wage_links == "one_each":
        # One wage each, drawn after everything above so that no other array moves. Earned-wage access keeps the
        # holders drawn above, among the people who earn a wage under the default links; now that everybody earns
        # one, the same holders are a smaller share of earners (about 7% where they were about 12%).
        wage_to = wage_links_one_each(economy)
    # Crypto collateral holders, M0's only borrowers from Comet: one order of everyone is drawn on a stream of its
    # own whatever the share, and its first round(share x n) hold collateral, so no earlier draw moves and a smaller
    # share's holders are among a larger one's, as for earned-wage access.
    crypto_rng = np.random.default_rng(np.random.SeedSequence([economy.seed, 3105]))
    crypto = np.isin(np.arange(economy.n), crypto_rng.permutation(economy.n)[:int(round(economy.crypto_share
                                                                                         * economy.n))])
    # Card lines and starting balances, on a stream of their own, so no earlier draw moves.
    card_line, card_start = card_lines(holder, score, np.random.default_rng(np.random.SeedSequence([economy.seed,
                                                                                                    3106])))
    return dict(wealth=liquid, illiquid=wealth - liquid, spending=spending, cycles=cycles, phases=phases,
                wage_to=wage_to, holder=holder, score=score, card_apr=card_apr, business=business, pay_days=pay_days,
                pay_phase=pay_phase, ewa=ewa, crypto=crypto, card_line=card_line, card_start=card_start)


def next_billing(cycles, phases, day, strict=False):
    """Each person's first billing date on or after `day` (strictly after it when strict)."""
    start = day + 1 if strict else day
    return start + (phases - start) % cycles


def last_billing(cycles, phases, day):
    """Each person's last billing date on or before `day`."""
    return day - (day - phases) % cycles

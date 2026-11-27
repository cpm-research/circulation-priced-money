"""Core CPM model in the notation of the paper: adoption plus circular-flow liquidity.

The module holds the inputs the population model shares (``Inputs``, ``REVIEW_RATE``) and the earlier analytical
core model: one representative 30-day pay cycle for each arm, with adoption as a share that moves month by month.
The population model (``cpm_abm.economy_abm``) takes its inputs from here, and its adoption rules follow the ones
set out below.

Participation spreads socially and is kept or abandoned on
experience; nobody joins on a computed gain. The overall benefit is
emergent: payments fail when a payer's liquidity need exceeds its buffer and
outside credit is unavailable (precautionary buffers, limited outside credit, idiosyncratic shocks). A
failed payment is missing income for its recipient, so failures propagate.
Fee savings are transfers (they recirculate) and are excluded unless switched on.
Amounts are per agent per month in units of monthly payments (y = 1); fields
marked "declared" are modelling choices.

Arms, each against S0 in the same economy with the same adoption rules:
M1 nominal CPM (the paper's contract), U the uncharged control (M1 with no holding
charge or rebate), M2 purchasing-power CPM (P indexed to J, contract in P
terms) and M0 actual DeFi (pinned Compound III USDC market, no CPM).
Participants in the pool arms decide whether to keep their precautionary
buffer as idle P or release it, by the experienced-cost rule.
"""
from dataclasses import dataclass

import numpy as np

STEPS = 720  # within-cycle time points: hourly in a 30-day cycle
SWEEPS = 60  # fixed-point iterations for the completion rate
ARMS = ("M0", "M1", "U", "M2")
# Experience review rate, a Poisson intensity a month: the monthly speed of technology adjustment k = 0.166 (standard
# error 0.032; Crouzet, Gupta and Mezzanotti, Journal of Political Economy 131(11), 2023, Table 4). The models draw a
# review once a month, so the chance of at least one review in a month is 1 - exp(-0.166) = 0.1530 (``Inputs.upsilon``).
REVIEW_RATE = 0.166


@dataclass(frozen=True)
class Inputs:
    """Baseline values; each comment names its source or declares its status."""

    rho_H: float = 0.0037        # control r_out: US T-bill about 4.5%/yr
    r_ext: float = 0.22 / 12     # outside bridging: card APR about 22%/yr (Fed G.19)
    access: float = 0.7          # share of uncovered needs outside credit will fund (declared; SHED 2024: 37% cannot cover $400 from cash or equivalent)
    penalty: float = 0.05        # late/overdraft cost per unit of failed payment (declared)
    buffer: float = 0.5          # mean idle precautionary buffer in S0, months of payments (declared)
    buffer_yield: float = 0.0007 / 12  # what an idle S0 buffer earns: FDIC national interest-checking rate, 2025
    buffer_at_outside: bool = False    # stress: S0 buffers already earn rho_H (high-yield account)
    savings: float = 0.5         # investable savings beyond the buffer, months of payments (declared)
    shock_prob: float = 0.5      # monthly chance of an unplanned expense (declared)
    shock_size: float = 0.2      # its size, months of payments (declared)
    term: float = 0.5            # months a bridge stays outstanding (declared)
    population: int = 1000       # agents sharing the pool (1,000 for the main results)
    coverage_z: float = 2.33     # pool covers aggregate need at the 99% level (declared)
    f_card: float = 0.017        # card acceptance cost per unit paid (CMSPI 2023)
    rewards: float = 0.0         # rewards returned per unit of card volume (sensitivity)
    merchant_fees: bool = False  # count merchant fee savings in experience (a transfer; off)
    card_share: float = 0.65     # card share of non-housing payments (Fed DCPC 2025)
    housing: float = 0.329       # housing share, due at cycle start (BLS CEX 2023)
    pays: int = 2                # paychecks per cycle (BLS CES Feb 2023: biweekly most common)
    card_due: float = 0.7        # statement due point in the cycle, 21-day due lag (declared)
    alpha: float = 0.002         # provider fee per unit paid, a(q) = alpha q
    o: float = 0.02 / 12         # operating cost per principal-month (2%/yr, Philippon 2015)
    C_fix: float = 5e-5          # fixed pool cost per capita per month (unknown; swept)
    switch_cost: float = 3.5e-6  # leaving threshold: one conversion amortised over a year
    xi0: float = 0.03 / 12       # joining: innovation per month (Sultan, Farley & Lehmann 1990)
    xi1: float = 0.38 / 12       # joining: imitation per month (same source)
    upsilon: float = float(-np.expm1(-REVIEW_RATE))  # monthly chance of a review, 0.1530 (``REVIEW_RATE``)
    noise: float = 1e-4          # spread of experienced outcomes, months of payments (declared)
    pool_cash_return: bool = False  # proposed lever, not in the paper: the pool, not the issuer, earns the reserve return on its idle cash
    arm: str = "M1"              # one of ARMS
    inflation: float = 0.037 / 12  # dJ/J for M2: BLS CPI-U, 12 months to September 2026
    supply_premium: float = 0.0  # M0 supply rate above rho_H; 0 = risk-adjusted. Pinned block: 0.0277/12 (7.27% vs 4.5%)
    borrow_margin: float = 0.01269 / 12  # M0 borrow rate above its supply rate at the pinned block (8.54% vs 7.27%)
    collateral_cover: float = 0.0  # M0: share of a household's uncovered need it can post collateral for (SHED 2023: 7% hold any crypto)
    gas_per_unit: float = 8.0e-5   # M0 payment cost: 65k gas at the pinned base fee per $142 payment


def cycle_profile(A, inputs):
    """Cumulative net flow z(t) in one cycle for each internal share A (rows).

    S0 (A = 0) pays card-eligible spending at the statement due date, inside
    the interest-free grace period; a participant pays its internal share at
    once in P (or USDC) and so gives up that float.
    """
    t = (np.arange(STEPS) + 0.5) / STEPS
    share = np.atleast_1d(np.asarray(A, float))[:, None]
    card = (1 - inputs.housing) * inputs.card_share
    other = (1 - inputs.housing) - card
    income = (np.floor(t * inputs.pays) + 1) / inputs.pays
    return (income - inputs.housing - other * t - card * share * t
            - card * (1 - share) * (t >= inputs.card_due))


def expected_gap(base, inputs):
    """E[(X - b)^+] over the shock and the exponential spread of buffer positions b.

    X = base + shock_size with probability shock_prob, else base. For an
    exponential buffer with mean B, E[(x - b)^+] = x - B (1 - exp(-x/B)).
    """
    def h(x):
        """Expected uncovered part of need x across buffer positions."""
        return x - inputs.buffer * (1 - np.exp(-x / inputs.buffer))
    return (1 - inputs.shock_prob) * h(base) + inputs.shock_prob * h(base + inputs.shock_size)


def _frame(inputs, rho, A):
    """Grid columns, cycle quantities and the S0 idle-buffer yield shared by every arm."""
    rho_col = np.atleast_1d(np.asarray(rho, float))[:, None]
    share = np.atleast_1d(np.asarray(A, float))[None, :]
    z = cycle_profile(share[0], inputs)
    shape = rho_col.shape[:1] + share.shape[1:]
    return dict(rho=rho_col, share=share, shape=shape, lost=np.maximum(0.0, -z).mean(axis=1)[None, :],
                float_p=np.maximum(z, 0.0).mean(axis=1)[None, :], card=(1 - inputs.housing) * inputs.card_share,
                shock_mean=inputs.shock_prob * inputs.shock_size,
                idle=rho_col + np.zeros(shape) if inputs.buffer_at_outside else inputs.buffer_yield + np.zeros(shape))


def _solve_phi(state, shape):
    """Damped fixed-point iteration for the completion rate phi."""
    phi = np.ones(shape)
    for _ in range(SWEEPS):
        phi = 0.5 * phi + 0.5 * state(phi)["phi_next"]
    return phi


def _pool(inputs, rho, A, keep):
    """M1, U or M2 with participants' buffers released into the pool (keep=False) or held as idle P.

    This closed form is the paper's analytical contract, which the economy does not run (its contract is the one in
    the assumption register); nothing in the engine (``economy_abm``) calls it. It is kept for the core model's own
    tests (tests/test_core_model.py) only.

    The contract runs in P terms: in M2 the comparable return is rho_H - dJ/J
    and every nominal amount adds back dJ/J (the paper's real-share and loan-cost
    equations).
    """
    f = _frame(inputs, rho, A)
    share, rho_col = f["share"], f["rho"]
    indexed, charged = inputs.arm == "M2", inputs.arm != "U"
    pi = inputs.inflation if indexed else 0.0
    rho_p = rho_col - pi
    pooled = np.sqrt(inputs.shock_prob * (1 - inputs.shock_prob) * inputs.shock_size ** 2
                     / np.maximum(share * inputs.population, 1.0))

    def state(phi):
        """Pool, coverage and failures implied by a completion rate."""
        base_e, base_p = 1 - phi, 1 - phi + f["lost"]
        need_p = base_p + f["shock_mean"]
        gap_p = expected_gap(base_p, inputs)
        bridged = gap_p if keep else need_p
        m = inputs.alpha * f["card"] * share ** 2 * phi - inputs.C_fix
        ready = (m > 0) & (share > 0)
        demand = inputs.term * share * bridged
        supply = share * (inputs.savings + (0.0 if keep else inputs.buffer))
        open_ended = inputs.pool_cash_return | (rho_p <= 0)
        standby = np.where(open_ended, np.inf, np.maximum(m, 0.0) / np.where(rho_p > 0, rho_p, 1.0))
        N = np.where(ready, np.minimum(supply, demand + standby), 0.0)
        required = inputs.term * share * (bridged + inputs.coverage_z * pooled)
        sigma = np.where(ready, np.minimum(1.0, np.divide(N, required, out=np.zeros(N.shape), where=required > 0)), 0.0)
        u_e = (1 - inputs.access) * expected_gap(base_e, inputs)
        u_p = (1 - sigma) * (1 - inputs.access) * gap_p
        return dict(m=m, ready=ready, need_p=need_p, gap_p=gap_p, bridged=bridged, demand=demand, N=N, sigma=sigma,
                    u_e=u_e, u_p=u_p, base_e=base_e, phi_next=1 - ((1 - share) * u_e + share * u_p))

    phi = _solve_phi(state, f["shape"])
    s = state(phi)
    r_p = np.maximum(rho_p + inputs.o, 0.0)
    r_nom = r_p + pi + np.zeros(phi.shape)
    P_bar = s["sigma"] * s["demand"]
    earning = s["N"] if inputs.pool_cash_return else P_bar
    # A floored coupon raises actual loan income above rho_p + o; that same
    # amount belongs to owners rather than disappearing from consolidated wealth.
    floor_income = np.maximum(-rho_p - inputs.o, 0.0) * P_bar
    R_p = np.divide(rho_p * earning + floor_income + s["m"], s["N"], out=np.full(phi.shape, np.nan), where=s["N"] > 0)
    internal = f["card"] * share * phi
    merchant = (inputs.f_card - inputs.rewards) * internal if inputs.merchant_fees else 0.0 * internal
    margin = merchant - inputs.alpha * internal + s["sigma"] * inputs.term * s["bridged"] * (inputs.r_ext - r_nom)
    working = np.minimum(f["float_p"], (1 + inputs.alpha) * internal)
    liquid = share * (f["float_p"] + (inputs.buffer if keep else 0.0))
    c_ins = np.divide(np.maximum(rho_p, 0.0) * P_bar, liquid, out=np.zeros(phi.shape), where=liquid > 0)
    # Payment-use bound (the paper): only payers with a positive margin M_i are included; with none
    # included the bound is +inf and c = c_ins (a payer with M_i <= 0 "does not set the rate for everyone else").
    c_ir = np.divide(margin, working, out=np.full(phi.shape, np.inf), where=(working > 0) & (margin > 0))
    c = np.where(s["ready"] & charged, np.minimum(c_ins, c_ir), 0.0)
    D = c * liquid
    rebate = np.minimum(D, np.maximum(rho_p, 0.0) * P_bar)
    net = np.where(P_bar > 0, r_nom - np.divide(rebate, P_bar, out=np.zeros(phi.shape), where=P_bar > 0), np.nan)
    theta = np.divide(D, D + r_p * P_bar, out=np.full(phi.shape, np.nan), where=D + r_p * P_bar > 0)
    gap_e = expected_gap(s["base_e"], inputs)
    outside_e = inputs.penalty * s["u_e"] + inputs.r_ext * inputs.term * inputs.access * gap_e
    outside_p = inputs.penalty * s["u_p"] + inputs.r_ext * inputs.term * (1 - s["sigma"]) * inputs.access * s["gap_p"]
    per_head = np.divide(s["N"], share, out=np.zeros(phi.shape), where=share > 0)
    # A buffer earns its yield only on the part not spent on needs for `term` months.
    used_e = s["base_e"] + f["shock_mean"] - gap_e
    used_p = s["need_p"] - s["gap_p"]
    held = (pi * (inputs.buffer - inputs.term * used_p) - f["idle"] * inputs.buffer if keep else
            (rho_col - f["idle"]) * s["sigma"] * inputs.buffer - f["idle"] * inputs.term * (1 - s["sigma"]) * used_p)
    parts = dict(buffer=held + 0 * phi, savings=0.0 * phi, indexation=pi * f["float_p"] + 0 * phi,
                 coupon=-r_nom * inputs.term * s["sigma"] * s["bridged"], provider_fee=-inputs.alpha * internal,
                 owner=np.nan_to_num(R_p - rho_p) * per_head, merchant=merchant + 0 * phi)
    wallet_e = -outside_e + rho_col * inputs.savings + f["idle"] * (inputs.buffer - inputs.term * used_e)
    wallet_p = -outside_p + rho_col * inputs.savings + f["idle"] * inputs.buffer + sum(parts.values())
    reserve = liquid + (0.0 if inputs.pool_cash_return else s["N"] - P_bar)
    rate = np.where(P_bar > 0, np.nan_to_num(net, nan=0.0), r_nom)
    cost = (rho_col + c - pi) * inputs.buffer * keep + rate * inputs.term * s["sigma"] * s["bridged"] + outside_p
    return dict(phi=phi, ready=s["ready"], sigma=s["sigma"], N=s["N"], P_bar=P_bar, R=R_p + pi, r_g=r_nom,
                c=c, theta=theta, net_rate=net, wallet_p=wallet_p, wallet_e=wallet_e, parts=parts,
                outside_p=outside_p, outside_e=outside_e, issuer=(rho_col - pi) * reserve, failures=1 - phi,
                experienced_cost=cost, buffer_use_e=f["idle"] * inputs.term * used_e)


def _m0(inputs, rho, A):
    """Actual DeFi: participants pay in USDC and supply buffers and savings to the pinned Comet market.

    The external market's capacity dwarfs these households, so its rates do
    not move with A; they are taken as rho_H plus the pinned spreads. Comet
    lends only against posted collateral, so a household's own supplied
    buffer is its bridge, and only the collateralised share of any remaining
    need is borrowed. There is no pool, readiness, charge or CPM issuer.
    """
    f = _frame(inputs, rho, A)
    share, rho_col = f["share"], f["rho"]
    supply_rate = rho_col + inputs.supply_premium + np.zeros(f["shape"])
    borrow_rate = supply_rate + inputs.borrow_margin
    cover = inputs.collateral_cover

    def state(phi):
        """Failures implied by a completion rate; participants lose the float and keep their own buffer."""
        base_e, base_p = 1 - phi, 1 - phi + f["lost"]
        gap_p = expected_gap(base_p, inputs)
        u_e = (1 - inputs.access) * expected_gap(base_e, inputs)
        u_p = (1 - cover) * (1 - inputs.access) * gap_p
        return dict(base_e=base_e, need_p=base_p + f["shock_mean"], gap_p=gap_p, u_e=u_e, u_p=u_p,
                    phi_next=1 - ((1 - share) * u_e + share * u_p))

    phi = _solve_phi(state, f["shape"])
    s = state(phi)
    internal = f["card"] * share * phi
    merchant = (inputs.f_card - inputs.rewards) * internal if inputs.merchant_fees else 0.0 * internal
    gap_e = expected_gap(s["base_e"], inputs)
    outside_e = inputs.penalty * s["u_e"] + inputs.r_ext * inputs.term * inputs.access * gap_e
    outside_p = inputs.penalty * s["u_p"] + inputs.r_ext * inputs.term * (1 - cover) * inputs.access * s["gap_p"]
    used = s["need_p"] - s["gap_p"]
    parts = dict(buffer=supply_rate * (inputs.buffer - inputs.term * used) - f["idle"] * inputs.buffer,
                 savings=(supply_rate - rho_col) * inputs.savings, indexation=0.0 * phi,
                 coupon=-borrow_rate * inputs.term * cover * s["gap_p"], provider_fee=-inputs.gas_per_unit * internal,
                 owner=0.0 * phi, merchant=merchant + 0 * phi)
    used_e = s["base_e"] + f["shock_mean"] - gap_e
    wallet_e = -outside_e + rho_col * inputs.savings + f["idle"] * (inputs.buffer - inputs.term * used_e)
    wallet_p = -outside_p + rho_col * inputs.savings + f["idle"] * inputs.buffer + sum(parts.values())
    active = (share > 0) & np.ones(f["shape"], bool)
    borrowed = share * inputs.term * cover * s["gap_p"]
    return dict(phi=phi, ready=active, sigma=cover + 0 * phi, N=share * (inputs.buffer + inputs.savings) + 0 * phi,
                P_bar=borrowed + 0 * phi, R=supply_rate, r_g=borrow_rate, c=0.0 * phi, theta=np.full(phi.shape, np.nan),
                net_rate=np.where(borrowed > 0, borrow_rate, np.nan), wallet_p=wallet_p, wallet_e=wallet_e, parts=parts,
                outside_p=outside_p, outside_e=outside_e, issuer=0.0 * phi, failures=1 - phi, released=active,
                buffer_use_e=f["idle"] * inputs.term * used_e)


def evaluate(inputs, rho, A):
    """Quasi-steady outcomes on a (rho_H, A) grid for inputs.arm; each array is (len(rho), len(A)).

    In the pool arms each cell takes the participants' cheaper buffer choice
    under the experienced-cost rule: cost is the outside return forgone and the charge
    on held P, plus credit interest at the experienced net rate, plus outside
    costs. Ties go to holding less.
    """
    if inputs.arm not in ARMS:
        raise ValueError(f"unknown arm {inputs.arm!r}")
    if inputs.arm == "M0":
        return _m0(inputs, rho, A)
    out, kept = _pool(inputs, rho, A, keep=False), _pool(inputs, rho, A, keep=True)
    release = out["experienced_cost"] <= kept["experienced_cost"]

    def pick(a, b):
        """Per-cell choice between the released and kept states."""
        return dict(map(lambda key: (key, pick(a[key], b[key])), a)) if isinstance(a, dict) else np.where(release, a, b)

    chosen = pick(out, kept)
    chosen["released"] = release
    return chosen


def gains(inputs, rho, A):
    """Each position's monthly gain over S0, the channels, and the system total (the paper's
    neutrality result).

    The participant gain splits into: outside interest and penalties avoided,
    buffer (released or held), savings premium, indexation of P balances,
    credit interest paid, payment fee or gas paid, owner return above the
    benchmark and (only if switched on) merchant fees. delta_W adds
    participants, non-participants and the issuer per capita; from_lenders is
    the part that was interest and penalties paid to outside lenders in S0.
    """
    out = evaluate(inputs, rho, A)
    zero = evaluate(inputs, rho, [0.0])
    share = np.atleast_1d(np.asarray(A, float))[None, :]
    wallet0, outside0 = zero["wallet_e"][:, :1], zero["outside_e"][:, :1]
    out["parts"]["outside"] = outside0 - out["outside_p"]
    # S0's buffer forgoes its yield while spent on needs (the same rule); that saving belongs to the
    # buffer channel.
    out["parts"]["buffer"] = out["parts"]["buffer"] + zero["buffer_use_e"][:, :1]
    gain_p, gain_e = out["wallet_p"] - wallet0, out["wallet_e"] - wallet0
    out.update(gain_participant=gain_p, gain_nonparticipant=gain_e,
               completion_gain=out["phi"] - zero["phi"][:, :1], investor=out["R"] - np.atleast_1d(rho)[:, None],
               experience=out["wallet_p"] - out["wallet_e"],
               delta_W=share * gain_p + (1 - share) * gain_e + out["issuer"],
               from_lenders=share * (outside0 - out["outside_p"]) + (1 - share) * (outside0 - out["outside_e"]))
    return out


def adopt(inputs, rho, A0, months, dt=0.05, grid=401):
    """Integrate participation on a (rho_H, A_0) grid.

    Entry is social: non-participants join at rate xi0 + xi1 A.
    Exit is experiential: participants review at the intensity whose monthly
    chance is upsilon, -ln(1 - upsilon) (0.166 a month by default), and leave
    when their realised outcome trails non-participants' by more than the
    switching cost. Nobody computes a counterfactual gain before joining.
    Returns participation at whole months, shape (months+1, len(rho), len(A0)).
    """
    table = gains(inputs, rho, np.linspace(0.0, 1.0, grid))["experience"]
    state = np.broadcast_to(np.atleast_1d(np.asarray(A0, float))[None, :],
                            (len(np.atleast_1d(rho)), len(np.atleast_1d(A0)))).copy()
    per_month = int(round(1 / dt))

    def experience_at(share):
        """Linear interpolation of the experienced outcome gap along each rho row."""
        position = np.clip(share, 0.0, 1.0) * (grid - 1)
        low = np.minimum(np.floor(position).astype(int), grid - 2)
        frac = position - low
        return (np.take_along_axis(table, low, axis=1) * (1 - frac)
                + np.take_along_axis(table, low + 1, axis=1) * frac)

    def logistic(x):
        """Overflow-safe logistic weight."""
        return 0.5 * (1.0 + np.tanh(x / 2.0))

    # The integration is in continuous time, so it reads the review intensity, not the monthly chance.
    review = -np.log1p(-inputs.upsilon)
    path = [state.copy()]
    for step in range(months * per_month):
        lag = experience_at(state)
        entry = (inputs.xi0 + inputs.xi1 * state) * (1 - state)
        exit_ = review * state * logistic((-lag - inputs.switch_cost) / inputs.noise)
        state = np.clip(state + dt * (entry - exit_), 0.0, 1.0)
        if (step + 1) % per_month == 0:
            path.append(state.copy())
    return np.array(path)

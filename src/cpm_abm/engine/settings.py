"""The Economy settings: population size, calendar, behavioural switches and stress options.

Also the legacy rules, the switches that give the earlier engines' behaviour for regression checks.
"""
from dataclasses import dataclass, replace

import numpy as np

from cpm_abm.engine.constants import EWA_SHARE, HOLDING_COST, JOB_LOSS, RING_SIDE
from cpm_abm.engine.rates import m0_rates


@dataclass(frozen=True)
class Economy:
    """The economy: population size, calendar, behavioural switches and stress options.

    Defaults are the decided baselines (``docs/DECISIONS.md``), as of
    21 October 2026, with the household economy and failure cost decided on
    3 November (the card base, outside prices following r_out, normal job
    loss and completed spells among them) and the yardsticks and CPM's own
    rules decided on 3 and 4 November (the issuer's costs and the owners'
    spread among them); each of those rules has its switch
    below, ``LEGACY_STEP45`` turns the 3 and 4 November yardsticks and pool
    rules off, and ``LEGACY`` (``legacy``) turns all of them off; demurrage
    (4 November) has none. Contract and price
    inputs (rho_H, o, C_fix, card APR ...) live in
    ``core_model.Inputs`` so the ABM and the core model read the same
    numbers; every runner sets C_fix to its sourced level (decided
    5 Nov: ``run_economy_figures.engine_inputs``, $0.18 a consumer unit a
    year), the core's 5e-5 placeholder staying only as the default of
    ``Inputs()``; the engine no longer reads the core's provider fee alpha
    (decided 5 Nov: P payments run on stablecoin rails). The failed-payment fee is the ABM's own
    (``FAIL_FEE``, decided 30 Oct); the core model keeps its declared 5%.
    """

    n: int = 1000                 # people: 1,000 main, 100 development
    alpha: float = 1.5            # Pareto shape of initial wealth (liquid and illiquid)
    buffer_months: float = 0.6    # median initial wealth in months of own spending, before the survey's cushions
    beta: float = 0.5             # spending elasticity to relative wealth
    bundles: int = 32             # service bundles per person per month
    burn_in: int = 6              # months of S0 before launch, in every arm (declared)
    months: int = 60              # months after launch
    # Most within-day settlement sweeps; iteration stops at the fixed point. Raised from 500 (decided 14 Nov 2026):
    # under the harsh stress a ring of late wages among payers with no money and no card can need far more, and the
    # cap changes no day that settles within it. Days needing more than SLOW_SWEEPS are counted (slow_days).
    sweeps: int = 20_000
    wealth_floor: float = 0.02    # relative-wealth floor for spending (declared)
    seed: int = 20261021
    n12: bool = True              # outside safe return rises with wealth (False: rho_H for everyone)
    shocks: bool = False          # SHED unexpected expenses: off under normal conditions (decided 21 Oct)
    routing: str = "fee"          # "fee": P only where it saves the card fee (21 Oct); "all": every payment in P
    h4_months: int = 12           # leaving-rule experience window in months (decided 21 Oct); 0 = one cycle
    # The leaving rule's logistic noise (decided 4 Nov) as a multiple of its decided scale, the core model's 1e-4
    # of each person's own monthly spending; every result reports 0.5 and 2 beside it.
    leave_noise: float = 1.0
    # Core-model conventions (``core_model.py``): a participant's working cash is P and conversion costs
    # only the switching cost chi at joining and leaving; merchant-fee savings are a transfer kept out of experience
    # (f_ext = 0). The alternatives are sensitivities: routine conversion at every E-P crossing and
    # merchant savings counted in experience.
    routine_conversion: bool = False
    merchant_in_experience: bool = False
    # Stress: outside lenders' interest, and the card's fees (14 Nov 2026), return to households by spending.
    lender_income_recirculated: bool = False
    inflation: float = 0.02 / 12  # CPI in every arm (decided 21 Oct: the 2% target)
    # M0 rates. "reserve" (decided 5 Nov: M0 is the strongest real DeFi, the default): USDC earns the bill less the
    # Sky Savings Rate's spread under it (``RESERVE_SPREAD``), floored at zero, paid from T-bill income as an outside
    # flow, and Comet lends against collateral at its borrow rate, both moving with r_out as observed (decided
    # 5 Nov: ``m0_rates``, read as ``m0_rates`` below says). "pinned" (21 Oct: "make m0 real defi") reads the supply
    # and borrow rates off the pinned Comet curves at the utilisation this economy's own supply produces; "fixed" is the
    # earlier M0 convention (supply rho_H + premium whatever the volume), kept as the upper-bound sensitivity.
    comet: str = "reserve"
    # How M0's rates follow r_out in the "reserve" mode (decided 5 Nov): "observed", one for one from the observed
    # October 2026 levels (the default); "fitted", the lag-3 OLS lines of the same estimate, a sensitivity
    # (``M0_FITTED``).
    m0_rates: str = "observed"
    # M0's crypto collateral holders (decided 5 Nov; the 5 Nov review): this share of people, drawn once on a stream
    # of their own (``build_population``), can borrow from Comet against full cover, and nobody else. 0, no crypto
    # collateral, is the default here and in the runners (CRYPTO_SHARE; decided 12 Nov: collateral lending by
    # Compound III is not run or reported; the option remains only for the unit tests of that code path). It replaces
    # the core model's uniform ``collateral_cover``, which the engine no longer reads.
    crypto_share: float = 0.0
    # Distress control (decided 21 and 30 Oct; 3 Nov): the extra monthly rate per job at which jobs lose their wage
    # in a distress year, above normal job loss (``job_loss``), in the year that starts distress_start months after
    # launch and lasts distress_length months (months 25-36); 0 is the level without distress. The harsh stress
    # (decided 14 Nov 2026), with no switch: an extra layoff's wage leaves the household economy for its whole spell,
    # owed by its payer to the outside on the job's pay dates, its worker receiving nothing; after normal job loss the
    # payer keeps the wage, so level 0 is unchanged. No unemployment insurance is modelled (declared); 2 points, the
    # stress clause's headline, is 2009's wage loss before unemployment insurance.
    distress: float = 0.0
    distress_start: int = 24
    distress_length: int = 12
    # The household economy and failure cost (decided 3 Nov), each rule with its switch; the legacy value of each
    # is in ``LEGACY_RULES``.
    # A re-queued wage counts once in the buffer replay's flows, on the day it first fell due (a defect fixed).
    requeued_once: bool = True
    # Wages settle on their job's pay dates at BLS pay frequencies (``PAY_DAYS``), not on the recipient's billing dates.
    pay_dates: bool = True
    # At most this many failure fees a payer a model month, counted in fee units (a partly unpaid payment counts as its
    # share), reset on day 1; past it a failure carries no fee. np.inf is no monthly cap. Two (decided 4 Nov): the
    # S0 check gave $37.35 a consumer unit a year at two and $53.35 at three, both in the $28 to $62 band, and two leans
    # against CPM; three until then, the Step 3 commit's default.
    fees_a_month: float = 2.0
    # The buffer choice of payers without pool access prices failures past the monthly cap at $27 (a declared device
    # standing in for the closure and lost service the model omits); False prices them at $0, as the experience
    # replays do (the S0 check's second reading).
    buffer_prices_past_cap: bool = True
    # The failure fee is booked as fee debt: no interest, repaid first (False: outside debt at r_ext, as built).
    fee_debt_free: bool = True
    # The real part's failure line counts unpaid shares of failed bills and wages and, for payers without a card,
    # bridged shares, each obligation once (False: fee units and pool payer-days, as built). Read by the runner.
    failure_shares: bool = True
    # Earned-wage access in every arm: the share of people who hold it, drawn among wage earners on a stream of its
    # own (``EWA_SHARE``, an upper bound); a short payer without a card uses it after the pool and before failing. 0 is
    # no access (as built).
    earned_wage_share: float = EWA_SHARE
    # Every non-housing bundle is card-eligible, 28% of spending (False: the core's card share of them, 18.2%, as
    # built).
    card_base_all: bool = True
    # Outside deposit and credit rates follow r_out from their October 2026 levels (``BILL_ANCHOR``; False: fixed, as
    # built): the savings deposit rate by deposit_pass_through of a change, card and business rates one for one, and new
    # vehicle and personal loans by their own pass-throughs, sourced (13 Nov 2026; 0, the fallback for an unsourced
    # pass-through, until then): the change in the Fed G.19 commercial-bank finance rate over the change in the
    # three-month bill (FRED TB3MS, the same month), February 2022 to February 2024, the 2022 to 2023 tightening:
    # new-car loans, 60 months (FRED RIFLPBCIANM60NM), 4.52% to 8.22% against 0.33% to 5.24%, 0.75; 24-month personal
    # loans (FRED TERMCBPER24NS), 9.39% to 12.49%, 0.63. Least-squares slopes over the window's nine quarterly
    # observations agree: 0.74 (standard error 0.06) and 0.66 (0.08). Series in data/raw/fred_g19_pass_through_20261113.
    # The shift is r_out less the October 2026 bill on r_out's basis (``outside_prices``), so at that rate nothing
    # moves.
    linked_rates: bool = True
    deposit_pass_through: float = 0.08
    vehicle_pass_through: float = 0.75
    personal_pass_through: float = 0.63
    # Normal job loss, the monthly rate per job in every month and every arm (``JOB_LOSS``; 0 is none, as built).
    job_loss: float = JOB_LOSS
    # Spell lengths are completed lengths consistent with the BLS figures for spells in progress (False: those figures
    # read as completed lengths, as built).
    completed_spells: bool = True
    # The yardsticks and CPM's own rules (decided 3 and 4 Nov), each rule with its switch; the legacy value of each
    # is in ``LEGACY_STEP45``.
    # The issuer's own cost of P outstanding, a month, its expenses line (0.24% a year, ``HOLDING_COST``, the money
    # funds' cost of holding money; 0 is none, as built). The provider fee and the rail it paid first (3 Nov) are gone
    # (decided 5 Nov: P payments run on stablecoin rails), and with them their switch.
    issuer_cost: float = HOLDING_COST
    # Owners' spread over the safe alternative, a month (0.25 point a year, declared, unsourced; 0 and 1 point are
    # sensitivities): applied alike to owners' alternative, every share's, and the coupon's capital part. The
    # yardsticks read it through ``_World._owners_alternative`` and ``_owners_alternative_nominal`` (0 as built).
    owner_spread: float = 0.0025 / 12
    # How the pool's paying its own way is read (decided 3 Nov: "The pool pays its own way"): "margin" reads the
    # pool's own margin (``_World._own_margin``), with owners' compensation K at their alternative, without the 0.9,
    # and recovered principal credited in the old ratio's numerator, which is kept for one map; "coverage" is the
    # self-financing test as built, collected income over 0.95 of K at 0.9 of r_out and the pool's costs. Read by the
    # engine's K and interest_collected records and by the runner's persistence test 4 and falsifier 3.
    self_financing: str = "margin"
    # What entrants compare with their alternative at dealing: "quote", the pool's published quote at N* (the decided
    # rule, as built); "realised", the pool's trailing realised return (``_World._track_record``), a sensitivity
    # (decided 11 Nov: the entry check), which reads the quote while the pool has no track record;
    # "leaving_rule", a third reading between the two (decided 12 Nov): the same track record, read by each
    # saver with the decided leaving rule's own dispersion (``_World._enters``), so "realised" is its limit with no
    # noise (``leave_noise`` 0).
    entry_reads: str = "quote"
    # Loan losses (decided 12 Nov): "none", as built (a loan written off stays owed and is collected later, so
    # lenders lose almost nothing); "sourced", the bound: every lender, the pool included, discharges each month the
    # sourced charge-off rate of the bank loans its loans replace (``charge_off_rates``, ``_World._loan_losses``),
    # and the pool's coupons carry that rate (``_World._priced_loss``).
    loan_losses: str = "none"
    # The distress line cut (decided 14 Nov 2026), a switchable side check only: lines are held through the distress
    # year in the main reading (False); True cuts each open line at the start of the distress year by its tier's sourced
    # share times the distress level over 2% (``CARD_CUT``, ``_World._cut_lines``).
    card_line_cut: bool = False
    # The robustness switches (docs/ROBUSTNESS_PLAN.md, section 5), side checks only, each off by default; every one
    # draws on streams of its own (``constants``), and the network, thresholds and launch set are the same in every
    # arm (``network.build_network``).
    # Buffer review share alpha: each month a person re-chooses its cash buffer only when its review draw is below
    # alpha, and otherwise keeps last month's. 1 is the base, everyone every month.
    buffer_review: float = 1.0
    # Joining rule: "linear", the base, chance xi0 + xi1 x contact share; "threshold", xi0 + xi1 where the contact share
    # is at least the person's own threshold and xi0 otherwise. Thresholds, read only under "threshold": "uniform" on 0
    # to 1, "measured" log-normal (``THRESHOLD_LOG_MEAN``), or one common number for everyone.
    joining: str = "linear"
    thresholds: object = "uniform"
    # Sellers of services, shocks and instalment purchases: "uniform" over the others, the base; "ring", one of the
    # buyer's 32 nearest positions on a ring with chance local_share and anyone else otherwise; "hubs", with chance
    # proportional to a weight falling with the rank of initial spending (``HUB_WEIGHT_EXPONENT``). Wage links stay
    # uniform in every world.
    sellers: str = "uniform"
    local_share: float = 1.0
    # Launch placement: "scattered", the base, each person with chance a0; "neighbourhood" (ring only), the round(a0 n)
    # people on the first ring positions; "largest" (hubs only), the round(a0 n) people with the largest weights.
    launch: str = "scattered"

    def __post_init__(self):
        """Refuse an unknown reading of self-financing (the 4 Nov review) or of M0's rates (5 Nov): a misspelt one would
        silently read as the coverage test as built, or as the fixed rates."""
        if self.self_financing not in ("margin", "coverage"):
            raise ValueError(f"self_financing is 'margin' or 'coverage', not {self.self_financing!r}")
        if self.comet not in ("reserve", "pinned", "fixed"):
            raise ValueError(f"comet is 'reserve', 'pinned' or 'fixed', not {self.comet!r}")
        if self.m0_rates not in ("observed", "fitted"):
            raise ValueError(f"m0_rates is 'observed' or 'fitted', not {self.m0_rates!r}")
        if self.entry_reads not in ("quote", "realised", "leaving_rule"):
            raise ValueError(f"entry_reads is 'quote', 'realised' or 'leaving_rule', not {self.entry_reads!r}")
        if self.loan_losses not in ("none", "sourced"):
            raise ValueError(f"loan_losses is 'none' or 'sourced', not {self.loan_losses!r}")
        self._check_switches()

    def _check_switches(self):
        """Refuse a robustness switch that is misspelt, out of range or in a combination the plan does not define: a
        neighbourhood launch needs the ring, a largest-first launch needs hubs, thresholds are read only under the
        threshold rule and a local share only on the ring, which needs more people than one neighbourhood."""
        if not 0 < self.buffer_review <= 1:
            raise ValueError(f"buffer_review is a share above 0 and at most 1, not {self.buffer_review!r}")
        if self.joining not in ("linear", "threshold"):
            raise ValueError(f"joining is 'linear' or 'threshold', not {self.joining!r}")
        named = isinstance(self.thresholds, str)
        if (named and self.thresholds not in ("uniform", "measured")) or (not named and (
                isinstance(self.thresholds, bool) or not isinstance(self.thresholds, (int, float))
                or not 0 <= self.thresholds <= 1)):
            raise ValueError(f"thresholds is 'uniform', 'measured' or one number from 0 to 1, not {self.thresholds!r}")
        if self.joining == "linear" and self.thresholds != "uniform":
            raise ValueError("thresholds are read only under the threshold joining rule (joining='threshold')")
        if self.sellers not in ("uniform", "ring", "hubs"):
            raise ValueError(f"sellers is 'uniform', 'ring' or 'hubs', not {self.sellers!r}")
        if not 0 <= self.local_share <= 1:
            raise ValueError(f"local_share is a share from 0 to 1, not {self.local_share!r}")
        if self.sellers != "ring" and self.local_share != 1.0:
            raise ValueError("local_share is read only on the ring (sellers='ring')")
        if self.sellers == "ring" and self.n <= 2 * RING_SIDE:
            raise ValueError(f"the ring needs more than {2 * RING_SIDE} people, one neighbourhood; got {self.n}")
        if self.launch not in ("scattered", "neighbourhood", "largest"):
            raise ValueError(f"launch is 'scattered', 'neighbourhood' or 'largest', not {self.launch!r}")
        needs = dict(neighbourhood="ring", largest="hubs").get(self.launch)
        if needs is not None and self.sellers != needs:
            raise ValueError(f"a {self.launch} launch needs sellers={needs!r}, not {self.sellers!r}")


# The Step 3 engine's rules (decided 4 Nov): every Step 4 and Step 5 switch off, as
# ``replace(economy, **LEGACY_STEP45)``. With no issuer cost the issuer's derived share of the reserve return is zero.
LEGACY_STEP45 = dict(issuer_cost=0.0, owner_spread=0.0, self_financing="coverage")
# The Step 1 engine's rules (decided 4 Nov): every Step 3, 4 and 5 switch off and no monthly cap of fees; ``legacy``
# gives any economy these rules.
LEGACY_RULES = dict(requeued_once=False, pay_dates=False, fees_a_month=np.inf, fee_debt_free=False,
                    failure_shares=False, earned_wage_share=0.0, card_base_all=False, linked_rates=False, job_loss=0.0,
                    completed_spells=False, **LEGACY_STEP45)


def legacy(economy=None):
    """``economy`` (default ``Economy()``) with the Step 1 rules: every Step 3, 4 and 5 rule off, no monthly cap."""
    return replace(economy or Economy(), **LEGACY_RULES)


LEGACY = legacy()

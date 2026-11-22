"""Standalone Compound III (Comet) engine: the pinned USDC market in exact integer arithmetic.

SOURCE: the pinned Ethereum USDC Comet in ``data/raw/compound_usdc_20261017/``
(block 26,214,368; implementation 0x63e749153baf1838f63ca22c275370bd2b1ceb15;
CometWithExtendedAssetList.sol and CometCore.sol). This module translates
accrual, utilisation and rate curves, signed principals, collateral custody
and gates, ``baseBorrowMin``, ``withdrawTo``, ``absorb``, ``buyCollateral``,
reserves and zero-speed reward tracking into raw-integer Python. It reads the
pinned data files and imports nothing from ``results/``.

DECLARED inputs must be supplied in an explicit Scenario: background-touch
horizon, collateral universe, opening composition, gas, tariffs, funded
counterparties and oracle tape. Historical values, including the
historical stress tape, exist only in the named unit-test fixture. The
normal_time_scenario supplies the chosen 1/30 monetary normalization and
flat tape; its other choices remain required arguments. Gas units are
declared, not measured at the pinned implementation.

Every transfer has a named payer and recipient and no account goes negative.
A transaction either commits completely or leaves no economic trace. Gas
incidence: a preflight rejection pays nothing; a submitted revert pays gas
only. The household adapter calls the public methods of ``Comet``.
"""
import copy
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "compound_usdc_20261017"
FACTOR, INDEX, PRICE, BASE, WEI = 10**18, 10**15, 10**8, 10**6, 10**18
DAY, YEAR, INTRINSIC_GAS = 86_400, 31_536_000, 21_000
MAX = "max"   # uint256.max sentinel: whole claim (withdraw) or whole debt (supply)
PAUSE_KEYS = ("supply", "transfer", "withdraw", "absorb", "buy")


class Revert(Exception):
    """A source failure condition inside one transaction; no economic transfer survives it."""


@dataclass(frozen=True)
class Receipt:
    """Outcome of one submitted or preflighted transaction (gas incidence)."""

    status: str
    reason: str = None
    gas_wei: int = 0
    result: object = None

    @property
    def ok(self):
        """True only for a committed transaction."""
        return self.status == "ok"


# ----- SOURCE: pinned inputs ---------------------------------------------------------------
def _read(name):
    """One preserved JSON input, read without changing it."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _headers(name):
    """Block number -> (base fee wei, timestamp) for every header saved in one JSON-RPC response file."""
    stack, found = [_read(name)], {}
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "baseFeePerGas" in node and "number" in node:
                found[int(node["number"], 16)] = (int(node["baseFeePerGas"], 16), int(node["timestamp"], 16))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _curve(raw, prefix):
    """Per-second rate curve fields of one side, exactly as returned by the pinned getters."""
    return dict(kink=int(raw[f"{prefix}Kink()"]), base=int(raw[f"{prefix}PerSecondInterestRateBase()"]),
                low=int(raw[f"{prefix}PerSecondInterestRateSlopeLow()"]),
                high=int(raw[f"{prefix}PerSecondInterestRateSlopeHigh()"]))


def _asset(row):
    """Pinned per-asset collateral settings, balances and oracle answer (raw integers)."""
    raw = row["raw"]
    return dict(offset=int(raw["offset"]), scale=int(raw["scale"]), borrow_cf=int(raw["borrow_factor"]),
                liquidate_cf=int(raw["liquidation_threshold_factor"]),
                liquidation_factor=int(raw["liquidation_credit_factor"]), supply_cap=int(raw["supply_cap"]),
                customer_total=int(raw["user_collateral"]), custody=int(raw["custody"]),
                inventory=int(raw["protocol_inventory"]), price=int(raw["price_1e8"]))


@dataclass(frozen=True)
class Pin:
    """SOURCE values of the pinned block, verified against the saved byte manifest."""

    block: int
    timestamp: int
    base_fee: int
    stress_block: int
    stress_fee: int
    supply_curve: dict
    borrow_curve: dict
    borrow_min: int
    target_reserves: int
    storefront: int
    min_rewards: int
    tracking_scale: int
    speeds: tuple
    descale: int
    paused: dict
    base_price: int
    assets: dict
    stored: dict
    cash: int
    getters: dict
    identities: dict


@lru_cache(maxsize=1)
def load_pin():
    """Read and verify the pinned snapshot, its block header and the 2023 stress block's base fee."""
    manifest = _read("sha256_manifest.json")
    names = ("snapshot.json", "anchor_responses.json", "history_state_responses.json")
    identities = {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in names}
    if any(identities[name] != manifest[name] for name in names):
        raise ValueError("pinned Compound inputs differ from the saved manifest")
    snap = _read("snapshot.json")
    raw = snap["raw_settings"]
    base_fee, timestamp = _headers("anchor_responses.json")[int(snap["block"])]
    if timestamp != int(datetime.fromisoformat(snap["utc"]).timestamp()):
        raise ValueError("pinned block timestamp and snapshot time disagree")
    stress_block = 18_759_911
    stress_fee, _ = _headers("history_state_responses.json")[stress_block]
    keys = ("supply_index", "borrow_index", "track_supply", "track_borrow", "supply_base", "borrow_base", "last")
    stored = dict(zip(keys, map(int, snap["stored_totals_raw"][:7])))
    paused = dict(zip(PAUSE_KEYS, map(lambda key: bool(int(raw[f"is{key.capitalize()}Paused()"])), PAUSE_KEYS)))
    return Pin(block=int(snap["block"]), timestamp=timestamp, base_fee=base_fee, stress_block=stress_block,
               stress_fee=stress_fee, supply_curve=_curve(raw, "supply"), borrow_curve=_curve(raw, "borrow"),
               borrow_min=int(raw["baseBorrowMin()"]), target_reserves=int(raw["targetReserves()"]),
               storefront=int(raw["storeFrontPriceFactor()"]), min_rewards=int(raw["baseMinForRewards()"]),
               tracking_scale=int(raw["trackingIndexScale()"]),
               speeds=(int(raw["baseTrackingSupplySpeed()"]), int(raw["baseTrackingBorrowSpeed()"])),
               descale=int(raw["baseScale()"]) // int(raw["baseAccrualScale()"]), paused=paused,
               base_price=int(snap["base_oracle_round_raw"][1]),
               assets={row["symbol"]: _asset(row) for row in snap["collaterals"]}, stored=stored,
               cash=int(Decimal(snap["cash_usdc"]) * BASE),
               getters=dict(utilisation=int(raw["getUtilization()"]), total_supply=int(raw["totalSupply()"]),
                            total_borrow=int(raw["totalBorrow()"]), reserves=int(raw["getReserves()"]),
                            supply_rate=int(snap["rates"]["supply"]["per_second_raw"]),
                            borrow_rate=int(snap["rates"]["borrow"]["per_second_raw"])),
               identities=identities)


# ----- DECLARED: explicit scenarios, without historical defaults --------------------------
@dataclass(frozen=True)
class Scenario:
    """Explicit numerical inputs; budgets/tariffs are already in the chosen model units.

    monetary_scale applies only to the source Pin's monetary dimensions.
    Collateral token quantities, gas/wei, time, indexes and factors stay native.
    Every operational/funding value and the horizon must be declared by callers.
    """

    universe: tuple
    phi: Fraction
    eth_float: int
    gas_units: dict
    priority_fee: int
    ramp_fixed: int
    ramp_rate: Fraction
    dex_fee: Fraction
    observation_delay: int
    budgets: dict
    oracle_tape: tuple
    slot: int
    horizon_days: int
    absorber: str
    buyer: str
    ramp: str
    dex: str
    monetary_scale: Fraction

    def __post_init__(self):
        """Reject an absent/invalid horizon and undeclared normalization factors."""
        if type(self.horizon_days) is not int or self.horizon_days <= 0:
            raise ValueError("scenario horizon_days must be a positive whole number of days")
        if self.monetary_scale not in (Fraction(1), Fraction(1, 30)):
            raise ValueError("scenario monetary_scale must be native 1 or the normal-time 1/30")
        dates = tuple(Fraction(str(row[0])) for row in self.oracle_tape)
        if dates != tuple(sorted(dates)) or any(day < 0 or day > self.horizon_days for day in dates):
            raise ValueError("oracle tape must be dated in order within the explicit horizon")


def normal_time_scenario(*, universe, phi, eth_float, gas_units, priority_fee, ramp_fixed, ramp_rate,
                         dex_fee, observation_delay, budgets, slot, horizon_days, absorber, buyer, ramp, dex):
    """Normal-time scenario: flat tape and 3,000 reference units = 100 model E.

    All other inputs are explicit. In particular budgets and ramp_fixed must
    already use model monetary units; normalization chooses no funding or tariff.
    This is a numerical normalization, not a public-market calibration.
    """
    return Scenario(universe=universe, phi=phi, eth_float=eth_float, gas_units=gas_units, priority_fee=priority_fee,
                    ramp_fixed=ramp_fixed, ramp_rate=ramp_rate, dex_fee=dex_fee, observation_delay=observation_delay,
                    budgets=budgets, oracle_tape=(), slot=slot, horizon_days=horizon_days, absorber=absorber,
                    buyer=buyer, ramp=ramp, dex=dex, monetary_scale=Fraction(1, 30))


def _scenario_pin(source, scenario):
    """Independently express the normal-time scale arithmetic without an archived adapter.

    Floor each affected raw integer by 30, then reconstruct getters from those
    integers. Utilization/rates use stored indexes; public supply, borrow and
    reserve getters project accrual to the pinned block timestamp. USDC's
    oracle answer is unchanged; collateral E-prices scale.
    Native token custody/caps, gas/wei, indexes, factors and rate curves do not.
    Source identities still identify the frozen inputs, never synthetic bytes.
    """
    if scenario.monetary_scale == 1:
        return source
    if source.speeds != (0, 0):
        raise ValueError("The normal-time normalization requires the pinned zero-reward market")
    stored = dict(source.stored, supply_base=source.stored["supply_base"] // 30,
                  borrow_base=source.stored["borrow_base"] // 30)
    assets = {name: dict(row, price=row["price"] // 30) for name, row in source.assets.items()}
    stored_supply = stored["supply_base"] * stored["supply_index"] // INDEX
    stored_borrow = stored["borrow_base"] * stored["borrow_index"] // INDEX
    utilisation = 0 if stored_supply == 0 else stored_borrow * FACTOR // stored_supply
    supply_rate, borrow_rate = rate(utilisation, source.supply_curve), rate(utilisation, source.borrow_curve)
    elapsed = source.timestamp - stored["last"]
    supply_index = stored["supply_index"] + mul_factor(stored["supply_index"], supply_rate * elapsed)
    borrow_index = stored["borrow_index"] + mul_factor(stored["borrow_index"], borrow_rate * elapsed)
    supplied = stored["supply_base"] * supply_index // INDEX
    borrowed = stored["borrow_base"] * borrow_index // INDEX
    cash = source.cash // 30
    getters = dict(utilisation=utilisation, total_supply=supplied, total_borrow=borrowed,
                   reserves=cash - supplied + borrowed, supply_rate=supply_rate, borrow_rate=borrow_rate)
    return replace(source, stored=stored, assets=assets, cash=cash, getters=getters,
                   borrow_min=source.borrow_min // 30, target_reserves=source.target_reserves // 30,
                   min_rewards=source.min_rewards // 30)


# ----- SOURCE: pure integer arithmetic -----------------------------------------------------
def mul_factor(n, factor):
    """mulFactor: n * factor / 1e18, floored."""
    return n * factor // FACTOR


def sdiv(a, b):
    """Solidity signed division, truncating toward zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def rate(u, side):
    """getSupplyRate/getBorrowRate at utilisation u (per second, 1e18)."""
    if u <= side["kink"]:
        return side["base"] + mul_factor(side["low"], u)
    return side["base"] + mul_factor(side["low"], side["kink"]) + mul_factor(side["high"], u - side["kink"])


def repay_and_supply(old, new):
    """repayAndSupplyAmount."""
    if new < old:
        return 0, 0
    if new <= 0:
        return new - old, 0
    if old >= 0:
        return 0, new - old
    return -old, new


def withdraw_and_borrow(old, new):
    """withdrawAndBorrowAmount."""
    if new > old:
        return 0, 0
    if new >= 0:
        return old - new, 0
    if old <= 0:
        return 0, old - new
    return old, -new


def dex_out(amount, asset_price, base_price, scale, fee):
    """DECLARED DEX quote: asset sold at the oracle cross rate less the pool fee; no slippage."""
    return amount * asset_price * BASE * (fee.denominator - fee.numerator) \
        // (scale * base_price * fee.denominator)


def dex_in(amount, asset_price, base_price, scale, fee):
    """USDC input that buys at least ``amount`` of the asset from the declared DEX."""
    keep = fee.denominator - fee.numerator
    return -(-amount * asset_price * BASE * fee.denominator // (scale * base_price * keep))


def purchase_size(amount, asset_price, base_price, scale, liquidation_factor, storefront):
    """Liquidation buyer sizing: the largest USDC amount whose storefront quote does not exceed ``amount``."""
    discounted = mul_factor(asset_price, FACTOR - mul_factor(storefront, FACTOR - liquidation_factor))
    return amount * discounted * BASE // (base_price * scale)


class Comet:
    """One pinned Comet market, its named finite counterparties and the households' wallets.

    ``market="external"`` is the chosen external-market boundary: pinned cash, frozen
    background principals and pinned customer collateral. ``"closed"`` is
    the rejected alternative, kept for checks: no background accounts and
    no USDC cash.
    """

    def __init__(self, scenario, *, pin=None, market="external"):
        """Open an explicitly declared scenario; no historical scenario is installed implicitly."""
        if not isinstance(scenario, Scenario):
            raise TypeError("Comet requires an explicit Scenario")
        if market not in ("external", "closed"):
            raise ValueError("market must be 'external' or 'closed'")
        self.d = scenario
        self.source_pin = load_pin() if pin is None else pin
        self.pin = _scenario_pin(self.source_pin, scenario)
        external = market == "external"
        if len(self.d.universe) != 1 or any(asset not in self.pin.assets for asset in self.d.universe):
            raise ValueError("this phase implements the chosen single-asset (WETH) universe only")
        stored = self.pin.stored
        self.market = dict(stored, supply_base=stored["supply_base"] if external else 0,
                           borrow_base=stored["borrow_base"] if external else 0,
                           totals={asset: self.pin.assets[asset]["customer_total"] if external else 0
                                   for asset in self.d.universe})
        self.kind = market
        self.prices = dict(USDC=self.pin.base_price)
        self.prices.update({asset: row["price"] for asset, row in self.pin.assets.items()})
        self.decimals = dict(E=6, USDC=6, ETH=18)
        self.decimals.update({asset: len(str(self.pin.assets[asset]["scale"])) - 1 for asset in self.d.universe})
        self.wallets = {("Comet", "USDC"): self.pin.cash if external else 0}
        self.wallets.update({("Comet", asset): self.pin.assets[asset]["custody"] if external else 0
                             for asset in self.d.universe})
        self.wallets.update(self.d.budgets)
        self.opening_external = dict(self.wallets)
        self.accounts, self.allowances, self.ramp_credit, self.points, self.opening = {}, {}, {}, {}, {}
        self.ledger, self.steps, self.rate_path, self.oracle_log, self.gas_log, self.ramp_log = [], [], [], [], [], []
        self.touch, self.tape_index = 1, 0
        self.tape = tuple((self.at(day), asset, ratio, label) for day, asset, ratio, label in self.d.oracle_tape)

    # ----- time map and marks ----------------------------------------------------------
    def at(self, day):
        """Model day -> chain second: day 0 is one slot after the pinned block; times must be whole seconds."""
        seconds = Fraction(str(day)) * DAY
        if seconds.denominator != 1:
            raise ValueError("model times must map to whole chain seconds")
        return self.pin.timestamp + self.d.slot + int(seconds)

    def day_of(self, timestamp):
        """Inverse of ``at`` for reporting."""
        return float(Fraction(timestamp - self.pin.timestamp - self.d.slot, DAY))

    def mark(self, asset, raw):
        """USD mark at the current oracle answers; E is the USD-par fixture unit, ETH uses WETH."""
        if asset == "E":
            return Fraction(raw, BASE)
        if asset == "USDC":
            return Fraction(raw * self.prices["USDC"], BASE * PRICE)
        listed = "WETH" if asset == "ETH" else asset
        return Fraction(raw * self.prices[listed], self.pin.assets[listed]["scale"] * PRICE)

    def balance(self, owner, asset):
        """Raw wallet balance of one named account."""
        return self.wallets.get((owner, asset), 0)

    def totals(self):
        """Sum of every named account by asset (BURN included once it exists)."""
        out = dict.fromkeys(self.decimals, 0)
        for (_, asset), value in self.wallets.items():
            out[asset] = out.get(asset, 0) + value
        return out

    # ----- wallets, gas and transactions --------------------------------------------------------
    def _move(self, t, event, asset, payer, recipient, raw, ref=""):
        """One actual transfer with a named payer and recipient; no account may go below zero."""
        if raw < 0 or self.balance(payer, asset) < raw:
            raise Revert(f"unfunded {event}: {payer} holds {self.balance(payer, asset)} {asset}, needs {raw}")
        self.wallets[(payer, asset)] = self.balance(payer, asset) - raw
        self.wallets[(recipient, asset)] = self.balance(recipient, asset) + raw
        self.ledger.append(dict(seq=len(self.ledger) + 1, day=self.day_of(t), timestamp=t, event=event, asset=asset,
                                payer=payer, recipient=recipient, raw=raw,
                                amount=str(Decimal(raw) / Decimal(10 ** self.decimals[asset])),
                                usd_mark=f"{float(self.mark(asset, raw)):.6f}", fixture_ref=ref))

    def gas_wei(self, op):
        """Gas cost of one submitted transaction at the pinned base fee (DECLARED units)."""
        return self.d.gas_units[op] * (self.pin.base_fee + self.d.priority_fee)

    def _pay_gas(self, t, who, op, note):
        """Burn the base fee from the sender's own ETH; the priority fee is declared zero."""
        wei = self.gas_wei(op)
        self._move(t, f"gas:{op}", "ETH", who, "BURN", wei, note)
        self.gas_log.append(dict(t=t, who=who, op=op, units=self.d.gas_units[op], wei=wei,
                                 usd=float(self.mark("ETH", wei)), weth_price_1e8=self.prices["WETH"]))

    def _save(self):
        """Everything one transaction may change, for an atomic rollback."""
        return (copy.deepcopy(self.market), copy.deepcopy(self.accounts), dict(self.wallets), dict(self.allowances),
                dict(self.ramp_credit), copy.deepcopy(self.points), len(self.ledger), len(self.ramp_log))

    def _restore(self, saved):
        """Undo a failed transaction completely."""
        market, accounts, wallets, allowances, credit, points, ledger, ramp = saved
        self.market, self.accounts, self.wallets, self.allowances = market, accounts, wallets, allowances
        self.ramp_credit, self.points = credit, points
        del self.ledger[ledger:]
        del self.ramp_log[ramp:]

    def _transaction(self, t, who, op, note, preflight, body, label=None):
        """Run ``body`` atomically. Gas: preflight rejection pays nothing; a submitted revert pays gas only."""
        self.advance(t)
        wei = self.gas_wei(op)
        if self.balance(who, "ETH") < wei:
            return Receipt("rejected", "insufficient ETH for gas")
        saved = self._save()
        try:
            result = body()
        except Revert as error:
            self._restore(saved)
            if preflight:
                return Receipt("rejected", str(error))
            self._pay_gas(t, who, op, note)
            return Receipt("reverted", str(error), wei)
        self._pay_gas(t, who, op, note)
        if label:
            self.snapshot(label(result) if callable(label) else label, t)
        return Receipt("ok", None, wei, result)

    def _paused(self, key):
        """Pinned pause flag for one action family."""
        if self.pin.paused[key]:
            raise Revert("Paused")

    def _take_allowance(self, owner, spender, asset, amount):
        """ERC-20 transferFrom allowance, consumed exactly (exact-amount approvals)."""
        allowed = self.allowances.get((owner, spender, asset), 0)
        if allowed < amount:
            raise Revert(f"transferFrom: allowance {allowed} < {amount}")
        self.allowances[(owner, spender, asset)] = allowed - amount

    # ----- SOURCE: indices, rates, principals -----------------------------------------------
    def utilisation(self, market=None):
        """getUtilization from stored indices (does not accrue first)."""
        m = market or self.market
        supplied = m["supply_base"] * m["supply_index"] // INDEX
        borrowed = m["borrow_base"] * m["borrow_index"] // INDEX
        return 0 if supplied == 0 else borrowed * FACTOR // supplied

    def rates(self, market=None):
        """(supply, borrow) per-second rates at the stored utilisation."""
        u = self.utilisation(market)
        return rate(u, self.pin.supply_curve), rate(u, self.pin.borrow_curve)

    def indices_at(self, now, market=None):
        """accruedInterestIndices: both sides from the same pre-accrual utilisation."""
        if now > self.at(self.d.horizon_days):
            raise ValueError("time exceeds the explicit scenario horizon")
        m = market or self.market
        elapsed = now - m["last"]
        if elapsed < 0:
            raise ValueError("time cannot run backwards")
        if elapsed == 0:
            return m["supply_index"], m["borrow_index"]
        supply_rate, borrow_rate = self.rates(m)
        si = m["supply_index"] + mul_factor(m["supply_index"], supply_rate * elapsed)
        bi = m["borrow_index"] + mul_factor(m["borrow_index"], borrow_rate * elapsed)
        if max(si, bi) >= 2**64:
            raise Revert("safe64")
        return si, bi

    def _accrue(self, now):
        """accrueInternal, including the zero-speed reward tracking update."""
        m = self.market
        elapsed = now - m["last"]
        if elapsed > 0:
            m["supply_index"], m["borrow_index"] = self.indices_at(now)
            if m["supply_base"] >= self.pin.min_rewards:
                m["track_supply"] += self.pin.speeds[0] * elapsed * BASE // m["supply_base"]
            if m["borrow_base"] >= self.pin.min_rewards:
                m["track_borrow"] += self.pin.speeds[1] * elapsed * BASE // m["borrow_base"]
            m["last"] = now

    def present_value(self, principal):
        """presentValue at stored indices: supply floors; debt magnitude floors."""
        if principal >= 0:
            return principal * self.market["supply_index"] // INDEX
        return -((-principal) * self.market["borrow_index"] // INDEX)

    def principal_value(self, balance):
        """principalValue at stored indices: supply rounds down; debt magnitude rounds up."""
        if balance >= 0:
            return balance * INDEX // self.market["supply_index"]
        bi = self.market["borrow_index"]
        return -((-balance * INDEX + bi - 1) // bi)

    def _update_principal(self, account, new):
        """updateBasePrincipal: reward accrual with the pinned tracking speeds (zero at the pin)."""
        m, old = self.market, account["principal"]
        delta = (m["track_supply"] if old >= 0 else m["track_borrow"]) - account["track_index"]
        account["track_accrued"] += abs(old) * delta // self.pin.tracking_scale // self.pin.descale
        account["principal"] = new
        account["track_index"] = m["track_supply"] if new >= 0 else m["track_borrow"]

    def balance_of(self, name, now):
        """balanceOf: projected positive base balance of a Comet account."""
        si, _ = self.indices_at(now)
        principal = self.accounts[name]["principal"]
        return principal * si // INDEX if principal > 0 else 0

    def borrow_balance_of(self, name, now):
        """borrowBalanceOf: projected debt magnitude of a Comet account."""
        _, bi = self.indices_at(now)
        principal = self.accounts[name]["principal"]
        return (-principal) * bi // INDEX if principal < 0 else 0

    def reserves(self, now):
        """getReserves: physical cash minus projected supply plus projected borrowing (may be negative)."""
        si, bi = self.indices_at(now)
        m = self.market
        return self.balance("Comet", "USDC") - m["supply_base"] * si // INDEX + m["borrow_base"] * bi // INDEX

    def collateral_reserves(self, asset):
        """getCollateralReserves: custody minus customer collateral (protocol inventory)."""
        return self.balance("Comet", asset) - self.market["totals"][asset]

    # ----- SOURCE: collateral gates ------------------------------------------------------------
    def collateral_value(self, account, factor):
        """Sum of individually floored factor-weighted USD values of the account's held collateral."""
        held = account["collateral"]
        return sum(mul_factor(held[asset] * self.prices[asset] // self.pin.assets[asset]["scale"],
                              self.pin.assets[asset][factor]) for asset in held if held[asset] > 0)

    def liquidity(self, name, factor, account=None):
        """Signed USD-1e8 liquidity: debt at the base oracle plus factor-weighted collateral."""
        account = account or self.accounts[name]
        debt = sdiv(self.present_value(account["principal"]) * self.prices["USDC"], BASE)
        return debt + self.collateral_value(account, factor)

    def collateralised(self, name, account=None):
        """isBorrowCollateralized."""
        account = account or self.accounts[name]
        return account["principal"] >= 0 or self.liquidity(name, "borrow_cf", account) >= 0

    def liquidatable(self, name):
        """isLiquidatable: strict inequality; a positive principal is never liquidatable."""
        account = self.accounts[name]
        return account["principal"] < 0 and self.liquidity(name, "liquidate_cf") < 0

    def borrow_capacity(self, name):
        """USDC raw a collateral holder could owe at the borrow factor and current oracle answers."""
        return self.collateral_value(self.accounts[name], "borrow_cf") * BASE // self.prices["USDC"]

    def quote(self, asset, base_amount):
        """quoteCollateral with the storefront discount."""
        row = self.pin.assets[asset]
        discount = mul_factor(self.pin.storefront, FACTOR - row["liquidation_factor"])
        discounted = mul_factor(self.prices[asset], FACTOR - discount)
        return self.prices["USDC"] * base_amount * row["scale"] // discounted // BASE

    def withdraw_gate(self, account, amount, cash):
        """Source failure order for withdrawBase on accrued indices; None means the gates pass."""
        balance = self.present_value(account["principal"]) - amount
        trial = dict(account, principal=self.principal_value(balance))
        if balance < 0 and -balance < self.pin.borrow_min:
            return "BorrowTooSmall"
        if balance < 0 and not self.collateralised(None, trial):
            return "NotCollateralized"
        if cash < amount:
            return "TransferOutFailed: market cash"
        return None

    # ----- background market, oracle tape, opening composition ------------------------------------
    def advance(self, until):
        """Run background accrual touches (day boundaries) and declared oracle updates up to ``until``."""
        if until > self.at(self.d.horizon_days):
            raise ValueError("time exceeds the explicit scenario horizon")
        while True:
            touch = self.at(self.touch) if self.touch <= self.d.horizon_days else None
            update = self.tape[self.tape_index][0] if self.tape_index < len(self.tape) else None
            touch_due = touch is not None and touch <= until
            update_due = update is not None and update <= until
            if not (touch_due or update_due):
                return
            if touch_due and (not update_due or touch <= update):   # same second: accrual touch first
                self._accrue(touch)
                u = self.utilisation()
                supply_rate, borrow_rate = self.rates()
                self.rate_path.append(dict(day=self.touch, utilisation=u / FACTOR,
                                           supply_apr_pct=supply_rate * YEAR / FACTOR * 100,
                                           borrow_apr_pct=borrow_rate * YEAR / FACTOR * 100))
                self.touch += 1
            else:
                timestamp, asset, ratio, label = self.tape[self.tape_index]
                self.set_price(timestamp, asset, self.pin.assets[asset]["price"] * ratio.numerator // ratio.denominator,
                               label)
                self.tape_index += 1

    def set_price(self, t, asset, raw, label):
        """Dated oracle answer, visible from its block; no freshness screen (the pinned Comet has none)."""
        if raw <= 0:
            raise Revert("BadPrice")
        self.oracle_log.append(dict(day=self.day_of(t), timestamp=t, asset=asset, before_1e8=self.prices[asset],
                                    after_1e8=raw, label=label))
        self.prices[asset] = raw

    def composition(self, wealth):
        """Split of opening marked wealth (micro-dollars) at the pinned answer: (E, WETH, ETH)."""
        p0 = self.pin.assets["WETH"]["price"]
        weth = (wealth * self.d.phi.numerator // self.d.phi.denominator) * (PRICE // BASE) * WEI // p0
        weth_mark = weth * p0 // WEI // (PRICE // BASE)
        eth_mark = self.d.eth_float * p0 // WEI // (PRICE // BASE)
        return dict(E=wealth - weth_mark - eth_mark, WETH=weth, ETH=self.d.eth_float, WETH_mark=weth_mark,
                    ETH_mark=eth_mark)

    def open_household(self, name, wealth):
        """Endow one household with the opening composition and open its fresh Comet account (no entitlement)."""
        if name in self.accounts or self.balance(name, "E"):
            raise ValueError(f"{name} is already open")
        parts = self.composition(wealth)
        self.wallets.update({(name, "E"): parts["E"], (name, "WETH"): parts["WETH"], (name, "ETH"): parts["ETH"],
                             (name, "USDC"): 0})
        self.accounts[name] = dict(principal=0, collateral=dict.fromkeys(self.d.universe, 0), track_index=0,
                                   track_accrued=0)
        self.opening[name] = dict(E=parts["E"], WETH=parts["WETH"], ETH=parts["ETH"])
        return parts

    # ----- native transactions (SOURCE gates; DECLARED gas) -------------------------------------
    def approve(self, t, owner, spender, asset, amount, note="", preflight=True):
        """ERC-20 approve: overwrite the allowance with an exact amount (one gas-paying transaction)."""
        def body():
            """Set the allowance."""
            self.allowances[(owner, spender, asset)] = amount
            return amount
        return self._transaction(t, owner, "approve", note, preflight, body)

    def supply_collateral(self, t, who, asset, amount, ref="", preflight=True):
        """supply(asset): transferFrom into custody, customer total, supply cap; no accrual (source order)."""
        def body():
            """Custody and cap."""
            self._paused("supply")
            if asset not in self.d.universe:
                raise Revert("asset outside the chosen universe")
            self._take_allowance(who, "Comet", asset, amount)
            self._move(t, "supplyCollateral", asset, who, "Comet", amount, ref)
            self.market["totals"][asset] += amount
            if self.market["totals"][asset] > self.pin.assets[asset]["supply_cap"]:
                raise Revert("SupplyCapExceeded")
            self.accounts[who]["collateral"][asset] += amount
            return amount
        return self._transaction(t, who, "supply_collateral", "", preflight, body,
                                 f"{who} supplies {asset} collateral")

    def withdraw_collateral(self, t, who, asset, amount, ref="", preflight=True):
        """withdrawCollateral: no interest accrual call (source order); must stay borrow-collateralised."""
        def body():
            """Custody release under the borrow gate."""
            self._paused("withdraw")
            account = self.accounts[who]
            if account["collateral"][asset] < amount:
                raise Revert("collateral underflow")
            account["collateral"][asset] -= amount
            self.market["totals"][asset] -= amount
            if not self.collateralised(who):
                raise Revert("NotCollateralized")
            self._move(t, "withdrawCollateral", asset, "Comet", who, amount, ref)
            return amount
        return self._transaction(t, who, "withdraw_collateral", "", preflight, body,
                                 f"{who} withdraws {asset} collateral")

    def withdraw_base(self, t, who, to, amount, ref="", preflight=True):
        """withdrawTo: accrue, consume a claim before borrowing, gates, then actual USDC to the named recipient."""
        def body():
            """Signed balance update and transfer out."""
            self._paused("withdraw")
            value = self.balance_of(who, t) if amount == MAX else amount
            self._accrue(t)
            account = self.accounts[who]
            failure = self.withdraw_gate(account, value, self.balance("Comet", "USDC"))
            if failure:
                raise Revert(failure)
            old = account["principal"]
            new = self.principal_value(self.present_value(old) - value)
            withdrawn, borrowed = withdraw_and_borrow(old, new)
            self.market["supply_base"] -= withdrawn
            self.market["borrow_base"] += borrowed
            self._update_principal(account, new)
            self._move(t, "withdrawTo", "USDC", "Comet", to, value, ref)
            if to == self.d.ramp:
                self.ramp_credit[who] = self.ramp_credit.get(who, 0) + value
            return value
        return self._transaction(t, who, "withdraw_base", "", preflight, body,
                                 lambda value: f"{who} withdraws {value / BASE} USDC to {to}")

    def supply_base(self, t, who, dst, amount, ref="", preflight=True):
        """supply/supplyTo base: repay debt before creating a claim; MAX repays the projected debt."""
        def body():
            """transferFrom, accrue and signed balance update."""
            self._paused("supply")
            value = self.borrow_balance_of(dst, t) if amount == MAX else amount
            self._take_allowance(who, "Comet", "USDC", value)
            self._move(t, "supply", "USDC", who, "Comet", value, ref)
            self._accrue(t)
            account = self.accounts[dst]
            old = account["principal"]
            new = self.principal_value(self.present_value(old) + value)
            repaid, supplied = repay_and_supply(old, new)
            self.market["supply_base"] += supplied
            self.market["borrow_base"] -= repaid
            self._update_principal(account, new)
            return dict(amount=value, repaid_principal=repaid, supplied_principal=supplied, debtor=old < 0)
        return self._transaction(t, who, "supply_base", "", preflight, body,
                                 lambda r: f"{who} {'repays' if r['debtor'] else 'supplies'} {r['amount'] / BASE} USDC")

    def absorb(self, t, absorber, names, preflight=True):
        """absorb: accrue once, then settle each named account in order; any non-liquidatable account reverts all."""
        def body():
            """Sequential absorption; settlement of one account changes totals seen by the next."""
            self._paused("absorb")
            reserves_before, cash_before = self.reserves(t), self.balance("Comet", "USDC")
            self._accrue(t)
            records = []
            for name in names:
                records.append(self._absorb_one(name))
            points = self.points.setdefault(absorber, dict(numAbsorbs=0, numAbsorbed=0, approxSpend_wei=0))
            points.update(numAbsorbs=points["numAbsorbs"] + 1, numAbsorbed=points["numAbsorbed"] + len(names),
                          approxSpend_wei=points["approxSpend_wei"]
                          + (self.d.gas_units["absorb"] - INTRINSIC_GAS) * self.pin.base_fee)
            return dict(accounts=records, reserves_before=reserves_before, reserves_after=self.reserves(t),
                        cash_change=self.balance("Comet", "USDC") - cash_before)
        return self._transaction(t, absorber, "absorb", "", preflight, body, f"{absorber} absorbs {', '.join(names)}")

    def _absorb_one(self, name):
        """absorbInternal: seize all collateral, credit liquidationFactor value at the base price, clamp at zero."""
        if not self.liquidatable(name):
            raise Revert("NotLiquidatable")
        account = self.accounts[name]
        old = account["principal"]
        old_balance, margin = self.present_value(old), self.liquidity(name, "liquidate_cf")
        seized = {asset: amount for asset, amount in account["collateral"].items() if amount > 0}
        value = {asset: amount * self.prices[asset] // self.pin.assets[asset]["scale"] for asset, amount in seized.items()}
        delta_value = sum(mul_factor(value[asset], self.pin.assets[asset]["liquidation_factor"]) for asset in value)
        delta_balance = delta_value * BASE // self.prices["USDC"]
        new_balance = max(0, old_balance + delta_balance)
        new = self.principal_value(new_balance)
        self._update_principal(account, new)
        account["collateral"] = dict.fromkeys(self.d.universe, 0)
        self.market["totals"].update({asset: self.market["totals"][asset] - seized[asset] for asset in seized})
        repaid, supplied = repay_and_supply(old, new)
        self.market["supply_base"] += supplied
        self.market["borrow_base"] -= repaid
        return dict(name=name, debt=-old_balance, margin=margin, seized=seized, value=value, delta_value=delta_value,
                    delta_balance=delta_balance, old_balance=old_balance, new_balance=new_balance, principal_after=new,
                    new_claim=self.present_value(new))

    def buy_collateral(self, t, buyer, asset, min_amount, base_amount, recipient, ref="", preflight=True):
        """buyCollateral: reserve gate before purchase (no accrual), funded buyer, quote, slippage, inventory."""
        def body():
            """Payment in, collateral out."""
            self._paused("buy")
            before = self.reserves(t)
            if before >= 0 and before >= self.pin.target_reserves:
                raise Revert("NotForSale")
            self._take_allowance(buyer, "Comet", "USDC", base_amount)
            self._move(t, "buyCollateral payment", "USDC", buyer, "Comet", base_amount, ref)
            amount = self.quote(asset, base_amount)
            if amount < min_amount:
                raise Revert("TooMuchSlippage")
            if amount > self.collateral_reserves(asset):
                raise Revert("InsufficientReserves")
            self._move(t, "buyCollateral delivery", asset, "Comet", recipient, amount, ref)
            return dict(paid=base_amount, received=amount, reserves_before=before, reserves_after=self.reserves(t))
        return self._transaction(t, buyer, "buy_collateral", "", preflight, body, f"{buyer} buys protocol {asset}")

    # ----- outside counterparties --------------------------------------------------------
    def ramp_fee(self, gross):
        """Equal-tariff convention: fixed plus rate, rounded up to the micro-dollar."""
        variable = gross * self.d.ramp_rate
        return self.d.ramp_fixed + -(-variable.numerator // variable.denominator)

    def off_ramp(self, t, who, usdc, ref=""):
        """Off-chain: the ramp pays E at the USDC oracle mark minus its fee for USDC it already received for ``who``."""
        saved = self._save()
        try:
            if self.ramp_credit.get(who, 0) < usdc:
                raise Revert("off-ramp: USDC not delivered to the ramp for this household")
            gross = usdc * self.prices["USDC"] // PRICE
            fee = self.ramp_fee(gross)
            self._move(t, "off-ramp payout", "E", self.d.ramp, who, gross - fee, ref)
            self.ramp_credit[who] -= usdc
        except Revert as error:
            self._restore(saved)
            return Receipt("rejected", str(error))
        self.ramp_log.append(dict(t=t, who=who, kind="off-ramp", usdc=usdc, gross_e=gross, fee_e=fee))
        return Receipt("ok", None, 0, gross - fee)

    def on_ramp(self, t, who, usdc, ref="", preflight=True):
        """Household pays E (mark rounded up plus fee); the ramp delivers USDC on-chain and pays its own gas."""
        def body():
            """E in, USDC out."""
            gross = -(-usdc * self.prices["USDC"] // PRICE)
            fee = self.ramp_fee(gross)
            self._move(t, "on-ramp payment", "E", who, self.d.ramp, gross + fee, ref)
            self._move(t, "on-ramp delivery", "USDC", self.d.ramp, who, usdc, ref)
            self.ramp_log.append(dict(t=t, who=who, kind="on-ramp", usdc=usdc, gross_e=gross, fee_e=fee))
            return gross + fee
        return self._transaction(t, self.d.ramp, "erc20_transfer", f"delivery to {who}", preflight, body)

    def dex_quote(self, asset, amount, price=None):
        """DECLARED USDC out for selling ``amount`` at the given or current oracle answer."""
        return dex_out(amount, price or self.prices[asset], self.prices["USDC"], self.pin.assets[asset]["scale"],
                       self.d.dex_fee)

    def dex_sell(self, t, who, asset, amount, ref="", preflight=True):
        """Sell collateral tokens to the funded pool D (allowance consumed); USDC to the seller."""
        def body():
            """Swap in, swap out."""
            out = self.dex_quote(asset, amount)
            self._take_allowance(who, self.d.dex, asset, amount)
            self._move(t, "DEX swap in", asset, who, self.d.dex, amount, ref)
            self._move(t, "DEX swap out", "USDC", self.d.dex, who, out, ref)
            return out
        return self._transaction(t, who, "dex_swap", "", preflight, body)

    # ----- liquidation service --------------------------------------------------------------
    def keeper(self, t_update, ref_prefix="absorbed:"):
        """After an oracle update: K observes all accounts after the declared delay and absorbs any
        liquidatable ones; U buys the seized collateral one slot later and resells it to D.

        No profitability screen (declared for the tiny case); points are never cash.
        Every leg is a funded transaction whose receipt is returned.
        """
        asset, slot = self.d.universe[0], self.d.slot
        t_obs = t_update + self.d.observation_delay
        self.advance(t_obs)
        seen = {name: self.liquidatable(name) for name in self.accounts}
        targets = [name for name, flag in seen.items() if flag]
        record = dict(t_obs=t_obs, seen=seen)
        if not targets:
            return record
        record["absorb"] = absorbed = self.absorb(t_obs, self.d.absorber, targets)
        if not absorbed.ok:
            return record
        seized = sum(row["seized"].get(asset, 0) for row in absorbed.result["accounts"])
        row = self.pin.assets[asset]
        base = purchase_size(seized, self.prices[asset], self.prices["USDC"], row["scale"], row["liquidation_factor"],
                             self.pin.storefront)
        ref = ref_prefix + "+".join(targets)
        self.approve(t_obs, self.d.buyer, "Comet", "USDC", base, "USDC allowance for Comet purchase")
        record["buy"] = bought = self.buy_collateral(t_obs + slot, self.d.buyer, asset, self.quote(asset, base), base,
                                                     self.d.buyer, ref)
        if not bought.ok:
            return record
        received = bought.result["received"]
        self.approve(t_obs + 2 * slot, self.d.buyer, self.d.dex, asset, received, f"{asset} allowance for DEX")
        record["resale"] = self.dex_sell(t_obs + 3 * slot, self.d.buyer, asset, received, ref)
        return record

    # ----- reporting -------------------------------------------------------------------------------
    def snapshot(self, label, t):
        """State after a step: positions and gates at stored indices, claims and debt projected to ``t``."""
        positions, asset = {}, self.d.universe[0]
        for name, account in self.accounts.items():
            debtor = account["principal"] < 0
            positions[name] = dict(principal=account["principal"], supply_claim_usdc=self.balance_of(name, t) / BASE,
                                   debt_usdc=self.borrow_balance_of(name, t) / BASE,
                                   borrow_liquidity_usd=self.liquidity(name, "borrow_cf") / PRICE if debtor else None,
                                   liquidation_liquidity_usd=(self.liquidity(name, "liquidate_cf") / PRICE
                                                              if debtor else None),
                                   reward_accrued=account["track_accrued"])
            positions[name][f"{asset.lower()}_collateral"] = account["collateral"][asset]
        supply_rate, borrow_rate = self.rates()
        row = dict(step=label, day=self.day_of(t), timestamp=t, usdc_price=self.prices["USDC"] / PRICE,
                   utilisation_stored=self.utilisation() / FACTOR, borrow_apr_pct=borrow_rate * YEAR / FACTOR * 100,
                   market_cash_usdc=self.balance("Comet", "USDC") / BASE, reserves_usdc=self.reserves(t) / BASE,
                   households=positions)
        row.update({f"{asset.lower()}_price": self.prices[asset] / PRICE for asset in self.d.universe})
        row.update({f"protocol_{asset.lower()}_inventory": self.collateral_reserves(asset)
                    / self.pin.assets[asset]["scale"] for asset in self.d.universe})
        self.steps.append(row)
        return row

    def valuation(self, name, t):
        """Every household position once at current common marks (exact fractions); debt is not netted away."""
        account = self.accounts[name]
        rows = dict(E=self.mark("E", self.balance(name, "E")), USDC_wallet=self.mark("USDC", self.balance(name, "USDC")))
        rows.update({f"{asset}_wallet": self.mark(asset, self.balance(name, asset)) for asset in self.d.universe})
        rows.update(ETH=self.mark("ETH", self.balance(name, "ETH")))
        rows.update({f"{asset}_collateral": self.mark(asset, amount) for asset, amount in account["collateral"].items()})
        rows.update(comet_supply_claim=self.mark("USDC", self.balance_of(name, t)),
                    comet_debt=-self.mark("USDC", self.borrow_balance_of(name, t)))
        opening = sum(self.mark(asset, amount) for asset, amount in self.opening[name].items())
        return rows, opening

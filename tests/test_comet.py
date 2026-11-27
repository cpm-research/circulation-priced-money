"""Standalone Comet source/transaction checks retained without an ABM import.

Origins: pre-reset checks_compound_spec.input_identity; checks_comet
pinned_state, revert_versus_preflight_gas, source_gates and
closed_market_reverts_first_draw. Historical Declared values are confined to
the named test fixture, not the new study's economic baseline. The module also holds
independent checks of explicit scenarios and the normal-time monetary normalization.
"""
import copy
from dataclasses import replace
import hashlib
import json
import unittest
from fractions import Fraction

from cpm_abm import comet
from cpm_abm.comet import BASE, INDEX
from tests.comet_fixtures import historical_cm03_scenario, normal_time_primitive_scenario


def require(receipt):
    """Require an actual committed transaction in a dated primitive fixture."""
    if not receipt.ok:
        raise AssertionError((receipt.status, receipt.reason))
    return receipt.result


def funded_actor(engine, name="actor"):
    """Open the historical 480-E unit fixture and post owned WETH with gas."""
    engine.open_household(name, 480*BASE)
    amount, at = engine.balance(name, "WETH"), engine.at(0.0)
    require(engine.approve(at, name, "Comet", "WETH", amount))
    require(engine.supply_collateral(at+engine.d.slot, name, "WETH", amount))
    return name


class CometTests(unittest.TestCase):
    """Check preserved source bytes, gates and funded transaction incidence."""

    def test_explicit_scenario_and_horizon_are_required(self):
        """Neither construction path can silently install historical scenario choices."""
        with self.assertRaises(TypeError):
            comet.Comet()
        with self.assertRaises(TypeError):
            comet.Comet(None)
        with self.assertRaises(TypeError):
            comet.Scenario()
        choices = dict(vars(historical_cm03_scenario()))
        choices.pop("horizon_days")
        with self.assertRaises(TypeError):
            comet.Scenario(**choices)
        with self.assertRaises(ValueError):
            normal_time_primitive_scenario(0)

    def test_normal_time_normalization_preserves_native_dimensions(self):
        """Scale source monetary quantities together; leave collateral, gas, time and curves native."""
        source = comet.load_pin()
        scenario = normal_time_primitive_scenario(200)
        engine = comet.Comet(scenario)
        pin = engine.pin
        self.assertEqual(scenario.monetary_scale, Fraction(1, 30))
        self.assertEqual(pin.borrow_min, source.borrow_min // 30)
        self.assertEqual(pin.borrow_min, 3_333_333)
        self.assertEqual(pin.target_reserves, source.target_reserves // 30)
        self.assertEqual(pin.min_rewards, source.min_rewards // 30)
        self.assertEqual(pin.cash, source.cash // 30)
        self.assertEqual(pin.stored["supply_base"], source.stored["supply_base"] // 30)
        self.assertEqual(pin.stored["borrow_base"], source.stored["borrow_base"] // 30)
        self.assertEqual(pin.base_price, source.base_price)
        self.assertEqual(pin.base_fee, source.base_fee)
        self.assertEqual(pin.timestamp, source.timestamp)
        self.assertEqual(pin.supply_curve, source.supply_curve)
        self.assertEqual(pin.borrow_curve, source.borrow_curve)
        self.assertEqual(pin.stored["supply_index"], source.stored["supply_index"])
        self.assertEqual(pin.stored["borrow_index"], source.stored["borrow_index"])
        self.assertEqual(pin.identities, source.identities)
        for asset, row in source.assets.items():
            self.assertEqual(pin.assets[asset], dict(row, price=row["price"] // 30))
        self.assertEqual(engine.balance("R", "E"), scenario.budgets[("R", "E")])
        self.assertEqual(engine.balance("R", "ETH"), 10**16)
        self.assertEqual(scenario.ramp_fixed, 210_000)
        self.assertEqual(engine.gas_wei("withdraw_base"), 140_000 * source.base_fee)
        elapsed = source.timestamp - pin.stored["last"]
        supply_rate, borrow_rate = engine.rates()
        supply_index = int(Fraction(pin.stored["supply_index"]) *
                           (1 + Fraction(supply_rate * elapsed, comet.FACTOR)))
        borrow_index = int(Fraction(pin.stored["borrow_index"]) *
                           (1 + Fraction(borrow_rate * elapsed, comet.FACTOR)))
        supplied = pin.stored["supply_base"] * supply_index // INDEX
        borrowed = pin.stored["borrow_base"] * borrow_index // INDEX
        self.assertEqual(pin.getters["total_supply"], supplied)
        self.assertEqual(pin.getters["total_borrow"], borrowed)
        self.assertEqual(pin.getters["reserves"], pin.cash - supplied + borrowed)
        self.assertEqual(engine.reserves(source.timestamp), pin.getters["reserves"])
        self.assertEqual(engine.utilisation(), pin.getters["utilisation"])
        self.assertEqual(engine.rates(), (pin.getters["supply_rate"], pin.getters["borrow_rate"]))
        self.assertEqual(source, comet.load_pin())

    def test_normal_time_tape_and_explicit_horizon(self):
        """Normal time stays flat past historical day 120; exceeding its own horizon fails before mutation."""
        engine = comet.Comet(normal_time_primitive_scenario(200))
        opening_prices = dict(engine.prices)
        engine.advance(engine.at(200))
        self.assertEqual(engine.d.oracle_tape, ())
        self.assertEqual(engine.oracle_log, [])
        self.assertEqual(engine.prices, opening_prices)
        self.assertEqual(len(engine.rate_path), 200)
        self.assertEqual(engine.rate_path[-1]["day"], 200)
        before = copy.deepcopy(engine.market)
        with self.assertRaises(ValueError):
            engine.advance(engine.at(201))
        with self.assertRaises(ValueError):
            engine.indices_at(engine.at(201))
        self.assertEqual(engine.market, before)
        self.assertEqual(len(engine.rate_path), 200)

    def test_normalized_minimum_still_gates_funded_draws(self):
        """A 25-model-E owner can use the scaled minimum without receiving collateral or gas gifts."""
        engine = comet.Comet(normal_time_primitive_scenario(30))
        parts = engine.open_household("actor", 25 * BASE)
        at = engine.at(0)
        require(engine.approve(at, "actor", "Comet", "WETH", parts["WETH"]))
        require(engine.supply_collateral(at + engine.d.slot, "actor", "WETH", parts["WETH"]))
        before = engine.balance("actor", "ETH")
        self.assertEqual(engine.withdraw_base(engine.at(1), "actor", "R", engine.pin.borrow_min - 1).reason,
                         "BorrowTooSmall")
        require(engine.withdraw_base(engine.at(1), "actor", "R", 5 * BASE))
        self.assertEqual(engine.balance("actor", "ETH"), before - engine.gas_wei("withdraw_base"))
        self.assertEqual(engine.accounts["actor"]["collateral"]["WETH"], parts["WETH"])
        self.assertGreater(engine.borrow_balance_of("actor", engine.at(1)), 0)

    def test_named_historical_fixture_keeps_its_stress_tape(self):
        """Only the explicit named fixture carries the historical day-8 shock and day-50 recovery."""
        engine = comet.Comet(historical_cm03_scenario())
        initial = engine.prices["WETH"]
        engine.advance(engine.at(9))
        self.assertEqual(engine.pin.borrow_min, 100 * BASE)
        self.assertEqual(engine.oracle_log[0]["day"], 8)
        self.assertEqual(engine.prices["WETH"], initial * 8 // 10)
        engine.advance(engine.at(50))
        self.assertEqual(engine.prices["WETH"], initial)
        self.assertEqual(engine.oracle_log[1]["day"], 50)

    def test_pinned_input_manifest_and_implementation_identity(self):
        """Every source-file digest and deployed implementation identity matches the preserved pin."""
        data = comet.DATA
        manifest_bytes = (data/"sha256_manifest.json").read_bytes()
        self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(),
                         "3e27213d2b1936a5a034f91d590be2e7890662c99f33ca5ca034845e5e239677")
        manifest = json.loads(manifest_bytes)
        for name, expected in manifest.items():
            self.assertEqual(hashlib.sha256((data/name).read_bytes()).hexdigest(), expected, name)
        snapshot = json.loads((data/"snapshot.json").read_bytes())
        verified = json.loads((data/"verified_source_1.json").read_bytes())
        runtime = bytes.fromhex(verified["deployed_bytecode"].removeprefix("0x"))
        self.assertEqual(hashlib.sha256(runtime).hexdigest(), snapshot["code_sha256"]["implementation_runtime"])
        self.assertEqual(snapshot["chain_id"], 1)
        self.assertEqual(snapshot["block"], 26_214_368)
        self.assertEqual(snapshot["block_hash"], "0x3a282d5aceb3cc24dfaf339fabe2d89a879b64158311b4b9e7d13463b8c8158e")

    def test_pinned_getters_and_time_map(self):
        """The untouched market opens at the source rates, totals, reserves and collateral custody."""
        engine = comet.Comet(historical_cm03_scenario())
        pin, market = engine.pin, engine.market
        supply_index, borrow_index = engine.indices_at(pin.timestamp)
        self.assertEqual(engine.utilisation(), pin.getters["utilisation"])
        self.assertEqual(engine.rates(), (pin.getters["supply_rate"], pin.getters["borrow_rate"]))
        self.assertEqual(market["supply_base"]*supply_index//INDEX, pin.getters["total_supply"])
        self.assertEqual(market["borrow_base"]*borrow_index//INDEX, pin.getters["total_borrow"])
        self.assertEqual(engine.reserves(pin.timestamp), pin.getters["reserves"])
        self.assertEqual(engine.collateral_reserves("WETH"), pin.assets["WETH"]["inventory"])
        self.assertEqual(pin.speeds, (0, 0))
        self.assertFalse(any(pin.paused.values()))
        self.assertEqual(engine.at(0.0), pin.timestamp+12)
        self.assertEqual(engine.at(12.3)-engine.at(0.0), 1_062_720)

    def test_rejected_preflight_and_submitted_revert_gas(self):
        """A rejected preflight is pure; a submitted failing draw pays only actual gas."""
        engine = comet.Comet(historical_cm03_scenario())
        actor = funded_actor(engine)
        at = engine.at(1.0)
        engine.advance(at)
        wallets, market, rows = dict(engine.wallets), copy.deepcopy(engine.market), len(engine.ledger)
        rejected = engine.withdraw_base(at, actor, "R", 50*BASE)
        self.assertEqual((rejected.status, rejected.reason, rejected.gas_wei), ("rejected", "BorrowTooSmall", 0))
        self.assertEqual(engine.wallets, wallets)
        self.assertEqual(engine.market, market)
        self.assertEqual(len(engine.ledger), rows)
        reverted = engine.withdraw_base(at, actor, "R", 50*BASE, preflight=False)
        self.assertEqual(reverted.status, "reverted")
        self.assertEqual(reverted.gas_wei, engine.d.gas_units["withdraw_base"]*engine.pin.base_fee)
        self.assertEqual(engine.balance(actor, "ETH"), wallets[(actor,"ETH")]-reverted.gas_wei)
        self.assertEqual(len(engine.ledger), rows+1)
        self.assertEqual(engine.ledger[-1]["event"], "gas:withdraw_base")
        self.assertEqual(engine.accounts[actor]["principal"], 0)
        self.assertEqual(engine.market, market)
        poor = comet.Comet(replace(historical_cm03_scenario(), eth_float=0))
        poor.open_household("unfunded_gas", 100*BASE)
        no_gas = poor.approve(poor.at(0.0), "unfunded_gas", "Comet", "WETH", 1)
        self.assertEqual(no_gas.reason, "insufficient ETH for gas")
        self.assertFalse(poor.ledger)

    def test_borrow_minimum_collateral_and_signed_repayment(self):
        """Minimums gate new draws; partial repayment may leave less debt than the minimum."""
        engine = comet.Comet(historical_cm03_scenario())
        actor, at = funded_actor(engine), engine.at(1.0)
        capacity = engine.borrow_capacity(actor)
        self.assertEqual(engine.withdraw_base(at, actor, "R", 100*BASE-1).reason, "BorrowTooSmall")
        self.assertEqual(engine.withdraw_base(at, actor, "R", capacity+BASE).reason, "NotCollateralized")
        require(engine.withdraw_base(at, actor, "R", 100*BASE))
        collateral = engine.accounts[actor]["collateral"]["WETH"]
        self.assertEqual(engine.withdraw_collateral(at, actor, "WETH", collateral).reason, "NotCollateralized")
        require(engine.on_ramp(at, actor, 110*BASE))
        require(engine.approve(at, actor, "Comet", "USDC", 60*BASE))
        require(engine.supply_base(at, actor, actor, 60*BASE))
        partial = engine.borrow_balance_of(actor, at)
        self.assertGreater(partial, 0)
        self.assertLess(partial, engine.pin.borrow_min)
        require(engine.approve(at, actor, "Comet", "USDC", 50*BASE))
        require(engine.supply_base(at, actor, actor, 50*BASE))
        claim = engine.balance_of(actor, at)
        self.assertGreater(engine.accounts[actor]["principal"], 0)
        self.assertGreaterEqual((50*BASE-partial)-claim, 0)
        self.assertLessEqual((50*BASE-partial)-claim, 1)
        self.assertFalse(engine.liquidatable(actor))

    def test_supply_cap_pause_and_reserve_sale_gates(self):
        """Labelled pin variants exercise source guards without changing the preserved source pin."""
        pin = comet.load_pin()
        weth = pin.assets["WETH"]
        tight = replace(pin, assets=dict(pin.assets, WETH=dict(weth, supply_cap=weth["customer_total"])))
        capped = comet.Comet(historical_cm03_scenario(), pin=tight)
        capped.open_household("actor", 480*BASE)
        require(capped.approve(capped.at(0.0), "actor", "Comet", "WETH", 1))
        self.assertEqual(capped.supply_collateral(capped.at(0.0), "actor", "WETH", 1).reason, "SupplyCapExceeded")
        paused = comet.Comet(historical_cm03_scenario(), pin=replace(pin, paused=dict(pin.paused, withdraw=True)))
        paused.open_household("actor", 480*BASE)
        self.assertEqual(paused.withdraw_base(paused.at(0.0), "actor", "R", 100*BASE).reason, "Paused")
        not_for_sale = comet.Comet(historical_cm03_scenario(), pin=replace(pin, target_reserves=0))
        require(not_for_sale.approve(not_for_sale.at(0.0), "U", "Comet", "USDC", BASE))
        self.assertEqual(not_for_sale.buy_collateral(not_for_sale.at(0.0), "U", "WETH", 0, BASE, "U").reason, "NotForSale")

    def test_closed_market_cannot_manufacture_base_currency(self):
        """With no external supplier, collateral alone cannot fund the first base draw."""
        engine = comet.Comet(historical_cm03_scenario(), market="closed")
        actor, at = funded_actor(engine), engine.at(1.0)
        before = dict(engine.wallets)
        receipt = engine.withdraw_base(at, actor, "R", 170*BASE)
        self.assertEqual(receipt.status, "rejected")
        self.assertEqual(receipt.gas_wei, 0)
        self.assertEqual(engine.wallets, before)
        self.assertEqual(engine.accounts[actor]["principal"], 0)
        self.assertEqual(engine.balance("Comet", "USDC"), 0)

    def test_funded_draw_repayment_preserves_each_asset_total(self):
        """Actual collateral, borrow, ramp and repayment legs conserve tokens including burnt gas."""
        engine = comet.Comet(historical_cm03_scenario())
        engine.open_household("actor", 480*BASE)
        totals = engine.totals()
        at = engine.at(0.0)
        amount = engine.balance("actor", "WETH")
        require(engine.approve(at, "actor", "Comet", "WETH", amount))
        require(engine.supply_collateral(at+engine.d.slot, "actor", "WETH", amount))
        at = engine.at(1.0)
        require(engine.withdraw_base(at, "actor", "R", 100*BASE))
        require(engine.on_ramp(at, "actor", 110*BASE))
        require(engine.approve(at, "actor", "Comet", "USDC", 110*BASE))
        require(engine.supply_base(at, "actor", "actor", 110*BASE))
        require(engine.withdraw_collateral(at, "actor", "WETH", amount))
        self.assertEqual(engine.totals(), totals)
        self.assertGreaterEqual(min(engine.wallets.values()), 0)
        self.assertEqual(engine.borrow_balance_of("actor", at), 0)
        self.assertEqual(engine.balance("actor", "WETH"), amount)

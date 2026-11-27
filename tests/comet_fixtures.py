"""Named Comet unit fixtures; none is a research-economy scenario."""
from fractions import Fraction

from cpm_abm import comet
from cpm_abm.comet import BASE, WEI


def historical_cm03_scenario():
    """Historical declared values, including the stress tape.

    These choices qualify primitive transactions only. Production exposes
    neither this fixture nor implicit copies of its budgets, gas or horizon.
    """
    return comet.Scenario(
        universe=("WETH",), phi=Fraction(1, 2), eth_float=10**15,
        gas_units=dict(approve=46_000, supply_collateral=110_000, withdraw_base=140_000, supply_base=120_000,
                       withdraw_collateral=120_000, erc20_transfer=65_000, dex_swap=130_000,
                       absorb=110_000, buy_collateral=75_000),
        priority_fee=0, ramp_fixed=210_000, ramp_rate=Fraction(1, 2000), dex_fee=Fraction(3, 1000),
        observation_delay=3_600,
        budgets={("R", "E"): 10_000 * BASE, ("R", "USDC"): 10_000 * BASE, ("R", "ETH"): 10**16,
                 ("D", "WETH"): 100 * WEI, ("D", "USDC"): 250_000 * BASE,
                 ("K", "ETH"): 10**16, ("U", "USDC"): 1_000 * BASE, ("U", "ETH"): 10**16},
        oracle_tape=((8.0, "WETH", Fraction(8, 10), "DECLARED synthetic -20% update (stress tape), not a forecast"),
                     (50.0, "WETH", Fraction(1), "DECLARED synthetic recovery to the pinned answer (stress tape)")),
        slot=12, horizon_days=120, absorber="K", buyer="U", ramp="R", dex="D", monetary_scale=Fraction(1))


def normal_time_primitive_scenario(horizon_days):
    """Use explicit test-only funding/fees to exercise the normal-time scenario API.

    The budget choice scales historical E/USDC funding by 30; native token/gas
    endowments stay native. The explicit common model tariff is 0.21 E. These
    named test values do not select the pending research economy's funding.
    """
    historical = historical_cm03_scenario()
    choices = dict(vars(historical))
    choices.pop("oracle_tape")
    choices.pop("monetary_scale")
    choices["budgets"] = {key: raw // 30 if key[1] in ("E", "USDC") else raw
                          for key, raw in historical.budgets.items()}
    choices["horizon_days"] = horizon_days
    return comet.normal_time_scenario(**choices)

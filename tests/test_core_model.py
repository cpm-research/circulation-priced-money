"""Identity checks for the core adoption and circular-flow liquidity model (src/cpm_abm/core_model.py)."""
from dataclasses import replace
import unittest

import numpy as np

from cpm_abm.core_model import Inputs, adopt, cycle_profile, gains


class CoreModelTests(unittest.TestCase):
    """Check the October 2026 draft's identities, the S0 anchor and the emergent channels the region rests on."""

    def test_cycle_closes_and_grace_float_covers_s0(self):
        """Income equals outflows each cycle; with the card float S0 never runs short."""
        inputs = Inputs()
        z = cycle_profile([0.0, 0.5, 1.0], inputs)
        self.assertAlmostEqual(float(z[0, -1]), 0.0, places=2)
        self.assertGreaterEqual(float(z[0].min()), -1e-12)
        self.assertGreater(float(np.maximum(0.0, -z[2]).mean()), 0.0)

    def test_nobody_gains_or_loses_without_participation(self):
        """At A = 0 the economy is S0: every gain and the system total are zero."""
        inputs = Inputs()
        out = gains(inputs, [0.002, inputs.rho_H, 0.01], [0.0])
        for key in ("gain_participant", "gain_nonparticipant", "issuer", "delta_W", "completion_gain"):
            np.testing.assert_allclose(out[key][:, 0], 0.0, atol=1e-15)

    def test_coupon_is_flat_and_theta_matches_the_insurance_identity(self):
        """Coupon: r^g = rho_H + o; where the insurance charge binds, theta = k/(k + r^g) and the net rate is o."""
        inputs = Inputs()
        out = gains(inputs, [inputs.rho_H], np.linspace(0.3, 0.55, 6))
        r_g = inputs.rho_H + inputs.o
        np.testing.assert_allclose(out["r_g"][0], r_g)
        np.testing.assert_allclose(out["theta"][0], inputs.rho_H / (inputs.rho_H + r_g), rtol=1e-12)
        np.testing.assert_allclose(out["net_rate"][0], inputs.o, rtol=1e-12)

    def test_payers_without_a_positive_margin_do_not_set_the_charge(self):
        """Use bound: where provider fees exceed the credit saving (M_i <= 0), nobody is included and c = c_ins."""
        inputs = Inputs()
        out = gains(inputs, [inputs.rho_H], [0.95, 1.0])
        r_g = inputs.rho_H + inputs.o
        self.assertTrue(np.all(out["c"][0] > 0))
        np.testing.assert_allclose(out["theta"][0], inputs.rho_H / (inputs.rho_H + r_g), rtol=1e-12)
        np.testing.assert_allclose(out["net_rate"][0], inputs.o, rtol=1e-12)

    def test_readiness_threshold_is_where_fee_income_covers_fixed_cost(self):
        """m = alpha * card * A^2 * phi - C_fix > 0, with phi between S0 completion and one."""
        inputs = Inputs()
        card = (1 - inputs.housing) * inputs.card_share
        phi0 = float(gains(inputs, [inputs.rho_H], [0.0])["phi"][0, 0])
        low = np.sqrt(inputs.C_fix / (inputs.alpha * card))
        high = np.sqrt(inputs.C_fix / (inputs.alpha * card * phi0))
        out = gains(inputs, [inputs.rho_H], [low - 1e-3, high + 1e-3])
        self.assertEqual(list(out["ready"][0]), [False, True])

    def test_owners_earn_exactly_the_outside_return_at_rest(self):
        """Stable capacity (October 2026 draft): N = Pbar + m/rho_H and R(N) = rho_H under that draft's contract."""
        inputs = Inputs()
        out = gains(inputs, [inputs.rho_H], [0.5, 1.0])
        np.testing.assert_allclose(out["R"][0], inputs.rho_H, rtol=1e-12)

    def test_failed_payments_fall_with_adoption_and_spill_over_to_non_participants(self):
        """Emergent channel: once the pool is ready, failures fall with A and non-participants gain."""
        inputs = Inputs()
        share = np.linspace(0.3, 1.0, 15)
        out = gains(inputs, [inputs.rho_H], share)
        self.assertTrue(np.all(np.diff(out["failures"][0]) < 0))
        self.assertAlmostEqual(float(out["failures"][0, -1]), 0.0, places=12)
        self.assertTrue(np.all(out["gain_nonparticipant"][0] > 0))
        self.assertTrue(np.all(np.diff(out["delta_W"][0]) > 0))

    def test_merchant_fee_savings_are_excluded_unless_switched_on(self):
        """The fee saving is a transfer; switching it on adds exactly (f_card - rewards) x internal volume."""
        inputs = Inputs()
        share = np.array([0.5, 1.0])
        off = gains(inputs, [inputs.rho_H], share)
        on = gains(replace(inputs, merchant_fees=True), [inputs.rho_H], share)
        np.testing.assert_allclose(off["parts"]["merchant"], 0.0)
        card = (1 - inputs.housing) * inputs.card_share
        expected = (inputs.f_card - inputs.rewards) * card * share * off["phi"][0]
        np.testing.assert_allclose(on["gain_participant"][0] - off["gain_participant"][0], expected, rtol=1e-12)

    def test_pool_cash_what_if_redistributes_without_creating_value(self):
        """With full coverage in both, moving the idle-cash return from issuer to pool leaves delta_W unchanged."""
        inputs = Inputs()
        share = np.array([0.5, 0.75, 1.0])
        paper = gains(inputs, [inputs.rho_H], share)
        what_if = gains(replace(inputs, pool_cash_return=True), [inputs.rho_H], share)
        np.testing.assert_allclose(paper["sigma"][0], 1.0)
        np.testing.assert_allclose(what_if["delta_W"][0], paper["delta_W"][0], rtol=1e-10)
        self.assertTrue(np.all(what_if["issuer"][0] < paper["issuer"][0]))
        self.assertTrue(np.all(what_if["gain_participant"][0] > paper["gain_participant"][0]))

    def test_uncharged_control_equals_m1_when_buffers_are_released_in_both(self):
        """Neutrality (October 2026 draft): with the same quantities, the charge only redistributes inside the
        representative agent."""
        inputs = Inputs()
        share = np.linspace(0.0, 1.0, 21)
        charged = gains(inputs, [inputs.rho_H], share)
        control = gains(replace(inputs, arm="U"), [inputs.rho_H], share)
        self.assertTrue(np.all(charged["released"]) and np.all(control["released"]))
        np.testing.assert_allclose(control["c"], 0.0)
        for key in ("gain_participant", "gain_nonparticipant", "issuer", "delta_W", "phi"):
            np.testing.assert_allclose(control[key], charged[key], rtol=1e-12, atol=1e-15)

    def test_uncharged_control_keeps_buffers_when_bridges_are_long(self):
        """Experienced-cost rule: at the gross coupon, holding idle P becomes cheaper than bridging a 4-month need."""
        inputs = replace(Inputs(), term=4.0)
        self.assertFalse(bool(gains(replace(inputs, arm="U"), [inputs.rho_H], [1.0])["released"][0, 0]))
        self.assertTrue(bool(gains(inputs, [inputs.rho_H], [1.0])["released"][0, 0]))

    def test_m2_indexation_is_a_transfer_from_the_issuer(self):
        """With full coverage in both, M2 leaves delta_W unchanged and pays holders dJ/J on their P balances."""
        inputs = Inputs()
        share = np.array([0.5, 1.0])
        nominal = gains(inputs, [inputs.rho_H], share)
        indexed = gains(replace(inputs, arm="M2"), [inputs.rho_H], share)
        np.testing.assert_allclose(indexed["delta_W"], nominal["delta_W"], rtol=1e-10)
        self.assertTrue(np.all(indexed["parts"]["indexation"] > 0))
        self.assertTrue(np.all(indexed["issuer"] < nominal["issuer"]))

    def test_m2_issuer_loses_when_the_outside_return_is_below_inflation(self):
        """The issuer's reserve earns rho_H while indexed backing grows at dJ/J."""
        inputs = replace(Inputs(), arm="M2")
        out = gains(inputs, [0.5 * inputs.inflation, 2.0 * inputs.inflation], [0.5])
        self.assertLess(float(out["issuer"][0, 0]), 0.0)
        self.assertGreater(float(out["issuer"][1, 0]), 0.0)

    def test_m0_has_no_readiness_gate_and_bridges_only_with_collateral(self):
        """Comet is already open; without collateral failures rise with A, with it they vanish."""
        inputs = replace(Inputs(), arm="M0")
        bare = gains(inputs, [inputs.rho_H], [0.05, 1.0])
        self.assertGreater(float(bare["gain_participant"][0, 0]), 0.0)
        self.assertGreater(float(bare["failures"][0, 1]), float(bare["failures"][0, 0]))
        posted = gains(replace(inputs, collateral_cover=1.0), [inputs.rho_H], [1.0])
        self.assertAlmostEqual(float(posted["failures"][0, 0]), 0.0, places=12)

    def test_m0_gain_vanishes_when_s0_buffers_already_earn_the_outside_return(self):
        """Risk-adjusted Comet supply pays rho_H, so an efficient S0 leaves M0 only its costs."""
        inputs = replace(Inputs(), arm="M0", buffer_at_outside=True)
        out = gains(inputs, [inputs.rho_H], [0.5, 1.0])
        self.assertTrue(np.all(out["gain_participant"] < 0))

    def test_buffers_earn_yield_only_on_the_part_not_spent_on_needs(self):
        """S0 and every arm credit idle yield on buffer - term * used, and channels sum to the gain."""
        for change in ({}, dict(arm="M2"), dict(arm="M0"), dict(pool_cash_return=True)):
            inputs = replace(Inputs(), buffer_at_outside=True, **change)
            out = gains(inputs, [inputs.rho_H], [0.0, 0.5, 1.0])
            if change.get("arm", "M1") == "M1":
                np.testing.assert_allclose(out["gain_participant"][:, 0], 0.0, atol=1e-15)
            np.testing.assert_allclose(sum(out["parts"].values()), out["gain_participant"], atol=1e-15)
        s0 = gains(replace(Inputs(), buffer_at_outside=True), [Inputs().rho_H], [0.0])
        self.assertGreater(float(s0["buffer_use_e"][0, 0]), 0.0)

    def test_adoption_is_bistable_around_readiness(self):
        """Social entry with experiential exit: starts below readiness fall back, starts above it spread."""
        inputs = Inputs()
        path = adopt(inputs, [inputs.rho_H], [0.0, 0.2, 0.3], months=240)
        self.assertLess(float(path[-1, 0, 0]), 0.05)
        self.assertLess(float(path[-1, 0, 1]), 0.05)
        self.assertGreater(float(path[-1, 0, 2]), 0.95)


if __name__ == "__main__":
    unittest.main()

"""Tests for three engine settings of the second run, each a setting of ``Economy`` whose default is the first run's
rule, at small scale.

What is covered
---------------
* ``card_cut_months``: with the distress line cut on, the cut lines are lower from the cut until m months later and
  then back at their uncut level, the uncut twin's, for every line still open; a line charged off in the meantime
  stays closed; 0 (the default) is the first run's cut, never restored; a positive value without the cut is refused.
* ``usdc_yield``: at an outside rate of 4.4% a holder of M0's stablecoin earns 4.4% less the Sky spread under
  "reserve" (the default) and nothing under "none"; the issuer's kept spread record is the rest of the reserve return
  in both; no other arm moves.
* The gain split (``experiment.accounts.split``): under the conserved edge it carries a part for the money returned,
  so its parts add up to the gain; with the edge open its keys and values are the first run's.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import CARD_CUT, RESERVE_SPREAD, Economy, _World
from cpm_abm.engine.rates import m0_rates
from scripts.run_economy_population import split   # puts scripts/ on the path, as the accounts module needs
from run_economy_figures import DOLLARS  # noqa: E402

# A small world whose distress year covers months 3 to 5 of an eight-month run; the line cut falls in month 3.
SMALL = Economy(n=200, months=6, burn_in=2, distress_start=1, distress_length=3)
CUT = dict(distress=0.02, card_line_cut=True)
RATE = 0.044 / 12   # an outside rate of 4.4% a year, a month


def lines_by_month(world):
    """Run ``world`` and return, for each month, its card lines and open-line flags just after the month's cut."""
    cut_lines, seen = world._cut_lines, []

    def record(month):
        cut_lines(month)
        seen.append((month, world.card_line.copy(), world.holder.copy()))

    world._cut_lines = record
    world.run()
    return seen


class CardCutMonthsTests(unittest.TestCase):
    """The distress line cut lasts a stated time (``Economy.card_cut_months``)."""

    def test_lines_are_cut_for_m_months_and_then_match_the_uncut_twin(self):
        """With m = 2 the cut falls in month 3: every open line is below its uncut level in months 3 and 4 and back at
        it from month 5, where the uncut twin has had it all along, for every line open in both."""
        cut = SMALL.burn_in + SMALL.distress_start
        months = 2
        restored = lines_by_month(_World(Inputs(), 0.4, replace(SMALL, card_cut_months=months, **CUT), "S0"))
        twin = lines_by_month(_World(Inputs(), 0.4, replace(SMALL, distress=0.02), "S0"))
        uncut = _World(Inputs(), 0.4, SMALL, "S0").pop["card_line"]
        self.assertTrue(bool((uncut > 0).any()))
        for (month, line, open_), (_, twin_line, twin_open) in zip(restored, twin):
            both = open_ & twin_open
            np.testing.assert_array_equal(twin_line[twin_open], uncut[twin_open])
            if cut <= month < cut + months:
                self.assertTrue(bool(np.all(line[open_] < uncut[open_])), month)
            else:
                np.testing.assert_array_equal(line[both], twin_line[both], err_msg=str(month))
            np.testing.assert_array_equal(line[~open_], 0.0)

    def test_restoring_undoes_the_cut_and_leaves_a_closed_line_closed(self):
        """At 2% a line falls by its tier's cut (deep subprime 32.58%) and, m months later, is back where it was; a
        line closed by a charge-off between the two stays at zero. In other months nothing moves."""
        economy = replace(SMALL, card_cut_months=12, **CUT)
        w = _World(Inputs(), 0.4, economy, "S0")
        before = w.card_line.copy()
        cut = economy.burn_in + economy.distress_start
        w._cut_lines(cut)
        np.testing.assert_allclose(w.card_line, before * (1 - CARD_CUT[w.card_tier]), rtol=1e-15)
        closed = np.flatnonzero(w.holder)[0]
        w.holder[closed], w.card_line[closed] = False, 0.0   # as a charge-off closes it (``_charge_off``)
        w._cut_lines(cut + 11)
        w._cut_lines(cut + 13)
        np.testing.assert_allclose(w.card_line, np.where(w.holder, before * (1 - CARD_CUT[w.card_tier]), 0.0),
                                   rtol=1e-15)
        w._cut_lines(cut + 12)
        np.testing.assert_array_equal(w.card_line, np.where(w.holder, before, 0.0))
        self.assertEqual(w.card_line[closed], 0.0)

    def test_zero_months_is_the_cut_as_built(self):
        """The default is 0, and a run with it is the same, bit for bit, as one whose restoring month lies beyond the
        run, with every open line still cut at the end."""
        self.assertEqual(Economy().card_cut_months, 0)
        never = _World(Inputs(), 0.4, replace(SMALL, **CUT), "M1")
        late = _World(Inputs(), 0.4, replace(SMALL, card_cut_months=100, **CUT), "M1")
        a, b = never.run()["series"], late.run()["series"]
        for key in a:
            np.testing.assert_array_equal(a[key], b[key], err_msg=key)
        open_ = never.holder
        np.testing.assert_allclose(never.card_line[open_],
                                   (never.pop["card_line"] * (1 - CARD_CUT[never.card_tier]))[open_], rtol=1e-15)

    def test_settings_refuse_what_they_do_not_define(self):
        """A positive duration without the cut, a negative one, a fraction and a boolean are refused."""
        for bad in (dict(card_cut_months=120), dict(card_cut_months=-1, card_line_cut=True),
                    dict(card_cut_months=1.5, card_line_cut=True), dict(card_cut_months=True, card_line_cut=True)):
            with self.assertRaises(ValueError, msg=str(bad)):
                Economy(**bad)
        Economy(card_cut_months=120, card_line_cut=True)


class UsdcYieldTests(unittest.TestCase):
    """What M0's stablecoin pays its holder (``Economy.usdc_yield``)."""

    def test_the_hand_case_at_four_point_four_percent(self):
        """At 4.4% a year a holder earns 4.4% less the Sky spread (0.441 point) under "reserve" and nothing under
        "none"; the issuer keeps the spread and the whole 4.4% on each unit; Comet's borrow rate is the same in both."""
        reserve = _World(Inputs(rho_H=RATE), 0.4, SMALL, "M0")
        none = _World(Inputs(rho_H=RATE), 0.4, replace(SMALL, usdc_yield="none"), "M0")
        self.assertEqual(Economy().usdc_yield, "reserve")
        self.assertAlmostEqual(12 * RESERVE_SPREAD, 0.00441, places=5)
        self.assertAlmostEqual(reserve.p_yield, RATE - RESERVE_SPREAD, places=15)
        self.assertEqual(reserve.p_yield, m0_rates(RATE)[0])
        self.assertAlmostEqual(reserve.issuer_keeps, RESERVE_SPREAD, places=15)
        self.assertEqual(none.p_yield, 0.0)
        self.assertEqual(none.issuer_keeps, RATE)
        self.assertEqual(none.comet_borrow, reserve.comet_borrow)

    def test_the_issuers_record_is_the_rest_of_the_reserve_return(self):
        """Over a short run, under "none" nobody is paid a yield on USDC and the issuer's kept spread is the whole
        4.4% on the USDC held, each month; under "reserve" it is the Sky spread on it (to the day's timing of the
        credited yield)."""
        for mode, kept, rtol in (("none", RATE, 1e-12), ("reserve", RESERVE_SPREAD, 1e-3)):
            w = _World(Inputs(rho_H=RATE), 0.4, replace(SMALL, usdc_yield=mode), "M0")
            series = w.run()["series"]
            held = series["p_bt"][SMALL.burn_in:]
            self.assertTrue(bool(np.all(held > 0)), mode)
            np.testing.assert_allclose(series["issuer_spread"][SMALL.burn_in:], kept * held, rtol=rtol, err_msg=mode)
            if mode == "none":
                self.assertEqual(float(w.acc["p_yield"].sum()), 0.0)
            else:
                self.assertGreater(float(w.acc["p_yield"].sum()), 0.0)

    def test_no_other_arm_moves(self):
        """Every arm but M0 runs the same, bit for bit, under "none"."""
        for arm in ("S0", "U", "M1", "M2"):
            a = _World(Inputs(rho_H=RATE), 0.4, SMALL, arm).run()["series"]
            b = _World(Inputs(rho_H=RATE), 0.4, replace(SMALL, usdc_yield="none"), arm).run()["series"]
            for key in a:
                np.testing.assert_array_equal(a[key], b[key], err_msg=f"{arm} {key}")

    def test_settings_refuse_what_they_do_not_define(self):
        """An unknown reading, and "none" outside M0's "reserve" mode, are refused."""
        for bad in (dict(usdc_yield="zero"), dict(usdc_yield="none", comet="fixed"),
                    dict(usdc_yield="none", comet="pinned")):
            with self.assertRaises(ValueError, msg=str(bad)):
                Economy(**bad)


class ReturnedSplitTests(unittest.TestCase):
    """The gain split's part for money returned under the conserved edge."""

    @staticmethod
    def gain(arm, s0, w):
        """The arm's mean wealth gain over S0 after launch, $ a person, from the monthly wealth change."""
        after = slice(w.burn_in, w.burn_in + w.months)
        return float(np.nansum(arm["series"]["wealth_change"][after] - s0["series"]["wealth_change"][after])
                     * DOLLARS)

    def test_the_parts_add_up_to_the_gain_under_the_conserved_edge(self):
        """With the edge conserved the parts, the returned money among them, add up to the gain to the cent's
        billionth, and the returned part is not zero, so without it they would not."""
        economy = replace(SMALL, edge="conserved")
        s0 = _World(Inputs(), 0.4, economy, "S0").run()
        for name in ("M0", "M1"):
            arm = _World(Inputs(), 0.4, economy, name).run()
            parts = split(arm, s0, economy)
            self.assertIn("returned", parts)
            self.assertGreater(abs(parts["returned"]), 1e-6, name)
            self.assertAlmostEqual(sum(parts.values()), self.gain(arm, s0, economy), places=6, msg=name)

    def test_with_the_edge_open_the_split_is_as_built(self):
        """With the edge open there is no returned part, the keys are the first run's and the parts add up to the
        gain."""
        s0 = _World(Inputs(), 0.4, SMALL, "S0").run()
        arm = _World(Inputs(), 0.4, SMALL, "M1").run()
        parts = split(arm, s0, SMALL)
        self.assertEqual(list(parts), ["outside_interest_saved", "penalties_saved", "card_fees_saved", "card_rewards",
                                       "conversion_fees_saved", "pool_costs", "savings_income", "valuation",
                                       "inflation", "gas_to_validators", "advance_fees_saved", "late_fees_saved",
                                       "wages_to_outside", "other_outside_flows"])
        self.assertAlmostEqual(sum(parts.values()), self.gain(arm, s0, SMALL), places=6)


if __name__ == "__main__":
    unittest.main()

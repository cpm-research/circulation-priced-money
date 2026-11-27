"""Tests for the conserved edge and the stress year as a slowdown, each a setting of ``Economy``
off by default, at small scale.

What is covered
---------------
* The conserved edge (``edge`` "conserved"): in every arm, with and without the slowdown, households' total real
  wealth changes each month by revaluation alone, and what was returned is the month's loss across the edge and to
  inflation; the split of the amount returned between owners (fixed equity shares by DFA wealth group) and the
  month's receivers; the ownership shares sum to 1 and stay fixed for the run.
* The slowdown: under ``distress_wages`` "kept" an extra layoff's wage is owed to nobody, so nothing is booked to the
  outside and its payer's net wealth is higher by exactly that wage when it would have been owed; under
  ``distress_purchases`` the purchases dropped at a higher level contain those dropped at a lower, are the same in
  every arm, and their share is near the chance x.
* Every new setting refuses values and combinations it does not define, and at the defaults the new records are zero.
"""
import unittest
from collections import Counter
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import Economy, _World
from cpm_abm.engine.constants import DFA_EQUITIES, DROP_STREAM, OUTSIDE_WAGE, SERVICE

ARMS = ("S0", "M0", "U", "M1", "M2")
# A small world whose distress year covers months 3 to 5 of an eight-month run.
SMALL = Economy(n=200, months=6, burn_in=2, distress_start=1, distress_length=3)
SLOWDOWN = dict(distress=0.02, distress_wages="kept", distress_purchases=0.3, purchases="poisson_size")


def service_rows(w, month):
    """The service purchases ``w`` makes for ``month`` as a multiset of (buyer, seller, amount, settle, card), from an
    empty table of obligations, nothing else run."""
    w.acc = {}
    w.ob = {key: value[:0] for key, value in w.ob.items()}
    w.req = {key: value[:0] for key, value in w.req.items()}
    w._obligations(month)
    service = w.ob["kind"] == SERVICE
    return Counter(zip(*(w.ob[key][service].tolist() for key in ("buyer", "seller", "amount", "settle", "card"))))


class ConservedEdgeTests(unittest.TestCase):
    """The conserved edge: what households lose across the edge and to inflation comes back to them."""

    def test_wealth_changes_only_by_revaluation_in_every_arm(self):
        """In every arm, with the slowdown off and on, each month's mean wealth change less the valuation term is zero
        to 1e-9 a person, the four-term identity with the amount returned holds, and the amount returned is the
        month's loss across the edge and to inflation."""
        for label, settings in (("normal", {}), ("slowdown", SLOWDOWN)):
            economy = replace(SMALL, edge="conserved", **settings)
            for arm in ARMS:
                series = _World(Inputs(), 0.4, economy, arm).run()["series"]
                message = f"{label}, {arm}"
                np.testing.assert_allclose(series["wealth_change"] - series["valuation"], 0.0, atol=1e-9,
                                           err_msg=message)
                np.testing.assert_allclose(series["wealth_change"], series["external"] + series["valuation"]
                                           + series["inflation"] + series["returned"], atol=1e-12, err_msg=message)
                np.testing.assert_allclose(series["returned"], -(series["external"] + series["inflation"]),
                                           atol=1e-12, err_msg=message)
                self.assertTrue(np.all(np.abs(series["returned"]) > 0), message)
                if settings:
                    self.assertTrue(np.all(series["wages_out"] == 0.0), message)
                    self.assertGreater(float(series["wages_kept"].sum()), 0.0, message)
                    self.assertGreater(float(series["purchases_dropped"].sum()), 0.0, message)

    def test_ownership_shares_follow_the_dfa_groups_and_stay_fixed(self):
        """At 300 people the groups hold 150, 120, 27 and 3; each group's people share its equity share equally, the
        shares sum to 1, and a run leaves them as they were opened."""
        w = _World(Inputs(), 0.4, replace(SMALL, n=300, edge="conserved"), "M1")
        omega = w.owners_weight.copy()
        self.assertAlmostEqual(float(omega.sum()), 1.0, places=14)
        shares = DFA_EQUITIES / DFA_EQUITIES.sum()
        values = np.unique(omega.round(15))
        self.assertEqual(values.size, 4)
        for share, size in zip(shares, (150, 120, 27, 3)):
            group = np.isclose(omega, share / size, rtol=1e-12)
            self.assertEqual(int(group.sum()), size)
        w.run()
        np.testing.assert_array_equal(w.owners_weight, omega)
        self.assertIsNone(_World(Inputs(), 0.4, SMALL, "M1").owners_weight)

    def split_of(self, owners_share, receipts=None):
        """What each person of a 300-person S0 world receives from a return of 3 at the close of its first month
        (external -2.5, inflation -0.5), with the month's receipts or ``receipts`` in their place."""
        w = _World(Inputs(), 0.4, replace(SMALL, n=300, edge="conserved", owners_share=owners_share), "S0")
        w.month(0)
        if receipts is not None:
            w.acc["receipts"] = receipts
        w.external = -2.5
        before = w.net_wealth()
        self.assertAlmostEqual(w._return_edge(-0.5), 3.0, places=14)
        return w, w.net_wealth() - before

    def test_owners_receive_by_equity_and_receivers_by_receipts(self):
        """With owners_share 1 the top 1% receive 50.88% of the amount and each group its DFA share; with 0 each
        person receives the amount times its share of the month's receipts, or of its spending with no receipts; at
        0.10 the mixture."""
        shares = DFA_EQUITIES / DFA_EQUITIES.sum()
        w, got = self.split_of(1.0)
        self.assertAlmostEqual(round(float(shares[3]), 4), 0.5088)
        top = w.owners_weight == w.owners_weight.max()
        self.assertEqual(int(top.sum()), 3)
        self.assertAlmostEqual(float(got[top].sum()) / 3.0, float(shares[3]), places=12)
        np.testing.assert_allclose(got, 3.0 * w.owners_weight, rtol=1e-12, atol=1e-15)
        w, got = self.split_of(0.0)
        receipts = w.acc["receipts"]
        self.assertGreater(float(receipts.sum()), 0.0)
        np.testing.assert_allclose(got, 3.0 * receipts / receipts.sum(), rtol=1e-12, atol=1e-15)
        w, got = self.split_of(0.0, receipts=np.zeros(300))
        np.testing.assert_allclose(got, 3.0 * w.spending / w.spending.sum(), rtol=1e-12, atol=1e-15)
        w, got = self.split_of(0.1)
        receipts = w.acc["receipts"]
        np.testing.assert_allclose(got, 3.0 * (0.1 * w.owners_weight + 0.9 * receipts / receipts.sum()),
                                   rtol=1e-12, atol=1e-15)

    def test_a_negative_amount_is_collected_and_covered(self):
        """A return of -50 in all (a sixth of a month's mean spending a person at 300 people) takes more than some
        people hold in cash: their net wealth still falls by exactly their part, what their cash lacked becoming an
        overdraft, and nobody's cash is left below zero."""
        w = _World(Inputs(), 0.4, replace(SMALL, n=300, edge="conserved", owners_share=0.0), "S0")
        w.month(0)
        w.external = 50.0
        before, cash = w.net_wealth(), w.cash.copy()
        self.assertAlmostEqual(w._return_edge(0.0), -50.0, places=14)
        receipts = w.acc["receipts"]
        part = -50.0 * receipts / receipts.sum()
        self.assertTrue(np.any(cash + part < 0))
        np.testing.assert_allclose(w.net_wealth() - before, part, rtol=1e-12, atol=1e-14)
        self.assertTrue(np.all(w.cash >= 0.0))


class SlowdownTests(unittest.TestCase):
    """The stress year as a slowdown: wages kept by their payers and purchases dropped."""

    def test_a_kept_wage_is_owed_to_nobody(self):
        """In the first distress month the as-built twin books each extra layoff's wage to the outside as its payer's
        payable; under "kept" no such row exists, nothing is booked, the payer's net wealth is higher by exactly that
        wage and the amount kept is the amount the twin sends outside."""
        economy = replace(SMALL, distress=0.05)
        worlds = {}
        for wages in ("outside", "kept"):
            w = _World(Inputs(), 0.4, replace(economy, distress_wages=wages), "M1")
            first = economy.burn_in + economy.distress_start
            list(map(w.month, range(first)))
            w.external = 0.0
            w._layoffs(first)
            w._obligations(first)
            worlds[wages] = w
        built, kept = worlds["outside"], worlds["kept"]
        out = built.ob["kind"] == OUTSIDE_WAGE
        self.assertTrue(out.any())
        self.assertFalse(np.any(kept.ob["kind"] == OUTSIDE_WAGE))
        owed = np.bincount(built.ob["buyer"][out], weights=built.ob["amount"][out], minlength=economy.n)
        self.assertAlmostEqual(built.external, -float(owed.sum()), places=12)
        self.assertEqual(kept.external, 0.0)
        self.assertEqual(kept.acc["wages_out"], 0.0)
        self.assertAlmostEqual(kept.acc["wages_kept"], built.acc["wages_out"], places=12)
        np.testing.assert_allclose(kept.net_wealth() - built.net_wealth(), owed, rtol=1e-12, atol=1e-14)

    def test_drops_are_nested_common_and_near_their_chance(self):
        """In a distress month at 2,000 people the purchases kept at a distress level of 0.02 are among those kept at
        0.01, which are among the no-distress twin's; the number dropped is the count of uniforms on stream 3113
        below x; every arm keeps the same purchases; and the share dropped is within 0.01 of x (0.15 and 0.3)."""
        self.assertEqual(DROP_STREAM, 3113)
        economy = replace(SMALL, n=2000, purchases="poisson_size", distress_purchases=0.3)
        month = economy.burn_in + economy.distress_start
        made, dropped = {}, {}
        for level in (0.0, 0.01, 0.02):
            w = _World(Inputs(), 0.4, replace(economy, distress=level), "M1")
            made[level] = service_rows(w, month)
            dropped[level] = w.acc["purchases_dropped"]
        whole = sum(made[0.0].values())
        draw = np.random.default_rng(np.random.SeedSequence([economy.seed, DROP_STREAM, month])).random(whole)
        for low, high in ((0.0, 0.01), (0.01, 0.02)):
            self.assertFalse(made[high] - made[low])
        for level in (0.01, 0.02):
            x = 0.3 * level / 0.02
            self.assertEqual(dropped[level], float((draw < x).sum()))
            self.assertEqual(sum(made[level].values()), whole - dropped[level])
            self.assertLess(abs(dropped[level] / whole - x), 0.01)
        for arm in ARMS:
            w = _World(Inputs(), 0.4, replace(economy, distress=0.02), arm)
            self.assertEqual(service_rows(w, month), made[0.02], arm)
        # Outside the distress year nothing is dropped.
        w = _World(Inputs(), 0.4, replace(economy, distress=0.02), "M1")
        service_rows(w, month - 1)
        self.assertEqual(w.acc["purchases_dropped"], 0.0)

    def test_settings_refuse_what_they_do_not_define(self):
        """An unknown edge or wage reading, the conserved edge with the recirculation stress, a share outside 0 to 1,
        drops without purchases of fixed size at random, and a chance of dropping above 1 are refused."""
        bad = (dict(edge="closed"), dict(edge="conserved", lender_income_recirculated=True), dict(owners_share=1.5),
               dict(owners_share=-0.1), dict(distress_wages="paid"), dict(distress_purchases=0.2),
               dict(distress_purchases=0.2, purchases="poisson_month"),
               dict(distress_purchases=1.5, purchases="poisson_size"),
               dict(distress_purchases=0.5, distress=0.05, purchases="poisson_size"))
        for settings in bad:
            with self.assertRaises(ValueError, msg=str(settings)):
                Economy(**settings)
        Economy(distress_purchases=1.0, distress=0.02, purchases="poisson_size", edge="conserved")


class DefaultTests(unittest.TestCase):
    """At the defaults the new settings change nothing."""

    def test_defaults_record_zeros(self):
        """With every new setting at its default, under the default stress, the amount returned, the wages kept and
        the purchases dropped are zero in every month, the wages sent outside are not, and the three-term identity
        holds."""
        economy = Economy()
        self.assertEqual((economy.edge, economy.owners_share, economy.distress_wages, economy.distress_purchases),
                         ("open", 0.10, "outside", 0.0))
        series = _World(Inputs(), 0.4, replace(SMALL, distress=0.02), "M1").run()["series"]
        for key in ("returned", "wages_kept", "purchases_dropped"):
            self.assertEqual(series[key].size, SMALL.burn_in + SMALL.months)
            self.assertTrue(np.all(series[key] == 0.0), key)
        self.assertGreater(float(series["wages_out"].sum()), 0.0)
        np.testing.assert_allclose(series["wealth_change"],
                                   series["external"] + series["valuation"] + series["inflation"], atol=1e-12)


if __name__ == "__main__":
    unittest.main()

"""The day's settlement map is monotone where the paper says it is (Proposition 'Settlement', part (i)).

The step of the proof that is not immediate is the pool's: it lends the largest draw its receipts test admits for
that draw and every smaller one, and the part of a shortfall it then leaves unlent must not fall as the shortfall
rises. Savings, the cash advance and earned-wage access are capped amounts, for which this is plain. Here the three
admission limits are swept over the shortfall on wide random parameters and the unlent part is checked for any fall.
"""
import unittest

import numpy as np

from cpm_abm.engine.lending_rules import limit_with_advance, limit_with_card, limit_with_fee

SETS, GRID = 3000, 240


class UnlentPartNeverFalls(unittest.TestCase):
    """unlent(short) = short - min(short, limit(short)) is nondecreasing in the shortfall, all else fixed."""

    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(20261117)
        cls.short = np.linspace(0.0, 3.0, GRID)[None, :]        # months of mean spending

        def column(low, high, zero_share=0.0):
            """One value per parameter set; a share of the sets hold exactly zero."""
            value = rng.uniform(low, high, size=(SETS, 1))
            return np.where(rng.random((SETS, 1)) < zero_share, 0.0, value)

        cls.spare, cls.f_pool = column(0.0, 3.0, 0.05), column(1.0, 1.05)
        cls.unit, cls.cap = column(0.0, 0.8, 0.1), column(0.0, 0.02, 0.05)
        cls.room, cls.f_advance = column(0.0, 2.0, 0.2), column(1.0, 1.10)
        cls.f_cash, cls.floor = column(1.0, 1.05), column(0.0, 0.01, 0.1)
        cls.rate, cls.f_fee = column(0.0, 0.08, 0.1), column(1.0, 1.05)
        cls.ewa_room, cls.f_ewa = column(0.0, 1.0, 0.3), column(1.0, 1.10)

    def assertNeverFalls(self, limit):
        self.assertTrue((limit >= -1e-12).all())
        unlent = self.short - np.minimum(self.short, limit)
        self.assertGreaterEqual(float(np.diff(unlent, axis=1).min()), -1e-9)

    def test_payer_without_a_card(self):
        self.assertNeverFalls(limit_with_fee(self.short, self.spare, self.f_pool, self.unit, self.cap))

    def test_payer_with_earned_wage_access(self):
        self.assertNeverFalls(limit_with_advance(self.short, self.spare, self.f_pool, self.unit, self.cap,
                                                 self.room, self.f_advance))

    def test_card_holder(self):
        self.assertNeverFalls(limit_with_card(self.short, self.spare, self.f_pool, self.unit, self.cap, self.room,
                                              self.f_cash, self.floor, self.rate, self.f_fee, self.ewa_room,
                                              self.f_ewa))

    def test_a_rationed_draw_keeps_the_property(self):
        """With a served share below one held fixed, short - share x min(short, limit) does not fall either: the
        ask rises by no more than the shortfall does."""
        ask = np.minimum(self.short, limit_with_fee(self.short, self.spare, self.f_pool, self.unit, self.cap))
        for share in (0.25, 0.5, 0.9):
            self.assertGreaterEqual(float(np.diff(self.short - share * ask, axis=1).min()), -1e-9)


if __name__ == "__main__":
    unittest.main()

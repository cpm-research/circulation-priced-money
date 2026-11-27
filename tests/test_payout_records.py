"""Tests for the records of the monthly payout and of the edge, written in every run and read by
no rule, at small scale.

What is covered
---------------
* ``payout``, months by people: what each person received from the payout of the conserved edge, summing each month
  to the stored total ``returned``; zero with the edge open.
* ``pool_payable`` and ``payout_inflation``: what the pool owes its operating provider at the month's end, never
  below zero, and the inflation part of the payout, minus the month's inflation term under the conserved edge.
* ``edge_accrued`` and ``edge_paid``: what was booked across the edge when a debt was created and what was booked as
  cash moved; together they are the month's whole net outflow, minus ``external``.
"""
import unittest
from dataclasses import replace

import numpy as np

from cpm_abm.core_model import Inputs
from cpm_abm.economy_abm import (BIG, CHARGED_OFF, DAYS, EWA_FEE, FEE_DEBT, LATE_OUTSIDE_WAGE, MONTH_USD,
                                 OUTSIDE_WAGE, REVOLVE, TERM, Economy, _World)
from tests.test_economy_abm import TINY, controlled_world

SMALL = replace(TINY, n=60, burn_in=2, months=6)
CONSERVED = replace(SMALL, edge="conserved")
ARMS = ("S0", "M0", "U", "M1", "M2")


class RecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {(edge, arm): _World(Inputs(), 0.6, economy, arm).run()
                    for edge, economy in (("open", SMALL), ("conserved", CONSERVED)) for arm in ARMS}

    def test_the_payout_by_person_sums_to_the_total(self):
        for (edge, arm), run in self.runs.items():
            payout, series = run["payout"], run["series"]
            self.assertEqual(payout.shape, (SMALL.burn_in + SMALL.months, SMALL.n))
            if edge == "open":
                self.assertTrue(np.all(payout == 0.0), arm)
                continue
            np.testing.assert_allclose(payout.sum(axis=1) / SMALL.n, series["returned"], rtol=0, atol=1e-12,
                                       err_msg=arm)
            self.assertTrue(np.any(payout != 0.0), arm)

    def test_the_payable_and_the_inflation_part(self):
        for (edge, arm), run in self.runs.items():
            series = run["series"]
            self.assertTrue(np.all(series["pool_payable"] >= 0.0), arm)
            if arm in ("S0", "M0"):
                self.assertTrue(np.all(series["pool_payable"] == 0.0), arm)
            want = -series["inflation"] if edge == "conserved" else np.zeros_like(series["inflation"])
            np.testing.assert_array_equal(series["payout_inflation"], want, err_msg=f"{edge} {arm}")

    def test_the_largest_payable_of_the_month(self):
        """The largest amount the pool owed its provider on any day is never below what it owes at the month's end.
        Example: a pool with no cash bears a $5 cost on one day and is paid $5 the next, then bears nothing more: it
        owes $5 at most and nothing at the end."""
        for (edge, arm), run in self.runs.items():
            series = run["series"]
            self.assertTrue(np.all(series["pool_payable_most"] >= series["pool_payable"]), arm)
        w = controlled_world()
        w.pool_cash, w.pool_payable, w.acc["pool_payable_most"] = 0.0, 0.0, 0.0
        w._pool_cost(5.0 / MONTH_USD)
        w.pool_cash = 5.0 / MONTH_USD
        w._pool_cost(0.0)
        self.assertEqual(w.pool_payable, 0.0)
        self.assertAlmostEqual(w.acc["pool_payable_most"] * MONTH_USD, 5.0, places=9)

    def test_accrued_and_paid_make_the_whole_edge(self):
        for (edge, arm), run in self.runs.items():
            series = run["series"]
            self.assertTrue(np.all(series["edge_accrued"] >= 0.0), arm)
            self.assertGreater(float(series["edge_accrued"].sum()), 0.0, arm)
            np.testing.assert_allclose(series["edge_accrued"] + series["edge_paid"], -series["external"], rtol=0,
                                       atol=1e-12, err_msg=f"{edge} {arm}")


class PaidPayoutTest(unittest.TestCase):
    """The payout returns what was paid (``Economy.payout`` "paid")."""

    @classmethod
    def setUpClass(cls):
        stress = dict(distress=0.02, distress_start=1, distress_length=3, card_line_cut=True)
        cls.runs = {(reading, distress, arm): _World(Inputs(), 0.6, replace(CONSERVED, payout=reading,
                                                                         **(stress if distress else {})), arm).run()
                    for reading in ("accrued", "paid") for distress in (False, True) for arm in ARMS}

    def test_the_identity_every_month_in_every_arrangement(self):
        """Wealth changes by revaluation less the change in the stock owed across the edge and not yet paid; by default
        by revaluation alone."""
        for (reading, distress, arm), run in self.runs.items():
            series = run["series"]
            stock = series["edge_owed"]
            change = np.diff(np.concatenate([[0.0], stock]))
            want = -change if reading == "paid" else np.zeros_like(change)
            np.testing.assert_allclose(series["wealth_change"] - series["valuation"], want, rtol=0, atol=1e-12,
                                       err_msg=f"{reading} {distress} {arm}")
            self.assertTrue(np.all(stock >= 0.0), arm)
            np.testing.assert_allclose(run["payout"].sum(axis=1) / SMALL.n, series["returned"], rtol=0, atol=1e-12)

    def test_the_stock_is_never_more_than_is_owed_outside(self):
        """Each person's stock is part of what it owes the outside at the close: its loans from outside lenders, its
        card statement and unbilled purchases, its earned-wage advances and the wages it owes outside."""
        economy = replace(CONSERVED, payout="paid", distress=0.02, distress_start=1, distress_length=3)
        for arm in ARMS:
            w = _World(Inputs(), 0.6, economy, arm)
            for month in range(w.total):
                w.month(month)
                bk, ob = w.book, w.ob
                outside = ~bk["pool"]
                owed = np.bincount(bk["borrower"][outside], weights=(bk["principal"] + bk["interest"])[outside],
                                   minlength=w.n)
                sink = (ob["kind"] == OUTSIDE_WAGE) | (ob["kind"] == LATE_OUTSIDE_WAGE)
                owed += np.bincount(ob["buyer"][sink], weights=ob["amount"][sink], minlength=w.n)
                owed += np.bincount(w.pop["wage_to"], weights=w.ewa_owed, minlength=w.n)
                owed += w.card_statement + w.card_unbilled
                stock = w._edge_owed()
                self.assertTrue(np.all(stock <= owed + 1e-12), (arm, month))
                self.assertTrue(np.all(stock >= 0.0), (arm, month))

    def test_the_readings_pay_the_same_while_nothing_is_owed(self):
        """In the first month both readings run the same world; their payouts differ by that month's change in the
        stock, and equal it exactly where the stock does not move."""
        for distress in (False, True):
            for arm in ARMS:
                built, paid = (self.runs[(reading, distress, arm)]["series"] for reading in ("accrued", "paid"))
                self.assertEqual(built["edge_owed"][0], paid["edge_owed"][0])
                self.assertAlmostEqual(paid["returned"][0], built["returned"][0] - paid["edge_owed"][0], places=12)

    @staticmethod
    def world():
        """The controlled world under the conserved edge and the payout of what was paid, its stock emptied like its
        other accounts: person 0 holds $200 of cash and nothing is owed anywhere."""
        w = controlled_world()
        w.economy = replace(w.economy, edge="conserved", payout="paid")
        w.owners_weight = np.full(w.n, 1.0 / w.n)
        w.acc["receipts"][:] = 1.0
        w.card_edge_owed[:], w.ewa_fee_owed[:], w.pool_payable = 0.0, 0.0, 0.0
        w.cash[0] = 200.0 / MONTH_USD
        w.edge_mark = w._edge_stock()
        return w

    @staticmethod
    def close(w):
        """A month's payout in dollars, with the external flow it saw, then the next month's mark and a fresh edge."""
        seen = -w.external * MONTH_USD
        returned = w._return_edge(0.0) * MONTH_USD
        w.edge_mark, w.external = w._edge_stock(), 0.0
        return returned, seen

    def outside_wage(self, w, settle):
        """A $100 wage owed outside by person 0, settling on day ``settle``, booked as ``_obligations`` books it."""
        wage = 100.0 / MONTH_USD
        w.ob = dict(buyer=np.array([0]), seller=np.array([1]), amount=np.array([wage]), settle=np.array([settle]),
                    card=np.array([False]), kind=np.array([OUTSIDE_WAGE]))
        w.payable[0] += wage
        w.external -= wage
        w._edge_debt(np.eye(w.n)[0] * wage)

    def test_a_payment_on_another_loan_does_not_return_an_owed_wage(self):
        """$100 owed outside as a wage and $100 of principal paid on a separate outside loan: nothing is returned and
        the stock stays $100; the $100 is returned in the month the wage itself is paid."""
        w = self.world()
        w._add_loans(np.array([0]), False, TERM, np.array([100.0 / MONTH_USD]), 0.0, 0.0, BIG, np.array([1]), 0)
        self.outside_wage(w, settle=45)
        w._pay(np.array([0]), np.array([100.0 / MONTH_USD]), np.maximum(w.cash, 0.0))
        self.assertAlmostEqual(float(w.book["principal"][0]) * MONTH_USD, 0.0, places=9)   # the loan is repaid
        self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 100.0, places=9)
        returned, seen = self.close(w)
        self.assertAlmostEqual(seen, 100.0, places=9)        # by default all of it would be handed back now
        self.assertAlmostEqual(returned, 0.0, places=9)
        # The next month person 0 is paid $200 and pays the wage on its date.
        w.cash[0] += 200.0 / MONTH_USD
        w._settle(1, 45)
        self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 0.0, places=9)
        returned, seen = self.close(w)
        self.assertAlmostEqual((returned, seen), (100.0, 0.0), places=9)

    def test_a_wage_discharged_unpaid_is_not_returned(self):
        """The wage owed outside is discharged unpaid: the debt goes, the discharge is booked across the edge as money
        coming back, the stock falls by $100, and nothing is returned in either month."""
        w = self.world()
        self.outside_wage(w, settle=45)
        self.assertAlmostEqual(self.close(w)[0], 0.0, places=9)
        wage = float(w.ob["amount"][0])
        w.ob["amount"][0] = 0.0
        w.payable[0] -= wage
        w.external += wage
        returned, seen = self.close(w)
        self.assertAlmostEqual(w.edge_mark * MONTH_USD, 0.0, places=9)
        self.assertAlmostEqual((returned, seen), (0.0, -100.0), places=9)

    def test_card_interest_is_returned_when_the_statement_is_paid(self):
        """$10 of card interest accrued in month 1 and paid with the statement in month 2: none of it is returned in
        month 1, the stock is $10, and the $10 is returned in month 2 when the payment clears it."""
        w = self.world()
        w.holder[0] = True
        w._add_loans(np.array([0]), False, REVOLVE, np.array([100.0 / MONTH_USD]), 0.1 * DAYS, 0.1 * DAYS, BIG)
        w._accrue()   # a day of interest at 10% a day on $100: $10, besides the day's yield on cash
        self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 10.0, places=9)
        returned, seen = self.close(w)
        self.assertAlmostEqual(returned, seen - 10.0, places=9)
        w.book["rate"][:] = 0.0
        w.card_statement[0] = 50.0 / MONTH_USD
        w._statement(20, 50)
        self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 0.0, places=9)
        returned, seen = self.close(w)
        self.assertAlmostEqual(returned, seen + 10.0, places=9)

    def test_payments_clear_only_their_own_liability(self):
        """$5 of interest accrued on an outside loan and a $7 card fee: a $50 statement payment clears the fee and
        leaves the loan's $5; a payment on the loan clears its $5 and leaves the fee."""
        for paying in ("card", "loan"):
            w = self.world()
            w.holder[0] = True
            w._add_loans(np.array([0]), False, TERM, np.array([100.0 / MONTH_USD]), 0.0, 0.0, BIG, np.array([1]), 0)
            w.book["interest"][0] = w.book["interest_due"][0] = 5.0 / MONTH_USD
            fee = np.eye(w.n)[0] * 7.0 / MONTH_USD
            w._add_loans(np.array([0]), False, REVOLVE, fee[:1], 0.0, 0.0, BIG)
            w._card_lender(fee)
            self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 12.0, places=9)
            if paying == "card":
                w.card_statement[0] = 50.0 / MONTH_USD
                w._statement(20, 50)
                self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 5.0, places=9)
            else:
                w._pay(np.array([0]), np.array([5.0 / MONTH_USD]), np.maximum(w.cash, 0.0))
                self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 7.0, places=9)

    def test_the_setting_and_its_refusals(self):
        self.assertEqual(Economy().payout, "accrued")
        for bad in (dict(payout="cash"), dict(payout="paid")):
            with self.assertRaises(ValueError, msg=bad):
                Economy(**bad)
        Economy(edge="conserved", payout="paid")


class LedgerWorld(_World):
    """A world that keeps its own ledger of what is owed across the edge, by accrual line and by payment kind,
    written from the flows the engine records and the payments it makes, never from ``_edge_owed``.

    Lines, by person: the interest accrued on outside loans other than the card (the month's interest by lender) less
    the interest paid on them; the failure fees less what is paid on fee debt; the card's interest and fees less what is
    paid to the card, fees and interest first, at most what the card is owed; the earned-wage fees, by job, less the
    repayments of advances, fees first; the wages owed outside as they are made less what is paid on them."""

    def __init__(self, *args):
        super().__init__(*args)
        n = self.n
        self.ledger = dict(loans=np.zeros(n), fees=np.zeros(n), card=np.zeros(n), ewa=np.zeros(n), wages=np.zeros(n))
        self.repaid = np.zeros(n)

    def _rows(self):
        bk = self.book
        card = self._card_rows() | (bk["kind"] == CHARGED_OFF)
        return ~bk["pool"] & ~card & (bk["kind"] != FEE_DEBT), ~bk["pool"] & card, bk["kind"] == FEE_DEBT

    def _pay(self, idx, payable, budget):
        loans, card, fees = self._rows()
        bk, size = self.book, self.book["borrower"].size
        interest, owed = bk["interest"].copy(), (bk["principal"] + bk["interest"]).copy()
        super()._pay(idx, payable, budget)
        bk = self.book
        by = lambda rows, paid: np.bincount(bk["borrower"][:size][rows], weights=paid[rows], minlength=self.n)
        self.ledger["loans"] -= by(loans, interest - bk["interest"][:size])
        self.ledger["fees"] -= by(fees, owed - (bk["principal"] + bk["interest"])[:size])
        self._card_paid(by(card, owed - (bk["principal"] + bk["interest"])[:size]))

    def _card_paid(self, paid):
        self.ledger["card"] -= np.minimum(self.ledger["card"], paid)

    def _minimum_paid(self, minimum, paid, t, on=None):
        # The statement's payment, own money and the pool's draw, is what the minimum counts beyond the payments on the
        # card's balances since the last statement; it is made before a late fee is charged.
        self._card_paid(paid - self.card_paid)
        super()._minimum_paid(minimum, paid, t, on)

    def _repay_advances(self, job, payee, paid, p_side):
        owed = self.ewa_owed.copy()
        out = super()._repay_advances(job, payee, paid, p_side)
        repaid = owed - self.ewa_owed
        self.repaid += repaid
        self.ledger["ewa"] -= np.minimum(self.ledger["ewa"], repaid)
        return out

    def _outside_wages(self):
        ob = self.ob
        sink = (ob["kind"] == OUTSIDE_WAGE) | (ob["kind"] == LATE_OUTSIDE_WAGE)
        return np.bincount(ob["buyer"][sink], weights=ob["amount"][sink], minlength=self.n)

    def _obligations(self, month):
        before = self._outside_wages()
        super()._obligations(month)
        self.ledger["wages"] += self._outside_wages() - before

    def _settle(self, month, t):
        before, owed, fee = self._outside_wages(), self.ewa_owed.copy(), self.acc["fee"].copy()
        self.repaid = np.zeros(self.n)
        super()._settle(month, t)
        self.ledger["wages"] -= before - self._outside_wages()
        self.ledger["fees"] += self.acc["fee"] - fee
        # Today's new advances by job: the rise of what is owed on them, with what today's wages repaid first added
        # back; each carries its fee, EWA_FEE of the advance, in what is owed.
        self.ledger["ewa"] += (self.ewa_owed - owed + self.repaid) * (EWA_FEE / (1 + EWA_FEE))

    def _wage_arrears(self, budget):
        before = self._outside_wages()
        super()._wage_arrears(budget)
        self.ledger["wages"] -= before - self._outside_wages()

    def _accrue(self):
        acc = {key: self.acc[key].copy() for key in ("credit_interest_outside", "credit_interest_card")}
        super()._accrue()
        self.ledger["loans"] += self.acc["credit_interest_outside"] - acc["credit_interest_outside"]
        self.ledger["card"] += self.acc["credit_interest_card"] - acc["credit_interest_card"]

    def _card_lender(self, fees):
        super()._card_lender(fees)
        self.ledger["card"] += fees

    def _loan_losses(self, month):
        # A discharge of a card balance takes the card line's share with it: the ledger scales by what the card is
        # owed after it over before it.
        owed = lambda: np.bincount(self.book["borrower"][self._rows()[1]],
                                   weights=(self.book["principal"] + self.book["interest"])[self._rows()[1]],
                                   minlength=self.n)
        before = owed()
        super()._loan_losses(month)
        self.ledger["card"] *= np.divide(owed(), before, out=np.ones(self.n), where=before > 1e-12)

    def _deflate(self):
        out = super()._deflate()
        f = 1.0 / (1.0 + self.economy.inflation)
        self.ledger = {key: value * f for key, value in self.ledger.items()}
        return out

    def stock(self):
        """The ledger's stock by person, the card's line at most what the card is owed."""
        bk = self.book
        card = ~bk["pool"] & (self._card_rows() | (bk["kind"] == CHARGED_OFF))
        owed = np.bincount(bk["borrower"][card], weights=(bk["principal"] + bk["interest"])[card], minlength=self.n)
        self.ledger["card"] = np.minimum(self.ledger["card"], owed)
        ewa = np.bincount(self.pop["wage_to"], weights=self.ledger["ewa"], minlength=self.n)
        return self.ledger["loans"] + self.ledger["fees"] + self.ledger["card"] + ewa + self.ledger["wages"]


class LedgerTest(unittest.TestCase):
    def test_the_stock_follows_an_independent_ledger(self):
        """Every month, in every arrangement with the stress year on, the engine's stock is the ledger's."""
        economy = replace(CONSERVED, payout="paid", distress=0.02, distress_start=1, distress_length=3, months=8,
                          earned_wage_share=0.5, card_line_cut=True)
        for losses in ("none", "sourced"):
            for arm in ARMS:
                w = LedgerWorld(Inputs(), 0.6, replace(economy, loan_losses=losses), arm)
                for month in range(w.total):
                    w.month(month)
                    np.testing.assert_allclose(w._edge_owed(), w.stock(), rtol=0, atol=1e-10,
                                               err_msg=f"{losses} {arm} {month}")
                self.assertGreater(float(w.stock().sum()), 0.0)

    def test_a_discharged_card_balance_takes_its_fees_with_it(self):
        """A $100 card balance holding a $10 fee, $50 of it discharged as a loan loss: the stock falls to $5, and the
        payout claws back the $50 the households gained less the $5 of the fee that was never handed out."""
        w = PaidPayoutTest.world()
        w.economy = replace(w.economy, loan_losses="sourced")
        w.holder[0] = True
        w._add_loans(np.array([0]), False, REVOLVE, np.array([100.0 / MONTH_USD]), 0.0, 0.0, BIG)
        w._card_edge(np.eye(w.n)[0] * 10.0 / MONTH_USD)
        w.edge_mark, w.external = w._edge_stock(), 0.0
        w.acc["loss_base"][:] = 0.0
        w.loss_carried[:] = 0.0
        w.loss_carried[0, 0] = 50.0 / MONTH_USD   # the card class, outside lenders: $50 to discharge this month
        w._loan_losses(1)
        self.assertAlmostEqual(w._edge_stock() * MONTH_USD, 5.0, places=9)
        returned, seen = PaidPayoutTest.close(w)
        self.assertAlmostEqual((returned, seen), (-45.0, -50.0), places=9)


class CashSideTest(unittest.TestCase):
    """The records that reconcile the paid payout with cash: ``edge_cleared`` and ``card_unbilled``."""

    def test_the_payout_is_cash_moved_plus_cleared_plus_inflation_less_kept(self):
        for share in (1.0, 0.1):
            for arm in ARMS:
                economy = replace(CONSERVED, payout="paid", edge_returned=share, distress=0.02, distress_start=1,
                                  distress_length=3, card_line_cut=True)
                s = _World(Inputs(), 0.6, economy, arm).run()["series"]
                np.testing.assert_allclose(s["returned"], s["edge_paid"] + s["edge_cleared"] + s["payout_inflation"]
                                           - s["edge_kept"], rtol=0, atol=1e-12, err_msg=f"{share} {arm}")
                self.assertTrue(np.all(s["edge_cleared"] >= -1e-12), arm)

    def test_card_interest_booked_then_paid(self):
        """$10 of card interest booked in month 1 and paid with the statement in month 2: edge_accrued $10 then $0,
        edge_cleared $0 then $10."""
        w = PaidPayoutTest.world()
        w.holder[0] = True
        w._add_loans(np.array([0]), False, REVOLVE, np.array([100.0 / MONTH_USD]), 0.1 * DAYS, 0.1 * DAYS, BIG)
        w.acc["edge_accrued"] = w.acc["edge_discharged"] = 0.0
        w._accrue()
        stock = w._edge_stock()
        months = [(w.acc["edge_accrued"] * MONTH_USD, w._edge_cleared(stock, 0.0) * MONTH_USD)]
        w.edge_mark = stock
        w.acc["edge_accrued"] = 0.0
        w.book["rate"][:] = 0.0
        w.card_statement[0] = 50.0 / MONTH_USD
        w._statement(20, 50)
        months.append((w.acc["edge_accrued"] * MONTH_USD, w._edge_cleared(w._edge_stock(), 0.0) * MONTH_USD))
        np.testing.assert_allclose(months, [(10.0, 0.0), (0.0, 10.0)], atol=1e-9)

    def test_card_credit_not_yet_in_the_book(self):
        """A $300 purchase on the card on the month's last day, no statement closed: card_debt 0, card_unbilled
        $300 over n."""
        w = controlled_world()
        w.holder[0] = True
        w.card_unbilled[0] = 300.0 / MONTH_USD
        self.assertAlmostEqual(float((w.card_unbilled + w.card_statement).sum()) * MONTH_USD / w.n, 30.0, places=9)
        series = _World(Inputs(), 0.6, SMALL, "S0").run()["series"]
        self.assertTrue(np.all(series["card_unbilled"] >= 0.0))
        self.assertGreater(float(series["card_unbilled"].max()), 0.0)


class EdgeReturnedTest(unittest.TestCase):
    """A share of the payout returned (``Economy.edge_returned``)."""

    def test_the_hand_case(self):
        """$100 to return in a month gives $100, $10 and $0 at 1, 0.10 and 0, with $0, $90 and $100 kept."""
        for share, back, kept in ((1.0, 100.0, 0.0), (0.10, 10.0, 90.0), (0.0, 0.0, 100.0)):
            w = PaidPayoutTest.world()
            w.economy = replace(w.economy, payout="accrued", edge_returned=share)
            w.external = -100.0 / MONTH_USD
            before = w.cash.sum()
            self.assertAlmostEqual(w._return_edge(0.0) * MONTH_USD, back, places=9)
            self.assertAlmostEqual(w.acc["edge_kept"] * MONTH_USD, kept, places=9)
            self.assertAlmostEqual((w.cash.sum() - before) * MONTH_USD, back, places=9)

    def test_nothing_returned_is_the_open_edge(self):
        """With nothing returned the households' numbers are those of the open edge, bit for bit; only the records
        of the edge itself differ (the payout's inflation part, and what was kept)."""
        for arm in ARMS:
            stress = dict(distress=0.02, distress_start=1, distress_length=3)
            open_ = _World(Inputs(), 0.6, replace(SMALL, **stress), arm).run()
            none = _World(Inputs(), 0.6, replace(CONSERVED, edge_returned=0.0, **stress), arm).run()
            for key in open_:
                if key in ("economy", "series"):
                    continue
                self.assertTrue(identical(open_[key], none[key]), (arm, key))
            for key, value in open_["series"].items():
                if key in ("payout_inflation", "edge_kept"):
                    continue
                self.assertTrue(identical(value, none["series"][key]), (arm, key))
            # What was kept is the whole month's loss across the edge and to inflation.
            np.testing.assert_allclose(none["series"]["edge_kept"],
                                       -none["series"]["external"] - none["series"]["inflation"], rtol=0, atol=1e-12)

    def test_the_identity_with_a_share_kept(self):
        """Wealth changes by revaluation less the change in the stock and less what was kept."""
        for reading in ("accrued", "paid"):
            for arm in ARMS:
                economy = replace(CONSERVED, payout=reading, edge_returned=0.10, distress=0.02, distress_start=1,
                                  distress_length=3)
                series = _World(Inputs(), 0.6, economy, arm).run()["series"]
                change = np.diff(np.concatenate([[0.0], series["edge_owed"]])) if reading == "paid" else 0.0
                np.testing.assert_allclose(series["wealth_change"] - series["valuation"],
                                           -change - series["edge_kept"], rtol=0, atol=1e-12, err_msg=arm)

    def test_the_setting_and_its_refusals(self):
        self.assertEqual(Economy().edge_returned, 1.0)
        for bad in (dict(edge_returned=0.5), dict(edge="conserved", edge_returned=1.5),
                    dict(edge="conserved", edge_returned=-0.1), dict(edge="conserved", edge_returned="all")):
            with self.assertRaises(ValueError, msg=bad):
                Economy(**bad)
        Economy(edge="conserved", edge_returned=0.1)


def identical(a, b):
    """Bit for bit: arrays by dtype, shape and bytes, dicts and lists of them item by item, anything else by value."""
    if isinstance(a, dict):
        return list(a) == list(b) and all(identical(a[key], b[key]) for key in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(map(identical, a, b))
    if isinstance(a, np.ndarray):
        return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()
    return a == b or (a != a and b != b)


if __name__ == "__main__":
    unittest.main()

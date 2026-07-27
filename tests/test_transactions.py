"""Redirect parsing and reconciliation against the transaction API."""

from __future__ import annotations

import unittest

from _support import CIPHER, make_transport, ok_envelope

from hesabe.errors import HesabeSignatureError
from hesabe.resources.transactions import Transactions
from hesabe.session import MerchantSession


def redirect_data(result):
    return CIPHER.encrypt({"status": True, "response": {"data": result}})


def make_transactions(*responses):
    transport, send = make_transport(*responses)
    return Transactions(transport, MerchantSession(transport)), send


RESULT = {"resultCode": "CAPTURED", "amount": "1.000", "paymentToken": "PT1"}


class ParseRedirectTest(unittest.TestCase):
    def test_unwraps_the_nested_result(self):
        transactions, _ = make_transactions(ok_envelope())
        result = transactions.parse_redirect(redirect_data(RESULT))
        self.assertEqual(result.paymentToken, "PT1")
        self.assertEqual(result.resultCode, "CAPTURED")


class VerifyRedirectTest(unittest.TestCase):
    def test_returns_the_authoritative_record_when_amounts_match(self):
        record = {"token": "PT1", "amount": 1, "status": "SUCCESSFUL"}
        transactions, send = make_transactions(ok_envelope(record))
        confirmed = transactions.verify_redirect(redirect_data(RESULT))
        self.assertEqual(confirmed.status, "SUCCESSFUL")
        self.assertIn("api/transaction/PT1", send.calls[0]["url"])

    def test_amount_mismatch_raises(self):
        record = {"token": "PT1", "amount": "99.000", "status": "SUCCESSFUL"}
        transactions, _ = make_transactions(ok_envelope(record))
        with self.assertRaises(HesabeSignatureError):
            transactions.verify_redirect(redirect_data(RESULT))

    def test_missing_payment_token_raises(self):
        transactions, _ = make_transactions(ok_envelope())
        with self.assertRaises(HesabeSignatureError):
            transactions.verify_redirect(redirect_data({"resultCode": "CAPTURED"}))


if __name__ == "__main__":
    unittest.main()

"""Webhook parsing and API-reconciled verification."""

from __future__ import annotations

import json
import unittest

import _support  # noqa: F401  (sys.path setup)

from hesabe.errors import HesabeSignatureError
from hesabe.types import HesabeObject
from hesabe.webhooks import Webhooks


class StubTransactions:
    def __init__(self, record):
        self.record = record
        self.calls = []

    def retrieve(self, token):
        self.calls.append(token)
        return HesabeObject.wrap(self.record)


EVENT = {"token": "PT1", "amount": "1.000", "status": "SUCCESSFUL"}


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.webhooks = Webhooks(StubTransactions({}))

    def test_accepts_str_bytes_and_dict(self):
        for body in (json.dumps(EVENT), json.dumps(EVENT).encode(), dict(EVENT)):
            with self.subTest(type(body).__name__):
                self.assertEqual(self.webhooks.parse(body)["token"], "PT1")

    def test_rejects_invalid_json(self):
        with self.assertRaises(HesabeSignatureError):
            self.webhooks.parse("not json")

    def test_rejects_payload_without_token(self):
        with self.assertRaises(HesabeSignatureError):
            self.webhooks.parse({"amount": "1.000"})


class VerifyTest(unittest.TestCase):
    def test_returns_the_confirmed_record(self):
        stub = StubTransactions({"token": "PT1", "amount": "1.000", "status": "SUCCESSFUL"})
        confirmed = Webhooks(stub).verify(EVENT)
        self.assertEqual(confirmed.status, "SUCCESSFUL")
        self.assertEqual(stub.calls, ["PT1"])

    def test_amount_type_differences_still_match(self):
        """A webhook string "1.000" must reconcile with an API number 1."""
        stub = StubTransactions({"token": "PT1", "amount": 1, "status": "SUCCESSFUL"})
        confirmed = Webhooks(stub).verify(EVENT)
        self.assertEqual(confirmed.amount, 1)

    def test_amount_mismatch_raises(self):
        stub = StubTransactions({"token": "PT1", "amount": "9.000", "status": "SUCCESSFUL"})
        with self.assertRaises(HesabeSignatureError):
            Webhooks(stub).verify(EVENT)

    def test_status_mismatch_raises(self):
        stub = StubTransactions({"token": "PT1", "amount": "1.000", "status": "FAILED"})
        with self.assertRaises(HesabeSignatureError):
            Webhooks(stub).verify(EVENT)


class HostileBodyTest(unittest.TestCase):
    """A forged webhook must always surface as HesabeSignatureError: the handler
    documented in the README catches that and nothing else."""

    def _webhooks(self):
        return Webhooks(StubTransactions({"token": "PT1", "amount": "1.000"}))

    def test_non_string_token_is_rejected(self):
        for token in (123, {"a": 1}, [1, 2], True, None):
            with self.subTest(token):
                with self.assertRaises(HesabeSignatureError):
                    self._webhooks().verify({"token": token, "amount": "1.000"})

    def test_deeply_nested_json_is_rejected(self):
        """json.loads raises RecursionError here, which is not a ValueError."""
        with self.assertRaises(HesabeSignatureError):
            self._webhooks().parse("[" * 60_000 + "]" * 60_000)

    def test_absurd_claimed_amount_is_rejected(self):
        """Decimal cannot quantize 1e30, and the crash must not escape untyped."""
        with self.assertRaises(HesabeSignatureError):
            self._webhooks().verify({"token": "PT1", "amount": "1e30"})


if __name__ == "__main__":
    unittest.main()

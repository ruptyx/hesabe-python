"""Merchant-call plumbing: the 401 retry and the merchant-code guarantee."""

from __future__ import annotations

import unittest

from _support import CIPHER, FakeSend, json_response, make_config
from hesabe.errors import HesabeAuthenticationError
from hesabe.http import Transport, _HttpResponse
from hesabe.resource import Resource
from hesabe.session import MerchantSession

LOGIN_BODY = {
    "status": True,
    "response": {
        "token": {
            "token_type": "Bearer",
            "access_token": "TOK-A",
            "refresh_token": "REF-A",
            "expires_in": 900,
        }
    },
}


class RoutedSend(FakeSend):
    """Answers the login endpoint, and 401s everything else."""

    def __call__(self, method, url, headers, body, timeout):
        super().__call__(method, url, headers, body, timeout)
        if url.endswith("api/v1/login"):
            return json_response(200, LOGIN_BODY)
        return _HttpResponse(
            401, CIPHER.encrypt({"status": False, "message": "Unauthenticated"}), {}
        )

    def paths(self, needle: str):
        return [call for call in self.calls if needle in call["url"]]


class Probe(Resource):
    def refund(self):
        return self._merchant(
            "POST", "api/v1/refund", payload={"token": "T"}, idempotent=False
        )

    def report(self):
        return self._merchant("GET", "api/v1/report/transactions")


def probe():
    send = RoutedSend(_HttpResponse(200, "", {}))
    transport = Transport(make_config(), send=send)
    return Probe(transport, MerchantSession(transport)), send


class MerchantRetryTest(unittest.TestCase):
    def test_401_does_not_replay_a_money_moving_call(self):
        """Hesabe has no idempotency keys: a replayed refund would pay twice."""
        resource, send = probe()
        with self.assertRaises(HesabeAuthenticationError):
            resource.refund()
        self.assertEqual(len(send.paths("api/v1/refund")), 1)

    def test_401_replays_a_replayable_call(self):
        resource, send = probe()
        with self.assertRaises(HesabeAuthenticationError):
            resource.report()
        self.assertEqual(len(send.paths("api/v1/report")), 2)

    def test_a_rejected_login_is_not_attempted_twice(self):
        send = FakeSend(json_response(401, {"status": False, "message": "Unauthenticated"}))
        transport = Transport(make_config(), send=send)
        with self.assertRaises(HesabeAuthenticationError):
            Probe(transport, MerchantSession(transport)).report()
        self.assertEqual(len([c for c in send.calls if "login" in c["url"]]), 1)


class MerchantCodeTest(unittest.TestCase):
    def test_config_wins_over_a_caller_supplied_merchant_code(self):
        resource = Probe(Transport(make_config(), send=FakeSend()), None)
        payload = resource._with_merchant_code({"merchantCode": "999999", "a": 1})
        self.assertEqual(payload["merchantCode"], "842217")

    def test_none_values_are_dropped(self):
        resource = Probe(Transport(make_config(), send=FakeSend()), None)
        payload = resource._with_merchant_code({"a": None, "b": 0})
        self.assertNotIn("a", payload)
        self.assertEqual(payload["b"], 0)


if __name__ == "__main__":
    unittest.main()

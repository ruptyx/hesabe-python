"""Checkout payload construction: version selection, verify_card invariants."""

from __future__ import annotations

import unittest

from _support import CIPHER, make_transport

from hesabe.http import _HttpResponse
from hesabe.resources.checkout import Checkout
from hesabe.session import MerchantSession


def checkout_response():
    body = CIPHER.encrypt(
        {"status": True, "token": "tok123", "response": {"data": "SESSIONDATA"}}
    )
    return _HttpResponse(200, body, {})


def create(**kwargs):
    transport, send = make_transport(checkout_response())
    checkout = Checkout(transport, MerchantSession(transport))
    kwargs.setdefault("amount", 1.5)
    kwargs.setdefault("order_reference_number", "ORDER-1")
    kwargs.setdefault("response_url", "https://x.test/ok")
    kwargs.setdefault("failure_url", "https://x.test/fail")
    session = checkout.create(**kwargs)
    return session, send.sent_payload()


class VersionSelectionTest(unittest.TestCase):
    def test_plain_checkout_uses_version_2(self):
        _, payload = create()
        self.assertEqual(payload["version"], "2.0")
        self.assertEqual(payload["paymentType"], 0)
        self.assertEqual(payload["amount"], "1.500")
        self.assertEqual(payload["merchantCode"], "842217")

    def test_explicit_false_flags_do_not_mask_other_v3_features(self):
        """A regression guard: save_card=False must not downgrade a subscription."""
        _, payload = create(save_card=False, subscription={"recurring_frequency": 0})
        self.assertEqual(payload["version"], "3.0")
        self.assertEqual(payload["subscription"], "1")
        self.assertEqual(payload["recurringFrequency"], "0")

    def test_channel_embedded_and_customer_id_select_v3(self):
        for kwargs in ({"channel": "mobile"}, {"embedded": True}, {"customer_id": 7}):
            with self.subTest(kwargs):
                _, payload = create(**kwargs)
                self.assertEqual(payload["version"], "3.0")

    def test_explicit_version_wins(self):
        _, payload = create(embedded=True, version="9.9")
        self.assertEqual(payload["version"], "9.9")

    def test_embedded_flag_is_forwarded(self):
        _, payload = create(embedded=True)
        self.assertIs(payload["embeddedPayment"], True)

    def test_none_fields_are_omitted(self):
        _, payload = create()
        self.assertNotIn("name", payload)
        self.assertNotIn("saveCard", payload)
        self.assertNotIn("channel", payload)


class SessionShapeTest(unittest.TestCase):
    def test_payment_url_wraps_the_session_data(self):
        session, _ = create()
        self.assertEqual(session.token, "tok123")
        self.assertEqual(session.data, "SESSIONDATA")
        self.assertEqual(session.payment_url, "https://gw.test/payment?data=SESSIONDATA")


class VerifyCardTest(unittest.TestCase):
    def _verify(self, **kwargs):
        transport, send = make_transport(checkout_response())
        checkout = Checkout(transport, MerchantSession(transport))
        kwargs.setdefault("customer_id", 4117)
        kwargs.setdefault("order_reference_number", "SAVE-1")
        kwargs.setdefault("response_url", "https://x.test/ok")
        kwargs.setdefault("failure_url", "https://x.test/fail")
        checkout.verify_card(**kwargs)
        return send.sent_payload()

    def test_builds_a_zero_amount_mpgs_save_card_session(self):
        payload = self._verify()
        self.assertEqual(payload["amount"], "0.000")
        self.assertEqual(payload["paymentType"], 2)
        self.assertIs(payload["saveCard"], True)
        self.assertEqual(payload["customer_id"], 4117)
        self.assertEqual(payload["version"], "3.0")

    def test_caller_cannot_override_the_invariants(self):
        payload = self._verify(amount=9.9, payment_type=1, save_card=False)
        self.assertEqual(payload["amount"], "0.000")
        self.assertEqual(payload["paymentType"], 2)
        self.assertIs(payload["saveCard"], True)


if __name__ == "__main__":
    unittest.main()

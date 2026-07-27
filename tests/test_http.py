"""Transport behaviour: envelope sniffing, retries, Retry-After, error mapping."""

from __future__ import annotations

import json
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

from _support import CIPHER, FakeSend, json_response, make_transport, ok_envelope

from hesabe.errors import (
    HesabeAPIError,
    HesabeAuthenticationError,
    HesabeCardError,
    HesabeConnectionError,
    HesabeError,
    HesabeInvalidRequestError,
    HesabeRateLimitError,
)
from hesabe.http import _HttpResponse, _retry_after_seconds

HTML = "<html><body>502 Bad Gateway</body></html>"


def gateway_get(transport, **kwargs):
    return transport.request("GET", "api/thing", base_url="https://gw.test", **kwargs)


def gateway_post(transport, **kwargs):
    kwargs.setdefault("payload", {"a": 1})
    kwargs.setdefault("idempotent", False)
    return transport.request("POST", "api/thing", base_url="https://gw.test", **kwargs)


class ParseVariantsTest(unittest.TestCase):
    def _envelope(self, response: _HttpResponse):
        transport, _ = make_transport(response)
        return transport.envelope("GET", "x", base_url="https://gw.test")

    def test_bare_hex_body(self):
        body = CIPHER.encrypt({"status": True, "response": {"ok": 1}})
        self.assertEqual(self._envelope(_HttpResponse(200, body, {}))["response"], {"ok": 1})

    def test_json_wrapped_hex_string(self):
        body = json.dumps(CIPHER.encrypt({"status": True, "response": {"ok": 2}}))
        self.assertEqual(self._envelope(_HttpResponse(200, body, {}))["response"], {"ok": 2})

    def test_nested_response_hex(self):
        inner = CIPHER.encrypt({"status": True, "response": {"ok": 3}})
        body = json.dumps({"response": inner})
        self.assertEqual(self._envelope(_HttpResponse(200, body, {}))["response"], {"ok": 3})

    def test_plain_json_envelope(self):
        body = json.dumps({"status": True, "response": {"ok": 4}})
        self.assertEqual(self._envelope(_HttpResponse(200, body, {}))["response"], {"ok": 4})

    def test_html_at_200_raises_api_error(self):
        with self.assertRaises(HesabeAPIError):
            self._envelope(_HttpResponse(200, HTML, {}))

    def test_encrypted_non_dict_raises_api_error(self):
        body = CIPHER.encrypt([1, 2, 3])
        with self.assertRaises(HesabeAPIError):
            self._envelope(_HttpResponse(200, body, {}))


@mock.patch("hesabe.http.time.sleep")
class RetryTest(unittest.TestCase):
    def test_unparseable_5xx_retries_idempotent_calls(self, sleep):
        transport, send = make_transport(_HttpResponse(502, HTML, {}), ok_envelope({"v": 1}))
        self.assertEqual(gateway_get(transport), {"v": 1})
        self.assertEqual(len(send.calls), 2)

    def test_unparseable_5xx_fails_fast_for_non_idempotent_calls(self, sleep):
        transport, send = make_transport(_HttpResponse(502, HTML, {}))
        with self.assertRaises(HesabeAPIError):
            gateway_post(transport)
        self.assertEqual(len(send.calls), 1)

    def test_429_retries_even_non_idempotent_calls(self, sleep):
        rejected = json_response(429, {"status": False, "message": "Too many requests"})
        transport, send = make_transport(rejected, ok_envelope({"v": 2}))
        self.assertEqual(gateway_post(transport), {"v": 2})
        self.assertEqual(len(send.calls), 2)

    def test_429_exhausts_into_rate_limit_error(self, sleep):
        rejected = json_response(429, {"status": False, "message": "Too many requests"})
        transport, send = make_transport(rejected, max_retries=1)
        with self.assertRaises(HesabeRateLimitError):
            gateway_get(transport)
        self.assertEqual(len(send.calls), 2)

    def test_retry_after_seconds_header_wins_over_backoff(self, sleep):
        rejected = json_response(
            429, {"status": False, "message": "slow down"}, {"Retry-After": "7"}
        )
        transport, _ = make_transport(rejected, ok_envelope({"v": 3}))
        self.assertEqual(gateway_get(transport), {"v": 3})
        sleep.assert_called_once_with(7.0)

    def test_retry_after_is_clamped_to_30_seconds(self, sleep):
        rejected = json_response(
            503, {"status": False, "message": "maintenance"}, {"Retry-After": "600"}
        )
        transport, _ = make_transport(rejected, ok_envelope({"v": 4}))
        self.assertEqual(gateway_get(transport), {"v": 4})
        sleep.assert_called_once_with(30.0)

    def test_malformed_retry_after_falls_back_to_backoff(self, sleep):
        rejected = json_response(
            429, {"status": False, "message": "slow down"}, {"Retry-After": "soon"}
        )
        transport, _ = make_transport(rejected, ok_envelope({"v": 5}))
        self.assertEqual(gateway_get(transport), {"v": 5})
        self.assertLess(sleep.call_args[0][0], 5.0)

    def test_connection_error_retries_idempotent_calls(self, sleep):
        transport, send = make_transport(OSError("boom"), ok_envelope({"v": 6}))
        self.assertEqual(gateway_get(transport), {"v": 6})
        self.assertEqual(len(send.calls), 2)

    def test_connection_error_fails_fast_for_non_idempotent_calls(self, sleep):
        transport, send = make_transport(OSError("boom"))
        with self.assertRaises(HesabeConnectionError):
            gateway_post(transport)
        self.assertEqual(len(send.calls), 1)


class ErrorMappingTest(unittest.TestCase):
    def _raise(self, response):
        transport, _ = make_transport(response, max_retries=0)
        with self.assertRaises(Exception) as ctx:
            gateway_get(transport)
        return ctx.exception

    def test_401_maps_to_authentication_error(self):
        error = self._raise(json_response(401, {"status": False, "message": "Invalid Signature."}))
        self.assertIsInstance(error, HesabeAuthenticationError)

    def test_decline_message_maps_to_card_error(self):
        error = self._raise(json_response(400, {"status": False, "message": "Insufficient funds"}))
        self.assertIsInstance(error, HesabeCardError)

    def test_field_errors_are_extracted(self):
        body = {"status": False, "message": "Invalid Request Data",
                "data": {"amount": ["The amount field is required."]}}
        error = self._raise(json_response(422, body))
        self.assertIsInstance(error, HesabeInvalidRequestError)
        self.assertEqual(error.field_errors, {"amount": ["The amount field is required."]})


class RequestBuildingTest(unittest.TestCase):
    def test_get_payload_is_encrypted_into_data_query_param(self):
        transport, send = make_transport(ok_envelope({}))
        gateway_get(transport, payload={"merchantCode": "842217"})
        query = parse_qs(urlparse(send.calls[0]["url"]).query)
        self.assertEqual(CIPHER.decrypt(query["data"][0]), {"merchantCode": "842217"})

    def test_post_payload_is_encrypted_into_data_body_field(self):
        transport, send = make_transport(ok_envelope({}))
        gateway_post(transport, payload={"amount": "1.000"})
        self.assertEqual(send.sent_payload(), {"amount": "1.000"})

    def test_access_code_header_only_on_encrypted_calls(self):
        transport, send = make_transport(json_response(200, {"status": True, "response": {}}))
        transport.request(
            "POST", "login", base_url="https://api.test",
            payload={"username": "u"}, encrypted=False, idempotent=False,
        )
        self.assertNotIn("accessCode", send.calls[0]["headers"])

        transport2, send2 = make_transport(ok_envelope({}))
        gateway_get(transport2, payload={"x": 1})
        self.assertEqual(send2.calls[0]["headers"]["accessCode"], "ACCESS-CODE")


class ErrorStatusTest(unittest.TestCase):
    def test_readable_body_at_an_error_status_is_not_success(self):
        """A proxy's 403 parses cleanly; returning it would read as success and
        hand the caller None."""
        transport, _ = make_transport(json_response(403, {"message": "forbidden"}))
        with self.assertRaises(HesabeAuthenticationError):
            gateway_get(transport)

    def test_redirect_is_refused_rather_than_returned(self):
        transport, send = make_transport(json_response(301, {"url": "https://elsewhere.test"}))
        with self.assertRaises(HesabeError):
            gateway_get(transport)
        self.assertEqual(len(send.calls), 1)

    def test_non_string_message_does_not_crash_the_error_path(self):
        """Localised {"en": ..., "ar": ...} messages appear in the wild."""
        body = CIPHER.encrypt({"status": False, "message": {"en": "Declined"}, "code": 506})
        transport, _ = make_transport(_HttpResponse(400, body, {}))
        with self.assertRaises(HesabeError) as caught:
            gateway_get(transport)
        self.assertIn("Declined", caught.exception.message)


class SecretExposureTest(unittest.TestCase):
    def test_connection_errors_do_not_carry_the_request(self):
        """requests' exceptions keep the PreparedRequest, whose body is the
        panel login."""
        transport, _ = make_transport(OSError("connection reset"))
        with self.assertRaises(HesabeConnectionError) as caught:
            transport.request(
                "POST", "api/v1/login", base_url="https://api.test",
                payload={"password": "hunter2"}, encrypted=False, idempotent=False,
            )
        self.assertIsNone(caught.exception.raw)

    def test_unencrypted_error_bodies_are_not_attached(self):
        """Login runs in clear text, so its body holds the bearer token."""
        body = {"status": False, "message": "nope", "token": {"access_token": "AT"}}
        transport, _ = make_transport(json_response(401, body))
        with self.assertRaises(HesabeAuthenticationError) as caught:
            transport.request(
                "POST", "api/v1/login", base_url="https://api.test",
                payload={"username": "u"}, encrypted=False, idempotent=False,
            )
        self.assertIsNone(caught.exception.raw)


class RetryAfterGrammarTest(unittest.TestCase):
    def test_only_plain_seconds_and_http_dates_are_honoured(self):
        # float() would take "inf" (a 30s sleep), "nan" (an instant hot retry)
        # and PEP 515 underscores; the TypeScript twin takes none of them.
        for header in ("inf", "nan", "1_000", "0x10", "", " ", "-3", "abc"):
            with self.subTest(header):
                self.assertIsNone(_retry_after_seconds({"Retry-After": header}))
        self.assertEqual(_retry_after_seconds({"Retry-After": "5"}), 5.0)
        self.assertEqual(_retry_after_seconds({"Retry-After": "0"}), 0.0)
        self.assertEqual(_retry_after_seconds({"Retry-After": "900"}), 30.0)

    def test_header_lookup_is_case_insensitive_for_custom_senders(self):
        self.assertEqual(_retry_after_seconds({"retry-after": "7"}), 7.0)


if __name__ == "__main__":
    unittest.main()

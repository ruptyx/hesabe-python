"""MerchantSession concurrency: single-flight login, stale-while-refresh."""

from __future__ import annotations

import json
import threading
import time
import unittest

from _support import FakeSend, json_response, make_config

from hesabe.errors import (
    HesabeAuthenticationError,
    HesabeConnectionError,
    HesabeError,
)
from hesabe.http import Transport, _HttpResponse
from hesabe.session import MerchantSession


def login_response(token="TOK-A", refresh="REF-A", expires=900):
    return json_response(
        200,
        {
            "status": True,
            "response": {
                "token": {
                    "token_type": "Bearer",
                    "access_token": token,
                    "refresh_token": refresh,
                    "expires_in": expires,
                }
            },
        },
    )


class GatedSend(FakeSend):
    """Blocks inside the send until released, so tests can stage waiters."""

    def __init__(self, *responses):
        super().__init__(*responses)
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, method, url, headers, body, timeout):
        self.entered.set()
        assert self.release.wait(5), "test never released the gated send"
        return super().__call__(method, url, headers, body, timeout)


def make_session(send):
    transport = Transport(make_config(), send=send)
    return MerchantSession(transport)


class SingleFlightTest(unittest.TestCase):
    def test_concurrent_callers_share_one_login(self):
        send = GatedSend(login_response())
        session = make_session(send)

        tokens = []
        threads = [
            threading.Thread(target=lambda: tokens.append(session.token()))
            for _ in range(6)
        ]
        for thread in threads:
            thread.start()
        assert send.entered.wait(5)
        time.sleep(0.05)  # let the rest queue up as waiters
        send.release.set()
        for thread in threads:
            thread.join(5)

        self.assertEqual(tokens, ["TOK-A"] * 6)
        self.assertEqual(len(send.calls), 1)

    def test_waiters_reraise_the_leaders_exception(self):
        send = GatedSend(OSError("network down"))
        session = make_session(send)

        errors = []

        def call():
            try:
                session.token()
            except HesabeError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=call) for _ in range(2)]
        threads[0].start()
        assert send.entered.wait(5)
        threads[1].start()
        time.sleep(0.05)
        send.release.set()
        for thread in threads:
            thread.join(5)

        self.assertEqual(len(errors), 2)
        self.assertIsInstance(errors[0], HesabeConnectionError)
        self.assertIs(errors[0], errors[1])
        self.assertEqual(len(send.calls), 1)


class StaleWhileRefreshTest(unittest.TestCase):
    def test_other_callers_use_the_valid_token_during_refresh(self):
        send = GatedSend(login_response(token="TOK-NEW"))
        session = make_session(send)
        with session._lock:
            session._access_token = "TOK-OLD"
            session._expires_at = time.time() + 30  # inside margin, not expired

        leader_result = []
        leader = threading.Thread(target=lambda: leader_result.append(session.token()))
        leader.start()
        assert send.entered.wait(5)

        # Refresh is in flight, but the old token is still valid.
        self.assertEqual(session.token(), "TOK-OLD")

        send.release.set()
        leader.join(5)
        self.assertEqual(leader_result, ["TOK-NEW"])
        self.assertEqual(session.token(), "TOK-NEW")


class RefreshFallbackTest(unittest.TestCase):
    def test_failed_refresh_falls_back_to_login(self):
        send = FakeSend(
            json_response(401, {"status": False, "message": "Invalid Signature."}),
            login_response(token="TOK-B"),
        )
        session = make_session(send)
        with session._lock:
            session._refresh_token = "REF-STALE"

        self.assertEqual(session.token(), "TOK-B")
        self.assertTrue(send.calls[0]["url"].endswith("api/v1/token-refresh"))
        self.assertTrue(send.calls[1]["url"].endswith("api/v1/login"))
        self.assertEqual(json.loads(send.calls[0]["body"]), {"refreshToken": "REF-STALE"})

    def test_missing_access_token_in_response_raises(self):
        send = FakeSend(json_response(200, {"status": True, "response": {"token": {}}}))
        session = make_session(send)
        with self.assertRaises(HesabeAuthenticationError):
            session.token()

    def test_invalidate_forces_a_new_login(self):
        send = FakeSend(login_response(token="TOK-1"), login_response(token="TOK-2", refresh=None))
        session = make_session(send)
        self.assertEqual(session.token(), "TOK-1")
        session.invalidate()
        self.assertEqual(session.token(), "TOK-2")
        # invalidate() cleared the refresh token, so the second call logged in.
        self.assertTrue(send.calls[1]["url"].endswith("api/v1/login"))


if __name__ == "__main__":
    unittest.main()

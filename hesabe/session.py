from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .errors import HesabeAuthenticationError, HesabeConfigurationError, HesabeError
from .http import Transport

_REFRESH_MARGIN_SECONDS = 60
_DEFAULT_EXPIRES_IN_SECONDS = 900


def _expires_in_seconds(token: Dict[str, Any]) -> float:
    """
    Absent means Hesabe's documented 15 minutes; anything else unusable — zero,
    negative, or not a number — means treat the token as already expired and
    fetch another rather than trust one the server may have declared dead.
    """
    raw = token.get("expires_in")
    if raw is None:
        return _DEFAULT_EXPIRES_IN_SECONDS
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not 0 <= seconds < 1e9:  # NaN, negative, or absurd
        return 0.0
    return seconds


class _Inflight:
    """Result slot for the single login/refresh a leader thread runs."""

    __slots__ = ("done", "token", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.token: Optional[str] = None
        self.error: Optional[BaseException] = None


class MerchantSession:
    """
    Merchant API and Smart POS sit behind a bearer token that expires after
    15 minutes. The session logs in on first use, refreshes ahead of expiry, and
    falls back to a full login if the refresh token is also stale.

    The lock guards state only; network calls run outside it. One leader thread
    performs the login while the others either keep using the still-valid token
    or wait on the leader's result (re-raising its exception on failure).
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at = 0.0
        self._inflight: Optional[_Inflight] = None
        self._generation = 0

    def token(self) -> str:
        now = time.time()
        with self._lock:
            if self._access_token and now < self._expires_at - _REFRESH_MARGIN_SECONDS:
                return self._access_token

            inflight = self._inflight
            leader = inflight is None
            if leader:
                inflight = self._inflight = _Inflight()
            elif self._access_token and now < self._expires_at:
                # Refresh started ahead of expiry: the current token is still
                # valid, so only the leader waits on the network.
                return self._access_token
            refresh_token = self._refresh_token
            generation = self._generation

        assert inflight is not None
        if not leader:
            inflight.done.wait()
            if inflight.error is not None:
                raise inflight.error
            assert inflight.token is not None
            return inflight.token

        try:
            token = self._acquire(refresh_token, generation)
        except BaseException as exc:
            inflight.error = exc
            raise
        else:
            inflight.token = token
            return token
        finally:
            # Always published, so a waiter can never be left blocked on an
            # event that nobody sets.
            with self._lock:
                self._inflight = None
            inflight.done.set()

    def invalidate(self) -> None:
        # An in-flight acquire is left running on purpose: it will publish a
        # fresh token, and the 401-retry path joins it instead of stampeding.
        # Bumping the generation stops it publishing a token fetched before the
        # invalidation, which would silently undo this call.
        with self._lock:
            self._access_token = None
            self._refresh_token = None
            self._expires_at = 0.0
            self._generation += 1

    def _acquire(self, refresh_token: Optional[str], generation: int) -> str:
        if refresh_token:
            try:
                return self._exchange(
                    "api/v1/token-refresh", {"refreshToken": refresh_token}, generation
                )
            except HesabeError:
                with self._lock:
                    if self._refresh_token == refresh_token:
                        self._access_token = None
                        self._refresh_token = None
                        self._expires_at = 0.0

        config = self._transport.config
        if not config.username or not config.password:
            raise HesabeConfigurationError(
                "Merchant API access needs a panel login. Set "
                "HESABE_MERCHANT_USERNAME and HESABE_MERCHANT_PASSWORD."
            )
        return self._exchange(
            "api/v1/login",
            {"username": config.username, "password": config.password},
            generation,
        )

    def _exchange(self, path: str, payload: Dict[str, Any], generation: int) -> str:
        result = self._transport.request(
            "POST",
            path,
            base_url=self._transport.config.merchant_api_url,
            payload=payload,
            encrypted=False,
            idempotent=False,
        )
        token = (result or {}).get("token") or {}
        access_token = token.get("access_token")
        if not access_token:
            raise HesabeAuthenticationError("Hesabe did not return an access token")

        with self._lock:
            if generation == self._generation:
                self._access_token = access_token
                self._refresh_token = token.get("refresh_token")
                self._expires_at = time.time() + _expires_in_seconds(token)
        return access_token

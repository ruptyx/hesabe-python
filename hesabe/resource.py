from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .errors import HesabeAuthenticationError
from .http import Transport
from .session import MerchantSession


class Resource:
    def __init__(self, transport: Transport, session: MerchantSession) -> None:
        self._transport = transport
        self._session = session

    def _with_merchant_code(self, payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Every Hesabe payload carries the merchant code; callers never supply it."""
        merged: Dict[str, Any] = {}
        if payload:
            merged.update({k: v for k, v in payload.items() if v is not None})
        # Written last: a stray caller key must not redirect the call to another
        # merchant's account.
        merged["merchantCode"] = self._transport.config.merchant_code
        return merged

    def _gateway(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._transport.request(
            method, path, base_url=self._transport.config.gateway_url, **kwargs
        )

    def _gateway_envelope(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        return self._transport.envelope(
            method, path, base_url=self._transport.config.gateway_url, **kwargs
        )

    def _merchant(self, method: str, path: str, **kwargs: Any) -> Any:
        def send(bearer: str) -> Any:
            return self._transport.request(
                method,
                path,
                base_url=self._transport.config.merchant_api_url,
                bearer_token=bearer,
                **kwargs,
            )

        idempotent = kwargs.get("idempotent")
        replayable = idempotent if idempotent is not None else method == "GET"

        # Taken outside the retry so a rejected panel login surfaces as itself
        # instead of provoking a second login attempt.
        bearer = self._session.token()
        try:
            return send(bearer)
        except HesabeAuthenticationError:
            # A 401 can arrive after Hesabe already processed the call, and there
            # are no idempotency keys — replaying a refund or an invoice would
            # move money twice. Only replayable calls get a second attempt.
            if not replayable:
                raise
            self._session.invalidate()
            return send(self._session.token())

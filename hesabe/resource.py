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
        merged: Dict[str, Any] = {"merchantCode": self._transport.config.merchant_code}
        if payload:
            merged.update({k: v for k, v in payload.items() if v is not None})
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
        def send() -> Any:
            return self._transport.request(
                method,
                path,
                base_url=self._transport.config.merchant_api_url,
                bearer_token=self._session.token(),
                **kwargs,
            )

        try:
            return send()
        except HesabeAuthenticationError:
            self._session.invalidate()
            return send()

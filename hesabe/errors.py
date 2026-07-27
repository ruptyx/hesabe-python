from __future__ import annotations

from typing import Any, Dict, Optional

_DECLINE_PATTERNS = (
    "insufficient funds",
    "do not honour",
    "do not honor",
    "declined",
    "not eligible for merchant-initiated charge",
    "expired card",
    "stolen",
    "lost card",
    "invalid card",
)


class HesabeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[int] = None,
        field_errors: Optional[Dict[str, Any]] = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.field_errors = field_errors or {}
        self.raw = raw

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r}, code={self.code})"


class HesabeConfigurationError(HesabeError):
    """Missing or malformed credentials, raised before any network call."""


class HesabeAuthenticationError(HesabeError):
    """The gateway rejected the access code, merchant code, or bearer token."""


class HesabeInvalidRequestError(HesabeError):
    """The request was well formed but the gateway refused it."""


class HesabeCardError(HesabeError):
    """The issuer or scheme declined the payment. Retrying rarely helps."""


class HesabeRateLimitError(HesabeError):
    """Too many requests. Direct-payment endpoints allow 30 per minute."""


class HesabeAPIError(HesabeError):
    """Hesabe returned 5xx or an unreadable body."""


class HesabeConnectionError(HesabeError):
    """The request never produced a response."""


class HesabeSignatureError(HesabeError):
    """A payload failed to decrypt, or a webhook could not be reconciled."""


def error_from_response(
    message: str,
    *,
    status_code: Optional[int] = None,
    code: Optional[int] = None,
    field_errors: Optional[Dict[str, Any]] = None,
    raw: Any = None,
) -> HesabeError:
    kwargs = {
        "status_code": status_code,
        "code": code,
        "field_errors": field_errors,
        "raw": raw,
    }
    normalized = message.lower()

    if status_code in (401, 403) or code == 501:
        return HesabeAuthenticationError(message, **kwargs)
    if status_code == 429:
        return HesabeRateLimitError(message, **kwargs)
    if any(pattern in normalized for pattern in _DECLINE_PATTERNS):
        return HesabeCardError(message, **kwargs)
    if status_code is not None and status_code >= 500:
        return HesabeAPIError(message, **kwargs)
    return HesabeInvalidRequestError(message, **kwargs)

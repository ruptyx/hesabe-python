from __future__ import annotations

import email.utils
import json
import random
import time
import urllib.parse
from typing import Any, Callable, Dict, Mapping, NamedTuple, Optional, Tuple

import requests

from .config import HesabeConfig
from .crypto import HesabeCipher, is_hex
from .errors import HesabeAPIError, HesabeConnectionError, HesabeError, error_from_response
from .types import HesabeObject

_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_RETRY_AFTER_STATUS = frozenset({429, 503})
_RETRY_AFTER_MAX_SECONDS = 30.0
_USER_AGENT = "hesabe-python/1.1.0"

# Retained from 1.0, when the HTTP implementation was selected at import time.
BACKEND = "requests"


class _HttpResponse(NamedTuple):
    status: int
    text: str
    headers: Mapping[str, str]


# method, url, headers, body, timeout -> response. The sender never raises on
# HTTP status codes; only transport failures (DNS, TLS, timeout) may raise.
SendFunc = Callable[[str, str, Dict[str, str], Optional[bytes], float], _HttpResponse]

_session = requests.Session()


def _send_default(
    method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float
) -> _HttpResponse:
    """Sends over a shared pooled Session so TLS connections are reused.

    Redirects are refused: Hesabe never redirects API calls, and following one
    would re-send the accessCode header to wherever it points.
    """
    response = _session.request(
        method, url, headers=headers, data=body, timeout=timeout, allow_redirects=False
    )
    return _HttpResponse(
        response.status_code, response.content.decode("utf-8", "replace"), response.headers
    )


def _backoff(attempt: int) -> float:
    return min(2**attempt * 0.25, 4.0) + random.uniform(0, 0.2)


def _retry_after_seconds(headers: Mapping[str, str]) -> Optional[float]:
    value = headers.get("Retry-After")
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        seconds = when.timestamp() - time.time()
    return max(0.0, min(seconds, _RETRY_AFTER_MAX_SECONDS))


def _retry_delay(status: int, headers: Mapping[str, str], attempt: int) -> float:
    """Server-provided Retry-After wins over backoff on 429/503, capped at 30s."""
    if status in _RETRY_AFTER_STATUS:
        retry_after = _retry_after_seconds(headers)
        if retry_after is not None:
            return retry_after
    return _backoff(attempt)


def _field_errors(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict) and any(isinstance(v, list) for v in value.values()):
        return {k: v for k, v in value.items() if isinstance(v, list)}
    return None


class Transport:
    def __init__(self, config: HesabeConfig, send: Optional[SendFunc] = None) -> None:
        self.config = config
        self.cipher = HesabeCipher(config.secret_key, config.iv_key)
        self._send = send or _send_default

    def request(
        self,
        method: str,
        path: str,
        *,
        base_url: str,
        payload: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        encrypted: bool = True,
        bearer_token: Optional[str] = None,
        idempotent: Optional[bool] = None,
    ) -> Any:
        envelope = self.envelope(
            method,
            path,
            base_url=base_url,
            payload=payload,
            query=query,
            encrypted=encrypted,
            bearer_token=bearer_token,
            idempotent=idempotent,
        )
        body = envelope.get("response")
        if body is None:
            body = envelope.get("data")
        return HesabeObject.wrap(body)

    def envelope(
        self,
        method: str,
        path: str,
        *,
        base_url: str,
        payload: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
        encrypted: bool = True,
        bearer_token: Optional[str] = None,
        idempotent: Optional[bool] = None,
    ) -> Dict[str, Any]:
        replayable = idempotent if idempotent is not None else method == "GET"
        url = self._build_url(base_url, path, payload, query, encrypted, method)
        data, headers = self._build_body(payload, encrypted, method, bearer_token)

        last_error: Optional[HesabeError] = None
        delay: Optional[float] = None
        for attempt in range(self.config.max_retries + 1):
            if attempt:
                time.sleep(delay if delay is not None else _backoff(attempt - 1))
                delay = None

            try:
                status, raw, response_headers = self._send(
                    method, url, headers, data, self.config.timeout
                )
            except Exception as exc:
                last_error = HesabeConnectionError(
                    f"Could not reach Hesabe at {url}: {exc}", raw=exc
                )
                if replayable:
                    continue
                raise last_error from exc

            # A 429 was rejected before processing, so it is safe to replay even
            # for non-idempotent calls.
            can_retry = (
                status == 429 or (replayable and status in _RETRYABLE_STATUS)
            ) and attempt < self.config.max_retries

            try:
                envelope = self._parse(raw, encrypted, status)
            except HesabeAPIError as exc:
                if can_retry:
                    last_error = exc
                    delay = _retry_delay(status, response_headers, attempt)
                    continue
                raise

            if envelope.get("status") is False:
                error = error_from_response(
                    envelope.get("message") or "Hesabe request failed",
                    status_code=status,
                    code=envelope.get("code"),
                    field_errors=_field_errors(envelope.get("data")),
                    raw=envelope,
                )
                if can_retry:
                    last_error = error
                    delay = _retry_delay(status, response_headers, attempt)
                    continue
                raise error

            if status in _RETRYABLE_STATUS:
                last_error = HesabeAPIError(
                    f"Hesabe returned HTTP {status}", status_code=status, raw=raw
                )
                if can_retry:
                    delay = _retry_delay(status, response_headers, attempt)
                    continue
                raise last_error

            return envelope

        raise last_error or HesabeAPIError("Hesabe request failed after retries")

    def _build_url(
        self,
        base_url: str,
        path: str,
        payload: Optional[Mapping[str, Any]],
        query: Optional[Mapping[str, Any]],
        encrypted: bool,
        method: str,
    ) -> str:
        params: Dict[str, str] = {}
        if encrypted and method == "GET" and payload is not None:
            params["data"] = self.cipher.encrypt(dict(payload))
        for key, value in (query or {}).items():
            if value is not None:
                params[key] = str(value)

        url = f"{base_url}/{path.lstrip('/')}"
        return f"{url}?{urllib.parse.urlencode(params)}" if params else url

    def _build_body(
        self,
        payload: Optional[Mapping[str, Any]],
        encrypted: bool,
        method: str,
        bearer_token: Optional[str],
    ) -> Tuple[Optional[bytes], Dict[str, str]]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if encrypted:
            headers["accessCode"] = self.config.access_code
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        if method == "GET" or payload is None:
            return None, headers

        body = (
            {"data": self.cipher.encrypt(dict(payload))} if encrypted else dict(payload)
        )
        return json.dumps(body).encode("utf-8"), headers

    def _parse(self, raw: str, encrypted: bool, status: int) -> Dict[str, Any]:
        """
        Hesabe answers with a bare hex string on success but drops to plain JSON
        for auth failures and the login endpoints, so the body is sniffed rather
        than assumed from the status code.
        """
        trimmed = raw.strip()

        if encrypted and is_hex(trimmed):
            return self._require_dict(self.cipher.decrypt(trimmed), status)
        try:
            parsed = json.loads(trimmed)
        except ValueError:
            raise HesabeAPIError(
                f"Unreadable response from Hesabe (HTTP {status})",
                status_code=status,
                raw=trimmed[:500],
            ) from None

        if isinstance(parsed, str) and is_hex(parsed):
            return self._require_dict(self.cipher.decrypt(parsed), status)
        if isinstance(parsed, dict):
            nested = parsed.get("response")
            if isinstance(nested, str) and is_hex(nested):
                return self._require_dict(self.cipher.decrypt(nested), status)
            return parsed

        raise HesabeAPIError(
            f"Unexpected response from Hesabe (HTTP {status})",
            status_code=status,
            raw=trimmed[:500],
        )

    def _require_dict(self, value: Any, status: int) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise HesabeAPIError(
                f"Unexpected response from Hesabe (HTTP {status})",
                status_code=status,
                raw=value,
            )
        return value

"""Shared helpers for the unit tests. Not collected by unittest discover."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hesabe.config import HesabeConfig  # noqa: E402
from hesabe.crypto import HesabeCipher  # noqa: E402
from hesabe.http import Transport, _HttpResponse  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

SECRET_KEY = "PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg"
IV_KEY = "5NVdrlPVNnjo2Jy9"

CIPHER = HesabeCipher(SECRET_KEY, IV_KEY)


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_config(**overrides: Any) -> HesabeConfig:
    values: Dict[str, Any] = dict(
        merchant_code="842217",
        access_code="ACCESS-CODE",
        secret_key=SECRET_KEY,
        iv_key=IV_KEY,
        environment="sandbox",
        gateway_url="https://gw.test",
        merchant_api_url="https://api.test",
        timeout=5.0,
        max_retries=2,
        username="user",
        password="pass",
    )
    values.update(overrides)
    return HesabeConfig(**values)


def ok_envelope(payload: Any = None, **extra: Any) -> _HttpResponse:
    """A 200 response whose body is the encrypted Hesabe success envelope."""
    envelope: Dict[str, Any] = {
        "status": True,
        "response": payload if payload is not None else {},
    }
    envelope.update(extra)
    return _HttpResponse(200, CIPHER.encrypt(envelope), {})


def json_response(status: int, body: Any, headers: Dict[str, str] = {}) -> _HttpResponse:
    return _HttpResponse(status, json.dumps(body), dict(headers))


class FakeSend:
    """Scripted SendFunc: yields queued responses, repeating the last one."""

    def __init__(self, *responses: Union[_HttpResponse, Exception]) -> None:
        self.queue: List[Union[_HttpResponse, Exception]] = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def __call__(
        self, method: str, url: str, headers: Dict[str, str], body: Any, timeout: float
    ) -> _HttpResponse:
        with self.lock:
            self.calls.append(
                {"method": method, "url": url, "headers": dict(headers), "body": body}
            )
            result = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(result, Exception):
            raise result
        return result

    def sent_payload(self, index: int = -1) -> Any:
        """The plaintext payload of a captured request body."""
        body = self.calls[index]["body"]
        data = json.loads(body.decode("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("data"), str):
            return CIPHER.decrypt(data["data"])
        return data


def make_transport(*responses: Union[_HttpResponse, Exception], **config_overrides: Any):
    send = FakeSend(*responses)
    transport = Transport(make_config(**config_overrides), send=send)
    return transport, send

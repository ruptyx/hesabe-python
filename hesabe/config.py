from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import HesabeConfigurationError

BASE_URLS = {
    "sandbox": {
        "gateway": "https://sandbox.hesabe.com",
        "merchant_api": "https://merchantapisandbox.hesabe.com",
    },
    "production": {
        "gateway": "https://api.hesabe.com",
        "merchant_api": "https://merchantapi.hesabe.com",
    },
}

_loaded: set = set()


def load_env_file(path: str = ".env") -> None:
    """Fills os.environ from a dotenv file without overwriting real variables."""
    resolved = Path(path).resolve()
    if resolved in _loaded:
        return
    _loaded.add(resolved)

    try:
        contents = resolved.read_text(encoding="utf-8")
    except OSError:
        return

    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _, raw = stripped.partition("=")
        key = key.removeprefix("export ").strip()
        if not key or key in os.environ:
            continue

        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #")[0].strip()
        os.environ[key] = value


def _required(value: Optional[str], option: str, variable: str) -> str:
    if not value:
        raise HesabeConfigurationError(
            f"Missing {option}. Set {variable} in your environment or pass "
            f"{option}= to Hesabe()."
        )
    return value


def _resolve_environment(explicit: Optional[str]) -> str:
    """
    Anything unrecognised is rejected rather than quietly treated as sandbox: a
    typo in a production deploy would otherwise send live traffic to the sandbox,
    where payments succeed and no money moves.
    """
    value = explicit if explicit is not None else os.environ.get("HESABE_ENVIRONMENT")
    if not value:
        return "sandbox"
    if value in BASE_URLS:
        return value

    raise HesabeConfigurationError(
        f"Unrecognised environment {value!r}. "
        "HESABE_ENVIRONMENT must be exactly 'sandbox' or 'production'."
    )


def _as_number(value: Optional[str], fallback: float) -> float:
    try:
        return float(value) if value else fallback
    except ValueError:
        return fallback


@dataclass(frozen=True)
class HesabeConfig:
    merchant_code: str
    access_code: str
    secret_key: str
    iv_key: str
    environment: str
    gateway_url: str
    merchant_api_url: str
    timeout: float
    max_retries: int
    username: Optional[str] = None
    password: Optional[str] = None


def resolve_config(
    *,
    merchant_code: Optional[str] = None,
    access_code: Optional[str] = None,
    secret_key: Optional[str] = None,
    iv_key: Optional[str] = None,
    environment: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    gateway_url: Optional[str] = None,
    merchant_api_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    env_path: Optional[str] = None,
) -> HesabeConfig:
    # Dotenv loading is opt-in: mutating os.environ is too surprising for a
    # library default. Pass env_path=".env" (or call load_env_file) to use one.
    if env_path is not None:
        load_env_file(env_path)

    resolved_environment = _resolve_environment(environment)
    defaults = BASE_URLS[resolved_environment]

    return HesabeConfig(
        merchant_code=_required(
            merchant_code or os.environ.get("HESABE_MERCHANT_CODE"),
            "merchant_code",
            "HESABE_MERCHANT_CODE",
        ),
        access_code=_required(
            access_code or os.environ.get("HESABE_ACCESS_CODE"),
            "access_code",
            "HESABE_ACCESS_CODE",
        ),
        secret_key=_required(
            secret_key or os.environ.get("HESABE_SECRET_KEY"),
            "secret_key",
            "HESABE_SECRET_KEY",
        ),
        iv_key=_required(
            iv_key or os.environ.get("HESABE_IV_KEY"), "iv_key", "HESABE_IV_KEY"
        ),
        environment=resolved_environment,
        username=username or os.environ.get("HESABE_MERCHANT_USERNAME"),
        password=password or os.environ.get("HESABE_MERCHANT_PASSWORD"),
        gateway_url=(
            gateway_url or os.environ.get("HESABE_GATEWAY_URL") or defaults["gateway"]
        ).rstrip("/"),
        merchant_api_url=(
            merchant_api_url
            or os.environ.get("HESABE_MERCHANT_API_URL")
            or defaults["merchant_api"]
        ).rstrip("/"),
        timeout=timeout if timeout is not None else _as_number(os.environ.get("HESABE_TIMEOUT"), 30.0),
        max_retries=int(
            max_retries
            if max_retries is not None
            else _as_number(os.environ.get("HESABE_MAX_RETRIES"), 2)
        ),
    )

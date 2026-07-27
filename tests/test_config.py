"""Configuration resolution: environment guard, opt-in dotenv, env parsing."""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import _support  # noqa: F401  (sys.path setup)

from hesabe.config import resolve_config
from hesabe.errors import HesabeConfigurationError

CREDENTIALS = dict(
    merchant_code="842217",
    access_code="ACCESS",
    secret_key="PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg",
    iv_key="5NVdrlPVNnjo2Jy9",
)


class EnvironmentGuardTest(unittest.TestCase):
    """Pins the fix: a typo must never silently route production to sandbox."""

    def test_explicit_typo_raises(self):
        with self.assertRaises(HesabeConfigurationError):
            resolve_config(environment="prodution", **CREDENTIALS)

    def test_env_var_typo_raises(self):
        with mock.patch.dict(os.environ, {"HESABE_ENVIRONMENT": "Production"}):
            with self.assertRaises(HesabeConfigurationError):
                resolve_config(**CREDENTIALS)

    def test_unset_defaults_to_sandbox(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = resolve_config(**CREDENTIALS)
        self.assertEqual(config.environment, "sandbox")
        self.assertEqual(config.gateway_url, "https://sandbox.hesabe.com")

    def test_production_selects_live_urls(self):
        config = resolve_config(environment="production", **CREDENTIALS)
        self.assertEqual(config.gateway_url, "https://api.hesabe.com")
        self.assertEqual(config.merchant_api_url, "https://merchantapi.hesabe.com")


class DotenvOptInTest(unittest.TestCase):
    def test_env_file_is_not_read_unless_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / f"{uuid.uuid4().hex}.env"
            env_file.write_text("HESABE_MERCHANT_CODE=999999\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(HesabeConfigurationError):
                    resolve_config(**{**CREDENTIALS, "merchant_code": None})

    def test_env_file_is_read_when_env_path_is_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / f"{uuid.uuid4().hex}.env"
            env_file.write_text(
                'HESABE_MERCHANT_CODE="999999"\nexport HESABE_TIMEOUT=12.5\n',
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                config = resolve_config(
                    env_path=str(env_file), **{**CREDENTIALS, "merchant_code": None}
                )
        self.assertEqual(config.merchant_code, "999999")
        self.assertEqual(config.timeout, 12.5)

    def test_real_environment_wins_over_the_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / f"{uuid.uuid4().hex}.env"
            env_file.write_text("HESABE_MERCHANT_CODE=999999\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"HESABE_MERCHANT_CODE": "111111"}, clear=True):
                config = resolve_config(
                    env_path=str(env_file), **{**CREDENTIALS, "merchant_code": None}
                )
        self.assertEqual(config.merchant_code, "111111")


class ResolutionTest(unittest.TestCase):
    def test_missing_credentials_name_the_variable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HesabeConfigurationError) as ctx:
                resolve_config(**{**CREDENTIALS, "access_code": None})
        self.assertIn("HESABE_ACCESS_CODE", str(ctx.exception))

    def test_base_urls_are_trailing_slash_trimmed(self):
        config = resolve_config(gateway_url="https://gw.test///", **CREDENTIALS)
        self.assertEqual(config.gateway_url, "https://gw.test")

    def test_unparseable_numeric_env_values_fall_back(self):
        with mock.patch.dict(
            os.environ, {"HESABE_TIMEOUT": "abc", "HESABE_MAX_RETRIES": ""}, clear=True
        ):
            config = resolve_config(**CREDENTIALS)
        self.assertEqual(config.timeout, 30.0)
        self.assertEqual(config.max_retries, 2)

    def test_hostile_numeric_env_values_never_escape_as_untyped_errors(self):
        """int(float("inf")) raises OverflowError, which is not a HesabeError."""
        for value in ("inf", "nan", "1e400", "-3", "2.9"):
            with self.subTest(value):
                with mock.patch.dict(
                    os.environ,
                    {"HESABE_TIMEOUT": value, "HESABE_MAX_RETRIES": value},
                    clear=True,
                ):
                    config = resolve_config(**CREDENTIALS)
                self.assertGreaterEqual(config.max_retries, 0)
                self.assertGreater(config.timeout, 0)

    def test_negative_max_retries_would_skip_the_request_loop_entirely(self):
        self.assertEqual(resolve_config(**CREDENTIALS, max_retries=-1).max_retries, 2)


class SecretExposureTest(unittest.TestCase):
    def test_repr_hides_every_secret(self):
        """Transport.config hangs off every resource, so its repr reaches logs."""
        config = resolve_config(**CREDENTIALS, username="u", password="hunter2")
        text = repr(config)
        for secret in (config.access_code, config.secret_key, config.iv_key, "hunter2"):
            self.assertNotIn(secret, text)
        self.assertIn(config.merchant_code, text)


if __name__ == "__main__":
    unittest.main()

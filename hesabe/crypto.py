"""AES-256-CBC with Hesabe's 32-byte block padding, backed by `cryptography`."""

from __future__ import annotations

import json
import re
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .errors import HesabeConfigurationError, HesabeSignatureError

# Retained from 1.0, when the AES implementation was selected at import time.
BACKEND = "cryptography"

_HEX = re.compile(r"^[0-9a-fA-F]+$")

# Hesabe pads to a 32-byte block, not AES's 16, and disables cipher-level
# padding. Both operations work on bytes; padding by character count corrupts
# any non-ASCII payload.
_BLOCK = 32


def is_hex(value: str) -> bool:
    return len(value) > 0 and len(value) % 2 == 0 and bool(_HEX.match(value))


def _pad(plaintext: bytes) -> bytes:
    length = _BLOCK - (len(plaintext) % _BLOCK)
    return plaintext + bytes([length]) * length


def _unpad(padded: bytes) -> bytes:
    if not padded:
        raise HesabeSignatureError("Decrypted payload is empty")
    length = padded[-1]
    if length == 0 or length > _BLOCK or length > len(padded):
        raise HesabeSignatureError("Decrypted payload has invalid padding")
    return padded[:-length]


def _key_bytes(value: str, size: int, name: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) != size:
        raise HesabeConfigurationError(
            f"{name} must be exactly {size} bytes, received {len(encoded)}"
        )
    return encoded


class HesabeCipher:
    def __init__(self, secret_key: str, iv_key: str) -> None:
        self._key = _key_bytes(secret_key, 32, "secret_key")
        self._iv = _key_bytes(iv_key, 16, "iv_key")

    def _cipher(self) -> Cipher:
        return Cipher(algorithms.AES(self._key), modes.CBC(self._iv))

    def encrypt(self, payload: Any) -> str:
        plaintext = _pad(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        encryptor = self._cipher().encryptor()
        return (encryptor.update(plaintext) + encryptor.finalize()).hex()

    def decrypt(self, ciphertext: str) -> Any:
        normalized = ciphertext.strip()
        if not is_hex(normalized):
            raise HesabeSignatureError("Expected a hex-encoded payload")
        decryptor = self._cipher().decryptor()
        decrypted = decryptor.update(bytes.fromhex(normalized)) + decryptor.finalize()
        unpadded = _unpad(decrypted)
        try:
            return json.loads(unpadded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HesabeSignatureError("Decrypted payload is not valid JSON") from None

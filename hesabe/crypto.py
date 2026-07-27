from __future__ import annotations

import json
import re
import warnings
from typing import Any, Callable, Tuple

from .errors import HesabeConfigurationError, HesabeSignatureError

_HEX = re.compile(r"^[0-9a-fA-F]+$")

# Hesabe pads to a 32-byte block, not AES's 16, and disables cipher-level
# padding. Both operations work on bytes; padding by character count corrupts
# any non-ASCII payload.
_BLOCK = 32

CbcFunc = Callable[[bytes, bytes, bytes], bytes]


def _load_backend() -> Tuple[CbcFunc, CbcFunc, str]:
    """Prefers an audited AES if one is installed, else the bundled fallback."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        def encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
            encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            return encryptor.update(data) + encryptor.finalize()

        def decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            return decryptor.update(data) + decryptor.finalize()

        return encrypt, decrypt, "cryptography"
    except ImportError:
        pass

    try:
        from Crypto.Cipher import AES

        def encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
            return AES.new(key, AES.MODE_CBC, iv).encrypt(data)

        def decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
            return AES.new(key, AES.MODE_CBC, iv).decrypt(data)

        return encrypt, decrypt, "pycryptodome"
    except ImportError:
        pass

    from ._aes import decrypt_cbc, encrypt_cbc

    warnings.warn(
        "hesabe is using its bundled pure-Python AES, which is not "
        "constant-time and is far slower than a native backend. Install one "
        "with `pip install cryptography`.",
        UserWarning,
    )
    return encrypt_cbc, decrypt_cbc, "builtin"


_encrypt_cbc, _decrypt_cbc, BACKEND = _load_backend()


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

    def encrypt(self, payload: Any) -> str:
        plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return _encrypt_cbc(self._key, self._iv, _pad(plaintext)).hex()

    def decrypt(self, ciphertext: str) -> Any:
        normalized = ciphertext.strip()
        if not is_hex(normalized):
            raise HesabeSignatureError("Expected a hex-encoded payload")
        decrypted = _decrypt_cbc(self._key, self._iv, bytes.fromhex(normalized))
        unpadded = _unpad(decrypted)
        try:
            return json.loads(unpadded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HesabeSignatureError("Decrypted payload is not valid JSON") from None

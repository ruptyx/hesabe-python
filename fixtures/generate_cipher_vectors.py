"""Regenerates cipher-vectors.json from the NIST-pinned Python cipher.

    python fixtures/generate_cipher_vectors.py

This file is the canonical source of the cross-SDK parity vectors. After
regenerating, copy both JSON files into hesabe-node's fixtures/ directory so
the two SDKs keep asserting byte-identical ciphertext.

Payloads must stay ASCII-only with string-typed decimals so that
json.dumps(separators=(",", ":")) and JSON.stringify produce byte-identical
plaintext in both SDKs; only then is cross-SDK ciphertext equality guaranteed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hesabe.crypto import HesabeCipher  # noqa: E402

SANDBOX_KEY = "PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg"
SANDBOX_IV = "5NVdrlPVNnjo2Jy9"
ALT_KEY = "A" * 32
ALT_IV = "B" * 16

# A payload whose compact JSON lands exactly on a 32-byte block boundary.
boundary = {"m": ""}
while len(json.dumps(boundary, separators=(",", ":")).encode()) % 32 != 0:
    boundary["m"] += "x"

CASES = [
    ("checkout-payload", SANDBOX_KEY, SANDBOX_IV,
     {"merchantCode": "842217", "amount": "1.500", "currency": "KWD"}),
    ("json-escapes", SANDBOX_KEY, SANDBOX_IV,
     {"note": 'line\nbreak "quoted" back\\slash', "tab": "a\tb"}),
    ("block-boundary", SANDBOX_KEY, SANDBOX_IV, boundary),
    ("nested-alt-key", ALT_KEY, ALT_IV,
     {"a": {"b": ["1", "2"]}, "n": 7, "flag": True, "none": None}),
]

vectors = []
for name, key, iv, payload in CASES:
    cipher = HesabeCipher(key, iv)
    ciphertext = cipher.encrypt(payload)
    assert cipher.decrypt(ciphertext) == payload
    vectors.append(
        {"name": name, "key": key, "iv": iv, "payload": payload, "ciphertextHex": ciphertext}
    )

out = ROOT / "fixtures" / "cipher-vectors.json"
out.write_text(json.dumps(vectors, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(vectors)} vectors)")

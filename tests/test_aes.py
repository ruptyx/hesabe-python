"""Correctness vectors for the bundled AES fallback.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hesabe._aes import INV_SBOX, SBOX, decrypt_cbc, encrypt_cbc  # noqa: E402
from hesabe.crypto import HesabeCipher  # noqa: E402

NIST_KEY = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
NIST_IV = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
NIST_PLAINTEXT = bytes.fromhex(
    "6bc1bee22e409f96e93d7e117393172a"
    "ae2d8a571e03ac9c9eb76fac45af8e51"
    "30c81c46a35ce411e5fbc1191a0a52ef"
    "f69f2445df4f9b17ad2b417be66c3710"
)
NIST_CIPHERTEXT = bytes.fromhex(
    "f58c4c04d6e5f1ba779eabfb5f7bfbd6"
    "9cfc4e967edb808d679f777bc6702c7d"
    "39f23369a9d9bacfa530e26304231461"
    "b2eb05e2c39be9fcda6c19078c6a9d1b"
)

FIPS_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
FIPS_PLAINTEXT = bytes.fromhex("00112233445566778899aabbccddeeff")
FIPS_CIPHERTEXT = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")


class SBoxTest(unittest.TestCase):
    def test_known_entries(self):
        self.assertEqual(SBOX[0x00], 0x63)
        self.assertEqual(SBOX[0x01], 0x7C)
        self.assertEqual(SBOX[0x53], 0xED)

    def test_is_a_bijection(self):
        self.assertEqual(sorted(SBOX), list(range(256)))
        for value in range(256):
            self.assertEqual(INV_SBOX[SBOX[value]], value)


class AesCbcTest(unittest.TestCase):
    def test_nist_sp800_38a_f25_encrypt(self):
        self.assertEqual(encrypt_cbc(NIST_KEY, NIST_IV, NIST_PLAINTEXT), NIST_CIPHERTEXT)

    def test_nist_sp800_38a_f26_decrypt(self):
        self.assertEqual(decrypt_cbc(NIST_KEY, NIST_IV, NIST_CIPHERTEXT), NIST_PLAINTEXT)

    def test_fips_197_c3_single_block(self):
        self.assertEqual(encrypt_cbc(FIPS_KEY, bytes(16), FIPS_PLAINTEXT), FIPS_CIPHERTEXT)
        self.assertEqual(decrypt_cbc(FIPS_KEY, bytes(16), FIPS_CIPHERTEXT), FIPS_PLAINTEXT)


class CipherTest(unittest.TestCase):
    def setUp(self):
        self.cipher = HesabeCipher("PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg", "5NVdrlPVNnjo2Jy9")

    def test_round_trip(self):
        payload = {"merchantCode": "842217", "amount": "1.500"}
        self.assertEqual(self.cipher.decrypt(self.cipher.encrypt(payload)), payload)

    def test_round_trip_with_non_ascii(self):
        """Padding by byte length, not character count, keeps Arabic intact."""
        payload = {"name": "أحمد المنصوري", "amount": "9.900"}
        self.assertEqual(self.cipher.decrypt(self.cipher.encrypt(payload)), payload)

    def test_round_trip_at_block_boundary(self):
        """A payload that lands on an exact 32-byte multiple pads with spaces."""
        for filler in range(64):
            payload = {"m": "x" * filler}
            self.assertEqual(self.cipher.decrypt(self.cipher.encrypt(payload)), payload)

    def test_rejects_wrong_key_length(self):
        from hesabe.errors import HesabeConfigurationError

        with self.assertRaises(HesabeConfigurationError):
            HesabeCipher("too-short", "5NVdrlPVNnjo2Jy9")


if __name__ == "__main__":
    unittest.main()

"""Cipher behaviour, including the cross-SDK interop vectors."""

from __future__ import annotations

import unittest

from _support import CIPHER, IV_KEY, SECRET_KEY, load_fixture
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from hesabe.crypto import HesabeCipher, is_hex
from hesabe.errors import HesabeConfigurationError, HesabeSignatureError


class InteropVectorTest(unittest.TestCase):
    """Both SDKs must produce byte-identical ciphertext for these payloads."""

    def test_vectors(self):
        for vector in load_fixture("cipher-vectors.json"):
            with self.subTest(vector["name"]):
                cipher = HesabeCipher(vector["key"], vector["iv"])
                self.assertEqual(cipher.encrypt(vector["payload"]), vector["ciphertextHex"])
                self.assertEqual(cipher.decrypt(vector["ciphertextHex"]), vector["payload"])


class DecryptRejectionTest(unittest.TestCase):
    def _raw(self, block: bytes) -> str:
        """Encrypts a raw block without Hesabe padding, to craft bad ciphertexts."""
        encryptor = Cipher(
            algorithms.AES(SECRET_KEY.encode()), modes.CBC(IV_KEY.encode())
        ).encryptor()
        return (encryptor.update(block) + encryptor.finalize()).hex()

    def test_rejects_zero_padding_byte(self):
        with self.assertRaises(HesabeSignatureError):
            CIPHER.decrypt(self._raw(b"A" * 31 + b"\x00"))

    def test_rejects_padding_longer_than_block(self):
        with self.assertRaises(HesabeSignatureError):
            CIPHER.decrypt(self._raw(b"A" * 31 + bytes([33])))

    def test_rejects_garbage_that_unpads_to_non_json(self):
        # Valid 1-byte padding but the remaining 31 bytes are not JSON.
        with self.assertRaises(HesabeSignatureError):
            CIPHER.decrypt(self._raw(b"\xff" * 31 + b"\x01"))

    def test_rejects_hex_that_is_not_a_whole_number_of_blocks(self):
        """Reachable from a redirect URL: ?data=abcd must not raise OpenSSL's own
        ValueError past the typed hierarchy."""
        for bad in ("abcd", "00", "deadbeef"):
            with self.subTest(bad):
                with self.assertRaises(HesabeSignatureError):
                    CIPHER.decrypt(bad)

    def test_rejects_padding_bytes_that_disagree(self):
        """Only the final byte carries the length; the rest must match it."""
        block = b'{"a":1}' + bytes([0x09]) * 8 + b"\xaa" * 16 + bytes([0x09])
        with self.assertRaises(HesabeSignatureError):
            CIPHER.decrypt(self._raw(block[:32]))

    def test_rejects_non_hex_input(self):
        for bad in ("", "zz", "abc"):  # empty, non-hex, odd length
            with self.subTest(bad):
                with self.assertRaises(HesabeSignatureError):
                    CIPHER.decrypt(bad)

    def test_rejects_wrong_key_lengths(self):
        with self.assertRaises(HesabeConfigurationError):
            HesabeCipher("short", IV_KEY)
        with self.assertRaises(HesabeConfigurationError):
            HesabeCipher(SECRET_KEY, "short")


class IsHexTest(unittest.TestCase):
    def test_accepts_even_length_hex(self):
        self.assertTrue(is_hex("00ff"))
        self.assertTrue(is_hex("ABCDEF12"))

    def test_rejects_odd_empty_and_non_hex(self):
        for bad in ("", "0", "0g", "xyz!"):
            self.assertFalse(is_hex(bad), bad)


class RoundTripTest(unittest.TestCase):
    def test_non_ascii_round_trip(self):
        payload = {"name": "أحمد المنصوري", "amount": "9.900"}
        self.assertEqual(CIPHER.decrypt(CIPHER.encrypt(payload)), payload)

    def test_round_trip_at_every_padding_boundary(self):
        for filler in range(65):
            payload = {"m": "x" * filler}
            self.assertEqual(CIPHER.decrypt(CIPHER.encrypt(payload)), payload)


if __name__ == "__main__":
    unittest.main()

"""Minimal AES-256-CBC, used only when no vetted crypto backend is installed.

The stdlib ships no AES, and this SDK declares no required dependencies, so this
module is the fallback that keeps `pip install hesabe` free of build steps. When
`cryptography` or `pycryptodome` is present, `hesabe.crypto` prefers it and this
code never runs. Correctness is pinned by the NIST SP 800-38A vectors in
`tests/test_aes.py`.
"""

from __future__ import annotations

_BLOCK = 16
_ROUNDS = 14
_KEY_WORDS = 8


def _build_tables() -> tuple[list[int], list[int]]:
    exp: list[int] = [0] * 256
    log: list[int] = [0] * 256
    value = 1
    for i in range(255):
        exp[i] = value
        log[value] = i
        value ^= _xtime(value)

    def rotl(byte: int, count: int) -> int:
        return ((byte << count) | (byte >> (8 - count))) & 0xFF

    sbox = [0] * 256
    inv_sbox = [0] * 256
    for i in range(256):
        inverse = 0 if i == 0 else exp[(255 - log[i]) % 255]
        result = inverse
        for shift in (1, 2, 3, 4):
            result ^= rotl(inverse, shift)
        result ^= 0x63
        sbox[i] = result
        inv_sbox[result] = i
    return sbox, inv_sbox


def _xtime(byte: int) -> int:
    shifted = byte << 1
    return (shifted ^ 0x1B) & 0xFF if byte & 0x80 else shifted & 0xFF


def _mul(a: int, b: int) -> int:
    product = 0
    while b:
        if b & 1:
            product ^= a
        a = _xtime(a)
        b >>= 1
    return product


SBOX, INV_SBOX = _build_tables()
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D]


def _expand_key(key: bytes) -> list[list[int]]:
    words = [list(key[i : i + 4]) for i in range(0, len(key), 4)]
    total = _BLOCK // 4 * (_ROUNDS + 1)

    for i in range(_KEY_WORDS, total):
        temp = list(words[i - 1])
        if i % _KEY_WORDS == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[b] for b in temp]
            temp[0] ^= RCON[i // _KEY_WORDS - 1]
        elif i % _KEY_WORDS == 4:
            temp = [SBOX[b] for b in temp]
        words.append([words[i - _KEY_WORDS][j] ^ temp[j] for j in range(4)])

    return [_to_state(words[r * 4 : r * 4 + 4]) for r in range(_ROUNDS + 1)]


def _to_state(words: list[list[int]]) -> list[int]:
    return [byte for word in words for byte in word]


def _add_round_key(state: list[int], round_key: list[int]) -> None:
    for i in range(_BLOCK):
        state[i] ^= round_key[i]


def _shift_rows(state: list[int]) -> None:
    for row in range(1, 4):
        column = [state[row + 4 * c] for c in range(4)]
        column = column[row:] + column[:row]
        for c in range(4):
            state[row + 4 * c] = column[c]


def _inv_shift_rows(state: list[int]) -> None:
    for row in range(1, 4):
        column = [state[row + 4 * c] for c in range(4)]
        column = column[-row:] + column[:-row]
        for c in range(4):
            state[row + 4 * c] = column[c]


def _mix_columns(state: list[int], matrix: tuple[int, int, int, int]) -> None:
    a0, a1, a2, a3 = matrix
    for c in range(4):
        base = 4 * c
        s0, s1, s2, s3 = state[base : base + 4]
        state[base + 0] = _mul(s0, a0) ^ _mul(s1, a1) ^ _mul(s2, a2) ^ _mul(s3, a3)
        state[base + 1] = _mul(s0, a3) ^ _mul(s1, a0) ^ _mul(s2, a1) ^ _mul(s3, a2)
        state[base + 2] = _mul(s0, a2) ^ _mul(s1, a3) ^ _mul(s2, a0) ^ _mul(s3, a1)
        state[base + 3] = _mul(s0, a1) ^ _mul(s1, a2) ^ _mul(s2, a3) ^ _mul(s3, a0)


def _encrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    _add_round_key(state, round_keys[0])
    for round_index in range(1, _ROUNDS):
        state = [SBOX[b] for b in state]
        _shift_rows(state)
        _mix_columns(state, (2, 3, 1, 1))
        _add_round_key(state, round_keys[round_index])
    state = [SBOX[b] for b in state]
    _shift_rows(state)
    _add_round_key(state, round_keys[_ROUNDS])
    return bytes(state)


def _decrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    _add_round_key(state, round_keys[_ROUNDS])
    for round_index in range(_ROUNDS - 1, 0, -1):
        _inv_shift_rows(state)
        state = [INV_SBOX[b] for b in state]
        _add_round_key(state, round_keys[round_index])
        _mix_columns(state, (14, 11, 13, 9))
    _inv_shift_rows(state)
    state = [INV_SBOX[b] for b in state]
    _add_round_key(state, round_keys[0])
    return bytes(state)


def encrypt_cbc(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    round_keys = _expand_key(key)
    previous = iv
    out = bytearray()
    for offset in range(0, len(plaintext), _BLOCK):
        block = plaintext[offset : offset + _BLOCK]
        mixed = bytes(a ^ b for a, b in zip(block, previous))
        previous = _encrypt_block(mixed, round_keys)
        out += previous
    return bytes(out)


def decrypt_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    round_keys = _expand_key(key)
    previous = iv
    out = bytearray()
    for offset in range(0, len(ciphertext), _BLOCK):
        block = ciphertext[offset : offset + _BLOCK]
        decrypted = _decrypt_block(block, round_keys)
        out += bytes(a ^ b for a, b in zip(decrypted, previous))
        previous = block
    return bytes(out)

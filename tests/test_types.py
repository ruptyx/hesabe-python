"""Amount formatting, shared vectors with the TypeScript SDK."""

from __future__ import annotations

import unittest
from decimal import Decimal

from _support import load_fixture

from hesabe.types import _normalize_amount, format_amount


class AmountVectorTest(unittest.TestCase):
    """Both SDKs must produce identical output for these inputs."""

    def test_vectors(self):
        for vector in load_fixture("amount-vectors.json"):
            with self.subTest(repr(vector["input"])):
                if vector.get("throws"):
                    with self.assertRaises(ValueError):
                        format_amount(vector["input"])
                else:
                    self.assertEqual(format_amount(vector["input"]), vector["expected"])


class PythonOnlyInputTest(unittest.TestCase):
    def test_decimal_input(self):
        self.assertEqual(format_amount(Decimal("1.0005")), "1.001")

    def test_rejects_nan_and_infinity(self):
        for bad in (float("nan"), float("inf"), Decimal("NaN")):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    format_amount(bad)

    def test_float_drift(self):
        self.assertEqual(format_amount(0.1 + 0.2), "0.300")


class NormalizeAmountTest(unittest.TestCase):
    def test_string_and_number_agree(self):
        self.assertEqual(_normalize_amount("1.000"), _normalize_amount(1))

    def test_unparseable_values_fall_back_to_raw(self):
        self.assertEqual(_normalize_amount("abc"), "abc")
        self.assertIsNone(_normalize_amount(None))


if __name__ == "__main__":
    unittest.main()

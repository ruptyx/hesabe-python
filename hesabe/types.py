from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Union

Money = Union[str, int, float, Decimal]


class PaymentType:
    HOSTED_CHECKOUT = 0
    KNET = 1
    MPGS = 2
    CYBERSOURCE = 5
    AMEX = 7
    MPGS_AMEX = 8
    MPGS_APPLE_PAY = 9
    CYBERSOURCE_APPLE_PAY = 10
    KNET_DEBIT_APPLE_PAY = 11
    KNET_CREDIT_APPLE_PAY = 12
    KNET_APPLE_PAY_INTERNATIONAL = 13
    AMEX_APPLE_PAY_INTERNATIONAL = 14
    CYBERSOURCE_SUBSCRIPTION = 15
    GOOGLE_PAY = 16
    DEEMA = 18
    MPGS_SUBSCRIPTION = 19
    SAMSUNG_PAY = 20


class ServiceType:
    SMS_PAYMENT = 2
    PAYMENT_GATEWAY = 3
    POS_TERMINAL = 6
    OPEN_INVOICE = 7
    RENTAL = 11
    STOCK_LISTING = 13
    DYNAMIC_COMMISSION = 14


class PaymentStatus:
    FAILED = 0
    SUCCESS = 1
    REFUND = 2
    REFUND_FAILED = 3
    AUTHORIZED = 4
    MULTIVENDOR_SUCCESS = 6
    SUBSCRIPTION = 8
    CASH_PAYMENT = 9
    SUB_MERCHANT_SUBSCRIPTION = 10
    MAIN_MERCHANT_SUBSCRIPTION = 11


class InvoiceType:
    SUBSCRIPTION = "0"
    SINGLE = "1"
    SPLIT = "6"
    INSTALLMENT = "7"


class RefundMethod:
    FULL = "1"
    PARTIAL = "2"


class HesabeObject(dict):
    """A dict that also allows attribute access, so responses read naturally."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        # Private names stay instance attributes; everything else is response
        # data, which must not pick up bookkeeping fields when it is re-sent.
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self[name] = value

    def __dir__(self):
        return list(super().__dir__()) + [key for key in self if isinstance(key, str)]

    @classmethod
    def wrap(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return cls({key: cls.wrap(item) for key, item in value.items()})
        if isinstance(value, list):
            return [cls.wrap(item) for item in value]
        return value


# The grammar the TypeScript twin accepts, so the two SDKs agree on exactly
# which strings are amounts. Decimal on its own is more permissive: it takes
# Arabic-Indic digits, PEP 515 underscores, "nan" and "inf".
_DECIMAL = re.compile(r"^[+-]?(?=[0-9]|\.[0-9])[0-9]*(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?\Z")

# JavaScript's trim() strips the byte-order mark; Python's strip() does not.
_TRIM = re.compile("^[\\s\ufeff]+|[\\s\ufeff]+\\Z")

# Decimal's default 28-digit context cannot quantize beyond this, and the
# TypeScript twin would allocate an unbounded BigInt. No KWD amount comes close.
_MAX_ADJUSTED_EXPONENT = 24


def format_amount(amount: Money) -> str:
    """
    Hesabe rejects amounts that are not fixed to three decimal places, and
    floating point arithmetic upstream is the usual cause of a 506 rejection.
    """
    text = _TRIM.sub("", str(amount))
    if not _DECIMAL.match(text):
        raise ValueError(f"Invalid amount: {amount!r}")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {amount!r}") from None
    if value < 0:
        raise ValueError(f"Amounts must not be negative: {amount!r}")
    if value.adjusted() > _MAX_ADJUSTED_EXPONENT:
        raise ValueError(f"Invalid amount: {amount!r}")
    quantized = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return str(abs(quantized))  # abs() folds "-0" into "0.000"


def _normalize_amount(value: Any) -> Any:
    """Hesabe reports amounts as strings in some payloads and numbers in others."""
    try:
        return format_amount(value)
    except (ValueError, TypeError):
        return value

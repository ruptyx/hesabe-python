from __future__ import annotations

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


class HesabeObject(dict):
    """A dict that also allows attribute access, so responses read naturally."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
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


def format_amount(amount: Money) -> str:
    """
    Hesabe rejects amounts that are not fixed to three decimal places, and
    floating point arithmetic upstream is the usual cause of a 506 rejection.
    """
    try:
        value = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid amount: {amount!r}") from None
    if not value.is_finite():
        raise ValueError(f"Invalid amount: {amount!r}")
    if value < 0:
        raise ValueError(f"Amounts must not be negative: {amount!r}")
    quantized = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return str(abs(quantized))  # abs() folds "-0" into "0.000"


def _normalize_amount(value: Any) -> Any:
    """Hesabe reports amounts as strings in some payloads and numbers in others."""
    try:
        return format_amount(value)
    except (ValueError, TypeError):
        return value

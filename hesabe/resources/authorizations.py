from __future__ import annotations

from urllib.parse import quote

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class Authorizations(Resource):
    """
    Two-step card payments: authorize at checkout with ``authorize=True``, then
    capture once you ship. MPGS only.
    """

    def capture(self, *, payment_token: str, amount: Money) -> HesabeObject:
        return self._gateway(
            "POST",
            "api/capture",
            payload=self._with_merchant_code(
                {"paymentToken": payment_token, "amount": format_amount(amount)}
            ),
            idempotent=False,
        )

    def cancel(self, payment_token: str) -> None:
        """Releases the hold so the funds cannot be captured later."""
        self._gateway(
            "DELETE",
            f"api/cancel/{quote(payment_token, safe='')}",
            idempotent=False,
        )

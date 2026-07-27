from __future__ import annotations

from urllib.parse import quote

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class Subscriptions(Resource):
    def capture(
        self, *, payment_token: str, amount: Money, order_reference_number: str
    ) -> HesabeObject:
        """
        Bills an active subscription. Required for on-demand profiles
        (``recurring_frequency=0``); monthly profiles bill themselves.
        """
        return self._gateway(
            "POST",
            "api/subscription/capture",
            payload=self._with_merchant_code(
                {
                    "paymentToken": payment_token,
                    "amount": format_amount(amount),
                    "orderReferenceNumber": order_reference_number,
                }
            ),
            idempotent=False,
        )

    def cancel(self, subscription_token: str) -> None:
        """Deactivates the subscription so no further charges are taken."""
        self._gateway(
            "DELETE",
            f"api/subscription/cancel/{quote(subscription_token, safe='')}",
            idempotent=False,
        )

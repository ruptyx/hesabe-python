from __future__ import annotations

from typing import List, Optional

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class Cards(Resource):
    def list(self, customer_id: int) -> List[HesabeObject]:
        """Lists the cards a customer has saved and that remain chargeable."""
        result = self._gateway(
            "GET",
            "api/direct-payment/cards",
            payload=self._with_merchant_code({"customer_id": customer_id}),
        )
        return (result or {}).get("cards") or []

    def charge(
        self,
        *,
        card_id: int,
        amount: Money,
        customer_id: Optional[int] = None,
        order_reference: Optional[str] = None,
    ) -> HesabeObject:
        """
        Charges a stored card with no customer interaction. Server-side only —
        this call carries your access code and must never run in a browser.
        """
        return self._gateway(
            "POST",
            "api/direct-payment/charge-card",
            payload=self._with_merchant_code(
                {
                    "card_id": card_id,
                    "amount": format_amount(amount),
                    "customer_id": customer_id,
                    "order_reference": order_reference,
                }
            ),
            idempotent=False,
        )

    def remove(self, card_id: int) -> None:
        """Deletes the card locally and its token at MPGS. This cannot be undone."""
        self._gateway(
            "DELETE",
            f"api/direct-payment/cards/{card_id}",
            payload=self._with_merchant_code(),
            idempotent=False,
        )

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote

from ..resource import Resource
from ..types import HesabeObject, Money, PaymentType, format_amount


class Checkout(Resource):
    def create(
        self,
        *,
        amount: Money,
        order_reference_number: str,
        response_url: str,
        failure_url: str,
        payment_type: int = PaymentType.HOSTED_CHECKOUT,
        currency: str = "KWD",
        name: Optional[str] = None,
        email: Optional[str] = None,
        mobile_number: Optional[str] = None,
        webhook_url: Optional[str] = None,
        commission: Optional[Money] = None,
        save_card: Optional[bool] = None,
        customer_id: Optional[int] = None,
        channel: Optional[str] = None,
        embedded: bool = False,
        authorize: bool = False,
        subscription: Optional[Dict[str, Any]] = None,
        variable1: Optional[str] = None,
        variable2: Optional[str] = None,
        variable3: Optional[str] = None,
        variable4: Optional[str] = None,
        variable5: Optional[str] = None,
        version: Optional[str] = None,
    ) -> HesabeObject:
        """
        Creates a payment session. The returned ``payment_url`` is where the
        customer completes the payment; nothing is charged until they do.

        Pass ``channel="mobile"`` to also receive a ``webview_url`` ready to open
        in a native WebView.
        """
        needs_v3 = any((save_card, channel, embedded, subscription, customer_id))

        payload: Dict[str, Any] = self._with_merchant_code(
            {
                "amount": format_amount(amount),
                "currency": currency,
                "paymentType": payment_type,
                "orderReferenceNumber": order_reference_number,
                "responseUrl": response_url,
                "failureUrl": failure_url,
                "version": version or ("3.0" if needs_v3 else "2.0"),
                "name": name,
                "email": email,
                "mobile_number": mobile_number,
                "webhookUrl": webhook_url,
                "variable1": variable1,
                "variable2": variable2,
                "variable3": variable3,
                "variable4": variable4,
                "variable5": variable5,
                "channel": channel,
            }
        )

        if commission is not None:
            payload["commission"] = format_amount(commission)
        if save_card is not None:
            payload["saveCard"] = save_card
        if customer_id is not None:
            payload["customer_id"] = customer_id
        if embedded:
            payload["embeddedPayment"] = True
        if authorize:
            payload["authorize"] = "1"
        if subscription:
            payload["subscription"] = "1"
            for key, target in (
                ("recurring_frequency", "recurringFrequency"),
                ("number_of_installments", "numberOfInstallments"),
                ("recurring_start_date", "recurringStartDate"),
            ):
                if subscription.get(key) is not None:
                    payload[target] = str(subscription[key])
            if subscription.get("recurring_amount") is not None:
                payload["recurringAmount"] = format_amount(subscription["recurring_amount"])

        envelope = self._gateway_envelope("POST", "checkout", payload=payload, idempotent=False)
        data = (envelope.get("response") or {}).get("data") or ""

        session = HesabeObject(
            {
                "token": envelope.get("token") or "",
                "data": data,
                "payment_url": f"{self._transport.config.gateway_url}/payment?data={quote(data)}",
            }
        )
        if envelope.get("webviewUrl"):
            session["webview_url"] = envelope["webviewUrl"]
        return session

    def verify_card(self, *, customer_id: int, **kwargs: Any) -> HesabeObject:
        """
        Starts a zero-amount 3DS authentication that stores the customer's card.
        The resulting ``cardId`` arrives on your ``response_url`` and can be
        charged later through ``cards.charge``.
        """
        kwargs.pop("amount", None)
        kwargs.pop("payment_type", None)
        kwargs.pop("save_card", None)
        return self.create(
            amount=0,
            payment_type=PaymentType.MPGS,
            save_card=True,
            customer_id=customer_id,
            **kwargs,
        )

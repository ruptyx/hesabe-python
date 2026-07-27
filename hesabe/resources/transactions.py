from __future__ import annotations

from urllib.parse import quote

from ..errors import HesabeInvalidRequestError, HesabeSignatureError
from ..resource import Resource
from ..types import HesabeObject, _normalize_amount


def _path_segment(value: str, name: str) -> str:
    """
    Dots are left alone by quote(), and the TypeScript twin's URL builder
    collapses them, so a lookup key of ".." would address a different endpoint
    in one SDK and not the other. Neither is a real key; reject both.
    """
    if not isinstance(value, str) or not value or set(value) <= {"."}:
        raise HesabeInvalidRequestError(f"{name} must be a non-empty identifier")
    return quote(value, safe="")


class Transactions(Resource):
    def retrieve(self, payment_token: str) -> HesabeObject:
        """Looks a transaction up by the payment token Hesabe issued."""
        return self._gateway(
            "GET", f"api/transaction/{_path_segment(payment_token, 'payment_token')}"
        )

    def retrieve_by_order_reference(self, order_reference_number: str) -> HesabeObject:
        """Looks a transaction up by the reference you supplied at checkout."""
        return self._gateway(
            "GET",
            f"api/transaction/{_path_segment(order_reference_number, 'order_reference_number')}",
            query={"isOrderReference": 1},
        )

    def parse_redirect(self, data: str) -> HesabeObject:
        """
        Decrypts the ``data`` query parameter Hesabe appends when it redirects
        the customer back to your response or failure URL.

        The payload travels through the customer's browser, and decrypting it
        proves key possession, not integrity — AES-CBC carries no MAC. Use
        ``verify_redirect`` (or ``transactions.retrieve``) before fulfilling.
        """
        envelope = self._transport.cipher.decrypt(data)
        body = envelope.get("response") if isinstance(envelope, dict) else None
        if isinstance(body, dict) and isinstance(body.get("data"), dict):
            body = body["data"]
        return HesabeObject.wrap(body if body is not None else envelope)

    def verify_redirect(self, data: str) -> HesabeObject:
        """
        Decrypts a redirect payload, then re-reads the transaction from the API
        and returns that authoritative copy. Check ``status == "SUCCESSFUL"``
        on the result before releasing goods.
        """
        claimed = self.parse_redirect(data)
        token = claimed.get("paymentToken") if isinstance(claimed, dict) else None
        if not token:
            raise HesabeSignatureError("Redirect payload has no payment token")

        confirmed = self.retrieve(str(token))
        if _normalize_amount(confirmed.get("amount")) != _normalize_amount(claimed.get("amount")):
            raise HesabeSignatureError(
                f"Redirect does not match transaction {token}: claimed "
                f"{claimed.get('amount')}, Hesabe reports {confirmed.get('amount')}"
            )
        return confirmed

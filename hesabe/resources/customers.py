from __future__ import annotations

from ..errors import HesabeAPIError
from ..resource import Resource
from ..types import HesabeObject


class Customers(Resource):
    def create(self, *, name: str, email: str, mobile_number: str) -> HesabeObject:
        """
        Creates the customer a saved card will belong to. Keep the returned
        ``customer_id`` — card verification and charging both require it.
        """
        customer = self._gateway(
            "POST",
            "api/direct-payment/customer",
            payload=self._with_merchant_code(
                {"name": name, "email": email, "mobile_number": mobile_number}
            ),
            idempotent=False,
        )
        if not isinstance(customer, dict) or customer.get("customer_id") is None:
            raise HesabeAPIError("Hesabe did not return a customer", raw=customer)
        try:
            customer["customer_id"] = int(customer["customer_id"])
        except (TypeError, ValueError):
            raise HesabeAPIError(
                "Hesabe returned a non-numeric customer_id", raw=customer
            ) from None
        return customer

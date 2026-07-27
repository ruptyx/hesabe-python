from __future__ import annotations

from typing import Optional

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class OpenInvoices(Resource):
    def create(
        self,
        *,
        title: str,
        fix_amount: Optional[Money] = None,
        min_amount: Optional[Money] = None,
        max_amount: Optional[Money] = None,
        expiry_date: Optional[str] = None,
        description: Optional[str] = None,
    ) -> HesabeObject:
        """
        Creates a shareable payment link. Pass ``fix_amount`` for a set price, or
        ``min_amount`` and ``max_amount`` to let the customer choose.
        """
        if fix_amount is not None:
            amounts = {"amountType": "0", "fixAmount": format_amount(fix_amount)}
        elif min_amount is not None and max_amount is not None:
            amounts = {
                "amountType": "1",
                "minAmount": format_amount(min_amount),
                "maxAmount": format_amount(max_amount),
            }
        else:
            raise ValueError("Pass either fix_amount, or both min_amount and max_amount")

        return self._merchant(
            "POST",
            "api/v1/open-invoice",
            payload=self._with_merchant_code(
                {
                    "title": title,
                    "expiryDate": expiry_date,
                    "description": description,
                    **amounts,
                }
            ),
            idempotent=False,
        )

    def list(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        search: Optional[str] = None,
    ) -> HesabeObject:
        return self._merchant(
            "GET",
            "api/v1/open-invoice/",
            payload=self._with_merchant_code(),
            query={"page": page, "fromDate": from_date, "toDate": to_date, "search": search},
        )

    def update(self, object_id: int, *, expiry_date: str) -> HesabeObject:
        """Only the expiry date can be changed after creation."""
        return self._merchant(
            "PUT",
            f"api/v1/open-invoice/{object_id}",
            payload=self._with_merchant_code({"expiryDate": expiry_date}),
            idempotent=False,
        )

    def cancel(self, invoice_id: int) -> None:
        self._merchant(
            "DELETE",
            f"api/v1/open-invoice/{invoice_id}",
            payload=self._with_merchant_code(),
            idempotent=False,
        )

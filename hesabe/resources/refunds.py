from __future__ import annotations

from typing import Optional

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class Refunds(Resource):
    def create(self, *, token: str, amount: Money, method: str = "partial") -> HesabeObject:
        """
        Submits a refund request against a completed transaction. Refunds settle
        only after Hesabe approves them, so the initial status is pending.
        """
        return self._merchant(
            "POST",
            "api/v1/refund",
            payload=self._with_merchant_code(
                {
                    "token": token,
                    "refundAmount": format_amount(amount),
                    "refundMethod": "1" if method == "full" else "2",
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
        """Returns a page of refunds with ``data``, ``pagination``, and ``stats``."""
        result = self._merchant(
            "GET",
            "api/v1/refund/",
            payload=self._with_merchant_code(),
            query={"page": page, "fromDate": from_date, "toDate": to_date, "search": search},
        )
        page_body = HesabeObject(result.get("refund_request_list") or {})
        page_body["stats"] = result.get("stats")
        return page_body

    def retrieve(self, refund_id: int) -> HesabeObject:
        return self._merchant(
            "GET", f"api/v1/refund/{refund_id}", payload=self._with_merchant_code()
        )

    def cancel(self, refund_id: int) -> None:
        """Withdraws a refund request that has not been approved yet."""
        self._merchant(
            "DELETE",
            f"api/v1/refund/{refund_id}",
            payload=self._with_merchant_code(),
            idempotent=False,
        )

from __future__ import annotations

from typing import Optional

from ..resource import Resource
from ..types import HesabeObject


class Reports(Resource):
    def transactions(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        search: Optional[str] = None,
        service_type: Optional[int] = None,
        payment_type: Optional[int] = None,
        payment_status: Optional[int] = None,
        include_stats: bool = False,
    ) -> HesabeObject:
        """
        Returns a page of settled and failed transactions. Aggregate totals are
        skipped unless ``include_stats`` is set, which is noticeably faster.
        """
        result = self._merchant(
            "GET",
            "api/v1/report/transactions",
            payload=self._with_merchant_code(),
            query={
                "page": page,
                "nostats": 0 if include_stats else 1,
                "fromDate": from_date,
                "toDate": to_date,
                "search": search,
                "serviceType": service_type,
                "paymentType": payment_type,
                "paymentStatus": payment_status,
            },
        )
        return HesabeObject(result.get("transaction_list") or {})

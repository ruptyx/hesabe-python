from __future__ import annotations

import base64
from typing import Union

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


class BulkInvoices(Resource):
    def upload(
        self, *, file: Union[bytes, str], file_type: str = "csv", scheduled: bool = False
    ) -> None:
        """Uploads a CSV or XLSX of invoices. Bytes are base64-encoded for you."""
        invoices = base64.b64encode(file).decode("ascii") if isinstance(file, bytes) else file
        self._merchant(
            "POST",
            "api/v1/invoice-bulk-upload",
            payload=self._with_merchant_code(
                {
                    "isScheduled": "true" if scheduled else "false",
                    "fileType": file_type,
                    "invoices": invoices,
                }
            ),
            idempotent=False,
        )

    def list(self, *, scheduled: bool = False, page: int = 1) -> HesabeObject:
        return self._merchant(
            "GET",
            "api/v1/invoice-bulk-upload/",
            payload=self._with_merchant_code({"type": "1" if scheduled else "0"}),
            query={"page": page},
        )

    def update(
        self,
        invoice_id: int,
        *,
        amount: Money,
        name: str,
        email: str,
        phone: str,
        reference_number: str,
    ) -> HesabeObject:
        return self._merchant(
            "PUT",
            f"api/v1/invoice-bulk-upload/{invoice_id}",
            payload=self._with_merchant_code(
                {
                    "amount": format_amount(amount),
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "reference_number": reference_number,
                }
            ),
            idempotent=False,
        )

    def remove(self, invoice_id: int) -> None:
        self._merchant(
            "DELETE",
            f"api/v1/invoice-bulk-upload/{invoice_id}",
            payload=self._with_merchant_code(),
            idempotent=False,
        )

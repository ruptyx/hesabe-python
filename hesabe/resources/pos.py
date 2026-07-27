from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..resource import Resource
from ..types import HesabeObject, Money, ServiceType, format_amount
from .reports import Reports


class Pos(Resource):
    def _invoice_payload(
        self,
        customer_name: str,
        amount: Money,
        terminal_id: str,
        customer_email: Optional[str],
        customer_phone: Optional[str],
        invoice_number: Optional[str],
        description: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "customer_name": customer_name,
            "amount": format_amount(amount),
            "terminal_id": terminal_id,
            "customer_email": customer_email or "",
            "customer_phone": customer_phone or "",
            "invoice_number": invoice_number or "",
            "description": description or "",
        }

    def create(
        self,
        *,
        customer_name: str,
        amount: Money,
        terminal_id: str,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        invoice_number: Optional[str] = None,
        description: Optional[str] = None,
    ) -> HesabeObject:
        """Pushes a charge to a physical terminal for the customer to complete."""
        return self._merchant(
            "POST",
            "api/v1/merchant/smartpos-transaction",
            payload=self._with_merchant_code(
                self._invoice_payload(
                    customer_name, amount, terminal_id, customer_email,
                    customer_phone, invoice_number, description,
                )
            ),
            idempotent=False,
        )

    def resend(
        self,
        *,
        transaction_id: str,
        customer_name: str,
        amount: Money,
        terminal_id: str,
        customer_email: Optional[str] = None,
        customer_phone: Optional[str] = None,
        invoice_number: Optional[str] = None,
        description: Optional[str] = None,
    ) -> HesabeObject:
        """Re-sends an existing POS invoice to the terminal."""
        payload = self._invoice_payload(
            customer_name, amount, terminal_id, customer_email,
            customer_phone, invoice_number, description,
        )
        payload.update({"resend": 1, "transaction_id": transaction_id})
        return self._merchant(
            "POST",
            "api/v1/merchant/smartpos-transaction",
            payload=self._with_merchant_code(payload),
            idempotent=False,
        )

    def list(self, *, page: int = 1) -> HesabeObject:
        return self._merchant(
            "GET",
            "api/v1/merchant/smartpos-invoices",
            payload=self._with_merchant_code(),
            query={"page": page},
        )

    def retrieve(self, invoice_id: int) -> HesabeObject:
        return self._merchant(
            "GET",
            f"api/v1/merchant/smartpos-invoices/{invoice_id}",
            payload=self._with_merchant_code(),
        )

    def terminals(self) -> List[HesabeObject]:
        """Registered terminals with their per-scheme commission rates."""
        return self._merchant(
            "GET",
            "api/v1/merchant/smartpos-terminals",
            payload=self._with_merchant_code(),
        )

    def transactions(self, **kwargs: Any) -> HesabeObject:
        """Transaction report pre-filtered to terminal activity."""
        kwargs.pop("service_type", None)
        return Reports(self._transport, self._session).transactions(
            service_type=ServiceType.POS_TERMINAL, **kwargs
        )

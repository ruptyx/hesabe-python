from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from ..resource import Resource
from ..types import HesabeObject, Money, format_amount


def _to_payload(params: Dict[str, Any]) -> Dict[str, Any]:
    payload = {key: value for key, value in params.items() if value is not None}

    if "amount" in payload:
        payload["amount"] = format_amount(payload["amount"])
    if isinstance(payload.get("allocatePayType"), (list, tuple)):
        payload["allocatePayType"] = ",".join(str(v) for v in payload["allocatePayType"])
    if isinstance(payload.get("itemsList"), (list, tuple)):
        payload["itemsList"] = [
            {
                **item,
                "rate": format_amount(item["rate"]),
                "amount": format_amount(item["amount"]),
            }
            for item in payload["itemsList"]
        ]
    return payload


def _invoice_fields(
    amount: Money,
    invoice_type: str,
    customer_name: Optional[str],
    customer_email: Optional[str],
    mobile_number: Optional[str],
    country_code: Optional[str],
    reference_number: Optional[str],
    description: Optional[str],
    expires_at: Optional[str],
    language: Optional[str],
    webhook: Optional[str],
    allocate_pay_type: Optional[Sequence[int]],
    items_list: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return _to_payload(
        {
            "amount": amount,
            "invoiceType": invoice_type,
            "customerName": customer_name,
            "customerEmail": customer_email,
            "mobileNumber": mobile_number,
            "countryCode": country_code,
            "referenceNumber": reference_number,
            "description": description,
            "expiresAt": expires_at,
            "language": language,
            "webhook": webhook,
            "allocatePayType": allocate_pay_type,
            "itemsList": items_list,
        }
    )


class Invoices(Resource):
    def create(
        self,
        *,
        amount: Money,
        invoice_type: str = "1",
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        mobile_number: Optional[str] = None,
        country_code: Optional[str] = None,
        reference_number: Optional[str] = None,
        description: Optional[str] = None,
        expires_at: Optional[str] = None,
        language: Optional[str] = None,
        webhook: Optional[str] = None,
        allocate_pay_type: Optional[Sequence[int]] = None,
        items_list: Optional[List[Dict[str, Any]]] = None,
    ) -> HesabeObject:
        """
        Creates a single payable invoice. ``invoice_type="1"`` sends an SMS and
        needs ``mobile_number`` plus ``country_code``; ``"0"`` returns a link.
        """
        return self._merchant(
            "POST",
            "api/v1/invoice",
            payload=self._with_merchant_code(
                _invoice_fields(
                    amount, invoice_type, customer_name, customer_email, mobile_number,
                    country_code, reference_number, description, expires_at, language,
                    webhook, allocate_pay_type, items_list,
                )
            ),
            idempotent=False,
        )

    def create_subscription(
        self,
        *,
        amount: Money,
        frequency: str,
        noof_recurrence: str,
        subscription_type: str,
        start_date: str,
        invoice_type: str = "0",
        **kwargs: Any,
    ) -> HesabeObject:
        """
        Creates a recurring invoice. ``subscription_type="0"`` lets Hesabe
        auto-capture; ``"1"`` means you capture on demand.
        """
        payload = self._with_merchant_code(
            _invoice_fields(
                amount, invoice_type,
                kwargs.get("customer_name"), kwargs.get("customer_email"),
                kwargs.get("mobile_number"), kwargs.get("country_code"),
                kwargs.get("reference_number"), kwargs.get("description"),
                kwargs.get("expires_at"), kwargs.get("language"),
                kwargs.get("webhook"), kwargs.get("allocate_pay_type"),
                kwargs.get("items_list"),
            )
        )
        payload.update(
            {
                "subscription": "1",
                "frequency": frequency,
                "noofRecurrence": noof_recurrence,
                "SubscriptionType": subscription_type,
                "startDate": start_date,
            }
        )
        return self._merchant("POST", "api/v1/invoice/", payload=payload, idempotent=False)

    def create_split(self, invoices: Sequence[Dict[str, Any]]) -> List[HesabeObject]:
        """Splits one bill across several payers; each entry becomes its own invoice."""
        return self._merchant(
            "POST",
            "api/v1/invoice/split",
            payload=self._with_merchant_code({"invoices": self._prepare(invoices)}),
            idempotent=False,
        )

    def create_installment(self, invoices: Sequence[Dict[str, Any]]) -> List[HesabeObject]:
        """Creates HeStallMent invoices, letting the customer pay across installments."""
        return self._merchant(
            "POST",
            "api/v1/invoice/emi",
            payload=self._with_merchant_code({"invoices": self._prepare(invoices)}),
            idempotent=False,
        )

    def list(
        self,
        *,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        search: Optional[str] = None,
        invoice_type: Optional[str] = None,
    ) -> HesabeObject:
        """Returns a page of invoices with ``data``, ``pagination``, and ``stats``."""
        result = self._merchant(
            "GET",
            "api/v1/invoice-dashboard",
            payload=self._with_merchant_code(),
            query={
                "page": page,
                "fromDate": from_date,
                "toDate": to_date,
                "search": search,
                "invoiceType": invoice_type,
            },
        )
        page_body = HesabeObject(result.get("invoices") or {})
        page_body["stats"] = result.get("stats")
        return page_body

    def retrieve(self, invoice_id: int) -> HesabeObject:
        return self._merchant(
            "GET", f"api/v1/invoice/{invoice_id}", payload=self._with_merchant_code()
        )

    def cancel(self, invoice_token: str) -> None:
        """Cancels an unpaid invoice. Identified by token, not numeric id."""
        self._merchant(
            "PUT",
            f"api/v1/invoice/{quote(invoice_token, safe='')}",
            payload=self._with_merchant_code({"statusId": "3"}),
            idempotent=False,
        )

    def resend(self, *, invoice_id: int, mobile_number: str, country_code: str) -> HesabeObject:
        """Re-sends an existing invoice without creating a new one."""
        return self._merchant(
            "POST",
            "api/v1/invoice/resend",
            payload=self._with_merchant_code(
                {
                    "resendId": str(invoice_id),
                    "mobileNumber": mobile_number,
                    "countryCode": country_code,
                }
            ),
            idempotent=False,
        )

    def send_bulk(self, invoice_ids: Sequence[Any]) -> None:
        """Sends several already-created invoices by SMS in one call."""
        self._merchant(
            "POST",
            "api/v1/invoice/bulk",
            payload=self._with_merchant_code({"ids": [str(i) for i in invoice_ids]}),
            idempotent=False,
        )

    def _prepare(self, invoices: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merchant_code = self._transport.config.merchant_code
        return [{**_to_payload(dict(item)), "merchantCode": merchant_code} for item in invoices]

from __future__ import annotations

import json
from typing import Any, Dict, Union

from .errors import HesabeSignatureError
from .resources.transactions import Transactions
from .types import HesabeObject, _normalize_amount


class Webhooks:
    def __init__(self, transactions: Transactions) -> None:
        self._transactions = transactions

    def parse(self, body: Union[str, bytes, Dict[str, Any]]) -> HesabeObject:
        if isinstance(body, (str, bytes)):
            try:
                payload = json.loads(body)
            except (ValueError, RecursionError):
                # RecursionError: deeply nested brackets in a forged body.
                raise HesabeSignatureError("Webhook body is not valid JSON") from None
        else:
            payload = body

        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise HesabeSignatureError("Webhook payload has no transaction token")
        return HesabeObject.wrap(payload)

    def verify(self, body: Union[str, bytes, Dict[str, Any]]) -> HesabeObject:
        """
        Hesabe sends webhooks unsigned and in clear text, so the payload alone
        proves nothing — anyone who learns your webhook URL can forge one. This
        re-reads the transaction from the API and returns that authoritative
        copy. Use it, not ``parse``, before releasing goods.
        """
        claimed = self.parse(body)
        confirmed = self._transactions.retrieve(claimed["token"])

        if confirmed.get("status") != claimed.get("status") or _normalize_amount(
            confirmed.get("amount")
        ) != _normalize_amount(claimed.get("amount")):
            raise HesabeSignatureError(
                f"Webhook does not match transaction {claimed['token']}: "
                f"claimed {claimed.get('status')} {claimed.get('amount')}, "
                f"Hesabe reports {confirmed.get('status')} {confirmed.get('amount')}"
            )
        return confirmed

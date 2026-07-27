from __future__ import annotations

from typing import Any

from .config import HesabeConfig, resolve_config
from .http import Transport
from .resources.authorizations import Authorizations
from .resources.bulk_invoices import BulkInvoices
from .resources.cards import Cards
from .resources.checkout import Checkout
from .resources.customers import Customers
from .resources.invoices import Invoices
from .resources.open_invoices import OpenInvoices
from .resources.pos import Pos
from .resources.profile import Profile
from .resources.refunds import Refunds
from .resources.reports import Reports
from .resources.subscriptions import Subscriptions
from .resources.transactions import Transactions
from .session import MerchantSession
from .webhooks import Webhooks


class Hesabe:
    def __init__(self, **options: Any) -> None:
        self._config: HesabeConfig = resolve_config(**options)

        transport = Transport(self._config)
        session = MerchantSession(transport)

        self.checkout = Checkout(transport, session)
        self.transactions = Transactions(transport, session)
        self.customers = Customers(transport, session)
        self.cards = Cards(transport, session)
        self.subscriptions = Subscriptions(transport, session)
        self.authorizations = Authorizations(transport, session)
        self.invoices = Invoices(transport, session)
        self.open_invoices = OpenInvoices(transport, session)
        self.bulk_invoices = BulkInvoices(transport, session)
        self.refunds = Refunds(transport, session)
        self.reports = Reports(transport, session)
        self.profile = Profile(transport, session)
        self.pos = Pos(transport, session)
        self.webhooks = Webhooks(self.transactions)

    @property
    def environment(self) -> str:
        return self._config.environment

    @property
    def merchant_code(self) -> str:
        return self._config.merchant_code

    def __repr__(self) -> str:
        return f"Hesabe(merchant_code={self.merchant_code!r}, environment={self.environment!r})"

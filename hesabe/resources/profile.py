from __future__ import annotations

from ..resource import Resource
from ..types import HesabeObject


class Profile(Resource):
    def retrieve(self) -> HesabeObject:
        """Merchant identity, bank details, commission rates, and enabled countries."""
        return self._merchant("GET", "api/v1/profile", payload=self._with_merchant_code())

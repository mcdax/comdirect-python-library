"""Data classes for the ``/api/reports/*`` endpoints.

One endpoint today — the cross-product balance report. Each item in
``values`` is either an ``AccountBalance``-shaped dict, a ``CardBalance``,
an ``InstallmentLoanBalance``, a ``FixedTermSavings`` or similar,
distinguished by the ``productType`` field. We keep the raw inner dict so
callers can branch on ``productType`` without us having to model every
product variant.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProductBalance:
    """Consolidated balance entry for a single product (account / card /
    loan / fixed-term savings).

    The ``balance`` attribute is the raw inner dict rather than a parsed
    type — its shape depends on ``productType``. Inspect ``productType`` and
    index into ``balance`` yourself, or extend this module with typed
    sub-classes once you know which product types you need.
    """

    productId: str
    productType: str
    targetClientId: Optional[str] = None
    clientConnectionType: Optional[str] = None
    balance: Optional[dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProductBalance":
        return cls(
            productId=data["productId"],
            productType=data["productType"],
            targetClientId=data.get("targetClientId"),
            clientConnectionType=data.get("clientConnectionType"),
            balance=data.get("balance"),
        )


__all__ = ["ProductBalance"]

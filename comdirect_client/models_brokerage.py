"""Data classes for the ``/api/brokerage/*`` endpoints.

Models the read surface only (depots, positions, transactions, orders,
instruments). Order CRUD, quotes and the pre-validation / validation /
cost-indication flow are not yet wrapped — implement those as a follow-up
when you actually need to place trades through this library.

Field set follows the Swagger spec shipped with devmapal's fork of this
library. Unused fields are still parsed but not required — the
``from_dict`` classmethods tolerate missing values.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from comdirect_client.models import AmountValue, EnumText


# ---------------------------------------------------------------------------
# Instrument (shared across depot positions, depot transactions and orders)
# ---------------------------------------------------------------------------


@dataclass
class Instrument:
    """Financial instrument (stock, ETF, derivative, etc.)."""

    instrumentId: str
    wkn: Optional[str] = None
    isin: Optional[str] = None
    mnemonic: Optional[str] = None
    name: Optional[str] = None
    shortName: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Instrument":
        return cls(
            instrumentId=data["instrumentId"],
            wkn=data.get("wkn"),
            isin=data.get("isin"),
            mnemonic=data.get("mnemonic"),
            name=data.get("name"),
            shortName=data.get("shortName"),
        )


@dataclass
class Price:
    """Quoted price for an instrument at a point in time."""

    price: AmountValue
    priceDateTime: Optional[str] = None
    quantity: Optional[AmountValue] = None
    type: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Price":
        return cls(
            price=AmountValue.from_dict(data["price"]),
            priceDateTime=data.get("priceDateTime"),
            quantity=AmountValue.from_dict(data["quantity"]) if data.get("quantity") else None,
            type=data.get("type"),
        )


# ---------------------------------------------------------------------------
# Depots and positions
# ---------------------------------------------------------------------------


@dataclass
class Depot:
    """Master data for a comdirect securities account."""

    depotId: str
    depotDisplayId: str
    clientId: str
    defaultSettlementAccountId: Optional[str] = None
    settlementAccountIds: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Depot":
        return cls(
            depotId=data["depotId"],
            depotDisplayId=data["depotDisplayId"],
            clientId=data["clientId"],
            defaultSettlementAccountId=data.get("defaultSettlementAccountId"),
            settlementAccountIds=list(data.get("settlementAccountIds") or []),
        )


@dataclass
class DepotPosition:
    """A single holding inside a depot."""

    depotId: str
    positionId: str
    wkn: Optional[str] = None
    custodyType: Optional[str] = None
    quantity: Optional[AmountValue] = None
    availableQuantity: Optional[AmountValue] = None
    currentPrice: Optional[Price] = None
    purchasePrice: Optional[AmountValue] = None
    currentValue: Optional[AmountValue] = None
    purchaseValue: Optional[AmountValue] = None
    profitLossPurchaseAbs: Optional[AmountValue] = None
    profitLossPurchaseRel: Optional[str] = None
    profitLossPrevDayAbs: Optional[AmountValue] = None
    profitLossPrevDayRel: Optional[str] = None
    instrument: Optional[Instrument] = None
    version: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DepotPosition":
        def _amt(key: str) -> Optional[AmountValue]:
            return AmountValue.from_dict(data[key]) if data.get(key) else None

        return cls(
            depotId=data["depotId"],
            positionId=data["positionId"],
            wkn=data.get("wkn"),
            custodyType=data.get("custodyType"),
            quantity=_amt("quantity"),
            availableQuantity=_amt("availableQuantity"),
            currentPrice=(
                Price.from_dict(data["currentPrice"]) if data.get("currentPrice") else None
            ),
            purchasePrice=_amt("purchasePrice"),
            currentValue=_amt("currentValue"),
            purchaseValue=_amt("purchaseValue"),
            profitLossPurchaseAbs=_amt("profitLossPurchaseAbs"),
            profitLossPurchaseRel=data.get("profitLossPurchaseRel"),
            profitLossPrevDayAbs=_amt("profitLossPrevDayAbs"),
            profitLossPrevDayRel=data.get("profitLossPrevDayRel"),
            instrument=(
                Instrument.from_dict(data["instrument"]) if data.get("instrument") else None
            ),
            version=data.get("version"),
        )


@dataclass
class DepotTransaction:
    """A buy / sell / transfer in a depot."""

    transactionId: str
    bookingStatus: Optional[str] = None
    bookingDate: Optional[str] = None  # YYYY-MM-DD — kept as str to match banking Transaction
    settlementDate: Optional[str] = None
    businessDate: Optional[str] = None
    quantity: Optional[AmountValue] = None
    instrumentId: Optional[str] = None
    instrument: Optional[Instrument] = None
    executionPrice: Optional[AmountValue] = None
    transactionValue: Optional[AmountValue] = None
    transactionDirection: Optional[str] = None  # IN / OUT
    transactionType: Optional[str] = None  # BUY / SELL / TRANSFER_IN / TRANSFER_OUT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DepotTransaction":
        def _amt(key: str) -> Optional[AmountValue]:
            return AmountValue.from_dict(data[key]) if data.get(key) else None

        return cls(
            transactionId=data["transactionId"],
            bookingStatus=data.get("bookingStatus"),
            bookingDate=data.get("bookingDate"),
            settlementDate=data.get("settlementDate"),
            businessDate=data.get("businessDate"),
            quantity=_amt("quantity"),
            instrumentId=data.get("instrumentId"),
            instrument=(
                Instrument.from_dict(data["instrument"]) if data.get("instrument") else None
            ),
            executionPrice=_amt("executionPrice"),
            transactionValue=_amt("transactionValue"),
            transactionDirection=data.get("transactionDirection"),
            transactionType=data.get("transactionType"),
        )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@dataclass
class Execution:
    """A single execution (fill) within an order."""

    executionId: str
    executionNumber: Optional[int] = None
    executedQuantity: Optional[AmountValue] = None
    executionPrice: Optional[AmountValue] = None
    executionTimestamp: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Execution":
        return cls(
            executionId=data["executionId"],
            executionNumber=data.get("executionNumber"),
            executedQuantity=(
                AmountValue.from_dict(data["executedQuantity"])
                if data.get("executedQuantity")
                else None
            ),
            executionPrice=(
                AmountValue.from_dict(data["executionPrice"])
                if data.get("executionPrice")
                else None
            ),
            executionTimestamp=data.get("executionTimestamp"),
        )


@dataclass
class Order:
    """An order (market/limit/stop/...) with executions."""

    orderId: str
    depotId: Optional[str] = None
    settlementAccountId: Optional[str] = None
    creationTimestamp: Optional[str] = None
    orderType: Optional[str] = None
    orderStatus: Optional[str] = None
    side: Optional[str] = None  # BUY / SELL
    instrumentId: Optional[str] = None
    venueId: Optional[str] = None
    quantity: Optional[AmountValue] = None
    openQuantity: Optional[AmountValue] = None
    cancelledQuantity: Optional[AmountValue] = None
    executedQuantity: Optional[AmountValue] = None
    limit: Optional[AmountValue] = None
    triggerLimit: Optional[AmountValue] = None
    validityType: Optional[str] = None
    validity: Optional[str] = None  # ISO date
    expectedValue: Optional[AmountValue] = None
    executions: list[Execution] = field(default_factory=list)
    quoteTicketId: Optional[str] = None
    version: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Order":
        def _amt(key: str) -> Optional[AmountValue]:
            return AmountValue.from_dict(data[key]) if data.get(key) else None

        return cls(
            orderId=data["orderId"],
            depotId=data.get("depotId"),
            settlementAccountId=data.get("settlementAccountId"),
            creationTimestamp=data.get("creationTimestamp"),
            orderType=data.get("orderType"),
            orderStatus=data.get("orderStatus"),
            side=data.get("side"),
            instrumentId=data.get("instrumentId"),
            venueId=data.get("venueId"),
            quantity=_amt("quantity"),
            openQuantity=_amt("openQuantity"),
            cancelledQuantity=_amt("cancelledQuantity"),
            executedQuantity=_amt("executedQuantity"),
            limit=_amt("limit"),
            triggerLimit=_amt("triggerLimit"),
            validityType=data.get("validityType"),
            validity=data.get("validity"),
            expectedValue=_amt("expectedValue"),
            executions=[Execution.from_dict(e) for e in (data.get("executions") or [])],
            quoteTicketId=data.get("quoteTicketId"),
            version=data.get("version"),
        )


# ``EnumText`` re-exported for convenience — some brokerage dicts nest it.
__all__ = [
    "AmountValue",
    "Depot",
    "DepotPosition",
    "DepotTransaction",
    "EnumText",
    "Execution",
    "Instrument",
    "Order",
    "Price",
]

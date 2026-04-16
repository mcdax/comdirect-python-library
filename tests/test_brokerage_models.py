"""Smoke tests for brokerage / messages / reports data classes.

These tests only exercise ``from_dict`` — they verify that the dataclasses
tolerate the minimum-payload and full-payload shapes documented in the
official Swagger. Live API behaviour is not exercised.
"""

from decimal import Decimal

from comdirect_client.models_brokerage import (
    Depot,
    DepotPosition,
    DepotTransaction,
    Execution,
    Instrument,
    Order,
    Price,
)
from comdirect_client.models_messages import Document, DocumentMetadata
from comdirect_client.models_reports import ProductBalance


class TestDepot:
    def test_from_dict_minimal(self) -> None:
        depot = Depot.from_dict(
            {
                "depotId": "D123",
                "depotDisplayId": "1234567890",
                "clientId": "C1",
            }
        )
        assert depot.depotId == "D123"
        assert depot.depotDisplayId == "1234567890"
        assert depot.settlementAccountIds == []

    def test_from_dict_with_settlements(self) -> None:
        depot = Depot.from_dict(
            {
                "depotId": "D123",
                "depotDisplayId": "1234567890",
                "clientId": "C1",
                "defaultSettlementAccountId": "A1",
                "settlementAccountIds": ["A1", "A2"],
            }
        )
        assert depot.defaultSettlementAccountId == "A1"
        assert depot.settlementAccountIds == ["A1", "A2"]


class TestDepotPosition:
    def test_from_dict_full(self) -> None:
        pos = DepotPosition.from_dict(
            {
                "depotId": "D1",
                "positionId": "P1",
                "wkn": "A2N9D9",
                "quantity": {"value": "10", "unit": "XXX"},
                "currentPrice": {
                    "price": {"value": "123.45", "unit": "EUR"},
                    "priceDateTime": "2026-04-11T10:00:00,00",
                },
                "currentValue": {"value": "1234.50", "unit": "EUR"},
                "instrument": {
                    "instrumentId": "I1",
                    "wkn": "A2N9D9",
                    "isin": "US0378331005",
                    "name": "Apple Inc.",
                },
            }
        )
        assert pos.wkn == "A2N9D9"
        assert pos.quantity is not None and pos.quantity.value == Decimal("10")
        assert pos.currentPrice is not None and pos.currentPrice.price.value == Decimal("123.45")
        assert pos.instrument is not None and pos.instrument.isin == "US0378331005"


class TestOrder:
    def test_from_dict_with_executions(self) -> None:
        order = Order.from_dict(
            {
                "orderId": "O1",
                "depotId": "D1",
                "orderType": "LIMIT",
                "orderStatus": "EXECUTED",
                "side": "BUY",
                "instrumentId": "I1",
                "quantity": {"value": "100", "unit": "XXX"},
                "limit": {"value": "50.00", "unit": "EUR"},
                "executions": [
                    {
                        "executionId": "E1",
                        "executionNumber": 1,
                        "executedQuantity": {"value": "50", "unit": "XXX"},
                        "executionPrice": {"value": "49.95", "unit": "EUR"},
                        "executionTimestamp": "2026-04-11T10:00:00,00",
                    }
                ],
            }
        )
        assert order.orderStatus == "EXECUTED"
        assert len(order.executions) == 1
        assert isinstance(order.executions[0], Execution)
        assert order.executions[0].executionNumber == 1

    def test_from_dict_minimal(self) -> None:
        order = Order.from_dict({"orderId": "O1"})
        assert order.orderId == "O1"
        assert order.executions == []


class TestInstrument:
    def test_from_dict(self) -> None:
        inst = Instrument.from_dict(
            {
                "instrumentId": "I1",
                "wkn": "A2N9D9",
                "isin": "US0378331005",
                "name": "Apple Inc.",
            }
        )
        assert inst.isin == "US0378331005"


class TestDepotTransaction:
    def test_from_dict(self) -> None:
        tx = DepotTransaction.from_dict(
            {
                "transactionId": "T1",
                "bookingStatus": "BOOKED",
                "bookingDate": "2026-04-01",
                "transactionDirection": "IN",
                "transactionType": "BUY",
                "quantity": {"value": "50", "unit": "XXX"},
                "transactionValue": {"value": "2500.00", "unit": "EUR"},
            }
        )
        assert tx.bookingStatus == "BOOKED"
        assert tx.transactionType == "BUY"


class TestPrice:
    def test_from_dict_minimal(self) -> None:
        p = Price.from_dict({"price": {"value": "10.00", "unit": "EUR"}})
        assert p.price.value == Decimal("10.00")
        assert p.quantity is None


class TestDocument:
    def test_from_dict_with_metadata(self) -> None:
        doc = Document.from_dict(
            {
                "documentId": "DOC1",
                "name": "Kontoauszug_2026-03.pdf",
                "mimeType": "application/pdf",
                "dateCreation": "2026-04-01",
                "deletable": False,
                "advertisement": False,
                "documentMetaData": {
                    "archived": False,
                    "alreadyRead": True,
                    "predocumentExists": False,
                    "dateRead": "2026-04-05T10:00:00",
                },
            }
        )
        assert doc.documentId == "DOC1"
        assert doc.mimeType == "application/pdf"
        assert isinstance(doc.documentMetaData, DocumentMetadata)
        assert doc.documentMetaData.alreadyRead is True


class TestProductBalance:
    def test_from_dict_keeps_raw_balance(self) -> None:
        pb = ProductBalance.from_dict(
            {
                "productId": "P1",
                "productType": "ACCOUNT",
                "targetClientId": "C1",
                "clientConnectionType": "OWNER",
                "balance": {"value": "1000.00", "unit": "EUR"},
            }
        )
        assert pb.productType == "ACCOUNT"
        # Raw dict preserved; caller branches on productType.
        assert pb.balance == {"value": "1000.00", "unit": "EUR"}

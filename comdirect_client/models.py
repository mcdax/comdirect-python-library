"""Data classes for comdirect banking API responses.

These are plain dataclasses with a ``from_dict`` classmethod for JSON parsing.
No I/O, no side effects, no business logic beyond field extraction and type
conversion. The only exception is ``Transaction.remittance`` which lazily
parses ``remittanceInfo`` via :mod:`comdirect_client.remittance`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from comdirect_client.remittance import ParsedRemittance, parse as parse_remittance


@dataclass
class AmountValue:
    """Monetary amount with currency/unit.

    Unit is usually an ISO-4217 code like ``EUR`` but may also be
    ``XXX`` (pieces), ``XXC`` (percent), etc.
    """

    value: Decimal
    unit: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "AmountValue":
        return cls(value=Decimal(data["value"]), unit=data["unit"])


@dataclass
class EnumText:
    """Key/text pair used for enumerated values (account types, transaction
    categories, etc.).

    Match on ``key`` — it is stable across languages. ``text`` is the
    human-readable label returned by the API (English in practice, despite
    what the German PDF claims).
    """

    key: str
    text: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "EnumText":
        return cls(key=data["key"], text=data["text"])


@dataclass
class AccountInformation:
    """Account details for the counterparty of a transaction (remitter,
    debtor or creditor).
    """

    holderName: str
    iban: Optional[str] = None
    bic: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountInformation":
        return cls(
            holderName=data["holderName"],
            iban=data.get("iban"),
            bic=data.get("bic"),
        )


@dataclass
class Account:
    """Master data for a comdirect account (Giro, Tagesgeld, etc.)."""

    accountId: str
    accountDisplayId: str
    currency: str
    clientId: str
    accountType: EnumText
    iban: Optional[str] = None
    bic: Optional[str] = None
    creditLimit: Optional[AmountValue] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Account":
        return cls(
            accountId=data["accountId"],
            accountDisplayId=data["accountDisplayId"],
            currency=data["currency"],
            clientId=data["clientId"],
            accountType=EnumText.from_dict(data["accountType"]),
            iban=data.get("iban"),
            bic=data.get("bic"),
            creditLimit=(
                AmountValue.from_dict(data["creditLimit"]) if data.get("creditLimit") else None
            ),
        )


@dataclass
class AccountBalance:
    """Balance snapshot for a single account."""

    accountId: str
    account: Account
    balance: AmountValue
    balanceEUR: AmountValue
    availableCashAmount: AmountValue
    availableCashAmountEUR: AmountValue

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountBalance":
        return cls(
            accountId=data["accountId"],
            account=Account.from_dict(data["account"]),
            balance=AmountValue.from_dict(data["balance"]),
            balanceEUR=AmountValue.from_dict(data["balanceEUR"]),
            availableCashAmount=AmountValue.from_dict(data["availableCashAmount"]),
            availableCashAmountEUR=AmountValue.from_dict(data["availableCashAmountEUR"]),
        )


@dataclass
class Transaction:
    """A single account transaction (Kontoumsatz).

    ``remittanceInfo`` is kept as the raw API string. Use the ``remittance``
    property for the structured, SEPA-aware parse, or ``remittance_lines`` for
    the flat list of Buchungstext lines as shown in the banking web UI.
    """

    bookingStatus: str
    reference: str
    valutaDate: str
    newTransaction: bool
    amount: Optional[AmountValue] = None
    transactionType: Optional[EnumText] = None
    remittanceInfo: Optional[str] = None
    bookingDate: Optional[date] = None
    remitter: Optional[AccountInformation] = None
    debtor: Optional[AccountInformation] = None
    creditor: Optional[AccountInformation] = None
    endToEndReference: Optional[str] = None
    directDebitCreditorId: Optional[str] = None
    directDebitMandateId: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        booking_date = date.fromisoformat(data["bookingDate"]) if data.get("bookingDate") else None
        amount = AmountValue.from_dict(data["amount"]) if data.get("amount") else None
        transaction_type = (
            EnumText.from_dict(data["transactionType"]) if data.get("transactionType") else None
        )
        remitter = AccountInformation.from_dict(data["remitter"]) if data.get("remitter") else None
        debtor = AccountInformation.from_dict(data["debtor"]) if data.get("debtor") else None
        creditor = AccountInformation.from_dict(data["creditor"]) if data.get("creditor") else None
        return cls(
            bookingStatus=data["bookingStatus"],
            reference=data["reference"],
            valutaDate=data["valutaDate"],
            newTransaction=data["newTransaction"],
            amount=amount,
            transactionType=transaction_type,
            remittanceInfo=data.get("remittanceInfo"),
            bookingDate=booking_date,
            remitter=remitter,
            debtor=debtor,
            creditor=creditor,
            endToEndReference=data.get("endToEndReference"),
            directDebitCreditorId=data.get("directDebitCreditorId"),
            directDebitMandateId=data.get("directDebitMandateId"),
        )

    @property
    def remittance(self) -> ParsedRemittance:
        """Lazily parse ``remittanceInfo`` into Buchungstext lines + SEPA
        metadata. See :mod:`comdirect_client.remittance` for the rules.

        Prefer this property over the top-level ``endToEndReference`` /
        ``directDebitCreditorId`` / ``directDebitMandateId`` fields: in live
        testing, the top-level fields are almost always ``None`` even when
        the remittanceInfo string embeds the same data.
        """
        return parse_remittance(self.remittanceInfo, self.bookingStatus)

    @property
    def remittance_lines(self) -> list[str]:
        """Flat list of Buchungstext lines as rendered by the banking web UI."""
        return self.remittance.buchungstext_lines

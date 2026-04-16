"""Data model tests - type structures and parsing."""

from datetime import date
from decimal import Decimal

from comdirect_client.models import (
    Account,
    AccountBalance,
    AccountInformation,
    AmountValue,
    EnumText,
    Transaction,
)


class TestAmountValueModel:
    """Test AmountValue model."""

    def test_amount_value_from_dict(self):
        """Test creating AmountValue from dict."""
        data = {"value": "1000.50", "unit": "EUR"}
        amount = AmountValue.from_dict(data)

        assert amount.value == Decimal("1000.50")
        assert amount.unit == "EUR"

    def test_amount_value_decimal_parsing(self):
        """Test that values are parsed as Decimal."""
        data = {"value": "1000.50", "unit": "EUR"}
        amount = AmountValue.from_dict(data)

        assert isinstance(amount.value, Decimal)

    def test_amount_value_arithmetic(self):
        """Test arithmetic operations on AmountValue."""
        data1 = {"value": "1000.50", "unit": "EUR"}
        data2 = {"value": "500.25", "unit": "EUR"}

        amount1 = AmountValue.from_dict(data1)
        amount2 = AmountValue.from_dict(data2)

        # Test that values can be used in arithmetic
        result = amount1.value + amount2.value
        assert result == Decimal("1500.75")


class TestEnumTextModel:
    """Test EnumText model."""

    def test_enum_text_from_dict(self):
        """Test creating EnumText from dict."""
        data = {"key": "GIRO", "text": "Girokonto"}
        enum = EnumText.from_dict(data)

        assert enum.key == "GIRO"
        assert enum.text == "Girokonto"


class TestAccountInformationModel:
    """Test AccountInformation model."""

    def test_account_information_from_dict(self):
        """Test creating AccountInformation from dict."""
        data = {
            "holderName": "John Doe",
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
        }
        info = AccountInformation.from_dict(data)

        assert info.holderName == "John Doe"
        assert info.iban == "DE89370400440532013000"
        assert info.bic == "COBADEFFXXX"

    def test_account_information_with_null_iban(self):
        """Test AccountInformation with null optional fields."""
        data = {
            "holderName": "Jane Doe",
        }
        info = AccountInformation.from_dict(data)

        assert info.holderName == "Jane Doe"
        assert info.iban is None
        assert info.bic is None


class TestAccountModel:
    """Test Account model."""

    def test_account_from_dict(self):
        """Test creating Account from dict."""
        data = {
            "accountId": "test_account_id",
            "accountDisplayId": "DE89370400440532013000",
            "currency": "EUR",
            "clientId": "test_client_id",
            "accountType": {"key": "GIRO", "text": "Girokonto"},
        }
        account = Account.from_dict(data)

        assert account.accountId == "test_account_id"
        assert account.accountDisplayId == "DE89370400440532013000"
        assert account.currency == "EUR"
        assert account.clientId == "test_client_id"
        assert account.accountType.key == "GIRO"
        assert account.accountType.text == "Girokonto"

    def test_account_with_optional_fields(self):
        """Test Account with optional fields."""
        data = {
            "accountId": "test_account_id",
            "accountDisplayId": "DE89370400440532013000",
            "currency": "EUR",
            "clientId": "test_client_id",
            "accountType": {"key": "GIRO", "text": "Girokonto"},
            "iban": "DE89370400440532013000",
            "bic": "COBADEFFXXX",
            "creditLimit": {"value": "10000.00", "unit": "EUR"},
        }
        account = Account.from_dict(data)

        assert account.iban == "DE89370400440532013000"
        assert account.bic == "COBADEFFXXX"
        assert account.creditLimit.value == Decimal("10000.00")


class TestAccountBalanceModel:
    """Test AccountBalance model."""

    def test_account_balance_from_dict(self):
        """Test creating AccountBalance from dict."""
        data = {
            "accountId": "test_account_id",
            "account": {
                "accountId": "test_account_id",
                "accountDisplayId": "DE89370400440532013000",
                "currency": "EUR",
                "clientId": "test_client_id",
                "accountType": {"key": "GIRO", "text": "Girokonto"},
            },
            "balance": {"value": "1000.50", "unit": "EUR"},
            "balanceEUR": {"value": "1000.50", "unit": "EUR"},
            "availableCashAmount": {"value": "950.00", "unit": "EUR"},
            "availableCashAmountEUR": {"value": "950.00", "unit": "EUR"},
        }
        balance = AccountBalance.from_dict(data)

        assert balance.accountId == "test_account_id"
        assert balance.balance.value == Decimal("1000.50")
        assert balance.account.accountDisplayId == "DE89370400440532013000"


class TestTransactionModel:
    """Test Transaction model."""

    def test_transaction_from_dict(self):
        """Test creating Transaction from dict."""
        data = {
            "bookingStatus": "BOOKED",
            "reference": "Test reference",
            "valutaDate": "2024-01-15",
            "newTransaction": False,
            "amount": {"value": "-50.00", "unit": "EUR"},
            "bookingDate": "2024-01-15",
        }
        transaction = Transaction.from_dict(data)

        assert transaction.bookingStatus == "BOOKED"
        assert transaction.reference == "Test reference"
        assert transaction.valutaDate == "2024-01-15"
        assert transaction.newTransaction is False
        assert transaction.amount.value == Decimal("-50.00")
        assert transaction.bookingDate == date(2024, 1, 15)

    def test_transaction_with_null_optional_fields(self):
        """Test Transaction with null optional fields."""
        data = {
            "bookingStatus": "BOOKED",
            "reference": "Test reference",
            "valutaDate": "2024-01-15",
            "newTransaction": False,
        }
        transaction = Transaction.from_dict(data)

        assert transaction.amount is None
        assert transaction.bookingDate is None
        assert transaction.transactionType is None
        assert transaction.remittance_lines == []
        assert transaction.remitter is None
        assert transaction.debtor is None
        assert transaction.creditor is None

    def test_transaction_with_debtor_field(self):
        """Test Transaction parsing with correct debtor field."""
        data = {
            "bookingStatus": "BOOKED",
            "reference": "Test reference",
            "valutaDate": "2024-01-15",
            "newTransaction": False,
            "debtor": {
                "holderName": "John Doe",
                "iban": "DE89370400440532013000",
            },
        }
        transaction = Transaction.from_dict(data)

        assert transaction.debtor is not None
        assert transaction.debtor.holderName == "John Doe"
        assert transaction.debtor.iban == "DE89370400440532013000"

    def test_transaction_with_remittance_info(self):
        """Test Transaction remittance lines parsing (smoke test).

        Full parser coverage lives in ``test_remittance_info.py``.
        """
        data = {
            "bookingStatus": "BOOKED",
            "reference": "Test reference",
            "valutaDate": "2024-01-15",
            "newTransaction": False,
            "remittanceInfo": "01Payment for services rendered",
        }
        transaction = Transaction.from_dict(data)

        assert transaction.remittance_lines == ["Payment for services rendered"]

    def test_transaction_with_transaction_type(self):
        """Test Transaction with transactionType."""
        data = {
            "bookingStatus": "BOOKED",
            "reference": "Test reference",
            "valutaDate": "2024-01-15",
            "newTransaction": False,
            "transactionType": {"key": "PURCHASE", "text": "Einkauf"},
        }
        transaction = Transaction.from_dict(data)

        assert transaction.transactionType is not None
        assert transaction.transactionType.key == "PURCHASE"
        assert transaction.transactionType.text == "Einkauf"

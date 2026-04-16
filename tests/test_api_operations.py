"""API operation tests - account balances and transactions."""

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from comdirect_client.client import ComdirectClient
from comdirect_client.exceptions import AccountNotFoundError, ValidationError, ServerError


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def authenticated_client(mock_httpx_client):
    """Create an authenticated client with mocked HTTP."""
    from datetime import datetime, timedelta, timezone

    with patch("comdirect_client.client.httpx.AsyncClient", return_value=mock_httpx_client):
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )
        client._http_client = mock_httpx_client
        # Set tokens to simulate authenticated state (use UTC-aware datetime)
        client._access_token = "test_access_token"
        client._refresh_token = "test_refresh_token"
        client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)  # Valid for 1 hour
        client._session_id = "test_session_id"
        yield client


class TestAccountBalancesRetrieval:
    """Test account balances retrieval."""

    @pytest.mark.asyncio
    async def test_retrieve_account_balances_successfully(
        self, authenticated_client, mock_httpx_client, log_capture
    ):
        """Test successfully retrieving account balances."""
        log_capture.set_level(logging.DEBUG)

        # Mock response
        response = Mock()
        response.status_code = 200
        response.json = Mock(
            return_value={
                "values": [
                    {
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
                ]
            }
        )
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        # Call method
        balances = await authenticated_client.get_account_balances()

        # Verify
        assert len(balances) == 1
        assert balances[0].accountId == "test_account_id"
        assert balances[0].balance.value == Decimal("1000.50")
        assert balances[0].account.accountDisplayId == "DE89370400440532013000"

    @pytest.mark.asyncio
    async def test_get_account_balances_without_attributes(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving account balances without account attributes."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        # Call with with_attributes=False
        await authenticated_client.get_account_balances(with_attributes=False)

        # Verify the request was made with correct parameter
        call_args = mock_httpx_client.get.call_args
        assert "without-attr" in call_args.kwargs["params"]
        assert call_args.kwargs["params"]["without-attr"] == "account"

    @pytest.mark.asyncio
    async def test_get_account_balances_without_specific_attributes(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving account balances without specific attributes."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        # Call with specific attributes to exclude
        await authenticated_client.get_account_balances(without_attributes="account,balance")

        # Verify the request was made with correct parameter
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["without-attr"] == "account,balance"

    @pytest.mark.asyncio
    async def test_account_balances_422_validation_error(
        self, authenticated_client, mock_httpx_client
    ):
        """Test handling 422 validation error in account balances request."""
        response = Mock()
        response.status_code = 422
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("422", request=Mock(), response=response)
        )

        mock_httpx_client.get = AsyncMock(return_value=response)

        with pytest.raises(ValidationError):
            await authenticated_client.get_account_balances()

    @pytest.mark.asyncio
    async def test_account_balances_500_server_error(self, authenticated_client, mock_httpx_client):
        """Test handling 500 server error in account balances request."""
        response = Mock()
        response.status_code = 500
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("500", request=Mock(), response=response)
        )

        mock_httpx_client.get = AsyncMock(return_value=response)

        with pytest.raises(ServerError):
            await authenticated_client.get_account_balances()


class TestTransactionRetrieval:
    """Test transaction retrieval."""

    @pytest.mark.asyncio
    async def test_retrieve_transactions_successfully(
        self, authenticated_client, mock_httpx_client, log_capture
    ):
        """Test successfully retrieving transactions."""
        log_capture.set_level(logging.DEBUG)

        response = Mock()
        response.status_code = 200
        response.json = Mock(
            return_value={
                "values": [
                    {
                        "bookingStatus": "BOOKED",
                        "reference": "Test reference",
                        "valutaDate": "2024-01-15",
                        "newTransaction": False,
                        "amount": {"value": "-50.00", "unit": "EUR"},
                        "bookingDate": "2024-01-15",
                        "remittanceInfo": "Payment for services",
                    }
                ]
            }
        )
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        # Call method
        transactions = await authenticated_client.get_transactions("test_account_id")

        # Verify
        assert len(transactions) == 1
        assert transactions[0].bookingStatus == "BOOKED"
        assert transactions[0].amount.value == Decimal("-50.00")
        assert transactions[0].bookingDate == date(2024, 1, 15)

    @pytest.mark.asyncio
    async def test_retrieve_transactions_with_direction_filter(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving transactions with direction filter."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        await authenticated_client.get_transactions(
            "test_account_id", transaction_direction="DEBIT"
        )

        # Verify the request includes the direction parameter
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["transactionDirection"] == "DEBIT"

    @pytest.mark.asyncio
    async def test_retrieve_transactions_with_state_filter(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving transactions with state filter."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        await authenticated_client.get_transactions("test_account_id", transaction_state="BOOKED")

        # Verify the request includes the state parameter
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["transactionState"] == "BOOKED"

    @pytest.mark.asyncio
    async def test_retrieve_transactions_always_fetches_max(
        self, authenticated_client, mock_httpx_client
    ):
        """Test that get_transactions always uses paging-count=500."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        await authenticated_client.get_transactions("test_account_id")

        # Verify paging-count is always 500
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["paging-count"] == "500"

    @pytest.mark.asyncio
    async def test_retrieve_transactions_without_attributes(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving transactions without account attributes."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        await authenticated_client.get_transactions("test_account_id", with_attributes=False)

        # Verify the request was made with correct parameter
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["without-attr"] == "account"

    @pytest.mark.asyncio
    async def test_retrieve_transactions_without_specific_attributes(
        self, authenticated_client, mock_httpx_client
    ):
        """Test retrieving transactions without specific attributes."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(return_value={"values": []})
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        await authenticated_client.get_transactions(
            "test_account_id", without_attributes="account,booking"
        )

        # Verify the request was made with correct parameter
        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"]["without-attr"] == "account,booking"

    @pytest.mark.asyncio
    async def test_transactions_404_account_not_found(
        self, authenticated_client, mock_httpx_client
    ):
        """Test handling 404 when account not found."""
        response = Mock()
        response.status_code = 404
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("404", request=Mock(), response=response)
        )

        mock_httpx_client.get = AsyncMock(return_value=response)

        with pytest.raises(AccountNotFoundError):
            await authenticated_client.get_transactions("nonexistent_account_id")

    @pytest.mark.asyncio
    async def test_transactions_422_validation_error(self, authenticated_client, mock_httpx_client):
        """Test handling 422 validation error in transactions request."""
        response = Mock()
        response.status_code = 422
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("422", request=Mock(), response=response)
        )

        mock_httpx_client.get = AsyncMock(return_value=response)

        with pytest.raises(ValidationError):
            await authenticated_client.get_transactions("test_account_id")

    @pytest.mark.asyncio
    async def test_transactions_500_server_error(self, authenticated_client, mock_httpx_client):
        """Test handling 500 server error in transactions request."""
        response = Mock()
        response.status_code = 500
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("500", request=Mock(), response=response)
        )

        mock_httpx_client.get = AsyncMock(return_value=response)

        with pytest.raises(ServerError):
            await authenticated_client.get_transactions("test_account_id")

    @pytest.mark.asyncio
    async def test_transactions_with_null_optional_fields(
        self, authenticated_client, mock_httpx_client
    ):
        """Test parsing transactions with null optional fields."""
        response = Mock()
        response.status_code = 200
        response.json = Mock(
            return_value={
                "values": [
                    {
                        "bookingStatus": "BOOKED",
                        "reference": "Test",
                        "valutaDate": "2024-01-15",
                        "newTransaction": False,
                        "amount": None,
                        "bookingDate": None,
                        "transactionType": None,
                        "remittanceInfo": None,
                        "remitter": None,
                        "debtor": None,
                        "creditor": None,
                    }
                ]
            }
        )
        response.raise_for_status = Mock()

        mock_httpx_client.get = AsyncMock(return_value=response)

        # Should not raise an exception
        transactions = await authenticated_client.get_transactions("test_account_id")

        assert len(transactions) == 1
        assert transactions[0].amount is None
        assert transactions[0].bookingDate is None
        assert transactions[0].transactionType is None
        assert transactions[0].remittance_lines == []

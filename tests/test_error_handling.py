"""Integration tests for HTTP error handling and query parameters."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from comdirect_client import (
    ComdirectClient,
    ValidationError,
    ServerError,
)


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@pytest.fixture
def client():
    """Create a ComdirectClient instance for testing."""
    client = ComdirectClient(
        client_id="test_id",
        client_secret="test_secret",
        username="test_user",
        password="test_pass",
    )
    # Set up minimal authentication state (use UTC-aware datetime)
    client._access_token = "test_token"
    client._token_expiry = utc_now() + timedelta(hours=1)
    return client


class TestValidationErrorHandling:
    """Test 422 Unprocessable Entity error handling."""

    @pytest.mark.asyncio
    async def test_account_balances_422_validation_error(self, client):
        """Test that 422 response raises ValidationError for account balances."""
        # Mock HTTP response with 422 status
        mock_response = MagicMock()
        mock_response.status_code = 422

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ValidationError) as exc_info:
                await client.get_account_balances(without_attributes="invalid_attr")

            assert "Invalid request parameters" in str(exc_info.value)
            assert mock_get.called

    @pytest.mark.asyncio
    async def test_transactions_422_validation_error(self, client):
        """Test that 422 response raises ValidationError for transactions."""
        mock_response = MagicMock()
        mock_response.status_code = 422

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ValidationError) as exc_info:
                await client.get_transactions("test_account_id", without_attributes="invalid_attr")

            assert "Invalid request parameters" in str(exc_info.value)


class TestServerErrorHandling:
    """Test 500 Internal Server Error handling."""

    @pytest.mark.asyncio
    async def test_account_balances_500_server_error(self, client):
        """Test that 500 response raises ServerError for account balances."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ServerError) as exc_info:
                await client.get_account_balances()

            assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transactions_500_server_error(self, client):
        """Test that 500 response raises ServerError for transactions."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(ServerError) as exc_info:
                await client.get_transactions("test_account_id")

            assert "500" in str(exc_info.value)


class TestQueryParameterExposure:
    """Test that query parameters are correctly exposed and sent."""

    @pytest.mark.asyncio
    async def test_account_balances_without_attributes_parameter(self, client):
        """Test that without_attributes parameter is included in request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"values": []}

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.get_account_balances(with_attributes=False)

            # Verify the call includes query parameters
            mock_get.assert_called_once()
            call_args = mock_get.call_args

            # Check that params are passed
            assert "params" in call_args.kwargs
            assert call_args.kwargs["params"] == {"without-attr": "account"}

    @pytest.mark.asyncio
    async def test_account_balances_custom_without_attributes(self, client):
        """Test custom without_attributes parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"values": []}

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.get_account_balances(without_attributes="balance,currency")

            call_args = mock_get.call_args
            assert call_args.kwargs["params"] == {"without-attr": "balance,currency"}

    @pytest.mark.asyncio
    async def test_transactions_without_attributes_parameter(self, client):
        """Test that transactions without_attributes parameter works."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"values": []}

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.get_transactions("test_account_id", with_attributes=False)

            call_args = mock_get.call_args
            assert call_args.kwargs["params"] == {"paging-count": "500", "without-attr": "account"}

    @pytest.mark.asyncio
    async def test_transactions_combined_parameters(self, client):
        """Test transactions with multiple query parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"values": []}

        with patch.object(client._http_client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await client.get_transactions(
                "test_account_id",
                transaction_direction="CREDIT",
                without_attributes="booking",
            )

            call_args = mock_get.call_args
            params = call_args.kwargs["params"]

            # Verify all parameters are present
            assert params["transactionDirection"] == "CREDIT"
            assert params["paging-count"] == "500"
            assert params["without-attr"] == "booking"


class TestDebtorField:
    """Verify the debtor field is parsed from the documented field name.

    Live API responses always use ``debtor``. The earlier `deptor` typo
    mentioned in older versions of this library was never observed against
    the production API and the fallback has been removed — see
    COMDIRECT_API.md changelog for 2026-04-11.
    """

    def test_transaction_parse_with_debtor_field(self):
        """Test parsing transaction with correct 'debtor' field."""
        from comdirect_client import Transaction

        data = {
            "bookingStatus": "BOOKED",
            "reference": "REF123",
            "valutaDate": "2023-01-01",
            "newTransaction": False,
            "debtor": {
                "holderName": "John Doe",
                "iban": "DE89370400440532013000",
                "bic": "COBADEFF",
            },
        }

        transaction = Transaction.from_dict(data)

        assert transaction.debtor is not None
        assert transaction.debtor.holderName == "John Doe"
        assert transaction.debtor.iban == "DE89370400440532013000"


class TestExceptionHierarchy:
    """Test the exception class hierarchy and types."""

    def test_validation_error_is_comdirect_api_error(self):
        """Test that ValidationError inherits from ComdirectAPIError."""
        from comdirect_client import ComdirectAPIError

        error = ValidationError("Test")
        assert isinstance(error, ComdirectAPIError)

    def test_server_error_is_comdirect_api_error(self):
        """Test that ServerError inherits from ComdirectAPIError."""
        from comdirect_client import ComdirectAPIError

        error = ServerError("Test")
        assert isinstance(error, ComdirectAPIError)

    def test_validation_error_message(self):
        """Test ValidationError message."""
        error = ValidationError("Invalid parameter")
        assert str(error) == "Invalid parameter"

    def test_server_error_message(self):
        """Test ServerError message."""
        error = ServerError("Server returned 500")
        assert str(error) == "Server returned 500"

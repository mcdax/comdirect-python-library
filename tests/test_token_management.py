"""Token refresh and callback tests."""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from comdirect_client.client import ComdirectClient
from comdirect_client.exceptions import TokenExpiredError


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def authenticated_client_with_expiry(mock_httpx_client):
    """Create an authenticated client that will expire soon."""
    with patch("comdirect_client.client.httpx.AsyncClient", return_value=mock_httpx_client):
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            token_refresh_threshold_seconds=120,
        )
        client._http_client = mock_httpx_client
        client._access_token = "test_access_token"
        client._refresh_token = "test_refresh_token"
        client._token_expiry = utc_now() + timedelta(seconds=150)  # Expires in 150 seconds
        client._session_id = "test_session_id"
        yield client


class TestTokenRefresh:
    """Test token refresh functionality."""

    @pytest.mark.asyncio
    async def test_token_refresh_succeeds(
        self, authenticated_client_with_expiry, mock_httpx_client, log_capture
    ):
        """Test successful token refresh."""
        log_capture.set_level(logging.DEBUG)

        # Mock refresh response
        response = Mock()
        response.status_code = 200
        response.json = Mock(
            return_value={
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "expires_in": 600,
            }
        )
        response.raise_for_status = Mock()

        mock_httpx_client.post = AsyncMock(return_value=response)

        # Manually call refresh (normally done by background task)
        success = await authenticated_client_with_expiry.refresh_token()

        # Verify
        assert success
        assert authenticated_client_with_expiry._access_token == "new_access_token"
        assert authenticated_client_with_expiry._refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_token_refresh_fails_with_401(
        self, authenticated_client_with_expiry, mock_httpx_client, log_capture
    ):
        """Test token refresh fails with 401."""
        log_capture.set_level(logging.DEBUG)

        response = Mock()
        response.status_code = 401
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("401", request=Mock(), response=response)
        )

        mock_httpx_client.post = AsyncMock(return_value=response)

        # Refresh should fail
        success = await authenticated_client_with_expiry.refresh_token()

        assert not success

    @pytest.mark.asyncio
    async def test_reauth_callback_invoked_on_refresh_failure(
        self, authenticated_client_with_expiry, mock_httpx_client, log_capture
    ):
        """Test reauth callback is invoked when refresh fails."""
        log_capture.set_level(logging.DEBUG)

        response = Mock()
        response.status_code = 401
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("401", request=Mock(), response=response)
        )

        mock_httpx_client.post = AsyncMock(return_value=response)

        # Register callback
        callback_called = []

        def test_callback(reason):
            callback_called.append(reason)

        authenticated_client_with_expiry.register_reauth_callback(test_callback)

        # Refresh fails
        success = await authenticated_client_with_expiry.refresh_token()

        assert not success
        # Callback should be invoked
        assert len(callback_called) > 0



class TestReauthCallback:
    """Test reauth callback mechanism."""

    def test_register_callback(self):
        """Test registering a reauth callback."""
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )

        callback_called = []

        def test_callback(reason):
            callback_called.append(reason)

        client.register_reauth_callback(test_callback)

        assert client.reauth_callback is not None
        assert client.reauth_callback == test_callback

    def test_register_callback_via_init(self):
        """Test registering callback via constructor."""
        callback_called = []

        def test_callback(reason):
            callback_called.append(reason)

        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            reauth_callback=test_callback,
        )

        assert client.reauth_callback == test_callback


class TestLogging:
    """Test logging behavior."""

    def test_logging_appropriate_levels(self, log_capture):
        """Test that appropriate logging levels are used."""
        log_capture.set_level(logging.DEBUG)

        # Create logger
        logger = logging.getLogger("comdirect_client")

        # Log at different levels
        logger.debug("DEBUG message")
        logger.info("INFO message")
        logger.warning("WARNING message")
        logger.error("ERROR message")

        # Verify all levels are present
        assert any(record.levelno == logging.DEBUG for record in log_capture.records)
        assert any(record.levelno == logging.INFO for record in log_capture.records)
        assert any(record.levelno == logging.WARNING for record in log_capture.records)
        assert any(record.levelno == logging.ERROR for record in log_capture.records)

    def test_no_sensitive_data_in_logs(self, log_capture):
        """Test that sensitive data is not logged."""
        log_capture.set_level(logging.DEBUG)

        # Log with client that has sensitive data
        ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_password",
        )

        # Password should not appear in logs
        for record in log_capture.records:
            assert "test_password" not in record.getMessage()
            assert record.getMessage().lower().count("password") == 0

        # Client secret should not appear in logs
        for record in log_capture.records:
            assert "test_secret" not in record.getMessage()

"""Tests for token persistence functionality."""

import pytest
import tempfile
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from comdirect_client.token_storage import (
    TokenPersistence,
    TokenStorageError,
)


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class TestTokenPersistence:
    """Test token persistence save/load functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def storage_path(self, temp_dir):
        """Create a path for token storage."""
        return str(Path(temp_dir) / "tokens.json")

    def test_init_no_path(self):
        """Test TokenPersistence with no path (no persistence)."""
        persistence = TokenPersistence(storage_path=None)
        assert persistence.storage_path is None

    def test_init_valid_path(self, storage_path):
        """Test TokenPersistence initialization with valid path."""
        persistence = TokenPersistence(storage_path=storage_path)
        assert persistence.storage_path == Path(storage_path)

    def test_init_nonexistent_parent(self):
        """Test TokenPersistence with nonexistent parent directory."""
        invalid_path = "/nonexistent/directory/tokens.json"
        with pytest.raises(TokenStorageError, match="Token storage directory does not exist"):
            TokenPersistence(storage_path=invalid_path)

    def test_save_and_load_tokens(self, storage_path):
        """Test saving and loading tokens."""
        persistence = TokenPersistence(storage_path=storage_path)

        access_token = "test_access_token_123"
        refresh_token = "test_refresh_token_456"
        token_expiry = utc_now() + timedelta(hours=1)

        # Save tokens
        persistence.save_tokens(access_token, refresh_token, token_expiry)

        # Load tokens
        loaded = persistence.load_tokens()
        assert loaded is not None
        loaded_access, loaded_refresh, loaded_expiry = loaded

        assert loaded_access == access_token
        assert loaded_refresh == refresh_token
        # Compare timestamps (allowing small rounding differences)
        # Both should be UTC-aware now
        assert abs((loaded_expiry - token_expiry).total_seconds()) < 1

    def test_load_nonexistent_file(self, storage_path):
        """Test loading from nonexistent file."""
        persistence = TokenPersistence(storage_path=storage_path)
        result = persistence.load_tokens()
        assert result is None

    def test_load_expired_tokens(self, storage_path):
        """Test that expired tokens are still loaded (refresh_token may be valid)."""
        persistence = TokenPersistence(storage_path=storage_path)

        access_token = "test_access_token"
        refresh_token = "test_refresh_token"
        token_expiry = utc_now() - timedelta(hours=1)  # Already expired

        persistence.save_tokens(access_token, refresh_token, token_expiry)

        # Expired tokens are now loaded (behavior changed to allow refresh attempts)
        result = persistence.load_tokens()
        assert result is not None
        loaded_access, loaded_refresh, loaded_expiry = result
        assert loaded_access == access_token
        assert loaded_refresh == refresh_token

    def test_load_corrupted_json(self, storage_path):
        """Test loading corrupted JSON file."""
        # Create a corrupted JSON file
        Path(storage_path).write_text("{invalid json")

        persistence = TokenPersistence(storage_path=storage_path)
        with pytest.raises(TokenStorageError, match="Token file is corrupted"):
            persistence.load_tokens()

    def test_load_missing_fields(self, storage_path):
        """Test loading JSON missing required fields."""
        # Create JSON with missing fields
        data = {"access_token": "test"}  # Missing refresh_token and token_expiry
        Path(storage_path).write_text(json.dumps(data))

        persistence = TokenPersistence(storage_path=storage_path)
        with pytest.raises(TokenStorageError, match="is missing fields"):
            persistence.load_tokens()

    def test_load_invalid_datetime(self, storage_path):
        """Test loading JSON with invalid datetime format."""
        data = {
            "access_token": "test",
            "refresh_token": "test",
            "token_expiry": "not-a-datetime",
        }
        Path(storage_path).write_text(json.dumps(data))

        persistence = TokenPersistence(storage_path=storage_path)
        with pytest.raises(TokenStorageError, match="invalid datetime format"):
            persistence.load_tokens()

    def test_clear_tokens(self, storage_path):
        """Test clearing token storage."""
        persistence = TokenPersistence(storage_path=storage_path)

        # Save tokens
        access_token = "test_access_token"
        refresh_token = "test_refresh_token"
        token_expiry = utc_now() + timedelta(hours=1)
        persistence.save_tokens(access_token, refresh_token, token_expiry)

        # Verify file exists
        assert Path(storage_path).exists()

        # Clear tokens
        persistence.clear_tokens()

        # Verify file is deleted
        assert not Path(storage_path).exists()

    def test_file_permissions(self, storage_path):
        """Test that saved file has restrictive permissions."""
        persistence = TokenPersistence(storage_path=storage_path)

        access_token = "test_access_token"
        refresh_token = "test_refresh_token"
        token_expiry = utc_now() + timedelta(hours=1)

        persistence.save_tokens(access_token, refresh_token, token_expiry)

        # Check file permissions (600 = -rw-------)
        file_mode = Path(storage_path).stat().st_mode
        # Extract permission bits
        perms = file_mode & 0o777
        assert perms == 0o600, f"Expected 0o600 but got {oct(perms)}"

    def test_no_persistence_save(self):
        """Test save with no persistence configured."""
        persistence = TokenPersistence(storage_path=None)

        access_token = "test_access_token"
        refresh_token = "test_refresh_token"
        token_expiry = utc_now() + timedelta(hours=1)

        # Should not raise error
        persistence.save_tokens(access_token, refresh_token, token_expiry)

    def test_no_persistence_load(self):
        """Test load with no persistence configured."""
        persistence = TokenPersistence(storage_path=None)
        result = persistence.load_tokens()
        assert result is None

    def test_token_expiry_iso_format(self, storage_path):
        """Test that token expiry is stored and retrieved in ISO format with UTC timezone."""
        persistence = TokenPersistence(storage_path=storage_path)

        # Use UTC-aware datetime
        original_expiry = datetime(2025, 12, 10, 15, 30, 45, 123456, tzinfo=timezone.utc)
        persistence.save_tokens("access", "refresh", original_expiry)

        # Read raw JSON to verify ISO format with timezone
        data = json.loads(Path(storage_path).read_text())
        assert data["token_expiry"] == original_expiry.isoformat()

        # Load and verify
        loaded = persistence.load_tokens()
        assert loaded is not None
        _, _, loaded_expiry = loaded
        assert loaded_expiry == original_expiry

    def test_multiple_save_overwrites(self, storage_path):
        """Test that multiple saves overwrite previous tokens."""
        persistence = TokenPersistence(storage_path=storage_path)

        # First save
        persistence.save_tokens("access1", "refresh1", utc_now() + timedelta(hours=1))
        loaded1 = persistence.load_tokens()
        assert loaded1 is not None
        assert loaded1[0] == "access1"

        # Second save (overwrite)
        persistence.save_tokens("access2", "refresh2", utc_now() + timedelta(hours=2))
        loaded2 = persistence.load_tokens()
        assert loaded2 is not None
        assert loaded2[0] == "access2"


class TestTokenPersistenceIntegration:
    """Integration tests with ComdirectClient."""

    @pytest.fixture
    def temp_token_file(self):
        """Create a temporary token file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_client_init_with_token_storage_path(self, temp_token_file):
        """Test ComdirectClient initialization with token_storage_path."""
        from comdirect_client import ComdirectClient

        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            token_storage_path=temp_token_file,
        )

        assert client._token_storage is not None
        assert client._token_storage.storage_path == Path(temp_token_file)

    def test_client_init_invalid_storage_path(self):
        """Test ComdirectClient initialization with invalid storage path."""
        from comdirect_client import ComdirectClient

        with pytest.raises(TokenStorageError):
            ComdirectClient(
                client_id="test_id",
                client_secret="test_secret",
                username="test_user",
                password="test_pass",
                token_storage_path="/nonexistent/path/tokens.json",
            )

    def test_client_init_no_token_storage_path(self):
        """Test ComdirectClient initialization without token_storage_path."""
        from comdirect_client import ComdirectClient

        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )

        assert client._token_storage is not None
        assert client._token_storage.storage_path is None

    def test_clear_token_storage_on_close(self, temp_token_file):
        """Test that token storage can be cleared."""
        from comdirect_client import ComdirectClient

        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            token_storage_path=temp_token_file,
        )

        # Manually save a token
        client._access_token = "test_token"
        client._refresh_token = "test_refresh"
        client._token_expiry = utc_now() + timedelta(hours=1)
        client._save_tokens_to_storage()

        # Verify file exists
        assert Path(temp_token_file).exists()

        # Clearing tokens in memory must also clear the persisted file.
        client._clear_tokens()

        # Verify file is deleted and memory is cleared
        assert not Path(temp_token_file).exists()
        assert client._access_token is None
        assert client._refresh_token is None

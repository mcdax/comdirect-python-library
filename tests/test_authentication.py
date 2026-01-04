"""Authentication interface and library configuration tests."""

from comdirect_client.client import ComdirectClient


class TestLibraryInterface:
    """Test the library's public interface and configuration."""

    def test_client_initialization(self):
        """Test client can be initialized with required credentials."""
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )

        assert client.client_id == "test_id"
        assert client.client_secret == "test_secret"
        assert client.username == "test_user"
        assert client.base_url == "https://api.comdirect.de"

    def test_client_initialization_with_custom_base_url(self):
        """Test client can be initialized with custom base URL."""
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            base_url="https://custom.api.comdirect.de",
        )

        assert client.base_url == "https://custom.api.comdirect.de"

    def test_client_has_required_methods(self):
        """Test client has all required async methods."""
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )

        # Check async methods exist
        assert hasattr(client, "authenticate")
        assert callable(getattr(client, "authenticate"))

        assert hasattr(client, "api")
        assert hasattr(client, "refresh_token")
        assert callable(getattr(client, "refresh_token"))

        # Check sync methods exist
        assert hasattr(client, "is_authenticated")
        assert callable(getattr(client, "is_authenticated"))

        assert hasattr(client, "register_reauth_callback")
        assert callable(getattr(client, "register_reauth_callback"))

    def test_is_authenticated_returns_false_initially(self):
        """Test is_authenticated returns False before authentication."""
        client = ComdirectClient(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
        )

        assert not client.is_authenticated()

    def test_reauth_callback_registration(self):
        """Test reauth callback can be registered."""
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

        # Verify callback is stored
        assert client.reauth_callback is not None
        assert client.reauth_callback == test_callback

    def test_client_initialization_with_reauth_callback(self):
        """Test client can be initialized with reauth callback."""
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

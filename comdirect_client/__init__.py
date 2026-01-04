"""Comdirect API Client Library.

Async Python client for the Comdirect Banking API with automatic token refresh.
Uses Bravado to generate API methods from the Swagger specification.
"""

__version__ = "0.1.0"

from comdirect_client.client import ComdirectClient
from comdirect_client.exceptions import (
    ComdirectAPIError,
    AuthenticationError,
    TANTimeoutError,
    SessionActivationError,
    TokenExpiredError,
    NetworkTimeoutError,
    AccountNotFoundError,
    ValidationError,
    ServerError,
)
from comdirect_client.token_storage import (
    TokenPersistence,
    TokenStorageError,
)

__all__ = [
    "ComdirectClient",
    "ComdirectAPIError",
    "AuthenticationError",
    "TANTimeoutError",
    "SessionActivationError",
    "TokenExpiredError",
    "NetworkTimeoutError",
    "AccountNotFoundError",
    "ValidationError",
    "ServerError",
    "TokenPersistence",
    "TokenStorageError",
]

"""Async Python client for the comdirect banking API.

The public surface is intentionally narrow: instantiate ``ComdirectClient``,
authenticate once (triggers push-TAN), then call ``get_account_balances`` or
``get_transactions``. See the module docstring on ``ComdirectClient`` for the
recommended lifecycle.

Brokerage, messages and reports endpoints are also available for read
access — see ``ComdirectClient.get_depots``, ``get_depot_positions``,
``get_documents`` and ``get_all_balances``.
"""

__version__ = "0.3.0"

from comdirect_client.client import ComdirectClient
from comdirect_client.exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    ComdirectAPIError,
    NetworkTimeoutError,
    ServerError,
    SessionActivationError,
    TANTimeoutError,
    TokenExpiredError,
    ValidationError,
)
from comdirect_client.models import (
    Account,
    AccountBalance,
    AccountInformation,
    AmountValue,
    EnumText,
    Transaction,
)
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
from comdirect_client.remittance import ParsedRemittance, parse as parse_remittance_info
from comdirect_client.token_storage import TokenPersistence, TokenStorageError

__all__ = [
    # Client
    "ComdirectClient",
    # Exceptions
    "ComdirectAPIError",
    "AuthenticationError",
    "TANTimeoutError",
    "SessionActivationError",
    "TokenExpiredError",
    "NetworkTimeoutError",
    "AccountNotFoundError",
    "ValidationError",
    "ServerError",
    # Token persistence
    "TokenPersistence",
    "TokenStorageError",
    # Banking models
    "AccountBalance",
    "Account",
    "Transaction",
    "AmountValue",
    "EnumText",
    "AccountInformation",
    # Brokerage models
    "Depot",
    "DepotPosition",
    "DepotTransaction",
    "Execution",
    "Instrument",
    "Order",
    "Price",
    # Messages models
    "Document",
    "DocumentMetadata",
    # Reports models
    "ProductBalance",
    # Remittance parsing
    "ParsedRemittance",
    "parse_remittance_info",
]

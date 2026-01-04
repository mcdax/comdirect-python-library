"""Custom HTTP client adapter for bravado-asyncio that injects Comdirect auth headers."""

import json
import logging
import time
import uuid
from typing import Any, Optional

from bravado_asyncio.http_client import AsyncioClient
from bravado.exception import HTTPError

logger = logging.getLogger(__name__)


class ComdirectBravadoClient(AsyncioClient):
    """Custom bravado-asyncio HTTP client that injects Comdirect authentication headers.

    This adapter extends AsyncioClient to automatically inject:
    - Authorization header with Bearer token
    - x-http-request-info header with session and request IDs
    """

    def __init__(
        self,
        get_access_token: callable,
        get_session_id: callable,
        generate_request_id: callable,
        *args: Any,
        **kwargs: Any,
    ):
        """Initialize the Comdirect Bravado client adapter.

        Args:
            get_access_token: Callable that returns the current access token
            get_session_id: Callable that returns the current session ID (generates if None)
            generate_request_id: Callable that generates a request ID
            *args: Additional arguments passed to AsyncioClient
            **kwargs: Additional keyword arguments passed to AsyncioClient
        """
        super().__init__(*args, **kwargs)
        self._get_access_token = get_access_token
        self._get_session_id = get_session_id
        self._generate_request_id = generate_request_id

    def request(
        self,
        request_params: dict[str, Any],
        operation: Optional[Any] = None,
        request_config: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Make an HTTP request with injected Comdirect headers.

        Args:
            request_params: Request parameters (method, url, headers, etc.)
            operation: Bravado operation object (optional)
            request_config: Additional request configuration (optional)

        Returns:
            Future that resolves to the HTTP response
        """
        # Get or create headers dict
        headers = request_params.get("headers", {})
        if not isinstance(headers, dict):
            headers = dict(headers) if headers else {}
        request_params["headers"] = headers

        # Inject Authorization header
        access_token = self._get_access_token()
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        # Inject x-http-request-info header
        session_id = self._get_session_id()
        request_id = self._generate_request_id()
        headers["x-http-request-info"] = json.dumps(
            {
                "clientRequestId": {
                    "sessionId": session_id,
                    "requestId": request_id,
                }
            }
        )

        # Ensure Accept header is set
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        logger.debug(
            f"Making {request_params.get('method', 'UNKNOWN')} request to "
            f"{request_params.get('url', 'UNKNOWN')} with auth headers"
        )

        # Call parent request method
        return super().request(request_params, operation, request_config)

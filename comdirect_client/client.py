"""Main Comdirect API client implementation with Bravado integration."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, cast

import httpx
from bravado.client import SwaggerClient
from bravado.exception import HTTPError

from comdirect_client.bravado_adapter import ComdirectBravadoClient
from comdirect_client.exceptions import (
    AuthenticationError,
    NetworkTimeoutError,
    SessionActivationError,
    TANTimeoutError,
    TokenExpiredError,
)
from comdirect_client.token_storage import TokenPersistence, TokenStorageError

logger = logging.getLogger(__name__)

# Swagger spec URL
SWAGGER_SPEC_URL = "https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json"


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def sanitize_token(token: str, prefix_length: int = 8) -> str:
    """Sanitize a token for logging by showing only the prefix."""
    if not token or len(token) <= prefix_length:
        return "***"
    return f"{token[:prefix_length]}..."


class ComdirectClient:
    """Async client for the Comdirect Banking API with Bravado integration.

    This client handles:
    - OAuth2 + TAN authentication flow
    - Automatic token refresh via asyncio
    - Token persistence across restarts
    - Reauth callback on token expiration
    - Comprehensive logging with sensitive data sanitization

    The client uses Bravado to generate API methods from the Swagger specification.
    After authentication, access the Bravado client via the `api` attribute to use
    all Comdirect API endpoints.

    IMPORTANT - Persistent Client Usage:
        This client should be kept alive (persistent) throughout your application's
        lifecycle for best functionality. The client runs a background asyncio task
        that automatically refreshes tokens 120 seconds before they expire.

        If you destroy the client instance after each operation:
        - The background refresh task is cancelled
        - Tokens will expire after ~10 minutes
        - A new TAN approval will be required for each session

        Best practice:
        - Create the client once at application startup
        - Reuse the same instance for all API calls
        - Use token_storage_path to persist tokens across application restarts
        - When tokens are loaded from storage, the refresh task starts automatically

    Example:
        ```python
        # Create once at startup
        client = ComdirectClient(
            client_id="...",
            client_secret="...",
            username="...",
            password="...",
            token_storage_path="/path/to/tokens.json",
        )

        # Authenticate (requires TAN approval)
        await client.authenticate()

        # Use Bravado-generated API methods (note: call .result() to get awaitable)
        balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
            user="user"
        ).result()
        balances = balances_response.values  # Access the values from response

        transactions_response = await client.api.banking.v1.accounts.transactions.get(
            accountId="account-uuid"
        ).result()
        transactions = transactions_response.values  # Access the values from response

        # Token auto-refreshes in background - no new TAN needed!
        ```
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        base_url: str = "https://api.comdirect.de",
        swagger_spec_url: str = SWAGGER_SPEC_URL,
        reauth_callback: Optional[Callable[[str], None]] = None,
        tan_status_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
        token_refresh_threshold_seconds: int = 120,
        timeout_seconds: float = 30.0,
        token_storage_path: Optional[str] = None,
    ):
        """Initialize the Comdirect API client.

        Args:
            client_id: OAuth2 client ID from Comdirect Developer Portal
            client_secret: OAuth2 client secret
            username: Comdirect account username
            password: Comdirect account password
            base_url: API base URL (default: production API)
            swagger_spec_url: URL to Swagger/OpenAPI specification (default: official Comdirect spec)
            reauth_callback: Optional callback function invoked when reauth is needed
            tan_status_callback: Optional callback function invoked during TAN approval process
                               Called with (status, data) where status is 'requested', 'pending', 'approved', 'timeout'
            token_refresh_threshold_seconds: Seconds before expiry to trigger refresh (default: 120)
            timeout_seconds: HTTP request timeout in seconds (default: 30.0)
            token_storage_path: Optional file path to persist tokens for session recovery.
                               Enables loading saved tokens on client restart.
                               Parent directory must exist.

        Raises:
            TokenStorageError: If token_storage_path directory doesn't exist
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self._password = password  # Private to avoid accidental logging
        self.base_url = base_url.rstrip("/")
        self.swagger_spec_url = swagger_spec_url
        self.reauth_callback = reauth_callback
        self.tan_status_callback = tan_status_callback
        self.token_refresh_threshold = token_refresh_threshold_seconds
        self.timeout_seconds = timeout_seconds

        # Token persistence
        try:
            self._token_storage = TokenPersistence(token_storage_path)
        except TokenStorageError as e:
            logger.error(f"Failed to initialize token storage: {e}")
            raise

        # State management
        self._session_id: Optional[str] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task[None]] = None

        # HTTP client for auth (not for API calls - those go through Bravado)
        self._http_client = httpx.AsyncClient(timeout=timeout_seconds)

        # Bravado client (initialized after authentication)
        self._bravado_client: Optional[SwaggerClient] = None
        self._bravado_http_client: Optional[ComdirectBravadoClient] = None

        logger.info("ComdirectClient initialized")

        # Attempt to restore tokens from storage
        self._restore_tokens_from_storage()

    def _generate_request_id(self) -> str:
        """Generate a 9-digit request ID from current timestamp."""
        timestamp = str(int(time.time() * 1000))  # Milliseconds
        request_id = timestamp[-9:]  # Last 9 digits
        logger.debug(f"Request ID: {request_id}")
        return request_id

    def _get_session_id(self) -> str:
        """Get or generate session ID."""
        if not self._session_id:
            self._session_id = str(uuid.uuid4())
            logger.debug(f"Generated session ID: {sanitize_token(self._session_id)}")
        return self._session_id

    def _get_request_info_header(self) -> str:
        """Generate x-http-request-info header value."""
        return json.dumps(
            {
                "clientRequestId": {
                    "sessionId": self._get_session_id(),
                    "requestId": self._generate_request_id(),
                }
            }
        )

    def _get_access_token(self) -> Optional[str]:
        """Get current access token (for Bravado adapter)."""
        return self._access_token

    async def _initialize_bravado_client(self) -> None:
        """Initialize the Bravado client with the Swagger spec."""
        if self._bravado_client is not None:
            return

        logger.info("Initializing Bravado client from Swagger spec")

        # Create custom HTTP client adapter
        self._bravado_http_client = ComdirectBravadoClient(
            get_access_token=self._get_access_token,
            get_session_id=self._get_session_id,
            generate_request_id=self._generate_request_id,
        )

        # Load Swagger spec and create client
        try:
            self._bravado_client = await asyncio.to_thread(
                SwaggerClient.from_url,
                self.swagger_spec_url,
                http_client=self._bravado_http_client,
                config={
                    "validate_requests": False,  # Don't validate requests (Comdirect spec may have issues)
                    "validate_responses": False,  # Don't validate responses
                    "validate_swagger_spec": False,  # Don't validate spec
                    "use_models": True,  # Use models for responses
                },
            )
            logger.info("Bravado client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Bravado client: {e}")
            raise

    @property
    def api(self) -> SwaggerClient:
        """Access the Bravado-generated API client.

        Returns:
            SwaggerClient instance with all API endpoints

        Raises:
            RuntimeError: If client is not authenticated or Bravado client not initialized
        """
        if not self.is_authenticated():
            raise RuntimeError(
                "Client not authenticated. Call authenticate() first before accessing API."
            )
        if self._bravado_client is None:
            raise RuntimeError(
                "Bravado client not initialized. This should not happen - please report a bug."
            )
        return self._bravado_client

    async def authenticate(self) -> None:
        """Perform full authentication flow (Steps 1-5).

        This method:
        1. Obtains OAuth2 password credentials token
        2. Retrieves session status
        3. Creates TAN challenge
        4. Polls for TAN approval (60 second timeout)
        5. Activates session
        6. Exchanges for secondary token with banking scope
        7. Starts automatic token refresh task
        8. Initializes Bravado client

        Raises:
            AuthenticationError: If authentication fails
            TANTimeoutError: If TAN approval times out
            SessionActivationError: If session activation fails
        """
        logger.info("Starting authentication flow")
        logger.info("Reason: Initial authentication required (no valid tokens available)")

        try:
            # Step 1: OAuth2 Password Credentials
            initial_token = await self._step1_password_credentials()

            # Step 2: Get Session UUID
            session_uuid = await self._step2_session_status(initial_token)

            # Step 3: Create TAN Challenge
            tan_challenge_id, tan_type, tan_poll_url = await self._step3_tan_challenge(
                initial_token, session_uuid
            )

            # Step 4: Poll for TAN Approval
            await self._step4_poll_tan_approval(initial_token, tan_poll_url, tan_type)

            # Step 4b: Activate Session
            await self._step4b_activate_session(initial_token, session_uuid, tan_challenge_id)

            # Step 5: Secondary Token Exchange
            await self._step5_secondary_token(initial_token)

            logger.info("Authentication successful")

            # Start automatic token refresh task
            self._start_refresh_task()

            # Initialize Bravado client
            await self._initialize_bravado_client()

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            self._clear_tokens()
            raise

    async def _step1_password_credentials(self) -> str:
        """Step 1: OAuth2 Resource Owner Password Credentials Grant.

        Returns:
            Access token with TWO_FACTOR scope

        Raises:
            AuthenticationError: If credentials are invalid
        """
        logger.debug("Step 1: Obtaining OAuth2 password credentials token")

        try:
            response = await self._http_client.post(
                f"{self.base_url}/oauth/token",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "password",
                    "username": self.username,
                    "password": self._password,
                },
            )

            if response.status_code == 401:
                logger.error("Authentication failed - Invalid credentials")
                raise AuthenticationError("Invalid credentials")

            response.raise_for_status()
            data = response.json()

            access_token = data["access_token"]
            logger.info(f"OAuth2 token obtained: {sanitize_token(access_token)}")
            return cast(str, access_token)

        except httpx.TimeoutException as e:
            logger.error("Network timeout during authentication")
            raise NetworkTimeoutError("Authentication request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during authentication: {e.response.status_code}")
            raise AuthenticationError(f"Authentication failed: {e}") from e

    async def _step2_session_status(self, access_token: str) -> str:
        """Step 2: Retrieve session UUID.

        Args:
            access_token: Access token from Step 1

        Returns:
            Session UUID identifier

        Raises:
            AuthenticationError: If session retrieval fails
        """
        logger.debug("Step 2: Retrieving session status")

        try:
            response = await self._http_client.get(
                f"{self.base_url}/api/session/clients/user/v1/sessions",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "x-http-request-info": self._get_request_info_header(),
                },
            )

            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                raise AuthenticationError("No session data returned")

            session_uuid = data[0]["identifier"]
            logger.info(f"Session UUID retrieved: {sanitize_token(session_uuid)}")
            return cast(str, session_uuid)

        except httpx.TimeoutException as e:
            logger.error("Network timeout during session retrieval")
            raise NetworkTimeoutError("Session retrieval timed out") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during session retrieval: {e.response.status_code}")
            raise AuthenticationError(f"Session retrieval failed: {e}") from e

    async def _step3_tan_challenge(
        self, access_token: str, session_uuid: str
    ) -> tuple[str, str, str]:
        """Step 3: Create TAN challenge.

        Args:
            access_token: Access token from Step 1
            session_uuid: Session UUID from Step 2

        Returns:
            Tuple of (challenge_id, tan_type, poll_url)

        Raises:
            AuthenticationError: If TAN challenge creation fails
        """
        logger.debug("Step 3: Creating TAN challenge")

        try:
            response = await self._http_client.post(
                f"{self.base_url}/api/session/clients/user/v1/sessions/{session_uuid}/validate",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-http-request-info": self._get_request_info_header(),
                },
                json={
                    "identifier": session_uuid,
                    "sessionTanActive": True,
                    "activated2FA": True,
                },
            )

            response.raise_for_status()

            # Parse x-once-authentication-info header
            auth_info_header = response.headers.get("x-once-authentication-info")
            if not auth_info_header:
                raise AuthenticationError("Missing x-once-authentication-info header")

            auth_info = json.loads(auth_info_header)
            challenge_id = auth_info["id"]
            tan_type = auth_info["typ"]
            poll_url = auth_info["link"]["href"]

            logger.info(f"TAN challenge created - Type: {tan_type}, ID: {challenge_id}")
            logger.warning(f"TAN approval required - Method: {tan_type}, Timeout: 60 seconds")

            # Notify that TAN has been requested
            self._invoke_tan_status_callback(
                "requested",
                {"tan_type": tan_type, "challenge_id": challenge_id, "timeout_seconds": 60},
            )

            return challenge_id, tan_type, poll_url

        except httpx.TimeoutException as e:
            logger.error("Network timeout during TAN challenge creation")
            raise NetworkTimeoutError("TAN challenge creation timed out") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during TAN challenge creation: {e.response.status_code}")
            raise AuthenticationError(f"TAN challenge creation failed: {e}") from e

    async def _step4_poll_tan_approval(
        self, access_token: str, poll_url: str, tan_type: str
    ) -> None:
        """Step 4: Poll for TAN approval.

        Args:
            access_token: Access token from Step 1
            poll_url: Polling URL from Step 3
            tan_type: TAN type (P_TAN_PUSH, P_TAN, M_TAN)

        Raises:
            TANTimeoutError: If TAN approval times out after 60 seconds
        """
        logger.info(f"Step 4: Waiting for TAN approval ({tan_type})")

        start_time = time.time()
        timeout = 60  # 60 seconds timeout
        poll_interval = 1  # 1 second between polls

        # Notify that TAN approval is pending
        self._invoke_tan_status_callback(
            "pending", {"tan_type": tan_type, "timeout_seconds": timeout, "elapsed_seconds": 0}
        )

        while time.time() - start_time < timeout:
            await asyncio.sleep(poll_interval)
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            logger.debug(f"Polling TAN status (elapsed: {elapsed}s, remaining: {remaining}s)")

            try:
                response = await self._http_client.get(
                    f"{self.base_url}{poll_url}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "x-http-request-info": self._get_request_info_header(),
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "AUTHENTICATED":
                        logger.info(f"TAN approved via {tan_type}")
                        self._invoke_tan_status_callback(
                            "approved", {"tan_type": tan_type, "elapsed_seconds": elapsed}
                        )
                        return
                    elif status == "PENDING":
                        if elapsed % 10 == 0 and elapsed > 0:  # Log every 10 seconds
                            logger.info(f"Still waiting for TAN approval ({elapsed}s elapsed)")
                            self._invoke_tan_status_callback(
                                "pending",
                                {
                                    "tan_type": tan_type,
                                    "timeout_seconds": timeout,
                                    "elapsed_seconds": elapsed,
                                    "remaining_seconds": remaining,
                                },
                            )
                        logger.debug("TAN approval pending, continuing poll")
                        continue
                    else:
                        logger.error(f"Unexpected TAN status: {status}")
                        raise AuthenticationError(f"Unexpected TAN status: {status}")
                else:
                    logger.warning(f"Poll returned status {response.status_code}, retrying")

            except httpx.TimeoutException:
                logger.warning("Poll request timed out, retrying")
                continue

        # Timeout reached
        logger.error(f"TAN approval timeout - No approval received after {timeout} seconds")
        self._invoke_tan_status_callback(
            "timeout", {"tan_type": tan_type, "timeout_seconds": timeout}
        )
        raise TANTimeoutError("TAN approval timed out after 60 seconds")

    async def _step4b_activate_session(
        self, access_token: str, session_uuid: str, challenge_id: str
    ) -> None:
        """Step 4b: Activate session after TAN approval.

        Args:
            access_token: Access token from Step 1
            session_uuid: Session UUID from Step 2
            challenge_id: TAN challenge ID from Step 3

        Raises:
            SessionActivationError: If session activation fails
        """
        logger.debug("Step 4b: Activating session")

        try:
            response = await self._http_client.patch(
                f"{self.base_url}/api/session/clients/user/v1/sessions/{session_uuid}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-http-request-info": self._get_request_info_header(),
                    "x-once-authentication-info": json.dumps({"id": challenge_id}),
                },
                json={
                    "identifier": session_uuid,
                    "sessionTanActive": True,
                    "activated2FA": True,
                },
            )

            if response.status_code == 422:
                logger.error("Session activation failed - Incorrect header format")
                raise SessionActivationError("Session activation failed: incorrect header format")

            response.raise_for_status()
            logger.info("Session activated successfully")

        except httpx.TimeoutException as e:
            logger.error("Network timeout during session activation")
            raise NetworkTimeoutError("Session activation timed out") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:
                logger.error("Session activation failed - Incorrect header format")
                raise SessionActivationError(f"Session activation failed: {e}") from e
            logger.error(f"HTTP error during session activation: {e.response.status_code}")
            raise SessionActivationError(f"Session activation failed: {e}") from e

    async def _step5_secondary_token(self, initial_token: str) -> None:
        """Step 5: Exchange for secondary token with banking scope.

        Args:
            initial_token: Access token from Step 1

        Raises:
            AuthenticationError: If token exchange fails
        """
        logger.debug("Step 5: Exchanging for secondary token")

        try:
            response = await self._http_client.post(
                f"{self.base_url}/oauth/token",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "cd_secondary",
                    "token": initial_token,
                },
            )

            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            expires_in = data["expires_in"]

            self._token_expiry = utc_now() + timedelta(seconds=expires_in)

            logger.info(
                f"Secondary token obtained: {sanitize_token(self._access_token or '')}, "
                f"expires in {expires_in}s"
            )

            # Save tokens to persistent storage
            self._save_tokens_to_storage()

        except httpx.TimeoutException as e:
            logger.error("Network timeout during token exchange")
            raise NetworkTimeoutError("Token exchange timed out") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during token exchange: {e.response.status_code}")
            raise AuthenticationError(f"Token exchange failed: {e}") from e

    async def refresh_token(self) -> bool:
        """Refresh the access token using the refresh token.

        Returns:
            True if refresh succeeded, False otherwise

        Raises:
            TokenExpiredError: If refresh token is expired
        """
        if not self._refresh_token:
            logger.error("No refresh token available")
            return False

        async with self._refresh_lock:
            logger.debug("Acquiring token refresh lock")
            logger.info("Refreshing token")

            try:
                response = await self._http_client.post(
                    f"{self.base_url}/oauth/token",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                )

                if response.status_code == 401:
                    logger.warning("Token refresh failed - token expired")
                    self._invoke_reauth_callback("token_refresh_failed")
                    return False

                response.raise_for_status()
                data = response.json()

                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]
                expires_in = data["expires_in"]

                self._token_expiry = utc_now() + timedelta(seconds=expires_in)

                logger.info(f"Token refreshed, expires in {expires_in}s")
                logger.debug("Token refresh lock released")

                # Save tokens to persistent storage
                self._save_tokens_to_storage()

                return True

            except httpx.TimeoutException:
                logger.error("Network timeout during token refresh")
                return False
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error during token refresh: {e.response.status_code}")
                return False

    def _start_refresh_task(self) -> None:
        """Start the background token refresh task."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        self._refresh_task = asyncio.create_task(self._token_refresh_loop())
        logger.info("Token refresh task started")

    async def _token_refresh_loop(self) -> None:
        """Background task that automatically refreshes tokens before expiration."""
        while True:
            try:
                if not self._token_expiry:
                    await asyncio.sleep(10)
                    continue

                # Calculate time until refresh needed
                now = utc_now()
                refresh_time = self._token_expiry - timedelta(seconds=self.token_refresh_threshold)
                sleep_duration = (refresh_time - now).total_seconds()

                if sleep_duration > 0:
                    logger.debug(f"Next token refresh in {sleep_duration:.0f}s")
                    await asyncio.sleep(sleep_duration)
                else:
                    # Token is already expired or near expiry, refresh immediately
                    logger.info(
                        f"Token already expired or near expiry (by {-sleep_duration:.0f}s), refreshing immediately"
                    )

                # Refresh token
                logger.info(
                    f"Auto-refreshing token ({self.token_refresh_threshold}s before expiry)"
                )
                success = await self.refresh_token()

                if not success:
                    logger.error("Automatic token refresh failed")
                    self._invoke_reauth_callback("automatic_refresh_failed")
                    break

            except asyncio.CancelledError:
                logger.info("Token refresh task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in token refresh loop: {e}")
                await asyncio.sleep(10)

    def _invoke_reauth_callback(self, reason: str) -> None:
        """Invoke the reauth callback if registered.

        Args:
            reason: Reason for requiring reauth
        """
        self._clear_tokens()

        logger.warning(
            f"Reauthentication required - Reason: {reason}, Action: Call authenticate() again"
        )

        if self.reauth_callback:
            logger.info(f"Invoking reauth callback - Reason: {reason}")
            try:
                self.reauth_callback(reason)
            except Exception as e:
                logger.error(f"Error in reauth callback: {e}")
        else:
            logger.warning("Reauth required but no callback registered")

    def _clear_tokens(self) -> None:
        """Clear all stored tokens and stop refresh task."""
        self._access_token = None
        self._refresh_token = None
        self._token_expiry = None

        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        logger.debug("Tokens cleared")

    def _restore_tokens_from_storage(self) -> None:
        """Restore tokens from persistent storage if available.

        If token storage is configured and valid tokens exist in storage,
        loads them into memory and starts the refresh task.
        """
        try:
            tokens = self._token_storage.load_tokens()
            if tokens:
                access_token, refresh_token, token_expiry = tokens
                self._access_token = access_token
                self._refresh_token = refresh_token
                self._token_expiry = token_expiry
                logger.info(f"Tokens restored from storage (expires: {token_expiry.isoformat()})")
                self._start_refresh_task()
                # Initialize Bravado client if we have valid tokens
                # Note: This creates a task but doesn't await it - it will initialize in background
                if self.is_authenticated():
                    try:
                        # Try to initialize synchronously if we're in an event loop
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self._initialize_bravado_client())
                        else:
                            loop.run_until_complete(self._initialize_bravado_client())
                    except RuntimeError:
                        # No event loop, will initialize on first authenticate() call
                        pass
        except TokenStorageError as e:
            logger.warning(f"Failed to restore tokens from storage: {e}")

    def _save_tokens_to_storage(self) -> None:
        """Save current tokens to persistent storage if configured."""
        if self._access_token and self._refresh_token and self._token_expiry:
            try:
                self._token_storage.save_tokens(
                    self._access_token, self._refresh_token, self._token_expiry
                )
            except TokenStorageError as e:
                logger.warning(f"Failed to save tokens to storage: {e}")

    def _clear_token_storage(self) -> None:
        """Clear token storage (useful for logout)."""
        try:
            self._token_storage.clear_tokens()
        except Exception as e:
            logger.warning(f"Failed to clear token storage: {e}")

    def is_authenticated(self) -> bool:
        """Check if the client is currently authenticated.

        Returns:
            True if authenticated with valid token, False otherwise
        """
        result = self._access_token is not None and self._token_expiry is not None
        logger.debug(
            f"is_authenticated() check: access_token={'present' if self._access_token else 'None'}, "
            f"token_expiry={'present' if self._token_expiry else 'None'}, "
            f"result={result}"
        )
        return result

    def get_token_expiry(self) -> Optional[datetime]:
        """Get the token expiry datetime.

        Returns:
            Token expiry datetime or None if not authenticated
        """
        return self._token_expiry

    def register_reauth_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be invoked when reauth is required.

        Args:
            callback: Function to call with error message when reauth is needed
        """
        self.reauth_callback = callback

    def register_tan_status_callback(
        self, callback: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """Register a callback to be invoked during TAN approval process.

        Args:
            callback: Function to call with (status, data) during TAN approval.
                     Status values: 'requested', 'pending', 'approved', 'timeout'
                     Data dict contains additional info like tan_type, elapsed_seconds, etc.
        """
        self.tan_status_callback = callback

    def _invoke_tan_status_callback(self, status: str, data: dict[str, Any]) -> None:
        """Invoke the TAN status callback if registered.

        Args:
            status: TAN status ('requested', 'pending', 'approved', 'timeout')
            data: Additional data about the TAN process
        """
        if self.tan_status_callback:
            try:
                self.tan_status_callback(status, data)
            except Exception as e:
                logger.error(f"Error in TAN status callback: {e}")
        else:
            logger.debug(f"TAN status update: {status} - {data} (no callback registered)")

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()

        await self._http_client.aclose()
        logger.info("ComdirectClient closed")

    async def __aenter__(self) -> "ComdirectClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

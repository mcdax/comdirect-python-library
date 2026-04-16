"""The public ``ComdirectClient`` facade.

This class holds mutable session state (tokens, session id, HTTP client),
runs the background token-refresh loop, and delegates actual work to the
stateless helpers in :mod:`comdirect_client.http_api` and
:mod:`comdirect_client.auth_flow`. Keep it small and glue-like; any code
that is tempted to grow here should go into one of those modules instead.

Persistent client pattern
-------------------------

Create the client once at application startup and reuse it. The background
refresh task will keep the tokens fresh so you never pay a second TAN
approval inside a single process lifetime::

    async with ComdirectClient(...) as client:
        if not client.is_authenticated():
            await client.authenticate()
        balances = await client.get_account_balances()
        transactions = await client.get_transactions(balances[0].accountId)

If you pass ``token_storage_path``, tokens persist across restarts and the
first ``authenticate()`` after a restart typically only needs a refresh
(no TAN prompt) — provided the refresh token is still valid.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional, Union

import httpx

from comdirect_client import http_api
from comdirect_client.auth_flow import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_TIMEOUT_SECONDS,
    AuthResult,
    TanStatusCallback,
    perform_authentication,
)
from comdirect_client.exceptions import TokenExpiredError
from comdirect_client.models import AccountBalance, Transaction
from comdirect_client.models_brokerage import (
    Depot,
    DepotPosition,
    DepotTransaction,
    Instrument,
    Order,
)
from comdirect_client.models_messages import Document
from comdirect_client.models_reports import ProductBalance
from comdirect_client.token_storage import TokenPersistence, TokenStorageError

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


ReauthCallback = Callable[[str], Union[None, Awaitable[None]]]


class ComdirectClient:
    """Async client for the comdirect banking API.

    See the module docstring for the recommended usage pattern.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        base_url: str = "https://api.comdirect.de",
        reauth_callback: Optional[ReauthCallback] = None,
        tan_status_callback: Optional[TanStatusCallback] = None,
        token_refresh_threshold_seconds: int = 120,
        timeout_seconds: float = 30.0,
        token_storage_path: Optional[str] = None,
        tan_timeout_seconds: int = DEFAULT_POLL_TIMEOUT_SECONDS,
        tan_poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self._password = password  # underscored to reduce accidental log leakage
        self.base_url = base_url.rstrip("/")
        self.reauth_callback = reauth_callback
        self.tan_status_callback = tan_status_callback
        self.token_refresh_threshold = token_refresh_threshold_seconds
        self.timeout_seconds = timeout_seconds
        self.tan_timeout_seconds = tan_timeout_seconds
        self.tan_poll_interval_seconds = tan_poll_interval_seconds

        self._token_storage = TokenPersistence(token_storage_path)

        # Mutable state protected by the refresh lock. The attribute names
        # (``_access_token``, ``_refresh_token``, ``_token_expiry``,
        # ``_session_id``, ``_http_client``) are intentionally stable — tests
        # set them directly to simulate an authenticated client.
        self._session_id: str = str(uuid.uuid4())
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task[None]] = None

        self._http_client = httpx.AsyncClient(timeout=timeout_seconds)
        logger.info("ComdirectClient initialized")

        self._try_restore_tokens()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ComdirectClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Cancel the background refresh task and close the HTTP client."""
        await self._stop_refresh_task()
        await self._http_client.aclose()
        logger.info("ComdirectClient closed")

    # ------------------------------------------------------------------
    # Authentication state
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        """Return True if we have tokens loaded — even expired ones.

        The refresh token may still be valid, so this method is deliberately
        lenient. Use ``get_token_expiry`` to decide whether a refresh is
        imminent.
        """
        return self._access_token is not None and self._token_expiry is not None

    def get_token_expiry(self) -> Optional[datetime]:
        """Return the current access token's expiry as a UTC-aware datetime."""
        return self._token_expiry

    def register_reauth_callback(self, callback: ReauthCallback) -> None:
        """Register (or replace) the reauth callback."""
        self.reauth_callback = callback

    def register_tan_status_callback(self, callback: TanStatusCallback) -> None:
        """Register (or replace) the TAN status callback."""
        self.tan_status_callback = callback

    # ------------------------------------------------------------------
    # Step 1-5 orchestration
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Run the full 5-step auth flow (TAN required)."""
        logger.info("Starting authentication flow")
        try:
            result = await perform_authentication(
                self._http_client,
                self.base_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                username=self.username,
                password=self._password,
                session_id=self._session_id,
                tan_status_callback=self.tan_status_callback,
                tan_timeout_seconds=self.tan_timeout_seconds,
                tan_poll_interval_seconds=self.tan_poll_interval_seconds,
            )
        except Exception:
            self._clear_tokens()
            raise

        self._store_auth_result(result)
        self._start_refresh_task()
        logger.info("Authentication successful")

    async def refresh_token(self) -> bool:
        """Refresh the access + refresh tokens. Returns True on success."""
        if not self._refresh_token:
            logger.error("No refresh token available")
            return False

        async with self._refresh_lock:
            logger.info("Refreshing token")
            data = await http_api.oauth_refresh(
                self._http_client,
                self.base_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
                refresh_token=self._refresh_token,
            )
            if data is None:
                await self._invoke_reauth_callback("token_refresh_failed")
                return False
            self._store_auth_result(
                AuthResult(
                    access_token=data["access_token"],
                    refresh_token=data["refresh_token"],
                    expires_in=int(data["expires_in"]),
                )
            )
            logger.info("Token refreshed, expires in %ds", data["expires_in"])
            return True

    # ------------------------------------------------------------------
    # Banking endpoints
    # ------------------------------------------------------------------

    async def get_account_balances(
        self,
        with_attributes: bool = True,
        without_attributes: Optional[str] = None,
    ) -> list[AccountBalance]:
        """Return all account balances for the logged-in customer."""
        await self._ensure_fresh_token()
        params = _build_without_attr_params(with_attributes, without_attributes)

        response = await http_api.get_account_balances(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            params=params or None,
        )
        balances = [AccountBalance.from_dict(item) for item in response["values"]]
        logger.info("Retrieved %d account balances", len(balances))
        return balances

    async def get_transactions(
        self,
        account_id: str,
        transaction_state: Optional[str] = None,
        transaction_direction: Optional[str] = None,
        with_attributes: bool = True,
        without_attributes: Optional[str] = None,
        min_booking_date: Optional[str] = None,
        max_booking_date: Optional[str] = None,
        paging_count: int = 500,
        paging_first: int = 0,
    ) -> list[Transaction]:
        """Fetch one page of transactions (up to 500) for an account.

        Defaults to the most recent 500 transactions within the API's default
        window. For accounts with more than 500 matching transactions, use
        :meth:`iter_all_booked_transactions` for full pagination.

        New optional parameters (verified via ``COMDIRECT_API.md``):

        * ``min_booking_date`` / ``max_booking_date`` — ISO ``YYYY-MM-DD``
          date range. ``min_booking_date`` also unlocks access to history
          older than the default ~6-month window.
        * ``paging_first`` — zero-based offset. Requires
          ``transaction_state="BOOKED"`` per the API (see pitfall #10 in
          ``COMDIRECT_API.md``).
        * ``paging_count`` — page size, capped server-side at 500.
        """
        await self._ensure_fresh_token()

        params: dict[str, str] = {"paging-count": str(paging_count)}
        if paging_first:
            params["paging-first"] = str(paging_first)
        if transaction_state:
            params["transactionState"] = transaction_state
        if transaction_direction:
            params["transactionDirection"] = transaction_direction
        if min_booking_date:
            params["min-bookingDate"] = min_booking_date
        if max_booking_date:
            params["max-bookingDate"] = max_booking_date
        if not with_attributes:
            params["without-attr"] = "account"
        if without_attributes:
            if "without-attr" in params:
                params["without-attr"] = f"{params['without-attr']},{without_attributes}"
            else:
                params["without-attr"] = without_attributes

        response = await http_api.get_transactions(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            account_id=account_id,
            params=params,
        )
        transactions = [Transaction.from_dict(item) for item in response["values"]]
        logger.info(
            "Retrieved %d transactions for account %s",
            len(transactions),
            account_id[:8],
        )
        return transactions

    async def fetch_all_booked_transactions(
        self,
        account_id: str,
        min_booking_date: str = "2000-01-01",
        transaction_direction: Optional[str] = None,
    ) -> list[Transaction]:
        """Walk every booked transaction on an account, bypassing the 500 cap.

        Implements the strategy documented in ``COMDIRECT_API.md``
        §"Pagination rules": force ``transactionState=BOOKED``, widen
        ``min-bookingDate`` to unlock historical data, then step through
        ``paging-first`` in 500-sized windows until a short page is returned.
        """
        all_transactions: list[Transaction] = []
        offset = 0
        while True:
            page = await self.get_transactions(
                account_id,
                transaction_state="BOOKED",
                transaction_direction=transaction_direction,
                min_booking_date=min_booking_date,
                paging_count=500,
                paging_first=offset,
            )
            all_transactions.extend(page)
            if len(page) < 500:
                break
            offset += 500
        return all_transactions

    # ------------------------------------------------------------------
    # Brokerage endpoints (read-only)
    # ------------------------------------------------------------------

    async def get_depots(self) -> list[Depot]:
        """Return the customer's depots (securities accounts)."""
        await self._ensure_fresh_token()
        response = await http_api.get_depots(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
        )
        return [Depot.from_dict(item) for item in response["values"]]

    async def get_depot_positions(
        self,
        depot_id: str,
        with_instrument: bool = True,
        without_attributes: Optional[str] = None,
    ) -> list[DepotPosition]:
        """Return the holdings inside a specific depot.

        ``with_instrument=True`` includes the nested ``instrument`` object.
        """
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        if with_instrument:
            params["with-attr"] = "instrument"
        if without_attributes:
            params["without-attr"] = without_attributes
        response = await http_api.get_depot_positions(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            depot_id=depot_id,
            params=params or None,
        )
        return [DepotPosition.from_dict(item) for item in response["values"]]

    async def get_depot_position(
        self,
        depot_id: str,
        position_id: str,
        with_instrument: bool = True,
    ) -> DepotPosition:
        """Return one specific holding inside a depot."""
        await self._ensure_fresh_token()
        params: dict[str, str] = {"with-attr": "instrument"} if with_instrument else {}
        response = await http_api.get_depot_position(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            depot_id=depot_id,
            position_id=position_id,
            params=params or None,
        )
        return DepotPosition.from_dict(response)

    async def get_depot_transactions(
        self,
        depot_id: str,
        wkn: Optional[str] = None,
        isin: Optional[str] = None,
        instrument_id: Optional[str] = None,
        booking_status: Optional[str] = None,  # BOOKED / NOTBOOKED / BOTH
        transaction_direction: Optional[str] = None,  # IN / OUT
        transaction_type: Optional[str] = None,  # BUY / SELL / TRANSFER_IN / TRANSFER_OUT
        min_booking_date: Optional[str] = None,
        max_booking_date: Optional[str] = None,
        min_transaction_value: Optional[str] = None,
        max_transaction_value: Optional[str] = None,
    ) -> list[DepotTransaction]:
        """Return buy/sell/transfer history for a depot.

        ``min_booking_date`` / ``max_booking_date`` accept either ISO dates
        (``YYYY-MM-DD``) or negative offsets (``-10d``) per the API spec.
        """
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        for key, value in [
            ("WKN", wkn),
            ("ISIN", isin),
            ("instrumentId", instrument_id),
            ("bookingStatus", booking_status),
            ("transactionDirection", transaction_direction),
            ("transactionType", transaction_type),
            ("min-bookingDate", min_booking_date),
            ("max-bookingDate", max_booking_date),
            ("min-transactionValue", min_transaction_value),
            ("max-transactionValue", max_transaction_value),
        ]:
            if value is not None:
                params[key] = value
        response = await http_api.get_depot_transactions(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            depot_id=depot_id,
            params=params or None,
        )
        return [DepotTransaction.from_dict(item) for item in response["values"]]

    async def get_depot_orders(
        self,
        depot_id: str,
        order_status: Optional[str] = None,
        venue_id: Optional[str] = None,
        order_type: Optional[str] = None,
        side: Optional[str] = None,
        isin: Optional[str] = None,
        wkn: Optional[str] = None,
        instrument_id: Optional[str] = None,
        min_creation_timestamp: Optional[str] = None,
        max_creation_timestamp: Optional[str] = None,
    ) -> list[Order]:
        """Return the order book for a depot.

        ``min_creation_timestamp`` / ``max_creation_timestamp`` use the
        comma-second UTC format from the Swagger:
        ``YYYY-MM-DDThh:mm:ss,ff``.
        """
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        for key, value in [
            ("orderStatus", order_status),
            ("venueId", venue_id),
            ("orderType", order_type),
            ("side", side),
            ("ISIN", isin),
            ("WKN", wkn),
            ("instrumentId", instrument_id),
            ("min-creationTimeStamp", min_creation_timestamp),
            ("max-creationTimeStamp", max_creation_timestamp),
        ]:
            if value is not None:
                params[key] = value
        response = await http_api.get_depot_orders(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            depot_id=depot_id,
            params=params or None,
        )
        return [Order.from_dict(item) for item in response["values"]]

    async def get_order(self, order_id: str) -> Order:
        """Return one order, including all executions."""
        await self._ensure_fresh_token()
        response = await http_api.get_order(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            order_id=order_id,
        )
        return Order.from_dict(response)

    async def get_instrument(
        self,
        instrument_id: str,
        with_attributes: Optional[str] = None,
    ) -> Instrument:
        """Look up an instrument by WKN, ISIN, mnemonic or UUID."""
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        if with_attributes:
            params["with-attr"] = with_attributes
        response = await http_api.get_instrument(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            instrument_id=instrument_id,
            params=params or None,
        )
        return Instrument.from_dict(response["values"][0])

    # ------------------------------------------------------------------
    # Messages / documents
    # ------------------------------------------------------------------

    async def get_documents(
        self,
        min_document_date: Optional[str] = None,
        max_document_date: Optional[str] = None,
        paging_count: Optional[int] = None,
        paging_first: Optional[int] = None,
    ) -> list[Document]:
        """List documents in the customer's PostBox."""
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        if min_document_date:
            params["min-documentDate"] = min_document_date
        if max_document_date:
            params["max-documentDate"] = max_document_date
        if paging_count is not None:
            params["paging-count"] = str(paging_count)
        if paging_first is not None:
            params["paging-first"] = str(paging_first)
        response = await http_api.get_documents(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            params=params or None,
        )
        return [Document.from_dict(item) for item in response["values"]]

    async def get_document_content(
        self,
        document_id: str,
        predocument: bool = False,
        accept: str = "application/pdf, text/html",
    ) -> tuple[bytes, str]:
        """Download a document as raw bytes.

        Returns ``(content, content_type)`` where ``content_type`` is the
        value of the response's ``Content-Type`` header (``application/pdf``
        or ``text/html``). See COMDIRECT_API.md §11 for why you cannot reuse
        the library's default JSON ``Accept`` header here.
        """
        await self._ensure_fresh_token()
        return await http_api.get_document_content(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            document_id=document_id,
            accept=accept,
            predocument=predocument,
        )

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    async def get_all_balances(
        self,
        product_type: Optional[str] = None,
        client_connection_type: Optional[str] = None,
        target_client_id: Optional[str] = None,
        without_attributes: Optional[str] = None,
    ) -> list[ProductBalance]:
        """Consolidated balance view across accounts, depots, cards, loans,
        and fixed-term savings.

        Filter with ``product_type`` (e.g. ``ACCOUNT``, ``DEPOT``, ``CARD``,
        ``INSTALLMENT_LOAN``, ``FIXED_TERM_SAVINGS``),
        ``client_connection_type`` or ``target_client_id``. The per-entry
        ``balance`` field is returned as a raw dict because its shape
        depends on ``productType`` — see ``ProductBalance`` for details.
        """
        await self._ensure_fresh_token()
        params: dict[str, str] = {}
        if product_type:
            params["productType"] = product_type
        if client_connection_type:
            params["clientConnectionType"] = client_connection_type
        if target_client_id:
            params["targetClientId"] = target_client_id
        if without_attributes:
            params["without-attr"] = without_attributes
        response = await http_api.get_all_balances(
            self._http_client,
            self.base_url,
            access_token=self._require_access_token(),
            session_id=self._session_id,
            params=params or None,
        )
        return [ProductBalance.from_dict(item) for item in response["values"]]

    # ------------------------------------------------------------------
    # Token management helpers
    # ------------------------------------------------------------------

    def _store_auth_result(self, result: AuthResult) -> None:
        self._access_token = result.access_token
        self._refresh_token = result.refresh_token
        self._token_expiry = _utc_now() + timedelta(seconds=result.expires_in)
        self._save_tokens_to_storage()

    def _require_access_token(self) -> str:
        """Return the access token, raising if the client is not authenticated.

        The banking endpoints call this after ``_ensure_fresh_token`` so they
        can safely dereference ``self._access_token``.
        """
        if self._access_token is None:
            raise TokenExpiredError("Not authenticated")
        return self._access_token

    async def _ensure_fresh_token(self) -> None:
        """Refresh the token if it is about to expire (or already expired).

        Uses the same threshold as the background task so a call that races
        with expiry doesn't have to eat a 401 first.
        """
        if not self.is_authenticated():
            raise TokenExpiredError("Not authenticated")
        assert self._token_expiry is not None
        threshold = self._token_expiry - timedelta(seconds=self.token_refresh_threshold)
        if _utc_now() >= threshold:
            logger.debug("Token near expiry — refreshing before request")
            if not await self.refresh_token():
                raise TokenExpiredError("Token expired and refresh failed")

    def _clear_tokens(self) -> None:
        """Drop tokens from memory AND persistent storage."""
        self._access_token = None
        self._refresh_token = None
        self._token_expiry = None
        self._token_storage.clear_tokens()
        logger.debug("Tokens cleared (memory + storage)")

    def _save_tokens_to_storage(self) -> None:
        if self._access_token and self._refresh_token and self._token_expiry:
            try:
                self._token_storage.save_tokens(
                    self._access_token, self._refresh_token, self._token_expiry
                )
            except TokenStorageError as e:
                logger.warning("Failed to save tokens to storage: %s", e)

    def _try_restore_tokens(self) -> None:
        """Best-effort restore on construction.

        The background refresh task is NOT started here — it needs a running
        event loop, and the client is usually constructed synchronously
        before ``asyncio.run``. The task starts on the first
        ``authenticate`` / ``refresh_token`` call instead.
        """
        try:
            tokens = self._token_storage.load_tokens()
        except TokenStorageError as e:
            logger.warning("Failed to restore tokens from storage: %s", e)
            return
        if tokens:
            self._access_token, self._refresh_token, self._token_expiry = tokens
            logger.info(
                "Tokens restored from storage (expires: %s)",
                self._token_expiry.isoformat(),
            )

    # ------------------------------------------------------------------
    # Background refresh loop
    # ------------------------------------------------------------------

    def _start_refresh_task(self) -> None:
        if self._refresh_task and not self._refresh_task.done():
            return
        try:
            self._refresh_task = asyncio.create_task(self._refresh_loop())
        except RuntimeError:
            # No running event loop — refresh will happen lazily via
            # _ensure_fresh_token() on the next API call.
            logger.debug("No running event loop; skipping background refresh task")
            return
        logger.info("Token refresh task started")

    async def _stop_refresh_task(self) -> None:
        task = self._refresh_task
        self._refresh_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            logger.debug("Token refresh task cancelled")

    async def _refresh_loop(self) -> None:
        """Sleep until the token is close to expiry, refresh, repeat."""
        try:
            while True:
                if self._token_expiry is None:
                    await asyncio.sleep(10)
                    continue
                sleep_seconds = (
                    self._token_expiry
                    - _utc_now()
                    - timedelta(seconds=self.token_refresh_threshold)
                ).total_seconds()
                if sleep_seconds > 0:
                    logger.debug("Next token refresh in %.0fs", sleep_seconds)
                    await asyncio.sleep(sleep_seconds)
                if not await self.refresh_token():
                    logger.error("Automatic token refresh failed; stopping loop")
                    await self._invoke_reauth_callback("automatic_refresh_failed")
                    return
        except asyncio.CancelledError:
            logger.info("Token refresh task cancelled")
            raise

    # ------------------------------------------------------------------
    # Reauth callback
    # ------------------------------------------------------------------

    async def _invoke_reauth_callback(self, reason: str) -> None:
        """Clear tokens and call the user-supplied reauth callback.

        Supports both sync and async callbacks.
        """
        self._clear_tokens()
        logger.warning("Reauthentication required — reason: %s", reason)
        if self.reauth_callback is None:
            logger.warning("Reauth required but no callback registered")
            return
        try:
            result = self.reauth_callback(reason)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:  # noqa: BLE001 — user code shouldn't break the client
            logger.error("Error in reauth callback: %s", e)


def _build_without_attr_params(
    with_attributes: bool, without_attributes: Optional[str]
) -> dict[str, str]:
    params: dict[str, str] = {}
    if not with_attributes:
        params["without-attr"] = "account"
    if without_attributes:
        if "without-attr" in params:
            params["without-attr"] = f"{params['without-attr']},{without_attributes}"
        else:
            params["without-attr"] = without_attributes
    return params

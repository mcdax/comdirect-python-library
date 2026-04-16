"""Low-level HTTP wrappers for each comdirect API endpoint we use.

Each function in this module does exactly one HTTP call. They take an
``httpx.AsyncClient``, a base URL, an access token, a session id and the
endpoint-specific arguments. They return the parsed JSON body (or a tuple
with additional data like response headers where needed) and raise the
appropriate ``ComdirectAPIError`` subclass on HTTP errors.

These functions are deliberately stateless: they do not know about token
refresh, background tasks or storage. That logic lives in
:mod:`comdirect_client.client`. Keeping the HTTP layer dumb makes it trivial
to mock and reason about.
"""

import json
import logging
import time
from typing import Any, Optional

import httpx

from comdirect_client.exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    NetworkTimeoutError,
    ServerError,
    SessionActivationError,
    ValidationError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request-info header helpers
# ---------------------------------------------------------------------------


def make_request_id() -> str:
    """Return a 9-digit request id (last 9 digits of the current millis).

    Comdirect requires exactly 9 digits. Uniqueness is not strictly
    required by the server — the header is used for idempotency and
    correlation on comdirect's side.
    """
    return str(int(time.time() * 1000))[-9:]


def request_info_header(session_id: str) -> str:
    """Build the ``x-http-request-info`` header value.

    Keeps the same ``sessionId`` for the lifetime of the client; only the
    ``requestId`` changes per call.
    """
    return json.dumps(
        {
            "clientRequestId": {
                "sessionId": session_id,
                "requestId": make_request_id(),
            }
        }
    )


def _bearer_headers(access_token: str, session_id: str) -> dict[str, str]:
    """Standard auth headers for every authenticated API call."""
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "x-http-request-info": request_info_header(session_id),
    }


# ---------------------------------------------------------------------------
# OAuth2 token endpoint
# ---------------------------------------------------------------------------


async def oauth_password(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Step 1: OAuth2 Resource Owner Password Credentials.

    Returns the full token response dict with ``access_token``, ``expires_in``
    and friends. Scope is ``TWO_FACTOR`` on success.
    """
    try:
        response = await http.post(
            f"{base_url}/oauth/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "password",
                "username": username,
                "password": password,
            },
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Authentication request timed out") from e

    if response.status_code == 401:
        raise AuthenticationError("Invalid credentials")
    if response.status_code >= 400:
        raise AuthenticationError(f"OAuth password flow failed: {response.status_code}")
    return response.json()  # type: ignore[no-any-return]


async def oauth_secondary(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    client_id: str,
    client_secret: str,
    initial_access_token: str,
) -> dict[str, Any]:
    """Step 5: Exchange a TAN-activated token for one with banking scope."""
    try:
        response = await http.post(
            f"{base_url}/oauth/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "cd_secondary",
                "token": initial_access_token,
            },
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Secondary token exchange timed out") from e

    if response.status_code >= 400:
        raise AuthenticationError(f"Secondary token exchange failed: {response.status_code}")
    return response.json()  # type: ignore[no-any-return]


async def oauth_refresh(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Optional[dict[str, Any]]:
    """Step 6: Refresh the access + refresh tokens.

    Returns the new token dict on success, or ``None`` on any HTTP error —
    the caller decides whether to reauth from scratch.
    """
    try:
        response = await http.post(
            f"{base_url}/oauth/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    except httpx.TimeoutException:
        logger.error("Network timeout during token refresh")
        return None

    if response.status_code >= 400:
        logger.warning("Token refresh failed with status %d", response.status_code)
        return None
    return response.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Session / TAN endpoints
# ---------------------------------------------------------------------------


async def get_session_status(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
) -> str:
    """Step 2: Return the session UUID (``identifier`` field)."""
    try:
        response = await http.get(
            f"{base_url}/api/session/clients/user/v1/sessions",
            headers=_bearer_headers(access_token, session_id),
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Session status request timed out") from e

    if response.status_code >= 400:
        raise AuthenticationError(f"Session status request failed: {response.status_code}")
    data = response.json()
    if not isinstance(data, list) or not data:
        raise AuthenticationError("No session data returned")
    return str(data[0]["identifier"])


async def create_tan_challenge(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    session_uuid: str,
) -> dict[str, Any]:
    """Step 3: Trigger a TAN challenge.

    Returns the parsed ``x-once-authentication-info`` header dict which
    contains ``id``, ``typ``, optional ``link.href`` (for push-TAN
    polling), optional ``challenge`` (Base64 PNG for photo-TAN), and
    ``availableTypes``.
    """
    try:
        response = await http.post(
            f"{base_url}/api/session/clients/user/v1/sessions/{session_uuid}/validate",
            headers={
                **_bearer_headers(access_token, session_id),
                "Content-Type": "application/json",
            },
            json={
                "identifier": session_uuid,
                "sessionTanActive": True,
                "activated2FA": True,
            },
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("TAN challenge request timed out") from e

    if response.status_code >= 400:
        raise AuthenticationError(f"TAN challenge creation failed: {response.status_code}")

    header = response.headers.get("x-once-authentication-info")
    if not header:
        raise AuthenticationError("Missing x-once-authentication-info header")
    return json.loads(header)  # type: ignore[no-any-return]


async def poll_tan_status(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    poll_url: str,
) -> Optional[str]:
    """Poll the push-TAN status endpoint once.

    Returns the ``status`` string (``PENDING`` or ``AUTHENTICATED``) or
    ``None`` on a non-200 response so the caller can retry.
    """
    try:
        response = await http.get(
            f"{base_url}{poll_url}",
            headers=_bearer_headers(access_token, session_id),
        )
    except httpx.TimeoutException:
        return None

    if response.status_code != 200:
        return None
    status = response.json().get("status")
    return str(status) if status is not None else None


async def activate_session(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    session_uuid: str,
    tan_challenge_id: str,
) -> None:
    """Step 4b: Finalise TAN activation via PATCH on the session."""
    try:
        response = await http.patch(
            f"{base_url}/api/session/clients/user/v1/sessions/{session_uuid}",
            headers={
                **_bearer_headers(access_token, session_id),
                "Content-Type": "application/json",
                "x-once-authentication-info": json.dumps({"id": tan_challenge_id}),
            },
            json={
                "identifier": session_uuid,
                "sessionTanActive": True,
                "activated2FA": True,
            },
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Session activation timed out") from e

    if response.status_code >= 400:
        raise SessionActivationError(f"Session activation failed: {response.status_code}")


# ---------------------------------------------------------------------------
# Banking endpoints
# ---------------------------------------------------------------------------


async def get_account_balances(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    params: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """``GET /api/banking/clients/user/v2/accounts/balances``.

    Returns the raw response dict with a ``values`` array of account
    balances. See :class:`~comdirect_client.models.AccountBalance`.
    """
    try:
        response = await http.get(
            f"{base_url}/api/banking/clients/user/v2/accounts/balances",
            headers=_bearer_headers(access_token, session_id),
            params=params,
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Account balances request timed out") from e

    _raise_for_banking_status(response, endpoint="account balances")
    return response.json()  # type: ignore[no-any-return]


async def get_transactions(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    account_id: str,
    params: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """``GET /api/banking/v1/accounts/{accountId}/transactions``.

    Returns the raw response dict with a ``values`` array of transactions
    and a ``paging`` object containing ``index`` and ``matches``.
    """
    try:
        response = await http.get(
            f"{base_url}/api/banking/v1/accounts/{account_id}/transactions",
            headers=_bearer_headers(access_token, session_id),
            params=params,
        )
    except httpx.TimeoutException as e:
        raise NetworkTimeoutError("Transactions request timed out") from e

    _raise_for_banking_status(response, endpoint="transactions", account_id=account_id)
    return response.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Response / error helpers
# ---------------------------------------------------------------------------


AUTH_STATUS_CODES = {401}


def _raise_for_banking_status(
    response: httpx.Response,
    *,
    endpoint: str,
    account_id: Optional[str] = None,
) -> None:
    """Map HTTP status codes from banking endpoints to library exceptions.

    Passes through ``401`` — the caller handles refresh + retry. Raises the
    appropriate exception for any other 4xx/5xx response.
    """
    status = response.status_code
    if status < 400 or status in AUTH_STATUS_CODES:
        return
    if status == 404:
        if account_id is not None:
            raise AccountNotFoundError(f"Account {account_id} not found")
        raise AccountNotFoundError(f"Resource not found for {endpoint}")
    if status == 422:
        raise ValidationError(f"Invalid request parameters for {endpoint}")
    if status >= 500:
        raise ServerError(f"API server returned {status} for {endpoint}")
    # Any other 4xx is treated as a generic validation error.
    raise ValidationError(f"Unexpected {status} response for {endpoint}")

"""The 5-step comdirect authentication flow as a plain async function.

This module knows nothing about ``ComdirectClient``, background tasks or
token storage. It takes a configured ``httpx.AsyncClient`` plus credentials,
walks steps 1-5 from ``COMDIRECT_API.md`` and returns the final token set.

The only "smart" part is push-TAN polling: if the TAN type is
``P_TAN_PUSH``, we poll the URL from ``x-once-authentication-info.link.href``
every second until the status is ``AUTHENTICATED`` or 60 seconds elapse.
Other TAN types (``P_TAN``, ``M_TAN``) require user interaction that is not
supported here — they raise ``AuthenticationError`` with a clear message.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from comdirect_client import http_api
from comdirect_client.exceptions import AuthenticationError, TANTimeoutError

logger = logging.getLogger(__name__)

PUSH_TAN = "P_TAN_PUSH"
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 60


@dataclass
class AuthResult:
    """Outcome of a successful authentication flow."""

    access_token: str
    refresh_token: str
    expires_in: int  # seconds until the access token expires


TanStatusCallback = Callable[[str, dict[str, Any]], None]


async def perform_authentication(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    session_id: str,
    tan_status_callback: Optional[TanStatusCallback] = None,
) -> AuthResult:
    """Run the full 5-step auth flow and return the banking-scope tokens.

    Raises ``AuthenticationError`` for unrecoverable failures (bad
    credentials, unsupported TAN type, missing challenge headers),
    ``TANTimeoutError`` if the user does not approve the push-TAN within
    60 seconds, and the usual network exceptions from ``httpx``.
    """

    # Step 1 — password grant → short-lived TWO_FACTOR token.
    step1 = await http_api.oauth_password(
        http,
        base_url,
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
    )
    initial_access_token = step1["access_token"]
    logger.debug("Step 1 OK: obtained TWO_FACTOR token")

    # Step 2 — fetch session UUID.
    session_uuid = await http_api.get_session_status(
        http,
        base_url,
        access_token=initial_access_token,
        session_id=session_id,
    )
    logger.debug("Step 2 OK: session UUID retrieved")

    # Step 3 — trigger TAN challenge.
    challenge = await http_api.create_tan_challenge(
        http,
        base_url,
        access_token=initial_access_token,
        session_id=session_id,
        session_uuid=session_uuid,
    )
    tan_type = challenge.get("typ")
    challenge_id = challenge.get("id")
    if not isinstance(challenge_id, str) or not isinstance(tan_type, str):
        raise AuthenticationError("TAN challenge response missing 'id' or 'typ'")
    logger.info("Step 3 OK: TAN challenge created (type=%s, id=%s)", tan_type, challenge_id)

    _notify_tan_status(
        tan_status_callback,
        "requested",
        {
            "tan_type": tan_type,
            "challenge_id": challenge_id,
            "timeout_seconds": POLL_TIMEOUT_SECONDS,
        },
    )

    # Step 4 — wait for user approval. Only push-TAN is supported headlessly.
    if tan_type != PUSH_TAN:
        raise AuthenticationError(
            f"Unsupported TAN type {tan_type!r}. This library currently "
            f"handles {PUSH_TAN} only. Configure push-TAN in the comdirect "
            f"photoTAN app or extend the client to prompt the user for a TAN."
        )
    link = challenge.get("link") or {}
    poll_url = link.get("href") if isinstance(link, dict) else None
    if not poll_url:
        raise AuthenticationError(
            "Push-TAN challenge has no polling link — cannot wait for approval"
        )

    await _wait_for_push_tan(
        http,
        base_url,
        access_token=initial_access_token,
        session_id=session_id,
        poll_url=poll_url,
        tan_type=tan_type,
        tan_status_callback=tan_status_callback,
    )

    # Step 4b — finalise session activation.
    await http_api.activate_session(
        http,
        base_url,
        access_token=initial_access_token,
        session_id=session_id,
        session_uuid=session_uuid,
        tan_challenge_id=challenge_id,
    )
    logger.debug("Step 4b OK: session activated")

    # Step 5 — exchange for banking-scope token.
    step5 = await http_api.oauth_secondary(
        http,
        base_url,
        client_id=client_id,
        client_secret=client_secret,
        initial_access_token=initial_access_token,
    )
    logger.debug("Step 5 OK: secondary token obtained")

    return AuthResult(
        access_token=step5["access_token"],
        refresh_token=step5["refresh_token"],
        expires_in=int(step5["expires_in"]),
    )


async def _wait_for_push_tan(
    http: httpx.AsyncClient,
    base_url: str,
    *,
    access_token: str,
    session_id: str,
    poll_url: str,
    tan_type: str,
    tan_status_callback: Optional[TanStatusCallback],
) -> None:
    """Poll the push-TAN status endpoint until approved or timeout."""
    logger.info("Waiting for push-TAN approval (timeout: %ds)", POLL_TIMEOUT_SECONDS)
    _notify_tan_status(
        tan_status_callback,
        "pending",
        {
            "tan_type": tan_type,
            "timeout_seconds": POLL_TIMEOUT_SECONDS,
            "elapsed_seconds": 0,
        },
    )

    start = time.monotonic()
    while time.monotonic() - start < POLL_TIMEOUT_SECONDS:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed = int(time.monotonic() - start)
        status = await http_api.poll_tan_status(
            http,
            base_url,
            access_token=access_token,
            session_id=session_id,
            poll_url=poll_url,
        )
        if status == "AUTHENTICATED":
            _notify_tan_status(
                tan_status_callback,
                "approved",
                {"tan_type": tan_type, "elapsed_seconds": elapsed},
            )
            return
        if status is None or status == "PENDING":
            if elapsed and elapsed % 10 == 0:
                logger.info("Still waiting for TAN approval (%ds elapsed)", elapsed)
                _notify_tan_status(
                    tan_status_callback,
                    "pending",
                    {
                        "tan_type": tan_type,
                        "timeout_seconds": POLL_TIMEOUT_SECONDS,
                        "elapsed_seconds": elapsed,
                        "remaining_seconds": POLL_TIMEOUT_SECONDS - elapsed,
                    },
                )
            continue
        raise AuthenticationError(f"Unexpected TAN status: {status}")

    _notify_tan_status(
        tan_status_callback,
        "timeout",
        {"tan_type": tan_type, "timeout_seconds": POLL_TIMEOUT_SECONDS},
    )
    raise TANTimeoutError(f"TAN approval timed out after {POLL_TIMEOUT_SECONDS} seconds")


def _notify_tan_status(
    callback: Optional[TanStatusCallback],
    status: str,
    data: dict[str, Any],
) -> None:
    """Invoke the TAN status callback if set; swallow any callback errors."""
    if callback is None:
        return
    try:
        callback(status, data)
    except Exception as e:  # noqa: BLE001 — don't let user code break auth
        logger.error("Error in TAN status callback: %s", e)

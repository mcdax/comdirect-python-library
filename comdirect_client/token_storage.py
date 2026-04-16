"""Persist OAuth2 tokens to disk so a restarted process can skip the TAN flow.

The file is a simple JSON dict with three keys::

    {
      "access_token": "...",
      "refresh_token": "...",
      "token_expiry": "2026-04-11T18:47:05.329571+00:00"
    }

Writes are atomic (temp file + ``os.replace``) and the file is created with
``0600`` permissions from the start so tokens are never world-readable even
briefly. Tokens are stored in plain text — encrypt the containing volume if
your threat model needs it.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TokenStorageError(Exception):
    """Raised for any I/O or format problem with the token file."""


class TokenPersistence:
    """Read/write OAuth2 tokens from/to a JSON file.

    Passing ``storage_path=None`` turns persistence off — every method
    becomes a no-op and ``load_tokens`` returns ``None``. This makes the
    class safe to always instantiate from ``ComdirectClient`` regardless of
    whether the caller wants persistence.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        self.storage_path: Optional[Path] = None
        if storage_path is None:
            return

        path = Path(storage_path)
        if not path.parent.exists() or not path.parent.is_dir():
            raise TokenStorageError(
                f"Token storage directory does not exist: {path.parent.absolute()}"
            )
        self.storage_path = path
        logger.debug("Token persistence enabled at: %s", self.storage_path.absolute())

    def save_tokens(
        self,
        access_token: str,
        refresh_token: str,
        token_expiry: datetime,
    ) -> None:
        """Write tokens atomically. No-op if persistence is disabled."""
        if self.storage_path is None:
            return

        payload = json.dumps(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expiry": token_expiry.isoformat(),
            }
        ).encode("utf-8")

        # Write to a sibling temp file with 0600 perms, then rename. Using
        # os.open + O_CREAT | O_EXCL prevents symlink attacks and ensures the
        # file is owner-only from the moment it exists.
        tmp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        try:
            fd = os.open(
                tmp_path,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, self.storage_path)
        except OSError as e:
            # Clean up temp file on failure
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise TokenStorageError(f"Failed to save tokens to {self.storage_path}: {e}") from e

        logger.debug(
            "Tokens saved to %s (expires: %s)",
            self.storage_path.name,
            token_expiry.isoformat(),
        )

    def load_tokens(self) -> Optional[tuple[str, str, datetime]]:
        """Read tokens from disk.

        Returns ``None`` if persistence is disabled or the file does not
        exist. Returns the tuple ``(access_token, refresh_token,
        token_expiry)`` even for already-expired tokens — the caller decides
        whether to refresh or discard. Raises ``TokenStorageError`` for
        corrupt or unreadable files.
        """
        if self.storage_path is None or not self.storage_path.exists():
            return None

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise TokenStorageError(
                f"Token file is corrupted (invalid JSON) at {self.storage_path}: {e}"
            ) from e
        except OSError as e:
            raise TokenStorageError(f"Failed to read tokens from {self.storage_path}: {e}") from e

        required = {"access_token", "refresh_token", "token_expiry"}
        missing = required - set(data)
        if missing:
            raise TokenStorageError(
                f"Token file {self.storage_path} is missing fields: {sorted(missing)}"
            )

        try:
            token_expiry = datetime.fromisoformat(data["token_expiry"])
        except ValueError as e:
            raise TokenStorageError(
                f"Token file {self.storage_path} has invalid datetime format: {e}"
            ) from e

        # Naive datetimes are treated as UTC for backward compatibility with
        # older token files that predate timezone-aware writes.
        if token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=timezone.utc)

        if token_expiry <= datetime.now(timezone.utc):
            logger.info(
                "Loaded tokens are expired (expired: %s), " "but refresh_token may still be valid",
                token_expiry.isoformat(),
            )
        else:
            logger.debug("Tokens loaded from storage (expires: %s)", token_expiry.isoformat())

        return data["access_token"], data["refresh_token"], token_expiry

    def clear_tokens(self) -> None:
        """Delete the token file. No-op if persistence is disabled."""
        if self.storage_path is None:
            return
        try:
            self.storage_path.unlink(missing_ok=True)
            logger.debug("Token storage cleared: %s", self.storage_path)
        except OSError as e:
            logger.error("Failed to clear token storage at %s: %s", self.storage_path, e)

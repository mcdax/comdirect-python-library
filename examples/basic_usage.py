#!/usr/bin/env python3
"""Basic usage example for the Comdirect API client.

This example demonstrates:
1. Client initialization with token persistence
2. Authentication with TAN challenge (only needed on first run)
3. Fetching account balances
4. Fetching ALL transactions across ALL accounts
5. Automatic token refresh
6. Reauth callback handling
7. Exporting all transactions to JSON file
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from comdirect_client.client import ComdirectClient


# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def write_transactions_to_json(transactions, filename="transactions.json"):
    """Write transactions to a JSON file.

    Args:
        transactions: List of transaction objects
        filename: Output JSON filename
    """
    output_path = Path(filename)

    # Convert transactions to JSON-serializable format
    transactions_data = []
    for tx in transactions:
        tx_dict = {
            "bookingStatus": tx.bookingStatus,
            "reference": tx.reference,
            "valutaDate": str(tx.valutaDate) if tx.valutaDate else None,
            "newTransaction": tx.newTransaction,
            "bookingDate": str(tx.bookingDate) if tx.bookingDate else None,
            "remittanceLines": tx.remittance_lines,  # Parsed lines with markers stripped
            "amount": {
                "value": str(tx.amount.value) if tx.amount else None,
                "unit": tx.amount.unit if tx.amount else None,
            },
            "transactionType": tx.transactionType.text if tx.transactionType else None,
            "remitter": tx.remitter,
            "debtor": tx.debtor,
            "creditor": tx.creditor,
        }
        transactions_data.append(tx_dict)

    # Write to JSON file
    with open(output_path, "w") as f:
        json.dump(transactions_data, f, indent=2, default=str)

    logger.info(f"✅ Wrote {len(transactions_data)} transactions to {output_path}")


def reauth_callback(reason: str):
    """Callback invoked when reauthentication is required.

    Args:
        reason: Reason why reauth is needed (e.g., "token_refresh_failed")
    """
    logger.warning(f"⚠️  Reauthentication required! Reason: {reason}")
    logger.info("You should restart the authentication flow")
    # In a real application, you might:
    # - Send a notification to the user
    # - Trigger a new authentication flow
    # - Store a flag in the database


async def main():
    """Main example function."""

    # Get credentials from environment variables
    client_id = os.getenv("COMDIRECT_CLIENT_ID")
    client_secret = os.getenv("COMDIRECT_CLIENT_SECRET")
    username = os.getenv("COMDIRECT_USERNAME")
    password = os.getenv("COMDIRECT_PASSWORD")

    if not all([client_id, client_secret, username, password]):
        logger.error("Missing required environment variables:")
        logger.error("  COMDIRECT_CLIENT_ID")
        logger.error("  COMDIRECT_CLIENT_SECRET")
        logger.error("  COMDIRECT_USERNAME")
        logger.error("  COMDIRECT_PASSWORD")
        return

    # Initialize client with async context manager
    async with ComdirectClient(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        base_url="https://api.comdirect.de",  # Production API
        reauth_callback=reauth_callback,  # Optional callback
        token_refresh_threshold_seconds=120,  # Refresh 2 minutes before expiry
        token_storage_path=os.path.expanduser("~/.comdirect_tokens.json"),  # Persist tokens
    ) as client:
        logger.info("=" * 60)
        logger.info("Step 1: Authentication")
        logger.info("=" * 60)

        # Check if we already have valid tokens from storage
        if client.is_authenticated():
            logger.info("✅ Using existing tokens from storage")
            expiry = client.get_token_expiry()
            if expiry:
                logger.info(f"Token expires at: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(
                    f"Token valid for: {(expiry - datetime.now(timezone.utc)).total_seconds():.0f} seconds"
                )
        else:
            try:
                # Perform full authentication (Steps 1-5)
                logger.info("No valid tokens found, starting authentication flow...")
                await client.authenticate()

                logger.info("✅ Authentication successful!")

                # Check token expiry
                expiry = client.get_token_expiry()
                if expiry:
                    logger.info(f"Token expires at: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
                    logger.info(
                        f"Token valid for: {(expiry - datetime.now(timezone.utc)).total_seconds():.0f} seconds"
                    )

            except Exception as e:
                logger.error(f"❌ Authentication failed: {e}")
                return

        # Wait a bit to demonstrate the authentication is complete
        await asyncio.sleep(2)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 2: Fetch Account Balances")
        logger.info("=" * 60)

        try:
            balances = await client.get_account_balances()

            logger.info(f"✅ Found {len(balances)} accounts:")
            for balance in balances:
                logger.info(f"\n  Account: {balance.account.accountDisplayId}")
                logger.info(f"    Type: {balance.account.accountType.text}")
                logger.info(f"    Balance: {balance.balance.value} {balance.balance.unit}")
                logger.info(
                    f"    Available: {balance.availableCashAmount.value} {balance.availableCashAmount.unit}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to fetch balances: {e}")
            return

        # Wait a bit
        await asyncio.sleep(2)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 3: Fetch ALL Transactions")
        logger.info("=" * 60)

        if balances:
            # Fetch all transactions from ALL accounts
            all_transactions = []

            for account in balances:
                account_id = account.accountId
                account_display = account.account.accountDisplayId

                try:
                    logger.info(f"\n📊 Fetching ALL transactions for account: {account_display}")

                    # Fetch ALL transactions for this account (up to 500 most recent)
                    transactions = await client.get_transactions(
                        account_id=account_id,
                        # transaction_state="BOOKED",  # Optional: filter by booking state
                        # transaction_direction="DEBIT",  # Optional: filter by direction (CREDIT/DEBIT/CREDIT_AND_DEBIT)
                    )

                    all_transactions.extend(transactions)
                    logger.info(
                        f"   ✅ Found {len(transactions)} transactions (max 500 per account)"
                    )

                except Exception as e:
                    logger.error(f"❌ Failed to fetch transactions for {account_display}: {e}")

            logger.info("")
            logger.info("=" * 60)
            logger.info(f"✅ TOTAL TRANSACTIONS ACROSS ALL ACCOUNTS: {len(all_transactions)}")
            logger.info("=" * 60)

            if all_transactions:
                # Display first 10 transactions
                logger.info("\nShowing first 10 transactions:")
                for i, tx in enumerate(all_transactions[:10]):
                    logger.info(f"\n  Transaction {i + 1}:")
                    logger.info(f"    Date: {tx.bookingDate or 'N/A'}")
                    if tx.amount:
                        logger.info(f"    Amount: {tx.amount.value} {tx.amount.unit}")
                    else:
                        logger.info("    Amount: N/A")
                    if tx.transactionType:
                        logger.info(f"    Type: {tx.transactionType.text}")
                    else:
                        logger.info("    Type: N/A")
                    text = " | ".join(tx.remittance_lines) if tx.remittance_lines else "N/A"
                    logger.info(f"    Text: {text[:50]}...")

                if len(all_transactions) > 10:
                    logger.info(f"\n  ... and {len(all_transactions) - 10} more transactions")

                # Write all transactions to JSON file
                write_transactions_to_json(all_transactions, "transactions.json")

        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 4: Demonstrate Automatic Token Refresh")
        logger.info("=" * 60)

        logger.info("The client automatically refreshes tokens in the background.")
        logger.info("Tokens are refreshed 120 seconds before expiration.")
        logger.info("You can continue making API calls without worrying about token expiry.")

        # Demonstrate get_transactions, which now fetches up to 500 transactions
        if balances:
            first_account = balances[0]
            account_id = first_account.accountId
            account_display = first_account.account.accountDisplayId

            logger.info(
                "\n================ get_transactions() demonstration (fetch-all) ================"
            )

            try:
                logger.info(f"Calling get_transactions() for {account_display}")
                tx_all = await client.get_transactions(account_id=account_id)
                logger.info(f"get_transactions() returned {len(tx_all)} transactions (max 500)")
            except Exception as e:
                logger.error(f"get_transactions() error: {e}")

        logger.info("\nKeeping client alive for 10 seconds...")
        logger.info("(In production, the background task runs continuously)")
        await asyncio.sleep(10)

        logger.info("✅ Done! The client will clean up on exit.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)

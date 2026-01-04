# Comdirect Python API Client

[![PyPI version](https://img.shields.io/pypi/v/comdirect-client.svg)](https://pypi.org/project/comdirect-client/)
[![Tests](https://github.com/mcdax/comdirect-python-library/actions/workflows/tests.yml/badge.svg)](https://github.com/mcdax/comdirect-python-library/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A modern, asynchronous Python client library for the Comdirect Banking API. This library handles authentication and session management, while using [Bravado](https://github.com/Yelp/bravado) to automatically generate API methods from the official Comdirect Swagger specification.

> **Note**: This code is AI-generated but has been thoroughly manually tested and reviewed.

## Features

- ✅ **Full OAuth2 + TAN Authentication Flow** - Handles all 5 authentication steps automatically
- ✅ **Automatic Token Refresh** - Background task refreshes tokens 120s before expiration
- ✅ **Optional Token Persistence** - Save/restore tokens to disk to avoid reauthentication after app restart
- ✅ **Bravado Integration** - Auto-generated API methods from Swagger spec (all endpoints available)
- ✅ **Type-Safe Models** - Bravado generates strongly typed models from the API specification
- ✅ **Async/Await** - Built on `httpx`, `asyncio`, and `bravado-asyncio` for high performance
- ✅ **Comprehensive Logging** - Detailed logging with sensitive data sanitization
- ✅ **Reauth Callbacks** - Custom callbacks when reauthentication is needed
- ✅ **Context Manager Support** - Automatic resource cleanup

## API Documentation References

This client implements the official Comdirect REST API:

- [Comdirect REST API Documentation (PDF)](https://kunde.comdirect.de/cms/media/comdirect_REST_API_Dokumentation.pdf)
- [Comdirect REST API Swagger Specification (JSON)](https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json)

---

## Table of Contents

- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running Tests](#running-tests)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Using the Bravado API Client](#using-the-bravado-api-client)
- [Token Management](#token-management)
  - [Automatic Token Refresh](#automatic-token-refresh)
  - [Token Persistence](#token-persistence)
  - [On-Demand Token Refresh](#on-demand-token-refresh)
  - [Reauth Callback](#reauth-callback)
  - [Token Lifecycle](#token-lifecycle)
- [Persistent Client Usage](#persistent-client-usage)
- [Data Models](#data-models)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Security Notes](#security-notes)

---

## Project Structure

```
comdirect-lib/
├── comdirect_client/           # Main package
│   ├── __init__.py             # Package exports
│   ├── client.py               # ComdirectClient with auth and Bravado integration
│   ├── bravado_adapter.py      # Custom HTTP client adapter for Bravado
│   ├── exceptions.py           # Custom exceptions
│   └── token_storage.py        # Token persistence
│
├── examples/
│   └── basic_usage.py          # Complete usage example with real authentication
│
├── tests/
│   ├── conftest.py             # Pytest fixtures and mocking setup
│   ├── test_authentication.py  # Authentication flow tests
│   ├── test_token_management.py # Token refresh and management tests
│   └── test_token_storage.py   # Token persistence tests
│
├── pyproject.toml              # Poetry dependencies and configuration
├── test.sh                     # Quick integration test script
├── .env.example                # Environment variable template
└── README.md                   # This file
```

### Key Components

- **`client.py`**: Core API client with OAuth2 flow, token refresh, and Bravado client initialization
- **`bravado_adapter.py`**: Custom HTTP client adapter that injects Comdirect authentication headers
- **`exceptions.py`**: Specific exception types for different failure scenarios
- **`token_storage.py`**: Token persistence for avoiding reauthentication after restart
- **Bravado**: Automatically generates API methods and models from the Swagger specification

---

## Installation

### Prerequisites

- **Python 3.9+** (tested with Python 3.9-3.12)

### Using pip (Recommended)

Install directly from PyPI:

```bash
pip install comdirect-client
```

### For Development

If you want to contribute or modify the library:

#### Using Poetry

```bash
# Clone the repository
git clone https://github.com/mcdax/comdirect-python-library.git
cd comdirect-lib

# Install production dependencies
poetry install

# Install with development dependencies (tests, linting, etc.)
poetry install --with dev

# Activate virtual environment
poetry shell
```

#### Using pip

```bash
# Clone the repository
git clone https://github.com/mcdax/comdirect-python-library.git
cd comdirect-lib

# Install in editable mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

### Dependencies

**Production:**

- `httpx ^0.27.0` - Async HTTP client
- `pydantic ^2.0.0` - Data validation

**Development:**

- `pytest ^8.0.0` - Testing framework
- `pytest-asyncio ^0.23.0` - Async test support
- `pytest-bdd ^7.0.0` - BDD testing with Gherkin
- `pytest-mock ^3.12.0` - Mocking utilities
- `black ^24.0.0` - Code formatter
- `mypy ^1.8.0` - Type checker
- `ruff ^0.2.0` - Fast Python linter

---

## Running Tests

### Quick Integration Test (Real API)

The fastest way to test with the real Comdirect API:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your Comdirect credentials
nano .env  # or vim, code, etc.
# Required variables:
#   COMDIRECT_CLIENT_ID=your_client_id
#   COMDIRECT_CLIENT_SECRET=your_client_secret
#   COMDIRECT_USERNAME=your_username
#   COMDIRECT_PASSWORD=your_password

# 3. Run integration test
chmod +x test.sh
./test.sh
```

**What happens:**

1. Authenticates with Comdirect API
2. **Waits for Push-TAN approval** on your smartphone (5-60 seconds)
3. Fetches account balances
4. Fetches transactions for first account
5. Tests automatic token refresh

**Expected output:**

```
INFO: Starting authentication flow
INFO: OAuth2 token obtained: 1a2b3c4d...
INFO: Waiting for TAN approval (P_TAN_PUSH)
INFO: TAN approved via P_TAN_PUSH
INFO: Authentication successful
INFO: Token refresh task started

Found 2 accounts:
  Account 1: Girokonto - Balance: 1234.56 EUR
  Account 2: Tagesgeld - Balance: 5678.90 EUR

Retrieved 15 transactions
  2024-11-09: -12.50 EUR (Direct Debit)
  ...
```

### BDD Tests (Mocked)

Run comprehensive BDD tests with mocked API responses:

```bash
# Install dev dependencies
poetry install --with dev

# Run all BDD tests
poetry run pytest tests/test_comdirect_bdd.py -v

# Run specific scenario
poetry run pytest tests/test_comdirect_bdd.py -k "token refresh" -v

# Run with coverage report
poetry run pytest --cov=comdirect_client --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

**BDD Coverage (39 scenarios):**

- ✅ Complete 5-step OAuth2 + TAN authentication flow
- ✅ Automatic token refresh (background task)
- ✅ On-demand token refresh (after 401 responses)
- ✅ Account balance retrieval
- ✅ Transaction retrieval with filters
- ✅ Pagination support
- ✅ Error handling and logging
- ✅ Reauth callback mechanism

### Unit Tests

```bash
# Run all tests
poetry run pytest tests/ -v

# Run with markers
poetry run pytest tests/ -m "not slow" -v

# Verbose output
poetry run pytest tests/ -vv -s
```

### Code Quality Tools

```bash
# Type checking
poetry run mypy comdirect_client

# Linting
poetry run ruff check .

# Auto-fix linting issues
poetry run ruff check --fix .

# Code formatting
poetry run black .

# Check formatting without changes
poetry run black --check .
```

---

## Quick Start

### 1. Install the Package

```bash
pip install comdirect-client
```

### 2. Basic Usage Example

```python
import asyncio
import os
from comdirect_client.client import ComdirectClient


async def main():
    # Initialize client
    async with ComdirectClient(
        client_id=os.getenv("COMDIRECT_CLIENT_ID"),
        client_secret=os.getenv("COMDIRECT_CLIENT_SECRET"),
        username=os.getenv("COMDIRECT_USERNAME"),
        password=os.getenv("COMDIRECT_PASSWORD"),
    ) as client:
        
        # Authenticate (triggers Push-TAN on your smartphone)
        print("Authenticating...")
        await client.authenticate()
        print("✓ Authenticated!")
        
        # Use Bravado-generated API methods
        # Fetch account balances
        balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
            user="user"
        ).result()
        balances = balances_response.values
        
        print(f"\nFound {len(balances)} accounts:")
        for balance in balances:
            account = balance.account
            print(f"  {account.accountDisplayId}: {balance.balance.value} {balance.balance.unit}")
         
        # Fetch transactions for first account
        if balances:
            account_id = balances[0].accountId
            transactions_response = await client.api.banking.v1.accounts.transactions.get(
                accountId=account_id,
                transactionState="BOOKED",
                paging_count=500
            ).result()
            transactions = transactions_response.values
            
            print(f"\nFound {len(transactions)} transactions:")
            for tx in transactions[:5]:  # Show first 5
                # Use booking date if available, otherwise fall back to valuta date
                display_date = tx.bookingDate.date if tx.bookingDate else tx.valutaDate
                amount = tx.amount.value if tx.amount else "N/A"
                unit = tx.amount.unit if tx.amount else ""
                print(f"  {display_date}: {amount} {unit}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Set Up Your Credentials

```bash
# Set environment variables
export COMDIRECT_CLIENT_ID="your_client_id"
export COMDIRECT_CLIENT_SECRET="your_client_secret"
export COMDIRECT_USERNAME="your_username"
export COMDIRECT_PASSWORD="your_password"

# Run your script
python your_script.py
```

### 4. Run the Included Example (Development Only)

If you've cloned the repository:

```bash
# Export credentials
export $(cat .env | xargs)

# Run example (requires Push-TAN approval on smartphone)
poetry run python examples/basic_usage.py

# Or use the test script
./test.sh
```

**Expected Flow:**

1. Script starts → Sends authentication request
2. **Your smartphone receives Push-TAN notification** (approve within 60s)
3. After approval → Fetches account data
4. Displays balances and recent transactions

---

## API Reference

### Client Initialization

```python
from comdirect_client.client import ComdirectClient

client = ComdirectClient(
    client_id: str,                     # OAuth2 client ID (required)
    client_secret: str,                 # OAuth2 client secret (required)
    username: str,                      # Comdirect username (required)
    password: str,                      # Comdirect password (required)
    base_url: str = "https://api.comdirect.de",  # API base URL
    swagger_spec_url: str = "https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json",  # Swagger spec URL
    token_storage_path: Optional[str] = None,    # File path for token persistence
    reauth_callback: Optional[Callable[[str], None]] = None,  # Called when reauth needed
    tan_status_callback: Optional[Callable[[str, dict], None]] = None,  # Called during TAN approval
    token_refresh_threshold_seconds: int = 120,  # Refresh 120s before expiry
    timeout_seconds: float = 30.0,     # HTTP request timeout
)
```

### Authentication

#### `authenticate()`

Performs the complete OAuth2 + TAN authentication flow (5 steps):

1. Password credentials grant → Initial token
2. Session status retrieval → Session UUID
3. TAN challenge creation → Triggers Push-TAN
4. TAN approval polling → Waits up to 60 seconds
5. Session activation + token exchange → Banking token

```python
await client.authenticate()
# Waits for Push-TAN approval on smartphone
# Raises TANTimeoutError if no approval within 60 seconds
# Raises AuthenticationError if credentials invalid
```

**What happens:**

- Sends authentication request to Comdirect API
- Creates TAN challenge (Push-TAN/Photo-TAN/SMS-TAN)
- **User must approve TAN on smartphone within 60 seconds**
- Polls for approval every 1 second
- Activates session and obtains banking token
- Starts automatic token refresh background task

#### `is_authenticated()`

Check if client has valid authentication token:

```python
if client.is_authenticated():
    print("Authenticated!")
else:
    print("Not authenticated - call authenticate() first")
```

#### `get_token_expiry()`

Get token expiration datetime:

```python
from datetime import datetime

expiry: Optional[datetime] = client.get_token_expiry()
if expiry:
    seconds_remaining = (expiry - datetime.now()).total_seconds()
    print(f"Token expires in {seconds_remaining:.0f} seconds")
```

#### `refresh_token()`

Manually refresh access token (usually done automatically):

```python
success: bool = await client.refresh_token()
if success:
    print("Token refreshed successfully")
else:
    print("Token refresh failed - reauthentication needed")
```

**Note:** The client automatically refreshes tokens in the background 120 seconds before expiration. Manual refresh is rarely needed.

---

### Using the Bravado API Client

After authentication, access all Comdirect API endpoints via the `api` property, which provides Bravado-generated methods from the Swagger specification.

#### Accessing the API Client

```python
# After authenticating
await client.authenticate()

# Access the Bravado-generated API client
api = client.api
```

#### Example: Fetching Account Balances

```python
# Get account balances
balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
    user="user"
).result()

# Access the values
balances = balances_response.values

for balance in balances:
    print(f"Account ID: {balance.accountId}")
    print(f"Display ID: {balance.account.accountDisplayId}")
    print(f"Balance: {balance.balance.value} {balance.balance.unit}")
    print(f"Available: {balance.availableCashAmount.value} {balance.availableCashAmount.unit}")
```

**With Query Parameters:**

```python
# Exclude account master data
balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
    user="user",
    without_attr="account"
).result()
```

#### Example: Fetching Transactions

```python
# Get transactions for an account
transactions_response = await client.api.banking.v1.accounts.transactions.get(
    accountId="account-uuid-here",
    transactionState="BOOKED",
    transactionDirection="CREDIT_AND_DEBIT",
    paging_count=500
).result()

transactions = transactions_response.values

for tx in transactions:
    # Use booking date if available, otherwise fall back to valuta date
    display_date = tx.bookingDate.date if tx.bookingDate else tx.valutaDate
    print(f"Date: {display_date}")
    if tx.amount:
        print(f"Amount: {tx.amount.value} {tx.amount.unit}")
    if tx.transactionType:
        print(f"Type: {tx.transactionType.text}")
    if tx.remittanceInfo:
        print(f"Remittance: {tx.remittanceInfo}")
```

**With Date Filtering:**

```python
# Fetch transactions for a date range
transactions_response = await client.api.banking.v1.accounts.transactions.get(
    accountId="account-uuid-here",
    min_bookingDate="2024-01-01",
    max_bookingDate="2024-12-31",
    paging_count=500
).result()
```

#### Available API Endpoints

All endpoints from the [Comdirect Swagger specification](https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json) are available via `client.api.*`. The API structure follows the Swagger spec paths:

- **Banking**: `client.api.banking.*`
  - Account balances: `client.api.banking.clients.user.v2.accounts.balances.get()`
  - Transactions: `client.api.banking.v1.accounts.transactions.get()`
- **Brokerage**: `client.api.brokerage.*`
- **Messages**: `client.api.messages.*`
- **Reports**: `client.api.reports.*`
- **Session**: `client.api.session.*`

#### Important Notes

1. **Always call `.result()`**: Bravado-asyncio operations return futures that must be awaited via `.result()`
2. **Response Structure**: Responses follow the Swagger spec structure. Most list endpoints return a response with a `values` property containing the actual data
3. **Type Safety**: Bravado generates type-safe models from the Swagger spec
4. **Error Handling**: Bravado raises its own exceptions (e.g., `HTTPError`). You may want to catch and convert them to your custom exceptions if needed

#### Example: Error Handling

```python
from bravado.exception import HTTPError

try:
    response = await client.api.banking.v1.accounts.transactions.get(
        accountId="invalid-uuid"
    ).result()
except HTTPError as e:
    if e.status_code == 404:
        print("Account not found")
    elif e.status_code == 422:
        print("Invalid request parameters")
    else:
        print(f"API error: {e}")
```

---

## Token Management

### Automatic Token Refresh

The client automatically refreshes access tokens in the background:

**How it works:**

1. After successful authentication, starts background asyncio task
2. Calculates refresh time: `token_expiry - 120 seconds` (configurable)
3. Sleeps until refresh time
4. Automatically calls `POST /oauth/token` with `grant_type=refresh_token`
5. Updates `access_token` and `refresh_token` (both tokens rotate!)
6. Repeats indefinitely

**Configuration:**

```python
client = ComdirectClient(
    ...,
    token_refresh_threshold_seconds=120,  # Refresh 120s before expiry (default)
)
```

**Timeline Example:**

```
T+0:     authenticate() → token expires at T+599s
T+479s:  Background task wakes up (599 - 120 = 479)
T+479s:  POST /oauth/token → new token expires at T+1078s
T+958s:  Next automatic refresh (1078 - 120 = 958)
...
```

**Failure Handling:**

- If refresh fails → Invokes `reauth_callback` (if configured)
- Clears all tokens
- Stops background refresh task

### Token Persistence

The client supports optional file-based token persistence to avoid reauthentication after application restart. Tokens are stored securely with restricted file permissions (0o600 - owner read/write only).

**Security Note:** Token persistence stores authentication tokens to disk. Ensure the storage directory is on an encrypted filesystem and has appropriate access controls. In production, consider encrypting tokens at rest using your application's encryption layer.

**Enable Token Persistence:**

```python
import asyncio
from comdirect_client.client import ComdirectClient

async def main():
    # Enable token persistence by providing a storage path
    async with ComdirectClient(
        client_id="your_client_id",
        client_secret="your_client_secret",
        username="your_username",
        password="your_password",
        token_storage_path="/secure/path/comdirect_tokens.json",
    ) as client:
        
        # First run: Authenticate and tokens are automatically saved
        try:
            await client.authenticate()
            print("✓ Authenticated and tokens saved to disk")
        except FileNotFoundError:
            print("✗ Token storage directory doesn't exist")
        
        # Subsequent runs: Tokens are automatically loaded from disk
        # If tokens are valid, authenticate() returns immediately without 2FA
        # If tokens are expired, they're silently discarded and new auth is needed

if __name__ == "__main__":
    asyncio.run(main())
```

**How Token Persistence Works:**

1. **Initialization**: Client loads saved tokens on startup (if they exist and aren't expired)
2. **Auto-Save**: After authentication or token refresh, tokens are automatically saved to disk
3. **Expiry Validation**: Expired tokens are rejected during load and reauthentication is triggered
4. **File Security**: Token file has restricted permissions (0o600 - owner only)
5. **On Logout**: Token file is automatically deleted via `client.close()` or context manager

**Persistent Storage Format:**

Tokens are stored as JSON with ISO format datetime:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "refresh_token_value_here",
  "token_expiry": "2025-12-10T15:30:45.123456"
}
```

**Recovery Scenarios:**

```python
# Scenario 1: Tokens exist and are valid
async with ComdirectClient(..., token_storage_path="...") as client:
    await client.authenticate()  # Returns immediately, no 2FA needed!
    balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
        user="user"
    ).result()

# Scenario 2: Tokens expired, need reauthentication
async with ComdirectClient(..., token_storage_path="...") as client:
    await client.authenticate()  # Triggers new 2FA flow
    # Old expired tokens are automatically cleared

# Scenario 3: First run, no tokens saved yet
async with ComdirectClient(..., token_storage_path="...") as client:
    await client.authenticate()  # Normal 2FA flow
    # Tokens saved to disk for next run

# Scenario 4: Storage directory doesn't exist
async with ComdirectClient(..., token_storage_path="/nonexistent/path") as client:
    await client.authenticate()  # Works normally, but won't persist
    # TokenStorageError logged as warning
```

**Error Handling:**

```python
from comdirect_client.exceptions import TokenStorageError

try:
    async with ComdirectClient(..., token_storage_path="...") as client:
        await client.authenticate()
except TokenStorageError as e:
    print(f"Token storage failed: {e}")
    # Token persistence unavailable, but client works normally
except FileNotFoundError:
    print("Token storage directory doesn't exist - create it first")
    import os
    os.makedirs(os.path.dirname(token_storage_path), exist_ok=True)
```

**Disabling Token Persistence:**

```python
# Simply omit the token_storage_path parameter (or set to None)
async with ComdirectClient(
    client_id="...",
    client_secret="...",
    username="...",
    password="...",
    # No token_storage_path - tokens not persisted
) as client:
    await client.authenticate()
```

### On-Demand Token Refresh

If an API call receives `401 Unauthorized`, the client automatically:

1. Attempts token refresh
2. Retries the original request with new token
3. If refresh fails → Invokes `reauth_callback` and raises `TokenExpiredError`

This provides a **dual refresh strategy**:

- **Proactive**: Background task (before expiration)
- **Reactive**: On 401 errors (after expiration)

### Reauth Callback

Configure a callback to handle reauthentication needs:

```python
def reauth_handler(reason: str):
    """Called when reauthentication is needed."""
    print(f"Reauthentication required: {reason}")
    # Send notification, trigger new auth flow, restart service, etc.
    
    # Reasons:
    # - "token_refresh_failed" - Background refresh failed
    # - "automatic_refresh_failed" - Background task error
    # - "api_request_unauthorized" - API returned 401 after refresh attempt

client = ComdirectClient(
    ...,
    reauth_callback=reauth_handler,
)
```

**Use cases:**

- Send email/Slack notification to admin
- Trigger new authentication flow
- Log metrics/alerting
- Gracefully restart service

### Token Lifecycle

Tokens expire every ~10 minutes (599s). The client automatically refreshes 120 seconds before expiration, ensuring seamless API calls. When a token refresh occurs, both `access_token` and `refresh_token` rotate on the Comdirect API side.

---

## Persistent Client Usage

**The ComdirectClient should be kept alive (persistent) throughout your application's lifecycle for best functionality.**

### Why Keep the Client Alive?

The client has a **background token refresh task** that automatically refreshes tokens 120 seconds before they expire. This task runs as an asyncio background coroutine and is critical for maintaining uninterrupted access to the Comdirect API.

**If the client instance is destroyed:**

- The background refresh task is cancelled
- Tokens will expire after ~10 minutes (599 seconds)
- A new TAN approval will be required for your next session
- This defeats the purpose of automatic token refresh

### Best Practice: Create Once, Reuse Everywhere

```python
import asyncio
from comdirect_client.client import ComdirectClient

# Global client instance - created once at application startup
client: ComdirectClient | None = None

async def init_client():
    """Initialize the client once at startup."""
    global client
    client = ComdirectClient(
        client_id="your_client_id",
        client_secret="your_client_secret",
        username="your_username",
        password="your_password",
        token_storage_path="/path/to/tokens.json",  # Persist across restarts
    )
    
    # Authenticate once - requires TAN approval
    await client.authenticate()
    print("Client authenticated and ready!")
    
    # The background refresh task is now running automatically
    # Tokens will be refreshed 120s before expiry

async def get_balances():
    """Use the persistent client for API calls."""
    if not client:
        raise RuntimeError("Client not initialized")
    response = await client.api.banking.clients.user.v2.accounts.balances.get(
        user="user"
    ).result()
    return response.values

async def get_transactions(account_id: str):
    """Another API call using the same client instance."""
    if not client:
        raise RuntimeError("Client not initialized")
    response = await client.api.banking.v1.accounts.transactions.get(
        accountId=account_id
    ).result()
    return response.values

async def shutdown():
    """Clean up when application shuts down."""
    if client:
        await client.close()
```

### What Happens with Token Storage?

When you configure `token_storage_path`:

1. **First run**: Authenticate with TAN, tokens are saved to disk
2. **Subsequent runs**: Tokens are loaded from disk on client creation
3. **Background refresh starts automatically** when valid tokens are loaded
4. **No new TAN approval needed** as long as tokens haven't expired

```python
# Application startup
client = ComdirectClient(
    ...,
    token_storage_path="/path/to/tokens.json",
)

# If valid tokens exist in storage:
# - Tokens are automatically loaded
# - Refresh task starts immediately
# - No authenticate() call needed!

if client.is_authenticated():
    print("Tokens restored from storage - ready to use!")
    balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
        user="user"
    ).result()
    balances = balances_response.values
else:
    print("No valid tokens - TAN approval required")
    await client.authenticate()
```

### Anti-Pattern: Creating New Client Per Request

**Do NOT do this** - it defeats the purpose of automatic token refresh:

```python
# BAD: Client is destroyed after each request
async def get_balance_bad():
    async with ComdirectClient(...) as client:
        await client.authenticate()  # TAN approval needed
        response = await client.api.banking.clients.user.v2.accounts.balances.get(
            user="user"
        ).result()
        return response.values
    # Client destroyed here! Refresh task cancelled!

# After ~10 minutes, calling get_balance_bad() again requires new TAN approval
```

### Framework Integration Examples

**FastAPI / Starlette:**

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from comdirect_client.client import ComdirectClient

client: ComdirectClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = ComdirectClient(
        ...,
        token_storage_path="/app/data/tokens.json",
    )
    if not client.is_authenticated():
        await client.authenticate()
    yield
    await client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/balances")
async def get_balances():
    response = await client.api.banking.clients.user.v2.accounts.balances.get(
        user="user"
    ).result()
    return response.values
```

**Long-running Service:**

```python
async def main():
    client = ComdirectClient(
        ...,
        token_storage_path="tokens.json",
        reauth_callback=lambda reason: print(f"Reauth needed: {reason}"),
    )
    
    if not client.is_authenticated():
        await client.authenticate()
    
    # Run indefinitely - tokens refresh automatically
    while True:
        balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
            user="user"
        ).result()
        balances = balances_response.values
        if balances:
            print(f"Current balance: {balances[0].balance.value} {balances[0].balance.unit}")
        await asyncio.sleep(3600)  # Check every hour

asyncio.run(main())
```

---

## Data Models

All API responses use **Bravado-generated models** from the Swagger specification. These models are automatically generated and provide type safety based on the official API schema.

### Accessing Model Properties

Bravado models follow the Swagger specification structure. Here are some common patterns:

**Account Balance Example:**

```python
balances_response = await client.api.banking.clients.user.v2.accounts.balances.get(
    user="user"
).result()

for balance in balances_response.values:
    # Access nested account object
    account = balance.account
    print(f"Account ID: {balance.accountId}")
    print(f"Display ID: {account.accountDisplayId}")
    print(f"Type: {account.accountType.text}")
    
    # Access amount values
    print(f"Balance: {balance.balance.value} {balance.balance.unit}")
    print(f"Available: {balance.availableCashAmount.value} {balance.availableCashAmount.unit}")
```

**Transaction Example:**

```python
transactions_response = await client.api.banking.v1.accounts.transactions.get(
    accountId="account-uuid"
).result()

for tx in transactions_response.values:
    # Date handling (bookingDate may be None for pending transactions)
    if tx.bookingDate:
        date_obj = tx.bookingDate.date  # Access date property
    else:
        date_str = tx.valutaDate  # Fallback to valutaDate string
    
    # Amount (may be None)
    if tx.amount:
        print(f"Amount: {tx.amount.value} {tx.amount.unit}")
    
    # Transaction type
    if tx.transactionType:
        print(f"Type: {tx.transactionType.text}")
    
    # Remittance info (raw string from API)
    if tx.remittanceInfo:
        print(f"Remittance: {tx.remittanceInfo}")
    
    # Account information
    if tx.creditor:
        print(f"Creditor: {tx.creditor.holderName}")
    if tx.debtor:
        print(f"Debtor: {tx.debtor.holderName}")
```

### Model Structure

Bravado models are generated from the Swagger spec, so they match the API documentation exactly. Key points:

- **Nested Objects**: Access nested properties directly (e.g., `balance.account.accountDisplayId`)
- **Optional Fields**: Many fields may be `None` - always check before accessing
- **Date Fields**: Some date fields are objects with a `.date` property, others are strings
- **Amount Values**: Amount fields have `.value` (string) and `.unit` (string) properties

For the complete model structure, refer to the [Comdirect Swagger specification](https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json).

---

## Error Handling

The library provides specific exceptions for different error scenarios, all defined in `comdirect_client.exceptions`:

### Exception Types

```python
from comdirect_client.exceptions import (
    AuthenticationError,      # Invalid credentials or auth failure
    ValidationError,          # Invalid request parameters (422)
    ServerError,              # Server error on API side (500)
    TANTimeoutError,          # TAN approval timeout (60 seconds)
    TokenExpiredError,        # Token expired and refresh failed
    SessionActivationError,   # Session activation failed
    AccountNotFoundError,     # Account UUID doesn't exist
    NetworkTimeoutError,      # Network request timeout
)
```

**Exception Hierarchy:**

```
ComdirectAPIError (base)
├── AuthenticationError       
├── ValidationError          
├── ServerError             
├── AccountNotFoundError   
├── TANTimeoutError
├── SessionActivationError
├── TokenExpiredError
└── NetworkTimeoutError
```

---

## Logging

The library uses Python's standard `logging` module with comprehensive logging throughout the codebase.

### Configure Logging

```python
import logging

# Basic configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Get logger for specific module
logger = logging.getLogger("comdirect_client.client")
logger.setLevel(logging.DEBUG)  # Set DEBUG for detailed logs
```

### Log Levels

| Level | Usage | Example |
|-------|-------|---------|
| **DEBUG** | Detailed technical info | `Request ID: 123456789` |
| **INFO** | High-level flow events | `Authentication successful` |
| **WARNING** | Recoverable issues | `Token refresh failed - token expired` |
| **ERROR** | Critical failures | `Authentication failed: Invalid credentials` |

---

## License

MIT License - see LICENSE file for details

## Disclaimer

This is an unofficial client library. Use at your own risk. The authors are not affiliated with Comdirect Bank AG.

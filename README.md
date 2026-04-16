# Comdirect Python API Client

[![PyPI version](https://img.shields.io/pypi/v/comdirect-client.svg)](https://pypi.org/project/comdirect-client/)
[![Tests](https://github.com/mcdax/comdirect-python-library/actions/workflows/tests.yml/badge.svg)](https://github.com/mcdax/comdirect-python-library/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Async Python client for the comdirect Banking and Brokerage API. Handles
the OAuth2 + push-TAN login flow, refreshes tokens in the background, and
gives you typed dataclasses for every read-only endpoint of the public
comdirect REST API.

> **Heads up**: This code is AI-assisted but has been reviewed and run
> against production. Every read-only method in this library was
> end-to-end verified against a real account on 2026-04-16 — see
> [`COMDIRECT_API.md`](COMDIRECT_API.md) for the details, including a
> corrected `remittanceInfo` parser, live pagination limits, and
> verified Accept-header behaviour for document downloads.

## Features

- **Full OAuth2 + TAN auth** — 5-step flow, push-TAN polling, session activation.
- **Automatic token refresh** — background task refreshes 120s before expiry.
- **Token persistence** — optional atomic-write JSON file so restarts don't need a new TAN.
- **Banking endpoints** — balances + transactions (incl. `>500` pagination helper).
- **Brokerage endpoints** — depots, positions, depot transactions, orders, instrument lookup.
- **Messages endpoints** — PostBox document list + binary download (PDF/HTML).
- **Reports endpoint** — `allbalances` cross-product view (accounts, depots, cards, loans).
- **Verified `remittanceInfo` parser** — 37/35-char windows, SEPA label extraction, whitespace normalization.
- **Typed dataclasses** — `Account`, `AccountBalance`, `Transaction`, `Depot`, `DepotPosition`, `Order`, `Document`, `ProductBalance`, etc.
- **Typed errors** — specific exceptions for auth / TAN timeout / 422 / 500 / account-not-found / network timeout.
- **Configurable TAN timing** — if your phone approval takes longer than 60s.

## Official references

- [comdirect REST API PDF](https://kunde.comdirect.de/cms/media/comdirect_REST_API_Dokumentation.pdf) (German, April 2020)
- [comdirect REST API Swagger](https://kunde.comdirect.de/cms/media/comdirect_rest_api_swagger.json)
- [`COMDIRECT_API.md`](COMDIRECT_API.md) — our verified notes, including pitfalls not in the official docs (remittance parsing, pagination rules, 406 on documents, etc.)

---

## Installation

```bash
pip install comdirect-client
```

Requires Python 3.9+. Sole runtime dependency is `httpx`.

For development:

```bash
git clone https://github.com/mcdax/comdirect-python-library.git
cd comdirect-python-library
poetry install --with dev
```

---

## Quick start

```python
import asyncio
import os
from comdirect_client import ComdirectClient


async def main():
    async with ComdirectClient(
        client_id=os.environ["COMDIRECT_CLIENT_ID"],
        client_secret=os.environ["COMDIRECT_CLIENT_SECRET"],
        username=os.environ["COMDIRECT_USERNAME"],
        password=os.environ["COMDIRECT_PASSWORD"],
        token_storage_path=os.path.expanduser("~/.comdirect_tokens.json"),
    ) as client:
        # First run: triggers push-TAN on your phone (approve within 60s).
        # Later runs: reuses tokens from disk, no TAN needed.
        if not client.is_authenticated():
            await client.authenticate()

        balances = await client.get_account_balances()
        for b in balances:
            print(f"{b.account.accountDisplayId} ({b.account.accountType.key}): "
                  f"{b.balance.value} {b.balance.unit}")

        if balances:
            txs = await client.get_transactions(balances[0].accountId, paging_count=20)
            for tx in txs[:5]:
                date = tx.bookingDate or tx.valutaDate
                amt = f"{tx.amount.value} {tx.amount.unit}" if tx.amount else "n/a"
                kind = tx.transactionType.key if tx.transactionType else ""
                print(f"  {date} {amt:>15}  {kind:>20}  {' / '.join(tx.remittance_lines[:1])}")


asyncio.run(main())
```

---

## API reference

### Client construction

```python
ComdirectClient(
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    *,
    base_url: str = "https://api.comdirect.de",
    token_storage_path: str | None = None,
    reauth_callback: Callable[[str], None | Awaitable[None]] | None = None,
    tan_status_callback: Callable[[str, dict], None] | None = None,
    token_refresh_threshold_seconds: int = 120,
    timeout_seconds: float = 30.0,
    tan_timeout_seconds: int = 60,
    tan_poll_interval_seconds: float = 1.0,
)
```

- Use as an async context manager (`async with ComdirectClient(...) as client:`), or manage the lifecycle manually and call `await client.close()` on shutdown.
- `token_storage_path` enables persistent login across process restarts. The file is written atomically with `0600` permissions.
- `reauth_callback(reason)` is invoked when the background refresh fails. Sync or async.
- `tan_status_callback(status, data)` fires at key points of the push-TAN poll — status is one of `"requested"`, `"pending"`, `"approved"`, `"timeout"`.
- `tan_timeout_seconds` / `tan_poll_interval_seconds` let you widen the push-TAN wait window if users are slow to approve.

### Authentication

| Method | What it does |
|---|---|
| `await authenticate()` | Runs the full 5-step flow. Triggers push-TAN. Raises `AuthenticationError`, `TANTimeoutError`, `SessionActivationError`. Only push-TAN (`P_TAN_PUSH`) is supported headlessly; photo-TAN / SMS-TAN raise `AuthenticationError` with a clear message. |
| `await refresh_token()` | Refreshes the access + refresh token pair. Called automatically by the background task. Returns `False` if the refresh fails (invokes the reauth callback). |
| `is_authenticated()` | True if tokens are loaded (even if expired — the refresh token may still be valid). |
| `get_token_expiry()` | The current access token's expiry as a UTC-aware `datetime`. |
| `register_reauth_callback(cb)` / `register_tan_status_callback(cb)` | Replace the callbacks after construction. |

### Banking

```python
balances = await client.get_account_balances()

txs = await client.get_transactions(
    account_id,
    transaction_state="BOOKED",           # BOOKED / NOTBOOKED / BOTH
    transaction_direction="DEBIT",        # CREDIT / DEBIT / CREDIT_AND_DEBIT
    min_booking_date="2025-06-01",        # ISO date; also unlocks history > 6 months
    max_booking_date="2025-12-31",        # ISO date
    paging_count=500,                     # server cap is 500
    paging_first=0,                       # > 0 requires transactionState="BOOKED"
)

all_booked = await client.fetch_all_booked_transactions(
    account_id,
    min_booking_date="2020-01-01",
)
# Walks paging-first in 500-sized chunks with transactionState=BOOKED.
# This is the only way to retrieve > 500 transactions per account.
```

Full discussion of pagination rules (why `paging-first` requires `BOOKED`, why the default response is capped, how `matches` works) is in [`COMDIRECT_API.md`](COMDIRECT_API.md).

### Brokerage

```python
depots = await client.get_depots()
depot = depots[0]

positions  = await client.get_depot_positions(depot.depotId)
position   = await client.get_depot_position(depot.depotId, position.positionId)
dtxs       = await client.get_depot_transactions(depot.depotId, min_booking_date="-30d")
orders     = await client.get_depot_orders(depot.depotId,
                                            min_creation_timestamp="2026-01-01T00:00:00,00")
order      = await client.get_order(order_id)
instrument = await client.get_instrument("US0378331005")  # WKN/ISIN/mnemonic/UUID
```

Date/timestamp format conventions differ across brokerage endpoints — see the table in [`COMDIRECT_API.md`](COMDIRECT_API.md#brokerage-date--timestamp-filter-conventions).

Order write operations (place / modify / cancel / prevalidation / cost indication / quote flow) are deliberately **not** wrapped — they require per-transaction TAN re-approval. Open an issue or a PR if you need them.

### Messages / documents

```python
docs = await client.get_documents(min_document_date="2025-01-01", paging_count=50)

# Download one document (PDF or HTML) as bytes.
content, mime_type = await client.get_document_content(docs[0].documentId)

# For documents with a predocument (Vorschaltseite):
if docs[0].documentMetaData and docs[0].documentMetaData.predocumentExists:
    pre_content, pre_mime = await client.get_document_content(
        docs[0].documentId, predocument=True
    )
```

The library sends `Accept: application/pdf, text/html` for document downloads. Sending `Accept: application/json` triggers `406 Not Acceptable` from the server — that's an API design choice, not a library bug (verified against production on 2026-04-16).

### Reports

```python
all_balances = await client.get_all_balances()
# Returns ProductBalance entries across accounts, depots, cards, loans,
# and fixed-term savings. Each entry's .balance is kept as a raw dict
# because the shape depends on .productType — branch on productType and
# index into balance yourself.

for p in all_balances:
    print(p.productType, p.productId, p.balance)
```

---

## Data models

All response bodies are parsed into dataclasses with `from_dict` classmethods. Monetary amounts use `Decimal`, dates use `datetime.date` (only for `Transaction.bookingDate`; everything else stays as ISO strings).

### Banking

- `Account` — master data (`accountId`, `accountDisplayId`, `currency`, `clientId`, `accountType: EnumText`, optional `iban`, `bic`, `creditLimit`)
- `AccountBalance` — `accountId`, `account: Account`, `balance: AmountValue`, `balanceEUR`, `availableCashAmount`, `availableCashAmountEUR`
- `Transaction` — `bookingStatus`, `reference`, `valutaDate`, `newTransaction`, optional `amount`, `transactionType`, `remittanceInfo`, `bookingDate`, `remitter`, `debtor`, `creditor`, `endToEndReference`, `directDebitCreditorId`, `directDebitMandateId`
  - `.remittance_lines` — Buchungstext as rendered by the banking web UI (one entry per on-screen line)
  - `.remittance` — full `ParsedRemittance` with `buchungstext_lines`, `end_to_end_reference`, `mandate_reference`, `creditor_id` extracted from the SEPA labels embedded in `remittanceInfo`

### Brokerage

- `Depot`, `DepotPosition`, `DepotTransaction`, `Order`, `Execution`, `Instrument`, `Price`

### Messages

- `Document`, `DocumentMetadata`

### Reports

- `ProductBalance` (with raw `balance` dict — shape varies by `productType`)

### Shared

- `AmountValue { value: Decimal, unit: str }`
- `EnumText { key: str, text: str }` — match on `key`, the `text` is a German-ish display string
- `AccountInformation { holderName, iban?, bic? }`

### Remittance parser (important)

The `remittanceInfo` field is a flat string with fixed-width windows — **not** newline-separated as the April-2020 PDF claims. The library's parser is verified against live data and the banking web UI. You generally shouldn't need to parse it yourself, but if you want to:

```python
from comdirect_client import parse_remittance_info

result = parse_remittance_info(tx.remittanceInfo, tx.bookingStatus)
result.buchungstext_lines       # list[str], each one chunk as shown in the web UI
result.end_to_end_reference     # from the 'End-to-End-Ref.:' SEPA label
result.mandate_reference        # from 'CORE / Mandatsref.:'
result.creditor_id              # from 'Gläubiger-ID:'
```

Full rules (37 vs 35 char windows, whitespace collapse, SEPA label extraction, verified test cases) are in [`COMDIRECT_API.md`](COMDIRECT_API.md#remittanceinfo-parsing-verwendungszweck).

---

## Token management

### Background refresh

After `authenticate()` or on startup with restored tokens, a background task refreshes the access token ~120 seconds before expiry. You don't need to call `refresh_token()` yourself in normal usage.

### Persistence

```python
async with ComdirectClient(
    ...,
    token_storage_path="/secure/dir/comdirect_tokens.json",
) as client:
    # On first run, triggers a TAN; afterwards, reuses the stored refresh
    # token across restarts so you skip the TAN approval.
    if not client.is_authenticated():
        await client.authenticate()
```

The token file is JSON with three fields (`access_token`, `refresh_token`, `token_expiry`). Writes are atomic (temp file + `os.replace`) and the file is created with `0600` permissions from the first byte — even if you kill the process mid-write, you won't end up with a corrupt file or world-readable tokens.

On a failed refresh, the file is cleared automatically to prevent zombie-login states across restarts.

### Reauth callback

```python
async def on_reauth(reason: str) -> None:
    # reason is one of:
    #   "token_refresh_failed"        — explicit refresh call failed
    #   "automatic_refresh_failed"    — background refresh task gave up
    await notify_slack(f"comdirect reauth required: {reason}")

async with ComdirectClient(..., reauth_callback=on_reauth) as client:
    ...
```

Both sync and async callbacks are supported.

---

## Error handling

All exceptions inherit from `ComdirectAPIError`:

| Exception | Raised when |
|---|---|
| `AuthenticationError` | Bad credentials, unsupported TAN type, any auth-flow HTTP error |
| `TANTimeoutError` | Push-TAN not approved within `tan_timeout_seconds` |
| `SessionActivationError` | PATCH session activation failed (usually wrong header format) |
| `TokenExpiredError` | Access token expired AND refresh failed |
| `NetworkTimeoutError` | `httpx.TimeoutException` on any request |
| `AccountNotFoundError` | 404 on any banking / brokerage endpoint |
| `ValidationError` | 422 from the API (bad parameter values, unsupported paging, etc.) |
| `ServerError` | 500 from the API |
| `TokenStorageError` | Token file missing, corrupt, unreadable or unwritable |

The API returns structured `BusinessMessage` payloads on 422 errors (body + `x-http-response-info` header). Those are currently only surfaced via the exception message; see [`COMDIRECT_API.md`](COMDIRECT_API.md#businessmessage-error-format-pdf-14) for the full shape if you need to parse them yourself from a caught `ValidationError`.

---

## Persistent client pattern

Keep one `ComdirectClient` alive for the lifetime of your application. Destroying and recreating it each operation cancels the background refresh task and forces a new TAN every ~10 minutes.

### FastAPI example

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from comdirect_client import ComdirectClient

client: ComdirectClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = ComdirectClient(
        client_id=settings.COMDIRECT_CLIENT_ID,
        client_secret=settings.COMDIRECT_CLIENT_SECRET,
        username=settings.COMDIRECT_USERNAME,
        password=settings.COMDIRECT_PASSWORD,
        token_storage_path="/app/data/comdirect_tokens.json",
    )
    if not client.is_authenticated():
        await client.authenticate()
    yield
    await client.close()

app = FastAPI(lifespan=lifespan)

@app.get("/balances")
async def balances():
    return await client.get_account_balances()
```

### Long-running daemon

```python
async def main():
    async with ComdirectClient(
        ...,
        token_storage_path="tokens.json",
        reauth_callback=lambda reason: print(f"reauth needed: {reason}"),
    ) as client:
        if not client.is_authenticated():
            await client.authenticate()
        while True:
            balances = await client.get_account_balances()
            print(f"balance: {balances[0].balance.value} {balances[0].balance.unit}")
            await asyncio.sleep(3600)

asyncio.run(main())
```

---

## Running tests

```bash
poetry install --with dev
poetry run pytest
poetry run mypy comdirect_client
poetry run black --check comdirect_client tests examples
poetry run ruff check comdirect_client tests examples
```

96 unit tests covering auth state, token refresh, token storage, API parameter building, error mapping, remittance parsing with real captured samples, and the brokerage/messages/reports data classes. CI runs them on Python 3.9/3.10/3.11/3.12.

Live testing against the real comdirect API needs credentials in the environment (see the `test.sh` template). A full read-only validation run was recorded in the commit history and re-executed on every significant change.

---

## Project structure

```
comdirect_client/
├── __init__.py             — public exports
├── client.py               — ComdirectClient (facade + state + background refresh)
├── http_api.py             — low-level HTTP per endpoint (one function each)
├── auth_flow.py            — the 5-step auth as a plain async function
├── remittance.py           — verified 37/35-char remittanceInfo parser
├── models.py               — banking data classes + common types
├── models_brokerage.py     — Depot, DepotPosition, DepotTransaction, Order, ...
├── models_messages.py      — Document, DocumentMetadata
├── models_reports.py       — ProductBalance
├── token_storage.py        — atomic JSON token file
└── exceptions.py           — typed errors

tests/                      — 96 unit tests (no network)
examples/basic_usage.py     — end-to-end demo with real auth
COMDIRECT_API.md            — verified API notes, pitfalls, remittance spec
```

Files are organised by concern — `client.py` is the only stateful piece; everything else is either pure functions or pure data classes.

---

## Disclaimer and license

MIT-licensed. This is an unofficial client — not affiliated with Comdirect Bank AG. Use at your own risk, especially for order placement operations should you extend the library to cover those.

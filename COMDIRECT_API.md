# Comdirect API Authentication Flow - Complete Implementation Guide

This document provides a complete, step-by-step guide to implementing the Comdirect OAuth2 + TAN authentication flow from scratch.

## Overview

The Comdirect API uses a 5-step authentication process:
1. OAuth2 Password Credentials Grant
2. Session Status Retrieval
3. TAN Challenge Creation
4. TAN Approval Polling + Session Activation
5. Secondary Token Exchange

## Prerequisites

- **Client Credentials**: `client_id` and `client_secret` from Comdirect Developer Portal
- **User Credentials**: Comdirect username and password
- **TAN Method**: Push-TAN, Photo-TAN, or SMS-TAN configured on the account
- **Base URL**: `https://api.comdirect.de`

## Step-by-Step Implementation

### Step 1: OAuth2 Resource Owner Password Credentials

**Purpose**: Obtain initial access token with `TWO_FACTOR` scope.

**Endpoint**: `POST /oauth/token`

**Headers**:
```http
Accept: application/json
Content-Type: application/x-www-form-urlencoded
```

**Body** (form-urlencoded):
```
client_id={your_client_id}
client_secret={your_client_secret}
grant_type=password
username={comdirect_username}
password={comdirect_password}
```

**Response** (200 OK):
```json
{
  "access_token": "66f8fb19-93ce-46b8-8da8-57cffc9f714e",
  "token_type": "bearer",
  "refresh_token": "f6b5b626-37ce-42b7-81bd-e658026b03ae",
  "expires_in": 599,
  "scope": "TWO_FACTOR",
  "kdnr": "1234567890",
  "bpid": 12345678,
  "kontaktId": 1234567890
}
```

**Store**:
- `access_token` - Used for subsequent requests
- `refresh_token` - For token renewal

---

### Step 2: Session Status Retrieval

**Purpose**: Get the session UUID needed for TAN activation.

**Endpoint**: `GET /api/session/clients/user/v1/sessions`

**Headers**:
```http
Authorization: Bearer {access_token_from_step_1}
Accept: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{random_uuid}", "requestId": "{9_digit_number}"}}
```

**Header Details**:
- `sessionId`: Generate a random UUID (v4) at the start of authentication, keep it consistent throughout
- `requestId`: Last 9 digits of current timestamp in milliseconds

**Response** (200 OK):
```json
[
  {
    "identifier": "D235A5651B904595B28D3D283D187C81",
    "sessionTanActive": false,
    "activated2FA": false
  }
]
```

**Store**:
- `identifier` - This is the session UUID needed for Step 3

---

### Step 3: TAN Challenge Creation

**Purpose**: Trigger TAN challenge (Push-TAN, Photo-TAN, or SMS-TAN).

**Endpoint**: `POST /api/session/clients/user/v1/sessions/{session_uuid}/validate`

**Headers**:
```http
Authorization: Bearer {access_token_from_step_1}
Accept: application/json
Content-Type: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{same_session_id}", "requestId": "{new_9_digit_number}"}}
```

**Body**:
```json
{
  "identifier": "{session_uuid_from_step_2}",
  "sessionTanActive": true,
  "activated2FA": true
}
```

**Response** (201 Created):
```json
{
  "identifier": "D235A5651B904595B28D3D283D187C81",
  "sessionTanActive": true,
  "activated2FA": true
}
```

**Response Headers** (CRITICAL):
```http
x-once-authentication-info: {"id":"605497991","typ":"P_TAN_PUSH","availableTypes":["P_TAN_PUSH","P_TAN"],"link":{"href":"/api/session/v1/authentications/B33EA0DDE2234C8BA24927E6EEA5E3A1","rel":"related","method":"GET","type":"application/json"}}
```

**Parse and Store**:
```javascript
const authInfo = JSON.parse(response.headers['x-once-authentication-info']);

// Store these values:
const tanChallengeId = authInfo.id;              // "605497991"
const tanType = authInfo.typ;                     // "P_TAN_PUSH", "P_TAN", or "M_TAN"
const tanPollUrl = authInfo.link.href;           // "/api/session/v1/authentications/..."
const tanChallengeInfoFull = response.headers['x-once-authentication-info']; // Store the full header string
```

**TAN Types**:
- `P_TAN_PUSH`: Push-TAN (notification to smartphone app)
- `P_TAN`: Photo-TAN (display QR code to user)
- `M_TAN`: SMS-TAN (SMS to user's phone)

---

### Step 4: TAN Approval Polling

**Purpose**: Poll for TAN approval status.

**Endpoint**: `GET {tan_poll_url_from_step_3}`

Example: `GET /api/session/v1/authentications/B33EA0DDE2234C8BA24927E6EEA5E3A1`

**Headers**:
```http
Authorization: Bearer {access_token_from_step_1}
Accept: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{same_session_id}", "requestId": "{new_9_digit_number}"}}
```

**NO BODY** (this is a GET request)

**Polling Logic**:
```
WHILE elapsed_time < 60 seconds:
    WAIT 1 second
    SEND GET request to poll URL
    
    IF response.status == 200:
        PARSE response body
        
        IF body.status == "AUTHENTICATED":
            TAN approved, proceed to Step 4b
            BREAK
        
        ELSE IF body.status == "PENDING":
            Continue polling
        
        ELSE:
            Error, abort
    ELSE:
        Log warning, continue polling

IF timeout reached:
    Authentication failed, abort
```

**Response While Pending**:
```json
{
  "status": "PENDING"
}
```

**Response When Approved**:
```json
{
  "status": "AUTHENTICATED"
}
```

**Important Notes**:
- Poll **every 1 second** (not faster, not slower)
- Timeout after **60 seconds** (1 minute)
- Use GET request (not PATCH, not POST)
- No request body
- Generate a new `requestId` for each poll

---

### Step 4b: Session Activation (PATCH)

**Purpose**: Finalize session activation after TAN approval.

**Endpoint**: `PATCH /api/session/clients/user/v1/sessions/{session_uuid}`

**Headers**:
```http
Authorization: Bearer {access_token_from_step_1}
Accept: application/json
Content-Type: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{same_session_id}", "requestId": "{new_9_digit_number}"}}
x-once-authentication-info: {"id": "{tan_challenge_id_from_step_3}"}
```

**Header Details**:
- `x-once-authentication-info`: Send ONLY the challenge ID in format `{"id": "605497991"}`
- Do NOT send the full authentication info from Step 3

**Body**:
```json
{
  "identifier": "{session_uuid_from_step_2}",
  "sessionTanActive": true,
  "activated2FA": true
}
```

**Response** (200 OK):
```json
{
  "identifier": "D235A5651B904595B28D3D283D187C81",
  "sessionTanActive": true,
  "activated2FA": true
}
```

---

### Step 5: OAuth2 Secondary Flow

**Purpose**: Exchange the TAN-activated token for a banking operations token.

**Endpoint**: `POST /oauth/token`

**Headers**:
```http
Accept: application/json
Content-Type: application/x-www-form-urlencoded
```

**Body** (form-urlencoded):
```
client_id={your_client_id}
client_secret={your_client_secret}
grant_type=cd_secondary
token={access_token_from_step_1}
```

**Response** (200 OK):
```json
{
  "access_token": "e090557b-d845-4580-a383-22b794f1d513",
  "token_type": "bearer",
  "refresh_token": "2d14d46c-1fac-4dcb-8a43-3a2a1bcc40b3",
  "expires_in": 599,
  "scope": "BANKING_RW BROKERAGE_RW MESSAGES_RO REPORTS_RO SESSION_RW",
  "kdnr": "1234567890",
  "bpid": 12345678,
  "kontaktId": 1234567890
}
```

**Store**:
- `access_token` - **This is the token to use for all banking operations**
- `refresh_token` - For token renewal
- `scope` - Verify you have the required scopes (BANKING_RW, etc.)

---

## Token Refresh Mechanism

**IMPORTANT**: Access tokens have a limited lifetime specified in the `expires_in` field (typically 599 seconds / ~10 minutes). Before expiration, you must refresh both the access and refresh tokens to avoid re-authentication.

### Step 6: Token Refresh

**Purpose**: Renew access and refresh tokens before they expire, avoiding the need to restart the full authentication flow.

**Timing**: Refresh tokens some time before the `expires_in` period ends (e.g., 2 minutes before expiration or when API returns 401).

**Endpoint**: `POST /oauth/token`

**Headers**:
```http
Accept: application/json
Content-Type: application/x-www-form-urlencoded
```

**Body** (form-urlencoded):
```
client_id={your_client_id}
client_secret={your_client_secret}
grant_type=refresh_token
refresh_token={current_refresh_token_from_step_5}
```

**Example Body**:
```
client_id=zugewiesene_client_id
client_secret=zugewiesenes_client_secret
grant_type=refresh_token
refresh_token=1234567890_Refresh-Token__1234567890
```

**Response** (200 OK):
```json
{
  "access_token": "1234567890_Access-Token_NEU_34567890",
  "token_type": "bearer",
  "refresh_token": "1234567890_Refresh-Token_NEU_4567890",
  "expires_in": 599,
  "scope": "BANKING_RO BROKERAGE_RW SESSION_RW"
}
```

**Store**:
- `access_token` - **New access token for banking operations**
- `refresh_token` - **New refresh token for future refreshes**
- `expires_in` - Calculate next refresh time

**Error Handling**:
- **If refresh fails**: Restart full authentication flow from Step 1
- **If refresh times out**: Restart full authentication flow from Step 1
- **If token expired**: Restart full authentication flow from Step 1

**Best Practices**:
1. Set a timer to refresh tokens 1-2 minutes before expiration
2. Store token expiration timestamp: `current_time + expires_in`
3. Always update both access and refresh tokens after successful refresh
4. Implement automatic retry with full auth flow on refresh failure
5. Never use an expired refresh token (will fail)

**Refresh Logic Pseudocode**:
```
FUNCTION refreshTokenIfNeeded():
    current_time = now()
    token_expiry_time = stored_token_timestamp + stored_expires_in_seconds
    refresh_threshold = token_expiry_time - 120 seconds  # 2 minutes before expiry
    
    IF current_time >= refresh_threshold:
        success = attemptTokenRefresh()
        
        IF NOT success:
            # Refresh failed, restart full authentication
            success = performFullAuthentication()
        
        RETURN success
    
    RETURN true  # Token still valid

FUNCTION attemptTokenRefresh():
    response = POST /oauth/token with refresh_token grant
    
    IF response.status == 200:
        access_token = response.access_token
        refresh_token = response.refresh_token
        expires_in = response.expires_in  # Get from response!
        token_timestamp = now()
        token_expiry_time = now() + expires_in
        RETURN true
    ELSE:
        RETURN false
```

---

### Step 7: Revoke Token (Logout)

**Purpose**: Explicitly invalidate the current access + refresh token pair and the session-TAN. Use this on logout to release the server-side session cleanly instead of waiting for it to expire.

**Endpoint**: `DELETE /oauth/revoke`

**Headers**:
```http
Accept: application/json
Content-Type: application/x-www-form-urlencoded
Authorization: Bearer {access_token}
```

**Body**: empty

**Response**: `204 No Content` on success.

After a successful revoke, both the access token, refresh token, and the session-TAN are invalid — a subsequent API call must go through the full authentication flow again (Steps 1-5).

This endpoint is documented in PDF §3.1.2 but not covered by the Swagger. Not verified against the live API by this document's tests (to avoid invalidating the test session).

---

## Using the Banking Token

After Step 5, use the secondary access token for all banking API calls. **Remember to refresh tokens before they expire!**

### Example: Get Account Balances

**Endpoint**: `GET /api/banking/clients/user/v2/accounts/balances`

**Headers**:
```http
Authorization: Bearer {access_token_from_step_5}
Accept: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{same_session_id}", "requestId": "{new_9_digit_number}"}}
```

**Query Parameters** (optional):
- `without-attr=account` - Suppresses the inclusion of the account object in the response

**Response** (200 OK):
```json
{
    "paging": {
        "index": 0,
        "matches": 2
    },
    "values": [
        {
            "account": {
                "accountId": "B5A9F0C8B4214C019D0A6167C3190CC4",
                "accountDisplayId": "1234567890",
                "currency": "EUR",
                "clientId": "AA8DC7B7617147618C2B533EE0B38A9F",
                "accountType": {
                    "key": "CA",
                    "text": "Girokonto"
                },
                "iban": "DE89370400440532013000",
                "bic": "COBADEHD001",
                "creditLimit": {
                    "value": "1100",
                    "unit": "EUR"
                }
            },
            "accountId": "B5A9F0C8B4214C019D0A6167C3190CC4",
            "balance": {
                "value": "6860.09",
                "unit": "EUR"
            },
            "balanceEUR": {
                "value": "6860.09",
                "unit": "EUR"
            },
            "availableCashAmount": {
                "value": "7625.7",
                "unit": "EUR"
            },
            "availableCashAmountEUR": {
                "value": "7625.7",
                "unit": "EUR"
            }
        },
        {
            "account": {
                "accountId": "CEF00034159E45A1B640702A22632341",
                "accountDisplayId": "1234567891",
                "currency": "EUR",
                "clientId": "AA8DC7B7617147618C2B533EE0B38A9F",
                "accountType": {
                    "key": "DAS",
                    "text": "Tagesgeld PLUS-Konto"
                },
                "iban": "DE89370400440532013001",
                "bic": "COBADEHD001",
                "creditLimit": {
                    "value": "0",
                    "unit": "EUR"
                }
            },
            "accountId": "CEF00034159E45A1B640702A22632341",
            "balance": {
                "value": "0",
                "unit": "EUR"
            },
            "balanceEUR": {
                "value": "0",
                "unit": "EUR"
            },
            "availableCashAmount": {
                "value": "0",
                "unit": "EUR"
            },
            "availableCashAmountEUR": {
                "value": "0",
                "unit": "EUR"
            }
        }
    ]
}
```

**Response Structure**:

The response body contains a `values` array, where each item is an **AccountBalance** object:

**AccountBalance Object Fields**:
- `account` (Object) - Contains the master data for the account
- `accountId` (String) - **The unique UUID of the account** (use this for transaction queries)
- `balance` (AmountValue) - The current account balance (Saldo)
- `balanceEUR` (AmountValue) - The current account balance converted to EUR
- `availableCashAmount` (AmountValue) - The maximum available funds (balance + credit line - pending amounts)
- `availableCashAmountEUR` (AmountValue) - The maximum available funds converted to EUR

**Account Object Fields** (nested inside `account`):
- `accountId` (String) - The account's UUID
- `accountDisplayId` (String) - The account number (Kontonummer) for display
- `currency` (String) - The account's currency (e.g., "EUR")
- `clientId` (String) - The client's UUID
- `accountType` (EnumText) - The type of account
  - `key`: Account type code (e.g., "CA" = Girokonto, "DAS" = Tagesgeld PLUS-Konto)
  - `text`: Human-readable account type description
- `iban` (String) - The IBAN, if available
- `bic` (String) - The BIC/SWIFT code
- `creditLimit` (AmountValue) - The credit line, if available

**AmountValue Structure**:
```json
{
    "value": "1234.56",
    "unit": "EUR"
}
```

**Important Notes**:
- Always use `accountId` (UUID) from this response for subsequent transaction queries
- Example UUID: `B5A9F0C8B4214C019D0A6167C3190CC4`
- Do NOT use `accountDisplayId` for API calls

### Example: Get Transactions

**Endpoint**: `GET /api/banking/v1/accounts/{accountId}/transactions`

**Path Parameters**:
- `accountId`: The UUID from the account object (e.g., `B5A9F0C8B4214C019D0A6167C3190CC4`)

**Headers**:
```http
Authorization: Bearer {access_token_from_step_5}
Accept: application/json
x-http-request-info: {"clientRequestId": {"sessionId": "{same_session_id}", "requestId": "{new_9_digit_number}"}}
```

**Query Parameters**:

Documented in official Swagger:
- `transactionState={STATE}` - Filters transactions by booking status
  - `BOOKED` - Only booked transactions
  - `NOTBOOKED` - Only pending transactions
  - `BOTH` - Both booked and pending (default)
- `transactionDirection={DIRECTION}` - Filters transactions by direction
  - `CREDIT` - Only incoming transactions
  - `DEBIT` - Only outgoing transactions
  - `CREDIT_AND_DEBIT` - Both incoming and outgoing (default)
- `paging-first={INDEX}` - Zero-based index of the first transaction returned (default: 0). **See pagination rules below — only works with `transactionState=BOOKED`.**
- `with-attr=account` - Include the Account master-data object in the response

Undocumented but verified to work against the production API (verified 2026-04-11):
- `paging-count={COUNT}` - Page size (default: 20, **hard maximum: 500**). Values >500 return `422 paging.invalid`.
- `min-bookingDate={YYYY-MM-DD}` - Lower bound on `bookingDate`. **Also unlocks access to historical transactions** beyond the default ~6-month window.
- `max-bookingDate={YYYY-MM-DD}` - Upper bound on `bookingDate` (ISO date). Combine with `min-bookingDate` for a date-range query.

### Pagination rules (empirically verified)

These rules are **not** in the official PDF (April 2020) or Swagger — they were established by live testing:

1. **`paging-count` maximum is 500.** Values 501+ → `422 {code: request.query.invalid, key: paging.invalid}`.

2. **`paging-first > 0` requires `transactionState=BOOKED`.** Otherwise the API returns:
   ```json
   {
     "code": "request.query.invalid",
     "messages": [{
       "severity": "ERROR",
       "key": "requestparameter.invalid",
       "message": "Paging is only valid for booked account transactions",
       "origin": ["transactionState"]
     }]
   }
   ```
   (i.e. error applies to the `transactionState` parameter.)

3. **Default response window is limited.** Without `min-bookingDate`, the API appears to return only a recent slice (observed: ~6 months of data). Add `min-bookingDate=2020-01-01` (or any date older than the account) to unlock the full history.

4. **`matches` in the `paging` object is the authoritative total count** for the current filter. Use it to know when you've reached the end.

5. **Strategy to retrieve ALL transactions** (>500):
   ```
   transactionState=BOOKED
   min-bookingDate=<far_past>
   paging-count=500
   paging-first=0, 500, 1000, 1500, ...
   ```
   Stop when a page returns fewer than 500 rows (or 0). Pending (NOTBOOKED) transactions must be fetched separately in a single unpaged call, since pagination isn't allowed on them.

**Example requests** (tested against production):

```bash
# Default (returns only 20)
GET /api/banking/v1/accounts/{accountId}/transactions

# Up to 500 most recent transactions (within default window)
GET /api/banking/v1/accounts/{accountId}/transactions?paging-count=500

# Only pending transactions
GET /api/banking/v1/accounts/{accountId}/transactions?transactionState=NOTBOOKED

# Page 2 of booked transactions
GET /api/banking/v1/accounts/{accountId}/transactions?transactionState=BOOKED&paging-count=500&paging-first=500

# Date range query
GET /api/banking/v1/accounts/{accountId}/transactions?min-bookingDate=2025-06-01&max-bookingDate=2025-12-31&paging-count=500

# Full history walk (page 1 of N) — required to get >500 transactions
GET /api/banking/v1/accounts/{accountId}/transactions?transactionState=BOOKED&min-bookingDate=2020-01-01&paging-count=500&paging-first=0

# Fails with 422 ("Paging is only valid for booked account transactions")
GET /api/banking/v1/accounts/{accountId}/transactions?paging-first=20&paging-count=20

# Fails with 422 ("paging.invalid")
GET /api/banking/v1/accounts/{accountId}/transactions?paging-count=501
```

**Note**: Neither the PDF nor the Swagger documents `paging-count`, `min-bookingDate`, `max-bookingDate`, or the "paging requires BOOKED" rule — these were established through live testing. The parameters and behavior may change without notice.

**Response** (200 OK):
```json
{
    "paging": {
        "index": 0,
        "matches": 15
    },
    "values": [
        {
            "bookingStatus": "BOOKED",
            "bookingDate": "2025-11-05",
            "amount": {
                "value": "-25.99",
                "unit": "EUR"
            },
            "remitter": {
                "holderName": "John Doe",
                "iban": "DE89370400440532013000"
            },
            "creditor": {
                "holderName": "Example Merchant GmbH",
                "iban": "DE89370400440532013999"
            },
            "reference": "2025110512345678",
            "valutaDate": "2025-11-05",
            "transactionType": {
                "key": "TRANSFER",
                "text": "Transfer"
            },
            "remittanceInfo": "Example payment reference\nOrder 123-4567890-1234567",
            "newTransaction": false
        }
    ]
}
```

**Response Structure**:

The response body contains a `values` array, where each item is an **AccountTransaction** object:

**AccountTransaction Object Fields**:
- `bookingStatus` (String) - Status of the transaction: `BOOKED` or `NOTBOOKED`
- `bookingDate` (String, **optional**) - The booking date in YYYY-MM-DD format (null if not booked yet)
- `amount` (AmountValue, **optional**) - The transaction amount and currency (negative = outgoing, positive = incoming)
- `remitter` (AccountInformation, **optional**) - Account information for the remitter (sender)
- `debtor` (AccountInformation, **optional**) - Account information for the debtor (payer)
- `creditor` (AccountInformation, **optional**) - Account information for the creditor (recipient)
- `reference` (String) - A unique reference number for this transaction
- `endToEndReference` (String) - The end-to-end reference, if it is a direct debit
- `valutaDate` (String) - The valuta date of the transaction (value date)
- `directDebitCreditorId` (String) - The creditor ID, if it is a direct debit
- `directDebitMandateId` (String) - The mandate reference, if it is a direct debit
- `transactionType` (EnumText, **optional**) - The category of the transaction, as `{key, text}` where `text` is English despite what the German-language PDF suggests. Keys observed on a live Girokonto (verified 2026-04-11, not an exhaustive list):
  - `TRANSFER` → "Transfer"
  - `DIRECT_DEBIT` → "Direct Debit"
  - `CARD_TRANSACTION` → "Card transaction"
  - `BANK_FEES` → "Bank fees"
  - `MISCELLANEOUS` → "Miscellaneous"
  - Other keys are likely (e.g. for standing orders, interest, securities) but were not observed in the sample account. The April 2020 PDF §4.2.3 lists the German-language categories these keys correspond to (`Überweisung`, `Lastschrift`, `Kartenverfügung`, `Bankgebühren`, `Sonstiges`, `Sparplan`, `Wertpapier`, `Dauerauftrag`, `Zinsen / Dividenden`, etc.), but does not publish the actual key identifiers — match on `key`, not `text`.
- `remittanceInfo` (String, **optional**) - The booking text (Verwendungszweck). Despite what the April-2020 PDF says ("separated by `\n`"), the real API returns **no newlines at all** — it is a single flat string with fixed-width chunks. See the dedicated **`remittanceInfo` parsing** section below for the full splitting algorithm.
- `newTransaction` (Boolean) - Indicates if this transaction has already been seen by the customer in the web interface

**AccountInformation Structure**:
```json
{
    "holderName": "John Doe",
    "iban": "DE89370400440532013000",  // Optional - may be null
    "bic": "COBADEHD001"  // Optional - may be null
}
```

**Important Notes About Optional Fields**:
- **Many fields can be `null`** in real API responses, even if they seem required in documentation
- The following fields are **optional** and may be `null`:
  - `amount` - Null for some transaction types
  - `transactionType` - Null for certain transactions
  - `remittanceInfo` - Null if no purpose text was provided
  - `bookingDate` - Null for pending (NOTBOOKED) transactions
  - `remitter`, `debtor`, `creditor` - May be null or have null `iban`/`bic` fields
- Always check for `null` values before accessing nested fields

**Important Notes**:
- Use `accountId` (UUID) from the balances endpoint, NOT the display ID
- The accountId is found in `values[].account.accountId` or `values[].accountId` from the balances response
- Example UUID: `B5A9F0C8B4214C019D0A6167C3190CC4`
- Transaction amounts are negative for outgoing payments, positive for incoming
- `remittanceInfo` contains a flat fixed-width string — see parsing rules below
- Use `newTransaction` to identify transactions the user hasn't seen yet

**Token Management**:
- Check token expiration before each API call
- Refresh token automatically if close to expiration
- Handle 401 Unauthorized errors by refreshing or re-authenticating

---

## `remittanceInfo` parsing (Verwendungszweck)

**Verified 2026-04-11** against the live comdirect online banking web app (via Playwright) by cross-checking real transactions against their displayed detail view. The April-2020 PDF §4.2.3 description is misleading on two points: there are no `\n` separators, and the "35-character line width" rule is more nuanced than documented.

### The flat-string format

`remittanceInfo` is always a **single flat string without any `\n` characters**, regardless of how many "lines" the underlying text has. The API encodes line structure by fixed-width windows:

| `bookingStatus` | Window width | Content per window | Structure |
|---|---|---|---|
| `BOOKED` | **37 chars** | 2-digit marker (`01`, `02`, …, `10`, …) + 35 content chars | Chunked, markered |
| `NOTBOOKED` | **35 chars** | 35 content chars, no marker | Chunked, unmarkered |

The total length of `remittanceInfo` is always an exact multiple of the window width. Content in each window is **right-padded with ASCII spaces** to fill the window. Markers zero-pad to 2 digits and run sequentially from `01`.

Example (booked, 6 × 37 = 222 chars, merchant name wraps mid-word across windows 01 → 02):

```
01AMZN Mktp DE*NI22A6FP4, AMZN.COM BI02LL  LU                             03Karte Nr. 4871 78XX XXXX 3636      04Kartenzahlung                      05comdirect Visa-Debitkarte          062026-04-07 00:00:00                
```

Example (pending, 2 × 35 = 70 chars):

```
JET-Tankstelle Wuppertal DEU       2026-04-11T13:31:08                
```

### Per-chunk normalization

Each chunk's content (after dropping the 2-char marker for booked transactions) must be normalized using whitespace collapsing. The comdirect web UI uses the equivalent of Python's `" ".join(content.split())` — this:

1. Strips all leading and trailing whitespace from the chunk
2. Collapses runs of internal whitespace to a **single** ASCII space
3. Handles the edge case of chunks that start with a space (e.g. when a word wraps and the next window begins with ` Pty Ltd`)

This was verified on Sample `#16` chunk 02: the raw API bytes are `'LL  LU                             '` (two internal spaces before the trailing padding) but the web UI's DOM `textContent` is `'LL LU'` with a single space. `rstrip()` alone is **not sufficient** — you must collapse.

### Chunks are NEVER concatenated across windows

Even when a word is wrapped mid-character across two chunks (e.g. `…AMZN.COM BI` + `LL LU` for `AMZN.COM BILL LU`), the web UI renders them as **two separate lines** separated by `<br>`. Do not try to reassemble wrapped words into a single string — the bank itself doesn't, and any naive concatenation would either double-space (if you rstripped) or lose the space (if you didn't). Leave them as separate list entries and let the caller decide how to display them.

### SEPA label extraction (booked transactions only)

For booked transactions, the web UI parses out structured SEPA metadata fields. When a normalized chunk content **exactly matches** one of the label strings below, that chunk AND the following chunk are consumed from the Buchungstext, and the following chunk's content is displayed in a dedicated field:

| Normalized chunk content | Web UI field label | Semantic key |
|---|---|---|
| `End-to-End-Ref.:` | "End-To-End-Referenz" | end-to-end reference |
| `CORE / Mandatsref.:` | "Mandatsreferenz" (label prefix `CORE /` dropped) | mandate reference |
| `Gläubiger-ID:` | "Gläubiger-Identifikationsnummer" | creditor identifier |

Untested but probable (based on SEPA scheme variants): `COR1 / Mandatsref.:` and `B2B / Mandatsref.:` likely work the same way as `CORE /`. No non-CORE samples appeared in 449 tested transactions.

Chunks **before** the first SEPA label, and any chunks that are not labels or label-values, stay in the Buchungstext as ordinary lines. This means card-transaction trailer chunks (`Karte Nr. 4871 78XX XXXX 3636`, `Kartenzahlung`, `comdirect Visa-Debitkarte`, `YYYY-MM-DD HH:MM:SS`) are **part of the Buchungstext**, not separate fields — the web UI just shows them as additional Buchungstext lines.

### Reference implementation

```python
SEPA_LABELS = {
    "End-to-End-Ref.:":     "end_to_end_reference",
    "CORE / Mandatsref.:":  "mandate_reference",
    "COR1 / Mandatsref.:":  "mandate_reference",  # assumed, untested
    "B2B / Mandatsref.:":   "mandate_reference",  # assumed, untested
    "Gläubiger-ID:":        "creditor_id",
}


def _normalize(chunk_content: str) -> str:
    """Strip + collapse runs of internal whitespace to single spaces."""
    return " ".join(chunk_content.split())


def parse_remittance_info(remittance_info: str | None, booking_status: str) -> dict:
    """Parse comdirect remittanceInfo into Buchungstext lines + SEPA fields.

    Returns a dict:
        {
            "buchungstext_lines": list[str],   # lines shown under "Buchungstext"
            "end_to_end_reference": str | None,
            "mandate_reference": str | None,
            "creditor_id": str | None,
        }
    """
    out: dict = {
        "buchungstext_lines": [],
        "end_to_end_reference": None,
        "mandate_reference": None,
        "creditor_id": None,
    }
    if not remittance_info:
        return out

    if booking_status == "BOOKED":
        # 37-char windows: 2-digit marker + 35-char content
        chunks: list[str] = []
        for i in range(0, len(remittance_info), 37):
            window = remittance_info[i:i + 37]
            if len(window) >= 2 and window[:2].isdigit():
                chunks.append(window[2:])
            else:
                # Anomaly — e.g. len=3 "01 " seen once, treat the trailing
                # substring after position 2 (possibly empty) as the content
                chunks.append(window[2:] if len(window) >= 2 else "")

        idx = 0
        while idx < len(chunks):
            norm = _normalize(chunks[idx])
            if norm in SEPA_LABELS and idx + 1 < len(chunks):
                out[SEPA_LABELS[norm]] = _normalize(chunks[idx + 1])
                idx += 2
                continue
            if norm:
                out["buchungstext_lines"].append(norm)
            idx += 1
    else:  # NOTBOOKED — 35-char windows, no markers, no SEPA extraction
        for i in range(0, len(remittance_info), 35):
            norm = _normalize(remittance_info[i:i + 35])
            if norm:
                out["buchungstext_lines"].append(norm)

    return out
```

### Verified test cases

Cross-checked against the comdirect online banking web UI for the account under test. Raw API bytes on the left; DOM `textContent` on the right (each line is a separate `<span>` with `<br>` between them in the web UI). Checkmark means the algorithm above produces the same split.

| # | Type / raw length | API `remittanceInfo` (repr) | Web UI "Buchungstext" lines + SEPA fields | ✓ |
|---|---|---|---|---|
| 7 | TRANSFER / 111 | `01OBK509157898` `02End-to-End-Ref.:` `03td5txib5a51a530cc9408d` | **Buchungstext:** `OBK509157898` **End-To-End-Referenz:** `td5txib5a51a530cc9408d` | ✓ |
| 12 | BANK_FEES / 148 | `01Entgelt` `02Visa-Kreditkarte` `03Zeitraum: 01.03.2026` `04bis 31.03.2026` | **Buchungstext:** `Entgelt` / `Visa-Kreditkarte` / `Zeitraum: 01.03.2026` / `bis 31.03.2026` | ✓ |
| 16 | CARD_TRANSACTION / 222 | `01AMZN Mktp DE*NI22A6FP4, AMZN.COM BI` `02LL  LU` `03Karte Nr. 4871 78XX XXXX 3636` `04Kartenzahlung` `05comdirect Visa-Debitkarte` `062026-04-07 00:00:00` | **Buchungstext (6 lines):** `AMZN Mktp DE*NI22A6FP4, AMZN.COM BI` / `LL LU` / `Karte Nr. 4871 78XX XXXX 3636` / `Kartenzahlung` / `comdirect Visa-Debitkarte` / `2026-04-07 00:00:00` — note the `LL  LU` → `LL LU` whitespace collapse | ✓ |
| 17 | DIRECT_DEBIT / 222 | `01B+B PARKHAUS GMBH & CO, WUPPERTAL` `02DE` `03Karte Nr. 4871 78XX XXXX 7657` `04Kartenzahlung` `05comdirect Visa-Debitkarte` `062026-04-01 00:00:00` | **Buchungstext (6 lines):** `B+B PARKHAUS GMBH & CO, WUPPERTAL` / `DE` / `Karte Nr. 4871 78XX XXXX 7657` / `Kartenzahlung` / `comdirect Visa-Debitkarte` / `2026-04-01 00:00:00` — chunks are NOT concatenated even though the merchant continues on line 02 | ✓ |
| 20 | DIRECT_DEBIT / 296 | `011049447148633/PP.7320.PP/. drunkens` `02lug, Ihr Einkauf bei drunkenslug` `03End-to-End-Ref.:` `041049447148633` `05CORE / Mandatsref.:` `064LHJ2255C8KDN` `07Gläubiger-ID:` `08LU96ZZZ0000000000000000058` | **Buchungstext:** `1049447148633/PP.7320.PP/. drunkens` / `lug, Ihr Einkauf bei drunkenslug` **End-To-End-Referenz:** `1049447148633` **Mandatsreferenz:** `4LHJ2255C8KDN` **Gläubiger-Identifikationsnummer:** `LU96ZZZ0000000000000000058` | ✓ |

### Common pitfalls to avoid

1. **Do not call `.rstrip()` alone** — you will miss internal whitespace collapsing (`LL  LU` vs `LL LU`).
2. **Do not reassemble word-wrapped chunks** — the web UI doesn't, and reassembly is ambiguous because you can't tell whether the break was intentional.
3. **Do not promote the card trailer** (`Karte Nr. …`, `Kartenzahlung`, card product, timestamp) to separate fields — the web UI leaves them in Buchungstext.
4. **Do not assume `\n` separators.** The PDF is wrong on this.
5. **Markers can be > `09`** — tested up to `10` (Sample 23, Detlev Louis). Treat markers as the first 2 digits of each 37-char window, not as a 1-digit value. Chunks beyond `99` are theoretically possible but untested.
6. **NOTBOOKED pagination doesn't exist**, and NOTBOOKED transactions are not expandable in the web UI. There's no "detail view" to cross-check against for pending transactions, so the 35-char no-marker rule is inferred from the raw API only.

### Untested edge cases

- Marker values above `10` (need a transaction with very long remittance info — not present in 449-sample test account)
- `COR1 / Mandatsref.:` and `B2B / Mandatsref.:` variants (non-CORE direct debits)
- Foreign-currency transfers (all test samples were EUR)
- Standing orders, salary credits, interest/dividend bookings (not present in test account)
- Markers skipping (e.g. `01`, `02`, `04` with no `03`) — never observed

---

## Common Pitfalls and Solutions

### 1. Wrong Polling Endpoint
**Error**: Always getting 422 on PATCH requests during polling
**Solution**: Use the polling URL from `x-once-authentication-info` header's `link.href` field, NOT the session endpoint

### 2. Wrong Polling Method
**Error**: 422 "UNPROCESSABLE_ONCE_AUTHENTICATION_INFO_HEADER"
**Solution**: Use GET request for polling (Step 4), not PATCH

### 3. Wrong Header Format in Step 4b
**Error**: 422 "UNPROCESSABLE_ONCE_AUTHENTICATION_INFO_HEADER" on session activation
**Solution**: Send only `{"id": "challenge_id"}` in `x-once-authentication-info` header, not the full JSON from Step 3

### 4. Polling Too Fast or Too Slow
**Error**: Rate limiting or timeout
**Solution**: Poll exactly every 1 second, timeout after 60 seconds

### 5. Missing x-http-request-info Header
**Error**: 400 Bad Request
**Solution**: Include this header in ALL requests after Step 1, with same sessionId throughout

### 6. Request ID Format
**Error**: Various 400 errors
**Solution**: Request ID must be exactly 9 digits. Use last 9 digits of timestamp in milliseconds

### 7. Token Expiration
**Error**: 401 Unauthorized on banking operations
**Solution**: Token expired - refresh token using Step 6, or restart full authentication if refresh fails

### 8. Refresh Token Expired
**Error**: 401 on token refresh endpoint
**Solution**: Refresh token also expired - restart full authentication flow from Step 1

### 9. Online banking lockout from TAN abuse
**Warning** (PDF §2.3, §2.4):
- Requesting **five TAN challenges** (Step 3) without approving one in between locks the online banking access.
- **Three incorrect TAN entries** in Step 4b lock the online banking access. After two incorrect entries, a correct TAN entry via the comdirect website clears the counter.

**Solution**: Abort retry loops after a single failure, let the user re-request rather than repeatedly polling new challenges, and never auto-retry TAN submission with the same (possibly wrong) TAN.

### 10. Pagination on NOTBOOKED transactions
**Error**: 422 `{"key": "requestparameter.invalid", "message": "Paging is only valid for booked account transactions", "origin": ["transactionState"]}`
**Solution**: `paging-first > 0` only works with `transactionState=BOOKED`. Fetch pending transactions in a single unpaged call (`transactionState=NOTBOOKED`), paginate only the booked history.

### 11. Document download requires a matching `Accept` header
**Error**: `406 Not Acceptable` from `GET /api/messages/v2/documents/{documentId}` and `…/predocument` when the default `Accept: application/json` header is sent.

**Why**: These endpoints return binary content (`text/html` or `application/pdf`) — the official Swagger declares `produces: ["text/html", "application/pdf"]` with no JSON option. The API enforces content negotiation and rejects any request that does not advertise a matching Accept value.

**Solution**: Set `Accept` to the actual MIME type you want (or the comma-separated list of both) before calling the endpoint:

```http
Accept: application/pdf, text/html
```

Source: the official `comdirect_rest_api_swagger.json` declares the `produces` list; the 406 behaviour is reported by devmapal's fork of the Python library based on live API experience (see commit `9db8b65`). Not reproduced by our own live testing yet — the mapping to 406 specifically is the fork author's observation rather than documented elsewhere.

---

## Brokerage date / timestamp filter conventions

The banking and brokerage modules use different date formats for range filters. This is inconsistent across the API and is not spelled out in a single place in the official docs — collected here from the official Swagger's parameter descriptions.

| Endpoint | Parameter | Format | Example |
|---|---|---|---|
| `GET /api/banking/v1/accounts/{accountId}/transactions` | `min-bookingDate`, `max-bookingDate` | ISO date `YYYY-MM-DD` | `2025-06-01` |
| `GET /api/brokerage/v3/depots/{depotId}/transactions` | `min-bookingDate`, `max-bookingDate` | ISO date **or** negative offset string | `2025-06-01` **or** `-10d` (meaning "last 10 days") |
| `GET /api/brokerage/depots/{depotId}/v3/orders` | `min-creationTimeStamp`, `max-creationTimeStamp` | UTC timestamp `YYYY-MM-DDThh:mm:ss,ff` | `2026-04-11T18:37:11,55` |
| `GET /api/messages/clients/{user}/v2/documents` | `min-documentDate`, `max-documentDate` | ISO date `YYYY-MM-DD` | `2025-06-01` |

**Source**: the corresponding `parameters[].description` fields in `comdirect_rest_api_swagger.json` (quoted verbatim: *"in UTC with the following format: YYYY-MM-DDThh:mm:ss,ff"*, *"Earliest booking date of the transaction. Format: YYYY-MM-DD or as negative offset from the current date e.g. -10d"*). Not verified against live API calls by this document's tests — file a correction PR if you hit deviations.

---

## State Management

Throughout the authentication flow, maintain these values:

```javascript
// Generate once at start, reuse throughout
const sessionId = generateUUID(); // e.g., "d44c2d9b-e799-407d-a723-a2c844dddad6"

// Function to generate new request ID for each API call
function generateRequestId() {
    const timestamp = Date.now().toString(); // e.g., "1699615696255445"
    return timestamp.slice(-9); // Last 9 digits: "696255445"
}

// Store throughout flow
let accessTokenStep1;           // From Step 1
let refreshTokenStep1;          // From Step 1
let sessionUuid;                // From Step 2
let tanChallengeId;             // From Step 3
let tanType;                    // From Step 3
let tanPollUrl;                 // From Step 3
let tanChallengeInfoFull;       // From Step 3 (full header string)
let accessTokenFinal;           // From Step 5 - USE THIS FOR BANKING
let refreshTokenFinal;          // From Step 5 - USE FOR TOKEN REFRESH
let tokenExpiryTimestamp;       // Calculate: now() + expires_in
```

---

## Error Handling

### Common HTTP Error Codes

- **401 Unauthorized**: Invalid credentials or expired token
- **422 Unprocessable Entity**: Wrong header format, invalid parameter value, or expired TAN challenge
- **404 Not Found**: Wrong endpoint or account doesn't exist (often returns an empty body — see BusinessMessage section)

### BusinessMessage error format (PDF §1.4)

On most errors (typically `422`), the API returns a structured `BusinessMessage` both in the response body AND duplicated in the `x-http-response-info` response header. This was verified on 2026-04-11 against the production API.

**Body shape on error**:
```json
{
  "code": "request.query.invalid",
  "messages": [
    {
      "severity": "ERROR",
      "key": "paging.invalid",
      "message": "Der Paging-Parameter {0} mit dem Wert {1} ist ungültig",
      "args": {"0": "paging-count", "1": 501},
      "origin": ["paging-count"]
    }
  ]
}
```

**Same content in response header `x-http-response-info`** (URL-decoded):
```
{"messages":[{"severity":"ERROR","key":"bookingStatus.invalid","message":"The value {0} for the bookingStatus is invalid","args":{"0":"NOTAVALIDSTATE"},"origin":["transactionState"]}]}
```

Field semantics:
- `severity`: `ERROR`, `WARN`, or `INFO`. Warnings/info can accompany a 200 response; errors replace the body.
- `key`: stable machine-readable identifier — **branch logic on this, not on the German `message`**.
- `message`: default display text, may contain `{0}`, `{1}` placeholders already filled from `args`. Comdirect sends messages in German by default.
- `args`: map of placeholder values used in `message`.
- `origin`: array of field names the error refers to (e.g. `["transactionState"]`). Useful for mapping errors to specific form fields.

**Known error keys** (observed):
- `paging.invalid` — `paging-count` outside allowed range (>500)
- `requestparameter.invalid` — e.g. `paging-first > 0` without `transactionState=BOOKED` (origin: `transactionState`)
- `bookingStatus.invalid` — `transactionState` has an unrecognized value

**Caveat**: Not every error populates the `x-http-response-info` header or the structured body. Some `404 Not Found` responses (e.g. unknown `accountId`) return an empty body and no `x-http-response-info` header — fall back to the HTTP status code in that case.

### TAN Challenge Errors

If Step 3 or 4 fails:
1. Check if TAN method is configured on the account
2. Verify user has approved TAN in their app/SMS
3. Check if TAN challenge expired (recreate from Step 3)

### Token Expiration and Refresh

- Step 1 token has a limited lifetime specified in the `expires_in` response field (typically ~10 minutes)
- Step 5 token also has a limited lifetime specified in the `expires_in` response field (typically ~10 minutes)
- **IMPORTANT**: Always read `expires_in` from the token response - do not hardcode the duration
- **IMPORTANT**: Use Step 6 (Token Refresh) to renew tokens before expiration
- If refresh fails or token already expired, restart full authentication from Step 1

**Token Lifecycle**:
1. After Step 5: Token valid for `expires_in` seconds (from response)
2. Before expiration: Refresh token using Step 6 (recommended: 2 minutes before `expires_in`)
3. Token refreshed: New token with new `expires_in` validity period
4. Repeat refresh cycle to maintain continuous access
5. If refresh fails: Restart full authentication

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: OAuth2 Password Credentials                         │
│ POST /oauth/token                                            │
│ ↓                                                            │
│ Response: access_token (TWO_FACTOR scope)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Step 2: Session Status                                       │
│ GET /api/session/clients/user/v1/sessions                   │
│ ↓                                                            │
│ Response: session_uuid                                       │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Step 3: TAN Challenge Creation                               │
│ POST /api/session/.../sessions/{uuid}/validate              │
│ ↓                                                            │
│ Response Header: x-once-authentication-info                  │
│   - Extract: tanChallengeId, tanType, tanPollUrl            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Step 4: TAN Approval Polling (1 second interval)            │
│ GET {tanPollUrl}                                             │
│ ↓                                                            │
│ Poll until: {"status": "AUTHENTICATED"}                     │
│ Timeout: 60 seconds                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Step 4b: Session Activation                                  │
│ PATCH /api/session/.../sessions/{uuid}                      │
│ Header: x-once-authentication-info: {"id": "{challengeId}"} │
│ ↓                                                            │
│ Response: 200 OK, session activated                          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Step 5: OAuth2 Secondary Flow                                │
│ POST /oauth/token                                            │
│ grant_type=cd_secondary                                      │
│ ↓                                                            │
│ Response: access_token (BANKING_RW scope) + refresh_token   │
│ Store: tokenExpiryTimestamp = now() + expires_in            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
               ┌──────────────────────────────────────┐
               │ Banking Operations                 │
               │ - Get Account Balances (v2)        │◄────────────┐
               │ - Get Transactions (per accountId) │             │
               └──────────┬─────────────────────────┘             │
                         │                         │
                         │ Token expires soon?     │
                         ▼                         │
              ┌──────────────────────┐             │
              │ Step 6: Token Refresh│             │
              │ POST /oauth/token    │             │
              │ grant_type=          │             │
              │   refresh_token      │             │
              │ ↓                    │             │
              │ Success: New tokens  ├─────────────┘
              │ Failure: Restart     │
              │   from Step 1        │
              └──────────────────────┘
```

---

## Security Considerations

1. **Never log passwords or tokens in production**
2. **Store credentials encrypted** (use Fernet, AES-256, or similar)
3. **Use HTTPS only** for all API requests
4. **Implement token refresh** before expiration
5. **Clear tokens on logout** or error
6. **Rate limit retry attempts** to avoid account lockout
7. **Validate TAN challenge expiration** and recreate if needed
8. **Use secure random UUID generation** for session IDs

---

## Testing

### Test with Comdirect Sandbox

1. Register at https://developer.comdirect.de/
2. Get sandbox credentials
3. Use sandbox base URL: `https://api-sandbox.comdirect.de`
4. Note: Sandbox may not support all TAN types

### Test TAN Types

- **Push-TAN**: Most common, requires smartphone app
- **Photo-TAN**: Requires displaying QR code to user
- **SMS-TAN**: Requires user to input code from SMS

---

## Implementation Checklist

- [ ] Step 1: OAuth2 password credentials implemented
- [ ] Step 2: Session status retrieval implemented
- [ ] Step 3: TAN challenge creation implemented
- [ ] Step 3: Parse `x-once-authentication-info` header correctly
- [ ] Step 4: GET polling on correct URL (from header link.href)
- [ ] Step 4: Poll every 1 second, timeout after 60 seconds
- [ ] Step 4: Check for `status: "AUTHENTICATED"` in response
- [ ] Step 4b: PATCH session activation with correct header format
- [ ] Step 5: Secondary token exchange implemented
- [ ] Step 6: Token refresh mechanism implemented
- [ ] Token expiry tracking (store timestamp + expires_in from response)
- [ ] Automatic token refresh before expiration
- [ ] Fallback to full auth if refresh fails
- [ ] Error handling for all steps
- [ ] Secure credential storage
- [ ] Logging (without sensitive data)
- [ ] Unit tests for each step
- [ ] Integration tests for full flow

---

## References

- Comdirect Developer Portal: https://developer.comdirect.de/
- OAuth 2.0 RFC: https://tools.ietf.org/html/rfc6749
- Postman Collection: Available from Comdirect Developer Portal

---

## Changelog

- **2026-04-11**: Cross-checked against the official `comdirect_REST_API_Dokumentation.pdf` (April 2020) and `comdirect_rest_api_swagger.json`, plus live testing against the production API and live comparison with the comdirect online banking web UI via Playwright:
  - **Added full `remittanceInfo` parsing section**: Verwendungszweck is a flat fixed-width string with no newlines, despite what the PDF says. Booked transactions use 37-char windows with 2-digit markers; pending transactions use 35-char unmarkered windows. Per-chunk normalization is `" ".join(content.split())` (full whitespace collapse, not just `rstrip`). SEPA labels (`End-to-End-Ref.:`, `CORE / Mandatsref.:`, `Gläubiger-ID:`) trigger structured extraction in the web UI and should be extracted the same way programmatically. Chunks are NEVER concatenated across windows, even when a word is wrapped mid-character. Includes reference Python implementation and 5 verified test cases.
  - **Corrected `transactionType.key` values**: actual keys are `TRANSFER`, `DIRECT_DEBIT`, `CARD_TRANSACTION`, `BANK_FEES`, `MISCELLANEOUS` (not `SEPA_CREDIT_TRANSFER` / `SEPA_DIRECT_DEBIT` / `STANDING_ORDER` as previously documented). `text` field is English, not German.
  - **Discovered pagination rule**: `paging-first > 0` requires `transactionState=BOOKED`. Otherwise returns 422 `"Paging is only valid for booked account transactions"`.
  - **Discovered >500 transaction strategy**: combine `transactionState=BOOKED`, `min-bookingDate=<far_past>`, and walk `paging-first=0,500,1000,...`. Successfully retrieved 2168 transactions across 5 pages in testing.
  - **Confirmed `paging-count` hard max of 500**: values ≥501 return 422 `paging.invalid`.
  - **Confirmed `min-bookingDate` and `max-bookingDate` both work** on account transactions, though neither is in the Swagger. `min-bookingDate` also unlocks history beyond the default ~6-month window.
  - **Added BusinessMessage error handling section** covering `x-http-response-info` header and response body structure (PDF §1.4), with observed error keys.
  - **Added Step 7: Revoke token** (`DELETE /oauth/revoke`) from PDF §3.1.2.
  - **Added TAN lockout warnings**: five challenges → lockout, three wrong TAN entries → lockout (PDF §2.3 / §2.4).
  - **Removed unverified `deptor` vs `debtor` typo note**: live responses consistently use `debtor`.
  - Labeled empirically-derived features (paging-count max, min/max-bookingDate, polling endpoint) as "not in official spec" so readers know the provenance.

- **2025-11-09**: Initial version based on successful implementation
  - Fixed TAN polling to use GET on correct endpoint
  - Fixed session activation header format
  - Fixed polling interval to 1 second
  - Added Step 6: Token Refresh mechanism
  - Updated account retrieval to use v2 balances endpoint
  - Clarified transaction endpoint requires accountId UUID
  - Added comprehensive response structure documentation
  - Added detailed field descriptions for AccountBalance and AccountTransaction objects
  - Added all query parameters for balances and transactions endpoints
  - **Documented optional fields**: Many Transaction fields (`amount`, `transactionType`, `remittanceInfo`, `bookingDate`, account information objects) can be `null` in real API responses
  - Added safe parsing guidance for optional fields

---

## Support

For issues with the Comdirect API:
- Check Comdirect Developer Portal documentation
- Contact Comdirect API support
- Review your API credentials and permissions

For implementation issues:
- Verify all headers are correctly formatted
- Check request/response logs for each step
- Ensure TAN method is configured on the account
- Verify timing (1 second polling, 60 second timeout)

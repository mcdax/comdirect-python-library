"""Tests for :mod:`comdirect_client.remittance`.

Test data is taken from real live API responses captured on 2026-04-11 and
cross-checked against the comdirect online banking web UI. Each sample name
refers to the numbered samples in ``COMDIRECT_API.md`` §"`remittanceInfo`
parsing (Verwendungszweck)".
"""

from comdirect_client.remittance import parse


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_none_returns_empty() -> None:
    result = parse(None, "BOOKED")
    assert result.buchungstext_lines == []
    assert result.end_to_end_reference is None
    assert result.mandate_reference is None
    assert result.creditor_id is None


def test_empty_string_returns_empty() -> None:
    assert parse("", "BOOKED").buchungstext_lines == []


def test_empty_booked_purpose_marker_only() -> None:
    """Sample 1 — anomalous 3-char payload ``'01 '`` seen in the wild."""
    result = parse("01 ", "BOOKED")
    assert result.buchungstext_lines == []


# ---------------------------------------------------------------------------
# Short (sub-window) booked payloads — used as smoke tests; still work
# because a single partial window is still parsed as chunk 01.
# ---------------------------------------------------------------------------


def test_short_booked_single_line() -> None:
    result = parse("01Payment for services rendered", "BOOKED")
    assert result.buchungstext_lines == ["Payment for services rendered"]


# ---------------------------------------------------------------------------
# Real samples from the live API (verified against web UI)
# ---------------------------------------------------------------------------


def test_sample_7_transfer_with_end_to_end_ref() -> None:
    """Sample #7 — IBKR transfer, 3 × 37-char windows.

    Web UI shows Buchungstext = ``OBK509157898`` and the SEPA label
    ``End-to-End-Ref.:`` is extracted into its own field.
    """
    raw = (
        "01OBK509157898                       "
        "02End-to-End-Ref.:                   "
        "03td5txib5a51a530cc9408d             "
    )
    result = parse(raw, "BOOKED")
    assert result.buchungstext_lines == ["OBK509157898"]
    assert result.end_to_end_reference == "td5txib5a51a530cc9408d"
    assert result.mandate_reference is None
    assert result.creditor_id is None


def test_sample_12_bank_fees_four_lines_no_sepa() -> None:
    """Sample #12 — monthly fee breakdown, 4 × 37-char windows, no labels."""
    raw = (
        "01Entgelt                            "
        "02Visa-Kreditkarte                   "
        "03Zeitraum: 01.03.2026               "
        "04bis 31.03.2026                     "
    )
    result = parse(raw, "BOOKED")
    assert result.buchungstext_lines == [
        "Entgelt",
        "Visa-Kreditkarte",
        "Zeitraum: 01.03.2026",
        "bis 31.03.2026",
    ]


def test_sample_16_card_transaction_collapses_double_space() -> None:
    """Sample #16 — Amazon card transaction, 6 × 37-char windows.

    Verifies two critical behaviours:
    * chunks are NOT concatenated across windows (merchant wraps from
      ``AMZN.COM BI`` into ``LL LU`` on the next line)
    * the raw double-space in ``'LL  LU'`` collapses to a single space
    """
    raw = (
        "01AMZN Mktp DE*NI22A6FP4, AMZN.COM BI"
        "02LL  LU                             "
        "03Karte Nr. 4871 78XX XXXX 3636      "
        "04Kartenzahlung                      "
        "05comdirect Visa-Debitkarte          "
        "062026-04-07 00:00:00                "
    )
    result = parse(raw, "BOOKED")
    assert result.buchungstext_lines == [
        "AMZN Mktp DE*NI22A6FP4, AMZN.COM BI",
        "LL LU",  # collapsed from raw 'LL  LU'
        "Karte Nr. 4871 78XX XXXX 3636",
        "Kartenzahlung",
        "comdirect Visa-Debitkarte",
        "2026-04-07 00:00:00",
    ]
    # Card trailer chunks are intentionally NOT promoted to dedicated fields
    # — the banking web UI keeps them inside Buchungstext.
    assert result.end_to_end_reference is None
    assert result.mandate_reference is None
    assert result.creditor_id is None


def test_sample_17_direct_debit_no_concatenation() -> None:
    """Sample #17 — B+B Parkhaus, merchant wraps across windows 01/02."""
    raw = (
        "01B+B PARKHAUS GMBH & CO, WUPPERTAL  "
        "02DE                                 "
        "03Karte Nr. 4871 78XX XXXX 7657      "
        "04Kartenzahlung                      "
        "05comdirect Visa-Debitkarte          "
        "062026-04-01 00:00:00                "
    )
    result = parse(raw, "BOOKED")
    # WUPPERTAL and DE stay as separate lines — no reassembly.
    assert result.buchungstext_lines[:2] == [
        "B+B PARKHAUS GMBH & CO, WUPPERTAL",
        "DE",
    ]


def test_sample_20_drunkenslug_full_sepa_metadata() -> None:
    """Sample #20 — PayPal direct debit with End-to-End + Mandate + Creditor."""
    raw = (
        "011049447148633/PP.7320.PP/. drunkens"
        "02lug, Ihr Einkauf bei drunkenslug   "
        "03End-to-End-Ref.:                   "
        "041049447148633                      "
        "05CORE / Mandatsref.:                "
        "064LHJ2255C8KDN                      "
        "07Gläubiger-ID:                      "
        "08LU96ZZZ0000000000000000058         "
    )
    result = parse(raw, "BOOKED")
    assert result.buchungstext_lines == [
        "1049447148633/PP.7320.PP/. drunkens",
        "lug, Ihr Einkauf bei drunkenslug",
    ]
    assert result.end_to_end_reference == "1049447148633"
    assert result.mandate_reference == "4LHJ2255C8KDN"
    assert result.creditor_id == "LU96ZZZ0000000000000000058"


# ---------------------------------------------------------------------------
# NOTBOOKED payloads (pending transactions)
# ---------------------------------------------------------------------------


def test_notbooked_single_chunk() -> None:
    """Sample #2-ish — pending card transaction, 2 × 35-char windows."""
    raw = "JET-Tankstelle Wuppertal DEU       " "2026-04-11T13:31:08                "
    result = parse(raw, "NOTBOOKED")
    assert result.buchungstext_lines == [
        "JET-Tankstelle Wuppertal DEU",
        "2026-04-11T13:31:08",
    ]


def test_notbooked_does_not_extract_sepa() -> None:
    """Pending transactions never have SEPA metadata extracted."""
    raw = "End-to-End-Ref.:                   some value                        "
    result = parse(raw, "NOTBOOKED")
    # Both chunks appear as Buchungstext; neither is treated as a label.
    assert result.end_to_end_reference is None
    assert len(result.buchungstext_lines) == 2

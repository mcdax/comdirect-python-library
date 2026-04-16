"""Parser for the comdirect ``remittanceInfo`` field (Verwendungszweck).

The field is a single flat string (no ``\\n``). Its structure was verified
against the live comdirect banking web UI on 2026-04-11 — see
``COMDIRECT_API.md`` §"``remittanceInfo`` parsing (Verwendungszweck)" for the
full evidence.

Rules in short:

* ``BOOKED`` transactions: 37-char windows, each prefixed with a 2-digit
  marker (``01``, ``02``, …). The total length is always a multiple of 37.
* ``NOTBOOKED`` transactions: 35-char windows, no markers.
* Per-chunk normalization collapses runs of whitespace to a single space
  (not just ``rstrip`` — ``LL  LU`` becomes ``LL LU``).
* Chunks are never concatenated across windows, even when a word wraps
  mid-character. The web UI shows them as separate lines.
* For BOOKED transactions only, three SEPA labels trigger structured
  extraction (the label chunk plus the following value chunk are lifted out
  of the Buchungstext and stored in dedicated fields).
"""

from dataclasses import dataclass, field
from typing import Optional

BOOKED_WINDOW = 37  # 2-char marker + 35-char content
NOTBOOKED_WINDOW = 35  # pure 35-char content, no marker

# Label string (after normalization) -> attribute name on ParsedRemittance
SEPA_LABELS: dict[str, str] = {
    "End-to-End-Ref.:": "end_to_end_reference",
    "CORE / Mandatsref.:": "mandate_reference",
    "COR1 / Mandatsref.:": "mandate_reference",  # assumed, untested
    "B2B / Mandatsref.:": "mandate_reference",  # assumed, untested
    "Gläubiger-ID:": "creditor_id",
}


@dataclass
class ParsedRemittance:
    """Result of parsing a ``remittanceInfo`` string.

    ``buchungstext_lines`` contains the lines that the banking web UI shows
    under the "Buchungstext" label — each entry is one visual line as rendered
    with ``<br>`` separators.
    """

    buchungstext_lines: list[str] = field(default_factory=list)
    end_to_end_reference: Optional[str] = None
    mandate_reference: Optional[str] = None
    creditor_id: Optional[str] = None


def _normalize(chunk_content: str) -> str:
    """Strip + collapse runs of internal whitespace to single spaces.

    This mirrors the normalization applied by the comdirect banking web UI
    before rendering a chunk. Verified against live transactions — e.g. the
    raw API bytes ``'LL  LU                             '`` become ``'LL LU'``
    with a single space.
    """
    return " ".join(chunk_content.split())


def _split_booked(remittance_info: str) -> list[str]:
    """Split a BOOKED remittance string into content chunks.

    Each 37-char window consists of a 2-digit marker (``01`` … ``99``) plus
    35 content characters. If a window does not start with two digits (the
    rare ``'01 '`` edge case when the purpose is empty), the whole window is
    returned as-is — ``_normalize`` will strip it to the empty string, which
    is then skipped by the caller.
    """
    chunks: list[str] = []
    for i in range(0, len(remittance_info), BOOKED_WINDOW):
        window = remittance_info[i : i + BOOKED_WINDOW]
        if len(window) >= 2 and window[:2].isdigit():
            chunks.append(window[2:])
        else:
            # No marker — treat the whole window as content. Happens for
            # fabricated/short inputs that don't follow the 37-char rule.
            chunks.append(window)
    return chunks


def _split_notbooked(remittance_info: str) -> list[str]:
    """Split a NOTBOOKED remittance string into 35-char content chunks."""
    return [
        remittance_info[i : i + NOTBOOKED_WINDOW]
        for i in range(0, len(remittance_info), NOTBOOKED_WINDOW)
    ]


def parse(remittance_info: Optional[str], booking_status: Optional[str]) -> ParsedRemittance:
    """Parse ``remittanceInfo`` into Buchungstext lines plus SEPA metadata.

    Args:
        remittance_info: The raw API field. May be ``None`` or empty.
        booking_status: ``"BOOKED"`` or ``"NOTBOOKED"``. Controls the window
            width and whether SEPA label extraction runs. Any other value is
            treated as ``"BOOKED"``.

    Returns:
        ``ParsedRemittance`` — always safe, never raises.
    """
    result = ParsedRemittance()
    if not remittance_info:
        return result

    if booking_status == "NOTBOOKED":
        for raw in _split_notbooked(remittance_info):
            line = _normalize(raw)
            if line:
                result.buchungstext_lines.append(line)
        return result

    # BOOKED (default): extract SEPA labels as we walk the chunks.
    chunks = _split_booked(remittance_info)
    idx = 0
    while idx < len(chunks):
        line = _normalize(chunks[idx])
        label_attr = SEPA_LABELS.get(line)
        if label_attr and idx + 1 < len(chunks):
            setattr(result, label_attr, _normalize(chunks[idx + 1]))
            idx += 2
            continue
        if line:
            result.buchungstext_lines.append(line)
        idx += 1
    return result

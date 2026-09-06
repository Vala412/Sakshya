"""Field normalization: GSTIN validation, invoice-number keys, date/amount parsing.

Every function here is pure (no I/O, no shared state) so it can be tested in
isolation and reused identically by ingestion, the matcher, and the
synthetic-data generator -- if generation-time and ingestion-time
normalization ever drifted apart, the eval harness would be scoring the
matcher against its own inconsistency rather than against real defects.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# GSTIN: format + check digit
# ---------------------------------------------------------------------------
# Structure (15 chars): 2-digit state code, 10-char PAN, 1-digit registration
# count within the state (1-9 then A-Z for 10-35), a literal 'Z' (reserved,
# always 'Z' today), and a checksum character.
_GSTIN_FORMAT_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$")

_CHECKSUM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(gstin_14: str) -> str:
    """Compute the 15th (check) character for the first 14 GSTIN characters.

    GSTN has never published this formula officially -- there is no spec to
    cite. This implements the mod-36 Luhn-style algorithm used by every
    independent GSTIN-checksum implementation found in the wild (ported
    across multiple languages by unrelated authors), and it was verified
    here against a real, independently-published valid GSTIN
    (27AAPFU0939F1ZV) rather than trusted on description alone.

    Each character is weighted 1/2 alternately from the left, doubled
    products are folded back into 0-35 (same idea as Luhn's digit-doubling),
    summed, and the check character is whatever brings that sum up to the
    next multiple of 36.
    """
    total = 0
    for index, char in enumerate(gstin_14):
        value = _CHECKSUM_ALPHABET.index(char)
        weight = 1 if index % 2 == 0 else 2
        product = value * weight
        total += (product // 36) + (product % 36)
    check_value = (36 - (total % 36)) % 36
    return _CHECKSUM_ALPHABET[check_value]


def is_valid_gstin(gstin: str) -> bool:
    """Structural format + checksum validity.

    Does not verify the GSTIN is actually registered/active -- that requires
    a live GST portal lookup, which is out of scope for a books-vs-2B
    reconciliation engine that must run offline and deterministically.
    """
    candidate = gstin.strip().upper()
    if not _GSTIN_FORMAT_RE.match(candidate):
        return False
    return gstin_check_digit(candidate[:14]) == candidate[14]


def gstin_similarity(a: str, b: str) -> float:
    """0-100 similarity between two GSTINs.

    Used to recover a single mistyped GSTIN character (the GSTN manual's
    "Probable match" category: GSTIN or document type mismatches while every
    other parameter agrees) -- so one supplier typo produces one finding
    instead of two independent unexplained documents.
    """
    return fuzz.ratio(a.strip().upper(), b.strip().upper())


# ---------------------------------------------------------------------------
# Invoice number keys
# ---------------------------------------------------------------------------
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]")


def strict_invoice_key(invoice_number: str) -> str:
    """Case- and whitespace-insensitive key, otherwise byte-for-byte.

    Used for exact-match comparison: two invoice numbers differing only in
    case or surrounding whitespace are the same document.
    """
    return invoice_number.strip().upper()


def loose_invoice_key(invoice_number: str) -> str:
    """Separator- and case-insensitive key (GSTN's own "approximation logic"
    on document number): INV-0005, INV/0005, and INV 0005 all normalize to
    the same key.

    Deliberately does NOT touch digit runs. An earlier version of this
    normalization stripped leading zeros with `re.sub(r"0+(\\d)", r"\\1")`,
    which silently merged INV/0005 with INV/0050 -- two distinct invoices --
    into one key; the eval harness caught it as a false duplicate-booking
    exception. Leading zeros are part of the invoice number's identity, not
    formatting noise, so only separator characters are stripped here.
    """
    return _NON_ALNUM_RE.sub("", invoice_number.strip().upper())


def invoice_number_similarity(a: str, b: str) -> float:
    """0-100 similarity between two invoice numbers' loose keys.

    For the "approximation logic" case a plain separator-strip doesn't
    catch: a transposed digit, an OCR/keying slip, etc. Compares loose keys
    (not raw strings) so separator differences never depress the score.
    """
    return fuzz.ratio(loose_invoice_key(a), loose_invoice_key(b))


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
# GSTR-2B JSON conventionally renders dates as DD-MM-YYYY; Tally's CSV/XML
# exports vary by report template and locale settings. Tried in an order
# that resolves the common real cases first -- none of these are ambiguous
# with each other once the separator and month representation are known.
_DATE_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d/%m/%y",
)


def parse_date(value: str | date) -> date:
    """Parse a date from any format GSTR-2B or Tally exports use."""
    if isinstance(value, date):
        return value
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value!r}")


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------
# Strip Indian-style comma grouping (1,23,456.78), the rupee sign, and
# incidental whitespace before parsing.
_AMOUNT_CLEAN_RE = re.compile(r"[,\s₹]")


def parse_amount(value: str | int | float | Decimal | None) -> Decimal:
    """Parse a monetary amount, tolerating Indian comma grouping, a rupee
    symbol, and parenthesized negatives (Tally's convention for outflows).

    Blank/None becomes 0.00 rather than raising: GSTR-2B leaves a tax-head
    field empty when that head doesn't apply to the document (e.g. no CESS),
    and that must not be mistaken for a parse failure. A whitespace-only
    cell (a plausible CSV export artifact) counts as blank too -- checking
    only `value == ""` would let " " fall through to the general string
    path below and raise, which is the wrong failure mode for what is,
    functionally, still an empty cell.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    if isinstance(value, (int, float)):
        return Decimal(str(value)).quantize(Decimal("0.01"))

    text = _AMOUNT_CLEAN_RE.sub("", str(value))
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognized amount format: {value!r}") from exc
    if negative:
        amount = -amount
    return amount.quantize(Decimal("0.01"))

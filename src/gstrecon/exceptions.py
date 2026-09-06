"""Exception classification: turn matching.py's parameter-level findings into
the 12 reason codes a reviewing CA actually needs, each with a severity and an
ITC-at-risk figure that can be summed into the working paper's ITC bridge.

Reason codes
------------
Core (real, direct ITC impact):
  EX-01  In books, not in GSTR-2B
  EX-02  In GSTR-2B, not in books
  EX-04  Tax amount mismatch
  EX-09  ITC flagged unavailable in 2B but claimed in books
  EX-11  Credit note in 2B with no reversal in books

v1:
  EX-03  Taxable value mismatch
  EX-06  GSTIN invalid or mismatched
  EX-10  Duplicate booking

Stretch:
  EX-05  Tax head mismatch (total agrees, IGST/CGST/SGST/CESS split doesn't)
  EX-07  Invoice number variance (below fuzzy-match threshold, else identical)
  EX-08  Period timing (invoice's own month vs the 2B period it appeared in)
  EX-12  Credit note booked but not yet reflected in 2B

EX-13 does not exist here: an earlier version of this taxonomy declared it but
it never fired against any synthetic defect, so it was removed rather than
kept as dead code.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from gstrecon import normalize
from gstrecon.matching import (
    PARAM_DOC_NUMBER,
    PARAM_GSTIN,
    PARAM_HEAD_WISE,
    PARAM_TAXABLE_VALUE,
    PARAM_TOTAL_TAX,
    MatchCategory,
    MatchResult,
    reconcile,
)
from gstrecon.models import DocType, Document, ItcAvailability

DEFAULT_TAX_TOLERANCE = Decimal("0")


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReasonCode(StrEnum):
    EX_01 = "EX-01"
    EX_02 = "EX-02"
    EX_03 = "EX-03"
    EX_04 = "EX-04"
    EX_05 = "EX-05"
    EX_06 = "EX-06"
    EX_07 = "EX-07"
    EX_08 = "EX-08"
    EX_09 = "EX-09"
    EX_10 = "EX-10"
    EX_11 = "EX-11"
    EX_12 = "EX-12"


_SEVERITY = {
    ReasonCode.EX_01: Severity.HIGH,
    ReasonCode.EX_02: Severity.LOW,
    ReasonCode.EX_03: Severity.MEDIUM,
    ReasonCode.EX_04: Severity.HIGH,
    ReasonCode.EX_05: Severity.MEDIUM,
    ReasonCode.EX_06: Severity.HIGH,
    ReasonCode.EX_07: Severity.LOW,
    ReasonCode.EX_08: Severity.LOW,
    ReasonCode.EX_09: Severity.HIGH,
    ReasonCode.EX_10: Severity.HIGH,
    ReasonCode.EX_11: Severity.HIGH,
    ReasonCode.EX_12: Severity.LOW,
}

_DESCRIPTIONS = {
    ReasonCode.EX_01: "In books, not in GSTR-2B",
    ReasonCode.EX_02: "In GSTR-2B, not in books",
    ReasonCode.EX_03: "Taxable value mismatch",
    ReasonCode.EX_04: "Tax amount mismatch",
    ReasonCode.EX_05: "Tax head mismatch (total agrees, head-wise split doesn't)",
    ReasonCode.EX_06: "GSTIN invalid or mismatched",
    ReasonCode.EX_07: "Invoice number variance",
    ReasonCode.EX_08: "Period timing difference",
    ReasonCode.EX_09: "ITC flagged unavailable in 2B but claimed in books",
    ReasonCode.EX_10: "Duplicate booking",
    ReasonCode.EX_11: "Credit note in 2B with no reversal in books",
    ReasonCode.EX_12: "Credit note booked but not yet reflected in 2B",
}


class Exception_(BaseModel):
    """One finding in the exception register.

    Named `Exception_` (trailing underscore) to avoid shadowing the Python
    builtin `Exception` -- this is a data record, not a Python exception, and
    giving it the bare name would make `except Exception` in surrounding code
    a landmine for whoever edits this file next.
    """

    model_config = ConfigDict(frozen=True)

    reason_code: ReasonCode
    severity: Severity
    description: str
    match_category: MatchCategory
    books_doc: Document | None
    gstr2b_doc: Document | None
    itc_at_risk: Decimal
    evidence: str

    @property
    def reason_label(self) -> str:
        return f"{self.reason_code.value}: {self.description}"


def _make(
    code: ReasonCode,
    result: MatchResult,
    *,
    itc_at_risk: Decimal,
    evidence: str,
) -> Exception_:
    return Exception_(
        reason_code=code,
        severity=_SEVERITY[code],
        description=_DESCRIPTIONS[code],
        match_category=result.category,
        books_doc=result.books_doc,
        gstr2b_doc=result.gstr2b_doc,
        itc_at_risk=itc_at_risk,
        evidence=evidence,
    )


def _dedup_key(doc: Document) -> tuple[str, str, str]:
    return (
        doc.supplier_gstin.strip().upper(),
        doc.doc_type.value,
        normalize.strict_invoice_key(doc.invoice_number),
    )


def _split_duplicates(docs: list[Document]) -> tuple[list[Document], list[Document]]:
    """Split `docs` into (one primary per identity key, every surplus copy).

    Run once per side *before* matching so a duplicated books entry produces
    exactly one EX-10 finding for the surplus copy -- not an EX-10 for the
    surplus *and* an EX-01 "missing from 2B" for it too, which is how an
    earlier version of this engine double-counted duplicate bookings.
    Ordered by row_ref so which copy is "primary" is deterministic and
    reproducible from the source file, not dependent on file-read order.
    """
    by_key: dict[tuple[str, str, str], list[Document]] = defaultdict(list)
    for doc in docs:
        by_key[_dedup_key(doc)].append(doc)

    primaries: list[Document] = []
    surplus: list[Document] = []
    for group in by_key.values():
        ordered = sorted(group, key=lambda d: d.row_ref)
        primaries.append(ordered[0])
        surplus.extend(ordered[1:])
    return primaries, surplus


def _invalid_gstin_exceptions(docs: list[Document]) -> list[Exception_]:
    """Structural GSTIN validity is independent of matching: a document can
    have an unmatchable-quality GSTIN even if it happens to pair perfectly on
    every other parameter, and that pairing would otherwise hide the defect.
    """
    findings: list[Exception_] = []
    for doc in docs:
        if normalize.is_valid_gstin(doc.supplier_gstin):
            continue
        is_books = doc.source.value == "books"
        findings.append(
            Exception_(
                reason_code=ReasonCode.EX_06,
                severity=_SEVERITY[ReasonCode.EX_06],
                description=f"{_DESCRIPTIONS[ReasonCode.EX_06]} (structurally invalid GSTIN)",
                match_category=MatchCategory.IN_BOOKS_NOT_2B
                if is_books
                else MatchCategory.IN_2B_NOT_BOOKS,
                books_doc=doc if is_books else None,
                gstr2b_doc=None if is_books else doc,
                itc_at_risk=(
                    Decimal("0.00") if doc.doc_type is DocType.CREDIT_NOTE else doc.total_tax
                ),
                evidence=f"invalid_gstin={doc.supplier_gstin!r} at {doc.row_ref}",
            )
        )
    return findings


def _duplicate_exceptions(surplus_docs: list[Document]) -> list[Exception_]:
    findings: list[Exception_] = []
    for doc in surplus_docs:
        is_books = doc.source.value == "books"
        findings.append(
            Exception_(
                reason_code=ReasonCode.EX_10,
                severity=_SEVERITY[ReasonCode.EX_10],
                description=_DESCRIPTIONS[ReasonCode.EX_10],
                match_category=MatchCategory.IN_BOOKS_NOT_2B
                if is_books
                else MatchCategory.IN_2B_NOT_BOOKS,
                books_doc=doc if is_books else None,
                gstr2b_doc=None if is_books else doc,
                itc_at_risk=doc.total_tax,
                evidence=f"duplicate of {_dedup_key(doc)} at {doc.row_ref}",
            )
        )
    return findings


def _expected_period(doc: Document) -> str:
    """MMYYYY for the calendar month the document's own date falls in, in
    the same (unconfirmed-by-spec) convention assumed for `return_period`."""
    return f"{doc.invoice_date.month:02d}{doc.invoice_date.year}"


def _classify_match(result: MatchResult) -> list[Exception_]:
    findings: list[Exception_] = []
    books, gstr2b = result.books_doc, result.gstr2b_doc

    if result.category is MatchCategory.IN_BOOKS_NOT_2B:
        assert books is not None
        code = ReasonCode.EX_12 if books.doc_type is DocType.CREDIT_NOTE else ReasonCode.EX_01
        at_risk = Decimal("0.00") if code is ReasonCode.EX_12 else books.total_tax
        findings.append(_make(code, result, itc_at_risk=at_risk, evidence=f"books={books.row_ref}"))
        return findings

    if result.category is MatchCategory.IN_2B_NOT_BOOKS:
        assert gstr2b is not None
        code = ReasonCode.EX_11 if gstr2b.doc_type is DocType.CREDIT_NOTE else ReasonCode.EX_02
        at_risk = gstr2b.total_tax if code is ReasonCode.EX_11 else Decimal("0.00")
        findings.append(
            _make(code, result, itc_at_risk=at_risk, evidence=f"gstr2b={gstr2b.row_ref}")
        )
        return findings

    # Every other category has both documents present.
    assert books is not None and gstr2b is not None
    params = set(result.mismatched_parameters)

    if PARAM_GSTIN in params:
        findings.append(
            _make(
                ReasonCode.EX_06,
                result,
                itc_at_risk=Decimal("0.00"),
                evidence=f"{books.supplier_gstin} vs {gstr2b.supplier_gstin}",
            )
        )

    if PARAM_TAXABLE_VALUE in params:
        findings.append(
            _make(
                ReasonCode.EX_03,
                result,
                itc_at_risk=Decimal("0.00"),
                evidence=f"{books.taxable_value} vs {gstr2b.taxable_value}",
            )
        )

    if PARAM_TOTAL_TAX in params:
        findings.append(
            _make(
                ReasonCode.EX_04,
                result,
                itc_at_risk=abs(books.total_tax - gstr2b.total_tax),
                evidence=f"{books.total_tax} vs {gstr2b.total_tax}",
            )
        )
    elif PARAM_HEAD_WISE in params:
        # Only reached when the total agreed but an individual head didn't --
        # see matching.py's offsetting-heads case. If the total itself also
        # mismatched, EX-04 already covers it above.
        findings.append(
            _make(
                ReasonCode.EX_05,
                result,
                itc_at_risk=Decimal("0.00"),
                evidence=f"{books.tax!r} vs {gstr2b.tax!r}",
            )
        )

    if PARAM_DOC_NUMBER in params:
        findings.append(
            _make(
                ReasonCode.EX_07,
                result,
                itc_at_risk=Decimal("0.00"),
                evidence=f"{books.invoice_number!r} vs {gstr2b.invoice_number!r}",
            )
        )

    if (
        gstr2b.itc_availability is ItcAvailability.NOT_AVAILABLE
        and books.doc_type is not DocType.CREDIT_NOTE
    ):
        findings.append(
            _make(
                ReasonCode.EX_09,
                result,
                itc_at_risk=books.total_tax,
                evidence=f"2b itc_availability=N for {gstr2b.row_ref}",
            )
        )

    expected_period = _expected_period(gstr2b)
    if gstr2b.return_period is not None and gstr2b.return_period != expected_period:
        findings.append(
            _make(
                ReasonCode.EX_08,
                result,
                itc_at_risk=Decimal("0.00"),
                evidence=f"invoice month={expected_period} return_period={gstr2b.return_period}",
            )
        )

    return findings


class ReconciliationResult(BaseModel):
    """The full output of one reconciliation pass: match results plus the
    documents set aside as duplicate surplus, plus every exception derived
    from them.

    report.py's ITC bridge is built from `match_results` /
    `books_duplicate_surplus` / `gstr2b_duplicate_surplus` directly, rather
    than re-deriving its own dedup+match pass -- the bridge and the
    exception register must agree on record-for-record, and the only way to
    guarantee that is for both to read from one reconciliation, not two
    separately-computed ones that happen to use the same inputs.
    """

    model_config = ConfigDict(frozen=True)

    match_results: list[MatchResult]
    books_duplicate_surplus: list[Document]
    gstr2b_duplicate_surplus: list[Document]
    findings: list[Exception_]


def reconcile_full(
    books_docs: list[Document],
    gstr2b_docs: list[Document],
    *,
    tax_tolerance: Decimal = DEFAULT_TAX_TOLERANCE,
) -> ReconciliationResult:
    """Full pipeline: dedup -> match -> classify -> structural GSTIN check.

    This is the one function report.py and the CLI should call -- it owns
    the ordering that keeps EX-10 (duplicate) and EX-01/EX-02 (missing) from
    double-counting the same document, which per-function composition at the
    call site got wrong before.
    """
    books_primary, books_surplus = _split_duplicates(books_docs)
    gstr2b_primary, gstr2b_surplus = _split_duplicates(gstr2b_docs)

    match_results = reconcile(books_primary, gstr2b_primary, tax_tolerance=tax_tolerance)

    findings: list[Exception_] = []
    for result in match_results:
        findings.extend(_classify_match(result))
    findings.extend(_duplicate_exceptions(books_surplus))
    findings.extend(_duplicate_exceptions(gstr2b_surplus))
    findings.extend(_invalid_gstin_exceptions(books_docs + gstr2b_docs))

    return ReconciliationResult(
        match_results=match_results,
        books_duplicate_surplus=books_surplus,
        gstr2b_duplicate_surplus=gstr2b_surplus,
        findings=findings,
    )


def classify_reconciliation(
    books_docs: list[Document],
    gstr2b_docs: list[Document],
    *,
    tax_tolerance: Decimal = DEFAULT_TAX_TOLERANCE,
) -> list[Exception_]:
    """Convenience wrapper over `reconcile_full` for callers that only need
    the exception register (e.g. the CLI's exception-register sheet, most
    tests) and not the intermediate match state the ITC bridge needs."""
    return reconcile_full(books_docs, gstr2b_docs, tax_tolerance=tax_tolerance).findings

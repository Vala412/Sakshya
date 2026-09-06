"""Deterministic books-vs-GSTR-2B matcher, built on the GSTN Matching Offline
Tool's own published taxonomy (matchingtool.pdf, GSTN, retrieved 2026) rather
than an invented tiering scheme:

  7 matching parameters : GSTIN, document type, document number, document
                           date, total taxable value, total tax amount (sum
                           of IGST+CGST+SGST+CESS), and tax amount head-wise
                           (each of IGST/CGST/SGST/CESS checked individually).

  6 categories           : Exact match (7/7), Partial match (GSTIN + doc type
                            agree, exactly one other parameter mismatches),
                            Probable match (GSTIN or doc type mismatches,
                            the other 5 parameters agree), Unmatched
                            (GSTIN + doc type + doc number + date agree, but
                            a value parameter mismatches beyond tolerance),
                            In-2B-not-in-books, In-books-not-in-2B.

One deliberate narrowing of the official definition: **document type is
never treated as the mismatching parameter for a Probable match here** --
i.e. an invoice is never proposed as a match for a credit note. GSTN's own
manual allows a doc-type mismatch as a Probable-match candidate (e.g. a
debit note booked as an invoice), but silently pairing an invoice with a
credit note on the strength of matching amounts risks masking a genuine
sign error in claimed ITC, which is a materially worse outcome than leaving
both sides unmatched for a human to review. Every other category is
implemented as specified.

Matching is greedy: within each document-type bucket, every candidate pair
that clears the minimum identity bar for its category is scored by how many
parameters agree (ties broken by string-similarity), and pairs are committed
best-first, consuming both sides so no document is matched twice. This is
deliberately not an optimal bipartite assignment (e.g. Hungarian algorithm) --
an auditor re-checking a match needs to see "these two documents agreed on N
of 7 parameters," not "the solver's global cost function preferred this
pairing over that one."
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from gstrecon import normalize
from gstrecon.models import Document

DEFAULT_TAX_TOLERANCE = Decimal("0")
# From the original T3/T4 design, carried over as the defaults for GSTN's
# "approximation logic" toggle: how similar a document number or GSTIN must
# be (rapidfuzz.fuzz.ratio, 0-100) to count as matching once exact equality
# has already failed.
DEFAULT_INVOICE_FUZZY_THRESHOLD = 88.0
DEFAULT_GSTIN_FUZZY_THRESHOLD = 85.0


class MatchCategory(StrEnum):
    EXACT = "exact_match"
    PARTIAL = "partial_match"
    PROBABLE = "probable_match"
    UNMATCHED = "unmatched"
    IN_2B_NOT_BOOKS = "in_2b_not_books"
    IN_BOOKS_NOT_2B = "in_books_not_2b"


# Canonical parameter names, taken verbatim (snake_cased) from the GSTN
# manual's own list, so exceptions.py can cite exactly which official
# parameter drove a classification instead of a name we made up.
PARAM_GSTIN = "gstin"
PARAM_DOC_TYPE = "document_type"
PARAM_DOC_NUMBER = "document_number"
PARAM_DOC_DATE = "document_date"
PARAM_TAXABLE_VALUE = "taxable_value"
PARAM_TOTAL_TAX = "total_tax_amount"
PARAM_HEAD_WISE = "tax_amount_head_wise"


@dataclass(frozen=True)
class ParameterMatch:
    """Per-parameter agreement between one books document and one GSTR-2B
    document. `doc_number_similarity`/`gstin_similarity` are kept alongside
    the booleans so the greedy matcher can rank otherwise-tied candidates by
    closeness rather than arbitrary document order.
    """

    gstin_exact: bool
    gstin_similarity: float
    doc_number_exact: bool
    doc_number_approx: bool
    doc_number_similarity: float
    date_match: bool
    taxable_value_match: bool
    total_tax_match: bool
    head_wise_match: bool

    @property
    def doc_number_ok(self) -> bool:
        """Matches for classification purposes under GSTN's "approximation
        logic": exact equality, or a fuzzy match above threshold."""
        return self.doc_number_exact or self.doc_number_approx

    def mismatched_value_parameters(self) -> tuple[str, ...]:
        mismatches = []
        if not self.taxable_value_match:
            mismatches.append(PARAM_TAXABLE_VALUE)
        if not self.total_tax_match:
            mismatches.append(PARAM_TOTAL_TAX)
        if not self.head_wise_match:
            mismatches.append(PARAM_HEAD_WISE)
        return tuple(mismatches)


class MatchResult(BaseModel):
    """One reconciled pairing (or orphan) plus the evidence needed to defend
    it in a working paper: which official parameters disagreed, and the
    row-level provenance of both documents (or the single document, for an
    orphan)."""

    model_config = ConfigDict(frozen=True)

    category: MatchCategory
    books_doc: Document | None
    gstr2b_doc: Document | None
    mismatched_parameters: tuple[str, ...] = ()

    @property
    def evidence(self) -> str:
        books_ref = self.books_doc.row_ref if self.books_doc else "(none)"
        gstr2b_ref = self.gstr2b_doc.row_ref if self.gstr2b_doc else "(none)"
        params = ", ".join(self.mismatched_parameters) or "none"
        return f"books={books_ref} 2b={gstr2b_ref} mismatched=[{params}]"


def _compare(
    books: Document,
    gstr2b: Document,
    *,
    tax_tolerance: Decimal,
    invoice_fuzzy_threshold: float,
) -> ParameterMatch:
    doc_number_exact = normalize.strict_invoice_key(
        books.invoice_number
    ) == normalize.strict_invoice_key(gstr2b.invoice_number)
    doc_number_similarity = normalize.invoice_number_similarity(
        books.invoice_number, gstr2b.invoice_number
    )
    return ParameterMatch(
        gstin_exact=books.supplier_gstin.strip().upper() == gstr2b.supplier_gstin.strip().upper(),
        gstin_similarity=normalize.gstin_similarity(books.supplier_gstin, gstr2b.supplier_gstin),
        doc_number_exact=doc_number_exact,
        doc_number_approx=(
            not doc_number_exact and doc_number_similarity >= invoice_fuzzy_threshold
        ),
        doc_number_similarity=doc_number_similarity,
        date_match=books.invoice_date == gstr2b.invoice_date,
        taxable_value_match=abs(books.taxable_value - gstr2b.taxable_value) <= tax_tolerance,
        total_tax_match=abs(books.total_tax - gstr2b.total_tax) <= tax_tolerance,
        head_wise_match=books.tax.head_wise_matches(gstr2b.tax, tax_tolerance),
    )


def _score(pm: ParameterMatch) -> tuple[int, float]:
    """Higher is better: (# of the 5 non-identity-anchor parameters matching,
    combined string similarity) -- used only to rank candidates that tie on
    category, never to decide the category itself."""
    matches = sum(
        [
            pm.doc_number_ok,
            pm.date_match,
            pm.taxable_value_match,
            pm.total_tax_match,
            pm.head_wise_match,
        ]
    )
    return matches, pm.doc_number_similarity + pm.gstin_similarity


def _classify_gstin_anchored(pm: ParameterMatch) -> tuple[MatchCategory, tuple[str, ...]] | None:
    """GSTIN matches exactly (doc_type already matched -- see module docstring
    on why doc_type is a hard anchor, never a candidate mismatch). Returns
    None if the pair doesn't clear the minimum identity bar to be considered
    a candidate at all.
    """
    if not pm.gstin_exact:
        return None

    mismatches: list[str] = []
    if not pm.doc_number_ok:
        mismatches.append(PARAM_DOC_NUMBER)
    if not pm.date_match:
        mismatches.append(PARAM_DOC_DATE)
    mismatches.extend(pm.mismatched_value_parameters())

    if not mismatches:
        return MatchCategory.EXACT, ()

    # Minimum identity bar: at least one of {doc number, date} must still
    # agree, or there isn't enough evidence these two rows describe the same
    # transaction -- see module docstring's candidate-generation rationale.
    identity_intact = pm.doc_number_ok or pm.date_match
    if not identity_intact:
        return None

    if len(mismatches) == 1:
        return MatchCategory.PARTIAL, tuple(mismatches)

    # 2+ mismatches with identity (doc number + date) both still intact means
    # every mismatch is a value parameter -- exactly GSTN's "Unmatched"
    # definition (identity confirmed, values disagree beyond tolerance).
    if pm.doc_number_ok and pm.date_match:
        return MatchCategory.UNMATCHED, tuple(mismatches)

    return None


def _classify_gstin_relaxed(
    pm: ParameterMatch, *, gstin_fuzzy_threshold: float
) -> tuple[MatchCategory, tuple[str, ...]] | None:
    """GSTIN differs but is similar enough to be a probable keying error
    (recovers the single-mistyped-GSTIN-character case): every other
    parameter must agree exactly -- Probable match requires document number,
    date, taxable value, and tax amounts all matching, per the manual.
    Conservative on purpose: this is the pairing most likely to be wrong if
    loosened, since it crosses a supplier-identity boundary.
    """
    if pm.gstin_exact or pm.gstin_similarity < gstin_fuzzy_threshold:
        return None
    if not (pm.doc_number_exact and pm.date_match and pm.taxable_value_match):
        return None
    if not (pm.total_tax_match and pm.head_wise_match):
        return None
    return MatchCategory.PROBABLE, (PARAM_GSTIN,)


def reconcile(
    books_docs: list[Document],
    gstr2b_docs: list[Document],
    *,
    tax_tolerance: Decimal = DEFAULT_TAX_TOLERANCE,
    invoice_fuzzy_threshold: float = DEFAULT_INVOICE_FUZZY_THRESHOLD,
    gstin_fuzzy_threshold: float = DEFAULT_GSTIN_FUZZY_THRESHOLD,
) -> list[MatchResult]:
    """Reconcile books documents against GSTR-2B documents.

    Documents are bucketed by `doc_type` first (a hard anchor -- see module
    docstring) and matched independently within each bucket, so an invoice
    can never be proposed as a match for a credit note regardless of how
    closely amounts happen to align.
    """
    results: list[MatchResult] = []
    doc_types = {d.doc_type for d in books_docs} | {d.doc_type for d in gstr2b_docs}

    for doc_type in doc_types:
        books_bucket = [d for d in books_docs if d.doc_type == doc_type]
        gstr2b_bucket = [d for d in gstr2b_docs if d.doc_type == doc_type]
        results.extend(
            _reconcile_bucket(
                books_bucket,
                gstr2b_bucket,
                tax_tolerance=tax_tolerance,
                invoice_fuzzy_threshold=invoice_fuzzy_threshold,
                gstin_fuzzy_threshold=gstin_fuzzy_threshold,
            )
        )
    return results


# Committing order: prefer the category an auditor would trust most, then
# within a category prefer the highest parameter-agreement score.
_CATEGORY_PRIORITY = {
    MatchCategory.EXACT: 0,
    MatchCategory.PARTIAL: 1,
    MatchCategory.UNMATCHED: 2,
    MatchCategory.PROBABLE: 3,
}


def _reconcile_bucket(
    books_bucket: list[Document],
    gstr2b_bucket: list[Document],
    *,
    tax_tolerance: Decimal,
    invoice_fuzzy_threshold: float,
    gstin_fuzzy_threshold: float,
) -> list[MatchResult]:
    candidates: list[tuple[tuple[int, int, float], int, int, MatchCategory, tuple[str, ...]]] = []

    for b_idx, books_doc in enumerate(books_bucket):
        for g_idx, gstr2b_doc in enumerate(gstr2b_bucket):
            pm = _compare(
                books_doc,
                gstr2b_doc,
                tax_tolerance=tax_tolerance,
                invoice_fuzzy_threshold=invoice_fuzzy_threshold,
            )
            classification = _classify_gstin_anchored(pm) or _classify_gstin_relaxed(
                pm, gstin_fuzzy_threshold=gstin_fuzzy_threshold
            )
            if classification is None:
                continue
            category, mismatched = classification
            matches, similarity = _score(pm)
            rank_key = (_CATEGORY_PRIORITY[category], -matches, -similarity)
            candidates.append((rank_key, b_idx, g_idx, category, mismatched))

    candidates.sort(key=lambda c: c[0])

    matched_books: set[int] = set()
    matched_gstr2b: set[int] = set()
    results: list[MatchResult] = []
    for _, b_idx, g_idx, category, mismatched in candidates:
        if b_idx in matched_books or g_idx in matched_gstr2b:
            continue
        matched_books.add(b_idx)
        matched_gstr2b.add(g_idx)
        results.append(
            MatchResult(
                category=category,
                books_doc=books_bucket[b_idx],
                gstr2b_doc=gstr2b_bucket[g_idx],
                mismatched_parameters=mismatched,
            )
        )

    for b_idx, books_doc in enumerate(books_bucket):
        if b_idx not in matched_books:
            results.append(
                MatchResult(
                    category=MatchCategory.IN_BOOKS_NOT_2B, books_doc=books_doc, gstr2b_doc=None
                )
            )
    for g_idx, gstr2b_doc in enumerate(gstr2b_bucket):
        if g_idx not in matched_gstr2b:
            results.append(
                MatchResult(
                    category=MatchCategory.IN_2B_NOT_BOOKS, books_doc=None, gstr2b_doc=gstr2b_doc
                )
            )

    return results

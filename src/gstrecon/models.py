"""Domain objects shared by ingestion, matching, and classification.

`Document` is the single representation for a line item from *either* side of
the reconciliation (books or GSTR-2B). Using one type for both sides -- rather
than a `BooksEntry`/`Gstr2bEntry` pair -- is what lets the matcher compare them
with the same code path instead of hand-mirrored logic for each direction.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DocSource(StrEnum):
    """Which ledger a Document was read from. Needed because a "match" is
    always books-vs-2B, never books-vs-books."""

    BOOKS = "books"
    GSTR_2B = "gstr_2b"


class DocType(StrEnum):
    """GST document type. Part of the match key -- an invoice must never pair
    with a credit note just because the amounts happen to line up."""

    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"


class ItcAvailability(StrEnum):
    """GSTR-2B's own flag for whether a document's ITC is available to claim
    (Section 16 conditions / Section 17(5) blocks, e.g. supplier under
    composition scheme, return not filed by the due date). Books entries
    never carry this -- it is 2B's judgment, not the taxpayer's -- so it is
    Optional on Document and only ever set for DocSource.GSTR_2B rows.
    """

    AVAILABLE = "Y"
    NOT_AVAILABLE = "N"


class TaxAmounts(BaseModel):
    """The four tax heads, kept as a distinct value object because the GSTN
    Matching Offline Tool manual is explicit that "tax amount head wise" is
    checked per head (IGST, CGST, SGST/UTGST, CESS individually) -- never by
    comparing the summed total alone. Collapsing this into a single `tax`
    Decimal on Document would make that per-head comparison unrepresentable.
    """

    model_config = ConfigDict(frozen=True)

    igst: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    cess: Decimal = Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess

    def head_wise_matches(self, other: TaxAmounts, tolerance: Decimal) -> bool:
        """True iff every one of the four heads agrees within `tolerance`.

        Deliberately checks each head independently rather than comparing
        `self.total` to `other.total` within tolerance*4: an IGST shortfall
        offset by an equal CESS excess would pass a total-based check while
        failing the actual GSTN parameter, and would hide a real classification
        head error (EX-05) behind a coincidentally-matching total.
        """
        return (
            abs(self.igst - other.igst) <= tolerance
            and abs(self.cgst - other.cgst) <= tolerance
            and abs(self.sgst - other.sgst) <= tolerance
            and abs(self.cess - other.cess) <= tolerance
        )


class Document(BaseModel):
    """One line item, already normalized (dates/amounts parsed) by ingestion.

    Frozen because a Document is a fact about what a source file said --
    matching and classification derive judgments *about* documents, they
    never mutate the documents themselves. That keeps the evidence trail
    (`row_ref`) trustworthy: if a Document could change after being read, an
    exception's citation of it could point to a state that no longer exists.
    """

    model_config = ConfigDict(frozen=True)

    source: DocSource
    doc_type: DocType
    supplier_gstin: str
    supplier_name: str | None = None
    invoice_number: str
    invoice_date: date
    taxable_value: Decimal
    tax: TaxAmounts
    itc_availability: ItcAvailability | None = None
    return_period: str | None = None
    # Evidence trail: where this row came from in the source file, e.g.
    # "gstr2b_2024-04.json#b2b[3].inv[1]" or "tally_purchase.csv:17". Every
    # exception traces back to this so the working paper is reproducible
    # from the original files, not just from the engine's internal state.
    row_ref: str

    @property
    def total_tax(self) -> Decimal:
        return self.tax.total

    @property
    def total_value(self) -> Decimal:
        return self.taxable_value + self.total_tax

    @property
    def signed_tax(self) -> Decimal:
        """Tax amount signed for ITC-bridge arithmetic.

        A credit note *reverses* previously claimed credit, so summing
        `signed_tax` across a set of documents gives net ITC directly; a
        debit note or invoice both add. This sign lives here, once, so that
        report.py's ITC bridge and exceptions.py's at-risk-amount
        calculations both just sum `signed_tax` rather than each re-deriving
        "is this a credit note" at their own call sites -- doing it per call
        site is exactly how a credit note used to get double-counted, once
        as a deduction and once as an unrelated "duplicate" exception.
        """
        return -self.total_tax if self.doc_type == DocType.CREDIT_NOTE else self.total_tax

    @property
    def signed_taxable_value(self) -> Decimal:
        return (
            -self.taxable_value
            if self.doc_type == DocType.CREDIT_NOTE
            else self.taxable_value
        )

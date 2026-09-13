"""Wire format for the reconciliation API.

Two decisions worth defending, because both look like over-engineering
until the alternative bites:

1. **Every money field crosses the wire as a `str`, not a `float`.**
   The engine works in `Decimal` precisely so that 0.1 + 0.2 is 0.30 and
   not 0.30000000000000004. Serialising to JSON's number type would throw
   that away at the last step, and the closing variance -- the one figure
   this whole project exists to prove is nil -- is exactly the kind of
   value that a float round-trip turns into `-0.000000001`. Strings keep
   the engine's precision intact all the way into the browser.

2. **The reason-code catalogue is served, not hardcoded in the client.**
   Severity and description for each code live in `exceptions.py`. A
   frontend copy would be a second source of truth that silently drifts
   the first time a severity is retuned there.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

# Money fields are serialised through this so the rule lives in exactly one
# place rather than being re-stated on every Decimal field in the module.
_MONEY_FIELDS_NOTE = "Exact decimal string, e.g. '1234.56'. Never parse as float for arithmetic."


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True)


class TaxAmountsOut(_Base):
    """The four GST tax heads, kept split because the GSTN matching
    parameters are checked per head -- the UI needs the split to show *which*
    head disagreed (EX-05), not just that the total did."""

    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    total: Decimal

    @field_serializer("igst", "cgst", "sgst", "cess", "total")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class DocumentOut(_Base):
    source: str
    doc_type: str
    supplier_gstin: str
    supplier_name: str | None
    invoice_number: str
    invoice_date: date
    taxable_value: Decimal
    tax: TaxAmountsOut
    itc_availability: str | None
    return_period: str | None
    # The provenance string ("books.csv:31") that makes a finding traceable
    # back to a line in the user's own file. The UI surfaces this verbatim.
    row_ref: str

    @field_serializer("taxable_value")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class FindingOut(_Base):
    """One row of the exception register.

    `id` is assigned by the API purely so the client has a stable React key
    and drawer target. It is an index into this response's own ordering --
    not an engine concept, and not stable across runs.
    """

    id: int
    reason_code: str
    severity: str
    description: str
    match_category: str
    books_doc: DocumentOut | None
    gstr2b_doc: DocumentOut | None
    itc_at_risk: Decimal
    evidence: str
    # Which of GSTN's 7 official parameters disagreed. Drives the per-field
    # diff highlighting in the evidence drawer -- this is the difference
    # between "these rows differ somewhere" and "document_number and
    # taxable_value differ, here they are".
    mismatched_parameters: list[str]

    @field_serializer("itc_at_risk")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class BridgeLineOut(_Base):
    label: str
    reason_codes: str
    document_count: int
    amount: Decimal

    @field_serializer("amount")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class ItcBridgeOut(_Base):
    """The ITC bridge, in the same order `report.py` writes it to the
    working paper's first sheet. Order is meaningful -- it is a running
    decomposition from books total down to nil, so the client renders it as
    given and never re-sorts."""

    books_total: Decimal
    gstr2b_total_available: Decimal
    gstr2b_total_blocked: Decimal
    lines: list[BridgeLineOut]
    closing_variance: Decimal

    @field_serializer("books_total", "gstr2b_total_available", "gstr2b_total_blocked",
                      "closing_variance")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class SummaryOut(_Base):
    """Counts the client would otherwise derive by scanning the full findings
    array on every render. Computed server-side once so the UI can show
    headline figures before (or without) materialising the register."""

    books_document_count: int
    gstr2b_document_count: int
    finding_count: int
    findings_by_severity: dict[str, int]
    findings_by_reason_code: dict[str, int]
    matches_by_category: dict[str, int]
    total_itc_at_risk: Decimal

    @field_serializer("total_itc_at_risk")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class RunMetadataOut(_Base):
    """The Reproducibility sheet, verbatim. Surfacing the input SHA-256s in
    the UI is the point: it is what lets a reviewer confirm the screen they
    are looking at was produced from the file they think it was."""

    gstrecon_version: str
    generated_at: datetime
    books_filename: str
    books_sha256: str
    gstr2b_filename: str
    gstr2b_sha256: str
    tax_tolerance: Decimal
    invoice_fuzzy_threshold: float
    gstin_fuzzy_threshold: float

    @field_serializer("tax_tolerance")
    def _ser(self, v: Decimal) -> str:
        return str(v)


class ReconciliationOut(_Base):
    run_id: str
    summary: SummaryOut
    bridge: ItcBridgeOut
    findings: list[FindingOut]
    metadata: RunMetadataOut


class ReasonCodeOut(_Base):
    code: str
    description: str
    severity: str


class ErrorOut(_Base):
    """Normalised error envelope.

    Every non-2xx response from this API has this shape, so the client's API
    layer has exactly one error contract to map instead of branching on
    FastAPI's default `{"detail": ...}` for some failures and a custom shape
    for others.
    """

    error: str
    message: str
    # Present for input-format failures: which uploaded file was at fault.
    field: str | None = None

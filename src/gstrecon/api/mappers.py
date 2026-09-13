"""Engine objects -> wire schemas.

Kept in its own module so `main.py` stays request/response plumbing and the
shape-translation is unit-testable without spinning up an HTTP client.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from gstrecon import __version__
from gstrecon.api import schemas
from gstrecon.exceptions import Exception_, ReconciliationResult
from gstrecon.matching import MatchResult
from gstrecon.models import Document
from gstrecon.report import ItcBridge, RunMetadata

_ZERO = Decimal("0")


def document_out(doc: Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        source=doc.source.value,
        doc_type=doc.doc_type.value,
        supplier_gstin=doc.supplier_gstin,
        supplier_name=doc.supplier_name,
        invoice_number=doc.invoice_number,
        invoice_date=doc.invoice_date,
        taxable_value=doc.taxable_value,
        tax=schemas.TaxAmountsOut(
            igst=doc.tax.igst,
            cgst=doc.tax.cgst,
            sgst=doc.tax.sgst,
            cess=doc.tax.cess,
            total=doc.tax.total,
        ),
        itc_availability=doc.itc_availability.value if doc.itc_availability else None,
        return_period=doc.return_period,
        row_ref=doc.row_ref,
    )


def _mismatched_parameters(
    finding: Exception_, match_results: list[MatchResult]
) -> list[str]:
    """Recover the GSTN parameter list for a finding.

    `Exception_` carries the two documents but not the `MatchResult` that
    produced it, so the parameters are looked up by identity of the document
    pair. Falls back to an empty list rather than guessing: an empty
    parameter list renders as "no per-parameter detail available", which is
    honest, whereas a guessed list would put fabricated evidence in front of
    an auditor.
    """
    for result in match_results:
        if result.books_doc is finding.books_doc and result.gstr2b_doc is finding.gstr2b_doc:
            return list(result.mismatched_parameters)
    return []


def finding_out(
    index: int, finding: Exception_, match_results: list[MatchResult]
) -> schemas.FindingOut:
    return schemas.FindingOut(
        id=index,
        reason_code=finding.reason_code.value,
        severity=finding.severity.value,
        description=finding.description,
        match_category=finding.match_category.value,
        books_doc=document_out(finding.books_doc) if finding.books_doc else None,
        gstr2b_doc=document_out(finding.gstr2b_doc) if finding.gstr2b_doc else None,
        itc_at_risk=finding.itc_at_risk,
        evidence=finding.evidence,
        mismatched_parameters=_mismatched_parameters(finding, match_results),
    )


def bridge_out(bridge: ItcBridge) -> schemas.ItcBridgeOut:
    return schemas.ItcBridgeOut(
        books_total=bridge.books_total,
        gstr2b_total_available=bridge.gstr2b_total_available,
        gstr2b_total_blocked=bridge.gstr2b_total_blocked,
        lines=[
            schemas.BridgeLineOut(
                label=line.label,
                reason_codes=line.reason_codes,
                document_count=line.document_count,
                amount=line.amount,
            )
            for line in bridge.lines
        ],
        closing_variance=bridge.closing_variance,
    )


def summary_out(
    books_docs: list[Document],
    gstr2b_docs: list[Document],
    reconciliation: ReconciliationResult,
) -> schemas.SummaryOut:
    findings = reconciliation.findings
    return schemas.SummaryOut(
        books_document_count=len(books_docs),
        gstr2b_document_count=len(gstr2b_docs),
        finding_count=len(findings),
        findings_by_severity=dict(Counter(f.severity.value for f in findings)),
        findings_by_reason_code=dict(Counter(f.reason_code.value for f in findings)),
        matches_by_category=dict(
            Counter(r.category.value for r in reconciliation.match_results)
        ),
        # Summed for a headline figure only. This is deliberately NOT the
        # bridge's closing variance and must never be presented as it: one
        # document can carry several findings, so this double-counts by
        # design (see the note on `Exception_.itc_at_risk`). The bridge is
        # the authoritative net-impact number.
        total_itc_at_risk=sum((f.itc_at_risk for f in findings), _ZERO),
    )


def metadata_out(
    metadata: RunMetadata, *, books_filename: str, gstr2b_filename: str
) -> schemas.RunMetadataOut:
    """Build the reproducibility block.

    `books_filename`/`gstr2b_filename` are passed separately because
    `RunMetadata.books_path` points at the server's temp copy of the upload;
    showing a reviewer `/tmp/tmp8f3k/books.csv` instead of the name they
    uploaded would make the Reproducibility panel actively misleading. The
    SHA-256 is still taken over the temp file -- same bytes, so the hash is
    the one that matters.
    """
    rows = dict(metadata.to_rows())
    return schemas.RunMetadataOut(
        gstrecon_version=__version__,
        generated_at=metadata.generated_at or datetime.now(UTC),
        books_filename=books_filename,
        books_sha256=rows["Books file SHA-256"],
        gstr2b_filename=gstr2b_filename,
        gstr2b_sha256=rows["GSTR-2B file SHA-256"],
        tax_tolerance=metadata.tax_tolerance,
        invoice_fuzzy_threshold=metadata.invoice_fuzzy_threshold,
        gstin_fuzzy_threshold=metadata.gstin_fuzzy_threshold,
    )


def reconciliation_out(
    *,
    run_id: str,
    books_docs: list[Document],
    gstr2b_docs: list[Document],
    reconciliation: ReconciliationResult,
    bridge: ItcBridge,
    metadata: RunMetadata,
    books_filename: str,
    gstr2b_filename: str,
) -> schemas.ReconciliationOut:
    return schemas.ReconciliationOut(
        run_id=run_id,
        summary=summary_out(books_docs, gstr2b_docs, reconciliation),
        bridge=bridge_out(bridge),
        findings=[
            finding_out(i, f, reconciliation.match_results)
            for i, f in enumerate(reconciliation.findings)
        ],
        metadata=metadata_out(
            metadata, books_filename=books_filename, gstr2b_filename=gstr2b_filename
        ),
    )

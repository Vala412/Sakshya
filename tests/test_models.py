from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from gstrecon.models import DocSource, DocType, Document, TaxAmounts


def _doc(doc_type: DocType, **overrides: object) -> Document:
    defaults: dict[str, object] = dict(
        source=DocSource.BOOKS,
        doc_type=doc_type,
        supplier_gstin="27AAPFU0939F1ZV",
        invoice_number="INV/0001",
        invoice_date=date(2024, 4, 1),
        taxable_value=Decimal("1000.00"),
        tax=TaxAmounts(igst=Decimal("180.00")),
        row_ref="test:1",
    )
    defaults.update(overrides)
    return Document(**defaults)  # type: ignore[arg-type]


class TestTaxAmounts:
    def test_total_sums_all_heads(self) -> None:
        tax = TaxAmounts(
            igst=Decimal("10"), cgst=Decimal("5"), sgst=Decimal("5"), cess=Decimal("1")
        )
        assert tax.total == Decimal("21")

    def test_head_wise_match_within_tolerance(self) -> None:
        a = TaxAmounts(cgst=Decimal("100.00"), sgst=Decimal("100.00"))
        b = TaxAmounts(cgst=Decimal("100.50"), sgst=Decimal("99.60"))
        assert a.head_wise_matches(b, tolerance=Decimal("1")) is True

    def test_head_wise_mismatch_beyond_tolerance(self) -> None:
        a = TaxAmounts(cgst=Decimal("100.00"))
        b = TaxAmounts(cgst=Decimal("102.00"))
        assert a.head_wise_matches(b, tolerance=Decimal("1")) is False

    def test_offsetting_heads_do_not_pass_as_matching(self) -> None:
        # An IGST shortfall exactly offset by a CESS excess must still fail:
        # per-head comparison, never a total-based shortcut.
        a = TaxAmounts(igst=Decimal("100.00"), cess=Decimal("0.00"))
        b = TaxAmounts(igst=Decimal("90.00"), cess=Decimal("10.00"))
        assert a.total == b.total
        assert a.head_wise_matches(b, tolerance=Decimal("1")) is False


class TestDocumentSignedAmounts:
    def test_invoice_signed_tax_is_positive(self) -> None:
        doc = _doc(DocType.INVOICE)
        assert doc.signed_tax == Decimal("180.00")
        assert doc.signed_taxable_value == Decimal("1000.00")

    def test_debit_note_signed_tax_is_positive(self) -> None:
        doc = _doc(DocType.DEBIT_NOTE)
        assert doc.signed_tax == Decimal("180.00")

    def test_credit_note_signed_tax_is_negative(self) -> None:
        doc = _doc(DocType.CREDIT_NOTE)
        assert doc.signed_tax == Decimal("-180.00")
        assert doc.signed_taxable_value == Decimal("-1000.00")

    def test_total_value_is_taxable_plus_tax(self) -> None:
        doc = _doc(DocType.INVOICE)
        assert doc.total_value == Decimal("1180.00")

    def test_document_is_frozen(self) -> None:
        doc = _doc(DocType.INVOICE)
        with pytest.raises(ValidationError):
            doc.taxable_value = Decimal("2000.00")  # type: ignore[misc]

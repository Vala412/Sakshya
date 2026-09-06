from datetime import date
from decimal import Decimal

from gstrecon import exceptions
from gstrecon.exceptions import ReasonCode
from gstrecon.models import DocSource, DocType, Document, ItcAvailability, TaxAmounts

GSTIN = "27AAPFU0939F1ZV"
# Differs from GSTIN by one character (index 6) but is itself a checksum-
# valid GSTIN, so it isolates the "probable match" case from the
# structurally-invalid-GSTIN case below.
GSTIN_TYPO = "27AAPFA0939F1ZF"
INVALID_GSTIN = "27AAPFU0939F1Z9"  # fails checksum


def _doc(
    source: DocSource,
    doc_type: DocType = DocType.INVOICE,
    gstin: str = GSTIN,
    invoice_number: str = "INV/0001",
    invoice_date: date = date(2024, 4, 1),
    taxable_value: Decimal = Decimal("1000.00"),
    igst: Decimal = Decimal("180.00"),
    cgst: Decimal = Decimal("0.00"),
    sgst: Decimal = Decimal("0.00"),
    cess: Decimal = Decimal("0.00"),
    itc_availability: ItcAvailability | None = None,
    return_period: str | None = None,
    row_ref: str = "row",
) -> Document:
    return Document(
        source=source,
        doc_type=doc_type,
        supplier_gstin=gstin,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        taxable_value=taxable_value,
        tax=TaxAmounts(igst=igst, cgst=cgst, sgst=sgst, cess=cess),
        itc_availability=itc_availability,
        return_period=return_period,
        row_ref=row_ref,
    )


def _books(**kwargs: object) -> Document:
    return _doc(DocSource.BOOKS, **kwargs)  # type: ignore[arg-type]


def _gstr2b(**kwargs: object) -> Document:
    return _doc(DocSource.GSTR_2B, **kwargs)  # type: ignore[arg-type]


def _codes(findings: list[exceptions.Exception_]) -> set[ReasonCode]:
    return {f.reason_code for f in findings}


class TestMissingDocuments:
    def test_ex01_books_invoice_missing_from_2b(self) -> None:
        findings = exceptions.classify_reconciliation([_books()], [])
        assert _codes(findings) == {ReasonCode.EX_01}
        assert findings[0].itc_at_risk == Decimal("180.00")

    def test_ex02_2b_invoice_missing_from_books(self) -> None:
        findings = exceptions.classify_reconciliation([], [_gstr2b()])
        assert _codes(findings) == {ReasonCode.EX_02}
        assert findings[0].itc_at_risk == Decimal("0.00")

    def test_ex11_2b_credit_note_with_no_books_reversal(self) -> None:
        findings = exceptions.classify_reconciliation(
            [], [_gstr2b(doc_type=DocType.CREDIT_NOTE, igst=Decimal("18.00"))]
        )
        assert _codes(findings) == {ReasonCode.EX_11}
        assert findings[0].itc_at_risk == Decimal("18.00")

    def test_ex12_books_credit_note_not_yet_in_2b(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(doc_type=DocType.CREDIT_NOTE)], []
        )
        assert _codes(findings) == {ReasonCode.EX_12}
        assert findings[0].itc_at_risk == Decimal("0.00")


class TestValueMismatches:
    def test_ex03_taxable_value_mismatch(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(taxable_value=Decimal("1000.00"))],
            [_gstr2b(taxable_value=Decimal("1100.00"))],
        )
        assert _codes(findings) == {ReasonCode.EX_03}

    def test_ex04_tax_amount_mismatch_carries_variance_as_at_risk(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(igst=Decimal("180.00"))], [_gstr2b(igst=Decimal("200.00"))]
        )
        assert _codes(findings) == {ReasonCode.EX_04}
        assert findings[0].itc_at_risk == Decimal("20.00")

    def test_ex05_head_wise_mismatch_when_total_agrees(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(igst=Decimal("180.00"), cess=Decimal("0.00"))],
            [_gstr2b(igst=Decimal("170.00"), cess=Decimal("10.00"))],
        )
        assert _codes(findings) == {ReasonCode.EX_05}

    def test_ex04_and_ex05_do_not_both_fire_for_the_same_head_change(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(igst=Decimal("180.00"))], [_gstr2b(igst=Decimal("300.00"))]
        )
        assert _codes(findings) == {ReasonCode.EX_04}


class TestInvoiceNumberVariance:
    def test_ex07_fires_when_doc_number_outright_differs(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(invoice_number="INV/0001")], [_gstr2b(invoice_number="INV/9999")]
        )
        assert _codes(findings) == {ReasonCode.EX_07}
        assert findings[0].itc_at_risk == Decimal("0.00")


class TestGstin:
    def test_ex06_probable_match_gstin_typo(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(gstin=GSTIN)], [_gstr2b(gstin=GSTIN_TYPO)]
        )
        assert _codes(findings) == {ReasonCode.EX_06}
        assert len(findings) == 1

    def test_ex06_structurally_invalid_gstin_fires_independent_of_match(self) -> None:
        # Everything else matches exactly, so this would otherwise be a
        # clean EXACT match -- the invalid GSTIN must still surface.
        findings = exceptions.classify_reconciliation(
            [_books(gstin=INVALID_GSTIN)], [_gstr2b(gstin=INVALID_GSTIN)]
        )
        assert ReasonCode.EX_06 in _codes(findings)
        # Fires once per invalid-GSTIN document, not once per pair.
        assert len([f for f in findings if f.reason_code is ReasonCode.EX_06]) == 2


class TestItcAvailability:
    def test_ex09_itc_flagged_unavailable_but_claimed(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books()], [_gstr2b(itc_availability=ItcAvailability.NOT_AVAILABLE)]
        )
        assert _codes(findings) == {ReasonCode.EX_09}
        assert findings[0].itc_at_risk == Decimal("180.00")

    def test_no_ex09_when_itc_available(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books()], [_gstr2b(itc_availability=ItcAvailability.AVAILABLE)]
        )
        assert findings == []


class TestPeriodTiming:
    def test_ex08_fires_when_return_period_differs_from_invoice_month(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(invoice_date=date(2024, 4, 15))],
            [_gstr2b(invoice_date=date(2024, 4, 15), return_period="052024")],
        )
        assert _codes(findings) == {ReasonCode.EX_08}

    def test_no_ex08_when_return_period_matches_invoice_month(self) -> None:
        findings = exceptions.classify_reconciliation(
            [_books(invoice_date=date(2024, 4, 15))],
            [_gstr2b(invoice_date=date(2024, 4, 15), return_period="042024")],
        )
        assert findings == []

    def test_no_ex08_when_return_period_absent(self) -> None:
        findings = exceptions.classify_reconciliation([_books()], [_gstr2b(return_period=None)])
        assert findings == []


class TestDuplicateBooking:
    def test_ex10_fires_for_surplus_copy_only(self) -> None:
        primary = _books(row_ref="b1")
        duplicate = _books(row_ref="b2")
        findings = exceptions.classify_reconciliation([primary, duplicate], [_gstr2b(row_ref="g1")])

        assert _codes(findings) == {ReasonCode.EX_10}
        assert len(findings) == 1
        assert findings[0].books_doc is not None and findings[0].books_doc.row_ref == "b2"
        assert findings[0].itc_at_risk == Decimal("180.00")

    def test_surplus_copy_does_not_also_fire_ex01(self) -> None:
        # Regression: an earlier version reported the *surplus* copy as BOTH
        # a duplicate and a missing-from-2B document. Here the primary copy
        # genuinely has no 2B match (the 2B list is empty), so it correctly
        # earns its own EX-01 -- the fix is that the surplus copy earns only
        # EX-10, not a second EX-01 on top of it.
        primary = _books(row_ref="b1")
        duplicate = _books(row_ref="b2")
        findings = exceptions.classify_reconciliation([primary, duplicate], [])

        assert len(findings) == 2
        ex01 = [f for f in findings if f.reason_code is ReasonCode.EX_01]
        ex10 = [f for f in findings if f.reason_code is ReasonCode.EX_10]
        assert len(ex01) == 1 and ex01[0].books_doc is not None
        assert ex01[0].books_doc.row_ref == "b1"
        assert len(ex10) == 1 and ex10[0].books_doc is not None
        assert ex10[0].books_doc.row_ref == "b2"


class TestCleanMatch:
    def test_exact_match_produces_no_findings(self) -> None:
        findings = exceptions.classify_reconciliation([_books()], [_gstr2b()])
        assert findings == []

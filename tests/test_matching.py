from datetime import date
from decimal import Decimal

from gstrecon import matching
from gstrecon.matching import MatchCategory
from gstrecon.models import DocSource, DocType, Document, TaxAmounts

GSTIN = "27AAPFU0939F1ZV"
# Differs from GSTIN by exactly one character -> similarity is high but not
# a coincidental match to some other real supplier.
GSTIN_TYPO = "27AAPFU0939F1ZQ"
OTHER_GSTIN = "07AAACH7409R1ZZ"


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
        row_ref=row_ref,
    )


def _books(**kwargs: object) -> Document:
    return _doc(DocSource.BOOKS, **kwargs)  # type: ignore[arg-type]


def _gstr2b(**kwargs: object) -> Document:
    return _doc(DocSource.GSTR_2B, **kwargs)  # type: ignore[arg-type]


class TestExactMatch:
    def test_identical_documents_are_exact(self) -> None:
        results = matching.reconcile([_books()], [_gstr2b()])
        assert len(results) == 1
        assert results[0].category is MatchCategory.EXACT
        assert results[0].mismatched_parameters == ()

    def test_case_and_separator_differences_still_exact(self) -> None:
        # strict_invoice_key is case/whitespace-insensitive only; identical
        # separators here so this stays an exact doc-number match.
        results = matching.reconcile(
            [_books(invoice_number="inv/0001 ")], [_gstr2b(invoice_number="INV/0001")]
        )
        assert results[0].category is MatchCategory.EXACT


class TestPartialMatch:
    def test_document_number_mismatch_only(self) -> None:
        results = matching.reconcile(
            [_books(invoice_number="INV/0001")], [_gstr2b(invoice_number="INV/9999")]
        )
        assert results[0].category is MatchCategory.PARTIAL
        assert results[0].mismatched_parameters == (matching.PARAM_DOC_NUMBER,)

    def test_document_number_approximate_match_counts_as_matching(self) -> None:
        # A separator-only difference: strict_invoice_key treats these as
        # different (different punctuation), but the loose key is identical,
        # so similarity is 100 -- GSTN's own "approximation logic" should
        # treat this as matching, not as a mismatch.
        results = matching.reconcile(
            [_books(invoice_number="INV-0001")], [_gstr2b(invoice_number="INV/0001")]
        )
        assert results[0].category is MatchCategory.EXACT

    def test_date_mismatch_only(self) -> None:
        results = matching.reconcile(
            [_books(invoice_date=date(2024, 4, 1))],
            [_gstr2b(invoice_date=date(2024, 4, 2))],
        )
        assert results[0].category is MatchCategory.PARTIAL
        assert results[0].mismatched_parameters == (matching.PARAM_DOC_DATE,)

    def test_taxable_value_mismatch_only(self) -> None:
        results = matching.reconcile(
            [_books(taxable_value=Decimal("1000.00"))],
            [_gstr2b(taxable_value=Decimal("1100.00"))],
        )
        assert results[0].category is MatchCategory.PARTIAL
        assert results[0].mismatched_parameters == (matching.PARAM_TAXABLE_VALUE,)

    def test_total_tax_mismatch_only(self) -> None:
        # Each head individually differs by 0.9 (within a tolerance of 1),
        # so head-wise passes -- but the two 0.9 differences compound on the
        # combined total, which is compared against the same tolerance and
        # so fails on its own. This is the mirror image of the offsetting-
        # heads case: here the total is the more sensitive parameter.
        results = matching.reconcile(
            [_books(igst=Decimal("100.00"), cess=Decimal("0.00"))],
            [_gstr2b(igst=Decimal("100.90"), cess=Decimal("0.90"))],
            tax_tolerance=Decimal("1"),
        )
        assert results[0].category is MatchCategory.PARTIAL
        assert results[0].mismatched_parameters == (matching.PARAM_TOTAL_TAX,)

    def test_head_wise_mismatch_with_matching_total_is_still_partial(self) -> None:
        # IGST short by 10, CESS over by 10: total tax is identical, but the
        # official "tax amount head wise" parameter must still fail. This is
        # the exact offsetting-heads scenario TaxAmounts.head_wise_matches
        # was built to catch.
        results = matching.reconcile(
            [_books(igst=Decimal("180.00"), cess=Decimal("0.00"))],
            [_gstr2b(igst=Decimal("170.00"), cess=Decimal("10.00"))],
        )
        assert results[0].category is MatchCategory.PARTIAL
        assert results[0].mismatched_parameters == (matching.PARAM_HEAD_WISE,)

    def test_tolerance_absorbs_small_rounding_difference(self) -> None:
        results = matching.reconcile(
            [_books(igst=Decimal("180.00"))],
            [_gstr2b(igst=Decimal("180.50"))],
            tax_tolerance=Decimal("1"),
        )
        assert results[0].category is MatchCategory.EXACT


class TestUnmatched:
    def test_identity_intact_multiple_value_mismatches(self) -> None:
        results = matching.reconcile(
            [_books(taxable_value=Decimal("1000.00"), igst=Decimal("180.00"))],
            [_gstr2b(taxable_value=Decimal("1200.00"), igst=Decimal("216.00"))],
        )
        assert results[0].category is MatchCategory.UNMATCHED
        # Changing IGST necessarily moves both the summed total and that
        # head individually, so all three value parameters legitimately
        # mismatch together here.
        assert set(results[0].mismatched_parameters) == {
            matching.PARAM_TAXABLE_VALUE,
            matching.PARAM_TOTAL_TAX,
            matching.PARAM_HEAD_WISE,
        }


class TestProbableMatch:
    def test_gstin_typo_with_everything_else_exact(self) -> None:
        results = matching.reconcile([_books(gstin=GSTIN)], [_gstr2b(gstin=GSTIN_TYPO)])
        assert results[0].category is MatchCategory.PROBABLE
        assert results[0].mismatched_parameters == (matching.PARAM_GSTIN,)

    def test_unrelated_gstin_is_not_a_probable_match(self) -> None:
        # Genuinely different supplier -- must not be proposed as a pairing
        # even if invoice number/date/amounts coincidentally match.
        results = matching.reconcile([_books(gstin=GSTIN)], [_gstr2b(gstin=OTHER_GSTIN)])
        categories = {r.category for r in results}
        assert MatchCategory.PROBABLE not in categories
        assert categories == {MatchCategory.IN_BOOKS_NOT_2B, MatchCategory.IN_2B_NOT_BOOKS}

    def test_gstin_typo_with_a_value_mismatch_is_not_probable(self) -> None:
        # Probable match requires every other parameter to agree exactly;
        # a value mismatch on top of a GSTIN typo has two unrelated problems
        # and should not be silently collapsed into one clean finding.
        results = matching.reconcile(
            [_books(gstin=GSTIN, taxable_value=Decimal("1000.00"))],
            [_gstr2b(gstin=GSTIN_TYPO, taxable_value=Decimal("1500.00"))],
        )
        categories = {r.category for r in results}
        assert MatchCategory.PROBABLE not in categories


class TestOrphans:
    def test_books_only_document(self) -> None:
        results = matching.reconcile([_books()], [])
        assert results[0].category is MatchCategory.IN_BOOKS_NOT_2B
        assert results[0].gstr2b_doc is None

    def test_gstr2b_only_document(self) -> None:
        results = matching.reconcile([], [_gstr2b()])
        assert results[0].category is MatchCategory.IN_2B_NOT_BOOKS
        assert results[0].books_doc is None


class TestDocTypeIsAHardAnchor:
    def test_invoice_never_pairs_with_credit_note(self) -> None:
        # Same GSTIN, invoice number, date, and amounts -- but different
        # doc types. Must never be proposed as a match regardless of how
        # closely everything else lines up.
        results = matching.reconcile(
            [_books(doc_type=DocType.INVOICE)],
            [_gstr2b(doc_type=DocType.CREDIT_NOTE)],
        )
        categories = {r.category for r in results}
        assert categories == {MatchCategory.IN_BOOKS_NOT_2B, MatchCategory.IN_2B_NOT_BOOKS}


class TestGreedyDisambiguation:
    def test_duplicate_invoice_number_prefers_the_better_match(self) -> None:
        # Two 2B invoices share a books invoice's (mistyped) number; only the
        # one with matching amounts should be paired -- the other must be
        # left as an orphan, not double-matched or matched arbitrarily.
        books_doc = _books(invoice_number="INV/0001", taxable_value=Decimal("1000.00"))
        good_2b = _gstr2b(
            invoice_number="INV/0001", taxable_value=Decimal("1000.00"), row_ref="good"
        )
        bad_2b = _gstr2b(
            invoice_number="INV/0001", taxable_value=Decimal("5000.00"), row_ref="bad"
        )

        results = matching.reconcile([books_doc], [good_2b, bad_2b])

        exact = [r for r in results if r.category is MatchCategory.EXACT]
        assert len(exact) == 1
        assert exact[0].gstr2b_doc is not None and exact[0].gstr2b_doc.row_ref == "good"

        orphans = [r for r in results if r.category is MatchCategory.IN_2B_NOT_BOOKS]
        assert len(orphans) == 1
        assert orphans[0].gstr2b_doc is not None and orphans[0].gstr2b_doc.row_ref == "bad"

    def test_no_document_is_matched_twice(self) -> None:
        books_docs = [
            _books(invoice_number="INV/0001", row_ref="b1"),
            _books(invoice_number="INV/0002", row_ref="b2"),
        ]
        gstr2b_docs = [
            _gstr2b(invoice_number="INV/0001", row_ref="g1"),
            _gstr2b(invoice_number="INV/0002", row_ref="g2"),
        ]
        results = matching.reconcile(books_docs, gstr2b_docs)
        matched_books_refs = [r.books_doc.row_ref for r in results if r.books_doc]
        matched_2b_refs = [r.gstr2b_doc.row_ref for r in results if r.gstr2b_doc]
        assert len(matched_books_refs) == len(set(matched_books_refs))
        assert len(matched_2b_refs) == len(set(matched_2b_refs))

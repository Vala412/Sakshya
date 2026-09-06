from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from gstrecon import ingest
from gstrecon.models import DocSource, DocType, ItcAvailability

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseGstr2bJson:
    @staticmethod
    @pytest.fixture(scope="class")
    def documents() -> list:
        return ingest.parse_gstr2b_json(FIXTURES / "gstr2b_sample.json")

    def test_total_document_count(self, documents: list) -> None:
        # 2 b2b invoices + 1 credit note + 1 debit note
        assert len(documents) == 4

    def test_b2b_invoice_fields(self, documents: list) -> None:
        inv = next(d for d in documents if d.invoice_number == "INV/0001")
        assert inv.source is DocSource.GSTR_2B
        assert inv.doc_type is DocType.INVOICE
        assert inv.supplier_gstin == "27AAPFU0939F1ZV"
        assert inv.supplier_name == "Acme Traders Pvt Ltd"
        assert inv.invoice_date == date(2024, 4, 1)
        assert inv.taxable_value == Decimal("1000.00")
        assert inv.tax.igst == Decimal("180.00")
        assert inv.itc_availability is ItcAvailability.AVAILABLE
        assert inv.row_ref == "gstr2b_sample.json.b2b[0].inv[0]"

    def test_taxable_value_falls_back_when_txval_absent(self, documents: list) -> None:
        inv = next(d for d in documents if d.invoice_number == "INV/0002")
        # val=590.00, tax total = 90.00 -> derived taxable value = 500.00
        assert inv.taxable_value == Decimal("500.00")
        assert inv.itc_availability is ItcAvailability.NOT_AVAILABLE

    def test_cdnr_credit_note(self, documents: list) -> None:
        cn = next(d for d in documents if d.invoice_number == "CN/0001")
        assert cn.doc_type is DocType.CREDIT_NOTE
        assert cn.signed_tax == Decimal("-18.00")

    def test_cdnr_debit_note(self, documents: list) -> None:
        dn = next(d for d in documents if d.invoice_number == "DN/0001")
        assert dn.doc_type is DocType.DEBIT_NOTE
        assert dn.signed_tax == Decimal("36.00")

    def test_missing_top_level_key_raises_schema_mismatch(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"nope": {}}')
        with pytest.raises(ingest.SchemaMismatchError):
            ingest.parse_gstr2b_json(bad_file)

    def test_missing_invoice_field_raises_schema_mismatch(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(
            '{"data": {"docdata": {"b2b": [{"ctin": "27AAPFU0939F1ZV", '
            '"inv": [{"dt": "01-04-2024"}]}]}}}'
        )
        with pytest.raises(ingest.SchemaMismatchError, match="inum"):
            ingest.parse_gstr2b_json(bad_file)

    def test_missing_both_value_fields_raises_schema_mismatch(self, tmp_path: Path) -> None:
        # Regression: with neither "txval" nor "val" present, taxable value
        # used to silently compute as `0 - tax.total` (a negative number)
        # instead of raising -- exactly the kind of quietly-wrong data this
        # parser is supposed to catch rather than propagate.
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(
            '{"data": {"docdata": {"b2b": [{"ctin": "27AAPFU0939F1ZV", "inv": '
            '[{"inum": "INV/0001", "dt": "01-04-2024", "iamt": "18.00"}]}]}}}'
        )
        with pytest.raises(ingest.SchemaMismatchError, match="txval.*val"):
            ingest.parse_gstr2b_json(bad_file)

    def test_unrecognized_itcavl_value_raises_schema_mismatch(self, tmp_path: Path) -> None:
        # Regression: an earlier version constructed ItcAvailability(raw)
        # directly, so an unexpected value crashed with a bare pydantic/enum
        # ValueError instead of a clear, located SchemaMismatchError.
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(
            '{"data": {"docdata": {"b2b": [{"ctin": "27AAPFU0939F1ZV", "inv": '
            '[{"inum": "INV/0001", "dt": "01-04-2024", "txval": "100.00", '
            '"itcavl": "MAYBE"}]}]}}}'
        )
        with pytest.raises(ingest.SchemaMismatchError, match="itcavl"):
            ingest.parse_gstr2b_json(bad_file)


class TestParseBooksCsv:
    @staticmethod
    @pytest.fixture(scope="class")
    def documents() -> list:
        return ingest.parse_books_csv(FIXTURES / "books_sample.csv")

    def test_junk_rows_are_rejected(self, documents: list) -> None:
        # 2 invoices + 1 credit note; the "Grand Total" row must be dropped.
        assert len(documents) == 3
        assert all(d.invoice_number != "" for d in documents)
        assert all(d.supplier_gstin for d in documents)

    def test_invoice_row_fields(self, documents: list) -> None:
        inv = next(d for d in documents if d.invoice_number == "INV/0001")
        assert inv.source is DocSource.BOOKS
        assert inv.doc_type is DocType.INVOICE
        assert inv.supplier_gstin == "27AAPFU0939F1ZV"
        assert inv.invoice_date == date(2024, 4, 1)
        assert inv.taxable_value == Decimal("1000.00")
        assert inv.tax.igst == Decimal("180.00")
        assert inv.row_ref == "books_sample.csv:5"

    def test_voucher_type_maps_to_credit_note(self, documents: list) -> None:
        cn = next(d for d in documents if d.invoice_number == "CN/0001")
        assert cn.doc_type is DocType.CREDIT_NOTE

    def test_header_row_is_located_past_report_title_rows(self, documents: list) -> None:
        # Header detection must skip the two leading report-title rows and
        # the blank line before finding the real column header.
        assert {d.invoice_number for d in documents} == {"INV/0001", "INV/0002", "CN/0001"}

    def test_missing_header_raises_schema_mismatch(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.csv"
        bad_file.write_text("Not,A,Real,Header\n1,2,3,4\n")
        with pytest.raises(ingest.SchemaMismatchError):
            ingest.parse_books_csv(bad_file)

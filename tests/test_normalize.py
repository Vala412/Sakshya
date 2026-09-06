from datetime import date
from decimal import Decimal

import pytest

from gstrecon import normalize


class TestGstin:
    def test_known_valid_gstin_checksum(self) -> None:
        # Independently published real-world example, used across multiple
        # GST tutorials -- not synthesized by this codebase.
        assert normalize.is_valid_gstin("27AAPFU0939F1ZV") is True

    def test_corrupted_checksum_is_invalid(self) -> None:
        assert normalize.is_valid_gstin("27AAPFU0939F1ZW") is False

    def test_wrong_length_is_invalid(self) -> None:
        assert normalize.is_valid_gstin("27AAPFU0939F1Z") is False

    def test_lowercase_and_whitespace_are_tolerated(self) -> None:
        assert normalize.is_valid_gstin(" 27aapfu0939f1zv ") is True

    def test_malformed_structure_is_invalid(self) -> None:
        # 14th char must be 'Z'; this swaps it for '9'.
        assert normalize.is_valid_gstin("27AAPFU0939F19V") is False

    def test_similarity_of_identical_gstins_is_100(self) -> None:
        assert normalize.gstin_similarity("27AAPFU0939F1ZV", "27AAPFU0939F1ZV") == 100.0

    def test_similarity_drops_for_single_typo(self) -> None:
        score = normalize.gstin_similarity("27AAPFU0939F1ZV", "27AAPFU0939F1ZX")
        assert 80.0 < score < 100.0


class TestInvoiceKeys:
    def test_strict_key_is_case_and_whitespace_insensitive(self) -> None:
        assert normalize.strict_invoice_key(" inv/0005 ") == "INV/0005"

    def test_strict_key_preserves_separators(self) -> None:
        assert normalize.strict_invoice_key("INV/0005") != normalize.strict_invoice_key(
            "INV-0005"
        )

    def test_loose_key_ignores_separator_style(self) -> None:
        variants = ["INV/0005", "INV-0005", "INV 0005", "inv0005"]
        keys = {normalize.loose_invoice_key(v) for v in variants}
        assert keys == {"INV0005"}

    def test_loose_key_does_not_collapse_leading_zeros(self) -> None:
        # Regression: an earlier implementation stripped leading zeros with
        # re.sub(r"0+(\d)", r"\1"), merging INV/0005 and INV/0050 into one
        # key even though they are two distinct invoices (#5 and #50).
        assert normalize.loose_invoice_key("INV/0005") != normalize.loose_invoice_key(
            "INV/0050"
        )

    def test_invoice_similarity_high_for_transposed_digit(self) -> None:
        score = normalize.invoice_number_similarity("INV/1234", "INV/1243")
        assert score > 80.0

    def test_invoice_similarity_ignores_separator_differences(self) -> None:
        assert normalize.invoice_number_similarity("INV/0005", "INV-0005") == 100.0


class TestParseDate:
    @pytest.mark.parametrize(
        "text",
        ["01-04-2024", "01/04/2024", "2024-04-01", "1-Apr-2024", "1-Apr-24", "1/4/24"],
    )
    def test_recognized_formats(self, text: str) -> None:
        assert normalize.parse_date(text) == date(2024, 4, 1)

    def test_passthrough_for_date_objects(self) -> None:
        d = date(2024, 4, 1)
        assert normalize.parse_date(d) is d

    def test_unrecognized_format_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize.parse_date("not-a-date")


class TestParseAmount:
    def test_plain_decimal_string(self) -> None:
        assert normalize.parse_amount("1234.50") == Decimal("1234.50")

    def test_indian_comma_grouping(self) -> None:
        assert normalize.parse_amount("1,23,456.78") == Decimal("123456.78")

    def test_rupee_symbol_and_whitespace(self) -> None:
        assert normalize.parse_amount("₹ 1,000.00") == Decimal("1000.00")

    def test_parenthesized_negative(self) -> None:
        assert normalize.parse_amount("(500.00)") == Decimal("-500.00")

    def test_blank_and_none_are_zero(self) -> None:
        assert normalize.parse_amount(None) == Decimal("0.00")
        assert normalize.parse_amount("") == Decimal("0.00")

    def test_numeric_inputs(self) -> None:
        assert normalize.parse_amount(1000) == Decimal("1000.00")
        assert normalize.parse_amount(1000.5) == Decimal("1000.50")

    def test_garbage_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize.parse_amount("not-a-number")

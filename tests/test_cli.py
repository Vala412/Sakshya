from pathlib import Path

from typer.testing import CliRunner

from gstrecon.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_reconcile_writes_working_paper_and_reports_summary(tmp_path: Path) -> None:
    output_path = tmp_path / "working_paper.xlsx"
    result = runner.invoke(
        app,
        [
            str(FIXTURES / "books_sample.csv"),
            str(FIXTURES / "gstr2b_sample.json"),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    assert "Closing variance:   0.00" in result.output
    assert "Wrote" in result.output


def test_missing_columns_reports_schema_error(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Not,A,Real,Header\n1,2,3,4\n")

    result = runner.invoke(
        app, [str(bad_csv), str(FIXTURES / "gstr2b_sample.json")]
    )

    assert result.exit_code == 1
    assert "Input format error" in result.output


def test_malformed_json_reports_clean_error_not_a_traceback(tmp_path: Path) -> None:
    # Regression: an earlier version only caught SchemaMismatchError, so a
    # file that isn't valid JSON at all (json.JSONDecodeError, which
    # SchemaMismatchError does not subclass) produced a raw traceback
    # instead of a clean CLI error.
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json")

    result = runner.invoke(app, [str(FIXTURES / "books_sample.csv"), str(bad_json)])

    assert result.exit_code == 1
    assert "Input format error" in result.output


def test_unparseable_date_reports_clean_error_not_a_traceback(tmp_path: Path) -> None:
    # Regression: normalize.parse_date raises a plain ValueError (not a
    # SchemaMismatchError), which an earlier version of the CLI didn't
    # catch at all -- a well-structured CSV with one bad date cell crashed
    # with a raw traceback instead of a clean, actionable message.
    bad_csv = tmp_path / "bad_date.csv"
    bad_csv.write_text(
        "Date,Party Name,GSTIN,Voucher Type,Invoice No,Taxable Value,IGST,CGST,SGST,CESS\n"
        "not-a-date,Acme,27AAPFU0939F1ZV,Purchase,INV/0001,1000.00,180.00,0.00,0.00,0.00\n"
    )

    result = runner.invoke(app, [str(bad_csv), str(FIXTURES / "gstr2b_sample.json")])

    assert result.exit_code == 1
    assert "Input format error" in result.output


def test_garbage_tax_tolerance_reports_clean_error_not_a_traceback() -> None:
    # Regression: Decimal("abc") raises decimal.InvalidOperation, which
    # does NOT subclass ValueError -- an earlier version of the CLI parsed
    # --tax-tolerance outside any try/except, so this crashed with a raw
    # traceback instead of a clean CLI error.
    result = runner.invoke(
        app,
        [
            str(FIXTURES / "books_sample.csv"),
            str(FIXTURES / "gstr2b_sample.json"),
            "--tax-tolerance",
            "not-a-number",
        ],
    )

    assert result.exit_code == 1
    assert "Input format error" in result.output

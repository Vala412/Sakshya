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

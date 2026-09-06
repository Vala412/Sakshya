"""CLI entry point: `gstrecon reconcile <books.csv> <gstr2b.json> -o <out.xlsx>`."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import typer

from gstrecon import ingest, report
from gstrecon.exceptions import DEFAULT_TAX_TOLERANCE, reconcile_full
from gstrecon.matching import DEFAULT_GSTIN_FUZZY_THRESHOLD, DEFAULT_INVOICE_FUZZY_THRESHOLD

app = typer.Typer(
    add_completion=False,
    help="Books-vs-GSTR-2B reconciliation: produces an audit-defensible Excel working paper.",
)


@app.command()
def reconcile(
    books: Path = typer.Argument(
        ..., exists=True, readable=True, help="Tally purchase-register CSV export"
    ),
    gstr2b: Path = typer.Argument(..., exists=True, readable=True, help="GSTR-2B JSON export"),
    output: Path = typer.Option(
        Path("working_paper.xlsx"), "--output", "-o", help="Output .xlsx path"
    ),
    tax_tolerance: str = typer.Option(
        str(DEFAULT_TAX_TOLERANCE),
        "--tax-tolerance",
        help="Per-tax-head tolerance in rupees. GSTN's own Matching Offline Tool allows 0-10.",
    ),
) -> None:
    """Reconcile a books export against a GSTR-2B export and write the
    three-sheet working paper (ITC Bridge, Exception Register,
    Reproducibility) to `output`.
    """
    # Every expected "bad input" failure in this pipeline surfaces as one of
    # these two: ValueError (SchemaMismatchError is a subclass, and so --
    # in Python's stdlib -- is json.JSONDecodeError raised by a malformed
    # GSTR-2B file; normalize.parse_date/parse_amount also raise plain
    # ValueError for an unparseable cell) or InvalidOperation (Decimal
    # doesn't subclass ValueError, so a garbage --tax-tolerance needs its
    # own arm). Catching broadly here -- rather than only SchemaMismatchError,
    # as an earlier version did -- is deliberate: a malformed date deep in a
    # CSV is just as much a "bad input" case as a missing column, and both
    # deserve a clean CLI message instead of a raw traceback. A genuine
    # internal bug (anything not raised by input parsing) is intentionally
    # left to propagate with its full traceback rather than swallowed here.
    try:
        parsed_tolerance = Decimal(tax_tolerance)
        books_docs = ingest.parse_books_csv(books)
        gstr2b_docs = ingest.parse_gstr2b_json(gstr2b)
    except (ValueError, InvalidOperation) as exc:
        typer.secho(f"Input format error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    reconciliation = reconcile_full(books_docs, gstr2b_docs, tax_tolerance=parsed_tolerance)
    metadata = report.RunMetadata(
        books_path=books,
        gstr2b_path=gstr2b,
        tax_tolerance=parsed_tolerance,
        invoice_fuzzy_threshold=DEFAULT_INVOICE_FUZZY_THRESHOLD,
        gstin_fuzzy_threshold=DEFAULT_GSTIN_FUZZY_THRESHOLD,
        books_document_count=len(books_docs),
        gstr2b_document_count=len(gstr2b_docs),
    )
    bridge = report.write_working_paper(
        output,
        books_docs=books_docs,
        gstr2b_docs=gstr2b_docs,
        reconciliation=reconciliation,
        metadata=metadata,
    )

    typer.echo(f"Wrote {output}")
    typer.echo(f"  Books documents:    {len(books_docs)}")
    typer.echo(f"  GSTR-2B documents:  {len(gstr2b_docs)}")
    typer.echo(f"  Exceptions raised:  {len(reconciliation.findings)}")
    typer.echo(f"  ITC as per books:   {bridge.books_total}")
    typer.echo(f"  ITC as per 2B:      {bridge.gstr2b_total_available}")
    typer.echo(f"  Closing variance:   {bridge.closing_variance}")

    if bridge.closing_variance != Decimal("0.00"):
        # This can only mean the bridge's own arithmetic identity broke, not
        # a real reconciliation finding -- see report.py's module docstring.
        typer.secho(
            "WARNING: ITC bridge did not tie to nil. This indicates an "
            "engine defect, not a genuine reconciliation finding -- please "
            "report it.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()

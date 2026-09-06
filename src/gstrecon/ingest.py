"""Ingestion: parse a GSTR-2B JSON export and a books (Tally) purchase-register
CSV into a common list[Document].

GSTR-2B JSON field names, sourced
----------------------------------
GSTN has never published an official GSTR-2B JSON schema (see project notes).
The fields used below are triangulated, not guaranteed:

  CONFIRMED against a real, independently-published parsing snippet:
    data.data.docdata.b2b -> [{ctin, trdnm, inv: [{inum, dt, iamt, camt,
    samt, itcavl}]}]

  INFERRED by convention from GSTR-1's item-level JSON schema (which is
  publicly documented for GSP/ASP filing integrations, and which 2B's
  auto-draft process likely inherits naming from), never independently
  confirmed for 2B specifically:
    - "txval" for taxable value (as distinct from "val", the total value)
    - "csamt" for the CESS amount
    - the entire "cdnr" section's shape (ntnum/typ/ntdt), by analogy to b2b

If a real GSTR-2B export doesn't match this, `parse_gstr2b_json` raises
`SchemaMismatchError` naming the exact missing key and JSON path, rather than
silently defaulting -- so the gap surfaces immediately against real data
instead of producing quietly-wrong Documents.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from gstrecon import normalize
from gstrecon.models import DocSource, DocType, Document, ItcAvailability, TaxAmounts


class SchemaMismatchError(ValueError):
    """A source file didn't match the expected shape at a specific location.

    Distinct from a plain ValueError so callers (and the CLI) can catch it
    to give the user a "the input format doesn't match what this engine
    expects" message rather than a bare stack trace.
    """


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise SchemaMismatchError(f"Missing expected field {key!r} at {where}")
    return mapping[key]


# ---------------------------------------------------------------------------
# GSTR-2B JSON
# ---------------------------------------------------------------------------
def parse_gstr2b_json(path: str | Path) -> list[Document]:
    """Parse a GSTR-2B JSON export into Documents (b2b invoices + cdnr notes).

    Only b2b and cdnr are handled -- see the "Known gaps" note in project
    docs: B2BA/CDNRA (amendments), IMPG/IMPGSEZ, ISD, and e-commerce sections
    are not covered, and an amended invoice will currently read as a second,
    unmatched document rather than a revision of the original.
    """
    path = Path(path)
    raw = json.loads(path.read_text())
    data = _require(raw, "data", path.name)
    docdata = _require(data, "docdata", f"{path.name}.data")
    # The statement's own return period ("rtnprd", conventionally MMYYYY) --
    # like everything else in this parser, this key is inferred by
    # convention from other GST return JSON schemas, not confirmed against a
    # real 2B export. Left as None (rather than raising) when absent, so a
    # missing/renamed field degrades to "EX-08 never fires" instead of
    # breaking ingestion of every other document in the file.
    return_period = data.get("rtnprd")

    documents: list[Document] = []
    documents.extend(_parse_2b_b2b(docdata.get("b2b", []), path.name, return_period))
    documents.extend(_parse_2b_cdnr(docdata.get("cdnr", []), path.name, return_period))
    return documents


def _tax_amounts_from_2b(item: dict[str, Any], where: str) -> TaxAmounts:
    return TaxAmounts(
        igst=normalize.parse_amount(item.get("iamt")),
        cgst=normalize.parse_amount(item.get("camt")),
        sgst=normalize.parse_amount(item.get("samt")),
        cess=normalize.parse_amount(item.get("csamt")),
    )


def _taxable_value_from_2b(item: dict[str, Any], tax: TaxAmounts, where: str) -> Decimal:
    """Prefer an explicit taxable-value field; fall back to deriving it from
    the total value minus tax, since it's unconfirmed whether "txval" is
    actually present on every real export (see module docstring).

    Raises if *neither* field is present rather than silently computing
    `0 - tax.total` (a negative taxable value that would then propagate
    into every downstream comparison and the ITC bridge as quietly wrong
    data) -- a missing amount field is exactly the kind of schema drift
    this module is designed to surface immediately, not paper over.
    """
    if "txval" in item:
        return normalize.parse_amount(item["txval"])
    if "val" in item:
        total_value = normalize.parse_amount(item["val"])
        return total_value - tax.total
    raise SchemaMismatchError(f"Missing both 'txval' and 'val' fields at {where}")


def _itc_availability(item: dict[str, Any], where: str) -> ItcAvailability | None:
    raw = item.get("itcavl")
    if raw is None:
        return None
    normalized = str(raw).strip().upper()
    try:
        return ItcAvailability(normalized)
    except ValueError as exc:
        raise SchemaMismatchError(
            f"Unrecognized itcavl value {raw!r} at {where} (expected 'Y' or 'N')"
        ) from exc


def _parse_2b_b2b(
    suppliers: list[dict[str, Any]], filename: str, return_period: str | None
) -> list[Document]:
    documents: list[Document] = []
    for s_idx, supplier in enumerate(suppliers):
        where = f"{filename}.b2b[{s_idx}]"
        ctin = _require(supplier, "ctin", where)
        trdnm = supplier.get("trdnm")
        for i_idx, inv in enumerate(supplier.get("inv", [])):
            inv_where = f"{where}.inv[{i_idx}]"
            tax = _tax_amounts_from_2b(inv, inv_where)
            documents.append(
                Document(
                    source=DocSource.GSTR_2B,
                    doc_type=DocType.INVOICE,
                    supplier_gstin=ctin,
                    supplier_name=trdnm,
                    invoice_number=str(_require(inv, "inum", inv_where)),
                    invoice_date=normalize.parse_date(_require(inv, "dt", inv_where)),
                    taxable_value=_taxable_value_from_2b(inv, tax, inv_where),
                    tax=tax,
                    itc_availability=_itc_availability(inv, inv_where),
                    return_period=return_period,
                    row_ref=inv_where,
                )
            )
    return documents


def _parse_2b_cdnr(
    suppliers: list[dict[str, Any]], filename: str, return_period: str | None
) -> list[Document]:
    documents: list[Document] = []
    for s_idx, supplier in enumerate(suppliers):
        where = f"{filename}.cdnr[{s_idx}]"
        ctin = _require(supplier, "ctin", where)
        trdnm = supplier.get("trdnm")
        for n_idx, note in enumerate(supplier.get("nt", [])):
            note_where = f"{where}.nt[{n_idx}]"
            tax = _tax_amounts_from_2b(note, note_where)
            note_type = str(_require(note, "typ", note_where)).strip().upper()
            doc_type = DocType.CREDIT_NOTE if note_type == "C" else DocType.DEBIT_NOTE
            documents.append(
                Document(
                    source=DocSource.GSTR_2B,
                    doc_type=doc_type,
                    supplier_gstin=ctin,
                    supplier_name=trdnm,
                    invoice_number=str(_require(note, "ntnum", note_where)),
                    invoice_date=normalize.parse_date(_require(note, "ntdt", note_where)),
                    taxable_value=_taxable_value_from_2b(note, tax, note_where),
                    tax=tax,
                    itc_availability=_itc_availability(note, note_where),
                    return_period=return_period,
                    row_ref=note_where,
                )
            )
    return documents


# ---------------------------------------------------------------------------
# Books (Tally) purchase-register CSV
# ---------------------------------------------------------------------------
# Tally's CSV export is template-configurable, not a fixed schema -- and
# every export carries a few report-header rows (report title, GSTIN, date
# range, a blank line) before the actual column header. Header detection
# scans for the first row containing enough recognizable column names to be
# confident it's the real header, rather than assuming a fixed row number.
_REQUIRED_COLUMNS = {"gstin", "invoice no", "date", "taxable value"}
_COLUMN_ALIASES = {
    "gstin": {"gstin", "supplier gstin", "party gstin"},
    "invoice_no": {"invoice no", "invoice number", "voucher no", "bill no"},
    "date": {"date", "voucher date", "invoice date"},
    "supplier_name": {"party name", "supplier name", "ledger name"},
    "taxable_value": {"taxable value", "taxable amt", "assessable value"},
    "igst": {"igst", "integrated tax"},
    "cgst": {"cgst", "central tax"},
    "sgst": {"sgst", "state tax", "utgst"},
    "cess": {"cess"},
    "voucher_type": {"voucher type", "type"},
}


def _normalize_header_cell(cell: str) -> str:
    return cell.strip().lower()


def _find_header_row(rows: list[list[str]]) -> int:
    for idx, row in enumerate(rows):
        normalized = {_normalize_header_cell(c) for c in row}
        matches = {field for field, aliases in _COLUMN_ALIASES.items() if normalized & aliases}
        if {"gstin", "invoice_no", "date", "taxable_value"} <= matches:
            return idx
    raise SchemaMismatchError(
        "Could not locate a header row containing GSTIN, invoice number, "
        "date, and taxable value columns (checked against known Tally "
        "export column-name aliases)."
    )


def _build_column_map(header_row: list[str]) -> dict[str, int]:
    column_map: dict[str, int] = {}
    for position, cell in enumerate(header_row):
        normalized = _normalize_header_cell(cell)
        for field, aliases in _COLUMN_ALIASES.items():
            if normalized in aliases and field not in column_map:
                column_map[field] = position
    return column_map


def _is_junk_row(row: list[str], column_map: dict[str, int]) -> bool:
    """Reject summary/blank rows a Tally export appends after the data (e.g.
    a "Grand Total" line): a real transaction row always has a GSTIN and an
    invoice number, a totals row never does.
    """
    gstin_col = column_map.get("gstin")
    invoice_col = column_map.get("invoice_no")
    if gstin_col is None or invoice_col is None:
        return True
    if gstin_col >= len(row) or invoice_col >= len(row):
        return True
    return not row[gstin_col].strip() or not row[invoice_col].strip()


def _cell(row: list[str], column_map: dict[str, int], field: str) -> str | None:
    col = column_map.get(field)
    if col is None or col >= len(row):
        return None
    return row[col]


def _voucher_type_to_doc_type(raw: str | None) -> DocType:
    if raw is None:
        return DocType.INVOICE
    normalized = raw.strip().lower()
    if "credit" in normalized:
        return DocType.CREDIT_NOTE
    if "debit" in normalized:
        return DocType.DEBIT_NOTE
    return DocType.INVOICE


def parse_books_csv(path: str | Path) -> list[Document]:
    """Parse a Tally purchase-register CSV export into Documents.

    Encoding is read as utf-8-sig so a UTF-8 BOM (common from Tally exports
    on Windows) doesn't get treated as a stray character in the first
    header cell.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header_idx = _find_header_row(rows)
    column_map = _build_column_map(rows[header_idx])

    documents: list[Document] = []
    for row_number, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if _is_junk_row(row, column_map):
            continue

        tax = TaxAmounts(
            igst=normalize.parse_amount(_cell(row, column_map, "igst")),
            cgst=normalize.parse_amount(_cell(row, column_map, "cgst")),
            sgst=normalize.parse_amount(_cell(row, column_map, "sgst")),
            cess=normalize.parse_amount(_cell(row, column_map, "cess")),
        )
        documents.append(
            Document(
                source=DocSource.BOOKS,
                doc_type=_voucher_type_to_doc_type(_cell(row, column_map, "voucher_type")),
                supplier_gstin=(_cell(row, column_map, "gstin") or "").strip(),
                supplier_name=_cell(row, column_map, "supplier_name"),
                invoice_number=(_cell(row, column_map, "invoice_no") or "").strip(),
                invoice_date=normalize.parse_date(_cell(row, column_map, "date") or ""),
                taxable_value=normalize.parse_amount(_cell(row, column_map, "taxable_value")),
                tax=tax,
                row_ref=f"{path.name}:{row_number}",
            )
        )
    return documents

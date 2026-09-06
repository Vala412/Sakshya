#!/usr/bin/env python3
"""Generate a labelled synthetic books+GSTR-2B dataset with exactly one
injected defect per non-clean case, plus the ground truth of which reason
code each case should produce.

Why synthetic, and why one defect per case: there is no real GSTR-2B/Tally
sample available (see project constraints), and even with one, a real file
wouldn't come with a ground-truth label saying which reason code *should*
fire for each row. One-defect-per-case is what makes per-code precision and
recall computable at all -- with multiple interacting defects per case,
"did EX-04 fire correctly" and "did EX-04 fire only because EX-09 also fired
on the same row" become impossible to tell apart from the outside.

Every case's identity is threaded through the invoice/note number as
"SYN{case_id:05d}...". Evaluate.py recovers case_id by regex-searching
whichever document survives in a finding; see `CASE_ID_RE` in evaluate.py.
The one case that deliberately mangles its own GSTR-2B-side invoice number
(EX-07) keeps the marker intact on the *books* side specifically so that
recovery still works -- see `_ex07` below.

Output: data/synthetic/books.csv, data/synthetic/gstr2b.json (real files
round-tripped through gstrecon.ingest, not in-memory Document objects
directly -- this exercises the same ingestion path a real user hits), and
data/synthetic/ground_truth.json (case_id -> expected reason codes).
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from gstrecon import normalize
from gstrecon.exceptions import ReasonCode
from gstrecon.models import DocSource, DocType, Document, ItcAvailability, TaxAmounts

# All "normal" cases are dated within this month; the file's own GSTR-2B
# return period is fixed to it too, so EX-08 can be injected by dating just
# that one case's documents a month earlier without every other case in the
# same file spuriously tripping the same check (return_period is one value
# per *file*, not per document -- see ingest.py).
NORMAL_MONTH = (2024, 4)
RETURN_PERIOD = "042024"
EX08_MONTH = (2024, 3)

CASE_ID_WIDTH = 5


def _case_marker(case_id: int) -> str:
    return f"SYN{case_id:0{CASE_ID_WIDTH}d}"


def _make_supplier_gstins(n: int) -> list[str]:
    """n distinct, checksum-valid GSTINs sharing a state code/PAN-letter
    pattern (varying only the numeric PAN segment) -- enough to spread cases
    across multiple "suppliers" without needing real registration data.
    """
    gstins = []
    for i in range(n):
        prefix = f"27AAAPA{i:04d}A1Z"
        assert len(prefix) == 14
        gstins.append(prefix + normalize.gstin_check_digit(prefix))
    return gstins


def _typo_gstin(gstin: str, rng: random.Random) -> str:
    """Flip one non-checksum character and recompute the checksum -- a
    single-keystroke error that's still a structurally valid GSTIN, high
    similarity to the original (recovers via matching.py's Probable-match
    path), but not a byte-for-byte match.
    """
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    position = rng.randint(2, 6)  # inside the 5-letter PAN segment
    chars = list(gstin[:14])
    original = chars[position]
    replacement = rng.choice([c for c in alphabet[10:] if c != original])
    chars[position] = replacement
    prefix = "".join(chars)
    return prefix + normalize.gstin_check_digit(prefix)


@dataclass
class SyntheticCase:
    case_id: int
    reason_code: ReasonCode | None  # None for a clean case
    description: str
    books_docs: list[Document] = field(default_factory=list)
    gstr2b_docs: list[Document] = field(default_factory=list)


def _clean_pair(
    case_id: int,
    rng: random.Random,
    gstins: list[str],
    *,
    doc_type: DocType = DocType.INVOICE,
    split_heads: bool = False,
    month: tuple[int, int] = NORMAL_MONTH,
) -> tuple[Document, Document]:
    gstin = rng.choice(gstins)
    invoice_number = _case_marker(case_id)
    year, month_no = month
    invoice_date = date(year, month_no, rng.randint(1, 28))
    taxable_value = Decimal(rng.randint(500, 50_000))

    if split_heads:
        half = (taxable_value * Decimal("9") / Decimal("100")).quantize(Decimal("0.01"))
        tax = TaxAmounts(cgst=half, sgst=half)
    else:
        igst = (taxable_value * Decimal("18") / Decimal("100")).quantize(Decimal("0.01"))
        tax = TaxAmounts(igst=igst)

    books = Document(
        source=DocSource.BOOKS,
        doc_type=doc_type,
        supplier_gstin=gstin,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        taxable_value=taxable_value,
        tax=tax,
        row_ref=f"synthetic-books-{case_id}",
    )
    gstr2b = Document(
        source=DocSource.GSTR_2B,
        doc_type=doc_type,
        supplier_gstin=gstin,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        taxable_value=taxable_value,
        tax=tax,
        itc_availability=ItcAvailability.AVAILABLE,
        return_period=RETURN_PERIOD,
        row_ref=f"synthetic-2b-{case_id}",
    )
    return books, gstr2b


def _case(
    case_id: int, code: ReasonCode | None, rng: random.Random, gstins: list[str]
) -> SyntheticCase:
    if code is None:
        books, gstr2b = _clean_pair(case_id, rng, gstins)
        return SyntheticCase(case_id, None, "clean, no defect", [books], [gstr2b])

    builder = _BUILDERS[code]
    return builder(case_id, rng, gstins)


def _ex01(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, _ = _clean_pair(case_id, rng, gstins)
    return SyntheticCase(case_id, ReasonCode.EX_01, "books invoice missing from 2B", [books], [])


def _ex02(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    _, gstr2b = _clean_pair(case_id, rng, gstins)
    return SyntheticCase(case_id, ReasonCode.EX_02, "2B invoice missing from books", [], [gstr2b])


def _ex03(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    perturbed = gstr2b.model_copy(
        update={"taxable_value": gstr2b.taxable_value + Decimal(rng.randint(100, 500))}
    )
    return SyntheticCase(case_id, ReasonCode.EX_03, "taxable value mismatch", [books], [perturbed])


def _ex04(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    bumped = gstr2b.tax.igst + Decimal(rng.randint(50, 200))
    perturbed = gstr2b.model_copy(update={"tax": TaxAmounts(igst=bumped)})
    return SyntheticCase(case_id, ReasonCode.EX_04, "tax amount mismatch", [books], [perturbed])


def _ex05(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins, split_heads=True)
    shift = Decimal(rng.randint(5, 20))
    shifted_tax = TaxAmounts(cgst=gstr2b.tax.cgst - shift, sgst=gstr2b.tax.sgst + shift)
    perturbed = gstr2b.model_copy(update={"tax": shifted_tax})
    return SyntheticCase(
        case_id, ReasonCode.EX_05, "tax head mismatch, total unchanged", [books], [perturbed]
    )


def _ex06(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    mutated_gstin = _typo_gstin(gstr2b.supplier_gstin, rng)
    perturbed = gstr2b.model_copy(update={"supplier_gstin": mutated_gstin})
    return SyntheticCase(
        case_id, ReasonCode.EX_06, "GSTIN typo (keying error)", [books], [perturbed]
    )


def _ex07(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    # Deliberately unrelated to the case marker -- this is the one mutation
    # that must NOT keep a recoverable case_id on the 2B side, so evaluate.py
    # must recover it from the (untouched) books side instead.
    unrelated_number = f"UNRELATED{rng.randint(10000, 99999)}"
    perturbed = gstr2b.model_copy(update={"invoice_number": unrelated_number})
    return SyntheticCase(
        case_id, ReasonCode.EX_07, "invoice number outright differs", [books], [perturbed]
    )


def _ex08(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins, month=EX08_MONTH)
    return SyntheticCase(
        case_id, ReasonCode.EX_08, "invoice month precedes its 2B return period", [books], [gstr2b]
    )


def _ex09(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    blocked = gstr2b.model_copy(update={"itc_availability": ItcAvailability.NOT_AVAILABLE})
    return SyntheticCase(
        case_id, ReasonCode.EX_09, "ITC unavailable per 2B but claimed in books", [books], [blocked]
    )


def _ex10(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, gstr2b = _clean_pair(case_id, rng, gstins)
    duplicate = books.model_copy(update={"row_ref": f"synthetic-books-{case_id}-dup"})
    return SyntheticCase(
        case_id,
        ReasonCode.EX_10,
        "duplicate booking on the books side",
        [books, duplicate],
        [gstr2b],
    )


def _ex11(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    _, gstr2b = _clean_pair(case_id, rng, gstins, doc_type=DocType.CREDIT_NOTE)
    return SyntheticCase(
        case_id, ReasonCode.EX_11, "2B credit note with no books reversal", [], [gstr2b]
    )


def _ex12(case_id: int, rng: random.Random, gstins: list[str]) -> SyntheticCase:
    books, _ = _clean_pair(case_id, rng, gstins, doc_type=DocType.CREDIT_NOTE)
    return SyntheticCase(
        case_id, ReasonCode.EX_12, "books credit note not yet in 2B", [books], []
    )


_BUILDERS = {
    ReasonCode.EX_01: _ex01,
    ReasonCode.EX_02: _ex02,
    ReasonCode.EX_03: _ex03,
    ReasonCode.EX_04: _ex04,
    ReasonCode.EX_05: _ex05,
    ReasonCode.EX_06: _ex06,
    ReasonCode.EX_07: _ex07,
    ReasonCode.EX_08: _ex08,
    ReasonCode.EX_09: _ex09,
    ReasonCode.EX_10: _ex10,
    ReasonCode.EX_11: _ex11,
    ReasonCode.EX_12: _ex12,
}


def generate_cases(total: int, clean: int, seed: int) -> list[SyntheticCase]:
    rng = random.Random(seed)
    gstins = _make_supplier_gstins(20)

    codes = list(_BUILDERS.keys())
    defect_total = total - clean
    base_count, remainder = divmod(defect_total, len(codes))
    plan: list[ReasonCode | None] = [None] * clean
    for idx, code in enumerate(codes):
        plan.extend([code] * (base_count + (1 if idx < remainder else 0)))
    rng.shuffle(plan)

    return [_case(case_id, code, rng, gstins) for case_id, code in enumerate(plan, start=1)]


def _voucher_type_label(doc_type: DocType) -> str:
    return {
        DocType.INVOICE: "Purchase",
        DocType.CREDIT_NOTE: "Credit Note",
        DocType.DEBIT_NOTE: "Debit Note",
    }[doc_type]


def _write_books_csv(path: Path, cases: list[SyntheticCase]) -> None:
    lines = ["Date,Party Name,GSTIN,Voucher Type,Invoice No,Taxable Value,IGST,CGST,SGST,CESS"]
    for case in cases:
        for doc in case.books_docs:
            lines.append(
                ",".join(
                    [
                        doc.invoice_date.strftime("%d-%m-%Y"),
                        "Synthetic Supplier",
                        doc.supplier_gstin,
                        _voucher_type_label(doc.doc_type),
                        doc.invoice_number,
                        str(doc.taxable_value),
                        str(doc.tax.igst),
                        str(doc.tax.cgst),
                        str(doc.tax.sgst),
                        str(doc.tax.cess),
                    ]
                )
            )
    path.write_text("\n".join(lines) + "\n")


def _write_gstr2b_json(path: Path, cases: list[SyntheticCase]) -> None:
    # A JSON-shaped dict of mixed value types (str fields alongside a list
    # field) -- not worth a TypedDict for a one-off synthetic-data shape.
    b2b: dict[str, dict[str, Any]] = {}
    cdnr: dict[str, dict[str, Any]] = {}

    for case in cases:
        for doc in case.gstr2b_docs:
            entry = {
                "inum" if doc.doc_type is DocType.INVOICE else "ntnum": doc.invoice_number,
                "dt" if doc.doc_type is DocType.INVOICE else "ntdt": doc.invoice_date.strftime(
                    "%d-%m-%Y"
                ),
                "val": str(doc.total_value),
                "txval": str(doc.taxable_value),
                "iamt": str(doc.tax.igst),
                "camt": str(doc.tax.cgst),
                "samt": str(doc.tax.sgst),
                "csamt": str(doc.tax.cess),
                "itcavl": doc.itc_availability.value if doc.itc_availability else "Y",
            }
            if doc.doc_type is DocType.INVOICE:
                supplier = b2b.setdefault(
                    doc.supplier_gstin,
                    {"ctin": doc.supplier_gstin, "trdnm": "Synthetic Supplier", "inv": []},
                )
                supplier["inv"].append(entry)
            else:
                entry["typ"] = "C" if doc.doc_type is DocType.CREDIT_NOTE else "D"
                supplier = cdnr.setdefault(
                    doc.supplier_gstin,
                    {"ctin": doc.supplier_gstin, "trdnm": "Synthetic Supplier", "nt": []},
                )
                supplier["nt"].append(entry)

    payload = {
        "data": {
            "rtnprd": RETURN_PERIOD,
            "docdata": {"b2b": list(b2b.values()), "cdnr": list(cdnr.values())},
        }
    }
    path.write_text(json.dumps(payload, indent=2))


def _write_ground_truth(path: Path, cases: list[SyntheticCase]) -> None:
    # Keyed by the zero-padded marker digits (e.g. "00034"), matching exactly
    # what CASE_ID_RE recovers from "SYN00034" in evaluate.py -- using the
    # bare int (str(34) == "34") here was an earlier bug: it silently never
    # matched anything the evaluator recovered, making every case look like
    # a missed detection regardless of what the engine actually found.
    payload = {
        f"{case.case_id:0{CASE_ID_WIDTH}d}": {
            "expected_codes": [case.reason_code.value] if case.reason_code else [],
            "description": case.description,
        }
        for case in cases
    }
    path.write_text(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total", type=int, default=250)
    parser.add_argument("--clean", type=int, default=91)
    parser.add_argument("--seed", type=int, default=20240401)
    parser.add_argument("--out-dir", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    cases = generate_cases(args.total, args.clean, args.seed)

    _write_books_csv(args.out_dir / "books.csv", cases)
    _write_gstr2b_json(args.out_dir / "gstr2b.json", cases)
    _write_ground_truth(args.out_dir / "ground_truth.json", cases)

    print(f"Generated {len(cases)} cases ({args.clean} clean) into {args.out_dir}/")


if __name__ == "__main__":
    main()

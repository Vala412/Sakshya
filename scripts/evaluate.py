#!/usr/bin/env python3
"""Eval harness: run the engine against the labelled synthetic dataset and
report per-reason-code precision/recall/F1, plus the false-positive rate on
clean cases.

Read this score honestly (see project docs): the generator and the
classifier share the same assumptions about what each reason code means, so
a perfect score here is a regression gate -- it proves the engine still
agrees with itself -- not evidence of real-world accuracy against an actual
GSTR-2B export, which this project has never had access to.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from gstrecon import ingest
from gstrecon.exceptions import ReasonCode, reconcile_full
from gstrecon.models import Document

CASE_ID_RE = re.compile(r"SYN(\d{5})")


def _recover_case_id(books_doc: Document | None, gstr2b_doc: Document | None) -> str | None:
    """Recover which synthetic case a finding belongs to.

    Books-side first: the one mutation that deliberately destroys the
    marker (EX-07) only ever touches the GSTR-2B side, leaving the books
    side's invoice number as the untouched "SYN00001" marker -- see
    generate_synthetic.py's `_ex07`.
    """
    for doc in (books_doc, gstr2b_doc):
        if doc is None:
            continue
        match = CASE_ID_RE.search(doc.invoice_number)
        if match:
            return match.group(1)
    return None


def evaluate(data_dir: Path) -> int:
    books_docs = ingest.parse_books_csv(data_dir / "books.csv")
    gstr2b_docs = ingest.parse_gstr2b_json(data_dir / "gstr2b.json")
    ground_truth = json.loads((data_dir / "ground_truth.json").read_text())

    reconciliation = reconcile_full(books_docs, gstr2b_docs)

    actual_codes: dict[str, set[str]] = defaultdict(set)
    unrecovered: list[str] = []
    for finding in reconciliation.findings:
        case_id = _recover_case_id(finding.books_doc, finding.gstr2b_doc)
        if case_id is None:
            unrecovered.append(finding.evidence)
            continue
        actual_codes[case_id].add(finding.reason_code.value)

    all_codes = [code.value for code in ReasonCode]
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    clean_false_positives = 0
    clean_total = 0

    for case_id, truth in ground_truth.items():
        expected = set(truth["expected_codes"])
        actual = actual_codes.get(case_id, set())

        if not expected:
            clean_total += 1
            if actual:
                clean_false_positives += 1

        for code in all_codes:
            if code in expected and code in actual:
                tp[code] += 1
            elif code in actual and code not in expected:
                fp[code] += 1
            elif code in expected and code not in actual:
                fn[code] += 1

    print(f"{'Code':<8}{'Precision':>10}{'Recall':>10}{'F1':>10}{'TP':>6}{'FP':>6}{'FN':>6}")
    all_perfect = True
    for code in all_codes:
        t, p_, n = tp[code], fp[code], fn[code]
        precision = t / (t + p_) if (t + p_) else float("nan")
        recall = t / (t + n) if (t + n) else float("nan")
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) and precision == precision and recall == recall
            else float("nan")
        )
        if t + p_ + n > 0 and (precision < 1.0 or recall < 1.0):
            all_perfect = False
        print(f"{code:<8}{precision:>10.2f}{recall:>10.2f}{f1:>10.2f}{t:>6}{p_:>6}{n:>6}")

    print()
    print(f"Clean cases: {clean_total}, false positives: {clean_false_positives}")
    if unrecovered:
        print(f"WARNING: {len(unrecovered)} findings could not be traced to a case_id:")
        for evidence in unrecovered[:10]:
            print(f"  - {evidence}")

    ok = all_perfect and clean_false_positives == 0 and not unrecovered
    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()
    sys.exit(evaluate(args.data_dir))


if __name__ == "__main__":
    main()

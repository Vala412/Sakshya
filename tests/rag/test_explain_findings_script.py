"""Tests for scripts/explain_findings.py's argument/input error handling --
regression coverage for the same "clean error, not a raw traceback" bug
class already found and fixed in cli.py (see fix/production-hardening-review).
Does not exercise the actual reconciliation/explanation pipeline (that
needs live services); this only checks the script fails cleanly on bad
input before ever reaching them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "explain_findings.py"
_spec = importlib.util.spec_from_file_location("explain_findings_script", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
explain_findings_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(explain_findings_script)


class TestArgumentValidation:
    def test_garbage_tax_tolerance_exits_cleanly(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        books = tmp_path / "books.csv"
        gstr2b = tmp_path / "gstr2b.json"
        books.write_text("x")
        gstr2b.write_text("x")
        monkeypatch.setattr(
            sys, "argv", ["explain_findings.py", str(books), str(gstr2b), "--tax-tolerance", "abc"]
        )

        with pytest.raises(SystemExit) as exc_info:
            explain_findings_script.main()
        assert exc_info.value.code == 2

    def test_malformed_gstr2b_json_exits_cleanly_not_a_traceback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        books = tmp_path / "books.csv"
        gstr2b = tmp_path / "gstr2b.json"
        books.write_text(
            "Date,Party Name,GSTIN,Voucher Type,Invoice No,Taxable Value,IGST,CGST,SGST,CESS\n"
        )
        gstr2b.write_text("not valid json")
        monkeypatch.setattr(sys, "argv", ["explain_findings.py", str(books), str(gstr2b)])

        with pytest.raises(SystemExit) as exc_info:
            explain_findings_script.main()
        assert "Input format error" in str(exc_info.value)

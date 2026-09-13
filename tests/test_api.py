"""API-layer tests.

These cover the HTTP contract the frontend is written against -- not the
matching engine, which `test_matching.py` / `test_exceptions.py` already
own. The distinction matters: a test here that asserted a *reason code* was
correct would be testing the engine through three extra layers of
indirection. What belongs here is the shape of the wire format, the error
envelope, and the guarantees the UI relies on (exact decimals, served
reason-code catalogue, downloadable working paper).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gstrecon.api.main import app, run_store

FIXTURES = Path(__file__).parent / "fixtures"
BOOKS = FIXTURES / "books_sample.csv"
GSTR2B = FIXTURES / "gstr2b_sample.json"


@pytest.fixture
def client() -> TestClient:
    # raise_server_exceptions=False so the registered 500 handler actually
    # runs, instead of TestClient re-raising the exception into the test.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_runs():
    yield
    run_store.clear()


def _upload(books_bytes: bytes | None = None, gstr2b_bytes: bytes | None = None, **form):
    # `is None`, not `or`: b"" is falsy, so `books_bytes or BOOKS.read_bytes()`
    # would silently substitute the real fixture and make the empty-upload
    # test assert against a perfectly valid request.
    books = BOOKS.read_bytes() if books_bytes is None else books_bytes
    gstr2b = GSTR2B.read_bytes() if gstr2b_bytes is None else gstr2b_bytes
    return {
        "files": {
            "books": ("books.csv", books, "text/csv"),
            "gstr2b": ("gstr2b.json", gstr2b, "application/json"),
        },
        "data": form,
    }


def _books_with_tax_variance() -> bytes:
    """The shared fixture pair reconciles perfectly -- every match is exact,
    so it yields no mismatched parameters and nothing tolerance-sensitive.
    Tests that need a *variance* build one here by understating INV/0001's
    IGST by Rs 5, which produces an EX-04 carrying the GSTN parameters
    `total_tax_amount` and `tax_amount_head_wise`.
    """
    return BOOKS.read_text().replace(
        "INV/0001,1000.00,180.00", "INV/0001,1000.00,175.00"
    ).encode()


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_reason_codes_cover_all_twelve(client: TestClient) -> None:
    response = client.get("/api/reason-codes")
    assert response.status_code == 200
    codes = response.json()
    assert [c["code"] for c in codes] == [f"EX-{i:02d}" for i in range(1, 13)]
    # Severity comes from the engine's own table, not a client-side copy.
    by_code = {c["code"]: c for c in codes}
    assert by_code["EX-01"]["severity"] == "high"
    assert by_code["EX-02"]["severity"] == "low"


def test_reconcile_returns_full_working_paper(client: TestClient) -> None:
    payload = _upload()
    response = client.post("/api/reconcile", files=payload["files"], data=payload["data"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {"run_id", "summary", "bridge", "findings", "metadata"}
    assert body["summary"]["books_document_count"] > 0
    assert body["summary"]["gstr2b_document_count"] > 0
    assert len(body["findings"]) == body["summary"]["finding_count"]


def test_money_fields_are_exact_strings_not_floats(client: TestClient) -> None:
    """Regression guard for the decision documented in schemas.py.

    If someone "simplifies" the serializers away, money crosses the wire as
    a JSON number and the browser silently rounds it. Asserting on the raw
    text rather than the parsed body is deliberate -- `json.loads` would
    turn a float back into something that compares equal to the string's
    value and hide the regression.
    """
    payload = _upload()
    response = client.post("/api/reconcile", files=payload["files"], data=payload["data"])
    raw = json.loads(response.text)

    assert isinstance(raw["bridge"]["closing_variance"], str)
    assert isinstance(raw["bridge"]["books_total"], str)
    for line in raw["bridge"]["lines"]:
        assert isinstance(line["amount"], str)
    for finding in raw["findings"]:
        assert isinstance(finding["itc_at_risk"], str)
        if finding["books_doc"]:
            assert isinstance(finding["books_doc"]["taxable_value"], str)
            assert isinstance(finding["books_doc"]["tax"]["igst"], str)


def test_bridge_ties_to_nil_over_the_wire(client: TestClient) -> None:
    """The engine guarantees this; the API must not break it in transport.

    Re-derived from the serialised strings rather than trusting the served
    `closing_variance`, so a mapper that dropped a bridge line would fail
    here instead of quietly reporting a nil variance it did not earn.
    """
    payload = _upload()
    body = client.post("/api/reconcile", files=payload["files"], data=payload["data"]).json()
    bridge = body["bridge"]

    running = Decimal(bridge["books_total"])
    for line in bridge["lines"]:
        running += Decimal(line["amount"])
    assert running - Decimal(bridge["gstr2b_total_available"]) == Decimal(
        bridge["closing_variance"]
    )
    assert Decimal(bridge["closing_variance"]) == Decimal("0")


def test_findings_expose_gstn_parameters(client: TestClient) -> None:
    """The evidence drawer's per-field diff depends on this list being
    populated for matched-pair findings; an always-empty list would make the
    drawer silently useless while every other test still passed."""
    payload = _upload(books_bytes=_books_with_tax_variance())
    body = client.post("/api/reconcile", files=payload["files"], data=payload["data"]).json()
    paired = [f for f in body["findings"] if f["books_doc"] and f["gstr2b_doc"]]
    assert paired, "variance fixture should produce a matched-pair finding"

    parameters = {p for f in paired for p in f["mismatched_parameters"]}
    # Named verbatim from the GSTN manual's own parameter list, which is what
    # lets the drawer cite the official parameter rather than a label we
    # invented -- see the PARAM_* constants in matching.py.
    assert "total_tax_amount" in parameters
    assert "tax_amount_head_wise" in parameters


def test_working_paper_download(client: TestClient) -> None:
    payload = _upload()
    run_id = client.post(
        "/api/reconcile", files=payload["files"], data=payload["data"]
    ).json()["run_id"]

    response = client.get(f"/api/runs/{run_id}/working-paper")
    assert response.status_code == 200
    # A real .xlsx is a zip container -- check the magic bytes rather than
    # just a non-empty body, which an error page would also satisfy.
    assert response.content[:2] == b"PK"


def test_unknown_run_returns_structured_404(client: TestClient) -> None:
    response = client.get("/api/runs/does-not-exist/working-paper")
    assert response.status_code == 404
    assert response.json()["error"] == "run_not_found"


@pytest.mark.parametrize(
    ("field", "bad_bytes", "expected_error"),
    [
        ("books", b"not,a,valid\nbooks,file,at-all\n", "invalid_books_file"),
        ("gstr2b", b"{ not json", "invalid_gstr2b_file"),
    ],
)
def test_malformed_uploads_return_422_with_field(
    client: TestClient, field: str, bad_bytes: bytes, expected_error: str
) -> None:
    kwargs = {f"{field}_bytes": bad_bytes}
    payload = _upload(**kwargs)
    response = client.post("/api/reconcile", files=payload["files"], data=payload["data"])

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == expected_error
    # The UI attaches the message to the right dropzone using this.
    assert body["field"] == field
    assert body["message"]


def test_empty_upload_is_rejected(client: TestClient) -> None:
    payload = _upload(books_bytes=b"")
    response = client.post("/api/reconcile", files=payload["files"], data=payload["data"])
    assert response.status_code == 400
    assert response.json()["error"] == "empty_file"


@pytest.mark.parametrize("tolerance", ["abc", "-1"])
def test_invalid_tolerance_is_rejected(client: TestClient, tolerance: str) -> None:
    payload = _upload(tax_tolerance=tolerance)
    response = client.post("/api/reconcile", files=payload["files"], data=payload["data"])
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_tolerance"
    assert body["field"] == "tax_tolerance"


def test_tolerance_is_actually_applied(client: TestClient) -> None:
    """A generous per-head tolerance must absorb small variances, so the
    finding count strictly drops. Without this, `tax_tolerance` could be
    parsed, validated, and then never passed to the engine."""
    variance = _books_with_tax_variance()
    strict = _upload(books_bytes=variance, tax_tolerance="0")
    loose = _upload(books_bytes=variance, tax_tolerance="1000000")

    strict_count = client.post(
        "/api/reconcile", files=strict["files"], data=strict["data"]
    ).json()["summary"]["finding_count"]
    loose_count = client.post(
        "/api/reconcile", files=loose["files"], data=loose["data"]
    ).json()["summary"]["finding_count"]

    assert loose_count < strict_count


def test_metadata_reports_uploaded_name_and_real_hash(client: TestClient) -> None:
    """The Reproducibility panel is the audit hook: it must show the name the
    analyst uploaded, and a hash of the bytes actually reconciled."""
    import hashlib

    payload = _upload()
    body = client.post("/api/reconcile", files=payload["files"], data=payload["data"]).json()
    metadata = body["metadata"]

    assert metadata["books_filename"] == "books.csv"
    assert metadata["books_sha256"] == hashlib.sha256(BOOKS.read_bytes()).hexdigest()
    assert metadata["gstr2b_sha256"] == hashlib.sha256(GSTR2B.read_bytes()).hexdigest()


def test_run_store_evicts_and_deletes_files(tmp_path: Path) -> None:
    """Eviction must unlink, not just forget -- otherwise a long-running
    server accumulates taxpayers' working papers in the temp directory."""
    from gstrecon.api.main import _RunStore

    store = _RunStore(capacity=2)
    paths = []
    for i in range(3):
        p = tmp_path / f"wp{i}.xlsx"
        p.write_bytes(b"PK\x03\x04")
        paths.append(p)
        store.put(f"run{i}", p)

    assert store.get("run0") is None
    assert not paths[0].exists()
    assert store.get("run2") is not None
    assert paths[2].exists()

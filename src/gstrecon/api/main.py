"""FastAPI app serving the deterministic reconciliation engine.

Scope note: this layer has **no** LLM or vector-store dependency. It runs
with no OPENAI_API_KEY and no Qdrant. The Phase 3 explanation layer, when it
is promoted to main, should attach as an additional endpoint that decorates
findings -- not by threading an LLM call into `POST /api/reconcile`, which
must stay deterministic, offline, and free.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from gstrecon import __version__, ingest, report
from gstrecon.api import mappers, schemas
from gstrecon.exceptions import _DESCRIPTIONS, _SEVERITY, DEFAULT_TAX_TOLERANCE, reconcile_full
from gstrecon.matching import DEFAULT_GSTIN_FUZZY_THRESHOLD, DEFAULT_INVOICE_FUZZY_THRESHOLD

logger = logging.getLogger(__name__)

# Uploads are streamed to disk with this cap enforced mid-stream, so a
# hostile upload can't exhaust the box. A realistic single-filer purchase
# register for one month is well under a megabyte -- 25 MB is generous.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Completed runs are kept only so the browser can fetch the .xlsx it was
# just offered. Bounded and in-process on purpose: this is a local analyst
# tool, not a multi-tenant service, and persisting other people's tax data
# to disk indefinitely is a liability, not a feature.
MAX_RETAINED_RUNS = 12


class _RunStore:
    """Bounded LRU of finished runs -> working-paper file on disk.

    Evicting deletes the file. Without that, a long-lived server would leave
    every uploaded taxpayer's working paper in the system temp directory.
    """

    def __init__(self, capacity: int = MAX_RETAINED_RUNS) -> None:
        self._items: OrderedDict[str, Path] = OrderedDict()
        self._capacity = capacity
        self._lock = Lock()

    def put(self, run_id: str, path: Path) -> None:
        with self._lock:
            self._items[run_id] = path
            self._items.move_to_end(run_id)
            while len(self._items) > self._capacity:
                _, evicted = self._items.popitem(last=False)
                evicted.unlink(missing_ok=True)

    def get(self, run_id: str) -> Path | None:
        with self._lock:
            path = self._items.get(run_id)
            if path is None:
                return None
            self._items.move_to_end(run_id)
            return path

    def clear(self) -> None:
        with self._lock:
            for path in self._items.values():
                path.unlink(missing_ok=True)
            self._items.clear()


run_store = _RunStore()

app = FastAPI(
    title="gstrecon API",
    version=__version__,
    description="Deterministic books-vs-GSTR-2B reconciliation. No LLM, no vector store.",
)

# The Vite dev server runs on a different origin than uvicorn, so the browser
# needs these during development. Restricted to localhost rather than "*":
# this API receives tax data, and a wildcard would let any page the analyst
# happens to have open POST to their local server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _error(status: int, error: str, message: str, field: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=schemas.ErrorOut(error=error, message=message, field=field).model_dump(),
    )


def _detail(error: str, message: str, field: str | None = None) -> dict[str, str | None]:
    """Build an HTTPException detail that is already in ErrorOut shape, so
    the handler below can pass it straight through."""
    return schemas.ErrorOut(error=error, message=message, field=field).model_dump()


@app.exception_handler(HTTPException)
async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Re-shape FastAPI's default {"detail": ...} into the ErrorOut envelope
    so the client has exactly one error contract to parse."""
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return _error(exc.status_code, "request_failed", str(exc.detail))


@app.exception_handler(Exception)
async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """A genuine engine bug must not leak a traceback to the browser, but it
    must not be swallowed silently either -- it is logged server-side with
    the stack intact, and the client gets a stable, non-revealing envelope.
    """
    logger.exception("Unhandled error while serving request", exc_info=exc)
    return _error(500, "internal_error", "The reconciliation engine failed unexpectedly.")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/reason-codes", response_model=list[schemas.ReasonCodeOut])
def reason_codes() -> list[schemas.ReasonCodeOut]:
    """The EX-01..EX-12 catalogue, read from the engine's own tables.

    Served rather than hardcoded client-side so severity/description can
    never drift between the UI and the classifier.
    """
    return [
        schemas.ReasonCodeOut(
            code=code.value,
            description=_DESCRIPTIONS[code],
            severity=_SEVERITY[code].value,
        )
        for code in _DESCRIPTIONS
    ]


@app.get("/api/defaults")
def defaults() -> dict[str, str | float]:
    """The engine's default thresholds, so the upload form can show real
    values instead of duplicating the constants."""
    return {
        "tax_tolerance": str(DEFAULT_TAX_TOLERANCE),
        "invoice_fuzzy_threshold": DEFAULT_INVOICE_FUZZY_THRESHOLD,
        "gstin_fuzzy_threshold": DEFAULT_GSTIN_FUZZY_THRESHOLD,
    }


def _persist_upload(upload: UploadFile, target_dir: Path, field: str) -> Path:
    """Stream an upload to disk, enforcing the size cap as we go.

    Read in chunks rather than `upload.read()` so an oversized file is
    rejected mid-stream instead of after it has already been buffered whole.
    """
    name = Path(upload.filename or field).name
    destination = target_dir / name
    limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    total = 0
    with destination.open("wb") as fh:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=_detail(
                        "file_too_large", f"{name} exceeds the {limit_mb} MB limit.", field
                    ),
                )
            fh.write(chunk)
    if total == 0:
        raise HTTPException(
            status_code=400, detail=_detail("empty_file", f"{name} is empty.", field)
        )
    return destination


@app.post("/api/reconcile", response_model=schemas.ReconciliationOut)
def reconcile(
    books: UploadFile = File(..., description="Tally purchase-register CSV export"),
    gstr2b: UploadFile = File(..., description="GSTR-2B JSON export"),
    tax_tolerance: str = Form(str(DEFAULT_TAX_TOLERANCE)),
) -> schemas.ReconciliationOut:
    """Run the full reconciliation and return the working paper as JSON.

    The generated .xlsx is retained under the returned `run_id` so the client
    can download the identical artefact it is looking at, rather than
    triggering a second reconciliation that could in principle differ.
    """
    # Not a TemporaryDirectory context manager: the .xlsx has to outlive this
    # request so /api/runs/{id}/working-paper can serve it. Lifetime is
    # managed by _RunStore's LRU eviction instead.
    workdir = Path(tempfile.mkdtemp(prefix="gstrecon-run-"))

    try:
        books_path = _persist_upload(books, workdir, "books")
        gstr2b_path = _persist_upload(gstr2b, workdir, "gstr2b")

        try:
            parsed_tolerance = Decimal(tax_tolerance)
        except InvalidOperation:
            raise HTTPException(
                status_code=422,
                detail=_detail(
                    "invalid_tolerance",
                    f"'{tax_tolerance}' is not a valid decimal amount.",
                    "tax_tolerance",
                ),
            ) from None
        if parsed_tolerance < 0:
            raise HTTPException(
                status_code=422,
                detail=_detail(
                    "invalid_tolerance", "Tax tolerance cannot be negative.", "tax_tolerance"
                ),
            )

        # Same two-arm catch as cli.py, and for the same reason: a malformed
        # date deep in the CSV is as much a bad-input case as a missing
        # column, and both deserve a clean 422 rather than a 500. A genuine
        # engine bug is not caught here and reaches the 500 handler intact.
        try:
            books_docs = ingest.parse_books_csv(books_path)
        except (ValueError, InvalidOperation) as exc:
            raise HTTPException(
                status_code=422, detail=_detail("invalid_books_file", str(exc), "books")
            ) from exc
        try:
            gstr2b_docs = ingest.parse_gstr2b_json(gstr2b_path)
        except (ValueError, InvalidOperation) as exc:
            raise HTTPException(
                status_code=422, detail=_detail("invalid_gstr2b_file", str(exc), "gstr2b")
            ) from exc

        reconciliation = reconcile_full(books_docs, gstr2b_docs, tax_tolerance=parsed_tolerance)
        metadata = report.RunMetadata(
            books_path=books_path,
            gstr2b_path=gstr2b_path,
            tax_tolerance=parsed_tolerance,
            invoice_fuzzy_threshold=DEFAULT_INVOICE_FUZZY_THRESHOLD,
            gstin_fuzzy_threshold=DEFAULT_GSTIN_FUZZY_THRESHOLD,
            books_document_count=len(books_docs),
            gstr2b_document_count=len(gstr2b_docs),
            generated_at=datetime.now(UTC),
        )

        run_id = uuid.uuid4().hex
        workpaper = workdir / "working_paper.xlsx"
        bridge = report.write_working_paper(
            workpaper,
            books_docs=books_docs,
            gstr2b_docs=gstr2b_docs,
            reconciliation=reconciliation,
            metadata=metadata,
        )
        run_store.put(run_id, workpaper)

        return mappers.reconciliation_out(
            run_id=run_id,
            books_docs=books_docs,
            gstr2b_docs=gstr2b_docs,
            reconciliation=reconciliation,
            bridge=bridge,
            metadata=metadata,
            books_filename=books_path.name,
            gstr2b_filename=gstr2b_path.name,
        )
    finally:
        books.file.close()
        gstr2b.file.close()


@app.get("/api/runs/{run_id}/working-paper")
def working_paper(run_id: str) -> FileResponse:
    path = run_store.get(run_id)
    if path is None or not path.exists():
        raise HTTPException(
            status_code=404,
            detail=_detail(
                "run_not_found",
                "That reconciliation is no longer available. Run it again to "
                "regenerate the working paper.",
            ),
        )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="working_paper.xlsx",
    )

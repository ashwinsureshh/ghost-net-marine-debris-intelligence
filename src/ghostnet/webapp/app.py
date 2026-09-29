"""FastAPI backend for the operator web application (PRD §9.1).

Responsibilities, per the split in §9.1:

* serve precomputed run artefacts exported from the workstation;
* recompute prioritisation (FR-6.1/6.2) live when the operator changes vessel
  capacity or switches agents off;
* generate FR-6.3 rationales via the Claude API — the reason a backend is
  genuinely required rather than decorative, since that key cannot live in a
  browser;
* record the FR-6.4 approval.

Run it:

    uvicorn ghostnet.webapp.app:app --reload

The built frontend is served from ``frontend/dist`` when present, so one
process serves both in deployment. When it is absent the API still works and
``/`` explains how to build it, rather than 404-ing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from ghostnet import __version__
from ghostnet.benchmark import cached_benchmark
from ghostnet.config import REPO_ROOT
from ghostnet.export import SCHEMA_VERSION, RunArtefact
from ghostnet.llm import RationaleWriter
from ghostnet.webapp.approvals import ApprovalStoreError
from ghostnet.webapp.planning import ABLATABLE, PlanningRequest, plan_from_artefact
from ghostnet.webapp.store import ArtefactStore

logger = logging.getLogger(__name__)

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

PROTOTYPE_NOTICE = (
    "Decision-support research prototype. Validated on historical and published "
    "data; every output stops at a recommendation for human review. Not "
    "operational-grade and not a monitoring service (PRD §5.2, §8)."
)

app = FastAPI(
    title="Ghost Net & Marine Debris Intelligence — Operator Console",
    description=PROTOTYPE_NOTICE,
    version=__version__,
)

# The frontend dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ArtefactStore()

# --------------------------------------------------------------------------
# Reliability middleware: request IDs, structured access logs, security
# headers, bounded request bodies, and one error shape that keeps ``detail``
# (the frontend and tests read it) and adds the request id for support.
# --------------------------------------------------------------------------

MAX_BODY_BYTES = int(os.environ.get("GHOSTNET_MAX_BODY_BYTES", "65536"))
access_log = logging.getLogger("ghostnet.access")
_REQUEST_ID_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


@app.middleware("http")
async def reliability_middleware(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "")
    request.state.request_id = supplied if _REQUEST_ID_OK.match(supplied) else uuid.uuid4().hex
    started = time.perf_counter()

    length = request.headers.get("content-length")
    if request.method in {"POST", "PUT", "PATCH"} and length and length.isdigit() \
            and int(length) > MAX_BODY_BYTES:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds {MAX_BODY_BYTES} bytes.",
                     "request_id": request.state.request_id},
        )
    else:
        try:
            response = await call_next(request)
        except Exception:  # last resort: never leak a traceback to the client
            logger.exception("Unhandled error [%s]", request.state.request_id)
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error.",
                         "request_id": request.state.request_id},
            )

    response.headers["X-Request-ID"] = request.state.request_id
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    access_log.info(json.dumps({
        "request_id": request.state.request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": round((time.perf_counter() - started) * 1000, 1),
    }))
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": _request_id(request)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "request_id": _request_id(request)},
    )


@app.exception_handler(ApprovalStoreError)
async def approval_store_error(request: Request, exc: ApprovalStoreError) -> JSONResponse:
    # 503, not 500: the server works, the audit log needs a person to look.
    logger.error("Approval store refused [%s]: %s", _request_id(request), exc)
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "request_id": _request_id(request)},
    )


# --------------------------------------------------------------------------
# Request/response models
# --------------------------------------------------------------------------


class PlanRequestBody(BaseModel):
    vessel_capacity: int = Field(default=3, ge=0, le=50)
    planning_horizon_days: int = Field(default=7, ge=1, le=90)
    ablate: list[str] = Field(default_factory=list)
    include_rationales: bool = True


# Module-level singleton so the default is not rebuilt per request (and so
# ruff's B008 stays satisfied). PlanRequestBody is immutable in practice —
# FastAPI validates and replaces it whenever a body is supplied.
DEFAULT_PLAN_REQUEST = PlanRequestBody()


class ApproveRequestBody(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    vessel_capacity: int = Field(default=3, ge=0, le=50)
    ablate: list[str] = Field(default_factory=list)
    detection_ids: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=2000)


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "artefact_schema": SCHEMA_VERSION,
        "runs": len(store.run_ids()),
    }


@app.get("/api/ready")
def ready() -> JSONResponse:
    """Readiness, distinct from liveness: can this instance serve real work?

    Checks that artefacts are present and parse, and that the approval log is
    readable and writable. Returns 503 with the failing checks otherwise, so a
    platform health probe does not route traffic to a hollow instance.
    """
    checks: dict[str, dict[str, Any]] = {}
    summaries = store.summaries()
    unreadable = [s["run_id"] for s in summaries if s.get("unreadable")]
    readable = len(summaries) - len(unreadable)
    checks["artefacts"] = {
        "ok": readable > 0,
        "readable": readable,
        "unreadable": unreadable,
    }
    ok, message = store.approval_backend.check()
    checks["approvals"] = {"ok": ok, "backend": store.approval_backend.name,
                           "durable": store.storage_is_durable, "message": message}
    status = all(c["ok"] for c in checks.values())
    return JSONResponse(status_code=200 if status else 503,
                        content={"ready": status, "checks": checks})


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Everything the UI needs to frame itself honestly."""
    writer = RationaleWriter()
    return {
        "version": __version__,
        "artefact_schema": SCHEMA_VERSION,
        "prototype_notice": PROTOTYPE_NOTICE,
        "ablatable_agents": list(ABLATABLE),
        "rationale_source": "llm" if writer.available else "template",
        "rationale_note": (
            "Dispatch rationales are written by Claude server-side."
            if writer.available
            else "No ANTHROPIC_API_KEY on this server, so rationales come from the "
            "deterministic offline template. The plan itself is unaffected — the "
            "model only explains it."
        ),
        "approvals_durable": store.storage_is_durable,
        "agents": [
            {"id": "detection", "name": "Satellite Detection", "fr": "FR-1"},
            {"id": "verification", "name": "False-Positive Verification", "fr": "FR-2"},
            {"id": "drift", "name": "Drift", "fr": "FR-3"},
            {"id": "attribution", "name": "Source Attribution", "fr": "FR-4"},
            {"id": "vessels", "name": "Dark Vessel Correlation", "fr": "FR-5"},
            {"id": "prioritisation", "name": "Response Prioritisation", "fr": "FR-6"},
        ],
    }


@app.get("/api/benchmark")
def benchmark() -> dict[str, Any]:
    """The measured quality numbers behind the console's metrics strip.

    A first-class endpoint rather than a field on ``/api/meta``, for the same
    reason ``/rejected`` is one: the detector's 0.407 region recall is the
    project's weakest published number, and burying it inside a grab-bag of UI
    configuration is how a number quietly stops being shown. `eval/results.md`
    remains the authority — this only reshapes it (see :mod:`ghostnet.benchmark`).
    """
    return cached_benchmark().model_dump()


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": store.summaries()}


def _require_run(run_id: str) -> RunArtefact:
    try:
        artefact = store.get(run_id)
    except ValueError as exc:  # schema mismatch
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read run {run_id!r}: {exc}") from exc
    if artefact is None:
        known = store.run_ids()
        available = (
            ", ".join(known)
            if known
            else "none — export one with `python scripts/export_run.py --synthetic`"
        )
        raise HTTPException(status_code=404, detail=f"No run {run_id!r}. Available: {available}")
    return artefact


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> RunArtefact:
    """The whole artefact: detections, every verification check, trajectories,
    attributions, correlations and their evidence — including the rejections."""
    return _require_run(run_id)


@app.get("/api/runs/{run_id}/rejected")
def get_rejected(run_id: str) -> dict[str, Any]:
    """Rejected detections with their reasons — PRD §8 auditability.

    A first-class endpoint, not a filter on the run, because the Verification
    Agent's entire measured contribution is what it throws away.
    """
    artefact = _require_run(run_id)
    detections = artefact.detections_by_id()
    rejected = []
    for verification in artefact.rejected:
        detection = detections.get(verification.detection_id)
        rejected.append(
            {
                "detection": detection.model_dump() if detection else None,
                "verification": verification.model_dump(),
                "reasons": verification.rejection_reasons,
                "failed_checks": [c.name for c in verification.checks if c.disqualified],
            }
        )
    return {
        "run_id": run_id,
        "rejected": rejected,
        "count": len(rejected),
        "detections_total": len(artefact.detections),
    }


@app.post("/api/runs/{run_id}/plan")
def compute_plan(
    run_id: str,
    body: Annotated[PlanRequestBody, Body()] = DEFAULT_PLAN_REQUEST,
) -> dict[str, Any]:
    """Recompute the ranked, capacity-bounded plan live (FR-6.1/6.2/6.3).

    This is the real server-side work: the operator's capacity and ablation
    choices change the answer, and the rationales are generated here because the
    Claude key cannot live in the browser.
    """
    artefact = _require_run(run_id)
    try:
        request = PlanningRequest(
            vessel_capacity=body.vessel_capacity,
            planning_horizon_days=body.planning_horizon_days,
            ablate=frozenset(body.ablate),
            include_rationales=body.include_rationales,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = plan_from_artefact(artefact, request)
    return {
        "run_id": run_id,
        "plan": result.plan.model_dump() if result.plan else None,
        "scores": [s.model_dump() for s in result.scores],
        "degradations": result.degradations,
        "considered": result.considered,
        "ablated": result.ablated,
    }


@app.post("/api/runs/{run_id}/approve", status_code=201)
def approve_plan(run_id: str, body: ApproveRequestBody) -> dict[str, Any]:
    """Record the explicit human checkpoint (FR-6.4)."""
    _require_run(run_id)
    try:
        record = store.record_approval(
            run_id=run_id,
            reviewer=body.reviewer,
            vessel_capacity=body.vessel_capacity,
            ablated=body.ablate,
            detection_ids=body.detection_ids,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "approval": record.model_dump(),
        "warning": (
            None
            if record.durable
            else "Recorded, but this server's disk is ephemeral — the approval "
            "log may not survive a restart. Set GHOSTNET_DURABLE_STORAGE=1 "
            "where the disk persists."
        ),
    }


@app.get("/api/runs/{run_id}/approvals")
def list_approvals(run_id: str, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, Any]:
    _require_run(run_id)
    records = store.approvals(run_id)[:limit]
    return {"run_id": run_id, "approvals": [r.model_dump() for r in records]}


# --------------------------------------------------------------------------
# Frontend
# --------------------------------------------------------------------------

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/", response_class=HTMLResponse)
    def frontend_missing() -> str:
        return (
            "<!doctype html><meta charset=utf-8>"
            "<title>Ghost Net Operator Console — API only</title>"
            "<style>body{font:16px/1.6 ui-sans-serif,system-ui;max-width:44rem;"
            "margin:4rem auto;padding:0 1.5rem;color:#0f172a}code{background:"
            "#f1f5f9;padding:.15rem .4rem;border-radius:.25rem}</style>"
            "<h1>API is running; the frontend is not built.</h1>"
            "<p>Build it once and this route serves the app instead:</p>"
            "<pre><code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></pre>"
            "<p>The API is live meanwhile — try "
            '<a href="/api/runs">/api/runs</a> or '
            '<a href="/docs">/docs</a>.</p>'
        )

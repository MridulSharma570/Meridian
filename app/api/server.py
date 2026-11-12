"""Meridian FastAPI application.

Serves the premium single-page frontend and the complete JSON API. Designed to
run behind any reverse proxy: binds 0.0.0.0, allows all origins, and the browser
only ever calls relative /api URLs (never localhost).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import keepalive, services
from app.agents.chat_agent import ChatAgent
from app.api.answer_policy import AnswerUnavailable, readiness, sample_mode
from app.agents.orchestrator import AGENT_META, PIPELINE
from app.api.providers import list_providers
from app.config import SUPPORTED_LANGUAGES, WEB_DIR, settings
from app.database import queries

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("meridian.api")


def _warmup() -> None:
    """Schema creation + demo seeding, deliberately OFF the startup path.

    PaaS hosts (Render, Railway, Fly) require the HTTP port to be listening
    within seconds. Any slow work here would cause a port-scan timeout and a
    deploy that appears to "keep shutting down".
    """
    try:
        services.bootstrap()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Background warm-up failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fast startup: bind immediately, warm up in the background."""
    logger.info("Meridian %s starting — platform=%s db=%s port=%s",
                settings.version, settings.platform,
                settings.database_url.split(":")[0], settings.port)
    warm: Optional[threading.Thread] = None
    if settings.warmup_in_background:
        warm = threading.Thread(target=_warmup, daemon=True, name="meridian-warmup")
        warm.start()
    else:
        _warmup()
    try:
        keepalive.start_keepalive()
    except Exception as exc:
        logger.warning("Keep-alive skipped: %s", exc)
    yield
    keepalive.stop_keepalive()
    logger.info("Meridian shutting down")


app = FastAPI(
    title="Meridian — Market Intelligence API",
    version=settings.version,
    description="Six autonomous AI agents plus a translator generate board-ready "
                "market intelligence reports from a single query.",
    lifespan=lifespan,
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"], expose_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.exception_handler(AnswerUnavailable)
async def answer_unavailable(request: Request, exc: AnswerUnavailable):
    """Never fabricate: return an actionable, structured 409 to the client."""
    return JSONResponse(status_code=exc.status_code, content=exc.as_dict())


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Never leak HTML tracebacks to the SPA; always return structured JSON."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={
        "detail": f"{type(exc).__name__}: {exc}",
        "hint": "Check /docs or the Agent Logs tab for details.",
    })


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ReportRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=600)
    region: str = "Global"
    period: str = "3Y"
    language: str = "en"


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class TranslateRequest(BaseModel):
    language: str = "hi"


class KeyRequest(BaseModel):
    slot: str
    provider: str
    api_key: str
    model: str = ""


class KeySlotRequest(BaseModel):
    slot: str


class ApplyAllRequest(BaseModel):
    provider: str
    api_key: str
    model: str = ""


class CompareRequest(BaseModel):
    company_a: str
    company_b: str
    region: str = "Global"


class CompareReportsRequest(BaseModel):
    report_a: str
    report_b: str


# --------------------------------------------------------------------------- #
# Frontend + system
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(WEB_DIR / "index.html"), media_type="text/html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(str(WEB_DIR / "favicon.svg"), media_type="image/svg+xml")


@app.api_route("/api/ping", methods=["GET", "HEAD"], tags=["System"])
def ping(response: Response):
    """Ultra-light liveness probe for Render health checks and uptime pings.

    Touches no database, no filesystem and no network, and is never cached —
    so a monitor always generates a genuine inbound request (which is what
    keeps a free Render instance from spinning down). HEAD is registered
    explicitly because free UptimeRobot/cron-job.org monitors probe with HEAD
    and FastAPI's `@app.get` would otherwise answer 405 Method Not Allowed.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return {"ok": True, "ts": int(time.time()), "service": "meridian"}


@app.api_route("/api/health", methods=["GET", "HEAD"], tags=["System"])
def health(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    state = services.startup_state()
    return {"status": "healthy", "app": settings.app_name,
            "version": settings.version, "tagline": settings.tagline,
            "developer": settings.developer,
            "database": "postgresql" if settings.using_postgres else "sqlite",
            "platform": settings.platform, "port": settings.port,
            "warming_up": not state["ready"],
            "keepalive": keepalive.keepalive_status(),
            "demo_mode": sample_mode(),
            "readiness": readiness()}


@app.get("/api/bootstrap", tags=["System"])
def bootstrap():
    """First-load payload. Only page loads wait (briefly) for warm-up."""
    services.wait_for_bootstrap(3.0)
    return {
        "warming_up": not services.startup_state()["ready"],
        "app": settings.app_name, "tagline": settings.tagline,
        "version": settings.version, "developer": settings.developer,
        "demo_mode": sample_mode(),
        "readiness": readiness(),
        "signature_trio": list(settings.signature_trio),
        "stats": services.overview_stats(),
        "settings": services.settings_payload(),
        "agents": [{"slot": k, **v} for k, v in AGENT_META.items()],
        "pipeline": PIPELINE,
    }


@app.get("/api/readiness", tags=["System"])
def api_readiness():
    """Is an answer allowed right now? Consumed by both frontends on load."""
    return readiness()


@app.get("/api/stats", tags=["System"])
def stats():
    return services.overview_stats()


@app.get("/api/agents", tags=["System"])
def agents():
    return {"agents": [{"slot": k, **v} for k, v in AGENT_META.items()],
            "pipeline": PIPELINE,
            "chat_suggestions": ChatAgent.SUGGESTIONS}


@app.get("/api/providers", tags=["Settings"])
def providers():
    return {"providers": list_providers()}


@app.get("/api/languages", tags=["System"])
def languages():
    return {"languages": [{"code": c, "name": n, "native": nat}
                          for c, n, nat in SUPPORTED_LANGUAGES]}


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@app.post("/api/reports", status_code=201, tags=["Reports"])
def create_report(body: ReportRequest):
    try:
        rid = services.start_report(body.query, region=body.region,
                                    period=body.period, language=body.language)
        return {"report_id": rid, "status": "processing",
                "events_url": f"/api/reports/{rid}/events"}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/reports", tags=["Reports"])
def list_reports(search: str = "", status: str = "", region: str = "",
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    # The SPA consumes a plain array; filtering metadata is available via /api/stats.
    return queries.list_reports(search=search, status=status, region=region,
                                limit=limit, offset=offset)


@app.get("/api/reports/{report_id}", tags=["Reports"])
def get_report(report_id: str):
    row = queries.get_report(report_id)
    if not row:
        raise HTTPException(404, "Report not found")
    return row


@app.get("/api/reports/{report_id}/dashboard", tags=["Reports"])
def report_dashboard(report_id: str, region: str = "", period: str = "",
                     competitor: str = ""):
    try:
        return services.dashboard_payload(report_id, region, period, competitor)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/reports/{report_id}/status", tags=["Reports"])
def report_status(report_id: str):
    st = services.job_status(report_id)
    if st["status"] == "unknown":
        raise HTTPException(404, "Report not found")
    return st


@app.get("/api/reports/{report_id}/events", tags=["Reports"])
def report_events(report_id: str, from_index: int = 0):
    """Server-Sent Events stream of live agent activity."""
    def gen():
        for event in services.event_stream(report_id, from_index):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "Connection": "keep-alive",
        "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*",
    })


@app.delete("/api/reports/{report_id}", tags=["Reports"])
def delete_report(report_id: str):
    if not queries.delete_report(report_id):
        raise HTTPException(404, "Report not found")
    return {"ok": True, "report_id": report_id}


@app.post("/api/reports/compare", tags=["Reports"])
def compare_reports(body: CompareReportsRequest):
    try:
        return services.compare_reports(body.report_a, body.report_b)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/reports/{report_id}/chat", tags=["Chat"])
def chat_history(report_id: str):
    if not queries.get_report(report_id):
        raise HTTPException(404, "Report not found")
    return queries.get_chat_history(report_id)


@app.post("/api/reports/{report_id}/chat", tags=["Chat"])
def chat(report_id: str, body: ChatRequest):
    try:
        return services.answer_chat(report_id, body.question)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/reports/{report_id}/translate", tags=["Reports"])
def translate(report_id: str, body: TranslateRequest):
    try:
        return services.translate_report(report_id, body.language)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/reports/{report_id}/export/{fmt}", tags=["Exports"])
def export(report_id: str, fmt: str):
    if fmt not in {"pdf", "pptx", "excel"}:
        raise HTTPException(400, "Format must be pdf, pptx or excel")
    try:
        path = Path(services.export_path(report_id, fmt))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    media = {"pdf": "application/pdf",
             "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[
                 "xlsx" if fmt == "excel" else fmt]
    return FileResponse(str(path), media_type=media,
                        filename=f"Meridian-{path.stem}.{path.suffix.lstrip('.')}",
                        headers={"Content-Disposition":
                                 f'inline; filename="Meridian-{path.stem}{path.suffix}"'})


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
@app.post("/api/compare", tags=["Compare"])
def compare(body: CompareRequest):
    try:
        return services.compare_companies(body.company_a, body.company_b, body.region)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/comparisons", tags=["Compare"])
def comparisons(limit: int = Query(30, ge=1, le=200)):
    return {"comparisons": queries.list_comparisons(limit)}


# --------------------------------------------------------------------------- #
# Settings / API keys
# --------------------------------------------------------------------------- #
@app.get("/api/settings", tags=["Settings"])
def get_settings():
    return services.settings_payload()


@app.post("/api/settings/keys", tags=["Settings"])
def save_key(body: KeyRequest):
    try:
        return {"ok": True, **services.save_key(body.slot, body.provider,
                                                body.api_key, body.model)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/settings/keys/test", tags=["Settings"])
def test_key(body: KeySlotRequest):
    return services.test_key(body.slot)


@app.get("/api/settings/openrouter/models", tags=["Settings"])
def openrouter_models(refresh: bool = Query(False)):
    """Live free OpenRouter models ranked for auto-selection (no key needed)."""
    return services.openrouter_free_models(refresh=refresh)


@app.delete("/api/settings/keys/{slot}", tags=["Settings"])
def delete_key(slot: str):
    return services.delete_key(slot)


@app.post("/api/settings/keys/apply-all", tags=["Settings"])
def apply_all(body: ApplyAllRequest):
    try:
        return services.apply_key_to_all(body.provider, body.api_key, body.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/agent-logs/{report_id}", tags=["System"])
def agent_logs(report_id: str):
    return {"logs": queries.get_agent_logs(report_id)}


# Exported ASGI app for uvicorn / gunicorn / Docker.
__all__ = ["app"]

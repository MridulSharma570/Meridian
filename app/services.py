"""High-level application services shared by the FastAPI app and Streamlit UI.

Everything the product *does* lives here: report jobs with live agent events,
chat, translation, comparison, filters, exports, settings and bootstrapping.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from app.agents.chat_agent import ChatAgent
from app.agents.orchestrator import Orchestrator
from app.agents.translator import SUPPORTED_LANGUAGES, TranslatorAgent
from app.api import answer_policy, key_manager
from app.api.llm_router import call_llm, effective_slot, test_connection
from app.agents.base import extract_json
from app.api.providers import list_providers
from app.config import AGENT_SLOTS, EXPORT_DIR, REGIONS, PERIODS, settings
from app.database import queries
from app.database.connection import ensure_schema
from app.data_sources.collector import collect_market_data
from app.data_sources.demo_data import build_comparison, clean_company, split_comparison
from app.export.excel_generator import generate_excel
from app.export.pdf_generator import generate_pdf
from app.export.pptx_generator import generate_pptx

logger = logging.getLogger("meridian.services")


@dataclass
class ReportJob:
    report_id: str
    status: str = "processing"
    events: List[dict] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    cond: threading.Condition = field(default_factory=threading.Condition)


_JOBS: Dict[str, ReportJob] = {}
_LOCK = threading.Lock()
_BOOTSTRAPPED = False
_BOOTSTRAP_DONE = False
_BOOTSTRAP_ERROR = ""


def _report_to_export_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "researcher_output": row.get("researcher_output"),
        "analyst_output": row.get("analyst_output"),
        "writer_output": row.get("writer_output"),
        "forecast_output": row.get("forecast_output"),
        "factcheck_output": row.get("factcheck_output"),
        "company": row.get("company"), "region": row.get("region"),
        "period": row.get("period"), "query": row.get("query"),
    }


def generate_exports(report_id: str) -> Dict[str, str]:
    """Create PDF / PPTX / XLSX for a report; each export is isolated."""
    row = queries.get_report(report_id)
    if not row:
        return {}
    payload = _report_to_export_dict(row)
    stem = f"meridian-{report_id[:8]}"
    paths: Dict[str, str] = {}
    for fmt, fn, ext in (("pdf", generate_pdf, "pdf"),
                         ("pptx", generate_pptx, "pptx"),
                         ("excel", generate_excel, "xlsx")):
        existing = row.get(f"{fmt}_path") if fmt != "excel" else row.get("excel_path")
        if existing and Path(existing).exists():
            paths[fmt] = existing
            continue
        try:
            paths[fmt] = fn(payload, EXPORT_DIR / f"{stem}.{ext}")
        except Exception as exc:
            logger.exception("%s export failed for %s", fmt, report_id)
            paths[fmt] = ""
    try:
        queries.update_report(report_id,
                              pdf_path=paths.get("pdf", ""),
                              pptx_path=paths.get("pptx", ""),
                              excel_path=paths.get("excel", ""))
    except Exception as exc:
        logger.warning("Could not persist export paths: %s", exc)
    return paths



def _report_is_verified(row: Dict[str, Any]) -> bool:
    """True only for reports actually produced from a provider + live sources."""
    dataset = (row.get("researcher_output") or {}).get("dataset") or {}
    writer = row.get("writer_output") or {}
    return bool(writer.get("verified_answer") and dataset.get("verified_sources"))


def _require_verified_report(row: Dict[str, Any]) -> None:
    if answer_policy.strict_mode() and not _report_is_verified(row):
        raise answer_policy.AnswerUnavailable(
            "This report was not produced from a configured API and live "
            "sources, so Meridian will not present it as a verified answer.",
            "Generate a new report after saving a provider API key in Settings.",
            "unverified_report")

def _persist_state(report_id: str, state: Dict[str, Any]) -> None:
    from datetime import datetime
    translation = state.get("translation", {})
    writer = state.get("writer", {})
    dataset = state.get("dataset", {})
    queries.update_report(
        report_id,
        company=dataset.get("company", clean_company(state.get("query", ""))),
        researcher_output=state.get("researcher", {}),
        analyst_output=state.get("analyst", {}),
        writer_output=writer,
        chat_output=state.get("chat", {}),
        forecast_output=state.get("forecast", {}),
        factcheck_output=state.get("factchecker", {}),
        final_report=state.get("final_report", ""),
        translated_report=translation.get("content"),
        reliability_score=int(state.get("reliability_score", 0) or 0),
        status="completed", completed_at=datetime.utcnow(),
        error_message=None,
    )


def _worker(report_id: str, query: str, region: str, period: str, language: str) -> None:
    job = _JOBS[report_id]
    def emit(event: dict) -> None:
        with job.cond:
            job.events.append(event)
            job.cond.notify_all()
    try:
        orch = Orchestrator(report_id, emit)
        state = orch.run(query, region=region, period=period, language=language)
        _persist_state(report_id, state)
        emit({"type": "exporting", "message": "Building PDF, PowerPoint and Excel exports"})
        try:
            generate_exports(report_id)
        except Exception as exc:
            logger.exception("Export stage failed")
            emit({"type": "warning", "message": f"Exports unavailable: {exc}"})
        job.status = "completed"
        job.finished_at = time.time()
        emit({"type": "job_complete", "report_id": report_id, "status": "completed"})
    except Exception as exc:
        logger.exception("Report job %s failed", report_id)
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = time.time()
        try:
            queries.update_report(report_id, status="failed", error_message=str(exc))
        except Exception:
            pass
        payload = {"type": "job_failed", "report_id": report_id, "error": str(exc),
                   "trace": traceback.format_exc()[-1200:]}
        if isinstance(exc, answer_policy.AnswerUnavailable):
            payload.update({"error_type": "answer_unavailable", "reason": exc.reason,
                            "hint": exc.hint,
                            "setup_path": exc.as_dict()["setup_path"]})
        emit(payload)


def start_report(query: str, *, region: str = "Global", period: str = "3Y",
                 language: str = "en", company: str = "") -> str:
    """Create a report and run the agent graph in a background thread."""
    answer_policy.require_api("research report")
    query = (query or "").strip()
    if len(query) < 3:
        raise ValueError("Please enter a research query of at least 3 characters")
    if len(query) > 600:
        raise ValueError("Query is too long (600 characters maximum)")
    region = region if region in REGIONS else "Global"
    period = period if period in PERIODS else "3Y"
    language = language if language in {c for c, _, _ in SUPPORTED_LANGUAGES} else "en"
    ensure_schema()
    report_id = queries.create_report(query, company=company or clean_company(query),
                                      region=region, period=period, language=language)
    with _LOCK:
        _JOBS[report_id] = ReportJob(report_id=report_id)
    t = threading.Thread(target=_worker, args=(report_id, query, region, period, language),
                         daemon=True, name=f"meridian-report-{report_id[:8]}")
    t.start()
    return report_id


def get_job(report_id: str) -> Optional[ReportJob]:
    with _LOCK:
        return _JOBS.get(report_id)


def job_status(report_id: str) -> Dict[str, Any]:
    row = queries.get_report(report_id)
    job = get_job(report_id)
    agents: Dict[str, Dict[str, Any]] = {}
    if job:
        for e in job.events:
            if e.get("type") == "agent_start":
                agents[e["agent"]] = {"name": e.get("name", e["agent"]),
                                      "icon": e.get("icon", "◆"), "status": "working",
                                      "started_at": e.get("ts")}
            elif e.get("type") == "agent_done":
                a = agents.setdefault(e["agent"], {"name": e.get("name", e["agent"]),
                                                   "icon": "◆"})
                a.update({"status": "done", "elapsed_ms": e.get("elapsed_ms", 0),
                          "provider": e.get("provider", ""),
                          "warning": e.get("warning", "")})
    progress = next((e.get("percent", 0) for e in reversed(job.events)
                     if job and e.get("type") == "progress"), 0)
    status = job.status if job else (row or {}).get("status", "unknown")
    return {
        "report_id": report_id, "status": status, "progress": progress,
        "agents": agents, "error": job.error if job else (row or {}).get("error_message", ""),
        "events": len(job.events) if job else 0,
        "elapsed_s": round((time.time() - job.started_at), 1) if job else 0,
    }


def event_stream(report_id: str, from_index: int = 0,
                 max_wait: float = 90) -> Generator[dict, None, None]:
    """Yield events as they arrive (used by the SSE endpoint)."""
    job = get_job(report_id)
    if job is None:
        row = queries.get_report(report_id)
        if not row:
            yield {"type": "error", "error": "Report not found"}
            return
        yield {"type": "snapshot", "status": row["status"], "percent": 100}
        return
    idx = max(0, from_index)
    deadline = time.time() + max_wait
    terminal = {"job_complete", "job_failed"}
    while time.time() < deadline:
        with job.cond:
            if idx >= len(job.events):
                job.cond.wait(timeout=1.0)
            batch = job.events[idx:].copy()
            idx = len(job.events)
            finished = any(e.get("type") in terminal for e in batch)
        for e in batch:
            yield e
        if finished:
            return
        yield {"type": "heartbeat", "ts": time.time()}
    return


def report_context(report_id: str) -> Dict[str, Any]:
    """Reconstruct the agent context from a persisted report."""
    row = queries.get_report(report_id)
    if not row:
        raise KeyError("Report not found")
    dataset = (row.get("researcher_output") or {}).get("dataset")
    if not dataset and answer_policy.strict_mode():
        raise answer_policy.AnswerUnavailable(
            "This saved report has no verified research context.",
            "Generate a new report with a configured provider API key.",
            "no_verified_context")
    dataset = dataset or collect_market_data(row["query"], row.get("region", "Global"),
                                             row.get("period", "3Y"))
    if answer_policy.strict_mode() and not (dataset.get("verified_sources") or []):
        raise answer_policy.AnswerUnavailable(
            "This saved report has no verified live sources.",
            "Generate a new report with a configured provider API key and live sources.",
            "no_verified_context")
    return {
        "query": row["query"], "region": row.get("region", "Global"),
        "period": row.get("period", "3Y"), "report_id": report_id,
        "dataset": dataset, "researcher": row.get("researcher_output") or {},
        "analyst": row.get("analyst_output") or {},
        "writer": row.get("writer_output") or {},
        "forecast": row.get("forecast_output") or {},
        "factcheck": row.get("factcheck_output") or {},
        "factchecker": row.get("factcheck_output") or {},
    }


def answer_chat(report_id: str, question: str) -> Dict[str, Any]:
    answer_policy.require_api("chat answer")
    question = (question or "").strip()
    if not question:
        raise ValueError("Question cannot be empty")
    if len(question) > 1000:
        raise ValueError("Question is too long")
    ctx = report_context(report_id)
    return ChatAgent(report_id).answer(ctx, question, report_id)


def translate_report(report_id: str, language: str) -> Dict[str, Any]:
    if language != "en":
        answer_policy.require_api("translation")
    ctx = report_context(report_id)
    markdown = (ctx["writer"].get("markdown") or
                queries.get_report(report_id).get("final_report") or "")
    cached = queries.get_cached_translation(report_id, language)
    if cached:
        return {"language": language, "content": cached, "method": "cached",
                "native": next((n for c, _, n in SUPPORTED_LANGUAGES if c == language), language),
                "note": "Served from the translation cache."}
    return TranslatorAgent(report_id).translate(markdown, language, ctx, report_id)


def dashboard_payload(report_id: str, region: str = "", period: str = "",
                      competitor: str = "") -> Dict[str, Any]:
    """Chart-ready data for a report, with interactive filters applied."""
    row = queries.get_report(report_id)
    if not row:
        raise KeyError("Report not found")
    _require_verified_report(row)
    region = region or row.get("region", "Global")
    period = period or row.get("period", "3Y")
    if answer_policy.strict_mode():
        # Filters must not pretend to recompute evidence that was never
        # collected for another region/period. Snap back to the report's own
        # verified scope; a different scope requires a new report.
        region = row.get("region", region)
        period = row.get("period", period)
    dataset = ((row.get("researcher_output") or {}).get("dataset")
               or collect_market_data(row["query"], region, period))
    analyst = row.get("analyst_output") or {}
    forecast = row.get("forecast_output") or {}
    factcheck = row.get("factcheck_output") or {}
    writer = row.get("writer_output") or {}
    selected = competitor or (dataset["competitors"][0]["name"] if dataset["competitors"] else "")
    dataset["confidence_note"] = answer_policy.provenance_note(dataset)
    return {
        "report": {k: row.get(k) for k in
                   ("id", "query", "company", "region", "period", "status", "language",
                    "reliability_score", "created_at", "completed_at", "pdf_path",
                    "pptx_path", "excel_path")},
        "dataset": dataset,
        "charts": {
            "history": dataset["history"], "competitors": dataset["competitors"],
            "quarters": dataset["quarters"], "sentiment": dataset["sentiment"],
            "heatmap": dataset["heatmap"], "heatmap_weeks": dataset["heatmap_weeks"],
            "heatmap_channels": dataset["heatmap_channels"],
            "segments": dataset["segments"], "macro": dataset["macro"],
            "forecast": forecast.get("series", []),
            "social_mentions": dataset["social_mentions"],
        },
        "filters": {"region": region, "period": period, "competitor": selected,
                    "regions": list(REGIONS), "periods": list(PERIODS),
                    "competitors": [c["name"] for c in dataset["competitors"]]},
        "analysis": {
            "summary": analyst.get("summary", ""), "swot": analyst.get("swot", {}),
            "pestle": analyst.get("pestle", []), "porter": analyst.get("porter", []),
            "sizing": analyst.get("sizing", {}), "trends": analyst.get("trends", []),
            "key_metrics": analyst.get("key_metrics", []),
        },
        "forecast": forecast, "factcheck": factcheck,
        "writer": {"executive_summary": writer.get("executive_summary", ""),
                   "sections": writer.get("sections", []),
                   "markdown": writer.get("markdown", ""),
                   "citations": writer.get("citations", [])},
        "selected_competitor": next((c for c in dataset["competitors"]
                                     if c["name"] == selected),
                                    dataset["competitors"][0] if dataset["competitors"] else {}),
        "readiness": answer_policy.readiness(),
        "agent_logs": queries.get_agent_logs(report_id),
        "sources": dataset["sources"],
    }


def _verified_comparison(company_a: str, company_b: str,
                          region: str) -> Dict[str, Any]:
    """Compare two companies using an LLM and real sources, never fake metrics."""
    da = collect_market_data(company_a, region)
    db = collect_market_data(company_b, region)
    sources = (da.get("verified_sources") or []) + (db.get("verified_sources") or [])
    answer_policy.require_evidence({"verified_sources": sources})
    prompt = (
        "Compare these two companies for a market-intelligence scorecard. "
        "Return JSON with keys: verdict (2-3 sentences, grounded only in the "
        "VERIFIED SOURCES), metrics (array of exactly 5 objects with metric, a, b, "
        "unit, note). Set a and b to 0 unless a real figure appears in the sources; "
        "in that case put the exact figure and its source id in note. Never invent "
        "a number, publisher, URL or citation.\n\n"
        f"COMPANY A: {company_a}\nCOMPANY B: {company_b}\nREGION: {region}\n\n"
        f"VERIFIED SOURCES:\n" + str(sources)[:6000]
    )
    try:
        res = call_llm(effective_slot("analyst"),
                       "You are an evidence-bound market analyst. Return only valid JSON.",
                       prompt, max_tokens=900, temperature=0.2, json_mode=True,
                       timeout=settings.agent_timeout_s)
    except Exception as exc:
        raise answer_policy.AnswerUnavailable(
            f"The configured provider could not produce a comparison: {exc}",
            "Check the key, model and quota in Settings → API Keys.",
            "provider_failed") from exc
    parsed = extract_json(res["text"])
    if not isinstance(parsed, dict):
        raise answer_policy.AnswerUnavailable(
            "The provider returned an unusable comparison; no scorecard was invented.",
            "Try a different model in Settings → API Keys.", "unusable_output")
    raw = parsed.get("metrics")
    metrics = []
    for m in (raw if isinstance(raw, list) else [])[:5]:
        if not isinstance(m, dict):
            continue
        try:
            a_val, b_val = float(m.get("a") or 0), float(m.get("b") or 0)
        except (TypeError, ValueError):
            a_val, b_val = 0.0, 0.0
        metrics.append({"metric": str(m.get("metric") or "Unverified dimension")[:80],
                        "a": a_val, "b": b_val,
                        "unit": str(m.get("unit") or "")[:12],
                        "note": str(m.get("note") or "No verified figure")[:200]})
    while len(metrics) < 5:
        metrics.append({"metric": f"Dimension {len(metrics)+1} (not available)",
                        "a": 0.0, "b": 0.0, "unit": "",
                        "note": "No verified figure was supplied by a live source."})
    return {
        "company_a": company_a, "company_b": company_b, "region": region,
        "metrics": metrics, "dataset_a": da, "dataset_b": db,
        "verdict": str(parsed.get("verdict") or "No verified verdict available.")[:600],
        "verified_sources": sources, "data_mode": "verified",
        "provider": res["provider"], "model": res["model"],
    }


def compare_companies(company_a: str, company_b: str, region: str = "Global") -> Dict[str, Any]:
    if not company_a.strip() or not company_b.strip():
        raise ValueError("Both company names are required")
    if company_a.strip().lower() == company_b.strip().lower():
        raise ValueError("Please choose two different companies")
    answer_policy.require_api("company comparison")
    a, b = clean_company(company_a), clean_company(company_b)
    data = (build_comparison(a, b, region) if answer_policy.sample_mode()
            else _verified_comparison(a, b, region))
    try:
        queries.save_comparison(data["company_a"], data["company_b"],
                                {"metrics": data["metrics"], "verdict": data["verdict"]})
    except Exception:
        pass
    return data


def compare_reports(report_a: str, report_b: str) -> Dict[str, Any]:
    a, b = queries.get_report(report_a), queries.get_report(report_b)
    if not a or not b:
        raise KeyError("One or both reports were not found")
    _require_verified_report(a)
    _require_verified_report(b)
    def summary(r):
        da = (r.get("analyst_output") or {})
        ds = (r.get("researcher_output") or {}).get("dataset") or {}
        return {
            "id": r["id"], "query": r["query"], "company": r.get("company", ""),
            "region": r.get("region", ""), "period": r.get("period", ""),
            "market_size": ds.get("market_size_usd_b", 0), "cagr": ds.get("cagr_pct", 0),
            "reliability": r.get("reliability_score", 0),
            "summary": da.get("summary", ""),
            "executive_summary": (r.get("writer_output") or {}).get("executive_summary", ""),
            "created_at": r.get("created_at"),
        }
    return {"report_a": summary(a), "report_b": summary(b)}


# --------------------------------------------------------------------------- #
# Settings API
# --------------------------------------------------------------------------- #
def settings_payload() -> Dict[str, Any]:
    return {
        "providers": list_providers(),
        "slots": key_manager.key_status(),
        "languages": [{"code": c, "name": n, "native": nat}
                      for c, n, nat in SUPPORTED_LANGUAGES],
        "regions": list(REGIONS), "periods": list(PERIODS),
        "encryption": "Fernet (AES-128-CBC + HMAC-SHA256)",
        "demo_mode": answer_policy.sample_mode(),
        "readiness": answer_policy.readiness(),
        "configured_count": sum(1 for s in key_manager.key_status() if s["configured"]),
    }


def save_key(slot: str, provider: str, api_key: str, model: str = "") -> Dict[str, Any]:
    return key_manager.save_key(slot, provider, api_key, model)


def test_key(slot: str) -> Dict[str, Any]:
    return test_connection(slot)


def delete_key(slot: str) -> Dict[str, Any]:
    return {"ok": key_manager.delete_key(slot), "slot": slot}


def openrouter_free_models(refresh: bool = False) -> Dict[str, Any]:
    """Ranked, zero-cost OpenRouter catalogue for the Settings screen.

    The catalogue endpoint is public (no API key is sent) and cached for 15
    minutes. ``refresh=True`` forces a re-fetch from OpenRouter.
    """
    from app.api.openrouter_auto import describe
    return describe(force=refresh)


def apply_key_to_all(provider: str, api_key: str, model: str = "") -> Dict[str, Any]:
    n = key_manager.apply_to_all(provider, api_key, model)
    return {"ok": True, "slots_updated": n}


def overview_stats() -> Dict[str, Any]:
    stats = queries.report_stats()
    stats["active_keys"] = queries.count_active_keys()
    stats["reports_this_week"] = len([r for r in queries.list_reports(limit=100)
                                      if (r.get("created_at") or "")[:10] >=
                                      time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400))])
    return stats


def export_path(report_id: str, fmt: str) -> str:
    row = queries.get_report(report_id)
    if not row:
        raise KeyError("Report not found")
    _require_verified_report(row)
    key = {"pdf": "pdf_path", "pptx": "pptx_path", "excel": "excel_path"}.get(fmt)
    if not key:
        raise ValueError("Unsupported format")
    path = row.get(key)
    if not path or not Path(path).exists():
        generate_exports(report_id)
        row = queries.get_report(report_id)
        path = row.get(key)
    if not path or not Path(path).exists():
        raise RuntimeError(f"{fmt.upper()} export could not be generated")
    return str(path)


def startup_state() -> Dict[str, Any]:
    """Cheap, DB-free status used by health checks (never blocks a request)."""
    return {"ready": _BOOTSTRAP_DONE, "error": _BOOTSTRAP_ERROR or None,
            "reports": None}  # deliberately does not query the database


def wait_for_bootstrap(timeout_s: float = 3.0) -> bool:
    """Brief, bounded wait used only by first-page-load requests.

    Health checks and the ASGI lifespan never call this — Render must see a
    listening socket immediately. Waiting a couple of seconds here simply
    avoids racing the background schema warm-up on first page load.
    """
    deadline = time.time() + max(0.0, timeout_s)
    while not _BOOTSTRAP_DONE and time.time() < deadline:
        time.sleep(0.05)
    return _BOOTSTRAP_DONE


def bootstrap() -> None:
    """Prepare the schema; never manufacture a sample report on first load.

    A fresh install with no API key must open to an honest empty dashboard and
    a "connect an API key" prompt. Sample reports are only seeded when the
    operator explicitly enables ``MERIDIAN_SAMPLE_MODE``.
    """
    global _BOOTSTRAPPED, _BOOTSTRAP_DONE, _BOOTSTRAP_ERROR
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True
    try:
        ensure_schema()
        if answer_policy.sample_mode() and not queries.list_reports(limit=1):
            logger.info("SAMPLE MODE: seeding one clearly labelled offline report")
            rid = start_report("Global artificial intelligence platforms market 2026",
                               region="Global", period="5Y", language="en")
            job = get_job(rid)
            deadline = time.time() + 12
            while job and job.status == "processing" and time.time() < deadline:
                time.sleep(0.1)
        _BOOTSTRAP_DONE = True
    except Exception as exc:
        _BOOTSTRAP_ERROR = str(exc)
        logger.warning("Bootstrap skipped: %s", exc)
    finally:
        # Health checks must stay green even if seeding failed.
        _BOOTSTRAP_DONE = True

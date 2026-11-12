"""Streamlit dashboard page: query composer, KPIs, live charts, report list."""
from __future__ import annotations

import time

import streamlit as st

from app import services
from app.api import answer_policy
from app.config import REGIONS, PERIODS, SUPPORTED_LANGUAGES
from app.ui.components import (history_chart, kpi_strip, plot, share_chart,
                               badge)
from app.ui.theme import hero


def render() -> None:
    hero("One query. <em>The entire market landscape.</em>",
         "Six autonomous AI agents and a translator research, analyse, write, forecast "
         "and fact-check a board-ready market report — with interactive charts and instant exports.",
         "MULTI-AGENT MARKET INTELLIGENCE")

    ready = answer_policy.readiness()
    if ready["sample_mode"]:
        st.warning("SAMPLE MODE — offline sample data only. This is not real research.")
    elif not ready["answers_enabled"]:
        st.error(f"{ready['message']} {ready['hint']}")
    with st.form("query_form", clear_on_submit=False):
        query = st.text_input("Research query",
                              placeholder="e.g. Indian electric vehicle market 2026 — Tesla vs BYD")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1.4])
        with c1:
            region = st.selectbox("Region", REGIONS)
        with c2:
            period = st.selectbox("Period", PERIODS, index=2)
        with c3:
            language = st.selectbox("Language", [n for _, _, n in SUPPORTED_LANGUAGES])
        with c4:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            go = st.form_submit_button("◆  Generate Intelligence", use_container_width=True,
                                       disabled=not ready["answers_enabled"])
    if go:
        if len(query.strip()) < 3:
            st.error("Enter a research query of at least 3 characters.")
        else:
            code = next(c for c, _, n in SUPPORTED_LANGUAGES if n == language)
            with st.spinner("Dispatching the agent pipeline…"):
                try:
                    rid = services.start_report(query.strip(), region=region,
                                                period=period, language=code)
                except Exception as exc:
                    st.error(str(exc))
                    return
                deadline = time.time() + 30
                while time.time() < deadline:
                    stt = services.job_status(rid)
                    if stt["status"] != "processing":
                        break
                    time.sleep(.15)
            st.session_state.report_id = rid
            st.success("Report complete — open it from **Intelligence Report** in the sidebar.")
            st.rerun()

    stats = services.overview_stats()
    kpi_strip([
        {"label": "Reports", "value": str(stats["total_reports"]),
         "delta": f"{stats['completed']} completed"},
        {"label": "Avg reliability", "value": f"{stats['avg_reliability']:.0f}/100",
         "delta": "Claim-level verification"},
        {"label": "Sources", "value": str(stats["sources_analyzed"]),
         "delta": "Across all reports"},
        {"label": "Agent runs", "value": str(stats["agents_run"]),
         "delta": f"{stats['active_keys']} keys configured"},
    ])

    from app.database import queries
    reports = queries.list_reports(limit=1)
    if reports:
        try:
            d = services.dashboard_payload(reports[0]["id"])
            ds = d["dataset"]
            st.markdown(f"### Intelligence at a glance {badge(ds['data_mode'].upper())}",
                        unsafe_allow_html=True)
            a, b = st.columns([1.4, 1])
            with a:
                plot(history_chart(ds["history"]))
            with b:
                plot(share_chart(ds["competitors"]))
        except Exception as exc:
            st.warning(f"Chart data unavailable: {exc}")

    st.markdown("### Recent reports")
    rows = queries.list_reports(limit=6)
    if not rows:
        st.info("No reports yet — use the composer above to generate your first one.")
    for r in rows:
        c1, c2, c3 = st.columns([4, 1.2, 1])
        with c1:
            st.markdown(f"**{r['query']}**  \n"
                        f"<span style='color:#64748B;font-size:11px;font-family:JetBrains Mono'>"
                        f"{r['region']} · {r['period']} · {r['created_at'][:16]}</span>",
                        unsafe_allow_html=True)
        with c2:
            st.markdown(badge(r["status"].upper(), "ok" if r["status"] == "completed" else "bad"
                              if r["status"] == "failed" else ""), unsafe_allow_html=True)
        with c3:
            if st.button("Open", key=f"open_{r['id']}"):
                st.session_state.report_id = r["id"]
                st.rerun()
        st.markdown("<hr style='margin:8px 0'>", unsafe_allow_html=True)

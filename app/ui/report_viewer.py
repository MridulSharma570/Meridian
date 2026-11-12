"""Streamlit report viewer: filters, interactive charts, exports, translation."""
from __future__ import annotations

import streamlit as st

from app import services
from app.config import SUPPORTED_LANGUAGES
from app.ui.components import (forecast_chart, history_chart, plot, revenue_chart,
                               segment_chart, sentiment_heatmap, share_chart, badge)


def render() -> None:
    from app.database import queries
    rows = queries.list_reports(limit=100)
    completed = [r for r in rows if r["status"] == "completed"]
    if not completed:
        st.info("No completed reports yet. Generate one from the Dashboard.")
        return
    ids = [r["id"] for r in completed]
    labels = {r["id"]: f"{r['query'][:60]} · {r['created_at'][:10]}" for r in completed}
    current = st.session_state.get("report_id", ids[0])
    if current not in ids:
        current = ids[0]
    chosen = st.selectbox("Report", ids, index=ids.index(current),
                          format_func=lambda i: labels[i])
    st.session_state.report_id = chosen

    c1, c2, c3, c4 = st.columns([1, 1, 1.4, 1])
    with c1: region = st.selectbox("Region", ["Global", "North America", "Europe",
                                              "Asia Pacific", "India", "LATAM", "Middle East"])
    with c2: period = st.selectbox("Period", ["12M", "3Y", "5Y", "10Y"], index=2)
    with c3: pass
    with c4: pass

    try:
        d = services.dashboard_payload(chosen, region, period)
    except Exception as exc:
        st.error(f"Could not load report: {exc}")
        return
    ds, r = d["dataset"], d["report"]
    st.markdown(f"## {ds['company']} — {ds['sector']}")
    st.markdown(badge(ds["region"], "ok") + badge(ds["period"]) +
                badge(f"RELIABILITY {d['factcheck'].get('reliability_score', 0)}/100", "ok") +
                badge(ds["data_mode"].upper()), unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    for col, fmt, label, mime in (
        (b1, "pdf", "PDF Report", "application/pdf"),
        (b2, "pptx", "PowerPoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (b3, "excel", "Excel Workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")):
        with col:
            try:
                path = services.export_path(chosen, fmt)
                with open(path, "rb") as fh:
                    st.download_button(f"⬇  {label}", fh.read(),
                                       file_name=f"Meridian-{fmt}-{chosen[:8]}.{path.split('.')[-1]}",
                                       mime=mime, use_container_width=True)
            except Exception as exc:
                st.caption(f"{label} unavailable: {exc}")

    tabs = st.tabs(["Overview", "Full Report", "Forecast", "Verification", "Sources", "Agent Logs"])
    with tabs[0]:
        a, b = st.columns([1.4, 1])
        with a: plot(history_chart(ds["history"]))
        with b: plot(share_chart(ds["competitors"]))
        a, b = st.columns([1.4, 1])
        with a: plot(revenue_chart(ds["quarters"], d["selected_competitor"]["name"]))
        with b: plot(segment_chart(ds["segments"]))
        plot(sentiment_heatmap(ds))
        st.dataframe(ds["competitors"], use_container_width=True, hide_index=True)
    with tabs[1]:
        st.markdown(d["writer"].get("markdown", ""), unsafe_allow_html=False)
        langs = {n: c for c, _, n in SUPPORTED_LANGUAGES}
        pick = st.selectbox("Translate full report", list(langs.keys()))
        if st.button("Translate"):
            try:
                t = services.translate_report(chosen, langs[pick])
                st.markdown(t["content"])
                st.caption(f"Method: {t['method']} · {t['note']}")
            except Exception as exc:
                st.error(str(exc))
    with tabs[2]:
        if d["forecast"].get("series"):
            plot(forecast_chart(d["forecast"]["series"]))
        st.dataframe(d["forecast"].get("scenarios", []), use_container_width=True, hide_index=True)
    with tabs[3]:
        st.dataframe(d["factcheck"].get("claims", []), use_container_width=True, hide_index=True)
        st.caption(d["factcheck"].get("disclaimer", ""))
    with tabs[4]:
        st.dataframe(ds["sources"], use_container_width=True, hide_index=True)
        st.caption(ds["confidence_note"])
    with tabs[5]:
        st.dataframe(d["agent_logs"], use_container_width=True, hide_index=True)

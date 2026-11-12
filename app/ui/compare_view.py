"""Streamlit comparison page: company vs company, or two saved reports."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from app import services
from app.api import answer_policy
from app.ui.components import plot
from app.ui.theme import PLOTLY_LAYOUT, hero


def render() -> None:
    hero("Compare Mode", "Side-by-side intelligence for two companies or two saved reports.",
         "COMPARISON MODE")
    ready = answer_policy.readiness()
    if ready["sample_mode"]:
        st.warning("SAMPLE MODE — comparison metrics are offline sample data.")
    elif not ready["answers_enabled"]:
        st.error(f"{ready['message']} {ready['hint']}")
    c1, c2, c3 = st.columns([2, 2, 1.2])
    with c1: a = st.text_input("Company A", "Tesla")
    with c2: b = st.text_input("Company B", "BYD")
    with c3:
        st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
        run = st.button("◆  Compare", use_container_width=True,
                        disabled=not ready["answers_enabled"])
    if run:
        try:
            data = services.compare_companies(a, b)
            st.session_state.comparison = data
        except Exception as exc:
            st.error(str(exc))
    data = st.session_state.get("comparison")
    if data:
        st.markdown(f"### {data['company_a']}  vs  {data['company_b']}")
        st.success(data["verdict"])
        st.dataframe(data["metrics"], use_container_width=True, hide_index=True)
        fig = go.Figure()
        for name, dsx, colour in ((data["company_a"], data["dataset_a"], "#C9A84C"),
                                  (data["company_b"], data["dataset_b"], "#4C7BF3")):
            fig.add_trace(go.Scatter(x=[h["year"] for h in dsx["history"]],
                                     y=[h["value"] for h in dsx["history"]], name=name,
                                     line=dict(color=colour, width=3)))
        fig.update_layout(**PLOTLY_LAYOUT, height=320)
        plot(fig)
    st.markdown("### Compare two saved reports")
    from app.database import queries
    rows = [r for r in queries.list_reports(limit=100) if r["status"] == "completed"]
    if len(rows) >= 2:
        labels = {r["id"]: r["query"][:60] for r in rows}
        c1, c2 = st.columns(2)
        with c1: ra = st.selectbox("Report A", [r["id"] for r in rows], format_func=lambda x: labels[x])
        with c2: rb = st.selectbox("Report B", [r["id"] for r in rows][::-1],
                                   format_func=lambda x: labels[x])
        if st.button("Compare reports"):
            try:
                st.dataframe(services.compare_reports(ra, rb), use_container_width=True)
            except Exception as exc:
                st.error(str(exc))
    else:
        st.caption("Generate at least two reports to compare them here.")

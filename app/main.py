"""Meridian Streamlit entry point.

Run with:  streamlit run app/main.py
The premium web application (recommended) is served by FastAPI:
          python run.py
Both frontends share the exact same service and agent layer.
"""
from __future__ import annotations

import logging

import streamlit as st

from app import services
from app.config import settings
from app.ui.chat_interface import render as chat_page
from app.ui.compare_view import render as compare_page
from app.ui.dashboard import render as dashboard_page
from app.ui.report_viewer import render as report_page
from app.ui.settings_page import render as settings_page
from app.ui.theme import footer, inject_theme

logging.basicConfig(level=logging.INFO)
inject_theme()

try:
    services.bootstrap()
except Exception as exc:  # never let Streamlit die on a cold database
    st.sidebar.warning(f"Startup note: {exc}")

with st.sidebar:
    st.markdown('<div class="mrd-logo">◆ &nbsp; MERIDIAN</div>'
                '<p style="color:#8F8474;font-size:10px;letter-spacing:.12em;margin-top:2px">'
                'MARKET INTELLIGENCE, REDEFINED.</p>', unsafe_allow_html=True)
    st.markdown("<div class='mrd-rule'></div>", unsafe_allow_html=True)
    page = st.radio("Navigation",
                    ["Dashboard", "Intelligence Report", "Compare Mode",
                     "Follow-up Chat", "API Keys", "History"],
                    label_visibility="collapsed")
    st.markdown("<div class='mrd-rule'></div>", unsafe_allow_html=True)
    stats = services.overview_stats()
    st.caption(f"◆ {stats['total_reports']} reports · {stats['active_keys']} keys · "
               f"v{settings.version}")
    st.caption("Developed by **Mridul Sharma**")

try:
    if page == "Dashboard":
        dashboard_page()
    elif page == "Intelligence Report":
        report_page()
    elif page == "Compare Mode":
        compare_page()
    elif page == "Follow-up Chat":
        chat_page()
    elif page == "API Keys":
        settings_page()
    elif page == "History":
        from app.database import queries
        st.markdown("## Report History")
        rows = queries.list_reports(limit=100)
        st.dataframe(rows, use_container_width=True, hide_index=True)
        for r in rows:
            c1, c2 = st.columns([5, 1])
            with c1:
                st.caption(f"{r['query']} · {r['region']} · {r['created_at'][:16]}")
            with c2:
                if st.button("Delete", key=f"del_hist_{r['id']}"):
                    queries.delete_report(r['id'])
                    st.rerun()
except Exception as exc:
    st.error(f"Something went wrong: {exc}")
    st.exception(exc)

footer()

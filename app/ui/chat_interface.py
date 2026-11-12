"""Streamlit follow-up chat interface (Agent 4)."""
from __future__ import annotations

import streamlit as st

from app import services
from app.agents.chat_agent import ChatAgent


def render() -> None:
    st.markdown("### 💬 Follow-up Intelligence")
    st.caption("Agent 4 answers using the research context already gathered in a saved report.")
    from app.database import queries
    rows = [r for r in queries.list_reports(limit=100) if r["status"] == "completed"]
    if not rows:
        st.info("Generate a report first, then ask follow-up questions here.")
        return
    labels = {r["id"]: r["query"][:60] for r in rows}
    rid = st.selectbox("Report context", [r["id"] for r in rows],
                       format_func=lambda x: labels[x])
    for m in queries.get_chat_history(rid):
        with st.chat_message(m["role"]):
            st.markdown(m["message"])
    suggestions = ChatAgent.SUGGESTIONS
    cols = st.columns(2)
    for i, s in enumerate(suggestions[:4]):
        with cols[i % 2]:
            if st.button(s, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_question = s
    if q := (st.session_state.pop("pending_question", None) or st.chat_input("Ask about this report…")):
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Analysing report context…"):
                try:
                    ans = services.answer_chat(rid, q)
                    st.markdown(ans["answer"])
                    st.caption(ans["provider"])
                except Exception as exc:
                    st.error(str(exc))

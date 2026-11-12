"""Reusable premium HTML components and Plotly chart builders for Streamlit."""
from __future__ import annotations

from typing import Any, Dict, List

import plotly.graph_objects as go
import streamlit as st

from app.ui.theme import PALETTE, PLOTLY_LAYOUT

COLORS = [PALETTE["gold"], PALETTE["sapphire"], PALETTE["violet"],
          PALETTE["success"], PALETTE["gold2"], PALETTE["danger"]]


def card_start(title: str = "", subtitle: str = "") -> None:
    head = f"<h3 style='margin:0 0 4px'>{title}</h3>" if title else ""
    sub = f"<p class='mrd-sub' style='margin:0 0 16px'>{subtitle}</p>" if subtitle else ""
    st.markdown(f'<div class="mrd-card">{head}{sub}', unsafe_allow_html=True)


def card_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def badge(text: str, kind: str = "") -> str:
    return f'<span class="mrd-badge {kind}">{text}</span>'


def kpi_strip(items: List[Dict[str, str]]) -> None:
    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        with col:
            st.metric(it["label"], it["value"], it.get("delta", ""))


def _apply(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT, height=height)
    return fig


def history_chart(history: List[dict]) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[h["year"] for h in history], y=[h["value"] for h in history],
        mode="lines+markers", name="Market size (USD B)",
        line=dict(color=PALETTE["gold"], width=3),
        marker=dict(size=7, color=PALETTE["gold2"], line=dict(color=PALETTE["navy"], width=1)),
        fill="tozeroy", fillcolor="rgba(198,161,91,.10)",
        hovertemplate="%{x}: <b>%{y:,.1f}B</b><extra></extra>"))
    return _apply(fig)


def share_chart(competitors: List[dict]) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=[c["name"] for c in competitors], values=[c["share"] for c in competitors],
        hole=.62, marker=dict(colors=COLORS, line=dict(color=PALETTE["navy"], width=2)),
        textfont=dict(color=PALETTE["white"], size=10),
        hovertemplate="<b>%{label}</b><br>%{value:.1f}% share<extra></extra>"))
    fig.update_layout(**{k: v for k, v in PLOTLY_LAYOUT.items() if k not in {"xaxis", "yaxis"}},
                      height=300, showlegend=True)
    return fig


def revenue_chart(quarters: List[dict], focus: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[q["label"] for q in quarters],
                             y=[q["revenue"] for q in quarters], name=focus,
                             line=dict(color=PALETTE["gold"], width=3),
                             hovertemplate=f"<b>{focus}</b> %{{y:,.2f}}B<extra></extra>"))
    fig.add_trace(go.Scatter(x=[q["label"] for q in quarters],
                             y=[q["competitor_avg"] for q in quarters],
                             name="Competitor average",
                             line=dict(color=PALETTE["sapphire"], width=2, dash="dot"),
                             hovertemplate="<b>Peer avg</b> %{y:,.2f}B<extra></extra>"))
    return _apply(fig)


def forecast_chart(series: List[dict]) -> go.Figure:
    fig = go.Figure()
    x = [r["month"] for r in series]
    up = [r["optimistic"] for r in series]
    low = [r["pessimistic"] for r in series]
    fig.add_trace(go.Scatter(x=x + x[::-1], y=up + low[::-1], fill="toself",
                             fillcolor="rgba(139,124,246,.16)", line=dict(color="rgba(0,0,0,0)"),
                             name="Confidence band", hoverinfo="skip"))
    for key, name, colour, dash in (("optimistic", "Optimistic", PALETTE["success"], "dot"),
                                    ("base", "Base", PALETTE["gold"], "solid"),
                                    ("pessimistic", "Pessimistic", PALETTE["danger"], "dot")):
        fig.add_trace(go.Scatter(x=x, y=[r[key] for r in series], name=name,
                                 line=dict(color=colour, width=3 if key == "base" else 2, dash=dash),
                                 hovertemplate=f"<b>{name}</b> %{{y:,.1f}}B<extra></extra>"))
    return _apply(fig, 320)


def sentiment_heatmap(dataset: Dict[str, Any]) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=dataset["heatmap"], x=dataset["heatmap_weeks"],
        y=dataset["heatmap_channels"], colorscale=[
            [0, "#0B0906"], [.35, "#8C6D2F"], [.65, "#C6A15B"], [1, "#F3ECDD"]],
        zmin=0, zmax=1, colorbar=dict(title="Score", tickfont=dict(color=PALETTE["slate"])),
        hovertemplate="<b>%{y}</b> · %{x}<br>Sentiment %{z:.0%}<extra></extra>"))
    fig.update_layout(**{k: v for k, v in PLOTLY_LAYOUT.items() if k != "hovermode"}, height=300)
    return fig


def segment_chart(segments: List[dict]) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[s["value"] for s in segments], y=[s["name"] for s in segments],
        orientation="h", marker=dict(color=COLORS[:len(segments)]),
        hovertemplate="<b>%{y}</b> %{x:.1f}%<extra></extra>"))
    return _apply(fig)


def plot(fig: go.Figure) -> None:
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False, "responsive": True})

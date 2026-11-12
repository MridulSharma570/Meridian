"""Meridian design tokens and the Streamlit CSS override.

The signature trio — Deep Navy #0A1628, Champagne Gold #C9A84C and
Ivory Platinum #EDE4D3 — is applied to every Streamlit widget. All type
sizes follow a 4px grid; spacing follows an 8px grid.
"""
from __future__ import annotations

import streamlit as st
from app.config import settings

PALETTE = {
    "navy": "#0A1628", "navy2": "#111C32", "card": "#1A2744",
    "gold": "#C9A84C", "gold2": "#E8CE8A", "ivory": "#EDE4D3",
    "white": "#F8FAFC", "muted": "#94A3B8", "slate": "#64748B",
    "success": "#059669", "danger": "#E11D48", "violet": "#8B7CF6",
    "sapphire": "#4C7BF3",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=PALETTE["muted"], size=11),
    margin=dict(l=40, r=20, t=30, b=40), hovermode="x unified",
    xaxis=dict(gridcolor="rgba(255,255,255,.06)", zeroline=False,
               linecolor="rgba(255,255,255,.1)", tickfont=dict(color=PALETTE["slate"])),
    yaxis=dict(gridcolor="rgba(255,255,255,.06)", zeroline=False,
               linecolor="rgba(255,255,255,.1)", tickfont=dict(color=PALETTE["slate"])),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                font=dict(color=PALETTE["muted"], size=10)),
    hoverlabel=dict(bgcolor="#0A1628", bordercolor=PALETTE["gold"],
                    font=dict(color=PALETTE["white"], family="JetBrains Mono")),
)

CSS = """
<style>
@import url('https://api.fontshare.com/v2/css?f[]=satoshi@700,900,500&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--navy:#0A1628;--navy2:#111C32;--card:#1A2744;--gold:#C9A84C;--gold2:#E8CE8A;
 --ivory:#EDE4D3;--white:#F8FAFC;--muted:#94A3B8;--slate:#64748B;--line:rgba(255,255,255,.08)}
.stApp{background:radial-gradient(ellipse 70% 40% at 8% -5%,rgba(76,123,243,.10),transparent 60%),
 radial-gradient(ellipse 60% 40% at 95% 0%,rgba(139,124,246,.09),transparent 60%),#0A1628!important}
.stApp header{background:transparent!important}
#MainMenu,footer,.stDeployButton{visibility:hidden}
.stApp [data-testid="stSidebar"]{background:linear-gradient(180deg,#091426,#0A1628)!important;
 border-right:1px solid var(--line)!important}
.stApp [data-testid="stSidebar"] *{color:var(--muted)!important}
.block-container{padding-top:24px!important;padding-bottom:48px!important;max-width:1240px}
h1,h2,h3,h4,h5{font-family:'Satoshi',Inter,sans-serif!important;color:var(--ivory)!important;letter-spacing:-.02em!important}
p,span,label,div{font-family:'Inter',sans-serif!important}
code,.stMetricValue,[data-testid="stMetricValue"]{font-family:'JetBrains Mono',monospace!important}
.stMetric{background:rgba(26,39,68,.6)!important;border:1px solid var(--line)!important;
 border-radius:16px!important;padding:18px!important;backdrop-filter:blur(20px);
 box-shadow:0 8px 24px rgba(0,0,0,.22),0 24px 64px rgba(0,0,0,.2)}
[data-testid="stMetricValue"]{color:var(--ivory)!important;font-weight:700!important}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:11px!important;letter-spacing:.12em!important;text-transform:uppercase}
[data-testid="stMetricDelta"]{color:#34D399!important}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--line)!important}
.stTabs [data-baseweb="tab"]{color:var(--muted)!important;font-size:12px!important;
 border-bottom:2px solid transparent!important;padding:10px 16px!important}
.stTabs [aria-selected="true"]{color:var(--gold2)!important;border-bottom-color:var(--gold)!important}
.stTextInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"],
 .stMultiSelect [data-baseweb="select"],.stNumberInput input{background:#0E1A2E!important;
 color:var(--white)!important;border:1px solid var(--line)!important;border-radius:10px!important}
.stTextInput input:focus,.stSelectbox [data-baseweb="select"]:focus{border-color:var(--gold)!important;
 box-shadow:0 0 0 3px rgba(201,168,76,.1)!important}
.stButton button{background:linear-gradient(145deg,var(--gold),#B8943F)!important;color:var(--navy)!important;
 border:0!important;border-radius:12px!important;font-weight:600!important;font-size:13px!important;
 padding:10px 18px!important;box-shadow:0 4px 18px rgba(201,168,76,.22)!important;transition:all .2s!important}
.stButton button:hover{transform:translateY(-1px) scale(1.02);box-shadow:0 8px 28px rgba(201,168,76,.35)!important}
.stDownloadButton button{background:transparent!important;color:var(--gold2)!important;
 border:1px solid rgba(201,168,76,.5)!important;border-radius:12px!important}
.stDownloadButton button:hover{background:rgba(201,168,76,.1)!important}
hr{border-color:var(--line)!important}
.stDataFrame,.stTable{background:rgba(26,39,68,.5)!important;border-radius:12px!important}
.stAlert{border-radius:12px!important;background:rgba(26,39,68,.7)!important;border:1px solid var(--line)!important}
.stExpander{background:rgba(26,39,68,.5)!important;border:1px solid var(--line)!important;border-radius:12px!important}
.stSpinner>div{border-top-color:var(--gold)!important}
.mrd-card{background:rgba(26,39,68,.62);backdrop-filter:blur(20px);border:1px solid var(--line);
 border-radius:16px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.22);margin-bottom:16px}
.mrd-hero{background:linear-gradient(125deg,rgba(26,39,68,.9),rgba(14,26,46,.75) 60%,rgba(201,168,76,.07));
 border:1px solid rgba(201,168,76,.18);border-radius:20px;padding:32px 36px;margin-bottom:20px}
.mrd-eyebrow{font-size:10px;letter-spacing:.22em;color:var(--gold);font-weight:700;text-transform:uppercase}
.mrd-h1{font-family:'Satoshi',sans-serif!important;font-size:36px!important;font-weight:900!important;
 line-height:1.12!important;letter-spacing:-.03em!important;margin:10px 0!important;color:var(--ivory)!important}
.mrd-h1 em{font-style:normal;background:linear-gradient(100deg,var(--gold2),var(--gold),var(--ivory));
 -webkit-background-clip:text;background-clip:text;color:transparent}
.mrd-sub{color:var(--muted)!important;font-size:13px!important;line-height:1.7!important}
.mrd-kpi{font-family:'Satoshi',sans-serif;font-size:24px;font-weight:900;color:var(--ivory);letter-spacing:-.02em}
.mrd-badge{display:inline-block;font-size:10px;font-weight:700;padding:5px 10px;border-radius:20px;
 background:rgba(201,168,76,.12);color:var(--gold2);border:1px solid rgba(201,168,76,.28);margin-right:6px}
.mrd-badge.ok{background:rgba(5,150,105,.14);color:#34D399;border-color:rgba(5,150,105,.28)}
.mrd-badge.bad{background:rgba(225,29,72,.13);color:#FB7185;border-color:rgba(225,29,72,.28)}
.mrd-foot{text-align:center;color:var(--slate);font-size:11px;padding:24px 0 8px}
.mrd-foot b{color:var(--gold)}
.mrd-logo{font-family:'Satoshi',sans-serif;font-weight:900;letter-spacing:.18em;color:var(--ivory);font-size:17px}
.mrd-rule{height:1px;background:linear-gradient(90deg,var(--line),transparent);margin:20px 0}

/* ------------------------------------------------ Responsive Streamlit --- */
html{-webkit-text-size-adjust:100%}
img,svg,canvas{max-width:100%!important}
@media(min-width:1800px){.block-container{max-width:1440px!important}}
@media(max-width:1024px){
  .block-container{padding-left:20px!important;padding-right:20px!important;
    padding-top:16px!important;max-width:100%!important}
  .mrd-hero{padding:24px 22px!important}
  .mrd-h1{font-size:30px!important}
  .mrd-card{padding:18px!important}
}
@media(max-width:768px){
  /* Streamlit turns its sidebar into an overlay here; keep content full width. */
  .block-container{padding:12px 14px 88px!important;max-width:100%!important}
  .mrd-hero{padding:20px 16px!important;border-radius:16px!important}
  .mrd-h1{font-size:clamp(24px,7vw,30px)!important}
  .mrd-sub{font-size:12px!important}
  .mrd-card{padding:14px!important;border-radius:14px!important}
  .mrd-kpi{font-size:20px}
  .mrd-logo{font-size:15px}
  h1{font-size:24px!important}h2{font-size:20px!important}h3{font-size:17px!important}
  .stMetric{padding:12px!important}
  [data-testid="stMetricValue"]{font-size:20px!important}
  .stButton button,.stDownloadButton button{width:100%!important;min-height:44px!important}
  .stTabs [data-baseweb="tab"]{padding:10px 10px!important;font-size:11px!important}
  .stDataFrame,.stTable{overflow-x:auto!important}
  .stTextInput input,.stTextArea textarea{font-size:16px!important}
}
@media(max-width:480px){
  .block-container{padding-left:10px!important;padding-right:10px!important}
  .mrd-h1{font-size:24px!important}
  .mrd-badge{font-size:9px;padding:4px 8px}
  .stMetric{padding:10px!important}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}
}
</style>
"""


def inject_theme() -> None:
    """Apply the full Meridian theme. Call once at the top of the Streamlit app."""
    st.set_page_config(page_title="Meridian · Market Intelligence", page_icon="◆",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, eyebrow: str = "MERIDIAN") -> None:
    st.markdown(
        f'<div class="mrd-hero"><div class="mrd-eyebrow">{eyebrow}</div>'
        f'<div class="mrd-h1">{title}</div><p class="mrd-sub">{subtitle}</p></div>',
        unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        f'<div class="mrd-foot">◆ &nbsp; MERIDIAN · {settings.tagline}<br>'
        f'Developed by <b>Mridul Sharma</b> · v{settings.version}</div>',
        unsafe_allow_html=True)

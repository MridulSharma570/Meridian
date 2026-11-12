"""Meridian design tokens and the Streamlit CSS override.

The signature trio — Obsidian #0B0906, Champagne Gold #C6A15B and
Pearl #F3ECDD — is applied to every Streamlit widget. All type
sizes follow a 4px grid; spacing follows an 8px grid.
"""
from __future__ import annotations

import streamlit as st
from app.config import settings

PALETTE = {
    "navy": "#0B0906", "navy2": "#17120D", "card": "#211A13",
    "gold": "#C6A15B", "gold2": "#E7CE8C", "ivory": "#F3ECDD",
    "white": "#F3ECDD", "muted": "#B9AE9C", "slate": "#8F8474",
    "success": "#C6A15B", "danger": "#F3ECDD", "violet": "#F3ECDD",
    "sapphire": "#E7CE8C",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=PALETTE["muted"], size=11),
    margin=dict(l=40, r=20, t=30, b=40), hovermode="x unified",
    xaxis=dict(gridcolor="rgba(243,236,221,.06)", zeroline=False,
               linecolor="rgba(243,236,221,.1)", tickfont=dict(color=PALETTE["slate"])),
    yaxis=dict(gridcolor="rgba(243,236,221,.06)", zeroline=False,
               linecolor="rgba(243,236,221,.1)", tickfont=dict(color=PALETTE["slate"])),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                font=dict(color=PALETTE["muted"], size=10)),
    hoverlabel=dict(bgcolor="#0B0906", bordercolor=PALETTE["gold"],
                    font=dict(color=PALETTE["white"], family="JetBrains Mono")),
)

CSS = """
<style>
@import url('https://api.fontshare.com/v2/css?f[]=satoshi@700,900,500&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--navy:#0B0906;--navy2:#17120D;--card:#211A13;--gold:#C6A15B;--gold2:#E7CE8C;
 --ivory:#F3ECDD;--white:#F3ECDD;--muted:#B9AE9C;--slate:#8F8474;--line:rgba(243,236,221,.08)}
.stApp{background:radial-gradient(ellipse 70% 40% at 8% -5%,rgba(198,161,91,.10),transparent 60%),
 radial-gradient(ellipse 60% 40% at 95% 0%,rgba(243,236,221,.09),transparent 60%),#0B0906!important}
.stApp header{background:transparent!important}
#MainMenu,footer,.stDeployButton{visibility:hidden}
.stApp [data-testid="stSidebar"]{background:linear-gradient(180deg,#0B0906,#0B0906)!important;
 border-right:1px solid var(--line)!important}
.stApp [data-testid="stSidebar"] *{color:var(--muted)!important}
.block-container{padding-top:24px!important;padding-bottom:48px!important;max-width:1240px}
h1,h2,h3,h4,h5{font-family:'Satoshi',Inter,sans-serif!important;color:var(--ivory)!important;letter-spacing:-.02em!important}
p,span,label,div{font-family:'Inter',sans-serif!important}
code,.stMetricValue,[data-testid="stMetricValue"]{font-family:'JetBrains Mono',monospace!important}
.stMetric{background:rgba(33,26,19,.6)!important;border:1px solid var(--line)!important;
 border-radius:16px!important;padding:18px!important;backdrop-filter:blur(20px);
 box-shadow:0 8px 24px rgba(0,0,0,.22),0 24px 64px rgba(0,0,0,.2)}
[data-testid="stMetricValue"]{color:var(--ivory)!important;font-weight:700!important}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-size:11px!important;letter-spacing:.12em!important;text-transform:uppercase}
[data-testid="stMetricDelta"]{color:#E7CE8C!important}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--line)!important}
.stTabs [data-baseweb="tab"]{color:var(--muted)!important;font-size:12px!important;
 border-bottom:2px solid transparent!important;padding:10px 16px!important}
.stTabs [aria-selected="true"]{color:var(--gold2)!important;border-bottom-color:var(--gold)!important}
.stTextInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"],
 .stMultiSelect [data-baseweb="select"],.stNumberInput input{background:#14100B!important;
 color:var(--white)!important;border:1px solid var(--line)!important;border-radius:10px!important}
.stTextInput input:focus,.stSelectbox [data-baseweb="select"]:focus{border-color:var(--gold)!important;
 box-shadow:0 0 0 3px rgba(198,161,91,.1)!important}
.stButton button{background:linear-gradient(145deg,var(--gold),#A9853D)!important;color:var(--navy)!important;
 border:0!important;border-radius:12px!important;font-weight:600!important;font-size:13px!important;
 padding:10px 18px!important;box-shadow:0 4px 18px rgba(198,161,91,.22)!important;transition:all .2s!important}
.stButton button:hover{transform:translateY(-1px) scale(1.02);box-shadow:0 8px 28px rgba(198,161,91,.35)!important}
.stDownloadButton button{background:transparent!important;color:var(--gold2)!important;
 border:1px solid rgba(198,161,91,.5)!important;border-radius:12px!important}
.stDownloadButton button:hover{background:rgba(198,161,91,.1)!important}
hr{border-color:var(--line)!important}
.stDataFrame,.stTable{background:rgba(33,26,19,.5)!important;border-radius:12px!important}
.stAlert{border-radius:12px!important;background:rgba(33,26,19,.7)!important;border:1px solid var(--line)!important}
.stExpander{background:rgba(33,26,19,.5)!important;border:1px solid var(--line)!important;border-radius:12px!important}
.stSpinner>div{border-top-color:var(--gold)!important}
.mrd-card{background:rgba(33,26,19,.62);backdrop-filter:blur(20px);border:1px solid var(--line);
 border-radius:16px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,.22);margin-bottom:16px}
.mrd-hero{background:linear-gradient(125deg,rgba(33,26,19,.9),rgba(18,14,10,.75) 60%,rgba(198,161,91,.07));
 border:1px solid rgba(198,161,91,.18);border-radius:20px;padding:32px 36px;margin-bottom:20px}
.mrd-eyebrow{font-size:10px;letter-spacing:.22em;color:var(--gold);font-weight:700;text-transform:uppercase}
.mrd-h1{font-family:'Satoshi',sans-serif!important;font-size:36px!important;font-weight:900!important;
 line-height:1.12!important;letter-spacing:-.03em!important;margin:10px 0!important;color:var(--ivory)!important}
.mrd-h1 em{font-style:normal;background:linear-gradient(100deg,var(--gold2),var(--gold),var(--ivory));
 -webkit-background-clip:text;background-clip:text;color:transparent}
.mrd-sub{color:var(--muted)!important;font-size:13px!important;line-height:1.7!important}
.mrd-kpi{font-family:'Satoshi',sans-serif;font-size:24px;font-weight:900;color:var(--ivory);letter-spacing:-.02em}
.mrd-badge{display:inline-block;font-size:10px;font-weight:700;padding:5px 10px;border-radius:20px;
 background:rgba(198,161,91,.12);color:var(--gold2);border:1px solid rgba(198,161,91,.28);margin-right:6px}
.mrd-badge.ok{background:rgba(198,161,91,.14);color:#E7CE8C;border-color:rgba(198,161,91,.28)}
.mrd-badge.bad{background:rgba(243,236,221,.13);color:#F3ECDD;border-color:rgba(243,236,221,.28)}
.mrd-foot{text-align:center;color:var(--slate);font-size:11px;padding:24px 0 8px}
.mrd-foot b{color:var(--gold)}
.mrd-logo{font-family:'Satoshi',sans-serif;font-weight:900;letter-spacing:.18em;color:var(--ivory);font-size:17px}
.mrd-rule{height:1px;background:linear-gradient(90deg,var(--line),transparent);margin:20px 0}

/* ------------------------------------------------ Responsive Streamlit --- */
html{-webkit-text-size-adjust:100%;max-width:100%;scroll-padding-top:64px}
body{max-width:100%;overflow-x:hidden}
button{touch-action:manipulation;-webkit-tap-highlight-color:transparent}
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
  /* Streamlit turns its sidebar into an overlay here; keep content full width.
     No bottom bar is reserved — the whole viewport belongs to the content. */
  .block-container{padding:12px 14px 28px!important;max-width:100%!important;
    padding-bottom:calc(28px + env(safe-area-inset-bottom,0px))!important}
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
  .stTabs [data-baseweb="tab"]{padding:10px 10px!important;font-size:12px!important;
    min-height:44px!important}
  .stDataFrame,.stTable{overflow-x:auto!important}
  /* 16px keeps iOS from zooming the viewport when any field is focused. */
  .stTextInput input,.stTextArea textarea,.stNumberInput input,
  .stSelectbox input,.stMultiSelect input{font-size:16px!important;min-height:44px!important}
  .stSelectbox [data-baseweb="select"],.stMultiSelect [data-baseweb="select"]{
    min-height:44px!important}
  div[data-baseweb="select"]>div{font-size:16px!important}
}
@media(max-width:480px){
  .block-container{padding-left:10px!important;padding-right:10px!important}
  .mrd-h1{font-size:24px!important}
  .mrd-badge{font-size:9px;padding:4px 8px}
  .stMetric{padding:10px!important}
  .stTabs [data-baseweb="tab"]{padding:9px 8px!important}
}
@media(max-width:380px){
  .mrd-card{padding:12px!important}
  .mrd-h1{font-size:22px!important}
  .mrd-sub{font-size:11px!important}
  h1{font-size:21px!important}h2{font-size:18px!important}
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

# The Streamlit CSS string above is kept for compatibility; inject_theme()
# appends this final fit layer so older cached rules cannot force overflow.
CSS += """
<style>
:root{--ink:#0B0906;--champagne:#C6A15B;--pearl:#F3ECDD}
html,body{max-width:100%;overflow-x:clip}
img,svg,canvas,video,iframe{max-width:100%!important}
.mrd-card,.mrd-hero{min-width:0;overflow:hidden;overflow-wrap:anywhere}
.stDataFrame,.stTable{max-width:100%;overflow-x:auto!important}
@media(max-width:700px){.mrd-badge{white-space:normal!important;text-align:center}}
</style>
"""

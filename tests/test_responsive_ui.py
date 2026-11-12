"""Regression tests for the responsive SPA and its navigation controls.

These are dependency-free static checks: they guard the CSS/HTML/JS contracts
that make the layout work from 320px phones to 1800px+ desktops, and ensure the
menu button can never become a dead control again.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "app" / "web"


def read(rel: str) -> str:
    return (ROOT / rel).read_text()


def media_block(css: str, header: str) -> str:
    """Return the declaration body of one @media rule (brace-aware)."""
    start = css.index(header)
    open_brace = css.index("{", start)
    depth = 0
    for i in range(open_brace, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace + 1:i]
    raise AssertionError(f"Unterminated media rule: {header}")


# --------------------------------------------------------------------------- #
# Document head and accessibility basics
# --------------------------------------------------------------------------- #
def test_viewport_meta_is_mobile_ready():
    html = read("app/web/index.html")
    assert 'width=device-width, initial-scale=1, viewport-fit=cover' in html
    assert 'user-scalable=no' not in html
    assert 'maximum-scale=1' not in html          # never block pinch zoom
    assert '<meta name="color-scheme" content="dark" />' in html


def test_menu_button_is_a_real_control():
    html = read("app/web/index.html")
    assert 'id="collapseBtn"' in html
    assert 'aria-controls="sidebar"' in html
    assert 'aria-expanded="true"' in html
    assert 'aria-label="Toggle navigation"' in html


def test_all_layout_controls_exist():
    html = read("app/web/index.html")
    for marker in ('id="scrim"', 'data-action="close-drawers"',
                   'id="missionBtn"', 'aria-controls="mission"',
                   'id="tabbar"', 'data-action="close-nav"',
                   'data-action="close-mission"', 'id="missionPulse"'):
        assert marker in html, f"missing {marker}"
    assert html.count('class="tabbar-item') == 5
    assert 'aria-label="New report"' in html


def test_js_layout_controller_is_complete():
    js = read("app/web/app.js")
    for marker in ("matchMedia('(max-width: 1100px)')", "function initLayout()",
                   "function toggleNav()", "function toggleMission()",
                   "function closeDrawers(", "function onLayoutModeChange()",
                   "localStorage.setItem", "'change', onLayoutModeChange",
                   "ev.key === 'Escape'", "focusBefore",
                   "addEventListener('click', toggleNav)",
                   "addEventListener('click', toggleMission)",
                   "'close-nav' || a === 'close-mission' || a === 'close-drawers'",
                   ".tabbar-item[data-view]"):
        assert marker in js, f"missing JS contract: {marker}"
    assert "$('.shell').classList.toggle('collapsed')" not in js  # old dead handler


def test_boot_initialises_layout_before_first_render():
    js = read("app/web/app.js")
    boot = js[js.index("(async function boot()"):]
    assert boot.index("initLayout()") < boot.index("await api('/api/bootstrap')")


def test_navigating_closes_mobile_drawers():
    js = read("app/web/app.js")
    fn = js[js.index("function navigate(view, id)"):]
    fn = fn[:fn.index("async function renderView()")]
    assert "closeDrawers()" in fn
    assert ".tabbar-item[data-view]" in fn


# --------------------------------------------------------------------------- #
# CSS breakpoints
# --------------------------------------------------------------------------- #
def test_compact_drawer_rules():
    css = read("app/web/app.css")
    block = media_block(css, "@media(max-width:1100px)")
    for marker in ("grid-template-columns:minmax(0,1fr)",
                   ".tabbar{display:grid}", "position:fixed",
                   "translateX(-102%)", "translateX(102%)",
                   "body.nav-open .sidebar", "body.mission-open .mission",
                   "body.nav-open,body.mission-open{overflow:hidden}",
                   "env(safe-area-inset-bottom", "toast-stack",
                   ".shell.mission-hidden .mission{display:flex}"):
        assert marker in block, f"compact CSS missing {marker}"


def test_phone_rules():
    css = read("app/web/app.css")
    block = media_block(css, "@media(max-width:700px)")
    for marker in (".mobile-brand{display:flex}", ".crumb{display:none}",
                   "#queryInput{font-size:16px}",
                   ".composer-row{display:grid", ".g4{grid-template-columns:repeat(2",
                   ".report-row{grid-template-columns:minmax(0,1fr)",
                   ".slot-grid{grid-template-columns:1fr}",
                   ".heat-grid{min-width:480px}", ".footer{flex-direction:column"):
        assert marker in block, f"phone CSS missing {marker}"
    assert ".icon-btn{width:40px;height:40px}" in block


def test_tiny_phone_and_desktop_rules():
    css = read("app/web/app.css")
    tiny = media_block(css, "@media(max-width:380px)")
    assert ".crumb{display:flex" in tiny
    assert ".new-report-btn .btn-label" in media_block(css, "@media(max-width:480px)")
    wide = media_block(css, "@media(min-width:1800px)")
    assert "max-width:1440px" in wide


def test_accessibility_and_motion_rules():
    css = read("app/web/app.css")
    assert ":where(button,a,input,select,textarea):focus-visible" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "@media(max-height:560px) and (orientation:landscape)" in css
    assert "env(safe-area-inset-bottom" in css
    assert "@media(max-width:1100px)" in css
    assert "@media(max-width:700px)" in css


def test_streamlit_theme_is_responsive_too():
    from app.ui.theme import CSS
    for header in ("@media(max-width:1024px)", "@media(max-width:768px)",
                   "@media(max-width:480px)", "@media(min-width:1800px)",
                   "@media(prefers-reduced-motion:reduce)"):
        assert header in CSS
    assert "min-height:44px!important" in CSS


def test_heatmap_is_scrollable_on_phones():
    assert 'class="heat-scroll"' in read("app/web/app.js")
    assert ".heat-scroll{overflow-x:auto" in read("app/web/app.css")


def test_stylesheet_has_balanced_braces():
    import re
    css = re.sub(r"/\*.*?\*/", "", read("app/web/app.css"), flags=re.S)
    assert css.count("{") == css.count("}")

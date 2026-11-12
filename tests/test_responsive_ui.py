"""Regression tests for the phone-first SPA and its navigation controls.

These are dependency-free static checks: they guard the CSS/HTML/JS contracts
that make the layout work from 320px phones to 1800px+ desktops, ensure the
menu button can never become a dead control again, and ensure no bottom tab
bar ever comes back.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
    assert '<span class="menu-label">Menu</span>' in html
    assert 'class="skip-link" href="#view"' in html


def test_all_layout_controls_exist():
    html = read("app/web/index.html")
    for marker in ('id="scrim"', 'data-action="close-drawers"',
                   'id="missionBtn"', 'aria-controls="mission"',
                   'data-action="close-nav"',
                   'data-action="close-mission"', 'id="missionPulse"',
                   'aria-label="New report"'):
        assert marker in html, f"missing {marker}"
    assert html.count('class="nav-item') == 5


def test_no_bottom_navigation_anywhere():
    """The user explicitly asked for the bottom buttons to be removed."""
    for rel in ("app/web/index.html", "app/web/app.css", "app/web/app.js"):
        text = read(rel)
        assert "tabbar" not in text.lower(), f"bottom bar returned in {rel}"
        assert "--tabbar-h" not in text, f"bottom bar offset returned in {rel}"
        assert "class=\"tabbar" not in text
    assert "bottom tab bar" not in read("app/web/app.css").lower()


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
                   ".nav-item[data-view]", "function decorateTables(",
                   "function watchMobileTables()", "MutationObserver",
                   "--heat-cols:", "Math.min(opts.labelWidth",
                   "const compact = W < 420"):
        assert marker in js, f"missing JS contract: {marker}"
    assert "$('.shell').classList.toggle('collapsed')" not in js  # old dead handler
    assert ".tabbar-item" not in js


def test_boot_initialises_layout_before_first_render():
    js = read("app/web/app.js")
    boot = js[js.index("(async function boot()"):]
    assert boot.index("initLayout()") < boot.index("await api('/api/bootstrap')")


def test_navigating_closes_mobile_drawers():
    js = read("app/web/app.js")
    fn = js[js.index("function navigate(view, id)"):]
    fn = fn[:fn.index("async function renderView()")]
    assert "closeDrawers()" in fn
    assert ".nav-item[data-view]" in fn
    assert ".tabbar-item" not in fn


# --------------------------------------------------------------------------- #
# CSS breakpoints
# --------------------------------------------------------------------------- #
def test_compact_drawer_rules():
    css = read("app/web/app.css")
    block = media_block(css, "@media(max-width:1100px)")
    for marker in ("grid-template-columns:minmax(0,1fr)",
                   ".menu-label{display:inline}", ".icon-btn.menu-btn{width:auto",
                   ".icon-btn{width:44px;height:44px;min-width:44px}",
                   "position:fixed", "translateX(-102%)", "translateX(102%)",
                   "body.nav-open .sidebar", "body.mission-open .mission",
                   "body.nav-open,body.mission-open{overflow:hidden}",
                   "env(safe-area-inset-bottom", "toast-stack",
                   ".nav-item{min-height:48px", "overscroll-behavior:contain",
                   ".shell.mission-hidden .mission{display:flex}"):
        assert marker in block, f"compact CSS missing {marker}"
    assert "tabbar" not in block.lower()


def test_phone_rules():
    css = read("app/web/app.css")
    block = media_block(css, "@media(max-width:700px)")
    for marker in (".mobile-brand{display:flex}", ".crumb{display:none}",
                   "#queryInput{font-size:16px}",
                   "font-size:16px;min-height:44px",
                   ".icon-btn{width:44px;height:44px;min-width:44px}",
                   ".icon-btn.menu-btn{width:auto;min-width:0;height:44px}",
                   ".icon-btn.menu-btn{padding:0 10px;gap:6px}",
                   ".btn,.btn-sm{min-height:44px", ".chip{min-height:44px",
                   ".composer-row{display:flex;flex-wrap:wrap",
                   ".g2,.g3,.g4,.g23,.g32{grid-template-columns:minmax(0,1fr)}",
                   ".tbl thead{display:none}",
                   '.tbl td::before{content:attr(data-label)',
                   ".tbl.no-head tbody tr{display:grid",
                   ".report-row{grid-template-columns:minmax(0,1fr)",
                   ".slot-grid{grid-template-columns:1fr}",
                   ".heat-grid{grid-template-columns:68px", "min-width:0",
                   ".footer{flex-direction:column",
                   "env(safe-area-inset-bottom"):
        assert marker in block, f"phone CSS missing {marker}"
    assert ".heat-grid{min-width:480px}" not in block   # no sideways scroll
    assert "var(--tabbar-h)" not in block


def test_tiny_phone_and_desktop_rules():
    css = read("app/web/app.css")
    tiny = media_block(css, "@media(max-width:380px)")
    assert ".mobile-brand{display:none}" in tiny
    assert ".composer-row .field{flex:1 1 100%}" in tiny
    assert ".menu-label{font-size:10px}" in tiny
    assert ".new-report-btn .btn-label" in media_block(css, "@media(max-width:480px)")
    wide = media_block(css, "@media(min-width:1800px)")
    assert "max-width:1440px" in wide
    landscape = media_block(css, "@media(max-height:560px) and (orientation:landscape)")
    assert "tabbar" not in landscape.lower()
    assert ".icon-btn{width:44px;height:44px;min-width:44px}" in landscape


def test_accessibility_and_motion_rules():
    css = read("app/web/app.css")
    assert ":where(button,a,input,select,textarea):focus-visible" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "@media(max-height:560px) and (orientation:landscape)" in css
    assert "env(safe-area-inset-bottom" in css
    assert "@media(max-width:1100px)" in css
    assert "@media(max-width:700px)" in css
    assert "scroll-padding-top" in css
    assert "touch-action:manipulation" in css
    assert ".skip-link:focus" in css


def test_streamlit_theme_is_responsive_too():
    from app.ui.theme import CSS
    for header in ("@media(max-width:1024px)", "@media(max-width:768px)",
                   "@media(max-width:480px)", "@media(max-width:380px)",
                   "@media(min-width:1800px)",
                   "@media(prefers-reduced-motion:reduce)"):
        assert header in CSS
    assert "min-height:44px!important" in CSS
    assert "font-size:16px!important" in CSS
    assert "88px" not in CSS              # old reserved bottom-bar space


def test_heatmap_fits_phone_width():
    js = read("app/web/app.js")
    css = read("app/web/app.css")
    assert 'class="heat-scroll"' in js
    assert "--heat-cols:${weeks.length}" in js
    assert "grid-template-columns:104px" not in js    # was hard-coded inline
    assert ".heat-scroll{overflow-x:auto" in css
    assert "grid-template-columns:104px repeat(var(--heat-cols" in css


def test_charts_adapt_to_narrow_containers():
    js = read("app/web/app.js")
    assert "Math.max(240, el.clientWidth || 400)" in js
    assert "Math.max(30, W * 0.12)" in js                 # line chart gutter
    assert "Math.max(52, W * 0.34)" in js                 # bar chart labels
    assert "const compact = W < 420" in js                # stacked phone bars
    assert "it.label.slice(0, maxChars - 1)" in js
    # Tooltip HTML must stay escaped: bindTooltips assigns innerHTML.
    assert 'data-tt="${esc(tt)}"' in js
    assert "const tt = esc(" in js
    assert "'<div class=\"chart-tooltip\" data-ttbox></div>'" in js
    assert "el.dataset.bound === '1'" in js   # no double-bound tap handlers


def test_docs_do_not_describe_a_bottom_bar():
    for rel in ("README.md", "docs/USER_GUIDE.md",
                "docs/TROUBLESHOOTING.md", "CHANGELOG.md"):
        text = read(rel).lower()
        assert "five-tab bottom bar" not in text, f"stale docs: {rel}"
        assert "bottom tab bar" not in text, f"stale docs: {rel}"


def test_stylesheet_has_balanced_braces():
    import re
    css = re.sub(r"/\*.*?\*/", "", read("app/web/app.css"), flags=re.S)
    assert css.count("{") == css.count("}")

# Fonts

Meridian loads its typography from CDN stylesheets with graceful local fallbacks,
so the product renders correctly even with no internet access:

| Role | Family | Source | Fallback |
|------|--------|--------|----------|
| Headings | **Satoshi Bold / Black** | https://api.fontshare.com/v2/css?f[]=satoshi@700,900,500&display=swap | Inter → system sans |
| Body | **Inter Regular / Medium** | https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700 | system sans |
| Data / numbers | **JetBrains Mono** | https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600 | Consolas / monospace |

## Fully offline typography (optional)

The binary `.woff2` files are intentionally not committed (they are licensed
assets and would bloat the repository). To self-host:

1. Download `Satoshi-Bold.woff2`, `Satoshi-Medium.woff2` from
   https://www.fontshare.com/fonts/satoshi and `Inter-Regular.woff2` /
   `JetBrainsMono-Regular.woff2` from https://fonts.google.com .
2. Place them in this folder.
3. Add to `app/web/app.css` (above all other rules):

```css
@font-face{font-family:'Satoshi';src:url('/static/fonts/Satoshi-Bold.woff2') format('woff2');
  font-weight:700 900;font-display:swap}
@font-face{font-family:'Inter';src:url('/static/fonts/Inter-Regular.woff2') format('woff2');
  font-weight:400 600;font-display:swap}
```

4. Copy the files into `app/web/fonts/` as well (the SPA's `/static` root is
   `app/web/`), or symlink `app/web/fonts -> ../assets/fonts`.

Font sizes follow a 4px grid: 10, 12, 14, 16, 20, 24, 28, 36, 40.

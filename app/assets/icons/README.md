# Icons

Meridian uses an inline Phosphor-style duotone SVG sprite defined at the top of
`app/web/index.html` (`<svg class="icon-sprite">` with `<symbol>` ids such as
`i-grid`, `i-key`, `i-chart`, `i-shield`). Inline sprites mean zero extra HTTP
requests, zero icon-font dependencies and perfect rendering offline.

Standalone SVG exports live in this folder for use in docs and presentations.
Add a new icon by appending a `<symbol id="i-name" viewBox="0 0 24 24">` to
the sprite and referencing it with `<svg><use href="#i-name"/></svg>`.

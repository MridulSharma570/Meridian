# Images

`meridian-logo.svg` — the official Meridian diamond mark: a gold diamond outline
with a nested inner diamond and a pearl "M" on Obsidian.

The SPA renders its logo as inline SVG in `app/web/index.html` (no external image
request) and ships `app/web/favicon.svg` for the browser tab. Decorative mesh
gradients, blurred blobs and organic shapes are pure CSS in `app/web/app.css` —
no raster assets are required, keeping the repository light and the UI crisp at
any pixel density.

Add screenshot PNGs to `docs/screenshots/` and update the placeholders in
`README.md` when preparing a submission or presentation.

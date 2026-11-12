# Meridian — User Guide

**Version 1.0.0 · Developed by Mridul Sharma**
*"Market Intelligence, Redefined."*

> **Screenshot descriptions** below describe exactly what you see on each
> screen (the app is dark-mode only: deep navy, gold accents, ivory type).

---

## 1. First launch

Open `http://localhost:8000`. On a fresh install the dashboard is honestly
empty and shows **API key required — answers are disabled**. Save a provider
key in Settings → API Keys before generating your first report.

**What you see on desktop:** a three-column layout. On the left, a collapsible
diamond-logo sidebar (Dashboard, Report History, Compare Mode, API Keys, User
Guide). In the centre, a large glass hero with the headline *"One query. The
entire market landscape."*, a wide gold-bordered query composer, region /
period / language dropdowns, a gold **Generate Intelligence** button and five
suggested queries. On the right, the **Agent Activity** mission-control panel
listing all seven agents with idle/working/done states. A small gold **Ask**
bubble sits at the bottom right.

**On tablets and phones (≤1100px):** the interface becomes a single, full-width
column with **no bottom bar**. A labelled **Menu** button at the top left opens
the navigation drawer; the Activity button opens the telemetry drawer. Both
slide in over a dimmed backdrop. Cards stack in one column, wide tables reflow
into labelled stacked rows, the heatmap shrinks to fit the screen, charts scale
their gutters to the available width, and the composer / exports / actions go
full-width. Every input is 16px (so iOS never zooms) and every touch target is
at least 44px. Nothing is clipped or hidden off-screen. See
[§11 Keyboard & micro-interactions](#11-keyboard--micro-interactions) for the
two top-left controls.

Four KPI cards sit below the hero: reports generated, average reliability,
sources analysed and agent executions.

---

## 2. Generate your first report

1. Type a question in the composer — a sector, a company, or a comparison:
   - `Indian electric vehicle market 2026`
   - `Global AI platforms competitive landscape`
   - `Tesla vs BYD`
2. Choose **Region** (Global, North America, Europe, Asia Pacific, India, LATAM,
   Middle East), **Period** (12M, 3Y, 5Y, 10Y) and **Language** (14 options).
3. Press **Generate Intelligence**.

**What you see:** the right-hand panel comes alive — each agent turns gold with
animated progress dots, then flips to a green check with its provider and
elapsed milliseconds. The progress bar climbs from 0 to 100%. When the
`job_complete` event arrives you are taken to the report automatically and a
toast confirms that PDF, PowerPoint and Excel are ready. A full report typically
finishes in **1–3 seconds**.

> An active provider API key is required first (Settings → API Keys). Without
> one, Generate is disabled and the API returns `409`; Meridian will not create
> a plausible report from templates.

---

## 3. The report screen

**What you see:** a gradient header with the company and sector, a row of badges
(region, period, data mode, reliability score, source count, timestamp), three
export buttons, an **Ask follow-up** button and a **Translate report** dropdown.
Below that, a filter bar (Region / Time period / Competitor focus) and six tabs.

### Tabs

| Tab | Contents |
|-----|----------|
| **Overview** | Four KPI cards, market trajectory area chart, market-share donut, revenue trend vs peer average, segment bars, sentiment heatmap, macro indicators, competitor table and SWOT snapshot. Hover any chart for exact values; click legend items to toggle series. |
| **Full Report** | Table of contents plus the complete 10-section markdown report: Executive Summary, Market Overview & sizing, Competitive Landscape, Trend Analysis, SWOT, PESTLE, Porter's Five Forces, Recommendations, Risks & Assumptions, Sources. |
| **Forecast** | Three scenario cards (base 60%, optimistic 20%, pessimistic 20%), a 12-month line chart with a shaded confidence band, and a month-by-month table with confidence percentages. |
| **Verification** | Per-section reliability scores with progress bars, then every major claim with status (verified / partially verified / ⚠️ unverified), score, source refs and a note. |
| **Sources** | The full source appendix with reliability scores and links, plus the collected news headlines with sentiment. |
| **Agent Logs** | Execution telemetry per agent: provider, status, milliseconds, token counts and warnings, plus three resilience cards. |

**Filters:** competitor focus can be changed from the collected dataset.
Region/period stay tied to the report's verified scope — generate a new report
for a different region or period rather than recomputing invented figures.

---

## 4. Follow-up chat (Agent 4)

Click the gold **Ask** bubble or **Ask follow-up**. A dock slides up with
suggested questions such as *"What about the rural market?"*, *"Compare the top
two competitors in more detail"*, *"What are the biggest risks to the forecast?"*
and *"Which sources support the market size estimate?"*.

Answers are generated by the configured LLM from the report context and real
source ids such as `[L01]`. If no provider is available, chat returns an error
instead of a canned answer. The conversation is saved to `chat_history` and
reappears when you reopen the dock.

---

## 5. Translation

In the report header, pick a language (Hindi, Spanish, French, German,
Japanese, Chinese, Arabic, Portuguese, Korean, Russian, Italian, Bengali,
Punjabi) and click the globe button.

With a Translator-slot LLM key you get a full neural translation that preserves
markdown, tables, numbers and `[S01]` references. Without a key, Meridian
applies a **structural translation**: a fully localised executive summary plus
a curated lexicon for every heading and label. The result is clearly labelled —
it never pretends to be a full human translation. Translations are cached.

---

## 6. Exports

| Button | What you get |
|--------|--------------|
| **PDF Report** | Paginanted board document: cover KPI table, executive summary, native vector charts, sizing, competitive, SWOT/PESTLE/Porter tables, 12-month forecast, fact-check, recommendations and a source appendix. Gold/navy header and footer on every page. |
| **PowerPoint** | 8 slides: cover, executive summary with KPIs, market trajectory chart, competitive donut + table, SWOT quadrants, forecast chart + scenarios, verification scorecard, recommendations. |
| **Excel** | 10 sheets (Summary, Market History, Competitors, Forecast, SWOT, PESTLE, Porter, Sentiment, Fact Check, Sources, Raw Data) with editable native line/pie/bar charts. |

All three are generated at report completion and regenerated on demand if a
file is missing.

---

## 7. Compare mode

Open **Compare Mode** in the sidebar.

- **Company vs company:** enter two names, choose a region, press **Run
  comparison**. You get a five-dimension scorecard (market share, revenue,
  growth, sentiment, source reliability) with gold/sapphire bars, a side-by-side
  trajectory chart and a written verdict.
- **Report vs report:** go to **Report History**, tick exactly two rows and press
  **Compare selected**. You see both executive summaries, market sizes, CAGRs
  and reliability scores side by side.

---

## 8. Report history

**What you see:** a search box, status and region filters, and a table with
checkboxes. Open any report with **Open**, delete with the trash icon, or tick
two rows to compare. Every report keeps its full agent outputs, sources and
export paths.

---

## 9. API Keys — the part that was missing

Open **API Keys** in the sidebar.

**What you see:** an encryption notice strip, a **Quick setup** card, seven
independent agent cards (Researcher, Analyst, Writer, Chat, Forecast,
Fact-Checker, optional Translator), a language list and the full provider
catalogue.

A new card above the slots — **Auto-select the best available free model** —
shows OpenRouter's live free ranking, the recommended model, the catalogue
state (`LIVE`, `CACHED` or `OFFLINE FALLBACK`) and a **Refresh** button. It is
read-only information and costs nothing to open.

For each slot:
1. Pick a **provider** from the FREE or PAID group (16 options).
2. Pick a **model** (auto-populated for that provider). For
   **OpenRouter (Free)** the default is **Auto — best free model (live)**:
   Meridian reads OpenRouter's public free-model catalogue, ranks the currently
   available explicit `:free` chat models and sends an all-free fallback chain. If a
   free model is retired or rate-limited, the next free model is tried
   automatically and the failed one is cooled down. No paid model is ever
   selected; $0 previews without `:free` are excluded because they can require
   a funded account. The alternative **OpenRouter free router (random)** lets
   OpenRouter pick any free model at random. You can still pin a specific
   `…:free` slug for reproducible output. If a test returns HTTP 402, check
   the OpenRouter key's account and per-key credit limit; the slot remains
   marked **SAVED · TEST FAILED** until a test succeeds.
3. Paste the key into the password field (eye icon shows/hides it).
4. Press **Save key** → it is Fernet-encrypted and stored; the card shows a
   masked value like `gsk_T••••••••7890`.
5. Press **Test connection** → a real minimal request reports the provider,
   latency, the model that actually answered and quota headers, or a clear
   error. On an auto slot the reported model may change between tests as the
   free catalogue rotates.
6. **Remove** deletes the key; if it was the last active provider, answers are
   disabled immediately.

**Quick setup** applies one key to all seven slots — perfect when you have a
single Groq, Gemini or OpenAI key. Mixing providers is equally supported.

Keys are never shown in plaintext again, never logged, never exported and never
sent to the browser. See [API_KEYS_SETUP.md](API_KEYS_SETUP.md) for how to get
each key.

---

## 10. Understanding data modes

| Badge | Meaning |
|-------|---------|
| `VERIFIED` | At least one live source was retrieved and cited; unsupported series are placeholders |
| `UNVERIFIED` | No live source was available; a report is refused in production mode |
| `SAMPLE` | Explicit offline sample mode only; deterministic demo data, not research |

The exact connector status is in `dataset.connectors`, the report's
*Risks & Assumptions* section, the Sources tab and the Agent Logs tab.
Unsupported claims stay at reliability 0 and are flagged ⚠️ by the
Fact-Checker. Keep live connectors enabled and provider keys configured for
verified answers.

---

## 11. Keyboard & micro-interactions

- `Enter` inside the chat input sends the question.
- **Menu button (top-left, ≡)** — on desktop it collapses the sidebar to a
  72px icon-only rail; press again to expand. The choice is remembered in
  `localStorage`. On tablets/phones it opens the full navigation drawer; press
  again, tap the dimmed backdrop, press `Escape`, use the ✕ button, or simply
  pick a page to close it. A gold dot on the button marks an open drawer.
- **Activity button (top-right, pulse icon)** — on desktop it hides/shows the
  Agent Activity panel to give charts more room (also remembered). On
  tablets/phones it slides the Agent Activity drawer in from the right. A small
  gold pulse on the button means a report is currently running.
- **No bottom bar on phones/tablets** — all five destinations (Dashboard,
  Report History, Compare Mode, API Keys, User Guide) live in the navigation
  drawer, and the active one is highlighted there. The full screen stays
  available for content and the footer.
- `Tab` stays inside an open drawer; `Escape` closes it and returns focus to
  the button that opened it.
- Hover (or tap on a phone) any chart for a tooltip; click a legend item to
  hide/show a series. Bar charts put the label above the bar on narrow screens.
- Heatmap cells scale up on hover with their exact score; on phones the label
  column narrows and the cells shrink to fit the viewport (no sideways scroll).
- Cards fade/slide in on view change; buttons lift slightly on hover.
- All layouts respect `prefers-reduced-motion` and iOS safe-area insets.

---

*Developed by Mridul Sharma · Meridian v1.0.0*

# Meridian — User Guide

**Version 1.0.0 · Developed by Mridul Sharma**
*"Market Intelligence, Redefined."*

> **Screenshot descriptions** below describe exactly what you see on each
> screen (the app is dark-mode only: deep navy, gold accents, ivory type).

---

## 1. First launch

Open `http://localhost:8000`. On a fresh install Meridian seeds one complete
demo report, so nothing is empty.

**What you see on desktop:** a three-column layout. On the left, a collapsible
diamond-logo sidebar (Dashboard, Report History, Compare Mode, API Keys, User
Guide). In the centre, a large glass hero with the headline *"One query. The
entire market landscape."*, a wide gold-bordered query composer, region /
period / language dropdowns, a gold **Generate Intelligence** button and five
suggested queries. On the right, the **Agent Activity** mission-control panel
listing all seven agents with idle/working/done states. A small gold **Ask**
bubble sits at the bottom right.

**On tablets and phones (≤1100px):** the interface becomes a single, full-width
column with a five-tab bar along the bottom (Home, History, Compare, Keys,
Guide). The left sidebar and the Agent Activity panel slide in as drawers over a
dimmed backdrop. Cards stack, KPIs stay two-up, the query composer and export
buttons become full-width, charts and wide tables scroll horizontally, and all
touch targets are at least 40px. Nothing is clipped or hidden off-screen. See
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

> No API keys are needed. Meridian runs its local analytical engine and labels
> the figures as `simulated` so you always know their provenance.

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

**Filters:** change region, period or competitor focus and press **Apply
filters**. Every chart recomputes immediately from the deterministic engine,
while the written report stays tied to its original scope.

---

## 4. Follow-up chat (Agent 4)

Click the gold **Ask** bubble or **Ask follow-up**. A dock slides up with
suggested questions such as *"What about the rural market?"*, *"Compare the top
two competitors in more detail"*, *"What are the biggest risks to the forecast?"*
and *"Which sources support the market size estimate?"*.

Answers are grounded in the report's dataset and include reference ids like
`[S01]`. If you configured a Chat-slot key, the answer is polished by the LLM;
otherwise the local engine answers. The conversation is saved to
`chat_history` and reappears when you reopen the dock.

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

For each slot:
1. Pick a **provider** from the FREE or PAID group (16 options).
2. Pick a **model** (auto-populated for that provider).
3. Paste the key into the password field (eye icon shows/hides it).
4. Press **Save key** → it is Fernet-encrypted and stored; the card shows a
   masked value like `gsk_T••••••••7890`.
5. Press **Test connection** → a real minimal request reports the provider,
   latency and quota headers, or a clear error.
6. **Remove** deletes the key; the local engine takes over instantly.

**Quick setup** applies one key to all seven slots — perfect when you have a
single Groq, Gemini or OpenAI key. Mixing providers is equally supported.

Keys are never shown in plaintext again, never logged, never exported and never
sent to the browser. See [API_KEYS_SETUP.md](API_KEYS_SETUP.md) for how to get
each key.

---

## 10. Understanding data modes

| Badge | Meaning |
|-------|---------|
| `LIVE` | 3+ external connectors succeeded; figures came from real feeds |
| `HYBRID` | 1–2 connectors succeeded; the rest came from the local engine |
| `SIMULATED` | No live feed; deterministic query-aware model estimates |

The exact connector status is in `dataset.connectors`, the report's
*Risks & Assumptions* section, the Sources tab and the Agent Logs tab.
Modelled claims are flagged ⚠️ by the Fact-Checker. Set `TAVILY_API_KEY`,
`NEWS_API_KEY` and provider keys to upgrade to verified data.

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
- **Bottom tab bar** (tablets/phones) switches views without opening the drawer;
  its active tab always matches the current page.
- `Tab` stays inside an open drawer; `Escape` closes it and returns focus to
  the button that opened it.
- Hover any chart for a tooltip; click a legend item to hide/show a series.
- Heatmap cells scale up on hover with their exact score; on phones the heatmap
  scrolls horizontally instead of shrinking into illegibility.
- Cards fade/slide in on view change; buttons lift slightly on hover.
- All layouts respect `prefers-reduced-motion` and iOS safe-area insets.

---

*Developed by Mridul Sharma · Meridian v1.0.0*

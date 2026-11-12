/* ==========================================================================
   MERIDIAN SPA — premium dashboard client
   No framework, no build step, no external JS dependencies.
   All charts are hand-built interactive SVG (hover tooltips + live filters).
   ========================================================================== */
(() => {
'use strict';

const S = {
  view: 'dashboard', reportId: null,
  boot: null, settings: null, stats: null, reports: [], dashboard: null,
  agents: {}, jobStatus: 'idle', progress: 0, eventSource: null,
  filters: { region: '', period: '', competitor: '' },
  tab: 'overview', compare: null, chatReport: null,
  chartFns: new Map(),
};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (n, c = '') => `<svg class="${c}"><use href="#i-${n}"/></svg>`;
const fmt = (n, d = 1) => Number(n || 0).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
const fmtInt = (n) => Number(n || 0).toLocaleString('en-US');
const shortDate = (s) => s ? String(s).replace('T', ' ').slice(0, 16) : '—';
const PALETTE = ['#C9A84C', '#4C7BF3', '#8B7CF6', '#059669', '#E8CE8A', '#E11D48', '#38BDF8', '#F59E0B'];

/* ---------------------------------------------------------------- API --- */
async function api(path, opts = {}) {
  const init = {method: opts.method || 'GET', headers: {'Content-Type': 'application/json'}};
  if (opts.body) init.body = JSON.stringify(opts.body);
  let res;
  try { res = await fetch(path, init); }
  catch (e) { throw new Error('Cannot reach the Meridian engine. Check that the server is running.'); }
  const ct = res.headers.get('content-type') || '';
  const data = ct.includes('json') ? await res.json().catch(() => ({})) : await res.text();
  if (!res.ok) throw new Error((data && (data.detail || data.error)) || `Request failed (${res.status})`);
  return data;
}
function toast(msg, kind = 'info', ms = 4200) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<span>${kind === 'ok' ? '✓' : kind === 'err' ? '!' : '◆'}</span><div>${esc(msg)}</div>`;
  $('#toasts').append(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(20px)'; setTimeout(() => el.remove(), 300); }, ms);
}
const kpi = (label, value, delta, ico, mono = false) => `
  <div class="card kpi"><div class="kpi-foot"></div>
    <div class="kpi-top"><span class="kpi-label">${esc(label)}</span>
      <span class="kpi-ico">${icon(ico)}</span></div>
    <div class="kpi-val ${mono ? 'mono' : ''}">${value}</div>
    <div class="kpi-delta">${delta}</div></div>`;
const card = (title, sub, body, extra = '') => `
  <section class="card"><div class="card-head"><div><h3>${title}</h3>${sub ? `<p>${sub}</p>` : ''}</div>${extra}</div>${body}</section>`;
const sectionTitle = (t, tail = '') => `<div class="section-title"><h2>${t}</h2><div class="rule"></div>${tail}</div>`;

/* ------------------------------------------------------------ Markdown --- */
function mdInline(t) {
  return t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.+?)\*/g, '<em>$1</em>')
          .replace(/`(.+?)`/g, '<code>$1</code>')
          .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
                   '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function mdToHtml(src) {
  const lines = esc(src || '').split('\n');
  let out = '', inList = false, inTable = false, para = [];
  const flushPara = () => { if (para.length) { out += `<p>${mdInline(para.join(' '))}</p>`; para = []; } };
  const closeList = () => { if (inList) { out += '</ul>'; inList = false; } };
  const closeTable = () => { if (inTable) { out += '</tbody></table>'; inTable = false; } };
  for (let i = 0; i < lines.length; i++) {
    const L = lines[i].trim();
    if (/^\|/.test(L) && /\|$/.test(L)) {
      const cells = L.slice(1, -1).split('|').map(x => x.trim());
      if (cells.every(c => /^:?-{2,}:?$/.test(c))) continue;
      flushPara(); closeList();
      if (!inTable) { out += '<table><thead><tr>' + cells.map(c => `<th>${mdInline(c)}</th>`).join('') + '</tr></thead><tbody>'; inTable = true; }
      else out += '<tr>' + cells.map(c => `<td>${mdInline(c)}</td>`).join('') + '</tr>';
      continue;
    }
    closeTable();
    if (!L) { flushPara(); closeList(); continue; }
    if (/^#{1,4}\s/.test(L)) { flushPara(); closeList();
      const n = L.match(/^#+/)[0].length;
      out += `<h${Math.min(n, 3)}>${mdInline(L.replace(/^#+\s*/, ''))}</h${Math.min(n, 3)}>`; continue; }
    if (/^>\s?/.test(L)) { flushPara(); closeList(); out += `<blockquote>${mdInline(L.replace(/^>\s?/, ''))}</blockquote>`; continue; }
    if (/^(---|\*\*\*)$/.test(L)) { flushPara(); closeList(); out += '<hr>'; continue; }
    if (/^([-*]|\d+\.)\s+/.test(L)) {
      flushPara(); if (!inList) { out += '<ul>'; inList = true; }
      out += `<li>${mdInline(L.replace(/^([-*]|\d+\.)\s+/, ''))}</li>`; continue;
    }
    para.push(L);
  }
  flushPara(); closeList(); closeTable();
  return out;
}

/* --------------------------------------------------------- SVG charts --- */
function registerChart(id, fn) { S.chartFns.set(id, fn); }
function renderCharts() {
  S.chartFns.forEach((fn, id) => {
    const el = document.getElementById(id);
    if (!el) { S.chartFns.delete(id); return; }
    const W = Math.max(280, el.clientWidth || 400), H = el.clientHeight || 240;
    try { el.innerHTML = fn(W, H) + '<div class="chart-tooltip" data-ttbox></div>'; }
    catch (e) { el.innerHTML = `<div class="empty tiny">Chart unavailable: ${esc(e.message)}</div>`; }
  });
  bindTooltips();
  $$('.legend span[data-toggle]').forEach(el => {
    if (el.dataset.bound === '1') return;   // renderCharts may run twice per view
    el.dataset.bound = '1';
    el.addEventListener('click', () => {
    const idx = +el.dataset.toggle;
    const svg = el.closest('.card')?.querySelector('.chart-box svg');
    const g = svg?.querySelector(`[data-series="${idx}"]`);
    if (g) { const hidden = g.style.display === 'none'; g.style.display = hidden ? '' : 'none';
             el.style.opacity = hidden ? '1' : '.4'; }
  });
  });
}
function bindTooltips() {
  $$('[data-tt]').forEach(el => {
    const box = el.closest('.chart-box, .heat-wrap')?.querySelector('[data-ttbox]');
    if (!box) return;
    const show = () => {
      box.innerHTML = el.dataset.tt; box.classList.add('show');
      const host = box.parentElement.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      box.style.left = `${Math.min(host.width - 20, Math.max(20, r.left - host.left + r.width / 2))}px`;
      box.style.top = `${Math.max(28, r.top - host.top)}px`;
    };
    el.addEventListener('mouseenter', show);
    el.addEventListener('mousemove', show);
    el.addEventListener('mouseleave', () => box.classList.remove('show'));
  });
}
function defs() {
  return `<defs>
    <linearGradient id="goldFade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C9A84C" stop-opacity=".34"/><stop offset="1" stop-color="#C9A84C" stop-opacity="0"/></linearGradient>
    <linearGradient id="goldStroke" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8C7231"/><stop offset=".5" stop-color="#E8CE8A"/><stop offset="1" stop-color="#C9A84C"/></linearGradient>
  </defs>`;
}
function lineChart(cfg) {
  return (W, H) => {
    const P = {l: 44, r: 14, t: 14, b: 26};
    const w = W - P.l - P.r, h = H - P.t - P.b;
    const labels = cfg.labels || [], sets = cfg.series || [];
    const all = sets.flatMap(s => s.values);
    const min = cfg.min !== undefined ? cfg.min : Math.min(...all, 0);
    const max = Math.max(...all, 1) * 1.12;
    const x = i => P.l + (labels.length <= 1 ? w / 2 : (i / (labels.length - 1)) * w);
    const y = v => P.t + h - ((v - min) / (max - min || 1)) * h;
    let g = defs();
    for (let k = 0; k <= 4; k++) {
      const yy = P.t + (k / 4) * h, val = max - (k / 4) * (max - min);
      g += `<line class="gridline" x1="${P.l}" y1="${yy}" x2="${W - P.r}" y2="${yy}"/>`;
      g += `<text class="lbl" x="${P.l - 7}" y="${yy + 3}" text-anchor="end">${cfg.fmtY ? cfg.fmtY(val) : fmt(val, 0)}</text>`;
    }
    labels.forEach((l, i) => {
      if (labels.length > 9 && i % Math.ceil(labels.length / 7) !== 0 && i !== labels.length - 1) return;
      g += `<text class="lbl" x="${x(i)}" y="${H - 7}" text-anchor="middle">${esc(l)}</text>`;
    });
    if (cfg.band) {
      const up = cfg.band.upper.map((v, i) => `${x(i)},${y(v)}`).join(' ');
      const dn = cfg.band.lower.map((v, i) => `${x(i)},${y(v)}`).reverse().join(' ');
      g += `<polygon points="${up} ${dn}" fill="rgba(139,124,246,.16)" stroke="none"/>`;
    }
    sets.forEach((s, si) => {
      const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
      const col = s.color || PALETTE[si];
      if (s.area && si === 0) g += `<polygon class="area" points="${P.l},${P.t + h} ${pts} ${W - P.r},${P.t + h}" fill="url(#goldFade)"/>`;
      g += `<g data-series="${si}"><polyline class="line" points="${pts}" stroke="${col}" ${s.dash ? 'stroke-dasharray="5 5"' : ''}/>`;
      s.values.forEach((v, i) => {
        if (s.dots !== false) g += `<circle cx="${x(i)}" cy="${y(v)}" r="2.6" fill="${col}" stroke="#0A1628" stroke-width="1.2"/>`;
      });
      g += '</g>';
    });
    labels.forEach((l, i) => {
      const half = w / Math.max(1, labels.length - 1) / 2;
      const tt = `<b>${esc(l)}</b><br>` + sets.map(s =>
        `${esc(s.name)}: <b>${fmt(s.values[i], cfg.decimals ?? 1)}</b>${cfg.unit || ''}`).join('<br>');
      g += `<rect class="hit" x="${x(i) - half}" y="${P.t}" width="${half * 2}" height="${h}" data-tt="${esc(tt)}"/>`;
    });
    g += `<line class="axis" x1="${P.l}" y1="${P.t + h}" x2="${W - P.r}" y2="${P.t + h}"/>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%">${g}</svg>`;
  };
}
function donutChart(items) {
  return (W, H) => {
    const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 16, r = R * 0.61;
    const total = items.reduce((a, b) => a + (b.value || 0), 0) || 1;
    let ang = -Math.PI / 2, g = defs();
    items.forEach((it, i) => {
      const a2 = ang + (it.value / total) * Math.PI * 2;
      const large = a2 - ang > Math.PI ? 1 : 0;
      const p = (rad, a) => `${(cx + rad * Math.cos(a)).toFixed(2)},${(cy + rad * Math.sin(a)).toFixed(2)}`;
      const d = `M ${p(R, ang)} A ${R} ${R} 0 ${large} 1 ${p(R, a2)} L ${p(r, a2)} A ${r} ${r} 0 ${large} 0 ${p(r, ang)} Z`;
      const color = it.color || PALETTE[i % PALETTE.length];
      g += `<path d="${d}" fill="${color}" stroke="#0A1628" stroke-width="2" data-tt="${esc(`<b>${esc(it.label)}</b><br>${fmt(it.value, 1)}% share`)}"/>`;
      ang = a2;
    });
    g += `<text x="${cx}" y="${cy - 4}" text-anchor="middle" fill="#EDE4D3" font-family="Satoshi,Arial" font-weight="900" font-size="22">${items.length}</text>`;
    g += `<text x="${cx}" y="${cy + 14}" text-anchor="middle" fill="#94A3B8" font-size="9" font-family="Inter,Arial" letter-spacing="1.4">TRACKED PLAYERS</text>`;
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%">${g}</svg>`;
  };
}
function barChart(items, opts = {}) {
  return (W, H) => {
    const P = {l: opts.labelWidth || 96, r: 44, t: 10, b: 8};
    const rowH = (H - P.t - P.b) / Math.max(1, items.length);
    const max = Math.max(...items.map(i => i.value), 1);
    let g = defs();
    items.forEach((it, i) => {
      const y = P.t + i * rowH + rowH * .16, bh = rowH * .6;
      const bw = ((W - P.l - P.r) * it.value) / max;
      g += `<text class="lbl-b" x="${P.l - 10}" y="${y + bh / 2 + 3}" text-anchor="end">${esc(it.label)}</text>`;
      g += `<rect x="${P.l}" y="${y}" width="${W - P.l - P.r}" height="${bh}" rx="4" fill="rgba(255,255,255,.045)"/>`;
      g += `<rect class="bar" x="${P.l}" y="${y}" width="${Math.max(2, bw)}" height="${bh}" rx="4" fill="${it.color || PALETTE[i % PALETTE.length]}" data-tt="${esc(`<b>${esc(it.label)}</b><br>${fmt(it.value, 1)}${opts.unit || ''}`)}"/>`;
      g += `<text class="lbl" x="${P.l + bw + 7}" y="${y + bh / 2 + 3}">${fmt(it.value, opts.decimals ?? 1)}${opts.unit || ''}</text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%">${g}</svg>`;
  };
}
function heatmapHtml(data, weeks, channels) {
  const colr = v => {
    if (v < .35) return 'rgba(225,29,72,.75)';
    if (v < .5) return 'rgba(245,158,11,.6)';
    if (v < .65) return 'rgba(201,168,76,.6)';
    return `rgba(5,150,105,${.35 + v * .5})`;
  };
  let html = `<div class="heat-grid" style="grid-template-columns:104px repeat(${weeks.length},1fr);position:relative">`;
  html += `<div></div>` + weeks.map(w => `<div class="heat-lbl" style="text-align:center">${esc(w)}</div>`).join('');
  channels.forEach((ch, r) => {
    html += `<div class="heat-lbl">${esc(ch)}</div>`;
    (data[r] || []).forEach((v, c) => {
      html += `<div class="heat-cell" style="background:${colr(v)}" data-tt="${esc(`<b>${esc(ch)} · ${esc(weeks[c])}</b><br>Sentiment: ${Math.round(v * 100)}/100`)}"></div>`;
    });
  });
  html += '</div>';
  return html;
}
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderCharts, 160); });

/* ------------------------------------------------------ Mission control --- */
function renderMission() {
  const order = ['researcher','analyst','writer','forecast','factchecker','chat','translator'];
  const meta = {researcher:['🔍','Researcher'], analyst:['📊','Analyst'], writer:['✍️','Writer'],
    forecast:['📈','Forecast Agent'], factchecker:['✅','Fact-Checker'],
    chat:['💬','Chat Agent'], translator:['🌐','Translator']};
  const live = S.jobStatus === 'running';
  $('#missionStatus').textContent = live ? 'RUNNING' : 'IDLE';
  $('#missionStatus').classList.toggle('live', live);
  const pct = S.progress || 0;
  let html = `<div class="progress-track"><i style="width:${pct}%"></i></div>
    <div class="tiny muted" style="margin-bottom:14px">Pipeline ${pct}% · ${live ? 'agents executing' : 'standing by'}</div>`;
  order.forEach(k => {
    const a = S.agents[k] || {}, st = a.status || 'idle';
    const state = st === 'working' ? 'WORKING <span class="dots"><i></i><i></i><i></i></span>'
      : st === 'done' ? '✓ DONE' : 'IDLE';
    const sub = st === 'done' ? `${a.provider || 'Local engine'} · ${a.elapsed_ms || 0} ms`
      : st === 'working' ? 'Executing specialised task…' : 'Awaiting next report';
    html += `<div class="agent-row ${st}"><div class="agent-ico">${meta[k][0]}</div>
      <div class="agent-txt"><b>${meta[k][1]}</b><small>${esc(sub)}</small></div>
      <div class="agent-state">${state}</div></div>`;
  });
  $('#missionBody').innerHTML = html;
  $('#missionKeys').textContent = `${S.settings?.configured_count || 0} / 7`;
  $('#missionDataMode').textContent = S.dashboard?.dataset?.data_mode || (S.boot?.demo_mode ? 'simulated' : '—');
}
function connectEvents(id) {
  if (S.eventSource) { S.eventSource.close(); S.eventSource = null; }
  try {
    S.eventSource = new EventSource(`/api/reports/${id}/events`);
    S.eventSource.onmessage = (ev) => {
      let e; try { e = JSON.parse(ev.data); } catch { return; }
      if (e.type === 'agent_start') { S.agents[e.agent] = {status:'working'}; S.jobStatus = 'running'; }
      else if (e.type === 'agent_done') S.agents[e.agent] = {status:'done', provider:e.provider, elapsed_ms:e.elapsed_ms};
      else if (e.type === 'progress') S.progress = e.percent;
      else if (e.type === 'warning' || e.type === 'agent_warning') toast(e.message || 'An agent recovered from a provider issue', 'info');
      else if (e.type === 'job_complete') {
        S.jobStatus = 'done'; S.progress = 100; renderMission();
        toast('Report complete — PDF, PowerPoint and Excel are ready', 'ok');
        S.eventSource?.close(); S.eventSource = null;
        if (S.view === 'dashboard' || S.view === 'history') navigate('report', id);
        else if (S.view === 'report' && S.reportId === id) loadReport(id);
        refreshChrome(); return;
      } else if (e.type === 'job_failed') {
        S.jobStatus = 'failed'; renderMission();
        toast(`Report failed: ${e.error}`, 'err', 8000);
        S.eventSource?.close(); return;
      }
      renderMission();
    };
    S.eventSource.onerror = () => { S.eventSource?.close(); S.eventSource = null; };
  } catch (e) { /* SSE unsupported: status polling still works */ }
}

/* ------------------------------------------------------------- Views --- */
async function renderDashboard() {
  const reports = S.reports.slice(0, 5);
  const stats = S.stats || {};
  const ds = S.dashboard?.dataset;
  const suggestions = ['Indian electric vehicle market 2026', 'Global AI platforms competitive landscape',
    'Fintech payments in India', 'Semiconductor supply chain outlook', 'Renewable energy in Europe'];
  let html = `
  <div class="hero">
    <div class="hero-eyebrow">Multi-agent market intelligence</div>
    <h1>One query.<br><span>The entire market landscape.</span></h1>
    <p class="hero-sub">Six autonomous AI agents and a translator work in concert to research, analyse,
       write, forecast and fact-check a board-ready report — with live charts and instant exports.</p>
    <div class="composer">
      <div class="composer-main">${icon('search', 'search-ico')}
        <input id="queryInput" type="text" maxlength="600" placeholder="e.g. Indian electric vehicle market 2026 — Tesla vs BYD" />
      </div>
      <div class="composer-row">
        <div class="field"><label>Region</label><select id="regionSel">${(S.settings?.regions || ['Global']).map(r => `<option>${esc(r)}</option>`).join('')}</select></div>
        <div class="field"><label>Period</label><select id="periodSel">${(S.settings?.periods || ['3Y']).map(p => `<option ${p === '3Y' ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></div>
        <div class="field"><label>Language</label><select id="langSel">${(S.settings?.languages || [{code:'en',native:'English'}]).map(l => `<option value="${l.code}" ${l.code === 'en' ? 'selected' : ''}>${esc(l.native)}</option>`).join('')}</select></div>
        <button class="btn btn-gold" data-action="generate">${icon('spark')} Generate Intelligence</button>
      </div>
    </div>
    <div class="chips">${suggestions.map(s => `<button class="chip" data-action="suggest" data-q="${esc(s)}">${esc(s)}</button>`).join('')}</div>
  </div>
  <div class="grid g4" style="margin-bottom:8px">
    ${kpi('Reports generated', `<span class="mono">${fmtInt(stats.total_reports || 0)}</span>`, `${fmtInt(stats.completed || 0)} completed successfully`, 'file', true)}
    ${kpi('Avg. reliability', `<span class="mono">${fmt(stats.avg_reliability || 0, 0)}<small style="font-size:14px;color:var(--slate)">/100</small></span>`, 'Claim-level verification', 'shield', true)}
    ${kpi('Sources analysed', `<span class="mono">${fmtInt(stats.sources_analyzed || 0)}</span>`, 'Across all saved reports', 'book', true)}
    ${kpi('Agent executions', `<span class="mono">${fmtInt(stats.agents_run || 0)}</span>`, `${stats.active_keys || 0} provider keys configured`, 'grid', true)}
  </div>
  ${sectionTitle('Intelligence at a glance', `<button class="btn btn-ghost btn-sm" data-action="nav" data-view="history">View all ${icon('arrow')}</button>`)}
  <div class="grid g23" style="margin-bottom:8px">
    ${card('Market trajectory', 'Historic market size · USD billions',
      `<div class="chart-box tall" id="dashHistory"></div>` +
      `<div class="legend"><span><i style="background:var(--gold)"></i> Market size</span>
       <span class="muted">${ds ? esc(ds.sector) + ' · ' + esc(ds.region) : 'Generate a report to populate'}</span></div>`)}
    ${card('Competitive share', 'Estimated market share by player',
      `<div class="chart-box tall" id="dashShare"></div><div class="legend" id="dashShareLegend"></div>`)}
  </div>
  <div class="grid g23" style="margin-bottom:8px">
    ${card('Recent reports', 'Search, reopen, export or compare',
      reports.length ? reports.map(r => reportRow(r)).join('') :
      `<div class="empty">${icon('file')}<h3>No reports yet</h3><p class="small">Use the composer above — your first report takes seconds.</p></div>`,
      `<button class="btn btn-ghost btn-sm" data-action="nav" data-view="history">${icon('clock')} History</button>`)}
    ${card('How Meridian works', 'A seven-stage autonomous pipeline', `
      <div class="grid" style="gap:14px">
        ${[['01','Researcher','Collects live web, financial, news, macro and social signals'],
           ['02','Analyst','SWOT · PESTLE · Porter · sizing · trend detection'],
           ['03–05','Writer / Forecast / Fact-Check','Report, 12-month confidence bands and claim verification'],
           ['06–07','Chat / Translator','Grounded follow-ups and 14-language localisation']]
          .map(x => `<div class="how-step"><span class="how-num">${x[0]}</span><div><b style="color:var(--ivory)">${x[1]}</b><div class="small muted">${x[2]}</div></div></div>`).join('')}
      </div>`)}
  </div>
  ${sectionTitle('Export-ready deliverables')}
  <div class="grid g3">
    ${card('PDF Report', 'Charts, tables and citations',
      `<p class="small muted" style="margin:0">A styled, paginated board document with native vector charts, a reliability section and a full source appendix.</p>`,
      `<span class="badge gold">ReportLab</span>`)}
    ${card('PowerPoint Deck', 'Eight presentation slides',
      `<p class="small muted" style="margin:0">Cover, KPIs, trajectory, competitive landscape, SWOT, forecast, verification and recommendations.</p>`,
      `<span class="badge gold">python-pptx</span>`)}
    ${card('Excel Workbook', 'Ten sheets + live charts',
      `<p class="small muted" style="margin:0">Raw data, forecast, frameworks, sentiment, sources and editable native charts for your own models.</p>`,
      `<span class="badge gold">openpyxl</span>`)}
  </div>`;
  $('#view').innerHTML = html;
  if (ds) {
    registerChart('dashHistory', lineChart({labels: ds.history.map(h => String(h.year)),
      series: [{name:'Market size', values: ds.history.map(h => h.value), color:'#C9A84C', area:true}],
      unit:'B', decimals:1, fmtY: v => fmt(v, 0)}));
    registerChart('dashShare', donutChart(ds.competitors.map((c, i) => ({label:c.name, value:c.share, color:PALETTE[i % PALETTE.length]}))));
    $('#dashShareLegend').innerHTML = ds.competitors.slice(0, 6).map((c, i) =>
      `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${esc(c.name)} · ${fmt(c.share, 1)}%</span>`).join('');
  } else {
    registerChart('dashHistory', lineChart({labels:['2021','2022','2023','2024','2025'],
      series:[{name:'Market size', values:[62,74,89,104,126], color:'#C9A84C', area:true}], unit:'B', fmtY:v=>fmt(v,0)}));
    registerChart('dashShare', donutChart([{label:'Awaiting report', value:100, color:'#8C7231'}]));
  }
  renderCharts();
}
function reportRow(r) {
  const st = r.status === 'completed' ? 'ok' : r.status === 'failed' ? 'bad' : 'warn';
  return `<div class="report-row"><div>
      <div class="rr-title">${esc(r.query)}</div>
      <div class="rr-meta">${esc(r.region)} · ${esc(r.period)} · ${shortDate(r.created_at)} · reliability ${r.reliability_score || 0}/100</div>
    </div><span class="badge ${st}"><i></i>${esc(r.status)}</span>
    <div class="rr-actions"><button class="btn btn-ghost btn-sm" data-action="open" data-id="${r.id}">Open ${icon('arrow')}</button></div></div>`;
}
async function renderHistory() {
  let html = `<div class="card" style="margin-bottom:20px">
    <div class="card-head"><div><span class="eyebrow">ARCHIVE</span><h2>Report History</h2>
      <p>Every report is stored with its full agent outputs, sources and exports.</p></div>
      <button class="btn btn-gold btn-sm" data-action="new-report">${icon('spark')} New Report</button></div>
    <div class="composer-row" style="margin-top:0">
      <div class="field" style="flex:1;min-width:220px"><label>Search reports</label>
        <input type="text" id="histSearch" placeholder="Query, company, keyword…" value="${esc(S.histSearch || '')}" /></div>
      <div class="field"><label>Status</label><select id="histStatus"><option value="">All</option><option value="completed">Completed</option><option value="processing">Processing</option><option value="failed">Failed</option></select></div>
      <div class="field"><label>Region</label><select id="histRegion"><option value="">All regions</option>${(S.settings?.regions || []).map(r => `<option>${esc(r)}</option>`).join('')}</select></div>
      <button class="btn btn-ghost" data-action="hist-filter">${icon('search')} Filter</button>
    </div></div>
    <div class="card"><div class="card-head"><div><h3>${S.reports.length} report${S.reports.length === 1 ? '' : 's'}</h3>
      <p>Select two rows to compare past reports side by side.</p></div>
      <button class="btn btn-outline btn-sm" data-action="compare-selected">${icon('swap')} Compare selected</button></div>
      <div id="histList">${S.reports.length ? `<div class="tbl-wrap"><table class="tbl">
        <thead><tr><th>Query / Subject</th><th>Region</th><th>Period</th><th>Reliability</th><th>Status</th><th>Created</th><th style="text-align:right">Actions</th></tr></thead><tbody>
        ${S.reports.map(r => `<tr><td><label style="display:flex;gap:9px;align-items:center;cursor:pointer">
          <input type="checkbox" class="hist-check" value="${r.id}" style="width:14px;height:14px;accent-color:#C9A84C"/>
          <strong>${esc(r.query)}</strong></label><div class="tiny muted" style="margin-left:23px">${esc(r.company || '')}</div></td>
          <td>${esc(r.region)}</td><td class="mono">${esc(r.period)}</td>
          <td class="num">${r.reliability_score || 0}/100</td>
          <td><span class="badge ${r.status === 'completed' ? 'ok' : r.status === 'failed' ? 'bad' : 'warn'}"><i></i>${esc(r.status)}</span></td>
          <td class="tiny mono">${shortDate(r.created_at)}</td>
          <td><div class="rr-actions" style="justify-content:flex-end">
            <button class="btn btn-ghost btn-sm" data-action="open" data-id="${r.id}">Open</button>
            <button class="icon-btn" data-action="delete" data-id="${r.id}" title="Delete">${icon('trash')}</button>
          </div></td></tr>`).join('')}
        </tbody></table></div>` : `<div class="empty">${icon('file')}<h3>No reports found</h3><p class="small">Try a different filter or generate a new report.</p></div>`}</div>
    </div>`;
  $('#view').innerHTML = html;
  $('#histStatus').value = S.histStatus || '';
  $('#histRegion').value = S.histRegion || '';
  S.chartFns.clear();
}
async function loadReport(id, keepTab = true) {
  try {
    const f = S.filters;
    const q = `?region=${encodeURIComponent(f.region)}&period=${encodeURIComponent(f.period)}&competitor=${encodeURIComponent(f.competitor)}`;
    S.dashboard = await api(`/api/reports/${id}/dashboard${q}`);
    S.reportId = id;
    if (!keepTab) S.tab = 'overview';
    renderReport();
  } catch (e) { toast(e.message, 'err'); }
}
async function renderReport() {
  const d = S.dashboard;
  if (!d) { $('#view').innerHTML = `<div class="card empty">${icon('file')}<h3>Select a report</h3></div>`; return; }
  const ds = d.dataset, r = d.report, fc = d.factcheck || {};
  const filters = d.filters;
  S.filters.region = filters.region; S.filters.period = filters.period;
  const langOpts = (S.settings?.languages || [{code:'en',native:'English'}]).map(l =>
    `<option value="${l.code}" ${l.code === r.language ? 'selected' : ''}>${esc(l.native)}</option>`).join('');
  const tabs = [['overview','Overview'],['report','Full Report'],['forecast','Forecast'],
                ['verify','Verification'],['sources','Sources'],['logs','Agent Logs']];
  $('#view').innerHTML = `
  <div class="report-hero">
    <div class="hero-eyebrow">Intelligence report · ${esc(r.status)}</div>
    <h1>${esc(ds.company)} <span style="color:var(--gold)">— ${esc(ds.sector)}</span></h1>
    <p class="small muted" style="margin:0;max-width:760px">${esc(r.query)}</p>
    <div class="meta">
      <span class="badge gold"><i></i>${esc(ds.region)}</span>
      <span class="badge mute">${esc(ds.period)} review</span>
      <span class="badge ${ds.data_mode === 'live' ? 'ok' : 'warn'}"><i></i>${esc(ds.data_mode)} data</span>
      <span class="badge ${fc.reliability_score >= 80 ? 'ok' : 'warn'}"><i></i>Reliability ${fc.reliability_score || 0}/100</span>
      <span class="badge mute">${ds.sources.length} sources</span>
      <span class="badge mute">${shortDate(r.created_at)}</span>
    </div>
    <div class="report-actions">
      <a class="btn btn-gold btn-sm" href="/api/reports/${r.id}/export/pdf" target="_blank" rel="noopener">${icon('download')} PDF Report</a>
      <a class="btn btn-outline btn-sm" href="/api/reports/${r.id}/export/pptx" target="_blank" rel="noopener">${icon('download')} PowerPoint</a>
      <a class="btn btn-outline btn-sm" href="/api/reports/${r.id}/export/excel" target="_blank" rel="noopener">${icon('download')} Excel</a>
      <button class="btn btn-ghost btn-sm" data-action="open-chat">${icon('chat')} Ask follow-up</button>
      <div class="field" style="margin-left:auto"><label>Translate report</label>
        <div style="display:flex;gap:6px"><select id="translateLang">${langOpts}</select>
        <button class="btn btn-ghost btn-sm" data-action="translate">${icon('globe')}</button></div></div>
    </div>
  </div>
  <div class="filter-bar">
    <div class="field"><label>Region</label><select id="fRegion">${filters.regions.map(x => `<option ${x === filters.region ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <div class="field"><label>Time period</label><select id="fPeriod">${filters.periods.map(x => `<option ${x === filters.period ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <div class="field"><label>Competitor focus</label><select id="fComp">${filters.competitors.map(x => `<option ${x === filters.competitor ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select></div>
    <button class="btn btn-gold btn-sm" data-action="apply-filters">${icon('refresh')} Apply filters</button>
    <span class="small muted" style="margin-left:8px">Charts recompute instantly</span>
  </div>
  <div class="tabs">${tabs.map(([k, v]) => `<button class="tab ${S.tab === k ? 'active' : ''}" data-action="tab" data-tab="${k}">${v}</button>`).join('')}</div>
  <div id="tabBody"></div>`;
  renderTab();
}
function renderTab() {
  const d = S.dashboard; if (!d) return;
  const ds = d.dataset, a = d.analysis, fc = d.factcheck || {}, f = d.forecast || {};
  const sel = d.selected_competitor || ds.competitors[0];
  const el = $('#tabBody'); if (!el) return;
  S.chartFns.clear();
  if (S.tab === 'overview') {
    el.innerHTML = `
      <div class="grid g4" style="margin-bottom:16px">
        ${kpi('Market size', `<span class="mono">$${fmt(ds.market_size_usd_b, 1)}B</span>`, `+${fmt(ds.cagr_pct, 1)}% CAGR · ${esc(ds.region)}`, 'chart', true)}
        ${kpi('Leader share', `<span class="mono">${fmt(sel.share, 1)}%</span>`, esc(sel.name), 'grid', true)}
        ${kpi('Sentiment', `<span class="mono">${fmt((ds.overall_sentiment || .6) * 100, 0)}</span>`, esc(ds.sentiment_label || 'Positive') + ' · cross-channel', 'spark', true)}
        ${kpi('Reliability', `<span class="mono">${fc.reliability_score || 0}</span>`, `${fc.flagged_count || 0} flagged claim(s)`, 'shield', true)}
      </div>
      <div class="grid g23" style="margin-bottom:16px">
        ${card('Market trajectory', 'Historic size · USD billions', `<div class="chart-box tall" id="cHistory"></div>
          <div class="legend"><span><i style="background:var(--gold)"></i>Market size</span><span class="muted">${ds.history[0]?.year} – ${ds.history.at(-1)?.year}</span></div>`)}
        ${card('Market share', 'Estimated share by tracked player', `<div class="chart-box tall" id="cShare"></div><div class="legend" id="cShareLegend"></div>`)}
      </div>
      <div class="grid g23" style="margin-bottom:16px">
        ${card('Revenue trend', `${esc(sel.name)} vs competitor average · USD B / quarter`,
          `<div class="chart-box tall" id="cRevenue"></div><div class="legend">
          <span data-toggle="0"><i style="background:var(--gold)"></i>${esc(sel.name)}</span>
          <span data-toggle="1"><i style="background:#4C7BF3"></i>Competitor average</span></div>`)}
        ${card('Segment mix', 'Share of demand by customer cohort', `<div class="chart-box tall" id="cSegments"></div>`)}
      </div>
      <div class="grid g2" style="margin-bottom:16px">
        ${card('Sentiment heatmap', 'Channel × week · hover for detail',
          `<div class="heat-wrap" id="cHeat" style="position:relative"></div>
           <div class="legend"><span><i style="background:rgba(225,29,72,.75)"></i>Negative</span>
           <span><i style="background:rgba(201,168,76,.6)"></i>Neutral</span>
           <span><i style="background:rgba(5,150,105,.7)"></i>Positive</span></div>`)}
        ${card('Macro indicators', `Economic backdrop · ${esc(ds.region)}`, `<div class="chart-box tall" id="cMacro"></div>`)}
      </div>
      <div class="grid g2">
        ${card('Competitive landscape', 'Share, revenue, growth and sentiment', `<div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>Company</th><th>Share</th><th>Revenue</th><th>Growth</th><th>Sentiment</th></tr></thead><tbody>
          ${ds.competitors.map(c => `<tr><td><strong>${esc(c.name)}</strong></td><td class="num">${fmt(c.share,1)}%</td>
          <td class="num">$${fmt(c.revenue_usd_b,1)}B</td><td class="num">${fmt(c.growth_pct,1)}%</td>
          <td class="num">${fmt(c.sentiment*100,0)}</td></tr>`).join('')}</tbody></table></div>`)}
        ${card('Strategic snapshot', esc(a.summary || ''), `<div class="tbl-wrap"><table class="tbl">
          <thead><tr><th>SWOT</th><th>Leading finding</th></tr></thead><tbody>
          ${Object.entries(a.swot || {}).map(([k,v]) => `<tr><td><strong class="gold">${esc(k)}</strong></td><td>${esc(v[0] || '')}</td></tr>`).join('')}
          </tbody></table></div>`)}
      </div>`;
    registerChart('cHistory', lineChart({labels: ds.history.map(h => String(h.year)),
      series:[{name:'Market size', values:ds.history.map(h=>h.value), color:'#C9A84C', area:true}],
      unit:'B', decimals:1, fmtY:v=>fmt(v,0)}));
    registerChart('cShare', donutChart(ds.competitors.map((c,i)=>({label:c.name,value:c.share,color:PALETTE[i%PALETTE.length]}))));
    $('#cShareLegend').innerHTML = ds.competitors.map((c,i)=>
      `<span><i style="background:${PALETTE[i%PALETTE.length]}"></i>${esc(c.name)} · ${fmt(c.share,1)}%</span>`).join('');
    registerChart('cRevenue', lineChart({labels:ds.quarters.map(q=>q.label),
      series:[{name:sel.name, values:ds.quarters.map(q=>q.revenue), color:'#C9A84C', area:true},
              {name:'Competitor average', values:ds.quarters.map(q=>q.competitor_avg), color:'#4C7BF3', dots:false}],
      unit:'B', decimals:1, fmtY:v=>fmt(v,0)}));
    registerChart('cSegments', barChart(ds.segments.map((s,i)=>({label:s.name,value:s.value,color:PALETTE[i]})), {unit:'%', labelWidth:110}));
    $('#cHeat').innerHTML = heatmapHtml(ds.heatmap, ds.heatmap_weeks, ds.heatmap_channels)
      + '<div class="chart-tooltip" data-ttbox></div>';
    registerChart('cMacro', barChart(Object.entries(ds.macro).slice(0,6).map(([k,v],i)=>({label:k,value:Math.abs(v),color:PALETTE[i]})), {labelWidth:150, decimals:1}));
  } else if (S.tab === 'report') {
    const secs = d.writer.sections || [];
    el.innerHTML = `<div class="grid g32">
      ${card('Report contents', `${secs.length} sections · ${(d.writer.markdown || '').split(/\s+/).length} words`,
        secs.map((s,i)=>`<div class="guide-step" style="margin-bottom:10px;padding-left:14px">
          <span class="tiny mono gold">${String(i+1).padStart(2,'0')}</span>
          <div class="small" style="color:var(--white);margin-top:2px">${esc(s.title)}</div></div>`).join(''))}
      ${card('Full research report', 'Board-ready markdown with citations',
        `<div class="md">${mdToHtml(d.writer.markdown || '')}</div>`)}
    </div>`;
  } else if (S.tab === 'forecast') {
    const series = f.series || [];
    el.innerHTML = `<div class="grid g32">
      ${card('Scenario outcomes', 'Probability-weighted 12-month view',
        (f.scenarios || []).map(sc => `<div style="padding:14px 0;border-bottom:1px solid var(--line-2)">
          <div style="display:flex;justify-content:space-between"><b class="ivory">${esc(sc.name)}</b>
          <span class="mono gold">$${fmt(sc.value,1)}B</span></div>
          <div class="small muted" style="margin-top:6px">${esc(sc.narrative)}</div>
          <span class="badge mute" style="margin-top:8px">${esc(sc.probability)} probability</span></div>`).join('') +
        `<div class="divider"></div><p class="tiny muted">${esc(f.method || '')} · ${esc(f.note || '')}</p>`)}
      ${card('12-month forecast with confidence bands', 'Base · optimistic · pessimistic (USD B)',
        `<div class="chart-box tall" id="cForecast"></div><div class="legend">
          <span data-toggle="1"><i style="background:var(--gold)"></i>Base</span>
          <span data-toggle="0"><i style="background:var(--success)"></i>Optimistic</span>
          <span data-toggle="2"><i style="background:var(--danger)"></i>Pessimistic</span>
          <span><i style="background:rgba(139,124,246,.4)"></i>Confidence band</span></div>` +
        `<div class="tbl-wrap" style="margin-top:18px"><table class="tbl"><thead><tr><th>Month</th><th>Base</th><th>Optimistic</th><th>Pessimistic</th><th>Confidence</th></tr></thead><tbody>
        ${series.map(x=>`<tr><td class="mono">${esc(x.month)}</td><td class="num">${fmt(x.base,1)}</td>
        <td class="num">${fmt(x.optimistic,1)}</td><td class="num">${fmt(x.pessimistic,1)}</td>
        <td class="num">${fmt(x.confidence*100,0)}%</td></tr>`).join('')}</tbody></table></div>`)}
    </div>`;
    registerChart('cForecast', lineChart({labels:series.map(x=>x.month.slice(2)),
      series:[{name:'Optimistic',values:series.map(x=>x.optimistic),color:'#059669',dots:false},
              {name:'Base',values:series.map(x=>x.base),color:'#C9A84C'},
              {name:'Pessimistic',values:series.map(x=>x.pessimistic),color:'#E11D48',dots:false}],
      band:{upper:series.map(x=>x.optimistic),lower:series.map(x=>x.pessimistic)},
      unit:'B', decimals:1, fmtY:v=>fmt(v,0)}));
  } else if (S.tab === 'verify') {
    el.innerHTML = `<div class="grid g32">
      ${card('Section reliability', 'Score out of 100',
        (fc.section_scores||[]).map(s=>`<div style="margin-bottom:14px">
          <div style="display:flex;justify-content:space-between;font-size:12px"><span>${esc(s.section)}</span>
          <b class="mono gold">${s.score}/100</b></div>
          <div class="score-bar"><i style="width:${s.score}%"></i></div>
          <div class="tiny muted" style="margin-top:5px">${s.claims_checked} claims checked · ${s.flags} flag(s)</div></div>`).join('') +
        `<div class="divider"></div><p class="tiny muted">${esc(fc.disclaimer||'')}</p>`)}
      ${card('Claim-level verification', 'Each major claim mapped to 2+ independent sources',
        (fc.claims||[]).map(c=>`<div class="claim"><span class="c-dot" style="background:${c.status==='verified'?'var(--success)':c.status==='partially_verified'?'var(--warn)':'var(--danger)'}"></span>
        <div><p>${esc(c.claim)}</p><small>${esc(c.category)} · ${esc(c.status.replace(/_/g,' '))} · ${c.score}/100 · refs ${esc((c.sources||[]).join(', '))}</small>
        <div class="tiny muted" style="margin-top:4px">${esc(c.note||'')}</div></div></div>`).join('') +
        `<div class="divider"></div><p class="tiny muted">${esc(fc.method||'')}</p>`)}
    </div>`;
  } else if (S.tab === 'sources') {
    el.innerHTML = card('Source appendix', `${ds.sources.length} references`,
      `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Ref</th><th>Publisher</th><th>Title</th><th>Type</th><th>Reliability</th><th>Link</th></tr></thead><tbody>
      ${ds.sources.map(s=>`<tr><td class="mono gold">${esc(s.id)}</td><td><strong>${esc(s.publisher)}</strong></td>
      <td>${esc(s.title)}</td><td>${esc(s.type)}</td><td class="num">${s.reliability}/100</td>
      <td><a href="${esc(s.url)}" target="_blank" rel="noopener">Open ${icon('arrow')}</a></td></tr>`).join('')}
      </tbody></table></div><div class="divider"></div><p class="tiny muted">${esc(ds.confidence_note)}</p>`) +
      `<div style="height:16px"></div>` +
      card('Latest headlines', 'Collected news signals',
        (ds.news||[]).map(n=>`<div class="claim"><span class="c-dot" style="background:${n.sentiment>.6?'var(--success)':'var(--gold)'}"></span>
        <div><p>${esc(n.title)}</p><small>${esc(n.source)} · ${esc(n.date)} · sentiment ${fmt(n.sentiment*100,0)}/100 · reliability ${n.reliability}/100</small></div></div>`).join(''));
  } else if (S.tab === 'logs') {
    el.innerHTML = card('Agent execution log', 'Performance telemetry for this report',
      `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Agent</th><th>Provider</th><th>Status</th><th>Time</th><th>Tokens in</th><th>Tokens out</th><th>Note</th></tr></thead><tbody>
      ${(d.agent_logs||[]).map(l=>`<tr><td><strong>${esc(l.agent_name)}</strong></td><td>${esc(l.provider_used)}</td>
      <td><span class="badge ${l.status==='done'?'ok':'warn'}"><i></i>${esc(l.status)}</span></td>
      <td class="num">${l.execution_time_ms} ms</td><td class="num">${l.input_tokens}</td><td class="num">${l.output_tokens}</td>
      <td class="tiny">${esc(l.error_message||'—')}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">No logs recorded.</td></tr>'}
      </tbody></table></div>`) +
      `<div style="height:16px"></div><div class="grid g3">
        ${card('Failure isolation', 'Always-on', `<p class="small muted">Each agent runs inside an isolation boundary. A missing key, timeout or malformed provider response falls back to the local analytical engine, so one failure never stops the pipeline.</p>`)}
        ${card('Encrypted vault', 'Fernet', `<p class="small muted">API keys are encrypted before they reach the database. Only masked values are ever returned to the browser.</p>`)}
        ${card('Data provenance', esc(ds.data_mode), `<p class="small muted">${esc(ds.confidence_note)}</p>`)}
      </div>`;
  }
  renderCharts();
}

async function renderCompare() {
  const c = S.compare;
  let html = `<div class="card" style="margin-bottom:20px">
    <div class="card-head"><div><span class="eyebrow">COMPARISON MODE</span><h2>Head-to-head intelligence</h2>
      <p>Compare two companies, or two saved reports, across every tracked dimension.</p></div></div>
    <div class="vs-head">
      <div class="field"><label>Company A</label><input type="text" id="cmpA" placeholder="e.g. Tesla" value="${esc(S.cmpA || '')}" /></div>
      <div class="vs-orb">VS</div>
      <div class="field"><label>Company B</label><input type="text" id="cmpB" placeholder="e.g. BYD" value="${esc(S.cmpB || '')}" /></div>
    </div>
    <div class="composer-row" style="margin-top:0">
      <div class="field"><label>Region</label><select id="cmpRegion">${(S.settings?.regions||['Global']).map(r=>`<option>${esc(r)}</option>`).join('')}</select></div>
      <button class="btn btn-gold" data-action="compare-companies">${icon('swap')} Run comparison</button>
      <button class="btn btn-ghost" data-action="compare-selected">${icon('file')} Compare two saved reports</button>
    </div></div>`;
  if (c && c.metrics) {
    const a = c.company_a, b = c.company_b;
    html += `<div class="grid g32" style="margin-bottom:16px">
      ${card('Dimension scorecard', 'Gold = A · Sapphire = B',
        c.metrics.map(m => {
          const winA = m.a >= m.b, total = (m.a + m.b) || 1;
          return `<div class="metric-row">
            <div><div class="metric-val a ${winA?'win':''}">${fmt(m.a,1)}${esc(m.unit)}</div>
            <div class="bar-compare"><i class="ba" style="width:${m.a/total*100}%"></i><i class="bb" style="width:${m.b/total*100}%"></i></div></div>
            <div class="m-name">${esc(m.metric)}</div>
            <div><div class="metric-val b ${!winA?'win':''}">${fmt(m.b,1)}${esc(m.unit)}</div>
            <div class="bar-compare"><i class="ba" style="width:${m.a/total*100}%"></i><i class="bb" style="width:${m.b/total*100}%"></i></div></div></div>`;
        }).join('') + `<div class="info-strip" style="margin:18px 0 0">${icon('spark')}<div><b>Verdict.</b> ${esc(c.verdict)}</div></div>`,
        `<span class="badge gold">${esc(c.region)}</span>`)}
      ${card('Market size & growth', 'Side-by-side trajectories',
        `<div class="chart-box tall" id="cmpChart"></div><div class="legend">
        <span data-toggle="0"><i style="background:var(--gold)"></i>${esc(a)}</span>
        <span data-toggle="1"><i style="background:#4C7BF3"></i>${esc(b)}</span></div>`)}
    </div>
    <div class="grid g2">${[a,b].map((name,i)=>{const x=i?c.dataset_b:c.dataset_a;return card(esc(name), 'Strategic profile',
      `<p class="small muted">${esc(x?.sector || '')} · ${esc(x?.region || '')}</p>
       <div class="tbl-wrap"><table class="tbl"><tbody>
       <tr><td>Market size</td><td class="num">$${fmt(x?.market_size_usd_b,1)}B</td></tr>
       <tr><td>CAGR</td><td class="num">${fmt(x?.cagr_pct,1)}%</td></tr>
       <tr><td>Leading player</td><td><strong>${esc(x?.competitors?.[0]?.name||'')}</strong></td></tr>
       <tr><td>Sources</td><td class="num">${x?.sources?.length||0}</td></tr></tbody></table></div>`)}).join('')}</div>`;
  } else if (c && c.report_a) {
    html += `<div class="grid g2">${[c.report_a,c.report_b].map((r,i)=>card(i?'Report B':'Report A', esc(r.query),
      `<p class="small muted">${esc(r.executive_summary || r.summary || '')}</p>
       <div class="tbl-wrap"><table class="tbl"><tbody>
       <tr><td>Company</td><td class="num">${esc(r.company)}</td></tr>
       <tr><td>Region / period</td><td class="num">${esc(r.region)} · ${esc(r.period)}</td></tr>
       <tr><td>Market size</td><td class="num">$${fmt(r.market_size,1)}B</td></tr>
       <tr><td>CAGR</td><td class="num">${fmt(r.cagr,1)}%</td></tr>
       <tr><td>Reliability</td><td class="num">${r.reliability}/100</td></tr>
       <tr><td>Created</td><td class="num tiny">${shortDate(r.created_at)}</td></tr></tbody></table></div>
       <button class="btn btn-outline btn-sm" style="margin-top:14px" data-action="open" data-id="${r.id}">Open report</button>`)).join('')}</div>`;
  } else {
    html += `<div class="card empty" style="padding:60px 20px">${icon('swap')}
      <h3>Compare anything</h3><p class="small">Enter two companies above, or select two reports in History and hit “Compare selected”.</p></div>`;
  }
  $('#view').innerHTML = html;
  if (c && c.metrics) {
    registerChart('cmpChart', lineChart({labels:c.dataset_a.history.map(h=>String(h.year)),
      series:[{name:c.company_a,values:c.dataset_a.history.map(h=>h.value),color:'#C9A84C',area:true},
              {name:c.company_b,values:c.dataset_b.history.map(h=>h.value),color:'#4C7BF3',dots:false}],
      unit:'B', decimals:1, fmtY:v=>fmt(v,0)}));
  }
  renderCharts();
}

async function renderSettings() {
  const p = S.settings;
  const grouped = (tier) => p.providers.filter(x => x.tier === tier).map(x =>
    `<option value="${x.key}">${esc(x.label)}</option>`).join('');
  const optgroups = `<optgroup class="provider-group" label="FREE PROVIDERS">${grouped('free')}</optgroup>
                     <optgroup class="provider-group paid" label="PAID PROVIDERS">${grouped('paid')}</optgroup>`;
  let html = `<div class="info-strip">${icon('shield')}<div><b>Your keys never leave this machine unencrypted.</b>
    Each agent has its own independent key slot. Keys are encrypted with Fernet (AES-128-CBC + HMAC)
    before storage, and only masked values are returned to this page. You may use the same key in every slot,
    or mix providers freely. No key is required — the local analytical engine runs the full pipeline.</div></div>
  <div class="card" style="margin-bottom:20px">
    <div class="card-head"><div><span class="eyebrow">QUICK SETUP</span><h3>Use one key for all agents</h3>
      <p>Ideal when you have a single Groq, Gemini or OpenAI key. Every slot is updated at once.</p></div>
      <span class="badge ${p.configured_count ? 'ok' : 'warn'}"><i></i>${p.configured_count} / ${p.slots.length} configured</span></div>
    <div class="composer-row" style="margin-top:0">
      <div class="field"><label>Provider</label><select id="allProvider">${optgroups}</select></div>
      <div class="field" style="flex:1;min-width:200px"><label>API key</label><input type="password" id="allKey" placeholder="Paste your API key" /></div>
      <button class="btn btn-gold" data-action="apply-all">${icon('key')} Apply to all ${p.slots.length} slots</button>
    </div>
  </div>
  ${sectionTitle('Independent agent key slots')}
  <div class="grid g2" id="slotGrid">`;
  p.slots.forEach(s => {
    const spec = p.providers.find(x => x.key === s.provider);
    const models = spec?.models || [];
    html += `<section class="card slot-card" data-slot="${esc(s.slot)}">
      <div class="slot-head"><div class="slot-ico">${s.icon}</div>
        <div style="flex:1"><b>${esc(s.name)}${s.slot==='translator'?' <span class="badge mute">optional</span>':''}</b>
        <small>${esc(s.description)}</small></div>
        <span class="badge ${s.configured ? 'ok' : 'mute'}"><i></i>${s.configured ? 'CONFIGURED' : 'NO KEY'}</span></div>
      ${s.configured ? `<div class="saved-key" style="margin-bottom:14px"><span>${esc(s.masked_key)} · ${esc(spec?.label || s.provider)}</span>
        <span>${s.last_test_ok === true ? '✓ tested' : s.last_test_ok === false ? '⚠ test failed' : 'not tested'}</span></div>` : ''}
      <div class="slot-grid">
        <div class="field"><label>Provider</label><select class="s-provider">${optgroups}</select></div>
        <div class="field"><label>Model</label><select class="s-model">${models.map(m=>`<option ${m===s.model?'selected':''}>${esc(m)}</option>`).join('')}</select></div>
        <div class="field wide"><label>API key ${s.configured ? '(leave blank to keep current)' : ''}</label>
          <div class="key-input-wrap"><input type="password" class="s-key" placeholder="${esc(spec?.key_hint || 'Paste key')}" autocomplete="off" />
          <button class="icon-btn" data-action="toggle-key" title="Show / hide">${icon('eye')}</button></div></div>
      </div>
      <div class="slot-actions">
        <button class="btn btn-gold btn-sm" data-action="save-key">${icon('check')} Save key</button>
        <button class="btn btn-outline btn-sm" data-action="test-key">${icon('refresh')} Test connection</button>
        <button class="btn btn-ghost btn-sm" data-action="delete-key">${icon('trash')}</button>
      </div>
      <div class="slot-result tiny muted" style="margin-top:10px">${s.configured ? `Encrypted at rest · ${esc(s.model || 'default model')}` : 'Uses the local analytical engine until a key is saved.'}</div>
      <div style="margin-top:10px"><a class="tiny" id="signup-${s.slot}" href="#" target="_blank" rel="noopener">Get a free key ↗</a></div>
    </section>`;
  });
  html += `</div>
  ${sectionTitle('Localisation & security')}
  <div class="grid g2">
    ${card('Supported languages', `${p.languages.length} languages · preserves markdown, tables and charts`,
      `<div class="lang-wrap">${p.languages.map(l=>`<span class="lang-tag">${esc(l.native)} <span class="tiny muted">${esc(l.code)}</span></span>`).join('')}</div>`)}
    ${card('Provider catalogue', `${p.providers.length} vendors · free and paid`,
      `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Provider</th><th>Tier</th><th>Default model</th><th>Get key</th></tr></thead><tbody>
      ${p.providers.map(x=>`<tr><td><strong>${esc(x.label)}</strong></td>
      <td><span class="badge ${x.tier==='free'?'ok':'gold'}"><i></i>${esc(x.group)}</span></td>
      <td class="tiny mono">${esc(x.default_model)}</td>
      <td><a href="${esc(x.signup_url)}" target="_blank" rel="noopener">Open ↗</a></td></tr>`).join('')}
      </tbody></table></div>`)}
  </div>`;
  $('#view').innerHTML = html;
  $$('.slot-card').forEach(cardEl => {
    const s = p.slots.find(x => x.slot === cardEl.dataset.slot);
    const provSel = $('.s-provider', cardEl), modelSel = $('.s-model', cardEl);
    if (s?.provider) provSel.value = s.provider;
    const sync = () => {
      const spec = p.providers.find(x => x.key === provSel.value);
      modelSel.innerHTML = (spec?.models || []).map(m => `<option>${esc(m)}</option>`).join('');
      if (s?.model && spec?.models.includes(s.model)) modelSel.value = s.model;
      const link = $('#signup-' + cardEl.dataset.slot);
      link.href = spec?.signup_url || '#';
    };
    provSel.addEventListener('change', sync); sync();
  });
  S.chartFns.clear();
}

function renderGuide() {
  $('#view').innerHTML = `<div class="hero" style="padding:32px 36px">
    <div class="hero-eyebrow">Documentation</div><h1 style="font-size:32px">The Meridian <span>User Guide</span></h1>
    <p class="hero-sub">Everything you need to go from a single question to a verified, exportable market report.</p></div>
  <div class="grid g2">
    ${card('1 · Generate a report', 'Start from the Dashboard', `<div class="md">
      <p>Type any market question — a sector, a company, or a <strong>Company A vs Company B</strong> comparison — then choose a region, time period and output language. Press <strong>Generate Intelligence</strong>.</p>
      <p>The Agent Activity panel on the right streams each agent's status live. Within seconds you'll have a full report, six interactive chart families and three downloadable files.</p></div>`)}
    ${card('2 · Explore & filter', 'Interactive dashboard', `<div class="md">
      <p>Use the <strong>Region</strong>, <strong>Time period</strong> and <strong>Competitor focus</strong> filters to recompute every chart. Hover any chart for precise values, and click a legend item to toggle a series.</p>
      <p>Tabs cover the full written report, the 12-month forecast with confidence bands, claim-level verification, the source appendix and agent execution logs.</p></div>`)}
    ${card('3 · Configure API keys', 'Settings → API Keys', `<div class="md">
      <p>Meridian works with no keys at all via its local analytical engine. To add live LLM intelligence, open <strong>API Keys</strong>, pick a free or paid provider for each agent slot, paste a key and press <strong>Save key</strong>.</p>
      <p><strong>Test connection</strong> performs a real, minimal request to the provider and reports latency and quota headers. The quick-setup bar applies one key to all slots at once.</p></div>`)}
    ${card('4 · Ask, translate, compare, export', 'Power features', `<div class="md">
      <p>Use the <strong>Ask</strong> button for grounded follow-up questions about rural markets, competitors, risks, sources or next steps. Translate the entire report into any of 14 languages from the report header.</p>
      <p>In <strong>Compare Mode</strong>, put two companies head-to-head, or tick two rows in History and compare past reports. Export to PDF, PowerPoint or Excel at any time.</p></div>`)}
  </div>
  ${sectionTitle('Data & honesty')}
  ${card('Where the numbers come from', 'Provenance is always visible', `<div class="md">
    <p>Meridian attempts live connectors for web search (Tavily / DuckDuckGo), Yahoo Finance, NewsAPI, Reddit sentiment and World Bank macro indicators. Each connector is failure-isolated.</p>
    <p>When a connector or LLM key is unavailable, a deterministic, query-aware analytical engine produces consistent figures, clearly labelled <strong>simulated</strong> in the data-mode badge, the report and the fact-check section. Modelled figures are explicitly flagged ⚠️ — confirm them with primary sources before external publication.</p>
    <p>Add keys in Settings or set <code>TAVILY_API_KEY</code>, <code>NEWS_API_KEY</code> and <code>DATABASE_URL</code> in your environment to upgrade to live data.</p></div>`)}
  <div class="divider"></div>
  <p class="small muted" style="text-align:center">Developed by <b class="gold">Mridul Sharma</b> · Meridian v1.0.0 · Market Intelligence, Redefined.</p>`;
  S.chartFns.clear();
}

/* ------------------------------------------------------------- Actions --- */
async function refreshChrome() {
  try {
    const [stats, reports, settings] = await Promise.all([
      api('/api/stats'), api('/api/reports?limit=100'), api('/api/settings')]);
    S.stats = stats; S.reports = reports; S.settings = settings;
    $('#navReportCount').textContent = reports.length;
    $('#keyDot').classList.toggle('ok', settings.configured_count > 0);
    renderMission();
  } catch (e) { console.warn('refresh failed', e); }
}
async function refreshReports(extra = '') {
  try { S.reports = await api('/api/reports?limit=100' + extra); }
  catch (e) { toast(e.message, 'err'); }
}
function navigate(view, id) {
  S.view = view;
  if (id) S.reportId = id;
  const labels = {dashboard:'Dashboard', history:'Report History', report:'Intelligence Report',
                  compare:'Compare Mode', settings:'API Keys', guide:'User Guide'};
  $('#crumb').innerHTML = `<span>Meridian</span><b>/</b><strong>${labels[view] || view}</strong>`;
  $$('.nav-item[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const desired = view === 'report' ? `#/report/${S.reportId}` : `#/${view}`;
  if (location.hash !== desired) location.hash = desired;
  $('#chatDock').hidden = true;
  $('#chatFab').style.display = '';
  renderView();
}
async function renderView() {
  S.chartFns.clear();
  $('#view').innerHTML = `<div class="grid g3">${[1,2,3].map(() =>
    '<div class="card"><div class="skeleton" style="height:18px;width:45%;margin-bottom:16px"></div><div class="skeleton" style="height:120px"></div></div>').join('')}</div>`;
  try {
    if (S.view === 'dashboard') {
      if (!S.dashboard && S.reports.length) {
        const latest = S.reports.find(r => r.status === 'completed') || S.reports[0];
        if (latest) { try { S.dashboard = await api(`/api/reports/${latest.id}/dashboard`); } catch {} }
      }
      await renderDashboard();
    } else if (S.view === 'history') await renderHistory();
    else if (S.view === 'report') { if (!S.dashboard || S.dashboard.report.id !== S.reportId) await loadReport(S.reportId, false); else await renderReport(); }
    else if (S.view === 'compare') await renderCompare();
    else if (S.view === 'settings') { S.settings = await api('/api/settings'); await renderSettings(); }
    else if (S.view === 'guide') renderGuide();
  } catch (e) {
    $('#view').innerHTML = `<div class="card empty">${icon('close')}<h3>Something went wrong</h3><p class="small">${esc(e.message)}</p></div>`;
  }
  renderCharts();
}
async function generate() {
  const q = $('#queryInput')?.value.trim();
  if (!q || q.length < 3) { toast('Enter a research query of at least 3 characters', 'err'); return; }
  const btn = $('[data-action="generate"]');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Dispatching agents…'; }
  try {
    const body = {query: q, region: $('#regionSel')?.value || 'Global',
      period: $('#periodSel')?.value || '3Y', language: $('#langSel')?.value || 'en'};
    const res = await api('/api/reports', {method:'POST', body});
    S.agents = {}; S.progress = 0; S.jobStatus = 'running'; S.reportId = res.report_id;
    renderMission();
    toast('Pipeline launched — watch the Agent Activity panel', 'ok');
    connectEvents(res.report_id);
  } catch (e) { toast(e.message, 'err'); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = `${icon('spark')} Generate Intelligence`; } }
}
async function openChat() {
  if (!S.reportId) { toast('Open a report first to ask follow-up questions', 'info'); return; }
  S.chatReport = S.reportId;
  $('#chatDock').hidden = false; $('#chatFab').style.display = 'none';
  try {
    const [h, agents] = await Promise.all([
      api(`/api/reports/${S.reportId}/chat`), api('/api/agents')]);
    $('#chatLog').innerHTML = h.length ? h.map(m => `<div class="msg ${m.role === 'user' ? 'user' : 'ai'}">${mdInline(esc(m.message))}</div>`).join('')
      : `<div class="msg ai">Hello — I'm Meridian's Chat Agent. I answer using the research context already gathered for this report. Try a suggested question below.<span class="msg-meta">AGENT 4 · GROUNDED CONTEXT</span></div>`;
    $('#chatSuggest').innerHTML = (agents.chat_suggestions || []).slice(0, 4).map(x =>
      `<button class="chip" data-action="chat-suggest" data-q="${esc(x)}">${esc(x)}</button>`).join('');
    $('#chatLog').scrollTop = $('#chatLog').scrollHeight;
  } catch (e) { toast(e.message, 'err'); }
}
async function sendChat(q) {
  if (!q.trim() || !S.chatReport) return;
  const log = $('#chatLog');
  log.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(q)}</div>`);
  $('#chatInput').value = ''; log.scrollTop = log.scrollHeight;
  log.insertAdjacentHTML('beforeend', `<div class="msg ai" id="pendingMsg"><span class="spinner"></span> Analysing report context…</div>`);
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api(`/api/reports/${S.chatReport}/chat`, {method:'POST', body:{question:q}});
    const p = $('#pendingMsg');
    if (p) p.outerHTML = `<div class="msg ai">${mdInline(esc(r.answer))}<span class="msg-meta">${esc(r.provider)}</span></div>`;
  } catch (e) { const p = $('#pendingMsg'); if (p) p.outerHTML = `<div class="msg ai">${esc(e.message)}</div>`; }
  log.scrollTop = log.scrollHeight;
}

document.addEventListener('click', async (ev) => {
  const t = ev.target.closest('[data-action]'); if (!t) return;
  const a = t.dataset.action;
  try {
    if (a === 'nav') navigate(t.dataset.view);
    else if (a === 'refresh') { await refreshChrome(); await renderView(); toast('Data refreshed', 'ok'); }
    else if (a === 'new-report') { navigate('dashboard'); setTimeout(() => $('#queryInput')?.focus(), 300); }
    else if (a === 'suggest') { $('#queryInput').value = t.dataset.q; $('#queryInput').focus(); }
    else if (a === 'generate') await generate();
    else if (a === 'open') { S.dashboard = null; S.tab = 'overview'; S.filters = {region:'',period:'',competitor:''}; navigate('report', t.dataset.id); }
    else if (a === 'delete') {
      if (!confirm('Delete this report and its exports permanently?')) return;
      await api(`/api/reports/${t.dataset.id}`, {method:'DELETE'});
      toast('Report deleted', 'ok'); await refreshChrome(); await renderView();
    }
    else if (a === 'hist-filter') {
      S.histSearch = $('#histSearch').value; S.histStatus = $('#histStatus').value; S.histRegion = $('#histRegion').value;
      await refreshReports(`&search=${encodeURIComponent(S.histSearch)}&status=${encodeURIComponent(S.histStatus)}&region=${encodeURIComponent(S.histRegion)}`);
      await renderHistory();
    }
    else if (a === 'compare-selected') {
      const ids = $$('.hist-check:checked').map(x => x.value);
      if (S.view !== 'history') { navigate('history'); toast('Select two reports with the checkboxes, then press Compare selected again.', 'info', 6500); return; }
      if (ids.length !== 2) { toast('Select exactly two reports to compare', 'err'); return; }
      S.compare = await api('/api/reports/compare', {method:'POST', body:{report_a:ids[0], report_b:ids[1]}});
      navigate('compare');
    }
    else if (a === 'apply-filters') {
      S.filters = {region:$('#fRegion').value, period:$('#fPeriod').value, competitor:$('#fComp').value};
      await loadReport(S.reportId); toast('Filters applied — charts recomputed', 'ok');
    }
    else if (a === 'tab') { S.tab = t.dataset.tab; $$('.tab').forEach(x=>x.classList.toggle('active', x.dataset.tab===S.tab)); renderTab(); }
    else if (a === 'translate') {
      const lang = $('#translateLang').value;
      if (lang === 'en') { toast('The original report is already in English', 'info'); return; }
      toast('Translating…', 'info');
      const r = await api(`/api/reports/${S.reportId}/translate`, {method:'POST', body:{language:lang}});
      $('#tabBody').innerHTML = `<div class="card"><div class="card-head"><div><span class="eyebrow">TRANSLATED REPORT · ${esc(r.native)}</span>
        <h2>${esc(S.dashboard.report.company || 'Report')} — ${esc(r.native)}</h2><p>${esc(r.note || '')}</p></div>
        <button class="btn btn-ghost btn-sm" data-action="tab" data-tab="report">Back to report</button></div>
        <div class="md">${mdToHtml(r.content)}</div></div>`;
      toast(`Report translated to ${r.native}`, 'ok');
    }
    else if (a === 'compare-companies') {
      S.cmpA = $('#cmpA').value.trim(); S.cmpB = $('#cmpB').value.trim();
      if (!S.cmpA || !S.cmpB) { toast('Enter both companies', 'err'); return; }
      S.compare = await api('/api/compare', {method:'POST',
        body:{company_a:S.cmpA, company_b:S.cmpB, region:$('#cmpRegion').value}});
      await renderCompare(); toast('Comparison ready', 'ok');
    }
    else if (a === 'toggle-key') {
      const inp = $('.s-key', t.closest('.slot-card'));
      inp.type = inp.type === 'password' ? 'text' : 'password';
    }
    else if (a === 'save-key') {
      const c = t.closest('.slot-card'), slot = c.dataset.slot;
      const key = $('.s-key', c).value.trim();
      if (!key) { toast('Enter an API key first (or leave the slot unconfigured)', 'err'); return; }
      await api('/api/settings/keys', {method:'POST', body:{slot, provider:$('.s-provider', c).value,
        api_key:key, model:$('.s-model', c).value}});
      $('.slot-result', c).textContent = '✓ Saved and encrypted with Fernet.';
      toast(`${slot} key saved and encrypted`, 'ok'); await refreshChrome();
    }
    else if (a === 'test-key') {
      const c = t.closest('.slot-card'), slot = c.dataset.slot, out = $('.slot-result', c);
      out.innerHTML = '<span class="spinner"></span> Testing live connection…';
      const r = await api('/api/settings/keys/test', {method:'POST', body:{slot}});
      if (r.ok) { out.innerHTML = `✓ ${esc(r.provider)} responded in ${r.latency_ms} ms · ${esc(r.model)}${r.quota ? ' · quota headers received' : ''}`;
                  toast(`${r.provider} connection successful`, 'ok'); }
      else { out.textContent = `⚠ ${r.error}`; toast(r.error, 'err', 7000); }
    }
    else if (a === 'delete-key') {
      const c = t.closest('.slot-card'), slot = c.dataset.slot;
      if (!confirm(`Remove the ${slot} key? The local engine will take over.`)) return;
      await api(`/api/settings/keys/${slot}`, {method:'DELETE'});
      $('.slot-result', c).textContent = 'Key removed — local analytical engine active.';
      toast(`${slot} key removed`, 'ok'); await refreshChrome();
    }
    else if (a === 'apply-all') {
      const key = $('#allKey').value.trim(), provider = $('#allProvider').value;
      if (!key) { toast('Paste an API key first', 'err'); return; }
      const r = await api('/api/settings/keys/apply-all', {method:'POST', body:{provider, api_key:key}});
      toast(`Key applied to ${r.slots_updated} agent slots`, 'ok');
      await refreshChrome(); await renderView();
    }
    else if (a === 'open-chat') await openChat();
    else if (a === 'close-chat') { $('#chatDock').hidden = true; $('#chatFab').style.display = ''; }
    else if (a === 'chat-suggest') { $('#chatInput').value = t.dataset.q; await sendChat(t.dataset.q); }
  } catch (e) { toast(e.message, 'err', 6500); }
});
$('#chatForm')?.addEventListener('submit', async (ev) => { ev.preventDefault(); await sendChat($('#chatInput').value); });
$('#collapseBtn')?.addEventListener('click', () => { $('.shell').classList.toggle('collapsed'); setTimeout(renderCharts, 320); });
$('#chatFab')?.addEventListener('click', () => openChat());
window.addEventListener('hashchange', () => {
  const h = location.hash.replace(/^#\/?/, '');
  if (h.startsWith('report/') && S.view !== 'report') navigate('report', h.split('/')[1]);
});

/* ---------------------------------------------------------------- Boot --- */
(async function boot() {
  try {
    S.boot = await api('/api/bootstrap');
    await refreshChrome();
    const h = location.hash.replace(/^#\/?/, '');
    if (h.startsWith('report/')) navigate('report', h.split('/')[1]);
    else navigate(['history','compare','settings','guide'].includes(h) ? h : 'dashboard');
    // Polling fallback: works even when a proxy blocks Server-Sent Events.
    setInterval(async () => {
      if (S.jobStatus !== 'running' || !S.reportId) return;
      try {
        const st = await api(`/api/reports/${S.reportId}/status`);
        S.progress = st.progress;
        Object.assign(S.agents, st.agents || {});
        if (st.status === 'completed' || st.status === 'failed') {
          S.jobStatus = st.status;
          if (st.status === 'completed' &&
              (S.view === 'dashboard' || S.view === 'history' || S.view === 'report')) {
            S.dashboard = null;
            navigate('report', S.reportId);
          }
          refreshChrome();
        }
        renderMission();
      } catch {}
    }, 3000);
  } catch (e) {
    $('#view').innerHTML = `<div class="card empty">${icon('close')}<h3>Engine unavailable</h3>
      <p class="small">${esc(e.message)}</p><p class="tiny muted">Start the server with <code>uvicorn app.api.server:app --host 0.0.0.0 --port 8000</code></p></div>`;
  }
})();
})();

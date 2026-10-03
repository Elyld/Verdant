/* Verdant v2 — route-aware frontend for the garden journal. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]
  ));
  const fmtDate = (iso) => iso
    ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : '—';
  // Local YYYY-MM-DD for defaulting date inputs. toISOString() is UTC and
  // goes a day back after 7pm Central — this one doesn't.
  const todayLocal = () => {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  };
  const fmtDateTime = (iso) => iso
    ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : '—';
  // Structured amount display: prefers the numeric value+unit, falls back to
  // the legacy free-text column. item: {amount_value, amount_unit, amount}
  // or {amount_used, ...} for fertilization rows.
  const fmtAmount = (item) => {
    const value = item.amount_value;
    const unit = (item.amount_unit || '').trim();
    if (value != null && unit) return `${Number(value)} ${unit}`;
    if (value != null) return `${Number(value)}`;
    return item.amount_used || item.amount || '';
  };
  // Temperature display honoring the user's °F/°C setting (stored Celsius).
  // The setting is cached on first use; pass the resolved unit for tests.
  let _tempUnit = null;
  const tempUnit = async () => {
    if (_tempUnit) return _tempUnit;
    try {
      const s = await api.get('/api/settings');
      _tempUnit = s && s.temperature_unit === 'C' ? 'C' : 'F';
    } catch { _tempUnit = 'F'; }
    return _tempUnit;
  };
  const fmtTemp = (celsius, unit) => {
    if (celsius == null) return '';
    const u = unit || _tempUnit || 'F';
    const v = u === 'C' ? celsius : celsius * 9 / 5 + 32;
    return `${Math.round(v * 10) / 10}°${u}`;
  };

  const api = {
    async request(method, path, { json, form } = {}) {
      const options = { method, headers: {} };
      if (json !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(json);
      } else if (form) {
        options.body = form;
      }
      const response = await fetch(path, options);
      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
          const body = await response.json();
          detail = Array.isArray(body.detail)
            ? body.detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
            : body.detail || detail;
        } catch { /* non-JSON response */ }
        throw new Error(detail);
      }
      return response.status === 204 ? null : response.json();
    },
    get(path) { return this.request('GET', path); },
    post(path, json) { return this.request('POST', path, { json }); },
    put(path, json) { return this.request('PUT', path, { json }); },
    patch(path, json) { return this.request('PATCH', path, { json }); },
    del(path) { return this.request('DELETE', path); },
    upload(path, form) { return this.request('POST', path, { form }); },
  };

  function toast(message, kind = 'info') {
    const host = $('#toasts');
    if (!host) return;
    const tones = {
      info: 'bg-navy-800 text-beige-50 ring-navy-600',
      ok: 'bg-sage-700 text-beige-50 ring-sage-500',
      err: 'bg-red-800 text-beige-50 ring-red-600',
      error: 'bg-red-800 text-beige-50 ring-red-600',
    };
    const el = document.createElement('div');
    el.className = `pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-botanical ring-1 ${tones[kind]}`;
    el.textContent = message;
    host.append(el);
    setTimeout(() => el.remove(), 3800);
  }

  function markdown(source) {
    let output = esc(source || '');
    output = output
      .replace(/^### (.*)$/gm, '<h3>$1</h3>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>')
      .replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return output.split(/\n{2,}/).map((block) => /^<h[1-3]>/.test(block) ? block : `<p>${block.replace(/\n/g, '<br>')}</p>`).join('');
  }

  function setVersion() {
    const version = document.documentElement.dataset.version;
    const target = $('#app-version');
    if (version && target) target.textContent = `v${version}`;
  }

  function setActiveNavigation() {
    const path = window.location.pathname;
    $$('nav a').forEach((link) => {
      const active = link.getAttribute('href') === path;
      if (active) link.setAttribute('aria-current', 'page');
      link.classList.toggle('bg-sage-600', active);
      link.classList.toggle('text-white', active);
    });
  }

  // Canonical nav sections (key, href, icon, label). The mobile tab bar
  // renderer uses this; the Settings chip picker reads it off Verdant.
  const NAV_SECTIONS = [
    { key: 'today', href: '/', icon: '☀️', label: 'Today' },
    { key: 'home', href: '/blog', icon: '📖', label: 'Blog & Stories' },
    { key: 'observations', href: '/observations', icon: '📝', label: 'Garden Logs' },
    { key: 'calendar', href: '/calendar', icon: '📅', label: 'Calendar' },
    { key: 'photos', href: '/photos', icon: '📷', label: 'Photos' },
    { key: 'plants', href: '/plants', icon: '🌿', label: 'Plants' },
    { key: 'seeds', href: '/seeds', icon: '🫘', label: 'Seeds' },
    { key: 'seedlings', href: '/seedlings', icon: '🌱', label: 'Seedlings' },
    { key: 'review', href: '/review', icon: '📊', label: 'Review' },
    { key: 'import', href: '/import', icon: '📥', label: 'Import' },
    { key: 'quick', href: '/quick', icon: '⚡', label: 'Quick Log' },
    { key: 'pantry', href: '/pantry', icon: '🥫', label: 'Pantry' },
    { key: 'costs', href: '/costs', icon: '💰', label: 'Costs' },
    { key: 'pests', href: '/pests', icon: '🐛', label: 'Pests' },
    { key: 'fertilizers', href: '/fertilizers', icon: '🧪', label: 'Fertilizers' },
    { key: 'planner', href: '/planner', icon: '🗺️', label: 'Planner' },
    { key: 'tags', href: '/tags', icon: '🏷️', label: 'Tags' },
    { key: 'agent', href: '/agent', icon: '🌱', label: 'Garden Assistant' },
    { key: 'settings', href: '/settings', icon: '⚙️', label: 'Settings' },
  ];
  const DEFAULT_MOBILE_TABS = ['quick', 'plants', 'calendar', 'planner', 'settings'];
  const MAX_MOBILE_TABS = 5;

  // Parse the mobile_tabs setting (JSON array string). Returns the key list
  // in the user's order, or null when unset/invalid (caller falls back to
  // DEFAULT_MOBILE_TABS). Unknown keys invalidate the whole value.
  function parseMobileTabs(raw) {
    try {
      const arr = JSON.parse(raw || '[]');
      if (!Array.isArray(arr) || !arr.length) return null;
      const valid = new Set(NAV_SECTIONS.map((s) => s.key));
      const seen = new Set();
      const out = [];
      for (const k of arr) {
        if (typeof k !== 'string' || !valid.has(k)) return null;
        if (!seen.has(k)) { seen.add(k); out.push(k); }
      }
      if (!out.length || out.length > MAX_MOBILE_TABS) return null;
      return out;
    } catch { return null; }
  }

  function mobileTabHtml(section) {
    return `<a href="${section.href}" class="mobile-tab flex-1" data-tab="${section.key}">` +
      `<span class="mobile-tab-icon" aria-hidden="true">${section.icon}</span>` +
      `<span class="mobile-tab-label">${esc(section.label)}</span>` +
      `<span class="mobile-tab-dot" aria-hidden="true"></span></a>`;
  }

  async function initMobileNav() {
    // Mobile bottom tab bar (below md). Renders the user's picks from the
    // mobile_tabs setting (tap order), falling back to the defaults; More
    // stays fixed last and opens the bottom sheet with everything else.
    const linksHost = $('#mobile-tab-links');
    const sheet = $('#mobile-sheet');
    if (!linksHost) return;
    let picks = null;
    try {
      const s = await getSettings();
      picks = parseMobileTabs(s && s.mobile_tabs);
    } catch { picks = null; }
    const keys = picks || DEFAULT_MOBILE_TABS.slice();
    const byKey = Object.fromEntries(NAV_SECTIONS.map((s) => [s.key, s]));
    linksHost.innerHTML = keys.map((k) => mobileTabHtml(byKey[k])).join('');
    const grid = $('#mobile-sheet-grid');
    if (grid) {
      const picked = new Set(keys);
      grid.innerHTML = NAV_SECTIONS.filter((s) => !picked.has(s.key)).map((s) =>
        `<a href="${s.href}" class="sheet-link"><span class="text-xl" aria-hidden="true">${s.icon}</span>` +
        `<span>${esc(s.label)}</span></a>`
      ).join('');
    }
    setActiveNavigation(); // mark the freshly rendered tabs
    if (!sheet) return;
    const open = () => {
      sheet.classList.remove('hidden');
      if (document.body && document.body.classList) document.body.classList.add('overflow-hidden');
    };
    const close = () => {
      sheet.classList.add('hidden');
      if (document.body && document.body.classList) document.body.classList.remove('overflow-hidden');
    };
    const moreBtn = $('#mobile-nav-more');
    if (moreBtn) moreBtn.addEventListener('click', open);
    const closeBtn = $('#mobile-sheet-close');
    if (closeBtn) closeBtn.addEventListener('click', close);
    const backdrop = $('#mobile-sheet-backdrop');
    if (backdrop) backdrop.addEventListener('click', close);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !sheet.classList.contains('hidden')) close();
    });
  }

  async function uploadFiles(path, files) {
    if (!files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((file) => form.append('files', file, file.name));
    await api.upload(path, form);
  }

  function wireDraft(form, key, fields) {
    const draft = JSON.parse(localStorage.getItem(key) || '{}');
    fields.forEach((selector) => {
      const input = $(selector);
      if (!input) return;
      if (draft[selector] !== undefined && input.type !== 'file') input.value = draft[selector];
      input.addEventListener('input', () => {
        const next = JSON.parse(localStorage.getItem(key) || '{}');
        next[selector] = input.value;
        localStorage.setItem(key, JSON.stringify(next));
      });
    });
    form.addEventListener('reset', () => localStorage.removeItem(key));
  }

  async function renderStats() {
    const host = $('#stats');
    if (!host) return;
    try {
      const stats = await api.get('/api/stats');
      const cards = [
        ['posts', 'Entries', '📖'], ['observations', 'Observations', '🔍'],
        ['fertilizations', 'Feedings', '🧪'], ['images', 'Photos', '🖼️'],
        ['avg_health', 'Avg health', '💚'],
      ];
      host.innerHTML = cards.map(([key, label, icon]) => `<div class="rounded-xl border border-beige-300 bg-beige-50 px-4 py-3"><dt class="text-xs font-bold uppercase text-navy-500">${icon} ${label}</dt><dd class="mt-1 font-display text-2xl text-sage-700">${esc(stats[key] ?? '—')}</dd></div>`).join('');
    } catch { /* stats are supplementary */ }
  }

  function healthBar(score) {
    const color = score >= 8 ? 'bg-sage-600' : score >= 5 ? 'bg-beige-500' : 'bg-red-600';
    return `<div class="flex items-center gap-2"><div class="h-2 w-16 rounded bg-beige-200"><div class="h-full ${color}" style="width:${score * 10}%"></div></div><b>${score}</b></div>`;
  }

  function plantCard(plant, locationName, badges) {
    const cadence = [
      plant.water_every_days ? `💧 every ${plant.water_every_days}d` : '',
      plant.feed_every_days ? `🧪 every ${plant.feed_every_days}d` : '',
    ].filter(Boolean).join(' · ') || 'No care schedule';
    return `<article class="card cursor-pointer transition hover:shadow-botanical" data-plant-card="${plant.id}" data-open-plant="${plant.id}" tabindex="0" role="button" aria-label="Open ${esc(plant.variety_name)}">
      <div class="plant-cover mb-3 grid h-36 place-items-center overflow-hidden rounded-lg bg-sage-100 text-4xl" data-cover="${plant.id}">🌱</div>
      <div class="flex items-start justify-between gap-2">
        <h3 class="font-display text-lg font-semibold text-navy-800">${esc(plant.variety_name)}</h3>
        <span class="pill">${esc(plant.status || 'Growing')}</span>
      </div>
      <p class="text-sm text-navy-500">${esc(plant.species_type || '')}${plant.species_type && locationName ? ' · ' : ''}${esc(locationName || '')}</p>
      <p class="mt-1 text-xs text-navy-400">${esc(cadence)}</p>
      ${badges ? `<div class="mt-2 flex flex-wrap gap-1">${badges}</div>` : ''}
    </article>`;
  }

  async function initFrost() {
    // Frost countdown pill in the site header; hidden unless FIRST_FROST_DATE is set.
    const pill = $('#frost-countdown');
    if (!pill) return;
    try {
      const data = await api.get('/api/stats/frost');
      if (data && data.days_until != null && data.days_until >= 0) {
        pill.textContent = '\u2744\uFE0F ' + data.days_until + 'd to first frost';
        pill.classList.remove('hidden');
      }
    } catch { /* the countdown is decorative; never break the page */ }
  }

  async function initNoaaAlerts() {
    // ⚠️ pill in the weather ribbon when National Weather Service alerts are
    // active for the garden point; clicking toggles a small panel listing
    // each alert. Decorative; never breaks the page.
    const ribbon = $('#weather-ribbon');
    const inner = $('#weather-ribbon-inner');
    if (!ribbon || !inner) return;
    let data;
    try {
      data = await api.get('/api/weather/noaa-alerts');
    } catch { return; }
    const alerts = (data && data.ok && Array.isArray(data.alerts)) ? data.alerts : [];
    if (!alerts.length) return;
    const rank = { Extreme: 0, Severe: 1, Moderate: 2, Minor: 3, Unknown: 4 };
    const top = alerts.reduce((a, b) => (rank[a.severity] ?? 4) <= (rank[b.severity] ?? 4) ? a : b);
    const tint = {
      Extreme: 'bg-red-700 text-red-50 ring-red-500',
      Severe: 'bg-red-700 text-red-50 ring-red-500',
      Moderate: 'bg-amber-400 text-navy-900 ring-amber-300',
      Minor: 'bg-sky-600 text-sky-50 ring-sky-500',
    }[top.severity] || 'bg-navy-600 text-beige-100 ring-navy-500';
    const fmtWhen = (iso) => {
      if (!iso) return '';
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? '' : d.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    };
    const panel = document.createElement('div');
    panel.id = 'noaa-panel';
    panel.className = 'hidden w-full border-t border-navy-700/50 px-4 py-2 sm:px-6 lg:px-8';
    panel.innerHTML = alerts.map((a) => {
      const when = [fmtWhen(a.onset), fmtWhen(a.ends)].filter(Boolean).join(' → ');
      return `<div class="mb-2 rounded-lg bg-navy-900/60 px-3 py-2 ring-1 ring-navy-700 last:mb-0">` +
        `<p class="font-semibold text-beige-100">${esc(a.event)}${when ? ` <span class="font-normal text-beige-300">· ${esc(when)}</span>` : ''}</p>` +
        (a.headline ? `<p class="text-beige-200">${esc(a.headline)}</p>` : '') +
        (a.description ? `<p class="mt-1 text-beige-300/90">${esc(a.description)}</p>` : '') +
        `</div>`;
    }).join('');
    const pill = document.createElement('button');
    pill.type = 'button';
    pill.id = 'noaa-pill';
    pill.className = `rounded-full px-2.5 py-0.5 font-semibold ring-1 ${tint}`;
    pill.setAttribute('aria-expanded', 'false');
    pill.innerHTML = `⚠️ ${esc(top.event)}${alerts.length > 1 ? ` +${alerts.length - 1}` : ''}`;
    pill.addEventListener('click', () => {
      const open = panel.classList.toggle('hidden');
      pill.setAttribute('aria-expanded', String(!open));
    });
    inner.appendChild(pill);
    ribbon.appendChild(panel);
    ribbon.classList.remove('hidden');
  }

  async function initWeatherRibbon() {
    // Slim site-wide weather ribbon below the header; rendered from the
    // cached forecast endpoint. Stays hidden unless garden coordinates are
    // configured — no nagging (the ribbon is decorative, never breaks the page).
    const ribbon = $('#weather-ribbon');
    const inner = $('#weather-ribbon-inner');
    if (!ribbon || !inner) return;
    try {
      const fc = await api.get('/api/weather/forecast');
      if (!fc || !fc.ok || !fc.forecast || !fc.forecast.current) return;
      const unit = fc.temp_unit === 'C' ? 'C' : 'F';
      const t = (v) => v == null ? '—' : `${Math.round(v)}°${unit}`;
      const cur = fc.forecast.current;
      const days = fc.forecast.daily || [];
      const tonight = days[0] ? t(days[0].tmin_c ?? days[0].tmin_f) : '—';
      const tm = days[1] || days[0] || {};
      const rain = tm.precip_prob != null ? `${tm.precip_prob}%` : '—';
      const gust = tm.gust_mph != null ? `${Math.round(tm.gust_mph)} mph` : '—';
      let asOf = '';
      if (fc.forecast.as_of) {
        const d = new Date(fc.forecast.as_of);
        if (!Number.isNaN(d.getTime())) asOf = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      }
      inner.innerHTML =
        `<span class="font-semibold">🌤️ ${t(cur.temp_c ?? cur.temp_f)} ${esc(cur.summary || '')}</span>` +
        `<span class="text-beige-300">·</span><span>🌙 Tonight ${tonight}</span>` +
        `<span class="text-beige-300">·</span><span>☀️ Tomorrow ${t(tm.tmax_c ?? tm.tmax_f)}</span>` +
        `<span class="text-beige-300">·</span><span>💧 ${rain}</span>` +
        `<span class="text-beige-300">·</span><span>💨 ${gust}</span>` +
        (asOf ? `<span class="ml-auto text-beige-300/80">as of ${asOf}</span>` : '');
      ribbon.classList.remove('hidden');
    } catch { /* decorative; never break the page */ }
    // Alert pill appends after the forecast spans (or alone when the
    // forecast is down) — chained, not concurrent, so innerHTML can't wipe it.
    await initNoaaAlerts();
  }

  const inits = [];
  const lateInits = [];
  function onBoot(fn) { inits.push(fn); }
  function onBootLate(fn) { lateInits.push(fn); }

  // Cached app settings (week_start, default_weight_unit, slideshow_interval,
  // confirm_water_all, ...). Fetched once per page load; never rejects.
  let _settings = null;
  async function getSettings() {
    if (_settings) return _settings;
    try {
      _settings = await api.get('/api/settings');
    } catch (error) {
      _settings = {};
    }
    return _settings;
  }

  function boot() {
    setVersion();
    setActiveNavigation();
    const reloaders = {};
    for (const fn of inits) Object.assign(reloaders, fn() || {});
    for (const fn of lateInits) fn(reloaders);
    initFrost();
    initWeatherRibbon();
    initMobileNav();
  }

  globalThis.Verdant = {
    $, $$, esc, fmtDate, fmtDateTime, fmtAmount, tempUnit, fmtTemp, api, toast, markdown,
    uploadFiles, wireDraft, renderStats, healthBar, plantCard, onBoot, onBootLate, todayLocal,
    getSettings, NAV_SECTIONS, DEFAULT_MOBILE_TABS, MAX_MOBILE_TABS, parseMobileTabs,
  };

  document.addEventListener('DOMContentLoaded', boot);
})();

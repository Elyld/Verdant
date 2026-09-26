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

  const inits = [];
  const lateInits = [];
  function onBoot(fn) { inits.push(fn); }
  function onBootLate(fn) { lateInits.push(fn); }

  function boot() {
    setVersion();
    setActiveNavigation();
    const reloaders = {};
    for (const fn of inits) Object.assign(reloaders, fn() || {});
    for (const fn of lateInits) fn(reloaders);
    initFrost();
  }

  globalThis.Verdant = {
    $, $$, esc, fmtDate, fmtDateTime, fmtAmount, tempUnit, fmtTemp, api, toast, markdown,
    uploadFiles, wireDraft, renderStats, healthBar, plantCard, onBoot, onBootLate,
  };

  document.addEventListener('DOMContentLoaded', boot);
})();

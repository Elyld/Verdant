/* Planner weather strip, garden alerts, yield heatmap, and companion hints. */
'use strict';
const fs = require('fs');
const path = require('path');

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

function makeEl() {
  const classes = new Set();
  const listeners = {};
  const children = [];
  const el = {
    style: {},
    dataset: {},
    _attrs: {},
    _listeners: listeners,
    _children: children,
    checked: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    setPointerCapture: () => {},
    focus: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { children.push(c); return c; },
    append: () => {},
    getBoundingClientRect: () => ({ width: 800, height: 500, left: 0, top: 0 }),
    textContent: '',
    value: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
['panel-planner', 'planner-canvas', 'planner-3d', 'planner-empty',
 'planner-2d-hint', 'planner-3d-hint',
 'view-2d', 'view-3d', 'heatmap-toggle', 'heatmap-legend',
 'weather-strip', 'weather-alerts',
 'planner-year', 'planner-copy', 'planner-add',
 'grid-cols', 'grid-rows', 'grid-apply',
 'rotation-banner', 'rotation-list', 'rotation-dismiss',
 'container-modal', 'container-modal-title', 'container-submit',
 'container-delete', 'container-id', 'container-name', 'container-kind',
 'container-grid-w', 'container-grid-h',
 'container-size', 'container-height', 'container-volume-value', 'container-volume-unit',
 'container-location', 'container-plantings', 'companion-hints',
 'container-plant-add', 'container-plant-add-btn', 'container-soil',
 'container-close', 'container-cancel', 'container-form',
 'copy-modal', 'copy-from', 'copy-to-label', 'copy-go', 'copy-cancel',
 'toasts', 'app-version',
].forEach((id) => { named[`#${id}`] = makeEl(); });
named['#planner-3d'].classList.add('hidden');
named['#planner-3d-hint'].classList.add('hidden');
named['#weather-strip'].classList.add('hidden');
named['#heatmap-legend'].classList.add('hidden');

global.document = {
  readyState: 'complete',
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
};
global.window = { location: { pathname: '/planner', origin: 'http://localhost:3119' }, addEventListener: () => {}, confirm: () => true };
global.confirm = () => true;
global.location = { search: '', origin: 'http://localhost:3119' };

global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  let resp = {};
  if (url === '/api/containers/grid') resp = { cols: 24, rows: 16 };
  else if (url.startsWith('/api/containers/plantings')) resp = [
    { id: 41, container_id: 12, plant_id: 5, variety_name: 'Sungold', species_type: 'Solanum lycopersicum', family_genus: 'Solanaceae', season_year: 2026, slot: 0, notes: '' },
    { id: 42, container_id: 12, plant_id: 6, variety_name: 'Genovese Basil', species_type: 'Ocimum basilicum', family_genus: 'Lamiaceae', season_year: 2026, slot: 1, notes: '' },
  ];
  else if (url.startsWith('/api/containers/rotation-warnings')) resp = [];
  else if (url === '/api/containers/years') resp = [2026, 2025];
  else if (url === '/api/plants/') resp = [
    { id: 5, variety_name: 'Sungold', species_type: 'Solanum lycopersicum', family_genus: 'Solanaceae' },
    { id: 6, variety_name: 'Genovese Basil', species_type: 'Ocimum basilicum', family_genus: 'Lamiaceae' },
  ];
  else if (url === '/api/locations/') resp = [];
  else if (url.startsWith('/api/containers/yield-map')) resp = { year: 2025, unit: 'oz', totals: { 'Tomato Bed': 48.0, 'Side Pot': 6.0 } };
  else if (url === '/api/weather/forecast') resp = {
    ok: true, temp_unit: 'F',
    forecast: {
      as_of: '2026-09-26T16:50',
      current: { temp_f: 78, summary: 'Partly cloudy' },
      hourly: [], daily: [{ date: '2026-09-26', tmin_f: 62 }, { date: '2026-09-27', tmax_f: 88, precip_prob: 20, gust_mph: 18 }],
    },
  };
  else if (url === '/api/weather/alerts') resp = {
    ok: true, temp_unit: 'F', as_of: '2026-09-26T16:50',
    alerts: [{ level: 'warn', icon: '🥶', title: 'Frost risk — low of 30°F', detail: 'Cover the peppers.' }],
  };
  else if (url === '/static/data/companions.json') resp = [
    { a: 'tomato', b: 'basil', relation: 'good', note: 'Classic pairing.', source: 'Iowa State Univ. Extension' },
    { a: 'bean', b: 'garlic', relation: 'bad', note: 'Alliums inhibit beans.', source: 'Iowa State Univ. Extension' },
  ];
  else if (url.startsWith('/api/containers/') && url.includes('year=')) resp = [
    { id: 12, name: 'Tomato Bed', kind: 'raised bed', grid_x: 2, grid_y: 2, grid_w: 4, grid_h: 4, season_year: 2026 },
    { id: 13, name: 'Side Pot', kind: 'pot', grid_x: 8, grid_y: 2, grid_w: 1, grid_h: 1, season_year: 2026 },
  ];
  else if (method !== 'GET') resp = { id: 99 };
  return { ok: true, status: 200, json: async () => resp };
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
  api: {
    get: (p) => fetch(p).then((r) => r.json()),
    post: (p, j) => fetch(p, { method: 'POST', body: JSON.stringify(j) }).then((r) => r.json()),
    patch: (p, j) => fetch(p, { method: 'PATCH', body: JSON.stringify(j) }).then((r) => r.json()),
    del: (p) => fetch(p, { method: 'DELETE' }).then((r) => r.json()),
  },
  toast: () => {},
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require('/home/hatch/workspace/verdant/app/static/js/planner.js');
  await tick(50);

  const strip = named['#weather-strip'];
  check('weather strip shown when forecast ok', !strip.classList.contains('hidden') && strip.classList.contains('flex'));
  check('strip shows current temp + summary', strip.innerHTML.includes('78°F') && strip.innerHTML.includes('Partly cloudy'));
  check('strip shows tonight/tomorrow', strip.innerHTML.includes('Tonight 62°F') && strip.innerHTML.includes('Tomorrow 88°F'));
  check('strip shows rain + wind', strip.innerHTML.includes('20%') && strip.innerHTML.includes('18 mph'));

  const alertsBox = named['#weather-alerts'];
  check('weather alert card rendered', alertsBox.innerHTML.includes('Frost risk'));
  check('alert card carries warn tone', alertsBox.innerHTML.includes('bg-amber-50'));

  // yield heatmap toggle
  // NOTE: the stub's querySelectorAll never removes cards, so grab the newest render.
  const canvas = named['#planner-canvas'];
  const bedCard = () => canvas._children.filter((c) => c.dataset && c.dataset.containerId === 12).pop();
  fire(named['#heatmap-toggle'], 'click');
  await tick(50);
  check('heatmap legend names the past season', named['#heatmap-legend'].innerHTML.includes('2025') || named['#heatmap-legend'].textContent.includes('2025'));
  check('heavy container tinted more than light one',
    bedCard() && bedCard().style.backgroundColor && bedCard().style.backgroundColor.includes('rgba(217, 119, 6'));
  check('heatmap shows oz on card', bedCard() && bedCard().innerHTML.includes('48 oz'));
  fire(named['#heatmap-toggle'], 'click');
  await tick(50);
  check('heatmap off hides legend', named['#heatmap-legend'].classList.contains('hidden'));
  check('heatmap off clears tint', !bedCard().style.backgroundColor);

  // companion hints in the container modal
  fire(bedCard(), 'click');
  await tick(20);
  const hints = named['#companion-hints'].innerHTML;
  check('companion hint shown for tomato x basil', hints.includes('tomato × basil') && hints.includes('🌱'));
  check('no false bad-pair hint', !hints.includes('⚠️'));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

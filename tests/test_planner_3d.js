/* Planner 3D / new-kind checks: arch + pallet cards render their icons,
 * and the 3D toggle degrades gracefully when the Three.js CDN can't load
 * (node has no document.head, so the script load must fail cleanly).
 */
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
 'view-2d', 'view-3d',
 'planner-year', 'planner-copy', 'planner-add',
 'grid-cols', 'grid-rows', 'grid-apply',
 'rotation-banner', 'rotation-list', 'rotation-dismiss',
 'container-modal', 'container-modal-title', 'container-submit',
 'container-delete', 'container-id', 'container-name', 'container-kind',
 'container-grid-w', 'container-grid-h',
 'container-size', 'container-volume-value', 'container-volume-unit',
 'container-location', 'container-plantings',
 'container-plant-add', 'container-plant-add-btn', 'container-soil',
 'container-close', 'container-cancel', 'container-form',
 'copy-modal', 'copy-from', 'copy-to-label', 'copy-go', 'copy-cancel',
 'toasts', 'app-version',
].forEach((id) => { named[`#${id}`] = makeEl(); });
// mirror the template's initial classes: 3D view starts hidden
named['#planner-3d'].classList.add('hidden');
named['#planner-3d-hint'].classList.add('hidden');

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

const seenToasts = [];
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  let resp = {};
  if (url === '/api/containers/grid') resp = { cols: 24, rows: 16 };
  else if (url.startsWith('/api/containers/plantings')) resp = [
    { id: 31, container_id: 12, plant_id: 5, variety_name: 'Kentucky Wonder', season_year: 2026, slot: 0, notes: '' },
  ];
  else if (url.startsWith('/api/containers/rotation-warnings')) resp = [];
  else if (url === '/api/containers/years') resp = [2026];
  else if (url === '/api/plants/') resp = [{ id: 5, variety_name: 'Kentucky Wonder' }];
  else if (url === '/api/locations/') resp = [];
  else if (url.startsWith('/api/containers/') && url.includes('year=')) resp = [
    { id: 12, name: 'Bean Arch', kind: 'arch', grid_x: 2, grid_y: 2, grid_w: 4, grid_h: 8, season_year: 2026 },
    { id: 13, name: 'Pallet Bin', kind: 'pallet', grid_x: 8, grid_y: 2, grid_w: 4, grid_h: 3, season_year: 2026 },
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
  toast: (m) => seenToasts.push(String(m)),
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require('/home/hatch/workspace/verdant/app/static/js/planner.js');
  await tick(50);

  const canvas = named['#planner-canvas'];
  const archCard = canvas._children.find((c) => c.dataset && c.dataset.containerId === 12);
  const palletCard = canvas._children.find((c) => c.dataset && c.dataset.containerId === 13);
  check('arch card rendered', !!archCard);
  check('arch card shows bridge icon', archCard && archCard.innerHTML.includes('🌉'));
  check('arch card spans 4x8 cells', archCard && archCard.style.gridColumn === '3 / span 4' && archCard.style.gridRow === '3 / span 8');
  check('pallet card rendered', !!palletCard);
  check('pallet card shows wood icon', palletCard && palletCard.innerHTML.includes('🪵'));
  check('arch card shows its plant', archCard && archCard.innerHTML.includes('Kentucky Wonder'));

  // view toggle exists, starts in 2D
  check('2D button active initially', named['#view-2d'].className.includes('bg-sage-200'));
  check('3D container hidden initially', named['#planner-3d'].classList.contains('hidden'));

  // 3D toggle with no CDN available: must toast and stay in 2D, not throw
  fire(named['#view-3d'], 'click');
  await tick(50);
  check('3D load failure toasts', seenToasts.some((t) => t.includes('Could not load the 3D library')));
  check('stays in 2D after 3D failure', !named['#planner-canvas'].classList.contains('hidden'));
  check('3D container still hidden after failure', named['#planner-3d'].classList.contains('hidden'));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

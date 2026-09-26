/* v2.10.0 JS checks: fertilizers, seed catalog tabs, tag manager, planner canvas.
 * Drives the four new page scripts with a stub DOM:
 *  1. fertilizers.js renders the shelf and posts a JSON create payload
 *  2. seed_catalog.js switches tabs from ?tab=catalog and opens the add modal from ?add=1
 *  3. tags.js swaps target fields per action and posts the right tag payload
 *  4. planner.js renders containers at x/y and PATCHes the new position after a drag
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
    select: () => {},
    reset: () => {},
    click: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { children.push(c); return c; },
    append: () => {},
    closest: () => null,
    matches: () => false,
    scrollIntoView: () => {},
    getBoundingClientRect: () => ({ width: 800, height: 500, left: 0, top: 0 }),
    textContent: '',
    value: '',
    src: '',
    disabled: false,
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
['panel-fertilizers', 'fert-products', 'fert-products-empty', 'fert-product-form',
 'fert-prod-name', 'fert-prod-npk', 'fert-prod-best', 'fert-prod-notes',
 'catalog-grid', 'catalog-empty', 'catalog-search', 'catalog-category', 'catalog-add',
 'seed-tab-sources', 'seed-tab-catalog', 'seed-vendor-filter', 'seed-add-toggle',
 'seed-tabbtn-sources', 'seed-tabbtn-catalog',
 'packet-modal', 'packet-modal-title', 'packet-submit', 'packet-id', 'packet-variety',
 'packet-species', 'packet-category', 'packet-year', 'packet-vendor', 'packet-vendor-url',
 'packet-qty', 'packet-notes', 'packet-photo', 'packet-form', 'packet-close', 'packet-cancel',
 'packet-categories',
 'panel-tags', 'tag-list', 'tag-empty', 'tag-form', 'tag-label', 'tag-action',
 'tag-target-wrap', 'tag-target', 'tag-target-lbl', 'tag-text-wrap', 'tag-text',
 'tag-text-lbl', 'tag-action-hint',
 'panel-planner', 'planner-canvas', 'planner-empty', 'planner-year', 'planner-copy',
 'planner-add', 'container-modal', 'container-modal-title', 'container-submit',
 'container-delete', 'container-id', 'container-name', 'container-kind',
 'container-size', 'container-location', 'container-plant', 'container-soil',
 'container-close', 'container-cancel', 'container-form',
 'copy-modal', 'copy-from', 'copy-to-label', 'copy-go', 'copy-cancel',
 'toasts', 'app-version',
].forEach((id) => { named[`#${id}`] = makeEl(); });

global.document = {
  readyState: 'complete',
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
};
global.window = { location: { pathname: '/', origin: 'http://localhost:3119' }, confirm: () => true };
global.location = { search: '?tab=catalog&add=1', origin: 'http://localhost:3119' };
Object.defineProperty(global, 'navigator', { value: { clipboard: { writeText: async () => {} } }, configurable: true });
global.FormData = function () { this.append = () => {}; };

const seenToasts = [];
const calls = { post: [], patch: [], del: [] };
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  const body = options && options.body ? JSON.parse(options.body) : null;
  if (method === 'POST') calls.post.push({ url, body });
  if (method === 'PATCH') calls.patch.push({ url, body });
  if (method === 'DELETE') calls.del.push({ url });
  let resp = {};
  if (url === '/api/fertilizers/') resp = [{ id: 1, name: 'Fish emulsion', npk_ratio: '5-1-1' }];
  else if (url === '/api/seed-packets/') resp = [
    { id: 1, variety_name: 'Fatalii', category: 'Pepper', year_acquired: 2025, photo_path: '', vendor_id: null },
  ];
  else if (url === '/api/seed-sources/') resp = [{ id: 2, source: 'Territorial', variety: '' }];
  else if (url === '/api/plants/') resp = [{ id: 5, variety_name: 'Habanero', status: 'Growing' }];
  else if (url === '/api/locations/') resp = [{ id: 3, name: 'Patio' }];
  else if (url === '/api/tags/') resp = [{ id: 9, code: 'abc123', label: 'Neem bottle', action: 'pest', target_text: 'Neem oil', tap_count: 2, last_tapped_at: '2026-09-25T10:00:00' }];
  else if (url.startsWith('/api/containers/') && url.includes('year=')) resp = [
    { id: 11, name: 'Grow bag 1', kind: 'grow bag', size: '10 gal', x: 20, y: 30, plant_id: 5, season_year: 2026 },
  ];
  else if (url === '/api/containers/years') resp = [2026];
  else if (method !== 'GET') resp = { id: 99 };
  return { ok: true, status: method === 'POST' ? 201 : 200, json: async () => resp };
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
    upload: (p) => fetch(p, { method: 'POST', body: '{}' }).then((r) => r.json()),
  },
  toast: (m) => seenToasts.push(String(m)),
  fmtDate: (s) => s,
  fmtDateTime: (s) => s,
  markdown: (s) => s,
  uploadFiles: async () => {},
  wireDraft: () => {},
  renderStats: async () => {},
  healthBar: () => '',
  plantCard: () => '',
  onBoot: (fn) => {},
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));
const JS = (f) => path.join('/home/hatch/workspace/verdant/app/static/js', f);

(async () => {
  // ---- fertilizers.js ----
  require(JS('fertilizers.js'));
  await tick(30);
  check('fertilizer shelf renders', named['#fert-products'].innerHTML.includes('Fish emulsion'));
  named['#fert-prod-name'].value = 'Cal-Mag';
  named['#fert-prod-npk'].value = '2-0-0';
  fire(named['#fert-product-form'], 'submit', { preventDefault: () => {}, target: named['#fert-product-form'] });
  await tick(30);
  const fertPost = calls.post.find((c) => c.url === '/api/fertilizers/');
  check('fertilizer create posts JSON body', fertPost && fertPost.body.name === 'Cal-Mag' && fertPost.body.npk_ratio === '2-0-0');
  check('fertilizer toast confirms', seenToasts.some((t) => t.includes('Fertilizer added')));

  // ---- seed_catalog.js (?tab=catalog&add=1) ----
  require(JS('seed_catalog.js'));
  await tick(30);
  check('catalog tab shown from query param', named['#seed-tab-catalog'].classList.contains('hidden') === false);
  check('sources tab hidden', named['#seed-tab-sources'].classList.contains('hidden') === true);
  check('packet grid renders', named['#catalog-grid'].innerHTML.includes('Fatalii'));
  check('add modal opens from ?add=1', named['#packet-modal'].classList.contains('hidden') === false);
  check('vendor select populated', named['#packet-vendor'].innerHTML.includes('Territorial'));

  // ---- tags.js ----
  require(JS('tags.js'));
  await tick(30);
  check('tag list renders with /t/ URL', named['#tag-list'].innerHTML.includes('/t/abc123'));
  named['#tag-action'].value = 'fertilize';
  fire(named['#tag-action'], 'change');
  await tick(30);
  check('fertilize action shows fertilizer picker', named['#tag-target'].innerHTML.includes('Fish emulsion'));
  check('hint explains the action', named['#tag-action-hint'].textContent.includes('bottle'));
  named['#tag-action'].value = 'pest';
  fire(named['#tag-action'], 'change');
  check('pest action shows text field', named['#tag-text-wrap'].classList.contains('hidden') === false);
  named['#tag-label'].value = 'Neem bottle 2';
  named['#tag-text'].value = 'Neem oil';
  fire(named['#tag-form'], 'submit', { preventDefault: () => {}, target: named['#tag-form'] });
  await tick(30);
  const tagPost = calls.post.find((c) => c.url === '/api/tags/');
  check('tag create posts action + target_text', tagPost && tagPost.body.action === 'pest' && tagPost.body.target_text === 'Neem oil');

  // ---- planner.js ----
  require(JS('planner.js'));
  await tick(30);
  const canvas = named['#planner-canvas'];
  const card = canvas._children.find((c) => c.dataset && c.dataset.containerId === 11);
  check('container card rendered on canvas', !!card);
  check('card positioned at x/y', card && card.style.left === '20%' && card.style.top === '30%');
  check('card shows plant name', card && card.innerHTML.includes('Habanero'));
  // Simulate a drag: pointerdown at (160,150) -> move to (320,300) on an 800x500 canvas.
  fire(card, 'pointerdown', { preventDefault: () => {}, clientX: 160, clientY: 150, pointerId: 1 });
  fire(card, 'pointermove', { clientX: 320, clientY: 300 });
  fire(card, 'pointerup', {});
  await tick(30);
  const dragPatch = calls.patch.find((c) => c.url === '/api/containers/11');
  check('drag PATCHes new position', dragPatch && dragPatch.body.x === 40 && dragPatch.body.y === 60);
  fire(named['#planner-add'], 'click');
  check('add button opens container modal', named['#container-modal'].classList.contains('hidden') === false);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

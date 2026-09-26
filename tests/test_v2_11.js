/* v2.11.0: packet back photo (front/back flip) — DOM harness for seed_catalog.js. */
const path = require('path');

let failures = 0;
const seenToasts = [];
function check(name, ok) {
  if (ok) console.log(`ok   - ${name}`);
  else { failures++; console.log(`FAIL - ${name}`); }
}

const named = {};
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
    files: [],
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    focus: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { children.push(c); return c; },
    append: () => {},
    closest: () => null,
    textContent: '',
    value: '',
    innerHTML: '',
  };
  return el;
}

['catalog-grid', 'catalog-empty', 'catalog-search', 'catalog-category', 'catalog-add',
 'seed-tab-sources', 'seed-tab-catalog', 'seed-vendor-filter', 'seed-add-toggle',
 'seed-tabbtn-sources', 'seed-tabbtn-catalog',
 'packet-modal', 'packet-modal-title', 'packet-submit', 'packet-id', 'packet-variety',
 'packet-species', 'packet-category', 'packet-year', 'packet-vendor', 'packet-vendor-list',
 'packet-vendor-url', 'packet-qty', 'packet-notes', 'packet-photo', 'packet-photo-back',
 'packet-form', 'packet-close', 'packet-cancel', 'packet-categories', 'catalog-from-sources',
].forEach((id) => { named['#' + id] = makeEl(); });

global.window = { location: { pathname: '/seeds', origin: 'http://localhost:3119' }, confirm: () => true };
global.location = { search: '?tab=catalog', origin: 'http://localhost:3119' };
global.document = {
  readyState: 'complete',
  addEventListener: () => {},
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
};
global.confirm = () => true;
global.FormData = class { constructor() { this.fields = {}; } append(k, v) { this.fields[k] = v; } };

const calls = { post: [], patch: [], del: [] };
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  const body = options && options.body && typeof options.body === 'string' ? JSON.parse(options.body) : null;
  if (method === 'POST') calls.post.push({ url, body });
  if (method === 'PATCH') calls.patch.push({ url, body });
  if (method === 'DELETE') calls.del.push({ url });
  let resp = {};
  if (url === '/api/seed-packets/') resp = method === 'GET' ? [
    { id: 1, variety_name: 'Fatalii', category: 'Pepper', photo_path: '/uploads/seed-packets/1/a.png', photo_back_path: '/uploads/seed-packets/1/b.png', vendor_name: '' },
    { id: 2, variety_name: 'Sungold', category: 'Tomato', photo_path: '/uploads/seed-packets/2/c.png', photo_back_path: '', vendor_name: '' },
  ] : { id: 99 };
  else if (url === '/api/seed-sources/') resp = [];
  else if (url === '/api/seed-packets/vendors') resp = [];
  else if (url === '/api/seed-packets/categories') resp = [];
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
  require(JS('seed_catalog.js'));
  await tick(30);
  const grid = named['#catalog-grid'].innerHTML;

  check('card with back photo renders flip button', grid.includes('data-flip'));
  check('flip button carries front and back URLs',
    grid.includes('data-front="/uploads/seed-packets/1/a.png"') &&
    grid.includes('data-back="/uploads/seed-packets/1/b.png"'));
  const flipCount = (grid.match(/data-flip/g) || []).length;
  check('card without back photo has no flip button', flipCount === 1);

  // Simulate the flip toggle with hand-built fakes.
  const fakeImg = { src: '/uploads/seed-packets/1/a.png', dataset: { side: 'front' } };
  const fakeLightboxBtn = { dataset: { lightbox: '/uploads/seed-packets/1/a.png' } };
  const fakeWrap = { querySelector: (s) => (s === '[data-packet-img]' ? fakeImg : fakeLightboxBtn) };
  const fakeFlip = {
    dataset: { front: '/uploads/seed-packets/1/a.png', back: '/uploads/seed-packets/1/b.png' },
    textContent: '⇄ Back',
    closest: (s) => (s === '.relative' ? fakeWrap : null),
  };
  const fakeTarget = { closest: (s) => (s === '[data-flip]' ? fakeFlip : null) };
  fire(named['#catalog-grid'], 'click', { target: fakeTarget, stopPropagation: () => {} });
  check('flip swaps img to back photo', fakeImg.src === '/uploads/seed-packets/1/b.png' && fakeImg.dataset.side === 'back');
  check('flip updates lightbox target + button label', fakeLightboxBtn.dataset.lightbox === '/uploads/seed-packets/1/b.png' && fakeFlip.textContent === '⇄ Front');
  fire(named['#catalog-grid'], 'click', { target: fakeTarget, stopPropagation: () => {} });
  check('flip back restores front photo', fakeImg.src === '/uploads/seed-packets/1/a.png' && fakeFlip.textContent === '⇄ Back');

  // Submit with a back photo file uploads it with ?side=back.
  named['#packet-variety'].value = 'Fatalii';
  named['#packet-id'].value = '';
  named['#packet-year'].value = '2025';
  named['#packet-photo'].files = [];
  named['#packet-photo-back'].files = [{ name: 'back.png' }];
  fire(named['#packet-form'], 'submit', { preventDefault: () => {} });
  await tick(50);
  check('back photo uploads with ?side=back',
    calls.post.some((c) => c.url === '/api/seed-packets/99/photo?side=back'));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();

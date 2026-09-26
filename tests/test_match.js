/* Regression test: /match photo<->plant workflow + Immich merge-duplicates button.
 * Drives match.js and immich.js with a stub DOM:
 *  1. Match page boots: albums + plants load, first photo renders with metadata
 *  2. Assign without a plant warns; assign with a plant PATCHes and advances
 *  3. Bulk button groups same-day photos and posts a bulk assign
 *  4. Merge duplicates button posts and toasts the result
 */
'use strict';
const fs = require('fs');
const path = require('path');

function makeEl() {
  const classes = new Set();
  const listeners = {};
  const el = {
    style: {},
    dataset: {},
    _attrs: {},
    _listeners: listeners,
    checked: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
      replace: (o, n) => { classes.delete(o); classes.add(n); },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: (sel) => (namedAll[sel] || []).slice(),
    appendChild: (c) => c,
    append: () => {},
    closest: () => null,
    matches: () => false,
    textContent: '',
    value: '',
    src: '',
    alt: '',
    disabled: false,
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
const namedAll = {};
['match-album', 'match-plant', 'match-unassigned', 'match-reload', 'match-progress',
 'match-empty', 'match-workspace', 'match-photo', 'match-caption', 'match-meta',
 'match-tags', 'match-counter', 'match-prev', 'match-next', 'match-assign',
 'match-skip', 'match-unassign', 'match-bulk', 'match-bulk-hint',
 'immich-merge', 'immich-section', 'immich-album-select', 'immich-import',
 'toasts', 'app-version'].forEach((id) => {
  named[`#${id}`] = makeEl();
});
named['#match-empty'].classList.add('hidden');
named['#match-workspace'].classList.add('hidden');
named['#match-unassigned'].checked = true;
namedAll['#immich-merge'] = [named['#immich-merge']];
namedAll['#immich-section'] = [named['#immich-section']];
namedAll['#immich-album-select'] = [named['#immich-album-select']];
namedAll['#immich-import'] = [named['#immich-import']];

const docListeners = {};
global.document = {
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: (sel) => (namedAll[sel] || []).slice(),
  addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
  dispatchEvent: (ev) => { (docListeners[ev.type] || []).forEach((fn) => fn(ev)); return true; },
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
};
global.window = { location: { pathname: '/match' }, confirm: () => true };
global.location = { search: '' };
global.CustomEvent = function (type, opts) { this.type = type; this.detail = (opts && opts.detail) || null; };
global.Image = function () { this.src = ''; };
const store = {};
global.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

const IMAGES = [
  { id: 101, file_path: '/uploads/albums/7/p0.jpg', title: 'p0.jpg', original_name: 'p0.jpg',
    taken_at: '2026-09-20T10:00:00', camera_make: 'Google', camera_model: 'Pixel',
    latitude: 39.1, longitude: -94.5, tags: 'pepper', plant_id: null, plant_variety: null },
  { id: 102, file_path: '/uploads/albums/7/p1.jpg', title: 'p1.jpg', original_name: 'p1.jpg',
    taken_at: '2026-09-20T10:05:00', camera_make: '', camera_model: '',
    latitude: null, longitude: null, tags: '', plant_id: null, plant_variety: null },
  { id: 103, file_path: '/uploads/albums/7/p2.jpg', title: 'p2.jpg', original_name: 'p2.jpg',
    taken_at: '2026-09-21T10:00:00', camera_make: '', camera_model: '',
    latitude: null, longitude: null, tags: '', plant_id: 5, plant_variety: 'Habanero' },
];
const calls = { patch: [], bulk: [], merge: 0 };
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  const body = options && options.body ? JSON.parse(options.body) : null;
  let resp = {};
  if (url === '/api/albums') resp = [{ id: 7, name: 'Plants 2025', images: IMAGES }];
  else if (url === '/api/plants/') resp = [
    { id: 5, variety_name: 'Habanero' },
    { id: 6, variety_name: 'Sungold' },
  ];
  else if (url.startsWith('/api/album-images/') && method === 'GET') {
    resp = url.includes('unassigned_only=true') ? IMAGES.filter((i) => !i.plant_id) : IMAGES;
  } else if (url === '/api/album-images/101' && method === 'PATCH') {
    calls.patch.push(body);
    resp = { ...IMAGES[0], plant_id: body.plant_id, plant_variety: 'Sungold' };
  } else if (url === '/api/album-images/bulk-assign' && method === 'POST') {
    calls.bulk.push(body);
    resp = { updated: body.image_ids.length };
  } else if (url === '/api/albums/merge-duplicates' && method === 'POST') {
    calls.merge += 1;
    resp = { groups_merged: 1, albums_removed: 2, images_moved: 3, files_removed: 47, detail: [] };
  } else if (url === '/api/immich/status') resp = { configured: true };
  else if (url === '/api/immich/albums') resp = [];
  return { ok: true, status: 200, json: async () => resp };
};

for (const f of ['core.js', 'match.js', 'immich.js']) {
  eval(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', f), 'utf8')); // eslint-disable-line no-eval
}

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`);
  if (!cond) failures += 1;
}
const tick = (ms = 60) => new Promise((r) => setTimeout(r, ms));
const seenToasts = [];
named['#toasts'].append = (c) => { seenToasts.push(c.textContent); };

(async () => {
  for (const fn of docListeners.DOMContentLoaded || []) await fn();
  await tick(150);

  check('workspace visible with photos', !named['#match-workspace'].classList.contains('hidden'));
  check('first photo rendered', named['#match-photo'].src === '/uploads/albums/7/p0.jpg');
  check('metadata line shows date/camera/gps', named['#match-meta'].textContent.includes('Google Pixel')
    && named['#match-meta'].textContent.includes('39.1000'));
  check('xmp tags shown', named['#match-tags'].textContent === '🏷️ pepper');
  check('counter shows position', named['#match-counter'].textContent.startsWith('1 / 2'));
  check('plants listed alphabetically', named['#match-plant'].innerHTML.indexOf('Habanero') < named['#match-plant'].innerHTML.indexOf('Sungold'));
  check('bulk button groups the two same-day photos',
    !named['#match-bulk'].disabled && named['#match-bulk'].textContent.includes('all 2'));

  // Bulk assign the two same-day photos first.
  named['#match-plant'].value = '5';
  await named['#match-bulk']._listeners.click[0]();
  await tick(60);
  check('bulk assign posted', calls.bulk.length === 1
    && calls.bulk[0].plant_id === 5
    && calls.bulk[0].image_ids.join(',') === '101,102');
  check('bulk toast confirms', seenToasts.some((t) => t.includes('2 photos to Habanero')));
  check('empty state after all assigned', !named['#match-empty'].classList.contains('hidden'));

  // Show everything (including assigned) and exercise single assign.
  named['#match-unassigned'].checked = false;
  await named['#match-unassigned']._listeners.change[0]();
  await tick(60);
  check('all photos listed when filter off', named['#match-counter'].textContent.startsWith('1 / 3'));

  // Assign with no plant chosen -> warning, no request.
  named['#match-plant'].value = '';
  await named['#match-assign']._listeners.click[0]();
  check('assign without plant warns', seenToasts.some((t) => t.includes('Choose a plant')));
  check('no patch sent without plant', calls.patch.length === 0);

  // Assign to Sungold -> PATCH and advance to the next photo.
  named['#match-plant'].value = '6';
  await named['#match-assign']._listeners.click[0]();
  await tick(60);
  check('patch sent with plant id', calls.patch.length === 1 && calls.patch[0].plant_id === 6);
  check('advanced to next photo', named['#match-photo'].src === '/uploads/albums/7/p1.jpg');

  // Keyboard navigation wraps.
  const key = (k) => ({ key: k, target: { matches: () => false } });
  docListeners.keydown.forEach((fn) => fn(key('ArrowLeft')));
  check('arrow key navigates back', named['#match-photo'].src === '/uploads/albums/7/p0.jpg');

  // Merge duplicates button.
  const mergeBtn = named['#immich-merge'];
  await mergeBtn._listeners.click[0]();
  await tick(60);
  check('merge posted once', calls.merge === 1);
  check('merge toast reports removed albums', seenToasts.some((t) => t.includes('Merged 2 duplicate album')));
  check('merge button restored', mergeBtn.disabled === false);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();

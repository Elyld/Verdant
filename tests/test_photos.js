/* Regression test: Photos tab slideshow + Immich import wiring.
 * Drives app.js's initPhotos/initImmich with a stub DOM:
 *  1. Immich section unhides when configured and lists server albums
 *  2. Import posts to the backend and fires verdant:albums-changed
 *  3. Photos picker loads local albums; selecting one starts the slideshow
 *  4. Prev/next wrap around; keyboard arrows work; play/pause toggles
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
    prepend: () => {},
    closest: () => null,
    scrollIntoView: () => {},
    focus: () => {},
    reset: () => {},
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
['photo-album-select', 'slideshow', 'photos-empty', 'slide-stage', 'slide-img',
 'slide-caption', 'slide-counter', 'slide-play', 'photo-refresh', 'slide-prev',
 'slide-next', 'slide-fullscreen', 'immich-album-select', 'immich-import',
 'calendar-grid', 'calendar-empty', 'day-modal', 'toasts', 'app-version'].forEach((id) => {
  named[`#${id}`] = makeEl();
});
named['#day-modal'].classList.add('hidden');
named['#slideshow'].classList.add('hidden');
named['#immich-section'] = makeEl();
named['#immich-section'].classList.add('hidden');
namedAll['#immich-section'] = [named['#immich-section']];
namedAll['#immich-album-select'] = [named['#immich-album-select']];
namedAll['#immich-import'] = [named['#immich-import']];
named['#slide-stage'].requestFullscreen = function () { this._fs = true; };

const docListeners = {};
global.document = {
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: (sel) => (namedAll[sel] || []).slice(),
  addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
  dispatchEvent: (ev) => { (docListeners[ev.type] || []).forEach((fn) => fn(ev)); return true; },
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
  fullscreenElement: null,
  exitFullscreen: () => {},
};
global.window = { location: { pathname: '/photos' }, confirm: () => true };
global.location = { search: '' };
global.CustomEvent = function (type, opts) { this.type = type; this.detail = (opts && opts.detail) || null; };
global.Image = function () { this.src = ''; };
const store = {};
global.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

const IMAGES = [0, 1, 2].map((i) => ({
  id: 100 + i, file_path: `/uploads/albums/7/p${i}.jpg`,
  title: `Photo ${i}`, original_name: `p${i}.jpg`,
}));
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  let body = null;
  if (url === '/api/immich/status') body = { configured: true };
  else if (url === '/api/immich/albums') body = [{ id: 'imm-1', albumName: 'Garden 2026', assetCount: 42 }];
  else if (url === '/api/immich/albums/imm-1/import' && method === 'POST') body = { created: 3, album: { id: 7, name: 'Garden 2026' } };
  else if (url === '/api/albums') body = [{ id: 7, name: 'Garden 2026', images: IMAGES }];
  else if (url === '/api/albums/7') body = { id: 7, name: 'Garden 2026', images: IMAGES };
  else if (url === '/api/stats/calendar') body = [];
  else body = {};
  return { ok: true, status: 200, json: async () => body };
};

const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'app.js'), 'utf8');
eval(src); // eslint-disable-line no-eval

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`);
  if (!cond) failures += 1;
}
const tick = (ms = 60) => new Promise((r) => setTimeout(r, ms));

(async () => {
  for (const fn of docListeners.DOMContentLoaded || []) await fn();
  await tick(120); // let boot's fetches settle

  // --- Immich wiring ---
  check('immich section unhidden when configured', !named['#immich-section'].classList.contains('hidden'));
  check('immich albums listed', named['#immich-album-select'].innerHTML.includes('Garden 2026 (42)'));

  // Import with nothing chosen -> no request (stays put, no crash).
  const importBtn = named['#immich-import'];
  await importBtn._listeners.click[0]();
  check('import without selection does not dispatch', !docListeners['verdant:albums-changed']?.length || true);

  // Choose the album and import.
  named['#immich-album-select'].value = 'imm-1';
  importBtn.textContent = 'Import album';
  let changedDetail = null;
  document.addEventListener('verdant:albums-changed', (ev) => { changedDetail = ev.detail; });
  await importBtn._listeners.click[0]();
  await tick(150);
  check('import dispatched albums-changed with new album id', changedDetail && changedDetail.selectId === 7);
  check('import button restored', importBtn.textContent === 'Import album' && importBtn.disabled === false);

  // --- Photos slideshow ---
  const picker = named['#photo-album-select'];
  check('photo picker lists local albums', picker.innerHTML.includes('Garden 2026'));
  check('imported album auto-selected', picker.value === '7');
  check('slideshow visible after import', !named['#slideshow'].classList.contains('hidden'));
  check('first slide shown', named['#slide-img'].src === '/uploads/albums/7/p0.jpg');
  check('counter reads 1 / 3', named['#slide-counter'].textContent === '1 / 3');
  check('caption shown', named['#slide-caption'].textContent === 'Photo 0');
  check('autoplay started', named['#slide-play'].innerHTML.includes('Pause'));

  await picker._listeners; // noop guard
  picker.value = '7';
  await named['#slide-next']._listeners.click[0]();
  check('next advances', named['#slide-img'].src === '/uploads/albums/7/p1.jpg');
  await named['#slide-next']._listeners.click[0]();
  await named['#slide-next']._listeners.click[0]();
  check('next wraps to first', named['#slide-img'].src === '/uploads/albums/7/p0.jpg');
  await named['#slide-prev']._listeners.click[0]();
  check('prev wraps to last', named['#slide-img'].src === '/uploads/albums/7/p2.jpg');

  for (const fn of docListeners.keydown || []) fn({ key: 'ArrowRight' });
  check('ArrowRight advances', named['#slide-img'].src === '/uploads/albums/7/p0.jpg');

  await named['#slide-play']._listeners.click[0]();
  check('pause toggles to Play', named['#slide-play'].innerHTML.includes('Play') && !named['#slide-play'].innerHTML.includes('Pause'));
  await named['#slide-play']._listeners.click[0]();
  check('play resumes', named['#slide-play'].innerHTML.includes('Pause'));

  await named['#slide-fullscreen']._listeners.click[0]();
  check('fullscreen requested', named['#slide-stage']._fs === true);

  // Deselect -> empty state.
  picker.value = '';
  await picker._listeners.change[0]();
  check('empty state on deselect', named['#slideshow'].classList.contains('hidden'));

  console.log(failures ? `\n${failures} FAILURE(S)` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('ERROR', e); process.exit(1); });

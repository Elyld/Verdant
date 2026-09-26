/* Regression test: calendar heatmap + day-observation popup modal.
 * Stubs just enough DOM for app.js's initCalendar path and drives it:
 *  1. heat levels still render correctly (spot check)
 *  2. clicking a day opens the modal with that day's observations
 *  3. modal closes via [data-close] click and via Escape
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
    _classes: classes,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
      replace: (oldC, newC) => { classes.delete(oldC); classes.add(newC); },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: () => makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => c,
    append: () => {},
    prepend: () => {},
    closest: () => null,
    scrollIntoView: () => {},
    focus: () => {},
    reset: () => {},
    submit: () => {},
    getContext: () => null,
    textContent: '',
    value: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const gridEl = makeEl();
const modalEl = makeEl();
modalEl.classList.add('hidden');
const docListeners = {};
global.document = {
  querySelector: (sel) => {
    if (sel === '#calendar-grid') return gridEl;
    if (sel === '#day-modal') return modalEl;
    if (sel === '#calendar-empty') return makeEl();
    return makeEl();
  },
  querySelectorAll: () => [],
  addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
};
global.window = { location: { pathname: '/calendar' }, confirm: () => true };
global.location = { search: '' };
const store = {};
global.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

// Sample calendar payload: 2026-09-15 has 3 observations (heat-2), 2026-09-20 has 8 (heat-4).
const calendarData = [
  { date: '2026-09-15', plant_name: 'Tomato', health_scale: 8, notes: 'First ripe fruit!', pest_sightings: 'aphids on lower leaves' },
  { date: '2026-09-15', plant_name: 'Basil', health_scale: 9, notes: 'Bushy and fragrant', pest_sightings: null },
  { date: '2026-09-15', plant_name: 'Pepper', health_scale: 4, notes: null, pest_sightings: null },
  ...Array.from({ length: 8 }, (_, i) => ({ date: '2026-09-20', plant_name: `Plant ${i}`, health_scale: 7, notes: `note ${i}`, pest_sightings: null })),
  { date: 'not-a-date', plant_name: 'Weed', health_scale: 1, notes: null, pest_sightings: null },
];
global.fetch = async () => ({ ok: true, status: 200, json: async () => calendarData });

const JS_FILES = ['core.js', 'calendar.js'];
for (const f of JS_FILES) {
  eval(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', f), 'utf8')); // eslint-disable-line no-eval
}

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`);
  if (!cond) failures += 1;
}

(async () => {
  for (const fn of docListeners.DOMContentLoaded || []) await fn();
  await new Promise((r) => setTimeout(r, 50)); // let the fetch promise settle

  const html = gridEl.innerHTML;
  check('grid rendered 3 month sections', (html.match(/calendar-month/g) || []).length === 3);
  const days = (html.match(/data-date="/g) || []).length;
  const now = new Date();
  let expected = 0;
  for (let d = -2; d <= 0; d += 1) expected += new Date(now.getFullYear(), now.getMonth() + d + 1, 0).getDate();
  check(`all ${expected} day cells rendered`, days === expected);
  check('2026-09-15 link is heat-2', /data-date="2026-09-15"[^>]*heat-2|heat-2"[^>]*data-date="2026-09-15/.test(html) || html.includes('data-date="2026-09-15" class="calendar-day heat-2"'));
  check('bad date skipped', !html.includes('not-a-date'));

  // Click the busy day -> modal opens with its observations.
  const gridClick = (gridEl._listeners.click || [])[0];
  check('grid has delegated click handler', !!gridClick);
  const anchor = {
    closest: (sel) => (sel === 'a[data-date]' ? anchor : null),
    getAttribute: (k) => (k === 'data-date' ? '2026-09-15' : null),
  };
  let prevented = false;
  gridClick({ target: anchor, preventDefault: () => { prevented = true; } });
  check('day click prevented navigation', prevented);
  check('modal opened', !modalEl.classList.contains('hidden') && modalEl.classList.contains('modal-open'));
  const body = modalEl.innerHTML;
  check('modal shows plant names', body.includes('Tomato') && body.includes('Basil') && body.includes('Pepper'));
  check('modal shows notes', body.includes('First ripe fruit!'));
  check('modal shows pests', body.includes('aphids on lower leaves'));
  check('modal links to Garden Logs', body.includes('/observations?date=2026-09-15'));
  check('modal has close affordance', body.includes('data-close'));

  // Close via backdrop/close-button delegation.
  const modalClick = (modalEl._listeners.click || [])[0];
  modalClick({ target: { closest: (sel) => (sel === '[data-close]' ? {} : null) } });
  check('modal closed via [data-close]', modalEl.classList.contains('hidden') && modalEl.innerHTML === '');

  // Reopen, then close via Escape.
  gridClick({ target: anchor, preventDefault: () => {} });
  check('modal reopened', modalEl.classList.contains('modal-open'));
  for (const fn of docListeners.keydown || []) fn({ key: 'Escape' });
  check('modal closed via Escape', modalEl.classList.contains('hidden') && modalEl.innerHTML === '');

  // Clicking a non-day area does nothing.
  gridClick({ target: { closest: () => null }, preventDefault: () => { throw new Error('should not navigate'); } });
  check('non-day click is a no-op', modalEl.classList.contains('hidden'));

  console.log(failures ? `\n${failures} FAILURE(S)` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('ERROR', e); process.exit(1); });

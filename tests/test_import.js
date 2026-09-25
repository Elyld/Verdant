/* Regression test: Import page preview/run wiring.
 * Drives app.js's initImport with a stub DOM:
 *  1. Preview with no file -> error toast, no request
 *  2. Preview renders counts, warnings, sample rows
 *  3. Harvest preview renders plant selects with the suggested option picked
 *  4. Run posts assignments gathered from the selects and shows the result
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
    disabled: false,
    files: [],
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
const namedAll = {};
['panel-import', 'import-entity', 'import-file', 'import-preview-btn', 'import-preview',
 'import-preview-body', 'import-assign', 'import-run-btn', 'import-result',
 'import-result-body', 'toasts', 'app-version'].forEach((id) => {
  named[`#${id}`] = makeEl();
});
named['#import-preview'].classList.add('hidden');
named['#import-assign'].classList.add('hidden');
named['#import-result'].classList.add('hidden');
named['#import-entity'].value = 'harvests';

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
global.window = { location: { pathname: '/import' }, confirm: () => true };
global.location = { search: '' };
global.CustomEvent = function (type, opts) { this.type = type; this.detail = (opts && opts.detail) || null; };
const store = {};
global.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: (k) => { delete store[k]; },
};

const seenToasts = [];
named['#toasts'].append = (c) => { seenToasts.push(c.textContent); };

const fetchCalls = [];
let previewPayload = null;
let runPayload = null;
global.fetch = async (url, options) => {
  fetchCalls.push(url);
  let body = {};
  if (url === '/api/import/preview') body = previewPayload;
  else if (url === '/api/import/run') {
    const form = options.body;
    runPayload = { assignments: form.get('assignments'), entity: form.get('entity') };
    body = { entity: 'harvests', entity_label: 'Harvest logs', imported: 2, skipped: 0, errors: [], warnings: [] };
  }
  else if (url === '/api/stats/calendar') body = [];
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
  await tick(120);

  const previewBtn = named['#import-preview-btn'];
  const runBtn = named['#import-run-btn'];

  // 1. No file chosen -> toast, no request.
  named['#import-file'].files = [];
  const callsBefore = fetchCalls.length;
  await previewBtn._listeners.click[0]();
  check('preview without file toasts an error', seenToasts.some((t) => t.includes('Choose a CSV file')));
  check('preview without file makes no request', fetchCalls.length === callsBefore);

  // 2. Harvest preview with one plant-less row and a suggestion.
  previewPayload = {
    entity: 'harvests', entity_label: 'Harvest logs', total_rows: 2,
    counts: { new: 1, skip: 1, error: 0, needs_plant: 1 },
    warnings: ['H-2026-010: pick a plant'],
    sample: [
      { key: 'H-2026-007', status: 'new', label: 'H-2026-007 2026-08-19 — 19 × Sungold' },
      { key: 'H-2026-010', status: 'needs_plant', label: 'H-2026-010 2026-08-19 — 3 fruit: pick a plant', hint_variety: null },
    ],
    truncated: false,
    plant_options: [
      { id: 16, plant_id: 'PL-016', variety_name: 'Sungold' },
      { id: 7, plant_id: 'PL-007', variety_name: 'Fatalii' },
    ],
    assign_rows: [{ key: 'H-2026-010', label: 'H-2026-010 2026-08-19 — 3 fruit: pick a plant', hint_variety: null }],
    suggested_assignments: {},
    needs_plants_first: false,
  };
  named['#import-file'].files = [{ name: 'harvests.csv' }];
  await previewBtn._listeners.click[0]();
  await tick(80);
  check('preview fetched', fetchCalls.includes('/api/import/preview'));
  check('preview card unhidden', !named['#import-preview'].classList.contains('hidden'));
  const bodyHtml = named['#import-preview-body'].innerHTML;
  check('counts rendered', bodyHtml.includes('1 new') && bodyHtml.includes('1 already here'));
  check('warning rendered', bodyHtml.includes('pick a plant'));
  check('import button shows new count', runBtn.textContent.includes('Import 1 row'));

  // 3. Assignment select rendered for the plant-less row.
  const assignHtml = named['#import-assign'].innerHTML;
  check('assign section unhidden', !named['#import-assign'].classList.contains('hidden'));
  check('assign select rendered', assignHtml.includes('data-assign="H-2026-010"'));
  check('plant options listed', assignHtml.includes('Fatalii (PL-007)'));

  // 4. Run gathers the chosen plant and shows the result.
  const sel = makeEl();
  sel.dataset.assign = 'H-2026-010';
  sel.value = '7';
  namedAll['#import-assign [data-assign]'] = [sel];
  await runBtn._listeners.click[0]();
  await tick(80);
  check('run posted', fetchCalls.includes('/api/import/run'));
  const sent = JSON.parse(runPayload.assignments);
  check('assignment sent for the plant-less row', sent['H-2026-010'] === 7);
  check('result card unhidden', !named['#import-result'].classList.contains('hidden'));
  check('result counts rendered', named['#import-result-body'].innerHTML.includes('2</b> imported'));
  check('success toast shown', seenToasts.some((t) => t.includes('Import done')));

  // 5. Suggested assignment comes pre-selected.
  previewPayload.suggested_assignments = { 'H-2026-010': 16 };
  previewPayload.assign_rows = [{ key: 'H-2026-010', label: 'H-2026-010 — pick a plant', hint_variety: 'Sungold' }];
  await previewBtn._listeners.click[0]();
  await tick(80);
  check('suggested plant pre-selected', named['#import-assign'].innerHTML.includes('value="16" selected'));

  process.exit(failures ? 1 : 0);
})();

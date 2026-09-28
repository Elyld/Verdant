/* Quick Log harvest weight UI test.
 * Drives quick.js's initQuick with a stub DOM:
 *  1. the harvest panel renders a weight input + unit select (oz/g/lb/kg)
 *  2. the unit select is prefilled from Preferences (default_weight_unit)
 *  3. saving with a weight POSTs weight/weight_unit to /api/harvests/
 *  4. saving with an empty weight POSTs weight: null (old behavior intact)
 *  5. the NFC ?plant=X&action=harvest spotlight flow still works
 * Run with: node tests/test_quick.js
 */
'use strict';
const fs = require('fs');
const path = require('path');

let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`ok - ${name}`); }
  else { failures++; console.log(`FAIL - ${name}`); }
}
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

function makeEl() {
  const classes = new Set();
  const listeners = {};
  const el = {
    style: {},
    dataset: {},
    _attrs: {},
    _listeners: listeners,
    _classes: classes,
    scrolled: false,
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
    querySelector: () => makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { el._children.push(c); return c; },
    append: () => {},
    prepend: () => {},
    closest: () => null,
    scrollIntoView: () => { el.scrolled = true; },
    focus: () => {},
    reset: () => {},
    textContent: '',
    value: '',
    disabled: false,
    _children: [],
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

// Card element whose querySelector returns stable per-selector stubs.
function makeCard() {
  const el = makeEl();
  const kids = {};
  el._kids = kids;
  el.querySelector = (sel) => {
    if (!kids[sel]) kids[sel] = makeEl();
    return kids[sel];
  };
  return el;
}

const posts = [];
const plant = { id: 7, variety_name: 'Test Pepper', status: 'Growing', location_id: 1 };
const api = {
  get: async (url) => {
    if (url === '/api/plants/') return [plant];
    if (url === '/api/locations/') return [{ id: 1, name: 'Patio' }];
    return [];
  },
  post: async (url, body) => { posts.push({ url, body }); return { id: 1 }; },
};

let bootFn = null;
const cards = [];
const spotEl = makeEl();
const hostEl = makeEl();
hostEl.appendChild = (c) => { cards.push(c); hostEl._children.push(c); return c; };
hostEl.querySelector = () => spotEl;

const named = {
  '#quick-groups': hostEl,
  '#quick-today': makeEl(),
  '#quick-today-log': makeEl(),
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s),
  fmtDate: (s) => s,
  fmtDateTime: (s) => s,
  api,
  toast: () => {},
  markdown: (s) => s,
  uploadFiles: async () => [],
  wireDraft: () => {},
  renderStats: () => {},
  healthBar: () => '',
  todayLocal: () => '2026-09-27',
  getSettings: async () => ({ default_weight_unit: 'g' }),
  onBoot: (fn) => { bootFn = fn; },
};
global.document = {
  createElement: (tag) => (tag === 'div' ? makeCard() : makeEl()),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  body: makeEl(),
};
global.window = {};
global.location = { search: '' };

async function main() {
  const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'quick.js'), 'utf8');
  eval(src);
  check('initQuick registered via onBoot', typeof bootFn === 'function');
  await bootFn();
  await tick(50);

  // Find the plant card (nested: host > section > grid > card).
  function findCard(el) {
    if (el.innerHTML && el.innerHTML.includes('data-hv-weight')) return el;
    for (const kid of el._children || []) {
      const found = findCard(kid);
      if (found) return found;
    }
    return null;
  }
  const card = findCard(hostEl);
  check('one plant card rendered', !!card);
  const kid = (sel) => card.querySelector(sel);
  const html = card.innerHTML;
  check('harvest panel has weight input', html.includes('data-hv-weight'));
  check('harvest panel has unit select', html.includes('data-hv-weight-unit'));
  check('unit select offers oz/g/lb/kg',
    html.includes('<option>oz</option>') && html.includes('<option>g</option>')
    && html.includes('<option>lb</option>') && html.includes('<option>kg</option>'));

  const unitSel = kid('[data-hv-weight-unit]');
  check('unit select prefilled from Preferences (g)', unitSel.value === 'g');

  const saveBtn = kid('[data-hv-save]');
  const clickSave = () => (saveBtn._listeners.click || []).forEach((fn) => fn({ currentTarget: saveBtn }));

  // Save with a weight.
  kid('[data-hv-weight]').value = '12.5';
  kid('[data-hv-weight-unit]').value = 'lb';
  const before = posts.length;
  clickSave();
  await tick(50);
  const weighed = posts.slice(before).find((p) => p.url === '/api/harvests/');
  check('save POSTs to /api/harvests/', !!weighed);
  check('weight posted', weighed && weighed.body.weight === 12.5);
  check('weight_unit posted', weighed && weighed.body.weight_unit === 'lb');
  check('quantity still posted', weighed && weighed.body.quantity === 1);
  check('plant_id still posted', weighed && weighed.body.plant_id === 7);

  // Save with empty weight (old behavior).
  kid('[data-hv-weight]').value = '';
  const before2 = posts.length;
  clickSave();
  await tick(50);
  const unweighed = posts.slice(before2).find((p) => p.url === '/api/harvests/');
  check('empty weight posts weight: null', !!unweighed && unweighed.body.weight === null);

  // NFC spotlight flow: ?plant=7&action=harvest spotlights the harvest button.
  global.location = { search: '?plant=7&action=harvest' };
  spotEl.scrolled = false;
  const spotClasses = new Set();
  spotEl.classList.add = (...c) => c.forEach((x) => spotClasses.add(x));
  spotEl.classList.remove = (...c) => c.forEach((x) => spotClasses.delete(x));
  await bootFn();
  await tick(50);
  check('NFC harvest spotlight scrolls into view', spotEl.scrolled === true);
  check('NFC harvest spotlight adds ring classes',
    spotClasses.has('ring-4') && spotClasses.has('ring-sage-300'));

  if (failures) { console.log(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log('\nAll quick-log weight checks passed.');
}

main().catch((e) => { console.error('HARNESS ERROR', e); process.exit(1); });

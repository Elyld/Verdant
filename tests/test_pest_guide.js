/* Pest & disease guide UI test.
 * Drives pests.js's initPests with a stub DOM:
 *  1. guide search renders result cards
 *  2. "Log a sighting" pre-fills the pest name field
 *  3. picking a plant shows "common issues" chips from the guide
 * Run with: node tests/test_pest_guide.js
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
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    querySelector: () => makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { el._children.push(c); return c; },
    append: (...kids) => { kids.forEach((k) => el._children.push(k)); },
    scrollIntoView: () => {},
    focus: () => {},
    textContent: '',
    value: '',
    _children: [],
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

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

const aphidEntry = {
  slug: 'aphids', name: 'Aphids', type: 'insect',
  hosts: ['tomato', 'pepper'], signs: 'clusters on new growth',
  treatment_organic: 'blast with water', treatment_conventional: 'pyrethrin',
  prevention: 'row covers', sources: ['K-State Extension'], source: 'Pest & disease guide',
};
const hornwormEntry = {
  slug: 'tomato-hornworm', name: 'Tomato hornworm', type: 'insect',
  hosts: ['tomato'], signs: 'fat green caterpillar',
  treatment_organic: 'handpick', treatment_conventional: 'carbaryl',
  prevention: 'till in fall', sources: ['K-State Extension'], source: 'Pest & disease guide',
};

const api = {
  get: async (url) => {
    if (url === '/api/pests/') return [];
    if (url === '/api/plants/') return [{ id: 1, variety_name: 'Cherokee Purple', species_type: 'Tomato' }];
    if (url.startsWith('/api/pest-guide/search')) return [aphidEntry];
    if (url.startsWith('/api/pest-guide/for-host')) return [aphidEntry, hornwormEntry];
    return [];
  },
  post: async () => ({ id: 1 }),
  patch: async () => ({}),
  del: async () => null,
};

const bootFns = [];
const named = {
  '#pest-form': makeEl(),
  '#panel-pests': makeEl(),
  '#pest-date': makeEl(),
  '#pest-name': makeEl(),
  '#pest-plant': makeEl(),
  '#pest-treatment': makeEl(),
  '#pest-notes': makeEl(),
  '#pests-open': makeEl(),
  '#pests-done': makeEl(),
  '#pests-open-empty': makeEl(),
  '#pests-done-empty': makeEl(),
  '#guide-q': makeEl(),
  '#guide-go': makeEl(),
  '#guide-results': makeEl(),
  '#pest-common': makeEl(),
  '#pest-common-chips': makeEl(),
};
named['#pest-common'].classList.add('hidden');

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s),
  fmtDate: (s) => s,
  fmtDateTime: (s) => s,
  api,
  toast: () => {},
  todayLocal: () => '2026-09-28',
  onBoot: (fn) => { bootFns.push(fn); },
};
global.document = {
  createElement: (tag) => (tag === 'article' ? makeCard() : makeEl()),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  body: makeEl(),
};
global.window = { confirm: () => true };
global.location = { search: '' };

async function main() {
  const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'pests.js'), 'utf8');
  eval(src);
  check('initPests registered via onBoot', bootFns.length > 0);
  for (const fn of bootFns) await fn();
  await tick(50);

  // 1. Guide search renders a result card.
  const goBtn = named['#guide-go'];
  named['#guide-q'].value = 'aphid';
  (goBtn._listeners.click || []).forEach((fn) => fn());
  await tick(50);
  const results = named['#guide-results'];
  check('search renders one result card', results._children.length === 1);
  check('card names the pest', results._children[0].innerHTML.includes('Aphids'));
  check('card shows organic treatment', results._children[0].innerHTML.includes('blast with water'));
  check('card shows sources', results._children[0].innerHTML.includes('K-State Extension'));

  // 2. "Log a sighting" pre-fills the pest name field.
  const card = results._children[0];
  const logBtn = card._kids['[data-guide-log]'];
  check('log button exists on card', !!logBtn);
  (logBtn._listeners.click || []).forEach((fn) => fn());
  check('pest name pre-filled', named['#pest-name'].value === 'Aphids');

  // 3. Picking a plant shows common-issue chips.
  named['#pest-plant'].value = '1';
  (named['#pest-plant']._listeners.change || []).forEach((fn) => fn());
  await tick(50);
  check('common-issues row shown', !named['#pest-common'].classList.contains('hidden'));
  const chips = named['#pest-common-chips']._children;
  check('two chips rendered', chips.length === 2);
  (chips[1]._listeners.click || []).forEach((fn) => fn());
  check('chip click fills pest name', named['#pest-name'].value === 'Tomato hornworm');

  if (failures) { console.log(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log('\nAll pest-guide checks passed.');
}

main().catch((e) => { console.error('HARNESS ERROR', e); process.exit(1); });

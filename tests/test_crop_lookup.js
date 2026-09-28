/* Crop lookup dialog (plants.js initCropLookup):
   1. 🔎 button opens the modal, search box seeded from the form's species/variety
   2. typing+Enter searches /api/crops and renders candidates
   3. clicking a candidate shows the detail + "Use this info" button
   4. using it fills empty form fields only (never clobbers typed values)
   5. Escape closes the modal
   Run with: node tests/test_crop_lookup.js
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

function makeEl(opts = {}) {
  const classes = new Set();
  const listeners = {};
  const el = {
    style: {}, dataset: {}, value: '', textContent: '', disabled: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c) => { const h = classes.has(c); h ? classes.delete(c) : classes.add(c); return !h; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    click: () => { (listeners.click || []).forEach((fn) => fn()); },
    fire: (t, ev) => { (listeners[t] || []).forEach((fn) => fn(ev || {})); },
    setAttribute: () => {}, getAttribute: () => null,
    querySelector: () => makeEl(), querySelectorAll: () => [],
    appendChild: (c) => c, focus: () => {}, scrollIntoView: () => {},
  };
  let html = '';
  if (!opts.noHtml) {
    Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  }
  Object.defineProperty(el, 'className', {
    get: () => [...classes].join(' '),
    set: (v) => { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach((x) => classes.add(x)); },
  });
  return el;
}

// Element whose innerHTML <button> tags (with their data-* attributes)
// become clickable stubs.
function makeButtonBox() {
  const el = makeEl({ noHtml: true });
  let buttons = [];
  let html = '';
  Object.defineProperty(el, 'innerHTML', {
    get: () => html,
    set: (v) => {
      html = String(v);
      buttons = [];
      const tagRe = /<button\b[^>]*>/g;
      let tm;
      while ((tm = tagRe.exec(html))) {
        const b = makeEl();
        const attrRe = /data-([a-z]+)="([^"]*)"/g;
        let am;
        while ((am = attrRe.exec(tm[0]))) b.dataset[am[1]] = am[2];
        if (/id="(crop-use)"/.test(tm[0])) b.id = 'crop-use';
        buttons.push(b);
      }
    },
  });
  el.querySelectorAll = (sel) => (sel === '[data-kind]' || sel === '#crop-use' ? buttons : []);
  el.querySelector = (sel) => {
    if (sel === '#crop-use') return buttons[0] || makeEl();
    return makeEl();
  };
  el._buttons = () => buttons;
  return el;
}

function makeModal() {
  const el = makeEl();
  const kids = {
    '#crop-q': makeEl(),
    '#crop-results': makeButtonBox(),
    '#crop-detail': makeButtonBox(),
  };
  el.querySelector = (sel) => kids[sel] || makeEl();
  el.querySelectorAll = () => [];
  el._kids = kids;
  return el;
}

const TOMATO = {
  key: 'tomato', name: 'Tomato', family: 'Nightshade (Solanaceae)', sun: 'Full Sun',
  spacing_in: '24–36', sowing_depth_in: '¼', days_to_germination: '5–10',
  days_to_maturity: 75, description: 'Start indoors 6–8 weeks before last frost.',
  source: 'Built-in crop guide',
  varieties: [{ name: 'Cherokee Purple', days_to_maturity: 80, note: 'Indeterminate heirloom beefsteak.' }],
};

const PACKET = {
  id: 7, variety_name: 'Cherokee Purple', species_type: 'Tomato',
  vendor_name: 'Territorial', vendor_url: 'https://example.com/p', year_acquired: 2025,
  quantity: '1 packet', notes: 'packet notes',
};

const apiCalls = [];
const api = {
  get: async (url) => {
    apiCalls.push(url);
    if (url.startsWith('/api/crops?q=')) {
      const q = decodeURIComponent(url.split('=')[1]).toLowerCase();
      const guide = [];
      if ('tomato'.includes(q) || q === 'tom') guide.push({
        kind: 'crop', key: 'tomato', name: 'Tomato', crop_name: 'Tomato',
        family: 'Nightshade (Solanaceae)', sun: 'Full Sun', days_to_maturity: 75, note: '' });
      if ('cherokee purple'.includes(q)) guide.push({
        kind: 'variety', key: 'tomato', name: 'Cherokee Purple', crop_name: 'Tomato',
        family: 'Nightshade (Solanaceae)', sun: 'Full Sun', days_to_maturity: 80,
        note: 'Indeterminate heirloom beefsteak.' });
      const stash = q.includes('cherokee') ? [{
        kind: 'packet', packet_id: 7, variety_name: 'Cherokee Purple',
        species_type: 'Tomato', vendor_name: 'Territorial', year_acquired: 2025 }] : [];
      return { ok: true, guide, stash };
    }
    if (url === '/api/crops/tomato') return { ok: true, crop: TOMATO };
    if (url === '/api/seed-packets/7') return PACKET;
    throw new Error('unexpected GET ' + url);
  },
};

const toasts = [];
const bootFns = [];
const docListeners = {};

const modal = makeModal();
const resultsBox = modal._kids['#crop-results'];
const detailBox = modal._kids['#crop-detail'];
const named = {
  '#crop-lookup-btn': makeEl(),
  '#crop-modal': modal,
  '#crop-results': resultsBox,
  '#crop-detail': detailBox,
  '#plant-name': makeEl(),
  '#plant-species': makeEl(),
  '#plant-light': makeEl(),
  '#plant-maturity': makeEl(),
  '#plant-notes': makeEl(),
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
  api,
  toast: (msg) => { toasts.push(msg); },
  onBoot: (fn) => { bootFns.push(fn); },
};
global.document = {
  createElement: () => makeEl(),
  querySelector: () => makeEl(),
  querySelectorAll: () => [],
  addEventListener: (t, fn) => { (docListeners[t] = docListeners[t] || []).push(fn); },
  body: makeEl(),
};
global.window = {};

async function main() {
  const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'plants.js'), 'utf8');
  eval(src);
  check('two boot fns registered (initPlants + initCropLookup)', bootFns.length === 2);
  await bootFns[1](); // initCropLookup only
  await tick(20);

  // 1. Modal opens, search seeded from the variety name when species is empty.
  named['#plant-name'].value = 'Cherokee Purple';
  named['#plant-species'].value = '';
  named['#crop-lookup-btn'].click();
  await tick(20);
  check('modal opened', !modal.classList.contains('hidden'));
  check('search seeded from variety name', modal.innerHTML.includes('value="Cherokee Purple"'));
  check('seed query searched', apiCalls.some((u) => u.startsWith('/api/crops?q=Cherokee')));

  // 2. Typing a query + Enter renders candidates.
  const q = modal._kids['#crop-q'];
  q.value = 'tom';
  q.fire('keydown', { key: 'Enter', preventDefault: () => {} });
  await tick(50);
  const results = resultsBox;
  check('candidates rendered', results.innerHTML.includes('Tomato'));
  check('candidate shows sun + maturity', results.innerHTML.includes('Full Sun'));

  // 3. Clicking a candidate shows detail with the use button.
  results._buttons()[0].click();
  await tick(50);
  const detail = detailBox;
  check('detail fetched the full crop', apiCalls.includes('/api/crops/tomato'));
  check('detail shows spacing/depth/timing',
    detail.innerHTML.includes('24–36') && detail.innerHTML.includes('5–10'));
  check('use button present', detail.innerHTML.includes('id="crop-use"'));

  // 4. "Use this info" fills empty fields, never clobbers.
  named['#plant-species'].value = '';
  named['#plant-light'].value = 'Part Shade'; // user-typed... (select mock: plain value)
  named['#plant-maturity'].value = '';
  named['#plant-notes'].value = '';
  detail.querySelector('#crop-use').click();
  await tick(20);
  check('species filled from crop', named['#plant-species'].value === 'Tomato');
  check('sun select set to crop sun', named['#plant-light'].value === 'Full Sun');
  check('maturity filled when empty', named['#plant-maturity'].value === 75);
  check('notes gained growing-info block', named['#plant-notes'].value.includes('Growing info (Tomato)'));
  check('modal closed after apply', modal.classList.contains('hidden'));
  check('toast confirms', toasts.some((t) => t.includes('Tomato')));

  // 5. Second pass: existing values are left alone, notes appended once.
  named['#plant-species'].value = 'Tomatillo';
  named['#plant-maturity'].value = '80';
  named['#plant-notes'].value = 'my notes';
  named['#crop-lookup-btn'].click();
  await tick(20);
  const q2 = modal._kids['#crop-q'];
  q2.value = 'tom';
  q2.fire('keydown', { key: 'Enter', preventDefault: () => {} });
  await tick(50);
  resultsBox._buttons()[0].click();
  await tick(50);
  detailBox.querySelector('#crop-use').click();
  await tick(20);
  check('species not clobbered', named['#plant-species'].value === 'Tomatillo');
  check('maturity not clobbered', named['#plant-maturity'].value === '80');
  check('notes appended, original kept',
    named['#plant-notes'].value.includes('my notes') &&
    named['#plant-notes'].value.includes('Growing info (Tomato)'));
  const count = (named['#plant-notes'].value.match(/Growing info \(Tomato\)/g) || []).length;
  check('growing-info block not duplicated', count === 1);

  // 6. Variety search: variety badge, detail shows variety note + source, apply fills variety name.
  named['#plant-name'].value = '';
  named['#plant-species'].value = '';
  named['#plant-maturity'].value = '';
  named['#plant-notes'].value = '';
  named['#crop-lookup-btn'].click();
  await tick(20);
  const q3 = modal._kids['#crop-q'];
  q3.value = 'cherokee';
  q3.fire('keydown', { key: 'Enter', preventDefault: () => {} });
  await tick(50);
  check('variety badge rendered', resultsBox.innerHTML.includes('variety</span>'));
  check('stash section rendered', resultsBox.innerHTML.includes('Your seed stash'));
  const varBtn = resultsBox._buttons().find((b) => b.dataset.kind === 'variety');
  check('variety button found', !!varBtn);
  varBtn.click();
  await tick(50);
  check('detail shows variety note', detailBox.innerHTML.includes('Indeterminate heirloom'));
  check('detail shows guide source', detailBox.innerHTML.includes('Source: Built-in crop guide · variety notes'));
  detailBox.querySelector('#crop-use').click();
  await tick(20);
  check('variety name filled', named['#plant-name'].value === 'Cherokee Purple');
  check('variety maturity override used', named['#plant-maturity'].value === 80);

  // 7. Seed-stash packet: detail shows stash source, apply fills from the packet.
  named['#plant-name'].value = '';
  named['#plant-species'].value = '';
  named['#plant-notes'].value = '';
  named['#crop-lookup-btn'].click();
  await tick(20);
  const q4 = modal._kids['#crop-q'];
  q4.value = 'cherokee';
  q4.fire('keydown', { key: 'Enter', preventDefault: () => {} });
  await tick(50);
  const pktBtn = resultsBox._buttons().find((b) => b.dataset.kind === 'packet');
  check('packet button found', !!pktBtn);
  pktBtn.click();
  await tick(50);
  check('packet detail fetched', apiCalls.includes('/api/seed-packets/7'));
  check('packet detail shows stash source', detailBox.innerHTML.includes('Source: your seed stash · Territorial'));
  detailBox.querySelector('#crop-use').click();
  await tick(20);
  check('packet variety filled', named['#plant-name'].value === 'Cherokee Purple');
  check('packet species filled', named['#plant-species'].value === 'Tomato');
  check('packet notes mention stash', named['#plant-notes'].value.includes('From seed stash'));

  // 8. Escape closes the modal.
  named['#crop-lookup-btn'].click();
  await tick(20);
  check('modal open again', !modal.classList.contains('hidden'));
  (docListeners.keydown || []).forEach((fn) => fn({ key: 'Escape' }));
  await tick(20);
  check('escape closes modal', modal.classList.contains('hidden'));

  console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} FAILURES`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((e) => { console.error('HARNESS ERROR', e); process.exit(1); });

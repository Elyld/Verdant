/* Winter seed-order assistant tab: spend cards, ratings table, wishlist. */
'use strict';
const fs = require('fs');

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

function makeEl() {
  const classes = new Set();
  const listeners = {};
  const el = {
    style: {},
    dataset: {},
    _listeners: listeners,
    checked: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    focus: () => {},
    scrollIntoView: () => {},
    closest: () => null,
    textContent: '',
    value: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
['seed-tab-assistant', 'oa-spend', 'oa-spend-empty', 'oa-spend-year',
 'oa-ratings', 'oa-ratings-empty', 'oa-wishlist', 'oa-wishlist-empty',
 'oa-order-list', 'oa-wish-form', 'oa-wish-variety', 'oa-wish-vendor',
 'oa-wish-notes', 'seed-tabbtn-assistant',
].forEach((id) => { named[`#${id}`] = makeEl(); });

global.document = {
  readyState: 'complete',
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
};
global.window = { location: { pathname: '/seeds', origin: 'http://localhost:3119' }, addEventListener: () => {} };
global.confirm = () => true;
global.location = { search: '', origin: 'http://localhost:3119' };

const ASSISTANT = {
  generated_at: '2026-09-27',
  last_year: 2025,
  packets: [
    { id: 1, variety_name: 'Cherokee Purple', category: 'Tomato', vendor_name: 'Territorial Seed',
      year_acquired: 2024, stash_age_years: 2, grow_again: 'yes',
      quantity: '~40 seeds', seed_count: 40,
      last_order: { vendor: 'Territorial Seed', order_date: '2025-01-12', invoice_id: 7 } },
    { id: 2, variety_name: 'Genovese Basil', category: 'Herb', vendor_name: '',
      year_acquired: null, stash_age_years: null, grow_again: '',
      quantity: '', seed_count: null, last_order: null },
  ],
  vendor_spend: [{ vendor: 'Territorial Seed', total: 84.32, orders: 3 }],
  wishlist: [
    { id: 11, variety_name: 'Costoluto Fiorentino', vendor_name: 'Territorial', notes: '',
      checked: true, date_added: '2026-09-20',
      last_order: { vendor: 'Baker Creek', order_date: '2024-12-01', invoice_id: 3 } },
    { id: 12, variety_name: 'Dragon Tongue', vendor_name: '', notes: 'bush bean',
      checked: false, date_added: '2026-09-21', last_order: null },
  ],
};

const calls = [];
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  let body = null;
  try { body = options && options.body ? JSON.parse(options.body) : null; } catch (e) { /* ignore */ }
  calls.push({ method, url, body });
  let resp = {};
  if (url === '/api/order-assistant/') resp = ASSISTANT;
  else if (method !== 'GET') resp = { ok: true };
  return { ok: true, status: 200, json: async () => resp };
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
  fmtDate: (s) => s,
  api: {
    get: (p) => fetch(p).then((r) => r.json()),
    post: (p, j) => fetch(p, { method: 'POST', body: JSON.stringify(j) }).then((r) => r.json()),
    patch: (p, j) => fetch(p, { method: 'PATCH', body: JSON.stringify(j) }).then((r) => r.json()),
    del: (p) => fetch(p, { method: 'DELETE' }).then((r) => r.json()),
  },
  toast: () => {},
  onBoot: (fn) => fn(),
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));
const fakeTarget = (btn) => ({ closest: (sel) => btn });

(async () => {
  require('/home/hatch/workspace/verdant/app/static/js/order_assistant.js');
  await tick(50);

  const spend = named['#oa-spend'];
  check('spend card names the vendor', spend.innerHTML.includes('Territorial Seed'));
  check('spend card shows the total', spend.innerHTML.includes('$84.32'));
  check('spend card shows order count', spend.innerHTML.includes('3 orders'));
  check('spend year label set', String(named['#oa-spend-year'].textContent) === '2025');

  const ratings = named['#oa-ratings'];
  check('ratings table lists the packet', ratings.innerHTML.includes('Cherokee Purple'));
  check('ratings table shows stash age', ratings.innerHTML.includes('bought 2024') && ratings.innerHTML.includes('2 yrs old'));
  check('ratings table lists unrated packet', ratings.innerHTML.includes('Genovese Basil'));
  check('rating buttons carry data attributes', ratings.innerHTML.includes('data-oa-rate="favorite"') && ratings.innerHTML.includes('data-packet="1"'));
  check('active rating is highlighted', ratings.innerHTML.includes('data-oa-rate="yes"') && ratings.innerHTML.includes('bg-sage-600'));
  check('wishlist prefill button present', ratings.innerHTML.includes('data-oa-to-wish="1"'));

  const wish = named['#oa-wishlist'];
  check('wishlist renders the item', wish.innerHTML.includes('Costoluto Fiorentino'));
  check('wishlist checkbox carries the id', wish.innerHTML.includes('data-oa-check="11"'));
  check('wishlist shows last vendor/date from invoices', wish.innerHTML.includes('Baker Creek') && wish.innerHTML.includes('2024-12-01'));
  check('wishlist shows notes', wish.innerHTML.includes('bush bean'));
  check('wishlist delete button present', wish.innerHTML.includes('data-oa-wdel="12"'));

  const orderList = named['#oa-order-list'];
  check('order list rolls up checked items', !orderList.classList.contains('hidden') && orderList.innerHTML.includes('Costoluto Fiorentino') && orderList.innerHTML.includes('Order list (1)'));

  // Rating click -> PATCH /api/seed-packets/2 {grow_again: 'favorite'}
  const host = named['#seed-tab-assistant'];
  const rateBtn = { dataset: { packet: '2', oaRate: 'favorite' } };
  fire(host, 'click', { target: fakeTarget(rateBtn) });
  await tick(20);
  const rateCall = calls.find((c) => c.method === 'PATCH' && c.url === '/api/seed-packets/2');
  check('rating click PATCHes the packet', !!rateCall && rateCall.body && rateCall.body.grow_again === 'favorite');

  // Checkbox toggle -> PATCH /api/wishlist/12 {checked: true}
  const box = { dataset: { oaCheck: '12' }, checked: true, closest: () => null };
  box.closest = (sel) => (sel === '[data-oa-check]' ? box : null);
  fire(host, 'change', { target: box });
  await tick(20);
  const checkCall = calls.find((c) => c.method === 'PATCH' && c.url === '/api/wishlist/12');
  check('checkbox toggle PATCHes the wishlist item', !!checkCall && checkCall.body && checkCall.body.checked === true);

  // Wishlist form submit -> POST /api/wishlist/
  named['#oa-wish-variety'].value = '  Jimmy Nardello  ';
  named['#oa-wish-vendor'].value = 'Baker Creek';
  named['#oa-wish-notes'].value = '';
  fire(named['#oa-wish-form'], 'submit');
  await tick(50);
  const postCall = calls.find((c) => c.method === 'POST' && c.url === '/api/wishlist/');
  check('wishlist form POSTs trimmed values', !!postCall && postCall.body && postCall.body.variety_name === 'Jimmy Nardello' && postCall.body.vendor_name === 'Baker Creek');

  // "+ wishlist" prefill from a rating row
  const preBtn = { dataset: { oaToWish: '1' } };
  const mixedTarget = { closest: (sel) => (sel === '[data-oa-to-wish]' ? preBtn : null) };
  fire(host, 'click', { target: mixedTarget });
  await tick(20);
  check('wishlist prefill copies variety + last vendor', named['#oa-wish-variety'].value === 'Cherokee Purple' && named['#oa-wish-vendor'].value === 'Territorial Seed');

  if (failures > 0) { console.error(`${failures} check(s) failed`); process.exit(1); }
  console.log('All order-assistant checks passed.');
})();

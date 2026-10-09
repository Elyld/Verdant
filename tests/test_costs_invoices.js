/* Regression test: Costs page invoices section wiring.
 * Drives costs.js's initCosts with a stub DOM:
 *  1. initCosts runs without throwing (a temporal-dead-zone bug once
 *     killed initInvoices: `const form = $('#invoice-form')` ran before the
 *     inner `const { $ } = globalThis.Verdant` was initialized).
 *  2. Invoice rows render: vendor, order number, total, PDF link when a
 *     pdf_path is present, and the linked-expense badge.
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
['cost-form', 'cost-form-title', 'cost-submit', 'cost-cancel', 'cost-date', 'cost-category', 'cost-desc', 'cost-amount', 'cost-notes',
 'cost-plant', 'costs-rows', 'costs-empty', 'costs-total', 'costs-by-cat',
 'invoice-form', 'inv-vendor', 'inv-date', 'inv-order', 'inv-total', 'inv-items',
  'inv-expense', 'inv-notes', 'inv-pdf', 'invoices-rows', 'invoices-empty',
  'books-badge',
  'toasts'].forEach((id) => {
  named[`#${id}`] = makeEl();
});
named['#costs-empty'].classList.add('hidden');
named['#cost-cancel'].classList.add('hidden');
named['#invoices-empty'].classList.add('hidden');

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
global.window = { location: { pathname: '/costs' }, confirm: () => true };
global.location = { search: '' };
global.CustomEvent = function (type, opts) { this.type = type; this.detail = (opts && opts.detail) || null; };

const seenToasts = [];
named['#toasts'].append = (c) => { seenToasts.push(c.textContent); };

const invoices = [
  { id: 1, vendor: 'Territorial Seed', order_number: 'WW1149159', order_date: '2026-08-24',
    total: 56.53, items_summary: 'Fall Garlic Festival x1 $46.95', notes: 'Garlic for fall.',
    source: 'gmail', expense_id: null, pdf_path: '/uploads/invoices/1/receipt.pdf' },
  { id: 2, vendor: '247Garden', order_number: '100126489', order_date: '2026-02-20',
    total: 48.02, items_summary: 'Grow bags', notes: '', source: 'gmail',
    expense_id: 3, pdf_path: null },
];
const expenses = [
  { id: 3, date: '2026-04-20', category: 'Supplies', description: 'Grow bags (5-pack)', amount: 24.99 },
];
const packets = [
  { id: 10, variety_name: 'Costoluto Fiorentino', vendor_name: 'Territorial Seed' },
  { id: 11, variety_name: 'Habanero', vendor_name: "Matt's Peppers" },
];
const linkedPackets = {
  1: [{ id: 10, variety_name: 'Costoluto Fiorentino', vendor_name: 'Territorial Seed' }],
  2: [],
};
const linkedExpensePackets = {
  3: [{ id: 11, variety_name: 'Habanero', vendor_name: "Matt's Peppers" }],
};
const suggestions = {
  1: [{ packet_id: 11, variety: 'Habanero', matched_item: 'Habanero - SEED / 25 seeds', score: 0.9 }],
  2: [],
};
const expenseSuggestions = {
  3: [{ packet_id: 10, variety: 'Costoluto Fiorentino', matched_item: 'Costoluto Fiorentino Tomato - ORGANIC SEED', score: 1.0 }],
};
const fetchCalls = [];
global.fetch = async (url, options = {}) => {
  fetchCalls.push({ url, method: options.method || 'GET', body: options.body });
  let body = [];
  if (url === '/api/invoices/') body = invoices;
  else if (url === '/api/expenses/') body = expenses;
  else if (url === '/api/seed-packets/') body = packets;
  else if (url === '/api/books/check') body = {
    level: 'error',
    counts: { error: 1, warn: 0, info: 0 },
    structural: [{ severity: 'error', code: 'INVOICE_EXPENSE_MISMATCH', message: 'Invoice 9 total mismatch', invoice_id: 9 }],
    ledger: [],
    ledger_summary: {},
    ledger_checked_at: '2026-10-09T20:00:00Z',
  };
  else if ((options.method === 'POST' || options.method === 'DELETE')
           && /^\/api\/(invoices|expenses)\/\d+\/packets(\/\d+)?$/.test(url)) {
    body = options.method === 'POST'
      ? { id: 11, variety_name: 'Habanero', vendor_name: "Matt's Peppers" }
      : null;
  } else if (/^\/api\/invoices\/\d+\/derive-packets$/.test(url)) {
    const apply = String(options.body || '').includes('"apply":true');
    body = {
      invoice_id: 1, vendor: 'Territorial Seed', applied: apply,
      created: apply ? [99] : [],
      plan: [{ variety_name: 'Fall Garlic Festival', category: 'Garlic', action: 'create', packet_id: null, match_score: 0 }],
    };
  } else {
    const m = url.match(/^\/api\/(invoices|expenses)\/(\d+)\/(packets|packet-suggestions)$/);
    if (m) {
      const store = m[1] === 'invoices' ? linkedPackets : linkedExpensePackets;
      const sugg = m[1] === 'invoices' ? suggestions : expenseSuggestions;
      body = m[3] === 'packets' ? (store[m[2]] || []) : (sugg[m[2]] || []);
    }
  }
  const status = options.method === 'DELETE' ? 204 : 200;
  return { ok: true, status, json: async () => body };
};

const JS_FILES = ['core.js', 'costs.js'];
eval(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'core.js'), 'utf8')); // eslint-disable-line no-eval
// Capture the boot callback instead of dispatching DOMContentLoaded (avoids
// boot()'s nav/frost wiring, which needs a fuller DOM).
const bootFns = [];
globalThis.Verdant.onBoot = (fn) => bootFns.push(fn);
globalThis.window = globalThis.window || {};
globalThis.window.confirm = () => true;
eval(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'costs.js'), 'utf8')); // eslint-disable-line no-eval

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}`);
  if (!cond) failures += 1;
}
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  // 1. initCosts must not throw (TDZ regression).
  let threw = null;
  try {
    bootFns.forEach((fn) => fn());
  } catch (e) { threw = e; }
  check('initCosts runs without throwing', threw === null);
  if (threw) { console.log('threw:', threw.message); process.exit(1); }

  await tick(80);

  // 2. Invoice rows render.
  const rows = named['#invoices-rows'].innerHTML;
  check('invoice rows rendered', rows.includes('Territorial Seed') && rows.includes('247Garden'));
  check('order numbers rendered', rows.includes('WW1149159') && rows.includes('100126489'));
  check('totals rendered', rows.includes('$56.53') && rows.includes('$48.02'));
  check('items summary rendered', rows.includes('Fall Garlic Festival'));
  check('notes rendered', rows.includes('Garlic for fall.'));
  check('PDF link shown when pdf_path set', rows.includes('receipt.pdf'));
  check('expense badge shown on linked invoice', rows.includes('Grow bags (5-pack)') && rows.includes('💸'));
  check('empty notice hidden', named['#invoices-empty'].classList.contains('hidden'));
  check('expense dropdown populated', named['#inv-expense'].innerHTML.includes('Grow bags (5-pack)'));

  // 3. Seed packet links render per invoice row (multi-select).
  check('linked packet chip rendered', rows.includes('🌱') && rows.includes('Costoluto Fiorentino'));
  check('detach button carries kind:invoice:packet ids', rows.includes('data-pk-detach="invoice:1:10"'));
  check('suggestion button rendered with packet id', rows.includes('data-pk-attach="invoice:1:11"') && rows.includes('+ Habanero'));
  check('suggestion shows matched item in title', rows.includes('Habanero - SEED / 25 seeds'));
  check('multi checkbox panel rendered per row', rows.includes('data-pk-check="invoice:1:10"') && rows.includes('data-pk-check="invoice:2:11"'));
  check('linked packets come pre-checked', rows.includes('data-pk-check="invoice:1:10" checked'));
  check('unlinked packets unchecked', !rows.includes('data-pk-check="invoice:2:10" checked'));
  check('checkboxes offer all seed packets', rows.includes("Matt&#39;s Peppers") || rows.includes("Matt's Peppers"));

  // 4. One-tap suggestion attach POSTs the right packet.
  const clickFns = named['#invoices-rows']._listeners.click || [];
  const fakeAttach = { target: { closest: (sel) => (sel === '[data-pk-attach]' ? { dataset: { pkAttach: 'invoice:2:11' } } : null) } };
  await Promise.all(clickFns.map((fn) => fn(fakeAttach)));
  await tick(80);
  const attachCall = fetchCalls.find((c) => c.url === '/api/invoices/2/packets' && c.method === 'POST');
  check('suggestion attach POSTs to invoice packets endpoint', !!attachCall);
  check('suggestion attach sends the packet id', !!attachCall && JSON.parse(attachCall.body).seed_packet_id === 11);

  // 5. Detach DELETEs the right link.
  const fakeDetach = { target: { closest: (sel) => (sel === '[data-pk-detach]' ? { dataset: { pkDetach: 'invoice:1:10' } } : null) } };
  await Promise.all(clickFns.map((fn) => fn(fakeDetach)));
  await tick(80);
  check('detach DELETEs the invoice/packet link', fetchCalls.some((c) => c.url === '/api/invoices/1/packets/10' && c.method === 'DELETE'));

  // 6. Checking a packet checkbox attaches it; unchecking detaches.
  const changeFns = named['#invoices-rows']._listeners.change || [];
  const fakeCheck = { target: { closest: () => ({ dataset: { pkCheck: 'invoice:2:10' }, checked: true }) } };
  await Promise.all(changeFns.map((fn) => fn(fakeCheck)));
  await tick(80);
  const checkCall = fetchCalls.filter((c) => c.url === '/api/invoices/2/packets' && c.method === 'POST').pop();
  check('checkbox check attaches the packet', !!checkCall && JSON.parse(checkCall.body).seed_packet_id === 10);
  const fakeUncheck = { target: { closest: () => ({ dataset: { pkCheck: 'invoice:1:10' }, checked: false }) } };
  await Promise.all(changeFns.map((fn) => fn(fakeUncheck)));
  await tick(80);
  check('checkbox uncheck detaches the packet', fetchCalls.some((c) => c.url === '/api/invoices/1/packets/10' && c.method === 'DELETE'));

  // 7. "Create expense" button only on invoices without a linked expense.
  check('create-expense button shown for unlinked invoice',
    rows.includes('data-create-expense="1"') && rows.includes('➕ Create expense'));
  check('no create-expense button on linked invoice', !rows.includes('data-create-expense="2"'));
  const fakeCreateExp = { target: { closest: (sel) => (sel === '[data-create-expense]' ? { dataset: { createExpense: '1' } } : null) } };
  await Promise.all(clickFns.map((fn) => fn(fakeCreateExp)));
  await tick(80);
  check('create-expense click POSTs to the create-expense endpoint',
    fetchCalls.some((c) => c.url === '/api/invoices/1/create-expense' && c.method === 'POST'));

  // 8. Expense rows carry an edit affordance; clicking it loads the form.
  const costRows = named['#costs-rows'].innerHTML;
  check('expense row has edit button', costRows.includes('data-edit-cost="3"'));
  const costClickFns = named['#costs-rows']._listeners.click || [];
  const fakeEdit = { target: { closest: (sel) => (sel === '[data-edit-cost]' ? { dataset: { editCost: '3' } } : null) } };
  await Promise.all(costClickFns.map((fn) => fn(fakeEdit)));
  await tick(20);
  check('edit populates date', named['#cost-date'].value === '2026-04-20');
  check('edit populates category', named['#cost-category'].value === 'Supplies');
  check('edit populates description', named['#cost-desc'].value === 'Grow bags (5-pack)');
  check('edit populates amount', String(named['#cost-amount'].value) === '24.99');
  check('form switches to editing mode',
    named['#cost-form-title'].textContent === 'Edit expense' && named['#cost-submit'].textContent === 'Save changes');
  check('cancel button shown while editing', !named['#cost-cancel'].classList.contains('hidden'));

  // 9. Submitting while editing PATCHes the expense, then the form resets.
  const submitFns = named['#cost-form']._listeners.submit || [];
  await Promise.all(submitFns.map((fn) => fn({ preventDefault: () => {} })));
  await tick(80);
  const patchCall = fetchCalls.find((c) => c.url === '/api/expenses/3' && c.method === 'PATCH');
  check('edit submit PATCHes the expense', !!patchCall);
  check('PATCH sends the form fields', !!patchCall && JSON.parse(patchCall.body).category === 'Supplies');
  check('form resets to add mode after save',
    named['#cost-form-title'].textContent === 'Log a purchase'
    && named['#cost-submit'].textContent === 'Add expense'
    && named['#cost-cancel'].classList.contains('hidden'));

  // 10. Cancel abandons editing without any API call.
  await Promise.all(costClickFns.map((fn) => fn(fakeEdit)));
  await tick(20);
  const callsBefore = fetchCalls.length;
  const cancelFns = named['#cost-cancel']._listeners.click || [];
  cancelFns.forEach((fn) => fn());
  check('cancel resets the form title', named['#cost-form-title'].textContent === 'Log a purchase');
  check('cancel makes no API call', fetchCalls.length === callsBefore);

  // 11. Expense rows carry seed-packet chips, suggestions, and the multi picker.
  const costRowsAfter = named['#costs-rows'].innerHTML;
  check('expense packet chip rendered', costRowsAfter.includes('data-pk-detach="expense:3:11"') && costRowsAfter.includes('Habanero'));
  check('expense multi checkbox panel rendered', costRowsAfter.includes('data-pk-check="expense:3:10"') && costRowsAfter.includes('data-pk-check="expense:3:11"'));
  check('expense linked packet pre-checked', costRowsAfter.includes('data-pk-check="expense:3:11" checked'));
  check('expense suggestion button rendered', costRowsAfter.includes('data-pk-attach="expense:3:10"') && costRowsAfter.includes('+ Costoluto Fiorentino'));

  // 12. Expense packet checkbox check/uncheck hits the expense endpoints.
  const costChangeFns = named['#costs-rows']._listeners.change || [];
  const fakeExpCheck = { target: { closest: () => ({ dataset: { pkCheck: 'expense:3:10' }, checked: true }) } };
  await Promise.all(costChangeFns.map((fn) => fn(fakeExpCheck)));
  await tick(80);
  const expCheckCall = fetchCalls.filter((c) => c.url === '/api/expenses/3/packets' && c.method === 'POST').pop();
  check('expense checkbox check attaches the packet', !!expCheckCall && JSON.parse(expCheckCall.body).seed_packet_id === 10);
  const fakeExpUncheck = { target: { closest: () => ({ dataset: { pkCheck: 'expense:3:11' }, checked: false }) } };
  await Promise.all(costChangeFns.map((fn) => fn(fakeExpUncheck)));
  await tick(80);
  check('expense checkbox uncheck detaches the packet', fetchCalls.some((c) => c.url === '/api/expenses/3/packets/11' && c.method === 'DELETE'));

  // 13. Expense suggestion one-tap attach POSTs to the expense endpoint.
  const fakeExpAttach = { target: { closest: (sel) => (sel === '[data-pk-attach]' ? { dataset: { pkAttach: 'expense:3:10' } } : null) } };
  await Promise.all(costClickFns.map((fn) => fn(fakeExpAttach)));
  await tick(80);
  const expAttachCall = fetchCalls.filter((c) => c.url === '/api/expenses/3/packets' && c.method === 'POST').pop();
  check('expense suggestion attach POSTs to expense packets endpoint', !!expAttachCall && JSON.parse(expAttachCall.body).seed_packet_id === 10);

  // 14. "Seed packets from items" derives packets: preview (no apply), then apply.
  check('derive button rendered for an invoice with items', rows.includes('data-derive="1"'));
  const fakeDerive = { target: { closest: (sel) => (sel === '[data-derive]' ? { dataset: { derive: '1' } } : null) } };
  await Promise.all(clickFns.map((fn) => fn(fakeDerive)));
  await tick(120);
  const deriveCalls = fetchCalls.filter((c) => c.url === '/api/invoices/1/derive-packets' && c.method === 'POST');
  check('derive posts a preview then an apply',
    deriveCalls.length === 2
    && !String(deriveCalls[0].body).includes('"apply":true')
    && String(deriveCalls[1].body).includes('"apply":true'));

  // 15. Books integrity badge renders from /api/books/check.
  const badge = named['#books-badge'].innerHTML;
  check('books badge fetched the check endpoint',
    fetchCalls.some((c) => c.url === '/api/books/check'));
  check('books badge shows an error summary', badge.includes('Books check') && badge.includes('1 error'));
  check('books badge lists the finding with a fix link',
    badge.includes('Invoice 9 total mismatch') && badge.includes('review invoice #9'));

  process.exit(failures ? 1 : 0);
})();

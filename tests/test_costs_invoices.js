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
['cost-form', 'cost-date', 'cost-category', 'cost-desc', 'cost-amount', 'cost-notes',
 'cost-plant', 'costs-rows', 'costs-empty', 'costs-total', 'costs-by-cat',
 'invoice-form', 'inv-vendor', 'inv-date', 'inv-order', 'inv-total', 'inv-items',
 'inv-expense', 'inv-notes', 'inv-pdf', 'invoices-rows', 'invoices-empty',
 'toasts'].forEach((id) => {
  named[`#${id}`] = makeEl();
});
named['#costs-empty'].classList.add('hidden');
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
global.fetch = async (url) => {
  let body = [];
  if (url === '/api/invoices/') body = invoices;
  else if (url === '/api/expenses/') body = expenses;
  return { ok: true, status: 200, json: async () => body };
};

const JS_FILES = ['core.js', 'costs.js'];
eval(fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'core.js'), 'utf8')); // eslint-disable-line no-eval
// Capture the boot callback instead of dispatching DOMContentLoaded (avoids
// boot()'s nav/frost wiring, which needs a fuller DOM).
const bootFns = [];
globalThis.Verdant.onBoot = (fn) => bootFns.push(fn);
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

  process.exit(failures ? 1 : 0);
})();

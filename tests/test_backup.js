/* Backup download button — harness for the fetch-driven download in backup.js. */
const path = require('path');

let failures = 0;
const seenToasts = [];
const clickedAnchors = [];
function check(name, ok) {
  if (ok) console.log(`ok   - ${name}`);
  else { failures++; console.log(`FAIL - ${name}`); }
}

function makeEl() {
  const classes = new Set();
  const listeners = {};
  return {
    style: {},
    dataset: {},
    disabled: false,
    textContent: '',
    value: '',
    innerHTML: '',
    files: [],
    _listeners: listeners,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, f) => { const on = f !== undefined ? f : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
  };
}

const named = {};
['backup-download', 'restore-form', 'restore-file', 'restore-submit', 'restore-result'].forEach((id) => {
  named['#' + id] = makeEl();
});
named['#backup-download'].textContent = '⬇ Download backup';

let exportMode = 'ok'; // 'ok' | 'fail'
global.fetch = async (url, options) => {
  if (url === '/api/backup/export') {
    if (exportMode === 'fail') {
      return { ok: false, status: 500, headers: { get: () => '' }, json: async () => ({ detail: 'boom' }) };
    }
    return {
      ok: true, status: 200,
      headers: { get: (h) => (h === 'Content-Disposition' ? 'attachment; filename="verdant-backup-20260926-120000.zip"' : '') },
      blob: async () => ({ size: 42 }),
      json: async () => ({}),
    };
  }
  return { ok: true, status: 200, headers: { get: () => '' }, json: async () => ({}) };
};
global.URL.createObjectURL = () => 'blob:fake-url';
global.URL.revokeObjectURL = () => {};

global.document = {
  readyState: 'complete',
  addEventListener: () => {},
  querySelector: (sel) => named[sel] || null,
  querySelectorAll: () => [],
  createElement: (tag) => {
    if (tag === 'a') {
      const a = { _href: '', download: '', click: () => clickedAnchors.push(a), remove: () => {} };
      Object.defineProperty(a, 'href', { get() { return this._href; }, set(v) { this._href = v; } });
      return a;
    }
    return makeEl();
  },
  body: { appendChild: () => {} },
};
global.window = { location: { pathname: '/backup' } };

globalThis.Verdant = {
  $: (sel) => named[sel] || null,
  $$: () => [],
  esc: (s) => String(s),
  api: {},
  toast: (m, kind) => seenToasts.push(`${kind || 'info'}:${m}`),
  onBoot: (fn) => fn(),
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require(path.join('/home/hatch/workspace/verdant/app/static/js/backup.js'));
  await tick(20);
  const btn = named['#backup-download'];

  // Success path.
  exportMode = 'ok';
  fire(btn, 'click');
  await tick(30);
  check('download uses the server filename', clickedAnchors.length === 1 && clickedAnchors[0].download === 'verdant-backup-20260926-120000.zip');
  check('success toast points at Downloads', seenToasts.some((t) => t.includes('Downloads')));
  check('button text restored after download', btn.textContent === '⬇ Download backup' && btn.disabled === false);

  // Failure path surfaces the server error.
  seenToasts.length = 0;
  clickedAnchors.length = 0;
  exportMode = 'fail';
  fire(btn, 'click');
  await tick(30);
  check('server error shown in toast', seenToasts.some((t) => t.includes('boom')));
  check('no download attempted on failure', clickedAnchors.length === 0);
  check('button text restored after failure', btn.textContent === '⬇ Download backup' && btn.disabled === false);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();

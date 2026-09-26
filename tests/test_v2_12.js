/* v2.12.0: seedling tracker workstation — DOM harness for seedlings.js. */
const path = require('path');

let failures = 0;
const seenToasts = [];
function check(name, ok) {
  if (ok) console.log(`ok   - ${name}`);
  else { failures++; console.log(`FAIL - ${name}`); }
}

const named = {};
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
    removeEventListener: () => {},
    focus: () => {},
    reset: () => {},
    scrollIntoView: () => {},
    setAttribute: () => {},
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: () => [],
    closest: () => null,
    textContent: '',
    value: '',
    innerHTML: '',
  };
  return el;
}

['panel-seedlings', 'seedling-form', 'seedling-form-title', 'seedling-id', 'seedling-variety',
 'seedling-varieties', 'seedling-sow', 'seedling-tray', 'seedling-location', 'seedling-light',
 'seedling-cells', 'seedling-packet', 'seedling-notes', 'seedling-heatmat', 'seedling-submit',
 'seedling-cancel', 'seedling-active', 'seedling-active-empty', 'seedling-done', 'seedling-done-empty',
].forEach((id) => { named['#' + id] = makeEl(); });

global.window = { location: { pathname: '/seedlings', origin: 'http://localhost:3119' }, confirm: () => true };
global.location = { search: '', origin: 'http://localhost:3119' };
global.document = {
  readyState: 'complete',
  addEventListener: () => {},
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
};
global.confirm = () => true;

const calls = { post: [], patch: [], del: [] };
const OLD = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10); // 30 days ago
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  const body = options && options.body && typeof options.body === 'string' ? JSON.parse(options.body) : null;
  if (method === 'POST') calls.post.push({ url, body });
  if (method === 'PATCH') calls.patch.push({ url, body });
  if (method === 'DELETE') calls.del.push({ url });
  let resp = {};
  if (url === '/api/seedling-batches/') resp = method === 'GET' ? [
    { id: 5, variety_name: 'Fatalii', sow_date: '2026-02-15', tray: 'Tray A', location: 'basement shelf',
      heat_mat: true, grow_light: 'LED 16h', cells_sown: 12, germinated: 8,
      germination_date: '2026-02-22', status: 'germinating', packet_id: 7, notes: '' },
    { id: 6, variety_name: 'Sungold', sow_date: OLD, tray: 'Tray B', location: '', heat_mat: false,
      grow_light: '', cells_sown: 6, germinated: 0, germination_date: '', status: 'sowing', packet_id: null, notes: '' },
    { id: 4, variety_name: 'Aji Pineapple', sow_date: '2026-02-01', tray: '', location: '', heat_mat: false,
      grow_light: '', cells_sown: 10, germinated: 9, germination_date: '2026-02-09',
      status: 'finished', transplant_date: '2026-04-20', packet_id: null, notes: 'Great germination.' },
  ] : { id: 99 };
  else if (url === '/api/seed-packets/') resp = [{ id: 7, variety_name: 'Fatalii', vendor_name: 'Baker Creek' }];
  else if (url.startsWith('/api/seedling-batches/5/sprout')) resp = { id: 5, status: 'germinating' };
  else if (url.startsWith('/api/seedling-batches/5/advance')) resp = { id: 5, status: 'growing' };
  else if (method !== 'GET') resp = { id: 99 };
  return { ok: true, status: method === 'POST' ? 201 : 200, json: async () => resp };
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
  api: {
    get: (p) => fetch(p).then((r) => r.json()),
    post: (p, j) => fetch(p, { method: 'POST', body: JSON.stringify(j) }).then((r) => r.json()),
    patch: (p, j) => fetch(p, { method: 'PATCH', body: JSON.stringify(j) }).then((r) => r.json()),
    del: (p) => fetch(p, { method: 'DELETE' }).then((r) => r.json()),
    upload: (p) => fetch(p, { method: 'POST', body: '{}' }).then((r) => r.json()),
  },
  toast: (m) => seenToasts.push(String(m)),
  fmtDate: (s) => s,
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));
const JS = (f) => path.join('/home/hatch/workspace/verdant/app/static/js', f);

(async () => {
  require(JS('seedlings.js'));
  await tick(30);
  const active = named['#seedling-active'].innerHTML;
  const done = named['#seedling-done'].innerHTML;

  check('active card renders variety + status pill', active.includes('Fatalii') && active.includes('Germinating'));
  check('germination bar shows 8/12 (67%)', active.includes('8/12 (67%)') && active.includes('width:67%'));
  check('days-to-germinate shown', active.includes('7 days to germinate'));
  check('heat mat chip renders', active.includes('warming mat'));
  check('stale batch gets a nudge', active.includes('No sprouts after 3+ weeks'));
  check('finished batch lands in done section', done.includes('Aji Pineapple') && done.includes('Finished'));
  check('variety datalist populated', named['#seedling-varieties'].innerHTML.includes('Fatalii'));
  check('packet picker lists stash packets', named['#seedling-packet'].innerHTML.includes('Baker Creek'));

  // One-tap sprout logging.
  const sproutBtn = { dataset: { sprout: '5' }, closest: (s) => (s === '[data-sprout]' ? sproutBtn : null) };
  fire(named['#panel-seedlings'], 'click', { target: { closest: (s) => sproutBtn.closest(s) } });
  await tick(30);
  check('sprout button posts count=1', calls.post.some((c) => c.url === '/api/seedling-batches/5/sprout?count=1'));

  // Advance to next stage.
  const advBtn = { dataset: { advance: '5' }, closest: (s) => (s === '[data-advance]' ? advBtn : null) };
  fire(named['#panel-seedlings'], 'click', { target: { closest: (s) => advBtn.closest(s) } });
  await tick(30);
  check('advance posts to /advance', calls.post.some((c) => c.url === '/api/seedling-batches/5/advance'));
  check('advance toast names the new stage', seenToasts.some((t) => t.includes('Growing')));

  // Start-batch form submit.
  named['#seedling-variety'].value = 'Habanero';
  named['#seedling-tray'].value = 'Tray C';
  named['#seedling-heatmat'].checked = true;
  fire(named['#seedling-form'], 'submit', { preventDefault: () => {} });
  await tick(30);
  const create = calls.post.find((c) => c.url === '/api/seedling-batches/');
  check('form submit creates batch', create && create.body.variety_name === 'Habanero' && create.body.heat_mat === true);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();

/* Seed packet library-photo picker: album/photo loading, attach flow, filter wiring. */
const path = require('path');

let failures = 0;
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
    files: [],
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    focus: () => {},
    closest: () => null,
    textContent: '',
    value: '',
    innerHTML: '',
  };
  return el;
}
for (const id of ['#packet-id', '#packet-form', '#library-side-label', '#library-album', '#library-grid',
  '#library-empty', '#library-modal', '#packet-library-front', '#packet-library-back',
  '#library-close', '#catalog-photo', '#packet-modal', '#catalog-grid', '#catalog-empty',
  '#catalog-search', '#catalog-category']) {
  named[id] = makeEl();
}
named['#packet-id'].value = '7';

global.window = { location: { pathname: '/seeds', origin: 'http://localhost:3119' }, confirm: () => true };
global.location = { search: '?tab=catalog', origin: 'http://localhost:3119' };
global.document = {
  readyState: 'complete',
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
};

const calls = { get: [], post: [] };
const toasts = [];
globalThis.Verdant = {
  $: (sel) => document.querySelector(sel),
  $$: (sel) => [...document.querySelectorAll(sel)],
  esc: (s) => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  api: {
    get: async (url) => {
      calls.get.push(url);
      if (url === '/api/albums') return [{ id: 3, name: 'Packet pics' }];
      if (url.startsWith('/api/album-images/')) {
        return [{ id: 42, file_path: '/uploads/albums/3/hab.jpg', title: 'Habanero packet', original_name: 'hab.jpg' }];
      }
      return [];
    },
    post: async (url, body) => {
      calls.post.push({ url, body });
      if (url === '/api/seed-packets/') return { id: 9 };
      return {};
    },
    patch: async () => ({}),
    del: async () => ({}),
    upload: async () => ({}),
  },
  toast: (msg, kind) => toasts.push({ msg, kind }),
};

const JS = (f) => path.join('/home/hatch/workspace/verdant/app/static/js', f);
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 20));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require(JS('seed_catalog.js'));

  // location.search has tab=catalog -> setTab('catalog') runs load(); wait for it
  await tick(50);

  check('photo filter select has a change listener',
    (named['#catalog-photo']._listeners.change || []).length > 0);
  check('library front/back buttons have click listeners',
    (named['#packet-library-front']._listeners.click || []).length > 0 &&
    (named['#packet-library-back']._listeners.click || []).length > 0);

  // Open the picker as "front"
  fire(named['#packet-library-front'], 'click');
  await tick(50);
  check('picker fetched albums and images',
    calls.get.includes('/api/albums') &&
    calls.get.some((u) => u.startsWith('/api/album-images/')));
  check('picker album dropdown lists the album',
    named['#library-album'].innerHTML.includes('Packet pics'));
  check('picker grid shows the library photo',
    named['#library-grid'].innerHTML.includes('data-lib-img="42"'));
  check('picker modal shown with front label',
    named['#library-modal'].classList.contains('flex') &&
    named['#library-side-label'].textContent.includes('front'));

  // Album filter change reloads images for that album
  named['#library-album'].value = '3';
  fire(named['#library-album'], 'change');
  await tick(50);
  check('album filter scopes image load',
    calls.get.some((u) => u.includes('album_id=3')));

  // Click the photo -> attaches as front of packet 7
  const btn = { dataset: { libImg: '42' } };
  fire(named['#library-grid'], 'click', { target: { closest: (sel) => (sel === '[data-lib-img]' ? btn : null) } });
  await tick(50);
  const attach = calls.post.find((c) => c.url.includes('photo-from-library'));
  check('photo click posts attach for packet 7 as front',
    !!attach && attach.url === '/api/seed-packets/7/photo-from-library' &&
    attach.body.image_id === 42 && attach.body.side === 'front');
  check('success toast shown', toasts.some((t) => /front photo set/i.test(t.msg)));
  check('picker closed after attach',
    !named['#library-modal'].classList.contains('flex'));

  // Back side label
  fire(named['#packet-library-back'], 'click');
  await tick(50);
  check('back button opens picker with back label',
    named['#library-side-label'].textContent.includes('back'));

  // ---- Add-form flow: pick stashes, submit attaches after create ----
  calls.post.length = 0;
  named['#packet-id'].value = ''; // new packet, no id yet
  fire(named['#packet-library-front'], 'click');
  await tick(50);
  const btn2 = { dataset: { libImg: '42' } };
  fire(named['#library-grid'], 'click', { target: { closest: (sel) => (sel === '[data-lib-img]' ? btn2 : null) } });
  await tick(50);
  check('new packet: library pick stashes instead of posting',
    !calls.post.some((c) => c.url.includes('photo-from-library')));
  check('new packet: toast says it attaches on save',
    toasts.some((t) => /when you save/i.test(t.msg)));
  check('new packet: front button shows pending check',
    named['#packet-library-front'].textContent.includes('✓'));

  fire(named['#packet-form'], 'submit', { preventDefault: () => {} });
  await tick(50);
  let attachCalls = calls.post.filter((c) => c.url.includes('photo-from-library'));
  check('save attaches stashed photo to the new packet',
    attachCalls.length === 1 &&
    attachCalls[0].url === '/api/seed-packets/9/photo-from-library' &&
    attachCalls[0].body.image_id === 42 && attachCalls[0].body.side === 'front');

  // Second save (nothing newly picked) must not re-attach.
  fire(named['#packet-form'], 'submit', { preventDefault: () => {} });
  await tick(50);
  attachCalls = calls.post.filter((c) => c.url.includes('photo-from-library'));
  check('no duplicate attach on second save', attachCalls.length === 1);

  console.log(failures ? `\n${failures} FAILURES` : '\nall seed library checks passed');
  process.exit(failures ? 1 : 0);
})();

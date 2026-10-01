/* Garden-assistant chat button test.
 * Drives ai_chat.js's boot with a stub DOM:
 *  1. the panel is a mobile slide-over (inset-y-0/right-0 sheet classes)
 *  2. a tap on the fab (pointer events, no drag) opens the chat panel
 *  3. dragging the fab moves it, persists the position, and does NOT open chat
 *  4. tapping the scrim closes the panel again
 *  5. a saved fab position is restored on boot
 * Run with: node tests/test_ai_chat_fab.js
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
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: () => makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { el._children.push(c); return c; },
    closest: () => null,
    remove: () => {},
    focus: () => { el._focused = true; },
    textContent: '',
    value: '',
    _children: [],
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'ai_chat.js'), 'utf8');

// Seed stub elements with the real classes from the markup the script injects,
// so the assertions below check the actual shipped HTML, not a copy of it.
function markupClasses(id) {
  const m = src.match(new RegExp(`id="${id}"[^>]*class="([^"]+)"`));
  return m ? m[1].split(/\s+/) : [];
}

// Card element whose querySelector returns stable per-selector stubs.
function makeCard() {
  const el = makeEl();
  const kids = {};
  el._kids = kids;
  el.querySelector = (sel) => {
    if (!kids[sel]) {
      kids[sel] = sel === '#ai-chat-fab' ? makeFab() : makeEl();
      const id = sel.replace(/^#/, '');
      markupClasses(id).forEach((c) => kids[sel]._classes.add(c));
    }
    return kids[sel];
  };
  return el;
}

// The chat button: tracks its own position like a fixed element would.
function makeFab() {
  const el = makeEl();
  el.offsetWidth = 56;
  el.offsetHeight = 56;
  el.setPointerCapture = () => {};
  el.getBoundingClientRect = () => {
    const x = parseFloat(el.style.left);
    const y = parseFloat(el.style.top);
    // Default corner before any drag: bottom-6 right-6 on a 1024x768 viewport.
    return {
      left: Number.isFinite(x) ? x : 1024 - 24 - 56,
      top: Number.isFinite(y) ? y : 768 - 24 - 56,
    };
  };
  return el;
}

function fire(el, type, props) {
  (el._listeners[type] || []).forEach((fn) => fn(Object.assign({ preventDefault: () => {} }, props)));
}

const store = new Map();
const localStorageStub = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => { store.set(k, String(v)); },
  removeItem: (k) => { store.delete(k); },
};
const sessionStorageStub = {
  getItem: () => null,
  setItem: () => {},
};

const api = {
  get: async (url) => {
    if (url === '/api/ai/chat-status') return { enabled: true, reachable: true, provider: 'ollama' };
    if (url === '/api/plants/') return [];
    return [];
  },
  post: async () => ({ id: 1 }),
};

globalThis.Verdant = {
  esc: (s) => String(s),
  api,
  toast: () => {},
  markdown: (s) => `<p>${s}</p>`,
  todayLocal: () => '2026-10-01',
};

const wrapEl = null; // (wrapper is captured from createElement below)
globalThis.document = {
  createElement: (tag) => (tag === 'div' ? makeCard() : makeEl()),
  body: makeEl(),
  readyState: 'complete',
  addEventListener: () => {},
};
// The script builds its UI into a wrapper div; capture that wrapper.
const realCreate = globalThis.document.createElement;
let bootWrap = null;
globalThis.document.createElement = (tag) => {
  const el = realCreate(tag);
  if (tag === 'div' && !bootWrap) bootWrap = el;
  return el;
};
globalThis.document.body.appendChild = (c) => c;

globalThis.window = {
  Verdant: globalThis.Verdant,
  matchMedia: () => ({ matches: true }),
  innerWidth: 1024,
  innerHeight: 768,
  setTimeout: (fn) => { fn(); return 0; },
  addEventListener: () => {},
};
globalThis.requestAnimationFrame = (fn) => { fn(); return 0; };
globalThis.localStorage = localStorageStub;
globalThis.sessionStorage = sessionStorageStub;


(async () => {
  eval(src);
  await tick(20);

  check('chat UI was built', !!bootWrap);
  const fab = bootWrap._kids['#ai-chat-fab'];
  const panel = bootWrap._kids['#ai-chat-panel'];
  const scrim = bootWrap._kids['#ai-chat-scrim'];
  check('fab, panel, and scrim exist', !!(fab && panel && scrim));

  const panelClasses = [...panel._classes].join(' ');
  check('panel is a mobile slide-over sheet',
    panelClasses.includes('inset-y-0') && panelClasses.includes('right-0') &&
    panelClasses.includes('max-w-sm') && panelClasses.includes('translate-x-full'));
  check('panel keeps the desktop floating-card classes',
    panelClasses.includes('sm:bottom-24') && panelClasses.includes('sm:w-[22rem]') &&
    panelClasses.includes('sm:rounded-2xl'));
  check('scrim is mobile-only', [...scrim._classes].join(' ').includes('sm:hidden'));

  // 2. Tap (no drag) opens the panel.
  fire(fab, 'pointerdown', { pointerId: 1, clientX: 100, clientY: 100 });
  fire(fab, 'pointermove', { pointerId: 1, clientX: 103, clientY: 104 });
  fire(fab, 'pointerup', { pointerId: 1, clientX: 103, clientY: 104 });
  check('tap opens the panel',
    !panel._classes.has('hidden') && panel._classes.has('flex') &&
    !panel._classes.has('translate-x-full'));
  check('scrim shows when panel is open', !scrim._classes.has('hidden'));
  check('fab hides while the panel is open', fab._classes.has('invisible'));

  // 4. Tapping the scrim closes the panel (setTimeout runs inline in the stub).
  fire(scrim, 'click', {});
  check('scrim tap closes the panel',
    panel._classes.has('hidden') && !panel._classes.has('flex') &&
    scrim._classes.has('hidden') && !fab._classes.has('invisible'));

  // 3. Dragging moves the fab, persists, and does not open the chat.
  fire(fab, 'pointerdown', { pointerId: 2, clientX: 200, clientY: 200 });
  fire(fab, 'pointermove', { pointerId: 2, clientX: 400, clientY: 500 });
  fire(fab, 'pointerup', { pointerId: 2, clientX: 400, clientY: 500 });
  check('drag sets an inline position on the fab',
    fab.style.left !== undefined && fab.style.left !== '' &&
    fab.style.top !== undefined && fab.style.top !== '');
  const saved = JSON.parse(store.get('verdant-ai-fab-pos') || 'null');
  check('drag persists the fab position', !!saved && Number.isFinite(saved.x) && Number.isFinite(saved.y));
  check('drag does not open the panel', panel._classes.has('hidden'));

  // 5. A fresh boot restores the saved position: load the script again so
  // boot() runs restoreFabPos() against the persisted value.
  let w2 = null;
  globalThis.document.createElement = (tag) => {
    const el = realCreate(tag);
    if (tag === 'div' && !w2) w2 = el;
    return el;
  };
  eval(src);
  await tick(20);
  const fabRestored = w2._kids['#ai-chat-fab'];
  check('saved fab position is restored on boot',
    fabRestored.style.left === `${saved.x}px` && fabRestored.style.top === `${saved.y}px`);

  // Drag clamps to the viewport: try to fling it far off-screen.
  fire(fabRestored, 'pointerdown', { pointerId: 3, clientX: 300, clientY: 300 });
  fire(fabRestored, 'pointermove', { pointerId: 3, clientX: 5000, clientY: 5000 });
  fire(fabRestored, 'pointerup', { pointerId: 3, clientX: 5000, clientY: 5000 });
  const lx = parseFloat(fabRestored.style.left);
  const ly = parseFloat(fabRestored.style.top);
  check('fab position is clamped to the viewport',
    lx <= 1024 - 56 - 8 && ly <= 768 - 56 - 8 && lx >= 8 && ly >= 8);

  if (failures) { console.log(`\n${failures} FAILURE(S)`); process.exit(1); }
  console.log('\nAll chat fab tests passed.');
})();

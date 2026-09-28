/* Navigation refresh (v2.28.0):
   - desktop grouped nav: 15 links, 4 labeled groups, no dropdowns, icon on every tab
   - mobile bottom tab bar: renders mobile_tabs picks (tap order) + fixed More,
     defaults when unset/invalid; More sheet lists everything else, no duplicates
   - Settings chip picker: toggles with max-4 enforcement, order numbers, PUT saves
*/
'use strict';
const fs = require('fs');

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

/* ---------------- tiny DOM ---------------- */
function makeEl(tag, attrs = {}) {
  const classes = new Set(String(attrs.class || '').split(/\s+/).filter(Boolean));
  const listeners = {};
  const el = {
    tag,
    attrs: { ...attrs },
    children: [],
    dataset: {},
    textContent: '',
    value: '',
    checked: false,
    disabled: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c, f) => {
        const on = f === undefined ? !classes.has(c) : !!f;
        if (on) classes.add(c); else classes.delete(c);
        return on;
      },
      contains: (c) => classes.has(c),
    },
    getAttribute: (n) => (n in el.attrs ? el.attrs[n] : null),
    setAttribute: (n, v) => { el.attrs[n] = String(v); },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    append: (child) => { el.children.push(child); },
    click: () => { (listeners.click || []).forEach((fn) => fn({ target: el, preventDefault() {} })); },
    fire: (t, e = {}) => { (listeners[t] || []).forEach((fn) => fn({ target: el, preventDefault() {}, ...e })); },
    closest: (sel) => (sel === '[data-key]' && el.attrs['data-key'] !== undefined ? el : null),
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

function parseLinks(html, ns) {
  const out = [];
  const re = /<a\s[^>]*href="([^"]+)"[^>]*>/g;
  let m;
  while ((m = re.exec(html))) {
    const key = ns + ':' + m[1];
    if (!linkCache[key]) linkCache[key] = makeEl('a', { href: m[1] });
    out.push(linkCache[key]);
  }
  return out;
}

const BASE = '/home/hatch/workspace/verdant';
const CORE = BASE + '/app/static/js/core.js';
const SETTINGS_JS = BASE + '/app/static/js/settings.js';
const baseHtml = fs.readFileSync(BASE + '/app/templates/base.html', 'utf8');
const desktopNavHtml = baseHtml.match(/<nav id="desktop-nav"[\s\S]*?<\/nav>/)[0];

/* ---------------- Phase A: template checks (no boot) ---------------- */
{
  const hrefs = [...desktopNavHtml.matchAll(/<a\s[^>]*href="([^"]+)"/g)].map((m) => m[1]);
  const expected = ['/', '/observations', '/calendar', '/photos', '/plants', '/seeds',
    '/seedlings', '/review', '/import', '/quick', '/costs', '/pests',
    '/fertilizers', '/planner', '/tags'];
  check('desktop nav has all 15 links', hrefs.length === 15 && expected.every((h) => hrefs.includes(h)));
  check('desktop nav has no dropdowns', !/<select/i.test(desktopNavHtml) && !/dropdown/i.test(desktopNavHtml));
  const labels = [...desktopNavHtml.matchAll(/nav-group-label">([^<]+)</g)].map((m) => m[1]);
  check('desktop nav has 4 labeled groups', JSON.stringify(labels) === JSON.stringify(['Grow', 'Track', 'Manage', 'Read']));
  const linkTexts = [...desktopNavHtml.matchAll(/<a\s[^>]*>([\s\S]*?)<\/a>/g)].map((m) => m[1]);
  const emojiRe = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
  check('every desktop tab has an icon', linkTexts.length === 15 && linkTexts.every((t) => emojiRe.test(t)));
  const mobileBlock = baseHtml.match(/<nav id="mobile-tabs"[\s\S]*?<\/nav>/)[0];
  check('mobile bar markup: no dropdowns', !/<select/i.test(mobileBlock) && !/dropdown/i.test(mobileBlock));
  const sheetBlock = baseHtml.match(/<div id="mobile-sheet"[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/);
  check('mobile sheet is a dialog, not a dropdown', !!sheetBlock && /role="dialog"/.test(baseHtml));
  check('safe-area padding present', /env\(safe-area-inset-bottom\)/.test(baseHtml));
}

/* ---------------- harness plumbing ---------------- */
const named = {};
const domListeners = {};
let linkCache = {};
let currentMobileTabs = '';
let capturedPut = null;
let fetchImpl = null;

function settingsPayload() {
  return {
    zone: '', frost_date: '', last_frost_date: '', garden_lat: '', garden_lon: '',
    temperature_unit: 'F', week_start: '0', default_weight_unit: 'oz',
    slideshow_interval: 5, confirm_water_all: true, digest_enabled: false,
    discord_webhook_url: '', digest_time: '08:00',
    mobile_tabs: currentMobileTabs, frost_preview: null,
  };
}

function resetDom() {
  for (const k of Object.keys(named)) delete named[k];
  for (const k of Object.keys(domListeners)) delete domListeners[k];
  linkCache = {};
  global.document.body = makeEl('body');
  capturedPut = null;
  const ids = ['#desktop-nav', '#mobile-tabs', '#mobile-tab-links', '#mobile-nav-more',
    '#mobile-sheet', '#mobile-sheet-backdrop', '#mobile-sheet-close', '#mobile-sheet-grid',
    '#frost-countdown', '#weather-ribbon', '#weather-ribbon-inner', '#app-version', '#toasts',
    '#settings-form', '#settings-status', '#mobile-tab-chips', '#mobile-tab-count',
    '#frost-preview', '#digest-test'];
  for (const id of ids) named[id] = makeEl('div');
  named['#desktop-nav'].innerHTML = desktopNavHtml;
  named['#mobile-sheet'].classList.add('hidden');
  fetchImpl = async (url, options = {}) => {
    if (url === '/api/settings' && (options.method || 'GET') === 'PUT') {
      capturedPut = JSON.parse(options.body);
      return { ok: true, status: 200, statusText: 'OK', json: async () => settingsPayload() };
    }
    return { ok: true, status: 200, statusText: 'OK', json: async () => settingsPayload() };
  };
}

global.document = {
  querySelector: (sel) => named[sel] || makeEl('div'),
  querySelectorAll: (sel) => {
    if (sel === 'nav a') {
      return [...parseLinks(named['#desktop-nav'].innerHTML, 'd'), ...parseLinks(named['#mobile-tab-links'].innerHTML, 'm')];
    }
    return [];
  },
  addEventListener: (t, fn) => { (domListeners[t] = domListeners[t] || []).push(fn); },
  createElement: () => makeEl('div'),
  documentElement: { dataset: { version: '2.28.0' } },
  body: makeEl('body'),
};
global.window = { location: { pathname: '/' }, addEventListener: () => {} };
global.fetch = (url, options) => fetchImpl(url, options);

const tick = (ms = 5) => new Promise((r) => setTimeout(r, ms));
async function bootFresh(withSettings) {
  delete require.cache[require.resolve(CORE)];
  delete require.cache[require.resolve(SETTINGS_JS)];
  require(CORE);
  if (withSettings) require(SETTINGS_JS);
  for (const fn of domListeners['DOMContentLoaded'] || []) await fn();
  await tick(30); // let async inits (getSettings, load()) settle
}

function tabHrefs() {
  return [...named['#mobile-tab-links'].innerHTML.matchAll(/<a\s[^>]*href="([^"]+)"[^>]*data-tab="([^"]+)"/g)]
    .map((m) => m[2]);
}
function sheetHrefs() {
  return [...named['#mobile-sheet-grid'].innerHTML.matchAll(/<a\s[^>]*href="([^"]+)"/g)].map((m) => m[1]);
}
function sheetOpen() { return !named['#mobile-sheet'].classList.contains('hidden'); }

(async () => {
  /* ---------------- Phase B: mobile bar behavior ---------------- */

  // B1: defaults when unset
  resetDom(); currentMobileTabs = ''; window.location.pathname = '/';
  await bootFresh(false);
  check('default tabs: quick,plants,calendar,planner in order',
    JSON.stringify(tabHrefs()) === JSON.stringify(['quick', 'plants', 'calendar', 'planner']));
  check('More button present after tabs', !!named['#mobile-nav-more']);
  {
    const sh = sheetHrefs();
    check('sheet lists the other 11, no duplicates',
      sh.length === 11 && !['/quick', '/plants', '/calendar', '/planner'].some((h) => sh.includes(h)));
  }

  // B2: custom picks respected in tap order; sheet excludes them
  resetDom(); currentMobileTabs = '["planner","costs","seeds"]'; window.location.pathname = '/';
  await bootFresh(false);
  check('custom tabs render in tap order',
    JSON.stringify(tabHrefs()) === JSON.stringify(['planner', 'costs', 'seeds']));
  {
    const sh = sheetHrefs();
    check('sheet excludes picked tabs (12 left)',
      sh.length === 12 && !['/planner', '/costs', '/seeds'].some((h) => sh.includes(h))
      && ['/quick', '/plants', '/calendar'].every((h) => sh.includes(h)));
  }

  // B3: invalid setting falls back to defaults; dupes are deduped like the backend
  for (const bad of ['["nope"]', 'not-json', '"quick"']) {
    resetDom(); currentMobileTabs = bad; window.location.pathname = '/';
    await bootFresh(false);
    check(`invalid mobile_tabs falls back to defaults (${bad})`,
      JSON.stringify(tabHrefs()) === JSON.stringify(['quick', 'plants', 'calendar', 'planner']));
  }
  resetDom(); currentMobileTabs = '["quick","quick","seeds","quick"]'; window.location.pathname = '/';
  await bootFresh(false);
  check('duplicate keys dedupe, order kept',
    JSON.stringify(tabHrefs()) === JSON.stringify(['quick', 'seeds']));

  // B4: sheet open/close
  resetDom(); currentMobileTabs = ''; window.location.pathname = '/';
  await bootFresh(false);
  named['#mobile-nav-more'].click();
  check('More opens the sheet', sheetOpen());
  check('body scroll locked while open', document.body.classList.contains('overflow-hidden'));
  named['#mobile-sheet-close'].click();
  check('close button closes the sheet', !sheetOpen());
  named['#mobile-nav-more'].click();
  named['#mobile-sheet-backdrop'].click();
  check('backdrop tap closes the sheet', !sheetOpen());
  named['#mobile-nav-more'].click();
  for (const fn of domListeners['keydown'] || []) fn({ key: 'Escape' });
  check('Escape closes the sheet', !sheetOpen());

  // B5: active states
  resetDom(); currentMobileTabs = ''; window.location.pathname = '/plants';
  await bootFresh(false);
  {
    const mobile = parseLinks(named['#mobile-tab-links'].innerHTML, 'm');
    const plants = mobile.find((l) => l.getAttribute('href') === '/plants');
    check('mobile Plants tab marked active', plants.classList.contains('bg-sage-600'));
    const desktop = parseLinks(named['#desktop-nav'].innerHTML, 'd');
    const dPlants = desktop.find((l) => l.getAttribute('href') === '/plants');
    check('desktop Plants tab still marked active', dPlants.classList.contains('bg-sage-600'));
  }
  resetDom(); currentMobileTabs = ''; window.location.pathname = '/costs';
  await bootFresh(false);
  {
    const mobile = parseLinks(named['#mobile-tab-links'].innerHTML, 'm');
    check('no mobile tab active when page is in More',
      mobile.every((l) => !l.classList.contains('bg-sage-600')));
  }

  /* ---------------- Phase C: Settings chip picker ---------------- */
  const chipState = () => [...named['#mobile-tab-chips'].innerHTML.matchAll(
    /<button[^>]*data-key="([^"]+)"[^>]*aria-pressed="(true|false)"[^>]*>[\s\S]*?<span class="tab-chip-order"( hidden)?>([^<]*)<\/span>/g)]
    .map((m) => ({ key: m[1], on: m[2] === 'true', order: m[4] }));
  const clickChip = (key) => {
    const btn = makeEl('button', { 'data-key': key });
    named['#mobile-tab-chips'].fire('click', { target: btn });
  };

  resetDom(); currentMobileTabs = ''; window.location.pathname = '/settings';
  await bootFresh(true);
  {
    const chips = chipState();
    check('15 chips rendered, none pressed by default',
      chips.length === 15 && chips.every((c) => !c.on));
  }
  clickChip('quick');
  clickChip('plants');
  {
    const chips = chipState();
    const q = chips.find((c) => c.key === 'quick');
    const p = chips.find((c) => c.key === 'plants');
    check('chips toggle on with order numbers 1,2', q.on && q.order === '1' && p.on && p.order === '2');
  }
  clickChip('quick'); // deselect
  {
    const chips = chipState();
    const q = chips.find((c) => c.key === 'quick');
    const p = chips.find((c) => c.key === 'plants');
    check('deselect renumbers remaining pick to 1', !q.on && p.on && p.order === '1');
  }
  // max 4
  clickChip('quick'); clickChip('calendar'); clickChip('planner'); // now plants,quick,calendar,planner = 4
  const toastsBefore = named['#toasts'].children.length;
  clickChip('costs');
  {
    const chips = chipState();
    check('max 4 enforced (5th tap rejected)',
      chips.filter((c) => c.on).length === 4 && !chips.find((c) => c.key === 'costs').on);
    check('toast shown on over-pick', named['#toasts'].children.length === toastsBefore + 1);
  }
  // save PUTs the array in tap order
  named['#settings-form'].fire('submit');
  await tick(30);
  check('save PUTs mobile_tabs JSON in tap order',
    capturedPut && capturedPut.mobile_tabs === JSON.stringify(['plants', 'quick', 'calendar', 'planner']));

  // existing picks load pressed with order
  resetDom(); currentMobileTabs = '["seeds","planner"]'; window.location.pathname = '/settings';
  await bootFresh(true);
  {
    const chips = chipState();
    const s = chips.find((c) => c.key === 'seeds');
    const p = chips.find((c) => c.key === 'planner');
    check('existing picks load pressed with order numbers',
      s.on && s.order === '1' && p.on && p.order === '2');
    check('count line shows picks', /2 of 4/.test(named['#mobile-tab-count'].textContent));
  }

  console.log(failures === 0 ? '\nALL NAV CHECKS PASSED' : `\n${failures} FAILURES`);
  process.exit(failures === 0 ? 0 : 1);
})();

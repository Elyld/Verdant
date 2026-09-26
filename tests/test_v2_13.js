/* v2.13.0: measurement cleanup — DOM harness for core helpers, settings
   temperature unit, and the split yield leaderboard on the review page. */
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

global.window = { location: { pathname: '/settings', origin: 'http://localhost:3119' }, confirm: () => true };
global.location = { search: '', origin: 'http://localhost:3119' };
global.document = {
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
};

const JS = (f) => path.join('/home/hatch/workspace/verdant/app/static/js', f);
const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  /* ---- core.js pure helpers (fmtAmount, fmtTemp) ---- */
  require(JS('core.js'));
  const { fmtAmount, fmtTemp } = globalThis.Verdant;

  check('fmtAmount prefers structured value+unit',
    fmtAmount({ amount_value: 2, amount_unit: 'gal', amount: '2 gal' }) === '2 gal');
  check('fmtAmount handles tbsp',
    fmtAmount({ amount_value: 1.5, amount_unit: 'tbsp', amount: '' }) === '1.5 tbsp');
  check('fmtAmount falls back to free text',
    fmtAmount({ amount_value: null, amount_unit: null, amount: 'a good soak' }) === 'a good soak');
  check('fmtAmount falls back to amount_used',
    fmtAmount({ amount_value: null, amount_unit: null, amount_used: '10-10-10' }) === '10-10-10');
  check('fmtTemp converts C->F', fmtTemp(20, 'F') === '68°F');
  check('fmtTemp keeps C', fmtTemp(20, 'C') === '20°C');
  check('fmtTemp handles null', fmtTemp(null, 'F') === '');

  /* ---- settings: temperature unit loads + saves ---- */
  ['settings-form', 'set-zone', 'set-first-frost', 'set-last-frost', 'set-temp-unit',
   'set-digest-enabled', 'set-webhook', 'set-digest-time', 'settings-status',
   'frost-preview', 'digest-test'].forEach((id) => { named['#' + id] = makeEl(); });

  const apiCalls = [];
  const settingsResp = {
    zone: '7a', frost_date: '2026-10-20', last_frost_date: '2026-04-15',
    temperature_unit: 'C', digest_enabled: false, discord_webhook_url: '', digest_time: '08:00',
  };
  globalThis.Verdant.api = {
    get: async (url) => {
      apiCalls.push({ method: 'get', url });
      if (url === '/api/settings') return settingsResp;
      return {};
    },
    put: async (url, body) => { apiCalls.push({ method: 'put', url, body }); return {}; },
    post: async (url, body) => { apiCalls.push({ method: 'post', url, body }); return {}; },
  };
  globalThis.Verdant.toast = (m, t) => console.log('TOAST', t, m);
  globalThis.Verdant.onBoot = (fn) => fn();

  require(JS('settings.js'));
  await tick(30);

  check('settings form prefills temperature unit from API',
    named['#set-temp-unit'].value === 'C');

  named['#set-temp-unit'].value = 'F';
  fire(named['#settings-form'], 'submit', { preventDefault: () => {} });
  await tick(30);
  const saved = apiCalls.find((c) => c.method === 'put' && c.url === '/api/settings');
  check('settings save includes temperature_unit', saved && saved.body.temperature_unit === 'F');

  /* ---- review: split yield leaderboard ---- */
  ['review-year', 'review-stats', 'review-activity', 'review-health', 'review-highlights',
   'review-yield-empty', 'review-yield-weight', 'review-yield-count',
   'review-prev', 'review-next', 'scorecard-empty', 'scorecard-summary', 'scorecard-rows']
    .forEach((id) => { named['#' + id] = makeEl(); });

  globalThis.Verdant.api.get = async (url) => {
    apiCalls.push({ method: 'get', url });
    if (url.startsWith('/api/stats/review')) {
      return {
        observations: 42, observations_by_month: Array(12).fill(3),
        avg_health_by_month: Array(12).fill(8), harvest_weight: 24, harvest_count: 6,
        photos: 10, waterings: 100, feedings: 20, pests_noted: 2,
        busiest_day: '2026-07-04', busiest_day_count: 5, top_plants: [],
      };
    }
    if (url.startsWith('/api/stats/yield')) {
      return {
        by_weight: [
          { variety_name: 'Habanero', total_oz: 12, harvest_count: 3 },
          { variety_name: 'Fatalii', total_oz: 8.5, harvest_count: 2 },
        ],
        by_count: [
          { variety_name: 'Sungold', total_quantity: 40, unit: 'pieces', harvest_count: 5 },
        ],
      };
    }
    if (url.startsWith('/api/stats/scorecard')) {
      return { total_spent: 50, total_oz: 20.5, unassigned_spent: 0, varieties: [] };
    }
    return {};
  };

  require(JS('review.js'));
  await tick(30);

  const weightHtml = named['#review-yield-weight'].innerHTML;
  const countHtml = named['#review-yield-count'].innerHTML;
  check('by-weight board lists weighed varieties with oz',
    weightHtml.includes('Habanero') && weightHtml.includes('12 oz'));
  check('by-weight board does not leak piece-count rows',
    !weightHtml.includes('Sungold'));
  check('by-count board lists piece counts with their unit',
    countHtml.includes('Sungold') && countHtml.includes('40 pieces'));
  check('by-count board does not leak weighed rows',
    !countHtml.includes('Habanero'));
  check('leaderboard shows medals', weightHtml.includes('🥇'));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})();

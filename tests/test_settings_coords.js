/* Settings page: garden coordinates fields + "Use my location" button. */
'use strict';
const path = require('path');

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
    checked: false,
    disabled: false,
    value: '',
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    setAttribute: () => {},
    querySelector: () => makeEl(),
    textContent: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  el._listeners = listeners;
  return el;
}

const named = {};
['settings-form', 'settings-status', 'set-zone', 'set-first-frost', 'set-last-frost',
 'set-lat', 'set-lon', 'set-locate', 'set-temp-unit', 'set-week-start', 'set-weight-unit',
 'set-digest-enabled', 'set-digest-time', 'set-webhook', 'set-slideshow-interval',
 'set-confirm-water-all', 'frost-preview', 'settings-save', 'digest-test',
 'digest-enabled-card', 'toasts',
].forEach((id) => { named[`#${id}`] = makeEl(); });

const requests = [];
const settingsPayload = {
  zone: '6b', frost_date: '2026-10-15', last_frost_date: '2026-04-10',
  garden_lat: '30.2672', garden_lon: '-97.7431',
  temperature_unit: 'F', week_start: 'sunday', default_weight_unit: 'oz',
  digest_enabled: false, discord_webhook_url: '', digest_time: '07:00',
  slideshow_interval: 5, confirm_water_all: true,
};

global.fetch = async (url, options = {}) => {
  requests.push({ url, method: options.method || 'GET', body: options.body });
  let resp = {};
  if (url === '/api/settings') resp = settingsPayload;
  else if (url === '/api/weather/geolocate') resp = { ok: true, lat: 35.5, lon: -95.5, city: 'Tulsa' };
  else if (url === '/api/digest/preview') resp = { ok: true, preview: {} };
  return { ok: true, status: 200, json: async () => resp };
};

const toasts = [];
globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s == null ? '' : s),
  api: {
    get: (p) => fetch(p).then((r) => r.json()),
    post: (p, j) => fetch(p, { method: 'POST', body: JSON.stringify(j) }).then((r) => r.json()),
    put: (p, j) => fetch(p, { method: 'PUT', body: JSON.stringify(j) }).then((r) => r.json()),
  },
  toast: (msg, kind) => { toasts.push({ msg, kind }); },
  onBoot: (fn) => { globalThis.__boot = fn; },
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require(path.join(__dirname, '..', 'app', 'static', 'js', 'settings.js'));
  globalThis.__boot();
  await tick(30);

  check('lat/lon fields populated from settings', named['#set-lat'].value === '30.2672' && named['#set-lon'].value === '-97.7431');

  // Save includes the coordinates.
  requests.length = 0;
  named['#set-lat'].value = '38.9';
  named['#set-lon'].value = '-94.7';
  fire(named['#settings-form'], 'submit');
  await tick(30);
  const put = requests.find((r) => r.method === 'PUT' && r.url === '/api/settings');
  const body = JSON.parse(put.body);
  check('save PUTs garden_lat/garden_lon', body.garden_lat === '38.9' && body.garden_lon === '-94.7');

  // Locate button: browser geolocation success path.
  Object.defineProperty(globalThis, 'navigator', {
    value: {
      geolocation: {
        getCurrentPosition: (ok) => ok({ coords: { latitude: 40.7128, longitude: -74.006 } }),
      },
    },
    configurable: true, writable: true,
  });
  named['#set-lat'].value = '';
  named['#set-lon'].value = '';
  toasts.length = 0;
  fire(named['#set-locate'], 'click');
  await tick(30);
  check('geolocation fills the fields', named['#set-lat'].value === '40.71280' && named['#set-lon'].value === '-74.00600');
  check('geolocation toast mentions browser', toasts.some((t) => t.msg.includes('from your browser')));

  // Locate button: geolocation failure → ip-api fallback fills the fields.
  Object.defineProperty(globalThis, 'navigator', {
    value: undefined, configurable: true, writable: true,
  });
  requests.length = 0;
  named['#set-lat'].value = '';
  named['#set-lon'].value = '';
  toasts.length = 0;
  fire(named['#set-locate'], 'click');
  await tick(30);
  check('fallback hits /api/weather/geolocate', requests.some((r) => r.url === '/api/weather/geolocate'));
  check('fallback fills city-level coords', named['#set-lat'].value === '35.5000' && named['#set-lon'].value === '-95.5000');
  check('fallback toast mentions city-level', toasts.some((t) => t.msg.includes('city-level')));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

/* NOAA alert pill + panel in the weather ribbon (core.js initNoaaAlerts):
   pill appears severity-tinted when alerts are active; clicking toggles the
   panel; nothing renders when there are no alerts or coords are unset. */
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
  const children = [];
  const el = {
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c) => { const had = classes.has(c); had ? classes.delete(c) : classes.add(c); return !had; },
      contains: (c) => classes.has(c),
    },
    children,
    appendChild: (c) => { children.push(c); return c; },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    click: () => { (listeners.click || []).forEach((fn) => fn()); },
    setAttribute: (k, v) => { el['attr:' + k] = v; },
    getAttribute: (k) => el['attr:' + k],
    textContent: '',
    dataset: {},
    id: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  // Real DOM links className <-> classList; mirror that here.
  Object.defineProperty(el, 'className', {
    get: () => [...classes].join(' '),
    set: (v) => { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach((x) => classes.add(x)); },
  });
  return el;
}

const named = {};
const domListeners = {};
let fetchImpl = async () => ({ ok: true, status: 200, json: async () => ({}) });

function resetDom() {
  for (const k of Object.keys(named)) delete named[k];
  named['#weather-ribbon'] = makeEl();
  named['#weather-ribbon-inner'] = makeEl();
  named['#frost-countdown'] = makeEl();
  named['#weather-ribbon'].classList.add('hidden');
  named['#frost-countdown'].classList.add('hidden');
  for (const k of Object.keys(domListeners)) delete domListeners[k];
}

global.document = {
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: (t, fn) => { (domListeners[t] = domListeners[t] || []).push(fn); },
  createElement: () => makeEl(),
  documentElement: { dataset: { version: '2.29.0' } },
};
global.window = { location: { pathname: '/' }, addEventListener: () => {} };
global.fetch = (url, options) => fetchImpl(url, options);

const CORE = path.join(__dirname, '..', 'app/static/js/core.js');
const tick = (ms) => new Promise((r) => setTimeout(r, ms));
function bootFresh() {
  delete require.cache[require.resolve(CORE)];
  require(CORE);
  return Promise.all((domListeners['DOMContentLoaded'] || []).map((fn) => fn()));
}

const GOOD_FORECAST = {
  ok: true, temp_unit: 'F',
  forecast: {
    as_of: '2026-09-28T06:10',
    current: { temp_f: 72, summary: 'Clear' },
    hourly: [],
    daily: [{ date: '2026-09-28', tmin_f: 58 }, { date: '2026-09-29', tmax_f: 81 }],
  },
};

const ALERTS = {
  ok: true,
  alerts: [
    { event: 'Freeze Warning', headline: 'Freeze Warning issued', severity: 'Severe',
      onset: '2026-10-13T01:00:00-05:00', ends: '2026-10-13T09:00:00-05:00',
      description: 'Sub-freezing temperatures as low as 28 expected.' },
    { event: 'Wind Advisory', headline: '', severity: 'Moderate',
      onset: null, ends: null, description: 'Gusty winds.' },
  ],
};

function mockFetch({ forecast = GOOD_FORECAST, alerts = ALERTS, frost = {} } = {}) {
  fetchImpl = async (url) => {
    let resp = {};
    if (url === '/api/weather/forecast') resp = forecast;
    else if (url === '/api/weather/noaa-alerts') resp = alerts;
    else if (url === '/api/stats/frost') resp = frost;
    return { ok: true, status: 200, json: async () => resp };
  };
}

(async () => {
  // Scenario 1: alerts active — severity-tinted pill + toggleable panel.
  resetDom();
  mockFetch();
  await bootFresh();
  await tick(30);
  const inner = named['#weather-ribbon-inner'];
  const ribbon = named['#weather-ribbon'];
  const pill = inner.children.find((c) => c.id === 'noaa-pill');
  const panel = ribbon.children.find((c) => c.id === 'noaa-panel');
  check('pill rendered when alerts active', !!pill);
  check('pill shows worst event first', pill && pill.innerHTML.includes('Freeze Warning'));
  check('pill counts extra alerts', pill && pill.innerHTML.includes('+1'));
  check('pill tinted for Severe', pill && pill.className.includes('bg-red-700'));
  check('panel rendered but hidden', !!panel && panel.classList.contains('hidden'));
  check('panel lists both alerts', panel && panel.innerHTML.includes('Freeze Warning') && panel.innerHTML.includes('Wind Advisory'));
  check('panel shows timing + description', panel && panel.innerHTML.includes('Sub-freezing'));
  check('ribbon visible', !ribbon.classList.contains('hidden'));
  pill.click();
  check('panel opens on pill click', !panel.classList.contains('hidden'));
  check('aria-expanded flips', pill.getAttribute('aria-expanded') === 'true');
  pill.click();
  check('panel closes on second click', panel.classList.contains('hidden'));

  // Scenario 2: no alerts — no pill, no panel, ribbon still shows forecast.
  resetDom();
  mockFetch({ alerts: { ok: true, alerts: [] } });
  await bootFresh();
  await tick(30);
  check('no pill when no alerts',
    !named['#weather-ribbon-inner'].children.some((c) => c.id === 'noaa-pill'));
  check('no panel when no alerts',
    !named['#weather-ribbon'].children.some((c) => c.id === 'noaa-panel'));
  check('ribbon still shows forecast', !named['#weather-ribbon'].classList.contains('hidden'));

  // Scenario 3: alerts endpoint down — page never breaks.
  resetDom();
  fetchImpl = async (url) => {
    if (url === '/api/weather/noaa-alerts') throw new Error('nws down');
    if (url === '/api/weather/forecast') return { ok: true, status: 200, json: async () => GOOD_FORECAST };
    return { ok: true, status: 200, json: async () => ({}) };
  };
  let threw = false;
  try { await bootFresh(); await tick(30); } catch { threw = true; }
  check('no throw when alerts fetch fails', !threw);
  check('no pill when alerts fetch fails',
    !named['#weather-ribbon-inner'].children.some((c) => c.id === 'noaa-pill'));

  // Scenario 4: Moderate top severity → amber tint.
  resetDom();
  mockFetch({ alerts: { ok: true, alerts: [ALERTS.alerts[1]] } });
  await bootFresh();
  await tick(30);
  const pill4 = named['#weather-ribbon-inner'].children.find((c) => c.id === 'noaa-pill');
  check('moderate alert → amber pill', !!pill4 && pill4.className.includes('bg-amber-400'));

  console.log(failures === 0 ? '\nAll checks passed.' : `\n${failures} FAILURES`);
  process.exit(failures === 0 ? 0 : 1);
})();

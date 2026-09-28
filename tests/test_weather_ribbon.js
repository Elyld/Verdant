/* Global weather ribbon (core.js initWeatherRibbon): renders on every page
   from the cached forecast endpoint, stays hidden when coordinates are
   unconfigured or the fetch fails. */
'use strict';

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

function makeEl() {
  const classes = new Set();
  const el = {
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
    },
    textContent: '',
    dataset: {},
    addEventListener: () => {},
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
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
  documentElement: { dataset: { version: '2.27.0' } },
};
global.window = { location: { pathname: '/' }, addEventListener: () => {} };
global.fetch = (url, options) => fetchImpl(url, options);

const CORE = '/home/hatch/workspace/verdant/app/static/js/core.js';
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
    daily: [
      { date: '2026-09-28', tmin_f: 58 },
      { date: '2026-09-29', tmax_f: 81, precip_prob: 10, gust_mph: 12 },
    ],
  },
};

(async () => {
  // Scenario 1: configured — ribbon renders with the forecast.
  resetDom();
  fetchImpl = async (url) => {
    let resp = {};
    if (url === '/api/weather/forecast') resp = GOOD_FORECAST;
    else if (url === '/api/stats/frost') resp = { days_until: 21 };
    return { ok: true, status: 200, json: async () => resp };
  };
  await bootFresh();
  await tick(30);
  const ribbon = named['#weather-ribbon'];
  const inner = named['#weather-ribbon-inner'];
  check('ribbon shown when forecast ok', !ribbon.classList.contains('hidden'));
  check('ribbon shows current temp + summary', inner.innerHTML.includes('72°F') && inner.innerHTML.includes('Clear'));
  check('ribbon shows tonight low', inner.innerHTML.includes('Tonight 58°F'));
  check('ribbon shows tomorrow high', inner.innerHTML.includes('Tomorrow 81°F'));
  check('ribbon shows rain + wind', inner.innerHTML.includes('10%') && inner.innerHTML.includes('12 mph'));
  check('ribbon shows as-of time', inner.innerHTML.includes('as of'));
  check('frost pill still works (regression)', !named['#frost-countdown'].classList.contains('hidden') &&
    named['#frost-countdown'].textContent.includes('21d to first frost'));

  // Scenario 2: not configured — ribbon stays hidden, no nagging.
  resetDom();
  fetchImpl = async (url) => {
    const resp = url === '/api/weather/forecast'
      ? { ok: false, reason: 'not-configured', hint: 'Set coordinates.' }
      : {};
    return { ok: true, status: 200, json: async () => resp };
  };
  await bootFresh();
  await tick(30);
  check('ribbon hidden when unconfigured', named['#weather-ribbon'].classList.contains('hidden'));
  check('ribbon body untouched when unconfigured', named['#weather-ribbon-inner'].innerHTML === '');

  // Scenario 3: fetch blows up — ribbon stays hidden, page never breaks.
  resetDom();
  fetchImpl = async (url) => {
    if (url === '/api/weather/forecast') throw new Error('network down');
    return { ok: true, status: 200, json: async () => ({}) };
  };
  let threw = false;
  try {
    await bootFresh();
    await tick(30);
  } catch { threw = true; }
  check('no throw when forecast fetch fails', !threw);
  check('ribbon hidden on fetch failure', named['#weather-ribbon'].classList.contains('hidden'));

  // Scenario 4: Celsius unit honored.
  resetDom();
  fetchImpl = async (url) => {
    let resp = {};
    if (url === '/api/weather/forecast') resp = {
      ok: true, temp_unit: 'C',
      forecast: {
        as_of: '2026-09-28T06:10',
        current: { temp_c: 22, summary: 'Clear' },
        hourly: [],
        daily: [{ date: '2026-09-28', tmin_c: 14 }, { date: '2026-09-29', tmax_c: 27 }],
      },
    };
    return { ok: true, status: 200, json: async () => resp };
  };
  await bootFresh();
  await tick(30);
  const innerC = named['#weather-ribbon-inner'].innerHTML;
  check('celsius unit honored', innerC.includes('22°C') && innerC.includes('Tomorrow 27°C'));

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

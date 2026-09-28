/* Today view — the morning-glance page. */
(() => {
  'use strict';

  const { $, esc, api, fmtDate, toast } = globalThis.Verdant;

  function initToday() {
    if (!$('#today-due')) return;

    $('#today-date').textContent = new Date().toLocaleDateString(undefined, {
      weekday: 'long', month: 'long', day: 'numeric',
    });
    const hour = new Date().getHours();
    const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    $('#today-greeting').textContent = `☀️ ${greet}`;

    loadWeather().catch(() => {});
    loadAlerts().catch(() => {});
    loadToday().catch((error) => toast(`Could not load Today: ${error.message}`, 'err'));
  }

  async function loadWeather() {
    const card = $('#today-weather');
    const fc = await api.get('/api/weather/forecast');
    if (!fc || !fc.ok || !fc.forecast || !fc.forecast.current) return; // not configured — stay quiet
    const unit = fc.temp_unit === 'C' ? 'C' : 'F';
    const t = (v) => (v == null ? '—' : `${Math.round(v)}°${unit}`);
    const cur = fc.forecast.current;
    const days = fc.forecast.daily || [];
    const tonight = days[0] || {};
    const tomorrow = days[1] || {};
    card.classList.remove('hidden');
    card.innerHTML = `
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <p class="font-display text-3xl font-semibold text-navy-800">${t(cur.temp_c ?? cur.temp_f)}</p>
        <p class="text-sm text-navy-500">${esc(cur.summary || '')}</p>
        <div class="ml-auto flex flex-wrap gap-x-4 gap-y-1 text-sm text-navy-600">
          <span>🌙 Tonight ${t(tonight.tmin_c ?? tonight.tmin_f)}</span>
          <span>☀️ Tomorrow ${t(tomorrow.tmax_c ?? tomorrow.tmax_f)}</span>
          <span>💧 ${tomorrow.precip_prob != null ? `${tomorrow.precip_prob}%` : '—'}</span>
        </div>
      </div>`;
  }

  async function loadAlerts() {
    const host = $('#today-alerts');
    const res = await api.get('/api/weather/noaa-alerts');
    const alerts = (res && res.alerts) || [];
    if (!alerts.length) return;
    host.innerHTML = alerts.map((a) => `
      <div class="rounded-xl bg-amber-50 px-4 py-3 ring-1 ring-amber-300">
        <p class="text-sm font-semibold text-amber-900">⚠️ ${esc(a.event || 'Weather alert')}</p>
        ${a.headline ? `<p class="mt-1 text-sm text-amber-800">${esc(a.headline)}</p>` : ''}
      </div>`).join('');
  }

  async function loadToday() {
    const data = await api.get('/api/today');
    if (!data || !data.ok) throw new Error('bad response');

    const dueHost = $('#today-due');
    const due = data.due || [];
    dueHost.innerHTML = due.length
      ? due.map((r) => {
          const what = r.kind === 'water' ? '💧 Water' : '🌱 Feed';
          const when = r.status === 'overdue'
            ? `<span class="font-semibold text-red-700">${Math.abs(r.days_until_due)}d overdue</span>`
            : 'due today';
          return `<li class="flex items-center justify-between gap-2 rounded-lg bg-beige-50 px-3 py-2 ring-1 ring-beige-200">
            <span>${what} <a class="font-semibold text-navy-700 underline decoration-sage-400" href="/plants">${esc(r.plant_name)}</a></span>
            <span class="text-navy-500">${when}</span></li>`;
        }).join('')
      : '<li class="text-navy-400">Nothing due — enjoy the garden. 🌱</li>';

    const hvHost = $('#today-harvest');
    const fc = data.harvest_forecast || [];
    hvHost.innerHTML = fc.length
      ? fc.map((f) => {
          const label = f.status === 'ready'
            ? '<span class="font-semibold text-sage-700">Ready now! 🎉</span>'
            : `Ready ~${fmtDate(f.ready_date)} <span class="text-navy-400">(${f.days_until_ready}d)</span>`;
          return `<li class="flex items-center justify-between gap-2 rounded-lg bg-beige-50 px-3 py-2 ring-1 ring-beige-200">
            <span><a class="font-semibold text-navy-700 underline decoration-sage-400" href="/plants">${esc(f.plant_name)}</a>
            ${f.crop_name ? `<span class="text-xs text-navy-400"> · ${esc(f.crop_name)} guide</span>` : ''}</span>
            <span class="text-sm text-navy-600">${label}</span></li>`;
        }).join('')
      : '<li class="text-navy-400">No predictions yet — add planting dates to your plants and the crop guide does the rest.</li>';

    const frostHost = $('#today-frost');
    const frost = data.frost;
    frostHost.innerHTML = frost && frost.first_frost_date
      ? `❄️ <strong class="text-navy-800">${frost.days_until}d</strong> until the first frost
         (<span title="${esc(frost.label || '')}">${fmtDate(frost.first_frost_date)}</span>)`
      : 'No frost date configured — <a class="underline decoration-sage-400 text-navy-700" href="/settings">set it in Settings</a> for the countdown and planting math.';
  }

  globalThis.Verdant.onBoot(initToday);
})();

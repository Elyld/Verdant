/* Calendar page + day popup. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function heatLevel(count) {
    if (count <= 0) return 0;
    if (count === 1) return 1;
    if (count <= 3) return 2;
    if (count <= 6) return 3;
    return 4;
  }

  function dayModalHtml(iso, entries) {
    const list = entries.slice().sort((a, b) => b.health_scale - a.health_scale);
    const pretty = new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    const cards = list.map((item) => `
      <article class="rounded-xl border border-beige-200 bg-white p-4">
        <div class="flex items-center justify-between gap-2">
          <h4 class="font-semibold text-navy-800">${esc(item.plant_name)}</h4>
          <span class="pill">${esc(String(item.health_scale))}/10 health</span>
        </div>
        ${item.pest_sightings ? `<p class="mt-2 text-sm">&#x1F41B; <span class="font-semibold">Pests:</span> ${esc(item.pest_sightings)}</p>` : ''}
        ${item.notes ? `<p class="mt-1 text-sm text-navy-600">${esc(item.notes)}</p>` : ''}
      </article>`).join('');
    return `
      <div class="modal-backdrop" data-close></div>
      <div class="modal-card card" role="dialog" aria-modal="true" aria-label="Observations on ${esc(iso)}">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 class="font-display text-xl font-semibold">${esc(pretty)}</h3>
            <p class="text-sm text-navy-500">${list.length} observation${list.length === 1 ? '' : 's'}</p>
          </div>
          <button type="button" class="btn-ghost" data-close aria-label="Close">&times;</button>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">${cards}</div>
        <div class="mt-4 text-right">
          <a class="btn-primary text-sm" href="/observations?date=${esc(iso)}">View in Garden Logs &rarr;</a>
        </div>
      </div>`;
  }

  function openDayModal(iso, entries) {
    const modal = $('#day-modal');
    if (!modal) return;
    modal.innerHTML = dayModalHtml(iso, entries);
    modal.classList.remove('hidden');
    modal.classList.add('modal-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeDayModal() {
    const modal = $('#day-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    modal.classList.add('hidden');
    modal.classList.remove('modal-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = '';
    document.body.style.overflow = '';
  }

  function initCalendar() {
    const grid = $('#calendar-grid');
    if (!grid) return;
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    api.get('/api/stats/calendar').then((observations) => {
      const byDate = new Map();
      observations.forEach((item) => {
        const key = String(item.date).slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) return;
        if (!byDate.has(key)) byDate.set(key, []);
        byDate.get(key).push(item);
      });
      const today = new Date();
      const months = [];
      for (let delta = -2; delta <= 0; delta += 1) months.push(new Date(today.getFullYear(), today.getMonth() + delta, 1));
      const legend = `<div class="flex items-center justify-end gap-1.5 pt-2 text-xs text-navy-500"><span>Less</span>${[0, 1, 2, 3, 4].map((level) => `<span class="heat-swatch heat-${level}" aria-hidden="true"></span>`).join('')}<span>More</span></div>`;
      grid.innerHTML = months.map((monthDate) => {
        const year = monthDate.getFullYear();
        const month = monthDate.getMonth();
        const cells = Array(monthDate.getDay()).fill('<div class="calendar-day calendar-empty"></div>');
        const days = new Date(year, month + 1, 0).getDate();
        for (let day = 1; day <= days; day += 1) {
          const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const entries = byDate.get(iso) || [];
          const level = heatLevel(entries.length);
          const average = entries.length ? Math.round(entries.reduce((sum, item) => sum + item.health_scale, 0) / entries.length) : null;
          const tip = entries.length
            ? `${entries.length} observation${entries.length === 1 ? '' : 's'} on ${iso}${average ? `, average health ${average}/10` : ''} — view in Garden Logs`
            : `No observations on ${iso}`;
          cells.push(`<a href="/observations?date=${iso}" data-date="${iso}" class="calendar-day heat-${level}" title="${esc(tip)}"><span>${day}</span></a>`);
        }
        return `<section class="card"><h2 class="mb-4 font-display text-xl font-semibold">${monthDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2><div class="calendar-weekdays">${weekdays.map((day) => `<span>${day}</span>`).join('')}</div><div class="calendar-month">${cells.join('')}</div>${legend}</section>`;
      }).join('');
      grid.addEventListener('click', (ev) => {
        const link = ev.target.closest('a[data-date]');
        if (!link) return;
        ev.preventDefault();
        const iso = link.getAttribute('data-date');
        openDayModal(iso, byDate.get(iso) || []);
      });
      const modal = $('#day-modal');
      modal?.addEventListener('click', (ev) => {
        if (ev.target.closest('[data-close]')) closeDayModal();
      });
      document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') closeDayModal();
      });
      if (!observations.length) $('#calendar-empty')?.classList.remove('hidden');
    }).catch((error) => { grid.innerHTML = `<div class="card text-red-700">Could not load calendar: ${esc(error.message)}</div>`; });
  }

  globalThis.Verdant.onBoot(initCalendar);
})();

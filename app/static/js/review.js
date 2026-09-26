/* Season review page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  /* ------------------------------ Review ------------------------------ */

  function initReview() {
    const yearEl = $('#review-year');
    if (!yearEl) return {};
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    let year = new Date().getFullYear();

    function statCard(icon, label, value) {
      return `<div class="rounded-xl border border-beige-300 bg-beige-50 px-4 py-3"><dt class="text-xs font-bold uppercase text-navy-500">${icon} ${label}</dt><dd class="mt-1 font-display text-2xl text-sage-700">${value}</dd></div>`;
    }

    function bars(values, max, colorFor, formatTip) {
      return values.map((value, i) => {
        const height = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 4;
        const tip = formatTip ? formatTip(value, i) : `${value}`;
        return `<div class="flex h-full flex-1 items-end" title="${esc(tip)}"><div class="w-full rounded-t ${colorFor(value, i)}" style="height:${height}%"></div></div>`;
      }).join('');
    }

    async function load() {
      yearEl.textContent = year;
      const data = await api.get(`/api/stats/review?year=${year}`);
      const yearlyHealth = (() => {
        let sum = 0; let n = 0;
        data.avg_health_by_month.forEach((avg, i) => {
          const count = data.observations_by_month[i];
          if (avg != null && count) { sum += avg * count; n += count; }
        });
        return n ? (sum / n).toFixed(1) : '—';
      })();
      const harvestLabel = data.harvest_weight
        ? `${data.harvest_count} <span class="text-base text-navy-400">· ${data.harvest_weight} oz</span>`
        : String(data.harvest_count);
      $('#review-stats').innerHTML = [
        statCard('🔍', 'Observations', data.observations),
        statCard('💚', 'Avg health', yearlyHealth),
        statCard('🧺', 'Harvests', harvestLabel),
        statCard('🖼️', 'Photos', data.photos),
        statCard('💧', 'Waterings', data.waterings),
        statCard('🧪', 'Feedings', data.feedings),
        statCard('🐛', 'Pests noted', data.pests_noted),
        statCard('📅', 'Busiest day', data.busiest_day ? `${fmtDate(data.busiest_day)} <span class="text-base text-navy-400">· ${data.busiest_day_count}</span>` : '—'),
      ].join('');

      const maxObs = Math.max(...data.observations_by_month, 1);
      $('#review-activity').innerHTML = bars(
        data.observations_by_month, maxObs,
        (v) => v > 0 ? 'bg-sage-500' : 'bg-beige-200',
        (v, i) => `${MONTHS[i]}: ${v} observations`,
      );
      $('#review-health').innerHTML = bars(
        data.avg_health_by_month.map((v) => v ?? 0), 10,
        (v) => v >= 8 ? 'bg-sage-600' : v >= 5 ? 'bg-beige-500' : v > 0 ? 'bg-red-400' : 'bg-beige-200',
        (v, i) => `${MONTHS[i]}: ${data.avg_health_by_month[i] ?? '—'} avg health`,
      );
      const monthRow = MONTHS.map((m) => `<span class="flex-1 text-center">${m}</span>`).join('');
      $('#review-months').innerHTML = monthRow;
      $('#review-months-2').innerHTML = monthRow;

      $('#review-top').innerHTML = data.top_plants.length
        ? data.top_plants.map((p, i) => `<li class="flex items-center justify-between gap-2 text-sm"><span class="text-navy-800"><b class="text-navy-400">${i + 1}.</b> ${esc(p.plant_name)}</span><span class="pill">${p.observations} obs</span></li>`).join('')
        : '<li class="text-sm text-navy-400">No observations this year yet.</li>';

      const highlights = [];
      if (data.busiest_day) highlights.push(`📅 Busiest day: <b>${fmtDate(data.busiest_day)}</b> with ${data.busiest_day_count} observation${data.busiest_day_count === 1 ? '' : 's'}.`);
      if (data.harvest_count) highlights.push(`🧺 <b>${data.harvest_count}</b> harvest${data.harvest_count === 1 ? '' : 's'}${data.harvest_weight ? ` totaling <b>${data.harvest_weight} oz</b>` : ''}.`);
      if (data.pests_noted) highlights.push(`🐛 Pests noted on <b>${data.pests_noted}</b> observation${data.pests_noted === 1 ? '' : 's'} — check the logs for what worked.`);
      else if (data.observations) highlights.push(`🐛 Not a single pest sighting all year. The garden approves.`);
      if (data.waterings || data.feedings) highlights.push(`💧 <b>${data.waterings}</b> watering${data.waterings === 1 ? '' : 's'} · 🧪 <b>${data.feedings}</b> feeding${data.feedings === 1 ? '' : 's'} logged.`);
      if (!highlights.length) highlights.push('Log some observations to start your story.');
      $('#review-highlights').innerHTML = highlights.map((h) => `<li>${h}</li>`).join('');

      const medals = ['🥇', '🥈', '🥉'];
      const row = (name, pill, i) => `
        <li class="flex items-center justify-between gap-2 text-sm">
          <span class="text-navy-800">${medals[i] || `<b class="text-navy-400">${i + 1}.</b>`} ${esc(name)}</span>
          <span class="pill">${pill}</span>
        </li>`;
      const yields = await api.get(`/api/stats/yield?year=${year}`).catch(() => null);
      const byWeight = (yields && yields.by_weight) || [];
      const byCount = (yields && yields.by_count) || [];
      $('#review-yield-empty').classList.toggle('hidden', byWeight.length > 0 || byCount.length > 0);
      $('#review-yield-weight').innerHTML = byWeight.slice(0, 10).map((y, i) =>
        row(y.variety_name, `${y.total_oz} oz · ${y.harvest_count} picks`, i)).join('')
        || '<li class="text-sm text-navy-400">No weighed harvests yet — add a weight when you log a harvest.</li>';
      $('#review-yield-count').innerHTML = byCount.slice(0, 10).map((y, i) =>
        row(y.variety_name, `${y.total_quantity} ${esc(y.unit)} · ${y.harvest_count} picks`, i)).join('')
        || '<li class="text-sm text-navy-400">Nothing counted by pieces yet.</li>';

      const score = await api.get(`/api/stats/scorecard?year=${year}`).catch(() => null);
      const rows = score && Array.isArray(score.varieties) ? score.varieties : [];
      $('#scorecard-empty').classList.toggle('hidden', rows.length > 0);
      $('#scorecard-summary').textContent = score
        ? `💸 $${score.total_spent.toFixed(2)} spent this season · 🧺 ${score.total_oz} oz harvested${score.unassigned_spent ? ` · $${score.unassigned_spent.toFixed(2)} not tied to a plant` : ''}`
        : '';
      $('#scorecard-rows').innerHTML = rows.map((r, i) => `
        <tr class="border-t border-beige-200">
          <td class="py-2 pr-3 font-semibold text-navy-800">${medals[i] || ''} ${esc(r.variety)}</td>
          <td class="py-2 pr-3 text-right">${r.harvest_events}</td>
          <td class="py-2 pr-3 text-right">${r.total_qty} pcs · ${r.total_oz} oz</td>
          <td class="py-2 pr-3 text-right">${r.oz_per_plant}</td>
          <td class="py-2 pr-3 text-right">$${r.direct_cost.toFixed(2)}</td>
          <td class="py-2 text-right">${r.cost_per_oz != null ? `$${r.cost_per_oz.toFixed(2)}` : '<span class="text-navy-400">—</span>'}</td>
        </tr>`).join('');
    }

    $('#review-prev').addEventListener('click', () => { year -= 1; load().catch((e) => toast(e.message, 'err')); });
    $('#review-next').addEventListener('click', () => { year += 1; load().catch((e) => toast(e.message, 'err')); });
    load().catch((error) => toast(`Could not load review: ${error.message}`, 'err'));
    return {};
  }

  globalThis.Verdant.onBoot(initReview);
})();

/* Pest log page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard, todayLocal } = globalThis.Verdant;

  function initPests() {
    const form = $('#pest-form');
    if (!form) return;
    const today = todayLocal();
    $('#pest-date').value = today;
    let plantNames = new Map();
    let plantSpecies = new Map();

    const TYPE_ICON = {
      insect: '🐛', mite: '🕷️', mollusk: '🐌', nematode: '🪱',
      disease: '🍂', virus: '🦠', physiological: '🌡️',
    };

    function guideCard(p) {
      const icon = TYPE_ICON[p.type] || '🐛';
      const el = document.createElement('article');
      el.className = 'rounded-xl bg-beige-50 px-4 py-3 ring-1 ring-beige-200';
      el.innerHTML =
        `<div class="flex flex-wrap items-center justify-between gap-2">
          <p class="font-semibold text-navy-800">${icon} ${esc(p.name)}
            <span class="ml-1 rounded-full bg-beige-200 px-2 py-0.5 text-xs font-normal text-navy-600">${esc(p.type)}</span></p>
          <button type="button" data-guide-log class="btn-ghost px-2 py-1 text-xs">Log a sighting →</button>
        </div>
        <p class="mt-1 text-sm text-navy-600"><span class="font-semibold">Hosts:</span> ${esc(p.hosts.join(', '))}</p>
        <p class="mt-1 text-sm text-navy-600"><span class="font-semibold">Signs:</span> ${esc(p.signs)}</p>
        <p class="mt-1 text-sm text-navy-600"><span class="font-semibold">Organic:</span> ${esc(p.treatment_organic)}</p>
        <p class="mt-1 text-sm text-navy-600"><span class="font-semibold">Conventional:</span> ${esc(p.treatment_conventional)}</p>
        <p class="mt-1 text-sm text-navy-600"><span class="font-semibold">Prevention:</span> ${esc(p.prevention)}</p>
        <p class="mt-1 text-xs text-navy-400">Sources: ${esc((p.sources || []).join(' · '))}</p>`;
      el.querySelector('[data-guide-log]').addEventListener('click', () => {
        $('#pest-name').value = p.name.replace(/\s*\(.*?\)\s*/g, '').trim() || p.name;
        $('#pest-name').focus();
        $('#pest-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
        toast(`“${p.name}” ready — pick the plant and log it.`, 'ok');
      });
      return el;
    }

    async function guideSearch(q) {
      const box = $('#guide-results');
      q = (q || '').trim();
      if (!q) { box.innerHTML = ''; return; }
      box.innerHTML = '<p class="text-sm text-navy-400">Searching the guide…</p>';
      try {
        const res = await api.get(`/api/pest-guide/search?q=${encodeURIComponent(q)}`);
        box.innerHTML = '';
        if (!res.length) {
          box.innerHTML = '<p class="text-sm text-navy-400">Nothing in the guide matches — describe it in the log notes anyway.</p>';
          return;
        }
        res.slice(0, 12).forEach((p) => box.appendChild(guideCard(p)));
      } catch (error) {
        box.innerHTML = `<p class="text-sm text-red-700">Guide lookup failed: ${esc(error.message)}</p>`;
      }
    }

    function initGuide() {
      const input = $('#guide-q');
      const go = $('#guide-go');
      if (!input || !go) return;
      go.addEventListener('click', () => guideSearch(input.value));
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); guideSearch(input.value); }
      });
    }

    async function showCommonIssues() {
      const wrap = $('#pest-common');
      const chips = $('#pest-common-chips');
      const id = Number($('#pest-plant').value) || null;
      const species = id ? plantSpecies.get(id) : null;
      wrap.classList.add('hidden');
      chips.innerHTML = '';
      if (!species) return;
      try {
        const res = await api.get(`/api/pest-guide/for-host?host=${encodeURIComponent(species)}`);
        if (!res.length) return;
        res.slice(0, 6).forEach((p) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'rounded-full bg-beige-200 px-2 py-0.5 text-xs text-navy-700 hover:bg-beige-300';
          b.textContent = `${TYPE_ICON[p.type] || '🐛'} ${p.name}`;
          b.title = p.signs;
          b.addEventListener('click', () => { $('#pest-name').value = p.name.replace(/\s*\(.*?\)\s*/g, '').trim() || p.name; });
          chips.appendChild(b);
        });
        wrap.classList.remove('hidden');
      } catch (error) { /* guide is a bonus — never block logging */ }
    }

    function row(log, open) {
      const plant = log.plant_id ? (plantNames.get(log.plant_id) || `Plant ${log.plant_id}`) : null;
      return `<li class="rounded-xl bg-beige-50 px-4 py-3 ring-1 ring-beige-200">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p class="font-semibold text-navy-800">🐛 ${esc(log.pest_name)}
            ${plant ? `<span class="text-sm font-normal text-navy-400">· ${esc(plant)}</span>` : ''}
            <span class="text-xs font-normal text-navy-400">· ${fmtDate(log.date)}</span></p>
          <div class="flex gap-2">
            ${open ? `<button type="button" data-resolve-pest="${log.id}" class="btn-ghost text-xs">✓ Resolve</button>` : ''}
            <button type="button" data-del-pest="${log.id}" class="text-xs text-red-700 underline">delete</button>
          </div>
        </div>
        ${log.treatment ? `<p class="mt-1 text-sm text-navy-600">🧪 ${esc(log.treatment)}</p>` : ''}
        ${log.notes ? `<p class="mt-1 text-sm text-navy-500">${esc(log.notes)}</p>` : ''}
      </li>`;
    }

    async function load() {
      const [logs, plants] = await Promise.all([
        api.get('/api/pests/'),
        api.get('/api/plants/').catch(() => []),
      ]);
      const list = Array.isArray(logs) ? logs : [];
      plantNames = new Map((Array.isArray(plants) ? plants : []).map((p) => [p.id, p.variety_name]));
      plantSpecies = new Map((Array.isArray(plants) ? plants : []).map((p) => [p.id, p.species_type]));
      const sel = $('#pest-plant');
      sel.innerHTML = '<option value="">—</option>' + [...plantNames.entries()]
        .map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
      const open = list.filter((l) => !l.resolved);
      const done = list.filter((l) => l.resolved);
      $('#pests-open-empty').classList.toggle('hidden', open.length > 0);
      $('#pests-done-empty').classList.toggle('hidden', done.length > 0);
      $('#pests-open').innerHTML = open.map((l) => row(l, true)).join('');
      $('#pests-done').innerHTML = done.map((l) => row(l, false)).join('');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const name = $('#pest-name').value.trim();
      if (!name) { toast('Name the pest first.', 'err'); return; }
      try {
        await api.post('/api/pests/', {
          date: $('#pest-date').value || today,
          pest_name: name,
          plant_id: $('#pest-plant').value ? Number($('#pest-plant').value) : null,
          treatment: $('#pest-treatment').value.trim(),
          notes: $('#pest-notes').value.trim(),
        });
        toast('Pest logged 🐛', 'ok');
        $('#pest-name').value = '';
        $('#pest-treatment').value = '';
        $('#pest-notes').value = '';
        load();
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
    });

    $('#panel-pests').addEventListener('click', async (event) => {
      const resolveBtn = event.target.closest('[data-resolve-pest]');
      const delBtn = event.target.closest('[data-del-pest]');
      try {
        if (resolveBtn) {
          await api.patch(`/api/pests/${resolveBtn.dataset.resolvePest}`, { resolved: true });
          toast('Resolved ✅', 'ok');
          load();
        } else if (delBtn) {
          if (!window.confirm('Delete this pest log?')) return;
          await api.del(`/api/pests/${delBtn.dataset.delPest}`);
          toast('Deleted.', 'ok');
          load();
        }
      } catch (error) { toast(`Could not update: ${error.message}`, 'err'); }
    });

    load().catch((error) => toast(`Could not load pests: ${error.message}`, 'err'));
    initGuide();
    $('#pest-plant').addEventListener('change', showCommonIssues);

    // NFC tag deep link: /pests?product=<name> pre-fills the treatment field.
    const product = new URLSearchParams(location.search).get('product');
    if (product) {
      $('#pest-treatment').value = product;
      $('#pest-name').focus();
    }
  }

  globalThis.Verdant.onBoot(initPests);
})();

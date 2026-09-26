/* Pest log page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initPests() {
    const form = $('#pest-form');
    if (!form) return;
    const today = new Date().toISOString().slice(0, 10);
    $('#pest-date').value = today;
    let plantNames = new Map();

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
  }

  globalThis.Verdant.onBoot(initPests);
})();

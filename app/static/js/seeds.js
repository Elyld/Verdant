/* Seed sources page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initSeedSources() {
    const host = $('#seed-groups');
    if (!host) return {};
    const filter = $('#seed-vendor-filter');
    const form = $('#seed-form');
    let sources = [];
    let plants = [];
    let editingId = null;

    const plantName = (id) => (plants.find((p) => p.id === id) || {}).variety_name || '';
    const newSourceId = () => `SRC-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

    async function load() {
      try {
        [sources, plants] = await Promise.all([
          api.get('/api/seed-sources/'),
          api.get('/api/plants/'),
        ]);
        if (!Array.isArray(sources)) sources = [];
        if (!Array.isArray(plants)) plants = [];
      } catch (error) {
        toast(`Could not load seed sources: ${error.message}`, 'err');
        return;
      }
      const vendors = [...new Set(sources.map((s) => s.source))].sort();
      filter.innerHTML = '<option value="">All vendors</option>'
        + vendors.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
      const plantLink = $('#seed-plant-link');
      plantLink.innerHTML = '<option value="">— none —</option>'
        + plants.map((p) => `<option value="${p.id}">${esc(p.variety_name || `Plant #${p.id}`)}</option>`).join('');
      render();
    }

    function render() {
      const selected = filter.value;
      const visible = selected ? sources.filter((s) => s.source === selected) : sources;
      $('#seeds-empty').classList.toggle('hidden', visible.length > 0);
      const groups = new Map();
      visible.forEach((s) => {
        if (!groups.has(s.source)) groups.set(s.source, []);
        groups.get(s.source).push(s);
      });
      host.innerHTML = [...groups.entries()].map(([vendor, items]) => `
        <div class="card space-y-3">
          <h3 class="font-display text-lg font-semibold text-navy-800">${esc(vendor)}
            <span class="ml-2 rounded-full bg-sage-100 px-2 py-0.5 text-xs font-body font-semibold text-sage-700">${items.length}</span>
          </h3>
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            ${items.map((s) => `
              <div class="rounded-xl bg-beige-50 p-4 ring-1 ring-beige-200">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <p class="font-semibold text-navy-800">${esc(s.variety) || '<span class="text-navy-300">—</span>'}</p>
                    <p class="text-xs text-navy-500">${esc(s.type || '')}${s.acquired_date ? ` · acquired ${fmtDate(s.acquired_date)}` : ''}</p>
                  </div>
                  <span class="text-xl">🌱</span>
                </div>
                ${s.linked_plant_id && plantName(s.linked_plant_id) ? `<p class="mt-1 text-xs text-sage-700">→ ${esc(plantName(s.linked_plant_id))}</p>` : ''}
                ${s.notes ? `<p class="mt-2 text-sm text-navy-600">${esc(s.notes)}</p>` : ''}
                <div class="mt-3 flex gap-2">
                  <button type="button" class="btn-ghost text-xs" data-edit-seed="${s.id}">Edit</button>
                  <button type="button" class="btn-ghost text-xs text-red-700" data-del-seed="${s.id}">Delete</button>
                </div>
              </div>`).join('')}
          </div>
        </div>`).join('');
    }

    function openForm(item) {
      editingId = item ? item.id : null;
      $('#seed-form-title').textContent = item ? 'Edit seed source' : 'Add seed source';
      $('#seed-submit').textContent = item ? 'Save changes' : 'Add seeds';
      $('#seed-vendor').value = item ? item.source : '';
      $('#seed-variety').value = item ? item.variety : '';
      $('#seed-type').value = item ? item.type : 'Vendor Purchase';
      $('#seed-acquired').value = item && item.acquired_date ? item.acquired_date.slice(0, 10) : '';
      $('#seed-plant-link').value = item && item.linked_plant_id ? String(item.linked_plant_id) : '';
      $('#seed-notes').value = item ? item.notes || '' : '';
      form.classList.remove('hidden');
      $('#seed-vendor').focus();
    }

    $('#seed-add-toggle').addEventListener('click', () => {
      if (form.classList.contains('hidden')) openForm(null);
      else form.classList.add('hidden');
    });
    $('#seed-cancel').addEventListener('click', () => form.classList.add('hidden'));
    filter.addEventListener('change', render);

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {
        source: $('#seed-vendor').value.trim(),
        variety: $('#seed-variety').value.trim(),
        type: $('#seed-type').value,
        acquired_date: $('#seed-acquired').value || null,
        linked_plant_id: $('#seed-plant-link').value ? Number($('#seed-plant-link').value) : null,
        notes: $('#seed-notes').value.trim() || null,
      };
      if (!payload.source) {
        toast('Vendor is required.', 'err');
        return;
      }
      try {
        if (editingId) {
          await api.patch(`/api/seed-sources/${editingId}`, payload);
          toast('Seed source updated.', 'ok');
        } else {
          payload.source_id = newSourceId();
          await api.post('/api/seed-sources/', payload);
          toast('Seed source added.', 'ok');
        }
        form.classList.add('hidden');
        await load();
      } catch (error) {
        toast(error.message, 'err');
      }
    });

    host.addEventListener('click', async (event) => {
      const editBtn = event.target.closest('[data-edit-seed]');
      const delBtn = event.target.closest('[data-del-seed]');
      if (editBtn) {
        const item = sources.find((s) => s.id === Number(editBtn.dataset.editSeed));
        if (item) openForm(item);
        return;
      }
      if (delBtn) {
        const item = sources.find((s) => s.id === Number(delBtn.dataset.delSeed));
        if (!item) return;
        if (!window.confirm(`Delete "${item.variety}" from ${item.source}?`)) return;
        try {
          await api.del(`/api/seed-sources/${item.id}`);
          toast('Seed source deleted.', 'ok');
          await load();
        } catch (error) {
          toast(error.message, 'err');
        }
      }
    });

    load();
    return {};
  }

  globalThis.Verdant.onBoot(initSeedSources);
})();

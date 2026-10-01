/* Pantry page — preservation log + pantry inventory. */
(() => {
  'use strict';

  const { $, esc, api, fmtDate, toast } = globalThis.Verdant;

  const METHOD_LABELS = {
    canned: '🥫 Canned',
    frozen: '🧊 Frozen',
    dehydrated: '☀️ Dehydrated',
    fermented: '🫧 Fermented',
    gave_away: '💝 Gave away',
    fresh: '🥗 Ate fresh',
  };
  const methodLabel = (m) => METHOD_LABELS[m] || esc(m || '—');

  function qtyStr(qty, unit) {
    if (qty == null) return '';
    const q = Number(qty);
    return `${Number.isInteger(q) ? q : Math.round(q * 100) / 100}${unit ? ` ${esc(unit)}` : ''}`;
  }

  async function initPantry() {
    if (!$('#panel-pantry')) return;
    $('#pres-date').value = new Date().toISOString().slice(0, 10);
    await Promise.all([loadLookups(), loadItems(), loadHistory()]);
    $('#preserve-form').addEventListener('submit', onSubmit);
  }

  async function loadLookups() {
    try {
      const plants = await api.get('/api/plants/');
      const names = [...new Set((plants || []).map((p) => p.variety_name).filter(Boolean))].sort();
      $('#pres-variety-list').innerHTML = names.map((n) => `<option value="${esc(n)}">`).join('');
    } catch { /* plants optional */ }
    try {
      const harvests = await api.get('/api/harvests/');
      const sel = $('#pres-harvest');
      const opts = (harvests || []).slice(0, 60).map((h) => {
        const label = `${h.date || ''} — ${h.quantity || ''} ${esc(h.unit || '')}`.trim();
        return `<option value="${h.id}">${esc(label)} (${esc(h.harvest_id || '')})</option>`;
      });
      sel.innerHTML = '<option value="">— none —</option>' + opts.join('');
    } catch { /* harvests optional */ }
  }

  async function onSubmit(e) {
    e.preventDefault();
    const num = (id) => {
      const v = $(id).value.trim();
      return v === '' ? null : Number(v);
    };
    const payload = {
      date: $('#pres-date').value,
      method: $('#pres-method').value,
      variety_name: $('#pres-variety').value.trim(),
      harvest_id: $('#pres-harvest').value ? Number($('#pres-harvest').value) : null,
      qty_in: num('#pres-qty-in'),
      qty_in_unit: $('#pres-unit-in').value.trim(),
      qty_out: num('#pres-qty-out'),
      qty_out_unit: $('#pres-unit-out').value.trim(),
      stored_location: $('#pres-location').value.trim(),
      notes: $('#pres-notes').value.trim(),
      add_to_pantry: $('#pres-to-pantry').checked,
    };
    try {
      await api.post('/api/pantry/preservation', payload);
      toast('Preserved ✓', 'ok');
      e.target.reset();
      $('#pres-date').value = new Date().toISOString().slice(0, 10);
      $('#pres-to-pantry').checked = true;
      await Promise.all([loadItems(), loadHistory()]);
    } catch (err) {
      toast(`Could not save: ${err.message}`, 'err');
    }
  }

  async function loadItems() {
    const host = $('#pantry-items');
    const empty = $('#pantry-items-empty');
    let items = [];
    try {
      items = await api.get('/api/pantry/items');
    } catch (err) {
      host.innerHTML = '';
      empty.textContent = `Could not load pantry: ${err.message}`;
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.toggle('hidden', items.length > 0);
    host.innerHTML = items.map((it) => `
      <div class="rounded-xl bg-beige-50 p-3 ring-1 ring-beige-200" data-item="${it.id}">
        <p class="font-semibold text-navy-800">${esc(it.name)}</p>
        <p class="text-sm text-navy-500">${methodLabel(it.method)} · ${qtyStr(it.quantity, it.unit)}${it.location ? ` · ${esc(it.location)}` : ''}</p>
        ${it.stored_date ? `<p class="text-xs text-navy-400">Stored ${esc(fmtDate(it.stored_date))}</p>` : ''}
        <div class="mt-2 flex items-center gap-2">
          <input type="number" min="0" step="any" placeholder="amount" aria-label="Amount to use"
            class="inp w-24 px-2 py-1 text-sm" data-use-amt="${it.id}" />
          <button type="button" class="btn-ghost px-2 py-1 text-sm" data-use="${it.id}">Use</button>
          <button type="button" class="btn-ghost px-2 py-1 text-sm text-red-700" data-del-item="${it.id}" title="Remove">✕</button>
        </div>
      </div>`).join('');
    host.querySelectorAll('[data-use]').forEach((btn) => btn.addEventListener('click', () => useItem(btn.dataset.use)));
    host.querySelectorAll('[data-del-item]').forEach((btn) => btn.addEventListener('click', () => deleteItem(btn.dataset.delItem)));
  }

  async function useItem(id) {
    const input = document.querySelector(`[data-use-amt="${id}"]`);
    const amount = Number((input && input.value) || '');
    if (!amount || amount <= 0) {
      toast('Enter an amount to use first.', 'err');
      return;
    }
    try {
      const updated = await api.post(`/api/pantry/items/${id}/use`, { amount });
      toast(updated.quantity > 0 ? 'Used ✓' : 'All used up ✓', 'ok');
      await loadItems();
    } catch (err) {
      toast(`Could not update: ${err.message}`, 'err');
    }
  }

  async function deleteItem(id) {
    if (!window.confirm('Remove this pantry item? (The preservation history stays.)')) return;
    try {
      await api.del(`/api/pantry/items/${id}`);
      await loadItems();
    } catch (err) {
      toast(`Could not remove: ${err.message}`, 'err');
    }
  }

  async function loadHistory() {
    const host = $('#pres-history');
    const empty = $('#pres-history-empty');
    let logs = [];
    try {
      logs = await api.get('/api/pantry/preservation');
    } catch (err) {
      host.innerHTML = '';
      empty.textContent = `Could not load history: ${err.message}`;
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.toggle('hidden', logs.length > 0);
    host.innerHTML = logs.map((l) => {
      const flow = [qtyStr(l.qty_in, l.qty_in_unit), qtyStr(l.qty_out, l.qty_out_unit)]
        .filter(Boolean).join(' → ');
      return `<li class="flex items-start justify-between gap-2 rounded-lg bg-beige-50 px-3 py-2 ring-1 ring-beige-200">
        <div class="text-sm text-navy-600">
          <span class="font-semibold text-navy-800">${methodLabel(l.method)} ${esc(l.variety_name || '')}</span>
          ${flow ? `<span class="text-navy-500"> · ${flow}</span>` : ''}
          <span class="text-navy-400"> · ${esc(fmtDate(l.date))}</span>
          ${l.stored_location ? `<span class="text-navy-500"> · ${esc(l.stored_location)}</span>` : ''}
          ${l.notes ? `<p class="text-navy-500">${esc(l.notes)}</p>` : ''}
        </div>
        <button type="button" class="btn-ghost px-2 py-1 text-xs text-red-700" data-del-log="${l.id}" title="Delete">✕</button>
      </li>`;
    }).join('');
    host.querySelectorAll('[data-del-log]').forEach((btn) => btn.addEventListener('click', async () => {
      if (!window.confirm('Delete this preservation entry?')) return;
      try {
        await api.del(`/api/pantry/preservation/${btn.dataset.delLog}`);
        await Promise.all([loadItems(), loadHistory()]);
      } catch (err) {
        toast(`Could not delete: ${err.message}`, 'err');
      }
    }));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPantry);
  } else {
    initPantry();
  }
})();

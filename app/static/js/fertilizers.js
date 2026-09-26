/* Fertilizers page — manage the fertilizer product catalog. */
(() => {
  'use strict';

  const { $, $$, esc, api, toast } = globalThis.Verdant;

  function initFertilizers() {
    if (!$('#panel-fertilizers')) return;

    async function load() {
      const ferts = await api.get('/api/fertilizers/').catch(() => []);
      const list = Array.isArray(ferts) ? ferts : [];
      $('#fert-products-empty').classList.toggle('hidden', list.length > 0);
      $('#fert-products').innerHTML = list.map((f) => `
        <div class="rounded-xl bg-beige-50 p-4 ring-1 ring-beige-200">
          <div class="flex items-start justify-between gap-2">
            <p class="font-semibold text-navy-800">🧪 ${esc(f.name)}</p>
            <button type="button" data-del-fert-prod="${f.id}" class="text-xs text-red-700 underline" aria-label="Delete ${esc(f.name)}">delete</button>
          </div>
          ${f.npk_ratio ? `<p class="mt-1 text-sm text-navy-600">NPK <span class="font-mono">${esc(f.npk_ratio)}</span></p>` : ''}
          ${f.best_for ? `<p class="mt-1 text-sm text-navy-500">Best for: ${esc(f.best_for)}</p>` : ''}
          ${f.notes ? `<p class="mt-1 text-sm text-navy-500">${esc(f.notes)}</p>` : ''}
        </div>`).join('');
    }

    $('#fert-product-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        name: $('#fert-prod-name').value.trim(),
        npk_ratio: $('#fert-prod-npk').value.trim(),
        best_for: $('#fert-prod-best').value.trim(),
        notes: $('#fert-prod-notes').value.trim(),
      };
      if (!payload.name) { toast('Give the fertilizer a name.', 'error'); return; }
      try {
        await api.post('/api/fertilizers/', payload);
        e.target.reset();
        toast('Fertilizer added.');
        load();
      } catch (err) {
        toast(err.message || 'Could not add fertilizer.', 'error');
      }
    });

    $('#fert-products').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-del-fert-prod]');
      if (!btn) return;
      if (!confirm('Delete this fertilizer? Past log entries keep their recorded name.')) return;
      try {
        await api.del(`/api/fertilizers/${btn.dataset.delFertProd}`);
        toast('Deleted.');
        load();
      } catch (err) {
        toast(err.message || 'Could not delete.', 'error');
      }
    });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFertilizers);
  } else {
    initFertilizers();
  }
})();

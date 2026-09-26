/* Costs page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initCosts() {
    const form = $('#cost-form');
    if (!form) return;
    const today = new Date().toISOString().slice(0, 10);
    $('#cost-date').value = today;
    const money = (n) => `$${Number(n || 0).toFixed(2)}`;

    async function load() {
      const expenses = await api.get('/api/expenses/');
      const list = Array.isArray(expenses) ? expenses : [];
      const total = list.reduce((sum, e) => sum + Number(e.amount || 0), 0);
      $('#costs-total').textContent = money(total);
      const byCat = {};
      list.forEach((e) => { byCat[e.category] = (byCat[e.category] || 0) + Number(e.amount || 0); });
      $('#costs-by-cat').innerHTML = Object.entries(byCat).sort((a, b) => b[1] - a[1])
        .map(([cat, amt]) => `<span class="pill">${esc(cat)} · ${money(amt)}</span>`).join('')
        || '<span class="text-sm text-navy-400">—</span>';
      $('#costs-empty').classList.toggle('hidden', list.length > 0);
      $('#costs-rows').innerHTML = list.map((e) => `
        <tr class="border-t border-beige-200">
          <td class="py-2 pr-3 whitespace-nowrap">${fmtDate(e.date)}</td>
          <td class="py-2 pr-3"><span class="pill">${esc(e.category)}</span></td>
          <td class="py-2 pr-3">${esc(e.description || '—')}${e.notes ? `<span class="block text-xs text-navy-400">${esc(e.notes)}</span>` : ''}</td>
          <td class="py-2 pr-3 text-right font-semibold">${money(e.amount)}</td>
          <td class="py-2 text-right"><button type="button" data-del-cost="${e.id}" class="text-xs text-red-700 underline">delete</button></td>
        </tr>`).join('');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        await api.post('/api/expenses/', {
          date: $('#cost-date').value || today,
          category: $('#cost-category').value,
          description: $('#cost-desc').value.trim(),
          amount: Number($('#cost-amount').value) || 0,
          notes: $('#cost-notes').value.trim(),
        });
        toast('Expense logged 💸', 'ok');
        $('#cost-desc').value = '';
        $('#cost-amount').value = '';
        $('#cost-notes').value = '';
        load();
      } catch (error) { toast(`Could not save expense: ${error.message}`, 'err'); }
    });

    $('#costs-rows').addEventListener('click', async (event) => {
      const btn = event.target.closest('[data-del-cost]');
      if (!btn) return;
      if (!window.confirm('Delete this expense?')) return;
      try {
        await api.del(`/api/expenses/${btn.dataset.delCost}`);
        toast('Expense deleted.', 'ok');
        load();
      } catch (error) { toast(`Could not delete: ${error.message}`, 'err'); }
    });

    load().catch((error) => toast(`Could not load expenses: ${error.message}`, 'err'));
  }

  /* ------------------------------ Pests ------------------------------ */

  globalThis.Verdant.onBoot(initCosts);
})();

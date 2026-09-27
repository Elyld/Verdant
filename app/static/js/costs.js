/* Costs page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard, todayLocal } = globalThis.Verdant;

  function initCosts() {
    const form = $('#cost-form');
    if (!form) return;
    const today = todayLocal();
    $('#cost-date').value = today;
    const money = (n) => `$${Number(n || 0).toFixed(2)}`;

    async function load() {
      const [expenses, plants] = await Promise.all([
        api.get('/api/expenses/'),
        api.get('/api/plants/').catch(() => []),
      ]);
      const list = Array.isArray(expenses) ? expenses : [];
      const plantNames = new Map((Array.isArray(plants) ? plants : []).map((p) => [p.id, p.variety_name]));
      const sel = $('#cost-plant');
      if (sel && !sel.dataset.loaded) {
        sel.innerHTML = '<option value="">— whole garden —</option>' +
          [...plantNames.entries()].map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
        sel.dataset.loaded = '1';
      }
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
          <td class="py-2 pr-3">${esc(e.description || '—')}${e.plant_id && plantNames.get(e.plant_id) ? `<span class="block text-xs text-sage-700">🌱 ${esc(plantNames.get(e.plant_id))}</span>` : ''}${e.notes ? `<span class="block text-xs text-navy-400">${esc(e.notes)}</span>` : ''}</td>
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
          plant_id: $('#cost-plant').value ? Number($('#cost-plant').value) : null,
        });
        toast('Expense logged 💸', 'ok');
        $('#cost-desc').value = '';
        $('#cost-amount').value = '';
        $('#cost-notes').value = '';
        $('#cost-plant').value = '';
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
    initInvoices();
  }

  function initInvoices() {
    const { $, esc, fmtDate, api, toast, todayLocal } = globalThis.Verdant;
    const form = $('#invoice-form');
    if (!form) return;
    const today = todayLocal();
    $('#inv-date').value = today;
    const money = (n) => `$${Number(n || 0).toFixed(2)}`;

    async function load() {
      const [invoices, expenses] = await Promise.all([
        api.get('/api/invoices/'),
        api.get('/api/expenses/').catch(() => []),
      ]);
      const list = Array.isArray(invoices) ? invoices : [];
      const expList = Array.isArray(expenses) ? expenses : [];
      const expNames = new Map(expList.map((e) => [e.id, `${fmtDate(e.date)} · ${e.description || e.category} · $${Number(e.amount || 0).toFixed(2)}`]));
      const sel = $('#inv-expense');
      if (sel && !sel.dataset.loaded) {
        sel.innerHTML = '<option value="">— none —</option>' +
          [...expNames.entries()].map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
        sel.dataset.loaded = '1';
      }
      $('#invoices-empty').classList.toggle('hidden', list.length > 0);
      $('#invoices-rows').innerHTML = list.map((inv) => `
        <tr class="border-t border-beige-200">
          <td class="py-2 pr-3 whitespace-nowrap">${fmtDate(inv.order_date)}</td>
          <td class="py-2 pr-3 font-semibold">${esc(inv.vendor || '—')}</td>
          <td class="py-2 pr-3">${esc(inv.order_number || '—')}${inv.expense_id && expNames.get(inv.expense_id) ? `<span class="block text-xs text-sage-700">💸 ${esc(expNames.get(inv.expense_id))}</span>` : ''}</td>
          <td class="py-2 pr-3">${esc(inv.items_summary || '—')}${inv.notes ? `<span class="block text-xs text-navy-400">${esc(inv.notes)}</span>` : ''}</td>
          <td class="py-2 pr-3 text-right font-semibold">${money(inv.total)}</td>
          <td class="py-2 text-right whitespace-nowrap">
            ${inv.pdf_path ? `<a href="${esc(inv.pdf_path)}" target="_blank" rel="noopener" class="text-xs text-sage-700 underline">PDF</a> ` : ''}
            <button type="button" data-del-inv="${inv.id}" class="text-xs text-red-700 underline">delete</button>
          </td>
        </tr>`).join('');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const created = await api.post('/api/invoices/', {
          vendor: $('#inv-vendor').value.trim(),
          order_date: $('#inv-date').value || today,
          order_number: $('#inv-order').value.trim(),
          total: Number($('#inv-total').value) || 0,
          items_summary: $('#inv-items').value.trim(),
          notes: $('#inv-notes').value.trim(),
          expense_id: $('#inv-expense').value ? Number($('#inv-expense').value) : null,
        });
        const pdfInput = $('#inv-pdf');
        if (pdfInput.files.length) {
          const data = new FormData();
          data.append('file', pdfInput.files[0], pdfInput.files[0].name);
          await api.upload(`/api/invoices/${created.id}/pdf`, data);
        }
        toast('Invoice saved 🧾', 'ok');
        ['#inv-vendor', '#inv-order', '#inv-total', '#inv-items', '#inv-notes'].forEach((s) => { $(s).value = ''; });
        $('#inv-expense').value = '';
        pdfInput.value = '';
        load();
      } catch (error) { toast(`Could not save invoice: ${error.message}`, 'err'); }
    });

    $('#invoices-rows').addEventListener('click', async (event) => {
      const btn = event.target.closest('[data-del-inv]');
      if (!btn) return;
      if (!window.confirm('Delete this invoice? Its PDF goes with it.')) return;
      try {
        await api.del(`/api/invoices/${btn.dataset.delInv}`);
        toast('Invoice deleted.', 'ok');
        load();
      } catch (error) { toast(`Could not delete: ${error.message}`, 'err'); }
    });

    load().catch((error) => toast(`Could not load invoices: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initCosts);
})();

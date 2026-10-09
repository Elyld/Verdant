/* Costs page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard, todayLocal } = globalThis.Verdant;

  // ---- Shared seed-packet tagging UI (invoice + expense rows) ----
  // kind is "invoice" or "expense"; object ids follow. Tags are independent:
  // linking a packet on an invoice never touches its expense and vice versa.
  function pkApiBase(kind) { return kind === 'invoice' ? '/api/invoices' : '/api/expenses'; }

  function packetBlockHTML(kind, id, linked, suggestions, packetList) {
    const chips = linked.map((p) => `
      <span class="pill ring-1 bg-sage-100 text-sage-800 ring-sage-300">🌱 ${esc(p.variety_name)}
        <button type="button" data-pk-detach="${kind}:${id}:${p.id}" class="ml-1 font-bold" title="Unlink packet">×</button>
      </span>`).join('');
    const suggBtns = suggestions.slice(0, 3).map((s) => `
      <button type="button" data-pk-attach="${kind}:${id}:${s.packet_id}" class="text-xs text-sage-700 underline" title="Matched “${esc(s.matched_item)}”">+ ${esc(s.variety)}</button>`).join(' ');
    const linkedIds = new Set(linked.map((p) => p.id));
    const checks = packetList.map((p) => `
      <label class="flex items-center gap-1.5 text-xs py-0.5 cursor-pointer"><input type="checkbox" data-pk-check="${kind}:${id}:${p.id}"${linkedIds.has(p.id) ? ' checked' : ''} class="accent-sage-700"> <span>${esc(p.variety_name)}${p.vendor_name ? ` <span class="text-navy-400">(${esc(p.vendor_name)})</span>` : ''}</span></label>`).join('');
    return `<div class="mt-1.5 flex flex-wrap items-center gap-1.5">${chips}
        <details class="text-xs"><summary class="text-sage-700 underline cursor-pointer">＋ link packets</summary>
          <div class="mt-1 max-h-40 overflow-y-auto rounded-lg border border-beige-200 bg-white p-2">${checks || '<span class="text-navy-400">No seed packets yet.</span>'}</div>
        </details></div>`
      + (suggBtns ? `<div class="mt-1 text-xs text-navy-400">suggested: ${suggBtns}</div>` : '');
  }

  // Returns true when the event was a packet action (caller should stop).
  async function handlePkClick(event, kind, reload) {
    const attachBtn = event.target.closest('[data-pk-attach]');
    if (attachBtn) {
      const [k, oid, pid] = attachBtn.dataset.pkAttach.split(':');
      if (k !== kind) return false;
      try {
        await api.post(`${pkApiBase(k)}/${oid}/packets`, { seed_packet_id: Number(pid) });
        toast('Packet linked 🌱', 'ok');
        reload();
      } catch (error) { toast(`Could not link packet: ${error.message}`, 'err'); }
      return true;
    }
    const detachBtn = event.target.closest('[data-pk-detach]');
    if (detachBtn) {
      const [k, oid, pid] = detachBtn.dataset.pkDetach.split(':');
      if (k !== kind) return false;
      try {
        await api.del(`${pkApiBase(k)}/${oid}/packets/${pid}`);
        toast('Packet unlinked.', 'ok');
        reload();
      } catch (error) { toast(`Could not unlink packet: ${error.message}`, 'err'); }
      return true;
    }
    return false;
  }

  async function handlePkChange(event, kind, reload) {
    const check = event.target.closest('[data-pk-check]');
    if (!check) return false;
    const [k, oid, pid] = check.dataset.pkCheck.split(':');
    if (k !== kind) return false;
    try {
      if (check.checked) {
        await api.post(`${pkApiBase(k)}/${oid}/packets`, { seed_packet_id: Number(pid) });
        toast('Packet linked 🌱', 'ok');
      } else {
        await api.del(`${pkApiBase(k)}/${oid}/packets/${pid}`);
        toast('Packet unlinked.', 'ok');
      }
      reload();
    } catch (error) { toast(`Could not update packet link: ${error.message}`, 'err'); }
    return true;
  }

  function initCosts() {
    const form = $('#cost-form');
    if (!form) return;
    const today = todayLocal();
    $('#cost-date').value = today;
    const money = (n) => `$${Number(n || 0).toFixed(2)}`;
    let editingId = null;
    let lastList = [];

    function resetCostForm() {
      editingId = null;
      $('#cost-form-title').textContent = 'Log a purchase';
      $('#cost-submit').textContent = 'Add expense';
      $('#cost-cancel').classList.add('hidden');
      $('#cost-desc').value = '';
      $('#cost-amount').value = '';
      $('#cost-notes').value = '';
      $('#cost-plant').value = '';
    }

    async function load() {
      const [expenses, plants, packets] = await Promise.all([
        api.get('/api/expenses/'),
        api.get('/api/plants/').catch(() => []),
        api.get('/api/seed-packets/').catch(() => []),
      ]);
      const list = Array.isArray(expenses) ? expenses : [];
      lastList = list;
      const packetList = Array.isArray(packets) ? packets : [];
      const plantNames = new Map((Array.isArray(plants) ? plants : []).map((p) => [p.id, p.variety_name]));
      const linkData = await Promise.all(list.map(async (e) => {
        const [linked, suggestions] = await Promise.all([
          api.get(`/api/expenses/${e.id}/packets`).catch(() => []),
          api.get(`/api/expenses/${e.id}/packet-suggestions`).catch(() => []),
        ]);
        return { id: e.id, linked, suggestions };
      }));
      const linksByExp = new Map(linkData.map((d) => [d.id, Array.isArray(d.linked) ? d.linked : []]));
      const suggByExp = new Map(linkData.map((d) => [d.id, Array.isArray(d.suggestions) ? d.suggestions : []]));
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
          <td class="py-2 pr-3">${esc(e.description || '—')}${e.plant_id && plantNames.get(e.plant_id) ? `<span class="block text-xs text-sage-700">🌱 ${esc(plantNames.get(e.plant_id))}</span>` : ''}${e.notes ? `<span class="block text-xs text-navy-400">${esc(e.notes)}</span>` : ''}${packetBlockHTML('expense', e.id, linksByExp.get(e.id) || [], suggByExp.get(e.id) || [], packetList)}</td>
          <td class="py-2 pr-3 text-right font-semibold">${money(e.amount)}</td>
          <td class="py-2 text-right whitespace-nowrap"><button type="button" data-edit-cost="${e.id}" class="text-xs text-sage-700 underline mr-2">edit</button><button type="button" data-del-cost="${e.id}" class="text-xs text-red-700 underline">delete</button></td>
        </tr>`).join('');
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {
        date: $('#cost-date').value || today,
        category: $('#cost-category').value,
        description: $('#cost-desc').value.trim(),
        amount: Number($('#cost-amount').value) || 0,
        notes: $('#cost-notes').value.trim(),
        plant_id: $('#cost-plant').value ? Number($('#cost-plant').value) : null,
      };
      try {
        if (editingId) {
          await api.patch(`/api/expenses/${editingId}`, payload);
          toast('Expense updated 💸', 'ok');
        } else {
          await api.post('/api/expenses/', payload);
          toast('Expense logged 💸', 'ok');
        }
        resetCostForm();
        load();
      } catch (error) { toast(`Could not save expense: ${error.message}`, 'err'); }
    });

    $('#cost-cancel').addEventListener('click', resetCostForm);

    $('#costs-rows').addEventListener('change', async (event) => {
      await handlePkChange(event, 'expense', load);
    });

    $('#costs-rows').addEventListener('click', async (event) => {
      if (await handlePkClick(event, 'expense', load)) return;
      const editBtn = event.target.closest('[data-edit-cost]');
      if (editBtn) {
        const e = lastList.find((x) => String(x.id) === editBtn.dataset.editCost);
        if (!e) return;
        editingId = e.id;
        $('#cost-date').value = (e.date || '').slice(0, 10) || today;
        $('#cost-category').value = e.category || 'Supplies';
        $('#cost-desc').value = e.description || '';
        $('#cost-amount').value = e.amount ?? '';
        $('#cost-notes').value = e.notes || '';
        $('#cost-plant').value = e.plant_id ? String(e.plant_id) : '';
        $('#cost-form-title').textContent = 'Edit expense';
        $('#cost-submit').textContent = 'Save changes';
        $('#cost-cancel').classList.remove('hidden');
        form.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
      const btn = event.target.closest('[data-del-cost]');
      if (!btn) return;
      if (!window.confirm('Delete this expense?')) return;
      try {
        await api.del(`/api/expenses/${btn.dataset.delCost}`);
        if (editingId && String(editingId) === btn.dataset.delCost) resetCostForm();
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
      const [invoices, expenses, packets] = await Promise.all([
        api.get('/api/invoices/'),
        api.get('/api/expenses/').catch(() => []),
        api.get('/api/seed-packets/').catch(() => []),
      ]);
      const list = Array.isArray(invoices) ? invoices : [];
      const packetList = Array.isArray(packets) ? packets : [];
      const expList = Array.isArray(expenses) ? expenses : [];
      const expNames = new Map(expList.map((e) => [e.id, `${fmtDate(e.date)} · ${e.description || e.category} · $${Number(e.amount || 0).toFixed(2)}`]));
      const sel = $('#inv-expense');
      if (sel && !sel.dataset.loaded) {
        sel.innerHTML = '<option value="">— none —</option>' +
          [...expNames.entries()].map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join('');
        sel.dataset.loaded = '1';
      }
      const linkData = await Promise.all(list.map(async (inv) => {
        const [linked, suggestions] = await Promise.all([
          api.get(`/api/invoices/${inv.id}/packets`).catch(() => []),
          (inv.items_summary ? api.get(`/api/invoices/${inv.id}/packet-suggestions`).catch(() => []) : []),
        ]);
        return { id: inv.id, linked, suggestions };
      }));
      const linksByInv = new Map(linkData.map((d) => [d.id, Array.isArray(d.linked) ? d.linked : []]));
      const suggByInv = new Map(linkData.map((d) => [d.id, Array.isArray(d.suggestions) ? d.suggestions : []]));
      const packetBlock = (inv) => packetBlockHTML('invoice', inv.id, linksByInv.get(inv.id) || [], suggByInv.get(inv.id) || [], packetList);
      $('#invoices-empty').classList.toggle('hidden', list.length > 0);
      $('#invoices-rows').innerHTML = list.map((inv) => `
        <tr class="border-t border-beige-200">
          <td class="py-2 pr-3 whitespace-nowrap">${fmtDate(inv.order_date)}</td>
          <td class="py-2 pr-3 font-semibold">${esc(inv.vendor || '—')}</td>
          <td class="py-2 pr-3">${esc(inv.order_number || '—')}${inv.expense_id && expNames.get(inv.expense_id) ? `<span class="block text-xs text-sage-700">💸 ${esc(expNames.get(inv.expense_id))}</span>` : (inv.expense_id ? '' : `<button type="button" data-create-expense="${inv.id}" class="block text-xs text-sage-700 underline">➕ Create expense</button>`)}</td>
          <td class="py-2 pr-3">${esc(inv.items_summary || '—')}${inv.notes ? `<span class="block text-xs text-navy-400">${esc(inv.notes)}</span>` : ''}${packetBlock(inv)}</td>
          <td class="py-2 pr-3 text-right font-semibold">${money(inv.total)}</td>
          <td class="py-2 text-right whitespace-nowrap">
            ${inv.email_link ? `<a href="${esc(inv.email_link)}" target="_blank" rel="noopener" class="text-xs text-sage-700 underline" title="Open the source email">✉️ email</a> ` : ''}${inv.pdf_path ? `<a href="${esc(inv.pdf_path)}" target="_blank" rel="noopener" class="text-xs text-sage-700 underline">PDF</a> ` : ''}
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
          email_link: $('#inv-email') && $('#inv-email').value.trim() ? $('#inv-email').value.trim() : null,
          expense_id: $('#inv-expense').value ? Number($('#inv-expense').value) : null,
        });
        const pdfInput = $('#inv-pdf');
        if (pdfInput.files.length) {
          const data = new FormData();
          data.append('file', pdfInput.files[0], pdfInput.files[0].name);
          await api.upload(`/api/invoices/${created.id}/pdf`, data);
        }
        toast('Invoice saved 🧾', 'ok');
        ['#inv-vendor', '#inv-order', '#inv-total', '#inv-items', '#inv-notes', '#inv-email'].forEach((s) => { if ($(s)) $(s).value = ''; });
        $('#inv-expense').value = '';
        pdfInput.value = '';
        load();
      } catch (error) { toast(`Could not save invoice: ${error.message}`, 'err'); }
    });

    $('#invoices-rows').addEventListener('click', async (event) => {
      if (await handlePkClick(event, 'invoice', load)) return;
      const createExpBtn = event.target.closest('[data-create-expense]');
      if (createExpBtn) {
        try {
          await api.post(`/api/invoices/${createExpBtn.dataset.createExpense}/create-expense`);
          toast('Expense created 💸', 'ok');
          load();
        } catch (error) { toast(`Could not create expense: ${error.message}`, 'err'); }
        return;
      }
      const btn = event.target.closest('[data-del-inv]');
      if (!btn) return;
      if (!window.confirm('Delete this invoice? Its PDF and any auto-created expense go with it.')) return;
      try {
        await api.del(`/api/invoices/${btn.dataset.delInv}`);
        toast('Invoice deleted.', 'ok');
        load();
      } catch (error) { toast(`Could not delete: ${error.message}`, 'err'); }
    });

    $('#invoices-rows').addEventListener('change', async (event) => {
      await handlePkChange(event, 'invoice', load);
    });

    load().catch((error) => toast(`Could not load invoices: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initCosts);
})();

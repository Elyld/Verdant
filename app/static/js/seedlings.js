/* Seedlings page — the indoor seed-starting workstation. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  const STATUS_LABELS = {
    sowing: '🌱 Sowing',
    germinating: '🌤️ Germinating',
    growing: '🌿 Growing',
    hardening: '💨 Hardening off',
    transplanted: '🪴 Transplanted',
    finished: '✅ Finished',
    failed: '❌ Failed',
  };
  const STATUS_PILL = {
    sowing: 'bg-beige-200 text-navy-700',
    germinating: 'bg-sage-200 text-sage-800',
    growing: 'bg-sage-300/50 text-sage-800',
    hardening: 'bg-navy-100 text-navy-700',
    transplanted: 'bg-sage-500/20 text-navy-800',
    finished: 'bg-sage-100 text-navy-500',
    failed: 'bg-red-100 text-red-700',
  };
  const NEXT_LABEL = {
    sowing: 'Sprouted →',
    germinating: 'Growing →',
    growing: 'Harden off →',
    hardening: 'Transplant →',
    transplanted: 'Finish →',
  };
  const ACTIVE = ['sowing', 'germinating', 'growing', 'hardening'];

  function initSeedlings() {
    if (!$('#panel-seedlings')) return;
    let packets = [];
    let editingId = null;

    const todayISO = () => new Date().toISOString().slice(0, 10);
    function daysBetween(aISO, bISO) {
      const ms = new Date(bISO + 'T12:00:00') - new Date(aISO + 'T12:00:00');
      return Math.round(ms / 86400000);
    }
    const packetById = (id) => packets.find((p) => p.id === Number(id));

    function setupChips(b) {
      const chips = [];
      if (b.tray) chips.push(`🗂️ ${esc(b.tray)}`);
      if (b.location) chips.push(`📍 ${esc(b.location)}`);
      if (b.heat_mat) chips.push('🔥 warming mat');
      if (b.grow_light) chips.push(`💡 ${esc(b.grow_light)}`);
      const pkt = b.packet_id ? packetById(b.packet_id) : null;
      if (pkt) chips.push(`📦 ${esc(pkt.vendor_name || pkt.variety_name || 'stash packet')}`);
      return chips.length
        ? `<div class="flex flex-wrap gap-1.5 text-xs">${chips.map((c) => `<span class="pill">${c}</span>`).join('')}</div>`
        : '';
    }

    function germBlock(b) {
      if (!b.cells_sown && !b.germinated) return '';
      const sown = b.cells_sown || b.germinated;
      const pct = sown ? Math.min(100, Math.round((b.germinated / sown) * 100)) : 0;
      const days = b.germination_date && b.sow_date ? daysBetween(b.sow_date, b.germination_date) : null;
      return `<div class="space-y-1">
        <div class="flex justify-between text-xs text-navy-600"><span>Germination</span><span>${b.germinated}/${sown}${sown ? ` (${pct}%)` : ''}</span></div>
        <div class="h-2 overflow-hidden rounded-full bg-beige-200"><div class="h-2 rounded-full bg-sage-500" style="width:${pct}%"></div></div>
        ${b.germination_date ? `<p class="text-xs text-navy-500">First sprout ${esc(b.germination_date)}${days !== null ? ` · ${days} day${days === 1 ? '' : 's'} to germinate` : ''}</p>` : ''}
      </div>`;
    }

    function staleHint(b) {
      if (!ACTIVE.includes(b.status) || !b.sow_date) return '';
      if (b.germinated > 0) return '';
      if (daysBetween(b.sow_date, todayISO()) >= 21) {
        return `<p class="text-xs font-semibold text-amber-700">⚠️ No sprouts after 3+ weeks — check the setup?</p>`;
      }
      return '';
    }

    function card(b) {
      const age = b.sow_date ? `${daysBetween(b.sow_date, todayISO())} days ago` : '';
      return `<div class="card space-y-2">
        <div class="flex items-start justify-between gap-2">
          <div>
            <p class="font-display text-lg font-semibold text-navy-800">${esc(b.variety_name)}</p>
            <p class="text-xs text-navy-500">${b.sow_date ? `Sown ${esc(b.sow_date)} · ${age}` : ''}</p>
          </div>
          <span class="pill ${STATUS_PILL[b.status] || ''}">${STATUS_LABELS[b.status] || esc(b.status)}</span>
        </div>
        ${setupChips(b)}
        ${germBlock(b)}
        ${staleHint(b)}
        ${b.transplant_date ? `<p class="text-xs text-navy-500">🪴 Transplanted ${esc(b.transplant_date)}</p>` : ''}
        ${b.notes ? `<p class="text-sm text-navy-600">${esc(b.notes)}</p>` : ''}
        <div class="flex flex-wrap gap-3 pt-1 text-xs">
          ${ACTIVE.includes(b.status) ? `<button type="button" data-sprout="${b.id}" class="font-semibold text-sage-700 underline">+ sprout</button>` : ''}
          ${NEXT_LABEL[b.status] ? `<button type="button" data-advance="${b.id}" class="font-semibold text-navy-700 underline">${NEXT_LABEL[b.status]}</button>` : ''}
          <button type="button" data-edit-batch="${b.id}" class="text-navy-500 underline">edit</button>
          <button type="button" data-del-batch="${b.id}" class="text-red-700 underline">delete</button>
        </div>
      </div>`;
    }

    async function load() {
      const [batches, pkts] = await Promise.all([
        api.get('/api/seedling-batches/').catch(() => []),
        api.get('/api/seed-packets/').catch(() => []),
      ]);
      const list = Array.isArray(batches) ? batches : [];
      packets = Array.isArray(pkts) ? pkts : [];

      // Variety datalist + packet picker.
      const varieties = [...new Set([...packets.map((p) => p.variety_name), ...list.map((b) => b.variety_name)].filter(Boolean))].sort();
      $('#seedling-varieties').innerHTML = varieties.map((v) => `<option value="${esc(v)}"></option>`).join('');
      const keepPacket = $('#seedling-packet').value;
      $('#seedling-packet').innerHTML = '<option value="">— none —</option>' + packets
        .map((p) => `<option value="${p.id}">${esc(p.variety_name)}${p.vendor_name ? ` · ${esc(p.vendor_name)}` : ''}</option>`)
        .join('');
      if (keepPacket) $('#seedling-packet').value = keepPacket;

      const active = list.filter((b) => ACTIVE.includes(b.status));
      const done = list.filter((b) => !ACTIVE.includes(b.status));
      $('#seedling-active-empty').classList.toggle('hidden', active.length > 0);
      $('#seedling-done-empty').classList.toggle('hidden', done.length > 0);
      $('#seedling-active').innerHTML = active.map(card).join('');
      $('#seedling-done').innerHTML = done.map(card).join('');
    }

    function resetForm() {
      editingId = null;
      $('#seedling-id').value = '';
      $('#seedling-form').reset();
      $('#seedling-sow').value = todayISO();
      $('#seedling-form-title').textContent = 'Start a batch';
      $('#seedling-submit').textContent = 'Start batch';
      $('#seedling-cancel').classList.add('hidden');
    }

    $('#seedling-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        variety_name: $('#seedling-variety').value.trim(),
        sow_date: $('#seedling-sow').value || todayISO(),
        tray: $('#seedling-tray').value.trim(),
        location: $('#seedling-location').value.trim(),
        heat_mat: $('#seedling-heatmat').checked,
        grow_light: $('#seedling-light').value.trim(),
        cells_sown: $('#seedling-cells').value ? Number($('#seedling-cells').value) : null,
        packet_id: $('#seedling-packet').value ? Number($('#seedling-packet').value) : null,
        notes: $('#seedling-notes').value.trim(),
      };
      if (!payload.variety_name) { toast('Give the batch a variety.', 'error'); return; }
      try {
        if (editingId) {
          await api.patch(`/api/seedling-batches/${editingId}`, payload);
          toast('Batch updated.');
        } else {
          await api.post('/api/seedling-batches/', payload);
          toast('Batch started. 🌱');
        }
        resetForm();
        load();
      } catch (err) {
        toast(err.message || 'Could not save batch.', 'error');
      }
    });

    $('#seedling-cancel').addEventListener('click', resetForm);

    $('#panel-seedlings').addEventListener('click', async (e) => {
      const sproutBtn = e.target.closest('[data-sprout]');
      const advBtn = e.target.closest('[data-advance]');
      const editBtn = e.target.closest('[data-edit-batch]');
      const delBtn = e.target.closest('[data-del-batch]');
      try {
        if (sproutBtn) {
          await api.post(`/api/seedling-batches/${sproutBtn.dataset.sprout}/sprout?count=1`, {});
          toast('Sprout logged. 🌱');
          load();
        } else if (advBtn) {
          const updated = await api.post(`/api/seedling-batches/${advBtn.dataset.advance}/advance`, {});
          toast(`Moved to ${STATUS_LABELS[updated.status] || updated.status}.`);
          load();
        } else if (editBtn) {
          const b = await api.get(`/api/seedling-batches/${editBtn.dataset.editBatch}`);
          editingId = b.id;
          $('#seedling-variety').value = b.variety_name || '';
          $('#seedling-sow').value = b.sow_date || '';
          $('#seedling-tray').value = b.tray || '';
          $('#seedling-location').value = b.location || '';
          $('#seedling-heatmat').checked = !!b.heat_mat;
          $('#seedling-light').value = b.grow_light || '';
          $('#seedling-cells').value = b.cells_sown || '';
          $('#seedling-packet').value = b.packet_id || '';
          $('#seedling-notes').value = b.notes || '';
          $('#seedling-form-title').textContent = `Edit ${b.variety_name}`;
          $('#seedling-submit').textContent = 'Save changes';
          $('#seedling-cancel').classList.remove('hidden');
          $('#seedling-form').scrollIntoView({ behavior: 'smooth' });
        } else if (delBtn) {
          if (!confirm('Delete this batch?')) return;
          await api.del(`/api/seedling-batches/${delBtn.dataset.delBatch}`);
          toast('Deleted.');
          load();
        }
      } catch (err) {
        toast(err.message || 'Something went wrong.', 'error');
      }
    });

    $('#seedling-sow').value = todayISO();
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSeedlings);
  } else {
    initSeedlings();
  }
})();

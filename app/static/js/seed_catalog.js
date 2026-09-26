/* Seed catalog tab on the Seeds page — the seed stash inventory. */
(() => {
  'use strict';

  const { $, $$, esc, api, toast } = globalThis.Verdant;

  function initSeedCatalog() {
    const grid = $('#catalog-grid');
    if (!grid) return;
    const params = new URLSearchParams(location.search);

    let packets = [];
    let vendors = [];

    function setTab(which) {
      const catalog = which === 'catalog';
      $('#seed-tab-sources').classList.toggle('hidden', catalog);
      $('#seed-tab-catalog').classList.toggle('hidden', !catalog);
      $('#seed-vendor-filter').classList.toggle('hidden', catalog);
      $('#seed-add-toggle').classList.toggle('hidden', catalog);
      const on = ['bg-beige-50', 'text-navy-800', 'shadow'];
      for (const cls of on) {
        $('#seed-tabbtn-sources').classList.toggle(cls, !catalog);
        $('#seed-tabbtn-catalog').classList.toggle(cls, catalog);
      }
      if (catalog) load();
    }

    function card(p) {
      const vendor = vendors.find((v) => v.id === p.vendor_id);
      const vendorName = vendor ? vendor.source : '';
      return `<div class="overflow-hidden rounded-xl bg-beige-50 ring-1 ring-beige-200">
        ${p.photo_path
          ? `<button type="button" data-lightbox="${esc(p.photo_path)}" class="block w-full"><img src="${esc(p.photo_path)}" alt="${esc(p.variety_name)} packet" class="h-36 w-full object-cover" loading="lazy" /></button>`
          : `<div class="flex h-36 w-full items-center justify-center bg-sage-100 text-4xl">🌱</div>`}
        <div class="space-y-1 p-4">
          <div class="flex items-start justify-between gap-2">
            <p class="font-semibold text-navy-800">${esc(p.variety_name)}</p>
            ${p.category ? `<span class="pill">${esc(p.category)}</span>` : ''}
          </div>
          ${p.species_type ? `<p class="text-sm italic text-navy-500">${esc(p.species_type)}</p>` : ''}
          <div class="text-sm text-navy-600">
            ${vendorName ? `<p>🏪 ${p.vendor_url ? `<a href="${esc(p.vendor_url)}" target="_blank" rel="noopener" class="underline decoration-sage-400 hover:text-navy-800">${esc(vendorName)}</a>` : esc(vendorName)}</p>` : ''}
            ${p.year_acquired ? `<p>📅 Bought ${p.year_acquired}</p>` : ''}
            ${p.quantity ? `<p>⚖️ ${esc(p.quantity)}</p>` : ''}
          </div>
          ${p.notes ? `<p class="text-sm text-navy-500">${esc(p.notes)}</p>` : ''}
          <div class="flex gap-3 pt-1 text-xs">
            <button type="button" data-edit-packet="${p.id}" class="text-sage-700 underline">edit</button>
            <button type="button" data-del-packet="${p.id}" class="text-red-700 underline">delete</button>
          </div>
        </div>
      </div>`;
    }

    function filtered() {
      const q = ($('#catalog-search').value || '').toLowerCase();
      const cat = $('#catalog-category').value;
      return packets.filter((p) =>
        (!cat || p.category === cat) &&
        (!q || `${p.variety_name} ${p.species_type} ${p.category}`.toLowerCase().includes(q)));
    }

    async function load() {
      const [pkts, srcs] = await Promise.all([
        api.get('/api/seed-packets/').catch(() => []),
        api.get('/api/seed-sources/').catch(() => []),
      ]);
      packets = Array.isArray(pkts) ? pkts : [];
      vendors = Array.isArray(srcs) ? srcs : [];
      const cats = [...new Set(packets.map((p) => p.category).filter(Boolean))].sort();
      $('#catalog-category').innerHTML = '<option value="">All types</option>' +
        cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      $('#packet-categories').innerHTML = cats.map((c) => `<option value="${esc(c)}">`).join('');
      $('#packet-vendor').innerHTML = '<option value="">— none —</option>' +
        vendors.map((v) => `<option value="${v.id}">${esc(v.source)}${v.variety ? ` · ${esc(v.variety)}` : ''}</option>`).join('');
      const list = filtered();
      $('#catalog-empty').classList.toggle('hidden', list.length > 0);
      grid.innerHTML = list.map(card).join('');
    }

    function openModal(packet) {
      $('#packet-modal-title').textContent = packet ? 'Edit seed packet' : 'Add seed packet';
      $('#packet-submit').textContent = packet ? 'Save changes' : 'Add packet';
      $('#packet-id').value = packet ? packet.id : '';
      $('#packet-variety').value = packet ? packet.variety_name : '';
      $('#packet-species').value = packet ? packet.species_type : '';
      $('#packet-category').value = packet ? packet.category : '';
      $('#packet-year').value = packet ? (packet.year_acquired || '') : new Date().getFullYear();
      $('#packet-vendor').value = packet && packet.vendor_id ? packet.vendor_id : '';
      $('#packet-vendor-url').value = packet ? packet.vendor_url : '';
      $('#packet-qty').value = packet ? packet.quantity : '';
      $('#packet-notes').value = packet ? (packet.notes || '') : '';
      $('#packet-photo').value = '';
      $('#packet-modal').classList.remove('hidden');
      $('#packet-modal').classList.add('flex');
      $('#packet-variety').focus();
    }

    function closeModal() {
      $('#packet-modal').classList.add('hidden');
      $('#packet-modal').classList.remove('flex');
    }

    $('#seed-tabbtn-sources').addEventListener('click', () => setTab('sources'));
    $('#seed-tabbtn-catalog').addEventListener('click', () => setTab('catalog'));
    $('#catalog-add').addEventListener('click', () => openModal(null));
    $('#packet-close').addEventListener('click', closeModal);
    $('#packet-cancel').addEventListener('click', closeModal);
    $('#catalog-search').addEventListener('input', load);
    $('#catalog-category').addEventListener('change', load);

    $('#packet-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('#packet-id').value;
      const payload = {
        variety_name: $('#packet-variety').value.trim(),
        species_type: $('#packet-species').value.trim(),
        category: $('#packet-category').value.trim(),
        year_acquired: $('#packet-year').value ? Number($('#packet-year').value) : null,
        vendor_id: $('#packet-vendor').value ? Number($('#packet-vendor').value) : null,
        vendor_url: $('#packet-vendor-url').value.trim(),
        quantity: $('#packet-qty').value.trim(),
        notes: $('#packet-notes').value.trim(),
      };
      try {
        const saved = id
          ? await api.patch(`/api/seed-packets/${id}`, payload)
          : await api.post('/api/seed-packets/', payload);
        const file = $('#packet-photo').files[0];
        if (file) {
          const form = new FormData();
          form.append('file', file);
          await api.upload(`/api/seed-packets/${saved.id}/photo`, form);
        }
        closeModal();
        toast(id ? 'Packet updated.' : 'Packet added.');
        load();
      } catch (err) {
        toast(err.message || 'Could not save packet.', 'error');
      }
    });

    grid.addEventListener('click', async (e) => {
      const editBtn = e.target.closest('[data-edit-packet]');
      const delBtn = e.target.closest('[data-del-packet]');
      if (editBtn) {
        const packet = packets.find((p) => p.id === Number(editBtn.dataset.editPacket));
        if (packet) openModal(packet);
      } else if (delBtn) {
        if (!confirm('Delete this packet from the catalog?')) return;
        try {
          await api.del(`/api/seed-packets/${delBtn.dataset.delPacket}`);
          toast('Deleted.');
          load();
        } catch (err) {
          toast(err.message || 'Could not delete.', 'error');
        }
      }
    });

    // NFC tag deep link: /seeds?tab=catalog&add=1 opens the add form.
    if (params.get('tab') === 'catalog') {
      setTab('catalog');
      if (params.get('add') === '1') openModal(null);
    } else {
      setTab('sources');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSeedCatalog);
  } else {
    initSeedCatalog();
  }
})();

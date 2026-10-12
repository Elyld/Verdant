/* Seed catalog tab on the Seeds page — the seed stash inventory. */
(() => {
  'use strict';

  const { $, $$, esc, api, toast } = globalThis.Verdant;

  function initSeedCatalog() {
    const grid = $('#catalog-grid');
    if (!grid) return;
    const params = new URLSearchParams(location.search);

    let packets = [];

    const SEED_TABS = ['sources', 'catalog', 'assistant'];
    const TAB_ON = ['bg-beige-50', 'text-navy-800', 'shadow'];
    function setTab(which) {
      if (!SEED_TABS.includes(which)) which = 'sources';
      for (const t of SEED_TABS) {
        const active = t === which;
        $(`#seed-tab-${t}`).classList.toggle('hidden', !active);
        const btn = $(`#seed-tabbtn-${t}`);
        if (btn) for (const cls of TAB_ON) btn.classList.toggle(cls, active);
      }
      if (which === 'catalog') load();
    }

    const RATING_BADGE = { no: '👎', yes: '👍', favorite: '⭐' };
    const RATING_TITLE = { no: 'Skip it', yes: 'Grow again', favorite: 'Favorite — must grow' };

    function card(p) {
      const vendorName = p.vendor_name || '';
      return `<div class="overflow-hidden rounded-xl bg-beige-50 ring-1 ring-beige-200">
        ${p.photo_path
          ? `<div class="relative">
               <button type="button" data-lightbox="${esc(p.photo_path)}" class="block w-full"><img src="${esc(p.photo_path)}" alt="${esc(p.variety_name)} packet" data-packet-img data-side="front" class="h-36 w-full object-cover" loading="lazy" /></button>
               ${p.photo_back_path ? `<button type="button" data-flip data-front="${esc(p.photo_path)}" data-back="${esc(p.photo_back_path)}" title="Flip to back of packet" class="absolute bottom-2 right-2 rounded-full bg-navy-800/85 px-2.5 py-1 text-xs font-semibold text-beige-50 ring-1 ring-beige-200/50 hover:bg-navy-700">⇄ Back</button>` : ''}
             </div>`
          : `<div class="flex h-36 w-full items-center justify-center bg-sage-100 text-4xl">🌱</div>`}
        <div class="space-y-1 p-4">
          <div class="flex items-start justify-between gap-2">
            <p class="font-semibold text-navy-800">${esc(p.variety_name)}${p.grow_again && RATING_BADGE[p.grow_again] ? ` <span title="Grow again: ${esc(RATING_TITLE[p.grow_again])}">${RATING_BADGE[p.grow_again]}</span>` : ''}</p>
            ${p.category ? `<span class="pill">${esc(p.category)}</span>` : ''}
          </div>
          ${p.species_type ? `<p class="text-sm italic text-navy-500">${esc(p.species_type)}</p>` : ''}
          <div class="text-sm text-navy-600">
            ${vendorName ? `<p>🏪 ${p.vendor_url ? `<a href="${esc(p.vendor_url)}" target="_blank" rel="noopener" class="underline decoration-sage-400 hover:text-navy-800">${esc(vendorName)}</a>` : esc(vendorName)}</p>` : ''}
            ${p.year_acquired ? `<p>📅 Bought ${p.year_acquired}</p>` : ''}
            ${p.quantity ? `<p>⚖️ ${esc(p.quantity)}${p.seed_count != null ? ` (${p.seed_count} seeds)` : ''}</p>` : (p.seed_count != null ? `<p>⚖️ ${p.seed_count} seeds</p>` : '')}
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
      const photo = $('#catalog-photo').value;
      return packets.filter((p) =>
        (!cat || p.category === cat) &&
        (!photo || (photo === 'with' ? !!p.photo_path : !p.photo_path)) &&
        (!q || `${p.variety_name} ${p.species_type} ${p.category}`.toLowerCase().includes(q)));
    }

    async function load() {
      const [pkts, vendorNames] = await Promise.all([
        api.get('/api/seed-packets/').catch(() => []),
        api.get('/api/seed-packets/vendors').catch(() => []),
      ]);
      packets = Array.isArray(pkts) ? pkts : [];
      const cats = [...new Set(packets.map((p) => p.category).filter(Boolean))].sort();
      $('#catalog-category').innerHTML = '<option value="">All types</option>' +
        cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      $('#packet-categories').innerHTML = cats.map((c) => `<option value="${esc(c)}">`).join('');
      const names = Array.isArray(vendorNames) ? vendorNames : [];
      $('#packet-vendor-list').innerHTML =
        names.map((n) => `<option value="${esc(n)}">`).join('');
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
      $('#packet-vendor').value = packet ? (packet.vendor_name || '') : '';
      $('#packet-vendor-url').value = packet ? packet.vendor_url : '';
      $('#packet-qty').value = packet ? packet.quantity : '';
      $('#packet-seed-count').value = packet && packet.seed_count != null ? packet.seed_count : '';
      $('#packet-grow-again').value = packet ? (packet.grow_again || '') : '';
      $('#packet-notes').value = packet ? (packet.notes || '') : '';
      $('#packet-photo').value = '';
      $('#packet-photo-back').value = '';
      // Library attach works for new packets too: the pick is stashed and
      // attached right after the packet is created on save.
      pendingLibrary = {};
      renderPending();
      // Show current photos with crop buttons when editing an existing packet.
      renderCurrentPhotos(packet);
      $('#packet-library-row').classList.remove('hidden');
      $('#packet-library-row').classList.add('flex');
      $('#packet-library-hint').classList.remove('hidden');
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
    $('#seed-tabbtn-assistant').addEventListener('click', () => setTab('assistant'));
    $('#catalog-add').addEventListener('click', () => openModal(null));
    $('#catalog-from-sources').addEventListener('click', async () => {
      if (!confirm('Copy every seed source into the stash as a packet? (Already-moved ones are skipped.)')) return;
      try {
        const res = await api.post('/api/seed-packets/from-sources', {});
        toast(`Moved ${res.created} source${res.created === 1 ? '' : 's'} to the stash${res.skipped ? `, ${res.skipped} already there` : ''}.`);
        load();
      } catch (err) {
        toast(err.message || 'Could not move sources.', 'error');
      }
    });
    $('#packet-close').addEventListener('click', closeModal);
    $('#packet-cancel').addEventListener('click', closeModal);
    $('#catalog-search').addEventListener('input', load);
    $('#catalog-category').addEventListener('change', load);
    $('#catalog-photo').addEventListener('change', load);

    // ---- Photo crop tool ----
    // Crops a packet's saved front/back photo in place (the library original
    // is never touched — the packet holds its own copy). Reuses the existing
    // /photo?side= upload endpoint; the crop happens client-side on a canvas.
    const crop = { packetId: null, side: 'front', ratio: null, rect: null, mode: null, start: null };

    function cropImg() { return $('#crop-img'); }
    function cropBox() { return $('#crop-box'); }
    function cropStage() { return $('#crop-stage'); }

    function imgOffset() {
      const s = cropStage().getBoundingClientRect();
      const i = cropImg().getBoundingClientRect();
      return { x: i.left - s.left, y: i.top - s.top, w: i.width, h: i.height };
    }

    function paintBox() {
      const box = cropBox();
      if (!crop.rect) { box.classList.add('hidden'); return; }
      const o = imgOffset();
      box.classList.remove('hidden');
      box.style.left = `${o.x + crop.rect.x}px`;
      box.style.top = `${o.y + crop.rect.y}px`;
      box.style.width = `${crop.rect.w}px`;
      box.style.height = `${crop.rect.h}px`;
    }

    function clampRect(r) {
      const o = imgOffset();
      r.x = Math.max(0, Math.min(r.x, o.w - 8));
      r.y = Math.max(0, Math.min(r.y, o.h - 8));
      r.w = Math.max(8, Math.min(r.w, o.w - r.x));
      r.h = Math.max(8, Math.min(r.h, o.h - r.y));
      return r;
    }

    function openCrop(src, side, packetId) {
      crop.packetId = packetId;
      crop.side = side;
      crop.rect = null;
      crop.ratio = null;
      $$('#crop-modal [data-crop-ratio]').forEach((b) =>
        b.classList.toggle('crop-ratio-on', b.dataset.cropRatio === ''));
      const img = cropImg();
      img.onload = () => paintBox();
      img.src = src;
      $('#crop-side-label').textContent = side === 'front' ? '— front of packet' : '— back of packet';
      $('#crop-modal').classList.remove('hidden');
      $('#crop-modal').classList.add('flex');
    }

    function closeCrop() {
      $('#crop-modal').classList.add('hidden');
      $('#crop-modal').classList.remove('flex');
      cropImg().src = '';
      crop.rect = null;
      crop.mode = null;
    }

    function stagePoint(ev) {
      const o = imgOffset();
      const s = cropStage().getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(ev.clientX - s.left - o.x, o.w)),
        y: Math.max(0, Math.min(ev.clientY - s.top - o.y, o.h)),
      };
    }

    function applyRatio(r, anchor) {
      // anchor: which corner stays fixed while the ratio is enforced.
      if (!crop.ratio) return r;
      const want = crop.ratio;
      if (anchor === 'se') {
        if (r.w / r.h > want) r.w = r.h * want; else r.h = r.w / want;
      }
      return clampRect(r);
    }

    cropStage().addEventListener('pointerdown', (ev) => {
      if (ev.target.closest('#crop-handle')) {
        crop.mode = 'resize';
      } else if (crop.rect) {
        const p = stagePoint(ev);
        const r = crop.rect;
        if (p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h) {
          crop.mode = 'move';
        } else {
          crop.mode = 'draw';
        }
      } else {
        crop.mode = 'draw';
      }
      const p = stagePoint(ev);
      crop.start = { x: p.x, y: p.y, rx: crop.rect?.x ?? 0, ry: crop.rect?.y ?? 0, rw: crop.rect?.w ?? 0, rh: crop.rect?.h ?? 0 };
      cropStage().setPointerCapture(ev.pointerId);
      ev.preventDefault();
    });

    cropStage().addEventListener('pointermove', (ev) => {
      if (!crop.mode) return;
      const p = stagePoint(ev);
      const s = crop.start;
      if (crop.mode === 'draw') {
        let r = { x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) };
        r = applyRatio(r, 'se');
        crop.rect = clampRect(r);
      } else if (crop.mode === 'move') {
        crop.rect = clampRect({ x: s.rx + (p.x - s.x), y: s.ry + (p.y - s.y), w: s.rw, h: s.rh });
      } else if (crop.mode === 'resize') {
        let r = { x: s.rx, y: s.ry, w: Math.max(8, s.rw + (p.x - s.x)), h: Math.max(8, s.rh + (p.y - s.y)) };
        r = applyRatio(r, 'se');
        crop.rect = clampRect(r);
      }
      paintBox();
    });

    cropStage().addEventListener('pointerup', () => { crop.mode = null; });
    cropStage().addEventListener('pointercancel', () => { crop.mode = null; });

    $$('#crop-modal [data-crop-ratio]').forEach((btn) => {
      btn.addEventListener('click', () => {
        crop.ratio = btn.dataset.cropRatio ? Number(btn.dataset.cropRatio) : null;
        $$('#crop-modal [data-crop-ratio]').forEach((b) => b.classList.toggle('crop-ratio-on', b === btn));
        if (crop.rect && crop.ratio) {
          crop.rect = applyRatio({ ...crop.rect }, 'se');
          paintBox();
        }
      });
    });

    $('#crop-reset').addEventListener('click', () => { crop.rect = null; paintBox(); });
    $('#crop-close').addEventListener('click', closeCrop);

    $('#crop-apply').addEventListener('click', async () => {
      const img = cropImg();
      if (!crop.rect || !img.naturalWidth) { toast('Draw a crop area first.', 'error'); return; }
      const scale = img.naturalWidth / img.clientWidth;
      const sx = Math.round(crop.rect.x * scale);
      const sy = Math.round(crop.rect.y * scale);
      const sw = Math.round(crop.rect.w * scale);
      const sh = Math.round(crop.rect.h * scale);
      const canvas = document.createElement('canvas');
      canvas.width = sw;
      canvas.height = sh;
      canvas.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
      if (!blob) { toast('Could not render the crop.', 'error'); return; }
      try {
        const form = new FormData();
        form.append('file', blob, 'crop.jpg');
        const updated = await api.upload(`/api/seed-packets/${crop.packetId}/photo?side=${crop.side}`, form);
        const local = packets.find((p) => p.id === crop.packetId);
        if (local) {
          if (crop.side === 'front') local.photo_path = updated.photo_path;
          else local.photo_back_path = updated.photo_back_path;
          renderCurrentPhotos(local);
        }
        toast('Crop applied.');
        closeCrop();
        load();
      } catch (err) {
        toast(err.message || 'Could not apply the crop.', 'error');
      }
    });

    function renderCurrentPhotos(packet) {
      const wrap = $('#packet-current-photos');
      if (!packet || (!packet.photo_path && !packet.photo_back_path)) {
        wrap.classList.add('hidden');
        wrap.classList.remove('flex');
        wrap.innerHTML = '';
        return;
      }
      const thumb = (src, side, label) => src ? `
        <div class="flex items-center gap-2 rounded-xl bg-beige-100 p-2 ring-1 ring-beige-200">
          <img src="${esc(src)}" alt="${label} of packet" class="h-16 w-16 rounded-lg object-cover" />
          <div class="text-xs">
            <p class="font-semibold text-navy-700">${label}</p>
            <button type="button" data-crop-side="${side}" class="text-sage-700 underline">✂️ Crop</button>
          </div>
        </div>` : '';
      wrap.innerHTML = thumb(packet.photo_path, 'front', 'Front') + thumb(packet.photo_back_path, 'back', 'Back');
      wrap.classList.remove('hidden');
      wrap.classList.add('flex');
    }

    $('#packet-current-photos').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-crop-side]');
      if (!btn) return;
      const packetId = Number($('#packet-id').value);
      const packet = packets.find((p) => p.id === packetId);
      if (!packet) return;
      const side = btn.dataset.cropSide;
      const src = side === 'front' ? packet.photo_path : packet.photo_back_path;
      if (src) openCrop(src, side, packetId);
    });

    // ---- Photo library picker ----
    let libSide = 'front';
    // side -> image_id picked for a not-yet-saved (new) packet; attached on save.
    let pendingLibrary = {};

    function renderPending() {
      $('#packet-library-front').textContent =
        `🖼️ Front from photo library${pendingLibrary.front ? ' ✓' : ''}`;
      $('#packet-library-back').textContent =
        `🖼️ Back from photo library${pendingLibrary.back ? ' ✓' : ''}`;
    }

    function closeLibraryPicker() {
      $('#library-modal').classList.add('hidden');
      $('#library-modal').classList.remove('flex');
    }

    async function loadLibraryImages() {
      const albumId = $('#library-album').value;
      const qs = albumId ? `?album_id=${encodeURIComponent(albumId)}&limit=200` : '?limit=200';
      let imgs = [];
      try {
        const res = await api.get(`/api/album-images/${qs}`);
        imgs = Array.isArray(res) ? res : [];
      } catch (err) {
        toast(err.message || 'Could not load photos.', 'error');
      }
      $('#library-empty').classList.toggle('hidden', imgs.length > 0);
      $('#library-grid').innerHTML = imgs.map((img) =>
        `<button type="button" data-lib-img="${img.id}" title="${esc(img.title || img.original_name || 'photo')}" class="overflow-hidden rounded-lg ring-1 ring-beige-200 hover:ring-2 hover:ring-sage-500">
           <img src="${esc(img.file_path)}" alt="" class="h-28 w-full object-cover" loading="lazy" />
         </button>`).join('');
    }

    async function openLibraryPicker(side) {
      libSide = side;
      $('#library-side-label').textContent = side === 'front' ? '— as front of packet' : '— as back of packet';
      let albums = [];
      try {
        const res = await api.get('/api/albums');
        albums = Array.isArray(res) ? res : [];
      } catch (err) {
        toast(err.message || 'Could not load albums.', 'error');
      }
      $('#library-album').innerHTML = '<option value="">All albums</option>' +
        albums.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join('');
      await loadLibraryImages();
      $('#library-modal').classList.remove('hidden');
      $('#library-modal').classList.add('flex');
    }

    $('#packet-library-front').addEventListener('click', () => openLibraryPicker('front'));
    $('#packet-library-back').addEventListener('click', () => openLibraryPicker('back'));
    $('#library-close').addEventListener('click', closeLibraryPicker);
    $('#library-album').addEventListener('change', loadLibraryImages);
    $('#library-grid').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-lib-img]');
      if (!btn) return;
      const packetId = $('#packet-id').value;
      const imageId = Number(btn.dataset.libImg);
      const sideLabel = libSide === 'front' ? 'Front' : 'Back';
      if (!packetId) {
        // New packet: stash the pick, attach it right after creation on save.
        pendingLibrary[libSide] = imageId;
        renderPending();
        toast(`${sideLabel} photo will be attached when you save.`);
        closeLibraryPicker();
        return;
      }
      try {
        await api.post(`/api/seed-packets/${packetId}/photo-from-library`,
          { image_id: imageId, side: libSide });
        toast(`${sideLabel} photo set from the library.`);
        closeLibraryPicker();
        closeModal();
        load();
      } catch (err) {
        toast(err.message || 'Could not attach photo.', 'error');
      }
    });

    $('#packet-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('#packet-id').value;
      const payload = {
        variety_name: $('#packet-variety').value.trim(),
        species_type: $('#packet-species').value.trim(),
        category: $('#packet-category').value.trim(),
        year_acquired: $('#packet-year').value ? Number($('#packet-year').value) : null,
        vendor_name: $('#packet-vendor').value.trim(),
        vendor_url: $('#packet-vendor-url').value.trim(),
        quantity: $('#packet-qty').value.trim(),
        seed_count: $('#packet-seed-count').value ? Number($('#packet-seed-count').value) : null,
        grow_again: $('#packet-grow-again').value,
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
        const backFile = $('#packet-photo-back').files[0];
        if (backFile) {
          const form = new FormData();
          form.append('file', backFile);
          await api.upload(`/api/seed-packets/${saved.id}/photo?side=back`, form);
        }
        // Library photos picked on the add form (or stashed before a save):
        // attach after files so an explicitly uploaded file wins a conflict.
        for (const side of ['front', 'back']) {
          if (pendingLibrary[side]) {
            await api.post(`/api/seed-packets/${saved.id}/photo-from-library`,
              { image_id: pendingLibrary[side], side });
          }
        }
        pendingLibrary = {};
        closeModal();
        toast(id ? 'Packet updated.' : 'Packet added.');
        load();
      } catch (err) {
        toast(err.message || 'Could not save packet.', 'error');
      }
    });

    grid.addEventListener('click', async (e) => {
      const flipBtn = e.target.closest('[data-flip]');
      if (flipBtn) {
        e.stopPropagation();
        const wrap = flipBtn.closest('.relative');
        const img = wrap.querySelector('[data-packet-img]');
        const lightboxBtn = wrap.querySelector('[data-lightbox]');
        const showingBack = img.dataset.side === 'back';
        img.dataset.side = showingBack ? 'front' : 'back';
        img.src = showingBack ? flipBtn.dataset.front : flipBtn.dataset.back;
        lightboxBtn.dataset.lightbox = img.src;
        flipBtn.textContent = showingBack ? '⇄ Back' : '⇄ Front';
        return;
      }
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
    const tabParam = params.get('tab');
    if (tabParam === 'assistant') {
      setTab('assistant');
    } else if (tabParam === 'catalog') {
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

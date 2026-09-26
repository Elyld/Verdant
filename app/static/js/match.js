/* Photo <-> plant matching workflow (/match page). */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initMatch() {
    const albumSel = $('#match-album');
    const plantSel = $('#match-plant');
    const unassignedOnly = $('#match-unassigned');
    if (!albumSel || !plantSel) return;

    let images = [];
    let index = 0;
    let plants = [];

    async function loadAlbums() {
      const albums = await api.get('/api/albums');
      if (!Array.isArray(albums)) return;
      const current = albumSel.value;
      albumSel.innerHTML = '<option value="">All albums</option>'
        + albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${(a.images || []).length})</option>`).join('');
      albumSel.value = current;
    }

    async function loadPlants() {
      const list = await api.get('/api/plants/').catch(() => []);
      plants = (Array.isArray(list) ? list : []).slice()
        .sort((a, b) => String(a.variety_name || '').localeCompare(String(b.variety_name || '')));
      plantSel.innerHTML = '<option value="">Choose a plant…</option>'
        + plants.map((p) => `<option value="${p.id}">${esc(p.variety_name)}</option>`).join('');
    }

    async function loadImages() {
      const params = new URLSearchParams({
        limit: '1000',
        unassigned_only: unassignedOnly.checked ? 'true' : 'false',
      });
      if (albumSel.value) params.set('album_id', albumSel.value);
      images = await api.get(`/api/album-images/?${params.toString()}`).catch(() => []);
      if (!Array.isArray(images)) images = [];
      index = 0;
      render();
    }

    function metaLine(img) {
      const bits = [];
      if (img.taken_at) bits.push('📅 ' + fmtDate(img.taken_at));
      const cam = [img.camera_make, img.camera_model].filter(Boolean).join(' ').trim();
      if (cam) bits.push('📷 ' + cam);
      if (img.latitude != null && img.longitude != null) {
        bits.push(`📍 ${Number(img.latitude).toFixed(4)}, ${Number(img.longitude).toFixed(4)}`);
      }
      return bits.join(' · ');
    }

    function render() {
      const empty = $('#match-empty');
      const workspace = $('#match-workspace');
      const progress = $('#match-progress');
      if (!images.length) {
        empty.classList.remove('hidden');
        workspace.classList.add('hidden');
        progress.textContent = '';
        return;
      }
      empty.classList.add('hidden');
      workspace.classList.remove('hidden');
      index = Math.max(0, Math.min(index, images.length - 1));
      const img = images[index];

      $('#match-photo').src = img.file_path;
      $('#match-photo').alt = img.title || img.original_name || 'Photo';
      $('#match-caption').textContent = img.title || img.original_name || `Photo #${img.id}`;
      $('#match-meta').textContent = metaLine(img);
      $('#match-tags').textContent = img.tags ? '🏷️ ' + img.tags : '';
      const assigned = images.filter((i) => i.plant_id).length;
      $('#match-counter').textContent = `${index + 1} / ${images.length} · ${assigned} assigned in this view`;
      progress.textContent = images.length === 1000 ? 'Showing first 1000 photos' : '';

      plantSel.value = img.plant_id ? String(img.plant_id) : '';
      updateBulkButton();
    }

    function sameDay(a, b) {
      if (!a || !b) return false;
      return String(a).slice(0, 10) === String(b).slice(0, 10);
    }

    function dayMates() {
      const img = images[index];
      if (!img || !img.taken_at) return [];
      return images.filter((i) => !i.plant_id && sameDay(i.taken_at, img.taken_at));
    }

    function updateBulkButton() {
      const btn = $('#match-bulk');
      const mates = dayMates();
      const hint = $('#match-bulk-hint');
      if (mates.length > 1) {
        btn.disabled = false;
        btn.textContent = `Assign all ${mates.length} from ${fmtDate(images[index].taken_at)}`;
        hint.textContent = 'Photos taken on the same day are usually the same plant session.';
      } else {
        btn.disabled = true;
        btn.textContent = 'Assign day\u2019s photos';
        hint.textContent = mates.length === 1
          ? 'This is the only unassigned photo from that day.'
          : 'Taken-date is unknown for this photo, so day grouping is unavailable.';
      }
    }

    function advance() {
      if (index < images.length - 1) index += 1;
      render();
    }

    function go(delta) {
      if (!images.length) return;
      index = (index + delta + images.length) % images.length;
      render();
    }

    async function assignCurrent() {
      const img = images[index];
      const plantId = plantSel.value ? Number(plantSel.value) : null;
      if (!img || !plantId) {
        toast('Choose a plant first.', 'err');
        return;
      }
      try {
        const updated = await api.patch(`/api/album-images/${img.id}`, { plant_id: plantId });
        if (unassignedOnly.checked) {
          images.splice(index, 1);
          if (index >= images.length) index = Math.max(0, images.length - 1);
        } else {
          images[index] = updated;
          advance();
          return;
        }
        render();
      } catch (error) {
        toast(`Could not assign: ${error.message}`, 'err');
      }
    }

    async function unassignCurrent() {
      const img = images[index];
      if (!img) return;
      try {
        const updated = await api.patch(`/api/album-images/${img.id}`, { plant_id: null });
        if (unassignedOnly.checked) {
          advance();
        } else {
          images[index] = updated;
          render();
        }
        toast('Unassigned.');
      } catch (error) {
        toast(`Could not unassign: ${error.message}`, 'err');
      }
    }

    async function bulkAssign() {
      const mates = dayMates();
      const plantId = plantSel.value ? Number(plantSel.value) : null;
      if (mates.length < 2 || !plantId) {
        toast('Choose a plant first.', 'err');
        return;
      }
      const name = plants.find((p) => p.id === plantId)?.variety_name || 'plant';
      try {
        const result = await api.post('/api/album-images/bulk-assign', {
          image_ids: mates.map((m) => m.id),
          plant_id: plantId,
        });
        const ids = new Set(mates.map((m) => m.id));
        if (unassignedOnly.checked) {
          images = images.filter((i) => !ids.has(i.id));
          if (index >= images.length) index = Math.max(0, images.length - 1);
        } else {
          images = images.map((i) => (ids.has(i.id) ? { ...i, plant_id: plantId, plant_variety: name } : i));
        }
        render();
        toast(`Assigned ${result.updated} photos to ${name}.`);
      } catch (error) {
        toast(`Bulk assign failed: ${error.message}`, 'err');
      }
    }

    $('#match-assign').addEventListener('click', assignCurrent);
    $('#match-skip').addEventListener('click', advance);
    $('#match-unassign').addEventListener('click', unassignCurrent);
    $('#match-bulk').addEventListener('click', bulkAssign);
    $('#match-reload').addEventListener('click', () => loadImages().catch((e) => toast(e.message, 'err')));
    albumSel.addEventListener('change', () => loadImages().catch((e) => toast(e.message, 'err')));
    unassignedOnly.addEventListener('change', () => loadImages().catch((e) => toast(e.message, 'err')));
    plantSel.addEventListener('change', updateBulkButton);
    $('#match-prev').addEventListener('click', () => go(-1));
    $('#match-next').addEventListener('click', () => go(1));
    document.addEventListener('keydown', (event) => {
      if (!$('#match-workspace') || $('#match-workspace').classList.contains('hidden')) return;
      if (event.target.matches('input, select, textarea')) return;
      if (event.key === 'ArrowLeft') go(-1);
      else if (event.key === 'ArrowRight') go(1);
    });

    Promise.all([loadAlbums(), loadPlants()])
      .then(loadImages)
      .catch((error) => toast(`Could not load: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initMatch);
})();

/* Photo <-> plant/packet matching workflow (/match page). */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initMatch() {
    const albumSel = $('#match-album');
    const targetSel = $('#match-plant');
    const unassignedOnly = $('#match-unassigned');
    if (!albumSel || !targetSel) return;

    let images = [];
    let index = 0;
    let plants = [];
    let packets = [];

    async function loadAlbums() {
      const albums = await api.get('/api/albums');
      if (!Array.isArray(albums)) return;
      const current = albumSel.value;
      albumSel.innerHTML = '<option value="">All albums</option>'
        + albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${(a.images || []).length})</option>`).join('');
      albumSel.value = current;
    }

    async function loadTargets() {
      const [plantList, packetList] = await Promise.all([
        api.get('/api/plants/').catch(() => []),
        api.get('/api/seed-packets/').catch(() => []),
      ]);
      plants = (Array.isArray(plantList) ? plantList : []).slice()
        .sort((a, b) => String(a.variety_name || '').localeCompare(String(b.variety_name || '')));
      packets = (Array.isArray(packetList) ? packetList : []).slice()
        .sort((a, b) => String(a.variety_name || '').localeCompare(String(b.variety_name || '')));
      const plantOpts = plants
        .map((p) => `<option value="p:${p.id}">${esc(p.variety_name)}</option>`).join('');
      const packetOpts = packets
        .map((p) => `<option value="s:${p.id}">${esc(packetLabel(p))}</option>`).join('');
      targetSel.innerHTML = '<option value="">Choose a plant or seed packet…</option>'
        + `<optgroup label="🌿 Plants">${plantOpts}</optgroup>`
        + `<optgroup label="🫘 Seed packets">${packetOpts}</optgroup>`;
    }

    function packetLabel(p) {
      const bits = [p.variety_name];
      const extra = [p.year_acquired, p.vendor_name].filter(Boolean).join(' · ');
      return extra ? `${bits[0]} (${extra})` : bits[0];
    }

    // The dropdown values are prefixed: p:<id> for plants, s:<id> for packets.
    function selectedTarget() {
      const v = targetSel.value || '';
      if (v.startsWith('p:')) return { plant_id: Number(v.slice(2)), seed_packet_id: null };
      if (v.startsWith('s:')) return { plant_id: null, seed_packet_id: Number(v.slice(2)) };
      return { plant_id: null, seed_packet_id: null };
    }

    function targetValue(img) {
      if (img.plant_id) return `p:${img.plant_id}`;
      if (img.seed_packet_id) return `s:${img.seed_packet_id}`;
      return '';
    }

    function targetName(target) {
      if (target.plant_id) return plants.find((p) => p.id === target.plant_id)?.variety_name || 'plant';
      if (target.seed_packet_id) return packets.find((p) => p.id === target.seed_packet_id)?.variety_name || 'seed packet';
      return 'target';
    }

    function isAssigned(img) { return !!(img.plant_id || img.seed_packet_id); }

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
      const assigned = images.filter(isAssigned).length;
      $('#match-counter').textContent = `${index + 1} / ${images.length} · ${assigned} assigned in this view`;
      progress.textContent = images.length === 1000 ? 'Showing first 1000 photos' : '';

      targetSel.value = targetValue(img);
      updateBulkButton();
    }

    function sameDay(a, b) {
      if (!a || !b) return false;
      return String(a).slice(0, 10) === String(b).slice(0, 10);
    }

    function dayMates() {
      const img = images[index];
      if (!img || !img.taken_at) return [];
      return images.filter((i) => !isAssigned(i) && sameDay(i.taken_at, img.taken_at));
    }

    function updateBulkButton() {
      const btn = $('#match-bulk');
      const mates = dayMates();
      const hint = $('#match-bulk-hint');
      if (mates.length > 1) {
        btn.disabled = false;
        btn.textContent = `Assign all ${mates.length} from ${fmtDate(images[index].taken_at)}`;
        hint.textContent = 'Photos taken on the same day are usually from the same session.';
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
      const target = selectedTarget();
      if (!img || (!target.plant_id && !target.seed_packet_id)) {
        toast('Choose a plant or seed packet first.', 'err');
        return;
      }
      try {
        const updated = await api.patch(`/api/album-images/${img.id}`, target);
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
        const updated = await api.patch(`/api/album-images/${img.id}`, { plant_id: null, seed_packet_id: null });
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
      const target = selectedTarget();
      if (mates.length < 2 || (!target.plant_id && !target.seed_packet_id)) {
        toast('Choose a plant or seed packet first.', 'err');
        return;
      }
      const name = targetName(target);
      try {
        const result = await api.post('/api/album-images/bulk-assign', {
          image_ids: mates.map((m) => m.id),
          ...target,
        });
        const ids = new Set(mates.map((m) => m.id));
        if (unassignedOnly.checked) {
          images = images.filter((i) => !ids.has(i.id));
          if (index >= images.length) index = Math.max(0, images.length - 1);
        } else {
          const varietyPatch = target.plant_id ? { plant_variety: name } : { packet_variety: name };
          images = images.map((i) => (ids.has(i.id) ? { ...i, ...target, ...varietyPatch } : i));
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
    targetSel.addEventListener('change', updateBulkButton);
    $('#match-prev').addEventListener('click', () => go(-1));
    $('#match-next').addEventListener('click', () => go(1));
    document.addEventListener('keydown', (event) => {
      if (!$('#match-workspace') || $('#match-workspace').classList.contains('hidden')) return;
      if (event.target.matches('input, select, textarea')) return;
      if (event.key === 'ArrowLeft') go(-1);
      else if (event.key === 'ArrowRight') go(1);
    });

    Promise.all([loadAlbums(), loadTargets()])
      .then(loadImages)
      .catch((error) => toast(`Could not load: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initMatch);
})();

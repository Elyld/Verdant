/* Backyard planner — grid-based container layout per season (1 cell = 1 ft).
 * Containers snap to the grid, have real footprints, and hold many plants. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  const KIND_ICON = { 'grow bag': '🛍️', 'raised bed': '🟫', 'pot': '🪴', 'planter': '🗄️' };
  const KIND_TONE = {
    'grow bag': 'bg-sage-100 ring-sage-300',
    'raised bed': 'bg-amber-100 ring-amber-300',
    'pot': 'bg-sky-100 ring-sky-300',
    'planter': 'bg-orange-100 ring-orange-300',
  };
  const FOOTPRINTS = { 'grow bag': [2, 2], 'raised bed': [4, 4], 'pot': [1, 1], 'planter': [3, 1] };

  function initPlanner() {
    const canvas = $('#planner-canvas');
    if (!canvas) return;

    let containers = [];
    let plantings = [];
    let plants = [];
    let locations = [];
    let years = [];
    let warnings = [];
    let year = new Date().getFullYear();
    let cols = 24, rows = 16;
    let editingId = null;
    let pendingPlantings = [];

    const plantById = (id) => plants.find((p) => p.id === id) || {};
    const plantingsFor = (cid) => plantings.filter((p) => p.container_id === cid);
    const warningsFor = (cid) => warnings.filter((w) => w.container_id === cid);

    function occupiedCells(ignoreId) {
      const occ = new Set();
      containers.forEach((c) => {
        if (c.id === ignoreId) return;
        for (let dx = 0; dx < (c.grid_w || 1); dx++) {
          for (let dy = 0; dy < (c.grid_h || 1); dy++) {
            occ.add(`${(c.grid_x || 0) + dx},${(c.grid_y || 0) + dy}`);
          }
        }
      });
      return occ;
    }

    function fits(gx, gy, w, h, ignoreId) {
      if (gx < 0 || gy < 0 || gx + w > cols || gy + h > rows) return false;
      const occ = occupiedCells(ignoreId);
      for (let dx = 0; dx < w; dx++) {
        for (let dy = 0; dy < h; dy++) {
          if (occ.has(`${gx + dx},${gy + dy}`)) return false;
        }
      }
      return true;
    }

    function card(c) {
      const el = document.createElement('button');
      el.type = 'button';
      const w = c.grid_w || 1, h = c.grid_h || 1;
      const small = w < 2 || h < 2;
      el.className = `relative flex flex-col items-center justify-center gap-0.5 overflow-hidden rounded-lg px-1 py-1 text-center shadow ring-2 ${KIND_TONE[c.kind] || KIND_TONE['grow bag']}`;
      el.style.gridColumn = `${(c.grid_x || 0) + 1} / span ${w}`;
      el.style.gridRow = `${(c.grid_y || 0) + 1} / span ${h}`;
      el.dataset.containerId = c.id;
      const ps = plantingsFor(c.id);
      const names = ps.slice(0, 3).map((p) => p.variety_name || '').filter(Boolean);
      const more = ps.length > 3 ? ` +${ps.length - 3} more` : '';
      const hasWarn = warningsFor(c.id).length > 0;
      el.innerHTML = `
        ${hasWarn ? '<span class="absolute right-1 top-1 text-sm" title="Rotation warning — same family grew here last season">⚠️</span>' : ''}
        <span class="${small ? 'text-lg' : 'text-2xl'} leading-none">${KIND_ICON[c.kind] || '🛍️'}</span>
        <span class="w-full truncate ${small ? 'text-[10px]' : 'text-xs'} font-semibold text-navy-800">${esc(c.name)}</span>
        ${!small ? `<span class="w-full truncate text-[10px] ${ps.length ? 'font-semibold text-sage-700' : 'text-navy-400'}">${ps.length ? esc(names.join(', ')) + more : 'empty'}</span>` : ''}`;
      el.addEventListener('pointerdown', (e) => startDrag(e, c, el));
      el.addEventListener('click', () => { if (!dragMoved) openModal(c); });
      return el;
    }

    let dragMoved = false;
    function startDrag(e, c, el) {
      e.preventDefault();
      dragMoved = false;
      const rect = canvas.getBoundingClientRect();
      const cellW = rect.width / cols, cellH = rect.height / rows;
      // Preserve where inside the card the pointer grabbed, in cells.
      const grabDX = Math.floor((e.clientX - rect.left) / cellW) - (c.grid_x || 0);
      const grabDY = Math.floor((e.clientY - rect.top) / cellH) - (c.grid_y || 0);
      const origX = c.grid_x || 0, origY = c.grid_y || 0;
      const w = c.grid_w || 1, h = c.grid_h || 1;
      el.setPointerCapture(e.pointerId);
      el.style.zIndex = '10';
      const move = (ev) => {
        let gx = Math.floor((ev.clientX - rect.left) / cellW) - grabDX;
        let gy = Math.floor((ev.clientY - rect.top) / cellH) - grabDY;
        gx = Math.max(0, Math.min(cols - w, gx));
        gy = Math.max(0, Math.min(rows - h, gy));
        if (gx !== c.grid_x || gy !== c.grid_y) dragMoved = true;
        c.grid_x = gx;
        c.grid_y = gy;
        el.style.gridColumn = `${gx + 1} / span ${w}`;
        el.style.gridRow = `${gy + 1} / span ${h}`;
      };
      const up = () => {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.removeEventListener('pointercancel', up);
        el.style.zIndex = '';
        if (dragMoved) {
          if (fits(c.grid_x, c.grid_y, w, h, c.id)) {
            api.patch(`/api/containers/${c.id}`, { grid_x: c.grid_x, grid_y: c.grid_y })
              .catch(() => toast('Could not save position.', 'error'));
          } else {
            c.grid_x = origX;
            c.grid_y = origY;
            render();
            toast('That spot is taken.', 'error');
          }
        }
        setTimeout(() => { dragMoved = false; }, 0);
      };
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
      el.addEventListener('pointercancel', up);
    }

    function render() {
      canvas.querySelectorAll('[data-container-id]').forEach((n) => n.remove());
      canvas.style.display = 'grid';
      canvas.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
      canvas.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
      canvas.style.aspectRatio = `${cols} / ${rows}`;
      canvas.style.backgroundImage = 'linear-gradient(to right, rgba(47,79,117,.10) 1px, transparent 1px), linear-gradient(to bottom, rgba(47,79,117,.10) 1px, transparent 1px)';
      canvas.style.backgroundSize = `calc(100% / ${cols}) calc(100% / ${rows})`;
      const empty = $('#planner-empty');
      empty.classList.toggle('hidden', containers.length > 0);
      empty.classList.toggle('flex', containers.length === 0);
      containers.forEach((c) => canvas.appendChild(card(c)));
    }

    function renderWarnings() {
      const banner = $('#rotation-banner');
      if (!warnings.length) {
        banner.classList.add('hidden');
        return;
      }
      $('#rotation-list').innerHTML = warnings.map((w) =>
        `<li><strong>${esc(w.container_name)}</strong>: ${esc(w.variety_name)} — ${esc(w.reason)}</li>`).join('');
      banner.classList.remove('hidden');
    }

    async function load() {
      const [cs, g, pl, p, l, ys, rw] = await Promise.all([
        api.get(`/api/containers/?year=${year}`).catch(() => []),
        api.get('/api/containers/grid').catch(() => ({ cols: 24, rows: 16 })),
        api.get(`/api/containers/plantings?year=${year}`).catch(() => []),
        api.get('/api/plants/').catch(() => []),
        api.get('/api/locations/').catch(() => []),
        api.get('/api/containers/years').catch(() => []),
        api.get(`/api/containers/rotation-warnings?year=${year}`).catch(() => []),
      ]);
      containers = Array.isArray(cs) ? cs : [];
      cols = g.cols || 24;
      rows = g.rows || 16;
      plantings = Array.isArray(pl) ? pl : [];
      plants = Array.isArray(p) ? p : [];
      locations = Array.isArray(l) ? l : [];
      years = Array.isArray(ys) ? ys : [];
      warnings = Array.isArray(rw) ? rw : [];
      if (!years.includes(year)) years.push(year);
      years.sort((a, b) => b - a);
      $('#planner-year').innerHTML = years.map((y) => `<option value="${y}"${y === year ? ' selected' : ''}>${y}</option>`).join('');
      $('#copy-from').innerHTML = years.filter((y) => y !== year).map((y) => `<option value="${y}">${y}</option>`).join('');
      $('#copy-to-label').textContent = year;
      $('#grid-cols').value = cols;
      $('#grid-rows').value = rows;
      $('#container-location').innerHTML = '<option value="">— none —</option>' +
        locations.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
      renderWarnings();
      render();
    }

    function renderPlantingList() {
      const ul = $('#container-plantings');
      const list = editingId ? plantingsFor(editingId) : pendingPlantings;
      ul.innerHTML = '';
      if (!list.length) {
        const li = document.createElement('li');
        li.className = 'text-xs text-navy-400';
        li.textContent = 'No plants yet.';
        ul.appendChild(li);
      }
      list.forEach((pl2) => {
        const li = document.createElement('li');
        li.className = 'flex items-center justify-between gap-2 rounded-lg bg-beige-100 px-2 py-1 text-sm';
        const name = pl2.variety_name || plantById(pl2.plant_id).variety_name || '';
        const label = document.createElement('span');
        label.className = 'truncate text-navy-800';
        label.textContent = name;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'shrink-0 text-xs text-red-700 underline';
        btn.textContent = 'remove';
        btn.addEventListener('click', async () => {
          if (pl2.id) {
            try {
              await api.del(`/api/containers/plantings/${pl2.id}`);
            } catch (err) {
              toast(err.message || 'Could not remove.', 'error');
              return;
            }
            plantings = plantings.filter((x) => x.id !== pl2.id);
          } else {
            pendingPlantings = pendingPlantings.filter((x) => x.plant_id !== pl2.plant_id);
          }
          renderPlantingList();
          render();
        });
        li.appendChild(label);
        li.appendChild(btn);
        ul.appendChild(li);
      });
      const added = new Set(list.map((x) => x.plant_id));
      $('#container-plant-add').innerHTML = '<option value="">— pick a plant —</option>' +
        plants.filter((x) => !added.has(x.id))
          .map((x) => `<option value="${x.id}">${esc(x.variety_name)}</option>`).join('');
    }

    function openModal(c) {
      editingId = c ? c.id : null;
      pendingPlantings = [];
      $('#container-modal-title').textContent = c ? 'Edit container' : 'Add container';
      $('#container-submit').textContent = c ? 'Save changes' : 'Add container';
      $('#container-delete').classList.toggle('hidden', !c);
      $('#container-id').value = c ? c.id : '';
      $('#container-name').value = c ? c.name : '';
      $('#container-kind').value = c ? c.kind : 'grow bag';
      const fp = FOOTPRINTS[c ? c.kind : 'grow bag'] || [2, 2];
      $('#container-grid-w').value = c && c.grid_w ? c.grid_w : fp[0];
      $('#container-grid-h').value = c && c.grid_h ? c.grid_h : fp[1];
      $('#container-size').value = c ? (c.size || '') : '';
      $('#container-volume-value').value = c && c.volume_value != null ? c.volume_value : '';
      $('#container-volume-unit').value = c ? (c.volume_unit || '') : '';
      $('#container-location').value = c && c.location_id ? c.location_id : '';
      $('#container-soil').value = c ? (c.soil_notes || '') : '';
      renderPlantingList();
      $('#container-modal').classList.remove('hidden');
      $('#container-modal').classList.add('flex');
      $('#container-name').focus();
    }

    function closeModal() {
      $('#container-modal').classList.add('hidden');
      $('#container-modal').classList.remove('flex');
    }

    $('#container-kind').addEventListener('change', (e) => {
      const fp = FOOTPRINTS[e.target.value] || [2, 2];
      $('#container-grid-w').value = fp[0];
      $('#container-grid-h').value = fp[1];
    });

    $('#container-plant-add-btn').addEventListener('click', async () => {
      const pid = Number($('#container-plant-add').value);
      if (!pid) return;
      if (editingId) {
        try {
          const np = await api.post('/api/containers/plantings', { container_id: editingId, plant_id: pid });
          plantings.push(np);
        } catch (err) {
          toast(err.message || 'Could not add plant.', 'error');
          return;
        }
      } else {
        if (pendingPlantings.some((x) => x.plant_id === pid)) {
          toast('Already in the list.', 'error');
          return;
        }
        pendingPlantings.push({ plant_id: pid });
      }
      renderPlantingList();
      render();
    });

    $('#planner-add').addEventListener('click', () => openModal(null));
    $('#container-close').addEventListener('click', closeModal);
    $('#container-cancel').addEventListener('click', closeModal);
    $('#planner-year').addEventListener('change', (e) => { year = Number(e.target.value); load(); });
    $('#rotation-dismiss').addEventListener('click', () => $('#rotation-banner').classList.add('hidden'));

    $('#grid-apply').addEventListener('click', async () => {
      const nc = Number($('#grid-cols').value), nr = Number($('#grid-rows').value);
      try {
        const g = await api.put('/api/containers/grid', { cols: nc, rows: nr });
        cols = g.cols;
        rows = g.rows;
        $('#grid-cols').value = cols;
        $('#grid-rows').value = rows;
        toast(`Grid is now ${cols}×${rows}.`);
        render();
      } catch (err) {
        toast(err.message || 'Could not resize grid.', 'error');
      }
    });

    $('#container-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('#container-id').value;
      const payload = {
        name: $('#container-name').value.trim(),
        kind: $('#container-kind').value,
        grid_w: Number($('#container-grid-w').value) || 2,
        grid_h: Number($('#container-grid-h').value) || 2,
        size: $('#container-size').value.trim(),
        volume_value: $('#container-volume-value').value ? Number($('#container-volume-value').value) : null,
        volume_unit: $('#container-volume-unit').value,
        location_id: $('#container-location').value ? Number($('#container-location').value) : null,
        soil_notes: $('#container-soil').value.trim(),
        season_year: year,
      };
      try {
        let cid = id ? Number(id) : null;
        if (cid) {
          await api.patch(`/api/containers/${cid}`, payload);
        } else {
          const created = await api.post('/api/containers/', payload);
          cid = created.id;
          for (const pp of pendingPlantings) {
            await api.post('/api/containers/plantings', { container_id: cid, plant_id: pp.plant_id });
          }
        }
        closeModal();
        toast(id ? 'Container updated.' : 'Container added — drag it where it really sits.');
        load();
      } catch (err) {
        toast(err.message || 'Could not save.', 'error');
      }
    });

    $('#container-delete').addEventListener('click', async () => {
      const id = $('#container-id').value;
      if (!id || !confirm('Remove this container from the plan?')) return;
      try {
        await api.del(`/api/containers/${id}`);
        closeModal();
        toast('Removed.');
        load();
      } catch (err) {
        toast(err.message || 'Could not delete.', 'error');
      }
    });

    $('#planner-copy').addEventListener('click', () => {
      if (!years.filter((y) => y !== year).length) { toast('No other season to copy from yet.', 'error'); return; }
      $('#copy-modal').classList.remove('hidden');
      $('#copy-modal').classList.add('flex');
    });
    $('#copy-cancel').addEventListener('click', () => {
      $('#copy-modal').classList.add('hidden');
      $('#copy-modal').classList.remove('flex');
    });
    $('#copy-go').addEventListener('click', async () => {
      try {
        await api.post('/api/containers/copy-season', { from_year: Number($('#copy-from').value), to_year: year });
        $('#copy-modal').classList.add('hidden');
        $('#copy-modal').classList.remove('flex');
        toast(`Copied into ${year}.`);
        load();
      } catch (err) {
        toast(err.message || 'Could not copy season.', 'error');
      }
    });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPlanner);
  } else {
    initPlanner();
  }
})();

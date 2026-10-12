/* Backyard planner — grid-based container layout per season (1 cell = 1 ft).
 * Containers snap to the grid, have real footprints, and hold many plants. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  const KIND_ICON = { 'grow bag': '🛍️', 'raised bed': '🟫', 'pot': '🪴', 'planter': '🗄️', 'arch': '🌉', 'pallet': '🪵' };
  const KIND_TONE = {
    'grow bag': 'bg-sage-100 ring-sage-300',
    'raised bed': 'bg-amber-100 ring-amber-300',
    'pot': 'bg-sky-100 ring-sky-300',
    'planter': 'bg-orange-100 ring-orange-300',
    'arch': 'bg-navy-100 ring-navy-300',
    'pallet': 'bg-beige-200 ring-beige-400',
  };
  const FOOTPRINTS = { 'grow bag': [2, 2], 'raised bed': [4, 4], 'pot': [1, 1], 'planter': [3, 1], 'arch': [4, 4], 'pallet': [4, 3] };
  const KIND_HEIGHT = { 'arch': 7 }; // default height in feet, used by the 3D view

  function initPlanner() {
    const canvas = $('#planner-canvas');
    if (!canvas) return;

    let containers = [];
    let plantings = [];
    let plants = [];
    let locations = [];
    let years = [];
    let warnings = [];
    let year = globalThis.Verdant.year(); // header Season picker is the source of truth
    let cols = 24, rows = 16;
    let editingId = null;
    let pendingPlantings = [];
    let wxAlerts = [];
    let companions = [];
    let heatOn = false;
    let heatTotals = {};
    let heatMax = 0;
    let heatYear = null;

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
      const heatOz = heatOn ? heatTotals[c.name] : null;
      const heatT = heatOz != null && heatMax > 0 ? Math.min(1, heatOz / heatMax) : 0;
      if (heatT > 0) el.style.backgroundColor = `rgba(217, 119, 6, ${0.12 + 0.55 * heatT})`;
      el.innerHTML = `
        ${hasWarn ? '<span class="absolute right-1 top-1 text-sm" title="Rotation warning — same family grew here last season">⚠️</span>' : ''}
        <span class="${small ? 'text-lg' : 'text-2xl'} leading-none">${KIND_ICON[c.kind] || '🛍️'}</span>
        <span class="w-full truncate ${small ? 'text-[10px]' : 'text-xs'} font-semibold text-navy-800">${esc(c.name)}</span>
        ${!small ? `<span class="w-full truncate text-[10px] ${ps.length ? 'font-semibold text-sage-700' : 'text-navy-400'}">${heatT > 0 ? `⚖️ ${heatOz} oz` : (ps.length ? esc(names.join(', ')) + more : 'empty')}</span>` : ''}`;
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
      canvas.style.display = view === '3d' ? 'none' : 'grid';
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
      const [cs, g, pl, p, l, ys, rw, al, cp, sc] = await Promise.all([
        api.get(`/api/containers/?year=${year}`).catch(() => []),
        api.get('/api/containers/grid').catch(() => ({ cols: 24, rows: 16 })),
        api.get(`/api/containers/plantings?year=${year}`).catch(() => []),
        api.get('/api/plants/').catch(() => []),
        api.get('/api/locations/').catch(() => []),
        api.get('/api/containers/years').catch(() => []),
        api.get(`/api/containers/rotation-warnings?year=${year}`).catch(() => []),
        api.get('/api/weather/alerts').catch(() => ({ ok: false, alerts: [] })),
        api.get('/static/data/companions.json').catch(() => []),
        api.get(`/api/succession/suggestions?year=${year}`).catch(() => null),
      ]);
      containers = Array.isArray(cs) ? cs : [];
      cols = g.cols || 24;
      rows = g.rows || 16;
      plantings = Array.isArray(pl) ? pl : [];
      plants = Array.isArray(p) ? p : [];
      locations = Array.isArray(l) ? l : [];
      years = Array.isArray(ys) ? ys : [];
      warnings = Array.isArray(rw) ? rw : [];
      wxAlerts = al && al.ok && Array.isArray(al.alerts) ? al.alerts : [];
      companions = Array.isArray(cp) ? cp : [];
      if (!years.includes(year)) years.push(year);
      years.sort((a, b) => b - a);
      heatYear = years.find((y) => y < year) ?? null;
      if (heatOn) {
        // Season changed while the heatmap is on — retotal for the new past season.
        try {
          const res = heatYear == null ? null : await api.get(`/api/containers/yield-map?year=${heatYear}`);
          heatTotals = (res && res.totals) || {};
          const vals = Object.values(heatTotals);
          heatMax = vals.length ? Math.max(...vals) : 0;
          $('#heatmap-legend').textContent = heatYear == null ? '' :
            `🔥 Yield heatmap — ${heatYear} harvest weight per container (darker = heavier).`;
        } catch { heatTotals = {}; heatMax = 0; }
      }
      $('#planner-year').innerHTML = years.map((y) => `<option value="${y}"${y === year ? ' selected' : ''}>${y}</option>`).join('');
      $('#copy-from').innerHTML = years.filter((y) => y !== year).map((y) => `<option value="${y}">${y}</option>`).join('');
      $('#copy-to-label').textContent = year;
      $('#grid-cols').value = cols;
      $('#grid-rows').value = rows;
      $('#container-location').innerHTML = '<option value="">— none —</option>' +
        locations.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
      renderWarnings();
      renderWxAlerts();
      renderSuccession(sc);
      render();
      if (view === '3d' && T) buildScene3D();
    }

    const ALERT_TONE = {
      info: 'bg-sky-50 ring-sky-300 text-sky-900',
      warn: 'bg-amber-50 ring-amber-300 text-amber-900',
      critical: 'bg-red-50 ring-red-400 text-red-900',
    };

    function renderWxAlerts() {
      const box = $('#weather-alerts');
      if (!wxAlerts.length) {
        box.innerHTML = '';
        return;
      }
      box.innerHTML = wxAlerts.map((a) =>
        `<div class="rounded-xl px-4 py-2.5 text-sm ring-1 ${ALERT_TONE[a.level] || ALERT_TONE.info}">` +
        `<p class="font-semibold">${esc(a.icon || '')} ${esc(a.title || '')}</p>` +
        (a.detail ? `<p class="mt-0.5">${esc(a.detail)}</p>` : '') +
        `</div>`).join('');
    }

    function renderSuccession(sc) {
      const panel = $('#succession-panel');
      if (!sc || !sc.ok || !sc.containers || !sc.containers.length) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
        return;
      }
      const frostBit = sc.first_frost
        ? ` · first frost ~${esc(sc.first_frost)} (${sc.days_left}d left)`
        : '';
      panel.innerHTML =
        `<div class="rounded-2xl bg-navy-900/70 p-4 ring-1 ring-navy-600/60">` +
        `<p class="font-display text-lg font-semibold text-beige-50">🔄 Succession ideas${frostBit}</p>` +
        `<p class="mt-0.5 text-sm text-sage-200/80">Empty right now — these still beat the frost, rotation-aware.</p>` +
        `<div class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">` +
        sc.containers.map((c) => {
          const body = c.suggestions.length
            ? `<ul class="mt-1.5 space-y-1 text-sm">` + c.suggestions.map((s) =>
              `<li class="flex items-baseline justify-between gap-2">` +
              `<span class="text-beige-50">${esc(s.name)}</span>` +
              `<span class="shrink-0 text-xs text-sage-200/80">sow by ${esc(s.sow_by)} · ${s.days_to_maturity}d</span></li>`).join('') + `</ul>`
            : `<p class="mt-1.5 text-sm text-sage-200/80">${esc(c.note || 'Nothing fits this window.')}</p>`;
          return `<div class="rounded-xl bg-navy-800/60 p-3 ring-1 ring-navy-600/50">` +
            `<p class="text-sm font-semibold text-beige-50">${esc(c.container_name)} <span class="font-normal text-sage-200/70">· ${esc(c.kind || 'container')}</span></p>` +
            body + `</div>`;
        }).join('') + `</div></div>`;
      panel.classList.remove('hidden');
    }

    async function toggleHeatmap() {
      heatOn = !heatOn;
      $('#heatmap-toggle').classList.toggle('bg-sage-200', heatOn);
      const legend = $('#heatmap-legend');
      if (heatOn) {
        if (heatYear == null) {
          toast('No past season to compare yet.', 'info');
          heatOn = false;
          $('#heatmap-toggle').classList.remove('bg-sage-200');
          return;
        }
        try {
          const res = await api.get(`/api/containers/yield-map?year=${heatYear}`);
          heatTotals = (res && res.totals) || {};
        } catch (err) {
          toast(err.message || 'Could not load yield data.', 'error');
          heatOn = false;
          $('#heatmap-toggle').classList.remove('bg-sage-200');
          return;
        }
        const vals = Object.values(heatTotals);
        heatMax = vals.length ? Math.max(...vals) : 0;
        legend.textContent = `🔥 Yield heatmap — ${heatYear} harvest weight per container (darker = heavier).`;
        legend.classList.remove('hidden');
      } else {
        legend.classList.add('hidden');
      }
      render();
    }

    // Common-name → scientific-name aliases so "tomato" matches Solanum lycopersicum.
    const PLANT_ALIASES = {
      tomato: ['tomato', 'solanum lycopersicum'],
      pepper: ['pepper', 'capsicum', 'chili', 'chile'],
      bean: ['bean', 'phaseolus'],
      corn: ['corn', 'zea mays'],
      cucumber: ['cucumber', 'cucumis sativus'],
      squash: ['squash', 'cucurbita', 'zucchini'],
      onion: ['onion', 'allium cepa'],
      garlic: ['garlic', 'allium sativum'],
      basil: ['basil', 'ocimum'],
      marigold: ['marigold', 'tagetes'],
      carrot: ['carrot', 'daucus carota'],
      lettuce: ['lettuce', 'lactuca'],
      cabbage: ['cabbage', 'brassica oleracea'],
      potato: ['potato', 'solanum tuberosum'],
      fennel: ['fennel', 'foeniculum'],
      melon: ['melon', 'citrullus', 'cucumis melo'],
      eggplant: ['eggplant', 'solanum melongena'],
    };
    const matchesKeyword = (text, key) => {
      const keys = PLANT_ALIASES[key] || [key];
      return keys.some((k) => text.includes(k));
    };

    function companionHintsFor(list) {
      const texts = list.map((pl2) => {
        const full = plantById(pl2.plant_id);
        return [pl2.variety_name || full.variety_name, pl2.species_type || full.species_type,
          pl2.family_genus || full.family_genus].filter(Boolean).join(' ').toLowerCase();
      });
      const seen = new Set();
      const out = [];
      companions.forEach((cp) => {
        const a = String(cp.a || '').toLowerCase();
        const b = String(cp.b || '').toLowerCase();
        if (!a || !b) return;
        for (let i = 0; i < texts.length; i++) {
          for (let j = i + 1; j < texts.length; j++) {
            const hit = (matchesKeyword(texts[i], a) && matchesKeyword(texts[j], b)) ||
              (matchesKeyword(texts[i], b) && matchesKeyword(texts[j], a));
            if (hit && !seen.has(`${a}|${b}`)) {
              seen.add(`${a}|${b}`);
              out.push(cp);
            }
          }
        }
      });
      return out;
    }

    function renderCompanionHints(list) {
      const box = $('#companion-hints');
      const hints = companionHintsFor(list);
      if (!hints.length) {
        box.innerHTML = '';
        return;
      }
      box.innerHTML = hints.map((h) => {
        const good = h.relation === 'good';
        return `<p class="text-xs ${good ? 'text-sage-700' : 'text-amber-800'}">` +
          `${good ? '🌱' : '⚠️'} <strong>${esc(h.a)} × ${esc(h.b)}</strong> — ${esc(h.note || '')}` +
          (h.source ? ` <span class="text-navy-400">(${esc(h.source)})</span>` : '') + `</p>`;
      }).join('');
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
      renderCompanionHints(list);
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
      $('#container-height').value = c && c.height_ft != null ? c.height_ft : (KIND_HEIGHT[c ? c.kind : 'grow bag'] || '');
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
      $('#container-height').value = KIND_HEIGHT[e.target.value] || '';
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
    $('#heatmap-toggle').addEventListener('click', toggleHeatmap);
    $('#container-close').addEventListener('click', closeModal);
    $('#container-cancel').addEventListener('click', closeModal);
    $('#planner-year').addEventListener('change', (e) => { globalThis.Verdant.setYear(Number(e.target.value)); });
    document.addEventListener('verdant:year', (e) => { year = Number(e.detail.year); load(); });
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
        if (view === '3d' && T) buildScene3D();
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
        height_ft: $('#container-height').value ? Number($('#container-height').value) : null,
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

    /* ---------------- 3D view (Three.js, lazy-loaded) ---------------- */
    /* Minecraft voxel edition: 16x16 pixel textures (NearestFilter), blocky
       containers, cross-quad pixel plants, blocky clouds, first-person walk. */
    let view = '2d';
    let T = null; // { THREE, renderer, scene, camera, controls, sun, group }
    let threeFailed = false;
    let walkMode = false;

    const view2dBtn = $('#view-2d');
    const view3dBtn = $('#view-3d');
    const viewWalkBtn = $('#view-walk');
    const wrap3d = $('#planner-3d');
    const hint2d = $('#planner-2d-hint');
    const hint3d = $('#planner-3d-hint');
    const orbitHintText = 'Drag to orbit · scroll or pinch to zoom · right-drag to pan · click a container to edit it.';
    const walkHintText = 'Click to grab the mouse · WASD walk · Shift sprint · Left-click break · Right-click place · E edit · Q blocks/plants · 1-7/wheel pick · ESC release.';

    // crosshair shown in walk mode
    const crosshair = document.createElement('div');
    crosshair.style.cssText = 'position:absolute;left:50%;top:50%;width:8px;height:8px;margin:-4px 0 0 -4px;' +
      'border-radius:50%;background:rgba(255,255,255,.92);box-shadow:0 0 0 2px rgba(20,35,55,.5);' +
      'display:none;pointer-events:none;z-index:5;';
    wrap3d.appendChild(crosshair);

    function loadScript(src) {
      return new Promise((resolve, reject) => {
        let settled = false;
        const done = (ok, err) => { if (!settled) { settled = true; ok ? resolve() : reject(err || new Error('script load failed')); } };
        try {
          const head = document.head || (document.getElementsByTagName && document.getElementsByTagName('head')[0]);
          if (!head) return done(false, new Error('no document head'));
          if (document.querySelector(`script[src="${src}"]`)) return done(true);
          const s = document.createElement('script');
          s.src = src;
          s.onload = () => done(true);
          s.onerror = () => done(false);
          head.appendChild(s);
          setTimeout(() => done(false, new Error('script load timeout')), 20000);
        } catch (err) { done(false, err); }
      });
    }

    // Seeded PRNG so plant/vine placement is stable across rebuilds.
    function mulberry32(seed) {
      let a = seed >>> 0;
      return function () {
        a |= 0; a = (a + 0x6D2B79F5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }

    /* ---------- pixel-art helpers ---------- */
    function px(ctx, x, y, w, h, c) {
      ctx.fillStyle = c;
      ctx.fillRect(x | 0, y | 0, Math.ceil(w), Math.ceil(h));
    }

    function noiseFill(ctx, S, rng, palette) {
      for (let y = 0; y < S; y++) {
        for (let x = 0; x < S; x++) {
          px(ctx, x, y, 1, 1, palette[(rng() * palette.length) | 0]);
        }
      }
    }

    // 16x16 painters. Each takes (ctx, S, rng). Transparent pixels simply
    // aren't painted (canvas starts clear).
    function paintGrassTop(ctx, S, rng) {
      noiseFill(ctx, S, rng, ['#6fbf5a', '#6fbf5a', '#65b551', '#7acc66', '#5da84b']);
      // 1px darker seam = the 1-ft grid lines between blocks
      px(ctx, 0, 0, S, 1, '#4f9440'); px(ctx, 0, S - 1, S, 1, '#4f9440');
      px(ctx, 0, 0, 1, S, '#4f9440'); px(ctx, S - 1, 0, 1, S, '#4f9440');
    }

    function paintDirtSide(ctx, S, rng) {
      noiseFill(ctx, S, rng, ['#8a5f3c', '#7d5535', '#96684a', '#755031']);
      // green fringe along the top edge, ragged
      for (let x = 0; x < S; x++) {
        const d = 2 + ((rng() * 3) | 0);
        for (let y = 0; y < d; y++) px(ctx, x, y, 1, 1, y === d - 1 && rng() < 0.5 ? '#5da84b' : '#6fbf5a');
      }
    }

    function paintDirt(ctx, S, rng) {
      noiseFill(ctx, S, rng, ['#8a5f3c', '#7d5535', '#96684a', '#755031', '#6e4a2e']);
    }

    function paintWoodPlanks(ctx, S, rng) {
      px(ctx, 0, 0, S, S, '#a0824f');
      for (let y = 0; y < S; y += 4) px(ctx, 0, y, S, 1, '#6e5636'); // plank seams
      for (let i = 0; i < 26; i++) px(ctx, (rng() * S) | 0, (rng() * S) | 0, 1 + ((rng() * 2) | 0), 1, rng() < 0.5 ? '#8f7040' : '#b08d58');
      if (rng() < 0.7) { // knot
        const kx = 2 + ((rng() * (S - 4)) | 0), ky = 2 + ((rng() * (S - 4)) | 0);
        px(ctx, kx, ky, 2, 2, '#5e482c');
      }
    }

    function paintDarkWood(ctx, S, rng) {
      noiseFill(ctx, S, rng, ['#6e5636', '#654e2f', '#78593a']);
    }

    function paintSoil(ctx, S, rng) {
      noiseFill(ctx, S, rng, ['#4a3520', '#42301c', '#54402a', '#3a2a18']);
      for (let i = 0; i < 5; i++) px(ctx, (rng() * (S - 1)) | 0, (rng() * (S - 1)) | 0, 2, 1, '#6b5a3a'); // tiny stones
    }

    function paintFabric(ctx, S, rng) {
      for (let y = 0; y < S; y++) {
        for (let x = 0; x < S; x++) {
          px(ctx, x, y, 1, 1, ((x + y) % 2 === 0) ? '#3a3f44' : '#2f3338');
        }
      }
      for (let i = 0; i < 12; i++) px(ctx, (rng() * S) | 0, (rng() * S) | 0, 1, 1, '#4a5058');
    }

    function paintTerracotta(ctx, S, rng) {
      px(ctx, 0, 0, S, S, '#c1663e');
      px(ctx, 0, 0, S, 3, '#a0522d'); // rim band
      px(ctx, 0, 3, S, 1, '#8f4726');
      for (let i = 0; i < 18; i++) px(ctx, (rng() * S) | 0, 4 + ((rng() * (S - 4)) | 0), 1, 1, rng() < 0.5 ? '#d4764c' : '#b25a36');
    }

    function paintLeafBlob(ctx, S, rng) {
      const greens = ['#3f8f37', '#4e9e3f', '#5cb85c', '#357a2e'];
      for (let y = 2; y < S - 2; y++) {
        for (let x = 2; x < S - 2; x++) {
          const dx = (x - S / 2) / (S / 2), dy = (y - S / 2) / (S / 2);
          if (dx * dx + dy * dy < 0.75 && rng() < 0.92) px(ctx, x, y, 1, 1, greens[(rng() * greens.length) | 0]);
        }
      }
    }

    // Pixel-sprite maps: one char per pixel, '.' = transparent.
    const SPR_PALETTE = {
      s: '#6e4f2e', g: '#3f8f37', G: '#5cb85c', r: '#d9402e', R: '#a82c1f',
      o: '#e08a2e', y: '#f2d13d', p: '#e06ba8', w: '#fdfdfd',
    };
    const SPRITES = {
      tomato: [
        '................',
        '.......gg.......',
        '......gggg......',
        '.......gg.......',
        '.......ss.......',
        '.....ggssgg.....',
        '....gggssggg....',
        '.....gsssgg.....',
        '....ggssrrgg....',
        '.....gssRRg.....',
        '....gggssggg....',
        '.....gggssg.....',
        '....ggrrsgg.....',
        '.....grrRg......',
        '......ggg.......',
        '.......s........',
      ],
      pepper: [
        '................',
        '.....gggg.......',
        '....gggggg......',
        '...gggggggg.....',
        '...gggggggg.....',
        '....gggggg......',
        '.....gggg.......',
        '....gggggg......',
        '...gggooogg.....',
        '...gggooogg.....',
        '....ggoooog.....',
        '.....gooo.......',
        '......gg........',
        '......gg........',
        '................',
        '................',
      ],
      leafy: [
        '................',
        '................',
        '.....GGGG.......',
        '....GGGGGG......',
        '...GGgGGgGG.....',
        '...GgGGGGgG.....',
        '....GGGGGG......',
        '...GGGGGGGG.....',
        '....gGGGGg......',
        '.....GGGG.......',
        '......gg........',
        '................',
        '................',
        '................',
        '................',
        '................',
      ],
      vine: [
        '................',
        'gg..............',
        '.ggg............',
        '..gggg..........',
        '...ggggg........',
        '....gggygg......',
        '.....gggyy......',
        '......ggg.......',
        '.......ggg......',
        '........ggg.....',
        '.........gggy...',
        '..........ggy...',
        '...........gg...',
        '............g...',
        '................',
        '................',
      ],
      flower: [
        '................',
        '......pppp......',
        '.....pppppp.....',
        '.....pyyypp.....',
        '.....pppppp.....',
        '......pppp......',
        '.......ss.......',
        '....g..ss.......',
        '.....g.ss.......',
        '......ssg.......',
        '......ss........',
        '......ss........',
        '................',
        '................',
        '................',
        '................',
      ],
      generic: [
        '................',
        '................',
        '................',
        '................',
        '......gg........',
        '.....gggg.......',
        '......gg........',
        '.......ss.......',
        '...g...ss.......',
        '....g..ss..g....',
        '.....g.ss.g.....',
        '.......ss.......',
        '.......ss.......',
        '................',
        '................',
        '................',
      ],
    };

    function paintSprite(ctx, name) {
      const map = SPRITES[name] || SPRITES.generic;
      for (let y = 0; y < map.length; y++) {
        const row = map[y];
        for (let x = 0; x < row.length; x++) {
          const c = SPR_PALETTE[row[x]];
          if (c) px(ctx, x, y, 1, 1, c);
        }
      }
    }

    function plantArchetype(species) {
      const s = (species || '').toLowerCase();
      if (/tomato/.test(s)) return 'tomato';
      if (/pepper|chili|chile|paprika/.test(s)) return 'pepper';
      if (/basil|lettuce|spinach|kale|arugula|chard|herb|mint|cilantro|parsley|dill/.test(s)) return 'leafy';
      if (/cucumber|cuke|melon|squash|pumpkin|zucchini|bean|pea/.test(s)) return 'vine';
      if (/flower|marigold|zinnia|sunflower|dahlia|cosmos/.test(s)) return 'flower';
      return 'generic';
    }

    function makePixTexture(THREE, size, painter, seed, repeat) {
      const cv = document.createElement('canvas');
      cv.width = cv.height = size;
      const ctx = cv.getContext('2d');
      painter(ctx, size, mulberry32(seed || 1));
      const tex = new THREE.CanvasTexture(cv);
      tex.magFilter = THREE.NearestFilter;
      tex.minFilter = THREE.NearestMipmapLinearFilter;
      tex.generateMipmaps = true;
      tex.encoding = THREE.sRGBEncoding;
      if (repeat) {
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(repeat[0], repeat[1]);
      }
      return tex;
    }

    function pixMaterial(THREE, tex, opts) {
      return new THREE.MeshStandardMaterial(Object.assign({ map: tex, roughness: 1, metalness: 0 }, opts || {}));
    }

    async function ensureThree() {
      if (T) return T;
      if (threeFailed) throw new Error('3d unavailable');
      const CDN = 'https://cdn.jsdelivr.net/npm/three@0.147.0';
      await loadScript(`${CDN}/build/three.min.js`);
      await loadScript(`${CDN}/examples/js/controls/OrbitControls.js`);
      const THREE = globalThis.THREE;
      if (!THREE || !THREE.OrbitControls) throw new Error('3d unavailable');

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min((typeof window !== 'undefined' && window.devicePixelRatio) || 1, 2));
      renderer.outputEncoding = THREE.sRGBEncoding;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      wrap3d.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const SKY = 0x77a4ff; // minecraft-ish sky blue
      scene.background = new THREE.Color(SKY);
      scene.fog = new THREE.Fog(SKY, 80, 200);

      const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 600);
      const controls = new THREE.OrbitControls(camera, renderer.domElement);
      // On-demand rendering (no rAF loop): kinder to phone batteries, and every
      // interaction fires a 'change' event that re-renders the scene.
      // (Walk mode runs its own loop while the pointer is locked.)
      controls.enableDamping = false;
      controls.maxPolarAngle = Math.PI / 2 - 0.03;
      controls.minDistance = 4;
      controls.maxDistance = 130;
      controls.addEventListener('change', () => render3D());

      scene.add(new THREE.HemisphereLight(0xbdd8ff, 0x8a9a6a, 0.85));
      const sun = new THREE.DirectionalLight(0xfff3d6, 0.95);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.camera.near = 1;
      sun.shadow.camera.far = 140;
      scene.add(sun);

      // click (not drag) a container to edit it — skipped in walk mode,
      // which raycasts from the crosshair instead.
      const ray = new THREE.Raycaster();
      const ptr = new THREE.Vector2();
      let downX = 0, downY = 0;
      const openFromHit = (h) => {
        let o = h.object;
        while (o && (o.userData.containerId === undefined || o.userData.containerId === null)) o = o.parent;
        if (o) {
          const c = containers.find((x) => x.id === o.userData.containerId);
          if (c) { openModal(c); return true; }
        }
        return false;
      };
      renderer.domElement.addEventListener('pointerdown', (e) => { downX = e.clientX; downY = e.clientY; });
      renderer.domElement.addEventListener('pointerup', (e) => {
        if (walkMode) return;
        if (Math.hypot(e.clientX - downX, e.clientY - downY) > 6) return;
        const r = renderer.domElement.getBoundingClientRect();
        if (!r.width) return;
        ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
        ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
        ray.setFromCamera(ptr, camera);
        const hits = T.group ? ray.intersectObjects(T.group.children, true) : [];
        for (const h of hits) { if (openFromHit(h)) break; }
      });
      // walk-mode clicks (pointer locked): raycast from screen center.
      // Left = break, right = place (build mode). E edits the aimed container.
      renderer.domElement.addEventListener('click', () => {
        if (walkMode && walk && !walk.locked) { try { walk.plc.lock(); } catch (err) { /* noop */ } }
      });
      renderer.domElement.addEventListener('mousedown', (e) => {
        if (!(walkMode && walk && walk.locked)) return;
        if (e.button === 0) breakAim();
        else if (e.button === 2) placeAim();
      });

      T = { THREE, renderer, scene, camera, controls, sun, group: null, TEX: null };
      wrap3d._three = T; // handle for tests / debugging
      sizeThree();
      return T;
    }

    function sizeThree() {
      if (!T) return;
      const w = wrap3d.clientWidth || 800;
      const h = Math.max(420, Math.round(w * rows / cols));
      T.renderer.setSize(w, h);
      T.camera.aspect = w / h;
      T.camera.updateProjectionMatrix();
      render3D();
    }

    function disposeGroup(gr) {
      gr.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) {
          (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => {
            if (m.map) m.map.dispose();
            m.dispose();
          });
        }
      });
    }

    // Build (and cache on T) the shared pixel textures for one scene build.
    function buildTextures(THREE) {
      const TEX = {};
      TEX.grass = makePixTexture(THREE, 16, paintGrassTop, 11, [cols + 8, rows + 8]);
      TEX.dirtSideX = makePixTexture(THREE, 16, paintDirtSide, 12, [rows + 8, 1]);
      TEX.dirtSideZ = makePixTexture(THREE, 16, paintDirtSide, 13, [cols + 8, 1]);
      TEX.dirt = makePixTexture(THREE, 16, paintDirt, 14);
      TEX.wood = makePixTexture(THREE, 16, paintWoodPlanks, 15);
      TEX.darkWood = makePixTexture(THREE, 16, paintDarkWood, 16);
      TEX.soil = makePixTexture(THREE, 16, paintSoil, 17);
      TEX.fabric = makePixTexture(THREE, 16, paintFabric, 18);
      TEX.terracotta = makePixTexture(THREE, 16, paintTerracotta, 19);
      TEX.leafBlob = makePixTexture(THREE, 16, paintLeafBlob, 20);
      TEX.plants = {};
      Object.keys(SPRITES).forEach((name) => {
        TEX.plants[name] = makePixTexture(THREE, 16, (ctx) => paintSprite(ctx, name), 21);
      });
      return TEX;
    }

    function box(THREE, w, h, d, mat) {
      return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    }

    function buildVessel(THREE, g, w, h, kind, TEX) {
      let bodyH;
      if (kind === 'raised bed') bodyH = 1.1;
      else if (kind === 'planter') bodyH = 0.8;
      else if (kind === 'pot') bodyH = 1.0;
      else bodyH = 1.1; // grow bag
      const woodMat = pixMaterial(THREE, TEX.wood);
      const darkWoodMat = pixMaterial(THREE, TEX.darkWood);
      const soilMat = pixMaterial(THREE, TEX.soil);
      if (kind === 'pot') {
        // terracotta block pot
        const s = Math.max(0.6, Math.min(w, h) * 0.7);
        const body = box(THREE, s, bodyH, s, pixMaterial(THREE, TEX.terracotta));
        body.position.y = bodyH / 2;
        g.add(body);
        const soil = box(THREE, s - 0.18, 0.1, s - 0.18, soilMat);
        soil.position.y = bodyH - 0.04;
        soil.receiveShadow = true;
        g.add(soil);
      } else if (kind === 'grow bag') {
        const body = box(THREE, w * 0.94, bodyH, h * 0.94, pixMaterial(THREE, TEX.fabric));
        body.position.y = bodyH / 2;
        g.add(body);
        const soil = box(THREE, w * 0.94 - 0.18, 0.1, h * 0.94 - 0.18, soilMat);
        soil.position.y = bodyH - 0.04;
        soil.receiveShadow = true;
        g.add(soil);
      } else {
        // wooden box + rim boards + soil inset
        const bw = w * 0.98, bd = h * 0.98;
        const body = box(THREE, bw, bodyH, bd, woodMat);
        body.position.y = bodyH / 2;
        g.add(body);
        const rimH = 0.12, rimT = 0.16;
        [[0, 1, bw + 0.1, rimT], [0, -1, bw + 0.1, rimT]].forEach(([x, s, rw, rd]) => {
          const rim = box(THREE, rw, rimH, rd, darkWoodMat);
          rim.position.set(x, bodyH - rimH / 2 + 0.02, s * (bd / 2 - rimT / 2 + 0.04));
          g.add(rim);
        });
        [[1, 0], [-1, 0]].forEach(([s]) => {
          const rim = box(THREE, rimT, rimH, bd + 0.1, darkWoodMat);
          rim.position.set(s * (bw / 2 - rimT / 2 + 0.04), bodyH - rimH / 2 + 0.02, 0);
          g.add(rim);
        });
        const soil = box(THREE, bw - 0.24, 0.1, bd - 0.24, soilMat);
        soil.position.y = bodyH - 0.05;
        soil.receiveShadow = true;
        g.add(soil);
      }
      g.userData.topY = bodyH;
    }

    function buildPallet(THREE, g, w, h, TEX) {
      const woodMat = pixMaterial(THREE, TEX.wood);
      const darkWoodMat = pixMaterial(THREE, TEX.darkWood);
      for (let i = 0; i < 3; i++) {
        const s = box(THREE, w * 0.98, 0.28, 0.3, darkWoodMat);
        s.position.set(0, 0.14, -h / 2 + 0.35 + i * ((h - 0.7) / 2));
        g.add(s);
      }
      const n = Math.max(3, Math.round(h / 0.7));
      for (let i = 0; i < n; i++) {
        const slat = box(THREE, w * 0.98, 0.12, Math.max(0.28, (h * 0.98 / n) * 0.7), woodMat);
        slat.position.set(0, 0.34, -h * 0.49 + (i + 0.5) * (h * 0.98 / n));
        g.add(slat);
      }
      g.userData.topY = 0.42;
    }

    function buildArch(THREE, g, w, h, height, TEX) {
      // voxel trellis: chunky posts + crossbars + climbing vine blobs
      const span = Math.min(w, h);
      const len = Math.max(w, h);
      const a = Math.max(0.75, span / 2);
      const hh = Math.max(1.5, height || 4);
      const postMat = pixMaterial(THREE, TEX.darkWood);
      const off = a * 0.92, along = len / 2 - 0.35;
      const corners = w > h
        ? [[-along, -off], [-along, off], [along, -off], [along, off]]
        : [[-off, -along], [off, -along], [-off, along], [off, along]];
      const postGeo = new THREE.BoxGeometry(0.24, hh, 0.24);
      corners.forEach(([fx, fz]) => {
        const f = new THREE.Mesh(postGeo, postMat);
        f.position.set(fx, hh / 2, fz);
        g.add(f);
      });
      // crossbars across the span at three heights (span runs along X when
      // w<=h, along Z when w>h)
      [0.35, 0.65, 0.95].forEach((t) => {
        const bar = box(THREE, a * 2 + 0.24, 0.16, 0.16, postMat);
        bar.position.set(0, hh * t, 0);
        if (w > h) bar.rotation.y = Math.PI / 2;
        g.add(bar);
      });
      // vine leaf blobs climbing the posts (seeded = stable)
      const rng = mulberry32((w * 131 + h * 17 + ((g.userData.containerId || 0) * 7)) | 0);
      const leafMat = pixMaterial(THREE, TEX.leafBlob);
      const blobGeo = new THREE.BoxGeometry(0.3, 0.3, 0.3);
      corners.forEach(([fx, fz]) => {
        const n = 3 + ((rng() * 3) | 0);
        for (let i = 0; i < n; i++) {
          const b = new THREE.Mesh(blobGeo, leafMat);
          b.position.set(fx + (rng() - 0.5) * 0.5, 0.4 + rng() * (hh - 0.8), fz + (rng() - 0.5) * 0.5);
          b.userData.noShadow = true;
          g.add(b);
        }
      });
      g.userData.topY = hh;
    }

    function buildPlantVoxel(THREE, g, px, pz, baseY, species, seed, TEX, big, plantingId) {
      // Minecraft cross-quad: two intersecting pixel-art planes.
      const arch = plantArchetype(species);
      const mat = new THREE.MeshStandardMaterial({
        map: TEX.plants[arch], alphaTest: 0.5, side: THREE.DoubleSide, roughness: 1, metalness: 0,
      });
      const H = big ? 2.0 : 1.3;
      const geo = new THREE.PlaneGeometry(1, H);
      const grp = new THREE.Group();
      const p1 = new THREE.Mesh(geo, mat);
      const p2 = new THREE.Mesh(geo, mat);
      p2.rotation.y = Math.PI / 2;
      p1.userData.noShadow = true;
      p2.userData.noShadow = true;
      grp.add(p1, p2);
      if (plantingId != null) grp.userData.plantingId = plantingId; // build-mode breaking
      const rng = mulberry32(seed);
      grp.rotation.y = rng() * Math.PI;
      const s = 0.9 + rng() * 0.35;
      grp.scale.set(s, s, s);
      grp.position.set(px, baseY + (H * s) / 2 - 0.05, pz);
      g.add(grp);
    }

    function addPlants3D(THREE, g, w, h, kind, c, TEX) {
      const ps = plantingsFor(c.id).slice(0, 6);
      if (!ps.length) return;
      const spots = [];
      if (kind === 'arch') {
        const span = Math.min(w, h), len = Math.max(w, h);
        ps.forEach((p, i) => {
          const t = (i + 0.5) / ps.length - 0.5;
          const side = i % 2 === 0 ? 1 : -1;
          const a = t * Math.max(0.5, len - 1);
          const b = side * Math.max(0.3, span / 2 - 0.45);
          spots.push(h > w ? [b, a] : [a, b]);
        });
      } else {
        const perRow = Math.ceil(Math.sqrt(ps.length));
        const nRows = Math.ceil(ps.length / perRow);
        ps.forEach((p, i) => {
          const row = Math.floor(i / perRow), col = i % perRow;
          const inRow = Math.min(perRow, ps.length - row * perRow);
          const sx = Math.max(0, w - 1.2), sz = Math.max(0, h - 1.2);
          spots.push([
            inRow === 1 ? 0 : -sx / 2 + sx * (col / (inRow - 1)),
            nRows === 1 ? 0 : -sz / 2 + sz * (row / (nRows - 1)),
          ]);
        });
      }
      const baseY = kind === 'arch' ? 0 : (g.userData.topY || 1);
      spots.forEach(([spx, spz], i) => {
        const p = ps[i];
        buildPlantVoxel(THREE, g, spx, spz, baseY, p && p.species_type, (c.id * 1009 + i * 101) | 0, TEX, kind === 'arch', p && p.id);
      });
    }

    function makeLabel(text) {
      const THREE = T.THREE;
      const fs = 34;
      const cv = document.createElement('canvas');
      let ctx = cv.getContext('2d');
      ctx.font = `600 ${fs}px system-ui, -apple-system, sans-serif`;
      const tw = Math.ceil(ctx.measureText(text || '?').width);
      cv.width = tw + 40;
      cv.height = 58;
      ctx = cv.getContext('2d');
      const r = 15;
      ctx.beginPath();
      ctx.moveTo(r, 2);
      ctx.lineTo(cv.width - r, 2); ctx.quadraticCurveTo(cv.width - 2, 2, cv.width - r, 2);
      ctx.lineTo(cv.width - 2, 58 - r); ctx.quadraticCurveTo(cv.width - 2, 58, cv.width - r, 58);
      ctx.lineTo(r, 58); ctx.quadraticCurveTo(2, 58, 2, 58 - r);
      ctx.lineTo(2, r); ctx.quadraticCurveTo(2, 2, r, 2);
      ctx.closePath();
      ctx.fillStyle = 'rgba(253,251,246,0.94)';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(47,79,117,0.35)';
      ctx.stroke();
      ctx.font = `600 ${fs}px system-ui, -apple-system, sans-serif`;
      ctx.fillStyle = '#142337';
      ctx.textBaseline = 'middle';
      ctx.fillText(text || '?', 20, 31);
      const tex = new THREE.CanvasTexture(cv);
      tex.minFilter = THREE.LinearFilter;
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
      sp.scale.set(cv.width * 0.011, cv.height * 0.011, 1);
      sp.renderOrder = 10;
      return sp;
    }

    function buildClouds(THREE, group, rng) {
      const mat = new THREE.MeshBasicMaterial({ color: 0xffffff });
      for (let i = 0; i < 6; i++) {
        const cw = 5 + rng() * 7, cd = 3 + rng() * 4;
        const cloud = new THREE.Group();
        const n = 2 + ((rng() * 3) | 0);
        for (let j = 0; j < n; j++) {
          const puff = box(THREE, cw * (0.5 + rng() * 0.5), 1.4, cd * (0.5 + rng() * 0.5), mat);
          puff.position.set((rng() - 0.5) * cw, (rng() - 0.5) * 0.6, (rng() - 0.5) * cd);
          cloud.add(puff);
        }
        const ext = Math.max(cols, rows) / 2 + 14;
        cloud.position.set((rng() - 0.5) * ext * 2.4, 26 + rng() * 10, (rng() - 0.5) * ext * 2.4);
        cloud.traverse((o) => { o.castShadow = false; o.receiveShadow = false; });
        group.add(cloud);
      }
    }

    function buildScene3D() {
      if (!T) return;
      const { THREE, scene, camera, controls, sun } = T;
      if (T.group) {
        scene.remove(T.group);
        disposeGroup(T.group);
      }
      const group = new THREE.Group();
      T.group = group;
      const TEX = buildTextures(THREE);
      T.TEX = TEX;
      const rng = mulberry32(1234);

      // the world: one big grass block (dirt sides, grass fringe)
      const gw = cols + 8, gd = rows + 8;
      const ground = new THREE.Mesh(
        new THREE.BoxGeometry(gw, 1, gd),
        [
          pixMaterial(THREE, TEX.dirtSideX),
          pixMaterial(THREE, TEX.dirtSideX),
          pixMaterial(THREE, TEX.grass),
          pixMaterial(THREE, TEX.dirt),
          pixMaterial(THREE, TEX.dirtSideZ),
          pixMaterial(THREE, TEX.dirtSideZ),
        ]
      );
      ground.position.y = -0.5;
      ground.receiveShadow = true;
      ground.userData.isGround = true; // build-mode placement targets this
      group.add(ground);

      buildClouds(THREE, group, rng);

      containers.forEach((c) => {
        const w = c.grid_w || 1, h = c.grid_h || 1;
        const g = new THREE.Group();
        g.position.set((c.grid_x || 0) + w / 2 - cols / 2, 0, (c.grid_y || 0) + h / 2 - rows / 2);
        g.userData.containerId = c.id;
        const kind = c.kind || 'grow bag';
        if (kind === 'arch') buildArch(THREE, g, w, h, c.height_ft || KIND_HEIGHT.arch || 4, TEX);
        else if (kind === 'pallet') buildPallet(THREE, g, w, h, TEX);
        else buildVessel(THREE, g, w, h, kind, TEX);
        addPlants3D(THREE, g, w, h, kind, c, TEX);
        const label = makeLabel(c.name);
        label.position.y = (g.userData.topY || 1) + 1.2;
        g.add(label);
        g.traverse((o) => { if (o.isMesh && !o.userData.noShadow) o.castShadow = true; });
        group.add(g);
      });
      scene.add(group);

      // frame the garden
      const maxDim = Math.max(cols, rows);
      camera.position.set(maxDim * 0.58, maxDim * 0.62, maxDim * 0.72);
      controls.target.set(0, 0, 0);
      controls.update();
      const ext = maxDim / 2 + 8;
      sun.position.set(cols * 0.6, 34, rows * 0.45);
      Object.assign(sun.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext });
      sun.shadow.camera.updateProjectionMatrix();
      sizeThree();
    }

    function render3D() {
      // Note: OrbitControls dispatches 'change' from inside update(), so this
      // must only render — calling update() here would recurse forever.
      if (!T || view !== '3d') return;
      T.renderer.render(T.scene, T.camera);
    }

    /* ---------------- walk mode ---------------- */
    // First-person: PointerLockControls for look, WASD for move, AABB
    // collision vs container footprints (arches are walk-under-able).
    let walk = null; // { plc, keys, locked, loopId, last, x, z, yaw }
    const EYE = 1.7, WALK_SPEED = 4, SPRINT_SPEED = 8, PLAYER_R = 0.35;

    const raf = (fn) => (typeof requestAnimationFrame === 'function')
      ? requestAnimationFrame(fn)
      : setTimeout(() => fn(typeof performance !== 'undefined' ? performance.now() : Date.now()), 16);
    const caf = (id) => {
      if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(id);
      else clearTimeout(id);
    };

    function isTouchOnly() {
      try {
        return 'ontouchstart' in window && !(window.matchMedia && window.matchMedia('(pointer:fine)').matches);
      } catch (e) { return false; }
    }

    async function ensureWalk() {
      if (walk) return walk;
      await ensureThree();
      const THREE = T.THREE;
      if (!THREE.PointerLockControls) {
        const CDN = 'https://cdn.jsdelivr.net/npm/three@0.147.0';
        await loadScript(`${CDN}/examples/js/controls/PointerLockControls.js`);
      }
      if (!THREE.PointerLockControls) throw new Error('walk unavailable');
      const plc = new THREE.PointerLockControls(T.camera, T.renderer.domElement);
      walk = { plc, keys: {}, locked: false, loopId: 0, last: 0, x: 0, z: 0, yaw: 0 };
      plc.addEventListener('lock', () => { walk.locked = true; startWalkLoop(); });
      plc.addEventListener('unlock', () => { walk.locked = false; });
      window.addEventListener('keydown', (e) => {
        if (!walkMode || !walk) return;
        walk.keys[e.code] = true;
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code) && e.preventDefault) e.preventDefault();
      });
      window.addEventListener('keyup', (e) => { if (walk) walk.keys[e.code] = false; });
      window.addEventListener('blur', () => { if (walk) walk.keys = {}; });
      return walk;
    }

    // Container footprints as AABBs in world coords. Arches are excluded —
    // walking under them is half the fun.
    function walkColliders() {
      const boxes = [];
      (containers || []).forEach((c) => {
        if ((c.kind || 'grow bag') === 'arch') return;
        const w = c.grid_w || 1, h = c.grid_h || 1;
        const cx = (c.grid_x || 0) + w / 2 - cols / 2;
        const cz = (c.grid_y || 0) + h / 2 - rows / 2;
        boxes.push({ minX: cx - (w / 2) * 0.96, maxX: cx + (w / 2) * 0.96, minZ: cz - (h / 2) * 0.96, maxZ: cz + (h / 2) * 0.96 });
      });
      return boxes;
    }

    // Pure: resolve a player circle vs AABBs + world bounds. Used by the loop
    // and directly by tests.
    function resolvePlayerCollision(px, pz, boxes, radius) {
      radius = radius == null ? PLAYER_R : radius;
      const bx = cols / 2 + 3.5, bz = rows / 2 + 3.5;
      px = Math.max(-bx, Math.min(bx, px));
      pz = Math.max(-bz, Math.min(bz, pz));
      (boxes || []).forEach((b) => {
        const cx = Math.max(b.minX, Math.min(px, b.maxX));
        const cz = Math.max(b.minZ, Math.min(pz, b.maxZ));
        const dx = px - cx, dz = pz - cz;
        const d2 = dx * dx + dz * dz;
        if (d2 >= radius * radius) return;
        if (d2 > 1e-9) {
          const d = Math.sqrt(d2);
          px = cx + (dx / d) * radius;
          pz = cz + (dz / d) * radius;
        } else {
          // center inside the box: push out along least-penetration axis
          const pl = px - b.minX, pr = b.maxX - px, pt = pz - b.minZ, pb = b.maxZ - pz;
          const m = Math.min(pl, pr, pt, pb);
          if (m === pl) px = b.minX - radius;
          else if (m === pr) px = b.maxX + radius;
          else if (m === pt) pz = b.minZ - radius;
          else pz = b.maxZ + radius;
        }
      });
      return { x: px, z: pz };
    }

    function movePlayer(dt) {
      if (!walk) return;
      const yaw = walk.yaw || 0;
      const fx = -Math.sin(yaw), fz = -Math.cos(yaw);
      const rx = Math.cos(yaw), rz = -Math.sin(yaw);
      const k = walk.keys || {};
      let mx = 0, mz = 0;
      if (k.KeyW || k.ArrowUp) mz += 1;
      if (k.KeyS || k.ArrowDown) mz -= 1;
      if (k.KeyD || k.ArrowRight) mx += 1;
      if (k.KeyA || k.ArrowLeft) mx -= 1;
      if (!mx && !mz) return;
      const sp = (k.ShiftLeft || k.ShiftRight) ? SPRINT_SPEED : SPRINT_SPEED / 2;
      const len = Math.hypot(mx, mz);
      const nx = walk.x + ((fx * mz + rx * mx) / len) * sp * dt;
      const nz = walk.z + ((fz * mz + rz * mx) / len) * sp * dt;
      const r = resolvePlayerCollision(nx, nz, walkColliders());
      walk.x = r.x;
      walk.z = r.z;
      if (T && T.camera) T.camera.position.set(walk.x, EYE, walk.z);
    }

    // One loop iteration. Returns true when the loop should continue.
    function walkStep(t) {
      if (!walkMode || !walk || !walk.locked) { if (walk) walk.loopId = 0; return false; }
      const now = typeof t === 'number' ? t : Date.now();
      const dt = Math.min(0.05, Math.max(0.001, (now - (walk.last || now - 16)) / 1000));
      walk.last = now;
      if (T && T.THREE && T.camera) {
        const e = new T.THREE.Euler().setFromQuaternion(T.camera.quaternion, 'YXZ');
        walk.yaw = e.y;
      }
      movePlayer(dt);
      updateGhost();
      render3D();
      return true;
    }

    function startWalkLoop() {
      if (!walk || walk.loopId) return;
      walk.last = 0;
      const frame = (t) => { walk.loopId = 0; if (walkStep(t)) walk.loopId = raf(frame); };
      walk.loopId = raf(frame);
    }

    function stopWalkLoop() {
      if (walk && walk.loopId) { caf(walk.loopId); walk.loopId = 0; }
    }

    async function enterWalkMode() {
      if (isTouchOnly()) { toast('Walk mode needs a keyboard + mouse.'); return; }
      try { await ensureWalk(); }
      catch (err) {
        toast('Could not load walk controls — check your connection and try again.', 'error');
        return;
      }
      walkMode = true;
      // start at the south edge, facing the garden (yaw 0 faces -z)
      walk.x = 0; walk.z = rows / 2 + 3; walk.yaw = 0; walk.keys = {};
      T.camera.position.set(walk.x, EYE, walk.z);
      T.camera.lookAt(0, EYE, 0);
      T.controls.enabled = false;
      crosshair.style.display = 'block';
      hint3d.textContent = walkHintText;
      hotbar.style.display = 'block';
      paintHotbar();
      bindBuildInputs();
      paintViewButtons();
      render3D();
      toast('Click the garden to grab the mouse, then walk with WASD.');
    }

    function exitWalkMode() {
      if (!walkMode) return;
      walkMode = false;
      stopWalkLoop();
      if (walk) {
        if (walk.plc && walk.plc.isLocked) { try { walk.plc.unlock(); } catch (e) { /* noop */ } }
        walk.locked = false;
      }
      if (T) {
        T.controls.enabled = true;
        crosshair.style.display = 'none';
        hotbar.style.display = 'none';
        clearGhost();
        hint3d.textContent = orbitHintText;
        buildScene3D(); // reframes the orbit camera
      }
      paintViewButtons();
    }

    wrap3d._walk = { // handle for tests / debugging
      resolvePlayerCollision, mulberry32, plantArchetype, walkColliders, makePixTexture,
      painters: {
        paintGrassTop, paintDirtSide, paintDirt, paintWoodPlanks, paintDarkWood,
        paintSoil, paintFabric, paintTerracotta, paintLeafBlob, paintSprite, SPRITES,
      },
      get mode() { return walkMode; },
      _get: () => walk,
      _set: (w) => { walk = w; },
      _setMode: (m) => { walkMode = m; },
      _startLoop: () => startWalkLoop(),
      _stopLoop: () => stopWalkLoop(),
      _tick: (t) => walkStep(t),
      _enter: () => enterWalkMode(),
      _exit: () => exitWalkMode(),
    };
    /* -------------- end walk mode -------------- */

    /* ---------------- build mode (Minecraft creative) ---------------- */
    // Hotbar + place/break while walking. Every mutation goes through the
    // real API and the 3D scene is rebuilt after each change. Creative
    // rules: infinite inventory, and the ground itself is never breakable.

    const HOTBAR = {
      blocks: [
        { key: 'raised bed', emoji: '🟫', label: 'Bed' },
        { key: 'grow bag', emoji: '⬛', label: 'Bag' },
        { key: 'pot', emoji: '🟧', label: 'Pot' },
        { key: 'planter', emoji: '🟨', label: 'Planter' },
        { key: 'pallet', emoji: '🟤', label: 'Pallet' },
        { key: 'arch', emoji: '⛩️', label: 'Arch' },
        { key: 'cold frame', emoji: '🪟', label: 'ColdFr' },
      ],
      plants: [
        { key: 'tomato', emoji: '🍅', label: 'Tomato', species: 'Tomato' },
        { key: 'pepper', emoji: '🫑', label: 'Pepper', species: 'Pepper' },
        { key: 'basil', emoji: '🌿', label: 'Basil', species: 'Basil' },
        { key: 'lettuce', emoji: '🥬', label: 'Lettuce', species: 'Lettuce' },
        { key: 'carrot', emoji: '🥕', label: 'Carrot', species: 'Carrot' },
        { key: 'flower', emoji: '🌸', label: 'Flower', species: 'Flower' },
      ],
    };
    let buildTab = 'blocks';
    let buildIndex = 0;
    let ghost = null; // translucent placement preview (scene-level, not in T.group)
    let buildInputsBound = false;
    let buildRay = null;

    // ---- pure helpers (also exposed to tests via wrap3d._build) ----
    function cellFromWorld(wx, wz, ncols, nrows) {
      // inverse of the container placement: wx = gx + w/2 - cols/2
      return { gx: Math.floor(wx + ncols / 2), gy: Math.floor(wz + nrows / 2) };
    }
    function rectsOverlap(ax, ay, aw, ah, bx, by, bw, bh) {
      return ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah;
    }
    function cellFree(gx, gy, w, h, list, ncols, nrows, ignoreId) {
      if (gx < 0 || gy < 0 || gx + w > ncols || gy + h > nrows) return false;
      return !(list || []).some((c) => c.id !== ignoreId && rectsOverlap(
        gx, gy, w, h, c.grid_x || 0, c.grid_y || 0, c.grid_w || 1, c.grid_h || 1));
    }
    function buildSlots() { return buildTab === 'blocks' ? HOTBAR.blocks : HOTBAR.plants; }
    function buildSelected() { const s = buildSlots(); return s[buildIndex] || s[0]; }
    function buildSelect(i) {
      const n = buildSlots().length;
      buildIndex = ((i % n) + n) % n;
      paintHotbar();
    }
    function buildCycle(d) { buildSelect(buildIndex + d); }
    function buildToggleTab() {
      buildTab = buildTab === 'blocks' ? 'plants' : 'blocks';
      buildIndex = 0;
      paintHotbar();
    }
    function nextContainerName(kind) {
      const base = String(kind || 'grow bag').replace(/\b\w/g, (c) => c.toUpperCase());
      const names = new Set((containers || []).map((c) => (c.name || '').toLowerCase()));
      let n = 1;
      while (names.has(`${base} ${n}`.toLowerCase())) n++;
      return `${base} ${n}`;
    }
    function needsBreakConfirm(c) { return plantingsFor(c.id).length > 0; }

    // ---- hotbar DOM (Minecraft-style, keyboard/wheel driven) ----
    const hotbar = document.createElement('div');
    hotbar.style.cssText = 'position:absolute;left:50%;bottom:12px;transform:translateX(-50%);' +
      'display:none;z-index:6;pointer-events:none;text-align:center;';
    const hotbarTab = document.createElement('div');
    const hotbarSlots = document.createElement('div');
    hotbar.appendChild(hotbarTab);
    hotbar.appendChild(hotbarSlots);
    wrap3d.appendChild(hotbar);

    function paintHotbar() {
      hotbarTab.textContent = (buildTab === 'blocks' ? '▣ BLOCKS' : '❀ PLANTS') + ' · Q switch · 1-7/wheel pick';
      hotbarTab.style.cssText = 'color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;' +
        'text-shadow:0 1px 2px #000;margin-bottom:4px;';
      hotbarSlots.innerHTML = buildSlots().map((s, i) => {
        const on = i === buildIndex;
        return '<div style="display:inline-block;width:54px;margin:0 2px;padding:4px 2px;' +
          'background:rgba(18,18,18,.75);border:2px solid ' + (on ? '#fff' : '#5a5a5a') + ';' +
          (on ? 'box-shadow:0 0 0 2px #fff;' : '') + 'border-radius:3px;vertical-align:top;">' +
          '<div style="font-size:22px;line-height:1.25">' + s.emoji + '</div>' +
          '<div style="font-size:9px;color:#ddd;white-space:nowrap;overflow:hidden">' + s.label + '</div>' +
          '<div style="font-size:9px;color:#9f9;font-weight:700">∞</div></div>';
      }).join('');
    }
    paintHotbar();

    function unlockPointer() {
      if (walk && walk.plc && walk.plc.isLocked) { try { walk.plc.unlock(); } catch (e) { /* noop */ } }
      if (walk) walk.locked = false;
    }

    // Raycast from the crosshair; walks up to find planting / container / ground.
    function aimHit() {
      if (!T || !T.group) return null;
      const THREE = T.THREE;
      if (!buildRay) buildRay = new THREE.Raycaster();
      T.camera.updateMatrixWorld(); // aim exactly where the camera is now, not last frame's matrix
      buildRay.setFromCamera(new THREE.Vector2(0, 0), T.camera);
      const hits = buildRay.intersectObjects(T.group.children, true);
      for (const h of hits) {
        if (h.object.isSprite) continue; // labels float above; aim through them
        let o = h.object, plantingId = null, containerId = null, isGround = false;
        while (o) {
          const ud = o.userData || {};
          if (plantingId === null && ud.plantingId != null) plantingId = ud.plantingId;
          if (containerId === null && ud.containerId != null) containerId = ud.containerId;
          if (ud.isGround) isGround = true;
          o = o.parent;
        }
        return { plantingId, containerId, isGround, point: h.point };
      }
      return null;
    }

    // Rebuild the 3D scene without yanking the walk camera out of first person.
    function refreshScene3D() {
      if (!T) return;
      let pos = null, quat = null;
      if (walkMode) {
        pos = T.camera.position.clone();
        quat = T.camera.quaternion.clone();
      }
      buildScene3D();
      if (walkMode && pos) {
        T.camera.position.copy(pos);
        T.camera.quaternion.copy(quat);
        render3D();
      }
    }

    async function breakAim() {
      const a = aimHit();
      if (!a) return;
      if (a.plantingId != null) {
        try {
          await api.del(`/api/containers/plantings/${a.plantingId}`);
          plantings = plantings.filter((p) => p.id !== a.plantingId);
          toast('Planting removed.');
          refreshScene3D();
        } catch (err) { toast(err.message || 'Could not remove planting.', 'error'); }
        return;
      }
      if (a.containerId == null) return;
      const c = containers.find((x) => x.id === a.containerId);
      if (!c) return;
      const n = plantingsFor(c.id).length;
      if (n > 0) {
        unlockPointer(); // confirm() needs a free mouse
        if (!confirm(`Break ${c.name}? Its ${n} planting${n === 1 ? '' : 's'} go${n === 1 ? 'es' : ''} too.`)) return;
      }
      try {
        await api.del(`/api/containers/${c.id}`);
        containers = containers.filter((x) => x.id !== c.id);
        plantings = plantings.filter((p) => p.container_id !== c.id);
        toast(`${c.name} broken.`);
        refreshScene3D();
      } catch (err) { toast(err.message || 'Could not break that.', 'error'); }
    }

    async function placeAim() {
      const a = aimHit();
      if (!a) return;
      const sel = buildSelected();
      if (buildTab === 'blocks') {
        if (!a.isGround) { toast('Aim at the ground to place blocks.', 'error'); return; }
        const { gx, gy } = cellFromWorld(a.point.x, a.point.z, cols, rows);
        if (!cellFree(gx, gy, 1, 1, containers, cols, rows, null)) { toast('No room there.', 'error'); return; }
        const name = nextContainerName(sel.key);
        let created = null;
        try {
          // create() auto-picks the first free spot; then move it to the aimed cell.
          created = await api.post('/api/containers/', {
            name, kind: sel.key, grid_w: 1, grid_h: 1, season_year: year,
          });
          const moved = await api.patch(`/api/containers/${created.id}`, { grid_x: gx, grid_y: gy });
          containers.push(moved);
          toast(`${name} placed.`);
          refreshScene3D();
        } catch (err) {
          if (created && created.id) { try { await api.del(`/api/containers/${created.id}`); } catch (e) { /* noop */ } }
          toast(err.message || 'Could not place that.', 'error');
        }
      } else {
        if (a.containerId == null) { toast('Aim at a container to plant.', 'error'); return; }
        const c = containers.find((x) => x.id === a.containerId);
        if (!c) return;
        try {
          const plant = await api.post('/api/plants/', { variety_name: sel.label, species_type: sel.species });
          const np = await api.post('/api/containers/plantings', { container_id: c.id, plant_id: plant.id });
          plantings.push(np);
          toast(`${sel.label} planted in ${c.name}.`);
          refreshScene3D();
        } catch (err) { toast(err.message || 'Could not plant that.', 'error'); }
      }
    }

    function editAim() {
      const a = aimHit();
      const c = a && a.containerId != null ? containers.find((x) => x.id === a.containerId) : null;
      if (!c) return;
      unlockPointer();
      openModal(c);
    }

    function disposeGhostMeshes(gr) {
      // NB: shared TEX maps are NOT disposed here — buildScene3D owns them.
      gr.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
      });
    }

    function clearGhost() {
      if (ghost && T) { T.scene.remove(ghost); disposeGhostMeshes(ghost); }
      ghost = null;
    }

    // Translucent green/red preview of the selected block at the aimed cell.
    // Runs every walk-loop frame; rebuilds only when cell/validity/selection changes.
    function updateGhost() {
      if (!T) return;
      const show = walkMode && walk && walk.locked && buildTab === 'blocks';
      const a = show ? aimHit() : null;
      let cell = null, ok = false;
      if (a && a.isGround) {
        cell = cellFromWorld(a.point.x, a.point.z, cols, rows);
        ok = cellFree(cell.gx, cell.gy, 1, 1, containers, cols, rows, null);
      }
      const sel = buildSelected();
      const key = show && cell ? `${sel.key}@${cell.gx},${cell.gy}:${ok ? 'g' : 'r'}` : '';
      if (!key) { clearGhost(); return; }
      if (ghost && ghost.userData.key === key) return;
      clearGhost();
      const THREE = T.THREE;
      ghost = new THREE.Group();
      if (sel.key === 'arch') buildArch(THREE, ghost, 1, 1, 4, T.TEX);
      else if (sel.key === 'pallet') buildPallet(THREE, ghost, 1, 1, T.TEX);
      else buildVessel(THREE, ghost, 1, 1, sel.key, T.TEX);
      const tint = new THREE.Color(ok ? 0x00cc44 : 0xcc2222);
      ghost.traverse((o) => {
        if (o.isMesh) {
          o.material.transparent = true;
          o.material.opacity = 0.6;
          o.material.emissive = tint;
          o.material.emissiveIntensity = 0.6;
          o.castShadow = false;
        }
      });
      ghost.position.set(cell.gx + 0.5 - cols / 2, 0.03, cell.gy + 0.5 - rows / 2);
      ghost.userData.key = key;
      T.scene.add(ghost);
    }

    function buildTyping() {
      const a = document.activeElement;
      return !!(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
    }

    function bindBuildInputs() {
      if (buildInputsBound || !T) return;
      buildInputsBound = true;
      const el = T.renderer.domElement;
      el.addEventListener('contextmenu', (e) => { if (walkMode) e.preventDefault(); });
      el.addEventListener('wheel', (e) => {
        if (!walkMode) return;
        e.preventDefault();
        buildCycle(e.deltaY > 0 ? 1 : -1);
      }, { passive: false });
      window.addEventListener('keydown', (e) => {
        if (!walkMode || buildTyping()) return;
        if (e.code === 'KeyQ') buildToggleTab();
        else if (e.code === 'KeyE') editAim();
        else if (/^Digit[1-7]$/.test(e.code)) buildSelect(Number(e.code.slice(5)) - 1);
      });
    }

    wrap3d._build = { // handle for tests / debugging
      cellFromWorld, rectsOverlap, cellFree, needsBreakConfirm,
      buildSlots, buildSelected, buildSelect, buildCycle, buildToggleTab,
      nextContainerName, updateGhost, aimHit, breakAim, placeAim, editAim,
      get tab() { return buildTab; },
      get index() { return buildIndex; },
      _setTab: (t) => { buildTab = t; buildIndex = 0; paintHotbar(); },
      _hotbar: () => hotbar,
      _ghost: () => ghost,
    };
    /* -------------- end build mode -------------- */

    function paintViewButtons() {
      const on = 'bg-sage-200 px-3 py-1 font-semibold text-navy-800';
      const off = 'bg-beige-50 px-3 py-1 text-navy-500 hover:bg-beige-100';
      view2dBtn.className = view === '2d' ? on : off;
      view3dBtn.className = (view === '3d' && !walkMode) ? on : off;
      if (viewWalkBtn) {
        viewWalkBtn.className = (walkMode ? on : off) + (view === '3d' ? '' : ' hidden');
      }
    }

    async function setView(v) {
      if (v === '3d') {
        try {
          await ensureThree();
        } catch (err) {
          threeFailed = true;
          toast('Could not load the 3D library — check your connection and try again.', 'error');
          return;
        }
        view = '3d';
        buildScene3D();
        render3D();
      } else {
        exitWalkMode();
        view = '2d';
      }
      const is3d = view === '3d';
      canvas.classList.toggle('hidden', is3d);
      canvas.style.display = is3d ? 'none' : 'grid'; // inline display beats the class
      hint2d.classList.toggle('hidden', is3d);
      wrap3d.classList.toggle('hidden', !is3d);
      hint3d.classList.toggle('hidden', !is3d);
      paintViewButtons();
      if (is3d) sizeThree();
    }

    view2dBtn.addEventListener('click', () => setView('2d'));
    view3dBtn.addEventListener('click', () => { if (walkMode) exitWalkMode(); else setView('3d'); });
    if (viewWalkBtn) {
      viewWalkBtn.addEventListener('click', () => {
        if (view !== '3d') return;
        if (walkMode) exitWalkMode();
        else enterWalkMode();
      });
    }
    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('resize', () => { if (view === '3d') sizeThree(); });
    }
    paintViewButtons();
    /* ---------------- end 3D view ---------------- */


    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPlanner);
  } else {
    initPlanner();
  }
})();

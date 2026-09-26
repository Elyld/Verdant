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
    let year = new Date().getFullYear();
    let cols = 24, rows = 16;
    let editingId = null;
    let pendingPlantings = [];
    let forecast = null;
    let tempUnit = 'F';
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
      const [cs, g, pl, p, l, ys, rw, fc, al, cp] = await Promise.all([
        api.get(`/api/containers/?year=${year}`).catch(() => []),
        api.get('/api/containers/grid').catch(() => ({ cols: 24, rows: 16 })),
        api.get(`/api/containers/plantings?year=${year}`).catch(() => []),
        api.get('/api/plants/').catch(() => []),
        api.get('/api/locations/').catch(() => []),
        api.get('/api/containers/years').catch(() => []),
        api.get(`/api/containers/rotation-warnings?year=${year}`).catch(() => []),
        api.get('/api/weather/forecast').catch(() => ({ ok: false })),
        api.get('/api/weather/alerts').catch(() => ({ ok: false, alerts: [] })),
        api.get('/static/data/companions.json').catch(() => []),
      ]);
      containers = Array.isArray(cs) ? cs : [];
      cols = g.cols || 24;
      rows = g.rows || 16;
      plantings = Array.isArray(pl) ? pl : [];
      plants = Array.isArray(p) ? p : [];
      locations = Array.isArray(l) ? l : [];
      years = Array.isArray(ys) ? ys : [];
      warnings = Array.isArray(rw) ? rw : [];
      forecast = fc && fc.ok ? fc.forecast : null;
      tempUnit = (fc && fc.temp_unit) || 'F';
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
      renderWeather();
      renderWxAlerts();
      render();
      if (view === '3d' && T) buildScene3D();
    }

    const ALERT_TONE = {
      info: 'bg-sky-50 ring-sky-300 text-sky-900',
      warn: 'bg-amber-50 ring-amber-300 text-amber-900',
      critical: 'bg-red-50 ring-red-400 text-red-900',
    };

    function fmtTemp(f) {
      if (f == null) return '—';
      return `${Math.round(f)}°${tempUnit}`;
    }

    function fmtTime(iso) {
      if (!iso) return '';
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }

    function renderWeather() {
      const strip = $('#weather-strip');
      if (!forecast || !forecast.current) {
        strip.classList.add('hidden');
        strip.classList.remove('flex');
        return;
      }
      const cur = forecast.current;
      const days = forecast.daily || [];
      const tonight = days[0] ? fmtTemp(days[0].tmin_f) : '—';
      const tm = days[1] || days[0] || {};
      const rain = tm.precip_prob != null ? `${tm.precip_prob}%` : '—';
      const gust = tm.gust_mph != null ? `${Math.round(tm.gust_mph)} mph` : '—';
      strip.innerHTML =
        `<span class="font-semibold">${fmtTemp(cur.temp_f)} ${esc(cur.summary || '')}</span>` +
        `<span class="text-beige-300">·</span><span>🌙 Tonight ${tonight}</span>` +
        `<span class="text-beige-300">·</span><span>☀️ Tomorrow ${fmtTemp(tm.tmax_f)}</span>` +
        `<span class="text-beige-300">·</span><span>💧 ${rain}</span>` +
        `<span class="text-beige-300">·</span><span>💨 ${gust}</span>` +
        `<span class="ml-auto text-xs text-beige-300">as of ${fmtTime(forecast.as_of)}</span>`;
      strip.classList.remove('hidden');
      strip.classList.add('flex');
    }

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
    let view = '2d';
    let T = null; // { THREE, renderer, scene, camera, controls, sun, group, raf }
    let threeFailed = false;

    const view2dBtn = $('#view-2d');
    const view3dBtn = $('#view-3d');
    const wrap3d = $('#planner-3d');
    const hint2d = $('#planner-2d-hint');
    const hint3d = $('#planner-3d-hint');

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
      scene.background = new THREE.Color(0xe9eef2);
      scene.fog = new THREE.Fog(0xe9eef2, 70, 160);

      const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500);
      const controls = new THREE.OrbitControls(camera, renderer.domElement);
      // On-demand rendering (no rAF loop): kinder to phone batteries, and every
      // interaction fires a 'change' event that re-renders the scene.
      controls.enableDamping = false;
      controls.maxPolarAngle = Math.PI / 2 - 0.03;
      controls.minDistance = 4;
      controls.maxDistance = 130;
      controls.addEventListener('change', () => render3D());

      scene.add(new THREE.HemisphereLight(0xffffff, 0x9db38f, 0.75));
      const sun = new THREE.DirectionalLight(0xfff6e6, 0.7);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.camera.near = 1;
      sun.shadow.camera.far = 120;
      scene.add(sun);

      // click (not drag) a container to edit it
      const ray = new THREE.Raycaster();
      const ptr = new THREE.Vector2();
      let downX = 0, downY = 0;
      renderer.domElement.addEventListener('pointerdown', (e) => { downX = e.clientX; downY = e.clientY; });
      renderer.domElement.addEventListener('pointerup', (e) => {
        if (Math.hypot(e.clientX - downX, e.clientY - downY) > 6) return;
        const r = renderer.domElement.getBoundingClientRect();
        if (!r.width) return;
        ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
        ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
        ray.setFromCamera(ptr, camera);
        const hits = T.group ? ray.intersectObjects(T.group.children, true) : [];
        for (const h of hits) {
          let o = h.object;
          while (o && (o.userData.containerId === undefined || o.userData.containerId === null)) o = o.parent;
          if (o) {
            const c = containers.find((x) => x.id === o.userData.containerId);
            if (c) { openModal(c); break; }
          }
        }
      });

      T = { THREE, renderer, scene, camera, controls, sun, group: null };
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

    function soilSlab(THREE, parent, w, h, y) {
      const soil = new THREE.Mesh(
        new THREE.BoxGeometry(Math.max(0.2, w - 0.24), 0.08, Math.max(0.2, h - 0.24)),
        new THREE.MeshStandardMaterial({ color: 0x5d4d2d, roughness: 1 })
      );
      soil.position.y = y;
      soil.receiveShadow = true;
      parent.add(soil);
    }

    function buildVessel(THREE, g, w, h, kind) {
      let bodyH, color;
      if (kind === 'raised bed') { bodyH = 1.1; color = 0x8b6f4e; }
      else if (kind === 'planter') { bodyH = 0.8; color = 0xa4884f; }
      else if (kind === 'pot') { bodyH = 1.0; color = 0xb0654a; }
      else { bodyH = 1.1; color = 0x33383d; } // grow bag
      if (kind === 'pot' || kind === 'grow bag') {
        const r = Math.max(0.3, Math.min(w, h) / 2 * 0.96);
        const geo = kind === 'pot'
          ? new THREE.CylinderGeometry(r, r * 0.78, bodyH, 20)
          : new THREE.CylinderGeometry(r, r * 0.92, bodyH, 20);
        const body = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: 0.9 }));
        body.position.y = bodyH / 2;
        g.add(body);
        const soil = new THREE.Mesh(
          new THREE.CylinderGeometry(r * 0.88, r * 0.88, 0.08, 20),
          new THREE.MeshStandardMaterial({ color: 0x5d4d2d, roughness: 1 })
        );
        soil.position.y = bodyH / 2 - 0.02;
        soil.receiveShadow = true;
        g.add(soil);
      } else {
        const body = new THREE.Mesh(
          new THREE.BoxGeometry(w * 0.98, bodyH, h * 0.98),
          new THREE.MeshStandardMaterial({ color, roughness: 0.9 })
        );
        body.position.y = bodyH / 2;
        g.add(body);
        soilSlab(THREE, g, w, h, bodyH / 2 - 0.02);
      }
      g.userData.topY = bodyH;
    }

    function buildPallet(THREE, g, w, h) {
      const wood = new THREE.MeshStandardMaterial({ color: 0xc0a469, roughness: 0.95 });
      const woodDark = new THREE.MeshStandardMaterial({ color: 0xa4884f, roughness: 0.95 });
      for (let i = 0; i < 3; i++) {
        const s = new THREE.Mesh(new THREE.BoxGeometry(w * 0.98, 0.28, 0.3), woodDark);
        s.position.set(0, 0.14, -h / 2 + 0.35 + i * ((h - 0.7) / 2));
        g.add(s);
      }
      const n = Math.max(3, Math.round(h / 0.7));
      for (let i = 0; i < n; i++) {
        const slat = new THREE.Mesh(
          new THREE.BoxGeometry(w * 0.98, 0.12, Math.max(0.28, (h * 0.98 / n) * 0.7)), wood);
        slat.position.set(0, 0.34, -h * 0.49 + (i + 0.5) * (h * 0.98 / n));
        g.add(slat);
      }
      g.userData.topY = 0.42;
    }

    function buildArch(THREE, g, w, h, height) {
      const span = Math.min(w, h);
      const len = Math.max(w, h);
      const a = Math.max(0.75, span / 2);
      const hh = Math.max(1.5, height || 4);
      // wire grid bent into a half-ellipse: ribs across the span, runs along the length
      const nCross = 9;
      const arcT = [];
      for (let j = 0; j < nCross; j++) arcT.push((j / (nCross - 1)) * Math.PI);
      const pts = [];
      const nRibs = Math.max(4, Math.round(len * 0.75));
      for (let i = 0; i < nRibs; i++) {
        const z = -len / 2 + (i / (nRibs - 1)) * len;
        let prev = null;
        for (const t of arcT) {
          const p = [a * Math.cos(t), hh * Math.sin(t), z];
          if (prev) pts.push(...prev, ...p);
          prev = p;
        }
      }
      for (const t of arcT) {
        const x = a * Math.cos(t), y = hh * Math.sin(t);
        pts.push(x, y, -len / 2, x, y, len / 2);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      const wires = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
        color: 0x7d97b9, transparent: true, opacity: 0.9,
      }));
      if (w > h) wires.rotation.y = Math.PI / 2; // run along X when the footprint is wider
      g.add(wires);
      const footGeo = new THREE.BoxGeometry(0.18, 0.5, 0.18);
      const footMat = new THREE.MeshStandardMaterial({ color: 0x4f6d94, roughness: 0.8 });
      const off = a * 0.92, along = len / 2 - 0.35;
      const corners = w > h
        ? [[-along, -off], [-along, off], [along, -off], [along, off]]
        : [[-off, -along], [off, -along], [-off, along], [off, along]];
      corners.forEach(([fx, fz]) => {
        const f = new THREE.Mesh(footGeo, footMat);
        f.position.set(fx, 0.25, fz);
        g.add(f);
      });
      g.userData.topY = hh;
    }

    function addPlants3D(THREE, g, w, h, kind, c) {
      const ps = plantingsFor(c.id).slice(0, 6);
      if (!ps.length) return;
      const leafA = new THREE.MeshStandardMaterial({ color: 0x688d61, roughness: 1 });
      const leafB = new THREE.MeshStandardMaterial({ color: 0x82a87b, roughness: 1 });
      const stemM = new THREE.MeshStandardMaterial({ color: 0x51704c, roughness: 1 });
      const spots = [];
      if (kind === 'arch') {
        // climbers at the two base edges
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
      spots.forEach(([px, pz], i) => {
        const plant = new THREE.Group();
        const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.5, 6), stemM);
        stem.position.y = 0.25;
        const bush = new THREE.Mesh(new THREE.IcosahedronGeometry(0.3, 0), i % 2 ? leafA : leafB);
        bush.position.y = 0.62;
        bush.scale.y = 0.85;
        plant.add(stem, bush);
        plant.position.set(px, baseY, pz);
        g.add(plant);
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
      ctx.lineTo(cv.width - r, 2); ctx.quadraticCurveTo(cv.width - 2, 2, cv.width - 2, r);
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

    function buildScene3D() {
      if (!T) return;
      const { THREE, scene, camera, controls, sun } = T;
      if (T.group) {
        scene.remove(T.group);
        disposeGroup(T.group);
      }
      const group = new THREE.Group();
      T.group = group;

      // grass + 1-ft grid over the garden area
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(cols + 8, rows + 8),
        new THREE.MeshStandardMaterial({ color: 0x9db38f, roughness: 1 })
      );
      ground.rotation.x = -Math.PI / 2;
      ground.receiveShadow = true;
      group.add(ground);

      const gc = document.createElement('canvas');
      gc.width = Math.max(32, cols * 32);
      gc.height = Math.max(32, rows * 32);
      const g2 = gc.getContext('2d');
      g2.fillStyle = '#a9bf99';
      g2.fillRect(0, 0, gc.width, gc.height);
      g2.strokeStyle = 'rgba(20,35,55,0.30)';
      g2.lineWidth = 1;
      for (let i = 0; i <= cols; i++) { g2.beginPath(); g2.moveTo(i * 32 + 0.5, 0); g2.lineTo(i * 32 + 0.5, gc.height); g2.stroke(); }
      for (let j = 0; j <= rows; j++) { g2.beginPath(); g2.moveTo(0, j * 32 + 0.5); g2.lineTo(gc.width, j * 32 + 0.5); g2.stroke(); }
      const gridPlane = new THREE.Mesh(
        new THREE.PlaneGeometry(cols, rows),
        new THREE.MeshStandardMaterial({ map: new THREE.CanvasTexture(gc), roughness: 1 })
      );
      gridPlane.rotation.x = -Math.PI / 2;
      gridPlane.position.y = 0.01;
      gridPlane.receiveShadow = true;
      group.add(gridPlane);

      containers.forEach((c) => {
        const w = c.grid_w || 1, h = c.grid_h || 1;
        const g = new THREE.Group();
        g.position.set((c.grid_x || 0) + w / 2 - cols / 2, 0, (c.grid_y || 0) + h / 2 - rows / 2);
        g.userData.containerId = c.id;
        const kind = c.kind || 'grow bag';
        if (kind === 'arch') buildArch(THREE, g, w, h, c.height_ft || KIND_HEIGHT.arch || 4);
        else if (kind === 'pallet') buildPallet(THREE, g, w, h);
        else buildVessel(THREE, g, w, h, kind);
        addPlants3D(THREE, g, w, h, kind, c);
        const label = makeLabel(c.name);
        label.position.y = (g.userData.topY || 1) + 1.0;
        g.add(label);
        g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
        group.add(g);
      });
      scene.add(group);

      // frame the garden
      const maxDim = Math.max(cols, rows);
      camera.position.set(maxDim * 0.58, maxDim * 0.62, maxDim * 0.72);
      controls.target.set(0, 0, 0);
      controls.update();
      const ext = maxDim / 2 + 8;
      sun.position.set(cols * 0.6, 32, rows * 0.45);
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

    function paintViewButtons() {
      const on = 'bg-sage-200 px-3 py-1 font-semibold text-navy-800';
      const off = 'bg-beige-50 px-3 py-1 text-navy-500 hover:bg-beige-100';
      view2dBtn.className = view === '2d' ? on : off;
      view3dBtn.className = view === '3d' ? on : off;
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
    view3dBtn.addEventListener('click', () => setView('3d'));
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

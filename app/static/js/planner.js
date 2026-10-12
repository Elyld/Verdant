/* Backyard planner — grid-based container layout per season (1 cell = 1 ft).
 * Containers snap to the grid, have real footprints, and hold many plants. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  const KIND_ICON = { 'grow bag': '🛍️', 'raised bed': '🟫', 'pot': '🪴', 'planter': '🗄️', 'arch': '🌉', 'pallet': '🪵', 'lamp': '💡', 'fence': '⛓️', 'bucket': '🪣', 'path': '🪨', 'rain barrel': '🛢️', 'compost bin': '🟤', 'hoop house': '🏠', 'fence gate': '🚪', 'bird bath': '🐦', 'fruit tree': '🌳', 'shed': '🏚️', 'pergola': '🏛️', 'stone edging': '🧱', 'sprinkler': '💦', 'drip line': '💧' };
  const KIND_TONE = {
    'grow bag': 'bg-sage-100 ring-sage-300',
    'raised bed': 'bg-amber-100 ring-amber-300',
    'pot': 'bg-sky-100 ring-sky-300',
    'planter': 'bg-orange-100 ring-orange-300',
    'arch': 'bg-navy-100 ring-navy-300',
    'pallet': 'bg-beige-200 ring-beige-400',
    'lamp': 'bg-yellow-100 ring-yellow-300',
    'fence': 'bg-stone-100 ring-stone-300',
    'bucket': 'bg-sky-50 ring-sky-200',
    'path': 'bg-stone-200 ring-stone-400',
    'rain barrel': 'bg-sky-200 ring-sky-400',
    'compost bin': 'bg-amber-200 ring-amber-400',
    'hoop house': 'bg-slate-100 ring-slate-300',
    'fence gate': 'bg-stone-100 ring-stone-400',
    'bird bath': 'bg-cyan-100 ring-cyan-300',
    'fruit tree': 'bg-green-100 ring-green-400',
    'shed': 'bg-amber-200 ring-amber-500',
    'pergola': 'bg-orange-100 ring-orange-300',
    'stone edging': 'bg-stone-200 ring-stone-500',
    'sprinkler': 'bg-sky-200 ring-sky-500',
    'drip line': 'bg-slate-200 ring-slate-400',
  };
  const FOOTPRINTS = { 'grow bag': [2, 2], 'raised bed': [4, 4], 'pot': [1, 1], 'planter': [3, 1], 'arch': [4, 4], 'pallet': [4, 3], 'lamp': [1, 1], 'fence': [1, 1], 'bucket': [1, 1], 'path': [1, 1], 'rain barrel': [1, 1], 'compost bin': [1, 1], 'hoop house': [4, 8], 'fence gate': [1, 1], 'bird bath': [1, 1], 'fruit tree': [1, 1], 'shed': [4, 6], 'pergola': [2, 4], 'stone edging': [1, 1], 'sprinkler': [1, 1], 'drip line': [1, 1] };
  const KIND_HEIGHT = { 'arch': 7, 'hoop house': 6 }; // default height in feet, used by the 3D view

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
    const dayNightBtn = $('#view-daynight');
    const tapeBtn = $('#view-tape');
    const soundBtn = $('#view-sound');
    const fsBtn = $('#view-fullscreen');
    const wrap3d = $('#planner-3d');
    const hint2d = $('#planner-2d-hint');
    const hint3d = $('#planner-3d-hint');
    const orbitHintText = 'Drag to orbit · scroll or pinch to zoom · right-drag to pan · click a container to edit it.';
    const walkHintText = 'Click to grab the mouse · WASD walk · Shift sprint · Left-click break · Right-click place · E edit · Q blocks/plants · 1-9/wheel pick · ESC release.';

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

    // sRGB hex -> linear THREE.Color. Needed because the bloom composer chain
    // renders in linear (r147 applies no output encoding to render targets)
    // with a GammaCorrection pass at the end; plain hex Colors are authored
    // as sRGB display values. (Color.convertSRGBToLinear() is a no-op while
    // ColorManagement.legacyMode is true in r147, hence the manual pow.)
    function srgbToLinear(THREE, hex) {
      const c = new THREE.Color(hex);
      c.r = Math.pow(c.r, 2.2); c.g = Math.pow(c.g, 2.2); c.b = Math.pow(c.b, 2.2);
      return c;
    }

    /* ---------- soft miniature painters (64x64, LinearFilter) ---------- */
    function px(ctx, x, y, w, h, c) {
      ctx.fillStyle = c;
      ctx.fillRect(x | 0, y | 0, Math.ceil(w), Math.ceil(h));
    }

    // soft mottled noise: translucent circles over a base coat
    function softNoise(ctx, S, rng, palette, count, rMin, rMax) {
      const n = count || Math.round((S * S) / 5);
      for (let i = 0; i < n; i++) {
        ctx.fillStyle = palette[(rng() * palette.length) | 0];
        ctx.globalAlpha = 0.18 + rng() * 0.28;
        ctx.beginPath();
        ctx.arc(rng() * S, rng() * S, rMin + rng() * (rMax - rMin), 0, 6.2832);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }
    function baseCoat(ctx, S, c) { ctx.fillStyle = c; ctx.fillRect(0, 0, S, S); }

    // 64x64 soft painters. Each takes (ctx, S, rng).
    function paintGrass(ctx, S, rng) {
      baseCoat(ctx, S, '#4da53a');
      softNoise(ctx, S, rng, ['#3f8f31', '#5fbf49', '#4aa839', '#6fd056', '#37902c'], 1100, 1, 4.5);
    }
    function paintGroundSide(ctx, S, rng) {
      // soft dark skirt under the platform
      const g = ctx.createLinearGradient(0, 0, 0, S);
      g.addColorStop(0, '#3f7a33'); g.addColorStop(1, '#26521f');
      ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
      softNoise(ctx, S, rng, ['#3c7030', '#548c40'], 260, 1, 5);
    }
    function paintSoil(ctx, S, rng) {
      baseCoat(ctx, S, '#4a3524');
      softNoise(ctx, S, rng, ['#332413', '#5c4227', '#6b4e2e', '#2b1e10', '#75562f'], 800, 1, 3.5);
    }
    function paintWood(ctx, S, rng) {
      baseCoat(ctx, S, '#8a5a2b');
      // long soft grain streaks
      for (let i = 0; i < 26; i++) {
        ctx.strokeStyle = rng() < 0.5 ? '#5e3a17' : '#b07a3f';
        ctx.globalAlpha = 0.42; ctx.lineWidth = 1 + rng() * 2.5;
        const y = rng() * S;
        ctx.beginPath(); ctx.moveTo(0, y);
        ctx.bezierCurveTo(S * 0.3, y + (rng() - 0.5) * 8, S * 0.7, y + (rng() - 0.5) * 8, S, y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      softNoise(ctx, S, rng, ['#754c1e', '#9c6b35'], 220, 1, 3);
    }
    function paintLightWood(ctx, S, rng) {
      // lighter boards for raised-bed rims so the form reads
      baseCoat(ctx, S, '#c49a63');
      for (let i = 0; i < 16; i++) {
        ctx.strokeStyle = rng() < 0.5 ? '#a87f4c' : '#d9b47e';
        ctx.globalAlpha = 0.4; ctx.lineWidth = 1 + rng() * 2;
        const y = rng() * S;
        ctx.beginPath(); ctx.moveTo(0, y);
        ctx.bezierCurveTo(S * 0.3, y + (rng() - 0.5) * 8, S * 0.7, y + (rng() - 0.5) * 8, S, y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      softNoise(ctx, S, rng, ['#b0864f', '#d6ad77'], 200, 1, 3);
    }
    function paintDarkWood(ctx, S, rng) {
      baseCoat(ctx, S, '#5f4626');
      softNoise(ctx, S, rng, ['#4a3619', '#735631', '#3d2c14'], 550, 1, 3.5);
    }
    function paintFabric(ctx, S, rng) {
      baseCoat(ctx, S, '#35393f');
      softNoise(ctx, S, rng, ['#2b2e33', '#41464d', '#3d4248'], 600, 1, 2.5);
    }
    function paintTerracotta(ctx, S, rng) {
      baseCoat(ctx, S, '#c96f3f');
      const g = ctx.createLinearGradient(0, 0, 0, S);
      g.addColorStop(0, 'rgba(255,255,255,0.10)'); g.addColorStop(1, 'rgba(0,0,0,0.14)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
      softNoise(ctx, S, rng, ['#a8542c', '#e08450', '#96421f'], 480, 1, 3);
    }
    function paintMetal(ctx, S, rng) {
      baseCoat(ctx, S, '#6f767d');
      softNoise(ctx, S, rng, ['#5d646b', '#82898f', '#52585f'], 520, 1, 3);
    }
    function paintWireMesh(ctx, S, rng) {
      // transparent canvas; wire grid reads through alphaTest. Lines are bold
      // enough to read as mesh from the orbit camera, not just up close.
      ctx.strokeStyle = '#bcc4cd'; ctx.lineWidth = 3;
      for (let i = 0; i <= S; i += 8) {
        ctx.beginPath(); ctx.moveTo(i + 0.5, 0); ctx.lineTo(i + 0.5, S); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, i + 0.5); ctx.lineTo(S, i + 0.5); ctx.stroke();
      }
    }
    function paintBucket(ctx, S, rng) {
      baseCoat(ctx, S, '#e8ecef');
      const g = ctx.createLinearGradient(0, 0, S, 0);
      g.addColorStop(0, 'rgba(0,0,0,0.10)'); g.addColorStop(0.25, 'rgba(255,255,255,0.12)');
      g.addColorStop(0.6, 'rgba(0,0,0,0.04)'); g.addColorStop(1, 'rgba(0,0,0,0.12)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
      softNoise(ctx, S, rng, ['#dfe5ea', '#f2f5f7'], 200, 1, 3);
    }
    function paintStone(ctx, S, rng) {
      baseCoat(ctx, S, '#8f959b');
      softNoise(ctx, S, rng, ['#787e85', '#a3a9af', '#6b7177', '#b9bfc5'], 700, 1, 3.5);
    }
    function paintBarrel(ctx, S, rng) {
      baseCoat(ctx, S, '#2f7cd4');
      const g = ctx.createLinearGradient(0, 0, S, 0);
      g.addColorStop(0, 'rgba(0,0,0,0.18)'); g.addColorStop(0.3, 'rgba(255,255,255,0.14)');
      g.addColorStop(1, 'rgba(0,0,0,0.16)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
      softNoise(ctx, S, rng, ['#2568b8', '#4a94e0', '#1f5aa8'], 320, 1, 3);
    }
    function paintCompost(ctx, S, rng) {
      baseCoat(ctx, S, '#3a2d20');
      softNoise(ctx, S, rng, ['#2f2417', '#4d3a26', '#443423'], 550, 1, 3.5);
    }
    function paintHoopPlastic(ctx, S, rng) {
      baseCoat(ctx, S, '#eef2f4');
      softNoise(ctx, S, rng, ['#e2e9ed', '#f7fafb'], 260, 2, 6);
    }
    function paintBasin(ctx, S, rng) {
      baseCoat(ctx, S, '#b9bdc2');
      softNoise(ctx, S, rng, ['#a9aeb4', '#c6cbd0', '#9fa5ab'], 550, 1, 3.5);
    }
    function paintLeaf(ctx, S, rng) {
      baseCoat(ctx, S, '#43a53b');
      softNoise(ctx, S, rng, ['#359231', '#55c04d', '#2c7a28', '#63d155', '#277a24'], 750, 1, 4);
    }
    function paintGrassTuft(ctx, S, rng) {
      // soft meadow blades on transparency
      const greens = ['#43a53b', '#55c04d', '#359231', '#6fd056', '#2c7a28'];
      ctx.lineCap = 'round';
      for (let i = 0; i < 22; i++) {
        ctx.strokeStyle = greens[(rng() * greens.length) | 0];
        ctx.lineWidth = 2 + rng() * 2;
        const x = 4 + rng() * (S - 8), h = S * (0.45 + rng() * 0.45);
        const lean = (rng() - 0.5) * 14;
        ctx.beginPath(); ctx.moveTo(x, S);
        ctx.quadraticCurveTo(x + lean * 0.4, S - h * 0.6, x + lean, S - h); ctx.stroke();
      }
    }
    function paintWildflower(ctx, S, rng, colorIdx) {
      const heads = ['#e5321e', '#ffc21f', '#ffffff'];
      const head = heads[colorIdx == null ? (rng() * 3) | 0 : colorIdx % 3];
      ctx.strokeStyle = '#3f8f37'; ctx.lineWidth = 3; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(S / 2, S);
      ctx.quadraticCurveTo(S / 2 - 4, S * 0.55, S / 2, S * 0.3); ctx.stroke();
      ctx.fillStyle = '#4e9e3f';
      ctx.beginPath(); ctx.ellipse(S / 2 - 8, S * 0.62, 7, 3.5, -0.5, 0, 6.2832); ctx.fill();
      ctx.beginPath(); ctx.ellipse(S / 2 + 8, S * 0.72, 7, 3.5, 0.5, 0, 6.2832); ctx.fill();
      const hx = S / 2, hy = S * 0.22, hr = S * 0.13;
      const g = ctx.createRadialGradient(hx - 2, hy - 2, 1, hx, hy, hr);
      g.addColorStop(0, '#ffffff'); g.addColorStop(0.25, head); g.addColorStop(1, head);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(hx, hy, hr, 0, 6.2832); ctx.fill();
      ctx.fillStyle = '#ffdf5e';
      ctx.beginPath(); ctx.arc(hx, hy, hr * 0.4, 0, 6.2832); ctx.fill();
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
      tex.magFilter = THREE.LinearFilter;
      tex.minFilter = THREE.LinearMipmapLinearFilter;
      tex.generateMipmaps = true;
      tex.encoding = THREE.sRGBEncoding;
      if (repeat) {
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        tex.repeat.set(repeat[0], repeat[1]);
      }
      return tex;
    }

    function pixMaterial(THREE, tex, opts) {
      return new THREE.MeshStandardMaterial(Object.assign({ map: tex, roughness: 0.9, metalness: 0 }, opts || {}));
    }

    async function ensureThree() {
      if (T) return T;
      if (threeFailed) throw new Error('3d unavailable');
      const CDN = 'https://cdn.jsdelivr.net/npm/three@0.147.0';
      await loadScript(`${CDN}/build/three.min.js`);
      await loadScript(`${CDN}/examples/js/controls/OrbitControls.js`);
      // CC0 model pack (v2.62.0): GLTFLoader vendored locally so models load
      // fully self-hosted. Failure here must never break the 3D view.
      try { await loadScript('/static/js/vendor/GLTFLoader.js'); } catch (err) { /* procedural fallback */ }
      const THREE = globalThis.THREE;
      if (!THREE || !THREE.OrbitControls) throw new Error('3d unavailable');
      // Bloom post-processing is a nice-to-have: if any pass fails to load,
      // the plain renderer path keeps working untouched.
      try {
        await loadScript(`${CDN}/examples/js/shaders/CopyShader.js`);
        await loadScript(`${CDN}/examples/js/shaders/LuminosityHighPassShader.js`);
        await loadScript(`${CDN}/examples/js/shaders/GammaCorrectionShader.js`);
        await loadScript(`${CDN}/examples/js/postprocessing/EffectComposer.js`);
        await loadScript(`${CDN}/examples/js/postprocessing/RenderPass.js`);
        await loadScript(`${CDN}/examples/js/postprocessing/ShaderPass.js`);
        await loadScript(`${CDN}/examples/js/postprocessing/MaskPass.js`);
        await loadScript(`${CDN}/examples/js/postprocessing/UnrealBloomPass.js`);
      } catch (err) { /* bloom unavailable; renderer-only fallback below */ }

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min((typeof window !== 'undefined' && window.devicePixelRatio) || 1, 2));
      renderer.outputEncoding = THREE.sRGBEncoding;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      wrap3d.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      // Gradient sky dome (big inverted sphere, BackSide shader): horizon ->
      // zenith blend driven by uniforms so the day/night toggle can lerp them.
      // Fog color tracks the horizon for a seamless ground fade.
      // NOTE: the composer chain renders in linear (r147 applies no output
      // encoding to render targets), with a GammaCorrection pass at the end.
      // Plain THREE.Color hexes are sRGB display values — srgbToLinear (defined
      // next to mulberry32) converts them; without it the sky washes out.
      // Palette comes from skyColors() (single source of truth); applyDayNight
      // re-derives these on toggle.
      const SKY0 = skyColors(false);
      const skyDomeMat = new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        uniforms: {
          topColor: { value: srgbToLinear(THREE, SKY0.top) },
          horizonColor: { value: srgbToLinear(THREE, SKY0.horizon) },
        },
        vertexShader: 'varying vec3 vP; void main() { vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: [
          'uniform vec3 topColor; uniform vec3 horizonColor; varying vec3 vP;',
          'void main() {',
          '  float h = normalize(vP).y;',
          // ease-out curve: rich zenith color reaches down into the low sky
          // angles a typical orbit view actually shows (a plain pow() leaves
          // everything near the pale horizon color).
          '  float t = 1.0 - pow(1.0 - max(h, 0.0), 3.0);',
          '  vec3 c = mix(horizonColor, topColor, t);',
          '  if (h < 0.0) c = mix(horizonColor, horizonColor * 0.45, min(-h * 3.0, 1.0));',
          '  gl_FragColor = vec4(c, 1.0);',
          '}',
        ].join('\n'),
      });
      const skyDome = new THREE.Mesh(new THREE.SphereGeometry(420, 24, 16), skyDomeMat);
      skyDome.userData.noShadow = true;
      scene.add(skyDome);
      scene.fog = new THREE.Fog(SKY0.horizon, 80, 200);

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

      scene.add(new THREE.HemisphereLight(0xaed0ff, 0x9aa050, 1.0)); // lively sky/ground bounce
      const hemi = scene.children[scene.children.length - 1];
      const sun = new THREE.DirectionalLight(0xffe3ae, 1.1); // warm, stronger key
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      sun.shadow.camera.near = 1;
      sun.shadow.camera.far = 140;
      scene.add(sun);

      // Prominent blocky sky: square sun + glow, square moon, starfield.
      // Sprites always face the camera, so the square sun reads correctly
      // from orbit and first person alike. Day/night toggles visibility.
      function skySprite(core, glow, corePx, size) {
        const cv = document.createElement('canvas');
        cv.width = cv.height = 128;
        const cx = cv.getContext('2d');
        const grd = cx.createRadialGradient(64, 64, 8, 64, 64, 64);
        grd.addColorStop(0, glow);
        grd.addColorStop(1, 'rgba(0,0,0,0)');
        cx.fillStyle = grd;
        cx.fillRect(0, 0, 128, 128);
        cx.fillStyle = core;
        cx.beginPath(); cx.arc(64, 64, corePx / 2, 0, 6.2832); cx.fill();
        const tex = new THREE.CanvasTexture(cv);
        tex.encoding = THREE.sRGBEncoding;
        const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, fog: false }));
        sp.scale.set(size, size, 1);
        return sp;
      }
      const sunSprite = skySprite('#ffdf5e', 'rgba(255,220,120,0.4)', 34, 42);
      sunSprite.position.set(-130, 62, -190);
      const moonSprite = skySprite('#e8ecf5', 'rgba(200,215,245,0.35)', 26, 55);
      moonSprite.position.set(140, 60, -190);
      moonSprite.visible = false;
      scene.add(sunSprite);
      scene.add(moonSprite);
      const starGeo = new THREE.BufferGeometry();
      const starPos = new Float32Array(360 * 3);
      {
        const sr = mulberry32(777);
        for (let i = 0; i < 360; i++) {
          const th = sr() * Math.PI * 2, ph = sr() * Math.PI * 0.48;
          const R = 300;
          starPos[i * 3] = R * Math.sin(ph) * Math.cos(th);
          starPos[i * 3 + 1] = R * Math.cos(ph) + 10;
          starPos[i * 3 + 2] = R * Math.sin(ph) * Math.sin(th);
        }
      }
      starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
      const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, fog: false }));
      stars.visible = false;
      scene.add(stars);

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
        if (tapeMode) {
          // measuring tape: first ground hit wins
          for (const h of hits) {
            let o = h.object, ground = false;
            while (o) { if (o.userData && o.userData.isGround) { ground = true; break; } o = o.parent; }
            if (ground) { tapeClick(h.point.x, h.point.z); break; }
          }
          return;
        }
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

      // Bloom composer (half-res internally): sun, lamp heads, fireflies and
      // bright sky bloom; everything else stays crisp. Falls back to the
      // plain renderer when any pass is missing.
      let composer = null;
      try {
        if (THREE.EffectComposer && THREE.RenderPass && THREE.UnrealBloomPass && THREE.GammaCorrectionShader) {
          composer = new THREE.EffectComposer(renderer);
          composer.setPixelRatio(Math.min((typeof window !== 'undefined' && window.devicePixelRatio) || 1, 2));
          composer.addPass(new THREE.RenderPass(scene, camera));
          const bw = wrap3d.clientWidth || 800, bh = Math.max(420, Math.round(bw * rows / cols));
          composer.addPass(new THREE.UnrealBloomPass(new THREE.Vector2(bw / 2, bh / 2), 0.5, 0.35, 0.95));
          // r147 has no OutputPass: GammaCorrection restores the sRGB look
          // the plain renderer gets from outputEncoding.
          composer.addPass(new THREE.ShaderPass(THREE.GammaCorrectionShader));
          composer.setSize(bw, bh);
        }
      } catch (err) { composer = null; }

      T = { THREE, renderer, scene, camera, controls, sun, composer, group: null, TEX: null,
        sky: { sunSprite, moonSprite, stars, hemi, dome: skyDome }, clouds: [], lamps: [], lampLights: [] };
      wrap3d._three = T; // handle for tests / debugging
      // Preload the CC0 model pack now (awaited: builders decide model vs
      // procedural at scene-build time). Slow/failed loads fall back silently.
      try { await preloadModels(THREE); } catch (err) { /* procedural fallback */ }
      T.modelsReady = true; // for tests / screenshot waits
      sizeThree();
      return T;
    }

    function sizeThree() {
      if (!T) return;
      const w = wrap3d.clientWidth || 800;
      const h = Math.max(420, Math.round(w * rows / cols));
      T.renderer.setSize(w, h);
      if (T.composer) T.composer.setSize(w, h);
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

    /* ---------------- CC0 model pack (v2.62.0) ---------------- */
    // Curated Kenney / Quaternius GLBs in /static/models (all CC0). Loaded
    // once in ensureThree; every builder below falls back to its procedural
    // version when a model is missing or fails. Clones share the cached
    // geometry/materials, so a missing/broken GLB can never break the scene.
    const MODEL_BASE = '/static/models/';
    const MODEL_FILES = [
      'kenney_tree_oak', 'kenney_tree_detailed', 'kenney_tree_small',
      'kenney_plant_bush', 'kenney_plant_bushDetailed', 'kenney_plant_bushSmall',
      'kenney_flower_redA', 'kenney_flower_redB', 'kenney_flower_yellowA',
      'kenney_flower_yellowB', 'kenney_flower_purpleA', 'kenney_flower_purpleB',
      'kenney_grass', 'kenney_grass_large', 'kenney_grass_leafs',
      'kenney_rock_smallA', 'kenney_rock_largeA',
      'kenney_fence_planks', 'kenney_fence_planksDouble', 'kenney_fence_gate',
      'kenney_fence_corner', 'kenney_fence_simple',
      'kenney_path_stone', 'kenney_path_stoneCircle', 'kenney_path_wood', 'kenney_path_woodEnd',
      'kenney_sign', 'kenney_pot_large', 'kenney_pot_small',
      'kenney_mushroom_red', 'kenney_mushroom_redGroup', 'kenney_mushroom_tan',
      'kenney_log_stack',
      'kenney_crop_carrot', 'kenney_crop_melon', 'kenney_crop_pumpkin', 'kenney_crop_turnip',
      'kenney_crops_cornStageA', 'kenney_crops_cornStageB', 'kenney_crops_cornStageC', 'kenney_crops_cornStageD',
      'kenney_crops_wheatStageA', 'kenney_crops_wheatStageB',
      'kenney_crops_leafsStageA', 'kenney_crops_leafsStageB',
      'kenney_crops_dirtRow', 'kenney_crops_dirtDoubleRow', 'kenney_crops_dirtSingle',
      'quaternius_tomato', 'quaternius_carrot', 'quaternius_corn',
      'quaternius_pumpkin', 'quaternius_pepper_green',
    ];
    const modelCache = {}; // name -> { obj, size }
    let modelsLoading = null;

    function preloadModels(THREE) {
      if (modelsLoading) return modelsLoading;
      modelsLoading = (async () => {
        if (!THREE || !THREE.GLTFLoader) return;
        const loader = new THREE.GLTFLoader();
        const loadOne = (name) => new Promise((resolve) => {
          let done = false;
          const finish = (ok) => { if (!done) { done = true; resolve(ok); } };
          try {
            loader.load(MODEL_BASE + name + '.glb',
              (gltf) => {
                try {
                  const obj = gltf.scene;
                  const box = new THREE.Box3().setFromObject(obj);
                  const size = new THREE.Vector3(); box.getSize(size);
                  if (!(size.y > 0)) return finish(false);
                  const c = new THREE.Vector3(); box.getCenter(c);
                  // normalize: centered in XZ, base sitting at y=0
                  obj.position.x -= c.x; obj.position.z -= c.z; obj.position.y -= box.min.y;
                  obj.traverse((o) => {
                    if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.userData.fromModel = true; }
                  });
                  modelCache[name] = { obj, size };
                  finish(true);
                } catch (e) { finish(false); }
              },
              undefined,
              () => finish(false));
          } catch (e) { finish(false); }
          setTimeout(() => finish(false), 12000); // per-model cap
        });
        const all = Promise.allSettled(MODEL_FILES.map(loadOne));
        const timeout = new Promise((r) => setTimeout(r, 20000)); // overall cap
        await Promise.race([all, timeout]);
      })();
      return modelsLoading;
    }

    // Clone a cached model into the scene. Returns null when unavailable —
    // callers MUST fall back to procedural building.
    // opts: { height } fit bbox height | { scale } | { scaleXYZ:[x,y,z] },
    //   { rotY }, { pos:[x,y,z] }, { plantingId } (build-mode breaking),
    //   { ownMaterials } (ghost preview: private materials so the green/red
    //   tint never touches the shared cache).
    function spawnModel(name, opts) {
      const t = modelCache[name];
      if (!t || !t.obj) return null;
      opts = opts || {};
      const m = t.obj.clone(true);
      if (opts.height) m.scale.setScalar(opts.height / (t.size.y || 1));
      else if (opts.scaleXYZ) m.scale.set(opts.scaleXYZ[0], opts.scaleXYZ[1], opts.scaleXYZ[2]);
      else if (opts.scale) m.scale.setScalar(opts.scale);
      if (opts.rotY) m.rotation.y = opts.rotY;
      if (opts.pos) m.position.set(opts.pos[0], opts.pos[1], opts.pos[2]);
      m.traverse((o) => {
        if (!o.isMesh) return;
        o.userData.fromModel = true;
        if (opts.ownMaterials) {
          o.material = Array.isArray(o.material) ? o.material.map((x) => x.clone()) : o.material.clone();
        }
      });
      if (opts.plantingId != null) m.userData.plantingId = opts.plantingId;
      return m;
    }

    // Pure: 0..1 growth progress from planting dates, null when unknown.
    function growthProgress(p) {
      if (!p || !p.date_planted || !p.days_to_maturity) return null;
      const start = new Date(p.date_planted + 'T12:00:00');
      const dtm = Number(p.days_to_maturity);
      if (isNaN(start.getTime()) || !(dtm > 0)) return null;
      return Math.max(0, Math.min(1, (Date.now() - start.getTime()) / 86400000 / dtm));
    }
    // Pure: 0..3 growth stage (A..D). Unknown dates -> mid stage.
    function growthStage(p) {
      const pr = growthProgress(p);
      if (pr == null) return 1;
      if (pr < 0.3) return 0;
      if (pr < 0.55) return 1;
      if (pr < 0.8) return 2;
      return 3;
    }
    // Pure: Kenney crop-plant model for a species + stage. Null = no model
    // fits (caller falls back to the procedural plant).
    function cropModelFor(species, stage) {
      const s = (species || '').toLowerCase();
      const st = Math.max(0, Math.min(3, stage == null ? 1 : stage));
      const ab = st >= 2 ? 'B' : 'A';
      if (/corn|maize/.test(s)) return 'kenney_crops_cornStage' + 'ABCD'[st];
      if (/carrot/.test(s)) return 'kenney_crop_carrot';
      if (/melon|cantaloupe|watermelon/.test(s)) return 'kenney_crop_melon';
      if (/pumpkin|squash|zucchini|gourd/.test(s)) return 'kenney_crop_pumpkin';
      if (/turnip|beet|radish|rutabaga|parsnip/.test(s)) return 'kenney_crop_turnip';
      if (/wheat|oat|barley|rye|sorghum|grain|rice/.test(s)) return 'kenney_crops_wheatStage' + ab;
      if (/lettuce|spinach|kale|arugula|chard|basil|herb|mint|cilantro|parsley|dill|bok\s?choy|cabbage|broccoli|cauliflower|celery|onion|garlic|leek|collard/.test(s)) return 'kenney_crops_leafsStage' + ab;
      return null;
    }
    // Pure: Quaternius produce marker for harvest-ready plantings. Null = skip.
    function produceModelFor(species) {
      const s = (species || '').toLowerCase();
      if (/tomato/.test(s)) return 'quaternius_tomato';
      if (/carrot/.test(s)) return 'quaternius_carrot';
      if (/corn|maize/.test(s)) return 'quaternius_corn';
      if (/pumpkin|squash|zucchini|gourd/.test(s)) return 'quaternius_pumpkin';
      if (/pepper|paprika/.test(s)) return 'quaternius_pepper_green';
      return null;
    }
    // Target display heights (ft) for crop models in beds.
    const CROP_HEIGHTS = {
      kenney_crops_cornStageA: 0.8, kenney_crops_cornStageB: 1.3,
      kenney_crops_cornStageC: 1.7, kenney_crops_cornStageD: 2.0,
      kenney_crop_carrot: 0.85, kenney_crop_melon: 0.6, kenney_crop_pumpkin: 0.6,
      kenney_crop_turnip: 0.9,
      kenney_crops_leafsStageA: 0.65, kenney_crops_leafsStageB: 1.0,
      kenney_crops_wheatStageA: 0.6, kenney_crops_wheatStageB: 0.95,
    };

    // Build (and cache on T) the shared pixel textures for one scene build.
    function buildTextures(THREE) {
      const S = 64; // soft miniature textures
      const TEX = {};
      TEX.grass = makePixTexture(THREE, S, paintGrass, 11, [cols + 8, rows + 8]);
      TEX.groundSide = makePixTexture(THREE, S, paintGroundSide, 12);
      TEX.soil = makePixTexture(THREE, S, paintSoil, 17);
      TEX.wood = makePixTexture(THREE, S, paintWood, 15);
      TEX.darkWood = makePixTexture(THREE, S, paintDarkWood, 16);
      TEX.lightWood = makePixTexture(THREE, S, paintLightWood, 161);
      TEX.fabric = makePixTexture(THREE, S, paintFabric, 18);
      TEX.terracotta = makePixTexture(THREE, S, paintTerracotta, 19);
      TEX.metal = makePixTexture(THREE, S, paintMetal, 22);
      TEX.wireMesh = makePixTexture(THREE, S, paintWireMesh, 23, [1, 1]); // [1,1] enables RepeatWrapping for UV tiling
      TEX.bucket = makePixTexture(THREE, S, paintBucket, 24);
      TEX.stone = makePixTexture(THREE, S, paintStone, 25);
      TEX.barrel = makePixTexture(THREE, S, paintBarrel, 26);
      TEX.compost = makePixTexture(THREE, S, paintCompost, 27);
      TEX.hoopPlastic = makePixTexture(THREE, S, paintHoopPlastic, 28);
      TEX.basin = makePixTexture(THREE, S, paintBasin, 29);
      TEX.leaf = makePixTexture(THREE, S, paintLeaf, 30);
      TEX.grassTuft = makePixTexture(THREE, S, paintGrassTuft, 31);
      TEX.flowerRed = makePixTexture(THREE, S, (ctx, Sd) => paintWildflower(ctx, Sd, mulberry32(101), 0), 32);
      TEX.flowerYellow = makePixTexture(THREE, S, (ctx, Sd) => paintWildflower(ctx, Sd, mulberry32(102), 1), 33);
      TEX.flowerWhite = makePixTexture(THREE, S, (ctx, Sd) => paintWildflower(ctx, Sd, mulberry32(103), 2), 34);
      return TEX;
    }

    function box(THREE, w, h, d, mat) {
      return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    }
    function ball(THREE, r, mat, detail) {
      return new THREE.Mesh(new THREE.IcosahedronGeometry(r, detail == null ? 1 : detail), mat);
    }
    function cyl(THREE, rt, rb, h, mat, seg) {
      return new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg || 20), mat);
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
        // v2.62.0: Kenney hexagonal planter; terracotta fallback below.
        const pm = spawnModel('kenney_pot_small', { height: 0.85 });
        if (pm) { g.add(pm); g.userData.topY = 0.85; return; }
        // smooth tapered terracotta pot + rim + soil
        const s = Math.max(0.6, Math.min(w, h) * 0.7);
        const body = cyl(THREE, s * 0.52, s * 0.4, bodyH, pixMaterial(THREE, TEX.terracotta));
        body.position.y = bodyH / 2;
        g.add(body);
        const rimMat = new THREE.MeshStandardMaterial({ color: 0xd98a5a, roughness: 0.85, metalness: 0 });
        const rim = cyl(THREE, s * 0.58, s * 0.56, 0.18, rimMat);
        rim.position.y = bodyH - 0.09;
        g.add(rim);
        const soil = cyl(THREE, s * 0.46, s * 0.46, 0.08, soilMat, 16);
        soil.position.y = bodyH - 0.1;
        soil.receiveShadow = true;
        g.add(soil);
      } else if (kind === 'grow bag') {
        // soft fabric form with a folded cuff
        const body = box(THREE, w * 0.94, bodyH, h * 0.94, pixMaterial(THREE, TEX.fabric));
        body.position.y = bodyH / 2;
        g.add(body);
        const cuff = box(THREE, w * 0.94 + 0.06, 0.16, h * 0.94 + 0.06, pixMaterial(THREE, TEX.fabric));
        cuff.position.y = bodyH - 0.08;
        g.add(cuff);
        const soil = box(THREE, w * 0.94 - 0.2, 0.1, h * 0.94 - 0.2, soilMat);
        soil.position.y = bodyH - 0.12;
        soil.receiveShadow = true;
        g.add(soil);
      } else {
        // wooden box + rim boards + soil inset, soft grain
        const bw = w * 0.98, bd = h * 0.98;
        const body = box(THREE, bw, bodyH, bd, woodMat);
        body.position.y = bodyH / 2;
        g.add(body);
        const rimMat = pixMaterial(THREE, TEX.lightWood); // lighter rim so the form reads
        const rimH = 0.14, rimT = 0.18;
        [[0, 1, bw + 0.1, rimT], [0, -1, bw + 0.1, rimT]].forEach(([x, s, rw, rd]) => {
          const rim = box(THREE, rw, rimH, rd, rimMat);
          rim.position.set(x, bodyH - rimH / 2 + 0.02, s * (bd / 2 - rimT / 2 + 0.04));
          g.add(rim);
        });
        [[1, 0], [-1, 0]].forEach(([s]) => {
          const rim = box(THREE, rimT, rimH, bd + 0.1, rimMat);
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

    // ---- arch geometry (pure helpers; also exposed to tests) ----
    function archArcPoint(span, height, t) {
      // t in [0,1] along a half-ellipse from one ground foot to the other
      const th = Math.PI * t;
      return { x: (span / 2) * Math.cos(th), y: height * Math.sin(th) };
    }
    function archRibCount(len) {
      return Math.max(5, Math.min(7, Math.round(len * 1.25)));
    }

    // Pure: height of a real 16ft cattle panel bent into an arch of `span`
    // feet. The arc length is fixed at 16ft, so H is solved from the
    // half-ellipse perimeter (Ramanujan) via bisection, then clamped to a
    // sane walk-through range.
    function cattlePanelHeight(span) {
      const a = Math.max(0.5, span) / 2;
      const arcLen = (b) => Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b))) / 2;
      let lo = 0.5, hi = 14;
      for (let i = 0; i < 48; i++) {
        const m = (lo + hi) / 2;
        if (arcLen(m) < 16) lo = m; else hi = m;
      }
      return Math.min(8.5, Math.max(4, (lo + hi) / 2));
    }

    function buildArch(THREE, g, w, h, height, TEX, opts) {
      // Soft garden archway: smooth half-ellipse tube ribs + fine wire mesh
      // (or translucent plastic for the hoop-house variant). Vines are soft
      // leaf blobs hugging the ribs. Walk-under-able: no collision.
      opts = opts || {};
      // A real 16ft cattle panel bent into an arch gives a ~4ft-wide,
      // ~7ft-tall walk-through. If the footprint's short side is narrower
      // than a usable walk-through, flip the arch: the profile crosses the
      // LONG side, so a narrow footprint becomes a short archway instead of
      // a long, thin, unusable tunnel.
      const narrow = Math.min(w, h) < 3.5;
      const span = narrow ? Math.max(w, h) : Math.min(w, h);
      const len = narrow ? Math.min(w, h) : Math.max(w, h);
      const spanAlongX = narrow ? w >= h : w <= h; // rib arcs live in the X-Y plane when the profile crosses x
      // Height comes from the panel, not a free parameter: a 16ft cattle
      // panel bent to `span` width. Solve the half-ellipse arc length = 16
      // for H (Ramanujan perimeter, bisection). An explicit height_ft still
      // wins when the user set one.
      const H = +height > 0 ? +height : cattlePanelHeight(span);
      const metalMat = new THREE.MeshStandardMaterial({
        // flat galvanized gray — no dark map, low metalness (no envmap in the
        // scene, so high metalness would render near-black)
        color: 0x9aa3a8, roughness: 0.5, metalness: 0.25,
      });
      const leafMat = new THREE.MeshStandardMaterial({ color: 0x43a53b, roughness: 0.9, metalness: 0 });
      const meshMat = opts.plastic
        ? new THREE.MeshStandardMaterial({
            map: TEX.hoopPlastic, transparent: true, opacity: 0.42, side: THREE.DoubleSide,
            roughness: 0.35, metalness: 0, depthWrite: false,
          })
        : new THREE.MeshStandardMaterial({
            map: TEX.wireMesh, alphaTest: 0.4, side: THREE.DoubleSide,
            roughness: 0.5, metalness: 0.15,
          });

      // Real cattle panels are 16ft x 50in: a long tunnel is built from
      // multiple panels side by side, not one stretched sheet. Panel-ize the
      // tunnel (~4ft panels with a small gap) so first person reads a series
      // of proper arches instead of a long thin tube. Each panel is ~5ft wide
      // at the feet and ~7ft at the crown, like a real bent panel.
      const R = span / 2;
      const PANEL = 4, GAP = opts.plastic ? 0 : 0.22;
      const nPanels = Math.max(1, Math.round(len / PANEL));
      const bounds = [];
      for (let pi = 0; pi <= nPanels; pi++) bounds.push(-len / 2 + (pi * len) / nPanels);
      // ribs at every panel boundary + one mid-rib per panel
      const ribOffs = [];
      bounds.forEach((b, i) => {
        ribOffs.push(b);
        if (i < nPanels) ribOffs.push((b + bounds[i + 1]) / 2);
      });
      const addRib = (off) => {
        const rib = new THREE.Mesh(new THREE.TorusGeometry(R, 0.13, 12, 40, Math.PI), metalMat);
        rib.scale.y = H / R; // circle -> half-ellipse with crown H
        if (spanAlongX) rib.position.set(0, 0, off);
        else { rib.rotation.y = Math.PI / 2; rib.position.set(off, 0, 0); }
        g.add(rib);
      };
      ribOffs.forEach(addRib);

      // Wire-mesh / plastic skin: one curved ribbon per panel (gaps only for
      // wire — a hoop house keeps one continuous plastic sheet).
      const M = 28;
      const GRID = 0.5; // mesh cell size: finer reads better up close
      for (let pi = 0; pi < nPanels; pi++) {
        const p0 = bounds[pi] + (pi > 0 ? GAP / 2 : 0);
        const p1 = bounds[pi + 1] - (pi < nPanels - 1 ? GAP / 2 : 0);
        const pos = [], uv = [], idx = [];
        const uRep = Math.max(1, Math.round((p1 - p0) / GRID));
        const vRep = Math.max(2, Math.round((Math.PI * (span / 2 + H)) / 2 / GRID));
        for (let j = 0; j <= M; j++) {
          const p = archArcPoint(span, H, j / M);
          const v = (j / M) * vRep;
          if (spanAlongX) { pos.push(p.x, p.y, p0, p.x, p.y, p1); }
          else { pos.push(p0, p.y, p.x, p1, p.y, p.x); }
          uv.push(0, v, uRep, v);
        }
        for (let j = 0; j < M; j++) {
          const a = j * 2, b = a + 1, c = a + 2, d = a + 3;
          idx.push(a, b, c, b, d, c);
        }
        const skinGeo = new THREE.BufferGeometry();
        skinGeo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
        skinGeo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
        skinGeo.setIndex(idx);
        skinGeo.computeVertexNormals();
        const skin = new THREE.Mesh(skinGeo, meshMat);
        skin.userData.noShadow = true; // alpha-tested mesh would cast a solid blob shadow
        g.add(skin);
      }

      // Soft leaf blobs hugging the ribs (seeded = stable). Skipped for the
      // plastic hoop-house variant (clean greenhouse look).
      const rng = mulberry32((w * 131 + h * 17 + ((g.userData.containerId || 0) * 7)) | 0);
      if (!opts.plastic) {
        const blobGeo = new THREE.IcosahedronGeometry(0.24, 1);
        const vineRibs = new Set();
        while (vineRibs.size < Math.min(3, ribOffs.length)) vineRibs.add((rng() * ribOffs.length) | 0);
        vineRibs.forEach((r) => {
          const off = ribOffs[r];
          const n = 3 + ((rng() * 3) | 0);
          for (let i = 0; i < n; i++) {
            const t = Math.min(0.95, 0.08 + (0.84 * (i + rng() * 0.6)) / n);
            const p = archArcPoint(span, H, t);
            const b = new THREE.Mesh(blobGeo, leafMat);
            const s = 0.7 + rng() * 0.7;
            b.scale.set(s, s * 0.8, s);
            if (spanAlongX) b.position.set(p.x, p.y + 0.12, off);
            else b.position.set(off, p.y + 0.12, p.x);
            b.userData.noShadow = true;
            g.add(b);
          }
        });
      }
      g.userData.topY = H;
    }

    // ---- World dressing: lamp posts, chain-link fence, buckets, path slabs ----
    // Pure: which of the 4 sides of the fence cell (gx,gy) touch another fence
    // cell. cellSet holds "gx,gy" strings for every cell covered by a fence.
    function fenceSides(gx, gy, cellSet) {
      return {
        n: cellSet.has(`${gx},${gy - 1}`),
        s: cellSet.has(`${gx},${gy + 1}`),
        w: cellSet.has(`${gx - 1},${gy}`),
        e: cellSet.has(`${gx + 1},${gy}`),
      };
    }
    // Pure: set of "gx,gy" cells covered by fence containers. Fence gates
    // count too, so a gate dropped into a fence run meshes both ways.
    function fenceCells(list) {
      return kindCells(list, ['fence', 'fence gate']);
    }
    // Pure: generic version — set of "gx,gy" cells covered by containers
    // whose kind is in the given list.
    function kindCells(list, kinds) {
      const set = new Set();
      (list || []).forEach((c) => {
        const k = c.kind || '';
        if (!kinds.includes(k)) return;
        const w = c.grid_w || 1, h = c.grid_h || 1;
        for (let dx = 0; dx < w; dx++) for (let dy = 0; dy < h; dy++) set.add(`${(c.grid_x || 0) + dx},${(c.grid_y || 0) + dy}`);
      });
      return set;
    }
    // Pure: stone edging and drip-line connection sets (fenceSides works on any).
    function edgingCells(list) { return kindCells(list, ['stone edging']); }
    function dripCells(list) { return kindCells(list, ['drip line']); }
    // Pure: ids of the n lamps nearest to (cx,cz). Lamp glow is capped for perf.
    function nearestLampIds(lamps, cx, cz, n) {
      return (lamps || [])
        .map((l, i) => ({ i, d: (l.x - cx) * (l.x - cx) + (l.z - cz) * (l.z - cz) }))
        .sort((a, b) => a.d - b.d)
        .slice(0, n)
        .map((o) => o.i);
    }


    function buildLamp(THREE, g, w, h, TEX) {
      // Short dark post + warm glowing globe.
      const post = cyl(THREE, 0.09, 0.11, 1.5, pixMaterial(THREE, TEX.metal));
      post.position.y = 0.75;
      g.add(post);
      const headMat = new THREE.MeshStandardMaterial({
        color: 0xffc46b, emissive: 0xff9d2e, emissiveIntensity: 0.15,
        roughness: 0.6, metalness: 0,
      });
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.3, 16, 12), headMat);
      head.position.y = 1.72;
      head.userData.lampHead = true;
      head.userData.noShadow = true;
      g.add(head);
      const cap = cyl(THREE, 0.36, 0.3, 0.12, pixMaterial(THREE, TEX.metal));
      cap.position.y = 2.05;
      g.add(cap);
      g.userData.topY = 2.15;
      g.userData.lampPos = { x: 0, y: 1.72, z: 0 }; // local; scene build converts to world
    }

    function buildFence(THREE, g, w, h, TEX, sides) {
      // v2.62.0: Kenney wooden picket models. An L-corner piece joins exactly
      // two perpendicular runs (rotY mapped from the model's +x/-z arms);
      // otherwise short rail stubs run from the center post to each neighbor.
      // Falls back to the procedural chain-link below when models are missing.
      sides = sides || {};
      const has = (k) => !!sides[k];
      const n = has('n'), s = has('s'), e = has('e'), wSide = has('w');
      const count = (n ? 1 : 0) + (s ? 1 : 0) + (e ? 1 : 0) + (wSide ? 1 : 0);
      let modeled = false;
      const cornerRot = { ne: 0, es: -Math.PI / 2, sw: Math.PI, wn: Math.PI / 2 };
      if (count === 2) {
        const key = (n && e) ? 'ne' : (e && s) ? 'es' : (s && wSide) ? 'sw' : (wSide && n) ? 'wn' : null;
        if (key) {
          const cm = spawnModel('kenney_fence_corner', { rotY: cornerRot[key] });
          if (cm) { g.add(cm); modeled = true; }
        }
      }
      const stub = (px, pz, rotY) => {
        const m = spawnModel('kenney_fence_planksDouble', { scaleXYZ: [0.55, 1, 1], rotY });
        if (m) { m.position.set(px, 0, pz); g.add(m); return true; }
        return false;
      };
      if (!modeled) {
        if (count === 0) {
          // lone fence cell: one full picket section
          const m = spawnModel('kenney_fence_planksDouble', { scaleXYZ: [1, 1.4, 1] });
          if (m) { g.add(m); modeled = true; }
        } else {
          if (n) modeled = stub(0, -0.26, Math.PI / 2) || modeled;
          if (s) modeled = stub(0, 0.26, Math.PI / 2) || modeled;
          if (wSide) modeled = stub(-0.26, 0, 0) || modeled;
          if (e) modeled = stub(0.26, 0, 0) || modeled;
        }
      }
      if (modeled) {
        // slim center post anchors the rails
        const post = cyl(THREE, 0.07, 0.09, 0.5, pixMaterial(THREE, TEX.darkWood));
        post.position.y = 0.25;
        g.add(post);
        g.userData.topY = 0.5;
        return;
      }
      // Chain-link: round center post + fine mesh planes only on sides
      // facing another fence segment. Single fence = just a post.
      sides = sides || {};
      const post = cyl(THREE, 0.1, 0.12, 1.1, pixMaterial(THREE, TEX.metal));
      post.position.y = 0.55;
      g.add(post);
      const meshMat = new THREE.MeshStandardMaterial({
        map: TEX.wireMesh, alphaTest: 0.4, side: THREE.DoubleSide,
        roughness: 0.7, metalness: 0.4, transparent: false,
      });
      const mkPanel = (pw, px, pz, rotY) => {
        const p = new THREE.Mesh(new THREE.PlaneGeometry(pw, 0.9), meshMat);
        p.position.set(px, 0.6, pz);
        p.rotation.y = rotY;
        p.userData.noShadow = true;
        g.add(p);
      };
      // panels span half a cell from the post to each connected neighbor
      if (sides.n) mkPanel(0.5, 0, -0.25, 0);
      if (sides.s) mkPanel(0.5, 0, 0.25, 0);
      if (sides.w) mkPanel(0.5, -0.25, 0, Math.PI / 2);
      if (sides.e) mkPanel(0.5, 0.25, 0, Math.PI / 2);
      g.userData.topY = 1.1;
    }

    function buildBucket(THREE, g, TEX) {
      // White 5-gal bucket: smooth tapered cylinder + rim + handle arc.
      const body = cyl(THREE, 0.42, 0.34, 0.85, pixMaterial(THREE, TEX.bucket), 20);
      body.position.y = 0.425;
      g.add(body);
      const rim = cyl(THREE, 0.45, 0.45, 0.1, pixMaterial(THREE, TEX.bucket), 20);
      rim.position.y = 0.85;
      g.add(rim);
      const handle = new THREE.Mesh(
        new THREE.TorusGeometry(0.4, 0.045, 8, 20, Math.PI),
        pixMaterial(THREE, TEX.metal)
      );
      handle.position.y = 0.9;
      handle.userData.noShadow = true;
      g.add(handle);
      g.userData.topY = 1.35;
    }

    function buildPath(THREE, g, TEX) {
      // v2.62.0: Kenney stone tile (reads as a stepping stone). Slight
      // deterministic rotation so runs don't look stamped. Slab fallback below.
      const m = spawnModel('kenney_path_stone', { scale: 1 });
      if (m) {
        m.rotation.y = (((g.userData.containerId || 0) % 4) * 0.09);
        g.add(m); g.userData.topY = 0.1; return;
      }
      // Flat stone slab for walkways. No collider (walked over).
      const slab = box(THREE, 0.96, 0.15, 0.96, pixMaterial(THREE, TEX.stone));
      slab.position.y = 0.075;
      slab.receiveShadow = true;
      g.add(slab);
      g.userData.topY = 0.15;
    }

    function buildRainBarrel(THREE, g, TEX) {
      // Blue rain barrel: smooth cylinder body, lid, spigot near base.
      const body = cyl(THREE, 0.44, 0.4, 1.6, pixMaterial(THREE, TEX.barrel), 20);
      body.position.y = 0.8;
      g.add(body);
      const lid = cyl(THREE, 0.47, 0.47, 0.12, pixMaterial(THREE, TEX.metal), 20);
      lid.position.y = 1.66;
      g.add(lid);
      const spigot = cyl(THREE, 0.08, 0.08, 0.3, pixMaterial(THREE, TEX.metal), 10);
      spigot.rotation.x = Math.PI / 2;
      spigot.position.set(0, 0.35, 0.48);
      g.add(spigot);
      g.userData.topY = 1.75;
    }

    function buildCompostBin(THREE, g, TEX) {
      // Dark compost cube with a slightly ajar lid.
      const mat = pixMaterial(THREE, TEX.compost);
      const body = box(THREE, 0.95, 0.95, 0.95, mat);
      body.position.y = 0.475;
      g.add(body);
      const lid = box(THREE, 1.0, 0.12, 1.0, pixMaterial(THREE, TEX.darkWood));
      lid.position.y = 1.0;
      lid.rotation.z = 0.06; // slightly ajar, like it's in use
      g.add(lid);
      g.userData.topY = 1.1;
    }

    function buildHoopHouse(THREE, g, w, h, height, TEX) {
      // Bigger cousin of the garden arch: smooth tube ribs + translucent
      // plastic skin. Solid in v1 (no walking inside — see walkColliders).
      buildArch(THREE, g, w, h, height || KIND_HEIGHT['hoop house'] || 6, TEX, { plastic: true });
      // end-wall footings so it reads as a structure, not a tunnel
      const metalMat = pixMaterial(THREE, TEX.metal);
      const span = Math.min(w, h), len = Math.max(w, h);
      const H = Math.max(1.5, height || KIND_HEIGHT['hoop house'] || 6);
      const p0 = archArcPoint(span, H, 0), p1 = archArcPoint(span, H, 1);
      [[-len / 2], [len / 2]].forEach(([off]) => {
        const foot1 = cyl(THREE, 0.09, 0.11, 1.2, metalMat);
        const foot2 = cyl(THREE, 0.09, 0.11, 1.2, metalMat);
        if (w <= h) { foot1.position.set(p0.x, 0.6, off); foot2.position.set(p1.x, 0.6, off); }
        else { foot1.position.set(off, 0.6, p0.x); foot2.position.set(off, 0.6, p1.x); }
        g.add(foot1, foot2);
      });
    }

    function buildFenceGate(THREE, g, w, h, TEX, sides) {
      // v2.62.0: Kenney gate model (1x1 cell). Neighboring runs' stubs reach
      // the shared edge, so no connectors needed. Procedural fallback below.
      const gm = spawnModel('kenney_fence_gate', { scale: 1 });
      if (gm) { g.add(gm); g.userData.topY = 0.6; return; }
      // 1x1 chain-link gate: round frame posts + fine mesh panel + handle.
      // Auto-connects visually to adjacent fence segments via fenceSides.
      sides = sides || {};
      const metalMat = pixMaterial(THREE, TEX.metal);
      const meshMat = new THREE.MeshStandardMaterial({
        map: TEX.wireMesh, alphaTest: 0.4, side: THREE.DoubleSide,
        roughness: 0.7, metalness: 0.4,
      });
      const post1 = cyl(THREE, 0.09, 0.11, 1.15, metalMat);
      post1.position.set(-0.42, 0.575, 0);
      const post2 = cyl(THREE, 0.09, 0.11, 1.15, metalMat);
      post2.position.set(0.42, 0.575, 0);
      g.add(post1, post2);
      const panel = new THREE.Mesh(new THREE.PlaneGeometry(0.72, 0.85), meshMat);
      panel.position.set(0, 0.6, 0);
      panel.userData.noShadow = true;
      g.add(panel);
      const handle = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), pixMaterial(THREE, TEX.darkWood));
      handle.position.set(0.28, 0.62, 0.08);
      g.add(handle);
      // connect to neighboring fence runs on the gate's long axis sides
      const fc = sides;
      const mkPanel = (pw, px, pz, rotY) => {
        const p = new THREE.Mesh(new THREE.PlaneGeometry(pw, 0.85), meshMat);
        p.position.set(px, 0.6, pz);
        p.rotation.y = rotY;
        p.userData.noShadow = true;
        g.add(p);
      };
      if (fc.n) mkPanel(0.5, 0, -0.25, 0);
      if (fc.s) mkPanel(0.5, 0, 0.25, 0);
      if (fc.w) mkPanel(0.5, -0.25, 0, Math.PI / 2);
      if (fc.e) mkPanel(0.5, 0.25, 0, Math.PI / 2);
      g.userData.topY = 1.15;
    }

    function buildBirdBath(THREE, g, TEX) {
      // Stone pedestal + wide shallow basin + water disc.
      const stoneMat = pixMaterial(THREE, TEX.basin);
      const base = cyl(THREE, 0.28, 0.34, 0.18, stoneMat, 16);
      base.position.y = 0.09;
      const stem = cyl(THREE, 0.14, 0.18, 0.7, stoneMat, 14);
      stem.position.y = 0.53;
      const basin = cyl(THREE, 0.55, 0.4, 0.25, stoneMat, 18);
      basin.position.y = 1.0;
      g.add(base, stem, basin);
      const water = cyl(THREE, 0.46, 0.46, 0.04,
        new THREE.MeshStandardMaterial({ color: 0x4fa3d8, transparent: true, opacity: 0.75, roughness: 0.15, metalness: 0 }), 18);
      water.position.y = 1.1;
      water.userData.noShadow = true;
      g.add(water);
      g.userData.topY = 1.15;
    }

    function buildFruitTree(THREE, g, TEX) {
      // v2.62.0: Kenney oak model; procedural apple tree is the fallback.
      const m = spawnModel('kenney_tree_oak', { height: 3.6 });
      if (m) { g.add(m); g.userData.topY = 3.6; return; }
      // Apple tree: round trunk + soft canopy blobs + little apples.
      const barkMat = pixMaterial(THREE, TEX.darkWood);
      const trunk = cyl(THREE, 0.16, 0.22, 1.7, barkMat, 12);
      trunk.position.y = 0.85;
      g.add(trunk);
      const branch = cyl(THREE, 0.09, 0.12, 1.1, barkMat, 10);
      branch.rotation.z = Math.PI / 2 - 0.25;
      branch.position.set(0.3, 1.6, 0);
      g.add(branch);
      const leafMat = new THREE.MeshStandardMaterial({ color: 0x43a53b, roughness: 0.9, metalness: 0 });
      const blobGeo = new THREE.IcosahedronGeometry(1, 1);
      const rng = mulberry32(((g.userData.containerId || 1) * 31 + 7) | 0);
      const blobs = [
        [0, 2.6, 0, 1.5], [-0.85, 2.2, 0.3, 1.0], [0.85, 2.25, -0.25, 1.0],
        [0.15, 3.2, -0.3, 1.05], [-0.3, 2.9, 0.55, 0.9], [0.5, 2.0, 0.65, 0.8],
        [-0.55, 2.35, -0.6, 0.85],
      ];
      blobs.forEach(([x, y, z, s]) => {
        const b = new THREE.Mesh(blobGeo, leafMat);
        b.scale.set(s, s * 0.85, s);
        b.position.set(x, y, z);
        b.rotation.y = rng() * Math.PI;
        g.add(b);
      });
      const appleMat = new THREE.MeshStandardMaterial({ color: 0xe0301e, roughness: 0.45, metalness: 0 });
      for (let i = 0; i < 9; i++) {
        const a = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), appleMat);
        const th = rng() * Math.PI * 2, rr = 0.8 + rng() * 0.6;
        a.scale.setScalar(0.14 + rng() * 0.05);
        a.position.set(Math.cos(th) * rr, 2.1 + rng() * 1.2, Math.sin(th) * rr);
        a.userData.noShadow = true;
        g.add(a);
      }
      g.userData.topY = 3.8;
    }

    function buildShed(THREE, g, w, h, TEX) {
      // Small garden shed: plank walls, STEEP contrasting gable roof with
      // overhanging eaves, trimmed door, framed window. Must read as a shed
      // from the orbit angle, not a brown box.
      const woodMat = pixMaterial(THREE, TEX.wood);
      const darkMat = pixMaterial(THREE, TEX.darkWood);
      const trimMat = pixMaterial(THREE, TEX.lightWood);
      const walls = box(THREE, w - 0.15, 2.2, h - 0.15, woodMat);
      walls.position.y = 1.1;
      g.add(walls);
      // gable roof: steep pitch, dark contrasting slabs, generous eaves
      const L = Math.max(w, h), S = Math.min(w, h), apexH = 1.6;
      const roof = new THREE.Group();
      const slopeLen = Math.hypot(S / 2 + 0.35, apexH);
      const ang = Math.atan2(apexH, S / 2 + 0.35);
      const roofMat = new THREE.MeshStandardMaterial({ color: 0x4a3220, roughness: 0.95, metalness: 0 });
      [-1, 1].forEach((s) => {
        const slab = box(THREE, slopeLen + 0.15, 0.16, L + 0.5, roofMat);
        slab.position.set((s * S) / 4, 2.2 + apexH / 2, 0);
        slab.rotation.z = -s * ang;
        roof.add(slab);
      });
      const tri = new THREE.Shape();
      tri.moveTo(-S / 2, 0); tri.lineTo(S / 2, 0); tri.lineTo(0, apexH); tri.closePath();
      const gableGeo = new THREE.ShapeGeometry(tri);
      [-1, 1].forEach((s) => {
        const gable = new THREE.Mesh(gableGeo, new THREE.MeshStandardMaterial({
          map: TEX.wood, roughness: 0.9, metalness: 0, side: THREE.DoubleSide,
        }));
        gable.position.set(0, 2.2, s * (L / 2 - 0.08));
        roof.add(gable);
      });
      if (w < h) roof.rotation.y = Math.PI / 2;
      g.add(roof);
      // door with light trim frame
      const dz = h / 2;
      const door = box(THREE, 0.95, 1.75, 0.12, darkMat);
      door.position.set(-0.8, 0.88, dz - 0.02);
      g.add(door);
      [[-0.8 - 0.55, 0], [-0.8 + 0.55, 0]].forEach(([tx]) => {
        const jamb = box(THREE, 0.14, 1.9, 0.14, trimMat);
        jamb.position.set(tx, 0.95, dz + 0.02);
        g.add(jamb);
      });
      const lintel = box(THREE, 1.24, 0.14, 0.14, trimMat);
      lintel.position.set(-0.8, 1.88, dz + 0.02);
      g.add(lintel);
      const knob = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 8), pixMaterial(THREE, TEX.metal));
      knob.position.set(-0.48, 0.95, dz + 0.05);
      g.add(knob);
      // window with frame + cross mullions on the front wall
      const wx = 1.1, wy = 1.35;
      const frame = box(THREE, 0.9, 0.8, 0.1, trimMat);
      frame.position.set(wx, wy, dz - 0.02);
      g.add(frame);
      const pane = box(THREE, 0.72, 0.62, 0.12, new THREE.MeshStandardMaterial({ color: 0x9fc8e8, roughness: 0.25, metalness: 0.1 }));
      pane.position.set(wx, wy, dz - 0.01);
      g.add(pane);
      const mullV = box(THREE, 0.06, 0.62, 0.13, trimMat);
      mullV.position.set(wx, wy, dz);
      g.add(mullV);
      const mullH = box(THREE, 0.72, 0.06, 0.13, trimMat);
      mullH.position.set(wx, wy, dz);
      g.add(mullH);
      g.userData.topY = 3.9;
    }

    function buildPergola(THREE, g, w, h, TEX) {
      // Walk-under pergola: four round posts + beam + slat roof. No collider.
      const woodMat = pixMaterial(THREE, TEX.wood);
      const px = w / 2 - 0.18, pz = h / 2 - 0.18;
      [[-px, -pz], [px, -pz], [-px, pz], [px, pz]].forEach(([x, z]) => {
        const post = cyl(THREE, 0.13, 0.15, 2.5, woodMat, 12);
        post.position.set(x, 1.25, z);
        g.add(post);
      });
      [-px, px].forEach((x) => { // long beams along the h axis
        const beam = box(THREE, 0.24, 0.3, h, woodMat);
        beam.position.set(x, 2.62, 0);
        g.add(beam);
      });
      for (let i = 0; i < 6; i++) { // cross slats
        const slat = box(THREE, w, 0.14, 0.34, woodMat);
        slat.position.set(0, 2.85, -h / 2 + 0.3 + (i * (h - 0.6)) / 5);
        g.add(slat);
      }
      g.userData.topY = 3.0;
    }

    function buildEdging(THREE, g, w, h, TEX, sides) {
      // Low stone border wall: rounded post + low walls on sides facing
      // neighboring edging cells (fence-connect pattern).
      sides = sides || {};
      const stoneMat = pixMaterial(THREE, TEX.stone);
      const post = cyl(THREE, 0.16, 0.18, 0.52, stoneMat, 12);
      post.position.y = 0.26;
      g.add(post);
      const mkWall = (ww, wd, x, z) => {
        const m = box(THREE, ww, 0.4, wd, stoneMat);
        m.position.set(x, 0.2, z);
        g.add(m);
      };
      if (sides.n) mkWall(1.0, 0.3, 0, -0.35);
      if (sides.s) mkWall(1.0, 0.3, 0, 0.35);
      if (sides.w) mkWall(0.3, 1.0, -0.35, 0);
      if (sides.e) mkWall(0.3, 1.0, 0.35, 0);
      g.userData.topY = 0.55;
    }

    function buildSprinkler(THREE, g, TEX) {
      // Lawn sprinkler: dark post + head + smooth translucent water arc.
      const metalMat = pixMaterial(THREE, TEX.metal);
      const post = cyl(THREE, 0.08, 0.1, 0.55, metalMat, 10);
      post.position.y = 0.275;
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 10), metalMat);
      head.position.y = 0.62;
      g.add(post, head);
      const arc = new THREE.Mesh(
        new THREE.TorusGeometry(1.25, 0.09, 8, 24, Math.PI),
        new THREE.MeshStandardMaterial({ color: 0x77ccff, transparent: true, opacity: 0.5, roughness: 0.2, metalness: 0 })
      );
      arc.position.y = 0.68;
      arc.userData.noShadow = true;
      g.add(arc);
      g.userData.topY = 1.95;
    }

    function buildDripLine(THREE, g, w, h, TEX, sides) {
      // Thin black irrigation tube: center hub + tubes toward neighboring
      // drip cells (same connect pattern as fences), lying on the ground.
      sides = sides || {};
      const tubeMat = new THREE.MeshStandardMaterial({ color: 0x1c1c1c, roughness: 0.9, metalness: 0 });
      const hub = cyl(THREE, 0.18, 0.18, 0.16, tubeMat, 12);
      hub.position.y = 0.08;
      g.add(hub);
      const mkTube = (len, x, z, rotY) => {
        const t = cyl(THREE, 0.07, 0.07, len, tubeMat, 8);
        t.rotation.z = Math.PI / 2;
        const holder = new THREE.Group();
        holder.add(t);
        holder.rotation.y = rotY;
        holder.position.set(x, 0.065, z);
        g.add(holder);
      };
      if (sides.n) mkTube(0.55, 0, -0.28, Math.PI / 2);
      if (sides.s) mkTube(0.55, 0, 0.28, Math.PI / 2);
      if (sides.w) mkTube(0.55, -0.28, 0, 0);
      if (sides.e) mkTube(0.55, 0.28, 0, 0);
      g.userData.topY = 0.2;
    }

    // Pure: soft foliage cluster for a plant archetype + seed. Deterministic
    // so rebuilds are stable. Returns {blobs:[{dx,dy,dz,s}], fruits:[...]}.
    const PLANT_GREENS = {
      tomato: 0x43a53b, pepper: 0x359231, leafy: 0x55c04d,
      vine: 0x43a53b, flower: 0x4aa83c, generic: 0x43a53b,
    };
    function plantFoliage(arch, seed) {
      const rng = mulberry32(seed);
      const n = 3 + ((rng() * 3) | 0); // 3-5 blobs: fuller plants
      const blobs = [];
      for (let i = 0; i < n; i++) {
        blobs.push({
          dx: (rng() - 0.5) * 0.6,
          dy: 0.35 + rng() * 0.6,
          dz: (rng() - 0.5) * 0.6,
          s: 0.38 + rng() * 0.3,
        });
      }
      const fruits = [];
      if (arch === 'tomato' || arch === 'pepper') {
        const nf = 3 + ((rng() * 3) | 0);
        for (let i = 0; i < nf; i++) {
          fruits.push({
            dx: (rng() - 0.5) * 0.7, dy: 0.3 + rng() * 0.5, dz: (rng() - 0.5) * 0.7,
            s: 0.11 + rng() * 0.06, c: arch === 'tomato' ? 0xe0301e : 0xf07a1e,
          });
        }
      } else if (arch === 'flower') {
        const nf = 2 + ((rng() * 2) | 0);
        const cols = [0xe5321e, 0xffc21f, 0xffffff];
        for (let i = 0; i < nf; i++) {
          fruits.push({
            dx: (rng() - 0.5) * 0.5, dy: 0.7 + rng() * 0.35, dz: (rng() - 0.5) * 0.5,
            s: 0.1 + rng() * 0.05, c: cols[(rng() * cols.length) | 0],
          });
        }
      }
      return { blobs, fruits };
    }

    function buildPlantSoft(THREE, g, px, pz, baseY, species, seed, big, plantingId) {
      // Soft miniature plant: a small cluster of smooth-shaded foliage blobs,
      // with fruit spheres for fruiting archetypes. Seeded = stable layout.
      const arch = plantArchetype(species);
      const grp = new THREE.Group();
      const cluster = plantFoliage(arch, seed);
      const leafMat = new THREE.MeshStandardMaterial({
        color: PLANT_GREENS[arch] || 0x4e9e3f, roughness: 0.9, metalness: 0,
      });
      const blobGeo = new THREE.IcosahedronGeometry(1, 1);
      cluster.blobs.forEach((b) => {
        const m = new THREE.Mesh(blobGeo, leafMat);
        m.scale.set(b.s, b.s * 0.85, b.s);
        m.position.set(b.dx, b.dy, b.dz);
        m.userData.noShadow = true;
        grp.add(m);
      });
      const fruitGeo = new THREE.IcosahedronGeometry(1, 1);
      cluster.fruits.forEach((f) => {
        const m = new THREE.Mesh(fruitGeo, new THREE.MeshStandardMaterial({
          color: f.c, roughness: 0.55, metalness: 0,
        }));
        m.scale.setScalar(f.s);
        m.position.set(f.dx, f.dy, f.dz);
        m.userData.noShadow = true;
        grp.add(m);
      });
      if (plantingId != null) grp.userData.plantingId = plantingId; // build-mode breaking
      const rng = mulberry32(seed ^ 0x9e37);
      grp.rotation.y = rng() * Math.PI;
      const s = (big ? 1.5 : 1) * (0.9 + rng() * 0.3);
      grp.scale.set(s, s, s);
      grp.position.set(px, baseY - 0.05, pz);
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
      const baseY = (kind === 'arch' || kind === 'hoop house') ? 0 : (g.userData.topY || 1);
      const useModels = kind !== 'arch'; // arch keeps its procedural climbers
      spots.forEach(([spx, spz], i) => {
        const p = ps[i];
        const seed = (c.id * 1009 + i * 101) | 0;
        if (useModels) {
          const st = growthStage(p);
          const mf = cropModelFor(p && p.species_type, st);
          const rng = mulberry32(seed ^ 0x51f3);
          const m = mf && spawnModel(mf, {
            height: CROP_HEIGHTS[mf] || 0.8,
            rotY: rng() * Math.PI * 2,
            plantingId: p && p.id,
          });
          if (m) {
            m.position.set(spx, baseY - 0.03, spz);
            g.add(m);
            // tilled mound under each plant
            const mound = spawnModel('kenney_crops_dirtSingle', { height: 0.26, rotY: rng() * Math.PI });
            if (mound) { mound.position.set(spx, baseY - 0.02, spz); g.add(mound); }
            // harvest-ready produce marker beside the plant
            const pr = growthProgress(p);
            if (pr != null && pr >= 0.8) {
              const prod = produceModelFor(p && p.species_type);
              if (prod) {
                const pm = spawnModel(prod, { height: 0.34, rotY: rng() * Math.PI * 2 });
                if (pm) { pm.position.set(spx + 0.42, baseY, spz + 0.18); g.add(pm); }
              }
            }
            return;
          }
        }
        buildPlantSoft(THREE, g, spx, spz, baseY, p && p.species_type, seed, kind === 'arch', p && p.id);
      });
    }

    // Bed name-stake + deterministic corner decor (v2.62.0). Only for planted
    // vessels with room; skipped silently when models are unavailable.
    const VESSEL_KINDS = ['raised bed', 'grow bag', 'planter', 'pot'];
    const SCATTER_MODELS = [
      ['kenney_plant_bushSmall', 0.55], ['kenney_flower_redA', 0.5], ['kenney_flower_yellowA', 0.5],
      ['kenney_flower_purpleA', 0.5], ['kenney_grass', 0.45], ['kenney_rock_smallA', 0.3],
      ['kenney_mushroom_red', 0.35], ['kenney_mushroom_tan', 0.3],
    ];
    function addBedMarkerAndScatter(THREE, g, w, h, kind, c) {
      if (!VESSEL_KINDS.includes(kind)) return;
      if (!plantingsFor(c.id).length) return;
      if (Math.min(w, h) < 2) return;
      const topY = g.userData.topY || 1;
      const rng = mulberry32(((c.id * 2654435761) % 4294967296) | 0);
      // garden sign as a plant-label stake, front-right inside corner
      const sign = spawnModel('kenney_sign', { height: 1.15, rotY: 0.5 });
      if (sign) { sign.position.set(w / 2 - 0.4, topY - 0.12, h / 2 - 0.4); g.add(sign); }
      // 1-2 decor items at the remaining corners (seeded = stable)
      const corners = [[-1, -1], [-1, 1], [1, -1]];
      const n = 1 + Math.floor(rng() * 2);
      for (let i = 0; i < n && corners.length; i++) {
        const [sx, sz] = corners.splice(Math.floor(rng() * corners.length), 1)[0];
        const [mf, ht] = SCATTER_MODELS[Math.floor(rng() * SCATTER_MODELS.length)];
        const d = spawnModel(mf, { height: ht, rotY: rng() * Math.PI * 2 });
        if (d) { d.position.set(sx * (w / 2 - 0.35), topY - 0.05, sz * (h / 2 - 0.35)); g.add(d); }
      }
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
      // Soft miniature clouds: merged sphere clusters. They drift in
      // walk mode (see driftClouds); in orbit mode they stay static so the
      // on-demand renderer can sleep.
      T.clouds = [];
      const mat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.92 });
      for (let i = 0; i < 9; i++) {
        const cw = 9 + rng() * 9, cd = 6 + rng() * 6;
        const cloud = new THREE.Group();
        const n = 4 + ((rng() * 3) | 0);
        for (let j = 0; j < n; j++) {
          const r = 2.2 + rng() * 2.4;
          const puff = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 10), mat);
          puff.scale.y = 0.55;
          puff.position.set((rng() - 0.5) * cw, (rng() - 0.5) * 1.2, (rng() - 0.5) * cd);
          cloud.add(puff);
        }
        const ext = Math.max(cols, rows) / 2 + 14;
        cloud.position.set((rng() - 0.5) * ext * 2.6, 20 + rng() * 10, (rng() - 0.5) * ext * 2.6);
        cloud.traverse((o) => { o.castShadow = false; o.receiveShadow = false; });
        cloud.userData.drift = 0.5 + rng() * 0.5;
        cloud.userData.cloudMat = mat;
        group.add(cloud);
        T.clouds.push(cloud);
      }
    }

    // Called from the walk-mode loop only. Wraps clouds around the sky.
    function driftClouds(dt) {
      if (!T || !T.clouds) return;
      const ext = Math.max(cols, rows) / 2 + 14;
      T.clouds.forEach((c) => {
        c.position.x += (c.userData.drift || 0.6) * dt;
        if (c.position.x > ext * 1.6) c.position.x = -ext * 1.6;
      });
    }

    /* ---------------- meadow decor: tall grass + wildflowers, fireflies ---------------- */
    // Pure: set of "gx,gy" cells covered by any container (grass never grows there).
    const GRASS_SEED = 4242, GRASS_CAP = 320;
    function occupiedCellSet(list) {
      const set = new Set();
      (list || []).forEach((c) => {
        const w = c.grid_w || 1, h = c.grid_h || 1;
        for (let dx = 0; dx < w; dx++) for (let dy = 0; dy < h; dy++) set.add(`${(c.grid_x || 0) + dx},${(c.grid_y || 0) + dy}`);
      });
      return set;
    }
    // Pure: deterministic scatter of grass/flower tufts on empty cells.
    // Same seed -> same layout, so rebuilds are stable; capped for perf.
    // Cells adjacent to beds grow thicker — a natural clustered look.
    function grassLayout(ncols, nrows, occupied, seed) {
      const rng = mulberry32(seed == null ? GRASS_SEED : seed);
      const cells = [];
      const adj = (gx, gy) => occupied.has(`${gx - 1},${gy}`) || occupied.has(`${gx + 1},${gy}`) ||
        occupied.has(`${gx},${gy - 1}`) || occupied.has(`${gx},${gy + 1}`);
      for (let gx = 0; gx < ncols; gx++) {
        for (let gy = 0; gy < nrows; gy++) {
          if (occupied.has(`${gx},${gy}`)) continue;
          const r = rng();
          const p = adj(gx, gy) ? 0.74 : 0.55; // lush near beds
          if (r < p && cells.length < GRASS_CAP) {
            cells.push({
              gx, gy,
              variant: r < 0.36 ? 'tuft' : r < 0.44 ? 'flower-red' : r < 0.49 ? 'flower-yellow' : r < 0.53 ? 'flower-white' : 'tuft',
            });
          }
        }
      }
      return cells;
    }

    function buildGrass3D(THREE, decor, TEX) {
      // Cross-quad tufts, Minecraft tall-grass style. Decor layer: no shadows,
      // no collision, excluded from raycast targets (lives outside T.group).
      const jrng = mulberry32(GRASS_SEED + 1);
      const texFor = { tuft: TEX.grassTuft, 'flower-red': TEX.flowerRed, 'flower-yellow': TEX.flowerYellow, 'flower-white': TEX.flowerWhite };
      grassLayout(cols, rows, occupiedCellSet(containers), GRASS_SEED).forEach(({ gx, gy, variant }) => {
        const mat = new THREE.MeshBasicMaterial({ map: texFor[variant], alphaTest: 0.5, side: THREE.DoubleSide });
        const tuft = new THREE.Group();
        for (let k = 0; k < 2; k++) {
          const p = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.55), mat);
          p.rotation.y = (k * Math.PI) / 2 + jrng() * 0.6;
          p.position.y = 0.27;
          tuft.add(p);
        }
        tuft.position.set(gx + 0.5 - cols / 2 + (jrng() - 0.5) * 0.5, 0, gy + 0.5 - rows / 2 + (jrng() - 0.5) * 0.5);
        tuft.traverse((o) => { o.castShadow = false; o.receiveShadow = false; });
        decor.add(tuft);
      });
    }

    // Pure: one firefly's position at time t (gentle sin drift around its base).
    function fireflyPos(base, phase, t) {
      return {
        x: base.x + Math.sin(t * 0.7 + phase) * 0.6,
        y: base.y + Math.sin(t * 1.1 + phase * 1.7) * 0.35,
        z: base.z + Math.cos(t * 0.5 + phase) * 0.6,
      };
    }

    function buildFireflies(THREE) {
      // ~40 glowing points, night only. Animated in the walk-mode loop;
      // static in orbit mode so the on-demand renderer can sleep.
      const N = 40, rng = mulberry32(7777);
      const pos = new Float32Array(N * 3), base = [], phases = new Float32Array(N);
      for (let i = 0; i < N; i++) {
        const b = {
          x: (rng() - 0.5) * (cols + 4),
          y: 0.6 + rng() * 1.6,
          z: (rng() - 0.5) * (rows + 4),
        };
        base.push(b); phases[i] = rng() * Math.PI * 2;
        pos[i * 3] = b.x; pos[i * 3 + 1] = b.y; pos[i * 3 + 2] = b.z;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const mat = new THREE.PointsMaterial({
        color: 0xeaff8a, size: 0.3, transparent: true, opacity: 0.95,
        blending: THREE.AdditiveBlending, depthWrite: false, fog: false,
      });
      const pts = new THREE.Points(geo, mat);
      pts.userData.base = base; pts.userData.phases = phases;
      pts.visible = dayNight === 'night';
      return pts;
    }

    function updateFireflies(t) {
      if (!T || !T.fireflies || !T.fireflies.visible) return;
      const ud = T.fireflies.userData, attr = T.fireflies.geometry.attributes.position;
      for (let i = 0; i < ud.base.length; i++) {
        const p = fireflyPos(ud.base[i], ud.phases[i], t);
        attr.setXYZ(i, p.x, p.y, p.z);
      }
      attr.needsUpdate = true;
    }

    /* ---------------- butterflies: daytime wanderers ---------------- */
    // Pure: one butterfly's position at time t — a lazy lissajous wander
    // around its home base, staying over the garden.
    function butterflyPos(base, phase, t) {
      return {
        x: base.x + Math.sin(t * 0.45 + phase) * 2.4,
        y: base.y + Math.sin(t * 0.9 + phase * 1.3) * 0.5,
        z: base.z + Math.cos(t * 0.38 + phase) * 2.4,
      };
    }
    // Pure: wing flap angle (radians) at time t — fast flutter.
    function butterflyWing(t, phase) {
      return Math.abs(Math.sin(t * 13 + phase)) * 1.15;
    }
    const BUTTERFLY_COLORS = [0xf2a13d, 0xf5f5f5, 0xffc21f, 0xe06ba8, 0xff8c42];
    function buildButterflies(THREE) {
      // 8 butterflies, day only (fireflies own the night). Two-triangle wings
      // flap via sin; wander in the walk-mode loop, static in orbit mode.
      const N = 8, rng = mulberry32(31337);
      const group = new THREE.Group();
      const items = [];
      for (let i = 0; i < N; i++) {
        const b = new THREE.Group();
        const wingMat = new THREE.MeshBasicMaterial({
          color: BUTTERFLY_COLORS[i % BUTTERFLY_COLORS.length],
          side: THREE.DoubleSide, transparent: true, opacity: 0.95,
        });
        const wingGeo = new THREE.PlaneGeometry(0.26, 0.2);
        wingGeo.translate(0.13, 0, 0); // hinge at the body
        const wl = new THREE.Mesh(wingGeo, wingMat);
        const wr = new THREE.Mesh(wingGeo, wingMat);
        wr.rotation.y = Math.PI;
        const body = new THREE.Mesh(
          new THREE.SphereGeometry(0.035, 6, 5),
          new THREE.MeshBasicMaterial({ color: 0x3a2c1c })
        );
        body.scale.set(1, 1, 2.2);
        b.add(wl, wr, body);
        const base = {
          x: (rng() - 0.5) * cols * 0.8,
          y: 1.1 + rng() * 1.2,
          z: (rng() - 0.5) * rows * 0.8,
        };
        const phase = rng() * Math.PI * 2;
        b.userData = { base, phase, wl, wr };
        b.traverse((o) => { o.castShadow = false; o.receiveShadow = false; });
        group.add(b);
        items.push(b);
      }
      group.userData.items = items;
      group.visible = dayNight !== 'night';
      return group;
    }
    function updateButterflies(t) {
      if (!T || !T.butterflies || !T.butterflies.visible) return;
      T.butterflies.userData.items.forEach((b) => {
        const { base, phase, wl, wr } = b.userData;
        const p = butterflyPos(base, phase, t);
        b.position.set(p.x, p.y, p.z);
        const flap = butterflyWing(t, phase);
        wl.rotation.z = flap;
        wr.rotation.z = -flap;
        // face the direction of travel (cheap: derivative of the lissajous)
        const ahead = butterflyPos(base, phase, t + 0.1);
        b.rotation.y = Math.atan2(ahead.x - p.x, ahead.z - p.z);
      });
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

      // the world: a smooth miniature base — soft grass top, dark skirt,
      // with the 1-ft planning grid as subtle thin lines (not block seams).
      const gw = cols + 8, gd = rows + 8;
      const sideMat = pixMaterial(THREE, TEX.groundSide);
      const ground = new THREE.Mesh(
        new THREE.BoxGeometry(gw, 1, gd),
        [sideMat, sideMat, pixMaterial(THREE, TEX.grass), sideMat, sideMat, sideMat]
      );
      ground.position.y = -0.5;
      ground.receiveShadow = true;
      ground.userData.isGround = true; // build-mode placement targets this
      const gridPts = [];
      for (let gx = 0; gx <= cols; gx++) {
        const x = gx - cols / 2;
        gridPts.push(new THREE.Vector3(x, 0.52, -rows / 2), new THREE.Vector3(x, 0.52, rows / 2));
      }
      for (let gz = 0; gz <= rows; gz++) {
        const z = gz - rows / 2;
        gridPts.push(new THREE.Vector3(-cols / 2, 0.52, z), new THREE.Vector3(cols / 2, 0.52, z));
      }
      const gridLines = new THREE.LineSegments(
        new THREE.BufferGeometry().setFromPoints(gridPts),
        new THREE.LineBasicMaterial({ color: 0x3f7a32, transparent: true, opacity: 0.35 })
      );
      gridLines.raycast = () => {}; // never a raycast target; ground beneath handles it
      ground.add(gridLines);
      T.gridLines = gridLines;
      group.add(ground);

      buildClouds(THREE, group, rng);

      // Meadow decor + fireflies live outside T.group: no raycast targets,
      // no collision, no placement blocking.
      if (T.decor) { scene.remove(T.decor); disposeGroup(T.decor); }
      if (T.fireflies) { scene.remove(T.fireflies); T.fireflies.geometry.dispose(); T.fireflies.material.dispose(); }
      const decor = new THREE.Group();
      buildGrass3D(THREE, decor, TEX);
      scene.add(decor);
      T.decor = decor;
      T.fireflies = buildFireflies(THREE);
      scene.add(T.fireflies);
      if (T.butterflies) { scene.remove(T.butterflies); disposeGroup(T.butterflies); }
      T.butterflies = buildButterflies(THREE);
      scene.add(T.butterflies);

      T.lamps = []; // world-space lamp head positions, for night lighting
      const fc = fenceCells(containers);
      const ec = edgingCells(containers), dc = dripCells(containers);

      containers.forEach((c) => {
        const w = c.grid_w || 1, h = c.grid_h || 1;
        const g = new THREE.Group();
        g.position.set((c.grid_x || 0) + w / 2 - cols / 2, 0, (c.grid_y || 0) + h / 2 - rows / 2);
        g.userData.containerId = c.id;
        const kind = c.kind || 'grow bag';
        if (kind === 'arch') buildArch(THREE, g, w, h, c.height_ft || KIND_HEIGHT.arch || 4, TEX);
        else if (kind === 'pallet') buildPallet(THREE, g, w, h, TEX);
        else if (kind === 'lamp') {
          buildLamp(THREE, g, w, h, TEX);
          const lp = g.userData.lampPos || { x: 0, y: 1.72, z: 0 };
          T.lamps.push({ x: g.position.x + lp.x, y: lp.y, z: g.position.z + lp.z });
        }
        else if (kind === 'fence') buildFence(THREE, g, w, h, TEX, fenceSides(c.grid_x || 0, c.grid_y || 0, fc));
        else if (kind === 'fence gate') buildFenceGate(THREE, g, w, h, TEX, fenceSides(c.grid_x || 0, c.grid_y || 0, fc));
        else if (kind === 'bucket') buildBucket(THREE, g, TEX);
        else if (kind === 'path') buildPath(THREE, g, TEX);
        else if (kind === 'rain barrel') buildRainBarrel(THREE, g, TEX);
        else if (kind === 'compost bin') buildCompostBin(THREE, g, TEX);
        else if (kind === 'hoop house') buildHoopHouse(THREE, g, w, h, c.height_ft || KIND_HEIGHT['hoop house'] || 6, TEX);
        else if (kind === 'bird bath') buildBirdBath(THREE, g, TEX);
        else if (kind === 'fruit tree') buildFruitTree(THREE, g, TEX);
        else if (kind === 'shed') buildShed(THREE, g, w, h, TEX);
        else if (kind === 'pergola') buildPergola(THREE, g, w, h, TEX);
        else if (kind === 'stone edging') buildEdging(THREE, g, w, h, TEX, fenceSides(c.grid_x || 0, c.grid_y || 0, ec));
        else if (kind === 'sprinkler') buildSprinkler(THREE, g, TEX);
        else if (kind === 'drip line') buildDripLine(THREE, g, w, h, TEX, fenceSides(c.grid_x || 0, c.grid_y || 0, dc));
        else buildVessel(THREE, g, w, h, kind, TEX);
        addPlants3D(THREE, g, w, h, kind, c, TEX);
        addBedMarkerAndScatter(THREE, g, w, h, kind, c);
        const label = makeLabel(c.name);
        label.position.y = (g.userData.topY || 1) + 1.2;
        g.add(label);
        g.userData.label = label; // walk mode hides these (crosshair target only)
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
      applyDayNight(); // re-apply sky/lamp state after the rebuild
      sizeThree();
    }

    function render3D() {
      // Note: OrbitControls dispatches 'change' from inside update(), so this
      // must only render — calling update() here would recurse forever.
      // Bloom composer is a single render() call, so on-demand rendering
      // keeps working; plain renderer is the fallback when bloom is missing.
      if (!T || view !== '3d') return;
      if (T.composer) T.composer.render();
      else T.renderer.render(T.scene, T.camera);
    }

    /* ---------------- day / night ---------------- */
    let dayNight = 'day'; // 'day' | 'night'
    const MAX_LAMP_LIGHTS = 8; // real PointLights; extra lamps just glow

    function clearLampLights() {
      if (!T) return;
      (T.lampLights || []).forEach((l) => { T.scene.remove(l); if (l.dispose) l.dispose(); });
      T.lampLights = [];
    }

    // Pure: gradient-sky palette per time of day (also the fog color).
    function skyColors(night) {
      // single source of truth for the sky/fog palette (day/night toggle lerps
      // these; the dome uniforms + fog color are derived in applyDayNight)
      return night
        ? { top: 0x050914, horizon: 0x101c3f }
        : { top: 0x3f8cff, horizon: 0x93ccff };
    }

    function applyDayNight() {
      if (!T || !T.sky) return;
      const THREE = T.THREE, night = dayNight === 'night';
      const pal = skyColors(night);
      if (T.sky.dome) {
        T.sky.dome.material.uniforms.topColor.value.copy(srgbToLinear(THREE, pal.top));
        T.sky.dome.material.uniforms.horizonColor.value.copy(srgbToLinear(THREE, pal.horizon));
      }
      if (T.scene.fog) T.scene.fog.color.copy(srgbToLinear(THREE, pal.horizon));
      if (T.gridLines) {
        // grid lines fade out entirely at night — they glowed against dark grass
        T.gridLines.material.opacity = night ? 0 : 0.35;
        T.gridLines.material.color.set(night ? 0x2a5522 : 0x3f7a32);
      }
      T.sky.hemi.intensity = night ? 0.25 : 0.9;
      T.sky.hemi.color.set(night ? 0x33456e : 0xbdd8ff);
      T.sun.intensity = night ? 0.14 : 1.1; // moonlight at night
      T.sun.color.set(night ? 0x9db4ff : 0xfff1d4);
      T.sky.sunSprite.visible = !night;
      T.sky.moonSprite.visible = night;
      T.sky.stars.visible = night;
      if (T.fireflies) T.fireflies.visible = night;
      if (T.butterflies) T.butterflies.visible = !night;
      // clouds tint with the sky (they share one material)
      if (T.clouds && T.clouds.length && T.clouds[0].userData.cloudMat) {
        T.clouds[0].userData.cloudMat.color.set(night ? 0x2a3a5f : 0xffffff);
      }
      // lamp heads always glow a little; at night they blaze
      if (T.group) {
        T.group.traverse((o) => {
          if (o.userData && o.userData.lampHead && o.material) {
            o.material.emissiveIntensity = night ? 1.3 : 0.15;
          }
        });
      }
      // real warm point lights, capped: nearest lamps to the camera win
      clearLampLights();
      if (night && T.lamps && T.lamps.length && T.camera) {
        const ids = nearestLampIds(T.lamps, T.camera.position.x, T.camera.position.z, MAX_LAMP_LIGHTS);
        ids.forEach((i) => {
          const p = T.lamps[i];
          const pl = new THREE.PointLight(0xffb45e, 1.4, 14, 2);
          pl.position.set(p.x, p.y + 0.3, p.z);
          T.scene.add(pl);
          T.lampLights.push(pl);
        });
      }
    }

    function toggleDayNight() {
      dayNight = dayNight === 'day' ? 'night' : 'day';
      applyDayNight();
      paintViewButtons();
      render3D();
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

    // Minimal pointer-lock look control (v2.62.0). Replaces three's
    // PointerLockControls, which exposes no sensitivity setting. Mirrors its
    // behavior (0.002 base factor, pitch clamp) plus a sane default.
    function makeLookControl(THREE, camera, dom) {
      const listeners = {};
      const euler = new THREE.Euler(0, 0, 0, 'YXZ');
      const ctl = {
        isLocked: false,
        sensitivity: 1.15,
        lock() { try { dom.requestPointerLock(); } catch (e) { /* noop */ } },
        unlock() { try { document.exitPointerLock(); } catch (e) { /* noop */ } },
        addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); },
      };
      const emit = (t) => (listeners[t] || []).forEach((fn) => { try { fn(); } catch (e) { /* noop */ } });
      ctl._onMove = (e) => {
        if (!ctl.isLocked) return;
        const s = 0.002 * ctl.sensitivity;
        euler.setFromQuaternion(camera.quaternion);
        euler.y -= e.movementX * s;
        euler.x -= e.movementY * s;
        euler.x = Math.max(-1.45, Math.min(1.45, euler.x));
        camera.quaternion.setFromEuler(euler);
      };
      ctl._onLockChange = () => {
        const locked = document.pointerLockElement === dom;
        if (locked === ctl.isLocked) return;
        ctl.isLocked = locked;
        emit(locked ? 'lock' : 'unlock');
      };
      ctl.dispose = () => {
        document.removeEventListener('mousemove', ctl._onMove);
        document.removeEventListener('pointerlockchange', ctl._onLockChange);
      };
      document.addEventListener('mousemove', ctl._onMove);
      document.addEventListener('pointerlockchange', ctl._onLockChange);
      return ctl;
    }

    async function ensureWalk() {
      if (walk) return walk;
      await ensureThree();
      const THREE = T.THREE;
      const plc = makeLookControl(THREE, T.camera, T.renderer.domElement);
      walk = { plc, keys: {}, locked: false, loopId: 0, last: 0, x: 0, z: 0, yaw: 0, vx: 0, vz: 0 };
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
        const kind = c.kind || 'grow bag';
        if (kind === 'arch') return; // walk under
        if (kind === 'pergola') return; // walk under
        if (kind === 'path') return; // flat slab: walked over, not into
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
      const sp = (k.ShiftLeft || k.ShiftRight) ? SPRINT_SPEED : SPRINT_SPEED / 2;
      // desired velocity (v2.62.0: smooth accel/damping instead of binary)
      let dvx = 0, dvz = 0;
      if (mx || mz) {
        const len = Math.hypot(mx, mz);
        dvx = ((fx * mz + rx * mx) / len) * sp;
        dvz = ((fz * mz + rz * mx) / len) * sp;
      }
      if (walk.vx == null) { walk.vx = 0; walk.vz = 0; }
      const rate = (mx || mz) ? 10 : 14; // snappy start, quick but smooth stop
      const t = 1 - Math.exp(-rate * dt);
      walk.vx += (dvx - walk.vx) * t;
      walk.vz += (dvz - walk.vz) * t;
      if (Math.abs(walk.vx) < 0.02 && Math.abs(walk.vz) < 0.02 && !mx && !mz) {
        walk.vx = walk.vz = 0;
      } else {
        const ox = walk.x, oz = walk.z;
        const r = resolvePlayerCollision(ox + walk.vx * dt, oz + walk.vz * dt, walkColliders());
        walk.x = r.x; walk.z = r.z;
        // Recompute velocity from actual motion: wall sliding keeps its
        // tangential part, head-on impact zeroes out (no lunge on release).
        if (dt > 0) { walk.vx = (r.x - ox) / dt; walk.vz = (r.z - oz) / dt; }
      }
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
      updateWalkLabel(); // crosshair-target label only (v2.62.0)
      driftClouds(dt); // slow cloud drift, walk mode only (battery-friendly)
      updateFireflies(now / 1000); // firefly drift, walk mode only
      updateButterflies(now / 1000); // butterfly wander + wing flap, walk mode only
      updateParticles(dt); // break-particle juice, walk mode only
      render3D();
      return true;
    }

    function startWalkLoop() {
      if (!walk || walk.loopId) return;
      walk.last = 0;
      const frame = (t) => { walk.loopId = 0; if (walkStep(t)) walk.loopId = raf(frame); };
      walk.loopId = raf(frame);
    }

    // v2.62.0: floating name labels clutter first person. Hide them all in
    // walk mode, showing only the single item under the crosshair (~10ft).
    function updateWalkLabel() {
      if (!T || !T.group) return;
      T.group.children.forEach((ch) => {
        if (ch.userData && ch.userData.label) ch.userData.label.visible = !walkMode;
      });
      if (!walkMode || !(walk && walk.locked)) return;
      const a = aimHit();
      if (a && a.containerId != null && a.point && T.camera) {
        if (T.camera.position.distanceTo(a.point) <= 10) {
          const grp = T.group.children.find((o) => o.userData && o.userData.containerId === a.containerId);
          if (grp && grp.userData.label) grp.userData.label.visible = true;
        }
      }
    }

    function stopWalkLoop() {
      if (walk && walk.loopId) { caf(walk.loopId); walk.loopId = 0; }
    }

    async function enterWalkMode() {
      if (isTouchOnly()) { toast('Walk mode needs a keyboard + mouse.'); return; }
      setTapeMode(false); // tape is orbit-only
      try { await ensureWalk(); }
      catch (err) {
        toast('Could not load walk controls — check your connection and try again.', 'error');
        return;
      }
      walkMode = true;
      // start at the south edge, facing the garden (yaw 0 faces -z)
      walk.x = 0; walk.z = rows / 2 + 3; walk.yaw = 0; walk.keys = {};
      walk.vx = 0; walk.vz = 0; // no lunge from a previous session's velocity
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
      archArcPoint, archRibCount, plantFoliage,
      fenceSides, fenceCells, kindCells, edgingCells, dripCells, nearestLampIds, driftClouds,
      skyColors, grassLayout, occupiedCellSet, fireflyPos, updateFireflies,
      butterflyPos, butterflyWing, updateButterflies,
      tapeDistance, setTapeMode, clearTape,
      spawnParticles, particleCount, updateParticles,
      get Sound() { return Sound; },
      get tapeMode() { return tapeMode; },
      get tapePoints() { return tapePoints; },
      get dayNight() { return dayNight; },
      _toggleDayNight: () => toggleDayNight(),
      painters: {
        paintGrass, paintGroundSide, paintSoil, paintWood, paintDarkWood,
        paintFabric, paintTerracotta, paintMetal, paintWireMesh,
        paintBucket, paintStone, paintBarrel, paintCompost, paintHoopPlastic, paintBasin,
        paintLeaf, paintGrassTuft, paintWildflower, paintLightWood,
      },
      get mode() { return walkMode; },
      _get: () => walk,
      _set: (w) => { walk = w; },
      _setT: (t) => { T = t; },
      _setMode: (m) => { walkMode = m; },
      _startLoop: () => startWalkLoop(),
      _stopLoop: () => stopWalkLoop(),
      _tick: (t) => walkStep(t),
      _enter: () => enterWalkMode(),
      _exit: () => exitWalkMode(),
    };
    /* -------------- end walk mode -------------- */

    /* ---------------- game feel: sounds + break particles ---------------- */
    // Tiny WebAudio synth, zero assets. Default ON; 🔊 button toggles.
    const Sound = {
      enabled: true, _ctx: null,
      ac() {
        if (!this._ctx) {
          try {
            const AC = (typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)) || null;
            if (AC) this._ctx = new AC();
          } catch (e) { this._ctx = null; }
        }
        return this._ctx;
      },
      thunk() { // place: short low sine thump
        const c = this.ac();
        if (!c || !this.enabled) return;
        try {
          const o = c.createOscillator(), g = c.createGain();
          o.type = 'sine';
          o.frequency.setValueAtTime(150, c.currentTime);
          o.frequency.exponentialRampToValueAtTime(60, c.currentTime + 0.12);
          g.gain.setValueAtTime(0.25, c.currentTime);
          g.gain.exponentialRampToValueAtTime(0.001, c.currentTime + 0.15);
          o.connect(g); g.connect(c.destination);
          o.start(); o.stop(c.currentTime + 0.16);
        } catch (e) { /* audio is decorative */ }
      },
      crunch() { // break: filtered noise burst
        const c = this.ac();
        if (!c || !this.enabled) return;
        try {
          const len = Math.floor(c.sampleRate * 0.2);
          const buf = c.createBuffer(1, len, c.sampleRate);
          const d = buf.getChannelData(0);
          for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
          const src = c.createBufferSource(); src.buffer = buf;
          const f = c.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 900;
          const g = c.createGain();
          g.gain.setValueAtTime(0.3, c.currentTime);
          g.gain.exponentialRampToValueAtTime(0.001, c.currentTime + 0.2);
          src.connect(f); f.connect(g); g.connect(c.destination);
          src.start();
        } catch (e) { /* audio is decorative */ }
      },
    };

    // Break particles: ~12 small voxel cubes burst from the broken
    // container's center, gravity + fade over ~0.6s. Runs in the walk-mode
    // rAF loop (build mode is walk-only, so no orbit animation needed).
    let particles = [];
    const PARTICLE_COLORS = [0x8a6b46, 0x6e4f2e, 0x5cb85c, 0x9aa0a6, 0x2b6cb0];
    function spawnParticles(x, y, z) {
      if (!T || !T.THREE) return;
      const THREE = T.THREE;
      const rng = mulberry32((Date.now() & 0xffff) | 1);
      for (let i = 0; i < 12; i++) {
        const s = 0.1 + rng() * 0.12;
        const m = new THREE.Mesh(
          new THREE.BoxGeometry(s, s, s),
          new THREE.MeshBasicMaterial({
            color: PARTICLE_COLORS[(rng() * PARTICLE_COLORS.length) | 0],
            transparent: true, opacity: 1,
          })
        );
        m.position.set(x + (rng() - 0.5) * 0.5, y + rng() * 0.4, z + (rng() - 0.5) * 0.5);
        T.scene.add(m);
        particles.push({
          mesh: m,
          vx: (rng() - 0.5) * 3.2, vy: 2.2 + rng() * 2.6, vz: (rng() - 0.5) * 3.2,
          life: 0.55 + rng() * 0.15, age: 0,
        });
      }
    }
    function updateParticles(dt) {
      if (!particles.length || !T) return;
      const alive = [];
      for (const p of particles) {
        p.age += dt;
        if (p.age >= p.life) {
          T.scene.remove(p.mesh);
          p.mesh.geometry.dispose();
          p.mesh.material.dispose();
          continue;
        }
        p.vy -= 7.5 * dt; // gravity
        p.mesh.position.x += p.vx * dt;
        p.mesh.position.y += p.vy * dt;
        p.mesh.position.z += p.vz * dt;
        if (p.mesh.position.y < 0.05) { p.mesh.position.y = 0.05; p.vy *= -0.35; p.vx *= 0.7; p.vz *= 0.7; }
        p.mesh.material.opacity = 1 - p.age / p.life;
        p.mesh.rotation.x += dt * 4; p.mesh.rotation.y += dt * 3;
        alive.push(p);
      }
      particles = alive;
    }
    function particleCount() { return particles.length; }

    /* ---------------- measuring tape (orbit mode) ---------------- */
    // 📏 toolbar button toggles tape mode; click two ground points in orbit
    // mode, get a line + "12.5 ft" label (1 unit = 1 ft). ESC clears.
    let tapeMode = false;
    let tapePoints = []; // [{x, z}] world coords, max 2
    let tapeGroup = null;
    function tapeDistance(a, b) { // pure; feet
      return Math.hypot(a.x - b.x, a.z - b.z);
    }
    function clearTape() {
      tapePoints = [];
      if (tapeGroup && T) { T.scene.remove(tapeGroup); disposeGroup(tapeGroup); }
      tapeGroup = null;
      render3D();
    }
    function drawTape() {
      if (!T || tapePoints.length < 2) return;
      const THREE = T.THREE;
      if (tapeGroup) { T.scene.remove(tapeGroup); disposeGroup(tapeGroup); }
      tapeGroup = new THREE.Group();
      const [a, b] = tapePoints;
      const geo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(a.x, 0.15, a.z), new THREE.Vector3(b.x, 0.15, b.z),
      ]);
      tapeGroup.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffffff })));
      const dot = (p) => {
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 8),
          new THREE.MeshBasicMaterial({ color: 0xffd23e }));
        m.position.set(p.x, 0.15, p.z);
        tapeGroup.add(m);
      };
      dot(a); dot(b);
      const d = tapeDistance(a, b);
      const label = makeLabel(`${d.toFixed(1)} ft`);
      label.position.set((a.x + b.x) / 2, 1.4, (a.z + b.z) / 2);
      tapeGroup.add(label);
      T.scene.add(tapeGroup);
      render3D();
    }
    function tapeClick(wx, wz) {
      tapePoints.push({ x: wx, z: wz });
      if (tapePoints.length > 2) tapePoints = [{ x: wx, z: wz }]; // third click starts a new tape
      if (tapePoints.length === 2) drawTape();
      else render3D();
    }
    function setTapeMode(on) {
      tapeMode = !!on;
      if (!tapeMode) clearTape();
      paintViewButtons();
      hint3d.textContent = tapeMode
        ? '📏 Tape: click two points on the ground to measure · ESC clears.'
        : (walkMode ? walkHintText : orbitHintText);
      render3D();
    }

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
        { key: 'lamp', emoji: '💡', label: 'Lamp' },
        { key: 'fence', emoji: '⛓️', label: 'Fence' },
        { key: 'bucket', emoji: '🪣', label: 'Bucket' },
        { key: 'path', emoji: '🪨', label: 'Path' },
        { key: 'rain barrel', emoji: '🛢️', label: 'Barrel' },
        { key: 'compost bin', emoji: '🟤', label: 'Compost' },
        { key: 'hoop house', emoji: '🏠', label: 'HoopHs' },
        { key: 'fence gate', emoji: '🚪', label: 'Gate' },
        { key: 'bird bath', emoji: '🐦', label: 'Bath' },
        { key: 'fruit tree', emoji: '🌳', label: 'Tree' },
        { key: 'shed', emoji: '🏚️', label: 'Shed' },
        { key: 'pergola', emoji: '🏛️', label: 'Pergola' },
        { key: 'stone edging', emoji: '🧱', label: 'Edging' },
        { key: 'sprinkler', emoji: '💦', label: 'Sprinklr' },
        { key: 'drip line', emoji: '💧', label: 'Drip' },
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
    // Per-kind build-mode placement footprints. Everything defaults to 1x1;
    // the hoop house is 4x8, the shed 4x6, the pergola 2x4.
    const PLACE_FOOTPRINTS = { 'hoop house': [4, 8], 'shed': [4, 6], 'pergola': [2, 4] };
    function placeFootprint(key) { return PLACE_FOOTPRINTS[key] || [1, 1]; }
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
      hotbarTab.textContent = (buildTab === 'blocks' ? '▣ BLOCKS' : '❀ PLANTS') + ' · Q switch · 1-9/wheel pick';
      hotbarTab.style.cssText = 'color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;' +
        'text-shadow:0 1px 2px #000;margin-bottom:4px;';
      const slotHtml = (s, i) => {
        const on = i === buildIndex;
        return '<div style="display:inline-block;width:54px;margin:0 2px;padding:4px 2px;' +
          'background:rgba(18,18,18,.75);border:2px solid ' + (on ? '#fff' : '#5a5a5a') + ';' +
          (on ? 'box-shadow:0 0 0 2px #fff;' : '') + 'border-radius:3px;vertical-align:top;">' +
          '<div style="font-size:22px;line-height:1.25">' + s.emoji + '</div>' +
          '<div style="font-size:9px;color:#ddd;white-space:nowrap;overflow:hidden">' + s.label + '</div>' +
          '<div style="font-size:9px;color:#9f9;font-weight:700">∞</div></div>';
      };
      // rows of 8 while the tab is long (BLOCKS has 22: 8/8/6); PLANTS stays one row
      const slots = buildSlots();
      let html = '';
      for (let r = 0; r * 8 < slots.length; r++) {
        html += '<div style="margin-bottom:4px;">' +
          slots.slice(r * 8, r * 8 + 8).map((s, j) => slotHtml(s, r * 8 + j)).join('') +
          '</div>';
      }
      hotbarSlots.innerHTML = html;
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
      // voxel-cube burst at the break point (before the scene rebuilds)
      const burstAt = (x, y, z) => { spawnParticles(x, y, z); Sound.crunch(); };
      const containerCenter = (c) => {
        if (T && T.group) {
          const grp = T.group.children.find((o) => o.userData && o.userData.containerId === c.id);
          if (grp) return { x: grp.position.x, y: (grp.userData.topY || 1) / 2 + 0.3, z: grp.position.z };
        }
        const w = c.grid_w || 1, h = c.grid_h || 1;
        return { x: (c.grid_x || 0) + w / 2 - cols / 2, y: 0.8, z: (c.grid_y || 0) + h / 2 - rows / 2 };
      };
      if (a.plantingId != null) {
        try {
          await api.del(`/api/containers/plantings/${a.plantingId}`);
          plantings = plantings.filter((p) => p.id !== a.plantingId);
          if (a.point) burstAt(a.point.x, a.point.y, a.point.z);
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
      const boom = containerCenter(c);
      try {
        await api.del(`/api/containers/${c.id}`);
        containers = containers.filter((x) => x.id !== c.id);
        plantings = plantings.filter((p) => p.container_id !== c.id);
        burstAt(boom.x, boom.y, boom.z);
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
        const [pw, ph] = placeFootprint(sel.key);
        const { gx, gy } = cellFromWorld(a.point.x, a.point.z, cols, rows);
        if (!cellFree(gx, gy, pw, ph, containers, cols, rows, null)) { toast('No room there.', 'error'); return; }
        const name = nextContainerName(sel.key);
        let created = null;
        try {
          // create() auto-picks the first free spot; then move it to the aimed cell.
          created = await api.post('/api/containers/', {
            name, kind: sel.key, grid_w: pw, grid_h: ph, season_year: year,
          });
          const moved = await api.patch(`/api/containers/${created.id}`, { grid_x: gx, grid_y: gy });
          containers.push(moved);
          Sound.thunk();
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
      const sel = buildSelected();
      const [pw, ph] = placeFootprint(sel.key);
      let cell = null, ok = false;
      if (a && a.isGround) {
        cell = cellFromWorld(a.point.x, a.point.z, cols, rows);
        ok = cellFree(cell.gx, cell.gy, pw, ph, containers, cols, rows, null);
      }
      const key = show && cell ? `${sel.key}@${cell.gx},${cell.gy}:${ok ? 'g' : 'r'}` : '';
      if (!key) { clearGhost(); return; }
      if (ghost && ghost.userData.key === key) return;
      clearGhost();
      const THREE = T.THREE;
      ghost = new THREE.Group();
      if (sel.key === 'arch') buildArch(THREE, ghost, 1, 1, 4, T.TEX);
      else if (sel.key === 'pallet') buildPallet(THREE, ghost, 1, 1, T.TEX);
      else if (sel.key === 'lamp') buildLamp(THREE, ghost, 1, 1, T.TEX);
      else if (sel.key === 'fence') buildFence(THREE, ghost, 1, 1, T.TEX, fenceSides(cell.gx, cell.gy, fenceCells(containers)));
      else if (sel.key === 'fence gate') buildFenceGate(THREE, ghost, 1, 1, T.TEX, fenceSides(cell.gx, cell.gy, fenceCells(containers)));
      else if (sel.key === 'bucket') buildBucket(THREE, ghost, T.TEX);
      else if (sel.key === 'path') buildPath(THREE, ghost, T.TEX);
      else if (sel.key === 'rain barrel') buildRainBarrel(THREE, ghost, T.TEX);
      else if (sel.key === 'compost bin') buildCompostBin(THREE, ghost, T.TEX);
      else if (sel.key === 'hoop house') buildHoopHouse(THREE, ghost, pw, ph, 6, T.TEX);
      else if (sel.key === 'bird bath') buildBirdBath(THREE, ghost, T.TEX);
      else if (sel.key === 'fruit tree') buildFruitTree(THREE, ghost, T.TEX);
      else if (sel.key === 'shed') buildShed(THREE, ghost, pw, ph, T.TEX);
      else if (sel.key === 'pergola') buildPergola(THREE, ghost, pw, ph, T.TEX);
      else if (sel.key === 'stone edging') buildEdging(THREE, ghost, 1, 1, T.TEX, fenceSides(cell.gx, cell.gy, edgingCells(containers)));
      else if (sel.key === 'sprinkler') buildSprinkler(THREE, ghost, T.TEX);
      else if (sel.key === 'drip line') buildDripLine(THREE, ghost, 1, 1, T.TEX, fenceSides(cell.gx, cell.gy, dripCells(containers)));
      else buildVessel(THREE, ghost, 1, 1, sel.key, T.TEX);
      const tint = new THREE.Color(ok ? 0x00cc44 : 0xcc2222);
      ghost.traverse((o) => {
        if (o.isMesh) {
          // Model clones share the cache's materials: give the ghost private
          // copies before tinting, or every instance in the scene would tint.
          if (o.userData.fromModel) {
            o.material = Array.isArray(o.material) ? o.material.map((x) => x.clone()) : o.material.clone();
          }
          o.material.transparent = true;
          o.material.opacity = 0.6;
          o.material.emissive = tint;
          o.material.emissiveIntensity = 0.6;
          o.castShadow = false;
        }
      });
      ghost.position.set(cell.gx + pw / 2 - cols / 2, 0.03, cell.gy + ph / 2 - rows / 2);
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
        else if (/^Digit[1-9]$/.test(e.code)) buildSelect(Number(e.code.slice(5)) - 1);
      });
    }

    wrap3d._build = { // handle for tests / debugging
      cellFromWorld, rectsOverlap, cellFree, needsBreakConfirm, placeFootprint,
      buildSlots, buildSelected, buildSelect, buildCycle, buildToggleTab,
      nextContainerName, updateGhost, aimHit, breakAim, placeAim, editAim,
      growthProgress, growthStage, cropModelFor, produceModelFor,
      cattlePanelHeight,
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
      if (dayNightBtn) {
        dayNightBtn.className = (view === '3d' ? '' : ' hidden') + ' ' + (dayNight === 'night' ? on : off);
        dayNightBtn.textContent = dayNight === 'night' ? '🌙 Night' : '☀️ Day';
      }
      if (tapeBtn) {
        tapeBtn.className = (view === '3d' ? '' : ' hidden') + ' ' + (tapeMode ? on : off);
      }
      if (soundBtn) {
        soundBtn.className = (view === '3d' ? '' : ' hidden') + ' ' + off;
        soundBtn.textContent = Sound.enabled ? '🔊' : '🔇';
      }
      if (fsBtn) {
        fsBtn.className = (view === '3d' ? '' : ' hidden') + ' ' + off;
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
        setTapeMode(false);
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
    if (dayNightBtn) {
      dayNightBtn.addEventListener('click', () => { if (view === '3d') toggleDayNight(); });
    }
    if (tapeBtn) {
      tapeBtn.addEventListener('click', () => {
        if (view !== '3d' || walkMode) return; // orbit mode only
        setTapeMode(!tapeMode);
      });
    }
    if (soundBtn) {
      soundBtn.addEventListener('click', () => {
        Sound.enabled = !Sound.enabled;
        paintViewButtons();
        if (Sound.enabled) Sound.thunk(); // little confirmation blip
      });
    }
    // v2.62.0: fullscreen 3D view. Esc exits natively; resize on change.
    function isFullscreen() {
      return !!(typeof document !== 'undefined' && document.fullscreenElement);
    }
    function toggleFullscreen() {
      if (typeof document === 'undefined') return;
      try {
        if (isFullscreen()) document.exitFullscreen();
        else if (wrap3d.requestFullscreen) wrap3d.requestFullscreen();
        else if (wrap3d.webkitRequestFullscreen) wrap3d.webkitRequestFullscreen();
      } catch (err) { /* noop */ }
    }
    if (fsBtn) {
      const paintFs = () => { fsBtn.textContent = isFullscreen() ? '⛶ ✓' : '⛶'; };
      fsBtn.addEventListener('click', () => { if (view === '3d') toggleFullscreen(); });
      if (typeof document !== 'undefined' && document.addEventListener) {
        document.addEventListener('fullscreenchange', () => {
          paintFs();
          if (view === '3d') sizeThree();
        });
      }
      paintFs();
    }
    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('resize', () => { if (view === '3d') sizeThree(); });
      window.addEventListener('keydown', (e) => {
        if (e.code === 'Escape' && tapeMode && !walkMode) setTapeMode(false);
      });
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

/* Garden Logs page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initLogs() {
    const fertForm = $('#fert-form');
    const obsForm = $('#obs-form');
    if (!fertForm || !obsForm) return {};
    const today = new Date().toISOString().slice(0, 10);
    $('#fert-date').value ||= today;
    $('#obs-date').value ||= new URLSearchParams(location.search).get('date') || today;
    let ferts = [];
    let observations = [];
    let editingFert = null;
    let editingObs = null;

    async function loadFerts() {
      ferts = await api.get('/api/fertilizations?limit=500');
      $('#fert-count').textContent = ferts.length;
      $('#fert-rows').innerHTML = ferts.length ? ferts.map((item) => `<tr><td class="td">${fmtDate(item.date)}</td><td class="td">${esc(item.fertilizer_name)}</td><td class="td">${esc(item.npk_ratio) || '—'}</td><td class="td">${esc(item.amount_used) || '—'}</td><td class="td">${esc(item.notes) || '—'}</td><td class="td text-right"><button class="text-sage-700" data-edit-fert="${item.id}">Edit</button> <button data-delete-fert="${item.id}" aria-label="Delete fertilization">🗑</button></td></tr>`).join('') : '<tr><td class="td text-center" colspan="6">No fertilization entries yet.</td></tr>';
    }
    async function loadObs() {
      const plant = $('#obs-filter').value.trim();
      const date = new URLSearchParams(location.search).get('date');
      observations = await api.get(`/api/observations?limit=500${plant ? `&plant=${encodeURIComponent(plant)}` : ''}${date ? `&date_from=${date}&date_to=${date}` : ''}`);
      $('#obs-count').textContent = observations.length;
      const weatherChip = (item) => item.temp_c != null
        ? `<div class="mt-0.5 text-xs text-navy-400">🌡️ ${esc(String(item.temp_c))}°C${item.weather_summary ? ` · ${esc(item.weather_summary)}` : ''}</div>`
        : '';
      $('#obs-rows').innerHTML = observations.length ? observations.map((item) => `<tr><td class="td">${fmtDate(item.date)}</td><td class="td">${esc(item.plant_name)}</td><td class="td">${healthBar(item.health_scale)}</td><td class="td">${item.watering_status ? '💧 Watered' : '—'}</td><td class="td">${esc(item.pest_sightings) || 'None'}</td><td class="td">${esc(item.notes) || ''}${weatherChip(item)}${!item.notes && !weatherChip(item) ? '—' : ''}</td><td class="td">${(item.images || []).map((image) => `<button data-lightbox="${esc(image.file_path)}"><img src="${esc(image.file_path)}" class="h-10 w-10 rounded object-cover" alt="${esc(item.plant_name)}"></button>`).join('') || '—'}</td><td class="td text-right"><button class="text-sage-700" data-edit-obs="${item.id}">Edit</button> <button data-delete-obs="${item.id}" aria-label="Delete observation">🗑</button></td></tr>`).join('') : '<tr><td class="td text-center" colspan="8">No observations yet.</td></tr>';
    }

    wireDraft(fertForm, 'verdant.draft.fert', ['#fert-date', '#fert-name', '#fert-npk', '#fert-amount', '#fert-notes', '#fert-plant-link']);
    wireDraft(obsForm, 'verdant.draft.obs', ['#obs-date', '#obs-plant', '#obs-plant-link', '#obs-health', '#obs-water', '#obs-pests', '#obs-notes']);
    $('#obs-health').addEventListener('input', () => { $('#obs-health-out').textContent = $('#obs-health').value; });

    async function loadPlantLinks() {
      try {
        const plants = await api.get('/api/plants/');
        const options = plants.map((p) => `<option value="${p.id}">${esc(p.variety_name)}</option>`).join('');
        const obsSel = $('#obs-plant-link');
        if (obsSel) {
          const current = obsSel.value;
          obsSel.innerHTML = '<option value="">— just a name, no profile —</option>' + options;
          if (current) obsSel.value = current;
        }
        const fertSel = $('#fert-plant-link');
        if (fertSel) {
          const currentF = fertSel.value;
          fertSel.innerHTML = '<option value="">— whole garden —</option>' + options;
          if (currentF) fertSel.value = currentF;
        }
        obsSel?.addEventListener('change', () => {
          const chosen = plants.find((p) => p.id === Number(obsSel.value));
          if (chosen && !$('#obs-plant').value.trim()) $('#obs-plant').value = chosen.variety_name;
        });
      } catch { /* plant links are optional */ }
    }
    loadPlantLinks();

    fertForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const payload = { date: $('#fert-date').value, fertilizer_name: $('#fert-name').value.trim(), npk_ratio: $('#fert-npk').value.trim(), amount_used: $('#fert-amount').value.trim(), notes: $('#fert-notes').value, plant_id: $('#fert-plant-link')?.value ? Number($('#fert-plant-link').value) : null };
        editingFert ? await api.patch(`/api/fertilizations/${editingFert}`, payload) : await api.post('/api/fertilizations', payload);
        editingFert = null; fertForm.reset(); localStorage.removeItem('verdant.draft.fert'); $('#fert-date').value = today;
        $('button[type="submit"]', fertForm).textContent = 'Add fertilization';
        toast('Fertilization saved 🧪', 'ok'); await Promise.all([loadFerts(), renderStats()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
    });
    obsForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const payload = { date: $('#obs-date').value, plant_name: $('#obs-plant').value.trim(), plant_id: $('#obs-plant-link')?.value ? Number($('#obs-plant-link').value) : null, health_scale: Number($('#obs-health').value), watering_status: $('#obs-water').value === 'true', pest_sightings: $('#obs-pests').value.trim(), notes: $('#obs-notes').value };
        const observation = editingObs ? await api.patch(`/api/observations/${editingObs}`, payload) : await api.post('/api/observations', payload);
        if (!editingObs) await uploadFiles(`/api/observations/${observation.id}/images`, $('#obs-images').files);
        editingObs = null; obsForm.reset(); localStorage.removeItem('verdant.draft.obs'); $('#obs-date').value = today; $('#obs-health-out').textContent = '5';
        $('button[type="submit"]', obsForm).textContent = 'Add observation';
        toast('Observation saved 🔍', 'ok'); await Promise.all([loadObs(), renderStats()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
    });
    document.addEventListener('click', (event) => {
      const fertButton = event.target.closest('[data-edit-fert]');
      const obsButton = event.target.closest('[data-edit-obs]');
      if (fertButton) {
        const item = ferts.find((entry) => entry.id === Number(fertButton.dataset.editFert));
        editingFert = item.id; $('#fert-date').value = item.date; $('#fert-name').value = item.fertilizer_name; $('#fert-npk').value = item.npk_ratio; $('#fert-amount').value = item.amount_used; $('#fert-notes').value = item.notes;
        $('button[type="submit"]', fertForm).textContent = 'Save changes'; fertForm.scrollIntoView({ behavior: 'smooth' });
      }
      if (obsButton) {
        const item = observations.find((entry) => entry.id === Number(obsButton.dataset.editObs));
        editingObs = item.id; $('#obs-date').value = item.date; $('#obs-plant').value = item.plant_name; const obsLink = $('#obs-plant-link'); if (obsLink && item.plant_id) obsLink.value = String(item.plant_id); $('#obs-health').value = item.health_scale; $('#obs-health-out').textContent = item.health_scale; $('#obs-water').value = String(item.watering_status); $('#obs-pests').value = item.pest_sightings; $('#obs-notes').value = item.notes;
        $('button[type="submit"]', obsForm).textContent = 'Save changes'; obsForm.scrollIntoView({ behavior: 'smooth' });
      }
    });
    let filterTimer;
    $('#obs-filter').addEventListener('input', () => { clearTimeout(filterTimer); filterTimer = setTimeout(() => loadObs(), 250); });
    Promise.all([loadFerts(), loadObs(), renderStats()]).catch((error) => toast(`Could not load garden logs: ${error.message}`, 'err'));
    return { ferts: loadFerts, obs: loadObs };
  }

  globalThis.Verdant.onBoot(initLogs);
})();

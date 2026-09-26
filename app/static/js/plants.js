/* Plants page + seed-starting calendar. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  /* ------------------------------ Plants ------------------------------ */

  function dueLabel(reminder) {
    const what = reminder.kind === 'water' ? 'Water' : 'Feed';
    if (reminder.status === 'unset') return `${what} · no schedule`;
    if (reminder.status === 'overdue') {
      return reminder.days_until_due == null
        ? `${what} · overdue (never logged)`
        : `${what} · ${-reminder.days_until_due}d overdue`;
    }
    if (reminder.status === 'due') return `${what} · due today`;
    if (reminder.status === 'soon') return `${what} · due in ${reminder.days_until_due}d`;
    return `${what} · on track`;
  }

  function reminderCard(reminder) {
    const urgent = reminder.status === 'overdue';
    const tone = urgent ? 'border-red-300' : reminder.status === 'due' ? 'border-beige-500' : 'border-sage-300';
    const icon = reminder.kind === 'water' ? '💧' : '🧪';
    return `<div class="card border-l-4 ${tone}">
      <div class="flex items-start justify-between gap-2">
        <div>
          <p class="font-semibold text-navy-800">${esc(reminder.plant_name)}</p>
          <p class="text-sm ${urgent ? 'font-semibold text-red-700' : 'text-navy-500'}">${icon} ${esc(dueLabel(reminder))}</p>
          ${reminder.last_date ? `<p class="text-xs text-navy-400">Last: ${fmtDate(reminder.last_date)}</p>` : ''}
        </div>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        ${reminder.kind === 'water'
          ? `<button type="button" class="btn-primary text-xs" data-water-plant="${reminder.plant_id}">Mark watered</button>`
          : `<button type="button" class="btn-primary text-xs" data-feed-toggle="${reminder.plant_id}">Mark fed</button>`}
        <button type="button" class="btn-ghost text-xs" data-open-plant="${reminder.plant_id}">Open profile</button>
      </div>
      <form class="fed-form mt-3 hidden gap-2" data-fed-form="${reminder.plant_id}">
        <input class="inp text-sm" placeholder="Fertilizer used (e.g. fish emulsion)" required maxlength="120" data-fed-name />
        <button type="submit" class="btn-primary text-xs">Save feeding</button>
      </form>
    </div>`;
  }

  function eventIcon(kind) {
    return { observation: '🔍', fertilization: '🧪', harvest: '🧺', watering: '💧' }[kind] || '•';
  }

  function timelineEventHtml(event) {
    const thumbs = (event.images || []).map((img) =>
      `<button type="button" data-lightbox="${esc(img.file_path)}"><img src="${esc(img.file_path)}" class="h-12 w-12 rounded-lg object-cover" alt="" loading="lazy"></button>`
    ).join('');
    return `<li class="flex gap-3">
      <span class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sage-100 text-lg ring-1 ring-sage-200">${eventIcon(event.kind)}</span>
      <div class="min-w-0 flex-1 border-b border-beige-200 pb-3">
        <p class="text-sm text-navy-800"><b>${fmtDate(event.date)}</b> — ${esc(event.title)}</p>
        ${event.detail ? `<p class="mt-0.5 text-sm text-navy-500">${esc(event.detail)}</p>` : ''}
        ${event.health_scale ? `<div class="mt-1">${healthBar(event.health_scale)}</div>` : ''}
        ${thumbs ? `<div class="mt-2 flex flex-wrap gap-1.5">${thumbs}</div>` : ''}
      </div>
    </li>`;
  }

  function plantModalHtml(plant, timeline, locationName, matched) {
    const events = timeline.events || [];
    const photos = timeline.photos || [];
    const harvests = events.filter((e) => e.kind === 'harvest');
    const matchedPhotos = Array.isArray(matched) ? matched : [];
    const today = new Date().toISOString().slice(0, 10);
    return `
      <div class="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 class="font-display text-2xl font-semibold text-navy-800">${esc(plant.variety_name)}</h3>
          <p class="text-sm text-navy-500">${esc(plant.species_type || '')}${plant.species_type && locationName ? ' · ' : ''}${esc(locationName || '')} · <span class="pill">${esc(plant.status || 'Growing')}</span></p>
          ${plant.notes ? `<p class="mt-2 text-sm text-navy-600">${esc(plant.notes)}</p>` : ''}
        </div>
        <div class="flex shrink-0 gap-2">
          <button type="button" class="btn-ghost text-sm" data-edit-plant="${plant.id}">Edit</button>
          <button type="button" class="btn-ghost" data-close aria-label="Close">×</button>
        </div>
      </div>

      <div class="grid gap-6 lg:grid-cols-5">
        <div class="space-y-6 lg:col-span-3">
          <section>
            <h4 class="mb-2 font-display text-lg font-semibold">Timeline</h4>
            ${events.length ? `<ul class="space-y-3">${events.map(timelineEventHtml).join('')}</ul>`
              : '<p class="text-sm text-navy-400">Nothing logged yet. Observations, feedings, waterings, and harvests linked to this plant will appear here.</p>'}
          </section>
          ${photos.length ? `
          <section>
            <h4 class="mb-2 font-display text-lg font-semibold">Growth timelapse <span class="pill ml-1">${photos.length} photos</span></h4>
            <div class="overflow-hidden rounded-xl bg-navy-900 ring-1 ring-navy-700">
              <img data-tl-img class="h-64 w-full object-contain sm:h-80" alt="Timelapse frame" />
              <div class="flex flex-wrap items-center gap-2 px-3 py-2">
                <button type="button" class="btn-ghost !border-navy-600 !text-beige-100 text-xs" data-tl-prev>←</button>
                <button type="button" class="btn-ghost !border-navy-600 !text-beige-100 text-xs" data-tl-play>▶ Play</button>
                <button type="button" class="btn-ghost !border-navy-600 !text-beige-100 text-xs" data-tl-next>→</button>
                <select data-tl-speed class="inp !w-auto !border-navy-600 !bg-navy-800 !text-beige-100 text-xs">
                  <option value="600">Fast</option>
                  <option value="1500" selected>Normal</option>
                  <option value="3000">Slow</option>
                </select>
                <span data-tl-caption class="text-xs text-sage-200"></span>
                <span data-tl-counter class="ml-auto text-xs text-sage-200"></span>
              </div>
            </div>
          </section>` : ''}
        </div>
        <div class="space-y-6 lg:col-span-2">
          <section class="rounded-xl border border-beige-200 bg-beige-50 p-4">
            <h4 class="mb-2 font-display text-lg font-semibold">Care schedule</h4>
            <div class="grid grid-cols-2 gap-3">
              <div><label class="lbl" for="care-water">Water every (days)</label><input id="care-water" type="number" min="1" max="365" class="inp" value="${plant.water_every_days ?? ''}" placeholder="—" /></div>
              <div><label class="lbl" for="care-feed">Feed every (days)</label><input id="care-feed" type="number" min="1" max="365" class="inp" value="${plant.feed_every_days ?? ''}" placeholder="—" /></div>
            </div>
            <button type="button" class="btn-primary mt-3 text-sm" data-save-care="${plant.id}">Save schedule</button>
            <p class="mt-2 text-xs text-navy-400">Reminders appear up top when watering or feeding is due.</p>
          </section>
          <section>
            <h4 class="mb-2 font-display text-lg font-semibold">Photos <span class="pill ml-1">${matchedPhotos.length}</span></h4>
            ${matchedPhotos.length ? `<div class="flex flex-wrap gap-1.5">${matchedPhotos.map((img) => `<button type="button" data-lightbox="${esc(img.file_path)}"><img src="${esc(img.file_path)}" class="h-16 w-16 rounded-lg object-cover" alt="${esc(img.taken_at ? fmtDate(img.taken_at) : (img.title || 'Plant photo'))}" loading="lazy" title="${esc(img.taken_at ? fmtDate(img.taken_at) : '')}"></button>`).join('')}</div>
            <p class="mt-2 text-xs text-navy-400"><a href="/match" class="underline">Match more photos</a> to this plant.</p>`
              : '<p class="mb-1 text-sm text-navy-400">No photos matched yet. <a href="/match" class="underline">Match photos</a> to build this gallery.</p>'}
          </section>
          <section>
            <h4 class="mb-2 font-display text-lg font-semibold">Harvests <span class="pill ml-1">${harvests.length}</span></h4>
            ${harvests.length ? `<ul class="mb-3 space-y-1.5 text-sm">${harvests.map((h) => `<li class="flex justify-between gap-2"><span>🧺 ${esc(h.title.replace('Harvested ', ''))}</span><span class="text-navy-400">${fmtDate(h.date)}</span></li>`).join('')}</ul>` : '<p class="mb-3 text-sm text-navy-400">No harvests logged yet.</p>'}
            <form data-harvest-form="${plant.id}" class="grid grid-cols-2 gap-2 rounded-xl border border-beige-200 bg-beige-50 p-3">
              <div><label class="lbl">Date</label><input type="date" class="inp text-sm" data-hv-date value="${today}" required /></div>
              <div><label class="lbl">Quantity</label><input type="number" min="1" value="1" class="inp text-sm" data-hv-qty required /></div>
              <div><label class="lbl">Unit</label><select class="inp text-sm" data-hv-unit><option>fruit</option><option>bunch</option><option>head</option><option>handful</option><option>oz</option><option>g</option><option>lb</option><option>kg</option></select></div>
              <div><label class="lbl">Weight</label><div class="flex gap-1"><input type="number" min="0" step="0.1" class="inp text-sm" data-hv-weight placeholder="optional" /><select class="inp text-sm w-20 shrink-0" data-hv-weight-unit><option>oz</option><option>g</option><option>lb</option><option>kg</option></select></div></div>
              <div class="col-span-2"><label class="lbl">Notes</label><input class="inp text-sm" data-hv-notes maxlength="200" placeholder="optional" /></div>
              <p class="col-span-2 text-xs text-navy-400">Tip: pick a weight unit above and the weight fills itself in — or count pieces and add the weighed total here.</p>
              <button type="submit" class="btn-primary col-span-2 text-sm">Log harvest</button>
            </form>
          </section>
          <section>
            <button type="button" class="btn-ghost text-sm text-red-700" data-delete-plant="${plant.id}">Delete plant</button>
          </section>
        </div>
      </div>`;
  }

  function wireTimelapse(root, photos) {
    const img = $('[data-tl-img]', root);
    if (!img || !photos.length) return;
    const caption = $('[data-tl-caption]', root);
    const counter = $('[data-tl-counter]', root);
    const playBtn = $('[data-tl-play]', root);
    let index = 0;
    let timer = null;
    const speed = () => Number($('[data-tl-speed]', root)?.value || 1500);
    function render() {
      const photo = photos[index];
      img.src = photo.file_path;
      img.alt = photo.caption || `Growth photo ${index + 1}`;
      caption.textContent = fmtDate(photo.date);
      counter.textContent = `${index + 1} / ${photos.length}`;
      const preload = new Image();
      preload.src = photos[(index + 1) % photos.length].file_path;
    }
    function go(delta) { index = (index + delta + photos.length) % photos.length; render(); }
    function stop() { if (timer) clearInterval(timer); timer = null; playBtn.innerHTML = '▶ Play'; }
    function play() { stop(); timer = setInterval(() => go(1), speed()); playBtn.innerHTML = '⏸ Pause'; }
    $('[data-tl-prev]', root).addEventListener('click', () => { stop(); go(-1); });
    $('[data-tl-next]', root).addEventListener('click', () => { stop(); go(1); });
    playBtn.addEventListener('click', () => { if (timer) stop(); else play(); });
    $('[data-tl-speed]', root).addEventListener('change', () => { if (timer) play(); });
    render();
  }

  function openPlantModal(plant, timeline, locationName, matched) {
    const modal = $('#plant-modal');
    if (!modal) return;
    modal.innerHTML = `<div class="modal-backdrop" data-close></div><div class="modal-card modal-wide card" role="dialog" aria-modal="true" aria-label="${esc(plant.variety_name)}">${plantModalHtml(plant, timeline, locationName, matched)}</div>`;
    modal.classList.remove('hidden');
    modal.classList.add('modal-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    wireTimelapse(modal, timeline.photos || []);
  }

  function closePlantModal() {
    const modal = $('#plant-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    modal.classList.add('hidden');
    modal.classList.remove('modal-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = '';
    document.body.style.overflow = '';
  }

  function initPlants() {
    const grid = $('#plant-grid');
    if (!grid) return {};
    const today = new Date().toISOString().slice(0, 10);
    let plants = [];
    let locations = [];
    let editingId = null;
    let reminderByPlant = new Map();

    const locationName = (id) => (locations.find((l) => l.id === id) || {}).name || '';

    async function loadReminders() {
      const host = $('#reminders');
      const list = $('#reminder-list');
      if (!host || !list) return;
      try {
        const reminders = await api.get('/api/plants/reminders/list');
        const urgent = reminders.filter((r) => ['overdue', 'due', 'soon'].includes(r.status));
        reminderByPlant = new Map();
        urgent.forEach((r) => {
          if (!reminderByPlant.has(r.plant_id)) reminderByPlant.set(r.plant_id, []);
          reminderByPlant.get(r.plant_id).push(r);
        });
        host.classList.toggle('hidden', !urgent.length);
        list.innerHTML = urgent.map(reminderCard).join('');
      } catch { /* reminders are supplementary */ }
    }

    async function loadPlants() {
      const [fetched, locs] = await Promise.all([
        api.get('/api/plants/'),
        api.get('/api/locations/').catch(() => []),
      ]);
      plants = fetched;
      locations = locs;
      const empty = $('#plants-empty');
      if (empty) empty.classList.toggle('hidden', plants.length > 0);
      grid.innerHTML = plants.map((plant) => {
        const badges = (reminderByPlant.get(plant.id) || [])
          .filter((r) => ['overdue', 'due', 'soon'].includes(r.status))
          .map((r) => `<span class="pill ${r.status === 'overdue' ? '!bg-red-100 !text-red-800' : ''}">${r.kind === 'water' ? '💧' : '🧪'} ${esc((dueLabel(r).split('· ')[1] || r.status))}</span>`)
          .join('');
        return plantCard(plant, locationName(plant.location_id), badges);
      }).join('');
      enrichCovers();
    }

    async function enrichCovers() {
      await Promise.all(plants.map(async (plant) => {
        try {
          const timeline = await api.get(`/api/plants/${plant.id}/timeline`);
          const photos = timeline.photos || [];
          if (!photos.length) return;
          const cover = photos[photos.length - 1];
          const host = grid.querySelector(`[data-cover="${plant.id}"]`);
          if (host) host.innerHTML = `<img src="${esc(cover.file_path)}" class="h-full w-full object-cover" alt="${esc(plant.variety_name)}" loading="lazy">`;
        } catch { /* cover is decorative */ }
      }));
    }

    async function openProfile(plantId) {
      try {
        const [plant, timeline, matched] = await Promise.all([
          api.get(`/api/plants/${plantId}`),
          api.get(`/api/plants/${plantId}/timeline`),
          api.get(`/api/album-images/?plant_id=${plantId}&limit=200`).catch(() => []),
        ]);
        openPlantModal(plant, timeline, locationName(plant.location_id), Array.isArray(matched) ? matched : []);
      } catch (error) { toast(`Could not open plant: ${error.message}`, 'err'); }
    }

    function fillForm(plant) {
      editingId = plant ? plant.id : null;
      $('#plant-form-title').textContent = plant ? `Edit ${plant.variety_name}` : 'Add a plant';
      $('#plant-submit').textContent = plant ? 'Save changes' : 'Add plant';
      $('#plant-name').value = plant?.variety_name || '';
      $('#plant-species').value = plant?.species_type || '';
      $('#plant-status').value = plant?.status || 'Growing';
      $('#plant-location').value = plant?.location_id ? String(plant.location_id) : '';
      $('#plant-planted').value = (plant?.date_planted || '').slice(0, 10);
      $('#plant-maturity').value = plant?.days_to_maturity ?? '';
      $('#plant-water').value = plant?.water_every_days ?? '';
      $('#plant-feed').value = plant?.feed_every_days ?? '';
      $('#plant-notes').value = plant?.notes || '';
      $('#plant-form').classList.remove('hidden');
      $('#plant-form').scrollIntoView({ behavior: 'smooth' });
    }

    async function loadLocationOptions() {
      try {
        locations = await api.get('/api/locations/');
        const sel = $('#plant-location');
        if (sel) sel.innerHTML = '<option value="">— none —</option>'
          + locations.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
      } catch { /* locations optional */ }
    }

    $('#plant-add-toggle').addEventListener('click', () => {
      const form = $('#plant-form');
      if (form.classList.contains('hidden')) fillForm(null);
      else { form.classList.add('hidden'); editingId = null; }
    });
    $('#plant-cancel').addEventListener('click', () => { $('#plant-form').classList.add('hidden'); editingId = null; });

    $('#plant-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = $('#plant-submit');
      button.disabled = true;
      const wasEditing = editingId;
      try {
        const payload = {
          variety_name: $('#plant-name').value.trim(),
          species_type: $('#plant-species').value.trim(),
          status: $('#plant-status').value,
          location_id: $('#plant-location').value ? Number($('#plant-location').value) : null,
          date_planted: $('#plant-planted').value || null,
          days_to_maturity: $('#plant-maturity').value ? Number($('#plant-maturity').value) : null,
          water_every_days: $('#plant-water').value ? Number($('#plant-water').value) : null,
          feed_every_days: $('#plant-feed').value ? Number($('#plant-feed').value) : null,
          notes: $('#plant-notes').value.trim(),
        };
        if (editingId) await api.patch(`/api/plants/${editingId}`, payload);
        else await api.post('/api/plants/', payload);
        $('#plant-form').classList.add('hidden');
        editingId = null;
        $('#plant-form').reset();
        toast(wasEditing ? 'Plant updated 🌱' : 'Plant added 🌱', 'ok');
        await Promise.all([loadReminders(), loadPlants()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
      finally { button.disabled = false; }
    });

    document.addEventListener('click', async (event) => {
      const editBtn = event.target.closest('[data-edit-plant]');
      if (editBtn) {
        const plant = plants.find((p) => p.id === Number(editBtn.dataset.editPlant));
        closePlantModal();
        if (plant) fillForm(plant);
        return;
      }
      const waterBtn = event.target.closest('[data-water-plant]');
      if (waterBtn) {
        waterBtn.disabled = true;
        try {
          await api.post('/api/watering-logs/', { plant_id: Number(waterBtn.dataset.waterPlant), date: today });
          toast('Watering logged 💧', 'ok');
          await Promise.all([loadReminders(), loadPlants()]);
        } catch (error) { toast(`Could not log watering: ${error.message}`, 'err'); waterBtn.disabled = false; }
        return;
      }
      const feedToggle = event.target.closest('[data-feed-toggle]');
      if (feedToggle) {
        const form = document.querySelector(`[data-fed-form="${feedToggle.dataset.feedToggle}"]`);
        form?.classList.toggle('hidden');
        form?.classList.toggle('flex');
        form?.querySelector('input')?.focus();
        return;
      }
      const saveCare = event.target.closest('[data-save-care]');
      if (saveCare) {
        const id = Number(saveCare.dataset.saveCare);
        try {
          await api.patch(`/api/plants/${id}`, {
            water_every_days: $('#care-water').value ? Number($('#care-water').value) : null,
            feed_every_days: $('#care-feed').value ? Number($('#care-feed').value) : null,
          });
          toast('Care schedule saved 🌱', 'ok');
          await Promise.all([loadReminders(), loadPlants()]);
        } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
        return;
      }
      const delBtn = event.target.closest('[data-delete-plant]');
      if (delBtn && window.confirm('Delete this plant and its harvests? Logged observations stay.')) {
        try {
          await api.del(`/api/plants/${delBtn.dataset.deletePlant}`);
          closePlantModal();
          toast('Plant deleted', 'ok');
          await Promise.all([loadReminders(), loadPlants()]);
        } catch (error) { toast(`Could not delete: ${error.message}`, 'err'); }
        return;
      }
      const opener = event.target.closest('[data-open-plant]');
      if (opener) {
        await openProfile(Number(opener.dataset.openPlant));
        return;
      }
      if (event.target.closest('[data-close]')) closePlantModal();
    });

    document.addEventListener('submit', async (event) => {
      const fedForm = event.target.closest('[data-fed-form]');
      if (fedForm) {
        event.preventDefault();
        const plantId = Number(fedForm.dataset.fedForm);
        const nameInput = fedForm.querySelector('[data-fed-name]');
        const name = nameInput.value.trim();
        if (!name) return;
        try {
          await api.post('/api/fertilizations', { date: today, fertilizer_name: name, plant_id: plantId });
          toast('Feeding logged 🧪', 'ok');
          nameInput.value = '';
          await Promise.all([loadReminders(), loadPlants()]);
        } catch (error) { toast(`Could not log feeding: ${error.message}`, 'err'); }
        return;
      }
      const hvForm = event.target.closest('[data-harvest-form]');
      if (hvForm) {
        event.preventDefault();
        const q = (sel) => hvForm.querySelector(sel);
        try {
          await api.post('/api/harvests/', {
            plant_id: Number(hvForm.dataset.harvestForm),
            date: q('[data-hv-date]').value,
            quantity: Number(q('[data-hv-qty]').value),
            unit: q('[data-hv-unit]').value,
            weight: q('[data-hv-weight]').value ? Number(q('[data-hv-weight]').value) : null,
            weight_unit: q('[data-hv-weight-unit]').value,
            notes: q('[data-hv-notes]').value.trim(),
          });
          toast('Harvest logged 🧺', 'ok');
          await openProfile(Number(hvForm.dataset.harvestForm));
        } catch (error) { toast(`Could not log harvest: ${error.message}`, 'err'); }
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closePlantModal();
      if (event.key === 'Enter' && event.target.matches('[data-open-plant]')) {
        openProfile(Number(event.target.dataset.openPlant));
      }
    });

    loadLocationOptions()
      .then(() => loadReminders())
      .then(() => loadPlants())
      .then(() => loadSowCalendar())
      .then(() => {
        // NFC tag deep link: /plants?plant=<id> opens that plant's profile.
        const pid = new URLSearchParams(location.search).get('plant');
        if (pid && /^\d+$/.test(pid)) openProfile(Number(pid));
      })
      .catch((error) => toast(`Could not load plants: ${error.message}`, 'err'));
    return { plants: loadPlants };
  }

  /* ------------------------ Seed-starting calendar ------------------------ */

  function initSowCalendar() {
    const panel = $('#sow-panel');
    if (!panel) return;
    loadSowCalendar();
  }

  async function loadSowCalendar() {
    const panel = $('#sow-panel');
    if (!panel) return;
    try {
      const rows = await api.get('/api/stats/seed-calendar');
      if (!Array.isArray(rows) || !rows.length) { panel.classList.add('hidden'); return; }
      panel.classList.remove('hidden');
      $('#sow-list').innerHTML = rows.map((r) => {
        const when = r.days_until < 0
          ? `<span class="pill">${Math.abs(r.days_until)}d ago</span>`
          : r.days_until === 0
            ? '<span class="pill bg-sage-200 text-sage-800">today!</span>'
            : `<span class="pill">in ${r.days_until}d</span>`;
        const done = r.started_indoors ? `<span class="text-xs text-sage-600">✓ started ${fmtDate(r.started_indoors)}</span>` : '';
        return `<li class="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span class="text-navy-800"><b>${esc(r.variety_name)}</b> <span class="text-navy-400">· start indoors by ${fmtDate(r.suggested_start)}</span> ${done}</span>
          ${when}</li>`;
      }).join('');
    } catch (error) { /* non-fatal; panel stays hidden */ }
  }

  globalThis.Verdant.onBoot(initPlants);
})();

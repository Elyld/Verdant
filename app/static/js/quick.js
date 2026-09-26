/* Quick Log page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initQuick() {
    const host = $('#quick-groups');
    if (!host) return;
    const today = new Date().toISOString().slice(0, 10);
    $('#quick-today').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });

    function flash(btn, label) {
      const original = btn.innerHTML;
      btn.innerHTML = '✓';
      btn.disabled = true;
      setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 900);
      refreshToday();
    }

    async function waterPlant(plant, btn) {
      try {
        await api.post('/api/watering-logs/', { plant_id: plant.id, location_id: plant.location_id || null, date: today });
        toast('Watered 💧', 'ok');
        flash(btn);
      } catch (error) { toast(`Could not log watering: ${error.message}`, 'err'); }
    }

    async function waterLocation(plants, btn) {
      try {
        await Promise.all(plants.map((p) => api.post('/api/watering-logs/', { plant_id: p.id, location_id: p.location_id || null, date: today })));
        toast(`Watered ${plants.length} plants 💧`, 'ok');
        flash(btn);
      } catch (error) { toast(`Could not log watering: ${error.message}`, 'err'); }
    }

    async function logHarvest(plantId, qty, btn) {
      try {
        await api.post('/api/harvests/', { plant_id: plantId, date: today, quantity: qty });
        toast(`Harvested ${qty} 🧺`, 'ok');
        flash(btn);
      } catch (error) { toast(`Could not log harvest: ${error.message}`, 'err'); }
    }

    async function logNote(plant, text, btn) {
      try {
        await api.post('/api/observations', { plant_id: plant.id, plant_name: plant.variety_name, date: today, notes: text, health_scale: 7 });
        toast('Note logged 📝', 'ok');
        flash(btn);
      } catch (error) { toast(`Could not log note: ${error.message}`, 'err'); }
    }

    function plantCard(plant) {
      const card = document.createElement('div');
      card.className = 'card space-y-3';
      card.innerHTML = `
        <p class="font-display text-lg font-semibold text-navy-800">${esc(plant.variety_name)}</p>
        <div class="grid grid-cols-3 gap-2">
          <button type="button" data-act="water" class="rounded-xl bg-navy-700 px-2 py-4 text-2xl text-beige-50 ring-1 ring-navy-600 active:bg-navy-600" title="Log watering">💧<span class="block text-xs font-semibold">Water</span></button>
          <button type="button" data-act="harvest" class="rounded-xl bg-sage-600 px-2 py-4 text-2xl text-beige-50 ring-1 ring-sage-500 active:bg-sage-500" title="Log harvest">🧺<span class="block text-xs font-semibold">Harvest</span></button>
          <button type="button" data-act="note" class="rounded-xl bg-beige-200 px-2 py-4 text-2xl text-navy-800 ring-1 ring-beige-300 active:bg-beige-300" title="Quick note">📝<span class="block text-xs font-semibold">Note</span></button>
        </div>
        <div data-harvest-ui class="hidden items-center justify-between gap-2 rounded-xl bg-sage-50 px-3 py-2 ring-1 ring-sage-200">
          <div class="flex items-center gap-2">
            <button type="button" data-hv-dec class="rounded-lg bg-beige-200 px-3 py-2 text-lg font-bold">−</button>
            <span data-hv-qty class="w-10 text-center text-lg font-bold">1</span>
            <button type="button" data-hv-inc class="rounded-lg bg-beige-200 px-3 py-2 text-lg font-bold">+</button>
          </div>
          <button type="button" data-hv-save class="btn-primary text-sm">Log harvest</button>
        </div>
        <div data-note-ui class="hidden gap-2">
          <input type="text" data-note-text class="inp flex-1" placeholder="Quick note…" maxlength="500" />
          <button type="button" data-note-save class="btn-primary text-sm">Save</button>
        </div>`;
      let qty = 1;
      const qtyEl = card.querySelector('[data-hv-qty]');
      const harvestUi = card.querySelector('[data-harvest-ui]');
      const noteUi = card.querySelector('[data-note-ui]');
      card.querySelector('[data-act="water"]').addEventListener('click', (e) => waterPlant(plant, e.currentTarget));
      card.querySelector('[data-act="harvest"]').addEventListener('click', () => {
        noteUi.classList.add('hidden'); noteUi.classList.remove('flex');
        harvestUi.classList.toggle('hidden'); harvestUi.classList.toggle('flex');
      });
      card.querySelector('[data-act="note"]').addEventListener('click', () => {
        harvestUi.classList.add('hidden'); harvestUi.classList.remove('flex');
        noteUi.classList.toggle('hidden'); noteUi.classList.toggle('flex');
        const input = card.querySelector('[data-note-text]');
        if (!noteUi.classList.contains('hidden')) input.focus();
      });
      card.querySelector('[data-hv-dec]').addEventListener('click', () => { qty = Math.max(1, qty - 1); qtyEl.textContent = qty; });
      card.querySelector('[data-hv-inc]').addEventListener('click', () => { qty += 1; qtyEl.textContent = qty; });
      card.querySelector('[data-hv-save]').addEventListener('click', (e) => logHarvest(plant.id, qty, e.currentTarget));
      const noteInput = card.querySelector('[data-note-text]');
      card.querySelector('[data-note-save]').addEventListener('click', (e) => {
        const text = noteInput.value.trim();
        if (!text) { toast('Write the note first.', 'err'); return; }
        logNote(plant, text, e.currentTarget);
        noteInput.value = '';
      });
      return card;
    }

    async function refreshToday() {
      try {
        const [waterings, harvests, plants] = await Promise.all([
          api.get(`/api/watering-logs/?date=${today}`).catch(() => []),
          api.get(`/api/harvests/?date=${today}`).catch(() => []),
          api.get('/api/plants/').catch(() => []),
        ]);
        const names = new Map((Array.isArray(plants) ? plants : []).map((p) => [p.id, p.variety_name]));
        const items = [];
        (Array.isArray(waterings) ? waterings : []).forEach((w) => items.push(`💧 Watered ${esc(names.get(w.plant_id) || 'plant')}`));
        (Array.isArray(harvests) ? harvests : []).forEach((h) => items.push(`🧺 Harvested ${h.quantity} from ${esc(names.get(h.plant_id) || 'plant')}`));
        $('#quick-today-log').innerHTML = items.length
          ? items.map((i) => `<li>${i}</li>`).join('')
          : '<li class="text-navy-400">Nothing yet — go touch grass.</li>';
      } catch { /* non-fatal */ }
    }

    async function load() {
      const params = new URLSearchParams(location.search);
      const onlyPlant = params.get('plant') ? Number(params.get('plant')) : null;
      const onlyLocation = params.get('location') ? Number(params.get('location')) : null;
      const action = params.get('action');
      const [plants, locations] = await Promise.all([
        api.get('/api/plants/'),
        api.get('/api/locations/').catch(() => []),
      ]);
      let growing = (Array.isArray(plants) ? plants : []).filter((p) => p.status === 'Growing');
      // NFC tag prefill: narrow to one plant or one location.
      if (onlyPlant) growing = growing.filter((p) => p.id === onlyPlant);
      if (onlyLocation) growing = growing.filter((p) => p.location_id === onlyLocation);
      const locName = new Map((Array.isArray(locations) ? locations : []).map((l) => [l.id, l.name]));
      const groups = new Map();
      growing.forEach((p) => {
        const key = p.location_id || 0;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(p);
      });
      host.innerHTML = '';
      if (!growing.length) {
        host.innerHTML = '<p class="card text-center text-navy-500">No growing plants yet.</p>';
        return;
      }
      [...groups.entries()].sort((a, b) => a[0] - b[0]).forEach(([locId, plist]) => {
        const section = document.createElement('section');
        section.className = 'space-y-3';
        const header = document.createElement('div');
        header.className = 'flex items-center justify-between gap-2';
        header.innerHTML = `<h3 class="font-display text-lg font-semibold text-navy-800">${esc(locName.get(locId) || (locId ? 'Unknown location' : 'No location'))}</h3>`;
        const waterAll = document.createElement('button');
        waterAll.type = 'button';
        waterAll.className = 'btn-ghost text-sm';
        waterAll.textContent = `💧 Water all (${plist.length})`;
        waterAll.addEventListener('click', () => waterLocation(plist, waterAll));
        header.appendChild(waterAll);
        section.appendChild(header);
        const grid = document.createElement('div');
        grid.className = 'grid gap-3 sm:grid-cols-2';
        plist.forEach((p) => grid.appendChild(plantCard(p)));
        section.appendChild(grid);
        host.appendChild(section);
      });
      refreshToday();
      // NFC tag prefill: spotlight the relevant action button.
      if (action === 'water' || action === 'harvest') {
        const btn = host.querySelector(`[data-act="${action}"]`);
        if (btn) {
          btn.scrollIntoView({ block: 'center', behavior: 'smooth' });
          btn.classList.add('ring-4', 'ring-sage-300');
          setTimeout(() => btn.classList.remove('ring-4', 'ring-sage-300'), 4000);
        }
      }
    }

    load().catch((error) => toast(`Could not load plants: ${error.message}`, 'err'));
  }

  /* ------------------------------ Costs ------------------------------ */

  globalThis.Verdant.onBoot(initQuick);
})();

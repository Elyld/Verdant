/* Quick Log page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, todayLocal, getSettings } = globalThis.Verdant;

  function initQuick() {
    const host = $('#quick-groups');
    if (!host) return;
    const today = todayLocal();
    $('#quick-today').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });

    function flash(btn, label) {
      const original = btn.innerHTML;
      btn.innerHTML = '✓';
      btn.disabled = true;
      setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 900);
      refreshToday();
    }

    // Toast with an Undo button (~8s). undoFn should delete whatever was
    // just created; failures surface as an error toast.
    function undoToast(message, undoFn) {
      const host = $('#toasts');
      if (!host) { toast(message, 'ok'); return; }
      const el = document.createElement('div');
      el.className = 'pointer-events-auto flex items-center justify-between gap-3 rounded-xl bg-sage-700 px-4 py-3 text-sm text-beige-50 shadow-botanical ring-1 ring-sage-500';
      const label = document.createElement('span');
      label.textContent = message;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'shrink-0 rounded-lg bg-beige-50/20 px-3 py-1.5 text-sm font-semibold text-beige-50 ring-1 ring-beige-50/40 active:bg-beige-50/30';
      btn.textContent = '↩ Undo';
      el.append(label, btn);
      host.append(el);
      const timer = setTimeout(() => el.remove(), 8000);
      btn.addEventListener('click', async () => {
        clearTimeout(timer);
        btn.disabled = true;
        btn.textContent = '…';
        try {
          await undoFn();
          toast('Undone.', 'info');
        } catch (error) { toast(`Could not undo: ${error.message}`, 'err'); }
        el.remove();
        refreshToday();
      });
    }

    async function waterPlant(plant, btn) {
      try {
        const created = await api.post('/api/watering-logs/', { plant_id: plant.id, location_id: plant.location_id || null, date: today });
        undoToast('Watered 💧', () => api.del(`/api/watering-logs/${created.id}`));
        flash(btn);
      } catch (error) { toast(`Could not log watering: ${error.message}`, 'err'); }
    }

    async function waterLocation(plants, btn) {
      try {
        const settings = await getSettings();
        if (settings.confirm_water_all !== false
            && !window.confirm(`Water all ${plants.length} plants in this location?`)) return;
        const created = await Promise.all(plants.map((p) => api.post('/api/watering-logs/', { plant_id: p.id, location_id: p.location_id || null, date: today })));
        const ids = created.map((c) => c.id).filter((id) => id != null);
        undoToast(`Watered ${plants.length} plants 💧`, () => Promise.all(ids.map((id) => api.del(`/api/watering-logs/${id}`))));
        flash(btn);
      } catch (error) { toast(`Could not log watering: ${error.message}`, 'err'); }
    }

    async function logHarvest(plantId, qty, weight, weightUnit, btn) {
      try {
        const created = await api.post('/api/harvests/', { plant_id: plantId, date: today, quantity: qty,
          weight: weight, weight_unit: weightUnit });
        undoToast(weight != null ? `Harvested ${qty} 🧺 · ${weight} ${weightUnit}` : `Harvested ${qty} 🧺`,
          () => api.del(`/api/harvests/${created.id}`));
        flash(btn);
      } catch (error) { toast(`Could not log harvest: ${error.message}`, 'err'); }
    }

    async function logNote(plant, text, btn) {
      try {
        const created = await api.post('/api/observations', { plant_id: plant.id, plant_name: plant.variety_name, date: today, notes: text, health_scale: 7 });
        undoToast('Note logged 📝', () => api.del(`/api/observations/${created.id}`));
        flash(btn);
      } catch (error) { toast(`Could not log note: ${error.message}`, 'err'); }
    }

    function quickPlantCard(plant, defaultWeightUnit) {
      const card = document.createElement('div');
      card.className = 'card space-y-3';
      card.innerHTML = `
        <p class="font-display text-lg font-semibold text-navy-800">${esc(plant.variety_name)}</p>
        <div class="grid grid-cols-3 gap-2">
          <button type="button" data-act="water" class="rounded-xl bg-navy-700 px-2 py-4 text-2xl text-beige-50 ring-1 ring-navy-600 active:bg-navy-600" title="Log watering">💧<span class="block text-xs font-semibold">Water</span></button>
          <button type="button" data-act="harvest" class="rounded-xl bg-sage-600 px-2 py-4 text-2xl text-beige-50 ring-1 ring-sage-500 active:bg-sage-500" title="Log harvest">🧺<span class="block text-xs font-semibold">Harvest</span></button>
          <button type="button" data-act="note" class="rounded-xl bg-beige-200 px-2 py-4 text-2xl text-navy-800 ring-1 ring-beige-300 active:bg-beige-300" title="Quick note">📝<span class="block text-xs font-semibold">Note</span></button>
        </div>
        <div data-harvest-ui class="hidden flex-col gap-2 rounded-xl bg-sage-50 px-3 py-2 ring-1 ring-sage-200">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <button type="button" data-hv-dec class="rounded-lg bg-beige-200 px-3 py-2 text-lg font-bold">−</button>
              <span data-hv-qty class="w-10 text-center text-lg font-bold">1</span>
              <button type="button" data-hv-inc class="rounded-lg bg-beige-200 px-3 py-2 text-lg font-bold">+</button>
            </div>
            <div class="flex items-center gap-1">
              <input type="number" min="0" step="0.1" data-hv-weight class="inp w-24 text-sm" placeholder="weight" />
              <select data-hv-weight-unit class="inp w-[4.5rem] shrink-0 text-sm"><option>oz</option><option>g</option><option>lb</option><option>kg</option></select>
            </div>
          </div>
          <button type="button" data-hv-save class="btn-primary w-full text-sm">Log harvest</button>
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
      card.querySelector('[data-hv-save]').addEventListener('click', (e) => {
        const wRaw = card.querySelector('[data-hv-weight]').value.trim();
        const weight = wRaw === '' ? null : Number(wRaw);
        const weightUnit = card.querySelector('[data-hv-weight-unit]').value;
        logHarvest(plant.id, qty, weight, weightUnit, e.currentTarget);
      });
      const unitSel = card.querySelector('[data-hv-weight-unit]');
      if (unitSel && defaultWeightUnit) unitSel.value = defaultWeightUnit;
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
      // Prefill the harvest weight unit from Preferences (mirrors the Plants page form).
      let defaultWeightUnit = 'oz';
      try { defaultWeightUnit = (await getSettings()).default_weight_unit || 'oz'; } catch { /* preference is supplementary */ }
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
        plist.forEach((p) => grid.appendChild(quickPlantCard(p, defaultWeightUnit)));
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

  globalThis.Verdant.onBoot(initQuick);
})();

/* "Tell Verdant what you did" — local-model sentence → draft log entries. */
(() => {
  'use strict';

  const { $, esc, api, toast, todayLocal } = globalThis.Verdant;

  const AI_ACTIONS = {
    water: { icon: '💧', label: 'Water' },
    fertilize: { icon: '🧪', label: 'Feed' },
    observe: { icon: '👁️', label: 'Observe' },
    harvest: { icon: '🧺', label: 'Harvest' },
    pest: { icon: '🐛', label: 'Pest' },
    note: { icon: '📝', label: 'Note' },
  };

  function initAiLog() {
    const card = $('#ai-log-card');
    if (!card) return;
    const off = $('#ai-log-off');
    const form = $('#ai-log-form');
    const textEl = $('#ai-log-text');
    const goBtn = $('#ai-log-go');
    const draftsEl = $('#ai-log-drafts');
    const actionsEl = $('#ai-log-actions');
    let plants = [];
    let drafts = [];

    async function boot() {
      let status;
      try {
        status = await api.get('/api/ai/status');
      } catch { return; } // card stays hidden when the backend is unreachable
      if (!status || !status.enabled) return; // disabled → hidden, no nagging
      card.classList.remove('hidden');
      if (!status.reachable) {
        form.classList.add('hidden');
        off.classList.remove('hidden');
        off.textContent = status.hint || 'The model server is not reachable — check Settings → Local AI.';
        return;
      }
      try {
        plants = (await api.get('/api/plants/')).filter((p) => p.status === 'Growing');
      } catch { plants = []; }
    }

    function plantOptions(selectedId) {
      return plants.map((p) =>
        `<option value="${p.id}"${p.id === selectedId ? ' selected' : ''}>${esc(p.variety_name)}</option>`).join('');
    }

    function draftCard(d, idx) {
      const meta = AI_ACTIONS[d.action] || AI_ACTIONS.note;
      const el = document.createElement('div');
      el.className = 'rounded-xl bg-beige-100 px-3 py-2 ring-1 ring-beige-300 space-y-2';
      el.dataset.idx = idx;
      const extra = [];
      if (d.action === 'fertilize') {
        extra.push(`<label class="block"><span class="lbl">Product</span><input data-f="detail" class="inp text-sm" value="${esc(d.detail || '')}" maxlength="120" placeholder="e.g. fish emulsion" /></label>`);
        extra.push(`<div class="grid grid-cols-2 gap-2">
          <label class="block"><span class="lbl">Amount</span><input data-f="amount" type="number" min="0" step="any" class="inp text-sm" value="${d.amount ?? ''}" /></label>
          <label class="block"><span class="lbl">Unit</span><input data-f="unit" class="inp text-sm" value="${esc(d.unit || '')}" maxlength="12" placeholder="oz" /></label>
        </div>`);
      } else if (d.action === 'pest') {
        extra.push(`<label class="block"><span class="lbl">Pest</span><input data-f="detail" class="inp text-sm" value="${esc(d.detail || '')}" maxlength="120" placeholder="e.g. aphids" /></label>`);
      } else if (d.action === 'harvest') {
        extra.push(`<label class="block"><span class="lbl">Quantity</span><input data-f="amount" type="number" min="1" step="1" class="inp text-sm" value="${Math.max(1, Math.round(d.amount || 1))}" /></label>`);
      }
      el.innerHTML =
        `<div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-navy-800">${meta.icon} ${meta.label}</span>
          <button type="button" data-remove class="btn-ghost px-2 py-1 text-sm" title="Remove draft">✕</button>
        </div>
        <label class="block"><span class="lbl">Plant</span>
          <select data-f="plant_id" class="inp text-sm">
            <option value="">— pick —</option>${plantOptions(d.plant_id)}
          </select></label>
        ${extra.join('')}
        <label class="block"><span class="lbl">Notes</span><input data-f="notes" class="inp text-sm" value="${esc(d.notes || '')}" maxlength="500" /></label>`;
      el.querySelector('[data-remove]').addEventListener('click', () => {
        drafts.splice(idx, 1);
        renderDrafts();
      });
      return el;
    }

    function renderDrafts() {
      draftsEl.innerHTML = '';
      drafts.forEach((d, i) => draftsEl.appendChild(draftCard(d, i)));
      actionsEl.classList.toggle('hidden', drafts.length === 0);
      actionsEl.classList.toggle('flex', drafts.length > 0);
    }

    function readCard(el, d) {
      const val = (name) => {
        const input = el.querySelector(`[data-f="${name}"]`);
        return input ? input.value.trim() : '';
      };
      const plantId = Number(val('plant_id')) || null;
      d.plant_id = plantId;
      d.plant_name = (plants.find((p) => p.id === plantId) || {}).variety_name || null;
      d.notes = val('notes');
      d.detail = val('detail') || null;
      const amount = val('amount');
      d.amount = amount === '' ? null : Number(amount);
      d.unit = val('unit') || null;
    }

    async function interpret() {
      const text = textEl.value.trim();
      if (!text) { toast('Say what you did first.', 'err'); return; }
      goBtn.disabled = true;
      goBtn.textContent = 'Thinking…';
      try {
        const res = await api.post('/api/ai/interpret', { text });
        drafts = res.drafts || [];
        renderDrafts();
        if (!drafts.length) {
          toast(res.message || 'Nothing loggable in there.', 'err');
        } else {
          toast(`${drafts.length} draft${drafts.length === 1 ? '' : 's'} — review and confirm.`, 'ok');
        }
      } catch (error) {
        toast(error.message || 'The model did not answer.', 'err');
      } finally {
        goBtn.disabled = false;
        goBtn.textContent = 'Interpret → drafts';
      }
    }

    async function confirm() {
      const today = todayLocal();
      // Pull any user edits from the cards back into the drafts.
      [...draftsEl.children].forEach((el) => {
        const d = drafts[Number(el.dataset.idx)];
        if (d) readCard(el, d);
      });
      let saved = 0;
      const problems = [];
      for (const d of drafts) {
        if (!d.plant_id && d.action !== 'note') {
          problems.push(`${(AI_ACTIONS[d.action] || {}).label || d.action}: pick a plant`);
          continue;
        }
        try {
          if (d.action === 'water') {
            await api.post('/api/watering-logs/', { plant_id: d.plant_id, date: today });
          } else if (d.action === 'fertilize') {
            if (!d.detail) { problems.push('Feed: product is required'); continue; }
            await api.post('/api/fertilizations', {
              date: today, fertilizer_name: d.detail,
              amount_used: [d.amount ?? '', d.unit ?? ''].filter((x) => x !== '').join(' '),
              notes: d.notes || '', plant_id: d.plant_id,
            });
          } else if (d.action === 'harvest') {
            await api.post('/api/harvests/', {
              plant_id: d.plant_id, date: today,
              quantity: Math.max(1, Math.round(d.amount || 1)), notes: d.notes || '',
            });
          } else if (d.action === 'pest') {
            if (!d.detail) { problems.push('Pest: pest name is required'); continue; }
            await api.post('/api/pests/', {
              date: today, pest_name: d.detail, plant_id: d.plant_id, notes: d.notes || '',
            });
          } else { // observe / note
            const pname = d.plant_name || (plants.find((p) => p.id === d.plant_id) || {}).variety_name;
            if (!pname) { problems.push('Note: pick a plant'); continue; }
            await api.post('/api/observations', {
              plant_id: d.plant_id, plant_name: pname, date: today,
              notes: d.notes || '(no note)', health_scale: 7,
            });
          }
          saved += 1;
        } catch (error) {
          problems.push(`${(AI_ACTIONS[d.action] || {}).label || d.action}: ${error.message}`);
        }
      }
      if (saved) toast(`Saved ${saved} entr${saved === 1 ? 'y' : 'ies'} ✓`, 'ok');
      if (problems.length) toast(problems.join(' · '), 'err');
      drafts = [];
      renderDrafts();
      textEl.value = '';
    }

    goBtn.addEventListener('click', interpret);
    $('#ai-log-cancel').addEventListener('click', () => {
      drafts = [];
      renderDrafts();
      textEl.value = '';
    });
    $('#ai-log-confirm').addEventListener('click', confirm);

    // ---- Voice input: dictate into the textarea (Web Speech API — the
    // browser transcribes on-device/in-browser, nothing is sent to Verdant).
    // Toggle: tap 🎤 Talk, keep talking, tap ⏹ Stop. Sessions auto-restart
    // on pauses so it keeps listening until you stop it.
    const micBtn = $('#ai-log-mic');
    if (micBtn) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) {
        // e.g. plain http on the LAN is not a secure context — explain on
        // tap instead of nagging.
        micBtn.classList.add('opacity-50');
        micBtn.addEventListener('click', () => toast(
          'Voice input needs a secure (https) connection — it works through the Cloudflare tunnel, not plain LAN http.', 'err'));
      } else {
        let rec = null;
        let listening = false;
        let prefix = '';
        let sessionFinal = '';
        let lastStart = 0;
        const setMicUI = () => {
          micBtn.innerHTML = listening ? '⏹ Stop' : '🎤 Talk';
          micBtn.classList.toggle('mic-live', listening);
          micBtn.setAttribute('aria-pressed', listening ? 'true' : 'false');
        };
        const renderText = (interim) => {
          textEl.value = [prefix, sessionFinal, interim]
            .filter((s) => s && s.trim()).join(' ').replace(/\s+/g, ' ');
        };
        const stopListening = () => {
          listening = false;
          try { if (rec) rec.stop(); } catch (e) { /* already stopped */ }
          rec = null;
          setMicUI();
        };
        const startRec = () => {
          rec = new SR();
          rec.lang = 'en-US';
          rec.interimResults = true;
          rec.continuous = true;
          rec.onresult = (e) => {
            let interim = '';
            for (let i = e.resultIndex; i < e.results.length; i++) {
              const t = e.results[i][0].transcript;
              if (e.results[i].isFinal) sessionFinal += t;
              else interim += t;
            }
            renderText(interim);
          };
          rec.onerror = (e) => {
            const err = (e && e.error) || '';
            if (err === 'not-allowed' || err === 'service-not-allowed') {
              stopListening();
              toast('Microphone blocked — allow mic access for this site and try again.', 'err');
            } else if (err === 'audio-capture') {
              stopListening();
              toast('No microphone found on this device.', 'err');
            }
            // 'no-speech', 'network', 'aborted': onend restarts quietly.
          };
          rec.onend = () => {
            if (!listening) return;
            // Browsers end sessions on pauses even with continuous=true —
            // restart, but bail on a hot error loop.
            if (Date.now() - lastStart < 300) { stopListening(); return; }
            lastStart = Date.now();
            try { rec.start(); } catch (e) { stopListening(); }
          };
          lastStart = Date.now();
          try {
            rec.start();
          } catch (e) {
            stopListening();
            toast('Could not start voice input.', 'err');
          }
        };
        micBtn.addEventListener('click', () => {
          if (listening) { stopListening(); return; }
          prefix = textEl.value.trim();
          sessionFinal = '';
          listening = true;
          setMicUI();
          startRec();
          if (listening) toast('Listening… tap ⏹ Stop when you are done.', 'ok');
        });
        setMicUI();
      }
    }

    boot();
  }

  globalThis.Verdant.onBoot(initAiLog);
})();

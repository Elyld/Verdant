/* Voice quick-log — speak a simple command, tap once to save.
   The no-AI sibling of the "Tell Verdant what you did" card: plain
   command parsing ("watered the tomatoes") instead of a local model,
   so it works even when the model server is offline. Web Speech API
   for transcription; everything parsed stays in the browser. */
(() => {
  'use strict';

  const V = globalThis.Verdant || {};
  const { $, esc, api, toast, todayLocal, onBoot } = V;

  /* ------------------------- command parser (pure) ------------------------- */
  const WATER_RE = /\b(water|watered|watering)\b/;
  const FEED_RE = /\b(feed|fed|fertilize|fertilized|fertilizing)\b/;
  const HARVEST_RE = /\b(harvest|harvested|harvesting|pick|picked|picking)\b/;

  /**
   * Parse a spoken command into a log draft.
   * @param {string} text spoken transcript
   * @param {Array} plants growing plants: [{id, variety_name, species_type}]
   * @returns {{action, text, qty, plant_id, plant_name}}
   *   action is "water" | "fertilize" | "harvest" | "note".
   */
  function parseVoiceCommand(text, plants) {
    const raw = (text || '').trim();
    const t = ` ${raw.toLowerCase()} `;
    const list = Array.isArray(plants) ? plants : [];

    let action = 'note';
    if (WATER_RE.test(t)) action = 'water';
    else if (FEED_RE.test(t)) action = 'fertilize';
    else if (HARVEST_RE.test(t)) action = 'harvest';

    let qty = null;
    const qm = t.match(/(\d+(?:\.\d+)?)/);
    if (qm) qty = parseFloat(qm[1]);

    // Longest variety/species substring wins. Substring matching handles
    // plurals ("tomatoes" contains "tomato") without a stemmer; individual
    // significant words catch "peppers" for a "Bell Pepper" plant.
    // Full-name matches score double so "basil" beats a stray "pepper".
    let best = null;
    for (const p of list) {
      const cands = [p.variety_name, p.species_type]
        .filter((s) => typeof s === 'string')
        .map((s) => s.toLowerCase().trim())
        .filter((s) => s.length > 2);
      for (const c of cands) {
        if (t.includes(c)) {
          if (!best || c.length * 2 > best.score) best = { plant: p, score: c.length * 2 };
          continue;
        }
        for (const w of c.split(/[^a-z]+/).filter((w) => w.length >= 4)) {
          if (t.includes(w) && (!best || w.length > best.score)) {
            best = { plant: p, score: w.length };
          }
        }
      }
    }
    return {
      action,
      text: raw,
      qty,
      plant_id: best ? best.plant.id : null,
      plant_name: best ? (best.plant.variety_name || best.plant.species_type) : null,
    };
  }

  /* ------------------------------ UI wiring ------------------------------ */
  const ACTION_META = {
    water: { icon: '💧', label: 'Water' },
    fertilize: { icon: '🧪', label: 'Feed' },
    harvest: { icon: '🧺', label: 'Harvest' },
    note: { icon: '📝', label: 'Note' },
  };

  function initVoiceLog() {
    if (typeof document === 'undefined' || !$) return;
    const card = $('#voice-log-card');
    if (!card) return;
    const btn = $('#voice-btn');
    const transcriptEl = $('#voice-transcript');
    const draftEl = $('#voice-draft');
    const hintEl = $('#voice-hint');
    let plants = [];
    let lastFertilizer = '';

    async function boot() {
      try {
        plants = (await api.get('/api/plants/')).filter((p) => p.status === 'Growing');
      } catch { plants = []; }
      try {
        const feeds = await api.get('/api/fertilizations/');
        if (Array.isArray(feeds) && feeds.length) {
          lastFertilizer = feeds[0].fertilizer_name || '';
        }
      } catch { /* optional */ }
    }
    boot();

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      btn.classList.add('opacity-50');
      btn.addEventListener('click', () => toast(
        'Voice input needs a secure (https) connection — it works through the Cloudflare tunnel, not plain LAN http.', 'err'));
      return;
    }

    let rec = null;
    let listening = false;
    let finalText = '';
    let lastStart = 0;

    const setUI = () => {
      btn.innerHTML = listening ? '⏹ Stop & parse' : '🎙️ Talk';
      btn.classList.toggle('mic-live', listening);
      btn.setAttribute('aria-pressed', listening ? 'true' : 'false');
    };
    const stopListening = (parse) => {
      listening = false;
      try { if (rec) rec.stop(); } catch { /* already stopped */ }
      rec = null;
      setUI();
      if (parse) parseDraft();
    };
    const startRec = () => {
      finalText = '';
      transcriptEl.value = '';
      draftEl.innerHTML = '';
      rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      rec.onresult = (e) => {
        let interim = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const tr = e.results[i][0].transcript;
          if (e.results[i].isFinal) finalText += tr;
          else interim += tr;
        }
        transcriptEl.value = `${finalText} ${interim}`.trim();
      };
      rec.onerror = (e) => {
        const err = (e && e.error) || '';
        if (err === 'not-allowed' || err === 'service-not-allowed') {
          stopListening(false);
          toast('Microphone blocked — allow mic access for this site and try again.', 'err');
        } else if (err === 'audio-capture') {
          stopListening(false);
          toast('No microphone found on this device.', 'err');
        }
      };
      rec.onend = () => {
        if (!listening) return;
        if (Date.now() - lastStart < 300) { stopListening(false); return; }
        lastStart = Date.now();
        try { rec.start(); } catch { stopListening(false); }
      };
      listening = true;
      lastStart = Date.now();
      setUI();
      hintEl.textContent = 'Listening… say something like "watered the tomatoes". Tap Stop when done.';
      try { rec.start(); } catch { stopListening(false); }
    };

    function parseDraft() {
      const text = (finalText || transcriptEl.value || '').trim();
      if (!text) {
        hintEl.textContent = 'Didn\'t catch that — try again.';
        return;
      }
      const d = parseVoiceCommand(text, plants);
      renderDraft(d);
    }

    function renderDraft(d) {
      const meta = ACTION_META[d.action] || ACTION_META.note;
      const extras = [];
      if (d.action === 'harvest') {
        extras.push(`<label class="block"><span class="lbl">Quantity</span><input id="voice-qty" type="number" min="1" step="1" class="inp text-sm" value="${Math.max(1, Math.round(d.qty || 1))}" /></label>`);
      } else if (d.action === 'fertilize') {
        extras.push(`<label class="block"><span class="lbl">Product</span><input id="voice-product" class="inp text-sm" value="${esc(lastFertilizer)}" maxlength="120" placeholder="e.g. fish emulsion" /></label>`);
      }
      const plantLine = d.plant_name
        ? `<span class="font-semibold">${esc(d.plant_name)}</span>`
        : `<span class="text-amber-700">no plant matched — ${d.action === 'note' ? 'saving as a general note' : 'pick one or rephrase'}</span>`;
      draftEl.innerHTML =
        `<div class="rounded-xl bg-beige-100 px-3 py-2 ring-1 ring-beige-300 space-y-2">` +
        `<p class="text-sm text-navy-700">${meta.icon} <strong>${meta.label}</strong> · ${plantLine}</p>` +
        `<p class="text-xs text-navy-400">Heard: “${esc(d.text)}”</p>` +
        extras.join('') +
        (d.action !== 'note' && !d.plant_id
          ? `<label class="block"><span class="lbl">Plant</span><select id="voice-plant" class="inp text-sm">` +
            plants.map((p) => `<option value="${p.id}">${esc(p.variety_name)}</option>`).join('') +
            `</select></label>`
          : '') +
        `<div class="flex gap-2">` +
        `<button type="button" id="voice-save" class="btn-primary text-sm">Save</button>` +
        `<button type="button" id="voice-discard" class="btn-ghost text-sm">Discard</button>` +
        `</div></div>`;
      $('#voice-discard').addEventListener('click', () => { draftEl.innerHTML = ''; });
      $('#voice-save').addEventListener('click', () => saveDraft(d));
    }

    async function saveDraft(d) {
      const today = todayLocal();
      const plantId = d.plant_id || ($('#voice-plant') ? Number($('#voice-plant').value) : null);
      const plantName = d.plant_name || (plants.find((p) => p.id === plantId) || {}).variety_name;
      try {
        if (d.action === 'water') {
          if (!plantId) throw new Error('Pick a plant first.');
          await api.post('/api/watering-logs', { plant_id: plantId, date: today, method: 'voice', notes: d.text });
        } else if (d.action === 'fertilize') {
          if (!plantId) throw new Error('Pick a plant first.');
          const product = ($('#voice-product') || {}).value || '';
          if (!product.trim()) throw new Error('Add the product name.');
          await api.post('/api/fertilizations', { plant_id: plantId, date: today, fertilizer_name: product.trim(), notes: `voice: ${d.text}` });
        } else if (d.action === 'harvest') {
          if (!plantId) throw new Error('Pick a plant first.');
          const qty = Math.max(1, Math.round(Number(($('#voice-qty') || {}).value) || d.qty || 1));
          await api.post('/api/harvests', { plant_id: plantId, date: today, quantity: qty, unit: 'fruit', notes: d.text });
        } else {
          await api.post('/api/observations', {
            plant_id: plantId || null, plant_name: plantName || 'Garden',
            date: today, notes: d.text, health_scale: 7,
          });
        }
        toast('Logged ✓', 'ok');
        draftEl.innerHTML = '';
        transcriptEl.value = '';
        hintEl.textContent = 'Say something like "watered the tomatoes", "harvested 3 peppers", "fed the basil".';
      } catch (err) {
        toast(`Could not save: ${err.message}`, 'err');
      }
    }

    btn.addEventListener('click', () => {
      if (listening) stopListening(true);
      else startRec();
    });
    setUI();
  }

  // Export the pure parser for the node test harness.
  globalThis.VerdantVoice = { parseVoiceCommand };
  if (typeof onBoot === 'function') onBoot(initVoiceLog);
})();

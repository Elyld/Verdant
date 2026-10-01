/* Floating garden-assistant chat. Bootstrapped on every page from base.html.
 *
 * The button appears when /api/ai/chat-status says the assistant is on.
 * Conversation survives page navigation within the tab (sessionStorage).
 * Draft log entries the assistant proposes render as confirm/discard cards
 * and save through the normal log endpoints — nothing is written silently.
 */
(() => {
  'use strict';

  const ACTION_META = {
    water: { label: 'Water', icon: '💧' },
    fertilize: { label: 'Feed', icon: '🧪' },
    harvest: { label: 'Harvest', icon: '🧺' },
    observe: { label: 'Observe', icon: '👀' },
    pest: { label: 'Pest', icon: '🐛' },
    note: { label: 'Note', icon: '📝' },
    reminder: { label: 'Reminder', icon: '🔔' },
    seed: { label: 'Seed packet', icon: '🌱' },
    plant_status: { label: 'Plant status', icon: '🔄' },
    plant_move: { label: 'Move plant', icon: '🪴' },
  };
  // Draft actions that don't involve picking a plant.
  const NO_PLANT_NEEDED = new Set(['note', 'seed', 'reminder']);
  const STORE_KEY = 'verdant-ai-chat';
  const MAX_STORED = 30;
  const HISTORY_SEND = 10;

  let els = {};
  let messages = [];
  let plants = [];
  let plantsById = {};
  let sending = false;

  function v() { return window.Verdant || {}; }
  function $(sel, root) { return (root || document).querySelector(sel); }

  function loadStored() {
    try {
      const raw = sessionStorage.getItem(STORE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      messages = Array.isArray(arr) ? arr.slice(-MAX_STORED) : [];
    } catch { messages = []; }
  }

  function store() {
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(messages.slice(-MAX_STORED)));
    } catch { /* storage full or blocked — chat still works */ }
  }

  function esc(s) {
    return (v().esc || ((x) => String(x == null ? '' : x)
      .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))))(s);
  }

  function todayLocal() {
    return (v().todayLocal || (() => new Date().toISOString().slice(0, 10)))();
  }

  function build() {
    const wrap = document.createElement('div');
    wrap.id = 'ai-chat-root';
    wrap.innerHTML = `
      <div id="ai-chat-scrim" class="fixed inset-0 z-30 hidden bg-navy-900/40 sm:hidden"></div>
      <button id="ai-chat-fab" type="button" aria-label="Chat with your garden assistant"
        class="fixed bottom-6 right-6 z-40 flex h-14 w-14 cursor-grab items-center justify-center rounded-full bg-sage-700 text-2xl text-beige-50 shadow-botanical ring-1 ring-sage-500 transition hover:bg-sage-600 active:cursor-grabbing">🌱</button>
      <section id="ai-chat-panel" class="fixed inset-y-0 right-0 z-40 hidden w-full max-w-sm translate-x-full flex-col overflow-hidden bg-beige-50 shadow-botanical transition-transform duration-200 sm:inset-y-auto sm:bottom-24 sm:right-6 sm:h-[min(32rem,70vh)] sm:w-[22rem] sm:max-w-[calc(100vw-2rem)] sm:translate-x-0 sm:rounded-2xl sm:ring-1 sm:ring-beige-300">
        <header class="flex items-center justify-between bg-navy-800 px-4 py-3 text-beige-50">
          <div>
            <p class="font-display text-base font-semibold">🌱 Garden assistant</p>
            <p id="ai-chat-sub" class="text-xs text-beige-300">Knows your garden · drafts need your OK</p>
          </div>
          <button id="ai-chat-close" type="button" aria-label="Close chat" class="rounded-full px-2 py-1 text-xl leading-none hover:bg-navy-700">×</button>
        </header>
        <div id="ai-chat-msgs" class="flex-1 space-y-3 overflow-y-auto px-3 py-3"></div>
        <form id="ai-chat-form" class="flex items-center gap-2 border-t border-beige-200 bg-beige-100 px-3 py-2">
          <input id="ai-chat-input" type="text" class="inp flex-1" placeholder="Ask or tell me what you did…" maxlength="2000" autocomplete="off" />
          <button id="ai-chat-send" type="submit" class="btn-primary shrink-0 px-3 py-2 text-sm">Send</button>
        </form>
      </section>`;
    document.body.appendChild(wrap);
    els = {
      fab: $('#ai-chat-fab', wrap),
      scrim: $('#ai-chat-scrim', wrap),
      panel: $('#ai-chat-panel', wrap),
      msgs: $('#ai-chat-msgs', wrap),
      form: $('#ai-chat-form', wrap),
      input: $('#ai-chat-input', wrap),
      send: $('#ai-chat-send', wrap),
      sub: $('#ai-chat-sub', wrap),
      close: $('#ai-chat-close', wrap),
    };
    els.scrim.addEventListener('click', closePanel);
    els.close.addEventListener('click', toggle);
    els.form.addEventListener('submit', onSend);
  }

  function openPanel() {
    els.scrim.classList.remove('hidden');
    els.panel.classList.remove('hidden');
    els.panel.classList.add('flex');
    els.fab.classList.add('invisible');
    // Slide the mobile sheet in (no-op on desktop: sm:translate-x-0 wins).
    requestAnimationFrame(() => requestAnimationFrame(() => {
      els.panel.classList.remove('translate-x-full');
    }));
    render();
    if (window.matchMedia && window.matchMedia('(pointer:fine)').matches) {
      els.input.focus();
    }
  }

  function closePanel() {
    els.panel.classList.add('translate-x-full');
    els.scrim.classList.add('hidden');
    els.fab.classList.remove('invisible');
    window.setTimeout(() => {
      els.panel.classList.add('hidden');
      els.panel.classList.remove('flex');
    }, 210);
  }

  function toggle() {
    if (els.panel.classList.contains('hidden')) openPanel();
    else closePanel();
  }

  // The 🌱 button can be dragged anywhere on screen (touch + mouse); a tap
  // still opens the chat. The position persists per browser.
  const FAB_POS_KEY = 'verdant-ai-fab-pos';
  const FAB_MARGIN = 8;

  function clampFab(x, y) {
    const w = els.fab.offsetWidth || 56;
    const h = els.fab.offsetHeight || 56;
    const maxX = Math.max(FAB_MARGIN, window.innerWidth - w - FAB_MARGIN);
    const maxY = Math.max(FAB_MARGIN, window.innerHeight - h - FAB_MARGIN);
    return {
      x: Math.min(Math.max(x, FAB_MARGIN), maxX),
      y: Math.min(Math.max(y, FAB_MARGIN), maxY),
    };
  }

  function applyFabPos(x, y) {
    const p = clampFab(x, y);
    els.fab.style.left = `${p.x}px`;
    els.fab.style.top = `${p.y}px`;
    els.fab.style.right = 'auto';
    els.fab.style.bottom = 'auto';
  }

  function restoreFabPos() {
    try {
      const raw = localStorage.getItem(FAB_POS_KEY);
      if (!raw) return;
      const pos = JSON.parse(raw);
      if (Number.isFinite(pos.x) && Number.isFinite(pos.y)) applyFabPos(pos.x, pos.y);
    } catch { /* no saved position — keep the default corner */ }
  }

  function enableFabDrag() {
    const fab = els.fab;
    fab.style.touchAction = 'none';
    let pid = null, startX = 0, startY = 0, baseX = 0, baseY = 0, moved = false;

    fab.addEventListener('pointerdown', (e) => {
      pid = e.pointerId;
      moved = false;
      startX = e.clientX; startY = e.clientY;
      const r = fab.getBoundingClientRect();
      baseX = r.left; baseY = r.top;
      if (fab.setPointerCapture) { try { fab.setPointerCapture(pid); } catch { /* noop */ } }
    });
    fab.addEventListener('pointermove', (e) => {
      if (e.pointerId !== pid) return;
      const dx = e.clientX - startX, dy = e.clientY - startY;
      if (!moved && Math.hypot(dx, dy) > 8) moved = true;
      if (moved) applyFabPos(baseX + dx, baseY + dy);
    });
    const finish = (e, save) => {
      if (e.pointerId !== pid) return;
      pid = null;
      if (moved) {
        moved = false;
        if (save) {
          try {
            const r = fab.getBoundingClientRect();
            localStorage.setItem(FAB_POS_KEY,
              JSON.stringify({ x: Math.round(r.left), y: Math.round(r.top) }));
          } catch { /* storage blocked — the position just won't persist */ }
        }
      } else {
        toggle();
      }
    };
    fab.addEventListener('pointerup', (e) => finish(e, true));
    fab.addEventListener('pointercancel', (e) => finish(e, false));
    fab.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
    window.addEventListener('resize', restoreFabPos);
  }

  function bubble(role, html, extraClass) {
    const div = document.createElement('div');
    div.className = role === 'user'
      ? 'ml-10 rounded-2xl rounded-br-md bg-sage-700 px-3 py-2 text-sm text-beige-50'
      : `mr-10 rounded-2xl rounded-bl-md bg-beige-100 px-3 py-2 text-sm text-navy-800 ring-1 ring-beige-200 ${extraClass || ''}`;
    div.innerHTML = html;
    return div;
  }

  function draftCard(d, msgIdx, idx) {
    const meta = ACTION_META[d.action] || ACTION_META.note;
    const el = document.createElement('div');
    el.className = 'rounded-xl bg-beige-50 px-3 py-2 ring-1 ring-sage-300 space-y-1';
    el.dataset.msg = msgIdx;
    el.dataset.idx = idx;
    const bits = [];
    if (d.action === 'reminder' && d.reminder_title) bits.push(`<strong>${esc(d.reminder_title)}</strong>`);
    if (d.plant_name) bits.push(`<strong>${esc(d.plant_name)}</strong>`);
    if (d.amount != null) bits.push(`${esc(String(d.amount))}${d.unit ? ' ' + esc(d.unit) : ''}`);
    if (d.detail) bits.push(esc(d.detail));
    let body = `<p class="text-sm text-navy-800">${meta.icon} ${meta.label}${bits.length ? ' — ' + bits.join(' · ') : ''}</p>`;
    if (d.notes) body += `<p class="text-xs text-navy-500">${esc(d.notes)}</p>`;
    if (d.action === 'note') body += `<p class="text-xs text-navy-400">Saves to Garden Logs under Notebook</p>`;
    if (!d.plant_id && !NO_PLANT_NEEDED.has(d.action)) {
      const opts = plants.map((p) =>
        `<option value="${p.id}">${esc(p.variety_name)}</option>`).join('');
      body += `<select data-plant-pick class="inp mt-1 text-sm"><option value="">Pick a plant…</option>${opts}</select>`;
    }
    body += `<div class="flex justify-end"><button type="button" data-drop class="text-xs text-navy-400 underline">remove</button></div>`;
    el.innerHTML = body;
    return el;
  }

  function render() {
    els.msgs.innerHTML = '';
    if (!messages.length) {
      els.msgs.appendChild(bubble('assistant',
        `<p>Hi! I know your garden — plants, what's due, recent logs, the weather. Ask me anything, or just tell me what you did out there and I'll draft the log entries.</p>`));
    }
    messages.forEach((m, mi) => {
      if (m.role === 'user') {
        els.msgs.appendChild(bubble('user', `<p>${esc(m.content)}</p>`));
      } else {
        const md = v().markdown || ((s) => `<p>${esc(s)}</p>`);
        els.msgs.appendChild(bubble('assistant', md(m.content)));
        (m.drafts || []).forEach((d, i) => els.msgs.appendChild(draftCard(d, mi, i)));
        if ((m.drafts || []).length) {
          const actions = document.createElement('div');
          actions.className = 'mr-10 flex gap-2';
          actions.innerHTML = `
            <button type="button" data-confirm class="btn-primary px-3 py-1.5 text-xs">Confirm &amp; save</button>
            <button type="button" data-discard class="btn-ghost px-3 py-1.5 text-xs">Discard</button>`;
          actions.dataset.msg = mi;
          els.msgs.appendChild(actions);
        }
      }
    });
    els.msgs.scrollTop = els.msgs.scrollHeight;
  }

  function draftAt(card) {
    const m = messages[Number(card.dataset.msg)];
    const d = m && m.drafts ? m.drafts[Number(card.dataset.idx)] : null;
    return { m, d };
  }

  // Draft card interactions (delegated — cards are re-rendered often).
  function wireDraftClicks() {
    els.msgs.addEventListener('click', async (event) => {
      const drop = event.target.closest('[data-drop]');
      if (drop) {
        const card = drop.closest('[data-idx]');
        if (card) {
          const { m } = draftAt(card);
          if (m) {
            m.drafts.splice(Number(card.dataset.idx), 1);
            store();
            render();
          }
        }
        return;
      }
      const confirm = event.target.closest('[data-confirm]');
      if (confirm) { await confirmDrafts(confirm.parentElement); return; }
      const discard = event.target.closest('[data-discard]');
      if (discard) {
        const m = messages[Number(discard.parentElement.dataset.msg)];
        if (m) { m.drafts = []; store(); render(); }
      }
    });
    els.msgs.addEventListener('change', (event) => {
      const pick = event.target.closest('[data-plant-pick]');
      if (!pick) return;
      const card = pick.closest('[data-idx]');
      if (!card) return;
      const { d } = draftAt(card);
      if (d) {
        d.plant_id = pick.value ? Number(pick.value) : null;
        const p = plantsById[d.plant_id];
        d.plant_name = p ? p.variety_name : d.plant_name;
        store();
      }
    });
  }

  async function confirmDrafts(actionsEl) {
    const mi = Number(actionsEl.dataset.msg);
    const m = messages[mi];
    if (!m || !m.drafts.length) return;
    const api = v().api;
    const toast = v().toast || (() => {});
    const today = todayLocal();
    let saved = 0;
    const problems = [];
    for (const d of m.drafts) {
      if (!d.plant_id && !NO_PLANT_NEEDED.has(d.action)) {
        problems.push(`${(ACTION_META[d.action] || {}).label || d.action}: pick a plant`);
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
        } else if (d.action === 'seed') {
          const year = d.seed_year ? parseInt(d.seed_year, 10) : null;
          await api.post('/api/seed-packets', {
            variety_name: d.plant_name,
            species_type: d.seed_species || '',
            vendor_name: d.seed_vendor || '',
            year_acquired: Number.isFinite(year) ? year : null,
            seed_count: d.amount ? Math.max(1, Math.round(d.amount)) : null,
            notes: d.notes || '',
          });
        } else if (d.action === 'plant_status') {
          const status = (d.detail || '').replace(/^→\s*/, '');
          await api.patch(`/api/plants/${d.plant_id}`, { status });
        } else if (d.action === 'plant_move') {
          if (d.planting_id) {
            try { await api.del(`/api/containers/plantings/${d.planting_id}`); }
            catch (e) { /* already moved or gone — just add the new one */ }
          }
          await api.post('/api/containers/plantings', {
            container_id: d.to_container_id, plant_id: d.plant_id,
          });
        } else if (d.action === 'reminder') {
          const title = (d.reminder_title || '').trim();
          const due = (d.reminder_due || '').trim();
          if (!title || !due) { problems.push('Reminder: title and date are required'); continue; }
          await api.post('/api/user-reminders', {
            title, due_date: due, notes: d.notes || '',
          });
        } else { // observe / note
          const pname = d.plant_name || (plantsById[d.plant_id] || {}).variety_name;
          if (!pname) { problems.push('Note: pick a plant'); continue; }
          await api.post('/api/observations', {
            plant_id: d.plant_id, plant_name: pname, date: today,
            notes: d.notes || '(no note)', health_scale: 7,
          });
        }
        saved += 1;
      } catch (error) {
        problems.push(`${(ACTION_META[d.action] || {}).label || d.action}: ${error.message}`);
      }
    }
    if (saved) toast(`Saved ${saved} entr${saved === 1 ? 'y' : 'ies'} ✓`, 'ok');
    if (problems.length) toast(problems.join(' · '), 'err');
    m.drafts = [];
    store();
    render();
  }

  async function onSend(event) {
    event.preventDefault();
    const text = els.input.value.trim();
    if (!text || sending) return;
    sending = true;
    els.input.value = '';
    messages.push({ role: 'user', content: text });
    store();
    render();
    const typing = bubble('assistant', '<p class="text-navy-400">thinking…</p>');
    els.msgs.appendChild(typing);
    els.msgs.scrollTop = els.msgs.scrollHeight;
    try {
      const history = messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .slice(-HISTORY_SEND)
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await v().api.post('/api/ai/chat', { message: text, history });
      messages.push({ role: 'assistant', content: res.reply || '…', drafts: res.drafts || [] });
    } catch (error) {
      messages.push({ role: 'assistant', content: `Hmm — ${error.message}` });
    } finally {
      sending = false;
      store();
      render();
      els.input.focus();
    }
  }

  async function boot() {
    let st = null;
    try { st = await v().api.get('/api/ai/chat-status'); }
    catch { return; }
    if (!st || !st.enabled) return;
    build();
    restoreFabPos();
    enableFabDrag();
    wireDraftClicks();
    loadStored();
    if (!st.reachable && !messages.length) {
      messages = [{ role: 'assistant',
        content: st.hint || "The AI provider isn't reachable — check Settings → AI." }];
    }
    try {
      plants = (await v().api.get('/api/plants/')).filter((p) => p.status === 'Growing');
      plantsById = Object.fromEntries(plants.map((p) => [p.id, p]));
    } catch { plants = []; plantsById = {}; }
    if (st.provider === 'openrouter') {
      els.sub.textContent = 'Knows your garden · via OpenRouter · drafts need your OK';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

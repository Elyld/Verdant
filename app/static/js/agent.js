/* Garden Assistant tab (/agent). Boots only on the Agent page.
 *
 * Threads, messages, and confirm-before-save drafts all live server-side,
 * so a browser refresh loses nothing. Drafts are confirmed one at a time
 * through /api/agent/drafts — nothing is ever written silently.
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
    chaos_reroll: { label: 'Chaos pick', icon: '🎲' },
    memory_write: { label: 'Memory', icon: '🧠' },
  };

  const FILE_META = {
    persona: { label: 'Persona', desc: 'Who it is and how it talks.' },
    operating_notes: { label: 'Operating notes', desc: "Lessons it's learned about your garden." },
    memory: { label: 'Memory', desc: "Facts you've told it to keep." },
  };

  const root = document.getElementById('agent-root');
  if (!root) return;

  function v() { return window.Verdant || {}; }
  function $(sel) { return root.querySelector(sel); }
  function esc(s) {
    return (v().esc || ((x) => String(x == null ? '' : x)
      .replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))))(s);
  }

  const els = {
    off: $('#agent-off'),
    grid: $('#agent-grid'),
    pill: $('#agent-status-pill'),
    threads: $('#agent-threads'),
    newBtn: $('#agent-new'),
    title: $('#agent-thread-title'),
    delBtn: $('#agent-delete'),
    msgs: $('#agent-msgs'),
    form: $('#agent-form'),
    input: $('#agent-input'),
    files: $('#agent-files'),
  };

  let currentId = null;
  let sending = false;

  function bubble(role, html) {
    const div = document.createElement('div');
    div.className = role === 'user'
      ? 'ml-10 rounded-2xl rounded-br-md bg-sage-700 px-3 py-2 text-sm text-beige-50'
      : 'mr-10 rounded-2xl rounded-bl-md bg-beige-100 px-3 py-2 text-sm text-navy-800 ring-1 ring-beige-200';
    div.innerHTML = html;
    return div;
  }

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  // ---- threads -----------------------------------------------------------

  async function loadThreads(selectId) {
    const { conversations } = await v().api.get('/api/agent/conversations');
    els.threads.innerHTML = '';
    if (!conversations.length) {
      els.threads.innerHTML = '<p class="px-2 py-3 text-sm text-navy-400">No chats yet — start one.</p>';
    }
    conversations.forEach((c) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.id = c.id;
      b.className = 'block w-full rounded-xl px-2 py-2 text-left hover:bg-beige-100' +
        (c.id === currentId ? ' bg-sage-100 ring-1 ring-sage-300' : '');
      b.innerHTML = `<p class="truncate text-sm font-semibold text-navy-800">${esc(c.title || 'New chat')}</p>` +
        `<p class="text-xs text-navy-400">${fmtTime(c.updated_at)}${c.draft_count ? ` · ⏳ ${c.draft_count}` : ''}</p>`;
      b.addEventListener('click', () => selectThread(c.id));
      els.threads.appendChild(b);
    });
    if (selectId && conversations.some((c) => c.id === selectId)) {
      await selectThread(selectId, true);
    } else if (!currentId && conversations.length) {
      await selectThread(conversations[0].id, true);
    }
  }

  async function newThread() {
    const res = await v().api.post('/api/agent/conversations', { title: '' });
    currentId = res.id;
    await loadThreads(currentId);
    els.input.focus();
  }

  async function deleteThread() {
    if (!currentId || !window.confirm('Delete this chat thread?')) return;
    await v().api.del(`/api/agent/conversations/${currentId}`);
    currentId = null;
    await loadThreads();
  }

  async function selectThread(id, skipReload) {
    currentId = id;
    if (!skipReload) await loadThreads();
    const { conversations } = await v().api.get('/api/agent/conversations');
    const c = conversations.find((x) => x.id === id);
    els.title.textContent = (c && c.title) || 'New chat';
    els.delBtn.classList.toggle('hidden', !c);
    // highlight
    els.threads.querySelectorAll('button[data-id]').forEach((b) => {
      const on = Number(b.dataset.id) === id;
      b.classList.toggle('bg-sage-100', on);
      b.classList.toggle('ring-1', on);
      b.classList.toggle('ring-sage-300', on);
    });
    await renderPane();
  }

  // ---- messages + drafts --------------------------------------------------

  function draftCard(d) {
    const p = d.payload || {};
    const meta = ACTION_META[d.kind] || ACTION_META.note;
    const el = document.createElement('div');
    el.className = 'rounded-xl bg-beige-50 px-3 py-2 ring-1 ring-sage-300 space-y-1';
    el.dataset.draft = d.id;
    const bits = [];
    if (p.action === 'reminder' && p.reminder_title) bits.push(`<strong>${esc(p.reminder_title)}</strong>`);
    if (p.plant_name) bits.push(`<strong>${esc(p.plant_name)}</strong>`);
    if (p.amount != null) bits.push(`${esc(String(p.amount))}${p.unit ? ' ' + esc(p.unit) : ''}`);
    if (p.detail && d.kind !== 'memory_write') bits.push(esc(p.detail));
    let body = `<p class="text-sm text-navy-800">${meta.icon} ${meta.label}${bits.length ? ' — ' + bits.join(' · ') : ''}</p>`;
    if (p.notes) body += `<p class="text-xs text-navy-500">${esc(p.notes)}</p>`;
    if (d.kind === 'memory_write' && p.memory_file) {
      body += `<p class="text-xs text-navy-400">Appends to “${esc(p.memory_file)}” after your OK</p>`;
    }
    if (d.kind === 'note') body += `<p class="text-xs text-navy-400">Saves to Garden Logs under Notebook</p>`;
    body += `<div class="flex gap-2 pt-1">
      <button type="button" data-confirm-draft class="btn-primary px-3 py-1 text-xs">Confirm &amp; save</button>
      <button type="button" data-discard-draft class="btn-ghost px-3 py-1 text-xs">Discard</button>
    </div>`;
    el.innerHTML = body;
    return el;
  }

  async function renderPane() {
    els.msgs.innerHTML = '';
    if (!currentId) {
      els.msgs.appendChild(bubble('assistant',
        '<p>Pick a chat on the left, or start a new one.</p>'));
      return;
    }
    const [{ messages }, { drafts }] = await Promise.all([
      v().api.get(`/api/agent/conversations/${currentId}/messages`),
      v().api.get(`/api/agent/drafts?conversation_id=${currentId}`),
    ]);
    if (drafts.length) {
      const head = document.createElement('p');
      head.className = 'text-xs font-semibold uppercase tracking-wide text-navy-400';
      head.textContent = `⏳ Waiting on you (${drafts.length})`;
      els.msgs.appendChild(head);
      drafts.forEach((d) => els.msgs.appendChild(draftCard(d)));
      const sep = document.createElement('hr');
      sep.className = 'border-beige-200';
      els.msgs.appendChild(sep);
    }
    if (!messages.length) {
      els.msgs.appendChild(bubble('assistant',
        '<p>Hi! I know your garden — plants, what\'s due, recent logs, the weather. Ask me anything, or just tell me what you did out there and I\'ll draft the log entries. Tell me things worth keeping and I\'ll remember them.</p>'));
    }
    const md = v().markdown || ((s) => `<p>${esc(s)}</p>`);
    messages.forEach((m) => {
      els.msgs.appendChild(bubble(m.role, m.role === 'user' ? `<p>${esc(m.content)}</p>` : md(m.content)));
    });
    els.msgs.scrollTop = els.msgs.scrollHeight;
  }

  async function onSend(event) {
    event.preventDefault();
    const text = els.input.value.trim();
    if (!text || sending) return;
    if (!currentId) {
      const res = await v().api.post('/api/agent/conversations', { title: '' });
      currentId = res.id;
      await loadThreads(currentId);
    }
    sending = true;
    els.input.value = '';
    await renderPane();
    const typing = bubble('assistant', '<p class="text-navy-400">thinking…</p>');
    els.msgs.appendChild(typing);
    els.msgs.scrollTop = els.msgs.scrollHeight;
    try {
      await v().api.post(`/api/agent/conversations/${currentId}/messages`, { message: text });
      await loadThreads(currentId);
    } catch (error) {
      const toast = v().toast || (() => {});
      toast(`Hmm — ${error.message}`, 'err');
    } finally {
      sending = false;
      await renderPane();
      els.input.focus();
    }
  }

  async function onDraftClick(event) {
    const confirmBtn = event.target.closest('[data-confirm-draft]');
    const discardBtn = event.target.closest('[data-discard-draft]');
    if (!confirmBtn && !discardBtn) return;
    const card = event.target.closest('[data-draft]');
    const id = card && card.dataset.draft;
    if (!id) return;
    const toast = v().toast || (() => {});
    try {
      if (confirmBtn) {
        const res = await v().api.post(`/api/agent/drafts/${id}/confirm`);
        toast(res.summary || 'Saved ✓', 'ok');
      } else {
        await v().api.post(`/api/agent/drafts/${id}/discard`);
      }
      await loadThreads(currentId);
    } catch (error) {
      // A draft that needs more info (e.g. no plant): say so, keep the draft.
      toast(error.message, 'err');
    }
  }

  // ---- identity files ------------------------------------------------------

  async function loadFiles() {
    const { files } = await v().api.get('/api/agent/files');
    els.files.innerHTML = '';
    files.forEach((f) => {
      const meta = FILE_META[f.name] || { label: f.name, desc: '' };
      const card = document.createElement('div');
      card.className = 'rounded-2xl bg-beige-100 p-3 ring-1 ring-beige-200';
      card.dataset.file = f.name;
      card.innerHTML = `
        <div class="flex items-baseline justify-between gap-2">
          <p class="font-display text-base font-semibold text-navy-800">${esc(meta.label)}</p>
          <button type="button" data-edit-file class="text-xs text-navy-500 underline hover:text-navy-700">Edit</button>
        </div>
        <p class="text-xs text-navy-400">${esc(meta.desc)}</p>
        <pre data-file-view class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap rounded-xl bg-beige-50 px-3 py-2 text-xs text-navy-700 ring-1 ring-beige-200">${esc(f.content || '')}</pre>
        <div data-file-editor class="mt-2 hidden space-y-2">
          <textarea data-file-text rows="8" class="inp w-full text-xs"></textarea>
          <div class="flex gap-2">
            <button type="button" data-save-file class="btn-primary px-3 py-1 text-xs">Save</button>
            <button type="button" data-cancel-file class="btn-ghost px-3 py-1 text-xs">Cancel</button>
          </div>
        </div>`;
      els.files.appendChild(card);
    });
  }

  async function onFileClick(event) {
    const card = event.target.closest('[data-file]');
    if (!card) return;
    const name = card.dataset.file;
    const view = card.querySelector('[data-file-view]');
    const editor = card.querySelector('[data-file-editor]');
    const area = card.querySelector('[data-file-text]');
    const toast = v().toast || (() => {});
    if (event.target.closest('[data-edit-file]')) {
      area.value = view.textContent;
      view.classList.add('hidden');
      editor.classList.remove('hidden');
      area.focus();
    } else if (event.target.closest('[data-cancel-file]')) {
      view.classList.remove('hidden');
      editor.classList.add('hidden');
    } else if (event.target.closest('[data-save-file]')) {
      try {
        await v().api.put(`/api/agent/files/${name}`, { content: area.value });
        toast('Saved ✓', 'ok');
        await loadFiles();
      } catch (error) {
        toast(error.message, 'err');
      }
    }
  }

  // ---- boot -----------------------------------------------------------------

  async function boot() {
    let st = null;
    try { st = await v().api.get('/api/ai/chat-status'); }
    catch { st = null; }
    if (!st || !st.enabled) {
      els.off.classList.remove('hidden');
      els.grid.classList.add('hidden');
      const pill = els.pill;
      if (st && !st.reachable && st.hint) {
        els.off.querySelector('p').textContent = st.hint;
      }
      return;
    }
    if (st.provider === 'openrouter') {
      els.pill.textContent = 'via OpenRouter';
      els.pill.classList.remove('hidden');
    }
    els.form.addEventListener('submit', onSend);
    els.msgs.addEventListener('click', onDraftClick);
    els.files.addEventListener('click', onFileClick);
    els.newBtn.addEventListener('click', newThread);
    els.delBtn.addEventListener('click', deleteThread);
    try {
      await Promise.all([loadThreads(), loadFiles()]);
    } catch (error) {
      const toast = v().toast || (() => {});
      toast(error.message, 'err');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

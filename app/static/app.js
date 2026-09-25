/* Verdant v2 — route-aware frontend for the garden journal. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]
  ));
  const fmtDate = (iso) => iso
    ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : '—';
  const fmtDateTime = (iso) => iso
    ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : '—';

  const api = {
    async request(method, path, { json, form } = {}) {
      const options = { method, headers: {} };
      if (json !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(json);
      } else if (form) {
        options.body = form;
      }
      const response = await fetch(path, options);
      if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
          const body = await response.json();
          detail = Array.isArray(body.detail)
            ? body.detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
            : body.detail || detail;
        } catch { /* non-JSON response */ }
        throw new Error(detail);
      }
      return response.status === 204 ? null : response.json();
    },
    get(path) { return this.request('GET', path); },
    post(path, json) { return this.request('POST', path, { json }); },
    patch(path, json) { return this.request('PATCH', path, { json }); },
    del(path) { return this.request('DELETE', path); },
    upload(path, form) { return this.request('POST', path, { form }); },
  };

  function toast(message, kind = 'info') {
    const host = $('#toasts');
    if (!host) return;
    const tones = {
      info: 'bg-navy-800 text-beige-50 ring-navy-600',
      ok: 'bg-sage-700 text-beige-50 ring-sage-500',
      err: 'bg-red-800 text-beige-50 ring-red-600',
    };
    const el = document.createElement('div');
    el.className = `pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-botanical ring-1 ${tones[kind]}`;
    el.textContent = message;
    host.append(el);
    setTimeout(() => el.remove(), 3800);
  }

  function markdown(source) {
    let output = esc(source || '');
    output = output
      .replace(/^### (.*)$/gm, '<h3>$1</h3>')
      .replace(/^## (.*)$/gm, '<h2>$1</h2>')
      .replace(/^# (.*)$/gm, '<h1>$1</h1>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return output.split(/\n{2,}/).map((block) => /^<h[1-3]>/.test(block) ? block : `<p>${block.replace(/\n/g, '<br>')}</p>`).join('');
  }

  function setVersion() {
    const version = document.documentElement.dataset.version;
    const target = $('#app-version');
    if (version && target) target.textContent = `v${version}`;
  }

  function setActiveNavigation() {
    const path = window.location.pathname;
    $$('nav a').forEach((link) => {
      const active = link.getAttribute('href') === path;
      if (active) link.setAttribute('aria-current', 'page');
      link.classList.toggle('bg-sage-600', active);
      link.classList.toggle('text-white', active);
    });
  }

  function wireLightboxAndDeletes(reloaders) {
    document.addEventListener('click', async (event) => {
      const lightboxTarget = event.target.closest('[data-lightbox]');
      if (lightboxTarget && $('#lightbox')) {
        $('#lightbox-img').src = lightboxTarget.dataset.lightbox;
        $('#lightbox').classList.replace('hidden', 'flex');
        return;
      }
      const actions = [
        ['[data-delete-post]', 'deletePost', '/api/posts/', 'Delete this entry and its photos?', reloaders.posts],
        ['[data-delete-fert]', 'deleteFert', '/api/fertilizations/', 'Delete this fertilization entry?', reloaders.ferts],
        ['[data-delete-obs]', 'deleteObs', '/api/observations/', 'Delete this observation and its photos?', reloaders.obs],
      ];
      for (const [selector, key, endpoint, question, reload] of actions) {
        const button = event.target.closest(selector);
        if (button && window.confirm(question)) {
          try {
            await api.del(`${endpoint}${button.dataset[key]}`);
            toast('Entry deleted', 'ok');
            await reload?.();
          } catch (error) { toast(error.message, 'err'); }
          return;
        }
      }
    });
    const lightbox = $('#lightbox');
    if (lightbox) lightbox.addEventListener('click', () => lightbox.classList.replace('flex', 'hidden'));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && lightbox) lightbox.classList.replace('flex', 'hidden');
    });
  }

  async function uploadFiles(path, files) {
    if (!files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((file) => form.append('files', file, file.name));
    await api.upload(path, form);
  }

  function wireDraft(form, key, fields) {
    const draft = JSON.parse(localStorage.getItem(key) || '{}');
    fields.forEach((selector) => {
      const input = $(selector);
      if (!input) return;
      if (draft[selector] !== undefined && input.type !== 'file') input.value = draft[selector];
      input.addEventListener('input', () => {
        const next = JSON.parse(localStorage.getItem(key) || '{}');
        next[selector] = input.value;
        localStorage.setItem(key, JSON.stringify(next));
      });
    });
    form.addEventListener('reset', () => localStorage.removeItem(key));
  }

  async function renderStats() {
    const host = $('#stats');
    if (!host) return;
    try {
      const stats = await api.get('/api/stats');
      const cards = [
        ['posts', 'Entries', '📖'], ['observations', 'Observations', '🔍'],
        ['fertilizations', 'Feedings', '🧪'], ['images', 'Photos', '🖼️'],
        ['avg_health', 'Avg health', '💚'],
      ];
      host.innerHTML = cards.map(([key, label, icon]) => `<div class="rounded-xl border border-beige-300 bg-beige-50 px-4 py-3"><dt class="text-xs font-bold uppercase text-navy-500">${icon} ${label}</dt><dd class="mt-1 font-display text-2xl text-sage-700">${esc(stats[key] ?? '—')}</dd></div>`).join('');
    } catch { /* stats are supplementary */ }
  }

  function postCard(post) {
    const images = post.images || [];
    return `<article class="card space-y-4" data-post="${post.id}">
      <header class="flex justify-between gap-3 border-b border-beige-200 pb-3">
        <div><h3 class="font-display text-xl font-semibold">${esc(post.title)}</h3><p class="text-xs text-navy-400">${fmtDateTime(post.created_at)}</p></div>
        <div class="flex gap-2"><button type="button" class="btn-ghost text-sm" data-edit-post="${post.id}">Edit</button><button type="button" class="btn-ghost text-sm" data-delete-post="${post.id}" aria-label="Delete entry">🗑</button></div>
      </header>
      ${post.content?.trim() ? `<div class="md">${markdown(post.content)}</div>` : ''}
      ${images.length ? `<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">${images.map((image) => `<button type="button" data-lightbox="${esc(image.file_path)}"><img src="${esc(image.file_path)}" alt="Photo from ${esc(post.title)}" class="h-40 w-full rounded-lg object-cover"></button>`).join('')}</div>` : ''}
    </article>`;
  }

  function initBlog() {
    const form = $('#post-form');
    if (!form) return {};
    let posts = [];
    let editingId = null;
    let offset = 0;
    const pageSize = 20;
    const feed = $('#feed');
    const loadMore = $('#posts-load-more');

    async function loadPosts(reset = true) {
      if (reset) offset = 0;
      const query = $('#post-search')?.value.trim() || '';
      const batch = await api.get(`/api/posts?limit=${pageSize}&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ''}`);
      posts = reset ? batch : posts.concat(batch);
      feed.innerHTML = posts.length ? posts.map(postCard).join('') : '<div class="card text-center text-navy-500">No entries yet. Write your first garden story.</div>';
      $('#feed-count').textContent = `${posts.length} ${posts.length === 1 ? 'entry' : 'entries'}`;
      if (loadMore) loadMore.classList.toggle('hidden', batch.length < pageSize);
    }

    wireDraft(form, 'verdant.draft.blog', ['#post-title', '#post-content']);
    $('#post-images')?.addEventListener('change', (event) => {
      $('#post-images-preview').innerHTML = Array.from(event.target.files || []).map((file) => `<li class="text-xs text-navy-500">${esc(file.name)}</li>`).join('');
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = $('button[type="submit"]', form);
      button.disabled = true;
      try {
        const payload = { title: $('#post-title').value.trim(), content: $('#post-content').value };
        const post = editingId
          ? await api.patch(`/api/posts/${editingId}`, payload)
          : await api.post('/api/posts', payload);
        if (!editingId) await uploadFiles(`/api/posts/${post.id}/images`, $('#post-images').files);
        editingId = null;
        form.reset();
        localStorage.removeItem('verdant.draft.blog');
        button.textContent = 'Publish entry';
        toast('Entry saved 🌿', 'ok');
        await Promise.all([loadPosts(), renderStats()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
      finally { button.disabled = false; }
    });
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-edit-post]');
      if (!button) return;
      const post = posts.find((item) => item.id === Number(button.dataset.editPost));
      if (!post) return;
      editingId = post.id;
      $('#post-title').value = post.title;
      $('#post-content').value = post.content || '';
      $('button[type="submit"]', form).textContent = 'Save changes';
      form.scrollIntoView({ behavior: 'smooth' });
    });
    let searchTimer;
    $('#post-search')?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadPosts(), 250);
    });
    loadMore?.addEventListener('click', async () => { offset += pageSize; await loadPosts(false); });
    loadPosts().catch((error) => toast(`Could not load entries: ${error.message}`, 'err'));
    renderStats();
    return { posts: loadPosts };
  }

  function healthBar(score) {
    const color = score >= 8 ? 'bg-sage-600' : score >= 5 ? 'bg-beige-500' : 'bg-red-600';
    return `<div class="flex items-center gap-2"><div class="h-2 w-16 rounded bg-beige-200"><div class="h-full ${color}" style="width:${score * 10}%"></div></div><b>${score}</b></div>`;
  }

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
      $('#obs-rows').innerHTML = observations.length ? observations.map((item) => `<tr><td class="td">${fmtDate(item.date)}</td><td class="td">${esc(item.plant_name)}</td><td class="td">${healthBar(item.health_scale)}</td><td class="td">${item.watering_status ? '💧 Watered' : '—'}</td><td class="td">${esc(item.pest_sightings) || 'None'}</td><td class="td">${esc(item.notes) || '—'}</td><td class="td">${(item.images || []).map((image) => `<button data-lightbox="${esc(image.file_path)}"><img src="${esc(image.file_path)}" class="h-10 w-10 rounded object-cover" alt="${esc(item.plant_name)}"></button>`).join('') || '—'}</td><td class="td text-right"><button class="text-sage-700" data-edit-obs="${item.id}">Edit</button> <button data-delete-obs="${item.id}" aria-label="Delete observation">🗑</button></td></tr>`).join('') : '<tr><td class="td text-center" colspan="8">No observations yet.</td></tr>';
    }

    wireDraft(fertForm, 'verdant.draft.fert', ['#fert-date', '#fert-name', '#fert-npk', '#fert-amount', '#fert-notes']);
    wireDraft(obsForm, 'verdant.draft.obs', ['#obs-date', '#obs-plant', '#obs-health', '#obs-water', '#obs-pests', '#obs-notes']);
    $('#obs-health').addEventListener('input', () => { $('#obs-health-out').textContent = $('#obs-health').value; });

    fertForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const payload = { date: $('#fert-date').value, fertilizer_name: $('#fert-name').value.trim(), npk_ratio: $('#fert-npk').value.trim(), amount_used: $('#fert-amount').value.trim(), notes: $('#fert-notes').value };
        editingFert ? await api.patch(`/api/fertilizations/${editingFert}`, payload) : await api.post('/api/fertilizations', payload);
        editingFert = null; fertForm.reset(); localStorage.removeItem('verdant.draft.fert'); $('#fert-date').value = today;
        $('button[type="submit"]', fertForm).textContent = 'Add fertilization';
        toast('Fertilization saved 🧪', 'ok'); await Promise.all([loadFerts(), renderStats()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
    });
    obsForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const payload = { date: $('#obs-date').value, plant_name: $('#obs-plant').value.trim(), health_scale: Number($('#obs-health').value), watering_status: $('#obs-water').value === 'true', pest_sightings: $('#obs-pests').value.trim(), notes: $('#obs-notes').value };
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
        editingObs = item.id; $('#obs-date').value = item.date; $('#obs-plant').value = item.plant_name; $('#obs-health').value = item.health_scale; $('#obs-health-out').textContent = item.health_scale; $('#obs-water').value = String(item.watering_status); $('#obs-pests').value = item.pest_sightings; $('#obs-notes').value = item.notes;
        $('button[type="submit"]', obsForm).textContent = 'Save changes'; obsForm.scrollIntoView({ behavior: 'smooth' });
      }
    });
    let filterTimer;
    $('#obs-filter').addEventListener('input', () => { clearTimeout(filterTimer); filterTimer = setTimeout(() => loadObs(), 250); });
    Promise.all([loadFerts(), loadObs(), renderStats()]).catch((error) => toast(`Could not load garden logs: ${error.message}`, 'err'));
    return { ferts: loadFerts, obs: loadObs };
  }

  function heatLevel(count) {
    if (count <= 0) return 0;
    if (count === 1) return 1;
    if (count <= 3) return 2;
    if (count <= 6) return 3;
    return 4;
  }

  function dayModalHtml(iso, entries) {
    const list = entries.slice().sort((a, b) => b.health_scale - a.health_scale);
    const pretty = new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    const cards = list.map((item) => `
      <article class="rounded-xl border border-beige-200 bg-white p-4">
        <div class="flex items-center justify-between gap-2">
          <h4 class="font-semibold text-navy-800">${esc(item.plant_name)}</h4>
          <span class="pill">${esc(String(item.health_scale))}/10 health</span>
        </div>
        ${item.pest_sightings ? `<p class="mt-2 text-sm">&#x1F41B; <span class="font-semibold">Pests:</span> ${esc(item.pest_sightings)}</p>` : ''}
        ${item.notes ? `<p class="mt-1 text-sm text-navy-600">${esc(item.notes)}</p>` : ''}
      </article>`).join('');
    return `
      <div class="modal-backdrop" data-close></div>
      <div class="modal-card card" role="dialog" aria-modal="true" aria-label="Observations on ${esc(iso)}">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 class="font-display text-xl font-semibold">${esc(pretty)}</h3>
            <p class="text-sm text-navy-500">${list.length} observation${list.length === 1 ? '' : 's'}</p>
          </div>
          <button type="button" class="btn-ghost" data-close aria-label="Close">&times;</button>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">${cards}</div>
        <div class="mt-4 text-right">
          <a class="btn-primary text-sm" href="/observations?date=${esc(iso)}">View in Garden Logs &rarr;</a>
        </div>
      </div>`;
  }

  function openDayModal(iso, entries) {
    const modal = $('#day-modal');
    if (!modal) return;
    modal.innerHTML = dayModalHtml(iso, entries);
    modal.classList.remove('hidden');
    modal.classList.add('modal-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeDayModal() {
    const modal = $('#day-modal');
    if (!modal || modal.classList.contains('hidden')) return;
    modal.classList.add('hidden');
    modal.classList.remove('modal-open');
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = '';
    document.body.style.overflow = '';
  }

  function initCalendar() {
    const grid = $('#calendar-grid');
    if (!grid) return;
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    api.get('/api/stats/calendar').then((observations) => {
      const byDate = new Map();
      observations.forEach((item) => {
        const key = String(item.date).slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) return;
        if (!byDate.has(key)) byDate.set(key, []);
        byDate.get(key).push(item);
      });
      const today = new Date();
      const months = [];
      for (let delta = -2; delta <= 0; delta += 1) months.push(new Date(today.getFullYear(), today.getMonth() + delta, 1));
      const legend = `<div class="flex items-center justify-end gap-1.5 pt-2 text-xs text-navy-500"><span>Less</span>${[0, 1, 2, 3, 4].map((level) => `<span class="heat-swatch heat-${level}" aria-hidden="true"></span>`).join('')}<span>More</span></div>`;
      grid.innerHTML = months.map((monthDate) => {
        const year = monthDate.getFullYear();
        const month = monthDate.getMonth();
        const cells = Array(monthDate.getDay()).fill('<div class="calendar-day calendar-empty"></div>');
        const days = new Date(year, month + 1, 0).getDate();
        for (let day = 1; day <= days; day += 1) {
          const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const entries = byDate.get(iso) || [];
          const level = heatLevel(entries.length);
          const average = entries.length ? Math.round(entries.reduce((sum, item) => sum + item.health_scale, 0) / entries.length) : null;
          const tip = entries.length
            ? `${entries.length} observation${entries.length === 1 ? '' : 's'} on ${iso}${average ? `, average health ${average}/10` : ''} — view in Garden Logs`
            : `No observations on ${iso}`;
          cells.push(`<a href="/observations?date=${iso}" data-date="${iso}" class="calendar-day heat-${level}" title="${esc(tip)}"><span>${day}</span></a>`);
        }
        return `<section class="card"><h2 class="mb-4 font-display text-xl font-semibold">${monthDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2><div class="calendar-weekdays">${weekdays.map((day) => `<span>${day}</span>`).join('')}</div><div class="calendar-month">${cells.join('')}</div>${legend}</section>`;
      }).join('');
      grid.addEventListener('click', (ev) => {
        const link = ev.target.closest('a[data-date]');
        if (!link) return;
        ev.preventDefault();
        const iso = link.getAttribute('data-date');
        openDayModal(iso, byDate.get(iso) || []);
      });
      const modal = $('#day-modal');
      modal?.addEventListener('click', (ev) => {
        if (ev.target.closest('[data-close]')) closeDayModal();
      });
      document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') closeDayModal();
      });
      if (!observations.length) $('#calendar-empty')?.classList.remove('hidden');
    }).catch((error) => { grid.innerHTML = `<div class="card text-red-700">Could not load calendar: ${esc(error.message)}</div>`; });
  }

  function initImmich() {
    const sections = $$('#immich-section');
    if (!sections.length) return;
    api.get('/api/immich/status')
      .then((status) => {
        if (!status.configured) return null;
        sections.forEach((section) => section.classList.remove('hidden'));
        return api.get('/api/immich/albums');
      })
      .then((albums) => {
        if (!albums) return;
        $$('#immich-album-select').forEach((sel) => {
          sel.innerHTML = '<option value="">Choose an Immich album…</option>'
            + albums.map((a) => `<option value="${esc(a.id)}">${esc(a.albumName)} (${a.assetCount})</option>`).join('');
        });
      })
      .catch(() => { /* Immich unreachable: leave the section hidden */ });
    $$('#immich-import').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const section = btn.closest('#immich-section');
        const sel = (section && section.querySelector('#immich-album-select')) || $('#immich-album-select');
        const albumId = sel && sel.value;
        if (!albumId) { toast('Choose an Immich album first.', 'err'); return; }
        btn.disabled = true;
        const label = btn.textContent;
        btn.textContent = 'Importing…';
        try {
          const result = await api.post(`/api/immich/albums/${encodeURIComponent(albumId)}/import`);
          toast(`Imported ${result.created} photo${result.created === 1 ? '' : 's'} into \u201C${result.album.name}\u201D.`);
          document.dispatchEvent(new CustomEvent('verdant:albums-changed', { detail: { selectId: result.album.id } }));
        } catch (error) {
          toast(`Import failed: ${error.message}`, 'err');
        } finally {
          btn.disabled = false;
          btn.textContent = label;
        }
      });
    });
  }

  function initPhotos() {
    const picker = $('#photo-album-select');
    if (!picker) return;
    const viewer = $('#slideshow');
    const empty = $('#photos-empty');
    const stage = $('#slide-stage');
    const img = $('#slide-img');
    const caption = $('#slide-caption');
    const counter = $('#slide-counter');
    const playBtn = $('#slide-play');
    let slides = [];
    let index = 0;
    let timer = null;

    async function loadAlbums(selectId) {
      const albums = await api.get('/api/albums');
      picker.innerHTML = '<option value="">Choose an album…</option>'
        + albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${(a.images || []).length})</option>`).join('');
      if (selectId) picker.value = String(selectId);
    }

    function render() {
      if (!slides.length) {
        viewer.classList.add('hidden');
        empty.classList.remove('hidden');
        empty.textContent = picker.value ? 'This album has no photos yet.' : 'Choose an album above to start the slideshow.';
        return;
      }
      empty.classList.add('hidden');
      viewer.classList.remove('hidden');
      const slide = slides[index];
      img.src = slide.file_path;
      img.alt = slide.title || slide.original_name || 'Garden photo';
      caption.textContent = slide.title || slide.original_name || '';
      counter.textContent = `${index + 1} / ${slides.length}`;
      [1, slides.length - 1].forEach((offset) => {
        const preload = new Image();
        preload.src = slides[(index + offset) % slides.length].file_path;
      });
    }

    function go(delta) {
      if (!slides.length) return;
      index = (index + delta + slides.length) % slides.length;
      render();
    }

    function play() {
      stop();
      timer = setInterval(() => go(1), 5000);
      playBtn.innerHTML = '&#10074;&#10074; Pause';
    }

    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
      playBtn.innerHTML = '&#9654; Play';
    }

    async function openAlbum(id) {
      stop();
      if (!id) { slides = []; index = 0; render(); return; }
      try {
        const album = await api.get(`/api/albums/${id}`);
        slides = album.images || [];
        index = 0;
        render();
        if (slides.length) play();
      } catch (error) {
        toast(`Could not load album: ${error.message}`, 'err');
      }
    }

    picker.addEventListener('change', () => openAlbum(picker.value));
    $('#photo-refresh').addEventListener('click', () => loadAlbums().catch((error) => toast(`Could not load albums: ${error.message}`, 'err')));
    $('#slide-prev').addEventListener('click', () => go(-1));
    $('#slide-next').addEventListener('click', () => go(1));
    playBtn.addEventListener('click', () => { if (timer) stop(); else if (slides.length) play(); });
    $('#slide-fullscreen').addEventListener('click', () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (stage.requestFullscreen) stage.requestFullscreen();
    });
    document.addEventListener('keydown', (event) => {
      if (!slides.length || viewer.classList.contains('hidden')) return;
      if (event.key === 'ArrowLeft') go(-1);
      else if (event.key === 'ArrowRight') go(1);
    });
    document.addEventListener('verdant:albums-changed', (event) => {
      loadAlbums(event.detail && event.detail.selectId)
        .then(() => openAlbum(picker.value))
        .catch((error) => toast(`Could not load albums: ${error.message}`, 'err'));
    });
    loadAlbums().catch((error) => toast(`Could not load albums: ${error.message}`, 'err'));
  }

  function boot() {
    setVersion();
    setActiveNavigation();
    const reloaders = { ...initBlog(), ...initLogs() };
    initCalendar();
    initImmich();
    initPhotos();
    wireLightboxAndDeletes(reloaders);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();

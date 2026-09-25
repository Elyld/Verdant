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
        const immichAlbumId = sel && sel.value;
        if (!immichAlbumId) { toast('Choose an Immich album first.', 'err'); return; }
        btn.disabled = true;
        const label = btn.textContent;
        try {
          // Big albums import in batches (50/request) so no single request
          // times out. Batches are idempotent server-side: a retried batch
          // never duplicates photos.
          const batchSize = 50;
          let localAlbumId = null, offset = 0, done = false;
          let totalCreated = 0, albumName = '';
          while (!done) {
            const qs = `?offset=${offset}&limit=${batchSize}` + (localAlbumId ? `&album_id=${localAlbumId}` : '');
            const result = await api.post(`/api/immich/albums/${encodeURIComponent(immichAlbumId)}/import${qs}`);
            localAlbumId = result.album_id;
            albumName = result.album_name;
            totalCreated += result.created;
            offset += batchSize;
            done = result.done;
            btn.textContent = `Importing… ${result.imported}/${result.total}`;
          }
          toast(`Imported ${totalCreated} photo${totalCreated === 1 ? '' : 's'} into \u201C${albumName}\u201D.`);
          document.dispatchEvent(new CustomEvent('verdant:albums-changed', { detail: { selectId: localAlbumId } }));
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

  function plantCard(plant, locationName, badges) {
    const cadence = [
      plant.water_every_days ? `💧 every ${plant.water_every_days}d` : '',
      plant.feed_every_days ? `🧪 every ${plant.feed_every_days}d` : '',
    ].filter(Boolean).join(' · ') || 'No care schedule';
    return `<article class="card cursor-pointer transition hover:shadow-botanical" data-plant-card="${plant.id}" data-open-plant="${plant.id}" tabindex="0" role="button" aria-label="Open ${esc(plant.variety_name)}">
      <div class="plant-cover mb-3 grid h-36 place-items-center overflow-hidden rounded-lg bg-sage-100 text-4xl" data-cover="${plant.id}">🌱</div>
      <div class="flex items-start justify-between gap-2">
        <h3 class="font-display text-lg font-semibold text-navy-800">${esc(plant.variety_name)}</h3>
        <span class="pill">${esc(plant.status || 'Growing')}</span>
      </div>
      <p class="text-sm text-navy-500">${esc(plant.species_type || '')}${plant.species_type && locationName ? ' · ' : ''}${esc(locationName || '')}</p>
      <p class="mt-1 text-xs text-navy-400">${esc(cadence)}</p>
      ${badges ? `<div class="mt-2 flex flex-wrap gap-1">${badges}</div>` : ''}
    </article>`;
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

  function plantModalHtml(plant, timeline, locationName) {
    const events = timeline.events || [];
    const photos = timeline.photos || [];
    const harvests = events.filter((e) => e.kind === 'harvest');
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
            <h4 class="mb-2 font-display text-lg font-semibold">Harvests <span class="pill ml-1">${harvests.length}</span></h4>
            ${harvests.length ? `<ul class="mb-3 space-y-1.5 text-sm">${harvests.map((h) => `<li class="flex justify-between gap-2"><span>🧺 ${esc(h.title.replace('Harvested ', ''))}</span><span class="text-navy-400">${fmtDate(h.date)}</span></li>`).join('')}</ul>` : '<p class="mb-3 text-sm text-navy-400">No harvests logged yet.</p>'}
            <form data-harvest-form="${plant.id}" class="grid grid-cols-2 gap-2 rounded-xl border border-beige-200 bg-beige-50 p-3">
              <div><label class="lbl">Date</label><input type="date" class="inp text-sm" data-hv-date value="${today}" required /></div>
              <div><label class="lbl">Quantity</label><input type="number" min="1" value="1" class="inp text-sm" data-hv-qty required /></div>
              <div><label class="lbl">Unit</label><select class="inp text-sm" data-hv-unit><option>fruit</option><option>vegetables</option><option>oz</option><option>lbs</option><option>bunch</option><option>head</option><option>handful</option></select></div>
              <div><label class="lbl">Weight (oz)</label><input type="number" min="0" step="0.1" class="inp text-sm" data-hv-weight placeholder="optional" /></div>
              <div class="col-span-2"><label class="lbl">Notes</label><input class="inp text-sm" data-hv-notes maxlength="200" placeholder="optional" /></div>
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

  function openPlantModal(plant, timeline, locationName) {
    const modal = $('#plant-modal');
    if (!modal) return;
    modal.innerHTML = `<div class="modal-backdrop" data-close></div><div class="modal-card modal-wide card" role="dialog" aria-modal="true" aria-label="${esc(plant.variety_name)}">${plantModalHtml(plant, timeline, locationName)}</div>`;
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
        const [plant, timeline] = await Promise.all([
          api.get(`/api/plants/${plantId}`),
          api.get(`/api/plants/${plantId}/timeline`),
        ]);
        openPlantModal(plant, timeline, locationName(plant.location_id));
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
      .catch((error) => toast(`Could not load plants: ${error.message}`, 'err'));
    return { plants: loadPlants };
  }

  /* ------------------------------ Review ------------------------------ */

  function initReview() {
    const yearEl = $('#review-year');
    if (!yearEl) return {};
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    let year = new Date().getFullYear();

    function statCard(icon, label, value) {
      return `<div class="rounded-xl border border-beige-300 bg-beige-50 px-4 py-3"><dt class="text-xs font-bold uppercase text-navy-500">${icon} ${label}</dt><dd class="mt-1 font-display text-2xl text-sage-700">${value}</dd></div>`;
    }

    function bars(values, max, colorFor, formatTip) {
      return values.map((value, i) => {
        const height = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 4;
        const tip = formatTip ? formatTip(value, i) : `${value}`;
        return `<div class="flex h-full flex-1 items-end" title="${esc(tip)}"><div class="w-full rounded-t ${colorFor(value, i)}" style="height:${height}%"></div></div>`;
      }).join('');
    }

    async function load() {
      yearEl.textContent = year;
      const data = await api.get(`/api/stats/review?year=${year}`);
      const yearlyHealth = (() => {
        let sum = 0; let n = 0;
        data.avg_health_by_month.forEach((avg, i) => {
          const count = data.observations_by_month[i];
          if (avg != null && count) { sum += avg * count; n += count; }
        });
        return n ? (sum / n).toFixed(1) : '—';
      })();
      const harvestLabel = data.harvest_weight
        ? `${data.harvest_count} <span class="text-base text-navy-400">· ${data.harvest_weight} oz</span>`
        : String(data.harvest_count);
      $('#review-stats').innerHTML = [
        statCard('🔍', 'Observations', data.observations),
        statCard('💚', 'Avg health', yearlyHealth),
        statCard('🧺', 'Harvests', harvestLabel),
        statCard('🖼️', 'Photos', data.photos),
        statCard('💧', 'Waterings', data.waterings),
        statCard('🧪', 'Feedings', data.feedings),
        statCard('🐛', 'Pests noted', data.pests_noted),
        statCard('📅', 'Busiest day', data.busiest_day ? `${fmtDate(data.busiest_day)} <span class="text-base text-navy-400">· ${data.busiest_day_count}</span>` : '—'),
      ].join('');

      const maxObs = Math.max(...data.observations_by_month, 1);
      $('#review-activity').innerHTML = bars(
        data.observations_by_month, maxObs,
        (v) => v > 0 ? 'bg-sage-500' : 'bg-beige-200',
        (v, i) => `${MONTHS[i]}: ${v} observations`,
      );
      $('#review-health').innerHTML = bars(
        data.avg_health_by_month.map((v) => v ?? 0), 10,
        (v) => v >= 8 ? 'bg-sage-600' : v >= 5 ? 'bg-beige-500' : v > 0 ? 'bg-red-400' : 'bg-beige-200',
        (v, i) => `${MONTHS[i]}: ${data.avg_health_by_month[i] ?? '—'} avg health`,
      );
      const monthRow = MONTHS.map((m) => `<span class="flex-1 text-center">${m}</span>`).join('');
      $('#review-months').innerHTML = monthRow;
      $('#review-months-2').innerHTML = monthRow;

      $('#review-top').innerHTML = data.top_plants.length
        ? data.top_plants.map((p, i) => `<li class="flex items-center justify-between gap-2 text-sm"><span class="text-navy-800"><b class="text-navy-400">${i + 1}.</b> ${esc(p.plant_name)}</span><span class="pill">${p.observations} obs</span></li>`).join('')
        : '<li class="text-sm text-navy-400">No observations this year yet.</li>';

      const highlights = [];
      if (data.busiest_day) highlights.push(`📅 Busiest day: <b>${fmtDate(data.busiest_day)}</b> with ${data.busiest_day_count} observation${data.busiest_day_count === 1 ? '' : 's'}.`);
      if (data.harvest_count) highlights.push(`🧺 <b>${data.harvest_count}</b> harvest${data.harvest_count === 1 ? '' : 's'}${data.harvest_weight ? ` totaling <b>${data.harvest_weight} oz</b>` : ''}.`);
      if (data.pests_noted) highlights.push(`🐛 Pests noted on <b>${data.pests_noted}</b> observation${data.pests_noted === 1 ? '' : 's'} — check the logs for what worked.`);
      else if (data.observations) highlights.push(`🐛 Not a single pest sighting all year. The garden approves.`);
      if (data.waterings || data.feedings) highlights.push(`💧 <b>${data.waterings}</b> watering${data.waterings === 1 ? '' : 's'} · 🧪 <b>${data.feedings}</b> feeding${data.feedings === 1 ? '' : 's'} logged.`);
      if (!highlights.length) highlights.push('Log some observations to start your story.');
      $('#review-highlights').innerHTML = highlights.map((h) => `<li>${h}</li>`).join('');
    }

    $('#review-prev').addEventListener('click', () => { year -= 1; load().catch((e) => toast(e.message, 'err')); });
    $('#review-next').addEventListener('click', () => { year += 1; load().catch((e) => toast(e.message, 'err')); });
    load().catch((error) => toast(`Could not load review: ${error.message}`, 'err'));
    return {};
  }

  function initBackup() {
    const form = $('#restore-form');
    if (!form) return {};
    const result = $('#restore-result');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const fileInput = $('#restore-file');
      const file = fileInput.files[0];
      if (!file) { toast('Choose a backup file first.', 'err'); return; }
      const submit = $('#restore-submit');
      submit.disabled = true;
      submit.textContent = 'Restoring…';
      try {
        const body = new FormData();
        body.append('file', file);
        const res = await fetch('/api/backup/import', { method: 'POST', body });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Restore failed (${res.status})`);
        const counts = data.restored || {};
        const total = Object.values(counts).reduce((a, b) => a + b, 0);
        result.classList.remove('hidden');
        result.innerHTML = `<div class="rounded-xl border border-sage-300 bg-sage-50 p-4 text-sage-800">✅ Restored <b>${total}</b> records from backup. Reloading…</div>`;
        toast(`Backup restored: ${total} records.`, 'ok');
        setTimeout(() => window.location.reload(), 1500);
      } catch (error) {
        toast(error.message, 'err');
        result.classList.remove('hidden');
        result.innerHTML = `<div class="rounded-xl border border-red-300 bg-red-50 p-4 text-red-800">⚠️ ${error.message}</div>`;
      } finally {
        submit.disabled = false;
        submit.textContent = 'Restore backup';
      }
    });
    return {};
  }

  function initSeedSources() {
    const host = $('#seed-groups');
    if (!host) return {};
    const filter = $('#seed-vendor-filter');
    const form = $('#seed-form');
    let sources = [];
    let plants = [];
    let editingId = null;

    const plantName = (id) => (plants.find((p) => p.id === id) || {}).variety_name || '';
    const newSourceId = () => `SRC-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;

    async function load() {
      try {
        [sources, plants] = await Promise.all([
          api.get('/api/seed-sources/'),
          api.get('/api/plants/'),
        ]);
        if (!Array.isArray(sources)) sources = [];
        if (!Array.isArray(plants)) plants = [];
      } catch (error) {
        toast(`Could not load seed sources: ${error.message}`, 'err');
        return;
      }
      const vendors = [...new Set(sources.map((s) => s.source))].sort();
      filter.innerHTML = '<option value="">All vendors</option>'
        + vendors.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
      const plantLink = $('#seed-plant-link');
      plantLink.innerHTML = '<option value="">— none —</option>'
        + plants.map((p) => `<option value="${p.id}">${esc(p.variety_name || `Plant #${p.id}`)}</option>`).join('');
      render();
    }

    function render() {
      const selected = filter.value;
      const visible = selected ? sources.filter((s) => s.source === selected) : sources;
      $('#seeds-empty').classList.toggle('hidden', visible.length > 0);
      const groups = new Map();
      visible.forEach((s) => {
        if (!groups.has(s.source)) groups.set(s.source, []);
        groups.get(s.source).push(s);
      });
      host.innerHTML = [...groups.entries()].map(([vendor, items]) => `
        <div class="card space-y-3">
          <h3 class="font-display text-lg font-semibold text-navy-800">${esc(vendor)}
            <span class="ml-2 rounded-full bg-sage-100 px-2 py-0.5 text-xs font-body font-semibold text-sage-700">${items.length}</span>
          </h3>
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            ${items.map((s) => `
              <div class="rounded-xl bg-beige-50 p-4 ring-1 ring-beige-200">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <p class="font-semibold text-navy-800">${esc(s.variety)}</p>
                    <p class="text-xs text-navy-500">${esc(s.type || '')}${s.acquired_date ? ` · acquired ${fmtDate(s.acquired_date)}` : ''}</p>
                  </div>
                  <span class="text-xl">🌱</span>
                </div>
                ${s.linked_plant_id && plantName(s.linked_plant_id) ? `<p class="mt-1 text-xs text-sage-700">→ ${esc(plantName(s.linked_plant_id))}</p>` : ''}
                ${s.notes ? `<p class="mt-2 text-sm text-navy-600">${esc(s.notes)}</p>` : ''}
                <div class="mt-3 flex gap-2">
                  <button type="button" class="btn-ghost text-xs" data-edit-seed="${s.id}">Edit</button>
                  <button type="button" class="btn-ghost text-xs text-red-700" data-del-seed="${s.id}">Delete</button>
                </div>
              </div>`).join('')}
          </div>
        </div>`).join('');
    }

    function openForm(item) {
      editingId = item ? item.id : null;
      $('#seed-form-title').textContent = item ? 'Edit seed source' : 'Add seed source';
      $('#seed-submit').textContent = item ? 'Save changes' : 'Add seeds';
      $('#seed-vendor').value = item ? item.source : '';
      $('#seed-variety').value = item ? item.variety : '';
      $('#seed-type').value = item ? item.type : 'Vendor Purchase';
      $('#seed-acquired').value = item && item.acquired_date ? item.acquired_date.slice(0, 10) : '';
      $('#seed-plant-link').value = item && item.linked_plant_id ? String(item.linked_plant_id) : '';
      $('#seed-notes').value = item ? item.notes || '' : '';
      form.classList.remove('hidden');
      $('#seed-vendor').focus();
    }

    $('#seed-add-toggle').addEventListener('click', () => {
      if (form.classList.contains('hidden')) openForm(null);
      else form.classList.add('hidden');
    });
    $('#seed-cancel').addEventListener('click', () => form.classList.add('hidden'));
    filter.addEventListener('change', render);

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {
        source: $('#seed-vendor').value.trim(),
        variety: $('#seed-variety').value.trim(),
        type: $('#seed-type').value,
        acquired_date: $('#seed-acquired').value || null,
        linked_plant_id: $('#seed-plant-link').value ? Number($('#seed-plant-link').value) : null,
        notes: $('#seed-notes').value.trim() || null,
      };
      if (!payload.source || !payload.variety) {
        toast('Vendor and variety are required.', 'err');
        return;
      }
      try {
        if (editingId) {
          await api.patch(`/api/seed-sources/${editingId}`, payload);
          toast('Seed source updated.', 'ok');
        } else {
          payload.source_id = newSourceId();
          await api.post('/api/seed-sources/', payload);
          toast('Seed source added.', 'ok');
        }
        form.classList.add('hidden');
        await load();
      } catch (error) {
        toast(error.message, 'err');
      }
    });

    host.addEventListener('click', async (event) => {
      const editBtn = event.target.closest('[data-edit-seed]');
      const delBtn = event.target.closest('[data-del-seed]');
      if (editBtn) {
        const item = sources.find((s) => s.id === Number(editBtn.dataset.editSeed));
        if (item) openForm(item);
        return;
      }
      if (delBtn) {
        const item = sources.find((s) => s.id === Number(delBtn.dataset.delSeed));
        if (!item) return;
        if (!window.confirm(`Delete "${item.variety}" from ${item.source}?`)) return;
        try {
          await api.del(`/api/seed-sources/${item.id}`);
          toast('Seed source deleted.', 'ok');
          await load();
        } catch (error) {
          toast(error.message, 'err');
        }
      }
    });

    load();
    return {};
  }

  function boot() {
    setVersion();
    setActiveNavigation();
    const reloaders = { ...initBlog(), ...initLogs(), ...initPlants(), ...initReview(), ...initBackup(), ...initSeedSources() };
    initCalendar();
    initImmich();
    initPhotos();
    wireLightboxAndDeletes(reloaders);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
